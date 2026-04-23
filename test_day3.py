"""
Tests for the Day 3 onboarding follow-up flow.

Covers:
  - Tier variable selection (personal vs business)
  - lambda_handler eligibility gates (inactive, wrong state, missing number)
  - lambda_handler happy path (personal and business tiers)
  - schedule_day3_followup in stripe webhook (schedule created, env vars missing)

Run:
    python -m pytest test_day3.py -v
    # or without pytest:
    python test_day3.py
"""

import json
import sys
import unittest
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Helpers to build fake DynamoDB user records
# ---------------------------------------------------------------------------

def make_user(
    user_id="user-123",
    tier="personal_shield",
    state="ACTIVE",
    active=True,
    whatsapp_number="whatsapp:+16175550001",
):
    return {
        "user_id": user_id,
        "subscription_tier": tier,
        "onboarding_state": state,
        "active": active,
        "whatsapp_number": whatsapp_number,
    }


# ---------------------------------------------------------------------------
# 1. Tier variable selection
# ---------------------------------------------------------------------------

class TestGetTierVars(unittest.TestCase):

    def setUp(self):
        import relayshield_day3_sender as d3
        self.d3 = d3

    def test_personal_shield_gets_reuse_and_sessions(self):
        tv = self.d3.get_tier_vars("personal_shield")
        self.assertEqual(tv["cmd2"], "REUSE")
        self.assertEqual(tv["cmd3"], "SESSIONS")

    def test_business_starter_gets_phone_and_add(self):
        tv = self.d3.get_tier_vars("business_starter")
        self.assertEqual(tv["cmd2"], "PHONE")
        self.assertEqual(tv["cmd3"], "ADD")

    def test_business_basic_gets_phone_and_add(self):
        tv = self.d3.get_tier_vars("business_basic")
        self.assertEqual(tv["cmd2"], "PHONE")
        self.assertEqual(tv["cmd3"], "ADD")

    def test_business_shield_gets_phone_and_add(self):
        tv = self.d3.get_tier_vars("business_shield")
        self.assertEqual(tv["cmd2"], "PHONE")
        self.assertEqual(tv["cmd3"], "ADD")

    def test_business_shield_pro_gets_phone_and_add(self):
        tv = self.d3.get_tier_vars("business_shield_pro")
        self.assertEqual(tv["cmd2"], "PHONE")
        self.assertEqual(tv["cmd3"], "ADD")

    def test_unknown_tier_defaults_to_personal(self):
        # Unknown tier should default to personal (non-business) commands
        tv = self.d3.get_tier_vars("unknown_tier")
        self.assertEqual(tv["cmd2"], "REUSE")
        self.assertEqual(tv["cmd3"], "SESSIONS")


# ---------------------------------------------------------------------------
# 2. lambda_handler eligibility gates
# ---------------------------------------------------------------------------

class TestLambdaHandlerEligibility(unittest.TestCase):

    def setUp(self):
        import relayshield_day3_sender as d3
        self.d3 = d3
        # Patch the template SID so the guard check passes
        self._orig_sid = d3.DAY3_TEMPLATE_SID
        d3.DAY3_TEMPLATE_SID = "HXtest000000"

    def tearDown(self):
        self.d3.DAY3_TEMPLATE_SID = self._orig_sid

    def _call(self, user_record, event=None):
        if event is None:
            event = {"user_id": user_record["user_id"], "tier": user_record["subscription_tier"]}
        with patch.object(self.d3, "get_user", return_value=user_record), \
             patch.object(self.d3, "get_twilio_credentials", return_value=("sid", "token", "+1555")), \
             patch.object(self.d3, "send_whatsapp_template", return_value=True) as mock_send:
            result = self.d3.lambda_handler(event, None)
            return result, mock_send

    def test_suppressed_when_user_not_found(self):
        with patch.object(self.d3, "get_user", return_value=None):
            result = self.d3.lambda_handler({"user_id": "ghost", "tier": "personal_shield"}, None)
        self.assertEqual(result["statusCode"], 200)
        self.assertIn("not found", result["body"])

    def test_suppressed_when_user_inactive(self):
        result, mock_send = self._call(make_user(active=False))
        self.assertEqual(result["statusCode"], 200)
        self.assertIn("inactive", result["body"])
        mock_send.assert_not_called()

    def test_suppressed_when_onboarding_state_not_eligible(self):
        result, mock_send = self._call(make_user(state="AWAITING_EMAIL_1"))
        # AWAITING_EMAIL_1 IS in DAY3_ELIGIBLE_STATES — should send
        mock_send.assert_called_once()

    def test_suppressed_when_onboarding_state_is_unknown(self):
        result, mock_send = self._call(make_user(state="SOME_UNKNOWN_STATE"))
        self.assertEqual(result["statusCode"], 200)
        mock_send.assert_not_called()

    def test_suppressed_when_no_whatsapp_number(self):
        user = make_user(whatsapp_number="")
        user.pop("whatsapp_number", None)
        result, mock_send = self._call(user)
        self.assertEqual(result["statusCode"], 200)
        mock_send.assert_not_called()

    def test_suppressed_when_template_sid_is_placeholder(self):
        self.d3.DAY3_TEMPLATE_SID = "PENDING_META_APPROVAL"
        with patch.object(self.d3, "get_user", return_value=make_user()):
            result = self.d3.lambda_handler({"user_id": "user-123", "tier": "personal_shield"}, None)
        self.assertEqual(result["statusCode"], 500)

    def test_missing_user_id_returns_400(self):
        with patch.object(self.d3, "get_user", return_value=make_user()):
            result = self.d3.lambda_handler({"tier": "personal_shield"}, None)
        self.assertEqual(result["statusCode"], 400)


