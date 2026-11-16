#!/usr/bin/env python3
"""Did the intel sweep keywords (001, 001b, 002, 003) actually produce channels?

READ-ONLY. Nothing in this script writes to AWS.

WHY THIS EXISTS
---------------
The sweeps in intel_channel_recommendations.md add brand-name keywords to
SEARCH_KEYWORDS in relayshield_intel_discovery.py. Closing the loop means
asking, per keyword, whether any channel in relayshield_intel_channels carries
it as keyword_match. Scheduled sessions have no AWS, so this runs on the Mac.

It answers three questions, in the order they have to be answered, because a
zero in (3) means nothing until (1) and (2) are known:

  1. DEPLOYED  Is the keyword in the code the Lambda is actually running?
               relayshield-intel-discovery is NOT in deploy_lambdas.yml, so a
               keyword on main is not evidence the Lambda searches for it.
               Sweeps 001/001b/002 only reached main on 2026-11-15/16.
  2. SEARCHED  Did a run actually search it? CloudWatch "Searching keyword:"
               lines, plus "Discovery complete" and "Task timed out" counts.
               Every weekly workflow run sampled on 2026-11-16 (Aug 31, Oct 5,
               Nov 2, Nov 9) printed {"skipped": "lock_held"}: the response it
               read came from a second invocation, so the workflow has never
               shown whether the first one finished.
  3. PRODUCED  Rows in relayshield_intel_channels whose keyword_match is the
               keyword.

HOW TO READ A ZERO IN (3). keyword_match is written only when a channel is
NEWLY added (or re-added after going inactive), and within one run a channel is
credited to the FIRST keyword in SEARCH_KEYWORDS order that found it. The sweep
blocks sit late in the list, so a channel that a generic keyword also matches
is credited to the generic one. A zero therefore means "added nothing new",
which is the retirement criterion, not "matches nothing on Telegram".

USAGE (on the founder's Mac, from the repo root)

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/intel_keyword_yield.py

Options: --days N (CloudWatch window, default 120), --skip-logs, --skip-deployed.
"""

import argparse
import ast
import io
import sys
import time
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DISCOVERY_SRC = REPO / "relayshield_intel_discovery.py"
REQUIRED_ACCOUNT = "239677749008"
REGION = "us-east-1"
TABLE = "relayshield_intel_channels"
FUNCTION = "relayshield-intel-discovery"
LOG_GROUP = "/aws/lambda/" + FUNCTION

# The sweeps as RECORDED in intel_channel_recommendations.md. Kept explicit
# rather than parsed from code comments, because the comment blocks in
# SEARCH_KEYWORDS do not have clean end markers (sweep 003's block runs straight
# into the 2026-07-24 Chinese/Korean batch). Each is checked against the live
# SEARCH_KEYWORDS list on every run, so a retired keyword is reported, not
# silently miscounted. "moon cloud" is in both 001 and 002, as the record says.
SWEEPS = {
    "001": ["omega cloud", "moon cloud", "bidencash", "darcula", "magic cat",
            "otp bot", "sim swap service", "cc shop", "dumps and pins", "fullz"],
    "001b": ["qilin", "dragonforce", "thegentlemen", "babuk"],
    "002": ["moon cloud", "daisy cloud", "log sync", "observer cloud",
            "alien txtbase", "data leak monitoring", "mailpass", "bidencash shop",
            "cti now", "noname057", "rippersec", "dark storm team", "z-pentest"],
    "003": ["astro otp", "sms buster", "smsranger", "tycoon 2fa", "lucid panel",
            "lighthouse phishing", "evilproxy", "sneaky 2fa", "xinxin group",
            "brians club", "b1acks stash", "serverkillers", "cyb3rdrag0nz",
            "cyber fattah team", "handala hack team", "conquerors electronic army"],
}


def keywords_from_source(text):
    """SEARCH_KEYWORDS from a relayshield_intel_discovery.py source, by AST, so
    the deployed copy is read exactly the way Python would read it."""
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "SEARCH_KEYWORDS" for t in node.targets):
            return [kw for kw, _cat in ast.literal_eval(node.value)]
    raise ValueError("SEARCH_KEYWORDS not found")


def all_sweep_keywords():
    seen, out = set(), []
    for kws in SWEEPS.values():
        for k in kws:
            if k not in seen:
                seen.add(k)
                out.append(k)
    return out


def check_account(session):
    acct = session.client("sts").get_caller_identity()["Account"]
    if acct != REQUIRED_ACCOUNT:
        sys.exit(f"Refusing to run: credentials resolve to account {acct}, not "
                 f"{REQUIRED_ACCOUNT}. Prefix the command with AWS_PROFILE=relayshield.")


