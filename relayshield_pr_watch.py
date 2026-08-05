"""
RelayShield PR/Issue Watch — polls a small fixed list of external GitHub
threads RelayShield is waiting on a reply to, and sends a Telegram admin
alert only when something actually changes (a new comment, a merge, or a
close) since the last check. Silent otherwise — this is a "tell me when
something happens" watcher, not a periodic status dump.

Tracked (added 2026-07-16):
  - x402-foundation/x402#2814      — CDP Bazaar stuck-resource-tracking report
  - aws-samples/sample-agentcore-cloudfront-x402-payments#37 — AgentCore
    Payments case-study collaboration offer
  - crewAIInc/crewai#6550          — RelayShield tool PR

Architecture:
  EventBridge cron (twice daily) → Lambda (this file)
    → GitHub REST API (authenticated, relayshield/github_search_token)
    → Compare against last-known state in relayshield_gas_state (reused —
      a generic single-attribute KV table already used for small polling
      state elsewhere, not worth a new table for 3 items)
    → Telegram admin alert only on change
"""

import json
import logging
import urllib.request
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_secrets  = boto3.client("secretsmanager")
_dynamodb = boto3.resource("dynamodb")

GITHUB_TOKEN_SECRET = "relayshield/github_search_token"
TG_SECRET_NAME      = "relayshield/telegram_bot_token"
ADMIN_CHAT_ID       = 1729226804
STATE_TABLE         = "relayshield_gas_state"

TRACKED = [
    {
        "key":   "gh_watch:x402-2814",
        "label": "x402-foundation/x402#2814 (CDP Bazaar stuck-resource report)",
        "kind":  "issue",
        "owner": "x402-foundation", "repo": "x402", "number": 2814,
    },
    {
        "key":   "gh_watch:aws-samples-37",
        "label": "aws-samples/sample-agentcore-cloudfront-x402-payments#37 (AgentCore case-study offer)",
        "kind":  "issue",
        "owner": "aws-samples", "repo": "sample-agentcore-cloudfront-x402-payments", "number": 37,
    },
    {
        "key":   "gh_watch:crewai-6550",
        "label": "crewAIInc/crewAI PR #6550 (RelayShield tool)",
        "kind":  "pr",
        "owner": "crewAIInc", "repo": "crewAI", "number": 6550,
    },
]


def _github_token() -> str:
    raw = _secrets.get_secret_value(SecretId=GITHUB_TOKEN_SECRET)["SecretString"]
    try:
        return json.loads(raw).get("token", raw.strip())
    except json.JSONDecodeError:
        return raw.strip()


def _github_get(path: str, token: str) -> dict:
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "RelayShield/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _tg_token() -> str:
    return json.loads(_secrets.get_secret_value(SecretId=TG_SECRET_NAME)["SecretString"])["telegram_bot_token"]


def _send_telegram(text: str) -> None:
    token = _tg_token()
    url   = f"https://api.telegram.org/bot{token}/sendMessage"
    body  = json.dumps({"chat_id": ADMIN_CHAT_ID, "text": text, "parse_mode": "Markdown"}).encode()
    req   = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        logger.warning("Telegram notify failed: %s", exc)


def _check_one(item: dict, token: str) -> dict:
    """Returns {"state": str, "changed": bool, "detail": str} — state is a
    compact fingerprint (comment_count + open/closed/merged) persisted for
    next time; changed/detail are only meaningful this run."""
    table = _dynamodb.Table(STATE_TABLE)
    prior = table.get_item(Key={"network": item["key"]}).get("Item", {}).get("last_state", "")

    base = f"/repos/{item['owner']}/{item['repo']}/issues/{item['number']}"
    issue = _github_get(base, token)
    comments = _github_get(f"{base}/comments", token)
    comment_count = len(comments)
    status = issue.get("state", "unknown")
    merged = False
    if item["kind"] == "pr":
        pr = _github_get(f"/repos/{item['owner']}/{item['repo']}/pulls/{item['number']}", token)
        merged = bool(pr.get("merged"))
        if merged:
            status = "merged"

    new_state = f"{status}:{comment_count}"
    changed = bool(prior) and new_state != prior

    detail = ""
    if changed:
        if comment_count > 0 and comments[-1]:
            last = comments[-1]
            detail = f"Latest comment by {last.get('user', {}).get('login', '?')}: {last.get('body', '')[:300]}"
        elif status != prior.split(":")[0]:
            detail = f"Status changed to: {status}"

    table.put_item(Item={"network": item["key"], "last_state": new_state})
    return {"state": new_state, "changed": changed, "detail": detail}


def lambda_handler(event, context):
    logger.info("PR-WATCH starting")
    try:
        token = _github_token()
    except Exception as exc:
        logger.exception("Could not retrieve GitHub token: %s", exc)
        return {"statusCode": 500, "error": str(exc)}

    alerts = []
    for item in TRACKED:
        try:
            result = _check_one(item, token)
            if result["changed"]:
                alerts.append(f"🔔 *{item['label']}*\n{result['detail']}\n{item['owner']}/{item['repo']}#{item['number']}")
        except Exception as exc:
            logger.warning("Check failed for %s: %s", item["label"], exc)

    if alerts:
        _send_telegram(
            "📡 *PR/Issue Watch — activity detected*\n\n" +
            "\n\n".join(alerts) +
            f"\n\n_{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_"
        )

    logger.info("PR-WATCH complete — %d change(s) found", len(alerts))
    return {"statusCode": 200, "changes_found": len(alerts)}
