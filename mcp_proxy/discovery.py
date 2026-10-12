"""Screen MCP DISCOVERY responses (initialize, tools/list, prompts/list,
resources/list) for the two disclosed attack patterns in the taxonomy:

  MCP-2026-008  a server marks a poisoned discovery response cacheScope=public,
                so a shared gateway re-serves it across authorization contexts.
  MCP-2026-015  the server-authored `instructions` field is folded into the
                client's system prompt with no sanitisation or length limit.

Until this module the proxy forwarded every discovery response untouched and
screened only tools/call results, so neither pattern could be seen at all.

DESIGN RULES, all deliberate:
  * FLAG, NEVER BLOCK. Discovery responses carry legitimate `instructions` and
    legitimate public caches. Same fail-open posture as result screening.
  * cacheScope=public ALONE IS NOT A FINDING. Static tool lists are public on
    purpose. It is an AMPLIFIER: it selects the 008 / chained taxonomy entries
    only when the response also carries something hostile. It is reported in
    `details` either way.
  * NO PAYLOAD IN THE VERDICT. Reasons name the pattern that fired, never the
    text that matched: the field is attacker-authored and may be long, encoded,
    or itself an injection aimed at whatever reads the log.
  * The cross-tenant anomaly entries (008_unknown_synthetic on one payload seen
    in several contexts) need MANY contexts and cannot be seen by one proxy.
    They are not emitted here.
"""
import re

from .screener import (_PROMPT_INJECTION_PATTERNS, _has_synthetic_hints,
                       extract_indicators, worst_category,
                       POISON_PROMPT_INJECTION, POISON_PII_LEAK,
                       POISON_MALICIOUS_URL, POISON_UNKNOWN_SYNTHETIC)
from . import taxonomy

DISCOVERY_METHODS = frozenset(
    {"initialize", "tools/list", "prompts/list", "resources/list"})

# The disclosure says there is no length limit; this is where we start to
# notice. Legitimate guidance is short.
INSTRUCTIONS_MAX_CHARS = 2000
MAX_URLS_CHECKED = 5

_EXFIL_RE = re.compile(
    r"\b(export|exfiltrate|send|upload|reveal|leak|forward|transmit|email|post)\b"
    r".{0,80}?"
    r"\b(database url|database|conversation|chat history|history|api[ _-]?keys?|"
    r"secrets?|passwords?|credentials?|tokens?|private keys?|\.env|"
    r"environment variables?)\b",
    re.IGNORECASE | re.DOTALL)
# Zero-width, bidi-control and Unicode tag characters: the same hiding places
# the agent-bait skill reads for.
_HIDDEN_RE = re.compile("[​-‏⁠⁦-⁩﻿\U000e0000-\U000e007f]")  # nosec B613
_BLOB_RE = re.compile(r"[A-Za-z0-9+/]{120,}={0,2}|[0-9a-fA-F]{120,}")
_CHAIN_CUE_RE = re.compile(r"\b(always|first|must|before|after|then)\b", re.IGNORECASE)

_SKIP_ITEM_KEYS = frozenset({"name", "uri", "mimeType", "version"})


def _walk_strings(node, out, depth=0):
    if depth > 10:
        return
    if isinstance(node, str):
        if node.strip():
            out.append(node)
    elif isinstance(node, dict):
        for v in node.values():
            _walk_strings(v, out, depth + 1)
    elif isinstance(node, (list, tuple)):
        for v in node:
            _walk_strings(v, out, depth + 1)


def _find_cache_public(node, depth=0) -> bool:
    if depth > 10:
        return False
    if isinstance(node, dict):
        if node.get("cacheScope") == "public":
            return True
        return any(_find_cache_public(v, depth + 1) for v in node.values())
    if isinstance(node, (list, tuple)):
        return any(_find_cache_public(v, depth + 1) for v in node)
    return False


def _split(resp: dict):
    """-> (instructions text or None, item description strings, item names)."""
    result = (resp or {}).get("result") if isinstance(resp, dict) else None
    if not isinstance(result, dict):
        return None, [], []
    instructions = result.get("instructions")
    if not isinstance(instructions, str):
        instructions = None
    texts, names = [], []
    for key in ("tools", "prompts", "resources"):
        for item in result.get(key) or []:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("name"), str):
                names.append(item["name"])
            _walk_strings({k: v for k, v in item.items()
                           if k not in _SKIP_ITEM_KEYS}, texts)
    return instructions, texts, names


def _injection(texts) -> bool:
    return any(p in t.lower() for t in texts for p in _PROMPT_INJECTION_PATTERNS)


