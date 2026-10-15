from datetime import UTC, datetime, timedelta

import httpx
import pytest

from le_results.client import Client
from le_results.profiles import Profile
from le_results.recommend import compatible, recommend
from le_results.synthetic import BASE, CANDIDATE


def test_candidate_compatibility_does_not_rank_performance():
    config = {
        "workloadSteps": [],
        "numberOfSessions": 6,
        "testDurationInMinutes": 30,
        "connectorProperties": {},
        "applicationDebugModeEnabled": False,
    }
    assert compatible({"testConfigurationSnapshot": config}, {"testConfigurationSnapshot": config})
    assert not compatible({"testConfigurationSnapshot": config}, {})
    changed = {**config, "numberOfSessions": 7}
    assert not compatible(
        {"testConfigurationSnapshot": config}, {"testConfigurationSnapshot": changed}
    )


def test_recommend_queries_match_contract_and_failed_application_retained():
    config = {
        "workloadSteps": [],
        "numberOfSessions": 6,
        "testDurationInMinutes": 30,
        "connectorProperties": {},
        "applicationDebugModeEnabled": False,
    }

    active_kind = "LoadTest"

    def respond(request):
        nonlocal active_kind
        path = request.url.path
        query = request.url.params
        if path.endswith("/tests"):
            assert query["orderBy"] == "name"
            return httpx.Response(
                200,
                json={
                    "items": [{"id": BASE, "type": "ContinuousTest", "isEnabled": False}],
                    "offset": 0,
                    "totalCount": 1,
                },
            )
        if path.endswith("/tests/test-runs"):
            active_kind = query["testType"][0].upper() + query["testType"][1:]
            assert query["orderBy"] == "created"
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"id": v, "state": "completed", "finished": "2026-09-01T00:00:00Z"}
                        for v in (CANDIDATE, BASE)
                    ],
                    "offset": 0,
                    "totalCount": 2,
                },
            )
        if path.endswith("/user-sessions"):
            assert "orderBy" not in query
            return httpx.Response(200, json={"items": [], "offset": 0, "totalCount": 0})
        if path.endswith(("/events", "/measurements")) or "/user-session-metrics/" in path:
            return httpx.Response(200, json={"items": [], "offset": 0, "totalCount": 0})
        return httpx.Response(
            200,
            json={
                "id": path.rsplit("/", 1)[-1],
                "type": "ContinuousTest" if "/tests/" in path else active_kind,
                "testConfigurationSnapshot": config,
                "appExecutionCounts": {
                    "successCount": 0 if path.endswith(BASE) else 1,
                    "totalCount": 1,
                },
            },
        )

    with Client(
        Profile("test", "https://appliance.example.com"),
        "fake",
        transport=httpx.MockTransport(respond),
    ) as client:
        result = recommend(client)
    assert result["models"]["LoadTest"]["selection"] == [BASE, CANDIDATE]
    assert result["models"]["ApplicationTest"]["selection"] == [CANDIDATE, BASE]
    assert result["models"]["ContinuousTest"]["enabled_in_subset"] == 0
    assert result["models"]["ContinuousTest"]["definition_enabled_states"]["unknown"] == 1


def test_recent_observations_outweigh_old_session_and_disabled_definition():
    timestamp = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()

    def respond(request):
        path = request.url.path
        if path.endswith("/tests"):
            return httpx.Response(200, json={"items": [{"id": BASE}], "offset": 0, "totalCount": 1})
        if path.endswith("/tests/test-runs"):
            return httpx.Response(200, json={"items": [], "offset": 0, "totalCount": 0})
        if path.endswith("/tests/" + BASE):
            return httpx.Response(
                200,
                json={
                    "id": BASE,
                    "type": "ContinuousTest",
                    "isEnabled": False,
                    "lastModified": "2020-01-01T00:00:00Z",
                },
            )
        if path.endswith("/user-sessions"):
            return httpx.Response(
                200,
                json={
                    "items": [{"id": CANDIDATE, "created": "2020-01-01T00:00:00Z"}],
                    "offset": 0,
                    "totalCount": 1,
                },
            )
        if "/user-session-metrics/" in path:
            assert request.url.params["orderBy"] == "timestamp"
            return httpx.Response(500)
        return httpx.Response(
            200, json={"items": [{"timestamp": timestamp}], "offset": 0, "totalCount": 20000}
        )

    with Client(
        Profile("test", "https://appliance.example.com"),
        "fake",
        transport=httpx.MockTransport(respond),
        retries=0,
    ) as client:
        result = recommend(client)
    model = result["models"]["ContinuousTest"]
    assert model["summary_enabled_states"] == {"enabled": 0, "disabled": 0, "unknown": 1}
    assert model["definition_enabled_states"] == {"enabled": 0, "disabled": 1, "unknown": 0}
    assert model["selection"] == [BASE]
    assert model["session_probes"][0]["recent_observations"] is True
    assert model["session_probes"][0]["observation_probes"][2]["status"] == "failed"
    assert "next_action" not in model


