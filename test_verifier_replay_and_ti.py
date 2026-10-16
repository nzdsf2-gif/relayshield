"""Replay protection, required credential expiry, and the TI screen, executed end to end.

Three things the TAP verifier claimed and did not do:

  * replay protection. `verify_tap_request` built a NEW MemoryNonceStore inside every call
    whenever none was passed, so it forgot every nonce the moment the request ended; and
    even a shared in-process store would not stop a replay that reaches another container.
  * credential expiry. An x401 credential with no `exp` was accepted for ever.
  * threat-intelligence screening. The committed Lambda handler passed no `ti_screen`, so
    a verifier sold on screening counterparties screened nothing.

Everything goes through lambda_handler. DynamoDB is a fake that implements the one
behaviour that matters (a conditional put that fails when the key exists); relayshield_api
is a stub module, because importing the real one needs AWS.
"""
import ast
import json
import os
import pathlib
import sys
import time
import types
import unittest
import unittest.mock

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, "/tmp/pycrypto")

import relayshield_tap_verifier as tap  # noqa: E402
import relayshield_verifier_nonces as nonces  # noqa: E402
import relayshield_tap_ti as ti  # noqa: E402
import test_tap_verifier as tt  # noqa: E402
import test_x401_integration as tx  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402


class ClientError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeTable:
    """DynamoDB's conditional put for `attribute_not_exists(pk) OR #t < :now`."""

    def __init__(self, fail_with=None):
        self.items = {}
        self.calls = 0
        self.fail_with = fail_with

    def put_item(self, Item, ConditionExpression, ExpressionAttributeNames, ExpressionAttributeValues):
        self.calls += 1
        # The fake implements exactly this condition, so the real call must send it.
        assert ConditionExpression == "attribute_not_exists(pk) OR #t < :now", ConditionExpression
        assert ExpressionAttributeNames == {"#t": "ttl"}
        if self.fail_with:
            raise self.fail_with
        existing = self.items.get(Item["pk"])
        now = ExpressionAttributeValues[":now"]
        if existing is not None and not (existing["ttl"] < now):
            raise ClientError("ConditionalCheckFailedException")
        self.items[Item["pk"]] = Item


