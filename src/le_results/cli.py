"""CLI uses explicit files for selection and report configuration."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .auth import Vault, hidden_token, resolve_token
from .client import Client
from .compare import compare
from .errors import ToolkitError
from .evidence import capture, verify_capture, write_json
from .profiles import Profile, ProfileStore, canonical_origin
from .selection import Selection, rolling
from .synthetic import demo


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="le-results", description="Unsupported community preview")
    sub = root.add_subparsers(dest="command", required=True)
    p = sub.add_parser("profile")
    ps = p.add_subparsers(dest="action", required=True)
    add = ps.add_parser("add")
    add.add_argument("name")
    add.add_argument("--url", required=True)
    add.add_argument("--api-version", choices=["v8-preview"], default="v8-preview")
    add.add_argument("--ca-bundle")
    add.add_argument("--replace", action="store_true")
    ps.add_parser("list")
    auth = sub.add_parser("auth")
    aps = auth.add_subparsers(dest="action", required=True)
    for name in ("set", "status", "delete"):
        a = aps.add_parser(name)
        a.add_argument("--profile", required=True)
        if name == "set":
            a.add_argument("--replace", action="store_true")
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--profile", required=True)
    doctor.add_argument("--offline", action="store_true")
    discovery = sub.add_parser("discover")
    discovery.add_argument("--profile", required=True)
    discovery.add_argument("--kind", choices=["tests", "runs"], default="runs")
    discovery.add_argument(
        "--test-type", choices=["LoadTest", "ApplicationTest", "ContinuousTest"], default="LoadTest"
    )
    discovery.add_argument("--limit", type=int, default=20)
    discovery.add_argument("--name", help="Exact name; ambiguous names require explicit IDs")
    discovery.add_argument("--out", type=Path, required=True)
    select = sub.add_parser("select")
    select.add_argument(
        "--test-type", choices=["LoadTest", "ApplicationTest", "ContinuousTest"], required=True
    )
    select.add_argument("--id", dest="ids", action="append", required=True)
    select.add_argument("--from", dest="start")
    select.add_argument("--to", dest="end")
    select.add_argument("--rolling-hours", type=float)
    select.add_argument("--out", type=Path, required=True)
    export = sub.add_parser("export")
    export.add_argument("--profile", required=True)
    export.add_argument("--selection", type=Path, required=True)
    export.add_argument("--out", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("capture", type=Path)
    comparison = sub.add_parser("compare")
    comparison.add_argument("--baseline", type=Path, required=True)
    comparison.add_argument("--candidate", type=Path, required=True)
    comparison.add_argument("--config", type=Path, required=True)
    comparison.add_argument("--out", type=Path, required=True)
    report = sub.add_parser("report")
    report.add_argument("--comparison", type=Path, required=True)
    report.add_argument("--config", type=Path)
    report.add_argument("--out", type=Path, required=True)
    synthetic = sub.add_parser("demo")
    synthetic.add_argument(
        "--scenario", choices=["windows-migration", "security-agent"], default="windows-migration"
    )
    synthetic.add_argument("--out", type=Path, required=True)
    live_report = sub.add_parser("report-live")
    live_report.add_argument("--config", type=Path, required=True)
    live_report.add_argument("--out", type=Path, required=True)
    return root


def run(args: argparse.Namespace) -> Any:
    store = ProfileStore()
    if args.command == "profile":
        if args.action == "list":
            return store.read()
        store.add(
            Profile(args.name, canonical_origin(args.url), args.api_version, args.ca_bundle),
            args.replace,
        )
        return {"profile": args.name, "stored": True, "credential_enrolled": False}
    if args.command == "auth":
        profile = store.get(args.profile)
        vault = Vault()
        if args.action == "set":
            if vault.get(profile) and not args.replace:
                raise ToolkitError("Credential exists; use --replace explicitly.")
            vault.set(profile, hidden_token(), args.replace)
            return {"profile": profile.name, "stored": True}
        if args.action == "delete":
            vault.delete(profile)
            return {"profile": profile.name, "deleted": True}
        return {
            "profile": profile.name,
            "credential_present": vault.get(profile) is not None,
            "backend": type(vault.backend).__name__,
            "credential_ref": profile.credential_ref,
        }
    if args.command == "doctor":
        profile = store.get(args.profile)
        vault = Vault()
        result: dict[str, Any] = {
            "profile": profile.name,
            "origin": profile.origin,
            "api_adapter": profile.api_version,
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "vault_backend": type(vault.backend).__name__,
            "credential_present": vault.get(profile) is not None,
            "tls": "trusted HTTPS",
            "live_check": "not attempted",
        }
        if not args.offline:
            with Client(profile, resolve_token(profile)) as client:
                result["appliance_version"] = client.get("system/version")
                result["live_check"] = "system/version GET succeeded"
        return result
    if args.command == "select":
        start, end = args.start, args.end
        if args.rolling_hours:
            if start or end or args.test_type != "ContinuousTest":
                raise ToolkitError(
                    "Rolling window is only for Continuous, without fixed boundaries."
                )
            start, end = rolling(args.rolling_hours)
        Selection(args.test_type, args.ids, start, end).write(args.out)
        return {"selection": str(args.out), "window_resolved_once": True}
    if args.command == "discover":
        if not 1 <= args.limit <= 100:
            raise ToolkitError("Discovery limit must be 1-100.")
        if args.test_type == "ContinuousTest" and args.kind == "runs":
            raise ToolkitError("Continuous discovery uses --kind tests and test IDs.")
        profile = store.get(args.profile)
        query = {"testType": args.test_type[0].lower() + args.test_type[1:], "direction": "desc"}
        if args.kind == "runs":
            query["orderBy"] = "created"
        with Client(profile, resolve_token(profile)) as client:
            rows = client.pages(
                "tests" if args.kind == "tests" else "tests/test-runs", query, limit=args.limit
            )
        if args.name:
            rows = [r for r in rows if r.get("name", r.get("testRunName")) == args.name]
            if len(rows) != 1:
                raise ToolkitError(
                    "Exact name has zero or multiple matches in the bounded subset. Select an ID."
                )
        write_json(
            args.out,
            {
                "schema_version": "discovery/1",
                "bounded": True,
                "limit": args.limit,
                "rows": rows,
                "note": "Names are data; IDs establish identity.",
            },
        )
        return {"out": str(args.out), "count": len(rows), "bounded": True}
    if args.command == "export":
        selection = Selection.read(args.selection)
        profile = store.get(args.profile)
        with Client(profile, resolve_token(profile)) as client:
            manifest = capture(client, selection, args.out)
        return {
            "out": str(args.out),
            "status": manifest["status"],
            "table_counts": manifest["table_counts"],
        }
    if args.command == "verify":
        manifest = verify_capture(args.capture)
        return {
            "hashes_valid": True,
            "status": manifest["status"],
            "provenance": manifest["provenance"],
        }
    if args.command == "compare":
        config = json.loads(args.config.read_text(encoding="utf-8"))
        result = compare(args.baseline, args.candidate, config)
        write_json(args.out, result)
        return {
            "out": str(args.out),
            "metric_groups": len(result["metrics"]),
            "warnings": result["warnings"],
        }
    if args.command == "report":
        from .report import build_report

        comparison = json.loads(args.comparison.read_text(encoding="utf-8"))
        config = json.loads(args.config.read_text(encoding="utf-8")) if args.config else None
        build_report(comparison, args.out, config)
        return {"out": str(args.out), "Desktop_validation": "pending"}
    if args.command == "demo":
        demo(args.out, args.scenario)
        return {"out": str(args.out), "provenance": "synthetic"}
    if args.command == "report-live":
        from .live_report import build_live_report

        build_live_report(json.loads(args.config.read_text(encoding="utf-8")), args.out)
        return {
            "out": str(args.out),
            "acquisition": "Power Query native Key credential",
            "Desktop_validation": "pending",
        }
    raise ToolkitError("Unknown command.")


def main() -> int:
    args = parser().parse_args()
    try:
        print(json.dumps(run(args), indent=2, ensure_ascii=True))
        return 0
    except ToolkitError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130
    except (OSError, ValueError, KeyError, TypeError):
        print(
            "Invalid configuration or inaccessible artifact. Review the documented contract.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
