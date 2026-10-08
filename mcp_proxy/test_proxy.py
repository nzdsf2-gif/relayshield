"""Tests for the MCP proxy firewall.

Run: python3 -m unittest mcp_proxy.test_proxy -v
"""

import json
import threading
import time
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

from mcp_proxy.config import ProxyConfig
from mcp_proxy.proxy import ProxyServer
from mcp_proxy.screener import Screener, extract_indicators


# ---------------------------------------------------------------------------
# Indicator extraction
# ---------------------------------------------------------------------------

class TestExtractIndicators(unittest.TestCase):
    def test_extracts_url(self):
        out = extract_indicators({"target": "https://evil.example/bad?x=1"})
        self.assertIn("https://evil.example/bad?x=1", out["urls"])

    def test_extracts_nested(self):
        out = extract_indicators({"a": {"b": ["go to http://x.test/y"]}})
        self.assertTrue(any("x.test" in u for u in out["urls"]))

    def test_extracts_ip(self):
        out = extract_indicators({"host": "connect to 1.2.3.4 now"})
        self.assertIn("1.2.3.4", out["ips"])

    def test_empty(self):
        out = extract_indicators({"n": 42, "s": "hello"})
        self.assertEqual(out["urls"], [])
        self.assertEqual(out["ips"], [])

    def test_cycle_safe(self):
        d = {}
        d["self"] = d
        out = extract_indicators(d)  # must not hang
        self.assertEqual(out["urls"], [])


# ---------------------------------------------------------------------------
# Screener
# ---------------------------------------------------------------------------

class TestScreener(unittest.TestCase):
    def _screener(self, check_result):
        s = Screener(api_base="https://example.invalid",
                     block_levels={"high", "medium"})
        s._check_url = mock.Mock(return_value=check_result)
        return s

    def test_no_indicators_allows(self):
        s = self._screener({"level": "high", "score": 90, "reasons": ["x"]})
        v = s.screen_tool_call("read_file", {"path": "/tmp/a.txt"})
        self.assertEqual(v["verdict"], "allow")

    def test_high_blocks(self):
        s = self._screener({"level": "high", "score": 90, "reasons": ["phishing"]})
        v = s.screen_tool_call("fetch", {"url": "https://evil.example/"})
        self.assertEqual(v["verdict"], "block")
        self.assertEqual(v["level"], "high")

    def test_medium_blocks_when_configured(self):
        s = self._screener({"level": "medium", "score": 55,
                            "reasons": ["suspicious"]})
        v = s.screen_tool_call("fetch", {"url": "https://grey.example/"})
        self.assertEqual(v["verdict"], "block")

    def test_unknown_allows(self):
        s = self._screener({"level": "unknown", "score": 15,
                            "reasons": ["no data"]})
        v = s.screen_tool_call("fetch", {"url": "https://clean.example/"})
        self.assertEqual(v["verdict"], "allow")

    def test_screening_failure_fails_open(self):
        s = Screener(api_base="https://example.invalid")
        s._check_url = mock.Mock(side_effect=RuntimeError("down"))
        v = s.screen_tool_call("fetch", {"url": "https://x.example/"})
        self.assertEqual(v["verdict"], "allow")
        self.assertIn("unavailable", v["reasons"][0])


# ---------------------------------------------------------------------------
# Proxy passthrough (with a fake upstream)
# ---------------------------------------------------------------------------