def deployed_keywords(session):
    lam = session.client("lambda", region_name=REGION)
    fn = lam.get_function(FunctionName=FUNCTION)
    cfg = fn["Configuration"]
    print(f"Deployed {FUNCTION}: LastModified={cfg.get('LastModified')} "
          f"Timeout={cfg.get('Timeout')}s CodeSha256={cfg.get('CodeSha256')}")
    with urllib.request.urlopen(fn["Code"]["Location"], timeout=60) as r:
        blob = r.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = next((n for n in z.namelist()
                     if n.rsplit("/", 1)[-1] == "relayshield_intel_discovery.py"), None)
        if name is None:
            print("  deployed package has no relayshield_intel_discovery.py; files: "
                  + ", ".join(sorted(z.namelist())[:15]))
            return None
        return keywords_from_source(z.read(name).decode("utf-8"))


def log_evidence(session, days):
    logs = session.client("logs", region_name=REGION)
    start = int((time.time() - days * 86400) * 1000)

    def events(pattern):
        kw = dict(logGroupName=LOG_GROUP, startTime=start, filterPattern=pattern)
        while True:
            resp = logs.filter_log_events(**kw)
            yield from resp.get("events", [])
            if not resp.get("nextToken"):
                return
            kw["nextToken"] = resp["nextToken"]

    searched = Counter()
    for e in events('"Searching keyword:"'):
        msg = e["message"]
        searched[msg.split("Searching keyword:", 1)[1].strip()] += 1
    complete = [e for e in events('"Discovery complete"')]
    timeouts = [e for e in events('"Task timed out"')]
    starts = [e for e in events('"INTEL-DISCOVERY starting"')]
    locked = [e for e in events('"already holds the discovery lock"')]
    print(f"CloudWatch {LOG_GROUP}, last {days} days:")
    print(f"  invocations started        : {len(starts)}")
    print(f"  exited on lock_held        : {len(locked)}")
    print(f"  'Discovery complete' lines : {len(complete)}")
    print(f"  'Task timed out' lines     : {len(timeouts)}")
    for e in complete[-6:]:
        when = time.strftime("%Y-%m-%d %H:%M", time.gmtime(e["timestamp"] / 1000))
        print(f"    {when}  {e['message'].strip()[-80:]}")
    for e in timeouts[-6:]:
        when = time.strftime("%Y-%m-%d %H:%M", time.gmtime(e["timestamp"] / 1000))
        print(f"    TIMEOUT {when}  {e['message'].strip()[-80:]}")
    return searched


def scan_all(table):
    items, resp = [], table.scan()
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    return items


def report(rows, repo_kws, deployed, searched):
    by_kw = defaultdict(list)
    for r in rows:
        km = str(r.get("keyword_match") or "").strip().lower()
        if km:
            by_kw[km].append(r)
    with_km = sum(len(v) for v in by_kw.values())
    print(f"\n{TABLE}: {len(rows)} rows, {with_km} carry keyword_match\n")

    def yn(flag):
        return "-" if flag is None else ("yes" if flag else "NO")

    for sweep, kws in SWEEPS.items():
        total = sum(len(by_kw.get(k, [])) for k in kws)
        print(f"=== Sweep {sweep}: {len(kws)} keywords, {total} channels credited ===")
        print(f"  {'keyword':<28} {'on main':<8} {'deployed':<9} {'searched':<9} channels")
        for k in kws:
            dep = None if deployed is None else (k in deployed)
            srch = None if searched is None else searched.get(k, 0)
            print(f"  {k:<28} {yn(k in repo_kws):<8} {yn(dep):<9} "
                  f"{'-' if srch is None else srch:<9} {len(by_kw.get(k, []))}")
            for r in sorted(by_kw.get(k, []), key=lambda x: str(x.get("first_seen", ""))):
                print(f"      @{r.get('username')}  active={r.get('active')}  "
                      f"category={r.get('category')}  members={r.get('member_count')}  "
                      f"first_seen={str(r.get('first_seen', ''))[:10]}")
        print()

    print("Paste everything above into the next session. A keyword is a")
    print("retirement candidate only if deployed=yes, searched>=2 and channels=0.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--skip-logs", action="store_true")
    ap.add_argument("--skip-deployed", action="store_true")
    args = ap.parse_args()

    repo_kws = set(keywords_from_source(DISCOVERY_SRC.read_text(encoding="utf-8")))
    missing = [k for k in all_sweep_keywords() if k not in repo_kws]
    if missing:
        print("NOTE: no longer in SEARCH_KEYWORDS on this checkout: " + ", ".join(missing))

    import boto3
    session = boto3.session.Session(region_name=REGION)
    check_account(session)

    deployed = None
    if not args.skip_deployed:
        dk = deployed_keywords(session)
        if dk is not None:
            deployed = set(dk)
            sweep_kws = all_sweep_keywords()
            print(f"  deployed SEARCH_KEYWORDS: {len(dk)}; sweep keywords present: "
                  f"{sum(k in deployed for k in sweep_kws)} of {len(sweep_kws)}")
    searched = None if args.skip_logs else log_evidence(session, args.days)

    table = session.resource("dynamodb").Table(TABLE)
    rows = scan_all(table)
    if not rows:
        sys.exit("No rows returned from relayshield_intel_channels: wrong profile or region?")
    report(rows, repo_kws, deployed, searched)
    return 0


if __name__ == "__main__":
    sys.exit(main())
