#!/usr/bin/env python3
"""Scam-kit fingerprinting primitives — pure functions, no network, no AWS.

Turns smishing/phishing-kit sightings (a URL's HTML, or caller-supplied kit
HTML) into stable, matchable fingerprints: ``kit_<sha256>`` IDs that are
identical for the same kit across sightings, even when per-victim nonces,
session tokens, or rotated credentials differ.

Design rules (from the product spec):
  * Secrets are stripped BEFORE hashing. A credential, token, or machine ID
    never influences a fingerprint, and never appears in signals, logs, or
    stored records. Two kits differing only in rotated secrets fingerprint
    identically — that is the point.
  * Family names are AUTO-SUGGESTED ONLY. This module can only ever emit
    ``family_status="suggested"``. There is no code path that writes
    ``"approved"`` — approval is a manual, out-of-band act by Andrew.
  * Verdict copy never says "safe". The best case is "no flags found" with
    an explicit not-a-guarantee caveat.
  * ``kind`` discriminates ``kit_`` from the planned ``malware_<sha256>``
    IDs (spec §8). v1 code paths only emit ``kit_``.

URL input limitation (v1): there is no JS rendering in the Lambda runtime,
so server-side URL fetching is STATIC HTML ONLY. Callers dealing with
JS-heavy kits should render the page themselves and submit the rendered
HTML via the ``html`` parameter. This is documented on the endpoint, not
hidden.
"""

import hashlib
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

KIT_ID_PREFIX = "kit_"
MALWARE_ID_PREFIX = "malware_"  # planned extension (spec §8) — not emitted by v1
FINGERPRINT_VERSION = "skfp-v1"  # bump whenever normalization changes

