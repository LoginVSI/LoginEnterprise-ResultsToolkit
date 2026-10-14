# Implementation and evidence

This public, unsupported community preview reduces repeated retrieval and report assembly. Josh owns product and technical decisions. Evidence below belongs to this repository; reference-project validation is not toolkit validation.

## Current checkpoint

### Continuation evidence, 2026-10-13

Existing branch/draft PR were retained. Checkout started clean at `9e5e6df`. A runtime upgrade removed the Python executable referenced by `.venv`. The broken environment was preserved under ignored storage and recreated with project-local 64-bit Python 3.14.8. Profiles, native enrollment and private references remain preserved. Observed client OpenSSL is 3.5.9.

DNS and TCP 443 succeeded. Strict verification rejected the issuing CA with OpenSSL code 92, missing required CA key usage. The hostname-covering leaf was self-issued but signed by a separate CA. Exact leaf/issuer trust already existed in Windows ROOT. Profile trust using the independently enrolled exact leaf succeeded with strict, partial-chain and hostname verification retained. The normal client/vault read v8-preview system/version and observed Login Enterprise 6.9.2. No global trust, appliance setting or verification flag was weakened.

Bounded acquisition established a complete selected Load capture, a compatible historical Load pair, Application evidence and a retained Continuous window. Resource requests return HTTP 500, including with explicit boundaries. Successful pages, endpoint failures and partial status stay preserved. Timer-only arithmetic is independently reconciled from raw records; units remain source-unconfirmed. Completed work differs and raw unended executions remain visible. No migration, causality or resource-improvement claim is made. No enabled Continuous test appeared in the bounded subset; this is not appliance-wide proof.

Customer additions include bootstrap readiness, structured diagnosis, credential-free certificate inspection, approved trust replacement/removal, bounded recommendations/request limits, corrected collector identity, disabled-metric status, optional-failure continuation, timer-only policy and finite capture reports. Skills/prompt gallery call the engine. Actual HTML/snapshot projects and a selected Load refreshable project are private. Their official schemas and connector/generated M syntax pass. Desktop acceptance remains separate.

Local checks pass 79 tests, lint and types. New tests use real synthetic HTTPS, including trusted/untrusted, explicit `CA:false` self-signed trust, hostname/expiry/purpose rejection and strict CA key-usage rejection. Dependency audit caught vulnerable parser versions; the supported range and locks now use audited cryptography 50.0.2. No known vulnerabilities remain. The final wheel passes isolated installation and demo/compare/report outside the checkout. Final CI results are recorded below.

Desktop 2.158.1304.0 is installed; UI inventory exposes no native app/browser surfaces. Open/refresh, approved connector policy/Key enrollment, two live refreshes and new observations remain owner checkpoints. Actual account membership is administrator despite a non-elevated token; standard-user proof remains pending. Claude review failed before inference because OAuth access expired and could not refresh. The public-only snapshot, prompt and restricted runner remain ready; no independent findings exist. Private writing guidance was applied to unpublished drafts, claim map, flow/demo brief and partner handoff. Nothing was published or sent. Licensing remains an owner decision.

A broader Continuous discovery returned 29 configured tests within a 100-record bound, with none enabled. Retained historical sessions remain useful, but active collection/new-data ingestion require an owner-managed test. The Load comparator now explicitly warns about differing completed-work/failure coverage. Final raw reconciliation includes successful, orchestration-diagnostic and historical Continuous evidence.

This continuation and [capability matrix](capabilities.md) supersede the older table's pending-credential/live entries. Dated historical checks below remain provenance; final audit/check/CI outcomes are added as they complete.

