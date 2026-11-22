"""Unit tests for the shell-injection argument screen (CVE-2026-129995).

Covers the scope (shell-injection-screen-scope-2026-11-21.md):
  Part 1: each metacharacter in the set flags a string argument; clean
    arguments pass; URL values containing ';' do not flag; nested
    arguments are walked and non-string values skipped; bare '$', '*',
    '?', '<', and bare '&' do not flag.
  Part 2: list_backups and ssh_backup_list classify as state-changing;
    list_commands stays read-only; 'backup' and 'schedule' are state verbs.
  Part 3: tools/list exposing a shell-token tool name flags with
    category shell_injection; a clean tools/list stays clean.
  Policy wiring: a flagged call under Enforce plus Policy 2 blocks
    without an attestation; under Audit it proceeds.

Place this file in mcp_proxy/ next to proxy.py, then run:
  python3 -m pytest test_shell_injection.py -q
These tests do NOT start a proxy, do NOT call the Gateway, and do NOT
require a passport. The screener tests use a Screener pointed at an
invalid API base; the shell-flag tests return before any TI fan-out,
and the clean/URL tests use arguments with no URLs (or assert only
that no shell flag fires), so no TI call is required.
"""

import time
import unittest
from datetime import datetime, timezone, timedelta

from mcp_proxy.screener import Screener, POISON_SHELL_INJECTION
from mcp_proxy.discovery import screen_discovery
from mcp_proxy.proxy import (
    ProxyHandler,
    _STATE_VERBS,
    _tool_is_read_only,
)


def _screener():
    return Screener(api_base="https://api.example.invalid")


def _tools_list(names):
    tools = [{"name": n, "description": "does a thing"} for n in names]
    return {"jsonrpc": "2.0", "id": 1,
            "result": {"protocolVersion": "2024-11-05", "tools": tools}}


class Part1Metacharacters(unittest.TestCase):
    def test_each_metacharacter_flags(self):
        cases = [
            ("semicolon", {"comment": "a;b"}),
            ("double ampersand", {"comment": "a && b"}),
            ("double pipe", {"comment": "a || b"}),
            ("single pipe", {"comment": "a | b"}),
            ("dollar paren", {"comment": "$(whoami)"}),
            ("backtick", {"comment": "`whoami`"}),
            ("newline", {"comment": "a\nb"}),
            ("carriage return", {"comment": "a\rb"}),
            ("greater than", {"comment": "a > b"}),
        ]
        for label, args in cases:
            with self.subTest(label=label):
                v = _screener().screen_tool_call("ssh_backup_create", args)
                self.assertEqual(v["verdict"], "flag", label)
                self.assertEqual(v["level"], "high", label)
                self.assertEqual(v["score"], 90, label)
                self.assertEqual(v["poison_category"],
                                 POISON_SHELL_INJECTION, label)
                self.assertIn("SHELL_METACHARACTER",
                              [c["code"] for c in v["cause_codes"]], label)
                # Reasons name the path and class, never the raw value.
                self.assertTrue(any("comment" in r for r in v["reasons"]), label)
                self.assertTrue(all("whoami" not in r and "rm" not in r
                                    for r in v["reasons"]), label)

    def test_clean_arguments_pass(self):
        v = _screener().screen_tool_call(
            "ssh_backup_create",
            {"database": "mydb", "comment": "nightly backup"})
        self.assertNotEqual(v.get("poison_category"), POISON_SHELL_INJECTION)

    def test_url_value_with_semicolon_does_not_flag(self):
        v = _screener().screen_tool_call(
            "check_link",
            {"url": "https://example.com/path?a=1;b=2"})
        self.assertNotEqual(v.get("poison_category"), POISON_SHELL_INJECTION)

    def test_nested_arguments_walked_non_strings_skipped(self):
        v = _screener().screen_tool_call("ssh_backup_create", {
            "outer": {"inner": "x;y"},
            "items": ["ok", "p|q"],
            "count": 42,
            "enabled": True,
            "nothing": None,
        })
        self.assertEqual(v["verdict"], "flag")
        self.assertEqual(v["poison_category"], POISON_SHELL_INJECTION)
        self.assertTrue(any("outer.inner" in r for r in v["reasons"]))

    def test_bare_exclusions_do_not_flag(self):
        v = _screener().screen_tool_call("lookup", {
            "price": "$100",
            "pattern": "file*.txt",
            "note": "a < b",
            "join": "a & b",
        })
        self.assertNotEqual(v.get("poison_category"), POISON_SHELL_INJECTION)

    def test_flag_names_argument_path(self):
        v = _screener().screen_tool_call(
            "ssh_backup_create", {"database": "mydb; drop"})
        self.assertTrue(any("database" in r for r in v["reasons"]))
        self.assertTrue(any("command separator" in r for r in v["reasons"]))


