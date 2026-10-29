#!/usr/bin/env python3
"""Put the Stripe webhook behind a queue (WAFR REL 4, "Implement loosely coupled dependencies"). Dry run by default.

    AWS_PROFILE=relayshield python3 tools/wafr_stripe_queue.py                    # read-only: queues, access, consumer
    AWS_PROFILE=relayshield python3 tools/wafr_stripe_queue.py --apply            # build the plumbing, still OFF
    AWS_PROFILE=relayshield python3 tools/wafr_stripe_queue.py --step enable --apply    # switch the webhook onto the queue
    AWS_PROFILE=relayshield python3 tools/wafr_stripe_queue.py --step disable --apply   # switch it back

The handler (relayshield_stripe_webhook.py) has a queue mode that is OFF unless the Lambda environment variable
STRIPE_EVENT_QUEUE_URL is set. So there are two separate acts, and the second is a deliberate step you name:

  queues    The main queue (SSE-SQS, 14 days, visibility timeout = 6 x the function's own timeout, read from the
            function) and a dead-letter queue it redrives to after max_receive_count failed receives. An existing
            queue that differs is reported, never changed.
  access    The function's execution role needs sqs:SendMessage (the door) and ReceiveMessage, DeleteMessage and
            GetQueueAttributes (the consumer) on the main queue. Checked with the IAM simulator; if missing, one
            customer-managed policy scoped to that queue is created and attached, only if the role has room under
            IAM's 10-managed-policy limit (else BLOCKED: the IAM role split comes first).
  consumer  An SQS event source mapping on the same function: batch size 1, maximum concurrency 2. Created only if
            none exists for this queue. With the flag still off this changes nothing: the queue is empty.
  enable    (never part of the default run) Sets STRIPE_EVENT_QUEUE_URL, MERGED into the existing variables:
            update_function_configuration REPLACES the whole Environment, so a naive write would delete
            DAY3_LAMBDA_ARN and DAY3_SCHEDULER_ROLE_ARN. Refuses unless the mapping is enabled, the role can use
            the queue, and the DEPLOYED code contains queue mode (read from the live artifact, not from git).
  disable   (never part of the default run) Removes the variable. The consumer keeps draining what is queued.

Never touches a resource it was not told about, and refuses to run unless the credentials resolve to the
RelayShield account, because the shell default profile is the pre-audit account.
"""
import argparse
import io
import json
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

SPEC = Path(__file__).resolve().parent / "wafr_stripe_queue_spec.json"
STEPS = ("queues", "access", "consumer", "enable", "disable")
DEFAULT_STEPS = ("queues", "access", "consumer")
NO_QUEUE = ("AWS.SimpleQueueService.NonExistentQueue", "QueueDoesNotExist")
QUEUE_ACTIONS = ["sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
MARKERS = (b"STRIPE_EVENT_QUEUE_URL", b"process_queue_batch")


def code_of(e):
    return getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)


def role_name(arn):
    return arn.rsplit("/", 1)[-1]


def arn_of(spec, name):
    return f"arn:aws:sqs:{spec['region']}:{spec['account']}:{name}"


def policy_arn_of(spec):
    return f"arn:aws:iam::{spec['account']}:policy/{spec['policy']['name']}"


def check_spec(spec):
    q, c = spec["queue"], spec["consumer"]
    if not 60 <= q["retention_seconds"] <= 1209600:
        return "queue.retention_seconds must be 60 to 1209600 (SQS's limit)"
    if not 1 <= q["max_receive_count"] <= 1000:
        return "queue.max_receive_count must be 1 to 1000 (SQS's limit)"
    if not 1 <= c["batch_size"] <= 10:
        return "consumer.batch_size must be 1 to 10 for a standard queue without a batching window"
    if not 2 <= c["max_concurrency"] <= 1000:
        return "consumer.max_concurrency must be 2 to 1000 (Lambda's limit)"
    return None


def read_function(lam, spec):
    try:
        return lam.get_function_configuration(FunctionName=spec["function"]), None
    except Exception as e:
        return None, f"cannot read {spec['function']}: {code_of(e)}"


