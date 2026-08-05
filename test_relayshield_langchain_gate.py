"""
Acceptance suite for relayshield_langchain_gate.py.

Per John6666's framing: these tests assert on the *protected action*
(whether handler() -- the real MCP connect/install -- was invoked), not
merely on the returned label. That is the difference between an advisory
tool and an enforceable policy boundary.

Requires: pip install langchain langchain-core langgraph
Run: pytest test_relayshield_langchain_gate.py -v
"""

from unittest.mock import patch

import pytest
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from relayshield_langchain_gate import (
    CheckResult,
    CheckState,
    RelayShieldCheckError,
    RelayShieldMCPGateMiddleware,
)


def _make_request(tool_name="connect_mcp_server", server_url="https://example-mcp-server.test"):
    return ToolCallRequest(
        tool_call={"name": tool_name, "args": {"server_url": server_url}, "id": "call_1"},
        tool=None,
        state={},
        runtime=None,
    )


def _run_gate(mock_return):
    """mock_return: either (state, CheckResult, None) success tuple, or a
    RelayShieldCheckError to be raised."""
    middleware = RelayShieldMCPGateMiddleware()
    request = _make_request()
    handler_called = {"value": False}

    def handler(req):
        handler_called["value"] = True
        return ToolMessage(content="connected", name=req.tool_call["name"], tool_call_id=req.tool_call["id"])

    with patch("relayshield_langchain_gate.check_mcp_registry_risk_with_retry") as mock_check:
        if isinstance(mock_return, RelayShieldCheckError):
            mock_check.return_value = (CheckState(mock_return.kind), None, mock_return)
        else:
            mock_check.return_value = mock_return
        result = middleware.wrap_tool_call(request, handler)
    return handler_called["value"], result


def test_synthetic_known_risk_server_blocks_connection():
    result = CheckResult(state=CheckState.FINDING, verdict="CRITICAL", findings=[{"type": "typosquat_suspected"}])
    called, msg = _run_gate((CheckState.FINDING, result, None))
    assert called is False
    assert msg.status == "error"


def test_benign_fresh_sufficient_coverage_allows():
    result = CheckResult(state=CheckState.NO_KNOWN_FINDING, verdict="LOW")
    called, _ = _run_gate((CheckState.NO_KNOWN_FINDING, result, None))
    assert called is True


def test_no_known_finding_with_partial_coverage_reviews_not_allows():
    result = CheckResult(state=CheckState.PARTIAL, verdict="LOW")
    called, _ = _run_gate((CheckState.PARTIAL, result, None))
    assert called is False


def test_stale_result_defers_to_review():
    result = CheckResult(state=CheckState.STALE, verdict="LOW")
    called, _ = _run_gate((CheckState.STALE, result, None))
    assert called is False


def test_401_blocks_protected_action():
    called, _ = _run_gate(RelayShieldCheckError("auth_failure", status=401))
    assert called is False


def test_429_defers_no_false_allow():
    called, _ = _run_gate(RelayShieldCheckError("upstream_failure", status=429))
    assert called is False


def test_500_blocks_protected_action():
    called, _ = _run_gate(RelayShieldCheckError("upstream_failure", status=500))
    assert called is False


def test_malformed_response_blocks_protected_action():
    called, _ = _run_gate(RelayShieldCheckError("malformed", detail="invalid JSON"))
    assert called is False


def test_network_disconnect_blocks_protected_action():
    called, _ = _run_gate(RelayShieldCheckError("upstream_failure", detail="connection refused"))
    assert called is False


def test_402_payment_required_defers_no_protected_action_yet():
    called, _ = _run_gate(RelayShieldCheckError("payment_required", status=402))
    assert called is False


def test_gate_internal_exception_blocks_protected_action_not_allow():
    """A raised exception inside the gate must not silently become allow."""
    middleware = RelayShieldMCPGateMiddleware()
    request = _make_request()
    handler_called = {"value": False}

    def handler(req):
        handler_called["value"] = True
        return ToolMessage(content="connected", name=req.tool_call["name"], tool_call_id=req.tool_call["id"])

    with patch("relayshield_langchain_gate.check_mcp_registry_risk_with_retry", side_effect=RuntimeError("boom")):
        result = middleware.wrap_tool_call(request, handler)
    assert handler_called["value"] is False
    assert result.status == "error"


def test_unrelated_tool_is_unaffected_by_gate():
    middleware = RelayShieldMCPGateMiddleware()
    request = ToolCallRequest(
        tool_call={"name": "read_local_file", "args": {"path": "/tmp/x"}, "id": "call_2"},
        tool=None,
        state={},
        runtime=None,
    )
    handler_called = {"value": False}

    def handler(req):
        handler_called["value"] = True
        return ToolMessage(content="ok", name=req.tool_call["name"], tool_call_id=req.tool_call["id"])

    with patch("relayshield_langchain_gate.check_mcp_registry_risk_with_retry") as mock_check:
        result = middleware.wrap_tool_call(request, handler)
    mock_check.assert_not_called()
    assert handler_called["value"] is True


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
