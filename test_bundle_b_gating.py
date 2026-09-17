#!/usr/bin/env python3
"""Guards for Bundle B's gating, its rate card, and the change-set submitter.

WHAT THESE PROTECT, and none of it fails loudly in production. A bundle that
overlaps another double-bills or cross-grants; a dimension key that disagrees
with the rate card meters into a dimension AWS does not have; a missing branch
in the 402 gate refuses every call from a customer who is being charged monthly.
That last one has SHIPPED TWICE, in Bundle D and again in Bundle A, which is why
it is asserted here one bundle before anyone could reintroduce it.

    python3 test_bundle_b_gating.py

Needs no AWS and no boto3: every table is read with `ast`, and the submitter's
guards are pure functions taking a parsed document.
"""
import ast
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import marketplace_submit_changeset as sub  # noqa: E402

CHANGESET = ROOT / "aws_marketplace" / "bundle_b_create_entity.json"


def literal_tables(path: Path, suffix: str) -> dict:
    """Every module-level dict literal whose name ends with `suffix`.

    BOTH ast.Assign AND ast.AnnAssign. Handling only Assign is how
    tools/source_arrivals.py once read one attribution table and silently
    skipped the other, returning a confident 117 keys with every real banner
    missing.
    """
    tree = ast.parse(path.read_text())
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            tgt = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if isinstance(tgt, ast.Name) and tgt.id.endswith(suffix):
                try:
                    out[tgt.id] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    pass
    return out


def dict_keys_of(path: Path, name: str) -> set:
    """The literal KEYS of a module-level dict, whatever its values are.

    literal_tables() cannot read BUNDLE_CONFIGS: its values reference module
    variables (BUNDLE_D_PRODUCT_CODE and friends), so literal_eval raises and the
    whole table is skipped -- silently, returning an empty set that reads exactly
    like "the entry is missing". That is what this helper exists to stop, and it
    was found by the guard failing on correct code rather than by reading it.
    """
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            tgt = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if isinstance(tgt, ast.Name) and tgt.id == name:
                if isinstance(node.value, ast.Dict):
                    return {k.value for k in node.value.keys
                            if isinstance(k, ast.Constant)}
    return set()


def code_only(py: str) -> str:
    """Source with comments and docstrings gone.

    Stripped in the FIRST version of these guards, not the second. The comments
    below the branches being asserted on quote the branch names verbatim, so a
    plain substring search would pass with the branch deleted.
    """
    tree = ast.parse(py)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and ast.get_docstring(node):
            node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def changeset_dimensions() -> list:
    doc = json.loads(CHANGESET.read_text())
    return [d for c in doc["ChangeSet"]
            if isinstance(c.get("DetailsDocument"), list)
            for d in c["DetailsDocument"]]


class TestNoBundleOverlaps(unittest.TestCase):
    """Three bundles, three tables, and nothing may appear in two of them."""

    def setUp(self):
        self.tables = literal_tables(ROOT / "relayshield_api.py", "DIMENSION_NAMES")

    def test_all_three_tables_are_present(self):
        for name in ("BUNDLE_A_DIMENSION_NAMES", "BUNDLE_B_DIMENSION_NAMES",
                     "BUNDLE_D_DIMENSION_NAMES"):
            self.assertIn(name, self.tables, f"{name} is missing or unparseable")

    def test_no_endpoint_belongs_to_two_bundles(self):
        seen = {}
        for name, table in self.tables.items():
            for path in table:
                self.assertNotIn(
                    path, seen,
                    f"{path} is in BOTH {name} and {seen.get(path)}. An endpoint in "
                    "two bundles bills twice or grants across, and neither raises.")
                seen[path] = name

    def test_no_dimension_key_belongs_to_two_bundles(self):
        seen = {}
        for name, table in self.tables.items():
            for key in table.values():
                self.assertNotIn(
                    key, seen,
                    f"dimension key {key!r} is in BOTH {name} and {seen.get(key)}")
                seen[key] = name


