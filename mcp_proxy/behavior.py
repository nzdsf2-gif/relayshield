"""Behavioral baselining for the MCP Proxy Firewall.

Learns normal tool call patterns per agent and flags deviations.
Detects cross-tool attack chains and maintains per-session risk scores.

Components:
- AgentProfile: per-agent tool call baselines (frequency, sequences,
  time-of-day patterns)
- BehaviorTracker: manages profiles and runs anomaly detection
- AttackChainDetector: matches known malicious tool sequences
- RiskScorer: 0-100 per-session risk score with time decay

All state is in-memory. No external dependencies.
"""

import logging
import math
import time

log = logging.getLogger(__name__)

# New poison categories for behavioral findings.
POISON_BEHAVIORAL_ANOMALY = "behavioral_anomaly"
POISON_ATTACK_CHAIN = "attack_chain"

# Known malicious tool sequences. Each chain is a list of tool-name
# patterns (substring match, case-insensitive) that must appear in
# order within the chain window.
_ATTACK_CHAINS = [
    {
        "name": "data_exfiltration",
        "description": "file read followed by network send followed by "
                       "email dispatch: classic data exfiltration chain",
        "patterns": ["read", "fetch", "get"],
        "then": ["http", "request", "post", "upload", "send"],
        "then2": ["mail", "email", "smtp", "notify"],
    },
    {
        "name": "lateral_movement",
        "description": "rapid tool calls across different servers: "
                       "lateral movement probe",
        "patterns": ["__lateral__"],  # special: handled by server counting
    },
    {
        "name": "privilege_escalation",
        "description": "injection-flagged response followed by a "
                       "privileged tool call: escalation attempt",
        "patterns": ["__injection_then_privileged__"],  # special case
    },
]

# Tools considered privileged for the escalation chain.
_PRIVILEGED_TOOL_HINTS = [
    "exec", "shell", "run_command", "run", "eval", "system",
    "delete", "drop", "admin", "sudo", "root", "grant",
]

# Chain detection window in seconds.
_CHAIN_WINDOW_S = 120.0

# Volume anomaly: flag when the short-window rate exceeds this multiple
# of the baseline rate.
_VOLUME_MULTIPLIER = 10.0

# Minimum calls before baselining is considered stable enough to flag
# anomalies (avoids false positives on brand-new agents).
_MIN_BASELINE_CALLS = 20

# Session risk decay: risk halves every this many seconds of quiet.
_RISK_HALF_LIFE_S = 600.0


def _hour_of_day(ts: float) -> int:
    """Hour of day (0-23) in local time for a timestamp."""
    return time.localtime(ts).tm_hour


class AgentProfile:
    """Baseline of normal behavior for one agent.

    Tracks tool frequencies, tool bigrams (consecutive pairs),
    hourly call distribution, and short-window call timestamps for
    rate computation.
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.total_calls = 0
        self.tool_counts = {}          # tool_name -> count
        self.bigram_counts = {}        # (prev_tool, tool) -> count
        self.hour_counts = [0] * 24    # calls per hour of day
        self.call_times = []           # recent timestamps (bounded)
        self.first_seen = time.time()
        self.last_tool = None

    def record(self, tool_name: str, ts: float = None):
        """Record one tool call into the baseline."""
        ts = ts if ts is not None else time.time()
        tool = tool_name.lower()
        if self.total_calls == 0:
            # Anchor the baseline window to the first observed event,
            # not to wall-clock construction time, so backfilled or
            # replayed timestamps produce sane rates.
            self.first_seen = ts
        self.total_calls += 1
        self.tool_counts[tool] = self.tool_counts.get(tool, 0) + 1
        if self.last_tool is not None:
            bigram = (self.last_tool, tool)
            self.bigram_counts[bigram] = self.bigram_counts.get(bigram, 0) + 1
        self.last_tool = tool
        self.hour_counts[_hour_of_day(ts)] += 1
        self.call_times.append(ts)
        # Bound memory: keep the last 500 timestamps.
        if len(self.call_times) > 500:
            self.call_times = self.call_times[-500:]

    def baseline_ready(self) -> bool:
        """True when enough history exists to judge anomalies."""
        return self.total_calls >= _MIN_BASELINE_CALLS

    def rate_per_minute(self, window_s: float = 60.0,
                        now: float = None) -> float:
        """Call rate over the trailing window."""
        now = now if now is not None else time.time()
        cutoff = now - window_s
        recent = [t for t in self.call_times if t >= cutoff]
        return len(recent) / (window_s / 60.0)

    def baseline_rate_per_minute(self) -> float:
        """Long-run average rate since first sight."""
        elapsed_min = max((time.time() - self.first_seen) / 60.0, 1.0)
        return self.total_calls / elapsed_min

    def is_unusual_hour(self, ts: float = None) -> bool:
        """True if this hour is far below the agent's normal hours."""
        if not self.baseline_ready():
            return False
        ts = ts if ts is not None else time.time()
        hour = _hour_of_day(ts)
        total = sum(self.hour_counts)
        if total == 0:
            return False
        # Flag if this hour holds less than 2% of historical calls.
        return (self.hour_counts[hour] / total) < 0.02

    def is_novel_sequence(self, tool_name: str) -> bool:
        """True if this tool never followed the previous tool before."""
        if not self.baseline_ready() or self.last_tool is None:
            return False
        tool = tool_name.lower()
        return (self.last_tool, tool) not in self.bigram_counts

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "total_calls": self.total_calls,
            "top_tools": sorted(self.tool_counts.items(),
                                key=lambda kv: kv[1], reverse=True)[:10],
            "baseline_ready": self.baseline_ready(),
            "baseline_rate_per_min": round(self.baseline_rate_per_minute(), 2),
            "first_seen": self.first_seen,
        }


