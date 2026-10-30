# Power BI Service and gateway readiness

This is preparation, not acceptance. No tenant, workspace or gateway was available, and none was provisioned. The Toolkit does not build a gateway and does not reuse the LE-PBI connector, its credentials or its API target. Each connector is accepted on its own evidence.

## What the Toolkit connector provides

| Requirement (Microsoft, on-premises data gateway) | Toolkit state |
|---|---|
| A `TestConnection` section in the connector | Implemented: `ResultsToolkit.Ping` over the data source path. Static M parse passes in CI. Not executed by a gateway |
| Key authentication | `Key` with label "Login Enterprise API token"; the token is read through `Extension.CurrentCredential()` and redacted from outputs |
| Credential scope | The data source path is the appliance origin; configuration is not part of the credential path |
| Connector folder readable by the gateway service | Owner action: the default service account is `NT SERVICE\PBIEgwService`, which cannot read folders under a user profile |
| Standard gateway with custom connectors enabled, and a data source created for the connector | Owner action in the tenant |
| One custom-connector data source in DirectQuery | Not applicable: the Toolkit builds import-mode projects |

The Toolkit snapshot projects read local JSON files and do not need a gateway for the file path unless the files are on a machine the Service cannot reach. Only the refreshable connector projects ask the gateway to call the appliance.

## Gateway acceptance checklist (for an existing authorized environment)

1. Place the signed or accepted `.mez` in a folder outside any user profile that the gateway service account can read. Point the gateway app's custom connector folder at it and restart the gateway service.
2. Enable custom connectors on the cluster, then add a data source for the Toolkit connector with the appliance origin. Enter the API token through the Service's credential dialog, never in a query or a file.
3. Confirm the test connection succeeds and fails clearly with a wrong token and an untrusted certificate. The gateway machine must trust the appliance certificate in the way Power Query does, separately from Python trust.
4. Publish one generated live project, run a manual refresh and compare the loaded counts, units and failure coverage with a Python capture of the same fixed window.
5. Only then schedule refresh. Record the gateway version, connector hash, identity, outcome and any error text without hostnames.

Not covered by any local check: Service-side credential storage, gateway service-account trust, refresh timeouts and the Service's row and time limits.

## Evidence contract for the LE-PBI handoff

A short list the two projects can agree on without editing each other: each project names its own connector file hash, gateway version, tenant region class (not name), data source kind, credential type, the API target version and the fixed window used, and reports the loaded row counts per table plus the newest source observation timestamp. Neither project infers success from the other's result.

## Freshness

A successful scheduled refresh over a fixed window reloads the same retained history. Use the newest source observation, not the refresh time, to judge currency. The command-line job reports both (see [scheduling](scheduling.md)); the connector has no freshness table yet.
