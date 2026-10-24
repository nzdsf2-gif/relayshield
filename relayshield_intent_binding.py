"""Pre-payment intent binding for agent commerce.

Innovation memo item 6 ("screen the basket"): at the moment an agent
pays, bind the payment intent to the actual artifacts: the
counterparty, the invoice, the cart. Everything is screened at binding
time, and at settlement time the executed payment is checked against
the signed binding before funds release. A payment that drifts from
what was screened (different counterparty, larger amount, edited
invoice) does not settle.

Lifecycle:

  1. create_binding(intent): the payer agent declares payer,
     counterparty, amount, currency, and the artifact set (invoice /
     cart descriptors, optionally an invoice image). The counterparty
     and every artifact are screened through pluggable screener hooks.
     A flagged screen refuses the binding. A clean pass produces a
     signed, expiring, single-use binding record.
  2. verify_at_settlement(binding, executed): the rail or facilitator
     presents the executed payment details. They must match the
     binding exactly (counterparty, payer, currency, amount within
     tolerance, artifact hashes unchanged), the binding must be
     unexpired and unconsumed, and its signature must verify. An
     "allow" consumes the binding, so it cannot be replayed.

Signing: Ed25519, through a signer key interface. Ed25519 over HMAC
because settlement verification can happen at a different party than
issuance (a rail, a facilitator, a marketplace): with a shared-secret
MAC, every verifier could also forge bindings. A public key verifies
without conferring issuance power. This also matches RelayShield's
existing signed artifacts (MCP proxy verdicts, the agent reputation
passport), so one verification story covers all three. The
implementation below is the same zero-dependency pure-Python RFC 8032
code pattern the MCP proxy ships, so this module has no third-party
dependencies; production signers plug in behind the Signer interface
(for example a KMS-backed signer, as the passport uses).

Verdict wording follows RelayShield's standing rule: a screen that
finds nothing reports "no_flags_found" with caveats. Nothing in this
module ever calls a counterparty, an artifact, or a payment "safe".

v2 (decisions applied 2026-10-23, see DESIGN.md):

  - A real invoice-image OCR screener (OcrInvoiceImageScreener)
    replaces the stub as the intended production hook. It extracts
    text through a pluggable TextExtractor, cross-checks the totals
    and payee identifiers the image actually renders against the
    bound artifacts, and reports mismatches as ADVISORY verdicts:
    they flag the binding and bake a step-up requirement into the
    signed record, but they do not hard-block unless policy says so
    (image_ocr.hard_block). OCR false positives are the known risk;
    the precision gain is catching image substitution and
    image-vs-artifact divergence that byte hashing cannot see.
  - TTL and amount tolerance are policy, not code constants:
    BindingPolicy loads from a YAML file in the mcp_proxy policy
    style (see intent_binding.policy.example.yaml).
  - Step-up requirements are baked into the binding record at
    issuance (record["step_up"], inside the signed payload), not
    managed as a separate flow.
  - Identifier canonicalization is per rail: intent.rail names a
    canonicalization policy ("default", "opaque", or a registered
    custom callable), and the name is recorded in the signed record
    (record["id_policy"]) so settlement applies the same policy.
"""

import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Callable, Optional, Protocol

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pure-Python Ed25519 (RFC 8032). Same implementation pattern as
# mcp_proxy/verdicts.py so this module keeps the zero-dependency
# property. Slow but more than fast enough for pay-moment signing.
# ---------------------------------------------------------------------------

