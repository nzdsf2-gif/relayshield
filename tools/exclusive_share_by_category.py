#!/usr/bin/env python3
"""measured_exclusive_share, broken out per indicator category.

`tools/export_intel_sample.py` already computes one corpus-wide
`measured_exclusive_share`. That single figure is the right KPI but the wrong
granularity for a competitive benchmark: a corpus that is 95% exclusive on
tg_handle and 3% exclusive on domain has two completely different stories in it,
and quoting the blend hides both.

This reuses the exporter's own classification -- same FEED_CHANNELS, same
FEED_CATEGORY, same collapse-to-distinct-indicator -- so the per-category
numbers reconcile exactly with the corpus-wide one rather than being a second,
subtly different measurement.

Runs against DynamoDB (needs AWS, so it runs on the Mac with
AWS_PROFILE=relayshield) or against a JSONL fixture for offline work:

    AWS_PROFILE=relayshield python3 tools/exclusive_share_by_category.py
    python3 tools/exclusive_share_by_category.py --fixture sample.jsonl --markdown

Emits JSON on stdout, and with --markdown a table ready to paste into the
benchmark. Every row carries its denominator, because a 100% exclusive share
over 12 indicators is not a claim worth making in front of a competitor's
customer and the reader must be able to see that without asking.
"""

import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from export_intel_sample import (  # noqa: E402
    EXCLUDED_TYPES,
    _load_fixture,
    _scan_live,
    collapse,
)

IOCS_TABLE = "relayshield_intel_iocs"

# Below this, a share is reported but flagged: the point estimate is too noisy
# to put in front of a buyer on its own. Chosen to be stated, not hidden -- the
# failure mode this guards against is quoting "100% exclusive" off a handful of
# rows, which is exactly how the Segment 1 outreach nearly went out.
MIN_DEFENSIBLE_N = 100


def per_category(records):
    """{ioc_type: {collected, also_in_feed, exclusive, exclusive_share}}."""
    stats = defaultdict(lambda: {"collected": 0, "also_in_feed": 0})
    for rec in records:
        if rec["ioc_type"] in EXCLUDED_TYPES:
            continue
        if not rec["from_channel"]:
            continue  # feed-only rows are not ours to count in either direction
        row = stats[rec["ioc_type"]]
        row["collected"] += 1
        if rec["from_feed"]:
            row["also_in_feed"] += 1

    out = {}
    for ioc_type, row in stats.items():
        collected = row["collected"]
        exclusive = collected - row["also_in_feed"]
        out[ioc_type] = {
            "collected": collected,
            "also_in_feed": row["also_in_feed"],
            "exclusive": exclusive,
            "exclusive_share": round(exclusive / collected, 6) if collected else 0.0,
            "defensible": collected >= MIN_DEFENSIBLE_N,
        }
    return dict(sorted(out.items(), key=lambda kv: kv[1]["exclusive"], reverse=True))


def to_markdown(stats, totals):
    lines = [
        "| Category | Collected (distinct) | Also in an ingested feed | Exclusive | Exclusive share |",
        "|---|---:|---:|---:|---:|",
    ]
    for ioc_type, row in stats.items():
        share = f"{row['exclusive_share']:.1%}"
        if not row["defensible"]:
            share += f" ⚠️ n={row['collected']}"
        lines.append(
            f"| `{ioc_type}` | {row['collected']:,} | {row['also_in_feed']:,} "
            f"| {row['exclusive']:,} | {share} |"
        )
    lines.append(
        f"| **All categories** | **{totals['collected']:,}** | **{totals['also_in_feed']:,}** "
        f"| **{totals['exclusive']:,}** | **{totals['exclusive_share']:.1%}** |"
    )
    lines.append("")
    lines.append(
        f"⚠️ marks a category with fewer than {MIN_DEFENSIBLE_N} collected indicators, "
        "where the share is too noisy to quote on its own."
    )
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", default=IOCS_TABLE)
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--fixture", help="JSONL of raw IOC rows, instead of scanning DynamoDB")
    ap.add_argument("--markdown", action="store_true", help="also print a paste-ready table")
    args = ap.parse_args()

    items = _load_fixture(args.fixture) if args.fixture else _scan_live(args.table, args.region)
    records = collapse(items)
    stats = per_category(records)

    collected = sum(r["collected"] for r in stats.values())
    also = sum(r["also_in_feed"] for r in stats.values())
    totals = {
        "collected": collected,
        "also_in_feed": also,
        "exclusive": collected - also,
        "exclusive_share": round((collected - also) / collected, 6) if collected else 0.0,
    }

    json.dump({"per_category": stats, "totals": totals,
               "min_defensible_n": MIN_DEFENSIBLE_N,
               "excluded_types": sorted(EXCLUDED_TYPES)},
              sys.stdout, indent=2, sort_keys=True)
    print()

    if args.markdown:
        print("\n" + to_markdown(stats, totals), file=sys.stderr)


if __name__ == "__main__":
    main()
