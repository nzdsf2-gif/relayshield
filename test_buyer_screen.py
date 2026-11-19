"""Buyer screening: POST /v1/buyer-screen, EXECUTED not grepped.

One POST takes the buyer signals the Shopify webhooks carry (email, IP,
shipping/billing addresses, account age/order history, cart value), fans
out to RelayShield's own TI corpus server-side, and returns a single risk
level + score + per-signal breakdown. Combination rule: RISKIEST SIGNAL
WINS. Score is monotonic in the worst signal (high=90, medium=55,
unknown=15 base, +5 per additional medium/high signal, capped at 100).

Invariants asserted throughout: no verdict ever says "safe"; levels are
only high/medium/unknown; every signal carries reasons; a failing corpus
lookup degrades to unknown instead of killing the screening; the raw
email never appears in the response. Corpus helpers are monkeypatched --
no network, no DynamoDB, no upstreams.

Revamp 2026-11-18 (v2): the BuyerScreenAgent class adds the TAP/PAP
third dimension. When the Worker passes an "agent" block (Poppy-detected
buyer), the Lambda verifies the agent's Passport and intent binding
in-process and folds the verdict in as one more additive signal. A clean
TAP result never clears a corpus flag; a verifier failure fails open
with no agent signal. The 44 v1 tests are unchanged.
"""
import json
import pathlib
import sys
import types
import unittest
import unittest.mock

ROOT = pathlib.Path(__file__).resolve().parent


def _stub_aws():
    boto3 = types.ModuleType("boto3"); boto3.__path__ = []
    boto3.resource = lambda *a, **k: unittest.mock.MagicMock()
    boto3.client = lambda *a, **k: unittest.mock.MagicMock()
    conditions = types.ModuleType("boto3.dynamodb.conditions")
    conditions.Key = lambda *a, **k: unittest.mock.MagicMock()
    conditions.Attr = lambda *a, **k: unittest.mock.MagicMock()
    dynamodb_mod = types.ModuleType("boto3.dynamodb"); dynamodb_mod.__path__ = []
    dynamodb_mod.conditions = conditions
    boto3.dynamodb = dynamodb_mod
    sess = types.ModuleType("boto3.session")
    sys.modules.setdefault("boto3", boto3)
    sys.modules.setdefault("boto3.dynamodb", dynamodb_mod)
    sys.modules.setdefault("boto3.dynamodb.conditions", conditions)
    sys.modules.setdefault("boto3.session", sess)
    bc = types.ModuleType("botocore"); bc.__path__ = []
    ex = types.ModuleType("botocore.exceptions")
    class _CE(Exception):
        pass
    ex.ClientError = _CE; ex.BotoCoreError = _CE; bc.exceptions = ex
    sys.modules.setdefault("botocore", bc)
    sys.modules.setdefault("botocore.exceptions", ex)


_stub_aws()
sys.path.insert(0, str(ROOT))


def _stub_missing_siblings():
    """Stub relayshield_* sibling modules that cannot be found, so the
    buyer-screen tests run on a minimal fixture (VM) as well as the full
    repo (Mac). A module is only stubbed when importlib cannot find it
    at all, so real modules always take precedence. The buyer-screen
    code never touches these siblings; they are only needed because
    relayshield_api.py imports them at module level."""
    import importlib.util
    for name in ("relayshield_agentic_api", "relayshield_breach_monitor",
                 "relayshield_corpus_provenance", "relayshield_intel_labels",
                 "relayshield_intent_binding", "relayshield_openapi_spec",
                 "relayshield_passport", "relayshield_phone_reputation",
                 "relayshield_scamkit", "relayshield_scamkit_fetch",
                 "relayshield_siem_connector", "relayshield_sim_swap_consent",
                 "relayshield_tap_ti", "relayshield_vt_budget"):
        if name not in sys.modules and importlib.util.find_spec(name) is None:
            sys.modules[name] = unittest.mock.MagicMock()


_stub_missing_siblings()
import relayshield_api as api  # noqa: E402


def _body_of(resp):
    return json.loads(resp["body"])


def _data_of(resp):
    body = _body_of(resp)
    assert body["ok"], body
    return body["data"]


