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

# x401 is an optional companion module. A package that lacks it must still verify
# TAP requests: a hard import here would take the whole Lambda down.
try:
    import x401_verifier as _x401
except Exception:  # ImportError, or a syntax error in the companion file
    _x401 = None

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
    k = (n.bit_length() + 7) // 8          # modulus length in bytes: the signature length
    if len(sig) != k:
        return False
    sig_int = int.from_bytes(sig, "big")
    if sig_int >= n:
        return False
    em_int = pow(sig_int, e, n)
    if em_int.bit_length() > em_len * 8:
        return False
    em = em_int.to_bytes(em_len, "big")
    if em_len < hlen + salt_len + 2 or em[-1] != 0xBC:
        return False
    masked_db = em[: em_len - hlen - 1]
    h_msg = em[em_len - hlen - 1: em_len - 1]
    # RFC 8017 9.1.2 step 6: the leftmost (8*emLen - emBits) bits of maskedDB must be
    # zero. The original test shifted the WRONG way (`em[0] >> zero_bits`), which checks
    # that the REMAINING bits are zero, so it rejected essentially every valid signature.
    zero_bits = 8 * em_len - em_bits
    if zero_bits and (masked_db[0] >> (8 - zero_bits)):
        return False
    db_mask = _mgf1(h_msg, em_len - hlen - 1, h)
    db = bytearray(a ^ b for a, b in zip(masked_db, db_mask))
    # step 9: clear those same leftmost bits of DB before reading the padding.
    if zero_bits:
        db[0] &= 0xFF >> zero_bits
    db = bytes(db)
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


# One per process. It used to be built INSIDE verify_tap_request whenever no store was
# passed, so every call started with an empty store and replay protection did nothing,
# not even within a single container.
_default_nonce_store = MemoryNonceStore()


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
    # Scoped by signer: a nonce is only unique per key, and two agents may both use "1".
    nonce = f"tap|{params['keyid']}|{params['nonce']}"
    store = nonce_store if nonce_store is not None else _default_nonce_store
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


NONCE_TABLE_ENV = "VERIFIER_NONCE_TABLE"
TI_SCREEN_ENV = "VERIFIER_TI_SCREEN"
_nonce_store_cache = {}


def _nonce_store():
    """Replay protection for this invocation. VERIFIER_NONCE_TABLE names the shared
    DynamoDB table; with it unset the per-process store is used, which is the old
    behaviour and does not stop a replay that lands on another container. Opting in is
    an environment variable rather than automatic so the table, the grant and the
    variable can be put in place in that order without a request failing in between."""
    import os
    table = os.environ.get(NONCE_TABLE_ENV, "").strip()
    if not table:
        return _default_nonce_store
    if table not in _nonce_store_cache:
        import relayshield_verifier_nonces as nonces
        _nonce_store_cache[table] = nonces.DynamoNonceStore(table)
    return _nonce_store_cache[table]


def _x401_nonce_fn(store):
    """Adapt a store's seen() to x401_verifier's (is_fresh, reason) shape."""
    def fn(key, now):
        if store.seen(f"x401|{key}", now):
            return False, "nonce replay detected"
        return True, "nonce fresh"
    return fn


def _ti_screen():
    """The TI screen, or None when VERIFIER_TI_SCREEN is not "1". When it IS on but
    cannot load, the returned function raises, so the verdict is `review` with
    `ti_unavailable` and the outage is visible instead of silently screening nothing."""
    import os
    if os.environ.get(TI_SCREEN_ENV, "") != "1":
        return None
    try:
        import relayshield_tap_ti
        return relayshield_tap_ti.screen
    except Exception as exc:
        reason = type(exc).__name__

        def unavailable(wallet=None, domain=None):
            raise RuntimeError(f"ti screen failed to load: {reason}")
        return unavailable


X401_ISSUERS_ENV = "X401_TRUSTED_ISSUERS"
X401_ISSUERS_FILE = "x401_issuers.json"
_x401_issuer_cache = {"keys": None}


