#!/usr/bin/env python3
"""Guards on the Bundle B create-entity change set.

Three things have to hold before this is ever submitted, and each of them has
cost this programme a real AWS review cycle on Bundle D:

1. NO CORPUS COUNTS. A public listing carries only claims that stay true without
   maintenance -- naming the SOURCES, never the totals. Bundle D quoted
   "5.0M+ indicators" in three places and needed a change set to stay honest.
2. NO EXTERNAL PAYMENT PAGE. AWS's Tier-1 audit treats a reachable link to an
   external payment page as a violation, and that failed Bundle D's visibility
   request twice.
3. THE DIMENSION KEYS MATCH THE ENDPOINTS. A dimension whose key does not map to
   a metered path bills nothing and looks correct.

No AWS, no boto3. It reads the committed artefact.
"""
import ast
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
CHANGESET = ROOT / "aws_marketplace" / "bundle_b_create_entity.json"

BUNDLE_A = ROOT / "aws_marketplace" / "bundle_a_create_entity.json"

ENDPOINTS = ["supply-chain", "asset-intel", "secret-scan", "threat-actor", "session-risk"]


def _api_table(name):
    """Read a dict literal out of relayshield_api.py without importing it.

    Importing pulls boto3 and a live credential chain into a test that needs
    neither, and retyping the numbers here is the two-files-must-agree defect
    this file exists to catch.
    """
    tree = ast.parse((ROOT / "relayshield_api.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Name) and t.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is not in relayshield_api.py")


def bundle_b_dimensions():
    return _api_table("BUNDLE_B_DIMENSION_NAMES")


def metered_credit_costs():
    return _api_table("METERED_CREDIT_COSTS")


def _pricing_terms():
    doc = json.loads(CHANGESET.read_text(encoding="utf-8"))
    change = [c for c in doc["ChangeSet"] if c["ChangeType"] == "UpdatePricingTerms"]
    assert len(change) == 1, f"expected one UpdatePricingTerms, got {len(change)}"
    return change[0]["DetailsDocument"]["Terms"]


def _card(term_type):
    out = {}
    for term in _pricing_terms():
        if term["Type"] != term_type:
            continue
        for rc in term["RateCards"]:
            for row in rc["RateCard"]:
                out[row["DimensionKey"]] = row["Price"]
    return out


def rate_card():
    """Per-call prices, keyed by dimension."""
    return _card("UsageBasedPricingTerm")


def upfront_card():
    """The monthly minimum, keyed by dimension."""
    return _card("ConfigurableUpfrontPricingTerm")


def prose() -> str:
    """Every buyer-visible string in the change set, joined."""
    doc = json.loads(CHANGESET.read_text(encoding="utf-8"))
    out = []

    def walk(node):
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(doc)
    return "\n".join(out)


class TestBundleBListingCopy(unittest.TestCase):
    def test_it_quotes_no_corpus_count(self):
        """MEASUREMENT DOCTRINE on a page we cannot cheaply edit. The patterns
        are shapes rather than the specific stale figures, because the next
        wrong number will be a different number."""
        text = prose()
        bad = re.findall(
            r"\b\d[\d,.]*\s*(?:M|K|million|thousand)\+?\s+"
            r"(?:indicators|IOCs|records|credentials|sightings|malware families)",
            text, re.I)
        bad += re.findall(r"\b\d[\d,]*\+?\s+(?:monitored\s+)?(?:criminal\s+)?"
                          r"(?:Telegram\s+)?(?:marketplaces|channels)\b", text, re.I)
        self.assertEqual(bad, [], f"the listing quotes a corpus count: {bad}")

    def test_it_names_the_sources_instead(self):
        text = prose().lower()
        for source in ("criminal telegram", "infostealer", "public indicator feeds"):
            self.assertIn(source, text,
                          f"the copy must name its sources; {source!r} is missing")

    def test_no_external_payment_page(self):
        """The Tier-1 violation that failed Bundle D's visibility request twice."""
        text = prose().lower()
        for bad in ("stripe.com", "buy.stripe", "checkout.", "add a card",
                    "payment link"):
            self.assertNotIn(bad, text,
                             f"{bad!r} is an external payment route in a listing "
                             "AWS audits for exactly that")
        self.assertIn("all billing is handled by aws marketplace", text,
                      "the usage instructions must say outright that AWS bills, "
                      "which is what the audit looks for")

    def test_the_dimensions_match_the_endpoints(self):
        doc = json.loads(CHANGESET.read_text(encoding="utf-8"))
        dims = next(c for c in doc["ChangeSet"]
                    if c["ChangeType"] == "AddDimensions")["DetailsDocument"]
        keys = {d["Key"] for d in dims}

        entitled = [d for d in dims if d["Types"] == ["Entitled"]]
        self.assertEqual(len(entitled), 1,
                         "exactly one Entitled dimension carries the monthly minimum; "
                         "dropping it is the 2026-07-27 placeholder failure")

        for ep in ENDPOINTS:
            expected = ep.replace("-", "_") + "_calls"
            self.assertIn(expected, keys,
                          f"{ep} has no dimension, so its calls bill nothing")

        metered = {d["Key"] for d in dims if d["Types"] == ["ExternallyMetered"]}
        self.assertEqual(len(metered), len(ENDPOINTS),
                         "a metered dimension with no endpoint, or the reverse")

    def test_every_endpoint_is_reachable_and_documented(self):
        """A usage instruction naming a path the API does not serve is a buyer
        following a 404. Read from relayshield_api.py, not asserted."""
        api = (ROOT / "relayshield_api.py").read_text(encoding="utf-8")
        text = prose()
        for ep in ENDPOINTS:
            path = f"/v1/metered/{ep}"
            self.assertIn(f'"{path}"', api, f"{path} is not in the API")
            self.assertIn(path, text, f"{path} is not documented in the listing")

    def test_it_creates_its_own_entity(self):
        """Bundle B is a SEPARATE SaaSProduct, like Bundle A. Targeting an
        existing entity would replace that product's whole rate card, which
        rolled Bundle D's prices back to placeholders once already."""
        doc = json.loads(CHANGESET.read_text(encoding="utf-8"))
        types = [c["ChangeType"] for c in doc["ChangeSet"]]
        self.assertEqual(types[0], "CreateProduct")
        for c in doc["ChangeSet"][1:]:
            ident = c["Entity"].get("Identifier", "")
            if not ident:
                continue      # CreateOffer names no entity; AWS assigns it
            self.assertTrue(ident.startswith(("$CreateProductChange",
                                              "$CreateOfferChange")),
                            f"{c['ChangeType']} targets {ident!r} rather than the "
                            "product or offer this change set creates")


class TestItIsAWholeSubmission(unittest.TestCase):
    """The defect this class exists for: the first version of this change set
    carried FIVE changes and Bundle A's accepted one carries THIRTEEN.

    It was built by "reading Bundle A's change set and reusing its envelope",
    which was the right method pointed at part of the artefact -- I stopped at
    AddDimensions and never read the offer half below it. AWS answered:

        INVALID_INPUT When adding dimensions for SaaS products, you must also
        set pricing for usage dimensions.

    Six guards were green throughout, because every one of them read the
    document that was there rather than asking what a COMPLETE one looks like.
    Bundle A's file is the only accepted example we have, so it is the
    expectation, exactly as its envelope was.
    """

    def types(self, path):
        doc = json.loads(path.read_text(encoding="utf-8"))
        return [c["ChangeType"] for c in doc["ChangeSet"]]

    def test_it_has_the_same_change_types_as_the_accepted_bundle_a_set(self):
        self.assertEqual(self.types(CHANGESET), self.types(BUNDLE_A),
                         "Bundle A's change set is the one AWS accepted. A "
                         "difference here is a missing step, not a style choice")

    def test_a_product_with_dimensions_carries_pricing_for_them(self):
        """The literal text of the AWS error, as a property."""
        doc = json.loads(CHANGESET.read_text(encoding="utf-8"))
        dims = next(c for c in doc["ChangeSet"]
                    if c["ChangeType"] == "AddDimensions")["DetailsDocument"]
        metered = {d["Key"] for d in dims if d["Types"] == ["ExternallyMetered"]}
        entitled = {d["Key"] for d in dims if d["Types"] == ["Entitled"]}

        priced = rate_card()
        self.assertEqual(metered, set(priced),
                         "every metered dimension needs a price and every price "
                         "needs a dimension")
        self.assertEqual(entitled, set(upfront_card()),
                         "the Entitled dimension carries the monthly minimum")

    def test_the_rate_card_agrees_with_what_the_api_actually_bills(self):
        """Two tables that must agree, with nothing checking them until now.
        A listing price above what we meter is a price we do not honour; below
        it, we bill AWS buyers less than everyone else and nothing raises."""
        priced = rate_card()
        for path, key in bundle_b_dimensions().items():
            cents = metered_credit_costs()[path]
            self.assertEqual(priced[key], f"{cents / 100:.2f}",
                             f"{key} is listed at {priced[key]} and billed at "
                             f"{cents / 100:.2f} by {path}")

    def test_the_monthly_minimum_is_the_one_the_repo_records(self):
        """$100/mo, from relayshield_api.py's own Bundle B comment. A number in
        a public artefact is read out of the code that defines it."""
        api = (ROOT / "relayshield_api.py").read_text(encoding="utf-8")
        self.assertIn("$100/mo minimum", api,
                      "relayshield_api.py no longer records Bundle B's minimum; "
                      "this guard has lost its source of truth")
        self.assertEqual(upfront_card()["attack_surface_bundle_access"], "100")

    def test_no_literal_entity_id_appears_anywhere(self):
        """A hardcoded prod-... would point the offer at a LIVE product and
        replace its rate card. Bundles A and D are both public."""
        found = re.findall(r"prod-[a-z0-9]+", CHANGESET.read_text(encoding="utf-8"))
        self.assertEqual(found, [], f"literal entity id in the change set: {found}")

    def field_classes(self, path):
        """Every field in the document, with list indices collapsed."""
        out = set()

        def walk(node, prefix):
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, f"{prefix}.{key}" if prefix else key)
            elif isinstance(node, list):
                for value in node:
                    walk(value, f"{prefix}[]")
            else:
                out.add(prefix)

        for change in json.loads(path.read_text(encoding="utf-8"))["ChangeSet"]:
            walk(change.get("DetailsDocument"), change.get("ChangeType", "?"))
        return out

    def test_every_field_the_accepted_set_carries_is_present_here(self):
        """The ChangeType sequence above says the same CHANGES are present.
        This says the same FIELDS are, which is the question that was never
        asked across five refused submissions: a document can carry all
        thirteen changes and still be missing a key inside one of them, and
        nothing that reads only this document can see an absence."""
        mine = self.field_classes(CHANGESET)
        accepted = self.field_classes(BUNDLE_A)
        self.assertEqual(
            accepted - mine, set(),
            "fields AWS accepted in Bundle A that Bundle B does not carry")
        self.assertEqual(
            mine - accepted, set(),
            "fields Bundle B carries that no accepted change set has. They may "
            "be fine; nothing in this repo has evidence that they are")

    def test_no_dimension_description_exceeds_ninety_characters(self):
        """The fifth refusal, em3sw5gs00lifcmy42mxe95t9, in the artefact rather
        than in the submitter: 'Valid descriptions cannot exceed more than 90
        characters'. A guard in the tool protects the submission path; a guard
        here protects the file from being edited back over the line."""
        doc = json.loads(CHANGESET.read_text(encoding="utf-8"))
        dims = next(c for c in doc["ChangeSet"]
                    if c["ChangeType"] == "AddDimensions")["DetailsDocument"]
        over = [(d["Key"], len(d["Description"])) for d in dims
                if len(d["Description"]) > 90]
        self.assertEqual(over, [], f"dimension descriptions over 90: {over}")



