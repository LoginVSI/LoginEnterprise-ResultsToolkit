"""Bounded HTTPS transport. No response bodies, headers or URLs enter diagnostics."""

import ssl
import time
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from .contracts import API_ROOT, allowed_path
from .errors import ToolkitError
from .profiles import Profile, canonical_origin


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
    ) -> None:
        if not 1 <= page_size <= 1000 or not 1 <= max_pages <= 1000:
            raise ToolkitError("Paging bounds must be positive and no larger than 1000.")
        if profile.api_version != "v8-preview":
            raise ToolkitError("Only the v8-preview adapter is supported.")
        if not token or any(c.isspace() for c in token):
            raise ToolkitError("Invalid local credential.")
        self.origin = canonical_origin(profile.origin)
        self._token = token
        self.sleep, self.retries = sleep, retries
        self.page_size, self.max_pages = page_size, max_pages
        self.deadline = time.monotonic() + deadline_seconds
        try:
            context = ssl.create_default_context(cafile=profile.ca_bundle)
        except (OSError, ssl.SSLError):
            raise ToolkitError("Cannot load custom CA bundle.") from None
        self.http = httpx.Client(
            verify=context,
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
        for attempt in range(self.retries + 1):
            if time.monotonic() >= self.deadline:
                raise ToolkitError("Capture deadline exceeded; narrow the selection.")
            try:
                response = self.http.get(self.origin + API_ROOT + "/" + path, params=params)
            except httpx.TransportError as exc:
                # Do not render exception strings: they can contain request details.
                if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
                    message = "HTTPS connection failed; verify DNS, trust chain and custom CA."
                else:
                    message = "HTTPS request timed out or transport failed."
                if attempt == self.retries:
                    raise ToolkitError(message) from None
                self.sleep(min(2**attempt, 4))
                continue
            status = response.status_code
            if 300 <= status < 400:
                raise ToolkitError("Redirect refused; credentials never follow redirects.", status)
            if status == 401:
                raise ToolkitError(
                    "401: credential expired or invalid; replace it explicitly.", status
                )
            if status == 403:
                raise ToolkitError("403: credential lacks permission for this result.", status)
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
                self.sleep(max(0, delay))
                continue
            if status != 200:
                raise ToolkitError(f"HTTP {status}: result endpoint failed.", status)
            try:
                data = response.json()
            except ValueError:
                raise ToolkitError("Endpoint returned invalid JSON.") from None
            if data is None:
                raise ToolkitError("Endpoint returned null, not an empty dataset.")
            return self._redact(data)
        raise ToolkitError("Request retries exhausted.")

    def _redact(self, value: Any) -> Any:
        if isinstance(value, dict):
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

            value = value.replace(self._token, "[REDACTED]")
            value = re.sub(r"(?i)bearer\s+[^\s\"'<>]+", "Bearer [REDACTED]", value)
            return re.sub(
                r"(?i)(token|api_?key|password|secret|authorization)=([^&\s]+)",
                r"\1=[REDACTED]",
                value,
            )
        return value

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