class TestTheRateCardAndTheCodeAgree(unittest.TestCase):
    """The change set creates the dimensions. The code meters into them."""

    def setUp(self):
        self.api = literal_tables(ROOT / "relayshield_api.py", "DIMENSION_NAMES")
        self.b = self.api["BUNDLE_B_DIMENSION_NAMES"]
        self.dims = changeset_dimensions()

    def test_every_metered_dimension_has_an_endpoint(self):
        metered = {d["Key"] for d in self.dims
                   if "ExternallyMetered" in d.get("Types", [])}
        self.assertEqual(
            metered, set(self.b.values()),
            "the rate card AWS will create and the table the code meters into "
            "disagree. Metering into a dimension the product does not have is "
            "rejected by AWS per call, forever, and looks like a billing outage.")

    def test_exactly_one_entitled_dimension_and_fulfillment_knows_it(self):
        entitled = [d["Key"] for d in self.dims if "Entitled" in d.get("Types", [])]
        self.assertEqual(len(entitled), 1,
                         f"expected one Entitled dimension, got {entitled}. That "
                         "one carries the monthly minimum.")
        keys = dict_keys_of(ROOT / "relayshield_bundle_fulfillment.py",
                            "BUNDLE_CONFIGS")
        self.assertTrue(keys, "BUNDLE_CONFIGS parsed as empty, which reads like a "
                              "missing entry and is a broken parse")
        self.assertIn(
            entitled[0], keys,
            f"the Entitled dimension {entitled[0]!r} has no BUNDLE_CONFIGS entry, so "
            "a subscriber resolves and is provisioned NOTHING. The E2E test AWS "
            "requires is exactly this path.")

    def test_the_five_prices_match_the_live_metered_table(self):
        """The comment in relayshield_api.py names five prices. Pin them."""
        costs = literal_tables(ROOT / "relayshield_api.py", "METERED_CREDIT_COSTS")
        table = costs["METERED_CREDIT_COSTS"]
        expected = {
            "/v1/metered/supply-chain": 10,
            "/v1/metered/asset-intel":  15,
            "/v1/metered/secret-scan":  35,
            "/v1/metered/threat-actor": 30,
            "/v1/metered/session-risk": 30,
        }
        for path, cents in expected.items():
            self.assertEqual(
                table.get(path), cents,
                f"{path} is {table.get(path)} credits, the Bundle B scope says "
                f"{cents}. A direct-Stripe customer pays the path-derived price, so "
                "a drift here is a price we do not honour.")
        self.assertEqual(set(expected), set(self.b),
                         "the priced set and the dimension set disagree")


class TestTheGateRecognisesBundleB(unittest.TestCase):
    """A branch that computes a flag nothing reads is decoration."""

    def setUp(self):
        self.src = code_only((ROOT / "relayshield_api.py").read_text())

    def test_both_branches_exist(self):
        for name in ("is_bundle_b_call", "is_bundle_b_direct_call"):
            self.assertIn(f"{name} = ", self.src, f"{name} is not computed")

    def test_the_402_gate_reads_both(self):
        """Without this a paying customer is refused on every single call."""
        i = self.src.index("402 insufficient credits")
        gate = self.src[max(0, i - 1400):i]
        for name in ("is_bundle_b_call", "is_bundle_b_direct_call"):
            self.assertIn(
                f"not {name}", gate,
                f"the 402 gate does not exempt {name}. A Bundle B customer would be "
                "charged monthly and refused on every call -- the defect that "
                "shipped in Bundle D and was caught pre-launch in Bundle A.")

    def test_the_direct_door_requires_no_aws_customer(self):
        """The discriminator between the two doors, and it decides the rail."""
        i = self.src.index("is_bundle_b_direct_call = ")
        block = self.src[i:i + 400]
        self.assertIn("stripe_customer_id", block)
        # ASSERT THE EXACT NEGATION, NOT THE WORD "not".
        #
        # The first version of this checked `"not " in block`, and proving it by
        # rewriting the condition to `is not None` -- the inversion that bills an
        # AWS customer on both rails -- left the guard GREEN, because "is not
        # None" contains "not ". A substring that the defect also satisfies is
        # not a guard. Found by reintroducing the defect, which is the only way
        # it could have been found.
        self.assertIn(
            'not key_record.get(\'aws_customer_id\')', block,
            "the direct door must require NOT aws_customer_id. Any other form -- "
            "`is not None`, `== \'\'` -- inverts or weakens it, and an AWS "
            "customer then meters to AWS AND bills through Stripe for the same "
            "call.")

    def test_the_aws_door_meters_to_aws_and_the_direct_door_to_stripe(self):
        i = self.src.index("elif is_bundle_b_call:")
        j = self.src.index("elif is_bundle_b_direct_call:")
        aws_branch = self.src[i:j]
        direct_branch = self.src[j:j + 500]
        self.assertIn("_report_marketplace_usage", aws_branch)
        self.assertNotIn("_record_stripe_meter_event", aws_branch,
                         "the AWS door must not also bill Stripe")
        self.assertIn("_record_stripe_meter_event", direct_branch)
        self.assertNotIn("_report_marketplace_usage", direct_branch,
                         "the Stripe door must not also meter AWS")


