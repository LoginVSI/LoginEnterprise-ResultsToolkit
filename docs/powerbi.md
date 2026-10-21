# Power BI reporting

Power BI is the first reporting adapter, not the engine's only destination. The builder produces editable PBIP/PBIR reports, model.bim definitions, M queries and a report specification. Supported visuals are a comparison table, unit slicer, change chart and coverage table. Desktop 2.159.883.0 x64 is the observed 20 October installation; the earlier target was 2.158.1304.0. Public schema validation and M parsing do not substitute for Desktop execution.

The opt-in [engineering review layout](review-demo.md) adds a 16:9 overview with native summary cards, source-unit timing bars, signed percentage changes and a separate evidence page. It uses the same verified comparison as the portable HTML. New layout acceptance remains separate from the earlier owner-tested projects.

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

## Single-source and resource evidence

`examples/continuous-selected-report.json` is an editable `live-selection/1` example for exactly one ID. The builder emits `acquisition/2` and observed mean/sample/missing/failure measures without comparison deltas. The rebuilt connector supports both acquisition versions. Choose a short window: every underlying resource group is downloaded before metric matching, and the connector still limits each sequence to 200 rows. A selected CPU alone does not bypass that resource-row bound.

Finite reports include numeric timer and resource source tables with unit, field, instance, timestamp and session reference. HTML caps each visible source table at 500 rows; full evidence remains bundled. Source-type mixtures or integers that cannot be represented exactly in numeric report columns are refused. All snapshot partitions use local files and need no appliance credential at refresh. This source inspection does not establish actual Desktop execution.

## Observed Desktop acceptance and connector loading, 20 October 2026

One retained-data snapshot was owner-tested: open, refresh, populated timing/resource/coverage tables, visual resize, save and reopen. The original edits were preserved. Its M sources are local files; a forced offline Desktop network test was not observed. One fixed-window live project completed two owner-observed refreshes and save/reopen after the fixes below. This is project-specific acceptance, not all-build, rolling or new-observation proof. Source-reported timing units remain unconfirmed.

The observed x64 Desktop installation is 2.159.883.0. Its installed loader assembly contains `Power BI Desktop\Custom Connectors`; the toolkit was initially in the other user folder and `ResultsToolkit.Rows` was unrecognized. A single registration in the build-indicated folder resolved loading, confirmed by the owner's Key prompt. The separate LE-PBI-Connector was left intact. Current Microsoft guidance names `[Documents]\Microsoft Power BI Desktop\Custom Connectors`; do not scatter copies across both folders. Resolve effective Documents with `[Environment]::GetFolderPath('MyDocuments')`, check the installed build and actual Get Data/Key behavior. The installer defaults to the observed legacy folder; `-ConnectorFolder MicrosoftPowerBI` explicitly selects Microsoft's documented alternative. Its backup/diagnosis is not host-loading proof. No extension policy or machine trust is changed.

After Key enrollment, runtime rejected `Table.FromRecords` with a required-field table type plus `MissingField.UseNull`. The constructor now uses `MissingField.Error`: every constructed Row already contains all fields, optional values remain explicit nulls and missing required fields fail. The existing cell-error/identity barriers remain. Owner refresh success verifies this case; broader negative runtime fixtures remain separate.

Snapshots need no toolkit connector at refresh. Live reporting needs the toolkit connector, not the separate LE-PBI-Connector, and separate Power Query Key/native HTTPS trust. Do not repeat security-policy toggles when approval is already configured. Never embed a token or bypass certificate/hostname checks. Historical refresh is not new-data ingestion.

For aggregate views, the metric-key guard now excludes metadata rows; unit selection and metric/instance identity guards remain. Read-only queries against the accepted live model reconcile actual row-scoped means/counts and the corrected query-scoped guard, including BLANK no-match/zero-baseline cases. Existing generated projects keep their original measures. Regenerate into a new folder or review/apply the one measure expression explicitly; preserve Desktop edits. Do not infer that regeneration has itself been opened/refreshed.

The installer does not unblock downloads by default. `-UnblockDownloadedPackage` is an explicit file-only opt-in and is reported; it changes no global policy. Compare the reviewed RC checksum with `-ExpectedSha256 HEX_DIGEST`. Exact archive entries and export checks are consistency checks, not signing/trust certification. Local script execution follows organizational policy; do not weaken execution policy to run it.
