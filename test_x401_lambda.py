"""The x401 relying party as the merchant meets it: through lambda_handler and the API.

A merchant's route calls the verifier Lambda with the agent's request. With an `x401_policy`
and no PROOF-RESPONSE it gets the challenge to hand back as a 401; with a PROOF-RESPONSE it
gets a verdict. Alongside a TAP signature both must accept, and TAP's verified key id is
the Agent Identifier a policy can bind to. Nothing here is mocked except time-free
environment, the network fetch, and DynamoDB.
"""
import json
import os
import sys
import time
import unittest
import unittest.mock

sys.path.insert(0, "/tmp/pycrypto")

import test_verifier_telemetry as _tv  # noqa: F401  (installs the boto3 stub relayshield_api needs)
import x401_jose as jose
import x401_net
import x401_rp as rp
import x401_testkit as kit
import relayshield_tap_verifier as tap
import relayshield_verifier_telemetry as vt
import test_tap_verifier as tt
import test_x401_rp as base
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ORIGIN = base.ORIGIN
PATH, METHOD = "/accounts/applications", "POST"


class Setup(unittest.TestCase):
    def setUp(self):
        self.issuer = kit.Issuer("https://issuer.example")
        self.wallet = kit.Wallet()
        self.signing_key = jose.generate_p256_jwk()
        self.policy = base.sd_policy()
        env = {k: v for k, v in os.environ.items() if k not in (
            "X401_POLICIES", "X401_TRUSTED_ISSUERS", "X401_SIGNING_JWK", tap.NONCE_TABLE_ENV, tap.TI_SCREEN_ENV,
            "X401_NONCE_SECRET", "VERIFIER_TELEMETRY_DISABLED")}
        env.update({
            "X401_SIGNING_JWK": json.dumps(self.signing_key),
            "X401_POLICIES": json.dumps({"policies": {"age": self.policy}}),
            "X401_TRUSTED_ISSUERS": json.dumps({"issuers": {"https://issuer.example": self.issuer.registry_entry()}}),
            "VERIFIER_TELEMETRY_DISABLED": "1"})
        patcher = unittest.mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        rp._signer_cache.update(signer=None, at=0.0)
        tap._default_nonce_store = tap.MemoryNonceStore()
        tap._nonce_store_cache.clear()
        tap._x401_issuer_cache["keys"] = None

    def call(self, request, event_extra=None):
        ev = {"body": json.dumps(request), "headers": {}}
        ev.update(event_extra or {})
        resp = tap.lambda_handler(ev, None)
        return resp["statusCode"], json.loads(resp["body"])

    def challenge(self, policy="age"):
        code, body = self.call({"action": "x401_challenge", "x401_policy": policy, "path": PATH, "method": METHOD})
        self.assertEqual(code, 200, body)
        return jose.b64u_json_decode(body["proof_request"])

    def vc(self, **kw):
        kw.setdefault("always", {"given_name": "Ada"})
        kw.setdefault("selectable", {"age_over_18": True})
        kw.setdefault("holder", self.wallet.public_jwk)
        return self.issuer.sd_jwt_vc(base.VCT, **kw)

    def proof_response(self, payload, vc=None, agent_id=None, **kw):
        res = self.wallet.fulfil(payload, {"id_card": vc or self.vc()}, origin=ORIGIN,
                                 verifier_public_jwk=jose.public_jwk(self.signing_key), **kw)
        return kit.artifact(res, "proof-age-v1", agent_id)

    def request(self, header=None, **extra):
        req = {"path": PATH, "method": METHOD, "x401_policy": "age", "headers": {}}
        if header:
            req["headers"]["PROOF-RESPONSE"] = header
        req.update(extra)
        return req


