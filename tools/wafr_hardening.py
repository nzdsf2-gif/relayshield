#!/usr/bin/env python3
"""Three Well-Architected Reliability fixes in one tool. Dry run by default.

    AWS_PROFILE=relayshield python3 tools/wafr_hardening.py                      # read-only, all steps
    AWS_PROFILE=relayshield python3 tools/wafr_hardening.py --step alarm         # one step
    AWS_PROFILE=relayshield python3 tools/wafr_hardening.py --apply              # make the changes

Steps (the numbers are in tools/wafr_hardening_spec.json):

  concurrency  Reserved concurrency on the functions that must never be starved (REL 7, REL 10). A reserved
               value is also a CAP, so it is set only where there is none; a DIFFERENT existing value is
               reported, never overwritten. Refuses if it would take the account's unreserved pool below 100,
               which is AWS's floor.
  alarm        CloudWatch alarms on relayshield-api: errors, throttles, and concurrency as a share of its
               reserved value (REL 6, OPS). On 2026-10-05 and 2026-10-11 the API had init outages and nothing
               alarmed. Notifies the SAME targets the existing Lambda error alarms use, found by reading them,
               or --sns-topic. With neither, the step is blocked: an alarm that tells nobody is a dashboard.
  retention    Set retention on log groups that have none (they keep logs forever and cost money forever).
               Setting retention DELETES older events, so the dry run lists each group with its size and age.
               Groups that already have a retention, of any length, are left alone.

Never touches a resource it was not told about, and refuses to run unless the credentials resolve to the
RelayShield account, because the shell default profile is the pre-audit account.
"""
import argparse
import json
import sys
import time
from pathlib import Path

SPEC = Path(__file__).resolve().parent / "wafr_hardening_spec.json"
UNRESERVED_FLOOR = 100  # AWS requires this much of the account limit to stay unreserved
STEPS = ("concurrency", "alarm", "retention")


# ---------------------------------------------------------------- concurrency
def plan_concurrency(lam, spec):
    """[(function, state, detail)]; state: ok | todo | conflict | missing | blocked."""
    want = spec["reserved_concurrency"]
    unreserved = lam.get_account_settings()["AccountLimit"]["UnreservedConcurrentExecutions"]
    rows, take = [], 0
    for fn, n in want.items():
        try:
            have = lam.get_function_concurrency(FunctionName=fn).get("ReservedConcurrentExecutions")
        except Exception as e:
            code = getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)
            rows.append([fn, "missing", code, n])
            continue
        if have is None:
            rows.append([fn, "todo", f"reserve {n}", n])
            take += n
        elif have == n:
            rows.append([fn, "ok", f"already {n}", n])
        else:
            rows.append([fn, "conflict", f"already reserved {have}, spec says {n}; not changed", n])
    if unreserved - take < UNRESERVED_FLOOR:
        rows = [[f, "blocked", f"reserving {take} would leave {unreserved - take} unreserved; AWS needs {UNRESERVED_FLOOR}", n]
                if s == "todo" else [f, s, d, n] for f, s, d, n in rows]
    return [tuple(r[:3]) for r in rows], {r[0]: r[3] for r in rows}


def apply_concurrency(lam, rows, wanted):
    for fn, state, _d in rows:
        if state == "todo":
            lam.put_function_concurrency(FunctionName=fn, ReservedConcurrentExecutions=wanted[fn])
            yield fn


# ---------------------------------------------------------------------- alarm
def discover_actions(cw):
    """AlarmActions of the existing Lambda Errors alarms: who already gets told."""
    seen, token = [], None
    while True:
        r = cw.describe_alarms(AlarmTypes=["MetricAlarm"], **({"NextToken": token} if token else {}))
        for a in r.get("MetricAlarms", []):
            if a.get("Namespace") == "AWS/Lambda" and a.get("MetricName") == "Errors":
                for act in a.get("AlarmActions", []):
                    if act not in seen:
                        seen.append(act)
        token = r.get("NextToken")
        if not token:
            return seen


def alarm_defs(spec, actions):
    a, fn = spec["api_alarm"], spec["api_alarm"]["function"]
    dim = [{"Name": "FunctionName", "Value": fn}]
    common = dict(Namespace="AWS/Lambda", Dimensions=dim, Period=300, EvaluationPeriods=1, DatapointsToAlarm=1,
                  ComparisonOperator="GreaterThanOrEqualToThreshold", TreatMissingData="notBreaching",
                  AlarmActions=actions)
    out = [
        dict(AlarmName=f"{fn}-errors", MetricName="Errors", Statistic="Sum", Threshold=float(a["errors_per_5min"]),
             AlarmDescription="Lambda errors on the public API, including init failures (ImportModuleError, SyntaxError).", **common),
        dict(AlarmName=f"{fn}-throttles", MetricName="Throttles", Statistic="Sum", Threshold=float(a["throttles_per_5min"]),
             AlarmDescription="Throttled invocations on the public API.", **common),
    ]
    reserved = spec["reserved_concurrency"].get(fn)
    if reserved:
        out.append(dict(AlarmName=f"{fn}-concurrency-high", MetricName="ConcurrentExecutions", Statistic="Maximum",
                        Threshold=float(reserved * a["concurrency_share_of_reserved"]),
                        AlarmDescription="Public API concurrency is near its reserved value.", **common))
    return out


