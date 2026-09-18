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
            "An AWS Marketplace product code is assigned by StartChangeSet when the\n"
            "product is created. If the product does not exist yet, there is no code\n"
            "to set and this step is premature."
        )


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
