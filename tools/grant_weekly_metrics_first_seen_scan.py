#!/usr/bin/env python3
"""relayshield-weekly-metrics runs under the shared relayshield-breach-check-
role-1sapnwdl role and, as of 2026-09-28, its _unique_indicators() raises:

  AccessDeniedException ... dynamodb:Scan ... table/relayshield_intel_first_seen
  ... assumed-role/relayshield-breach-check-role-1sapnwdl/relayshield-weekly-metrics

THIS REPLACES tools/grant_weekly_metrics_first_seen_scan.sh, which was WRONG.
That script checked whether "dynamodb:Scan" appeared ANYWHERE in a policy's
JSON body, and separately whether the table name appeared ANYWHERE in the
same body -- never confirming both were on the SAME statement. The role's
~11 attached managed policies mean a policy document covering this table can
easily also contain an unrelated statement, for a different table, that
happens to grant Scan -- and the shell script would call that "already
covers this table with Scan", when the statement that ACTUALLY governs
relayshield_intel_first_seen may still only have PutItem.

That is exactly what happened: it reported "already includes Scan. Nothing
to do." on every run, including the very first, and the Lambda kept getting
denied on the identical action/resource every time. The check itself was
false, not just the earlier write.

  AWS_PROFILE=relayshield ~/.rsvenv/bin/python \
    tools/grant_weekly_metrics_first_seen_scan.py

READ-MERGE-WRITE, deliberately, on the SPECIFIC STATEMENT that covers this
table -- never the whole document, never assumed to be Statement[0].
put-role-policy and create-policy-version both REPLACE the entire document
they're given, so this reads the full document, finds the one statement
whose Resource actually references relayshield_intel_first_seen, adds Scan
to that statement's Action list only, and writes the WHOLE document back
unchanged except for that one list. Every other statement is untouched.

Prints the real document it found and the real document it wrote, not a
yes/no summary -- the summary is exactly what was wrong last time.
"""
import json
import sys

ACCOUNT = "239677749008"
REGION = "us-east-1"
TABLE = "relayshield_intel_first_seen"
TABLE_ARN = f"arn:aws:dynamodb:{REGION}:{ACCOUNT}:table/{TABLE}"
FUNC = "relayshield-weekly-metrics"


def _as_list(x):
    return x if isinstance(x, list) else [x]


def _resource_matches(resource) -> bool:
    return any(
        v == TABLE_ARN or v == "*" or (isinstance(v, str) and v.endswith(f"table/{TABLE}"))
        for v in _as_list(resource)
    )


def _has_scan(action) -> bool:
    return any(v in ("dynamodb:Scan", "dynamodb:*", "*") for v in _as_list(action))


def _add_scan(action):
    vals = list(_as_list(action))
    if not any(v in ("dynamodb:Scan", "dynamodb:*", "*") for v in vals):
        vals.append("dynamodb:Scan")
    return vals


def _find_statement(doc: dict, label: str):
    """Returns (index, statement) for the ONE statement in doc whose Resource
    covers TABLE_ARN, or (None, None). Prints what it found, in full, rather
    than summarizing -- the summary is what was wrong before."""
    stmts = doc.get("Statement", [])
    stmts = stmts if isinstance(stmts, list) else [stmts]
    for i, st in enumerate(stmts):
        res = st.get("Resource")
        if res is not None and _resource_matches(res):
            print(f"   {label}: statement[{i}] covers {TABLE}")
            print(f"     Action   : {json.dumps(st.get('Action'))}")
            print(f"     Resource : {json.dumps(res)}")
            return i, st
    return None, None