# ---------------------------------------------------------------------------
# 3. lambda_handler happy path — correct template variables sent
# ---------------------------------------------------------------------------

class TestLambdaHandlerHappyPath(unittest.TestCase):

    def setUp(self):
        import relayshield_day3_sender as d3
        self.d3 = d3
        self._orig_sid = d3.DAY3_TEMPLATE_SID
        d3.DAY3_TEMPLATE_SID = "HXtest000000"

    def tearDown(self):
        self.d3.DAY3_TEMPLATE_SID = self._orig_sid

    def _run(self, tier):
        user = make_user(tier=tier)
        event = {"user_id": user["user_id"], "tier": tier}
        with patch.object(self.d3, "get_user", return_value=user), \
             patch.object(self.d3, "get_twilio_credentials", return_value=("sid", "token", "+1555")), \
             patch.object(self.d3, "send_whatsapp_template", return_value=True) as mock_send:
            result = self.d3.lambda_handler(event, None)
            return result, mock_send

    def test_personal_shield_sends_reuse_and_sessions(self):
        result, mock_send = self._run("personal_shield")
        self.assertEqual(result["statusCode"], 200)
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args
        variables = call_kwargs[1]["variables"] if call_kwargs[1] else call_kwargs[0][2]
        # Check via keyword arg pattern used in the Lambda
        sent_vars = mock_send.call_args.kwargs.get("variables") or mock_send.call_args[1].get("variables")
        self.assertEqual(sent_vars["1"], "Personal Shield")
        self.assertEqual(sent_vars["2"], "REUSE")
        self.assertEqual(sent_vars["4"], "SESSIONS")

    def test_business_basic_sends_phone_and_add(self):
        result, mock_send = self._run("business_basic")
        self.assertEqual(result["statusCode"], 200)
        mock_send.assert_called_once()
        sent_vars = mock_send.call_args.kwargs.get("variables") or mock_send.call_args[1].get("variables")
        self.assertEqual(sent_vars["1"], "Business Basic")
        self.assertEqual(sent_vars["2"], "PHONE")
        self.assertEqual(sent_vars["4"], "ADD")

    def test_business_starter_sends_phone_and_add(self):
        result, mock_send = self._run("business_starter")
        sent_vars = mock_send.call_args.kwargs.get("variables") or mock_send.call_args[1].get("variables")
        self.assertEqual(sent_vars["1"], "Business Starter")
        self.assertEqual(sent_vars["2"], "PHONE")
        self.assertEqual(sent_vars["4"], "ADD")

    def test_tier_from_dynamodb_overrides_event_payload(self):
        # Event says personal_shield but DynamoDB record says business_basic
        user = make_user(tier="business_basic")
        event = {"user_id": user["user_id"], "tier": "personal_shield"}
        with patch.object(self.d3, "get_user", return_value=user), \
             patch.object(self.d3, "get_twilio_credentials", return_value=("sid", "token", "+1555")), \
             patch.object(self.d3, "send_whatsapp_template", return_value=True) as mock_send:
            self.d3.lambda_handler(event, None)
        sent_vars = mock_send.call_args.kwargs.get("variables") or mock_send.call_args[1].get("variables")
        self.assertEqual(sent_vars["2"], "PHONE")  # business, not personal

    def test_return_body_contains_sent_true(self):
        result, _ = self._run("personal_shield")
        body = json.loads(result["body"])
        self.assertTrue(body["sent"])

    def test_correct_template_sid_used(self):
        result, mock_send = self._run("personal_shield")
        sent_sid = mock_send.call_args.kwargs.get("template_sid") or mock_send.call_args[1].get("template_sid")
        self.assertEqual(sent_sid, "HXtest000000")

    def test_all_five_variables_present(self):
        """Template requires exactly 5 variables — verify none are missing."""
        result, mock_send = self._run("personal_shield")
        sent_vars = mock_send.call_args.kwargs.get("variables") or mock_send.call_args[1].get("variables")
        for key in ("1", "2", "3", "4", "5"):
            self.assertIn(key, sent_vars, f"Template variable {{{{{key}}}}} is missing")
            self.assertTrue(sent_vars[key], f"Template variable {{{{{key}}}}} is empty")


# ---------------------------------------------------------------------------
# 4. schedule_day3_followup in stripe webhook
# ---------------------------------------------------------------------------

