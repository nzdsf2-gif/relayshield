"""Durable kill-chain history and corpus-pivot registrations.

Two append-only JSONL stores backing the Phase 5 kill-chain layer:

- ChainHistoryStore: one record per scored session event (a flag or
  block verdict from the call-side or result-side hook), so chain
  scores can be compared historically per correlation identity over
  24h / 7d / 30d windows (GET /_rs/killchain reads through it).

- PivotRegistry: the registration interface for corpus pivoting.
  External endpoints and indicators observed in a scored chain are
  registered here. The default sink is a JSONL file beside the
  history store; a deployment (or the corpus side, later) can pass
  any callable sink to register() construction and each record is
  handed to it as well. The proxy package ships no TI-API client for
  pivots today, so the file is the seam: records are complete,
  self-describing, and replayable into whatever pivot consumer the
  corpus side builds.

Both mirror audit.py's persistence discipline: in-memory list plus
append-only JSONL when a path is configured, load-on-start, and
failures logged, never raised into the request path.
"""

import json
import logging
import threading
import time

log = logging.getLogger(__name__)

# Named comparison windows for the history view, in seconds.
WINDOW_SECONDS = {
    "24h": 86400.0,
    "7d": 604800.0,
    "30d": 2592000.0,
}
DEFAULT_WINDOW = "24h"


def parse_window(name):
    """Resolve a window name to (canonical_name, seconds).

    Unknown or empty names fall back to the default window; the
    canonical name is returned so callers can echo what was applied.
    """
    key = str(name or "").strip().lower()
    if key in WINDOW_SECONDS:
        return key, WINDOW_SECONDS[key]
    return DEFAULT_WINDOW, WINDOW_SECONDS[DEFAULT_WINDOW]


def _append_jsonl(path, record):
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as exc:
        log.error("kill-chain store: persist to %s failed: %s",
                  path, exc)


def _load_jsonl(path):
    records = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass  # No file yet; start empty.
    return records