def _chains_tools(texts, names) -> bool:
    """A description that tells the agent to call ANOTHER tool by name."""
    for t in texts:
        for n in names:
            if len(n) < 4:
                continue
            for m in re.finditer(r"\b" + re.escape(n) + r"\b", t):
                window = t[max(0, m.start() - 40):m.end() + 40]
                if _CHAIN_CUE_RE.search(window):
                    return True
    return False


def _anomalous(text: str) -> list:
    out = []
    if len(text) > INSTRUCTIONS_MAX_CHARS:
        out.append("instructions field exceeds the length bound")
    if _HIDDEN_RE.search(text):
        out.append("hidden or control characters in instructions field")
    if _BLOB_RE.search(text):
        out.append("encoded blob in instructions field")
    if _has_synthetic_hints([text]):
        out.append("instruction-like phrasing in instructions field")
    return out


def screen_discovery(method: str, resp, screener=None) -> dict:
    """Return {"verdict": "clean"|"flagged", "reasons", "poison_category",
    "taxonomy_ids", "details"}. Never raises on a malformed response."""
    clean = {"verdict": "clean", "reasons": [], "poison_category": "clean",
             "taxonomy_ids": [], "details": {"method": method}}
    if method not in DISCOVERY_METHODS or not isinstance(resp, dict):
        return clean
    instructions, texts, names = _split(resp)
    public = _find_cache_public(resp)
    details = {"method": method, "cache_scope_public": public,
               "instructions_len": len(instructions) if instructions else 0,
               "items": len(names)}
    reasons, ids, cats = [], set(), set()

    def hit(cat, reason, *entry_ids):
        cats.add(cat)
        reasons.append(reason)
        ids.update(entry_ids)

    if instructions:
        if _injection([instructions]):
            hit(POISON_PROMPT_INJECTION,
                "prompt-injection phrase in server instructions field",
                "mcp_2026_015_prompt_injection",
                *(["mcp_2026_008_015_chained_prompt_injection"] if public else []))
        if _EXFIL_RE.search(instructions):
            hit(POISON_PII_LEAK, "data-exfiltration instruction in server instructions field",
                "mcp_2026_015_pii_leak",
                *(["mcp_2026_008_015_chained_pii_leak"] if public else []))
        anomalies = _anomalous(instructions)
        for a in anomalies:
            hit(POISON_UNKNOWN_SYNTHETIC, a, "mcp_2026_015_unknown_synthetic")
    if _injection(texts):
        hit(POISON_PROMPT_INJECTION,
            f"prompt-injection phrase in {method} descriptions",
            *(["mcp_2026_008_prompt_injection"] if public else []))
    if any(_EXFIL_RE.search(t) for t in texts):
        hit(POISON_PII_LEAK, f"data-exfiltration instruction in {method} descriptions",
            *(["mcp_2026_008_015_chained_pii_leak"] if public else []))
    if _chains_tools(texts, names):
        hit(POISON_UNKNOWN_SYNTHETIC,
            f"{method} description directs the agent to call another tool",
            *(["mcp_2026_015_unknown_synthetic"] if instructions else []),
            *(["mcp_2026_008_unknown_synthetic"] if public else []))
    elif public and _has_synthetic_hints(texts):
        hit(POISON_UNKNOWN_SYNTHETIC,
            f"instruction-like phrasing in publicly cacheable {method} descriptions",
            "mcp_2026_008_unknown_synthetic")

    if screener is not None:
        try:
            blob = (([instructions] if instructions else []) + texts)
            urls = extract_indicators(blob).get("urls", [])[:MAX_URLS_CHECKED]
            if urls:
                v = screener.screen_indicators({"urls": urls})
                details["urls_checked"] = len(urls)
                if v.get("verdict") == "block":
                    hit(POISON_MALICIOUS_URL,
                        f"known-malicious URL in {method} response",
                        *(["mcp_2026_008_malicious_url"] if public else []))
        except Exception:
            details["url_check"] = "unavailable"  # fail open

    if not reasons:
        clean["details"] = details
        return clean
    return {"verdict": "flagged", "reasons": reasons,
            "poison_category": worst_category(cats),
            "taxonomy_ids": sorted(ids), "details": details}


def taxonomy_evidence(ids) -> list:
    """Evidence entries that make a verdict actionable: what the pattern is and
    what to do about it, from the shipped taxonomy snapshot."""
    out = []
    for i in ids:
        e = taxonomy.ENTRIES.get(i)
        if e:
            out.append({"type": "taxonomy", "id": i,
                        "detail": f"{e['disclosure']} {e['attack_pattern']}. "
                                  f"Mitigation: {e['mitigation']}"})
    return out
