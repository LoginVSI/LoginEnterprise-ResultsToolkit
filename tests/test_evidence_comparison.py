import json
from datetime import UTC, datetime

import httpx
import pytest

from le_results.client import Client
from le_results.compare import compare
from le_results.errors import ToolkitError
from le_results.evidence import (
    TABLES,
    capture,
    finalize,
    load_table,
    normalize,
    unique,
    verify_capture,
)
from le_results.profiles import Profile
from le_results.selection import Selection, rolling, utc
from le_results.synthetic import APP, BASE, CANDIDATE, EXECUTION, SESSION, demo


def edit_capture(directory, table, rows):
    manifest = verify_capture(directory)
    tables = {k: load_table(directory, k) for k in TABLES}
    tables[table] = rows
    finalize(directory, manifest, tables)


@pytest.fixture
def pair(tmp_path):
    demo(tmp_path)
    config = json.loads((tmp_path / "compare.json").read_text())
    return tmp_path / "baseline", tmp_path / "candidate", config


def test_independent_arithmetic_and_failure_reconciliation(pair):
    b, c, config = pair
    result = compare(b, c, config)
    row = result["metrics"][0]
    # Independent hand-calculated known inputs, not the production aggregation implementation.
    assert row["baseline_mean"] == 120
    assert row["candidate_mean"] == 130
    assert row["absolute_change"] == 10
    assert row["relative_change_percent"] == pytest.approx(100 / 12)
    assert row["baseline_samples"] == row["candidate_samples"] == 3
    assert result["coverage"][1]["execution_failures"] == 1
    assert row["interpretation"] == "worsened"


def test_unmatched_configured_metric_never_zero(pair):
    b, c, config = pair
    config["metrics"][0]["match"] = {"measurementId": "configured-but-empty"}
    row = compare(b, c, config)["metrics"][0]
    assert row["baseline_mean"] is None and row["absolute_change"] is None
    assert row["baseline_samples"] == 0


def test_unmatched_candidate_preserves_baseline(pair):
    b, c, config = pair
    edit_capture(c, "measurements", [])
    row = compare(b, c, config)["metrics"][0]
    assert row["baseline_mean"] == 120 and row["candidate_mean"] is None
    assert row["absolute_change"] is None


def test_zero_baseline_relative_undefined(pair):
    b, c, config = pair
    rows = load_table(b, "measurements")
    for row in rows:
        row["duration"] = 0
    edit_capture(b, "measurements", rows)
    row = compare(b, c, config)["metrics"][0]
    assert row["absolute_change"] == 130 and row["relative_change_percent"] is None


def test_missing_and_nonfinite_values_are_not_samples(pair):
    b, c, config = pair
    rows = load_table(c, "measurements")
    rows[0]["duration"] = None
    rows[1]["duration"] = ">N"
    edit_capture(c, "measurements", rows)
    row = compare(b, c, config)["metrics"][0]
    assert row["candidate_samples"] == 1 and row["candidate_missing"] == 2


def test_status_timer_rejected_and_resource_timer_explicit(pair):
    b, c, config = pair
    config["metrics"][0]["semantics"] = "status"
    with pytest.raises(ToolkitError, match="categorical"):
        compare(b, c, config)
    config["metrics"][0]["semantics"] = "resource"
    config["metrics"][0]["unit"] = "bytes"
    assert compare(b, c, config)["metrics"][0]["unit"] == "bytes"


def test_wmi_reorder_missing_instance_and_shared_host_sessions(pair):
    b, c, config = pair
    metric = config["metrics"][0]
    metric.update(
        table="session_metrics",
        value_field="measurement",
        unit="%",
        match={"displayName": "CPU"},
        group_by=["instance", "fieldName", "unit"],
        semantics="resource",
    )

    def row(run, instance, value, session):
        return {
            "testRunId": run,
            "instance": instance,
            "fieldName": "CPU",
            "displayName": "CPU",
            "unit": "%",
            "measurement": value,
            "userSessionKey": session,
            "timestamp": "2026-09-01T10:00:00Z",
        }

    edit_capture(
        b,
        "session_metrics",
        [
            row(BASE, "host-a", 20, "s1"),
            row(BASE, "host-b", 50, "s2"),
            row(BASE, "host-a", 20, "s3"),
        ],
    )
    edit_capture(
        c,
        "session_metrics",
        [row(CANDIDATE, "host-b", 60, "s2"), row(CANDIDATE, "host-a", 30, "s1")],
    )
    rows = {r["group"]["instance"]: r for r in compare(b, c, config)["metrics"]}
    assert rows["host-a"]["absolute_change"] == 10
    assert rows["host-b"]["absolute_change"] == 10
    assert rows["host-a"]["baseline_samples"] == 2 and rows["host-a"]["baseline_sessions"] == 2
    edit_capture(c, "session_metrics", [row(CANDIDATE, "host-b", 60, "s2")])
    rows = {r["group"]["instance"]: r for r in compare(b, c, config)["metrics"]}
    assert rows["host-a"]["candidate_mean"] is None


