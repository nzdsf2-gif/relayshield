"""x401_jose -- the JOSE pieces the x401 relying party needs, in pure stdlib.

Everything the Lambda needs to sign its own OpenID4VP request and to verify what wallets
and issuers send back, with no third-party package in the deployment zip:

    ES256  (ECDSA P-256 / SHA-256)  sign and verify   <- what wallets and issuers use
    EdDSA  (Ed25519)                verify             <- reuses relayshield_tap_verifier
    PS256  (RSASSA-PSS)             verify             <- reuses relayshield_tap_verifier
    RS256  (RSASSA-PKCS1-v1_5)      verify
    JWK thumbprints (RFC 7638), did:key and did:jwk resolution (offline, no network)

THE RULES THIS FILE ENFORCES, because JOSE is where verifiers get hurt:

  * The KEY decides the algorithm, never the token. `verify_jws` takes the algorithms the
    caller will accept AND the key; the header's `alg` must be in that set AND must be
    compatible with the key's type. `none` and the HMAC family are never accepted, so there
    is no downgrade to "no signature" or to a shared secret the attacker can compute from
    the public key.
  * Malformed input returns False or raises ValueError. It never reaches a branch that
    treats "could not check" as "valid".
  * Signing is deterministic (RFC 6979), so a weak random source cannot leak the key.

ES256 here is textbook arithmetic on Python integers. Verification touches only public
values. Signing is NOT constant-time (CPython cannot be); the signing key lives in a
Lambda that serves one request at a time and is not exposed to a local attacker, but
that is the honest limit and is why the key is a dedicated one, never reused.
"""

import base64
import hashlib
import hmac
import json

# --------------------------------------------------------------------------- base64url


