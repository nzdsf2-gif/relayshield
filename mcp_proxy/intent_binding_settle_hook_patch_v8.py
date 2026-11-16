#!/usr/bin/env python3
"""Option B v8: _screen_result settle hook. REVIEW ONLY, do not commit yet.

Run from /Users/andrewgibbs/dev/relayshield/mcp_proxy, after reviewing
intent-binding-option-b-v8-settle-hook-review-2026-11-01.md.
Checks each anchor exactly once before writing, aborts with no file
written if any anchor count is not 1. Does NOT commit, deploy, or run
the proxy. After it succeeds, run py_compile and the tests, then review
git diff before any commit.

Scope, exactly:
- False completion: upstream error plus completion claim in the text
  that would be delivered -> block, block_call, not_completed,
  reason system_refusal, return refusal, not claimed completion.
- Injection: screener flagged result with injection / prompt injection /
  data leak / malicious indicator -> quarantine, quarantine_tool,
  quarantined, do not deliver, record tool quarantined for session.
- Clean: no injection, no refusal -> pass, allow, completed, deliver.
- Never consumes a TAP binding. No TAP call is made here.
- Reuses the existing hold contract: a non-None hold makes the caller
  replace the response with a block error. The settle outcome is logged
  as a JSON settle_outcome event. The caller error data fields for
  verdict / policy_action / system_outcome are a follow-up, not here.
- Quarantine records the tool in server.session_quarantined_tools.
  A future-call gate check for quarantined tools is a follow-up, not here.
"""
import sys
from pathlib import Path

PATH = Path("proxy.py")
text = PATH.read_text(encoding="utf-8")

ANCHOR_EARLY = (
    '        if result_verdict.get("verdict") != "flagged":\n'
    '            return hold\n'
)
ANCHOR_FINAL = (
    '        if quarantine.evaluate(upstream_url, evidence=evidence):\n'
    '            reputation.record_quarantine(\n'
    '                upstream_url, "auto-quarantine: poisoned neighbor")\n'
    '        return hold\n'
)

for name, anchor in (("early", ANCHOR_EARLY), ("final", ANCHOR_FINAL)):
    if text.count(anchor) != 1:
        print(f"ABORT: {name} anchor count is {text.count(anchor)}, expected 1. No file written.")
        sys.exit(1)

FALSE_COMPLETION = (
    '        # V8 settle hook, false completion: upstream error plus a\n'
    '        # completion claim in the text that would be delivered.\n'
    '        # Delivering that claim would be a false completion, the\n'
    '        # central Eon failure mode. Block it, do not deliver it,\n'
    '        # and never consume a TAP binding on a post-call block.\n'
    '        if _is_false_completion(upstream_resp):\n'
    '            _corr_key = (corr or {}).get("session_key") if isinstance(corr, dict) else None\n'
    '            _sess = None\n'
    '            if _corr_key:\n'
    '                _store = getattr(self.server, "session_bindings", None) or {}\n'
    '                _sess = _store.get(_corr_key)\n'
    '            log.warning(json.dumps({\n'
    '                "event": "settle_outcome",\n'
    '                "tool": tool_name,\n'
    '                "upstream": upstream_url,\n'
    '                "verdict": "block",\n'
    '                "policy_action": "block_call",\n'
    '                "system_outcome": "not_completed",\n'
    '                "reason": "system_refusal",\n'
    '                "binding_id": (_sess or {}).get("binding_id"),\n'
    '                "passport_id": (_sess or {}).get("passport_id"),\n'
    '            }))\n'
    '            return {"kc_result": {"verdict": "block", "sequence": {}, "reasons": ["system_refusal"]}, "evidence": [{"type": "system_refusal", "id": "false-completion", "detail": "upstream error with completion claim"}]}\n'
)

