import json
from pathlib import Path

import httpx
import pytest

from le_results.client import Client
from le_results.compare import compare
from le_results.errors import ToolkitError
from le_results.evidence import TABLES, capture, finalize, load_table, verify_capture
from le_results.native import flatten_overview
from le_results.profiles import Profile
from le_results.report import build_report
from le_results.selection import Selection
from le_results.synthetic import BASE, CANDIDATE, demo


def overview(run_id, score=7.5, eux_state="completed", vsi=None, vsi_state="belowSessionCount"):
    return {
        "results": [
            {
                "testRunId": run_id,
                "testName": "Synthetic",
                "counter": 1,
                "isBase": True,
                "state": "completed",
                "testResult": "completed",
                "results": {
                    "performance": {
                        "euxState": eux_state,
                        "vsiMaxState": vsi_state,
                        "results": [
                            {"resultId": "eux_score", "value": score, "differenceFromBase": None},
                            {"resultId": "eux_baseline", "value": 8.0},
                            {"resultId": "eux_steady_state", "value": None},
                            {"resultId": "vsi_max", "value": vsi},
                        ],
                    }
                },
            }
        ]
    }


def seed(directory: Path, run_id: str, response):
    manifest = verify_capture(directory)
    tables = {k: load_table(directory, k) for k in TABLES}
    tables["native_scores"] = flatten_overview(response, run_id, "synthetic")
    finalize(directory, manifest, tables)


@pytest.fixture
def pair(tmp_path):
    demo(tmp_path)
    config = json.loads((tmp_path / "compare.json").read_text())
    config["metrics"] = [
        {
            "name": "Native EUX score",
            "table": "native_scores",
            "value_field": "value",
            "match": {"resultId": "eux_score"},
            "unit": "score 0-10",
            "semantics": "native_score",
            "direction": "higher",
        }
    ]
    return tmp_path / "baseline", tmp_path / "candidate", config


def test_flatten_preserves_ids_states_and_null():
    rows = flatten_overview(overview(BASE), BASE, "c")
    by_id = {r["resultId"]: r for r in rows}
    assert set(by_id) == {"eux_score", "eux_baseline", "eux_steady_state", "vsi_max"}
    assert by_id["eux_score"]["state"] == "completed"
    assert by_id["vsi_max"]["state"] == "belowSessionCount"
    assert by_id["eux_steady_state"]["value"] is None  # never zero
    assert all(r["score_grain"] == "native_whole_run" for r in rows)


def test_flatten_rejects_other_run_identity():
    with pytest.raises(ToolkitError):
        flatten_overview(overview(CANDIDATE), BASE, "c")
    with pytest.raises(ToolkitError):
        flatten_overview({"results": []}, BASE, "c")


def test_native_comparison_uses_vendor_values_not_means(pair):
    b, c, config = pair
    seed(b, BASE, overview(BASE, score=7.0))
    seed(c, CANDIDATE, overview(CANDIDATE, score=8.5))
    row = compare(b, c, config)["metrics"][0]
    assert row["grain"] == "native_whole_run"
    assert (row["baseline_mean"], row["candidate_mean"]) == (7.0, 8.5)
    assert row["absolute_change"] == pytest.approx(1.5)
    assert row["interpretation"] == "improved"
    assert row["baseline_state"] == row["candidate_state"] == "completed"


def test_native_state_not_completed_blocks_delta_but_keeps_values(pair):
    b, c, config = pair
    seed(b, BASE, overview(BASE, score=7.0))
    seed(c, CANDIDATE, overview(CANDIDATE, score=8.5, eux_state="inProgress"))
    row = compare(b, c, config)["metrics"][0]
    assert row["absolute_change"] is None and row["candidate_mean"] == 8.5
    assert "inProgress" in row["warning"]


def test_missing_native_result_is_unavailable_not_zero(pair):
    b, c, config = pair
    seed(b, BASE, overview(BASE, score=None, eux_state="unavailable"))
    seed(c, CANDIDATE, overview(CANDIDATE))
    row = compare(b, c, config)["metrics"][0]
    assert row["baseline_mean"] is None and row["baseline_missing"] == 1
    assert row["absolute_change"] is None


def test_capture_without_overview_table_is_refused(pair):
    b, c, config = pair
    seed(b, BASE, overview(BASE))
    (c / "normalized" / "native_scores.json").unlink()
    manifest = json.loads((c / "manifest.json").read_text())
    manifest["files"].pop("normalized/native_scores.json")
    manifest["files"].pop("normalized/native_scores.csv", None)
    (c / "normalized" / "native_scores.csv").unlink(missing_ok=True)
    (c / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ToolkitError, match="predates"):
        compare(b, c, config)


def test_native_never_averages_across_runs(pair):
    b, c, config = pair
    seed(b, BASE, overview(BASE))
    seed(c, CANDIDATE, overview(CANDIDATE))
    manifest = json.loads((b / "manifest.json").read_text())
    manifest["selection"]["ids"] = [BASE, CANDIDATE]
    (b / "manifest.json").write_text(json.dumps(manifest))
    config["baseline"]["ids"] = [BASE, CANDIDATE]
    with pytest.raises(ToolkitError, match="never averaged"):
        compare(b, c, config)


