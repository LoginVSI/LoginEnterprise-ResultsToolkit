import sys

import httpx
import pytest

from le_results import cli
from le_results.client import Client
from le_results.evidence import verify_capture
from le_results.profiles import Profile
from le_results.selection import Selection
from le_results.synthetic import BASE


def test_real_partial_capture_exits_two_and_preserves_failed_endpoint(
    monkeypatch, tmp_path, capsys
):
    selection = tmp_path / "selection.json"
    Selection("LoadTest", [BASE]).write(selection)
    token = "offline-fake-token"

    def respond(request):
        path = request.url.path
        if path.endswith("/events"):
            return httpx.Response(500, text=token)
        if path.endswith("/test-runs/" + BASE):
            return httpx.Response(
                200,
                json={
                    "id": BASE,
                    "type": "LoadTest",
                    "finished": "2026-09-01T00:00:00Z",
                    "testConfigurationSnapshot": {"sessionMetricsEnabled": False},
                },
            )
        if "/system/" in path:
            return httpx.Response(200, json={"version": "synthetic"})
        return httpx.Response(200, json={"items": [], "offset": 0, "totalCount": 0})

    monkeypatch.setattr(
        cli.ProfileStore, "get", lambda *args: Profile("fixture", "https://appliance.example.com")
    )
    monkeypatch.setattr(cli, "resolve_token", lambda _: token)
    monkeypatch.setattr(
        cli,
        "Client",
        lambda *args, **kwargs: Client(*args, **kwargs, transport=httpx.MockTransport(respond)),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "le-results",
            "export",
            "--profile",
            "fixture",
            "--selection",
            str(selection),
            "--out",
            str(tmp_path / "capture"),
        ],
    )
    assert cli.main() == 2
    output = capsys.readouterr()
    assert token not in output.out + output.err
    manifest = verify_capture(tmp_path / "capture")
    assert manifest["status"] == "partial"
    assert any(
        endpoint["status"] == "failed" and endpoint["path"].endswith("/events")
        for endpoint in manifest["endpoints"]
    )


def test_real_recommendation_budget_failure_exits_two_with_artifact(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        cli.ProfileStore, "get", lambda *args: Profile("fixture", "https://appliance.example.com")
    )
    monkeypatch.setattr(cli, "resolve_token", lambda _: "offline-fake-token")

    def bounded(*args, **kwargs):
        kwargs["max_requests"] = 1
        return Client(
            *args,
            **kwargs,
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"items": [], "offset": 0, "totalCount": 0})
            ),
        )

    monkeypatch.setattr(cli, "Client", bounded)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "le-results",
            "recommend",
            "--profile",
            "fixture",
            "--out",
            str(tmp_path / "recommend.json"),
        ],
    )
    assert cli.main() == 2
    output = capsys.readouterr().out
    assert '"bounds_exhausted": true' in output and '"status": "partial"' in output
    assert (tmp_path / "recommend.json").exists()


@pytest.mark.parametrize("number", ["NaN", "Infinity", "1e999"])
def test_nonfinite_discovery_preserves_failed_recommendations(monkeypatch, tmp_path, number):
    from le_results.recommend import recommend

    with Client(
        Profile("fixture", "https://appliance.example.com"),
        "offline-fake-token",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, content='{"items": [], "offset": 0, "totalCount": ' + number + "}"
            )
        ),
    ) as client:
        result = recommend(client)
    assert result["status"] == "partial"
    assert all(model["discovery_status"] == "failed" for model in result["models"].values())
    assert all(
        model["diagnostic"]["code"] == "source_schema" for model in result["models"].values()
    )