class AttackChainDetector:
    """Matches known malicious tool sequences within a time window.

    Keeps a per-agent event log of (ts, tool_name, server_url,
    flagged_injection) and checks each new event against chain
    definitions.
    """

    def __init__(self, window_s: float = _CHAIN_WINDOW_S):
        self.window_s = window_s
        self._events = {}  # agent_id -> list of event dicts

    def _prune(self, agent_id: str, now: float):
        events = self._events.get(agent_id, [])
        cutoff = now - self.window_s
        self._events[agent_id] = [e for e in events if e["ts"] >= cutoff]

    def record(self, agent_id: str, tool_name: str, server_url: str = "",
               had_injection: bool = False, ts: float = None) -> list:
        """Record an event; return list of matched chain dicts."""
        now = ts if ts is not None else time.time()
        self._prune(agent_id, now)
        event = {"ts": now, "tool": tool_name.lower(),
                 "server": server_url, "had_injection": had_injection}
        self._events.setdefault(agent_id, []).append(event)
        return self._check_chains(agent_id, event)

    @staticmethod
    def _matches_any(tool: str, hints: list) -> bool:
        return any(h in tool for h in hints)

    def _check_chains(self, agent_id: str, event: dict) -> list:
        matched = []
        events = self._events.get(agent_id, [])
        tools = [e["tool"] for e in events]

        for chain in _ATTACK_CHAINS:
            name = chain["name"]
            if name == "data_exfiltration":
                if self._check_exfiltration(tools, chain):
                    matched.append(chain)
            elif name == "lateral_movement":
                if self._check_lateral(events):
                    matched.append(chain)
            elif name == "privilege_escalation":
                if self._check_escalation(events, chain):
                    matched.append(chain)
        return matched

    def _check_exfiltration(self, tools: list, chain: dict) -> bool:
        """read-like, then network-like, then mail-like, in order."""
        stage = 0
        for tool in tools:
            if stage == 0 and self._matches_any(tool, chain["patterns"]):
                stage = 1
            elif stage == 1 and self._matches_any(tool, chain["then"]):
                stage = 2
            elif stage == 2 and self._matches_any(tool, chain["then2"]):
                return True
        return False

    def _check_lateral(self, events: list) -> bool:
        """Five or more distinct servers touched in the window."""
        servers = {e["server"] for e in events if e["server"]}
        return len(servers) >= 5

    def _check_escalation(self, events: list, chain: dict) -> bool:
        """An injection-flagged event followed by a privileged tool."""
        seen_injection = False
        for e in events:
            if e["had_injection"]:
                seen_injection = True
            elif seen_injection and self._matches_any(
                    e["tool"], _PRIVILEGED_TOOL_HINTS):
                return True
        return False


class RiskScorer:
    """Per-session risk score, 0-100, with time decay.

    Findings add risk; quiet periods decay it. Scores above the
    quarantine threshold can trigger quarantine evaluation.
    """

    def __init__(self, half_life_s: float = _RISK_HALF_LIFE_S):
        self.half_life_s = half_life_s
        self._scores = {}  # agent_id -> {"score": float, "updated": ts}

    def add(self, agent_id: str, points: float, reason: str = "") -> float:
        """Add risk points; returns the new decayed score."""
        now = time.time()
        entry = self._scores.get(agent_id, {"score": 0.0, "updated": now})
        decayed = self._decay(entry["score"], now - entry["updated"])
        new_score = min(100.0, decayed + points)
        self._scores[agent_id] = {"score": new_score, "updated": now}
        log.info("behavior risk: agent=%s +%s (%s) -> %.1f",
                 agent_id, points, reason, new_score)
        return new_score

    def get(self, agent_id: str) -> float:
        """Current decayed score for an agent."""
        now = time.time()
        entry = self._scores.get(agent_id)
        if entry is None:
            return 0.0
        return self._decay(entry["score"], now - entry["updated"])

    def _decay(self, score: float, elapsed_s: float) -> float:
        if elapsed_s <= 0 or score <= 0:
            return score
        return score * (0.5 ** (elapsed_s / self.half_life_s))

    def reset(self, agent_id: str):
        self._scores.pop(agent_id, None)


