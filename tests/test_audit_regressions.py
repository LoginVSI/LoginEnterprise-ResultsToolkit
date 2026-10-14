"""Executed regressions for independently reported coverage and trust risks."""

import json

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from test_evidence_comparison import mock_capture
from test_reports_contracts import check_references
from test_tls_handshakes import server

from le_results.auth import resolve_token
from le_results.client import Client
from le_results.compare import compare
from le_results.diagnostics import approve_trust
from le_results.errors import ToolkitError
from le_results.evidence import TABLES, capture, finalize, load_table, verify_capture
from le_results.profiles import Profile, ProfileStore
from le_results.report import build_report
from le_results.selection import Selection
from le_results.synthetic import APP, BASE, CANDIDATE, SESSION, demo


def test_window_union_preserves_failed_and_already_active_sessions(tmp_path):
    modes = []

    def respond(req):
        if req.url.path.endswith("user-sessions"):
            mode = req.url.params["filterType"]
            modes.append(mode)
            rows = [
                {
                    "id": SESSION if mode == "created" else APP,
                    "testRunId": BASE,
                    "loginState": "failed" if mode == "created" else "succeeded",
                }
            ]
            return httpx.Response(200, json={"items": rows, "offset": 0, "totalCount": 1})
        return mock_capture(req)

    with Client(
        Profile("test", "https://appliance.example.com"),
        "fake",
        transport=httpx.MockTransport(respond),
    ) as client:
        capture(
            client,
            Selection("ApplicationTest", [BASE], "2026-09-01T10:00:00Z", "2026-09-01T11:00:00Z"),
            tmp_path,
        )
    assert modes == ["loggedIn", "created"]
    assert {r["loginState"] for r in load_table(tmp_path, "sessions")} == {"failed", "succeeded"}


def test_timer_only_rejects_aborted_multi_result_capture(tmp_path):
    def respond(req):
        if req.url.path.endswith("test-runs/" + CANDIDATE):
            return httpx.Response(
                200, json={"id": CANDIDATE, "type": "ApplicationTest", "finished": None}
            )
        if "user-session-metrics" in req.url.path:
            return httpx.Response(500)
        return mock_capture(req)

    path = tmp_path / "capture"
    with Client(
        Profile("test", "https://appliance.example.com"),
        "fake",
        transport=httpx.MockTransport(respond),
    ) as client:
        with pytest.raises(ToolkitError):
            capture(client, Selection("ApplicationTest", [BASE, CANDIDATE]), path)
    assert verify_capture(path)["error"]
    config = {
        "schema_version": "comparison/1",
        "coverage_policy": "timer-only",
        "baseline": {"label": "Before", "ids": [BASE, CANDIDATE]},
        "candidate": {"label": "After", "ids": [BASE, CANDIDATE]},
        "metrics": [{"table": "measurements"}],
    }
    with pytest.raises(ToolkitError, match="complete captures"):
        compare(path, path, config)


def test_approved_trust_replacement_refused_before_http(tmp_path):
    store = ProfileStore(tmp_path / "config")
    with server(tmp_path, self_signed=True) as (profile, requests, leaf):
        store.add(Profile(profile.name, profile.origin))
        approve_trust(
            store, profile.name, tmp_path / "trust.pem", [leaf.fingerprint(hashes.SHA256()).hex()]
        )
        approved = store.get(profile.name)
        (tmp_path / "other").mkdir()
        with server(tmp_path / "other", self_signed=True) as (other, _, _):
            (tmp_path / "trust.pem").write_bytes(
                __import__("pathlib").Path(other.ca_bundle).read_bytes()
            )
        with pytest.raises(ToolkitError, match="changed"):
            Client(approved, "fake")
        assert requests == []


def test_timer_identity_does_not_pool_applications(tmp_path):
    demo(tmp_path)
    config = json.loads((tmp_path / "compare.json").read_text())
    del config["metrics"][0]["match"]["applicationId"]
    with pytest.raises(ToolkitError, match="applicationId"):
        compare(tmp_path / "baseline", tmp_path / "candidate", config)
    config["metrics"][0]["group_by"] = ["applicationId"]
    assert (
        compare(tmp_path / "baseline", tmp_path / "candidate", config)["metrics"][0][
            "baseline_mean"
        ]
        == 120
    )


def test_same_run_snapshot_keys_include_role(tmp_path):
    demo(tmp_path / "source")
    config = json.loads((tmp_path / "source/compare.json").read_text())
    config["candidate"]["ids"] = [BASE]
    source = tmp_path / "source/baseline"
    result = compare(source, source, config)
    build_report(result, tmp_path / "report")
    check_references(tmp_path / "report")


