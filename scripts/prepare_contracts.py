"""Publish sanitized contracts without modifying private originals."""

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: sanitize(v) for k, v in value.items() if k not in ("contact", "example", "examples")
        }
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        return re.sub(r"https?://[^\s\"<>]+", "https://appliance.example.com", value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=Path(".private/api-input"))
    args = parser.parse_args()
    dest = Path("docs/api")
    dest.mkdir(parents=True, exist_ok=True)
    provenance = []
    for name, version in [("openapi-v8-preview.json", "8.0-preview"), ("openapi-v7.json", "7.0")]:
        original = (args.source_root / name).read_bytes()
        spec = json.loads(original.decode("utf-8-sig"))
        assert spec["info"]["version"] == version, "Unexpected API contract version"
        assert spec["servers"] == [{"url": "/publicApi"}]
        clean = sanitize(spec)
        content = (json.dumps(clean, indent=2, ensure_ascii=True) + "\n").encode()
        (dest / name).write_bytes(content)
        provenance.append(
            {
                "file": name,
                "info_version": version,
                "original_sha256": hashlib.sha256(original).hexdigest(),
                "sanitized_sha256": hashlib.sha256(content).hexdigest(),
                "source": "Owner-supplied OpenAPI export, September 2026 inputs",
                "sanitization": "Removed examples/contact; replaced absolute URLs in all strings",
            }
        )

        # Every local reference must resolve. This validates graph integrity, not live behavior.
        def check(value: Any, document: Any = clean) -> None:
            if isinstance(value, dict):
                if "$ref" in value:
                    ref = value["$ref"]
                    assert ref.startswith("#/"), "External reference not permitted"
                    target = document
                    for key in ref[2:].split("/"):
                        target = target[key.replace("~1", "/").replace("~0", "~")]
                for v in value.values():
                    check(v, document)
            elif isinstance(value, list):
                for v in value:
                    check(v, document)

        check(clean)
    (dest / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print("Sanitized two contracts; versions and local reference graphs validated.")


if __name__ == "__main__":
    main()
