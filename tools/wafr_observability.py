#!/usr/bin/env python3
"""Four Well-Architected observability and protection fixes in one tool. Dry run by default.

    AWS_PROFILE=relayshield python3 tools/wafr_observability.py                    # read-only, all steps
    AWS_PROFILE=relayshield python3 tools/wafr_observability.py --step tracing     # one step
    AWS_PROFILE=relayshield python3 tools/wafr_observability.py --apply            # make the changes

Steps (the numbers are in tools/wafr_observability_spec.json):

  tracing    X-Ray active tracing on the key Lambdas and on the API Gateway stage (OPS "Implement distributed
             tracing", REL "Monitor end-to-end tracing of requests"). Lambda only SENDS traces if its execution
             role may call xray:PutTraceSegments, so the role is checked first and the AWS-managed
             AWSXRayDaemonWriteAccess policy is attached only if it is missing AND the role has room (IAM allows
             10 managed policies; the shared role's inline budget is already full, see CLAUDE.md IAM section).
             No room, or no right to simulate: the Lambda rows are BLOCKED, not enabled with no traces arriving.
  throttle   Stage-level default throttle on the API (REL "Use bulkhead architectures", quotas). Set only where
             the stage has none; a DIFFERENT existing value is reported, never overwritten.
  dashboard  One CloudWatch dashboard (errors, throttles, an error-rate metric-math series, p99 duration,
             concurrency, API Gateway 4XX/5XX/latency, and the alarm states) plus saved Logs Insights queries
             (REL "Define and calculate metrics", "Analyze logs", "Monitor all components"). Queries are created
             only if no query of that name exists, because put_query_definition without an id adds a duplicate.
  quota      An alarm at a share of the ACCOUNT concurrency quota, read from Service Quotas rather than
             assumed (REL "Monitor and manage quotas"). Notifies the same targets the existing Lambda error
             alarms use, found by reading them; with none, blocked. An alarm that tells nobody is a dashboard.

Never touches a resource it was not told about, and refuses to run unless the credentials resolve to the
RelayShield account, because the shell default profile is the pre-audit account.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wafr_hardening import discover_actions  # noqa: E402  (same directory; reads the existing alarm targets)

SPEC = Path(__file__).resolve().parent / "wafr_observability_spec.json"
STEPS = ("tracing", "throttle", "dashboard", "quota")
XRAY_ACTIONS = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]


def code_of(e):
    return getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)


# -------------------------------------------------------------------- tracing
def role_name(arn):
    return arn.rsplit("/", 1)[-1]


def plan_xray_role(iam, spec, role_arn):
    """(state, detail, action-or-None) for one execution role."""
    t = spec["tracing"]
    try:
        r = iam.simulate_principal_policy(PolicySourceArn=role_arn, ActionNames=XRAY_ACTIONS, ResourceArns=["*"])
    except Exception as e:
        return "blocked", f"cannot check X-Ray permission on {role_name(role_arn)}: {code_of(e)}", None
    results = r.get("EvaluationResults", [])
    if len(results) == len(XRAY_ACTIONS) and all(x.get("EvalDecision") == "allowed" for x in results):
        return "ok", f"{role_name(role_arn)} may write X-Ray traces", None
    name = role_name(role_arn)
    try:
        attached = iam.list_attached_role_policies(RoleName=name).get("AttachedPolicies", [])
    except Exception as e:
        return "blocked", f"cannot list policies on {name}: {code_of(e)}", None
    if len(attached) >= t["iam_managed_policy_limit"]:
        return "blocked", (f"{name} already has {len(attached)} managed policies (limit {t['iam_managed_policy_limit']}); "
                           "attaching would fail. Needs the IAM role split (iam_role_split.md) first"), None
    return "todo", f"attach {t['xray_policy_arn']} to {name} ({len(attached)} managed policies today)", \
        lambda: iam.attach_role_policy(RoleName=name, PolicyArn=t["xray_policy_arn"])


def find_rest_api(apigw):
    """The one REST API, or (None, why)."""
    apis, pos = [], None
    while True:
        r = apigw.get_rest_apis(limit=500, **({"position": pos} if pos else {}))
        apis += r.get("items", [])
        pos = r.get("position")
        if not pos:
            break
    if len(apis) != 1:
        return None, f"expected exactly one REST API, found {len(apis)}: {[a['name'] for a in apis]}"
    return apis[0], None


def plan_tracing(clients, spec):
    t, rows, actions = spec["tracing"], [], []
    lam, iam, apigw = clients["lambda"], clients["iam"], clients["apigateway"]
    roles, todo_fns = {}, []
    for fn in t["lambda_functions"]:
        try:
            cfg = lam.get_function_configuration(FunctionName=fn)
        except Exception as e:
            rows.append((fn, "missing", code_of(e)))
            continue
        mode = cfg.get("TracingConfig", {}).get("Mode", "PassThrough")
        if mode == "Active":
            rows.append((fn, "ok", "tracing already Active"))
        else:
            todo_fns.append((fn, cfg["Role"]))
    for _fn, arn in todo_fns:
        if arn not in roles:
            roles[arn] = plan_xray_role(iam, spec, arn)
    for arn, (state, detail, act) in roles.items():
        rows.append((role_name(arn), state, detail))
        if act:
            actions.append((role_name(arn), act))
    for fn, arn in todo_fns:
        state = roles[arn][0]
        if state in ("ok", "todo"):
            rows.append((fn, "todo", "set TracingConfig Active"))
            actions.append((fn, lambda fn=fn: lam.update_function_configuration(FunctionName=fn, TracingConfig={"Mode": "Active"})))
        else:
            rows.append((fn, "blocked", f"role {role_name(arn)} cannot be confirmed to write traces; tracing not enabled"))
    api, why = find_rest_api(apigw)
    if not api:
        rows.append(("(api stage)", "blocked", why))
    else:
        stage = apigw.get_stage(restApiId=api["id"], stageName=t["api_stage"])
        label = f"{api['name']}/{t['api_stage']}"
        if stage.get("tracingEnabled"):
            rows.append((label, "ok", "stage tracing already enabled"))
        else:
            rows.append((label, "todo", "enable stage tracing"))
            actions.append((label, lambda: apigw.update_stage(
                restApiId=api["id"], stageName=t["api_stage"],
                patchOperations=[{"op": "replace", "path": "/tracingEnabled", "value": "true"}])))
    return rows, actions


# ------------------------------------------------------------------- throttle
def plan_throttle(clients, spec):
    t, apigw = spec["throttle"], clients["apigateway"]
    api, why = find_rest_api(apigw)
    if not api:
        return [("(api stage)", "blocked", why)], []
    ms = apigw.get_stage(restApiId=api["id"], stageName=t["stage"]).get("methodSettings", {}).get("*/*", {})
    have_rate, have_burst = ms.get("throttlingRateLimit", -1), ms.get("throttlingBurstLimit", -1)
    label = f"{api['name']}/{t['stage']}"
    unset = have_rate < 0 and have_burst < 0
    if (have_rate, have_burst) == (t["rate_limit"], t["burst_limit"]):
        return [(label, "ok", f"already {t['rate_limit']} rps, burst {t['burst_limit']}")], []
    if not unset:
        return [(label, "conflict", f"stage already throttles at {have_rate} rps, burst {have_burst}; spec says "
                                    f"{t['rate_limit']}/{t['burst_limit']}; not changed")], []
    ops = [{"op": "replace", "path": "/*/*/throttling/rateLimit", "value": str(t["rate_limit"])},
           {"op": "replace", "path": "/*/*/throttling/burstLimit", "value": str(t["burst_limit"])}]
    return [(label, "todo", f"set default {t['rate_limit']} rps, burst {t['burst_limit']} (none today)")], \
        [(label, lambda: apigw.update_stage(restApiId=api["id"], stageName=t["stage"], patchOperations=ops))]


# ------------------------------------------------------------------ dashboard
def _lam(metric, fn, stat="Sum", **extra):
    return ["AWS/Lambda", metric, "FunctionName", fn, {"stat": stat, **extra}]


def dashboard_body(spec, api_name):
    d, region, acct = spec["dashboard"], spec["region"], spec["account"]
    api, others, stage = d["api_function"], d["other_functions"], spec["tracing"]["api_stage"]

    def w(x, y, title, metrics, width=12, **props):
        return {"type": "metric", "x": x, "y": y, "width": width, "height": 6,
                "properties": {"title": title, "region": region, "view": "timeSeries", "period": 300, "metrics": metrics, **props}}
    alarms = [f"arn:aws:cloudwatch:{region}:{acct}:alarm:{api}-{s}" for s in ("errors", "throttles", "concurrency-high")]
    alarms.append(f"arn:aws:cloudwatch:{region}:{acct}:alarm:{spec['quota']['alarm_name']}")
    dim = [["ApiName", api_name, "Stage", stage]]
    return {"widgets": [
        w(0, 0, f"{api}: errors and throttles", [_lam("Errors", api), _lam("Throttles", api)]),
        {"type": "metric", "x": 12, "y": 0, "width": 12, "height": 6, "properties": {
            "title": f"{api}: error rate %", "region": region, "view": "timeSeries", "period": 300, "stat": "Sum",
            "metrics": [[{"expression": "IF(m2>0, 100*m1/m2, 0)", "label": "Error rate %", "id": "e1"}],
                        ["AWS/Lambda", "Errors", "FunctionName", api, {"id": "m1", "visible": False}],
                        ["AWS/Lambda", "Invocations", "FunctionName", api, {"id": "m2", "visible": False}]]}},
        w(0, 6, f"{api}: p99 duration (ms)", [_lam("Duration", api, "p99")]),
        w(12, 6, "Concurrent executions: API and account", [_lam("ConcurrentExecutions", api, "Maximum"),
                                                          ["AWS/Lambda", "ConcurrentExecutions", {"stat": "Maximum", "label": "Account"}]]),
        w(0, 12, "API Gateway 4XX and 5XX", [["AWS/ApiGateway", "5XXError"] + dim[0] + [{"stat": "Sum"}],
                                             ["AWS/ApiGateway", "4XXError"] + dim[0] + [{"stat": "Sum"}]]),
        w(12, 12, "API Gateway latency (ms)", [["AWS/ApiGateway", "Latency"] + dim[0] + [{"stat": "p99"}],
                                               ["AWS/ApiGateway", "IntegrationLatency"] + dim[0] + [{"stat": "p99"}]]),
        w(0, 18, "Errors, other key functions", [_lam("Errors", f) for f in others]),
        {"type": "alarm", "x": 12, "y": 18, "width": 12, "height": 6, "properties": {"title": "Alarm states", "alarms": alarms}},
    ]}


def query_defs(spec):
    g = [f"/aws/lambda/{spec['dashboard']['api_function']}"]
    p = spec["dashboard"]["query_prefix"]
    return [
        (p + "api-top-errors", g, "fields @timestamp, @message | filter @message like /ERROR|Traceback|errorType/ "
                                  "| stats count(*) as n by @message | sort n desc | limit 20"),
        (p + "api-init-failures", g, "fields @timestamp, @message | filter @message like /ImportModuleError|Runtime\\.|SyntaxError|No module named/ "
                                     "| sort @timestamp desc | limit 50"),
        (p + "api-slowest-invocations", g, "fields @timestamp, @requestId, @duration | filter @type = \"REPORT\" "
                                           "| sort @duration desc | limit 25"),
        (p + "api-cold-starts", g, "filter @type = \"REPORT\" | stats count(*) as invocations, count(@initDuration) as cold_starts, "
                                   "avg(@initDuration) as avg_init_ms by bin(1h)"),
        (p + "api-throttle-and-429", g, "fields @timestamp, @message | filter @message like /429|Throttl|Rate exceeded/ "
                                        "| sort @timestamp desc | limit 50"),
    ]


def plan_dashboard(clients, spec):
    cw, logs, apigw = clients["cloudwatch"], clients["logs"], clients["apigateway"]
    d, rows, actions = spec["dashboard"], [], []
    api, why = find_rest_api(apigw)
    if not api:
        return [("(dashboard)", "blocked", why)], []
    body = dashboard_body(spec, api["name"])
    try:
        cur = cw.get_dashboard(DashboardName=d["name"])
        same = json.loads(cur["DashboardBody"]) == body
        rows.append((d["name"], "ok" if same else "todo", "already as specified" if same else "exists, body differs; will be replaced"))
    except Exception as e:
        if code_of(e) != "ResourceNotFound":
            return [(d["name"], "blocked", f"cannot read dashboard: {code_of(e)}")], []
        rows.append((d["name"], "todo", "create"))
    if rows[-1][1] == "todo":
        actions.append((d["name"], lambda: cw.put_dashboard(DashboardName=d["name"], DashboardBody=json.dumps(body))))
    have, token = set(), None
    while True:
        r = logs.describe_query_definitions(queryDefinitionNamePrefix=d["query_prefix"], **({"nextToken": token} if token else {}))
        have |= {q["name"] for q in r.get("queryDefinitions", [])}
        token = r.get("nextToken")
        if not token:
            break
    for name, groups, text in query_defs(spec):
        if name in have:
            rows.append((name, "ok", "saved query exists"))
        else:
            rows.append((name, "todo", "create saved query"))
            actions.append((name, lambda n=name, g=groups, t=text: logs.put_query_definition(name=n, queryString=t, logGroupNames=g)))
    return rows, actions


# ---------------------------------------------------------------------- quota
def quota_alarm(spec, limit, actions):
    q = spec["quota"]
    return dict(AlarmName=q["alarm_name"], Namespace="AWS/Lambda", MetricName="ConcurrentExecutions", Statistic="Maximum",
                Period=60, EvaluationPeriods=1, DatapointsToAlarm=1, Threshold=float(limit * q["share"]),
                ComparisonOperator="GreaterThanOrEqualToThreshold", TreatMissingData="notBreaching", AlarmActions=actions,
                AlarmDescription=f"Account-wide Lambda concurrency is at {int(q['share'] * 100)}% of the account quota ({limit:g}).")


def plan_quota(clients, spec, sns_topic):
    q, cw = spec["quota"], clients["cloudwatch"]
    try:
        limit = clients["service-quotas"].get_service_quota(ServiceCode=q["service_code"], QuotaCode=q["quota_code"])["Quota"]["Value"]
    except Exception as e:
        return [(q["alarm_name"], "blocked", f"cannot read the account quota from Service Quotas: {code_of(e)}")], []
    actions = [sns_topic] if sns_topic else discover_actions(cw)
    if not actions:
        return [(q["alarm_name"], "blocked", "no existing Lambda error alarm has an action to copy; pass --sns-topic <arn>")], []
    d = quota_alarm(spec, limit, actions)
    cur = cw.describe_alarms(AlarmNames=[d["AlarmName"]]).get("MetricAlarms", [])
    if cur and (cur[0].get("Threshold"), cur[0].get("AlarmActions")) == (d["Threshold"], d["AlarmActions"]):
        return [(d["AlarmName"], "ok", f"already as specified (quota {limit:g}, threshold {d['Threshold']:g})")], []
    verb = "update" if cur else "create"
    return [(d["AlarmName"], "todo", f"{verb}: quota {limit:g}, threshold {d['Threshold']:g}, notifies {', '.join(actions)}")], \
        [(d["AlarmName"], lambda: cw.put_metric_alarm(**d))]


# ----------------------------------------------------------------------- main
def run(clients, account_of, spec, apply, steps, sns_topic=None, out=print):
    got = account_of()
    if got != spec["account"]:
        out(f"Refusing to run: credentials resolve to account {got}, not {spec['account']}. Use AWS_PROFILE=relayshield.")
        return 2
    attention = False
    for step in steps:
        out(f"\n== {step}")
        rows, actions = {"tracing": lambda: plan_tracing(clients, spec), "throttle": lambda: plan_throttle(clients, spec),
                         "dashboard": lambda: plan_dashboard(clients, spec),
                         "quota": lambda: plan_quota(clients, spec, sns_topic)}[step]()
        for name, state, detail in rows:
            out(f"  {state.upper():<9} {name}  {detail}".rstrip())
        if apply:
            for name, act in actions:
                resp = act()
                out(f"  CHANGED   {name}")
                for msg in (resp or {}).get("DashboardValidationMessages", []) if isinstance(resp, dict) else []:
                    out(f"  AWS REPORTS  {msg.get('DataPath')}: {msg.get('Message')}")
                    attention = True
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
    clients = {k: boto3.client(k, region_name=r) for k in ("lambda", "iam", "apigateway", "cloudwatch", "logs", "service-quotas")}
    sts = boto3.client("sts", region_name=r)
    steps = STEPS if a.step == "all" else (a.step,)
    return run(clients, lambda: sts.get_caller_identity()["Account"], spec, a.apply, steps, a.sns_topic)


if __name__ == "__main__":
    sys.exit(main())
