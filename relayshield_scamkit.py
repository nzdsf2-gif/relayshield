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
  * EXCEPTION (FLAME v1a, deliberate): kit-infrastructure constants — known
    phishing-kit URI paths, hardcoded Entra application IDs, hardcoded
    User-Agent literals, Socket.IO event names — are extracted from the RAW
    HTML *before* strip_secrets() runs, because strip_secrets() would redact
    the GUIDs and long hex runs they depend on (e.g. the FlowerStorm Entra
    application ID, Evilginx canary values). These are public,
    kit-attributable IOCs, not victim secrets; only *matched known-marker
    names* enter the hashed signal set, while raw values (AppIDs, hosts)
    are emitted separately in ``corpus_candidates`` for later TI loading.
  * Family names: the 13 FLAME TP-0067 kit families Andrew approved on
    2026-09-25 are emitted with ``family_status="approved"`` (see
    APPROVED_FAMILIES / family_status_for()); every other name is
    ``"suggested"``. No code path approves a name outside that set —
    additional approvals are a manual, out-of-band act by Andrew.
  * Verdict copy never says "safe". The best case is "no flags found" with
    an explicit not-a-guarantee caveat.
  * ``kind`` discriminates ``kit_`` from the planned ``malware_<sha256>``
    IDs (spec §8). v1 code paths only emit ``kit_``.

FLAME v1a (2026-09-25): 13 static AiTM-kit indicators from FLAME TP-0067
(AiTM Phishing Kit Infrastructure). Tycoon 2FA markers are HISTORICAL —
taken down 2026-03-04 (Europol-led, 330 domains seized) — kept as
backfill markers, not expectations of current activity. Values FLAME
publishes only in truncated form (Sneaky 2FA favicon hash) or as theme
descriptions (Rockstar/FlowerStorm titles) are NOT seeded; only complete,
verifiable constants are.

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
FINGERPRINT_VERSION = "skfp-v2"  # bump whenever normalization changes
FINGERPRINT_VERSION_V1 = "skfp-v1"  # previous schema — rows remain valid (dual-version)
SUPPORTED_FINGERPRINT_VERSIONS = (FINGERPRINT_VERSION_V1, FINGERPRINT_VERSION)

# Exact skfp-v1 signal schema. v1_signal_projection() maps a v2 signal dict
# back to this key set so a re-sighted kit resolves to its pre-v2 row
# instead of silently forking a new fingerprint ID (no silent ID churn).
V1_SIGNAL_KEYS = (
    "brand_marks",
    "dom_skeleton_hash",
    "exfil_endpoints",
    "form_action_hosts",
    "kind",
    "script_hashes",
    "sms_lure_template_hash",
    "url_pattern_class",
)

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


# ---------------------------------------------------------------------------
# FLAME v1a static kit markers (TP-0067 AiTM catalog, reviewed 2026-04-02)
# ---------------------------------------------------------------------------
# Every constant below is a COMPLETE, verifiable value published in FLAME
# TP-0067. Deliberately NOT seeded, per data-hygiene rules:
#   * Sneaky 2FA base64 favicon SHA256 — FLAME publishes it truncated
#     ("5d91563b..."). favicon_data_hash still detects data-URI favicons;
#     the known-bad list stays empty until a complete hash is published.
#   * Rockstar 2FA "car-themed" / FlowerStorm "botanical-themed" titles —
#     FLAME describes the themes but publishes no complete titles. Only the
#     complete Sneaky 2FA title "Gourmet Delights" is seeded.
# Tycoon 2FA markers are HISTORICAL (takedown 2026-03-04) — backfill only.

HISTORICAL_FAMILIES = frozenset({"tycoon-2fa"})

# marker_name -> (regex, family_hint). family_hint feeds corpus_candidates'
# marker_family_hints only — it never auto-assigns kit_family (suggest-only).
_KIT_URI_MARKERS: list[tuple[str, re.Pattern, str | None]] = [
    ("greatness-admin-uri",
     re.compile(r"/admin/js/mj\.php", re.IGNORECASE), "greatness"),
    ("rockstar-flowerstorm-next-php",
     re.compile(r"(?<![\w.-])next\.php\b", re.IGNORECASE), "flowerstorm"),
    ("modlishka-panel",
     re.compile(r"/SayHello2Modlishka"), "modlishka"),
    ("muraena-instrument",
     re.compile(r"/instrument\b"), "muraena"),
    ("chenlun-resource-config",
     re.compile(r"ResourceRedConfig\.js|/ResourceConfig/urlConfig\.json"), "chenlun"),
    ("evilginx-canary-js",
     re.compile(r"/s/[0-9a-fA-F]{64}\.js\b"), "evilginx"),
    ("greatness-httpd-grt",
     re.compile(r"httpd\.grt", re.IGNORECASE), "greatness"),
]

