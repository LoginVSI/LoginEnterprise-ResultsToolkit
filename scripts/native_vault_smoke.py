"""Nonsecret disposable native vault roundtrip under the current account."""

import sys
from uuid import uuid4

from le_results.auth import Vault
from le_results.profiles import Profile


def main() -> None:
    vault = Vault()
    profile = Profile("smoke-" + uuid4().hex, "https://vault-smoke.example.com")
    try:
        vault.set(profile, "nonsecret-disposable-smoke-value")
        assert vault.get(profile) == "nonsecret-disposable-smoke-value"
    finally:
        vault.delete(profile)
    assert vault.get(profile) is None
    print(f"Native {sys.platform} vault roundtrip passed; disposable entry removed.")


if __name__ == "__main__":
    main()
