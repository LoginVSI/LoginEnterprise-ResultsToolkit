# Credentials and diagnostics

`auth status` shows profile, backend and credential-presence metadata. It never returns the token. `doctor --offline` checks local configuration/provider metadata; `doctor` also requests the documented system/version endpoint through trusted HTTPS.

| Diagnostic | Action |
|---|---|
| Missing local credential | Run `le-results auth set --profile lab` once in a normal terminal with hidden input |
| Credential already exists | Replace explicitly with `auth set --replace`; no repeated enrollment prompt |
| 401 | Token may have expired or been revoked; replace it explicitly after checking appliance token state |
| 403 | Token lacks permission; ask the appliance administrator for the required result-read access |
| Unsafe/unavailable keyring backend | Use native Windows Credential Manager, macOS Keychain or Linux Secret Service; plaintext/null/chained/alternate persistence is refused |
| HTTPS connection/certificate failure | Check DNS and certificate chain; supply a reviewed CA bundle with `profile add --ca-bundle PATH --replace`; there is no insecure-TLS option |
| 429 / long Retry-After | Wait and retry later; automatic waits and retry attempts are bounded |
| Paging offset/total mismatch or later-page failure | Inspect the partial manifest/raw pages and recapture a narrower selection to a new directory |
| Empty data outside retention | Check retention and available summaries; empty raw rows do not prove that no activity occurred |
| Missing metric or invalid unit | Inspect raw evidence and collector definitions, then correct explicit metric configuration; do not use zero as a fallback |
| Ambiguous name | Review bounded discovery and select explicit IDs; names do not prove identity or operating system |
| Desktop connector not visible | Verify extension installation/trust policy manually; the project does not install or weaken security settings automatically |

On Windows, keep the wrapper on native Windows Python under the same account that enrolled the credential. WSL is a separate Linux environment and must not be assumed to share Windows Credential Manager. Verify its provider separately if used. Linux desktops may need a running Secret Service session and `PYTHON_KEYRING_BACKEND=keyring.backends.SecretService.Keyring`; macOS requires Keychain access under the enrolled user. These native providers require platform smoke evidence before claiming persistence works there.

Headless CI can supply `LE_RESULTS_TOKEN` through an explicitly chosen runtime secret provider. This overrides vault lookup for requests. An environment variable is not encrypted storage; no automatic `.env` persistence exists. Do not print it or place its value in process arguments. CI's offline tests need no credential.

Authorization bodies/headers, sensitive fields and reflected credential text are redacted from capture data and excluded from request diagnostics. The client does not follow redirects, uses no implicit proxy from environment variables, and sends credentials only to its configured origin. Python string memory zeroization is not promised. Result data may still contain personal or customer information; review it before sharing with any reporting or AI host.
