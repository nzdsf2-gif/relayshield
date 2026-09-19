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
import ast
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
        """The property is that a refusal names the route to the RIGHT value.

        This guard used to require the string `marketplace_read_product.py`,
        which pinned one ROUTE rather than the property -- and when that route
        turned out to be the wrong one (DescribeEntity may carry no product
        code at all; ResolveCustomer is what returns it) the guard defended the
        wrong answer and failed on the correction. A test that pins the shape
        of an answer instead of what the answer must ACHIEVE eventually fails
        on correct code, and the temptation then is to loosen it.
        """
        try:
            ENV.validate("BUNDLE_D_PRODUCT_CODE", "prod-kkvurtspreofy")
        except ENV.Refused as exc:
            text = str(exc)
            self.assertIn("ENTITY ID", text)
            self.assertTrue(
                "ResolveCustomer" in text or "marketplace_read_product.py" in text,
                "a refusal owes the reader the route that produces the right "
                f"value; this one names neither: {text}")
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

    def test_the_runbook_value_row_asks_for_the_product_code(self):
        """Anchored on the ROW, not on the step number it sits under.

        The first version required "from STEP 5b" and failed the day that step
        moved to 8b -- a guard encoding the runbook's numbering rather than its
        claim. What must hold is that the row naming the env var's value asks
        for the product code and says outright it is not the prod- id.
        """
        text = (ROOT / "bundle_b_launch_runbook.md").read_text(encoding="utf-8")
        rows = [l for l in text.splitlines()
                if l.startswith("| value |") and "product code" in l]
        self.assertTrue(rows, "no `| value |` row names the product code")
        for row in rows:
            self.assertIn("Not the `prod-", row,
                          f"this row does not rule out the entity id: {row}")

    def test_the_runbook_carries_the_read_that_produces_it(self):
        """Either route is acceptable; naming NEITHER is not. The E2E log line
        is the authoritative one, because ResolveCustomer is what assigns the
        code, and the DescribeEntity read is a cheaper try that may find
        nothing."""
        text = (ROOT / "bundle_b_launch_runbook.md").read_text(encoding="utf-8")
        self.assertTrue(
            "Product code not recognised" in text
            or "marketplace_read_product" in text,
            "the runbook must name at least one route to the product code")

    def test_the_env_step_comes_after_the_subscription_that_assigns_the_value(self):
        """2026-09-19: it was run sixth, with the entity id, and refused. The
        guard was right and the ORDER was wrong -- a step numbered 6 in a
        numbered list is an instruction to run it sixth, whatever the prose
        beside it says. Prose cannot enforce an order; position can."""
        lines = (ROOT / "bundle_b_launch_runbook.md").read_text(
            encoding="utf-8").splitlines()
        def at(prefix):
            return next(i for i, l in enumerate(lines) if l.startswith(prefix))
        self.assertLess(at("## STEP 8 --"), at("## STEP 8b --"),
                        "setting BUNDLE_B_PRODUCT_CODE must come after the "
                        "subscription, which is what assigns the value")

    def test_the_read_workflow_exists_and_has_no_apply_mode(self):
        wf = (ROOT / ".github" / "workflows" /
              "marketplace_read_product.yml").read_text(encoding="utf-8")
        body = "\n".join(l for l in wf.splitlines()
                          if not l.lstrip().startswith("#")).lower()
        self.assertNotIn("apply", body,
                         "the read workflow must have no apply path: it is the "
                         "one you re-run freely while AWS is still APPLYING")


class AGitShaIsNeverAMarketplaceIdentifier(unittest.TestCase):
    """Offered twice: once as the product code, once as the ChangeSetId.

    Both times because GitHub prints the commit SHA in the Actions run header
    while the value the reader needs is inside the job's output. The shape is
    unambiguous -- 40 hex is neither a 25-character ChangeSetId nor a prod-
    entity id -- so this one refuses rather than warns.
    """

    SHA = "a7067bd2c5e70b0318c9b7f327ddeb13568b778c"
    REAL_CHANGE_SET = "17or75a96xofiu7gic33wjrm6"

    def test_a_sha_as_a_change_set_id_is_refused(self):
        with self.assertRaises(SystemExit) as ctx:
            READ.check_input_shapes(self.SHA, "")
        self.assertIn("git commit SHA", str(ctx.exception))
        self.assertIn("ChangeSetId", str(ctx.exception))

    def test_a_sha_as_an_entity_id_is_refused(self):
        with self.assertRaises(SystemExit):
            READ.check_input_shapes("", self.SHA)

    def test_a_real_change_set_id_passes_silently(self):
        import contextlib, io as _io
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            READ.check_input_shapes(self.REAL_CHANGE_SET, "")
        self.assertEqual(buf.getvalue(), "",
                         "a correct id must not be warned about")

    def test_a_real_entity_id_passes_silently(self):
        import contextlib, io as _io
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            for ident in ENTITY_IDS:
                READ.check_input_shapes("", ident)
        self.assertEqual(buf.getvalue(), "")

    def test_an_unrecognised_value_warns_and_continues(self):
        """A probe that cannot tell has no standing to stop a read-only tool."""
        import contextlib, io as _io
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            READ.check_input_shapes("SOMETHING-ELSE", "")
        self.assertIn("WARNING", buf.getvalue())

    def test_the_refusal_runs_before_any_aws_call(self):
        """It has to fire without credentials and without boto3, or the reader
        gets an import error instead of the sentence naming their mistake."""
        import ast
        src = (ROOT / "tools" / "marketplace_read_product.py").read_text(encoding="utf-8")
        main = next(n for n in ast.walk(ast.parse(src))
                    if isinstance(n, ast.FunctionDef) and n.name == "main")
        def index_of(pred):
            for i, stmt in enumerate(main.body):
                for sub in ast.walk(stmt):
                    if pred(sub):
                        return i
            return None
        check = index_of(lambda n: isinstance(n, ast.Call)
                         and getattr(n.func, "id", "") == "check_input_shapes")
        boto = index_of(lambda n: isinstance(n, ast.Import)
                        and any(a.name == "boto3" for a in n.names))
        self.assertIsNotNone(check, "check_input_shapes is not called at all")
        self.assertIsNotNone(boto)
        self.assertLess(check, boto,
                        "the shape refusal must precede the boto3 import")


