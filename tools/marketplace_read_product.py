#!/usr/bin/env python3
"""Read a Marketplace change set and the entity it created. READ ONLY.

    python3 tools/marketplace_read_product.py --change-set-id 9hxvi0lkd62on8uhb1iv3yfbc
    python3 tools/marketplace_read_product.py --entity-id prod-xxxxxxxxxxxxx

WHY THIS EXISTS
---------------
Turning "create the product" into a workflow click without giving the reader a
way to read its RESULT back is half a step. That is exactly what was reported
on 2026-09-18: "Running GH Action in Step 5 doesn't make it obvious" what to
put in BUNDLE_B_PRODUCT_CODE.

AND THE ANSWER THE REPO HAD WRITTEN DOWN WAS WRONG. This repo's own submit
tool and the Bundle B runbook both said outright that the entity
id StartChangeSet returns IS the product code. It is not. Measured from our
own artefacts rather than from memory:

    entity id     prod-kkvurtspreofy          Catalog API identifier
    product code  46y72j0d99w7lyqkiqrakpc5k   TODO.md:1707, the value that
                                              goes in aws_product_code
    product code  5s4a96a1ui1a5efrom6udnm2g   relayshield_aws_marketplace.py:22

Two different namespaces. The product code is what ResolveCustomer returns and
what GetEntitlements(ProductCode=...) and BatchMeterUsage take, so setting the
entity id as BUNDLE_B_PRODUCT_CODE would match no key row, raise nothing, and
report success -- the exact failure shape the whole diagnostic was built for.

NOTE THE COLLISION THAT MAKES THIS EASY TO GET WRONG: a change set id is the
same 25-character lowercase-alphanumeric shape as a product code
(9hxvi0lkd62on8uhb1iv3yfbc, from TODO.md). Shape alone does not tell you which
one you are holding, which is why this tool labels every candidate by where it
came from.

WHETHER DescribeEntity CARRIES THE PRODUCT CODE IS UNVERIFIED. docs.aws.amazon.com
is egress-blocked from the container and the only DescribeEntity capture in this
repo is of an Offer, not a SaaSProduct. So this tool REPORTS what the API returns
instead of asserting what it should return, and says outright when it found
nothing -- the authoritative read is then the Marketplace Management Portal.
"""
import argparse
import json
import re
import sys

ACCOUNT = "239677749008"
CATALOG = "AWSMarketplace"
REGION = "us-east-1"

# Both real product codes recorded in this repo are 25 lowercase alphanumerics.
# Kept as a RANGE rather than pinned at 25: one observation of a length is not a
# specification, and a candidate rejected for being 24 characters would be the
# tool hiding the answer it was asked for.
CANDIDATE = re.compile(r"^[a-z0-9]{20,30}$")

# An entity id is NOT excluded by a second rule, deliberately. The first draft
# had one, and proving it by deletion showed it could never fire: prod-... is
# hyphenated and CANDIDATE allows no hyphen, so the shape alone already excludes
# every entity id. A guard nothing can trip is decoration, and this repo has
# shipped enough of those. test_product_code_is_not_entity_id.py asserts the
# exclusion as a property of CANDIDATE instead, which is where it actually lives.

PORTAL = "https://aws.amazon.com/marketplace/management/products/"


def walk(doc, path=""):
    """Every scalar in a nested document, with the key path that reached it."""
    if isinstance(doc, dict):
        for k, v in doc.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            yield from walk(v, f"{path}[{i}]")
    elif isinstance(doc, str):
        yield path, doc


