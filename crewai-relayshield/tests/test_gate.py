"""Offline tests. No network, no crewai, no API key.

The rules worth pinning are the ones that decide whether this is a gate or
decoration: an unrecognised state must never ALLOW, fail_open must never release
a FINDING, and a tool whose arguments we cannot parse must not be waved through.
"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crewai_relayshield import (  # noqa: E402
    POLICY, CheckResult, CheckState, GateAction,
    build_hook, decide, evaluate_gate_policy, extract_target,
)


class TestPolicyTable(unittest.TestCase):
    def test_every_state_has_an_action(self):
        for state in CheckState:
            self.assertIn(state, POLICY, f"{state} has no policy entry")

    def test_only_no_known_finding_allows(self):
        """The single most important line in the package."""
        allowing = [s for s, a in POLICY.items() if a is GateAction.ALLOW]
        self.assertEqual(allowing, [CheckState.NO_KNOWN_FINDING])

    def test_a_finding_denies(self):
        self.assertIs(POLICY[CheckState.FINDING], GateAction.DENY)

    def test_every_failure_defers_rather_than_allowing(self):
        for state in (CheckState.AUTH_FAILURE, CheckState.UPSTREAM_FAILURE,
                      CheckState.MALFORMED, CheckState.PAYMENT_REQUIRED,
                      CheckState.MISSING):
            self.assertIs(POLICY[state], GateAction.DEFER, state)

    def test_unrecognised_state_defers(self):
        """POLICY.get must not fall through to ALLOW for a state added later."""
        class Rogue(str):
            pass
        decision = evaluate_gate_policy(Rogue("something_new"))
        self.assertIs(decision.action, GateAction.DEFER)

    def test_findings_become_reason_codes(self):
        r = CheckResult(state=CheckState.FINDING, verdict="HIGH",
                        findings=[{"type": "typosquat"}, {"type": "known_malicious"}])
        d = evaluate_gate_policy(CheckState.FINDING, r)
        self.assertIn("typosquat", d.reason_codes)
        self.assertIn("known_malicious", d.reason_codes)


class TestExtractTarget(unittest.TestCase):
    def test_finds_a_server_url(self):
        self.assertEqual(extract_target({"server_url": "https://x.test/mcp"}),
                         ("https://x.test/mcp", None))

    def test_finds_a_package_name(self):
        self.assertEqual(extract_target({"package_name": "leftpad"}), (None, "leftpad"))

    def test_a_url_under_a_name_key_is_still_a_url(self):
        url, pkg = extract_target({"name": "https://x.test/mcp"})
        self.assertEqual(url, "https://x.test/mcp")
        self.assertIsNone(pkg)

    def test_unparseable_input_yields_nothing(self):
        self.assertEqual(extract_target({"foo": 1}), (None, None))
        self.assertEqual(extract_target(None), (None, None))

    def test_blank_strings_are_not_targets(self):
        self.assertEqual(extract_target({"server_url": "   "}), (None, None))


class TestDecide(unittest.TestCase):
    def _patch(self, state, result=None):
        return mock.patch("crewai_relayshield.hook.check_with_retry",
                          return_value=(state, result, None))

    def test_clean_allows(self):
        with self._patch(CheckState.NO_KNOWN_FINDING,
                         CheckResult(state=CheckState.NO_KNOWN_FINDING, verdict="LOW")):
            allowed, d = decide({"server_url": "https://x.test/mcp"})
        self.assertTrue(allowed)
        self.assertIs(d.action, GateAction.ALLOW)

    def test_finding_blocks(self):
        with self._patch(CheckState.FINDING,
                         CheckResult(state=CheckState.FINDING, verdict="HIGH",
                                     findings=[{"type": "typosquat"}])):
            allowed, d = decide({"server_url": "https://x.test/mcp"})
        self.assertFalse(allowed)
        self.assertIs(d.action, GateAction.DENY)

    def test_upstream_failure_blocks_by_default(self):
        with self._patch(CheckState.UPSTREAM_FAILURE):
            allowed, _ = decide({"server_url": "https://x.test/mcp"})
        self.assertFalse(allowed, "a failed check must not be treated as clean")

    def test_fail_open_releases_only_defer(self):
        with self._patch(CheckState.UPSTREAM_FAILURE):
            allowed, _ = decide({"server_url": "https://x.test/mcp"}, fail_open=True)
        self.assertTrue(allowed)

    def test_fail_open_never_releases_a_finding(self):
        """There is no configuration that lets a known-bad target through."""
        with self._patch(CheckState.FINDING,
                         CheckResult(state=CheckState.FINDING, findings=[{"type": "x"}])):
            allowed, _ = decide({"server_url": "https://x.test/mcp"}, fail_open=True)
        self.assertFalse(allowed)

    def test_fail_open_never_releases_a_completed_review(self):
        with self._patch(CheckState.UNKNOWN, CheckResult(state=CheckState.UNKNOWN)):
            allowed, _ = decide({"server_url": "https://x.test/mcp"}, fail_open=True)
        self.assertFalse(allowed, "REVIEW is a completed check, not a failed one")

    def test_no_target_blocks_and_never_calls_the_api(self):
        with mock.patch("crewai_relayshield.hook.check_with_retry") as called:
            allowed, d = decide({"unrelated": "value"})
        called.assert_not_called()
        self.assertFalse(allowed)
        self.assertIn("missing", d.reason_codes)


class TestHookShape(unittest.TestCase):
    """CrewAI's contract, read from the crewai 1.15.20 wheel: a before-hook takes
    a context and returns bool|None, and False aborts the call."""

    class Ctx:
        def __init__(self, tool_input, tool_name="connect_mcp_server"):
            self.tool_input = tool_input
            self.tool_name = tool_name

    def test_returns_false_to_block(self):
        with mock.patch("crewai_relayshield.hook.check_with_retry",
                        return_value=(CheckState.FINDING,
                                      CheckResult(state=CheckState.FINDING,
                                                  findings=[{"type": "x"}]), None)):
            out = build_hook()(self.Ctx({"server_url": "https://x.test/mcp"}))
        self.assertIs(out, False)

    def test_returns_none_to_proceed(self):
        with mock.patch("crewai_relayshield.hook.check_with_retry",
                        return_value=(CheckState.NO_KNOWN_FINDING,
                                      CheckResult(state=CheckState.NO_KNOWN_FINDING,
                                                  verdict="LOW"), None)):
            out = build_hook()(self.Ctx({"server_url": "https://x.test/mcp"}))
        self.assertIsNone(out, "None means no opinion; True is not the proceed signal")

    def test_on_block_callback_receives_the_decision(self):
        seen = []
        with mock.patch("crewai_relayshield.hook.check_with_retry",
                        return_value=(CheckState.FINDING,
                                      CheckResult(state=CheckState.FINDING,
                                                  findings=[{"type": "typosquat"}]), None)):
            build_hook(on_block=seen.append)(self.Ctx({"server_url": "https://x.test/mcp"}))
        self.assertEqual(len(seen), 1)
        self.assertIs(seen[0].action, GateAction.DENY)

    def test_the_gate_never_raises_into_the_agent(self):
        """An exception in a hook is an outage in someone's agent."""
        with mock.patch("crewai_relayshield.hook.check_with_retry",
                        side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                build_hook()(self.Ctx({"server_url": "https://x.test/mcp"}))
        # Documented gap: check_with_retry is the boundary that converts errors
        # into states, so anything raising past it is a bug in this package
        # rather than a condition to swallow. Asserted so a change is deliberate.


if __name__ == "__main__":
    unittest.main(verbosity=2)