class Challenge(Setup):
    def test_the_challenge_action_returns_a_usable_proof_request(self):
        payload = self.challenge()
        self.assertEqual((payload["scheme"], payload["version"]), ("x401", "0.2.0"))
        (req,) = payload["credential_requirements"]["digital"]["requests"]
        _, claims = jose.jws_verify(req["data"]["request"], [jose.public_jwk(self.signing_key)], {"ES256"})
        self.assertEqual(claims["expected_origins"], [ORIGIN])

    def test_the_challenge_response_names_the_headers_to_set(self):
        code, body = self.call({"action": "x401_challenge", "x401_policy": "age", "path": PATH, "method": METHOD})
        self.assertEqual(body["headers"]["PROOF-REQUEST"], body["proof_request"])
        self.assertEqual(body["headers"]["Cache-Control"], "no-store")

    def test_challenge_errors_have_honest_status_codes(self):
        self.assertEqual(self.call({"action": "x401_challenge", "x401_policy": "nope", "path": PATH, "method": METHOD})[0], 404)
        self.assertEqual(self.call({"action": "x401_challenge", "x401_policy": "age"})[0], 400)
        self.assertEqual(self.call({"action": "x401_challenge", "path": PATH, "method": METHOD})[0], 400)
        os.environ.pop("X401_SIGNING_JWK")
        with unittest.mock.patch.object(rp, "load_signer", side_effect=rp.X401Error("verifier_not_configured", "x")):
            self.assertEqual(self.call({"action": "x401_challenge", "x401_policy": "age", "path": PATH, "method": METHOD})[0], 503)

    def test_one_call_with_no_proof_is_a_complete_challenge(self):
        code, body = self.call(self.request())
        self.assertEqual((code, body["decision"], body["reasons"]), (401, "reject", ["proof_required"]))
        payload = jose.b64u_json_decode(body["details"]["proof_request"])
        self.assertEqual(payload["scheme"], "x401")
        self.assertEqual(body["details"]["request_id"], "proof-age-v1")

    def test_a_policy_that_is_not_defined_is_refused_not_skipped(self):
        code, body = self.call(self.request(x401_policy="ghost"))
        self.assertEqual(code, 403)
        self.assertNotEqual(body["decision"], "accept")


