#!/usr/bin/env python3
"""Read-only summary of what opt-in MCP proxies have reported.

    AWS_PROFILE=relayshield python3 tools/mcp_proxy_telemetry_report.py
    AWS_PROFILE=relayshield python3 tools/mcp_proxy_telemetry_report.py --days 7 --min-reporters 2

Prints, from relayshield_mcp_proxy_telemetry:
  * how many distinct installs reported, and over what window
  * verdict counts by category, by taxonomy entry and by kind
  * CANDIDATE indicators: host, payload hash prefix, category, how many distinct
    reporting accounts, and review status

WHAT A CANDIDATE IS NOT: it is not a finding and nothing here promotes it. Each is
a claim from an open endpoint, attributable only to an account. Count distinct
REPORTERS, not reports: one account repeating itself is one witness.

A SMALL NUMBER IS NOT A SMALL RESULT. Reporting is opt-in, so these figures are a
floor on what proxies see and say nothing about prevalence. Do not quote them
externally as a rate (MEASUREMENT DOCTRINE).

It scans the whole table, which is small while adoption is. Progress goes to
stderr so a slow scan is distinguishable from a hang.
"""
import argparse
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

ACCOUNT = "239677749008"
TABLE = "relayshield_mcp_proxy_telemetry"


def summarise(items, since_iso: str, min_reporters: int) -> dict:
    installs, counts, cands = set(), Counter(), []
    for it in items:
        pk, sk = it.get("pk", ""), it.get("sk", "")
        if pk.startswith("INSTALL#") and sk.startswith("REPORT#") and sk[7:] >= since_iso:
            installs.add(pk[8:])
            for c in it.get("counts", []):
                counts[(c["category"], c.get("taxonomy_id", ""), c["kind"])] += int(c["n"])
        elif pk.startswith("CAND#") and it.get("last_seen", "") >= since_iso:
            if len(it.get("reporters") or ()) >= min_reporters:
                cands.append(it)
    cands.sort(key=lambda c: (-len(c.get("reporters") or ()), -int(c.get("report_count", 0))))
    return {"installs": len(installs), "counts": counts, "candidates": cands}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--min-reporters", type=int, default=1)
    args = ap.parse_args()
    import boto3
    got = boto3.client("sts").get_caller_identity()["Account"]
    if got != ACCOUNT:
        print(f"STOP: credentials resolve to {got}, not {ACCOUNT}.", file=sys.stderr)
        return 1
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(TABLE)
    items, kw, pages = [], {}, 0
    while True:
        r = table.scan(**kw)
        items += r.get("Items", [])
        pages += 1
        print(f"  scanned {pages} page(s), {len(items)} row(s)", file=sys.stderr)
        if not r.get("LastEvaluatedKey"):
            break
        kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]
    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat(timespec="seconds")
    s = summarise(items, since, args.min_reporters)
    print(f"window: last {args.days} days    distinct installs reporting: {s['installs']}")
    print("\nVERDICT COUNTS (category / taxonomy entry / kind)")
    for (c, t, k), n in s["counts"].most_common():
        print(f"  {n:>7}  {c:<24} {t or '-':<46} {k}")
    if not s["counts"]:
        print("  none. Either no proxy has opted in, or none has flagged anything.")
    print(f"\nCANDIDATE INDICATORS (>= {args.min_reporters} distinct reporting account(s)). UNREVIEWED CLAIMS.")
    for c in s["candidates"]:
        print(f"  reporters={len(c.get('reporters') or ()):<3} reports={int(c.get('report_count', 0)):<4} "
              f"{c['host']:<40} {c['payload_hash'][:12]}  {c['category']:<18} {c.get('status', '')}")
    if not s["candidates"]:
        print("  none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
