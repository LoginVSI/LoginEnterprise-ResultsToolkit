"""A finite engineering-review presentation of verified comparison facts.

No scoring, unit conversion, pooled means or replacement comparison arithmetic.
HTML and native PBIR visuals bind to the same engine-derived presentation tables.
"""

import html
import json
from pathlib import Path
from typing import Any

from .errors import ToolkitError
from .evidence import write_json

INK = "#17283D"
BLUE = "#42638C"
TEAL = "#087F8C"
AMBER = "#9A5200"


def action(row: dict[str, Any]) -> str:
    group = "; ".join(f"{key}: {value}" for key, value in row["group"].items())
    return row["metric"] + (" / " + group if group else "")


def validate_review(comparison: dict[str, Any], config: dict[str, Any]) -> None:
    rows = comparison["metrics"]
    if comparison.get("schema_version") != "comparison-result/1":
        raise ToolkitError("Review layout requires a verified comparison.")
    if any(
        "executions_without_measurements" not in side or "successful_executions" not in side
        for side in comparison["coverage"]
    ):
        raise ToolkitError("Rebuild this comparison for review-layout coverage counters.")
    if any(side["completeness"] != "complete" for side in comparison["coverage"]):
        raise ToolkitError(
            "Review layout requires complete acquisition; use the standard evidence report for partial captures."
        )
    if any(
        side.get("execution_state_unknown", 0) or side["executions_without_measurements"] is None
        for side in comparison["coverage"]
    ):
        raise ToolkitError(
            "Review layout requires known execution states and resolved timing links; use the standard evidence report."
        )
    if not 1 <= len(rows) <= 3 or len({row["unit"] for row in rows}) != 1:
        raise ToolkitError("Review layout needs 1-3 actions with one shared source unit.")
    if len(config["title"]) > 60 or any(len(action(row)) > 20 for row in rows):
        raise ToolkitError(
            "Review layout needs a title up to 60 characters and action labels up to 20 characters; retain full identity in the evidence."
        )
    if any(row["semantics"] != "duration" for row in rows):
        raise ToolkitError("Review layout is for duration comparisons, not scores or resources.")
    if len({action(row) for row in rows}) != len(rows):
        raise ToolkitError("Review actions need distinct labels/group identities.")
    if any(
        row[key] is not None and row[key] < 0
        for row in rows
        for key in ("baseline_mean", "candidate_mean")
    ):
        raise ToolkitError("Review timing bars require nonnegative source means.")
    if set(config["visuals"]) != {
        "comparison_table",
        "change_chart",
        "coverage_table",
        "source_table",
    }:
        raise ToolkitError(
            "Review layout uses comparison_table, change_chart, coverage_table and source_table."
        )


def fmt(value: Any, signed: bool = False) -> str:
    if value is None:
        return "Unavailable"
    if value == 0:
        return "0"
    if abs(value) < 0.05:
        return format(value, "+.3g" if signed else ".3g")
    return format(value, "+,.1f" if signed else ",.1f").removesuffix(".0")


def lit(value: Any) -> dict[str, Any]:
    text = (
        ("true" if value else "false")
        if type(value) is bool
        else ("'" + value.replace("'", "''") + "'" if isinstance(value, str) else f"{value}D")
    )
    return {"expr": {"Literal": {"Value": text}}}


def fill(color: str) -> dict[str, Any]:
    return {"solid": {"color": lit(color)}}


def projection(table: str, name: str, measure: bool = False) -> dict[str, Any]:
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