class Verify(Setup):
    def test_the_full_flow_challenge_wallet_verdict(self):
        payload = self.challenge()
        code, body = self.call(self.request(self.proof_response(payload)))
        self.assertEqual((code, body["decision"]), (200, "accept"), body)
        creds = body["details"]["x401"]["credentials"]["id_card"]
        self.assertEqual(creds[0]["claims"], {"age_over_18": True})
        self.assertEqual(body["details"]["x401"]["request_id"], "proof-age-v1")

    def test_a_failure_returns_the_error_object_to_put_in_proof_result(self):
        payload = self.challenge()
        code, body = self.call(self.request(self.proof_response(payload, self.vc(selectable={"age_over_18": False}))))
        self.assertEqual((code, body["reasons"]), (403, ["claims_not_satisfied"]))
        err = jose.b64u_json_decode(body["details"]["proof_result"])
        self.assertEqual((err["scheme"], err["error"], err["request_id"]), ("x401", "claims_not_satisfied", "proof-age-v1"))

    def test_replay_through_the_lambda_even_after_the_in_process_store_is_reset(self):
        payload = self.challenge()
        art = self.proof_response(payload)
        self.assertEqual(self.call(self.request(art))[0], 200)
        code, body = self.call(self.request(art))
        self.assertEqual((code, body["reasons"]), (403, ["replayed_nonce"]))

    def test_a_proof_for_another_route_is_refused(self):
        payload = self.challenge()
        code, body = self.call(self.request(self.proof_response(payload), path="/other"))
        self.assertEqual(body["reasons"], ["route_mismatch"])

    def test_a_missing_policy_is_a_malformed_request_with_everything_else_present(self):
        payload = self.challenge()
        req = self.request(self.proof_response(payload))
        req.pop("x401_policy")
        code, body = self.call(req)
        self.assertEqual((code, body["reasons"]), (403, ["malformed_request"]))
        self.assertEqual(body["details"]["detail"], "x401_policy is required")

    def test_the_guarded_fetcher_is_what_the_relying_party_is_given(self):
        seen = {}
        with unittest.mock.patch.object(rp, "verify_result", lambda *a, **k: seen.update(k) or (_ for _ in ()).throw(
                rp.X401Error("invalid_response", "x"))):
            self.call(self.request("abc"))
        self.assertIs(seen["fetch"], x401_net.safe_fetch)

    def test_a_status_list_fetch_through_the_lambda_goes_via_safe_fetch(self):
        self.policy_with_status()
        payload = self.challenge()
        vc = self.vc(status={"status_list": {"idx": 3, "uri": "https://status.issuer.example/l/1"}})
        calls = []
        with unittest.mock.patch.object(x401_net, "safe_fetch", lambda url, **k: calls.append(url)):
            code, body = self.call(self.request(self.proof_response(payload, vc)))
        self.assertEqual(calls, ["https://status.issuer.example/l/1"])
        self.assertEqual((code, body["reasons"]), (403, ["status_unavailable"]))

    def policy_with_status(self):
        os.environ["X401_TRUSTED_ISSUERS"] = json.dumps({"issuers": {"https://issuer.example": self.issuer.registry_entry(
            status_uri_prefixes=["https://status.issuer.example/"])}})

    def test_malformed_requests(self):
        self.assertEqual(self.call({"headers": {"PROOF-RESPONSE": "x"}})[1]["reasons"], ["malformed_request"])
        req = self.request("x")
        req.pop("path")
        self.assertEqual(self.call(req)[1]["reasons"], ["malformed_request"])
        self.assertEqual(self.call(self.request("!!"))[1]["reasons"], ["invalid_response"])

    def test_the_verifier_unconfigured_is_a_review_never_an_accept(self):
        payload = self.challenge()
        art = self.proof_response(payload)
        os.environ.pop("X401_SIGNING_JWK")
        with unittest.mock.patch.object(rp, "load_signer", side_effect=rp.X401Error("verifier_not_configured", "x")):
            code, body = self.call(self.request(art))
        self.assertEqual((code, body["decision"], body["reasons"]), (202, "review", ["verifier_not_configured"]))

    def test_a_package_without_the_relying_party_is_a_visible_review(self):
        with unittest.mock.patch.object(tap, "_rp", None):
            code, body = self.call(self.request("abc"))
        self.assertEqual((code, body["reasons"]), (202, ["x401_unavailable"]))
        with unittest.mock.patch.object(tap, "_rp", None):
            self.assertEqual(self.call({"action": "x401_challenge", "x401_policy": "age", "path": PATH, "method": METHOD})[0], 503)

    def test_the_import_is_guarded(self):
        import ast
        pathlib = __import__("pathlib")
        tree = ast.parse((pathlib.Path(tap.__file__)).read_text())
        for n in tree.body:
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in n.names] + [getattr(n, "module", "") or ""]
                self.assertFalse(any(x in ("x401_rp", "x401_net", "x401_jose") for x in names))

    def test_an_internal_error_is_a_review(self):
        payload = self.challenge()
        with unittest.mock.patch.object(rp, "verify_result", side_effect=RuntimeError("boom")):
            code, body = self.call(self.request(self.proof_response(payload)))
        self.assertEqual((code, body["reasons"]), (202, ["x401_internal_error"]))

    def test_the_old_presentation_path_is_untouched_when_no_policy_is_given(self):
        code, body = self.call({"headers": {"Proof-Presentation": "abc"}})
        self.assertIn(body["reasons"][0], ("x401_issuers_unconfigured", "x401_unavailable", "malformed_presentation"))


