"""x401 relying party: every path through x401_rp, with real signatures and nothing mocked
except time and the network fetch.

An issuer signs real credentials, a wallet presents them with real key binding, and the
relying party validates them. The negative tests build the specific wrong thing (a forged
nonce, an altered disclosure, a wrong audience) and check the SPECIFIC error code, because
"it was rejected" is satisfied by a verifier that rejects everything.
"""
import copy
import hashlib
import json
import time
import unittest
import zlib

import x401_jose as jose
import x401_rp as rp
import x401_testkit as kit
import relayshield_tap_verifier as tap

VCT = "https://credentials.example/id"
ORIGIN = "https://shop.example"
NOW = 1_800_000_000


def sd_policy(**over):
    p = {"request_id": "proof-age-v1", "satisfied_requirements": ["urn:example:age18"],
         "dcql_query": {"credentials": [{"id": "id_card", "format": "dc+sd-jwt", "meta": {"vct_values": [VCT]},
                                         "claims": [{"path": ["age_over_18"], "values": [True]}]}]},
         "trusted_issuers": ["https://issuer.example"], "expected_origins": [ORIGIN], "ttl_seconds": 600}
    p.update(over)
    return p


class Env:
    def __init__(self, policy=None, issuer_extra=None):
        self.issuer = kit.Issuer("https://issuer.example")
        self.wallet = kit.Wallet()
        self.signer = rp.Signer(jose.generate_p256_jwk())
        self.policy = policy or sd_policy()
        self.policies = {"p": self.policy}
        self.issuers = rp.load_issuers(raw=json.dumps({"issuers": {"https://issuer.example": self.issuer.registry_entry(**(issuer_extra or {}))}}))
        self.store = tap.MemoryNonceStore()

    def challenge(self, route="/buy", method="POST", now=NOW):
        return rp.create_challenge("p", self.policies, route, method, self.signer, now)

    def nonce(self, ch, i=0):
        req = ch["payload"]["credential_requirements"]["digital"]["requests"][i]
        data = req["data"]
        return (jose.jws_payload(data["request"]) if "request" in data else data)["nonce"]

    def vc(self, **kw):
        kw.setdefault("always", {"given_name": "Ada"})
        kw.setdefault("selectable", {"age_over_18": True})
        kw.setdefault("holder", self.wallet.public_jwk)
        kw.setdefault("now", NOW)
        return self.issuer.sd_jwt_vc(VCT, **kw)

    def result(self, ch, vc=None, **kw):
        kw.setdefault("origin", ORIGIN)
        kw.setdefault("now", NOW)
        return self.wallet.fulfil(ch["payload"], {"id_card": vc or self.vc()}, **kw)

    def verify(self, result, now=NOW + 5, route="/buy", method="POST", store="default", **kw):
        art = result if isinstance(result, str) else kit.artifact(result, self.policy.get("request_id"))
        return rp.verify_result(art, policy_id=kw.pop("policy_id", "p"), policies=kw.pop("policies", self.policies),
                                issuers=kw.pop("issuers", self.issuers), route=route, method=method,
                                signer=kw.pop("signer", self.signer),
                                store=self.store if store == "default" else store, now=now, **kw)

    def manual(self, ch, presentations, protocol="openid4vp-v1-signed"):
        return {"protocol": protocol, "data": {"vp_token": {"id_card": presentations}}}


class Case(unittest.TestCase):
    def setUp(self):
        self.e = Env()

    def fails(self, code, result, **kw):
        with self.assertRaises(rp.X401Error) as cm:
            self.e.verify(result, **kw)
        self.assertEqual(cm.exception.code, code, cm.exception.description)
        return cm.exception


class Challenge(Case):
    def test_payload_shape_and_signed_request(self):
        ch = self.e.challenge()
        p = ch["payload"]
        self.assertEqual((p["scheme"], p["version"]), ("x401", "0.2.0"))
        self.assertEqual(p["request_id"], "proof-age-v1")
        self.assertEqual(p["satisfied_requirements"], ["urn:example:age18"])
        self.assertNotIn("oauth", p, "no token exchange is offered, so `oauth` must be omitted")
        (req,) = p["credential_requirements"]["digital"]["requests"]
        self.assertEqual(req["protocol"], "openid4vp-v1-signed")
        hdr, claims = jose.jws_verify(req["data"]["request"], [self.e.signer.public_jwk], {"ES256"}, "oauth-authz-req+jwt")
        self.assertEqual(hdr["kid"], rp.DEFAULT_KID)
        self.assertEqual(claims["client_id"], rp.DEFAULT_CLIENT_ID)
        self.assertEqual(claims["expected_origins"], [ORIGIN])
        self.assertEqual((claims["response_type"], claims["response_mode"]), ("vp_token", "dc_api"))
        self.assertEqual(claims["dcql_query"], self.e.policy["dcql_query"])
        self.assertEqual(claims["exp"], NOW + 600)
        self.assertIn("dc+sd-jwt", claims["client_metadata"]["vp_formats_supported"])
        self.assertNotIn("encryption", json.dumps(claims["client_metadata"]).lower())
        self.assertEqual(jose.b64u_json_decode(ch["header"]), p)

    def test_the_request_is_not_verifiable_with_another_key(self):
        ch = self.e.challenge()
        other = rp.Signer(jose.generate_p256_jwk())
        data = ch["payload"]["credential_requirements"]["digital"]["requests"][0]["data"]
        with self.assertRaises(ValueError):
            jose.jws_verify(data["request"], [other.public_jwk], {"ES256"})

    def test_unsigned_mode_carries_no_client_id_or_origins(self):
        e = Env(sd_policy(mode="unsigned", unsigned_allowed_origins=[ORIGIN]))
        (req,) = e.challenge()["payload"]["credential_requirements"]["digital"]["requests"]
        self.assertEqual(req["protocol"], "openid4vp-v1-unsigned")
        self.assertNotIn("client_id", req["data"])
        self.assertNotIn("expected_origins", req["data"])

    def test_both_mode_offers_two_entries(self):
        e = Env(sd_policy(mode="both", unsigned_allowed_origins=[ORIGIN]))
        reqs = e.challenge()["payload"]["credential_requirements"]["digital"]["requests"]
        self.assertEqual([r["protocol"] for r in reqs], ["openid4vp-v1-signed", "openid4vp-v1-unsigned"])
        self.assertEqual(e.nonce(e.challenge(), 0).split(".")[0] != "", True)

    def test_unknown_policy_and_unconfigured_signer(self):
        with self.assertRaises(rp.X401Error) as cm:
            rp.create_challenge("nope", self.e.policies, "/", "GET", self.e.signer, NOW)
        self.assertEqual(cm.exception.code, "unknown_policy")
        with self.assertRaises(rp.X401Error) as cm:
            rp.load_signer(env={}, fetch_secret=lambda sid: (_ for _ in ()).throw(RuntimeError("no secret")))
        self.assertEqual(cm.exception.code, "verifier_not_configured")

    def test_each_challenge_has_a_fresh_nonce(self):
        self.assertNotEqual(self.e.nonce(self.e.challenge()), self.e.nonce(self.e.challenge()))

    def test_load_signer_reads_env_and_secret_and_refuses_a_public_key(self):
        priv = jose.generate_p256_jwk()
        s = rp.load_signer(env={"X401_SIGNING_JWK": json.dumps(priv)})
        self.assertEqual(s.client_id, rp.DEFAULT_CLIENT_ID)
        s = rp.load_signer(env={}, fetch_secret=lambda sid: json.dumps({"jwk": priv}))
        self.assertEqual(s.public_jwk["x"], priv["x"])
        self.assertNotIn("d", s.public_jwk)
        with self.assertRaises(rp.X401Error):
            rp.load_signer(env={"X401_SIGNING_JWK": json.dumps(jose.public_jwk(priv))})

    def test_error_object_shape(self):
        obj = jose.b64u_json_decode(rp.error_header("invalid_signature", "bad", "rid"))
        self.assertEqual(obj, {"scheme": "x401", "version": "0.2.0", "error": "invalid_signature",
                               "error_description": "bad", "request_id": "rid"})


