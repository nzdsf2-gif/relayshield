#!/usr/bin/env python3
"""Unit tests for scam-kit Stripe billing (relayshield_scamkit_billing).

Everything exercised here is pure (tier/price mapping, checkout params,
webhook signature verification, event dispatch, meter-event payloads) or
uses an injected fake DynamoDB table — no network, no AWS, no Stripe.

Run:  python3 test_scamkit_billing.py
"""

import hashlib
import hmac
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import relayshield_scamkit_billing as b


class FakeTable:
    def __init__(self):
        self.items = {}
        self.updates = []

    def update_item(self, Key=None, UpdateExpression=None,
                    ExpressionAttributeValues=None):
        self.updates.append((Key, UpdateExpression, ExpressionAttributeValues))
        key = Key["api_key"]
        item = self.items.setdefault(key, {"api_key": key})
        vals = ExpressionAttributeValues or {}
        expr = UpdateExpression or ""
        if expr.startswith("SET"):
            for assign in expr[3:].split(","):
                field, _, placeholder = assign.partition("=")
                item[field.strip()] = vals[placeholder.strip()]
        elif expr.startswith("REMOVE"):
            for field in expr[len("REMOVE"):].split(","):
                item.pop(field.strip(), None)
        return {}


class TestCheckoutLineItems(unittest.TestCase):
    def test_monthly_has_base_qty1_and_metered_overage_without_quantity(self):
        items = b.checkout_line_items("monthly")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["price"], b.PRICE_MONTHLY_BASE)
        self.assertEqual(items[0]["quantity"], 1)
        self.assertEqual(items[1]["price"], b.PRICE_MONTHLY_OVERAGE)
        self.assertNotIn("quantity", items[1])  # metered: Stripe rejects quantity

    def test_payg_has_three_metered_prices_no_quantities(self):
        items = b.checkout_line_items("payg")
        self.assertEqual(
            [i["price"] for i in items],
            [b.PRICE_PAYG_FINGERPRINT, b.PRICE_PAYG_MATCH, b.PRICE_PAYG_CAMPAIGN],
        )
        for item in items:
            self.assertNotIn("quantity", item)

    def test_unknown_tier_raises(self):
        with self.assertRaises(ValueError):
            b.checkout_line_items("enterprise")


class TestCheckoutSessionParams(unittest.TestCase):
    def test_monthly_params(self):
        p = b.build_checkout_session_params("monthly", "rs_live_abc123")
        self.assertEqual(p["mode"], "subscription")
        self.assertEqual(p["client_reference_id"], "rs_live_abc123")
        self.assertEqual(p["line_items[0][price]"], b.PRICE_MONTHLY_BASE)
        self.assertEqual(p["line_items[0][quantity]"], "1")
        self.assertEqual(p["line_items[1][price]"], b.PRICE_MONTHLY_OVERAGE)
        self.assertNotIn("line_items[1][quantity]", p)
        self.assertEqual(p["metadata[tier]"], "monthly")
        self.assertEqual(p["subscription_data[metadata][api_key]"], "rs_live_abc123")
        self.assertEqual(p["subscription_data[metadata][tier]"], "monthly")

    def test_payg_params(self):
        p = b.build_checkout_session_params("payg", "rs_live_xyz")
        self.assertEqual(p["line_items[0][price]"], b.PRICE_PAYG_FINGERPRINT)
        self.assertEqual(p["line_items[1][price]"], b.PRICE_PAYG_MATCH)
        self.assertEqual(p["line_items[2][price]"], b.PRICE_PAYG_CAMPAIGN)
        self.assertNotIn("line_items[3][price]", p)

    def test_custom_urls(self):
        p = b.build_checkout_session_params(
            "payg", "rs_live_xyz",
            success_url="https://example.com/ok", cancel_url="https://example.com/no")
        self.assertEqual(p["success_url"], "https://example.com/ok")
        self.assertEqual(p["cancel_url"], "https://example.com/no")

    def test_bad_tier_raises(self):
        with self.assertRaises(ValueError):
            b.build_checkout_session_params("free", "rs_live_abc123")

    def test_client_reference_id_length_guarded(self):
        with self.assertRaises(ValueError):
            b.build_checkout_session_params("monthly", "x" * 201)


