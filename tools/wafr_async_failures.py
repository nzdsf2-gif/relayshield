#!/usr/bin/env python3
"""Well-Architected REL 5 fix: limit async retries, bound the event age, catch what fails. Dry run by default.

    AWS_PROFILE=relayshield python3 tools/wafr_async_failures.py                   # read-only, all steps
    AWS_PROFILE=relayshield python3 tools/wafr_async_failures.py --step access     # one step
    AWS_PROFILE=relayshield python3 tools/wafr_async_failures.py --apply           # make the changes

Practices this backs (REL 5): "Control and limit retry calls", "Fail fast and limit queues". The numbers are in
tools/wafr_async_spec.json. Steps, in the order they must run:

  queue    One SQS standard queue for failed asynchronous invocations, encrypted with SQS-managed keys, 14 days
           retention. An existing queue with different retention or no encryption is reported, never changed.
  access   Lambda sends a failed event to the queue AS THE FUNCTION'S EXECUTION ROLE, so each role must be allowed
           sqs:SendMessage on that one queue. Checked with the IAM policy simulator first. If a role cannot, one
           customer-managed policy scoped to the queue is created and attached, but only if the role has room (IAM
           allows 10 managed policies and the shared role's inline budget is already full, see CLAUDE.md). No room,
           or no right to simulate: BLOCKED, and the retry step then leaves that function alone. A destination the
           role cannot write to would drop failures silently, which is worse than having none.
  retry    Asynchronous invoke config on every function that is the Lambda target of an ENABLED EventBridge rule
           (those are the async ones; read from AWS, not listed by hand): MaximumRetryAttempts, MaximumEventAge,
           and the queue as the on-failure destination. put_function_event_invoke_config REPLACES a whole config, so
           it is called only where none exists. An existing config, even a different one, is reported and kept.
  alarm    A CloudWatch alarm when the queue is not empty, notifying the same targets the existing Lambda error
           alarms use, found by reading them. A failure queue nobody watches is a silent sink.

Never touches a resource it was not told about, and refuses to run unless the credentials resolve to the
RelayShield account, because the shell default profile is the pre-audit account.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wafr_hardening import discover_actions  # noqa: E402  (same directory; reads the existing alarm targets)

SPEC = Path(__file__).resolve().parent / "wafr_async_spec.json"
STEPS = ("queue", "access", "retry", "alarm")
LAMBDA_ARN = re.compile(r"^arn:aws:lambda:[^:]+:(\d+):function:([^:]+)(?::(.+))?$")
NO_QUEUE = ("AWS.SimpleQueueService.NonExistentQueue", "QueueDoesNotExist")


def code_of(e):
    return getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)


def role_name(arn):
    return arn.rsplit("/", 1)[-1]


def check_spec(spec):
    a = spec["async"]
    if not 0 <= a["max_retry_attempts"] <= 2:
        return "async.max_retry_attempts must be 0 to 2 (Lambda's limit)"
    if not 60 <= a["max_event_age_seconds"] <= 21600:
        return "async.max_event_age_seconds must be 60 to 21600 (Lambda's limit)"
    if not 60 <= spec["queue"]["retention_seconds"] <= 1209600:
        return "queue.retention_seconds must be 60 to 1209600 (SQS's limit)"
    return None


def queue_arn_of(spec):
    return f"arn:aws:sqs:{spec['region']}:{spec['account']}:{spec['queue']['name']}"


def policy_arn_of(spec):
    return f"arn:aws:iam::{spec['account']}:policy/{spec['policy']['name']}"


def kw(name, qual):
    return {"FunctionName": name, **({"Qualifier": qual} if qual else {})}


def label(name, qual):
    return f"{name}:{qual}" if qual else name


# -------------------------------------------------------------------- targets
def discover_targets(events, spec):
    """Lambda functions that are targets of ENABLED EventBridge rules, plus the spec's extras, minus its excludes.
    Returns (sorted list of (name, qualifier), number of disabled rules skipped)."""
    found, disabled, token = set(), 0, None
    while True:
        r = events.list_rules(**({"NextToken": token} if token else {}))
        for rule in r.get("Rules", []):
            if rule.get("State") != "ENABLED":
                disabled += 1
                continue
            t2 = None
            while True:
                tr = events.list_targets_by_rule(Rule=rule["Name"], **({"NextToken": t2} if t2 else {}))
                for t in tr.get("Targets", []):
                    m = LAMBDA_ARN.match(t.get("Arn", ""))
                    if m and m.group(1) == spec["account"]:
                        found.add((m.group(2), m.group(3)))
                t2 = tr.get("NextToken")
                if not t2:
                    break
        token = r.get("NextToken")
        if not token:
            break
    for fn in spec["async"]["extra_functions"]:
        found.add((fn, None))
    skip = set(spec["async"]["exclude_functions"])
    return sorted(((n, q) for n, q in found if n not in skip), key=lambda t: (t[0], t[1] or "")), disabled


def resolve(lam, targets):
    """{(name, qual): ('role', arn) | ('missing', code)}"""
    out = {}
    for name, qual in targets:
        try:
            out[(name, qual)] = ("role", lam.get_function_configuration(**kw(name, qual))["Role"])
        except Exception as e:
            out[(name, qual)] = ("missing", code_of(e))
    return out


# ---------------------------------------------------------------------- queue
def plan_queue(clients, spec):
    sqs, q = clients["sqs"], spec["queue"]
    want = {"MessageRetentionPeriod": str(q["retention_seconds"]), "SqsManagedSseEnabled": "true"}
    try:
        url = sqs.get_queue_url(QueueName=q["name"])["QueueUrl"]
    except Exception as e:
        if code_of(e) not in NO_QUEUE:
            return [(q["name"], "blocked", f"cannot read the queue: {code_of(e)}")], []
        return [(q["name"], "todo", f"create standard queue, SSE-SQS on, retention {q['retention_seconds']} s")], \
            [(q["name"], lambda: sqs.create_queue(QueueName=q["name"], Attributes=want))]
    have = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=list(want)).get("Attributes", {})
    diff = [f"{k} is {have.get(k)!r}, spec says {v!r}" for k, v in want.items() if have.get(k) != v]
    if diff:
        return [(q["name"], "conflict", "queue exists but " + "; ".join(diff) + "; not changed")], []
    return [(q["name"], "ok", "exists as specified")], []


# --------------------------------------------------------------------- access
def can_send(iam, role_arn, queue_arn):
    """True / False, or an error code string when the simulator cannot be used."""
    try:
        r = iam.simulate_principal_policy(PolicySourceArn=role_arn, ActionNames=["sqs:SendMessage"], ResourceArns=[queue_arn])
    except Exception as e:
        return code_of(e)
    res = r.get("EvaluationResults", [])
    return len(res) == 1 and res[0].get("EvalDecision") == "allowed"


def plan_role(iam, spec, role_arn, queue_arn):
    """(state, detail, attach-action-or-None); the shared policy is created separately, once."""
    name = role_name(role_arn)
    ok = can_send(iam, role_arn, queue_arn)
    if ok is True:
        return "ok", f"{name} may send to the failure queue", None
    if ok is not False:
        return "blocked", f"cannot check sqs:SendMessage on {name}: {ok}", None
    pol = policy_arn_of(spec)
    try:
        attached = iam.list_attached_role_policies(RoleName=name).get("AttachedPolicies", [])
    except Exception as e:
        return "blocked", f"cannot list policies on {name}: {code_of(e)}", None
    if any(p["PolicyArn"] == pol for p in attached):
        return "blocked", f"{name} already has {spec['policy']['name']} attached yet still cannot send; something else denies it", None
    limit = spec["policy"]["iam_managed_policy_limit"]
    if len(attached) >= limit:
        return "blocked", (f"{name} already has {len(attached)} managed policies (limit {limit}); attaching would fail. "
                           "Needs the IAM role split (iam_role_split.md) first"), None
    return "todo", f"attach {spec['policy']['name']} to {name} ({len(attached)} managed policies today)", \
        lambda: iam.attach_role_policy(RoleName=name, PolicyArn=pol)


def policy_doc(queue_arn):
    return {"Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Action": "sqs:SendMessage", "Resource": queue_arn}]}


def plan_access(clients, spec, resolved):
    iam, qarn = clients["iam"], queue_arn_of(spec)
    rows, attaches, seen = [], [], set()
    for key, (kind, val) in resolved.items():
        if kind != "role" or val in seen:
            continue
        seen.add(val)
        state, detail, act = plan_role(iam, spec, val, qarn)
        rows.append((role_name(val), state, detail))
        if act:
            attaches.append((role_name(val), act))
    if not attaches:
        return rows, []
    pol, actions = policy_arn_of(spec), []
    try:
        iam.get_policy(PolicyArn=pol)
    except Exception as e:
        if code_of(e) != "NoSuchEntity":
            return rows + [(spec["policy"]["name"], "blocked", f"cannot read the policy: {code_of(e)}")], []
        rows.append((spec["policy"]["name"], "todo", f"create customer-managed policy: sqs:SendMessage on {qarn} only"))
        actions.append((spec["policy"]["name"], lambda: iam.create_policy(
            PolicyName=spec["policy"]["name"], PolicyDocument=json.dumps(policy_doc(qarn)),
            Description="Lets Lambda send failed asynchronous invocations to the relayshield failure queue (WAFR REL 5).")))
    return rows, actions + attaches


# ---------------------------------------------------------------------- retry
def wanted_config(spec):
    a = spec["async"]
    return a["max_retry_attempts"], a["max_event_age_seconds"], queue_arn_of(spec)


def put_async_config(lam, name, qual, spec, sleep, tries=8, wait=8):
    """IAM changes take a moment to be visible to Lambda's own check of the destination, so a permission-shaped
    refusal is retried for about a minute; anything else is raised at once."""
    retries, age, dest = wanted_config(spec)
    for i in range(tries):
        try:
            return lam.put_function_event_invoke_config(
                MaximumRetryAttempts=retries, MaximumEventAgeInSeconds=age,
                DestinationConfig={"OnFailure": {"Destination": dest}}, **kw(name, qual))
        except Exception as e:
            msg = str(e).lower()
            if code_of(e) != "InvalidParameterValueException" or i == tries - 1 or not any(w in msg for w in ("role", "permission", "sqs")):
                raise
            sleep(wait)


def plan_retry(clients, spec, resolved, apply, sleep):
    lam, iam, qarn = clients["lambda"], clients["iam"], queue_arn_of(spec)
    retries, age, dest = wanted_config(spec)
    rows, actions = [], []
    for (name, qual), (kind, val) in resolved.items():
        lbl = label(name, qual)
        if kind == "missing":
            rows.append((lbl, "missing", f"target of an EventBridge rule but cannot be read: {val}"))
            continue
        try:
            cur = lam.get_function_event_invoke_config(**kw(name, qual))
        except Exception as e:
            if code_of(e) != "ResourceNotFoundException":
                rows.append((lbl, "blocked", f"cannot read the async config: {code_of(e)}"))
                continue
            cur = None
        if cur is not None:
            have = (cur.get("MaximumRetryAttempts"), cur.get("MaximumEventAgeInSeconds"),
                    cur.get("DestinationConfig", {}).get("OnFailure", {}).get("Destination"))
            if have == (retries, age, dest):
                rows.append((lbl, "ok", "already as specified"))
            else:
                rows.append((lbl, "conflict", f"already configured (retries {have[0]}, max age {have[1]} s, on failure {have[2]}); not changed"))
            continue
        sendable = can_send(iam, val, qarn)
        if sendable is not True:
            state = plan_role(iam, spec, val, qarn)[0] if sendable is False else "blocked"
            if state == "todo" and not apply:
                rows.append((lbl, "todo", f"set retries {retries}, max age {age} s, on failure -> queue (after the access step grants {role_name(val)})"))
                actions.append((lbl, None))
                continue
            rows.append((lbl, "blocked", f"{role_name(val)} cannot send to the failure queue, so no destination is set"))
            continue
        rows.append((lbl, "todo", f"set retries {retries}, max age {age} s, on failure -> queue"))
        actions.append((lbl, lambda n=name, q=qual: put_async_config(lam, n, q, spec, sleep)))
    return rows, [a for a in actions if a[1]]


# ---------------------------------------------------------------------- alarm
def alarm_def(spec, actions):
    return dict(AlarmName=spec["alarm"]["name"], Namespace="AWS/SQS", MetricName="ApproximateNumberOfMessagesVisible",
                Dimensions=[{"Name": "QueueName", "Value": spec["queue"]["name"]}], Statistic="Maximum", Period=300,
                EvaluationPeriods=1, DatapointsToAlarm=1, Threshold=float(spec["alarm"]["messages_at_or_above"]),
                ComparisonOperator="GreaterThanOrEqualToThreshold", TreatMissingData="notBreaching", AlarmActions=actions,
                AlarmDescription="A failed or expired asynchronous Lambda invocation landed in the failure queue.")


def plan_alarm(clients, spec, sns_topic):
    cw, name = clients["cloudwatch"], spec["alarm"]["name"]
    actions = [sns_topic] if sns_topic else discover_actions(cw)
    if not actions:
        return [(name, "blocked", "no existing Lambda error alarm has an action to copy; pass --sns-topic <arn>")], []
    d = alarm_def(spec, actions)
    cur = cw.describe_alarms(AlarmNames=[name]).get("MetricAlarms", [])
    if cur and (cur[0].get("Threshold"), cur[0].get("AlarmActions")) == (d["Threshold"], d["AlarmActions"]):
        return [(name, "ok", "already as specified")], []
    verb = "update" if cur else "create"
    return [(name, "todo", f"{verb}: queue not empty, notifies {', '.join(actions)}")], [(name, lambda: cw.put_metric_alarm(**d))]


# ----------------------------------------------------------------------- main
def run(clients, account_of, spec, apply, steps, sns_topic=None, out=print, sleep=time.sleep):
    got = account_of()
    if got != spec["account"]:
        out(f"Refusing to run: credentials resolve to account {got}, not {spec['account']}. Use AWS_PROFILE=relayshield.")
        return 2
    bad_spec = check_spec(spec)
    if bad_spec:
        out(f"Refusing to run: {bad_spec}.")
        return 2
    attention = False
    targets, disabled = discover_targets(clients["events"], spec)
    out(f"{len(targets)} asynchronously invoked function(s) found from ENABLED EventBridge rules "
        f"({disabled} disabled rule(s) skipped). Failure queue: {queue_arn_of(spec)}")
    for step in steps:
        out(f"\n== {step}")
        if step == "queue":
            rows, actions = plan_queue(clients, spec)
        elif step == "alarm":
            rows, actions = plan_alarm(clients, spec, sns_topic)
        else:
            resolved = resolve(clients["lambda"], targets)
            rows, actions = (plan_access(clients, spec, resolved) if step == "access"
                             else plan_retry(clients, spec, resolved, apply, sleep))
        for name, state, detail in rows:
            if state != "ok":
                out(f"  {state.upper():<9} {name}  {detail}".rstrip())
        if apply:
            for name, act in actions:
                act()
                out(f"  CHANGED   {name}")
        bad = [r for r in rows if r[1] in ("conflict", "missing", "blocked")]
        attention = attention or bool(bad)
        out(f"  {step}: {sum(r[1] == 'ok' for r in rows)} already fine, {sum(r[1] == 'todo' for r in rows)} to change, "
            f"{len(bad)} need attention.")
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
    clients = {k: boto3.client(k, region_name=r) for k in ("lambda", "iam", "sqs", "events", "cloudwatch")}
    sts = boto3.client("sts", region_name=r)
    steps = STEPS if a.step == "all" else (a.step,)
    return run(clients, lambda: sts.get_caller_identity()["Account"], spec, a.apply, steps, a.sns_topic)


if __name__ == "__main__":
    sys.exit(main())