# --------------------------------------------------------------------- queues
def desired_queue_attrs(spec, timeout):
    q = spec["queue"]
    main = {"MessageRetentionPeriod": str(q["retention_seconds"]), "SqsManagedSseEnabled": "true",
            "VisibilityTimeout": str(timeout * q["visibility_multiplier"]),
            "RedrivePolicy": json.dumps({"deadLetterTargetArn": arn_of(spec, q["dlq_name"]), "maxReceiveCount": q["max_receive_count"]})}
    dlq = {"MessageRetentionPeriod": str(q["retention_seconds"]), "SqsManagedSseEnabled": "true"}
    return main, dlq


def same_attr(k, have, want):
    if k == "RedrivePolicy":
        try:
            a, b = json.loads(have or "{}"), json.loads(want)
        except ValueError:
            return False
        return a.get("deadLetterTargetArn") == b["deadLetterTargetArn"] and int(a.get("maxReceiveCount", -1)) == b["maxReceiveCount"]
    return have == want


def plan_one_queue(sqs, name, want):
    try:
        url = sqs.get_queue_url(QueueName=name)["QueueUrl"]
    except Exception as e:
        if code_of(e) not in NO_QUEUE:
            return (name, "blocked", f"cannot read the queue: {code_of(e)}"), None
        return (name, "todo", "create"), (name, lambda: sqs.create_queue(QueueName=name, Attributes=want))
    have = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=list(want)).get("Attributes", {})
    diff = [f"{k} is {have.get(k)!r}, spec says {v!r}" for k, v in want.items() if not same_attr(k, have.get(k), v)]
    if diff:
        return (name, "conflict", "exists but " + "; ".join(diff) + "; not changed"), None
    return (name, "ok", "exists as specified"), None


def plan_queues(clients, spec):
    cfg, why = read_function(clients["lambda"], spec)
    if not cfg:
        return [(spec["queue"]["name"], "blocked", why)], []
    main, dlq = desired_queue_attrs(spec, cfg["Timeout"])
    rows, actions = [], []
    for name, want in ((spec["queue"]["dlq_name"], dlq), (spec["queue"]["name"], main)):  # DLQ first: the main queue points at it
        row, act = plan_one_queue(clients["sqs"], name, want)
        rows.append(row)
        if act:
            actions.append(act)
    return rows, actions


# --------------------------------------------------------------------- access
def can_use(iam, role_arn, queue_arn):
    """True / False, or an error code string when the simulator cannot be used."""
    try:
        r = iam.simulate_principal_policy(PolicySourceArn=role_arn, ActionNames=QUEUE_ACTIONS, ResourceArns=[queue_arn])
    except Exception as e:
        return code_of(e)
    res = r.get("EvaluationResults", [])
    return len(res) == len(QUEUE_ACTIONS) and all(x.get("EvalDecision") == "allowed" for x in res)


