"""Guards for tools/load_mcp_taxonomy.py and its source file."""
import ast
import copy
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("load_mcp_taxonomy", REPO / "tools" / "load_mcp_taxonomy.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

DOC = json.loads(mod.DEFAULT_FILE.read_text())


class SourceFile(unittest.TestCase):
    def test_validates_and_loads_every_entry(self):
        self.assertEqual(len(mod.validate(DOC)), 9)

    def test_only_strong_and_moderate_are_present(self):
        self.assertEqual({e["fit"] for e in DOC["entries"]}, {"STRONG", "MODERATE"})

    def test_no_excluded_fit_is_also_loaded(self):
        # An excluded (disclosure, category) pair must not reappear as an entry.
        loaded = {(e["disclosure"], e["poison_category"]) for e in DOC["entries"]}
        for x in DOC["excluded_thin_fits"]:
            self.assertNotIn((x["disclosure"], x["category"]), loaded)


class Validation(unittest.TestCase):
    def _bad(self, edit):
        d = copy.deepcopy(DOC)
        edit(d)
        with self.assertRaises(ValueError):
            mod.validate(d)

    def test_refuses_a_thin_fit(self):
        self._bad(lambda d: d["entries"][0].update(fit="THIN"))

    def test_refuses_an_unknown_fit(self):
        self._bad(lambda d: d["entries"][0].update(fit="UNKNOWN"))

    def test_refuses_an_unknown_category(self):
        self._bad(lambda d: d["entries"][0].update(poison_category="made_up"))

    def test_refuses_a_duplicate_id(self):
        self._bad(lambda d: d["entries"][1].update(id=d["entries"][0]["id"]))

    def test_refuses_an_unapproved_file(self):
        self._bad(lambda d: d.pop("approved_by"))

    def test_refuses_a_missing_field(self):
        self._bad(lambda d: d["entries"][0].pop("mitigation"))

    def test_refuses_the_wrong_taxonomy(self):
        self._bad(lambda d: d.update(taxonomy="something_else"))


class Pinned(unittest.TestCase):
    def test_categories_exist_in_the_proxy_screener(self):
        # Two files that must agree: the loader's category set and the proxy's.
        tree = ast.parse((REPO / "mcp_proxy" / "screener.py").read_text())
        consts = {n.value.value for n in ast.walk(tree)
                  if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
                  and isinstance(n.value.value, str)}
        self.assertTrue(mod.CATEGORIES <= consts, mod.CATEGORIES - consts)

    def test_hash_is_stable_and_changes_with_content(self):
        e = DOC["entries"][0]
        self.assertEqual(mod.content_hash(e), mod.content_hash(copy.deepcopy(e)))
        f = copy.deepcopy(e)
        f["mitigation"] += "x"
        self.assertNotEqual(mod.content_hash(e), mod.content_hash(f))

    def test_dry_run_default_and_account_guard_are_in_the_source(self):
        src = (REPO / "tools" / "load_mcp_taxonomy.py").read_text()
        code = re.sub(r'""".*?"""', "", src, flags=re.S)
        self.assertIn('"--apply", action="store_true"', code)
        self.assertIn("239677749008", code)
        self.assertLess(code.index("get_caller_identity"), code.index("put_item"))

    def test_boto3_is_imported_after_validation(self):
        src = (REPO / "tools" / "load_mcp_taxonomy.py").read_text()
        self.assertLess(src.index("validate(doc)"), src.index("import boto3"))


if __name__ == "__main__":
    unittest.main()
