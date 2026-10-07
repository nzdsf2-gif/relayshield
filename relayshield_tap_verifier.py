"""
relayshield_tap_verifier -- merchant-side Visa Trusted Agent Protocol verifier.

Verifies RFC 9421 HTTP Message Signatures on inbound agent requests, then
screens the counterparty against RelayShield's threat-intel corpus. This is
the "Site Protection Provider" role in Visa's TAP spec: Visa's directory
answers "is this agent registered"; we answer "is it safe to transact with".

Pure stdlib: no third-party crypto. Ed25519 and RSA-PSS are implemented
directly so the Lambda zip needs nothing beyond this file.

Pipeline:
  1. Parse Signature-Input / Signature headers
  2. Resolve keyid against Visa JWKS (cached)
  3. Rebuild the RFC 9421 signature base from covered components
  4. Verify the signature (Ed25519 or RSASSA-PSS/SHA-256)
  5. Freshness: created within the 8-minute window, not expired
  6. Replay: nonce must be unseen (pluggable store)
  7. Intent scoping: declared intent must cover the attempted action
  8. TI screen: wallet / merchant domain against the corpus (pluggable)
  9. Verdict: accept / review / reject

Verdict policy:
  - reject: bad signature, expired, replay, unknown key, TI high/critical,
            read-only intent attempting a payment action
  - review:  TI medium/flagged, TI unavailable, tag not recognised,
            unrecognised intent attempting a payment action
  - accept:  signature valid, fresh, nonce new, intent covers action, TI clean
"""

import base64
import hashlib
import json
import logging
import re
import time
import urllib.request

logger = logging.getLogger()
logger.setLevel(logging.INFO)

VISA_JWKS_URL = "https://mcp.visa.com/.well-known/jwks"
JWKS_CACHE_TTL = 3600

MAX_AGE_SECONDS = 8 * 60  # 8-minute validity window per TAP spec
VALID_TAGS = {"agent-browser-auth", "agent-payer-auth"}
VALID_ALGS = {"ed25519", "ps256"}

_jwks_cache = {"at": 0.0, "keys": {}}


# ---------------------------------------------------------------------------
# base64url helpers
# ---------------------------------------------------------------------------

def b64u_decode(s: str) -> bytes:
    s = s.strip()
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def b64u_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


# ---------------------------------------------------------------------------
# JWKS
# ---------------------------------------------------------------------------