class AChangeSetIdentifierCarriesARevisionSuffix(unittest.TestCase):
    """Change set 27vgy6fh2q7uke1ddtxa0w1l3 SUCCEEDED and created the product,
    and this tool then died one line later:

        ValidationException: [Requested entity id 'prod-szi2wdww3obry@1' is
        invalid. It should match with ^[a-zA-Z0-9][.a-zA-Z0-9/-]+[a-zA-Z0-9$.]

    DescribeChangeSet reports the entity REVISION (`@1`); DescribeEntity
    refuses it. Two identifiers for one product, one character apart, and the
    failure reads as "the product is invalid" when the product is fine and it
    was the request that was malformed.
    """

    def test_the_revision_suffix_is_stripped(self):
        self.assertEqual(READ.bare_entity_id("prod-szi2wdww3obry@1"),
                         "prod-szi2wdww3obry")

    def test_a_bare_id_is_unchanged(self):
        self.assertEqual(READ.bare_entity_id("prod-kkvurtspreofy"),
                         "prod-kkvurtspreofy")

    def test_an_offer_identifier_strips_too(self):
        self.assertEqual(READ.bare_entity_id("offer-tphmeebmexqp2@1"),
                         "offer-tphmeebmexqp2")

    def test_a_double_digit_revision_strips(self):
        self.assertEqual(READ.bare_entity_id("prod-szi2wdww3obry@12"),
                         "prod-szi2wdww3obry")

    def test_empty_and_none_are_safe(self):
        self.assertEqual(READ.bare_entity_id(""), "")
        self.assertEqual(READ.bare_entity_id(None), "")

    def test_the_stripped_id_satisfies_the_tool_s_own_entity_pattern(self):
        """The guard that WARNS on an unrecognised entity id must not warn on
        the one the change set just handed us."""
        self.assertTrue(READ.ENTITY.match(READ.bare_entity_id("prod-szi2wdww3obry@1")))

    def test_an_at_suffix_is_never_sent_to_describe_entity(self):
        """Read the CALL SITE, not the helper. A helper nothing calls is
        decoration -- the ast lesson from the SIM swap detector."""
        src = (ROOT / "tools" / "marketplace_read_product.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        main = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == "main")
        assigns = [n for n in ast.walk(main)
                   if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "entity_id" for t in n.targets)]
        from_changeset = [n for n in assigns
                          if isinstance(n.value, ast.Call)
                          and getattr(n.value.func, "id", "") == "bare_entity_id"]
        self.assertTrue(
            from_changeset,
            "the entity id taken out of the change set must go through "
            "bare_entity_id(); a raw Identifier carries @1 and DescribeEntity "
            "refuses it")


class TheRefusalsNameTheRouteThatProducesTheValue(unittest.TestCase):
    """2026-09-19: step 6 was run with `prod-szi2wdww3obry` and refused. The
    guard was right -- an entity id in that field matches no key row, raises
    nothing, and makes a revocation scan over a live listing find nothing and
    report success.

    But a refusal that only says no costs a round. Both of these used to send
    the reader somewhere that cannot answer: the entity-id one named
    marketplace_read_product.py, which reports NONE when DescribeEntity carries
    no code, and the git-SHA one said the code comes from StartChangeSet, which
    is the sentence this programme has now been wrong about twice.

    A product code is returned by ResolveCustomer, so it exists only once a
    customer subscribes -- and the subscription does not need the key, because
    BUNDLE_CONFIGS is keyed on the entitlement DIMENSION.
    """

    def _refusal(self, value):
        with self.assertRaises(ENV.Refused) as ctx:
            ENV.validate("BUNDLE_B_PRODUCT_CODE", value)
        return str(ctx.exception)

    def test_an_entity_id_is_refused(self):
        self.assertIn("ENTITY ID", self._refusal("prod-szi2wdww3obry"))

    def test_the_entity_id_refusal_names_resolvecustomer_not_a_lookup_tool(self):
        text = self._refusal("prod-szi2wdww3obry")
        self.assertIn("ResolveCustomer", text)
        self.assertNotIn("marketplace_read_product.py", text)

    def test_the_entity_id_refusal_says_the_step_is_premature(self):
        """The reader's next move is the test offer, not a hunt."""
        self.assertIn("PREMATURE", self._refusal("prod-szi2wdww3obry").upper())

    def test_the_git_sha_refusal_no_longer_credits_startchangeset(self):
        """StartChangeSet returns the ENTITY ID. Saying it returns the product
        code is the exact confusion these guards exist to stop, printed by the
        guard itself."""
        text = self._refusal("a7067bd2c5e70b0318c9b7f327ddeb13568b778c")
        self.assertIn("ResolveCustomer", text)
        self.assertNotIn("product code is assigned by StartChangeSet", text)

    def test_a_real_product_code_is_accepted(self):
        ENV.validate("BUNDLE_B_PRODUCT_CODE", "46y72j0d99w7lyqkiqrakpc5k")


if __name__ == "__main__":
    unittest.main(verbosity=2)
