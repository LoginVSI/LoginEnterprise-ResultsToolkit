"""Optional finite file export. No database writes or ingestion checkpoints."""

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import ToolkitError
from .evidence import load_table, verify_capture, write_json


def timestamp_ns(value: Any) -> int:
    if not isinstance(value, str):
        raise ToolkitError("Time-series observations require a source timestamp.")
    match = re.fullmatch(
        r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?(Z|[+-]\d\d:\d\d)", value
    )
    if not match:
        raise ToolkitError(
            "Source timestamp must have a timezone and at most nanosecond precision."
        )
    try:
        instant = datetime.fromisoformat(match[1] + match[3].replace("Z", "+00:00"))
        delta = instant.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
        result = (delta.days * 86400 + delta.seconds) * 10**9 + int((match[2] or "0").ljust(9, "0"))
    except ValueError:
        raise ToolkitError("Invalid source timestamp.") from None
    if not -9223372036854775806 <= result <= 9223372036854775806:
        raise ToolkitError("Timestamp exceeds InfluxDB 3 range.")
    return result


def escape_tag(value: str) -> str:
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ToolkitError("Control characters are unsuitable for line protocol tags.")
    return value.replace("\\", "\\\\").replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")


def string_field(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ToolkitError("Newlines are unsuitable for line protocol fields.")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def observation_line(row: dict[str, Any], table: str, source_id: str) -> tuple[str, str]:
    # Exclude capture-time metadata so an identical overlapping acquisition has the same identity.
    source = {
        k: v
        for k, v in row.items()
        if k == "_testRunId_from_endpoint"
        or (k != "capture_id" and not k.startswith("_") and not k.endswith("_utc"))
    }
    value = row.get("measurement" if table == "session_metrics" else "duration")
    if value is not None and (
        type(value) not in (int, float) or (type(value) is int and abs(value) > 2**53)
    ):
        raise ToolkitError("Source value cannot be represented as an exact numeric observation.")
    if value is not None and not math.isfinite(value):
        raise ToolkitError("Source value must be finite.")
    encoded = json.dumps(
        source, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )
    stamp = timestamp_ns(row.get("timestamp"))
    identity = json.dumps(
        {**source, "timestamp": stamp},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    observation = hashlib.sha256(identity.encode()).hexdigest()
    tags = {
        "source_id": source_id,
        "result_id": row.get("testRunId"),
        "session_ref": row.get("userSessionKey")
        if table == "session_metrics"
        else row.get("userSessionId"),
        "application_id": row.get("applicationId"),
        "execution_id": row.get("appExecutionId"),
        "metric_id": row.get("measurementId")
        if table == "measurements"
        else row.get("displayName"),
        "field_name": row.get("fieldName"),
        "instance": row.get("instance"),
        "unit": row.get("unit"),
        "observation_id": observation,
        "result_id_source": "endpoint" if row.get("_testRunId_from_endpoint") is True else "source",
    }
    tag_set = ",".join(
        k + "=" + escape_tag(str(v)) for k, v in sorted(tags.items()) if v is not None and str(v)
    )
    fields = [
        "value_present=" + ("true" if value is not None else "false"),
        "source_json=" + string_field(encoded),
    ]
    if value is not None:
        fields.append("value=" + repr(float(value)))
    return (
        f"le_{table},{tag_set} {','.join(fields)} {stamp}",
        observation,
    )


def export_line_protocol(
    capture: Path, directory: Path, max_records: int = 10000
) -> dict[str, Any]:
    if type(max_records) is not int or not 1 <= max_records <= 100000:
        raise ToolkitError("Line protocol bound must be 1-100000 observations.")
    manifest = verify_capture(capture)
    if manifest["status"] != "complete":
        raise ToolkitError("Failed or partial acquisition cannot prepare a database batch.")
    if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
        raise ToolkitError("Use a new export directory; preserve prior batches.")
    source_id = hashlib.sha256(manifest["origin"].encode()).hexdigest()
    lines: list[str] = []
    seen: set[tuple[str, str]] = set()
    counts: dict[str, int] = {}
    for table in ("measurements", "session_metrics"):
        rows = load_table(capture, table)
        counts[table] = len(rows)
        if sum(counts.values()) > max_records:
            raise ToolkitError("Observation bound exceeded; narrow the capture.")
        for row in rows:
            line, observation = observation_line(row, table, source_id)
            if (table, observation) not in seen:
                lines.append(line)
                seen.add((table, observation))
    payload = ("\n".join(lines) + ("\n" if lines else "")).encode()
    if len(payload) > 64 * 1024 * 1024:
        raise ToolkitError("Line protocol batch exceeds 64 MiB; narrow the capture.")
    receipt = {
        "schema_version": "line-protocol-export/1",
        "target": "InfluxDB 3 Core 3.12.0; SQL; Grafana 13.2",
        "precision": "ns",
        "status": "prepared-not-written",
        "acquisition_status": manifest["status"],
        "selection": manifest["selection"],
        "source_counts": counts,
        "exported_points": len(lines),
        "canonical_overlap_duplicates": sum(counts.values()) - len(lines),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "manifest_sha256": hashlib.sha256((capture / "manifest.json").read_bytes()).hexdigest(),
        "grain": "Raw observations; no aggregation, conversion or timer unit inference",
        "source_granularity": manifest.get("source_granularity", "unknown"),
        "checkpoint_advanced": False,
        "limitations": [
            "No destination writes or runtime compatibility demonstrated.",
            "Observation hash is a tag, preventing same-time identity collisions. Changed source values append distinct versions; no last-write claim.",
            "No acquisition/write resume; use new overlapping frozen captures and review version conflicts.",
            "Session references and host scope remain source evidence, not independent devices.",
        ],
    }
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "observations.lp").write_bytes(payload)
    write_json(directory / "receipt.json", receipt)
    return receipt
