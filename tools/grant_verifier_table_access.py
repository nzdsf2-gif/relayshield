#!/usr/bin/env python3
"""Let the verifier Lambda WRITE its two tables, and nothing else.

    AWS_PROFILE=relayshield python3 tools/grant_verifier_table_access.py --function NAME          # dry run
    AWS_PROFILE=relayshield python3 tools/grant_verifier_table_access.py --function NAME --apply

WHY THIS EXISTS INSTEAD OF tools/grant_breach_cache_access.py. That tool edits the managed
policy `relayshield-first-seen-write` and refuses unless it is already attached to the role.
The verifier runs as its OWN role (relayshield-tap-verifier-role), which does not carry it, so
the tool stops with "is not attached". Attaching a shared policy to a role to make a tool work
would widen that role beyond what it needs; a small dedicated policy does not.

Creates the customer-managed policy `relayshield-verifier-tables-write`:
  dynamodb:PutItem on relayshield_verifier_nonces (one conditional put per request: the
  store never reads, scans or deletes) and on relayshield_verifier_telemetry (one put per
  rejection, opted-in accounts only). No read, no update, no delete: a leaked credential
  could add rows, not read or erase them.

It reads the function's role from AWS rather than assuming it, refuses to overwrite an existing
policy of that name that covers different tables, attaches it, then asks IAM's simulator whether
the role can write both tables and exits non-zero if not. A role cannot widen its own
permissions, so this runs as the operator (relayshield-deployer), never inside Actions.

If the role is at the managed-policy cap the attach fails with LimitExceeded: that is the IAM
split in iam_role_split.md, not something to work around here.
"""
import argparse
import json
import subprocess
import sys

ACCOUNT = "239677749008"
POLICY = "relayshield-verifier-tables-write"
TABLES = ("relayshield_verifier_nonces", "relayshield_verifier_telemetry")
ACTIONS = ["dynamodb:PutItem"]


def aws(*args, check=True):
    r = subprocess.run(["aws", "--no-cli-pager", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"aws {' '.join(args[:2])} failed: {r.stderr.strip()[:400]}")
    return r


def table_arn(table, region):
    return f"arn:aws:dynamodb:{region}:{ACCOUNT}:table/{table}"


def build_document(arns):
    return {"Version": "2012-10-17", "Statement": [{
        "Sid": "VerifierTablesPutOnly", "Effect": "Allow", "Action": ACTIONS, "Resource": list(arns)}]}


def resources_of(doc):
    stmts = doc.get("Statement") if isinstance(doc, dict) else None
    if not isinstance(stmts, list) or not stmts:
        return None
    res = stmts[0].get("Resource")
    return sorted(res) if isinstance(res, list) else [res]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--function", required=True)
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)

    got = aws("sts", "get-caller-identity", "--query", "Account", "--output", "text").stdout.strip()
    if got != ACCOUNT:
        print(f"STOP: credentials resolve to account {got}, not {ACCOUNT}. Prefix with AWS_PROFILE=relayshield.")
        return 2
    arns = [table_arn(t, a.region) for t in TABLES]
    # The tables must exist: a grant on a table that is not there succeeds and protects nothing.
    for t in TABLES:
        r = aws("dynamodb", "describe-table", "--table-name", t, "--region", a.region,
                "--query", "Table.TableStatus", "--output", "text", check=False)
        status = r.stdout.strip()
        if r.returncode != 0 or status != "ACTIVE":
            print(f"STOP: table {t} is not ACTIVE ({status or r.stderr.strip()[:200]}). "
                  "Run the setup script first; nothing was changed.")
            return 5
    role_arn = aws("lambda", "get-function-configuration", "--function-name", a.function, "--region", a.region,
                   "--query", "Role", "--output", "text").stdout.strip()
    role = role_arn.rsplit("/", 1)[-1]
    doc = build_document(arns)
    print(f"function {a.function} runs as role {role}")
    print(f"policy {POLICY} would allow {', '.join(ACTIONS)} on exactly:")
    for arn in arns:
        print(f"  {arn}")
    if not a.apply:
        print("DRY RUN. Nothing was changed. Re-run with --apply.")
        return 0
    policy_arn = f"arn:aws:iam::{ACCOUNT}:policy/{POLICY}"
    if aws("iam", "get-policy", "--policy-arn", policy_arn, check=False).returncode == 0:
        vid = aws("iam", "get-policy", "--policy-arn", policy_arn, "--query", "Policy.DefaultVersionId",
                  "--output", "text").stdout.strip()
        current = json.loads(aws("iam", "get-policy-version", "--policy-arn", policy_arn, "--version-id", vid,
                                 "--query", "PolicyVersion.Document", "--output", "json").stdout)
        if resources_of(current) != sorted(arns):
            print(f"STOP: {POLICY} already exists for different resources ({resources_of(current)}). Not overwriting.")
            return 3
        print(f"{POLICY} already exists with the right resources.")
    else:
        aws("iam", "create-policy", "--policy-name", POLICY, "--policy-document", json.dumps(doc),
            "--query", "Policy.Arn", "--output", "text")
        print(f"created {POLICY}")
    aws("iam", "attach-role-policy", "--role-name", role, "--policy-arn", policy_arn)
    # ONE CALL PER TABLE. simulate-principal-policy returns one EvaluationResult per ACTION, not one
    # per resource, so asking about both ARNs at once yields a single aggregated row. The first
    # version of this tool counted rows against tables and reported a granted, attached policy as
    # a failure on its first real run; the stand-in aws it was tested against returned one row per
    # ARN, which the real API does not. Per-table calls make each answer unambiguous.
    sim = {}
    for t, arn in zip(TABLES, arns):
        out = json.loads(aws("iam", "simulate-principal-policy", "--policy-source-arn", role_arn,
                             "--action-names", *ACTIONS, "--resource-arns", arn,
                             "--query", "EvaluationResults[].EvalDecision", "--output", "json").stdout)
        sim[t] = out[0] if len(out) == 1 else "no-answer"
    print(f"IAM simulator: {', '.join(ACTIONS)} -> {sim}")
    if any(d != "allowed" for d in sim.values()):
        print("STOP: the role still cannot write both tables.")
        return 4
    print("done. The proof is a real request after VERIFIER_NONCE_TABLE is set, not this simulation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
