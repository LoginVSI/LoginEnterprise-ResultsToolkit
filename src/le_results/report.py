"""Editable, local-file Power BI project plus a portable HTML evidence report."""

import html
import json
import shutil
from pathlib import Path
from typing import Any

from .errors import ToolkitError
from .evidence import TABLES, load_table, verify_capture, write_json

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/"


def validate_numeric_rows(rows: list[dict[str, Any]]) -> None:
    fields = {key for row in rows for key, value in row.items() if type(value) in (int, float)}
    for field in fields:
        if any(row.get(field) is not None and type(row[field]) not in (int, float) for row in rows):
            raise ToolkitError(
                "Source column contains mixed numeric and text values; inspect retained capture before reporting.",
                code="source_type",
            )
        if any(type(row.get(field)) is int and abs(row[field]) > 2**53 for row in rows):
            raise ToolkitError(
                "Source integer cannot be represented exactly in the numeric report column.",
                code="source_type",
            )


def m_string(value: str) -> str:
    return (
        '"'
        + value.replace("#", "#(#)")
        .replace('"', '""')
        .replace("\r", "#(cr)")
        .replace("\n", "#(lf)")
        + '"'
    )


def local_query(path: Path, columns: list[tuple[str, str]]) -> str:
    fields = ", ".join(m_string(name) for name, _ in columns)
    types = ", ".join(
        "{"
        + m_string(name)
        + ", "
        + ("type number" if kind == "double" else "Int64.Type" if kind == "int64" else "type text")
        + "}"
        for name, kind in columns
    )
    return (
        "let Source = Json.Document(File.Contents(" + m_string(str(path.resolve())) + ")),\n"
        "Rows = Table.FromRecords(Source, {" + fields + "}, MissingField.UseNull),\n"
        "Typed = Table.TransformColumnTypes(Rows, {" + types + '}, "en-US") in Typed'
    )


