#!/usr/bin/env python3
"""
Give each Lambda its own execution role, built from the shared role's own policies.

The problem
-----------
Every Lambda runs as relayshield-breach-check-role-1sapnwdl, whose convention is
one inline policy per table. 26 of them now fill the 10,240-byte inline budget,
so on 2026-08-29 a single PutItem grant had to fall back to a customer-managed
policy. That buys a little room and then stops: a role may have only 10 managed
policies attached. The cap is not the bug. One role doing everything for every
function is the bug, and it will keep producing this.

The approach, and why it is staged
----------------------------------
A per-function role is derived from the shared role's EXISTING statements, not
written from scratch. Inferring actions from source code is how you ship a role
that works until the first quarterly code path runs and then fails in production
with AccessDenied. So:

  * The ACTIONS come from the shared role -- they are known to work today.
  * The RESOURCES this function touches come from tools/iam_scan_sources.py.
  * A statement is dropped only when the function does not call that service at
    all, or when it does and none of that service's resources are ones this
    function uses. Anything else is carried over.

A statement is only ever matched by ARN for services whose resources appear in
the source as names: DynamoDB tables, Secrets Manager ids, Lambda invoke targets,
S3 buckets. For everything else -- KMS reached through an alias, SES, Rekognition,
the marketplace metering APIs -- the source contains no ARN to match, so the
statement is kept whenever the function uses that service. Dropping those would
produce a role that looks tidy and fails on whichever code path needs the
permission. The fixture run that first exercised this dropped intel-monitor's
kms:Decrypt, which it needs on every encrypted-field read.

By default a carried-over statement keeps its resource patterns UNCHANGED. So
step one is a pure move: identical permissions, on a role of the function's own.
That frees the shared budget and gives every function room to grow, and if
something breaks it is attributable to the move alone.

Narrowing wildcard resources to the concrete ARNs a function uses is step two,
behind --narrow-wildcards, run per function after step one is proven. Two
changes at once is how you end up unable to say which one broke it.

Order of operations
-------------------
  1. AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/iam_snapshot_role.py
  2. python3 tools/iam_scan_sources.py
  3. python3 tools/iam_split_roles.py --from-snapshot iam/snapshots/<role>.json
     (no credentials needed -- prints what it WOULD do, for every function)
  4. AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/iam_split_roles.py \
         --apply --only relayshield-gas-monitor
     One function at a time. Start with a small, scheduled, non-customer-facing
     one, so a mistake shows up on a monitor and not on the API.
  5. Watch it run once on its own schedule, then do the next.

Nothing here deletes anything from the shared role. Reclaiming that budget is a
separate, later step, safe only once snapshot's functions_using_this_role list
is empty -- and that list includes handlers that are not in deploy_lambdas.yml.
"""

import argparse
import fnmatch
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCES = os.path.join(REPO, "iam", "required_resources.json")

RELAYSHIELD_ACCOUNT = "239677749008"
REGION = "us-east-1"

# Logs are non-negotiable for a Lambda and are the same for all of them, so they
# come from the AWS-managed policy rather than being duplicated into 22 roles.
BASIC_EXECUTION = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
VPC_EXECUTION = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"

MANAGED_POLICY_BYTES = 6144
INLINE_BUDGET_BYTES = 10240


# ---------------------------------------------------------------------------
# ARN construction
# ---------------------------------------------------------------------------

def table_arns(name):
    base = "arn:aws:dynamodb:%s:%s:table/%s" % (REGION, RELAYSHIELD_ACCOUNT, name)
    # Index ARNs are separate resources. A policy that grants Query on the table
    # but not on table/index/* fails only on the code paths that use a GSI.
    return [base, base + "/index/*"]


def secret_arns(name):
    # Secrets Manager appends a random 6-character suffix to the ARN, so a secret
    # can only ever be matched by pattern, never by literal ARN.
    return ["arn:aws:secretsmanager:%s:%s:secret:%s-??????"
            % (REGION, RELAYSHIELD_ACCOUNT, name)]


def function_arns(name):
    return ["arn:aws:lambda:%s:%s:function:%s" % (REGION, RELAYSHIELD_ACCOUNT, name)]


def bucket_arns(name):
    return ["arn:aws:s3:::%s" % name, "arn:aws:s3:::%s/*" % name]


