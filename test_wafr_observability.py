"""tools/wafr_observability.py: X-Ray tracing, API throttle, dashboard and saved queries, account quota alarm.

Two layers, because a fake written by the same hand as the code proves nothing about the library:
  * Fake clients test the DECISIONS (never enable tracing on a role that cannot write traces, never overwrite a
    different stage throttle, never duplicate a saved query, block the quota alarm with nobody to tell, dry run
    writes nothing, wrong account refused, IAM attach happens BEFORE the Lambda switch).
  * botocore's Stubber, over the REAL lambda / iam / apigateway / cloudwatch / logs / service-quotas models, tests
    the SHAPES: every request the tool makes is validated against the model and every response it parses is a
    legal one. Skipped (and said so) where boto3 is not installed; CI installs it from tests_requirements.txt.
NOT covered by either: that AWS accepts the dashboard body. put_dashboard returns validation messages and the
tool prints them and exits non-zero if there are any."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import wafr_observability as T  # noqa: E402

SPEC = json.load(open(ROOT / "tools" / "wafr_observability_spec.json"))
ACCT = SPEC["account"]
TOPIC = "arn:aws:sns:us-east-1:239677749008:relayshield-alerts"
ROLE = "arn:aws:iam::239677749008:role/service-role/relayshield-breach-check-role-1sapnwdl"
FUNCS = SPEC["tracing"]["lambda_functions"]


class AwsError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeLambda:
    def __init__(self, mode="PassThrough", role=ROLE, missing=()):
        self.cfg = {f: {"Role": role, "TracingConfig": {"Mode": mode}} for f in FUNCS if f not in missing}
        self.puts, self.log = [], None

    def get_function_configuration(self, FunctionName):
        if FunctionName not in self.cfg:
            raise AwsError("ResourceNotFoundException")
        return self.cfg[FunctionName]

    def update_function_configuration(self, FunctionName, TracingConfig):
        self.puts.append((FunctionName, TracingConfig["Mode"]))
        if self.log is not None:
            self.log.append(("lambda", FunctionName))


class FakeIAM:
    def __init__(self, allowed=False, attached=3, sim_error=None, log=None):
        self.allowed, self.attached, self.sim_error, self.attaches, self.log = allowed, attached, sim_error, [], log

    def simulate_principal_policy(self, PolicySourceArn, ActionNames, ResourceArns):
        if self.sim_error:
            raise AwsError(self.sim_error)
        d = "allowed" if self.allowed else "implicitDeny"
        return {"EvaluationResults": [{"EvalActionName": a, "EvalDecision": d} for a in ActionNames]}

    def list_attached_role_policies(self, RoleName):
        return {"AttachedPolicies": [{"PolicyName": f"p{i}", "PolicyArn": f"arn:aws:iam::1:policy/p{i}"} for i in range(self.attached)]}

    def attach_role_policy(self, RoleName, PolicyArn):
        self.attaches.append((RoleName, PolicyArn))
        if self.log is not None:
            self.log.append(("iam", RoleName))


class FakeAPIGW:
    def __init__(self, apis=({"id": "abc123", "name": "relayshield-api-gw"},), stage=None):
        self.apis, self.stage, self.patches = list(apis), stage if stage is not None else {}, []

    def get_rest_apis(self, **kw):
        return {"items": self.apis}

    def get_stage(self, restApiId, stageName):
        return self.stage

    def update_stage(self, restApiId, stageName, patchOperations):
        self.patches.append(patchOperations)


class FakeCW:
    def __init__(self, actions=(TOPIC,), dashboard=None, dash_error="ResourceNotFound", alarm=None, validation=()):
        self.actions, self.dashboard, self.dash_error, self.alarm = list(actions), dashboard, dash_error, alarm
        self.validation, self.dash_puts, self.alarm_puts = list(validation), [], []

    def get_dashboard(self, DashboardName):
        if self.dashboard is None:
            raise AwsError(self.dash_error)
        return {"DashboardBody": json.dumps(self.dashboard)}

    def put_dashboard(self, DashboardName, DashboardBody):
        self.dash_puts.append(json.loads(DashboardBody))
        return {"DashboardValidationMessages": self.validation}

    def describe_alarms(self, **kw):
        if "AlarmNames" in kw:
            return {"MetricAlarms": [self.alarm] if self.alarm else []}
        e = {"AlarmName": "x", "Namespace": "AWS/Lambda", "MetricName": "Errors"}
        return {"MetricAlarms": [{**e, "AlarmActions": self.actions}] if self.actions else [e]}

    def put_metric_alarm(self, **kw):
        self.alarm_puts.append(kw)


class FakeLogs:
    def __init__(self, existing=()):
        self.existing, self.puts = list(existing), []

    def describe_query_definitions(self, **kw):
        return {"queryDefinitions": [{"name": n, "queryDefinitionId": f"id{i}"} for i, n in enumerate(self.existing)]}

    def put_query_definition(self, name, queryString, logGroupNames):
        self.puts.append(name)


class FakeSQ:
    def __init__(self, value=1000.0, error=None):
        self.value, self.error = value, error

    def get_service_quota(self, ServiceCode, QuotaCode):
        if self.error:
            raise AwsError(self.error)
        return {"Quota": {"Value": self.value}}


def clients(**over):
    c = {"lambda": FakeLambda(), "iam": FakeIAM(), "apigateway": FakeAPIGW(), "cloudwatch": FakeCW(), "logs": FakeLogs(),
         "service-quotas": FakeSQ()}
    c.update(over)
    return c


def go(c, apply=False, steps=T.STEPS, acct=ACCT, spec=SPEC, sns=None):
    lines = []
    rc = T.run(c, lambda: acct, spec, apply, steps, sns, out=lines.append)
    return rc, "\n".join(lines)


class Guards(unittest.TestCase):
    def test_wrong_account_refused_and_nothing_written(self):
        c = clients()
        rc, out = go(c, apply=True, acct="620534471984")
        self.assertEqual(rc, 2)
        self.assertIn("Refusing to run", out)
        self.assertEqual((c["lambda"].puts, c["iam"].attaches, c["apigateway"].patches, c["cloudwatch"].dash_puts, c["logs"].puts), ([], [], [], [], []))

    def test_dry_run_writes_nothing_and_says_so(self):
        c = clients()
        rc, out = go(c)
        self.assertEqual((c["lambda"].puts, c["iam"].attaches, c["apigateway"].patches, c["cloudwatch"].dash_puts,
                          c["cloudwatch"].alarm_puts, c["logs"].puts), ([], [], [], [], [], []))
        self.assertIn("Dry run only", out)
        self.assertEqual(rc, 0)


class Tracing(unittest.TestCase):
    def test_role_that_can_write_traces_needs_no_attach(self):
        c = clients(iam=FakeIAM(allowed=True))
        go(c, apply=True, steps=("tracing",))
        self.assertEqual(c["iam"].attaches, [])
        self.assertEqual(sorted(c["lambda"].puts), sorted((f, "Active") for f in FUNCS))

    def test_missing_permission_with_room_attaches_policy_once_and_BEFORE_enabling(self):
        log = []
        lam, iam = FakeLambda(), FakeIAM(allowed=False, attached=3, log=log)
        lam.log = log
        go(clients(**{"lambda": lam, "iam": iam}), apply=True, steps=("tracing",))
        self.assertEqual(iam.attaches, [("relayshield-breach-check-role-1sapnwdl", SPEC["tracing"]["xray_policy_arn"])])
        self.assertEqual(log[0][0], "iam")
        self.assertEqual({x[0] for x in log[1:]}, {"lambda"})

    def test_no_room_for_a_managed_policy_blocks_every_lambda_and_changes_nothing(self):
        c = clients(iam=FakeIAM(allowed=False, attached=10))
        rc, out = go(c, apply=True, steps=("tracing",))
        self.assertEqual((c["lambda"].puts, c["iam"].attaches), ([], []))
        self.assertIn("BLOCKED", out)
        self.assertIn("iam_role_split.md", out)
        self.assertEqual(rc, 1)

    def test_cannot_simulate_blocks_rather_than_enabling_blind(self):
        c = clients(iam=FakeIAM(sim_error="AccessDenied"))
        rc, out = go(c, apply=True, steps=("tracing",))
        self.assertEqual(c["lambda"].puts, [])
        self.assertIn("AccessDenied", out)
        self.assertEqual(rc, 1)

    def test_already_active_functions_are_left_alone(self):
        c = clients(**{"lambda": FakeLambda(mode="Active")})
        go(c, apply=True, steps=("tracing",))
        self.assertEqual((c["lambda"].puts, c["iam"].attaches), ([], []))

    def test_missing_function_is_reported(self):
        c = clients(**{"lambda": FakeLambda(missing=("relayshield-mcp-http",))}, iam=FakeIAM(allowed=True))
        rc, out = go(c, apply=True, steps=("tracing",))
        self.assertIn("MISSING", out)
        self.assertEqual(rc, 1)
        self.assertEqual(len(c["lambda"].puts), len(FUNCS) - 1)

    def test_stage_tracing_enabled_with_the_right_patch(self):
        c = clients(iam=FakeIAM(allowed=True))
        go(c, apply=True, steps=("tracing",))
        self.assertEqual(c["apigateway"].patches, [[{"op": "replace", "path": "/tracingEnabled", "value": "true"}]])

    def test_stage_already_traced_is_not_patched(self):
        c = clients(iam=FakeIAM(allowed=True), apigateway=FakeAPIGW(stage={"tracingEnabled": True}))
        go(c, apply=True, steps=("tracing",))
        self.assertEqual(c["apigateway"].patches, [])

    def test_two_rest_apis_is_blocked_not_guessed(self):
        apis = ({"id": "a", "name": "one"}, {"id": "b", "name": "two"})
        c = clients(apigateway=FakeAPIGW(apis=apis), iam=FakeIAM(allowed=True))
        rc, out = go(c, apply=True, steps=("tracing", "throttle", "dashboard"))
        self.assertEqual((c["apigateway"].patches, c["cloudwatch"].dash_puts), ([], []))
        self.assertIn("expected exactly one REST API", out)
        self.assertEqual(rc, 1)


class Throttle(unittest.TestCase):
    def test_unset_stage_gets_the_spec_values(self):
        c = clients()
        go(c, apply=True, steps=("throttle",))
        self.assertEqual(c["apigateway"].patches, [[{"op": "replace", "path": "/*/*/throttling/rateLimit", "value": "100"},
                                                    {"op": "replace", "path": "/*/*/throttling/burstLimit", "value": "200"}]])

    def test_minus_one_means_unset_in_api_gateway(self):
        c = clients(apigateway=FakeAPIGW(stage={"methodSettings": {"*/*": {"throttlingRateLimit": -1.0, "throttlingBurstLimit": -1}}}))
        go(c, apply=True, steps=("throttle",))
        self.assertEqual(len(c["apigateway"].patches), 1)

    def test_a_different_existing_throttle_is_reported_not_overwritten(self):
        c = clients(apigateway=FakeAPIGW(stage={"methodSettings": {"*/*": {"throttlingRateLimit": 25.0, "throttlingBurstLimit": 50}}}))
        rc, out = go(c, apply=True, steps=("throttle",))
        self.assertEqual(c["apigateway"].patches, [])
        self.assertIn("CONFLICT", out)
        self.assertEqual(rc, 1)

    def test_matching_throttle_is_left_alone(self):
        c = clients(apigateway=FakeAPIGW(stage={"methodSettings": {"*/*": {"throttlingRateLimit": 100.0, "throttlingBurstLimit": 200}}}))
        rc, _ = go(c, apply=True, steps=("throttle",))
        self.assertEqual((c["apigateway"].patches, rc), ([], 0))


class Dashboard(unittest.TestCase):
    def test_creates_dashboard_and_all_queries(self):
        c = clients()
        go(c, apply=True, steps=("dashboard",))
        self.assertEqual(len(c["cloudwatch"].dash_puts), 1)
        self.assertEqual(sorted(c["logs"].puts), sorted(n for n, _g, _t in T.query_defs(SPEC)))

    def test_identical_dashboard_is_not_rewritten(self):
        body = T.dashboard_body(SPEC, "relayshield-api-gw")
        c = clients(cloudwatch=FakeCW(dashboard=body), logs=FakeLogs([n for n, _g, _t in T.query_defs(SPEC)]))
        go(c, apply=True, steps=("dashboard",))
        self.assertEqual((c["cloudwatch"].dash_puts, c["logs"].puts), ([], []))

    def test_changed_dashboard_is_replaced(self):
        c = clients(cloudwatch=FakeCW(dashboard={"widgets": []}))
        go(c, apply=True, steps=("dashboard",))
        self.assertEqual(len(c["cloudwatch"].dash_puts), 1)

    def test_only_missing_queries_are_created_so_none_is_duplicated(self):
        names = [n for n, _g, _t in T.query_defs(SPEC)]
        c = clients(logs=FakeLogs(names[:3]))
        go(c, apply=True, steps=("dashboard",))
        self.assertEqual(sorted(c["logs"].puts), sorted(names[3:]))

    def test_unexpected_read_error_blocks_instead_of_overwriting(self):
        c = clients(cloudwatch=FakeCW(dash_error="AccessDeniedException"))
        rc, out = go(c, apply=True, steps=("dashboard",))
        self.assertEqual(c["cloudwatch"].dash_puts, [])
        self.assertIn("BLOCKED", out)
        self.assertEqual(rc, 1)

    def test_aws_validation_messages_are_printed_and_fail_the_run(self):
        c = clients(cloudwatch=FakeCW(validation=[{"DataPath": "/widgets/0", "Message": "bad metric"}]))
        rc, out = go(c, apply=True, steps=("dashboard",))
        self.assertIn("bad metric", out)
        self.assertEqual(rc, 1)

    def test_body_is_well_formed(self):
        body = T.dashboard_body(SPEC, "relayshield-api-gw")
        json.dumps(body)
        for w in body["widgets"]:
            for k in ("type", "x", "y", "width", "height", "properties"):
                self.assertIn(k, w)
            self.assertLessEqual(w["x"] + w["width"], 24)
        expr = [w for w in body["widgets"] if "expression" in json.dumps(w)][0]
        ids = {m[-1].get("id") for m in expr["properties"]["metrics"] if isinstance(m[-1], dict)}
        self.assertTrue({"e1", "m1", "m2"} <= ids)

    def test_api_gateway_metrics_use_the_discovered_api_name_and_stage(self):
        s = json.dumps(T.dashboard_body(SPEC, "my-discovered-api"))
        self.assertIn("my-discovered-api", s)
        self.assertIn(SPEC["tracing"]["api_stage"], s)


class Quota(unittest.TestCase):
    def test_threshold_is_share_of_the_quota_read_from_service_quotas(self):
        c = clients(**{"service-quotas": FakeSQ(1000.0)})
        go(c, apply=True, steps=("quota",))
        a = c["cloudwatch"].alarm_puts[0]
        self.assertEqual((a["Threshold"], a["AlarmActions"], a["Namespace"], a["MetricName"]), (800.0, [TOPIC], "AWS/Lambda", "ConcurrentExecutions"))
        self.assertNotIn("Dimensions", a)  # account-wide, not one function

    def test_a_raised_quota_moves_the_threshold(self):
        c = clients(**{"service-quotas": FakeSQ(2000.0)})
        go(c, apply=True, steps=("quota",))
        self.assertEqual(c["cloudwatch"].alarm_puts[0]["Threshold"], 1600.0)

    def test_blocked_when_nobody_would_be_told(self):
        c = clients(cloudwatch=FakeCW(actions=()))
        rc, out = go(c, apply=True, steps=("quota",))
        self.assertEqual(c["cloudwatch"].alarm_puts, [])
        self.assertIn("BLOCKED", out)
        self.assertEqual(rc, 1)

    def test_blocked_when_the_quota_cannot_be_read(self):
        c = clients(**{"service-quotas": FakeSQ(error="AccessDeniedException")})
        rc, out = go(c, apply=True, steps=("quota",))
        self.assertEqual(c["cloudwatch"].alarm_puts, [])
        self.assertIn("AccessDeniedException", out)
        self.assertEqual(rc, 1)

    def test_unchanged_when_already_as_specified(self):
        d = T.quota_alarm(SPEC, 1000.0, [TOPIC])
        c = clients(cloudwatch=FakeCW(alarm={"AlarmName": d["AlarmName"], "Threshold": d["Threshold"], "AlarmActions": [TOPIC]}))
        go(c, apply=True, steps=("quota",))
        self.assertEqual(c["cloudwatch"].alarm_puts, [])

    def test_explicit_sns_topic_beats_discovery(self):
        other = "arn:aws:sns:us-east-1:239677749008:other"
        c = clients(cloudwatch=FakeCW(actions=()))
        go(c, apply=True, steps=("quota",), sns=other)
        self.assertEqual(c["cloudwatch"].alarm_puts[0]["AlarmActions"], [other])


try:
    import boto3
    from botocore.stub import ANY, Stubber
except ImportError:  # the repo's own suites stub boto3 out; say so rather than pass silently
    boto3 = None


@unittest.skipIf(boto3 is None, "boto3 not installed: the Stubber shape checks did not run")
class RealServiceModels(unittest.TestCase):
    """Every request validated against, and every response parsed from, the real service models."""

    def mk(self, svc):
        c = boto3.client(svc, region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="y")
        return c, Stubber(c)

    def test_full_apply_matches_the_real_models(self):
        lam, sl = self.mk("lambda")
        iam, si = self.mk("iam")
        gw, sg = self.mk("apigateway")
        cw, sc = self.mk("cloudwatch")
        lg, sx = self.mk("logs")
        sq, sqs = self.mk("service-quotas")
        role = "relayshield-breach-check-role-1sapnwdl"

        for f in FUNCS:
            sl.add_response("get_function_configuration", {"Role": ROLE, "TracingConfig": {"Mode": "PassThrough"}}, {"FunctionName": f})
        si.add_response("simulate_principal_policy", {"EvaluationResults": [{"EvalActionName": a, "EvalDecision": "implicitDeny"} for a in T.XRAY_ACTIONS]},
                        {"PolicySourceArn": ROLE, "ActionNames": T.XRAY_ACTIONS, "ResourceArns": ["*"]})
        si.add_response("list_attached_role_policies", {"AttachedPolicies": [{"PolicyName": "p", "PolicyArn": "arn:aws:iam::1:policy/p"}]},
                        {"RoleName": role})
        si.add_response("attach_role_policy", {}, {"RoleName": role, "PolicyArn": SPEC["tracing"]["xray_policy_arn"]})
        for f in FUNCS:
            sl.add_response("update_function_configuration", {"FunctionName": f}, {"FunctionName": f, "TracingConfig": {"Mode": "Active"}})

        api = {"items": [{"id": "abc123", "name": "relayshield-api-gw"}]}
        sg.add_response("get_rest_apis", api, {"limit": 500})
        sg.add_response("get_stage", {"tracingEnabled": False}, {"restApiId": "abc123", "stageName": "prod"})
        sg.add_response("update_stage", {}, {"restApiId": "abc123", "stageName": "prod",
                                             "patchOperations": [{"op": "replace", "path": "/tracingEnabled", "value": "true"}]})
        sg.add_response("get_rest_apis", api, {"limit": 500})
        sg.add_response("get_stage", {"methodSettings": {}}, {"restApiId": "abc123", "stageName": "prod"})
        sg.add_response("update_stage", {}, {"restApiId": "abc123", "stageName": "prod", "patchOperations": [
            {"op": "replace", "path": "/*/*/throttling/rateLimit", "value": "100"},
            {"op": "replace", "path": "/*/*/throttling/burstLimit", "value": "200"}]})
        sg.add_response("get_rest_apis", api, {"limit": 500})

        sc.add_client_error("get_dashboard", "ResourceNotFound", expected_params={"DashboardName": "relayshield-service-health"})
        sx.add_response("describe_query_definitions", {"queryDefinitions": []}, {"queryDefinitionNamePrefix": "relayshield/"})
        sc.add_response("put_dashboard", {"DashboardValidationMessages": []},
                        {"DashboardName": "relayshield-service-health", "DashboardBody": ANY})
        for n, g, t in T.query_defs(SPEC):
            sx.add_response("put_query_definition", {"queryDefinitionId": "id"}, {"name": n, "queryString": t, "logGroupNames": g})

        sqs.add_response("get_service_quota", {"Quota": {"Value": 1000.0}}, {"ServiceCode": "lambda", "QuotaCode": "L-B99A9384"})
        sc.add_response("describe_alarms", {"MetricAlarms": [{"AlarmName": "e", "Namespace": "AWS/Lambda", "MetricName": "Errors",
                                                              "AlarmActions": [TOPIC]}]}, {"AlarmTypes": ["MetricAlarm"]})
        sc.add_response("describe_alarms", {"MetricAlarms": []}, {"AlarmNames": ["relayshield-account-concurrency-80pct"]})
        sc.add_response("put_metric_alarm", {}, T.quota_alarm(SPEC, 1000.0, [TOPIC]))

        stubs = (sl, si, sg, sc, sx, sqs)
        for s in stubs:
            s.activate()
        try:
            rc, out = go({"lambda": lam, "iam": iam, "apigateway": gw, "cloudwatch": cw, "logs": lg, "service-quotas": sq}, apply=True)
            for s in stubs:
                s.assert_no_pending_responses()
        finally:
            for s in stubs:
                s.deactivate()
        self.assertEqual(rc, 0, out)

    def test_dashboard_body_serialises_to_a_string_the_model_accepts(self):
        cw, sc = self.mk("cloudwatch")
        body = json.dumps(T.dashboard_body(SPEC, "relayshield-api-gw"))
        sc.add_response("put_dashboard", {"DashboardValidationMessages": []}, {"DashboardName": "n", "DashboardBody": body})
        with sc:
            cw.put_dashboard(DashboardName="n", DashboardBody=body)


if __name__ == "__main__":
    unittest.main()