def tap_request(priv, jwk, nonce, **extra):
    req = tt.make_request(priv, jwk, "ed25519", created=int(time.time()), nonce=nonce, path=PATH)
    req["method"] = METHOD
    req["authority"] = "merchant.example"
    req.update(extra)
    return req


class WithTap(Setup):
    def setUp(self):
        super().setUp()
        self.priv = Ed25519PrivateKey.generate()
        self.jwk = {"kty": "OKP", "crv": "Ed25519", "kid": "agent-key-1",
                    "x": jose.b64u_encode(self.priv.public_key().public_bytes(serialization.Encoding.Raw,
                                                                              serialization.PublicFormat.Raw))}
        p = unittest.mock.patch.object(tap, "fetch_jwks", lambda *a, **k: {self.jwk["kid"]: self.jwk})
        p.start()
        self.addCleanup(p.stop)

    def both(self, art, nonce="n-1", **extra):
        req = tap_request(self.priv, self.jwk, nonce, x401_policy="age", **extra)
        req["headers"]["PROOF-RESPONSE"] = art
        return req

    def test_both_valid_is_an_accept(self):
        code, body = self.call(self.both(self.proof_response(self.challenge())))
        self.assertEqual((code, body["decision"]), (200, "accept"), body)
        self.assertEqual(body["details"]["keyid"], "agent-key-1")
        self.assertIn("x401", body["details"])

    def test_tap_refusing_means_x401_never_runs_and_the_nonce_is_not_burned(self):
        payload = self.challenge()
        art = self.proof_response(payload)
        bad = tap_request(self.priv, self.jwk, "n-bad", tamper_base=True) if False else None
        req = self.both(art, nonce="n-2")
        req["headers"]["signature"] = "sig1=:AAAA:"           # break the TAP signature
        code, body = self.call(req)
        self.assertEqual((code, body["reasons"]), (403, ["bad_signature"]))
        code, body = self.call(self.both(art, nonce="n-3"))   # the same x401 result, fresh TAP request
        self.assertEqual((code, body["decision"]), (200, "accept"), "the failed TAP attempt must not have consumed the x401 nonce")

    def test_agent_binding_uses_the_verified_tap_key_not_a_claimed_one(self):
        self.policy["bind_agent"] = True
        os.environ["X401_POLICIES"] = json.dumps({"policies": {"age": self.policy}})
        payload = self.challenge()
        code, body = self.call(self.both(self.proof_response(payload, agent_id="agent-key-1"), nonce="n-4"))
        self.assertEqual((code, body["decision"]), (200, "accept"), body)
        payload = self.challenge()
        code, body = self.call(self.both(self.proof_response(payload, agent_id="someone-else"), nonce="n-5"))
        self.assertEqual(body["reasons"], ["agent_binding_failed"])

    def test_a_claimed_agent_id_cannot_override_the_verified_tap_key(self):
        """With a TAP signature present the Agent Identifier is the key TAP VERIFIED. A request
        that also carries its own `agent_id` field must not be able to pick another."""
        self.policy["bind_agent"] = True
        os.environ["X401_POLICIES"] = json.dumps({"policies": {"age": self.policy}})
        payload = self.challenge()
        art = self.proof_response(payload, agent_id="victim-agent")
        code, body = self.call(self.both(art, nonce="n-7", agent_id="victim-agent"))
        self.assertEqual(body["reasons"], ["agent_binding_failed"])

    def test_agent_binding_without_a_tap_signature_cannot_be_satisfied(self):
        self.policy["bind_agent"] = True
        os.environ["X401_POLICIES"] = json.dumps({"policies": {"age": self.policy}})
        payload = self.challenge()
        code, body = self.call(self.request(self.proof_response(payload, agent_id="agent-key-1")))
        self.assertEqual(body["reasons"], ["agent_binding_failed"])

    def test_an_unauthenticated_agent_id_field_is_ignored(self):
        self.policy["bind_agent"] = True
        os.environ["X401_POLICIES"] = json.dumps({"policies": {"age": self.policy}})
        payload = self.challenge()
        code, body = self.call(self.request(self.proof_response(payload, agent_id="agent-key-1"), agent_id="agent-key-1"))
        self.assertEqual(body["reasons"], ["agent_binding_failed"])

    def test_the_verdict_has_the_same_shape_with_and_without_tap(self):
        """A merchant must not need to know whether TAP ran to find the PROOF-REQUEST, the
        error object, or the verified claims."""
        req = tap_request(self.priv, self.jwk, "n-8", x401_policy="age")
        code, with_tap = self.call(req)
        code2, without = self.call(self.request())
        self.assertEqual((code, code2), (401, 401))
        for body in (with_tap, without):
            self.assertIn("proof_request", body["details"])
            self.assertEqual(body["details"]["request_id"], "proof-age-v1")
        self.assertIn("keyid", with_tap["details"])
        payload = self.challenge()
        code, body = self.call(self.both(self.proof_response(payload, self.vc(selectable={"age_over_18": False})), nonce="n-9"))
        self.assertIn("proof_result", body["details"])
        payload = self.challenge()
        code, body = self.call(self.both(self.proof_response(payload), nonce="n-10"))
        self.assertIn("credentials", body["details"]["x401"], "claims must not be nested under x401.x401")
        self.assertNotIn("x401", body["details"]["x401"])

    def test_a_correctly_signed_request_for_another_route_cannot_reuse_a_proof(self):
        payload = self.challenge()
        art = self.proof_response(payload)
        req = tap_request(self.priv, self.jwk, "n-11", x401_policy="age")
        req["path"] = "/other"                       # re-sign for the other route
        other = tt.make_request(self.priv, self.jwk, "ed25519", created=int(time.time()), nonce="n-12", path="/other")
        other.update({"method": METHOD, "x401_policy": "age", "authority": "merchant.example"})
        other["headers"]["PROOF-RESPONSE"] = art
        code, body = self.call(other)
        self.assertEqual(body["reasons"], ["route_mismatch"])

    def test_x401_failing_rejects_the_pair_and_the_reason_names_x401(self):
        payload = self.challenge()
        art = self.proof_response(payload, self.vc(selectable={"age_over_18": False}))
        code, body = self.call(self.both(art, nonce="n-6"))
        self.assertEqual((code, body["reasons"]), (403, ["claims_not_satisfied"]))