def _x401_verify_sig(header, signing_input, sig_b64, pubkey, alg):
    """verify_sig_fn for x401_verifier. The KEY decides the algorithm, never the
    token's own `alg` header: an Ed25519 key only verifies EdDSA and an RSA key only
    PS256, so a credential cannot pick a weaker scheme for a key. RS256 (PKCS#1 v1.5)
    is NOT supported and fails, rather than being verified with the wrong scheme."""
    sig = b64u_decode(sig_b64)
    alg = str(alg or "")
    if isinstance(pubkey, (bytes, bytearray)):
        return alg in ("EdDSA", "Ed25519") and _ed_verify(bytes(pubkey), signing_input, sig)
    if isinstance(pubkey, tuple) and len(pubkey) == 2:
        n, e = pubkey
        return alg == "PS256" and _pss_verify(n, e, sig, signing_input)
    return False


def _x401_issuer_keys(env=None, path=None, refresh=False) -> dict:
    """Trusted issuers: {issuer id: Ed25519 key bytes | (n, e)}.

    Source is the X401_TRUSTED_ISSUERS environment variable (a JSON string) if set,
    else x401_issuers.json beside this module. Both hold
    {"issuers": {"<issuer DID or URI>": <JWK>, ...}}. An entry that is not a usable
    Ed25519 or RSA JWK is skipped with a warning. EMPTY means "not configured": the
    caller answers `review`, never `accept`, because nothing can be verified."""
    import os
    if _x401_issuer_cache["keys"] is not None and not refresh and env is None and path is None:
        return _x401_issuer_cache["keys"]
    raw = env if env is not None else os.environ.get(X401_ISSUERS_ENV, "")
    if not raw:
        file_path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), X401_ISSUERS_FILE)
        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                raw = fh.read()
        except OSError:
            raw = ""
    keys = {}
    try:
        doc = json.loads(raw) if raw else {}
        entries = doc.get("issuers", {}) if isinstance(doc, dict) else {}
        entries = entries if isinstance(entries, dict) else {}
    except ValueError:
        logger.warning("x401 issuer registry is not valid JSON")
        entries = {}
    for issuer, jwk in (entries or {}).items():
        try:
            if not isinstance(issuer, str) or not issuer or not isinstance(jwk, dict):
                raise ValueError("bad entry")
            keys[issuer] = (_jwk_to_ed25519_pub(jwk) if jwk.get("kty") == "OKP"
                            else _jwk_to_rsa_pub(jwk))
        except Exception:
            logger.warning("x401 issuer registry: skipping an unusable entry")
    if env is None and path is None:
        _x401_issuer_cache["keys"] = keys
    return keys


def _presentation_issuer(presentation) -> str:
    """The `iss` the presentation CLAIMS for its first JWT credential, for telemetry
    only. It is read without verifying anything, so on a rejected request it is the
    attacker's claim, and it is only ever hashed."""
    try:
        vp = json.loads(b64u_decode(presentation).decode("utf-8"))
        for cred in vp.get("verifiableCredential", []):
            if isinstance(cred, str) and cred.count(".") == 2:
                payload = json.loads(b64u_decode(cred.split(".")[1]).decode("utf-8"))
                iss = payload.get("iss")
                if isinstance(iss, str):
                    return iss
    except Exception:
        pass
    return ""


def verify_x401_branch(request: dict, headers: dict) -> Verdict:
    """The x401 half. `headers` are the AGENT's request headers, lower-cased, taken
    from request["headers"] exactly as the TAP signature headers are.

    The transaction being authorised comes from request["transaction"]
    ({"amount", "currency", "merchant", "action_category", "agent_id"}); `agent_id`,
    `merchant_domain` and `authority` on the request are used when it omits them.
    The mandate's constraints are checked against these and a constraint that cannot
    be checked fails (see x401_verifier.validate_mandate_scope)."""
    if _x401 is None:
        return _review("x401_unavailable")
    try:
        issuer_keys = _x401_issuer_keys()
        if not issuer_keys:
            return _review("x401_issuers_unconfigured")
        presentation = headers.get("proof-presentation")
        if not isinstance(presentation, str) or not presentation.strip():
            return _reject("malformed_presentation")
        tx = request.get("transaction")
        tx = tx if isinstance(tx, dict) else {}
        transaction = {
            "agent_id": tx.get("agent_id") or request.get("agent_id") or "",
            "merchant": tx.get("merchant") or request.get("merchant_domain")
                        or request.get("authority") or "",
            "amount": tx.get("amount"),
            "currency": tx.get("currency") or "",
            "action_category": tx.get("action_category") or "",
        }
        res = _x401.verify_x401_presentation(
            presentation, transaction, issuer_keys=issuer_keys,
            verify_sig_fn=_x401_verify_sig, nonce_fn=_x401_nonce_fn(_nonce_store()))
    except Exception as exc:
        logger.warning("x401 verification error: %s", type(exc).__name__)
        return _review("x401_internal_error")
    if res.get("valid"):
        return Verdict("accept", ["x401_valid"],
                       {"assurance": res.get("assurance")})
    # The sentence in res["reason"] can carry request values, so it goes to the
    # merchant under details only, and telemetry only ever sees the code.
    return _reject(_x401.reason_code(res.get("reason")), x401_detail=res.get("reason"))


