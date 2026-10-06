#!/usr/bin/env python3
"""Read-only: where did today's VirusTotal quota go?

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/diagnose_vt_usage.py
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/diagnose_vt_usage.py --date 2026-10-06

WHY. VirusTotal's free key allows 500 requests per UTC day (quota resets 00:00 UTC) and
EVERY request counts: a report lookup, a submission and each status poll. Nothing in the
code counts them, so the first sign of exhaustion was VirusTotal's own email. Six places
call VirusTotal on ONE shared key: /v1/scan-url + /v1/result (the checkemail@ Worker
calls these for up to five links per email and polls every 2.5s for up to 12s), /v1/scan-file,
/v1/ip-intel, the composite check's fallback, the Telegram /scan path and the WhatsApp bot
(report lookup, submission, then a poll every 3s for up to 30s per URL, 45s per file).
None of the FREE front doors (Mini App, Chrome extension, widget, /v1/link-check) calls it.

WHAT IT CAN AND CANNOT SEE. Polls are not logged, so these counts are LOWER BOUNDS on VT
requests, and the multiplier is large: one unknown link is 1 submission plus up to ~5 polls
from checkemail, up to ~10 from WhatsApp. The Telegram path logs nothing countable and the
checkemail Worker has no CloudWatch group at all (its calls arrive as scan-url lines).
Read-only. Needs logs:StartQuery/GetQueryResults like miniapp_funnel.py.
"""
import argparse
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
ACCOUNT = "239677749008"
API = "/aws/lambda/relayshield-api"
WA = "/aws/lambda/relayshield-whatsapp-webhook"


def hourly(logs, run, group, term, s, e):
    rows, _, st = run(logs, group, f'filter @message like "{term}" | stats count() as n by bin(1h) as hr | sort hr', s, e)
    return rows, st


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", default=None, help="UTC day, default today")
    args = ap.parse_args()
    import boto3
    from miniapp_funnel import run_insights as run
    if boto3.client("sts").get_caller_identity()["Account"] != ACCOUNT:
        raise SystemExit("Refusing: credentials are not the RelayShield account. Prefix AWS_PROFILE=relayshield.")
    logs = boto3.client("logs", region_name="us-east-1")
    day = dt.datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc) if args.date \
        else dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    s = int(day.timestamp() * 1000)
    e = min(int((day + dt.timedelta(days=1)).timestamp() * 1000), int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000))
    print(f"UTC day {day:%Y-%m-%d}  (VT quota resets 00:00 UTC; limit 500 requests, polls included)\n")

    summary = []
    for label, group, term in (
        ("scan-url submissions (1 VT call each, plus polls)", API, "scan-url submitted"),
        ("scan-file submissions", API, "scan-file submitted"),
        ("VT results returned by /v1/result", API, "VT result"),
        ("ip-intel lookups (cache hits and own-corpus hits INCLUDED)", API, "ip-intel query_type"),
        ("WhatsApp URL scans completed", WA, "VT URL scan complete"),
        ("WhatsApp analyses that TIMED OUT (each burned ~10 polls)", WA, "did not complete within"),
    ):
        rows, st = hourly(logs, run, group, term, s, e)
        total = sum(int(r.get("n") or 0) for r in rows)
        summary.append((label, total, st))
        print(f"== {label}: {total}   [{st}]")
        for r in rows:
            print(f"   {r.get('hr')}  {r.get('n')}")
        print()

    rows, _, st = run(logs, API, 'filter @message like "scan-url submitted" '
                      '| parse @message "url=* analysis_id" as url | stats count() as n by url '
                      '| sort n desc | limit 15', s, e)
    print(f"== most-repeated scan-url targets  [{st}]")
    print("   (the same URL many times in a day is a loop or a spam wave; a spread of distinct URLs is real use)")
    for r in rows:
        print(f"   {r.get('n'):>4}  {(r.get('url') or '')[:100]}")
    print("\n== SUMMARY (lower bounds; polls are not logged)")
    for label, total, st in summary:
        print(f"   {total:>5}  {label}  [{st}]")
    print("   Telegram /scan: no countable log line. checkemail@: appears inside the scan-url rows above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
