"""Install a built wheel into a fresh environment and run outside src."""

import argparse
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", type=Path, default=Path(".private/wheel-smoke"))
    parser.add_argument(
        "--external", action="store_true", help="Create a fresh environment outside the checkout"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    target = (
        Path(tempfile.mkdtemp(prefix="le-results-wheel-smoke-")) / "environment"
        if args.external
        else args.environment.resolve()
    )
    if (
        not args.external and not target.is_relative_to((root / ".private").resolve())
    ) or target.exists():
        raise SystemExit("Use a new environment directory under ignored .private.")
    venv.EnvBuilder(with_pip=True).create(target)
    python = target / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--quiet",
            "--require-hashes",
            "-r",
            str(root / "requirements.lock"),
        ],
        check=True,
    )
    wheels = sorted((root / "artifacts/wheels").glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit("Build exactly one wheel under artifacts/wheels first.")
    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", "--no-deps", str(wheels[0])], check=True
    )
    run_dir = target / "walkthrough"
    run_dir.mkdir()
    subprocess.run(
        [
            str(python),
            "-I",
            "-c",
            "import le_results, pathlib, sys; assert pathlib.Path(le_results.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve())",
        ],
        cwd=run_dir,
        check=True,
    )
    subprocess.run(
        [str(python), "-I", "-m", "le_results.cli", "demo", "--out", "synthetic"],
        cwd=run_dir,
        check=True,
    )
    subprocess.run(
        [
            str(python),
            "-I",
            "-m",
            "le_results.cli",
            "compare",
            "--baseline",
            "synthetic/baseline",
            "--candidate",
            "synthetic/candidate",
            "--config",
            "synthetic/compare.json",
            "--out",
            "synthetic/comparison.json",
        ],
        cwd=run_dir,
        check=True,
    )
    subprocess.run(
        [
            str(python),
            "-I",
            "-m",
            "le_results.cli",
            "report",
            "--comparison",
            "synthetic/comparison.json",
            "--out",
            "report",
        ],
        cwd=run_dir,
        check=True,
    )
    (run_dir / "report.json").write_text(
        '{"schema_version": "report/1", "title": "Smoke", "visuals": ["comparison_table"]}',
        encoding="utf-8",
    )
    (run_dir / "job.json").write_text(
        '{"schema_version": "job/1", "name": "smoke", "baseline_capture": "synthetic/baseline", '
        '"candidate_capture": "synthetic/candidate", "comparison": "synthetic/compare.json", '
        '"report": "report.json"}',
        encoding="utf-8",
    )
    for arguments in (
        ["job", "run", "--config", "job.json", "--out-root", "jobs"],
        ["job", "status", "--out-root", "jobs"],
        ["report-pdf", "--help"],
    ):
        subprocess.run(
            [str(python), "-I", "-m", "le_results.cli", *arguments], cwd=run_dir, check=True
        )
    print(
        "Fresh wheel installation and "
        + ("outside-checkout" if args.external else "outside-src")
        + " offline workflow passed."
    )


if __name__ == "__main__":
    main()
