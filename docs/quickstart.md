# Start with a synthetic comparison

Want a migration-review presentation with three actions and visible failure coverage? Jump to the [three-action review](#three-action-migration-review) after installing the toolkit below.

Use Python 3.11 or newer. Native Windows Python 3.14.8 is the locally exercised runtime. Hosted platform checks are tracked in progress.md. Installation downloads dependencies; the walkthrough itself makes no appliance requests and needs no AI subscription.

In a fresh checkout of the repository, use PowerShell:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\le-results.exe demo --out artifacts\migration
.\.venv\Scripts\le-results.exe compare --baseline artifacts\migration\baseline --candidate artifacts\migration\candidate --config artifacts\migration\compare.json --out artifacts\migration\comparison.json
.\.venv\Scripts\le-results.exe report --comparison artifacts\migration\comparison.json --config examples\report.json --out artifacts\migration\report
.\.venv\Scripts\le-results.exe verify artifacts\migration\baseline
```

On Linux/macOS, create `.venv` with `python3 -m venv .venv`, then use `.venv/bin/python` and `.venv/bin/le-results` for the same commands. Hosted core checks and fresh wheel walkthroughs pass on Windows/Linux/macOS with Python 3.11 and 3.14; native credential persistence requires a separately verified provider on each platform. An optional uv installation can use `uv pip install --require-hashes -r requirements.lock` followed by `uv pip install --no-deps -e .`; pip remains the straightforward fallback.

Open `artifacts/migration/report/report.html` in a browser. The baseline values are 100, 120 and 140; the candidate values are 110, 130 and 150. The means are 120 and 130, with absolute change 10 and relative change 8.3333%. One candidate execution failed. These are synthetic values, not measurements of either Windows version.

The same directory contains `Results.pbip`, editable report/model files, Power Query sources, copied evidence and local datasets. It requires no appliance connection. Follow [Desktop validation](powerbi.md) before treating it as a verified Power BI report. Generation uses absolute local file paths; regenerate after moving the bundle. Captures and report destinations must be empty to avoid replacing evidence.

For a security-agent example, use a different destination:

```powershell
.\.venv\Scripts\le-results.exe demo --scenario security-agent --out artifacts\security-agent
```

## Three-action migration review

For a meeting-ready example with faster, unchanged and slower actions, follow the [three-action review walkthrough](review-demo.md). It uses `demo --scenario windows-review`, explicit synthetic roles and the same comparison for HTML and editable Power BI snapshots. One failed execution has no timing record.

After installation above, run these commands into new directories:

```powershell
.\.venv\Scripts\le-results.exe demo --scenario windows-review --out artifacts\review-input
.\.venv\Scripts\le-results.exe verify artifacts\review-input\baseline
.\.venv\Scripts\le-results.exe verify artifacts\review-input\candidate
.\.venv\Scripts\le-results.exe compare --baseline artifacts\review-input\baseline --candidate artifacts\review-input\candidate --config artifacts\review-input\compare.json --out artifacts\review-comparison.json
.\.venv\Scripts\le-results.exe report --comparison artifacts\review-comparison.json --config examples\review-report.json --out artifacts\review-overview
.\.venv\Scripts\le-results.exe report --comparison artifacts\review-comparison.json --config examples\review-meeting-report.json --out artifacts\review-meeting
```

Open each folder's `report.html`; `Results.pbip` is the editable local snapshot. The meeting configuration moves per-action sample detail to Evidence while retaining total matched observations (9 baseline / 8 candidate), workload coverage and the failure warning on the overview. Neither configuration establishes a Windows performance conclusion. Preserve Desktop edits and use a new folder for every regeneration.

## Add an appliance

Before importing the engine, Windows users can run `scripts/Test-LEResultsReadiness.ps1`. It checks that the selected executable starts, reports runtime/architecture and explains missing dependencies. Add `-Profile lab` for offline engine readiness, `-OutputDirectory .private\readiness` for a write check, and `-Live` for verified TLS/API diagnosis. Use `-Python PATH` when the environment is elsewhere. Missing or broken Python exits 2 with a safe bootstrap diagnostic.

Choose an explicit installed runtime when creating the environment. A runtime upgrade can leave `pyvenv.cfg` pointing at a removed executable. Preserve that environment under ignored storage, create a new `.venv` with Python 3.11 or 3.14, then reinstall the locks and toolkit. Preserve profiles and native vault enrollment outside `.venv`. Activation is optional. Use a user-local runtime and a checkout under your own writable directory; no machine PATH or global security changes are needed.

```powershell
.\.venv\Scripts\le-results.exe profile add lab --url https://appliance.example.com --api-version v8-preview
.\.venv\Scripts\le-results.exe auth set --profile lab
.\.venv\Scripts\le-results.exe auth status --profile lab
.\.venv\Scripts\le-results.exe doctor --profile lab
```

Replace the example origin with your appliance origin. It must be HTTPS without a path, query, fragment or embedded credential. The engine adds the documented API root. Profiles go outside the checkout, under `%LOCALAPPDATA%\LoginVSI\ResultsToolkit` on Windows or the platform application configuration directory elsewhere. The token goes into a verified native credential store, never the profile file.

`auth set` requires hidden input in a normal terminal. Never put the token in chat, a command argument, a source file or a Power BI parameter. Use `auth set --replace --profile lab` to replace it, or `auth delete --profile lab` to delete it. `profile add --replace` changes nonsecret configuration without carrying a credential to a different origin.

## Select and export existing results

To obtain bounded suggestions without manually collecting every GUID:

```powershell
.\.venv\Scripts\le-results.exe recommend --profile lab --limit 20 --candidates 5 --out .private\recommendations.json
```

This reviews at most 20 results/tests per model, five candidate details per model and five retained sessions per Continuous candidate, within 60 requests and a 180-second acquisition deadline. Load suggestions use matching historical configuration in recency order. Application suggestions retain available failure evidence. Continuous distinguishes enabled configuration from retained sessions and collection health. Inspect IDs, coverage and limitations before capture. A bounded subset does not prove that no suitable test exists elsewhere.

Exports accept `--max-requests 200 --max-pages 10 --page-size 100 --timeout 20 --deadline 300`. Page/record limits apply per endpoint; the request/deadline limit covers the capture. Exhausting a bound leaves partial evidence and exits 2. Ctrl+C finalizes capture evidence before exit 130. Always use a new output directory.

For one finite capture, including useful partial evidence, use:

```powershell
.\.venv\Scripts\le-results.exe report-capture --capture .private\captures\selected-load --out .private\reports\selected-load
```

This produces HTML, copied evidence, editable PBIP/PBIR/model files and source datasets without inventing a comparison. Review endpoint outcomes and failure coverage. Desktop opening/refresh is still a separate check.

Comparison normally requires complete captures. A reviewed `comparison/1` config can explicitly set `"coverage_policy": "timer-only"` when only session-metric requests failed and timing/session/execution/event acquisition completed. All configured metrics must then use the timer table. The comparison keeps partial capture status and the resource failure warning. Failed timing or failure-coverage requests still block comparison. Never label an unconfirmed timer unit milliseconds or infer a CPU improvement from missing data.

The [editable PowerShell example](../examples/customer-workflow.ps1) documents diagnosis, discovery, selected capture, comparison, snapshot and live-generation parameters. All operations call the engine. See the [prompt gallery](prompt-gallery.md) for equivalent AI requests and verification.

## Approved mirrors and offline installation

The tested installation path uses pip with the committed hash locks. For an approved package mirror, add `--index-url https://packages.example.com/simple` to the locked install command; keep mirror authentication in the package tool's approved credential mechanism. Do not put credentials in URLs or scripts. Mirror and offline deployment remain guidance until exercised in your environment.

On a connected machine with the same target platform/runtime, download the locked wheels with `python -m pip download --require-hashes -r requirements.lock --dest wheelhouse` and build the toolkit wheel. Transfer that reviewed wheelhouse and install with `python -m pip install --no-index --find-links wheelhouse --require-hashes -r requirements.lock`, followed by the toolkit wheel with `--no-deps`. Conditional platform dependencies require a wheelhouse for each target. Customers do not need the private development references.

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

## Extended customer workflows

The [workflow reference](customer-workflows.md) covers broader Continuous screening, explicit export failure exits, finite timer/resource reports, a single-source refreshable project and existing Application PDF download. Use `live-selection/1` for one Continuous ID without comparison deltas. The [optional time-series path](timeseries.md) produces files only and is not an integration prerequisite.

## Refine a selected snapshot

Use an editable finite `report/1` specification to choose source, resource and coverage tables. Keep the capture and generate a new output folder; preserve saved Desktop edits.

```powershell
le-results report-capture --capture artifacts/selected --config examples/finite-report.json --out artifacts/selected-refined
```

This has no invented baseline/candidate or delta. Unsupported visual/type inputs fail explicitly. For live loading, install one reviewed package with `powershell.exe -NoProfile -File scripts/Install-LEResultsConnector.ps1 -Package artifacts/ResultsToolkit.mez`; save/close Desktop first. `-DiagnoseOnly` reports file/export presence, not host loading. See Power BI guidance for build-specific folders and separate Key/trust.

## Optional: PDF, scheduled jobs, upgrade, removal and recovery

PDF output and scheduled jobs need nothing beyond the engine. `report-pdf` uses a browser already on the machine; see [PDF export](pdf-export.md). `job run` needs a job file and an output folder; see [scheduling](scheduling.md). To register a Windows task for your own account run `scripts/Register-LEResultsJob.ps1`, which prints a dry run by default, needs an explicit time and interval, and can create the task disabled.

First setup with a missing piece, in order:

1. `scripts/Test-LEResultsReadiness.ps1` names a missing Python, dependency or architecture problem and the next action.
2. `le-results profile add lab --url https://appliance.example.com` stores the non-secret address. Enter the token only with `le-results auth set --profile lab`, which uses hidden input and your native credential store.
3. `le-results doctor --profile lab` separates DNS, TCP, TLS and HTTP failures. Fix a certificate with the scoped trust steps in [troubleshooting](troubleshooting.md); never turn verification off.

Upgrade: install the new wheel with `pip install --upgrade` inside the project environment, rerun the readiness script and `le-results verify` on an existing capture. Captures are versioned files and older ones stay readable. Removal: delete the project environment, run `le-results auth delete --profile lab` for each profile, delete the profile configuration and remove any task with `scripts/Register-LEResultsJob.ps1 -TaskName <name> -Unregister -Apply`. Reports and captures are your files and are never deleted by these steps. Recovery after a failed run is in [scheduling](scheduling.md).