# guid -> (marker_name, family_hint). Public kit-infrastructure constants.
_KNOWN_APP_IDS: dict[str, tuple[str, str | None]] = {
    # Rockstar 2FA / FlowerStorm Office365 app (Storm-1575 lineage)
    "72782ba9-4490-4f03-8d82-562370ea3566": ("rockstar-flowerstorm-appid", "flowerstorm"),
    # OfficeHome app ID — commonly appears in AiTM token replay
    "4765445b-32c6-49b0-83e6-1d93765276ca": ("officehome-token-replay-appid", None),
}

# Contexts in which a GUID is an application/client identifier (public IOC),
# never a victim secret. Unknown GUIDs found ONLY in these contexts become
# corpus candidates.
_APPID_CONTEXT_RE = re.compile(
    r"(?:client_id|clientid|appId|app_id|applicationId|x-client-id)"
    r"\s*[\"':=]\s*[\"']?"
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    r"[\"']?"
    r"|api://([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
    re.IGNORECASE,
)

_KNOWN_UA_MARKS: list[tuple[str, re.Pattern, str | None]] = [
    # Rockstar 2FA / FlowerStorm hardcoded WebView UA
    ("rockstar-flowerstorm-webview-ua",
     re.compile(r"WebView/3\.0"), "flowerstorm"),
]
_UA_LITERAL_RE = re.compile(r"""['"]Mozilla/5\.0[^'"]{0,160}['"]""")

_SOCKETIO_LIB_RE = re.compile(r"socket\.io", re.IGNORECASE)
_SOCKETIO_CONNECT_RE = re.compile(r"\bio\s*\(\s*['\"]|io\.connect\s*\(", re.IGNORECASE)
# Mamba 2FA Socket.IO relay events — only counted with a socket.io context
# present, so generic words like "new-session" don't false-positive.
_KNOWN_SOCKETIO_EVENTS = ("new-session", "password_command", "otp_command")
_SOCKETIO_EVENT_RE = re.compile(
    r"(?:emit|on)\s*\(\s*['\"](new-session|password_command|otp_command)['\"]")

_TURNSTILE_ARTIFACTS: list[tuple[str, re.Pattern]] = [
    ("turnstile-script", re.compile(r"challenges\.cloudflare\.com/turnstile", re.IGNORECASE)),
    ("cf-turnstile-div", re.compile(r"cf-turnstile", re.IGNORECASE)),
    ("turnstile-explicit", re.compile(r"Cloudflare\s+Turnstile", re.IGNORECASE)),
]
# Tycoon 2FA's page text (FLAME TP-0067). HISTORICAL — takedown 2026-03-04.
_TYCOON_BROWSER_CHECKS_RE = re.compile(r"browser checks", re.IGNORECASE)

_LOGIN_PASSWORD_RE = re.compile(
    r"""<input\b[^>]*\btype\s*=\s*["']password["'][^>]*>""", re.IGNORECASE)

_FAVICON_LINK_RE = re.compile(
    r"""<link\b[^>]*\brel\s*=\s*["'](?:shortcut\s+)?icon["'][^>]*>""", re.IGNORECASE)
_HREF_ATTR_RE = re.compile(r"""\bhref\s*=\s*["']([^"']+)["']""", re.IGNORECASE)

_EMPTY_TAG_RE = re.compile(
    r"<(span|b|i|em|strong|u|font|div|p)\s*>\s*</\1\s*>", re.IGNORECASE)
# Sneaky 2FA: "empty HTML tags between characters" (TP-0067).
_EMPTY_TAG_STUFFING_THRESHOLD = 8

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
# Only complete, verifiable titles are seeded — never invented ones.
_KNOWN_KIT_TITLES: list[tuple[str, re.Pattern, str | None]] = [
    ("sneaky2fa-gourmet-delights",
     re.compile(r"^\s*gourmet delights\s*$", re.IGNORECASE), "sneaky-2fa"),
]

