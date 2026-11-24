#!/usr/bin/env python3
"""Well-Architected SEC 8 (data at rest): audit, then close the gaps that are safe to close. Dry run by default.

    AWS_PROFILE=relayshield python3 tools/wafr_data_at_rest.py                 # read-only, all steps
    AWS_PROFILE=relayshield python3 tools/wafr_data_at_rest.py --step s3       # one step
    AWS_PROFILE=relayshield python3 tools/wafr_data_at_rest.py --apply         # make the changes
    AWS_PROFILE=relayshield python3 tools/wafr_data_at_rest.py --check         # read-only, exit 1 on ANY gap

Steps:

  s3        Every bucket in the region: default encryption present, all four public-access-block flags on.
            APPLY adds default encryption (SSE-S3, AES256) where there is none, and turns the block on where
            the bucket is NOT public. A bucket that is public (policy, ACL grant to everyone, or a website
            endpoint) is reported as CONFLICT and never touched: blocking it would take a live site down.
            A bucket named in the spec's expected_public list is skipped on purpose and said so.
  sqs       Every queue: server-side encryption on (SSE-SQS or a KMS key). APPLY turns on SSE-SQS where neither.
  dynamodb  Every table: encrypted (always true in DynamoDB; the key type is reported), point-in-time recovery,
            deletion protection. READ-ONLY here. The writer is tools/protect_dynamodb_tables.sh, so one tool
            owns each change; this step reports ELSEWHERE for what it would fix.
  account   The account-level S3 public access block. APPLY turns it on only when NO bucket in the region is
            public, otherwise BLOCKED, because the account switch overrides the per-bucket choices above.

WHAT THIS EVIDENCES, AND WHAT IT DOES NOT. It supports the two SEC 8 practices "Automate data at rest
protection" (the check is automatable and scheduled: .github/workflows/data_at_rest_check.yml) and "Enforce
access control" (public access blocked, encryption enforced by configuration). It does NOT show least-privilege
IAM on the data stores: that is the per-Lambda role split in iam_role_split.md, SEC 3. Say so in the Note.
It does not rotate keys and does not move data to customer-managed KMS keys: AWS-managed encryption is on by
default for every store above, and a customer key adds cost and a way to lock ourselves out for no High question.

Never touches a resource it was not able to read, and refuses to run unless the credentials resolve to the
RelayShield account, because the shell default profile is the pre-audit account.
"""
import argparse
import json
import sys
from pathlib import Path

SPEC = Path(__file__).resolve().parent / "wafr_data_at_rest_spec.json"
STEPS = ("s3", "sqs", "dynamodb", "account")
PAB_FLAGS = ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")
ALL_USERS = ("http://acs.amazonaws.com/groups/global/AllUsers", "http://acs.amazonaws.com/groups/global/AuthenticatedUsers")
# states: ok | todo | conflict | blocked | elsewhere | skipped
ATTENTION = ("conflict", "blocked", "elsewhere")


def code(e):
    return getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)


def paged(fn, key, token_in, token_out, **kw):
    token = None
    while True:
        r = fn(**kw, **({token_in: token} if token else {}))
        yield from r.get(key, [])
        token = r.get(token_out)
        if not token:
            return


# ------------------------------------------------------------------------- s3
def bucket_in_region(s3, name, region):
    loc = s3.get_bucket_location(Bucket=name).get("LocationConstraint") or "us-east-1"
    return loc == region, loc


def is_public(s3, name):
    """(public?, why). Policy status, a website endpoint, or an ACL grant to everyone. Unreadable counts as public:
    the safe direction is to NOT block a bucket we could not see."""
    try:
        if s3.get_bucket_policy_status(Bucket=name)["PolicyStatus"]["IsPublic"]:
            return True, "bucket policy is public"
    except Exception as e:
        if code(e) != "NoSuchBucketPolicy":
            return True, f"policy status unreadable ({code(e)})"
    try:
        s3.get_bucket_website(Bucket=name)
        return True, "static website hosting is on"
    except Exception as e:
        if code(e) != "NoSuchWebsiteConfiguration":
            return True, f"website config unreadable ({code(e)})"
    try:
        for g in s3.get_bucket_acl(Bucket=name).get("Grants", []):
            if g.get("Grantee", {}).get("URI") in ALL_USERS:
                return True, "ACL grants access to everyone"
    except Exception as e:
        return True, f"ACL unreadable ({code(e)})"
    return False, ""


