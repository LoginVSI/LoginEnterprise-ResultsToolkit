"""Generate a refreshable model from explicit nonsecret selection/metric definitions."""

import json
from pathlib import Path
from typing import Any

from .errors import ToolkitError
from .evidence import write_json
from .profiles import canonical_origin
from .report import SCHEMA, build_report, m_string
from .selection import Selection, rolling


def build_live_report(config: dict[str, Any], directory: Path) -> None:
    if config.get("schema_version") != "live-report/1":
        raise ToolkitError("Expected live-report/1 configuration.")
    origin = canonical_origin(config["origin"])
    kind = config["test_type"]
    start, end = config.get("start"), config.get("end")
    hours = config.get("rolling_hours")
    if hours is not None:
        if kind != "ContinuousTest" or start or end:
            raise ToolkitError(
                "Rolling windows are exclusive to Continuous, without fixed boundaries."
            )
        start, end = rolling(hours)
    for side in ("baseline", "candidate"):
        if not config[side].get("label"):
            raise ToolkitError("Explicit scenario labels are required.")
        Selection(kind, config[side]["ids"], start, end).validate()
    if config["baseline"]["label"] == config["candidate"]["label"]:
        raise ToolkitError("Scenario labels must differ.")
    if set(config["baseline"]["ids"]) & set(config["candidate"]["ids"]):
        raise ToolkitError("Baseline and candidate must use different IDs.")
    metrics = config.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        raise ToolkitError("Supply explicit metrics.")
    for metric in metrics:
        if metric.get("table") not in ("measurements", "session_metrics") or not metric.get(
            "match"
        ):
            raise ToolkitError("Metrics require exact timer or session-metric identity fields.")
        if metric.get("value_field") != (
            "duration" if metric["table"] == "measurements" else "measurement"
        ):
            raise ToolkitError("Metric value_field differs from the API contract.")
        if metric.get("semantics") not in ("duration", "resource") or not metric.get("unit"):
            raise ToolkitError(
                "Arithmetic reporting requires duration/resource semantics and an explicit unit."
            )
        if metric.get("direction") not in ("lower", "higher", "neutral"):
            raise ToolkitError("Metric direction is required.")
        if metric["table"] == "session_metrics" and not {"instance", "fieldName", "unit"}.issubset(
            metric.get("group_by", [])
        ):
            raise ToolkitError("Session metrics must group by instance, fieldName and unit.")
    # Only allowed fields are serialized into M. Never accept a token parameter.
    acquisition = {k: config[k] for k in ("test_type", "baseline", "candidate", "metrics")}
    acquisition["schema_version"] = "acquisition/1"
    acquisition.update({k: config[k] for k in ("start", "end", "rolling_hours") if k in config})

    def reject_secrets(value: Any) -> None:
        if isinstance(value, dict):
            if any(
                any(s in k.lower() for s in ("token", "password", "authorization", "secret"))
                for k in value
            ):
                raise ToolkitError("Credentials must not appear in report configuration.")
            for item in value.values():
                reject_secrets(item)
        elif isinstance(value, list):
            for item in value:
                reject_secrets(item)

    reject_secrets(config)
    placeholder = {
        "schema_version": "comparison-result/1",
        "baseline": config["baseline"],
        "candidate": config["candidate"],
        "test_type": kind,
        "metrics": [],
        "coverage": [],
        "warnings": [
            "Refreshable project has no acquired data until a successful Desktop refresh."
        ],
    }
    build_report(
        placeholder,
        directory,
        {
            "schema_version": "report/1",
            "title": config.get("title", "Refreshable results"),
            "visuals": [],
        },
    )
    query = (
        "ResultsToolkit.Rows("
        + m_string(origin)
        + ", "
        + m_string(json.dumps(acquisition, ensure_ascii=True))
        + ")"
    )
    (directory / "Acquisition.pq").write_text(query + "\n", encoding="utf-8")
    write_json(directory / "live-report-spec.json", {**config, "origin": origin})
    columns = [
        "row_kind",
        "scenario",
        "run_id",
        "session_id",
        "execution_id",
        "metric_key",
        "metric_name",
        "unit",
        "instance",
        "field_name",
        "state",
        "timestamp",
        "timestamp_utc",
        "source_json",
        "configuration_scope",
        "window_start",
        "window_end",
        "captured_at",
        "capture_status",
    ]

    def dax_string(value: str) -> str:
        return '"' + value.replace('"', '""') + '"'

    base_label = dax_string(config["baseline"]["label"])
    candidate_label = dax_string(config["candidate"]["label"])
    filter_kind = 'Results[row_kind] IN {"measurement", "session_metric"}'
    unit_guard = "COUNTROWS(FILTER(ALLSELECTED(Results[unit]), NOT ISBLANK(Results[unit]))) = 1 && HASONEVALUE(Results[metric_key])"
    measures = [
        {
            "name": "Baseline Mean",
            "expression": f"IF({unit_guard}, CALCULATE(AVERAGE(Results[value]), Results[scenario] = {base_label}, {filter_kind}))",
            "formatString": "0.00",
        },
        {
            "name": "Candidate Mean",
            "expression": f"IF({unit_guard}, CALCULATE(AVERAGE(Results[value]), Results[scenario] = {candidate_label}, {filter_kind}))",
            "formatString": "0.00",
        },
        {
            "name": "Absolute Change",
            "expression": "IF(NOT ISBLANK([Baseline Mean]) && NOT ISBLANK([Candidate Mean]), [Candidate Mean] - [Baseline Mean])",
            "formatString": "0.00",
        },
        {
            "name": "Relative Change Percent",
            "expression": "IF(NOT ISBLANK([Absolute Change]) && [Baseline Mean] <> 0, DIVIDE([Absolute Change], ABS([Baseline Mean])) * 100)",
            "formatString": "0.00",
        },
        {
            "name": "Baseline Samples",
            "expression": f"CALCULATE(COUNT(Results[value]), Results[scenario] = {base_label}, {filter_kind})",
            "formatString": "0",
        },
        {
            "name": "Candidate Samples",
            "expression": f"CALCULATE(COUNT(Results[value]), Results[scenario] = {candidate_label}, {filter_kind})",
            "formatString": "0",
        },
        {
            "name": "Executions",
            "expression": 'CALCULATE(COUNTROWS(Results), Results[row_kind] = "execution")',
            "formatString": "0",
        },
        {
            "name": "Execution Failures",
            "expression": 'CALCULATE(COUNTROWS(Results), Results[row_kind] = "execution", Results[state] = "endedWithErrors")',
            "formatString": "0",
        },
        {
            "name": "Sessions",
            "expression": 'CALCULATE(COUNTROWS(Results), Results[row_kind] = "session")',
            "formatString": "0",
        },
        {
            "name": "Failed Logons",
            "expression": 'CALCULATE(COUNTROWS(Results), Results[row_kind] = "session", Results[state] = "failed")',
            "formatString": "0",
        },
    ]
    model = {
        "name": "ResultsToolkit",
        "compatibilityLevel": 1600,
        "model": {
            "culture": "en-US",
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "relationships": [],
            "tables": [
                {
                    "name": "Results",
                    "columns": [
                        {
                            "name": name,
                            "dataType": "string",
                            "sourceColumn": name,
                            "summarizeBy": "none",
                        }
                        for name in columns
                    ]
                    + [
                        {
                            "name": "value",
                            "dataType": "double",
                            "sourceColumn": "value",
                            "summarizeBy": "none",
                        }
                    ],
                    "measures": measures,
                    "partitions": [
                        {
                            "name": "Results",
                            "mode": "import",
                            "source": {"type": "m", "expression": [query]},
                        }
                    ],
                }
            ],
        },
    }
    write_json(directory / "Results.SemanticModel" / "model.bim", model)
    page = directory / "Results.Report" / "definition" / "pages" / "comparison"

    def field(name: str, measure: bool = False) -> dict[str, Any]:
        return {
            "field": {
                "Measure" if measure else "Column": {
                    "Expression": {"SourceRef": {"Entity": "Results"}},
                    "Property": name,
                }
            },
            "queryRef": "Results." + name,
            "nativeQueryRef": name,
        }

    visuals = [
        ("unit_filter", "slicer", {"Values": {"projections": [field("unit")]}}, 0, 0, 300, 100),
        (
            "comparison_table",
            "tableEx",
            {
                "Values": {
                    "projections": [field("metric_key"), field("unit")]
                    + [
                        field(n, True)
                        for n in (
                            "Baseline Mean",
                            "Candidate Mean",
                            "Absolute Change",
                            "Relative Change Percent",
                            "Baseline Samples",
                            "Candidate Samples",
                        )
                    ]
                }
            },
            0,
            110,
            1260,
            320,
        ),
        (
            "change_chart",
            "clusteredBarChart",
            {
                "Category": {"projections": [field("metric_key")]},
                "Y": {"projections": [field("Absolute Change", True)]},
            },
            0,
            450,
            700,
            350,
        ),
        (
            "coverage_table",
            "tableEx",
            {
                "Values": {
                    "projections": [field("scenario")]
                    + [
                        field(n, True)
                        for n in ("Sessions", "Executions", "Execution Failures", "Failed Logons")
                    ]
                }
            },
            710,
            450,
            550,
            350,
        ),
    ]
    for z, (name, visual_type, query_state, x, y, width, height) in enumerate(visuals):
        write_json(
            page / "visuals" / name / "visual.json",
            {
                "$schema": SCHEMA + "report/definition/visualContainer/2.1.0/schema.json",
                "name": name,
                "position": {
                    "x": x,
                    "y": y,
                    "z": z,
                    "tabOrder": z,
                    "width": width,
                    "height": height,
                },
                "visual": {"visualType": visual_type, "query": {"queryState": query_state}},
            },
        )
    (directory / "OPEN-IN-DESKTOP.txt").write_text(
        "Install the independently authored ResultsToolkit.mez connector following docs/powerbi.md. "
        "Open Results.pbip; enroll the token once in Power Query's Key credential dialog for this origin. "
        "Refresh and reconcile with a Python capture for the identical IDs/window. "
        "A failed refresh is an error, not successful empty data. Rolling windows resolve once per query evaluation. "
        "Subsequent refreshes acquire new data. This is not streaming. Desktop execution is pending.\n",
        encoding="utf-8",
    )
