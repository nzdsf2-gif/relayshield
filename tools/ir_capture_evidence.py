#!/usr/bin/env python3
"""Incident evidence capture. READ-ONLY. Run it BEFORE containment, because containment overwrites evidence.

    AWS_PROFILE=relayshield python3 tools/ir_capture_evidence.py --lookup AccessKeyId=AKIA... --function relayshield-api
    AWS_PROFILE=relayshield python3 tools/ir_capture_evidence.py --lookup Username=someone --iam-user someone --since-hours 720

What it saves, into ./ir_evidence_<UTC timestamp>/ (a NEW directory; it refuses to reuse one):
  caller.json                   who ran the capture, which account, when (UTC)
  cloudtrail_<n>.json           CloudTrail LookupEvents for each --lookup KEY=VALUE, newest first.
                                KEY is one of AccessKeyId, Username, ResourceName, EventName. CloudTrail's event
                                history only reaches back 90 days, so the window is capped there and says so.
  lambda_<function>.json        configuration, versions, aliases and reserved concurrency of each --function.
                                The presigned code URL is removed: it is a live download link, not evidence.
  iam_<user>.json               access keys of each --iam-user with their last-used time and service.
  SHA256SUMS                    a hash of every file above, so a later change to a file is detectable.

It changes nothing in AWS, and refuses to run unless the credentials resolve to the RelayShield account.
The directory is CONFIDENTIAL (account ids, user names, IP addresses). Do not commit it. Copy it somewhere you
cannot overwrite, then say where in the incident record: docs/security/forensics_plan.md section 4.
"""
import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

ACCOUNT = "239677749008"
REGION = "us-east-1"
LOOKUP_KEYS = ("AccessKeyId", "Username", "ResourceName", "EventName")
MAX_DAYS = 90
MAX_EVENTS = 5000


def code(e):
    return getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)


def write(outdir, name, obj):
    (outdir / name).write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n")


def parse_lookup(s):
    k, sep, v = s.partition("=")
    if not sep or k not in LOOKUP_KEYS or not v:
        raise ValueError(f"--lookup must be KEY=VALUE with KEY one of {', '.join(LOOKUP_KEYS)}: got {s!r}")
    return k, v


def cloudtrail(ct, key, value, start):
    events, token = [], None
    while len(events) < MAX_EVENTS:
        kw = {"LookupAttributes": [{"AttributeKey": key, "AttributeValue": value}], "StartTime": start, "MaxResults": 50}
        if token:
            kw["NextToken"] = token
        r = ct.lookup_events(**kw)
        events += r.get("Events", [])
        token = r.get("NextToken")
        if not token:
            break
    return {"lookup": f"{key}={value}", "since_utc": start.isoformat(), "count": len(events),
            "truncated_at_limit": len(events) >= MAX_EVENTS, "events": events}


def lambda_state(lam, fn):
    d = lam.get_function(FunctionName=fn)
    d.pop("ResponseMetadata", None)
    d.get("Code", {}).pop("Location", None)
    out = {"function": d.get("Configuration"), "code": d.get("Code"), "tags": d.get("Tags")}
    out["versions"] = [v for p in _pages(lam.list_versions_by_function, "Versions", FunctionName=fn) for v in [p]]
    out["aliases"] = list(_pages(lam.list_aliases, "Aliases", FunctionName=fn))
    out["reserved_concurrency"] = lam.get_function_concurrency(FunctionName=fn).get("ReservedConcurrentExecutions")
    return out


def _pages(fn, key, **kw):
    marker = None
    while True:
        r = fn(**kw, **({"Marker": marker} if marker else {}))
        yield from r.get(key, [])
        marker = r.get("NextMarker")
        if not marker:
            return


def iam_state(iam, user):
    keys = iam.list_access_keys(UserName=user).get("AccessKeyMetadata", [])
    out = []
    for k in keys:
        last = iam.get_access_key_last_used(AccessKeyId=k["AccessKeyId"]).get("AccessKeyLastUsed", {})
        out.append({**k, "last_used": last})
    return {"user": user, "access_keys": out}


def manifest(outdir):
    lines = []
    for p in sorted(outdir.iterdir()):
        if p.name != "SHA256SUMS":
            lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}")
    (outdir / "SHA256SUMS").write_text("\n".join(lines) + "\n")
    return lines


def run(clients, account_of, lookups, functions, iam_users, since_hours, outdir, now=None, out=print):
    got = account_of()
    if got != ACCOUNT:
        out(f"Refusing to run: credentials resolve to account {got}, not {ACCOUNT}. Use AWS_PROFILE=relayshield.")
        return 2
    if not (lookups or functions or iam_users):
        out("Nothing to capture: give at least one of --lookup, --function, --iam-user.")
        return 2
    outdir = Path(outdir)
    if outdir.exists():
        out(f"Refusing to reuse {outdir}: evidence is written once.")
        return 2
    now = now or dt.datetime.now(dt.timezone.utc)
    capped = min(since_hours, MAX_DAYS * 24)
    if capped != since_hours:
        out(f"NOTE: CloudTrail event history reaches back {MAX_DAYS} days; window cut from {since_hours} to {capped} hours.")
    start = now - dt.timedelta(hours=capped)
    outdir.mkdir(parents=True)
    write(outdir, "caller.json", {"account": got, "captured_at_utc": now.isoformat(), "since_utc": start.isoformat()})
    failed = 0
    jobs = [(f"cloudtrail_{i}.json", lambda k=k, v=v: cloudtrail(clients["cloudtrail"], k, v, start)) for i, (k, v) in enumerate(lookups, 1)]
    jobs += [(f"lambda_{fn}.json", lambda fn=fn: lambda_state(clients["lambda"], fn)) for fn in functions]
    jobs += [(f"iam_{u}.json", lambda u=u: iam_state(clients["iam"], u)) for u in iam_users]
    for name, job in jobs:
        try:
            write(outdir, name, job())
            out(f"  saved    {name}")
        except Exception as e:
            failed += 1
            write(outdir, name, {"error": code(e), "detail": str(e)})
            out(f"  FAILED   {name}  ({code(e)}); the failure is recorded in the file so a gap is visible later")
    for line in manifest(outdir):
        out(f"  hashed   {line}")
    out(f"\nEvidence in {outdir}. {failed} failed. Copy it somewhere you cannot overwrite; do not commit it.")
    return 1 if failed else 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookup", action="append", default=[], help="KEY=VALUE, repeatable")
    ap.add_argument("--function", action="append", default=[])
    ap.add_argument("--iam-user", action="append", default=[])
    ap.add_argument("--since-hours", type=int, default=168)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    try:
        lookups = [parse_lookup(s) for s in a.lookup]
    except ValueError as e:
        print(e)
        return 2
    import boto3
    clients = {n: boto3.client(n, region_name=REGION) for n in ("cloudtrail", "lambda", "iam")}
    sts = boto3.client("sts", region_name=REGION)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return run(clients, lambda: sts.get_caller_identity()["Account"], lookups, a.function, a.iam_user,
               a.since_hours, a.out or f"ir_evidence_{stamp}")


if __name__ == "__main__":
    sys.exit(main())
