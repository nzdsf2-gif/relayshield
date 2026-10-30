"""tools/wafr_stripe_queue.py: queues, access, consumer, and the separate enable / disable switch (WAFR REL 4).

Two layers, because a fake written by the same hand as the code proves nothing about the library:
  * Fake clients test the DECISIONS: the dead-letter queue exists before the queue that points at it; access is
    granted before the consumer is created; the default run never flips the flag; enabling MERGES into the existing
    Lambda environment (update_function_configuration replaces all of it) and refuses unless the consumer works and
    the DEPLOYED code contains queue mode; disabling removes only its own variable; nothing existing is overwritten.
  * botocore's Stubber, over the REAL lambda / iam / sqs models, tests the SHAPES of every request and response.
    Skipped (and said so) where boto3 is not installed; CI installs it from tests_requirements.txt.
NOT covered: that Lambda accepts the mapping the instant the policy is attached (the tool retries a permission-shaped
refusal for about a minute), that the IAM simulator answers for this role, and that a real presigned code URL
downloads (the fetch is injected)."""
import copy
import io
import json
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import wafr_stripe_queue as T  # noqa: E402

SPEC = json.load(open(ROOT / "tools" / "wafr_stripe_queue_spec.json"))
ACCT = SPEC["account"]
FN = SPEC["function"]
QARN = T.arn_of(SPEC, SPEC["queue"]["name"])
DLQARN = T.arn_of(SPEC, SPEC["queue"]["dlq_name"])
PARN = T.policy_arn_of(SPEC)
ROLE = "arn:aws:iam::239677749008:role/service-role/relayshield-breach-check-role-1sapnwdl"
URL = f"https://sqs.us-east-1.amazonaws.com/{ACCT}/{SPEC['queue']['name']}"
ENV = {"DAY3_LAMBDA_ARN": "arn:aws:lambda:us-east-1:239677749008:function:relayshield-day3-sender",
       "DAY3_SCHEDULER_ROLE_ARN": "arn:aws:iam::239677749008:role/relayshield-scheduler-invoke-day3"}


def code_zip(with_queue_mode=True):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        src = "STRIPE_EVENT_QUEUE_URL = 1\ndef process_queue_batch(e): pass\n" if with_queue_mode else "def lambda_handler(e, c): pass\n"
        z.writestr("relayshield_stripe_webhook.py", src)
        z.writestr("other.txt", "STRIPE_EVENT_QUEUE_URL process_queue_batch")  # a non-.py file must not count
    return buf.getvalue()


class AwsError(Exception):
    def __init__(self, code, msg=""):
        super().__init__(msg or code)
        self.response = {"Error": {"Code": code, "Message": msg}}


class Log(list):
    pass


class FakeLambda:
    def __init__(self, timeout=30, env=None, env_error=None, mapping=None, missing=False, put_errors=(), log=None, location="https://code/zip"):
        self.cfg = {"Role": ROLE, "Timeout": timeout, "Environment": {"Variables": dict(ENV if env is None else env)}}
        if env_error:
            self.cfg["Environment"] = {"Error": {"ErrorCode": env_error}}
        self.mapping, self.missing, self.put_errors, self.log, self.location = mapping, missing, list(put_errors), log, location
        self.created, self.updates = [], []

    def get_function_configuration(self, FunctionName):
        if self.missing:
            raise AwsError("ResourceNotFoundException")
        return self.cfg

    def get_function(self, FunctionName):
        return {"Code": {"Location": self.location}, "Configuration": self.cfg}

    def list_event_source_mappings(self, FunctionName, EventSourceArn):
        return {"EventSourceMappings": [self.mapping] if self.mapping else []}

    def create_event_source_mapping(self, EventSourceArn, FunctionName, BatchSize, Enabled, ScalingConfig):
        if self.put_errors:
            raise self.put_errors.pop(0)
        self.created.append(dict(arn=EventSourceArn, fn=FunctionName, batch=BatchSize, enabled=Enabled, conc=ScalingConfig["MaximumConcurrency"]))
        if self.log is not None:
            self.log.append(("mapping-create", FunctionName))

    def update_function_configuration(self, FunctionName, Environment):
        self.updates.append(Environment["Variables"])
        if self.log is not None:
            self.log.append(("env-update", FunctionName))