class SdJwtHappyPath(Case):
    def test_accept_returns_only_the_requested_claims(self):
        ch = self.e.challenge()
        out = self.e.verify(self.e.result(ch))
        self.assertTrue(out["ok"])
        (c,) = out["credentials"]["id_card"]
        self.assertEqual(c["claims"], {"age_over_18": True})
        self.assertEqual(c["issuer"], "https://issuer.example")
        self.assertEqual(out["request_id"], "proof-age-v1")
        self.assertEqual(out["satisfied_requirements"], ["urn:example:age18"])
        self.assertNotIn("given_name", json.dumps(out))

    def test_a_relayed_handler_with_no_origin_binds_to_client_id(self):
        ch = self.e.challenge()
        out = self.e.verify(self.e.result(ch, relay=True, origin=None))
        self.assertTrue(out["ok"])

    def test_array_element_disclosures_and_nested_paths(self):
        pol = sd_policy(dcql_query={"credentials": [{"id": "id_card", "format": "dc+sd-jwt", "meta": {"vct_values": [VCT]},
                                                      "claims": [{"path": ["nationalities", None], "values": ["US"]}]}]})
        e = Env(pol)
        ch = e.challenge()
        vc = e.vc(selectable={}, array_selectable={"nationalities": ["US", "CA"]})
        out = e.verify(e.result(ch, vc))
        self.assertTrue(out["ok"])
        self.assertEqual(out["credentials"]["id_card"][0]["claims"]["nationalities.*"], "US",
                         "only the requested value is returned, not the CA the wallet over-shared")

    def test_decoy_digests_are_ignored(self):
        ch = self.e.challenge()
        self.assertTrue(self.e.verify(self.e.result(ch, self.e.vc(decoys=9)))["ok"])

    def test_verification_is_fast_enough_for_a_request_path(self):
        ch = self.e.challenge()
        res = self.e.result(ch)
        t = time.time()
        self.e.verify(res)
        self.assertLess(time.time() - t, 1.0)


