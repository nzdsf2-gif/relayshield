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
    """The PaymentIntent shape, verified against mppx 0.9.2
    (dist/stripe/server/internal/record-payment.js). Every assertion here is a
    key that was WRONG when this shape was derived from prose instead."""

    def setUp(self):
        self.p = mpp.stripe_payment_intent_params(35, "base", "0xabc")

    def test_mode_is_its_own_key(self):
        # Was missing entirely in the derived version.
        self.assertEqual(self.p["payment_method_options[crypto][mode]"],
                         "transaction_verification")

    def test_the_sub_object_is_transaction_verification_OPTIONS(self):
        # The derived version wrote [transaction_verification][...], which is a
        # different key and would have been rejected outright.
        self.assertEqual(
            self.p["payment_method_options[crypto][transaction_verification_options][network]"],
            "base")
        self.assertEqual(
            self.p["payment_method_options[crypto][transaction_verification_options][transaction_hash]"],
            "0xabc")
        self.assertNotIn(
            "payment_method_options[crypto][transaction_verification][network]", self.p)

    def test_payment_method_types_is_present_and_a_list(self):
        # Also missing from the derived version.
        self.assertEqual(self.p["payment_method_types[]"], ["crypto"])
        self.assertEqual(self.p["payment_method_data[type]"], "crypto")

    def test_it_is_tagged_as_a_machine_payment(self):
        # How machine revenue is queried on the Stripe side.
        self.assertEqual(self.p["metadata[machine_payment]"], "true")

    def test_amount_and_currency(self):
        self.assertEqual(self.p["amount"], 35)
        self.assertEqual(self.p["currency"], "usd")
        self.assertEqual(self.p["confirm"], "true")

    def test_caller_metadata_does_not_displace_the_machine_payment_tag(self):
        p = mpp.stripe_payment_intent_params(35, "base", "0xabc",
                                             metadata={"usdc_units": 350000})
        self.assertEqual(p["metadata[usdc_units]"], "350000")
        self.assertEqual(p["metadata[machine_payment]"], "true")

    def test_every_value_survives_form_encoding(self):
        import urllib.parse
        urllib.parse.urlencode(
            mpp.stripe_payment_intent_params(35, "base", "0xabc",
                                             metadata={"path": mpp.MPP_PATH}),
            doseq=True)

    def test_deposit_address_defaults_to_the_configured_network(self):
        self.assertEqual(mpp.stripe_deposit_address_params()["network"], mpp.MPP_NETWORK)
        self.assertEqual(mpp.stripe_deposit_address_params("tempo")["network"], "tempo")

    def test_the_api_version_is_the_one_the_reference_implementation_pins(self):
        self.assertEqual(mpp.STRIPE_PREVIEW_VERSION, "2026-07-29.preview")

    def test_stripe_records_on_base_and_it_is_six_decimals(self):
        self.assertEqual(mpp.STRIPE_NETWORKS["base"], 6)
        self.assertIn(mpp.MPP_NETWORK, mpp.STRIPE_NETWORKS)


class DepositAddressTests(unittest.TestCase):
    """List before create. Creating unconditionally scatters revenue across a
    new address on every Lambda cold start."""

    def setUp(self):
        self._req = mpp._stripe_request
        mpp._deposit_cache.clear()

    def tearDown(self):
        mpp._stripe_request = self._req
        mpp._deposit_cache.clear()

    def _record(self, responses):
        calls = []

        def fake(path, params, key, idempotency_key=""):
            calls.append((path, params))
            return responses.pop(0)

        mpp._stripe_request = fake
        return calls

    def test_an_existing_address_is_reused_and_nothing_is_created(self):
        calls = self._record([(200, {"data": [{"address": "0xdead", "id": "cda_1"}]})])
        got = mpp._stripe_deposit_address("sk_test_x", "base")
        self.assertEqual(got["address"], "0xdead")
        self.assertEqual(len(calls), 1, "a reusable address must not trigger a create")
        self.assertIn("network=base", calls[0][0])
        self.assertIsNone(calls[0][1], "the list call is a GET")

    def test_an_empty_list_creates_one(self):
        calls = self._record([(200, {"data": []}),
                              (200, {"address": "0xnew", "id": "cda_2"})])
        got = mpp._stripe_deposit_address("sk_test_x", "base")
        self.assertEqual(got["address"], "0xnew")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][1], {"network": "base"})

    def test_not_enabled_returns_none_rather_than_raising(self):
        self._record([(403, {"error": {"message": "crypto is not enabled"}})])
        self.assertIsNone(mpp._stripe_deposit_address("sk_test_x", "base"))


