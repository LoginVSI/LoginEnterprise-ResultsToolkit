# Bounded, read-only appliance acceptance

Run `doctor` first to establish verified TLS/API access; follow the [certificate workflow](troubleshooting.md) for trust failures. Existing enrollment can be reused. `recommend` discovers bounded candidates across all test models and records reasons. The acceptance script screens all pairs among at most five Load details, preserves later evidence after optional failures, records partial captures and exits 2 when incomplete. Bounds cover requests/pages/deadline. Results are never selected for favorable performance.

On 6.9.2, selected result paths and a retained Continuous test-ID window have been exercised. Earlier session-metric requests returned HTTP 500 and remain preserved as failed. Minimal requests isolated omitted optional sorting as the trigger. Explicit timestamp ordering recovered the endpoint, with new complete captures across the selected models. Resource responses are successfully empty; no CPU/memory measurements or retention explanation are established. Default comparisons now work on the new complete pair. Timer-only policy remains available for explicitly bounded partial evidence, with every selected result's timing/failure acquisition complete. Desktop acceptance remains separate.

Enroll the native credential once and verify `auth status`. The following command discovers at most 20 recent Load results, inspects at most five completed runs, and exports one run or a compatible pair. It does not create or change tests.

```powershell
.\.venv\Scripts\python.exe scripts\live_acceptance.py --profile lab --out .private\live\first-capture
```

The script records exact IDs and labels scenarios by their role, without inventing operating systems. Compatibility screening compares historical workload, concurrency, duration and collector settings. The exported evidence still needs review for coverage, retention, engine identity/debug settings and confounders. If there is no compatible pair, the single-run export remains useful; synthetic comparisons prove the offline workflow while live comparison stays pending.

A metric configuration is optional for this first capture. Supply a reviewed `comparison/1` file with `--comparison-config PATH` to compare the chosen IDs and build a snapshot. The script substitutes actual baseline/candidate IDs but keeps your reviewed labels and metric definitions. Do not guess timer units or use current collector settings as historical proof. Never use a name alone to assign Windows 10/11 identity.

Record observed appliance version, capture status, endpoint counts/availability, settings, retention gaps and independent arithmetic checks. Login Enterprise 6.9.2 is a target until the version and chosen paths are verified. An old reference project's successful capture is not validation of this toolkit.

For Application acceptance, discover `ApplicationTest` runs and explicitly export both successful and failed examples. Verify session login states, executions, failure events and available timings. For Continuous, select test IDs with a fixed window first, then establish rolling refresh in Desktop using the identical source contract. Inspect endpoint boundaries and duplicate/late-data behavior. The initial live scope is selected Load; wider acceptance is recorded separately.
