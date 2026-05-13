"""
RelayShield Solana Activity Monitor Lambda

Monitors Solana wallets for new transaction activity every 15 minutes.
Sends a Telegram alert whenever new transactions are detected on a
monitored Solana wallet.

Trigger: EventBridge schedule — every 15 minutes
DynamoDB tables:
  relayshield_monitored_wallets  — wallet_address, user_id, chain_type, last_seen_sig
  relayshield_users              — user_id → telegram_chat_id

Secrets:
  relayshield/alchemy_api_key    — {"api_key": "..."}
  relayshield/telegram_bot_token — {"telegram_bot_token": "..."}

How it works:
  1. Scan relayshield_monitored_wallets for chain_type == "solana"
  2. For each wallet, call Alchemy Solana RPC getSignaturesForAddress
  3. Compare against stored last_seen_sig — detect any new signatures
  4. Alert via Telegram with transaction summary
  5. Update last_seen_sig in DynamoDB
"""

import json
import logging
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
ALCHEMY_SECRET_NAME     = "relayshield/alchemy_api_key"
TG_SECRET_NAME          = "relayshield/telegram_bot_token"
TELEGRAM_API_BASE       = "https://api.telegram.org/bot{token}/{method}"

# Max signatures to check per wallet per run (avoids processing stale history on first run)
SIG_LIMIT = 5

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


def _alchemy_solana_url() -> str:
    api_key = _get_secret_json(ALCHEMY_SECRET_NAME, "api_key")
    return f"https://solana-mainnet.g.alchemy.com/v2/{api_key}"


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


def _get_recent_signatures(address: str) -> list[dict]:
    """Return up to SIG_LIMIT recent transaction signatures for a Solana address."""
    url  = _alchemy_solana_url()
    body = json.dumps({
        "jsonrpc": "2.0",
        "id":      1,
        "method":  "getSignaturesForAddress",
        "params":  [address, {"limit": SIG_LIMIT}],
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return data.get("result", [])
    except Exception as exc:
        logger.error("Solana getSignaturesForAddress failed wallet=%s: %s", address, exc)
        return []


def _get_all_solana_wallets() -> list[dict]:
    table  = dynamodb.Table(MONITORED_WALLETS_TABLE)
    items  = []
    kwargs: dict = {"FilterExpression": Attr("chain_type").eq("solana")}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return items


def _update_last_seen_sig(address: str, sig: str) -> None:
    try:
        dynamodb.Table(MONITORED_WALLETS_TABLE).update_item(
            Key={"wallet_address": address},
            UpdateExpression="SET last_seen_sig = :s, last_checked_at = :t",
            ExpressionAttributeValues={
                ":s": sig,
                ":t": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:
        logger.error("Failed to update last_seen_sig wallet=%s: %s", address, exc)


def _get_user(user_id: str) -> dict | None:
    resp = dynamodb.Table(USERS_TABLE).get_item(Key={"user_id": user_id})
    return resp.get("Item")


def _format_activity_alert(address: str, new_sigs: list[dict]) -> str:
    short = f"{address[:6]}...{address[-4:]}"
    count = len(new_sigs)
    tx_word = "transaction" if count == 1 else "transactions"

    lines = [
        f"🔔 *Solana Wallet Activity*\n",
        f"*Wallet:* `{short}`",
        f"*New {tx_word} detected:* {count}\n",
    ]

    for sig_info in new_sigs[:3]:
        sig   = sig_info.get("signature", "")
        slot  = sig_info.get("slot", "")
        err   = sig_info.get("err")
        status = "❌ Failed" if err else "✅ Confirmed"
        sig_short = f"{sig[:8]}...{sig[-6:]}" if len(sig) > 16 else sig
        lines.append(f"• `{sig_short}` — {status}")

    if count > 3:
        lines.append(f"  _...and {count - 3} more_")

    lines.append(
        f"\n[View on Solscan](https://solscan.io/account/{address})\n\n"
        f"_RelayShield Crypto Shield_"
    )
    return "\n".join(lines)


def lambda_handler(event: dict, context) -> dict:
    wallets = _get_all_solana_wallets()
    logger.info("Solana monitor — checking %d wallets", len(wallets))

    for wallet_item in wallets:
        address        = wallet_item.get("wallet_address", "")
        user_id        = wallet_item.get("user_id")
        last_seen_sig  = wallet_item.get("last_seen_sig")

        if not address or not user_id:
            continue

        sigs = _get_recent_signatures(address)
        if not sigs:
            continue

        latest_sig = sigs[0].get("signature")

        if last_seen_sig is None:
            # First run — record the latest sig without alerting
            logger.info("Solana first run — wallet=%s sig=%s", address, latest_sig)
            if latest_sig:
                _update_last_seen_sig(address, latest_sig)
            continue

        # Find all sigs newer than last_seen_sig
        new_sigs = []
        for sig_info in sigs:
            if sig_info.get("signature") == last_seen_sig:
                break
            new_sigs.append(sig_info)

        if not new_sigs:
            logger.info("Solana no new txs — wallet=%s", address)
            continue

        logger.info("Solana new txs — wallet=%s count=%d", address, len(new_sigs))

        user = _get_user(user_id)
        if not user:
            continue
        chat_id = user.get("telegram_chat_id")
        if not chat_id:
            continue

        alert = _format_activity_alert(address, new_sigs)
        _send_telegram(int(chat_id), alert)
        _update_last_seen_sig(address, latest_sig)
        logger.info("Solana alert sent — wallet=%s new_txs=%d", address, len(new_sigs))

    return {"statusCode": 200, "body": "ok"}
