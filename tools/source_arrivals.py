#!/usr/bin/env python3
"""Count attributed arrivals by key, on either of the two surfaces that log one.

    tools/source_arrivals.py                    the developers page (default)
    tools/source_arrivals.py --surface bot      t.me/relayshield_bot ?start=SRC_

The two are different log groups with different attribution mechanisms; the
SURFACES table below says how they differ and why that difference decides what
an absence means on each. The rest of this docstring was written for the
developers surface and holds for both.

WHY THIS EXISTS, and it is not bookkeeping. Every distribution decision this
repo makes rests on an unmeasured premise. "The pre-commit hook was a good
discovery surface, so an IDE widget would be too" is a reasonable-sounding
sentence, and nothing in this repo can currently say whether its first half is
true. `rsscan` and `rsscan-deps` have been registered keys in _SOURCE_BANNERS
since 2026-09-03, so the arrivals ARE attributable and always have been. Nobody
has ever counted them.

MEASUREMENT DOCTRINE APPLIES TO OUR OWN FUNNEL, not just to the corpus. So this
tool is deliberately built to make an absence look like an absence:

  * A key with no arrivals is reported as ZERO ARRIVALS, and a key that is not
    registered at all is reported as UNREGISTERED. They are different findings
    with different fixes -- the first is a channel that did not work, the second
    is a link that was published without its key and whose arrivals were logged
    as `unmatched:` and rendered no banner. Conflating them is FD-8, four months
    of it.
  * The window reported is the window OBSERVED, never the window requested. If
    log retention is 30 days and you ask for 90, you get 30 and it says so. A
    count over a window you did not actually have is a wrong number presented
    with confidence, which this repo has paid for twice.
  * `unmatched:` rows are printed FIRST and loudly, because each one is a live
    link pointing at a key that does not exist. That is invisible everywhere
    else: the page renders, nothing errors, and the attribution is simply gone.

THIS RUNS ON THE MAC. The container's AWS credentials are placeholders --
get_caller_identity returns InvalidClientTokenId -- so per the standing rule the
check moves rather than disappearing:

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/source_arrivals.py

WITHOUT AWS_PROFILE=relayshield this resolves to 620534471984, the pre-audit
account, where the log group does not exist and the read returns
ResourceNotFoundException -- which looks exactly like "no arrivals" and is not.
The script asserts the account before it reads anything, for that reason.

ONE THING THE NUMBERS CANNOT TELL YOU, and it is stated in the output rather
than left for the reader to trip over: relayshield-developer-signup had NO
DEPLOY PATH until 2026-09-03. Keys registered before that date only began
resolving when the reconciled function deployed. So a low count on an old key
may be a channel that failed, or a key that was inert for the period it was
supposed to be measuring. Check the key's registration date against the window
before concluding anything about the channel.
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACCOUNT = "239677749008"

# TWO SURFACES, ONE TOOL, AND THAT IS DELIBERATE RATHER THAN TIDY.
#
# Added 2026-09-17, when submitting @relayshield_bot to bot directories turned
# out to be unmeasurable: tools/miniapp_funnel.py's BOT stage matches
# `acquisition source=(miniapp|tg-miniapp[a-z-]*)`, so it counts Mini App
# arrivals and NOTHING ELSE, and this tool read only the developer-signup log
# group. Five bot directory submissions would have produced five numbers nobody
# could separate -- FD-8's shape, caught before the links shipped rather than
# four months after.
#
# A SECOND TOOL WAS THE OBVIOUS MOVE AND IT IS THE WRONG ONE. This repo has
# paid four times for two files that must agree with nothing checking that they
# do (the pattern tables, LAMBDA_MAP against the invoke policy, the three route
# lists, the watchlist secret name). A second counter would have drifted from
# this one's doctrine -- the observed window, ZERO separated from UNMEASURED --
# and the drift would be invisible because both would keep printing numbers.
#
# THE TWO SURFACES ATTRIBUTE DIFFERENTLY AND THE DIFFERENCE IS LOAD-BEARING:
#
#   developers  ?source=<key> on api.relayshield.net/developers. The key is
#               GATED: _SOURCE_BANNERS decides, and an unregistered key logs
#               `unmatched:<key>` and renders no banner. So an unregistered key
#               is recoverable after the fact -- the unmatched row names it.
#
#   bot         ?start=SRC_<key> on t.me/relayshield_bot. There is NO allowlist:
#               relayshield_telegram_webhook.py accepts any key up to 32
#               characters and logs it verbatim. So a bot key needs no
#               registration anywhere -- and a link published WITHOUT the
#               SRC_ suffix logs nothing at all, leaves no unmatched row, and is
#               indistinguishable from organic /start traffic forever. On this
#               surface the unrecoverable mistake is omission, not registration.
SURFACES = {
    "developers": {
        "log_group": "/aws/lambda/relayshield-developer-signup",
        # The line relayshield_developer_signup.py emits on every request. The
        # source value is the RAW parameter, not the banner variant it maps to,
        # so n8n-onboarding and n8n-offboarding stay distinguishable here even
        # though both render the same banner.
        "filter": "developer-signup request",
        "line": re.compile(r"developer-signup request .*?\bsource=(\S+)"),
        "unit": "arrivals on the developers page, not signups and not revenue",
        "gated": True,
    },
    "bot": {
        "log_group": "/aws/lambda/relayshield-telegram-webhook",
        # relayshield_telegram_webhook.py, the SRC_ branch. It logs the source
        # and a HASHED chat id, then falls through to the ordinary welcome:
        # the parameter is attribution only and never changes what the user
        # sees.
        "filter": "acquisition source=",
        "line": re.compile(r"acquisition source=(\S+)"),
        "unit": "bot /start arrivals that CARRIED a SRC_ key, not total signups",
        "gated": False,
    },
}


def registered_keys() -> set:
    """Read _SOURCE_BANNERS and _SOURCE_ALIASES out of the handler with ast.

    Parsed rather than imported: importing the handler pulls boto3 and its
    module-level clients, which is a dependency this tool does not need and a
    credential path it should not touch.

    BOTH ast.Assign AND ast.AnnAssign, and the second one is not defensive
    padding -- the first version of this function handled only Assign and
    therefore read _SOURCE_ALIASES and silently skipped _SOURCE_BANNERS, which
    is declared as `_SOURCE_BANNERS: dict[str, ...] = {`. It returned a
    plausible-looking 117 keys with every real banner missing, so the tool would
    have reported `rsscan`, `tg-widget` and `tg-miniapp` as UNREGISTERED when
    all three are registered. Nothing errored. That is the quiet-alarm shape and
    it was caught only by running the thing and reading the output against a
    grep, which is rule 14 applied to my own tool rather than to a command.

    So this asserts a floor rather than trusting the walk: if either table comes
    back empty the parse is wrong, and an empty table must never be presented as
    "no keys are registered".
    """
    import ast

    src = (ROOT / "relayshield_developer_signup.py").read_text()
    tree = ast.parse(src)
    found = {"_SOURCE_BANNERS": set(), "_SOURCE_ALIASES": set()}

    def collect(name, value):
        if name in found and isinstance(value, ast.Dict):
            for k in value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    found[name].add(k.value)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                collect(getattr(target, "id", None), node.value)
        elif isinstance(node, ast.AnnAssign):
            collect(getattr(node.target, "id", None), node.value)

    for name, keys in found.items():
        if not keys:
            raise SystemExit(
                f"ERROR: parsed 0 keys out of {name}. The parse is wrong, not the\n"
                "       table. Reporting keys as UNREGISTERED on this would be a\n"
                "       false absence, which is worse than no answer.")
    return found["_SOURCE_BANNERS"] | found["_SOURCE_ALIASES"]


def assert_account() -> None:
    import boto3
    from botocore.exceptions import ClientError

    try:
        got = boto3.client("sts").get_caller_identity()["Account"]
    except ClientError as e:
        raise SystemExit(f"ERROR: STS: {e.response['Error']['Code']}")
    if got != ACCOUNT:
        raise SystemExit(
            f"ERROR: this is account {got}, not {ACCOUNT}.\n"
            f"       {ACCOUNT} is the ONLY RelayShield account. Re-run with\n"
            "       AWS_PROFILE=relayshield. A read against the wrong account\n"
            "       returns ResourceNotFoundException, which reads as 'no data'\n"
            "       and is not.")


def pull(surface: str, days: int):
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        raise SystemExit("ERROR: boto3 missing. Use ~/.rsvenv/bin/python on the Mac.")

    assert_account()
    spec = SURFACES[surface]
    log_group, line_rx = spec["log_group"], spec["line"]
    logs = boto3.client("logs", region_name="us-east-1")
    start = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)

    counts, total, earliest, token = Counter(), 0, None, None
    try:
        while True:
            kw = dict(logGroupName=log_group, startTime=start,
                      filterPattern=spec["filter"])
            if token:
                kw["nextToken"] = token
            resp = logs.filter_log_events(**kw)
            for ev in resp.get("events", []):
                ts = ev.get("timestamp")
                if ts and (earliest is None or ts < earliest):
                    earliest = ts
                m = line_rx.search(ev.get("message", ""))
                if not m:
                    continue
                total += 1
                src = m.group(1)
                if src != "-":
                    counts[src] += 1
            token = resp.get("nextToken")
            if not token:
                break
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "ResourceNotFoundException":
            raise SystemExit(
                f"ERROR: log group {log_group} not found in {ACCOUNT}.\n"
                "       That is a missing log group, NOT zero arrivals. The\n"
                "       function may never have been invoked, or the name has\n"
                "       changed. Do not read this as a measurement.")
        raise SystemExit(f"ERROR: {code}: {e.response['Error'].get('Message','')[:200]}")

    return counts, total, earliest


def bot_route_keys() -> set:
    """Read the bot directory keys out of bot_directories.json.

    Unlike registered_keys() this is NOT a gate that the running code consults.
    The webhook accepts any SRC_ key. This file records which ones we have
    actually published, which is what makes ZERO ARRIVALS mean something: a key
    we submitted somewhere and that produced nothing is a channel result, and a
    key nobody has published is not a measurement at all.
    """
    path = ROOT / "bot_directories.json"
    if not path.exists():
        return set()
    data = json.loads(path.read_text())
    return {r["key"] for r in data.get("routes", []) if r.get("key")}


def report(counts, total, earliest, days, want, surface) -> int:
    spec = SURFACES[surface]
    gated = spec["gated"]
    print(f"surface       : {surface}")
    print(f"log group     : {spec['log_group']}")
    if earliest:
        seen = datetime.fromtimestamp(earliest / 1000, tz=timezone.utc)
        observed = (datetime.now(timezone.utc) - seen).days
        print(f"window asked  : last {days} days")
        print(f"window OBSERVED: {observed} days (earliest event {seen:%Y-%m-%d})")
        if observed < days - 1:
            print("                 ^ shorter than asked. Log retention, not a quiet"
                  " period.\n                   Every count below covers the OBSERVED"
                  " window only.")
    else:
        print(f"window asked  : last {days} days")
        print("window OBSERVED: no events at all")
    print(f"requests      : {total}")
    print(f"attributed    : {sum(counts.values())}")
    print()

    if not total:
        print("NO REQUESTS LOGGED. That is UNMEASURED, not zero traffic -- check")
        print("that the window is inside log retention before concluding anything.")
        return 1

    unmatched = {k: v for k, v in counts.items() if k.startswith("unmatched:")}
    if unmatched and gated:
        print("UNMATCHED KEYS -- each one is a LIVE LINK pointing at a key that does")
        print("not exist. The page renders, nothing errors, and the attribution is")
        print("silently gone. Register the key, then re-run.")
        for k, v in sorted(unmatched.items(), key=lambda kv: -kv[1]):
            print(f"  {v:>6}  {k}")
        print()

    rest = {k: v for k, v in counts.items() if not k.startswith("unmatched:")}
    if rest:
        print("ARRIVALS BY KEY")
        for k, v in sorted(rest.items(), key=lambda kv: -kv[1]):
            print(f"  {v:>6}  {k}")
        print()

    if want:
        print("KEYS ASKED ABOUT")
        known = registered_keys() if gated else bot_route_keys()
        for k in want:
            n = counts.get(k, 0)
            if k not in known and gated:
                print(f"  {k}: UNREGISTERED. Not in _SOURCE_BANNERS or _SOURCE_ALIASES,")
                print(f"     so arrivals on it logged as unmatched:{k} and rendered no")
                print("     banner. This is not a measurement of the channel.")
            elif k not in known:
                print(f"  {k}: NOT IN bot_directories.json. The webhook would have")
                print("     logged it fine -- there is no allowlist on this surface -- so")
                print(f"     {n} is a real count. But nothing records where this key was")
                print("     published, so it cannot be read as a result for any channel.")
            elif n == 0:
                print(f"  {k}: ZERO ARRIVALS over the observed window.")
                print("     BEFORE reading that as a channel that did not work, rule out")
                print("     the failure that looks identical: a listing that points at a")
                print("     BARE t.me/relayshield_bot logs nothing, so a live and working")
                print("     listing reads as zero here. Open the listing and check the")
                print("     link carries ?start=SRC_ before concluding anything.")
            else:
                print(f"  {k}: {n}")
        print()

    if not gated:
        print("EVERY COUNT ABOVE EXCLUDES ARRIVALS WITH NO SRC_ KEY, which is most of")
        print("them. This measures attributed arrivals, never total bot traffic, and")
        print("the two must not be compared with each other.")
        print()

    print(f"Counts are {spec['unit']}.")
    print("Do not quote any of these externally: MEASUREMENT DOCTRINE applies to our")
    print("own funnel exactly as it does to the corpus.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--surface", choices=sorted(SURFACES), default="developers",
                    help="developers = ?source= on the developers page (default). "
                         "bot = ?start=SRC_ arrivals on t.me/relayshield_bot. "
                         "They are different log groups and different attribution "
                         "mechanisms; see the SURFACES comment.")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--key", action="append", default=[],
                    help="Report this key explicitly, including when it is zero "
                         "or unregistered. Repeatable.")
    ap.add_argument("--list-registered", action="store_true",
                    help="Print every known key for the surface and exit. Needs no AWS.")
    args = ap.parse_args()

    if args.list_registered:
        keys = registered_keys() if SURFACES[args.surface]["gated"] else bot_route_keys()
        for k in sorted(keys):
            print(k)
        return 0

    counts, total, earliest = pull(args.surface, args.days)
    return report(counts, total, earliest, args.days, args.key, args.surface)


if __name__ == "__main__":
    sys.exit(main())
