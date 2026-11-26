"""tools/oidc_workflow_grants.py and the five intel workflows moved to the OIDC role.

Layers:
  * STATIC, no AWS: every one of the five workflows uses the OIDC role and no stored key, can mint an OIDC token, and EVERY aws call
    it makes (invoke / update-function-code / filter-log-events) is covered by a grant in iam_github_deploy_intel_ops.json or the
    already-applied invoke list. A workflow that asks for something nothing grants fails here, not on a Monday at 08:00.
  * DECISIONS, fake IAM: dry run writes nothing, apply writes ONE new inline policy and never touches another, wrong account refused,
    nothing to do when already allowed, trust mismatch is reported.
  * SHAPES, botocore Stubber over the REAL iam model (skipped, and said so, where boto3 is absent)."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import oidc_workflow_grants as T  # noqa: E402

WF = ["intel_channel_discovery", "intel_channel_review", "intel_feed", "intel_kev", "intel_substack"]
DOC = json.load(open(ROOT / "iam_github_deploy_intel_ops.json"))
ROLE_ARN = "arn:aws:iam::239677749008:role/relayshield-github-deploy"


def text(n):
    return (ROOT / ".github" / "workflows" / f"{n}.yml").read_text()


def code_lines(t):
    return "\n".join(l for l in t.splitlines() if not l.lstrip().startswith("#"))


class Static(unittest.TestCase):
    def test_no_workflow_uses_a_stored_aws_key_and_each_uses_the_role(self):
        for n in WF:
            c = code_lines(text(n))
            self.assertNotIn("secrets.AWS_ACCESS_KEY_ID", c, n)
            self.assertNotIn("secrets.AWS_SECRET_ACCESS_KEY", c, n)
            self.assertIn("role-to-assume: " + ROLE_ARN, c, n)

    def test_each_can_mint_an_oidc_token(self):
        for n in WF:
            self.assertRegex(code_lines(text(n)), r"permissions:\s*\n(?:\s+[\w-]+: \w+[^\n]*\n)*\s+id-token: write", n)

    def test_workflows_that_open_issues_keep_issues_write(self):
        """A permissions block REMOVES every unlisted permission: adding id-token must not take away issues."""
        for n in ("intel_channel_discovery", "intel_channel_review"):
            self.assertRegex(code_lines(text(n)), r"issues: write", n)

    def test_every_aws_call_is_covered_by_a_grant(self):
        granted = set()
        for s in DOC["Statement"]:
            for a in s["Action"]:
                for r in s["Resource"]:
                    granted.add((a, r))
        invoke_list = {a for s in json.load(open(ROOT / "iam_github_deploy_invoke.json"))["Statement"] for a in s["Resource"]}
        base = "arn:aws:lambda:us-east-1:239677749008:function:"
        for n in WF:
            c = code_lines(text(n))
            for m in re.finditer(r"aws lambda (invoke|update-function-code)[^\n]*\\\n(?:[^\n]*\\\n)*", c):
                fn = re.search(r"--function-name (\S+)", m.group(0)).group(1)
                act = "lambda:InvokeFunction" if m.group(1) == "invoke" else "lambda:UpdateFunctionCode"
                self.assertTrue((act, base + fn) in granted or (act == "lambda:InvokeFunction" and base + fn in invoke_list),
                                f"{n}: {act} on {fn} is granted nowhere in the repo")
            for m in re.finditer(r"aws logs filter-log-events[^\n]*\\\n(?:[^\n]*\\\n)*", c):
                lg = re.search(r"--log-group-name (\S+)", m.group(0)).group(1)
                self.assertIn(("logs:FilterLogEvents", f"arn:aws:logs:us-east-1:239677749008:log-group:{lg}:*"), granted, f"{n}: log group {lg}")
        # and the commands we expect are really there, so the loop above cannot pass by matching nothing
        self.assertIn("aws lambda invoke", code_lines(text("intel_feed")))
        self.assertIn("aws lambda update-function-code", code_lines(text("intel_substack")))
        self.assertIn("aws logs filter-log-events", code_lines(text("intel_channel_review")))

    def test_the_policy_file_asks_for_nothing_broad(self):
        for s in DOC["Statement"]:
            self.assertNotIn("*", "".join(s["Action"]).replace("logs:FilterLogEvents", ""))
            for r in s["Resource"]:
                self.assertNotEqual(r, "*")
                self.assertTrue(r.startswith("arn:aws:") and "239677749008" in r)

    def test_no_other_workflow_was_touched_by_this_change(self):
        """The eleven workflows already on OIDC are not edited here; assert they still carry no stored key either."""
        for p in (ROOT / ".github" / "workflows").glob("*.yml"):
            if p.stem in WF:
                continue
            if "role-to-assume" in p.read_text():
                self.assertNotIn("secrets.AWS_ACCESS_KEY_ID", code_lines(p.read_text()), p.name)


class Fake:
    def __init__(self, denied=(), trust=None, account="239677749008", sub_after_apply=True):
        self.denied, self.calls, self.applied = set(denied), [], False
        self.trust = trust if trust is not None else {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Federated": "x"},
            "Action": "sts:AssumeRoleWithWebIdentity", "Condition": {"StringLike": {T.SUB_KEY: "repo:nzdsf2-gif/relayshield:*"}}}]}

    def get_role(self, RoleName):
        self.calls.append(("get_role", RoleName))
        return {"Role": {"AssumeRolePolicyDocument": self.trust}}

    def simulate_principal_policy(self, PolicySourceArn, ActionNames, ResourceArns, **kw):
        self.calls.append(("simulate", tuple(ActionNames), tuple(ResourceArns)))
        assert len(ActionNames) == 1 and len(ResourceArns) == 1, "one pair per call"
        return {"EvaluationResults": [{"EvalActionName": a, "EvalResourceName": "${ResourceId}",
                                       "EvalDecision": "implicitDeny" if (a, r) in self.denied and not self.applied else "allowed"}
                                      for a in ActionNames for r in ResourceArns], "IsTruncated": False}

    def put_role_policy(self, RoleName, PolicyName, PolicyDocument):
        self.calls.append(("put_role_policy", RoleName, PolicyName))
        self.applied = True
        json.loads(PolicyDocument)

    def writes(self):
        return [c for c in self.calls if c[0].startswith("put_")]


ALL = {(a, r) for s in DOC["Statement"] for a in s["Action"] for r in s["Resource"]}


def go(f, apply=False, account="239677749008"):
    lines = []
    rc = T.run(f, lambda: account, apply, out=lines.append, doc=DOC)
    return rc, "\n".join(lines)


class Decisions(unittest.TestCase):
    def test_wrong_account_refused_nothing_called(self):
        f = Fake()
        rc, out = go(f, True, account="620534471984")
        self.assertEqual((rc, f.calls), (2, []))
        self.assertIn("620534471984", out)

    def test_dry_run_reports_denials_and_writes_nothing(self):
        f = Fake(denied=ALL)
        rc, out = go(f)
        self.assertEqual((rc, f.writes()), (1, []))
        self.assertIn("DENIED", out)
        self.assertIn("Dry run only", out)

    def test_apply_puts_one_new_policy_and_proves_it(self):
        f = Fake(denied=ALL)
        rc, out = go(f, True)
        self.assertEqual(rc, 0)
        self.assertEqual(f.writes(), [("put_role_policy", "relayshield-github-deploy", "relayshield-deploy-intel-ops")])
        self.assertIn("PROVED", out)

    def test_nothing_to_apply_when_everything_is_allowed(self):
        f = Fake()
        rc, out = go(f, True)
        self.assertEqual((rc, f.writes()), (0, []))
        self.assertIn("Nothing to apply", out)

    def test_every_simulation_is_one_pair_and_reported_against_the_resource_asked(self):
        f = Fake(denied=ALL)
        rc, out = go(f)
        sims = [c for c in f.calls if c[0] == "simulate"]
        self.assertEqual(len(sims), len(ALL))
        self.assertNotIn("ResourceId", out, "the simulator's echoed name must never be what the report shows")
        self.assertIn("relayshield-intel-discovery", out)

    def test_trust_mismatch_is_reported_and_fails(self):
        trust = {"Statement": [{"Condition": {"StringEquals": {T.SUB_KEY: "repo:nzdsf2-gif/relayshield:environment:prod"}}}]}
        rc, out = go(Fake(trust=trust))
        self.assertEqual(rc, 1)
        self.assertIn("MISMATCH", out)

    def test_trust_matching_main_via_wildcard_passes(self):
        rc, out = go(Fake())
        self.assertEqual(rc, 0)
        self.assertIn("matches", out)

    def test_extra_constraint_on_trust_is_flagged_as_unsimulatable(self):
        trust = {"Statement": [{"Condition": {"StringLike": {T.SUB_KEY: "repo:nzdsf2-gif/relayshield:*",
                                                              "token.actions.githubusercontent.com:job_workflow_ref": "x"}}}]}
        _rc, out = go(Fake(trust=trust))
        self.assertIn("job_workflow_ref", out)


try:
    import boto3
    from botocore.stub import Stubber
    HAVE = True
except Exception:  # pragma: no cover
    HAVE = False


@unittest.skipUnless(HAVE, "boto3 not installed: the real-model layer did not run")
class RealModels(unittest.TestCase):
    def test_every_request_and_response_matches_the_real_iam_model(self):
        iam = boto3.client("iam", region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="x")
        s = Stubber(iam)
        trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Federated": f"arn:aws:iam::239677749008:oidc-provider/token.actions.githubusercontent.com"},
                 "Action": "sts:AssumeRoleWithWebIdentity", "Condition": {"StringLike": {T.SUB_KEY: "repo:nzdsf2-gif/relayshield:*"}}}]}
        import datetime
        role = {"Path": "/", "RoleName": T.ROLE, "RoleId": "AROAEXAMPLE0000000", "Arn": ROLE_ARN, "CreateDate": datetime.datetime(2026, 1, 1),
                "AssumeRolePolicyDocument": json.dumps(trust)}

        PAIRS = sorted(ALL, key=lambda p: [(a, r) for s_ in DOC["Statement"] for a in s_["Action"] for r in s_["Resource"]].index(p))

        def sim_exp(a, r):
            return {"PolicySourceArn": ROLE_ARN, "ActionNames": [a], "ResourceArns": [r]}

        def sim_resp(a, r, decision):
            # the real service echoed '${ResourceId}' as the resource name: the tool must not depend on it
            return {"EvaluationResults": [{"EvalActionName": a, "EvalResourceName": "${ResourceId}", "EvalDecision": decision}], "IsTruncated": False}
        s.add_response("get_role", {"Role": role}, {"RoleName": T.ROLE})
        for a, r in PAIRS:
            s.add_response("simulate_principal_policy", sim_resp(a, r, "implicitDeny"), sim_exp(a, r))
        s.add_response("put_role_policy", {}, {"RoleName": T.ROLE, "PolicyName": T.POLICY_NAME, "PolicyDocument": json.dumps(DOC)})
        for a, r in PAIRS:
            s.add_response("simulate_principal_policy", sim_resp(a, r, "allowed"), sim_exp(a, r))
        lines = []
        with s:
            rc = T.run(iam, lambda: "239677749008", True, out=lines.append, doc=DOC)
            s.assert_no_pending_responses()
        self.assertEqual(rc, 0, "\n".join(lines))
        self.assertIn("PROVED", "\n".join(lines))

    def test_the_real_policy_file_fits_the_inline_limit_and_names_a_legal_policy(self):
        self.assertLess(len(json.dumps(DOC)), 2000)


if __name__ == "__main__":
    unittest.main()
