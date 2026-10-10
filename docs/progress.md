# Implementation and evidence

This public, unsupported community preview reduces repeated retrieval and report assembly. Josh owns product and technical decisions. Evidence below belongs to this repository; reference-project validation is not toolkit validation.

## Current checkpoint

Work is on `feat/results-toolkit-foundation`. The starting checkout had one initial commit and a user-added `/.private/` ignore rule, retained in this change. All three private inputs are present in the original checkout and none are tracked. No existing project license was found. Licensing remains an owner decision; no terms have been selected on the owner's behalf.

| Slice | Implemented | Offline proof | Appliance proof | Desktop proof |
|---|---|---|---|---|
| Installable Python engine, CLI, native PowerShell wrapper | Yes | Installation and walkthrough exercised; regression pass pending fixes | N/A | N/A |
| Nonsecret profiles and native vault enrollment/status/replacement/deletion | Yes | Native Windows backend lookup confirmed, no credential enrolled; abstraction tests in progress | No token | N/A |
| Read-only HTTPS transport, bounded retry/paging and safe errors | Yes | Negative and paging tests implemented | Pending credential | N/A |
| Explicit Load/Application/Continuous selection and capture | Yes | Application/failure and partial-page fixtures in progress | Pending credential | N/A |
| Raw JSON, normalized JSON/CSV, dictionary and hashed manifest | Yes | Synthetic capture and verification exercised | Pending credential | N/A |
| Explicit metric comparison and failure/coverage evidence | Yes | Synthetic means 120/130, delta 10, relative 8.3333%; candidate failure retained | Pending compatible Load pair | N/A |
| Portable HTML and editable local-file PBIP/PBIR/model.bim report | Yes | Generated; official schema validation in progress | N/A | Pending |
| Refreshable acquisition and generated live model | In progress | Pending M runtime | Pending | Pending |
| Portable AI skills and customer documentation | In progress | Pending walkthrough review | N/A | N/A |
| InfluxDB/Grafana | Planned | No implementation | No | N/A |
| Independent Claude Code audit | Handoff planned | Not run | N/A | N/A |

## Decisions and contract evidence

- Python 3.11+ with httpx, keyring and platformdirs. The standard-library CLI avoids an extra command framework. Native Windows Python keeps vault lookup under the enrolled user's account. Linux/macOS compatibility is a target until platform checks run.
- API routing is explicitly `/publicApi/v8-preview`. `info.version` was verified as `8.0-preview` and `7.0`; v7 is reference only. Full sanitized snapshots and original/sanitized hashes are in `docs/api`. Examples/contact metadata were removed, and absolute URLs replaced throughout. Private originals were not modified.
- Discovery is bounded to a recent subset, then selection records explicit UUIDs. Continuous selects test identity plus a frozen window. Result paths may name this `testRunId`; this mapping still needs live proof.
- Raw timer `duration` has no declared unit in the supplied API schema. Comparison configuration must declare unit, semantics and direction. SetTimer is not assumed to be a duration.
- `testConfigurationSnapshot` is the supplied v8-preview property. Historical includes request `testRunConfigurationSnapshot`. Continuous configuration is current. Snapshot definitions expose metric ID/name/unit, but may omit current collector query and settings; do not relabel current settings as historical.
- Measurements deduplicate only exact rows, not timer IDs. Session metric instance/field/unit identity is required for grouping. Observations and sessions do not establish independent device counts.
- EUX and VSImax are preserved as vendor values and state objects. No toolkit score computation or censored capacity comparison exists. Application EUX retrieval is excluded.
- Microsoft PBIR public schemas permit external editing; PBIR-Legacy does not. Generated PBIP references PBIR and an editable model.bim. Desktop acceptance remains explicit.
- Upstream connector source uses v7-preview routing, a token parameter and error-to-empty paths. Its no-LICENSE status at the reviewed commit means this toolkit independently implements functionality and copies no source or assets.

## Iterative checklist

- [x] Inspect Git status/origin, retain user's ignore change, create feature branch.
- [x] Verify local reference versions and hashes; publish sanitized contracts with graph checks.
- [x] Implement secure enrollment and create local validation profile without a token.
- [x] Implement bounded discovery, explicit selections, raw/normalized export and comparison.
- [x] Exercise a no-appliance synthetic migration export/comparison/report.
- [ ] Finish regression/type/lint checks, native vault roundtrip and scoped checkpoint commit.
- [ ] Complete refreshable M connector and report generation with explicit credential storage.
- [ ] Validate report schemas/references and fresh wheel installation.
- [ ] Finish portable workflows, CI, customer docs, live/Desktop procedures and independent audit handoff.
- [ ] Run bounded live discovery/export with saved credential; use a compatible Load pair when available.
- [ ] Open/refresh snapshot and live report in target Desktop and reconcile numeric source checks.
- [ ] Push scoped commits and create accurate draft PR.

## Verified foundation checkpoint

On 2026-10-09, native Windows Python 3.14.8 passed 46 unit/functional/negative tests, Ruff and mypy (12 source modules). Editable installation and the synthetic export/comparison/report walkthrough succeeded. Eleven PBIP/PBIR JSON files passed Microsoft's official schemas, including nested visual expressions. Installed Desktop version was read as 2.158.1304.0, matching the target; no Desktop open/refresh acceptance has occurred. GitHub CLI authentication is available.

The local 901-page September 2026 guide was consulted at pages 259 (retention), 449 (API), 524 (single-user Desktop Load and figure), 573/588 (session metrics), and 859 (SetTimer). The guide's full prior ChatGPT review remains completed. Local consultation adds design evidence, not live proof. Figure inspection is pending a local renderer.

The two initial test issues were in fixture dispatch and test-double class cleanup; corrected regressions now pass. No production failure was hidden by rewriting expected values.

Resume from this file and AGENTS.md. Private state stays ignored; do not copy the original assignment or personal environment details into public content.