class TestWebhookSignature(unittest.TestCase):
    SECRET = "whsec_test_secret"

    def _sig(self, payload: bytes, ts: int):
        sig = hmac.new(self.SECRET.encode(), f"{ts}.{payload.decode()}".encode(),
                       hashlib.sha256).hexdigest()
        return f"t={ts},v1={sig}"

    def test_valid_signature(self):
        payload = b'{"type":"checkout.session.completed"}'
        ts = int(time.time())
        self.assertTrue(b.verify_stripe_signature(payload, self._sig(payload, ts), self.SECRET))

    def test_tampered_payload_fails(self):
        payload = b'{"type":"checkout.session.completed"}'
        ts = int(time.time())
        self.assertFalse(b.verify_stripe_signature(b'{"type":"other"}', self._sig(payload, ts), self.SECRET))

    def test_wrong_secret_fails(self):
        payload = b'{"a":1}'
        ts = int(time.time())
        self.assertFalse(b.verify_stripe_signature(payload, self._sig(payload, ts), "wrong"))

    def test_expired_timestamp_fails(self):
        payload = b'{"a":1}'
        ts = int(time.time()) - 600
        self.assertFalse(b.verify_stripe_signature(payload, self._sig(payload, ts), self.SECRET))

    def test_missing_header_fails(self):
        self.assertFalse(b.verify_stripe_signature(b'{"a":1}', "", self.SECRET))

    def test_multiple_v1_signatures_any_match(self):
        payload = b'{"a":1}'
        ts = int(time.time())
        good = self._sig(payload, ts).split("v1=")[1]
        header = f"t={ts},v1=deadbeef,v1={good}"
        self.assertTrue(b.verify_stripe_signature(payload, header, self.SECRET))


class TestEventDispatch(unittest.TestCase):
    def test_checkout_completed_activates(self):
        event = {"type": "checkout.session.completed", "data": {"object": {
            "client_reference_id": "rs_live_abc",
            "customer": "cus_123",
            "subscription": "sub_456",
            "metadata": {"tier": "monthly"},
        }}}
        action, payload = b.dispatch_billing_event(event)
        self.assertEqual(action, "activate")
        self.assertEqual(payload, {
            "api_key": "rs_live_abc",
            "stripe_customer_id": "cus_123",
            "stripe_subscription_id": "sub_456",
            "scamkit_tier": "monthly",
        })

    def test_checkout_completed_without_our_metadata_ignored(self):
        event = {"type": "checkout.session.completed", "data": {"object": {
            "client_reference_id": "",
            "customer": "cus_123",
            "metadata": {},
        }}}
        self.assertEqual(b.dispatch_billing_event(event), ("ignore", None))

    def test_subscription_deleted_deactivates(self):
        event = {"type": "customer.subscription.deleted", "data": {"object": {
            "metadata": {"api_key": "rs_live_abc"},
        }}}
        self.assertEqual(b.dispatch_billing_event(event), ("deactivate", "rs_live_abc"))

    def test_subscription_deleted_without_api_key_ignored(self):
        event = {"type": "customer.subscription.deleted", "data": {"object": {
            "metadata": {},
        }}}
        self.assertEqual(b.dispatch_billing_event(event), ("ignore", None))

    def test_unrelated_event_ignored(self):
        self.assertEqual(
            b.dispatch_billing_event({"type": "invoice.paid", "data": {"object": {}}}),
            ("ignore", None))


