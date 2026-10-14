# Capability boundaries

| Capability | Implemented | Offline verified | Appliance verified | Desktop/host verified |
|---|---|---|---|---|
| Python engine, CLI, Windows wrappers | Yes | Tests, lint/types, fresh wheel | Read-only CLI exercised | PowerShell 5.1/7 readiness exercised; standard-user proof separate |
| Native encrypted vault | Yes | Windows metadata/persistence and rejection tests | Existing enrollment reused | Native Linux/macOS pending |
| Diagnosis and profile trust | Yes | Real synthetic HTTPS handshakes | Strict TLS and system/version on 6.9.2 | Python trust is separate from Power Query |
| Bounded recommendations | Yes | Contract/query/selection tests | Load/Application/Continuous subset and retained sessions | Canonical skill used in current Codex host |
| Exports and hashed manifests | Yes | Paging, cancellation, failure, identity tests | New complete pair/Application/Continuous; earlier partial failures preserved | N/A |
| Explicit comparisons | Yes | Missing/zero, units, instances, failures | Complete-pair timer arithmetic independently reconciled; resources successfully empty | Desktop DAX pending |
| Finite HTML and editable snapshots | Yes | Schemas/source references, synthetic targets | Reports built from actual captures | Desktop open/refresh pending |
| Refreshable Power BI adapter | Yes | Official schemas and Microsoft M parsing | Project selects verified IDs; endpoint defects retained | Connector loading, Key enrollment, two refreshes and Mashup/DAX checks pending |
| Independent Claude review | Completed public-only review | Claude ran tests/lint/types; findings and dispositions recorded | No appliance access in audit | Separate from host skill behavior and Desktop proof |
| Service/gateway, streaming, incremental ingestion, InfluxDB/Grafana | Outside this preview | No claim | No | No |

| Test model | Evidence | Limits |
|---|---|---|
| Load | Completed run UUID, historical snapshot, current configuration, sessions/executions/events/timers, available resources/EUX and native score states | Match workload, concurrency, duration and historical definitions. Preserve failures, unfinished work and coverage. |
| Application | Completed successful/failed results, sessions/executions/events and timers | No EUX/VSImax claim. Orchestration and execution success are separate. |
| Continuous | Test UUID with fixed/resolved window, current configuration and retained observations | Enabled configuration is distinct from healthy collection. Test IDs were verified on retained result paths; no invented discrete runs. |
| Single-user Desktop Load | Same retrieval where enabled; guide documents one user/no login process | Capacity comparison is not meaningful. Special model rules are documented, not live-verified here. |

Minimal resource requests fail with HTTP 500 when optional sorting is omitted. Explicit `orderBy=timestamp` recovered requests on the observed appliance; Swagger definitions match the checked-in operation. Fresh captures contain successful empty resource envelopes. Earlier failed captures remain partial and immutable. Empty resources cannot support CPU/memory conclusions. Default comparisons reject partial captures; explicit `timer-only` policy permits only complete timing/failure evidence for every selected result when session-metric acquisition alone failed. Retained observations are not independent devices.

The API does not declare every timer unit. Unknown units, historical collector settings and retention gaps remain labeled. SetTimer can represent resources or categorical sentinels; declared status values cannot be averaged. Native EUX/VSImax states and bounds remain vendor evidence without a toolkit scoring algorithm. Names do not establish OS identity, independence or causality.

Reports support metric/group tables, unit filters, change charts and coverage. Finite reports show timer rows and endpoint outcomes. HTML relative-change scale is dimensionless. Power BI source-unit measures guard unit selection. Generation, schema/reference checks, M parsing, Desktop opening, refresh and reconciliation are separate evidence states. No PBIT is fabricated.
