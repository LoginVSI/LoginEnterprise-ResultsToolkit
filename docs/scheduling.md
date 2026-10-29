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

- One run stages into `.staging/<stamp>` and publishes with a single rename to `runs/<stamp>`. A concurrent run exits 3 (`job_locked`) and changes nothing. A stale lock is never removed automatically.
- A partial or failed capture, comparison, report or requested PDF stops the run. The staging directory moves to `failed/<stamp>` for diagnosis, `latest.json` is not touched and the exit code is 2. Earlier runs are kept.
- `status.json` keeps `last_attempt`, `last_success` and `latest_source_observation` apart. A run that succeeds over old data reports old data. `job status` fails when there is no success, the last attempt failed, or the newest source observation exceeds `--max-age-hours`.
- Same-second runs get distinct names. Deletion is opt-in (`keep_runs`, `keep_failed`) and never removes the run `latest.json` names.

## Snapshots, windows and rolling data

A job over fixed selections is a repeatable snapshot. Refreshing a fixed historical window proves no new observations and no real-time behavior. A rolling Continuous job acquires new data only if the source collects it; `latest_source_observation` shows whether it did. Active advancement of the existing Continuous data was not proven in this change.

## Scheduler identity and recovery

The job reads the profile and the native vault as the account the scheduler runs under. Credentials enrolled by another account are not available to it. Enroll as the scheduled account (`le-results auth set`, hidden input) and run `le-results doctor` as that account. Keep strict TLS and any approved profile trust; do not disable verification to fix a scheduled failure. Give the account write access only to `--out-root`.

Windows Task Scheduler: create a task for the user that owns the vault. The action is the full path of the virtual environment's `le-results` executable with arguments `job run --config ... --out-root ...`. Use "Run only when user is logged on" unless that account's vault is confirmed usable in a non-interactive session. Linux and macOS: a user-level systemd timer or cron entry under the same rule, after checking the keyring backend works without a desktop session. Native Linux and macOS vault behavior is not verified.

After a failure, read `status.json`, inspect the endpoint outcomes in the failed run's capture manifests, fix the cause and rerun. Earlier runs stay valid. Exit codes: 0 success, 2 failure, 3 skipped because another run is active.