# boto3 client name -> the prefix its actions carry in an IAM policy. Mostly the
# same string; the ones that are not are the reason this map exists.
SERVICE_ACTION_PREFIX = {
    "bedrock-runtime": "bedrock",
    "meteringmarketplace": "aws-marketplace",
    "marketplace-entitlement": "aws-marketplace",
}

# Services whose resources CAN be read out of the source, so a statement about
# them is safe to match by ARN and safe to drop when nothing matches.
RESOLVABLE_SERVICES = {"dynamodb", "secretsmanager", "lambda", "s3"}


def action_services(statement):
    """The service prefixes a statement's actions belong to."""
    services = set()
    for action in as_list(statement.get("Action")) or as_list(statement.get("NotAction")):
        if action == "*":
            services.add("*")
        elif ":" in action:
            services.add(action.split(":", 1)[0])
    return services


def function_services(info):
    """The service prefixes this function's source shows it calling."""
    return {SERVICE_ACTION_PREFIX.get(s, s) for s in info.get("services", [])}


def needed_arns(info):
    """Every ARN this function's own source says it touches."""
    arns = []
    for t in info.get("tables", []):
        arns += table_arns(t)
    for s in info.get("secrets", []):
        arns += secret_arns(s)
    for f in info.get("invokes", []):
        arns += function_arns(f)
    for b in info.get("buckets", []):
        arns += bucket_arns(b)
    return arns


def arn_matches(pattern, arn):
    """IAM resource matching: * and ? are the only wildcards, case-sensitive.

    Matched in BOTH directions on purpose. A policy pattern may be broader than
    the ARN (table/* covers one table) or narrower in a way that still refers to
    the same resource (a secret pattern ending -?????? against our -?????? form).
    """
    return fnmatch.fnmatchcase(arn, pattern) or fnmatch.fnmatchcase(pattern, arn)


def as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


# ---------------------------------------------------------------------------
# Derivation. Pure -- no AWS, no I/O. This is the part worth being sure about,
# so it is callable and inspectable on its own.
# ---------------------------------------------------------------------------

def collect_statements(snapshot, include_aws_managed=False):
    """Every statement on the shared role, tagged with where it came from."""
    out = []
    for name, doc in snapshot.get("inline_policies", {}).items():
        for i, st in enumerate(as_list(doc.get("Statement"))):
            out.append(("inline:" + name, i, st))
    for arn, pol in snapshot.get("attached_policies", {}).items():
        # AWSLambdaBasicExecutionRole and friends are re-attached by ARN on the
        # new role; copying their contents in would be duplication that then
        # drifts from what AWS ships.
        if pol.get("aws_managed") and not include_aws_managed:
            continue
        for i, st in enumerate(as_list(pol.get("document", {}).get("Statement"))):
            out.append(("managed:" + pol.get("name", arn), i, st))
    return out