_P = 2 ** 255 - 19
_D = -121665 * pow(121666, _P - 2, _P) % _P
_I = pow(2, (_P - 1) // 4, _P)
_L = 2 ** 252 + 27742317777372353535851937790883648493


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


def _ed25519_clamp(h: bytes) -> int:
    a = int.from_bytes(h[:32], "little")
    a &= ~(1 | (1 << 255))
    a |= 1 << 254
    return a


def _ed25519_publickey(seed: bytes) -> bytes:
    a = _ed25519_clamp(_ed25519_H(seed))
    return _ed25519_encodepoint(_ed25519_scalarmult(_G, a))


def _ed25519_sign(seed: bytes, msg: bytes) -> bytes:
    h = _ed25519_H(seed)
    a = _ed25519_clamp(h)
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
# Canonical encoding and hashing (same conventions as the MCP proxy:
# sorted-key compact JSON; SHA-256 content hashes).
# ---------------------------------------------------------------------------

def canonical_bytes(payload) -> bytes:
    """Deterministic JSON encoding used for signing and hashing."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8")


def content_hash_of(obj) -> str:
    """SHA-256 hex of the canonical JSON encoding of obj."""
    return hashlib.sha256(canonical_bytes(obj)).hexdigest()


# ---------------------------------------------------------------------------
# Signer key interface.
# ---------------------------------------------------------------------------

class Signer(Protocol):
    """Anything that can produce Ed25519 signatures for bindings.

    Production deployments plug a KMS- or HSM-backed signer in behind
    this interface; the binding logic never touches key material
    directly.
    """

    @property
    def key_id(self) -> str:
        ...

    @property
    def public_key_hex(self) -> str:
        ...

    def sign(self, msg: bytes) -> bytes:
        ...


class Ed25519Signer:
    """Pure-Python Ed25519 signer from a 32-byte seed (hex).

    The seed comes from the constructor argument or the
    INTENT_BINDING_SIGNING_KEY environment variable. It is never
    logged and never appears in any binding record.
    """

    def __init__(self, seed_hex: str = "", key_id: str = "local-ed25519"):
        seed_hex = (seed_hex or os.environ.get(
            "INTENT_BINDING_SIGNING_KEY", "")).strip()
        if not seed_hex:
            raise ValueError(
                "no signing seed: pass seed_hex or set "
                "INTENT_BINDING_SIGNING_KEY")
        seed = bytes.fromhex(seed_hex)
        if len(seed) != 32:
            raise ValueError("Ed25519 seed must be 32 bytes")
        self._seed = seed
        self._pk = _ed25519_publickey(seed)
        self._key_id = key_id

    @property
    def key_id(self) -> str:
        return self._key_id

    @property
    def public_key_hex(self) -> str:
        return self._pk.hex()

    def sign(self, msg: bytes) -> bytes:
        return _ed25519_sign(self._seed, msg)


def verify_signature(public_key_hex: str, signature_hex: str,
                     msg: bytes) -> bool:
    """Verify an Ed25519 signature against a hex public key."""
    try:
        pk = bytes.fromhex(public_key_hex)
        sig = bytes.fromhex(signature_hex)
    except (ValueError, TypeError):
        return False
    return _ed25519_verify(pk, sig, msg)


# ---------------------------------------------------------------------------
# Screening model and hooks.
# ---------------------------------------------------------------------------

# Screen outcome vocabulary. "no_flags_found" is the best outcome a
# screen can report; it is a statement about the corpus at screening
# time, never a claim that anything is safe.
STATUS_NO_FLAGS = "no_flags_found"
STATUS_FLAGGED = "flagged"
STATUS_NOT_EVALUATED = "not_evaluated"

_SCREEN_CAVEAT = (
    "screening reflects the RelayShield corpus at binding time; "
    "no flags found is not a guarantee of legitimacy"
)


@dataclass
class ScreenResult:
    """Outcome of one screening hook.

    advisory marks a flagged result that policy treats as a flag,
    not a veto: the OCR image screener produces advisory flags
    because OCR mismatches can be extraction error rather than
    fraud. The binder records an advisory verdict on the binding
    and bakes a step-up requirement into the record; it refuses
    the binding only when policy sets image_ocr.hard_block. The
    counterparty and artifact screeners never produce advisory
    results: their flags are corpus verdicts, not extraction
    guesses, and they refuse as before.
    """
    status: str = STATUS_NO_FLAGS
    reasons: list = field(default_factory=list)
    caveats: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    advisory: bool = False

    @property
    def flagged(self) -> bool:
        return self.status == STATUS_FLAGGED

    @property
    def evaluated(self) -> bool:
        return self.status != STATUS_NOT_EVALUATED

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reasons": list(self.reasons),
            "caveats": list(self.caveats),
            "evidence": list(self.evidence),
            "advisory": bool(self.advisory),
        }

    @classmethod
    def no_flags(cls, evidence: list = None) -> "ScreenResult":
        return cls(status=STATUS_NO_FLAGS, reasons=["no flags found"],
                   caveats=[_SCREEN_CAVEAT], evidence=evidence or [])

    @classmethod
    def flagged_result(cls, reasons: list,
                       evidence: list = None) -> "ScreenResult":
        return cls(status=STATUS_FLAGGED, reasons=list(reasons),
                   evidence=evidence or [])

    @classmethod
    def advisory_result(cls, reasons: list,
                        evidence: list = None) -> "ScreenResult":
        """A flagged result that flags-and-steps-up rather than
        refusing outright (the OCR posture)."""
        return cls(status=STATUS_FLAGGED, reasons=list(reasons),
                   caveats=["advisory verdict: recorded on the "
                            "binding with a step-up requirement; "
                            "not a hard block unless policy sets "
                            "image_ocr.hard_block"],
                   evidence=evidence or [], advisory=True)

    @classmethod
    def not_evaluated(cls, why: str) -> "ScreenResult":
        return cls(status=STATUS_NOT_EVALUATED, reasons=[why],
                   caveats=["no verdict is expressed for this input"])


class CounterpartyScreener(Protocol):
    """Screens the payment counterparty (domain, URL, wallet, email,
    or marketplace service id) against threat intelligence."""

    def screen_counterparty(self, counterparty: str,
                            context: dict) -> ScreenResult:
        ...


class ArtifactScreener(Protocol):
    """Screens one artifact descriptor (invoice fields, cart line
    items) for fraud signals: lookalike payee details in the invoice
    body, kit fingerprints, mismatched totals, and similar."""

    def screen_artifact(self, artifact: "Artifact",
                        context: dict) -> ScreenResult:
        ...


class InvoiceImageScreener(Protocol):
    """Screenshot-to-verdict hook for invoice images.

    A production implementation runs OCR over the image, extracts the
    payee, amounts, and payment instructions as rendered (not as the
    agent claims they are), and screens the extracted indicators.
    """

    def screen_invoice_image(self, image_ref: str, image_sha256: str,
                             context: dict) -> ScreenResult:
        ...


class NotEvaluatedImageScreener:
    """Stub invoice-image screener.

    Returns "not_evaluated" rather than inventing a verdict: until the
    OCR pipeline is wired, this build expresses no opinion on invoice
    images, and the binding record says so.
    """

    def screen_invoice_image(self, image_ref: str, image_sha256: str,
                             context: dict) -> ScreenResult:
        return ScreenResult.not_evaluated(
            "invoice image screening is not wired in this build; "
            "the image was hashed and bound but not evaluated")


# ---------------------------------------------------------------------------
# Invoice image OCR (v2).
#
# The OCR screener cross-checks what an invoice image actually
# renders (extracted totals, extracted payee identifiers) against
# the artifacts the binding covers. This catches two things byte
# hashing cannot: a substituted image whose descriptor was replayed
# honestly but whose rendered content is a different invoice, and an
# image that diverges from its own descriptor (descriptor says
# $25.00 to seller.example; the rendered invoice says $2,500.00 to
# an unknown wallet).
#
# OCR is fallible, so every mismatch verdict is ADVISORY: it flags
# the binding and triggers a baked-in step-up requirement, and it
# hard-blocks only when policy sets image_ocr.hard_block. See
# DESIGN.md v2 for the production OCR requirements.
# ---------------------------------------------------------------------------

class OCRUnavailableError(RuntimeError):
    """Raised by a TextExtractor when no OCR engine can run."""


class TextExtractor(Protocol):
    """Extracts text from image bytes. Implementations must raise
    OCRUnavailableError (not return empty text) when no OCR engine
    is available, so 'engine missing' is never confused with 'image
    contained no text'."""

    def extract_text(self, image_bytes: bytes) -> str:
        ...


class FunctionTextExtractor:
    """Adapts any bytes -> str callable to a TextExtractor. The
    production seam for a hosted OCR client (or the MSGSCAN
    pipeline); also what the tests drive."""

    def __init__(self, fn: Callable[[bytes], str]):
        self._fn = fn

    def extract_text(self, image_bytes: bytes) -> str:
        return self._fn(image_bytes)


def _image_suffix(image_bytes: bytes) -> str:
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if image_bytes[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return ".webp"
    return ".png"


class TesseractTextExtractor:
    """TextExtractor backed by tesseract.

    Uses pytesseract (with Pillow) when importable; otherwise falls
    back to the `tesseract` binary on PATH. Raises
    OCRUnavailableError when neither exists, which is the case in
    the build sandbox: no tesseract binary, no pytesseract. The
    OcrInvoiceImageScreener converts that to an honest
    not_evaluated verdict rather than a fake pass. Production needs
    one of the two paths installed; DESIGN.md v2 lists the exact
    requirements.
    """

    def __init__(self, lang: str = "eng", psm: str = "6"):
        self._lang = lang
        self._psm = psm

    @classmethod
    def available(cls) -> bool:
        try:
            import pytesseract  # noqa: F401
            return True
        except ImportError:
            pass
        return shutil.which("tesseract") is not None

    def extract_text(self, image_bytes: bytes) -> str:
        if not image_bytes:
            raise OCRUnavailableError("no image bytes supplied")
        # Path 1: pytesseract + Pillow.
        try:
            import io

            import pytesseract
            from PIL import Image

            image = Image.open(io.BytesIO(image_bytes))
            config = f"--psm {self._psm}"
            return pytesseract.image_to_string(
                image, lang=self._lang, config=config)
        except ImportError:
            pass
        # Path 2: the tesseract CLI.
        exe = shutil.which("tesseract")
        if exe is None:
            raise OCRUnavailableError(
                "no OCR engine available: pytesseract is not "
                "installed and no tesseract binary is on PATH")
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                    suffix=_image_suffix(image_bytes),
                    delete=False) as fh:
                fh.write(image_bytes)
                tmp_path = fh.name
            proc = subprocess.run(
                [exe, tmp_path, "stdout", "--psm", self._psm,
                 "-l", self._lang],
                capture_output=True, timeout=60)
            if proc.returncode != 0:
                raise OCRUnavailableError(
                    "tesseract exited "
                    f"{proc.returncode}: "
                    f"{proc.stderr.decode('utf-8', 'replace')[:200]}")
            return proc.stdout.decode("utf-8", "replace")
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


# --- OCR text analysis ------------------------------------------------

# Amounts with exactly two decimal places or thousands grouping.
# Bare integers are ignored: invoice numbers and quantities are not
# totals (INV-100 must not read as $100).
_AMOUNT_RE = re.compile(
    r"\d{1,3}(?:,\d{3})+\.\d{2}|\d{1,3}(?:,\d{3})+|\d+\.\d{2}")
_TOTAL_KEYWORDS = ("grand total", "amount due", "balance due",
                   "total due", "total")
_WALLET_RE = re.compile(r"0x[0-9a-fA-F]{40}")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_DOMAIN_RE = re.compile(
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z]{2,}")


def extract_amount_strings(text: str) -> list:
    """All money-shaped amount strings in the text, commas kept."""
    return _AMOUNT_RE.findall(text or "")


def extract_total_minor(text: str, currency: str):
    """Best-effort invoice total from OCR text, in minor units.

    Prefers amounts on lines carrying a total keyword ("subtotal"
    lines are excluded: a subtotal is not the total), taking the
    largest such amount (a totals block may show both the total and
    a lesser 'paid' figure). Falls back to the largest amount in
    the document. Returns None when no usable amount is found or
    the chosen string does not convert exactly.
    """
    lines = (text or "").splitlines()
    total_line_amounts: list = []
    all_amounts: list = []
    for line in lines:
        amounts = extract_amount_strings(line)
        all_amounts += amounts
        lowered = line.lower()
        if "subtotal" in lowered:
            continue
        if any(keyword in lowered for keyword in _TOTAL_KEYWORDS):
            total_line_amounts += amounts
    candidates = total_line_amounts or all_amounts
    if not candidates:
        return None

    def _minor(amount_str: str):
        try:
            return to_minor_units(amount_str.replace(",", ""), currency)
        except ValueError:
            return None

    converted = [m for m in (_minor(c) for c in candidates)
                 if m is not None]
    return max(converted) if converted else None


def extract_payee_identifiers(text: str) -> set:
    """Payee-shaped identifiers rendered in OCR text: EVM wallet
    addresses, email addresses, and domains. An email's domain is
    not double-reported as a bare domain."""
    text = text or ""
    identifiers = set(_WALLET_RE.findall(text))
    emails = set(_EMAIL_RE.findall(text))
    identifiers |= emails
    email_domains = {e.split("@", 1)[1].lower() for e in emails}
    for domain in _DOMAIN_RE.findall(text):
        if domain.lower() not in email_domains:
            identifiers.add(domain)
    return identifiers


class OcrInvoiceImageScreener:
    """Real invoice-image screener: OCR + cross-check.

    Reads the image bytes and the expected values from the
    per-image context the binder supplies:
      context["image_bytes"]: the bound image bytes (the binder
        passes the artifact's content_bytes). Without bytes there
        is nothing to OCR and the verdict is not_evaluated: a hash
        alone cannot be cross-checked against its own rendering.
      context["expected"]: {"amount_minor", "currency",
        "counterparty_canonical"} for the intent being bound.
      context["known_identifiers"]: canonical identifiers
        harvested from the counterparty and every bound artifact;
        an identifier the image renders that appears nowhere in
        the bound set is a divergence.
      context["canonicalize"]: the record's canonicalization
        callable (defaults to canonical_identifier).

    All mismatch verdicts are advisory (see ScreenResult.advisory).
    """

    def __init__(self, extractor: TextExtractor = None):
        self._extractor = extractor or TesseractTextExtractor()

    def screen_invoice_image(self, image_ref: str, image_sha256: str,
                             context: dict) -> ScreenResult:
        image_bytes = context.get("image_bytes")
        if image_bytes is None:
            return ScreenResult.not_evaluated(
                "invoice image bytes were not supplied; OCR needs "
                "the image itself, not only its hash")
        try:
            text = self._extractor.extract_text(image_bytes)
        except OCRUnavailableError as exc:
            return ScreenResult.not_evaluated(f"OCR unavailable: {exc}")
        except Exception as exc:  # a broken engine is not a verdict
            return ScreenResult.not_evaluated(
                f"OCR extraction failed: {exc}")
        if not text or not text.strip():
            return ScreenResult.advisory_result(
                ["OCR extracted no readable text from the invoice "
                 "image; its totals and payee could not be "
                 "cross-checked against the bound artifacts"],
                evidence=[{"type": "ocr_text_chars", "value": 0}])

        canon = context.get("canonicalize") or canonical_identifier
        expected = context.get("expected") or {}
        known = context.get("known_identifiers") or set()
        reasons: list = []
        evidence: list = [
            {"type": "ocr_text_chars", "value": len(text)}]

        # Totals cross-check.
        expected_minor = expected.get("amount_minor")
        if expected_minor is not None:
            extracted_minor = extract_total_minor(
                text, expected.get("currency", ""))
            evidence.append({"type": "ocr_total_minor",
                             "value": extracted_minor})
            if extracted_minor is None:
                reasons.append(
                    "could not confirm the invoice total from the "
                    "image text; no total-shaped amount was readable")
            elif extracted_minor != expected_minor:
                reasons.append(
                    f"invoice image total ({extracted_minor} minor "
                    f"units) does not match the bound amount "
                    f"({expected_minor} minor units); the image "
                    "rendered to the payer is not the invoice the "
                    "artifacts describe")

        # Payee identifier cross-check.
        rendered = extract_payee_identifiers(text)
        unknown = sorted(
            ident for ident in rendered if canon(ident) not in known)
        if rendered:
            evidence.append({"type": "ocr_identifiers",
                             "value": sorted(rendered)})
        if unknown:
            reasons.append(
                "invoice image names payee identifier(s) absent "
                "from the bound artifacts: "
                + ", ".join(unknown[:3])
                + (" (+more)" if len(unknown) > 3 else ""))

        if reasons:
            return ScreenResult.advisory_result(reasons, evidence)
        result = ScreenResult.no_flags(evidence)
        result.caveats.append(
            "OCR cross-check compares the totals and identifiers "
            "the image renders against the bound artifacts; it is "
            "not a corpus evaluation of the counterparty")
        return result


# ---------------------------------------------------------------------------
# Payment model.
# ---------------------------------------------------------------------------

_ZERO_DECIMAL_CURRENCIES = {"JPY", "KRW", "VND", "CLP", "ISK", "UGX"}


def to_minor_units(amount, currency: str) -> int:
    """Convert a decimal amount string to integer minor units.

    Rejects sub-minor-unit precision rather than rounding silently:
    money comparisons must be exact.
    """
    exp = 0 if (currency or "").upper() in _ZERO_DECIMAL_CURRENCIES else 2
    try:
        value = Decimal(str(amount))
    except InvalidOperation:
        raise ValueError(f"unparseable amount: {amount!r}")
    if value < 0:
        raise ValueError("amount must not be negative")
    scaled = value * (10 ** exp)
    if scaled != scaled.to_integral_value():
        raise ValueError(
            f"amount {amount!r} has sub-minor-unit precision for "
            f"{currency}")
    return int(scaled)


def canonical_identifier(value: str) -> str:
    """Canonical form for payer/counterparty comparison.

    URLs reduce to host plus path (scheme, default port, and trailing
    slash dropped); everything else is stripped and lowercased, which
    is correct for domains, emails, and EVM wallet addresses. Display
    forms are kept separately in the record.
    """
    s = (value or "").strip()
    if "://" in s:
        parts = urllib.parse.urlsplit(s)
        host = (parts.hostname or "").lower()
        path = (parts.path or "").rstrip("/")
        return f"{host}{path}" if path else host
    return s.lower().rstrip("/")


def canonical_identifier_opaque(value: str) -> str:
    """Canonical form for case-sensitive opaque identifiers (some
    marketplace service ids): whitespace is stripped, nothing else.
    Lowercasing or URL reduction would merge distinct ids."""
    return (value or "").strip()


# Identifier canonicalization policies, selected per rail by
# PaymentIntent.rail and recorded in the signed record as
# record["id_policy"], so settlement canonicalizes the executed
# identifiers with the same policy the binding was issued under.
# A binder accepts additional named policies (name -> callable)
# via its canonicalizers argument.
CANONICALIZERS = {
    "default": canonical_identifier,
    "opaque": canonical_identifier_opaque,
}


@dataclass
class Artifact:
    """One bound artifact: an invoice, a cart, an invoice image.

    artifact_id is the caller-stable key used to match the artifact
    between binding time and settlement time. The hash covers the raw
    content_bytes when supplied (invoice image bytes, a canonical
    invoice document); otherwise it covers the canonical JSON of the
    descriptor. An invoice image presented by reference carries
    {"image_ref": ..., "image_sha256": ...} as its descriptor, so the
    claimed image hash is itself bound.
    """
    artifact_id: str
    kind: str  # "invoice" | "cart" | "invoice_image" | "other"
    descriptor: dict = field(default_factory=dict)
    content_bytes: Optional[bytes] = field(default=None, repr=False)

    def compute_hash(self) -> str:
        if self.content_bytes is not None:
            return hashlib.sha256(self.content_bytes).hexdigest()
        return content_hash_of(self.descriptor)


@dataclass
class PaymentIntent:
    """What the payer agent declares at binding time."""
    payer: str
    counterparty: str
    amount: str  # decimal string, e.g. "25.00"
    currency: str  # ISO 4217, e.g. "USD"
    artifacts: list = field(default_factory=list)  # list[Artifact]
    tap_intent_ref: str = ""  # TAP intent token id this binding rides on
    metadata: dict = field(default_factory=dict)
    # Rail / identifier-policy name: selects the canonicalization
    # policy for payer and counterparty ("default", "opaque", or a
    # policy registered on the binder). "" means "default". The
    # resolved name is signed into the record as id_policy.
    rail: str = ""


@dataclass
class ExecutedPayment:
    """What actually executed, as presented at settlement time."""
    payer: str
    counterparty: str
    amount: str
    currency: str
    artifacts: list = field(default_factory=list)  # list[Artifact]
    rail_reference: str = ""  # token id / settlement reference, informational
    # Informational only: settlement canonicalizes with the policy
    # named in the binding record, never with a policy the presenter
    # chooses at settlement time.
    rail: str = ""


# ---------------------------------------------------------------------------
# Binding record.
# ---------------------------------------------------------------------------

@dataclass
class Binding:
    """A signed binding record plus its signature envelope."""
    record: dict
    signature: str = ""       # hex Ed25519 signature over canonical record
    public_key: str = ""      # hex public key of the issuing signer
    key_id: str = ""

    @property
    def binding_id(self) -> str:
        return self.record.get("binding_id", "")

    def to_dict(self) -> dict:
        return {
            "record": self.record,
            "signature": self.signature,
            "public_key": self.public_key,
            "key_id": self.key_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Binding":
        return cls(record=data["record"],
                   signature=data.get("signature", ""),
                   public_key=data.get("public_key", ""),
                   key_id=data.get("key_id", ""))

    def signature_valid(self) -> bool:
        if not self.signature or not self.public_key:
            return False
        return verify_signature(self.public_key, self.signature,
                                canonical_bytes(self.record))


@dataclass
class SettlementDecision:
    """Outcome of verify_at_settlement. decision is "allow" or
    "block"; reason_codes are the machine-readable contract."""
    decision: str
    reason_codes: list = field(default_factory=list)
    reasons: list = field(default_factory=list)
    binding_id: str = ""

    @property
    def allowed(self) -> bool:
        return self.decision == "allow"


class BindingRefused(Exception):
    """Raised by create_binding when screening or validation refuses.

    Carries machine-readable reason_codes, human-readable reasons,
    and the screening verdicts that caused the refusal, so callers
    can route to step-up / human approval where their policy allows.
    """

    def __init__(self, reason_codes: list, reasons: list,
                 verdicts: dict = None):
        super().__init__("; ".join(reasons))
        self.reason_codes = reason_codes
        self.reasons = reasons
        self.verdicts = verdicts or {}


# ---------------------------------------------------------------------------
# Binding store (consumption registry).
# ---------------------------------------------------------------------------

class BindingStore(Protocol):
    def save(self, binding: Binding) -> None:
        ...

    def get(self, binding_id: str) -> Optional[Binding]:
        ...

    def is_consumed(self, binding_id: str) -> bool:
        ...

    def consume(self, binding_id: str) -> bool:
        """Atomically mark consumed. Returns False if already
        consumed (a racing settlement won)."""
        ...


class InMemoryBindingStore:
    """Reference store. Production replaces this with a conditional
    write (for example a DynamoDB ConditionExpression on a consumed
    attribute) so consume() stays atomic across processes."""

    def __init__(self):
        self._bindings: dict = {}
        self._consumed: set = set()
        self._lock = threading.Lock()

    def save(self, binding: Binding) -> None:
        with self._lock:
            self._bindings[binding.binding_id] = binding

    def get(self, binding_id: str) -> Optional[Binding]:
        with self._lock:
            return self._bindings.get(binding_id)

    def is_consumed(self, binding_id: str) -> bool:
        with self._lock:
            return binding_id in self._consumed

    def consume(self, binding_id: str) -> bool:
        with self._lock:
            if binding_id in self._consumed:
                return False
            self._consumed.add(binding_id)
            return True


# ---------------------------------------------------------------------------
# Reason codes.
# ---------------------------------------------------------------------------

# create_binding refusals
RC_COUNTERPARTY_FLAGGED = "COUNTERPARTY_FLAGGED"
RC_ARTIFACT_FLAGGED = "ARTIFACT_FLAGGED"
RC_INVOICE_IMAGE_FLAGGED = "INVOICE_IMAGE_FLAGGED"
RC_SCREEN_NOT_EVALUATED = "SCREEN_NOT_EVALUATED"
RC_INVALID_INTENT = "INVALID_INTENT"

# verify_at_settlement outcomes
RC_OK = "OK"
RC_BINDING_NOT_FOUND = "BINDING_NOT_FOUND"
RC_SIGNATURE_INVALID = "SIGNATURE_INVALID"
RC_ID_POLICY_UNKNOWN = "ID_POLICY_UNKNOWN"
RC_BINDING_ALREADY_CONSUMED = "BINDING_ALREADY_CONSUMED"
RC_BINDING_EXPIRED = "BINDING_EXPIRED"
RC_PAYER_MISMATCH = "PAYER_MISMATCH"
RC_COUNTERPARTY_MISMATCH = "COUNTERPARTY_MISMATCH"
RC_CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
RC_AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
RC_ARTIFACT_MISSING = "ARTIFACT_MISSING"
RC_ARTIFACT_TAMPERED = "ARTIFACT_TAMPERED"
RC_ARTIFACT_UNEXPECTED = "ARTIFACT_UNEXPECTED"

# verify_at_settlement step-up attestation outcomes (decided
# 2026-10-24: a rail presents a signed attestation object per
# required method at settle time; settle-check validates presence,
# TTL window, and evidence_ref shape, and does NOT re-verify the
# external approval system).
RC_STEP_UP_ATTESTATION_MISSING = "STEP_UP_ATTESTATION_MISSING"
RC_STEP_UP_ATTESTATION_INVALID = "STEP_UP_ATTESTATION_INVALID"

ATTESTATION_METHODS = ("human_approval", "second_agent_approval",
                       "policy_rule")


def _evidence_ref_well_formed(value) -> bool:
    """Shape check for an attestation's evidence_ref (a URI or a hash
    of the approval record). This is shape only, never content: the
    referenced record is the rail's to keep, not ours to re-verify.
    Rejects empty, trivially short, and whitespace-containing
    values; accepts any longer whitespace-free string."""
    if not isinstance(value, str):
        return False
    value = value.strip()
    return len(value) >= 8 and not any(ch.isspace() for ch in value)


def validate_step_up_attestations(step_up: dict, attestations,
                                  issued_at, expires_at):
    """Validate settle-time step-up attestations against the
    requirement baked into the binding record at issuance.

    Returns (codes, reasons); empty codes means satisfied. Rules,
    exactly the decided v1 set:
    - step_up.required False: no validation, attestations ignored.
    - Every method in step_up.satisfied_by must be covered by at
      least one presented attestation with that method, else
      STEP_UP_ATTESTATION_MISSING.
    - Every presented attestation must be a mapping with a known
      method, a well-formed evidence_ref, and an integer attested_at
      inside the binding TTL window [issued_at, expires_at], else
      STEP_UP_ATTESTATION_INVALID. A malformed attestation blocks
      even when the required methods are otherwise covered: malformed
      evidence in a settlement request means a broken rail
      integration, and this library fails closed.
    - attestor is part of the attestation object shape but is NOT
      validated in v1 (the decision lists presence, TTL, and
      evidence_ref shape only); it is carried through, not checked.
    A required step-up that names no satisfaction method is
    unsatisfiable and blocks as MISSING (a policy misconfiguration,
    not a rail fault, but it must never silently allow).
    """
    if not isinstance(step_up, dict) or not step_up.get("required"):
        return [], []
    required = step_up.get("satisfied_by") or []
    if not required:
        return ([RC_STEP_UP_ATTESTATION_MISSING],
                ["binding requires step-up but the signed record "
                 "names no satisfaction method"])
    if attestations is None:
        attestations = []
    codes: list = []
    reasons: list = []
    if not isinstance(attestations, list):
        return ([RC_STEP_UP_ATTESTATION_INVALID],
                ["attestations must be a list of attestation "
                 "objects"])
    presented_methods = set()
    for att in attestations:
        if not isinstance(att, dict):
            codes.append(RC_STEP_UP_ATTESTATION_INVALID)
            reasons.append("attestation is not an object")
            continue
        method = att.get("method")
        if method not in ATTESTATION_METHODS:
            codes.append(RC_STEP_UP_ATTESTATION_INVALID)
            reasons.append(
                f"attestation method {method!r} is not a known "
                "method (human_approval, second_agent_approval, "
                "policy_rule)")
            continue
        presented_methods.add(method)
        if not _evidence_ref_well_formed(att.get("evidence_ref")):
            codes.append(RC_STEP_UP_ATTESTATION_INVALID)
            reasons.append(
                f"attestation for {method} has a malformed "
                "evidence_ref (must be a non-empty, "
                "whitespace-free URI or hash)")
            continue
        attested_at = att.get("attested_at")
        if (isinstance(attested_at, bool)
                or not isinstance(attested_at, int)
                or not isinstance(issued_at, int)
                or not isinstance(expires_at, int)
                or not (issued_at <= attested_at <= expires_at)):
            codes.append(RC_STEP_UP_ATTESTATION_INVALID)
            reasons.append(
                f"attestation for {method} has attested_at "
                f"{attested_at!r}, outside the binding TTL window "
                f"[{issued_at}, {expires_at}]")
    for method in required:
        if method not in presented_methods:
            codes.append(RC_STEP_UP_ATTESTATION_MISSING)
            reasons.append(
                f"step-up requires {method} but no attestation "
                "for it was presented at settle time")
    return (list(dict.fromkeys(codes)), reasons)


# ---------------------------------------------------------------------------
# Policy (v2): TTL, tolerance, image-OCR posture, and step-up rules
# live in a YAML policy file, not in code constants (mcp_proxy
# policy style: sectioned YAML, lazy yaml import, validated load).
# ---------------------------------------------------------------------------

def _policy_int(data: dict, key: str, default, minimum=None,
                maximum=None):
    value = data.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"policy key {key!r} must be an integer, "
                         f"got {value!r}")
    if minimum is not None and value < minimum:
        raise ValueError(f"policy key {key!r} must be >= {minimum}, "
                         f"got {value}")
    if maximum is not None and value > maximum:
        raise ValueError(f"policy key {key!r} must be <= {maximum}, "
                         f"got {value}")
    return value


def _policy_bool(data: dict, key: str, default):
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"policy key {key!r} must be a boolean, "
                         f"got {value!r}")
    return value


