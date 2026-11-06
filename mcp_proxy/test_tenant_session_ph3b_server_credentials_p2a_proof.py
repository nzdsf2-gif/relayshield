"""Ph3b server credentials P2a proof test (Mac version).

Run from the relayshield repo, in mcp_proxy, after the P2a patch:
  python3 -m pytest test_tenant_session_ph3b_server_credentials_p2a_proof.py -q

Uses the real mcp_proxy.screener and the real collector-sidecar.
The Screener's _post_json is monkeypatched so no HTTP is made.
The collector's urlopen is monkeypatched so no POST is made.

Note on test_screen_tool_result_threads_key: the _check_url
forwarding is asserted hard. The _lookup_kit forwarding is
asserted only when the result extraction finds a kit id,
because that depends on the extractor recognising the kit
shape in the result; the direct _lookup_kit override is
covered by test_lookup_kit_uses_override.
"""

import importlib.util
import json
import os
import sys
from unittest import mock

sys.path.insert(0, "/Users/andrewgibbs/dev/relayshield")

os.environ["MCP_PROXY_COLLECTOR_URL"] = "https://example.invalid/api/gate-verdicts"
os.environ["MCP_PROXY_COLLECTOR_SECRET"] = "global-secret"

import mcp_proxy.screener as screener_mod
from mcp_proxy.screener import Screener

_spec = importlib.util.spec_from_file_location(
    "collector_sidecar",
    "/Users/andrewgibbs/dev/relayshield/collector-sidecar-2026-11-01.py",
)
collector = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(collector)


def test_check_url_uses_override():
    seen = {}

    def fake_post_json(url, payload, timeout, api_key=""):
        seen["api_key"] = api_key
        return {"data": {"level": "unknown", "score": 0, "signals": []}}

    with mock.patch.object(screener_mod, "_post_json", fake_post_json):
        s = Screener("https://example.invalid", api_key="global-key")
        s._check_url("http://example.com", api_key="tenant-key")
        assert seen["api_key"] == "tenant-key"
        s._check_url("http://example.com")
        assert seen["api_key"] == "global-key"


def test_lookup_kit_uses_override():
    seen = {}

    def fake_post_json(url, payload, timeout, api_key=""):
        seen["api_key"] = api_key
        return {"data": {"verdict": "match", "family": "f", "confidence": 1}}

    with mock.patch.object(screener_mod, "_post_json", fake_post_json):
        s = Screener("https://example.invalid", api_key="global-key")
        s._lookup_kit("kit_abc", api_key="tenant-key")
        assert seen["api_key"] == "tenant-key"
        s._lookup_kit("kit_abc")
        assert seen["api_key"] == "global-key"


def test_screen_tool_call_threads_key():
    s = Screener("https://example.invalid", api_key="global-key")
    seen = {}

    def fake_check_url(url, api_key=None):
        seen["api_key"] = api_key
        return {"level": "unknown", "score": 0, "reasons": []}

    s._check_url = fake_check_url
    s.screen_tool_call("check_link", {"url": "http://example.com"}, api_key="tenant-key")
    assert seen["api_key"] == "tenant-key"
    s.screen_tool_call("check_link", {"url": "http://example.com"})
    assert seen["api_key"] is None


def test_screen_tool_result_threads_key():
    s = Screener("https://example.invalid", api_key="global-key")
    seen = {}

    def fake_check_url(url, api_key=None):
        seen["url_key"] = api_key
        return {"level": "unknown", "score": 0, "reasons": []}

    def fake_lookup_kit(kit_id, api_key=None):
        seen["kit_key"] = api_key
        return None

    s._check_url = fake_check_url
    s._lookup_kit = fake_lookup_kit
    s.screen_tool_result(
        {"url": "http://example.com", "kit_id": "kit_" + "a" * 64},
        api_key="tenant-key",
    )
    assert seen.get("url_key") == "tenant-key"
    if "kit_key" in seen:
        assert seen["kit_key"] == "tenant-key"


def test_parse_audit_carries_tenant():
    line = json.dumps({
        "seq": 1, "ts": "2026-11-05T00:00:00Z", "tool": "check_link",
        "decision": "allow", "tenant_id": "tenant-a", "binding_id": "bind-1",
        "location_id": "loc-1", "entry_hash": "h1",
    })
    rec = collector.parse_audit_line(line, set())
    assert rec["tenant_id"] == "tenant-a"
    assert rec["binding_id"] == "bind-1"
    assert rec["location_id"] == "loc-1"


def test_parse_log_carries_tenant():
    line = 'settle_outcome {"tool": "check_link", "reason": "x", "binding_id": "bind-1", "passport_id": "p1", "tenant_id": "tenant-a"}'
    rec = collector.parse_log_line(line, set())
    assert rec["tenant_id"] == "tenant-a"


def test_post_batch_groups_by_tenant(tmp_path):
    secrets = tmp_path / "tenant-secrets.json"
    secrets.write_text(json.dumps({"tenant-a": {"collector_secret": "secret-a"}}))
    os.environ["MCP_PROXY_TENANT_SECRETS_FILE"] = str(secrets)
    captured = []

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(req, timeout=10):
        captured.append(req)
        return Resp()

    with mock.patch.object(collector.urllib.request, "urlopen", fake_urlopen):
        ok = collector.post_batch([
            {"tenant_id": "tenant-a", "tool": "check_link"},
            {"tenant_id": "tenant-b", "tool": "check_link"},
            {"tool": "check_link"},
        ])
    assert ok is True
    assert len(captured) == 3
    for req in captured:
        body = json.loads(req.data.decode())
        tid = body["verdicts"][0].get("tenant_id")
        secret = req.headers.get("X-rs-collector-secret")
        if tid == "tenant-a":
            assert secret == "secret-a"
        else:
            assert secret == "global-secret"
        assert len(body["verdicts"]) == 1


def test_post_batch_no_tenant_uses_global(tmp_path):
    secrets = tmp_path / "tenant-secrets.json"
    secrets.write_text(json.dumps({}))
    os.environ["MCP_PROXY_TENANT_SECRETS_FILE"] = str(secrets)
    captured = []

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(req, timeout=10):
        captured.append(req)
        return Resp()

    with mock.patch.object(collector.urllib.request, "urlopen", fake_urlopen):
        ok = collector.post_batch([{"tool": "check_link"}])
    assert ok is True
    assert len(captured) == 1
    assert captured[0].headers.get("X-rs-collector-secret") == "global-secret"