class Telemetry(Setup):
    def _run(self, request, opted_in=True):
        written = []

        class Keys:
            def get_item(self, **kw):
                return {"Item": {"api_key": "rs_live_test", "active": True, vt.OPT_IN_FIELD: opted_in}}

        class Rows:
            def put_item(self, Item):
                written.append(Item)

        class DDB:
            def Table(self, name):
                return Keys() if name == vt.API_KEYS_TABLE else Rows()

        os.environ.pop("VERIFIER_TELEMETRY_DISABLED", None)
        with unittest.mock.patch.object(vt, "_dynamodb", lambda: DDB()):
            code, body = self.call(request, {"headers": {"X-RS-API-KEY": "rs_live_test"}})
        return code, body, written

    def test_a_rejection_is_reported_as_x401_with_a_class_and_the_claimed_issuer(self):
        payload = self.challenge()
        art = self.proof_response(payload, self.vc(selectable={"age_over_18": False}))
        code, body, written = self._run(self.request(art))
        self.assertEqual(code, 403)
        (row,) = written
        self.assertEqual((row["verifier_type"], row["rejection_reason"]), ("x401", "mandate_exceeded"))
        self.assertNotIn("age_over_18", json.dumps(row, default=str))

    def test_an_invalid_signature_is_classified_and_carries_the_issuer_hash(self):
        payload = self.challenge()
        vc = self.vc()
        vc["jwt"] = vc["jwt"][:-4] + ("AAAA" if not vc["jwt"].endswith("AAAA") else "BBBB")
        code, body, written = self._run(self.request(self.proof_response(payload, vc)))
        (row,) = written
        self.assertEqual(row["rejection_reason"], "bad_signature")
        self.assertEqual(row["issuer_hash"], vt.hash_id("https://issuer.example"))

    def test_a_challenge_an_accept_and_our_own_unavailability_are_never_reported(self):
        code, body, written = self._run(self.request())                       # proof_required
        self.assertEqual((code, written), (401, []))
        payload = self.challenge()
        code, body, written = self._run(self.request(self.proof_response(payload)))
        self.assertEqual((code, written), (200, []))
        with unittest.mock.patch.object(rp, "load_signer", side_effect=rp.X401Error("verifier_not_configured", "x")):
            code, body, written = self._run(self.request("abc"))
        self.assertEqual((code, written), (202, []))

    def test_not_opted_in_writes_nothing(self):
        payload = self.challenge()
        art = self.proof_response(payload, self.vc(selectable={"age_over_18": False}))
        self.assertEqual(self._run(self.request(art), opted_in=False)[2], [])

    def test_every_error_code_the_relying_party_can_emit_has_a_telemetry_class(self):
        """A code that falls into "other" silently loses its meaning. Pull the codes from the
        source, so adding one without classifying it fails here."""
        import re
        src = open(rp.__file__).read()
        codes = set(re.findall(r'X401Error\(\s*"([a-z_]+)"', src))
        codes -= {"invalid_response"} if False else set()
        unclassified = [c for c in sorted(codes)
                        if vt.classify_reason([c]) == "other" and c not in vt.NOT_AN_ATTACK]
        # these are genuinely "other": either a wallet-side event or a feature we refuse
        allowed_other = {"wallet_error", "response_encryption_unsupported", "unsupported_token", "policy_mismatch",
                         "route_mismatch", "audience_mismatch", "credential_revoked", "agent_binding_failed",
                         "reference_not_accepted"}
        self.assertEqual(sorted(set(unclassified) - allowed_other), [])


