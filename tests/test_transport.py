import json

import httpx
import pytest

from le_results.client import Client
from le_results.errors import ToolkitError
from le_results.profiles import Profile

PROFILE = Profile("test", "https://appliance.example.com")


def client(handler, **kwargs):
    return Client(
        PROFILE,
        "offline-fake-token",
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
        **kwargs,
    )


@pytest.mark.parametrize("status", [301, 302, 307, 308, 401, 403, 404, 500])
def test_error_body_and_redirect_never_exposed(status):
    requests = []

    def respond(req):
        requests.append(req)
        return httpx.Response(
            status, headers={"Location": "https://evil.example/"}, text="offline-fake-token"
        )

    with client(respond) as c:
        with pytest.raises(ToolkitError) as error:
            c.get("system/version")
    assert len(requests) == 1
    assert "offline-fake-token" not in str(error.value)
    assert error.value.status == status


def test_429_retry_after_and_bound():
    delays, calls = [], []

    def respond(req):
        calls.append(req)
        return (
            httpx.Response(429, headers={"Retry-After": "2"})
            if len(calls) == 1
            else httpx.Response(200, json={"version": "synthetic"})
        )

    with Client(PROFILE, "fake", transport=httpx.MockTransport(respond), sleep=delays.append) as c:
        assert c.get("system/version") == {"version": "synthetic"}
    assert delays == [2]
    with client(lambda _: httpx.Response(429, headers={"Retry-After": "60"})) as c:
        with pytest.raises(ToolkitError, match="bounded wait"):
            c.get("system/version")


def test_timeout_bounded_safe():
    calls = []

    def fail(req):
        calls.append(req)
        raise httpx.ReadTimeout("offline-fake-token", request=req)

    with client(fail) as c:
        with pytest.raises(ToolkitError, match="timed out") as error:
            c.get("system/version")
    assert len(calls) == 3
    assert "offline-fake-token" not in str(error.value)


def test_invalid_ca_is_actionable(tmp_path):
    bad = tmp_path / "ca.pem"
    bad.write_text("not a certificate")
    with pytest.raises(ToolkitError, match="CA bundle"):
        Client(Profile("p", PROFILE.origin, ca_bundle=str(bad)), "fake")


def test_null_not_empty():
    with client(lambda _: httpx.Response(200, content=b"null")) as c:
        with pytest.raises(ToolkitError, match="null"):
            c.get("system/version")


def test_destination_and_queries_allowlisted():
    with client(lambda _: pytest.fail("must not make request")) as c:
        for path in [
            "https://evil.example",
            "../system/version",
            "tests/123/start",
            "system/version?token=bad",
        ]:
            with pytest.raises(ToolkitError):
                c.get(path)
        with pytest.raises(ToolkitError):
            c.get("system/version", {"token": "not allowed"})


def test_redaction_of_reflected_secret_and_authorization():
    with client(
        lambda _: httpx.Response(
            200, json={"message": "offline-fake-token Bearer abc", "password": "private"}
        )
    ) as c:
        data = c.get("system/version")
    assert "offline-fake-token" not in json.dumps(data)
    assert "abc" not in json.dumps(data)
    assert data["password"] == "[REDACTED]"


def test_multi_page_offsets_and_final_page():
    offsets = []

    def respond(req):
        offset = int(req.url.params["offset"])
        offsets.append(offset)
        return httpx.Response(
            200,
            json={
                "items": [{"id": x} for x in range(offset, min(offset + 2, 5))],
                "offset": offset,
                "totalCount": 5,
            },
        )

    with client(respond, page_size=2) as c:
        assert [r["id"] for r in c.pages("tests")] == list(range(5))
    assert offsets == [0, 2, 4]


@pytest.mark.parametrize(
    "envelope",
    [
        {"items": None, "offset": 0},
        {"items": [], "offset": 1},
        {"items": [], "offset": 0, "totalCount": 3},
        {"items": [None], "offset": 0},
        {"items": [], "offset": 0, "totalCount": "0"},
    ],
)
def test_bad_or_truncated_envelope_fails(envelope):
    with client(lambda _: httpx.Response(200, json=envelope)) as c:
        with pytest.raises(ToolkitError):
            c.pages("tests")


def test_failed_later_page_not_successful_empty():
    saved = []

    def respond(req):
        if req.url.params["offset"] == "0":
            return httpx.Response(
                200, json={"items": [{"id": 1}, {"id": 2}], "offset": 0, "totalCount": 4}
            )
        return httpx.Response(403)

    with client(respond, page_size=2) as c:
        with pytest.raises(ToolkitError, match="403"):
            c.pages("tests", on_page=lambda i, data: saved.append(data))
    assert len(saved) == 1 and len(saved[0]["items"]) == 2


def test_deadline_prevents_request():
    with client(lambda _: pytest.fail("deadline must stop requests"), deadline_seconds=-1) as c:
        with pytest.raises(ToolkitError, match="deadline"):
            c.get("system/version")
