"""Explicit, unit-aware comparisons. No inferred OS identity or EUX calculation."""

import math
import statistics
from pathlib import Path
from typing import Any

from .errors import ToolkitError
from .evidence import load_table, verify_capture


def numeric(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def compare(baseline: Path, candidate: Path, config: dict[str, Any]) -> dict[str, Any]:
    bm, cm = verify_capture(baseline), verify_capture(candidate)
    if config.get("schema_version") != "comparison/1":
        raise ToolkitError("Expected comparison/1 configuration.")
    if bm["selection"]["test_type"] != cm["selection"]["test_type"]:
        raise ToolkitError("Cannot compare different test models.")
    if bm["status"] != "complete" or cm["status"] != "complete":
        raise ToolkitError("Comparison requires complete captures; inspect partial evidence first.")
    warnings: list[str] = []
    if bm["provenance"] == "synthetic" or cm["provenance"] == "synthetic":
        warnings.append("SYNTHETIC demonstration; these values are not benchmark results.")
    warnings.extend(
        [
            "Observed change does not establish causality.",
            "Arithmetic observation means use equal weight per retained observation, not per device.",
        ]
    )
    sides = [(baseline, bm, config["baseline"]), (candidate, cm, config["candidate"])]
    for _directory, manifest, scenario in sides:
        if not isinstance(scenario, dict) or not scenario.get("label") or not scenario.get("ids"):
            raise ToolkitError("Each scenario needs an explicit label and selected IDs.")
        if not set(scenario["ids"]).issubset(manifest["selection"]["ids"]):
            raise ToolkitError("Scenario IDs are not present in the capture selection.")
    bruns, cruns = load_table(baseline, "runs"), load_table(candidate, "runs")
    bconfigs = [r.get("testConfigurationSnapshot") for r in bruns]
    cconfigs = [r.get("testConfigurationSnapshot") for r in cruns]
    if None in bconfigs or None in cconfigs:
        warnings.append(
            "Historical configuration unavailable for at least one run; comparability unconfirmed."
        )
    if bconfigs != cconfigs:
        warnings.append(
            "Configuration differs: review workload, concurrency, duration, collectors, engine/debug settings."
        )
    if any(r.get("isDesktopTestRun") for r in bruns + cruns):
        warnings.append(
            "Desktop Load: no login process and no meaningful capacity/VSImax comparison."
        )
    metrics = config.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        raise ToolkitError("Configure at least one explicitly defined metric.")
    results = []
    for metric in metrics:
        table = metric.get("table")
        if table not in ("measurements", "session_metrics"):
            raise ToolkitError("Only timer and session observation comparisons are supported.")
        field = "duration" if table == "measurements" else "measurement"
        if metric.get("value_field") != field or not metric.get("unit"):
            raise ToolkitError("Metric requires its contract value_field and an explicit unit.")
        if metric.get("semantics") not in ("duration", "resource", "status"):
            raise ToolkitError("Declare duration, resource or status semantics.")
        if metric.get("direction") not in ("lower", "higher", "neutral"):
            raise ToolkitError("Declare lower, higher or neutral metric direction.")
        if metric.get("semantics") == "status":
            raise ToolkitError(
                "Status sentinel values are categorical; arithmetic comparison refused."
            )
        match = metric.get("match")
        if not isinstance(match, dict) or not match:
            raise ToolkitError("Specify exact metric identity fields in match.")
        group_by = metric.get("group_by", [])
        if table == "session_metrics" and not {"instance", "fieldName", "unit"}.issubset(group_by):
            raise ToolkitError("Session metrics must group by instance, fieldName and unit.")
        groups: list[dict[tuple[Any, ...], dict[str, Any]]] = []
        for directory, _manifest, scenario in sides:
            buckets: dict[tuple[Any, ...], dict[str, Any]] = {}
            for row in load_table(directory, table):
                if row.get("testRunId") not in scenario["ids"] or any(
                    row.get(k) != v for k, v in match.items()
                ):
                    continue
                key = tuple(row.get(k) for k in group_by)
                bucket = buckets.setdefault(key, {"values": [], "missing": 0, "sessions": set()})
                if numeric(row.get(field)):
                    # Never convert units silently.
                    if table == "session_metrics" and row.get("unit") != metric["unit"]:
                        raise ToolkitError("Source unit differs from configured metric unit.")
                    if row[field] in metric.get("exclude_values", []):
                        bucket["missing"] += 1
                    else:
                        bucket["values"].append(row[field])
                else:
                    bucket["missing"] += 1
                session = row.get("userSessionId", row.get("userSessionKey"))
                if session:
                    bucket["sessions"].add(session)
            groups.append(buckets)
        for key in sorted(set(groups[0]) | set(groups[1]), key=str) or [()]:
            b, c = [g.get(key, {"values": [], "missing": 0, "sessions": set()}) for g in groups]
            bv = statistics.fmean(b["values"]) if b["values"] else None
            cv = statistics.fmean(c["values"]) if c["values"] else None
            delta = cv - bv if bv is not None and cv is not None else None
            relative = (
                delta / abs(bv) * 100 if delta is not None and bv is not None and bv != 0 else None
            )
            warning = None
            if bv is None or cv is None:
                warning = "Unmatched or unavailable measurements; no delta calculated."
            elif bv == 0:
                warning = "Zero baseline; relative change undefined."
            if len(b["values"]) != len(c["values"]):
                warnings.append("Unequal metric sample coverage: " + str(metric.get("name")))
            direction = metric["direction"]
            interpretation = "unavailable" if delta is None else "neutral"
            if delta is not None and delta != 0 and direction != "neutral":
                interpretation = "improved" if (delta < 0) == (direction == "lower") else "worsened"
            results.append(
                {
                    "metric": metric["name"],
                    "unit": metric["unit"],
                    "group": dict(zip(group_by, key, strict=False)),
                    "semantics": metric["semantics"],
                    "baseline_mean": bv,
                    "candidate_mean": cv,
                    "absolute_change": delta,
                    "relative_change_percent": relative,
                    "baseline_samples": len(b["values"]),
                    "candidate_samples": len(c["values"]),
                    "baseline_missing": b["missing"],
                    "candidate_missing": c["missing"],
                    "baseline_sessions": len(b["sessions"]),
                    "candidate_sessions": len(c["sessions"]),
                    "direction": direction,
                    "interpretation": interpretation,
                    "warning": warning,
                }
            )
    coverage = []
    for directory, manifest, scenario in sides:
        sessions = [
            r for r in load_table(directory, "sessions") if r.get("testRunId") in scenario["ids"]
        ]
        executions = [
            r for r in load_table(directory, "executions") if r.get("testRunId") in scenario["ids"]
        ]
        coverage.append(
            {
                "scenario": scenario["label"],
                "sessions": len(sessions),
                "executions": len(executions),
                "execution_failures": sum(r.get("state") == "endedWithErrors" for r in executions),
                "unended_executions": sum(r.get("state") == "created" for r in executions),
                "execution_state_unknown": sum(
                    r.get("state") not in ("ended", "endedWithErrors", "created")
                    for r in executions
                ),
                "sessions_without_executions": sum(
                    not any(e.get("userSessionId") == r.get("id") for e in executions)
                    for r in sessions
                ),
                "login_states": {
                    str(state): sum(r.get("loginState") == state for r in sessions)
                    for state in set(r.get("loginState") for r in sessions)
                },
                "completeness": manifest["status"],
            }
        )
    return {
        "schema_version": "comparison-result/1",
        "baseline": config["baseline"],
        "candidate": config["candidate"],
        "test_type": bm["selection"]["test_type"],
        "metrics": results,
        "coverage": coverage,
        "warnings": sorted(set(warnings)),
        "source_manifests": [bm, cm],
        "source_captures": [str(baseline.resolve()), str(candidate.resolve())],
    }
