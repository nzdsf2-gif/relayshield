"""Unit tests for the Phase 4 policy engine."""

import os
import tempfile
import unittest

from .policy import PolicyEngine, RateLimiter, parse_rate_limit


POLICY_YAML = """
agents:
  "agent-123":
    allow_tools: ["read_file", "search", "expensive_query"]
    deny_tools: ["exec_shell"]
  "agent-*":
    deny_tools: ["rm_rf"]
servers:
  "http://internal:9000":
    trust: high
    strictness: relaxed
tools:
  "exec_shell":
    require_approval: true
  "expensive_query":
    rate_limit: 2/minute
"""


def _write_policy(content=POLICY_YAML):
    fd, path = tempfile.mkstemp(suffix=".yaml")
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path


class TestParseRateLimit(unittest.TestCase):
    def test_minute(self):
        self.assertEqual(parse_rate_limit("10/minute"), (10, 60.0))

    def test_hour(self):
        self.assertEqual(parse_rate_limit("100/hour"), (100, 3600.0))

    def test_bad(self):
        self.assertEqual(parse_rate_limit("nope"), (None, None))
        self.assertEqual(parse_rate_limit("10/fortnight"), (None, None))


class TestRateLimiter(unittest.TestCase):
    def test_within_limit(self):
        rl = RateLimiter()
        self.assertTrue(rl.check("k", 3, 60.0, now=1000.0))
        self.assertTrue(rl.check("k", 3, 60.0, now=1001.0))
        self.assertTrue(rl.check("k", 3, 60.0, now=1002.0))

    def test_exceeded(self):
        rl = RateLimiter()
        for i in range(3):
            rl.check("k", 3, 60.0, now=1000.0 + i)
        self.assertFalse(rl.check("k", 3, 60.0, now=1003.0))

    def test_window_slides(self):
        rl = RateLimiter()
        rl.check("k", 1, 10.0, now=1000.0)
        self.assertFalse(rl.check("k", 1, 10.0, now=1005.0))
        self.assertTrue(rl.check("k", 1, 10.0, now=1016.0))


class TestPolicyEngine(unittest.TestCase):
    def setUp(self):
        self.path = _write_policy()
        self.engine = PolicyEngine(self.path)

    def tearDown(self):
        os.unlink(self.path)

    def test_disabled_without_path(self):
        e = PolicyEngine("")
        r = e.evaluate("anyone", "any_tool", "http://x")
        self.assertEqual(r["decision"], "allow")

    def test_deny_tool(self):
        # Agent-level deny wins over tool-level approval requirement.
        r = self.engine.evaluate("agent-123", "exec_shell",
                                 "http://internal:9000")
        self.assertEqual(r["decision"], "deny")
        self.assertEqual(r["poison_category"], "policy_deny")

    def test_approval_required(self):
        # A tool with require_approval, for an agent without a deny.
        r = self.engine.evaluate("agent-999", "exec_shell",
                                 "http://internal:9000")
        self.assertEqual(r["decision"], "approval_required")

    def test_allow_list_exclusive(self):
        r = self.engine.evaluate("agent-123", "read_file",
                                 "http://internal:9000")
        self.assertEqual(r["decision"], "allow")
        r = self.engine.evaluate("agent-123", "write_file",
                                 "http://internal:9000")
        self.assertEqual(r["decision"], "deny")
        self.assertEqual(r["poison_category"], "policy_deny")

    def test_glob_agent_deny(self):
        r = self.engine.evaluate("agent-999", "rm_rf", "http://x")
        self.assertEqual(r["decision"], "deny")

    def test_rate_limit(self):
        e = self.engine
        for _ in range(2):
            r = e.evaluate("agent-123", "expensive_query", "http://x")
            self.assertEqual(r["decision"], "allow")
        r = e.evaluate("agent-123", "expensive_query", "http://x")
        self.assertEqual(r["decision"], "deny")
        self.assertIn("rate limit", r["reasons"][0])

    def test_server_trust_hint(self):
        r = self.engine.evaluate("agent-123", "read_file",
                                 "http://internal:9000")
        self.assertEqual(r["server_trust"], "high")
        self.assertEqual(r["server_strictness"], "relaxed")

    def test_unknown_server_defaults(self):
        r = self.engine.evaluate("agent-123", "read_file",
                                 "http://unknown:1234")
        self.assertEqual(r["server_trust"], "medium")

    def test_reload(self):
        self.assertTrue(self.engine.reload())
        self.assertTrue(self.engine.loaded)

    def test_summary(self):
        s = self.engine.summary()
        self.assertTrue(s["enabled"])
        self.assertEqual(s["agents"], 2)
        self.assertEqual(s["tools"], 2)


if __name__ == "__main__":
    unittest.main()
