"""tools/grant_feed_first_seen_write.py, executed against a fake boto3 that
models IAM's behaviour: put_role_policy REPLACES a same-named policy silently,
and a new policy takes a moment to show up in a simulation."""
import contextlib
import importlib.util
import io
import json
import pathlib
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "grant_feed", ROOT / "tools" / "grant_feed_first_seen_write.py")
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

FEED_ROLE = "arn:aws:iam::239677749008:role/relayshield-intel-feed-role"
SHARED = "arn:aws:iam::239677749008:role/" + g.SHARED_ROLE


class FakeIam:
    def __init__(self, decision="implicitDeny", policies=(), lag=0):
        self.decision, self.policies, self.lag = decision, list(policies), lag
        self.put, self.sims = [], 0

    def simulate_principal_policy(self, **kw):
        self.sims += 1
        assert kw["ActionNames"] == ["dynamodb:PutItem"]
        assert kw["ResourceArns"] == [g.TABLE_ARN]
        if self.put and self.sims > 1 + self.lag:
            return {"EvaluationResults": [{"EvalDecision": "allowed"}]}
        return {"EvaluationResults": [{"EvalDecision": self.decision}]}

    def list_role_policies(self, RoleName):
        return {"PolicyNames": self.policies}

    def put_role_policy(self, **kw):
        self.put.append(kw)


class FakeBoto3:
    def __init__(self, iam, account="239677749008", role=FEED_ROLE):
        self.iam, self.account, self.role = iam, account, role

    def client(self, name, **kw):
        if name == "sts":
            return types.SimpleNamespace(
                get_caller_identity=lambda: {"Account": self.account})
        if name == "lambda":
            return types.SimpleNamespace(
                get_function_configuration=lambda FunctionName: {"Role": self.role})
        return self.iam


def run(iam, *args, **kw):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = g.main(list(args), boto3=FakeBoto3(iam, **kw), sleep=lambda s: None)
    return rc, out.getvalue(), err.getvalue()


class Grant(unittest.TestCase):
    def test_without_apply_it_reads_and_writes_nothing(self):
        iam = FakeIam()
        rc, out, _ = run(iam)
        self.assertEqual(rc, 0)
        self.assertEqual(iam.put, [])
        self.assertIn("implicitDeny", out)
        self.assertIn("READ-ONLY", out)

    def test_apply_adds_a_put_only_policy_on_the_one_table(self):
        iam = FakeIam()
        rc, out, _ = run(iam, "--apply")
        self.assertEqual(rc, 0)
        self.assertEqual(len(iam.put), 1)
        put = iam.put[0]
        self.assertEqual(put["RoleName"], "relayshield-intel-feed-role")
        self.assertEqual(put["PolicyName"], "relayshield-first-seen-put")
        doc = json.loads(put["PolicyDocument"])
        (stmt,) = doc["Statement"]
        self.assertEqual(stmt["Effect"], "Allow")
        self.assertEqual(stmt["Action"], ["dynamodb:PutItem"])
        self.assertEqual(stmt["Resource"], g.TABLE_ARN)
        self.assertIn("is now: allowed", out)

    def test_it_waits_for_iam_to_catch_up(self):
        iam = FakeIam(lag=3)
        rc, out, _ = run(iam, "--apply")
        self.assertEqual(rc, 0)
        self.assertGreater(iam.sims, 3)

    def test_already_allowed_changes_nothing(self):
        iam = FakeIam(decision="allowed")
        rc, out, _ = run(iam, "--apply")
        self.assertEqual(rc, 0)
        self.assertEqual(iam.put, [])
        self.assertIn("Already allowed", out)

    def test_it_never_overwrites_a_policy_of_the_same_name(self):
        iam = FakeIam(policies=["relayshield-first-seen-put"])
        rc, _, err = run(iam, "--apply")
        self.assertEqual(rc, 4)
        self.assertEqual(iam.put, [])
        self.assertIn("Not overwriting", err)

    def test_the_wrong_account_is_refused_before_anything_is_read(self):
        iam = FakeIam()
        rc, _, err = run(iam, "--apply", account="620534471984")
        self.assertEqual(rc, 2)
        self.assertEqual((iam.put, iam.sims), ([], 0))
        self.assertIn("AWS_PROFILE=relayshield", err)

    def test_it_will_not_touch_the_full_shared_role(self):
        iam = FakeIam()
        rc, _, err = run(iam, "--apply", role=SHARED)
        self.assertEqual(rc, 3)
        self.assertEqual(iam.put, [])
        self.assertIn("SHARED role", err)

    def test_the_policy_grants_exactly_one_action_and_one_resource(self):
        (stmt,) = g.POLICY["Statement"]
        self.assertEqual(stmt["Action"], ["dynamodb:PutItem"])
        self.assertEqual(
            stmt["Resource"],
            "arn:aws:dynamodb:us-east-1:239677749008:table/relayshield_intel_first_seen")


if __name__ == "__main__":
    unittest.main()
