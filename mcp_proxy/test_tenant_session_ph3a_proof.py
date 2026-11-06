"""Phase 3a completion proof, for review, Mac test only.

Place this file in /Users/andrewgibbs/dev/relayshield/mcp_proxy,
next to proxy.py, then run:
  python3 -m pytest test_tenant_session_ph3a_proof.py -q

This is the tenant-verified proof for Ph3a, and it closes Ph3a
before Ph3b starts. It does NOT need a Gateway, a passport, a
live tenant, or a Worker fetch, because it tests the exact link
Ph3a owns, in the real code path:

  verified session in server.session_bindings
    -> _handle_tools_call (real, with the moved corr/session_key
       block before the first audit call)
    -> _audit_session_fields (real)
    -> real AuditTrail.record, with tenant_id, binding_id,
       location_id stamped on the entry

What it proves, each with a real AuditTrail entry:
1. Verified tenant session: the quarantined-server audit entry
   carries tenant_id="tenant-a", binding_id="bind_test",
   location_id="loc-1". This is the tenant-verified row.
2. Unverified tenant session: same call, tenant_id and
   location_id are empty, binding_id is still stamped. A
   binding-only tenant_id does NOT leak into audit.
3. No session: all three fields empty, no error. This matches
   the live row proven on 2026-11-05 morning, seq 1, where the
   empty fields were correct for a call with no session.

The session_key is not guessed: it is computed with the proxy's
own resolve_correlation_identity(req, agent_id, upstream_url),
the same function _handle_tools_call uses, and the session is
stored under that key, exactly as _handle_initialize stores it.

What this test does NOT prove, and says so plainly: how a
session gets tenant_verified=True in production. That is Ph1
session creation, where tenant_verified is True only when the
passport_doc returned by the Gateway passport check carries a
tenant_id. The one live probe for that input is a separate
step, after this test: call the Gateway passport check with a
real passport and read whether its passport_doc carries
tenant_id. If it does not, the issuer must add tenant_id to
passport claims at issue time. That is a defined issuer task,
not a reason to hold Ph3b, because every step downstream of
passport_doc is proven here.
"""

from mcp_proxy.proxy import ProxyHandler, resolve_correlation_identity
from mcp_proxy.audit import AuditTrail


UPSTREAM = "https://example-upstream.invalid/mcp"


class FakeQuarantine:
    # Ph3b call-site update 2026-11-05: _handle_tools_call now passes
    # tenant_id to is_quarantined and evaluate, matching the real
    # QuarantineManager signature. The fake must accept the kwarg,
    # or the handler raises TypeError before it reaches the audit
    # call this test is proving. The fake still returns its fixed
    # quarantined value regardless of tenant, which is exactly what
    # the Ph3a audit-stamping proof needs.
    def __init__(self, quarantined=True):
        self._quarantined = quarantined

    def is_quarantined(self, url, tenant_id=""):
        return self._quarantined

    def evaluate(self, url, evidence=None, tenant_id=""):
        return False


class FakePolicy:
    enabled = False

    def evaluate(self, agent_id, tool_name, server_url, arguments, tenant_id=""):
        return {"decision": "allow", "reasons": [], "poison_category": "clean"}


class FakeCfg:
    upstream_url = UPSTREAM
    intent_binding_mode = "off"


class FakeServer:
    def __init__(self, audit, session=None, session_key=None):
        self.audit = audit
        self.session_bindings = {}
        if session is not None and session_key is not None:
            self.session_bindings[session_key] = session
        self.quarantine = FakeQuarantine(quarantined=True)
        self.policy = FakePolicy()
        self.neighbors = []
        self.behavior = object()
        self.reputation = object()


def make_handler(session=None):
    # Compute the session_key exactly as the proxy does, so the
    # session lands where _handle_tools_call will look for it.
    req = {"params": {"name": "check_link", "arguments": {"url": "https://example.com"}}}
    agent_id = "127.0.0.1"
    corr = resolve_correlation_identity(req, agent_id, UPSTREAM)
    session_key = corr["session_key"]
    handler = object.__new__(ProxyHandler)
    handler.server = FakeServer(AuditTrail(persist_path=""), session=session, session_key=session_key)
    handler.client_address = ("127.0.0.1", 12345)
    return handler, req, session_key


def call_tools(handler, req):
    return handler._handle_tools_call(req, 1, FakeCfg(), None)


def test_verified_session_audit_row_carries_tenant():
    handler, req, _ = make_handler({
        "tenant_id": "tenant-a",
        "location_id": "loc-1",
        "binding_id": "bind_test",
        "tenant_verified": True,
    })
    result = call_tools(handler, req)
    assert result is not None, "quarantined upstream must block, not pass through"
    entries = handler.server.audit._entries
    assert len(entries) == 1
    entry = entries[0]
    assert entry["tool"] == "check_link"
    assert entry["decision"] == "block"
    assert entry["poison_category"] == "quarantined_server"
    assert entry["tenant_id"] == "tenant-a"
    assert entry["binding_id"] == "bind_test"
    assert entry["location_id"] == "loc-1"


def test_unverified_tenant_does_not_leak_into_audit():
    handler, req, _ = make_handler({
        "tenant_id": "tenant-a",
        "location_id": "loc-1",
        "binding_id": "bind_test",
        "tenant_verified": False,
    })
    result = call_tools(handler, req)
    assert result is not None
    entry = handler.server.audit._entries[0]
    assert entry["tenant_id"] == ""
    assert entry["location_id"] == ""
    assert entry["binding_id"] == "bind_test"


def test_no_session_stamps_empty_not_error():
    handler, req, _ = make_handler(session=None)
    result = call_tools(handler, req)
    assert result is not None
    entry = handler.server.audit._entries[0]
    assert entry["tenant_id"] == ""
    assert entry["binding_id"] == ""
    assert entry["location_id"] == ""
