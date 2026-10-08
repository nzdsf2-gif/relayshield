"""TI screening for MCP tool call parameters.

Extracts URLs, domains, and IPs from arbitrary tool arguments and
screens them against RelayShield's threat intelligence via the
keyless composite-check API.
"""

import json
import logging
import re
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

# Regexes for indicator extraction.
_URL_RE = re.compile(
    r"https?://[^\s\"'<>`]+", re.IGNORECASE
)
_DOMAIN_RE = re.compile(
    r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"[a-zA-Z]{2,}\b"
)
_IPV4_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)

# Skip obvious non-indicators.
_SKIP_DOMAINS = {
    "localhost", "example.com", "example.org", "example.net",
}

# Scam-kit fingerprint IDs embedded in tool results. A poisoned MCP
# server serving kit-identified content is strong evidence of compromise.
_KIT_ID_RE = re.compile(r"\bkit_[0-9a-f]{64}\b", re.IGNORECASE)

# Prompt-injection phrases commonly found in poisoned tool results.
# Matched case-insensitively against result text.
_PROMPT_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all previous instructions",
    "disregard previous instructions",
    "disregard all prior instructions",
    "override your instructions",
    "do not follow your instructions",
    "you are now ",
    "new system prompt",
    "[system]",
    "bypass your safety",
    "forget your instructions",
]

# Secret material that should never appear in a tool result; its
# presence suggests exfiltration or a poisoned payload.
_SECRET_PATTERNS = [
    "-----BEGIN PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
]


def extract_indicators(obj, _depth=0, _seen=None) -> dict:
    """Recursively extract URLs, domains, and IPs from tool arguments.

    Returns {"urls": [...], "domains": [...], "ips": [...]} with
    deduplicated values.
    """
    if _seen is None:
        _seen = set()
    urls, domains, ips = set(), set(), set()

    def _walk(node, depth):
        if depth > 10 or id(node) in _seen:
            return
        if isinstance(node, (dict, list)):
            _seen.add(id(node))
        if isinstance(node, str):
            for m in _URL_RE.finditer(node):
                urls.add(m.group(0).rstrip(".,;:!?)"))
            for m in _DOMAIN_RE.finditer(node):
                d = m.group(0).lower()
                if d not in _SKIP_DOMAINS:
                    domains.add(d)
            for m in _IPV4_RE.finditer(node):
                ips.add(m.group(0))
        elif isinstance(node, dict):
            for v in node.values():
                _walk(v, depth + 1)
        elif isinstance(node, (list, tuple)):
            for v in node:
                _walk(v, depth + 1)

    _walk(obj, _depth)
    # Domains already covered by URLs are redundant; keep both anyway,
    # the API handles either.
    return {
        "urls": sorted(urls),
        "domains": sorted(domains),
        "ips": sorted(ips),
    }


def _post_json(url: str, payload: dict, timeout: float, api_key: str = "") -> dict:
    """POST JSON and return the parsed response body."""
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-RS-API-KEY"] = api_key
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