def _patch_corpus(ioc=None, stolen=None, breach=None):
    """Monkeypatch the three corpus helpers; defaults are all-clean."""
    patches = [
        unittest.mock.patch.object(
            api, "_buyer_screen_ioc_hits",
            lambda value, types: (ioc or {}).get((value, tuple(types)), [])),
        unittest.mock.patch.object(
            api, "_buyer_screen_stolen_credential_hits",
            lambda email: (stolen or {}).get(email, [])),
        unittest.mock.patch.object(
            api, "_buyer_screen_breach_cache",
            lambda email: (breach or {}).get(email)),
    ]
    # _buyer_screen_signal_email calls _breach_cache_get, not a wrapper.
    patches[2] = unittest.mock.patch.object(
        api, "_breach_cache_get",
        lambda email: (breach or {}).get(email))
    return patches


def _run(params, ioc=None, stolen=None, breach=None):
    patches = _patch_corpus(ioc=ioc, stolen=stolen, breach=breach)
    for p in patches:
        p.start()
    try:
        return api.handle_buyer_screen(params)
    finally:
        for p in patches:
            p.stop()


def _email_params(email="buyer@example.com"):
    return {"email": {"from_address": email}}


class BuyerScreenBasics(unittest.TestCase):
    def test_empty_input_400(self):
        resp = _run({})
        self.assertEqual(resp["statusCode"], 400)
        self.assertIn("buyer signal", _body_of(resp)["error"])

    def test_email_only_ok(self):
        d = _data_of(_run(_email_params()))
        self.assertEqual(d["level"], "unknown")
        self.assertEqual(d["score"], 15)
        self.assertEqual(len(d["signals"]), 1)
        self.assertEqual(d["signals"][0]["type"], "email")

    def test_envelope_shape(self):
        d = _data_of(_run(_email_params()))
        for key in ("level", "score", "signals", "checked_at", "note"):
            self.assertIn(key, d)
        self.assertIn("unknown", d["note"])

    def test_levels_only_high_medium_unknown(self):
        for params in (_email_params(), {"ip": "203.0.113.7"},
                       {"shipping_address": {"zip": "02101", "country": "US"}}):
            d = _data_of(_run(params))
            self.assertIn(d["level"], ("high", "medium", "unknown"))

    def test_no_safe_language(self):
        d = _data_of(_run({
            "email": {"from_address": "buyer@example.com"},
            "ip": "203.0.113.7",
            "shipping_address": {"address1": "1 Main St", "zip": "02101", "country": "US"},
            "billing_address": {"address1": "1 Main St", "zip": "02101", "country": "US"},
            "account": {"orders_count": 5, "verified_email": True},
        }))
        self.assertNotIn("safe", json.dumps(d).lower())

    def test_raw_email_never_returned(self):
        d = _data_of(_run(_email_params("secretbuyer@example.com")))
        self.assertNotIn("secretbuyer@example.com", json.dumps(d))

    def test_malformed_email_skipped(self):
        resp = _run({"email": {"from_address": "not-an-email"},
                     "ip": "203.0.113.7"})
        d = _data_of(resp)
        self.assertEqual([s["type"] for s in d["signals"]], ["ip"])

    def test_email_as_string_treated_as_absent(self):
        resp = _run({"email": "buyer@example.com", "ip": "203.0.113.7"})
        d = _data_of(resp)
        self.assertEqual([s["type"] for s in d["signals"]], ["ip"])

    def test_device_fingerprint_ignored_in_v1(self):
        d = _data_of(_run({**_email_params(),
                           "device_fingerprint": "fp-abc-123"}))
        self.assertEqual([s["type"] for s in d["signals"]], ["email"])

    def test_routes_registered(self):
        self.assertIs(api.ROUTES.get("/v1/buyer-screen"),
                      api.handle_buyer_screen)
        self.assertIn("/v1/buyer-screen", api.KEYLESS_SCAN_ENDPOINTS)


