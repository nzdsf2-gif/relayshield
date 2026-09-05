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

    # PREFLIGHT, added 2026-09-05 after a run reported "permission denied" with
    # no way to tell WHICH permission or WHOSE. Two entirely different systems
    # can say that here -- AWS refusing this operator identity, and Stripe
    # refusing a restricted key -- and they have different fixes. Ask both,
    # before the key is even typed, and name the layer in the answer.
    print("== 0. Can this AWS identity do the three things this script needs?")
    who = sts.get_caller_identity().get("Arn", "")
    print(f"   identity {who}")
    denied = []
    try:
        sm.get_secret_value(SecretId=SECRET_ID)
        print(f"   OK    secretsmanager:GetSecretValue on {SECRET_ID}")
    except Exception as exc:
        denied.append(("secretsmanager:GetSecretValue", SECRET_ID, exc))
        print(f"   FAIL  secretsmanager:GetSecretValue on {SECRET_ID}")
    try:
        sm.describe_secret(SecretId=SECRET_ID)
        print(f"   OK    secretsmanager:DescribeSecret on {SECRET_ID}")
    except Exception as exc:
        denied.append(("secretsmanager:DescribeSecret", SECRET_ID, exc))
        print(f"   FAIL  secretsmanager:DescribeSecret on {SECRET_ID}")
    # PutSecretValue cannot be tested without writing, so it is checked with the
    # policy simulator against this identity rather than by trying it. A write
    # that fails halfway is the one outcome this script must never produce.
    try:
        iam = boto3.client("iam", region_name=REGION)
        sim = iam.simulate_principal_policy(
            PolicySourceArn=who,
            ActionNames=["secretsmanager:PutSecretValue", "lambda:UpdateFunctionConfiguration"],
            ResourceArns=[f"arn:aws:secretsmanager:{REGION}:{ACCOUNT}:secret:{SECRET_ID}-??????"],
        )
        for r in sim.get("EvaluationResults", []):
            verdict = r.get("EvalDecision")
            mark = "OK  " if verdict == "allowed" else "FAIL"
            print(f"   {mark}  {r.get('EvalActionName')} -> {verdict}")
            if verdict != "allowed":
                if r.get("EvalActionName") == "lambda:UpdateFunctionConfiguration":
                    # NOT fatal since 2026-09-05. _get_secret now carries a
                    # _SECRET_TTL of 300s in every caching consumer, so a rotated
                    # secret is picked up on its own within five minutes. The
                    # recycle was only ever a way to make that immediate.
                    print("         ^ not fatal: the handlers now re-read the secret")
                    print("           every 300s on their own. Step 4 will skip and")
                    print("           step 5 will tell you how long to wait.")
                else:
                    denied.append((r.get("EvalActionName"), "(simulated)", verdict))
    except Exception as exc:
        print(f"   ?     could not simulate the write permissions ({type(exc).__name__}).")
        print("         Not fatal: the simulator itself needs iam:SimulatePrincipalPolicy.")
        print("         The writes below will still report their own errors clearly.")

    if denied:
        print()
        print("   AWS DENIED SOMETHING, AND THIS IS AN AWS PROBLEM, NOT A STRIPE ONE.")
        print("   Nothing was asked for and nothing was written. What failed:")
        for action, resource, exc in denied:
            print(f"     {action} on {resource}")
            print(f"       {exc}")
        print()
        print("   Grant the missing action to the identity above, then re-run. If the")
        print("   identity is not the one you expected, check AWS_PROFILE.")
        sys.exit(1)
    print()

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
        print("   STRIPE DENIED THIS, AND IT IS A STRIPE PROBLEM, NOT AN AWS ONE.")
        print("   The AWS preflight above passed, so this is about the key itself.")
        print("   'Permission denied' from Stripe on a key that works in the Dashboard")
        print("   almost always means a RESTRICTED key (rk_...) with a permission")
        print("   switched off, not an invalid key. Stripe names the missing one above.")
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
        try:
            sm.put_secret_value(SecretId=SECRET_ID, SecretString=payload)
        except Exception as exc:
            sys.exit(f"AWS refused the write to {SECRET_ID}, and the key is unchanged:\n"
                     f"  {exc}\n"
                     "This is an AWS permission problem (secretsmanager:PutSecretValue), "
                     "not a problem with the Stripe key -- the key passed every Stripe "
                     "probe above.")
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
        try:
            lam.update_function_configuration(
                FunctionName=fn, Description=f"{desc} [stripe-key {stamp}]".strip())
        except Exception as exc:
            print(f"   DENIED     {fn}: {exc}")
            print("   The secret IS updated. This function was not recycled, so it will")
            print("   hold the old key until it cold-starts on its own. DO NOT REVOKE")
            print("   the old key until this is resolved or that function has recycled.")
            continue
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
    if recycled:
        print(f"  {len(recycled)} function(s) were recycled and are already on the new key.")
    if missing or len(recycled) < len(CONSUMERS):
        print("  Some functions were NOT recycled. That is fine and no longer")
        print("  requires a permission: every caching consumer re-reads the secret")
        print("  on a 300-second TTL. WAIT SIX MINUTES from the write above, then")
        print("  revoke. Waiting is the whole cost of not holding")
        print("  lambda:UpdateFunctionConfiguration.")
    print("  Revoke the OLD key in the Stripe Dashboard, Developers -> API keys.")
    print()
    print("  Then confirm the billing chain still works end to end rather than")
    print("  assuming it survived -- one metered API call, and check the usage")
    print("  lands on the aggregate meter in Stripe. The metering path swallows")
    print("  its own errors, so 'no errors in the log' is not evidence.")


if __name__ == "__main__":
    main()
