"""Ph3b server credentials P2b proof test (Mac version).

Run from the relayshield repo, in mcp_proxy, after the P2b patch:
  python3 -m pytest test_tenant_session_ph3b_server_credentials_p2b_proof.py -q

The two P2b call sites live inside _handle_tools_call and
_screen_result, which are not directly callable in a unit test
without a full proxy setup. This test therefore verifies, from
the source, that both call sites pass the tenant's screener_key,
and that _tenant_key (the P1 helper the call sites use) returns
the stored key for a tenant and None for the no-tenant path.
The P1 proof test covers the sync path; this covers the lookup
the call sites depend on.
"""

import pathlib
import sys

sys.path.insert(0, "/Users/andrewgibbs/dev/relayshield")

from mcp_proxy.proxy import ProxyHandler
from mcp_proxy.tenant_secrets import TenantSecrets

PROXY = pathlib.Path("/Users/andrewgibbs/dev/relayshield/mcp_proxy/proxy.py")


class FakeServer:
    def __init__(self, tenant_secrets):
        self.tenant_secrets = tenant_secrets


def test_call_sites_pass_tenant_key():
    lines = PROXY.read_text().splitlines()
    tool_call = [l for l in lines if "screen_tool_call(tool_name, arguments" in l]
    tool_result = [l for l in lines if "screen_tool_result(upstream_resp" in l]
    assert len(tool_call) == 1, tool_call
    assert len(tool_result) == 1, tool_result
    assert "api_key=" in tool_call[0], tool_call[0]
    assert "_tenant_key(_audit_tenant" in tool_call[0], tool_call[0]
    assert "api_key=" in tool_result[0], tool_result[0]
    assert "_tenant_key(_sr_tenant" in tool_result[0], tool_result[0]


def test_tenant_key_lookup_for_call_sites(tmp_path):
    import json

    secrets_file = tmp_path / "tenant-secrets.json"
    secrets_file.write_text(json.dumps({"tenant-a": {"screener_key": "sk-a"}}))
    store = TenantSecrets(path=str(secrets_file))
    handler = object.__new__(ProxyHandler)
    handler.server = FakeServer(store)
    assert handler._tenant_key("tenant-a", "screener_key") == "sk-a"
    assert handler._tenant_key("", "screener_key") is None
    assert handler._tenant_key("tenant-b", "screener_key") is None
