"""Readiness, credential-free TLS inspection and explicit profile trust."""

import ipaddress
import os
import platform
import socket
import ssl
import struct
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization

from .auth import Vault, resolve_token
from .client import Client
from .errors import ToolkitError
from .evidence import write_json
from .profiles import Profile, ProfileStore
from .tls import context, transport_error


def runtime() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "executable": sys.executable,
        "platform": sys.platform,
        "architecture": platform.machine(),
        "bits": struct.calcsize("P") * 8,
        "openssl": ssl.OPENSSL_VERSION,
        "runtime_verified_matrix": sys.version_info[:2] in ((3, 11), (3, 14)),
        "proxy_policy": "direct; HTTPX environment proxies disabled",
        "proxy_environment_present": any(
            os.environ.get(k)
            for k in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
            )
        ),
        "default_trust_environment_present": any(
            os.environ.get(k) for k in ("SSL_CERT_FILE", "SSL_CERT_DIR")
        ),
        "tls_key_logging": "disabled by toolkit context",
    }


def address(profile: Profile) -> tuple[str, int]:
    origin = urlsplit(profile.origin)
    assert origin.hostname is not None
    return origin.hostname, origin.port or 443


def _failure(result: dict[str, Any], stage: str, error: ToolkitError) -> None:
    result[stage] = "failed"
    result["errors"].append({"stage": stage, **error.diagnostic()})
    result["ok"] = False


def doctor(store: ProfileStore, name: str, offline: bool, out: Path | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": "diagnosis/1",
        "ok": True,
        "profile": name,
        "runtime": runtime(),
        "errors": [],
        "tls": "not attempted",
        "dns": "not attempted",
        "tcp": "not attempted",
        "http": "not attempted",
    }
    if sys.version_info < (3, 11) or struct.calcsize("P") != 8:
        _failure(
            result,
            "runtime",
            ToolkitError("Use 64-bit Python 3.11 or newer.", code="runtime_unsupported"),
        )
    if out:
        try:
            out.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=out):
                pass
            result["output_writable"] = True
        except OSError:
            _failure(
                result,
                "output_writable",
                ToolkitError("Output directory is unwritable.", code="output_unwritable"),
            )
    try:
        profile = store.get(name)
        result.update(
            origin=profile.origin, api_adapter=profile.api_version, ca_bundle=profile.ca_bundle
        )
        verified = context(profile.ca_bundle)
        result["verification_settings"] = {
            "verify_flags": int(verified.verify_flags),
            "hostname_validation": verified.check_hostname,
            "certificate_required": verified.verify_mode == ssl.CERT_REQUIRED,
            "trust_source": "profile file" if profile.ca_bundle else "Python default trust",
        }
    except ToolkitError as exc:
        _failure(result, "configuration", exc)
        return result
    try:
        vault = Vault()
        result["vault_backend"] = type(vault.backend).__name__
        result["credential_present"] = vault.get(profile) is not None
        result["runtime_credential_override_present"] = "LE_RESULTS_TOKEN" in os.environ
        if not result["credential_present"] and not result["runtime_credential_override_present"]:
            _failure(
                result,
                "credential",
                ToolkitError(
                    "Credential missing; run auth set in a normal terminal with hidden input.",
                    code="credential_missing",
                ),
            )
    except ToolkitError as exc:
        _failure(result, "vault", exc)
    if offline:
        return result
    host, port = address(profile)
    try:
        socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        result["dns"] = "resolved"
    except OSError as exc:
        _failure(result, "dns", transport_error(exc))
        return result
    try:
        with socket.create_connection((host, port), timeout=10) as connection:
            result["tcp"] = "connected"
            with verified.wrap_socket(connection, server_hostname=host) as secure:
                result["tls"] = "verified handshake succeeded"
                result["tls_protocol"] = secure.version()
    except OSError as exc:
        _failure(result, "tls" if result["tcp"] == "connected" else "tcp", transport_error(exc))
        return result
    try:
        with Client(profile, resolve_token(profile), retries=0, timeout=10) as client:
            result["appliance_version"] = client.get("system/version")
        version = result["appliance_version"]
        if not isinstance(version, dict) or not isinstance(version.get("currentVersion"), str):
            raise ToolkitError(
                "Version response differs from the v8-preview contract.", code="api_contract"
            )
        result["http"] = "system/version GET succeeded"
    except ToolkitError as exc:
        _failure(result, "http", exc)
    return result