class TestTheProductCodeStaysInert(unittest.TestCase):
    """Committed before the entity exists, and safe because of this."""

    def test_the_code_is_an_env_var_defaulting_empty(self):
        src = code_only((ROOT / "relayshield_bundle_fulfillment.py").read_text())
        self.assertIn('BUNDLE_B_PRODUCT_CODE = os.environ.get', src)
        self.assertIn("'BUNDLE_B_PRODUCT_CODE', ''", src.replace('"', "'"),
                      "it must default to the empty string; PRODUCT_CODES filters "
                      "empties, which is what makes this file behave exactly as it "
                      "does today until AWS assigns the id")

    def test_it_joins_product_codes(self):
        src = code_only((ROOT / "relayshield_bundle_fulfillment.py").read_text())
        i = src.index("PRODUCT_CODES = ")
        self.assertIn("BUNDLE_B_PRODUCT_CODE", src[i:i + 200],
                      "a product code not in PRODUCT_CODES means the DynamoDB scans "
                      "match nothing for that bundle, silently")


class TestTheTestOfferIsAValidE2EVehicle(unittest.TestCase):
    """The offer AWS's fulfillment verification is performed through.

    It exists to be subscribed to ONCE, by one account, at a price low enough to
    be free and non-zero enough that BatchMeterUsage is genuinely exercised. An
    offer that prices a dimension the product does not have is rejected; one that
    prices none of them proves nothing about metering.
    """

    OFFER = ROOT / "aws_marketplace" / "bundle_b_test_offer.json"

    def setUp(self):
        self.offer = json.loads(self.OFFER.read_text())
        self.dims = changeset_dimensions()

    def _details(self, change_type):
        for c in self.offer["ChangeSet"]:
            if c["ChangeType"] == change_type:
                return c["DetailsDocument"]
        self.fail(f"the offer has no {change_type}")

    def test_every_priced_dimension_exists_on_the_product(self):
        product_keys = {d["Key"] for d in self.dims}
        priced = set()
        for term in self._details("UpdatePricingTerms")["Terms"]:
            for grant in term.get("Grants", []):
                priced.add(grant["DimensionKey"])
            for rc in term.get("RateCards", []):
                for row in rc["RateCard"]:
                    priced.add(row["DimensionKey"])
        missing = priced - product_keys
        self.assertFalse(
            missing,
            f"the offer prices {sorted(missing)}, which the product does not "
            "have. AWS rejects the change set and the reason names a dimension, "
            "not the offer.")

    def test_every_metered_dimension_is_priced_so_metering_is_exercised(self):
        metered = {d["Key"] for d in self.dims
                   if "ExternallyMetered" in d.get("Types", [])}
        priced = {row["DimensionKey"]
                  for term in self._details("UpdatePricingTerms")["Terms"]
                  for rc in term.get("RateCards", [])
                  for row in rc["RateCard"]}
        self.assertEqual(
            metered, priced,
            "a metered dimension the test offer does not price cannot be "
            "exercised during the fulfillment verification, so the E2E test "
            "would pass without proving BatchMeterUsage works for it.")

    def test_the_charge_date_is_not_a_committed_past_date(self):
        """Bundle A's carries 2026-08-08. Copying it ships a rejected offer.

        A payment schedule in the past is refused, and the refusal names the
        schedule rather than the copy-paste, so this is a guard against the
        cheapest possible mistake.
        """
        schedule = self._details("UpdatePaymentScheduleTerms")["Terms"][0]["Schedule"]
        for row in schedule:
            self.assertEqual(
                row["ChargeDate"], "__CHARGE_DATE__",
                "the ChargeDate must stay a placeholder in the committed file. "
                "The submitter fills it at send time and prints the date used.")

    def test_it_targets_exactly_one_buyer_account(self):
        buyers = self._details("UpdateTargeting")["PositiveTargeting"]["BuyerAccounts"]
        self.assertEqual(len(buyers), 1,
                         f"a verification offer targets one test account, got {buyers}")
        self.assertNotIn("239677749008", buyers,
                         "the seller account is not the buyer account")

    def test_the_offer_carries_the_product_id_placeholder(self):
        self.assertEqual(self._details("CreateOffer")["ProductId"],
                         "__BUNDLE_B_PRODUCT_ID__",
                         "the product id is assigned by AWS at CreateProduct time "
                         "and cannot be committed")

    def test_an_unsubstituted_placeholder_is_refused(self):
        with self.assertRaises(sub.Refused) as ctx:
            sub.validate(json.loads(self.OFFER.read_text()))
        self.assertIn("placeholder", str(ctx.exception).lower())

    def test_substitution_makes_it_valid(self):
        doc = sub.substitute(json.loads(self.OFFER.read_text()), "prod-example123")
        changes = sub.validate(doc)
        self.assertEqual(changes[0]["ChangeType"], "CreateOffer")


