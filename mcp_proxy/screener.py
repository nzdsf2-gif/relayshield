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
                 block_levels: set = None):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.block_levels = block_levels or {"high", "medium"}

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

    def screen_tool_call(self, tool_name: str, arguments: dict) -> dict:
        """Full screening for a tools/call invocation."""
        indicators = extract_indicators(arguments)
        verdict = self.screen_indicators(indicators)
        verdict["tool_name"] = tool_name
        return verdict


def _level_rank(level: str) -> int:
    return {"unknown": 0, "medium": 1, "high": 2}.get(level, 0)
