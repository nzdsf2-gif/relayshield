"""Offline tests for the MPP settlement endpoint. No AWS, no network, no boto3.

    python3 test_mpp_settlement.py

boto3 is stubbed before the import because the build container has none, and
because every assertion here is about wire shapes and arithmetic rather than
about AWS. The two things being pinned:

  1. The money arithmetic. USDC carries 6 decimals and Stripe wants an integer
     minor unit, and a conversion that is wrong by a factor of ten is invisible
     until it appears in someone's ledger.
  2. The endpoint never quietly claims the Stripe rail. Reporting `rail:
     "stripe"` for a payment that landed in the Coinbase wallet would make the
     whole reason for this endpoint unverifiable.
"""

import base64
import json
import sys
import types
import unittest


# --- stub boto3 before importing the handler -------------------------------
class _StubTable:
    def __init__(self):
        self.items = []

    def put_item(self, Item):
        self.items.append(Item)


class _StubResource:
    def __init__(self):
        self.table = _StubTable()

    def Table(self, name):
        return self.table


_stub = types.ModuleType("boto3")
_stub.resource = lambda *a, **k: _StubResource()
_stub.client = lambda *a, **k: object()
sys.modules.setdefault("boto3", _stub)

import relayshield_mpp_settlement as mpp  # noqa: E402


LIVE_WALLET   = "0xa26054A4188e6D5c31A4DcdFcA27b0FfE247228d"
STRIPE_ADDR   = "0x000000000000000000000000000000000000dEaD"


class ConversionTests(unittest.TestCase):
    """USDC atomic units (6 decimals) -> Stripe minor units (2 decimals)."""

    def test_the_live_price_converts_exactly(self):
        self.assertEqual(mpp.usdc_units_to_cents(350000), 35)

    def test_one_dollar(self):
        self.assertEqual(mpp.usdc_units_to_cents(1_000_000), 100)

    def test_zero_and_negative_are_zero_not_an_exception(self):
        self.assertEqual(mpp.usdc_units_to_cents(0), 0)
        self.assertEqual(mpp.usdc_units_to_cents(-1), 0)

    def test_a_sub_cent_amount_is_not_inflated_to_a_cent(self):
        # 4000 units is $0.004. Rounding that up to a cent would put a number
        # into Stripe's reporting that never moved, so it stays 0 and the
        # handler flags the row instead.
        self.assertEqual(mpp.usdc_units_to_cents(4000), 0)

    def test_half_a_cent_rounds_up(self):
        self.assertEqual(mpp.usdc_units_to_cents(5000), 1)

    def test_it_is_not_off_by_a_factor_of_ten(self):
        # The failure this whole test class exists for.
        self.assertNotEqual(mpp.usdc_units_to_cents(350000), 350)
        self.assertNotEqual(mpp.usdc_units_to_cents(350000), 3)


class PaymentRequirementsTests(unittest.TestCase):

    def test_payto_is_whatever_the_rail_supplied(self):
        req = mpp.build_payment_requirements(STRIPE_ADDR)
        self.assertEqual(req["accepts"][0]["payTo"], STRIPE_ADDR)

    def test_shape_matches_the_live_endpoints(self):
        req = mpp.build_payment_requirements(LIVE_WALLET)
        self.assertEqual(req["x402Version"], 2)
        entry = req["accepts"][0]
        self.assertEqual(entry["scheme"], "exact")
        self.assertEqual(entry["network"], "eip155:8453")
        self.assertEqual(entry["asset"], mpp.USDC_BASE_ADDRESS)
        # Amount is a STRING of atomic units in x402 v2, not a number and not
        # dollars. A float here silently changes the price.
        self.assertEqual(entry["amount"], "350000")
        self.assertIsInstance(entry["amount"], str)

    def test_resource_is_the_structured_object_v2_requires(self):
        res = mpp.build_payment_requirements(LIVE_WALLET)["resource"]
        self.assertEqual(set(res), {"url", "description", "mimeType"})
        self.assertTrue(res["url"].endswith(mpp.MPP_PATH))

    def test_requirements_are_json_serialisable(self):
        json.dumps(mpp.build_payment_requirements(LIVE_WALLET))


