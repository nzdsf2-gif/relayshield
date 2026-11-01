"""Unit tests for Option B v4 intent gate, for review and for the Mac tree.

Place this file in /Users/andrewgibbs/dev/relayshield/mcp_proxy, next to proxy.py,
then run: python3 -m pytest test_intent_binding_gate.py -q

These tests do NOT start a proxy, do NOT call the Gateway, and do NOT require
a passport. They test _intent_gate, _tool_is_read_only, _intent_mismatch,
and _to_minor directly, with a fake server and config, using
object.__new__(ProxyHandler) to avoid BaseHTTPRequestHandler __init__.

Expected: all tests pass on v4, with intent_binding_mode Off, Audit, and
Enforce exercised separately. The one pre-existing failure in test_proxy.py,
test_no_indicators_allows, is unrelated and is not covered here.
"""
import time
from datetime import datetime, timezone, timedelta

from mcp_proxy.proxy import (
    ProxyHandler,
    _intent_mismatch,
    _to_minor,
    _tool_is_read_only,
)


class FakeServer:
    def __init__(self):
        self.session_bindings = {}


class FakeCfg:
    def __init__(self, mode="off"):
        self.intent_binding_mode = mode


def make_handler(mode="off", session=None):
    handler = object.__new__(ProxyHandler)
    handler.server = FakeServer()
    if session is not None:
        handler.server.session_bindings["test-session"] = session
    cfg = FakeCfg(mode)
    return handler, cfg


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
    }
    session.update(overrides)
    return session


def test_read_only_tools_pass():
    assert _tool_is_read_only("list_files", {}) is True
    assert _tool_is_read_only("read_file", {"path": "/tmp/a.txt"}) is True
    assert _tool_is_read_only("get_status", {}) is True
    assert _tool_is_read_only("tools/list", {}) is True


def test_state_changing_tools_are_not_read_only():
    assert _tool_is_read_only("create_order", {}) is False
    assert _tool_is_read_only("send_message", {}) is False
    assert _tool_is_read_only("pay_invoice", {}) is False
    assert _tool_is_read_only("http_post", {}) is False


def test_unknown_tool_defaults_to_state_changing():
    assert _tool_is_read_only("base64_encode", {}) is False
    assert _tool_is_read_only("some_future_tool", {}) is False


def test_read_verb_with_write_argument_is_state_changing():
    assert _tool_is_read_only("get_customer", {"amount": "25.00"}) is False


def test_gate_off_returns_none_even_without_session():
    handler, cfg = make_handler(mode="off")
    assert handler._intent_gate("test-session", "pay_invoice", {"counterparty": "bob", "amount": "25.00"}, cfg, req={}) is None


def test_gate_audit_returns_none_even_without_session():
    handler, cfg = make_handler(mode="audit")
    assert handler._intent_gate("test-session", "pay_invoice", {"counterparty": "bob", "amount": "25.00"}, cfg, req={}) is None


def test_gate_enforce_blocks_missing_binding():
    handler, cfg = make_handler(mode="enforce")
    gate = handler._intent_gate("test-session", "pay_invoice", {"counterparty": "bob", "amount": "25.00"}, cfg, req={})
    assert gate is not None
    assert gate["error"]["data"]["reason"] == "missing_binding"


def test_gate_enforce_allows_read_only_without_session():
    handler, cfg = make_handler(mode="enforce")
    assert handler._intent_gate("test-session", "read_file", {"path": "/tmp/a.txt"}, cfg, req={}) is None


def test_gate_enforce_allows_matching_payment():
    handler, cfg = make_handler(mode="enforce", session=base_session())
    gate = handler._intent_gate("test-session", "pay_invoice", {"counterparty": "bob", "amount": "25.00", "currency": "USD"}, cfg, req={})
    assert gate is None


def test_gate_enforce_blocks_amount_drift():
    handler, cfg = make_handler(mode="enforce", session=base_session())
    gate = handler._intent_gate("test-session", "pay_invoice", {"counterparty": "bob", "amount": "26.00", "currency": "USD"}, cfg, req={})
    assert gate is not None
    assert gate["error"]["data"]["reason"] == "intent_drift_amount"


def test_gate_enforce_blocks_recipient_drift():
    handler, cfg = make_handler(mode="enforce", session=base_session())
    gate = handler._intent_gate("test-session", "pay_invoice", {"counterparty": "carol", "amount": "25.00", "currency": "USD"}, cfg, req={})
    assert gate is not None
    assert gate["error"]["data"]["reason"] == "intent_drift_recipient"


def test_gate_enforce_blocks_expired_passport():
    expired = base_session(passport_expires_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat())
    handler, cfg = make_handler(mode="enforce", session=expired)
    gate = handler._intent_gate("test-session", "pay_invoice", {"counterparty": "bob", "amount": "25.00", "currency": "USD"}, cfg, req={})
    assert gate is not None
    assert gate["error"]["data"]["reason"] == "passport_expired"


def test_gate_enforce_blocks_step_up_missing():
    step_up = base_session(step_up={"required": True, "satisfied_by": ["human_approval"]})
    handler, cfg = make_handler(mode="enforce", session=step_up)
    gate = handler._intent_gate("test-session", "pay_invoice", {"counterparty": "bob", "amount": "25.00", "currency": "USD"}, cfg, req={})
    assert gate is not None
    assert gate["error"]["data"]["reason"] == "step_up_attestation_missing"


def test_gate_enforce_allows_step_up_satisfied():
    step_up = base_session(step_up={"required": True, "satisfied_by": ["human_approval"]})
    handler, cfg = make_handler(mode="enforce", session=step_up)
    req = {"params": {"_meta": {"attestations": [{"method": "human_approval", "evidence_ref": "ev1", "attested_at": "2026-10-31T00:00:00Z"}]}}}
    gate = handler._intent_gate("test-session", "pay_invoice", {"counterparty": "bob", "amount": "25.00", "currency": "USD"}, cfg, req=req)
    assert gate is None


def test_to_minor_usd_and_jpy():
    assert _to_minor("25.00", "USD") == 2500
    assert _to_minor("100", "JPY") == 100
    assert _to_minor("25", "USD") == 2500


def test_intent_mismatch_direct():
    session = base_session()
    assert _intent_mismatch(session, "pay_invoice", {"counterparty": "bob", "amount": "25.00", "currency": "USD"}) is None
    assert _intent_mismatch(session, "pay_invoice", {"counterparty": "bob", "amount": "99.00", "currency": "USD"}) == "intent_drift_amount"
    assert _intent_mismatch(session, "pay_invoice", {"counterparty": "carol", "amount": "25.00", "currency": "USD"}) == "intent_drift_recipient"