class BuyerScreenEmail(unittest.TestCase):
    def test_ioc_email_hit_high(self):
        d = _data_of(_run(
            _email_params("fraud@example.com"),
            ioc={("fraud@example.com", ("email",)): [{"ioc_value": "fraud@example.com"}]}))
        self.assertEqual(d["level"], "high")
        self.assertEqual(d["score"], 90)
        self.assertIn("fraudster", d["signals"][0]["reasons"][0])

    def test_stealer_credential_hit_high(self):
        d = _data_of(_run(
            _email_params("victim@example.com"),
            stolen={"victim@example.com": [{"domain": "shop.example"}]}))
        self.assertEqual(d["level"], "high")
        self.assertIn("stealer", d["signals"][0]["reasons"][0])

    def test_breach_cache_hit_medium(self):
        d = _data_of(_run(
            _email_params("breached@example.com"),
            breach={"breached@example.com": [{"Name": "SomeBreach"}]}))
        self.assertEqual(d["level"], "medium")
        self.assertEqual(d["score"], 55)
        self.assertIn("breach exposure", d["signals"][0]["reasons"][0])

    def test_breach_cache_empty_list_is_clean(self):
        d = _data_of(_run(
            _email_params("clean@example.com"),
            breach={"clean@example.com": []}))
        self.assertEqual(d["level"], "unknown")

    def test_disposable_domain_medium(self):
        d = _data_of(_run(_email_params("buyer@mailinator.com")))
        self.assertEqual(d["level"], "medium")
        self.assertIn("disposable", d["signals"][0]["reasons"][0])

    def test_email_domain_ioc_hit_medium(self):
        d = _data_of(_run(
            _email_params("buyer@bad-domain.example"),
            ioc={("bad-domain.example", ("domain",)): [{"ioc_value": "bad-domain.example"}]}))
        self.assertEqual(d["level"], "medium")
        self.assertIn("domain flagged", d["signals"][0]["reasons"][0])

    def test_clean_email_unknown(self):
        d = _data_of(_run(_email_params("buyer@example.com")))
        self.assertEqual(d["level"], "unknown")
        self.assertEqual(d["signals"][0]["reasons"], ["no email risk flags"])


class BuyerScreenIp(unittest.TestCase):
    def test_ioc_ip_hit_high(self):
        d = _data_of(_run(
            {"ip": "203.0.113.7"},
            ioc={("203.0.113.7", ("ip",)): [{"ioc_value": "203.0.113.7"}]}))
        self.assertEqual(d["level"], "high")
        self.assertIn("flagged", d["signals"][0]["reasons"][0])

    def test_clean_ip_unknown(self):
        d = _data_of(_run({"ip": "203.0.113.7"}))
        self.assertEqual(d["level"], "unknown")

    def test_private_ip_unknown_with_reason(self):
        for ip in ("10.0.0.5", "192.168.1.1", "127.0.0.1", "172.16.0.9",
                   "172.31.255.1", "169.254.10.20"):
            d = _data_of(_run({"ip": ip}))
            self.assertEqual(d["level"], "unknown", ip)
            self.assertIn("private", d["signals"][0]["reasons"][0], ip)

    def test_public_172_32_is_not_private(self):
        d = _data_of(_run({"ip": "172.32.0.9"}))
        self.assertEqual(d["signals"][0]["reasons"],
                         ["no IP flags in threat intel corpus"])


class BuyerScreenAddress(unittest.TestCase):
    def test_no_address_no_signal(self):
        d = _data_of(_run(_email_params()))
        self.assertEqual([s["type"] for s in d["signals"]], ["email"])

    def test_matching_addresses_unknown(self):
        addr = {"address1": "1 Main St", "city": "Boston",
                "zip": "02101", "country": "US"}
        d = _data_of(_run({**_email_params(),
                           "shipping_address": dict(addr),
                           "billing_address": dict(addr)}))
        sig = [s for s in d["signals"] if s["type"] == "address"][0]
        self.assertEqual(sig["level"], "unknown")

    def test_zip_mismatch_medium(self):
        d = _data_of(_run({
            **_email_params(),
            "shipping_address": {"address1": "1 Main St", "zip": "02101", "country": "US"},
            "billing_address": {"address1": "9 Oak Ave", "zip": "90210", "country": "US"},
        }))
        sig = [s for s in d["signals"] if s["type"] == "address"][0]
        self.assertEqual(sig["level"], "medium")
        self.assertIn("do not match", sig["reasons"][0])

    def test_country_mismatch_medium(self):
        d = _data_of(_run({
            **_email_params(),
            "shipping_address": {"address1": "1 Main St", "zip": "02101", "country": "US"},
            "billing_address": {"address1": "1 Main St", "zip": "02101", "country": "CA"},
        }))
        sig = [s for s in d["signals"] if s["type"] == "address"][0]
        self.assertEqual(sig["level"], "medium")

    def test_country_code_used_when_present(self):
        d = _data_of(_run({
            **_email_params(),
            "shipping_address": {"address1": "1 Main St", "zip": "02101",
                                 "country": "United States", "country_code": "US"},
            "billing_address": {"address1": "1 Main St", "zip": "02101",
                                "country": "United States", "country_code": "US"},
        }))
        sig = [s for s in d["signals"] if s["type"] == "address"][0]
        self.assertEqual(sig["level"], "unknown")

    def test_po_box_medium(self):
        for addr1 in ("PO Box 123", "P.O. Box 45", "P O Box 7"):
            d = _data_of(_run({
                **_email_params(),
                "shipping_address": {"address1": addr1, "zip": "02101", "country": "US"},
            }))
            sig = [s for s in d["signals"] if s["type"] == "address"][0]
            self.assertEqual(sig["level"], "medium", addr1)
            self.assertIn("PO box", sig["reasons"][0], addr1)

    def test_one_sided_address_no_mismatch(self):
        d = _data_of(_run({
            **_email_params(),
            "shipping_address": {"address1": "1 Main St", "zip": "02101", "country": "US"},
        }))
        sig = [s for s in d["signals"] if s["type"] == "address"][0]
        self.assertEqual(sig["level"], "unknown")


