#!/usr/bin/env python3
"""Change the PRICES on Bundle D's public AWS offer, and nothing else.

    python3 tools/marketplace_update_offer_prices.py                       # dry run, reads the live offer
    python3 tools/marketplace_update_offer_prices.py --from-file F.json    # dry run against a saved read
    python3 tools/marketplace_update_offer_prices.py --apply --confirm UPDATE-LIVE-PRICES

WHY A DEDICATED TOOL. A change set does not edit a rate card, it REPLACES it with whatever it
is handed, and an empty or half-empty card is a valid document. That rolled Bundle D's prices
back to placeholders on 2026-07-27. So this tool never types a price into a template. It reads
the live offer, copies its two pricing terms verbatim, changes only the numbers named in
aws_marketplace/bundle_d_aws_prices.json, and sends ONE change (UpdatePricingTerms). The legal,
support, renewal and targeting terms are not in the change set at all.

WHAT IT REFUSES, each proven by test_bundle_d_aws_prices.py putting the defect back:
  * a live offer whose dimensions differ from the spec (a missing dimension is the rollback);
  * a live price that is not the spec's reference price (the spec is stale, or someone changed
    the card, and applying would overwrite their change);
  * a new price outside the 5-10 percent band below its Stripe-direct reference;
  * an offer id other than the one in the spec, or a non-Released offer;
  * --apply without --confirm UPDATE-LIVE-PRICES, and --apply against the wrong AWS account.

DEFAULT IS A DRY RUN. It prints the table of old and new prices and the exact document it would
send. Runs on the Mac (AWS_PROFILE=relayshield) or in Actions (.github/workflows/
marketplace_offer_prices.yml, which gives the choice as a dropdown rather than a typed phrase).
"""
import argparse
import copy
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "aws_marketplace" / "bundle_d_aws_prices.json"
ACCOUNT = "239677749008"
CATALOG = "AWSMarketplace"
CONFIRM = "UPDATE-LIVE-PRICES"


class Refused(Exception):
    pass


