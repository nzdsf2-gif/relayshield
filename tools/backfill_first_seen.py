#!/usr/bin/env python3
"""A6 backfill: populate relayshield_intel_first_seen from existing sightings.

The monitor records first-seen for every indicator from 2026-08-27. Everything
collected before that has its first sighting sitting in relayshield_intel_iocs
and nowhere else, so the lead-time claim for older indicators would read as
"first seen 2026-08-27", which is false and worse than absent.

min(seen_ts) per ioc_value is exactly what a live query would compute today, so
the backfilled rows are correct rather than approximate.

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/backfill_first_seen.py
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/backfill_first_seen.py --apply

Read-only without --apply. Writes are conditional on attribute_not_exists, so
re-running is safe and a row already written by the live monitor is never
overwritten by an older scan.

CREATE THE TABLE FIRST, with NO TTL:

    aws dynamodb create-table \\
      --table-name relayshield_intel_first_seen \\
      --attribute-definitions AttributeName=ioc_value,AttributeType=S \\
      --key-schema AttributeName=ioc_value,KeyType=HASH \\
      --billing-mode PAY_PER_REQUEST \\
      --region us-east-1

A TTL here would delete the evidence the lead-time claim rests on.
"""
import argparse
import sys

IOCS = "relayshield_intel_iocs"
FIRST_SEEN = "relayshield_intel_first_seen"


def main() -> int:
    import boto3

    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    ddb = boto3.resource("dynamodb")
    src = ddb.Table(IOCS)

    earliest: dict[str, tuple[str, str, str]] = {}
    scanned = 0
    kwargs: dict = {"ProjectionExpression": "ioc_value, seen_ts, channel, category"}
    while True:
        resp = src.scan(**kwargs)
        for it in resp.get("Items", []):
            scanned += 1
            v, ts = it.get("ioc_value"), it.get("seen_ts")
            if not v or not ts:
                continue
            cur = earliest.get(v)
            if cur is None or ts < cur[0]:
                earliest[v] = (ts, it.get("channel", ""), it.get("category", ""))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last

    print(f"scanned {scanned} sighting(s)")
    print(f"{len(earliest)} distinct indicator(s)")
    if earliest:
        oldest = min(v[0] for v in earliest.values())
        newest = max(v[0] for v in earliest.values())
        print(f"first-seen range: {oldest}  ..  {newest}")

    if not args.apply:
        print("\nREAD-ONLY. Re-run with --apply to write. Create the table first, with NO TTL:")
        print("  see this file's docstring for the create-table command")
        return 0

    dst = ddb.Table(FIRST_SEEN)
    # Written one at a time, not batched: batch_writer cannot express a
    # condition, and unconditional writes here would overwrite a first_seen the
    # live monitor already recorded with a LATER date from an older scan row.
    written = skipped = failed = 0
    for value, (ts, channel, category) in earliest.items():
        try:
            dst.put_item(
                Item={"ioc_value": value, "first_seen": ts,
                      "first_channel": channel, "first_category": category},
                ConditionExpression="attribute_not_exists(ioc_value)",
            )
            written += 1
        except Exception as exc:
            if type(exc).__name__ == "ConditionalCheckFailedException":
                skipped += 1          # already recorded, by the live monitor or a prior run
            else:
                failed += 1
                if failed <= 5:
                    print(f"  failed {value[:28]}: {type(exc).__name__}: {exc}")
    print(f"\nwrote {written}, skipped {skipped} already present, {failed} failure(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