def derive_policy(snapshot, info, narrow_wildcards=False, include_unattributed=False):
    """Build one function's policy out of the shared role's statements.

    Returns (document, report). The report explains every statement's fate, so a
    dropped permission is a thing someone decided, not a thing that happened.
    """
    wanted = needed_arns(info)
    used_services = function_services(info)
    kept, dropped, narrowed, unattributable = [], [], [], []

    for origin, idx, st in collect_statements(snapshot):
        if st.get("Effect") != "Allow":
            # A Deny is a guardrail. It is carried over verbatim, always, and is
            # never narrowed -- narrowing a Deny widens what is permitted.
            kept.append(dict(st))
            continue

        svcs = action_services(st)
        if svcs and "*" not in svcs and not (svcs & used_services):
            # This function never calls the service at all, so the statement is
            # some other Lambda's. This is the clean, confident drop.
            dropped.append((origin, idx, st.get("Sid", ""),
                            ["service not used: " + ", ".join(sorted(svcs))]))
            if include_unattributed:
                kept.append(dict(st))
            continue

        # The function DOES use this service, but the source cannot say which
        # resources. A KMS key reached through alias/relayshield-data-key, an SES
        # identity, a Rekognition call -- none of these appear in the code as an
        # ARN, so matching would drop a permission the function genuinely needs
        # and it would fail at runtime, on whichever path uses it. Keep it.
        if svcs and not (svcs & RESOLVABLE_SERVICES):
            kept.append(dict(st))
            continue

        patterns = as_list(st.get("Resource"))
        if not patterns:
            # NotResource, or a statement shaped in a way this tool does not
            # model. Never guessed at.
            unattributable.append((origin, idx, "no Resource key"))
            if include_unattributed:
                kept.append(dict(st))
            continue

        matching, is_wild = [], False
        for pat in patterns:
            hits = [a for a in wanted if arn_matches(pat, a)]
            if hits:
                matching.append((pat, hits))
                if pat == "*" or pat.endswith(":*") or pat.endswith("/*"):
                    is_wild = True

        if not matching:
            dropped.append((origin, idx, st.get("Sid", ""), patterns))
            if include_unattributed:
                kept.append(dict(st))
            continue

        new_st = dict(st)
        if narrow_wildcards and is_wild:
            concrete = sorted({a for _, hits in matching for a in hits})
            new_st["Resource"] = concrete
            narrowed.append((origin, idx, patterns, concrete))
        else:
            new_st["Resource"] = [p for p, _ in matching]
        kept.append(new_st)

    doc = {"Version": "2012-10-17", "Statement": kept}
    report = {
        "kept": len(kept),
        "dropped": dropped,
        "narrowed": narrowed,
        "unattributable": unattributable,
        "bytes": len(json.dumps(doc, separators=(",", ":"))),
    }
    return doc, report


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def role_name_for(function_name):
    return "%s-role" % function_name