def candidates(doc):
    out = []
    for path, value in walk(doc):
        if CANDIDATE.match(value):
            out.append((path, value))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--change-set-id", default="")
    ap.add_argument("--entity-id", default="")
    ap.add_argument("--full", action="store_true",
                    help="print the whole DetailsDocument as well")
    args = ap.parse_args()

    if not args.change_set_id and not args.entity_id:
        raise SystemExit("ERROR: give --change-set-id or --entity-id.")

    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        raise SystemExit("ERROR: boto3 is not installed. python3 -m pip install boto3")

    who = boto3.client("sts", region_name=REGION).get_caller_identity()
    if who["Account"] != ACCOUNT:
        raise SystemExit(
            f"Refusing to run: credentials resolve to {who['Account']}, not {ACCOUNT}.\n"
            "620534471984 is the pre-audit account. Nothing was read.")

    cat = boto3.client("marketplace-catalog", region_name=REGION)
    entity_id = args.entity_id

    if args.change_set_id:
        print(f"== CHANGE SET {args.change_set_id}")
        try:
            cs = cat.describe_change_set(Catalog=CATALOG,
                                         ChangeSetId=args.change_set_id)
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in ("AccessDeniedException", "UnauthorizedException"):
                raise SystemExit(
                    f"ERROR: {code} on DescribeChangeSet. The catalog grant has never\n"
                    "       been applied: sh tools/apply_marketplace_catalog_policy.sh")
            raise SystemExit(f"ERROR: {code}: {exc.response['Error'].get('Message','')[:400]}")

        status = cs.get("Status", "")
        print(f"   Status : {status}")
        if status == "FAILED":
            if cs.get("FailureDescription"):
                print(f"   Failure: {cs['FailureDescription']}")
            for ch in cs.get("ChangeSet", []):
                for e in ch.get("ErrorDetailList", []) or []:
                    print(f"   Error  : {e.get('ErrorCode')} {e.get('ErrorMessage','')[:300]}")
        for ch in cs.get("ChangeSet", []):
            ident = (ch.get("Entity") or {}).get("Identifier", "")
            print(f"   {ch.get('ChangeType','')}: {ident or '(no identifier yet)'}")
            if ident.startswith("prod-") and not entity_id:
                entity_id = ident
        # FAILED and APPLYING are different answers with different next moves,
        # and the first draft printed the "wait and re-run" text for both --
        # telling the reader to wait for something that will never succeed.
        if status == "FAILED":
            print("\n   FAILED. Nothing was created, so there is no product and no")
            print("   product code. The error lines above name the field; fix the")
            print("   change set JSON and submit it again.")
            return 0
        if status != "SUCCEEDED":
            print("\n   NOT SUCCEEDED YET. PREPARING and APPLYING mean AWS is still")
            print("   working; re-run this in a few minutes. A product does not exist")
            print("   until SUCCEEDED, so there is no product code to read.")
            if not entity_id:
                return 0

    if not entity_id:
        print("\nNo prod- entity id in that change set. Nothing further to read.")
        return 0

    print(f"\n== ENTITY {entity_id}")
    try:
        ent = cat.describe_entity(Catalog=CATALOG, EntityId=entity_id)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        raise SystemExit(f"ERROR: {code}: {exc.response['Error'].get('Message','')[:400]}")

    print(f"   EntityType : {ent.get('EntityType')}")
    print(f"   EntityArn  : {ent.get('EntityArn')}")

    details = ent.get("DetailsDocument")
    if details is None:
        raw = ent.get("Details") or "{}"
        try:
            details = json.loads(raw)
        except json.JSONDecodeError:
            details = {}

    if args.full:
        print("\n-- DetailsDocument --")
        print(json.dumps(details, indent=2, default=str)[:20000])

    found = candidates(details)
    print("\n== PRODUCT CODE CANDIDATES in the entity document")
    if found:
        for path, value in found:
            print(f"   {path} = {value}")
        print("\n   A product code is 20-30 lowercase alphanumerics. So is a change")
        print("   set id, so read the KEY PATH beside each value, not the shape.")
    else:
        print("   NONE. The entity document carries no value of that shape.")
        print("\n   That is a finding about DescribeEntity, not about the product.")
        print("   The authoritative read is the Marketplace Management Portal:")
        print(f"     {PORTAL}")
        print("   Open the product, and the product code is on its page. It is also")
        print("   in the SNS topic ARN AWS creates for the listing, which ends in the")
        print("   product code (relayshield_aws_marketplace.py:23 records one).")

    print(f"\n   The entity id is {entity_id}. That is NOT the product code -- it is")
    print("   the Catalog API identifier, and it is what the test-offer and")
    print("   go-public change sets take as product_id.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