class FakeIAM:
    def __init__(self, allowed=False, attached=3, sim_error=None, policy_exists=False, has_policy=False, log=None):
        self.allowed, self.attached, self.sim_error = allowed, attached, sim_error
        self.policy_exists, self.has_policy, self.log = policy_exists, has_policy, log
        self.creates, self.attaches, self.granted = [], [], False

    def simulate_principal_policy(self, PolicySourceArn, ActionNames, ResourceArns):
        if self.sim_error:
            raise AwsError(self.sim_error)
        d = "allowed" if (self.allowed or self.granted) else "implicitDeny"
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
        self.granted = True
        if self.log is not None:
            self.log.append(("iam-attach", RoleName))


class FakeSQS:
    """Per-queue state: {name: attrs}. A queue named in `error` raises that code on lookup."""
    def __init__(self, queues=None, error=None, log=None):
        self.queues, self.error, self.log, self.creates = dict(queues or {}), error, log, []

    def get_queue_url(self, QueueName):
        if self.error:
            raise AwsError(self.error)
        if QueueName not in self.queues:
            raise AwsError("AWS.SimpleQueueService.NonExistentQueue")
        return {"QueueUrl": f"https://sqs.us-east-1.amazonaws.com/{ACCT}/{QueueName}"}

    def get_queue_attributes(self, QueueUrl, AttributeNames):
        a = self.queues[QueueUrl.rsplit("/", 1)[-1]]
        return {"Attributes": {k: v for k, v in a.items() if k in AttributeNames}}

    def create_queue(self, QueueName, Attributes):
        self.creates.append((QueueName, Attributes))
        self.queues[QueueName] = Attributes
        if self.log is not None:
            self.log.append(("sqs-create", QueueName))


MAIN_ATTRS, DLQ_ATTRS = T.desired_queue_attrs(SPEC, 30)
GOOD_QUEUES = {SPEC["queue"]["name"]: MAIN_ATTRS, SPEC["queue"]["dlq_name"]: DLQ_ATTRS}
GOOD_MAPPING = {"UUID": "11111111-1111-1111-1111-111111111111", "State": "Enabled", "BatchSize": 1, "ScalingConfig": {"MaximumConcurrency": 2}}


def clients(**over):
    c = {"lambda": FakeLambda(), "iam": FakeIAM(), "sqs": FakeSQS()}
    c.update(over)
    return c


def go(c, apply=False, steps=T.DEFAULT_STEPS, acct=ACCT, spec=SPEC, sleep=lambda s: None, fetch=lambda u: code_zip()):
    lines = []
    rc = T.run(c, lambda: acct, spec, apply, steps, out=lines.append, sleep=sleep, fetch=fetch)
    return rc, "\n".join(lines)


def ready(**over):
    """Everything an enable needs: queue, mapping, access, deployed code."""
    c = {"lambda": FakeLambda(mapping=GOOD_MAPPING), "iam": FakeIAM(allowed=True), "sqs": FakeSQS(GOOD_QUEUES)}
    c.update(over)
    return c


class Guards(unittest.TestCase):
    def test_wrong_account_refused_and_nothing_written(self):
        c = clients()
        rc, out = go(c, apply=True, acct="620534471984")
        self.assertEqual(rc, 2)
        self.assertEqual((c["sqs"].creates, c["iam"].creates, c["lambda"].created, c["lambda"].updates), ([], [], [], []))

    def test_dry_run_writes_nothing_and_says_so(self):
        c = clients()
        rc, out = go(c)
        self.assertEqual((c["sqs"].creates, c["iam"].creates, c["iam"].attaches, c["lambda"].created, c["lambda"].updates), ([], [], [], [], []))
        self.assertIn("Dry run only", out)

    def test_values_outside_the_service_limits_are_refused(self):
        for section, field, bad in (("consumer", "max_concurrency", 1), ("consumer", "batch_size", 11),
                                    ("queue", "max_receive_count", 0), ("queue", "retention_seconds", 30)):
            spec = copy.deepcopy(SPEC)
            spec[section][field] = bad
            c = clients()
            rc, out = go(c, apply=True, spec=spec)
            self.assertEqual(rc, 2, field)
            self.assertEqual(c["sqs"].creates, [])

    def test_the_default_run_never_includes_the_switch(self):
        self.assertNotIn("enable", T.DEFAULT_STEPS)
        self.assertNotIn("disable", T.DEFAULT_STEPS)
        self.assertEqual(set(T.STEPS), set(T.DEFAULT_STEPS) | {"enable", "disable"})