def apply_one(session, snapshot, function_name, doc, dry_run=True):
    iam = session.client("iam")
    lam = session.client("lambda", region_name=REGION)

    role = role_name_for(function_name)
    policy_name = "%s-derived" % function_name
    trust = json.dumps(snapshot["role"]["trust_policy"])

    fn = lam.get_function_configuration(FunctionName=function_name)
    old_role_arn = fn["Role"]
    in_vpc = bool(fn.get("VpcConfig", {}).get("VpcId"))

    print("  current role: %s" % old_role_arn.rsplit("/", 1)[-1])
    print("  new role    : %s%s" % (role, "  [VPC -- also attaching VPC access]" if in_vpc else ""))

    if dry_run:
        print("  (dry run -- nothing changed)")
        return

    try:
        iam.create_role(RoleName=role, AssumeRolePolicyDocument=trust,
                        Description="Execution role for %s. Derived from %s by "
                                    "tools/iam_split_roles.py." % (
                                        function_name, snapshot["role"]["name"]))
        print("  created role")
    except iam.exceptions.EntityAlreadyExistsException:
        print("  role already exists -- updating its policy in place")

    iam.attach_role_policy(RoleName=role, PolicyArn=BASIC_EXECUTION)
    if in_vpc:
        iam.attach_role_policy(RoleName=role, PolicyArn=VPC_EXECUTION)

    iam.put_role_policy(RoleName=role, PolicyName=policy_name,
                        PolicyDocument=json.dumps(doc, separators=(",", ":")))
    print("  wrote inline policy %s (%d bytes of %d)"
          % (policy_name, len(json.dumps(doc, separators=(",", ":"))), INLINE_BUDGET_BYTES))

    new_arn = "arn:aws:iam::%s:role/%s" % (RELAYSHIELD_ACCOUNT, role)

    # A freshly created role is not immediately assumable by Lambda. Without this
    # retry the switch fails with InvalidParameterValueException "The role
    # defined for the function cannot be assumed by Lambda", which reads like a
    # trust-policy mistake and is really just IAM propagation.
    last = None
    for attempt in range(10):
        try:
            lam.update_function_configuration(FunctionName=function_name, Role=new_arn)
            break
        except lam.exceptions.InvalidParameterValueException as exc:
            last = exc
            time.sleep(3 * (attempt + 1))
    else:
        raise SystemExit("could not switch %s to %s after retrying: %s"
                         % (function_name, role, last))

    lam.get_waiter("function_updated").wait(FunctionName=function_name)
    print("  switched %s -> %s" % (function_name, role))

    print("\n  Roll back with:")
    print("    AWS_PROFILE=relayshield aws lambda update-function-configuration \\")
    print("      --function-name %s --role %s --region %s" % (function_name, old_role_arn, REGION))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-snapshot", required=True,
                    help="iam/snapshots/<role>.json, written by tools/iam_snapshot_role.py")
    ap.add_argument("--only", action="append", default=None,
                    help="limit to this function (repeatable). Required with --apply.")
    ap.add_argument("--apply", action="store_true",
                    help="actually create the role and switch the function to it")
    ap.add_argument("--narrow-wildcards", action="store_true",
                    help="step two: replace wildcard resources with the concrete ARNs "
                         "this function uses. Run only after the plain move is proven.")
    ap.add_argument("--include-unattributed", action="store_true",
                    help="also carry over statements that match nothing this function "
                         "uses, instead of dropping them")
    ap.add_argument("--write-policies", metavar="DIR",
                    help="write each derived policy document to DIR for review")
    args = ap.parse_args()

    with open(args.from_snapshot, encoding="utf-8") as fh:
        snapshot = json.load(fh)
    with open(RESOURCES, encoding="utf-8") as fh:
        scan = json.load(fh)

    functions = scan["functions"]
    if args.only:
        missing = [f for f in args.only if f not in functions]
        if missing:
            sys.exit("not in iam/required_resources.json: %s\nknown: %s"
                     % (", ".join(missing), ", ".join(sorted(functions))))
        functions = {f: functions[f] for f in args.only}

    if args.apply and not args.only:
        sys.exit("--apply needs --only. Migrate one function at a time, and watch each "
                 "one run before starting the next.")

    session = None
    if args.apply:
        try:
            import boto3
        except ImportError:
            sys.exit("boto3 is not installed. python3 -m venv ~/.rsvenv && "
                     "~/.rsvenv/bin/pip install boto3")
        session = boto3.Session()
        account = session.client("sts").get_caller_identity()["Account"]
        if account != RELAYSHIELD_ACCOUNT:
            sys.exit("Refusing to run: credentials resolve to account %s, not %s.\n"
                     "Re-run with AWS_PROFILE=relayshield." % (account, RELAYSHIELD_ACCOUNT))
        print("account %s\n" % account)

    total_dropped = 0
    for name in sorted(functions):
        info = functions[name]
        doc, rep = derive_policy(
            snapshot, info,
            narrow_wildcards=args.narrow_wildcards,
            include_unattributed=args.include_unattributed,
        )
        print("%s" % name)
        print("  %d statements, %d bytes (inline budget on the NEW role: %d)"
              % (rep["kept"], rep["bytes"], INLINE_BUDGET_BYTES))
        if rep["bytes"] > INLINE_BUDGET_BYTES:
            print("  !! over the inline budget on its own -- split this one by service")
        if rep["narrowed"]:
            print("  narrowed %d wildcard statements" % len(rep["narrowed"]))
        if rep["dropped"]:
            total_dropped += len(rep["dropped"])
            print("  dropped %d statements matching nothing this function uses:"
                  % len(rep["dropped"]))
            for origin, idx, sid, pats in rep["dropped"][:8]:
                print("    %s[%d] %s %s" % (origin, idx, sid, pats[0] if pats else ""))
            if len(rep["dropped"]) > 8:
                print("    ... and %d more" % (len(rep["dropped"]) - 8))
        if rep["unattributable"]:
            print("  %d statements could not be attributed (no Resource key):"
                  % len(rep["unattributable"]))
            for origin, idx, why in rep["unattributable"][:5]:
                print("    %s[%d] %s" % (origin, idx, why))

        if args.write_policies:
            os.makedirs(args.write_policies, exist_ok=True)
            path = os.path.join(args.write_policies, "%s.json" % name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(doc, indent=2) + "\n")
            print("  wrote %s" % path)

        if args.apply:
            apply_one(session, snapshot, name, doc, dry_run=False)
        print()

    if not args.apply:
        print("Dry run. Nothing was created or changed.")
        if total_dropped:
            print("\n%d statements were dropped across these functions. A drop is correct"
                  "\nwhen the statement's resources belong to some OTHER Lambda -- which is"
                  "\nthe whole point of splitting the role. Read the list above before"
                  "\napplying, and use --write-policies to diff a full document."
                  % total_dropped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
