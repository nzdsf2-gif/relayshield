"""x401_testkit -- an issuer, a wallet and a "Credential Manager", for tests and demos.

NOT DEPLOYED. It signs real credentials (pure-stdlib ES256 from x401_jose) so the relying
party in x401_rp.py is exercised end to end with nothing mocked. It is also what
tools/x401_demo.py uses, so the full flow can be shown without a wallet app.

    issuer = Issuer("https://issuer.example")
    wallet = Wallet()
    vc = issuer.sd_jwt_vc("https://credentials.example/id", always={"given_name": "Ada"},
                          selectable={"age_over_18": True}, holder=wallet.public_jwk)
    result = wallet.fulfil(payload, {"id_card": vc}, origin="https://shop.example")

`fulfil` behaves the way a conforming Credential Manager does: it reads the (signed)
request, checks its signature against the verifier's key, binds the response to the
request's nonce and to the origin, and returns the `{protocol, data}` result.
"""

import hashlib
import json
import os
import time

import x401_jose as jose


def _salt():
    return jose.b64u_encode(os.urandom(16))


class Issuer:
    def __init__(self, iss, kid="issuer-key-1"):
        self.iss, self.kid = iss, kid
        self.private_jwk = jose.generate_p256_jwk()
        self.private_jwk["kid"] = kid
        self.public_jwk = dict(jose.public_jwk(self.private_jwk), kid=kid)

    def registry_entry(self, **extra):
        entry = {"jwks": [self.public_jwk]}
        entry.update(extra)
        return entry

    def sign(self, payload, typ="dc+sd-jwt", alg_header=None, kid=None):
        hdr = {"typ": typ, "kid": kid or self.kid}
        tok = jose.jws_sign_es256(self.private_jwk, hdr, payload)
        return tok

    def sd_jwt_vc(self, vct, always=None, selectable=None, array_selectable=None, holder=None,
                  now=None, exp_delta=3600, nbf_delta=None, status=None, no_exp=False,
                  sd_alg=None, extra_payload=None, decoys=2):
        """-> {"jwt": issuer_jwt, "disclosures": {name: disclosure_string, ...}, "claims": {...}}"""
        now = int(now if now is not None else time.time())
        payload = {"iss": self.iss, "iat": now, "vct": vct}
        if not no_exp:
            payload["exp"] = now + exp_delta
        if nbf_delta is not None:
            payload["nbf"] = now + nbf_delta
        if holder is not None:
            payload["cnf"] = {"jwk": holder}
        if status is not None:
            payload["status"] = status
        payload.update(always or {})
        digests, disclosures = [], {}
        for name, value in (selectable or {}).items():
            d = jose.b64u_encode(json.dumps([_salt(), name, value]).encode())
            disclosures[name] = d
            digests.append(jose.b64u_encode(hashlib.sha256(d.encode()).digest()))
        for name, items in (array_selectable or {}).items():
            elems = []
            for i, item in enumerate(items):
                d = jose.b64u_encode(json.dumps([_salt(), item]).encode())
                disclosures[f"{name}[{i}]"] = d
                elems.append({"...": jose.b64u_encode(hashlib.sha256(d.encode()).digest())})
            payload[name] = elems
        for _ in range(decoys):
            digests.append(jose.b64u_encode(hashlib.sha256(os.urandom(16)).digest()))
        if digests:
            payload["_sd"] = sorted(digests)
        payload["_sd_alg"] = sd_alg or "sha-256"
        payload.update(extra_payload or {})
        return {"jwt": self.sign(payload), "disclosures": disclosures, "claims": payload}

    def vc_jwt(self, types, subject_claims, holder_did=None, holder_jwk=None, now=None, exp_delta=3600):
        now = int(now if now is not None else time.time())
        subject = dict(subject_claims)
        if holder_did:
            subject["id"] = holder_did
        payload = {"iss": self.iss, "nbf": now, "exp": now + exp_delta, "jti": jose.b64u_encode(os.urandom(8)),
                   "vc": {"@context": ["https://www.w3.org/2018/credentials/v1"],
                          "type": ["VerifiableCredential"] + list(types), "credentialSubject": subject}}
        if holder_did:
            payload["sub"] = holder_did
        if holder_jwk:
            payload["cnf"] = {"jwk": holder_jwk}
        return self.sign(payload, typ="JWT")


