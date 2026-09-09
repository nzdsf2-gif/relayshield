#!/usr/bin/env python3
"""Add a usage dimension to the live Bundle D AWS Marketplace listing, safely.

WHY THIS EXISTS, AND WHY IT IS NOT A CONSOLE SESSION. Asked 2026-09-08 whether
agent-bait-scan could be added to Bundle D "remotely". The first answer given was
that it needs a human at the AWS console. That was wrong, and the correction is
worth stating because it is CLAUDE.md's own rule: a container without credentials
does not mean the check cannot happen, it means the check MOVES -- into a
committed script run on the Mac, or into GitHub Actions, which holds the OIDC
role. `lambda_drift_check.yml` and `recover_live_handler.yml` are the precedent.

Adding a dimension is an API call, `StartChangeSet` on the Marketplace Catalog
API against entity prod-kkvurtspreofy. Nothing about it requires a browser.

WHAT DOES REQUIRE CARE, and it is documented in this repo in the file the change
would affect. From relayshield_bundle_fulfillment.py:

    Bundle A was originally planned for that same entity, but adding it there
    meant submitting a change set that replaces the whole rate card, which had
    already rolled Bundle D's prices back to placeholders once (2026-07-27).

So a change set does not ADD a dimension to a rate card, it REPLACES the rate
card, and a malformed one has already zeroed live prices on this exact product.
That is the reason this script reads before it writes, and refuses to write from
anything but a freshly captured entity.

TWO PREREQUISITES, NEITHER OF WHICH IS SATISFIED TODAY:

  1. `relayshield-github-deploy` has NO catalog permissions. The IAM snapshot
     carries aws-marketplace:MeterUsage, BatchMeterUsage and ResolveCustomer --
     metering only. `DescribeEntity`, `ListEntities` and `StartChangeSet` are all
     absent, so even --describe fails until they are granted.
  2. The product decision. relayshield_agentic_api.py's AWS_DIMENSION_NAMES
     carries a comment saying agent-bait-scan is deliberately absent until the
     endpoint has a MEASURED false-positive rate, because a published dimension is
     an expensive place to discover a heuristic needs tuning. An AWS-licensed
     caller is meanwhile billed on the Stripe rail, so nothing is free and nothing
     is blocked. This script does not overrule that; it exists so the decision is
     the only thing left.

Modes, in the order they must be used:

    --describe                 read-only. Captures the CURRENT entity to a file.
    --plan --from <file>       builds the change set from that capture, prints it.
    --apply --from <file>      sends it. Refuses a capture older than 24 hours.
"""

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

ENTITY_ID = os.environ.get("BUNDLE_D_ENTITY_ID", "prod-kkvurtspreofy")
CATALOG = "AWSMarketplace"
REGION = "us-east-1"

# The dimension to add. Its API name must match what relayshield_agentic_api.py
# sends to MeterUsage, or the meter call silently reports an unknown dimension.
NEW_DIMENSION = {
    "Key": "agent_bait_scan",
    "Description": "Agent-bait scan: screens a repository's agent-facing instructions",
    "Name": "Agent-bait scan",
    "Types": ["Metered"],
    "Unit": "UnitsOfMeasure",
}


def _client():
    try:
        import boto3
    except ImportError:
        raise SystemExit("ERROR: boto3 is not installed. In Actions the workflow "
                         "installs it; on the Mac use ~/.rsvenv/bin/python.")
    return boto3.client("marketplace-catalog", region_name=REGION)