class TestTheSubmitterRefusesTheDangerousShapes(unittest.TestCase):
    """Every guard exercised as a pure function, no AWS."""

    def base(self):
        return json.loads(CHANGESET.read_text())

    def test_the_real_changeset_validates(self):
        changes = sub.validate(self.base())
        self.assertEqual(len(changes), 5)

    def test_a_live_entity_is_refused(self):
        doc = self.base()
        doc["ChangeSet"][1]["Entity"]["Identifier"] = "prod-kkvurtspreofy"
        with self.assertRaises(sub.Refused) as ctx:
            sub.validate(doc)
        self.assertIn("prod-kkvurtspreofy", str(ctx.exception))

    def test_every_live_entity_is_named_in_the_guard(self):
        """Bundle A is as live as Bundle D and just as replaceable."""
        self.assertIn("prod-f5qkfsxlxs4qg", sub.LIVE_ENTITIES)
        self.assertIn("prod-kkvurtspreofy", sub.LIVE_ENTITIES)

    def test_a_modification_only_changeset_is_refused(self):
        doc = {"Catalog": "AWSMarketplace",
               "ChangeSet": [{"ChangeType": "AddDimensions",
                              "Entity": {"Type": "SaaSProduct@1.0",
                                         "Identifier": "prod-whatever"},
                              "DetailsDocument": []}]}
        with self.assertRaises(sub.Refused):
            sub.validate(doc)

    def test_go_public_validates_on_its_own(self):
        """UpdateVisibility replaces no rate card and is the last create step.

        The first version of the guard refused it, which is a check that forces
        you to skip a legitimate step to pass -- and it named a tool that would
        also have refused it.
        """
        doc = sub.substitute(
            json.loads((ROOT / "aws_marketplace" / "bundle_b_go_public.json").read_text()),
            "prod-example123")
        changes = sub.validate(doc)
        self.assertEqual(changes[0]["ChangeType"], "UpdateVisibility")

    def test_a_visibility_flip_on_a_live_listing_is_still_refused(self):
        """The narrowing must not have opened the case worth refusing."""
        doc = json.loads((ROOT / "aws_marketplace" / "bundle_b_go_public.json").read_text())
        doc["ChangeSet"][0]["Entity"]["Identifier"] = "prod-kkvurtspreofy"
        with self.assertRaises(sub.Refused) as ctx:
            sub.validate(doc)
        self.assertIn("prod-kkvurtspreofy", str(ctx.exception))

    def test_an_empty_changeset_is_refused(self):
        with self.assertRaises(sub.Refused):
            sub.validate({"Catalog": "AWSMarketplace", "ChangeSet": []})

    def test_the_wrong_catalog_is_refused(self):
        doc = self.base()
        doc["Catalog"] = "SomeOtherCatalog"
        with self.assertRaises(sub.Refused):
            sub.validate(doc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
