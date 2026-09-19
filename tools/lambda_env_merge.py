#!/usr/bin/env python3
"""Set ONE environment variable on a Lambda without deleting the others.

    python3 tools/lambda_env_merge.py --function F --key K --value V           # plan
    python3 tools/lambda_env_merge.py --function F --key K --value V --apply

WHY THIS EXISTS, AND IT IS NOT CONVENIENCE
------------------------------------------
`aws lambda update-function-configuration --environment` REPLACES the whole
variables block. It does not merge. On 2026-09-18 a bare command setting
BUNDLE_B_PRODUCT_CODE on relayshield-bundle-fulfillment left that function
holding exactly one variable, and the API returned a success block showing
the new state -- which is indistinguishable from a correct result, because it
IS the correct result of the command that was sent.

relayshield_bundle_fulfillment.py reads THREE product codes. An emptied
BUNDLE_D_PRODUCT_CODE raises nothing: PRODUCT_CODES loses the entry,
_product_code_filter() stops matching any existing key row, and revocation
and suspension scans over a LIVE listing find nothing and report success.

So the fix is not a more careful command. It is a tool that GETs the block,
merges, and refuses to write a result that drops a key. The hazard stops
being something a reader has to remember.

It runs in GitHub Actions (marketplace_lambda_env.yml) so the value never has
to be pasted into a terminal, and it runs on the Mac identically.
"""
import argparse
import json
import re
import subprocess
import sys

ACCOUNT = "239677749008"
REGION = "us-east-1"

# A 40-character lowercase hex string is a git commit SHA, and that is exactly
# what was pasted into this field on 2026-09-18 -- the prompt asked for a value
# that did not exist yet, so the newest 40-hex string in the terminal was the
# reasonable thing to reach for. An AWS product code is assigned by
# StartChangeSet and is never this shape.
GIT_SHA = re.compile(r"^[0-9a-f]{40}$")

# AN ENTITY ID IS NOT A PRODUCT CODE, and until 2026-09-18 this repo's own submit
# tool and the Bundle B runbook both said it was. Measured from our own artefacts,
# because docs.aws.amazon.com is egress-blocked from the container:
#
#     entity id     prod-kkvurtspreofy          Catalog API identifier
#     product code  46y72j0d99w7lyqkiqrakpc5k   TODO.md:1707
#     product code  5s4a96a1ui1a5efrom6udnm2g   relayshield_aws_marketplace.py:22
#
# The product code is what ResolveCustomer returns and what GetEntitlements and
# BatchMeterUsage take. An entity id in this field matches no key row, raises
# nothing, and reports success -- strictly worse than the git SHA, because the
# SHA at least looks wrong.
ENTITY_ID = re.compile(r"^prod-[a-z0-9]+$")

# Both observed codes are 25 lowercase alphanumerics. This WARNS rather than
# refuses: one length seen twice is not a specification, and a tool that blocks
# a correct value is worse than one that questions it.
CODE_SHAPE = re.compile(r"^[a-z0-9]{20,30}$")


class Refused(Exception):
    pass


