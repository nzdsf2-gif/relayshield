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

    def test_check_field_limits_runs_unconditionally_in_main(self):
        self._assert_unconditional("check_field_limits")


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


class ItBlocksAFieldOverALimitAwsEnforces(unittest.TestCase):
    """The FIFTH failed change set, em3sw5gs00lifcmy42mxe95t9, 2026-09-19:

        INVALID_INPUT Remove invalid key 'supply_chain_calls' with types
        '[Metered, ExternallyMetered]'. Valid descriptions cannot exceed more
        than 90 characters.

    Four of six descriptions were over. Media passed, pricing passed, eleven
    document guards passed. Five submissions, five different validations none
    of our checks knew about -- which is the defect, rather than any one of
    the five.
    """

    def doc(self, description):
        return {"ChangeSet": [{
            "ChangeType": "AddDimensions",
            "DetailsDocument": [{"Key": "a_calls", "Name": "A",
                                 "Description": description, "Unit": "Units",
                                 "Types": ["ExternallyMetered"]}]}]}

    def test_a_90_character_description_passes(self):
        SUBMIT.check_field_limits(self.doc("x" * 90), reference=None)

    def test_a_91_character_description_is_refused(self):
        with self.assertRaises(SystemExit) as ctx:
            SUBMIT.check_field_limits(self.doc("x" * 91), reference=None)
        self.assertIn("AddDimensions[].Description", str(ctx.exception))
        self.assertIn("91 > 90", str(ctx.exception))

    def test_the_refusal_names_where_the_limit_came_from(self):
        """A limit nobody can source is a limit the next session deletes."""
        with self.assertRaises(SystemExit) as ctx:
            SUBMIT.check_field_limits(self.doc("x" * 120), reference=None)
        self.assertIn("em3sw5gs00lifcmy42mxe95t9", str(ctx.exception))

    def test_the_committed_bundle_b_change_set_is_within_every_limit(self):
        SUBMIT.check_field_limits(json.loads(BUNDLE_B.read_text(encoding="utf-8")))

    def test_the_document_aws_refused_is_refused_here(self):
        """The exact four descriptions, restored from the submitted version."""
        doc = json.loads(BUNDLE_B.read_text(encoding="utf-8"))
        dims = next(c for c in doc["ChangeSet"]
                    if c["ChangeType"] == "AddDimensions")["DetailsDocument"]
        for d in dims:
            if d["Key"] == "secret_scan_calls":
                d["Description"] = ("Detects live credentials in public artifacts "
                                    "across six sources, including code hosts and "
                                    "package registries.")
        with self.assertRaises(SystemExit) as ctx:
            SUBMIT.check_field_limits(doc)
        self.assertIn("109 > 90", str(ctx.exception))


class ItComparesEveryFieldAgainstTheAcceptedSet(unittest.TestCase):
    """A class path collapses list indices, so every dimension Description is
    ONE field rather than six. Comparing by INDEX against another product pairs
    'Breach Exposure Check' with 'Supply Chain Exposure Check' and reports the
    difference as a finding, which is a guard nobody can act on."""

    def test_indices_collapse_into_one_class(self):
        classes = SUBMIT.field_classes({"ChangeSet": [{
            "ChangeType": "AddDimensions",
            "DetailsDocument": [{"Description": "a"}, {"Description": "bb"}]}]})
        self.assertEqual(classes["AddDimensions[].Description"], ["a", "bb"])

    def test_over_reference_reports_and_does_not_block(self):
        """The repo rule: a probe that cannot tell must not block. 'Longer than
        one accepted example' is not a known constraint."""
        doc = json.loads(BUNDLE_B.read_text(encoding="utf-8"))
        info = next(c for c in doc["ChangeSet"]
                    if c["ChangeType"] == "UpdateInformation"
                    and "ProductTitle" in c["DetailsDocument"])
        info["DetailsDocument"]["ProductTitle"] = "R" * 400
        SUBMIT.check_field_limits(doc)          # must not raise

    def test_an_offer_change_set_is_not_measured_against_a_create_set(self):
        """bundle_b_test_offer.json creates no product. Comparing its fields
        with a create set's would report every absent field as a difference."""
        SUBMIT.check_field_limits({"ChangeSet": [
            {"ChangeType": "UpdateVisibility", "DetailsDocument": {"x": "y"}}]})


