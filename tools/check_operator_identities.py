#!/usr/bin/env python3
"""Answer why relayshield_operator_identities is not filling up.

A4 ("operator identity sightings") has reported 0 on every run since it
shipped. The monitor writes with:

    Key={"handle": handle, "platform": "telegram"}
    UpdateExpression="SET first_seen=..., last_seen=..., #ttl=... "
                     "ADD sightings :one, channels :ch, categories :cat"

and caught every exception per-handle, so a wrong key schema, a missing table
and an IAM denial all printed the same 0 as a genuinely quiet run. The monitor
now distinguishes those (see _operator_line), but only from the next run
onwards. This answers it now, against the real table.

Nothing in the repo creates this table and tools/import_channels.py, named in
the monitor's docstring as the manual counterpart, does not exist here, so the
schema it was actually created with is not knowable from source.

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/check_operator_identities.py

Read-only. It never writes.
"""
import sys
from datetime import datetime, timezone

TABLE = "relayshield_operator_identities"
EXPECTED = [("handle", "HASH"), ("platform", "RANGE")]


def main() -> int:
    import boto3
    from botocore.exceptions import ClientError

    ddb = boto3.client("dynamodb")
    try:
        desc = ddb.describe_table(TableName=TABLE)["Table"]
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        print(f"describe_table({TABLE}) failed: {code}")
        if code == "ResourceNotFoundException":
            print("\nTHE TABLE DOES NOT EXIST. Every write the monitor attempted")
            print("raised and was swallowed. Create it with the schema below, or")
            print("point OPERATORS_TABLE at whatever it is really called:")
            print("  HASH  handle   (S)")
            print("  RANGE platform (S)")
            print("\nAlso confirm the intel Lambda's role has dynamodb:UpdateItem on it.")
        elif code == "AccessDeniedException":
            print("\nThe caller cannot even describe the table. If the Lambda role is")
            print("equally restricted, that alone explains every rejected write.")
        return 1

    schema = [(k["AttributeName"], k["KeyType"]) for k in desc["KeySchema"]]
    print(f"table   : {TABLE}")
    print(f"items   : {desc.get('ItemCount', 0)} (ItemCount updates ~every 6h)")
    print(f"status  : {desc.get('TableStatus')}")
    print(f"key     : {schema}")
    print(f"expected: {EXPECTED}")

    if schema != EXPECTED:
        print("\nMISMATCH. This is the bug. The monitor keys every write on")
        print('Key={"handle": ..., "platform": "telegram"}, which DynamoDB rejects')
        print("with ValidationException against the schema above, on every handle,")
        print("on every run. Fix by aligning _store_operator_identities() to the")
        print("real schema, or by recreating the table to match.")
        return 1

    print("\nKey schema matches what the monitor writes.")

    resp = ddb.scan(TableName=TABLE, Limit=200)
    items = resp.get("Items", [])
    if not items:
        print("Table is EMPTY. Schema is right, so look at the IAM role next:")
        print("  the intel Lambda needs dynamodb:UpdateItem on this table.")
        print("  A denial is caught and logged, never raised, so it is silent.")
        return 1

    def ts(i):
        return i.get("last_seen", {}).get("S", "")

    items.sort(key=ts, reverse=True)
    newest = ts(items[0])
    print(f"\n{len(items)} item(s) sampled. Most recent last_seen: {newest or 'unset'}")
    for i in items[:5]:
        print(f"  {i.get('handle',{}).get('S','?'):<28} "
              f"sightings={i.get('sightings',{}).get('N','?'):<5} last_seen={ts(i)}")
    if newest:
        try:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(newest)
            print(f"\nNewest sighting is {age.days}d {age.seconds // 3600}h old.")
            if age.days >= 1:
                print("Writes worked at some point and have since stopped. Compare that")
                print("date against the last deploy of relayshield-intel-monitor.")
        except ValueError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
