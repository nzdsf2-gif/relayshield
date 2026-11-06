"""Phase 3b tools-list proof, for review, Mac test only.

Place this file in /Users/andrewgibbs/dev/relayshield/mcp_proxy,
next to proxy.py, then run:
  python3 -m pytest test_tenant_session_ph3b_tools_list_proof.py -q

This proves Option C tools-list isolation with the real library
code, plus the proxy call sites:

1. SchemaStore isolation, real store: tenant-a stores
   check_link, tenant-b stores check_wallet, global stores
   both. get_schema for tenant-a check_wallet is {}, for
   tenant-b check_link is {}, global still returns both, and
   unkeyed get_schema is still global.
2. PolicyEngine allowed_tools, real engine with a temp
   policy.yaml, agents agent-1 allow_tools [check_link],
   deny_tools [check_wallet]: agent fallback returns only
   check_link from [check_link, check_wallet, check_email].
   Tenant policy {"allow_tools": ["check_email"]} wins over
   the agent rules and returns only check_email. Tenant policy
   {"deny_tools": ["check_link"]} wins entirely, it does not
   merge with the agent rules, so it returns check_wallet and
   check_email, with only check_link denied.
3. Source check, proxy.py: _screen_discovery takes tenant_id,
   _forward_passthrough filters tools/list through
   allowed_tools with tenant_policy, and _handle_tools_call
   passes _audit_tenant to get_schema.

What this does NOT prove: a live tools/list call end to end,
which would need a full upstream response and a Worker
resolved policy carrying allow_tools. When the Worker returns
those fields, allowed_tools reads them with no proxy rework;
until then the agent-rules fallback is the live path, and the
test above proves that path.
"""

import pathlib
import re

from mcp_proxy.policy import PolicyEngine
from mcp_proxy.schema_validator import SchemaStore


def test_schema_store_isolated_by_tenant():
    store = SchemaStore()
    store.update_from_tools_list([
        {"name": "check_link", "inputSchema": {"type": "object", "properties": {"url": {}}}},
        {"name": "check_wallet", "inputSchema": {"type": "object", "properties": {"wallet": {}}}},
    ])
    store.update_from_tools_list([
        {"name": "check_link", "inputSchema": {"type": "object", "properties": {"url": {}}}},
    ], tenant_id="tenant-a")
    store.update_from_tools_list([
        {"name": "check_wallet", "inputSchema": {"type": "object", "properties": {"wallet": {}}}},
    ], tenant_id="tenant-b")
    assert store.get_schema("check_link", tenant_id="tenant-a") != {}
    assert store.get_schema("check_wallet", tenant_id="tenant-a") == {}
    assert store.get_schema("check_wallet", tenant_id="tenant-b") != {}
    assert store.get_schema("check_link", tenant_id="tenant-b") == {}
    assert store.get_schema("check_link") != {}
    assert store.get_schema("check_wallet") != {}
    assert store.has_schema("check_link", tenant_id="tenant-a") is True
    assert store.has_schema("check_wallet", tenant_id="tenant-a") is False


def test_allowed_tools_agent_fallback(tmp_path):
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(
        "agents:\n"
        "  agent-1:\n"
        "    allow_tools: [check_link]\n"
        "    deny_tools: [check_wallet]\n",
        encoding="utf-8",
    )
    engine = PolicyEngine(policy_path=str(policy_file))
    assert engine.enabled
    names = ["check_link", "check_wallet", "check_email"]
    assert engine.allowed_tools("agent-1", names) == ["check_link"]
    assert engine.allowed_tools("agent-1", names, tenant_policy={"allow_tools": ["check_email"]}) == ["check_email"]
    # Tenant policy wins entirely when it carries either field, it
    # does not merge with the agent rules: deny check_link alone
    # leaves check_wallet allowed, because the agent deny list is
    # not consulted once a tenant policy is present.
    assert engine.allowed_tools("agent-1", names, tenant_policy={"deny_tools": ["check_link"]}) == ["check_wallet", "check_email"]


def test_proxy_tools_list_sites():
    text = pathlib.Path(__file__).with_name("proxy.py").read_text(encoding="utf-8")
    assert "def _screen_discovery(self, upstream_url: str, method: str," in text
    assert "screener: Screener, tenant_id: str = \"\"):" in text
    assert "update_from_tools_list(tools, tenant_id=tenant_id)" in text
    assert "allowed_tools(" in text
    assert "tenant_policy=_lt_policy" in text
    assert 'if method == "tools/list":' in text
    assert "get_schema(tool_name, tenant_id=_audit_tenant)" in text
