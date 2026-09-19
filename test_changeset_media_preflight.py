#!/usr/bin/env python3
"""A media URL is an EXTERNAL RESOURCE. Validating the string validates nothing.

On 2026-09-18 change set de0zvpnvpcq3olta3y7kpx4p2 was submitted, ran fifteen
seconds and came back FAILED:

    INVALID_MEDIA_LOCATION Media location not accessible:
    .../bundle_b/relayshield_logo_bundle_b.png

The URL was produced by substituting bundle_a -> bundle_b in a path copied out
of Bundle A's ACCEPTED change set, and the object had never been uploaded.
Six guards on that document were green, because every one of them checked the
document. `curl -I` settles it in one second:

    bundle_a/relayshield_logo_bundle_a.png   200
    bundle_b/relayshield_logo_bundle_b.png   403

A public S3 bucket with no ListBucket answers 403 for an object that is not
there rather than 404, so the two codes are ONE finding.
"""
import ast
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "submit", ROOT / "tools" / "marketplace_submit_changeset.py")
SUBMIT = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SUBMIT)

BUNDLE_B = ROOT / "aws_marketplace" / "bundle_b_create_entity.json"


def doc_with(url: str) -> dict:
    return {"ChangeSet": [{"DetailsDocument": {"LogoUrl": url}}]}


class ItFindsTheFieldsAwsFetches(unittest.TestCase):

    def test_it_finds_a_logo_url_with_its_key_path(self):
        found = SUBMIT.media_urls(doc_with("https://example.com/a.png"))
        self.assertEqual(
            found, [("ChangeSet[0].DetailsDocument.LogoUrl",
                     "https://example.com/a.png")])

    def test_it_ignores_urls_aws_never_dereferences(self):
        """Usage instructions carry api.relayshield.net and a docs link. Probing
        those would turn an unrelated outage into a refusal to submit."""
        doc = {"ChangeSet": [{"DetailsDocument": {
            "UsageInstructions": "Base URL\nhttps://api.relayshield.net",
            "SupportDescription": "see https://api.relayshield.net/developers"}}]}
        self.assertEqual(SUBMIT.media_urls(doc), [])

    def test_the_committed_bundle_b_changeset_declares_exactly_one(self):
        doc = json.loads(BUNDLE_B.read_text(encoding="utf-8"))
        found = SUBMIT.media_urls(doc)
        self.assertEqual(len(found), 1, f"expected one media url, got {found}")


class ItBlocksOnlyOnAnUnambiguousAnswer(unittest.TestCase):
    """The repo rule: a probe that cannot tell must not block. A preflight that
    refuses to submit because S3 was briefly slow is worse than the defect it
    guards, because it stands between finished work and its submission."""

    def test_403_and_404_both_refuse(self):
        for code in (403, 404):
            with self.assertRaises(SystemExit) as caught:
                SUBMIT.check_media(doc_with("https://example.com/x.png"),
                                   probe=lambda u, c=code: ("MISSING", f"HTTP {c}"))
            self.assertIn("INVALID_MEDIA_LOCATION", str(caught.exception))

    def test_a_timeout_warns_and_continues(self):
        SUBMIT.check_media(doc_with("https://example.com/x.png"),
                           probe=lambda u: ("UNKNOWN", "TimeoutError"))

    def test_a_5xx_warns_and_continues(self):
        SUBMIT.check_media(doc_with("https://example.com/x.png"),
                           probe=lambda u: ("UNKNOWN", "HTTP 503"))

    def test_200_passes(self):
        SUBMIT.check_media(doc_with("https://example.com/x.png"),
                           probe=lambda u: ("OK", "HTTP 200"))

    def test_a_document_with_no_media_is_not_a_failure(self):
        SUBMIT.check_media({"ChangeSet": [{"DetailsDocument": {"Title": "x"}}]})


class TheProbeMapsStatusCodes(unittest.TestCase):
    """403 and 404 are one finding. Defect B -- narrowing this to 404 alone --
    changed the live verdict on the real URL from MISSING to UNKNOWN and no
    test noticed, so the mapping is pinned here without a network."""

    def _probe_raising(self, code):
        import urllib.error
        import urllib.request
        real = urllib.request.urlopen

        def fake(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, code, "no", {}, None)

        urllib.request.urlopen = fake
        try:
            return SUBMIT.probe_media("https://example.com/x.png")
        finally:
            urllib.request.urlopen = real

    def test_403_is_missing_because_s3_hides_absence_behind_it(self):
        self.assertEqual(self._probe_raising(403)[0], "MISSING")

    def test_404_is_missing(self):
        self.assertEqual(self._probe_raising(404)[0], "MISSING")

    def test_500_is_unknown_and_therefore_does_not_block(self):
        self.assertEqual(self._probe_raising(500)[0], "UNKNOWN")


