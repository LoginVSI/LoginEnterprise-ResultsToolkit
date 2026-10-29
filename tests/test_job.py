import contextlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from le_results.client import Client
from le_results.errors import ToolkitError
from le_results.job import job_status, load_job, run_job
from le_results.profiles import Profile
from le_results.selection import Selection
from le_results.synthetic import APP, BASE, CANDIDATE, SESSION, demo

T0 = datetime(2026, 10, 28, 12, 0, 0, tzinfo=UTC)
REPORT = {
    "schema_version": "report/1",
    "title": "Job report",
    "visuals": ["comparison_table", "coverage_table"],
}


@pytest.fixture
def retained(tmp_path):
    demo(tmp_path / "evidence")
    (tmp_path / "report.json").write_text(json.dumps(REPORT))
    config = {
        "schema_version": "job/1",
        "name": "retained-review",
        "baseline_capture": "evidence/baseline",
        "candidate_capture": "evidence/candidate",
        "comparison": "evidence/compare.json",
        "report": "report.json",
    }
    path = tmp_path / "job.json"
    path.write_text(json.dumps(config))
    return path, tmp_path / "out", config


def clock(*steps):
    values = iter(steps)
    return lambda: next(values)


def test_retained_job_publishes_complete_run_and_status(retained):
    path, root, _ = retained
    result = run_job(path, root, now=lambda: T0)
    published = root / "runs" / "20261028T120000Z"
    assert Path(result["published"]) == published
    assert (published / "comparison.json").is_file() and (
        published / "report" / "report.html"
    ).is_file()
    summary = json.loads((published / "job-run.json").read_text())
    assert summary["mode"] == "retained-captures" and summary["provenance"] == ["synthetic"]
    # Source freshness is the retained observation, not the run time.
    assert summary["latest_source_observation"] == "2026-09-01T10:02:00Z"
    status = json.loads((root / "status.json").read_text())
    assert status["last_attempt"]["outcome"] == "succeeded"
    assert status["last_success"]["latest_source_observation"] == "2026-09-01T10:02:00Z"
    assert json.loads((root / "latest.json").read_text())["stamp"] == "20261028T120000Z"
    assert not (root / ".lock").exists() and not any((root / ".staging").iterdir())


def test_same_second_runs_do_not_collide_and_prior_run_is_kept(retained):
    path, root, _ = retained
    run_job(path, root, now=lambda: T0)
    run_job(path, root, now=lambda: T0)
    assert sorted(p.name for p in (root / "runs").iterdir()) == [
        "20261028T120000Z",
        "20261028T120000Z-1",
    ]


def test_failed_run_never_replaces_last_good_and_is_visible(retained):
    path, root, config = retained
    run_job(path, root, now=lambda: T0)
    good = (root / "latest.json").read_bytes()
    broken = dict(config, comparison="missing.json")
    path.write_text(json.dumps(broken))
    with pytest.raises(ToolkitError, match="Last good output is unchanged"):
        run_job(path, root, now=lambda: T0 + timedelta(hours=1))
    assert (root / "latest.json").read_bytes() == good
    failed = list((root / "failed").iterdir())
    assert len(failed) == 1 and (failed[0] / "baseline" / "manifest.json").is_file()
    status = job_status(root, now=T0 + timedelta(hours=2))
    assert status["ok"] is False
    assert "last attempt failed" in status["problems"][0]
    assert status["last_success"]["stamp"] == "20261028T120000Z"
    assert status["last_attempt"]["outcome"] == "failed"


def test_concurrent_run_is_skipped_without_touching_outputs(retained):
    path, root, _ = retained
    root.mkdir()
    (root / ".lock").write_text(json.dumps({"started": T0.isoformat(), "pid": 1}))
    with pytest.raises(ToolkitError) as caught:
        run_job(path, root, now=lambda: T0 + timedelta(minutes=5))
    assert caught.value.code == "job_locked"
    assert (root / ".lock").exists()  # another run's lock is never removed
    assert not (root / "status.json").exists() and not (root / "runs").exists()


