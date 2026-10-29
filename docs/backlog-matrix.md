# Backlog reconciliation, 28 October 2026

Dispositions: **done** (implemented and offline verified), **implement now** (done in this pass), **feasibility** (assessed only), **limitation** (documented), **blocked** (needs environment or owner), **deferred** (deliberate, with reason). All items are in this repository unless noted. "Offline" means synthetic fixtures and tests, not an appliance.

| Item | Customer outcome | Implementation | Evidence | Gap or dependency | Disposition | Next acceptance step |
|---|---|---|---|---|---|---|
| Native versus aggregate EUX | Trust which score is the vendor's whole-run value | `native_scores` table from the Load overview, `score_grain` labels, native comparison with state gating, `grain` in HTML and snapshot | 15 offline tests; [native-scores](native-scores.md) | Appliance reconciliation not run. Connector does not retrieve the overview | **done** (offline); appliance **blocked** on read-only approval; connector **deferred** | Capture one completed Load run and match four result IDs with the UI |
| Other metric identity and state | No wrong averages | Existing timer/session identity rules; native rows refuse grouping and cross-run means | Existing and new tests | None new | **done** | None |
| Custom PDF | Executive PDF without a manual print | `report-pdf` with diagnostics, verification, receipt | 13 tests, real Edge print, inspected pages; [pdf-export](pdf-export.md) | Only Edge on Windows exercised | **done**; other platforms **blocked** (hardware) | Run `LE_RESULTS_TEST_BROWSER=1` on Linux and macOS |
| Scheduled capture and report | Unattended refresh with safe failure | `job run` and `job status` | 19 job tests; [scheduling](scheduling.md) | No appliance run; no task registered | **done** (offline); registration **owner action** | Run once against an approved profile under the scheduled account |
| Connector gateway and Service compatibility | Know what refreshes in the Power BI Service | Documented limits only | Existing docs | Needs tenant and gateway; not in scope without owner destination | **blocked** | Owner picks a tenant and gateway, then run a Toolkit-specific acceptance |
| Connector freshness visibility | See how current data is | CLI job status carries `latest_source_observation`; connector has none | Tests | Connector would need a freshness table | **deferred** | Add a freshness query to the connector when native overview lands there |
| Toolkit incremental ingestion | Cheaper repeat captures | None. Assessment below | Capture and mapper reading | No stable per-observation ID; endpoint boundary inclusion unconfirmed; request count grows with sessions | **deferred** | See "Incremental ingestion" |
| Power BI incremental refresh | Faster large refresh | None | None | Needs RangeStart/RangeEnd parameters and a source that supports them; independent of the Python checkpoint | **deferred** | Design after a customer volume need |
| Grafana without a database | Chart exports in Grafana | Assessment, recipe plan | [assessment](grafana-influxdb-assessment.md) | Runtime unverified | **feasibility** | Synthetic proof with approved download |
| Grafana with InfluxDB 3 | Time-series dashboards | Existing file mapper only | Assessment; mapper reading | No writer; cardinality untested | **feasibility**, no-go for a writer now | Go criteria in the assessment |
| Excel and notebook recipes | Reuse data elsewhere | Normalized CSV/JSON exports exist | Existing docs | No customer-requested recipe gap was found in this pass | **limitation** | Add a recipe when a customer asks |
| AI-guided onboarding, skills, manual equivalents | Natural language entry, not mandatory | Three canonical skills updated for native scores, PDF and jobs | Skill text; CLI equivalents documented | Fresh-install proof not done in this pass | **done**; clean-install **blocked** | Fresh machine run |
| Standard user, ARM, Linux and macOS vault, clean install | Platform confidence | None | Hosted CI covers core only | No such hardware or account here | **blocked** | Owner provides hosts |
| Negative runtime proof | Clear failures | PDF renderer missing, blank, truncated, leaking, timeout; job lock, partial, stale | Tests | Mashup negative fixtures remain | **done** for new code; Mashup **blocked** | Desktop negative cases |
| Retained versus advancing Continuous data | Know if data is new | Job freshness separates run time from source time | Tests | Advancement of existing data not checked | **blocked** (needs approved read-only access) | Compare two samples of one Continuous test hours apart |
| Credentials, recovery | Safe operation | Scheduler identity and recovery in docs | Docs | Rotation and support are owners' actions | **limitation** | None |
| Packaging, stale docs, links | Accurate public material | Capabilities, architecture and changelog updated; Blog B URL recorded in the private tracker | Public content check | Publication state is owner's | **done** | None |
| Independent review | Non-author check | Review handoff prepared (private) | Not executed | Self-review is not independent | **blocked** on a reviewer | Run the handoff |
| Blog 4, Microsoft showcase, Nutanix | Communications | Private drafts and claim notes | Private packet | Nothing sent or published | **owner action** | Owner review |

## Incremental ingestion

Cost: each Load or Continuous result costs paged sessions, one app-execution request per session, paged measurements and events, and session metrics. Request count grows with sessions, so a long Continuous window is the expensive case. Observed bounded captures stayed within the default request limit.

Blockers to checkpointing: measurement rows have no per-observation ID (`measurementId` names a timer); window boundary inclusion is confirmed only for the EUX endpoint; late arrivals need an overlap re-fetch; deletion by retention is invisible. A safe design would use a watermark equal to the newest source timestamp, an overlap of at least the longest collector interval, canonical-hash deduplication (already used by the mapper), commit only after a complete capture, and a full-capture reconciliation of counts.

Done in this pass: the job records `latest_source_observation`, the natural watermark, and refuses to publish partial evidence. Not done: resume, merge and deletion handling. Acceptance plan: sample one Continuous test twice with an approved read-only profile, confirm boundary behavior and duplicate rates, then implement merge with a replay test.