def b64u_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def b64u_decode(s) -> bytes:
    if isinstance(s, bytes):
        s = s.decode("ascii")
    if not isinstance(s, str):
        raise ValueError("not a string")
    s = s.strip()
    if not s or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in s):
        raise ValueError("not base64url")
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def b64u_json(obj) -> str:
    return b64u_encode(json.dumps(obj, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def b64u_json_decode(s) -> dict:
    obj = json.loads(b64u_decode(s).decode("utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("expected a JSON object")
    return obj


# --------------------------------------------------------------------------- P-256

_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_A = _P - 3
_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_GX = 0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296
_GY = 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5
_INF = None


def _inv(x: int, m: int) -> int:
    return pow(x, -1, m)


def _on_curve(x: int, y: int) -> bool:
    return 0 <= x < _P and 0 <= y < _P and (y * y - (x * x * x + _A * x + _B)) % _P == 0


# Jacobian coordinates (X, Y, Z): affine x = X/Z^2, y = Y/Z^3. Z == 0 is the point at infinity.
def _jdouble(pt):
    if pt is _INF:
        return _INF
    X, Y, Z = pt
    if Y == 0:
        return _INF
    S = (4 * X * Y * Y) % _P
    M = (3 * X * X + _A * pow(Z, 4, _P)) % _P
    X3 = (M * M - 2 * S) % _P
    Y3 = (M * (S - X3) - 8 * pow(Y, 4, _P)) % _P
    Z3 = (2 * Y * Z) % _P
    return (X3, Y3, Z3)


def _jadd(p1, p2):
    if p1 is _INF:
        return p2
    if p2 is _INF:
        return p1
    X1, Y1, Z1 = p1
    X2, Y2, Z2 = p2
    Z1Z1, Z2Z2 = (Z1 * Z1) % _P, (Z2 * Z2) % _P
    U1, U2 = (X1 * Z2Z2) % _P, (X2 * Z1Z1) % _P
    S1, S2 = (Y1 * Z2 * Z2Z2) % _P, (Y2 * Z1 * Z1Z1) % _P
    if U1 == U2:
        return _jdouble(p1) if S1 == S2 else _INF
    H, R = (U2 - U1) % _P, (S2 - S1) % _P
    H2 = (H * H) % _P
    H3 = (H * H2) % _P
    V = (U1 * H2) % _P
    X3 = (R * R - H3 - 2 * V) % _P
    Y3 = (R * (V - X3) - S1 * H3) % _P
    Z3 = (H * Z1 * Z2) % _P
    return (X3, Y3, Z3)


def _to_affine(pt):
    if pt is _INF:
        return None
    X, Y, Z = pt
    zi = _inv(Z, _P)
    zi2 = (zi * zi) % _P
    return ((X * zi2) % _P, (Y * zi2 * zi) % _P)


def _mul(k: int, point_affine):
    """k * point. Left-to-right double-and-add; the point is affine (x, y)."""
    k %= _N
    if k == 0 or point_affine is None:
        return _INF
    base = (point_affine[0], point_affine[1], 1)
    acc = _INF
    for bit in bin(k)[2:]:
        acc = _jdouble(acc)
        if bit == "1":
            acc = _jadd(acc, base)
    return acc


def p256_public_from_private(d: int):
    if not 1 <= d < _N:
        raise ValueError("private scalar out of range")
    return _to_affine(_mul(d, (_GX, _GY)))


def _bits2int(b: bytes) -> int:
    return int.from_bytes(b, "big")


def _rfc6979_k(d: int, h1: bytes):
    """Deterministic nonce, RFC 6979 section 3.2 with SHA-256 (qlen == hlen == 256)."""
    x = d.to_bytes(32, "big")
    h = (_bits2int(h1) % _N).to_bytes(32, "big")
    V, K = b"\x01" * 32, b"\x00" * 32
    K = hmac.new(K, V + b"\x00" + x + h, hashlib.sha256).digest()
    V = hmac.new(K, V, hashlib.sha256).digest()
    K = hmac.new(K, V + b"\x01" + x + h, hashlib.sha256).digest()
    V = hmac.new(K, V, hashlib.sha256).digest()
    while True:
        V = hmac.new(K, V, hashlib.sha256).digest()
        k = _bits2int(V)
        if 1 <= k < _N:
            return k
        K = hmac.new(K, V + b"\x00", hashlib.sha256).digest()
        V = hmac.new(K, V, hashlib.sha256).digest()


def es256_sign(d: int, message: bytes) -> bytes:
    """Raw 64-byte r||s signature (the JOSE form), not DER."""
    h1 = hashlib.sha256(message).digest()
    e = _bits2int(h1) % _N
    k = _rfc6979_k(d, h1)
    while True:
        R = _to_affine(_mul(k, (_GX, _GY)))
        r = R[0] % _N
        s = (_inv(k, _N) * (e + r * d)) % _N
        if r != 0 and s != 0:
            return r.to_bytes(32, "big") + s.to_bytes(32, "big")
        k = (k + 1) % _N or 1


def es256_verify(pub_xy, message: bytes, sig: bytes) -> bool:
    try:
        if len(sig) != 64:
            return False
        r, s = int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")
        if not (1 <= r < _N and 1 <= s < _N):
            return False
        x, y = pub_xy
        if not _on_curve(x, y):
            return False
        e = _bits2int(hashlib.sha256(message).digest()) % _N
        w = _inv(s, _N)
        u1, u2 = (e * w) % _N, (r * w) % _N
        pt = _jadd(_mul(u1, (_GX, _GY)), _mul(u2, (x, y)))
        aff = _to_affine(pt)
        return aff is not None and aff[0] % _N == r
    except Exception:
        return False


def p256_decompress(compressed: bytes):
    if len(compressed) != 33 or compressed[0] not in (2, 3):
        raise ValueError("not a compressed P-256 point")
    x = int.from_bytes(compressed[1:], "big")
    if x >= _P:
        raise ValueError("x out of range")
    rhs = (x * x * x + _A * x + _B) % _P
    y = pow(rhs, (_P + 1) // 4, _P)         # p is 3 mod 4
    if (y * y) % _P != rhs:
        raise ValueError("not on curve")
    if (y & 1) != (compressed[0] & 1):
        y = _P - y
    return x, y


# --------------------------------------------------------------------------- JWK helpers


def _int_to_bytes(n: int, length: int) -> bytes:
    return n.to_bytes(length, "big")


def jwk_p256_public(x: int, y: int, kid: str = "") -> dict:
    jwk = {"kty": "EC", "crv": "P-256", "x": b64u_encode(_int_to_bytes(x, 32)),
           "y": b64u_encode(_int_to_bytes(y, 32))}
    if kid:
        jwk["kid"] = kid
    return jwk


def jwk_to_p256(jwk: dict):
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        raise ValueError("not a P-256 JWK")
    x, y = int.from_bytes(b64u_decode(jwk["x"]), "big"), int.from_bytes(b64u_decode(jwk["y"]), "big")
    if not _on_curve(x, y):
        raise ValueError("point is not on P-256")
    return x, y


def generate_p256_jwk() -> dict:
    """A fresh P-256 private JWK (includes `d`). For tools/generate_x401_verifier_key.py."""
    import os
    while True:
        d = int.from_bytes(os.urandom(32), "big")
        if 1 <= d < _N:
            break
    x, y = p256_public_from_private(d)
    jwk = jwk_p256_public(x, y)
    jwk["d"] = b64u_encode(_int_to_bytes(d, 32))
    return jwk


def public_jwk(jwk: dict) -> dict:
    """The JWK with every private member removed."""
    return {k: v for k, v in jwk.items() if k in ("kty", "crv", "x", "y", "n", "e", "kid", "alg", "use")}


def jwk_thumbprint(jwk: dict) -> str:
    """RFC 7638 SHA-256 thumbprint, base64url."""
    kty = jwk.get("kty")
    if kty == "EC":
        members = {"crv": jwk["crv"], "kty": "EC", "x": jwk["x"], "y": jwk["y"]}
    elif kty == "OKP":
        members = {"crv": jwk["crv"], "kty": "OKP", "x": jwk["x"]}
    elif kty == "RSA":
        members = {"e": jwk["e"], "kty": "RSA", "n": jwk["n"]}
    else:
        raise ValueError("unsupported key type")
    return b64u_encode(hashlib.sha256(json.dumps(members, separators=(",", ":"), sort_keys=True).encode()).digest())


# --------------------------------------------------------------------------- RS256


_SHA256_DIGESTINFO = bytes.fromhex("3031300d060960864801650304020105000420")


def rs256_verify(n: int, e: int, message: bytes, sig: bytes) -> bool:
    try:
        k = (n.bit_length() + 7) // 8
        if len(sig) != k:
            return False
        s = int.from_bytes(sig, "big")
        if s >= n:
            return False
        em = pow(s, e, n).to_bytes(k, "big")
        t = _SHA256_DIGESTINFO + hashlib.sha256(message).digest()
        if k < len(t) + 11:
            return False
        expected = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
        return hmac.compare_digest(em, expected)
    except Exception:
        return False


# --------------------------------------------------------------------------- JWS

NEVER_ALGS = frozenset({"none", "None", "NONE", "HS256", "HS384", "HS512"})
_KTY_FOR_ALG = {"ES256": "EC", "EdDSA": "OKP", "PS256": "RSA", "RS256": "RSA"}


def jws_parse(token: str):
    """-> (header, payload_bytes, signing_input, signature). Raises ValueError."""
    if not isinstance(token, str) or token.count(".") != 2 or len(token) > 200_000:
        raise ValueError("not a compact JWS")
    h, p, s = token.split(".")
    header = b64u_json_decode(h)
    return header, b64u_decode(p), f"{h}.{p}".encode("ascii"), b64u_decode(s)


def jws_payload(token: str) -> dict:
    """The decoded payload object. DOES NOT VERIFY ANYTHING."""
    obj = json.loads(jws_parse(token)[1].decode("utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("payload is not an object")
    return obj


def verify_signature(alg: str, jwk: dict, signing_input: bytes, sig: bytes) -> bool:
    """Verify `sig` with `jwk` under `alg`. False on any mismatch of key type and algorithm."""
    if alg in NEVER_ALGS or alg not in _KTY_FOR_ALG:
        return False
    if not isinstance(jwk, dict) or jwk.get("kty") != _KTY_FOR_ALG[alg]:
        return False
    try:
        if alg == "ES256":
            return es256_verify(jwk_to_p256(jwk), signing_input, sig)
        import relayshield_tap_verifier as tap   # lazily: no import cycle at load time
        if alg == "EdDSA":
            if jwk.get("crv") != "Ed25519":
                return False
            return tap._ed_verify(b64u_decode(jwk["x"]), signing_input, sig)
        n = int.from_bytes(b64u_decode(jwk["n"]), "big")
        e = int.from_bytes(b64u_decode(jwk["e"]), "big")
        if alg == "PS256":
            return tap._pss_verify(n, e, sig, signing_input)
        return rs256_verify(n, e, signing_input, sig)
    except Exception:
        return False


def jws_verify(token: str, keys, allowed_algs, expected_typ=None):
    """Verify a compact JWS against any key in `keys`. -> (header, payload_dict).

    Raises ValueError with a short reason on ANY failure. `keys` is a JWK or a list of
    JWKs; when the header has a `kid` only keys with that kid (or no kid) are tried."""
    header, payload_bytes, signing_input, sig = jws_parse(token)
    alg = header.get("alg")
    if not isinstance(alg, str) or alg in NEVER_ALGS:
        raise ValueError("unsupported_alg")
    if alg not in allowed_algs:
        raise ValueError("alg_not_allowed")
    if expected_typ is not None and header.get("typ") != expected_typ:
        raise ValueError("bad_typ")
    candidates = [keys] if isinstance(keys, dict) else list(keys or [])
    kid = header.get("kid")
    if isinstance(kid, str) and kid:
        narrowed = [k for k in candidates if k.get("kid") in (None, kid)]
        candidates = narrowed
    if not candidates:
        raise ValueError("no_key")
    if not any(verify_signature(alg, k, signing_input, sig) for k in candidates[:8]):
        raise ValueError("bad_signature")
    payload = json.loads(payload_bytes.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("payload_not_object")
    return header, payload


def jws_sign_es256(private_jwk: dict, header: dict, payload: dict) -> str:
    """Compact JWS signed with an ES256 private JWK. `header["alg"]` is forced to ES256."""
    if private_jwk.get("kty") != "EC" or private_jwk.get("crv") != "P-256" or "d" not in private_jwk:
        raise ValueError("an EC P-256 private JWK is required")
    hdr = dict(header)
    hdr["alg"] = "ES256"
    signing_input = f"{b64u_json(hdr)}.{b64u_json(payload)}".encode("ascii")
    d = int.from_bytes(b64u_decode(private_jwk["d"]), "big")
    return signing_input.decode("ascii") + "." + b64u_encode(es256_sign(d, signing_input))


# --------------------------------------------------------------------------- DIDs (offline only)

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58decode(s: str) -> bytes:
    n = 0
    for c in s:
        n = n * 58 + _B58.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\x00" * (len(s) - len(s.lstrip("1"))) + raw


def resolve_did_key_jwk(did: str) -> dict:
    """did:key:z... -> public JWK, for Ed25519 (0xed01) and P-256 (0x1200) keys. No network."""
    if not isinstance(did, str) or not did.startswith("did:key:z"):
        raise ValueError("not a did:key")
    raw = _b58decode(did[len("did:key:z"):].split("#", 1)[0])
    if raw[:2] == b"\xed\x01" and len(raw) == 34:
        return {"kty": "OKP", "crv": "Ed25519", "x": b64u_encode(raw[2:])}
    if raw[:2] == b"\x80\x24" and len(raw) == 35:       # varint 0x1200
        x, y = p256_decompress(raw[2:])
        return jwk_p256_public(x, y)
    raise ValueError("unsupported did:key type")


def resolve_did_jwk(did: str) -> dict:
    """did:jwk:<base64url JWK> -> public JWK. No network."""
    if not isinstance(did, str) or not did.startswith("did:jwk:"):
        raise ValueError("not a did:jwk")
    jwk = b64u_json_decode(did[len("did:jwk:"):].split("#", 1)[0])
    if "d" in jwk:
        raise ValueError("did:jwk must not carry a private key")
    return jwk


def resolve_offline_did(did: str) -> dict:
    if isinstance(did, str) and did.startswith("did:key:"):
        return resolve_did_key_jwk(did)
    if isinstance(did, str) and did.startswith("did:jwk:"):
        return resolve_did_jwk(did)
    raise ValueError("only did:key and did:jwk resolve without a network")