def plan_s3(s3, spec):
    rows = []
    for b in s3.list_buckets().get("Buckets", []):
        name = b["Name"]
        try:
            here, loc = bucket_in_region(s3, name, spec["region"])
        except Exception as e:
            rows.append((name, "blocked", f"cannot read location ({code(e)})", {}))
            continue
        if not here:
            rows.append((name, "skipped", f"lives in {loc}, not {spec['region']}; run the tool with that region", {}))
            continue
        todo, notes = [], []
        try:
            s3.get_bucket_encryption(Bucket=name)
        except Exception as e:
            if code(e) == "ServerSideEncryptionConfigurationNotFoundError":
                todo.append("encrypt")
            else:
                rows.append((name, "blocked", f"cannot read encryption ({code(e)})", {}))
                continue
        try:
            cfg = s3.get_public_access_block(Bucket=name)["PublicAccessBlockConfiguration"]
            missing = [f for f in PAB_FLAGS if not cfg.get(f)]
        except Exception as e:
            if code(e) != "NoSuchPublicAccessBlockConfiguration":
                rows.append((name, "blocked", f"cannot read public access block ({code(e)})", {}))
                continue
            missing = list(PAB_FLAGS)
        public, why = is_public(s3, name)
        if name in spec["expected_public_buckets"]:
            if "encrypt" in todo:
                rows.append((name, "todo", "no default encryption (expected public, so the public access block is left alone)", {"encrypt": True}))
            else:
                rows.append((name, "skipped", "listed in expected_public_buckets; public access block deliberately not applied", {}))
            continue
        if missing and public:
            rows.append((name, "conflict", f"public ({why}) and public access block incomplete; NOT changed, "
                         f"decide whether it must be public and add it to expected_public_buckets or fix it by hand", {"encrypt": "encrypt" in todo}))
            continue
        if missing:
            todo.append("block")
        if todo:
            rows.append((name, "todo", " and ".join({"encrypt": "add default encryption AES256", "block": "turn on all four public access block flags"}[t] for t in todo),
                         {"encrypt": "encrypt" in todo, "block": "block" in todo}))
        else:
            rows.append((name, "ok", "encrypted by default, public access blocked", {}))
    return rows


