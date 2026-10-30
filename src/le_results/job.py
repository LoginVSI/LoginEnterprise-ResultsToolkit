"""Bounded one-shot capture/report job for an OS scheduler. No daemon, no schedule registration.

A run stages everything, then publishes the complete directory with one rename. Failed or partial
attempts are kept apart under failed/ and never become latest. status.json separates the last
attempt, the last success and the latest source observation so a successful run over stale data
is visible as stale.
"""

import contextlib
import json
import os
import re
import shutil
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .client import Client
from .compare import compare
from .errors import ToolkitError
from .evidence import capture, load_table, verify_capture, write_json
from .report import build_report
from .selection import Selection, rolling, utc

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
STAMP = re.compile(r"^\d{8}T\d{6}Z(-\d+)?$")
ROLES = ("baseline", "candidate")
ALLOWED = {
    "schema_version",
    "name",
    "profile",
    "baseline_selection",
    "candidate_selection",
    "baseline_capture",
    "candidate_capture",
    "rolling_hours",
    "comparison",
    "report",
    "pdf",
    "keep_runs",
    "keep_failed",
    "lock_stale_hours",
    "limits",
}
LIMITS = {"max_requests", "max_pages", "page_size", "timeout", "deadline"}
HISTORY = 20
LOCK_STALE_HOURS = 3  # a scheduler time limit kills a run without cleanup
OBSERVED = (
    ("measurements", "timestamp_utc"),
    ("session_metrics", "timestamp_utc"),
    ("eux", "timestamp_utc"),
)

ClientFactory = Callable[[str, dict[str, Any]], AbstractContextManager[Client]]