class Part2Readonly(unittest.TestCase):
    def test_shell_tools_are_state_changing(self):
        self.assertFalse(_tool_is_read_only("list_backups", {}))
        self.assertFalse(_tool_is_read_only("ssh_backup_list", {}))
        self.assertFalse(_tool_is_read_only("ssh_backup_create", {}))
        self.assertFalse(_tool_is_read_only("ssh_backup_schedule", {}))
        self.assertFalse(_tool_is_read_only("backup_create", {}))
        self.assertFalse(_tool_is_read_only("schedule_job", {}))

    def test_list_commands_stays_read_only(self):
        self.assertTrue(_tool_is_read_only("list_commands", {}))

    def test_dry_run_unaffected(self):
        # 'run' is not a shell token; dry_run keeps its prior
        # classification (unknown verb -> state-changing, fail closed).
        self.assertFalse(_tool_is_read_only("dry_run", {}))

    def test_state_verbs_include_backup_and_schedule(self):
        self.assertIn("backup", _STATE_VERBS)
        self.assertIn("schedule", _STATE_VERBS)

    def test_ordinary_read_tools_unaffected(self):
        self.assertTrue(_tool_is_read_only("list_files", {}))
        self.assertTrue(_tool_is_read_only("read_file", {"path": "/tmp/a.txt"}))
        self.assertTrue(_tool_is_read_only("get_status", {}))


class Part3Discovery(unittest.TestCase):
    def test_tools_list_with_shell_tool_flags(self):
        v = screen_discovery("tools/list", _tools_list(
            ["check_link", "ssh_backup_list"]))
        self.assertEqual(v["verdict"], "flagged")
        self.assertEqual(v["poison_category"], POISON_SHELL_INJECTION)
        self.assertTrue(any("shell-capable" in r for r in v["reasons"]))

    def test_tools_list_without_shell_tool_stays_clean(self):
        v = screen_discovery("tools/list", _tools_list(
            ["check_link", "list_commands"]))
        self.assertEqual(v["verdict"], "clean")

    def test_non_tools_list_method_not_flagged_for_shell_names(self):
        # Shell-token names in a prompts/list response are not tools.
        resp = {"jsonrpc": "2.0", "id": 1,
                "result": {"protocolVersion": "2024-11-05",
                           "prompts": [{"name": "ssh_backup_list",
                                        "description": "x"}]}}
        v = screen_discovery("prompts/list", resp)
        self.assertEqual(v["verdict"], "clean")


class FakeServer:
    def __init__(self):
        self.session_bindings = {}
        self.tenant_policies = {}
        self.tenant_policy_cache = {}


class FakeCfg:
    def __init__(self, mode="off"):
        self.intent_binding_mode = mode


def _base_session(**overrides):
    session = {
        "binding_id": "bind_test",
        "payer": "alice",
        "counterparty": "bob",
        "amount": "25.00",
        "currency": "USD",
        "artifacts": [],
        "step_up": {},
        "passport_id": "pass_test",
        "passport_expires_at": (datetime.now(timezone.utc)
                                + timedelta(hours=1)).isoformat(),
        "verified_at": time.time(),
        "tenant_verified": True,
        "tenant_id": "tnt_test",
    }
    session.update(overrides)
    return session


def _make_handler(policy):
    handler = object.__new__(ProxyHandler)
    handler.server = FakeServer()
    handler.server.session_bindings["test-session"] = _base_session()
    handler.server.tenant_policies["tnt_test"] = policy
    return handler, FakeCfg("off")


_FLAG_VERDICT = {"verdict": "flag", "level": "high",
                 "poison_category": POISON_SHELL_INJECTION,
                 "reasons": ["shell metacharacter (command separator)"
                             " in argument 'comment'"]}


class PolicyWiring(unittest.TestCase):
    def test_flagged_enforce_policy2_blocks_without_attestation(self):
        handler, cfg = _make_handler({
            "policy1_mode": "enforce", "policy2_step_up_enabled": True})
        gate = handler._intent_gate(
            "test-session", "ssh_backup_create",
            {"database": "mydb", "comment": "nightly; rm"},
            cfg, req={}, screen_verdict=_FLAG_VERDICT)
        self.assertIsNotNone(gate)
        self.assertEqual(gate["error"]["data"]["reason"],
                         "step_up_attestation_missing")
        self.assertIn("content_flag",
                      gate["error"]["data"]["step_up_triggers"])

    def test_flagged_audit_proceeds(self):
        handler, cfg = _make_handler({
            "policy1_mode": "audit", "policy2_step_up_enabled": True})
        gate = handler._intent_gate(
            "test-session", "ssh_backup_create",
            {"database": "mydb", "comment": "nightly; rm"},
            cfg, req={}, screen_verdict=_FLAG_VERDICT)
        self.assertIsNone(gate)

    def test_flagged_enforce_policy2_disabled_proceeds_if_bound(self):
        handler, cfg = _make_handler({
            "policy1_mode": "enforce", "policy2_step_up_enabled": False})
        gate = handler._intent_gate(
            "test-session", "ssh_backup_create",
            {"database": "mydb", "comment": "nightly; rm"},
            cfg, req={}, screen_verdict=_FLAG_VERDICT)
        self.assertIsNone(gate)

    def test_flagged_enforce_no_session_blocks_missing_binding(self):
        handler = object.__new__(ProxyHandler)
        handler.server = FakeServer()
        cfg = FakeCfg("enforce")
        gate = handler._intent_gate(
            "test-session", "ssh_backup_create",
            {"database": "mydb", "comment": "nightly; rm"},
            cfg, req={}, screen_verdict=_FLAG_VERDICT)
        self.assertIsNotNone(gate)
        self.assertEqual(gate["error"]["data"]["reason"], "missing_binding")


if __name__ == "__main__":
    unittest.main()
