"""tools/grant_verifier_table_access.py against a stand-in `aws`. What matters: PutItem on the
two tables and nothing wider, a dry run writes nothing, a missing table or the wrong account
stops before any write, an existing policy for other tables is not overwritten, and a simulator
answer that is not `allowed` for BOTH tables fails the run."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
TOOL = ROOT / "tools" / "grant_verifier_table_access.py"
ARN = "arn:aws:dynamodb:us-east-1:239677749008:table/"

FAKE_AWS = r'''#!__PY__
import json, os, sys
p = os.environ["FAKE_AWS_STATE"]; st = json.load(open(p))
args = [a for a in sys.argv[1:] if a != "--no-cli-pager"]
st.setdefault("log", []).append(args)
def done(out="", rc=0, err=""):
    json.dump(st, open(p, "w")); sys.stdout.write(out); sys.stderr.write(err); sys.exit(rc)
def opt(n): return args[args.index(n) + 1] if n in args else None
svc, cmd = args[0], args[1]
if svc == "sts": done(st["account"] + "\n")
if svc == "dynamodb" and cmd == "describe-table":
    t = opt("--table-name")
    if t in st["tables"]: done(st["tables"][t] + "\n")
    done(rc=254, err="ResourceNotFoundException")
if svc == "lambda": done("arn:aws:iam::239677749008:role/tap-role\n")
if svc == "iam" and cmd == "get-policy":
    if "Policy.DefaultVersionId" in " ".join(args): done("v1\n")
    done("{}") if st.get("policy") else done(rc=254, err="NoSuchEntity")
if svc == "iam" and cmd == "get-policy-version": done(json.dumps(st["policy"]))
if svc == "iam" and cmd == "create-policy":
    st["policy"] = json.loads(opt("--policy-document")); st["created"] = True; done("arn\n")
if svc == "iam" and cmd == "attach-role-policy":
    st.setdefault("attached", []).append(opt("--role-name")); done()
if svc == "iam" and cmd == "simulate-principal-policy":
    arns = args[args.index("--resource-arns") + 1:]
    arns = [a for a in arns if not a.startswith("--")][:1] if "--query" in args[args.index("--resource-arns"):] else arns
    # the REAL api returns ONE row per action however many resources were asked about
    st.setdefault("sim_calls", []).append(arns)
    if len(arns) != 1:
        done(json.dumps(["allowed"]))
    name = arns[0].rsplit("/", 1)[-1]
    done(json.dumps(st["simulate"].get(name, ["allowed"]) if isinstance(st["simulate"], dict) else st["simulate"]))
done(rc=1, err="unexpected: " + " ".join(args))
'''


class Case(unittest.TestCase):
    def setUp(self):
        self.td = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.td, ignore_errors=True))
        (self.td / "bin").mkdir()
        exe = self.td / "bin" / "aws"
        exe.write_text(FAKE_AWS.replace("__PY__", sys.executable))
        exe.chmod(0o755)
        self.sp = self.td / "state.json"
        self.state = {"account": "239677749008", "simulate": {},
                      "tables": {"relayshield_verifier_nonces": "ACTIVE",
                                 "relayshield_verifier_telemetry": "ACTIVE"}}

    def run_tool(self, *extra, **state):
        self.state.update(state)
        self.sp.write_text(json.dumps(self.state))
        env = dict(os.environ, PATH=f"{self.td / 'bin'}{os.pathsep}{os.environ['PATH']}", FAKE_AWS_STATE=str(self.sp))
        r = subprocess.run([sys.executable, "-B", str(TOOL), "--function", "f", *extra], env=env,
                           capture_output=True, text=True, timeout=60)
        return r, json.loads(self.sp.read_text())


class Grant(Case):
    def test_apply_grants_put_only_on_exactly_the_two_tables_and_attaches_it(self):
        r, st = self.run_tool("--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        stmt = st["policy"]["Statement"][0]
        self.assertEqual(stmt["Action"], ["dynamodb:PutItem"])
        self.assertEqual(sorted(stmt["Resource"]),
                         [ARN + "relayshield_verifier_nonces", ARN + "relayshield_verifier_telemetry"])
        self.assertEqual(st["attached"], ["tap-role"])

    def test_a_dry_run_writes_nothing(self):
        r, st = self.run_tool()
        self.assertEqual(r.returncode, 0)
        self.assertIn("DRY RUN", r.stdout)
        self.assertNotIn("created", st)
        self.assertNotIn("attached", st)

    def test_the_wrong_account_stops_before_any_write(self):
        r, st = self.run_tool("--apply", account="620534471984")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("created", st)

    def test_a_table_that_is_not_active_stops_before_any_write(self):
        r, st = self.run_tool("--apply", tables={"relayshield_verifier_nonces": "ACTIVE"})
        self.assertEqual(r.returncode, 5)
        self.assertIn("relayshield_verifier_telemetry", r.stdout)
        self.assertNotIn("created", st)
        r, st = self.run_tool("--apply", tables={"relayshield_verifier_nonces": "CREATING",
                                                  "relayshield_verifier_telemetry": "ACTIVE"})
        self.assertEqual(r.returncode, 5)

    def test_an_existing_policy_for_other_tables_is_not_overwritten(self):
        other = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": ["dynamodb:PutItem"],
                                                         "Resource": [ARN + "something_else"]}]}
        r, st = self.run_tool("--apply", policy=other)
        self.assertEqual(r.returncode, 3)
        self.assertNotIn("attached", st)

    def test_rerunning_with_the_right_policy_is_a_clean_noop_that_still_attaches(self):
        good = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": ["dynamodb:PutItem"],
                "Resource": [ARN + "relayshield_verifier_telemetry", ARN + "relayshield_verifier_nonces"]}]}
        r, st = self.run_tool("--apply", policy=good)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("created", st)
        self.assertEqual(st["attached"], ["tap-role"])

    def test_the_simulator_is_asked_once_per_table_because_the_real_api_returns_one_row_per_action(self):
        r, st = self.run_tool("--apply")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(len(st["sim_calls"]), 2)
        self.assertTrue(all(len(c) == 1 for c in st["sim_calls"]))

    def test_one_table_not_allowed_fails_the_run_and_names_which(self):
        for bad in ("relayshield_verifier_nonces", "relayshield_verifier_telemetry"):
            r, _ = self.run_tool("--apply", simulate={bad: ["implicitDeny"]})
            self.assertEqual(r.returncode, 4, (bad, r.stdout))
            self.assertIn("STOP", r.stdout)
            self.assertIn("implicitDeny", r.stdout)

    def test_an_empty_simulator_answer_fails_the_run(self):
        r, _ = self.run_tool("--apply", simulate={"relayshield_verifier_nonces": [],
                                                   "relayshield_verifier_telemetry": []})
        self.assertEqual(r.returncode, 4)


class Source(unittest.TestCase):
    def test_no_wider_action_than_put_item(self):
        import ast
        tree = ast.parse(TOOL.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "ACTIONS" for t in node.targets):
                self.assertEqual(ast.literal_eval(node.value), ["dynamodb:PutItem"])
                return
        self.fail("ACTIONS not found")


if __name__ == "__main__":
    unittest.main()