class Store(unittest.TestCase):
    def test_first_sight_is_new_and_a_repeat_is_a_replay(self):
        s = nonces.DynamoNonceStore(table=FakeTable())
        self.assertFalse(s.seen("tap|k|n1", 1000))
        self.assertTrue(s.seen("tap|k|n1", 1001))
        self.assertFalse(s.seen("tap|k|n2", 1001))

    def test_two_containers_sharing_a_table_see_each_others_nonces(self):
        table = FakeTable()
        a, b = nonces.DynamoNonceStore(table=table), nonces.DynamoNonceStore(table=table)
        self.assertFalse(a.seen("tap|k|n", 1000))
        self.assertTrue(b.seen("tap|k|n", 1000), "a replay on another container must be caught")

    def test_an_expired_row_the_ttl_has_not_deleted_yet_counts_as_absent(self):
        s = nonces.DynamoNonceStore(table=FakeTable(), ttl_seconds=60)
        self.assertFalse(s.seen("n", 1000))
        self.assertTrue(s.seen("n", 1059))
        self.assertFalse(s.seen("n", 1061))

    def test_the_key_is_a_hash_not_the_nonce_or_the_signer(self):
        table = FakeTable()
        nonces.DynamoNonceStore(table=table).seen("tap|secret-keyid|secret-nonce", 1)
        (pk,) = table.items
        self.assertEqual(len(pk), 64)
        self.assertNotIn("secret", json.dumps(table.items))

    def test_a_store_failure_raises_instead_of_reading_as_not_seen(self):
        s = nonces.DynamoNonceStore(table=FakeTable(fail_with=ClientError("ProvisionedThroughputExceededException")))
        with self.assertRaises(ClientError):
            s.seen("n", 1)
        s = nonces.DynamoNonceStore(table=FakeTable(fail_with=RuntimeError("no such table")))
        with self.assertRaises(RuntimeError):
            s.seen("n", 1)

    def test_the_grant_gives_put_item_and_nothing_else(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import grant_breach_cache_access as g
        self.assertEqual(g.TABLE_ACTIONS["relayshield_verifier_nonces"], ["dynamodb:PutItem"])
        self.assertEqual(g.CACHE_SIDS["relayshield_verifier_nonces"], "VerifierNonceWrite")

    def test_the_setup_script_enables_ttl_and_says_to_set_the_variable_last(self):
        sh = (ROOT / "tools" / "setup_verifier_nonces_table.sh").read_text()
        self.assertIn("update-time-to-live", sh)
        self.assertIn("AttributeName=ttl", sh)
        self.assertIn("VERIFIER_NONCE_TABLE", sh)
        self.assertIn("THEN set the variable", sh)


def signed_tap(nonce, authority="merchant.example", **kw):
    priv = Ed25519PrivateKey.generate()
    jwk = {"kty": "OKP", "crv": "Ed25519", "kid": "visa-k",
           "x": tx.b64u(priv.public_key().public_bytes(serialization.Encoding.Raw,
                                                       serialization.PublicFormat.Raw))}
    req = tt.make_request(priv, jwk, "ed25519", created=int(time.time()), nonce=nonce, **kw)
    return req, jwk


class Base(unittest.TestCase):
    def setUp(self):
        tap._default_nonce_store = tap.MemoryNonceStore()
        tap._nonce_store_cache.clear()
        tap._x401_issuer_cache["keys"] = None
        env = {k: v for k, v in os.environ.items()
               if k not in (tap.NONCE_TABLE_ENV, tap.TI_SCREEN_ENV, "X401_TRUSTED_ISSUERS")}
        env["X401_TRUSTED_ISSUERS"] = tx.registry_env()
        env["VERIFIER_TELEMETRY_DISABLED"] = "1"
        p = unittest.mock.patch.dict(os.environ, env, clear=True)
        p.start()
        self.addCleanup(p.stop)

    def call(self, req, jwk=None):
        ev = {"body": json.dumps(req), "headers": {}}
        if jwk is None:
            return json.loads(tap.lambda_handler(ev, None)["body"]), tap.lambda_handler(ev, None)["statusCode"]
        with unittest.mock.patch.object(tap, "fetch_jwks", lambda *a, **k: {jwk["kid"]: jwk}):
            resp = tap.lambda_handler(ev, None)
        return json.loads(resp["body"]), resp["statusCode"]


class TapReplay(Base):
    def test_the_same_signed_request_twice_is_a_replay_even_with_no_store_passed(self):
        """This is the original bug: each call used to start with an empty store."""
        req, jwk = signed_tap("nonce-1")
        body, code = self.call(req, jwk)
        self.assertEqual((code, body["decision"]), (200, "accept"), body)
        body, code = self.call(req, jwk)
        self.assertEqual((code, body["reasons"]), (403, ["replay_nonce"]))

    def test_verify_tap_request_called_directly_with_no_store_still_catches_a_replay(self):
        """The handler always passes a store, so only a direct caller can reintroduce
        the original bug (a new MemoryNonceStore built inside every call)."""
        req, jwk = signed_tap("direct-1")
        kw = {"jwks": {jwk["kid"]: jwk}}
        self.assertEqual(tap.verify_tap_request(req, **kw).decision, "accept")
        again = tap.verify_tap_request(req, **kw)
        self.assertEqual((again.decision, again.reasons), ("reject", ["replay_nonce"]))

    def test_two_agents_using_the_same_nonce_string_do_not_collide(self):
        a, jwk_a = signed_tap("1")
        b, jwk_b = signed_tap("1")
        jwk_b["kid"] = "other-key"
        # sign b again under the other key id so its Signature-Input names it
        priv = Ed25519PrivateKey.generate()
        jwk_b = {"kty": "OKP", "crv": "Ed25519", "kid": "other-key",
                 "x": tx.b64u(priv.public_key().public_bytes(serialization.Encoding.Raw,
                                                             serialization.PublicFormat.Raw))}
        b = tt.make_request(priv, jwk_b, "ed25519", created=int(time.time()), nonce="1")
        self.assertEqual(self.call(a, jwk_a)[1], 200)
        self.assertEqual(self.call(b, jwk_b)[1], 200)

    def test_with_the_table_variable_set_the_shared_store_is_used(self):
        table = FakeTable()
        with unittest.mock.patch.dict(os.environ, {tap.NONCE_TABLE_ENV: "relayshield_verifier_nonces"}), \
                unittest.mock.patch.object(nonces.DynamoNonceStore, "_tbl", lambda self: table):
            req, jwk = signed_tap("nonce-shared")
            self.assertEqual(self.call(req, jwk)[1], 200)
            self.assertEqual(len(table.items), 1)
            # a "second container": a brand new in-process state, same table
            tap._default_nonce_store = tap.MemoryNonceStore()
            tap._nonce_store_cache.clear()
            body, code = self.call(req, jwk)
        self.assertEqual((code, body["reasons"]), (403, ["replay_nonce"]))

    def test_a_dynamo_failure_rejects_as_infrastructure_not_as_an_attack(self):
        table = FakeTable(fail_with=RuntimeError("table missing"))
        with unittest.mock.patch.dict(os.environ, {tap.NONCE_TABLE_ENV: "relayshield_verifier_nonces"}), \
                unittest.mock.patch.object(nonces.DynamoNonceStore, "_tbl", lambda self: table):
            req, jwk = signed_tap("nonce-x")
            body, code = self.call(req, jwk)
        self.assertEqual((code, body["reasons"]), (403, ["nonce_store_error"]))
        import relayshield_verifier_telemetry as vt
        self.assertIsNone(vt.classify_reason(["nonce_store_error"]))

    def test_without_the_variable_the_old_per_process_store_is_used(self):
        self.assertIs(tap._nonce_store(), tap._default_nonce_store)

    def test_x401_replay_goes_through_the_shared_store_too(self):
        table = FakeTable()
        cred = tx.credential(jti="shared-jti")
        with unittest.mock.patch.dict(os.environ, {tap.NONCE_TABLE_ENV: "relayshield_verifier_nonces"}), \
                unittest.mock.patch.object(nonces.DynamoNonceStore, "_tbl", lambda self: table):
            first = json.loads(tap.lambda_handler(
                {"body": json.dumps(tx.x401_request(cred)), "headers": {}}, None)["body"])
            tap._nonce_store_cache.clear()
            second = json.loads(tap.lambda_handler(
                {"body": json.dumps(tx.x401_request(cred)), "headers": {}}, None)["body"])
        self.assertEqual(first["decision"], "accept", first)
        self.assertEqual(second["reasons"], ["replay_nonce"])
        self.assertTrue(any(True for _ in table.items), "the nonce must be in the table")

    def test_one_issuers_jti_does_not_collide_with_anothers(self):
        key = lambda iss: f"{iss}|jti-1"  # noqa: E731
        seen = tap._x401_nonce_fn(tap.MemoryNonceStore())
        self.assertEqual(seen(key("did:a"), 1)[0], True)
        self.assertEqual(seen(key("did:b"), 1)[0], True)
        self.assertEqual(seen(key("did:a"), 2)[0], False)


class RequiredExpiry(Base):
    def call_x(self, cred):
        resp = tap.lambda_handler({"body": json.dumps(tx.x401_request(cred)), "headers": {}}, None)
        return resp["statusCode"], json.loads(resp["body"])

    def _cred_with(self, **claims):
        import base64
        c = tx.credential()
        h, p, s = c.split(".")
        payload = json.loads(tx.b64u and base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
        payload.pop("exp", None)
        payload.update(claims)
        p2 = tx.b64u(json.dumps(payload).encode())
        sig = tx.ED.sign(f"{h}.{p2}".encode())
        return f"{h}.{p2}.{tx.b64u(sig)}"

    def test_a_credential_without_exp_is_rejected(self):
        code, body = self.call_x(self._cred_with())
        self.assertEqual((code, body["reasons"]), (403, ["malformed_credential"]))
        self.assertIn("no expiry", body["details"]["x401_detail"])

    def test_an_unreadable_or_non_finite_exp_is_rejected(self):
        for bad in ("soon", "nan", float("inf"), [1], True):
            code, body = self.call_x(self._cred_with(exp=bad))
            self.assertEqual(code, 403, bad)
            self.assertEqual(body["reasons"], ["malformed_credential"], bad)

    def test_a_normal_credential_still_passes(self):
        self.assertEqual(self.call_x(tx.credential())[0], 200)

    def test_the_new_codes_are_classified_as_malformed_by_telemetry(self):
        import relayshield_verifier_telemetry as vt
        self.assertEqual(vt.classify_reason(["malformed_credential"]), "malformed")


def stub_api(link_signals=None, wallet=None, wallet_ok=True, calls=None):
    """A stand-in for relayshield_api with just the four names the screen uses."""
    m = types.ModuleType("relayshield_api")
    calls = calls if calls is not None else []

    def _assess_domain(domain, gsb_flagged):
        calls.append(("domain", domain, gsb_flagged))
        return {"signals": dict(link_signals or {}), "reasons": ["corpus hit"] if link_signals else []}

    def _link_check_level(signals):
        if signals.get("ioc_corpus") or signals.get("safe_browsing"):
            return "high"
        if signals.get("lookalike"):
            return "medium"
        return "unknown"

    def handle_wallet_risk(params):
        calls.append(("wallet", params["address"]))
        if not wallet_ok:
            return {"statusCode": 502, "body": json.dumps({"ok": False, "error": "x"})}
        return {"statusCode": 200, "body": json.dumps({"ok": True, "data": wallet or {"risk_level": "LOW"}})}

    def _unwrap(resp):
        body = json.loads(resp.get("body") or "{}")
        return (200 <= resp["statusCode"] < 300 and body.get("ok")), (body.get("data") or {})

    m._assess_domain, m._link_check_level = _assess_domain, _link_check_level
    m.handle_wallet_risk, m._unwrap = handle_wallet_risk, _unwrap
    return m, calls


class TiScreen(Base):
    def screen_with(self, **kw):
        api, calls = stub_api(**kw)
        with unittest.mock.patch.dict(sys.modules, {"relayshield_api": api}):
            return ti, calls

    def test_domain_normalisation_strips_scheme_port_path_and_credentials(self):
        for raw, want in (("https://Shop.Example:8443/x?y", "shop.example"),
                          ("user:pw@shop.example", "shop.example"), ("shop.example.", "shop.example"),
                          ("[::1]:80", ""), ("", ""), (None, ""), (5, "")):
            self.assertEqual(ti.normalise_domain(raw), want, raw)

    def test_levels_are_high_medium_or_unknown_never_low_or_clean(self):
        for signals, want in (({"ioc_corpus": True}, "high"), ({"safe_browsing": True}, "high"),
                              ({"lookalike": "PayPal"}, "medium"), ({}, "unknown")):
            api, _ = stub_api(link_signals=signals)
            with unittest.mock.patch.dict(sys.modules, {"relayshield_api": api}):
                self.assertEqual(ti.screen(domain="shop.example")["level"], want)
        for risk, want in (("CRITICAL", "high"), ("HIGH", "high"), ("MEDIUM", "medium"),
                           ("LOW", "unknown"), (None, "unknown")):
            api, _ = stub_api(wallet={"risk_level": risk})
            with unittest.mock.patch.dict(sys.modules, {"relayshield_api": api}):
                self.assertEqual(ti.screen(wallet="0xabc")["level"], want, risk)

    def test_the_worst_of_wallet_and_domain_wins(self):
        api, _ = stub_api(link_signals={"lookalike": "x"}, wallet={"risk_level": "CRITICAL"})
        with unittest.mock.patch.dict(sys.modules, {"relayshield_api": api}):
            self.assertEqual(ti.screen(wallet="0xabc", domain="shop.example")["level"], "high")

    def test_a_failed_wallet_lookup_raises_instead_of_reading_as_clean(self):
        api, _ = stub_api(wallet_ok=False)
        with unittest.mock.patch.dict(sys.modules, {"relayshield_api": api}):
            with self.assertRaises(RuntimeError):
                ti.screen(wallet="0xabc")

    def test_safe_browsing_is_not_consulted(self):
        api, calls = stub_api()
        with unittest.mock.patch.dict(sys.modules, {"relayshield_api": api}):
            ti.screen(domain="shop.example")
        self.assertEqual(calls, [("domain", "shop.example", False)])

    def test_nothing_to_screen_makes_no_lookup(self):
        api, calls = stub_api()
        with unittest.mock.patch.dict(sys.modules, {"relayshield_api": api}):
            self.assertEqual(ti.screen(), {"level": "unknown", "reasons": []})
        self.assertEqual(calls, [])


class TiWiring(Base):
    def _run(self, level_signals=None, wallet=None, wallet_ok=True, nonce="ti-n", wallet_addr=None, **req_extra):
        api, calls = stub_api(link_signals=level_signals, wallet=wallet, wallet_ok=wallet_ok)
        req, jwk = signed_tap(nonce)
        req.update(req_extra)
        if wallet_addr:
            req["wallet"] = wallet_addr
        with unittest.mock.patch.dict(sys.modules, {"relayshield_api": api}):
            return self.call(req, jwk), calls

    def test_off_by_default_no_screen_is_passed(self):
        self.assertIsNone(tap._ti_screen())
        (body, code), calls = self._run(level_signals={"ioc_corpus": True}, merchant_domain="evil.example")
        self.assertEqual((code, calls), (200, []))

    def test_on_a_flagged_counterparty_rejects_with_ti_flagged(self):
        with unittest.mock.patch.dict(os.environ, {tap.TI_SCREEN_ENV: "1"}):
            (body, code), calls = self._run(level_signals={"ioc_corpus": True},
                                            merchant_domain="evil.example")
        self.assertEqual((code, body["reasons"]), (403, ["ti_flagged"]))
        self.assertEqual(calls, [("domain", "evil.example", False)])

    def test_on_a_clean_counterparty_is_accepted_and_not_called_clean(self):
        with unittest.mock.patch.dict(os.environ, {tap.TI_SCREEN_ENV: "1"}):
            (body, code), _ = self._run(merchant_domain="fine.example")
        self.assertEqual(code, 200)
        self.assertEqual(body["details"]["ti_level"], "unknown")
        self.assertNotIn("clean", json.dumps(body).lower().replace("ti_clean", ""))

    def test_on_a_screen_that_cannot_answer_is_a_review_not_an_accept(self):
        with unittest.mock.patch.dict(os.environ, {tap.TI_SCREEN_ENV: "1"}):
            (body, code), _ = self._run(wallet_ok=False, nonce="ti-w", wallet_addr="0xabc")
        self.assertEqual((code, body["reasons"]), (202, ["ti_unavailable"]))

    def test_on_but_unloadable_is_a_visible_review_not_a_silent_skip(self):
        with unittest.mock.patch.dict(os.environ, {tap.TI_SCREEN_ENV: "1"}), \
                unittest.mock.patch.dict(sys.modules, {"relayshield_tap_ti": None}):
            req, jwk = signed_tap("ti-load")
            req["merchant_domain"] = "shop.example"
            body, code = self.call(req, jwk)
        self.assertEqual((code, body["reasons"]), (202, ["ti_unavailable"]))

    def test_the_screen_is_applied_to_the_tap_half_of_a_combined_request(self):
        with unittest.mock.patch.dict(os.environ, {tap.TI_SCREEN_ENV: "1"}):
            api, calls = stub_api(link_signals={"ioc_corpus": True})
            req, jwk = signed_tap("ti-both")
            req["merchant_domain"] = "evil.example"
            req["headers"]["Proof-Presentation"] = tx.presentation(tx.credential())
            req["transaction"] = tx.tx()
            with unittest.mock.patch.dict(sys.modules, {"relayshield_api": api}):
                body, code = self.call(req, jwk)
        self.assertEqual((code, body["reasons"]), (403, ["ti_flagged"]))

    def test_telemetry_classifies_a_ti_reject_and_records_what_was_screened_not_matched(self):
        import relayshield_verifier_telemetry as vt
        v = tap.Verdict("reject", ["ti_flagged"], {"keyid": "k"})
        item = vt.build_event("tap", v, agent_id="k", screened=["wallet", "domain"], now=1_800_000_000)
        self.assertEqual((item["rejection_reason"], item["attack_pattern"]), ("ti_match", "wallet+domain"))

    def test_relayshield_api_is_only_imported_inside_the_screen(self):
        tree = ast.parse((ROOT / "relayshield_tap_ti.py").read_text())
        for n in tree.body:
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in n.names] + [getattr(n, "module", "") or ""]
                self.assertFalse(any("relayshield_api" in x for x in names))


if __name__ == "__main__":
    unittest.main()
