#!/usr/bin/env python3
"""Measure agent-bait-scan's false-positive rate. The gate on ABS-1 / Bundle D.

WHY THIS EXISTS. relayshield_agentic_api.py's AWS_DIMENSION_NAMES deliberately
omits agent-bait-scan, and says why: adding a third usage dimension to a
PUBLISHED AWS Marketplace listing is a change set with AWS review latency, and a
published dimension is an expensive place to discover a fresh heuristic needs
tuning. It goes in "once the endpoint has run against real traffic long enough to
have a measured false-positive rate".

Nothing was measuring that. The handler logged fetch failures and provenance
errors and nothing about what the heuristics FIRED ON, so the gate could never
open on its own. It now emits one AGENT_BAIT_SCAN line per scan; this pulls them.

**A FALSE POSITIVE HERE IS A HUMAN JUDGEMENT, NOT A COMPUTATION, AND THIS TOOL
DOES NOT PRETEND OTHERWISE.** The endpoint reports what a repository's
instructions would cause an agent to do. Whether a given `execution_instruction`
finding is a false positive depends on whether that repository legitimately asks
you to pipe a script into a shell, which plenty of good projects do. So this
samples, writes an adjudication file with one row per finding, and computes the
rate only from rows a person has marked. An unmarked row counts as nothing.

    --pull    read CloudWatch, write a sample to adjudicate   (needs AWS)
    --rate    compute the rate from the adjudicated file      (no AWS)

Run --pull on the Mac with AWS_PROFILE=relayshield, or in Actions under the OIDC
role. It needs logs:FilterLogEvents on the agentic API's log group.
"""

import argparse
import json
import random
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_GROUP = "/aws/lambda/relayshield-agentic-api"
DEFAULT_OUT = ROOT / "aws_marketplace" / "agent_bait_adjudication.jsonl"
MIN_ADJUDICATED = 30


def pull(days: int, sample: int, out: Path) -> int:
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError:
        raise SystemExit("ERROR: boto3 missing. Use ~/.rsvenv/bin/python on the Mac.")

    logs = boto3.client("logs", region_name="us-east-1")
    start = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)

    events, token = [], None
    try:
        while True:
            kw = dict(logGroupName=LOG_GROUP, startTime=start,
                      filterPattern="AGENT_BAIT_SCAN")
            if token:
                kw["nextToken"] = token
            resp = logs.filter_log_events(**kw)
            events.extend(resp.get("events", []))
            token = resp.get("nextToken")
            if not token or len(events) >= 5000:
                break
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "ResourceNotFoundException":
            raise SystemExit(
                f"ERROR: log group {LOG_GROUP} not found.\n"
                "       Check the profile: without AWS_PROFILE=relayshield this\n"
                "       resolves to the pre-audit account 620534471984, where no\n"
                "       RelayShield resource exists and a read looks like a\n"
                "       missing resource.")
        raise SystemExit(f"ERROR: {code}: {e.response['Error'].get('Message','')[:200]}")

    scans = []
    for ev in events:
        msg = ev.get("message", "")
        i = msg.find("AGENT_BAIT_SCAN ")
        if i == -1:
            continue
        try:
            scans.append(json.loads(msg[i + len("AGENT_BAIT_SCAN "):].strip()))
        except json.JSONDecodeError:
            continue

    flagged = [s for s in scans if s.get("n_findings", 0) > 0]
    print(f"window        : last {days} days")
    print(f"scans logged  : {len(scans)}")
    print(f"with findings : {len(flagged)}")
    if not scans:
        print("\nNo scans yet. The rate is not zero, it is UNMEASURED. Say that\n"
              "rather than reporting 0%, and do not open the Bundle D dimension on it.")
        return 0

    # Sample the FLAGGED scans: an unflagged scan cannot contain a false
    # positive, so adjudicating it spends a person's attention for nothing.
    random.seed(0)                      # reproducible sample, so a re-pull is stable
    chosen = flagged if len(flagged) <= sample else random.sample(flagged, sample)

    existing = {}
    if out.is_file():
        for line in out.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                existing[row["repository"]] = row

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        for s in chosen:
            prev = existing.get(s["repository"], {})
            fh.write(json.dumps({
                "repository": s["repository"],
                "verdict":    s.get("verdict"),
                "kinds":      s.get("kinds", []),
                "hidden":     s.get("hidden", False),
                "provenance": s.get("provenance", False),
                # "" until a person writes "tp" or "fp" here. Anything else is
                # ignored, which is what makes an unadjudicated row count as
                # nothing rather than silently as a true positive.
                "adjudication": prev.get("adjudication", ""),
                "note":         prev.get("note", ""),
            }) + "\n")
    print(f"\nwrote {len(chosen)} rows to {out}")
    print("Open each repository, decide whether the finding is real, and set\n"
          '"adjudication" to "tp" or "fp". Existing marks are preserved on re-pull.')
    return 0


def rate(path: Path) -> int:
    if not path.is_file():
        raise SystemExit(f"ERROR: {path} not found. Run --pull first.")
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    marked = [r for r in rows if r.get("adjudication") in ("tp", "fp")]
    fp = [r for r in marked if r["adjudication"] == "fp"]

    print(f"rows          : {len(rows)}")
    print(f"adjudicated   : {len(marked)}")
    if not marked:
        print("\nUNMEASURED. No row carries tp or fp.")
        return 1

    pct = 100.0 * len(fp) / len(marked)
    print(f"false positives: {len(fp)}")
    print(f"RATE          : {pct:.1f}% of adjudicated findings")

    by_kind = Counter(k for r in fp for k in r.get("kinds", []))
    if by_kind:
        print("\nfalse positives by kind, which is where tuning goes:")
        for k, n in by_kind.most_common():
            print(f"  {n:3d}  {k}")

    if len(marked) < MIN_ADJUDICATED:
        print(f"\nNOT YET DEFENSIBLE. {len(marked)} adjudicated is under the "
              f"{MIN_ADJUDICATED} floor.\n"
              "MEASUREMENT DOCTRINE: a category under its floor does not get quoted,\n"
              "and does not open the Bundle D dimension either.")
        return 1

    print(f"\nMeasured on {len(marked)} adjudicated findings. This is the number\n"
          "ABS-1 was waiting for, and the one to weigh against a Marketplace\n"
          "change set that replaces the whole rate card.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--pull", action="store_true")
    mode.add_argument("--rate", action="store_true")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--sample", type=int, default=50)
    ap.add_argument("--file", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    return pull(args.days, args.sample, args.file) if args.pull else rate(args.file)


if __name__ == "__main__":
    raise SystemExit(main())
