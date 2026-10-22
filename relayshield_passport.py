"""
RelayShield Signed Agent Reputation Passport.

A passport is a portable, cryptographically signed JSON record for an agent
identity. RelayShield issues it after running its TAP and PAP agent
verifications and threat screening. Any marketplace can then verify the
passport in one check (locally with RelayShield's public key, or via a
hosted RelayShield check endpoint) without re-running the verifications.

Design notes
------------
* Signing algorithm: Ed25519 only. No algorithm negotiation, by design.
* Signed bytes: the canonical JSON encoding of the passport document
  (keys sorted, no insignificant whitespace, UTF-8). The signature is
  never a field inside the document; it travels alongside it.
* Transport form: ``<payload>.<signature>`` where both parts are
  base64url without padding. The payload part is the canonical JSON
  bytes; the signature part is the 64-byte Ed25519 signature. This is
  JWT-shaped on purpose (familiar to integrators) but is NOT a JWT:
  there is no header segment and no ``alg`` to negotiate.
* Keys in this module are raw 32-byte Ed25519 seeds (private) and raw
  32-byte public keys, accepted as bytes or hex strings.
* Issuance has two modes. Local: sign with a raw seed held by the
  caller. KMS: sign through AWS KMS (class ``KmsPassportSigner``), so
  the private key never leaves KMS. KMS signs Ed25519 keys with the
  pre-hashed variant, Ed25519ph, so the two modes produce different
  signature variants under the same key; verification accepts either
  (see ``verify_passport``). The issued document records which key
  signed it in the ``signing_key`` field: the KMS key id, or a short
  fingerprint of the public key for local issuance. See SPEC.md
  section 10 for key creation, IAM, and rotation.

Backend selection: the module uses the first available Ed25519 backend:
``cryptography``, then PyNaCl, then a bundled pure-Python implementation
of RFC 8032. The pure-Python backend is correct (it is checked against
the RFC 8032 test vectors in test_passport.py) but slow; it exists so
the format can be developed and verified anywhere. Ed25519ph
verification always uses the bundled point arithmetic, because neither
``cryptography`` nor PyNaCl exposes the pre-hashed variant.

See SPEC.md for the full schema, the marketplace verification flow, and
the planned API shape.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

__all__ = [
    "PASSPORT_VERSION",
    "DEFAULT_ISSUER",
    "DEFAULT_TTL_SECONDS",
    "BACKEND",
    "KMS_KEY_ID_ENV",
    "KmsPassportSigner",
    "generate_keypair",
    "public_key_fingerprint",
    "raw_public_key_from_spki",
    "build_passport_document",
    "issue_passport",
    "sign_document",
    "encode_compact",
    "decode_compact",
    "verify_passport",
    "canonical_json",
]

PASSPORT_VERSION = "1.0"
DEFAULT_ISSUER = "relayshield.net"
DEFAULT_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days; see SPEC.md open decisions.

_VERIFICATION_STATUSES = ("verified", "rejected", "not_performed")
_REQUIRED_FIELDS = (
    "version",
    "passport_id",
    "issuer",
    "subject",
    "verifications",
    "screening",
    "issued_at",
    "expires_at",
)


# --------------------------------------------------------------------------
# Ed25519 backends
# --------------------------------------------------------------------------

try:  # Preferred: PyCA cryptography
    from cryptography.exceptions import InvalidSignature as _CryptoInvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey as _CryptoPrivateKey,
        Ed25519PublicKey as _CryptoPublicKey,
    )

    BACKEND = "cryptography"
except ImportError:  # pragma: no cover - depends on environment
    try:
        import nacl.exceptions as _nacl_exceptions
        import nacl.signing as _nacl_signing

        BACKEND = "pynacl"
    except ImportError:
        BACKEND = "pure-python (RFC 8032)"


def _ed25519_public_from_seed(seed: bytes) -> bytes:
    if BACKEND == "cryptography":
        key = _CryptoPrivateKey.from_private_bytes(seed)
        from cryptography.hazmat.primitives import serialization

        return key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    if BACKEND == "pynacl":
        return bytes(_nacl_signing.SigningKey(seed).verify_key)
    return _pure_publickey(seed)


def _ed25519_sign(seed: bytes, message: bytes) -> bytes:
    if BACKEND == "cryptography":
        return _CryptoPrivateKey.from_private_bytes(seed).sign(message)
    if BACKEND == "pynacl":
        return _nacl_signing.SigningKey(seed).sign(message).signature
    return _pure_sign(seed, message)


def _ed25519_verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    if len(public_key) != 32 or len(signature) != 64:
        return False
    if BACKEND == "cryptography":
        try:
            _CryptoPublicKey.from_public_bytes(public_key).verify(signature, message)
            return True
        except _CryptoInvalidSignature:
            return False
    if BACKEND == "pynacl":
        try:
            _nacl_signing.VerifyKey(public_key).verify(message, signature)
            return True
        except _nacl_exceptions.BadSignatureError:
            return False
    return _pure_verify(public_key, message, signature)


# --- Pure-Python Ed25519 (RFC 8032 reference formulas) -------------------
# Correct but not constant-time and not fast. Development/fallback only.

_q = 2**255 - 19
_l = 2**252 + 27742317777372353535851937790883648493
_d = -121665 * pow(121666, _q - 2, _q) % _q
_I = pow(2, (_q - 1) // 4, _q)


def _pure_hash(message: bytes) -> bytes:
    return hashlib.sha512(message).digest()


def _pure_bit(h: bytes, i: int) -> int:
    return (h[i // 8] >> (i % 8)) & 1


def _pure_secret_expand(seed: bytes):
    h = _pure_hash(seed)
    a = 2 ** (256 - 2) + sum(
        2**i * _pure_bit(h, i) for i in range(3, 256 - 2)
    )
    return a, h[32:64]


def _pure_xrecover(y: int) -> int:
    xx = (y * y - 1) * pow(_d * y * y + 1, _q - 2, _q) % _q
    x = pow(xx, (_q + 3) // 8, _q)
    if (x * x - xx) % _q != 0:
        x = (x * _I) % _q
    if x % 2 != 0:
        x = _q - x
    return x


_By = 4 * pow(5, _q - 2, _q) % _q
_B = [_pure_xrecover(_By), _By]


def _pure_edwards(P, Q):
    x1, y1 = P
    x2, y2 = Q
    t = _d * x1 * x2 * y1 * y2 % _q
    x3 = (x1 * y2 + x2 * y1) * pow(1 + t, _q - 2, _q) % _q
    y3 = (y1 * y2 + x1 * x2) * pow(1 - t, _q - 2, _q) % _q
    return [x3, y3]


def _pure_scalarmult(P, e: int):
    if e == 0:
        return [0, 1]
    Q = _pure_scalarmult(P, e // 2)
    Q = _pure_edwards(Q, Q)
    if e & 1:
        Q = _pure_edwards(Q, P)
    return Q


def _pure_encodepoint(P) -> bytes:
    x, y = P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _pure_decodepoint(data: bytes):
    v = int.from_bytes(data, "little")
    y = v & ((1 << 255) - 1)
    sign = (v >> 255) & 1
    x = _pure_xrecover(y)
    if x & 1 != sign:
        x = _q - x
    return [x, y]


def _pure_publickey(seed: bytes) -> bytes:
    a, _ = _pure_secret_expand(seed)
    return _pure_encodepoint(_pure_scalarmult(_B, a))


def _pure_sign(seed: bytes, message: bytes) -> bytes:
    a, prefix = _pure_secret_expand(seed)
    public_key = _pure_encodepoint(_pure_scalarmult(_B, a))
    r = int.from_bytes(_pure_hash(prefix + message), "little") % _l
    R_encoded = _pure_encodepoint(_pure_scalarmult(_B, r))
    h = int.from_bytes(_pure_hash(R_encoded + public_key + message), "little") % _l
    S = (r + h * a) % _l
    return R_encoded + S.to_bytes(32, "little")


def _pure_verify_equation(public_key: bytes, signature: bytes, h: int) -> bool:
    """The Ed25519 group equation [S]B == R + [h]A for a given challenge h.

    Pure Ed25519 and Ed25519ph differ only in how the challenge h is
    computed, so both verification paths share this check.
    """
    try:
        R = _pure_decodepoint(signature[:32])
        A = _pure_decodepoint(public_key)
    except Exception:
        return False
    S = int.from_bytes(signature[32:], "little")
    if S >= _l:
        return False
    return _pure_scalarmult(_B, S) == _pure_edwards(R, _pure_scalarmult(A, h))


def _pure_verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    h = int.from_bytes(
        _pure_hash(signature[:32] + public_key + message), "little"
    ) % _l
    return _pure_verify_equation(public_key, signature, h)


# --- Ed25519ph (RFC 8032 section 5.1, empty context) ---------------------
# AWS KMS signs Ed25519 keys with the pre-hashed variant (see the KMS
# section below), so passports issued through KMS carry Ed25519ph
# signatures, not pure Ed25519 ones. The challenge hash is computed over
# a domain separator, then R, A, and SHA-512(message). Neither
# `cryptography` nor PyNaCl exposes Ed25519ph, so verification uses the
# bundled point arithmetic regardless of the selected backend; that is
# fine because the pure-Python backend is always available.

_ED25519PH_DOM = b"SigEd25519 no Ed25519 collisions" + bytes((1, 0))


def _ed25519ph_verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    if len(public_key) != 32 or len(signature) != 64:
        return False
    digest = hashlib.sha512(message).digest()
    h = int.from_bytes(
        _pure_hash(_ED25519PH_DOM + signature[:32] + public_key + digest),
        "little",
    ) % _l
    return _pure_verify_equation(public_key, signature, h)


def _ed25519ph_sign_prehashed(seed: bytes, digest: bytes) -> bytes:
    """Ed25519ph signature over a precomputed SHA-512 digest.

    This mirrors exactly what AWS KMS computes for ED25519_PH_SHA_512
    with MessageType=DIGEST. The module never signs this way in
    production (KMS does); the implementation exists as the reference
    construction, and so tests can emulate KMS faithfully.
    """
    if len(digest) != 64:
        raise ValueError("Ed25519ph digest must be 64 bytes (SHA-512)")
    a, prefix = _pure_secret_expand(seed)
    public_key = _pure_encodepoint(_pure_scalarmult(_B, a))
    r = int.from_bytes(_pure_hash(_ED25519PH_DOM + prefix + digest), "little") % _l
    r_encoded = _pure_encodepoint(_pure_scalarmult(_B, r))
    h = int.from_bytes(
        _pure_hash(_ED25519PH_DOM + r_encoded + public_key + digest), "little"
    ) % _l
    s = (r + h * a) % _l
    return r_encoded + s.to_bytes(32, "little")


def _ed25519ph_sign(seed: bytes, message: bytes) -> bytes:
    return _ed25519ph_sign_prehashed(seed, hashlib.sha512(message).digest())


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _coerce_key(key, expected_len: int, name: str) -> bytes:
    if isinstance(key, str):
        try:
            key = bytes.fromhex(key)
        except ValueError as exc:
            raise ValueError(f"{name} must be bytes or a hex string") from exc
    if not isinstance(key, (bytes, bytearray)) or len(key) != expected_len:
        raise ValueError(f"{name} must be {expected_len} bytes")
    return bytes(key)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    if not isinstance(data, str):
        raise ValueError("compact form must be a string")
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _isoformat(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO 8601 string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def canonical_json(document: dict) -> bytes:
    """The exact bytes that get signed: canonical JSON, UTF-8."""
    return json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def generate_keypair():
    """Return (private_seed_hex, public_key_hex). For tests and demos only.

    Production issuer keys must be generated and held in a KMS/HSM; see
    SPEC.md. Never hard-code or commit an issuer private key.
    """
    seed = os.urandom(32)
    return seed.hex(), _ed25519_public_from_seed(seed).hex()


# --------------------------------------------------------------------------
# AWS KMS signing backend
# --------------------------------------------------------------------------

KMS_KEY_ID_ENV = "RELAYSHIELD_PASSPORT_KMS_KEY_ID"
_KMS_SIGNING_ALGORITHM = "ED25519_PH_SHA_512"
_ED25519_SPKI_PREFIX = bytes.fromhex("302a300506032b6570032100")


def public_key_fingerprint(public_key) -> str:
    """Short fingerprint of a raw Ed25519 public key: SHA-256, 32 hex chars.

    Used as the document's signing_key value for locally held keys,
    where there is no KMS key id to record.
    """
    pub = _coerce_key(public_key, 32, "public_key")
    return hashlib.sha256(pub).hexdigest()[:32]


def raw_public_key_from_spki(der: bytes) -> bytes:
    """Extract the raw 32-byte Ed25519 public key from an SPKI DER blob.

    This is the encoding AWS KMS GetPublicKey returns. An Ed25519 SPKI
    is a fixed 12-byte prefix (a SEQUENCE wrapping the OID 1.3.101.112
    and a BIT STRING header) followed by the 32 raw key bytes, so the
    extraction is a prefix check and a slice, not a DER parse.
    """
    if (
        not isinstance(der, (bytes, bytearray))
        or len(der) != len(_ED25519_SPKI_PREFIX) + 32
        or not bytes(der).startswith(_ED25519_SPKI_PREFIX)
    ):
        raise ValueError("not an Ed25519 SubjectPublicKeyInfo DER encoding")
    return bytes(der)[len(_ED25519_SPKI_PREFIX):]


class KmsPassportSigner:
    """Issue passport signatures through an AWS KMS Ed25519 key.

    The private key never leaves KMS. Signing uses the pre-hash flow:
    MessageType=DIGEST with SigningAlgorithm ED25519_PH_SHA_512 over the
    SHA-512 digest of the canonical payload bytes. The alternative RAW
    flow (ED25519_SHA_512) caps the message at 4096 bytes; a passport
    is usually smaller, but nothing in the format guarantees it stays
    under that cap as verifications, references, and future fields
    grow, so issuance pre-hashes and payload size is never a signing
    constraint. The resulting signatures are Ed25519ph (RFC 8032
    section 5.1, empty context); verify_passport accepts that variant
    alongside pure Ed25519, so no other behavior changes.

    boto3 is imported lazily, only when a KMS call is actually made, so
    importing this module and using local keys needs no AWS SDK and no
    AWS account. Tests (and non-boto3 environments) can inject a stub
    client via the ``client`` parameter.

    The same object serves verifiers: ``public_key()`` fetches the key
    once via GetPublicKey and caches it, after which verification is
    fully local and offline. A verifier that already holds the raw
    public key does not need this class, or AWS, at all.
    """

    def __init__(
        self,
        key_id: str | None = None,
        *,
        client=None,
        region_name: str | None = None,
    ):
        self._key_id = key_id or os.environ.get(KMS_KEY_ID_ENV)
        if not self._key_id:
            raise ValueError(
                "KMS key id required: pass key_id or set " + KMS_KEY_ID_ENV
            )
        self._client = client
        self._region_name = region_name
        self._public_key: bytes | None = None
        self._resolved_key_id: str | None = None

    def _kms(self):
        if self._client is None:
            import boto3  # Lazy: only the KMS path needs the AWS SDK.

            self._client = (
                boto3.client("kms", region_name=self._region_name)
                if self._region_name
                else boto3.client("kms")
            )
        return self._client

    @property
    def signing_key(self) -> str:
        """The value recorded in the document's signing_key field.

        The canonical KeyId reported by KMS once the public key has
        been fetched; the configured id (which may be an alias or an
        ARN) until then.
        """
        return self._resolved_key_id or self._key_id

    def public_key(self) -> bytes:
        """Raw 32-byte Ed25519 public key, fetched once and cached."""
        if self._public_key is None:
            response = self._kms().get_public_key(KeyId=self._key_id)
            key_spec = response.get("KeySpec")
            if key_spec is not None and key_spec != "ECC_NIST_EDWARDS25519":
                raise ValueError(
                    f"KMS key is {key_spec}, not ECC_NIST_EDWARDS25519"
                )
            self._public_key = raw_public_key_from_spki(response["PublicKey"])
            self._resolved_key_id = response.get("KeyId") or self._key_id
        return self._public_key

    def sign(self, message: bytes) -> bytes:
        """Sign message bytes via KMS and return the 64-byte signature."""
        digest = hashlib.sha512(message).digest()
        response = self._kms().sign(
            KeyId=self._key_id,
            Message=digest,
            MessageType="DIGEST",
            SigningAlgorithm=_KMS_SIGNING_ALGORITHM,
        )
        signature = response["Signature"]
        if len(signature) != 64:
            raise ValueError("KMS returned a signature that is not 64 bytes")
        return signature


# --------------------------------------------------------------------------
# Issuance
# --------------------------------------------------------------------------


def _validate_verification(name: str, entry) -> dict:
    if not isinstance(entry, dict):
        raise ValueError(f"verifications.{name} must be an object")
    status = entry.get("status")
    if status not in _VERIFICATION_STATUSES:
        raise ValueError(
            f"verifications.{name}.status must be one of {_VERIFICATION_STATUSES}"
        )
    cleaned = {"status": status}
    if entry.get("verified_at") is not None:
        _parse_timestamp(entry["verified_at"])  # raises if malformed
        cleaned["verified_at"] = entry["verified_at"]
    if status == "verified" and "verified_at" not in cleaned:
        raise ValueError(f"verifications.{name}.verified_at is required when verified")
    if entry.get("reference") is not None:
        cleaned["reference"] = str(entry["reference"])
    return cleaned


def build_passport_document(
    *,
    subject: dict,
    verifications: dict,
    screening: dict,
    issuer: str = DEFAULT_ISSUER,
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    passport_id: str | None = None,
    signing_key: str | None = None,
) -> dict:
    """Assemble and validate a passport document (unsigned).

    ``signing_key`` identifies the issuer key that will sign: a KMS key
    id, or a public-key fingerprint for a locally held key. It sits
    inside the document, so it is covered by the signature and cannot
    be swapped by a presenter. Optional: documents built without it are
    the pre-KMS format and remain verifiable.
    """
    if not isinstance(subject, dict) or not subject.get("agent_id"):
        raise ValueError("subject.agent_id is required")
    clean_subject = {"agent_id": str(subject["agent_id"])}
    if subject.get("wallet"):
        clean_subject["wallet"] = str(subject["wallet"])
    elif not subject.get("did"):
        raise ValueError("subject requires a wallet or a did")
    if subject.get("did"):
        clean_subject["did"] = str(subject["did"])

    if not isinstance(verifications, dict):
        raise ValueError("verifications must be an object")
    clean_verifications = {
        name: _validate_verification(name, verifications[name])
        for name in ("tap", "pap")
        if name in verifications
    }
    if not clean_verifications:
        raise ValueError("verifications requires at least one of: tap, pap")

    if not isinstance(screening, dict):
        raise ValueError("screening must be an object")
    checks_total = int(screening.get("checks_total", 0))
    flags_total = int(screening.get("flags_total", 0))
    if checks_total < 0 or flags_total < 0 or flags_total > checks_total:
        raise ValueError("screening counts must satisfy 0 <= flags_total <= checks_total")
    clean_screening = {"checks_total": checks_total, "flags_total": flags_total}
    if screening.get("last_screened_at") is not None:
        _parse_timestamp(screening["last_screened_at"])
        clean_screening["last_screened_at"] = screening["last_screened_at"]

    issued = issued_at or datetime.now(timezone.utc)
    expires = expires_at or (issued + timedelta(seconds=ttl_seconds))
    if expires <= issued:
        raise ValueError("expires_at must be after issued_at")

    document = {
        "version": PASSPORT_VERSION,
        "passport_id": passport_id or f"rsp_{uuid.uuid4().hex}",
        "issuer": issuer,
        "subject": clean_subject,
        "verifications": clean_verifications,
        "screening": clean_screening,
        "issued_at": _isoformat(issued),
        "expires_at": _isoformat(expires),
    }
    if signing_key is not None:
        document["signing_key"] = str(signing_key)
    return document


def sign_document(private_key, document: dict) -> bytes:
    seed = _coerce_key(private_key, 32, "private_key")
    return _ed25519_sign(seed, canonical_json(document))


def encode_compact(document: dict, signature: bytes) -> str:
    """Compact transport form: base64url(payload) + '.' + base64url(signature)."""
    if len(signature) != 64:
        raise ValueError("signature must be 64 bytes")
    return f"{_b64url_encode(canonical_json(document))}.{_b64url_encode(signature)}"


def decode_compact(compact: str):
    """Split a compact passport into (document, signature). Raises ValueError."""
    parts = compact.split(".")
    if len(parts) != 2:
        raise ValueError("compact passport must have exactly two segments")
    payload_bytes = _b64url_decode(parts[0])
    signature = _b64url_decode(parts[1])
    if len(signature) != 64:
        raise ValueError("signature segment must decode to 64 bytes")
    document = json.loads(payload_bytes.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("passport payload must be a JSON object")
    # The payload segment must be the canonical encoding, byte for byte, so
    # that what the verifier re-encodes is exactly what was signed.
    if _b64url_encode(canonical_json(document)) != parts[0]:
        raise ValueError("payload is not canonical JSON")
    return document, signature


def issue_passport(
    private_key=None,
    *,
    signer: KmsPassportSigner | None = None,
    subject: dict,
    verifications: dict,
    screening: dict,
    issuer: str = DEFAULT_ISSUER,
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    passport_id: str | None = None,
) -> dict:
    """Issue a passport. Returns {"passport": document, "compact": str}.

    Sign in exactly one of two ways:

    * ``private_key``: a locally held Ed25519 seed (bytes or hex).
      The document's signing_key is a fingerprint of the public key.
    * ``signer``: a KmsPassportSigner; AWS KMS signs and the private
      key never leaves KMS. The document's signing_key is the KMS
      key id.
    """
    if (private_key is None) == (signer is None):
        raise ValueError("pass exactly one of private_key or signer")
    if signer is not None:
        # Resolves and caches the canonical KMS key id (and warms the
        # public-key cache a verifier on this host will want anyway).
        signer.public_key()
        signing_key = signer.signing_key
        seed = None
    else:
        seed = _coerce_key(private_key, 32, "private_key")
        signing_key = public_key_fingerprint(_ed25519_public_from_seed(seed))
    document = build_passport_document(
        subject=subject,
        verifications=verifications,
        screening=screening,
        issuer=issuer,
        issued_at=issued_at,
        expires_at=expires_at,
        ttl_seconds=ttl_seconds,
        passport_id=passport_id,
        signing_key=signing_key,
    )
    payload = canonical_json(document)
    if signer is not None:
        signature = signer.sign(payload)
    else:
        signature = _ed25519_sign(seed, payload)
    return {"passport": document, "compact": encode_compact(document, signature)}


# --------------------------------------------------------------------------
# Verification (the marketplace side)
# --------------------------------------------------------------------------


def verify_passport(
    compact: str,
    public_key,
    *,
    expected_issuer: str = DEFAULT_ISSUER,
    now: datetime | None = None,
) -> dict:
    """Verify a compact passport. Returns a structured verdict:

    {
      "valid": bool,
      "status": "valid" | "malformed" | "unsupported_version" |
                "invalid_signature" | "issuer_mismatch" | "expired",
      "checks": {"well_formed": bool, "signature": bool|None,
                 "issuer": bool|None, "not_expired": bool|None},
      "passport": document | None,
      "errors": [str, ...],
    }

    Checks run in a fixed order: structure, version, signature, issuer,
    expiry. A passport is valid only if every check passes. Revocation is
    deliberately NOT checked here; it needs the hosted status endpoint
    described in SPEC.md.
    """
    verdict = {
        "valid": False,
        "status": "malformed",
        "checks": {
            "well_formed": False,
            "signature": None,
            "issuer": None,
            "not_expired": None,
        },
        "passport": None,
        "errors": [],
    }
    try:
        pub = _coerce_key(public_key, 32, "public_key")
        document, signature = decode_compact(compact)
        missing = [f for f in _REQUIRED_FIELDS if f not in document]
        if missing:
            raise ValueError(f"missing required fields: {', '.join(missing)}")
        _parse_timestamp(document["issued_at"])
        _parse_timestamp(document["expires_at"])
    except (ValueError, TypeError, KeyError) as exc:
        verdict["errors"].append(str(exc))
        return verdict

    verdict["checks"]["well_formed"] = True
    verdict["passport"] = document

    if document["version"] != PASSPORT_VERSION:
        verdict["status"] = "unsupported_version"
        verdict["errors"].append(f"unsupported version: {document['version']}")
        return verdict

    # Locally issued passports carry pure Ed25519 signatures; KMS-issued
    # ones carry Ed25519ph signatures (KMS signs Ed25519 keys with the
    # pre-hashed variant). Both are signatures by the issuer key over
    # these exact bytes, so accept whichever variant verifies. The
    # document's signing_key field tells the verifier which key to use;
    # it does not change this check.
    payload = canonical_json(document)
    signature_ok = _ed25519_verify(pub, payload, signature) or _ed25519ph_verify(
        pub, payload, signature
    )
    verdict["checks"]["signature"] = signature_ok
    if not signature_ok:
        verdict["status"] = "invalid_signature"
        verdict["errors"].append("Ed25519 signature does not verify")
        return verdict

    issuer_ok = document["issuer"] == expected_issuer
    verdict["checks"]["issuer"] = issuer_ok
    if not issuer_ok:
        verdict["status"] = "issuer_mismatch"
        verdict["errors"].append(
            f"issuer {document['issuer']!r} != expected {expected_issuer!r}"
        )
        return verdict

    moment = now or datetime.now(timezone.utc)
    not_expired = _parse_timestamp(document["expires_at"]) > moment
    verdict["checks"]["not_expired"] = not_expired
    if not not_expired:
        verdict["status"] = "expired"
        verdict["errors"].append(f"expired at {document['expires_at']}")
        return verdict

    verdict["valid"] = True
    verdict["status"] = "valid"
    return verdict


if __name__ == "__main__":  # Small self-demo with throwaway keys.
    priv_hex, pub_hex = generate_keypair()
    issued = issue_passport(
        priv_hex,
        subject={"agent_id": "agent_demo_001", "wallet": "0x0000000000000000000000000000000000000000"},
        verifications={
            "tap": {"status": "verified", "verified_at": "2026-10-21T12:00:00Z"},
            "pap": {"status": "verified", "verified_at": "2026-10-21T12:00:05Z"},
        },
        screening={"checks_total": 128, "flags_total": 0, "last_screened_at": "2026-10-21T12:00:05Z"},
    )
    print("backend:", BACKEND)
    print("compact:", issued["compact"][:72] + "...")
    print("verdict:", verify_passport(issued["compact"], pub_hex)["status"])