class SdJwtRejections(Case):
    def test_tampered_issuer_signature(self):
        ch = self.e.challenge()
        vc = self.e.vc()
        vc["jwt"] = vc["jwt"][:-4] + ("AAAA" if not vc["jwt"].endswith("AAAA") else "BBBB")
        self.fails("invalid_signature", self.e.result(ch, vc))

    def test_a_credential_signed_by_someone_else_who_claims_to_be_the_issuer(self):
        ch = self.e.challenge()
        impostor = kit.Issuer("https://issuer.example")        # same iss, different key
        vc = impostor.sd_jwt_vc(VCT, selectable={"age_over_18": True}, holder=self.e.wallet.public_jwk, now=NOW)
        self.fails("invalid_signature", self.e.result(ch, vc))

    def test_issuer_not_trusted_by_the_policy(self):
        other = kit.Issuer("https://other.example")
        e = Env()
        e.issuers = rp.load_issuers(raw=json.dumps({"issuers": {
            "https://issuer.example": e.issuer.registry_entry(), "https://other.example": other.registry_entry()}}))
        ch = e.challenge()
        vc = other.sd_jwt_vc(VCT, selectable={"age_over_18": True}, holder=e.wallet.public_jwk, now=NOW)
        with self.assertRaises(rp.X401Error) as cm:
            e.verify(e.result(ch, vc))
        self.assertEqual(cm.exception.code, "untrusted_issuer")

    def test_issuer_in_the_policy_but_with_no_key_in_the_registry(self):
        self.e.issuers = {}
        self.fails("untrusted_issuer", self.e.result(self.e.challenge()))

    def test_expired_not_yet_valid_and_no_expiry(self):
        ch = self.e.challenge()
        self.fails("credential_expired", self.e.result(ch, self.e.vc(exp_delta=-3600)))
        self.fails("credential_not_yet_valid", self.e.result(ch, self.e.vc(nbf_delta=3600)))
        self.fails("credential_expired", self.e.result(ch, self.e.vc(no_exp=True)))

    def test_a_credential_without_exp_can_be_allowed_by_policy(self):
        e = Env(sd_policy(allow_credential_without_exp=True))
        ch = e.challenge()
        self.assertTrue(e.verify(e.result(ch, e.vc(no_exp=True)))["ok"])

    def test_wrong_credential_type(self):
        ch = self.e.challenge()
        vc = self.e.issuer.sd_jwt_vc("https://credentials.example/other", selectable={"age_over_18": True},
                                     holder=self.e.wallet.public_jwk, now=NOW)
        self.fails("credential_type_mismatch", self.e.result(ch, vc))

    def test_value_restrictions_are_enforced_by_us_not_trusted_to_the_wallet(self):
        ch = self.e.challenge()
        self.fails("claims_not_satisfied", self.e.result(ch, self.e.vc(selectable={"age_over_18": False})))

    def test_value_matching_is_type_exact(self):
        """True is not 1, and 1 is not 1.0. A wallet returning a near-miss must not pass."""
        for wrong in (1, "true", "True", 1.0):
            ch = self.e.challenge()
            self.fails("claims_not_satisfied", self.e.result(ch, self.e.vc(selectable={"age_over_18": wrong})))

    def test_a_missing_requested_claim(self):
        ch = self.e.challenge()
        vc = self.e.vc(selectable={})
        self.fails("claims_not_satisfied", self.e.result(ch, vc))

    def test_the_wallet_withholding_a_requested_disclosure(self):
        ch = self.e.challenge()
        self.fails("claims_not_satisfied", self.e.result(ch, disclose={"id_card": []}))

    def test_no_key_binding_jwt(self):
        ch = self.e.challenge()
        vc = self.e.vc()
        pres = self.e.wallet.present_sd_jwt(vc, ["age_over_18"], self.e.nonce(ch), "origin:" + ORIGIN, NOW, drop_kb=True)
        self.fails("holder_binding_failed", self.e.manual(ch, [pres]))

    def test_key_binding_signed_by_a_different_key(self):
        ch = self.e.challenge()
        stranger = jose.generate_p256_jwk()
        pres = self.e.wallet.present_sd_jwt(self.e.vc(), ["age_over_18"], self.e.nonce(ch), "origin:" + ORIGIN, NOW, kb_key=stranger)
        self.fails("holder_binding_failed", self.e.manual(ch, [pres]))

    def test_credential_with_no_holder_key(self):
        ch = self.e.challenge()
        self.fails("holder_binding_failed", self.e.result(ch, self.e.vc(holder=None)))

    def test_wrong_audience(self):
        ch = self.e.challenge()
        for aud in ("origin:https://evil.example", "https://shop.example", "evil", ""):
            pres = self.e.wallet.present_sd_jwt(self.e.vc(), ["age_over_18"], self.e.nonce(ch), aud, NOW)
            self.fails("audience_mismatch", self.e.manual(ch, [pres]))

    def test_a_result_for_a_different_nonce(self):
        ch = self.e.challenge()
        pres = self.e.wallet.present_sd_jwt(self.e.vc(), ["age_over_18"], "not-ours", "origin:" + ORIGIN, NOW)
        self.fails("invalid_nonce", self.e.manual(ch, [pres]))

    def test_a_nonce_from_another_verifier_key_is_refused(self):
        other = rp.Signer(jose.generate_p256_jwk())
        ch = rp.create_challenge("p", self.e.policies, "/buy", "POST", other, NOW)
        res = self.e.wallet.fulfil(ch["payload"], {"id_card": self.e.vc()}, origin=ORIGIN, now=NOW)
        self.fails("invalid_nonce", res)

    def test_a_forged_nonce_state_is_refused(self):
        ch = self.e.challenge()
        body, mac = self.e.nonce(ch).split(".")
        state = jose.b64u_json_decode(body)
        state["t"] = rp._route_tag("/admin", "POST")
        forged = jose.b64u_json(state) + "." + mac
        pres = self.e.wallet.present_sd_jwt(self.e.vc(), ["age_over_18"], forged, "origin:" + ORIGIN, NOW)
        self.fails("invalid_nonce", self.e.manual(ch, [pres]))

    def test_sd_hash_must_cover_this_exact_presentation(self):
        ch = self.e.challenge()
        pres = self.e.wallet.present_sd_jwt(self.e.vc(), ["age_over_18"], self.e.nonce(ch), "origin:" + ORIGIN, NOW,
                                            sd_hash_override=jose.b64u_encode(b"x" * 32))
        self.fails("holder_binding_failed", self.e.manual(ch, [pres]))

    def test_a_disclosure_added_after_the_holder_signed(self):
        ch = self.e.challenge()
        vc = self.e.vc()
        pres = self.e.wallet.present_sd_jwt(vc, ["age_over_18"], self.e.nonce(ch), "origin:" + ORIGIN, NOW)
        extra = jose.b64u_encode(json.dumps(["salt", "extra", 1]).encode())
        head, kb = pres.rsplit("~", 1)
        self.fails("holder_binding_failed", self.e.manual(ch, [head + "~" + extra + "~" + kb]))

    def test_a_disclosure_that_matches_nothing(self):
        ch = self.e.challenge()
        junk = jose.b64u_encode(json.dumps(["salt", "ghost", 1]).encode())
        pres = self.e.wallet.present_sd_jwt(self.e.vc(), ["age_over_18"], self.e.nonce(ch), "origin:" + ORIGIN, NOW,
                                            extra_disclosures=[junk])
        self.fails("invalid_credential", self.e.manual(ch, [pres]))

    def test_the_same_disclosure_sent_twice(self):
        ch = self.e.challenge()
        vc = self.e.vc()
        pres = self.e.wallet.present_sd_jwt(vc, ["age_over_18"], self.e.nonce(ch), "origin:" + ORIGIN, NOW,
                                            extra_disclosures=[vc["disclosures"]["age_over_18"]])
        self.fails("invalid_credential", self.e.manual(ch, [pres]))

    def test_a_disclosure_that_would_overwrite_a_visible_claim(self):
        ch = self.e.challenge()
        vc = self.e.vc(always={"age_over_18": False}, selectable={"age_over_18": True})
        self.fails("invalid_credential", self.e.result(ch, vc))

    def test_unsupported_hash_algorithm(self):
        ch = self.e.challenge()
        self.fails("invalid_credential", self.e.result(ch, self.e.vc(sd_alg="sha-512")))

    def test_key_binding_made_before_the_request_existed(self):
        ch = self.e.challenge()
        pres = self.e.wallet.present_sd_jwt(self.e.vc(), ["age_over_18"], self.e.nonce(ch), "origin:" + ORIGIN, NOW - 3600)
        self.fails("holder_binding_failed", self.e.manual(ch, [pres]))

    def test_key_binding_from_the_future(self):
        ch = self.e.challenge()
        pres = self.e.wallet.present_sd_jwt(self.e.vc(), ["age_over_18"], self.e.nonce(ch), "origin:" + ORIGIN, NOW + 3600)
        self.fails("holder_binding_failed", self.e.manual(ch, [pres]))

    def test_an_alg_none_issuer_jwt_is_refused(self):
        ch = self.e.challenge()
        vc = self.e.vc()
        claims = jose.jws_payload(vc["jwt"])
        vc["jwt"] = f"{jose.b64u_json({'alg': 'none', 'typ': 'dc+sd-jwt'})}.{jose.b64u_json(claims)}."
        self.fails("invalid_signature", self.e.result(ch, vc))

    def test_a_wrong_typ_on_the_credential(self):
        ch = self.e.challenge()
        vc = self.e.vc()
        vc["jwt"] = self.e.issuer.sign(jose.jws_payload(vc["jwt"]), typ="JWT")
        self.fails("invalid_credential", self.e.result(ch, vc))

    def test_junk_instead_of_a_presentation(self):
        ch = self.e.challenge()
        for junk in ("", "not-a-jwt", "a~b", "~~", 5, None, {}, [], "x" * 300_000):
            with self.assertRaises(rp.X401Error):
                self.e.verify(self.e.manual(ch, [junk]))


