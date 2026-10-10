# Capability boundaries

| Test model | Selection | Retrieved evidence | Comparison boundary |
|---|---|---|---|
| Load | Completed run UUIDs | Run/configuration snapshot, sessions, executions, events, timers, available session metrics/EUX, source score states | Explicit baseline/candidate and metric definitions; compare workload, concurrency, duration and coverage |
| Application | Completed run UUIDs, including failed results | Run/configuration snapshot, successful/failed sessions and executions, events and available timings | No EUX or VSImax; run orchestration success does not establish execution success |
| Continuous | Test UUIDs with an explicit fixed or resolved rolling window | Current test configuration, windowed sessions/executions/events/timers/session metrics/EUX | No invented discrete run IDs; some result paths name the test identity testRunId; live mapping still needs proof |
| Single-user Desktop Load | Completed Load run UUID | Same Load retrieval where enabled | Guide documents no login process, one user, EUX/session metrics/PDF capability and hidden VSImax users; capacity comparison is not meaningful |

Core capture, comparison and report generation have offline regressions. Appliance behavior is not yet verified against 6.9.2. The Desktop Load rules come from the September 2026 guide, page 524, and the v8-preview `isDesktopTestRun` field; they are not a live observation.

The report builder supports numeric timer/resource comparisons, metric/group tables, unit filters, change charts, and coverage/failure tables. It preserves vendor EUX/VSImax objects but does not calculate EUX, compare censored capacity as an exact value, infer operating systems, prove causality, or run tests. Imported status sentinel timers are excluded from arithmetic comparisons.

Snapshots include raw evidence and normalized source datasets. The refreshable adapter is a narrower reporting view with source records retained as JSON, explicit metric identity and observation grain. It has source/syntax/schema checks; Mashup execution, connector loading and Desktop refresh are separate pending acceptance tasks. Service/gateway refresh, streaming, deployment, incremental ingestion and InfluxDB/Grafana are outside the implemented preview.
