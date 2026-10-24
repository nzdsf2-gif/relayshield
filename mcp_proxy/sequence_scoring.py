"""Kill-chain sequence scoring for the MCP Proxy Firewall.

Per-call screening (screener.py) judges each tool call in isolation,
and behavior.py's AttackChainDetector matches a few fixed tool-name
sequences. Neither answers the question this module answers: is this
*session* walking an attack progression, one individually-plausible
call at a time?

    recon -> sensitive access -> encode / stage -> exfiltrate

Each stage alone is a call an agent might legitimately make. The
sequence is the signal. This module tracks the ordered tool calls per
session, classifies each call into a kill-chain stage, and raises a
session risk score as the chain progresses *in order*. Out-of-order
or skipped-stage activity earns only partial ("gap") credit: it is
noted, but a chain with a missing link is weaker evidence than a
chain that walks every step. Scores decay with a half-life and stage
progress expires after a window, so a benign session that happens to
touch one stage never accumulates risk forever.

Verdict shape mirrors BehaviorTracker.check: a dict with verdict
("allow"|"flag"|"block"), poison_category, reasons, risk_score, plus
a "sequence" detail block and confidence "signals" in the shape
confidence.score_verdict consumes. The signal code is KILL_CHAIN,
the dedicated cause code for sequence-scored chains (registered in
confidence.CAUSE_CODES, risk-scaled by the session score);
ATTACK_CHAIN remains the code for attack-chain matches from the
behavior and threat-intel layers.

All state is in-memory, keyed by an opaque session key. No external
dependencies. Deterministic: classification uses no DNS and no
network, so the same call sequence always produces the same score.
"""

import ipaddress
import json
import logging
import re
import socket
import time
from collections import OrderedDict

log = logging.getLogger(__name__)

# Poison category for sequence-scoring findings. Registered with a
# first-class rank in screener._CATEGORY_RANK and its own cause code
# (KILL_CHAIN) in confidence.CATEGORY_CAUSE_CODES.
POISON_KILL_CHAIN = "kill_chain"

# Kill-chain stages, in progression order.
STAGE_RECON = "recon"
STAGE_ACCESS = "access"
STAGE_STAGING = "staging"
STAGE_EXFIL = "exfil"
STAGE_ORDER = (STAGE_RECON, STAGE_ACCESS, STAGE_STAGING, STAGE_EXFIL)

STAGE_LABELS = {
    STAGE_RECON: "recon (discovery and enumeration)",
    STAGE_ACCESS: "access (sensitive read)",
    STAGE_STAGING: "staging (encode, compress, or write-out)",
    STAGE_EXFIL: "exfiltration (external endpoint)",
}

# ---------------------------------------------------------------------------
# Stage classification hints.
#
# Tool-name hints are substring matches, case-insensitive, in the same
# style as behavior.py's chain patterns. Argument signals matter as
# much as tool names: ACCESS requires a sensitivity marker (a bare
# read of an ordinary file is benign), and EXFIL requires evidence of
# an external endpoint (a bare "send" to an internal service is not
# exfiltration).
# ---------------------------------------------------------------------------

_RECON_TOOL_HINTS = [
    "list", "ls", "dir", "find", "search", "scan", "enum",
    "discover", "inventory", "whoami", "describe", "tree", "browse",
]

# Tool names that are themselves about sensitive material: calling
# one is an ACCESS-stage event regardless of arguments.
_ACCESS_TOOL_HINTS = [
    "credential", "secret", "token", "password", "passwd", "vault",
    "ssh_key", "private_key", "keychain", "env_var", "getenv",
    "cookie", "session_token", "auth_token",
]

# Markers in argument values that make a read ACCESS-stage: paths or
# content pointing at credential stores and sensitive config.
_SENSITIVE_ARG_MARKERS = [
    ".ssh", ".aws", ".gnupg", ".kube", ".docker", ".env",
    "credentials", "credential", "secrets", "secret", "id_rsa",
    "id_dsa", "id_ecdsa", "id_ed25519", ".pem", "private_key",
    "password", "passwd", "token", "shadow", "netrc", "cookie",
    ".git-credentials", "kubeconfig", "authorized_keys",
]