class Binding(Case):
    def test_wrong_route_method_and_policy(self):
        ch = self.e.challenge("/buy", "POST")
        res = self.e.result(ch)
        self.fails("route_mismatch", res, route="/other")
        self.fails("route_mismatch", res, method="GET")
        self.e.policies["q"] = copy.deepcopy(self.e.policy)
        self.fails("policy_mismatch", res, policy_id="q")

    def test_method_case_does_not_matter_but_the_path_does(self):
        ch = self.e.challenge("/buy", "post")
        self.assertTrue(self.e.verify(self.e.result(ch), method="POST")["ok"])

    def test_an_expired_request(self):
        ch = self.e.challenge()
        self.fails("expired_request", self.e.result(ch), now=NOW + 600 + 120)

    def test_replay_is_refused_and_a_failed_attempt_does_not_burn_the_nonce(self):
        ch = self.e.challenge()
        bad = self.e.result(ch, self.e.vc(selectable={"age_over_18": False}))
        self.fails("claims_not_satisfied", bad)
        good = self.e.result(ch)
        self.assertTrue(self.e.verify(good)["ok"], "the failed attempt must not have consumed the nonce")
        self.fails("replayed_nonce", good)

    def test_a_replay_on_another_container_is_caught_through_a_shared_store(self):
        ch = self.e.challenge()
        res = self.e.result(ch)
        shared = {}

        class Store:
            def seen(self, key, now=None):
                if key in shared:
                    return True
                shared[key] = 1
                return False
        self.e.verify(res, store=Store())
        self.fails("replayed_nonce", res, store=Store())

    def test_unsigned_result_for_a_signed_only_policy(self):
        ch = self.e.challenge()
        res = self.e.result(ch)
        res["protocol"] = "openid4vp-v1-unsigned"
        self.fails("unsupported_protocol", res)

    def test_unsigned_mode_accepts_only_declared_origins(self):
        e = Env(sd_policy(mode="unsigned", unsigned_allowed_origins=[ORIGIN]))
        ch = e.challenge()
        self.assertTrue(e.verify(e.wallet.fulfil(ch["payload"], {"id_card": e.vc()}, origin=ORIGIN, now=NOW))["ok"])
        ch = e.challenge()
        res = e.wallet.fulfil(ch["payload"], {"id_card": e.vc()}, origin="https://evil.example", now=NOW)
        with self.assertRaises(rp.X401Error) as cm:
            e.verify(res)
        self.assertEqual(cm.exception.code, "audience_mismatch")

    def test_client_id_is_not_an_acceptable_audience_for_an_unsigned_result(self):
        e = Env(sd_policy(mode="unsigned", unsigned_allowed_origins=[ORIGIN]))
        ch = e.challenge()
        res = e.wallet.fulfil(ch["payload"], {"id_card": e.vc()}, origin=ORIGIN, now=NOW, aud_override=e.signer.client_id)
        with self.assertRaises(rp.X401Error) as cm:
            e.verify(res)
        self.assertEqual(cm.exception.code, "audience_mismatch")

    def test_agent_binding(self):
        e = Env(sd_policy(bind_agent=True))
        ch = e.challenge()
        art = lambda aid: kit.artifact(e.result(ch), "proof-age-v1", aid)  # noqa: E731
        with self.assertRaises(rp.X401Error) as cm:
            e.verify(art(None))                                         # nobody authenticated
        self.assertEqual(cm.exception.code, "agent_binding_failed")
        with self.assertRaises(rp.X401Error) as cm:
            e.verify(art("agent-B"), agent_id="agent-A")                # artifact names someone else
        self.assertEqual(cm.exception.code, "agent_binding_failed")
        out = e.verify(art("agent-A"), agent_id="agent-A")
        self.assertEqual(out["agent_id"], "agent-A")

    def test_a_mismatched_agent_id_is_refused_even_when_binding_is_off(self):
        ch = self.e.challenge()
        with self.assertRaises(rp.X401Error) as cm:
            self.e.verify(kit.artifact(self.e.result(ch), None, "agent-B"), agent_id="agent-A")
        self.assertEqual(cm.exception.code, "agent_binding_failed")


