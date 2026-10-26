#!/usr/bin/env python3
"""The listing verifier must tell a right paste from a wrong one, and must not pass what it cannot see.

WHY. Changes to Bundle D's listing are pasted into Management Portal forms by a person, and a
session cannot see the clipboard. On 2026-10-26 the wrong file went into a field. tools/
verify_bundle_d_listing.py is how a session learns what is ACTUALLY live. A checker that passes the
wrong text, or fails the right text, is worse than none, so each way of being wrong is executed here.

The BEFORE document is the real DescribeEntity structure of prod-kkvurtspreofy (Actions run
40201513798); AFTER is built from the repo's own files by the same helper the tool uses to read them.

    python3 test_verify_bundle_d_listing.py
"""
import contextlib
import copy
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import verify_bundle_d_listing as v  # noqa: E402

FIX = ROOT / "aws_marketplace" / "fixtures"
BEFORE = json.loads((FIX / "prod_kkvurtspreofy_before_2026-10-25.json").read_text())
OFFER_BEFORE = json.loads((FIX / "offer_3d5w6tbuis4wu_2026-10-25.json").read_text())


def after_product():
    p = copy.deepcopy(BEFORE)
    copy_json = json.loads(v.read("bundle_d_listing_copy.json"))
    d = p["Description"]
    for k in ("ShortDescription", "LongDescription", "Highlights", "SearchKeywords"):
        d[k] = copy_json[k]
    opt = p["Versions"][0]["DeliveryOptions"][0]
    opt["UsageInstructions"] = v.read("bundle_d_api_usage_instructions.md")
    ep = opt["Endpoints"][0]
    ep["EndpointUrl"] = v.MCP_URL
    ep["IntegrationProtocols"][0]["UsageInstructions"] = v.read("bundle_d_mcp_usage_instructions.md")
    for plat in opt["HostingArchitecture"]["Platforms"]:
        plat["Provider"], plat["EnvironmentOwner"] = "AWS", "SELLER"
    opt["HostingArchitecture"]["ArchitectureDiagramUrl"] = "https://example.invalid/architecture.png"
    return p


def after_offer():
    spec = json.loads(v.read("bundle_d_aws_prices.json"))
    new = {d: x["aws"] for g in ("monthly", "per_call") for d, x in spec[g].items()}
    o = copy.deepcopy(OFFER_BEFORE)
    for t in o["Terms"]:
        for card in t.get("RateCards", []):
            for row in card.get("RateCard", []):
                row["Price"] = new[row["DimensionKey"]]
    return o


def failed(results, stage):
    return [c["label"] for c in results[stage] if not c["ok"]]


class TheBeforeState(unittest.TestCase):
    def setUp(self):
        self.results, self.ok = v.run(BEFORE, OFFER_BEFORE, "all")

    def test_nothing_that_has_not_been_changed_yet_passes(self):
        self.assertFalse(self.ok)
        for stage in ("endpoint", "copy", "architecture", "prices"):
            self.assertTrue(failed(self.results, stage), stage)

    def test_the_endpoint_stage_names_each_stale_field(self):
        labels = " | ".join(failed(self.results, "endpoint"))
        self.assertIn("endpoint URL", labels)
        self.assertIn("MCP usage instructions", labels)
        self.assertIn("API usage instructions", labels)

    def test_things_that_must_not_change_do_pass_before_and_after(self):
        passed = {c["label"] for c in self.results["endpoint"] if c["ok"]}
        self.assertIn("fulfillment URL unchanged", passed)
        self.assertIn("product still Public", passed)
        self.assertIn("authorization is API_KEY only", passed)

    def test_prices_read_as_before(self):
        self.assertIn("BEFORE", failed(self.results, "prices")[0])


class TheAfterState(unittest.TestCase):
    def test_everything_passes_when_the_repo_files_are_what_is_live(self):
        results, ok = v.run(after_product(), after_offer(), "all")
        self.assertTrue(ok, {s: failed(results, s) for s in v.STAGES})

    def test_prices_read_as_after(self):
        results, _ = v.run(after_product(), after_offer(), "prices")
        self.assertIn("AFTER", results["prices"][0]["label"])