class BuyerScreenAccount(unittest.TestCase):
    def test_new_account_zero_orders_medium(self):
        d = _data_of(_run({
            **_email_params(),
            "account": {"orders_count": 0, "verified_email": True},
        }))
        sig = [s for s in d["signals"] if s["type"] == "account"][0]
        self.assertEqual(sig["level"], "medium")
        self.assertIn("new account", sig["reasons"][0])

    def test_new_account_recent_created_medium(self):
        from datetime import datetime, timezone, timedelta
        created = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        d = _data_of(_run({
            **_email_params(),
            "account": {"orders_count": 3, "created_at": created,
                        "verified_email": True},
        }))
        sig = [s for s in d["signals"] if s["type"] == "account"][0]
        self.assertEqual(sig["level"], "medium")

    def test_new_account_high_value_cart(self):
        d = _data_of(_run({
            **_email_params(),
            "account": {"orders_count": 0, "verified_email": True},
            "cart": {"total_price": "149.00", "currency": "USD", "line_items": 2},
        }))
        sig = [s for s in d["signals"] if s["type"] == "account"][0]
        self.assertTrue(any("high-value order" in r for r in sig["reasons"]))

    def test_new_account_unverified_email_reason(self):
        d = _data_of(_run({
            **_email_params(),
            "account": {"orders_count": 0, "verified_email": False},
        }))
        sig = [s for s in d["signals"] if s["type"] == "account"][0]
        self.assertTrue(any("not verified" in r for r in sig["reasons"]))

    def test_old_account_unknown(self):
        from datetime import datetime, timezone, timedelta
        created = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        d = _data_of(_run({
            **_email_params(),
            "account": {"orders_count": 5, "created_at": created,
                        "verified_email": True},
            "cart": {"total_price": "500.00", "currency": "USD"},
        }))
        sig = [s for s in d["signals"] if s["type"] == "account"][0]
        self.assertEqual(sig["level"], "unknown")

    def test_bad_cart_total_no_crash(self):
        d = _data_of(_run({
            **_email_params(),
            "account": {"orders_count": 0, "verified_email": True},
            "cart": {"total_price": "not-a-number"},
        }))
        sig = [s for s in d["signals"] if s["type"] == "account"][0]
        self.assertEqual(sig["level"], "medium")
        self.assertFalse(any("high-value order" in r for r in sig["reasons"]))

    def test_bad_created_at_no_crash(self):
        d = _data_of(_run({
            **_email_params(),
            "account": {"orders_count": 0, "created_at": "yesterday-ish"},
        }))
        sig = [s for s in d["signals"] if s["type"] == "account"][0]
        self.assertEqual(sig["level"], "medium")

    def test_no_account_no_cart_no_signal(self):
        d = _data_of(_run(_email_params()))
        self.assertEqual([s["type"] for s in d["signals"]], ["email"])


class BuyerScreenCombination(unittest.TestCase):
    def test_riskiest_wins(self):
        d = _data_of(_run(
            {**_email_params("fraud@example.com"),
             "account": {"orders_count": 0, "verified_email": True}},
            ioc={("fraud@example.com", ("email",)): [{"ioc_value": "fraud@example.com"}]}))
        self.assertEqual(d["level"], "high")

    def test_corroboration_adds_five(self):
        # high email (90) + medium account (55) -> 90 + 5 = 95
        d = _data_of(_run(
            {**_email_params("fraud@example.com"),
             "account": {"orders_count": 0, "verified_email": True}},
            ioc={("fraud@example.com", ("email",)): [{"ioc_value": "fraud@example.com"}]}))
        self.assertEqual(d["score"], 95)

    def test_two_medium_signals_score_60(self):
        d = _data_of(_run({
            **_email_params("buyer@mailinator.com"),
            "account": {"orders_count": 0, "verified_email": True},
        }))
        self.assertEqual(d["level"], "medium")
        self.assertEqual(d["score"], 60)

    def test_score_caps_at_100(self):
        d = _data_of(_run(
            {**_email_params("fraud@example.com"),
             "ip": "203.0.113.7",
             "account": {"orders_count": 0, "verified_email": True}},
            ioc={("fraud@example.com", ("email",)): [{"ioc_value": "fraud@example.com"}],
                 ("203.0.113.7", ("ip",)): [{"ioc_value": "203.0.113.7"}]}))
        self.assertEqual(d["level"], "high")
        self.assertEqual(d["score"], 100)

    def test_unknown_never_corroborates(self):
        d = _data_of(_run({
            **_email_params("buyer@mailinator.com"),
            "ip": "203.0.113.7",
            "shipping_address": {"address1": "1 Main St", "zip": "02101", "country": "US"},
            "billing_address": {"address1": "1 Main St", "zip": "02101", "country": "US"},
        }))
        # Only one risky signal (email medium); unknowns add nothing.
        self.assertEqual(d["score"], 55)


