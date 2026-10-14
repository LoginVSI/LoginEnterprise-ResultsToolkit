"""Real local HTTPS handshakes using synthetic certificates and fake credentials."""

import json
import ssl
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from le_results.client import Client
from le_results.diagnostics import approve_trust, doctor, inspect_certificate
from le_results.errors import ToolkitError
from le_results.profiles import Profile, ProfileStore
from le_results.tls import context, transport_error


def certificate(
    key,
    name,
    *,
    signer=None,
    issuer=None,
    ca=False,
    expired=False,
    hostname="localhost",
    purpose=ExtendedKeyUsageOID.SERVER_AUTH,
    key_usage=True,
):
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer or subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(now + timedelta(days=-1 if expired else 7))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key((signer or key).public_key()), False
        )
    )
    if key_usage:
        builder = builder.add_extension(
            x509.KeyUsage(True, False, True, False, False, ca, ca, False, False), True
        )
    if not ca:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(hostname)]), False
        )
        builder = builder.add_extension(x509.ExtendedKeyUsage([purpose]), False)
    return builder.sign(signer or key, hashes.SHA256())


@contextmanager
def server(
    tmp_path,
    *,
    self_signed=False,
    hostname="localhost",
    expired=False,
    purpose=ExtendedKeyUsageOID.SERVER_AUTH,
    ca_key_usage=True,
    self_issued=False,
    include_ca=True,
):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca = certificate(
        ca_key,
        "Synthetic leaf" if self_issued else "Synthetic root",
        ca=True,
        key_usage=ca_key_usage,
    )
    leaf = certificate(
        key,
        "Synthetic leaf",
        signer=None if self_signed else ca_key,
        issuer=None if self_signed else ca.subject,
        expired=expired,
        hostname=hostname,
        purpose=purpose,
    )
    pem = leaf.public_bytes(serialization.Encoding.PEM)
    chain = tmp_path / "server.pem"
    chain.write_bytes(
        pem
        + (b"" if self_signed or not include_ca else ca.public_bytes(serialization.Encoding.PEM))
    )
    keyfile = tmp_path / "server.key"
    keyfile.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    trust = tmp_path / "trust.pem"
    trust.write_bytes(pem if self_signed else ca.public_bytes(serialization.Encoding.PEM))
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            body = b'{"currentVersion":"synthetic"}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    secure = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    secure.load_cert_chain(chain, keyfile)
    http.socket = secure.wrap_socket(http.socket, server_side=True)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield (
            Profile(
                "local",
                f"https://localhost:{http.server_port}",
                ca_bundle=str(trust),
                approved_sha256=(
                    (leaf if self_signed else ca).fingerprint(hashes.SHA256()).hex().upper(),
                ),
            ),
            requests,
            leaf,
        )
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=3)


@pytest.mark.parametrize("self_signed", [False, True])
def test_verified_success_and_explicit_ca_false_self_signed_trust(tmp_path, self_signed):
    with server(tmp_path, self_signed=self_signed) as (profile, requests, leaf):
        with Client(profile, "synthetic-secret", retries=0) as client:
            assert client.get("system/version")["currentVersion"] == "synthetic"
        assert requests == ["/publicApi/v8-preview/system/version"]
        if self_signed:
            assert leaf.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"hostname": "other.example"}, "certificate_hostname"),
        ({"expired": True}, "certificate_expired"),
        ({"purpose": ExtendedKeyUsageOID.CLIENT_AUTH}, "certificate_purpose"),
    ],
)
def test_rejected_handshake_sends_no_http(tmp_path, kwargs, expected):
    with server(tmp_path, **kwargs) as (profile, requests, _):
        with Client(profile, "synthetic-secret", retries=0) as client:
            with pytest.raises(ToolkitError) as failure:
                client.get("system/version")
        assert failure.value.code == expected
        assert failure.value.verify_code is not None
        assert "synthetic-secret" not in json.dumps(failure.value.diagnostic())
        assert requests == []


def test_untrusted_rejected_and_inspection_never_sends_http_or_enrolls_trust(tmp_path, monkeypatch):
    with server(tmp_path, self_signed=True) as (profile, requests, _):
        untrusted = Profile(profile.name, profile.origin)
        with Client(untrusted, "synthetic-secret", retries=0) as client:
            with pytest.raises(ToolkitError) as failure:
                client.get("system/version")
        assert failure.value.code == "certificate_self_signed"
        monkeypatch.setattr(
            "le_results.diagnostics.Vault", lambda: pytest.fail("inspection must not access vault")
        )
        result = inspect_certificate(untrusted, tmp_path / "inspection")
        assert result["trusted"] is False and result["http_sent"] is False
        assert requests == []
        assert result["certificates"][0]["self_signed"] is True