class TheWaysAPasteGoesWrong(unittest.TestCase):
    def _endpoint_failures(self, mutate):
        p = after_product()
        mutate(p)
        results, _ = v.run(p, after_offer(), "endpoint")
        return failed(results, "endpoint")

    def test_a_trailing_newline_is_caught_and_named_as_whitespace_only(self):
        def m(p):
            p["Versions"][0]["DeliveryOptions"][0]["Endpoints"][0]["IntegrationProtocols"][0]["UsageInstructions"] += "\n"
        got = self._endpoint_failures(m)
        self.assertEqual(len(got), 1)
        results, _ = v.run(after_product(), after_offer(), "endpoint")
        mcp_want = v.read("bundle_d_mcp_usage_instructions.md")
        self.assertIn("ONLY in leading/trailing whitespace", v.where_different(mcp_want, mcp_want + "\n"))

    def test_the_long_description_pasted_into_the_mcp_field_is_caught(self):
        wrong = json.loads(v.read("bundle_d_listing_copy.json"))["LongDescription"]

        def m(p):
            p["Versions"][0]["DeliveryOptions"][0]["Endpoints"][0]["IntegrationProtocols"][0]["UsageInstructions"] = wrong
        self.assertTrue(any("MCP usage instructions" in x for x in self._endpoint_failures(m)))

    def test_the_two_usage_texts_swapped_between_fields_are_caught(self):
        def m(p):
            opt = p["Versions"][0]["DeliveryOptions"][0]
            mcp = opt["Endpoints"][0]["IntegrationProtocols"][0]
            mcp["UsageInstructions"], opt["UsageInstructions"] = opt["UsageInstructions"], mcp["UsageInstructions"]
        self.assertEqual(len(self._endpoint_failures(m)), 2)

    def test_the_old_api_text_with_the_false_sentence_is_caught(self):
        def m(p):
            opt = p["Versions"][0]["DeliveryOptions"][0]
            opt["UsageInstructions"] = opt["UsageInstructions"].replace("known-malicious domains", "registration-age red flags")
        self.assertTrue(any("API usage instructions" in x for x in self._endpoint_failures(m)))

    def test_the_old_space_url_is_caught(self):
        def m(p):
            p["Versions"][0]["DeliveryOptions"][0]["Endpoints"][0]["EndpointUrl"] = BEFORE["Versions"][0]["DeliveryOptions"][0]["Endpoints"][0]["EndpointUrl"]
        self.assertTrue(any("endpoint URL" in x for x in self._endpoint_failures(m)))

    def test_a_second_endpoint_is_caught(self):
        def m(p):
            eps = p["Versions"][0]["DeliveryOptions"][0]["Endpoints"]
            eps.append(copy.deepcopy(eps[0]))
        self.assertTrue(any("exactly one endpoint" in x for x in self._endpoint_failures(m)))

    def test_a_change_of_fulfillment_url_or_visibility_is_caught(self):
        def m(p):
            p["Versions"][0]["DeliveryOptions"][0]["FulfillmentUrl"] = "https://example.invalid/x"
            p["Description"]["Visibility"] = "Limited"
        self.assertEqual(len(self._endpoint_failures(m)), 2)

    def test_half_applied_prices_read_as_mixed(self):
        o = after_offer()
        o["Terms"][0]["RateCards"][0]["RateCard"][0]["Price"] = "2.000"
        results, ok = v.run(after_product(), o, "prices")
        self.assertFalse(ok)
        self.assertIn("MIXED", results["prices"][0]["label"])

    def test_architecture_still_unspecified_is_caught(self):
        p = after_product()
        p["Versions"][0]["DeliveryOptions"][0]["HostingArchitecture"]["Platforms"][0]["Provider"] = "UNSPECIFIED"
        results, ok = v.run(p, after_offer(), "architecture")
        self.assertFalse(ok)
        self.assertEqual(len(failed(results, "architecture")), 1)

    def test_a_missing_diagram_is_caught(self):
        p = after_product()
        p["Versions"][0]["DeliveryOptions"][0]["HostingArchitecture"]["ArchitectureDiagramUrl"] = ""
        self.assertFalse(v.run(p, after_offer(), "architecture")[1])


