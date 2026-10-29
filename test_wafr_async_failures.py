"""tools/wafr_async_failures.py: failure queue, queue access, async retry limits, queue-not-empty alarm (WAFR REL 5).

Two layers, because a fake written by the same hand as the code proves nothing about the library:
  * Fake clients test the DECISIONS (never overwrite an existing async config, never set a destination the role
    cannot write to, discover only ENABLED rules' Lambda targets, grant access BEFORE setting the destination,
    block rather than guess, dry run writes nothing, wrong account refused).
  * botocore's Stubber, over the REAL lambda / iam / sqs / events / cloudwatch models, tests the SHAPES: every
    request the tool makes is validated against the model and every response it parses is a legal one. Skipped
    (and said so) where boto3 is not installed; CI installs it from tests_requirements.txt.
NOT covered by either: that Lambda accepts the destination the moment the policy is attached (the tool retries a
permission-shaped refusal for about a minute), and that the IAM policy simulator answers for a role it may not
read (the tool blocks on any simulator error)."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import wafr_async_failures as T  # noqa: E402

SPEC = json.load(open(ROOT / "tools" / "wafr_async_spec.json"))
ACCT = SPEC["account"]
QARN = T.queue_arn_of(SPEC)
PARN = T.policy_arn_of(SPEC)
TOPIC = "arn:aws:sns:us-east-1:239677749008:relayshield-alerts"
ROLE = "arn:aws:iam::239677749008:role/service-role/relayshield-breach-check-role-1sapnwdl"
ROLE2 = "arn:aws:iam::239677749008:role/relayshield-intel-feed"


def lam_arn(name, qual=None, acct=ACCT):
    return f"arn:aws:lambda:us-east-1:{acct}:function:{name}" + (f":{qual}" if qual else "")


class AwsError(Exception):
    def __init__(self, code, msg=""):
        super().__init__(msg or code)
        self.response = {"Error": {"Code": code, "Message": msg}}


class Log(list):
    pass


class FakeEvents:
    def __init__(self, rules=None, page=None):
        self.rules = rules if rules is not None else {"r1": ("ENABLED", [lam_arn("fn-a")]), "r2": ("ENABLED", [lam_arn("fn-b")])}
        self.page = page

    def list_rules(self, NextToken=None):
        names = list(self.rules)
        if self.page:
            start = int(NextToken or 0)
            chunk, nxt = names[start:start + self.page], (str(start + self.page) if start + self.page < len(names) else None)
        else:
            chunk, nxt = names, None
        out = {"Rules": [{"Name": n, "State": self.rules[n][0]} for n in chunk]}
        if nxt:
            out["NextToken"] = nxt
        return out

    def list_targets_by_rule(self, Rule, NextToken=None):
        return {"Targets": [{"Id": str(i), "Arn": a} for i, a in enumerate(self.rules[Rule][1])]}


class FakeLambda:
    def __init__(self, roles=None, configs=None, put_errors=(), log=None):
        self.roles = roles if roles is not None else {"fn-a": ROLE, "fn-b": ROLE}
        self.configs, self.puts, self.put_errors, self.log = dict(configs or {}), [], list(put_errors), log

    def get_function_configuration(self, FunctionName, Qualifier=None):
        if FunctionName not in self.roles:
            raise AwsError("ResourceNotFoundException")
        return {"Role": self.roles[FunctionName]}

    def get_function_event_invoke_config(self, FunctionName, Qualifier=None):
        if (FunctionName, Qualifier) not in self.configs:
            raise AwsError("ResourceNotFoundException")
        return self.configs[(FunctionName, Qualifier)]

    def put_function_event_invoke_config(self, FunctionName, MaximumRetryAttempts, MaximumEventAgeInSeconds, DestinationConfig, Qualifier=None):
        if self.put_errors:
            raise self.put_errors.pop(0)
        self.puts.append(dict(fn=FunctionName, qual=Qualifier, retries=MaximumRetryAttempts, age=MaximumEventAgeInSeconds,
                              dest=DestinationConfig["OnFailure"]["Destination"]))
        if self.log is not None:
            self.log.append(("lambda-put", FunctionName))


class FakeIAM:
    def __init__(self, allowed=False, attached=3, sim_error=None, policy_exists=False, has_policy=False, log=None):
        self.allowed, self.attached, self.sim_error = allowed, attached, sim_error
        self.policy_exists, self.has_policy, self.log = policy_exists, has_policy, log
        self.creates, self.attaches, self.granted = [], [], set()

    def simulate_principal_policy(self, PolicySourceArn, ActionNames, ResourceArns):
        if self.sim_error:
            raise AwsError(self.sim_error)
        d = "allowed" if (self.allowed or PolicySourceArn in self.granted) else "implicitDeny"
        return {"EvaluationResults": [{"EvalActionName": a, "EvalDecision": d} for a in ActionNames]}

    def list_attached_role_policies(self, RoleName):
        rows = [{"PolicyName": f"p{i}", "PolicyArn": f"arn:aws:iam::1:policy/p{i}"} for i in range(self.attached)]
        if self.has_policy:
            rows.append({"PolicyName": SPEC["policy"]["name"], "PolicyArn": PARN})
        return {"AttachedPolicies": rows}

    def get_policy(self, PolicyArn):
        if not self.policy_exists:
            raise AwsError("NoSuchEntity")
        return {"Policy": {"Arn": PolicyArn}}

    def create_policy(self, PolicyName, PolicyDocument, Description=""):
        self.creates.append((PolicyName, json.loads(PolicyDocument)))
        self.policy_exists = True
        if self.log is not None:
            self.log.append(("iam-create", PolicyName))

    def attach_role_policy(self, RoleName, PolicyArn):
        self.attaches.append((RoleName, PolicyArn))
        self.granted.add(next((r for r in (ROLE, ROLE2) if r.endswith("/" + RoleName)), RoleName))
        if self.log is not None:
            self.log.append(("iam-attach", RoleName))


class FakeSQS:
    def __init__(self, exists=False, attrs=None, error=None, log=None):
        self.exists, self.error, self.log, self.creates = exists, error, log, []
        self.attrs = attrs if attrs is not None else {"MessageRetentionPeriod": "1209600", "SqsManagedSseEnabled": "true"}

    def get_queue_url(self, QueueName):
        if self.error:
            raise AwsError(self.error)
        if not self.exists:
            raise AwsError("AWS.SimpleQueueService.NonExistentQueue")
        return {"QueueUrl": f"https://sqs.us-east-1.amazonaws.com/{ACCT}/{QueueName}"}

    def get_queue_attributes(self, QueueUrl, AttributeNames):
        return {"Attributes": {k: v for k, v in self.attrs.items() if k in AttributeNames}}

    def create_queue(self, QueueName, Attributes):
        self.creates.append((QueueName, Attributes))
        if self.log is not None:
            self.log.append(("sqs-create", QueueName))


class FakeCW:
    def __init__(self, actions=(TOPIC,), alarm=None, log=None):
        self.actions, self.alarm, self.puts, self.log = list(actions), alarm, [], log

    def describe_alarms(self, **kw):
        if "AlarmNames" in kw:
            return {"MetricAlarms": [self.alarm] if self.alarm else []}
        e = {"AlarmName": "x", "Namespace": "AWS/Lambda", "MetricName": "Errors"}
        return {"MetricAlarms": [{**e, "AlarmActions": self.actions}] if self.actions else [e]}

    def put_metric_alarm(self, **kw):
        self.puts.append(kw)
        if self.log is not None:
            self.log.append(("alarm", kw["AlarmName"]))


def clients(**over):
    c = {"events": FakeEvents(), "lambda": FakeLambda(), "iam": FakeIAM(), "sqs": FakeSQS(), "cloudwatch": FakeCW()}
    c.update(over)
    return c


def go(c, apply=False, steps=T.STEPS, acct=ACCT, spec=SPEC, sns=None, sleep=lambda s: None):
    lines = []
    rc = T.run(c, lambda: acct, spec, apply, steps, sns, out=lines.append, sleep=sleep)
    return rc, "\n".join(lines)


class Guards(unittest.TestCase):
    def test_wrong_account_refused_and_nothing_written(self):
        c = clients()
        rc, out = go(c, apply=True, acct="620534471984")
        self.assertEqual(rc, 2)
        self.assertIn("Refusing to run", out)
        self.assertEqual((c["sqs"].creates, c["iam"].creates, c["lambda"].puts, c["cloudwatch"].puts), ([], [], [], []))

    def test_dry_run_writes_nothing_and_says_so(self):
        c = clients()
        rc, out = go(c)
        self.assertEqual((c["sqs"].creates, c["iam"].creates, c["iam"].attaches, c["lambda"].puts, c["cloudwatch"].puts),
                        ([], [], [], [], []))
        self.assertIn("Dry run only", out)

    def test_values_outside_lambdas_limits_are_refused_before_any_call(self):
        for field, bad in (("max_retry_attempts", 3), ("max_event_age_seconds", 30), ("max_event_age_seconds", 30000)):
            spec = copy.deepcopy(SPEC)
            spec["async"][field] = bad
            c = clients()
            rc, out = go(c, apply=True, spec=spec)
            self.assertEqual(rc, 2, field)
            self.assertEqual(c["lambda"].puts, [])


class Targets(unittest.TestCase):
    def test_only_enabled_rules_and_only_lambda_targets_in_this_account(self):
        ev = FakeEvents({"on": ("ENABLED", [lam_arn("fn-a"), "arn:aws:sns:us-east-1:239677749008:topic",
                                            lam_arn("other-acct", acct="111111111111")]),
                         "off": ("DISABLED", [lam_arn("fn-off")])})
        t, disabled = T.discover_targets(ev, SPEC)
        self.assertEqual((t, disabled), ([("fn-a", None)], 1))

    def test_alias_qualifier_is_kept_and_a_function_in_two_rules_is_counted_once(self):
        ev = FakeEvents({"a": ("ENABLED", [lam_arn("fn-a", "live")]), "b": ("ENABLED", [lam_arn("fn-a", "live")]),
                         "c": ("ENABLED", [lam_arn("fn-a")])})
        self.assertEqual(T.discover_targets(ev, SPEC)[0], [("fn-a", None), ("fn-a", "live")])

    def test_rule_pages_are_followed(self):
        ev = FakeEvents({f"r{i}": ("ENABLED", [lam_arn(f"fn-{i}")]) for i in range(5)}, page=2)
        self.assertEqual(len(T.discover_targets(ev, SPEC)[0]), 5)

    def test_extra_functions_added_and_excluded_functions_removed(self):
        spec = copy.deepcopy(SPEC)
        spec["async"]["extra_functions"] = ["s3-fn"]
        spec["async"]["exclude_functions"] = ["fn-b"]
        self.assertEqual(T.discover_targets(FakeEvents(), spec)[0], [("fn-a", None), ("s3-fn", None)])


class Queue(unittest.TestCase):
    def test_missing_queue_is_created_encrypted_with_the_specified_retention(self):
        c = clients()
        go(c, apply=True, steps=("queue",))
        self.assertEqual(c["sqs"].creates, [("relayshield-async-failures", {"MessageRetentionPeriod": "1209600", "SqsManagedSseEnabled": "true"})])

    def test_existing_queue_as_specified_is_left_alone(self):
        c = clients(sqs=FakeSQS(exists=True))
        rc, out = go(c, apply=True, steps=("queue",))
        self.assertEqual((rc, c["sqs"].creates), (0, []))

    def test_existing_queue_with_other_settings_is_reported_not_changed(self):
        for attrs in ({"MessageRetentionPeriod": "345600", "SqsManagedSseEnabled": "true"},
                      {"MessageRetentionPeriod": "1209600", "SqsManagedSseEnabled": "false"}):
            c = clients(sqs=FakeSQS(exists=True, attrs=attrs))
            rc, out = go(c, apply=True, steps=("queue",))
            self.assertEqual(rc, 1)
            self.assertIn("CONFLICT", out)
            self.assertEqual(c["sqs"].creates, [])

    def test_the_botocore_json_error_code_is_also_read_as_missing(self):
        c = clients(sqs=FakeSQS(error="QueueDoesNotExist"))
        go(c, apply=True, steps=("queue",))
        self.assertEqual(len(c["sqs"].creates), 1)

    def test_unexpected_read_error_blocks_instead_of_creating(self):
        c = clients(sqs=FakeSQS(error="AccessDenied"))
        rc, out = go(c, apply=True, steps=("queue",))
        self.assertEqual((rc, c["sqs"].creates), (1, []))


class Access(unittest.TestCase):
    def test_a_role_that_can_already_send_needs_nothing(self):
        c = clients(iam=FakeIAM(allowed=True))
        rc, out = go(c, apply=True, steps=("access",))
        self.assertEqual((rc, c["iam"].creates, c["iam"].attaches), (0, [], []))

    def test_denied_role_with_room_gets_one_policy_scoped_to_the_queue_then_one_attach_per_role(self):
        log = Log()
        c = clients(iam=FakeIAM(log=log), **{"lambda": FakeLambda(roles={"fn-a": ROLE, "fn-b": ROLE2})})
        go(c, apply=True, steps=("access",))
        self.assertEqual([k for k, _ in log], ["iam-create", "iam-attach", "iam-attach"])
        self.assertEqual(c["iam"].creates, [(SPEC["policy"]["name"], T.policy_doc(QARN))])
        doc = c["iam"].creates[0][1]["Statement"][0]
        self.assertEqual((doc["Action"], doc["Resource"]), ("sqs:SendMessage", QARN))

    def test_two_functions_sharing_a_role_attach_once(self):
        c = clients()
        go(c, apply=True, steps=("access",))
        self.assertEqual(len(c["iam"].attaches), 1)

    def test_existing_policy_is_attached_not_recreated(self):
        c = clients(iam=FakeIAM(policy_exists=True))
        go(c, apply=True, steps=("access",))
        self.assertEqual((c["iam"].creates, len(c["iam"].attaches)), ([], 1))

    def test_no_room_for_a_managed_policy_blocks_and_changes_nothing(self):
        c = clients(iam=FakeIAM(attached=10))
        rc, out = go(c, apply=True, steps=("access",))
        self.assertEqual(rc, 1)
        self.assertIn("BLOCKED", out)
        self.assertIn("role split", out)
        self.assertEqual((c["iam"].creates, c["iam"].attaches), ([], []))

    def test_cannot_simulate_blocks_rather_than_attaching_blind(self):
        c = clients(iam=FakeIAM(sim_error="AccessDenied"))
        rc, out = go(c, apply=True, steps=("access",))
        self.assertEqual((rc, c["iam"].creates, c["iam"].attaches), (1, [], []))

    def test_policy_already_attached_but_still_denied_is_blocked_not_reattached(self):
        c = clients(iam=FakeIAM(has_policy=True))
        rc, out = go(c, apply=True, steps=("access",))
        self.assertEqual((rc, c["iam"].attaches), (1, []))
        self.assertIn("something else denies", out)


class Retry(unittest.TestCase):
    def test_unconfigured_function_gets_the_spec_values_and_the_queue(self):
        c = clients(iam=FakeIAM(allowed=True))
        rc, out = go(c, apply=True, steps=("retry",))
        self.assertEqual(rc, 0, out)
        self.assertEqual(sorted(p["fn"] for p in c["lambda"].puts), ["fn-a", "fn-b"])
        for p in c["lambda"].puts:
            self.assertEqual((p["retries"], p["age"], p["dest"]), (1, 3600, QARN))

    def test_matching_config_is_left_alone(self):
        cfg = {"MaximumRetryAttempts": 1, "MaximumEventAgeInSeconds": 3600, "DestinationConfig": {"OnFailure": {"Destination": QARN}}}
        c = clients(iam=FakeIAM(allowed=True), **{"lambda": FakeLambda(configs={("fn-a", None): cfg, ("fn-b", None): cfg})})
        rc, out = go(c, apply=True, steps=("retry",))
        self.assertEqual((rc, c["lambda"].puts), (0, []))

    def test_a_different_existing_config_is_reported_and_NEVER_replaced(self):
        # put_function_event_invoke_config replaces the whole config, including an OnSuccess destination.
        other = {"MaximumRetryAttempts": 2, "MaximumEventAgeInSeconds": 21600,
                 "DestinationConfig": {"OnSuccess": {"Destination": "arn:aws:sqs:us-east-1:239677749008:other"}}}
        c = clients(iam=FakeIAM(allowed=True), **{"lambda": FakeLambda(configs={("fn-a", None): other})})
        rc, out = go(c, apply=True, steps=("retry",))
        self.assertEqual(rc, 1)
        self.assertIn("CONFLICT", out)
        self.assertEqual([p["fn"] for p in c["lambda"].puts], ["fn-b"])

    def test_unreadable_target_is_reported_missing(self):
        c = clients(iam=FakeIAM(allowed=True), **{"lambda": FakeLambda(roles={"fn-a": ROLE})})
        rc, out = go(c, apply=True, steps=("retry",))
        self.assertEqual(rc, 1)
        self.assertIn("MISSING", out)
        self.assertEqual([p["fn"] for p in c["lambda"].puts], ["fn-a"])

    def test_a_role_that_cannot_send_gets_NO_destination_when_access_could_not_be_granted(self):
        c = clients(iam=FakeIAM(attached=10))
        rc, out = go(c, apply=True, steps=("retry",))
        self.assertEqual((rc, c["lambda"].puts), (1, []))
        self.assertIn("no destination is set", out)

    def test_apply_after_a_failed_grant_does_not_set_a_destination_either(self):
        c = clients(iam=FakeIAM(attached=10))
        rc, out = go(c, apply=True, steps=("access", "retry"))
        self.assertEqual((rc, c["lambda"].puts), (1, []))

    def test_dry_run_of_retry_alone_expects_the_access_step_and_does_not_call_it_blocked(self):
        c = clients()
        rc, out = go(c, steps=("retry",))
        self.assertEqual(rc, 0, out)
        self.assertIn("after the access step", out)
        self.assertNotIn("BLOCKED", out)

    def test_alias_qualifier_reaches_the_api_call(self):
        c = clients(iam=FakeIAM(allowed=True), events=FakeEvents({"r": ("ENABLED", [lam_arn("fn-a", "live")])}))
        go(c, apply=True, steps=("retry",))
        self.assertEqual([(p["fn"], p["qual"]) for p in c["lambda"].puts], [("fn-a", "live")])

    def test_access_is_granted_BEFORE_the_destination_is_set(self):
        log = Log()
        c = clients(iam=FakeIAM(log=log), **{"lambda": FakeLambda(log=log)})
        rc, out = go(c, apply=True, steps=("access", "retry"))
        self.assertEqual(rc, 0, out)
        self.assertLess(log.index(("iam-attach", "relayshield-breach-check-role-1sapnwdl")), log.index(("lambda-put", "fn-a")))

    def test_iam_propagation_refusal_is_retried_then_succeeds(self):
        slept = []
        err = AwsError("InvalidParameterValueException", "The provided execution role does not have permissions to call SendMessage on SQS")
        c = clients(iam=FakeIAM(allowed=True), **{"lambda": FakeLambda(put_errors=[err, err])})
        rc, out = go(c, apply=True, steps=("retry",), sleep=slept.append)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(slept), 2)
        self.assertEqual(len(c["lambda"].puts), 2)

    def test_any_other_refusal_is_raised_at_once_not_retried(self):
        slept = []
        c = clients(iam=FakeIAM(allowed=True), **{"lambda": FakeLambda(put_errors=[AwsError("InvalidParameterValueException", "MaximumRetryAttempts out of range")])})
        with self.assertRaises(AwsError):
            go(c, apply=True, steps=("retry",), sleep=slept.append)
        self.assertEqual(slept, [])


class Alarm(unittest.TestCase):
    def test_alarm_watches_the_queue_and_notifies_the_discovered_targets(self):
        c = clients()
        go(c, apply=True, steps=("alarm",))
        a = c["cloudwatch"].puts[0]
        self.assertEqual((a["Namespace"], a["MetricName"], a["Dimensions"], a["AlarmActions"], a["Threshold"]),
                         ("AWS/SQS", "ApproximateNumberOfMessagesVisible", [{"Name": "QueueName", "Value": "relayshield-async-failures"}], [TOPIC], 1.0))

    def test_blocked_when_nobody_would_be_told(self):
        c = clients(cloudwatch=FakeCW(actions=()))
        rc, out = go(c, apply=True, steps=("alarm",))
        self.assertEqual((rc, c["cloudwatch"].puts), (1, []))
        self.assertIn("BLOCKED", out)

    def test_unchanged_when_already_as_specified(self):
        c = clients(cloudwatch=FakeCW(alarm={"Threshold": 1.0, "AlarmActions": [TOPIC]}))
        rc, out = go(c, apply=True, steps=("alarm",))
        self.assertEqual((rc, c["cloudwatch"].puts), (0, []))

    def test_explicit_sns_topic_beats_discovery(self):
        c = clients()
        go(c, apply=True, steps=("alarm",), sns="arn:aws:sns:us-east-1:239677749008:mine")
        self.assertEqual(c["cloudwatch"].puts[0]["AlarmActions"], ["arn:aws:sns:us-east-1:239677749008:mine"])


class FullRun(unittest.TestCase):
    def test_apply_order_is_queue_policy_attach_put_alarm_and_a_second_run_changes_nothing(self):
        log = Log()
        c = clients(iam=FakeIAM(log=log), sqs=FakeSQS(log=log), cloudwatch=FakeCW(log=log), **{"lambda": FakeLambda(log=log)})
        rc, out = go(c, apply=True)
        self.assertEqual(rc, 0, out)
        self.assertEqual([k for k, _ in log], ["sqs-create", "iam-create", "iam-attach", "lambda-put", "lambda-put", "alarm"])
        # second run against the state the first one left behind
        cfg = {"MaximumRetryAttempts": 1, "MaximumEventAgeInSeconds": 3600, "DestinationConfig": {"OnFailure": {"Destination": QARN}}}
        c2 = clients(iam=FakeIAM(allowed=True), sqs=FakeSQS(exists=True),
                     cloudwatch=FakeCW(alarm={"Threshold": 1.0, "AlarmActions": [TOPIC]}),
                     **{"lambda": FakeLambda(configs={("fn-a", None): cfg, ("fn-b", None): cfg})})
        rc2, out2 = go(c2, apply=True)
        self.assertEqual(rc2, 0, out2)
        self.assertEqual((c2["sqs"].creates, c2["iam"].creates, c2["lambda"].puts, c2["cloudwatch"].puts), ([], [], [], []))


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
        ev, se = self.mk("events")
        lam, sl = self.mk("lambda")
        iam, si = self.mk("iam")
        sqs, sq = self.mk("sqs")
        cw, sc = self.mk("cloudwatch")
        fn, role = "fn-a", "relayshield-breach-check-role-1sapnwdl"
        sim = {"PolicySourceArn": ROLE, "ActionNames": ["sqs:SendMessage"], "ResourceArns": [QARN]}
        denied = {"EvaluationResults": [{"EvalActionName": "sqs:SendMessage", "EvalDecision": "implicitDeny"}]}
        allowed = {"EvaluationResults": [{"EvalActionName": "sqs:SendMessage", "EvalDecision": "allowed"}]}

        se.add_response("list_rules", {"Rules": [{"Name": "r1", "State": "ENABLED"}, {"Name": "r2", "State": "DISABLED"}]}, {})
        se.add_response("list_targets_by_rule", {"Targets": [{"Id": "1", "Arn": lam_arn(fn)}]}, {"Rule": "r1"})

        # queue
        sq.add_client_error("get_queue_url", "AWS.SimpleQueueService.NonExistentQueue", expected_params={"QueueName": "relayshield-async-failures"})
        sq.add_response("create_queue", {"QueueUrl": "https://sqs.us-east-1.amazonaws.com/239677749008/relayshield-async-failures"},
                        {"QueueName": "relayshield-async-failures",
                         "Attributes": {"MessageRetentionPeriod": "1209600", "SqsManagedSseEnabled": "true"}})
        # access
        sl.add_response("get_function_configuration", {"Role": ROLE}, {"FunctionName": fn})
        si.add_response("simulate_principal_policy", denied, sim)
        si.add_response("list_attached_role_policies", {"AttachedPolicies": [{"PolicyName": "p", "PolicyArn": "arn:aws:iam::1:policy/p"}]}, {"RoleName": role})
        si.add_client_error("get_policy", "NoSuchEntity", expected_params={"PolicyArn": PARN})
        si.add_response("create_policy", {"Policy": {"PolicyName": SPEC["policy"]["name"]}},
                        {"PolicyName": SPEC["policy"]["name"], "PolicyDocument": json.dumps(T.policy_doc(QARN)), "Description": ANY})
        si.add_response("attach_role_policy", {}, {"RoleName": role, "PolicyArn": PARN})
        # retry
        sl.add_response("get_function_configuration", {"Role": ROLE}, {"FunctionName": fn})
        sl.add_client_error("get_function_event_invoke_config", "ResourceNotFoundException", expected_params={"FunctionName": fn})
        si.add_response("simulate_principal_policy", allowed, sim)
        sl.add_response("put_function_event_invoke_config", {"MaximumRetryAttempts": 1},
                        {"FunctionName": fn, "MaximumRetryAttempts": 1, "MaximumEventAgeInSeconds": 3600,
                         "DestinationConfig": {"OnFailure": {"Destination": QARN}}})
        # alarm
        sc.add_response("describe_alarms", {"MetricAlarms": [{"AlarmName": "e", "Namespace": "AWS/Lambda", "MetricName": "Errors",
                                                              "AlarmActions": [TOPIC]}]}, {"AlarmTypes": ["MetricAlarm"]})
        sc.add_response("describe_alarms", {"MetricAlarms": []}, {"AlarmNames": [SPEC["alarm"]["name"]]})
        sc.add_response("put_metric_alarm", {}, T.alarm_def(SPEC, [TOPIC]))

        stubs = (se, sl, si, sq, sc)
        for s in stubs:
            s.activate()
        try:
            rc, out = go({"events": ev, "lambda": lam, "iam": iam, "sqs": sqs, "cloudwatch": cw}, apply=True)
            for s in stubs:
                s.assert_no_pending_responses()
        finally:
            for s in stubs:
                s.deactivate()
        self.assertEqual(rc, 0, out)

    def test_the_json_protocol_queue_error_code_is_also_read_as_missing(self):
        sqs, sq = self.mk("sqs")
        sq.add_client_error("get_queue_url", "QueueDoesNotExist", expected_params={"QueueName": "relayshield-async-failures"})
        with sq:
            rows, actions = T.plan_queue({"sqs": sqs}, SPEC)
        self.assertEqual((rows[0][1], len(actions)), ("todo", 1))

    def test_an_existing_queue_response_is_parsed(self):
        sqs, sq = self.mk("sqs")
        url = "https://sqs.us-east-1.amazonaws.com/239677749008/relayshield-async-failures"
        sq.add_response("get_queue_url", {"QueueUrl": url}, {"QueueName": "relayshield-async-failures"})
        sq.add_response("get_queue_attributes", {"Attributes": {"MessageRetentionPeriod": "1209600", "SqsManagedSseEnabled": "true"}},
                        {"QueueUrl": url, "AttributeNames": ["MessageRetentionPeriod", "SqsManagedSseEnabled"]})
        with sq:
            rows, actions = T.plan_queue({"sqs": sqs}, SPEC)
        self.assertEqual((rows[0][1], actions), ("ok", []))

    def test_an_existing_async_config_response_is_parsed_as_a_match(self):
        lam, sl = self.mk("lambda")
        sl.add_response("get_function_event_invoke_config",
                        {"MaximumRetryAttempts": 1, "MaximumEventAgeInSeconds": 3600,
                         "DestinationConfig": {"OnFailure": {"Destination": QARN}}}, {"FunctionName": "fn-a"})
        with sl:
            rows, _ = T.plan_retry({"lambda": lam, "iam": FakeIAM(allowed=True)}, SPEC, {("fn-a", None): ("role", ROLE)}, True, lambda s: None)
        self.assertEqual(rows[0][1], "ok")


if __name__ == "__main__":
    unittest.main()
