"""The five places that must agree about which Lambdas are versioned, and the deploy gate.

    python3 test_deploy_versions.py

WHY: the same function list lives in deploy_lambdas.yml (VERSIONED_FUNCS), rollback_lambda.yml (the choice
options) and iam_github_deploy_versions.json (the grant). Two files that must agree with nothing checking that
they do is the shape of the 2026-09-03 discord-bot failure (see tools/check_deploy_invoke_policy.py). This is the
check, plus the properties of the deploy gate that are easy to break by editing YAML:
  * a failed or missing test run must stop the deploy, a manual run must bypass it and say so;
  * the version step runs AFTER the import probe and can never fail the deploy;
  * the rollback validates its input and reads inputs through env, never interpolated into the shell.
Needs pyyaml (in tests_requirements.txt)."""
import json
import re
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
WF = ROOT / ".github" / "workflows"


def load(name):
    d = yaml.safe_load((WF / name).read_text())
    d["on"] = d.get("on", d.get(True))  # PyYAML reads the key `on` as boolean True
    return d


class Agreement(unittest.TestCase):
    def setUp(self):
        self.deploy, self.rollback, self.tests = load("deploy_lambdas.yml"), load("rollback_lambda.yml"), load("tests.yml")
        self.versioned = self.deploy["jobs"]["deploy"]["env"]["VERSIONED_FUNCS"].split()
        self.iam = json.load(open(ROOT / "iam_github_deploy_versions.json"))

    def test_three_lists_agree(self):
        options = self.rollback["on"]["workflow_dispatch"]["inputs"]["function"]["options"]
        arns = self.iam["Statement"][0]["Resource"]
        iam_fns = {a.rsplit(":", 1)[-1] for a in arns if not a.endswith(":*")}
        self.assertEqual(sorted(self.versioned), sorted(options))
        self.assertEqual(set(self.versioned), iam_fns)

    def test_every_function_has_both_the_plain_and_qualified_arn(self):
        arns = self.iam["Statement"][0]["Resource"]
        for f in self.versioned:
            base = f"arn:aws:lambda:us-east-1:239677749008:function:{f}"
            self.assertIn(base, arns)
            self.assertIn(base + ":*", arns)

    def test_every_versioned_function_is_deployed_by_this_workflow(self):
        text = (WF / "deploy_lambdas.yml").read_text()
        for f in self.versioned:
            self.assertRegex(text, rf'\]="{re.escape(f)}"', f"{f} is not in LAMBDA_MAP, so nothing would ever version it")

    def test_grant_covers_every_action_the_workflows_call(self):
        granted = set(self.iam["Statement"][0]["Action"])
        text = (WF / "deploy_lambdas.yml").read_text() + (WF / "rollback_lambda.yml").read_text()
        used = {"publish-version": "PublishVersion", "update-alias": "UpdateAlias", "create-alias": "CreateAlias",
                "get-alias": "GetAlias", "list-versions-by-function": "ListVersionsByFunction", "get-function ": "GetFunction"}
        for cli, action in used.items():
            if f"aws lambda {cli}" in text:
                self.assertIn(f"lambda:{action}", granted, f"workflows call `{cli.strip()}` but the grant lacks lambda:{action}")


class Gate(unittest.TestCase):
    def setUp(self):
        self.deploy, self.tests = load("deploy_lambdas.yml"), load("tests.yml")
        self.job = self.deploy["jobs"]["deploy"]

    def test_tests_workflow_is_callable(self):
        self.assertIn("workflow_call", self.tests["on"])

    def test_deploy_needs_the_gate_and_the_gate_calls_tests_yml(self):
        self.assertEqual(self.job["needs"], "tests")
        self.assertEqual(self.deploy["jobs"]["tests"]["uses"], "./.github/workflows/tests.yml")

    def test_failed_gate_stops_the_deploy_and_manual_run_bypasses_it(self):
        cond = self.job["if"]
        self.assertIn("always()", cond)
        self.assertIn("needs.tests.result == 'success'", cond)
        self.assertIn("workflow_dispatch", cond)
        self.assertNotIn("failure", cond)
        self.assertIn("workflow_dispatch", self.deploy["jobs"]["tests"]["if"])

    def test_bypass_is_announced(self):
        steps = [s for s in self.job["steps"] if s.get("if") == "github.event_name == 'workflow_dispatch'"]
        self.assertTrue(steps and "NOT run" in steps[0]["run"])

    def test_version_step_comes_after_the_probe_and_cannot_fail_the_job(self):
        names = [s.get("name", "") for s in self.job["steps"]]
        probe, publish = names.index("Verify deployed Lambdas import cleanly"), names.index("Publish a version and move the live alias")
        self.assertGreater(publish, probe)
        run = self.job["steps"][publish]["run"]
        self.assertNotRegex(run, r"\bexit [1-9]")
        self.assertIn("::warning::", run)
        self.assertNotIn("continue-on-error", self.job["steps"][publish])  # no need: the script itself never exits non-zero

    def test_gate_job_has_read_only_permissions(self):
        self.assertEqual(self.deploy["jobs"]["tests"]["permissions"], {"contents": "read"})


class Rollback(unittest.TestCase):
    def setUp(self):
        self.wf = load("rollback_lambda.yml")
        self.job = self.wf["jobs"]["rollback"]

    def test_inputs_reach_the_shell_only_through_env(self):
        text = (WF / "rollback_lambda.yml").read_text()
        for line in text.splitlines():
            if "${{" in line and "inputs." in line:
                self.assertRegex(line, r"^\s+(FUNC|WANT): \$\{\{ inputs\.", f"input interpolated outside env: {line.strip()}")

    def test_function_is_a_dropdown_not_free_text(self):
        self.assertEqual(self.wf["on"]["workflow_dispatch"]["inputs"]["function"]["type"], "choice")

    def test_version_is_validated_and_alias_moves_last(self):
        run = "\n".join(s.get("run", "") for s in self.job["steps"])
        self.assertIn("^(previous|[0-9]+)$", run)
        names = [s["name"] for s in self.job["steps"]]
        self.assertEqual(names[-1], "Move the live alias to match")
        self.assertLess(names.index("Prove it imports"), names.index("Move the live alias to match"))

    def test_rolls_back_code_not_just_the_alias(self):
        run = "\n".join(s.get("run", "") for s in self.job["steps"])
        self.assertIn("update-function-code", run)


if __name__ == "__main__":
    unittest.main()
