"""Policy engine for the MCP proxy firewall.

Evaluates every tools/call against administrator-defined rules
*before* TI screening runs. Policy denies are fast: no network calls,
no corpus lookups. The point is deterministic control over which
agents may call which tools on which servers.

Policy format (YAML):

    agents:
      "agent-123":
        allow_tools: ["read_file", "search"]
        deny_tools: ["exec_shell"]
    servers:
      "http://internal:9000":
        trust: high
        strictness: relaxed
    tools:
      "exec_shell":
        require_approval: true
        rate_limit: 10/minute

Evaluation order for a tools/call:
  1. Agent rules (deny_tools wins over allow_tools; an allow_tools
     list, when present, is exclusive).
  2. Tool rules (rate limits; require_approval flags the call for
     operator review).
  3. Server rules (trust level feeds screening strictness hints).

A policy decision of "deny" blocks the call immediately with a signed
verdict carrying poison_category "policy_deny". A decision of
"approval_required" flags the call for review but does not block.
"""

import fnmatch
import logging
import os
import time

log = logging.getLogger(__name__)

# Rate limit window parsing: "10/minute", "100/hour", "5/second".
_RATE_WINDOWS = {
    "second": 1.0,
    "minute": 60.0,
    "hour": 3600.0,
    "day": 86400.0,
}


def parse_rate_limit(spec: str):
    """Parse "N/window" into (max_calls, window_seconds).

    Returns (None, None) for unparsable specs.
    """
    try:
        count_s, window_s = spec.split("/", 1)
        count = int(count_s.strip())
        window = _RATE_WINDOWS.get(window_s.strip().lower())
        if window is None or count < 1:
            return None, None
        return count, window
    except (ValueError, AttributeError):
        return None, None


def _match_key(pattern: str, value: str) -> bool:
    """Glob match a policy key against a runtime value."""
    return fnmatch.fnmatchcase(value, pattern)


def _load_yaml(path: str) -> dict:
    """Load a YAML policy file. Returns {} on any problem."""
    try:
        import yaml
    except ImportError:
        log.error("policy: PyYAML not available, cannot load %s", path)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except OSError as exc:
        log.error("policy: cannot read %s: %s", path, exc)
        return {}
    except Exception as exc:
        log.error("policy: invalid YAML in %s: %s", path, exc)
        return {}
    if not isinstance(data, dict):
        log.error("policy: top-level YAML in %s must be a mapping", path)
        return {}
    return data


class RateLimiter:
    """Sliding-window per-key rate limiter (in-memory)."""

    def __init__(self):
        # key -> list of event timestamps (monotonic)
        self._events = {}

    def check(self, key: str, max_calls: int, window_s: float,
              now: float = None) -> bool:
        """Record an event and return True if within the limit.

        Returns False when the limit is exceeded (the event still
        counts toward the window).
        """
        now = time.monotonic() if now is None else now
        events = self._events.setdefault(key, [])
        cutoff = now - window_s
        events = [t for t in events if t > cutoff]
        events.append(now)
        self._events[key] = events
        return len(events) <= max_calls

    def reset(self):
        self._events.clear()


