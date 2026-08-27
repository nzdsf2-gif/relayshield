#!/usr/bin/env python3
"""Triage relayshield_intel_channels: the pending_review backlog and the active set.

WHY THIS EXISTS
---------------
Two questions came up on 2026-08-20 that neither could be answered from the dev
sandbox, because it holds no AWS credentials:

  1. The digest reported 122 active channels; the founder counts 95 today.
  2. 75 channels sit in category=pending_review and have never been triaged.

This answers both by reading the table directly. It is READ-ONLY by default and
prints what it would change; `--apply` is required to write anything.

USAGE (on the founder's Mac)

    AWS_PROFILE=relayshield python3 tools/triage_channels.py
    AWS_PROFILE=relayshield python3 tools/triage_channels.py --pending
    AWS_PROFILE=relayshield python3 tools/triage_channels.py --activate a,b,c --apply

Needs boto3. Homebrew Python is PEP 668 externally-managed, so use the throwaway
venv the handoff describes:

    python3 -m venv ~/.rsvenv && ~/.rsvenv/bin/pip install boto3
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/triage_channels.py
"""

import argparse
import sys
from collections import Counter

import boto3
from boto3.dynamodb.conditions import Attr

TABLE = "relayshield_intel_channels"
REGION = "us-east-1"


def scan_all(table, **kwargs):
    items, resp = [], table.scan(**kwargs)
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
        items.extend(resp.get("Items", []))
    return items


def summarize(rows):
    active = [r for r in rows if r.get("active") is True]
    inactive = [r for r in rows if r.get("active") is not True]
    failing = [r for r in active if int(r.get("consecutive_failures") or 0) > 0]

    print(f"Total rows          : {len(rows)}")
    print(f"active=True         : {len(active)}")
    print(f"active=False/unset  : {len(inactive)}")
    print()

    # THE 95-vs-122 QUESTION. active=True means "we intend to monitor this". It
    # has never meant "and we can". consecutive_failures (added 2026-08-20) is
    # the first field that distinguishes them, so it is empty until the patched
    # monitor has run at least once -- an all-zero column here means "no data
    # yet", NOT "no attrition".
    print(f"active but FAILING  : {len(failing)}")
    if failing:
        print("  (active=True yet unreachable — this is the 122-vs-95 gap)")
        for r in sorted(failing, key=lambda x: -int(x.get("consecutive_failures") or 0))[:25]:
            print(f"   @{r['username']:<28} fails={r.get('consecutive_failures')}"
                  f"  {r.get('last_error','')}  {str(r.get('last_error_at',''))[:19]}")
    else:
        print("  none recorded — if the patched monitor has not run yet, this")
        print("  proves nothing. Check the digest's 'X of Y active' line instead.")
    print()

    print("By category:")
    for cat, n in Counter(str(r.get("category", "—")) for r in rows).most_common():
        print(f"   {cat:<24} {n}")


def show_pending(rows, limit):
    pending = [r for r in rows if str(r.get("category")) == "pending_review"]

    def members(r):
        try:
            return int(r.get("approximate_member_count") or r.get("member_count") or 0)
        except (TypeError, ValueError):
            return 0

    def provenance(r):
        via   = str(r.get("discovery_method", "") or "").strip()
        found = str(r.get("found_via", "") or "").strip()
        return (via and via != "?") or bool(found)

    # Bucketing added 2026-08-26. The flat list was 117 rows and mostly
    # unreviewable: @google, @anthropic, @deepmind, @moscow, @finance,
    # @thousands, @approximately. Those are English words and company names
    # extracted as usernames, and they never resolved -- no member count, no
    # discovery method, no found_via. Asking a human to read 117 rows to find
    # the eight that resolved is why this backlog has not been triaged.
    #
    # The split is on evidence, not on a word list: a row either resolved
    # against Telegram (it has a member count), or it has provenance saying
    # where it came from, or it has neither and cannot be judged at all.
    reviewable = [r for r in pending if members(r) > 0]
    unresolved = [r for r in pending if members(r) == 0 and provenance(r)]
    orphaned   = [r for r in pending if members(r) == 0 and not provenance(r)]

    print(f"\n{len(pending)} channels in pending_review")
    print(f"  {len(reviewable):>3} resolved, judge these        (member count known)")
    print(f"  {len(unresolved):>3} unresolved but traceable    (has provenance, never resolved)")
    print(f"  {len(orphaned):>3} orphaned                    (no members, no provenance)")

    print("\n--- REVIEW THESE: resolved, sorted by size ---\n")
    for r in sorted(reviewable, key=members, reverse=True)[:limit]:
        print(f"@{r['username']:<30} members={members(r):<9}"
              f" via={str(r.get('discovery_method','?'))[:22]:<22}"
              f" found_via={str(r.get('found_via','') or '-')[:22]}")

    if unresolved:
        print("\n--- UNRESOLVED: came from somewhere, never resolved ---")
        print("Re-resolve before judging. A dead handle here is normal attrition.\n")
        for r in sorted(unresolved, key=lambda r: r["username"])[:limit]:
            print(f"@{r['username']:<30} via={str(r.get('discovery_method','?'))[:22]:<22}"
                  f" found_via={str(r.get('found_via','') or '-')[:22]}")

    if orphaned:
        print(f"\n--- ORPHANED: {len(orphaned)} rows with no evidence of any kind ---")
        print("Almost certainly @word extracted from message text rather than a real")
        print("handle. They cannot be judged and they inflate this queue on every run.")
        print("Fix the extractor before purging, or the next run recreates them.\n")
        names = sorted(r["username"] for r in orphaned)
        for i in range(0, len(names), 6):
            print("  " + "  ".join(f"@{n}"[:22].ljust(22) for n in names[i:i + 6]))

    print("\nActivate the ones worth monitoring:")
    print("  ... --activate name1,name2 --apply")
    print("\nJudge by what the room is FOR, not by size. The active set is")
    print("infostealer/credential_dump-shaped; a big room off-theme is noise.")


def activate(table, names, apply_):
    for name in names:
        name = name.strip().lstrip("@")
        if not name:
            continue
        if not apply_:
            print(f"DRY RUN would activate @{name}")
            continue
        table.update_item(
            Key={"username": name},
            UpdateExpression="SET active = :t, category = :c REMOVE consecutive_failures, last_error",
            ExpressionAttributeValues={":t": True, ":c": "infostealer"},
        )
        print(f"activated @{name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pending", action="store_true", help="list the pending_review backlog")
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--activate", default="", help="comma-separated usernames to activate")
    ap.add_argument("--apply", action="store_true", help="actually write (default is dry run)")
    args = ap.parse_args()

    table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
    rows = scan_all(table)
    if not rows:
        print("No rows returned — wrong profile or wrong region?", file=sys.stderr)
        return 1

    summarize(rows)
    if args.pending:
        show_pending(rows, args.limit)
    if args.activate:
        activate(table, args.activate.split(","), args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
