"""Phase 3b step-up translation proof, for review, Mac test only.

Place this file in /Users/andrewgibbs/dev/relayshield/mcp_proxy,
next to proxy.py, then run:
  python3 -m pytest test_tenant_session_ph3b_step_up_proof.py -q

These tests do NOT start a proxy, do NOT call the Gateway, and do
NOT require a passport or a Worker. They test _intent_gate with a
fake server and a fake tenant policy fetcher, using
object.__new__(ProxyHandler), in the same pattern as the Phase 1
and Phase 2 tests. The known-recipients store uses a tmp file,
never the real default path. Sessions carry passport_id None so
no passport status lookup runs.

What this proves:
1. The extraction helpers: recipient first-present wins, amount
   minor units first, decimal fields converted, none when absent.
2. The known-recipients store: record, is_known, persistence
   across a reload, corrupt file starts empty.
3. Policy 2 amount: a call at or above the tenant threshold
   blocks without an attestation and allows with human_approval.
4. Policy 2 unknown recipient: a call to a recipient the tenant
   has not seen blocks, then allows once recorded, and the
   binding's bound counterparty never triggers.
5. Policy 2 content flag: a screening verdict of flag blocks,
   allow and block verdicts do not trigger.
6. The binding floor: a binding step-up still blocks when
   Policy 2 is disabled, and Policy 2 cannot waive it.
7. Audit: a would-require is logged and the call is allowed.
8. The _intent_mismatch refactor: the existing drift checks
   still return the same reasons.
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone, timedelta

from mcp_proxy.known_recipients import KnownRecipients
from mcp_proxy.proxy import (
    ProxyHandler,
    _extract_amount_minor,
    _extract_recipient,
    _intent_mismatch,
)


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


def make_handler(mode="off", session=None, fetcher=None, known_path=None):
    handler = object.__new__(ProxyHandler)
    handler.server = FakeServer()
    if fetcher is not None:
        handler.server.tenant_policy_fetcher = fetcher
    if session is not None:
        handler.server.session_bindings["test-session"] = session
    if known_path is not None:
        handler.server.known_recipients = KnownRecipients(path=known_path)
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


def _policy2_fetcher(policy=None):
    def fetcher(tenant_id, location_id):
        return dict(policy or {"policy1_mode": "enforce", "policy2_step_up_enabled": True, "step_up_amount_threshold": 10000})
    return fetcher


def _attested_req():
    return {"params": {"_meta": {"attestations": [{"method": "human_approval"}]}}}


def _gate(handler, cfg, args, req=None, screen_verdict=None):
    return handler._intent_gate("test-session", "pay_invoice", args, cfg, req=req, screen_verdict=screen_verdict)


def test_extract_recipient_and_amount():
    assert _extract_recipient({"counterparty": "Carol"}) == "carol"
    assert _extract_recipient({"to": "Dave", "counterparty": "Carol"}) == "carol"
    assert _extract_recipient({}) is None
    assert _extract_amount_minor({"amount_minor": 15000}) == 15000
    assert _extract_amount_minor({"amount": "150.00"}, "USD") == 15000
    assert _extract_amount_minor({"amount": "25.00"}, "USD") == 2500
    assert _extract_amount_minor({}) is None
    try:
        _extract_amount_minor({"amount": "not-a-number"}, "USD")
    except ValueError:
        pass
    else:
        raise AssertionError("unparseable amount must raise ValueError")


def test_known_recipients_persists_and_corrupt_starts_empty(tmp_path):
    path = str(tmp_path / "known.json")
    store = KnownRecipients(path=path)
    assert store.is_known("tenant-a", "carol") is False
    assert store.record("tenant-a", "Carol") is True
    assert store.record("tenant-a", "carol") is False
    assert store.is_known("tenant-a", "CAROL") is True
    reloaded = KnownRecipients(path=path)
    assert reloaded.is_known("tenant-a", "carol") is True
    assert reloaded.is_known("tenant-b", "carol") is False
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert KnownRecipients(path=str(bad)).is_known("tenant-a", "carol") is False


def test_policy2_amount_blocks_and_allows(tmp_path):
    handler, cfg = make_handler(
        session=base_session(amount="150.00"),
        fetcher=_policy2_fetcher(),
        known_path=str(tmp_path / "known.json"))
    args = {"counterparty": "bob", "amount": "150.00", "currency": "USD"}
    gate = _gate(handler, cfg, args)
    assert gate is not None
    assert gate["error"]["data"]["reason"] == "step_up_attestation_missing"
    assert gate["error"]["data"]["step_up_triggers"] == ["amount"]
    assert _gate(handler, cfg, args, req=_attested_req()) is None


def test_policy2_amount_below_threshold_allows(tmp_path):
    handler, cfg = make_handler(
        session=base_session(amount="25.00"),
        fetcher=_policy2_fetcher(),
        known_path=str(tmp_path / "known.json"))
    assert _gate(handler, cfg, {"counterparty": "bob", "amount": "25.00", "currency": "USD"}) is None


def test_policy2_unknown_recipient_blocks_then_allows(tmp_path):
    known_path = str(tmp_path / "known.json")
    session = base_session(counterparty=None, amount="25.00")
    handler, cfg = make_handler(session=session, fetcher=_policy2_fetcher(), known_path=known_path)
    args = {"counterparty": "carol", "amount": "25.00", "currency": "USD"}
    gate = _gate(handler, cfg, args)
    assert gate is not None
    assert gate["error"]["data"]["reason"] == "step_up_attestation_missing"
    assert gate["error"]["data"]["step_up_triggers"] == ["unknown_recipient"]
    handler.server.known_recipients.record("tenant-a", "carol")
    assert _gate(handler, cfg, args) is None


def test_policy2_bound_counterparty_never_triggers(tmp_path):
    handler, cfg = make_handler(
        session=base_session(amount="25.00"),
        fetcher=_policy2_fetcher(),
        known_path=str(tmp_path / "known.json"))
    assert _gate(handler, cfg, {"counterparty": "bob", "amount": "25.00", "currency": "USD"}) is None


def test_policy2_content_flag(tmp_path):
    handler, cfg = make_handler(
        session=base_session(amount="25.00"),
        fetcher=_policy2_fetcher(),
        known_path=str(tmp_path / "known.json"))
    args = {"counterparty": "bob", "amount": "25.00", "currency": "USD"}
    gate = _gate(handler, cfg, args, screen_verdict={"verdict": "flag", "level": "high"})
    assert gate is not None
    assert gate["error"]["data"]["step_up_triggers"] == ["content_flag"]
    assert _gate(handler, cfg, args, screen_verdict={"verdict": "allow", "level": "unknown"}) is None
    assert _gate(handler, cfg, args, screen_verdict={"verdict": "block", "level": "high"}) is None


def test_binding_floor_when_policy2_disabled(tmp_path):
    fetcher = _policy2_fetcher({"policy1_mode": "enforce"})
    session = base_session(amount="25.00", step_up={"required": True, "satisfied_by": ["human_approval"]})
    handler, cfg = make_handler(session=session, fetcher=fetcher, known_path=str(tmp_path / "known.json"))
    args = {"counterparty": "bob", "amount": "25.00", "currency": "USD"}
    gate = _gate(handler, cfg, args)
    assert gate is not None
    assert gate["error"]["data"]["reason"] == "step_up_attestation_missing"
    assert gate["error"]["data"]["step_up_triggers"] == []
    assert _gate(handler, cfg, args, req=_attested_req()) is None


def test_audit_logs_would_require(tmp_path, caplog):
    fetcher = _policy2_fetcher({"policy1_mode": "audit", "policy2_step_up_enabled": True, "step_up_amount_threshold": 10000})
    handler, cfg = make_handler(
        session=base_session(amount="150.00"),
        fetcher=fetcher,
        known_path=str(tmp_path / "known.json"))
    with caplog.at_level(logging.INFO):
        gate = _gate(handler, cfg, {"counterparty": "bob", "amount": "150.00", "currency": "USD"})
    assert gate is None
    assert "step_up_would_require" in caplog.text


def test_policy2_disabled_no_trigger(tmp_path):
    fetcher = _policy2_fetcher({"policy1_mode": "enforce"})
    session = base_session(counterparty=None, amount="25.00")
    handler, cfg = make_handler(session=session, fetcher=fetcher, known_path=str(tmp_path / "known.json"))
    assert _gate(handler, cfg, {"counterparty": "carol", "amount": "25.00", "currency": "USD"}) is None


def test_intent_mismatch_still_works():
    session = base_session()
    assert _intent_mismatch(session, "pay_invoice", {"counterparty": "carol", "amount": "25.00", "currency": "USD"}) == "intent_drift_recipient"
    assert _intent_mismatch(session, "pay_invoice", {"counterparty": "bob", "amount": "99.00", "currency": "USD"}) == "intent_drift_amount"
    assert _intent_mismatch(session, "pay_invoice", {"counterparty": "bob", "amount": "25.00", "currency": "USD"}) is None