class TestPersistence(unittest.TestCase):
    def test_store_mapping_sets_tier_fields(self):
        table = FakeTable()
        b.store_subscription_mapping(table, {
            "api_key": "rs_live_abc",
            "stripe_customer_id": "cus_123",
            "stripe_subscription_id": "sub_456",
            "scamkit_tier": "payg",
        })
        item = table.items["rs_live_abc"]
        self.assertEqual(item["stripe_customer_id"], "cus_123")
        self.assertEqual(item["stripe_subscription_id"], "sub_456")
        self.assertEqual(item["scamkit_tier"], "payg")
        self.assertIn("scamkit_subscribed_at", item)

    def test_clear_tier_removes_tier_but_keeps_customer(self):
        table = FakeTable()
        table.items["rs_live_abc"] = {
            "api_key": "rs_live_abc",
            "stripe_customer_id": "cus_123",
            "stripe_subscription_id": "sub_456",
            "scamkit_tier": "monthly",
        }
        b.clear_subscription_tier(table, "rs_live_abc")
        item = table.items["rs_live_abc"]
        self.assertNotIn("scamkit_tier", item)
        self.assertNotIn("stripe_subscription_id", item)
        self.assertEqual(item["stripe_customer_id"], "cus_123")  # kept for history


class TestMeterEvents(unittest.TestCase):
    def test_monthly_always_reports_monthly_execution(self):
        for path in ("/v1/metered/scamkit-fingerprint",
                     "/v1/metered/scamkit-match",
                     "/v1/metered/scamkit-campaign-scan"):
            self.assertEqual(b.scamkit_meter_event_for("monthly", path),
                             b.EVENT_MONTHLY_EXECUTION)

    def test_payg_reports_per_endpoint_events(self):
        self.assertEqual(b.scamkit_meter_event_for("payg", "/v1/metered/scamkit-fingerprint"),
                         b.EVENT_PAYG_FINGERPRINT)
        self.assertEqual(b.scamkit_meter_event_for("payg", "/v1/metered/scamkit-match"),
                         b.EVENT_PAYG_MATCH)
        self.assertEqual(b.scamkit_meter_event_for("payg", "/v1/metered/scamkit-campaign-scan"),
                         b.EVENT_PAYG_CAMPAIGN)

    def test_unknown_path_returns_none(self):
        self.assertIsNone(b.scamkit_meter_event_for("payg", "/v1/metered/breach"))
        self.assertIsNone(b.scamkit_meter_event_for("monthly", "/v1/payg/scamkit-fingerprint"))

    def test_unknown_tier_returns_none(self):
        self.assertIsNone(b.scamkit_meter_event_for("free", "/v1/metered/scamkit-match"))

    def test_payload_shape(self):
        p = b.build_meter_event_payload("cus_123", b.EVENT_PAYG_MATCH)
        self.assertEqual(p["event_name"], b.EVENT_PAYG_MATCH)
        self.assertEqual(p["payload[stripe_customer_id]"], "cus_123")
        self.assertEqual(p["payload[value]"], "1")  # count aggregation: always 1
        self.assertTrue(p["identifier"].startswith("cus_123-"))

    def test_identifiers_unique(self):
        a = b.build_meter_event_payload("cus_123", b.EVENT_PAYG_MATCH)["identifier"]
        c = b.build_meter_event_payload("cus_123", b.EVENT_PAYG_MATCH)["identifier"]
        self.assertNotEqual(a, c)

    def test_report_skips_missing_customer(self):
        # Must not raise and must not attempt network with no customer.
        b.report_scamkit_meter_event("sk_test", "", b.EVENT_PAYG_MATCH)
        b.report_scamkit_meter_event("sk_test", "cus_123", "")


class TestRawBody(unittest.TestCase):
    def test_plain_body(self):
        self.assertEqual(b.raw_body_bytes({"body": "hello"}), b"hello")

    def test_base64_body_decoded(self):
        import base64
        raw = b'{"type":"x"}'
        event = {"body": base64.b64encode(raw).decode(), "isBase64Encoded": True}
        self.assertEqual(b.raw_body_bytes(event), raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
