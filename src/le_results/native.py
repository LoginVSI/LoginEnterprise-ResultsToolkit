"""Native whole-run scores from the Load result overview.

Rows keep vendor values, result IDs and states exactly as returned. This module never
computes, averages or weights EUX/VSImax; aggregate-interval rows live in the ``eux`` table.
"""

from typing import Any

from .errors import ToolkitError

GRAIN = "native_whole_run"
AGGREGATE_GRAIN = "aggregate_interval_vendor"
ENDPOINT = "load-test-run-overview/{id}"


def _result_row(
    entry: dict[str, Any], group: str, item: Any, state: Any, capture_id: str
) -> dict[str, Any]:
    if not isinstance(item, dict) or not isinstance(item.get("resultId"), str):
        raise ToolkitError("Native overview result lacks a resultId.", code="source_identity")
    return {
        "testRunId": entry["testRunId"],
        "testName": entry.get("testName"),
        "counter": entry.get("counter"),
        "isBase": entry.get("isBase"),
        "run_state": entry.get("state"),
        "test_result": entry.get("testResult"),
        "result_group": group,
        "resultId": item["resultId"],
        "value": item.get("value"),
        "state": state,
        "source_difference_from_base": item.get("differenceFromBase"),
        "score_grain": GRAIN,
        "provenance": "native_overview",
        "source_endpoint": ENDPOINT,
        "capture_id": capture_id,
    }


def flatten_overview(overview: Any, run_id: str, capture_id: str) -> list[dict[str, Any]]:
    """One row per native result ID for the selected run; absent values stay null."""
    entries = overview.get("results") if isinstance(overview, dict) else None
    if not isinstance(entries, list):
        raise ToolkitError("Native overview response is malformed.", code="source_identity")
    if any(not isinstance(e, dict) or e.get("testRunId") != run_id for e in entries) or not any(
        isinstance(e, dict) and e.get("testRunId") == run_id for e in entries
    ):
        raise ToolkitError(
            "Native overview identity differs from selected run.", code="source_identity"
        )
    rows: list[dict[str, Any]] = []
    for entry in entries:
        results = entry.get("results") or {}
        performance = results.get("performance") or {}
        for item in performance.get("results") or []:
            rid = item.get("resultId") if isinstance(item, dict) else None
            state = (
                performance.get("euxState")
                if isinstance(rid, str) and rid.startswith("eux_")
                else performance.get("vsiMaxState")
                if rid == "vsi_max"
                else None
            )
            rows.append(_result_row(entry, "performance", item, state, capture_id))
        for item in results.get("loginTime") or []:
            rows.append(_result_row(entry, "loginTime", item, None, capture_id))
        total = (results.get("appPerformanceResult") or {}).get("totalAppPerformance")
        if total:
            rows.append(_result_row(entry, "appPerformance", total, None, capture_id))
    return rows
