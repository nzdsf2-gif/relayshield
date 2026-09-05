"""RelayShield gate for CrewAI: check what an agent is about to trust, first."""

from .core import (
    CheckResult,
    CheckState,
    GateAction,
    GateDecision,
    POLICY,
    RelayShieldCheckError,
    check_mcp_registry_risk,
    check_with_retry,
    evaluate_gate_policy,
    record_gate_decision,
)
from .hook import (
    DEFAULT_PROTECTED_TOOLS,
    build_hook,
    decide,
    extract_target,
    install,
)

__version__ = "0.1.0"

__all__ = [
    "CheckResult", "CheckState", "GateAction", "GateDecision", "POLICY",
    "RelayShieldCheckError", "check_mcp_registry_risk", "check_with_retry",
    "evaluate_gate_policy", "record_gate_decision",
    "DEFAULT_PROTECTED_TOOLS", "build_hook", "decide", "extract_target", "install",
    "__version__",
]
