#!/usr/bin/env python3
"""Delete one customer's verifier telemetry reports, on request.

Privacy policy section 13 promises: "To have them deleted, email us from your account
address and we will delete the entries linked to your key." This is that promise.

    # 1. Find the reporter hash for the account (read only; prints no full key):
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/delete_verifier_reports.py --email someone@example.com

    # 2. Count what would be deleted, then delete it:
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/delete_verifier_reports.py --reporter-hash 0123456789abcdef
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/delete_verifier_reports.py --reporter-hash 0123456789abcdef --apply

WHY A HASH AND NOT A KEY. Rows carry the first 16 hex characters of SHA-256 of the API
key (relayshield_verifier_telemetry.reporter_hash), never the key. Step 1 recomputes it
from the key records for an email so nobody has to handle a key.

SAFETY. Dry run unless --apply. The hash must be exactly 16 lowercase hex characters, so
an empty or short value can never match "everything". Rows are matched on that attribute
alone and deleted by their own (pk, sk). The table is scanned page by page with a running
count printed as it goes: a long read that prints nothing is indistinguishable from a
hang. Deleting does not affect the account's opt-in setting.
"""
import argparse
import hashlib
import re
import sys

ACCOUNT = "239677749008"
REGION = "us-east-1"
TABLE = "relayshield_verifier_telemetry"
KEYS_TABLE = "relayshield_api_keys"
HASH_RE = re.compile(r"^[0-9a-f]{16}$")


def reporter_hash(api_key: str) -> str:
    """Must stay identical to relayshield_verifier_telemetry.reporter_hash; a test checks."""
    return hashlib.sha256(str(api_key).encode("utf-8")).hexdigest()[:16]


def is_reporter_hash(value: str) -> bool:
    return isinstance(value, str) and bool(HASH_RE.match(value))


def describe_key(record: dict) -> str:
    k = str(record.get("api_key", ""))
    return (f"key ...{k[-6:]}  active={bool(record.get('active'))}  "
            f"verifier_telemetry_opt_in={record.get('verifier_telemetry_opt_in') is True}  "
            f"reporter_hash={reporter_hash(k)}")


def scan_matching(table, rhash: str, progress=print):
    """Every (pk, sk) whose reporter_hash equals rhash. Pages with a running count."""
    from boto3.dynamodb.conditions import Attr  # imported here so the pure helpers test without boto3
    kwargs = {"FilterExpression": Attr("reporter_hash").eq(rhash),
              "ProjectionExpression": "pk, sk"}
    found, pages = [], 0
    while True:
        resp = table.scan(**kwargs)
        pages += 1
        found.extend({"pk": i["pk"], "sk": i["sk"]} for i in resp.get("Items", []))
        progress(f"   scanned page {pages}: {len(found)} matching so far")
        if not resp.get("LastEvaluatedKey"):
            return found
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def delete_rows(table, rows: list) -> int:
    with table.batch_writer() as batch:
        for r in rows:
            batch.delete_item(Key={"pk": r["pk"], "sk": r["sk"]})
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--email", help="print the reporter hash for each key on this account")
    g.add_argument("--reporter-hash", help="16 hex characters, from --email")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    try:
        import boto3
        from boto3.dynamodb.conditions import Key
    except ImportError:
        raise SystemExit("ERROR: boto3 missing. Use ~/.rsvenv/bin/python.")
    acct = boto3.client("sts").get_caller_identity()["Account"]
    if acct != ACCOUNT:
        raise SystemExit(f"Refusing to run: credentials resolve to {acct}, not {ACCOUNT}. "
                         "Prefix the command with AWS_PROFILE=relayshield.")
    ddb = boto3.resource("dynamodb", region_name=REGION)
    if args.email:
        items = ddb.Table(KEYS_TABLE).query(
            IndexName="email-index",
            KeyConditionExpression=Key("email").eq(args.email.strip().lower())).get("Items", [])
        if not items:
            print("No key records for that email.")
            return 1
        for rec in items:
            print(describe_key(rec))
        print("Next: re-run with --reporter-hash <hash above>. Nothing was read from or changed in "
              f"{TABLE}.")
        return 0
    if not is_reporter_hash(args.reporter_hash):
        print("REFUSED: --reporter-hash must be exactly 16 lowercase hex characters.")
        return 2
    table = ddb.Table(TABLE)
    print(f"== scanning {TABLE} for reporter_hash {args.reporter_hash}")
    rows = scan_matching(table, args.reporter_hash)
    print(f"{len(rows)} report(s) linked to that hash.")
    if not rows:
        return 0
    if not args.apply:
        print("DRY RUN. Re-run with --apply to delete them.")
        return 0
    print(f"deleted {delete_rows(table, rows)} report(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
