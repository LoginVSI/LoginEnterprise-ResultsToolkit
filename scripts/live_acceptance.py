"""Bounded read-only selected-Load acceptance with saved native credentials."""

import argparse
import json
from pathlib import Path

from le_results.auth import resolve_token
from le_results.client import Client
from le_results.compare import compare
from le_results.contracts import route
from le_results.errors import ToolkitError
from le_results.evidence import capture, verify_capture, write_json
from le_results.profiles import ProfileStore
from le_results.report import build_report
from le_results.selection import Selection


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--comparison-config", type=Path)
    args = parser.parse_args()
    if args.out.exists() and any(args.out.iterdir()):
        raise ToolkitError("Acceptance destination must be empty.")
    profile = ProfileStore().get(args.profile)
    with Client(
        profile, resolve_token(profile), deadline_seconds=300, max_requests=200, max_pages=10
    ) as client:
        recent = client.pages(
            "tests/test-runs",
            {"testType": "loadTest", "orderBy": "created", "direction": "desc"},
            limit=20,
        )
        write_json(args.out / "discovery.json", {"bounded": True, "limit": 20, "rows": recent})
        completed = [
            r
            for r in recent
            if r.get("type") == "LoadTest" and r.get("state") == "completed" and r.get("finished")
        ][:5]
        if not completed:
            write_json(
                args.out / "acceptance.json",
                {"status": "no-completed-run-in-subset", "live_comparison": "pending"},
            )
            return 2
        details = [
            client.get(
                route("test-runs/{id}", id=r["id"]), {"include": "testRunConfigurationSnapshot"}
            )
            for r in completed
        ]
        keys = (
            "workloadSteps",
            "numberOfSessions",
            "testDurationInMinutes",
            "sessionMetricDefinitions",
            "sessionMetricScheduleRate",
            "applicationDebugModeEnabled",
            "connectorProperties",
            "rampUpDurationInMinutes",
            "rampDownDurationInMinutes",
            "euxEnabled",
            "sessionMetricsEnabled",
            "productVersion",
            "environmentId",
            "launcherGroups",
            "accountGroups",
        )

        def compatible(left, right):
            a, b = left.get("testConfigurationSnapshot"), right.get("testConfigurationSnapshot")
            return (
                isinstance(a, dict)
                and isinstance(b, dict)
                and all(a.get(k) == b.get(k) for k in keys)
                and a.get("workloadSteps") is not None
            )

        chosen = [details[0]]
        for index, latest in enumerate(details):
            for earlier in details[index + 1 :]:
                if compatible(earlier, latest):
                    chosen = [earlier, latest]
                    break
            if len(chosen) == 2:
                break
        write_json(
            args.out / "selection-reasons.json",
            {
                "screened_ids": [r["id"] for r in details],
                "selected_ids": [r["id"] for r in chosen],
                "compatibility_keys": keys,
                "reason": "First compatible completed pair in recency-ordered bounded candidates; no selection by performance outcome.",
                "limitations": "Review retained workload completion, observation coverage and source identity; names do not establish OS or causality.",
            },
        )
        captures = []
        for index, run in enumerate(chosen):
            label = "baseline" if index == 0 else "candidate"
            target = args.out / label
            try:
                manifest = capture(client, Selection("LoadTest", [run["id"]]), target)
            except ToolkitError:
                if not (target / "manifest.json").exists():
                    raise
                manifest = verify_capture(target)
            captures.append(
                {
                    "role": label,
                    "id": run["id"],
                    "status": manifest["status"],
                    "table_counts": manifest["table_counts"],
                    "appliance_version": manifest["appliance_version"],
                }
            )
        result = {
            "status": "export-verified"
            if all(c["status"] == "complete" for c in captures)
            else "partial",
            "captures": captures,
            "live_comparison": "pending reviewed metric units/configuration"
            if len(chosen) == 2
            else "no-compatible-pair-in-bounded-subset",
            "Desktop_validation": "pending",
            "OS_identity": "not inferred",
        }
        if len(chosen) == 2 and args.comparison_config and result["status"] == "export-verified":
            config = json.loads(args.comparison_config.read_text(encoding="utf-8"))
            config["baseline"]["ids"] = [chosen[0]["id"]]
            config["candidate"]["ids"] = [chosen[1]["id"]]
            write_json(args.out / "resolved-comparison-config.json", config)
            comparison = compare(args.out / "baseline", args.out / "candidate", config)
            write_json(args.out / "comparison.json", comparison)
            build_report(comparison, args.out / "report")
            result["live_comparison"] = (
                "engine-comparison-completed; independent source checks still required"
            )
        write_json(args.out / "acceptance.json", result)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "export-verified" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ToolkitError as exc:
        print(str(exc))
        raise SystemExit(2) from None
