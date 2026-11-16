#!/usr/bin/env python3
"""Patch Part 1, Gateway only, for review before apply, version 2.

Applies to: /Users/andrewgibbs/dev/relayshield/relayshield_api.py
Target: _settle_core, at line 18254 on main, October 31, 2026.
Anchor, confirmed from Mac extraction, line 18301:
    data["step_up"] = binding.record.get("step_up") or {}
followed by:
    return _ok(data)
Change: add verdict, policy_action, system_outcome, verdict_id to
the settle response, without changing decision, reason_codes,
reasons, binding_id, or step_up.
Idempotent: if verdict is already added in _settle_core, it exits
without changing the file. Run, then review with git diff, before
any commit or deploy. No deploy in this script.
"""

import pathlib
import sys

PATH = pathlib.Path("/Users/andrewgibbs/dev/relayshield/relayshield_api.py")

OLD = """        data["step_up"] = binding.record.get("step_up") or {}
    return _ok(data)"""

NEW = """        data["step_up"] = binding.record.get("step_up") or {}
    decision_text = str(decision.decision or "").lower()
    reason_list = [str(r) for r in decision.reason_codes]
    if decision_text == "allow":
        verdict = "pass"
        policy_action = "allow"
        system_outcome = "completed"
    elif any("ALREADY_CONSUMED" in r for r in reason_list):
        verdict = "block"
        policy_action = "block_call"
        system_outcome = "not_completed"
    else:
        verdict = "block"
        policy_action = "block_call"
        system_outcome = "blocked"
    data["verdict"] = verdict
    data["policy_action"] = policy_action
    data["system_outcome"] = system_outcome
    data["verdict_id"] = "verdict_" + (decision.binding_id or binding_id)
    return _ok(data)"""

text = PATH.read_text()
if 'data["verdict"] = verdict' in text:
    print("Already patched, no change made.")
    sys.exit(0)
if OLD not in text:
    print("OLD block not found, no change made. Check _settle_core on main.")
    sys.exit(1)
if text.count(OLD) != 1:
    print("OLD block found more than once, no change made.")
    sys.exit(1)
PATH.write_text(text.replace(OLD, NEW, 1))
print("Patched _settle_core, review with git diff before commit or deploy.")
