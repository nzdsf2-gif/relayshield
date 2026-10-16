"""The two operator tools, run against a stand-in `aws` executable that records what it was
asked to do. What matters: the private key never appears in any output or argument, the
file that carries it is private and is gone afterwards, and nothing is written to the wrong
account, to an existing secret, or on a dry run."""
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import x401_jose as jose  # noqa: E402

FAKE_AWS = r'''#!__PY__
import json, os, sys
state_path = os.environ["FAKE_AWS_STATE"]
st = json.load(open(state_path))
args = sys.argv[1:]
args = [a for a in args if a != "--no-cli-pager"]
st.setdefault("log", []).append(args)
def done(out="", rc=0, err=""):
    json.dump(st, open(state_path, "w"))
    sys.stdout.write(out); sys.stderr.write(err); sys.exit(rc)
def opt(name):
    return args[args.index(name) + 1] if name in args else None
svc, cmd = args[0], args[1]
if svc == "sts":
    done(st["account"] + "\n")
if svc == "secretsmanager" and cmd == "describe-secret":
    sid = opt("--secret-id")
    if sid in st["secrets"]:
        done(("arn:aws:secretsmanager:us-east-1:239677749008:secret:" + sid + "-AbCdEf\n") if opt("--query") == "ARN" else "{}")
    done(rc=254, err="An error occurred (ResourceNotFoundException) when calling the DescribeSecret operation")
if svc == "secretsmanager" and cmd in ("create-secret", "put-secret-value"):
    sv = opt("--secret-string")
    assert sv.startswith("file://"), "the secret must be passed as a file, never on the command line"
    path = sv[len("file://"):]
    st["secret_file_mode"] = oct(os.stat(path).st_mode & 0o777)
    st["secret_dir_mode"] = oct(os.stat(os.path.dirname(path)).st_mode & 0o777)
    st["secrets"][opt("--name") or opt("--secret-id")] = open(path).read()
    st["secret_file_path"] = path
    done("name\n")
if svc == "lambda":
    done("arn:aws:iam::239677749008:role/verifier-role\n")
if svc == "iam" and cmd == "get-policy":
    if "Policy.DefaultVersionId" in " ".join(args):
        done("v1\n")
    if st.get("policy"):
        done("{}")
    done(rc=254, err="NoSuchEntity")
if svc == "iam" and cmd == "get-policy-version":
    done(json.dumps(st["policy"]))
if svc == "iam" and cmd == "create-policy":
    st["policy"] = json.loads(opt("--policy-document"))
    done("arn\n")
if svc == "iam" and cmd == "attach-role-policy":
    st.setdefault("attached", []).append([opt("--role-name"), opt("--policy-arn")])
    done()
if svc == "iam" and cmd == "simulate-principal-policy":
    done(json.dumps([st.get("simulate", "allowed")]))
done(rc=1, err="unexpected: " + " ".join(args))
'''


class Fake:
    def __init__(self, td, **state):
        self.td = pathlib.Path(td)
        self.bin = self.td / "bin"
        self.bin.mkdir()
        exe = self.bin / "aws"
        exe.write_text(FAKE_AWS.replace("__PY__", sys.executable))
        exe.chmod(0o755)
        self.state_path = self.td / "state.json"
        base = {"account": "239677749008", "secrets": {}, "log": []}
        base.update(state)
        self.state_path.write_text(json.dumps(base))
        self.env = dict(os.environ, PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}", FAKE_AWS_STATE=str(self.state_path))

    def state(self):
        return json.loads(self.state_path.read_text())

    def run(self, script, *args):
        return subprocess.run([sys.executable, "-B", str(ROOT / "tools" / script), *args], env=self.env,
                              capture_output=True, text=True, timeout=60)


def pubkey_stub(td):
    p = pathlib.Path(td) / "relayshield_x401_pubkey.py"
    p.write_text('"""stub"""\n\nPUBLIC_JWK = None\nKID = "did:web:api.relayshield.net#x401-1"\n')
    return p


