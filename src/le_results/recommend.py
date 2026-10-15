"""Bounded suggestions based on configuration and coverage, never performance rank."""

from datetime import UTC, datetime, timedelta
from typing import Any

from .client import Client
from .contracts import identifier, route
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


def recommend(
    client: Client,
    limit: int = 20,
    candidates: int = 5,
    continuous_candidates: int = 5,
) -> dict[str, Any]:
    if not 1 <= limit <= 100 or not 1 <= candidates <= 5 or not 1 <= continuous_candidates <= 40:
        raise ToolkitError(
            "Use discovery limit 1-100, run details 1-5 and Continuous details 1-40."
        )
    now = datetime.now(UTC)
    recent_start = now - timedelta(hours=24)
    result: dict[str, Any] = {
        "schema_version": "recommendations/1",
        "bounded": True,
        "limit_per_model": limit,
        "candidate_details_per_model": candidates,
        "continuous_candidate_details": continuous_candidates,
        "recent_observation_window": {"start": recent_start.isoformat(), "end": now.isoformat()},
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
        try:
            rows = client.pages(
                "tests" if kind == "ContinuousTest" else "tests/test-runs", query, limit=limit
            )
        except ToolkitError as exc:
            result["models"][kind] = {
                "discovery_status": "failed",
                "diagnostic": exc.diagnostic(),
                "selection": [],
                "reason": "Metadata acquisition failed; no empty-success or selection inferred.",
            }
            continue
        completed = (
            rows
            if kind == "ContinuousTest"
            else [r for r in rows if r.get("state") == "completed" and r.get("finished")]
        )
        if kind == "ContinuousTest":
            completed = sorted(
                completed,
                key=lambda r: (
                    r.get("isEnabled") is True,
                    r.get("lastModified") if isinstance(r.get("lastModified"), str) else "",
                ),
                reverse=True,
            )
        details = []
        detail_outcomes: list[dict[str, Any]] = []
        if kind == "ApplicationTest":
            failed = next(
                (r for r in completed if r.get("result") not in (None, "successful")), None
            )
            if failed and failed not in completed[:candidates]:
                completed = [*completed[: max(0, candidates - 1)], failed]
        for row in completed[: continuous_candidates if kind == "ContinuousTest" else candidates]:
            try:
                candidate_id = identifier(row.get("id"))
                detail = client.get(
                    route(
                        "tests/{id}" if kind == "ContinuousTest" else "test-runs/{id}",
                        id=candidate_id,
                    ),
                    {
                        "include": "all"
                        if kind == "ContinuousTest"
                        else "testRunConfigurationSnapshot"
                    },
                )
                if (
                    not isinstance(detail, dict)
                    or detail.get("id") != row["id"]
                    or detail.get("type") != kind
                ):
                    raise ToolkitError(
                        "Candidate detail identity/type differs from discovery.",
                        code="source_identity",
                    )
                details.append(detail)
                detail_outcomes.append({"id": candidate_id, "status": "complete"})
            except ToolkitError as exc:
                detail_outcomes.append(
                    {"id": row.get("id"), "status": "failed", "diagnostic": exc.diagnostic()}
                )
                if exc.code in ("deadline", "request_bound"):
                    break
        model: dict[str, Any] = {
            "discovery": rows,
            "discovery_status": "complete bounded subset",
            "details": details,
            "detail_outcomes": detail_outcomes,
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
                        if r.get("result") not in (None, "successful")
                        or any(
                            isinstance(r.get(k), dict)
                            and type(r[k].get("successCount")) in (int, float)
                            and type(r[k].get("totalCount")) in (int, float)
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
            model["summary_enabled_states"] = enabled_states(rows)
            model["definition_enabled_states"] = enabled_states(details)
            probes = []
            for detail in details:
                session_outcome: dict[str, Any] = {"status": "complete"}
                try:
                    sessions = client.pages(
                        route("test-runs/{id}/user-sessions", id=detail["id"]),
                        {"direction": "desc"},
                        limit=5,
                    )
                    if not sessions:
                        session_outcome["status"] = "empty"
                except ToolkitError as exc:
                    sessions = []
                    session_outcome = {"status": "failed", "diagnostic": exc.diagnostic()}
                observations = []
                for endpoint in ("measurements", "events", "resources"):
                    path = (
                        route("user-session-metrics/{id}", id=detail["id"])
                        if endpoint == "resources"
                        else route("test-runs/{id}/" + endpoint, id=detail["id"])
                    )
                    observation_query: dict[str, Any] = {
                        "count": 1,
                        "offset": 0,
                        "direction": "desc",
                        "includeTotalCount": "true",
                    }
                    if endpoint in ("resources", "events"):
                        observation_query["orderBy"] = "timestamp"
                    try:
                        envelope = client.get(path, observation_query)
                        if not isinstance(envelope, dict):
                            raise ToolkitError(
                                "Unexpected one-record observation envelope.", code="api_contract"
                            )
                        items = envelope.get("items")
                        if (
                            not isinstance(items, list)
                            or len(items) > 1
                            or any(not isinstance(item, dict) for item in items)
                        ):
                            raise ToolkitError("Unexpected one-record observation envelope.")
                        timestamp = items[0].get("timestamp") if items else None
                        observed = None
                        if isinstance(timestamp, str):
                            try:
                                instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                                if instant.tzinfo is not None:
                                    observed = recent_start <= instant <= now
                            except ValueError:
                                pass
                        observations.append(
                            {
                                "endpoint": endpoint,
                                "status": "complete" if items else "empty",
                                "total_count": envelope.get("totalCount"),
                                "sample_timestamp": timestamp,
                                "ordering": "timestamp descending"
                                if endpoint in ("resources", "events")
                                else "server default descending; latest ordering not established",
                                "observed_in_recent_window": observed,
                                "observation_query": observation_query,
                            }
                        )
                    except ToolkitError as exc:
                        observations.append(
                            {
                                "endpoint": endpoint,
                                "status": "failed",
                                "diagnostic": exc.diagnostic(),
                                "observation_query": observation_query,
                            }
                        )
                probes.append(
                    {
                        "test_id": detail["id"],
                        "configured_enabled": detail.get("isEnabled"),
                        "retained_session_subset": sessions,
                        "session_probe_outcome": session_outcome,
                        "observation_probes": observations,
                        "recent_observations": any(
                            p.get("observed_in_recent_window") is True for p in observations
                        ),
                    }
                )
            model["session_probes"] = probes
            useful = next(
                (probe for probe in probes if probe["recent_observations"]), None
            ) or next((probe for probe in probes if probe["retained_session_subset"]), None)
            if useful:
                model.update(
                    selection=[useful["test_id"]],
                    reason="Recent source observations found; freeze a window around observation timestamps. Collection health remains unconfirmed."
                    if useful["recent_observations"]
                    else "Retained sessions found; inspect observation timestamps before selecting a window. Collection health remains unconfirmed.",
                )
            if not any(probe["recent_observations"] for probe in probes):
                model["next_action"] = (
                    "Resolve an existing test ID or review probe failures and bounds. No recent observations were established in these probes; do not infer stopped collection from configuration or session start dates."
                )
        result["models"][kind] = model
    result["requests_used"] = client.request_count
    diagnostics = []
    for model in result["models"].values():
        if model.get("discovery_status") == "failed":
            diagnostics.append(model["diagnostic"])
        diagnostics.extend(
            o["diagnostic"] for o in model.get("detail_outcomes", []) if o["status"] == "failed"
        )
        for probe in model.get("session_probes", []):
            if probe["session_probe_outcome"]["status"] == "failed":
                diagnostics.append(probe["session_probe_outcome"]["diagnostic"])
            diagnostics.extend(
                o["diagnostic"] for o in probe["observation_probes"] if o["status"] == "failed"
            )
    result["failed_probes"] = len(diagnostics)
    result["bounds_exhausted"] = any(
        d["code"] in ("deadline", "request_bound") for d in diagnostics
    )
    result["status"] = "partial" if diagnostics else "complete bounded recommendations"
    if result["bounds_exhausted"]:
        result["limitations"].append(
            "Request/deadline bounds exhausted; narrow the screening scope before retrying. Unscreened candidates remain unknown."
        )
    return result


def enabled_states(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Missing or malformed configuration is unknown, never false."""
    return {
        "enabled": sum(r.get("isEnabled") is True for r in rows),
        "disabled": sum(r.get("isEnabled") is False for r in rows),
        "unknown": sum(type(r.get("isEnabled")) is not bool for r in rows),
    }