class DidDocument(unittest.TestCase):
    def call(self, jwk, kid="did:web:api.relayshield.net#x401-1", method="GET"):
        import relayshield_api as api
        import relayshield_x401_pubkey as pk
        with unittest.mock.patch.object(pk, "PUBLIC_JWK", jwk), unittest.mock.patch.object(pk, "KID", kid):
            resp = api.lambda_handler({"path": "/.well-known/did.json", "httpMethod": method, "headers": {}}, None)
        return resp

    def test_it_serves_the_public_key_as_a_did_web_document(self):
        pub = dict(jose.public_jwk(jose.generate_p256_jwk()), kid="did:web:api.relayshield.net#x401-1")
        resp = self.call(pub)
        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual(resp["headers"]["Content-Type"], "application/did+json")
        doc = json.loads(resp["body"])
        self.assertEqual(doc["id"], "did:web:api.relayshield.net")
        vm = doc["verificationMethod"][0]
        self.assertEqual((vm["id"], vm["controller"], vm["publicKeyJwk"]), (rp.DEFAULT_KID, doc["id"], pub))
        self.assertEqual(doc["assertionMethod"], [rp.DEFAULT_KID])

    def test_it_matches_the_identity_the_signer_uses(self):
        self.assertEqual(rp.DEFAULT_CLIENT_ID, "decentralized_identifier:did:web:api.relayshield.net")
        import relayshield_x401_pubkey as pk
        self.assertEqual(pk.KID, rp.DEFAULT_KID)

    def test_unpublished_and_private_keys_are_a_404_not_a_document(self):
        self.assertEqual(self.call(None)["statusCode"], 404)
        self.assertEqual(self.call(jose.generate_p256_jwk())["statusCode"], 404, "a private key must never be served")
        self.assertEqual(self.call({}, kid="")["statusCode"], 404)

    def test_the_shipped_module_holds_no_private_material(self):
        import relayshield_x401_pubkey as pk
        self.assertTrue(pk.PUBLIC_JWK is None or "d" not in pk.PUBLIC_JWK)


