"""Only explicitly verified native credential stores are accepted."""

import getpass
import os
import sys
import warnings
from typing import Any

import keyring

from .errors import ToolkitError
from .profiles import Profile

SERVICE = "LoginVSI.ResultsToolkit"
ALLOWED = {
    "win32": ("keyring.backends.Windows", "WinVaultKeyring"),
    "darwin": ("keyring.backends.macOS", "Keyring"),
    "linux": ("keyring.backends.SecretService", "Keyring"),
}


class Vault:
    def __init__(self, backend: Any = None, platform: str | None = None) -> None:
        try:
            self.backend = backend if backend is not None else keyring.get_keyring()
        except Exception:
            raise ToolkitError(
                "Native credential store unavailable; configure a native provider."
            ) from None
        kind = type(self.backend)
        if (kind.__module__, kind.__name__) != ALLOWED.get(platform or sys.platform):
            raise ToolkitError(
                "Unsafe or unavailable keyring backend. Use Windows Credential Manager, "
                "macOS Keychain or Linux Secret Service. Headless CI may use "
                "LE_RESULTS_TOKEN as an explicit runtime override."
            )

    def get(self, profile: Profile) -> str | None:
        try:
            return self.backend.get_password(SERVICE, profile.credential_ref)
        except Exception:
            raise ToolkitError("Native credential lookup failed under this user account.") from None

    def set(self, profile: Profile, token: str, replace: bool = False) -> None:
        if not token or any(c.isspace() for c in token):
            raise ToolkitError("Token must be nonempty and contain no whitespace.")
        if self.get(profile) and not replace:
            raise ToolkitError("Credential exists; use auth set --replace explicitly.")
        try:
            self.backend.set_password(SERVICE, profile.credential_ref, token)
        except Exception:
            raise ToolkitError("Native credential persistence failed.") from None

    def delete(self, profile: Profile) -> None:
        if self.get(profile) is None:
            return
        try:
            self.backend.delete_password(SERVICE, profile.credential_ref)
        except Exception:
            raise ToolkitError("Native credential deletion failed.") from None


def hidden_token() -> str:
    if not sys.stdin.isatty():
        raise ToolkitError(
            "Run le-results auth set in your normal interactive terminal. "
            "Hidden input is required; no echoed fallback is permitted."
        )
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            return getpass.getpass("API token (hidden): ")
        except getpass.GetPassWarning:
            raise ToolkitError("Hidden terminal input unavailable.") from None


def resolve_token(profile: Profile) -> str:
    override = os.environ.get("LE_RESULTS_TOKEN")
    token = override if override is not None else Vault().get(profile)
    if not token or any(c.isspace() for c in token):
        raise ToolkitError(
            "No usable credential. Run le-results auth set --profile " + profile.name
        )
    return token