def load_spec(path=SPEC_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def spec_prices(spec: dict) -> dict:
    """{dimension: (reference, aws)} as Decimals, usage and monthly together."""
    out = {}
    for group in ("monthly", "per_call"):
        for dim, v in spec[group].items():
            out[dim] = (Decimal(v["reference"]), Decimal(v["aws"]))
    return out


def check_spec(spec: dict) -> None:
    """The band. Pure arithmetic on the spec, so it needs no AWS and no live read."""
    lo, hi = (Decimal(x) for x in spec["discount_band_percent"])
    for dim, (ref, new) in spec_prices(spec).items():
        if ref <= 0:
            raise Refused(f"{dim}: reference price {ref} is not positive.")
        off = (ref - new) / ref * 100
        if not (lo <= off <= hi):
            raise Refused(
                f"{dim}: {new} is {off:.2f} percent below the reference {ref}; "
                f"the band is {lo} to {hi} percent. (Andrew's rule, 2026-10-25.)")


def _terms(doc: dict) -> dict:
    out = {}
    for t in doc.get("Terms", []):
        out.setdefault(t.get("Type"), []).append(t)
    return out


def live_prices(doc: dict) -> dict:
    """{dimension: Decimal} for every dimension the live offer prices."""
    out = {}
    for ttype in ("UsageBasedPricingTerm", "ConfigurableUpfrontPricingTerm"):
        for t in _terms(doc).get(ttype, []):
            for card in t.get("RateCards", []):
                for row in card.get("RateCard", []):
                    out[row["DimensionKey"]] = Decimal(row["Price"])
    return out


def check_live(doc: dict, spec: dict) -> None:
    if doc.get("Id") != spec["offer_id"]:
        raise Refused(f"live offer is {doc.get('Id')!r}, the spec is for {spec['offer_id']!r}.")
    if doc.get("ProductId") != spec["product_id"]:
        raise Refused(f"offer belongs to {doc.get('ProductId')!r}, the spec expects {spec['product_id']!r}.")
    if doc.get("State") != "Released":
        raise Refused(f"offer state is {doc.get('State')!r}, not Released.")
    want = spec_prices(spec)
    have = live_prices(doc)
    if set(have) != set(want):
        raise Refused(
            "the live rate card and the spec disagree about WHICH dimensions exist.\n"
            f"   only live: {sorted(set(have) - set(want))}\n"
            f"   only spec: {sorted(set(want) - set(have))}\n"
            "A change set replaces the whole card; sending this would drop or invent a dimension.")
    stale = {d: (have[d], want[d][0]) for d in want if have[d] != want[d][0]}
    if stale:
        lines = "\n".join(f"   {d}: live {a}, spec reference {b}" for d, (a, b) in sorted(stale.items()))
        raise Refused(
            "the live prices are not the prices the spec was written against:\n" + lines +
            "\nSomeone has changed the card, or the spec is stale. Re-read the offer and decide; "
            "applying now would overwrite that change.")
    ups = _terms(doc).get("ConfigurableUpfrontPricingTerm", [])
    use = _terms(doc).get("UsageBasedPricingTerm", [])
    if len(ups) != 1 or len(use) != 1:
        raise Refused("expected exactly one usage term and one upfront term on the live offer.")


def _fmt(old: str, new: Decimal) -> str:
    """Keep the live card's own number style: 3 decimals for usage, whole dollars for the upfront price."""
    if "." in old:
        return f"{new:.{len(old.split('.')[1])}f}"
    if new != new.to_integral_value():
        raise Refused(f"the live price {old!r} is whole dollars but the new price {new} is not.")
    return str(int(new))


def build_change_set(doc: dict, spec: dict) -> dict:
    check_spec(spec)
    check_live(doc, spec)
    want = spec_prices(spec)
    terms = []
    for ttype in ("UsageBasedPricingTerm", "ConfigurableUpfrontPricingTerm"):
        term = copy.deepcopy(_terms(doc)[ttype][0])
        for card in term["RateCards"]:
            for row in card["RateCard"]:
                row["Price"] = _fmt(row["Price"], want[row["DimensionKey"]][1])
        terms.append(term)
    return {
        "Catalog": CATALOG,
        "ChangeSetName": "bundle_d_aws_edition_prices",
        "ChangeSet": [{
            "ChangeType": "UpdatePricingTerms",
            "Entity": {"Type": "Offer@1.0", "Identifier": spec["offer_id"]},
            # "Contract" is the model on the accepted Bundle B pricing change
            # (aws_marketplace/bundle_b_create_entity.json); this offer has the same two terms.
            "DetailsDocument": {"PricingModel": "Contract", "Terms": terms},
        }],
    }


def summary(doc: dict, spec: dict) -> str:
    have = live_prices(doc)
    rows = ["  dimension                    live      new       off"]
    for dim, (ref, new) in spec_prices(spec).items():
        rows.append(f"  {dim:<27} {have[dim]:>8}  {new:>8}  {(ref - new) / ref * 100:>5.1f}%")
    return "\n".join(rows)


def fetch_live(spec: dict) -> dict:
    try:
        import boto3
    except ImportError:
        raise SystemExit("boto3 is missing. Run on the Mac with ~/.rsvenv/bin/python, in Actions, or use --from-file.")
    client = boto3.client("marketplace-catalog", region_name="us-east-1")
    resp = client.describe_entity(Catalog=CATALOG, EntityId=spec["offer_id"])
    return resp["DetailsDocument"] if isinstance(resp["DetailsDocument"], dict) else json.loads(resp["DetailsDocument"])


def assert_account(client_factory=None) -> None:
    if client_factory is None:
        import boto3
        client_factory = lambda: boto3.client("sts")  # noqa: E731
    got = client_factory().get_caller_identity()["Account"]
    if got != ACCOUNT:
        raise SystemExit(
            f"REFUSED: credentials resolve to {got}, not {ACCOUNT}. Re-run with AWS_PROFILE=relayshield.\n"
            "A write against the wrong account succeeds and changes nothing anyone can see.")


def main(argv=None, client=None, sts=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-file", default="")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm", default="")
    ap.add_argument("--spec", default=str(SPEC_PATH))
    args = ap.parse_args(argv)

    spec = load_spec(args.spec)
    if args.apply and args.confirm != CONFIRM:
        print(f"REFUSED: --apply needs --confirm {CONFIRM}. This changes live prices.", file=sys.stderr)
        return 2
    try:
        doc = json.loads(Path(args.from_file).read_text()) if args.from_file else fetch_live(spec)
        change_set = build_change_set(doc, spec)
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    print(f"offer {spec['offer_id']} on product {spec['product_id']}  (state {doc['State']})\n")
    print(summary(doc, spec))
    print("\nThe change set that would be sent (ONE change; legal, support, renewal and targeting terms untouched):\n")
    print(json.dumps(change_set, indent=2))
    if not args.apply:
        print("\nDRY RUN. Nothing was sent.")
        return 0

    assert_account(sts)
    if client is None:
        import boto3
        client = boto3.client("marketplace-catalog", region_name="us-east-1")
    resp = client.start_change_set(Catalog=CATALOG, ChangeSet=change_set["ChangeSet"],
                                   ChangeSetName=change_set["ChangeSetName"])
    print(f"\nSUBMITTED. ChangeSetId {resp.get('ChangeSetId')}")
    print("AWS reviews it asynchronously. Read the result with the 'Read a Marketplace product' workflow.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