def test_missing_and_future_timestamps_do_not_prove_recent_collection():
    def respond(request):
        path = request.url.path
        if path.endswith("/tests/test-runs") or path.endswith("/user-sessions"):
            return httpx.Response(200, json={"items": [], "offset": 0, "totalCount": 0})
        if path.endswith("/tests"):
            return httpx.Response(200, json={"items": [{"id": BASE}], "offset": 0, "totalCount": 1})
        if path.endswith("/tests/" + BASE):
            return httpx.Response(
                200, json={"id": BASE, "type": "ContinuousTest", "isEnabled": True}
            )
        timestamp = "2099-01-01T00:00:00Z" if path.endswith("/events") else "bad"
        return httpx.Response(
            200, json={"items": [{"timestamp": timestamp}], "offset": 0, "totalCount": 1}
        )

    with Client(
        Profile("test", "https://appliance.example.com"),
        "fake",
        transport=httpx.MockTransport(respond),
    ) as client:
        model = recommend(client)["models"]["ContinuousTest"]
    assert model["selection"] == []
    assert not model["session_probes"][0]["recent_observations"]
    assert "existing test ID" in model["next_action"]


def test_recommendation_budget_failure_is_visible_and_not_empty_success():
    with Client(
        Profile("test", "https://appliance.example.com"),
        "fake",
        max_requests=1,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"items": [], "offset": 0, "totalCount": 0})
        ),
    ) as client:
        result = recommend(client)
    assert result["status"] == "partial" and result["bounds_exhausted"]
    assert result["models"]["ApplicationTest"]["discovery_status"] == "failed"
    assert result["requests_used"] == 1


@pytest.mark.parametrize("envelope", [[], {"items": [42]}, {"items": "wrong"}])
def test_malformed_probe_is_recorded_as_failed(envelope):
    def respond(request):
        path = request.url.path
        if path.endswith("/tests/test-runs") or path.endswith("/user-sessions"):
            return httpx.Response(200, json={"items": [], "offset": 0, "totalCount": 0})
        if path.endswith("/tests"):
            return httpx.Response(200, json={"items": [{"id": BASE}], "offset": 0, "totalCount": 1})
        if path.endswith("/tests/" + BASE):
            return httpx.Response(200, json={"id": BASE, "type": "ContinuousTest"})
        return httpx.Response(200, json=envelope)

    with Client(
        Profile("test", "https://appliance.example.com"),
        "fake",
        transport=httpx.MockTransport(respond),
    ) as client:
        result = recommend(client)
    assert result["failed_probes"] == 3 and result["status"] == "partial"


@pytest.mark.parametrize("identity", [None, 123, {"bad": "id"}])
def test_malformed_discovery_id_becomes_failed_detail(identity):
    def respond(request):
        if request.url.path.endswith("/tests/test-runs"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"id": identity, "state": "completed", "finished": "2026-01-01T00:00:00Z"}
                    ],
                    "offset": 0,
                    "totalCount": 1,
                },
            )
        return httpx.Response(200, json={"items": [], "offset": 0, "totalCount": 0})

    with Client(
        Profile("test", "https://appliance.example.com"),
        "fake",
        transport=httpx.MockTransport(respond),
    ) as client:
        result = recommend(client)
    assert result["status"] == "partial"
    assert result["models"]["LoadTest"]["detail_outcomes"][0]["status"] == "failed"
