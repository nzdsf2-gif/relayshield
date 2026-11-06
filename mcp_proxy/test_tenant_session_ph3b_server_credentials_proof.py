"""Phase 3b per-tenant server credentials P1 proof, for review, Mac test only.

Place this file in /Users/andrewgibbs/dev/relayshield/mcp_proxy,
next to proxy.py, then run:
  python3 -m pytest test_tenant_session_ph3b_server_credentials_proof.py -q

These tests do NOT start a proxy, do NOT call the Gateway or the
Worker, and do NOT require a passport. They test the TenantSecrets
store, the sync endpoint call, and _fetch_tenant_policy with a
fake server, using object.__new__(ProxyHandler) and a mocked
urlopen, in the same pattern as the Phase 2 tests. Env vars are
set inside each test and restored in a finally block.

What this proves:
1. The store: set/get, persistence across a reload, corrupt
   file starts empty.
2. Sync: the proxy calls the sync endpoint with the bootstrap
   key, stores the returned keys in the local file, and
   skips sync entirely when the URL env is unset.
3. Policy fetch: the proxy sends the tenant's policy_key as
   the Bearer token, never the global key.
4. Fail closed: a verified tenant whose policy-key marker is
   set is gated as Enforce, so an intent-drift call blocks;
   a transient fetch error string does not fail closed, and
   a tenant policy of Off still allows.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from mcp_proxy.proxy import ProxyHandler
from mcp_proxy.tenant_secrets import TenantSecrets


class FakeServer:
    def __init__(self):
        self.session_bindings = {}
        self.tenant_policies = {}
        self.tenant_policy_cache = {}
        self.tenant_policy_errors = {}
        self.tenant_policy_ttl_seconds = 60


class FakeCfg:
    def __init__(self, mode="off"):
        self.intent_binding_mode = mode


class FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def make_handler(mode="off", session=None, fetcher=None, secrets_path=None):
    handler = object.__new__(ProxyHandler)
    handler.server = FakeServer()
    if fetcher is not None:
        handler.server.tenant_policy_fetcher = fetcher
    if session is not None:
        handler.server.session_bindings["test-session"] = session
    if secrets_path is not None:
        handler.server.tenant_secrets = TenantSecrets(path=secrets_path)
    return handler, FakeCfg(mode)


def base_session(**overrides):
    session = {
        "binding_id": "bind_test",
        "payer": "alice",
        "counterparty": "bob",
        "amount": "25.00",
        "currency": "USD",
        "artifacts": [],
        "step_up": {},
        "passport_id": None,
        "passport_expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "verified_at": 0,
        "tenant_id": "tenant-a",
        "location_id": None,
        "msp_id": None,
        "distributor_id": None,
        "tenant_verified": True,
    }
    session.update(overrides)
    return session


def test_store_persists_and_corrupt_starts_empty(tmp_path):
    path = str(tmp_path / "secrets.json")
    store = TenantSecrets(path=path)
    assert store.get("tenant-a", "policy_key") is None
    assert store.set("tenant-a", "policy_key", "pk-1") is True
    assert store.set("tenant-a", "policy_key", "pk-1") is False
    assert store.get("tenant-a", "policy_key") == "pk-1"
    assert store.get("tenant-a", "screener_key") is None
    reloaded = TenantSecrets(path=path)
    assert reloaded.get("tenant-a", "policy_key") == "pk-1"
    assert reloaded.get("tenant-b", "policy_key") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert TenantSecrets(path=str(bad)).get("tenant-a", "policy_key") is None


def test_sync_stores_keys_and_skips_when_unconfigured(tmp_path):
    path = str(tmp_path / "secrets.json")
    handler, _ = make_handler(secrets_path=path)
    old_url = os.environ.pop("MCP_PROXY_TENANT_KEYS_URL", None)
    old_boot = os.environ.pop("MCP_PROXY_TENANT_POLICY_KEY", None)
    try:
        assert handler._sync_tenant_keys("tenant-a") is False
        os.environ["MCP_PROXY_TENANT_KEYS_URL"] = "https://example.invalid/api/provisioning/tenants/{tenant_id}/keys"
        os.environ["MCP_PROXY_TENANT_POLICY_KEY"] = "bootstrap-key"
        seen = {}

        def fake_urlopen(request, timeout=5):
            seen["url"] = request.full_url
            seen["auth"] = request.headers.get("Authorization")
            return FakeResponse({"data": {"policy_key": "pk-1", "screener_key": "sk-1", "collector_secret": "cs-1"}})

        with patch("urllib.request.urlopen", fake_urlopen):
            assert handler._sync_tenant_keys("tenant-a") is True
        assert seen["url"] == "https://example.invalid/api/provisioning/tenants/tenant-a/keys"
        assert seen["auth"] == "Bearer bootstrap-key"
        store = handler.server.tenant_secrets
        assert store.get("tenant-a", "policy_key") == "pk-1"
        assert store.get("tenant-a", "screener_key") == "sk-1"
        assert store.get("tenant-a", "collector_secret") == "cs-1"
    finally:
        if old_url is None:
            os.environ.pop("MCP_PROXY_TENANT_KEYS_URL", None)
        else:
            os.environ["MCP_PROXY_TENANT_KEYS_URL"] = old_url
        if old_boot is None:
            os.environ.pop("MCP_PROXY_TENANT_POLICY_KEY", None)
        else:
            os.environ["MCP_PROXY_TENANT_POLICY_KEY"] = old_boot


def test_policy_fetch_sends_tenant_key_not_global(tmp_path):
    path = str(tmp_path / "secrets.json")
    handler, _ = make_handler(secrets_path=path)
    handler.server.tenant_secrets.set("tenant-a", "policy_key", "tenant-policy-key-1")
    old_url = os.environ.get("MCP_PROXY_TENANT_POLICY_URL")
    old_boot = os.environ.get("MCP_PROXY_TENANT_POLICY_KEY")
    os.environ["MCP_PROXY_TENANT_POLICY_URL"] = "https://example.invalid/api/provisioning/tenants/{tenant_id}/resolved-policy"
    os.environ["MCP_PROXY_TENANT_POLICY_KEY"] = "global-key"
    seen = {}

    def fake_urlopen(request, timeout=5):
        seen["auth"] = request.headers.get("Authorization")
        return FakeResponse({"policy1_mode": "enforce"})

    try:
        with patch("urllib.request.urlopen", fake_urlopen):
            policy = handler._fetch_tenant_policy({"tenant_id": "tenant-a", "location_id": None})
    finally:
        if old_url is None:
            os.environ.pop("MCP_PROXY_TENANT_POLICY_URL", None)
        else:
            os.environ["MCP_PROXY_TENANT_POLICY_URL"] = old_url
        if old_boot is None:
            os.environ.pop("MCP_PROXY_TENANT_POLICY_KEY", None)
        else:
            os.environ["MCP_PROXY_TENANT_POLICY_KEY"] = old_boot
    assert policy == {"policy1_mode": "enforce"}
    assert seen["auth"] == "Bearer tenant-policy-key-1"


def test_missing_key_fails_closed_at_gate(tmp_path):
    handler, cfg = make_handler(session=base_session(), secrets_path=str(tmp_path / "secrets.json"))
    handler.server.tenant_policy_errors["tenant-a"] = "missing_policy_key"
    args = {"counterparty": "carol", "amount": "25.00", "currency": "USD"}
    gate = handler._intent_gate("test-session", "pay_invoice", args, cfg)
    assert gate is not None
    assert gate["error"]["data"]["reason"] == "intent_drift_recipient"


def test_transient_error_does_not_fail_closed(tmp_path):
    def fetcher(tenant_id, location_id):
        return {"policy1_mode": "off"}

    handler, cfg = make_handler(session=base_session(), fetcher=fetcher, secrets_path=str(tmp_path / "secrets.json"))
    handler.server.tenant_policy_errors["tenant-a"] = "connection timed out"
    args = {"counterparty": "carol", "amount": "25.00", "currency": "USD"}
    assert handler._intent_gate("test-session", "pay_invoice", args, cfg) is None


def test_policy_off_still_allows(tmp_path):
    def fetcher(tenant_id, location_id):
        return {"policy1_mode": "off"}

    handler, cfg = make_handler(session=base_session(), fetcher=fetcher, secrets_path=str(tmp_path / "secrets.json"))
    args = {"counterparty": "carol", "amount": "25.00", "currency": "USD"}
    assert handler._intent_gate("test-session", "pay_invoice", args, cfg) is None
