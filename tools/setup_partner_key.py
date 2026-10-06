#!/usr/bin/env python3
"""Issue (or report) a partner connector's API key.

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/setup_partner_key.py --source openai_connector
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/setup_partner_key.py --source openai_connector --apply

Read-only without --apply. Idempotent: it scans relayshield_api_keys for an
existing item with the given source first, exactly like _find_developer_key_by
_email does not mint a second key for the same email -- running this twice
against the same --source must not silently create two keys.

GENERALISED 2026-09-24 from a Muse-only script of the same shape. One partner,
one function definition, one place for this reasoning to drift from the code
that actually enforces it -- N near-identical copies is N chances to be wrong,
which is this repo's own most-repeated defect. --source is now required and
free-text, so a NEW partner (OpenAI, the next one) is one command, not a new
file. The first partner built this way was Muse (source="muse_connector",
500/day, 2026-09-22); this script issues the exact same shape of key for any
--source, including it.

WHY A PARTNER KEY NEEDS partner_daily_cap AND NOT JUST A FREE-TIER KEY.
-------------------------------------------------------------------------
A plain free-tier key (_issue_free_key) carries free_calls_remaining, which
runs out. Once it does, /v1/metered/breach 402s -- fine for a developer
testing the API, wrong for a live connector whose users expect the free
breach-check to keep working the way the free link-check and wallet-risk
checks already do.

partner_daily_cap is what handle_breach's _check_partner_upstream_budget
reads (relayshield_api.py). It is a DAILY ceiling on calls to the shared HIBP
upstream, not a lifetime allowance -- unlimited-looking to that partner's
users, but bounded so no single connector can starve HIBP's rate limit for
every other caller sharing that one key (the Telegram bot, the WhatsApp bot,
the OAuth watchlist, and every paying API customer). The budget check is keyed
on the API KEY VALUE itself (relayshield_api.py's usage_key includes
api_key_str), so two partner keys are independently capped with no code
change needed per partner -- issuing a new key is the whole integration.

EVERY PARTNER KEY IS PROTECTED THE SAME WAY ANY OTHER FREE KEY IS: no
stripe_customer_id, no stripe_subscription_id, no credit_balance. It can
never be billed, and _record_stripe_meter_event is a no-op for it by
construction (relayshield_api.py's is_partner_call branch explicitly skips
billing rather than relying on the absent stripe_customer_id as an implicit
guard).

THE CAP IS A STARTING POINT, NOT A MEASURED NUMBER. 500/day is a guess sized
to "a real integration doing real traffic, not an open proxy" -- adjust it
with --daily-cap once real volume from that partner is observed. Lowering it
later is a one-line update-item; this script does not attempt to guess a new
partner's actual volume, which nobody has measured yet.

THIS DOES NOT CREATE ANY AWS API GATEWAY RESOURCE. /v1/metered/breach is
gated entirely inside this Lambda by X-RS-API-KEY (see handle_metered_request
in relayshield_api.py) -- unlike the standalone /v1/breach route in the
top-level ROUTES dict, which other tooling in this repo has documented as
API-Gateway-key-gated. A partner should be given /v1/metered/breach, which
needs nothing at the gateway: just this DynamoDB record and the key value.
"""
import argparse
import re
import sys
import uuid
from datetime import datetime, timezone

ACCOUNT = "239677749008"
API_KEYS_TABLE = "relayshield_api_keys"

# Free-text but bounded: the value is stored, logged and read back by other
# tooling (is_partner_call in relayshield_api.py just needs it non-empty on
# partner_daily_cap, but a source string is also what shows up in CloudWatch
# and in any future per-partner report), so keep it to the same shape the
# _SOURCE_BANNERS keys already use elsewhere in this repo.
_SOURCE_RE = re.compile(r"^[a-z][a-z0-9_-]{2,40}$")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True,
                     help="partner identifier, e.g. openai_connector, muse_connector")
    ap.add_argument("--apply", action="store_true", help="actually write (default is dry run)")
    ap.add_argument("--daily-cap", type=int, default=500,
                     help="partner_daily_cap for /v1/metered/breach (default 500)")
    ap.add_argument("--email", default="",
                     help="a contact address for the key record, if the partner gave us one")
    args = ap.parse_args()

    if not _SOURCE_RE.match(args.source):
        print(f"STOP: --source {args.source!r} does not match {_SOURCE_RE.pattern} "
              f"-- lowercase, starts with a letter, 3-41 chars.", file=sys.stderr)
        return 1
    source = args.source

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

    print(f"\n== 2. Scanning {API_KEYS_TABLE} for an existing source={source!r} key")
    existing = None
    kwargs: dict = {}
    while True:
        resp = table.scan(**kwargs)
        for item in resp.get("Items", []):
            if item.get("source") == source:
                existing = item
                break
        if existing or "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    if existing:
        print(f"   found: api_key={existing['api_key'][:16]}... "
              f"partner_daily_cap={existing.get('partner_daily_cap')} "
              f"active={existing.get('active')}")
        print(f"\nA {source!r} key already exists. This script never mints a second one for")
        print("the same source. To change its cap, use tools/lambda_env_merge.py's pattern")
        print("(read, merge, write) or update-item directly -- not a fresh put_item, which")
        print("would drop any other fields set on the record since.")
        return 0

    print("   none found -- would create one")

    api_key = f"rs_live_{uuid.uuid4().hex}"
    item = {
        "api_key":           api_key,
        "active":            True,
        "source":            source,
        "partner_daily_cap": args.daily_cap,
        "created_at":        datetime.now(timezone.utc).isoformat(),
    }
    if args.email:
        item["email"] = args.email

    print(f"\n== 3. {'Writing' if args.apply else 'Would write'} to {API_KEYS_TABLE}:")
    for k, v in item.items():
        print(f"   {k:20s} {v}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to actually create this key.")
        return 0

    table.put_item(Item=item, ConditionExpression="attribute_not_exists(api_key)")
    print(f"\nCreated. Send {source} this value as their X-RS-API-KEY header:\n\n  {api_key}\n")
    print("It is not stored anywhere else and will not be printed again by this script --")
    print(f"re-running it with --source {source} will report the key exists (masked) rather")
    print("than re-mint it.")
    print(f"\nIt is scoped to /v1/metered/breach only, capped at {args.daily_cap} calls/day")
    print("against the shared HIBP upstream, never billed, never expires unless revoked")
    print("by hand (set active=False on the item).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
