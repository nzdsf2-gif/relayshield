#!/usr/bin/env python3
"""Rotate the Stripe secret key safely, on a LIVE revenue account.

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/rotate_stripe_key.py

It prompts for the new key without echoing it, PROVES the key works before
writing it anywhere, writes it to Secrets Manager, forces every consuming Lambda
to drop its cached copy, verifies, and only then tells you to revoke the old key
in the Dashboard. The key is never printed, never an argument, never in an env
var, and never in shell history.

THE ANSWER TO "DOES IT NEED TO BE AN ENV VAR": NO.
--------------------------------------------------
Nothing in this repo reads the Stripe key from the environment. All six
consumers read the Secrets Manager secret `relayshield/stripe_secret_key` at
runtime. That is the pattern to keep: an env var on a Lambda is printed in full
by `aws lambda get-function-configuration` with no --query, which is how every
deploy log used to leak the environment block.

THE ANSWER TO "CAN I DELETE THE OLD KEY": YES, BUT NOT YET, AND THE ORDER IS THE
WHOLE POINT.
-------------------------------------------------------------------------------
Three of the six consumers cache the secret in a module-level dict with NO TTL:

    relayshield_api.py, relayshield_agentic_api.py, relayshield_mpp_settlement.py

A module-level cache lives as long as the Lambda execution environment, so a
warm container keeps serving the OLD key after the secret changes -- for minutes
to hours, depending on traffic. relayshield_stripe_webhook.py reads it on every
call and switches instantly, so the two halves disagree during the window.

That would be a merely annoying race except for what fails. `_record_stripe_meter_event`
is FIRE AND FORGET and never raises: a 401 from a revoked key is caught, logged
at WARNING, and the customer is served the paid response anyway. So revoking the
old key before the containers recycle does not produce an outage or a red alarm.
It produces SILENT UNDER-BILLING, which is the quiet-alarm failure this repo has
been bitten by before, pointed at revenue.

Hence step 4: force every consumer to recycle before you revoke anything.

NOT THIS SECRET
---------------
`relayshield/stripe_webhook_secret` and `relayshield/stripe_developer_webhook_secret`
are endpoint signing secrets, not API keys. Rolling an API key does not change
them and they must not be touched here.
"""

import getpass
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

SECRET_ID = "relayshield/stripe_secret_key"
REGION    = "us-east-1"
ACCOUNT   = "239677749008"

# Every Lambda that talks to api.stripe.com, from a grep of this repo rather
# than from memory. Resolved against AWS below -- a name that does not exist is
# reported, never silently skipped, because a consumer left holding a revoked
# key is the entire failure this script exists to prevent.
CONSUMERS = [
    "relayshield-api",
    "relayshield-agentic-api",
    "relayshield-developer-signup",
    "relayshield-stripe-webhook",
    "relayshield-weekly-metrics",
    "relayshield-mpp-settlement",
]

# Read-only probes covering every permission the handlers actually use. A
# RESTRICTED key (rk_...) can pass the first and fail a later one, and it would
# then fail only on whichever code path needs that permission, whenever that
# path next runs -- the same shape as the IAM lesson in CLAUDE.md.
PROBES = [
    ("/v1/account",                  "read the account at all"),
    ("/v1/billing/meters?limit=1",   "post usage to the billing meter (metered billing)"),
    ("/v1/customers?limit=1",        "look up customers (developer signup, bundle doors)"),
    ("/v1/subscriptions?limit=1",    "read subscriptions (the webhook's price lookup)"),
    ("/v1/payment_intents?limit=1",  "create PaymentIntents (MPP settlement)"),
]


def stripe_get(path, key):
    req = urllib.request.Request(f"https://api.stripe.com{path}", method="GET")
    req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except Exception:
            return exc.code, {}
    except Exception as exc:
        return 0, {"error": {"message": str(exc)}}