def load_job(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or config.get("schema_version") != "job/1":
        raise ToolkitError("Expected a job/1 configuration.")
    if set(config) - ALLOWED:
        raise ToolkitError("Unknown job setting: " + ", ".join(sorted(set(config) - ALLOWED)))
    if not isinstance(config.get("name"), str) or not NAME.match(config["name"]):
        raise ToolkitError("Job name uses lowercase letters, digits and hyphens (max 63).")
    live = sum(f"{r}_selection" in config for r in ROLES)
    retained = sum(f"{r}_capture" in config for r in ROLES)
    if (live, retained) not in ((2, 0), (0, 2)):
        raise ToolkitError(
            "Give baseline_selection and candidate_selection (appliance) or baseline_capture and candidate_capture (retained evidence), not a mix."
        )
    if live and not isinstance(config.get("profile"), str):
        raise ToolkitError("Appliance jobs need a profile name; retained-capture jobs do not.")
    for key in ("comparison",):
        if not isinstance(config.get(key), str):
            raise ToolkitError(f"Job needs a {key} file path.")
    if "pdf" in config and not isinstance(config["pdf"], bool):
        raise ToolkitError("pdf is true or false.")
    if config.get("pdf") and not isinstance(config.get("report"), str):
        raise ToolkitError("A PDF is a print of the HTML report; set report as well.")
    stale_hours = config.get("lock_stale_hours")
    if stale_hours is not None and (
        type(stale_hours) not in (int, float) or isinstance(stale_hours, bool) or stale_hours <= 0
    ):
        raise ToolkitError("lock_stale_hours must be a positive number.")
    for key in ("keep_runs", "keep_failed"):
        if key in config and (type(config[key]) is not int or config[key] < 1):
            raise ToolkitError(f"{key} must be a positive integer.")
    hours = config.get("rolling_hours")
    if hours is not None and (type(hours) not in (int, float) or isinstance(hours, bool)):
        raise ToolkitError("rolling_hours must be a number.")
    limits = config.get("limits", {})
    if not isinstance(limits, dict) or set(limits) - LIMITS:
        raise ToolkitError("limits accepts " + ", ".join(sorted(LIMITS)) + ".")
    return config


def _resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def _lock_started(lock: Path) -> str | None:
    try:
        value = json.loads(lock.read_text(encoding="utf-8"))["started"]
        datetime.fromisoformat(value)
        return str(value)
    except (OSError, ValueError, KeyError, TypeError):
        return None


@contextlib.contextmanager
def job_lock(root: Path, now: datetime, stale_hours: float = LOCK_STALE_HOURS) -> Iterator[bool]:
    """Exclusive create. A live second run exits job_locked; a lock older than the stale limit
    (a killed scheduler task never cleans up) is reclaimed once and the run records that."""
    lock = root / ".lock"
    reclaimed = False
    for attempt in range(2):
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            started = _lock_started(lock)
            stale = started is not None and now - datetime.fromisoformat(started) > timedelta(
                hours=stale_hours
            )
            if attempt == 0 and stale and _lock_started(lock) == started:
                lock.unlink(missing_ok=True)
                reclaimed = True
                continue
            raise ToolkitError(
                "Another run holds the job lock; this run was skipped and nothing was changed."
                if not stale
                else f"The job lock is older than {stale_hours:g} hours and could not be reclaimed; delete {lock.name} in the output root if no run is active.",
                code="job_locked",
            ) from None
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump({"started": now.isoformat(), "pid": os.getpid()}, stream)
    try:
        yield reclaimed
    finally:
        lock.unlink(missing_ok=True)


def _read_status(root: Path) -> dict[str, Any]:
    path = root / "status.json"
    if not path.is_file():
        return {"schema_version": "job-status/1", "last_success": None, "history": []}
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        raise ToolkitError(
            "status.json is unreadable; keep it for diagnosis and fix or move it."
        ) from None
    if not isinstance(status, dict) or status.get("schema_version") != "job-status/1":
        raise ToolkitError("Unsupported job status contract.")
    return status


def _atomic_json(path: Path, data: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    write_json(temporary, data)
    os.replace(temporary, path)


def latest_observation(captures: dict[str, Path]) -> dict[str, Any]:
    """Newest retained source timestamp overall and per role; unparseable values are skipped.

    The stalest role is what freshness checks use, so a recent candidate cannot hide an old
    baseline.
    """
    by_role: dict[str, str | None] = {}
    for role, directory in captures.items():
        newest: str | None = None
        for table, field in OBSERVED:
            for row in load_table(directory, table):
                value = row.get(field)
                if not isinstance(value, str):
                    continue
                try:
                    value = utc(value)
                except ToolkitError:
                    continue
                if newest is None or _instant(value) > _instant(newest):
                    newest = value
        by_role[role] = newest
    known = [v for v in by_role.values() if v is not None]
    return {
        "latest_source_observation": max(known, key=_instant) if known else None,
        "stalest_role_observation": min(known, key=_instant)
        if len(known) == len(by_role)
        else None,
        "observation_by_role": by_role,
        "basis": "newest measurement, session-metric or aggregate-EUX timestamp in each capture",
    }


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _stamp(now: datetime, root: Path) -> str:
    base = now.strftime("%Y%m%dT%H%M%SZ")
    used = [
        int(path.name.partition("-")[2] or 0)
        for part in ("runs", "failed", ".staging")
        if (root / part).is_dir()
        for path in (root / part).iterdir()
        if path.name == base or path.name.startswith(base + "-")
    ]
    # Strictly above every existing suffix, so a pruned name is never reused as "newest".
    return f"{base}-{max(used) + 1}" if used else base


def _prune(root: Path, part: str, keep: int | None, protect: str | None) -> None:
    if not keep or not (root / part).is_dir():
        return

    def order(path: Path) -> tuple[str, int]:
        base, _, suffix = path.name.partition("-")
        return base, int(suffix or 0)

    runs = sorted(
        (p for p in (root / part).iterdir() if p.is_dir() and STAMP.match(p.name)), key=order
    )
    for old in runs[: max(0, len(runs) - keep)]:
        if old.name != protect:
            shutil.rmtree(old, ignore_errors=True)


def run_job(
    config_path: Path,
    root: Path,
    client_factory: ClientFactory | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    renderer: Callable[[Path, Path], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    config = load_job(config_path)
    base = config_path.resolve().parent
    root.mkdir(parents=True, exist_ok=True)
    started = now()
    with job_lock(
        root, started, float(config.get("lock_stale_hours", LOCK_STALE_HOURS))
    ) as reclaimed:
        status = _read_status(root)
        stamp = _stamp(started, root)
        stage = root / ".staging" / stamp
        stage.mkdir(parents=True)
        outcome: dict[str, Any] = {"stamp": stamp, "started": started.isoformat()}
        if reclaimed:
            outcome["reclaimed_stale_lock"] = True
        try:
            summary = _execute(config, base, stage, client_factory, now, renderer)
        except (Exception, KeyboardInterrupt) as exc:
            kept = f"failed/{stamp}"
            try:
                (root / "failed").mkdir(exist_ok=True)
                os.replace(stage, root / "failed" / stamp)
            except OSError:
                kept = f".staging/{stamp}"  # a locked file must not hide the failure record
            if isinstance(exc, ToolkitError):
                error = exc.diagnostic()
            elif isinstance(exc, KeyboardInterrupt):
                error = {"code": "cancelled", "message": "Cancelled"}
            elif isinstance(exc, (OSError, ValueError, KeyError, TypeError)):
                error = {"code": "invalid_input", "message": "Invalid configuration or artifact."}
            else:
                error = {"code": "unexpected_error", "message": type(exc).__name__}
            outcome.update(finished=now().isoformat(), outcome="failed", error=error, kept=kept)
            status["last_attempt"] = outcome
            status["history"] = [*status.get("history", []), outcome][-HISTORY:]
            _atomic_json(root / "status.json", status)
            _prune(root, "failed", config.get("keep_failed"), None)
            if isinstance(exc, KeyboardInterrupt):
                raise
            if isinstance(exc, ToolkitError):
                raise ToolkitError(
                    f"Job failed ({error['code']}): {exc}. Last good output is unchanged; partial evidence is under {kept}.",
                    code=exc.code,
                ) from None
            raise ToolkitError(
                f"Job failed ({error['code']}). Last good output is unchanged; see {kept}.",
                code=str(error["code"]),
            ) from None
        (root / "runs").mkdir(exist_ok=True)
        published = root / "runs" / stamp
        write_json(stage / "job-run.json", {**summary, "stamp": stamp})
        os.replace(stage, published)  # publish the complete directory in one step
        finished = now().isoformat()
        outcome.update(finished=finished, outcome="succeeded", published=f"runs/{stamp}")
        status["last_attempt"] = outcome
        status["last_success"] = {
            "stamp": stamp,
            "finished": finished,
            "published": f"runs/{stamp}",
            "latest_source_observation": summary["latest_source_observation"],
            "stalest_role_observation": summary["stalest_role_observation"],
        }
        status["history"] = [*status.get("history", []), outcome][-HISTORY:]
        try:
            _atomic_json(root / "status.json", status)  # authoritative record first
            _atomic_json(root / "latest.json", status["last_success"])
        except OSError:
            raise ToolkitError(
                f"The run was published at runs/{stamp} but status bookkeeping failed; check disk space and permissions, then rerun.",
                code="bookkeeping",
            ) from None
        _prune(root, "runs", config.get("keep_runs"), stamp)
        return {**status["last_success"], "published": str(published)}


def _execute(
    config: dict[str, Any],
    base: Path,
    stage: Path,
    client_factory: ClientFactory | None,
    now: Callable[[], datetime],
    renderer: Callable[[Path, Path], dict[str, Any]] | None,
) -> dict[str, Any]:
    directories = {role: stage / role for role in ROLES}
    sources: dict[str, Any] = {}
    if "baseline_selection" in config:
        if client_factory is None:
            raise ToolkitError("No appliance client is available for this job.")
        with client_factory(config["profile"], config.get("limits", {})) as client:
            for role in ROLES:
                selection = Selection.read(_resolve(base, config[f"{role}_selection"]))
                if config.get("rolling_hours") is not None:
                    if selection.test_type != "ContinuousTest":
                        raise ToolkitError("rolling_hours applies only to Continuous selections.")
                    start, end = rolling(float(config["rolling_hours"]), now())
                    selection = Selection(selection.test_type, selection.ids, start, end).validate()
                sources[role] = {"window": [selection.start, selection.end], "ids": selection.ids}
                capture(client, selection, directories[role])
    else:
        for role in ROLES:
            source = _resolve(base, config[f"{role}_capture"])
            verify_capture(source)
            shutil.copytree(source, directories[role])
            sources[role] = {"retained_capture": source.name}
    manifests = {role: verify_capture(directories[role]) for role in ROLES}
    if any(m["status"] != "complete" for m in manifests.values()):
        raise ToolkitError(
            "Capture is not complete; nothing was published.", code="capture_partial"
        )
    comparison_config = json.loads(_resolve(base, config["comparison"]).read_text(encoding="utf-8"))
    result = compare(directories["baseline"], directories["candidate"], comparison_config)
    write_json(stage / "comparison.json", result)
    outputs = ["comparison.json"]
    if config.get("report"):
        report_config = json.loads(_resolve(base, config["report"]).read_text(encoding="utf-8"))
        build_report(result, stage / "report", report_config)
        outputs.append("report/")
        if config.get("pdf"):
            if renderer is None:
                from .pdf import print_report  # lazy: the browser is optional

                renderer = print_report
            renderer(stage / "report", stage / "report.pdf")
            outputs.append("report.pdf")
    observation = latest_observation({role: directories[role] for role in ROLES})
    return {
        "schema_version": "job-run/1",
        "job": config["name"],
        "mode": "appliance" if "baseline_selection" in config else "retained-captures",
        "sources": sources,
        "outputs": outputs,
        "provenance": sorted({m["provenance"] for m in manifests.values()}),
        "captured_at": {role: manifests[role]["captured_at"] for role in ROLES},
        **observation,
        "scope": "A fresh run over a fixed window or retained evidence. Latest source observation, not run time, shows how current the data is.",
    }


def job_status(
    root: Path, max_age_hours: float | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Freshness view. ok is false for never-succeeded, failed-last-attempt, lock or stale data.

    status.json is authoritative; latest.json is a convenience pointer.
    """
    status = _read_status(root)
    current = now or datetime.now(UTC)
    last, attempt = status.get("last_success"), status.get("last_attempt")
    problems: list[str] = []
    if last is None:
        problems.append("no successful run yet")
    elif not (root / str(last.get("published", ""))).is_dir():
        problems.append("the last successful run's folder is missing")
    if attempt and attempt.get("outcome") == "failed":
        problems.append("last attempt failed; the last good output is still published")
    lock = root / ".lock"
    started = _lock_started(lock) if lock.exists() else None
    if lock.exists() and (
        started is None
        or current - datetime.fromisoformat(started) > timedelta(hours=LOCK_STALE_HOURS)
    ):
        problems.append("a lock file is older than the stale limit; the next run will reclaim it")
    if last and max_age_hours is not None:
        reference = last.get("stalest_role_observation") or last.get("latest_source_observation")
        if reference is None:
            problems.append("latest source observation is unknown")
        else:
            try:
                age = current - _instant(utc(reference))
            except ToolkitError:
                problems.append("latest source observation is unreadable")
            else:
                if age > timedelta(hours=max_age_hours):
                    problems.append(
                        f"source observation is older than {max_age_hours:g} hours (the stalest side is used)"
                    )
    return {
        "ok": not problems,
        "problems": problems,
        "last_attempt": attempt,
        "last_success": last,
        "locked": lock.exists(),
    }
