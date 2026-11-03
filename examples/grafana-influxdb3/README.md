# Grafana with InfluxDB 3 (example)

A small, optional example for teams that already run Grafana and InfluxDB 3. It is not part of the engine. Evidence and limits are in [the assessment](../../docs/grafana-influxdb-assessment.md).

Files: `datasource.yaml` and `dashboard.json` (Grafana provisioning), `write_lp.py` (standard-library writer).

## Use

```powershell
# 1. Prepare points from a verified complete capture
le-results export-line-protocol --capture artifacts/review/baseline --out artifacts/lp

# 2. Write them (PowerShell 7). The token comes from your environment, never an argument.
$env:INFLUXDB3_TOKEN = Read-Host -AsSecureString | ConvertFrom-SecureString -AsPlainText   # type it; do not paste into chat
python examples/grafana-influxdb3/write_lp.py --file artifacts/lp/observations.lp --url https://influx.example.com:8181 --database leproof --ca-file path\to\ca.pem
```

On Linux or macOS export the variable in your shell instead. The writer sends bounded batches (`--batch-lines`, default 1000) with `accept_partial=false`, verifies TLS, allows plain HTTP only to a loopback address and writes `observations.lp.write-receipt.json` next to the file. Re-running the same file resumes after the last acknowledged batch. Re-running a changed file replays everything, which is safe for unchanged data because each point carries an observation-hash tag. A changed source value is stored as an additional point.

## Dashboard

`dashboard.json` opens on an explicit UTC range (the synthetic fixture window) and has two selectors: result (baseline or candidate, multi-select) and action (one at a time). The first panel plots the selected action by result. The table shows timing points, missing values, first and last observation and min, mean and max per result and action. It never averages across actions. A failed execution has no timing, so it has no point; failures and run completion are in the companion HTML or PDF report from the same capture. Change the time range to your own data before use.

## Data source and TLS

`datasource.yaml` points Grafana at an HTTPS InfluxDB with a CA you supply and reads the token from `INFLUXDB3_TOKEN`. Do not use skip-verify. This was verified against InfluxDB 3 Core 3.12.0 and Grafana 13.3.0 on loopback with a disposable CA and synthetic data: the health check passed with the CA and failed without it, and the dashboard queries matched direct SQL.

## Limits

InfluxDB 3 Core 3.12 has admin tokens only, so the writer's token has full rights; keep the server on a trusted network. Delivery is not exactly-once. Failures and completion context are not in the points; take them from the capture receipt. Chart one action at a time and never read a mean of mixed actions as a verdict. The dashboard pins UTC and is labeled synthetic; point it at your own database before use.

## Cleanup

Stop the server, delete its data folder and revoke the token. The receipt files are yours to keep or delete.
