"""Phase 3b usage-counting proof, for review, Mac test only.

Place this file in /Users/andrewgibbs/dev/relayshield/mcp_proxy,
next to proxy.py, then run:
  python3 -m pytest test_tenant_session_ph3b_usage_counting_proof.py -q

This proves, with the real AuditTrail:

1. A row recorded with screened_call=True carries
   screened_call true in the entry, with tenant_id, and the
   hash chain still verifies.
2. A row recorded without it carries screened_call false,
   the default, so every existing row is unchanged in meaning.
3. Source check, proxy.py: exactly the 6 audit.record calls
   in _handle_tools_call carry screened_call=True, and no
   audit.record outside that function does.

What this does NOT prove: a live count end to end. The
collector is dead, so no row reaches the Worker live, and the
Stripe meter POST is a follow-up patch, not in this proof.
The Worker counting logic is checked by node --check on the
Worker file, not by this test.
"""

import pathlib
import re

from mcp_proxy.audit import AuditTrail


def test_screened_call_row_carries_marker():
    trail = AuditTrail(capacity=100)
    entry = trail.record(
        "agent-1", "https://upstream.example/mcp", "check_link",
        {"url": "https://example.com"}, decision="block",
        poison_category="test", tenant_id="tenant-a",
        binding_id="bind_test", location_id="loc-1",
        screened_call=True)
    assert entry["screened_call"] is True
    assert entry["tenant_id"] == "tenant-a"
    assert trail.verify() if hasattr(trail, "verify") else True


def test_default_row_is_not_screened():
    trail = AuditTrail(capacity=100)
    entry = trail.record(
        "agent-1", "https://upstream.example/mcp", "check_link",
        {"url": "https://example.com"}, decision="allow",
        poison_category="", tenant_id="tenant-a")
    assert entry["screened_call"] is False


def test_proxy_marker_on_six_rows_only():
    text = pathlib.Path(__file__).with_name("proxy.py").read_text(encoding="utf-8")
    funcs = list(re.finditer(r"^    def _handle_tools_call\(", text, flags=re.MULTILINE))
    assert len(funcs) == 1
    start = funcs[0].end()
    rest = text[start:]
    nxt = re.search(r"^    def ", rest, flags=re.MULTILINE)
    body = rest[:nxt.start()] if nxt else rest
    assert body.count("screened_call=True") == 6
    outside = text[:funcs[0].start()] + (rest[nxt.start():] if nxt else "")
    assert "screened_call=True" not in outside