class ArtifactHandling(Case):
    def test_malformed_artifacts(self):
        for bad in ("", "   ", "!!!", "a,b", jose.b64u_json([1]), jose.b64u_json({}), "x" * 300_000, None, 5,
                    jose.b64u_json({"credential_result": {}, "credential_result_uri": "https://x"})):
            with self.assertRaises(rp.X401Error) as cm:
                self.e.verify(bad)
            self.assertIn(cm.exception.code, ("invalid_response", "unsupported_protocol"))

    def test_a_verification_token_object_is_not_accepted(self):
        tok = jose.b64u_json({"scheme": "x401", "version": "0.2.0", "token_type": "Bearer", "access_token": "x"})
        self.fails("unsupported_token", tok)

    def test_wallet_error_and_encrypted_responses(self):
        ch = self.e.challenge()
        self.fails("wallet_error", {"protocol": "openid4vp-v1-signed", "data": {"error": "access_denied"}})
        self.fails("response_encryption_unsupported", {"protocol": "openid4vp-v1-signed", "data": {"response": "eyJ..."}})

    def test_vp_token_structure(self):
        ch = self.e.challenge()
        pres = self.e.wallet.present_sd_jwt(self.e.vc(), ["age_over_18"], self.e.nonce(ch), "origin:" + ORIGIN, NOW)
        for bad in ({}, {"unknown": [pres]}, {"id_card": pres}, {"id_card": []}, {"id_card": [pres, pres]}, "x", []):
            self.fails("invalid_response", {"protocol": "openid4vp-v1-signed", "data": {"vp_token": bad}})

    def test_data_may_arrive_as_a_json_string(self):
        ch = self.e.challenge()
        res = self.e.result(ch)
        res["data"] = json.dumps(res["data"])
        self.assertTrue(self.e.verify(res)["ok"])

    def test_result_by_reference(self):
        e = Env(sd_policy(result_uri_prefixes=["https://results.relayshield.net/x401/"]))
        ch = e.challenge()
        res = e.result(ch)
        uri = "https://results.relayshield.net/x401/abc123"
        art = jose.b64u_json({"request_id": "proof-age-v1", "credential_result_uri": uri})
        fetched = []
        fetch = lambda u: (fetched.append(u), json.dumps(res).encode())[1]  # noqa: E731
        self.assertTrue(e.verify(art, fetch=fetch)["ok"])
        self.assertEqual(fetched, [uri])
        ch2 = e.challenge()
        res2 = e.result(ch2)
        with self.assertRaises(rp.X401Error) as cm:                  # the same reference, a new result
            e.verify(art, fetch=lambda u: json.dumps(res2).encode())
        self.assertEqual(cm.exception.code, "replayed_nonce")

    def test_references_to_unrecognised_hosts_are_never_fetched(self):
        e = Env(sd_policy(result_uri_prefixes=["https://results.relayshield.net/x401/"]))
        fetched = []
        for uri in ("https://evil.example/x", "http://results.relayshield.net/x401/a", "https://results.relayshield.net.evil.example/x401/a",
                    "file:///etc/passwd", "https://169.254.169.254/latest", 5, None):
            art = jose.b64u_json({"credential_result_uri": uri})
            with self.assertRaises(rp.X401Error) as cm:
                e.verify(art, fetch=lambda u: fetched.append(u) or b"{}")
            self.assertEqual(cm.exception.code, "reference_not_accepted")
        self.assertEqual(fetched, [])

    def test_no_prefixes_configured_means_no_references(self):
        art = jose.b64u_json({"credential_result_uri": "https://results.relayshield.net/x401/abc"})
        self.fails("reference_not_accepted", art)

    def test_reference_fetch_failures(self):
        e = Env(sd_policy(result_uri_prefixes=["https://r.example/"]))
        art = jose.b64u_json({"credential_result_uri": "https://r.example/a"})
        for payload in (None, b"", b"not json", b"x" * (rp.MAX_RESULT_BYTES + 1)):
            with self.assertRaises(rp.X401Error) as cm:
                e.verify(art, fetch=lambda u, p=payload: p)
            self.assertIn(cm.exception.code, ("reference_unavailable", "invalid_response"))