class KeyTool(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.td, ignore_errors=True))

    def apply(self, fake, *extra):
        return fake.run("generate_x401_verifier_key.py", "--apply", "--pubkey-file", str(self.pub), *extra)

    def test_it_stores_the_private_key_publishes_the_public_one_and_leaks_nothing(self):
        fake = Fake(self.td)
        self.pub = pubkey_stub(self.td)
        r = self.apply(fake)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        st = fake.state()
        stored = json.loads(st["secrets"]["relayshield/x401_verifier_key"])
        self.assertIn("d", stored)
        # the PRIVATE scalar appears nowhere a human or a log could see it
        self.assertNotIn(stored["d"], r.stdout + r.stderr)
        self.assertNotIn(stored["d"], json.dumps(st["log"]), "the key must be passed as a file, not an argument")
        self.assertNotIn(stored["d"], self.pub.read_text())
        # the file that carried it was private and is gone
        self.assertEqual(st["secret_file_mode"], "0o600")
        self.assertEqual(st["secret_dir_mode"], "0o700")
        self.assertFalse(os.path.exists(st["secret_file_path"]))
        # the published key is the stored key's public half, and signs verifiably
        ns = {}
        exec(compile(self.pub.read_text(), "pub", "exec"), ns)
        pub = ns["PUBLIC_JWK"]
        self.assertNotIn("d", pub)
        self.assertEqual((pub["x"], pub["y"]), (stored["x"], stored["y"]))
        tok = jose.jws_sign_es256(stored, {"kid": ns["KID"]}, {"a": 1})
        jose.jws_verify(tok, [pub], {"ES256"})
        self.assertEqual(ns["KID"], "did:web:api.relayshield.net#x401-1")

    def test_a_dry_run_changes_nothing(self):
        fake = Fake(self.td)
        self.pub = pubkey_stub(self.td)
        before = self.pub.read_text()
        r = fake.run("generate_x401_verifier_key.py", "--pubkey-file", str(self.pub))
        self.assertEqual(r.returncode, 0)
        self.assertIn("DRY RUN", r.stdout)
        self.assertEqual(fake.state()["secrets"], {})
        self.assertEqual(self.pub.read_text(), before)

    def test_the_wrong_account_stops_everything_before_a_key_exists(self):
        fake = Fake(self.td, account="620534471984")
        self.pub = pubkey_stub(self.td)
        r = self.apply(fake)
        self.assertEqual(r.returncode, 2)
        self.assertIn("620534471984", r.stdout)
        self.assertEqual(fake.state()["secrets"], {})
        self.assertIsNone(self.pub.read_text().count("PUBLIC_JWK = {") or None)

    def test_an_existing_key_is_never_replaced_without_rotate(self):
        fake = Fake(self.td, secrets={"relayshield/x401_verifier_key": "{\"keep\": true}"})
        self.pub = pubkey_stub(self.td)
        r = self.apply(fake)
        self.assertEqual(r.returncode, 3)
        self.assertEqual(fake.state()["secrets"]["relayshield/x401_verifier_key"], "{\"keep\": true}")
        r = self.apply(fake, "--rotate")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("d", json.loads(fake.state()["secrets"]["relayshield/x401_verifier_key"]))
        self.assertTrue(any(c[1] == "put-secret-value" for c in fake.state()["log"]))

    def test_the_repo_copy_of_the_pubkey_module_is_untouched_by_the_tests(self):
        text = (ROOT / "relayshield_x401_pubkey.py").read_text()
        self.assertIn("PUBLIC_JWK = None", text)


class GrantTool(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(self.td, ignore_errors=True))
        self.fake = Fake(self.td, secrets={"relayshield/x401_verifier_key": "{}"})

    def test_it_grants_get_secret_value_on_that_one_secret_only(self):
        r = self.fake.run("grant_x401_secret_access.py", "--function", "my-verifier", "--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        st = self.fake.state()
        stmt = st["policy"]["Statement"][0]
        self.assertEqual(stmt["Action"], ["secretsmanager:GetSecretValue"])
        self.assertTrue(stmt["Resource"].startswith("arn:aws:secretsmanager:us-east-1:239677749008:secret:relayshield/x401_verifier_key"))
        self.assertNotIn("*", stmt["Resource"])
        self.assertEqual(st["attached"][0][0], "verifier-role")

    def test_dry_run_changes_nothing(self):
        r = self.fake.run("grant_x401_secret_access.py", "--function", "my-verifier")
        self.assertEqual(r.returncode, 0)
        self.assertIn("DRY RUN", r.stdout)
        self.assertNotIn("policy", self.fake.state())

    def test_wrong_account_and_a_failing_simulation_are_refused(self):
        bad = Fake(tempfile.mkdtemp(), account="620534471984")
        r = bad.run("grant_x401_secret_access.py", "--function", "f", "--apply")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("policy", bad.state())
        st = self.fake.state()
        st["simulate"] = "implicitDeny"
        self.fake.state_path.write_text(json.dumps(st))
        r = self.fake.run("grant_x401_secret_access.py", "--function", "f", "--apply")
        self.assertEqual(r.returncode, 4)
        self.assertIn("still cannot read", r.stdout)

    def test_an_existing_policy_for_another_resource_is_not_overwritten(self):
        st = self.fake.state()
        st["policy"] = {"Statement": [{"Resource": "arn:aws:secretsmanager:us-east-1:239677749008:secret:other"}]}
        self.fake.state_path.write_text(json.dumps(st))
        r = self.fake.run("grant_x401_secret_access.py", "--function", "f", "--apply")
        self.assertEqual(r.returncode, 3)
        self.assertNotIn("attached", self.fake.state())


if __name__ == "__main__":
    unittest.main()