class BuyerScreenCorpusFailure(unittest.TestCase):
    def test_ioc_lookup_failure_returns_empty(self):
        class _RaisingTable:
            def query(self, **kwargs):
                raise RuntimeError("dynamodb down")
        with unittest.mock.patch.object(
                api, "dynamodb") as mock_ddb:
            mock_ddb.Table.return_value = _RaisingTable()
            hits = api._buyer_screen_ioc_hits("x@example.com", ("email",))
        self.assertEqual(hits, [])

    def test_stealer_lookup_failure_returns_empty(self):
        class _RaisingTable:
            def query(self, **kwargs):
                raise RuntimeError("dynamodb down")
        with unittest.mock.patch.object(
                api, "dynamodb") as mock_ddb:
            mock_ddb.Table.return_value = _RaisingTable()
            hits = api._buyer_screen_stolen_credential_hits("x@example.com")
        self.assertEqual(hits, [])

    def test_handler_survives_corpus_outage(self):
        # Every corpus helper raises; the email signal degrades to unknown
        # and the handler still returns a 200 verdict. A corpus outage must
        # never surface as a screening error -- the Worker fails open on a
        # non-200, so a 500 here would silently skip tagging on every order
        # until the outage cleared.
        with unittest.mock.patch.object(
                api, "_buyer_screen_ioc_hits", side_effect=RuntimeError("down")), \
             unittest.mock.patch.object(
                api, "_buyer_screen_stolen_credential_hits",
                side_effect=RuntimeError("down")), \
             unittest.mock.patch.object(
                api, "_breach_cache_get", side_effect=RuntimeError("down")):
            d = _data_of(api.handle_buyer_screen(_email_params()))
        self.assertEqual(d["level"], "unknown")
        self.assertIn("check failed", d["signals"][0]["reasons"][0])