def test_malformed_single_response_finalizes_manifest(tmp_path):
    def respond(req):
        if req.url.path.endswith("test-runs/" + BASE):
            return httpx.Response(200, json=[])
        return mock_capture(req)

    with Client(
        Profile("test", "https://appliance.example.com"),
        "fake",
        transport=httpx.MockTransport(respond),
    ) as client:
        with pytest.raises(ToolkitError, match="incomplete"):
            capture(client, Selection("ApplicationTest", [BASE]), tmp_path)
    assert verify_capture(tmp_path)["error"] == "Malformed source response"


def test_extra_file_refused_and_dedup_count_visible(tmp_path):
    demo(tmp_path)
    path = tmp_path / "baseline"
    manifest = verify_capture(path)
    tables = {k: load_table(path, k) for k in TABLES}
    tables["measurements"] += tables["measurements"][:1]
    finalize(path, manifest, tables)
    assert verify_capture(path)["deduplicated_rows"]["measurements"] == 1
    (path / "unlisted.txt").write_text("unreviewed")
    with pytest.raises(ToolkitError, match="unlisted"):
        verify_capture(path)


def test_runtime_override_requires_exact_profile_scope(monkeypatch):
    profile = Profile("one", "https://one.example.com")
    monkeypatch.setenv("LE_RESULTS_TOKEN", "synthetic-token")
    with pytest.raises(ToolkitError, match="exact profile"):
        resolve_token(profile)
    monkeypatch.setenv("LE_RESULTS_TOKEN_SCOPE", profile.credential_ref)
    assert resolve_token(profile) == "synthetic-token"
    with pytest.raises(ToolkitError):
        resolve_token(Profile("one", "https://two.example.com"))


def test_comparison_tampering_rejected_before_report(tmp_path):
    demo(tmp_path / "source")
    config = json.loads((tmp_path / "source/compare.json").read_text())
    result = compare(tmp_path / "source/baseline", tmp_path / "source/candidate", config)
    result["metrics"][0]["baseline_mean"] = 9999
    with pytest.raises(ToolkitError, match="differs"):
        build_report(result, tmp_path / "report")
    assert not (tmp_path / "report").exists()


def test_resource_sort_and_contract_use_verified_client(tmp_path):
    queries = []

    def respond(req):
        if req.url.path.endswith("openapi.json"):
            assert req.url.path == "/publicApi/v8-preview/openapi.json"
            return httpx.Response(200, json={"info": {"version": "8.0-preview"}})
        if "user-session-metrics" in req.url.path:
            queries.append(dict(req.url.params))
            if req.url.params.get("orderBy") != "timestamp":
                return httpx.Response(500)
        return mock_capture(req)

    with Client(
        Profile("test", "https://appliance.example.com"),
        "fake",
        transport=httpx.MockTransport(respond),
    ) as client:
        assert client.get_contract()["info"]["version"] == "8.0-preview"
        capture(client, Selection("ApplicationTest", [BASE]), tmp_path)
    assert queries[0]["orderBy"] == "timestamp" and queries[0]["direction"] == "asc"
    assert verify_capture(tmp_path)["endpoints"][-1]["status"] == "empty"


def test_retry_cannot_spend_remaining_deadline():
    waits = []
    with Client(
        Profile("test", "https://appliance.example.com"),
        "fake",
        deadline_seconds=1,
        sleep=waits.append,
        transport=httpx.MockTransport(lambda _: httpx.Response(429, headers={"Retry-After": "2"})),
    ) as client:
        with pytest.raises(ToolkitError, match="deadline"):
            client.get("system/version")
    assert waits == []


def test_mutating_session_union_retains_raw_but_blocks_acceptance(tmp_path):
    execution_requests = []

    def respond(req):
        if req.url.path.endswith("user-sessions"):
            row = {
                "id": SESSION,
                "testRunId": BASE,
                "loginState": "succeeded",
                "sessionState": "active"
                if req.url.params["filterType"] == "loggedIn"
                else "finished",
            }
            return httpx.Response(200, json={"items": [row], "offset": 0, "totalCount": 1})
        if req.url.path.endswith("app-executions"):
            execution_requests.append(req)
        return mock_capture(req)

    with Client(
        Profile("test", "https://appliance.example.com"),
        "fake",
        transport=httpx.MockTransport(respond),
    ) as client:
        with pytest.raises(ToolkitError, match="incomplete"):
            capture(
                client,
                Selection(
                    "ApplicationTest", [BASE], "2026-09-01T10:00:00Z", "2026-09-01T11:00:00Z"
                ),
                tmp_path,
            )
    manifest = verify_capture(tmp_path)
    assert manifest["status"] == "partial" and manifest["session_query_overlap"][BASE] == 1
    assert manifest["identity_conflicts"][0]["fields"] == ["sessionState"]
    assert len(load_table(tmp_path, "sessions")) == len(execution_requests) == 1
    raw = [json.loads(p.read_text()) for p in (tmp_path / "raw").glob("*.json")]
    states = {
        r.get("sessionState")
        for page in raw
        if isinstance(page, dict)
        for r in page.get("items", [])
        if r.get("id") == SESSION
    }
    assert states == {"active", "finished"}


