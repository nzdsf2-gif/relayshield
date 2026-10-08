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
/v1/link-check does not call it. CORRECTED 2026-10-08: this line used to say the Mini App, the Chrome
extension and the widget do not either. That was true until 2026-10-02 and false from then on: all
three call /v1/composite-check (commit aa697dd), and from 2026-10-04 (579de4c) that endpoint fell
back to VirusTotal on an unknown URL, with no cache table until 2026-10-07. The per-IP cap did not
stop it: one client looped on 429s and a pool of cloud IPs each stayed under 300. From 2026-10-08
the fallback runs for callers with a VERIFIED API KEY only, so a keyless request can no longer
spend VirusTotal quota through composite-check, and `vt_fallback_withheld` lines count the ones
it turned away.

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
        # EVERY request is logged with its path, so these are exact request counts, not
        # lower bounds. /v1/result was unauthenticated and spent one VT request per call
        # until 2026-10-06, and its failures log only at ERROR, so a probing crawler
        # leaves almost nothing else behind. A big number here is the leak.
        ("GET /v1/result requests (each was one VT request)", API, "path=/v1/result"),
        ("GET /v1/payg/result requests (each was one VT request)", API, "path=/v1/payg/result"),
        ("result polls that FAILED (probing for ids that do not exist)", API, "VT result poll failed"),
        ("POST /v1/scan-url requests", API, "path=/v1/scan-url"),
        ("scan-url submissions (1 VT call each, plus polls)", API, "scan-url submitted"),
        ("vt_call lines (after the budget shipped: every allowed request)", API, "vt_call surface="),
        ("vt_refused lines (budget said no)", API, "vt_refused"),
        ("scan-file submissions", API, "scan-file submitted"),
        ("VT results returned by /v1/result", API, "VT result"),
        ("ip-intel lookups (cache hits and own-corpus hits INCLUDED)", API, "ip-intel query_type"),
        # THE SEVENTH SPENDER THIS TOOL DID NOT COUNT. /v1/composite-check falls back to a VT URL
        # report on an "unknown" URL (added 2026-10-04) and its cache table did not exist until
        # 2026-10-07, so every unknown URL was one VT request. Callers: the Chrome extension, the
        # Shopify order-screening Worker, the Telegram widget. Every one of those lines is an UPPER
        # bound on that spend (a known-bad or cached URL never reaches VT), so a small number here
        # rules the composite out and a large one names it.
        ("composite-check requests (upper bound on VT fallback spend)", API, "composite-check signals="),
        ("VT fallback skipped or failed (no key, quota, or upstream error)", API, "VT fallback"),
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
    # WHO. The request line carries caller=<label> only after the 2026-10-06 build; before
    # it every anonymous caller was "-", so for an earlier day this section can show the
    # shape (one caller or none) but not identify anyone.
    callers = {}
    for label, term in (("/v1/result", "path=/v1/result"), ("/v1/payg/result", "path=/v1/payg/result")):
        rows, _, st = run(logs, API, f'filter @message like "{term}" | parse @message "caller=*" as c '
                          '| stats count() as n by c | sort n desc | limit 10', s, e)
        callers[label] = rows
        print(f"== {label} requests by caller  [{st}]")
        print("   ('-' = no caller label: a day before the label existed, or a request with no source IP)")
        for r in rows:
            print(f"   {r.get('n'):>5}  {r.get('c') or '-'}")
        print()
    rows, _, st = run(logs, API, 'filter @message like "vt_call surface=" | parse @message "surface=* kind=* caller=*" '
                      'as surf, kind, c | stats count() as n by surf, c | sort n desc | limit 10', s, e)
    print(f"== VT requests actually spent, by surface and caller  [{st}]")
    for r in rows:
        print(f"   {r.get('n'):>5}  {r.get('surf')}  {r.get('c')}")

    print("\n== VERDICT ON THE SCRAPER THEORY (a reading aid, not a measurement)")
    result_total = sum(t for lbl, t, _ in summary if lbl.startswith("GET /v1/result") or lbl.startswith("GET /v1/payg/result"))
    ranked = sorted((int(r.get("n") or 0) for rows_ in callers.values() for r in rows_), reverse=True)
    if result_total < 100:
        print(f"   {result_total} result requests: too few to have spent a 500-request day. The theory is NOT supported;")
        print("   look at the checkemail and WhatsApp rows above instead.")
    else:
        top = ranked[0] if ranked else 0
        labelled = any((r.get("c") or "-") != "-" for rows_ in callers.values() for r in rows_)
        print(f"   {result_total} result requests, each one VT request before the fix: enough to drain the day by themselves.")
        if not labelled:
            print("   They carry no caller label, so WHO cannot be read from this day. Volume says the leak was big enough;")
            print("   it does not say a scraper did it. The label exists from the 2026-10-06 build, so the next spike will say.")
        elif top >= 0.6 * result_total:
            print(f"   One caller made {top} of them: consistent with a single scraper or a stuck client.")
        else:
            print("   Spread across many callers: consistent with a crawler pool or broad probing, not one source.")
    print("\n== SUMMARY (lower bounds; polls are not logged)")
    for label, total, st in summary:
        print(f"   {total:>5}  {label}  [{st}]")
    print("   Telegram /scan: no countable log line. checkemail@: appears inside the scan-url rows above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
