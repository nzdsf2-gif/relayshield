"""relayshield_stripe_webhook.py: synchronous behaviour (pinned) and the optional queue mode (WAFR REL 4).

The webhook had no tests of its own before 2026-10-29, and it is the path that onboards a paying customer. So the
first class here, Synchronous, pins what the handler does TODAY, and was run against the unchanged handler before
the queue mode was added. If one of those fails after a change, the change altered the payment path.

Queue mode is OFF unless the Lambda environment variable STRIPE_EVENT_QUEUE_URL is set. When set, the HTTP request
is still signature-verified (the 5-minute timestamp tolerance only makes sense at the door), the event is put on
the queue and Stripe gets a 200; the same function, invoked by SQS, does the processing. An enqueue failure
returns 500 so Stripe retries for up to three days; a processing failure raises so SQS retries and then redrives
to a dead-letter queue.

NOT covered: that SQS really invokes this function with this event shape (the record fields used, eventSource,
eventSourceARN and body, are the documented ones), and any real AWS or Stripe call."""
import hashlib
import hmac
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import relayshield_stripe_webhook as sw  # noqa: E402

SECRET = "whsec_test_secret"
QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/239677749008/relayshield-stripe-events"
QUEUE_ARN = "arn:aws:sqs:us-east-1:239677749008:relayshield-stripe-events"


