"""Tests for the Telegram-first checkout flow in relayshield_stripe_webhook.

Covers tier resolution when the pre-payment record carries no tier. Before the
fix the fallback referenced `subscription_tier`, which is only assigned later in
the WhatsApp flow, so the handler raised and Stripe retried forever.

boto3 is stubbed before import because the module creates AWS clients at import.
"""

import json
import os
import sys
import unittest
from unittest import mock

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

sys.modules.setdefault("boto3", mock.MagicMock())
sys.modules.setdefault("boto3.dynamodb", mock.MagicMock())
sys.modules.setdefault("boto3.dynamodb.conditions", mock.MagicMock())

import relayshield_stripe_webhook as wh  # noqa: E402

PLINK = "plink_1TIVkIL2dcjOeFiYCB6i7g5g"  # Business Shield (monthly)
CHAT_ID = "123456789"


def _event(session_extra=None):
    session = {
        "id": "cs_test_1",
        "customer": "cus_1",
        "subscription": "sub_1",
        "client_reference_id": CHAT_ID,
    }
    session.update(session_extra or {})
    body = json.dumps({
        "type": "checkout.session.completed",
        "data": {"object": session},
    })
    return {"body": body, "headers": {"Stripe-Signature": "t=1,v1=x"}}


class TelegramTierResolution(unittest.TestCase):
    def setUp(self):
        self.pre_payment = {
            "user_id": "u1",
            "onboarding_state": "AWAITING_PAYMENT",
        }
        patches = {
            "verify_stripe_signature": mock.Mock(return_value=True),
            "get_secret": mock.Mock(return_value="secret"),
            "get_secret_json": mock.Mock(return_value="bot-token"),
            "get_pre_payment_record": mock.Mock(side_effect=lambda _c: self.pre_payment),
            "get_price_id_from_subscription": mock.Mock(return_value=None),
            "advance_telegram_record": mock.Mock(),
            "schedule_day3_followup": mock.Mock(),
            "send_telegram_phone_request": mock.Mock(return_value=True),
        }
        self.m = {}
        for name, m in patches.items():
            p = mock.patch.object(wh, name, m)
            p.start()
            self.addCleanup(p.stop)
            self.m[name] = m

    def test_tier_on_pre_payment_record_is_used_unchanged(self):
        self.pre_payment["subscription_tier"] = wh.TIER_PERSONAL
        resp = wh.lambda_handler(_event({"payment_link": PLINK}), None)
        self.assertEqual(resp["statusCode"], 200)
        body = json.loads(resp["body"])
        self.assertEqual(body["subscription_tier"], wh.TIER_PERSONAL)
        self.assertEqual(body["onboarding_state"], "AWAITING_PHONE")
        self.m["advance_telegram_record"].assert_called_once_with(
            "u1", "cus_1", "sub_1", wh.TIER_PERSONAL)

    def test_missing_tier_resolves_from_payment_link(self):
        resp = wh.lambda_handler(_event({"payment_link": PLINK}), None)
        self.assertEqual(resp["statusCode"], 200)
        body = json.loads(resp["body"])
        self.assertEqual(body["subscription_tier"], wh.TIER_SHIELD)
        self.assertEqual(body["onboarding_state"], "AWAITING_PHONE")
        self.m["advance_telegram_record"].assert_called_once_with(
            "u1", "cus_1", "sub_1", wh.TIER_SHIELD)
        self.m["schedule_day3_followup"].assert_called_once_with("u1", wh.TIER_SHIELD)
        self.m["send_telegram_phone_request"].assert_called_once_with(
            CHAT_ID, "bot-token", "Business Shield")

    def test_empty_tier_resolves_from_session_metadata(self):
        self.pre_payment["subscription_tier"] = ""
        resp = wh.lambda_handler(_event({"metadata": {"tier": "Business Basic"}}), None)
        body = json.loads(resp["body"])
        self.assertEqual(body["subscription_tier"], wh.TIER_BASIC)

    def test_missing_tier_resolves_from_subscription_price(self):
        price_id = next(k for k, v in wh.PRICE_TIER_MAP.items() if v == wh.TIER_PRO)
        self.m["get_price_id_from_subscription"].return_value = price_id
        resp = wh.lambda_handler(_event(), None)
        body = json.loads(resp["body"])
        self.assertEqual(body["subscription_tier"], wh.TIER_PRO)

    def test_unresolvable_tier_returns_200_error_and_does_not_advance(self):
        resp = wh.lambda_handler(_event({"payment_link": "plink_unknown"}), None)
        self.assertEqual(resp["statusCode"], 200)
        body = json.loads(resp["body"])
        self.assertEqual(body["error"], "Could not determine subscription tier")
        self.assertEqual(body["payment_link"], "plink_unknown")
        self.assertEqual(body["telegram_chat_id"], CHAT_ID)
        self.m["advance_telegram_record"].assert_not_called()
        self.m["schedule_day3_followup"].assert_not_called()
        self.m["send_telegram_phone_request"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