_REACT_ARTIFACTS: list[tuple[str, re.Pattern]] = [
    # Darcula ships React client-side rendering (TP-0067).
    ("react-dom-script", re.compile(r"react-dom(?:\.production|\.development)?\.min\.js|react-dom@", re.IGNORECASE)),
    ("react-script", re.compile(r"(?<!dom)react(?:\.production|\.development)?\.min\.js", re.IGNORECASE)),
    ("data-reactroot", re.compile(r"data-reactroot", re.IGNORECASE)),
    ("react-devtools-hook", re.compile(r"__REACT_DEVTOOLS_GLOBAL_HOOK__")),
    ("reactdom-render", re.compile(r"ReactDOM\.(createRoot|render|hydrate)")),
    ("nextjs-chunks", re.compile(r"/_next/static/chunks/")),
]

_ANCHOR_HREF_RE = re.compile(
    r"""<a\b[^>]*\bhref\s*=\s*["'](https?://[^"'<>\s]+)["']""", re.IGNORECASE)
_IFRAME_SRC_RE = re.compile(
    r"""<iframe\b[^>]*\bsrc\s*=\s*["'](https?://[^"'<>\s]+)["']""", re.IGNORECASE)
_SCRIPT_SRC_RE = re.compile(
    r"""<script\b[^>]*\bsrc\s*=\s*["']([^"'<>\s]+)["']""", re.IGNORECASE)