def apply_s3(s3, rows):
    for name, state, _d, act in rows:
        if state == "conflict" and act.get("encrypt") or state == "todo" and act.get("encrypt"):
            s3.put_bucket_encryption(Bucket=name, ServerSideEncryptionConfiguration={
                "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}, "BucketKeyEnabled": True}]})
            yield f"{name}: default encryption"
        if state == "todo" and act.get("block"):
            s3.put_public_access_block(Bucket=name, PublicAccessBlockConfiguration={f: True for f in PAB_FLAGS})
            yield f"{name}: public access block"


# ------------------------------------------------------------------------ sqs
def plan_sqs(sqs, spec):
    rows = []
    for url in paged(sqs.list_queues, "QueueUrls", "NextToken", "NextToken"):
        name = url.rsplit("/", 1)[-1]
        try:
            a = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["KmsMasterKeyId", "SqsManagedSseEnabled"]).get("Attributes", {})
        except Exception as e:
            rows.append((name, "blocked", f"cannot read ({code(e)})", url))
            continue
        if a.get("KmsMasterKeyId"):
            rows.append((name, "ok", "KMS key", url))
        elif str(a.get("SqsManagedSseEnabled", "")).lower() == "true":
            rows.append((name, "ok", "SSE-SQS", url))
        else:
            rows.append((name, "todo", "no server-side encryption; turn on SSE-SQS", url))
    return rows


def apply_sqs(sqs, rows):
    for name, state, _d, url in rows:
        if state == "todo":
            sqs.set_queue_attributes(QueueUrl=url, Attributes={"SqsManagedSseEnabled": "true"})
            yield name


# ------------------------------------------------------------------- dynamodb
def plan_dynamodb(ddb, spec):
    rows = []
    for t in paged(ddb.list_tables, "TableNames", "ExclusiveStartTableName", "LastEvaluatedTableName"):
        try:
            d = ddb.describe_table(TableName=t)["Table"]
            pitr = ddb.describe_continuous_backups(TableName=t)["ContinuousBackupsDescription"].get(
                "PointInTimeRecoveryDescription", {}).get("PointInTimeRecoveryStatus")
        except Exception as e:
            rows.append((t, "blocked", f"cannot read ({code(e)})", None))
            continue
        gaps = []
        if pitr != "ENABLED":
            gaps.append("point-in-time recovery off")
        if not d.get("DeletionProtectionEnabled"):
            gaps.append("deletion protection off")
        key = (d.get("SSEDescription") or {}).get("SSEType") or "AWS-owned key"
        if d.get("SSEDescription") and d["SSEDescription"].get("Status") not in (None, "ENABLED"):
            gaps.append(f"encryption status {d['SSEDescription']['Status']}")
        if gaps:
            rows.append((t, "elsewhere", "; ".join(gaps) + " -> sh tools/protect_dynamodb_tables.sh --apply", None))
        else:
            rows.append((t, "ok", f"encrypted ({key}), PITR on, deletion protection on", None))
    return rows


# -------------------------------------------------------------------- account
def plan_account(s3, s3control, account, spec):
    try:
        cfg = s3control.get_public_access_block(AccountId=account)["PublicAccessBlockConfiguration"]
        if all(cfg.get(f) for f in PAB_FLAGS):
            return [("account public access block", "ok", "all four flags on", None)]
    except Exception as e:
        if code(e) != "NoSuchPublicAccessBlockConfiguration":
            return [("account public access block", "blocked", f"cannot read ({code(e)})", None)]
    pub = []
    for b in s3.list_buckets().get("Buckets", []):
        if b["Name"] in spec["expected_public_buckets"]:
            pub.append(f"{b['Name']} (expected public)")
            continue
        try:
            here, _ = bucket_in_region(s3, b["Name"], spec["region"])
        except Exception:
            pub.append(f"{b['Name']} (location unreadable)")
            continue
        if here and is_public(s3, b["Name"])[0]:
            pub.append(b["Name"])
    if pub:
        return [("account public access block", "blocked",
                 "not on, and these buckets are public so the switch would break them: " + ", ".join(pub), None)]
    return [("account public access block", "todo", "turn on all four account-level flags; no bucket is public", None)]


def apply_account(s3control, rows, account):
    for name, state, _d, _x in rows:
        if state == "todo":
            s3control.put_public_access_block(AccountId=account, PublicAccessBlockConfiguration={f: True for f in PAB_FLAGS})
            yield name


# ----------------------------------------------------------------------- main
def run(clients, account_of, spec, apply, steps, check=False, out=print):
    got = account_of()
    if got != spec["account"]:
        out(f"Refusing to run: credentials resolve to account {got}, not {spec['account']}. Use AWS_PROFILE=relayshield.")
        return 2
    if apply and check:
        out("--apply and --check are opposites; pick one.")
        return 2
    attention = todo_any = False
    for step in steps:
        out(f"\n== {step}")
        done = []
        if step == "s3":
            rows = plan_s3(clients["s3"], spec)
            done = list(apply_s3(clients["s3"], rows)) if apply else []
        elif step == "sqs":
            rows = plan_sqs(clients["sqs"], spec)
            done = list(apply_sqs(clients["sqs"], rows)) if apply else []
        elif step == "dynamodb":
            rows = plan_dynamodb(clients["dynamodb"], spec)
        else:
            rows = plan_account(clients["s3"], clients["s3control"], got, spec)
            done = list(apply_account(clients["s3control"], rows, got)) if apply else []
        for name, state, detail, _x in rows:
            if state != "ok":
                out(f"  {state.upper():<9} {name}  {detail}".rstrip())
        ok = sum(r[1] == "ok" for r in rows)
        todo = sum(r[1] == "todo" for r in rows)
        bad = [r for r in rows if r[1] in ATTENTION]
        attention |= bool(bad)
        todo_any |= bool(todo)
        for d in done:
            out(f"  CHANGED   {d}")
        out(f"  {step}: {ok} already fine, {todo} to change, {len(bad)} need attention, {sum(r[1] == 'skipped' for r in rows)} skipped on purpose.")
    if not apply:
        out("\nDry run only. Re-run with --apply to make the changes." if not check else "\nCheck only.")
    # Applying fixes what it can; whatever is left (conflict, blocked, elsewhere) still exits 1. A check also fails on
    # anything not yet done, which is what makes the scheduled run a drift alarm rather than a report.
    return 1 if attention or (check and todo_any) else 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--step", choices=STEPS + ("all",), default="all")
    ap.add_argument("--spec", default=str(SPEC))
    a = ap.parse_args(argv)
    spec = json.load(open(a.spec))
    import boto3
    r = spec["region"]
    clients = {n: boto3.client(n, region_name=r) for n in ("s3", "sqs", "dynamodb", "s3control")}
    sts = boto3.client("sts", region_name=r)
    steps = STEPS if a.step == "all" else (a.step,)
    return run(clients, lambda: sts.get_caller_identity()["Account"], spec, a.apply, steps, a.check)


if __name__ == "__main__":
    sys.exit(main())