class AConfirmationIsChosenNotTyped(unittest.TestCase):
    """2026-09-19: an apply was refused because CREATE-NEW_PRODUCT was typed
    for CREATE-NEW-PRODUCT. One underscore, invisible at a glance, in an
    18-character string with mixed punctuation.

    The guard fired correctly and the round was still spent, which is the point:
    a confirmation that CAN be mistyped WILL be, and the cost lands on the
    reader rather than on whoever chose a free-text box. A dropdown keeps the
    whole safety property -- the dangerous value is not the default and must be
    selected deliberately -- and removes the keyboard from the path.
    """

    def _inputs(self, name):
        import yaml
        wf = yaml.safe_load(
            (ROOT / ".github" / "workflows" / f"{name}.yml").read_text(encoding="utf-8"))
        return wf[True]["workflow_dispatch"]["inputs"]

    def test_the_create_confirmation_is_a_choice(self):
        field = self._inputs("marketplace_changeset")["confirm"]
        self.assertEqual(field["type"], "choice",
                         "a typed confirmation phrase is one keystroke from a "
                         "wasted round; make it a dropdown")
        self.assertIn("CREATE-NEW-PRODUCT", field["options"])

    def test_the_dangerous_value_is_not_the_default(self):
        """A dropdown that defaults to the confirmation is not a confirmation."""
        for name, key in (("marketplace_changeset", "confirm"),
                          ("marketplace_dimension", "confirm_entity")):
            field = self._inputs(name)[key]
            self.assertEqual(field.get("default", ""), "",
                             f"{name}.{key} defaults to a live value")

    def test_the_dimension_confirmation_is_a_choice_of_real_entities(self):
        field = self._inputs("marketplace_dimension")["confirm_entity"]
        self.assertEqual(field["type"], "choice")
        self.assertIn("prod-kkvurtspreofy", field["options"])


class AHandTypedProductIdIsValidatedBeforeUse(unittest.TestCase):
    """`product_id` cannot be a dropdown, because AWS assigns new ids. So it
    gets the other half: a shape check that reproduces AWS's refusal in zero
    seconds, and the `@1` revision stripped, because the value a reader copies
    out of the create run carries it and both DescribeEntity and a change set
    refuse it."""

    def test_a_revision_suffix_is_stripped(self):
        self.assertEqual(SUBMIT.clean_product_id("prod-szi2wdww3obry@1"),
                         "prod-szi2wdww3obry")

    def test_surrounding_whitespace_is_stripped(self):
        self.assertEqual(SUBMIT.clean_product_id("  prod-szi2wdww3obry  "),
                         "prod-szi2wdww3obry")

    def test_empty_is_allowed_because_a_create_set_needs_none(self):
        self.assertEqual(SUBMIT.clean_product_id(""), "")

    def test_a_wrong_shape_is_refused_locally(self):
        for bad in ("prod_szi2wdww3obry", "PROD-SZI2WDWW3OBRY", "szi2wdww3obry"):
            with self.assertRaises(SUBMIT.Refused, msg=f"{bad} was accepted"):
                SUBMIT.clean_product_id(bad)

    def test_the_cleaner_runs_before_substitution(self):
        """Read the CALL SITE: a validator nothing calls is decoration."""
        src = (ROOT / "tools" / "marketplace_submit_changeset.py").read_text(
            encoding="utf-8")
        main = next(n for n in ast.walk(ast.parse(src))
                    if isinstance(n, ast.FunctionDef) and n.name == "main")
        order = []
        for node in ast.walk(main):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "id", "")
                if name in ("clean_product_id", "substitute"):
                    order.append((node.lineno, name))
        order.sort()
        names = [n for _, n in order]
        self.assertIn("clean_product_id", names,
                      "main() never validates --product-id")
        self.assertLess(names.index("clean_product_id"), names.index("substitute"),
                        "the id is substituted into the document before it is "
                        "checked, so a bad value reaches AWS")


class TheReferenceIsChosenByShape(unittest.TestCase):
    """The first version hard-wired bundle_a_create_entity.json, so the TEST
    OFFER and GO-PUBLIC sets -- the two documents that follow the create -- were
    compared against nothing and printed no field table at all.

    That is the same gap that let four over-length descriptions through: the
    comparison existed and did not reach the document being sent. Running it
    against the test offer immediately found an over-length offer Description.
    """

    def _doc(self, name):
        return json.loads((ROOT / "aws_marketplace" / f"{name}.json").read_text())

    def test_a_create_set_picks_bundle_a_s_create_set(self):
        got = SUBMIT.pick_reference(self._doc("bundle_b_create_entity"))
        self.assertEqual(got.name, "bundle_a_create_entity.json")

    def test_a_test_offer_picks_bundle_a_s_test_offer(self):
        got = SUBMIT.pick_reference(self._doc("bundle_b_test_offer"))
        self.assertEqual(got.name, "bundle_a_test_offer.json")

    def test_a_go_public_set_picks_bundle_a_s_go_public(self):
        got = SUBMIT.pick_reference(self._doc("bundle_b_go_public"))
        self.assertEqual(got.name, "bundle_a_go_public.json")

    def test_an_unknown_shape_gets_no_reference_rather_than_a_wrong_one(self):
        self.assertIsNone(SUBMIT.pick_reference(
            {"ChangeSet": [{"ChangeType": "SomethingNobodyHasSent"}]}))

    def test_check_field_limits_actually_calls_it(self):
        """Proven necessary: reverting the selection to REFERENCES[0] left
        every test above GREEN, because they call pick_reference directly.
        A chooser nothing consults is decoration -- the same shape as a guard
        nothing calls, which this repo has now paid for three times."""
        src = (ROOT / "tools" / "marketplace_submit_changeset.py").read_text(
            encoding="utf-8")
        func = next(n for n in ast.walk(ast.parse(src))
                    if isinstance(n, ast.FunctionDef) and n.name == "check_field_limits")
        calls = [getattr(n.func, "id", "") for n in ast.walk(func)
                 if isinstance(n, ast.Call)]
        self.assertIn("pick_reference", calls,
                      "check_field_limits does not choose its reference by "
                      "shape, so it compares every document against one file")

    def test_every_bundle_b_document_has_an_accepted_counterpart(self):
        """A document with no reference is one nothing can vet. Today all three
        have one, and this fails the day a fourth is added without its own
        accepted example -- which is the moment to notice, not after AWS says
        so."""
        for name in ("bundle_b_create_entity", "bundle_b_test_offer",
                     "bundle_b_go_public"):
            self.assertIsNotNone(SUBMIT.pick_reference(self._doc(name)),
                                 f"{name} has no accepted Bundle A counterpart")


