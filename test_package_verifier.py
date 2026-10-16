"""The verifier package is complete, or the build says so. Executed, not read."""
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import package_verifier as pv  # noqa: E402


class Manifest(unittest.TestCase):
    def test_the_core_manifest_is_complete(self):
        self.assertEqual(pv.problems(pv.manifest()), [])

    def test_dropping_any_module_is_caught_by_the_import_walk(self):
        """Every module here is imported behind a try/except, so a missing one does not fail at
        runtime: it silently degrades. The AST walk is what notices."""
        for victim in pv.CORE:
            if not victim.endswith(".py") or victim == "relayshield_tap_verifier.py":
                continue
            files = [f for f in pv.manifest() if f != victim]
            msgs = pv.problems(files)
            self.assertTrue(any(f"imports {victim[:-3]}" in m for m in msgs), (victim, msgs))

    def test_a_listed_file_that_does_not_exist_is_caught(self):
        self.assertTrue(any("missing from the repo" in m for m in pv.problems(pv.manifest() + ["nope.py"])))

    def test_tests_the_testkit_and_tools_can_never_be_packaged(self):
        for f in ("test_x401_rp.py", "x401_testkit.py", "tools/x401_demo.py"):
            (ROOT / f).exists()
            self.assertTrue(any("must not be packaged" in m for m in pv.problems(pv.manifest() + [f])), f)
        self.assertFalse([f for f in pv.manifest(True) if f.startswith(("test_", "x401_testkit"))])

    def test_the_ti_variant_bundles_the_api_and_everything_it_imports(self):
        files = pv.manifest(with_ti=True)
        self.assertIn("relayshield_api.py", files)
        self.assertEqual(pv.problems(files, with_ti=True), [])
        self.assertGreater(len(files), len(pv.CORE))

    def test_without_ti_the_one_optional_import_is_tolerated_and_nothing_else(self):
        self.assertEqual(pv.OPTIONAL_IMPORTS, {"relayshield_tap_ti.py": {"relayshield_api"}})
        files = [f for f in pv.manifest() if f != "relayshield_tap_ti.py"]
        self.assertTrue(pv.problems(files), "dropping the TI module itself is still an error")

    def test_a_private_key_in_the_config_files_stops_the_build(self):
        import json
        original = (ROOT / "x401_issuers.json").read_text()
        try:
            (ROOT / "x401_issuers.json").write_text(json.dumps({"issuers": {"i": {"kty": "EC", "d": "secret"}}}))
            self.assertTrue(any("private key" in m for m in pv.problems(pv.manifest())))
        finally:
            (ROOT / "x401_issuers.json").write_text(original)

    def test_the_shipped_config_files_are_valid_and_empty(self):
        import json
        self.assertEqual(json.loads((ROOT / "x401_issuers.json").read_text()), {"issuers": {}})
        self.assertEqual(json.loads((ROOT / "x401_policies.json").read_text()), {"policies": {}})


class Build(unittest.TestCase):
    def test_the_built_package_runs_in_isolation_and_the_build_is_reproducible(self):
        with tempfile.TemporaryDirectory() as td:
            outs = []
            for i in (1, 2):
                out = pathlib.Path(td) / f"v{i}.zip"
                r = subprocess.run([sys.executable, "-B", str(ROOT / "tools" / "package_verifier.py"), "--out", str(out)],
                                   capture_output=True, text=True, timeout=100)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("SMOKE OK", r.stdout)
                outs.append(out.read_bytes())
            self.assertEqual(outs[0], outs[1], "the same inputs must give the same bytes")

    def test_a_broken_package_fails_the_smoke_test(self):
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            z = pathlib.Path(td) / "bad.zip"
            files = [f for f in pv.manifest() if f != "x401_rp.py"]
            pv.build(files, z)
            ok, log = pv.smoke(z)
        self.assertFalse(ok)
        self.assertIn("x401_rp", log)


if __name__ == "__main__":
    unittest.main()
