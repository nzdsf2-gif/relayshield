"""aws_marketplace/bundle_d_test_offer.json: the private test offer that runs Bundle D through a real subscription.

It is Bundle B's accepted test offer with the product, the dimensions and the wording changed, and nothing else.
The dimension keys are read from bundle_d_aws_prices.json, which the verifier proved equal to the LIVE offer's."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import marketplace_submit_changeset as T  # noqa: E402

D = json.load(open(ROOT / "aws_marketplace" / "bundle_d_test_offer.json"))
B = json.load(open(ROOT / "aws_marketplace" / "bundle_b_test_offer.json"))
PRICES = json.load(open(ROOT / "aws_marketplace" / "bundle_d_aws_prices.json"))


def change(doc, kind):
    return next(c for c in doc["ChangeSet"] if c["ChangeType"] == kind)["DetailsDocument"]


class Shape(unittest.TestCase):
    def test_same_nine_changes_in_the_same_order_as_the_accepted_bundle_b_offer(self):
        self.assertEqual([c["ChangeType"] for c in D["ChangeSet"]], [c["ChangeType"] for c in B["ChangeSet"]])
        self.assertEqual(D["ChangeSet"][-1]["ChangeType"], "ReleaseOffer")

    def test_it_targets_bundle_d_by_a_literal_id_not_a_typed_placeholder(self):
        pid = change(D, "CreateOffer")["ProductId"]
        self.assertEqual(pid, PRICES["product_id"])
        self.assertEqual(pid, "prod-kkvurtspreofy")

    def test_only_the_two_date_placeholders_remain_and_the_tool_substitutes_them(self):
        left = set(T.PLACEHOLDER_RE.findall(json.dumps(D)))
        self.assertEqual(left, {"__CHARGE_DATE__", "__AVAILABILITY_END_DATE__"})
        self.assertEqual(len(T.validate(T.substitute(D, ""))), 9)

    def test_buyer_is_the_test_account_only(self):
        self.assertEqual(change(D, "UpdateTargeting")["PositiveTargeting"]["BuyerAccounts"], ["442429445748"])


class Pricing(unittest.TestCase):
    def terms(self):
        t = change(D, "UpdatePricingTerms")["Terms"]
        return t[0], t[1]

    def test_the_entitlement_grant_is_the_live_monthly_dimension(self):
        up, _ = self.terms()
        self.assertEqual([g["DimensionKey"] for g in up["Grants"]], list(PRICES["monthly"]))
        self.assertEqual(up["Price"], "0")

    def test_every_live_metered_dimension_is_priced_and_none_is_free_or_extra(self):
        _, use = self.terms()
        card = use["RateCards"][0]["RateCard"]
        self.assertEqual([r["DimensionKey"] for r in card], list(PRICES["per_call"]))
        self.assertTrue(all(r["Price"] == "0.00000001" for r in card))  # non-zero so BatchMeterUsage is exercised

    def test_the_wording_is_not_longer_than_what_aws_accepted_for_bundle_b(self):
        for key in ("Name", "Description"):
            self.assertLessEqual(len(change(D, "UpdateInformation")[key]), len(change(B, "UpdateInformation")[key]), key)


class GuardStillProtectsTheLiveCard(unittest.TestCase):
    def test_a_change_aimed_at_the_live_entity_is_still_refused(self):
        doc = json.loads(json.dumps(T.substitute(D, "")))
        doc["ChangeSet"][1]["Entity"]["Identifier"] = "prod-kkvurtspreofy"
        with self.assertRaises(T.Refused):
            T.validate(doc)


if __name__ == "__main__":
    unittest.main()