class Queues(unittest.TestCase):
    def test_dead_letter_queue_is_created_BEFORE_the_queue_that_redrives_to_it(self):
        log = Log()
        c = clients(sqs=FakeSQS(log=log))
        go(c, apply=True, steps=("queues",))
        self.assertEqual([n for _, n in log], [SPEC["queue"]["dlq_name"], SPEC["queue"]["name"]])

    def test_main_queue_has_the_redrive_policy_encryption_and_a_visibility_timeout_of_6x_the_function_timeout(self):
        c = clients(**{"lambda": FakeLambda(timeout=45)})
        go(c, apply=True, steps=("queues",))
        attrs = dict(c["sqs"].creates)[SPEC["queue"]["name"]]
        self.assertEqual(attrs["VisibilityTimeout"], "270")
        self.assertEqual(attrs["SqsManagedSseEnabled"], "true")
        self.assertEqual(json.loads(attrs["RedrivePolicy"]), {"deadLetterTargetArn": DLQARN, "maxReceiveCount": 5})
        self.assertNotIn("RedrivePolicy", dict(c["sqs"].creates)[SPEC["queue"]["dlq_name"]])

    def test_queues_as_specified_are_left_alone(self):
        c = ready()
        rc, out = go(c, apply=True, steps=("queues",))
        self.assertEqual((rc, c["sqs"].creates), (0, []))

    def test_an_existing_queue_that_differs_is_reported_and_not_changed(self):
        for key, val in (("VisibilityTimeout", "30"), ("SqsManagedSseEnabled", "false"),
                         ("RedrivePolicy", json.dumps({"deadLetterTargetArn": DLQARN, "maxReceiveCount": 3}))):
            q = copy.deepcopy(GOOD_QUEUES)
            q[SPEC["queue"]["name"]][key] = val
            c = ready(sqs=FakeSQS(q))
            rc, out = go(c, apply=True, steps=("queues",))
            self.assertEqual(rc, 1, key)
            self.assertIn("CONFLICT", out)
            self.assertEqual(c["sqs"].creates, [])

    def test_redrive_policy_key_order_does_not_cause_a_false_conflict(self):
        q = copy.deepcopy(GOOD_QUEUES)
        q[SPEC["queue"]["name"]]["RedrivePolicy"] = json.dumps({"maxReceiveCount": 5, "deadLetterTargetArn": DLQARN})
        rc, out = go(ready(sqs=FakeSQS(q)), steps=("queues",))
        self.assertEqual(rc, 0, out)

    def test_unreadable_function_blocks_rather_than_guessing_a_timeout(self):
        c = clients(**{"lambda": FakeLambda(missing=True)})
        rc, out = go(c, apply=True, steps=("queues",))
        self.assertEqual((rc, c["sqs"].creates), (1, []))

    def test_unexpected_queue_read_error_blocks_instead_of_creating(self):
        c = clients(sqs=FakeSQS(error="AccessDenied"))
        rc, out = go(c, apply=True, steps=("queues",))
        self.assertEqual((rc, c["sqs"].creates), (1, []))


