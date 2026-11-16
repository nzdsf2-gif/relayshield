#!/usr/bin/env python3
"""Patch Part 1b fix, October 31, 2026.

Fixes two skips in the first Part 1b script, where the
already-present check matched the first line of the new block
instead of the new code itself, so it skipped two inserts:
1. Gateway settle persistence call, store.record_verdict.
2. Console panel Verdict, Policy action, System outcome rows.

Idempotent, checks for the actual new code, not the anchor.
No deploy in this script. Review with git diff before commit.
"""

import pathlib
import sys

API = pathlib.Path("/Users/andrewgibbs/dev/relayshield/relayshield_api.py")
text = API.read_text()
if "store.record_verdict" in text:
    print("Gateway persistence call: already present, skipped.")
else:
    old = """    data["verdict_id"] = "verdict_" + (decision.binding_id or binding_id)
    return _ok(data)"""
    new = """    data["verdict_id"] = "verdict_" + (decision.binding_id or binding_id)
    try:
        store = getattr(binder, "_store", None)
        if store is not None and hasattr(store, "record_verdict"):
            store.record_verdict(
                decision.binding_id or binding_id, verdict,
                policy_action, system_outcome, data["verdict_id"])
    except Exception as exc:
        logger.exception("intent verdict persistence failed: %s", exc)
    return _ok(data)"""
    if old not in text or text.count(old) != 1:
        print("Gateway persistence call: OLD not found exactly once, no change.")
        sys.exit(1)
    API.write_text(text.replace(old, new, 1))
    print("Gateway persistence call: patched.")

HTML = pathlib.Path("/Users/andrewgibbs/dev/relayshield-mcp-proxyfw/mcp-firewall-console.html")
htext = HTML.read_text()
if "Policy action" in htext and "System outcome" in htext:
    print("Console panel verdict rows: already present, skipped.")
else:
    old = """  html += "<div class=\\"kv\\"><span class=\\"k\\">Verdicts</span><span class=\\"v\\">" + escapeHtml(row.verdict_summary) + "</span></div>";"""
    new = old + """
  html += "<div class=\\"kv\\"><span class=\\"k\\">Verdict</span><span class=\\"v\\">" + escapeHtml(row.verdict || "not_settled") + "</span></div>";
  html += "<div class=\\"kv\\"><span class=\\"k\\">Policy action</span><span class=\\"v\\">" + escapeHtml(row.policy_action || "none") + "</span></div>";
  html += "<div class=\\"kv\\"><span class=\\"k\\">System outcome</span><span class=\\"v\\">" + escapeHtml(row.system_outcome || "not_completed") + "</span></div>";"""
    if old not in htext or htext.count(old) != 1:
        print("Console panel verdict rows: OLD not found exactly once, no change.")
        sys.exit(1)
    HTML.write_text(htext.replace(old, new, 1))
    print("Console panel verdict rows: patched.")

print("Part 1b fix done, review with git diff before commit or deploy.")