def build_report(
    comparison: dict[str, Any],
    directory: Path,
    config: dict[str, Any] | None = None,
    *,
    _internal: bool = False,
) -> None:
    capture_mode = comparison.get("schema_version") == "capture-report/1"
    if comparison.get("schema_version") not in (
        ("comparison-result/1", "capture-report/1", "live-placeholder/1")
        if _internal
        else ("comparison-result/1",)
    ):
        raise ToolkitError("Expected a comparison-result/1 artifact.")
    if comparison.get("schema_version") == "comparison-result/1":
        from .compare import compare

        paths = comparison.get("source_captures", [])
        if len(paths) != 2 or not comparison.get("configuration"):
            raise ToolkitError("Rebuild the comparison with its configuration before reporting.")
        expected = compare(Path(paths[0]), Path(paths[1]), comparison["configuration"])
        # Older comparison-result/1 files predate these additive coverage counters.
        # Omission is compatible; a supplied value must still match source evidence.
        old_coverage = comparison.get("coverage")
        if isinstance(old_coverage, list) and len(old_coverage) == 2:
            for old_side, new_side in zip(old_coverage, expected["coverage"], strict=True):
                if isinstance(old_side, dict):
                    for key in ("successful_executions", "executions_without_measurements"):
                        if key not in old_side:
                            new_side.pop(key)
        # Older files also predate the additive per-metric grain marker on observation rows.
        old_metrics = comparison.get("metrics")
        if isinstance(old_metrics, list) and len(old_metrics) == len(expected["metrics"]):
            for old_row, new_row in zip(old_metrics, expected["metrics"], strict=True):
                if (
                    isinstance(old_row, dict)
                    and "grain" not in old_row
                    and new_row.get("grain") == "observation_mean"
                ):
                    new_row.pop("grain")
        if comparison != expected:
            raise ToolkitError(
                "Comparison differs from its verified source/configuration; rebuild it."
            )
    if config is not None and not isinstance(config, dict):
        raise ToolkitError("Use a report/1 configuration object.")
    config = (
        {
            "schema_version": "report/1",
            "title": "Login Enterprise result comparison",
            "visuals": ["comparison_table", "change_chart", "unit_filter", "coverage_table"],
        }
        if config is None
        else dict(config)
    )
    if set(config) - {"schema_version", "title", "visuals", "layout", "overview_table"}:
        raise ToolkitError(
            "Unsupported report specification fields; keep credentials out of reports."
        )
    config.setdefault("title", "Login Enterprise result comparison")
    if (
        not isinstance(config["title"], str)
        or not isinstance(config.get("visuals"), list)
        or not all(isinstance(v, str) for v in config["visuals"])
    ):
        raise ToolkitError("Use a report/1 object with a text title and visual-name list.")
    if len(set(config["visuals"])) != len(config["visuals"]):
        raise ToolkitError("Report visual names must be unique.")
    if config.get("schema_version") != "report/1":
        raise ToolkitError("Unsupported report specification.")
    supported = {
        "comparison_table",
        "change_chart",
        "unit_filter",
        "coverage_table",
        "source_table",
        "resource_table",
    }
    if set(config.get("visuals", [])) - supported:
        raise ToolkitError(
            "Unsupported visual; use comparison_table, change_chart, unit_filter or coverage_table."
        )
    review = config.get("layout", "standard") == "review"
    if config.get("layout", "standard") not in ("standard", "review"):
        raise ToolkitError("Report layout must be standard or review.")
    if "overview_table" in config and (not review or type(config["overview_table"]) is not bool):
        raise ToolkitError("overview_table is a boolean option for the review layout.")
    if review:
        from .review_report import validate_review

        validate_review(comparison, config)
    if directory.exists() and any(directory.iterdir()):
        raise ToolkitError("Report destination must be empty.")
    preflight_tables: dict[str, list[dict[str, Any]]] = {name: [] for name in TABLES}
    for path in comparison.get("source_captures", []):
        source = Path(path)
        verify_capture(source)
        for name in TABLES:
            preflight_tables[name].extend(load_table(source, name))
    for rows in preflight_tables.values():
        validate_numeric_rows(rows)
    directory.mkdir(parents=True, exist_ok=True)
    metrics = [
        {
            **{k: v for k, v in r.items() if k != "group"},
            "group_identity": json.dumps(r["group"], sort_keys=True),
            "grain": r.get("grain", "observation_mean"),
            "baseline_state": r.get("baseline_state"),
            "candidate_state": r.get("candidate_state"),
            "metric_group": r["metric"] + " / " + json.dumps(r["group"], sort_keys=True),
        }
        for r in comparison["metrics"]
    ]
    write_json(directory / "data" / "Comparison.json", metrics)
    write_json(directory / "data" / "Coverage.json", comparison["coverage"])
    write_json(
        directory / "data" / "Warnings.json", [{"warning": w} for w in comparison["warnings"]]
    )
    write_json(directory / "comparison.json", comparison)
    write_json(directory / "report-spec.json", config)
    comparison_cols = [
        ("metric", "string"),
        ("metric_group", "string"),
        ("unit", "string"),
        ("semantics", "string"),
        ("grain", "string"),
        ("baseline_state", "string"),
        ("candidate_state", "string"),
        ("group_identity", "string"),
        *[
            (k, "double")
            for k in (
                "baseline_mean",
                "candidate_mean",
                "absolute_change",
                "relative_change_percent",
            )
        ],
        *[
            (k, "int64")
            for k in (
                "baseline_samples",
                "candidate_samples",
                "baseline_missing",
                "candidate_missing",
            )
        ],
        ("interpretation", "string"),
        ("warning", "string"),
    ]
    coverage_cols = [
        ("scenario", "string"),
        *[
            (k, "int64")
            for k in (
                "sessions",
                "executions",
                "completed_executions",
                "execution_failures",
                "unended_executions",
                "sessions_without_executions",
            )
        ],
        ("completeness", "string"),
    ]
    tables = []
    for name, columns in [
        ("Comparison", comparison_cols),
        ("Coverage", coverage_cols),
        ("Warnings", [("warning", "string")]),
    ]:
        query = local_query(directory / "data" / f"{name}.json", columns)
        (directory / f"{name}.pq").write_text(query + "\n", encoding="utf-8")
        table: dict[str, Any] = {
            "name": name,
            "columns": [
                {"name": col, "dataType": kind, "sourceColumn": col, "summarizeBy": "none"}
                for col, kind in columns
            ],
            "partitions": [
                {
                    "name": name,
                    "mode": "import",
                    "source": {"type": "m", "expression": query.splitlines()},
                }
            ],
        }
        if name == "Comparison":
            table["measures"] = [
                {
                    "name": "Absolute Change",
                    "expression": "IF(COUNTROWS(ALLSELECTED(Comparison[unit])) = 1, SELECTEDVALUE(Comparison[absolute_change]))",
                    "formatString": "0.00",
                },
                {
                    "name": "Relative Change Percent",
                    "expression": "SELECTEDVALUE(Comparison[relative_change_percent])",
                    "formatString": "0.00",
                },
                {
                    "name": "Baseline Mean",
                    "expression": "IF(COUNTROWS(ALLSELECTED(Comparison[unit])) = 1, SELECTEDVALUE(Comparison[baseline_mean]))",
                    "formatString": "0.00",
                },
                {
                    "name": "Candidate Mean",
                    "expression": "IF(COUNTROWS(ALLSELECTED(Comparison[unit])) = 1, SELECTEDVALUE(Comparison[candidate_mean]))",
                    "formatString": "0.00",
                },
            ]
        tables.append(table)
    source_paths = comparison.get("source_captures", [])
    source_tables: dict[str, list[dict[str, Any]]] = {name: [] for name in TABLES}
    roles = ("selected",) if capture_mode else ("baseline", "candidate")
    for label, source_path in zip(roles, source_paths, strict=False):
        source = Path(source_path)
        verify_capture(source)
        shutil.copytree(source, directory / "evidence" / label)
        for name in TABLES:
            for raw in load_table(source, name):
                row = {
                    k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list, bool)) else v
                    for k, v in raw.items()
                }
                row["scenario"] = comparison[label]["label"]
                row["run_key"] = (
                    label + "/" + str(raw.get("testRunId", raw.get("id") if name == "runs" else ""))
                )
                session = (
                    raw.get("id")
                    if name == "sessions"
                    else raw.get("userSessionId", raw.get("userSessionKey"))
                )
                row["session_key"] = row["run_key"] + "/" + str(session) if session else None
                source_tables[name].append(row)
    for name, rows in source_tables.items():
        if not source_paths:
            break
        if name in ("runs", "sessions"):
            key = "run_key" if name == "runs" else "session_key"
            identities = [row[key] for row in rows]
            if None in identities or len(identities) != len(set(identities)):
                raise ToolkitError(
                    "Source relationship keys are not unique; recapture stable identities."
                )
        fields = sorted({k for row in rows for k in row}) or ["capture_id"]
        if name == "measurements":
            fields = sorted(
                set(fields) | {"measurementId", "duration", "timestamp", "userSessionId"}
            )
        if name == "session_metrics":
            fields = sorted(
                set(fields)
                | {
                    "displayName",
                    "fieldName",
                    "measurement",
                    "unit",
                    "instance",
                    "timestamp",
                    "userSessionKey",
                }
            )
        columns = [
            (field, "double" if any(type(r.get(field)) in (float, int) for r in rows) else "string")
            for field in fields
        ]
        validate_numeric_rows(rows)
        model_name = "Source_" + name
        write_json(directory / "data" / f"{model_name}.json", rows)
        query = local_query(directory / "data" / f"{model_name}.json", columns)
        tables.append(
            {
                "name": model_name,
                "columns": [
                    {"name": col, "dataType": kind, "sourceColumn": col, "summarizeBy": "none"}
                    for col, kind in columns
                ],
                "partitions": [
                    {
                        "name": model_name,
                        "mode": "import",
                        "source": {"type": "m", "expression": query.splitlines()},
                    }
                ],
            }
        )
    relationships = []
    for name in ("executions", "measurements", "session_metrics"):
        if source_tables["sessions"] and source_tables[name]:
            relationships.append(
                {
                    "name": "session_to_" + name,
                    "fromTable": "Source_" + name,
                    "fromColumn": "session_key",
                    "toTable": "Source_sessions",
                    "toColumn": "session_key",
                    "crossFilteringBehavior": "oneDirection",
                }
            )
    if source_tables["runs"] and source_tables["sessions"]:
        relationships.append(
            {
                "name": "run_to_session",
                "fromTable": "Source_sessions",
                "fromColumn": "run_key",
                "toTable": "Source_runs",
                "toColumn": "run_key",
                "crossFilteringBehavior": "oneDirection",
            }
        )
    model = {
        "name": "ResultsToolkit",
        "compatibilityLevel": 1600,
        "model": {
            "culture": "en-US",
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "tables": tables,
            "relationships": relationships,
            "annotations": [
                {"name": "PBI_QueryOrder", "value": '["Comparison","Coverage","Warnings"]'}
            ],
        },
    }
    model_dir = directory / "Results.SemanticModel"
    write_json(model_dir / "model.bim", model)
    write_json(
        model_dir / "definition.pbism",
        {
            "$schema": SCHEMA + "semanticModel/definitionProperties/1.0.0/schema.json",
            "version": "1.0",
            "settings": {},
        },
    )
    report_dir = directory / "Results.Report"
    write_json(
        directory / "Results.pbip",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
            "version": "1.0",
            "artifacts": [{"report": {"path": "Results.Report"}}],
            "settings": {"enableAutoRecovery": True},
        },
    )
    write_json(
        report_dir / "definition.pbir",
        {
            "$schema": SCHEMA + "report/definitionProperties/2.0.0/schema.json",
            "version": "4.0",
            "datasetReference": {"byPath": {"path": "../Results.SemanticModel"}},
        },
    )
    definition = report_dir / "definition"
    write_json(
        definition / "version.json",
        {
            "$schema": SCHEMA + "report/definition/versionMetadata/1.0.0/schema.json",
            "version": "2.0.0",
        },
    )
    write_json(
        definition / "report.json",
        {
            "$schema": SCHEMA + "report/definition/report/2.0.0/schema.json",
            "themeCollection": {
                "baseTheme": {
                    "name": "CY24SU10",
                    "reportVersionAtImport": "5.59",
                    "type": "SharedResources",
                }
            },
        },
    )
    write_json(
        definition / "pages" / "pages.json",
        {
            "$schema": SCHEMA + "report/definition/pagesMetadata/1.0.0/schema.json",
            "pageOrder": ["comparison"],
            "activePageName": "comparison",
        },
    )
    page_dir = definition / "pages" / "comparison"
    write_json(
        page_dir / "page.json",
        {
            "$schema": SCHEMA + "report/definition/page/2.0.0/schema.json",
            "name": "comparison",
            "displayName": config["title"],
            "displayOption": "FitToPage",
            "height": 900,
            "width": 1280,
        },
    )

    def column(table: str, name: str, measure: bool = False) -> dict[str, Any]:
        return {
            "field": {
                "Measure" if measure else "Column": {
                    "Expression": {"SourceRef": {"Entity": table}},
                    "Property": name,
                }
            },
            "queryRef": table + "." + name,
            "nativeQueryRef": name,
        }

    for index, name in enumerate([] if review else config["visuals"]):
        if name == "unit_filter":
            visual = {
                "visualType": "slicer",
                "query": {
                    "queryState": {"Values": {"projections": [column("Comparison", "unit")]}}
                },
            }
            position = {"x": 0, "y": 0, "width": 280, "height": 100}
        elif name in ("source_table", "resource_table"):
            resource = name == "resource_table"
            visual = {
                "visualType": "tableEx",
                "query": {
                    "queryState": {
                        "Values": {
                            "projections": [
                                column(
                                    "Source_session_metrics" if resource else "Source_measurements",
                                    field,
                                )
                                for field in (
                                    (
                                        "displayName",
                                        "fieldName",
                                        "measurement",
                                        "unit",
                                        "instance",
                                        "timestamp",
                                        "userSessionKey",
                                    )
                                    if resource
                                    else (
                                        "measurementId",
                                        "duration",
                                        "timestamp",
                                        "userSessionId",
                                    )
                                )
                            ]
                        }
                    }
                },
            }
            position = {
                "x": 0,
                "y": 110 if not resource else 450,
                "width": 1100 if not resource else 700,
                "height": 280,
            }
        elif name == "change_chart":
            visual = {
                "visualType": "clusteredBarChart",
                "query": {
                    "queryState": {
                        "Category": {"projections": [column("Comparison", "metric_group")]},
                        "Y": {"projections": [column("Comparison", "Absolute Change", True)]},
                    }
                },
            }
            position = {"x": 0, "y": 450, "width": 700, "height": 380}
        else:
            visual_table = "Coverage" if name == "coverage_table" else "Comparison"
            fields = (
                [
                    "scenario",
                    "sessions",
                    "executions",
                    "execution_failures",
                    "sessions_without_executions",
                    "completeness",
                ]
                if visual_table == "Coverage"
                else [
                    "metric_group",
                    "unit",
                    "grain",
                    "baseline_mean",
                    "candidate_mean",
                    "absolute_change",
                    "relative_change_percent",
                    "baseline_samples",
                    "candidate_samples",
                    "warning",
                ]
            )
            visual = {
                "visualType": "tableEx",
                "query": {
                    "queryState": {
                        "Values": {"projections": [column(visual_table, f) for f in fields]}
                    }
                },
            }
            position = {
                "x": 0 if visual_table == "Comparison" else 710,
                "y": 110 if visual_table == "Comparison" else 450,
                "width": 1260 if visual_table == "Comparison" else 550,
                "height": 320,
            }
        write_json(
            page_dir / "visuals" / name / "visual.json",
            {
                "$schema": SCHEMA + "report/definition/visualContainer/2.1.0/schema.json",
                "name": name,
                "position": {**position, "z": index, "tabOrder": index},
                "visual": visual,
            },
        )
    html_rows = "".join(
        "<tr>"
        + "".join(
            "<td>" + html.escape(str(r.get(k) if r.get(k) is not None else "unavailable")) + "</td>"
            for k in (
                "metric_group",
                "unit",
                "grain",
                "baseline_mean",
                "candidate_mean",
                "absolute_change",
                "relative_change_percent",
                "baseline_samples",
                "candidate_samples",
            )
        )
        + "</tr>"
        for r in metrics
    )
    warnings = "".join("<li>" + html.escape(w) + "</li>" for w in comparison["warnings"])
    bars = ""
    for i, row in enumerate(metrics):
        delta = row["relative_change_percent"]
        label = html.escape(row["metric_group"])
        y = i * 48
        if delta is None:
            bars += f'<text x="0" y="{y + 16}">{label}: relative change unavailable (missing or zero baseline)</text>'
        else:
            width = min(abs(delta), 100) * 3
            x = 350 - width if delta < 0 else 350
            bars += f'<text x="0" y="{y + 16}">{label}: {delta:+.2f}%</text><line x1="350" y1="{y + 22}" x2="350" y2="{y + 44}" stroke="#172033"/><rect x="{x}" y="{y + 24}" width="{width}" height="18" fill="#2563eb"/>'
    comparison_section = (
        ""
        if capture_mode
        else (
            "<table><tr><th>Metric/group</th><th>Unit</th><th>Grain</th><th>Baseline value/mean</th><th>Candidate value/mean</th><th>Absolute change</th><th>Relative %</th><th>Baseline n</th><th>Candidate n</th></tr>"
            + html_rows
            + "</table>"
            + f'<svg width="700" height="{max(48, len(metrics) * 48)}" aria-label="Signed relative change percent; negative left, positive right; bars clipped at 100 percent">'
            + bars
            + "</svg>"
        )
    )
    content = (
        "<!doctype html><html lang='en'><meta charset='utf-8'><title>Result evidence</title>"
        "<style>body{font:16px system-ui;margin:32px;color:#172033}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}table{border-collapse:collapse}li{margin:10px}svg{max-width:100%}</style>"
        "<h1>"
        + html.escape(config["title"])
        + "</h1><p>"
        + (
            html.escape(comparison["selected"]["label"])
            if capture_mode
            else html.escape(comparison["baseline"]["label"])
            + " compared with "
            + html.escape(comparison["candidate"]["label"])
        )
        + "</p>"
        + comparison_section
        + "<h2>Coverage</h2><pre>"
        + html.escape(json.dumps(comparison["coverage"], indent=2))
        + "</pre><h2>Evidence limits</h2><ul>"
        + warnings
        + "</ul></html>"
    )
    (directory / "report.html").write_text(content, encoding="utf-8")
    if capture_mode:
        source_rows = source_tables["measurements"]
        headers = ("measurementId", "duration", "timestamp", "userSessionId")
        details = (
            "<h2>Retained timer observations</h2><p>Duration units are unspecified by the API. This preview shows up to 500 rows; complete source datasets remain in the bundle.</p><table><tr>"
            + "".join("<th>" + field + "</th>" for field in headers)
            + "</tr>"
        )
        details += (
            "".join(
                "<tr>"
                + "".join(
                    "<td>"
                    + html.escape(
                        str(row.get(field) if row.get(field) is not None else "unavailable")
                    )
                    + "</td>"
                    for field in headers
                )
                + "</tr>"
                for row in source_rows[:500]
            )
            + "</table>"
        )
        details += (
            "<h2>Retained resource observations</h2><p>Source units, field and instance identities are retained. Up to 500 rows are shown; complete datasets remain in the bundle. No cross-unit average is calculated.</p><table><tr>"
            + "".join(
                "<th>" + field + "</th>"
                for field in (
                    "displayName",
                    "fieldName",
                    "measurement",
                    "unit",
                    "instance",
                    "timestamp",
                    "userSessionKey",
                )
            )
            + "</tr>"
            + "".join(
                "<tr>"
                + "".join(
                    "<td>"
                    + html.escape("unavailable" if row.get(field) is None else str(row[field]))
                    + "</td>"
                    for field in (
                        "displayName",
                        "fieldName",
                        "measurement",
                        "unit",
                        "instance",
                        "timestamp",
                        "userSessionKey",
                    )
                )
                + "</tr>"
                for row in source_tables["session_metrics"][:500]
            )
            + "</table>"
        )
        details += (
            "<h2>Endpoint outcomes</h2><pre>"
            + html.escape(json.dumps(comparison["endpoint_outcomes"], indent=2))
            + "</pre>"
        )
        (directory / "report.html").write_text(
            content.replace("</html>", details + "</html>"), encoding="utf-8"
        )
    (directory / ".gitignore").write_text(
        "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n", encoding="utf-8"
    )
    if review:
        from .review_report import build_review

        build_review(comparison, directory, config)