class Wallet:
    def __init__(self):
        self.private_jwk = jose.generate_p256_jwk()
        self.public_jwk = jose.public_jwk(self.private_jwk)
        self.did = "did:jwk:" + jose.b64u_json(self.public_jwk)

    # ---- presentations -------------------------------------------------------------
    def present_sd_jwt(self, vc, disclose, nonce, aud, now=None, sd_hash_override=None, kb_extra=None,
                       drop_kb=False, kb_key=None, extra_disclosures=()):
        parts = [vc["jwt"]] + [vc["disclosures"][n] for n in disclose] + list(extra_disclosures)
        sd_part = "~".join(parts) + "~"
        if drop_kb:
            return sd_part
        kb_payload = {"iat": int(now if now is not None else time.time()), "aud": aud, "nonce": nonce,
                      "sd_hash": sd_hash_override or jose.b64u_encode(hashlib.sha256(sd_part.encode()).digest())}
        kb_payload.update(kb_extra or {})
        kb = jose.jws_sign_es256(kb_key or self.private_jwk, {"typ": "kb+jwt"}, kb_payload)
        return sd_part + kb

    def present_vc_jwt(self, vc_jwts, nonce, aud, now=None, key=None, header_extra=None, payload_extra=None):
        payload = {"iss": self.did, "aud": aud, "nonce": nonce, "iat": int(now if now is not None else time.time()),
                   "vp": {"@context": ["https://www.w3.org/2018/credentials/v1"], "type": ["VerifiablePresentation"],
                          "verifiableCredential": list(vc_jwts)}}
        payload.update(payload_extra or {})
        hdr = {"typ": "JWT", "kid": self.did + "#0"}
        hdr.update(header_extra or {})
        return jose.jws_sign_es256(key or self.private_jwk, hdr, payload)

    # ---- the Credential Manager ----------------------------------------------------
    def fulfil(self, x401_payload, credentials, origin=None, verifier_public_jwk=None, protocol_index=0,
               disclose=None, now=None, relay=False, aud_override=None):
        """Behave like a conforming Credential Manager for entry `protocol_index`.

        credentials: {dcql credential id: sd-jwt vc dict | list of vc-jwt strings}
        disclose:    {dcql credential id: [claim names to disclose]}; default = everything
        relay:       True = a remote handler with no invoking origin (audience = client_id)."""
        entry = x401_payload["credential_requirements"]["digital"]["requests"][protocol_index]
        protocol, data = entry["protocol"], entry["data"]
        if protocol == "openid4vp-v1-signed":
            if verifier_public_jwk is not None:
                _, req = jose.jws_verify(data["request"], [verifier_public_jwk], {"ES256"}, "oauth-authz-req+jwt")
            else:
                req = jose.jws_payload(data["request"])
            if not relay and origin not in req.get("expected_origins", []):
                raise ValueError("origin not in expected_origins")
            aud = req["client_id"] if relay else "origin:" + origin
        else:
            req = data
            aud = "origin:" + origin
        aud = aud_override or aud
        vp_token = {}
        for cq in req["dcql_query"]["credentials"]:
            held = credentials.get(cq["id"])
            if held is None:
                continue
            if cq["format"] == "dc+sd-jwt":
                names = (disclose or {}).get(cq["id"], list(held["disclosures"]))
                vp_token[cq["id"]] = [self.present_sd_jwt(held, names, req["nonce"], aud, now)]
            else:
                vp_token[cq["id"]] = [self.present_vc_jwt(held, req["nonce"], aud, now)]
        return {"protocol": protocol, "data": {"vp_token": vp_token}}


def artifact(result, request_id=None, agent_id=None):
    """The Result Artifact an Agent puts in PROOF-RESPONSE."""
    obj = {"credential_result": result}
    if request_id:
        obj["request_id"] = request_id
    if agent_id:
        obj["agent_id"] = agent_id
    return jose.b64u_json(obj)


# ---------------------------------------------------------------------------------------
# An agent that signs TAP requests, with no third-party package: RFC 8032 Ed25519 signing
# on top of the arithmetic relayshield_tap_verifier already carries for verification.
# ---------------------------------------------------------------------------------------

_ED_L = 2 ** 252 + 27742317777372353535851937790883648493


def ed25519_public_key(seed: bytes) -> bytes:
    import relayshield_tap_verifier as tap
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return tap._ed_encodepoint(*tap._ed_scalarmult(tap._ED_GX, tap._ED_GY, a))


def ed25519_sign(seed: bytes, message: bytes) -> bytes:
    import relayshield_tap_verifier as tap
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    A = tap._ed_encodepoint(*tap._ed_scalarmult(tap._ED_GX, tap._ED_GY, a))
    r = int.from_bytes(hashlib.sha512(h[32:] + message).digest(), "little") % _ED_L
    R = tap._ed_encodepoint(*tap._ed_scalarmult(tap._ED_GX, tap._ED_GY, r))
    k = int.from_bytes(hashlib.sha512(R + A + message).digest(), "little") % _ED_L
    return R + ((r + k * a) % _ED_L).to_bytes(32, "little")


class Agent:
    """An AI agent with a TAP signing key: it signs the request it sends the merchant."""

    def __init__(self, keyid="agent-key-1"):
        self.seed = os.urandom(32)
        self.keyid = keyid
        self.jwk = {"kty": "OKP", "crv": "Ed25519", "kid": keyid,
                    "x": jose.b64u_encode(ed25519_public_key(self.seed))}

    def request(self, path, method="POST", authority="merchant.example", nonce=None, created=None,
                tag="agent-payer-auth", extra=None):
        """A TAP-signed inbound request, in the JSON shape the verifier Lambda takes."""
        import relayshield_tap_verifier as tap
        params = {"created": int(created if created is not None else time.time()), "keyid": self.keyid,
                  "alg": "ed25519", "nonce": nonce or jose.b64u_encode(os.urandom(12)), "tag": tag}
        req = {"authority": authority, "path": path, "method": method, "headers": {}}
        base = tap.build_signature_base(["@authority", "@path"], params, req)
        sig = ed25519_sign(self.seed, base)
        param_str = "".join(f";{k}={v}" if isinstance(v, int) else f';{k}="{v}"' for k, v in params.items())
        req["headers"]["signature-input"] = f'sig1=("@authority" "@path"){param_str}'
        req["headers"]["signature"] = f"sig1=:{jose.b64u_encode(sig)}:"
        req.update(extra or {})
        return req