def policy_doc(queue_arn):
    return {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": QUEUE_ACTIONS, "Resource": queue_arn}]}


def plan_access(clients, spec):
    iam, name = clients["iam"], spec["policy"]["name"]
    cfg, why = read_function(clients["lambda"], spec)
    if not cfg:
        return [(name, "blocked", why)], []
    role, qarn = cfg["Role"], arn_of(spec, spec["queue"]["name"])
    rn = role_name(role)
    ok = can_use(iam, role, qarn)
    if ok is True:
        return [(rn, "ok", f"{rn} may use the Stripe event queue")], []
    if ok is not False:
        return [(rn, "blocked", f"cannot check queue permissions on {rn}: {ok}")], []
    pol = policy_arn_of(spec)
    try:
        attached = iam.list_attached_role_policies(RoleName=rn).get("AttachedPolicies", [])
    except Exception as e:
        return [(rn, "blocked", f"cannot list policies on {rn}: {code_of(e)}")], []
    if any(p["PolicyArn"] == pol for p in attached):
        return [(rn, "blocked", f"{rn} already has {name} attached yet still cannot use the queue; something else denies it")], []
    limit = spec["policy"]["iam_managed_policy_limit"]
    if len(attached) >= limit:
        return [(rn, "blocked", f"{rn} already has {len(attached)} managed policies (limit {limit}); attaching would fail. "
                                "Needs the IAM role split (iam_role_split.md) first")], []
    rows = [(rn, "todo", f"attach {name} to {rn} ({len(attached)} managed policies today)")]
    actions = []
    try:
        iam.get_policy(PolicyArn=pol)
    except Exception as e:
        if code_of(e) != "NoSuchEntity":
            return [(name, "blocked", f"cannot read the policy: {code_of(e)}")], []
        rows.insert(0, (name, "todo", f"create customer-managed policy: {', '.join(QUEUE_ACTIONS)} on {qarn} only"))
        actions.append((name, lambda: iam.create_policy(
            PolicyName=name, PolicyDocument=json.dumps(policy_doc(qarn)),
            Description="Stripe webhook event queue: send from the door, receive and delete in the consumer (WAFR REL 4).")))
    actions.append((rn, lambda: iam.attach_role_policy(RoleName=rn, PolicyArn=pol)))
    return rows, actions


# ------------------------------------------------------------------- consumer
def mapping_for(lam, spec):
    r = lam.list_event_source_mappings(FunctionName=spec["function"], EventSourceArn=arn_of(spec, spec["queue"]["name"]))
    ms = r.get("EventSourceMappings", [])
    return ms[0] if ms else None


def create_mapping(lam, spec, sleep, tries=8, wait=8):
    """Lambda checks the role's queue permissions when the mapping is created, and an IAM change takes a moment to
    be visible to it, so a permission-shaped refusal is retried for about a minute; anything else is raised."""
    c = spec["consumer"]
    for i in range(tries):
        try:
            return lam.create_event_source_mapping(
                EventSourceArn=arn_of(spec, spec["queue"]["name"]), FunctionName=spec["function"], BatchSize=c["batch_size"],
                Enabled=True, ScalingConfig={"MaximumConcurrency": c["max_concurrency"]})
        except Exception as e:
            msg = str(e).lower()
            if code_of(e) != "InvalidParameterValueException" or i == tries - 1 or not any(w in msg for w in ("role", "permission", "sqs")):
                raise
            sleep(wait)


def plan_consumer(clients, spec, apply, sleep):
    lam, name = clients["lambda"], f"{spec['function']} <- {spec['queue']['name']}"
    m = mapping_for(lam, spec)
    c = spec["consumer"]
    if m:
        scaling = (m.get("ScalingConfig") or {}).get("MaximumConcurrency")
        if m.get("BatchSize") == c["batch_size"] and scaling == c["max_concurrency"]:
            return [(name, "ok", f"mapping {m.get('UUID', '')} exists, state {m.get('State', '')}")], []
        return [(name, "conflict", f"mapping exists (batch size {m.get('BatchSize')}, max concurrency {scaling}); "
                                   f"spec says {c['batch_size']} and {c['max_concurrency']}; not changed")], []
    cfg, why = read_function(lam, spec)
    if not cfg:
        return [(name, "blocked", why)], []
    ok = can_use(clients["iam"], cfg["Role"], arn_of(spec, spec["queue"]["name"]))
    if ok is not True and apply:
        return [(name, "blocked", f"{role_name(cfg['Role'])} cannot use the queue yet, so no mapping is created")], []
    note = "" if ok is True else " (after the access step grants the role)"
    return [(name, "todo", f"create mapping, batch size {c['batch_size']}, max concurrency {c['max_concurrency']}{note}")], \
        [(name, lambda: create_mapping(lam, spec, sleep))]


# ------------------------------------------------------------- enable/disable
def code_has_queue_mode(zip_bytes):
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        for n in z.namelist():
            if n.endswith(".py") and all(m in z.read(n) for m in MARKERS):
                return True
    return False


def fetch_url(url):
    with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310  (a presigned S3 URL that Lambda itself returned)
        return r.read()


def env_of(cfg):
    env = cfg.get("Environment") or {}
    return env.get("Variables") or {}, env.get("Error")


def plan_enable(clients, spec, fetch):
    lam, var, name = clients["lambda"], spec["env_var"], spec["function"]
    cfg, why = read_function(lam, spec)
    if not cfg:
        return [(name, "blocked", why)], []
    vars_, err = env_of(cfg)
    if err:
        return [(name, "blocked", f"Lambda cannot read this function's environment ({err.get('ErrorCode')}); not touching it")], []
    try:
        url = clients["sqs"].get_queue_url(QueueName=spec["queue"]["name"])["QueueUrl"]
    except Exception as e:
        return [(name, "blocked", f"the queue is not readable ({code_of(e)}); run the queues step first")], []
    if vars_.get(var) == url:
        return [(name, "ok", f"{var} is already set to this queue")], []
    if var in vars_:
        return [(name, "conflict", f"{var} is already set to a different value; not changed")], []
    m = mapping_for(lam, spec)
    if not m or m.get("State") not in ("Enabled", "Enabling", "Creating"):
        return [(name, "blocked", "no enabled SQS mapping for this queue; run the consumer step first. Enabling now would queue events that nothing processes")], []
    ok = can_use(clients["iam"], cfg["Role"], arn_of(spec, spec["queue"]["name"]))
    if ok is not True:
        return [(name, "blocked", f"{role_name(cfg['Role'])} cannot use the queue ({ok}); run the access step first")], []
    try:
        loc = lam.get_function(FunctionName=name)["Code"]["Location"]
        has = code_has_queue_mode(fetch(loc))
    except Exception as e:
        return [(name, "blocked", f"cannot read the deployed code to confirm queue mode is in it: {code_of(e)}")], []
    if not has:
        return [(name, "blocked", "the DEPLOYED code does not contain queue mode yet. Merge it and let deploy_lambdas.yml run first; "
                                  "enabling now would queue events and the old code would never process them")], []
    merged = {**vars_, var: url}
    return [(name, "todo", f"set {var} (merged with {len(vars_)} existing variable(s): {', '.join(sorted(vars_)) or 'none'})")], \
        [(name, lambda: lam.update_function_configuration(FunctionName=name, Environment={"Variables": merged}))]


def plan_disable(clients, spec):
    lam, var, name = clients["lambda"], spec["env_var"], spec["function"]
    cfg, why = read_function(lam, spec)
    if not cfg:
        return [(name, "blocked", why)], []
    vars_, err = env_of(cfg)
    if err:
        return [(name, "blocked", f"Lambda cannot read this function's environment ({err.get('ErrorCode')}); not touching it")], []
    if var not in vars_:
        return [(name, "ok", f"{var} is not set; the webhook is already synchronous")], []
    kept = {k: v for k, v in vars_.items() if k != var}
    return [(name, "todo", f"remove {var}, keeping {len(kept)} other variable(s). The consumer keeps draining the queue")], \
        [(name, lambda: lam.update_function_configuration(FunctionName=name, Environment={"Variables": kept}))]


# ----------------------------------------------------------------------- main
def run(clients, account_of, spec, apply, steps, out=print, sleep=time.sleep, fetch=fetch_url):
    got = account_of()
    if got != spec["account"]:
        out(f"Refusing to run: credentials resolve to account {got}, not {spec['account']}. Use AWS_PROFILE=relayshield.")
        return 2
    bad_spec = check_spec(spec)
    if bad_spec:
        out(f"Refusing to run: {bad_spec}.")
        return 2
    attention = False
    for step in steps:
        out(f"\n== {step}")
        rows, actions = {"queues": lambda: plan_queues(clients, spec), "access": lambda: plan_access(clients, spec),
                         "consumer": lambda: plan_consumer(clients, spec, apply, sleep),
                         "enable": lambda: plan_enable(clients, spec, fetch), "disable": lambda: plan_disable(clients, spec)}[step]()
        for name, state, detail in rows:
            out(f"  {state.upper():<9} {name}  {detail}".rstrip())
        if apply:
            for name, act in actions:
                act()
                out(f"  CHANGED   {name}")
        bad = [r for r in rows if r[1] in ("conflict", "missing", "blocked")]
        attention = attention or bool(bad)
        out(f"  {step}: {sum(r[1] == 'ok' for r in rows)} already fine, {sum(r[1] == 'todo' for r in rows)} to change, "
            f"{len(bad)} need attention.")
    if apply and "enable" in steps and not attention:
        out("\nThe Stripe webhook now queues checkout events. Watch the DLQ and the failure alarm. To go back: --step disable --apply")
    if not apply:
        out("\nDry run only. Re-run with --apply to make the changes.")
    return 1 if attention else 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--step", choices=STEPS + ("all",), default="all")
    ap.add_argument("--spec", default=str(SPEC))
    a = ap.parse_args(argv)
    spec = json.load(open(a.spec))
    import boto3
    r = spec["region"]
    clients = {k: boto3.client(k, region_name=r) for k in ("lambda", "iam", "sqs")}
    sts = boto3.client("sts", region_name=r)
    steps = DEFAULT_STEPS if a.step == "all" else (a.step,)
    return run(clients, lambda: sts.get_caller_identity()["Account"], spec, a.apply, steps)


if __name__ == "__main__":
    sys.exit(main())
