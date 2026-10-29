# Grafana with InfluxDB 3 (synthetic proof files)

`datasource.yaml` and `dashboard.json` are Grafana provisioning files from the loopback proof in [the assessment](../../docs/grafana-influxdb-assessment.md). They read `le_measurements` points written from `le-results export-line-protocol` output into a database named `leproof`. Set the data source URL for your own InfluxDB 3 server and keep it on a trusted network. Add authentication and TLS settings before any real use; the proof used neither. The panels are labeled synthetic and pin UTC.