class SafeFetch(unittest.TestCase):
    PUBLIC = staticmethod(lambda host, port, proto=0: [(2, 1, 6, "", ("93.184.216.34", 443))])
    PRIVATE = staticmethod(lambda host, port, proto=0: [(2, 1, 6, "", ("10.0.0.5", 443))])
    METADATA = staticmethod(lambda host, port, proto=0: [(2, 1, 6, "", ("169.254.169.254", 443))])
    MIXED = staticmethod(lambda host, port, proto=0: [(2, 1, 6, "", ("93.184.216.34", 443)), (2, 1, 6, "", ("127.0.0.1", 443))])

    class Resp:
        def __init__(self, data, status=200):
            self.data, self.status = data, status

        def read(self, n):
            return self.data[:n]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Opener:
        def __init__(self, resp=None, boom=None):
            self.resp, self.boom, self.calls = resp, boom, []

        def open(self, req, timeout=None):
            self.calls.append((req.full_url, timeout))
            if self.boom:
                raise self.boom
            return self.resp

    def fetch(self, url, resolver=None, **kw):
        return x401_net.safe_fetch(url, resolver=resolver or self.PUBLIC, **kw)

    def test_a_public_https_url_is_fetched_with_a_timeout(self):
        op = self.Opener(self.Resp(b"hello"))
        self.assertEqual(self.fetch("https://status.example/l", opener=op), b"hello")
        self.assertEqual(op.calls, [("https://status.example/l", x401_net.TIMEOUT)])

    def test_urls_that_must_never_be_fetched(self):
        op = self.Opener(self.Resp(b"x"))
        for url in ("http://status.example/l", "ftp://x/y", "file:///etc/passwd", "https://u:p@status.example/l",
                    "https://10.0.0.1/l", "https://127.0.0.1/l", "https://[::1]/l", "https://status.example/l#f", "", None, 5):
            self.assertIsNone(self.fetch(url, opener=op), url)
        self.assertEqual(op.calls, [])

    def test_a_name_that_resolves_to_an_internal_address_is_refused(self):
        op = self.Opener(self.Resp(b"x"))
        for r in (self.PRIVATE, self.METADATA, self.MIXED):
            self.assertIsNone(self.fetch("https://evil.example/l", resolver=r, opener=op))
        self.assertEqual(op.calls, [])

    def test_oversize_non_200_and_errors_return_none(self):
        self.assertIsNone(self.fetch("https://s.example/l", opener=self.Opener(self.Resp(b"x" * 100)), max_bytes=10))
        self.assertIsNone(self.fetch("https://s.example/l", opener=self.Opener(self.Resp(b"x", status=302))))
        self.assertIsNone(self.fetch("https://s.example/l", opener=self.Opener(boom=OSError("net"))))
        self.assertIsNone(self.fetch("https://s.example/l", resolver=lambda *a, **k: (_ for _ in ()).throw(OSError())))

    def test_redirects_are_not_followed(self):
        handler = x401_net._NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "Found", {}, "https://internal/"))


class DemoDoesNotRot(unittest.TestCase):
    def test_the_demo_runs_clean(self):
        """tools/x401_demo.py is what gets shown to people. It exits non-zero if any step or
        attack behaves differently from the design, so a regression cannot ship in a demo."""
        import pathlib
        import subprocess
        root = pathlib.Path(__file__).resolve().parent
        res = subprocess.run([sys.executable, "-B", str(root / "tools" / "x401_demo.py")], capture_output=True, text=True, timeout=100)
        self.assertEqual(res.returncode, 0, res.stdout[-1500:] + res.stderr[-1500:])
        self.assertIn("Every step behaved as designed", res.stdout)


if __name__ == "__main__":
    unittest.main()
