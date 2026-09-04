#!/usr/bin/env python3
"""Put the MPP endpoint's Stripe calls in front of Stripe and print what it says.

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/mpp_settlement_selftest.py

WHY THIS EXISTS
---------------
`docs.stripe.com` is blocked from the build container, so the parameter names in
`relayshield_mpp_settlement.py` -- the crypto deposit address call and the
transaction_verification PaymentIntent -- were DERIVED from Stripe's published
pages rather than read from the API reference. Derived names are a guess with
good manners.

This script sends the exact dicts those two builder functions produce and prints
Stripe's own reply. Stripe names a wrong parameter precisely, so one run either
confirms the shape or hands over the corrections, and the fix is a one-line edit
to the builder rather than a hunt through a handler.

SAFETY
------
It refuses to run against a live key unless --live is passed. A PaymentIntent
with confirm=true on a live key is a real charge attempt on a live revenue
account, and this is a script written to be run repeatedly while a shape is
being settled. The key comes from Secrets Manager and is never printed.
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SECRET = "relayshield/stripe_secret_key"


def _key() -> str:
    import boto3
    raw = boto3.client("secretsmanager", region_name="us-east-1") \
               .get_secret_value(SecretId=SECRET)["SecretString"].strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    return parsed.get("stripe_secret_key") or parsed.get("STRIPE_SECRET_KEY") or raw


def call(path, params, key, version, idempotency=""):
    data = urllib.parse.urlencode(params, doseq=True).encode() if params is not None else None
    req = urllib.request.Request(f"https://api.stripe.com{path}", data=data,
                                 method="POST" if data is not None else "GET")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Stripe-Version", version)
    if data is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    if idempotency:
        req.add_header("Idempotency-Key", idempotency)
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except Exception:
            return exc.code, {}
    except Exception as exc:
        return 0, {"error": {"message": str(exc)}}


def report(title, status, body):
    print(f"== {title}")
    print(f"   HTTP {status}")
    err = body.get("error") or {}
    if status == 200:
        print(f"   OK. id={body.get('id', '(none)')}")
        print("   The shape in the builder is CORRECT. Delete the 'derived, not")
        print("   verified' warning above that function and record this run.")
    elif err.get("param"):
        # The useful case. Stripe names the exact parameter it did not like.
        print(f"   type={err.get('type')} code={err.get('code')}")
        print(f"   PARAM STRIPE REJECTED: {err['param']}")
        print(f"   {err.get('message', '')}")
        print("   -> fix that one key in the builder function and re-run.")
    else:
        print(f"   type={err.get('type')} code={err.get('code')}")
        print(f"   {err.get('message', '(no message)')}")
        if status in (401, 403, 404):
            print("   Not granted, or not on this API version. That is the expected")
            print("   answer while crypto reads Ineligible on the account, and it is")
            print("   NOT evidence the parameter names are wrong -- an ungranted")
            print("   resource and a misspelt one look identical from out here.")
            print("   This exact text is the thing to send machine-payments@stripe.com.")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true",
                    help="permit running against a live key (creates a real PaymentIntent)")
    ap.add_argument("--tx", default="0x" + "11" * 32,
                    help="transaction hash to record; defaults to an obvious dummy")
    args = ap.parse_args()

    import relayshield_mpp_settlement as mpp

    key  = _key()
    live = key.startswith("sk_live_")
    print(f"Key is {'LIVE' if live else 'TEST'}. It is never printed.")
    print(f"Stripe-Version pinned to {mpp.STRIPE_PREVIEW_VERSION} "
          "(a preview version moves -- check this first if a working call breaks).\n")

    if live and not args.live:
        sys.exit("Refusing to run against a live key without --live. "
                 "confirm=true on a live key is a real charge attempt.")

    status, acct = call("/v1/account", None, key, mpp.STRIPE_PREVIEW_VERSION)
    if status != 200:
        sys.exit(f"could not read the account: HTTP {status}")
    print(f"Account {acct.get('id')} ({acct.get('country')}), "
          f"default currency {acct.get('default_currency')}\n")

    deposit_params = mpp.stripe_deposit_address_params()
    print(f"   posting {deposit_params}")
    status, body = call("/v1/crypto/deposit_addresses", deposit_params, key,
                        mpp.STRIPE_PREVIEW_VERSION)
    report("1. stripe_deposit_address_params() -> POST /v1/crypto/deposit_addresses",
           status, body)

    cents = mpp.usdc_units_to_cents(mpp.PRICE_UNITS)
    print(f"   conversion check: {mpp.PRICE_UNITS} USDC atomic units -> {cents} cents "
          f"(${cents / 100:.2f})")
    if cents != 35:
        print("   ⚠ that is not 35. The price or the conversion has changed.")
    pi_params = mpp.stripe_payment_intent_params(
        cents, "base", args.tx,
        currency=acct.get("default_currency") or "usd",
        metadata={"path": mpp.MPP_PATH, "selftest": "true"},
    )
    print(f"   posting {json.dumps(pi_params, indent=6)}")
    status, body = call("/v1/payment_intents", pi_params, key,
                        mpp.STRIPE_PREVIEW_VERSION,
                        idempotency=f"mpp-selftest-{args.tx}")
    report("2. stripe_payment_intent_params() -> POST /v1/payment_intents",
           status, body)

    print("WHAT TO DO WITH THIS")
    print("  Both 200      -> the rail works. Set RELAYSHIELD_MPP_RAIL=auto on the")
    print("                   Lambda and pay the endpoint once for real.")
    print("  A rejected    -> correct that one key in the named builder function in")
    print("  parameter        relayshield_mpp_settlement.py, re-run, repeat.")
    print("  401/403/404   -> the account is not enabled. Send the message text above")
    print("                   to machine-payments@stripe.com with the account id, and")
    print("                   leave RELAYSHIELD_MPP_RAIL=facilitator until it clears.")


if __name__ == "__main__":
    main()