# Generic read verbs: an ACCESS event only when a sensitive marker
# is also present in the arguments or the tool name.
_READ_TOOL_HINTS = [
    "read", "get", "fetch", "cat", "open", "download", "view",
    "show", "load", "dump", "export",
]

_STAGING_TOOL_HINTS = [
    "base64", "encode", "decode", "compress", "zip", "tar", "gzip",
    "encrypt", "obfuscat", "archive", "bundle", "write", "save",
    "create_file", "copy_file", "move_file",
]

# Argument signals for staging: payloads being prepared for movement.
_STAGING_ARG_MARKERS = [
    "/tmp/", "temp/", "staging", ".cache/", "data:text/plain",
    "data:application/octet-stream",
]

_EXFIL_TOOL_HINTS = [
    "http", "post", "upload", "send", "webhook", "curl", "wget",
    "request", "notify", "mail", "email", "publish", "push",
    "transfer", "share",
]

_URL_RE = re.compile(r"https?://[^\s\"'<>`]+", re.IGNORECASE)
_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
# A long unbroken base64 run in an argument is payload-shaped.
_B64_BLOB_RE = re.compile(r"[A-Za-z0-9+/]{240,}={0,2}")

# Hosts that are never exfiltration destinations. Mirrors the
# screener's internal-target lists, reduced to what can be decided
# without DNS: literals, localhost, and private-intranet suffixes.
_PRIVATE_HOST_SUFFIXES = (
    ".localhost", ".local", ".internal", ".intranet",
    ".lan", ".corp", ".home", ".private",
)
_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fc00::/7"),
]


def _host_is_external(host: str) -> bool:
    """True when a host is a plausible external endpoint.

    Literal and suffix checks only, no DNS: scoring must be
    deterministic, and a hostname that merely *resolves* internally
    is the SSRF module's problem, not this one's.
    """
    host = (host or "").strip().lower().rstrip(".").strip("[]")
    if not host:
        return False
    if host == "localhost" or host.endswith(_PRIVATE_HOST_SUFFIXES):
        return False
    ip = None
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            ip = ipaddress.IPv4Address(socket.inet_aton(host))
        except (OSError, ValueError):
            ip = None
    if ip is not None:
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:
            ip = mapped
        return not any(ip in net for net in _PRIVATE_NETS)
    return True


def _external_endpoints(arguments) -> list:
    """External hosts referenced by URLs or email addresses in args."""
    hosts = set()
    if arguments is None:
        return []
    try:
        blob = json.dumps(arguments, default=str)
    except (TypeError, ValueError):
        blob = str(arguments)
    for m in _URL_RE.finditer(blob):
        url = m.group(0).rstrip(".,;:!?)")
        try:
            from urllib.parse import urlsplit
            host = urlsplit(url).hostname or ""
        except Exception:
            host = ""
        if host and _host_is_external(host):
            hosts.add(host.lower())
    for m in _EMAIL_RE.finditer(blob):
        domain = m.group(1)
        if _host_is_external(domain):
            hosts.add(domain.lower())
    return sorted(hosts)


def _args_blob(arguments, limit: int = 20000) -> str:
    """Lowercased string form of arguments for marker matching."""
    if arguments is None:
        return ""
    try:
        blob = json.dumps(arguments, default=str)
    except (TypeError, ValueError):
        blob = str(arguments)
    return blob[:limit].lower()


def _matches_any(tool: str, hints: list) -> bool:
    return any(h in tool for h in hints)


