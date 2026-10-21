# Preview compatibility and release readiness

The branch and draft PR remain the review destination. No release or main merge is authorized by these checks. MIT is bundled by owner authorization. Final acceptance/merge/publication remain owner decisions.

| Contract / artifact | Version and compatibility boundary |
|---|---|
| Python package | 0.1.0a1, Python >=3.11; CI exercises 3.11/3.14 on Windows/Linux/macOS. Other versions/ARM/native-emulated combinations are unverified. |
| Appliance adapter | Explicit v8-preview only; observed Login Enterprise 6.9.2. Selected operations are exercised, not every API/build. v7 is reference only. |
| Capture, selection, comparison/report | `/1` schemas; raw source + hashes + completeness retained. Regenerate older comparisons that lack configuration/source provenance. |
| Refreshable comparison | `live-report/1` -> `acquisition/1`, at most four distinct selected results. |
| Refreshable single source | `live-selection/1` -> `acquisition/2`, exactly one ID, same finite acquisition security and error barriers. Requires the rebuilt connector. |
| Optional line-protocol file | `line-protocol-export/1`, ns precision, prepared-not-written; no destination/runtime compatibility claim. |
| Power BI | Observed Desktop 2.159.883.0 x64. One snapshot and one fixed-window live project owner-accepted; source/read-only DAX reconcile. Rolling, new data, forced-offline and broader negative Mashup fixtures remain separate. |
| Credential/platform | Native Windows enrollment/persistence and verified trust exercised. Actual non-admin and native Linux/macOS vault proof need suitable accounts/hosts. Hosted core CI is separate. |

Build a wheel with `python -m build --wheel --outdir artifacts/wheels` and the unsigned development connector with `python scripts/build_connector.py --out artifacts/ResultsToolkit.mez`. Create a source archive from the reviewed final commit, record SHA-256 checksums, dependency locks and public-content check results. Install the wheel with committed hash locks in a new user-local environment outside the checkout and exercise demo/verify/compare/finite/snapshot/single-live/file-export workflows. Customers need no private development references.

Release gates:

- MIT LICENSE and package metadata are bundled; preserve upstream reuse boundaries and notices. No unlicensed source/assets are copied.
- Tests, lint/types, audits, packaging, Windows wrappers, report schemas and generated/connector M pass on final head; verify all CI jobs on that head.
- Review public source/PR/release text for credentials, appliance identities, customer/internal context and personal paths. Ignore rules alone are insufficient.
- Record actual snapshot local-file refresh/editable save, error/identity M fixtures, connector policy/Key/trust, two live refreshes and source reconciliation before claiming Desktop acceptance. New-data proof requires advancing source observations.
- Keep native vault, standard-user and untested architecture limits visible. Do not manufacture proof by changing accounts or policy.
- Owner decides final merge/release/blog publication. Prepare artifacts and release notes first; keep preview unsupported and unpublished until those decisions.

Service/gateway distribution needs its own connector/trust support, organizational approval, destination credentials and controlled refresh/reconciliation tests. No tenant publication, scheduled refresh or compatibility promise follows from Desktop file checks. Optional destinations and internal productization are separate proposals.
