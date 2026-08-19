#!/usr/bin/env python3
"""
Cut the outreach sample slice from relayshield_intel_iocs.

Produces the artefact every Segment 1 message in victim_side_outreach_messages.md
offers: a slice a blockchain-analytics team can measure their own coverage
against, plus the composition numbers and a methodology note, so nothing in the
outreach rests on our word.

    AWS_PROFILE=relayshield python3 tools/export_intel_sample.py --out dist/intel_sample

Outputs, all into --out:
    relayshield_intel_sample.csv    the slice, one row per distinct indicator
    relayshield_intel_sample.jsonl  same rows, machine-readable
    METHODOLOGY.md                  collection, sampling, limits, how to verify
    manifest.json                   live corpus totals, slice counts, SHA-256s

Three deliberate decisions, all stated in METHODOLOGY.md rather than hidden:

1. Emails and phone numbers are NEVER exported. They are personal data of
   victims as often as of actors, and the corpus holds 11 and 122 of them
   respectively, so their absence costs the recipient nothing.
2. Channel names are NEVER exported. They are the collection surface; naming
   them hands over the pipeline rather than a sample of its output. Each
   channel gets a stable per-export label (source_01, source_02, ...) so a
   recipient can still see clustering across sources.
3. The slice is a sample, not the corpus. Default 250 indicators, stratified
   to mirror live composition, chosen by a seeded deterministic hash so the
   same --seed reproduces the same slice byte for byte and we can answer
   "send it again" without a second judgement call.
"""

import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

IOCS_TABLE = "relayshield_intel_iocs"

# Never exported. See decision 1 above.
EXCLUDED_TYPES = {"email", "phone"}


def _scan_live(table_name, region):
    """Full scan of the IOC table, projecting only what the slice needs."""
    import boto3

    table = boto3.resource("dynamodb", region_name=region).Table(table_name)
    kwargs = {
        "ProjectionExpression": "ioc_value, seen_ts, ioc_type, channel, category, malware",
    }
    items, scanned = [], 0
    while True:
        page = table.scan(**kwargs)
        items.extend(page.get("Items", []))
        scanned += page.get("ScannedCount", 0)
        key = page.get("LastEvaluatedKey")
        if not key:
            break
        kwargs["ExclusiveStartKey"] = key
    print(f"scanned {scanned} rows, retrieved {len(items)} items", file=sys.stderr)
    return items


def _load_fixture(path):
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def collapse(items):
    """One record per distinct indicator, carrying its sighting history.

    The table is keyed (ioc_value, seen_ts), so a value seen on five days is
    five rows. Counting rows would inflate every number we quote.
    """
    by_value = {}
    for it in items:
        value = (it.get("ioc_value") or "").strip()
        if not value:
            continue
        ts = it.get("seen_ts") or ""
        rec = by_value.get(value)
        if rec is None:
            by_value[value] = {
                "ioc_value": value,
                "ioc_type": it.get("ioc_type") or "unknown",
                "first_seen": ts,
                "last_seen": ts,
                "times_seen": 1,
                "channels": {it.get("channel") or ""},
                "category": it.get("category") or "",
                "malware": it.get("malware") or "",
            }
        else:
            rec["times_seen"] += 1
            if ts and (not rec["first_seen"] or ts < rec["first_seen"]):
                rec["first_seen"] = ts
            if ts and ts > rec["last_seen"]:
                rec["last_seen"] = ts
            rec["channels"].add(it.get("channel") or "")
            if not rec["malware"] and it.get("malware"):
                rec["malware"] = it["malware"]
    return list(by_value.values())


def channel_labels(records):
    """Stable per-export pseudonyms, ordered by how much a channel contributes.

    Deterministic for a given corpus, and reveals nothing about the channel
    itself. See decision 2.
    """
    volume = Counter()
    for rec in records:
        for ch in rec["channels"]:
            if ch:
                volume[ch] += 1
    return {ch: f"source_{i:02d}" for i, (ch, _) in enumerate(volume.most_common(), start=1)}


def _rank(value, seed):
    """Deterministic sort key in [0,1) — the seeded 'random' draw."""
    digest = hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()[:16]
    return int(digest, 16) / float(1 << 64)


def stratify(records, size, seed):
    """Sample proportionally by indicator type, so the slice looks like the corpus.

    A flat random sample of a corpus that is 59% URLs would hand over a slice
    that is 59% URLs and almost no wallets, which is the half they care about.
    Every type present keeps at least one row.
    """
    buckets = defaultdict(list)
    for rec in records:
        buckets[rec["ioc_type"]].append(rec)

    total = sum(len(v) for v in buckets.values())
    if total == 0:
        return []
    if size >= total:
        quota = {t: len(v) for t, v in buckets.items()}
    else:
        quota = {t: max(1, round(size * len(v) / total)) for t, v in buckets.items()}
        # Rounding up per type overshoots; trim from the largest buckets first.
        while sum(quota.values()) > size:
            biggest = max(quota, key=lambda t: (quota[t], len(buckets[t])))
            if quota[biggest] <= 1:
                break
            quota[biggest] -= 1

    out = []
    for ioc_type, bucket in buckets.items():
        bucket.sort(key=lambda r: _rank(r["ioc_value"], seed))
        out.extend(bucket[: quota[ioc_type]])
    out.sort(key=lambda r: (r["ioc_type"], r["ioc_value"]))
    return out


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


FIELDS = ["ioc_type", "ioc_value", "first_seen", "last_seen", "times_seen",
          "sources", "source_count", "category", "malware"]