def build_review(comparison: dict[str, Any], directory: Path, config: dict[str, Any]) -> None:
    from .report import SCHEMA, local_query

    rows, coverage = comparison["metrics"], comparison["coverage"]
    synthetic = any(m.get("provenance") == "synthetic" for m in comparison["source_manifests"])
    badge = "SYNTHETIC DEMONSTRATION" if synthetic else "RETAINED RESULT COMPARISON"
    b, c = coverage
    unit = rows[0]["unit"]
    timing = [
        {
            "Action": action(row),
            "Unit": row["unit"],
            "Baseline mean": row["baseline_mean"],
            "Candidate mean": row["candidate_mean"],
            "Change percent": row["relative_change_percent"],
            "Baseline n": row["baseline_samples"],
            "Candidate n": row["candidate_samples"],
            "Baseline unavailable": row["baseline_missing"],
            "Candidate unavailable": row["candidate_missing"],
        }
        for row in rows
    ]
    coverage_rows = [
        {
            "Role": role,
            "Sessions": side["sessions"],
            "Executions": side["executions"],
            "Succeeded": side["successful_executions"],
            "Failed": side["execution_failures"],
            "No retained timing": side["executions_without_measurements"],
            "Unfinished": side["unended_executions"],
            "Acquisition": side["completeness"],
        }
        for role, side in zip(("Baseline", "Candidate"), coverage, strict=True)
    ]
    cards = {
        "Application actions": str(len(rows)),
        "Matched timings | B / C": f"{sum(r['baseline_samples'] for r in rows)} / {sum(r['candidate_samples'] for r in rows)}",
        "Execution failures | B / C": f"{b['execution_failures']} / {c['execution_failures']}",
        "No retained timing | B / C": f"{b['executions_without_measurements']} / {c['executions_without_measurements']}",
    }
    warning = (
        f"Full selection | Failures B / C: {b['execution_failures']} / {c['execution_failures']}. "
        f"No retained timing B / C: {b['executions_without_measurements']} / {c['executions_without_measurements']}. "
        "Missing is not zero. No rollout verdict: acceptance criteria are not defined."
    )
    limits = (
        "Means describe available retained observations, equally weighted per action. "
        "Counts are observations and executions, not independent users or devices. "
        "No rollout verdict or overall score: acceptance criteria are not defined."
    )
    if synthetic:
        limits += " Authored fixture units and scenario roles are not appliance evidence or Windows performance conclusions."

    model_path = directory / "Results.SemanticModel/model.bim"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    for name, data in [
        ("ReviewTiming", timing),
        ("ReviewCoverage", coverage_rows),
        ("ReviewCards", [cards]),
    ]:
        columns = [
            (
                key,
                "int64"
                if type(value) is int
                else "double"
                if type(value) is float
                or key in ("Baseline mean", "Candidate mean", "Change percent")
                else "string",
            )
            for key, value in data[0].items()
        ]
        write_json(directory / "data" / f"{name}.json", data)
        query = local_query(directory / "data" / f"{name}.json", columns)
        (directory / f"{name}.pq").write_text(query + "\n", encoding="utf-8")
        model_table: dict[str, Any] = {
            "name": name,
            "columns": [
                {
                    "name": key,
                    "sourceColumn": key,
                    "dataType": kind,
                    "summarizeBy": "none",
                    **(
                        {"formatString": '0.0"%"' if key == "Change percent" else "#,0.0"}
                        if kind == "double"
                        else {}
                    ),
                }
                for key, kind in columns
            ],
            "partitions": [
                {
                    "name": name,
                    "mode": "import",
                    "source": {"type": "m", "expression": query.splitlines()},
                }
            ],
        }
        if name == "ReviewTiming":
            model_table["measures"] = [
                {
                    "name": label,
                    "expression": f"IF(HASONEVALUE(ReviewTiming[Unit]), SELECTEDVALUE(ReviewTiming[{field}]))",
                    "formatString": '0.0"%"' if field == "Change percent" else "#,0.0",
                }
                for label, field in [
                    ("Baseline", "Baseline mean"),
                    ("Candidate", "Candidate mean"),
                    ("Change (%)", "Change percent"),
                ]
            ]
        elif name == "ReviewCards":
            model_table["measures"] = [
                {"name": key + " value", "expression": f"SELECTEDVALUE(ReviewCards[{key}])"}
                for key in cards
            ]
        model["model"]["tables"].append(model_table)
    write_json(model_path, model)
    definition = directory / "Results.Report/definition"
    write_json(
        definition / "pages/pages.json",
        {
            "$schema": SCHEMA + "report/definition/pagesMetadata/1.0.0/schema.json",
            "pageOrder": ["comparison", "evidence"],
            "activePageName": "comparison",
        },
    )
    for name, page_title in [
        ("comparison", "Overview"),
        ("evidence", "Evidence and sample counts"),
    ]:
        write_json(
            definition / "pages" / name / "page.json",
            {
                "$schema": SCHEMA + "report/definition/page/2.0.0/schema.json",
                "name": name,
                "displayName": page_title,
                "displayOption": "FitToPage",
                "width": 1280,
                "height": 720,
            },
        )

    visual_index = 0

    def visual(
        name: str, body: dict[str, Any], box: tuple[int, int, int, int], page: str = "comparison"
    ) -> None:
        nonlocal visual_index
        x, y, width, height = box
        visual_index += 1
        write_json(
            definition / "pages" / page / "visuals" / name / "visual.json",
            {
                "$schema": SCHEMA + "report/definition/visualContainer/2.1.0/schema.json",
                "name": name,
                "position": {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "z": visual_index,
                    "tabOrder": visual_index,
                },
                "visual": body,
            },
        )

    def text(
        name: str,
        value: str,
        box: tuple[int, int, int, int],
        size: int = 14,
        color: str = INK,
        page: str = "comparison",
        background: str = "#FFFFFF",
    ) -> None:
        visual(
            name,
            {
                "visualType": "textbox",
                "objects": {
                    "general": [
                        {
                            "properties": {
                                "paragraphs": [
                                    {
                                        "textRuns": [
                                            {
                                                "value": value,
                                                "textStyle": {
                                                    "fontFamily": "Segoe UI",
                                                    "fontSize": f"{size}pt",
                                                    "color": color,
                                                },
                                            }
                                        ]
                                    }
                                ]
                            }
                        }
                    ]
                },
                "visualContainerObjects": {
                    "background": [{"properties": {"show": lit(True), "color": fill(background)}}]
                },
            },
            box,
            page,
        )

    def title(value: str) -> dict[str, Any]:
        return {
            "title": [
                {
                    "properties": {
                        "show": lit(True),
                        "text": lit(value),
                        "fontSize": lit(14),
                        "fontColor": fill(INK),
                    }
                }
            ]
        }

    def table(
        name: str,
        entity: str,
        fields: list[str],
        box: tuple[int, int, int, int],
        page: str = "comparison",
    ) -> None:
        visual(
            name,
            {
                "visualType": "tableEx",
                "query": {
                    "queryState": {
                        "Values": {"projections": [projection(entity, field) for field in fields]}
                    }
                },
                "objects": {
                    "columnHeaders": [
                        {
                            "properties": {
                                "fontSize": lit(11),
                                "autoSizeColumnWidth": lit(True),
                                "columnAdjustment": lit("growToFit"),
                            }
                        }
                    ],
                    "values": [{"properties": {"fontSize": lit(11)}}],
                },
            },
            box,
            page,
        )

    text("title", badge + "  |  " + config["title"], (24, 12, 1232, 44), 21)

    def short_label(value: str) -> str:
        return value if len(value) <= 40 else value[:37] + "..."

    text(
        "roles",
        short_label(comparison["baseline"]["label"])
        + "  →  "
        + short_label(comparison["candidate"]["label"])
        + f"  |  Timing unit: {unit}",
        (24, 60, 1232, 32),
        12,
    )
    for i, key in enumerate(cards):
        visual(
            "card" + str(i),
            {
                "visualType": "card",
                "query": {
                    "queryState": {
                        "Values": {"projections": [projection("ReviewCards", key + " value", True)]}
                    }
                },
                "objects": {
                    "labels": [{"properties": {"fontSize": lit(25)}}],
                    "categoryLabels": [{"properties": {"show": lit(False)}}],
                },
                "visualContainerObjects": title(key),
            },
            (24 + i * 314, 104, 290, 78),
        )
    bound = max(10, max(abs(row["relative_change_percent"] or 0) for row in rows) * 1.25)
    for name, measures, label, x in [
        ("timings", ["Baseline", "Candidate"], f"Mean timing ({unit})", 24),
        ("changes", ["Change (%)"], "Change vs baseline (%) | 0 = same mean", 652),
    ]:
        objects: dict[str, Any] = {
            "labels": [
                {
                    "properties": {
                        "show": lit(True),
                        "labelPrecision": lit(1),
                        "labelDisplayUnits": lit(1),
                    }
                }
            ],
            "categoryAxis": [{"properties": {"fontSize": lit(12)}}],
            "valueAxis": [
                {
                    "properties": {
                        "start": lit(-bound if name == "changes" else 0),
                        "labelDisplayUnits": lit(1),
                        **({"end": lit(bound)} if name == "changes" else {}),
                    }
                }
            ],
            "dataPoint": [
                {
                    "properties": {"fill": fill(TEAL)},
                    "selector": {"metadata": "ReviewTiming." + measures[-1]},
                }
            ],
        }
        if name == "timings":
            objects["dataPoint"].append(
                {
                    "properties": {"fill": fill(BLUE)},
                    "selector": {"metadata": "ReviewTiming.Baseline"},
                }
            )
        else:
            objects["y1AxisReferenceLine"] = [
                {
                    "selector": {"id": "0"},
                    "properties": {
                        "show": lit(True),
                        "value": lit(0),
                        "lineColor": fill(INK),
                        "style": lit("solid"),
                        "transparency": lit(0),
                    },
                }
            ]
        visual(
            name,
            {
                "visualType": "clusteredBarChart",
                "query": {
                    "queryState": {
                        "Category": {"projections": [projection("ReviewTiming", "Action")]},
                        "Y": {
                            "projections": [
                                projection("ReviewTiming", value, True) for value in measures
                            ]
                        },
                    }
                },
                "objects": objects,
                "visualContainerObjects": title(label),
            },
            (x, 196, 604, 270),
        )
    text("coverage_title", "Work completed | full selected workloads", (24, 474, 1232, 28), 14)
    table(
        "coverage",
        "ReviewCoverage",
        ["Role", "Executions", "Succeeded", "Failed", "Unfinished", "No retained timing"],
        (24, 508, 604, 126),
    )
    if config.get("overview_table", True):
        table(
            "samples", "ReviewTiming", ["Action", "Baseline n", "Candidate n"], (652, 508, 604, 126)
        )
    else:
        text("limits", limits, (652, 508, 604, 126), 12)
    text("failure_warning", warning, (24, 648, 1232, 60), 13, AMBER, background="#FFF4DE")
    text(
        "evidence_title",
        badge + " | Source evidence and sample counts",
        (24, 12, 1232, 46),
        22,
        page="evidence",
    )
    table("samples", "ReviewTiming", list(timing[0]), (24, 70, 1232, 150), "evidence")
    table(
        "source",
        "Source_measurements",
        ["scenario", "measurementId", "duration", "timestamp", "appExecutionId"],
        (24, 235, 1232, 195),
        "evidence",
    )
    table("warnings", "Warnings", ["warning"], (24, 442, 1232, 82), "evidence")
    identity_text = "Selected IDs: baseline "
    identity_text += (
        ", ".join(comparison["baseline"]["ids"])
        + "; candidate "
        + ", ".join(comparison["candidate"]["ids"])
    )
    if len(identity_text) > 170:
        identity_text = "Selected IDs and complete scenario labels are retained in comparison.json and the copied manifests."
    text(
        "identities",
        identity_text,
        (24, 532, 1232, 60),
        12,
        page="evidence",
    )
    text(
        "evidence_limits",
        limits
        + " Raw responses, manifests, comparison definitions and full source tables travel with this project.",
        (24, 604, 1232, 100),
        13,
        page="evidence",
    )
    render_html(directory, config, badge, timing, coverage_rows, cards, warning, limits, comparison)