class _FakeUpstream(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        req_id = body.get("id")
        method = body.get("method", "")
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05",
                      "serverInfo": {"name": "fake", "version": "1"}}
        elif method == "tools/list":
            result = {"tools": [{"name": "fetch",
                                 "description": "fetch a url"}]}
        elif method == "tools/call":
            result = {"content": [{"type": "text", "text": "fetched ok"}]}
        else:
            result = {}
        resp = {"jsonrpc": "2.0", "id": req_id, "result": result}
        raw = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _post(url, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


class _ProxyTestBase(unittest.TestCase):
    """Spins up a fake upstream and a real ProxyServer with mocked screener."""

    @classmethod
    def setUpClass(cls):
        cls.upstream = HTTPServer(("127.0.0.1", 0), _FakeUpstream)
        t = threading.Thread(target=cls.upstream.serve_forever, daemon=True)
        t.start()
        cls.upstream_url = (
            f"http://127.0.0.1:{cls.upstream.server_address[1]}")

    @classmethod
    def tearDownClass(cls):
        cls.upstream.shutdown()

    def _start_proxy(self, screening_enabled=True, verdict=None):
        cfg = ProxyConfig()
        cfg.upstream_url = self.upstream_url
        cfg.listen_port = 0  # ephemeral
        cfg.screening_enabled = screening_enabled
        # Build the server without binding via __init__ side effects:
        # ProxyServer.__init__ binds the port, so use port 0 then read back.
        server = ProxyServer(cfg)
        if verdict is not None:
            server.screener.screen_tool_call = mock.Mock(return_value=verdict)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        url = f"http://127.0.0.1:{server.server_address[1]}"
        self.addCleanup(server.shutdown)
        return url

    def _allow_verdict(self, tool="fetch"):
        return {"verdict": "allow", "level": "unknown", "score": 0,
                "reasons": ["test clean"], "tool_name": tool}

    def _block_verdict(self, tool="fetch"):
        return {"verdict": "block", "level": "high", "score": 95,
                "reasons": ["phishing kit"], "tool_name": tool}


class TestProxyPassthrough(_ProxyTestBase):
    def test_initialize_passthrough(self):
        url = self._start_proxy(screening_enabled=False)
        resp = _post(url, {"jsonrpc": "2.0", "id": 1,
                           "method": "initialize", "params": {}})
        self.assertEqual(resp["id"], 1)
        self.assertEqual(resp["result"]["serverInfo"]["name"], "fake")

    def test_tools_list_passthrough(self):
        url = self._start_proxy(screening_enabled=False)
        resp = _post(url, {"jsonrpc": "2.0", "id": 2,
                           "method": "tools/list", "params": {}})
        self.assertEqual(resp["result"]["tools"][0]["name"], "fetch")

    def test_tools_call_blocked(self):
        url = self._start_proxy(verdict=self._block_verdict())
        resp = _post(url, {"jsonrpc": "2.0", "id": 3,
                           "method": "tools/call",
                           "params": {"name": "fetch",
                                      "arguments": {"url": "https://evil.example/"}}})
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32001)
        self.assertIn("Blocked by RelayShield", resp["error"]["message"])
        self.assertEqual(resp["error"]["data"]["level"], "high")

    def test_tools_call_allowed_forwards(self):
        url = self._start_proxy(verdict=self._allow_verdict())
        resp = _post(url, {"jsonrpc": "2.0", "id": 4,
                           "method": "tools/call",
                           "params": {"name": "fetch",
                                      "arguments": {"url": "https://clean.example/"}}})
        self.assertIn("result", resp)
        self.assertEqual(resp["result"]["content"][0]["text"], "fetched ok")

    def test_screening_disabled_is_passthrough(self):
        url = self._start_proxy(screening_enabled=False)
        resp = _post(url, {"jsonrpc": "2.0", "id": 5,
                           "method": "tools/call",
                           "params": {"name": "fetch",
                                      "arguments": {"url": "https://evil.example/"}}})
        # Screening off: forwarded to upstream, not blocked.
        self.assertIn("result", resp)

    def test_proxy_overhead_under_50ms(self):
        """Proxy-side overhead per call stays under 50ms (localhost upstream)."""
        url = self._start_proxy(screening_enabled=False)
        payload = {"jsonrpc": "2.0", "id": 9, "method": "tools/list",
                   "params": {}}
        _post(url, payload)  # warm up
        start = time.monotonic()
        n = 5
        for _ in range(n):
            _post(url, payload)
        elapsed_ms = (time.monotonic() - start) * 1000 / n
        self.assertLess(elapsed_ms, 50,
                        f"proxy overhead {elapsed_ms:.1f}ms exceeds 50ms")


class TestConfig(unittest.TestCase):
    def test_defaults(self):
        import os
        os.environ.pop("MCP_PROXY_UPSTREAM", None)
        cfg = ProxyConfig()
        self.assertEqual(cfg.listen_port, 8090)
        self.assertTrue(cfg.screening_enabled)

    def test_missing_upstream_flagged(self):
        import os
        os.environ.pop("MCP_PROXY_UPSTREAM", None)
        cfg = ProxyConfig()
        problems = cfg.validate()
        self.assertTrue(any("MCP_PROXY_UPSTREAM" in p for p in problems))

    def test_block_levels_parsed(self):
        import os
        os.environ["MCP_PROXY_BLOCK_LEVELS"] = "high"
        try:
            cfg = ProxyConfig()
            self.assertEqual(cfg.block_level_set, {"high"})
        finally:
            del os.environ["MCP_PROXY_BLOCK_LEVELS"]


if __name__ == "__main__":
    unittest.main()