class BehaviorTracker:
    """Top-level behavioral screening for the proxy.

    Usage in the proxy's tools/call path:
        result = tracker.check(agent_id, tool_name, arguments,
                               server_url=upstream_url)
    result is a dict with keys: verdict ("allow"|"flag"),
    poison_category, reasons, risk_score.
    """

    # Risk points per finding type.
    _RISK_VOLUME = 25.0
    _RISK_SEQUENCE = 10.0
    _RISK_HOUR = 10.0
    _RISK_CHAIN = 40.0

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._profiles = {}  # agent_id -> AgentProfile
        self._chains = AttackChainDetector()
        self._risk = RiskScorer()

    def profile_for(self, agent_id: str) -> AgentProfile:
        if agent_id not in self._profiles:
            self._profiles[agent_id] = AgentProfile(agent_id)
        return self._profiles[agent_id]

    def risk_score(self, agent_id: str) -> float:
        return self._risk.get(agent_id)

    def check(self, agent_id: str, tool_name: str, arguments: dict = None,
              server_url: str = "", had_injection: bool = False,
              ts: float = None) -> dict:
        """Screen one tool call for behavioral anomalies.

        Returns {"verdict": "allow"|"flag",
                 "poison_category": str, "reasons": [...],
                 "risk_score": float, "anomalies": [...]}.
        The baseline is updated for every call, including flagged ones,
        so the profile keeps learning.
        """
        ts = ts if ts is not None else time.time()
        result = {
            "verdict": "allow",
            "poison_category": "clean",
            "reasons": [],
            "risk_score": self._risk.get(agent_id),
            "anomalies": [],
        }
        if not self.enabled:
            return result

        profile = self.profile_for(agent_id)

        # Anomaly checks run against the baseline BEFORE this call is
        # recorded, so a first-seen tool is genuinely novel.
        anomalies = []
        if profile.baseline_ready():
            current_rate = profile.rate_per_minute(now=ts)
            baseline_rate = profile.baseline_rate_per_minute()
            if (baseline_rate > 0
                    and current_rate > baseline_rate * _VOLUME_MULTIPLIER):
                anomalies.append(
                    f"volume anomaly: {current_rate:.1f} calls/min vs "
                    f"baseline {baseline_rate:.1f} calls/min "
                    f"({_VOLUME_MULTIPLIER:.0f}x threshold)")
            if profile.is_novel_sequence(tool_name):
                anomalies.append(
                    f"sequence anomaly: '{tool_name}' never followed "
                    f"'{profile.last_tool}' before")
            if profile.is_unusual_hour(ts):
                anomalies.append(
                    f"time anomaly: call at hour "
                    f"{_hour_of_day(ts):02d}:00, outside agent's normal "
                    f"hours")

        # Attack-chain detection uses the event stream.
        chains = self._chains.record(
            agent_id, tool_name, server_url=server_url,
            had_injection=had_injection, ts=ts)

        # Record this call into the baseline.
        profile.record(tool_name, ts)

        # Score and classify.
        reasons = []
        categories = set()
        if anomalies:
            reasons.extend(anomalies)
            categories.add(POISON_BEHAVIORAL_ANOMALY)
            for a in anomalies:
                if a.startswith("volume"):
                    self._risk.add(agent_id, self._RISK_VOLUME, "volume")
                elif a.startswith("sequence"):
                    self._risk.add(agent_id, self._RISK_SEQUENCE,
                                   "sequence")
                else:
                    self._risk.add(agent_id, self._RISK_HOUR, "hour")
        for chain in chains:
            reasons.append(
                f"attack_chain: {chain['name']}: {chain['description']}")
            categories.add(POISON_ATTACK_CHAIN)
            self._risk.add(agent_id, self._RISK_CHAIN, chain["name"])

        result["anomalies"] = anomalies
        result["risk_score"] = self._risk.get(agent_id)
        if reasons:
            result["verdict"] = "flag"
            # Attack chains outrank plain anomalies.
            result["poison_category"] = (
                POISON_ATTACK_CHAIN if POISON_ATTACK_CHAIN in categories
                else POISON_BEHAVIORAL_ANOMALY)
            result["reasons"] = reasons
        return result

    def profiles(self) -> dict:
        """All agent profiles as dicts (for admin endpoints)."""
        return {aid: p.to_dict() for aid, p in self._profiles.items()}
