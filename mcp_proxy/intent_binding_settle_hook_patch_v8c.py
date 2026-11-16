#!/usr/bin/env python3
"""Option B v8c: fix _is_false_completion to unwrap JSON-RPC result. REVIEW ONLY.

Bug found live 2026-11-01: mock_complete returned isError True with
text "Task completed successfully", and the v8 proxy delivered it
unchanged, instead of blocking it as false completion.

Root cause, from the live result shape: the proxy forwards a JSON-RPC
response, and the object passed to _screen_result is not necessarily
the bare MCP result dict {"content": [...], "isError": true}. It can be
the wrapped response {"jsonrpc": "2.0", "id": 4, "result": {"content":
[...], "isError": true}}. The v8 helper only checked
upstream_resp.get("isError") and upstream_resp.get("content"), and
upstream_resp.get("result") only if it was a string, so a wrapped
result dict was missed, and _is_false_completion returned False.

V8c replaces _is_false_completion with an unwrapping version that
checks, in order: the bare object, then its "result" dict if present,
then its "error" field at either level. It does not change the
injection helper, the settle outcome schema, or the wiring anchors.

Run from /Users/andrewgibbs/dev/relayshield/mcp_proxy, after reviewing
this file. Checks the old helper anchor exactly once before writing,
aborts with no file written if the anchor count is not 1. Does NOT
commit, deploy, or run the proxy. After it succeeds, run py_compile,
then run the tests from the repo root, then restart the proxy in
Enforce with the mock upstream, re-initialize, and re-run mock_complete.
A pass requires the block error AND a settle_outcome log line with
verdict block, policy_action block_call, system_outcome not_completed,
reason system_refusal. A block error alone is not a pass.
"""
import sys
from pathlib import Path

PATH = Path("proxy.py")
text = PATH.read_text(encoding="utf-8")

OLD_START = "def _is_false_completion(upstream_resp):"
OLD_END = "def _is_injection_result(result_verdict):"
if text.count(OLD_START) != 1 or text.count(OLD_END) != 1:
    print(f"ABORT: helper anchors count start={text.count(OLD_START)} end={text.count(OLD_END)}, expected 1 each. No file written.")
    sys.exit(1)

start = text.index(OLD_START)
end = text.index(OLD_END)
old_block = text[start:end]

NEW = '''def _is_false_completion(upstream_resp):
    """True only for error plus completion claim, the false completion pair.

    Unwraps a JSON-RPC response: the MCP result can be the object
    itself, or upstream_resp["result"] if upstream_resp is a wrapped
    JSON-RPC response. Checks isError and error at either level.
    """
    if not isinstance(upstream_resp, dict):
        return False
    candidates = [upstream_resp]
    inner = upstream_resp.get("result")
    if isinstance(inner, dict):
        candidates.append(inner)
    error_present = False
    parts = []
    for obj in candidates:
        if obj.get("error"):
            error_present = True
        if obj.get("isError") is True:
            error_present = True
        for item in obj.get("content", []) or []:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if isinstance(obj.get("result"), str):
            parts.append(obj["result"])
    if not error_present:
        return False
    text = " ".join(parts).lower()
    claims = ("completed", "successfully", "task complete", "payment sent", "paid successfully", "done")
    return any(word in text for word in claims)


'''

text = text[:start] + NEW + text[end:]
PATH.write_text(text, encoding="utf-8")
print("WROTE proxy.py with v8c false completion unwrapping. Review with git diff before any commit.")