class ADateInThePastIsRefused(unittest.TestCase):
    """bundle_a_test_offer.json carries ChargeDate 2026-08-08 AND
    AvailabilityEndDate 2026-09-06. Both were correct on the day it was
    submitted. Bundle B was built by reusing that envelope, ChargeDate was
    turned into a placeholder and the availability date was NOT -- half the
    fix, which is the shape of every Bundle B failure so far.

    A past date BLOCKS rather than warning, and the distinction is the one
    check_media draws: a timeout means the probe could not tell, while a date
    before today cannot become valid by waiting.
    """

    TODAY = "2026-09-19"

    def _doc(self, value, key="AvailabilityEndDate"):
        return {"ChangeSet": [{"DetailsDocument": {key: value}}]}

    def test_a_past_date_is_refused(self):
        with self.assertRaises(SystemExit) as caught:
            SUBMIT.check_dates(self._doc("2026-09-06"), today=self.TODAY)
        self.assertIn("2026-09-06", str(caught.exception))
        self.assertIn("AvailabilityEndDate", str(caught.exception))

    def test_today_and_the_future_pass(self):
        SUBMIT.check_dates(self._doc(self.TODAY), today=self.TODAY)
        SUBMIT.check_dates(self._doc("2026-12-18"), today=self.TODAY)

    def test_a_past_charge_date_is_refused_too(self):
        with self.assertRaises(SystemExit):
            SUBMIT.check_dates(self._doc("2026-08-08", key="ChargeDate"),
                               today=self.TODAY)

    def test_a_version_that_looks_like_a_date_is_left_alone(self):
        """The standard EULA term carries Version 2022-07-14, which is a
        document version and is correct as it stands. A guard that forces you
        to change a true value to go green is one that gets loosened."""
        SUBMIT.check_dates(
            {"ChangeSet": [{"DetailsDocument": {"Documents": [
                {"Type": "StandardEula", "Version": "2022-07-14"}]}}]},
            today=self.TODAY)

    def test_the_committed_test_offer_carries_no_literal_date(self):
        """The defect itself: a date written into the file is right for one day.
        Every date in a committed Bundle B change set is a placeholder."""
        for name in ("bundle_b_create_entity", "bundle_b_test_offer",
                     "bundle_b_go_public"):
            doc = json.loads(
                (ROOT / "aws_marketplace" / f"{name}.json").read_text())
            for path, value in SUBMIT.date_fields(doc):
                self.fail(f"{name} commits a literal date: {path} = {value}. "
                          "Make it a __PLACEHOLDER__ filled in substitute().")

    def test_substitution_fills_both_dates_in_the_future(self):
        doc = json.loads(
            (ROOT / "aws_marketplace" / "bundle_b_test_offer.json").read_text())
        filled = SUBMIT.substitute(doc, "prod-szi2wdww3obry")
        found = dict((p.rsplit(".", 1)[-1], v)
                     for p, v in SUBMIT.date_fields(filled))
        self.assertIn("ChargeDate", found)
        self.assertIn("AvailabilityEndDate", found)
        SUBMIT.check_dates(filled)
        self.assertGreater(found["AvailabilityEndDate"], found["ChargeDate"],
                           "the offer expires on or before it is charged")

    def test_main_actually_calls_it(self):
        """A guard nothing calls is decoration, and it has to run at the top
        level of main() -- nested in the dry-run branch it would check the one
        document that is never sent."""
        src = (ROOT / "tools" / "marketplace_submit_changeset.py").read_text(
            encoding="utf-8")
        func = next(n for n in ast.walk(ast.parse(src))
                    if isinstance(n, ast.FunctionDef) and n.name == "main")
        top = [n for n in func.body if isinstance(n, ast.Expr)
               and isinstance(n.value, ast.Call)
               and getattr(n.value.func, "id", "") == "check_dates"]
        self.assertEqual(len(top), 1,
                         "check_dates is not called exactly once at the top "
                         "level of main(), so it may not see what is sent")


if __name__ == "__main__":
    unittest.main(verbosity=2)
