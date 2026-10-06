#!/usr/bin/env python3
"""Read-only: what can a Crypto Shield Mobile user's API key actually do?

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/diagnose_cs_partner_key.py --email someone@example.com

WHY IT EXISTS. A partner who was given a free licence rather than paying through
Stripe has a key record that no CS Mobile code path ever created, and every
paid-screen entitlement in the app is decided by FLAGS ON THAT RECORD, not by
whether the person is a customer. The v1.6.0 screens (attack chain, SIM swap
enrolment) failed for exactly such a user, and nothing in the repo could say why
because the record lives only in DynamoDB. This prints the flags that decide it.

WHAT IT CHECKS, read out of relayshield_api.py rather than retyped: the
CS_MOBILE_ALLOWED_ENDPOINTS list, and the one condition that admits a call on
them without credits or a TI subscription -- `cs_mobile_access` on an ACTIVE key.
It does NOT evaluate the other admitting branches (credits, bundles, free tier);
it says so rather than implying a complete verdict.

NEVER PRINTS A KEY. Only the last six characters, to tell records apart. The
email is an argument and is never written anywhere. Read-only: no write call.
"""
import argparse
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ACCOUNT = "239677749008"
TABLE = "relayshield_api_keys"


def cs_mobile_endpoints() -> list:
    """The allowlist, parsed from the API source so there is one copy."""
    tree = ast.parse((ROOT / "relayshield_api.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "CS_MOBILE_ALLOWED_ENDPOINTS" for t in node.targets):
            return sorted(ast.literal_eval(node.value.args[0]))
    raise SystemExit("CS_MOBILE_ALLOWED_ENDPOINTS not found in relayshield_api.py")


def admitted_by_cs_mobile_branch(record: dict) -> bool:
    """Mirror of `is_cs_mobile_call` on an authenticated key: the key must be
    active (`_verify_rs_api_key`) and carry cs_mobile_access."""
    return bool(record.get("active")) and bool(record.get("cs_mobile_access"))


def describe(record: dict) -> list:
    k = str(record.get("api_key", ""))
    return [
        f"  key ...{k[-6:] if k else '??????'}",
        f"    active                 {bool(record.get('active'))}",
        f"    cs_mobile_access       {bool(record.get('cs_mobile_access'))}",
        f"    source                 {record.get('source')!r}",
        f"    stripe_subscription_id {'present' if record.get('stripe_subscription_id') else 'absent'}",
        f"    stripe_customer_id     {'present' if record.get('stripe_customer_id') else 'absent'}",
        f"    credit_balance         {record.get('credit_balance')!r}",
        f"    free_calls_remaining   {record.get('free_calls_remaining')!r}",
        f"    intel_plan_tier        {record.get('intel_plan_tier')!r}",
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", required=True)
    args = ap.parse_args()
    try:
        import boto3
        from boto3.dynamodb.conditions import Attr, Key
    except ImportError:
        raise SystemExit("ERROR: boto3 missing. Use ~/.rsvenv/bin/python.")
    acct = boto3.client("sts").get_caller_identity()["Account"]
    if acct != ACCOUNT:
        raise SystemExit(f"Refusing to run: credentials resolve to {acct}, not {ACCOUNT}. "
                         "Prefix the command with AWS_PROFILE=relayshield.")
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(TABLE)
    email = args.email.strip().lower()
    try:
        items = table.query(IndexName="email-index",
                            KeyConditionExpression=Key("email").eq(email)).get("Items", [])
        how = "email-index"
    except Exception as exc:  # the comment in developer_signup says no GSI once existed
        print(f"email-index query failed ({exc.__class__.__name__}); scanning instead", file=sys.stderr)
        items = table.scan(FilterExpression=Attr("email").eq(email)).get("Items", [])
        how = "scan"
    print(f"records for that email via {how}: {len(items)}\n")
    for r in items:
        print("\n".join(describe(r)))
        ok = admitted_by_cs_mobile_branch(r)
        print(f"    CS Mobile endpoints admitted by the cs_mobile branch: {'YES' if ok else 'NO'}")
        if not ok:
            print("      (other branches -- credits, bundles, free tier -- are NOT evaluated here)")
        print()
    if not items:
        print("NO RECORD. The app's email link (/developer/cs-mobile-link) cannot find a key for this "
              "address, so this person has no key in the app at all.")
    else:
        print("endpoints the cs_mobile branch covers:")
        for e in cs_mobile_endpoints():
            print("  ", e)
        print("\n/v1/sim-swap/enroll is NOT in that list: it needs only an ACTIVE key. "
              "The push delivery join needs the app's push token registered under THIS key.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