def signed_http(event_obj, secret=SECRET, ts=None, header=True):
    body = json.dumps(event_obj)
    ts = int(time.time()) if ts is None else ts
    sig = hmac.new(secret.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    return {"body": body, "headers": {"Stripe-Signature": f"t={ts},v1={sig}"} if header else {}, "isBase64Encoded": False}


def checkout(session=None, event_id="evt_1"):
    base = {"id": "cs_test_1", "customer": "cus_1", "subscription": "sub_1", "client_reference_id": "",
            "customer_details": {"phone": "+14155550123", "email": "a@example.com"}, "payment_link": "plink_1THTZrL2dcjOeFiYO4RQryp6"}
    base.update(session or {})
    return {"id": event_id, "type": "checkout.session.completed", "data": {"object": base}}


def sqs_event(stripe_event, arn=QUEUE_ARN, source="aws:sqs", message_id="m1"):
    return {"Records": [{"messageId": message_id, "eventSource": source, "eventSourceARN": arn,
                         "body": json.dumps({"v": 1, "event_id": stripe_event.get("id", ""), "event": stripe_event})}]}


class Base(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop("STRIPE_EVENT_QUEUE_URL", None)
        self.p = {}
        for name, rv in (("get_secret", None), ("get_price_id_from_subscription", None), ("get_pre_payment_record", None),
                         ("advance_telegram_record", None), ("schedule_day3_followup", None), ("send_telegram_phone_request", True),
                         ("user_exists_for_phone", False), ("create_user_record", "user-1"), ("send_welcome_email_ses", True),
                         ("get_twilio_credentials", ("sid", "tok", "from")), ("send_whatsapp_template", True), ("send_whatsapp", True)):
            m = patch.object(sw, name, MagicMock(return_value=rv))
            self.p[name] = m.start()
            self.addCleanup(m.stop)
        self.p["get_secret"].side_effect = lambda name: SECRET if name == sw.STRIPE_WEBHOOK_SECRET_NAME else "sk_test"
        tg = patch.object(sw, "get_secret_json", MagicMock(return_value="bot-token"))
        tg.start()
        self.addCleanup(tg.stop)
        sqs = patch.object(sw, "sqs_client", MagicMock(), create=True)
        self.sqs = sqs.start()
        self.addCleanup(sqs.stop)
        self.addCleanup(self.env.stop)

    def call(self, event):
        return sw.lambda_handler(event, None)

    def code(self, event):
        return self.call(event)["statusCode"]


class Synchronous(Base):
    """Queue mode off: the handler does exactly what it did before."""

    def test_missing_signature_header_is_400(self):
        self.assertEqual(self.code(signed_http(checkout(), header=False)), 400)

    def test_wrong_signature_is_400_and_nothing_happens(self):
        self.assertEqual(self.code(signed_http(checkout(), secret="whsec_other")), 400)
        self.p["create_user_record"].assert_not_called()

    def test_stale_timestamp_is_400(self):
        self.assertEqual(self.code(signed_http(checkout(), ts=int(time.time()) - 3600)), 400)

    def test_secret_retrieval_failure_is_500_so_stripe_retries(self):
        self.p["get_secret"].side_effect = RuntimeError("secrets down")
        self.assertEqual(self.code(signed_http(checkout())), 500)

    def test_invalid_json_with_a_valid_signature_is_400(self):
        body = "not json"
        ts = int(time.time())
        sig = hmac.new(SECRET.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
        self.assertEqual(self.code({"body": body, "headers": {"stripe-signature": f"t={ts},v1={sig}"}}), 400)

    def test_other_event_types_are_acknowledged_and_ignored(self):
        r = self.call(signed_http({"id": "evt_x", "type": "invoice.paid", "data": {"object": {}}}))
        self.assertEqual(r["statusCode"], 200)
        self.assertIn("acknowledged, not processed", r["body"])
        self.p["create_user_record"].assert_not_called()

    def test_ti_checkout_is_skipped(self):
        self.p["get_price_id_from_subscription"].return_value = next(iter(sw.TI_PRICE_IDS))
        r = self.call(signed_http(checkout()))
        self.assertEqual(r["statusCode"], 200)
        self.assertIn("developer webhook", r["body"])
        self.p["create_user_record"].assert_not_called()

    def test_whatsapp_flow_onboards_the_customer(self):
        r = self.call(signed_http(checkout()))
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(json.loads(r["body"])["onboarding_state"], "AWAITING_EMAIL_1")
        kw = self.p["create_user_record"].call_args.kwargs
        self.assertEqual((kw["phone_number"], kw["subscription_tier"], kw["referred_by"]), ("+14155550123", "personal_shield", ""))
        self.p["send_whatsapp_template"].assert_called_once()

    def test_partner_code_reaches_the_user_record_and_does_not_enter_the_telegram_flow(self):
        self.call(signed_http(checkout({"client_reference_id": "p_abc123"})))
        self.assertEqual(self.p["create_user_record"].call_args.kwargs["referred_by"], "abc123")
        self.p["get_pre_payment_record"].assert_not_called()

    def test_telegram_flow_advances_an_awaiting_payment_record(self):
        self.p["get_pre_payment_record"].return_value = {"user_id": "u9", "onboarding_state": "AWAITING_PAYMENT", "subscription_tier": "business_basic"}
        r = self.call(signed_http(checkout({"client_reference_id": "123456"})))
        self.assertEqual(json.loads(r["body"])["onboarding_state"], "AWAITING_PHONE")
        self.p["advance_telegram_record"].assert_called_once()
        self.p["create_user_record"].assert_not_called()

    def test_telegram_flow_skips_a_record_that_is_already_advanced(self):
        self.p["get_pre_payment_record"].return_value = {"user_id": "u9", "onboarding_state": "AWAITING_PHONE"}
        r = self.call(signed_http(checkout({"client_reference_id": "123456"})))
        self.assertIn("Already processed", r["body"])
        self.p["advance_telegram_record"].assert_not_called()

    def test_telegram_flow_with_no_prepayment_record_is_200_not_a_retry(self):
        r = self.call(signed_http(checkout({"client_reference_id": "123456"})))
        self.assertEqual(r["statusCode"], 200)

    def test_user_that_already_exists_is_not_created_twice(self):
        self.p["user_exists_for_phone"].return_value = True
        r = self.call(signed_http(checkout()))
        self.assertEqual(r["statusCode"], 200)
        self.p["create_user_record"].assert_not_called()

    def test_database_write_failure_is_500_so_stripe_retries(self):
        self.p["create_user_record"].side_effect = RuntimeError("ddb down")
        self.assertEqual(self.code(signed_http(checkout())), 500)

    def test_the_http_path_never_touches_sqs_when_the_flag_is_unset(self):
        self.call(signed_http(checkout()))
        self.sqs.send_message.assert_not_called()


class QueueModeIntake(Base):
    def setUp(self):
        super().setUp()
        os.environ["STRIPE_EVENT_QUEUE_URL"] = QUEUE_URL

    def test_verified_checkout_is_queued_once_and_not_processed_inline(self):
        ev = checkout()
        r = self.call(signed_http(ev))
        self.assertEqual(r["statusCode"], 200)
        self.sqs.send_message.assert_called_once()
        kw = self.sqs.send_message.call_args.kwargs
        self.assertEqual(kw["QueueUrl"], QUEUE_URL)
        body = json.loads(kw["MessageBody"])
        self.assertEqual((body["v"], body["event_id"], body["event"]), (1, "evt_1", ev))
        self.p["create_user_record"].assert_not_called()
        self.p["send_whatsapp_template"].assert_not_called()

    def test_bad_signature_is_400_and_never_queued(self):
        self.assertEqual(self.code(signed_http(checkout(), secret="whsec_other")), 400)
        self.sqs.send_message.assert_not_called()

    def test_other_event_types_are_acknowledged_without_queueing(self):
        r = self.call(signed_http({"id": "evt_x", "type": "invoice.paid", "data": {"object": {}}}))
        self.assertEqual(r["statusCode"], 200)
        self.sqs.send_message.assert_not_called()

    def test_enqueue_failure_is_500_so_stripe_retries_and_nothing_is_processed_inline(self):
        self.sqs.send_message.side_effect = RuntimeError("sqs down")
        self.assertEqual(self.code(signed_http(checkout())), 500)
        self.p["create_user_record"].assert_not_called()

    def test_the_queued_message_carries_no_signature_or_secret(self):
        self.call(signed_http(checkout()))
        sent = self.sqs.send_message.call_args.kwargs["MessageBody"]
        self.assertNotIn(SECRET, sent)
        self.assertNotIn("v1=", sent)


class QueueModeConsumer(Base):
    def test_a_queued_event_is_processed_exactly_as_the_http_path_would(self):
        out = self.call(sqs_event(checkout()))
        self.assertEqual(out, {"processed": 1})
        kw = self.p["create_user_record"].call_args.kwargs
        self.assertEqual((kw["phone_number"], kw["subscription_tier"]), ("+14155550123", "personal_shield"))

    def test_consumer_works_with_the_flag_off_so_a_rollback_drains_the_queue(self):
        os.environ.pop("STRIPE_EVENT_QUEUE_URL", None)
        self.assertEqual(self.call(sqs_event(checkout())), {"processed": 1})

    def test_consumer_does_not_apply_the_signature_age_limit(self):
        # The message can wait in the queue far longer than Stripe's 5-minute tolerance.
        self.assertEqual(self.call(sqs_event(checkout())), {"processed": 1})

    def test_a_processing_failure_raises_so_sqs_retries_and_redrives(self):
        self.p["create_user_record"].side_effect = RuntimeError("ddb down")
        with self.assertRaises(RuntimeError):
            self.call(sqs_event(checkout()))

    def test_an_unparsable_message_raises_rather_than_being_deleted(self):
        ev = sqs_event(checkout())
        ev["Records"][0]["body"] = "not json"
        with self.assertRaises(Exception):
            self.call(ev)

    def test_a_message_missing_its_event_raises(self):
        ev = sqs_event(checkout())
        ev["Records"][0]["body"] = json.dumps({"v": 1})
        with self.assertRaises(Exception):
            self.call(ev)

    def test_records_from_any_other_queue_are_refused(self):
        with self.assertRaises(ValueError):
            self.call(sqs_event(checkout(), arn="arn:aws:sqs:us-east-1:239677749008:some-other-queue"))
        self.p["create_user_record"].assert_not_called()

    def test_records_from_any_other_event_source_are_refused(self):
        with self.assertRaises(ValueError):
            self.call(sqs_event(checkout(), source="aws:sns"))
        self.p["create_user_record"].assert_not_called()

    def test_one_failing_record_fails_the_batch_so_nothing_is_silently_dropped(self):
        ev = sqs_event(checkout(event_id="evt_1"))
        ev["Records"].append(sqs_event(checkout(event_id="evt_2"), message_id="m2")["Records"][0])
        self.p["create_user_record"].side_effect = [RuntimeError("boom"), "user-2"]
        with self.assertRaises(RuntimeError):
            self.call(ev)

    def test_a_ti_checkout_in_the_queue_is_skipped_like_the_http_path(self):
        self.p["get_price_id_from_subscription"].return_value = next(iter(sw.TI_PRICE_IDS))
        self.assertEqual(self.call(sqs_event(checkout())), {"processed": 1})
        self.p["create_user_record"].assert_not_called()

    def test_a_request_body_cannot_pose_as_an_sqs_event(self):
        # API Gateway fixes the top-level keys of the Lambda event; a caller controls only "body".
        forged = {"body": json.dumps(sqs_event(checkout())), "headers": {}}
        self.assertEqual(self.code(forged), 400)
        self.p["create_user_record"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