class DcqlSemantics(Case):
    def _two_credential_env(self, credential_sets=None):
        q = {"credentials": [
            {"id": "id_card", "format": "dc+sd-jwt", "meta": {"vct_values": [VCT]}, "claims": [{"path": ["age_over_18"], "values": [True]}]},
            {"id": "licence", "format": "dc+sd-jwt", "meta": {"vct_values": ["https://credentials.example/licence"]}, "claims": [{"path": ["class"]}]}]}
        if credential_sets:
            q["credential_sets"] = credential_sets
        e = Env(sd_policy(dcql_query=q))
        return e

    def test_every_credential_is_required_without_credential_sets(self):
        e = self._two_credential_env()
        ch = e.challenge()
        with self.assertRaises(rp.X401Error):
            e.verify(e.wallet.fulfil(ch["payload"], {"id_card": e.vc()}, origin=ORIGIN, now=NOW))
        lic = e.issuer.sd_jwt_vc("https://credentials.example/licence", selectable={"class": "B"}, holder=e.wallet.public_jwk, now=NOW)
        ch = e.challenge()
        out = e.verify(e.wallet.fulfil(ch["payload"], {"id_card": e.vc(), "licence": lic}, origin=ORIGIN, now=NOW))
        self.assertEqual(set(out["credentials"]), {"id_card", "licence"})

    def test_credential_sets_options(self):
        e = self._two_credential_env([{"options": [["id_card"], ["licence"]]}])
        lic = e.issuer.sd_jwt_vc("https://credentials.example/licence", selectable={"class": "B"}, holder=e.wallet.public_jwk, now=NOW)
        ch = e.challenge()
        self.assertTrue(e.verify(e.wallet.fulfil(ch["payload"], {"licence": lic}, origin=ORIGIN, now=NOW))["ok"])
        ch = e.challenge()
        self.assertTrue(e.verify(e.wallet.fulfil(ch["payload"], {"id_card": e.vc()}, origin=ORIGIN, now=NOW))["ok"])

    def test_claim_sets_accept_any_one_listed_combination(self):
        q = {"credentials": [{"id": "id_card", "format": "dc+sd-jwt", "meta": {"vct_values": [VCT]},
                              "claims": [{"id": "a", "path": ["age_over_18"], "values": [True]},
                                         {"id": "b", "path": ["birthdate"]}],
                              "claim_sets": [["a"], ["b"]]}]}
        e = Env(sd_policy(dcql_query=q))
        ch = e.challenge()
        self.assertTrue(e.verify(e.result(ch, e.vc(selectable={"birthdate": "1990-01-01"})))["ok"])
        ch = e.challenge()
        self.assertTrue(e.verify(e.result(ch, e.vc(selectable={"age_over_18": True})))["ok"])
        ch = e.challenge()
        with self.assertRaises(rp.X401Error):
            e.verify(e.result(ch, e.vc(selectable={"unrelated": 1})))

    def test_multiple_true_allows_several_presentations(self):
        q = {"credentials": [{"id": "id_card", "format": "dc+sd-jwt", "multiple": True, "meta": {"vct_values": [VCT]},
                              "claims": [{"path": ["age_over_18"], "values": [True]}]}]}
        e = Env(sd_policy(dcql_query=q))
        ch = e.challenge()
        nonce = e.nonce(ch)
        p1 = e.wallet.present_sd_jwt(e.vc(), ["age_over_18"], nonce, "origin:" + ORIGIN, NOW)
        p2 = e.wallet.present_sd_jwt(e.vc(), ["age_over_18"], nonce, "origin:" + ORIGIN, NOW)
        self.assertEqual(len(e.verify(e.manual(ch, [p1, p2]))["credentials"]["id_card"]), 2)

    def test_credentials_presented_by_two_different_holders_are_refused(self):
        q = {"credentials": [{"id": "id_card", "format": "dc+sd-jwt", "multiple": True, "meta": {"vct_values": [VCT]},
                              "claims": [{"path": ["age_over_18"], "values": [True]}]}]}
        e = Env(sd_policy(dcql_query=q))
        ch = e.challenge()
        w2 = kit.Wallet()
        nonce = e.nonce(ch)
        p1 = e.wallet.present_sd_jwt(e.vc(), ["age_over_18"], nonce, "origin:" + ORIGIN, NOW)
        p2 = w2.present_sd_jwt(e.vc(holder=w2.public_jwk), ["age_over_18"], nonce, "origin:" + ORIGIN, NOW)
        with self.assertRaises(rp.X401Error) as cm:
            e.verify(e.manual(ch, [p1, p2]))
        self.assertEqual(cm.exception.code, "holder_binding_failed")

    def test_a_bad_presentation_is_discarded_but_a_good_one_can_still_satisfy_the_query(self):
        q = {"credentials": [{"id": "id_card", "format": "dc+sd-jwt", "multiple": True, "meta": {"vct_values": [VCT]},
                              "claims": [{"path": ["age_over_18"], "values": [True]}]}]}
        e = Env(sd_policy(dcql_query=q))
        ch = e.challenge()
        nonce = e.nonce(ch)
        bad = e.wallet.present_sd_jwt(e.vc(selectable={"age_over_18": False}), ["age_over_18"], nonce, "origin:" + ORIGIN, NOW)
        good = e.wallet.present_sd_jwt(e.vc(), ["age_over_18"], nonce, "origin:" + ORIGIN, NOW)
        out = e.verify(e.manual(ch, [bad, good]))
        self.assertEqual(len(out["credentials"]["id_card"]), 1)

    def test_every_presentation_must_carry_the_requests_nonce_not_just_the_first(self):
        """The nonce is read from the first presentation to find our state, so the others
        need their own check: a stale presentation from an OLDER challenge, perfectly signed,
        must not ride along with a fresh one."""
        q = {"credentials": [{"id": "id_card", "format": "dc+sd-jwt", "multiple": True, "meta": {"vct_values": [VCT]},
                              "claims": [{"path": ["age_over_18"], "values": [True]}]}]}
        e = Env(sd_policy(dcql_query=q))
        old_nonce = e.nonce(e.challenge(now=NOW - 30))        # a real, validly issued nonce
        ch = e.challenge()
        fresh = e.wallet.present_sd_jwt(e.vc(), ["age_over_18"], e.nonce(ch), "origin:" + ORIGIN, NOW)
        stale = e.wallet.present_sd_jwt(e.vc(), ["age_over_18"], old_nonce, "origin:" + ORIGIN, NOW)
        out = e.verify(e.manual(ch, [fresh, stale]))
        self.assertEqual(len(out["credentials"]["id_card"]), 1, "the stale presentation must be discarded")
        ch = e.challenge()
        fresh = e.wallet.present_sd_jwt(e.vc(), ["age_over_18"], e.nonce(ch), "origin:" + ORIGIN, NOW)
        with self.assertRaises(rp.X401Error) as cm:            # and alone it is refused with the right code
            e.verify(e.manual(ch, [fresh.replace(fresh.rsplit("~", 1)[1], e.wallet.present_sd_jwt(
                e.vc(), ["age_over_18"], old_nonce, "origin:" + ORIGIN, NOW).rsplit("~", 1)[1])]))
        self.assertIn(cm.exception.code, ("holder_binding_failed", "invalid_nonce"))

    def test_claims_path_pointer_semantics(self):
        root = {"a": {"b": [10, 20, {"c": 1}]}, "s": "x"}
        self.assertEqual(rp.select_claims(root, ["a", "b", 1]), [20])
        self.assertEqual(rp.select_claims(root, ["a", "b", None]), [10, 20, {"c": 1}])
        self.assertEqual(rp.select_claims(root, ["a", "b", 2, "c"]), [1])
        for bad in (["zz"], ["a", "b", 9], ["s", "x"], ["a", "b", "k"], ["a", 0], ["a", "b", True], ["a", "b", -1]):
            with self.assertRaises(ValueError):
                rp.select_claims(root, bad)