class Access(unittest.TestCase):
    def test_a_role_that_already_has_all_four_actions_needs_nothing(self):
        c = clients(iam=FakeIAM(allowed=True))
        rc, out = go(c, apply=True, steps=("access",))
        self.assertEqual((rc, c["iam"].creates, c["iam"].attaches), (0, [], []))

    def test_denied_role_with_room_gets_one_queue_scoped_policy_then_the_attach(self):
        log = Log()
        c = clients(iam=FakeIAM(log=log))
        go(c, apply=True, steps=("access",))
        self.assertEqual([k for k, _ in log], ["iam-create", "iam-attach"])
        st = c["iam"].creates[0][1]["Statement"][0]
        self.assertEqual((st["Action"], st["Resource"]), (T.QUEUE_ACTIONS, QARN))
        self.assertEqual({"sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"}, set(st["Action"]))

    def test_existing_policy_is_attached_not_recreated(self):
        c = clients(iam=FakeIAM(policy_exists=True))
        go(c, apply=True, steps=("access",))
        self.assertEqual((c["iam"].creates, len(c["iam"].attaches)), ([], 1))

    def test_no_room_blocks_and_changes_nothing(self):
        c = clients(iam=FakeIAM(attached=10))
        rc, out = go(c, apply=True, steps=("access",))
        self.assertEqual((rc, c["iam"].creates, c["iam"].attaches), (1, [], []))
        self.assertIn("role split", out)

    def test_cannot_simulate_blocks_rather_than_attaching_blind(self):
        c = clients(iam=FakeIAM(sim_error="AccessDenied"))
        rc, out = go(c, apply=True, steps=("access",))
        self.assertEqual((rc, c["iam"].creates, c["iam"].attaches), (1, [], []))

    def test_policy_already_attached_but_still_denied_is_blocked_not_reattached(self):
        c = clients(iam=FakeIAM(has_policy=True))
        rc, out = go(c, apply=True, steps=("access",))
        self.assertEqual((rc, c["iam"].attaches), (1, []))
        self.assertIn("something else denies", out)

    def test_one_missing_action_is_not_enough(self):
        class Partial(FakeIAM):
            def simulate_principal_policy(self, PolicySourceArn, ActionNames, ResourceArns):
                return {"EvaluationResults": [{"EvalActionName": a, "EvalDecision": "allowed" if a != "sqs:DeleteMessage" else "implicitDeny"}
                                              for a in ActionNames]}
        c = clients(iam=Partial())
        go(c, apply=True, steps=("access",))
        self.assertEqual(len(c["iam"].attaches), 1)


class Consumer(unittest.TestCase):
    def test_mapping_is_created_with_batch_size_1_and_max_concurrency_2(self):
        c = clients(iam=FakeIAM(allowed=True))
        rc, out = go(c, apply=True, steps=("consumer",))
        self.assertEqual(rc, 0, out)
        self.assertEqual(c["lambda"].created, [dict(arn=QARN, fn=FN, batch=1, enabled=True, conc=2)])

    def test_existing_mapping_as_specified_is_left_alone(self):
        c = ready()
        rc, out = go(c, apply=True, steps=("consumer",))
        self.assertEqual((rc, c["lambda"].created), (0, []))

    def test_an_existing_mapping_that_differs_is_reported_and_not_changed(self):
        c = ready(**{"lambda": FakeLambda(mapping={**GOOD_MAPPING, "BatchSize": 10})})
        rc, out = go(c, apply=True, steps=("consumer",))
        self.assertEqual((rc, c["lambda"].created), (1, []))
        self.assertIn("CONFLICT", out)

    def test_no_mapping_is_created_for_a_role_that_cannot_use_the_queue(self):
        c = clients(iam=FakeIAM(attached=10))
        rc, out = go(c, apply=True, steps=("access", "consumer"))
        self.assertEqual((rc, c["lambda"].created), (1, []))

    def test_dry_run_of_consumer_alone_expects_the_access_step_and_is_not_blocked(self):
        rc, out = go(clients(), steps=("consumer",))
        self.assertEqual(rc, 0, out)
        self.assertIn("after the access step", out)

    def test_iam_propagation_refusal_is_retried_then_succeeds(self):
        slept = []
        err = AwsError("InvalidParameterValueException", "The provided execution role does not have permissions to call ReceiveMessage on SQS")
        c = clients(iam=FakeIAM(allowed=True), **{"lambda": FakeLambda(put_errors=[err, err])})
        rc, out = go(c, apply=True, steps=("consumer",), sleep=slept.append)
        self.assertEqual((rc, len(slept), len(c["lambda"].created)), (0, 2, 1))

    def test_any_other_refusal_is_raised_at_once(self):
        slept = []
        c = clients(iam=FakeIAM(allowed=True), **{"lambda": FakeLambda(put_errors=[AwsError("InvalidParameterValueException", "BatchSize out of range")])})
        with self.assertRaises(AwsError):
            go(c, apply=True, steps=("consumer",), sleep=slept.append)
        self.assertEqual(slept, [])


