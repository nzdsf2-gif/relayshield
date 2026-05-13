"""
RelayShield TON Activity Monitor Lambda

Monitors TON (The Open Network) wallets for new transaction activity every 15 minutes.
Sends a Telegram alert whenever new transactions are detected on a
monitored TON wallet.

Trigger: EventBridge schedule — every 15 minutes
DynamoDB tables:
  relayshield_monitored_wallets  — wallet_address, user_id, chain_type, last_seen_lt
  relayshield_users              — user_id → telegram_chat_id

Secrets:
  relayshield/telegram_bot_token — {"telegram_bot_token": "..."}

How it works:
  1. Scan relayshield_monitored_wallets for chain_type == "ton"
  2. For each wallet, call TON Center API getTransactions
  3. Compare against stored last_seen_lt (logical time) to detect new txs
  4. Alert via Telegram with transaction summary
  5. Update last_seen_lt in DynamoDB

TON Center API: https://toncenter.com/api/v2/
  - Free tier: 1 req/sec
  - getTransactions?address=...&limit=5

Note: TON Center API key can be obtained from @tonapibot on Telegram.
Store as: relayshield/toncenter_api_key → {"api_key": "..."}
Without an API key the free tier is rate-limited to 1 req/sec which is
sufficient for a small user base.
"""

import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

secrets_client = boto3.client("secretsmanager")
dynamodb       = boto3.resource("dynamodb")

MONITORED_WALLETS_TABLE = "relayshield_monitored_wallets"
USERS_TABLE             = "relayshield_users"
TG_SECRET_NAME          = "relayshield/telegram_bot_token"
TONCENTER_SECRET_NAME   = "relayshield/toncenter_api_key"
TELEGRAM_API_BASE       = "https://api.telegram.org/bot{token}/{method}"

TONCENTER_BASE_URL = "https://toncenter.com/api/v2"
TX_LIMIT           = 5   # transactions to fetch per wallet per poll

_secret_cache: dict[str, str] = {}


def _get_secret(name: str) -> str:
    if name not in _secret_cache:
        _secret_cache[name] = secrets_client.get_secret_value(
            SecretId=name
        )["SecretString"].strip()
    return _secret_cache[name]


def _get_secret_json(name: str, key: str) -> str:
    return json.loads(_get_secret(name))[key]


def _tg_token() -> str:
    return _get_secret_json(TG_SECRET_NAME, "telegram_bot_token")


def _toncenter_api_key() -> str | None:
    """Return TON Center API key, or None if not configured."""
    try:
        return _get_secret_json(TONCENTER_SECRET_NAME, "api_key")
    except Exception:
        return None


def _send_telegram(chat_id: int, text: str) -> None:
    token = _tg_token()
    url   = TELEGRAM_API_BASE.format(token=token, method="sendMessage")
    body  = json.dumps({
        "chat_id":    chat_id,
        "text":       text,
        "parse_mode": "Markdown",
    }).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        logger.error("Telegram send failed chat_id=%s: %s", chat_id, exc)


def _get_recent_transactions(address: str) -> list[dict]:
    """Return up to TX_LIMIT recent transactions for a TON wallet via TON Center API."""
    params: dict = {"address": address, "limit": TX_LIMIT}
    api_key = _toncenter_api_key()
    if api_key:
        params["api_key"] = api_key

    url = f"{TONCENTER_BASE_URL}/getTransactions?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        if not data.get("ok"):
            logger.warning("TON Center error for wallet=%s: %s", address, data.get("error"))
            return []
        return data.get("result", [])
    except Exception as exc:
        logger.error("TON getTransactions failed wallet=%s: %s", address, exc)
        return []


def _get_all_ton_wallets() -> list[dict]:
    table  = dynamodb.Table(MONITORED_WALLETS_TABLE)
    items  = []
    kwargs: dict = {"FilterExpression": Attr("chain_type").eq("ton")}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return items