class MppChallengeTests(unittest.TestCase):

    def test_it_does_not_claim_a_verified_spec_version(self):
        # The MPP specification is not reachable from the build container. This
        # block must say so rather than assert a version it has not read.
        self.assertEqual(mpp.build_mpp_challenge(LIVE_WALLET)["version"], "unverified")

    def test_it_points_at_the_x402_block_as_authoritative(self):
        self.assertIn("x402", mpp.build_mpp_challenge(LIVE_WALLET)["note"])

    def test_it_carries_the_same_payto_and_amount_as_x402(self):
        # Two blocks quoting different prices in one 402 is worse than one block.
        ch  = mpp.build_mpp_challenge(STRIPE_ADDR)
        req = mpp.build_payment_requirements(STRIPE_ADDR)
        self.assertEqual(ch["payTo"], req["accepts"][0]["payTo"])
        self.assertEqual(ch["amount"]["value"], req["accepts"][0]["amount"])
        self.assertEqual(ch["amount"]["decimals"], 6)


class StripeParamsTests(unittest.TestCase):

    def test_payment_intent_carries_the_network_and_hash(self):
        p = mpp.stripe_payment_intent_params(35, "base", "0xabc")
        self.assertEqual(p["amount"], 35)
        self.assertEqual(p["currency"], "usd")
        self.assertEqual(
            p["payment_method_options[crypto][transaction_verification][network]"], "base")
        self.assertEqual(
            p["payment_method_options[crypto][transaction_verification][transaction_hash]"],
            "0xabc")
        self.assertEqual(p["payment_method_data[type]"], "crypto")

    def test_metadata_is_flattened_and_stringified(self):
        p = mpp.stripe_payment_intent_params(35, "base", "0xabc",
                                             metadata={"usdc_units": 350000})
        self.assertEqual(p["metadata[usdc_units]"], "350000")

    def test_every_value_survives_form_encoding(self):
        import urllib.parse
        p = mpp.stripe_payment_intent_params(35, "base", "0xabc",
                                             metadata={"path": mpp.MPP_PATH})
        urllib.parse.urlencode(p, doseq=True)

    def test_deposit_address_asks_for_base(self):
        self.assertEqual(mpp.stripe_deposit_address_params()["network"], "base")


class RailSelectionTests(unittest.TestCase):
    """The endpoint must never report a rail it did not use."""

    def setUp(self):
        self._rail   = mpp.MPP_RAIL
        self._wallet = mpp.X402_PAYTO_ADDRESS
        self._addr   = mpp._stripe_deposit_address
        self._key    = mpp._stripe_secret_key
        mpp.X402_PAYTO_ADDRESS = LIVE_WALLET
        mpp._deposit_cache.clear()

    def tearDown(self):
        mpp.MPP_RAIL              = self._rail
        mpp.X402_PAYTO_ADDRESS    = self._wallet
        mpp._stripe_deposit_address = self._addr
        mpp._stripe_secret_key    = self._key
        mpp._deposit_cache.clear()

    def test_pinned_to_facilitator_never_touches_stripe(self):
        called = []
        mpp._stripe_secret_key = lambda: called.append("key") or "sk_test_x"
        mpp._stripe_deposit_address = lambda *a, **k: called.append("stripe")
        mpp.MPP_RAIL = "facilitator"
        rail, pay_to, _ = mpp._rail_and_payto()
        self.assertEqual(rail, "facilitator")
        self.assertEqual(pay_to, LIVE_WALLET)
        self.assertEqual(called, [], "the pinned rail must not call Stripe at all")

    def test_auto_falls_back_to_the_live_wallet_when_stripe_is_not_enabled(self):
        mpp.MPP_RAIL = "auto"
        mpp._stripe_secret_key      = lambda: "sk_test_x"
        mpp._stripe_deposit_address = lambda *a, **k: None    # the answer today
        rail, pay_to, reason = mpp._rail_and_payto()
        self.assertEqual(rail, "facilitator")
        self.assertEqual(pay_to, LIVE_WALLET)
        self.assertIn("stripe not enabled", reason)

    def test_auto_uses_stripe_when_a_deposit_address_comes_back(self):
        mpp.MPP_RAIL = "auto"
        mpp._stripe_secret_key      = lambda: "sk_test_x"
        mpp._stripe_deposit_address = lambda *a, **k: {
            "address": STRIPE_ADDR, "id": "cda_1", "network": "base"}
        rail, pay_to, _ = mpp._rail_and_payto()
        self.assertEqual(rail, "stripe")
        self.assertEqual(pay_to, STRIPE_ADDR)

    def test_a_raising_stripe_call_degrades_rather_than_propagating(self):
        mpp.MPP_RAIL = "auto"

        def boom():
            raise RuntimeError("secrets manager is down")

        mpp._stripe_secret_key = boom
        rail, pay_to, _ = mpp._rail_and_payto()
        self.assertEqual(rail, "facilitator")
        self.assertEqual(pay_to, LIVE_WALLET)

    def test_pinned_to_stripe_refuses_rather_than_quietly_using_the_wallet(self):
        mpp.MPP_RAIL = "stripe"
        mpp._stripe_secret_key      = lambda: "sk_test_x"
        mpp._stripe_deposit_address = lambda *a, **k: None
        rail, pay_to, _ = mpp._rail_and_payto()
        self.assertEqual(rail, "stripe")
        self.assertEqual(pay_to, "")


