#!/usr/bin/env python3
"""Mutation-resistant scam-kit lineage — structural fingerprints.

Companion to ``relayshield_scamkit`` (skfp-v2). That module derives
``kit_<sha256>``: an exact identity over a canonical signal set. Exact
identity is the right tool for "have we seen this precise kit before",
but it decays under AI-driven mutation: the DOM skeleton hash changes
when a tag is inserted or an input is renamed, and a script hash changes
when a single identifier is renamed. Kit authors now paraphrase with
LLMs precisely because that breaks hash-based matching.

This module adds the layer underneath exact identity: a STRUCTURAL
feature set built only from properties a mutation cannot change without
breaking the kit itself:

  * Platform surface. A kit must still call fetch / addEventListener /
    socket.emit by those names — the browser and the relay server do not
    accept paraphrases. Method names on platform objects are invariant.
  * Backend protocol. Panel paths (next.php, /admin/js/mj.php), Socket.IO
    event names, and hardcoded Entra application IDs must match the
    operator's server-side code. Rotating them means rebuilding the
    backend, which is the expensive part of the operation.
  * Harvest shape. The form must still ask for the same field types in
    the same order (text, password, submit) or it stops harvesting.
  * Tree shape. The DOM's parent/child structure survives rewording,
    renaming, and wrapper insertion (single-child container chains are
    compressed away before edges are taken).

Raw values never enter the feature set: hosts appear only as roles and
shapes (external / IP-literal / count bucket), credentials are stripped
with the same patterns as relayshield_scamkit before any analysis, and
wallet addresses appear only as presence tokens. Feature sets are
JSON-canonical and capped per group (the same bounded-input discipline
as the 25-indicator cap in campaign-scan).

Lineage assignment mirrors the house conventions:
  * IDs are deterministic: ``lineage_<sha256>`` over the founding
    member's canonical feature set, minted once. Stability after that
    comes from the registry, exactly as kit family labels are never
    renamed by later sightings.
  * Weak evidence SUGGESTS, never assigns — the same rule as
    suggest_family(). A probable match is returned as a candidate for
    review, not merged.
  * Confidence uses the same band edges as relayshield_scamkit
    (0.90 / 0.60 / 0.30) so API consumers see one confidence language.
    A structural match alone never produces a "known kit" verdict;
    verdict vocabulary stays with compute_confidence().

Pure functions, stdlib only, no network, no AWS — same as the module it
sits beside. See DESIGN.md for the full rationale and API proposal.

PRODUCTION ADAPTATION (2026-10-23, against relayshield main
c8b2bf43deb31257e875686cd9c970f1e4d8d27b): this copy drops the private
_SECRET_PATTERNS table the innovation build carried and imports
strip_secrets from relayshield_scamkit instead — one stripping table,
one owner, exactly as the innovation build's own integration note
prescribed. The two tables were verified identical (same labels, same
order, same regexes) against current main before the swap, and the
fixture suite passes unchanged, so feature extraction is byte-for-byte
the innovation build's behavior. Everything else is unchanged: the
public design (structural features, weighted similarity, assign_lineage
at 0.72 match / 0.55 suggested, lineage_<sha256>) is the innovation
build's, and the signal keys read from extract_signals() output were
re-verified against current main (kit_uri_markers, kit_appid_marks,
hardcoded_ua_marks, socketio_kit_events, title_marks,
turnstile_browser_checks, react_csr, empty_tag_stuffing,
no_turnstile_with_login — all still emitted with the same shapes).
"""

import hashlib
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlparse

from relayshield_scamkit import strip_secrets

LINEAGE_VERSION = "sklin-v1"
LINEAGE_ID_PREFIX = "lineage_"

# Assignment thresholds on the weighted structural similarity score.
# Tuned against the fixtures in test_scamkit_lineage.py: genuine
# mutations of one kit score 0.78+, unrelated kits score under 0.45,
# and a same-scaffold/different-kit case lands in the suggested band.
SAME_LINEAGE_THRESHOLD = 0.72
SUGGEST_LINEAGE_THRESHOLD = 0.55

# A feature set with fewer tokens than this cannot auto-assign, however
# high its score: tiny pages (a bare password form) share shape by
# accident. Exact identity for such pages is kit_<sha256>'s job.
MIN_RICHNESS_TOKENS = 8

# Per-group caps (bounded inputs, deterministic sorted truncation).
MAX_DOM_EDGES = 64
MAX_TAG_TOKENS = 48
MAX_API_TOKENS = 48
MAX_EVENT_TOKENS = 16
MAX_FORMS = 8
MAX_FIELDS_PER_FORM = 25      # the campaign-scan 25-cap, applied per form
MAX_TLD_TOKENS = 6
MAX_SHARED_SAMPLE = 10        # explainability samples in score detail


# ---------------------------------------------------------------------------
# Secret stripping — imported from relayshield_scamkit (see the
# production-adaptation note in the module docstring). Structural
# analysis runs on secret-stripped text so no credential, token, or
# victim value can leak into a feature, a log line, or a stored lineage
# record; the stripping table has exactly one owner.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Light DOM tree (for shape features — NOT the hashed skeleton)
# ---------------------------------------------------------------------------
_VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})

