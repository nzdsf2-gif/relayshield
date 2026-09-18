#!/usr/bin/env python3
"""An AWS Marketplace ENTITY ID is not a PRODUCT CODE, and three places in this
repo said it was until 2026-09-18.

    tools/marketplace_submit_changeset.py   printed it as advice on success
    bundle_b_launch_runbook.md              "That id is the product code. Save it."
    CLAUDE.md                               repeated it

Measured from this repo's own artefacts rather than from a doc, because
docs.aws.amazon.com is egress-blocked from the container:

    entity id     prod-kkvurtspreofy          Catalog API identifier
    product code  46y72j0d99w7lyqkiqrakpc5k   TODO.md
    product code  5s4a96a1ui1a5efrom6udnm2g   relayshield_aws_marketplace.py

The product code is what ResolveCustomer returns and what GetEntitlements and
BatchMeterUsage take. An entity id in BUNDLE_B_PRODUCT_CODE matches no key row,
raises nothing and reports success -- strictly worse than the git SHA that was
actually pasted, because the SHA at least looks wrong.
"""
import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ENV = load("lambda_env_merge", "tools/lambda_env_merge.py")
READ = load("marketplace_read_product", "tools/marketplace_read_product.py")

REAL_CODES = ["46y72j0d99w7lyqkiqrakpc5k", "5s4a96a1ui1a5efrom6udnm2g"]
ENTITY_IDS = ["prod-kkvurtspreofy", "prod-f5qkfsxlxs4qg"]


def code_only(path: Path) -> str:
    """Prose describing a defect is not the defect. Six occurrences in this
    repo's history of a guard matching its own explanatory comment."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        out.append(line)
    return "\n".join(out)


class TheEnvToolRefusesAnEntityId(unittest.TestCase):

    def test_an_entity_id_is_refused_for_a_product_code_key(self):
        for ident in ENTITY_IDS:
            with self.assertRaises(ENV.Refused, msg=f"{ident} was accepted"):
                ENV.validate("BUNDLE_B_PRODUCT_CODE", ident)

    def test_the_refusal_says_which_namespace_it_got(self):
        try:
            ENV.validate("BUNDLE_D_PRODUCT_CODE", "prod-kkvurtspreofy")
        except ENV.Refused as exc:
            self.assertIn("ENTITY ID", str(exc))
            self.assertIn("marketplace_read_product.py", str(exc),
                          "a refusal owes the reader the read that produces the "
                          "right value")
        else:
            self.fail("prod-kkvurtspreofy was accepted")

    def test_a_real_product_code_is_accepted(self):
        """The guard must not be so broad that the correct value fails. A check
        that forces you to work around it is a check that gets loosened."""
        for code in REAL_CODES:
            ENV.validate("BUNDLE_B_PRODUCT_CODE", code)
            self.assertEqual(ENV.shape_note("BUNDLE_B_PRODUCT_CODE", code), "",
                             f"{code} is a real product code and drew a shape note")

    def test_a_git_sha_is_still_refused(self):
        with self.assertRaises(ENV.Refused):
            ENV.validate("BUNDLE_B_PRODUCT_CODE", "6" * 8 + "f" * 32)

    def test_an_entity_id_is_fine_for_a_key_that_is_not_a_product_code(self):
        """Only *_PRODUCT_CODE is constrained. The entity id is a legitimate
        value elsewhere -- it is what the test-offer and go-public change sets
        take as product_id."""
        ENV.validate("BUNDLE_B_ENTITY_ID", "prod-f5qkfsxlxs4qg")


class TheReadToolSeparatesThem(unittest.TestCase):

    def test_a_prod_id_is_never_offered_as_a_product_code_candidate(self):
        doc = {"ProductId": "prod-kkvurtspreofy", "Title": "RelayShield"}
        self.assertEqual(READ.candidates(doc), [])

    def test_the_exclusion_lives_in_the_shape_rule_itself(self):
        """The first draft carried a separate prod- exclusion and deleting it
        changed nothing: an entity id is hyphenated and the shape rule allows no
        hyphen. Asserted here as a property of CANDIDATE so the real reason is
        pinned rather than a rule that cannot fire."""
        for ident in ENTITY_IDS:
            self.assertIsNone(READ.CANDIDATE.match(ident))
        self.assertFalse(hasattr(READ, "ENTITY_ID"),
                         "a second exclusion rule is unreachable and reads as "
                         "protection that is not there")

    def test_a_real_code_is_found_and_labelled_with_its_key_path(self):
        doc = {"Details": {"ProductCode": REAL_CODES[0]}}
        found = READ.candidates(doc)
        self.assertEqual(found, [("Details.ProductCode", REAL_CODES[0])],
                         "the key path is what tells a product code from a "
                         "change set id, which is the same shape")

    def test_it_walks_lists_as_well_as_dicts(self):
        doc = {"Dimensions": [{"Key": "a"}, {"Code": REAL_CODES[1]}]}
        self.assertIn(("Dimensions[1].Code", REAL_CODES[1]), READ.candidates(doc))


class NoArtefactSaysTheyAreTheSame(unittest.TestCase):
    """Anchored on the SENTENCE that makes the claim, never on the file.

    A word that appears for an unrelated reason is a guard that cannot fail --
    the README provider guard learned that on its own proof run.
    """

    CLAIM = re.compile(
        r"(entity id|that id|the id)[^.\n]{0,60}\bis the product code",
        re.IGNORECASE)

    def test_the_submit_tool_does_not_print_the_wrong_advice(self):
        src = code_only(ROOT / "tools" / "marketplace_submit_changeset.py")
        hit = self.CLAIM.search(src)
        self.assertIsNone(hit, f"marketplace_submit_changeset.py still says: "
                               f"{hit.group(0) if hit else ''}")

    def test_the_runbook_step_6_asks_for_the_product_code(self):
        text = (ROOT / "bundle_b_launch_runbook.md").read_text(encoding="utf-8")
        self.assertIn("| value | the **product code** from STEP 5b", text,
                      "STEP 6's value row must name the product code, not the "
                      "product id -- naming the id is what sent the wrong value")

    def test_the_runbook_carries_the_read_that_produces_it(self):
        text = (ROOT / "bundle_b_launch_runbook.md").read_text(encoding="utf-8")
        self.assertIn("STEP 5b", text)
        self.assertIn("marketplace_read_product", text)

    def test_the_read_workflow_exists_and_has_no_apply_mode(self):
        wf = (ROOT / ".github" / "workflows" /
              "marketplace_read_product.yml").read_text(encoding="utf-8")
        body = "\n".join(l for l in wf.splitlines()
                          if not l.lstrip().startswith("#")).lower()
        self.assertNotIn("apply", body,
                         "the read workflow must have no apply path: it is the "
                         "one you re-run freely while AWS is still APPLYING")


if __name__ == "__main__":
    unittest.main(verbosity=2)
