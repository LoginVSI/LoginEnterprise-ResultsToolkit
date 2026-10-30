# Optional finite time-series export

This extension does not change the preview prerequisites. `export-line-protocol` maps verified complete captures to files only. Chosen evaluation target: **InfluxDB 3 Core 3.12.0 with SQL and Grafana 13.2's InfluxDB data source**. A disposable loopback proof on 28 October wrote the prepared synthetic file with the InfluxDB 3 write API, queried it with SQL and rendered a Grafana 13.3.0 dashboard; counts and means matched. The toolkit itself still writes no database, and authentication, TLS and scale were not tested. See the [assessment](grafana-influxdb-assessment.md).

```powershell
le-results export-line-protocol --capture artifacts/demo/baseline --max-records 10000 --out artifacts/time-series
```

The command writes `observations.lp` and `receipt.json`. Default limit is 10,000 source observations; maximum 100,000 and 64 MiB payload. Failed/partial captures, invalid timestamps, unsafe field types and existing populated destinations are refused. Receipt status is `prepared-not-written`; no acquisition/write checkpoint advances.

Timers and session metrics use separate tables, raw row grain and original source timestamps at nanosecond precision. Missing values emit `value_present=false` without a numeric zero. Timer units remain unknown when absent; no unit conversion or aggregate weighting is performed. Source unit/field/instance/session/result identity and endpoint-derived result markers are retained. Unsafe large integer-to-float conversions are rejected.

InfluxDB 3 identifies points by table, tags and timestamp. Its documented overwrite behavior is nondeterministic. The mapper puts an observation hash in a tag to distinguish different observations sharing a timestamp; changed source values append distinct versions. Equivalent timestamp spellings canonicalize to the same instant for identity, while each batch and original capture retains the original text. Database overwrite behavior can select either source_json spelling; the capture stays authoritative. Exact overlapping acquisition metadata is excluded from identity. This can create substantial series/cardinality and requires target performance/retention testing. The raw capture remains authoritative.

See the [official line-protocol reference](https://docs.influxdata.com/influxdb3/core/reference/line-protocol/) for escaping, precision and point identity; [Grafana's InfluxDB guidance](https://grafana.com/docs/grafana/latest/datasources/influxdb/) describes SQL configuration. These sources document the target, not this toolkit's runtime acceptance.

An example query for a reviewed group is:

```sql
SELECT time, value, value_present, unit, instance, field_name
FROM le_session_metrics
WHERE $__timeFilter(time)
  AND result_id = 'REPLACE_WITH_REVIEWED_ID'
  AND metric_id = 'CPU' AND unit = '%'
ORDER BY time
```

Select one metric/field/unit/instance, show missing-value and capture coverage alongside the series, and avoid calling observations independent devices. `source_json` can contain private account/host metadata; review files before transfer. A disposable synthetic setup/query/dashboard fixture is a future runtime check, not a working integration claim.

Destination credentials must be separate native credentials with destination-specific scope; never reuse the appliance token. No write command is included until a disposable destination can verify authentication, partial-write behavior and query reconciliation. Incremental acquisition/resume is not implemented: use new frozen overlapping captures, inspect late arrivals/conflicting versions and deduplicate canonically. A future checkpoint must commit only after complete acquisition and confirmed writes, with replay-safe crash/retry behavior. Service/gateway refresh and streaming remain separate follow-ups.
