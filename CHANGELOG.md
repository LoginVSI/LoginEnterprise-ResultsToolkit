# Changelog

## Community preview, unreleased

- Raise the development-only pypdf pin to 6.21.4 (official hashes) after new advisories; runtime dependencies are unchanged.

- Verify Grafana 13.3.0 against the authenticated TLS InfluxDB 3 Core example on loopback with synthetic data and certificate validation (health check fails without the CA). The example data source now uses HTTPS with a supplied CA, and the dashboard table shows sample counts and missing values per run and action.

- Add native whole-run scores to the refreshable Power BI connector (`ResultsToolkit.Native`, separate `NativeScores` table, completed-only change measures). Implemented and parser-checked; not yet run in Desktop or the Service. Correct the Continuous note: an empty window does not show why, and the captured definition was disabled.

- Retrieve native whole-run EUX/VSImax results from the Load overview into a separate `native_scores` table and compare them per run with vendor states. Label aggregate-interval `eux` rows and never average native scores across runs.
- Add `report-pdf`, an optional verified PDF print of an existing HTML report using a user-local Edge, Chrome or Chromium. No new pip dependency or administrator rights.
- Add `job run` and `job status` for scheduler-driven capture/report runs that publish only complete output and separate last attempt, last success and source freshness.
- Add `scripts/Register-LEResultsJob.ps1` (dry run by default, explicit schedule, disabled option, show and remove), a Power BI Service and gateway readiness runbook and setup, upgrade, removal and recovery guidance.
- Add an optional Grafana and InfluxDB 3 example (data source, dashboard, standard-library writer) with loopback proofs on synthetic data, and the backlog reconciliation. Core offers admin tokens only; scale beyond 30,000 points and Grafana over TLS are untested.
- Record a separate-context review of this change and fix its findings: unexpected job errors, killed-run locks, per-side freshness, PDF leak and completeness checks, native display of VSImax lower bounds.

- Complete the preview closeout review and record both final Blog B reviews as complete. Keep project-specific acceptance, pending runtime/platform checks and optional integrations distinct. Merge authorization does not publish a release, package or article.
- Resolve closeout CI audit findings with development-only filelock 4.2.1, pypdf 6.21.2 and setuptools 84.1.0 pins and official hashes. Runtime dependencies are unchanged; no advisory suppression is added.

- Link the three-action synthetic review directly from quickstart and prompt gallery, with a ready-to-use meeting refinement. Keep customized HTML headings explicitly synthetic and remove repeated interpretation text from the refined view. Aggregate observation cards and failure coverage remain visible.
- Record a successful fresh-Claude synthetic customer workflow separately from the previously accepted Desktop meeting project. New workflow projects remain Desktop-pending.

- Record 22 October owner acceptance of the refined synthetic meeting snapshot: successful refresh, persistent edit/save/close/reopen and matching HTML/Power BI timing and coverage review. Other projects and live/runtime claims remain separate.

- Add a reproducible three-action synthetic review and an opt-in 16:9 HTML/Power BI presentation with explicit failure and timing coverage. Configuration-only refinement preserves the verified data and moves details to a second page. Refined-project acceptance is recorded on 22 October; other generated projects remain separate.
- Update the development-only pypdf lock to 6.21.1 from official hashes after CI identified newly reported vulnerabilities.

- Addressed independent Claude findings with session-window coverage, per-result timer-only gates, pinned trust material, strict TLS across supported runtimes, explicit metric identity and role-scoped snapshot relationships.
- Recovered the observed session-metric HTTP 500 with explicit timestamp sorting. Fresh bounded captures preserve empty resource responses; earlier failed captures remain immutable.
- Bounded live connector acquisition, retained native credential errors and missing counts, and strengthened comparison/source validation. Desktop execution remains pending.

- Added bootstrap readiness, structured DNS/TCP/TLS/HTTP diagnosis and credential-free inspection. Approved profile trust can be replaced/removed without changing vault credentials or global settings.
- Added real synthetic HTTPS tests, including self-signed end-entity trust. Strict/hostname verification remain enabled; toolkit TLS key logging is disabled.
- Exercised read-only acquisition on Login Enterprise 6.9.2. Fixed collector group identity, explicitly disabled historical metrics and retention after optional failures.
- Added bounded recommendations, request limits, finite reports and explicit timer-only comparison. Failed resource acquisition stays visible.
- Expanded setup, no-AI examples and the prompt gallery. Desktop acceptance, native Linux/macOS vault acceptance and licensing remain separate checkpoints.

## Continuation validation

- Inspect full Continuous enabled state and sampled source timestamps separately; retain failed probes/bounds and broaden bounded definition screening.
- Add bounded read-only native Application PDF download with compressed-response checks and safe failures.
- Show raw resource evidence in finite HTML/Power BI tables; refuse mixed numeric source types and avoid empty comparison scaffolding in finite HTML.
- Generate a single-source refreshable project without pooled results or artificial comparison roles.
- Add optional finite line-protocol files with ns timestamps/provenance and no database write/checkpoint claim.
- Record focused independent review, actual synthetic host demonstrations and remaining Desktop/platform/licensing gates.

### 20 October practical acceptance

- Add owner-authorized MIT license and package license metadata.
- Add a user-scoped, backed-up single connector installer with explicit folder choice and no policy changes. Recovery continues when inspecting a newly placed file fails, preserves backup locations and returns a failure status.
- Fix the owner-demonstrated live table-type failure by retaining required-column errors rather than applying UseNull.
- Add editable finite report refinement and accurate selected-report opening instructions.
- Record project-specific snapshot/live owner acceptance, published first article and remaining runtime/platform limits.

- Fix aggregate live metric-key scope without removing unit/instance guards; existing project measures require an explicit upgrade.
- Update certifi hash locks for PYSEC-2026-4320; no TLS validation workaround.
- Normalize finite titles and reject unknown/duplicate specification fields before output; strengthen installer checks and tested rollback.
