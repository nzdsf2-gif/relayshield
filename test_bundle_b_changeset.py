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
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
CHANGESET = ROOT / "aws_marketplace" / "bundle_b_create_entity.json"

ENDPOINTS = ["supply-chain", "asset-intel", "secret-scan", "threat-actor", "session-risk"]


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
            self.assertTrue(ident.startswith("$CreateProductChange"),
                            f"{c['ChangeType']} targets {ident!r} rather than the "
                            "product this change set creates")


if __name__ == "__main__":
    unittest.main(verbosity=1)