def rows_for_export(sample, labels):
    rows = []
    for rec in sample:
        srcs = sorted(labels[ch] for ch in rec["channels"] if ch)
        rows.append({
            "ioc_type": rec["ioc_type"],
            "ioc_value": rec["ioc_value"],
            "first_seen": rec["first_seen"],
            "last_seen": rec["last_seen"],
            "times_seen": rec["times_seen"],
            "sources": " ".join(srcs),
            "source_count": len(srcs),
            "category": rec["category"],
            "malware": rec["malware"],
        })
    return rows


METHODOLOGY = """# RelayShield indicator sample — methodology

Generated {generated}. Sample of {sample_n} distinct indicators drawn from a live corpus of
{corpus_n} distinct indicators collected from monitored criminal Telegram channels.

## What this is

Scam infrastructure extracted from the channels where it is advertised and coordinated, not
re-packaged from public feeds. One row per distinct indicator, carrying every sighting we have
for it: when we first saw it, when we last saw it, how many times, and across how many distinct
channels.

`first_seen` is the honest number to test us on. It is the timestamp our collector recorded,
which is what any claim about arriving earlier than a public feed has to rest on.

## Live composition, measured at export time

{composition}

## How the sample was drawn

- One record per distinct indicator. The underlying table is keyed (indicator, sighting
  timestamp), so a value seen on five days is five rows; counting rows would inflate every
  number above.
- Stratified by indicator type in proportion to the live composition, so the slice looks like
  the corpus rather than being dominated by URLs.
- Selection within each type is a SHA-256 rank over the indicator value with seed `{seed}`.
  Deterministic: the same seed reproduces this exact slice.

## What is deliberately not here, and why

- **No email addresses or phone numbers.** They are personal data, of victims as often as of
  actors. The full corpus holds 11 and 122 of them, so their absence costs you nothing.
- **No channel names.** Each contributing channel appears as a stable label (`source_01`, ...)
  so you can still see clustering across sources. The channel list is the collection surface;
  naming it would be handing over the pipeline rather than a sample of its output.
- **This is a sample, not the corpus.**

## Known limits, stated up front

- The corpus is **crypto-scam shaped**: URLs and wallets dominate. If you are evaluating it for
  breach or victim-domain coverage, it is thin, and we would rather you knew that now.
- Domains are the weakest segment. A large share are article links scraped from CTI news reposts
  (news sites, web infrastructure), not attacker infrastructure. Treat the domain rows as the
  least useful part of this slice.
- Indicators carry a 90-day TTL, so this is a live-window corpus, not a historical archive.

## How to verify the exclusivity claim yourself

We claim 99.89% of channel-sourced indicators appear in none of the public feeds we ingest.
That is our measurement, against our feed set, and you should not take it on our word:

1. Take the wallet and URL rows from this slice.
2. Intersect them with your own coverage, and with whatever public feeds you ingest.
3. For anything that does overlap, compare your first-seen date with the `first_seen` column.

Overlap tells you how much is genuinely additive. The date comparison tells you whether it is
additive *earlier*, which is the part that matters.

## Files

- `relayshield_intel_sample.csv` — the slice
- `relayshield_intel_sample.jsonl` — same rows, one JSON object per line
- `manifest.json` — corpus totals, per-type counts, SHA-256 of each file
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="dist/intel_sample", help="output directory")
    ap.add_argument("--size", type=int, default=250, help="indicators in the slice")
    ap.add_argument("--seed", default="outreach-2026-08", help="sampling seed (reproducible)")
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--table", default=IOCS_TABLE)
    ap.add_argument("--fixture", help="read items from a JSONL file instead of DynamoDB")
    args = ap.parse_args()

    items = _load_fixture(args.fixture) if args.fixture else _scan_live(args.table, args.region)
    records = [r for r in collapse(items) if r["ioc_type"] not in EXCLUDED_TYPES]
    if not records:
        sys.exit("no exportable indicators found")

    composition = Counter(r["ioc_type"] for r in records)
    corpus_n = len(records)
    sample = stratify(records, args.size, args.seed)
    labels = channel_labels(sample)
    rows = rows_for_export(sample, labels)

    os.makedirs(args.out, exist_ok=True)
    csv_path = os.path.join(args.out, "relayshield_intel_sample.csv")
    jsonl_path = os.path.join(args.out, "relayshield_intel_sample.jsonl")
    with open(csv_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    with open(jsonl_path, "w") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    comp_lines = "\n".join(
        f"| {t} | {n} | {n / corpus_n:.1%} |"
        for t, n in composition.most_common()
    )
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    md_path = os.path.join(args.out, "METHODOLOGY.md")
    with open(md_path, "w") as fh:
        fh.write(METHODOLOGY.format(
            generated=generated, sample_n=len(rows), corpus_n=corpus_n, seed=args.seed,
            composition="| Type | Distinct | Share |\n|---|---|---|\n" + comp_lines,
        ))

    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed,
        "corpus_distinct_exportable": corpus_n,
        "corpus_composition": dict(composition.most_common()),
        "sample_size": len(rows),
        "sample_composition": dict(Counter(r["ioc_type"] for r in rows).most_common()),
        "distinct_sources_in_sample": len(labels),
        "excluded_types": sorted(EXCLUDED_TYPES),
        "sha256": {
            "relayshield_intel_sample.csv": _sha256_file(csv_path),
            "relayshield_intel_sample.jsonl": _sha256_file(jsonl_path),
            "METHODOLOGY.md": _sha256_file(md_path),
        },
    }
    with open(os.path.join(args.out, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)

    print(f"corpus (exportable, distinct): {corpus_n}")
    for t, n in composition.most_common():
        print(f"  {t:14s} {n:6d}  {n / corpus_n:6.1%}")
    print(f"sample: {len(rows)} indicators from {len(labels)} distinct sources -> {args.out}")


if __name__ == "__main__":
    main()