def plan_alarm(cw, spec, sns_topic):
    actions = [sns_topic] if sns_topic else discover_actions(cw)
    if not actions:
        return [("(all)", "blocked", "no existing Lambda error alarm has an action to copy; pass --sns-topic <arn>")], [], actions
    rows, defs = [], alarm_defs(spec, actions)
    for d in defs:
        cur = cw.describe_alarms(AlarmNames=[d["AlarmName"]]).get("MetricAlarms", [])
        if not cur:
            rows.append((d["AlarmName"], "todo", f"create, threshold {d['Threshold']:g}"))
        elif (cur[0].get("Threshold"), cur[0].get("AlarmActions")) == (d["Threshold"], d["AlarmActions"]):
            rows.append((d["AlarmName"], "ok", "already as specified"))
        else:
            rows.append((d["AlarmName"], "todo", f"update, threshold {cur[0].get('Threshold'):g} -> {d['Threshold']:g}"))
    return rows, defs, actions


# ------------------------------------------------------------------ retention
def plan_retention(logs, spec):
    rows, token = [], None
    while True:
        r = logs.describe_log_groups(**({"nextToken": token} if token else {}))
        for g in r.get("logGroups", []):
            if "retentionInDays" in g:
                rows.append((g["logGroupName"], "ok", f"{g['retentionInDays']} days"))
            else:
                age = (time.time() * 1000 - g.get("creationTime", 0)) / 86_400_000
                rows.append((g["logGroupName"], "todo",
                             f"no retention; {g.get('storedBytes', 0):,} bytes, created {age:.0f} days ago; "
                             f"events older than {spec['log_retention_days']} days will be deleted"))
        token = r.get("nextToken")
        if not token:
            return rows


# ----------------------------------------------------------------------- main
def run(clients, account_of, spec, apply, steps, sns_topic=None, out=print):
    got = account_of()
    if got != spec["account"]:
        out(f"Refusing to run: credentials resolve to account {got}, not {spec['account']}. Use AWS_PROFILE=relayshield.")
        return 2
    attention = False
    for step in steps:
        out(f"\n== {step}")
        if step == "concurrency":
            rows, wanted = plan_concurrency(clients["lambda"], spec)
            done = list(apply_concurrency(clients["lambda"], rows, wanted)) if apply else []
        elif step == "alarm":
            rows, defs, _ = plan_alarm(clients["cloudwatch"], spec, sns_topic)
            done = []
            if apply:
                for d in defs:
                    if any(r[0] == d["AlarmName"] and r[1] == "todo" for r in rows):
                        clients["cloudwatch"].put_metric_alarm(**d)
                        done.append(d["AlarmName"])
        else:
            rows = plan_retention(clients["logs"], spec)
            done = []
            if apply:
                for name, state, _d in rows:
                    if state == "todo":
                        clients["logs"].put_retention_policy(logGroupName=name, retentionInDays=spec["log_retention_days"])
                        done.append(name)
        for name, state, detail in rows:
            if state != "ok" or step != "retention":
                out(f"  {state.upper():<9} {name}  {detail}".rstrip())
        ok = sum(r[1] == "ok" for r in rows)
        todo = sum(r[1] == "todo" for r in rows)
        bad = [r for r in rows if r[1] in ("conflict", "missing", "blocked")]
        attention = attention or bool(bad)
        for name in done:
            out(f"  CHANGED   {name}")
        out(f"  {step}: {ok} already fine, {todo} to change, {len(bad)} need attention.")
    if not apply:
        out("\nDry run only. Re-run with --apply to make the changes.")
    return 1 if attention else 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--step", choices=STEPS + ("all",), default="all")
    ap.add_argument("--sns-topic", default=None)
    ap.add_argument("--spec", default=str(SPEC))
    a = ap.parse_args(argv)
    spec = json.load(open(a.spec))
    import boto3
    r = spec["region"]
    clients = {"lambda": boto3.client("lambda", region_name=r), "cloudwatch": boto3.client("cloudwatch", region_name=r),
               "logs": boto3.client("logs", region_name=r)}
    sts = boto3.client("sts", region_name=r)
    steps = STEPS if a.step == "all" else (a.step,)
    return run(clients, lambda: sts.get_caller_identity()["Account"], spec, a.apply, steps, a.sns_topic)


if __name__ == "__main__":
    sys.exit(main())
