# Application review demonstration

This offline workflow produces a self-contained HTML comparison and an editable local-file Power BI snapshot from the same verified comparison. No appliance, connector, credential or AI host is required. Power BI Desktop is needed only to open and accept the PBIP.

The `windows-review` fixture declares synthetic Windows 10 baseline and Windows 11 candidate roles. They are not verified operating systems or benchmark results. Three named actions have timing means of 1,000/800 ms, 500/500 ms and 2,000/2,500 ms. The engine calculates changes of -20%, 0% and +25%. Milliseconds are explicitly authored fixture units, not an inference about API timers.

Each role has one session and nine executions. The candidate has eight successful executions and one execution that ended with errors without a timing record. Export therefore has two timing observations against three on the baseline. No null or zero duration is fabricated in the source. `fixture.json` explains the authored inputs and expected observation design. A complete synthetic capture does not mean every execution succeeded.

Use the installed `le-results` command, or invoke `.venv/Scripts/python.exe -m le_results.cli` directly without activation:

```powershell
le-results demo --scenario windows-review --out artifacts/review-input
le-results verify artifacts/review-input/baseline
le-results verify artifacts/review-input/candidate
le-results compare --baseline artifacts/review-input/baseline --candidate artifacts/review-input/candidate --config artifacts/review-input/compare.json --out artifacts/review-comparison.json
le-results report --comparison artifacts/review-comparison.json --config examples/review-report.json --out artifacts/review-overview
```

Use new output directories. `report.html` embeds its styling and charts. `Results.pbip`, its Report and SemanticModel directories, local JSON datasets and retained evidence form the editable snapshot bundle. Move the whole bundle together; generated M file paths are absolute and must be regenerated or reviewed if relocated. Never rename a PBIP to PBIT.

The review layout uses native cards, bar charts, tables and textboxes. It accepts 1-3 duration actions with one shared source unit and distinct group labels. Absolute timing bars share that source unit; the signed change chart uses dimensionless percentage points with a zero reference. Underlying values remain numeric and unrounded. The native percent measure formats 25 as 25%, not 2,500%. No score or rollout verdict is calculated.

This compact layout requires complete acquisition, known execution states and resolved timing links. Use the standard evidence report for partial/timer-only captures or unknown relationships. If any selected timing lacks an execution link, the general comparison's no-retained-timing counter is null, not a claim that every execution lacks measurements. Compact titles are limited to 60 characters and action/group labels to 20; full identity remains in retained evidence. Native warnings are available on the Evidence page. Both baseline and candidate failures remain visible. Native display formatting still needs its own Desktop check.

The summary labels show matched metric samples, execution failures and executions with no retained timing. Matched sample counts sum configured metric groups; overlapping metric definitions can count the same observation more than once. Full-workload coverage is separate from those matches. An execution with no timing does not establish that a timing was expected outside this explicitly authored fixture. Successful-execution counts require source state `ended`; `endedWithErrors` remains failed. Observations are not independent sessions or devices.

## Refine the first page

Copy `examples/review-report.json`, set a meeting-specific title and change `overview_table` to `false`. Keep the remaining fields. Run `report` with that specification into a new folder. The overview keeps the charts, full-workload coverage and failure warning; sample-count detail and retained source tables remain on the Evidence page. The HTML moves the sample-count table into its secondary evidence section. Comparison and presentation datasets remain identical across both versions.

Schema checks, M parsing and HTML rendering are separate evidence. This new native layout needs its own Desktop open/local refresh/value reconciliation/save/reopen check. Acceptance of a previous toolkit project does not transfer to it. Do not interrupt another session that owns Desktop or install a connector for this local snapshot.
