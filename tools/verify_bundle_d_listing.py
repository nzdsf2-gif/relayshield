#!/usr/bin/env python3
"""Compare the LIVE Bundle D listing with what this repo says it should say, field by field. READ ONLY.

    python3 tools/verify_bundle_d_listing.py                       # reads prod-kkvurtspreofy and its offer
    python3 tools/verify_bundle_d_listing.py --stage endpoint      # exit code judges only that stage
    python3 tools/verify_bundle_d_listing.py --from-file product.json --offer-file offer.json

WHY THIS EXISTS. Changes to this listing go through the Management Portal, whose forms compose the
change set, and a human pastes text into them. On 2026-10-26 the wrong file was pasted into a field and
every file ended in a newline the form rejects. Neither was visible from here. This tool is how a
session finds out what ACTUALLY went live, instead of reporting what was meant to. It compares byte
for byte, and on a mismatch says where the first difference is and whether it is only whitespace.

STAGES, in the order the changes are submitted (one open change per product at a time):
  endpoint      MCP endpoint URL, both usage-instruction fields, authorization, fulfillment URL
  copy          short and long description, highlights, search keywords
  architecture  hosting architecture declared for both planes, and a diagram URL
  prices        the offer's rate card: BEFORE (Stripe-direct prices), AFTER (AWS edition) or MIXED
`--stage all` (the default) prints every stage and exits non-zero if ANY differs; a named stage
exits non-zero only for that stage, so "endpoint passes" can be asserted before the copy exists.
"""
import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AWS = ROOT / "aws_marketplace"
PRODUCT_ID = "prod-kkvurtspreofy"
CATALOG = "AWSMarketplace"
STAGES = ("endpoint", "copy", "architecture", "prices")

MCP_URL = "https://api.relayshield.net/mcp"
FULFILLMENT_URL = "https://api.relayshield.net/marketplace/bundle-fulfillment"


def read(name: str) -> str:
    return (AWS / name).read_bytes().decode("utf-8")


def where_different(want: str, got: str) -> str:
    if want == got:
        return "identical"
    n = next((i for i, (a, b) in enumerate(zip(want, got)) if a != b), min(len(want), len(got)))
    note = []
    if want.strip() == got.strip():
        note.append("differs ONLY in leading/trailing whitespace")
    elif want.replace("\r\n", "\n") == got.replace("\r\n", "\n"):
        note.append("differs ONLY in line endings")
    return (f"first difference at character {n}; want {len(want)} chars, live {len(got)} chars; "
            f"want ...{want[max(0, n - 20):n + 25]!r} live ...{got[max(0, n - 20):n + 25]!r}"
            + (f" ({'; '.join(note)})" if note else ""))


def delivery_option(product: dict) -> dict:
    versions = product.get("Versions") or []
    opts = (versions[0].get("DeliveryOptions") if versions else None) or []
    return opts[0] if opts else {}


def live_prices(offer: dict) -> dict:
    out = {}
    for t in offer.get("Terms", []):
        if t.get("Type") in ("UsageBasedPricingTerm", "ConfigurableUpfrontPricingTerm"):
            for card in t.get("RateCards", []):
                for row in card.get("RateCard", []):
                    out[row["DimensionKey"]] = Decimal(row["Price"])
    return out


def check(label: str, ok: bool, detail: str = "") -> dict:
    return {"label": label, "ok": bool(ok), "detail": detail}


def stage_endpoint(product: dict) -> list:
    opt = delivery_option(product)
    eps = opt.get("Endpoints") or []
    ep = eps[0] if eps else {}
    proto = (ep.get("IntegrationProtocols") or [{}])[0]
    mcp_want, api_want = read("bundle_d_mcp_usage_instructions.md"), read("bundle_d_api_usage_instructions.md")
    return [
        check("ApiType is MCP_SERVER", opt.get("ApiType") == "MCP_SERVER", f"live {opt.get('ApiType')!r}"),
        check("exactly one endpoint", len(eps) == 1, f"live has {len(eps)}"),
        check(f"endpoint URL is {MCP_URL}", ep.get("EndpointUrl") == MCP_URL, f"live {ep.get('EndpointUrl')!r}"),
        check("authorization is API_KEY only", ep.get("AuthorizationTypes") == ["API_KEY"], f"live {ep.get('AuthorizationTypes')!r}"),
        check("MCP usage instructions match bundle_d_mcp_usage_instructions.md",
              proto.get("UsageInstructions") == mcp_want, where_different(mcp_want, proto.get("UsageInstructions") or "")),
        check("API usage instructions match bundle_d_api_usage_instructions.md",
              opt.get("UsageInstructions") == api_want, where_different(api_want, opt.get("UsageInstructions") or "")),
        check("fulfillment URL unchanged", opt.get("FulfillmentUrl") == FULFILLMENT_URL, f"live {opt.get('FulfillmentUrl')!r}"),
        check("product still Public", product.get("Description", {}).get("Visibility") == "Public",
              f"live {product.get('Description', {}).get('Visibility')!r}"),
    ]


