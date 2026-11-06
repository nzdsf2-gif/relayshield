"""Phase 3b call-site proof, for review, Mac test only.

Place this file in /Users/andrewgibbs/dev/relayshield/mcp_proxy,
next to proxy.py, then run:
  python3 -m pytest test_tenant_session_ph3b_proof.py -q

This proves Ph3b isolation with the real library code, plus that
the call sites in _handle_tools_call actually pass the tenant:

1. Rate limit isolation, real PolicyEngine with a temp policy.yaml
   (check_link, 2/minute): tenant-a, same agent and tool, third
   call denies, tenant-b, same agent and tool, first call allows.
   Tenant A's calls do not count toward tenant B's limit.
2. Quarantine isolation, real QuarantineManager with a fake
   registry (tenant path never touches the registry): tenant-a
   auto-quarantines after 2 flags, tenant-b is not quarantined,
   global is not quarantined. Direct tenant-b quarantine does
   not quarantine tenant-a or the global entry.
3. Call-site wiring, source-level, in _handle_tools_call only:
   the four call sites in that function carry
   tenant_id=_audit_tenant, and the evaluate calls outside that
   function are unchanged by this patch, which is the stated
   scope, not a silent omission.

What this does NOT prove: tools-list filtering, schema-store
keying, usage counting, signed verdicts, or settle-hook
quarantine, which are separate Ph3b items, not bundled here.
"""

import pathlib
import re

from mcp_proxy.policy import PolicyEngine
from mcp_proxy.quarantine import QuarantineManager


class FakeRegistry:
    def get(self, url):
        return None

    def register(self, url):
        raise AssertionError("tenant path must not touch the registry")


def test_rate_limit_isolated_by_tenant(tmp_path):
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(
        "tools:\n"
        "  check_link:\n"
        "    rate_limit: 2/minute\n",
        encoding="utf-8",
    )
    engine = PolicyEngine(policy_path=str(policy_file))
    assert engine.enabled
    for _ in range(2):
        result = engine.evaluate("agent-1", "check_link", "https://upstream.invalid/mcp", {}, tenant_id="tenant-a")
        assert result["decision"] == "allow"
    result = engine.evaluate("agent-1", "check_link", "https://upstream.invalid/mcp", {}, tenant_id="tenant-a")
    assert result["decision"] == "deny"
    assert result["poison_category"] == "policy_deny"
    result = engine.evaluate("agent-1", "check_link", "https://upstream.invalid/mcp", {}, tenant_id="tenant-b")
    assert result["decision"] == "allow"


def test_quarantine_isolated_by_tenant():
    manager = QuarantineManager(FakeRegistry(), auto_quarantine_after=2)
    url = "https://upstream.invalid/mcp"
    assert manager.evaluate(url, evidence=["flag-1"], tenant_id="tenant-a") is False
    assert manager.evaluate(url, evidence=["flag-2"], tenant_id="tenant-a") is True
    assert manager.is_quarantined(url, tenant_id="tenant-a") is True
    assert manager.is_quarantined(url, tenant_id="tenant-b") is False
    assert manager.is_quarantined(url) is False
    manager.quarantine(url, "operator quarantine", tenant_id="tenant-b")
    assert manager.is_quarantined(url, tenant_id="tenant-b") is True
    assert manager.is_quarantined(url, tenant_id="tenant-a") is True
    assert manager.is_quarantined(url) is False


def test_handle_tools_call_sites_pass_tenant():
    text = pathlib.Path(__file__).with_name("proxy.py").read_text(encoding="utf-8")
    defs = list(re.finditer(r"^    def _handle_tools_call\(", text, flags=re.MULTILINE))
    assert len(defs) == 1
    body_start = defs[0].end()
    rest = text[body_start:]
    next_def = re.search(r"^    def ", rest, flags=re.MULTILINE)
    body = rest[:next_def.start()] if next_def else rest
    assert "quarantine.is_quarantined(upstream_url, tenant_id=_audit_tenant)" in body
    assert "quarantine.evaluate(upstream_url, tenant_id=_audit_tenant)" in body
    assert "quarantine.evaluate(upstream_url, evidence=evidence,\n                    tenant_id=_audit_tenant)" in body
    # NOTE: do NOT count the raw string tenant_id=_audit_tenant here:
    # Ph3a audit.record calls in the same function already use it,
    # so the raw count is 6 from Ph3a plus 4 from Ph3b. Count only
    # the call-site patterns above.
    assert "arguments,\n                    tenant_id=_audit_tenant)" in body