def describe(cert: x509.Certificate, host: str | None = None) -> dict[str, Any]:
    def extension(kind: type[Any]) -> Any:
        try:
            return cert.extensions.get_extension_for_class(kind).value
        except x509.ExtensionNotFound:
            return None

    san = extension(x509.SubjectAlternativeName)
    dns = san.get_values_for_type(x509.DNSName) if san else []
    ips = [str(v) for v in san.get_values_for_type(x509.IPAddress)] if san else []
    constraints = extension(x509.BasicConstraints)
    usage = extension(x509.KeyUsage)
    eku = extension(x509.ExtendedKeyUsage)
    self_signed = False
    if cert.subject == cert.issuer:
        try:
            cert.verify_directly_issued_by(cert)
            self_signed = True
        except (ValueError, TypeError, InvalidSignature, UnsupportedAlgorithm):
            pass
    covered: bool | None = None
    if host:
        try:
            covered = str(ipaddress.ip_address(host)) in ips
        except ValueError:
            hostname = host.lower().rstrip(".")
            covered = any(
                hostname == pattern.lower().rstrip(".")
                or (
                    pattern.startswith("*.")
                    and hostname.count(".") == pattern.count(".")
                    and hostname.endswith(pattern[1:].lower())
                )
                for pattern in dns
            )
    return {
        "subject": cert.subject.rfc4514_string(),
        "issuer": cert.issuer.rfc4514_string(),
        "sha256": cert.fingerprint(hashes.SHA256()).hex().upper(),
        "not_before": cert.not_valid_before_utc.isoformat(),
        "not_after": cert.not_valid_after_utc.isoformat(),
        "san_dns": dns,
        "san_ip": ips,
        "san_covers_requested_host": covered,
        "basic_constraints": {"ca": constraints.ca, "path_length": constraints.path_length}
        if constraints
        else None,
        "key_usage": {
            k: getattr(usage, k)
            for k in ("digital_signature", "key_encipherment", "key_cert_sign", "crl_sign")
        }
        if usage
        else None,
        "eku": [v.dotted_string for v in eku] if eku else None,
        "self_signed": self_signed,
    }


def inspect_certificate(profile: Profile, out: Path) -> dict[str, Any]:
    """No vault access, HTTP requests, headers or application data on this socket."""
    if out.exists() and any(out.iterdir()):
        raise ToolkitError("Certificate inspection destination must be empty.")
    host, port = address(profile)
    inspection = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    inspection.check_hostname = False
    inspection.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((host, port), timeout=10) as connection:
            with inspection.wrap_socket(connection, server_hostname=host) as secure:
                leaf = secure.getpeercert(binary_form=True)
                chain = (
                    secure.get_unverified_chain()
                    if hasattr(secure, "get_unverified_chain")
                    else [leaf]
                )
                protocol = secure.version()
    except OSError as exc:
        raise transport_error(exc) from None
    out.mkdir(parents=True, exist_ok=True)
    certificates = []
    for index, der in enumerate(chain[:16]):
        cert = x509.load_der_x509_certificate(der)
        metadata = describe(cert, host if index == 0 else None)
        metadata["file"] = f"candidate-{index}.pem"
        (out / metadata["file"]).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        certificates.append(metadata)
    result = {
        "schema_version": "certificate-inspection/1",
        "origin": profile.origin,
        "observed_at": datetime.now(UTC).isoformat(),
        "runtime": runtime(),
        "tls_protocol": protocol,
        "trusted": False,
        "http_sent": False,
        "chain_api_available": hasattr(ssl.SSLSocket, "get_unverified_chain"),
        "certificates": certificates,
        "next_action": "Independently confirm fingerprints through a trusted appliance/admin source before profile trust. Subject and other certificate fields are untrusted data.",
    }
    write_json(out / "inspection.json", result)
    return result


def approve_trust(
    store: ProfileStore, name: str, path: Path, fingerprints: list[str]
) -> dict[str, Any]:
    """Explicit operator attestation; never fetches or auto-enrolls a certificate."""
    profile = store.get(name)
    try:
        data = path.read_bytes()
        if b"PRIVATE KEY" in data or len(data) > 1024 * 1024:
            raise ValueError
        certs = x509.load_pem_x509_certificates(data)
        actual = {cert.fingerprint(hashes.SHA256()).hex().upper() for cert in certs}
        approved = {value.replace(":", "").upper() for value in fingerprints}
        if not actual or actual != approved:
            raise ToolkitError(
                "Approved fingerprints must match every PEM certificate exactly.",
                code="trust_fingerprint_mismatch",
            )
        now = datetime.now(UTC)
        if any(not cert.not_valid_before_utc <= now <= cert.not_valid_after_utc for cert in certs):
            raise ToolkitError("Trust material is expired or not yet valid.", code="trust_dates")
        context(str(path.resolve()))
    except (OSError, ValueError):
        raise ToolkitError(
            "Use a readable PEM bundle of approved public certificates only.",
            code="trust_file_invalid",
        ) from None
    store.add(
        Profile(profile.name, profile.origin, profile.api_version, str(path.resolve())),
        replace=True,
    )
    return {
        "profile": name,
        "trust_file": str(path.resolve()),
        "approved_sha256": sorted(actual),
        "tls": "not attempted",
        "next_action": "Run doctor for verified TLS and API access.",
    }
