#!/usr/bin/env python3
"""Put the MPP endpoint's Stripe calls in front of Stripe and print what it says.

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/mpp_settlement_selftest.py

WHY THIS EXISTS
---------------
The shapes in `relayshield_mpp_settlement.py` are now VERIFIED against mppx
0.9.2, Stripe's own reference implementation, rather than derived from prose --
and that verification found three wrong keys in the PaymentIntent and a wrong
API version. Reading an implementation is much better than reading a blog, and
it is still not the same as the account answering.

So this script sends the exact dicts those builders produce and prints Stripe's
own reply. It answers three questions in order, and they are different
questions: is the account enabled, does it have a business profile (MPP needs
one as `networkId`), and does a transaction_verification PaymentIntent record.

A 403 on the first is the expected answer today and is NOT evidence the shapes
are wrong -- an ungranted resource and a misspelt one look identical from out
here. That distinction is why the report below separates them.

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
    # List first, exactly as the handler does. A create when one already exists
    # is a new address for no reason, and on Lambda that is every cold start.
    net = deposit_params["network"]
    status, body = call(f"/v1/crypto/deposit_addresses?network={net}&limit=1", None, key,
                        mpp.STRIPE_PREVIEW_VERSION)
    report(f"1a. GET /v1/crypto/deposit_addresses?network={net} (list before create)",
           status, body)
    if status == 200 and not (body.get("data") or []):
        status, body = call("/v1/crypto/deposit_addresses", deposit_params, key,
                            mpp.STRIPE_PREVIEW_VERSION)
        report("1b. stripe_deposit_address_params() -> POST /v1/crypto/deposit_addresses",
               status, body)

    # MPP uses the business profile id as `networkId`. Without it a challenge
    # cannot be built at all, so it is worth knowing separately from the
    # crypto gate -- the two are granted independently.
    status, body = call("/v2/network/business_profiles/me", None, key,
                        mpp.STRIPE_PREVIEW_VERSION)
    profile_id = body.get("id", "") if status == 200 else ""
    report("1c. GET /v2/network/business_profiles/me (MPP networkId)", status, body)
    if profile_id:
        print(f"   STRIPE_PROFILE_ID={profile_id}")
        realm = "api.relayshield.net"
        header = mpp.build_mpp_challenge(realm, profile_id,
                                         mpp.mpp_secret_key(key),
                                         description="RelayShield MCP registry risk check")
        print("   The challenge this account can now issue:")
        print(f"     WWW-Authenticate: {header[:160]}...")
        print("   Objective check, on this machine, against a deployed URL:")
        print("     npx mppx@latest validate https://api.relayshield.net/v1/mpp/mcp-registry-risk")
    print()

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
    print("  All 200       -> the rail works. Set RELAYSHIELD_MPP_RAIL=auto and, if a")
    print("                   profile id came back, STRIPE_PROFILE_ID, then pay the")
    print("                   endpoint once for real and check the PaymentIntent lands.")
    print("  A rejected    -> correct that one key in the named builder function in")
    print("  parameter        relayshield_mpp_settlement.py, re-run, repeat. These are")
    print("                   verified against mppx 0.9.2, so a rejection here means")
    print("                   mppx has moved -- check its version before editing.")
    print("  401/403/404   -> the account is not enabled. That message text is the")
    print("                   thing to send machine-payments@stripe.com with the")
    print("                   account id. Leave RELAYSHIELD_MPP_RAIL=facilitator.")
    print()
    print("  NOTE ON EVIDENCE: a 200 here proves STRIPE enabled the account. It is")
    print("  not evidence about us, and it is not the artefact to send anyone. The")
    print("  artefact is a live URL that returns a 402, `npx mppx@latest validate`")
    print("  passing against it, and a settled PaymentIntent id in the account.")


if __name__ == "__main__":
    main()
