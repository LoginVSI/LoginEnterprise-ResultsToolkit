"""Versioned captures preserve endpoint outcomes and source rows."""

import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .client import Client
from .contracts import route
from .errors import ToolkitError
from .selection import Selection, utc

TABLES = (
    "runs",
    "sessions",
    "executions",
    "events",
    "measurements",
    "session_metrics",
    "eux",
    "current_configuration",
    "collectors",
)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8"
    )


def normalize(row: dict[str, Any], capture_id: str) -> dict[str, Any]:
    result = {**row, "capture_id": capture_id}
    for key, value in row.items():
        if isinstance(value, str) and (
            key in ("timestamp", "created", "started", "finished") or key.endswith("Time")
        ):
            try:
                result[key + "_utc"] = utc(value)
            except ToolkitError:
                result[key + "_utc"] = None
                result[key + "_warning"] = "Unparseable or timezone-free source timestamp"
    return result


def unique(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Exact-row dedup only: measurementId denotes a timer, not a unique observation.
    seen: set[str] = set()
    out = []
    for row in rows:
        key = json.dumps(row, sort_keys=True, allow_nan=False)
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out


def finalize(
    directory: Path, manifest: dict[str, Any], tables: dict[str, list[dict[str, Any]]]
) -> None:
    manifest["table_counts"] = {}
    for table in TABLES:
        rows = unique(tables.get(table, []))
        manifest["table_counts"][table] = len(rows)
        write_json(directory / "normalized" / f"{table}.json", rows)
        fields = sorted({k for row in rows for k in row}) or ["capture_id"]
        with (directory / "normalized" / f"{table}.csv").open(
            "w", encoding="utf-8", newline=""
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v
                        for k, v in row.items()
                    }
                )
    write_json(
        directory / "data-dictionary.json",
        {
            "schema_version": "dictionary/1",
            "tables": {
                "runs": "One selected run or Continuous test configuration; source fields retained",
                "sessions": "One session identity; loginState and failure states are retained",
                "executions": "One app execution identity, linked to run/session/application",
                "events": "One source event, with nullable relationships retained",
                "measurements": "One timer observation; measurementId is not an observation ID; duration unit unspecified by API",
                "session_metrics": "One timestamp/session/field/instance observation; source unit retained; host scope uncertain",
                "eux": "One vendor score interval; no toolkit EUX calculation",
                "current_configuration": "One current test configuration, never evidence of historical settings",
                "collectors": "One current definition/group/selected-result association; source query/counter, instance and poll settings retained where exposed",
            },
            "timestamps": "Original fields retained; *_utc contains timezone-aware UTC conversion",
            "nested_fields": "JSON objects/arrays preserved in JSON and serialized in CSV",
            "null": "Unavailable is null, never zero",
        },
    )
    manifest["files"] = {
        p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(directory.rglob("*"))
        if p.is_file() and p.name != "manifest.json"
    }
    write_json(directory / "manifest.json", manifest)


