"""x401 inside the TAP verifier, executed end to end through lambda_handler.

Every credential here is really signed (Ed25519 and RSA-PSS, minted with the
`cryptography` package, which is a test dependency and not a Lambda one) and verified by
the module's own pure-stdlib code. Nothing is mocked except the issuer registry, the
Visa JWKS fetch and, for telemetry, DynamoDB.

The first version of this branch was never run, and running it found: a rejected x401
request returned a Verdict object instead of an HTTP response, the transaction was read
from fields a proxied event does not have so every mandate check was skipped, a null
`headers` crashed the handler, and an empty issuer registry made every presentation fail
as "unknown issuer". Each is a test below.
"""
import ast
import base64
import json
import os
import pathlib
import sys
import time
import unittest
import unittest.mock

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, "/tmp/pycrypto")

from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding, rsa  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402

import relayshield_tap_verifier as tap  # noqa: E402
import relayshield_verifier_telemetry as vt  # noqa: E402
import x401_verifier as x401  # noqa: E402
import test_tap_verifier as tt  # noqa: E402  (reuses make_request for a real TAP signature)


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


ISSUER = "did:web:issuer.example"
ED = Ed25519PrivateKey.generate()
ED_JWK = {"kty": "OKP", "crv": "Ed25519", "kid": "iss-ed",
          "x": b64u(ED.public_key().public_bytes(serialization.Encoding.Raw,
                                                 serialization.PublicFormat.Raw))}
RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_nums = RSA_KEY.public_key().public_numbers()
RSA_JWK = {"kty": "RSA", "kid": "iss-rsa",
           "n": b64u(_nums.n.to_bytes((_nums.n.bit_length() + 7) // 8, "big")),
           "e": b64u(_nums.e.to_bytes((_nums.e.bit_length() + 7) // 8, "big"))}

_counter = [0]


def mandate(**over):
    m = {"agent": "agent-1", "merchant": "shop.example",
         "amountCeiling": {"value": 50, "currency": "USD"},
         "actionCategory": ["purchase"], "assuranceLevel": "IAL2"}
    m.update(over)
    return {k: v for k, v in m.items() if v is not None}


def credential(subject=None, key="ed", alg=None, iss=ISSUER, exp_delta=3600, jti=None,
               tamper=False):
    _counter[0] += 1
    payload = {"iss": iss, "jti": jti or f"jti-{_counter[0]}-{time.time_ns()}",
               "exp": time.time() + exp_delta,
               "vc": {"credentialSubject": subject if subject is not None else mandate()}}
    header = {"alg": alg or ("EdDSA" if key == "ed" else "PS256")}
    h = b64u(json.dumps(header).encode())
    p = b64u(json.dumps(payload).encode())
    signing_input = f"{h}.{p}".encode()
    if key == "ed":
        sig = ED.sign(signing_input)
    else:
        sig = RSA_KEY.sign(signing_input, padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                                      salt_length=32), hashes.SHA256())
    if tamper:
        sig = bytes([sig[0] ^ 1]) + sig[1:]
    return f"{h}.{p}.{b64u(sig)}"


def presentation(*creds):
    return b64u(json.dumps({"verifiableCredential": list(creds)}).encode())


def tx(**over):
    t = {"amount": 20, "currency": "USD", "merchant": "shop.example",
         "action_category": "purchase", "agent_id": "agent-1"}
    t.update(over)
    return t


def event(request):
    return {"headers": {"x-rs-api-key": "rs_live_test"}, "body": json.dumps(request)}


def x401_request(cred=None, transaction="default", extra_headers=None, **top):
    headers = {"Proof-Presentation": presentation(cred or credential())}
    headers.update(extra_headers or {})
    req = {"headers": headers, "authority": "shop.example"}
    req["transaction"] = tx() if transaction == "default" else transaction
    req.update(top)
    return req


def registry_env(entries=None):
    return json.dumps({"issuers": entries if entries is not None
                       else {ISSUER: ED_JWK}})


class Base(unittest.TestCase):
    def setUp(self):
        tap._x401_issuer_cache["keys"] = None
        x401._nonce_cache.clear()
        patcher = unittest.mock.patch.dict(os.environ, {"X401_TRUSTED_ISSUERS": registry_env()})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: tap._x401_issuer_cache.update(keys=None))
        # Never let a test reach DynamoDB or Visa.
        env = unittest.mock.patch.dict(os.environ, {"VERIFIER_TELEMETRY_DISABLED": "1"})
        env.start()
        self.addCleanup(env.stop)

    def call(self, request):
        resp = tap.lambda_handler(event(request), None)
        self.assertIsInstance(resp, dict, "the handler must return an HTTP response, not a Verdict")
        return resp["statusCode"], json.loads(resp["body"])


class OnlyX401(Base):
    def test_a_valid_presentation_is_accepted(self):
        code, body = self.call(x401_request())
        self.assertEqual((code, body["decision"]), (200, "accept"), body)

    def test_a_rejection_is_an_http_403_with_the_reason_code(self):
        """The first version returned a Verdict object here: a 502 in production."""
        code, body = self.call(x401_request(transaction=tx(amount=500)))
        self.assertEqual(code, 403)
        self.assertEqual(body["reasons"], ["mandate_scope_exceeded"])

    def test_every_request_without_the_header_is_exactly_the_old_tap_path(self):
        code, body = self.call({"headers": {}})
        self.assertEqual(code, 403)
        self.assertEqual(body["reasons"], ["missing_signature_headers"])

    def test_null_headers_do_not_crash(self):
        for req in ({"headers": None}, {}, {"headers": "x"}):
            self.assertEqual(self.call(req)[0], 403)

    def test_an_RSA_PSS_credential_verifies_with_an_RSA_issuer(self):
        env = registry_env({ISSUER: RSA_JWK})
        with unittest.mock.patch.dict(os.environ, {"X401_TRUSTED_ISSUERS": env}):
            tap._x401_issuer_cache["keys"] = None
            code, body = self.call(x401_request(credential(key="rsa")))
        self.assertEqual((code, body["decision"]), (200, "accept"), body)


class FailsClosed(Base):
    def test_a_missing_amount_is_a_failure_not_a_pass(self):
        """The first version skipped any check whose transaction value was empty, so a
        caller that sent no transaction was verified against nothing."""
        t = tx()
        del t["amount"]
        code, body = self.call(x401_request(transaction=t))
        self.assertEqual((code, body["reasons"]), (403, ["mandate_scope_exceeded"]))
        self.assertIn("amount not supplied", body["details"]["x401_detail"])

    def test_no_transaction_at_all_is_a_failure(self):
        req = x401_request(transaction={})
        self.assertEqual(self.call(req)[0], 403)
        req.pop("transaction")
        self.assertEqual(self.call(req)[0], 403)

    def test_each_constraint_the_mandate_sets_must_be_checkable(self):
        for field, label in (("merchant", "merchant not supplied"),
                             ("action_category", "action not supplied"),
                             ("agent_id", "agent not supplied"),
                             ("currency", "currency not supplied")):
            t = tx()
            t[field] = ""
            req = x401_request(transaction=t, authority="")
            code, body = self.call(req)
            self.assertEqual(code, 403, field)
            self.assertIn(label, body["details"]["x401_detail"], field)

    def test_merchant_defaults_to_the_authority_when_the_transaction_omits_it(self):
        t = tx()
        del t["merchant"]
        code, body = self.call(x401_request(transaction=t, authority="shop.example"))
        self.assertEqual(code, 200, body)

    def test_nan_and_infinity_amounts_do_not_slip_past_the_ceiling(self):
        """float('nan') > ceiling is False, so a nan amount passed an `amount > ceiling` test."""
        for bad in ("nan", "inf", float("nan"), True):
            code, _ = self.call(x401_request(transaction=tx(amount=bad)))
            self.assertEqual(code, 403, bad)

    def test_an_unreadable_validity_date_fails_instead_of_never_expiring(self):
        for field in ("validUntil", "validFrom"):
            c = credential(mandate(**{field: "next tuesday-ish"}))
            code, body = self.call(x401_request(c))
            self.assertEqual(code, 403, field)
            self.assertIn("not a readable time", body["details"]["x401_detail"])

    def test_an_expired_mandate_is_rejected(self):
        c = credential(mandate(validUntil="2020-01-01T00:00:00Z"))
        self.assertEqual(self.call(x401_request(c))[0], 403)

    def test_assurance_below_IAL2_is_rejected(self):
        c = credential(mandate(assuranceLevel="IAL1"))
        code, body = self.call(x401_request(c))
        self.assertEqual((code, body["reasons"]), (403, ["assurance_insufficient"]))

    def test_an_expired_credential_is_rejected(self):
        code, body = self.call(x401_request(credential(exp_delta=-3600)))
        self.assertEqual((code, body["reasons"]), (403, ["signature_expired"]))

    def test_a_tampered_signature_is_rejected(self):
        code, body = self.call(x401_request(credential(tamper=True)))
        self.assertEqual((code, body["reasons"]), (403, ["bad_signature"]))

    def test_an_issuer_not_in_the_registry_is_rejected(self):
        code, body = self.call(x401_request(credential(iss="did:web:stranger.example")))
        self.assertEqual((code, body["reasons"]), (403, ["unknown_issuer"]))

    def test_a_replayed_credential_is_rejected(self):
        c = credential(jti="fixed-jti")
        self.assertEqual(self.call(x401_request(c))[0], 200)
        code, body = self.call(x401_request(c))
        self.assertEqual((code, body["reasons"]), (403, ["replay_nonce"]))

    def test_malformed_input_is_rejected_not_raised(self):
        for header in ("!!!not base64!!!", b64u(b"[]"), b64u(b'{"x":1}'), "", "   "):
            req = x401_request()
            req["headers"]["Proof-Presentation"] = header
            self.assertEqual(self.call(req)[0], 403, header)
        req = x401_request()
        req["headers"]["Proof-Presentation"] = 12345
        self.assertEqual(self.call(req)[0], 403)

    def test_the_token_cannot_choose_a_weaker_algorithm_for_a_key(self):
        """The registry key decides the algorithm. An Ed25519 key never verifies PS256,
        an RSA key never verifies EdDSA, and RS256 (PKCS#1 v1.5) is not verified at all
        rather than being checked with the wrong scheme."""
        self.assertEqual(self.call(x401_request(credential(alg="PS256")))[0], 403)
        env = registry_env({ISSUER: RSA_JWK})
        with unittest.mock.patch.dict(os.environ, {"X401_TRUSTED_ISSUERS": env}):
            tap._x401_issuer_cache["keys"] = None
            for alg in ("EdDSA", "RS256", "none", "HS256"):
                c = credential(key="rsa", alg=alg)
                self.assertEqual(self.call(x401_request(c))[0], 403, alg)

    def test_the_rejection_text_does_not_echo_the_mandate_values(self):
        _, body = self.call(x401_request(transaction=tx(agent_id="somebody-else")))
        self.assertNotIn("agent-1", json.dumps(body))


class Unavailable(Base):
    def test_an_empty_registry_is_a_review_not_a_reject_and_not_an_accept(self):
        with unittest.mock.patch.dict(os.environ, {"X401_TRUSTED_ISSUERS": registry_env({})}):
            tap._x401_issuer_cache["keys"] = None
            code, body = self.call(x401_request())
        self.assertEqual((code, body["reasons"]), (202, ["x401_issuers_unconfigured"]))

    def test_the_committed_registry_file_is_valid_and_ships_empty(self):
        doc = json.loads((ROOT / "x401_issuers.json").read_text())
        self.assertEqual(doc, {"issuers": {}})

    def test_a_package_without_the_x401_module_still_verifies_tap(self):
        with unittest.mock.patch.object(tap, "_x401", None):
            code, body = self.call(x401_request())
            self.assertEqual((code, body["reasons"]), (202, ["x401_unavailable"]))
            self.assertEqual(self.call({"headers": {}})[1]["reasons"], ["missing_signature_headers"])

    def test_the_import_is_guarded_at_module_top(self):
        tree = ast.parse((ROOT / "relayshield_tap_verifier.py").read_text())
        for n in tree.body:
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in n.names] + [getattr(n, "module", "") or ""]
                self.assertFalse(any("x401" in x for x in names),
                                 "an unguarded top-level x401 import takes the whole Lambda down")
        guarded = [n for n in tree.body if isinstance(n, ast.Try)
                   and any(isinstance(b, ast.Import) and b.names[0].name == "x401_verifier"
                           for b in n.body)]
        self.assertTrue(guarded)

    def test_an_internal_error_is_a_review_never_an_accept(self):
        with unittest.mock.patch.object(x401, "verify_x401_presentation",
                                        side_effect=RuntimeError("boom")):
            code, body = self.call(x401_request())
        self.assertEqual((code, body["reasons"]), (202, ["x401_internal_error"]))


class Registry(unittest.TestCase):
    def test_ed25519_and_rsa_entries_load_as_bytes_and_tuple(self):
        keys = tap._x401_issuer_keys(env=json.dumps({"issuers": {"a": ED_JWK, "b": RSA_JWK}}))
        self.assertIsInstance(keys["a"], bytes)
        self.assertEqual(len(keys["a"]), 32)
        self.assertEqual(keys["b"][1], 65537)

    def test_unusable_entries_are_skipped_and_the_rest_kept(self):
        doc = {"issuers": {"good": ED_JWK, "bad": {"kty": "OKP"}, "worse": "text", "": ED_JWK}}
        self.assertEqual(set(tap._x401_issuer_keys(env=json.dumps(doc))), {"good"})

    def test_garbage_means_not_configured(self):
        for raw in ("not json", "[]", '{"issuers": []}', '{"issuers": 3}'):
            self.assertEqual(tap._x401_issuer_keys(env=raw), {}, raw)


class Both(Base):
    """A request carrying a TAP signature AND a presentation: both must accept."""

    def _both(self, x401_cred=None, **tap_kw):
        priv = Ed25519PrivateKey.generate()
        jwk = {"kty": "OKP", "crv": "Ed25519", "kid": "visa-k",
               "x": b64u(priv.public_key().public_bytes(serialization.Encoding.Raw,
                                                        serialization.PublicFormat.Raw))}
        req = tt.make_request(priv, jwk, "ed25519", created=int(time.time()),
                              nonce=f"n-{time.time_ns()}", **tap_kw)
        req["headers"]["Proof-Presentation"] = presentation(x401_cred or credential())
        req["transaction"] = tx()
        return req, jwk

    def _call(self, req, jwk):
        with unittest.mock.patch.object(tap, "fetch_jwks", lambda *a, **k: {jwk["kid"]: jwk}):
            return self.call(req)

    def test_both_valid_is_an_accept(self):
        req, jwk = self._both()
        code, body = self._call(req, jwk)
        self.assertEqual((code, body["decision"]), (200, "accept"), body)

    def test_x401_failing_rejects_and_reasons_name_x401_only(self):
        req, jwk = self._both(credential(tamper=True))
        code, body = self._call(req, jwk)
        self.assertEqual((code, body["reasons"]), (403, ["bad_signature"]))
        self.assertEqual(body["details"]["keyid"], "visa-k")

    def test_tap_failing_rejects_even_when_x401_is_valid(self):
        req, jwk = self._both(tamper_base=True)
        code, body = self._call(req, jwk)
        self.assertEqual((code, body["reasons"]), (403, ["bad_signature"]))

    def test_a_review_from_one_half_does_not_become_an_accept(self):
        with unittest.mock.patch.object(tap, "_x401", None):
            req, jwk = self._both()
            code, body = self._call(req, jwk)
        self.assertEqual((code, body["decision"]), (202, "review"))

    def test_a_reject_beats_a_review(self):
        v = tap._combine(tap._review("a"), tap._reject("b"))
        self.assertEqual((v.decision, v.reasons), ("reject", ["b"]))


class Telemetry(Base):
    """The hook, seen from the x401 path. DynamoDB is faked; nothing else is."""

    def _run(self, request, opted_in=True):
        written, reads = [], []

        class Keys:
            def get_item(self, **kw):
                reads.append(kw)
                return {"Item": {"api_key": "rs_live_test", "active": True,
                                 vt.OPT_IN_FIELD: opted_in}}

        class Rows:
            def put_item(self, Item):
                written.append(Item)

        class DDB:
            def Table(self, name):
                return Keys() if name == vt.API_KEYS_TABLE else Rows()

        env = {k: v for k, v in os.environ.items() if k != "VERIFIER_TELEMETRY_DISABLED"}
        with unittest.mock.patch.dict(os.environ, env, clear=True), \
                unittest.mock.patch.object(vt, "_dynamodb", lambda: DDB()):
            resp = tap.lambda_handler(event(request), None)
        return resp, written, reads

    def test_an_x401_rejection_is_reported_as_x401_with_the_issuer_hash_and_a_code(self):
        resp, written, _ = self._run(x401_request(transaction=tx(amount=500)))
        self.assertEqual(resp["statusCode"], 403)
        self.assertEqual(len(written), 1)
        row = written[0]
        self.assertEqual(row["verifier_type"], "x401")
        self.assertEqual(row["rejection_reason"], "mandate_exceeded")
        self.assertEqual(row["issuer_hash"], vt.hash_id(ISSUER))
        self.assertNotIn("500", json.dumps(row, default=str))
        self.assertNotIn("shop.example", json.dumps(row, default=str))

    def test_an_accept_touches_no_table(self):
        resp, written, reads = self._run(x401_request())
        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual((written, reads), ([], []))

    def test_not_opted_in_writes_nothing(self):
        _, written, _ = self._run(x401_request(transaction=tx(amount=500)), opted_in=False)
        self.assertEqual(written, [])

    def test_our_own_unavailability_is_not_reported_as_an_attack(self):
        with unittest.mock.patch.object(tap, "_x401", None):
            resp, written, reads = self._run(x401_request())
        self.assertEqual(resp["statusCode"], 202)
        self.assertEqual((written, reads), ([], []))

    def test_every_x401_failure_code_is_classified_not_lumped_into_other(self):
        codes = {c for _, c in x401._REASON_CODES}
        for code in codes - {"assurance_insufficient"}:
            self.assertNotEqual(vt.classify_reason([code]), "other", code)
        self.assertEqual(vt.classify_reason(["assurance_insufficient"]), "other")

    def test_a_tap_plus_x401_rejection_is_typed_as_both(self):
        # TAP half rejects (unsigned) while a presentation is present -> reasons name TAP's.
        req = x401_request(extra_headers={"signature": "sig1=:AA:", "signature-input": "sig1=()"})
        resp, written, _ = self._run(req)
        self.assertEqual(resp["statusCode"], 403)
        self.assertEqual(written[0]["verifier_type"], "tap+x401")


class ReasonCodes(unittest.TestCase):
    def test_prose_to_code(self):
        cases = {
            "presentation parse failed: x": "malformed_presentation",
            "unknown issuer: did:x": "unknown_issuer",
            "credential signature invalid": "bad_signature",
            "mandate scope exceeded: amount 5 exceeds ceiling 1": "mandate_scope_exceeded",
            "nonce replay detected": "replay_nonce",
            "something nobody wrote": "x401_other",
            None: "x401_other",
        }
        for prose, code in cases.items():
            self.assertEqual(x401.reason_code(prose), code, prose)


if __name__ == "__main__":
    unittest.main()