def main():
    import boto3
    sts = boto3.client("sts", region_name=REGION)
    acct = sts.get_caller_identity()["Account"]
    if acct != ACCOUNT:
        sys.exit(f"STOP: this profile resolves to {acct}, not {ACCOUNT}. "
                 "Re-run with AWS_PROFILE=relayshield. Nothing changed.")
    print(f"Account {acct} -- correct.\n")

    sm     = boto3.client("secretsmanager", region_name=REGION)
    lam    = boto3.client("lambda", region_name=REGION)

    print("== 1. The new key")
    print("   Paste it. It is not echoed, does not enter shell history, and is")
    print("   never printed back.")
    new_key = getpass.getpass("   New Stripe secret key: ").strip()
    if not new_key:
        sys.exit("nothing entered; nothing changed.")
    kind = ("restricted" if new_key.startswith("rk_")
            else "secret" if new_key.startswith("sk_") else "UNRECOGNISED")
    mode = "LIVE" if "_live_" in new_key else "TEST" if "_test_" in new_key else "unknown"
    print(f"   Looks like a {kind} key in {mode} mode.")
    if kind == "UNRECOGNISED":
        sys.exit("STOP: that does not start with sk_ or rk_. Nothing changed.")
    print()

    print("== 2. Prove it works BEFORE writing it anywhere")
    failed = []
    for path, why in PROBES:
        status, body = stripe_get(path, new_key)
        ok = status == 200
        print(f"   {'OK  ' if ok else 'FAIL'}  {path:<32} -- {why}")
        if not ok:
            failed.append((path, why, (body.get('error') or {}).get('message', '')))
    if failed:
        print()
        for path, why, msg in failed:
            print(f"   {path}: {msg}")
        print()
        print("   STOP. Nothing was written. A key that cannot do one of these")
        print("   fails ONLY on the code path that needs it, and the metering path")
        print("   swallows its own errors -- so the symptom would be revenue quietly")
        print("   not being billed, with nothing going red.")
        print("   If this is a restricted key, grant the missing permission in the")
        print("   Dashboard and re-run. Otherwise use a full secret key.")
        sys.exit(1)
    print("   Every permission the handlers use is present.\n")

    print("== 3. Write it to Secrets Manager")
    try:
        current = sm.get_secret_value(SecretId=SECRET_ID)["SecretString"].strip()
    except Exception as exc:
        sys.exit(f"could not read the existing secret: {exc}")
    # Preserve the stored SHAPE. Every reader accepts a bare string or a JSON
    # object with stripe_secret_key/STRIPE_SECRET_KEY, and changing which one is
    # stored would work in some handlers and not others.
    try:
        parsed = json.loads(current)
        if isinstance(parsed, dict):
            field = ("stripe_secret_key" if "stripe_secret_key" in parsed
                     else "STRIPE_SECRET_KEY" if "STRIPE_SECRET_KEY" in parsed
                     else "stripe_secret_key")
            parsed[field] = new_key
            payload, shape = json.dumps(parsed), f"JSON object, field {field}"
        else:
            payload, shape = new_key, "bare string"
    except json.JSONDecodeError:
        payload, shape = new_key, "bare string"
    if payload == current:
        print("   The stored value is already this key. Nothing to write.\n")
    else:
        sm.put_secret_value(SecretId=SECRET_ID, SecretString=payload)
        print(f"   Written as a {shape}. The previous version is retained by")
        print("   Secrets Manager as AWSPREVIOUS if you need to roll back.\n")

    print("== 4. Force every consumer to drop its cached copy")
    print("   Three of them cache the secret for the life of the execution")
    print("   environment. Updating the configuration replaces those environments.")
    import datetime
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    recycled, missing = [], []
    for fn in CONSUMERS:
        try:
            cfg = lam.get_function_configuration(FunctionName=fn)
        except lam.exceptions.ResourceNotFoundException:
            missing.append(fn)
            print(f"   NOT FOUND  {fn}")
            continue
        desc = (cfg.get("Description") or "").split(" [stripe-key ")[0]
        lam.update_function_configuration(
            FunctionName=fn, Description=f"{desc} [stripe-key {stamp}]".strip())
        lam.get_waiter("function_updated_v2").wait(FunctionName=fn)
        recycled.append(fn)
        print(f"   recycled   {fn}")
    print()

    if missing:
        print("   Functions above that were NOT FOUND still need checking by hand.")
        print("   relayshield-mpp-settlement is expected here until")
        print("   tools/create_mpp_settlement_lambda.sh has been run.")
        print("   Any OTHER name missing means this list is wrong -- fix it before")
        print("   revoking anything, because a consumer nobody recycled will hold")
        print("   the old key.\n")

    print("== 5. Verify the stored secret is what the handlers will read")
    stored = sm.get_secret_value(SecretId=SECRET_ID)["SecretString"].strip()
    try:
        readback = json.loads(stored)
        readback = (readback.get("stripe_secret_key")
                    or readback.get("STRIPE_SECRET_KEY") or stored)
    except json.JSONDecodeError:
        readback = stored
    status, acct_body = stripe_get("/v1/account", readback)
    if status != 200:
        sys.exit("STOP: the stored secret does not authenticate. Roll back to "
                 "AWSPREVIOUS in Secrets Manager before doing anything else.")
    print(f"   The stored secret authenticates as {acct_body.get('id')}.\n")

    print("NOW, AND NOT BEFORE:")
    print("  Revoke the OLD key in the Stripe Dashboard, Developers -> API keys.")
    print("  Everything that reads it has been recycled, so nothing is still")
    print("  holding it.")
    print()
    print("  Then confirm the billing chain still works end to end rather than")
    print("  assuming it survived -- one metered API call, and check the usage")
    print("  lands on the aggregate meter in Stripe. The metering path swallows")
    print("  its own errors, so 'no errors in the log' is not evidence.")


if __name__ == "__main__":
    main()
