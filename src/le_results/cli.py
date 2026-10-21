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
    doctor.add_argument("--out", type=Path, help="Check destination writability")
    certificate = sub.add_parser(
        "certificate", help="Credential-free inspection; no trust enrollment"
    )
    certificate.add_argument("--profile", required=True)
    certificate.add_argument("--out", type=Path, required=True)
    trust = sub.add_parser("trust", help="Configure independently approved profile trust")
    trust.add_argument("--profile", required=True)
    trust.add_argument("--ca-bundle", type=Path)
    trust.add_argument("--approved-sha256", action="append", default=[])
    trust.add_argument("--remove", action="store_true")
    discovery = sub.add_parser("discover")
    discovery.add_argument("--profile", required=True)
    discovery.add_argument("--kind", choices=["tests", "runs"], default="runs")
    discovery.add_argument(
        "--test-type", choices=["LoadTest", "ApplicationTest", "ContinuousTest"], default="LoadTest"
    )
    discovery.add_argument("--limit", type=int, default=20)
    discovery.add_argument("--name", help="Exact name; ambiguous names require explicit IDs")
    discovery.add_argument("--out", type=Path, required=True)
    recommendations = sub.add_parser("recommend", help="Bounded representative result suggestions")
    recommendations.add_argument("--profile", required=True)
    recommendations.add_argument("--limit", type=int, default=20)
    recommendations.add_argument("--candidates", type=int, default=5)
    recommendations.add_argument("--continuous-candidates", type=int, default=5)
    recommendations.add_argument("--out", type=Path, required=True)
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
    export.add_argument("--max-requests", type=int, default=200)
    export.add_argument("--max-pages", type=int, default=10)
    export.add_argument("--page-size", type=int, default=100)
    export.add_argument("--timeout", type=float, default=20)
    export.add_argument("--deadline", type=float, default=300)
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
    finite = sub.add_parser("report-capture", help="Finite evidence report without a comparison")
    finite.add_argument("--capture", type=Path, required=True)
    finite.add_argument("--out", type=Path, required=True)
    finite.add_argument("--title", default="Selected result evidence")
    finite.add_argument("--config", type=Path, help="Editable finite report/1 specification")
    synthetic = sub.add_parser("demo")
    synthetic.add_argument(
        "--scenario", choices=["windows-migration", "security-agent"], default="windows-migration"
    )
    synthetic.add_argument("--out", type=Path, required=True)
    live_report = sub.add_parser("report-live")
    live_report.add_argument("--config", type=Path, required=True)
    live_report.add_argument("--out", type=Path, required=True)
    native_pdf = sub.add_parser(
        "download-pdf", help="Read an existing completed Application report"
    )
    native_pdf.add_argument("--profile", required=True)
    native_pdf.add_argument("--application-run-id", required=True)
    native_pdf.add_argument("--out", type=Path, required=True)
    native_pdf.add_argument("--max-mib", type=int, default=16)
    lp = sub.add_parser(
        "export-line-protocol", help="Optional finite dry-run file export; no database writes"
    )
    lp.add_argument("--capture", type=Path, required=True)
    lp.add_argument("--out", type=Path, required=True)
    lp.add_argument("--max-records", type=int, default=10000)
    return root


def run(args: argparse.Namespace) -> Any:
    store = ProfileStore()
    if args.command == "profile":
        if args.action == "list":
            return store.read()
        store.add(
            Profile(args.name, canonical_origin(args.url), args.api_version),
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
        from .diagnostics import doctor

        return doctor(store, args.profile, args.offline, args.out)
    if args.command == "certificate":
        from .diagnostics import inspect_certificate

        return inspect_certificate(store.get(args.profile), args.out)
    if args.command == "trust":
        from .diagnostics import approve_trust

        if args.remove:
            if args.ca_bundle or args.approved_sha256:
                raise ToolkitError("Use --remove without trust-file arguments.")
            profile = store.get(args.profile)
            store.add(Profile(profile.name, profile.origin, profile.api_version), replace=True)
            return {"profile": profile.name, "trust_file": None, "tls": "not attempted"}
        if not args.ca_bundle or not args.approved_sha256:
            raise ToolkitError(
                "Supply --ca-bundle and independently approved --approved-sha256 for each certificate."
            )
        return approve_trust(store, args.profile, args.ca_bundle, args.approved_sha256)
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
        with Client(profile, resolve_token(profile), max_requests=20, max_pages=5) as client:
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
    if args.command == "recommend":
        from .recommend import recommend

        profile = store.get(args.profile)
        with Client(
            profile,
            resolve_token(profile),
            max_requests=250,
            max_pages=5,
            page_size=100,
            retries=0,
            deadline_seconds=300,
        ) as client:
            result = recommend(client, args.limit, args.candidates, args.continuous_candidates)
        write_json(args.out, result)
        return {
            "out": str(args.out),
            "requests_used": result["requests_used"],
            "ok": result["status"] != "partial",
            "status": result["status"],
            "failed_probes": result["failed_probes"],
            "bounds_exhausted": result["bounds_exhausted"],
            "models": {
                k: {"selection": v["selection"], "reason": v["reason"]}
                for k, v in result["models"].items()
            },
        }
    if args.command == "export":
        selection = Selection.read(args.selection)
        profile = store.get(args.profile)
        with Client(
            profile,
            resolve_token(profile),
            max_requests=args.max_requests,
            max_pages=args.max_pages,
            page_size=args.page_size,
            timeout=args.timeout,
            deadline_seconds=args.deadline,
        ) as client:
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
    if args.command == "report-capture":
        from .report import build_capture_report

        config = json.loads(args.config.read_text(encoding="utf-8")) if args.config else None
        build_capture_report(args.capture, args.out, args.title, config)
        return {
            "out": str(args.out),
            "scope": "finite capture evidence",
            "Desktop_validation": "pending",
        }
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
    if args.command == "download-pdf":
        import hashlib

        from .contracts import identifier

        if args.out.exists():
            raise ToolkitError("PDF destination must be new; preserve prior evidence.")
        if not 1 <= args.max_mib <= 64:
            raise ToolkitError("PDF maximum must be 1-64 MiB.")
        profile = store.get(args.profile)
        with Client(
            profile, resolve_token(profile), max_requests=4, retries=0, deadline_seconds=90
        ) as client:
            data = client.get_application_pdf(
                identifier(args.application_run_id), args.max_mib * 1024 * 1024
            )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        try:
            with args.out.open("xb") as stream:
                stream.write(data)
        except OSError:
            raise ToolkitError(
                "Native PDF write failed; the new destination may be partial. Preserve it and retry a new path.",
                code="output_write",
            ) from None
        return {
            "out": str(args.out),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "scope": "native Application GET report; no report job created",
        }
    if args.command == "export-line-protocol":
        from .timeseries import export_line_protocol

        return export_line_protocol(args.capture, args.out, args.max_records)
    raise ToolkitError("Unknown command.")


def main() -> int:
    args = parser().parse_args()
    try:
        result = run(args)
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 2 if isinstance(result, dict) and result.get("ok") is False else 0
    except ToolkitError as exc:
        print(json.dumps({"ok": False, "error": exc.diagnostic()}), file=sys.stderr)
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