# Presentational wrappers. A wrapper with exactly one element child and
# no direct text is layout noise — AI mutations insert/remove these
# freely — so chains of them are compressed before edges are taken.
_TRANSPARENT_TAGS = frozenset({
    "div", "section", "article", "aside", "header", "footer", "main",
    "nav", "span", "center", "font",
})
_CANON_TAG = {t: "box" for t in _TRANSPARENT_TAGS}
_CANON_TAG.update({f"h{i}": "heading" for i in range(1, 7)})

_MAX_TREE_NODES = 2000  # bounded input: stop growing the tree past this


class _Node:
    __slots__ = ("tag", "children", "has_text")

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.children: list[_Node] = []
        self.has_text = False


class _StructureParser(HTMLParser):
    """Builds a light element tree plus form/script inventories.

    Attribute VALUES are never recorded (they carry nonces and lure
    text) except the few structural ones the harvest-shape features
    need: form method/action, input type/name (name is classified, not
    kept), script src. Mirrors the _SkeletonParser discipline in
    relayshield_scamkit.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("root")
        self._stack: list[_Node] = [self.root]
        self._node_count = 0
        self.forms: list[dict] = []          # {method, action, fields:[(tag,type,name)]}
        self._open_forms: list[dict] = []
        self.scripts: list[tuple[str | None, str]] = []  # (src, body)
        self._script_src: str | None = None
        self._script_buf: list[str] | None = None
        self.anchor_hrefs: list[str] = []
        self.iframe_srcs: list[str] = []
        self.img_srcs: list[str] = []
        self.mailto_domains: list[str] = []
        self.favicon_data_uri = False

    def _attrs(self, attrs) -> dict:
        return {k.lower(): (v or "") for k, v in attrs}

    def handle_starttag(self, tag, attrs) -> None:
        tag = tag.lower()
        a = self._attrs(attrs)
        parent = self._stack[-1]
        node = _Node(tag)
        if self._node_count < _MAX_TREE_NODES:
            parent.children.append(node)
            self._node_count += 1
        if tag not in _VOID_TAGS:
            self._stack.append(node)

        if tag == "form":
            rec = {"method": (a.get("method") or "get").lower(),
                   "action": a.get("action") or "", "fields": []}
            self.forms.append(rec)
            self._open_forms.append(rec)
        elif tag in ("input", "select", "textarea", "button"):
            if self._open_forms:
                ftype = (a.get("type") or ("text" if tag == "input" else tag)).lower()
                self._open_forms[-1]["fields"].append(
                    (tag, ftype, a.get("name") or ""))
        elif tag == "script":
            self._script_src = a.get("src") or None
            self._script_buf = []
        elif tag == "a":
            href = a.get("href") or ""
            if href:
                self.anchor_hrefs.append(href)
                if href.lower().startswith("mailto:"):
                    addr = href[7:].split("?")[0]
                    if "@" in addr:
                        self.mailto_domains.append(addr.split("@")[-1].lower())
        elif tag == "iframe":
            if a.get("src"):
                self.iframe_srcs.append(a["src"])
        elif tag == "img":
            if a.get("src"):
                self.img_srcs.append(a["src"])
        elif tag == "link":
            rel = (a.get("rel") or "").lower()
            href = a.get("href") or ""
            if "icon" in rel and href.lower().startswith("data:"):
                self.favicon_data_uri = True

    def handle_startendtag(self, tag, attrs) -> None:
        # Self-closing form: record the node/field but do not push.
        depth = len(self._stack)
        self.handle_starttag(tag, attrs)
        if len(self._stack) > depth:
            self._stack.pop()
        if tag.lower() == "form" and self._open_forms:
            self._open_forms.pop()

    def handle_endtag(self, tag) -> None:
        tag = tag.lower()
        if tag == "script" and self._script_buf is not None:
            self.scripts.append((self._script_src, "".join(self._script_buf)))
            self._script_buf = None
            self._script_src = None
        if tag == "form" and self._open_forms:
            self._open_forms.pop()
        # Pop to the matching open element; tolerate malformed nesting.
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                del self._stack[i:]
                break

    def handle_data(self, data) -> None:
        if self._script_buf is not None:
            self._script_buf.append(data)
        elif data.strip():
            self._stack[-1].has_text = True


def _compress(node: _Node) -> _Node:
    """Collapse single-child transparent wrappers, bottom-up."""
    node.children = [_compress(c) for c in node.children]
    if (node.tag in _TRANSPARENT_TAGS and len(node.children) == 1
            and not node.has_text):
        return node.children[0]
    return node


def _canon(tag: str) -> str:
    return _CANON_TAG.get(tag, tag)


def _tree_features(root: _Node) -> dict:
    """Edges, tag multiset (bucketed), depth and size from the tree."""
    root = _compress(root)
    edges: set[str] = set()
    tag_counts: dict[str, int] = {}
    max_depth = 0
    node_total = 0

    def walk(node: _Node, depth: int) -> None:
        nonlocal max_depth, node_total
        for child in node.children:
            node_total += 1
            max_depth = max(max_depth, depth + 1)
            ct = _canon(child.tag)
            tag_counts[ct] = tag_counts.get(ct, 0) + 1
            edges.add(f"{_canon(node.tag)}>{ct}")
            walk(child, depth + 1)

    walk(root, 0)

    def count_bucket(n: int) -> str:
        if n <= 1:
            return "1"
        if n <= 3:
            return "2-3"
        if n <= 8:
            return "4-8"
        return "9+"

    tags = sorted(f"tag:{t}:{count_bucket(c)}"
                  for t, c in tag_counts.items())[:MAX_TAG_TOKENS]
    if node_total <= 5:
        size = "xs"
    elif node_total <= 15:
        size = "s"
    elif node_total <= 40:
        size = "m"
    else:
        size = "l"
    if max_depth <= 2:
        depth_b = "shallow"
    elif max_depth <= 4:
        depth_b = "mid"
    elif max_depth <= 7:
        depth_b = "deep"
    else:
        depth_b = "verydeep"
    return {
        "edges": sorted(edges)[:MAX_DOM_EDGES],
        "tags": tags,
        "depth": depth_b,
        "size": size,
    }


# ---------------------------------------------------------------------------
# Form / harvest-shape features
# ---------------------------------------------------------------------------
# Field NAME classes: names themselves are free for an AI to rename, so
# only a coarse semantic class is kept, and only as a set (bonus signal).
# The load-bearing form feature is the field TYPE sequence: a credential
# harvest form must ask text-then-password in order, whatever the fields
# are called.
_NAME_CLASS_RULES: list[tuple[str, re.Pattern]] = [
    ("password", re.compile(r"pass|pwd|passwd", re.IGNORECASE)),
    ("otp", re.compile(r"otp|2fa|mfa|code|token|pin\b", re.IGNORECASE)),
    ("card", re.compile(r"card|ccnum|cc_|pan\b|expir|cvv|cvc", re.IGNORECASE)),
    ("email", re.compile(r"mail", re.IGNORECASE)),
    ("phone", re.compile(r"phone|tel|mobile|sms", re.IGNORECASE)),
    ("identifier", re.compile(r"user|usr|login|acct|account|customer|member", re.IGNORECASE)),
    ("personname", re.compile(r"name|fname|lname|full", re.IGNORECASE)),
]


def _name_class(name: str) -> str:
    for cls, rx in _NAME_CLASS_RULES:
        if rx.search(name or ""):
            return cls
    return "other"


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _action_role(action: str, page_host: str) -> str:
    if not action:
        return "empty"
    host = _host_of(action)
    if not host:
        return "relative"
    if page_host and host == page_host:
        return "self"
    return "external"


def _form_features(parser: _StructureParser, page_host: str) -> dict:
    signatures: list[str] = []
    name_classes: set[str] = set()
    has_password = False
    for rec in parser.forms[:MAX_FORMS]:
        fields = rec["fields"][:MAX_FIELDS_PER_FORM]
        types = []
        for tag, ftype, name in fields:
            types.append(ftype if tag == "input" else tag)
            if ftype == "password":
                has_password = True
            if name:
                name_classes.add(_name_class(name))
        role = _action_role(rec["action"], page_host)
        signatures.append(f"{rec['method']}:{'/'.join(types)}:{role}")
    return {
        "signatures": sorted(set(signatures)),
        "name_classes": sorted(name_classes),
        "count": min(len(parser.forms), MAX_FORMS),
        "has_password": has_password,
    }


# ---------------------------------------------------------------------------
# Script control-flow / platform-surface features
# ---------------------------------------------------------------------------
# The vocabulary is platform surface: names a script cannot be paraphrased
# away from, because the browser, the DOM, and the relay server require
# them verbatim. Local identifiers are NEVER features (they are exactly
# what AI mutation renames).
_API_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("fetch", re.compile(r"\bfetch\s*\(")),
    ("xhr", re.compile(r"XMLHttpRequest")),
    ("sendbeacon", re.compile(r"sendBeacon")),
    ("websocket", re.compile(r"\bWebSocket\b")),
    ("socketio", re.compile(r"\bio\s*\(|io\.connect|socket\.io")),
    ("storage-local", re.compile(r"localStorage")),
    ("storage-session", re.compile(r"sessionStorage")),
    ("doc-cookie", re.compile(r"document\.cookie")),
    ("eval", re.compile(r"\beval\s*\(")),
    ("function-ctor", re.compile(r"\bFunction\s*\(")),
    ("atob", re.compile(r"\batob\s*\(")),
    ("btoa", re.compile(r"\bbtoa\s*\(")),
    ("crypto-subtle", re.compile(r"crypto\.subtle")),
    ("postmessage", re.compile(r"postMessage")),
    ("worker", re.compile(r"\bWorker\s*\(")),
    ("dom-query", re.compile(r"querySelector|getElementById|getElementsBy")),
    ("dom-create", re.compile(r"createElement")),
    ("event-listener", re.compile(r"addEventListener")),
    ("form-submit-call", re.compile(r"\.submit\s*\(")),
    ("location-change", re.compile(r"location\.(?:href|assign|replace)|window\.location\s*=")),
    ("timer", re.compile(r"setTimeout|setInterval")),
    ("json", re.compile(r"JSON\.(?:parse|stringify)")),
]

_LISTENER_RE = re.compile(r"addEventListener\s*\(\s*['\"]([a-zA-Z]{2,24})['\"]")
_EMIT_ON_RE = re.compile(r"\.(?:emit|on)\s*\(\s*['\"]([A-Za-z0-9_\-]{1,40})['\"]")
_SOCKETIO_CTX_RE = re.compile(r"socket\.io|\bio\s*\(|io\.connect\s*\(", re.IGNORECASE)

_STR_LITERAL_RE = re.compile(r"'[^'\n]{0,200}'|\"[^\"\n]{0,200}\"")


def _count_bucket(n: int, cuts: tuple[int, ...], labels: tuple[str, ...]) -> str:
    for cut, label in zip(cuts, labels):
        if n <= cut:
            return label
    return labels[-1]


def _flow_bucket(n: int) -> str:
    return _count_bucket(n, (0, 1, 2, 5, 10), ("0", "1", "2", "3-5", "6-10", "11+"))


def _script_features(script_bodies: list[str]) -> dict:
    """Platform-surface tokens + bucketed control-flow counts.

    Runs on secret-stripped bodies (the extractor strips first), so no
    credential or token value can appear here; string literal CONTENTS
    are never features — only their count bucket and the
    ``has:base64-blob`` shape left behind when strip_secrets redacts a
    long base64 run.
    """
    api: set[str] = set()
    events: set[str] = set()
    flow_counts = {"functions": 0, "loops": 0, "conditionals": 0,
                   "trys": 0, "awaits": 0, "strings": 0}
    has_b64 = False
    total_len = 0
    for body in script_bodies:
        total_len += len(body)
        for token, rx in _API_PATTERNS:
            if rx.search(body):
                api.add(token)
        for m in _LISTENER_RE.finditer(body):
            events.add(f"on:{m.group(1).lower()}")
        if _SOCKETIO_CTX_RE.search(body):
            # Protocol event names must match the relay server verbatim —
            # they survive mutation for the same reason API names do.
            # (Same context rule as relayshield_scamkit's Socket.IO
            # events: no socket.io context, no event features.)
            for m in _EMIT_ON_RE.finditer(body):
                events.add(f"evt:{m.group(1)}")
        flow_counts["functions"] += len(re.findall(r"\bfunction\b|=>", body))
        flow_counts["loops"] += len(re.findall(r"\b(?:for|while)\s*\(", body))
        flow_counts["conditionals"] += len(re.findall(r"\bif\s*\(", body))
        flow_counts["trys"] += len(re.findall(r"\btry\b", body))
        flow_counts["awaits"] += len(re.findall(r"\bawait\b", body))
        flow_counts["strings"] += len(_STR_LITERAL_RE.findall(body))
        if "<STRIPPED:long_b64>" in body:
            has_b64 = True
    flow = {k: _flow_bucket(v) for k, v in flow_counts.items()}
    flow["strings"] = _count_bucket(flow_counts["strings"], (0, 3, 10, 25),
                                    ("0", "1-3", "4-10", "11-25", "26+"))
    flow["bytes"] = _count_bucket(total_len, (0, 200, 1000, 4000),
                                  ("0", "1-200", "201-1000", "1001-4000", "4001+"))
    if has_b64:
        flow["has_base64_blob"] = True
    return {
        "api": sorted(api)[:MAX_API_TOKENS],
        "events": sorted(events)[:MAX_EVENT_TOKENS],
        "flow": flow,
    }


# ---------------------------------------------------------------------------
# Infrastructure-pivot features (roles and shapes — never raw values)
# ---------------------------------------------------------------------------
_SHORTENERS = frozenset({
    "bit.ly", "t.ly", "tinyurl.com", "goo.gl", "ow.ly", "is.gd",
    "buff.ly", "rebrand.ly", "cutt.ly",
})
_WALLET_BTC_RE = re.compile(r"\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b")
_WALLET_ETH_RE = re.compile(r"\b0x[0-9a-fA-F]{40}\b")
_URL_LITERAL_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)


def _infra_features(parser: _StructureParser, clean_html: str,
                    raw_html: str, page_host: str,
                    script_bodies: list[str]) -> dict:
    roles: set[str] = set()
    shapes: set[str] = set()
    ext_hosts: set[str] = set()

    def note_host(url: str) -> str:
        host = _host_of(url)
        if host and host != page_host:
            ext_hosts.add(host)
            return host
        return ""

    for rec in parser.forms:
        if _action_role(rec["action"], page_host) == "external":
            roles.add("form-action-external")
            note_host(rec["action"])
    for href in parser.anchor_hrefs:
        if href.lower().startswith(("http://", "https://")) and note_host(href):
            roles.add("anchor-external")
    for src in parser.iframe_srcs:
        if note_host(src):
            roles.add("iframe-external")
    for src, _body in parser.scripts:
        if src:
            if _host_of(src):
                roles.add("script-src")
            note_host(src)
    for src in parser.img_srcs:
        if note_host(src):
            roles.add("img-external")
    if parser.mailto_domains:
        roles.add("mailto-exfil")
        for d in parser.mailto_domains:
            if d != page_host:
                ext_hosts.add(d)
    for body in script_bodies:
        for m in _URL_LITERAL_RE.finditer(body):
            if note_host(m.group(0)):
                roles.add("script-url-external")
        if "WebSocket" in body or "wss://" in body:
            roles.add("websocket-literal")
    if _SOCKETIO_CTX_RE.search(clean_html):
        roles.add("socketio-relay")

    for host in ext_hosts:
        if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
            shapes.add("host:ip-literal")
        if host in _SHORTENERS:
            shapes.add("host:shortener")
        if "." in host:
            shapes.add(f"tld:{host.rsplit('.', 1)[-1]}")
    # Wallet shapes are detected on the RAW html (like the kit markers):
    # strip_secrets redacts a bare address as a long-base64 run before
    # the stripped text is ever seen. Only the presence token is emitted
    # — the address value itself never enters the feature set.
    if _WALLET_BTC_RE.search(raw_html):
        shapes.add("has:wallet-btc")
    if _WALLET_ETH_RE.search(raw_html):
        shapes.add("has:wallet-eth")
    if parser.favicon_data_uri:
        shapes.add("has:favicon-data-uri")

    return {
        "roles": sorted(roles),
        "shapes": sorted(shapes)[:MAX_TLD_TOKENS + 4],
        "ext_host_count": _count_bucket(len(ext_hosts), (0, 1, 2, 5),
                                        ("0", "1", "2", "3-5", "6+")),
    }


# ---------------------------------------------------------------------------
# Known-constant marks (builtin subset — see DESIGN.md)
# ---------------------------------------------------------------------------
# Public kit-infrastructure constants, mirroring the most load-bearing
# entries of relayshield_scamkit's FLAME v1a tables. In production the
# extractor should be fed the fingerprint call's signals dict (the
# ``signals`` parameter), which carries the full maintained tables; this
# subset keeps the module usable and testable standalone.
_BUILTIN_URI_MARKERS: list[tuple[str, re.Pattern]] = [
    ("greatness-admin-uri", re.compile(r"/admin/js/mj\.php", re.IGNORECASE)),
    ("rockstar-flowerstorm-next-php", re.compile(r"(?<![\w.-])next\.php\b", re.IGNORECASE)),
    ("evilginx-canary-js", re.compile(r"/s/[0-9a-fA-F]{64}\.js\b")),
    ("modlishka-panel", re.compile(r"/SayHello2Modlishka")),
]
_BUILTIN_APPID_MARKS: dict[str, str] = {
    "72782ba9-4490-4f03-8d82-562370ea3566": "rockstar-flowerstorm-appid",
    "4765445b-32c6-49b0-83e6-1d93765276ca": "officehome-token-replay-appid",
}
_KNOWN_SOCKETIO_EVENTS = frozenset({"new-session", "password_command", "otp_command"})
_TITLE_MARKS: list[tuple[str, re.Pattern]] = [
    ("sneaky2fa-gourmet-delights", re.compile(r"^\s*gourmet delights\s*$", re.IGNORECASE)),
]
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_UA_LITERAL_RE = re.compile(r"""['"]Mozilla/5\.0[^'"]{0,160}['"]""")
_EMPTY_TAG_RE = re.compile(r"<(span|b|i|em|strong|u|font|div|p)\s*>\s*</\1\s*>",
                           re.IGNORECASE)
_TURNSTILE_RE = re.compile(r"challenges\.cloudflare\.com/turnstile|cf-turnstile",
                           re.IGNORECASE)
_REACT_RE = re.compile(r"react-dom|ReactDOM\.(?:createRoot|render|hydrate)|data-reactroot",
                       re.IGNORECASE)


def _builtin_marks(raw_html: str) -> dict:
    html = raw_html or ""
    lowered = html.lower()
    marks = {
        "uri": sorted(n for n, rx in _BUILTIN_URI_MARKERS if rx.search(html)),
        "appid": sorted(name for guid, name in _BUILTIN_APPID_MARKS.items()
                        if guid in lowered),
        "ua": sorted(
            (["rockstar-flowerstorm-webview-ua"] if "webview/3.0" in lowered else [])
            + (["multiple-hardcoded-uas"]
               if len({u.strip("'\"") for u in _UA_LITERAL_RE.findall(html)}) >= 2
               else [])),
        "socketio_events": [],
        "titles": [],
    }
    if _SOCKETIO_CTX_RE.search(html):
        found = {m.group(1) for m in _EMIT_ON_RE.finditer(html)}
        marks["socketio_events"] = sorted(found & _KNOWN_SOCKETIO_EVENTS)
    title_m = _TITLE_RE.search(html)
    if title_m:
        title = title_m.group(1).strip()
        marks["titles"] = sorted(n for n, rx in _TITLE_MARKS if rx.search(title))
    return marks


def _marks_from_signals(signals: dict) -> dict:
    return {
        "uri": sorted(signals.get("kit_uri_markers") or []),
        "appid": sorted(signals.get("kit_appid_marks") or []),
        "ua": sorted(signals.get("hardcoded_ua_marks") or []),
        "socketio_events": sorted(signals.get("socketio_kit_events") or []),
        "titles": sorted(signals.get("title_marks") or []),
    }


def _presence_tokens(raw_html: str, signals: dict | None,
                     form_feats: dict) -> list[str]:
    """Behavior-presence tokens (mirrors the presence-style signals in
    relayshield_scamkit's _overlap_score: turnstile, react, stuffing)."""
    tokens: set[str] = set()
    if signals is not None:
        if (signals.get("turnstile_browser_checks") or {}).get("present"):
            tokens.add("has:turnstile")
        if (signals.get("react_csr") or {}).get("present"):
            tokens.add("has:react-csr")
        if (signals.get("empty_tag_stuffing") or {}).get("present"):
            tokens.add("has:empty-tag-stuffing")
        if signals.get("no_turnstile_with_login"):
            tokens.add("has:login-no-turnstile")
    else:
        html = raw_html or ""
        if _TURNSTILE_RE.search(html):
            tokens.add("has:turnstile")
        if _REACT_RE.search(html):
            tokens.add("has:react-csr")
        if len(_EMPTY_TAG_RE.findall(html)) >= 8:
            tokens.add("has:empty-tag-stuffing")
        if form_feats["has_password"] and "has:turnstile" not in tokens:
            tokens.add("has:login-no-turnstile")
    return sorted(tokens)


# ---------------------------------------------------------------------------
# Structural feature extraction
# ---------------------------------------------------------------------------
def _page_url_class(url: str, page_host: str) -> str:
    """Light URL shape class for standalone use. When ``signals`` is
    supplied, its maintained ``url_pattern_class`` is used instead."""
    if not url:
        return "not_provided"
    if not page_host:
        return "unparseable"
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", page_host):
        return "ip-host"
    if page_host in _SHORTENERS:
        return "url-shortener"
    if "xn--" in page_host:
        return "punycode"
    return "standard"


def extract_structural_features(html_text: str, url: str = "",
                                signals: dict | None = None) -> dict:
    """Extract the normalized structural feature set from kit HTML.

    Pure and deterministic: same input ⇒ identical feature dict (all
    lists sorted, all counts bucketed). ``signals`` may carry the
    skfp-v2 signal dict from relayshield_scamkit.extract_signals for the
    same page; when present, its maintained marker tables and URL class
    are used (production path). Without it, builtin subsets apply
    (standalone/testing path).

    Ordering mirrors relayshield_scamkit's rule: known-constant marks
    and wallet shapes are read from the RAW html (strip_secrets would
    redact the GUIDs and address runs they depend on), while script
    bodies are secret-stripped before any feature is taken from them.
    The tree parser also runs on raw html — every feature it feeds is a
    tag name, a classified field name, a host, or a presence flag, and
    mailto domains (an exfil signal) only survive pre-strip. No raw
    attribute value or text content is ever emitted as a feature.
    """
    raw = html_text or ""
    clean = strip_secrets(raw)
    page_host = _host_of(url)

    parser = _StructureParser()
    try:
        parser.feed(raw)
    except Exception:
        # Malformed HTML must not fail extraction — use what was parsed.
        pass

    script_bodies = [strip_secrets(body) for _src, body in parser.scripts
                     if body and body.strip()]
    dom = _tree_features(parser.root)
    forms = _form_features(parser, page_host)
    scripts = _script_features(script_bodies)
    infra = _infra_features(parser, clean, raw, page_host, script_bodies)
    infra["presence"] = _presence_tokens(raw, signals, forms)
    if signals is not None:
        marks = _marks_from_signals(signals)
        infra["url_class"] = signals.get("url_pattern_class") or "not_provided"
        brands = sorted(signals.get("brand_marks") or [])
    else:
        marks = _builtin_marks(raw)
        infra["url_class"] = _page_url_class(url, page_host)
        brands = []
    infra["brands"] = brands

    return {
        "lineage_version": LINEAGE_VERSION,
        "dom": dom,
        "forms": forms,
        "scripts": scripts,
        "infra": infra,
        "marks": marks,
    }


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------
_GROUP_WEIGHTS = {
    "dom": 0.22,      # tree edges + tag multiset + depth/size
    "forms": 0.22,    # harvest shape: field type sequences + name classes
    "scripts": 0.18,  # platform API surface + protocol event names
    "flow": 0.08,     # bucketed control-flow counts
    "infra": 0.12,    # roles, shapes, external-host count, presence, brands
    "marks": 0.18,    # known kit constants (URI paths, App IDs, UA, events)
}


def flatten_features(features: dict) -> dict[str, set[str]]:
    """Project a feature dict to {group: token set} for comparison."""
    dom = features.get("dom") or {}
    forms = features.get("forms") or {}
    scripts = features.get("scripts") or {}
    infra = features.get("infra") or {}
    marks = features.get("marks") or {}
    return {
        "dom": set(dom.get("edges") or []) | set(dom.get("tags") or [])
               | {f"depth:{dom.get('depth')}", f"size:{dom.get('size')}"},
        "forms": set(forms.get("signatures") or [])
                 | {f"nameclass:{c}" for c in forms.get("name_classes") or []}
                 | {f"formcount:{forms.get('count')}",
                    f"haspassword:{bool(forms.get('has_password'))}"},
        "scripts": set(scripts.get("api") or []) | set(scripts.get("events") or []),
        "flow": set(),  # scored by bucket distance, not Jaccard
        "infra": set(infra.get("roles") or []) | set(infra.get("shapes") or [])
                 | set(infra.get("presence") or [])
                 | {f"brand:{b}" for b in infra.get("brands") or []}
                 | {f"exthosts:{infra.get('ext_host_count')}",
                    f"urlclass:{infra.get('url_class')}"},
        "marks": set(marks.get("uri") or []) | set(marks.get("appid") or [])
                 | set(marks.get("ua") or [])
                 | set(marks.get("socketio_events") or [])
                 | set(marks.get("titles") or []),
    }


_CONSTANT_TOKEN_PREFIXES = ("formcount:", "haspassword:", "exthosts:",
                            "urlclass:", "depth:", "size:")


def feature_richness(features: dict) -> int:
    """Distinctive-token count: the evidence available for assignment.

    Constant tokens (present in nearly every page: counts, depth, URL
    class) are excluded — richness measures how much *distinguishing*
    structure a page carries. A near-empty page scores in single digits
    however it is dressed up, which is what MIN_RICHNESS_TOKENS guards.
    """
    flat = flatten_features(features)
    total = 0
    for group in ("dom", "forms", "scripts", "infra", "marks"):
        total += sum(1 for t in flat[group]
                     if not t.startswith(_CONSTANT_TOKEN_PREFIXES))
    return total


def _jaccard(a: set, b: set) -> float:
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _flow_similarity(fa: dict, fb: dict) -> float:
    """Bucket-distance similarity over control-flow count metrics:
    same bucket 1.0, adjacent bucket 0.5, further 0.0."""
    order = ["0", "1", "2", "3-5", "6-10", "11+"]
    str_order = ["0", "1-3", "4-10", "11-25", "26+"]
    byt_order = ["0", "1-200", "201-1000", "1001-4000", "4001+"]
    orders = {"strings": str_order, "bytes": byt_order}
    keys = [k for k in set(fa) | set(fb) if k != "has_base64_blob"]
    if not keys:
        return 0.0
    total = 0.0
    for k in keys:
        va, vb = fa.get(k), fb.get(k)
        if va is None or vb is None:
            continue
        seq = orders.get(k, order)
        try:
            d = abs(seq.index(va) - seq.index(vb))
        except ValueError:
            d = 2
        total += 1.0 if d == 0 else (0.5 if d == 1 else 0.0)
    blob = 1.0 if bool(fa.get("has_base64_blob")) == bool(fb.get("has_base64_blob")) else 0.0
    return (total + blob) / (len(keys) + 1)


def structural_similarity(a: dict, b: dict) -> tuple[float, dict]:
    """Weighted structural similarity in [0.0, 1.0] plus an explainable
    per-group breakdown.

    Each group is scored only when at least one side has tokens in it;
    weights renormalize over the scored groups (the comparable-signals
    discipline of relayshield_scamkit._overlap_score).
    """
    fa, fb = flatten_features(a), flatten_features(b)
    flow_a = (a.get("scripts") or {}).get("flow") or {}
    flow_b = (b.get("scripts") or {}).get("flow") or {}
    detail: dict[str, dict] = {}
    weighted = 0.0
    weight_sum = 0.0
    for group, weight in _GROUP_WEIGHTS.items():
        if group == "flow":
            if not flow_a and not flow_b:
                continue
            score = _flow_similarity(flow_a, flow_b)
            shared = []
        else:
            sa, sb = fa[group], fb[group]
            if not sa and not sb:
                continue
            score = _jaccard(sa, sb)
            shared = sorted(sa & sb)[:MAX_SHARED_SAMPLE]
        detail[group] = {"score": round(score, 3), "weight": weight,
                         "shared": shared}
        weighted += weight * score
        weight_sum += weight
    overall = round(weighted / weight_sum, 4) if weight_sum else 0.0
    return overall, detail


# ---------------------------------------------------------------------------
# Lineage IDs and confidence
# ---------------------------------------------------------------------------
def lineage_id_for(features: dict) -> str:
    """Deterministic lineage ID for a founding feature set:
    ``lineage_<sha256>`` over the canonical feature JSON, namespaced by
    LINEAGE_VERSION — the kit_<sha256> derivation pattern.

    Minted once, when a lineage is founded. Later members do NOT
    recompute it (their features differ — that is the point of fuzzy
    matching); stability comes from the stored assignment, the same way
    a kit's family label is never renamed by later sightings.
    """
    canonical = json.dumps(features, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(
        (LINEAGE_VERSION + ":" + canonical).encode("utf-8")).hexdigest()
    return f"{LINEAGE_ID_PREFIX}{digest}"


def valid_lineage_id(value: str) -> bool:
    """Shape check for caller-supplied IDs: ``lineage_`` + 64 hex chars."""
    return bool(re.fullmatch(r"lineage_[0-9a-f]{64}", value or ""))


def lineage_confidence_band(confidence: float) -> str:
    """Same band edges as relayshield_scamkit.confidence_band, so the
    two products speak one confidence language. Note the lineage band
    describes confidence in the ASSIGNMENT, not a kit verdict: verdict
    vocabulary (known_kit / likely_variant / unknown) and its copy stay
    with relayshield_scamkit.verdict_copy."""
    if confidence >= 0.90:
        return "exact"
    if confidence >= 0.60:
        return "likely_variant"
    if confidence >= 0.30:
        return "weak"
    return "unknown"


def assign_lineage(features: dict, known_lineages: list[dict], *,
                   same_threshold: float = SAME_LINEAGE_THRESHOLD,
                   suggest_threshold: float = SUGGEST_LINEAGE_THRESHOLD) -> dict:
    """Assign ``features`` to a known lineage, suggest one, or found one.

    ``known_lineages``: list of ``{"lineage_id": ..., "features": {...}}``
    (the stored representative — the founding member's feature set —
    plus optionally ``members``: a count, echoed for context only).

    Decisions:
      * ``matched``   — best similarity >= same_threshold: the kit joins
        that lineage; its stored ID is returned. Assignment is stable:
        callers persist (fingerprint_id -> lineage_id) and never
        recompute.
      * ``suggested`` — suggest_threshold <= best < same_threshold, OR
        the feature set is too sparse to auto-assign (richness guard):
        a candidate lineage is named for review but NOT assigned. This
        mirrors suggest_family(): weak evidence suggests, never merges,
        because a wrong merge is worse than a missed one.
      * ``new``       — best < suggest_threshold: a new lineage is
        founded and its deterministic ID minted from these features.

    ``confidence`` is confidence in the stated decision, mapped onto the
    house band edges (see lineage_confidence_band).
    """
    richness = feature_richness(features)
    best_id: str | None = None
    best_score = 0.0
    best_detail: dict = {}
    for entry in known_lineages or []:
        lid = entry.get("lineage_id")
        lfeat = entry.get("features") or {}
        if not lid or not lfeat:
            continue
        score, detail = structural_similarity(features, lfeat)
        if score > best_score:
            best_score, best_id, best_detail = score, lid, detail

    result: dict = {
        "similarity": round(best_score, 4),
        "best_match_detail": best_detail,
        "richness": richness,
        "candidate_lineage_id": None,
    }
    if best_id is not None and best_score >= same_threshold \
            and richness >= MIN_RICHNESS_TOKENS:
        conf = round(0.75 + 0.24 * (best_score - same_threshold)
                     / max(1e-9, 1.0 - same_threshold), 2)
        result.update({
            "decision": "matched",
            "lineage_id": best_id,
            "confidence": min(conf, 0.99),
            "reason": f"structural similarity {best_score:.2f} >= "
                      f"same-lineage threshold {same_threshold:.2f}",
        })
    elif best_id is not None and best_score >= same_threshold:
        # Above the match threshold but too sparse to trust the shape:
        # tiny pages share shape by accident. Suggest, never assign.
        result.update({
            "decision": "suggested",
            "lineage_id": None,
            "candidate_lineage_id": best_id,
            "confidence": 0.45,
            "reason": f"similarity {best_score:.2f} but only {richness} "
                      f"structural tokens (< {MIN_RICHNESS_TOKENS}) — "
                      f"too sparse to auto-assign",
        })
    elif best_id is not None and best_score >= suggest_threshold:
        conf = round(0.45 + 0.29 * (best_score - suggest_threshold)
                     / max(1e-9, same_threshold - suggest_threshold), 2)
        result.update({
            "decision": "suggested",
            "lineage_id": None,
            "candidate_lineage_id": best_id,
            "confidence": conf,
            "reason": f"structural similarity {best_score:.2f} in the "
                      f"suggest band [{suggest_threshold:.2f}, "
                      f"{same_threshold:.2f}) — candidate for review, "
                      f"not merged",
        })
    else:
        conf = 0.99 if best_id is None else round(
            0.55 + 0.44 * (suggest_threshold - best_score)
            / max(1e-9, suggest_threshold), 2)
        result.update({
            "decision": "new",
            "lineage_id": lineage_id_for(features),
            "confidence": min(conf, 0.99),
            "reason": (f"best similarity {best_score:.2f} < suggest "
                       f"threshold {suggest_threshold:.2f} — new lineage "
                       f"founded") if best_id is not None else
                      "no known lineages to compare — new lineage founded",
        })
    result["confidence_band"] = lineage_confidence_band(result["confidence"])
    return result


def cluster_lineages(feature_sets: list[dict]) -> dict:
    """Batch-cluster feature sets into lineages (deterministic).

    Order-independent: inputs are processed in canonical-hash order, so
    the same batch always yields the same clusters regardless of input
    order. Each cluster's representative is its founding member's
    feature set (stable, never silently re-based). A kit whose best
    match lands in the suggest band founds its own cluster AND is
    reported in ``borderline`` with its candidate — batch clustering
    applies the same never-merge-on-weak-evidence rule as assign_lineage.
    """
    order = sorted(range(len(feature_sets)),
                   key=lambda i: lineage_id_for(feature_sets[i]))
    clusters: list[dict] = []
    borderline: list[dict] = []
    for idx in order:
        feats = feature_sets[idx]
        known = [{"lineage_id": c["lineage_id"], "features": c["representative"]}
                 for c in clusters]
        res = assign_lineage(feats, known)
        if res["decision"] == "matched":
            for c in clusters:
                if c["lineage_id"] == res["lineage_id"]:
                    c["members"].append(idx)
                    break
        else:
            lid = res["lineage_id"] or lineage_id_for(feats)
            clusters.append({"lineage_id": lid, "members": [idx],
                             "representative": feats})
            if res["decision"] == "suggested":
                borderline.append({
                    "index": idx,
                    "founded_lineage_id": lid,
                    "candidate_lineage_id": res["candidate_lineage_id"],
                    "similarity": res["similarity"],
                })
    return {"clusters": clusters, "borderline": borderline}
