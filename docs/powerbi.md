# Power BI reporting

Power BI is the first reporting adapter, not the engine's only destination. The builder produces editable PBIP/PBIR reports, model.bim definitions, M queries and a report specification. Supported visuals are a comparison table, unit slicer, change chart and coverage table. Desktop 2.158.1304.0 is the installed target. Public schema validation and M parsing do not substitute for Desktop execution.

## Snapshot acceptance

`report-capture --capture PATH --out NEW_DIRECTORY` creates a finite editable source report for one capture. It keeps partial endpoint outcomes without inventing baseline/candidate scenarios. Reconcile source rows, session/execution relationships and failures. Timer units remain unconfirmed unless separately established.

Complete the synthetic quickstart, then open `artifacts/migration/report/Results.pbip` in Desktop. Enable the documented PBIP/PBIR preview features manually if your build requires them; the agent does not change application security/privacy settings. Click **Refresh**. The queries read files copied into the bundle, with no appliance credential or access.

Inspect the comparison table and reconcile means 120/130, absolute change 10, relative change 8.3333%, and three observations per side against `comparison.json` and the source timer rows. The coverage table must retain one candidate execution failure. Review source run/session/execution relationships and missing values. Select one unit for a meaningful chart. Save an editable project; export a PBIT through Desktop only after validation if useful. Record build, artifact/spec hashes, selected values, refresh result and discrepancies in the progress record. Generation alone is not acceptance.

The model includes numeric comparison fields, source datasets and compound run/session relationships. It does not join coverage summaries to observation facts. Source CSV/JSON and `report.html` remain usable without Desktop. Moving a bundle requires regenerating local file paths.

## Refreshable acceptance

Make a reviewed nonsecret copy of `examples/live-report.json` under `.private/`. Replace the example origin, synthetic UUIDs and metric identity/unit. Do not add a token. Continuous uses test UUIDs and either fixed start/end or `rolling_hours`, as in `examples/continuous-report.json`.

```powershell
.\.venv\Scripts\python.exe scripts\build_connector.py --out artifacts\ResultsToolkit.mez
.\.venv\Scripts\le-results.exe report-live --config .private\live-report.json --out artifacts\live-report
```

Review the independently authored M source before trusting the connector. The package is an unsigned development extension. Use Microsoft's [custom connector guidance](https://learn.microsoft.com/en-us/power-bi/connect-data/desktop-connector-extensibility) and your organization's extension/signing policy to install it in Desktop's Custom Connectors directory. Security/trust configuration is a deliberate operator step; the toolkit does not change it. Restart Desktop after installing the extension, then open `Results.pbip`.

Power Query prompts for a **Key** credential for the canonical HTTPS origin. Enroll the token there once, through Desktop's own credential mechanism. The Python vault and Power Query store are separate. Never embed the token in the report configuration, M source, parameter, URL or file. The connector uses `Extension.CurrentCredential()[Key]` with `ManualCredentials=true` to construct the bearer header inside acquisition. Redirects are refused and failed pages propagate errors.

The live model has one acquisition partition. A rolling Continuous window resolves once within that query evaluation using FixedUtcNow; subsequent refreshes resolve new windows. This is refresh-driven reporting, not streaming. The adapter uses the same observation-mean, explicit unit and missing/zero-baseline rules as the engine. M source/syntax and schema checks are available; runtime parity is still a Desktop acceptance task.

Refresh once, record the resolved window, then run a Python export/comparison for the identical IDs/window and metric definition. Reconcile timer/resource means, sample counts, missing values, units/instances, execution failures and logon states. Check a failed later page and 401/403 response in a controlled local test before claiming error semantics are runtime-verified. Refresh again to establish that acquisition occurs on subsequent Desktop refreshes. Record each result, rather than promoting a file-generation check into live-refresh evidence.

Service publication, gateway refresh, signed distribution and scheduled refresh are separate capabilities outside initial Desktop acceptance. Power Query certificate trust follows the native application/system configuration; the Python client's custom CA option is not automatically transferred.

## Validation tooling

```powershell
.\.venv\Scripts\python.exe scripts\validate_powerbi.py artifacts\live-report
node scripts\validate_m.cjs .private\powerquery-validation adapters\powerbi\ResultsToolkit.pq artifacts\live-report\Acquisition.pq
```

The schema validator downloads only official Microsoft schema URLs into ignored local cache and records hashes there. A populated cache allows repeat validation without downloads. M validation uses Microsoft's parser, not a Mashup evaluator; install the pinned validation dependency as described in CONTRIBUTING.md. The independent audit must keep those distinctions visible.