class TheDryRunRunsIt(unittest.TestCase):
    """A dry run that skips the one check AWS failed on is checking a different
    document from the one that ships."""

    def _assert_unconditional(self, func_name):
        """Asserted with ast, because the first version of this guard was a
        substring-index comparison and the mutation that moves the call INSIDE
        the dry-run branch preserves textual order. It passed on the defect.
        A substring the defect also satisfies is not a guard.

        The property is not "before the return", it is "not nested in any
        branch": nested under `if not args.apply` the dry run would check and
        an APPLY would not, which is the dangerous half.
        """
        src = (ROOT / "tools" / "marketplace_submit_changeset.py").read_text(
            encoding="utf-8")
        main = next(n for n in ast.walk(ast.parse(src))
                    if isinstance(n, ast.FunctionDef) and n.name == "main")

        top_level = [
            i for i, stmt in enumerate(main.body)
            if any(isinstance(sub, ast.Call)
                   and getattr(sub.func, "id", "") == func_name
                   for sub in ast.walk(stmt))
            and not isinstance(stmt, (ast.If, ast.Try, ast.For, ast.While))
        ]
        self.assertEqual(
            len(top_level), 1,
            f"{func_name} must be called exactly once, at the top level of "
            "main(). Nested in a branch it runs on some paths and not others, "
            "and the path it would skip is --apply.")

        returns = [i for i, stmt in enumerate(main.body)
                   if isinstance(stmt, ast.If)
                   and any(isinstance(sub, ast.Return) for sub in ast.walk(stmt))]
        self.assertTrue(returns, "main() has no conditional return to order against")
        self.assertLess(top_level[0], min(returns),
                        f"{func_name} must run before the first branch that can "
                        "return, or a dry run checks a different document from "
                        "the one an apply sends")

    def test_check_media_runs_unconditionally_in_main(self):
        self._assert_unconditional("check_media")

    def test_check_pricing_runs_unconditionally_in_main(self):
        self._assert_unconditional("check_pricing")


class ItBlocksADimensionWithNoPrice(unittest.TestCase):
    """Change set 17or75a96xofiu7gic33wjrm6 passed the media preflight added
    hours earlier and failed anyway:

        INVALID_INPUT When adding dimensions for SaaS products, you must also
        set pricing for usage dimensions.

    Five changes where Bundle A's accepted set has thirteen. The pricing half
    of the document was absent, so nothing that read the document could see it.
    """

    PRICED = {
        "ChangeSet": [
            {"ChangeType": "AddDimensions",
             "DetailsDocument": [{"Key": "a_calls", "Types": ["ExternallyMetered"]},
                                 {"Key": "bundle_access", "Types": ["Entitled"]}]},
            {"ChangeType": "UpdatePricingTerms",
             "DetailsDocument": {"Terms": [
                 {"Type": "UsageBasedPricingTerm",
                  "RateCards": [{"RateCard": [{"DimensionKey": "a_calls",
                                               "Price": "0.10"}]}]},
                 {"Type": "ConfigurableUpfrontPricingTerm",
                  "RateCards": [{"RateCard": [{"DimensionKey": "bundle_access",
                                               "Price": "100"}]}]}]}},
        ]
    }

    def test_a_fully_priced_change_set_passes(self):
        SUBMIT.check_pricing(self.PRICED)

    def test_the_document_aws_refused_is_refused_here(self):
        doc = {"ChangeSet": [self.PRICED["ChangeSet"][0]]}
        with self.assertRaises(SystemExit) as ctx:
            SUBMIT.check_pricing(doc)
        self.assertIn("INVALID_INPUT", str(ctx.exception))
        self.assertIn("a_calls", str(ctx.exception))

    def test_one_unpriced_dimension_among_priced_ones_still_blocks(self):
        doc = json.loads(json.dumps(self.PRICED))
        doc["ChangeSet"][0]["DetailsDocument"].append(
            {"Key": "b_calls", "Types": ["ExternallyMetered"]})
        with self.assertRaises(SystemExit) as ctx:
            SUBMIT.check_pricing(doc)
        self.assertIn("b_calls", str(ctx.exception))

    def test_a_price_for_a_dimension_that_does_not_exist_blocks(self):
        """A rate card naming a key no dimension declares is a price nothing
        can bill -- the silent direction of the same disagreement."""
        doc = json.loads(json.dumps(self.PRICED))
        (doc["ChangeSet"][1]["DetailsDocument"]["Terms"][0]
            ["RateCards"][0]["RateCard"]).append(
                {"DimensionKey": "typo_calls", "Price": "0.10"})
        with self.assertRaises(SystemExit) as ctx:
            SUBMIT.check_pricing(doc)
        self.assertIn("typo_calls", str(ctx.exception))

    def test_a_change_set_with_no_dimensions_is_not_this_check_s_business(self):
        """UpdateVisibility and the test offer add no dimensions. A guard that
        fires on them is one that gets skipped."""
        SUBMIT.check_pricing({"ChangeSet": [{"ChangeType": "UpdateVisibility",
                                          "DetailsDocument": {}}]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
