# Grafana and InfluxDB feasibility

This repository owns the assessment. LE-PBI should not build a duplicate stack. The runtime of options A and B is **unverified**: no Grafana or InfluxDB software was downloaded or run in this change, because a download needs owner approval and nothing here justifies touching shared infrastructure. The Login Enterprise appliance's internal Grafana and InfluxDB were not touched.

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

## Bounded acceptance plan (needs owner approval to download)

1. Pin Grafana 13.2.x and InfluxDB 3 Core 3.12.x from official release artifacts into an ignored `.private/` folder, bound to loopback, no public exposure, no Docker, no services.
2. Prepare a synthetic capture, run `export-line-protocol`, write with a one-off script using a test-only token, then query the count and a known value with SQL.
3. Render one Grafana panel and one Infinity panel from the synthetic comparison CSV.
4. Reconcile point and row counts and one value against `receipt.json`. Record versions, setup and cleanup. Delete the folder afterwards.

Until then the line-protocol export stays a finite file mapper with no destination claim.