def test_stale_lock_message_tells_owner_what_to_do(retained):
    path, root, _ = retained
    root.mkdir()
    (root / ".lock").write_text(json.dumps({"started": T0.isoformat(), "pid": 1}))
    with pytest.raises(ToolkitError, match="delete .lock"):
        run_job(path, root, now=lambda: T0 + timedelta(hours=13))


def test_requested_pdf_failure_is_a_failed_run(retained):
    path, root, config = retained
    path.write_text(json.dumps(dict(config, pdf=True)))

    def broken_renderer(report_dir, out):
        raise ToolkitError("No Chromium-family browser found.", code="pdf_renderer_missing")

    with pytest.raises(ToolkitError) as caught:
        run_job(path, root, now=lambda: T0, renderer=broken_renderer)
    assert caught.value.code == "pdf_renderer_missing"
    assert not (root / "runs").exists() and not (root / "latest.json").exists()
    assert job_status(root)["last_attempt"]["error"]["code"] == "pdf_renderer_missing"


def test_pdf_is_published_with_the_run_when_rendering_succeeds(retained):
    path, root, config = retained
    path.write_text(json.dumps(dict(config, pdf=True)))

    def renderer(report_dir, out):
        out.write_bytes(b"%PDF-stub")
        return {}

    run_job(path, root, now=lambda: T0, renderer=renderer)
    published = root / "runs" / "20261028T120000Z"
    assert (published / "report.pdf").is_file()
    assert "report.pdf" in json.loads((published / "job-run.json").read_text())["outputs"]


def test_freshness_distinguishes_run_time_from_source_observation(retained):
    path, root, _ = retained
    run_job(path, root, now=lambda: T0)
    # The run just succeeded but its newest source data is almost two months old.
    stale = job_status(root, max_age_hours=24, now=T0)
    assert stale["ok"] is False and "older than 24 hours" in stale["problems"][0]
    assert job_status(root, now=T0)["ok"] is True
    assert job_status(root / "nowhere", now=T0)["problems"] == ["no successful run yet"]


def test_retention_is_opt_in_and_never_removes_the_latest(retained):
    path, root, config = retained
    path.write_text(json.dumps(dict(config, keep_runs=2)))
    for minute in range(3):
        run_job(path, root, now=lambda minute=minute: T0 + timedelta(minutes=minute))
    assert sorted(p.name for p in (root / "runs").iterdir()) == [
        "20261028T120100Z",
        "20261028T120200Z",
    ]


@pytest.mark.parametrize(
    "patch",
    [
        {"unexpected": 1},
        {"name": "Bad Name"},
        {"baseline_selection": "s.json"},  # mixed with captures
        {"pdf": True, "report": None},
        {"keep_runs": 0},
        {"limits": {"token": "x"}},
        {"schema_version": "job/2"},
    ],
)
def test_job_config_is_strict(retained, patch):
    path, _, config = retained
    merged = {**config, **patch}
    merged = {k: v for k, v in merged.items() if v is not None}
    path.write_text(json.dumps(merged))
    with pytest.raises(ToolkitError):
        load_job(path)


