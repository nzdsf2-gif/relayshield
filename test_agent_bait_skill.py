#!/usr/bin/env python3
"""Invariants for the Claude Code skill. No network, no boto3, no AWS.

Two of these pin defects this repo has already paid for once, which is the only
reason a test on a markdown file earns its place:

  * FD-8: a live link shipped four months ahead of its attribution key, so every
    arrival from the canonical MCP directory logged "unmatched:" and rendered no
    banner. The rule that came out of it is that the key is registered FIRST.
  * FD defect 4, and relayshield-venice-skill/SKILL.md today: publishing the raw
    execute-api hostname instead of the branded one. That URL is what callers and
    indexers persist, so it pins them to something that breaks when the gateway
    id changes.

Both are invisible in review and both are one grep to catch.
"""

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKILL = ROOT / ".claude" / "skills" / "relayshield-agent-bait" / "SKILL.md"
SIGNUP = ROOT / "relayshield_developer_signup.py"

TEXT = SKILL.read_text(encoding="utf-8")


class TestFrontmatter(unittest.TestCase):
    def test_has_yaml_frontmatter_with_name_and_description(self):
        self.assertTrue(TEXT.startswith("---\n"), "skill must open with frontmatter")
        end = TEXT.index("\n---\n", 3)
        fm = TEXT[4:end]
        self.assertRegex(fm, r"(?m)^name:\s*relayshield-agent-bait\s*$")
        self.assertIn("description:", fm)

    def test_description_names_the_trigger_situations(self):
        """A skill nobody triggers is a skill nobody has. The description is the
        whole trigger surface, so it must carry the words a user actually types."""
        fm = TEXT[4:TEXT.index("\n---\n", 3)].lower()
        for word in ("mcp server", "install", "prompt injection", "repository"):
            self.assertIn(word, fm, f"description should mention {word!r}")


class TestUrls(unittest.TestCase):
    def test_never_publishes_the_raw_execute_api_host(self):
        self.assertNotIn("execute-api", TEXT,
                         "use https://api.relayshield.net — the branded host is what "
                         "callers and x402 indexers persist")

    def test_uses_the_branded_host(self):
        self.assertIn("https://api.relayshield.net/v1/payg/agent-bait-scan", TEXT)


class TestAttributionKeyShipsFirst(unittest.TestCase):
    def test_every_source_param_in_the_skill_is_registered(self):
        """The rule from FD-8, enforced rather than remembered."""
        used = set(re.findall(r"[?&]source=([A-Za-z0-9_-]+)", TEXT))
        self.assertTrue(used, "the skill should carry at least one attributed link")

        tree = ast.parse(SIGNUP.read_text(encoding="utf-8"))
        registered = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for tgt in node.targets:
                name = getattr(tgt, "id", None) or getattr(tgt, "attr", None)
                if name == "_SOURCE_BANNERS" and isinstance(node.value, ast.Dict):
                    for k in node.value.keys:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            registered.add(k.value)
            # annotated assignment: _SOURCE_BANNERS: dict[...] = {...}
        for node in ast.walk(tree):
            if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "_SOURCE_BANNERS":
                if isinstance(node.value, ast.Dict):
                    for k in node.value.keys:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            registered.add(k.value)

        self.assertIn("claude-skill", registered,
                      "_SOURCE_BANNERS must carry the key BEFORE the link ships")
        missing = used - registered
        self.assertFalse(missing, f"unregistered ?source= keys in the skill: {sorted(missing)}")


class TestTheThreeRulesSurvive(unittest.TestCase):
    """The endpoint refuses to say these things. An agent reading the skill will
    paraphrase its results to a human, so the refusals have to be in the skill
    too or they are lost exactly where they matter."""

    def test_says_it_never_claims_safe(self):
        self.assertIn('never says "safe"', TEXT)
        self.assertIn("nothing known against it", TEXT)

    def test_says_it_never_calls_a_repo_malicious(self):
        self.assertIn("never calls a repository or a person malicious", TEXT)

    def test_tells_the_reader_to_check_surfaces_read(self):
        self.assertIn("surfaces_read", TEXT)
        self.assertIn("surfaces_missing", TEXT)

    def test_documents_the_hidden_text_escalation(self):
        self.assertIn("hidden_text", TEXT)
        self.assertIn("CRITICAL", TEXT)


class TestMatchesTheEndpoint(unittest.TestCase):
    def test_finding_types_match_the_handler(self):
        """A skill that documents a field the handler does not emit teaches an
        agent to look for something that never arrives."""
        src = (ROOT / "relayshield_agent_bait_scan.py").read_text(encoding="utf-8")
        emitted = set(re.findall(r'add\(\s*[^,]+,\s*"([a-z_]+)"', src))
        self.assertTrue(emitted, "could not read finding types out of the handler")
        for t in emitted:
            self.assertIn(t, TEXT, f"skill does not document finding type {t!r}")

    def test_price_matches_the_payg_table(self):
        src = (ROOT / "relayshield_agentic_api.py").read_text(encoding="utf-8")
        m = re.search(r'"/v1/payg/agent-bait-scan":\s*(\d+)', src)
        self.assertIsNotNone(m, "price not found in the PAYG table")
        self.assertEqual(m.group(1), "500000", "handler price changed")
        self.assertIn("$0.50", TEXT, "skill quotes a price the handler does not charge")


if __name__ == "__main__":
    unittest.main(verbosity=2)
