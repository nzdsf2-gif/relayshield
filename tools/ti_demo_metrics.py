#!/usr/bin/env python3
"""Re-measure the four stat cards on the TI demo, with the right UNITS.

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/ti_demo_metrics.py

Read-only. Needs AWS, so it runs on the Mac and never in the build container.

WHY THIS EXISTS, AND IT IS NOT STALENESS. cloudflare_worker_ti_demo.js shows
"5.4M+ / IOC indicators", captured 2026-08-12 from the row count of
relayshield_intel_iocs. That table is keyed (ioc_value, seen_ts) -- a value seen
on five days is five rows -- and export_intel_sample.py's own `collapse()` says
so in its docstring: "Counting rows would inflate every number we quote."

So the card is not a stale indicator count. It is a SIGHTINGS count wearing an
indicators label, and the two differ by roughly an order of magnitude: the
2026-09-03 measurement recorded 494K distinct against 5.8M sightings. A prospect
who checks is the audience MEASUREMENT DOCTRINE was written about, and this is
the most checkable number on the page.

It prints BOTH replacement copies, because which one ships is a decision and not
a measurement:

  A. SOURCES, NOT COUNTS -- recommended, and what the AWS listing already does.
     True today, true in June, needs no re-measurement, and cannot go stale in
     front of somebody.
  B. CORRECTED COUNTS with honest labels, if the demo must show numbers. Every
     card then carries a date, because a number with no date is a claim with no
     expiry.

The distinct count is a FULL SCAN of a multi-million-row table. That is minutes
and a real read bill, so it is opt-in: --distinct. Without it the tool reports
sightings and says plainly that it has not measured indicators, rather than
printing the row count under an indicators heading -- which is the defect.
"""

import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

IOCS_TABLE = "relayshield_intel_iocs"
FAMILIES_TABLE = "relayshield_malpedia_families"
CHANNELS_TABLE = "relayshield_intel_channels"
MITRE_TABLE = "relayshield_mitre_attack"

REQUIRED_ACCOUNT = "239677749008"


def _guard_account(region):
    """620534471984 is the pre-audit account and is the shell default.

    A read there returns ResourceNotFoundException, which looks like a missing
    table and is not -- so the check is worth one call rather than a wrong
    conclusion about the corpus.
    """
    import boto3

    who = boto3.client("sts", region_name=region).get_caller_identity()
    if who["Account"] != REQUIRED_ACCOUNT:
        raise SystemExit(
            f"Refusing to run: credentials resolve to account {who['Account']}, "
            f"not {REQUIRED_ACCOUNT}. Prefix the command with "
            f"AWS_PROFILE=relayshield.")


def _table_item_count(table_name, region):
    """Row count from DescribeTable. One call, instant, free.

    THE FIRST VERSION OF THIS TOOL SCANNED, AND IT HUNG. `Select="COUNT"` still
    reads every page of a 5.5-million-row table, so the run printed its header
    and then sat in a pagination loop for minutes with nothing on screen and a
    real read bill accruing -- which is EXACTLY the defect CLAUDE.md records
    about miniapp_funnel.py and `filter_log_events`, rebuilt by me in a new
    file four days later. A lesson recorded in one file is not a lesson the
    next file learns, for the third time.

    DescribeTable's ItemCount is APPROXIMATE and refreshed roughly every six
    hours, and that is fine for a headline that is about to be rewritten as
    prose anyway. It is never fine for a number quoted to the row, which is
    another reason Option A is the recommendation.
    """
    import boto3
    from botocore.exceptions import ClientError

    try:
        d = boto3.client("dynamodb", region_name=region).describe_table(
            TableName=table_name)
        return d["Table"].get("ItemCount")
    except ClientError as exc:
        print(f"  ! {table_name}: {exc.response['Error']['Code']}",
              file=sys.stderr)
        return None


def _count(table_name, region, filt=None):
    """Filtered row count by scan. Returns None if the table is unreadable.

    None rather than 0, deliberately and for the same reason the watchlist
    monitor does it: "we could not read this" and "this is empty" are different
    findings, and rendering the first as the second is how a false number gets
    onto a page.

    Only used for the SMALL tables -- channels and MITRE -- where a filter is
    needed and the row count is in the hundreds. It prints a page counter to
    stderr regardless, because a tool that goes quiet is indistinguishable from
    a tool that has hung, and this file has already made that mistake once.
    """
    import boto3
    from botocore.exceptions import ClientError

    table = boto3.resource("dynamodb", region_name=region).Table(table_name)
    total, pages, kwargs = 0, 0, {"Select": "COUNT"}
    if filt:
        kwargs.update(filt)
    try:
        while True:
            page = table.scan(**kwargs)
            total += page.get("Count", 0)
            pages += 1
            key = page.get("LastEvaluatedKey")
            print(f"    {table_name}: page {pages}, {total} matched so far",
                  file=sys.stderr)
            if not key:
                return total
            kwargs["ExclusiveStartKey"] = key
    except ClientError as exc:
        print(f"  ! {table_name}: {exc.response['Error']['Code']}",
              file=sys.stderr)
        return None