class Screener:
    """Screens tool call arguments against RelayShield TI."""

    def __init__(self, api_base: str, api_key: str = "", timeout: float = 5.0,
                 block_levels: set = None, kit_lookup_enabled: bool = False):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.block_levels = block_levels or {"high", "medium"}
        # When True, kit_<sha256> IDs found in results are enriched via
        # the /v1/payg/scamkit-match API.
        self.kit_lookup_enabled = kit_lookup_enabled

    def screen_indicators(self, indicators: dict) -> dict:
        """Screen extracted indicators. Returns a verdict dict.

        Verdict: {"verdict": "allow"|"block"|"unknown",
                  "level": str, "score": int, "reasons": [...],
                  "screened": {...}}
        """
        urls = indicators.get("urls", [])
        if not urls:
            # Nothing URL-shaped to check; allow.
            return {
                "verdict": "allow",
                "level": "unknown",
                "score": 0,
                "reasons": ["no screenable indicators in tool arguments"],
                "screened": indicators,
            }

        # Check each URL via composite-check (keyless). Take the worst.
        worst = {"level": "unknown", "score": 0, "reasons": []}
        checked = 0
        errors = 0
        for url in urls[:10]:  # cap per-call fan-out
            try:
                result = self._check_url(url)
                checked += 1
            except Exception as exc:
                errors += 1
                log.warning("screening failed for %s: %s", url, exc)
                continue
            if _level_rank(result["level"]) > _level_rank(worst["level"]):
                worst = result

        if checked == 0:
            # All screening calls failed: fail open, but say so.
            return {
                "verdict": "allow",
                "level": "unknown",
                "score": 0,
                "reasons": [f"TI screening unavailable ({errors} errors); allowed"],
                "screened": indicators,
            }

        verdict = "block" if worst["level"] in self.block_levels else "allow"
        worst["verdict"] = verdict
        worst["screened"] = indicators
        return worst

    def _check_url(self, url: str) -> dict:
        """Single URL check via the composite-check API."""
        body = _post_json(
            f"{self.api_base}/v1/composite-check",
            {"url": url},
            timeout=self.timeout,
            api_key=self.api_key,
        )
        data = body.get("data", body)
        level = str(data.get("level", "unknown")).lower()
        score = int(data.get("score", 0))
        reasons = []
        for sig in data.get("signals", []):
            for r in sig.get("reasons", []):
                reasons.append(str(r))
        if not reasons:
            reasons = [f"composite-check level={level} score={score}"]
        return {"level": level, "score": score, "reasons": reasons}

    def _lookup_kit(self, kit_id: str) -> dict:
        """Look up a kit fingerprint via the scamkit-match API.

        Returns {"kit_id": ..., "family": ..., "verdict": ...} or None
        when the kit is unknown.
        """
        body = _post_json(
            f"{self.api_base}/v1/payg/scamkit-match",
            {"kit_id": kit_id},
            timeout=self.timeout,
            api_key=self.api_key,
        )
        data = body.get("data", body)
        if not data or data.get("verdict") == "no-match":
            return None
        return {
            "kit_id": kit_id,
            "family": data.get("family", "unknown"),
            "verdict": data.get("verdict", "unknown"),
            "confidence": data.get("confidence", 0),
        }

    def screen_tool_call(self, tool_name: str, arguments: dict) -> dict:
        """Full screening for a tools/call invocation."""
        indicators = extract_indicators(arguments)
        verdict = self.screen_indicators(indicators)
        verdict["tool_name"] = tool_name
        return verdict

    def screen_tool_result(self, result_obj) -> dict:
        """Screen an upstream tools/call result for poisoned content.

        Checks result text for prompt-injection phrases, embedded
        malicious URLs (via TI), leaked secret material, and known
        scam-kit fingerprint IDs.

        Returns {"verdict": "clean"|"flagged", "reasons": [...],
                 "details": {...}, "kit_ids": [...]}.
        """
        texts = _extract_result_text(result_obj)
        reasons = []
        details = {"text_chunks": len(texts)}
        kit_ids = []

        # 1. Prompt-injection heuristics.
        for text in texts:
            lowered = text.lower()
            for pattern in _PROMPT_INJECTION_PATTERNS:
                if pattern in lowered:
                    reasons.append(
                        f"prompt-injection phrase in tool result: "
                        f"'{pattern}'"
                    )
                    break

        # 2. Secret material in results.
        for text in texts:
            for pattern in _SECRET_PATTERNS:
                if pattern in text:
                    reasons.append(
                        "secret material in tool result "
                        f"({pattern.strip('-')[:24].strip()}...)"
                    )
                    break

        # 3. Malicious URLs embedded in result text.
        indicators = extract_indicators({"texts": texts})
        urls = indicators.get("urls", [])
        details["urls_found"] = len(urls)
        worst = None
        for url in urls[:10]:
            try:
                check = self._check_url(url)
            except Exception as exc:
                log.warning("result URL screening failed for %s: %s",
                            url, exc)
                continue
            if _level_rank(check["level"]) > _level_rank(
                    worst["level"] if worst else "unknown"):
                worst = check
        if worst and worst["level"] in self.block_levels:
            reasons.append(
                f"malicious URL in tool result: level={worst['level']} "
                f"score={worst['score']}"
            )
            details["url_reasons"] = worst["reasons"]

        # 4. Scam-kit fingerprint IDs. A kit_<sha256> in a tool result
        # ties the content to a known phishing kit family.
        seen_kits = set()
        for text in texts:
            for m in _KIT_ID_RE.finditer(text):
                kit_id = m.group(0).lower()
                if kit_id not in seen_kits:
                    seen_kits.add(kit_id)
                    kit_ids.append(kit_id)
        if kit_ids:
            reasons.append(
                f"scam-kit fingerprint(s) in tool result: "
                f"{', '.join(kit_ids[:3])}"
                + ("..." if len(kit_ids) > 3 else "")
            )
            details["kit_ids"] = kit_ids

        # 5. Kit fingerprint lookup via scamkit-match API (if configured).
        # Enriches kit_ids with family/verdict from the TI corpus.
        kit_evidence = []
        if kit_ids and getattr(self, "kit_lookup_enabled", False):
            for kit_id in kit_ids[:5]:
                try:
                    match = self._lookup_kit(kit_id)
                    if match:
                        kit_evidence.append(match)
                except Exception as exc:
                    log.warning("kit lookup failed for %s: %s", kit_id, exc)
        if kit_evidence:
            details["kit_evidence"] = kit_evidence

        return {
            "verdict": "flagged" if reasons else "clean",
            "reasons": reasons,
            "details": details,
            "kit_ids": kit_ids,
        }


def _level_rank(level: str) -> int:
    return {"unknown": 0, "medium": 1, "high": 2}.get(level, 0)


def _extract_result_text(result_obj) -> list:
    """Pull text chunks out of an MCP tools/call result object.

    Handles {"result": {"content": [{"type": "text", "text": ...}]}},
    plain {"content": [...]}, and raw strings. Cycle-safe.
    """
    texts = []
    seen = set()

    def _walk(node, depth):
        if depth > 10 or id(node) in seen:
            return
        if isinstance(node, (dict, list)):
            seen.add(id(node))
        if isinstance(node, str):
            if node.strip():
                texts.append(node)
        elif isinstance(node, dict):
            # MCP content blocks carry the text directly.
            if node.get("type") == "text" and isinstance(node.get("text"),
                                                         str):
                texts.append(node["text"])
            else:
                for v in node.values():
                    _walk(v, depth + 1)
        elif isinstance(node, (list, tuple)):
            for v in node:
                _walk(v, depth + 1)

    _walk(result_obj, 0)
    return texts
