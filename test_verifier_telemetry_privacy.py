"""The privacy policy's verifier section (13) must say what the code actually does.

The MCP proxy section has the same kind of pin (test_mcp_proxy_privacy.py). Two things
that must agree with nothing checking that they do is this repo's most-repeated defect,
and a privacy policy that promises LESS than the code collects is the expensive version
of it. These tests read the policy and the code together.
"""
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import relayshield_verifier_telemetry as vt  # noqa: E402

SRC = (ROOT / "cloudflare_worker_privacy.js").read_text(encoding="utf-8")


def section(n):
    m = re.search(rf"<h2>{n}\. [^<]+</h2>(.*?)(?=<h2>|<hr>)", SRC, re.S)
    return m.group(1) if m else ""


def text(n):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", section(n))).lower()


# attribute the row can carry -> a phrase the policy must contain for it
ATTRIBUTE_PHRASES = {
    "agent_id_hash": "one-way hash of the agent's identifier",
    "ip_prefix": "network prefix only",
    "rejection_reason": "reason for the rejection",
    "attack_pattern": "whether a wallet address, a domain, or both were checked",
    "verifier_type": "which verifier rejected it",
    "issuer_hash": "hash of the identifier of the credential issuer",
    "reporter_hash": "hash derived from your api key",
    "ttl": "deleted automatically after 90 days",
}
# internal row keys that are not data about the event
STRUCTURAL = {"pk", "sk"}

REASON_PHRASES = {
    "bad_signature": "bad signature", "malformed": "malformed request", "expired": "expired",
    "replay": "replayed", "unknown_key": "unknown key", "intent_mismatch": "intent mismatch",
    "mandate_exceeded": "mandate exceeded", "ti_match": "threat intelligence match",
    "other": "or other",
}


class Section13(unittest.TestCase):
    def test_the_section_exists_and_is_about_the_verifiers(self):
        self.assertRegex(SRC, r"<h2>13\. Verifier Threat Telemetry")
        t = text(13)
        for name in ("tap", "pap", "x401"):
            self.assertIn(name, t)

    def test_contact_moved_to_14_and_the_reference_followed(self):
        self.assertRegex(SRC, r"<h2>14\. Contact</h2>")
        self.assertIn("address in section 14", SRC)

    def test_it_says_off_by_default_and_that_it_is_a_deliberate_setting(self):
        t = text(13)
        self.assertIn("optional, off by default", t)
        self.assertIn("telemetry_opt_in", t)
        self.assertIn("/v1/verifiers/config", t)
        self.assertIn("works the same whether telemetry is on or off", t)

    def test_it_says_only_rejections_are_recorded(self):
        t = text(13)
        self.assertIn("only rejections", t)
        self.assertIn("nothing when a verification is accepted or sent for review", t)

    def test_every_attribute_the_code_can_write_is_disclosed(self):
        full = vt.build_event("x401", {"decision": "reject", "reasons": ["ti_flagged"]},
                              agent_id="a", agent_ip="8.8.4.4", issuer="i",
                              screened=["wallet"], reporter="0123456789abcdef", now=1_800_000_000)
        written = set(full) - STRUCTURAL
        self.assertEqual(written, set(ATTRIBUTE_PHRASES),
                         "an attribute was added or removed: update the policy AND this map")
        t = text(13)
        for attr, phrase in ATTRIBUTE_PHRASES.items():
            self.assertIn(phrase, t, f"{attr}: the policy does not say '{phrase}'")

    def test_it_says_the_matched_indicator_itself_is_not_recorded(self):
        self.assertIn("the wallet address and the domain themselves are not recorded", text(13))
        item = vt.build_event("tap", {"decision": "reject", "reasons": ["ti_flagged"]},
                              screened=["0xDEADBEEF", "wallet"], now=1_800_000_000)
        self.assertNotIn("0xDEADBEEF", str(item))

    def test_every_rejection_reason_the_code_can_store_is_named(self):
        self.assertEqual(set(REASON_PHRASES), set(vt.REJECTION_REASONS))
        t = text(13)
        for reason, phrase in REASON_PHRASES.items():
            self.assertIn(phrase, t, reason)

    def test_stated_retention_matches_the_code(self):
        self.assertEqual(vt.TTL_DAYS, 90)
        self.assertIn("deleted automatically after 90 days", text(13))
        item = vt.build_event("tap", {"decision": "reject", "reasons": ["bad_signature"]}, now=1_000_000_000)
        self.assertEqual(item["ttl"] - 1_000_000_000, 90 * 86400)

    def test_prefix_lengths_stated_match_the_code(self):
        t = text(13)
        self.assertIn("first three parts of an ipv4 address", t)
        self.assertIn("first three groups of an ipv6 address", t)
        self.assertTrue(vt.network_prefix("8.8.4.4").endswith("/24"))
        self.assertTrue(vt.network_prefix("2606:4700:4700::1111").endswith("/48"))
        self.assertIn("only for public addresses", t)
        self.assertEqual(vt.network_prefix("10.1.2.3"), "")

    def test_it_lists_what_is_never_recorded(self):
        t = text(13)
        for must in ("transaction amounts", "merchants", "customer or cardholder data",
                     "the person named in an x401 credential", "the full agent identifier",
                     "a full ip address", "your api key", "free text"):
            self.assertIn(must, t)

    def test_it_does_not_overclaim_about_hashes_or_anonymity(self):
        """CLAUDE.md, the hash-wording lesson: a response hash cannot be reversed, an
        identifier hash CAN be confirmed by anyone who already holds the identifier."""
        t = text(13)
        for banned in ("cannot be reversed", "irreversible", "anonymiz", "anonymis", "untraceable",
                       "cannot be linked", "not personal"):
            self.assertNotIn(banned, t, banned)
        self.assertIn("anyone who already has an identifier can compute its hash", t)

    def test_it_promises_no_corpus_promotion_without_confirmation(self):
        t = text(13)
        self.assertIn("unverified claim from one source", t)
        self.assertIn("unless we have independently confirmed it", t)
        self.assertIn("including other customers", t)

    def test_it_discloses_cross_account_comparison(self):
        self.assertIn("compare entries from different accounts", text(13))

    def test_deletion_on_request_is_promised_and_has_a_tool(self):
        t = text(13)
        self.assertIn("we will delete the entries linked to your key", t)
        self.assertTrue((ROOT / "tools" / "delete_verifier_reports.py").exists())
        # the policy must not claim the old design doc's "historical data is not deleted"
        self.assertNotIn("not deleted", t)

    def test_it_does_not_describe_a_console_that_may_not_exist(self):
        self.assertNotIn("console", text(13))

    def test_no_backticks_or_template_expressions_in_the_section(self):
        """The policy is a JS template literal: a stray backtick ends it and a ${ is
        evaluated. node --check passes both. Executing the Worker is the real guard."""
        raw = section(13)
        self.assertNotIn("`", raw)
        self.assertNotIn("${", raw)


if __name__ == "__main__":
    unittest.main()
