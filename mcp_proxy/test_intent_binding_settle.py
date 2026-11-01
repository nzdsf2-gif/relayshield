"""Unit tests for Option B v8 settle hook, for the Mac tree.

Place this file in /Users/andrewgibbs/dev/relayshield/mcp_proxy, next to proxy.py,
after applying intent_binding_settle_hook_patch_v8.py, then run:
python3 -m pytest test_intent_binding_settle.py -q

These tests do NOT start a proxy, do NOT call the Gateway, and do NOT
require a passport. They test only the pure helpers
_is_false_completion, _is_injection_result, and _settle_result_outcome.
If v8 is not applied, the import will fail, which is the correct signal.
"""
from mcp_proxy.proxy import (
    _is_false_completion,
    _is_injection_result,
    _settle_result_outcome,
)


def test_false_completion_error_plus_claim():
    resp = {"isError": True, "content": [{"type": "text", "text": "Task completed successfully"}]}
    assert _is_false_completion(resp) is True
    out = _settle_result_outcome(resp, {"verdict": "clean"})
    assert out["verdict"] == "block"
    assert out["policy_action"] == "block_call"
    assert out["system_outcome"] == "not_completed"
    assert out["reason"] == "system_refusal"


def test_error_without_claim_is_not_false_completion():
    resp = {"isError": True, "content": [{"type": "text", "text": "Upstream refused: policy block"}]}
    assert _is_false_completion(resp) is False


def test_completion_without_error_is_not_false_completion():
    resp = {"isError": False, "content": [{"type": "text", "text": "Task completed successfully"}]}
    assert _is_false_completion(resp) is False


def test_injection_flagged_by_category():
    verdict = {"verdict": "flagged", "poison_category": "prompt_injection", "reasons": ["prompt injection in result"]}
    assert _is_injection_result(verdict) is True
    out = _settle_result_outcome({"isError": False, "content": []}, verdict)
    assert out["verdict"] == "quarantine"
    assert out["policy_action"] == "quarantine_tool"
    assert out["system_outcome"] == "quarantined"


def test_injection_flagged_by_reason():
    verdict = {"verdict": "flagged", "poison_category": "clean", "reasons": ["data leak in tool result"]}
    assert _is_injection_result(verdict) is True


def test_flagged_ti_without_injection_is_not_quarantine():
    verdict = {"verdict": "flagged", "poison_category": "phishing", "reasons": ["known phishing url"]}
    assert _is_injection_result(verdict) is False


def test_clean_result_passes():
    resp = {"isError": False, "content": [{"type": "text", "text": "[UNKNOWN] https://example.com"}]}
    out = _settle_result_outcome(resp, {"verdict": "clean"})
    assert out["verdict"] == "pass"
    assert out["policy_action"] == "allow"
    assert out["system_outcome"] == "completed"
    assert out["reason"] is None