class BuyerScreenAgent(unittest.TestCase):
    """TAP/PAP third dimension (revamp 2026-11-18).

    The Worker passes an "agent" block when it detects a Poppy file on
    the buyer domain. The Lambda verifies the agent's Passport and intent
    binding in-process (no HTTP, no x402 charge) and folds the verdict in
    as one more additive signal. Fixtures below monkeypatch the TAP
    verifier internals (handle_passport_check / handle_passport_status /
    _intent_binder); nothing here touches the network or DynamoDB.
    """

    def _passport_ok(self, **data):
        return lambda params: api._ok(data)

    def _passport_unavailable(self):
        # 503: verifier unconfigured (or timed out upstream). Fail open.
        return lambda params: api._err("verifier unavailable", 503)

    def _passport_raises(self):
        def _raise(params):
            raise RuntimeError("verifier timed out")
        return _raise

    def _binder(self, bindings):
        return lambda tenant_id, rail="tap": _FakeBinder(bindings)

    def _run_agent(self, params, passport_check=None, passport_status=None,
                   binder=None, **kw):
        patches = _patch_corpus(**kw)
        if passport_check is not None:
            patches.append(unittest.mock.patch.object(
                api, "handle_passport_check", passport_check))
        if passport_status is not None:
            patches.append(unittest.mock.patch.object(
                api, "handle_passport_status", passport_status))
        if binder is not None:
            patches.append(unittest.mock.patch.object(
                api, "_intent_binder", binder))
        for p in patches:
            p.start()
        try:
            return api.handle_buyer_screen(params)
        finally:
            for p in patches:
                p.stop()

    def _agent_signal(self, data):
        sigs = [s for s in data["signals"] if s["type"] == "agent"]
        self.assertEqual(len(sigs), 1, data["signals"])
        return sigs[0]

    def test_no_agent_block_no_agent_signal(self):
        d = _data_of(_run(_email_params()))
        self.assertEqual([s["type"] for s in d["signals"]], ["email"])

    def test_non_dict_agent_ignored(self):
        d = _data_of(_run({**_email_params(), "agent": "agent.example.com"}))
        self.assertEqual([s["type"] for s in d["signals"]], ["email"])

    def test_passport_valid_is_unknown_no_flag(self):
        d = _data_of(self._run_agent(
            {**_email_params(),
             "agent": {"domain": "agent.example.com",
                       "passport_compact": "v1.valid-compact"}},
            passport_check=self._passport_ok(
                valid=True, status="valid", revoked=False)))
        self.assertEqual(d["level"], "unknown")
        self.assertEqual(d["score"], 15)
        sig = self._agent_signal(d)
        self.assertEqual(sig["level"], "unknown")
        self.assertIn("Passport verified", sig["reasons"][0])

    def test_passport_missing_is_informational_not_medium(self):
        # Q2: an unverified agent is informational, NOT medium, until
        # Passport adoption grows. The score must not move.
        d = _data_of(self._run_agent(
            {**_email_params(),
             "agent": {"domain": "agent.example.com",
                       "poppy": {"signal": "positive",
                                 "reason": "valid poppy file"}}}))
        self.assertEqual(d["level"], "unknown")
        self.assertEqual(d["score"], 15)
        sig = self._agent_signal(d)
        self.assertEqual(sig["level"], "unknown")
        self.assertIn("no Passport presented (informational)",
                      sig["reasons"][0])

    def test_passport_expired_is_high(self):
        d = _data_of(self._run_agent(
            {**_email_params(),
             "agent": {"domain": "agent.example.com",
                       "passport_compact": "v1.expired-compact"}},
            passport_check=self._passport_ok(
                valid=False, status="expired", revoked=False)))
        self.assertEqual(d["level"], "high")
        self.assertEqual(d["score"], 90)
        sig = self._agent_signal(d)
        self.assertEqual(sig["level"], "high")
        self.assertIn("expired", sig["reasons"][0])

    def test_passport_revoked_is_high(self):
        d = _data_of(self._run_agent(
            {**_email_params(),
             "agent": {"domain": "agent.example.com",
                       "passport_compact": "v1.revoked-compact"}},
            passport_check=self._passport_ok(
                valid=True, status="revoked", revoked=True)))
        self.assertEqual(d["level"], "high")
        sig = self._agent_signal(d)
        self.assertIn("revoked", sig["reasons"][0])

    def test_passport_bad_signature_is_high(self):
        d = _data_of(self._run_agent(
            {**_email_params(),
             "agent": {"domain": "agent.example.com",
                       "passport_compact": "v1.tampered"}},
            passport_check=self._passport_ok(
                valid=False, status="invalid_signature", revoked=False)))
        self.assertEqual(d["level"], "high")
        self.assertIn("failed verification", self._agent_signal(d)["reasons"][0])

    def test_passport_id_active_is_verified(self):
        d = _data_of(self._run_agent(
            {**_email_params(),
             "agent": {"domain": "agent.example.com",
                       "passport_id": "rsp_abc123"}},
            passport_status=lambda pid: api._ok(
                {"passport_id": pid, "status": "active"})))
        self.assertEqual(d["level"], "unknown")
        self.assertIn("Passport verified",
                      self._agent_signal(d)["reasons"][0])

    def test_passport_id_expired_is_high(self):
        d = _data_of(self._run_agent(
            {**_email_params(),
             "agent": {"domain": "agent.example.com",
                       "passport_id": "rsp_abc123"}},
            passport_status=lambda pid: api._ok(
                {"passport_id": pid, "status": "expired"})))
        self.assertEqual(d["level"], "high")

    def test_passport_id_not_found_is_informational(self):
        d = _data_of(self._run_agent(
            {**_email_params(),
             "agent": {"domain": "agent.example.com",
                       "passport_id": "rsp_nope"}},
            passport_status=lambda pid: api._ok(
                {"passport_id": pid, "status": "not_found"})))
        self.assertEqual(d["level"], "unknown")
        self.assertEqual(d["score"], 15)
        self.assertIn("not found", self._agent_signal(d)["reasons"][0])

    def test_binding_verified_with_valid_passport(self):
        import time as _time
        now = int(_time.time())
        record = {"payer": "agent.example.com",
                  "counterparty": "shop.myshopify.com",
                  "amount": "149.00", "currency": "USD",
                  "issued_at": now - 60, "expires_at": now + 3600}
        d = _data_of(self._run_agent(
            {**_email_params(),
             "shop": "https://shop.myshopify.com",
             "cart": {"total_price": "149.00", "currency": "USD"},
             "agent": {"domain": "agent.example.com",
                       "passport_compact": "v1.valid-compact",
                       "binding_id": "bind_1", "tenant_id": "tnt_agent"}},
            passport_check=self._passport_ok(
                valid=True, status="valid", revoked=False),
            binder=self._binder({"bind_1": _FakeBinding(record)})))
        self.assertEqual(d["level"], "unknown")
        self.assertEqual(d["score"], 15)
        sig = self._agent_signal(d)
        self.assertEqual(sig["level"], "unknown")
        self.assertTrue(any("Passport verified" in r for r in sig["reasons"]))
        self.assertTrue(any("binding verified" in r for r in sig["reasons"]))

    def test_binding_not_found_is_high(self):
        d = _data_of(self._run_agent(
            {**_email_params(),
             "agent": {"domain": "agent.example.com",
                       "passport_compact": "v1.valid-compact",
                       "binding_id": "bind_nope", "tenant_id": "tnt_agent"}},
            passport_check=self._passport_ok(
                valid=True, status="valid", revoked=False),
            binder=self._binder({})))
        self.assertEqual(d["level"], "high")
        self.assertIn("binding not found",
                      self._agent_signal(d)["reasons"][0])

    def test_binding_counterparty_mismatch_is_high(self):
        import time as _time
        now = int(_time.time())
        record = {"payer": "agent.example.com",
                  "counterparty": "other-shop.myshopify.com",
                  "amount": "149.00", "currency": "USD",
                  "issued_at": now - 60, "expires_at": now + 3600}
        d = _data_of(self._run_agent(
            {**_email_params(),
             "shop": "https://shop.myshopify.com",
             "cart": {"total_price": "149.00", "currency": "USD"},
             "agent": {"domain": "agent.example.com",
                       "passport_compact": "v1.valid-compact",
                       "binding_id": "bind_1", "tenant_id": "tnt_agent"}},
            passport_check=self._passport_ok(
                valid=True, status="valid", revoked=False),
            binder=self._binder({"bind_1": _FakeBinding(record)})))
        self.assertEqual(d["level"], "high")
        self.assertIn("counterparty mismatch",
                      self._agent_signal(d)["reasons"][0])

    def test_binding_amount_mismatch_is_high(self):
        import time as _time
        now = int(_time.time())
        record = {"payer": "agent.example.com",
                  "counterparty": "shop.myshopify.com",
                  "amount": "9.00", "currency": "USD",
                  "issued_at": now - 60, "expires_at": now + 3600}
        d = _data_of(self._run_agent(
            {**_email_params(),
             "shop": "https://shop.myshopify.com",
             "cart": {"total_price": "149.00", "currency": "USD"},
             "agent": {"domain": "agent.example.com",
                       "passport_compact": "v1.valid-compact",
                       "binding_id": "bind_1", "tenant_id": "tnt_agent"}},
            passport_check=self._passport_ok(
                valid=True, status="valid", revoked=False),
            binder=self._binder({"bind_1": _FakeBinding(record)})))
        self.assertEqual(d["level"], "high")
        self.assertIn("amount mismatch",
                      self._agent_signal(d)["reasons"][0])

    def test_binding_expired_is_high(self):
        import time as _time
        now = int(_time.time())
        record = {"payer": "agent.example.com",
                  "counterparty": "shop.myshopify.com",
                  "amount": "149.00", "currency": "USD",
                  "issued_at": now - 7200, "expires_at": now - 3600}
        d = _data_of(self._run_agent(
            {**_email_params(),
             "agent": {"domain": "agent.example.com",
                       "passport_compact": "v1.valid-compact",
                       "binding_id": "bind_1", "tenant_id": "tnt_agent"}},
            passport_check=self._passport_ok(
                valid=True, status="valid", revoked=False),
            binder=self._binder({"bind_1": _FakeBinding(record)})))
        self.assertEqual(d["level"], "high")
        self.assertIn("binding expired",
                      self._agent_signal(d)["reasons"][0])

    def test_binding_bad_signature_is_high(self):
        import time as _time
        now = int(_time.time())
        record = {"payer": "agent.example.com",
                  "counterparty": "shop.myshopify.com",
                  "amount": "149.00", "currency": "USD",
                  "issued_at": now - 60, "expires_at": now + 3600}
        d = _data_of(self._run_agent(
            {**_email_params(),
             "agent": {"domain": "agent.example.com",
                       "passport_compact": "v1.valid-compact",
                       "binding_id": "bind_1", "tenant_id": "tnt_agent"}},
            passport_check=self._passport_ok(
                valid=True, status="valid", revoked=False),
            binder=self._binder(
                {"bind_1": _FakeBinding(record, valid=False)})))
        self.assertEqual(d["level"], "high")
        self.assertIn("signature does not verify",
                      self._agent_signal(d)["reasons"][0])

    def test_binding_without_tenant_skips_binding_check(self):
        # The registry is tenant-scoped; without tenant_id the binding
        # cannot be resolved, so it is skipped and the Passport verdict
        # stands on its own.
        d = _data_of(self._run_agent(
            {**_email_params(),
             "agent": {"domain": "agent.example.com",
                       "passport_compact": "v1.valid-compact",
                       "binding_id": "bind_1"}},
            passport_check=self._passport_ok(
                valid=True, status="valid", revoked=False),
            binder=self._binder({})))
        self.assertEqual(d["level"], "unknown")
        sig = self._agent_signal(d)
        self.assertTrue(any("Passport verified" in r for r in sig["reasons"]))
        self.assertFalse(any("binding" in r for r in sig["reasons"]))

    def test_verifier_unavailable_fails_open(self):
        # Q1: verifier timeout / unconfigured -> no agent signal at all,
        # flag nothing, return the existing buyer-screen verdict.
        d = _data_of(self._run_agent(
            {**_email_params(),
             "agent": {"domain": "agent.example.com",
                       "passport_compact": "v1.valid-compact"}},
            passport_check=self._passport_unavailable()))
        self.assertEqual(d["level"], "unknown")
        self.assertEqual(d["score"], 15)
        self.assertEqual(
            [s for s in d["signals"] if s["type"] == "agent"], [])

    def test_verifier_exception_fails_open(self):
        d = _data_of(self._run_agent(
            {**_email_params(),
             "agent": {"domain": "agent.example.com",
                       "passport_compact": "v1.valid-compact"}},
            passport_check=self._passport_raises()))
        self.assertEqual(d["level"], "unknown")
        self.assertEqual(
            [s for s in d["signals"] if s["type"] == "agent"], [])

    def test_binder_unconfigured_fails_open(self):
        d = _data_of(self._run_agent(
            {**_email_params(),
             "agent": {"domain": "agent.example.com",
                       "passport_compact": "v1.valid-compact",
                       "binding_id": "bind_1", "tenant_id": "tnt_agent"}},
            passport_check=self._passport_ok(
                valid=True, status="valid", revoked=False),
            binder=lambda tenant_id, rail="tap": None))
        self.assertEqual(d["level"], "unknown")
        sig = self._agent_signal(d)
        self.assertTrue(any("Passport verified" in r for r in sig["reasons"]))

    def test_clean_tap_never_clears_corpus_flag(self):
        # Corpus high + verified Passport: still high, same score. The
        # TAP check is additive; it can never downgrade a corpus flag.
        d = _data_of(self._run_agent(
            {**_email_params("fraud@example.com"),
             "agent": {"domain": "agent.example.com",
                       "passport_compact": "v1.valid-compact"}},
            passport_check=self._passport_ok(
                valid=True, status="valid", revoked=False),
            ioc={("fraud@example.com", ("email",)):
                 [{"ioc_value": "fraud@example.com"}]}))
        self.assertEqual(d["level"], "high")
        self.assertEqual(d["score"], 90)

    def test_agent_high_corroborates_corpus_medium(self):
        # Corpus medium (55) + agent high (90): riskiest wins at 90, and
        # the second risky signal adds +5 -> 95.
        d = _data_of(self._run_agent(
            {**_email_params("buyer@mailinator.com"),
             "agent": {"domain": "agent.example.com",
                       "passport_compact": "v1.expired-compact"}},
            passport_check=self._passport_ok(
                valid=False, status="expired", revoked=False)))
        self.assertEqual(d["level"], "high")
        self.assertEqual(d["score"], 95)


class _FakeBinding:
    """Minimal stand-in for intent_binding.Binding in agent tests."""

    def __init__(self, record, valid=True):
        self.record = record
        self._valid = valid

    def signature_valid(self):
        return self._valid


class _FakeBinder:
    """Minimal stand-in for intent_binding.IntentBinder in agent tests."""

    def __init__(self, bindings):
        self._bindings = bindings

    def get_binding(self, binding_id):
        return self._bindings.get(binding_id)


if __name__ == "__main__":
    unittest.main()
