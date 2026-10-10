"""Editable, local-file Power BI project plus a portable HTML evidence report."""

import html
import json
import shutil
from pathlib import Path
from typing import Any

from .errors import ToolkitError
from .evidence import TABLES, load_table, verify_capture, write_json

SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/"


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
    comparison: dict[str, Any], directory: Path, config: dict[str, Any] | None = None
) -> None:
    if comparison.get("schema_version") != "comparison-result/1":
        raise ToolkitError("Expected a comparison-result/1 artifact.")
    config = config or {
        "schema_version": "report/1",
        "title": "Login Enterprise result comparison",
        "visuals": ["comparison_table", "change_chart", "unit_filter", "coverage_table"],
    }
    if config.get("schema_version") != "report/1":
        raise ToolkitError("Unsupported report specification.")
    supported = {"comparison_table", "change_chart", "unit_filter", "coverage_table"}
    if set(config.get("visuals", [])) - supported:
        raise ToolkitError(
            "Unsupported visual; use comparison_table, change_chart, unit_filter or coverage_table."
        )
    if directory.exists() and any(directory.iterdir()):
        raise ToolkitError("Report destination must be empty.")
    directory.mkdir(parents=True, exist_ok=True)
    metrics = [
        {
            **{k: v for k, v in r.items() if k != "group"},
            "group_identity": json.dumps(r["group"], sort_keys=True),
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
    for label, source_path in zip(("baseline", "candidate"), source_paths, strict=False):
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
                row["run_key"] = str(raw.get("testRunId", raw.get("id") if name == "runs" else ""))
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
        fields = sorted({k for row in rows for k in row}) or ["capture_id"]
        columns = [
            (field, "double" if any(type(r.get(field)) in (float, int) for r in rows) else "string")
            for field in fields
        ]
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

    for index, name in enumerate(config["visuals"]):
        if name == "unit_filter":
            visual = {
                "visualType": "slicer",
                "query": {
                    "queryState": {"Values": {"projections": [column("Comparison", "unit")]}}
                },
            }
            position = {"x": 0, "y": 0, "width": 280, "height": 100}
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
        if row["absolute_change"] is not None:
            delta = row["relative_change_percent"]
            if delta is not None:
                width = min(abs(delta), 100) * 3
                bars += f'<text x="0" y="{i * 40 + 20}" font-size="12">{html.escape(row["metric"])} ({delta:.2f}%)</text><rect x="300" y="{i * 40 + 5}" width="{width}" height="20" fill="#2563eb"/>'
    content = (
        "<!doctype html><html lang='en'><meta charset='utf-8'><title>Result evidence</title>"
        "<style>body{font:16px system-ui;margin:32px;color:#172033}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}table{border-collapse:collapse}li{margin:10px}svg{max-width:100%}</style>"
        "<h1>"
        + html.escape(config["title"])
        + "</h1><p>"
        + html.escape(comparison["baseline"]["label"])
        + " compared with "
        + html.escape(comparison["candidate"]["label"])
        + "</p>"
        "<table><tr><th>Metric/group</th><th>Unit</th><th>Baseline mean</th><th>Candidate mean</th><th>Absolute change</th><th>Relative %</th><th>Baseline n</th><th>Candidate n</th></tr>"
        + html_rows
        + "</table>"
        f'<svg width="700" height="{max(40, len(metrics) * 40)}" aria-label="Relative change percent; bars clipped at 100 percent">'
        + bars
        + "</svg>"
        "<h2>Coverage</h2><pre>"
        + html.escape(json.dumps(comparison["coverage"], indent=2))
        + "</pre><h2>Evidence limits</h2><ul>"
        + warnings
        + "</ul></html>"
    )
    (directory / "report.html").write_text(content, encoding="utf-8")
    (directory / ".gitignore").write_text(
        "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n", encoding="utf-8"
    )
    (directory / "OPEN-IN-DESKTOP.txt").write_text(
        "Open Results.pbip in Power BI Desktop, refresh local files, select one unit, and reconcile "
        "means, deltas, sample counts and execution failures with comparison.json. "
        "Desktop build 2.158.1304.0 is a target until this passes. "
        "No appliance credential is required. Moving the directory requires regenerating file paths.\n",
        encoding="utf-8",
    )
