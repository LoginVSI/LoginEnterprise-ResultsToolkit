"""Bounded suggestions based on configuration and coverage, never performance rank."""

from typing import Any

from .client import Client
from .contracts import route
from .errors import ToolkitError

COMPATIBILITY_KEYS = (
    "workloadSteps",
    "numberOfSessions",
    "testDurationInMinutes",
    "rampUpDurationInMinutes",
    "rampDownDurationInMinutes",
    "euxEnabled",
    "sessionMetricsEnabled",
    "sessionMetricDefinitions",
    "sessionMetricScheduleRate",
    "applicationDebugModeEnabled",
    "connectorProperties",
    "productVersion",
    "environmentId",
    "launcherGroups",
    "accountGroups",
)


def compatible(left: dict[str, Any], right: dict[str, Any]) -> bool:
    a, b = left.get("testConfigurationSnapshot"), right.get("testConfigurationSnapshot")
    return (
        isinstance(a, dict)
        and isinstance(b, dict)
        and a.get("workloadSteps") is not None
        and all(a.get(k) == b.get(k) for k in COMPATIBILITY_KEYS)
        and all(
            k in a and k in b
            for k in (
                "numberOfSessions",
                "testDurationInMinutes",
                "connectorProperties",
                "applicationDebugModeEnabled",
            )
        )
    )


def recommend(client: Client, limit: int = 20, candidates: int = 5) -> dict[str, Any]:
    if not 1 <= limit <= 100 or not 1 <= candidates <= 5:
        raise ToolkitError("Use discovery limit 1-100 and candidate details 1-5.")
    result: dict[str, Any] = {
        "schema_version": "recommendations/1",
        "bounded": True,
        "limit_per_model": limit,
        "candidate_details_per_model": candidates,
        "compatibility_keys": COMPATIBILITY_KEYS,
        "models": {},
        "limitations": [
            "Suggestions require capture/coverage review before comparison.",
            "Names do not establish OS identity or causality.",
            "Enabled state does not prove healthy active collection.",
        ],
    }
    for kind in ("LoadTest", "ApplicationTest", "ContinuousTest"):
        query = {"testType": kind[0].lower() + kind[1:], "direction": "desc", "orderBy": "created"}
        if kind == "ContinuousTest":
            query["orderBy"] = "name"  # TestSortKey has no created member.
        rows = client.pages(
            "tests" if kind == "ContinuousTest" else "tests/test-runs", query, limit=limit
        )
        completed = (
            rows
            if kind == "ContinuousTest"
            else [r for r in rows if r.get("state") == "completed" and r.get("finished")]
        )
        if kind == "ContinuousTest":
            completed = sorted(
                completed,
                key=lambda r: (r.get("isEnabled") is True, r.get("lastModified") or ""),
                reverse=True,
            )
        details = []
        if kind == "ApplicationTest":
            failed = next((r for r in completed if r.get("result") not in (None, "successful")), None)
            if failed and failed not in completed[:candidates]:
                completed = [*completed[:max(0, candidates - 1)], failed]
        for row in completed[:candidates]:
            details.append(
                client.get(
                    route(
                        "tests/{id}" if kind == "ContinuousTest" else "test-runs/{id}", id=row["id"]
                    ),
                    {
                        "include": "all"
                        if kind == "ContinuousTest"
                        else "testRunConfigurationSnapshot"
                    },
                )
            )
        model: dict[str, Any] = {
            "discovery": rows,
            "details": details,
            "selection": [],
            "reason": "No suitable candidate in bounded subset.",
        }
        if kind == "LoadTest":
            for index, latest in enumerate(details):
                earlier = next((r for r in details[index + 1 :] if compatible(r, latest)), None)
                if earlier:
                    model.update(
                        selection=[earlier["id"], latest["id"]],
                        reason="First compatible completed pair in recency order; no performance ranking.",
                    )
                    break
            if not model["selection"] and details:
                model.update(
                    selection=[details[0]["id"]],
                    reason="Completed diagnostic capture; no defensible pair in screened candidates.",
                )
        elif kind == "ApplicationTest":
            if details:
                model.update(
                    selection=[details[0]["id"]],
                    reason="Most recent completed result; inspect executions and failed logons as well as orchestration status.",
                )
                failure = next(
                    (
                        r
                        for r in details
                        if r.get("result") not in (None, "successful") or any(
                            isinstance(r.get(k), dict)
                            and r[k].get("successCount") is not None
                            and r[k].get("totalCount") is not None
                            and r[k]["successCount"] < r[k]["totalCount"]
                            for k in ("loginCounts", "appExecutionCounts")
                        )
                    ),
                    None,
                )
                if failure and failure["id"] not in model["selection"]:
                    model["selection"].append(failure["id"])
        else:
            model["enabled_in_subset"] = sum(r.get("isEnabled") is True for r in rows)
            probes = []
            for detail in details:
                sessions = client.pages(
                    route("test-runs/{id}/user-sessions", id=detail["id"]),
                    {"direction": "desc"},
                    limit=5,
                )
                probes.append(
                    {
                        "test_id": detail["id"],
                        "configured_enabled": detail.get("isEnabled"),
                        "recent_session_subset": sessions,
                    }
                )
            model["session_probes"] = probes
            useful = next((probe for probe in probes if probe["recent_session_subset"]), None)
            if useful:
                model.update(
                    selection=[useful["test_id"]],
                    reason="Retained session evidence found; freeze a window around recorded session timestamps. Health remains unconfirmed.",
                )
            if not model["enabled_in_subset"]:
                model["next_action"] = (
                    "Owner may create/start a small Continuous workload with session metrics and completed application steps, then provide the test ID. Toolkit will only read it."
                )
        result["models"][kind] = model
    result["requests_used"] = client.request_count
    return result
