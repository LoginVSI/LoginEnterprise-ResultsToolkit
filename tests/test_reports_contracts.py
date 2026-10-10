import hashlib
import json
import re
from pathlib import Path

import pytest

from le_results.compare import compare
from le_results.contracts import PAGED, SINGLE
from le_results.errors import ToolkitError
from le_results.evidence import TABLES, load_table, verify_capture
from le_results.live_report import build_live_report
from le_results.report import build_report
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


@pytest.mark.parametrize("filename", ["live-report.json", "continuous-report.json"])
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
