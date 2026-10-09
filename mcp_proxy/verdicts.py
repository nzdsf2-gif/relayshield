"""Signed verdicts for MCP proxy firewall decisions.

Every block/quarantine decision gets a signed verdict that ties the
decision to RelayShield's threat intelligence evidence. A copied proxy
without the live backend and signing key produces verdicts nobody can
verify: the signature is the proof of provenance.

Signing uses Ed25519 (RFC 8032), implemented here in pure Python so the
proxy keeps its zero-dependency property. The private key comes only
from the MCP_PROXY_SIGNING_KEY environment variable (32 bytes, hex).
If no key is configured, verdicts are issued unsigned but still carry
the full TI evidence (graceful degradation).
"""

import hashlib
import json
import logging
import os
import time

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pure-Python Ed25519 (RFC 8032).
# ---------------------------------------------------------------------------

_P = 2 ** 255 - 19
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _ed25519_H(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()


def _ed25519_xrecover(y: int) -> int:
    xx = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = (x * _I) % _P
    if x % 2 != 0:
        x = _P - x
    return x


_GY = 4 * pow(5, _P - 2, _P) % _P
_GX = _ed25519_xrecover(_GY)
_G = (_GX, _GY, 1, _GX * _GY % _P)  # extended coords (X, Y, Z, T)


def _ed25519_edwards_add(p, q):
    (x1, y1, z1, t1) = p
    (x2, y2, z2, t2) = q
    a = ((y1 - x1) * (y2 - x2)) % _P
    b = ((y1 + x1) * (y2 + x2)) % _P
    c = (t1 * 2 * _D * t2) % _P
    d = (z1 * 2 * z2) % _P
    e = (b - a) % _P
    f = (d - c) % _P
    g = (d + c) % _P
    h = (b + a) % _P
    x3 = (e * f) % _P
    y3 = (g * h) % _P
    z3 = (f * g) % _P
    t3 = (e * h) % _P
    return (x3, y3, z3, t3)


def _ed25519_scalarmult(p, e: int):
    q = (0, 1, 1, 0)  # identity
    bits = bin(e)[2:][::-1]
    for bit in bits:
        if bit == "1":
            q = _ed25519_edwards_add(q, p)
        p = _ed25519_edwards_add(p, p)
    return q


def _ed25519_encodepoint(p) -> bytes:
    (x, y, z, _) = p
    zi = pow(z, _P - 2, _P)
    x = (x * zi) % _P
    y = (y * zi) % _P
    bits = bin(y)[2:].zfill(256)[::-1]
    bits = list(bits)
    bits[255] = "1" if x & 1 else "0"
    bits = "".join(bits[::-1])
    return int(bits, 2).to_bytes(32, "little")


def _ed25519_decodepoint(s: bytes):
    y = int.from_bytes(s, "little") & ((1 << 255) - 1)
    sign = (s[31] >> 7) & 1
    x = _ed25519_xrecover(y)
    if x & 1 != sign:
        x = _P - x
    return (x, y, 1, (x * y) % _P)


_L = 2 ** 252 + 27742317777372353535851937790883648493


def _ed25519_publickey(sk: bytes) -> bytes:
    h = _ed25519_H(sk)
    a = int.from_bytes(h[:32], "little")
    a &= ~(1 | (1 << 255))
    a |= 1 << 254
    return _ed25519_encodepoint(_ed25519_scalarmult(_G, a))


def _ed25519_sign(sk: bytes, msg: bytes) -> bytes:
    h = _ed25519_H(sk)
    a = int.from_bytes(h[:32], "little")
    a &= ~(1 | (1 << 255))
    a |= 1 << 254
    pk = _ed25519_encodepoint(_ed25519_scalarmult(_G, a))
    r = int.from_bytes(_ed25519_H(h[32:] + msg), "little") % _L
    big_r = _ed25519_encodepoint(_ed25519_scalarmult(_G, r))
    s = (r + int.from_bytes(
        _ed25519_H(big_r + pk + msg), "little") % _L * a) % _L
    return big_r + s.to_bytes(32, "little")


def _ed25519_verify(pk: bytes, sig: bytes, msg: bytes) -> bool:
    if len(sig) != 64 or len(pk) != 32:
        return False
    try:
        big_a = _ed25519_decodepoint(pk)
        big_r = _ed25519_decodepoint(sig[:32])
    except Exception:
        return False
    s = int.from_bytes(sig[32:], "little")
    if s >= _L:
        return False
    h = int.from_bytes(_ed25519_H(sig[:32] + pk + msg), "little") % _L
    lhs = _ed25519_scalarmult(_G, s)
    rhs = _ed25519_edwards_add(big_r, _ed25519_scalarmult(big_a, h))
    return (_ed25519_encodepoint(lhs) == _ed25519_encodepoint(rhs))


# ---------------------------------------------------------------------------
# Verdict construction and signing.
# ---------------------------------------------------------------------------

def _canonical_bytes(payload: dict) -> bytes:
    """Deterministic JSON encoding for signing."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8")


class VerdictSigner:
    """Issues and verifies signed screening verdicts.

    The private key is read once from MCP_PROXY_SIGNING_KEY (64 hex
    chars = 32 bytes). It is never logged or included in any output.
    """

    def __init__(self, signing_key_hex: str = ""):
        self._sk = None
        self._pk = None
        key_hex = (signing_key_hex or os.environ.get(
            "MCP_PROXY_SIGNING_KEY", "")).strip()
        if key_hex:
            try:
                sk = bytes.fromhex(key_hex)
                if len(sk) != 32:
                    raise ValueError("must be 32 bytes")
                self._sk = sk
                self._pk = _ed25519_publickey(sk)
            except Exception as exc:
                log.error("invalid MCP_PROXY_SIGNING_KEY: %s", exc)

    @property
    def signing_enabled(self) -> bool:
        return self._sk is not None

    @property
    def public_key_hex(self) -> str:
        """Public key for partners to verify verdicts. Safe to share."""
        return self._pk.hex() if self._pk else ""

    def issue(self, decision: str, tool_name: str, content_hash: str,
              evidence: list, level: str = "", score: int = 0,
              reasons: list = None, extra: dict = None,
              poison_category: str = "clean") -> dict:
        """Build a verdict dict, signed when a key is configured.

        decision: "block" | "quarantine" | "flag" | "allow"
        evidence: list of {"type": ..., "id": ..., "detail": ...}
        poison_category: attack taxonomy (prompt_injection, pii_leak,
            malicious_url, kit_match, secret_leak, unknown_synthetic,
            oauth_tampering, credential_exfiltration, behavioral_anomaly,
            attack_chain, policy_deny, policy_approval, clean)
        """
        verdict = {
            "v": 1,
            "ts": time.time(),
            "decision": decision,
            "tool": tool_name,
            "content_hash": content_hash,
            "level": level,
            "score": score,
            "reasons": reasons or [],
            "evidence": evidence or [],
            "poison_category": poison_category,
        }
        if extra:
            verdict["extra"] = extra
        if self.signing_enabled:
            sig = _ed25519_sign(self._sk, _canonical_bytes(verdict))
            verdict["sig"] = sig.hex()
            verdict["pubkey"] = self.public_key_hex
        else:
            verdict["sig"] = ""
            verdict["pubkey"] = ""
        return verdict

    def verify(self, verdict: dict) -> bool:
        """Verify a verdict's signature. Unsigned verdicts return False."""
        sig_hex = verdict.get("sig", "")
        pk_hex = verdict.get("pubkey", "")
        if not sig_hex or not pk_hex:
            return False
        try:
            sig = bytes.fromhex(sig_hex)
            pk = bytes.fromhex(pk_hex)
        except ValueError:
            return False
        unsigned = {k: v for k, v in verdict.items()
                    if k not in ("sig", "pubkey")}
        return _ed25519_verify(pk, sig, _canonical_bytes(unsigned))


def content_hash_of(obj) -> str:
    """SHA-256 hex of the canonical JSON encoding of obj."""
    return hashlib.sha256(_canonical_bytes(obj)).hexdigest()