class PolicyEngine:
    """Evaluates tools/call requests against a YAML policy.

    Thread-safety: this engine is used from the proxy's single
    request-handling flow; rate limiter state is per-process.
    """

    def __init__(self, policy_path: str = ""):
        self.policy_path = policy_path or os.environ.get(
            "MCP_PROXY_POLICY_FILE", "")
        self._policy = {"agents": {}, "servers": {}, "tools": {}}
        self._limiter = RateLimiter()
        self._loaded_at = 0.0
        if self.policy_path:
            self.reload()

    @property
    def enabled(self) -> bool:
        return bool(self.policy_path)

    @property
    def loaded(self) -> bool:
        return self._loaded_at > 0

    def reload(self) -> bool:
        """Reload the policy file. Returns True on success."""
        if not self.policy_path:
            return False
        data = _load_yaml(self.policy_path)
        if not data and self._loaded_at > 0:
            # Keep the last good policy on parse failure.
            log.warning("policy: keeping previous policy after load failure")
            return False
        policy = {
            "agents": data.get("agents") or {},
            "servers": data.get("servers") or {},
            "tools": data.get("tools") or {},
        }
        self._policy = policy
        self._loaded_at = time.time()
        log.info("policy: loaded %s (agents=%d servers=%d tools=%d)",
                 self.policy_path, len(policy["agents"]),
                 len(policy["servers"]), len(policy["tools"]))
        return True

    # -- lookup helpers -------------------------------------------------

    def _agent_rules(self, agent_id: str) -> dict:
        for pattern, rules in self._policy["agents"].items():
            if _match_key(str(pattern), agent_id):
                return rules or {}
        return {}

    def _server_rules(self, server_url: str) -> dict:
        for pattern, rules in self._policy["servers"].items():
            if _match_key(str(pattern), server_url):
                return rules or {}
        return {}

    def _tool_rules(self, tool_name: str) -> dict:
        for pattern, rules in self._policy["tools"].items():
            if _match_key(str(pattern), tool_name):
                return rules or {}
        return {}

    # -- evaluation -----------------------------------------------------

    def evaluate(self, agent_id: str, tool_name: str, server_url: str,
                 arguments: dict = None) -> dict:
        """Evaluate a tools/call. Returns a decision dict.

        decision: "allow" | "deny" | "approval_required"
        """
        if not self.enabled:
            return {"decision": "allow", "reasons": ["policy disabled"]}

        reasons = []

        # 1. Agent rules.
        agent_rules = self._agent_rules(agent_id)
        deny_tools = agent_rules.get("deny_tools") or []
        allow_tools = agent_rules.get("allow_tools") or []
        if any(_match_key(str(p), tool_name) for p in deny_tools):
            return {
                "decision": "deny",
                "reasons": [f"agent '{agent_id}' denied tool '{tool_name}' "
                            f"by policy"],
                "poison_category": "policy_deny",
            }
        if allow_tools and not any(
                _match_key(str(p), tool_name) for p in allow_tools):
            return {
                "decision": "deny",
                "reasons": [f"tool '{tool_name}' not in agent "
                            f"'{agent_id}' allow list"],
                "poison_category": "policy_deny",
            }

        # 2. Tool rules: rate limits.
        tool_rules = self._tool_rules(tool_name)
        rate_spec = tool_rules.get("rate_limit")
        if rate_spec:
            max_calls, window_s = parse_rate_limit(str(rate_spec))
            if max_calls:
                key = f"{agent_id}:{tool_name}"
                if not self._limiter.check(key, max_calls, window_s):
                    return {
                        "decision": "deny",
                        "reasons": [f"tool '{tool_name}' rate limit "
                                    f"exceeded ({rate_spec})"],
                        "poison_category": "policy_deny",
                    }

        # 3. Tool rules: approval requirement.
        if tool_rules.get("require_approval"):
            reasons.append(f"tool '{tool_name}' requires operator approval")
            return {
                "decision": "approval_required",
                "reasons": reasons,
                "poison_category": "policy_approval",
            }

        # 4. Server rules: trust level is advisory here; screening
        #    strictness is applied by the caller.
        server_rules = self._server_rules(server_url)
        trust = server_rules.get("trust", "medium")
        strictness = server_rules.get("strictness", "standard")
        return {
            "decision": "allow",
            "reasons": reasons or ["policy allows"],
            "poison_category": "clean",
            "server_trust": trust,
            "server_strictness": strictness,
        }

    def summary(self) -> dict:
        """Policy overview for the admin API."""
        return {
            "enabled": self.enabled,
            "path": self.policy_path,
            "loaded": self.loaded,
            "loaded_at": self._loaded_at,
            "agents": len(self._policy["agents"]),
            "servers": len(self._policy["servers"]),
            "tools": len(self._policy["tools"]),
        }
