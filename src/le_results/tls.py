"""Shared verified context and allowlisted transport diagnostics.

Exception text is deliberately never copied into an error or artifact.
"""

import errno
import socket
import ssl
import sys
from pathlib import Path

import httpx

from .errors import ToolkitError


def context(ca_bundle: str | None = None) -> ssl.SSLContext:
    # Mirror create_default_context without its SSLKEYLOGFILE side effect.
    result = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if sys.version_info >= (3, 13):
        result.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN | ssl.VERIFY_X509_STRICT
    try:
        if ca_bundle:
            if not Path(ca_bundle).is_file():
                raise ToolkitError("Trust file missing or unreadable.", code="trust_file_missing")
            with Path(ca_bundle).open("rb") as trust_file:
                material = trust_file.read(1024 * 1024 + 1)
            if b"PRIVATE KEY" in material or len(material) > 1024 * 1024:
                raise ToolkitError(
                    "CA bundle must contain only bounded public certificate material.",
                    code="trust_file_invalid",
                )
            result.load_verify_locations(cafile=ca_bundle)
        else:
            result.load_default_certs(ssl.Purpose.SERVER_AUTH)
    except (OSError, ssl.SSLError):
        raise ToolkitError(
            "Cannot load CA bundle; use readable PEM public certificates, without private keys.",
            code="trust_file_invalid",
        ) from None
    return result


def transport_error(exc: BaseException) -> ToolkitError:
    pending, causes = [exc], []
    seen: set[int] = set()
    while pending and len(seen) < 24:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        causes.append(item)
        for nested in (item.__cause__, item.__context__):
            if nested is not None:
                pending.append(nested)
    for item in causes:
        if isinstance(item, ssl.SSLCertVerificationError):
            raw_code = getattr(item, "verify_code", None)
            code = raw_code if isinstance(raw_code, int) else 0
            known = {
                9: (
                    "certificate_not_yet_valid",
                    "Certificate is not yet valid; check dates and clock.",
                ),
                10: (
                    "certificate_expired",
                    "Certificate expired; obtain renewed approved trust material.",
                ),
                18: (
                    "certificate_self_signed",
                    "Untrusted self-signed certificate; independently confirm its fingerprint before profile trust.",
                ),
                19: (
                    "certificate_untrusted_chain",
                    "Untrusted certificate chain; obtain approved CA trust material.",
                ),
                20: (
                    "certificate_issuer_missing",
                    "Issuer unavailable; distinguish missing client CA trust from a missing server intermediate.",
                ),
                21: (
                    "certificate_chain_incomplete",
                    "Cannot verify certificate chain; inspect approved CA trust and server intermediates.",
                ),
                26: (
                    "certificate_purpose",
                    "Certificate is unsuitable for TLS server authentication.",
                ),
                62: (
                    "certificate_hostname",
                    "Certificate hostname mismatch; use the approved SAN hostname or repair the server certificate.",
                ),
                64: (
                    "certificate_hostname",
                    "Certificate IP address mismatch; use the approved SAN identity.",
                ),
                92: (
                    "certificate_ca_key_usage",
                    "Issuing CA certificate lacks required key usage; request a conforming CA/server chain. Strict verification is retained.",
                ),
            }
            kind, message = known.get(
                code,
                (
                    "certificate_verification",
                    "Certificate verification failed; inspect the numeric verification code and approved chain.",
                ),
            )
            return ToolkitError(message, code=kind, verify_code=code or None)
    for item in causes:
        if isinstance(item, socket.gaierror):
            return ToolkitError(
                "DNS resolution failed; verify the origin and DNS route.", code="dns_failed"
            )
        if isinstance(item, ConnectionRefusedError) or (
            isinstance(item, OSError) and item.errno in (errno.ECONNREFUSED, 10061)
        ):
            return ToolkitError(
                "TCP connection refused; verify reachability and listener.",
                code="connection_refused",
            )
    if any(isinstance(item, (TimeoutError, httpx.TimeoutException)) for item in causes):
        return ToolkitError(
            "Connection or request timed out; the failing network phase is not established.",
            code="timeout",
        )
    if any(isinstance(item, ssl.SSLError) for item in causes):
        return ToolkitError(
            "TLS negotiation failed; certificate verification success is not established.",
            code="tls_negotiation",
        )
    return ToolkitError(
        "Unknown transport failure; DNS, routing and TLS cause are not established.",
        code="transport_unknown",
    )
