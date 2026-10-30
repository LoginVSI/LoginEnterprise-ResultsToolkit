"""Write a prepared `observations.lp` into InfluxDB 3 in bounded batches. Example, not a product.

Standard library only. The token comes from an environment variable, never an argument or file in
this repository. TLS is verified; plain HTTP is accepted only for a loopback address. A batch is
all-or-nothing (`accept_partial=false`). Identity of a point is its table, tags and timestamp, and
the mapper puts an observation hash in a tag, so replaying a batch is safe for unchanged data. A
changed source value is a different observation and is stored as an additional point. Resume skips
batches already acknowledged for the same payload hash. Exactly-once delivery is not claimed.
"""

import argparse
import hashlib
import ipaddress
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def batches(lines: list[bytes], size: int, max_bytes: int) -> list[list[bytes]]:
    out: list[list[bytes]] = []
    current: list[bytes] = []
    used = 0
    for line in lines:
        if len(line) + 1 > max_bytes:
            raise ValueError("A single line exceeds the byte bound.")
        if current and (len(current) >= size or used + len(line) + 1 > max_bytes):
            out.append(current)
            current, used = [], 0
        current.append(line)
        used += len(line) + 1
    if current:
        out.append(current)
    return out


def post(url: str, token: str, body: bytes, context: ssl.SSLContext | None, timeout: float) -> int:
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "text/plain; charset=utf-8"},
    )
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        return int(response.status)


def write_file(
    path: Path,
    url: str,
    database: str,
    *,
    token: str,
    ca_file: str | None = None,
    batch_lines: int = 1000,
    max_lines: int = 200_000,
    max_batch_bytes: int = 4 * 1024 * 1024,
    retries: int = 2,
    timeout: float = 30,
    sleep: Any = time.sleep,
) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Use an http(s) URL.")
    if parsed.scheme == "http" and not loopback(parsed.hostname):
        raise ValueError("Plain HTTP is allowed only for a loopback address; use https.")
    data = path.read_bytes()
    lines = [line.rstrip(b"\r") for line in data.split(b"\n") if line.strip()]
    if not 1 <= len(lines) <= max_lines:
        raise ValueError(f"Expected 1-{max_lines} lines.")
    digest = hashlib.sha256(data).hexdigest()
    receipt_path = path.with_name(path.name + ".write-receipt.json")
    done: set[int] = set()
    if receipt_path.is_file():
        previous = json.loads(receipt_path.read_text(encoding="utf-8"))
        if previous.get("payload_sha256") == digest and previous.get("database") == database:
            done = set(previous.get("acknowledged_batches", []))
    plan = batches(lines, batch_lines, max_batch_bytes)
    context = ssl.create_default_context(cafile=ca_file) if parsed.scheme == "https" else None
    query = urllib.parse.urlencode(
        {"db": database, "precision": "nanosecond", "accept_partial": "false"}
    )
    endpoint = f"{parsed.scheme}://{parsed.netloc}/api/v3/write_lp?{query}"
    receipt: dict[str, Any] = {
        "schema_version": "lp-write-receipt/1",
        "database": database,
        "payload_sha256": digest,
        "lines": len(lines),
        "batches": len(plan),
        "acknowledged_batches": sorted(done),
        "failed_batch": None,
        "error": None,
        "scope": "Acknowledged means the server returned success for that batch. Not exactly-once.",
    }
    for index, batch in enumerate(plan):
        if index in done:
            continue
        body = b"\n".join(batch) + b"\n"
        for attempt in range(retries + 1):
            try:
                post(endpoint, token, body, context, timeout)
                done.add(index)
                receipt["acknowledged_batches"] = sorted(done)
                break
            except urllib.error.HTTPError as exc:
                if exc.code < 500:  # a rejected batch will not improve on retry
                    receipt.update(failed_batch=index, error=f"HTTP {exc.code}")
                    break
                receipt.update(failed_batch=index, error=f"HTTP {exc.code}")
            except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
                reason = getattr(exc, "reason", exc)
                receipt.update(failed_batch=index, error=type(reason).__name__)
            if attempt < retries:
                sleep(0.5 * 2**attempt)
        else:
            break
        if index in done:
            receipt.update(failed_batch=None, error=None)
            continue
        break
    receipt["complete"] = len(done) == len(plan)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--ca-file")
    parser.add_argument("--token-env", default="INFLUXDB3_TOKEN")
    parser.add_argument("--batch-lines", type=int, default=1000)
    args = parser.parse_args()
    token = os.environ.get(args.token_env)
    if not token:
        print(f"Set {args.token_env} in your environment; the token is never read from arguments.")
        return 2
    try:
        receipt = write_file(
            args.file,
            args.url,
            args.database,
            token=token,
            ca_file=args.ca_file,
            batch_lines=args.batch_lines,
        )
    except (ValueError, OSError) as exc:
        print(f"Not written: {exc}")
        return 2
    print(
        json.dumps(
            {k: receipt[k] for k in ("lines", "batches", "complete", "failed_batch", "error")}
        )
    )
    return 0 if receipt["complete"] else 2


if __name__ == "__main__":
    sys.exit(main())