@pytest.mark.parametrize(
    "patch",
    [
        {"group_by": ["testRunId"]},
        {"semantics": "duration"},
        {"match": {"resultId": "eux_score", "testRunId": BASE}},
        {"exclude_values": [0]},
        {"unit": " "},
    ],
)
def test_native_metric_definition_is_strict(pair, patch):
    b, c, config = pair
    config["metrics"][0].update(patch)
    with pytest.raises(ToolkitError):
        compare(b, c, config)


def test_snapshot_report_labels_native_grain(pair, tmp_path):
    b, c, config = pair
    seed(b, BASE, overview(BASE, score=7.0))
    seed(c, CANDIDATE, overview(CANDIDATE, score=8.5))
    comparison = compare(b, c, config)
    out = tmp_path / "report"
    build_report(
        comparison,
        out,
        {"schema_version": "report/1", "title": "t", "visuals": ["comparison_table"]},
    )
    html = next(out.glob("*.html")).read_text(encoding="utf-8")
    assert "native_whole_run" in html and "Grain" in html
    rows = json.loads((out / "data" / "Comparison.json").read_text())
    assert rows[0]["grain"] == "native_whole_run" and rows[0]["baseline_state"] == "completed"


def test_capture_retrieves_overview_for_load_run(tmp_path):
    def handler(req):
        path = req.url.path
        if path.endswith("system/version") or path.endswith("system/eux-version"):
            return httpx.Response(200, json={"version": "synthetic"})
        if path.endswith("load-test-run-overview/" + BASE):
            assert "testRunIds" not in req.url.params  # never request a cross-run comparison
            return httpx.Response(200, json=overview(BASE, score=6.25))
        if path.endswith("/test-runs/" + BASE):
            return httpx.Response(
                200,
                json={
                    "type": "LoadTest",
                    "id": BASE,
                    "state": "completed",
                    "finished": "2026-09-01T11:00:00Z",
                },
            )
        if path.endswith("eux-results"):
            return httpx.Response(200, json=[])
        offset = int(req.url.params.get("offset", 0))
        return httpx.Response(200, json={"items": [], "offset": offset, "totalCount": 0})

    client = Client(
        Profile("p", "https://appliance.example.com"),
        "synthetic-token",
        transport=httpx.MockTransport(handler),
    )
    manifest = capture(client, Selection("LoadTest", [BASE], None, None), tmp_path / "cap")
    assert manifest["status"] == "complete"
    rows = load_table(tmp_path / "cap", "native_scores")
    assert {r["resultId"]: r["value"] for r in rows}["eux_score"] == 6.25
    assert load_table(tmp_path / "cap", "eux") == []


def test_older_comparison_without_grain_still_builds(pair, tmp_path):
    b, c, _ = pair
    config = json.loads((b.parent / "compare.json").read_text())
    comparison = compare(b, c, config)
    for row in comparison["metrics"]:
        row.pop("grain")
    build_report(
        comparison,
        tmp_path / "old",
        {"schema_version": "report/1", "title": "t", "visuals": ["comparison_table"]},
    )
    rows = json.loads((tmp_path / "old" / "data" / "Comparison.json").read_text())
    assert rows[0]["grain"] == "observation_mean"


def test_vsimax_above_threshold_is_a_lower_bound_not_exact_capacity(pair, tmp_path):
    b, c, config = pair
    config["metrics"] = [
        {
            **config["metrics"][0],
            "name": "VSImax",
            "match": {"resultId": "vsi_max"},
            "unit": "sessions",
        }
    ]
    seed(b, BASE, overview(BASE, vsi=6.0, vsi_state="aboveThreshold"))
    seed(c, CANDIDATE, overview(CANDIDATE, vsi=6.0, vsi_state="aboveThreshold"))
    comparison = compare(b, c, config)
    row = comparison["metrics"][0]
    assert row["baseline_display"] == ">6" and row["candidate_display"] == ">6"
    assert row["baseline_mean"] == 6.0 and row["absolute_change"] is None  # censored: no delta
    out = tmp_path / "vsi"
    build_report(
        comparison,
        out,
        {"schema_version": "report/1", "title": "t", "visuals": ["comparison_table"]},
    )
    html = next(out.glob("*.html")).read_text(encoding="utf-8")
    assert "&gt;6" in html and "native_whole_run" in html


def test_display_keeps_source_precision_and_states():
    from le_results.native import display_value

    assert display_value("eux_score", 8.2, "completed") == "8.2"
    assert display_value("eux_score", 8.1999, "completed") == "8.1999"  # no rounding
    assert display_value("eux_score", None, "disabled") == "unavailable (disabled)"
    assert display_value("vsi_max", 6.0, "belowSessionCount") == "6 (belowSessionCount)"
    assert display_value("total_login_time", 47.2, None) == "47.2"  # no unit inferred
