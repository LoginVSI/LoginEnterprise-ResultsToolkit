# Contributing

Read AGENTS.md and docs/progress.md. Keep changes scoped to deterministic result evidence and report assembly. Do not add appliance mutations or claim compatibility based on a filename or generated file.

Install the development lock into an isolated environment and install the package without resolving a second dependency set:

```powershell
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe src
.\.venv\Scripts\python.exe scripts\check_public_content.py
.\.venv\Scripts\python.exe -m pip_audit --local --skip-editable
```

Tests cover actual selection/capture/comparison/report behavior, contract paths, paging/auth/TLS failures, unit and instance identity, unavailable measurements and independent numeric targets. Keep real captures and credentials out of fixtures. Synthetic values must remain labeled synthetic. Add regressions for demonstrated risks; avoid tests that only reproduce implementation wording.

Microsoft M syntax checks require Node.js 22+ and npm. These are optional development dependencies, separate from the Python customer runtime:

```powershell
npm.cmd ci --ignore-scripts --prefix scripts\powerquery-validation
node scripts\validate_m.cjs scripts\powerquery-validation
```

Update locks deliberately with `uv pip compile pyproject.toml --universal --python-version 3.11 --generate-hashes -o requirements.lock` and the corresponding `--extra dev` command. Resolve from the minimum runtime so older Python's conditional dependencies are hashed too. Review package versions and audit results. Build a wheel with `python -m build --wheel --outdir artifacts/wheels`, then run `python scripts/installation_smoke.py` with a new ignored environment path. No release or package publication is part of preview work.

Pinned CI actions use read-only repository permissions. The development lock includes current setuptools to replace vulnerable tooling seeded by older Python environments; it is not an engine runtime dependency. Native vault checks and Desktop acceptance are not replaced by hosted offline tests. Record actual findings, fixes and checks in progress.md. License terms remain an owner decision; do not copy public upstream source without established reuse rights.
