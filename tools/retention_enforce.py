#!/usr/bin/env python3
"""Enforce the one-year retention rule in the Information Security Policy, section 4.

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/retention_enforce.py                      # dry run, both targets
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/retention_enforce.py --only hosted_proxies --apply

WHAT THE RULE MEANS, AND WHAT THIS TOOL REFUSES TO GUESS. Records are deleted one year AFTER
TERMINATION, never one year after creation. A creation-date rule would delete every long-standing paying
customer. So a record is eligible only when it is terminated AND carries a termination timestamp older than
the cutoff:

  hosted_proxies  relayshield_hosted_proxies: status = "terminated" and terminated_at (epoch) older than 1 year.
  users           relayshield_users: active = false and deactivated_at or subscription_cancelled_at older than 1 year.
                  A row with no termination timestamp is counted as "undatable" and is NEVER deleted: the dry
                  run tells you how many, and the fix is to stamp deactivated_at at cancellation, not to
                  guess an age.

NOT COVERED: the MCP proxy's own audit log. It lives in the proxy process or in the file named by
MCP_PROXY_AUDIT_FILE on the tenant instance, not in DynamoDB.

SAFETY. Dry run unless --apply. --apply needs --only, so deleting one table is always a deliberate choice.
--days cannot be lower than 365. A run that would delete more than --max-delete (default 100) rows refuses.
Each delete carries a ConditionExpression that re-checks the status and the exact timestamp that was read, so a
record reactivated between the scan and the delete is skipped. Prints identifiers and counts only, never
contact details. The scan prints progress per page. Account is checked first and anything but 239677749008
stops the run before a table is touched.
"""
import argparse
import sys
import time
from datetime import datetime, timezone

ACCOUNT = "239677749008"
REGION = "us-east-1"
MIN_DAYS = 365
DEFAULT_MAX_DELETE = 100

TARGETS = {
    "hosted_proxies": {
        "table": "relayshield_hosted_proxies",
        "key": "tenant_id",
        "names": {"#s": "status"},
        "filter": "#s = :flag",
        "values": {":flag": {"S": "terminated"}},
        "condition": "#s = :flag AND {ts} = :ts",
        "ts_attrs": ["terminated_at"],
    },
    "users": {
        "table": "relayshield_users",
        "key": "user_id",
        "names": {},
        "filter": "active = :flag",
        "values": {":flag": {"BOOL": False}},
        "condition": "active = :flag AND {ts} = :ts",
        "ts_attrs": ["deactivated_at", "subscription_cancelled_at"],
    },
}


