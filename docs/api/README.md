# Sanitized contract snapshots

`openapi-v8-preview.json` is the implementation contract; `openapi-v7.json` is reference only. `provenance.json` records the verified info.version, original SHA-256, sanitized SHA-256 and transformations. Original supplied bytes stay private and unchanged.

Run `python scripts/prepare_contracts.py --source-root PATH_TO_PRIVATE_INPUTS` only when updating owner-supplied inputs. Resolve that path from the original checkout if using a worktree. Review the entire output before committing, not only info/servers. The script removes examples/contact and replaces absolute URLs in all strings. Tests verify public hashes and read-only adapter routes. These snapshots establish contract facts, not an appliance compatibility claim.