class PolicyAndRegistry(unittest.TestCase):
    def test_unsupported_formats_are_refused_not_ignored(self):
        for fmt in ("mso_mdoc", "ldp_vc", "made_up"):
            p = sd_policy()
            p["dcql_query"]["credentials"][0]["format"] = fmt
            with self.assertRaises(ValueError) as cm:
                rp.validate_policy("p", p)
            self.assertIn("not supported", str(cm.exception))

    def test_holder_binding_cannot_be_switched_off(self):
        p = sd_policy()
        p["dcql_query"]["credentials"][0]["require_cryptographic_holder_binding"] = False
        with self.assertRaises(ValueError):
            rp.validate_policy("p", p)

    def test_each_structural_error_is_caught(self):
        def mutated(fn):
            p = sd_policy()
            fn(p)
            return p
        cases = [
            lambda p: p.pop("trusted_issuers"), lambda p: p.update(trusted_issuers=[]), lambda p: p.pop("expected_origins"),
            lambda p: p.update(expected_origins=["http://shop.example"]), lambda p: p.update(ttl_seconds=5),
            lambda p: p.update(ttl_seconds=True), lambda p: p.update(mode="sideways"), lambda p: p.update(mode="unsigned"),
            lambda p: p["dcql_query"].update(credentials=[]),
            lambda p: p["dcql_query"]["credentials"][0].update(id="bad id!"),
            lambda p: p["dcql_query"]["credentials"][0].pop("meta"),
            lambda p: p["dcql_query"]["credentials"][0].update(meta={}),
            lambda p: p["dcql_query"]["credentials"][0].update(claims=[{"path": []}]),
            lambda p: p["dcql_query"]["credentials"][0].update(claims=[{"path": [1.5]}]),
            lambda p: p["dcql_query"]["credentials"][0].update(claims=[{"path": ["a"], "values": []}]),
            lambda p: p["dcql_query"].update(credential_sets=[{"options": [["ghost"]]}]),
            lambda p: p["dcql_query"]["credentials"][0].update(claim_sets=[["x"]]),
        ]
        for fn in cases:
            with self.assertRaises(ValueError):
                rp.validate_policy("p", mutated(fn))
        rp.validate_policy("p", sd_policy())

    def test_a_broken_policy_is_dropped_not_loaded_weaker(self):
        good, bad = sd_policy(), sd_policy()
        bad.pop("trusted_issuers")
        got = rp.load_policies(raw=json.dumps({"policies": {"good": good, "bad": bad}}))
        self.assertEqual(set(got), {"good"})
        self.assertEqual(rp.load_policies(raw="not json"), {})
        self.assertEqual(rp.load_policies(raw=""), rp.load_policies(raw="", path="/nonexistent"))

    def test_the_shipped_policy_and_registry_files_load(self):
        self.assertIsInstance(rp.load_policies(), dict)
        self.assertIsInstance(rp.load_issuers(), dict)

    def test_registry_refuses_private_keys_and_junk(self):
        iss = kit.Issuer("https://i.example")
        doc = {"issuers": {"good": iss.registry_entry(), "private": {"jwks": [iss.private_jwk]},
                           "junk": "text", "empty": {"jwks": []}, "bad_curve": {"kty": "EC", "crv": "P-256", "x": "AA", "y": "AA"}}}
        self.assertEqual(set(rp.load_issuers(raw=json.dumps(doc))), {"good"})

    def test_registry_only_keeps_https_status_prefixes(self):
        iss = kit.Issuer("https://i.example")
        got = rp.load_issuers(raw=json.dumps({"issuers": {"i": iss.registry_entry(
            status_uri_prefixes=["https://s.example/", "http://s.example/", 5])}}))
        self.assertEqual(got["i"]["status_uri_prefixes"], ["https://s.example/"])


