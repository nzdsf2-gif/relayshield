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


class McpUsageInstructions(unittest.TestCase):
    """The MCP usage instructions are a field on the Fulfillment options form, next to the endpoint URL.
    On 2026-10-26 the endpoint URL was changed in the form while this text still told buyers to connect
    to the old Space and described a registration-age check that no longer runs."""

    TEXT = (ROOT / "aws_marketplace" / "bundle_d_mcp_usage_instructions.md").read_text(encoding="utf-8")

    def test_fits_the_4000_character_field(self):
        self.assertLessEqual(len(self.TEXT), 4000)

    def test_points_at_the_aws_endpoint_and_never_at_the_old_space(self):
        self.assertIn("https://api.relayshield.net/mcp", self.TEXT)
        for stale in ("hf.space", "gradio", "/sse", "huggingface"):
            self.assertNotIn(stale, self.TEXT.lower(), stale)

    def test_names_the_transport_so_an_sse_only_client_is_not_surprised(self):
        self.assertIn("Streamable HTTP", self.TEXT)

    def test_documents_exactly_the_tools_the_endpoint_serves(self):
        import re
        script = (ROOT / "tools" / "create_mcp_http_lambda.sh").read_text(encoding="utf-8")
        toolset = set(re.search(r'^TOOLSET="([^"]+)"', script, re.M).group(1).split(","))
        documented = set(re.findall(r"^(check_[a-z_]+):", self.TEXT, re.M))
        self.assertEqual(documented, toolset)

    def test_claims_nothing_the_aws_path_does_not_do(self):
        self.assertIsNone(re.search(r"registration[- ]age|newly[- ]registered|domain age", self.TEXT, re.I))

    def test_house_rules(self):
        self.assertNotIn("\u2014", self.TEXT)
        for name in ("have i been pwned", "haveibeenpwned", "hibp", "hudson rock", "cavalier", "github", "rdap", "stripe"):
            self.assertNotIn(name, self.TEXT.lower(), name)
        self.assertIsNone(re.search(r"\d+(\.\d+)?\s?[MK]\+", self.TEXT))


class PasteableWithoutWhitespaceErrors(unittest.TestCase):
    """The Management Portal rejects any field value that starts or ends with whitespace:
    "Values can not start or end with whitespace characters (space, tab, newline)". On 2026-10-26 the
    MCP usage instructions file ended with a newline, so even the RIGHT file would have been refused
    on paste. These files are pasted whole into portal fields, so they carry no trailing newline."""

    PASTE_FILES = ("bundle_d_mcp_usage_instructions.md", "bundle_d_api_usage_instructions.md")

    def test_whole_field_files_have_no_leading_or_trailing_whitespace(self):
        for name in self.PASTE_FILES:
            raw = (ROOT / "aws_marketplace" / name).read_bytes().decode("utf-8")
            self.assertEqual(raw, raw.strip(), name)

    def test_every_copy_field_has_no_leading_or_trailing_whitespace(self):
        for key in ("ShortDescription", "LongDescription"):
            self.assertEqual(COPY[key], COPY[key].strip(), key)
        for item in COPY["Highlights"] + COPY["SearchKeywords"]:
            self.assertEqual(item, item.strip(), item)

    def test_per_field_portal_files_are_exactly_the_json_fields(self):
        """aws_marketplace/portal_fields/ is what Andrew opens by raw URL and pastes one field at a time.
        It must be byte-identical to the JSON the verifier compares against, or a correct paste reads DIFFERS."""
        d = ROOT / "aws_marketplace" / "portal_fields"
        want = {
            "1_short_description.txt": COPY["ShortDescription"],
            "2_long_description.txt": COPY["LongDescription"],
            "3_highlight_1.txt": COPY["Highlights"][0],
            "4_highlight_2.txt": COPY["Highlights"][1],
            "5_highlight_3.txt": COPY["Highlights"][2],
            "6_search_keywords_comma_separated.txt": ",".join(COPY["SearchKeywords"]),
        }
        self.assertEqual(sorted(p.name for p in d.iterdir()), sorted(want))
        for name, text in want.items():
            self.assertEqual((d / name).read_bytes(), text.encode("utf-8"), name)

    def test_no_carriage_returns_which_some_forms_count_as_extra_characters(self):
        for name in self.PASTE_FILES:
            self.assertNotIn("\r", (ROOT / "aws_marketplace" / name).read_bytes().decode("utf-8"), name)

    def test_the_two_usage_files_are_not_each_other_or_the_long_description(self):
        mcp = (ROOT / "aws_marketplace" / "bundle_d_mcp_usage_instructions.md").read_text(encoding="utf-8")
        api = (ROOT / "aws_marketplace" / "bundle_d_api_usage_instructions.md").read_text(encoding="utf-8")
        self.assertTrue(mcp.startswith("Connecting\n"), "the MCP file must start with its own heading")
        self.assertTrue(api.startswith("Overview\n"), "the API file must start with its own heading")
        self.assertNotIn("is built for the emerging risk", mcp + api)


class ApiUsageInstructions(unittest.TestCase):
    """The REST usage text is the other usage field on the same form. It is the LIVE text with one
    sentence changed, because the registration-age lookup does not run for AWS-licensed keys."""

    TEXT = (ROOT / "aws_marketplace" / "bundle_d_api_usage_instructions.md").read_text(encoding="utf-8")

    def test_fits_the_4000_character_field(self):
        self.assertLessEqual(len(self.TEXT), 4000)

    def test_the_false_claim_is_gone_and_the_true_one_is_in(self):
        self.assertNotIn("registration-age", self.TEXT)
        self.assertIn("typosquat risk and known-malicious domains", self.TEXT)

    def test_all_five_endpoints_and_the_base_url_survive(self):
        for path in ("mcp-registry-risk", "prompt-injection-breach", "tech-stack-cve", "bulk-identity-risk", "llm-credential-exposure"):
            self.assertIn(f"https://api.relayshield.net/v1/metered/{path}", self.TEXT, path)
        self.assertIn("X-RS-API-KEY", self.TEXT)

    def test_curl_continuation_lines_are_intact(self):
        self.assertGreaterEqual(sum(1 for line in self.TEXT.splitlines() if line.endswith(" \\")), 10)

    def test_house_rules(self):
        self.assertNotIn("\u2014", self.TEXT)
        for name in ("have i been pwned", "haveibeenpwned", "hibp", "hudson rock", "cavalier", "github", "rdap", "stripe"):
            self.assertNotIn(name, self.TEXT.lower(), name)


if __name__ == "__main__":
    unittest.main()
