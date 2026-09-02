#!/usr/bin/env python3
"""Why does relayshield_stolen_sessions hold almost nothing?

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/diagnose_stolen_sessions.py

Read-only. Never writes, never deletes.

WHY THIS EXISTS
---------------
On 2026-09-02 a scan for OpenRouter keys returned Count 0 -- and, far more
importantly, ScannedCount 9. Nine rows is the whole table.

Nine is a number this repo has seen before. The docstring of
_store_observed_session in relayshield_intel_monitor.py records:

    "the table held 9 rows on 2026-08-16, all of them source 'demo', after
     months of collection."

That was the CORPUS-1 finding: _store_stolen_session required a matched_email,
so a stolen session was only kept when it already belonged to a customer, which
with a small customer base discards essentially everything. _store_observed_
session was added to keep unmatched sessions too.

If the table STILL holds nine rows and they are STILL the demo rows, the
CORPUS-1 fix has written nothing since it shipped. A matching count is a lead
and not a finding, which is why this script reads the `source` attribute on
every row rather than trusting the arithmetic.

WHAT IT ANSWERS, IN ORDER
  1. What is actually in the table -- by source, type, and date written.
  2. Has the CORPUS-1 observed path EVER fired?
  3. Where does the pipeline stop? INTEL-5 log lines say whether archives are
     being seen, downloaded, rejected as the wrong format, or parsed to zero
     sessions. Each of those is a different bug with a different fix.

WHY A SCRIPT AND NOT A PASTED COMMAND
The container running Claude has no usable AWS credentials, and "no AWS in this
sandbox" is never a reason to skip a check -- it moves the check to the Mac, it
does not delete it. This is that move.

WHAT IT DELIBERATELY DOES NOT DO
It does not print a stolen credential, a cookie value, an email address or a
domain belonging to a person. Counts and categories only. The matched rows hold
a KMS-encrypted address and a hashed index, and nothing here decrypts either.
"""

import argparse
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

try:
    import boto3
except ImportError:
    sys.exit("boto3 missing. Create the durable venv once:\n"
             "    python3 -m venv ~/.rsvenv && ~/.rsvenv/bin/pip install boto3\n"
             "then run this with ~/.rsvenv/bin/python")

TABLE = "relayshield_stolen_sessions"
LOG_GROUP = "/aws/lambda/relayshield-intel-monitor"
EXPECTED_ACCOUNT = "239677749008"


def assert_account():
    """620534471984 is the pre-audit account and is never the target of a
    RelayShield command. It is also the shell default, so a missing
    AWS_PROFILE aims there silently and a read returns ResourceNotFound,
    which reads as a missing table and is not."""
    acct = boto3.client("sts").get_caller_identity()["Account"]
    if acct != EXPECTED_ACCOUNT:
        sys.exit(f"WRONG ACCOUNT: {acct}. Expected {EXPECTED_ACCOUNT}.\n"
                 f"Re-run with AWS_PROFILE=relayshield.")
    print(f"account {acct}  OK\n")
    return acct


def scan_table():
    ddb = boto3.resource("dynamodb")
    table = ddb.Table(TABLE)
    rows, kwargs = [], {}
    while True:
        resp = table.scan(**kwargs)
        rows.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return rows


def report_table(rows):
    print("=" * 72)
    print(f"1. WHAT IS IN {TABLE}")
    print("=" * 72)
    print(f"\n  total rows: {len(rows)}\n")
    if not rows:
        print("  The table is EMPTY. Nothing has ever been written, so the")
        print("  question is not 'which credentials' but 'does collection run'.")
        return {}

    by_source = Counter(r.get("source", "(no source attribute)") for r in rows)
    by_type = Counter(r.get("session_type", "(none)") for r in rows)
    by_day = Counter((r.get("ingested_at") or "")[:10] or "(none)" for r in rows)
    nhi = Counter(r.get("nhi_description", "") for r in rows if r.get("type") == "nhi")

    print("  by source:")
    for k, v in by_source.most_common():
        print(f"    {v:6d}  {k}")
    print("\n  by session_type:")
    for k, v in by_type.most_common(15):
        print(f"    {v:6d}  {k}")
    print("\n  by day written:")
    for k, v in sorted(by_day.items()):
        print(f"    {v:6d}  {k}")
    if nhi:
        print("\n  NHI credential findings by provider:")
        for k, v in nhi.most_common():
            print(f"    {v:6d}  {k}")
    else:
        print("\n  NHI credential findings: NONE.")
        print("    _NHI_PATS in relayshield_intel_monitor.py writes these, and it")
        print("    only ever runs over files unpacked from a stealer archive. No")
        print("    NHI rows therefore means no archive has been parsed, not that")
        print("    the patterns are wrong. Section 3 says which.")
    return by_source


