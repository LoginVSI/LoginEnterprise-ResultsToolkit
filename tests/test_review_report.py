"""Synthetic source arithmetic and presentation semantics, no Desktop claim."""

import copy
import json
from fractions import Fraction

import pytest

from le_results.compare import compare
from le_results.errors import ToolkitError
from le_results.evidence import TABLES, finalize, load_table, verify_capture, write_json
from le_results.report import build_report
from le_results.review_report import fmt, lit, validate_review
from le_results.synthetic import demo

CONFIG = {
    "schema_version": "report/1",
    "title": "SYNTHETIC application review",
    "layout": "review",
    "overview_table": True,
    "visuals": ["comparison_table", "change_chart", "coverage_table", "source_table"],
}


def example(tmp_path):
    demo(tmp_path / "sample", "windows-review")
    config = json.loads((tmp_path / "sample/compare.json").read_text())
    return compare(tmp_path / "sample/baseline", tmp_path / "sample/candidate", config)


def test_three_actions_reconcile_independent_raw_arithmetic_and_absent_timing(tmp_path):
    result = example(tmp_path)
    raw = [
        json.loads((tmp_path / "sample" / side / "raw/synthetic.json").read_text())
        for side in ("baseline", "candidate")
    ]
    for row, definition in zip(result["metrics"], result["configuration"]["metrics"], strict=True):
        values = [
            [
                r["duration"]
                for r in side["measurements"]
                if r["applicationId"] == definition["match"]["applicationId"]
            ]
            for side in raw
        ]
        means = [sum(map(Fraction, numbers)) / len(numbers) for numbers in values]
        assert [row["baseline_mean"], row["candidate_mean"]] == list(map(float, means))
        assert row["absolute_change"] == float(means[1] - means[0])
        assert row["relative_change_percent"] == float((means[1] - means[0]) / means[0] * 100)
    assert [r["relative_change_percent"] for r in result["metrics"]] == [-20, 0, 25]
    assert [r["candidate_samples"] for r in result["metrics"]] == [3, 3, 2]
    assert all(type(r["duration"]) is int for side in raw for r in side["measurements"])
    failed = next(e for e in raw[1]["executions"] if e["state"] == "endedWithErrors")
    assert not any(m["appExecutionId"] == failed["id"] for m in raw[1]["measurements"])
    assert result["coverage"][1]["executions_without_measurements"] == 1
    assert result["coverage"][1]["successful_executions"] == 8
    assert result["coverage"][1]["execution_failures"] == 1


def test_review_and_refinement_bind_same_numeric_data_and_supported_local_model(tmp_path):
    result = example(tmp_path)
    build_report(result, tmp_path / "report", CONFIG)
    build_report(result, tmp_path / "refined", {**CONFIG, "overview_table": False})
    for name in ("Comparison", "Coverage", "ReviewTiming", "ReviewCoverage", "ReviewCards"):
        assert (tmp_path / f"report/data/{name}.json").read_bytes() == (
            tmp_path / f"refined/data/{name}.json"
        ).read_bytes()
    model = json.loads((tmp_path / "report/Results.SemanticModel/model.bim").read_text())
    tables = {table["name"]: table for table in model["model"]["tables"]}
    for path in (tmp_path / "report/Results.Report").rglob("visual.json"):
        visual = json.loads(path.read_text())["visual"]
        for role in visual.get("query", {}).get("queryState", {}).values():
            for projection in role["projections"]:
                kind, field = next(iter(projection["field"].items()))
                table = tables[field["Expression"]["SourceRef"]["Entity"]]
                assert field["Property"] in {
                    r["name"] for r in table["measures" if kind == "Measure" else "columns"]
                }
    for table in tables.values():
        expression = "\n".join(table["partitions"][0]["source"]["expression"])
        assert "File.Contents" in expression and "Web.Contents" not in expression
    for page in (tmp_path / "report/Results.Report/definition/pages").glob("*/page.json"):
        value = json.loads(page.read_text())
        assert (value["width"], value["height"]) == (1280, 720)
    text = (tmp_path / "refined/report.html").read_text(encoding="utf-8")
    assert "SYNTHETIC DEMONSTRATION" in text and "No rollout verdict" in text
    assert "<pre>" not in text and "<script" not in text and "<svg " in text
    assert 'x1="325"' in text and "+25%" in text
    assert not (
        tmp_path / "refined/Results.Report/definition/pages/comparison/visuals/samples"
    ).exists()


def test_review_legacy_coverage_and_tampering_are_distinct(tmp_path):
    result = example(tmp_path)
    legacy = copy.deepcopy(result)
    for side in legacy["coverage"]:
        side.pop("successful_executions")
        side.pop("executions_without_measurements")
    build_report(legacy, tmp_path / "legacy")
    with pytest.raises(ToolkitError, match="Rebuild this comparison"):
        build_report(legacy, tmp_path / "review", CONFIG)
    assert not (tmp_path / "review").exists()
    bad = copy.deepcopy(result)
    bad["coverage"][1]["executions_without_measurements"] = 0
    with pytest.raises(ToolkitError, match="differs"):
        build_report(bad, tmp_path / "tampered", CONFIG)


