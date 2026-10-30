"""Generate a refreshable model from explicit nonsecret selection/metric definitions."""

import json
from pathlib import Path
from typing import Any

from .errors import ToolkitError
from .evidence import write_json
from .metrics import validate_metrics
from .profiles import canonical_origin
from .report import SCHEMA, build_report, m_string
from .selection import Selection, rolling


def build_live_report(config: dict[str, Any], directory: Path) -> None:
    single = config.get("schema_version") == "live-selection/1"
    if config.get("schema_version") not in ("live-report/1", "live-selection/1"):
        raise ToolkitError("Expected live-report/1 or live-selection/1 configuration.")
    roles = ("selected",) if single else ("baseline", "candidate")
    if single and ("baseline" in config or "candidate" in config):
        raise ToolkitError("A selected-source report cannot include comparison roles.")
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
    for side in roles:
        if not config[side].get("label"):
            raise ToolkitError("Explicit scenario labels are required.")
        Selection(kind, config[side]["ids"], start, end).validate()
    if single and len(config["selected"]["ids"]) != 1:
        raise ToolkitError(
            "A selected-source live report requires exactly one result ID; no pooled mean."
        )
    if not single and config["baseline"]["label"] == config["candidate"]["label"]:
        raise ToolkitError("Scenario labels must differ.")
    if not single and set(config["baseline"]["ids"]) & set(config["candidate"]["ids"]):
        raise ToolkitError("Baseline and candidate must use different IDs.")
    if sum(len(config[role]["ids"]) for role in roles) > 4:
        raise ToolkitError("The preview live connector permits at most four results per refresh.")
    metrics = validate_metrics(config.get("metrics"))
    native_metrics = [m for m in metrics if m.get("table") == "native_scores"]
    metrics = [m for m in metrics if m.get("table") != "native_scores"]
    if native_metrics:
        if kind != "LoadTest":
            raise ToolkitError("Native whole-run scores apply to Load results only.")
        if any(len(config[role]["ids"]) != 1 for role in roles):
            raise ToolkitError(
                "Native whole-run scores need exactly one result per side; they are never pooled."
            )
    for metric in metrics:
        if not isinstance(metric.get("name"), str) or not metric["name"].strip():
            raise ToolkitError("Every metric requires a nonempty name.")
        identities = (
            ("applicationId", "measurementId")
            if metric.get("table") == "measurements"
            else ("displayName",)
        )
        for identity in identities:
            if identity not in metric.get("match", {}) and identity not in metric.get(
                "group_by", []
            ):
                raise ToolkitError(f"Metric identity requires {identity} in match or group_by.")
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
    acquisition = {k: config[k] for k in ("test_type", *roles)}
    acquisition["metrics"] = metrics
    acquisition["schema_version"] = "acquisition/2" if single else "acquisition/1"
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
    native_acquisition = {**acquisition, "metrics": native_metrics}
    placeholder = {
        "schema_version": "live-placeholder/1",
        **{role: config[role] for role in roles},
        "test_type": kind,
        "metrics": [],
        "coverage": [],
        "warnings": [
            "Refreshable project has no acquired data until a successful Desktop refresh."
        ],
    }
    if single:
        placeholder = {
            "schema_version": "capture-report/1",
            "selected": config["selected"],
            "metrics": [],
            "coverage": [],
            "endpoint_outcomes": [],
            "warnings": [
                "Refreshable selected-source project has no acquired data until a successful Desktop refresh."
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
        _internal=True,
    )
    query = (
        "ResultsToolkit.Rows("
        + m_string(origin)
        + ", "
        + m_string(json.dumps(acquisition, ensure_ascii=True))
        + ")"
    )
    (directory / "Acquisition.pq").write_text(query + "\n", encoding="utf-8")
    native_query = (
        "ResultsToolkit.Native("
        + m_string(origin)
        + ", "
        + m_string(json.dumps(native_acquisition, ensure_ascii=True))
        + ")"
    )
    if native_metrics:
        (directory / "NativeAcquisition.pq").write_text(native_query + "\n", encoding="utf-8")
    write_json(directory / "live-report-spec.json", {**config, "origin": origin})
    columns = [
        "row_kind",
        "scenario",
        "run_id",
        "session_id",
        "execution_id",
        "deduplicated_rows",
        "observation_present",
        "availability",
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

    base_label = dax_string(config["selected" if single else "baseline"]["label"])
    candidate_label = dax_string(config["selected" if single else "candidate"]["label"])
    filter_kind = 'Results[row_kind] IN {"measurement", "session_metric"}'
    unit_guard = (
        "COUNTROWS(FILTER(ALLSELECTED(Results[unit]), NOT ISBLANK(Results[unit]))) = 1 && "
        f"CALCULATE(HASONEVALUE(Results[metric_key]), {filter_kind})"
    )
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
            "expression": 'CALCULATE(COUNTROWS(Results), Results[row_kind] = "session", Results[state] IN {"failed", "aborted", "abandoned"})',
            "formatString": "0",
        },
    ]
    if single:
        measures[:6] = [
            {
                "name": "Observed Mean",
                "expression": f"IF({unit_guard}, CALCULATE(AVERAGE(Results[value]), {filter_kind}))",
                "formatString": "0.00",
            },
            {
                "name": "Samples",
                "expression": f"CALCULATE(COUNT(Results[value]), {filter_kind})",
                "formatString": "0",
            },
            {
                "name": "Missing",
                "expression": f'CALCULATE(COUNTROWS(Results), {filter_kind}, Results[observation_present] = "true", ISBLANK(Results[value]))',
                "formatString": "0",
            },
        ]
    for side, label in () if single else (("Baseline", base_label), ("Candidate", candidate_label)):
        measures.append(
            {
                "name": side + " Missing",
                "expression": f'CALCULATE(COUNTROWS(Results), Results[scenario] = {label}, {filter_kind}, Results[observation_present] = "true", ISBLANK(Results[value]))',
                "formatString": "0",
            }
        )
    model: dict[str, Any] = {
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
    native_measures: list[dict[str, str]] = []
    if native_metrics:
        completed = 'NativeScores[state] = "completed"'

        def native_side(label: str) -> str:
            # One run per side is enforced, so a completed score has exactly one row.
            return (
                "IF(HASONEVALUE(NativeScores[result_id]) && CALCULATE(COUNTROWS(NativeScores), "
                f"NativeScores[scenario] = {label}, {completed}) = 1, "
                f"CALCULATE(MAX(NativeScores[value]), NativeScores[scenario] = {label}, {completed}))"
            )

        if single:
            native_measures = [
                {"name": "Native Score", "expression": native_side(base_label), "formatString": "0.0"}
            ]
        else:
            native_measures = [
                {
                    "name": "Baseline Native Score",
                    "expression": native_side(base_label),
                    "formatString": "0.0",
                },
                {
                    "name": "Candidate Native Score",
                    "expression": native_side(candidate_label),
                    "formatString": "0.0",
                },
                {
                    "name": "Native Change",
                    "expression": "IF(NOT ISBLANK([Baseline Native Score]) && NOT ISBLANK([Candidate Native Score]), [Candidate Native Score] - [Baseline Native Score])",
                    "formatString": "0.0",
                },
            ]
        text_columns = (
            "scenario run_id metric_name result_id result_group unit state display_value "
            "availability test_name counter run_state test_result score_grain provenance "
            "source_endpoint source_json captured_at capture_status"
        ).split()
        model["model"]["tables"].append(
            {
                "name": "NativeScores",
                "columns": [
                    {"name": n, "dataType": "string", "sourceColumn": n, "summarizeBy": "none"}
                    for n in text_columns
                ]
                + [
                    {
                        "name": "value",
                        "dataType": "double",
                        "sourceColumn": "value",
                        "summarizeBy": "none",
                    }
                ],
                "measures": native_measures,
                "partitions": [
                    {
                        "name": "NativeScores",
                        "mode": "import",
                        "source": {"type": "m", "expression": [native_query]},
                    }
                ],
            }
        )
    write_json(directory / "Results.SemanticModel" / "model.bim", model)
    page = directory / "Results.Report" / "definition" / "pages" / "comparison"

    def field(name: str, measure: bool = False, entity: str = "Results") -> dict[str, Any]:
        return {
            "field": {
                "Measure" if measure else "Column": {
                    "Expression": {"SourceRef": {"Entity": entity}},
                    "Property": name,
                }
            },
            "queryRef": entity + "." + name,
            "nativeQueryRef": name,
        }

    visuals = [
        ("unit_filter", "slicer", {"Values": {"projections": [field("unit")]}}, 0, 0, 300, 100),
        (
            "comparison_table",
            "tableEx",
            {
                "Values": {
                    "projections": [field("metric_key"), field("unit"), field("availability")]
                    + [
                        field(n, True)
                        for n in (
                            ("Observed Mean", "Samples", "Missing")
                            if single
                            else (
                                "Baseline Mean",
                                "Candidate Mean",
                                "Absolute Change",
                                "Relative Change Percent",
                                "Baseline Samples",
                                "Candidate Samples",
                                "Baseline Missing",
                                "Candidate Missing",
                            )
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
            "observation_chart" if single else "change_chart",
            "clusteredBarChart",
            {
                "Category": {"projections": [field("metric_key")]},
                "Y": {
                    "projections": [field("Observed Mean" if single else "Absolute Change", True)]
                },
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
    if native_metrics:
        native_values = [
            field(n, entity="NativeScores")
            for n in ("scenario", "metric_name", "display_value", "state", "unit")
        ] + [field(m["name"], True, "NativeScores") for m in native_measures]
        if not metrics:
            # Native-only: the timer visuals would be empty, so keep coverage and add the native table.
            visuals = [(*visuals[3][:3], 0, 450, 1260, 350)]
        visuals.append(
            ("native_table", "tableEx", {"Values": {"projections": native_values}}, 0, 810 if metrics else 0, 1260, 300 if metrics else 430)
        )
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
        "Subsequent refreshes repeat acquisition; new-data proof requires advancing source timestamps. "
        "This is not streaming. Record Desktop acceptance for this specific project and build.\n"
        + (
            "NativeScores holds the vendor's whole-run score per run from the Load overview. "
            "A change appears only when both states are completed; a VSImax above threshold is a lower bound.\n"
            if native_metrics
            else ""
        ),
        encoding="utf-8",
    )
