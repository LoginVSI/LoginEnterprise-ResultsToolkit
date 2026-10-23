"""Bounded HTTPS transport. No response bodies, headers or URLs enter diagnostics."""

import json
import math
import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from .contracts import API_ROOT, allowed_path, route
from .errors import ToolkitError
from .profiles import Profile, canonical_origin
from .tls import context, transport_error


class Client:
    def __init__(
        self,
        profile: Profile,
        token: str,
        *,
        transport: Any = None,
        sleep: Callable[[float], None] = time.sleep,
        retries: int = 2,
        timeout: float = 20,
        page_size: int = 100,
        max_pages: int = 100,
        deadline_seconds: float = 300,
        max_requests: int = 2000,
    ) -> None:
        if not 1 <= page_size <= 1000 or not 1 <= max_pages <= 1000:
            raise ToolkitError("Paging bounds must be positive and no larger than 1000.")
        if profile.api_version != "v8-preview":
            raise ToolkitError("Only the v8-preview adapter is supported.")
        if not token or any(c.isspace() for c in token):
            raise ToolkitError("Invalid local credential.")
        self.origin = canonical_origin(profile.origin)
        if (
            not math.isfinite(timeout)
            or not math.isfinite(deadline_seconds)
            or min(timeout, deadline_seconds) <= 0
        ):
            raise ToolkitError("Timeout and deadline must be finite positive seconds.")
        if not 0 <= retries <= 5:
            raise ToolkitError("Retries must be bounded to 0-5.")
        self.timeout = timeout
        self.redactions = 0
        self._token = token
        self.sleep, self.retries = sleep, retries
        self.page_size, self.max_pages = page_size, max_pages
        self.deadline = time.monotonic() + deadline_seconds
        if not 1 <= max_requests <= 10000:
            raise ToolkitError("Request bound must be 1-10000.")
        self.max_requests, self.request_count = max_requests, 0
        verified_context = context(profile.ca_bundle, profile.approved_sha256)
        self.http = httpx.Client(
            verify=verified_context,
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        )

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not allowed_path(path):
            raise ToolkitError("Endpoint is outside the read-only adapter allowlist.")
        permitted = {
            "count",
            "offset",
            "direction",
            "includeTotalCount",
            "include",
            "from",
            "to",
            "filter",
            "testType",
            "orderBy",
            "filterType",
        }
        if params and set(params) - permitted:
            raise ToolkitError("Unsupported query fields.")
        return self._request(API_ROOT + "/" + path, params)

    def get_contract(self) -> Any:
        """Read only the appliance's explicit v8-preview Swagger through normal security."""
        return self._request(API_ROOT + "/openapi.json", None)

    def get_application_pdf(self, run_id: str, max_bytes: int = 16 * 1024 * 1024) -> bytes:
        """Download the documented Application GET report, without creating a report job."""
        if type(max_bytes) is not int or not 1 <= max_bytes <= 64 * 1024 * 1024:
            raise ToolkitError("PDF byte bound must be 1-67108864.")
        run = self.get(route("test-runs/{id}", id=run_id))
        if (
            not isinstance(run, dict)
            or run.get("id") != run_id
            or run.get("type") != "ApplicationTest"
            or not run.get("finished")
        ):
            raise ToolkitError("Native PDF retrieval requires a completed Application result.")
        data = self._request(
            API_ROOT + "/" + route("test-runs/{id}/reports/pdf", id=run_id),
            None,
            binary_max_bytes=max_bytes,
        )
        if not isinstance(data, bytes) or not data.startswith(b"%PDF-"):
            raise ToolkitError("Native report did not return a PDF.", code="api_contract")
        if self._token.encode() in data:
            raise ToolkitError(
                "Credential reflection rejected in native report.", code="credential_reflection"
            )
        return data

    def get_documentation(self, path: str) -> str:
        if path not in (
            "swagger/index.html",
            "v8-preview/docs/index.html",
            "swagger/swagger-ui-init.js",
        ):
            raise ToolkitError("Documentation path is outside the explicit v8-preview allowlist.")
        return str(self._request("/publicApi/" + path, None, json_response=False))

    def _request(
        self,
        relative_path: str,
        params: dict[str, Any] | None,
        *,
        json_response: bool = True,
        binary_max_bytes: int | None = None,
    ) -> Any:
        for attempt in range(self.retries + 1):
            if self.request_count >= self.max_requests:
                raise ToolkitError(
                    "Request bound exceeded; narrow the selection.", code="request_bound"
                )
            if time.monotonic() >= self.deadline:
                raise ToolkitError(
                    "Capture deadline exceeded; narrow the selection.", code="deadline"
                )
            try:
                self.request_count += 1
                request_timeout = min(self.timeout, self.deadline - time.monotonic())
                if binary_max_bytes is None:
                    response = self.http.get(
                        self.origin + relative_path, params=params, timeout=request_timeout
                    )
                else:
                    with self.http.stream(
                        "GET", self.origin + relative_path, params=params, timeout=request_timeout
                    ) as stream:
                        content = bytearray()
                        if stream.status_code == 200:
                            for chunk in stream.iter_bytes(chunk_size=65536):
                                if len(content) + len(chunk) > binary_max_bytes:
                                    raise ToolkitError(
                                        "Native PDF exceeds the configured byte bound.",
                                        code="response_bound",
                                    )
                                if time.monotonic() >= self.deadline:
                                    raise ToolkitError(
                                        "Download deadline exceeded.", code="deadline"
                                    )
                                content.extend(chunk)
                        response = httpx.Response(
                            stream.status_code,
                            headers={"Retry-After": stream.headers.get("Retry-After", "")},
                            content=bytes(content),
                            request=stream.request,
                        )
            except httpx.DecodingError:
                raise ToolkitError(
                    "Endpoint response encoding is invalid.", code="response_encoding"
                ) from None
            except httpx.TransportError as exc:
                diagnostic = transport_error(exc)
                if attempt == self.retries or diagnostic.code.startswith("certificate_"):
                    raise diagnostic from None
                self._wait(min(2**attempt, 4))
                continue
            status = response.status_code
            if time.monotonic() >= self.deadline:
                raise ToolkitError(
                    "Capture deadline exceeded; narrow the selection.", code="deadline"
                )
            if 300 <= status < 400:
                raise ToolkitError("Redirect refused; credentials never follow redirects.", status)
            if status == 401:
                raise ToolkitError(
                    "401: credential expired or invalid; replace it explicitly.",
                    status,
                    code="authentication",
                )
            if status == 403:
                raise ToolkitError(
                    "403: credential lacks permission for this result.",
                    status,
                    code="authorization",
                )
            if status in (429, 502, 503, 504) and attempt < self.retries:
                delay = float(2**attempt)
                header = response.headers.get("Retry-After", "")
                try:
                    delay = float(header)
                except ValueError:
                    try:
                        delay = (parsedate_to_datetime(header) - datetime.now(UTC)).total_seconds()
                    except (ValueError, TypeError, OverflowError):
                        pass
                if delay > 30:
                    raise ToolkitError("Retry-After exceeds bounded wait; retry later.", status)
                self._wait(max(0, delay))
                continue
            if status != 200:
                raise ToolkitError(
                    f"HTTP {status}: result endpoint failed.",
                    status,
                    code="api_route_missing" if status == 404 else "http_failed",
                )
            if binary_max_bytes is not None:
                return response.content
            if not json_response:
                return self._redact(response.text)
            try:
                data = response.json()
            except ValueError:
                raise ToolkitError("Endpoint returned invalid JSON.") from None
            if data is None:
                raise ToolkitError("Endpoint returned null, not an empty dataset.")
            return self._redact(data)
        raise ToolkitError("Request retries exhausted.")

    def _redact(self, value: Any) -> Any:
        if isinstance(value, float) and not math.isfinite(value):
            raise ToolkitError("Endpoint returned a non-finite JSON number.", code="source_schema")
        if isinstance(value, dict):
            self.redactions += sum(
                any(
                    s in k.lower().replace("_", "")
                    for s in ("authorization", "password", "secret", "token", "apikey", "cookie")
                )
                for k in value
            )
            return {
                k: "[REDACTED]"
                if any(
                    s in k.lower().replace("_", "")
                    for s in (
                        "authorization",
                        "password",
                        "secret",
                        "token",
                        "apikey",
                        "cookie",
                    )
                )
                else self._redact(v)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [self._redact(v) for v in value]
        if isinstance(value, str):
            import re

            original = value
            value = value.replace(self._token, "[REDACTED]")
            value = re.sub(r"(?i)bearer\s+[^\s\"'<>]+", "Bearer [REDACTED]", value)
            safe = re.sub(
                r"(?i)(token|api_?key|password|secret|authorization)=([^&\s]+)",
                r"\1=[REDACTED]",
                value,
            )
            self.redactions += safe != original
            return safe
        return value

    def _wait(self, seconds: float) -> None:
        if not math.isfinite(seconds) or seconds >= self.deadline - time.monotonic():
            raise ToolkitError("Retry exceeds remaining capture deadline.", code="deadline")
        self.sleep(seconds)

    def pages(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        on_page: Callable[[int, dict[str, Any]], None] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        offset = 0
        result: list[dict[str, Any]] = []
        expected_total: int | None = None
        seen_rows: set[str] = set()
        for page in range(self.max_pages):
            count = min(self.page_size, limit - len(result)) if limit else self.page_size
            query = {
                **(params or {}),
                "count": count,
                "offset": offset,
                "direction": (params or {}).get("direction", "asc"),
                "includeTotalCount": "true",
            }
            data = self.get(path, query)
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                raise ToolkitError("Invalid paging envelope; items must be an array.")
            items = data["items"]
            if any(not isinstance(x, dict) for x in items):
                raise ToolkitError("Invalid paging item.")
            if data.get("offset") != offset:
                raise ToolkitError("Paging offset mismatch; capture cannot be trusted.")
            total = data.get("totalCount")
            if total is not None and (type(total) is not int or total < 0):
                raise ToolkitError("Invalid totalCount.")
            if expected_total is not None and total != expected_total:
                raise ToolkitError("Dataset changed during paging; recapture the frozen window.")
            expected_total = total
            if on_page:
                on_page(page, data)
            page_rows = {json.dumps(row, sort_keys=True, allow_nan=False) for row in items}
            if len(page_rows) != len(items) or seen_rows & page_rows:
                raise ToolkitError(
                    "Overlapping paging rows; capture incomplete. Recapture a stable window.",
                    code="paging_overlap",
                )
            seen_rows.update(page_rows)
            result.extend(items)
            offset += len(items)
            if limit and len(result) >= limit:
                return result[:limit]
            if total is not None and offset >= total:
                if offset != total:
                    raise ToolkitError("Paging returned more than declared totalCount.")
                return result
            if len(items) < count:
                if total is not None and offset < total:
                    raise ToolkitError("Truncated page before declared totalCount.")
                return result
        raise ToolkitError("Page bound exceeded; capture is incomplete. Narrow the selection.")
