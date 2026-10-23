import pytest

from le_results.auth import Vault, hidden_token
from le_results.errors import ToolkitError
from le_results.profiles import Profile, ProfileStore, canonical_origin


class FakeNative:
    def __init__(self):
        self.values = {}

    def get_password(self, service, ref):
        return self.values.get((service, ref))

    def set_password(self, service, ref, value):
        self.values[(service, ref)] = value

    def delete_password(self, service, ref):
        del self.values[(service, ref)]


@pytest.mark.parametrize(
    "url",
    [
        "http://host",
        "https://u:p@host",
        "https://host/publicApi",
        "https://host?token=x",
        "https://host/#x",
    ],
)
def test_unsafe_origins_rejected(url):
    with pytest.raises(ToolkitError):
        canonical_origin(url)


def test_origin_canonicalization():
    assert canonical_origin("https://EXAMPLE.com:443/") == "https://example.com"
    assert canonical_origin("https://example.com:8443") == "https://example.com:8443"


def test_backend_rejects_plaintext_null_and_chainer():
    for name in ["PlaintextKeyring", "Keyring", "ChainerBackend"]:
        unsafe = type(name, (), {"__module__": "keyrings.alt.file"})()
        with pytest.raises(ToolkitError, match="Unsafe"):
            Vault(unsafe, "win32")


def test_vault_host_and_profile_isolation():
    # Test double intentionally has native identity; production constructor uses installed backend.
    native = type("WinVaultKeyring", (FakeNative,), {"__module__": "keyring.backends.Windows"})
    vault = Vault(native(), "win32")
    one, two = Profile("one", "https://one.example"), Profile("one", "https://two.example")
    vault.set(one, "test-only-value")
    assert vault.get(one) == "test-only-value" and vault.get(two) is None
    assert vault.get(Profile("another", one.origin)) is None
    with pytest.raises(ToolkitError, match="exists"):
        vault.set(one, "replacement")
    vault.set(one, "replacement", replace=True)
    vault.delete(one)
    assert vault.get(one) is None


def test_profile_store_preserves_unrelated_and_never_stores_secret(tmp_path):
    store = ProfileStore(tmp_path)
    store.add(Profile("first", "https://one.example"))
    store.add(Profile("second", "https://two.example"))
    with pytest.raises(ToolkitError, match="exists"):
        store.add(Profile("first", "https://three.example"))
    store.add(Profile("first", "https://three.example"), replace=True)
    assert store.get("second").origin == "https://two.example"
    assert "credential_ref" in store.read()["first"]
    assert "token" not in store.path.read_text()


def test_no_noninteractive_secret_prompt(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(ToolkitError, match="interactive terminal"):
        hidden_token()


def test_profile_list_refuses_unexpected_secret_fields(tmp_path):
    store = ProfileStore(tmp_path)
    store.path.write_text(
        '{"lab": {"origin": "https://host.example", "api_version": "v8-preview", "token": "do-not-echo"}}'
    )
    with pytest.raises(ToolkitError) as error:
        store.read()
    assert "do-not-echo" not in str(error.value)
