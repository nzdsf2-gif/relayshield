#!/usr/bin/env python3
"""One-time backfill of relayshield_intel_feed_current from relayshield_intel_iocs.

The stream maintainer (relayshield_feed_maintainer) starts at LATEST, so it only
sees writes from the moment it was wired up. Everything already in the table --
about 483,000 distinct IOCs spread over 5.74M sighting rows -- has to be seeded
by this script. Run it once, then let the stream keep the table current.

Run:  AWS_PROFILE=relayshield python3.11 tools/backfill_intel_feed.py
Dry:  AWS_PROFILE=relayshield python3.11 tools/backfill_intel_feed.py --dry-run
Note: python3.11 specifically. It is the only interpreter on this machine with boto3.

SAFE TO RE-RUN. Every write is conditional on the row being newer than what is
already stored, so a second run is a no-op rather than a rewind. That matters
because the stream is live while this runs: the two write to the same rows
concurrently, and without the condition a backfill row from June could overwrite
a live sighting from today and resurface a stale indicator as fresh.
"""
import argparse
import collections
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

SOURCE = "relayshield_intel_iocs"
TARGET = "relayshield_intel_feed_current"
FEED_SHARD = "v1"
SERVABLE = {"ip", "domain", "url", "hash_sha256", "email"}
SEGMENTS = 16

stats = collections.Counter()
lock = threading.Lock()


def labels_of(item):
    raw = item.get("malware")
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [p.strip() for p in str(raw).split(",") if p.strip()]


def worker(segment, dry_run):
    ddb = boto3.resource("dynamodb", config=Config(retries={"max_attempts": 10, "mode": "adaptive"}))
    src, dst = ddb.Table(SOURCE), ddb.Table(TARGET)
    # Collapse in memory per segment first. A segment holds a disjoint set of
    # partition keys, so the newest sighting of any IOC is guaranteed to be
    # inside one segment -- no cross-worker coordination needed.
    newest = {}
    kwargs = {"Segment": segment, "TotalSegments": SEGMENTS,
              "ProjectionExpression": "ioc_value, ioc_type, seen_ts, malware, channel, category"}
    while True:
        resp = src.scan(**kwargs)
        for it in resp.get("Items", []):
            with lock:
                stats["rows_scanned"] += 1
            if it.get("ioc_type") not in SERVABLE or not it.get("seen_ts"):
                continue
            v, ts = it["ioc_value"], str(it["seen_ts"])
            cur = newest.get(v)
            if cur is None or ts > cur["seen_ts"]:
                newest[v] = {"seen_ts": ts, "item": it}
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    with lock:
        stats["distinct"] += len(newest)
    if dry_run:
        return

    for v, rec in newest.items():
        it, ts = rec["item"], rec["seen_ts"]
        expr = ("SET last_seen_ts = :ts, first_seen_ts = if_not_exists(first_seen_ts, :ts), "
                "feed_shard = :shard, ioc_type = :t, channel = :ch, category = :cat")
        vals = {":ts": ts, ":shard": FEED_SHARD, ":t": it.get("ioc_type", ""),
                ":ch": it.get("channel", "") or "", ":cat": it.get("category", "") or ""}
        labs = labels_of(it)
        if labs:
            expr += ", malware = :m"
            vals[":m"] = labs
        try:
            dst.update_item(
                Key={"ioc_value": v},
                UpdateExpression=expr,
                ConditionExpression="attribute_not_exists(last_seen_ts) OR last_seen_ts < :ts",
                ExpressionAttributeValues=vals,
            )
            with lock:
                stats["written"] += 1
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                with lock:
                    stats["already_current"] += 1
            else:
                with lock:
                    stats["errors"] += 1
                raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="scan and count, write nothing")
    args = ap.parse_args()

    started = time.time()
    print("backfill %s -> %s  (%d segments, dry_run=%s)" % (SOURCE, TARGET, SEGMENTS, args.dry_run))
    with ThreadPoolExecutor(max_workers=SEGMENTS) as pool:
        futures = [pool.submit(worker, s, args.dry_run) for s in range(SEGMENTS)]
        for f in futures:
            f.result()

    took = time.time() - started
    print("\nrows scanned    : %s" % format(stats["rows_scanned"], ","))
    print("distinct IOCs   : %s" % format(stats["distinct"], ","))
    if not args.dry_run:
        print("written         : %s" % format(stats["written"], ","))
        print("already current : %s" % format(stats["already_current"], ","))
        print("errors          : %s" % format(stats["errors"], ","))
    if stats["distinct"]:
        print("sightings/IOC   : %.1f" % (stats["rows_scanned"] / stats["distinct"]))
    print("elapsed         : %.0f s" % took)
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
