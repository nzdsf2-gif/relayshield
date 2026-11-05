"""Phase 1 tenant session gate tests, for review, Mac test only.

Place this file in /Users/andrewgibbs/dev/relayshield/mcp_proxy,
next to proxy.py, then run:
  python3 -m pytest test_tenant_session_gate.py -q

These tests do NOT start a proxy, do NOT call the Gateway, and do
NOT require a passport. They test _intent_gate directly, with a
fake server and config, using object.__new__(ProxyHandler), in the
same pattern as test_intent_binding_gate.py.

Phase 1 scope only: verified tenant policy resolution from
server.tenant_policies, unverified tenant fallback to global mode,
gate error stamping, and dedicated no-tenant regression. Console
fetch, AuditTrail stamping, quarantine, rate limit, tools list,
and signed verdict scoping are Phase 2 and Phase 3, not here.
"""

import time
from datetime import datetime, timezone, timedelta

from mcp_proxy.proxy import ProxyHandler


class FakeServer:
    def __init__(self):
        self.session_bindings = {}
        self.tenant_policies = {}


class FakeCfg:
    def __init__(self, mode="off"):
        self.intent_binding_mode = mode


def make_handler(mode="off", session=None, tenant_policies=None):
    handler = object.__new__(ProxyHandler)
    handler.server = FakeServer()
    handler.server.tenant_policies = tenant_policies or {}
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


def test_no_session_uses_global_mode_not_tenant_policy():
    # Design limitation, stated plainly: a call with no session has
    # no tenant to resolve, so the gate cannot apply a tenant policy
    # to it. It must use the global mode. For a shared instance,
    # tenant identity before initialize, for example a /t/{tenantId}
    # route or an agent mapping, is needed to distinguish a missing
    # binding call for an Off tenant from one for an Enforce tenant.
    # That pre-initialize identity is a Phase 2 design item, not
    # hidden by this test.
    policies = {"tenant-a": {"policy1_mode": "enforce"}}
    handler, cfg = make_handler(mode="off", session=None, tenant_policies=policies)
    assert handler._intent_gate("test-session", "pay_invoice", {"counterparty": "bob", "amount": "25.00"}, cfg, req={}) is None


def test_two_tenants_same_msp_isolated():
    policies = {
        "tenant-a": {"policy1_mode": "enforce"},
        "tenant-b": {"policy1_mode": "off"},
    }
    # Tenant A, Enforce, with a matching session, then a drifted call.
    handler_a, cfg_a = make_handler(
        mode="off",
        session=base_session(tenant_id="tenant-a", tenant_verified=True, msp_id="msp-1"),
        tenant_policies=policies,
    )
    gate_a = handler_a._intent_gate(
        "test-session", "pay_invoice",
        {"counterparty": "carol", "amount": "25.00", "currency": "USD"},
        cfg_a, req={},
    )
    assert gate_a is not None
    assert gate_a["error"]["data"]["reason"] == "intent_drift_recipient"

    # Tenant B, Off, same MSP, same drifted call, must not block.
    handler_b, cfg_b = make_handler(
        mode="off",
        session=base_session(tenant_id="tenant-b", tenant_verified=True, msp_id="msp-1"),
        tenant_policies=policies,
    )
    gate_b = handler_b._intent_gate(
        "test-session", "pay_invoice",
        {"counterparty": "carol", "amount": "25.00", "currency": "USD"},
        cfg_b, req={},
    )
    assert gate_b is None


def test_unverified_tenant_does_not_get_tenant_policy():
    policies = {"tenant-a": {"policy1_mode": "enforce"}}
    handler, cfg = make_handler(
        mode="off",
        session=base_session(tenant_id="tenant-a", tenant_verified=False),
        tenant_policies=policies,
    )
    # Unverified tenant, global Off, drifted call must not block,
    # proving a client-supplied tenant_id alone does not grant policy.
    gate = handler._intent_gate(
        "test-session", "pay_invoice",
        {"counterparty": "carol", "amount": "25.00", "currency": "USD"},
        cfg, req={},
    )
    assert gate is None


def test_location_policy_wins_over_tenant_policy():
    policies = {
        "tenant-a": {"policy1_mode": "off"},
        "tenant-a:loc-1": {"policy1_mode": "enforce"},
    }
    handler, cfg = make_handler(
        mode="off",
        session=base_session(
            tenant_id="tenant-a", location_id="loc-1", tenant_verified=True,
        ),
        tenant_policies=policies,
    )
    gate = handler._intent_gate(
        "test-session", "pay_invoice",
        {"counterparty": "carol", "amount": "25.00", "currency": "USD"},
        cfg, req={},
    )
    assert gate is not None
    assert gate["error"]["data"]["reason"] == "intent_drift_recipient"


def test_dedicated_no_tenant_uses_global_mode():
    handler, cfg = make_handler(mode="enforce", session=None)
    gate = handler._intent_gate(
        "test-session", "pay_invoice",
        {"counterparty": "bob", "amount": "25.00"},
        cfg, req={},
    )
    assert gate is not None
    assert gate["error"]["data"]["reason"] == "missing_binding"


def test_read_only_still_passes_for_verified_tenant():
    policies = {"tenant-a": {"policy1_mode": "enforce"}}
    handler, cfg = make_handler(
        mode="off",
        session=base_session(tenant_id="tenant-a", tenant_verified=True),
        tenant_policies=policies,
    )
    assert handler._intent_gate(
        "test-session", "read_file", {"path": "/tmp/a.txt"}, cfg, req={},
    ) is None
