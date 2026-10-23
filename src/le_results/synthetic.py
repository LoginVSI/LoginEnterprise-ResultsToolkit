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
    if scenario == "windows-review":
        review_demo(directory)
        return
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
                    "$type": "LoadTest",
                    "workloadSteps": [],
                    "testDurationInMinutes": 30,
                },
                "euxScore": {"score": None, "state": "unavailable"},
                "vsiMax": {"maxSessions": None, "state": "belowSessionCount"},
            }
        ]
        tables["sessions"] = [{"id": SESSION, "testRunId": run_id, "loginState": "succeeded"}]
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
                    "match": {"measurementId": "synthetic-open", "applicationId": APP},
                    "group_by": [],
                    "unit": "synthetic milliseconds",
                    "semantics": "duration",
                    "direction": "lower",
                }
            ],
        },
    )


def review_demo(directory: Path) -> None:
    """Three declared synthetic actions; no server response or OS benchmark claim."""
    from uuid import NAMESPACE_URL, uuid5

    from .errors import ToolkitError

    if directory.exists() and any(directory.iterdir()):
        raise ToolkitError("Demo destination must be empty.")

    def identity(name: str) -> str:
        return str(uuid5(NAMESPACE_URL, "results-toolkit-synthetic-review/" + name))

    actions: list[tuple[str, list[int], list[int | None]]] = [
        ("Open document", [900, 1000, 1100], [720, 800, 880]),
        ("Search workspace", [450, 500, 550], [450, 500, 550]),
        ("Export workbook", [1800, 2000, 2200], [2400, 2600, None]),
    ]
    for role, run_id in [("baseline", BASE), ("candidate", CANDIDATE)]:
        tables: dict[str, list[dict[str, Any]]] = {name: [] for name in TABLES}
        session = identity(role + "/session")
        tables["runs"] = [
            {
                "id": run_id,
                "testId": identity("test"),
                "type": "LoadTest",
                "state": "completed",
                "finished": "2026-09-01T10:30:00Z",
                "configuration_scope": "historical",
                "testConfigurationSnapshot": {
                    "numberOfSessions": 1,
                    "$type": "LoadTest",
                    "testDurationInMinutes": 30,
                    "workloadSteps": [],
                },
            }
        ]
        tables["sessions"] = [{"id": session, "testRunId": run_id, "loginState": "succeeded"}]
        for action_index, (action, baseline, candidate) in enumerate(actions):
            for sample, value in enumerate(baseline if role == "baseline" else candidate):
                execution = identity(f"{role}/{action}/{sample}")
                app = identity(action)
                failed = role == "candidate" and action == "Export workbook" and sample == 2
                tables["executions"].append(
                    {
                        "id": execution,
                        "testRunId": run_id,
                        "userSessionId": session,
                        "applicationId": app,
                        "state": "endedWithErrors" if failed else "ended",
                    }
                )
                if value is not None:
                    tables["measurements"].append(
                        normalize(
                            {
                                "measurementId": "action-duration",
                                "duration": value,
                                "applicationId": app,
                                "testRunId": run_id,
                                "userSessionId": session,
                                "appExecutionId": execution,
                                "timestamp": f"2026-09-01T10:{action_index * 3 + sample:02}:00Z",
                            },
                            "synthetic",
                        )
                    )
                if failed:
                    tables["events"].append(
                        {
                            "testRunId": run_id,
                            "eventType": "applicationFailure",
                            "appExecutionId": execution,
                        }
                    )
        target = directory / role
        write_json(target / "raw/synthetic.json", tables)
        finalize(
            target,
            {
                "schema_version": "capture/1",
                "api_version": "v8-preview",
                "origin": "https://appliance.example.com",
                "appliance_version": "synthetic",
                "provenance": "synthetic",
                "status": "complete",
                "captured_at": "2026-09-01T11:00:00Z",
                "selection": {"test_type": "LoadTest", "ids": [run_id], "start": None, "end": None},
                "source_granularity": "synthetic timer observations; one session per role",
                "endpoints": [],
                "warnings": [
                    "SYNTHETIC: scenario labels are declared fixture roles, not verified operating systems.",
                    "Fixture defines timing values in ms; this does not establish API timer units.",
                    "One candidate execution failed without a timing; absence is not measured zero.",
                ],
            },
            tables,
        )
    write_json(
        directory / "compare.json",
        {
            "schema_version": "comparison/1",
            "baseline": {"label": "Windows 10 baseline (SYNTHETIC)", "ids": [BASE]},
            "candidate": {"label": "Windows 11 candidate (SYNTHETIC)", "ids": [CANDIDATE]},
            "metrics": [
                {
                    "name": name,
                    "table": "measurements",
                    "value_field": "duration",
                    "match": {"measurementId": "action-duration", "applicationId": identity(name)},
                    "group_by": [],
                    "unit": "ms",
                    "semantics": "duration",
                    "direction": "lower",
                }
                for name, _, _ in actions
            ],
        },
    )
    write_json(
        directory / "fixture.json",
        {
            "provenance": "SYNTHETIC, no appliance request or Windows performance conclusion",
            "unit": "ms, explicitly authored fixture unit, not inferred from the API",
            "actions": [
                {"name": name, "baseline": base, "candidate": cand} for name, base, cand in actions
            ],
            "design": "One timing per execution is intended by this fixture. Null in this recipe means no measurement record, never a null/zero API duration. Nine executions and one session per role; observations are not independent users/devices.",
        },
    )
