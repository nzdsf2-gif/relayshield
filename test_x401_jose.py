"""x401_jose: the crypto the x401 relying party stands on, checked against the
`cryptography` package (a test dependency, not a Lambda one) and published test vectors."""
import base64
import json
import sys
import unittest

sys.path.insert(0, "/tmp/pycrypto")
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature

import x401_jose as j


def ec_jwk(key, kid=None):
    n = key.public_key().public_numbers()
    return j.jwk_p256_public(n.x, n.y, kid or "")


def ed_jwk(key):
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return {"kty": "OKP", "crv": "Ed25519", "x": j.b64u_encode(raw)}


def rsa_jwk(key):
    n = key.public_key().public_numbers()
    f = lambda v: j.b64u_encode(v.to_bytes((v.bit_length() + 7) // 8, "big"))  # noqa: E731
    return {"kty": "RSA", "n": f(n.n), "e": f(n.e)}


def make_jws(header, payload, signer):
    h, p = j.b64u_json(header), j.b64u_json(payload)
    return f"{h}.{p}.{j.b64u_encode(signer(f'{h}.{p}'.encode()))}"


class ES256(unittest.TestCase):
    def test_rfc6979_vector_reproduces_exactly(self):
        d = 0xC9AFA9D845BA75166B5C215767B1D6934E50C3DB36E89B127B8A622B120F6721
        sig = j.es256_sign(d, b"sample")
        self.assertEqual(int.from_bytes(sig[:32], "big"),
                         0xEFD48B2AACB6A8FD1140DD9CD45E81D69D2C877B56AAF991C34D0EA84EAF3716)
        self.assertEqual(int.from_bytes(sig[32:], "big"),
                         0xF7CB1C942D657C41D436C7A1B6E29F65F3E900DBB9AFF4064DC4AB2F843ACDA8)

    def test_both_directions_against_the_cryptography_package(self):
        for i in range(8):
            key = ec.generate_private_key(ec.SECP256R1())
            nums = key.public_key().public_numbers()
            msg = f"message {i}".encode()
            r, s = decode_dss_signature(key.sign(msg, ec.ECDSA(hashes.SHA256())))
            self.assertTrue(j.es256_verify((nums.x, nums.y), msg, r.to_bytes(32, "big") + s.to_bytes(32, "big")))
            mine = j.es256_sign(key.private_numbers().private_value, msg)
            key.public_key().verify(encode_dss_signature(int.from_bytes(mine[:32], "big"),
                                                         int.from_bytes(mine[32:], "big")),
                                    msg, ec.ECDSA(hashes.SHA256()))

    def test_tampering_wrong_key_and_malformed_signatures_fail(self):
        key, other = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
        n, on = key.public_key().public_numbers(), other.public_key().public_numbers()
        d = key.private_numbers().private_value
        sig = j.es256_sign(d, b"m")
        self.assertTrue(j.es256_verify((n.x, n.y), b"m", sig))
        self.assertFalse(j.es256_verify((n.x, n.y), b"M", sig))
        self.assertFalse(j.es256_verify((on.x, on.y), b"m", sig))
        flipped = bytes([sig[0] ^ 1]) + sig[1:]
        self.assertFalse(j.es256_verify((n.x, n.y), b"m", flipped))
        for bad in (b"", b"\x00" * 64, b"\xff" * 64, sig[:63], sig + b"\x00", b"\x00" * 32 + sig[32:]):
            self.assertFalse(j.es256_verify((n.x, n.y), b"m", bad))
        self.assertFalse(j.es256_verify((1, 2), b"m", sig), "a point off the curve must fail")

    def test_the_point_at_infinity_and_zero_scalars_are_refused(self):
        with self.assertRaises(ValueError):
            j.p256_public_from_private(0)
        with self.assertRaises(ValueError):
            j.p256_public_from_private(j._N)

    def test_a_forged_signature_under_an_off_curve_point_is_refused(self):
        """The invalid-point attack. (0, 0) is not on P-256 but IS a point of order 2 on
        y^2 = x^3 - 3x. The group law does not use b, so arithmetic on it runs fine and a
        signature can be CONSTRUCTED to verify against it. Only the on-curve check stops it."""
        msg = b"forged"
        e = j._bits2int(__import__("hashlib").sha256(msg).digest()) % j._N
        for s in range(2, 200):
            u1 = e * pow(s, -1, j._N) % j._N
            R = j._to_affine(j._mul(u1, (j._GX, j._GY)))
            r = R[0] % j._N
            u2 = r * pow(s, -1, j._N) % j._N
            if u2 % 2 == 0:                       # an even multiple of an order-2 point is infinity
                sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
                break
        else:
            self.fail("could not construct the forgery")
        # prove the forgery is real: without the guard the arithmetic accepts it
        pt = j._jadd(j._mul(u1, (j._GX, j._GY)), j._mul(u2, (0, 0)))
        self.assertEqual(j._to_affine(pt)[0] % j._N, r)
        self.assertFalse(j.es256_verify((0, 0), msg, sig))

    def test_a_signature_is_deterministic(self):
        d = int.from_bytes(b"\x07" * 32, "big")
        self.assertEqual(j.es256_sign(d, b"x"), j.es256_sign(d, b"x"))


class JWS(unittest.TestCase):
    def setUp(self):
        self.ek = ec.generate_private_key(ec.SECP256R1())
        self.ejwk = ec_jwk(self.ek, "k1")

    def es(self, header, payload):
        def signer(data):
            r, s = decode_dss_signature(self.ek.sign(data, ec.ECDSA(hashes.SHA256())))
            return r.to_bytes(32, "big") + s.to_bytes(32, "big")
        return make_jws(header, payload, signer)

    def test_round_trip_through_our_own_signer(self):
        priv = j.generate_p256_jwk()
        tok = j.jws_sign_es256(priv, {"typ": "t", "kid": "a"}, {"x": 1})
        hdr, pl = j.jws_verify(tok, j.public_jwk(priv), {"ES256"}, "t")
        self.assertEqual((hdr["alg"], pl), ("ES256", {"x": 1}))
        self.assertNotIn("d", j.public_jwk(priv))

    def test_a_token_signed_elsewhere_verifies(self):
        tok = self.es({"alg": "ES256", "kid": "k1"}, {"a": 1})
        self.assertEqual(j.jws_verify(tok, [self.ejwk], {"ES256"})[1], {"a": 1})

    def test_alg_none_and_hmac_are_never_accepted(self):
        for alg in ("none", "None", "NONE", "HS256", "HS512"):
            tok = f"{j.b64u_json({'alg': alg})}.{j.b64u_json({'a': 1})}."
            with self.assertRaises(ValueError):
                j.jws_verify(tok, [self.ejwk], {alg, "ES256"})

    def test_an_alg_the_caller_did_not_allow_is_refused(self):
        tok = self.es({"alg": "ES256"}, {})
        with self.assertRaises(ValueError) as cm:
            j.jws_verify(tok, [self.ejwk], {"EdDSA"})
        self.assertEqual(str(cm.exception), "alg_not_allowed")

    def test_the_header_alg_must_fit_the_key_type(self):
        """A token claiming PS256 cannot be checked against an EC key, or EdDSA against RSA."""
        rk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        tok = make_jws({"alg": "PS256"}, {"a": 1}, lambda d: rk.sign(
            d, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256()))
        self.assertEqual(j.jws_verify(tok, [rsa_jwk(rk)], {"PS256"})[1], {"a": 1})
        with self.assertRaises(ValueError):
            j.jws_verify(tok, [self.ejwk], {"PS256"})
        self.assertFalse(j.verify_signature("EdDSA", rsa_jwk(rk), b"x", b"\x00" * 64))
        self.assertFalse(j.verify_signature("ES256", ed_jwk(Ed25519PrivateKey.generate()), b"x", b"\x00" * 64))

    def test_eddsa_ps256_and_rs256_verify_valid_signatures(self):
        ed = Ed25519PrivateKey.generate()
        tok = make_jws({"alg": "EdDSA"}, {"a": 1}, ed.sign)
        self.assertEqual(j.jws_verify(tok, [ed_jwk(ed)], {"EdDSA"})[1], {"a": 1})
        rk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        tok = make_jws({"alg": "RS256"}, {"a": 2}, lambda d: rk.sign(d, padding.PKCS1v15(), hashes.SHA256()))
        self.assertEqual(j.jws_verify(tok, [rsa_jwk(rk)], {"RS256"})[1], {"a": 2})
        bad = tok[:-4] + ("AAAA" if tok[-4:] != "AAAA" else "BBBB")
        with self.assertRaises(ValueError):
            j.jws_verify(bad, [rsa_jwk(rk)], {"RS256"})

    def test_kid_narrows_the_key_set_and_a_wrong_kid_finds_no_key(self):
        tok = self.es({"alg": "ES256", "kid": "other"}, {})
        with self.assertRaises(ValueError) as cm:
            j.jws_verify(tok, [self.ejwk], {"ES256"})
        self.assertEqual(str(cm.exception), "no_key")

    def test_a_wrong_typ_is_refused_when_one_is_required(self):
        tok = self.es({"alg": "ES256", "typ": "JWT"}, {})
        with self.assertRaises(ValueError):
            j.jws_verify(tok, [self.ejwk], {"ES256"}, "kb+jwt")

    def test_malformed_tokens_raise_valueerror_not_other_exceptions(self):
        for bad in ("", "a.b", "a.b.c.d", "....", "!!!.!!!.!!!", None, 5, "x" * 300_000,
                    f"{j.b64u_encode(b'[]')}.{j.b64u_encode(b'{}')}.AA"):
            with self.assertRaises(ValueError):
                j.jws_verify(bad, [self.ejwk], {"ES256"})

    def test_a_payload_that_is_not_an_object_is_refused(self):
        tok = self.es({"alg": "ES256"}, ["list"]) if False else None
        h, p = j.b64u_json({"alg": "ES256"}), j.b64u_encode(b"[1,2]")
        r, s = decode_dss_signature(self.ek.sign(f"{h}.{p}".encode(), ec.ECDSA(hashes.SHA256())))
        tok = f"{h}.{p}.{j.b64u_encode(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
        with self.assertRaises(ValueError):
            j.jws_verify(tok, [self.ejwk], {"ES256"})

    def test_signing_requires_a_private_p256_key(self):
        with self.assertRaises(ValueError):
            j.jws_sign_es256(j.public_jwk(j.generate_p256_jwk()), {}, {})


class Keys(unittest.TestCase):
    def test_rfc7638_thumbprint_vector(self):
        jwk = {"kty": "RSA", "e": "AQAB", "n": (
            "0vx7agoebGcQSuuPiLJXZptN9nndrQmbXEps2aiAFbWhM78LhWx4cbbfAAtVT86zwu1RK7aPFFxuhDR1L6tSoc_BJECPebWKRXjB"
            "ZCiFV4n3oknjhMstn64tZ_2W-5JsGY4Hc5n9yBXArwl93lqt7_RN5w6Cf0h4QyQ5v-65YGjQR0_FDW2QvzqY368QQMicAtaSqzs8"
            "KJZgnYb9c7d0zgdAZHzu6qMQvRL5hajrn1n91CbOpbISD08qNLyrdkt-bFTWhAI4vMQFh6WeZu0fM4lFd2NcRwr3XPksINHaQ-G_"
            "xBniIqbw0Ls1jF44-csFCur-kEgU8awapJzKnqDKgw")}
        self.assertEqual(j.jwk_thumbprint(jwk), "NzbLsXh8uDCcd-6MNwXF4W_7noWXFZAfHkxZsRGC9Xs")

    def test_thumbprint_ignores_private_and_extra_members(self):
        priv = j.generate_p256_jwk()
        self.assertEqual(j.jwk_thumbprint(priv), j.jwk_thumbprint(dict(j.public_jwk(priv), kid="x", use="sig")))

    def test_did_jwk_and_did_key_resolve_offline(self):
        pub = j.public_jwk(j.generate_p256_jwk())
        self.assertEqual(j.resolve_did_jwk("did:jwk:" + j.b64u_json(pub)), pub)
        with self.assertRaises(ValueError):
            j.resolve_did_jwk("did:jwk:" + j.b64u_json(j.generate_p256_jwk()))   # carries d
        # the did:key spec's own Ed25519 example
        got = j.resolve_did_key_jwk("did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK")
        self.assertEqual((got["kty"], got["crv"], len(j.b64u_decode(got["x"]))), ("OKP", "Ed25519", 32))
        # a P-256 key round-trips through its compressed did:key form
        k = ec.generate_private_key(ec.SECP256R1())
        nums = k.public_key().public_numbers()
        comp = bytes([2 + (nums.y & 1)]) + nums.x.to_bytes(32, "big")
        alphabet = j._B58
        n = int.from_bytes(b"\x80\x24" + comp, "big")
        enc = ""
        while n:
            n, rem = divmod(n, 58)
            enc = alphabet[rem] + enc
        got = j.resolve_did_key_jwk("did:key:z" + enc)
        self.assertEqual((j.b64u_decode(got["x"]), j.b64u_decode(got["y"])),
                         (nums.x.to_bytes(32, "big"), nums.y.to_bytes(32, "big")))

    def test_only_offline_dids_resolve(self):
        for did in ("did:web:evil.example", "did:ion:abc", "https://x", "", None):
            with self.assertRaises(ValueError):
                j.resolve_offline_did(did)


class AgentSigning(unittest.TestCase):
    """The testkit's pure-Python Ed25519 signer must be byte-identical to the reference
    implementation, or every TAP test built on it proves nothing."""

    def test_signatures_and_public_keys_match_the_cryptography_package(self):
        import os
        import x401_testkit as kit
        for _ in range(4):
            seed = os.urandom(32)
            ref = Ed25519PrivateKey.from_private_bytes(seed)
            self.assertEqual(kit.ed25519_public_key(seed),
                             ref.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
            msg = os.urandom(40)
            self.assertEqual(kit.ed25519_sign(seed, msg), ref.sign(msg))

    def test_an_agent_request_is_accepted_by_the_tap_verifier(self):
        import time as _t
        import x401_testkit as kit
        import relayshield_tap_verifier as tap
        agent = kit.Agent()
        req = agent.request("/pay", created=int(_t.time()))
        v = tap.verify_tap_request(req, jwks={agent.keyid: agent.jwk}, nonce_store=tap.MemoryNonceStore())
        self.assertEqual((v.decision, v.details["keyid"]), ("accept", agent.keyid), v.reasons)


if __name__ == "__main__":
    unittest.main()
