"""Server reputation graph for the MCP Proxy Firewall.

Maintains per-server reputation scores (0-100, higher is more
trustworthy) computed from observed behavior: TI hits, quarantine
events, behavioral anomaly scores, and uptime. Scores feed a graph
API for the dashboard and can warn operators before quarantine.

This is the local half of the reputation story. The product plan
describes a cross-deployment reputation graph fed by anonymized
telemetry; that network layer is future work. This module keeps the
per-deployment scores and history that the network layer will
aggregate.
"""

import logging
import time
import urllib.parse

log = logging.getLogger(__name__)

# Score bounds and starting point.
_SCORE_MAX = 100.0
_SCORE_MIN = 0.0
_SCORE_START = 80.0  # new servers start trusted-but-unproven

# Score deltas per event type.
_DELTA_TI_HIT = -25.0
_DELTA_FLAG = -10.0
_DELTA_QUARANTINE = -40.0
_DELTA_QUARANTINE_CLEARED = +15.0
_DELTA_BEHAVIOR_ANOMALY = -5.0
_DELTA_ATTACK_CHAIN = -20.0
_DELTA_CLEAN_HOUR = +1.0   # slow recovery for uneventful hours

# History retention: keep this many score samples per server.
_HISTORY_MAX = 200

# Reputation bands for display.
BAND_TRUSTED = "trusted"        # score >= 70
BAND_WATCH = "watch"            # 40 <= score < 70
BAND_UNTRUSTED = "untrusted"    # score < 40


def band_for(score: float) -> str:
    if score >= 70.0:
        return BAND_TRUSTED
    if score >= 40.0:
        return BAND_WATCH
    return BAND_UNTRUSTED


class ServerScore:
    """Reputation record for one MCP server."""

    def __init__(self, url: str):
        self.url = url
        parsed = urllib.parse.urlparse(url)
        self.domain = (parsed.netloc or parsed.path).lower()
        self.score = _SCORE_START
        self.first_seen = time.time()
        self.last_event = self.first_seen
        self.event_counts = {
            "ti_hit": 0,
            "flag": 0,
            "quarantine": 0,
            "behavior_anomaly": 0,
            "attack_chain": 0,
            "clean_calls": 0,
        }
        # History of (ts, score) for the graph.
        self.history = [(self.first_seen, _SCORE_START)]

    def _apply(self, delta: float, event: str, detail: str = ""):
        old = self.score
        self.score = max(_SCORE_MIN, min(_SCORE_MAX, self.score + delta))
        self.last_event = time.time()
        self.history.append((self.last_event, self.score))
        if len(self.history) > _HISTORY_MAX:
            self.history = self.history[-_HISTORY_MAX:]
        log.info("reputation: %s %s %.1f -> %.1f (%s)",
                 self.url, event, old, self.score, detail or event)

    def ti_hit(self, detail: str = ""):
        self.event_counts["ti_hit"] += 1
        self._apply(_DELTA_TI_HIT, "ti_hit", detail)

    def flag(self, detail: str = ""):
        self.event_counts["flag"] += 1
        self._apply(_DELTA_FLAG, "flag", detail)

    def quarantined(self, detail: str = ""):
        self.event_counts["quarantine"] += 1
        self._apply(_DELTA_QUARANTINE, "quarantined", detail)

    def quarantine_cleared(self, detail: str = ""):
        self._apply(_DELTA_QUARANTINE_CLEARED, "quarantine_cleared",
                     detail)

    def behavior_anomaly(self, detail: str = ""):
        self.event_counts["behavior_anomaly"] += 1
        self._apply(_DELTA_BEHAVIOR_ANOMALY, "behavior_anomaly", detail)

    def attack_chain(self, detail: str = ""):
        self.event_counts["attack_chain"] += 1
        self._apply(_DELTA_ATTACK_CHAIN, "attack_chain", detail)

    def clean_call(self):
        """A screened-clean call. Counts toward slow recovery."""
        self.event_counts["clean_calls"] += 1
        # Recovery is throttled: at most one recovery point per hour
        # of event-free operation.
        if time.time() - self.last_event >= 3600.0:
            self._apply(_DELTA_CLEAN_HOUR, "clean_hour")

    def to_dict(self, include_history: bool = True) -> dict:
        d = {
            "url": self.url,
            "domain": self.domain,
            "score": round(self.score, 1),
            "band": band_for(self.score),
            "first_seen": self.first_seen,
            "last_event": self.last_event,
            "event_counts": dict(self.event_counts),
        }
        if include_history:
            d["history"] = [
                {"ts": ts, "score": round(s, 1)}
                for ts, s in self.history
            ]
        return d


class ReputationStore:
    """Registry of per-server reputation scores.

    Feeds the GET /_rs/reputation admin endpoint and the dashboard
    reputation graph. Threading: the proxy is single-threaded
    (BaseHTTPRequestHandler), so no locks are needed.
    """

    def __init__(self):
        self._servers = {}

    def get_or_create(self, url: str) -> ServerScore:
        if url not in self._servers:
            self._servers[url] = ServerScore(url)
            log.info("reputation: tracking new server %s", url)
        return self._servers[url]

    def get(self, url: str):
        return self._servers.get(url)

    def all(self) -> dict:
        return dict(self._servers)

    def summary(self) -> dict:
        """Compact summary for the admin endpoint."""
        servers = [s.to_dict() for s in self._servers.values()]
        servers.sort(key=lambda s: s["score"])
        return {
            "servers": servers,
            "counts": {
                "total": len(servers),
                "trusted": sum(1 for s in servers
                               if s["band"] == BAND_TRUSTED),
                "watch": sum(1 for s in servers
                             if s["band"] == BAND_WATCH),
                "untrusted": sum(1 for s in servers
                                 if s["band"] == BAND_UNTRUSTED),
            },
        }

    def record_ti_hit(self, url: str, detail: str = ""):
        self.get_or_create(url).ti_hit(detail)

    def record_flag(self, url: str, detail: str = ""):
        self.get_or_create(url).flag(detail)

    def record_quarantine(self, url: str, detail: str = ""):
        self.get_or_create(url).quarantined(detail)

    def record_quarantine_cleared(self, url: str, detail: str = ""):
        self.get_or_create(url).quarantine_cleared(detail)

    def record_behavior_anomaly(self, url: str, detail: str = ""):
        self.get_or_create(url).behavior_anomaly(detail)

    def record_attack_chain(self, url: str, detail: str = ""):
        self.get_or_create(url).attack_chain(detail)

    def record_clean_call(self, url: str):
        self.get_or_create(url).clean_call()
