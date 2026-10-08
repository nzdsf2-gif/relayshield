#!/usr/bin/env python3
"""Read-only: which source IPs spent the keyless daily allowance on a given UTC day?

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/keyless_ip_top.py --date 2026-10-07

WHY. The composite-check log line carries no source, so the VT usage diagnostic can say HOW MANY
composite checks ran but not WHO sent them. `_check_keyless_ip_quota` already records one counter per
source IP per UTC day (usage_key "ip#<ip>#<YYYY-MM-DD>", attribute call_count, 3-day TTL), so the
answer is already in DynamoDB for any day in the last three.

HOW TO READ IT.
  * One address far above the rest is a single caller: a script, a scraper, a Cloudflare Worker's egress
    IP, or an office behind one NAT. Many addresses with similar counts is real distributed use.
  * call_count is in QUOTA UNITS across EVERY keyless endpoint (link-check, wallet-risk, composite-check,
    email-check), not composite alone, and a composite with url+wallet+email is up to 3 units. It is an
    attribution aid, not a VirusTotal count.
  * Callers presenting a valid API key skip this quota entirely, so they never appear here. That
    includes the Shopify Worker, which provisions a per-shop key.
  * The IPs are personal data. Read them, do not paste them into a committed file or a public place.
    Only the first two octets and a count are printed by default; --full shows the whole address.

Read-only: one Scan, no writes.
"""
import argparse
import datetime as dt

ACCOUNT = "239677749008"
TABLE = "relayshield_demo_key_usage"


def mask(ip: str, full: bool) -> str:
    if full or ":" in ip:  # IPv6: show as stored, it is already long and unreadable
        return ip
    parts = ip.split(".")
    return ".".join(parts[:2] + ["x", "x"]) if len(parts) == 4 else ip


def rows_for_day(table, day: str):
    """Every ip# row for the day. Paginated: a Scan returns at most 1 MB per page."""
    out, kwargs = [], {
        "FilterExpression": "begins_with(usage_key, :p) AND contains(usage_key, :d)",
        "ExpressionAttributeValues": {":p": "ip#", ":d": "#" + day},
    }
    pages = 0
    while True:
        resp = table.scan(**kwargs)
        pages += 1
        for item in resp.get("Items", []):
            key = str(item.get("usage_key", ""))
            # Re-check both ends client-side: the server filter is the efficient one, this is the
            # one that cannot be fooled by a key shaped like ours on another table prefix.
            if key.startswith("ip#") and key.endswith("#" + day):
                out.append((key.split("#")[1], int(item.get("call_count", 0))))
        if "LastEvaluatedKey" not in resp:
            return out, pages
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
        if pages % 5 == 0:
            print(f"  ... {pages} pages scanned, {len(out)} matching rows so far")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", default=None, help="UTC day YYYY-MM-DD, default today")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--full", action="store_true", help="print whole addresses")
    args = ap.parse_args()
    import boto3
    if boto3.client("sts").get_caller_identity()["Account"] != ACCOUNT:
        raise SystemExit("Refusing: credentials are not the RelayShield account. Prefix AWS_PROFILE=relayshield.")
    day = args.date or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(TABLE)
    print(f"Scanning {TABLE} for keyless per-IP counters on UTC day {day} (read-only) ...")
    rows, pages = rows_for_day(table, day)
    rows.sort(key=lambda r: r[1], reverse=True)
    total = sum(n for _, n in rows)
    print(f"\n{len(rows)} distinct source IPs, {total} quota units in total ({pages} page(s) scanned)")
    if not rows:
        print("NO ROWS. Either nothing keyless ran that day, or the rows have expired (3-day TTL). "
              "Do not read this as proof of no traffic.")
        return 0
    print(f"\nTop {min(args.top, len(rows))} by quota units:")
    for ip, n in rows[:args.top]:
        print(f"  {n:>6}  {mask(ip, args.full)}   {100 * n / total:4.1f}% of the day")
    top1 = rows[0][1]
    print(f"\nReading aid: the busiest address is {100 * top1 / total:.0f}% of all keyless units. "
          "Over about half means one caller, and that is the lead; under ten percent means spread across many.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