# ---------------------------------------------------------------------------
# Secret stripping
# ---------------------------------------------------------------------------
# Ordered most-specific-first. Every match is replaced with a typed
# placeholder that preserves the *shape* ("a credential was here") without
# the value, so stripping is stable across sightings.
_SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}\b")),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("bearer", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_\-\.~+/=]{16,}")),
    ("basic_auth_url", re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@")),
    ("assigned_secret", re.compile(
        r"(?i)(password|passwd|pwd|secret|api[_-]?key|apikey|auth[_-]?token|access[_-]?token|"
        r"client[_-]?secret|private[_-]?key)\s*[:=]\s*['\"]?[^'\"\s,};&]{8,}['\"]?")),
    ("query_nonce", re.compile(r"([?&])(sid|session|sessionid|token|auth|nonce|victim|vid|uid|user_id|tracking|track_id)=[^&#\s'\"]*")),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("uuid", re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")),
    ("mac", re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")),
    ("long_hex", re.compile(r"\b[0-9a-fA-F]{32,}\b")),
    ("long_b64", re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b")),
]

# Query-param names whose values are per-victim and must not affect the URL
# pattern class or any hash. Applied to URLs before classification.
_NONCE_PARAMS = frozenset({
    "sid", "session", "sessionid", "token", "auth", "nonce", "victim",
    "vid", "uid", "user_id", "tracking", "track_id", "phpsessid", "jsessionid",
})


def strip_secrets(text: str) -> str:
    """Replace credential/token/machine-ID values with typed placeholders.

    Idempotent and order-stable: running it twice changes nothing the second
    time, so callers don't need to track whether input was pre-stripped.
    """
    if not text:
        return ""
    out = text
    for label, pattern in _SECRET_PATTERNS:
        out = pattern.sub(f"<STRIPPED:{label}>", out)
    return out


def _strip_url_nonces(url: str) -> str:
    """Drop per-victim query params from a URL (used before classification)."""
    try:
        parts = urlparse(url)
        if not parts.query:
            return url
        kept = [(k, v) for k, v in
                (p.split("=", 1) if "=" in p else (p, "") for p in parts.query.split("&"))
                if k.lower() not in _NONCE_PARAMS]
        clean_q = "&".join(f"{k}={v}" if v else k for k, v in kept)
        return parts._replace(query=clean_q).geturl()
    except Exception:
        return url


# ---------------------------------------------------------------------------
# HTML normalization → DOM skeleton
# ---------------------------------------------------------------------------
class _SkeletonParser(HTMLParser):
    """Builds a canonical DOM skeleton plus per-script bodies and form hosts.

    Attribute VALUES are dropped (they carry nonces, tokens, lure text);
    attribute NAMES are kept sorted, because the *shape* of the form is the
    kit's fingerprint. A few structural values (input type, form method) are
    kept — they define kit behavior, not victim identity.
    """

    _KEPT_ATTRS = {
        "input": frozenset({"type", "name"}),
        "form": frozenset({"method"}),
        "button": frozenset({"type"}),
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.scripts: list[tuple[str | None, str]] = []  # (src, body)
        self.form_actions: list[str] = []
        self.visible_text: list[str] = []
        self._script_src: str | None = None
        self._script_buf: list[str] | None = None
        self._skip_text_depth = 0  # inside script/style

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in ("script", "style"):
            self._skip_text_depth += 1
        names = sorted(n.lower() for n, _ in attrs)
        kept = []
        for n in self._KEPT_ATTRS.get(tag, ()):
            v = dict((k.lower(), val) for k, val in attrs).get(n)
            if v:
                kept.append(f"{n}={v.lower()[:32]}")
        extra = (" " + " ".join(kept)) if kept else ""
        self.parts.append(f"<{tag}[{','.join(names)}]{extra}>")
        if tag == "script":
            self._script_src = dict((k.lower(), v) for k, v in attrs).get("src")
            self._script_buf = []
        if tag == "form":
            self.form_actions.append(dict((k.lower(), v) for k, v in attrs).get("action") or "")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("script", "style") and self._skip_text_depth:
            self._skip_text_depth -= 1
        self.parts.append(f"</{tag}>")
        if tag == "script" and self._script_buf is not None:
            self.scripts.append((self._script_src, "".join(self._script_buf)))
            self._script_buf = None
            self._script_src = None

    def handle_data(self, data: str) -> None:
        if self._script_buf is not None:
            self._script_buf.append(data)
        elif not self._skip_text_depth:
            s = data.strip()
            if s:
                # Length bucket, not content: lure text varies per victim.
                self.visible_text.append(s)
                self.parts.append(f"#t[{min(len(s) // 32, 8)}]")


def normalize_html(html_text: str) -> str:
    """Canonical DOM skeleton string. Same kit ⇒ same skeleton."""
    parser = _SkeletonParser()
    try:
        parser.feed(html_text or "")
    except Exception:
        # Malformed HTML must not fail the fingerprint — hash what we got.
        pass
    return "".join(parser.parts)


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()


# ---------------------------------------------------------------------------
# Signal extraction
# ---------------------------------------------------------------------------
_BRANDS = (
    "paypal", "apple", "amazon", "microsoft", "google", "facebook",
    "instagram", "netflix", "chase", "bankofamerica", "wellsfargo",
    "dhl", "fedex", "ups", "usps",
)

_URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)

_SHORTENERS = frozenset({
    "bit.ly", "t.ly", "tinyurl.com", "goo.gl", "ow.ly", "is.gd",
    "buff.ly", "rebrand.ly", "cutt.ly",
})

_LURE_WORDS = frozenset({
    "login", "verify", "secure", "update", "account", "signin",
    "confirm", "validate", "unlock",
})


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def classify_url_pattern(url: str) -> str:
    """Coarse URL shape class — stable across per-victim nonce rotation."""
    if not url:
        return "not_provided"
    clean = _strip_url_nonces(url)
    host = _host_of(clean)
    if not host:
        return "unparseable"
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
        return "ip-host"
    if host in _SHORTENERS:
        return "url-shortener"
    if "xn--" in host:
        return "punycode"
    labels = host.split(".")
    if len(labels) >= 4 and any(len(lb) >= 12 and re.fullmatch(r"[a-z0-9-]+", lb) for lb in labels[:-2]):
        return "random-subdomain"
    for brand in _BRANDS:
        if brand in host and not host.endswith(brand + ".com"):
            return "typosquat-brand"
    path = urlparse(clean).path.lower()
    if any(w in path for w in _LURE_WORDS):
        return "path-lure"
    return "standard"


def _normalize_lure_text(text: str) -> str:
    """Reduce smishing lure text to its template: amounts, names, dates and
    tracking numbers become placeholders so the same lure with different
    victims hashes identically."""
    t = text.lower()
    t = re.sub(r"\$\s?\d[\d,.]*|\d[\d,.]*\s?(usd|eur|€|\$)", "<AMOUNT>", t)
    t = re.sub(r"\b\d{6,}\b", "<NUM>", t)
    t = re.sub(r"\b\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?\b", "<DATE>", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def extract_signals(html_text: str, url: str = "") -> dict:
    """Extract the v1 signal set from kit HTML. Pure; no network.

    Returned dict is JSON-canonical (sorted keys) and fully stripped of
    secrets — safe to hash, log (at low verbosity), and store.
    """
    clean = strip_secrets(html_text or "")
    parser = _SkeletonParser()
    try:
        parser.feed(clean)
    except Exception:
        pass

    page_host = _host_of(url)

    script_hashes = []
    for src, body in parser.scripts:
        if src:
            script_hashes.append(_sha256_hex("src:" + _strip_url_nonces(src.strip().lower())))
        elif body and body.strip():
            # Whitespace-normalized so minified-vs-pretty variants match.
            norm = re.sub(r"\s+", " ", strip_secrets(body)).strip()
            if norm:
                script_hashes.append(_sha256_hex("inline:" + norm))

    form_hosts = sorted({_host_of(a) for a in parser.form_actions if _host_of(a)})

    exfil: set[str] = set()
    for m in _URL_RE.finditer(clean):
        h = _host_of(m.group(0))
        if h and h != page_host:
            exfil.add(h)

    visible = " ".join(parser.visible_text).lower()
    brands = sorted({b for b in _BRANDS if b in visible})

    lure_hash = _sha256_hex(_normalize_lure_text(" ".join(parser.visible_text)))

    return {
        "brand_marks": brands,
        "dom_skeleton_hash": _sha256_hex("".join(parser.parts)),
        "exfil_endpoints": sorted(exfil),
        "fingerprint_version": FINGERPRINT_VERSION,
        "form_action_hosts": form_hosts,
        "kind": "kit",
        "script_hashes": sorted(set(script_hashes)),
        "sms_lure_template_hash": lure_hash,
        "url_pattern_class": classify_url_pattern(url),
    }


# ---------------------------------------------------------------------------
# Fingerprint IDs
# ---------------------------------------------------------------------------
def fingerprint_id(signals: dict, kind: str = "kit") -> str:
    """Stable ID: ``kit_<sha256>`` over the canonical feature vector.

    Same kit ⇒ same ID across sightings. ``kind="malware"`` is the planned
    extension point (spec §8) and yields ``malware_<sha256>``; v1 callers
    must pass ``kind="kit"``.
    """
    if kind == "malware":
        prefix = MALWARE_ID_PREFIX
    else:
        prefix = KIT_ID_PREFIX
    canonical = json.dumps(signals, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256((FINGERPRINT_VERSION + ":" + canonical).encode("utf-8")).hexdigest()
    return f"{prefix}{digest}"


def valid_fingerprint_id(value: str) -> bool:
    """Shape check for caller-supplied IDs: ``kit_`` + 64 hex chars."""
    return bool(re.fullmatch(r"kit_[0-9a-f]{64}", value or ""))


# ---------------------------------------------------------------------------
# Family auto-suggest (deterministic — never "approved")
# ---------------------------------------------------------------------------
# Signal weights for overlap scoring. The DOM skeleton is the strongest
# kit-identity signal; shared scripts next; hosts/brands are corroborating.
_SIGNAL_WEIGHTS = {
    "dom_skeleton_hash": 3,
    "script_hashes": 2,      # per shared hash
    "form_action_hosts": 1,  # per shared host
    "exfil_endpoints": 1,    # per shared host
    "brand_marks": 1,        # per shared brand
}

# Minimum overlap score to suggest a family. Tuned conservatively: a wrong
# family suggestion is worse than none, because analysts act on the name.
SUGGEST_THRESHOLD = 4


def _overlap_score(a: dict, b: dict) -> tuple[int, int]:
    """(score, comparable_signals) between two signal dicts."""
    score = 0
    comparable = 0
    if a.get("dom_skeleton_hash") and b.get("dom_skeleton_hash"):
        comparable += 1
        if a["dom_skeleton_hash"] == b["dom_skeleton_hash"]:
            score += _SIGNAL_WEIGHTS["dom_skeleton_hash"]
    for key in ("script_hashes", "form_action_hosts", "exfil_endpoints", "brand_marks"):
        sa, sb = set(a.get(key) or []), set(b.get(key) or [])
        if sa or sb:
            comparable += 1
            score += len(sa & sb) * _SIGNAL_WEIGHTS[key]
    return score, comparable


def suggest_family(signals: dict, known_families: list[dict]) -> tuple[str | None, str | None]:
    """Deterministic family auto-suggest.

    ``known_families``: list of ``{"family": name, "signals": {...}}`` —
    families whose status the caller has already resolved (suggested or
    approved; this function does not distinguish, it only matches shape).

    Returns ``(family_name, "suggested")`` or ``(None, None)``.

    HARD RULE: this function can only ever emit ``"suggested"``. There is
    deliberately no parameter, flag, or code path that returns ``"approved"``.
    Marking a family approved is a manual act by Andrew, recorded directly
    on the stored fingerprint item — never by this code.
    """
    best: str | None = None
    best_score = 0
    for fam in known_families:
        name = fam.get("family")
        fsig = fam.get("signals") or {}
        if not name or not fsig:
            continue
        score, _ = _overlap_score(signals, fsig)
        if score > best_score:
            best_score, best = score, name
    if best and best_score >= SUGGEST_THRESHOLD:
        return best, "suggested"
    return None, None


# ---------------------------------------------------------------------------
# Confidence & verdicts
# ---------------------------------------------------------------------------
def compute_confidence(*, exact_sightings: int = 0, overlap_fraction: float = 0.0) -> tuple[float, str]:
    """Map corpus evidence to (confidence, verdict).

    Bands (spec §3):
      0.90–1.00  exact fingerprint, ≥2 sightings            → known_kit
      0.60–0.89  partial signal overlap                     → likely_variant
      0.30–0.59  weak overlap                               → likely_variant (weak band)
      <0.30      no match                                   → unknown
    """
    if exact_sightings >= 2:
        return round(0.90 + min(0.09, 0.01 * exact_sightings), 2), "known_kit"
    if overlap_fraction >= 0.5:
        return round(0.60 + overlap_fraction * 0.29, 2), "likely_variant"
    if overlap_fraction >= 0.2:
        return round(0.30 + overlap_fraction * 0.50, 2), "likely_variant"
    return 0.0, "unknown"


def confidence_band(confidence: float) -> str:
    if confidence >= 0.90:
        return "exact"
    if confidence >= 0.60:
        return "likely_variant"
    if confidence >= 0.30:
        return "weak"
    return "unknown"


def verdict_copy(verdict: str, *, family: str | None = None,
                 sightings: int = 0, shared: int = 0, total: int = 0) -> str:
    """Human-readable verdict. NEVER renders "safe"/"clean"/"legitimate"."""
    if verdict == "known_kit" and family:
        return f"Matches known kit family {family} ({sightings} sightings)"
    if verdict == "likely_variant" and family:
        return (f"Shares {shared} of {total} signals with kit family {family} — "
                "likely variant. Treat as suspicious.")
    if verdict == "likely_variant":
        return "Weak similarity to known kits — treat as suspicious."
    # unknown — the hard rule: never a clean bill of health.
    return "No flags found in RelayShield's corpus — this is not a guarantee of safety."