class Enable(unittest.TestCase):
    def test_flag_is_merged_with_the_existing_variables_never_replacing_them(self):
        c = ready()
        rc, out = go(c, apply=True, steps=("enable",))
        self.assertEqual(rc, 0, out)
        self.assertEqual(c["lambda"].updates, [{**ENV, "STRIPE_EVENT_QUEUE_URL": URL}])
        self.assertIn("DAY3_LAMBDA_ARN", c["lambda"].updates[0])

    def test_dry_run_changes_nothing(self):
        c = ready()
        rc, out = go(c, steps=("enable",))
        self.assertEqual((rc, c["lambda"].updates), (0, []))
        self.assertIn("TODO", out)

    def test_refuses_when_there_is_no_consumer(self):
        for mapping in (None, {**GOOD_MAPPING, "State": "Disabled"}):
            c = ready(**{"lambda": FakeLambda(mapping=mapping)})
            rc, out = go(c, apply=True, steps=("enable",))
            self.assertEqual((rc, c["lambda"].updates), (1, []), mapping)
            self.assertIn("nothing processes", out.replace("that nothing processes", "nothing processes"))

    def test_refuses_when_the_role_cannot_use_the_queue(self):
        c = ready(iam=FakeIAM(allowed=False))
        rc, out = go(c, apply=True, steps=("enable",))
        self.assertEqual((rc, c["lambda"].updates), (1, []))

    def test_refuses_when_the_DEPLOYED_code_has_no_queue_mode(self):
        c = ready()
        rc, out = go(c, apply=True, steps=("enable",), fetch=lambda u: code_zip(with_queue_mode=False))
        self.assertEqual((rc, c["lambda"].updates), (1, []))
        self.assertIn("DEPLOYED code", out)

    def test_a_marker_in_a_non_python_file_does_not_count_as_queue_mode(self):
        self.assertFalse(T.code_has_queue_mode(code_zip(with_queue_mode=False)))
        self.assertTrue(T.code_has_queue_mode(code_zip()))

    def test_refuses_when_the_deployed_code_cannot_be_read(self):
        def boom(u):
            raise AwsError("URLError")
        c = ready()
        rc, out = go(c, apply=True, steps=("enable",), fetch=boom)
        self.assertEqual((rc, c["lambda"].updates), (1, []))

    def test_refuses_when_the_queue_does_not_exist(self):
        c = ready(sqs=FakeSQS({}))
        rc, out = go(c, apply=True, steps=("enable",))
        self.assertEqual((rc, c["lambda"].updates), (1, []))

    def test_already_set_to_this_queue_is_fine_and_a_different_value_is_kept(self):
        c = ready(**{"lambda": FakeLambda(mapping=GOOD_MAPPING, env={**ENV, "STRIPE_EVENT_QUEUE_URL": URL})})
        self.assertEqual(go(c, apply=True, steps=("enable",))[0], 0)
        self.assertEqual(c["lambda"].updates, [])
        c = ready(**{"lambda": FakeLambda(mapping=GOOD_MAPPING, env={**ENV, "STRIPE_EVENT_QUEUE_URL": "https://elsewhere"})})
        rc, out = go(c, apply=True, steps=("enable",))
        self.assertEqual((rc, c["lambda"].updates), (1, []))
        self.assertIn("CONFLICT", out)

    def test_an_unreadable_environment_is_never_overwritten(self):
        c = ready(**{"lambda": FakeLambda(mapping=GOOD_MAPPING, env_error="KMSAccessDeniedException")})
        rc, out = go(c, apply=True, steps=("enable",))
        self.assertEqual((rc, c["lambda"].updates), (1, []))

    def test_function_with_no_environment_at_all_gets_just_the_flag(self):
        c = ready(**{"lambda": FakeLambda(mapping=GOOD_MAPPING, env={})})
        go(c, apply=True, steps=("enable",))
        self.assertEqual(c["lambda"].updates, [{"STRIPE_EVENT_QUEUE_URL": URL}])


class Disable(unittest.TestCase):
    def test_removes_only_the_flag_and_keeps_everything_else(self):
        c = ready(**{"lambda": FakeLambda(mapping=GOOD_MAPPING, env={**ENV, "STRIPE_EVENT_QUEUE_URL": URL})})
        rc, out = go(c, apply=True, steps=("disable",))
        self.assertEqual((rc, c["lambda"].updates), (0, [ENV]))
        self.assertIn("keeps draining", out)

    def test_already_off_changes_nothing(self):
        c = ready()
        rc, out = go(c, apply=True, steps=("disable",))
        self.assertEqual((rc, c["lambda"].updates), (0, []))

    def test_unreadable_environment_is_never_overwritten(self):
        c = ready(**{"lambda": FakeLambda(env_error="KMSAccessDeniedException")})
        rc, out = go(c, apply=True, steps=("disable",))
        self.assertEqual((rc, c["lambda"].updates), (1, []))

    def test_disable_does_not_touch_the_queue_or_the_consumer(self):
        c = ready(**{"lambda": FakeLambda(mapping=GOOD_MAPPING, env={**ENV, "STRIPE_EVENT_QUEUE_URL": URL})})
        go(c, apply=True, steps=("disable",))
        self.assertEqual((c["sqs"].creates, c["lambda"].created, c["iam"].attaches), ([], [], []))


