#!/usr/bin/env python3
"""The AWS edition of Bundle D is sold 5-10 percent below the Stripe-direct bundle, and the
tool that changes the live rate card cannot drop a dimension or move a price it did not mean to.

WHY THESE EXIST. A Marketplace change set REPLACES the rate card with whatever it is handed
(it rolled Bundle D back to placeholders on 2026-07-27), and the failure is not an error, it is a
listing with wrong prices. So the guards are executed here against the REAL live offer: the
fixture is the DescribeEntity document the Actions run returned on 2026-10-25, not a document
written to match the code.

    python3 test_bundle_d_aws_prices.py

No network, no AWS. The client the apply path talks to is a fake that records its calls.
"""
import ast
import copy
import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import marketplace_update_offer_prices as tool  # noqa: E402

FIXTURE = ROOT / "aws_marketplace" / "fixtures" / "offer_3d5w6tbuis4wu_2026-10-25.json"


def live():
    return json.loads(FIXTURE.read_text())


def spec():
    return tool.load_spec()


def code_prices_cents() -> dict:
    """METERED_CREDIT_COSTS out of relayshield_api.py, by ast, so this needs no boto3."""
    tree = ast.parse((ROOT / "relayshield_api.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "METERED_CREDIT_COSTS":
            return {k.value: v.value for k, v in zip(node.value.keys, node.value.values)
                    if isinstance(k, ast.Constant) and isinstance(v, ast.Constant)}
    raise AssertionError("METERED_CREDIT_COSTS not found")


class FakeCatalog:
    def __init__(self):
        self.calls = []

    def start_change_set(self, **kw):
        self.calls.append(kw)
        return {"ChangeSetId": "cs-test"}


class FakeSts:
    def __init__(self, account):
        self.account = account

    def get_caller_identity(self):
        return {"Account": self.account}


class TheSpec(unittest.TestCase):
    def test_every_aws_price_is_within_the_five_to_ten_percent_band(self):
        tool.check_spec(spec())  # raises on any price outside the band

    def test_the_monthly_minimum_is_270_because_269_is_outside_the_band(self):
        s = spec()
        self.assertEqual(s["monthly"]["agentic_bundle_access"]["aws"], "270")
        s["monthly"]["agentic_bundle_access"]["aws"] = "269"
        with self.assertRaisesRegex(tool.Refused, "10.03 percent"):
            tool.check_spec(s)

    def test_references_are_what_the_code_charges_stripe_direct_callers(self):
        cents = code_prices_cents()
        paths = {"bulk_identity_risk": "/v1/metered/bulk-identity-risk",
                 "tech_stack_cve": "/v1/metered/tech-stack-cve",
                 "mcp_registry_risk": "/v1/metered/mcp-registry-risk",
                 "prompt_injection_breach": "/v1/metered/prompt-injection-breach",
                 "llm_credential_exposure": "/v1/metered/llm-credential-exposure"}
        for dim, path in paths.items():
            self.assertEqual(Decimal(spec()["per_call"][dim]["reference"]), Decimal(cents[path]) / 100, dim)

    def test_a_price_four_percent_off_or_eleven_percent_off_is_refused(self):
        for aws in ("1.920", "1.780"):    # 4.0 and 11.0 percent off 2.000
            s = spec()
            s["per_call"]["bulk_identity_risk"]["aws"] = aws
            with self.assertRaises(tool.Refused, msg=aws):
                tool.check_spec(s)

    def test_a_price_above_the_reference_is_refused(self):
        s = spec()
        s["per_call"]["tech_stack_cve"]["aws"] = "0.250"
        with self.assertRaises(tool.Refused):
            tool.check_spec(s)


class TheLiveOffer(unittest.TestCase):
    def test_the_real_offer_passes_every_guard(self):
        tool.check_live(live(), spec())

    def test_a_missing_dimension_is_refused_because_that_is_the_rollback(self):
        d = live()
        d["Terms"][0]["RateCards"][0]["RateCard"].pop()   # drop llm_credential_exposure
        with self.assertRaisesRegex(tool.Refused, "only spec"):
            tool.check_live(d, spec())

    def test_an_extra_dimension_is_refused(self):
        d = live()
        d["Terms"][0]["RateCards"][0]["RateCard"].append({"DimensionKey": "agent_bait_scan", "Price": "0.500"})
        with self.assertRaisesRegex(tool.Refused, "only live"):
            tool.check_live(d, spec())

    def test_a_live_price_that_has_already_moved_is_refused(self):
        d = live()
        d["Terms"][0]["RateCards"][0]["RateCard"][0]["Price"] = "1.800"
        with self.assertRaisesRegex(tool.Refused, "overwrite that change"):
            tool.check_live(d, spec())

    def test_the_wrong_offer_or_product_or_state_is_refused(self):
        for key, bad in (("Id", "offer-aaaaaaaaaaaaa"), ("ProductId", "prod-szi2wdww3obry"), ("State", "Draft")):
            d = live()
            d[key] = bad
            with self.assertRaises(tool.Refused, msg=key):
                tool.check_live(d, spec())


class TheChangeSet(unittest.TestCase):
    def setUp(self):
        self.cs = tool.build_change_set(live(), spec())
        self.change = self.cs["ChangeSet"][0]

    def test_exactly_one_pricing_change_on_the_offer(self):
        self.assertEqual(len(self.cs["ChangeSet"]), 1)
        self.assertEqual(self.change["ChangeType"], "UpdatePricingTerms")
        self.assertEqual(self.change["Entity"], {"Type": "Offer@1.0", "Identifier": "offer-3d5w6tbuis4wu"})

    def test_it_carries_only_the_two_pricing_terms(self):
        terms = self.change["DetailsDocument"]["Terms"]
        self.assertEqual([t["Type"] for t in terms], ["UsageBasedPricingTerm", "ConfigurableUpfrontPricingTerm"])
        self.assertEqual(self.change["DetailsDocument"]["PricingModel"], "Contract")

    def test_all_six_dimensions_survive_with_the_new_prices_in_the_live_number_style(self):
        got = {}
        for t in self.change["DetailsDocument"]["Terms"]:
            for card in t["RateCards"]:
                for row in card["RateCard"]:
                    got[row["DimensionKey"]] = row["Price"]
        self.assertEqual(got, {
            "bulk_identity_risk": "1.800", "tech_stack_cve": "0.180", "mcp_registry_risk": "0.320",
            "prompt_injection_breach": "0.320", "llm_credential_exposure": "0.360",
            "agentic_bundle_access": "270"})

    def test_nothing_but_the_prices_differs_from_the_live_terms(self):
        def neutral(terms):
            t = copy.deepcopy(terms)
            for term in t:
                for card in term["RateCards"]:
                    for row in card["RateCard"]:
                        row["Price"] = "x"
            return t
        live_terms = [t for t in live()["Terms"] if t["Type"] in ("UsageBasedPricingTerm", "ConfigurableUpfrontPricingTerm")]
        self.assertEqual(neutral(live_terms), neutral(self.change["DetailsDocument"]["Terms"]))

    def test_the_input_document_is_not_mutated(self):
        d = live()
        tool.build_change_set(d, spec())
        self.assertEqual(d, live())

    def test_legal_support_renewal_and_targeting_are_not_in_the_change_set(self):
        blob = json.dumps(self.cs)
        for word in ("LegalTerm", "SupportTerm", "RenewalTerm", "TargetingRule", "RefundPolicy"):
            self.assertNotIn(word, blob)


class TheCommandLine(unittest.TestCase):
    def run_main(self, args, client=None, sts=None):
        import contextlib
        import io
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = tool.main(args + ["--from-file", str(FIXTURE)], client=client, sts=sts)
        return rc, out.getvalue(), err.getvalue()

    def test_dry_run_sends_nothing_and_prints_the_table(self):
        client = FakeCatalog()
        rc, out, _ = self.run_main([], client=client)
        self.assertEqual(rc, 0)
        self.assertEqual(client.calls, [])
        self.assertIn("DRY RUN. Nothing was sent.", out)
        self.assertIn("agentic_bundle_access", out)

    def test_apply_without_the_confirmation_is_refused_before_anything_else(self):
        client = FakeCatalog()
        rc, _, err = self.run_main(["--apply"], client=client, sts=lambda: FakeSts(tool.ACCOUNT))
        self.assertEqual(rc, 2)
        self.assertIn("UPDATE-LIVE-PRICES", err)
        self.assertEqual(client.calls, [])

    def test_apply_with_the_wrong_confirmation_is_refused(self):
        client = FakeCatalog()
        rc, _, _ = self.run_main(["--apply", "--confirm", "yes"], client=client, sts=lambda: FakeSts(tool.ACCOUNT))
        self.assertEqual(rc, 2)
        self.assertEqual(client.calls, [])

    def test_apply_against_the_wrong_aws_account_sends_nothing(self):
        client = FakeCatalog()
        with self.assertRaises(SystemExit):
            self.run_main(["--apply", "--confirm", tool.CONFIRM], client=client, sts=lambda: FakeSts("620534471984"))
        self.assertEqual(client.calls, [])

    def test_a_confirmed_apply_on_the_right_account_sends_exactly_one_change_set(self):
        client = FakeCatalog()
        rc, out, _ = self.run_main(["--apply", "--confirm", tool.CONFIRM], client=client, sts=lambda: FakeSts(tool.ACCOUNT))
        self.assertEqual(rc, 0)
        self.assertEqual(len(client.calls), 1)
        call = client.calls[0]
        self.assertEqual(call["Catalog"], "AWSMarketplace")
        self.assertEqual(len(call["ChangeSet"]), 1)
        self.assertIn("SUBMITTED", out)

    def test_a_stale_spec_is_refused_even_with_a_valid_confirmation(self):
        d = live()
        d["Terms"][1]["RateCards"][0]["RateCard"][0]["Price"] = "250"
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(d, f)
        client = FakeCatalog()
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rc = tool.main(["--apply", "--confirm", tool.CONFIRM, "--from-file", f.name],
                           client=client, sts=lambda: FakeSts(tool.ACCOUNT))
        self.assertEqual(rc, 2)
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