def capture(client: Client, selection: Selection, directory: Path) -> dict[str, Any]:
    selection.validate()
    if directory.exists() and any(directory.iterdir()):
        raise ToolkitError("Capture destination must be empty; previous evidence is immutable.")
    directory.mkdir(parents=True, exist_ok=True)
    captured = datetime.now(UTC).isoformat()
    manifest: dict[str, Any] = {
        "schema_version": "capture/1",
        "api_version": "v8-preview",
        "origin": client.origin,
        "captured_at": captured,
        "selection": {
            "test_type": selection.test_type,
            "ids": selection.ids,
            "start": selection.start,
            "end": selection.end,
            "scenario": selection.scenario,
        },
        "provenance": "appliance",
        "status": "failed",
        "endpoints": [],
        "warnings": [
            "Retention unknown: empty raw data does not prove no activity.",
            "Source units and custom timer semantics require explicit metric definitions.",
            "Session observations are not independent devices; shared-host CPU/memory may repeat.",
            "Window boundaries are endpoint-specific; EUX inclusive, other boundaries unconfirmed.",
            "Late data requires a new overlapping capture; no incremental ingestion implemented.",
        ],
        "source_granularity": "raw endpoint observations; no inferred aggregation",
        "checkpoint": {"window_frozen": True, "incremental_resume": False},
    }
    tables: dict[str, list[dict[str, Any]]] = {k: [] for k in TABLES}
    counter = 0
    result_id: str | None = None

    def acquire(
        path: str,
        table: str | None,
        paged: bool = False,
        params: dict[str, Any] | None = None,
        optional: bool = False,
    ) -> Any:
        nonlocal counter
        counter += 1
        prefix = f"{counter:03d}"
        outcome: dict[str, Any] = {
            "path": path,
            "query": params or {},
            "status": "failed",
            "count": 0,
        }
        manifest["endpoints"].append(outcome)

        def save(page: int, data: dict[str, Any]) -> None:
            write_json(directory / "raw" / f"{prefix}-{page:04d}.json", data)
            outcome["count"] += len(data["items"])
            outcome["last_page"] = page
            outcome["last_offset"] = data["offset"]

        try:
            if paged:
                data = client.pages(path, params, on_page=save)
            else:
                data = client.get(path, params)
                write_json(directory / "raw" / f"{prefix}.json", data)
                outcome["count"] = len(data) if isinstance(data, list) else 1
            if table:
                rows = data if isinstance(data, list) else [data]
                if any(not isinstance(row, dict) for row in rows):
                    raise ToolkitError("Unexpected source row type.")
                if table in (
                    "sessions",
                    "executions",
                    "measurements",
                    "events",
                    "session_metrics",
                    "eux",
                ) and any(row.get("testRunId") not in (None, result_id) for row in rows):
                    raise ToolkitError(
                        "Returned source result identity differs from selected endpoint.",
                        code="source_identity",
                    )
                tables[table].extend(normalize(row, captured) for row in rows)
            outcome["status"] = "empty" if outcome["count"] == 0 else "complete"
            return data
        except ToolkitError as exc:
            outcome["error"] = str(exc)
            outcome["diagnostic"] = exc.diagnostic()
            if optional and exc.status in (404, 405) and outcome["count"] == 0:
                outcome["status"] = "unavailable"
                manifest["warnings"].append("Optional endpoint unavailable: " + path)
                return None
            outcome["status"] = "partial" if outcome["count"] else "failed"
            if optional:
                return None
            raise

    try:
        manifest["appliance_version"] = acquire("system/version", None)
        manifest["eux_version"] = acquire("system/eux-version", None, optional=True)
        for selected in selection.ids:
            if selection.test_type == "ContinuousTest":
                run = acquire(route("tests/{id}", id=selected), "runs", params={"include": "all"})
                if run.get("id") != selected or run.get("type") != "ContinuousTest":
                    raise ToolkitError(
                        "Returned Continuous test identity/type differs from selection."
                    )
                tables["runs"][-1]["configuration_scope"] = "current"
                result_id = (
                    selected  # Contract calls this testRunId; Continuous uses test identity.
                )
            else:
                run = acquire(
                    route("test-runs/{id}", id=selected),
                    "runs",
                    params={"include": "testRunConfigurationSnapshot"},
                )
                if run.get("id") != selected or run.get("type") != selection.test_type:
                    raise ToolkitError(
                        "Returned run identity/type differs from explicit selection."
                    )
                if not run.get("finished"):
                    raise ToolkitError("Selected run is unfinished; choose a completed run.")
                tables["runs"][-1]["configuration_scope"] = (
                    "historical"
                    if run.get("testConfigurationSnapshot") is not None
                    else "unavailable"
                )
                result_id = selected
            if selection.test_type == "ContinuousTest":
                current = run
            elif run.get("testId"):
                current = acquire(
                    route("tests/{id}", id=run["testId"]),
                    "current_configuration",
                    params={"include": "all"},
                    optional=True,
                )
                if current:
                    tables["current_configuration"][-1]["configuration_scope"] = "current"
                    tables["current_configuration"][-1]["_selected_result_id"] = selected
            else:
                current = None
            if current and current.get("sessionMetricDefinitionGroupId"):
                first_collector = len(tables["collectors"])
                acquire(
                    route(
                        "session-metric-definition-groups/{id}/members",
                        id=current["sessionMetricDefinitionGroupId"],
                    ),
                    "collectors",
                    True,
                    optional=True,
                )
                for collector in tables["collectors"][first_collector:]:
                    collector["configuration_scope"] = "current"
                    collector["_selected_result_id"] = selected
                    collector["_collector_group_id"] = current["sessionMetricDefinitionGroupId"]
            manifest["warnings"].append(
                "Current collector definitions do not establish historical collector settings."
            )
            window = {"from": selection.start, "to": selection.end} if selection.start else {}
            sessions = acquire(
                route("test-runs/{id}/user-sessions", id=result_id), "sessions", True, window
            )
            for session in sessions:
                acquire(
                    route(
                        "test-runs/{id}/user-sessions/{session}/app-executions",
                        id=result_id,
                        session=session["id"],
                    ),
                    "executions",
                    True,
                    window,
                )
            acquire(
                route("test-runs/{id}/measurements", id=result_id),
                "measurements",
                True,
                {**window, "include": "all"},
            )
            acquire(route("test-runs/{id}/events", id=result_id), "events", True, window)
            historical = run.get("testConfigurationSnapshot") or {}
            metric_settings = run if selection.test_type == "ContinuousTest" else historical
            metric_path = route("user-session-metrics/{id}", id=result_id)
            if metric_settings.get("sessionMetricsEnabled") is False:
                manifest["endpoints"].append(
                    {
                        "path": metric_path,
                        "query": window,
                        "status": "disabled",
                        "count": None,
                        "reason": "Source configuration explicitly disables session metrics",
                        "configuration_scope": "current"
                        if selection.test_type == "ContinuousTest"
                        else "historical",
                    }
                )
            else:
                first_metric = len(tables["session_metrics"])
                acquire(metric_path, "session_metrics", True, window, True)
                for row in tables["session_metrics"][first_metric:]:
                    row["_selected_result_id"] = result_id
                    if row.get("testRunId") is None:
                        row["testRunId"] = result_id
                        row["_testRunId_from_endpoint"] = True
            if selection.test_type != "ApplicationTest":
                acquire(
                    route("test-runs/{id}/eux-results", id=result_id),
                    "eux",
                    params=window,
                    optional=True,
                )
        manifest["status"] = (
            "partial"
            if any(e["status"] in ("failed", "partial") for e in manifest["endpoints"])
            else "complete"
        )
    except (ToolkitError, KeyboardInterrupt, KeyError, TypeError, ValueError) as exc:
        manifest["status"] = (
            "partial"
            if any(e["status"] in ("complete", "empty", "partial") for e in manifest["endpoints"])
            else "failed"
        )
        manifest["error"] = (
            str(exc)
            if isinstance(exc, ToolkitError)
            else "Cancelled"
            if isinstance(exc, KeyboardInterrupt)
            else "Malformed source response"
        )
        finalize(directory, manifest, tables)
        if isinstance(exc, KeyboardInterrupt):
            raise
        raise ToolkitError(
            "Capture incomplete. Inspect manifest endpoint outcomes; recapture to a new directory."
        ) from None
    finalize(directory, manifest, tables)
    if manifest["status"] != "complete":
        raise ToolkitError(
            "Capture incomplete. Inspect manifest endpoint outcomes; recapture to a new directory."
        )
    return manifest


def verify_capture(directory: Path) -> dict[str, Any]:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "capture/1":
        raise ToolkitError("Unsupported capture contract.")
    for name, digest in manifest["files"].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            raise ToolkitError("Capture file missing or outside capture directory.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ToolkitError("Capture hash mismatch; evidence changed.")
    return manifest


def load_table(directory: Path, table: str) -> list[dict[str, Any]]:
    if table not in TABLES:
        raise ToolkitError("Unknown table.")
    return json.loads((directory / "normalized" / f"{table}.json").read_text(encoding="utf-8"))
