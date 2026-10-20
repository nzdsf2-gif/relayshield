#!/usr/bin/env python3
"""Let relayshield-intel-feed write relayshield_intel_first_seen.

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/grant_feed_first_seen_write.py
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/grant_feed_first_seen_write.py --apply

Without --apply it only READS and prints the decision. 2026-10-20:

    arn:aws:iam::239677749008:role/relayshield-intel-feed-role   implicitDeny

The feed Lambda runs under its OWN role, not the shared relayshield-breach-check
role that carries the first-seen write policy for the monitor, so the feed's
first-seen flush (relayshield_intel_feed._flush_first_seen) would be denied on
its first call and stop after one warning.

WHAT IT WRITES. One NEW inline policy, relayshield-first-seen-put, granting
dynamodb:PutItem on that one table ARN and nothing else. It is a new name on a
role that has its own inline budget, so it cannot replace or widen anything that
exists, and it refuses to run if a policy of that name is already there rather
than overwriting it (put-role-policy replaces a same-named policy silently).

It does not touch the shared role: that role's 10,240-byte inline budget is full,
and it already has this permission.
"""
import argparse
import json
import sys
import time

REQUIRED_ACCOUNT = "239677749008"
REGION = "us-east-1"
FUNC = "relayshield-intel-feed"
TABLE = "relayshield_intel_first_seen"
POLICY_NAME = "relayshield-first-seen-put"
SHARED_ROLE = "relayshield-breach-check-role-1sapnwdl"
TABLE_ARN = f"arn:aws:dynamodb:{REGION}:{REQUIRED_ACCOUNT}:table/{TABLE}"
POLICY = {
    "Version": "2012-10-17",
    "Statement": [{
        "Sid": "FeedFirstSeenPut",
        "Effect": "Allow",
        "Action": ["dynamodb:PutItem"],
        "Resource": TABLE_ARN,
    }],
}


def _decision(iam, role_arn):
    res = iam.simulate_principal_policy(
        PolicySourceArn=role_arn, ActionNames=["dynamodb:PutItem"],
        ResourceArns=[TABLE_ARN])
    return res["EvaluationResults"][0]["EvalDecision"]


def main(argv=None, boto3=None, sleep=time.sleep) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    if boto3 is None:
        import boto3

    who = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]
    if who != REQUIRED_ACCOUNT:
        print(f"Refusing to run: credentials resolve to account {who}, not "
              f"{REQUIRED_ACCOUNT}. Prefix the command with AWS_PROFILE=relayshield.",
              file=sys.stderr)
        return 2

    role_arn = boto3.client("lambda", region_name=REGION).get_function_configuration(
        FunctionName=FUNC)["Role"]
    role = role_arn.rsplit("/", 1)[-1]
    iam = boto3.client("iam")
    print(f"function  {FUNC}\nrole      {role_arn}")

    if role == SHARED_ROLE:
        print("\nThis function runs under the SHARED role, whose inline budget is full "
              "and which already carries relayshield-first-seen-write. Not adding "
              "anything here; check that policy instead.", file=sys.stderr)
        return 3

    before = _decision(iam, role_arn)
    print(f"dynamodb:PutItem on {TABLE}: {before}")
    if before == "allowed":
        print("\nAlready allowed. Nothing to do.")
        return 0

    existing = iam.list_role_policies(RoleName=role).get("PolicyNames", [])
    if POLICY_NAME in existing:
        print(f"\nSTOP: a policy named {POLICY_NAME} already exists on {role} and the "
              f"decision is still {before}, so something else (a permissions boundary "
              f"or an explicit deny) is the cause. Not overwriting it.", file=sys.stderr)
        return 4

    print(f"\nWould add inline policy {POLICY_NAME} to {role}:")
    print(json.dumps(POLICY, indent=2))
    if not args.apply:
        print("\nREAD-ONLY. Re-run with --apply to write it.")
        return 0

    iam.put_role_policy(RoleName=role, PolicyName=POLICY_NAME,
                        PolicyDocument=json.dumps(POLICY))
    after = before
    for _ in range(6):               # IAM is eventually consistent
        after = _decision(iam, role_arn)
        if after == "allowed":
            break
        sleep(3)
    print(f"\nadded {POLICY_NAME}. dynamodb:PutItem on {TABLE} is now: {after}")
    return 0 if after == "allowed" else 1


if __name__ == "__main__":
    sys.exit(main())