def render_html(
    directory: Path,
    config: dict[str, Any],
    badge: str,
    timing: list[dict[str, Any]],
    coverage: list[dict[str, Any]],
    cards: dict[str, str],
    warning: str,
    limits: str,
    comparison: dict[str, Any],
) -> None:
    esc = html.escape
    unit = timing[0]["Unit"]

    def table(rows: list[dict[str, Any]], fields: list[str]) -> str:
        return (
            "<table><thead><tr>"
            + "".join("<th>" + esc(k) + "</th>" for k in fields)
            + "</tr></thead><tbody>"
            + "".join(
                "<tr>"
                + "".join(
                    "<td>"
                    + esc(
                        fmt(row[key])
                        if type(row[key]) in (int, float) or row[key] is None
                        else str(row[key])
                    )
                    + "</td>"
                    for key in fields
                )
                + "</tr>"
                for row in rows
            )
            + "</tbody></table>"
        )

    max_mean = (
        max(
            (row[key] or 0 for row in timing for key in ("Baseline mean", "Candidate mean")),
            default=1,
        )
        or 1
    )
    bound = max(10, max(abs(row["Change percent"] or 0) for row in timing) * 1.25)
    absolute, relative = "", ""
    for i, row in enumerate(timing):
        y = 25 + i * 50
        label = esc(row["Action"])
        absolute += f'<text x="4" y="{y}">{label}</text>'
        for field, color, offset in [("Baseline mean", BLUE, 8), ("Candidate mean", TEAL, 27)]:
            value = row[field]
            width = 240 * (value or 0) / max_mean
            absolute += f'<rect x="185" y="{y + offset - 16}" width="{width:.3f}" height="14" rx="3" fill="{color}"/><text x="{195 + width:.3f}" y="{y + offset - 4}">{esc(fmt(value))}</text>'
        value = row["Change percent"]
        width = abs(value or 0) / bound * 135
        x = 325 - width if value is not None and value < 0 else 325
        relative += f'<text x="4" y="{y}">{label}</text><rect x="{x:.3f}" y="{y + 5}" width="{width:.3f}" height="20" rx="3" fill="{TEAL}"/><text x="{x - 9 if value is not None and value < 0 else x + width + 9:.3f}" y="{y + 20}" text-anchor="{"end" if value is not None and value < 0 else "start"}">{esc(fmt(value, True))}{"%" if value is not None else ""}</text>'
        if value == 0:
            relative += f'<circle cx="325" cy="{y + 15}" r="4" fill="{TEAL}"/>'
    height = max(190, len(timing) * 50 + 40)

    def svg(body: str, label: str) -> str:
        return f'<svg viewBox="0 0 560 {height}" role="img" aria-label="{label}">{body}</svg>'

    ticks = "".join(
        f'<text x="{x}" y="{height - 4}" text-anchor="middle">{fmt(value, True)}%</text>'
        for x, value in [(190, -bound), (325, 0), (460, bound)]
    )
    relative += (
        f'<line x1="325" y1="10" x2="325" y2="{height - 24}" stroke="{INK}" stroke-width="2"/>'
        + ticks
    )
    details = table(timing, list(timing[0]))
    samples = table(timing, ["Action", "Baseline n", "Candidate n"])
    notes = "<ul>" + "".join("<li>" + esc(w) + "</li>" for w in comparison["warnings"]) + "</ul>"
    content = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(config["title"])} | {badge}</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#edf1f5;color:{INK};font:16px "Segoe UI",Arial,sans-serif}}main{{max-width:1440px;margin:auto;padding:20px}}.overview{{background:white;border-radius:16px;padding:22px}}header{{display:flex;justify-content:space-between;align-items:start;gap:20px}}h1{{font-size:28px;margin:6px 0}}h2{{font-size:19px;margin:0 0 12px}}p{{margin:6px 0;line-height:1.45}}.badge{{font-size:12px;letter-spacing:1.5px;font-weight:700;color:{AMBER}}}.meta,.note{{color:#526379;font-size:14px}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:16px 0}}.card{{background:#f1f5f8;padding:12px 16px;border-radius:10px}}.value{{display:block;font-size:28px;font-weight:600;margin-top:4px}}.pair{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}.panel{{border:1px solid #e0e6ec;border-radius:12px;padding:16px;min-width:0}}svg{{width:100%;height:184px;display:block}}svg text{{font:18px "Segoe UI",Arial,sans-serif;fill:{INK}}}.legend{{display:flex;gap:20px;font-size:13px;margin:0 0 8px}}.dot{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}}table{{border-collapse:collapse;width:100%;font-size:14px}}th{{color:#526379;font-weight:600;text-align:left}}th,td{{padding:7px 8px;border-bottom:1px solid #e4e9ef}}.coverage{{margin-top:16px}}.warning{{background:#fff4de;color:#794300;border-left:4px solid #c47a11;padding:10px 14px;border-radius:6px;margin-top:14px;font-size:14px}}details{{background:white;border-radius:12px;margin-top:20px;padding:20px;overflow:auto}}summary{{font-weight:600;cursor:pointer}}.detail-note{{margin-top:14px}}@media(max-width:900px){{.pair{{grid-template-columns:1fr}}.cards{{grid-template-columns:1fr 1fr}}main{{padding:12px}}}}</style></head><body><main>
