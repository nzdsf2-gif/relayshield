"""
RelayShield FEED MAINTAINER -- keeps relayshield_intel_feed_current deduplicated.

WHY THIS EXISTS (TAXII-PAGINATION-2, 2026-08-16).

relayshield_intel_iocs is keyed (ioc_value HASH, seen_ts RANGE): one row per
SIGHTING. Measured over a 64,000-row parallel-segment sample, it carries 11.9
sightings per distinct IOC, with one IP seen 248 times. 5,744,557 rows is only
about 483,000 distinct indicators.

Serving TAXII straight off that table meant a scan, and a scan meant a full
traversal cost ~965 requests at the old page size. No polling client budgets
that many sequential calls, so Microsoft Sentinel walked the first 25 pages and
restarted every 74 seconds, forever, re-ingesting the same 12,331 indicators and
never reaching the rest of the corpus. Measured, both from CloudWatch and from
inside the customer's workspace, and the two agreed to 0.02%.

This table is the fix: ONE item per distinct IOC, with a GSI keyed
(feed_shard HASH, last_seen_ts RANGE) so the feed can be QUERIED in time order
with native, durable pagination instead of scanned.

WHY A STREAM RATHER THAN DUAL-WRITES. relayshield_intel_iocs has seven writers
(relayshield_intel_feed, intel_monitor, intel_kev, intel_ransomware,
intel_substack, cert_monitor, tools/ingest_apt38_jumpsec) plus the API. Threading
a second write through each is seven deploys, seven chances to miss one, and any
FUTURE ingester silently absent from the feed. A stream consumer cannot be
forgotten: it sees every write to the table by construction.

FEED SEMANTICS, founder decision 2026-08-16: a re-sighting BUMPS last_seen_ts, so
a re-confirmed indicator reappears to any client polling with added_after. Live
re-confirmation from criminal marketplaces is the differentiator; an indicator
that is still being traded today is worth more than one seen once in June.
first_seen_ts is preserved separately and never moves.
"""
import json
import logging
import os

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
FEED_TABLE = os.environ.get("FEED_TABLE", "relayshield_intel_feed_current")

# Single logical shard. The GSI partition key exists so the feed can be queried
# in time order at all; a constant value keeps that ordering GLOBAL, which is
# what a TAXII added_after traversal needs. Measured write rate is ~0.7/s and the
# projected table is ~72 MB, both far inside a single partition's limits, so
# there is nothing to gain from splitting today. If it ever needs sharding, the
# client-visible cost is that a traversal has to merge N ordered streams.
FEED_SHARD = "v1"

# Only types the STIX/MISP serialisers can actually represent. Anything else in
# the source table is not servable, so indexing it would inflate the distinct
# count we report without adding a single deliverable indicator.
SERVABLE_TYPES = {"ip", "domain", "url", "hash_sha256", "email"}


def _s(v):
    """Unwrap a DynamoDB stream attribute value to a plain string."""
    if isinstance(v, dict):
        return v.get("S") or v.get("N") or ""
    return v if isinstance(v, str) else ""


def _labels(image: dict) -> list:
    raw = image.get("malware")
    if not raw:
        return []
    if isinstance(raw, dict) and "L" in raw:
        return [_s(x) for x in raw["L"] if _s(x)]
    val = _s(raw)
    # Labels arrive comma-joined from some sources. Splitting here is what stops
    # "Loader,Potemkin" being treated as a single family name downstream, which
    # is the source-side half of INTEL-LABELS-1.
    return [p.strip() for p in val.split(",") if p.strip()] if val else []


def lambda_handler(event, context):
    table = dynamodb.Table(FEED_TABLE)
    upserts = skipped = removed = stale = 0

    for record in event.get("Records", []):
        name = record.get("eventName")
        keys = record.get("dynamodb", {}).get("Keys", {})
        ioc_value = _s(keys.get("ioc_value"))
        if not ioc_value:
            continue

        if name == "REMOVE":
            # A sighting expiring does NOT mean the indicator is gone; other
            # sightings of the same ioc_value may remain. Deleting here would
            # silently drop live indicators from the feed, so removals are
            # counted and left alone. Expiry is handled by valid_until on the
            # served object, not by deleting feed rows.
            removed += 1
            continue

        image = record.get("dynamodb", {}).get("NewImage", {})
        ioc_type = _s(image.get("ioc_type"))
        if ioc_type not in SERVABLE_TYPES:
            skipped += 1
            continue

        seen_ts = _s(image.get("seen_ts"))
        if not seen_ts:
            skipped += 1
            continue

        # UpdateItem rather than a batched put. A put would rewrite the whole
        # item, resetting first_seen_ts to the latest sighting on every
        # re-sighting -- the opposite of what it is for. if_not_exists pins it to
        # the first sighting we ever saw and leaves it there.
        #
        # The condition also makes this order-independent. Stream records are
        # ordered per partition key but a retry or a backfill running alongside
        # can present an older sighting after a newer one, and without the guard
        # that would drag last_seen_ts backwards and resurface a stale indicator
        # as fresh.
        expr = ("SET last_seen_ts = :ts, "
                "first_seen_ts = if_not_exists(first_seen_ts, :ts), "
                "feed_shard = :shard, ioc_type = :t, channel = :ch, category = :cat")
        values = {
            ":ts": seen_ts, ":shard": FEED_SHARD, ":t": ioc_type,
            ":ch": _s(image.get("channel")), ":cat": _s(image.get("category")),
        }
        labels = _labels(image)
        if labels:
            expr += ", malware = :m"
            values[":m"] = labels

        try:
            table.update_item(
                Key={"ioc_value": ioc_value},
                UpdateExpression=expr,
                ConditionExpression="attribute_not_exists(last_seen_ts) OR last_seen_ts < :ts",
                ExpressionAttributeValues=values,
            )
            upserts += 1
        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            # Already hold a sighting at least this recent. Expected and normal.
            stale += 1
        except Exception:
            logger.exception("feed maintainer failed on %s", ioc_value[:60])
            raise

    logger.info(
        "feed maintainer: upserts=%d already_current=%d skipped=%d removals_ignored=%d records=%d",
        upserts, stale, skipped, removed, len(event.get("Records", [])),
    )
    return {"upserts": upserts, "already_current": stale,
            "skipped": skipped, "removals_ignored": removed}