def test_unit_mismatch_refused(pair):
    b, c, config = pair
    config["metrics"][0].update(
        table="session_metrics",
        value_field="measurement",
        unit="%",
        match={"displayName": "CPU"},
        group_by=["instance", "fieldName", "unit"],
    )
    edit_capture(
        b,
        "session_metrics",
        [{"testRunId": BASE, "displayName": "CPU", "unit": "bytes", "measurement": 2}],
    )
    with pytest.raises(ToolkitError, match="unit"):
        compare(b, c, config)


def test_absent_execution_is_not_success(pair):
    b, c, config = pair
    edit_capture(c, "executions", [])
    coverage = compare(b, c, config)["coverage"][1]
    assert coverage["executions"] == 0 and coverage["sessions_without_executions"] == 1


def test_hash_tampering_detected(pair):
    b, _, _ = pair
    (b / "normalized" / "measurements.json").write_text("[]")
    with pytest.raises(ToolkitError, match="hash mismatch"):
        verify_capture(b)


def test_dedup_is_full_identity_not_measurement_id():
    rows = [
        {"measurementId": "timer", "timestamp": "a", "duration": 1},
        {"measurementId": "timer", "timestamp": "b", "duration": 2},
    ]
    assert unique(rows + rows) == rows


def test_time_boundaries_original_and_utc():
    assert utc("2026-01-01T12:00:00-08:00") == "2026-01-01T20:00:00Z"
    with pytest.raises(ToolkitError):
        utc("2026-01-01T12:00:00")
    row = normalize({"timestamp": "2026-01-01T12:00:00-08:00"}, "capture")
    assert row["timestamp"].endswith("-08:00") and row["timestamp_utc"].endswith("Z")
    assert rolling(2, datetime(2026, 1, 1, 20, tzinfo=UTC)) == (
        "2026-01-01T18:00:00Z",
        "2026-01-01T20:00:00Z",
    )
    with pytest.raises(ToolkitError):
        Selection("ContinuousTest", [BASE]).validate()
    with pytest.raises(ToolkitError):
        Selection(
            "ContinuousTest", [BASE], "2026-01-01T20:00:00Z", "2026-01-01T19:00:00Z"
        ).validate()


def mock_capture(req):
    path = req.url.path
    if path.endswith("system/version") or path.endswith("system/eux-version"):
        return httpx.Response(200, json={"version": "synthetic"})
    if path.endswith("/test-runs/" + BASE):
        return httpx.Response(
            200,
            json={
                "type": "ApplicationTest",
                "id": BASE,
                "state": "completed",
                "finished": "2026-09-01T11:00:00Z",
                "result": "failed",
            },
        )
    offset = int(req.url.params.get("offset", 0))
    if path.endswith("user-sessions"):
        rows = [{"id": SESSION, "testRunId": BASE, "loginState": "failed"}]
    elif path.endswith("app-executions"):
        rows = [
            {
                "id": EXECUTION,
                "testRunId": BASE,
                "userSessionId": SESSION,
                "state": "endedWithErrors",
                "applicationId": APP,
            }
        ]
    elif path.endswith("measurements"):
        rows = [
            {
                "testRunId": BASE,
                "measurementId": "timer",
                "duration": 0,
                "timestamp": "2026-09-01T10:00:00Z",
            }
        ]
    else:
        rows = []
    return httpx.Response(200, json={"items": rows, "offset": offset, "totalCount": len(rows)})


def test_application_capture_failure_events_no_eux(tmp_path):
    paths = []

    def respond(req):
        paths.append(req.url.path)
        return mock_capture(req)

    with Client(
        Profile("test", "https://appliance.example.com"),
        "fake",
        transport=httpx.MockTransport(respond),
    ) as client:
        manifest = capture(client, Selection("ApplicationTest", [BASE]), tmp_path)
    assert manifest["status"] == "complete"
    assert load_table(tmp_path, "runs")[0]["result"] == "failed"
    assert load_table(tmp_path, "sessions")[0]["loginState"] == "failed"
    assert not any(p.endswith("eux-results") for p in paths)
    assert verify_capture(tmp_path)["table_counts"]["eux"] == 0


def test_capture_later_page_failure_retains_raw_partial(tmp_path):
    def respond(req):
        if req.url.path.endswith("measurements"):
            if req.url.params["offset"] == "0":
                return httpx.Response(
                    200, json={"items": [{"measurementId": "one"}], "offset": 0, "totalCount": 2}
                )
            return httpx.Response(403)
        return mock_capture(req)

    with Client(
        Profile("test", "https://appliance.example.com"),
        "fake",
        transport=httpx.MockTransport(respond),
        page_size=1,
    ) as client:
        with pytest.raises(ToolkitError, match="incomplete"):
            capture(client, Selection("ApplicationTest", [BASE]), tmp_path)
    manifest = verify_capture(tmp_path)
    assert manifest["status"] == "partial"
    assert any(e["status"] == "partial" and e["count"] == 1 for e in manifest["endpoints"])
    assert any("one" in p.read_text() for p in (tmp_path / "raw").glob("*.json"))
