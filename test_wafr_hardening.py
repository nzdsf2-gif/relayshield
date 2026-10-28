"""tools/wafr_hardening.py: reserved concurrency, API alarms, log retention.

Two layers, because a fake written by the same hand as the code proves nothing about the library:
  * Fake clients test the DECISIONS (never overwrite a different reservation, never take the pool under
    the floor, block the alarm step with nowhere to send it, dry run writes nothing, wrong account refused).
  * botocore's Stubber, over the REAL lambda / cloudwatch / logs service models, tests the SHAPES: every
    request the tool makes is validated against the model, and every response it parses is a legal one.
    Skipped (and said so) where boto3 is not installed; CI installs it from tests_requirements.txt."""
import copy
import json
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import wafr_hardening as T  # noqa: E402

SPEC = json.load(open(ROOT / "tools" / "wafr_hardening_spec.json"))
ACCT = SPEC["account"]
TOPIC = "arn:aws:sns:us-east-1:239677749008:relayshield-alerts"


class FakeLambda:
    def __init__(self, reserved, unreserved=1000):
        self.reserved, self.unreserved, self.puts = reserved, unreserved, []

    def get_account_settings(self):
        return {"AccountLimit": {"UnreservedConcurrentExecutions": self.unreserved}}

    def get_function_concurrency(self, FunctionName):
        if FunctionName not in self.reserved:
            raise RuntimeError("ResourceNotFoundException")
        v = self.reserved[FunctionName]
        return {} if v is None else {"ReservedConcurrentExecutions": v}

    def put_function_concurrency(self, FunctionName, ReservedConcurrentExecutions):
        self.puts.append((FunctionName, ReservedConcurrentExecutions))


class FakeCW:
    def __init__(self, actions=(TOPIC,)):
        self.actions, self.puts, self.have = list(actions), [], {}

    def describe_alarms(self, **kw):
        if "AlarmNames" in kw:
            return {"MetricAlarms": [self.have[n] for n in kw["AlarmNames"] if n in self.have]}
        a = [{"AlarmName": "x", "Namespace": "AWS/Lambda", "MetricName": "Errors", "AlarmActions": self.actions}]
        return {"MetricAlarms": a if self.actions else [{"AlarmName": "x", "Namespace": "AWS/Lambda", "MetricName": "Errors"}]}

    def put_metric_alarm(self, **kw):
        self.puts.append(kw["AlarmName"])


class FakeLogs:
    def __init__(self, groups):
        self.groups, self.puts = groups, []

    def describe_log_groups(self, **kw):
        return {"logGroups": self.groups}

    def put_retention_policy(self, logGroupName, retentionInDays):
        self.puts.append((logGroupName, retentionInDays))


def go(clients, apply=False, steps=T.STEPS, acct=ACCT, spec=SPEC, sns=None):
    lines = []
    rc = T.run(clients, lambda: acct, spec, apply, steps, sns, out=lines.append)
    return rc, "\n".join(lines)


ALL_NONE = {"relayshield-api": None, "relayshield-bundle-fulfillment": None, "relayshield-stripe-webhook": None}


