"""Every tracked Python source in this repo must COMPILE.

WHY THIS EXISTS. On 2026-10-04 a one-character slip in relayshield_scamkit.py
(`)` where `})` belonged, closing a frozenset) was pushed to main. relayshield_api.py
imports that module at the top, so the whole API failed to load. The deploy went
green anyway: the post-deploy import probe only grepped for ImportModuleError and
"No module named", and a syntax error is reported as Runtime.UserCodeSyntaxError,
so the probe printed "relayshield-api imports cleanly" over a function that could
not start. Nothing else in the repo parses a file it does not happen to run.

This is the cheapest possible check and it runs before a push: it parses every
tracked .py file with the real compiler front end and fails naming the file and
line. It deliberately does not import anything, so it needs no boto3 and no
network.
"""
import ast
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent


def tracked_python() -> list[pathlib.Path]:
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout.split()
    return [ROOT / p for p in out if "node_modules" not in p]


class EverySourceCompiles(unittest.TestCase):
    def test_every_tracked_python_file_parses(self):
        files = tracked_python()
        # A guard that scopes itself down to nothing passes forever.
        self.assertGreater(len(files), 100, "git ls-files returned suspiciously few files")
        broken = []
        for path in files:
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                broken.append(f"{path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}")
        self.assertEqual(broken, [], "files that do not compile:\n  " + "\n  ".join(broken))

    def test_the_lambda_import_chain_of_the_api_compiles(self):
        """relayshield_api.py imports these at module load. If any one fails to
        parse, every endpoint in the API is down, so name them explicitly in
        case the broad test above is ever narrowed."""
        for name in ("relayshield_api.py", "relayshield_scamkit.py",
                     "relayshield_scamkit_fetch.py", "relayshield_openapi_spec.py",
                     "relayshield_corpus_provenance.py", "relayshield_phone_reputation.py",
                     "relayshield_breach_monitor.py"):
            path = ROOT / name
            self.assertTrue(path.exists(), f"{name} is imported by the API but is missing")
            ast.parse(path.read_text(encoding="utf-8"), filename=name)

    def test_the_deploy_probe_recognises_a_syntax_error(self):
        """The probe that printed 'imports cleanly' over a dead function. Reads
        the pattern out of the workflow rather than restating it."""
        import re
        text = (ROOT / ".github/workflows/deploy_lambdas.yml").read_text(encoding="utf-8")
        m = re.search(r"elif grep -qiE '([^']+)' out\.json", text)
        self.assertIsNotNone(m, "the import probe no longer uses the Runtime.* pattern")
        rx = re.compile(m.group(1), re.IGNORECASE)
        self.assertTrue(rx.search('{"errorType": "Runtime.UserCodeSyntaxError", "errorMessage": "x"}'))
        self.assertTrue(rx.search('{"errorType": "Runtime.ImportModuleError"}'))
        self.assertTrue(rx.search('Unable to import module: No module named boto'))
        self.assertFalse(rx.search('{"statusCode": 404, "body": "{\\"ok\\": false}"}'),
                         "a healthy probe response must not read as a failure")


if __name__ == "__main__":
    unittest.main()
