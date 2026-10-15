# Readiness, certificates and safe diagnostics

Start with `scripts/Test-LEResultsReadiness.ps1` if Python may be missing or the project environment may be broken. It runs before engine imports, using the checkout executable by default; `-Python PATH` selects another environment. No activation, administrator terminal, system PATH edit or global execution-policy change is required. If policy blocks scripts, invoke documented Python commands directly or use your organization's approved script-signing path.

`auth status` reports native backend and credential presence without returning the token. `doctor --offline` checks profile, runtime, provider, credential and trust-file configuration. It never claims a successful TLS handshake. `doctor` separately records DNS, TCP, verified TLS and the read-only `system/version` request. `--out DIRECTORY` checks writability. Output is JSON. Exit codes are 0 for success, 2 for diagnosis/failure and 130 for cancellation.

```powershell
.\scripts\Test-LEResultsReadiness.ps1 -Profile lab -OutputDirectory .private\readiness
.\.venv\Scripts\le-results.exe doctor --profile lab
```

## Inspect and approve profile trust

Use an HTTPS origin. If trust fails, inspect a candidate on a credential-free connection:

```powershell
.\.venv\Scripts\le-results.exe certificate --profile lab --out .private\certificate-review-01
```

This sends no HTTP, accesses no vault and enrolls no trust. It records the presented chain where the runtime exposes it, subject/issuer, SAN coverage, dates, Basic Constraints, key usage/EKU, SHA-256 fingerprints and runtime metadata. Python 3.11 exposes the leaf only through the public socket API. Certificate fields are untrusted data. A matching SAN or fetched fingerprint does not establish trust.

Obtain public trust material from an approved administrator source, or reuse an exact certificate already enrolled in an approved local trust store. Compare fingerprints independently, rather than fetching the endpoint twice. For an internal CA, determine whether client CA trust is missing or the server omitted an intermediate. The client needs public certificates, never a private key, PFX password or token in chat.

Keep the approved PEM bundle in a user-writable location. Supply one independently approved fingerprint for every certificate in it:

```powershell
.\.venv\Scripts\le-results.exe trust --profile lab --ca-bundle .private\trust\approved.pem --approved-sha256 REPLACE_WITH_APPROVED_SHA256
.\.venv\Scripts\le-results.exe doctor --profile lab
```

`trust` checks fingerprints and validity, then stores the resolved path and approved fingerprints in the nonsecret profile. Every client/doctor context checks those fingerprints again and loads the inspected bytes. Replacing the file does not silently approve another anchor. `profile add` creates the origin first; use `trust` for certificate approval. Existing profiles with an unpinned bundle need this approval step again using the independently approved material. Certificate and hostname validation remain enabled. `doctor` must subsequently establish verified TLS and HTTP access.

