"""Deliberately synthetic migration and security-agent examples."""

from pathlib import Path
from typing import Any

from .evidence import TABLES, finalize, normalize, write_json

BASE = "11111111-1111-4111-8111-111111111111"
CANDIDATE = "22222222-2222-4222-8222-222222222222"
APP = "33333333-3333-4333-8333-333333333333"
SESSION = "44444444-4444-4444-8444-444444444444"
EXECUTION = "55555555-5555-4555-8555-555555555555"


def demo(directory: Path, scenario: str = "windows-migration") -> None:
    if directory.exists() and any(directory.iterdir()):
        from .errors import ToolkitError

        raise ToolkitError("Demo destination must be empty.")
    for label, run_id, values in [
        ("baseline", BASE, [100, 120, 140]),
        ("candidate", CANDIDATE, [110, 130, 150]),
    ]:
        target = directory / label
        tables: dict[str, list[dict[str, Any]]] = {k: [] for k in TABLES}
        tables["runs"] = [
            {
                "id": run_id,
                "testId": APP,
                "type": "LoadTest",
                "state": "completed",
                "finished": "2026-09-01T10:30:00Z",
                "configuration_scope": "historical",
                "testConfigurationSnapshot": {
                    "numberOfSessions": 1,
                    "workload": "synthetic",
                    "testDurationInMinutes": 30,
                },
                "euxScore": {"score": None, "state": "insufficientData"},
                "vsiMax": {"maxSessions": None, "state": "notReached"},
            }
        ]
        tables["sessions"] = [{"id": SESSION, "testRunId": run_id, "loginState": "completed"}]
        tables["executions"] = [
            {
                "id": EXECUTION,
                "testRunId": run_id,
                "userSessionId": SESSION,
                "applicationId": APP,
                "state": "ended" if label == "baseline" else "endedWithErrors",
            }
        ]
        tables["measurements"] = [
            normalize(
                {
                    "measurementId": "synthetic-open",
                    "duration": value,
                    "testRunId": run_id,
                    "userSessionId": SESSION,
                    "appExecutionId": EXECUTION,
                    "applicationId": APP,
                    "timestamp": f"2026-09-01T10:0{i}:00Z",
                },
                "synthetic",
            )
            for i, value in enumerate(values)
        ]
        tables["events"] = (
            []
            if label == "baseline"
            else [
                {
                    "testRunId": run_id,
                    "eventType": "applicationFailure",
                    "appExecutionId": EXECUTION,
                }
            ]
        )
        manifest = {
            "schema_version": "capture/1",
            "api_version": "v8-preview",
            "origin": "https://appliance.example.com",
            "appliance_version": "synthetic",
            "provenance": "synthetic",
            "status": "complete",
            "captured_at": "2026-09-01T11:00:00Z",
            "selection": {"test_type": "LoadTest", "ids": [run_id], "start": None, "end": None},
            "source_granularity": "synthetic observations",
            "endpoints": [],
            "warnings": ["SYNTHETIC: no appliance or OS benchmark evidence."],
        }
        write_json(target / "raw" / "synthetic.json", tables)
        finalize(target, manifest, tables)
    labels = (
        ["Synthetic Windows 10", "Synthetic Windows 11"]
        if scenario == "windows-migration"
        else ["Synthetic agent disabled", "Synthetic agent enabled"]
    )
    write_json(
        directory / "compare.json",
        {
            "schema_version": "comparison/1",
            "baseline": {"label": labels[0], "ids": [BASE]},
            "candidate": {"label": labels[1], "ids": [CANDIDATE]},
            "metrics": [
                {
                    "name": "Synthetic document open",
                    "table": "measurements",
                    "value_field": "duration",
                    "match": {"measurementId": "synthetic-open"},
                    "group_by": [],
                    "unit": "synthetic milliseconds",
                    "semantics": "duration",
                    "direction": "lower",
                }
            ],
        },
    )