class TheRenderedMarkdownSignature(unittest.TestCase):
    """2026-10-26: the API usage text went live 35 characters short (3,675 of 3,710), first difference at
    character 214, because it was copied from a rendered Markdown preview. The numbers below are the
    real ones, and the MCP file passed because it contains neither construct."""

    API = v.read("bundle_d_api_usage_instructions.md")

    def test_the_real_numbers_reproduce_exactly(self):
        rendered = v.as_rendered_markdown(self.API)
        self.assertEqual((len(self.API), len(rendered)), (3710, 3675))
        self.assertEqual(next(i for i, (a, b) in enumerate(zip(self.API, rendered)) if a != b), 214)

    def test_the_verifier_names_the_cause(self):
        msg = v.where_different(self.API, v.as_rendered_markdown(self.API))
        self.assertIn("rendered Markdown preview", msg)
        self.assertIn("pbcopy", msg)

    def test_it_does_not_claim_that_cause_for_other_differences(self):
        self.assertNotIn("rendered Markdown", v.where_different(self.API, self.API.replace("Overview", "Overveiw")))
        self.assertNotIn("rendered Markdown", v.where_different(self.API, self.API[:-5]))

    def test_every_differing_region_is_listed_not_just_the_first(self):
        msg = v.where_different(self.API, v.as_rendered_markdown(self.API))
        self.assertIn("22 differing region(s)", msg)       # 13 backslash lines + 9 list markers
        self.assertIn("(+12 more)", msg)

    def test_the_mcp_file_is_unaffected_by_rendering(self):
        mcp = v.read("bundle_d_mcp_usage_instructions.md")
        self.assertEqual(v.as_rendered_markdown(mcp), mcp)


class EveryCopyFieldIsActuallyCompared(unittest.TestCase):
    """A mutant that stopped comparing Highlights survived the first version of this file."""

    def _copy_failures(self, mutate):
        p = after_product()
        mutate(p["Description"])
        results, _ = v.run(p, after_offer(), "copy")
        return failed(results, "copy")

    def test_a_changed_short_description_is_caught(self):
        self.assertEqual(len(self._copy_failures(lambda d: d.__setitem__("ShortDescription", d["ShortDescription"] + " x"))), 1)

    def test_a_changed_long_description_is_caught(self):
        self.assertEqual(len(self._copy_failures(lambda d: d.__setitem__("LongDescription", d["LongDescription"] + "\n"))), 1)

    def test_a_changed_highlight_is_caught(self):
        def m(d):
            d["Highlights"] = list(d["Highlights"])
            d["Highlights"][2] = "Backed by RelayShield's live threat intel corpus: 5.0M+ IOCs."
        self.assertEqual(len(self._copy_failures(m)), 1)

    def test_a_reordered_or_missing_keyword_is_caught(self):
        self.assertEqual(len(self._copy_failures(lambda d: d.__setitem__("SearchKeywords", d["SearchKeywords"][:-1]))), 1)
        self.assertEqual(len(self._copy_failures(lambda d: d.__setitem__("SearchKeywords", list(reversed(d["SearchKeywords"]))))), 1)

    def test_the_old_corpus_counts_still_live_are_caught_by_the_copy_stage(self):
        self.assertTrue(failed(v.run(BEFORE, OFFER_BEFORE, "copy")[0], "copy"))


class TheCommandLine(unittest.TestCase):
    def _run(self, product, offer, *args):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            pf, of = Path(d, "p.json"), Path(d, "o.json")
            pf.write_text(json.dumps(product))
            of.write_text(json.dumps(offer))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = v.main(["--from-file", str(pf), "--offer-file", str(of), *args])
        return rc, out.getvalue()

    def test_a_named_stage_judges_only_that_stage(self):
        p = after_product()
        p["Description"]["ShortDescription"] = "stale copy"
        self.assertEqual(self._run(p, after_offer(), "--stage", "endpoint")[0], 0)
        self.assertEqual(self._run(p, after_offer(), "--stage", "copy")[0], 1)
        self.assertEqual(self._run(p, after_offer(), "--stage", "all")[0], 1)

    def test_every_stage_is_always_printed(self):
        _, out = self._run(after_product(), after_offer(), "--stage", "endpoint")
        for stage in v.STAGES:
            self.assertIn(f"== {stage}", out)

    def test_live_read_uses_describe_entity_for_the_product_and_the_offer(self):
        calls = []

        class Client:
            def describe_entity(self, Catalog, EntityId):
                calls.append(EntityId)
                return {"DetailsDocument": after_offer() if EntityId.startswith("offer-") else after_product()}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = v.main([], client=Client())
        self.assertEqual(rc, 0)
        self.assertEqual(calls, ["prod-kkvurtspreofy", "offer-3d5w6tbuis4wu"])


if __name__ == "__main__":
    unittest.main()