class TokenStatusList(Case):
    URI = "https://status.issuer.example/lists/1"

    def _list(self, e, revoked=(), bits=1, size=64, uri=None, exp_delta=3600, key=None, bomb=False):
        data = bytearray(size)
        for idx in revoked:
            per = 8 // bits
            data[idx // per] |= (1 << bits) - 1 << ((idx % per) * bits)
        raw = bytes(10_000_000) if bomb else bytes(data)
        payload = {"sub": uri or self.URI, "iat": NOW, "exp": NOW + exp_delta,
                   "status_list": {"bits": bits, "lst": jose.b64u_encode(zlib.compress(raw))}}
        signer = key or e.issuer
        return signer.sign(payload, typ="statuslist+jwt").encode()

    def _env(self, **pol):
        return Env(sd_policy(**pol), issuer_extra={"status_uri_prefixes": ["https://status.issuer.example/"]})

    def _vc(self, e, idx=5, uri=None):
        return e.vc(status={"status_list": {"idx": idx, "uri": uri or self.URI}})

    def test_a_valid_credential_passes_and_a_revoked_one_does_not(self):
        e = self._env()
        ch = e.challenge()
        fetch = lambda u: self._list(e, revoked=(9,))  # noqa: E731
        self.assertTrue(e.verify(e.result(ch, self._vc(e, 5)), fetch=fetch)["ok"])
        ch = e.challenge()
        with self.assertRaises(rp.X401Error) as cm:
            e.verify(e.result(ch, self._vc(e, 9)), fetch=fetch)
        self.assertEqual(cm.exception.code, "credential_revoked")

    def test_multi_bit_lists(self):
        e = self._env()
        ch = e.challenge()
        with self.assertRaises(rp.X401Error) as cm:
            e.verify(e.result(ch, self._vc(e, 3)), fetch=lambda u: self._list(e, revoked=(3,), bits=2))
        self.assertEqual(cm.exception.code, "credential_revoked")

    def test_failures_are_closed_not_open(self):
        e = self._env()
        for label, fetch in (("none", lambda u: None), ("garbage", lambda u: b"junk"),
                             ("other key", lambda u: self._list(e, key=kit.Issuer("https://issuer.example"))),
                             ("wrong sub", lambda u: self._list(e, uri="https://status.issuer.example/lists/2")),
                             ("expired", lambda u: self._list(e, exp_delta=-3600)),
                             ("index beyond list", lambda u: self._list(e, size=0)),
                             ("zip bomb", lambda u: self._list(e, bomb=True)), ("no fetcher", None)):
            ch = e.challenge()
            with self.assertRaises(rp.X401Error, msg=label) as cm:
                e.verify(e.result(ch, self._vc(e, 5)), fetch=fetch)
            self.assertEqual(cm.exception.code, "status_unavailable", label)

    def test_the_status_uri_must_be_registered_for_the_issuer(self):
        e = self._env()
        fetched = []
        for uri in ("https://evil.example/list", "http://status.issuer.example/lists/1",
                    "https://status.issuer.example.evil.example/x"):
            ch = e.challenge()
            with self.assertRaises(rp.X401Error) as cm:
                e.verify(e.result(ch, self._vc(e, 5, uri=uri)), fetch=lambda u: fetched.append(u) or b"")
            self.assertEqual(cm.exception.code, "status_unavailable")
        self.assertEqual(fetched, [])

    def test_a_malformed_status_claim_is_refused(self):
        e = self._env()
        for status in ({"status_list": {"idx": -1, "uri": self.URI}}, {"status_list": {"idx": True, "uri": self.URI}},
                       {"status_list": {"idx": 1}}, {"other": 1}, {"status_list": "x"}):
            ch = e.challenge()
            with self.assertRaises(rp.X401Error) as cm:
                e.verify(e.result(ch, e.vc(status=status)), fetch=lambda u: self._list(e))
            self.assertEqual(cm.exception.code, "status_unavailable")

    def test_no_status_claim_means_nothing_to_check(self):
        e = self._env()
        ch = e.challenge()
        self.assertTrue(e.verify(e.result(ch), fetch=lambda u: self.fail("must not fetch"))["ok"])

    def test_ignore_is_an_explicit_policy_choice(self):
        e = Env(sd_policy(status="ignore"))
        ch = e.challenge()
        self.assertTrue(e.verify(e.result(ch, self._vc(e, 5)))["ok"])


class JwtVc(Case):
    def setUp(self):
        q = {"credentials": [{"id": "id_card", "format": "jwt_vc_json",
                              "meta": {"type_values": ["FinancialCustomerCredential"]},
                              "claims": [{"path": ["credentialSubject", "assurance_level"], "values": ["VC-AL2", "VC-AL3"]}]}]}
        self.e = Env(sd_policy(dcql_query=q))

    def vc_jwt(self, level="VC-AL2", types=("FinancialCustomerCredential",), bind="did", **kw):
        return self.e.issuer.vc_jwt(types, {"assurance_level": level},
                                    holder_did=self.e.wallet.did if bind in ("did", "both") else None,
                                    holder_jwk=self.e.wallet.public_jwk if bind in ("cnf", "both") else None, now=NOW, **kw)

    def go(self, vcs, ch=None, **pkw):
        ch = ch or self.e.challenge()
        nonce = self.e.nonce(ch)
        pres = self.e.wallet.present_vc_jwt(vcs, pkw.pop("nonce", nonce), pkw.pop("aud", "origin:" + ORIGIN), NOW, **pkw)
        return self.e.verify(self.e.manual(ch, [pres]))

    def test_the_spec_example_query_is_satisfied(self):
        out = self.go([self.vc_jwt()])
        self.assertEqual(out["credentials"]["id_card"][0]["claims"], {"credentialSubject.assurance_level": "VC-AL2"})

    def test_through_the_wallet_simulator(self):
        ch = self.e.challenge()
        res = self.e.wallet.fulfil(ch["payload"], {"id_card": [self.vc_jwt("VC-AL3")]}, origin=ORIGIN, now=NOW)
        self.assertTrue(self.e.verify(res)["ok"])

    def test_binding_by_cnf_jwk_works_too(self):
        self.assertTrue(self.go([self.vc_jwt(bind="cnf")])["ok"])

    def test_a_credential_not_bound_to_the_presenting_holder(self):
        other = kit.Wallet()
        stolen = self.e.issuer.vc_jwt(("FinancialCustomerCredential",), {"assurance_level": "VC-AL2"},
                                      holder_did=other.did, now=NOW)
        with self.assertRaises(rp.X401Error) as cm:
            self.go([stolen])
        self.assertEqual(cm.exception.code, "holder_binding_failed")

    def test_assurance_level_not_in_the_allowed_values(self):
        with self.assertRaises(rp.X401Error) as cm:
            self.go([self.vc_jwt("VC-AL1")])
        self.assertEqual(cm.exception.code, "claims_not_satisfied")

    def test_wrong_type(self):
        with self.assertRaises(rp.X401Error) as cm:
            self.go([self.vc_jwt(types=("SomethingElse",))])
        self.assertEqual(cm.exception.code, "credential_type_mismatch")

    def test_wrong_nonce_audience_and_signature(self):
        for kw, code in (({"nonce": "nope"}, "invalid_nonce"), ({"aud": "origin:https://evil.example"}, "audience_mismatch")):
            with self.assertRaises(rp.X401Error) as cm:
                self.go([self.vc_jwt()], **kw)
            self.assertEqual(cm.exception.code, code)
        with self.assertRaises(rp.X401Error) as cm:
            self.go([self.vc_jwt()], key=jose.generate_p256_jwk())     # VP signed by a key that is not the holder's
        self.assertEqual(cm.exception.code, "holder_binding_failed")

    def test_untrusted_issuer_and_tampered_credential(self):
        rogue = kit.Issuer("https://rogue.example")
        bad = rogue.vc_jwt(("FinancialCustomerCredential",), {"assurance_level": "VC-AL2"}, holder_did=self.e.wallet.did, now=NOW)
        with self.assertRaises(rp.X401Error) as cm:
            self.go([bad])
        self.assertEqual(cm.exception.code, "untrusted_issuer")
        good = self.vc_jwt()
        with self.assertRaises(rp.X401Error) as cm:
            self.go([good[:-4] + ("AAAA" if not good.endswith("AAAA") else "BBBB")])
        self.assertEqual(cm.exception.code, "invalid_signature")

    def test_an_expired_credential(self):
        with self.assertRaises(rp.X401Error) as cm:
            self.go([self.vc_jwt(exp_delta=-3600)])
        self.assertEqual(cm.exception.code, "credential_expired")

    def test_a_vp_with_no_credentials_or_too_many(self):
        for vcs in ([], [self.vc_jwt()] * 6):
            with self.assertRaises(rp.X401Error):
                self.go(vcs)

    def test_a_holder_that_is_not_an_offline_did(self):
        with self.assertRaises(rp.X401Error) as cm:
            self.go([self.vc_jwt()], header_extra={"kid": "did:web:evil.example#k"}, payload_extra={"iss": "did:web:evil.example"})
        self.assertEqual(cm.exception.code, "holder_binding_failed")

    def test_replay(self):
        ch = self.e.challenge()
        self.go([self.vc_jwt()], ch)
        with self.assertRaises(rp.X401Error) as cm:
            self.go([self.vc_jwt()], ch)
        self.assertEqual(cm.exception.code, "replayed_nonce")


class Errors(Case):
    def test_errors_carry_the_claimed_issuer_for_telemetry_but_are_marked_unverified(self):
        ch = self.e.challenge()
        vc = self.e.vc()
        vc["jwt"] = vc["jwt"][:-4] + ("AAAA" if not vc["jwt"].endswith("AAAA") else "BBBB")
        exc = self.fails("invalid_signature", self.e.result(ch, vc))
        self.assertEqual(exc.issuer, "https://issuer.example")
        self.assertEqual(exc.request_id, "proof-age-v1")

    def test_descriptions_do_not_echo_credential_contents(self):
        ch = self.e.challenge()
        exc = self.fails("claims_not_satisfied", self.e.result(ch, self.e.vc(always={"given_name": "SECRETNAME"}, selectable={"age_over_18": False})))
        self.assertNotIn("SECRETNAME", exc.description)
        self.assertNotIn("SECRETNAME", rp.error_header(exc.code, exc.description))


if __name__ == "__main__":
    unittest.main()