def describe(out_path: Path) -> int:
    from botocore.exceptions import ClientError
    try:
        entity = _client().describe_entity(Catalog=CATALOG, EntityId=ENTITY_ID)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("AccessDeniedException", "UnauthorizedException"):
            raise SystemExit(
                f"ERROR: {code} on DescribeEntity.\n"
                "       Expected until the role is granted catalog permissions. The\n"
                "       IAM snapshot shows only aws-marketplace:MeterUsage,\n"
                "       BatchMeterUsage and ResolveCustomer. This needs\n"
                "       DescribeEntity, ListEntities and StartChangeSet."
            )
        raise SystemExit(f"ERROR: {code}: {e.response['Error'].get('Message','')[:200]}")

    entity["_captured_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    out_path.write_text(json.dumps(entity, indent=2, default=str))
    details = json.loads(entity.get("Details") or "{}")
    dims = details.get("Dimensions", [])
    print(f"captured {ENTITY_ID} -> {out_path}")
    print(f"  entity type   : {entity.get('EntityType')}")
    print(f"  last modified : {entity.get('LastModifiedDate')}")
    print(f"  dimensions    : {len(dims)}")
    for d in dims:
        print(f"    - {d.get('Key')}  ({d.get('Name')})")
    return 0


def _load(from_path: Path, max_age_hours: int | None):
    if not from_path.is_file():
        raise SystemExit(f"ERROR: {from_path} not found. Run --describe first.")
    entity = json.loads(from_path.read_text())
    captured = entity.get("_captured_at")
    if max_age_hours is not None:
        if not captured:
            raise SystemExit("ERROR: capture has no _captured_at. Re-run --describe.")
        age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(captured)
        if age > dt.timedelta(hours=max_age_hours):
            raise SystemExit(
                f"ERROR: the capture is {age} old, older than {max_age_hours}h.\n"
                "       A change set REPLACES the whole rate card, so building one\n"
                "       from a stale read is how prices get rolled back to\n"
                "       placeholders. That happened on this product on 2026-07-27.\n"
                "       Re-run --describe."
            )
    return entity


# THE INFORMATION BLOCK REPLACES, EXACTLY LIKE THE RATE CARD DOES.
#
# UpdateInformation is not a patch. Whatever this document contains becomes the
# listing, so a change set that names three fields and omits the other six blanks
# them on a PUBLISHED page. Same failure mode as 2026-07-27's prices rolled back
# to placeholders, one entity section over.
#
# So the override file is a PARTIAL and the other fields are round-tripped from
# the live capture. Nothing is retyped, which means nothing can be retyped wrong.
#
# THE SHAPE IS FLAT AND WAS VERIFIED, NOT GUESSED. The nine keys below are read
# out of aws_marketplace/bundle_a_create_entity.json, a change set AWS actually
# accepted. Guessing would have produced {"Description": {...}} by analogy with
# the DescribeEntity response, where these fields ARE nested -- the read shape and
# the write shape genuinely differ, and only one of them is in our own artefacts.
_INFO_FROM_ENTITY = {
    "ProductTitle":        ("Description", "ProductTitle"),
    "ShortDescription":    ("Description", "ShortDescription"),
    "LongDescription":     ("Description", "LongDescription"),
    "Highlights":          ("Description", "Highlights"),
    "SearchKeywords":      ("Description", "SearchKeywords"),
    "Categories":          ("Description", "Categories"),
    "LogoUrl":             ("PromotionalResources", "LogoUrl"),
    "AdditionalResources": ("PromotionalResources", "AdditionalResources"),
    "SupportDescription":  ("SupportInformation", "Description"),
}

# Held at what AWS has already accepted rather than at what reads best. See the
# _why block in aws_marketplace/bundle_d_listing_copy.json: a rejected change set
# costs a review cycle on a published listing, and this one carries the dimension
# with it.
_MAX_HIGHLIGHTS = 3


def copy_change(entity: dict, details: dict, copy_path: Path):
    """Build the UpdateInformation change, or return None if there is nothing
    to change."""
    override = json.loads(copy_path.read_text(encoding="utf-8"))
    override = {k: v for k, v in override.items() if not k.startswith("_")}

    doc = {}
    for field, (section, key) in _INFO_FROM_ENTITY.items():
        doc[field] = (details.get(section) or {}).get(key)

    # A field the capture does not carry cannot be round-tripped, and sending
    # None for it is how a live listing loses its logo or its support text.
    blank = [f for f, v in doc.items()
             if f not in override and v in (None, "", [])
             and f not in ("AdditionalResources",)]
    if blank:
        raise SystemExit(
            "REFUSING: the capture has no value for "
            f"{', '.join(blank)}.\n"
            "          UpdateInformation REPLACES the whole information block, so\n"
            "          submitting this would blank those fields on a published\n"
            "          listing. Re-run --describe against the product entity."
        )

    doc.update(override)

    if len(doc.get("Highlights") or []) > _MAX_HIGHLIGHTS:
        raise SystemExit(
            f"REFUSING: {len(doc['Highlights'])} highlights. AWS documents a maximum\n"
            f"          of {_MAX_HIGHLIGHTS}, and the accepted change set in\n"
            "          aws_marketplace/bundle_a_create_entity.json carries three.\n"
            "          A rejection costs a review cycle on a live listing."
        )

    # MEASUREMENT DOCTRINE, enforced rather than remembered. These are the exact
    # figures the live listing carried in three places, and the ones a competitor
    # reading the page would check. The doctrine has said since August that the
    # corpus headline is never quoted; the listing was the last public place we
    # were still doing it, and nothing stopped a future session putting a fresh
    # number back.
    prose = " ".join(str(doc.get(f) or "") for f in
                     ("ShortDescription", "LongDescription")) + " " + \
            " ".join(doc.get("Highlights") or [])
    for banned in ("5.0M", "3,750", "85+ monitored", "494K", "5.8M sightings"):
        if banned in prose:
            raise SystemExit(
                f"REFUSING: the copy quotes '{banned}'. MEASUREMENT DOCTRINE: the\n"
                "          corpus headline is never quoted, least of all on a public\n"
                "          listing. Name the sources, which do not change, rather\n"
                "          than counts, which do."
            )

    if all(doc[f] == (details.get(sec) or {}).get(k)
           for f, (sec, k) in _INFO_FROM_ENTITY.items()):
        return None

    return {
        "ChangeType": "UpdateInformation",
        "Entity": {"Type": entity["EntityType"], "Identifier": ENTITY_ID},
        "DetailsDocument": doc,
    }, override


def plan(from_path: Path, max_age_hours: int | None, copy_path: Path | None = None):
    entity = _load(from_path, max_age_hours)
    details = json.loads(entity.get("Details") or "{}")
    dims = list(details.get("Dimensions", []))

    # THE GUARD THAT CAUGHT A REAL TRAP, found by running this against
    # aws_marketplace/offer_baseline_2026-07-31.json on 2026-09-08. That file is
    # an Offer@1.0 entity carrying ZERO dimensions, while the product plainly has
    # two live ones (mcp_registry_risk, prompt_injection_breach, both in
    # relayshield_agentic_api.py's AWS_DIMENSION_NAMES). Dimensions live on the
    # SaaS PRODUCT entity, not on the offer.
    #
    # Building a rate card from the wrong entity is precisely how prices got
    # rolled back to placeholders on 2026-07-27: the change set replaces the card
    # with whatever you hand it, and an empty card is a valid document.
    entity_type = entity.get("EntityType", "")
    if not entity_type.startswith("SaaSProduct"):
        raise SystemExit(
            f"REFUSING: captured entity is {entity_type!r}, not a SaaSProduct.\n"
            "          Usage dimensions live on the PRODUCT entity, not the offer.\n"
            "          Re-run --describe against the product entity id."
        )
    # ALL SIX live dimensions, read from the real DescribeEntity capture on
    # 2026-09-09. The first version of this guard named only two, taken from
    # AWS_DIMENSION_NAMES in relayshield_agentic_api.py -- but that table maps
    # only the endpoints we METER through the Marketplace rail, not the
    # dimensions the LISTING carries. Four more exist:
    # agentic_bundle_access (the Entitled monthly minimum), bulk_identity_risk,
    # tech_stack_cve and llm_credential_exposure.
    #
    # THE DEFECT THAT MATTERED: a capture holding only those two would have
    # PASSED the old guard, and a change set built from it could have dropped
    # four live dimensions including the Entitled one that carries the monthly
    # commitment. That is the 2026-07-27 "prices rolled back to placeholders"
    # failure with a guard in front of it that did not look.
    known = ["agentic_bundle_access", "bulk_identity_risk", "tech_stack_cve",
             "mcp_registry_risk", "prompt_injection_breach", "llm_credential_exposure"]
    present = {d.get("Key") for d in dims}
    missing = [k for k in known if k not in present]
    if missing:
        raise SystemExit(
            "REFUSING: the capture is missing dimensions this product is known to\n"
            f"          have live: {', '.join(missing)}.\n"
            f"          It carries {len(dims)}: {sorted(present) or 'none'}.\n"
            "          A change set REPLACES the rate card, so submitting from this\n"
            "          capture would drop the live dimensions. Re-run --describe and\n"
            "          check you are reading the right entity."
        )

    change_set = []
    print(f"entity        : {ENTITY_ID} ({entity['EntityType']})")
    print(f"captured at   : {entity.get('_captured_at')}")

    if any(d.get("Key") == NEW_DIMENSION["Key"] for d in dims):
        print(f"dimension     : '{NEW_DIMENSION['Key']}' is already on this product, "
              "nothing to add")
    else:
        # The whole rate card goes back, existing dimensions preserved verbatim.
        dims.append(NEW_DIMENSION)
        change_set.append({
            "ChangeType": "AddDimensions",
            "Entity": {"Type": entity["EntityType"], "Identifier": ENTITY_ID},
            "DetailsDocument": {"Dimensions": [NEW_DIMENSION]},
        })
        print(f"dimensions    : {len(dims) - 1} -> {len(dims)}")
        print("existing, preserved:")
        for d in dims[:-1]:
            print(f"    - {d.get('Key')}")
        print("adding:")
        print(json.dumps(NEW_DIMENSION, indent=2))

    # BATCHED WITH THE DIMENSION, NOT SUBMITTED SEPARATELY. One change set is one
    # AWS review cycle. Two submissions against the same published listing is two
    # cycles and a window in which the copy advertises agent-bait scanning while
    # the rate card cannot bill it.
    if copy_path is not None:
        built = copy_change(entity, details, copy_path)
        if built is None:
            print("copy          : the live listing already matches the override file")
        else:
            change, override = built
            change_set.append(change)
            print(f"copy          : {len(override)} field(s) overridden "
                  f"({', '.join(sorted(override))})")
            for field in sorted(override):
                live = (details.get("Description") or {}).get(field)
                print(f"\n  --- {field} ---")
                print(f"  was : {json.dumps(live)[:300]}")
                print(f"  now : {json.dumps(change['DetailsDocument'][field])[:300]}")

    if not change_set:
        print("\nNothing to do.")
        return None

    print("\nchange set that would be sent:")
    print(json.dumps(change_set, indent=2)[:6000])
    return change_set


def main() -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--describe", action="store_true")
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--apply", action="store_true")
    ap.add_argument("--from", dest="from_path", default="aws_marketplace/entity_current.json")
    ap.add_argument("--out", default="aws_marketplace/entity_current.json")
    ap.add_argument("--i-have-read-the-rate-card-warning", action="store_true",
                    help="required for --apply. See the docstring.")
    ap.add_argument("--with-copy", nargs="?", const="aws_marketplace/bundle_d_listing_copy.json",
                    default=None, metavar="FILE",
                    help="also send the listing-copy change, batched into the SAME "
                         "change set. One submission is one AWS review cycle.")
    args = ap.parse_args()

    if args.describe:
        out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
        return describe(out)

    copy_path = Path(args.with_copy) if args.with_copy else None

    if args.plan:
        plan(Path(args.from_path), max_age_hours=None, copy_path=copy_path)
        return 0

    if not args.i_have_read_the_rate_card_warning:
        raise SystemExit(
            "REFUSING TO APPLY. A change set REPLACES the whole rate card on a\n"
            "PUBLISHED listing, and a malformed one rolled this product's prices\n"
            "back to placeholders on 2026-07-27. Read the docstring, then pass\n"
            "--i-have-read-the-rate-card-warning.\n\n"
            "Note also the product decision this does not overrule: the endpoint\n"
            "has no measured false-positive rate yet, and a published dimension is\n"
            "an expensive place to find out a heuristic needs tuning."
        )

    change_set = plan(Path(args.from_path), max_age_hours=24, copy_path=copy_path)
    if change_set is None:
        return 0
    name = ("add-agent-bait-dimension-and-listing-copy" if copy_path
            else "add-agent-bait-scan-dimension")
    resp = _client().start_change_set(
        Catalog=CATALOG, ChangeSet=change_set, ChangeSetName=name,
    )
    print("\nSUBMITTED.")
    print("  ChangeSetId :", resp.get("ChangeSetId"))
    print("  AWS reviews change sets on their own schedule. Track it in the\n"
          "  Marketplace Management Portal under Requests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