Work is on `feat/results-toolkit-foundation`. Foundation checkpoint `de5fa0f` and reporting checkpoint `dc6132f` are pushed. [Draft PR #1](https://github.com/LoginVSI/LoginEnterprise-ResultsToolkit/pull/1) records scope and acceptance gaps. The starting checkout had one initial commit and a user-added `/.private/` ignore rule, retained in this change. All three private inputs are present in the original checkout and none are tracked. No existing project license was found. Licensing remains an owner decision; no terms have been selected on the owner's behalf.

| Slice | Implemented | Offline proof | Appliance proof | Desktop proof |
|---|---|---|---|---|
| Installable Python engine, CLI, native PowerShell wrapper | Yes | Fresh wheel and outside-source walkthrough; PowerShell 5.1/7 exercised | N/A | N/A |
| Nonsecret profiles and native vault enrollment/status/replacement/deletion | Yes | Native Windows lookup/roundtrip and rejection tests | Existing enrollment reused successfully | N/A |
| Read-only HTTPS transport, bounded retry/paging and safe errors | Yes | Real HTTPS and safe-error/paging tests | Verified strict TLS and version endpoint on 6.9.2 | N/A |
| Explicit Load/Application/Continuous selection and capture | Yes | Model, identity and partial-page tests | Selected complete Load and partial evidence across all three models | N/A |
| Raw JSON, normalized JSON/CSV, dictionary and hashed manifest | Yes | Synthetic capture/verification | Actual source/hash/count relationships reconciled | N/A |
| Explicit metric comparison and failure/coverage evidence | Yes | Synthetic means 120/130, delta 10, relative 8.3333%; candidate failure retained | Compatible pair, explicit timer-only arithmetic reconciled; resources failed | N/A |
| Portable HTML and editable local-file PBIP/PBIR/model.bim report | Yes | Source evidence copied; relationships/numeric fields and official schemas checked | N/A | Pending open/refresh |
| Refreshable acquisition and generated live model | Yes | M syntax, schemas and generated references checked; M execution pending | Pending | Pending subsequent refresh |
| Portable AI skills and customer documentation | Yes | Three canonical skills validate; six thin host adapters; no-AI walkthrough | N/A | N/A |
| Hosted Windows/Linux/macOS core CI | Yes | Six OS/Python combinations and M parser pass, including fresh wheel walkthroughs | N/A | N/A |
| InfluxDB/Grafana | Planned | No implementation | No | N/A |
| Independent Claude Code audit | Ready prompt in claude-audit.md | Not run | N/A | N/A |

## Decisions and contract evidence

- Python 3.11+ with httpx, keyring and platformdirs. The standard-library CLI avoids an extra command framework. Native Windows Python keeps vault lookup under the enrolled user's account. Windows/Linux/macOS core checks pass on Python 3.11 and 3.14; native Linux/macOS vault access remains unverified.
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
- [x] Finish regression/type/lint checks, native vault roundtrip and scoped foundation checkpoint de5fa0f.
- [x] Complete refreshable M connector and report generation with explicit credential storage.
- [x] Validate report schemas/references and fresh wheel installation.
- [x] Finish portable workflows, CI, customer docs, live/Desktop procedures and independent audit handoff.
- [x] Record hosted core CI results separately from native credential proof.
- [ ] Verify native Linux/macOS credential access on suitable hosts.
- [x] Run bounded live discovery/export and reconcile a compatible timer-only Load pair; resource endpoint acceptance remains pending HTTP 500 remediation.
- [ ] Open/refresh snapshot and live report in target Desktop and reconcile numeric source checks.
- [x] Push scoped commits and create accurate draft PR.

## Verified foundation checkpoint

On 2026-10-09, native Windows Python 3.14.8 passed 46 unit/functional/negative tests, Ruff and mypy (12 source modules). Editable installation and the synthetic export/comparison/report walkthrough succeeded. Eleven PBIP/PBIR JSON files passed Microsoft's official schemas, including nested visual expressions. Installed Desktop version was read as 2.158.1304.0, matching the target; no Desktop open/refresh acceptance has occurred. GitHub CLI authentication is available.

The local 901-page September 2026 guide was consulted at pages 259 (retention), 449 (API), 524 (single-user Desktop Load and figure), 573/588 (session metrics), and 859 (SetTimer). Page 524 was rendered and visually inspected: one user, no login process, optional EUX/session metrics and no meaningful capacity comparison. The guide's full prior ChatGPT review remains completed. Local consultation adds design evidence, not live proof.

The two initial test issues were in fixture dispatch and test-double class cleanup; corrected regressions now pass. No production failure was hidden by rewriting expected values.

## Reporting and workflow checkpoint

Native Windows Python 3.14.8 now passes 59 unit/functional/negative tests, Ruff and mypy across 13 engine modules. A fresh isolated environment installed the wheel with hash-locked runtime dependencies, then ran demo, compare and report outside src. Windows PowerShell 5.1 and 7.6.6 wrappers both verified capture hashes. The three canonical skills passed skill-creator validation.

The final snapshot, Load live and Continuous live projects each passed 11 official Microsoft PBIP/PBIR schema checks. Microsoft's M parser 2.0.0 validates connector and generated query syntax. These checks do not evaluate Mashup or DAX in Desktop. The unsigned development connector was packaged without upstream assets. Power Query Key enrollment is separate from the Python vault.

Current collector definitions retain source fields/settings where exposed and remain labeled current. Snapshot bundles copy verified raw/normalized evidence. Numeric visual measures use selection-wide unit guards. Synthetic arithmetic remains independently reconciled at means 120/130, delta 10, relative 8.3333%, three observations per side and one candidate execution failure. No benchmark claim is made.

Self-review fixed an optional endpoint later-page 404 being mislabeled unavailable. Its regression requires partial evidence and failure. Cancellation finalizes evidence before exit. Synthetic login/EUX/VSImax states were corrected against the API enums. These are implementation-agent findings, not an independent Claude audit.

Computer-use imported its API but could not connect to its native pipe (system error 2). No Desktop UI actions or refresh proof occurred. A real API credential is still absent. Bounded live_acceptance.py is ready: a recent subset of at most 20 results and at most five completed Load candidates, with one-run export if no compatible pair exists. It does not invent OS identity.

Remaining external evidence: hidden-input enrollment in a normal user terminal; bounded live capture/comparison on 6.9.2; snapshot and live Desktop open/refresh/source reconciliation; subsequent Continuous rolling refresh; independent Claude audit. Native Linux/macOS vault access, Service/gateway, signed distribution, incremental ingestion and InfluxDB/Grafana are not verified capabilities. Licensing remains an owner decision.

The first [hosted run](https://github.com/LoginVSI/LoginEnterprise-ResultsToolkit/actions/runs/38013349723) passed Python 3.14 on Windows/Linux/macOS and M parsing. Python 3.11 installation exposed missing conditional dependency hashes (backports.tarfile and related older-runtime dependencies). Locks were regenerated with minimum runtime 3.11. The [second run](https://github.com/LoginVSI/LoginEnterprise-ResultsToolkit/actions/runs/38013682767) passed tests/lint/types on Python 3.11 across all three platforms, then caught vulnerable setuptools seeded by the runners. Development locks now replace that tooling with a current audited version rather than suppressing findings. CI also installs the wheel into a fresh runtime-only environment on every platform. Final matrix results are pending.

Two additional identity regressions require a selected Continuous response ID to match and retain collector-to-group/result associations across multiple selected runs. Current definitions remain current even when the corresponding run has historical configuration.

The final code checkpoint `1946dee` passes the complete [push matrix](https://github.com/LoginVSI/LoginEnterprise-ResultsToolkit/actions/runs/38014505385) and [PR matrix](https://github.com/LoginVSI/LoginEnterprise-ResultsToolkit/actions/runs/38014509193): 59 tests, lint/types, public-content checks, dependency audit, wheel build, fresh runtime-only wheel installation and offline demo/compare/report on Windows/Linux/macOS with Python 3.11 and 3.14. Both Windows PowerShell wrappers pass in hosted Windows jobs. The separate M parser job passes. No findings were suppressed to obtain these results. These runs establish core portability, not native Linux/macOS vault or Desktop acceptance.

Resume from this file and AGENTS.md. Private state stays ignored; do not copy the original assignment or personal environment details into public content. Safe blog evidence/asset ideas are in ai-workflows.md; neither blog has been published.