def aws(*args: str) -> str:
    cmd = ["aws", "--region", REGION, "--no-cli-pager", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise Refused(f"aws {' '.join(args[:2])} failed:\n{proc.stderr.strip()}")
    return proc.stdout


def assert_account() -> None:
    got = aws("sts", "get-caller-identity", "--query", "Account", "--output", "text").strip()
    if got != ACCOUNT:
        raise Refused(
            f"credentials resolve to {got}, not {ACCOUNT}. Nothing was read or written.\n"
            "620534471984 is the pre-audit account and a write there SUCCEEDS silently."
        )


def validate(key: str, value: str) -> None:
    if not value:
        raise Refused("empty value. To clear a key, say so explicitly; this tool only sets.")
    if key.endswith("_PRODUCT_CODE") and GIT_SHA.match(value):
        raise Refused(
            f"{key} was given {value!r}, which is a 40-character git commit SHA.\n"
            "That is the commit shown in the Actions run page HEADER, which is the\n"
            "most copyable 40-hex string on that screen and is never a product code.\n"
            "A product code is 20-30 lowercase alphanumerics, and it is returned by\n"
            "ResolveCustomer when a customer subscribes -- NOT by StartChangeSet,\n"
            "which returns the prod-... entity id. So it does not exist until the\n"
            "E2E subscription runs, and that test does not need this key set."
        )
    if key.endswith("_PRODUCT_CODE") and ENTITY_ID.match(value):
        raise Refused(
            f"{key} was given {value!r}, which is a Catalog API ENTITY ID, not a\n"
            "product code. They are different namespaces: the entity id is what\n"
            "StartChangeSet returns and what the test-offer and go-public change\n"
            "sets take; the product code is what ResolveCustomer returns and what\n"
            "GetEntitlements and BatchMeterUsage take.\n\n"
            "AND THIS STEP IS PREMATURE, WHICH IS THE LARGER FINDING. The code is\n"
            "assigned to a SUBSCRIPTION, so it does not exist until the E2E test\n"
            "runs -- and that test does NOT need this key. BUNDLE_CONFIGS in\n"
            "relayshield_bundle_fulfillment.py is keyed on the entitlement\n"
            "DIMENSION, ResolveCustomer supplies the code at fulfillment time, and\n"
            "the mismatch guard needs both sides non-empty so an unset key skips\n"
            "it. Run the test offer and the subscription first; the subscription\n"
            "prints the real code in its own CloudWatch line:\n"
            "    Product code not recognised: got <THE CODE>, known [...]\n"
            "Set this key from that line, afterwards. Do not go hunting for it."
        )


def shape_note(key: str, value: str) -> str:
    if key.endswith("_PRODUCT_CODE") and not CODE_SHAPE.match(value):
        return ("NOTE: both product codes recorded in this repo are 20-30 lowercase\n"
                "      alphanumerics and this value is not. Not refused, because one\n"
                "      observed shape is not a specification. Check it before apply.")
    return ""


def current(function: str) -> dict:
    raw = aws("lambda", "get-function-configuration", "--function-name", function,
              "--query", "Environment.Variables", "--output", "json")
    doc = json.loads(raw or "null")
    return doc if isinstance(doc, dict) else {}


def merged(before: dict, key: str, value: str) -> dict:
    after = dict(before)
    after[key] = value
    # The whole point. A result that loses a key is the defect this replaces.
    missing = set(before) - set(after)
    if missing:
        raise Refused(f"the merged block would drop {sorted(missing)}. Refusing.")
    return after


def redact(d: dict) -> dict:
    """Never print a value that is not the one being set.

    These blocks carry live secrets. deploy_lambdas.yml learned this the
    expensive way: its default output printed the full configuration, so every
    deploy put secrets in plaintext into a log anyone with repo read access
    can fetch.
    """
    return {k: (v if k.endswith("_PRODUCT_CODE") else "<redacted>") for k, v in d.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--function", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--value", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    try:
        validate(args.key, args.value)
        assert_account()
        before = current(args.function)
        after = merged(before, args.key, args.value)
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    print(f"function : {args.function}")
    print(f"before   : {json.dumps(redact(before), sort_keys=True)}")
    print(f"after    : {json.dumps(redact(after), sort_keys=True)}")
    kept = sorted(set(before) - {args.key})
    print(f"preserved: {kept if kept else '(none -- the block held only this key)'}")
    note = shape_note(args.key, args.value)
    if note:
        print(note)

    if not args.apply:
        print("\nPLAN ONLY. Nothing was written. Re-run with --apply.")
        return 0

    try:
        aws("lambda", "update-function-configuration",
            "--function-name", args.function,
            "--environment", json.dumps({"Variables": after}),
            "--query", "FunctionName", "--output", "text")
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print("\nAPPLIED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
