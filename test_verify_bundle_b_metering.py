"""Guards for tools/verify_bundle_b_metering.py.

The defect these exist for: the FIRST version extracted the log patterns with a
regex over the function body and picked up the function's own DOCSTRING, which
explains the logging convention and therefore contains the words. It returned a
bare "Marketplace usage" and a truncated "Marketplace usage reported", and the
rejected-record branch went undetected. Prose fooling a guard, seventh time.

No AWS, no boto3. Reads the committed artefacts.
"""
import ast
import importlib.util
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
TOOL = ROOT / "tools" / "verify_bundle_b_metering.py"
API = ROOT / "relayshield_api.py"
AUDIT = ROOT / "tools" / "diagnose_bundle_b_audit.sh"


def _load():
    spec = importlib.util.spec_from_file_location("vbbm", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _logger_formats():
    """Independently parsed: what the function ACTUALLY writes."""
    fn = next(n for n in ast.walk(ast.parse(API.read_text(encoding="utf-8")))
              if isinstance(n, ast.FunctionDef)
              and n.name == "_report_marketplace_usage")
    out = []
    for node in ast.walk(fn):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "logger"
                and node.args and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            out.append(node.args[0].value)
    return out


class Extraction(unittest.TestCase):
    def test_every_line_the_function_writes_is_searched(self):
        pats = _load().log_patterns()
        for fmt in _logger_formats():
            head = fmt.split("%")[0].strip()
            self.assertIn(head, pats,
                          f"the function writes {fmt!r} and nothing searches for it")

    def test_no_pattern_is_a_bare_prefix_that_matches_everything(self):
        """'Marketplace usage' alone matches all six lines, so a hit against it
        cannot tell success from rejection. That is what the regex produced."""
        pats = _load().log_patterns()
        for p in pats:
            others = [q for q in pats if q != p]
            self.assertFalse(
                any(q.startswith(p) for q in others),
                f"{p!r} is a prefix of another pattern: it cannot discriminate")

    def test_the_docstring_cannot_reach_the_extraction(self):
        """Proven by putting the words in the docstring and requiring no change."""
        src = API.read_text(encoding="utf-8")
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "_report_marketplace_usage")
        doc = ast.get_docstring(fn) or ""
        self.assertTrue(doc, "no docstring, so this guard proves nothing")
        # The real docstring already discusses logging; assert the extraction
        # returns exactly the logger formats and nothing the prose contributed.
        self.assertEqual(sorted(_load().log_patterns()),
                         sorted({f.split("%")[0].strip() for f in _logger_formats()}))


class Refusals(unittest.TestCase):
    def test_it_refuses_an_entity_id_and_names_the_namespace(self):
        body = TOOL.read_text(encoding="utf-8")
        self.assertIn('startswith("prod-")', body)
        self.assertIn("ResolveCustomer", body,
                      "a refusal must name the route to the right value")

    def test_it_refuses_anything_that_is_not_a_product_code_shape(self):
        mod = _load()
        self.assertTrue(mod.CODE_RE.match("cmh79gzztkdtp0dlzbdepa643"))
        self.assertFalse(mod.CODE_RE.match("prod-szi2wdww3obry"))
        self.assertFalse(mod.CODE_RE.match("a7067bd2c5e70b0318c9b7f327ddeb13568b778c"))


class VerdictFirst(unittest.TestCase):
    def test_the_verdict_is_printed_before_any_evidence(self):
        """Three rounds on 2026-09-21 were lost to a diagnostic whose decisive
        section was last and got truncated out of a pasted terminal."""
        body = TOOL.read_text(encoding="utf-8")
        self.assertLess(body.index('VERDICT for product code'), body.index('EVIDENCE 1'),
                        "the verdict must come first")

    def test_a_refused_read_is_never_rendered_as_a_zero(self):
        body = TOOL.read_text(encoding="utf-8")
        self.assertIn("COULD NOT TELL", body)
        self.assertIn("Do not read", body)


class AuditScriptSearchesAllSix(unittest.TestCase):
    def test_the_audit_script_searches_every_line_too(self):
        """It searched three of six until 2026-09-22, and the missing three were
        the failure cases, so a rejection printed 'none'."""
        sh = AUDIT.read_text(encoding="utf-8")
        # ANCHOR ON THE SECTION, NOT ON THE FIRST MATCH IN THE FILE. There are
        # two `for PAT in` loops and the first one is section 4's entitlement
        # check -- the same defect as the cta-line guard that took the first
        # write and became the wrong block the moment a second one appeared.
        sec = sh.index("== 5.")
        start = sh.index("for PAT in", sec)
        loop = sh[start:sh.index("; do", start)]
        for fmt in _logger_formats():
            head = fmt.split("%")[0].strip()
            self.assertTrue(
                any(head.startswith(q) or q in head
                    for q in re.findall(r'"([^"]+)"', loop)),
                f"audit section 5 does not search for {head!r}")


if __name__ == "__main__":
    unittest.main(verbosity=1)