def classify_call(tool_name: str, arguments: dict = None):
    """Classify one tool call into a kill-chain stage.

    Returns (stage, why) or (None, "") for a call with no stage
    signal. Priority is exfil > staging > access > recon: when a
    call carries several signals, the most progression-shaped one
    wins.
    """
    tool = (tool_name or "").lower()
    blob = _args_blob(arguments)

    # EXFIL: an outbound-shaped tool plus an external endpoint in
    # the arguments. Either half alone is not enough.
    if _matches_any(tool, _EXFIL_TOOL_HINTS):
        externals = _external_endpoints(arguments)
        if externals:
            return STAGE_EXFIL, (
                f"outbound tool with external endpoint "
                f"{externals[0]}")

    # STAGING: an encode/compress/write tool, or payload-shaped
    # arguments (large base64 blob, data URI, staging path).
    if _matches_any(tool, _STAGING_TOOL_HINTS):
        return STAGE_STAGING, "encode/compress/write tool name"
    if _B64_BLOB_RE.search(blob):
        return STAGE_STAGING, "large base64 payload in arguments"
    for marker in _STAGING_ARG_MARKERS:
        if marker in blob:
            return STAGE_STAGING, f"staging marker in arguments: {marker}"

    # ACCESS: sensitive tool name, or a read-shaped tool touching
    # sensitive material.
    if _matches_any(tool, _ACCESS_TOOL_HINTS):
        return STAGE_ACCESS, "tool name targets credential material"
    markers = [m for m in _SENSITIVE_ARG_MARKERS if m in blob]
    if markers and _matches_any(tool, _READ_TOOL_HINTS):
        shown = ", ".join(sorted(set(markers))[:3])
        return STAGE_ACCESS, f"sensitive markers in arguments: {shown}"
    if markers and ("path" in blob or "file" in blob):
        shown = ", ".join(sorted(set(markers))[:3])
        return STAGE_ACCESS, f"sensitive markers in arguments: {shown}"

    # RECON: discovery-shaped tool names.
    if _matches_any(tool, _RECON_TOOL_HINTS):
        return STAGE_RECON, "discovery/enumeration tool name"

    return None, ""


# ---------------------------------------------------------------------------
# Configuration.
# ---------------------------------------------------------------------------

_DEFAULT_STAGE_POINTS = {
    STAGE_RECON: 15.0,
    STAGE_ACCESS: 30.0,
    STAGE_STAGING: 20.0,
    STAGE_EXFIL: 30.0,
}


class SequenceScoringConfig:
    """Toggles and thresholds for kill-chain sequence scoring.

    Mirrors the proxy's other module toggles: an enable flag,
    thresholds, and stage behavior, loadable from a YAML policy
    section (from_dict), constructor arguments, or environment
    variables in the MCP_PROXY_* style (from_env).
    """

    def __init__(self, enabled: bool = True,
                 flag_threshold: float = 40.0,
                 block_threshold: float = 85.0,
                 block_stage: str = STAGE_EXFIL,
                 window_s: float = 1800.0,
                 half_life_s: float = 900.0,
                 gap_points: float = 20.0,
                 max_sessions: int = 4096,
                 stage_points: dict = None):
        self.enabled = bool(enabled)
        self.flag_threshold = float(flag_threshold)
        self.block_threshold = float(block_threshold)
        # Stage whose in-order completion blocks regardless of
        # score. None (or ""/"never" in config) disables the rule.
        if block_stage in ("", "never", "none"):
            block_stage = None
        self.block_stage = block_stage
        self.window_s = float(window_s)
        self.half_life_s = float(half_life_s)
        self.gap_points = float(gap_points)
        self.max_sessions = max(16, int(max_sessions))
        points = dict(_DEFAULT_STAGE_POINTS)
        if stage_points:
            for k, v in stage_points.items():
                if k in points:
                    points[k] = float(v)
        self.stage_points = points

    @classmethod
    def from_dict(cls, section: dict = None) -> "SequenceScoringConfig":
        """Build from a YAML policy section named sequence_scoring.

        Unknown keys are ignored so the policy file can grow without
        breaking older proxies.
        """
        section = section or {}
        return cls(
            enabled=section.get("enabled", True),
            flag_threshold=section.get("flag_threshold", 40.0),
            block_threshold=section.get("block_threshold", 85.0),
            block_stage=section.get("block_stage", STAGE_EXFIL),
            window_s=section.get("window_s", 1800.0),
            half_life_s=section.get("half_life_s", 900.0),
            gap_points=section.get("gap_points", 20.0),
            max_sessions=section.get("max_sessions", 4096),
            stage_points=section.get("stage_points"),
        )

    @classmethod
    def from_env(cls, environ: dict = None) -> "SequenceScoringConfig":
        """Build from MCP_PROXY_KILL_CHAIN_* environment variables."""
        import os
        env = environ if environ is not None else os.environ

        def _float(name, default):
            try:
                return float(env[name])
            except (KeyError, TypeError, ValueError):
                return default

        cfg = cls()
        cfg.enabled = env.get(
            "MCP_PROXY_KILL_CHAIN", "true").lower() != "false"
        cfg.flag_threshold = _float(
            "MCP_PROXY_KILL_CHAIN_FLAG_SCORE", cfg.flag_threshold)
        cfg.block_threshold = _float(
            "MCP_PROXY_KILL_CHAIN_BLOCK_SCORE", cfg.block_threshold)
        cfg.window_s = _float(
            "MCP_PROXY_KILL_CHAIN_WINDOW_S", cfg.window_s)
        cfg.half_life_s = _float(
            "MCP_PROXY_KILL_CHAIN_HALF_LIFE_S", cfg.half_life_s)
        block_stage = env.get("MCP_PROXY_KILL_CHAIN_BLOCK_STAGE")
        if block_stage:
            block_stage = block_stage.strip().lower()
            cfg.block_stage = (
                None if block_stage in ("", "never", "none")
                else block_stage)
        return cfg


