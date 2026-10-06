import importlib.util, pathlib, re, unittest

ROOT = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("g", ROOT / "tools" / "grant_breach_cache_access.py")
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)


class Merge(unittest.TestCase):
    DOC = {"Version": "2012-10-17", "Statement": [
        {"Sid": "A", "Effect": "Allow", "Action": ["dynamodb:PutItem"], "Resource": "arn:x:table/first_seen"},
        {"Effect": "Allow", "Action": "dynamodb:Scan", "Resource": "arn:x:table/other"}]}

    def test_other_statements_untouched_and_one_added(self):
        out = g.merged_document(self.DOC)
        self.assertEqual(out["Statement"][:2], self.DOC["Statement"])
        self.assertEqual(len(out["Statement"]), 3)

    def test_idempotent(self):
        once = g.merged_document(self.DOC)
        self.assertEqual(g.merged_document(once), once)

    def test_input_not_mutated(self):
        before = repr(self.DOC)
        g.merged_document(self.DOC)
        self.assertEqual(repr(self.DOC), before)

    def test_grant_is_exact_table_and_two_actions_only(self):
        st = g.merged_document({"Statement": []})["Statement"][0]
        self.assertEqual(st["Resource"], g.TABLE_ARN)
        self.assertNotIn("*", st["Resource"])
        self.assertEqual(sorted(st["Action"]), ["dynamodb:GetItem", "dynamodb:PutItem"])

    def test_actions_match_what_the_cache_code_calls(self):
        src = (ROOT / "relayshield_api.py").read_text()
        for fn, call in (("_breach_cache_get", "get_item"), ("_breach_cache_put", "put_item")):
            m = re.search(rf"def {fn}\(.*?(?=\ndef )", src, re.S)
            self.assertIsNotNone(m, fn)
            self.assertIn(call, m.group(0))
        self.assertIn(g.TABLE, src)


class SecondTable(unittest.TestCase):
    VT = "relayshield_vt_url_cache"

    def test_each_table_has_its_own_sid(self):
        self.assertEqual(len(set(g.CACHE_SIDS.values())), len(g.CACHE_SIDS))

    def test_granting_the_second_table_keeps_the_first(self):
        doc = g.merged_document({"Statement": []})
        doc = g.merged_document(doc, self.VT)
        resources = sorted(s["Resource"] for s in doc["Statement"])
        self.assertEqual(resources, sorted([g.table_arn(g.TABLE), g.table_arn(self.VT)]))

    def test_vt_grant_is_exact_arn_and_two_actions(self):
        st = g.merged_document({"Statement": []}, self.VT)["Statement"][0]
        self.assertEqual(st["Resource"], g.table_arn(self.VT))
        self.assertNotIn("*", st["Resource"])
        self.assertEqual(sorted(st["Action"]), ["dynamodb:GetItem", "dynamodb:PutItem"])

    def test_vt_idempotent(self):
        once = g.merged_document({"Statement": []}, self.VT)
        self.assertEqual(g.merged_document(once, self.VT), once)

    def test_actions_match_what_the_vt_cache_code_calls(self):
        src = (ROOT / "relayshield_api.py").read_text()
        for fn, call in (("_vt_url_cache_get", "get_item"), ("_vt_url_cache_put", "put_item")):
            m = re.search(rf"def {fn}\(.*?(?=\ndef )", src, re.S)
            self.assertIsNotNone(m, fn)
            self.assertIn(call, m.group(0))
        self.assertIn(self.VT, src)


if __name__ == "__main__":
    unittest.main()
