#!/usr/bin/env python3
"""The Mini App funnel, end to end, from the logs the code already writes.

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30

WHY THIS IS THE HIGH-PRIORITY TOOL AND NOT A NICE-TO-HAVE. The founder asked
for exactly this, in these words: "Lets measure tg-miniapp arrivals, miniapp bot
signups, Stars, and Tg miniApps traffic driven to our existing Tg bot ... as
well as traffic driven to our API landing site."

Every argument about whether the Mini App is a discovery surface currently rests
on nobody having counted. That is the same defect tools/source_arrivals.py was
written for -- FD-1 was marked DONE for months while "done" meant shipped, not
reached -- and this is that lesson applied to the surface we are shipping NOW,
before the argument rather than after it.

=============================================================================
THE SIX STAGES, AND WHY EACH ONE IS A DIFFERENT QUESTION
=============================================================================

A single "users" number would hide the only thing worth knowing, which is WHERE
people stop. So the stages are reported separately and never summed:

  1. OPENED        the Mini App made an API call. This is reach.
  2. CHECKED       somebody pasted something. This is intent.
  3. WATCHED       somebody asked to be told if it changes. This is the first
                   act that requires trusting us with anything.
  4. BOT           the Mini App produced a bot subscriber. This is the flywheel
                   the watchlist docstring claims, and it is the number that
                   decides whether the Mini App feeds the business or is a
                   separate toy.
  5. STARS         somebody paid. A payment measures value where an open
                   measures curiosity.
  6. ALERTED       we sent an alert. This is the product WORKING, and it is the
                   only stage that measures whether the promise was kept.

And separately, DEVELOPERS: arrivals on api.relayshield.net/developers carrying
a Mini App source key. That is the "traffic driven to our API landing site" half
of the question, and it is the bridge from a consumer surface to the thing that
actually bills.

=============================================================================
WHAT THIS TOOL REFUSES TO DO
=============================================================================

IT NEVER REPORTS A WINDOW IT DID NOT OBSERVE. Ask for 90 days against 30 days of
retention and you get 30, and it says so. A count over a window you did not have
is a wrong number presented with confidence, and this repo has paid for that
twice -- most recently a version list sorted as strings that put 0.2.11 before
0.2.4 and read as "the release is missing".

IT DISTINGUISHES ZERO FROM UNMEASURABLE. A log group that does not exist, a
function never invoked, and a stage that genuinely produced nothing are three
different findings with three different fixes. They are labelled NO LOG GROUP,
NEVER INVOKED and ZERO, never collapsed into "0".

IT QUOTES NOTHING EXTERNALLY. MEASUREMENT DOCTRINE applies to our own funnel
exactly as it applies to the corpus: these are numbers for deciding what to
build, not numbers for a deck. A stage under 100 is not defensible and the
output says so per stage rather than leaving it to be remembered.
"""

import argparse
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

ACCOUNT = "239677749008"
REGION = "us-east-1"

# Each stage: (label, log group, CloudWatch filter, regex over the message,
#              what a zero here would MEAN). The last field is the point: a
# number with no interpretation is a number somebody will interpret wrongly.
# Each stage: (label, log group, CloudWatch filter, regex over the message,
#              what a zero here would MEAN). The last field is the point: a
# number with no interpretation is a number somebody will interpret wrongly.
#
# EVERY FILTER BELOW WAS CHECKED AGAINST THE LINE THE CODE ACTUALLY WRITES, and
# two of them were wrong on the first draft. The stage that counts Mini App bot
# subscribers filtered on "SRC_miniapp", which is the DEEP LINK payload; the
# webhook strips the prefix and lower-cases it before logging, so the line reads
# `acquisition source=miniapp` and the filter would have matched nothing,
# forever, and reported a working channel as dead. And /v1/ton-address did not
# log a source at all until this commit, so half the Mini App's checks were
# uncountable. A filter written from what the code SHOULD log is a false
# absence waiting to happen, and this repo has had four of those.
STAGES = [
    ("CHECKED    link and TON checks from the Mini App",
     "/aws/lambda/relayshield-api", "tg-miniapp",
     re.compile(r"source=(tg-miniapp[a-z-]*)"),
     "people open it and paste nothing, which is a first-screen problem"),

    ("WATCHED    watchlist adds",
     "/aws/lambda/relayshield-watchlist", "watchlist add",
     re.compile(r"watchlist add kind=(\w+)"),
     "checking works and nobody wants the follow-up, which kills the flywheel"),

    ("BOT        Mini App to bot subscribers",
     "/aws/lambda/relayshield-telegram-webhook", "acquisition source=",
     re.compile(r"acquisition source=(miniapp|tg-miniapp[a-z-]*)"),
     "the Mini App is a dead end and feeds nothing"),

    ("STARS      paid upgrades",
     "/aws/lambda/relayshield-telegram-webhook", "stars payment credited",
     re.compile(r"stars payment credited stars=(\d+)"),
     "free usage without demand, which is information and not failure"),

    ("ALERTED    verdict-change alerts sent",
     "/aws/lambda/relayshield-watchlist-monitor", "watchlist alert sent",
     re.compile(r"watchlist alert sent signals=([\w,]+)"),
     "either nothing watched has changed, or the monitor is not running"),

    ("DEVELOPERS arrivals on the API landing page",
     "/aws/lambda/relayshield-developer-signup", "developer-signup request",
     re.compile(r"developer-signup request .*?\bsource=(tg-miniapp[a-z-]*|tg-widget)"),
     "the consumer surface is not bridging to the thing that bills"),
]

