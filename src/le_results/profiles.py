"""Nonsecret configuration, deliberately outside the checkout."""

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from platformdirs import user_config_path

from .errors import ToolkitError


def canonical_origin(value: str) -> str:
    try:
        url = urlsplit(value)
        port = url.port
    except ValueError:
        raise ToolkitError("Invalid HTTPS appliance origin.") from None
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.path not in ("", "/")
        or url.query
        or url.fragment
    ):
        raise ToolkitError("Use an HTTPS origin without credentials, path, query or fragment.")
    host = url.hostname.lower().encode("idna").decode("ascii")
    if ":" in host:
        host = f"[{host}]"
    return f"https://{host}" + (f":{port}" if port and port != 443 else "")


@dataclass(frozen=True)
class Profile:
    name: str
    origin: str
    api_version: str = "v8-preview"
    ca_bundle: str | None = None
    approved_sha256: tuple[str, ...] = ()

    @property
    def credential_ref(self) -> str:
        digest = hashlib.sha256(self.origin.encode()).hexdigest()
        return f"{self.name}:{digest}"


def config_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ["LOCALAPPDATA"]) / "LoginVSI" / "ResultsToolkit"
    return user_config_path("ResultsToolkit", "LoginVSI")


class ProfileStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.path = (directory or config_dir()) / "profiles.json"

    def read(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            profiles = json.loads(self.path.read_text(encoding="utf-8"))
            allowed = {"origin", "api_version", "ca_bundle", "credential_ref", "approved_sha256"}
            if not isinstance(profiles, dict) or any(
                not isinstance(v, dict) or set(v) - allowed for v in profiles.values()
            ):
                raise ValueError
            for name, values in profiles.items():
                if not isinstance(values.get("origin"), str) or not isinstance(values.get("api_version"), str):
                    raise ValueError
                origin = canonical_origin(values["origin"])
                if values.get("ca_bundle") is not None and not isinstance(values["ca_bundle"], str):
                    raise ValueError
                fingerprints = values.get("approved_sha256", [])
                if not isinstance(fingerprints, list) or any(
                    not isinstance(value, str) or not re.fullmatch("[A-F0-9]{64}", value)
                    for value in fingerprints
                ):
                    raise ValueError
                if values.get("credential_ref", Profile(name, origin).credential_ref) != Profile(name, origin).credential_ref:
                    raise ValueError
            return profiles
        except (ValueError, OSError):
            raise ToolkitError(
                "Cannot read profiles.json; repair it before making changes."
            ) from None

    def get(self, name: str) -> Profile:
        values = self.read().get(name)
        if values is None:
            raise ToolkitError("Profile missing. Run le-results profile add first.")
        profile = Profile(
            name,
            canonical_origin(str(values["origin"])),
            str(values["api_version"]),
            values.get("ca_bundle"),
            tuple(values.get("approved_sha256") or ()),
        )
        canonical_origin(profile.origin)
        if profile.api_version != "v8-preview":
            raise ToolkitError("Only the explicit v8-preview adapter is implemented.")
        return profile

    def add(self, profile: Profile, replace: bool = False) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", profile.name):
            raise ToolkitError(
                "Profile alias must use 1-64 letters, digits, underscores or hyphens."
            )
        if profile.api_version != "v8-preview":
            raise ToolkitError("Only v8-preview is supported.")
        profiles = self.read()
        if profile.name in profiles and not replace:
            raise ToolkitError("Profile exists; use --replace explicitly.")
        data = asdict(profile)
        data["origin"] = canonical_origin(profile.origin)
        data["credential_ref"] = Profile(profile.name, data["origin"]).credential_ref
        data.pop("name")
        profiles[profile.name] = data
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(profiles, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
