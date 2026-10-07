#!/usr/bin/env python3
"""Let relayshield-api read and write a cache table (default relayshield_breach_cache).

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/grant_breach_cache_access.py            # dry run
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/grant_breach_cache_access.py --apply
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/grant_breach_cache_access.py --table relayshield_vt_url_cache

--table accepts only the names in CACHE_SIDS. Each gets its OWN statement Sid, so granting
the second table never replaces the first table's statement.

WHY. tools/setup_breach_cache.sh measured 2026-10-06: the table is ACTIVE and TTL is
ENABLED on `ttl`, but the role relayshield-api runs as returns implicitDeny for
dynamodb:GetItem and dynamodb:PutItem on it. handle_breach fails soft, so every
breach lookup silently goes to the live vendor, which has one shared rate limit
used by both bots and every paying customer.

HOW. The shared role is out of inline budget and over its managed-policy count, so a
NEW policy cannot be attached. This appends ONE statement (Sid BreachCacheReadWrite)
to an EXISTING attached managed policy and writes the whole document back with every
other statement untouched (create-policy-version replaces the document, so it is read,
merged and written). The statement names this one table ARN: no wildcard, and only the
two actions the code uses. Default target policy is relayshield-first-seen-write, the
small one the first-seen and weekly-metrics grants already extended.

It checks first whether the two actions are ALREADY allowed (by simulate-principal-
policy, the same check setup_breach_cache.sh uses) and does nothing if so. After
--apply it simulates again and prints the verdicts: that is the proof, not the write.
Dry run prints the document it would write.
"""
import argparse
import json
import sys

ACCOUNT = "239677749008"
REGION = "us-east-1"
TABLE = "relayshield_breach_cache"
TABLE_ARN = f"arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/{TABLE}"
FUNC = "relayshield-api"
ACTIONS = ["dynamodb:GetItem", "dynamodb:PutItem"]
SID = "BreachCacheReadWrite"
# One Sid per table: merged_document drops a statement with ITS Sid before appending, so
# a shared Sid would make the second grant silently delete the first.
CACHE_SIDS = {
    "relayshield_breach_cache": "BreachCacheReadWrite",
    "relayshield_vt_url_cache": "VtUrlCacheReadWrite",
}
DEFAULT_POLICY = "relayshield-first-seen-write"
SIZE_LIMIT = 6144  # managed policy, whitespace excluded


def table_arn(table: str) -> str:
    return f"arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/{table}"


def merged_document(doc: dict, table: str = TABLE) -> dict:
    """The document with the cache statement present exactly once; nothing else changed."""
    sid = CACHE_SIDS[table]
    stmts = doc.get("Statement", [])
    stmts = list(stmts) if isinstance(stmts, list) else [stmts]
    stmts = [s for s in stmts if s.get("Sid") != sid]
    stmts.append({"Sid": sid, "Effect": "Allow", "Action": list(ACTIONS), "Resource": table_arn(table)})
    out = dict(doc)
    out["Statement"] = stmts
    return out


def compact_size(doc: dict) -> int:
    return len(json.dumps(doc, separators=(",", ":")))


def simulate(iam, role_arn: str, table: str = TABLE) -> dict:
    res = iam.simulate_principal_policy(PolicySourceArn=role_arn, ActionNames=ACTIONS,
                                        ResourceArns=[table_arn(table)])["EvaluationResults"]
    return {r["EvalActionName"]: r["EvalDecision"] for r in res}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--policy-name", default=DEFAULT_POLICY)
    ap.add_argument("--table", default=TABLE, choices=sorted(CACHE_SIDS))
    args = ap.parse_args()
    table = args.table
    import boto3
    iam = boto3.client("iam", region_name=REGION)
    got = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]
    if got != ACCOUNT:
        print(f"STOP: credentials resolve to {got}, not {ACCOUNT}. Nothing changed.", file=sys.stderr)
        return 1
    role_arn = boto3.client("lambda", region_name=REGION).get_function_configuration(
        FunctionName=FUNC)["Role"]
    role = role_arn.rsplit("/", 1)[-1]
    print(f"== role {role}  table {table}")
    before = simulate(iam, role_arn, table)
    print(f"   now: {before}")
    if all(v == "allowed" for v in before.values()):
        print("Already allowed. Nothing to do.")
        return 0
    attached = {p["PolicyName"]: p["PolicyArn"]
                for p in iam.list_attached_role_policies(RoleName=role)["AttachedPolicies"]}
    if args.policy_name not in attached:
        print(f"STOP: {args.policy_name} is not attached to {role}. Attached: {sorted(attached)}")
        return 1
    arn = attached[args.policy_name]
    vid = iam.get_policy(PolicyArn=arn)["Policy"]["DefaultVersionId"]
    doc = iam.get_policy_version(PolicyArn=arn, VersionId=vid)["PolicyVersion"]["Document"]
    new = merged_document(doc, table)
    print(f"\n== {arn}: {compact_size(doc)} -> {compact_size(new)} of {SIZE_LIMIT} characters")
    if compact_size(new) > SIZE_LIMIT:
        print("STOP: that would exceed the managed-policy size limit. Pick another attached policy "
              "with --policy-name or do the IAM split (iam_role_split.md).")
        return 1
    print(json.dumps(new, indent=2))
    if not args.apply:
        print("\nDRY RUN. Re-run with --apply to write it.")
        return 0
    versions = iam.list_policy_versions(PolicyArn=arn)["Versions"]
    if len(versions) >= 5:
        old = sorted((v for v in versions if not v["IsDefaultVersion"]), key=lambda v: v["CreateDate"])
        if old:
            iam.delete_policy_version(PolicyArn=arn, VersionId=old[0]["VersionId"])
            print(f"pruned oldest non-default version {old[0]['VersionId']} (5-version cap)")
    iam.create_policy_version(PolicyArn=arn, PolicyDocument=json.dumps(new), SetAsDefault=True)
    print("written. Simulating again (IAM can lag a few seconds; re-run the dry run to re-check):")
    print(f"   after: {simulate(iam, role_arn, table)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
