"""Phase 3b _screen_result proof, for review, Mac test only.

Place this file in /Users/andrewgibbs/dev/relayshield/mcp_proxy,
next to proxy.py, then run:
  python3 -m pytest test_tenant_session_ph3b_screen_result_proof.py -q

This proves the settle-hook tenant wiring in _screen_result:

1. The tenant resolution helper, real _audit_session_fields,
   returns tenant-a for a verified session, empty tenant for an
   unverified session, and empty tenant for an unknown session
   key. This is the exact helper the _screen_result patch calls
   with corr's session_key, so a corr of None, or an unverified
   session, correctly yields an empty tenant and global behaviour.
2. Source check, in _screen_result only: the tenant resolution
   is present, both quarantine.evaluate calls carry
   tenant_id=_sr_tenant, and both settle_outcome audit logs carry
   "tenant_id": _sr_tenant, alongside the binding_id they
   already carried.

What this does NOT prove: a live _screen_result call end to
end, which would need a full upstream response, screener,
neighbors, and reputation harness. The evaluate and audit
call sites are proven by the source check, and the tenant
isolation of evaluate itself is proven by the Ph3b proof test
(test_tenant_session_ph3b_proof.py), which uses the real
QuarantineManager.
"""

import pathlib
import re

from mcp_proxy.proxy import ProxyHandler


class FakeServer:
    def __init__(self, session_bindings):
        self.session_bindings = session_bindings


def _handler_with(session_key, session):
    handler = object.__new__(ProxyHandler)
    bindings = {}
    if session_key is not None:
        bindings[session_key] = session
    handler.server = FakeServer(bindings)
    return handler


def test_audit_session_fields_verified():
    handler = _handler_with("key-1", {
        "tenant_id": "tenant-a",
        "location_id": "loc-1",
        "binding_id": "bind_test",
        "tenant_verified": True,
    })
    tenant, binding, location = handler._audit_session_fields("key-1")
    assert tenant == "tenant-a"
    assert binding == "bind_test"
    assert location == "loc-1"


def test_audit_session_fields_unverified_does_not_leak():
    handler = _handler_with("key-1", {
        "tenant_id": "tenant-a",
        "location_id": "loc-1",
        "binding_id": "bind_test",
        "tenant_verified": False,
    })
    tenant, binding, location = handler._audit_session_fields("key-1")
    assert tenant == ""
    assert location == ""
    assert binding == "bind_test"


def test_audit_session_fields_unknown_key_empty():
    handler = _handler_with("key-1", {
        "tenant_id": "tenant-a",
        "binding_id": "bind_test",
        "tenant_verified": True,
    })
    tenant, binding, location = handler._audit_session_fields("key-missing")
    assert tenant == ""
    assert binding == ""
    assert location == ""


def test_screen_result_sites_pass_tenant():
    text = pathlib.Path(__file__).with_name("proxy.py").read_text(encoding="utf-8")
    defs = list(re.finditer(r"^    def _screen_result\(", text, flags=re.MULTILINE))
    assert len(defs) == 1
    body_start = defs[0].end()
    rest = text[body_start:]
    next_def = re.search(r"^    def ", rest, flags=re.MULTILINE)
    body = rest[:next_def.start()] if next_def else rest
    assert "_sr_tenant, _sr_binding, _sr_location = self._audit_session_fields(_sr_corr_key)" in body
    # 2 evaluate calls plus the signed verdict in _screen_result.
    assert body.count("tenant_id=_sr_tenant") == 3
    assert body.count('"tenant_id": _sr_tenant,') == 2