def test_strict_missing_ca_key_usage_rejection(tmp_path):
    with server(tmp_path, ca_key_usage=False) as (profile, requests, _):
        with Client(profile, "synthetic-secret", retries=0) as client:
            with pytest.raises(ToolkitError) as failure:
                client.get("system/version")
        assert failure.value.verify_code == 92
        assert requests == []


def test_approved_self_issued_leaf_trust_keeps_runtime_flags(tmp_path):
    with server(tmp_path, self_issued=True, ca_key_usage=False, include_ca=False) as (
        profile,
        requests,
        leaf,
    ):
        assert leaf.subject == leaf.issuer
        from cryptography.exceptions import InvalidSignature

        with pytest.raises(InvalidSignature):
            leaf.verify_directly_issued_by(leaf)
        # This is explicitly approved synthetic material, never a network-fetched enrollment.
        trust = tmp_path / "trust.pem"
        trust.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
        profile = Profile(
            profile.name,
            profile.origin,
            ca_bundle=str(trust),
            approved_sha256=(leaf.fingerprint(hashes.SHA256()).hex().upper(),),
        )
        default_flags = context(str(trust)).verify_flags
        with Client(profile, "synthetic-secret", retries=0) as client:
            assert client.get("system/version")["currentVersion"] == "synthetic"
            assert requests == ["/publicApi/v8-preview/system/version"]
        assert context(str(trust)).verify_flags == default_flags


def test_unknown_exception_text_not_exposed_and_cycles_bounded():
    error = RuntimeError("Bearer synthetic-secret https://proxy-user:proxy-password@example.com")
    error.__cause__ = error
    safe = transport_error(error)
    assert safe.code == "transport_unknown"
    assert "synthetic-secret" not in str(safe) and "proxy-password" not in str(safe)


def test_verification_exception_without_numeric_code_is_still_safe():
    error = ssl.SSLCertVerificationError(1, "Bearer synthetic-secret")
    safe = transport_error(error)
    assert safe.code == "certificate_verification" and safe.verify_code is None
    assert "synthetic-secret" not in json.dumps(safe.diagnostic())


def test_no_key_logging_and_runtime_default_flags(monkeypatch, tmp_path):
    monkeypatch.setenv("SSLKEYLOGFILE", str(tmp_path / "secrets.log"))
    safe = context()
    assert safe.keylog_filename is None
    assert not (tmp_path / "secrets.log").exists()
    monkeypatch.delenv("SSLKEYLOGFILE")
    assert safe.verify_flags == (
        ssl.create_default_context().verify_flags
        | ssl.VERIFY_X509_STRICT
        | ssl.VERIFY_X509_PARTIAL_CHAIN
    )
    assert safe.check_hostname and safe.verify_mode == ssl.CERT_REQUIRED


def test_trust_exact_fingerprints_and_offline_doctor_no_tls_claim(tmp_path, monkeypatch):
    store = ProfileStore(tmp_path / "config")
    with server(tmp_path, self_signed=True) as (profile, _, leaf):
        store.add(Profile(profile.name, profile.origin))
        with pytest.raises(ToolkitError, match="fingerprints"):
            approve_trust(store, profile.name, tmp_path / "trust.pem", ["00"])
        approve_trust(
            store, profile.name, tmp_path / "trust.pem", [leaf.fingerprint(hashes.SHA256()).hex()]
        )

    class FakeVault:
        backend = object()

        def get(self, profile):
            return "fake"

    monkeypatch.setattr("le_results.diagnostics.Vault", FakeVault)
    result = doctor(store, "local", True, tmp_path / "outputs")
    assert result["tls"] == "not attempted" and result["ok"] is True
    assert result["output_writable"] is True


@pytest.mark.parametrize(
    "contents", [b"not PEM", b"-----BEGIN " + b"PRIVATE KEY-----\nfake\n", b""]
)
def test_malformed_trust_does_not_change_profile(tmp_path, contents):
    store = ProfileStore(tmp_path / "config")
    store.add(Profile("test", "https://appliance.example.com"))
    trust = tmp_path / "bad.pem"
    trust.write_bytes(contents)
    with pytest.raises(ToolkitError):
        approve_trust(store, "test", trust, ["00"])
    assert store.get("test").ca_bundle is None
