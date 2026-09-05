"""The CrewAI binding: a `before_tool_call` hook that refuses the call.

VERIFIED AGAINST THE RELEASED PACKAGE, NOT THE PULL REQUEST
-----------------------------------------------------------
RelayShield's notes carried `crewAIInc/crewAI#6550` as "still awaiting maintainer
review", and a gate written against an unmerged PR is a gate nobody can install.
Checked against `crewai` 1.15.20 on 2026-09-05 by reading the wheel: the hook is
SHIPPED. `crewai.hooks` exports `before_tool_call`, `register_before_tool_call_hook`
and `ToolCallHookContext`, and returning False from a before-hook aborts the call.

The contract this file depends on, all of it read from that wheel:
  * hook signature is `(context: ToolCallHookContext) -> bool | None`
  * returning False BLOCKS the tool call
  * `context.tool_name` is the tool's name, `context.tool_input` is a mutable dict
  * the decorator takes `tools=[...]` to scope which tools it fires for

WHY FAIL-CLOSED IS THE DEFAULT
------------------------------
This gate sits in front of "connect to an unfamiliar MCP server". If a failed
check lets the call through, there is no gate -- an attacker who can make the
check fail has removed it, and the failure modes that matter (timeout, 429, an
expired key) are all cheap to cause. So ALLOW is the only action that proceeds,
and DENY, REVIEW and DEFER all block.

That couples the agent's availability to ours, which is a real cost and someone
else's call to make. `fail_open=True` inverts it for DEFER only: a check that
could not be COMPLETED stops blocking, while a check that completed and said
REVIEW still blocks. Never make FINDING fail open; that is not a configuration,
it is turning the product off.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from .core import (
    CheckState,
    GateAction,
    GateDecision,
    check_with_retry,
    evaluate_gate_policy,
    record_gate_decision,
)

logger = logging.getLogger("relayshield.gate")

# Tools whose arguments name something the agent is about to trust. A gate on
# every tool is a gate nobody keeps switched on.
DEFAULT_PROTECTED_TOOLS: tuple[str, ...] = (
    "connect_mcp_server",
    "add_mcp_server",
    "install_package",
    "install_tool",
    "load_plugin",
)

# Where the target hides in tool_input, in the order we look. A tool we do not
# recognise the shape of is reported as such rather than waved through.
_TARGET_KEYS_URL = ("server_url", "url", "endpoint", "mcp_url", "server")
_TARGET_KEYS_PKG = ("package_name", "package", "name", "tool_name", "plugin")


def extract_target(tool_input: dict) -> tuple[str | None, str | None]:
    """(server_url, package_name) from a tool's arguments. Pure, so the messy
    part is testable without CrewAI or a network."""
    if not isinstance(tool_input, dict):
        return None, None
    url = pkg = None
    for k in _TARGET_KEYS_URL:
        v = tool_input.get(k)
        if isinstance(v, str) and v.strip():
            url = v.strip()
            break
    for k in _TARGET_KEYS_PKG:
        v = tool_input.get(k)
        if isinstance(v, str) and v.strip():
            pkg = v.strip()
            break
    # A bare "name" that is really a URL is a URL.
    if pkg and not url and pkg.startswith(("http://", "https://")):
        url, pkg = pkg, None
    return url, pkg


def decide(
    tool_input: dict,
    *,
    api_key: str | None = None,
    api_base: str | None = None,
    timeout: float = 8.0,
    fail_open: bool = False,
) -> tuple[bool, GateDecision]:
    """(allowed, decision). No CrewAI import, so the whole decision path is
    testable on its own."""
    server_url, package_name = extract_target(tool_input)

    if not server_url and not package_name:
        # We could not find a target in the arguments. That is not clean.
        decision = evaluate_gate_policy(CheckState.MISSING)
        record_gate_decision({"tool_input_keys": sorted(tool_input or {})}, decision)
        return (True if fail_open else False), decision

    state, result, _err = check_with_retry(
        server_url=server_url, package_name=package_name,
        api_key=api_key, api_base=api_base, timeout=timeout,
    )
    decision = evaluate_gate_policy(state, result)
    record_gate_decision({"server_url": server_url, "package_name": package_name}, decision)

    if decision.action is GateAction.ALLOW:
        return True, decision
    if fail_open and decision.action is GateAction.DEFER:
        # The check could not be completed. A completed REVIEW still blocks, and
        # a FINDING always blocks, whatever this flag says.
        logger.warning("relayshield_gate fail_open: allowing on %s", decision.reason_codes)
        return True, decision
    return False, decision


def build_hook(
    *,
    api_key: str | None = None,
    api_base: str | None = None,
    timeout: float = 8.0,
    fail_open: bool = False,
    on_block: Callable[[GateDecision], None] | None = None,
) -> Callable:
    """A callable with CrewAI's before-hook signature. Returns False to block."""

    def relayshield_gate(context) -> bool | None:
        allowed, decision = decide(
            dict(getattr(context, "tool_input", {}) or {}),
            api_key=api_key, api_base=api_base, timeout=timeout, fail_open=fail_open,
        )
        if allowed:
            return None                     # None means "no opinion, carry on"
        if on_block:
            on_block(decision)
        else:
            logger.error(
                "RelayShield blocked %s: %s (%s)",
                getattr(context, "tool_name", "?"),
                decision.action.value, ", ".join(decision.reason_codes),
            )
        return False                        # False aborts the tool call

    relayshield_gate.__name__ = "relayshield_gate"
    return relayshield_gate


def install(
    tools: Sequence[str] | None = None,
    *,
    api_key: str | None = None,
    api_base: str | None = None,
    timeout: float = 8.0,
    fail_open: bool = False,
    on_block: Callable[[GateDecision], None] | None = None,
):
    """Register the gate with CrewAI's global before_tool_call hooks.

        from crewai_relayshield import install
        install()

    Imports crewai lazily so that `core` and `decide` stay usable, and testable,
    without the framework installed.
    """
    try:
        from crewai.hooks import register_before_tool_call_hook
    except ImportError as exc:                                  # pragma: no cover
        raise ImportError(
            "crewai-relayshield's install() needs crewai>=1.15. The gate logic in "
            "crewai_relayshield.decide() works without it."
        ) from exc

    hook = build_hook(api_key=api_key, api_base=api_base, timeout=timeout,
                      fail_open=fail_open, on_block=on_block)
    names = tuple(tools) if tools is not None else DEFAULT_PROTECTED_TOOLS

    def scoped(context) -> bool | None:
        if getattr(context, "tool_name", None) not in names:
            return None
        return hook(context)

    scoped.__name__ = "relayshield_gate"
    register_before_tool_call_hook(scoped)
    logger.info("RelayShield gate registered for tools: %s", ", ".join(names))
    return scoped