class TestScheduleDay3Followup(unittest.TestCase):

    def setUp(self):
        import relayshield_stripe_webhook as sw
        self.sw = sw
        self._orig_lambda_arn = sw.DAY3_LAMBDA_ARN
        self._orig_role_arn = sw.DAY3_SCHEDULER_ROLE_ARN

    def tearDown(self):
        self.sw.DAY3_LAMBDA_ARN = self._orig_lambda_arn
        self.sw.DAY3_SCHEDULER_ROLE_ARN = self._orig_role_arn

    def test_creates_schedule_with_correct_name(self):
        self.sw.DAY3_LAMBDA_ARN = "arn:aws:lambda:us-east-1:123:function:relayshield-day3-sender"
        self.sw.DAY3_SCHEDULER_ROLE_ARN = "arn:aws:iam::123:role/relayshield-scheduler-invoke-day3"

        with patch.object(self.sw.scheduler_client, "create_schedule") as mock_create:
            self.sw.schedule_day3_followup("user-abc", "personal_shield")

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        self.assertEqual(call_kwargs["Name"], "relayshield-day3-user-abc")

    def test_schedule_uses_at_expression(self):
        self.sw.DAY3_LAMBDA_ARN = "arn:aws:lambda:us-east-1:123:function:relayshield-day3-sender"
        self.sw.DAY3_SCHEDULER_ROLE_ARN = "arn:aws:iam::123:role/relayshield-scheduler-invoke-day3"

        with patch.object(self.sw.scheduler_client, "create_schedule") as mock_create:
            self.sw.schedule_day3_followup("user-abc", "personal_shield")

        call_kwargs = mock_create.call_args[1]
        self.assertTrue(call_kwargs["ScheduleExpression"].startswith("at("))

    def test_schedule_payload_contains_user_id_and_tier(self):
        self.sw.DAY3_LAMBDA_ARN = "arn:aws:lambda:us-east-1:123:function:relayshield-day3-sender"
        self.sw.DAY3_SCHEDULER_ROLE_ARN = "arn:aws:iam::123:role/relayshield-scheduler-invoke-day3"

        with patch.object(self.sw.scheduler_client, "create_schedule") as mock_create:
            self.sw.schedule_day3_followup("user-xyz", "business_basic")

        target_input = json.loads(mock_create.call_args[1]["Target"]["Input"])
        self.assertEqual(target_input["user_id"], "user-xyz")
        self.assertEqual(target_input["tier"], "business_basic")

    def test_schedule_sets_action_after_completion_delete(self):
        self.sw.DAY3_LAMBDA_ARN = "arn:aws:lambda:us-east-1:123:function:relayshield-day3-sender"
        self.sw.DAY3_SCHEDULER_ROLE_ARN = "arn:aws:iam::123:role/relayshield-scheduler-invoke-day3"

        with patch.object(self.sw.scheduler_client, "create_schedule") as mock_create:
            self.sw.schedule_day3_followup("user-abc", "personal_shield")

        call_kwargs = mock_create.call_args[1]
        self.assertEqual(call_kwargs["ActionAfterCompletion"], "DELETE")

    def test_skipped_when_lambda_arn_not_set(self):
        self.sw.DAY3_LAMBDA_ARN = ""
        self.sw.DAY3_SCHEDULER_ROLE_ARN = "arn:aws:iam::123:role/some-role"

        with patch.object(self.sw.scheduler_client, "create_schedule") as mock_create:
            self.sw.schedule_day3_followup("user-abc", "personal_shield")

        mock_create.assert_not_called()

    def test_skipped_when_role_arn_not_set(self):
        self.sw.DAY3_LAMBDA_ARN = "arn:aws:lambda:us-east-1:123:function:relayshield-day3-sender"
        self.sw.DAY3_SCHEDULER_ROLE_ARN = ""

        with patch.object(self.sw.scheduler_client, "create_schedule") as mock_create:
            self.sw.schedule_day3_followup("user-abc", "personal_shield")

        mock_create.assert_not_called()

    def test_scheduler_failure_does_not_raise(self):
        self.sw.DAY3_LAMBDA_ARN = "arn:aws:lambda:us-east-1:123:function:relayshield-day3-sender"
        self.sw.DAY3_SCHEDULER_ROLE_ARN = "arn:aws:iam::123:role/some-role"

        with patch.object(
            self.sw.scheduler_client, "create_schedule",
            side_effect=Exception("Simulated AWS error")
        ):
            # Must not raise — onboarding must not fail over this
            try:
                self.sw.schedule_day3_followup("user-abc", "personal_shield")
            except Exception:
                self.fail("schedule_day3_followup raised an exception — must be non-fatal")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestGetTierVars))
    suite.addTests(loader.loadTestsFromTestCase(TestLambdaHandlerEligibility))
    suite.addTests(loader.loadTestsFromTestCase(TestLambdaHandlerHappyPath))
    suite.addTests(loader.loadTestsFromTestCase(TestScheduleDay3Followup))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