def parse_ts(attr):
    """Epoch seconds from a DynamoDB typed value: N (epoch) or S (ISO 8601). None if unusable."""
    if not isinstance(attr, dict):
        return None
    try:
        if "N" in attr:
            return float(attr["N"])
        if "S" in attr and attr["S"]:
            dt = datetime.fromisoformat(attr["S"].replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
    except (ValueError, TypeError):
        return None
    return None


def newest_marker(item, ts_attrs):
    """(attribute, typed value, epoch) of the NEWEST termination marker, or None. Newest, so a record is
    only ever aged from its most recent termination."""
    best = None
    for name in ts_attrs:
        v = item.get(name)
        e = parse_ts(v)
        if e is not None and (best is None or e > best[2]):
            best = (name, v, e)
    return best


def scan_target(client, spec, cutoff, out):
    """Returns (eligible, counts). eligible is a list of (key_value, ts_attr, ts_typed_value)."""
    proj_names = dict(spec["names"])
    proj = ["#k"] + ["#a%d" % i for i, _ in enumerate(spec["ts_attrs"])]
    proj_names["#k"] = spec["key"]
    for i, a in enumerate(spec["ts_attrs"]):
        proj_names["#a%d" % i] = a
    counts = {"scanned": 0, "terminated": 0, "eligible": 0, "too_recent": 0, "undatable": 0}
    eligible, start = [], None
    while True:
        kw = dict(TableName=spec["table"], FilterExpression=spec["filter"],
                  ExpressionAttributeNames=proj_names, ExpressionAttributeValues=spec["values"],
                  ProjectionExpression=", ".join(proj))
        if start:
            kw["ExclusiveStartKey"] = start
        resp = client.scan(**kw)
        counts["scanned"] += resp.get("ScannedCount", 0)
        for item in resp.get("Items", []):
            counts["terminated"] += 1
            marker = newest_marker(item, spec["ts_attrs"])
            if marker is None:
                counts["undatable"] += 1
            elif marker[2] < cutoff:
                counts["eligible"] += 1
                eligible.append((item[spec["key"]], marker[0], marker[1]))
            else:
                counts["too_recent"] += 1
        start = resp.get("LastEvaluatedKey")
        print("   %s: scanned %d, terminated %d, eligible %d" %
              (spec["table"], counts["scanned"], counts["terminated"], counts["eligible"]), file=out)
        if not start:
            return eligible, counts


def delete_rows(client, spec, eligible, out):
    deleted = skipped = 0
    for key_val, ts_attr, ts_val in eligible:
        values = dict(spec["values"])
        values[":ts"] = ts_val
        kw = dict(TableName=spec["table"], Key={spec["key"]: key_val},
                  ConditionExpression=spec["condition"].format(ts=ts_attr),
                  ExpressionAttributeValues=values)
        if spec["names"]:  # DynamoDB rejects an empty ExpressionAttributeNames
            kw["ExpressionAttributeNames"] = spec["names"]
        try:
            client.delete_item(**kw)
            deleted += 1
        except client.exceptions.ConditionalCheckFailedException:
            skipped += 1
            print("   skipped (changed since scan): %s" % list(key_val.values())[0], file=out)
    return deleted, skipped


def main(argv=None, client=None, now=None, out=sys.stdout):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", choices=sorted(TARGETS), help="one target; required with --apply")
    ap.add_argument("--days", type=int, default=MIN_DAYS, help="retention in days, minimum 365")
    ap.add_argument("--max-delete", type=int, default=DEFAULT_MAX_DELETE)
    ap.add_argument("--apply", action="store_true", help="delete; without it nothing is changed")
    args = ap.parse_args(argv)
    if args.days < MIN_DAYS:
        print("REFUSED: --days %d is below the policy minimum of %d. Nothing was changed." % (args.days, MIN_DAYS), file=out)
        return 2
    if args.apply and not args.only:
        print("REFUSED: --apply needs --only <target>. Run the dry run first and choose one.", file=out)
        return 2
    if client is None:
        import boto3
        sts = boto3.client("sts", region_name=REGION)
        got = sts.get_caller_identity()["Account"]
        if got != ACCOUNT:
            print("STOP: credentials resolve to account %s, not %s. Nothing was read or changed." % (got, ACCOUNT), file=out)
            return 2
        client = boto3.client("dynamodb", region_name=REGION)
    cutoff = (now if now is not None else time.time()) - args.days * 86400
    print("%s (retention %d days, cutoff %s)" % ("APPLY MODE" if args.apply else "DRY RUN, nothing will be changed",
          args.days, datetime.fromtimestamp(cutoff, timezone.utc).strftime("%Y-%m-%d")), file=out)
    names = [args.only] if args.only else sorted(TARGETS)
    results = {}
    for name in names:
        spec = TARGETS[name]
        print("== %s" % name, file=out)
        eligible, counts = scan_target(client, spec, cutoff, out)
        results[name] = (eligible, counts)
        print("   eligible %d, terminated but under a year %d, terminated with NO timestamp (never deleted) %d"
              % (counts["eligible"], counts["too_recent"], counts["undatable"]), file=out)
        for key_val, ts_attr, _ in eligible[:10]:
            print("   would delete: %s (aged by %s)" % (list(key_val.values())[0], ts_attr), file=out)
    if not args.apply:
        print("Dry run only. Nothing was changed.", file=out)
        return 0
    eligible, _ = results[args.only]
    if len(eligible) > args.max_delete:
        print("REFUSED: %d rows eligible, above --max-delete %d. Read the list, then raise it deliberately."
              % (len(eligible), args.max_delete), file=out)
        return 2
    deleted, skipped = delete_rows(client, TARGETS[args.only], eligible, out)
    print("Deleted %d, skipped %d (changed since the scan)." % (deleted, skipped), file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
