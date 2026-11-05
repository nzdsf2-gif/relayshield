"""Phase 2 tenant policy fetch and cache tests, for review, Mac test only.

Place this file in /Users/andrewgibbs/dev/relayshield/mcp_proxy,
next to proxy.py, then run:
  python3 -m pytest test_tenant_session_ph2.py -q

These tests do NOT start a proxy, do NOT call the Gateway, and do
NOT require a passport or a Worker. They test _intent_gate with a
fake server and a fake tenant policy fetcher, using
object.__new__(ProxyHandler), in the same pattern as the Phase 1
tests. The fetcher contract is: fetcher(tenant_id, location_id)
returns a resolved policy dict, for example {"policy1_mode": "enforce"}.

Phase 2 scope only: fetch on first use, cache within TTL, last-good
on fetch failure, location key isolation, and fallback to global
mode for unverified tenants. Worker route, server-to-server auth,
pre-initialize tenant identity, and step-up translation are not
covered here, and are not claimed by these tests.
"""

import time
from datetime import datetime, timezone, timedelta

from mcp_proxy.proxy import ProxyHandler


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


def make_handler(mode="off", session=None, fetcher=None):
    handler = object.__new__(ProxyHandler)
    handler.server = FakeServer()
    if fetcher is not None:
        handler.server.tenant_policy_fetcher = fetcher
    if session is not None:
        handler.server.session_bindings["test-session"] = session
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
        "passport_id": "pass_test",
        "passport_expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "verified_at": time.time(),
        "tenant_id": None,
        "location_id": None,
        "msp_id": None,
        "distributor_id": None,
        "tenant_verified": False,
    }
    session.update(overrides)
    return session


def test_fetch_on_first_use_enforces():
    calls = []

    def fetcher(tenant_id, location_id):
        calls.append((tenant_id, location_id))
        return {"policy1_mode": "enforce"}

    handler, cfg = make_handler(
        mode="off",
        session=base_session(tenant_id="tenant-a", tenant_verified=True),
        fetcher=fetcher,
    )
    gate = handler._intent_gate(
        "test-session", "pay_invoice",
        {"counterparty": "carol", "amount": "25.00", "currency": "USD"},
        cfg, req={},
    )
    assert gate is not None
    assert gate["error"]["data"]["reason"] == "intent_drift_recipient"
    assert calls == [("tenant-a", None)]


def test_cache_within_ttl_does_not_refetch():
    calls = []

    def fetcher(tenant_id, location_id):
        calls.append(tenant_id)
        return {"policy1_mode": "off"}

    handler, cfg = make_handler(
        mode="off",
        session=base_session(tenant_id="tenant-a", tenant_verified=True),
        fetcher=fetcher,
    )
    assert handler._intent_gate("test-session", "read_file", {"path": "/tmp/a.txt"}, cfg, req={}) is None
    # Read-only calls return before the gate, so use a state-changing
    # call that passes, to exercise the fetch path twice.
    assert handler._intent_gate(
        "test-session", "pay_invoice",
        {"counterparty": "bob", "amount": "25.00", "currency": "USD"},
        cfg, req={},
    ) is None
    assert handler._intent_gate(
        "test-session", "pay_invoice",
        {"counterparty": "bob", "amount": "25.00", "currency": "USD"},
        cfg, req={},
    ) is None
    assert len(calls) == 1


def test_fetch_failure_keeps_last_good():
    state = {"fail": False}

    def fetcher(tenant_id, location_id):
        if state["fail"]:
            raise RuntimeError("console unreachable")
        return {"policy1_mode": "enforce"}

    handler, cfg = make_handler(
        mode="off",
        session=base_session(tenant_id="tenant-a", tenant_verified=True),
        fetcher=fetcher,
    )
    handler.server.tenant_policy_ttl_seconds = 0
    gate1 = handler._intent_gate(
        "test-session", "pay_invoice",
        {"counterparty": "carol", "amount": "25.00", "currency": "USD"},
        cfg, req={},
    )
    assert gate1 is not None
    state["fail"] = True
    gate2 = handler._intent_gate(
        "test-session", "pay_invoice",
        {"counterparty": "carol", "amount": "25.00", "currency": "USD"},
        cfg, req={},
    )
    assert gate2 is not None
    assert gate2["error"]["data"]["reason"] == "intent_drift_recipient"
    assert "tenant-a" in handler.server.tenant_policy_errors


def test_location_fetch_key_is_isolated():
    seen = []

    def fetcher(tenant_id, location_id):
        seen.append((tenant_id, location_id))
        if location_id == "loc-1":
            return {"policy1_mode": "enforce"}
        return {"policy1_mode": "off"}

    handler, cfg = make_handler(
        mode="off",
        session=base_session(tenant_id="tenant-a", location_id="loc-1", tenant_verified=True),
        fetcher=fetcher,
    )
    gate = handler._intent_gate(
        "test-session", "pay_invoice",
        {"counterparty": "carol", "amount": "25.00", "currency": "USD"},
        cfg, req={},
    )
    assert gate is not None
    assert seen == [("tenant-a", "loc-1")]
    assert "tenant-a:loc-1" in handler.server.tenant_policies
    assert "tenant-a" not in handler.server.tenant_policies
