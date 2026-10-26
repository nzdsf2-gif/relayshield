#!/usr/bin/env python3
"""The AWS-edition listing copy must be accepted by AWS and must stay true.

WHY. A change to a PUBLISHED listing that AWS refuses costs a full review cycle, and the
first draft of this copy was 631 characters in a 500-character field. The limits below are the
ones the live, AWS-accepted listing sits inside (read from the live entity on 2026-10-25).
The other half is the claims. This copy says no customer query goes to an outside data provider;
that is true only because of the first-party data path (CLAUDE.md, the AWS-licensed path section),
so the copy may not claim anything that path does not do.

    python3 test_bundle_d_listing_copy.py
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COPY = json.loads((ROOT / "aws_marketplace" / "bundle_d_listing_copy.json").read_text(encoding="utf-8"))
MD = (ROOT / "aws_marketplace" / "bundle_d_listing_copy_aws_edition.md").read_text(encoding="utf-8")
FIELDS = ("ShortDescription", "LongDescription", "Highlights", "SearchKeywords")


def blob():
    return json.dumps({k: COPY[k] for k in FIELDS}, ensure_ascii=False)


class Limits(unittest.TestCase):
    def test_short_description_fits_the_500_character_field(self):
        self.assertLessEqual(len(COPY["ShortDescription"]), 500)

    def test_three_highlights_and_at_most_thirteen_keywords(self):
        # What AWS has already accepted: three highlights and thirteen keywords.
        self.assertEqual(len(COPY["Highlights"]), 3)
        self.assertLessEqual(len(COPY["SearchKeywords"]), 13)

    def test_every_keyword_and_highlight_is_nonempty_and_not_a_duplicate(self):
        self.assertEqual(len(set(COPY["SearchKeywords"])), len(COPY["SearchKeywords"]))
        self.assertTrue(all(h.strip() for h in COPY["Highlights"]))


class HouseRules(unittest.TestCase):
    def test_no_em_dashes(self):
        self.assertNotIn("—", blob())

    def test_no_corpus_counts(self):
        # MEASUREMENT DOCTRINE: never quote the corpus headline.
        for pat in (r"\d+(\.\d+)?\s?[MK]\+", r"\b3,750\b", r"\b85\+", r"\b5\.0M"):
            self.assertIsNone(re.search(pat, blob()), pat)

    def test_no_third_party_vendor_names(self):
        for name in ("have i been pwned", "haveibeenpwned", "hibp", "hudson rock", "cavalier", "github", "rdap", "stripe"):
            self.assertNotIn(name, blob().lower(), name)


class Truth(unittest.TestCase):
    def test_agent_bait_is_not_advertised(self):
        self.assertIsNone(re.search(r"agent[- ]bait", blob(), re.I))

    def test_no_tool_count_that_the_endpoint_does_not_serve(self):
        self.assertNotIn("13 tools", blob())
        self.assertIsNone(re.search(r"\b\d+ tools\b", blob()))

    def test_the_registration_age_check_is_not_claimed(self):
        # It is an outside lookup and does not run for AWS-licensed keys.
        self.assertIsNone(re.search(r"newly[- ]registered|registration age|domain age", blob(), re.I))

    def test_the_own_corpus_statement_and_the_no_forwarding_promise_are_present(self):
        text = COPY["LongDescription"]
        self.assertIn("RelayShield's own continuously collected corpus", text)
        self.assertIn("not forwarded to outside data providers", text)
        self.assertIn("names any signal it did not run", text)

    def test_every_advertised_endpoint_is_one_the_aws_toolset_serves(self):
        # The five checks named in the copy are exactly the listing tools in RS_MCP_TOOLS.
        script = (ROOT / "tools" / "create_mcp_http_lambda.sh").read_text(encoding="utf-8")
        toolset = set(re.search(r'^TOOLSET="([^"]+)"', script, re.M).group(1).split(","))
        self.assertEqual(toolset - {"check_server_status"}, {
            "check_mcp_server_risk", "check_prompt_injection_breach", "check_tech_stack_cve",
            "check_bulk_identity_risk", "check_llm_credential_exposure"})
        text = COPY["LongDescription"].lower()
        for phrase in ("mcp registry risk", "prompt-injection breach", "cve targeting",
                       "bulk per-agent identity risk", "llm credential exposure"):
            self.assertIn(phrase, text)


class PasteFile(unittest.TestCase):
    def test_the_paste_file_carries_every_field_verbatim(self):
        self.assertIn(COPY["ShortDescription"], MD)
        self.assertIn(COPY["LongDescription"], MD)
        for h in COPY["Highlights"]:
            self.assertIn(h, MD)
        for k in COPY["SearchKeywords"]:
            self.assertIn(f"- {k}\n", MD + "\n")

    def test_the_paste_file_states_the_right_short_length(self):
        m = re.search(r"Short description \((\d+) characters", MD)
        self.assertEqual(int(m.group(1)), len(COPY["ShortDescription"]))


if __name__ == "__main__":
    unittest.main()