class MppChallengeTests(unittest.TestCase):
    """MPP is an HTTP authentication scheme, not a JSON body key. Verified
    against mppx 0.9.2 dist/Challenge.js and the payment-auth-spec draft."""

    REALM  = "api.relayshield.net"
    PROF   = "profile_123"
    SECRET = "s3cret"

    def test_base64url_is_unpadded_and_url_safe(self):
        self.assertEqual(mpp._b64url(b"\xff\xfe\xfd"), "__79")
        self.assertNotIn("=", mpp._b64url(b"abcde"))

    def test_canonical_json_is_sorted_and_tight(self):
        self.assertEqual(mpp._canonical_json({"b": 1, "a": 2}), '{"a":2,"b":1}')

    def test_the_request_puts_networkid_under_methoddetails(self):
        # mppx's zod transform moves it there; a networkId at the top level is
        # the shape BEFORE the transform and is not what goes on the wire.
        r = mpp.mpp_payment_request(350000, self.PROF)
        self.assertEqual(r["amount"], "350000")
        self.assertIsInstance(r["amount"], str)
        self.assertEqual(r["methodDetails"]["networkId"], self.PROF)
        self.assertEqual(r["methodDetails"]["paymentMethodTypes"], ["crypto"])
        self.assertNotIn("networkId", r)

    def test_the_challenge_is_a_www_authenticate_value_not_a_dict(self):
        h = mpp.build_mpp_challenge(self.REALM, self.PROF, self.SECRET)
        self.assertTrue(h.startswith("Payment "))
        for field in ("id=", "realm=", "method=", "intent=", "request="):
            self.assertIn(field, h)
        self.assertIn('method="stripe"', h)
        self.assertIn('intent="charge"', h)

    def test_the_id_is_bound_to_the_amount(self):
        # The property that makes this a challenge rather than a suggestion:
        # change the price and the id must change.
        a = mpp.mpp_challenge_id(self.REALM, "stripe", "charge",
                                 mpp.mpp_payment_request(350000, self.PROF), self.SECRET)
        b = mpp.mpp_challenge_id(self.REALM, "stripe", "charge",
                                 mpp.mpp_payment_request(1, self.PROF), self.SECRET)
        self.assertNotEqual(a, b)

    def test_the_id_is_bound_to_the_realm_and_the_secret(self):
        req = mpp.mpp_payment_request(350000, self.PROF)
        base = mpp.mpp_challenge_id(self.REALM, "stripe", "charge", req, self.SECRET)
        self.assertNotEqual(base, mpp.mpp_challenge_id("evil.example", "stripe", "charge",
                                                       req, self.SECRET))
        self.assertNotEqual(base, mpp.mpp_challenge_id(self.REALM, "stripe", "charge",
                                                       req, "other"))

    def test_the_id_slot_count_is_stable(self):
        # Absent optional fields occupy empty slots, so (expires set, no digest)
        # can never collide with (no expires, digest set).
        req = mpp.mpp_payment_request(350000, self.PROF)
        with_exp = mpp.mpp_challenge_id(self.REALM, "stripe", "charge", req,
                                        self.SECRET, expires="2026-01-01T00:00:00Z")
        with_dig = mpp.mpp_challenge_id(self.REALM, "stripe", "charge", req,
                                        self.SECRET, digest="sha-256=abc")
        self.assertNotEqual(with_exp, with_dig)

    def test_the_default_credential_header_is_not_advertised(self):
        # mppx treats Authorization as the implicit default and omits it, so
        # passing it explicitly must not change the binding.
        req = mpp.mpp_payment_request(350000, self.PROF)
        self.assertEqual(
            mpp.mpp_challenge_id(self.REALM, "stripe", "charge", req, self.SECRET),
            mpp.mpp_challenge_id(self.REALM, "stripe", "charge", req, self.SECRET,
                                 header="Authorization"))

    def test_the_server_secret_is_never_the_raw_api_key(self):
        derived = mpp.mpp_secret_key("sk_test_supersecret")
        self.assertNotIn("sk_test_supersecret", derived)
        self.assertEqual(derived, mpp.mpp_secret_key("sk_test_supersecret"),
                         "must be stable across Lambda instances")

    def test_a_description_above_latin1_cannot_break_the_header(self):
        h = mpp.build_mpp_challenge(self.REALM, self.PROF, self.SECRET,
                                    description="risk check \u2014 MCP registry")
        h.encode("latin-1")   # must not raise
        self.assertNotIn("\n", h)


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
        # MPP is off by default, so no WWW-Authenticate and no mpp block. The
        # x402 challenge must stand entirely on its own.
        self.assertNotIn("WWW-Authenticate", resp["headers"])
        self.assertNotIn("mpp", body)
        self.assertEqual(body["price"], f"$0.35 USDC ({mpp.MPP_NETWORK})")

    def test_when_mpp_is_switched_on_the_challenge_rides_www_authenticate(self):
        real_flag, real_key, real_prof = (mpp.MPP_CHALLENGE_ENABLED,
                                          mpp._stripe_secret_key, mpp._stripe_profile_id)
        mpp.MPP_CHALLENGE_ENABLED = True
        mpp._stripe_secret_key = lambda: "sk_test_x"
        mpp._stripe_profile_id = lambda key: "profile_123"
        try:
            resp = mpp.lambda_handler(
                {"path": mpp.MPP_PATH, "httpMethod": "POST", "headers": {}}, None)
        finally:
            (mpp.MPP_CHALLENGE_ENABLED, mpp._stripe_secret_key,
             mpp._stripe_profile_id) = real_flag, real_key, real_prof
        self.assertEqual(resp["statusCode"], 402)
        self.assertTrue(resp["headers"]["WWW-Authenticate"].startswith("Payment "))
        # and the x402 challenge is still there beside it, untouched
        self.assertIn("PAYMENT-REQUIRED", resp["headers"])

    def test_an_unreachable_stripe_never_costs_us_the_x402_challenge(self):
        real_flag, real_key = mpp.MPP_CHALLENGE_ENABLED, mpp._stripe_secret_key

        def boom():
            raise RuntimeError("secrets manager is down")

        mpp.MPP_CHALLENGE_ENABLED = True
        mpp._stripe_secret_key = boom
        try:
            resp = mpp.lambda_handler(
                {"path": mpp.MPP_PATH, "httpMethod": "POST", "headers": {}}, None)
        finally:
            mpp.MPP_CHALLENGE_ENABLED, mpp._stripe_secret_key = real_flag, real_key
        self.assertEqual(resp["statusCode"], 402)
        self.assertIn("PAYMENT-REQUIRED", resp["headers"])
        self.assertNotIn("WWW-Authenticate", resp["headers"])

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
