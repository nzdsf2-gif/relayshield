#!/usr/bin/env python3
"""Count arrivals on api.relayshield.net/developers by ?source= key.

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
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_GROUP = "/aws/lambda/relayshield-developer-signup"
ACCOUNT = "239677749008"

# The line relayshield_developer_signup.py emits on every request. The source
# value is the RAW parameter, not the banner variant it maps to, so
# n8n-onboarding and n8n-offboarding stay distinguishable here even though both
# render the same banner.
_LINE = re.compile(r"developer-signup request .*?\bsource=(\S+)")


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


def pull(days: int):
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        raise SystemExit("ERROR: boto3 missing. Use ~/.rsvenv/bin/python on the Mac.")

    assert_account()
    logs = boto3.client("logs", region_name="us-east-1")
    start = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)

    counts, total, earliest, token = Counter(), 0, None, None
    try:
        while True:
            kw = dict(logGroupName=LOG_GROUP, startTime=start,
                      filterPattern="developer-signup request")
            if token:
                kw["nextToken"] = token
            resp = logs.filter_log_events(**kw)
            for ev in resp.get("events", []):
                ts = ev.get("timestamp")
                if ts and (earliest is None or ts < earliest):
                    earliest = ts
                m = _LINE.search(ev.get("message", ""))
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
                f"ERROR: log group {LOG_GROUP} not found in {ACCOUNT}.\n"
                "       That is a missing log group, NOT zero arrivals. The\n"
                "       function may never have been invoked, or the name has\n"
                "       changed. Do not read this as a measurement.")
        raise SystemExit(f"ERROR: {code}: {e.response['Error'].get('Message','')[:200]}")

    return counts, total, earliest


def report(counts, total, earliest, days, want) -> int:
    print(f"log group     : {LOG_GROUP}")
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
    if unmatched:
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
        known = registered_keys()
        for k in want:
            n = counts.get(k, 0)
            if k not in known:
                print(f"  {k}: UNREGISTERED. Not in _SOURCE_BANNERS or _SOURCE_ALIASES,")
                print(f"     so arrivals on it logged as unmatched:{k} and rendered no")
                print("     banner. This is not a measurement of the channel.")
            elif n == 0:
                print(f"  {k}: ZERO ARRIVALS over the observed window. The key is")
                print("     registered and resolving, so this is a real absence -- but")
                print("     check the key was registered BEFORE the window started, and")
                print("     that relayshield-developer-signup was deployed for it")
                print("     (no deploy path existed before 2026-09-03).")
            else:
                print(f"  {k}: {n}")
        print()

    print("Counts are arrivals on the developers page, not signups and not revenue.")
    print("Do not quote any of these externally: MEASUREMENT DOCTRINE applies to our")
    print("own funnel exactly as it does to the corpus.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--key", action="append", default=[],
                    help="Report this key explicitly, including when it is zero "
                         "or unregistered. Repeatable.")
    ap.add_argument("--list-registered", action="store_true",
                    help="Print every registered key and exit. Needs no AWS.")
    args = ap.parse_args()

    if args.list_registered:
        for k in sorted(registered_keys()):
            print(k)
        return 0

    counts, total, earliest = pull(args.days)
    return report(counts, total, earliest, args.days, args.key)


if __name__ == "__main__":
    sys.exit(main())