class AgentOutcome:
    """What lambda_handler needs: the verdict, which verifier(s) produced it, and
    the issuer the presentation claimed (telemetry only)."""

    def __init__(self, verdict, verifier_type, issuer=None):
        self.verdict = verdict
        self.verifier_type = verifier_type
        self.issuer = issuer


def _combine(tap_v: Verdict, x401_v: Verdict) -> Verdict:
    """Both credentials were presented, so BOTH must accept. Any reject wins, then any
    review. Reasons come only from the verdicts that decided the outcome, so the first
    reason (which telemetry classifies) names the cause rather than a passing half."""
    details = dict(tap_v.details)
    details["x401"] = x401_v.details
    for level in ("reject", "review"):
        deciding = [v for v in (tap_v, x401_v) if v.decision == level]
        if deciding:
            reasons = [r for v in deciding for r in v.reasons]
            return Verdict(level, reasons, details)
    return Verdict("accept", list(tap_v.reasons) + list(x401_v.reasons), details)


def verify_agent_request(request: dict) -> AgentOutcome:
    """TAP, x401, or both, chosen by which credentials the agent presented.

    No PROOF-PRESENTATION header: exactly the TAP verifier, unchanged. Header and TAP
    signature: both must accept. Header alone: x401 only."""
    raw = request.get("headers")
    headers = ({str(k).lower(): v for k, v in raw.items()} if isinstance(raw, dict) else {})
    if not isinstance(raw, dict):
        request = {**request, "headers": {}}   # verify_tap_request calls .items() on it
    tap_kw = {"nonce_store": _nonce_store(), "ti_screen": _ti_screen()}
    if "proof-presentation" not in headers:
        return AgentOutcome(verify_tap_request(request, **tap_kw), "tap")
    issuer = _presentation_issuer(headers.get("proof-presentation"))
    x401_v = verify_x401_branch(request, headers)
    if "signature" in headers and "signature-input" in headers:
        return AgentOutcome(_combine(verify_tap_request(request, **tap_kw), x401_v), "tap+x401", issuer)
    return AgentOutcome(x401_v, "x401", issuer)


def lambda_handler(event, context):
    """API Gateway entry point. Expects the inbound agent HTTP request
    described in the TAP spec, proxied as JSON."""
    event = event if isinstance(event, dict) else {}
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    try:
        data = json.loads(body) if isinstance(body, str) else body
    except Exception:
        return _http(400, {"decision": "reject",
                           "reasons": ["bad_request_body"]})
    request = data if isinstance(data, dict) else {}
    outcome = verify_agent_request(request)
    verdict = outcome.verdict
    _report_rejection(verdict, event, request, outcome.verifier_type, outcome.issuer)
    code = {"accept": 200, "review": 202, "reject": 403}[verdict.decision]
    return _http(code, verdict.to_dict())


def _report_rejection(verdict, event, request, verifier_type="tap", issuer=None):
    """Opt-in threat telemetry. Runs AFTER the verdict is final, can change nothing in
    it, and never raises. An accept or review returns before any lookup, so the opt-in
    check costs nothing on the normal path. See relayshield_verifier_telemetry."""
    if verdict.decision != "reject":
        return
    try:
        import relayshield_verifier_telemetry as vt
        vt.maybe_report(verifier_type, verdict, event, request, issuer=issuer)
    except Exception as exc:
        logger.warning("verifier telemetry unavailable: %s", type(exc).__name__)


def _http(status, obj):
    return {"statusCode": status,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(obj)}