def _distinct_indicators(region, approx_rows=None):
    """Distinct indicators, by full scan and collapse. SLOW AND NOT FREE.

    Reuses export_intel_sample.py's own `collapse()` so this number reconciles
    exactly with measured_exclusive_share rather than being a second, subtly
    different measurement.

    It says what it is about to cost BEFORE it starts. A long-running read that
    announces nothing is the hang this file was rewritten to stop.
    """
    from export_intel_sample import EXCLUDED_TYPES, _scan_live, collapse

    est = ""
    if approx_rows:
        est = f" about {approx_rows:,} rows,"
    print(f"  FULL SCAN of {IOCS_TABLE}:{est} several minutes and a real read\n"
          f"  bill. Ctrl-C now if that was not intended.\n", file=sys.stderr)
    items = _scan_live(IOCS_TABLE, region)
    print(f"  scanned {len(items):,} rows, collapsing to distinct indicators...",
          file=sys.stderr)
    records = collapse(items)
    return sum(1 for r in records if r["ioc_type"] not in EXCLUDED_TYPES)


def _fmt(n):
    return "unreadable" if n is None else f"{n:,}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--distinct", action="store_true",
                    help="also collapse to distinct indicators (full scan, "
                         "minutes, real read cost)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    _guard_account(args.region)

    print("Re-measuring the TI demo's stat cards\n", file=sys.stderr)
    sightings = _table_item_count(IOCS_TABLE, args.region)
    families = _table_item_count(FAMILIES_TABLE, args.region)
    channels = _count(CHANNELS_TABLE, args.region, {
        "FilterExpression": "active = :t",
        "ExpressionAttributeValues": {":t": True},
    })
    mitre = _count(MITRE_TABLE, args.region, {
        "FilterExpression": "sk = :i",
        "ExpressionAttributeValues": {":i": "info"},
    })
    distinct = _distinct_indicators(args.region, sightings) if args.distinct else None

    today = date.today().isoformat()
    out = {
        "measured_on": today,
        "sightings_rows_in_intel_iocs": sightings,
        "distinct_indicators": distinct,
        "malware_families": families,
        "active_channels": channels,
        "mitre_groups": mitre,
    }
    if args.json:
        print(json.dumps(out, indent=2))
        return

    print(f"  rows in {IOCS_TABLE:<28} {_fmt(sightings)}   <- SIGHTINGS")
    print(f"  distinct indicators                  "
          f"{_fmt(distinct) if args.distinct else 'NOT MEASURED (pass --distinct)'}")
    print(f"  malware families                     {_fmt(families)}")
    print(f"  active criminal Telegram channels    {_fmt(channels)}")
    print(f"  MITRE ATT&CK groups                  {_fmt(mitre)}")

    print("\n  THE ROW COUNT IS NOT AN INDICATOR COUNT. relayshield_intel_iocs")
    print("  is keyed (ioc_value, seen_ts), so one value seen on five days is")
    print("  five rows. The live card labels this number 'IOC indicators'.")

    print("\n" + "=" * 68)
    print("OPTION A -- sources, not counts. RECOMMENDED.")
    print("=" * 68)
    print("""
  Hero:
    Query indicators collected continuously from monitored criminal Telegram
    marketplaces, infostealer log dumps and public indicator feeds, alongside
    MITRE ATT&CK profiles, trending threats and identity risk scoring.

  Cards (capabilities, which change by a deliberate act with a commit behind
  them, rather than counts that are wrong again next month):
    Criminal Telegram marketplaces   monitored continuously
    Infostealer log dumps            parsed on arrival
    MITRE ATT&CK                     actor profiles and techniques
    Identity risk scoring            live, per domain and per address
""")

    print("=" * 68)
    print("OPTION B -- corrected counts. Every card carries the date.")
    print("=" * 68)
    if not args.distinct:
        print("\n  Re-run with --distinct first: option B needs the indicator")
        print("  count, and the whole point is not to print a sightings number")
        print("  under an indicators label a second time.\n")
        return
    print(f"""
    {_fmt(distinct)}    distinct indicators (measured {today})
    {_fmt(sightings)}  sightings across them
    {_fmt(families)}     malware families
    {_fmt(channels)}         active criminal Telegram channels
    {_fmt(mitre)}        MITRE ATT&CK groups
""")


if __name__ == "__main__":
    main()