def stage_copy(product: dict) -> list:
    d = product.get("Description", {})
    want = json.loads(read("bundle_d_listing_copy.json"))
    out = []
    for key in ("ShortDescription", "LongDescription"):
        out.append(check(f"{key} matches bundle_d_listing_copy.json", d.get(key) == want[key],
                         where_different(want[key], d.get(key) or "")))
    for key in ("Highlights", "SearchKeywords"):
        out.append(check(f"{key} match bundle_d_listing_copy.json", d.get(key) == want[key],
                         f"live {d.get(key)!r}" if d.get(key) != want[key] else ""))
    return out


def stage_architecture(product: dict) -> list:
    h = delivery_option(product).get("HostingArchitecture") or {}
    plats = {p.get("Component"): p for p in h.get("Platforms", [])}
    out = []
    for comp in ("CONTROL_PLANE", "APPLICATION_PLANE"):
        p = plats.get(comp, {})
        out.append(check(f"{comp} provider is declared (not UNSPECIFIED)",
                         p.get("Provider") not in (None, "", "UNSPECIFIED"),
                         f"live Provider={p.get('Provider')!r} EnvironmentOwner={p.get('EnvironmentOwner')!r}"))
    out.append(check("an architecture diagram URL is set", bool(h.get("ArchitectureDiagramUrl")),
                     f"live {h.get('ArchitectureDiagramUrl')!r}"))
    return out


def stage_prices(offer: dict) -> list:
    spec = json.loads(read("bundle_d_aws_prices.json"))
    have = live_prices(offer)
    ref, aws = {}, {}
    for group in ("monthly", "per_call"):
        for dim, v in spec[group].items():
            ref[dim], aws[dim] = Decimal(v["reference"]), Decimal(v["aws"])
    if have == aws:
        state, ok = "AFTER (the AWS-edition prices are live)", True
    elif have == ref:
        state, ok = "BEFORE (still the Stripe-direct prices)", False
    else:
        state, ok = "MIXED (some prices moved and some did not)", False
    detail = "; ".join(f"{d}: live {have.get(d)} / aws {aws[d]}" for d in aws if have.get(d) != aws[d])
    return [check(f"offer rate card is {state}", ok, detail)]


def run(product: dict, offer: dict, stage: str):
    stages = {"endpoint": lambda: stage_endpoint(product), "copy": lambda: stage_copy(product),
              "architecture": lambda: stage_architecture(product), "prices": lambda: stage_prices(offer)}
    results = {name: stages[name]() for name in STAGES}
    chosen = STAGES if stage == "all" else (stage,)
    ok = all(c["ok"] for name in chosen for c in results[name])
    return results, ok


def describe(client, entity_id: str) -> dict:
    resp = client.describe_entity(Catalog=CATALOG, EntityId=entity_id)
    doc = resp["DetailsDocument"]
    return doc if isinstance(doc, dict) else json.loads(doc)


def main(argv=None, client=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("all",) + STAGES, default="all")
    ap.add_argument("--from-file", default="")
    ap.add_argument("--offer-file", default="")
    args = ap.parse_args(argv)
    if args.from_file:
        product = json.loads(Path(args.from_file).read_text())
        offer = json.loads(Path(args.offer_file).read_text()) if args.offer_file else {}
    else:
        if client is None:
            import boto3
            client = boto3.client("marketplace-catalog", region_name="us-east-1")
        product = describe(client, PRODUCT_ID)
        offer = describe(client, json.loads(read("bundle_d_aws_prices.json"))["offer_id"])

    results, ok = run(product, offer, args.stage)
    for name in STAGES:
        print(f"\n== {name}" + ("   <- judged" if args.stage in ("all", name) else ""))
        for c in results[name]:
            print(f"   {'PASS   ' if c['ok'] else 'DIFFERS'}  {c['label']}")
            if not c["ok"] and c["detail"]:
                print(f"            {c['detail']}")
    print("\n" + ("ALL JUDGED CHECKS PASS." if ok else "AT LEAST ONE JUDGED CHECK DIFFERS."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
