#!/usr/bin/env python3
"""Submit a COMMITTED Marketplace change set file. The route Bundle B had none of.

WHY THIS EXISTS, AND IT IS A GAP RATHER THAN A PREFERENCE. `bundle_b_create_entity.json`
has been written and guarded by six tests since 2026-09-15, and nothing in this repo
could send it. `tools/marketplace_add_dimension.py` is hardcoded to
`BUNDLE_D_ENTITY_ID = prod-kkvurtspreofy`, reads that live entity, and builds a
dimension change set FROM the capture -- so it cannot submit a `CreateProduct`, which
by definition names no entity because AWS assigns the id.

So the change set existed, the tests passed, and the submission had no door. That is
"a route added to the handler's dispatch table is not a route" one layer out: the
artefact is real, the thing that would send it was never built, and every check we had
was checking the artefact.

    python3 tools/marketplace_submit_changeset.py aws_marketplace/bundle_b_create_entity.json
    python3 tools/marketplace_submit_changeset.py <file> --apply --confirm CREATE-NEW-PRODUCT

DEFAULT IS A DRY RUN. It prints exactly what would be sent and exits 0 without calling
AWS. `--apply` additionally requires the confirmation token typed by hand, because the
failure mode on this API is not an error, it is a silently wrong listing.

IT REFUSES TO TOUCH AN EXISTING ENTITY, and that refusal is the most important line in
the file. A change set does NOT add to a rate card, it REPLACES the card with whatever
it is handed, and a malformed one rolled Bundle D's prices back to placeholders on
2026-07-27. This tool is for CREATING products. Modifying a published one goes through
marketplace_add_dimension.py, which reads the live entity first and round-trips every
field it is not changing. Keeping those two jobs in two tools is what makes this one
safe to run without a capture.

RUNS ON THE MAC OR IN ACTIONS. The container has no usable AWS credentials, and the
Actions role `relayshield-github-deploy` is the identity `StartChangeSet` is called by
-- see .github/workflows/marketplace_changeset.yml. It needs the catalog grant first:

    sh tools/apply_marketplace_catalog_policy.sh

which is operator-side and once, because a role cannot widen its own permissions.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACCOUNT = "239677749008"
CATALOG = "AWSMarketplace"
CONFIRM_TOKEN = "CREATE-NEW-PRODUCT"

# Entities that are LIVE and must never be the target of this tool. Named
# explicitly rather than inferred: a published listing is exactly the thing whose
# rate card a bad change set replaces, and the guard is worth more when it names
# what it is protecting.
LIVE_ENTITIES = {
    "prod-kkvurtspreofy": "Bundle D, Agentic Attack Surface (LIVE, public)",
    "prod-f5qkfsxlxs4qg": "Bundle A, Core Identity Exposure (LIVE)",
    # ADDED 2026-09-22, THE DAY THE WITHDRAW CHANGE SET WAS WRITTEN, because that
    # file plus one mistyped --product-id takes the listing eight submissions
    # bought straight back off the marketplace. Public since 2026-09-21, carries
    # agreement agmt-29l852u6kqzmjh2me0pglvj9q and product code
    # cmh79gzztkdtp0dlzbdepa643. The two duplicates differ from it only by a
    # random suffix, which is precisely the shape that cost seven rounds.
    "prod-szi2wdww3obry":
        "Bundle B, Attack Surface & Supply Chain (LIVE, public since 2026-09-21)",
}

# THREE SaaS PRODUCTS CARRY THE BUNDLE B DISPLAY NAME, AND ONLY ONE CAN FULFIL.
# Measured 2026-09-22 with `aws marketplace-catalog list-entities`: three rows
# named "RelayShield - Attack Surface & Supply Chain API", all Limited. Seven
# visibility requests were refused because the Management Portal's own button
# selects by NAME and the wrong row was the one being submitted.
#
# prod-szi2wdww3obry is the real one: it carries agreement
# agmt-29l852u6kqzmjh2me0pglvj9q and product code cmh79gzztkdtp0dlzbdepa643,
# which holds the live entitlement. The other two have never been subscribed,
# fulfilled or metered, so AWS's "no successful metering records" was correct
# for them every single time.
#
# THE REFUSAL IS NARROW ON PURPOSE. Only TargetVisibility Public is blocked, so
# withdrawing a duplicate (Restricted / Limited) still works -- a guard that
# forces you to skip the legitimate cleanup step is the one that gets loosened.
DUPLICATE_BUNDLE_B = {
    "prod-v5nr5gjtdnofi":
        "a DUPLICATE Bundle B entity -- refused seven visibility requests, "
        "never subscribed",
    "prod-p3ei5nmgufnnq":
        "a DUPLICATE Bundle B entity -- never subscribed, fulfilled or metered",
}
BUNDLE_B_REAL = "prod-szi2wdww3obry"

# A change set that creates a product opens with CreateProduct. Anything else is
# either a modification (wrong tool) or a shape nobody has reviewed.
CREATE_TYPES = {"CreateProduct", "CreateOffer"}

# UpdateVisibility IS ALLOWED ON ITS OWN, and the first version of this guard
# refused it. That was a FALSE POSITIVE and fixing the guard rather than working
# around it is the point: flipping a product from Limited to Public replaces no
# rate card, it is the last step of the create sequence, and the refusal even
# named marketplace_add_dimension.py -- which cannot do UpdateVisibility either,
# so the reader was sent to a tool that would also refuse them.
#
# What actually protects the live listings is the LIVE_ENTITIES check below, not
# this one. UpdateVisibility against prod-kkvurtspreofy is still refused there,
# which is the case worth refusing: a published product taken private.
STANDALONE_TYPES = {"UpdateVisibility"}


class Refused(Exception):
    """A guard fired. The message is the reason, and it is printed verbatim."""


PLACEHOLDER_RE = __import__("re").compile(r"__[A-Z][A-Z0-9_]*__")


# A HAND-TYPED IDENTIFIER IS VALIDATED BEFORE IT IS SUBSTITUTED, NOT AFTER.
#
# 2026-09-19: an apply was refused because CREATE-NEW_PRODUCT was typed for
# CREATE-NEW-PRODUCT. That input is a dropdown now and cannot be mistyped.
# `product_id` cannot be a dropdown -- AWS assigns new ids -- so it gets the
# other half of the same treatment: a shape check here, which reproduces AWS's
# refusal in zero seconds instead of fifteen, and names the field.
#
# It also strips the `@N` revision, because DescribeChangeSet prints
# prod-szi2wdww3obry@1 and DescribeEntity and a change set both refuse it. The
# value a reader copies is the one with the suffix on it.
PRODUCT_ID = re.compile(r"^prod-[a-z0-9]+$")


def clean_product_id(raw: str) -> str:
    value = re.sub(r"@\d+$", "", (raw or "").strip())
    if not value:
        return ""
    if not PRODUCT_ID.match(value):
        raise Refused(
            f"--product-id was given {raw!r}, which is not an entity id.\n"
            "An entity id is 'prod-' followed by lowercase letters and digits,\n"
            "with no spaces and no @revision suffix. It is printed by the Apply\n"
            "step of the create run as 'CreateProduct: prod-....@1', and the\n"
            "'@1' is the revision -- strip it, which this tool does for you when\n"
            "the rest of the value is well formed."
        )
    return value


def substitute(doc: dict, product_id: str) -> dict:
    """Fill the placeholders a committed change set cannot carry literally.

    TWO FIELDS, AND NEITHER CAN BE COMMITTED WITH A REAL VALUE:

    `__BUNDLE_B_PRODUCT_ID__` -- AWS assigns the product id when CreateProduct
    succeeds, so it does not exist when the offer file is written. Guessing one
    would target a product that is not ours.

    `__CHARGE_DATE__` -- bundle_a_test_offer.json carries ChargeDate 2026-08-08,
    which was correct on the day it was submitted and is a date in the PAST for
    anyone running it since. A payment schedule in the past is rejected, so this
    is filled at send time and the date used is printed rather than assumed.

    `__AVAILABILITY_END_DATE__` -- the SAME defect in the SAME file, left behind
    when ChargeDate was fixed. A private offer needs UpdateAvailability or
    ReleaseOffer fails MISSING_AVAILABILITY_END_DATE (commit e72cc31, which cost
    Bundle A a submission), and Bundle A's literal 2026-09-06 was correct on the
    day and is in the past for anyone since. An END date in the past is worse
    than a charge date in the past: it can release an offer that has already
    expired, so the buyer account is told to subscribe to something it cannot
    see. Ninety days out, which outlives any verification run.
    """
    import datetime
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    raw = json.dumps(doc)
    if product_id:
        raw = raw.replace("__BUNDLE_B_PRODUCT_ID__", product_id)
    if "__CHARGE_DATE__" in raw:
        raw = raw.replace("__CHARGE_DATE__", today)
        print(f"charge date   : {today} (filled at send time, not committed)")
    if "__AVAILABILITY_END_DATE__" in raw:
        end = (datetime.datetime.now(datetime.timezone.utc).date()
               + datetime.timedelta(days=90)).isoformat()
        raw = raw.replace("__AVAILABILITY_END_DATE__", end)
        print(f"availability  : ends {end} (filled at send time, not committed)")
    return json.loads(raw)


def validate(doc: dict) -> list:
    """Return the change list, or raise Refused with the reason.

    PURE, and deliberately so: it takes a parsed document and touches nothing
    else, which is what lets every guard below be exercised in a container with
    no AWS credentials. A guard that can only be tested against the live API is
    a guard nobody runs.
    """
    if not isinstance(doc, dict):
        raise Refused("the file does not hold a JSON object")

    catalog = doc.get("Catalog")
    if catalog != CATALOG:
        raise Refused(
            f"Catalog is {catalog!r}, expected {CATALOG!r}. A change set for a "
            "different catalog is not one this account can submit.")

    changes = doc.get("ChangeSet")
    if not isinstance(changes, list) or not changes:
        raise Refused("ChangeSet is missing or empty. An empty change set is a "
                      "valid document that does nothing, which is worse than an "
                      "error because it returns success.")

    types = [c.get("ChangeType") for c in changes]
    if not (set(types) & CREATE_TYPES) and not set(types) <= STANDALONE_TYPES:
        raise Refused(
            f"{types} is neither a create sequence nor "
            f"{sorted(STANDALONE_TYPES)}.\n"
            "       This tool CREATES products and offers, and flips a new one to "
            "Public.\n"
            "       Changing a PUBLISHED listing replaces its whole rate card, so "
            "it goes\n"
            "       through tools/marketplace_add_dimension.py, which reads the "
            "live entity first.")

    # A LITERAL PLACEHOLDER MUST NEVER REACH AWS. This is rule 11 one layer out:
    # `<paste the key>` in a shell block is a syntax error the reader sees at
    # once, and `__BUNDLE_B_PRODUCT_ID__` in a change set is a string AWS will
    # accept into a field and then fail on, or worse, store.
    left = PLACEHOLDER_RE.findall(json.dumps(doc))
    if left:
        raise Refused(
            f"unsubstituted placeholder(s): {sorted(set(left))}.\n"
            "       __BUNDLE_B_PRODUCT_ID__ is filled with --product-id, using the "
            "id\n"
            "       StartChangeSet returned when the product was created.")

    for change in changes:
        ident = (change.get("Entity") or {}).get("Identifier", "")
        if ident in LIVE_ENTITIES:
            # THE ROUTE NAMED HAS TO BE ONE THAT CAN DO THE THING. The first
            # version of this message sent every refusal to
            # marketplace_add_dimension.py, which cannot do UpdateVisibility at
            # all -- the reader is then pointed at a second tool that also
            # refuses them, which this repo has already paid for once.
            if change.get("ChangeType") == "UpdateVisibility":
                target = (change.get("DetailsDocument") or {}).get(
                    "TargetVisibility", "?")
                raise Refused(
                    f"UpdateVisibility {target} targets {ident} -- "
                    f"{LIVE_ENTITIES[ident]}.\n"
                    "       REFUSING. This is a PUBLISHED listing, so Restricted "
                    "takes it off the\n"
                    "       marketplace and Limited is not a state a public "
                    "product returns to.\n"
                    "       If you meant to WITHDRAW A DUPLICATE, the ids differ "
                    "only by suffix:\n"
                    "       " + ", ".join(sorted(DUPLICATE_BUNDLE_B)) + "\n"
                    "       Withdrawing this listing on purpose is a deliberate "
                    "act: remove it from\n"
                    "       LIVE_ENTITIES in this file, in its own commit, and "
                    "say why there.")
            raise Refused(
                f"a change targets {ident} -- {LIVE_ENTITIES[ident]}.\n"
                "       REFUSING. A change set REPLACES the whole rate card of the "
                "entity it names,\n"
                "       and a malformed one rolled Bundle D's prices back to "
                "placeholders on 2026-07-27.\n"
                "       If you meant to modify that listing, use "
                "tools/marketplace_add_dimension.py.")

        if (change.get("ChangeType") == "UpdateVisibility"
                and ident in DUPLICATE_BUNDLE_B
                and (change.get("DetailsDocument") or {}).get(
                    "TargetVisibility") == "Public"):
            raise Refused(
                f"UpdateVisibility Public targets {ident} -- "
                f"{DUPLICATE_BUNDLE_B[ident]}.\n"
                "       REFUSING. Three SaaS products carry the Bundle B display "
                "name and only\n"
                f"       {BUNDLE_B_REAL} has an agreement, a product code and "
                "metering behind it.\n"
                "       Publishing this one gives buyers a listing that cannot "
                "fulfil.\n"
                f"       Pass --product-id {BUNDLE_B_REAL} instead. To WITHDRAW "
                "this duplicate,\n"
                "       set TargetVisibility to Restricted, which this guard "
                "allows.")

    return changes


def summarise(changes: list) -> None:
    """Print what would be sent, in the shape a reader can check against the plan."""
    print(f"changes       : {len(changes)}")
    for i, change in enumerate(changes, 1):
        entity = change.get("Entity") or {}
        ident = entity.get("Identifier")
        target = ident if ident else "NEW (AWS assigns the id)"
        print(f"  {i}. {change.get('ChangeType'):<20} {entity.get('Type','?'):<18} {target}")

    # Dimensions are the field this programme has been burned by, so they are
    # printed rather than counted.
    #
    # DetailsDocument IS NOT ONE SHAPE, and assuming it was is how the first
    # version of this function crashed on the very file it was written for.
    # AddDimensions carries a LIST of dimensions directly; AddDeliveryOptions
    # carries a DICT with a DeliveryOptions key. Found by running it against the
    # real change set rather than by reading the API docs.
    for change in changes:
        dd = change.get("DetailsDocument")
        if isinstance(dd, list):
            dims = dd
        elif isinstance(dd, dict):
            dims = dd.get("Dimensions")
        else:
            dims = None
        if not dims:
            continue
        print(f"\ndimensions in {change.get('ChangeType')}: {len(dims)}")
        for d in dims:
            print(f"  {d.get('Key','?'):<32} {d.get('Types', d.get('Unit','?'))}")


def assert_account() -> None:
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        raise SystemExit(
            "ERROR: boto3 missing. This runs on the Mac (~/.rsvenv/bin/python) or "
            "in Actions.\n"
            "       A dry run needs neither: re-run without --apply.")
    try:
        got = boto3.client("sts").get_caller_identity()["Account"]
    except ClientError as exc:
        raise SystemExit(f"ERROR: STS: {exc.response['Error']['Code']}")
    if got != ACCOUNT:
        raise SystemExit(
            f"ERROR: credentials resolve to {got}, not {ACCOUNT}.\n"
            f"       {ACCOUNT} is the ONLY RelayShield account. Re-run with\n"
            "       AWS_PROFILE=relayshield. A WRITE against the wrong account\n"
            "       SUCCEEDS and creates a product nothing can see.")


MEDIA_KEY = re.compile(r"(Logo|Media|Image|Video|Thumbnail|Screenshot)Url$")


def media_urls(node, path=""):
    """Every URL AWS will try to FETCH, with the key path that named it.

    A change set carries plenty of URLs AWS never dereferences -- the base URL
    in usage instructions, support links, documentation. Only the media fields
    are fetched, and only those can fail preparation.
    """
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            here = f"{path}.{k}" if path else k
            if isinstance(v, str) and MEDIA_KEY.search(k) and v.startswith("http"):
                out.append((here, v))
            else:
                out.extend(media_urls(v, here))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out.extend(media_urls(v, f"{path}[{i}]"))
    elif isinstance(node, str) and path.endswith("Detail"):
        # Change details arrive as JSON-encoded strings in some exports.
        try:
            out.extend(media_urls(json.loads(node), path))
        except (json.JSONDecodeError, TypeError):
            pass
    return out


def probe_media(url: str, timeout: float = 15.0):
    """(verdict, detail). UNAMBIGUOUS failures only may block.

    403 and 404 both mean "AWS will not be able to fetch this": a public S3
    bucket with no ListBucket answers 403 for an object that does not exist
    rather than 404, so the two are one finding, not two. Everything else --
    a timeout, a refused connection, a 5xx, a blocked egress policy -- means
    THIS PROBE COULD NOT TELL, and a probe that cannot tell has no standing
    to stop the work.
    """
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, method="HEAD")
    req.add_header("User-Agent", "Mozilla/5.0 (RelayShield preflight)")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return "OK", f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404):
            return "MISSING", f"HTTP {exc.code}"
        return "UNKNOWN", f"HTTP {exc.code}"
    except Exception as exc:
        return "UNKNOWN", type(exc).__name__


def check_media(doc: dict, probe=probe_media) -> None:
    """Refuse a change set whose media AWS cannot fetch.

    WHY THIS EXISTS. On 2026-09-18 change set de0zvpnvpcq3olta3y7kpx4p2 was
    submitted, ran for fifteen seconds and came back FAILED:

        INVALID_MEDIA_LOCATION Media location not accessible:
        .../bundle_b/relayshield_logo_bundle_b.png

    The URL was produced by substituting bundle_a -> bundle_b in a path copied
    out of Bundle A's accepted change set. The SHAPE was right and the object
    had never been uploaded, so six guards on the document all passed. A field
    whose value is an EXTERNAL RESOURCE is not validated by validating the
    string, and the cheapest place to learn that is here rather than from AWS.
    """
    found = media_urls(doc)
    if not found:
        return
    print("\nmedia preflight:")
    bad = []
    for path, url in found:
        verdict, detail = probe(url)
        print(f"  {verdict:<8} {detail:<10} {path} = {url}")
        if verdict == "MISSING":
            bad.append((path, url, detail))
        elif verdict == "UNKNOWN":
            print("           ^ this probe could not tell. Not blocking; AWS may "
                  "still refuse it.")
    if bad:
        lines = "\n".join(f"    {p} = {u}  ({d})" for p, u, d in bad)
        raise SystemExit(
            "\nREFUSED: media AWS cannot fetch. Change set preparation would "
            "FAIL on\n         INVALID_MEDIA_LOCATION, which is what happened on "
            "2026-09-18.\n\n" + lines + "\n\n"
            "         A public S3 object that was never uploaded answers 403, not\n"
            "         404, so 403 here means absent rather than forbidden. Upload\n"
            "         the object, or point the field at one that already returns\n"
            "         200 -- Bundle A's logo is the RelayShield shield mark with no\n"
            "         bundle-specific text in it.\n")


def priced_dimensions(doc: dict) -> dict:
    """{dimension key: price} across every rate card in the change set."""
    out = {}
    for change in doc.get("ChangeSet", []):
        if change.get("ChangeType") != "UpdatePricingTerms":
            continue
        details = change.get("DetailsDocument") or {}
        for term in details.get("Terms", []):
            for card in term.get("RateCards", []):
                for row in card.get("RateCard", []):
                    key = row.get("DimensionKey")
                    if key:
                        out[key] = row.get("Price")
    return out


def check_pricing(doc: dict) -> None:
    """Refuse a change set that adds dimensions and prices none of them.

    WHY THIS EXISTS. Change set 17or75a96xofiu7gic33wjrm6 cleared the media
    preflight added hours earlier and then came back FAILED anyway:

        INVALID_INPUT When adding dimensions for SaaS products, you must also
        set pricing for usage dimensions.

    The document held five changes. Bundle A's accepted one holds thirteen: the
    offer, its pricing, legal, support and renewal terms, and the two releases.
    It was built by reusing Bundle A's envelope and I stopped reading at
    AddDimensions, so the half that prices the dimensions was simply absent.

    Every guard was on the document that existed. This one asks what a COMPLETE
    one looks like, which is the question none of them asked.
    """
    dims = []
    for change in doc.get("ChangeSet", []):
        if change.get("ChangeType") == "AddDimensions":
            dims += change.get("DetailsDocument") or []
    if not dims:
        return

    priced = priced_dimensions(doc)
    print("\npricing preflight:")
    for dim in dims:
        key = dim.get("Key")
        price = priced.get(key)
        mark = "OK      " if price is not None else "UNPRICED"
        print(f"  {mark} {key:<32} {price if price is not None else '-'}")

    unpriced = [d.get("Key") for d in dims if d.get("Key") not in priced]
    if unpriced:
        raise SystemExit(
            "\nREFUSED: these dimensions carry no price:\n"
            + "\n".join(f"    {k}" for k in unpriced)
            + "\n\n         AWS refuses the whole change set with\n"
              "         INVALID_INPUT ... you must also set pricing for usage\n"
              "         dimensions. A SaaS product is created by ONE change set\n"
              "         carrying the product AND its offer: CreateProduct,\n"
              "         UpdateInformation, UpdateTargeting, AddDeliveryOptions,\n"
              "         AddDimensions, ReleaseProduct, CreateOffer, the offer's\n"
              "         UpdateInformation, UpdatePricingTerms, UpdateLegalTerms,\n"
              "         UpdateSupportTerms, UpdateRenewalTerms, ReleaseOffer.\n"
              "         aws_marketplace/bundle_a_create_entity.json is the copy\n"
              "         AWS accepted; read all of it, not the first half.\n")

    orphans = [k for k in priced if k not in {d.get("Key") for d in dims}]
    if orphans:
        raise SystemExit(
            "\nREFUSED: priced dimensions that this change set never declares:\n"
            + "\n".join(f"    {k}" for k in orphans)
            + "\n\n         A rate card naming a key no dimension defines is a\n"
              "         price nothing can ever bill.\n")


# ---------------------------------------------------------------- field sizes
#
# THE FIFTH FAILED CHANGE SET, em3sw5gs00lifcmy42mxe95t9, 2026-09-19:
#
#     INVALID_INPUT Remove invalid key 'supply_chain_calls' with types
#     '[Metered, ExternallyMetered]'. Valid descriptions cannot exceed more
#     than 90 characters.
#
# Four of six dimension descriptions were over. The media preflight passed,
# the pricing preflight passed, eleven document guards passed, and AWS still
# refused it -- for the FIFTH time, each time on a different validation that
# none of our checks knew about.
#
# The pattern was fixing one constraint per round. What ends it is not another
# single-field check: it is asking, for EVERY field, whether this document is
# within the range the ACCEPTED example demonstrates. Bundle A's create set is
# the only change set AWS has taken from us, so it is the authority on what
# passes -- exactly as its ENVELOPE was the authority on which changes a SaaS
# create needs.
#
# Two mechanisms, deliberately different in force:
#
#   CEILINGS  a limit we have MEASURED. It blocks. Each entry names where the
#             number came from; a limit nobody can source does not go here.
#   reference every string, against the longest string AWS accepted in that
#             same field. Over-length prints OVER and does NOT block, because
#             "longer than one example" is not a known constraint and a probe
#             that cannot tell has no standing to stop finished work. It is
#             the line a reader checks before pressing apply.

CEILINGS = {
    "AddDimensions[].Description": (
        90, "AWS INVALID_INPUT on change set em3sw5gs00lifcmy42mxe95t9, "
            "2026-09-19: 'Valid descriptions cannot exceed more than 90 "
            "characters'"),
}

# THE REFERENCE IS CHOSEN BY SHAPE, NOT HARD-WIRED TO THE CREATE SET.
#
# The first version named bundle_a_create_entity.json and nothing else, so the
# TEST OFFER and the GO-PUBLIC change sets -- the two documents that follow the
# create -- were compared against nothing at all and printed no field table.
# That is exactly the gap that let four over-length descriptions through on the
# create set: the comparison existed and did not reach the document being sent.
#
# Bundle A has an accepted artefact for all three, so each one has an authority.
# Matching on the ChangeType sequence picks it without a mapping to maintain.
REFERENCES = [
    ROOT / "aws_marketplace" / "bundle_a_create_entity.json",
    ROOT / "aws_marketplace" / "bundle_a_test_offer.json",
    ROOT / "aws_marketplace" / "bundle_a_go_public.json",
]


def pick_reference(doc: dict):
    """The accepted Bundle A change set with the same ChangeType sequence."""
    mine = [c.get("ChangeType") for c in doc.get("ChangeSet", [])]
    for path in REFERENCES:
        if not path.exists():
            continue
        theirs = [c.get("ChangeType")
                  for c in json.loads(path.read_text()).get("ChangeSet", [])]
        if theirs == mine:
            return path
    return None


def field_classes(doc: dict) -> dict:
    """{class path: [strings]} for every string in the change set.

    A CLASS path collapses list indices, so the third dimension's Description
    and the fifth one's are the same field rather than two. Comparing by index
    against another product is meaningless -- it pairs 'Breach Exposure Check'
    with 'Supply Chain Exposure Check' and calls the difference a finding.
    """
    out = {}

    def walk(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for value in node:
                walk(value, f"{path}[]")
        elif isinstance(node, str):
            out.setdefault(path, []).append(node)

    for change in doc.get("ChangeSet", []):
        walk(change.get("DetailsDocument"), change.get("ChangeType", "?"))
    return out


ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def date_fields(doc: dict):
    """Yield (key path, value) for every ISO date under a key ending in Date.

    Narrow on purpose. `Version: "2022-07-14"` in the standard EULA term is a
    document version that happens to look like a date, and it is correct as it
    stands; widening this to every date-shaped string would refuse it.
    """
    out = []

    def walk(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}.{key}" if path else key)
        elif isinstance(node, list):
            for item in node:
                walk(item, f"{path}[]")
        elif isinstance(node, str):
            leaf = path.rsplit(".", 1)[-1].replace("[]", "")
            if leaf.endswith("Date") and ISO_DATE.match(node):
                out.append((path, node))

    walk(doc, "")
    return out


def check_dates(doc: dict, today=None) -> None:
    """Refuse a date in the past. Checked AFTER substitution, on what is sent.

    THIS EXISTS BECAUSE A DATE COPIED FROM AN ACCEPTED CHANGE SET IS CORRECT ON
    ONE DAY AND WRONG ON EVERY OTHER. bundle_a_test_offer.json carries
    ChargeDate 2026-08-08 and AvailabilityEndDate 2026-09-06, both right when
    they were submitted. Bundle B was built by reusing that envelope, the charge
    date was turned into a placeholder, and the availability date was not --
    half the fix, which is the shape of every Bundle B failure so far.

    A past date is unambiguous and therefore blocks: it cannot become valid by
    waiting, and nothing about the submission makes it right. That is the
    distinction from check_media, where a timeout means the probe could not tell
    and has no standing to stop finished work.
    """
    import datetime
    today = today or datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    found = date_fields(doc)
    if not found:
        print("dates         : none in this change set")
        return
    stale = []
    for path, value in found:
        verdict = "PAST" if value < today else "ok"
        print(f"date          : {verdict:4}  {value}  {path}")
        if verdict == "PAST":
            stale.append((path, value))
    if stale:
        # SystemExit, not Refused: this runs OUTSIDE main()'s try, exactly like
        # check_media and check_pricing. A Refused raised here escapes as a
        # traceback instead of a readable refusal.
        raise SystemExit(
            "\nREFUSED: date(s) in the past: "
            + ", ".join(f"{p} = {v}" for p, v in stale)
            + f" (today is {today}).\n"
            "       A payment schedule in the past is rejected, and an "
            "availability END date in the\n"
            "       past releases an offer that has already expired -- the buyer "
            "account is then told\n"
            "       to subscribe to something it cannot see. Make the field a "
            "__PLACEHOLDER__ and fill\n"
            "       it in substitute(), rather than committing a date that is "
            "correct for one day.")


# A FIELD WHOSE VALUES ARE A CLOSED SET IS NOT A LENGTH CONSTRAINT, and comparing
# one against an accepted example produces a warning nobody can act on: the
# withdraw change set's "Restricted" (10) reads as OVER against go-public's
# "Public" (6), on a value that is correct and has no other spelling. A check
# that cries wolf gets disabled, and then it is not a check at all -- so enum
# fields are compared for membership by AWS and by nothing here.
ENUM_CLASS_PATHS = {
    "UpdateVisibility.TargetVisibility",   # Public | Restricted | Limited
}


def check_field_limits(doc: dict, reference="auto") -> None:
    classes = field_classes(doc)

    over = []
    for path, (limit, source) in CEILINGS.items():
        for value in classes.get(path, []):
            if len(value) > limit:
                over.append((path, limit, len(value), value, source))
    if over:
        lines = ["\nREFUSED: field values over a limit AWS enforces:\n"]
        for path, limit, got, value, source in over:
            lines.append(f"    {path}  {got} > {limit}")
            lines.append(f"        {value[:72]}...")
            lines.append(f"        limit source: {source}")
        raise SystemExit("\n".join(lines) + "\n")

    if reference == "auto":
        reference = pick_reference(doc)
    if not reference or not Path(reference).exists():
        print("\nNo accepted Bundle A change set has this ChangeType sequence,")
        print("so there is nothing to compare field sizes against. That is a")
        print("finding about this document's shape, not a pass.")
        return
    ref = field_classes(json.loads(Path(reference).read_text()))

    print("\nfield sizes, against the change set AWS accepted "
          f"({Path(reference).name}):")
    longer = []
    for path, values in sorted(classes.items()):
        if path in ENUM_CLASS_PATHS:
            continue
        mine = max(len(v) for v in values)
        theirs = ref.get(path)
        if not theirs:
            continue
        accepted = max(len(v) for v in theirs)
        mark = "OVER" if mine > accepted else "    "
        if mine > accepted:
            longer.append((path, mine, accepted))
        print(f"  {mark} {mine:>5} / {accepted:>5} accepted   {path}")

    if longer:
        print("\n  NOT A REFUSAL, and read it before pressing apply: these "
              "fields are longer\n  than anything AWS has taken from us. No "
              "limit is known for them, so this\n  cannot say they are too "
              "long -- only that they are outside the range that\n  is proven "
              "to pass.")
        for path, mine, accepted in longer:
            print(f"    {path}  {mine} vs {accepted}")


def submit(doc: dict, changes: list, name: str) -> int:
    import boto3
    from botocore.exceptions import ClientError
    client = boto3.client("marketplace-catalog", region_name="us-east-1")
    try:
        resp = client.start_change_set(
            Catalog=doc["Catalog"], ChangeSet=changes, ChangeSetName=name)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("AccessDeniedException", "UnauthorizedException"):
            raise SystemExit(
                f"ERROR: {code} on StartChangeSet.\n"
                "       The catalog grant has never been applied. It is one command,\n"
                "       operator-side and once, because a role cannot widen its own\n"
                "       permissions:\n\n"
                "           sh tools/apply_marketplace_catalog_policy.sh\n")
        raise SystemExit(
            f"ERROR: {code}: {exc.response['Error'].get('Message','')[:400]}")

    print("\nSUBMITTED")
    print(f"  ChangeSetId  : {resp.get('ChangeSetId')}")
    print(f"  ChangeSetArn : {resp.get('ChangeSetArn')}")
    print("\nAWS reviews this asynchronously. Watch it with:")
    print(f"  AWS_PROFILE=relayshield aws marketplace-catalog describe-change-set \\")
    print(f"    --catalog {CATALOG} --change-set-id {resp.get('ChangeSetId')} --no-cli-pager")
    print("\nWHEN IT SUCCEEDS it returns the new ENTITY ID (prod-...). Read it, and")
    print("the product code, with:")
    print(f"  python3 tools/marketplace_read_product.py --change-set-id {resp.get('ChangeSetId')}")
    print("\nTHE ENTITY ID IS NOT THE PRODUCT CODE. This line used to say it was, and")
    print("that was wrong. The entity id is the Catalog API identifier and is what the")
    print("test-offer and go-public change sets take as --product-id. The PRODUCT CODE")
    print("is what ResolveCustomer returns and what GetEntitlements and BatchMeterUsage")
    print("take, and it is the value BUNDLE_B_PRODUCT_CODE needs. Setting the entity id")
    print("there would match no key row, raise nothing, and report success.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("changeset", help="path to the committed change set JSON")
    ap.add_argument("--apply", action="store_true",
                    help="actually call StartChangeSet. Requires --confirm.")
    ap.add_argument("--confirm", default="",
                    help=f"type {CONFIRM_TOKEN} to confirm an --apply")
    ap.add_argument("--product-id", default="",
                    help="the entity id AWS returned from CreateProduct, "
                         "substituted for __BUNDLE_B_PRODUCT_ID__ in an offer file")
    ap.add_argument("--name", default="",
                    help="ChangeSetName. Defaults to the file's stem.")
    args = ap.parse_args()

    path = Path(args.changeset)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        raise SystemExit(f"ERROR: {path} does not exist.")

    doc = json.loads(path.read_text())
    # relative_to RAISES on a path outside the repo, and the first version used
    # it bare -- so pointing this at a file in /tmp crashed with a pathlib
    # traceback instead of reading the file. Found by running it.
    try:
        shown = path.relative_to(ROOT)
    except ValueError:
        shown = path
    print(f"file          : {shown}")
    args.product_id = clean_product_id(args.product_id)
    doc = substitute(doc, args.product_id)
    try:
        changes = validate(doc)
    except Refused as exc:
        raise SystemExit(f"REFUSED: {exc}")

    print(f"catalog       : {doc['Catalog']}")
    summarise(changes)

    # BEFORE the dry-run return, deliberately: a dry run that skips the one
    # check AWS would have failed on is checking a different document from the
    # one that ships, which is the family of defect this repo keeps paying for.
    check_media(doc)
    check_pricing(doc)
    check_field_limits(doc)
    check_dates(doc)

    if not args.apply:
        print("\nDRY RUN. Nothing was sent. Add --apply --confirm "
              f"{CONFIRM_TOKEN} to submit.")
        return 0

    if args.confirm != CONFIRM_TOKEN:
        raise SystemExit(
            f"\nREFUSED: --apply needs --confirm {CONFIRM_TOKEN} typed by hand.\n"
            "         This creates a real product in a real marketplace account.")

    assert_account()
    return submit(doc, changes, args.name or path.stem)


if __name__ == "__main__":
    raise SystemExit(main())
