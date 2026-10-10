# Start with a synthetic comparison

Use Python 3.11 or newer. Native Windows Python 3.14.8 is the locally exercised runtime. Hosted platform checks are tracked in progress.md. Installation downloads dependencies; the walkthrough itself makes no appliance requests and needs no AI subscription.

In a fresh checkout of the preview branch, use PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\le-results.exe demo --out artifacts\migration
.\.venv\Scripts\le-results.exe compare --baseline artifacts\migration\baseline --candidate artifacts\migration\candidate --config artifacts\migration\compare.json --out artifacts\migration\comparison.json
.\.venv\Scripts\le-results.exe report --comparison artifacts\migration\comparison.json --config examples\report.json --out artifacts\migration\report
.\.venv\Scripts\le-results.exe verify artifacts\migration\baseline
```

On Linux/macOS, create `.venv` with `python3 -m venv .venv`, then use `.venv/bin/python` and `.venv/bin/le-results` for the same commands. This is a supported design target; native credential persistence requires a separately verified provider on each platform. An optional uv installation can use `uv pip install --require-hashes -r requirements.lock` followed by `uv pip install --no-deps -e .`; pip remains the straightforward fallback.

Open `artifacts/migration/report/report.html` in a browser. The baseline values are 100, 120 and 140; the candidate values are 110, 130 and 150. The means are 120 and 130, with absolute change 10 and relative change 8.3333%. One candidate execution failed. These are synthetic values, not measurements of either Windows version.

The same directory contains `Results.pbip`, editable report/model files, Power Query sources, copied evidence and local datasets. It requires no appliance connection. Follow [Desktop validation](powerbi.md) before treating it as a verified Power BI report. Generation uses absolute local file paths; regenerate after moving the bundle. Captures and report destinations must be empty to avoid replacing evidence.

For a security-agent example, use a different destination:

```powershell
.\.venv\Scripts\le-results.exe demo --scenario security-agent --out artifacts\security-agent
```

## Add an appliance

```powershell
.\.venv\Scripts\le-results.exe profile add lab --url https://appliance.example.com --api-version v8-preview
.\.venv\Scripts\le-results.exe auth set --profile lab
.\.venv\Scripts\le-results.exe auth status --profile lab
.\.venv\Scripts\le-results.exe doctor --profile lab
```

Replace the example origin with your appliance origin. It must be HTTPS without a path, query, fragment or embedded credential. The engine adds the documented API root. Profiles go outside the checkout, under `%LOCALAPPDATA%\LoginVSI\ResultsToolkit` on Windows or the platform application configuration directory elsewhere. The token goes into a verified native credential store, never the profile file.

`auth set` requires hidden input in a normal terminal. Never put the token in chat, a command argument, a source file or a Power BI parameter. Use `auth set --replace --profile lab` to replace it, or `auth delete --profile lab` to delete it. `profile add --replace` changes nonsecret configuration without carrying a credential to a different origin.

## Select and export existing results

```powershell
.\.venv\Scripts\le-results.exe discover --profile lab --kind runs --test-type LoadTest --limit 20 --out .private\recent-load.json
.\.venv\Scripts\le-results.exe select --test-type LoadTest --id REPLACE_WITH_COMPLETED_RUN_UUID --out .private\selection.json
.\.venv\Scripts\le-results.exe export --profile lab --selection .private\selection.json --out .private\captures\selected-load
```

Inspect the recent subset, resolve ambiguous names, and record actual IDs. Choose completed runs. Application uses `--test-type ApplicationTest` and retains successful and failed results, executions, events and available measurements. Continuous uses `--kind tests`, test IDs and a window:

```powershell
.\.venv\Scripts\le-results.exe select --test-type ContinuousTest --id REPLACE_WITH_TEST_UUID --from 2026-10-01T00:00:00Z --to 2026-10-02T00:00:00Z --out .private\continuous-selection.json
```

`--rolling-hours 24` can replace fixed boundaries for Continuous. The CLI resolves it once when creating the selection file. Recreate the selection for a later capture. Report refresh resolves its own rolling window once per query evaluation.

Copy the demo comparison config into `.private/`, replace its labels, IDs and metric definition with verified values, then run `compare` and `report` against your captures. A test name does not establish OS identity. The dictionary explains unit, grain and sample rules.

Windows users may call the thin wrapper:

```powershell
.\scripts\Invoke-LEResults.ps1 doctor --profile lab --offline
```

The wrapper uses the checkout's native Windows Python environment. It does not invoke WSL or assume vault sharing. CLI exit codes are 0 for a completed operation, 2 for a safe diagnostic/failure, and 130 for cancellation. A complete retrieval does not mean the tested workload succeeded.
