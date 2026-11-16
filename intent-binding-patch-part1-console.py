#!/usr/bin/env python3
"""Patch Part 1b, Gateway persistence plus console verdict display.

For review before apply. Idempotent, no deploy in this script.
Files, Mac:
- /Users/andrewgibbs/dev/relayshield/relayshield_api.py
  * Add _DynamoBindingStore.record_verdict, after consume, before
    _corpus_screen_result. Writes last_verdict, last_policy_action,
    last_system_outcome, last_verdict_id, last_settled_at as separate
    DynamoDB item attributes, never inside the signed record, with
    a tenant condition. Does not touch record, signature, consumed.
  * In _settle_core, after the verdict mapping, call record_verdict
    best-effort, log on failure, do not fail the settle decision.
- /Users/andrewgibbs/dev/relayshield-mcp-proxyfw/cloudflare_worker_mcpfw_api.js
  * In handleIntentBindings row mapping, parse item.record JSON
    for payer, counterparty, amount_minor, currency, rail, and read
    last_verdict fields, with not_settled fallback.
- /Users/andrewgibbs/dev/relayshield-mcp-proxyfw/mcp-firewall-console.html
  * In intent binding detail, add Verdict, Policy action, System
    outcome rows after the Verdicts row.

Run, then review with git diff in each repo, before commit/deploy.
After console edits, run python3 build.py in the console directory
to regenerate cloudflare_worker_mcpfw.js. Do not edit that file.
"""

import pathlib
import sys

def patch(path, old, new, label):
    text = pathlib.Path(path).read_text()
    if new.strip()[:60] in text:
        print(f"{label}: already present, skipped.")
        return
    if old not in text:
        print(f"{label}: OLD not found, no change.")
        sys.exit(1)
    if text.count(old) != 1:
        print(f"{label}: OLD found more than once, no change.")
        sys.exit(1)
    pathlib.Path(path).write_text(text.replace(old, new, 1))
    print(f"{label}: patched.")

API = "/Users/andrewgibbs/dev/relayshield/relayshield_api.py"

patch(API,
"""            raise


def _corpus_screen_result""",
"""            raise

    def record_verdict(self, binding_id, verdict, policy_action,
                       system_outcome, verdict_id):
        try:
            self._table.update_item(
                Key={"binding_id": binding_id},
                UpdateExpression=(
                    "SET last_verdict = :v, last_policy_action = :p, "
                    "last_system_outcome = :s, last_verdict_id = :id, "
                    "last_settled_at = :now"),
                ConditionExpression="tenant_id = :tenant",
                ExpressionAttributeValues={
                    ":v": verdict,
                    ":p": policy_action,
                    ":s": system_outcome,
                    ":id": verdict_id,
                    ":tenant": self._tenant_id,
                    ":now": int(time.time()),
                },
            )
        except Exception as exc:
            if _fx_cond_code(exc) == "ConditionalCheckFailedException":
                return False
            raise
        return True


def _corpus_screen_result""",
"Gateway record_verdict")

patch(API,
"""    data["verdict_id"] = "verdict_" + (decision.binding_id or binding_id)
    return _ok(data)""",
"""    data["verdict_id"] = "verdict_" + (decision.binding_id or binding_id)
    try:
        store = getattr(binder, "_store", None)
        if store is not None and hasattr(store, "record_verdict"):
            store.record_verdict(
                decision.binding_id or binding_id, verdict,
                policy_action, system_outcome, data["verdict_id"])
    except Exception as exc:
        logger.exception("intent verdict persistence failed: %s", exc)
    return _ok(data)""",
"Gateway settle persistence call")

WORKER = "/Users/andrewgibbs/dev/relayshield-mcp-proxyfw/cloudflare_worker_mcpfw_api.js"

patch(WORKER,
"""        const amountMinor = item.amount_minor?.N ? parseInt(item.amount_minor.N, 10) : 0;
        return {
          binding_id: item.binding_id?.S || "",
          payer: item.payer?.S || "",
          counterparty: item.counterparty?.S || "",
          amount: (amountMinor / 100).toFixed(2),
          amount_minor: amountMinor,
          currency: item.currency?.S || "USD",
          rail: item.id_policy?.S || "",
          step_up: { required: stepUp.required?.BOOL || false, triggers },
          verdict_summary: verdictParts.length ? verdictParts.join(". ") + "." : "No verdicts recorded.",
          consumed: item.consumed?.BOOL || false,""",
"""        let recordJson = {};
        try { recordJson = JSON.parse(item.record?.S || "{}"); } catch (e) { recordJson = {}; }
        const amountMinor = item.amount_minor?.N ? parseInt(item.amount_minor.N, 10) : (recordJson.amount_minor || 0);
        return {
          binding_id: item.binding_id?.S || "",
          payer: item.payer?.S || recordJson.payer || "",
          counterparty: item.counterparty?.S || recordJson.counterparty || "",
          amount: (amountMinor / 100).toFixed(2),
          amount_minor: amountMinor,
          currency: item.currency?.S || recordJson.currency || "USD",
          rail: item.id_policy?.S || recordJson.id_policy || "",
          step_up: { required: stepUp.required?.BOOL || false, triggers },
          verdict_summary: verdictParts.length ? verdictParts.join(". ") + "." : "No verdicts recorded.",
          verdict: item.last_verdict?.S || "not_settled",
          policy_action: item.last_policy_action?.S || "none",
          system_outcome: item.last_system_outcome?.S || "not_completed",
          verdict_id: item.last_verdict_id?.S || "",
          consumed: item.consumed?.BOOL || false,""",
"Console API verdict row")

HTML = "/Users/andrewgibbs/dev/relayshield-mcp-proxyfw/mcp-firewall-console.html"

patch(HTML,
"""  html += "<div class=\\"kv\\"><span class=\\"k\\">Verdicts</span><span class=\\"v\\">" + escapeHtml(row.verdict_summary) + "</span></div>";""",
"""  html += "<div class=\\"kv\\"><span class=\\"k\\">Verdicts</span><span class=\\"v\\">" + escapeHtml(row.verdict_summary) + "</span></div>";
  html += "<div class=\\"kv\\"><span class=\\"k\\">Verdict</span><span class=\\"v\\">" + escapeHtml(row.verdict || "not_settled") + "</span></div>";
  html += "<div class=\\"kv\\"><span class=\\"k\\">Policy action</span><span class=\\"v\\">" + escapeHtml(row.policy_action || "none") + "</span></div>";
  html += "<div class=\\"kv\\"><span class=\\"k\\">System outcome</span><span class=\\"v\\">" + escapeHtml(row.system_outcome || "not_completed") + "</span></div>";""",
"Console panel verdict rows")

print("Part 1b patches done, review with git diff before commit or deploy.")