_MAILTO_RE = re.compile(
    r"""mailto:([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})""", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _classify_url_pattern_v1(url: str) -> str:
    """skfp-v1 URL classifier — frozen. Used for the v1 backfill projection;
    do not change its behavior."""
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


# FLAME v1a kit URL patterns (TP-0067). Static-text classes fire on the URL
# itself; redirect-behavior classes need fetch-pipeline observations and
# never fire from static text alone.
_EVILGINX_LURE_RE = re.compile(r"/[A-Za-z]{8}(?:[/?#]|$)")
_EVILGINX_CANARY_RE = re.compile(r"/s/[0-9a-fA-F]{64}\.js(?:[?#]|$)")
_MAMBA_PATH_RE = re.compile(r"^/[mno]/$")
_MAMBA_QUERY_RE = re.compile(r"^[A-Za-z0-9%+/_=-]{8,}$")
_GREATNESS_ADMIN_PATH = "/admin/js/mj.php"
_RICKROLL_IDS = ("dQw4w9WgXcQ",)


def classify_url_pattern(url: str, observations: dict | None = None) -> str:
    """Coarse URL shape class — stable across per-victim nonce rotation.

    v2 adds five FLAME TP-0067 kit classes (checked before the v1
    fallbacks; the v1 class is preserved separately as
    ``url_pattern_class_v1``). Two redirect-behavior classes
    (``evilginx-rickroll-redirect``, ``w3ll-wikipedia-antibot-redirect``)
    are reserved for fetch-pipeline ``observations`` (``redirect_chain``)
    and never fire from static URL text alone.
    """
    if not url:
        return "not_provided"
    clean = _strip_url_nonces(url)
    host = _host_of(clean)
    if not host:
        return "unparseable"

    # Fetch-pipeline behavior classes (dormant until observations exist).
    if observations:
        raw_chain = observations.get("redirect_chain") or []
        # v1b pipeline records hops as {"url", "status"} dicts; accept plain
        # URL strings too (earlier contract).
        chain = [h.get("url", "") if isinstance(h, dict) else h
                 for h in raw_chain]
        if any(any(rid in u for rid in _RICKROLL_IDS) or "rickroll" in u.lower()
               for u in chain):
            return "evilginx-rickroll-redirect"
        if chain and "wikipedia.org" in _host_of(chain[-1]):
            return "w3ll-wikipedia-antibot-redirect"

    parts = urlparse(clean)
    path = parts.path or "/"

    # FLAME v1a kit URL classes (static).
    if _EVILGINX_CANARY_RE.search(path):
        return "evilginx-canary"          # Evilginx /s/<64hex>.js canary
    if _MAMBA_PATH_RE.match(path) and _MAMBA_QUERY_RE.match(parts.query or ""):
        return "mamba-relay-url"           # Mamba 2FA /{m,n,o}/?{Base64}
    if _GREATNESS_ADMIN_PATH in path.lower():
        return "greatness-admin-uri"       # Greatness /admin/js/mj.php
    if host.endswith(".buzz"):
        labels = host.split(".")
        if max((len(lb) for lb in labels), default=0) >= 12:
            return "nakedpages-buzz-domain"  # NakedPages .buzz long-name domains
    if _EVILGINX_LURE_RE.search(path):
        return "evilginx-lure-path"        # Evilginx 8-char alpha lure paths

    return _classify_url_pattern_v1(url)


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


def _extract_kit_markers(raw_html: str, url: str = "") -> tuple[dict, list[str]]:
    """Extract FLAME v1a kit markers from RAW HTML — BEFORE strip_secrets().

    Returns (markers, family_hints). family_hints are kit-family names
    suggested by the markers; they are informational only (suggest-only —
    this module never assigns kit_family).

    CRITICAL ORDERING: strip_secrets() redacts GUIDs (uuid pattern) and
    long hex runs (long_hex pattern). The FlowerStorm Entra application ID
    and Evilginx canary values would be erased by it, so every marker here
    is matched against the raw page. Marker *names* (not raw values) enter
    the hashed signal set; raw IOC values go to corpus_candidates.
    """
    html = raw_html or ""
    page_host = _host_of(url)
    markers: dict = {}
    hints: set[str] = set()

    # 1. kit_uri_markers — known phishing-kit URI path markers in HTML/JS
    uri_hits = []
    for name, rx, fam in _KIT_URI_MARKERS:
        if rx.search(html):
            uri_hits.append(name)
            if fam:
                hints.add(fam)
    markers["kit_uri_markers"] = sorted(uri_hits)

    # 2. turnstile_browser_checks — Cloudflare Turnstile artifacts
    t_artifacts = sorted(n for n, rx in _TURNSTILE_ARTIFACTS if rx.search(html))
    tycoon_text = bool(_TYCOON_BROWSER_CHECKS_RE.search(html))
    turnstile_present = bool(t_artifacts)
    markers["turnstile_browser_checks"] = {
        "present": turnstile_present,
        "artifacts": t_artifacts,
        # Tycoon 2FA's "browser checks" page text — HISTORICAL (takedown 2026-03-04)
        "tycoon_browser_checks_text": tycoon_text,
    }
    if turnstile_present and tycoon_text:
        hints.add("tycoon-2fa")

    # 3. kit_appid_marks — hardcoded Entra application IDs (marker names only)
    lowered = html.lower()
    appid_hits = []
    for guid, (name, fam) in _KNOWN_APP_IDS.items():
        if guid in lowered:
            appid_hits.append(name)
            if fam:
                hints.add(fam)
    markers["kit_appid_marks"] = sorted(appid_hits)

    # 4. hardcoded_ua_marks — hardcoded User-Agent strings used by kits
    ua_hits = []
    for name, rx, fam in _KNOWN_UA_MARKS:
        if rx.search(html):
            ua_hits.append(name)
            if fam:
                hints.add(fam)
    ua_literals = {u.strip("'\"") for u in _UA_LITERAL_RE.findall(html)}
    if len(ua_literals) >= 2:
        # Sneaky 2FA analog: distinct hardcoded UAs per auth step
        # (Safari/iOS for login, Edge/Windows for resume).
        ua_hits.append("multiple-hardcoded-uas")
    markers["hardcoded_ua_marks"] = sorted(set(ua_hits))

    # 5. socketio_kit_events — Mamba 2FA Socket.IO relay event names
    sio_context = bool(_SOCKETIO_LIB_RE.search(html) or _SOCKETIO_CONNECT_RE.search(html))
    sio_events = sorted(set(_SOCKETIO_EVENT_RE.findall(html))) if sio_context else []
    markers["socketio_kit_events"] = sio_events
    if sio_events:
        hints.add("mamba-2fa")

    # 6. no_turnstile_with_login — negative signal: login form, no Turnstile
    # (Mamba 2FA explicitly ships NO Cloudflare Turnstile). Corroborating
    # only — never a verdict driver on its own.
    has_login = bool(_LOGIN_PASSWORD_RE.search(html))
    markers["no_turnstile_with_login"] = has_login and not turnstile_present

    # 7. favicon_data_hash — sha256 of inline/data-URI favicon, when present.
    # known_bad stays False: FLAME publishes Sneaky 2FA's base64 favicon
    # SHA256 truncated ("5d91563b..."), so no complete hash can be seeded.
    favicon_sha = None
    for lm in _FAVICON_LINK_RE.finditer(html):
        hm = _HREF_ATTR_RE.search(lm.group(0))
        if not hm:
            continue
        href = hm.group(1)
        if href.lower().startswith("data:"):
            parts = href.split(",", 1)
            if len(parts) == 2 and parts[1]:
                favicon_sha = _sha256_hex(parts[1])
                break
    markers["favicon_data_hash"] = {"sha256": favicon_sha, "known_bad": False}

    # 8. empty_tag_stuffing — Sneaky 2FA: empty HTML tags between characters
    empty_count = len(_EMPTY_TAG_RE.findall(html))
    markers["empty_tag_stuffing"] = {
        "present": empty_count >= _EMPTY_TAG_STUFFING_THRESHOLD,
        "empty_tag_count": empty_count,
    }

    # 9. title_marks — kit page-title markers (complete titles only)
    title_m = _TITLE_RE.search(html)
    title_text = title_m.group(1).strip() if title_m else ""
    title_hits = []
    for name, rx, fam in _KNOWN_KIT_TITLES:
        if title_text and rx.search(title_text):
            title_hits.append(name)
            if fam:
                hints.add(fam)
    markers["title_marks"] = sorted(title_hits)

    # 10. react_csr — React client-side-rendering artifacts (Darcula)
    r_artifacts = sorted(n for n, rx in _REACT_ARTIFACTS if rx.search(html))
    markers["react_csr"] = {"present": bool(r_artifacts), "artifacts": r_artifacts}

    # 11. anchor_exfil_hosts — exfil hosts in anchor hrefs (≠ page host)
    anchor_hosts = set()
    for m in _ANCHOR_HREF_RE.finditer(html):
        h = _host_of(m.group(1))
        if h and h != page_host:
            anchor_hosts.add(h)
    markers["anchor_exfil_hosts"] = sorted(anchor_hosts)

    # 12. email_hosts — email-address exfil hosts (mailto:), ≠ page host
    email_hosts = set()
    for m in _MAILTO_RE.finditer(html):
        d = m.group(1).split("@")[-1].lower()
        if d and d != page_host:
            email_hosts.add(d)
    markers["email_hosts"] = sorted(email_hosts)

    return markers, sorted(hints)


def extract_corpus_candidates(html: str, url: str = "",
                              signals: dict | None = None) -> dict:
    """Structured TI-corpus load candidates — NOT hashed into the fingerprint.

    Emitted alongside each fingerprint so corpus loaders can review and
    ingest them later. THIS MODULE WRITES TO NO LIVE STORE; callers decide
    what to persist. Only kit-infrastructure values are included:

      * app_ids: GUIDs in Entra-style auth contexts (client_id=, appId=,
        api://…) plus any known kit App IDs found in the page. A bare GUID
        in prose is NOT a candidate — context is required.
      * exfil_hosts: external hosts from anchors, iframes, form actions,
        and the exfil_endpoints signal (folded in when signals given).
      * email_hosts / kit_uri_markers / socketio_hosts: as extracted.
      * marker_family_hints: kit families suggested by markers
        (suggest-only; "tycoon-2fa" hints are historical — see
        HISTORICAL_FAMILIES).

    Victim-shaped values (passwords, tokens, personal emails as identifiers)
    are never candidates.
    """
    raw = html or ""
    page_host = _host_of(url)
    markers, hints = _extract_kit_markers(raw, url)

    app_ids: set[str] = set()
    lowered = raw.lower()
    for guid in _KNOWN_APP_IDS:
        if guid in lowered:
            app_ids.add(guid)
    for m in _APPID_CONTEXT_RE.finditer(raw):
        app_ids.add((m.group(1) or m.group(2)).lower())

    exfil_hosts: set[str] = set()
    for rx in (_ANCHOR_HREF_RE, _IFRAME_SRC_RE):
        for m in rx.finditer(raw):
            h = _host_of(m.group(1))
            if h and h != page_host:
                exfil_hosts.add(h)
    if signals:
        for key in ("form_action_hosts", "anchor_exfil_hosts", "exfil_endpoints"):
            for h in signals.get(key) or []:
                if h and h != page_host:
                    exfil_hosts.add(h)

    socketio_hosts: set[str] = set()
    if markers["socketio_kit_events"] or _SOCKETIO_LIB_RE.search(raw):
        for m in _SCRIPT_SRC_RE.finditer(raw):
            if "socket.io" in m.group(1).lower():
                h = _host_of(m.group(1))
                if h:
                    socketio_hosts.add(h)

    return {
        "app_ids": sorted(app_ids),
        "email_hosts": markers["email_hosts"],
        "exfil_hosts": sorted(exfil_hosts),
        "kit_uri_markers": markers["kit_uri_markers"],
        "marker_family_hints": hints,
        "socketio_hosts": sorted(socketio_hosts),
    }


def extract_signals(html_text: str, url: str = "",
                    observations: dict | None = None) -> dict:
    """Extract the v2 signal set from kit HTML. Pure; no network.

    ORDERING (hard rule): FLAME v1a kit markers are extracted from the RAW
    HTML FIRST — strip_secrets() would redact the GUIDs and long hex runs
    they depend on (FlowerStorm App ID, Evilginx canary). The v1 signal
    pipeline below it is byte-identical to skfp-v1 (see
    v1_signal_projection()); only additive v2 fields follow it.

    ``observations`` is the future fetch-pipeline hook (redirect chains,
    TLS facts). When None, behavior is static-HTML-only.

    Returned dict is JSON-canonical (sorted keys) and fully stripped of
    secrets — safe to hash, log (at low verbosity), and store.
    """
    raw = html_text or ""
    markers, _hints = _extract_kit_markers(raw, url)

    clean = strip_secrets(raw)
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

    signals = {
        "brand_marks": brands,
        "dom_skeleton_hash": _sha256_hex("".join(parser.parts)),
        "exfil_endpoints": sorted(exfil),
        "fingerprint_version": FINGERPRINT_VERSION,
        "form_action_hosts": form_hosts,
        "kind": "kit",
        "script_hashes": sorted(set(script_hashes)),
        "sms_lure_template_hash": lure_hash,
        "url_pattern_class": classify_url_pattern(url, observations),
        # v1 fallback class — feeds v1_signal_projection() for the
        # dual-version backfill (no silent ID churn on upgrade).
        "url_pattern_class_v1": _classify_url_pattern_v1(url),
    }
    # FLAME v1a additions (additive only — v1 keys above are untouched).
    signals.update(markers)
    return signals


# ---------------------------------------------------------------------------
# Fingerprint IDs
# ---------------------------------------------------------------------------
def v1_signal_projection(signals: dict) -> dict:
    """Project a v2 signal dict back to the exact skfp-v1 schema.

    Dual-version backfill: the v1 digest of a re-sighted kit must equal the
    ID stored before the v2 upgrade, so the sighting links to the same
    family record instead of silently forking a new fingerprint ID. The v1
    extraction pipeline is unchanged by v1a (markers are additive), and the
    v1 URL class is carried in every v2 signal dict as
    ``url_pattern_class_v1`` for exactly this purpose.
    """
    proj = {k: signals.get(k) for k in V1_SIGNAL_KEYS}
    proj["url_pattern_class"] = signals.get("url_pattern_class_v1")
    proj["fingerprint_version"] = FINGERPRINT_VERSION_V1
    return proj


def fingerprint_id(signals: dict, kind: str = "kit",
                   version: str | None = None) -> str:
    """Stable ID: ``kit_<sha256>`` over the canonical feature vector.

    Same kit ⇒ same ID across sightings. ``kind="malware"`` is the planned
    extension point (spec §8) and yields ``malware_<sha256>``; v1 callers
    must pass ``kind="kit"``.

    ``version`` selects the digest namespace and defaults to the signal
    dict's declared ``fingerprint_version`` (falling back to the current
    ``FINGERPRINT_VERSION``). skfp-v1 rows hash under "skfp-v1" and stay
    valid; new fingerprints hash under "skfp-v2".
    """
    if kind == "malware":
        prefix = MALWARE_ID_PREFIX
    else:
        prefix = KIT_ID_PREFIX
    ver = version or signals.get("fingerprint_version") or FINGERPRINT_VERSION
    if ver not in SUPPORTED_FINGERPRINT_VERSIONS:
        raise ValueError(f"unsupported fingerprint version: {ver!r}")
    canonical = json.dumps(signals, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256((ver + ":" + canonical).encode("utf-8")).hexdigest()
    return f"{prefix}{digest}"


def valid_fingerprint_id(value: str) -> bool:
    """Shape check for caller-supplied IDs: ``kit_`` + 64 hex chars."""
    return bool(re.fullmatch(r"kit_[0-9a-f]{64}", value or ""))


# ---------------------------------------------------------------------------
# Family names — Andrew-approved set
# ---------------------------------------------------------------------------
# Andrew approved these 13 FLAME TP-0067 kit family names on 2026-09-25.
# They may be emitted with family_status="approved" via family_status_for();
# every other name stays "suggested". Human review can still set approved
# manually on any row via a direct table edit — approval logic never
# fabricates sightings or corpus writes.
APPROVED_FAMILIES = frozenset({
    "tycoon-2fa", "evilginx", "sneaky-2fa", "mamba-2fa", "evilproxy",
    "flowerstorm", "rockstar-2fa", "nakedpages", "w3ll-panel", "greatness",
    "caffeine", "sessionshark", "darcula",
})


def family_status_for(name: str | None) -> str:
    """``"approved"`` for an Andrew-approved family name, else ``"suggested"``."""
    return "approved" if (name or "").strip().lower() in APPROVED_FAMILIES else "suggested"


# ---------------------------------------------------------------------------
# Family auto-suggest (deterministic)
# ---------------------------------------------------------------------------
# Signal weights for overlap scoring. The DOM skeleton is the strongest
# kit-identity signal; hardcoded Entra App IDs are near-deterministic kit
# constants (FLAME TP-0067); shared scripts next; hosts/brands/markers are
# corroborating.
_SIGNAL_WEIGHTS = {
    "dom_skeleton_hash": 3,
    "kit_appid_marks": 3,    # per shared App ID marker (FLAME v1a)
    "script_hashes": 2,      # per shared hash
    "kit_uri_markers": 2,    # per shared URI marker (FLAME v1a)
    "hardcoded_ua_marks": 2,  # per shared UA marker (FLAME v1a)
    "socketio_kit_events": 2,  # per shared Socket.IO event (FLAME v1a)
    "title_marks": 2,        # per shared title marker (FLAME v1a)
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
    for key in ("script_hashes", "form_action_hosts", "exfil_endpoints",
                "brand_marks", "kit_uri_markers", "kit_appid_marks",
                "hardcoded_ua_marks", "socketio_kit_events", "title_marks"):
        sa, sb = set(a.get(key) or []), set(b.get(key) or [])
        if sa or sb:
            comparable += 1
            score += len(sa & sb) * _SIGNAL_WEIGHTS[key]
    # Presence-style dict markers: 1 point when both pages exhibit them.
    for key in ("turnstile_browser_checks", "react_csr"):
        pa = bool((a.get(key) or {}).get("present"))
        pb = bool((b.get(key) or {}).get("present"))
        if pa or pb:
            comparable += 1
            if pa and pb:
                score += 1
    return score, comparable


def suggest_family(signals: dict, known_families: list[dict]) -> tuple[str | None, str | None]:
    """Deterministic family auto-suggest.

    ``known_families``: list of ``{"family": name, "signals": {...}}`` —
    families whose status the caller has already resolved (suggested or
    approved; this function does not distinguish, it only matches shape).

    Returns ``(family_name, family_status_for(family_name))`` or
    ``(None, None)``. The 13 FLAME TP-0067 families Andrew approved on
    2026-09-25 are returned with status ``"approved"``; every other name
    is ``"suggested"``.

    HARD RULE: only names in APPROVED_FAMILIES can ever be emitted as
    ``"approved"``. There is no parameter, flag, or code path that approves
    any other name. Marking an additional family approved is a manual act by
    Andrew, recorded directly on the stored fingerprint item — never by
    this code.
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
        return best, family_status_for(best)
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
