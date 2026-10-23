import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .contracts import identifier
from .errors import ToolkitError


def utc(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError
        return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")
    except ValueError:
        raise ToolkitError("Timestamp requires ISO 8601 with explicit timezone.") from None


@dataclass(frozen=True)
class Selection:
    test_type: str
    ids: list[str]
    start: str | None = None
    end: str | None = None
    scenario: dict[str, Any] | None = None
    schema_version: str = "selection/1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "ids", [identifier(value) for value in self.ids])

    def validate(self) -> "Selection":
        if self.schema_version != "selection/1" or self.test_type not in (
            "LoadTest",
            "ApplicationTest",
            "ContinuousTest",
        ):
            raise ToolkitError("Unsupported selection contract or test type.")
        if not self.ids or len(self.ids) > 20 or len(set(self.ids)) != len(self.ids):
            raise ToolkitError("Select 1-20 unique identifiers.")
        for value in self.ids:
            identifier(value)
        if (self.start is None) != (self.end is None):
            raise ToolkitError("Supply both time boundaries.")
        if self.test_type == "ContinuousTest" and self.start is None:
            raise ToolkitError("Continuous selections require test IDs and a frozen window.")
        if self.start and self.end and utc(self.start) >= utc(self.end):
            raise ToolkitError("Window start must precede its end.")
        return self

    def write(self, path: Path) -> None:
        self.validate()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def read(cls, path: Path) -> "Selection":
        try:
            return cls(**json.loads(path.read_text(encoding="utf-8"))).validate()
        except (TypeError, ValueError):
            raise ToolkitError("Invalid selection file.") from None


def rolling(hours: float, now: datetime | None = None) -> tuple[str, str]:
    if not 0 < hours <= 24 * 31:
        raise ToolkitError("Rolling hours must be positive and no more than 744.")
    end = now or datetime.now(UTC)
    return utc((end - timedelta(hours=hours)).isoformat()), utc(end.isoformat())
