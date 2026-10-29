# Grafana and InfluxDB feasibility

This repository owns the assessment. LE-PBI should not build a duplicate stack. After owner approval, a disposable loopback proof of option B ran on 28 October (below). Option A (Infinity) was **not** run: its plugin was outside the approved download. The Login Enterprise appliance's internal Grafana and InfluxDB were not touched, there was no Docker and no service, and nothing was exposed beyond 127.0.0.1.

## Versions and compatibility

Facts read from official documentation on 2026-10-28. Confirm each at acceptance, since the pages do not state everything the choice depends on.

| Item | Finding | Confidence |
|---|---|---|
| InfluxDB 3 Core | Docs banner announces 3.12. Default endpoint `localhost:8181`. Docs list historical query as an Enterprise feature, and give no numeric Core query-range or retention limits on the page read. | 3.12 likely, limits unknown |
| Grafana | Docs refer to 13.2 as the release where the InfluxDB data source becomes a standalone plugin (needs Grafana 12.3 or later). 13.1 and earlier keep the bundled plugin. | From docs text |
| Grafana InfluxDB data source | Languages: SQL, InfluxQL and Flux. Which language works with which InfluxDB generation was not on the page read. | Gap |
| Infinity data source | Version 4.1.4 on the plugin page. Reads JSON, CSV, XML, GraphQL and HTML endpoints. Whether it reads local files was not stated; assume HTTP endpoints only. | Version firm, file access unknown |

InfluxDB generations differ and must not be mixed. 2.x uses org, bucket, Flux or InfluxQL and its own token scheme. 3.x uses databases and tables, SQL (and InfluxQL) and a different write route. The existing mapper (`export-line-protocol`) targets 3.x: tag-set plus timestamp identity, ns precision and the 3.x timestamp range check. It is not a 2.x loader. Retention and query-limit behavior for Core must be read from the Core configuration reference before a go decision.

## Options

| | A. Grafana with Infinity over exports | B. Line protocol into InfluxDB 3, queried by Grafana | C. Exports, HTML and Power BI only |
|---|---|---|---|
| Value | Grafana-standardized teams can chart comparison and observation CSV/JSON with no database | Native time-series dashboards, long history, ad hoc SQL | Already works and is accepted |
| Prerequisites | Grafana, Infinity plugin, an HTTP location for files (a static server or share) | Grafana, InfluxDB 3 server, TLS, tokens, a write path the toolkit does not have | None beyond the preview |
| Operations | Refreshing files is a toolkit job; Grafana only reads | Two services to patch, back up and size; token rotation; retention | None |
| Network, TLS, auth | Infinity needs the file host allow-listed; files can contain private metadata | Separate destination token (never the appliance token), TLS to Influx, scoped write | Local files |
| Timestamps, units, identity | CSV/JSON flatten to one table per file; units and grain must be columns | Mapper keeps ns time and source unit tags; units absent in the API stay unlabeled | Carried in the report |
| Cardinality and duplicates | None | Mapper puts a per-observation hash in a tag, so identity is exact but the tag is effectively unique per point. High tag cardinality needs a load test on 3.x before any claim. `source_json` per point is large | None |
| Idempotency, late data | Replace the file on each run | Same observation replays to the same identity; changed values append versions. No checkpoint, so replay is whole-capture | Recapture |
| Partial writes and recovery | Not applicable | Needs batch commit and retry rules; not implemented | Capture verification |
| Reconciliation | Row counts against the manifest | Points written against `exported_points`, then query counts | Existing |
| Freshness | A stale file looks current. Add `job status` freshness as a dashboard column | Query max time per source | HTML states capture time |

## Recommendation

1. Ship C as the default. It needs nothing new.
2. Document A as a recipe for Grafana customers only after one disposable proof. Estimated effort: about one day for a synthetic proof (Grafana OSS, Infinity, `python -m http.server` on loopback serving comparison CSV), plus half a day of documentation.
3. Do not build a write path for B yet. Go criteria: a named customer already runs Grafana with InfluxDB 3; a disposable InfluxDB 3 instance is available; the cardinality test of the observation-hash tag passes on a realistic capture; Core query and retention limits meet the customer's history need; a batch writer with token from the vault, bounded batches, retry that is safe under replay and count reconciliation is agreed. Estimated effort once go: three to five days for the writer and its negative tests, plus a day for a pinned synthetic proof. No-go if the customer's history exceeds Core limits (consider Enterprise), or cardinality fails.
4. If the customer uses InfluxDB 2.x, B needs a different mapper and API. Treat it as a separate item.

## Option B loopback proof, 28 October 2026

Pinned and checksum-verified official Windows x64 artifacts: InfluxDB 3 Core 3.12.0 (SHA-256 matched the published `.sha256` file) and Grafana OSS 13.3.0 (SHA-256 matched the download page). Grafana 13.3.0 replaced the 13.2.x originally planned because it was current and is at least 13.2. Both ran as the current user, bound to 127.0.0.1, under an ignored private folder. InfluxDB used `--without-auth` on loopback only, so **token authentication and TLS were not exercised**.

What was shown, using the synthetic three-action review capture (baseline 9 timings, candidate 8 because one failed execution has no timing):

- `export-line-protocol` prepared 9 and 8 points. Posting each file to `/api/v3/write_lp` with `precision=nanosecond` returned 204.
- SQL counts per run were 9 and 8, and means were 1166.667 and 1112.5, equal to an independent calculation from the capture and to the receipt's `exported_points`.
- Replaying the candidate file returned 204 and left the total at 17 points: the observation tag makes replay idempotent for unchanged data.
- Grafana's InfluxDB data source in SQL mode (Flight SQL over the same port, `insecureGrpc` for plain loopback HTTP) passed its health check and returned the same counts and means through `/api/ds/query`.
- A provisioned dashboard rendered a point series per run and a count/mean table. Files are in [examples/grafana-influxdb3](../examples/grafana-influxdb3).

Findings that matter for customers:

- In Grafana 13.3 the SQL query field is `rawSql` and the table format is `"format": "table"`. Using the InfluxQL-era `query` key fails with "No SQL statements were provided".
- Long-form results need a `partitionByValues` transform on `result_id` to draw one series per run.
- Time displayed in the browser's timezone, so a UTC-7 browser showed 03:00 for 10:00Z data. The example dashboard pins `timezone: utc`.
- A time-series panel without a time column fails with "no time column found".
- Only 17 points were written. Cardinality, large batches, Core query-range and retention limits, authentication, TLS, partial-write behavior and `value_present=false` rows were **not** tested.

Cleanup: processes and plugin children were stopped, ports closed, and binaries and data deleted. Setup used `influxdb3 serve --node-id proof --object-store file --data-dir <dir> --http-bind 127.0.0.1:18181 --without-auth` and `grafana server --homepath <dir>` with provisioning and paths set by `GF_PATHS_*` environment variables.

Effect on the recommendation: the file-to-database path works end to end on a tiny synthetic load, so option B is technically feasible. The no-writer decision stands, because the go criteria (a customer, cardinality, limits, auth and TLS, retry rules) are untested.

## Remaining acceptance plan (option A and hardening)

1. Repeat with token authentication and TLS on loopback, a missing-value (`value_present=false`) row and a realistic capture of tens of thousands of points to measure the observation-tag cardinality.
2. With approval for the Infinity plugin, render one panel from the synthetic comparison CSV served from loopback.
3. Reconcile counts and one value against `receipt.json`, record versions and delete the folder afterwards.

Until then the line-protocol export stays a finite file mapper with no destination claim.