<section class="overview"><header><div><span class="badge">{badge}</span><h1>{esc(config["title"])}</h1><p class="meta">{esc(comparison["baseline"]["label"])} → {esc(comparison["candidate"]["label"])}</p></div><span class="meta">ENGINEERING REVIEW<br>Local snapshot</span></header>
<div class="cards">{"".join('<div class="card"><span class="meta">' + esc(k) + '</span><span class="value">' + esc(v) + "</span></div>" for k, v in cards.items())}</div>
<div class="pair"><section class="panel"><h2>Application timing · {esc(unit)}</h2><div class="legend"><span><i class="dot" style="background:{BLUE}"></i>Baseline mean</span><span><i class="dot" style="background:{TEAL}"></i>Candidate mean</span></div>{svg(absolute, "Baseline and candidate timing means in " + esc(unit))}</section><section class="panel"><h2>Change from baseline · %</h2><p class="note">Negative = shorter timing · 0 = same mean · positive = longer timing</p>{svg(relative, "Signed relative change percent with a shared zero reference")}</section></div>
<div class="pair coverage"><section><h2>Work completed</h2>{table(coverage, ["Role", "Executions", "Succeeded", "Failed", "Unfinished", "No retained timing"])}<p class="note">{coverage[0]["Sessions"]} baseline / {coverage[1]["Sessions"]} candidate sessions. B / C = baseline / candidate.</p></section><section><h2>{"Observation coverage" if config.get("overview_table", True) else "How to read this comparison"}</h2>{samples if config.get("overview_table", True) else '<p class="note">' + esc(limits) + "</p>"}</section></div>
<aside class="warning">{esc(warning)}</aside></section>
<details><summary>Evidence, sample counts and limitations</summary><p class="detail-note">{esc(limits)}</p>{details}<h2>Selection and source</h2><p>Baseline IDs: {esc(", ".join(comparison["baseline"]["ids"]))}<br>Candidate IDs: {esc(", ".join(comparison["candidate"]["ids"]))}</p>{notes}<p>Full raw/normalized source, manifests and verified comparison definitions remain in the accompanying project bundle. This HTML is self-contained and makes no network requests.</p></details></main></body></html>"""
    (directory / "report.html").write_text(content, encoding="utf-8")