def report_corpus1(by_source):
    print("\n" + "=" * 72)
    print("2. HAS THE CORPUS-1 OBSERVED PATH EVER FIRED?")
    print("=" * 72)
    observed = by_source.get("observed", 0)
    demo = by_source.get("demo", 0)
    matched = sum(v for k, v in by_source.items() if k not in ("observed", "demo"))
    print(f"\n  observed (CORPUS-1, unmatched sessions kept): {observed}")
    print(f"  demo    (seed rows, not collection):          {demo}")
    print(f"  matched (belongs to a monitored customer):    {matched}\n")
    if observed == 0:
        print("  VERDICT: the CORPUS-1 fix has never written a row.")
        print("  _store_observed_session is called only from the archive parsing")
        print("  path, so this is the same finding as 'no archive was parsed'.")
        print("  It is NOT evidence that the fix is wrong -- go to section 3.")
    else:
        print(f"  VERDICT: the observed path works. {observed} row(s) written.")
        print("  If the total is still small, the constraint is upstream volume,")
        print("  not the storage gate.")


def report_logs(days):
    print("\n" + "=" * 72)
    print(f"3. WHERE DOES THE PIPELINE STOP? (INTEL-5 log lines, last {days}d)")
    print("=" * 72)
    logs = boto3.client("logs")
    start = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)

    # Each of these is a DIFFERENT bug with a different fix, which is the whole
    # reason for reading them separately rather than counting archives_parsed.
    # Ordered as the funnel runs, so the first probe that reads zero is where
    # it stops. Updated 2026-09-02 to match ARCHIVE-FUNNEL-1's instrumentation:
    # before that, a document rejected by the extension/mime filter produced no
    # log line at all, so every probe here read zero whether documents were
    # arriving or not. A funnel whose middle is invisible cannot be debugged.
    probes = [
        ("documents skipped, not archive-shaped",
         "document SKIPPED",
         "documents ARE arriving. The filter rejected them -- read the name= "
         "and mime= on these lines and widen it if they are really archives"),
        ("archives dispatched to the parser",
         "INTEL-5: archive", "the monitor saw an archive and tried to handle it"),
        ("skipped, oversized",
         "skipping oversized archive", "raise the INTEL-5 size cap"),
        ("download failed",
         "archive download failed", "a Telegram/session problem, not a parsing one"),
        ("rejected, neither ZIP nor RAR",
         "neither ZIP nor RAR", "the bytes are not a ZIP or RAR (7z? password-protected?)"),
        ("archive handler raised",
         "INTEL-5 archive failed", "an exception inside _process_stealer_archive"),
        ("archives that parsed, with a session count",
         "unique sessions parsed",
         "parsing WORKS. If the count is 0 the archive layout is unrecognised; "
         "if it is non-zero the sessions should be in the table above"),
    ]
    any_hit = False
    for label, needle, meaning in probes:
        try:
            resp = logs.filter_log_events(
                logGroupName=LOG_GROUP, startTime=start,
                filterPattern=f'"{needle}"', limit=200)
            n = len(resp.get("events", []))
        except logs.exceptions.ResourceNotFoundException:
            print(f"\n  log group {LOG_GROUP} not found. Is the monitor deployed?")
            return
        except Exception as exc:
            print(f"\n  log query failed for '{needle}': {exc}")
            continue
        flag = "  <-- " + meaning if n else ""
        if n:
            any_hit = True
        print(f"\n  {n:5d}  {label}{flag}")
        for ev in resp.get("events", [])[:3]:
            print(f"         {ev['message'].strip()[:150]}")

    print()
    if not any_hit:
        print("  NOTHING MATCHED, which now means something specific.")
        print()
        print("  Since ARCHIVE-FUNNEL-1 (2026-09-02) every document the monitor")
        print("  sees produces a line: either it is dispatched to the parser or it")
        print("  is logged as SKIPPED with its name, mime type and size. Zero of")
        print("  BOTH means no channel posted a document at all in this window.")
        print()
        print("  If the deploy carrying that change has not run yet, this section")
        print("  cannot tell you anything and the run is not an answer. Check the")
        print("  most recent run digest for the 'Documents seen' line -- if it is")
        print("  absent, the instrumentation is not live yet.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=14,
                    help="how far back to read INTEL-5 log lines (default 14)")
    args = ap.parse_args()

    if not os.environ.get("AWS_PROFILE"):
        print("WARNING: AWS_PROFILE is not set. The shell default is the "
              "pre-audit account 620534471984, which holds no RelayShield "
              "resource. Re-run with AWS_PROFILE=relayshield.\n")
    assert_account()

    rows = scan_table()
    by_source = report_table(rows)
    if by_source:
        report_corpus1(by_source)
    report_logs(args.days)

    print("\n" + "=" * 72)
    print("WHAT THIS MEANS FOR THE OPENROUTER WEBHOOK")
    print("=" * 72)
    print("\n  The trigger to build it is the first non-zero count of sk-or-v1-*")
    print("  in this table, and the standing measurement rule says do not quote a")
    print("  category number to anyone until it clears 100 collected indicators.")
    print(f"\n  This table holds {len(rows)} row(s) in total. A zero OpenRouter count")
    print("  out of that is not evidence that no OpenRouter keys are being traded.")
    print("  It measures our collection, not the criminal market. Fix the pipeline")
    print("  above before reading any number here as a fact about the world.")


if __name__ == "__main__":
    sys.exit(main())
