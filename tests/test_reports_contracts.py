import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from le_results.compare import compare
from le_results.contracts import PAGED, SINGLE
from le_results.errors import ToolkitError
from le_results.evidence import TABLES, finalize, load_table, verify_capture, write_json
from le_results.live_report import build_live_report
from le_results.report import build_capture_report, build_report
from le_results.synthetic import demo

ROOT = Path(__file__).resolve().parents[1]


def test_spec_versions_graph_provenance_and_read_only_adapter():
    provenance = json.loads((ROOT / "docs/api/provenance.json").read_text())
    for item in provenance:
        content = (ROOT / "docs/api" / item["file"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == item["sanitized_sha256"]
        assert json.loads(content)["info"]["version"] == item["info_version"]
        assert b"cloudapp.azure.com" not in content
    spec = json.loads((ROOT / "docs/api/openapi-v8-preview.json").read_text())

    def generic(path):
        return re.sub(r"\{[^}]+\}", "{}", path)

    for path in PAGED | SINGLE:
        matches = [
            v for p, v in spec["paths"].items() if generic(p) == generic("/v8-preview/" + path)
        ]
        assert len(matches) == 1 and "get" in matches[0]
        if path in PAGED:
            names = {p["name"] for p in matches[0]["get"]["parameters"]}
            assert {"count", "offset", "includeTotalCount"}.issubset(names)
    assert "unit" not in spec["components"]["schemas"]["Measurement"]["properties"]
    assert {"instance", "fieldName", "unit", "userSessionKey"}.issubset(
        spec["components"]["schemas"]["UserSessionMetricResult"]["properties"]
    )
    assert (
        "testConfigurationSnapshot"
        in spec["components"]["schemas"]["LoadTestRun"]["allOf"][1]["properties"]
    )


def check_references(directory):
    model = json.loads((directory / "Results.SemanticModel/model.bim").read_text())
    tables = {t["name"]: t for t in model["model"]["tables"]}
    for file in directory.glob("Results.Report/definition/pages/*/visuals/*/visual.json"):
        visual = json.loads(file.read_text())
        for slot in visual["visual"]["query"]["queryState"].values():
            for projection in slot["projections"]:
                kind, ref = next(iter(projection["field"].items()))
                table = tables[ref["Expression"]["SourceRef"]["Entity"]]
                assert ref["Property"] in {
                    f["name"] for f in table["columns" if kind == "Column" else "measures"]
                }
    for relation in model["model"]["relationships"]:
        for side in ("from", "to"):
            table = tables[relation[side + "Table"]]
            assert relation[side + "Column"] in {c["name"] for c in table["columns"]}
        to_rows = json.loads((directory / "data" / (relation["toTable"] + ".json")).read_text())
        keys = [r[relation["toColumn"]] for r in to_rows]
        assert len(keys) == len(set(keys))
    return model


def test_snapshot_bundle_models_and_no_appliance_queries(tmp_path):
    source = tmp_path / "source"
    demo(source)
    result = compare(
        source / "baseline", source / "candidate", json.loads((source / "compare.json").read_text())
    )
    report = tmp_path / "report"
    build_report(result, report)
    model = check_references(report)
    assert verify_capture(report / "evidence/baseline")["status"] == "complete"
    assert len(load_table(report / "evidence/candidate", "measurements")) == 3
    for table in model["model"]["tables"]:
        query = "\n".join(table["partitions"][0]["source"]["expression"])
        assert "File.Contents" in query and "Web.Contents" not in query
    comp = next(t for t in model["model"]["tables"] if t["name"] == "Comparison")
    assert next(c for c in comp["columns"] if c["name"] == "baseline_mean")["dataType"] == "double"


def test_finite_capture_report_retains_sources_without_inventing_comparison(tmp_path):
    demo(tmp_path / "source")
    target = tmp_path / "finite"
    build_capture_report(tmp_path / "source/candidate", target, "Finite evidence")
    check_references(target)
    assert verify_capture(target / "evidence/selected")["status"] == "complete"
    result = json.loads((target / "comparison.json").read_text())
    assert result["schema_version"] == "capture-report/1"
    assert result["metrics"] == []
    assert result["coverage"][0]["execution_failures"] == 1
    assert "compared with" not in (target / "report.html").read_text()
    assert "Endpoint outcomes" in (target / "report.html").read_text()


def test_finite_resource_rows_remain_numeric_and_keep_unit_instance_identity(tmp_path):
    demo(tmp_path / "source")
    capture = tmp_path / "source/candidate"
    manifest = verify_capture(capture)
    tables = {name: load_table(capture, name) for name in TABLES}
    tables["session_metrics"] = [
        {
            "timestamp": "2026-09-01T10:00:00Z",
            "testRunId": manifest["selection"]["ids"][0],
            "measurement": 0,
            "displayName": "Synthetic CPU",
            "fieldName": "counter",
            "unit": "%",
            "instance": "_Total",
            "userSessionKey": tables["sessions"][0]["id"],
        }
    ]
    write_json(capture / "raw/resource-fixture.json", tables["session_metrics"])
    finalize(capture, manifest, tables)
    target = tmp_path / "resources"
    build_capture_report(capture, target)
    model = check_references(target)
    resources = next(t for t in model["model"]["tables"] if t["name"] == "Source_session_metrics")
    assert (
        next(c for c in resources["columns"] if c["name"] == "measurement")["dataType"] == "double"
    )
    assert "resource_table" in json.loads((target / "report-spec.json").read_text())["visuals"]
    content = (target / "report.html").read_text()
    assert "Retained resource observations" in content and "Synthetic CPU" in content
    assert "_Total" in content and "<td>0</td>" in content

    class Tables(HTMLParser):
        def __init__(self):
            super().__init__()
            self.depth = 0
            self.heading = ""
            self.read_heading = False
            self.tables = []

        def handle_starttag(self, tag, attrs):
            if tag == "h2":
                self.heading = ""
                self.read_heading = True
            if tag == "table":
                assert self.depth == 0, "Nested source tables"
                self.depth += 1
                self.tables.append([self.heading, 0])
            if tag in ("tr", "td", "th"):
                assert self.depth == 1, "Source cells outside table"
                if tag == "tr":
                    self.tables[-1][1] += 1

        def handle_endtag(self, tag):
            if tag == "h2":
                self.read_heading = False
            if tag == "table":
                self.depth -= 1

        def handle_data(self, data):
            if self.read_heading:
                self.heading += data

    parsed = Tables()
    parsed.feed(content)
    assert parsed.depth == 0
    assert parsed.tables == [
        ["Retained timer observations", 4],
        ["Retained resource observations", 2],
    ]
    assert "Baseline mean" not in content


@pytest.mark.parametrize(
    "filename", ["live-report.json", "continuous-report.json", "continuous-selected-report.json"]
)
def test_live_model_scoped_credential_parameters_and_reference_integrity(tmp_path, filename):
    config = json.loads((ROOT / "examples" / filename).read_text())
    build_live_report(config, tmp_path)
    model = check_references(tmp_path)
    assert len(model["model"]["tables"]) == 1  # One evaluation freezes the refresh window.
    query = (tmp_path / "Acquisition.pq").read_text()
    assert "ResultsToolkit.Rows" in query and "Bearer" not in query and "Token" not in query
    assert {"timestamp", "timestamp_utc", "source_json", "instance"}.issubset(
        {c["name"] for c in model["model"]["tables"][0]["columns"]}
    )


def test_live_config_secret_or_status_rejected(tmp_path):
    config = json.loads((ROOT / "examples/live-report.json").read_text())
    config["api_token"] = "fake-do-not-persist"
    with pytest.raises(ToolkitError, match="Credentials"):
        build_live_report(config, tmp_path)
    del config["api_token"]
    config["metrics"][0]["semantics"] = "status"
    with pytest.raises(ToolkitError, match="semantics"):
        build_live_report(config, tmp_path)


def test_selected_live_source_has_no_comparison_measures(tmp_path):
    config = json.loads((ROOT / "examples/continuous-selected-report.json").read_text())
    build_live_report(config, tmp_path / "selected")
    model = check_references(tmp_path / "selected")
    measures = {r["name"] for r in model["model"]["tables"][0]["measures"]}
    assert {"Observed Mean", "Samples", "Missing", "Execution Failures"}.issubset(measures)
    assert not any("Change" in r or "Baseline" in r or "Candidate" in r for r in measures)
    query = (tmp_path / "selected/Acquisition.pq").read_text()
    assert "acquisition/2" in query and "selected" in query and "baseline" not in query
    config["selected"]["ids"].append("22222222-2222-4222-8222-222222222222")
    with pytest.raises(ToolkitError, match="exactly one"):
        build_live_report(config, tmp_path / "pooled")
    config["selected"]["ids"].pop()
    config["baseline"] = config["selected"]
    with pytest.raises(ToolkitError, match="comparison roles"):
        build_live_report(config, tmp_path / "invalid")


def test_synthetic_states_are_declared_in_contract(tmp_path):
    demo(tmp_path)
    spec = json.loads((ROOT / "docs/api/openapi-v8-preview.json").read_text())
    schemas = spec["components"]["schemas"]
    run = load_table(tmp_path / "baseline", "runs")[0]
    assert run["euxScore"]["state"] in schemas["EuxState"]["enum"]
    assert run["vsiMax"]["state"] in schemas["VsiMaxState"]["enum"]
    assert (
        load_table(tmp_path / "baseline", "sessions")[0]["loginState"]
        in schemas["LoginState"]["enum"]
    )
    assert set(TABLES) == set(verify_capture(tmp_path / "baseline")["table_counts"])


def test_source_mixed_numeric_column_fails_before_claiming_report_acceptance(tmp_path):
    demo(tmp_path / "source")
    capture = tmp_path / "source/candidate"
    manifest = verify_capture(capture)
    tables = {name: load_table(capture, name) for name in TABLES}
    tables["measurements"][0]["duration"] = "unavailable sentinel"
    finalize(capture, manifest, tables)
    with pytest.raises(ToolkitError, match="mixed numeric"):
        build_capture_report(capture, tmp_path / "report")
    assert not (tmp_path / "report").exists()


def test_unresolved_timer_reference_is_visible_without_inventing_execution(tmp_path):
    demo(tmp_path / "source")
    capture = tmp_path / "source/candidate"
    manifest = verify_capture(capture)
    tables = {name: load_table(capture, name) for name in TABLES}
    tables["measurements"][0]["appExecutionId"] = "77777777-7777-4777-8777-777777777777"
    finalize(capture, manifest, tables)
    result = verify_capture(capture)
    assert result["relationship_coverage"]["timer_execution_links"] == {
        "resolved": 2,
        "nullable": 0,
        "unresolved": 1,
        "unresolved_ids": ["77777777-7777-4777-8777-777777777777"],
    }
    assert result["status"] == "complete"  # Acquisition is distinct from linkage coverage.
    assert any("absent from the captured" in warning for warning in result["warnings"])
    assert len(load_table(capture, "executions")) == 1


def test_unhashable_timer_reference_remains_unresolved_evidence(tmp_path):
    demo(tmp_path / "source")
    capture = tmp_path / "source/candidate"
    manifest = verify_capture(capture)
    tables = {name: load_table(capture, name) for name in TABLES}
    tables["measurements"][0]["appExecutionId"] = {"unexpected": "object"}
    finalize(capture, manifest, tables)
    result = verify_capture(capture)
    assert result["relationship_coverage"]["timer_execution_links"]["unresolved"] == 1
    assert load_table(capture, "measurements")[0]["appExecutionId"] == {"unexpected": "object"}
