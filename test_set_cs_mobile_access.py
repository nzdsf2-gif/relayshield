import importlib.util, pathlib, re, unittest

ROOT = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("setacc", ROOT / "tools" / "set_cs_mobile_access.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class PickAndPlan(unittest.TestCase):
    def test_two_records_one_email_pick_only_the_suffix_match(self):
        items = [{"api_key": "rs_aaaaaa111111"}, {"api_key": "rs_bbbbbb222222"}]
        rec, why = m.pick_record(items, "222222")
        self.assertEqual(rec["api_key"], "rs_bbbbbb222222")

    def test_no_match_and_ambiguous_and_short_all_refuse(self):
        items = [{"api_key": "rs_x111111"}, {"api_key": "rs_y111111"}]
        self.assertIsNone(m.pick_record(items, "999999")[0])
        self.assertIsNone(m.pick_record(items, "111111")[0])
        self.assertIsNone(m.pick_record(items, "11")[0])

    def test_plan_only_lists_unset_flags(self):
        self.assertEqual(m.plan_changes({}), {"cs_mobile_access": True, "active": True})
        self.assertEqual(m.plan_changes({"active": True}), {"cs_mobile_access": True})
        self.assertEqual(m.plan_changes({"active": True, "cs_mobile_access": True}), {})

    def test_never_writes_a_stripe_field_and_cannot_create_a_record(self):
        src = (ROOT / "tools" / "set_cs_mobile_access.py").read_text()
        self.assertEqual(set(m.FLAGS), {"cs_mobile_access", "active"})
        self.assertIn("attribute_exists(api_key)", src)
        self.assertNotRegex(src, r"put_item")

    def test_describe_never_prints_a_whole_key(self):
        out = m.describe({"api_key": "rs_secretsecretsecret123456"})
        self.assertNotIn("secretsecret", out)
        self.assertIn("123456", out)


class VersionAgreement(unittest.TestCase):
    """A gradle build reads build.gradle, not app.json. Both must say the same."""
    def test_gradle_matches_app_json(self):
        import json
        app = json.loads((ROOT / "crypto-shield-app" / "app.json").read_text())["expo"]
        g = (ROOT / "crypto-shield-app" / "android" / "app" / "build.gradle").read_text()
        code = int(re.search(r"versionCode\s+(\d+)", g).group(1))
        name = re.search(r'versionName\s+"([^"]+)"', g).group(1)
        self.assertEqual(code, app["android"]["versionCode"])
        self.assertEqual(name, app["version"])


if __name__ == "__main__":
    unittest.main()
