"""Validate generated files against Microsoft's public schemas, caching locally."""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit

import httpx
import jsonschema
from referencing import Registry, Resource


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--cache", type=Path, default=Path(".private/powerbi-schemas"))
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    fetched = {}

    def retrieve(uri):
        url = urldefrag(uri)[0]
        if urlsplit(url).hostname != "developer.microsoft.com" or not url.startswith("https://"):
            raise ValueError("Only official Microsoft schemas are permitted")
        path = args.cache / (hashlib.sha256(url.encode()).hexdigest() + ".json")
        if not path.exists():
            response = httpx.get(url, timeout=30, follow_redirects=False)
            response.raise_for_status()
            path.write_bytes(response.content)
        doc = json.loads(path.read_text(encoding="utf-8"))

        # Absolutize references because embedded schemas sometimes omit $id.
        def refs(value):
            if isinstance(value, dict):
                if "$ref" in value and not value["$ref"].startswith("#"):
                    value["$ref"] = urljoin(url, value["$ref"])
                for item in value.values():
                    refs(item)
            elif isinstance(value, list):
                for item in value:
                    refs(item)

        refs(doc)
        fetched[url] = hashlib.sha256(path.read_bytes()).hexdigest()
        return Resource.from_contents(doc)

    registry = Registry(retrieve=retrieve)
    count = 0
    for path in args.directory.rglob("*"):
        if path.suffix not in (".json", ".pbip", ".pbir", ".pbism"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "$schema" in data:
            uri = data["$schema"]
            resource = retrieve(uri)
            validator = jsonschema.Draft7Validator(
                resource.contents, registry=registry.with_resource(uri, resource)
            )
            errors = list(validator.iter_errors(data))
            if errors:
                for error in errors:
                    print(
                        path.relative_to(args.directory),
                        "/".join(map(str, error.path)),
                        error.message,
                    )
                raise SystemExit(1)
            count += 1
    (args.cache / "provenance.json").write_text(
        json.dumps(fetched, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Validated {count} Power BI files against official schemas. Desktop execution remains a separate check."
    )


if __name__ == "__main__":
    main()
