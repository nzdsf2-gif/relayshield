"""Phase 3a call-site helper tests, for review, Mac test only.

Place this file in /Users/andrewgibbs/dev/relayshield/mcp_proxy,
next to proxy.py, then run:
  python3 -m pytest test_tenant_session_callsite.py -q

These tests do NOT start a proxy, do NOT call the Gateway, and
do NOT require a passport. They test _audit_session_fields
directly, with a fake server, using object.__new__(ProxyHandler),
in the same pattern as test_tenant_session_gate.py.

Scope: helper only. Full audit.record stamping in
_handle_tools_call is step 2 of the call-site patch, and its
tests land with that patch, once the exact audit call sites
from the step 1 inventory are known. This file must pass
after step 1 alone, with no audit entry changed.
"""

from mcp_proxy.proxy import ProxyHandler


class FakeServer:
    def __init__(self):
        self.session_bindings = {}


def make_handler(session=None):
    handler = object.__new__(ProxyHandler)
    handler.server = FakeServer()
    if session is not None:
        handler.server.session_bindings["test-session"] = session
    return handler


def test_verified_session_stamps_all_three():
    handler = make_handler({
        "tenant_id": "tenant-a",
        "location_id": "loc-1",
        "binding_id": "bind_test",
        "tenant_verified": True,
    })
    assert handler._audit_session_fields("test-session") == ("tenant-a", "bind_test", "loc-1")


def test_unverified_tenant_not_stamped_but_binding_is():
    handler = make_handler({
        "tenant_id": "tenant-a",
        "location_id": "loc-1",
        "binding_id": "bind_test",
        "tenant_verified": False,
    })
    assert handler._audit_session_fields("test-session") == ("", "bind_test", "")


def test_no_session_stamps_empty_not_error():
    handler = make_handler(session=None)
    assert handler._audit_session_fields("test-session") == ("", "", "")


def test_no_binding_stamps_empty_binding():
    handler = make_handler({
        "tenant_id": "tenant-a",
        "location_id": None,
        "binding_id": None,
        "tenant_verified": True,
    })
    assert handler._audit_session_fields("test-session") == ("tenant-a", "", "")