def _reject_unknown(data: dict, allowed: set, where: str):
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValueError(
            f"unknown policy key(s) in {where}: "
            + ", ".join(unknown))


@dataclass
class BindingPolicy:
    """Binder policy. Defaults are the v1 constants, now data.

    YAML shape (see intent_binding.policy.example.yaml):

        binding:
          ttl_seconds: 900
          amount_tolerance: {minor: 0, bps: 0}
          screening:
            require_image_verdict: false
            allow_unevaluated: false
          image_ocr:
            hard_block: false        # advisory OCR flags refuse
          step_up:
            satisfied_by: [human_approval]
            amount_minor_at_or_above: null   # or an integer
            on_image_unevaluated: false

    Validation is strict: unknown keys, wrong types, and
    out-of-range values raise ValueError at load, so a typo'd
    policy fails loudly instead of silently running on defaults.
    """
    ttl_seconds: int = 900
    amount_tolerance_minor: int = 0
    amount_tolerance_bps: int = 0
    require_image_verdict: bool = False
    allow_unevaluated: bool = False
    image_ocr_hard_block: bool = False
    step_up_satisfied_by: tuple = ("human_approval",)
    step_up_amount_minor_at_or_above: Optional[int] = None
    step_up_on_image_unevaluated: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> "BindingPolicy":
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("policy must be a mapping")
        _reject_unknown(data, {"binding"}, "policy root")
        section = data.get("binding", {})
        if not isinstance(section, dict):
            raise ValueError("policy key 'binding' must be a mapping")
        _reject_unknown(
            section,
            {"ttl_seconds", "amount_tolerance", "screening",
             "image_ocr", "step_up"},
            "binding")

        tolerance = section.get("amount_tolerance", {})
        if not isinstance(tolerance, dict):
            raise ValueError(
                "policy key 'amount_tolerance' must be a mapping")
        _reject_unknown(tolerance, {"minor", "bps"},
                        "binding.amount_tolerance")

        screening = section.get("screening", {})
        if not isinstance(screening, dict):
            raise ValueError("policy key 'screening' must be a mapping")
        _reject_unknown(
            screening, {"require_image_verdict", "allow_unevaluated"},
            "binding.screening")

        image_ocr = section.get("image_ocr", {})
        if not isinstance(image_ocr, dict):
            raise ValueError("policy key 'image_ocr' must be a mapping")
        _reject_unknown(image_ocr, {"hard_block"}, "binding.image_ocr")

        step_up = section.get("step_up", {})
        if not isinstance(step_up, dict):
            raise ValueError("policy key 'step_up' must be a mapping")
        _reject_unknown(
            step_up,
            {"satisfied_by", "amount_minor_at_or_above",
             "on_image_unevaluated"},
            "binding.step_up")
        satisfied_by = step_up.get("satisfied_by", ["human_approval"])
        if (not isinstance(satisfied_by, list)
                or not satisfied_by
                or not all(isinstance(s, str) and s
                           for s in satisfied_by)):
            raise ValueError(
                "policy key 'step_up.satisfied_by' must be a "
                "non-empty list of strings")

        return cls(
            ttl_seconds=_policy_int(
                section, "ttl_seconds", 900, minimum=1),
            amount_tolerance_minor=_policy_int(
                tolerance, "minor", 0, minimum=0),
            amount_tolerance_bps=_policy_int(
                tolerance, "bps", 0, minimum=0, maximum=10000),
            require_image_verdict=_policy_bool(
                screening, "require_image_verdict", False),
            allow_unevaluated=_policy_bool(
                screening, "allow_unevaluated", False),
            image_ocr_hard_block=_policy_bool(
                image_ocr, "hard_block", False),
            step_up_satisfied_by=tuple(satisfied_by),
            step_up_amount_minor_at_or_above=_policy_int(
                step_up, "amount_minor_at_or_above", None, minimum=0),
            step_up_on_image_unevaluated=_policy_bool(
                step_up, "on_image_unevaluated", False),
        )

    @classmethod
    def from_yaml_text(cls, text: str) -> "BindingPolicy":
        try:
            import yaml
        except ImportError as exc:
            raise ValueError(
                "loading a YAML policy requires PyYAML; construct "
                "BindingPolicy.from_dict instead") from exc
        return cls.from_dict(yaml.safe_load(text))

    @classmethod
    def load_yaml_file(cls, path: str) -> "BindingPolicy":
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_yaml_text(fh.read())