def build_capture_report(
    source: Path,
    directory: Path,
    title: str = "Selected result evidence",
    config: dict[str, Any] | None = None,
) -> None:
    if config is not None:
        if (
            not isinstance(config, dict)
            or not isinstance(config.get("title", title), str)
            or not isinstance(config.get("visuals"), list)
            or not all(isinstance(v, str) for v in config["visuals"])
        ):
            raise ToolkitError(
                "Use a report/1 object with a text title and a list of visual names."
            )
        if any(
            v not in ("source_table", "resource_table", "coverage_table")
            for v in config.get("visuals", [])
        ):
            raise ToolkitError(
                "Finite evidence reports support source, resource and coverage tables only."
            )
        title = config.get("title", title)
        config = {**config, "title": title}
    manifest = verify_capture(source)
    sessions = load_table(source, "sessions")
    executions = load_table(source, "executions")
    selected = {"label": title, "ids": manifest["selection"]["ids"]}
    coverage = {
        "scenario": title,
        "sessions": len(sessions),
        "executions": len(executions),
        "completed_executions": sum(
            r.get("state") in ("ended", "endedWithErrors") for r in executions
        ),
        "execution_failures": sum(row.get("state") == "endedWithErrors" for row in executions),
        "unended_executions": sum(row.get("state") == "created" for row in executions),
        "sessions_without_executions": sum(
            not any(
                e.get("userSessionId") == s.get("id") and e.get("testRunId") == s.get("testRunId")
                for e in executions
            )
            for s in sessions
        ),
        "completeness": manifest["status"],
        "login_states": {
            str(state): sum(s.get("loginState") == state for s in sessions)
            for state in {s.get("loginState") for s in sessions}
        },
    }
    result = {
        "schema_version": "capture-report/1",
        "selected": selected,
        "metrics": [],
        "coverage": [coverage],
        "warnings": [
            *manifest["warnings"],
            "Capture status: " + manifest["status"],
            "Finite selected evidence; no comparison or causal claim is made.",
        ],
        "source_captures": [str(source.resolve())],
        "source_manifests": [manifest],
        "endpoint_outcomes": manifest["endpoints"],
    }
    build_report(
        result,
        directory,
        config
        if config is not None
        else {
            "schema_version": "report/1",
            "title": title,
            "visuals": ["source_table", "resource_table", "coverage_table"],
        },
        _internal=True,
    )
    (directory / "OPEN-IN-DESKTOP.txt").write_text(
        "Open Results.pbip in Power BI Desktop, refresh local files, select one unit, and reconcile "
        "source rows, units, sample counts and execution failures with the retained capture. "
        "This finite report has no baseline/candidate deltas. Record acceptance for this project/build. "
        "No appliance credential is required. Moving the directory requires regenerating file paths.\n",
        encoding="utf-8",
    )
