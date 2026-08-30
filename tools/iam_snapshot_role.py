#!/usr/bin/env python3
"""
Snapshot an IAM role into the repo, before anything changes it.

Run this FIRST, before tools/iam_split_roles.py, and commit what it writes.

Why
---
The DRIFT RULE in CLAUDE.md is about Lambda code, but it applies with more force
to IAM: relayshield-breach-check-role-1sapnwdl carries 26 inline policies that
exist ONLY in AWS. They are not in git, no workflow checks them, and nothing
would notice if one were deleted. That is worse than the 2026-08-26 hand-deploy,
because a missing permission does not fail at deploy time -- it fails on
whichever code path needs it, whenever that path next runs.

This is read-only. It creates nothing, changes nothing, deletes nothing.

Usage (on the Mac -- the container has no usable AWS credentials)
-----------------------------------------------------------------
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/iam_snapshot_role.py
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/iam_snapshot_role.py --role some-other-role
"""

import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP_DIR = os.path.join(REPO, "iam", "snapshots")

DEFAULT_ROLE = "relayshield-breach-check-role-1sapnwdl"

# The only RelayShield account. 620534471984 is the pre-audit account and is the
# shell default, so an aws call without AWS_PROFILE=relayshield silently aims at
# it. Reads there return ResourceNotFoundException, which merely looks confusing.
# WRITES there succeed, which is how an empty relayshield_intel_first_seen table
# ended up in the wrong account on 2026-08-29. This script only reads, but it
# refuses to run against the wrong account anyway: a snapshot of the wrong
# account's role, committed to the repo, would be worse than no snapshot.
RELAYSHIELD_ACCOUNT = "239677749008"

# IAM quotas. Both are hard limits, neither is adjustable.
INLINE_BUDGET_BYTES = 10240   # total, across ALL inline policies on one role
MANAGED_ATTACH_LIMIT = 10     # attached managed policies per role (20 on request)
MANAGED_POLICY_BYTES = 6144   # one managed policy document


def require_boto3():
    try:
        import boto3  # noqa: F401
    except ImportError:
        sys.exit(
            "boto3 is not installed.\n"
            "  python3 -m venv ~/.rsvenv && ~/.rsvenv/bin/pip install boto3\n"
            "then re-run with ~/.rsvenv/bin/python"
        )


def guard_account(session):
    ident = session.client("sts").get_caller_identity()
    account = ident["Account"]
    if account != RELAYSHIELD_ACCOUNT:
        sys.exit(
            "Refusing to run: credentials resolve to account %s, not %s.\n"
            "Re-run with AWS_PROFILE=relayshield." % (account, RELAYSHIELD_ACCOUNT)
        )
    return ident


def snapshot(session, role_name):
    iam = session.client("iam")

    role = iam.get_role(RoleName=role_name)["Role"]

    inline = {}
    for page in iam.get_paginator("list_role_policies").paginate(RoleName=role_name):
        for name in page["PolicyNames"]:
            doc = iam.get_role_policy(RoleName=role_name, PolicyName=name)["PolicyDocument"]
            inline[name] = doc

    attached = {}
    for page in iam.get_paginator("list_attached_role_policies").paginate(RoleName=role_name):
        for pol in page["AttachedPolicies"]:
            arn = pol["PolicyArn"]
            meta = iam.get_policy(PolicyArn=arn)["Policy"]
            ver = iam.get_policy_version(
                PolicyArn=arn, VersionId=meta["DefaultVersionId"])["PolicyVersion"]
            attached[arn] = {
                "name": pol["PolicyName"],
                "default_version": meta["DefaultVersionId"],
                "aws_managed": arn.startswith("arn:aws:iam::aws:policy/"),
                "document": ver["Document"],
            }

    # IAM measures the inline budget against the stored JSON. Whitespace is not
    # counted, so compact separators are the honest measure of how much room is
    # actually left.
    inline_bytes = {
        name: len(json.dumps(doc, separators=(",", ":")))
        for name, doc in inline.items()
    }
    total_inline = sum(inline_bytes.values())

    # Which Lambdas actually run as this role. Without this the split is guesswork:
    # 46 relayshield_*.py sources are not in deploy_lambdas.yml's LAMBDA_MAP, and
    # some of them are deployed handlers. The shared role cannot be emptied until
    # every function on this list has moved off it.
    lam = session.client("lambda", region_name="us-east-1")
    users = []
    for page in lam.get_paginator("list_functions").paginate():
        for fn in page["Functions"]:
            if fn.get("Role") == role["Arn"]:
                users.append({
                    "name": fn["FunctionName"],
                    "last_modified": fn.get("LastModified"),
                    "vpc": bool(fn.get("VpcConfig", {}).get("VpcId")),
                })
    users.sort(key=lambda f: f["name"])

    return {
        "_generated_by": "tools/iam_snapshot_role.py",
        "_read_only": True,
        "account": RELAYSHIELD_ACCOUNT,
        "role": {
            "name": role["RoleName"],
            "arn": role["Arn"],
            "created": role["CreateDate"].isoformat(),
            "trust_policy": role["AssumeRolePolicyDocument"],
            "permissions_boundary": role.get("PermissionsBoundary", {}).get(
                "PermissionsBoundaryArn"),
        },
        "budget": {
            "inline_bytes_used": total_inline,
            "inline_bytes_limit": INLINE_BUDGET_BYTES,
            "inline_bytes_free": INLINE_BUDGET_BYTES - total_inline,
            "inline_policy_count": len(inline),
            "managed_attached": len(attached),
            "managed_attach_limit": MANAGED_ATTACH_LIMIT,
            "per_policy_bytes": inline_bytes,
        },
        "inline_policies": inline,
        "attached_policies": attached,
        "functions_using_this_role": users,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", default=DEFAULT_ROLE)
    ap.add_argument("--out", default=None, help="override the output path")
    args = ap.parse_args()

    require_boto3()
    import boto3

    session = boto3.Session()
    ident = guard_account(session)
    print("account %s (%s)" % (ident["Account"], ident["Arn"]))

    data = snapshot(session, args.role)

    out = args.out or os.path.join(SNAP_DIR, "%s.json" % args.role)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(data, indent=2, sort_keys=False) + "\n")

    b = data["budget"]
    print("wrote %s" % os.path.relpath(out, REPO))
    print("  inline : %d policies, %d/%d bytes used, %d free"
          % (b["inline_policy_count"], b["inline_bytes_used"],
             b["inline_bytes_limit"], b["inline_bytes_free"]))
    print("  managed: %d attached of %d allowed"
          % (b["managed_attached"], b["managed_attach_limit"]))
    print("  lambdas running as this role: %d" % len(data["functions_using_this_role"]))
    for fn in data["functions_using_this_role"]:
        print("    %s%s" % (fn["name"], "  [VPC]" if fn["vpc"] else ""))

    if b["inline_bytes_free"] < 512:
        print("\nThe inline budget is effectively full. Every new grant from here is a"
              "\nseparate managed policy, and there are only %d attachment slots."
              % (b["managed_attach_limit"] - b["managed_attached"]))
    print("\nCommit this file, then: python3 tools/iam_split_roles.py --from-snapshot %s"
          % os.path.relpath(out, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