def appliance_handler(fail_measurements=False):
    def handler(req):
        path = req.url.path
        if path.endswith("system/version") or path.endswith("system/eux-version"):
            return httpx.Response(200, json={"version": "synthetic"})
        run = BASE if BASE in path else CANDIDATE
        if path.endswith("/test-runs/" + run):
            return httpx.Response(
                200,
                json={
                    "type": "LoadTest",
                    "id": run,
                    "state": "completed",
                    "finished": "2026-09-01T11:00:00Z",
                },
            )
        if path.endswith("eux-results"):
            return httpx.Response(200, json=[])
        if path.endswith("load-test-run-overview/" + run):
            return httpx.Response(404, json={})
        offset = int(req.url.params.get("offset", 0))
        rows: list[dict] = []
        if path.endswith("user-sessions"):
            rows = [{"id": SESSION, "testRunId": run, "loginState": "succeeded"}]
        elif path.endswith("app-executions"):
            rows = [
                {
                    "id": "55555555-5555-4555-8555-555555555555",
                    "testRunId": run,
                    "userSessionId": SESSION,
                    "applicationId": APP,
                    "state": "ended",
                }
            ]
        elif path.endswith("measurements"):
            if fail_measurements:
                return httpx.Response(500, json={})
            rows = [
                {
                    "testRunId": run,
                    "measurementId": "synthetic-open",
                    "duration": 100 if run == BASE else 120,
                    "applicationId": APP,
                    "appExecutionId": "55555555-5555-4555-8555-555555555555",
                    "timestamp": "2026-09-01T10:30:00Z",
                }
            ]
        return httpx.Response(200, json={"items": rows, "offset": offset, "totalCount": len(rows)})

    return handler


@pytest.fixture
def appliance(tmp_path):
    for name, run in (("baseline", BASE), ("candidate", CANDIDATE)):
        Selection("LoadTest", [run]).write(tmp_path / f"{name}.json")
    comparison = {
        "schema_version": "comparison/1",
        "baseline": {"label": "Base", "ids": [BASE]},
        "candidate": {"label": "Cand", "ids": [CANDIDATE]},
        "metrics": [
            {
                "name": "Open",
                "table": "measurements",
                "value_field": "duration",
                "match": {"measurementId": "synthetic-open", "applicationId": APP},
                "group_by": [],
                "unit": "ms",
                "semantics": "duration",
                "direction": "lower",
            }
        ],
    }
    (tmp_path / "compare.json").write_text(json.dumps(comparison))
    path = tmp_path / "job.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "job/1",
                "name": "lab-load",
                "profile": "lab",
                "baseline_selection": "baseline.json",
                "candidate_selection": "candidate.json",
                "comparison": "compare.json",
            }
        )
    )
    return path, tmp_path / "out"


def factory(handler):
    @contextlib.contextmanager
    def make(profile, limits):
        client = Client(
            Profile(profile, "https://appliance.example.com"),
            "synthetic-token",
            transport=httpx.MockTransport(handler),
            retries=0,
            sleep=lambda s: None,
        )
        with client:
            yield client

    return make


def test_appliance_job_captures_compares_and_publishes(appliance):
    path, root = appliance
    result = run_job(path, root, factory(appliance_handler()), now=lambda: T0)
    published = Path(result["published"])
    comparison = json.loads((published / "comparison.json").read_text())
    assert comparison["metrics"][0]["baseline_mean"] == 100
    assert comparison["metrics"][0]["candidate_mean"] == 120
    assert (
        verify_status(root)["last_success"]["latest_source_observation"] == "2026-09-01T10:30:00Z"
    )


def verify_status(root):
    return json.loads((root / "status.json").read_text())


def test_partial_acquisition_never_becomes_a_successful_run(appliance):
    path, root = appliance
    run_job(path, root, factory(appliance_handler()), now=lambda: T0)
    before = (root / "latest.json").read_bytes()
    with pytest.raises(ToolkitError, match="Last good output is unchanged"):
        run_job(
            path,
            root,
            factory(appliance_handler(fail_measurements=True)),
            now=lambda: T0 + timedelta(hours=1),
        )
    assert (root / "latest.json").read_bytes() == before
    kept = next((root / "failed").iterdir())
    manifest = json.loads((kept / "baseline" / "manifest.json").read_text())
    assert manifest["status"] in ("partial", "failed")  # partial evidence kept for diagnosis
    assert len(list((root / "runs").iterdir())) == 1


def test_rolling_hours_only_for_continuous_selections(appliance):
    path, root = appliance
    config = json.loads(path.read_text())
    path.write_text(json.dumps(dict(config, rolling_hours=24)))
    with pytest.raises(ToolkitError, match="Continuous"):
        run_job(path, root, factory(appliance_handler()), now=lambda: T0)
