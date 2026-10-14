# Power BI reporting

Power BI is the first reporting adapter, not the engine's only destination. The builder produces editable PBIP/PBIR reports, model.bim definitions, M queries and a report specification. Supported visuals are a comparison table, unit slicer, change chart and coverage table. Desktop 2.158.1304.0 is the installed target. Public schema validation and M parsing do not substitute for Desktop execution.

## Snapshot acceptance

`report-capture --capture PATH --out NEW_DIRECTORY` creates a finite editable source report for one capture. It keeps partial endpoint outcomes without inventing baseline/candidate scenarios. Reconcile source rows, session/execution relationships and failures. Timer units remain unconfirmed unless separately established.

Complete the synthetic quickstart, then open `artifacts/migration/report/Results.pbip` in Desktop. Enable the documented PBIP/PBIR preview features manually if your build requires them; the agent does not change application security/privacy settings. Click **Refresh**. The queries read files copied into the bundle, with no appliance credential or access.

Inspect the comparison table and reconcile means 120/130, absolute change 10, relative change 8.3333%, and three observations per side against `comparison.json` and the source timer rows. The coverage table must retain one candidate execution failure. Review source run/session/execution relationships and missing values. Select one unit for a meaningful chart. Save an editable project; export a PBIT through Desktop only after validation if useful. Record build, artifact/spec hashes, selected values, refresh result and discrepancies in the progress record. Generation alone is not acceptance.

The model includes numeric comparison fields, source datasets and role/run/session relationships. A before/after snapshot can reuse the same Continuous test across windows without colliding relationship keys. Report generation checks comparison values against the retained configuration and verified source captures. Older comparison artifacts need regeneration. Source CSV/JSON and `report.html` remain usable without Desktop. Moving a bundle requires regenerating local file paths.

## Refreshable acceptance

Make a reviewed nonsecret copy of `examples/live-report.json` under `.private/`. Replace the example origin, synthetic UUIDs and metric identity/unit. Do not add a token. Continuous uses test UUIDs and either fixed start/end or `rolling_hours`, as in `examples/continuous-report.json`.

```powershell
.\.venv\Scripts\python.exe scripts\build_connector.py --out artifacts\ResultsToolkit.mez
.\.venv\Scripts\le-results.exe report-live --config .private\live-report.json --out artifacts\live-report
```

Review the independently authored M source before trusting the connector. The package is an unsigned development extension. Use Microsoft's [custom connector guidance](https://learn.microsoft.com/en-us/power-bi/connect-data/desktop-connector-extensibility) and your organization's extension/signing policy to install it in Desktop's Custom Connectors directory. Security/trust configuration is a deliberate operator step; the toolkit does not change it. Restart Desktop after installing the extension, then open `Results.pbip`.

Power Query prompts for a **Key** credential for the canonical HTTPS origin. Enroll the token there once, through Desktop's own credential mechanism. The Python vault and Power Query store are separate. Never embed the token in the report configuration, M source, parameter, URL or file. The connector uses `Extension.CurrentCredential()[Key]` with `ManualCredentials=true` to construct the bearer header inside acquisition. Its source rejects exposed redirect statuses and propagates page failures; actual redirect handling needs Desktop verification.

The live model has one acquisition partition. A rolling Continuous window resolves once within that query evaluation using FixedUtcNow; subsequent refreshes resolve new windows. This is refresh-driven reporting, not streaming. M/DAX is independently implemented reporting code; the Python engine remains authoritative for reconciliation. Runtime arithmetic, credentials, redirects and error behavior need Desktop acceptance even when schemas and syntax pass.

The finite preview connector allows four selected results in total, ten sessions per result and two 100-record pages per endpoint sequence, with a five-minute deadline and three attempts per request. Exceeding a bound fails refresh rather than returning truncated success. The connector code permits at most 375 HTTP attempts in one acquisition evaluation; host credential prompts and separate TestConnection evaluations are outside that calculation. Windowed sessions union explicit `loggedIn` and `created` queries to preserve ongoing activity and failed logons. Resource paging specifies timestamp ordering. Current Continuous settings cannot establish historical resource availability. Disabled historical metrics, configured-but-empty placeholders and missing observations remain distinct. Missing counts exclude placeholders.

Large Load datasets can exceed those preview limits; use the engine's bounded exports and a snapshot instead. Session-query overlap is resolved by identity. Conflicting versions keep raw evidence and make Python capture partial; the live connector fails refresh. A session created before the window that never logged in may fall outside both server filters even if its failure occurs during the window. This API coverage gap remains explicit. Duplicate rows across pages fail acquisition because stable ordering cannot establish a unique tie-breaker by itself.

401/403 use Power Query's native credential exceptions rather than custom errors, following [Microsoft's status-code guidance](https://learn.microsoft.com/en-us/power-query/handling-status-codes). Other HTTP statuses are handled explicitly. Certificate and transport errors propagate from the host; the adapter does not mislabel every request error as a TLS failure. No Desktop prompting behavior is claimed from code review alone.

Refresh once, record the resolved window, then run a Python export/comparison for the identical IDs/window and metric definition. Reconcile timer/resource means, sample counts, missing values, units/instances, execution failures and logon states. Check a failed later page and 401/403 response in a controlled local test before claiming error semantics are runtime-verified. Refresh again to establish that acquisition occurs on subsequent Desktop refreshes. Record each result, rather than promoting a file-generation check into live-refresh evidence.

Service publication, gateway refresh, signed distribution and scheduled refresh are separate capabilities outside initial Desktop acceptance. Power Query certificate trust follows the native application/system configuration; the Python client's custom CA option is not automatically transferred.

## Validation tooling

```powershell
.\.venv\Scripts\python.exe scripts\validate_powerbi.py artifacts\live-report
node scripts\validate_m.cjs scripts\powerquery-validation adapters\powerbi\ResultsToolkit.pq artifacts\live-report\Acquisition.pq
```

The schema validator downloads only official Microsoft schema URLs into ignored local cache and records hashes there. A populated cache allows repeat validation without downloads. M validation uses Microsoft's parser, not a Mashup evaluator; install the pinned validation dependency as described in CONTRIBUTING.md. The independent audit must keep those distinctions visible.
