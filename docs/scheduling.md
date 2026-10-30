# Scheduled capture and report jobs

`le-results job run` is one bounded run meant for an operating system scheduler. There is no daemon and the toolkit registers no schedules. Registering a task, installing a service or delivering a file is the owner's action.

## Job file

```json
{
  "schema_version": "job/1",
  "name": "weekly-image-review",
  "profile": "lab",
  "baseline_selection": "selections/baseline.json",
  "candidate_selection": "selections/candidate.json",
  "comparison": "compare.json",
  "report": "report.json",
  "pdf": true,
  "keep_runs": 12,
  "limits": {"max_requests": 200, "deadline": 300}
}
```

Relative paths resolve beside the job file. Retained evidence needs no appliance or credential: replace the selections and `profile` with `baseline_capture` and `candidate_capture` directories. `rolling_hours` recomputes the window of Continuous selections at run time. Fixed Load or Application selections are unchanged runs of the same evidence.

```powershell
le-results job run --config job.json --out-root D:\reports\weekly
le-results job status --out-root D:\reports\weekly --max-age-hours 30
```

## Guarantees

- One run stages into `.staging/<stamp>` and publishes with a single rename to `runs/<stamp>`. A concurrent run exits 3 (`job_locked`) and changes nothing. A lock older than `lock_stale_hours` (default 3, set above your task's time limit) is reclaimed once, because a scheduler that kills a run cannot clean up; the reclaim is recorded in `status.json`. An unreadable lock is never reclaimed.
- A partial or failed capture, comparison, report or requested PDF stops the run. The staging directory moves to `failed/<stamp>` for diagnosis, `latest.json` is not touched and the exit code is 2. Earlier runs are kept.
- `status.json` (authoritative; `latest.json` is a pointer) keeps `last_attempt`, `last_success` and the source observation apart. A run that succeeds over old data reports old data. Timestamps are parsed, unparseable ones are skipped, and freshness checks use the stalest of the baseline and candidate so a recent side cannot hide an old one. `job status` fails when there is no success, its folder is missing, the last attempt failed, a lock is overdue, or the source observation exceeds `--max-age-hours`.
- Any unexpected error is also recorded as a failed attempt (`unexpected_error`, class name only) and the staging folder moves to `failed/`. A failure to write bookkeeping after publishing is reported as `bookkeeping`.
- Same-second runs get distinct names. Deletion is opt-in (`keep_runs`, `keep_failed`) and never removes the run `latest.json` names.

## Snapshots, windows and rolling data

A job over fixed selections is a repeatable snapshot. Refreshing a fixed historical window proves no new observations and no real-time behavior. A rolling Continuous job acquires new data only if the source collects it; `latest_source_observation` shows whether it did. Active advancement of the existing Continuous data was not proven in this change.

## Scheduler identity and recovery

The job reads the profile and the native vault as the account the scheduler runs under. Credentials enrolled by another account are not available to it. Enroll as the scheduled account (`le-results auth set`, hidden input) and run `le-results doctor` as that account. Keep strict TLS and any approved profile trust; do not disable verification to fix a scheduled failure. Give the account write access only to `--out-root`.

Windows Task Scheduler: `scripts/Register-LEResultsJob.ps1` builds the task for you (dry run by default, explicit time and interval, `-Disabled` to create it off, `-Show`, `-Unregister -Apply`). It runs the virtual environment's Python with `-I -m le_results.cli job run --config ... --out-root ...` as you, interactive logon only, with a two-hour limit and no overlapping runs. There is no log redirection; read `status.json` and the task's last result. Use "Run only when user is logged on" unless that account's vault is confirmed usable in a non-interactive session. Linux and macOS: a user-level systemd timer or cron entry under the same rule, after checking the keyring backend works without a desktop session. Native Linux and macOS vault behavior is not verified.

After a failure, read `status.json`, inspect the endpoint outcomes in the failed run's capture manifests, fix the cause and rerun. Earlier runs stay valid. Exit codes: 0 success, 2 failure, 3 skipped because another run is active.
