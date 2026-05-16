"""
RelayShield Bitcoin Activity Monitor Lambda

Monitors Bitcoin wallets for new transaction activity every 15 minutes.
Sends a Telegram alert whenever new transactions are detected on a
monitored Bitcoin wallet.

Trigger: EventBridge schedule — every 15 minutes
DynamoDB tables:
  relayshield_monitored_wallets  — wallet_address, user_id, chain_type, last_seen_txid
  relayshield_users              — user_id → telegram_chat_id

Secrets:
  relayshield/telegram_bot_token — {"telegram_bot_token": "..."}

Data source:
  Blockstream API — https://blockstream.info/api (free, no key required)

How it works:
  1. Scan relayshield_monitored_wallets for chain_type == "bitcoin"
  2. For each wallet, call Blockstream API to fetch recent transactions
  3. Compare against stored last_seen_txid — detect any new transactions
  4. Alert via Telegram with transaction summary and mempool.space link
  5. Update last_seen_txid in DynamoDB
"""

import json
import logging
import urllib.request
import urllib.error
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
TELEGRAM_API_BASE       = "https://api.telegram.org/bot{token}/{method}"
BLOCKSTREAM_API         = "https://blockstream.info/api"

# Max transactions to fetch per wallet per run
TX_LIMIT = 5

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


def _get_recent_txs(address: str) -> list[dict]:
    """
    Return up to TX_LIMIT recent transactions for a Bitcoin address
    using the Blockstream API. Returns newest-first.
    """
    url = f"{BLOCKSTREAM_API}/address/{address}/txs"
    req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            txs = json.loads(resp.read())
        return txs[:TX_LIMIT]
    except urllib.error.HTTPError as exc:
        logger.error("Blockstream API error wallet=%s status=%s", address, exc.code)
        return []
    except Exception as exc:
        logger.error("Blockstream API failed wallet=%s: %s", address, exc)
        return []


def _get_address_info(address: str) -> dict:
    """Return address summary (balance, tx count) from Blockstream."""
    url = f"{BLOCKSTREAM_API}/address/{address}"
    req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        logger.error("Blockstream address info failed wallet=%s: %s", address, exc)
        return {}


def _satoshi_to_btc(sats: int) -> str:
    """Convert satoshis to BTC string with up to 8 decimal places."""
    btc = sats / 100_000_000
    return f"{btc:.8f}".rstrip("0").rstrip(".")


def _get_received_value(tx: dict, address: str) -> int:
    """Sum satoshis received by address in this transaction's outputs."""
    total = 0
    for vout in tx.get("vout", []):
        scriptpubkey_address = vout.get("scriptpubkey_address", "")
        if scriptpubkey_address == address:
            total += vout.get("value", 0)
    return total


def _get_sent_value(tx: dict, address: str) -> int:
    """Sum satoshis spent from address in this transaction's inputs."""
    total = 0
    for vin in tx.get("vin", []):
        prevout = vin.get("prevout", {})
        if prevout.get("scriptpubkey_address", "") == address:
            total += prevout.get("value", 0)
    return total


def _get_all_bitcoin_wallets() -> list[dict]:
    table  = dynamodb.Table(MONITORED_WALLETS_TABLE)
    items  = []
    kwargs: dict = {"FilterExpression": Attr("chain_type").eq("bitcoin")}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return items


def _update_last_seen_txid(address: str, txid: str) -> None:
    try:
        dynamodb.Table(MONITORED_WALLETS_TABLE).update_item(
            Key={"wallet_address": address},
            UpdateExpression="SET last_seen_txid = :t, last_checked_at = :c",
            ExpressionAttributeValues={
                ":t": txid,
                ":c": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:
        logger.error("Failed to update last_seen_txid wallet=%s: %s", address, exc)


def _get_user(user_id: str) -> dict | None:
    resp = dynamodb.Table(USERS_TABLE).get_item(Key={"user_id": user_id})
    return resp.get("Item")


def _format_activity_alert(address: str, new_txs: list[dict]) -> str:
    short   = f"{address[:6]}...{address[-4:]}"
    count   = len(new_txs)
    tx_word = "transaction" if count == 1 else "transactions"

    lines = [
        f"🔔 *Bitcoin Wallet Activity*\n",
        f"*Wallet:* `{short}`",
        f"*New {tx_word} detected:* {count}\n",
    ]

    for tx in new_txs[:3]:
        txid      = tx.get("txid", "")
        confirmed = tx.get("status", {}).get("confirmed", False)
        status    = "✅ Confirmed" if confirmed else "⏳ Unconfirmed"
        txid_short = f"{txid[:8]}...{txid[-6:]}" if len(txid) > 16 else txid

        received = _get_received_value(tx, address)
        sent     = _get_sent_value(tx, address)

        if received > 0 and sent == 0:
            direction = f"📥 +{_satoshi_to_btc(received)} BTC"
        elif sent > 0 and received == 0:
            direction = f"📤 -{_satoshi_to_btc(sent)} BTC"
        elif received > 0 and sent > 0:
            net = received - sent
            sign = "+" if net >= 0 else ""
            direction = f"↔️ {sign}{_satoshi_to_btc(net)} BTC"
        else:
            direction = "↔️ Internal"

        lines.append(f"• `{txid_short}` — {status} {direction}")

    if count > 3:
        lines.append(f"  _...and {count - 3} more_")

    lines.append(
        f"\n[View on mempool.space](https://mempool.space/address/{address})\n\n"
        f"_RelayShield Crypto Shield_"
    )
    return "\n".join(lines)


def lambda_handler(event: dict, context) -> dict:
    wallets = _get_all_bitcoin_wallets()
    logger.info("Bitcoin monitor — checking %d wallets", len(wallets))

    for wallet_item in wallets:
        address       = wallet_item.get("wallet_address", "")
        user_id       = wallet_item.get("user_id")
        last_seen_txid = wallet_item.get("last_seen_txid")

        if not address or not user_id:
            continue

        txs = _get_recent_txs(address)
        if not txs:
            logger.info("Bitcoin no txs returned — wallet=%s", address)
            continue

        latest_txid = txs[0].get("txid")

        if last_seen_txid is None:
            # First run — record latest txid without alerting
            logger.info("Bitcoin first run — wallet=%s txid=%s", address, latest_txid)
            if latest_txid:
                _update_last_seen_txid(address, latest_txid)
            continue

        # Find all txs newer than last_seen_txid
        new_txs = []
        for tx in txs:
            if tx.get("txid") == last_seen_txid:
                break
            new_txs.append(tx)

        if not new_txs:
            logger.info("Bitcoin no new txs — wallet=%s", address)
            continue

        logger.info("Bitcoin new txs — wallet=%s count=%d", address, len(new_txs))

        user = _get_user(user_id)
        if not user:
            continue
        chat_id = user.get("telegram_chat_id")
        if not chat_id:
            continue

        alert = _format_activity_alert(address, new_txs)
        _send_telegram(int(chat_id), alert)
        _update_last_seen_txid(address, latest_txid)
        logger.info("Bitcoin alert sent — wallet=%s new_txs=%d", address, len(new_txs))

    return {"statusCode": 200, "body": "ok"}