class HandlerTests(unittest.TestCase):

    def setUp(self):
        self._rail   = mpp.MPP_RAIL
        self._wallet = mpp.X402_PAYTO_ADDRESS
        mpp.MPP_RAIL = "facilitator"
        mpp.X402_PAYTO_ADDRESS = LIVE_WALLET

    def tearDown(self):
        mpp.MPP_RAIL           = self._rail
        mpp.X402_PAYTO_ADDRESS = self._wallet

    def test_the_deployer_import_probe_gets_a_real_response(self):
        # deploy_lambdas.yml invokes every function it deploys with this exact
        # payload. It must return, not raise: a raise reads as a broken deploy.
        resp = mpp.lambda_handler({"source": "ci.import-probe"}, None)
        self.assertEqual(resp["statusCode"], 404)
        self.assertFalse(json.loads(resp["body"])["ok"])

    def test_descriptor(self):
        resp = mpp.lambda_handler({"path": "/v1/mpp", "httpMethod": "GET"}, None)
        self.assertEqual(resp["statusCode"], 200)
        data = json.loads(resp["body"])["data"]
        self.assertEqual(data["endpoint"], mpp.MPP_PATH)
        self.assertEqual(data["price"], "$0.35 USDC")

    def test_get_on_the_paid_path_is_405_not_a_free_call(self):
        resp = mpp.lambda_handler({"path": mpp.MPP_PATH, "httpMethod": "GET"}, None)
        self.assertEqual(resp["statusCode"], 405)

    def test_no_payment_header_yields_402_with_a_decodable_challenge(self):
        resp = mpp.lambda_handler(
            {"path": mpp.MPP_PATH, "httpMethod": "POST", "headers": {}}, None)
        self.assertEqual(resp["statusCode"], 402)

        header = json.loads(base64.b64decode(resp["headers"]["PAYMENT-REQUIRED"]))
        body   = json.loads(resp["body"])
        self.assertEqual(header, body["x402"],
                         "the header and the body must quote the same price")
        self.assertEqual(body["rail"], "facilitator")
        self.assertEqual(body["price"], "$0.35 USDC (Base)")
        self.assertIn("mpp", body)

    def test_no_usable_payto_is_503_not_a_free_call(self):
        mpp.X402_PAYTO_ADDRESS = ""
        resp = mpp.lambda_handler(
            {"path": mpp.MPP_PATH, "httpMethod": "POST", "headers": {}}, None)
        self.assertEqual(resp["statusCode"], 503)

    def test_payment_header_is_read_case_insensitively(self):
        # urllib capitalises header names, so "PAYMENT-SIGNATURE" arrives as
        # "Payment-signature". Matching exactly cost every urllib caller a 401.
        for spelling in ("PAYMENT-SIGNATURE", "Payment-signature", "x-payment"):
            self.assertEqual(mpp._header({spelling: "abc"}, "PAYMENT-SIGNATURE") or
                             mpp._header({spelling: "abc"}, "X-PAYMENT"), "abc")


class SettlementRowTests(unittest.TestCase):

    def test_a_failed_stripe_record_is_written_as_a_flagged_row(self):
        table = _StubTable()
        real  = mpp.dynamodb
        mpp.dynamodb = types.SimpleNamespace(Table=lambda name: table)
        try:
            mpp._log_settlement("stripe", {"transaction": "0xdead", "payer": "0xpayer"},
                                35, "", "stripe_record_failed")
        finally:
            mpp.dynamodb = real
        row = table.items[0]
        self.assertEqual(row["rail"], "stripe")
        self.assertEqual(row["payment_intent"], "")
        self.assertEqual(row["note"], "stripe_record_failed")
        self.assertEqual(row["amount_cents"], 35)
        self.assertEqual(row["tx_hash"], "0xdead")

    def test_logging_never_raises(self):
        real = mpp.dynamodb

        class Boom:
            def Table(self, name):
                raise RuntimeError("table gone")

        mpp.dynamodb = Boom()
        try:
            mpp._log_settlement("stripe", {}, 35, "pi_1")   # must not raise
        finally:
            mpp.dynamodb = real


if __name__ == "__main__":
    unittest.main(verbosity=2)