The toolkit explicitly enables strict and partial-chain verification on every supported runtime, including Python 3.11. An approved exact leaf can terminate profile trust when the presented chain permits it. This can help when independent leaf trust already exists and an older issuing CA is unsuitable for strict validation. It does not repair the server chain for other clients. A self-signed `CA:false` leaf can be explicitly trusted: synthetic HTTPS tests cover that case. Basic Constraints alone cannot decide the outcome. See [Python SSL defaults](https://docs.python.org/3.14/library/ssl.html) and [OpenSSL verification rules](https://docs.openssl.org/3.4/man1/openssl-verification-options/).

For rotation, inspect into a new directory, independently approve fingerprints, replace profile trust and run `doctor` again. Keep old evidence. To remove profile trust without deleting credentials or files:

```powershell
.\.venv\Scripts\le-results.exe trust --profile lab --remove
```

The profile returns to Python default trust. No Windows root store changes. For server repair, provide the SAN hostname, fingerprint, verification code and missing extension/intermediate. Strict verification stays enabled. The toolkit never replaces appliance certificates, changes Allowed URLs or restarts services.

## Diagnose the established failure

| Evidence/code | Smallest next action |
|---|---|
| Python missing, unsupported or broken environment | Install a user-local 64-bit runtime, preserve the old environment, recreate `.venv` with an explicit executable and install locks. 3.11/3.14 are the verification matrix; other architectures/runtimes need separate checks. |
| Unwritable output | Choose a new directory owned by your user. Capture/report destinations must be empty. |
| Missing profile | `profile add lab --url https://appliance.example.com` with the explicit adapter. |
| Unsafe/unavailable vault | Use Windows Credential Manager, macOS Keychain or Linux Secret Service. Plaintext, null, chained and alternate backends are refused. |
| Missing credential | `auth set --profile lab` in a normal terminal with hidden input. Presence does not prove token validity. |
| Missing/malformed trust file | Restore approved public PEM material or remove profile trust. Private-key bundles are refused. |
| Untrusted/self-signed chain | Independently confirm trust material, configure profile trust and verify again. |
| Missing issuer/incomplete chain | Compare the presented chain with approved CA material; distinguish missing client trust from missing server intermediates. |
| `certificate_hostname` | Use the approved SAN hostname or request a conforming server certificate. |
| Expired/not-yet-valid certificate | Check the clock and obtain renewed approved material. |
| `certificate_ca_key_usage` (OpenSSL 92) | Issuing CA lacks required key usage. Request a conforming chain; test already-approved profile trust where supported. Never clear strict flags. |
| `dns_failed` | Verify the origin and DNS route. |
| `connection_refused` | Verify the TCP listener/route. A generic HTTPS failure alone does not establish a blocked port. |
| `timeout` | Narrow the window and determine the failing phase. A timeout does not establish DNS or TLS failure. |
| 401 | Check expiry/revocation; replace explicitly with `auth set --replace`. |
| 403 | Ask for Login Enterprise result-read permission. Windows elevation is unrelated. |
| 404/incompatible schema | Verify the v8-preview route and contract. There is no v7 fallback. |
| HTTP 500 | Preserve outcomes/pages. The observed 6.9.2 session-metric route fails when optional `orderBy` is omitted; the adapter now explicitly sends `orderBy=timestamp` and `direction=asc`. Verify a new bounded capture before calling acquisition recovered. Other 500 causes remain unknown; give the administrator the route, query, timestamp and observed version. |
| Bound or later-page failure | Inspect partial manifest/raw pages and recapture a narrower selection into a new directory. |
| Disabled/empty/missing metric | Preserve its status. Configured-but-empty differs from disabled. Missing measurements never become zero. |
| Unknown transport | Leave it unknown; diagnostics never copy arbitrary exception strings or claim an unestablished cause. |

## Separate trust and credential domains

Python uses its verified SSL context and optional profile PEM. Windows/browser trust follows that application's certificate policy. Power BI/Power Query trust and Key enrollment are separate from the profile and vault. Appliance outbound CA trust concerns LDAP, mail and other outbound services; that store is not a general client HTTPS fix. A browser warning click-through is not runtime validation. [Login VSI's versioned certificate guidance](https://docs.loginvsi.com/login-enterprise/6.6/managing-certificates-on-the-appliance) documents server/outbound procedures; the toolkit does not execute them. This public reference was available during review; newer-version certificate guidance was not independently located.

The HTTP client uses direct routing and `trust_env=False`, so [HTTPX environment proxies](https://www.python-httpx.org/environment_variables/) are not implicit. Diagnosis reports only variable presence, never values. If the network requires a proxy, have its owner supply an approved route. The toolkit does not alter global proxy/security configuration. Python default CA loading may use the runtime's trust environment; a profile bundle selects that file. Toolkit TLS key logging is disabled.

Use native Windows Python under the vault-enrolled account. WSL has separate Linux credentials and trust. Native Linux/macOS persistence remains separately unverified. `LE_RESULTS_TOKEN` is an explicitly chosen headless override, not encrypted persistence or a customer default. It requires `LE_RESULTS_TOKEN_SCOPE` equal to the selected profile's nonsecret `credential_ref` from `profile list`; switching origins/profiles fails closed. No token files are introduced. Never print tokens or put them in arguments, report parameters or M source. Redirects are refused and reflected secrets are redacted. Capture manifests record redaction and exact-duplicate counts. Review result data before sharing it outside the private workspace.

Recommendation failures are retained per metadata/detail/session/observation probe. Request/deadline exhaustion is reported explicitly; narrow the scope before retrying. A successful one-record sample proves that observation exists, not collection health. Missing enabled fields remain unknown. `export` exits 2 when the manifest is partial/failed; `verify` checks hashes and reports status without upgrading completeness.

Native PDF errors preserve HTTP/authentication distinctions, response encoding/byte/deadline failures and a refused existing destination. A write failure may leave a partial new file; keep it as failed evidence and use a new path. The credential-reflection check covers raw bytes only, not every embedded compressed/encoded PDF object.