class FullRun(unittest.TestCase):
    def test_default_apply_builds_the_plumbing_in_order_and_leaves_the_flag_off(self):
        log = Log()
        c = clients(iam=FakeIAM(log=log), sqs=FakeSQS(log=log), **{"lambda": FakeLambda(log=log)})
        rc, out = go(c, apply=True)
        self.assertEqual(rc, 0, out)
        self.assertEqual([k for k, _ in log], ["sqs-create", "sqs-create", "iam-create", "iam-attach", "mapping-create"])
        self.assertEqual(c["lambda"].updates, [])
        self.assertNotIn("now queues", out)

    def test_a_second_run_against_the_resulting_state_changes_nothing(self):
        c = ready()
        rc, out = go(c, apply=True)
        self.assertEqual(rc, 0, out)
        self.assertEqual((c["sqs"].creates, c["iam"].creates, c["lambda"].created, c["lambda"].updates), ([], [], [], []))

    def test_enable_then_disable_round_trips_the_environment(self):
        c = ready()
        go(c, apply=True, steps=("enable",))
        c["lambda"].cfg["Environment"]["Variables"] = c["lambda"].updates[-1]
        go(c, apply=True, steps=("disable",))
        self.assertEqual(c["lambda"].updates[-1], ENV)


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

    def run_with(self, stubs_clients, steps, fetch=lambda u: code_zip()):
        for _c, s in stubs_clients.values():
            s.activate()
        try:
            rc, out = go({k: v[0] for k, v in stubs_clients.items()}, apply=True, steps=steps, fetch=fetch)
            for _c, s in stubs_clients.values():
                s.assert_no_pending_responses()
        finally:
            for _c, s in stubs_clients.values():
                s.deactivate()
        return rc, out

    def test_default_apply_matches_the_real_models(self):
        lam, iam, sqs = self.mk("lambda"), self.mk("iam"), self.mk("sqs")
        sl, si, sq = lam[1], iam[1], sqs[1]
        role = "relayshield-breach-check-role-1sapnwdl"
        cfg = {"Role": ROLE, "Timeout": 30}
        main, dlq = T.desired_queue_attrs(SPEC, 30)
        denied = {"EvaluationResults": [{"EvalActionName": a, "EvalDecision": "implicitDeny"} for a in T.QUEUE_ACTIONS]}
        allowed = {"EvaluationResults": [{"EvalActionName": a, "EvalDecision": "allowed"} for a in T.QUEUE_ACTIONS]}
        sim = {"PolicySourceArn": ROLE, "ActionNames": T.QUEUE_ACTIONS, "ResourceArns": [QARN]}
        # queues
        sl.add_response("get_function_configuration", cfg, {"FunctionName": FN})
        both = ((SPEC["queue"]["dlq_name"], dlq), (SPEC["queue"]["name"], main))
        for name, _attrs in both:  # the tool plans (reads) both queues first, then creates them: DLQ before main
            sq.add_client_error("get_queue_url", "AWS.SimpleQueueService.NonExistentQueue", expected_params={"QueueName": name})
        for name, attrs in both:
            sq.add_response("create_queue", {"QueueUrl": f"https://sqs.us-east-1.amazonaws.com/{ACCT}/{name}"}, {"QueueName": name, "Attributes": attrs})
        # access
        sl.add_response("get_function_configuration", cfg, {"FunctionName": FN})
        si.add_response("simulate_principal_policy", denied, sim)
        si.add_response("list_attached_role_policies", {"AttachedPolicies": [{"PolicyName": "p", "PolicyArn": "arn:aws:iam::1:policy/p"}]}, {"RoleName": role})
        si.add_client_error("get_policy", "NoSuchEntity", expected_params={"PolicyArn": PARN})
        si.add_response("create_policy", {"Policy": {"PolicyName": SPEC["policy"]["name"]}},
                        {"PolicyName": SPEC["policy"]["name"], "PolicyDocument": json.dumps(T.policy_doc(QARN)), "Description": ANY})
        si.add_response("attach_role_policy", {}, {"RoleName": role, "PolicyArn": PARN})
        # consumer
        sl.add_response("list_event_source_mappings", {"EventSourceMappings": []}, {"FunctionName": FN, "EventSourceArn": QARN})
        sl.add_response("get_function_configuration", cfg, {"FunctionName": FN})
        si.add_response("simulate_principal_policy", allowed, sim)
        sl.add_response("create_event_source_mapping", {"UUID": "11111111-1111-1111-1111-111111111111", "State": "Creating"},
                        {"EventSourceArn": QARN, "FunctionName": FN, "BatchSize": 1, "Enabled": True, "ScalingConfig": {"MaximumConcurrency": 2}})
        rc, out = self.run_with({"lambda": lam, "iam": iam, "sqs": sqs}, T.DEFAULT_STEPS)
        self.assertEqual(rc, 0, out)

    def test_enable_matches_the_real_models_and_merges_the_environment(self):
        lam, iam, sqs = self.mk("lambda"), self.mk("iam"), self.mk("sqs")
        sl, si, sq = lam[1], iam[1], sqs[1]
        cfg = {"Role": ROLE, "Timeout": 30, "Environment": {"Variables": ENV}}
        allowed = {"EvaluationResults": [{"EvalActionName": a, "EvalDecision": "allowed"} for a in T.QUEUE_ACTIONS]}
        sl.add_response("get_function_configuration", cfg, {"FunctionName": FN})
        sq.add_response("get_queue_url", {"QueueUrl": URL}, {"QueueName": SPEC["queue"]["name"]})
        sl.add_response("list_event_source_mappings", {"EventSourceMappings": [{"UUID": "11111111-1111-1111-1111-111111111111", "State": "Enabled", "BatchSize": 1}]},
                        {"FunctionName": FN, "EventSourceArn": QARN})
        si.add_response("simulate_principal_policy", allowed, {"PolicySourceArn": ROLE, "ActionNames": T.QUEUE_ACTIONS, "ResourceArns": [QARN]})
        sl.add_response("get_function", {"Code": {"Location": "https://code/zip"}, "Configuration": cfg}, {"FunctionName": FN})
        sl.add_response("update_function_configuration", cfg,
                        {"FunctionName": FN, "Environment": {"Variables": {**ENV, "STRIPE_EVENT_QUEUE_URL": URL}}})
        rc, out = self.run_with({"lambda": lam, "iam": iam, "sqs": sqs}, ("enable",))
        self.assertEqual(rc, 0, out)

    def test_disable_matches_the_real_models(self):
        lam, iam, sqs = self.mk("lambda"), self.mk("iam"), self.mk("sqs")
        sl = lam[1]
        cfg = {"Role": ROLE, "Timeout": 30, "Environment": {"Variables": {**ENV, "STRIPE_EVENT_QUEUE_URL": URL}}}
        sl.add_response("get_function_configuration", cfg, {"FunctionName": FN})
        sl.add_response("update_function_configuration", cfg, {"FunctionName": FN, "Environment": {"Variables": ENV}})
        rc, out = self.run_with({"lambda": lam, "iam": iam, "sqs": sqs}, ("disable",))
        self.assertEqual(rc, 0, out)

    def test_main_runs_the_default_steps_not_the_switch(self):
        seen = {}
        with patch.object(boto3, "client", MagicMock()), patch.object(T, "run", lambda c, a, s, ap, steps, **k: seen.setdefault("steps", steps) and 0):
            T.main([])
        self.assertEqual(seen["steps"], T.DEFAULT_STEPS)

    def test_the_json_protocol_queue_error_code_is_also_read_as_missing(self):
        sqs, sq = self.mk("sqs")
        sq.add_client_error("get_queue_url", "QueueDoesNotExist", expected_params={"QueueName": "q"})
        with sq:
            row, act = T.plan_one_queue(sqs, "q", {"MessageRetentionPeriod": "60"})
        self.assertEqual((row[1], act is not None), ("todo", True))


if __name__ == "__main__":
    unittest.main()