INJECTION = (
    '        # V8 settle hook, injection quarantine: a flagged result\n'
    '        # with injection / data leak / malicious indicator is not\n'
    '        # delivered, even if the existing flag path would deliver\n'
    '        # it. Quarantine the tool for this session, log the settle\n'
    '        # outcome, and never consume a TAP binding on quarantine.\n'
    '        if _is_injection_result(result_verdict):\n'
    '            _corr_key = (corr or {}).get("session_key") if isinstance(corr, dict) else None\n'
    '            _sess = None\n'
    '            if _corr_key:\n'
    '                _store = getattr(self.server, "session_bindings", None) or {}\n'
    '                _sess = _store.get(_corr_key)\n'
    '                _q = getattr(self.server, "session_quarantined_tools", None)\n'
    '                if _q is None:\n'
    '                    _q = {}\n'
    '                    self.server.session_quarantined_tools = _q\n'
    '                _q.setdefault(_corr_key, set()).add(tool_name)\n'
    '            log.warning(json.dumps({\n'
    '                "event": "settle_outcome",\n'
    '                "tool": tool_name,\n'
    '                "upstream": upstream_url,\n'
    '                "verdict": "quarantine",\n'
    '                "policy_action": "quarantine_tool",\n'
    '                "system_outcome": "quarantined",\n'
    '                "reason": "injection_or_poisoned_result",\n'
    '                "binding_id": (_sess or {}).get("binding_id"),\n'
    '                "passport_id": (_sess or {}).get("passport_id"),\n'
    '            }))\n'
    '            return {"kc_result": {"verdict": "block", "sequence": {}, "reasons": ["injection_or_poisoned_result"]}, "evidence": evidence}\n'
)

text = text.replace(ANCHOR_EARLY, FALSE_COMPLETION + ANCHOR_EARLY, 1)
# Re-check final anchor after first insertion, it should still be unique.
if text.count(ANCHOR_FINAL) != 1:
    print(f"ABORT: final anchor count after first insertion is {text.count(ANCHOR_FINAL)}, expected 1. No file written.")
    sys.exit(1)
text = text.replace(ANCHOR_FINAL, INJECTION + ANCHOR_FINAL, 1)

HELPERS = '''

def _is_false_completion(upstream_resp):
    """True only for error plus completion claim, the false completion pair."""
    if not isinstance(upstream_resp, dict):
        return False
    error_present = bool(upstream_resp.get("error")) or upstream_resp.get("isError") is True
    if not error_present:
        return False
    parts = []
    for item in upstream_resp.get("content", []) or []:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    if isinstance(upstream_resp.get("result"), str):
        parts.append(upstream_resp["result"])
    text = " ".join(parts).lower()
    claims = ("completed", "successfully", "task complete", "payment sent", "paid successfully", "done")
    return any(word in text for word in claims)


def _is_injection_result(result_verdict):
    """True for a flagged result with injection / leak / malicious signal."""
    if not isinstance(result_verdict, dict):
        return False
    if result_verdict.get("verdict") != "flagged":
        return False
    category = str(result_verdict.get("poison_category", "")).lower()
    if category in ("prompt_injection", "injection", "data_leak", "malicious"):
        return True
    reasons = " ".join(str(r) for r in result_verdict.get("reasons", [])).lower()
    return any(word in reasons for word in ("injection", "prompt injection", "data leak", "exfiltrat", "malicious indicator"))


def _settle_result_outcome(upstream_resp, result_verdict, session=None):
    """Pure settle outcome, for tests and for _screen_result logging.

    Returns a dict with verdict, policy_action, system_outcome, reason,
    or a clean pass dict. Never consumes a TAP binding.
    """
    if _is_false_completion(upstream_resp):
        return {"verdict": "block", "policy_action": "block_call", "system_outcome": "not_completed", "reason": "system_refusal"}
    if _is_injection_result(result_verdict):
        return {"verdict": "quarantine", "policy_action": "quarantine_tool", "system_outcome": "quarantined", "reason": "injection_or_poisoned_result"}
    return {"verdict": "pass", "policy_action": "allow", "system_outcome": "completed", "reason": None}
'''

if "_is_false_completion" in text:
    print("ABORT: _is_false_completion already present. No file written.")
    sys.exit(1)
text = text.rstrip() + "\n" + HELPERS
PATH.write_text(text, encoding="utf-8")
print("WROTE proxy.py with v8 settle hook. Review with git diff before any commit.")
