import httpx

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

    def respond(request):
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
        return httpx.Response(
            200,
            json={
                "id": path.rsplit("/", 1)[-1],
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