def make_session_key(agent_id: str, server_url: str = "",
                     session_id: str = "") -> str:
    """Compose the session key the scorer tracks.

    An explicit transport session ID (e.g. the MCP Mcp-Session-Id
    header) wins when the deployment has one; otherwise the session
    is the (agent, server) pair, matching how behavior.py keys its
    per-agent state.
    """
    if session_id:
        return f"session:{session_id}"
    return f"{agent_id}|{server_url}"


# ---------------------------------------------------------------------------
# Session state and scorer.
# ---------------------------------------------------------------------------

class _SessionState:
    __slots__ = ("stage_index", "score", "last_ts", "last_advance_ts",
                 "chain_count", "events", "calls")

    def __init__(self):
        self.stage_index = -1        # highest stage reached in order
        self.score = 0.0
        self.last_ts = 0.0
        self.last_advance_ts = 0.0
        self.chain_count = 1
        self.events = []             # stage events, for explanations
        self.calls = 0

    def reset_progress(self):
        self.stage_index = -1
        self.events = []
        self.last_advance_ts = 0.0


class KillChainScorer:
    """Session-scoped kill-chain sequence scoring.

    Usage in the proxy's tools/call path, alongside BehaviorTracker:

        result = scorer.observe_call(session_key, tool_name,
                                     arguments, server_url=upstream)
    result is a dict with keys: verdict ("allow"|"flag"|"block"),
    poison_category, reasons, risk_score, sequence, signals.

    Threading: like BehaviorTracker, this assumes the proxy's
    single request-handling flow per process.
    """

    def __init__(self, config: SequenceScoringConfig = None,
                 enabled: bool = None):
        self.config = config or SequenceScoringConfig()
        if enabled is not None:
            self.config.enabled = bool(enabled)
        self._sessions = OrderedDict()  # session_key -> _SessionState

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    # -- state helpers --------------------------------------------------

    def _state_for(self, session_key: str) -> _SessionState:
        state = self._sessions.get(session_key)
        if state is None:
            state = _SessionState()
            self._sessions[session_key] = state
            while len(self._sessions) > self.config.max_sessions:
                self._sessions.popitem(last=False)
        else:
            self._sessions.move_to_end(session_key)
        return state

    def _decay(self, score: float, elapsed_s: float) -> float:
        if elapsed_s <= 0 or score <= 0:
            return score
        return score * (0.5 ** (elapsed_s / self.config.half_life_s))

    def _explanation(self, state: _SessionState) -> str:
        """One-line audit explanation of the chain so far."""
        if not state.events:
            return "no kill-chain stage events recorded"
        parts = []
        for ev in state.events:
            label = STAGE_LABELS[ev["stage"]]
            kind = "gap" if ev.get("gap") else "stage"
            parts.append(
                f"{label} via '{ev['tool']}' ({ev['why']}) [{kind}]")
        stage_txt = (
            f"stage {state.stage_index + 1}/4 "
            f"{STAGE_LABELS[STAGE_ORDER[state.stage_index]]}"
            if state.stage_index >= 0 else "no ordered stage reached")
        return (
            f"kill-chain chain {state.chain_count}: "
            + "; ".join(parts)
            + f"; progression at {stage_txt}; "
            f"session score {state.score:.0f} "
            f"(flag at {self.config.flag_threshold:.0f}, "
            f"block at {self.config.block_threshold:.0f})")

    def _result(self, session_key: str, state: _SessionState,
                verdict: str, reasons: list) -> dict:
        explanation = self._explanation(state)
        stages_seen = []
        for ev in state.events:
            if not ev.get("gap") and ev["stage"] not in stages_seen:
                stages_seen.append(ev["stage"])
        return {
            "verdict": verdict,
            "poison_category": (
                POISON_KILL_CHAIN if verdict != "allow" else "clean"),
            "reasons": reasons,
            "risk_score": round(state.score, 1),
            "sequence": {
                "session": session_key,
                "chain": state.chain_count,
                "stage": (STAGE_ORDER[state.stage_index]
                          if state.stage_index >= 0 else None),
                "stage_index": state.stage_index,
                "stages_seen": stages_seen,
                "score": round(state.score, 1),
                "explanation": explanation,
            },
            "signals": ([{
                "code": "KILL_CHAIN",
                "detail": explanation,
                "risk": round(state.score, 1),
            }] if verdict != "allow" else []),
        }

    # -- core progression ----------------------------------------------

    def _apply_stage(self, state: _SessionState, stage: str,
                     tool_name: str, why: str, now: float):
        """Score one stage observation. Returns (points, advanced, gap)."""
        sidx = STAGE_ORDER.index(stage)
        if sidx == state.stage_index + 1:
            state.stage_index = sidx
            state.last_advance_ts = now
            state.events.append({
                "stage": stage, "tool": tool_name, "why": why,
                "ts": now, "gap": False,
            })
            return self.config.stage_points[stage], True, False
        if sidx > state.stage_index + 1:
            state.events.append({
                "stage": stage, "tool": tool_name, "why": why,
                "ts": now, "gap": True,
            })
            # Bound memory: explanations only need recent events.
            state.events = state.events[-50:]
            return self.config.gap_points, False, True
        # Same or earlier stage: already counted. No double-counting,
        # so repeating one stage can never grind the score upward.
        return 0.0, False, False

    def _prepare(self, state: _SessionState, now: float):
        """Window expiry and decay, applied before each observation."""
        if (state.stage_index >= 0 and state.last_advance_ts
                and now - state.last_advance_ts > self.config.window_s):
            # The chain went quiet past the progression window: the
            # partial progression is abandoned, not banked.
            state.reset_progress()
        if state.last_ts:
            state.score = self._decay(state.score,
                                      now - state.last_ts)
        state.last_ts = now
        # Note: progression expiry is governed by the window above
        # alone. An earlier draft also forgot progression when the
        # decayed score fell under a floor, but that double-forgetting
        # wiped legitimate slow chains (and any chain whose operator
        # retuned stage points downward) mid-progression. Score decay
        # by itself guarantees benign sessions never bank risk
        # forever; the window forgets stale progression.

    def _verdict_for(self, points: float, advanced: bool, stage,
                     state: _SessionState) -> str:
        reached_block_stage = (
            advanced and self.config.block_stage is not None
            and stage == self.config.block_stage)
        if reached_block_stage:
            return "block"
        if points > 0 and state.score >= self.config.block_threshold:
            return "block"
        if points > 0 and state.score >= self.config.flag_threshold:
            return "flag"
        return "allow"

    # -- public API -----------------------------------------------------

    def observe_call(self, session_key: str, tool_name: str,
                     arguments: dict = None, server_url: str = "",
                     ts: float = None) -> dict:
        """Score one tool call within its session.

        Returns the verdict dict described in the class docstring.
        Block verdicts reset the session's stage progression (the
        chain has been acted on) while the score itself is left to
        decay, mirroring RiskScorer semantics in behavior.py.
        """
        now = ts if ts is not None else time.time()
        if not self.config.enabled:
            return {
                "verdict": "allow", "poison_category": "clean",
                "reasons": [], "risk_score": 0.0,
                "sequence": {"session": session_key, "stage": None,
                             "stage_index": -1, "stages_seen": [],
                             "score": 0.0,
                             "explanation": "sequence scoring disabled"},
                "signals": [],
            }

        state = self._state_for(session_key)
        self._prepare(state, now)
        state.calls += 1

        stage, why = classify_call(tool_name, arguments)
        points, advanced, gap = 0.0, False, False
        if stage is not None:
            points, advanced, gap = self._apply_stage(
                state, stage, tool_name, why, now)
            if points > 0:
                state.score = min(100.0, state.score + points)

        verdict = self._verdict_for(points, advanced, stage, state)
        reasons = []
        if verdict != "allow":
            reasons.append(f"kill_chain: {self._explanation(state)}")
        result = self._result(session_key, state, verdict, reasons)

        if verdict == "block":
            # The chain is complete and acted on: reset progression
            # so a later chain is scored as a new chain. The score
            # stays (decaying) so session_state still shows the
            # session is hot.
            state.reset_progress()
            state.chain_count += 1

        log.info("kill-chain: session=%s tool=%s stage=%s +%s -> "
                 "score %.1f verdict=%s",
                 session_key, tool_name, stage, points, state.score,
                 verdict)
        return result

    def observe_result(self, session_key: str,
                       external_endpoints: list = None,
                       tool_name: str = "", ts: float = None) -> dict:
        """Score external endpoints seen in a tool *result*.

        The call-side classifier can only see where a call is aimed.
        When a result hands the agent fresh external endpoints (a
        poisoned result steering the session outward), the proxy can
        feed them here: an external endpoint appearing after ACCESS
        or STAGING progress is an exfiltration-stage observation.
        With no prior progression it is noted as a gap observation
        only, never a chain advance on its own.
        """
        now = ts if ts is not None else time.time()
        state = self._state_for(session_key)
        if not self.config.enabled or not external_endpoints:
            return self._result(session_key, state, "allow", [])
        self._prepare(state, now)
        external = [h for h in external_endpoints
                    if _host_is_external(h)]
        if not external:
            return self._result(session_key, state, "allow", [])
        points, advanced, gap = self._apply_stage(
            state, STAGE_EXFIL, tool_name or "(tool result)",
            f"result referenced external endpoint {external[0]}", now)
        if points > 0:
            state.score = min(100.0, state.score + points)
        verdict = self._verdict_for(points, advanced, STAGE_EXFIL,
                                    state)
        reasons = []
        if verdict != "allow":
            reasons.append(f"kill_chain: {self._explanation(state)}")
        result = self._result(session_key, state, verdict, reasons)
        if verdict == "block":
            state.reset_progress()
            state.chain_count += 1
        return result

    def session_state(self, session_key: str, ts: float = None) -> dict:
        """Current session snapshot (decayed) for admin/audit use."""
        state = self._sessions.get(session_key)
        if state is None:
            return {"session": session_key, "known": False,
                    "score": 0.0, "stage": None, "stages_seen": []}
        now = ts if ts is not None else time.time()
        score = self._decay(state.score, now - state.last_ts) \
            if state.last_ts else state.score
        stages_seen = []
        for ev in state.events:
            if not ev.get("gap") and ev["stage"] not in stages_seen:
                stages_seen.append(ev["stage"])
        return {
            "session": session_key,
            "known": True,
            "chain": state.chain_count,
            "score": round(score, 1),
            "stage": (STAGE_ORDER[state.stage_index]
                      if state.stage_index >= 0 else None),
            "stages_seen": stages_seen,
            "calls": state.calls,
            "explanation": self._explanation(state),
        }

    def sessions(self) -> dict:
        """All known session snapshots (for admin endpoints)."""
        return {k: self.session_state(k) for k in list(self._sessions)}

    def reset(self, session_key: str = None):
        """Forget one session, or all sessions when key is None."""
        if session_key is None:
            self._sessions.clear()
        else:
            self._sessions.pop(session_key, None)
