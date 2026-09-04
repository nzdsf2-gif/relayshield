#!/usr/bin/env python3
"""Is this Stripe account actually enabled for machine payments? Read-only.

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/stripe_machine_payments_probe.py

Answers one question before anybody writes an endpoint: can we call the machine
payments surface at all, or is it gated behind the access request that keeps
coming back? Every call here is a GET. It creates nothing, charges nothing and
prints no key.

WHY THIS EXISTS
---------------
Stripe documents both protocols and says a seller integrates "in a few lines of
code", which is easy to read as "we can ship this today". Stablecoin acceptance
is separately documented as gated: available to US businesses outside New York,
and everyone else emails machine-payments@stripe.com with their account ID. So
"the docs exist" and "our account can do it" are different facts, and building
against the second without checking the first wastes a day and produces a
confusing 400 at the end of it.

The key comes from Secrets Manager, never from an argument or an env var in a
pasted block. See CLAUDE.md rule 11.
"""

import json
import sys
import urllib.error
import urllib.request

SECRET = "relayshield/stripe_secret_key"
# The preview version the x402 documentation uses. A preview version is a moving
# target: if this probe starts failing on parameters that used to work, check
# whether the date has moved before assuming an entitlement changed.
PREVIEW = "2026-05-27.preview"


def _key():
    import boto3
    sm = boto3.client("secretsmanager", region_name="us-east-1")
    raw = sm.get_secret_value(SecretId=SECRET)["SecretString"]
    try:
        d = json.loads(raw)
        return d.get("stripe_secret_key") or d.get("STRIPE_SECRET_KEY") or raw
    except json.JSONDecodeError:
        return raw


def get(path, key, version=None):
    req = urllib.request.Request(f"https://api.stripe.com{path}", method="GET")
    req.add_header("Authorization", f"Bearer {key}")
    if version:
        req.add_header("Stripe-Version", version)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read())
        except Exception:
            return exc.code, {}
    except Exception as exc:
        return 0, {"error": {"message": str(exc)}}


def main():
    key = _key()
    mode = "LIVE" if key.startswith("sk_live_") else "TEST"
    print(f"Using the {mode} key from {SECRET}. The key itself is never printed.\n")

    print("== 1. Which account, and where is it registered?")
    status, acct = get("/v1/account", key)
    if status != 200:
        sys.exit(f"could not read the account: HTTP {status} "
                 f"{acct.get('error', {}).get('message', '')}")
    print(f"   id       {acct.get('id')}")
    print(f"   country  {acct.get('country')}   default currency {acct.get('default_currency')}")
    print("   Stablecoin acceptance is documented as US-only outside New York.")
    print("   Anywhere else: email machine-payments@stripe.com with that account id.\n")

    print("== 2. Capabilities that look like machine payments or crypto")
    caps = acct.get("capabilities") or {}
    interesting = {k: v for k, v in caps.items()
                   if any(t in k.lower() for t in
                          ("crypto", "stablecoin", "usdc", "machine", "mpp", "x402", "spt"))}
    if interesting:
        for k, v in sorted(interesting.items()):
            print(f"   {k:<40} {v}")
    else:
        print("   NONE. No capability on this account names crypto, stablecoins or")
        print("   machine payments. That is the answer to 'are we enabled yet'.")
    print(f"   ({len(caps)} capabilities in total on the account.)\n")

    print("== 3. Does the x402 deposit-address surface answer us?")
    status, body = get("/v1/crypto/deposit_addresses?limit=1", key, PREVIEW)
    err = (body.get("error") or {})
    print(f"   GET /v1/crypto/deposit_addresses -> HTTP {status}")
    if status == 200:
        print("   ENABLED. The endpoint answers, so the x402 path is open to this account.")
    elif status in (401, 403):
        print("   NOT ENABLED, or not permitted for this key. Message:")
        print(f"     {err.get('message', '(none)')}")
    elif status == 404:
        print("   Not found on this API version or not enabled for this account. Message:")
        print(f"     {err.get('message', '(none)')}")
        print("   A 404 here is NOT proof the product does not exist: an ungranted")
        print("   resource and a missing one look identical from outside.")
    else:
        print(f"   type={err.get('type')} code={err.get('code')}")
        print(f"     {err.get('message', '(none)')}")

    print()
    print("WHAT TO DO WITH THIS")
    print("  Enabled  -> build one endpoint on the Stripe rail and prove it end to end.")
    print("  Not      -> that error text is the concrete thing to put in front of Stripe.")
    print("              'The console returns the access request' is a support ticket;")
    print("              'GET /v1/crypto/deposit_addresses returns this' is an engineering")
    print("              question, and it reaches a different person.")


if __name__ == "__main__":
    main()
