#!/usr/bin/env python3
"""Tag the AWS resources behind Bundle D for Partner Revenue Measurement (PRM). Dry run by default.

    AWS_PROFILE=relayshield python3 tools/prm_tag_resources.py            # read-only: current tag state
    AWS_PROFILE=relayshield python3 tools/prm_tag_resources.py --apply    # add the tag

The list of resources is aws_marketplace/prm_tag_spec.json. This tool only ADDS one tag. It never
removes or changes another tag, and it REFUSES to overwrite an existing `aws-apn-id` that holds a
different value (a resource carries one such tag, and replacing another partner's or product's
tag would silently re-attribute its spend). A resource that is missing is reported, not created.
A wrong AWS account is refused, because the shell default profile is the pre-audit account.
"""
import argparse
import json
import sys
from pathlib import Path

SPEC = Path(__file__).resolve().parent.parent / "aws_marketplace" / "prm_tag_spec.json"


def arns(spec, account):
    region = spec["region"]
    for n in spec["lambda_functions"]:
        yield "lambda", n, f"arn:aws:lambda:{region}:{account}:function:{n}"
    for i in spec["rest_api_ids"]:
        yield "apigateway", i, f"arn:aws:apigateway:{region}::/restapis/{i}"
    for t in spec["dynamodb_tables"]:
        yield "dynamodb", t, f"arn:aws:dynamodb:{region}:{account}:table/{t}"


def read_tags(clients, kind, arn):
    if kind == "lambda":
        return clients["lambda"].list_tags(Resource=arn).get("Tags", {})
    if kind == "apigateway":
        return clients["apigateway"].get_tags(resourceArn=arn).get("tags", {})
    items = clients["dynamodb"].list_tags_of_resource(ResourceArn=arn).get("Tags", [])
    return {t["Key"]: t["Value"] for t in items}


def write_tag(clients, kind, arn, key, value):
    if kind == "lambda":
        clients["lambda"].tag_resource(Resource=arn, Tags={key: value})
    elif kind == "apigateway":
        clients["apigateway"].tag_resource(resourceArn=arn, tags={key: value})
    else:
        clients["dynamodb"].tag_resource(ResourceArn=arn, Tags=[{"Key": key, "Value": value}])


def plan(clients, spec, account):
    """Return [(kind, name, arn, state, detail)]; state in ok | todo | conflict | missing."""
    key, value = spec["tag_key"], spec["tag_value"]
    rows = []
    for kind, name, arn in arns(spec, account):
        try:
            tags = read_tags(clients, kind, arn)
        except Exception as e:  # a missing resource is a finding, not a crash
            code = getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)
            rows.append((kind, name, arn, "missing", code))
            continue
        have = tags.get(key)
        if have is None:
            rows.append((kind, name, arn, "todo", ""))
        elif have == value:
            rows.append((kind, name, arn, "ok", "already tagged"))
        else:
            rows.append((kind, name, arn, "conflict", f"{key} is already {have!r}"))
    return rows


def run(clients, account_of, spec, apply, out=print):
    account = spec["account"]
    got = account_of()
    if got != account:
        out(f"Refusing to run: credentials resolve to account {got}, not {account}. Use AWS_PROFILE=relayshield.")
        return 2
    rows = plan(clients, spec, account)
    for kind, name, _arn, state, detail in rows:
        out(f"  {state.upper():<9} {kind:<10} {name}  {detail}".rstrip())
    todo = [r for r in rows if r[3] == "todo"]
    bad = [r for r in rows if r[3] in ("conflict", "missing")]
    if apply:
        for kind, name, arn, _s, _d in todo:
            write_tag(clients, kind, arn, spec["tag_key"], spec["tag_value"])
            out(f"  TAGGED    {kind:<10} {name}")
    out(f"\n{spec['tag_key']} = {spec['tag_value']}: {len(todo)} to tag, "
        f"{sum(r[3] == 'ok' for r in rows)} already done, {len(bad)} need attention.")
    if not apply and todo:
        out("Dry run only. Re-run with --apply to add the tag.")
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--spec", default=str(SPEC))
    a = ap.parse_args(argv)
    spec = json.load(open(a.spec))
    import boto3
    r = spec["region"]
    clients = {"lambda": boto3.client("lambda", region_name=r), "apigateway": boto3.client("apigateway", region_name=r),
               "dynamodb": boto3.client("dynamodb", region_name=r)}
    sts = boto3.client("sts", region_name=r)
    return run(clients, lambda: sts.get_caller_identity()["Account"], spec, a.apply)


if __name__ == "__main__":
    sys.exit(main())
