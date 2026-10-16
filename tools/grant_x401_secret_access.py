#!/usr/bin/env python3
"""Let the verifier Lambda read the x401 signing secret, and nothing else.

    AWS_PROFILE=relayshield python3 tools/grant_x401_secret_access.py --function NAME          # dry run
    AWS_PROFILE=relayshield python3 tools/grant_x401_secret_access.py --function NAME --apply

Creates the customer-managed policy `relayshield-x401-secret-read`, allowing
secretsmanager:GetSecretValue on THAT ONE SECRET'S ARN, and attaches it to the role the
function runs as. It then asks IAM's simulator whether the role can read the secret, and
exits non-zero if it cannot.

A role cannot widen its own permissions, so this runs as the operator (relayshield-deployer),
never inside Actions. It reads the function's role from AWS rather than assuming it: the
repo does not record which role the verifier Lambda uses.

If the role already has the maximum number of managed policies the attach fails with
LimitExceeded; that is the IAM split in iam_role_split.md, not something to work around here.
"""
import argparse
import json
import subprocess
import sys

ACCOUNT = "239677749008"
POLICY = "relayshield-x401-secret-read"
DEFAULT_SECRET = "relayshield/x401_verifier_key"


def aws(*args, check=True):
    r = subprocess.run(["aws", "--no-cli-pager", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"aws {' '.join(args[:2])} failed: {r.stderr.strip()[:400]}")
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--function", required=True)
    ap.add_argument("--secret-name", default=DEFAULT_SECRET)
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)

    got = aws("sts", "get-caller-identity", "--query", "Account", "--output", "text").stdout.strip()
    if got != ACCOUNT:
        print(f"STOP: credentials resolve to account {got}, not {ACCOUNT}. Prefix with AWS_PROFILE=relayshield.")
        return 2
    role_arn = aws("lambda", "get-function-configuration", "--function-name", a.function, "--region", a.region,
                   "--query", "Role", "--output", "text").stdout.strip()
    role = role_arn.rsplit("/", 1)[-1]
    secret_arn = aws("secretsmanager", "describe-secret", "--secret-id", a.secret_name, "--region", a.region,
                     "--query", "ARN", "--output", "text").stdout.strip()
    doc = {"Version": "2012-10-17", "Statement": [{
        "Sid": "ReadX401VerifierKey", "Effect": "Allow",
        "Action": ["secretsmanager:GetSecretValue"], "Resource": secret_arn}]}
    print(f"function {a.function} runs as role {role}")
    print(f"policy {POLICY} would allow secretsmanager:GetSecretValue on exactly:\n  {secret_arn}")
    if not a.apply:
        print("DRY RUN. Nothing was changed. Re-run with --apply.")
        return 0
    policy_arn = f"arn:aws:iam::{ACCOUNT}:policy/{POLICY}"
    if aws("iam", "get-policy", "--policy-arn", policy_arn, check=False).returncode == 0:
        # same name, possibly a different secret: refuse to guess which statement to keep
        current = json.loads(aws("iam", "get-policy-version", "--policy-arn", policy_arn, "--version-id",
                                 aws("iam", "get-policy", "--policy-arn", policy_arn, "--query",
                                     "Policy.DefaultVersionId", "--output", "text").stdout.strip(),
                                 "--query", "PolicyVersion.Document", "--output", "json").stdout)
        res = current["Statement"][0]["Resource"] if isinstance(current.get("Statement"), list) else None
        if res != secret_arn:
            print(f"STOP: {POLICY} already exists for a different resource ({res}). Not overwriting.")
            return 3
        print(f"{POLICY} already exists with the right resource.")
    else:
        aws("iam", "create-policy", "--policy-name", POLICY, "--policy-document", json.dumps(doc),
            "--query", "Policy.Arn", "--output", "text")
        print(f"created {POLICY}")
    aws("iam", "attach-role-policy", "--role-name", role, "--policy-arn", policy_arn)
    sim = json.loads(aws("iam", "simulate-principal-policy", "--policy-source-arn", role_arn,
                         "--action-names", "secretsmanager:GetSecretValue", "--resource-arns", secret_arn,
                         "--query", "EvaluationResults[].EvalDecision", "--output", "json").stdout)
    print(f"IAM simulator: secretsmanager:GetSecretValue -> {sim}")
    if sim != ["allowed"]:
        print("STOP: the role still cannot read the secret.")
        return 4
    print("done. The proof is the next real call: a challenge request must return 200, not `verifier_not_configured`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