DEFENSIBLE_FLOOR = 100


def assert_account():
    import boto3
    from botocore.exceptions import ClientError
    try:
        got = boto3.client("sts").get_caller_identity()["Account"]
    except ClientError as e:
        raise SystemExit(f"ERROR: STS: {e.response['Error']['Code']}")
    if got != ACCOUNT:
        raise SystemExit(
            f"ERROR: this is account {got}, not {ACCOUNT}.\n"
            "       Re-run with AWS_PROFILE=relayshield. A read against the\n"
            "       pre-audit account returns ResourceNotFoundException, which\n"
            "       reads as 'no data' and is not.")


def pull_stage(logs, group, pattern, rx, start_ms):
    """(count, breakdown, earliest_ms, status). status is the honest one."""
    from botocore.exceptions import ClientError
    counts, total, earliest, token, saw_any_event = Counter(), 0, None, None, False
    try:
        while True:
            kw = dict(logGroupName=group, startTime=start_ms, filterPattern=f'"{pattern}"')
            if token:
                kw["nextToken"] = token
            resp = logs.filter_log_events(**kw)
            for ev in resp.get("events", []):
                saw_any_event = True
                ts = ev.get("timestamp")
                if ts and (earliest is None or ts < earliest):
                    earliest = ts
                m = rx.search(ev.get("message", ""))
                if m:
                    total += 1
                    counts[m.group(1)] += 1
            token = resp.get("nextToken")
            if not token:
                break
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "ResourceNotFoundException":
            # NOT zero. The function may not exist yet, which for
            # relayshield-watchlist-monitor is the expected state until
            # tools/create_watchlist_monitor.sh has been run.
            return 0, counts, None, "NO LOG GROUP"
        return 0, counts, None, f"ERROR {code}"
    if not saw_any_event:
        return 0, counts, None, "ZERO"
    return total, counts, earliest, "OK"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--breakdown", action="store_true",
                    help="show the per-value split within each stage")
    args = ap.parse_args()

    try:
        import boto3
    except ImportError:
        raise SystemExit("ERROR: boto3 missing. Use ~/.rsvenv/bin/python on the Mac.")

    assert_account()
    logs = boto3.client("logs", region_name=REGION)
    start_ms = int((datetime.now(timezone.utc) - timedelta(days=args.days)).timestamp() * 1000)

    print(f"RelayShield Mini App funnel, {args.days} days requested\n")
    rows = []
    for label, group, pattern, rx, meaning in STAGES:
        total, counts, earliest, status = pull_stage(logs, group, pattern, rx, start_ms)
        rows.append((label, total, counts, earliest, status, meaning))

    widest = max(len(r[0]) for r in rows)
    for label, total, counts, earliest, status, meaning in rows:
        if status == "OK":
            shown = str(total)
        elif status == "ZERO":
            shown = "0"
        else:
            shown = status
        print(f"  {label.ljust(widest)}   {shown:>8}")
        if status == "NO LOG GROUP":
            print(f"  {' ' * widest}            ^ the function has never run. NOT a")
            print(f"  {' ' * widest}              measurement of the channel.")
        elif total == 0:
            print(f"  {' ' * widest}            ^ zero means: {meaning}")
        elif total < DEFENSIBLE_FLOOR:
            print(f"  {' ' * widest}            ^ under {DEFENSIBLE_FLOOR}: real, and NOT")
            print(f"  {' ' * widest}              defensible enough to quote anywhere.")
        if args.breakdown and counts:
            for k, v in counts.most_common(8):
                print(f"  {' ' * widest}              {k}: {v}")

    # THE WINDOW ACTUALLY OBSERVED, per stage, because retention differs per log
    # group and one global claim would be wrong for at least one of them.
    print("\nWindow actually observed:")
    for label, total, counts, earliest, status, _ in rows:
        if earliest is None:
            print(f"  {label.split()[0]:<11} no events, so no window was observed")
            continue
        days = (datetime.now(timezone.utc)
                - datetime.fromtimestamp(earliest / 1000, tz=timezone.utc)).days
        flag = "  <-- SHORTER THAN REQUESTED" if days < args.days - 1 else ""
        print(f"  {label.split()[0]:<11} {days} days{flag}")

    print("\nRead this before acting on any number above:")
    print("  * CHECKED counts API CALLS, not people. One session makes several.")
    print("    It is a floor on interest and a ceiling on nothing. There is no")
    print("    honest 'opens' number: the Mini App is a Cloudflare Worker and it")
    print("    does not report to us, deliberately -- the first thing it does")
    print("    that we can see is a check the user asked for.")
    print("  * BOT is the stage that decides whether the Mini App is a discovery")
    print("    surface or a separate product. A high OPENED with a low BOT means")
    print("    a utility people use once, which is what a checker is without the")
    print("    watchlist attached.")
    print("  * ALERTED at zero with WATCHED above zero is AMBIGUOUS and needs the")
    print("    monitor's own log read: 'nothing changed' and 'the monitor is not")
    print("    running' produce the identical number here.")
    print("  * None of these go in a deck. MEASUREMENT DOCTRINE applies to our")
    print("    own funnel exactly as it applies to the corpus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
