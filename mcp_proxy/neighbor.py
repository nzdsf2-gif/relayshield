"""Neighbor MCP server identity and reputation tracking.

Tracks the reputation of upstream MCP servers so a poisoned server can
be flagged and quarantined without affecting other servers. Reputation
is keyed by server URL, so quarantine is always per-server.
"""

import logging
import time
import urllib.parse

log = logging.getLogger(__name__)

# Reputation levels.
CLEAN = "clean"
SUSPICIOUS = "suspicious"
QUARANTINED = "quarantined"


class ServerReputation:
    """Reputation record for one upstream MCP server."""

    def __init__(self, url: str):
        self.url = url
        parsed = urllib.parse.urlparse(url)
        self.domain = (parsed.netloc or parsed.path).lower()
        self.reputation = CLEAN
        self.flags = []  # list of {"ts", "reason", "evidence"}
        self.first_seen = time.time()
        self.last_flagged = None

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "domain": self.domain,
            "reputation": self.reputation,
            "flag_count": len(self.flags),
            "first_seen": self.first_seen,
            "last_flagged": self.last_flagged,
            "flags": self.flags[-10:],  # most recent 10
        }


class NeighborRegistry:
    """Registry of known upstream MCP servers and their reputations."""

    def __init__(self, screener=None):
        self._servers = {}
        self._screener = screener

    def register(self, url: str) -> ServerReputation:
        """Register a server; TI-screen its domain on first sight.

        Fail-open: if the TI check errors, the server stays clean and
        the failure is logged.
        """
        if url in self._servers:
            return self._servers[url]
        rep = ServerReputation(url)
        self._servers[url] = rep
        log.info("neighbor registered: %s (domain %s)", url, rep.domain)
        if self._screener is not None:
            try:
                indicators = {"urls": [url], "domains": [rep.domain],
                              "ips": []}
                verdict = self._screener.screen_indicators(indicators)
                if verdict.get("verdict") == "block":
                    self.flag(url, "upstream domain flagged by TI on "
                                   "registration",
                              verdict.get("reasons", []))
            except Exception as exc:
                log.warning("neighbor TI check failed for %s: %s", url, exc)
        return rep

    def flag(self, url: str, reason: str, evidence=None) -> ServerReputation:
        """Record a flag against a server. Escalates clean to suspicious."""
        rep = self._servers.get(url)
        if rep is None:
            rep = self.register(url)
        entry = {"ts": time.time(), "reason": reason,
                 "evidence": evidence or []}
        rep.flags.append(entry)
        rep.last_flagged = entry["ts"]
        if rep.reputation == CLEAN:
            rep.reputation = SUSPICIOUS
            log.warning("neighbor %s marked suspicious: %s", url, reason)
        return rep

    def get(self, url: str):
        return self._servers.get(url)

    def all(self) -> dict:
        return dict(self._servers)