class DuplicateBundleBEntities(unittest.TestCase):
    """Three SaaS products carry the Bundle B display name (measured 2026-09-22).

    Seven visibility requests were refused because the Management Portal selects
    by NAME and the wrong row was submitted. The guard is narrow on purpose: only
    TargetVisibility Public is refused, so withdrawing a duplicate still works.
    """

    def _submit(self, product_id, visibility="Public"):
        import subprocess, tempfile, json as _json, os
        doc = _json.loads(
            (ROOT / "aws_marketplace" / "bundle_b_go_public.json").read_text())
        doc["ChangeSet"][0]["DetailsDocument"]["TargetVisibility"] = visibility
        fd, path = tempfile.mkstemp(suffix=".json",
                                    dir=str(ROOT / "aws_marketplace"))
        try:
            with os.fdopen(fd, "w") as fh:
                _json.dump(doc, fh)
            return subprocess.run(
                [sys.executable, str(ROOT / "tools" /
                                     "marketplace_submit_changeset.py"),
                 path, "--product-id", product_id],
                capture_output=True, text=True)
        finally:
            os.unlink(path)

    def test_publishing_a_duplicate_is_refused_and_names_the_real_one(self):
        for dup in ("prod-v5nr5gjtdnofi", "prod-p3ei5nmgufnnq"):
            with self.subTest(dup=dup):
                r = self._submit(dup)
                self.assertNotEqual(r.returncode, 0,
                                    f"{dup} was NOT refused")
                self.assertIn("REFUSED", r.stdout + r.stderr)
                self.assertIn("prod-szi2wdww3obry", r.stdout + r.stderr,
                              "the refusal must name the entity to use instead")

    def test_publishing_the_real_entity_is_allowed(self):
        r = self._submit("prod-szi2wdww3obry")
        self.assertEqual(r.returncode, 0,
                         f"the real Bundle B entity was refused:\n{r.stdout}")

    def test_withdrawing_a_duplicate_is_allowed(self):
        """A guard that blocks the cleanup step is one that gets loosened."""
        r = self._submit("prod-v5nr5gjtdnofi", visibility="Restricted")
        self.assertEqual(r.returncode, 0,
                         f"withdrawing a duplicate was refused:\n{r.stdout}")


if __name__ == "__main__":
    unittest.main(verbosity=1)
