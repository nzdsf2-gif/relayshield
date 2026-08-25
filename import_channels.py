#!/usr/bin/env python3
"""Import hand-collected channels and operator handles into the intel tables.

WHY THIS EXISTS
---------------
Three sources publish running lists of criminal Telegram channels and are all
blocked by the dev sandbox's egress proxy — socradar.io, breachsense.com and
ransomlook.io. They are ordinary websites in a browser, so the fastest path to
verified handles is a human copying them out. This turns that paste into rows.

RansomLook is also wired as an automatic source in
relayshield_intel_discovery.py (ingest_ransomlook_channels). This tool is for
the two that have no API, and for anything found by hand.

WHAT IT WRITES
--------------
Channels  -> relayshield_intel_channels, category="pending_review",
             active=False. The SAME safe queue every other discovery path uses,
             so the OSINT-2 classifier decides, never this script.
Operators -> relayshield_operator_identities, one row per (handle, platform),
             first_seen preserved via if_not_exists.

NOTHING HERE ACTIVATES A CHANNEL. That is deliberate and should stay true: an
approve flips active=True with no undo, and a hand-typed list is exactly where
a typo enters.

USAGE (on the founder's Mac)

    python3 -m venv /tmp/rsvenv && /tmp/rsvenv/bin/pip install boto3

    # dry run — prints what it would write, touches nothing
    AWS_PROFILE=relayshield /tmp/rsvenv/bin/python tools/import_channels.py channels.txt

    # commit it
    AWS_PROFILE=relayshield /tmp/rsvenv/bin/python tools/import_channels.py channels.txt --apply

    # operator handles instead of channels
    AWS_PROFILE=relayshield /tmp/rsvenv/bin/python tools/import_channels.py operators.txt \
        --operators --source socradar --apply

INPUT FORMAT
------------
One entry per line. Blank lines and lines starting with # are ignored.
The @ is optional. An optional comma-separated note becomes the description:

    @lockbitsupp, LockBit support channel
    akira_news
    # anything after a hash is a comment
"""

import argparse
import re
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal

import boto3

CHANNELS_TABLE  = "relayshield_intel_channels"
OPERATORS_TABLE = "relayshield_operator_identities"
REGION          = "us-east-1"
TTL_DAYS        = 90

# Telegram usernames: 5-32 chars, letters/digits/underscore. Kept slightly
# looser at 4 so short legacy handles are not silently dropped, matching the
# floor used elsewhere in this codebase.
_USERNAME_RE = re.compile(r"^[a-z0-9_]{4,32}$")


def parse(path: str) -> list[tuple[str, str]]:
    """(handle, note) pairs from the input file. Reports what it rejects."""
    out, rejected = [], []
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            handle, _, note = line.partition(",")
            handle = handle.strip().lstrip("@").lower()
            # Tolerate a pasted t.me link, which is how these usually arrive.
            handle = re.sub(r"^(?:https?://)?(?:t\.me|telegram\.me)/", "", handle).strip("/")
            if not _USERNAME_RE.match(handle):
                rejected.append((lineno, line))
                continue
            out.append((handle, note.strip()))

    if rejected:
        print(f"\n{len(rejected)} line(s) rejected — not valid Telegram usernames:")
        for lineno, line in rejected[:20]:
            print(f"   line {lineno}: {line!r}")
        print("  (a rejected line is silently useless if ignored, hence this list)\n")

    # Dedupe, keeping the first note seen for a handle.
    seen, deduped = set(), []
    for h, n in out:
        if h in seen:
            continue
        seen.add(h)
        deduped.append((h, n))
    if len(deduped) != len(out):
        print(f"{len(out) - len(deduped)} duplicate handle(s) collapsed.")
    return deduped


def import_channels(entries, source: str, apply: bool) -> None:
    table = boto3.resource("dynamodb", region_name=REGION).Table(CHANNELS_TABLE)
    now   = datetime.now(timezone.utc).isoformat()
    new = skipped = 0

    for handle, note in entries:
        existing = table.get_item(Key={"username": handle}).get("Item")
        if existing:
            # Never overwrite. An active channel is being monitored and a
            # rejected one was rejected on purpose; re-queueing either would
            # make the classifier re-pay for a verdict it already reached.
            skipped += 1
            print(f"  skip @{handle:<28} already known "
                  f"(category={existing.get('category')}, active={existing.get('active')})")
            continue

        new += 1
        print(f"  {'ADD ' if apply else 'would add'} @{handle:<28} {note[:50]}")
        if not apply:
            continue
        table.put_item(Item={
            "username":         handle,
            "category":         "pending_review",
            "description":      note or f"Imported from {source}",
            "member_count":     0,
            "first_seen":       now,
            "last_verified":    now,
            "active":           False,
            "discovery_method": f"manual_import:{source}",
            "found_via":        source,
        })
        time.sleep(0.05)

    print(f"\n{new} new, {skipped} already known.")
    if new and not apply:
        print("DRY RUN — nothing written. Re-run with --apply.")
    elif new:
        print("Queued as pending_review. Run the classifier to triage:")
        print("  GitHub → Actions → INTEL Channel Classifier (OSINT-2) → Run workflow")


def import_operators(entries, source: str, platform: str, apply: bool) -> None:
    table = boto3.resource("dynamodb", region_name=REGION).Table(OPERATORS_TABLE)
    now   = datetime.now(timezone.utc).isoformat()

    for handle, note in entries:
        print(f"  {'ADD ' if apply else 'would add'} @{handle:<28} [{platform}] {note[:45]}")
        if not apply:
            continue
        # Mirrors _store_operator_identities() in relayshield_intel_monitor.py:
        # if_not_exists preserves first_seen across re-imports, ADD keeps the
        # counters and the string sets server-side.
        table.update_item(
            Key={"handle": handle, "platform": platform},
            UpdateExpression=(
                "SET first_seen = if_not_exists(first_seen, :now), "
                "    last_seen  = :now, "
                "    #ttl       = :ttl "
                "ADD sightings :one, channels :ch, categories :cat"
            ),
            ExpressionAttributeNames={"#ttl": "ttl"},
            ExpressionAttributeValues={
                ":now": now,
                ":one": Decimal(1),
                ":ch":  {f"manual:{source}"},
                ":cat": {"ransomware" if "ransom" in source.lower() else "unknown"},
                ":ttl": Decimal(int(time.time()) + TTL_DAYS * 86400),
            },
        )
        time.sleep(0.05)

    print(f"\n{len(entries)} operator handle(s) processed.")
    if not apply:
        print("DRY RUN — nothing written. Re-run with --apply.")
    print("\nREMINDER: this table is a LEAD LIST, not a verdict. A handle here "
          "appeared somewhere we monitor; it is not proof of anything. Do not "
          "export it as 'known scam operators'.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="one handle per line; '# comment' and blanks ignored")
    ap.add_argument("--operators", action="store_true",
                    help="write to the operator identity table instead of channels")
    ap.add_argument("--platform", default="telegram",
                    help="operator platform label (default: telegram)")
    ap.add_argument("--source", default="manual",
                    help="where the list came from, e.g. socradar / breachsense / ransomlook")
    ap.add_argument("--apply", action="store_true",
                    help="write to DynamoDB (default: dry run)")
    args = ap.parse_args()

    entries = parse(args.file)
    if not entries:
        print("Nothing usable in the input file.")
        return 1

    print(f"{len(entries)} entr(ies) parsed from {args.file}, source={args.source}\n")
    if args.operators:
        import_operators(entries, args.source, args.platform, args.apply)
    else:
        import_channels(entries, args.source, args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
