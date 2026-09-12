#!/usr/bin/env python3
"""The Mini App funnel, end to end, from the logs the code already writes.

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30

It reads CloudWatch Logs INSIGHTS, so the identity running it needs
logs:StartQuery, logs:GetQueryResults and logs:StopQuery. A refusal comes back
named -- ERROR AccessDeniedException against the group that refused -- and is
never rendered as a zero. Progress goes to stderr, one line per query, because
a long silence is exactly what made the previous version look broken.

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
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTES_FILE = ROOT / "miniapp_routes.json"
SNAPSHOT_DIR = ROOT / "miniapp_funnel_snapshots"

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


def load_routes() -> list:
    """The canonical route table. A missing or unparseable file RAISES.

    Falling back to a built-in list would be the source_arrivals.py defect
    exactly: that tool's first parse silently skipped _SOURCE_BANNERS and
    returned a plausible-looking 117 keys with every real banner missing, so it
    would have reported three live channels as UNREGISTERED. A route table that
    quietly degrades reports a working channel as dead, and a zero from a
    measurement tool gets acted on.
    """
    if not ROUTES_FILE.exists():
        raise SystemExit(f"ERROR: {ROUTES_FILE} is missing. It is the source of "
                         "truth for route keys and this tool cannot guess them.")
    data = json.loads(ROUTES_FILE.read_text())
    routes = data.get("routes") or []
    if not routes:
        raise SystemExit(f"ERROR: {ROUTES_FILE} parsed but holds no routes. "
                         "Reporting every channel as zero on this would be a "
                         "false absence.")
    return routes, data.get("loop_keys") or []


# Every log line that carries a route key, and the group it lives in. The Mini
# App reaches the API through check(), which routes URLs to /v1/link-check and
# EVERY address -- TON included -- to /v1/wallet-risk. /v1/ton-address is never
# called from the app, so a source on it alone measures nothing here.
ROUTE_SOURCES = [
    ("/aws/lambda/relayshield-api", "source="),
    ("/aws/lambda/relayshield-developer-signup", "developer-signup request"),
]
_ROUTE_RX = re.compile(r"source=(tg-miniapp[a-z0-9-]*)")


# ---------------------------------------------------------------------------
# WHY THIS TOOL USES LOGS INSIGHTS AND NOT filter_log_events, WHICH IS WHAT IT
# SHIPPED WITH AND IS WHY IT PRINTED ITS HEADER AND THEN NOTHING ELSE.
#
# Reported twice as "I'm still getting no reply to your terminal command". The
# output was not swallowed and nothing raised: the run printed the header and
# then sat inside a pagination loop for longer than anyone was prepared to
# wait. filter_log_events is a SCAN. It returns a nextToken to continue walking
# log streams even when the page it just returned held no matching events at
# all, so a rare pattern over 30 days of /aws/lambda/relayshield-api -- the
# busiest group we have -- is thousands of sequential round trips before the
# first number can be printed. Eight such sweeps run before any output.
#
# Insights does the filter server-side and returns the matching lines in one
# query, so the same question costs one round trip plus a short poll.
#
# THE REGEXES ARE NOT DUPLICATED INTO INSIGHTS' OWN parse SYNTAX, DELIBERATELY.
# The query filters on the coarse substring and the EXISTING Python regex still
# does the matching, client-side, exactly as before. Re-expressing each stage
# regex as an Insights `parse` would be two things that must agree with nothing
# checking that they do, which is the shape that has cost this repo four
# separate false absences -- and a measurement tool's wrong answer gets acted
# on.
INSIGHTS_LIMIT = 10000        # Insights' own hard cap on rows returned
INSIGHTS_TIMEOUT_S = 180
INSIGHTS_POLL_S = 1.0


def _like(term: str) -> str:
    """One substring predicate, quoted the way Insights wants it."""
    esc = term.replace("\\", "\\\\").replace('"', '\\"')
    return f'@message like "{esc}"'


def run_insights(logs, group, query, start_ms, end_ms,
                 limit=None, timeout=None):
    """(rows, statistics, status). rows are dicts of field name -> value.

    status is the honest one and is never collapsed:
      OK            the query completed
      NO LOG GROUP  the group does not exist. NOT zero.
      TIMEOUT       we stopped waiting. NOT zero, and NOT a result.
      QUERY FAILED  Insights returned Failed/Cancelled
      ERROR <code>  anything else, named
    """
    import time
    from botocore.exceptions import ClientError
    # Read the caps at CALL time, not as default arguments bound at import.
    # A default argument cannot be adjusted by a caller or a test, and the cap
    # is exactly the branch that decides whether a number is a count or a
    # floor -- which is the one branch that must be exercisable.
    limit = INSIGHTS_LIMIT if limit is None else limit
    timeout = INSIGHTS_TIMEOUT_S if timeout is None else timeout
    print(f"  querying {group} ...", file=sys.stderr, flush=True)
    try:
        qid = logs.start_query(logGroupName=group,
                               startTime=int(start_ms // 1000),
                               endTime=int(end_ms // 1000),
                               queryString=query,
                               limit=limit)["queryId"]
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "ResourceNotFoundException":
            return [], {}, "NO LOG GROUP"
        return [], {}, f"ERROR {code}"
    deadline = time.time() + timeout
    while True:
        resp = logs.get_query_results(queryId=qid)
        status = resp.get("status")
        if status == "Complete":
            rows = [{f["field"]: f.get("value") for f in row}
                    for row in resp.get("results", [])]
            return rows, resp.get("statistics") or {}, "OK"
        if status in ("Failed", "Cancelled", "Timeout"):
            return [], {}, "QUERY FAILED"
        if time.time() >= deadline:
            try:
                logs.stop_query(queryId=qid)
            except Exception:
                pass
            return [], {}, "TIMEOUT"
        time.sleep(INSIGHTS_POLL_S)


def group_window(logs, group, start_ms, end_ms, cache):
    """(event_count, earliest_ms, status) for one log group, cached per run.

    This is what finally separates the three findings the docstring has always
    claimed to separate and the old code could not. filter_log_events answered
    one question -- did anything match -- so a function that had not run at all
    and a function that ran constantly without ever matching both came back as
    "ZERO". They are different problems with different fixes.

    It also gives a better window: the earliest event in the GROUP is what the
    retention actually held, where the earliest MATCHING event is a fact about
    the filter. The window section is a claim about retention, so it wants the
    first.
    """
    if group not in cache:
        rows, _stats, status = run_insights(
            logs, group, "stats count(*) as n, min(@timestamp) as first_ms",
            start_ms, end_ms, limit=1)
        if status != "OK":
            cache[group] = (None, None, status)
        else:
            n, first = 0, None
            if rows:
                try:
                    n = int(float(rows[0].get("n") or 0))
                except (TypeError, ValueError):
                    n = 0
                raw = rows[0].get("first_ms")
                try:
                    first = int(float(raw)) if raw else None
                except (TypeError, ValueError):
                    first = None
            cache[group] = (n, first, "OK")
    return cache[group]


def pull_routes(logs, start_ms, end_ms, keys, window_cache):
    """Counts per route key, plus what arrived carrying a key we do not know.

    The unknown bucket is printed loudly for the same reason source_arrivals.py
    prints `unmatched:` first: each one is a live link pointing at a key that
    does not exist, and it is invisible everywhere else -- the page renders, the
    check answers, nothing errors, and the attribution is simply gone.
    """
    counts, unknown, reachable = Counter(), Counter(), True
    for group, pattern in ROUTE_SOURCES:
        n, _first, wstatus = group_window(logs, group, start_ms, end_ms, window_cache)
        if wstatus != "OK":
            reachable = False
            continue
        if not n:
            continue
        query = ("fields @message | filter "
                 + _like(pattern) + " and " + _like("tg-miniapp"))
        rows, stats, status = run_insights(logs, group, query, start_ms, end_ms)
        if status != "OK":
            reachable = False
            continue
        for r in rows:
            m = _ROUTE_RX.search(r.get("@message") or "")
            if not m:
                continue
            k = m.group(1)
            (counts if k in keys else unknown)[k] += 1
        # A capped page is a floor, and a floor presented as a count is the
        # confident-wrong-number failure. Say so rather than under-reporting.
        if len(rows) >= INSIGHTS_LIMIT and _matched(stats) > len(rows):
            reachable = False
    return counts, unknown, reachable


def _matched(stats) -> int:
    try:
        return int(float(stats.get("recordsMatched") or 0))
    except (TypeError, ValueError):
        return 0


def pull_stage(logs, group, pattern, rx, start_ms, end_ms, window_cache):
    """(count, breakdown, earliest_ms, status). status is the honest one."""
    counts = Counter()
    n, earliest, wstatus = group_window(logs, group, start_ms, end_ms, window_cache)
    if wstatus != "OK":
        # NOT zero. The function may not exist yet, which for
        # relayshield-watchlist-monitor is the expected state until
        # tools/create_watchlist_monitor.sh has been run.
        return 0, counts, None, wstatus
    if not n:
        return 0, counts, None, "NEVER INVOKED"
    query = "fields @message | filter " + _like(pattern)
    rows, stats, status = run_insights(logs, group, query, start_ms, end_ms)
    if status != "OK":
        return 0, counts, earliest, status
    total = 0
    for r in rows:
        m = rx.search(r.get("@message") or "")
        if m:
            total += 1
            counts[m.group(1)] += 1
    if len(rows) >= INSIGHTS_LIMIT and _matched(stats) > len(rows):
        # More matched than Insights will return. total is a FLOOR.
        return total, counts, earliest, "CAPPED"
    if not total:
        return 0, counts, earliest, "ZERO"
    return total, counts, earliest, "OK"


def print_routes(routes, loop_keys) -> int:
    """The table and the exact link for each. No AWS, so it works anywhere."""
    print("Mini App discovery routes, ranked. Source: miniapp_routes.json\n")
    for r in sorted(routes, key=lambda x: x["rank"]):
        aud = f"{r['audience']:,}" if r.get("audience") else "unmeasured"
        print(f"{r['rank']:>2}. {r['destination']}   (audience {aud})")
        if r["key"]:
            print(f"    link  https://t.me/relayshield_bot/idcheck?startapp={r['key']}")
            print(f"    before  python3 tools/miniapp_funnel.py --snapshot before-{r['id']}")
            print(f"    after   python3 tools/miniapp_funnel.py --compare before-{r['id']}")
        else:
            print("    NO KEY, ON PURPOSE.")
        if r.get("why_first"):
            print(f"    {r['why_first']}")
        print(f"    {r['audience_note']}")
        print()
    print("Keys that are NOT routes, and are counted separately:")
    for lk in loop_keys:
        print(f"  {lk['key']}: {lk['what']}")
        print(f"    {lk['why_not_a_route']}")
    return 0


def save_snapshot(current: dict, label: str) -> None:
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    path = SNAPSHOT_DIR / f"{re.sub(r'[^a-z0-9-]', '-', label.lower())}.json"
    if path.exists():
        # NEVER silently. A baseline overwritten after the submission has
        # already run turns the before-and-after into a comparison of a number
        # with itself, and it reads as "the channel did nothing".
        print(f"\nREFUSING to overwrite {path.name}: a snapshot with this label")
        print("already exists. If the first one was taken at the wrong moment,")
        print("delete it by hand -- deleting a baseline should be a decision.")
        return
    path.write_text(json.dumps(current, indent=2) + "\n")
    try:
        shown = path.relative_to(ROOT)
    except ValueError:
        # SNAPSHOT_DIR can be pointed outside the repo, and a cosmetic path
        # calculation must never be the thing that loses a saved baseline.
        shown = path
    print(f"\nSnapshot saved: {shown}")
    print("COMMIT IT. The container it was generated in is reclaimed, and a")
    print("baseline that exists only on one machine is not a baseline.")


def print_comparison(current: dict, label: str) -> None:
    path = SNAPSHOT_DIR / f"{re.sub(r'[^a-z0-9-]', '-', label.lower())}.json"
    if not path.exists():
        print(f"\nNo snapshot named {path.name}. Nothing to compare against --")
        print("which is a missing baseline, NOT a result of zero.")
        return
    before = json.loads(path.read_text())
    print(f"\nDelta against {path.name} (taken {before.get('generated_at', '?')[:16]}):")
    print("  WINDOW CAVEAT, and it is the one that would make these numbers a")
    print("  lie: both runs count a rolling --days window back from NOW, so a")
    print("  delta is only the submission's effect if the two runs are CLOSE")
    print("  together relative to that window. Comparing a --days 30 baseline")
    print("  taken five weeks ago measures the window sliding, not the channel.")
    for section in ("stages", "routes"):
        rows = []
        for k, now in (current.get(section) or {}).items():
            was = (before.get(section) or {}).get(k)
            if not isinstance(now, int) or not isinstance(was, int):
                continue
            if now - was:
                rows.append((k, was, now))
        if rows:
            print(f"  {section}:")
            for k, was, now in sorted(rows, key=lambda r: r[2] - r[1], reverse=True):
                print(f"    {k.ljust(28)} {was:>6} -> {now:>6}   {now - was:+d}")
        else:
            print(f"  {section}: no change")
    newk = set(current.get("unknown_route_keys") or {}) - set(before.get("unknown_route_keys") or {})
    if newk:
        print("  NEW UNKNOWN ROUTE KEYS since the baseline, which means a link")
        print("  shipped carrying a key nobody registered:")
        for k in sorted(newk):
            print(f"    {k}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--breakdown", action="store_true",
                    help="show the per-value split within each stage")
    ap.add_argument("--snapshot", metavar="LABEL",
                    help="save this run under miniapp_funnel_snapshots/LABEL.json. "
                         "Run it BEFORE a submission, with the route id as the "
                         "label: --snapshot before-trendingapps")
    ap.add_argument("--compare", metavar="LABEL",
                    help="diff this run against a saved snapshot and print the "
                         "DELTA. Run it after a submission: --compare before-trendingapps")
    ap.add_argument("--list-routes", action="store_true",
                    help="print the route table and the exact link for each, "
                         "then exit. No AWS needed.")
    args = ap.parse_args()

    routes, loop_keys = load_routes()

    if args.list_routes:
        return print_routes(routes, loop_keys)

    try:
        import boto3
    except ImportError:
        raise SystemExit("ERROR: boto3 missing. Use ~/.rsvenv/bin/python on the Mac.")

    assert_account()
    logs = boto3.client("logs", region_name=REGION)
    now = datetime.now(timezone.utc)
    end_ms = int(now.timestamp() * 1000)
    start_ms = int((now - timedelta(days=args.days)).timestamp() * 1000)
    window_cache = {}

    print(f"RelayShield Mini App funnel, {args.days} days requested\n")
    # Progress goes to stderr, per query, because this reads several log groups
    # and a long silence after the header is what made the old version look
    # broken. A tool that is working and a tool that is hung must not produce
    # the same thing on screen.
    rows = []
    for label, group, pattern, rx, meaning in STAGES:
        total, counts, earliest, status = pull_stage(
            logs, group, pattern, rx, start_ms, end_ms, window_cache)
        rows.append((label, total, counts, earliest, status, meaning))

    widest = max(len(r[0]) for r in rows)
    for label, total, counts, earliest, status, meaning in rows:
        if status == "OK":
            shown = str(total)
        elif status == "ZERO":
            shown = "0"
        elif status == "CAPPED":
            shown = f">={total}"
        else:
            shown = status
        print(f"  {label.ljust(widest)}   {shown:>8}")
        if status == "NO LOG GROUP":
            print(f"  {' ' * widest}            ^ the log group does not exist, so the")
            print(f"  {' ' * widest}              function has never run. NOT a")
            print(f"  {' ' * widest}              measurement of the channel.")
        elif status == "NEVER INVOKED":
            print(f"  {' ' * widest}            ^ the group exists and held NO events at")
            print(f"  {' ' * widest}              all in this window. The function is idle,")
            print(f"  {' ' * widest}              which is not the same as nothing matching.")
        elif status == "CAPPED":
            print(f"  {' ' * widest}            ^ more lines matched than Insights will")
            print(f"  {' ' * widest}              return ({INSIGHTS_LIMIT}). This is a FLOOR, not a")
            print(f"  {' ' * widest}              count. Narrow --days to get a real number.")
        elif status == "TIMEOUT":
            print(f"  {' ' * widest}            ^ the query did not finish in")
            print(f"  {' ' * widest}              {INSIGHTS_TIMEOUT_S}s. NOT zero and NOT a result.")
        elif total == 0:
            print(f"  {' ' * widest}            ^ zero means: {meaning}")
        elif total < DEFENSIBLE_FLOOR:
            print(f"  {' ' * widest}            ^ under {DEFENSIBLE_FLOOR}: real, and NOT")
            print(f"  {' ' * widest}              defensible enough to quote anywhere.")
        if args.breakdown and counts:
            for k, v in counts.most_common(8):
                print(f"  {' ' * widest}              {k}: {v}")

    # ---- per route ----------------------------------------------------
    keys = {r["key"] for r in routes if r["key"]}
    route_counts, unknown, reachable = pull_routes(
        logs, start_ms, end_ms, keys, window_cache)

    print("\nPer discovery route:")
    if not reachable:
        print("  a log group is missing, so these counts are INCOMPLETE and not a"
              " measurement of any channel.")
    if unknown:
        # First and loudly. Each is a live link naming a key nothing knows.
        print("  UNKNOWN ROUTE KEYS -- a published link carries a key that is not")
        print("  in miniapp_routes.json, so its arrivals are unattributed:")
        for k, v in unknown.most_common():
            print(f"    {k}: {v}")
        print()
    for r in sorted(routes, key=lambda x: x["rank"]):
        key = r["key"]
        if not key:
            print(f"  {r['rank']:>2}. {r['destination'][:44].ljust(46)} NOT SHIPPED (decision)")
            continue
        n = route_counts.get(key, 0)
        aud = f"{r['audience']:,}" if r.get("audience") else "unmeasured"
        flag = ""
        if n == 0:
            flag = "  <-- not submitted yet, or submitted and nothing came"
        elif n < DEFENSIBLE_FLOOR:
            flag = "  <-- real, not quotable"
        print(f"  {r['rank']:>2}. {r['destination'][:44].ljust(46)} {n:>7}   "
              f"audience {aud}{flag}")

    print("\n  A zero is AMBIGUOUS on its own. 'We have not submitted here yet'")
    print("  and 'we submitted and nobody came' are different findings with")
    print("  different fixes, and only the snapshot labels tell them apart --")
    print("  which is what --snapshot before-<id> is for.")

    current = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days_requested": args.days,
        "stages": {label.split()[0]: (total if status in ("OK", "ZERO") else status)
                   for label, total, _c, _e, status, _m in rows},
        "routes": {r["key"]: route_counts.get(r["key"], 0)
                   for r in routes if r["key"]},
        "unknown_route_keys": dict(unknown),
    }

    if args.compare:
        print_comparison(current, args.compare)
    if args.snapshot:
        save_snapshot(current, args.snapshot)

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
