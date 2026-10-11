"""The two controls between a caller and a per-call Twilio bill.

1. The FREE TIER must not reach Twilio-backed endpoints. A free key is minted
   from an email address alone and carries 100 calls, so any cap at or above 100
   per key can never fire against it. This is what 1,407 unexplained lookups
   ($19.79, 2026-10-03 to 10-10) point at.
2. A per-key HOURLY cap bounds what a paid or subscribed key can spend.

PR #49 shipped control 2 with no test at all. Every request here goes through
lambda_handler, because the dispatcher is where this repo's runtime-dead defects
have lived and a handler-level test cannot see them.
"""
import json
import pathlib
import sys
import types
import unittest
import unittest.mock as mock

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import test_muse_connector_features  # noqa: F401,E402  (installs the boto3 stubs)
import relayshield_api as api  # noqa: E402

PHONE = "/v1/metered/phone-reputation"
SIMSWAP = "/v1/metered/sim-swap"


class FakeDynamo:
    """Counts usage_key increments like the real atomic ADD; accepts other writes."""
    def __init__(self, fail=False):
        self.counts, self.fail = {}, fail

    def Table(self, name):
        outer = self

        class T:
            def update_item(self, **kw):
                if outer.fail:
                    raise RuntimeError("dynamodb down")
                uk = (kw.get("Key") or {}).get("usage_key")
                if uk is None:
                    return {}
                outer.counts[uk] = outer.counts.get(uk, 0) + 1
                return {"Attributes": {"call_count": outer.counts[uk]}}
        return T()


FREE = {"api_key": "rs_live_free", "active": True, "plan": "free", "source": "direct",
        "free_calls_remaining": 100}
PAID = {"api_key": "rs_live_paid", "active": True, "credit_balance": 10_000_000,
        "source": "direct"}


def call(path, record, ddb=None):
    ev = {"path": path, "httpMethod": "POST", "body": "{}",
          "headers": {"X-RS-API-KEY": record["api_key"]},
          "requestContext": {"identity": {"sourceIp": "9.9.9.9"}}}
    r = api.lambda_handler(ev, None)
    return r, json.loads(r["body"])


class Base(unittest.TestCase):
    def setUp(self):
        self.ddb = FakeDynamo()
        self.reached = []
        for target, name in ((api, "dynamodb"),):
            p = mock.patch.object(target, name, self.ddb)
            p.start(); self.addCleanup(p.stop)

        def fake(name):
            def h(params, *a, **k):
                self.reached.append(name)
                return api._ok({"stub": name})
            return h
        for name in ("handle_phone_reputation", "handle_sim_swap", "handle_breach"):
            p = mock.patch.object(api, name, fake(name)); p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(api, "_record_stripe_meter_event", lambda *a, **k: None)
        p.start(); self.addCleanup(p.stop)
        self.rec = {}
        p = mock.patch.object(api, "_verify_rs_api_key", lambda k: self.rec or None)
        p.start(); self.addCleanup(p.stop)


class FreeTier(Base):
    def test_free_key_cannot_reach_twilio_phone_reputation(self):
        self.rec = dict(FREE)
        r, b = call(PHONE, self.rec)
        self.assertEqual(r["statusCode"], 402)
        self.assertNotIn("handle_phone_reputation", self.reached)

    def test_free_key_cannot_reach_twilio_sim_swap(self):
        self.rec = dict(FREE)
        r, _ = call(SIMSWAP, self.rec)
        self.assertEqual(r["statusCode"], 402)
        self.assertNotIn("handle_sim_swap", self.reached)

    def test_the_refusal_does_not_say_free_calls_are_used_up(self):
        self.rec = dict(FREE)
        _, b = call(PHONE, self.rec)
        self.assertNotIn("used up", b["error"])
        self.assertIn("not included in the free tier", b["error"])

    def test_a_free_key_with_no_calls_left_still_gets_the_used_up_message(self):
        self.rec = dict(FREE, free_calls_remaining=0)
        _, b = call("/v1/metered/breach", self.rec)
        self.assertIn("used up", b["error"])

    def test_free_tier_still_works_for_a_free_endpoint(self):
        self.rec = dict(FREE)
        r, _ = call("/v1/metered/breach", self.rec)
        self.assertEqual(r["statusCode"], 200)
        self.assertIn("handle_breach", self.reached)

    def test_the_exclusion_set_is_what_we_think_it_is(self):
        self.assertTrue({PHONE, SIMSWAP, "/v1/metered/bulk-identity-risk"} <= api.FREE_TIER_EXCLUDED_ENDPOINTS)


class HourlyCap(Base):
    def test_paid_key_is_served_up_to_the_cap_then_429(self):
        self.rec = dict(PAID)
        cap = api.PHONE_REP_KEY_HOURLY_CAP
        for _ in range(cap):
            r, _b = call(PHONE, self.rec)
            self.assertEqual(r["statusCode"], 200)
        r, b = call(PHONE, self.rec)
        self.assertEqual(r["statusCode"], 429)
        self.assertEqual(r["headers"]["Retry-After"], "3600")
        self.assertEqual(r["headers"]["Access-Control-Allow-Origin"], "*")
        self.assertEqual(self.reached.count("handle_phone_reputation"), cap)

    def test_the_cap_is_50(self):
        self.assertEqual(api.PHONE_REP_KEY_HOURLY_CAP, 50)

    def test_the_cap_is_per_key(self):
        self.rec = dict(PAID)
        for _ in range(api.PHONE_REP_KEY_HOURLY_CAP + 1):
            call(PHONE, self.rec)
        self.rec = dict(PAID, api_key="rs_live_other")
        r, _ = call(PHONE, self.rec)
        self.assertEqual(r["statusCode"], 200)

    def test_the_counter_is_not_charged_for_other_endpoints(self):
        self.rec = dict(PAID)
        for _ in range(5):
            call("/v1/metered/breach", self.rec)
        self.assertFalse([k for k in self.ddb.counts if k.startswith("phonerep#")])

    def test_dynamodb_failure_fails_open(self):
        self.rec = dict(PAID)
        self.ddb.fail = True
        r, _ = call(PHONE, self.rec)
        self.assertEqual(r["statusCode"], 200)

    def test_the_window_rolls_over_each_hour(self):
        self.rec = dict(PAID)
        for _ in range(api.PHONE_REP_KEY_HOURLY_CAP + 1):
            call(PHONE, self.rec)
        keys = [k for k in self.ddb.counts if k.startswith("phonerep#key#")]
        self.assertTrue(all(len(k.rsplit("#", 1)[-1]) == len("2026-10-11T00") for k in keys))


if __name__ == "__main__":
    unittest.main()