def fetch_jwks(url: str = VISA_JWKS_URL, ttl: float = JWKS_CACHE_TTL,
               _now: float | None = None) -> dict:
    """Fetch JWKS, cached for `ttl` seconds. Returns {kid: jwk}."""
    now = _now if _now is not None else time.time()
    if _jwks_cache["keys"] and now - _jwks_cache["at"] < ttl:
        return _jwks_cache["keys"]
    req = urllib.request.Request(url, headers={"User-Agent": "relayshield-tap-verifier/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        doc = json.loads(resp.read().decode("utf-8"))
    keys = {k["kid"]: k for k in doc.get("keys", []) if k.get("kid")}
    _jwks_cache["at"] = now
    _jwks_cache["keys"] = keys
    logger.info("JWKS refreshed: %d keys", len(keys))
    return keys


def _jwk_to_ed25519_pub(jwk: dict) -> bytes:
    if jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519":
        raise ValueError("not an Ed25519 JWK")
    return b64u_decode(jwk["x"])


def _jwk_to_rsa_pub(jwk: dict) -> tuple[int, int]:
    if jwk.get("kty") != "RSA":
        raise ValueError("not an RSA JWK")
    n = int.from_bytes(b64u_decode(jwk["n"]), "big")
    e = int.from_bytes(b64u_decode(jwk["e"]), "big")
    return n, e


# ---------------------------------------------------------------------------
# Ed25519 (pure python, RFC 8032)
# ---------------------------------------------------------------------------

_ED_P = 2 ** 255 - 19
_ED_D = (-121665 * pow(121666, _ED_P - 2, _ED_P)) % _ED_P
_ED_I = pow(2, (_ED_P - 1) // 4, _ED_P)


def _ed_xrecover(y: int) -> int:
    xx = (y * y - 1) * pow(_ED_D * y * y + 1, _ED_P - 2, _ED_P) % _ED_P
    x = pow(xx, (_ED_P + 3) // 8, _ED_P)
    if (x * x - xx) % _ED_P != 0:
        x = (x * _ED_I) % _ED_P
    return x if x % 2 == 0 else _ED_P - x


def _ed_decodepoint(s: bytes) -> tuple[int, int]:
    y = int.from_bytes(s, "little") & ((1 << 255) - 1)
    x = _ed_xrecover(y)
    if (s[-1] >> 7) != (x & 1):
        x = _ED_P - x
    return x, y


def _ed_encodepoint(x: int, y: int) -> bytes:
    b = y.to_bytes(32, "little")
    if x & 1:
        b = b[:-1] + bytes([b[-1] | 0x80])
    return b


def _ed_verify(pub32: bytes, msg: bytes, sig64: bytes) -> bool:
    """Return True iff sig64 is a valid Ed25519 signature of msg under pub32."""
    if len(pub32) != 32 or len(sig64) != 64:
        return False
    try:
        ax, ay = _ed_decodepoint(pub32)
    except Exception:
        return False
    r = int.from_bytes(sig64[:32], "little")
    s = int.from_bytes(sig64[32:], "little")
    if s >= 2 ** 253:
        return False
    # R = s*B - h*A  (projective, single scalar mult via double-and-add)
    h = int.from_bytes(hashlib.sha512(sig64[:32] + pub32 + msg).digest(), "little")
    h = h % (2 ** 252 + 27742317777372353535851937790883648493)
    # compute s*B
    bx, by = _ed_scalarmult(_ED_GX, _ED_GY, s)
    # compute h*A
    hx, hy = _ed_scalarmult(ax, ay, h)
    # R_check = s*B - h*A
    rx, ry = _ed_point_sub(bx, by, hx, hy)
    r_enc = _ed_encodepoint(rx, ry)
    # accept both parities of the x-recovery (strict encodings match exactly)
    return r_enc[:32] == sig64[:32]


# base point
def _ed_point_add(px, py, qx, qy):
    # Twisted Edwards with a=-1: y3 = (y1*y2 + x1*x2) / (1 - d*x1*x2*y1*y2).
    # Affine is slower than extended coordinates but fine for verification
    # (two scalar mults per verify).
    x1, y1, x2, y2 = px, py, qx, qy
    d = _ED_D
    x3 = (x1 * y2 + x2 * y1) * pow(1 + d * x1 * x2 * y1 * y2, _ED_P - 2, _ED_P) % _ED_P
    y3 = (y1 * y2 + x1 * x2) * pow(1 - d * x1 * x2 * y1 * y2, _ED_P - 2, _ED_P) % _ED_P
    return x3 % _ED_P, y3 % _ED_P


def _ed_point_sub(px, py, qx, qy):
    return _ed_point_add(px, py, (-qx) % _ED_P, qy)


def _ed_scalarmult(px, py, e):
    rx, ry = 0, 1
    qx, qy = px, py
    while e:
        if e & 1:
            rx, ry = _ed_point_add(rx, ry, qx, qy)
        qx, qy = _ed_point_add(qx, qy, qx, qy)
        e >>= 1
    return rx, ry


_ED_GY = (4 * pow(5, _ED_P - 2, _ED_P)) % _ED_P
_ED_GX = _ed_xrecover(_ED_GY)


# ---------------------------------------------------------------------------
# RSA-PSS (EMSA-PSS-VERIFY, SHA-256)
# ---------------------------------------------------------------------------

def _mgf1(seed: bytes, length: int, h=hashlib.sha256) -> bytes:
    out = b""
    for i in range((length + 31) // 32):
        out += h(seed + i.to_bytes(4, "big")).digest()
    return out[:length]


def _pss_verify(n: int, e: int, sig: bytes, msg: bytes,
                h=hashlib.sha256, salt_len: int = 32) -> bool:
    """EMSA-PSS-VERIFY per RFC 8017 s9.1.2. Returns True on valid signature."""
    hlen = h().digest_size
    em_bits = n.bit_length() - 1
    em_len = (em_bits + 7) // 8
    if len(sig) != em_len:
        return False
    try:
        em_int = pow(int.from_bytes(sig, "big"), e, n)
    except Exception:
        return False
    em = em_int.to_bytes(em_len, "big")
    if em[-1] != 0xBC:
        return False
    masked_db = em[: em_len - hlen - 1]
    h_msg = em[em_len - hlen - 1: em_len - 1]
    # check leading zero bits
    if em[0] >> (8 * em_len - em_bits):
        return False
    db_mask = _mgf1(h_msg, em_len - hlen - 1, h)
    db = bytes(a ^ b for a, b in zip(masked_db, db_mask))
    # db = PS(0x00 * pad_len) || 0x01 || salt, where
    # pad_len = em_len - hlen - salt_len - 2
    pad_len = em_len - hlen - salt_len - 2
    if pad_len < 0 or any(b != 0 for b in db[:pad_len]):
        return False
    if db[pad_len] != 0x01:
        return False
    salt = db[pad_len + 1:]
    if len(salt) != salt_len:
        return False
    m_hash = h(msg).digest()
    h_prime = h(b"\x00" * 8 + m_hash + salt).digest()
    return h_prime == h_msg


# ---------------------------------------------------------------------------
# RFC 9421 parsing
# ---------------------------------------------------------------------------

_SIG_INPUT_RE = re.compile(
    r'\s*(?P<label>[A-Za-z0-9!#$%&\'*+\-.^_`|~]+)\s*=\s*'
    r'\(\s*(?P<components>[^)]*?)\s*\)'
    r'(?P<params>[^,]*?)\s*(?:,|$)'
)
_PARAM_RE = re.compile(
    r';\s*(?P<key>[A-Za-z0-9!#$%&\'*+\-.^_`|~]+)\s*=\s*'
    r'(?P<val>[0-9]+|"(?:[^"\\]|\\.)*")'
)
_COMP_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _unescape(s: str) -> str:
    return s.replace('\\"', '"').replace("\\\\", "\\")


def parse_signature_input(value: str) -> dict:
    """Parse a Signature-Input header into {label: {components, params}}."""
    out = {}
    for m in _SIG_INPUT_RE.finditer(value):
        label = m.group("label")
        comps = [_unescape(c) for c in _COMP_RE.findall(m.group("components") or "")]
        params = {}
        for pm in _PARAM_RE.finditer(m.group("params") or ""):
            v = pm.group("val")
            params[pm.group("key")] = int(v) if v.isdigit() else _unescape(v[1:-1])
        out[label] = {"components": comps, "params": params}
    return out


def parse_signatures(value: str) -> dict:
    """Parse a Signature header into {label: base64-signature}."""
    out = {}
    for part in value.split(","):
        part = part.strip()
        if "=" not in part:
            continue
        label, sig = part.split("=", 1)
        label = label.strip()
        sig = sig.strip()
        if sig.startswith(":") and sig.endswith(":"):
            sig = sig[1:-1]
        out[label] = sig
    return out


def build_signature_base(components: list[str], params: dict,
                         request: dict) -> bytes:
    """Build the RFC 9421 signature base. `request` maps names to values.

    Supported derived components: @authority, @path, @method, @query.
    Anything else is looked up in request['headers'] (case-insensitive).
    """
    lines = []
    headers = {k.lower(): v for k, v in (request.get("headers") or {}).items()}
    for comp in components:
        name = comp
        # parameters on individual components (e.g. ;bs ;tr) are not needed
        # for the TAP profile; strip anything after ';'
        if ";" in name:
            name = name.split(";")[0].strip()
        if name == "@authority":
            val = request.get("authority", "")
        elif name == "@path":
            val = request.get("path", "")
        elif name == "@method":
            val = request.get("method", "POST")
        elif name == "@query":
            val = request.get("query", "")
        else:
            val = headers.get(name.lower().lstrip('"').strip('"'), "")
        lines.append(f'"{name}": {val}')
    # Params must appear in the same order as in the Signature-Input header;
    # RFC 9421 signs the exact serialization. Dicts preserve insertion order.
    param_strs = []
    for k, v in params.items():
        param_strs.append(f'{k}={v}' if isinstance(v, int) else f'{k}="{v}"')
    lines.append(
        f'"@signature-params": ({ " ".join(chr(34) + c + chr(34) for c in components) });'
        + ";".join(param_strs)
    )
    return ("\n".join(lines)).encode("ascii")


# ---------------------------------------------------------------------------
# Nonce store (replay protection)
# ---------------------------------------------------------------------------

class MemoryNonceStore:
    """In-process nonce store. For Lambda, prefer DynamoDBNonceStore."""

    def __init__(self):
        self._seen: dict[str, float] = {}

    def seen(self, nonce: str, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        # prune entries older than the max window
        cutoff = now - MAX_AGE_SECONDS - 60
        self._seen = {k: v for k, v in self._seen.items() if v > cutoff}
        if nonce in self._seen:
            return True
        self._seen[nonce] = now
        return False


# ---------------------------------------------------------------------------
# Intent scoping (Visa TAP intent-scoped tokens)
# ---------------------------------------------------------------------------
# TAP credentials are minted against a declared purchasing intent: the token
# is only valid where that intent allows. The merchant must enforce the
# boundary, e.g. an agent holding a "browse" token must not check out.
# Intent levels: 0 = read-only, 1 = may move money. A token whose intent
# level is below the attempted action level is an intent mismatch.

INTENT_LEVELS = {
    # read-only: browsing, discovery, price comparison
    "browse": 0, "search": 0, "read": 0, "lookup": 0,
    "price-check": 0, "pricecheck": 0, "quote": 0, "discover": 0,
    # transactional: the agent is authorized to move money
    "checkout": 1, "purchase": 1, "pay": 1, "payment": 1,
    "order": 1, "buy": 1, "transact": 1,
}

# Path fragments indicating a money-moving action.
PAYMENT_PATH_HINTS = (
    "pay", "checkout", "purchase", "order", "payment",
    "charge", "buy", "transaction", "authorize",
)


def _derive_action_level(request):
    """Classify the attempted action: 1 = moves money, 0 = read-only,
    None = cannot be determined."""
    explicit = request.get("action")
    if explicit is not None:
        lvl = INTENT_LEVELS.get(str(explicit).strip().lower())
        if lvl is not None:
            return lvl
        # explicit but unrecognised: fall through to path heuristics
    path = str(request.get("path") or "").lower()
    if any(h in path for h in PAYMENT_PATH_HINTS):
        return 1
    if path:
        return 0
    return None


def _intent_claim(params, request):
    """Return (intent, source). Prefers the signature-covered param, since
    only that value is authenticated; falls back to header then request
    field for tokens that carry intent outside Signature-Input."""
    if params.get("intent"):
        return str(params["intent"]), "signature_params"
    headers = {k.lower(): v for k, v in (request.get("headers") or {}).items()}
    if headers.get("tap-intent"):
        return str(headers["tap-intent"]), "tap_intent_header"
    if request.get("intent"):
        return str(request["intent"]), "request_field"
    return None, "none"


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------

class Verdict:
    def __init__(self, decision: str, reasons: list[str], details: dict | None = None):
        assert decision in ("accept", "review", "reject")
        self.decision = decision
        self.reasons = reasons
        self.details = details or {}

    def to_dict(self):
        return {"decision": self.decision, "reasons": self.reasons,
                "details": self.details}

    def __repr__(self):
        return f"Verdict({self.decision}, {self.reasons})"


def _reject(*reasons, **details):
    return Verdict("reject", list(reasons), details)


def _review(*reasons, **details):
    return Verdict("review", list(reasons), details)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def verify_tap_request(request: dict,
                       jwks: dict | None = None,
                       nonce_store=None,
                       ti_screen=None,
                       now: float | None = None) -> Verdict:
    """Verify a TAP-signed inbound agent request.

    request = {
      "headers": {"signature-input": ..., "signature": ..., ...},
      "authority": "merchant.example",
      "path": "/v1/pay",
      "method": "POST",
      # optional counterparty material for TI screening:
      "wallet": "0x...",
      "merchant_domain": "shop.example",
      "agent_id": "...",
    }
    jwks: {kid: jwk} (fetched from Visa if None)
    nonce_store: object with .seen(nonce, now) -> bool
    ti_screen: callable(wallet=None, domain=None) -> {"level": ..., "reasons": [...]}
    """
    now = now if now is not None else time.time()
    headers = {k.lower(): v for k, v in (request.get("headers") or {}).items()}

    sig_input = headers.get("signature-input")
    sig_header = headers.get("signature")
    if not sig_input or not sig_header:
        return _reject("missing_signature_headers")

    try:
        parsed = parse_signature_input(sig_input)
    except Exception:
        return _reject("malformed_signature_input")
    if not parsed:
        return _reject("malformed_signature_input")
    label = next(iter(parsed))
    entry = parsed[label]
    params = entry["params"]
    components = entry["components"]

    # Required params
    for req_param in ("created", "keyid", "alg", "nonce"):
        if req_param not in params:
            return _reject(f"missing_param_{req_param}")
    alg = str(params["alg"]).lower()
    if alg not in VALID_ALGS:
        return _reject("unsupported_alg", alg=alg)

    # Required covered components for the TAP profile
    need = {"@authority", "@path"}
    have = {c.split(";")[0].strip().strip('"') for c in components}
    if not need.issubset(have):
        return _reject("missing_covered_components",
                       missing=sorted(need - have))

    # Freshness
    created = params["created"]
    if not isinstance(created, int):
        return _reject("bad_created")
    age = now - created
    if age < -60:
        return _reject("created_in_future", age=age)
    if age > MAX_AGE_SECONDS:
        return _reject("signature_too_old", age=age)
    expires = params.get("expires")
    if isinstance(expires, int) and now > expires:
        return _reject("signature_expired")

    # Replay
    nonce = str(params["nonce"])
    store = nonce_store or MemoryNonceStore()
    try:
        if store.seen(nonce, now):
            return _reject("replay_nonce")
    except Exception as exc:
        logger.warning("nonce store error: %s", exc)
        return _reject("nonce_store_error")

    # Resolve key
    if jwks is None:
        try:
            jwks = fetch_jwks()
        except Exception as exc:
            logger.warning("JWKS fetch failed: %s", exc)
            return _review("jwks_unavailable")
    keyid = str(params["keyid"])
    jwk = jwks.get(keyid)
    if not jwk:
        return _reject("unknown_keyid", keyid=keyid)

    # Signature
    sigs = parse_signatures(sig_header)
    sig_b64 = sigs.get(label)
    if not sig_b64:
        return _reject("missing_signature_for_label", label=label)
    try:
        sig_bytes = b64u_decode(sig_b64)
    except Exception:
        return _reject("bad_signature_encoding")
    try:
        base = build_signature_base(components, params, request)
    except Exception as exc:
        return _reject("base_construction_failed", error=str(exc))

    ok = False
    try:
        if alg == "ed25519":
            pub = _jwk_to_ed25519_pub(jwk)
            ok = _ed_verify(pub, base, sig_bytes)
        else:  # ps256
            n, e = _jwk_to_rsa_pub(jwk)
            ok = _pss_verify(n, e, sig_bytes, base)
    except Exception as exc:
        logger.warning("verify error: %s", exc)
        ok = False
    if not ok:
        return _reject("bad_signature")

    details = {"keyid": keyid, "alg": alg,
               "tag": params.get("tag"), "age_seconds": round(age, 1)}

    # Tag: recognised values pass; anything else is review, not reject
    tag = params.get("tag")
    if tag is not None and str(tag) not in VALID_TAGS:
        details["tag"] = str(tag)
        return _review("unrecognised_tag", **details)

    # Intent scoping: the credential is only valid where the declared
    # intent allows. A read-only intent attempting payment is a reject
    # (scope violation); an unrecognised intent attempting payment is a
    # review (cannot verify scope). Absent intent skips the check.
    intent, intent_src = _intent_claim(params, request)
    if intent is not None:
        intent_norm = intent.strip().lower()
        details["intent"] = intent_norm
        details["intent_source"] = intent_src
        intent_level = INTENT_LEVELS.get(intent_norm)
        action_level = _derive_action_level(request)
        if intent_level is None:
            if action_level == 1:
                details["intent_issue"] = (
                    "unrecognised_intent_for_payment_action")
                return _review("intent_mismatch", **details)
        elif action_level is not None and intent_level < action_level:
            details["intent_issue"] = "read_only_intent_attempted_payment"
            return _reject("intent_mismatch", **details)

    # TI corpus screening: the differentiator beyond signature-only verifiers
    wallet = request.get("wallet")
    domain = request.get("merchant_domain") or request.get("authority")
    if ti_screen is not None and (wallet or domain):
        try:
            ti = ti_screen(wallet=wallet, domain=domain) or {}
        except Exception as exc:
            logger.warning("TI screen error: %s", exc)
            return _review("ti_unavailable", **details)
        level = str(ti.get("level", "unknown")).lower()
        reasons = ti.get("reasons", [])
        if level in ("critical", "high"):
            return _reject("ti_flagged", ti_level=level,
                           ti_reasons=reasons, **details)
        if level in ("medium", "moderate", "suspicious", "flagged"):
            return _review("ti_flagged", ti_level=level,
                           ti_reasons=reasons, **details)
        details["ti_level"] = level
    elif ti_screen is not None:
        details["ti_skipped"] = "no_counterparty_material"

    return Verdict("accept", ["signature_valid", "fresh", "nonce_new",
                              "ti_clean"], details)


def lambda_handler(event, context):
    """API Gateway entry point. Expects the inbound agent HTTP request
    described in the TAP spec, proxied as JSON."""
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    try:
        data = json.loads(body) if isinstance(body, str) else body
    except Exception:
        return _http(400, {"decision": "reject",
                           "reasons": ["bad_request_body"]})
    verdict = verify_tap_request(data if isinstance(data, dict) else {})
    code = {"accept": 200, "review": 202, "reject": 403}[verdict.decision]
    return _http(code, verdict.to_dict())


def _http(status, obj):
    return {"statusCode": status,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(obj)}