def _update_last_seen_lt(address: str, lt: str) -> None:
    """Store the logical time (lt) of the newest seen transaction."""
    try:
        dynamodb.Table(MONITORED_WALLETS_TABLE).update_item(
            Key={"wallet_address": address},
            UpdateExpression="SET last_seen_lt = :lt, last_checked_at = :t",
            ExpressionAttributeValues={
                ":lt": lt,
                ":t":  datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:
        logger.error("Failed to update last_seen_lt wallet=%s: %s", address, exc)


def _get_user(user_id: str) -> dict | None:
    resp = dynamodb.Table(USERS_TABLE).get_item(Key={"user_id": user_id})
    return resp.get("Item")


def _ton_value_to_toncoin(nano: int | str) -> str:
    """Convert nanoton (int string) to TON with 4 decimal places."""
    try:
        val = int(nano) / 1e9
        return f"{val:.4f} TON"
    except Exception:
        return "? TON"


def _format_activity_alert(address: str, new_txs: list[dict]) -> str:
    short  = f"{address[:6]}...{address[-4:]}"
    count  = len(new_txs)
    tx_word = "transaction" if count == 1 else "transactions"

    lines = [
        f"🔔 *TON Wallet Activity*\n",
        f"*Wallet:* `{short}`",
        f"*New {tx_word} detected:* {count}\n",
    ]

    for tx in new_txs[:3]:
        in_msg = tx.get("in_msg", {})
        value  = in_msg.get("value", 0)
        src    = in_msg.get("source", "")
        # Outgoing transactions have value=0 in in_msg
        if value and int(value) > 0:
            src_short = f"{src[:6]}...{src[-4:]}" if len(src) > 12 else (src or "?")
            lines.append(f"• ⬇️ Received {_ton_value_to_toncoin(value)} from `{src_short}`")
        else:
            # Outbound — check out_msgs
            out_msgs = tx.get("out_msgs", [])
            if out_msgs:
                out_val = out_msgs[0].get("value", 0)
                dst     = out_msgs[0].get("destination", "")
                dst_short = f"{dst[:6]}...{dst[-4:]}" if len(dst) > 12 else (dst or "?")
                lines.append(f"• ⬆️ Sent {_ton_value_to_toncoin(out_val)} to `{dst_short}`")
            else:
                lines.append("• Smart contract interaction")

    if count > 3:
        lines.append(f"  _...and {count - 3} more_")

    lines.append(
        f"\n[View on Tonscan](https://tonscan.org/address/{address})\n\n"
        f"_RelayShield Crypto Shield_"
    )
    return "\n".join(lines)


def lambda_handler(event: dict, context) -> dict:
    wallets = _get_all_ton_wallets()
    logger.info("TON monitor — checking %d wallets", len(wallets))

    for wallet_item in wallets:
        address      = wallet_item.get("wallet_address", "")
        user_id      = wallet_item.get("user_id")
        last_seen_lt = wallet_item.get("last_seen_lt")

        if not address or not user_id:
            continue

        txs = _get_recent_transactions(address)
        if not txs:
            continue

        # TON transactions are ordered newest-first; lt is the logical time (unique per tx)
        latest_lt = str(txs[0].get("transaction_id", {}).get("lt", ""))

        if last_seen_lt is None:
            # First run — record the latest lt without alerting
            logger.info("TON first run — wallet=%s lt=%s", address, latest_lt)
            if latest_lt:
                _update_last_seen_lt(address, latest_lt)
            continue

        # Find all transactions newer than last_seen_lt
        new_txs = []
        for tx in txs:
            tx_lt = str(tx.get("transaction_id", {}).get("lt", ""))
            if tx_lt == last_seen_lt:
                break
            new_txs.append(tx)

        if not new_txs:
            logger.info("TON no new txs — wallet=%s", address)
            continue

        logger.info("TON new txs — wallet=%s count=%d", address, len(new_txs))

        user = _get_user(user_id)
        if not user:
            continue
        chat_id = user.get("telegram_chat_id")
        if not chat_id:
            continue

        alert = _format_activity_alert(address, new_txs)
        _send_telegram(int(chat_id), alert)
        _update_last_seen_lt(address, latest_lt)
        logger.info("TON alert sent — wallet=%s new_txs=%d", address, len(new_txs))

    return {"statusCode": 200, "body": "ok"}