def test_timer_identity_requires_measurement_id(tmp_path):
    demo(tmp_path)
    config = json.loads((tmp_path / "compare.json").read_text())
    del config["metrics"][0]["match"]["measurementId"]
    with pytest.raises(ToolkitError, match="measurementId"):
        compare(tmp_path / "baseline", tmp_path / "candidate", config)
    config["metrics"][0]["group_by"] = ["measurementId"]
    assert (
        compare(tmp_path / "baseline", tmp_path / "candidate", config)["metrics"][0][
            "baseline_mean"
        ]
        == 120
    )


@pytest.mark.parametrize("removed", ["source_captures", "configuration"])
def test_missing_comparison_provenance_cannot_skip_validation(tmp_path, removed):
    demo(tmp_path / "source")
    config = json.loads((tmp_path / "source/compare.json").read_text())
    result = compare(tmp_path / "source/baseline", tmp_path / "source/candidate", config)
    result["metrics"][0]["baseline_mean"] = 9999
    del result[removed]
    with pytest.raises(ToolkitError, match="Rebuild"):
        build_report(result, tmp_path / "report")
    assert not (tmp_path / "report").exists()


def test_external_capture_report_cannot_bypass_comparison_validation(tmp_path):
    with pytest.raises(ToolkitError, match="comparison-result"):
        build_report(
            {"schema_version": "capture-report/1", "metrics": [{"baseline_mean": 9999}]}, tmp_path
        )
    assert not (tmp_path / "data").exists()


def test_overlapping_pages_preserve_failure(tmp_path):
    def respond(req):
        if req.url.path.endswith("measurements"):
            return httpx.Response(
                200,
                json={
                    "items": [{"measurementId": "same", "duration": 2}],
                    "offset": int(req.url.params["offset"]),
                    "totalCount": 2,
                },
            )
        return mock_capture(req)

    with Client(
        Profile("test", "https://appliance.example.com"),
        "fake",
        page_size=1,
        transport=httpx.MockTransport(respond),
    ) as client:
        with pytest.raises(ToolkitError, match="incomplete"):
            capture(client, Selection("ApplicationTest", [BASE]), tmp_path)
    manifest = verify_capture(tmp_path)
    outcome = next(e for e in manifest["endpoints"] if e["path"].endswith("measurements"))
    assert outcome["status"] == "partial" and outcome["count"] == 2
    assert outcome["diagnostic"]["code"] == "paging_overlap"


def test_offline_doctor_rejects_unscoped_override(tmp_path, monkeypatch):
    from le_results.diagnostics import doctor

    class FakeVault:
        backend = object()

        def get(self, profile):
            return None

    store = ProfileStore(tmp_path)
    store.add(Profile("one", "https://one.example.com"))
    monkeypatch.setattr("le_results.diagnostics.Vault", FakeVault)
    monkeypatch.setenv("LE_RESULTS_TOKEN", "synthetic")
    monkeypatch.delenv("LE_RESULTS_TOKEN_SCOPE", raising=False)
    result = doctor(store, "one", True, None)
    assert not result["ok"] and result["errors"][0]["code"] == "credential_scope"


def test_changing_execution_identity_is_not_two_completed_units(tmp_path):
    def respond(req):
        if req.url.path.endswith("app-executions"):
            rows = [
                {"id": APP, "testRunId": BASE, "userSessionId": SESSION, "state": state}
                for state in ("created", "ended")
            ]
            return httpx.Response(200, json={"items": rows, "offset": 0, "totalCount": 2})
        return mock_capture(req)

    with Client(
        Profile("test", "https://appliance.example.com"),
        "fake",
        transport=httpx.MockTransport(respond),
    ) as client:
        with pytest.raises(ToolkitError, match="incomplete"):
            capture(client, Selection("ApplicationTest", [BASE]), tmp_path)
    manifest = verify_capture(tmp_path)
    assert manifest["status"] == "partial"
    assert manifest["identity_conflicts"][0]["table"] == "executions"
    assert len(load_table(tmp_path, "executions")) == 1
