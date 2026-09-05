"""Framework-agnostic gate core: call RelayShield, map the answer to a decision.

Nothing in this module imports crewai. That is deliberate and it is the same
split the LangChain gate uses: the policy is the valuable part and it should be
reusable behind any pre-execution chokepoint, so the framework binding lives in
one thin file next door (`hook.py`) and this one can be tested with no agent
framework installed at all.

This IS a copy of logic that also exists in the RelayShield repo's
`relayshield_langchain_gate.py`, and copies are how four pattern tables end up
disagreeing. It is copied anyway because a PyPI package cannot import from a
private repo, and the mitigation is that the copy is small, pure, and pinned by
tests that assert the policy table itself rather than its effects.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger("relayshield.gate")

DEFAULT_API_BASE = "https://api.relayshield.net"
CHECK_VERSION = "mcp-registry-risk-v1"
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 0.5


class CheckState(str, Enum):
    """What the check actually told us. Kept distinct from what we DO about it,
    because collapsing 'the API was down' into 'nothing found' is the bug that
    turns a gate into decoration."""

    FINDING = "finding"
    NO_KNOWN_FINDING = "no_known_finding"
    UNKNOWN = "unknown"
    PARTIAL = "partial"
    STALE = "stale"
    AUTH_FAILURE = "auth_failure"
    UPSTREAM_FAILURE = "upstream_failure"
    MALFORMED = "malformed"
    PAYMENT_REQUIRED = "payment_required"
    MISSING = "missing"


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


class RelayShieldCheckError(Exception):
    """A condition the caller maps to a CheckState. Never allowed to escape as a
    bare exception, because an exception in a gate is an outage in the agent."""

    def __init__(self, kind: str, detail: str = "", status: int | None = None):
        self.kind = kind
        self.detail = detail
        self.status = status
        super().__init__(f"{kind}: {detail}")


def check_mcp_registry_risk(
    server_url: str | None = None,
    package_name: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    timeout: float = 8.0,
) -> CheckResult:
    """Ask RelayShield about an MCP server or package and normalise the answer."""
    if not server_url and not package_name:
        raise RelayShieldCheckError("missing", "neither server_url nor package_name given")

    base = (api_base or os.environ.get("RELAYSHIELD_API_URL") or DEFAULT_API_BASE).rstrip("/")
    key = api_key or os.environ.get("RELAYSHIELD_API_KEY", "")

    payload: dict[str, str] = {}
    if server_url:
        payload["server_url"] = server_url
    if package_name:
        payload["package_name"] = package_name

    req = urllib.request.Request(
        f"{base}/v1/mcp-registry-risk",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **({"x-api-key": key} if key else {})},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8", "replace") if exc.fp else ""
        if status in (401, 403):
            raise RelayShieldCheckError("auth_failure", body[:200], status) from exc
        if status == 402:
            raise RelayShieldCheckError("payment_required", body[:200], status) from exc
        if status == 429 or status >= 500:
            raise RelayShieldCheckError("upstream_failure", body[:200], status) from exc
        raise RelayShieldCheckError("malformed", body[:200], status) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RelayShieldCheckError("upstream_failure", str(exc)[:200]) from exc

    if not body.strip():
        raise RelayShieldCheckError("malformed", "empty body", status)
    try:
        doc = json.loads(body)
    except ValueError as exc:
        raise RelayShieldCheckError("malformed", "non-JSON 200", status) from exc

    data = doc.get("data") if isinstance(doc, dict) else None
    if not isinstance(data, dict):
        raise RelayShieldCheckError("malformed", "no data object", status)

    findings = [f for f in (data.get("findings") or []) if isinstance(f, dict)]
    verdict = data.get("verdict") or data.get("risk_level")

    if findings:
        state = CheckState.FINDING
    elif package_name and not server_url:
        # Only half the target was checkable. Not the same as clean, and the
        # policy table treats it differently on purpose.
        state = CheckState.PARTIAL
    elif verdict is None:
        state = CheckState.UNKNOWN
    else:
        state = CheckState.NO_KNOWN_FINDING

    return CheckResult(state=state, verdict=verdict, findings=findings, raw_status=status)


def check_with_retry(**kwargs):
    """Bounded retry. Only `upstream_failure` is retried: an auth failure, a 402
    or a malformed body will say exactly the same thing the second time, and
    retrying them just adds latency to a decision that is already made."""
    last: RelayShieldCheckError | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            result = check_mcp_registry_risk(**kwargs)
            return result.state, result, None
        except RelayShieldCheckError as exc:
            last = exc
            if exc.kind != "upstream_failure" or attempt == MAX_RETRIES:
                try:
                    return CheckState(exc.kind), None, exc
                except ValueError:
                    return CheckState.MISSING, None, exc
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
    return CheckState.UPSTREAM_FAILURE, None, last


# The policy table. Kept as data rather than branches so a test can assert it
# directly, and so an unrecognised state cannot fall through to ALLOW.
POLICY: dict[CheckState, GateAction] = {
    CheckState.FINDING:          GateAction.DENY,
    CheckState.NO_KNOWN_FINDING: GateAction.ALLOW,
    CheckState.UNKNOWN:          GateAction.REVIEW,
    CheckState.PARTIAL:          GateAction.REVIEW,
    CheckState.STALE:            GateAction.REVIEW,
    CheckState.AUTH_FAILURE:     GateAction.DEFER,
    CheckState.UPSTREAM_FAILURE: GateAction.DEFER,
    CheckState.MALFORMED:        GateAction.DEFER,
    CheckState.PAYMENT_REQUIRED: GateAction.DEFER,
    CheckState.MISSING:          GateAction.DEFER,
}


def evaluate_gate_policy(state: CheckState, result: CheckResult | None = None) -> GateDecision:
    action = POLICY.get(state, GateAction.DEFER)   # unknown state defers, never allows
    # getattr rather than state.value: a caller passing a plain string, or a
    # state added in a later version, must still get a DEFER rather than an
    # AttributeError. A gate that raises is an outage in someone else's agent,
    # and the whole point of the DEFER default is to survive the unexpected.
    reasons = [getattr(state, "value", str(state))]
    if result and result.findings:
        reasons += [str(f.get("type", "finding")) for f in result.findings]
    return GateDecision(
        action=action,
        reason_codes=reasons,
        check_version=CHECK_VERSION,
        observed_at=datetime.now(timezone.utc).isoformat(),
        detail=(result.verdict if result and result.verdict
                else getattr(state, "value", str(state))),
    )


def record_gate_decision(target: dict, decision: GateDecision) -> None:
    """Audit line. Decision, reasons, version, target and time only: never an
    API key, a payment proof or session material."""
    logger.info(
        "relayshield_gate_decision target=%s action=%s reasons=%s check_version=%s observed_at=%s",
        {k: v for k, v in target.items() if v},
        decision.action.value,
        decision.reason_codes,
        decision.check_version,
        decision.observed_at,
    )