def test_review_rejects_mixed_units_before_writing(tmp_path):
    result = example(tmp_path)
    config = result["configuration"]
    config["metrics"][0]["unit"] = "seconds"
    changed = compare(tmp_path / "sample/baseline", tmp_path / "sample/candidate", config)
    with pytest.raises(ToolkitError, match="one shared source unit"):
        build_report(changed, tmp_path / "bad", CONFIG)
    assert not (tmp_path / "bad").exists()


def test_unmatched_review_mean_remains_null_and_renders_unavailable(tmp_path):
    result = example(tmp_path)
    config = result["configuration"]
    config["metrics"] = [config["metrics"][0]]
    config["metrics"][0]["match"]["measurementId"] = "not-observed"
    missing = compare(tmp_path / "sample/baseline", tmp_path / "sample/candidate", config)
    build_report(missing, tmp_path / "missing", CONFIG)
    data = json.loads((tmp_path / "missing/data/ReviewTiming.json").read_text())
    assert data[0]["Baseline mean"] is None and data[0]["Change percent"] is None
    assert data[0]["Baseline n"] == 0
    assert "Unavailable" in (tmp_path / "missing/report.html").read_text()


def rewrite_source(directory, mutate):
    manifest = verify_capture(directory)
    tables = {name: load_table(directory, name) for name in TABLES}
    mutate(tables)
    write_json(directory / "raw/synthetic.json", tables)
    finalize(directory, manifest, tables)


def test_unlinked_timing_means_unknown_absence_not_all_executions_missing(tmp_path):
    result = example(tmp_path)

    def unlink(tables):
        tables["measurements"][0]["appExecutionId"] = None

    rewrite_source(tmp_path / "sample/candidate", unlink)
    result = compare(
        tmp_path / "sample/baseline", tmp_path / "sample/candidate", result["configuration"]
    )
    assert result["coverage"][1]["executions_without_measurements"] is None
    with pytest.raises(ToolkitError, match="resolved timing links"):
        build_report(result, tmp_path / "unknown", CONFIG)
    assert not (tmp_path / "unknown").exists()


def test_review_refuses_partial_and_unknown_execution_states(tmp_path):
    result = example(tmp_path)
    result["coverage"][0]["completeness"] = "partial"
    with pytest.raises(ToolkitError, match="complete acquisition"):
        validate_review(result, CONFIG)
    result["coverage"][0]["completeness"] = "complete"
    result["coverage"][0]["execution_state_unknown"] = 1
    with pytest.raises(ToolkitError, match="known execution states"):
        validate_review(result, CONFIG)


def test_baseline_failure_warning_escaping_and_native_warning_binding(tmp_path):
    result = example(tmp_path)

    def fail(tables):
        tables["executions"][0]["state"] = "endedWithErrors"

    rewrite_source(tmp_path / "sample/baseline", fail)
    result = compare(
        tmp_path / "sample/baseline", tmp_path / "sample/candidate", result["configuration"]
    )
    build_report(result, tmp_path / "both", {**CONFIG, "title": "Engineer's <review>"})
    text = (tmp_path / "both/report.html").read_text(encoding="utf-8")
    assert "Failures B / C: 1 / 1" in text and "&lt;review&gt;" in text
    assert "Engineer's <review>" not in text
    assert lit("Engineer's")["expr"]["Literal"]["Value"] == "'Engineer''s'"
    warnings = (
        tmp_path / "both/Results.Report/definition/pages/evidence/visuals/warnings/visual.json"
    )
    assert (
        json.loads(warnings.read_text())["visual"]["query"]["queryState"]["Values"]["projections"][
            0
        ]["queryRef"]
        == "Warnings.warning"
    )


def test_review_small_values_and_layout_bounds_are_explicit(tmp_path):
    assert fmt(0, True) == "0"
    assert fmt(0.04) == "0.04" and fmt(-0.004, True) == "-0.004"
    result = example(tmp_path)
    with pytest.raises(ToolkitError, match="title up to 60"):
        validate_review(result, {**CONFIG, "title": "x" * 61})
    long_label = copy.deepcopy(result)
    long_label["metrics"][0]["metric"] = "x" * 21
    with pytest.raises(ToolkitError, match="labels up to 20"):
        validate_review(long_label, CONFIG)
    result["metrics"].append(copy.deepcopy(result["metrics"][0]))
    with pytest.raises(ToolkitError, match="1-3 actions"):
        validate_review(result, CONFIG)
