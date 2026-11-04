# Metric guide and coverage matrix

A short reference for reading any number the toolkit shows. It applies to HTML, PDF, Power BI projects, configuration files and the skills. The engine's `comparison.json` is the source of truth; each surface shows the same values.

## Kinds of numbers

| Kind | Grain | Unit | Applies to | Comparison rule |
|---|---|---|---|---|
| Timer duration (`measurements`) | One observation per action execution | Authored in the metric definition; the API does not state it | Load, Application, Continuous | Mean of observations, equal weight per observation (not per device or user). Chart one action at a time |
| Session metric (`session_metrics`) | One sample per timestamp | Source `unit`, must match the definition | Load, Continuous when session metrics are enabled | Same as timers. Disabled collection reads `disabled`, not zero |
| Aggregate EUX rows (`eux`) | Vendor aggregate per interval (`aggregate_interval_vendor`) | Score | Load, Continuous | Shown as retained rows. Never mixed with native scores |
| Native whole-run score (`native_scores`) | One vendor value per run (`native_whole_run`) | Authored (EUX score 0 to 10 in the examples, VSImax in sessions) | Load only | One run per side. Never averaged across runs. The toolkit does not calculate EUX or VSImax |

## States, bounds and missing values

- **Missing is not zero.** A missing timing or score shows as `unavailable`, with the source state when there is one. A failed execution produces no timing, so it is absent from timing counts and present in failure counts.
- **Zero is a value.** A real zero is shown and used. A zero baseline gives no relative change, and the report says so.
- **Native states.** `euxState` and `vsiMaxState` are kept on every row. A change is calculated only when both sides are `completed`. Otherwise values and states are shown and the change is `unavailable`.
- **VSImax above threshold is a lower bound.** It shows as `>6`, never as exact capacity, and is never subtracted.
- **Login-time and application-performance native results** carry no vendor state, so no change is calculated for them.

## Denominators

- Timing counts are observations that recorded a timing. Execution counts come from the capture's executions. They differ whenever an execution fails without a timing, so read them together (the coverage table shows both).
- Failure counts use the execution and session states in the capture. They are not inferred from timings.
- Power BI numeric measures and cards hold raw values; the display columns carry bounds such as `>6`. Critical caveats are shown as columns and text in the exports, not only in hover text.

## Where each surface shows what

| Item | HTML and PDF | Power BI snapshot | Live project | Comparison JSON |
|---|---|---|---|---|
| Value and unit | Yes | Yes | Yes | Yes |
| Grain | Column (native reports) | Column | `score_grain` column | `grain` |
| Native state | Inline mark when not `completed` | Column | `state` column | `baseline_state`, `candidate_state` |
| VSImax bound `>6` | Yes | Display column | `display_value` column | `baseline_display` |
| Change blocked by state | Yes, with reason | Yes | Measure is blank | Warning text |
| Execution failures and coverage | Coverage section | Coverage table | Only in mixed projects with timer metrics | `coverage` |

Native-only live projects read the Load overview and nothing else, so they have no execution coverage. Add a timer metric to the same configuration for coverage, within the connector's ten-session bound.

See also [native scores](native-scores.md), [data dictionary](data-dictionary.md) and [PDF export](pdf-export.md).
