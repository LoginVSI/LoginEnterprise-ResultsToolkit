import gzip

import httpx
import pytest

from le_results.client import Client
from le_results.errors import ToolkitError
from le_results.profiles import Profile
from le_results.synthetic import BASE


@pytest.mark.parametrize("status", [200, 302, 401, 403, 404, 500])
def test_native_pdf_get_status_and_no_redirect(status):
    requests = []

    def respond(request):
        requests.append(request)
        assert request.method == "GET"
        assert not request.content
        if not request.url.path.endswith("/pdf"):
            return httpx.Response(
                200,
                json={"id": BASE, "type": "ApplicationTest", "finished": "2026-09-01T00:00:00Z"},
            )
        return httpx.Response(
            status, content=b"%PDF-1.7\nsynthetic", headers={"Location": "https://other.example/"}
        )

    with Client(
        Profile("test", "https://appliance.example.com"),
        "offline-secret-token",
        transport=httpx.MockTransport(respond),
        retries=0,
    ) as client:
        if status == 200:
            assert client.get_application_pdf(BASE).startswith(b"%PDF-")
        else:
            with pytest.raises(ToolkitError) as error:
                client.get_application_pdf(BASE)
            assert error.value.status == status
            assert "offline-secret-token" not in str(error.value)
    assert len(requests) == 2


@pytest.mark.parametrize(
    "body,maximum,code",
    [
        (b"%PDF-" + b"x" * 100, 20, "response_bound"),
        (b"not a PDF", 100, "api_contract"),
        (b"%PDF-offline-secret-token", 100, "credential_reflection"),
    ],
)
def test_native_pdf_bounds_contract_and_reflection(body, maximum, code):
    def respond(request):
        if request.url.path.endswith("/pdf"):
            return httpx.Response(200, content=body)
        return httpx.Response(
            200, json={"id": BASE, "type": "ApplicationTest", "finished": "2026-09-01T00:00:00Z"}
        )

    with Client(
        Profile("test", "https://appliance.example.com"),
        "offline-secret-token",
        transport=httpx.MockTransport(respond),
    ) as client:
        with pytest.raises(ToolkitError) as error:
            client.get_application_pdf(BASE, maximum)
    assert error.value.code == code
    assert "offline-secret-token" not in str(error.value)


def test_native_pdf_rejects_non_application_without_requesting_report():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200, json={"id": BASE, "type": "LoadTest", "finished": "2026-09-01T00:00:00Z"}
        )

    with Client(
        Profile("test", "https://appliance.example.com"),
        "fake",
        transport=httpx.MockTransport(respond),
    ) as client:
        with pytest.raises(ToolkitError, match="Application"):
            client.get_application_pdf(BASE)
    assert len(calls) == 1


def test_compressed_pdf_is_decoded_once_and_invalid_encoding_is_safe():
    payload = b"%PDF-1.7\nsynthetic compressed report"

    def respond(request):
        if not request.url.path.endswith("/pdf"):
            return httpx.Response(
                200,
                json={"id": BASE, "type": "ApplicationTest", "finished": "2026-09-01T00:00:00Z"},
            )
        return httpx.Response(
            200,
            stream=httpx.ByteStream(gzip.compress(payload)),
            headers={"Content-Encoding": "gzip"},
        )

    with Client(
        Profile("test", "https://appliance.example.com"),
        "fake",
        transport=httpx.MockTransport(respond),
    ) as client:
        assert client.get_application_pdf(BASE) == payload

    def invalid(request):
        if not request.url.path.endswith("/pdf"):
            return respond(request)
        return httpx.Response(
            200,
            stream=httpx.ByteStream(b"secret malformed encoding"),
            headers={"Content-Encoding": "gzip"},
        )

    with Client(
        Profile("test", "https://appliance.example.com"),
        "fake",
        transport=httpx.MockTransport(invalid),
    ) as client:
        with pytest.raises(ToolkitError) as error:
            client.get_application_pdf(BASE)
    assert error.value.code == "response_encoding" and "secret" not in str(error.value)


def test_malformed_run_payload_is_contract_failure():
    with Client(
        Profile("test", "https://appliance.example.com"),
        "fake",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])),
    ) as client:
        with pytest.raises(ToolkitError, match="Application"):
            client.get_application_pdf(BASE)
