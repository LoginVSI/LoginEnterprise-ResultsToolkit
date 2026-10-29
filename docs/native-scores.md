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
- Result rows carry `grain` (`native_whole_run` or `observation_mean`), plus states and run IDs for native rows. HTML and the Power BI snapshot `Comparison` table show `grain`, `baseline_state` and `candidate_state`. The `baseline_mean` column holds the vendor value for native rows.

The toolkit does not implement an EUX algorithm, weight aggregate rows or infer capacity from VSImax. The refreshable Power Query connector does not retrieve the overview yet, and `report-live` refuses native metrics with that message. The review layout accepts duration comparisons only.

## Reconciliation status

Offline tests cover identity, states, null handling, no averaging, old-capture refusal and report labeling with synthetic overview responses. The route comes from the checked-in v8-preview contract. It was not exercised against an appliance in this change, and no native UI or PDF reconciliation of a real run was performed. Next acceptance step: with owner-approved read-only access, capture one existing completed Load run and compare `eux_score`, `eux_baseline`, `eux_steady_state` and `vsi_max` with the appliance UI for the same run.