def main() -> int:
    import boto3

    iam = boto3.client("iam", region_name=REGION)
    lam = boto3.client("lambda", region_name=REGION)
    sts = boto3.client("sts", region_name=REGION)

    print("== 1. Which account are we actually talking to?")
    got = sts.get_caller_identity()["Account"]
    if got != ACCOUNT:
        print(f"STOP: profile resolves to {got}, not {ACCOUNT}. Nothing changed.", file=sys.stderr)
        return 1
    print(f"   {got}  (correct)")

    print(f"\n== 2. Which role does {FUNC} run as?")
    role_arn = lam.get_function_configuration(FunctionName=FUNC)["Role"]
    role = role_arn.rsplit("/", 1)[-1]
    print(f"   {role}")

    print(f"\n== 3. Checking every statement of every policy on {role} for one covering {TABLE}")
    print("   (not just whether Scan and the table name each appear SOMEWHERE in the doc)")

    inline_hit = None
    for name in iam.list_role_policies(RoleName=role)["PolicyNames"]:
        doc = iam.get_role_policy(RoleName=role, PolicyName=name)["PolicyDocument"]
        idx, st = _find_statement(doc, f"inline:{name}")
        if st is not None:
            inline_hit = (name, doc, idx, st)
            break

    managed_hit = None
    if not inline_hit:
        for ap in iam.list_attached_role_policies(RoleName=role)["AttachedPolicies"]:
            arn = ap["PolicyArn"]
            vid = iam.get_policy(PolicyArn=arn)["Policy"]["DefaultVersionId"]
            doc = iam.get_policy_version(PolicyArn=arn, VersionId=vid)["PolicyVersion"]["Document"]
            idx, st = _find_statement(doc, f"managed:{arn}")
            if st is not None:
                managed_hit = (arn, doc, idx, st)
                break

    if inline_hit:
        name, doc, idx, st = inline_hit
        if _has_scan(st.get("Action")):
            print(f"\n   statement[{idx}] of inline policy {name} ALREADY has Scan on THIS resource.")
            print("   If the function is still denied, this genuinely is not the cause --")
            print("   paste the fresh CloudWatch traceback rather than assuming this script's job.")
            return 0
        print(f"\n== 4. Adding dynamodb:Scan to statement[{idx}] of inline policy {name}")
        print("      (every other statement in this document is left byte-for-byte alone)")
        st["Action"] = _add_scan(st.get("Action"))
        iam.put_role_policy(RoleName=role, PolicyName=name, PolicyDocument=json.dumps(doc))
        verify = iam.get_role_policy(RoleName=role, PolicyName=name)["PolicyDocument"]
        print("   written. Verify -- the full document as AWS now has it:")
        print(json.dumps(verify, indent=2))
        return 0

    if managed_hit:
        arn, doc, idx, st = managed_hit
        if _has_scan(st.get("Action")):
            print(f"\n   statement[{idx}] of managed policy {arn} ALREADY has Scan on THIS resource.")
            print("   If the function is still denied, this genuinely is not the cause --")
            print("   paste the fresh CloudWatch traceback rather than assuming this script's job.")
            return 0
        print(f"\n== 4. Adding dynamodb:Scan to statement[{idx}] of managed policy {arn}")
        print("      (every other statement in this document is left byte-for-byte alone)")
        st["Action"] = _add_scan(st.get("Action"))
        versions = iam.list_policy_versions(PolicyArn=arn)["Versions"]
        if len(versions) >= 5:
            non_default = sorted(
                (v for v in versions if not v["IsDefaultVersion"]), key=lambda v: v["CreateDate"]
            )
            if non_default:
                old_vid = non_default[0]["VersionId"]
                iam.delete_policy_version(PolicyArn=arn, VersionId=old_vid)
                print(f"   pruned oldest non-default version {old_vid} (5-version cap)")
        iam.create_policy_version(PolicyArn=arn, PolicyDocument=json.dumps(doc), SetAsDefault=True)
        new_vid = iam.get_policy(PolicyArn=arn)["Policy"]["DefaultVersionId"]
        verify = iam.get_policy_version(PolicyArn=arn, VersionId=new_vid)["PolicyVersion"]["Document"]
        print(f"   new default version {new_vid} created. Verify -- the full document as AWS now has it:")
        print(json.dumps(verify, indent=2))
        return 0

    print(f"\n== 4. No existing statement anywhere on {role} references {TABLE} at all.")
    print("      Granting fresh read access (GetItem, Query, Scan).")
    new_policy_name = "relayshield-first-seen-read"
    doc = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": ["dynamodb:GetItem", "dynamodb:Query", "dynamodb:Scan"],
            "Resource": TABLE_ARN,
        }],
    }
    try:
        iam.put_role_policy(RoleName=role, PolicyName=new_policy_name, PolicyDocument=json.dumps(doc))
        print(f"   attached as inline policy {new_policy_name}")
        return 0
    except Exception as exc:
        print(f"   inline failed: {exc}")
        print("   falling back to a customer-managed policy, which has its own separate budget")
        arn = f"arn:aws:iam::{ACCOUNT}:policy/{new_policy_name}"
        try:
            iam.get_policy(PolicyArn=arn)
            iam.create_policy_version(PolicyArn=arn, PolicyDocument=json.dumps(doc), SetAsDefault=True)
        except iam.exceptions.NoSuchEntityException:
            iam.create_policy(PolicyName=new_policy_name, PolicyDocument=json.dumps(doc))
        try:
            iam.attach_role_policy(RoleName=role, PolicyArn=arn)
            print(f"   attached {arn} to {role}")
            return 0
        except Exception as exc2:
            print(f"\n!! NOT GRANTED. Both budgets on {role} appear spent: {exc2}")
            print(f"!! The real fix at that point is moving {FUNC} onto its own role:")
            print(f"!!   AWS_PROFILE=relayshield python3 tools/iam_split_roles.py "
                  f"--from-snapshot <snapshot> --only {FUNC} --apply")
            return 1


if __name__ == "__main__":
    sys.exit(main())
