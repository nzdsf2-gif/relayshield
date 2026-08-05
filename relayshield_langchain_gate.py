"""
RelayShield mandatory-gate reference implementation for LangChain.

Context: a host-side, pre-execution gate in front of "connect to / install an
unfamiliar MCP server or package" -- the first reference gate proposed by
John6666 (HF discuss.huggingface.co, smolagents-agent-security-tools-v2
thread) after CrewAI's before_tool_call hook (crewAIInc/crewAI#6550, still
awaiting maintainer review as of 2026-07-21).

LangChain's `wrap_tool_call` middleware hook (langchain.agents.middleware,
verified against langchain==1.3.14 / langgraph-prebuilt==1.1.0) is the
concrete home used here -- it is a real, shipped, blocking pre-execution
hook with the same shape as John6666's `before_tool_call` pseudocode:
inspect the tool call, decide, and only then invoke (or refuse to invoke)
the actual handler.

This is deliberately not framework-exclusive. The gate logic
(normalize_finding / evaluate_gate_policy) has no LangChain import and can
be reused verbatim behind CrewAI's before_tool_call, an MCP client/gateway,
or any other pre-execution chokepoint John6666 lists in his message.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger("relayshield.gate")

# ---------------------------------------------------------------------------
# Protected action surface
# ---------------------------------------------------------------------------
# The raw connection/install tools are intentionally never bound to the model
# directly in a real deployment -- only this composite/gated path is exposed.
# A model "calling a lower-level connector directly" is not a case the
# middleware can catch after the fact; it is prevented architecturally by not
# giving the model a tool that skips the gate. See John6666's own framing:
# "The raw connection/install capability should either: not be exposed
# directly to the model, or only be exposed through a composite tool or host
# hook that cannot execute it before the gate completes."
PROTECTED_TOOLS = {
    "connect_mcp_server",
    "install_mcp_package",
}

RELAYSHIELD_API_BASE = os.environ.get(
    "RELAYSHIELD_API_BASE", "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod"
)
RELAYSHIELD_CHECK_PATH = "/v1/metered/mcp-registry-risk"

# Bounded retry policy for transient upstream conditions (429 / timeout).
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 1.0


# ---------------------------------------------------------------------------
# Normalized check state
# ---------------------------------------------------------------------------
# This is the layer John6666 asked to keep first-class even though
# RelayShield's `mcp-registry-risk` endpoint does not yet natively emit all of
# these distinctions -- it returns {"verdict": ..., "findings": [...]} and an
# HTTP status, nothing more granular. The adapter below is where "no matching
# intelligence found" gets separated from "the check never completed",
# because a mandatory gate cannot treat those as the same answer.
class CheckState(str, Enum):
    FINDING = "finding"                    # relevant evidence of risk
    NO_KNOWN_FINDING = "no_known_finding"   # fresh, sufficiently covered, clean
    UNKNOWN = "unknown"                     # host-adapter default; not yet distinguished by the API
    PARTIAL = "partial"                     # only part of the target was checkable (e.g. package_name only)
    STALE = "stale"                         # reserved -- API has no freshness/cache-age field today
    AUTH_FAILURE = "auth_failure"
    UPSTREAM_FAILURE = "upstream_failure"   # timeout / 429 / 5xx
    MALFORMED = "malformed"                 # empty body / invalid JSON / non-JSON 200
    PAYMENT_REQUIRED = "payment_required"
    MISSING = "missing"                     # unrecognized/absent outcome shape


class GateAction(str, Enum):
    ALLOW = "allow"
    REVIEW = "review"
    DENY = "deny"
    DEFER = "defer"


@dataclass(frozen=True)
class GateDecision:
    action: GateAction
    reason_codes: list[str]
    check_version: str
    observed_at: str
    detail: str = ""


@dataclass(frozen=True)
class CheckResult:
    state: CheckState
    verdict: str | None = None
    findings: list[dict] = field(default_factory=list)
    raw_status: int | None = None


# ---------------------------------------------------------------------------
# Trusted RelayShield client
# ---------------------------------------------------------------------------
# Called from trusted host/middleware code only -- never exposed to the model
# as a callable tool, so it cannot be selected as an optional preliminary
# step and skipped. It also cannot recurse into its own gate: it is a plain
# HTTP call, not a graph tool node, so PROTECTED_TOOLS membership is moot for
# it by construction.
class RelayShieldCheckError(Exception):
    """Raised for conditions the caller must map to a CheckState, not a Python exception."""

    def __init__(self, kind: str, detail: str = "", status: int | None = None):
        self.kind = kind
        self.detail = detail
        self.status = status
        super().__init__(f"{kind}: {detail}")


def check_mcp_registry_risk(
    server_url: str | None = None,
    package_name: str | None = None,
    api_key: str | None = None,
    timeout: float = 8.0,
) -> CheckResult:
    """Call RelayShield's mcp-registry-risk endpoint and normalize the result.

    Raises RelayShieldCheckError for every non-2xx / malformed / network
    condition -- the caller (evaluate against policy) is responsible for
    turning that into a CheckState, so this function never silently returns
    a "clean" result on failure.
    """
    api_key = api_key or os.environ.get("RELAYSHIELD_API_KEY", "")
    if not api_key:
        raise RelayShieldCheckError("auth_failure", "no RELAYSHIELD_API_KEY configured")

    body = json.dumps(
        {k: v for k, v in {"server_url": server_url, "package_name": package_name}.items() if v}
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{RELAYSHIELD_API_BASE}{RELAYSHIELD_CHECK_PATH}",
        data=body,
        headers={"Content-Type": "application/json", "X-RS-API-KEY": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
        if status == 401:
            raise RelayShieldCheckError("auth_failure", detail=raw.decode(errors="replace"), status=status) from exc
        if status == 402:
            raise RelayShieldCheckError("payment_required", detail=raw.decode(errors="replace"), status=status) from exc
        if status == 429:
            raise RelayShieldCheckError("upstream_failure", detail="rate_limited", status=status) from exc
        if status >= 500:
            raise RelayShieldCheckError("upstream_failure", detail=raw.decode(errors="replace"), status=status) from exc
        raise RelayShieldCheckError("malformed", detail=f"unexpected status {status}", status=status) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RelayShieldCheckError("upstream_failure", detail=str(exc)) from exc

    if not raw:
        raise RelayShieldCheckError("malformed", detail="empty body", status=status)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RelayShieldCheckError("malformed", detail=str(exc), status=status) from exc
    if not isinstance(data, dict) or "verdict" not in data:
        raise RelayShieldCheckError("malformed", detail="response missing 'verdict'", status=status)

    verdict = data.get("verdict", "LOW")
    findings = data.get("findings", [])

    if findings:
        return CheckResult(state=CheckState.FINDING, verdict=verdict, findings=findings, raw_status=status)

    # package_name-only requests are explicitly partial coverage per the
    # API's own "package_name_only" finding type -- but that finding type is
    # LOW severity today, so it lands in `findings` above, not here. This
    # branch is reserved for a future response shape that signals partial
    # coverage without an accompanying LOW finding.
    if server_url is None and package_name is not None:
        return CheckResult(state=CheckState.PARTIAL, verdict=verdict, raw_status=status)

    return CheckResult(state=CheckState.NO_KNOWN_FINDING, verdict=verdict, raw_status=status)


def check_mcp_registry_risk_with_retry(**kwargs) -> tuple[CheckState, CheckResult | None, RelayShieldCheckError | None]:
    """Bounded retry wrapper. Only retries upstream_failure; every other
    failure kind is terminal after one attempt (per John6666's table:
    auth/malformed/payment_required are not retry-eligible states)."""
    last_err: RelayShieldCheckError | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            result = check_mcp_registry_risk(**kwargs)
            return result.state, result, None
        except RelayShieldCheckError as exc:
            last_err = exc
            if exc.kind != "upstream_failure" or attempt == MAX_RETRIES:
                return CheckState(exc.kind), None, exc
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
    return CheckState.UPSTREAM_FAILURE, None, last_err


# ---------------------------------------------------------------------------
# Policy -- John6666's table, applied verbatim
# ---------------------------------------------------------------------------
_POLICY: dict[CheckState, GateAction] = {
    CheckState.FINDING: GateAction.DENY,
    CheckState.NO_KNOWN_FINDING: GateAction.ALLOW,
    CheckState.UNKNOWN: GateAction.REVIEW,
    CheckState.PARTIAL: GateAction.REVIEW,
    CheckState.STALE: GateAction.REVIEW,
    CheckState.AUTH_FAILURE: GateAction.DEFER,
    CheckState.UPSTREAM_FAILURE: GateAction.DEFER,
    CheckState.MALFORMED: GateAction.DEFER,
    CheckState.PAYMENT_REQUIRED: GateAction.DEFER,
    CheckState.MISSING: GateAction.DEFER,
}


def evaluate_gate_policy(state: CheckState, result: CheckResult | None = None) -> GateDecision:
    action = _POLICY.get(state, GateAction.DEFER)  # unrecognized state -> defer, never allow
    reason_codes = [state.value]
    if result and result.findings:
        reason_codes += [f["type"] for f in result.findings]
    return GateDecision(
        action=action,
        reason_codes=reason_codes,
        check_version="mcp-registry-risk-v1",
        observed_at=datetime.now(timezone.utc).isoformat(),
        detail=(result.verdict if result else state.value),
    )


def record_gate_decision(target: dict, decision: GateDecision) -> None:
    """Audit log -- decision, reason codes, check version, target identifier,
    and time only. Never logs API keys, payment proofs, or session material."""
    logger.info(
        "relayshield_gate_decision target=%s action=%s reasons=%s check_version=%s observed_at=%s",
        {k: v for k, v in target.items() if v},
        decision.action.value,
        decision.reason_codes,
        decision.check_version,
        decision.observed_at,
    )


# ---------------------------------------------------------------------------
# LangChain middleware
# ---------------------------------------------------------------------------
def _deny_message(tool_call: dict, decision: GateDecision):
    from langchain_core.messages import ToolMessage

    return ToolMessage(
        content=(
            f"Blocked by RelayShield registry-risk gate: action={decision.action.value} "
            f"reasons={decision.reason_codes}. The connection/install did not occur. "
            "Local reading, analysis, and drafting remain available."
        ),
        name=tool_call["name"],
        tool_call_id=tool_call["id"],
        status="error",
    )


def _build_gate_middleware():
    """Constructs the middleware class lazily so this module imports cleanly
    even if langchain/langgraph aren't installed (e.g. under pytest -k gate
    without the full agent stack)."""
    from langchain.agents.middleware import AgentMiddleware

    class RelayShieldMCPGateMiddleware(AgentMiddleware):
        """Mandatory pre-execution gate for connect_mcp_server / install_mcp_package.

        Invoked by the trusted host (this middleware), never selected by the
        model as an optional tool call. A raised exception inside the gate
        itself is treated as `defer`, not `allow` -- see the broad except
        below; failing open would defeat the purpose of a mandatory gate.
        """

        def wrap_tool_call(self, request, handler):
            tool_call = request.tool_call
            if tool_call["name"] not in PROTECTED_TOOLS:
                return handler(request)  # unrelated tools are unaffected

            args = tool_call.get("args", {})
            target = {"server_url": args.get("server_url"), "package_name": args.get("package_name")}

            try:
                state, result, err = check_mcp_registry_risk_with_retry(**target)
                decision = evaluate_gate_policy(state, result)
            except Exception:  # noqa: BLE001 -- gate failure must not become allow
                logger.exception("relayshield_gate: unhandled exception, defaulting to defer")
                decision = GateDecision(
                    action=GateAction.DEFER,
                    reason_codes=["gate_internal_exception"],
                    check_version="mcp-registry-risk-v1",
                    observed_at=datetime.now(timezone.utc).isoformat(),
                )

            record_gate_decision(target, decision)

            if decision.action == GateAction.ALLOW:
                return handler(request)

            # review / deny / defer all resolve to "protected action does not
            # occur" for this reference gate -- a fuller deployment could
            # route `review` to a human-in-the-loop interrupt instead
            # (see langchain.agents.middleware.HumanInTheLoopMiddleware,
            # which this middleware composes cleanly with).
            return _deny_message(tool_call, decision)

    return RelayShieldMCPGateMiddleware


try:
    RelayShieldMCPGateMiddleware = _build_gate_middleware()
except ImportError:
    # langchain/langgraph not installed -- the pure-Python gate logic above
    # (CheckState, evaluate_gate_policy, check_mcp_registry_risk_with_retry)
    # remains importable and testable on its own.
    RelayShieldMCPGateMiddleware = None
