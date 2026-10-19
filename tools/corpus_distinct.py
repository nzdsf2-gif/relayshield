#!/usr/bin/env python3
"""Cumulative distinct-indicator count for the corpus, measured now.

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/corpus_distinct.py

Read-only. It runs the SAME function the weekly metrics Lambda runs
(relayshield_weekly_metrics._measure_corpus), so the number printed here is the
number the Monday email will print once that function has the time to finish.

WHY THIS EXISTS INSTEAD OF `ti_demo_metrics.py --distinct`. That command loads
every sighting row into one Python list before collapsing it. The table holds
about 9.5 million rows, so it needs several GB of memory and, on a laptop, it
ends without printing a result (2026-10-19: it printed its warning and returned
to the prompt). This tool keeps one 8-byte hash per indicator, about 60 MB for
700K indicators, and prints a heartbeat so a long scan is never mistaken for a
hung one.

It prints the time the scan took. That is the number that decides whether the
Lambda can do this inside a Monday run, so paste it back.
"""
import argparse
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

REQUIRED_ACCOUNT = "239677749008"
TABLE = "relayshield_intel_iocs"


def _guard_account(region):
    """620534471984 is the pre-audit account and is the shell default, so a
    missing AWS_PROFILE does not error: it quietly aims at the wrong account."""
    import boto3

    who = boto3.client("sts", region_name=region).get_caller_identity()
    if who["Account"] != REQUIRED_ACCOUNT:
        raise SystemExit(
            f"Refusing to run: credentials resolve to account {who['Account']}, "
            f"not {REQUIRED_ACCOUNT}. Prefix the command with "
            f"AWS_PROFILE=relayshield.")


def _approx_rows(region):
    import boto3

    try:
        return boto3.client("dynamodb", region_name=region).describe_table(
            TableName=TABLE)["Table"]["ItemCount"]
    except Exception:  # noqa: BLE001 -- a missing estimate is not a failure
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--max-minutes", type=float, default=90,
                    help="give up (printing NO total) after this long")
    args = ap.parse_args()

    _guard_account(args.region)
    approx = _approx_rows(args.region)

    import boto3
    import relayshield_weekly_metrics as wm

    est = f"about {approx:,} rows" if approx else "a large table"
    print(f"Scanning {TABLE}: {est}. Read-only, a real read bill, a few minutes.\n"
          f"Prints a line about every 10 seconds. Ctrl-C to stop; it will print no total.\n",
          file=sys.stderr)

    started = time.monotonic()
    last = [0.0]

    def beat(rows, distinct):
        now = time.monotonic()
        if now - last[0] < 10:
            return
        last[0] = now
        pct = f" ({rows / approx:.0%})" if approx else ""
        print(f"  {now - started:6.0f}s  {rows:>11,} rows{pct}  "
              f"{distinct:>9,} distinct so far", file=sys.stderr)

    try:
        out = wm._measure_corpus(
            boto3.client("dynamodb", region_name=args.region),
            time.monotonic() + args.max_minutes * 60,
            progress=beat)
    except KeyboardInterrupt:
        print("\nInterrupted. No total was produced.", file=sys.stderr)
        return 130

    if args.json:
        print(json.dumps(out, indent=2))
        return 0 if out.get("measured") else 1
    if not out.get("measured"):
        print(f"\nNOT MEASURED: {out.get('reason')}  (after {out.get('seconds')}s)")
        return 1

    total, prior = out["distinct"], out["week_ago"]
    channel = out["channel_collected"]
    print(f"""
Distinct indicators in the corpus (cumulative)   {total:>10,}
  one week ago                                   {prior:>10,}
  net change this week                           {total - prior:>+10,}
  collected by RelayShield channels              {channel:>10,}
  ingested from public feeds                     {total - channel:>10,}

  scanned {out['rows']:,} sightings in {out['seconds']}s
  counts indicators still inside retention (feeds 365 days, Telegram 90);
  internal figure, never quote it externally.""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
