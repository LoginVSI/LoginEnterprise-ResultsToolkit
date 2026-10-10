"""Small explicit v8-preview adapter; definitions derived from the supplied OpenAPI."""

import re
from uuid import UUID

from .errors import ToolkitError

API_ROOT = "/publicApi/v8-preview"
PAGED = {
    "tests",
    "tests/test-runs",
    "test-runs/{id}/measurements",
    "test-runs/{id}/user-sessions",
    "test-runs/{id}/events",
    "test-runs/{id}/user-sessions/{session}/app-executions",
    "user-session-metrics/{id}",
    "session-metric-definition-groups/{id}/members",
}
SINGLE = {
    "system/version",
    "system/eux-version",
    "test-runs/{id}",
    "tests/{id}",
    "test-runs/{id}/eux-results",
    "test-runs/{id}/statistics",
}


def identifier(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError:
        raise ToolkitError("Expected an explicit UUID identifier.") from None


def route(template: str, **ids: str) -> str:
    if template not in PAGED | SINGLE:
        raise ToolkitError("Endpoint is outside the read-only adapter allowlist.")
    return template.format(**{k: identifier(v) for k, v in ids.items()})


def allowed_path(path: str) -> bool:
    return any(
        re.fullmatch(
            re.escape(p)
            .replace(r"\{id\}", "[a-f0-9-]{36}")
            .replace(r"\{session\}", "[a-f0-9-]{36}"),
            path,
        )
        for p in PAGED | SINGLE
    )
