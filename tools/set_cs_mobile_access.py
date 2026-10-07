#!/usr/bin/env python3
"""Grant Crypto Shield Mobile access to ONE existing API key, without any billing.

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/set_cs_mobile_access.py --email someone@example.com --key-suffix abc123
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/set_cs_mobile_access.py --email someone@example.com --key-suffix abc123 --apply

WHY. Every paid CS Mobile screen is admitted by `cs_mobile_access` on an ACTIVE key,
and only the Stripe provisioning path ever writes that flag. A partner given a free
licence by hand has neither, so the paid screens 402 for them. This sets the two
flags and nothing else.

WHY IT CANNOT BILL. It never adds a Stripe field. And in relayshield_api.py the
`is_cs_mobile_call` branch is `pass` ("no credits, no Stripe meter event"), so a
flagged key is not metered even if a stripe_customer_id were present.

SAFETY. Dry run unless --apply. The record is picked by email AND the last six
characters of the key, so two records for one address (a refunded duplicate
checkout exists for one partner) can never be confused: no match or more than one
match refuses. The write carries attribute_exists(api_key), so it cannot create a
record. The key is never printed in full. Run tools/diagnose_cs_partner_key.py
first and read it.
"""
import argparse
import sys

ACCOUNT = "239677749008"
TABLE = "relayshield_api_keys"
FLAGS = {"cs_mobile_access": True, "active": True}


def pick_record(items: list, suffix: str):
    """The single record whose key ends with `suffix`, else a reason string."""
    suffix = suffix.strip()
    if len(suffix) < 4:
        return None, "key suffix must be at least 4 characters"
    hits = [r for r in items if str(r.get("api_key", "")).endswith(suffix)]
    if not hits:
        return None, "no record for that email ends with that key suffix"
    if len(hits) > 1:
        return None, f"{len(hits)} records match that suffix; use a longer one"
    return hits[0], ""


def plan_changes(record: dict) -> dict:
    """Only the flags that are not already set."""
    return {k: v for k, v in FLAGS.items() if record.get(k) is not v and bool(record.get(k)) is not v}


def describe(record: dict) -> str:
    k = str(record.get("api_key", ""))
    return (f"key ...{k[-6:]}  active={bool(record.get('active'))}  "
            f"cs_mobile_access={bool(record.get('cs_mobile_access'))}  "
            f"stripe_subscription_id={'present' if record.get('stripe_subscription_id') else 'absent'}  "
            f"stripe_customer_id={'present' if record.get('stripe_customer_id') else 'absent'}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", required=True)
    ap.add_argument("--key-suffix", required=True, help="last characters of the key, from the diagnostic")
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
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(TABLE)
    items = table.query(IndexName="email-index",
                        KeyConditionExpression=Key("email").eq(args.email.strip().lower())).get("Items", [])
    rec, why = pick_record(items, args.key_suffix)
    if rec is None:
        print(f"REFUSED: {why}. {len(items)} record(s) exist for that email.")
        return 1
    print("before:", describe(rec))
    changes = plan_changes(rec)
    if rec.get("stripe_subscription_id") or rec.get("stripe_customer_id"):
        print("NOTE: this record carries Stripe ids. The cs_mobile branch does not meter, so the flag "
              "cannot cause a charge, but check Stripe for an active subscription on that customer.")
    if not changes:
        print("Nothing to change: both flags are already true.")
        return 0
    print("will set:", ", ".join(f"{k}={v}" for k, v in changes.items()))
    if not args.apply:
        print("DRY RUN. Re-run with --apply to write.")
        return 0
    sets = ", ".join(f"#{i} = :{i}" for i in range(len(changes)))
    table.update_item(
        Key={"api_key": rec["api_key"]},
        UpdateExpression="SET " + sets,
        ConditionExpression="attribute_exists(api_key)",
        ExpressionAttributeNames={f"#{i}": k for i, k in enumerate(changes)},
        ExpressionAttributeValues={f":{i}": v for i, v in enumerate(changes.values())},
    )
    after = table.get_item(Key={"api_key": rec["api_key"]}).get("Item", {})
    print("after: ", describe(after))
    return 0


if __name__ == "__main__":
    sys.exit(main())