class Decisions(unittest.TestCase):
    def test_wrong_account_refused_and_nothing_written(self):
        lam = FakeLambda(ALL_NONE)
        rc, out = go({"lambda": lam}, apply=True, steps=("concurrency",), acct="620534471984")
        self.assertEqual(rc, 2)
        self.assertIn("Refusing to run", out)
        self.assertEqual(lam.puts, [])

    def test_dry_run_writes_nothing_and_says_so(self):
        lam, cw, lg = FakeLambda(ALL_NONE), FakeCW(), FakeLogs([{"logGroupName": "/aws/x", "storedBytes": 5, "creationTime": 0}])
        rc, out = go({"lambda": lam, "cloudwatch": cw, "logs": lg})
        self.assertEqual((lam.puts, cw.puts, lg.puts), ([], [], []))
        self.assertIn("Dry run only", out)
        self.assertEqual(rc, 0)

    def test_apply_reserves_only_where_there_is_none(self):
        lam = FakeLambda({"relayshield-api": None, "relayshield-bundle-fulfillment": 10, "relayshield-stripe-webhook": None})
        go({"lambda": lam}, apply=True, steps=("concurrency",))
        self.assertEqual(sorted(lam.puts), [("relayshield-api", 100), ("relayshield-stripe-webhook", 10)])

    def test_different_existing_reservation_is_reported_not_overwritten(self):
        lam = FakeLambda({**ALL_NONE, "relayshield-api": 5})
        rc, out = go({"lambda": lam}, apply=True, steps=("concurrency",))
        self.assertNotIn(("relayshield-api", 100), lam.puts)
        self.assertIn("CONFLICT", out)
        self.assertEqual(rc, 1)

    def test_pool_floor_blocks_every_reservation(self):
        lam = FakeLambda(ALL_NONE, unreserved=150)  # 120 to take would leave 30, under AWS's floor of 100
        rc, out = go({"lambda": lam}, apply=True, steps=("concurrency",))
        self.assertEqual(lam.puts, [])
        self.assertIn("BLOCKED", out)
        self.assertEqual(rc, 1)

    def test_missing_function_is_reported(self):
        lam = FakeLambda({"relayshield-api": None})
        rc, out = go({"lambda": lam}, steps=("concurrency",))
        self.assertIn("MISSING", out)
        self.assertEqual(rc, 1)

    def test_alarm_blocked_when_nobody_would_be_told(self):
        cw = FakeCW(actions=())
        rc, out = go({"cloudwatch": cw}, apply=True, steps=("alarm",))
        self.assertEqual(cw.puts, [])
        self.assertIn("BLOCKED", out)
        self.assertEqual(rc, 1)

    def test_alarm_copies_existing_actions_and_creates_three(self):
        cw = FakeCW()
        go({"cloudwatch": cw}, apply=True, steps=("alarm",))
        self.assertEqual(cw.puts, ["relayshield-api-errors", "relayshield-api-throttles", "relayshield-api-concurrency-high"])

    def test_concurrency_alarm_threshold_is_share_of_reserved(self):
        d = {x["AlarmName"]: x for x in T.alarm_defs(SPEC, [TOPIC])}
        self.assertEqual(d["relayshield-api-concurrency-high"]["Threshold"], 80.0)

    def test_alarm_unchanged_when_already_as_specified(self):
        cw = FakeCW()
        for d in T.alarm_defs(SPEC, [TOPIC]):
            cw.have[d["AlarmName"]] = {"AlarmName": d["AlarmName"], "Threshold": d["Threshold"], "AlarmActions": [TOPIC]}
        go({"cloudwatch": cw}, apply=True, steps=("alarm",))
        self.assertEqual(cw.puts, [])

    def test_retention_sets_only_groups_without_one_and_leaves_others(self):
        now = int(time.time() * 1000)
        lg = FakeLogs([{"logGroupName": "/a", "creationTime": now}, {"logGroupName": "/b", "retentionInDays": 7, "creationTime": now},
                       {"logGroupName": "/c", "retentionInDays": 400, "creationTime": now}])
        go({"logs": lg}, apply=True, steps=("retention",))
        self.assertEqual(lg.puts, [("/a", 90)])

    def test_dry_run_retention_warns_that_old_events_are_deleted(self):
        lg = FakeLogs([{"logGroupName": "/a", "storedBytes": 1234, "creationTime": 0}])
        _rc, out = go({"logs": lg}, steps=("retention",))
        self.assertIn("will be deleted", out)
        self.assertIn("1,234 bytes", out)


try:
    import boto3
    from botocore.stub import Stubber
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
        cw, sc = self.mk("cloudwatch")
        lg, sg = self.mk("logs")
        sl.add_response("get_account_settings", {"AccountLimit": {"ConcurrentExecutions": 1000, "UnreservedConcurrentExecutions": 1000}})
        for fn, v in (("relayshield-api", None), ("relayshield-bundle-fulfillment", None), ("relayshield-stripe-webhook", 10)):
            sl.add_response("get_function_concurrency", {} if v is None else {"ReservedConcurrentExecutions": v}, {"FunctionName": fn})
        sl.add_response("put_function_concurrency", {"ReservedConcurrentExecutions": 100},
                        {"FunctionName": "relayshield-api", "ReservedConcurrentExecutions": 100})
        sl.add_response("put_function_concurrency", {"ReservedConcurrentExecutions": 10},
                        {"FunctionName": "relayshield-bundle-fulfillment", "ReservedConcurrentExecutions": 10})

        sc.add_response("describe_alarms", {"MetricAlarms": [{"AlarmName": "e", "Namespace": "AWS/Lambda", "MetricName": "Errors",
                                                              "AlarmActions": [TOPIC]}]}, {"AlarmTypes": ["MetricAlarm"]})
        defs = T.alarm_defs(SPEC, [TOPIC])
        for d in defs:
            sc.add_response("describe_alarms", {"MetricAlarms": []}, {"AlarmNames": [d["AlarmName"]]})
        for d in defs:
            sc.add_response("put_metric_alarm", {}, d)  # expected_params = the exact request, validated against the model

        sg.add_response("describe_log_groups", {"logGroups": [{"logGroupName": "/aws/lambda/a", "creationTime": 1, "storedBytes": 9}],
                                                "nextToken": "t"}, {})
        sg.add_response("describe_log_groups", {"logGroups": [{"logGroupName": "/aws/lambda/b", "retentionInDays": 90}]}, {"nextToken": "t"})
        sg.add_response("put_retention_policy", {}, {"logGroupName": "/aws/lambda/a", "retentionInDays": 90})

        with sl, sc, sg:
            rc, out = go({"lambda": lam, "cloudwatch": cw, "logs": lg}, apply=True)
            sl.assert_no_pending_responses()
            sc.assert_no_pending_responses()
            sg.assert_no_pending_responses()
        self.assertEqual(rc, 0, out)


if __name__ == "__main__":
    unittest.main()