class ChainHistoryStore:
    """Append-only history of kill-chain session scores.

    One record per non-allow sequence verdict. Each record carries
    the running peak score for its session key, so a window query
    can report per-session peaks without replaying the scorer.
    """

    def __init__(self, persist_path: str = ""):
        self._path = persist_path or ""
        self._lock = threading.Lock()
        self._records = []
        self._peak = {}  # session_key -> peak score seen so far
        if self._path:
            self._records = _load_jsonl(self._path)
            for rec in self._records:
                key = rec.get("session_key", "")
                peak = rec.get("peak_score", rec.get("score", 0.0))
                if peak > self._peak.get(key, 0.0):
                    self._peak[key] = peak
            if self._records:
                log.info("kill-chain history: loaded %d records from %s",
                         len(self._records), self._path)

    @property
    def persist_path(self):
        return self._path or None

    def record(self, identity: str, session_key: str,
               session_id: str = "", identity_source: str = "",
               server: str = "", tool: str = "", score: float = 0.0,
               stages: list = None, decision: str = "", chain: int = 1,
               source: str = "call", ts: float = None) -> dict:
        """Append one history record. Returns the record."""
        now = ts if ts is not None else time.time()
        score = round(float(score), 1)
        with self._lock:
            peak = max(score, self._peak.get(session_key, 0.0))
            self._peak[session_key] = peak
            record = {
                "ts": now,
                "identity": identity,
                "identity_source": identity_source,
                "session_key": session_key,
                "session_id": session_id,
                "server": server,
                "tool": tool,
                "score": score,
                "peak_score": peak,
                "stages": list(stages or []),
                "decision": decision,
                "chain": chain,
                "source": source,
            }
            self._records.append(record)
            if self._path:
                _append_jsonl(self._path, record)
            return dict(record)

    def query(self, identity: str = None, window: str = DEFAULT_WINDOW,
              now: float = None) -> dict:
        """Sessions scored inside a window, with simple aggregates.

        Sessions are grouped by session key: each entry reports the
        session's peak score in the window, its most recent record's
        detail, and how many scored events the window holds for it.
        Aggregates (count, max, mean) are over session peaks.
        """
        name, seconds = parse_window(window)
        now = now if now is not None else time.time()
        cutoff = now - seconds
        with self._lock:
            records = list(self._records)
        grouped = {}
        for rec in records:
            if rec.get("ts", 0.0) < cutoff:
                continue
            if identity is not None and rec.get("identity") != identity:
                continue
            key = rec.get("session_key", "")
            slot = grouped.get(key)
            if slot is None:
                slot = {
                    "session_key": key,
                    "identity": rec.get("identity", ""),
                    "identity_source": rec.get("identity_source", ""),
                    "session_id": rec.get("session_id", ""),
                    "server": rec.get("server", ""),
                    "peak_score": 0.0,
                    "last_score": 0.0,
                    "last_ts": 0.0,
                    "last_tool": "",
                    "last_decision": "",
                    "stages": [],
                    "chain": rec.get("chain", 1),
                    "events": 0,
                }
                grouped[key] = slot
            slot["events"] += 1
            slot["peak_score"] = max(slot["peak_score"],
                                    rec.get("peak_score",
                                            rec.get("score", 0.0)))
            if rec.get("ts", 0.0) >= slot["last_ts"]:
                slot["last_ts"] = rec.get("ts", 0.0)
                slot["last_score"] = rec.get("score", 0.0)
                slot["last_tool"] = rec.get("tool", "")
                slot["last_decision"] = rec.get("decision", "")
                slot["stages"] = list(rec.get("stages", []))
                slot["chain"] = rec.get("chain", slot["chain"])
                slot["server"] = rec.get("server", slot["server"])
                slot["session_id"] = rec.get("session_id",
                                             slot["session_id"])
        sessions = sorted(grouped.values(),
                          key=lambda s: s["last_ts"], reverse=True)
        peaks = [s["peak_score"] for s in sessions]
        return {
            "window": name,
            "window_s": seconds,
            "identity": identity,
            "count": len(sessions),
            "max_score": round(max(peaks), 1) if peaks else 0.0,
            "mean_score": (round(sum(peaks) / len(peaks), 1)
                           if peaks else 0.0),
            "sessions": sessions,
        }


class PivotRegistry:
    """Registration interface for corpus pivots from scored chains.

    register() is the seam: the proxy calls it whenever a scored
    chain (flag or block) observed external endpoints or indicators.
    Records persist to the JSONL sink beside the history store and
    are also handed to an optional callable sink, which is where a
    future corpus-side consumer (TI API client, queue producer)
    plugs in without touching the proxy's call path.
    """

    def __init__(self, persist_path: str = "", sink=None):
        self._path = persist_path or ""
        self._sink = sink
        self._lock = threading.Lock()
        self._records = (_load_jsonl(self._path) if self._path else [])

    @property
    def persist_path(self):
        return self._path or None

    def register(self, identity: str, session_key: str, server: str,
                 tool: str = "", source: str = "call",
                 indicators: dict = None, stages: list = None,
                 score: float = 0.0, ts: float = None) -> dict:
        """Register one pivot observation. Returns the record."""
        indicators = indicators or {}
        record = {
            "ts": ts if ts is not None else time.time(),
            "identity": identity,
            "session_key": session_key,
            "server": server,
            "tool": tool,
            "source": source,
            "score": round(float(score), 1),
            "stages": list(stages or []),
            "indicators": {
                "urls": list(indicators.get("urls", [])),
                "domains": list(indicators.get("domains", [])),
                "ips": list(indicators.get("ips", [])),
                "hosts": list(indicators.get("hosts", [])),
            },
        }
        with self._lock:
            self._records.append(record)
            if self._path:
                _append_jsonl(self._path, record)
        if self._sink is not None:
            try:
                self._sink(dict(record))
            except Exception as exc:  # a sink must never break the proxy
                log.error("kill-chain pivot sink error: %s", exc)
        return dict(record)

    def registrations(self) -> list:
        with self._lock:
            return [dict(r) for r in self._records]
