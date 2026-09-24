#!/usr/bin/env python3
"""Issue (or report) the Muse connector's partner API key.

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/setup_muse_partner_key.py
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/setup_muse_partner_key.py --apply

Read-only without --apply. Idempotent: it scans relayshield_api_keys for an
existing item with source="muse_connector" first, exactly like
_find_developer_key_by_email does not mint a second key for the same email --
running this twice must not silently create two Muse keys.

WHY THIS KEY NEEDS partner_daily_cap AND NOT JUST A FREE-TIER KEY.
-------------------------------------------------------------------
A plain free-tier key (_issue_free_key) carries free_calls_remaining, which
runs out. Once it does, /v1/metered/breach 402s -- fine for a developer
testing the API, wrong for a live connector whose users expect the free
breach-check to keep working the way the free link-check and wallet-risk
checks already do.

partner_daily_cap is what handle_breach's _check_partner_upstream_budget
reads (relayshield_api.py). It is a DAILY ceiling on calls to the shared HIBP
upstream, not a lifetime allowance -- unlimited-looking to a Muse user, but
bounded so the connector cannot starve HIBP's rate limit for every other
caller sharing that one key (the Telegram bot, the WhatsApp bot, the OAuth
watchlist, and every paying API customer).

THIS KEY IS ALSO PROTECTED THE SAME WAY ANY OTHER FREE KEY IS: no
stripe_customer_id, no stripe_subscription_id, no credit_balance. It can
never be billed, and _record_stripe_meter_event is a no-op for it by
construction (relayshield_api.py's is_partner_call branch explicitly skips
billing rather than relying on the absent stripe_customer_id as an implicit
guard).

THE CAP IS A STARTING POINT, NOT A MEASURED NUMBER. 500/day is a guess sized
to "a real integration doing real traffic, not an open proxy" -- adjust it
with --daily-cap once real Muse volume is observed. Lowering it later is a
one-line update-item; this script does not attempt to guess Muse's actual
volume, which nobody has measured yet.

THIS DOES NOT CREATE ANY AWS API GATEWAY RESOURCE. /v1/metered/breach is
gated entirely inside this Lambda by X-RS-API-KEY (see handle_metered_request
in relayshield_api.py) -- unlike the standalone /v1/breach route in the
top-level ROUTES dict, which other tooling in this repo has documented as
API-Gateway-key-gated. Muse should be given /v1/metered/breach, which needs
nothing at the gateway: just this DynamoDB record and the key value.
"""
import argparse
import sys
import uuid
from datetime import datetime, timezone

ACCOUNT = "239677749008"
API_KEYS_TABLE = "relayshield_api_keys"
SOURCE = "muse_connector"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually write (default is dry run)")
    ap.add_argument("--daily-cap", type=int, default=500,
                     help="partner_daily_cap for /v1/metered/breach (default 500)")
    ap.add_argument("--email", default="",
                     help="a contact address for the key record, if Muse gave us one")
    args = ap.parse_args()

    import boto3

    sts = boto3.client("sts")
    got = sts.get_caller_identity()["Account"]
    if got != ACCOUNT:
        print(f"STOP: this identity resolves to account {got}, not {ACCOUNT}.", file=sys.stderr)
        print("Nothing has been created.", file=sys.stderr)
        return 1
    print(f"== 1. Account: {got}  (correct)")

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(API_KEYS_TABLE)

    print(f"\n== 2. Scanning {API_KEYS_TABLE} for an existing source={SOURCE!r} key")
    existing = None
    kwargs: dict = {}
    while True:
        resp = table.scan(**kwargs)
        for item in resp.get("Items", []):
            if item.get("source") == SOURCE:
                existing = item
                break
        if existing or "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    if existing:
        print(f"   found: api_key={existing['api_key'][:16]}... "
              f"partner_daily_cap={existing.get('partner_daily_cap')} "
              f"active={existing.get('active')}")
        print("\nA Muse key already exists. This script never mints a second one.")
        print("To change its cap, use tools/lambda_env_merge.py's pattern (read, merge, write)")
        print("or update-item directly -- not a fresh put_item, which would drop any other")
        print("fields set on the record since.")
        return 0

    print("   none found -- would create one")

    api_key = f"rs_live_{uuid.uuid4().hex}"
    item = {
        "api_key":           api_key,
        "active":            True,
        "source":            SOURCE,
        "partner_daily_cap": args.daily_cap,
        "created_at":        datetime.now(timezone.utc).isoformat(),
    }
    if args.email:
        item["email"] = args.email

    print(f"\n== 3. {'Writing' if args.apply else 'Would write'} to {API_KEYS_TABLE}:")
    for k, v in item.items():
        print(f"   {k:20s} {v if k != 'api_key' else v}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to actually create this key.")
        return 0

    table.put_item(Item=item, ConditionExpression="attribute_not_exists(api_key)")
    print(f"\nCreated. Send Muse this value as their X-RS-API-KEY header:\n\n  {api_key}\n")
    print("It is not stored anywhere else and will not be printed again by this script --")
    print(f"re-running it will report the key exists (masked) rather than re-mint it.")
    print(f"\nIt is scoped to /v1/metered/breach only, capped at {args.daily_cap} calls/day")
    print("against the shared HIBP upstream, never billed, never expires unless revoked")
    print("by hand (set active=False on the item).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