# ---------------------------------------------------------------------------
# The binder.
# ---------------------------------------------------------------------------

def _resolve(value, policy_value):
    """Constructor kwarg (None = unset) beats policy beats the
    dataclass default already folded into the policy."""
    return policy_value if value is None else value


class IntentBinder:
    """Creates bindings and verifies settlements against them.

    Parameters:
      signer: Signer for binding records.
      counterparty_screener / artifact_screener / image_screener:
        pluggable screening hooks. The image screener defaults to
        the not-evaluated stub; production wires
        OcrInvoiceImageScreener. Counterparty and artifact
        screeners have no default: an unscreened binding is worse
        than no binding, so create_binding refuses when their
        screens do not evaluate (unless allow_unevaluated).
      store: consumption registry (defaults to in-memory).
      policy: BindingPolicy carrying ttl_seconds, amount tolerance,
        require_image_verdict, allow_unevaluated, the image-OCR
        hard-block posture, and the step-up rules. These used to be
        code constants; they are configuration now (YAML file in
        production, BindingPolicy in code).
      ttl_seconds / amount_tolerance_minor / amount_tolerance_bps /
      require_image_verdict / allow_unevaluated /
      image_ocr_hard_block: explicit overrides; None (the default)
        means "take the value from policy". Defaults with no
        policy: TTL 900 seconds (pay-moment use: intent is declared
        at checkout, settlement follows immediately), zero amount
        tolerance (exact amount; tolerance exists for rails that
        add variable fees, see DESIGN.md before widening it), OCR
        flags advisory rather than blocking.
      canonicalizers: additional named identifier policies
        (name -> callable) merged over CANONICALIZERS, selected
        per intent by PaymentIntent.rail.
      now_fn: clock, injectable for tests.
    """

    def __init__(self, signer: Signer,
                 counterparty_screener: CounterpartyScreener = None,
                 artifact_screener: ArtifactScreener = None,
                 image_screener: InvoiceImageScreener = None,
                 store: BindingStore = None,
                 ttl_seconds: int = None,
                 amount_tolerance_minor: int = None,
                 amount_tolerance_bps: int = None,
                 require_image_verdict: bool = None,
                 allow_unevaluated: bool = None,
                 now_fn: Callable[[], float] = time.time,
                 policy: BindingPolicy = None,
                 image_ocr_hard_block: bool = None,
                 canonicalizers: dict = None):
        self._signer = signer
        self._counterparty_screener = counterparty_screener
        self._artifact_screener = artifact_screener
        self._image_screener = image_screener or NotEvaluatedImageScreener()
        self._store = store or InMemoryBindingStore()
        self._policy = policy or BindingPolicy()
        self._ttl = int(_resolve(ttl_seconds, self._policy.ttl_seconds))
        self._tolerance_minor = int(_resolve(
            amount_tolerance_minor,
            self._policy.amount_tolerance_minor))
        self._tolerance_bps = int(_resolve(
            amount_tolerance_bps, self._policy.amount_tolerance_bps))
        self._require_image_verdict = _resolve(
            require_image_verdict, self._policy.require_image_verdict)
        self._allow_unevaluated = _resolve(
            allow_unevaluated, self._policy.allow_unevaluated)
        self._image_ocr_hard_block = _resolve(
            image_ocr_hard_block, self._policy.image_ocr_hard_block)
        self._canonicalizers = dict(CANONICALIZERS)
        if canonicalizers:
            self._canonicalizers.update(canonicalizers)
        self._now = now_fn

    # -- creation -----------------------------------------------------

    def create_binding(self, intent: PaymentIntent) -> Binding:
        """Screen an intent and issue a signed binding.

        Raises BindingRefused (with reason codes) when validation
        fails or any screen flags. On success the binding is saved
        to the store and returned.
        """
        context = {
            "payer": intent.payer,
            "amount": intent.amount,
            "currency": intent.currency,
            "tap_intent_ref": intent.tap_intent_ref,
            "metadata": intent.metadata,
        }

        # Validate and normalize the money fields first: a binding
        # over an unparseable amount is meaningless.
        try:
            amount_minor = to_minor_units(intent.amount, intent.currency)
        except ValueError as exc:
            raise BindingRefused([RC_INVALID_INTENT], [str(exc)])
        if not intent.payer or not intent.counterparty:
            raise BindingRefused(
                [RC_INVALID_INTENT],
                ["payer and counterparty are required"])
        if not intent.artifacts:
            raise BindingRefused(
                [RC_INVALID_INTENT],
                ["at least one artifact (invoice or cart) is required: "
                 "an intent with nothing bound to it binds nothing"])

        # Resolve the identifier canonicalization policy for this
        # rail before anything is compared or signed. The resolved
        # policy name is signed into the record (id_policy) so
        # settlement applies the same policy.
        id_policy = intent.rail or "default"
        canon = self._canonicalizers.get(id_policy)
        if canon is None:
            raise BindingRefused(
                [RC_INVALID_INTENT],
                [f"unknown identifier policy (rail): {id_policy!r}"])
        payer_canonical = canon(intent.payer)
        counterparty_canonical = canon(intent.counterparty)

        verdicts: dict = {}
        refusal_codes: list = []
        refusal_reasons: list = []

        # Counterparty screen.
        cp_result = None
        if self._counterparty_screener is not None:
            cp_result = self._counterparty_screener.screen_counterparty(
                intent.counterparty, context)
        if cp_result is None:
            cp_result = ScreenResult.not_evaluated(
                "no counterparty screener configured")
        verdicts["counterparty"] = cp_result.to_dict()
        if cp_result.flagged:
            refusal_codes.append(RC_COUNTERPARTY_FLAGGED)
            refusal_reasons += [
                f"counterparty: {r}" for r in cp_result.reasons]
        elif not cp_result.evaluated and not self._allow_unevaluated:
            refusal_codes.append(RC_SCREEN_NOT_EVALUATED)
            refusal_reasons.append(
                "counterparty screen did not evaluate; refusing to "
                "bind an unscreened counterparty")

        # Artifact screens + hashes. Duplicate artifact ids would
        # make settlement matching ambiguous, so refuse them.
        artifact_hashes: dict = {}
        artifact_kinds: dict = {}
        artifact_verdicts: dict = {}
        seen_ids: set = set()
        for artifact in intent.artifacts:
            if artifact.artifact_id in seen_ids:
                raise BindingRefused(
                    [RC_INVALID_INTENT],
                    [f"duplicate artifact_id: {artifact.artifact_id!r}"])
            seen_ids.add(artifact.artifact_id)
            artifact_hashes[artifact.artifact_id] = \
                artifact.compute_hash()
            artifact_kinds[artifact.artifact_id] = artifact.kind

            if artifact.kind == "invoice_image":
                continue  # image hook runs below, once per image
            result = None
            if self._artifact_screener is not None:
                result = self._artifact_screener.screen_artifact(
                    artifact, context)
            if result is None:
                result = ScreenResult.not_evaluated(
                    "no artifact screener configured")
            artifact_verdicts[artifact.artifact_id] = result.to_dict()
            if result.flagged:
                refusal_codes.append(RC_ARTIFACT_FLAGGED)
                refusal_reasons += [
                    f"artifact {artifact.artifact_id}: {r}"
                    for r in result.reasons]
            elif not result.evaluated and not self._allow_unevaluated:
                refusal_codes.append(RC_SCREEN_NOT_EVALUATED)
                refusal_reasons.append(
                    f"artifact {artifact.artifact_id} screen did not "
                    "evaluate; refusing to bind an unscreened artifact")
        verdicts["artifacts"] = artifact_verdicts

        # Identifiers the bound set already names, harvested for
        # the image OCR cross-check: anything the image renders
        # that appears nowhere in this set is a divergence.
        known_identifiers = {payer_canonical, counterparty_canonical}
        known_identifiers.add(canon(intent.counterparty))
        for artifact in intent.artifacts:
            blob = json.dumps(artifact.descriptor, sort_keys=True,
                              default=str)
            for ident in extract_payee_identifiers(blob):
                known_identifiers.add(canon(ident))

        # Invoice image screen (screenshot-to-verdict hook). Runs
        # per image artifact. An advisory verdict (the OCR posture)
        # is recorded on the binding and becomes a step-up trigger;
        # it refuses only when policy sets image_ocr.hard_block. A
        # non-advisory image flag (a corpus verdict, not an
        # extraction guess) refuses as before, and an unevaluated
        # image refuses when policy requires an image verdict, or
        # becomes a step-up trigger when policy says so.
        image_verdicts: dict = {}
        step_up_triggers: list = []
        for artifact in intent.artifacts:
            if artifact.kind != "invoice_image":
                continue
            image_ref = str(artifact.descriptor.get("image_ref", ""))
            image_hash = artifact_hashes[artifact.artifact_id]
            image_context = dict(context)
            image_context.update({
                "image_bytes": artifact.content_bytes,
                "image_descriptor": artifact.descriptor,
                "canonicalize": canon,
                "known_identifiers": set(known_identifiers),
                "expected": {
                    "amount_minor": amount_minor,
                    "currency": (intent.currency or "").upper(),
                    "counterparty_canonical": counterparty_canonical,
                },
            })
            result = self._image_screener.screen_invoice_image(
                image_ref, image_hash, image_context)
            image_verdicts[artifact.artifact_id] = result.to_dict()
            if result.flagged and result.advisory \
                    and not self._image_ocr_hard_block:
                step_up_triggers.append({
                    "type": "invoice_image_advisory",
                    "artifact_id": artifact.artifact_id,
                    "reasons": list(result.reasons),
                })
            elif result.flagged:
                refusal_codes.append(RC_INVOICE_IMAGE_FLAGGED)
                refusal_reasons += [
                    f"invoice image {artifact.artifact_id}: {r}"
                    for r in result.reasons]
            elif (not result.evaluated and self._require_image_verdict):
                refusal_codes.append(RC_SCREEN_NOT_EVALUATED)
                refusal_reasons.append(
                    f"invoice image {artifact.artifact_id} was not "
                    "evaluated and policy requires an image verdict")
            elif (not result.evaluated
                    and self._policy.step_up_on_image_unevaluated):
                step_up_triggers.append({
                    "type": "invoice_image_unevaluated",
                    "artifact_id": artifact.artifact_id,
                    "reasons": list(result.reasons),
                })
        if image_verdicts:
            verdicts["invoice_images"] = image_verdicts

        if refusal_codes:
            # Deduplicate codes while preserving order.
            codes = list(dict.fromkeys(refusal_codes))
            raise BindingRefused(codes, refusal_reasons, verdicts)

        # Step-up block (v2): requirements are computed here, at
        # issuance, and baked into the signed record. The rail
        # reads them from the record it already verifies instead of
        # running a separate step-up flow; the library records the
        # requirement, the caller's rail enforces satisfaction
        # before settling (see DESIGN.md v2).
        threshold = self._policy.step_up_amount_minor_at_or_above
        if threshold is not None and amount_minor >= threshold:
            step_up_triggers.append({
                "type": "amount_threshold",
                "amount_minor": amount_minor,
                "threshold_minor": threshold,
            })
        step_up = {
            "required": bool(step_up_triggers),
            "triggers": step_up_triggers,
            "satisfied_by": list(self._policy.step_up_satisfied_by),
        }

        issued_at = int(self._now())
        tolerance = max(
            self._tolerance_minor,
            amount_minor * self._tolerance_bps // 10000)
        record = {
            "v": 2,
            "binding_id": "bind_" + secrets.token_hex(16),
            "nonce": secrets.token_hex(16),
            "payer": intent.payer,
            "payer_canonical": payer_canonical,
            "counterparty": intent.counterparty,
            "counterparty_canonical": counterparty_canonical,
            "id_policy": id_policy,
            "step_up": step_up,
            "amount_minor": amount_minor,
            "currency": (intent.currency or "").upper(),
            "amount_tolerance_minor": tolerance,
            "artifact_hashes": artifact_hashes,
            "artifact_kinds": artifact_kinds,
            "artifact_set_hash": content_hash_of(
                [{"artifact_id": aid, "kind": artifact_kinds[aid],
                  "hash": artifact_hashes[aid]}
                 for aid in sorted(artifact_hashes)]),
            "verdicts": verdicts,
            "tap_intent_ref": intent.tap_intent_ref,
            "issued_at": issued_at,
            "expires_at": issued_at + self._ttl,
        }
        signature = self._signer.sign(canonical_bytes(record))
        binding = Binding(record=record,
                            signature=signature.hex(),
                            public_key=self._signer.public_key_hex,
                            key_id=self._signer.key_id)
        self._store.save(binding)
        return binding

    # -- settlement verification ---------------------------------------

    def verify_at_settlement(self, binding_or_id,
                             executed: ExecutedPayment,
                             attestations=None
                             ) -> SettlementDecision:
        """Check an executed payment against its binding.

        Accepts a Binding or a binding_id resolved from the store.
        Returns a SettlementDecision; an allow consumes the binding
        so the same binding cannot settle twice. A block does not
        consume: a fat-fingered amount should not burn the buyer's
        one binding (see DESIGN.md for the probing tradeoff).

        attestations is the rail's settle-time step-up evidence: a
        list of {method, evidence_ref, attested_at, attestor}
        objects. When the signed record requires step-up, every
        required method must be attested, each attestation must
        carry a well-formed evidence_ref and an attested_at inside
        the binding TTL window, or the settlement blocks (and does
        not consume) with STEP_UP_ATTESTATION_* codes. The external
        approval system itself is never re-verified here: the rail
        attests, and this check validates the attestation's shape
        and timing only. Attestations are ignored when the record
        does not require step-up.
        """
        if isinstance(binding_or_id, Binding):
            binding = binding_or_id
        else:
            binding = self._store.get(str(binding_or_id))
        if binding is None:
            bid = (binding_or_id if isinstance(binding_or_id, str)
                   else "")
            return SettlementDecision(
                decision="block",
                reason_codes=[RC_BINDING_NOT_FOUND],
                reasons=["no binding found for the presented "
                         "binding_id"],
                binding_id=bid)
        bid = binding.binding_id
        record = binding.record

        # Signature first: nothing else in the record can be trusted
        # until the issuer's signature verifies.
        if not binding.signature_valid():
            return SettlementDecision(
                decision="block",
                reason_codes=[RC_SIGNATURE_INVALID],
                reasons=["binding signature does not verify against "
                         "the record; the record may have been "
                         "altered after issuance"],
                binding_id=bid)

        if self._store.is_consumed(bid):
            return SettlementDecision(
                decision="block",
                reason_codes=[RC_BINDING_ALREADY_CONSUMED],
                reasons=["binding was already consumed by an earlier "
                         "settlement"],
                binding_id=bid)

        if int(self._now()) > int(record.get("expires_at", 0)):
            return SettlementDecision(
                decision="block",
                reason_codes=[RC_BINDING_EXPIRED],
                reasons=["binding expired at "
                         f"{record.get('expires_at')}; the intent "
                         "must be re-screened and re-bound"],
                binding_id=bid)

        # Identifiers are compared under the canonicalization
        # policy the binding was issued with (signed into the
        # record), never under a policy chosen at settlement time.
        # A verifier that does not know the policy cannot compare
        # honestly, so it blocks rather than guessing.
        canon = self._canonicalizers.get(
            record.get("id_policy", "default"))
        if canon is None:
            return SettlementDecision(
                decision="block",
                reason_codes=[RC_ID_POLICY_UNKNOWN],
                reasons=["binding names identifier policy "
                         f"{record.get('id_policy')!r}, which this "
                         "verifier does not know; refusing to "
                         "compare identifiers under the wrong policy"],
                binding_id=bid)

        codes: list = []
        reasons: list = []

        if canon(executed.payer) != record["payer_canonical"]:
            codes.append(RC_PAYER_MISMATCH)
            reasons.append(
                f"payer mismatch: bound payer is "
                f"{record['payer']!r}, executed payer is "
                f"{executed.payer!r}")

        if canon(executed.counterparty) != \
                record["counterparty_canonical"]:
            codes.append(RC_COUNTERPARTY_MISMATCH)
            reasons.append(
                f"counterparty mismatch: bound counterparty is "
                f"{record['counterparty']!r}, executed counterparty "
                f"is {executed.counterparty!r}; the screened party "
                "is not the party being paid")

        if (executed.currency or "").upper() != record["currency"]:
            codes.append(RC_CURRENCY_MISMATCH)
            reasons.append(
                f"currency mismatch: bound {record['currency']}, "
                f"executed {(executed.currency or '').upper()}")
        else:
            try:
                executed_minor = to_minor_units(executed.amount,
                                                executed.currency)
            except ValueError as exc:
                codes.append(RC_AMOUNT_MISMATCH)
                reasons.append(f"executed amount unusable: {exc}")
                executed_minor = None
            if executed_minor is not None:
                drift = executed_minor - record["amount_minor"]
                if abs(drift) > record["amount_tolerance_minor"]:
                    codes.append(RC_AMOUNT_MISMATCH)
                    direction = "above" if drift > 0 else "below"
                    reasons.append(
                        f"amount mismatch: bound "
                        f"{record['amount_minor']} minor units, "
                        f"executed {executed_minor} minor units "
                        f"({abs(drift)} {direction} the bound amount, "
                        f"tolerance "
                        f"{record['amount_tolerance_minor']})")

        # Artifact set comparison.
        bound_hashes: dict = record["artifact_hashes"]
        executed_hashes: dict = {}
        for artifact in executed.artifacts:
            executed_hashes[artifact.artifact_id] = \
                artifact.compute_hash()
        for aid, bound_hash in bound_hashes.items():
            if aid not in executed_hashes:
                codes.append(RC_ARTIFACT_MISSING)
                reasons.append(
                    f"artifact {aid!r} was bound but is absent at "
                    "settlement")
            elif executed_hashes[aid] != bound_hash:
                codes.append(RC_ARTIFACT_TAMPERED)
                reasons.append(
                    f"artifact {aid!r} changed after binding: bound "
                    f"hash {bound_hash[:12]}..., settlement hash "
                    f"{executed_hashes[aid][:12]}...; what was "
                    "screened is not what is being paid for")
        for aid in executed_hashes:
            if aid not in bound_hashes:
                codes.append(RC_ARTIFACT_UNEXPECTED)
                reasons.append(
                    f"artifact {aid!r} appears at settlement but was "
                    "never bound or screened")

        # Step-up attestation validation runs with the other
        # comparison checks and before consumption, so a settlement
        # blocked on missing or malformed attestations does not burn
        # the binding (same principle as an amount block).
        step_up = record.get("step_up") or {}
        if step_up.get("required"):
            scodes, sreasons = validate_step_up_attestations(
                step_up, attestations,
                record.get("issued_at"), record.get("expires_at"))
            codes.extend(scodes)
            reasons.extend(sreasons)

        if codes:
            return SettlementDecision(
                decision="block",
                reason_codes=list(dict.fromkeys(codes)),
                reasons=reasons,
                binding_id=bid)

        # All checks passed: consume atomically so this binding can
        # never settle a second payment.
        if not self._store.consume(bid):
            return SettlementDecision(
                decision="block",
                reason_codes=[RC_BINDING_ALREADY_CONSUMED],
                reasons=["binding was consumed by a concurrent "
                         "settlement"],
                binding_id=bid)
        return SettlementDecision(
            decision="allow",
            reason_codes=[RC_OK],
            reasons=[
                "executed payment matches the signed binding "
                "(counterparty, payer, currency, amount within "
                "tolerance, artifact hashes unchanged); screening "
                "at binding time reported no flags found, which is "
                "not a guarantee of legitimacy"],
            binding_id=bid)

    def get_binding(self, binding_id: str) -> Optional[Binding]:
        return self._store.get(binding_id)
