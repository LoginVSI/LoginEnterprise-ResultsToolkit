# Native EUX and VSImax scores

A Load result carries two different kinds of EUX evidence. The toolkit keeps them apart everywhere.

| | Native whole-run score | Aggregate-interval rows |
|---|---|---|
| Source | `GET /v8-preview/load-test-run-overview/{baseTestRunId}` | `GET /v8-preview/test-runs/{id}/eux-results` |
| Table | `native_scores` | `eux` |
| Grain | One value per run and result ID (`score_grain: native_whole_run`) | One vendor interval score per timestamp (`score_grain: aggregate_interval_vendor`) |
| Result IDs in the contract | `eux_score`, `eux_baseline`, `eux_steady_state`, `vsi_max` | None; a single `score` per interval |
| State | `euxState` and `vsiMaxState` kept on each row | None |

The capture requests the overview once per selected Load run with the run as its own base. It never passes `testRunIds`, so the vendor never computes a cross-run difference for us. `source_difference_from_base` is retained only as a vendor field. A 404 or 405 marks the endpoint unavailable and the capture stays complete. A response for a different run fails the capture with a source identity error.

## Comparing

```json
{
  "name": "Native EUX score",
  "table": "native_scores",
  "value_field": "value",
  "match": {"resultId": "eux_score"},
  "unit": "score 0-10",
  "semantics": "native_score",
  "direction": "higher"
}
```

Rules enforced by the engine:

- Exactly one run per side. Native scores are never averaged across runs.
- Unit and direction are explicit. No grouping and no excluded values.
- A delta needs two numeric values and both states equal to `completed`. Otherwise values and states are shown, the delta is unavailable and the warning names the states. Censored VSImax states (`belowSessionCount`, `belowThreshold`, `aboveThreshold`) are never subtracted.
- A null value stays unavailable. It is never zero.
- Captures made before this feature lack the table. Comparing native scores against one is refused with an instruction to recapture.
- Native columns and the `Source_native_scores` table appear only in reports that compare native scores, so timing and resource projects keep the accepted model shape. Only `performance` results (`eux_*`, `vsi_max`) carry a vendor state; login-time and application-performance results are retained as returned and never get a delta. Result rows carry `grain` (`native_whole_run` or `observation_mean`), plus states and run IDs for native rows. HTML and the Power BI snapshot `Comparison` table show `grain`, `baseline_state` and `candidate_state`. The `baseline_mean` column holds the vendor value for native rows.

The toolkit does not implement an EUX algorithm, weight aggregate rows or infer capacity from VSImax. The refreshable Power Query connector does not retrieve the overview yet, and `report-live` refuses native metrics with that message. The review layout accepts duration comparisons only.

## Reconciliation status

Offline tests cover identity, states, null handling, no averaging, old-capture refusal and report labeling with synthetic overview responses. On 28 October one existing completed Load run was captured read-only from the 6.9.2 appliance (no tests created or changed). The overview request succeeded and the capture is complete. It returned the four performance result IDs plus login-time results and one application-performance row. For that run EUX and VSImax were disabled: all four performance values were null with state `disabled`, matching the run object's own `euxScore` and `vsiMax` states. Login-time values were retained as returned. A second read-only capture of an existing EUX-enabled completed Load run (June 2025) reconciled with the owner-supplied UI, native PDF and overview response. The run identity (name and counter) matched. `eux_score` 8.2, `eux_baseline` 8.4, `eux_steady_state` 8.3 (state `completed`) and `vsi_max` 6 (state `aboveThreshold`) matched exactly, and the run object's own `euxScore` and `vsiMax` fields agreed, including baseline window start and size and the `EUX2023` version. The 33 aggregate interval rows of the same run average 8.01 and range 7.0 to 8.4, which differs from the native 8.2. That gap is why the two grains are kept separate and the aggregate mean is never presented as the run score. Both captures are kept as separate private evidence.

VSImax in state `aboveThreshold` means the threshold was not reached, so the vendor value is a lower bound. The HTML table, the comparison JSON (`baseline_display`) and the Power BI comparison table show it as `>6`, not as an exact capacity of six, and no delta is calculated for it. Power BI numeric measures and cards carry the raw vendor value (6) without the bound. Read the display and state columns beside it, and do not chart the numeric measure as a capacity. Values are shown at source precision with no rounding. Login-time values are retained as returned with no unit inferred.

Reconciled so far: the overview response, run-object fields and owner-supplied UI/PDF values for one run. Not reconciled: other runs, other EUX versions and VSImax in the `completed` state.
