"""
RelayShield Alchemy Notify Webhook Lambda

Receives ADDRESS_ACTIVITY webhook callbacks from Alchemy Notify,
looks up the RelayShield subscriber who owns the address, and sends
a Telegram alert with transfer details and GoPlus risk context.

Also performs real-time drainer detection: records each outbound
transaction in relayshield_wallet_activity_log (TTL 1 hour) and fires
a high-urgency drain alert if 2+ outbound txs are seen within 10 minutes.

Webhook type: ADDRESS_ACTIVITY
Trigger: any inbound or outbound transfer on a monitored wallet address

Environment variables (set on Lambda):
  None — all config via Secrets Manager

Secrets:
  relayshield/alchemy_api_key      — {"api_key": "...", "webhook_id": "...", "signing_key": "..."}
  relayshield/telegram_bot_token   — {"telegram_bot_token": "..."}

API Gateway:
  POST /v1/alchemy-webhook  — public endpoint, HMAC-verified
"""

import hashlib
import hmac
import json
import logging
import time
import urllib.error
import urllib.request
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key, Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

secrets_client = boto3.client("secretsmanager")
dynamodb       = boto3.resource("dynamodb")

MONITORED_WALLETS_TABLE  = "relayshield_monitored_wallets"
USERS_TABLE              = "relayshield_users"
ACTIVITY_LOG_TABLE       = "relayshield_wallet_activity_log"
ALCHEMY_SECRET_NAME      = "relayshield/alchemy_api_key"
TG_SECRET_NAME           = "relayshield/telegram_bot_token"
GOPLUS_BASE_URL          = "https://api.gopluslabs.io/api/v1/address_security"
TELEGRAM_API_BASE        = "https://api.telegram.org/bot{token}/{method}"

# Drainer detection thresholds
DRAIN_WINDOW_SECONDS = 600   # 10-minute rolling window
DRAIN_TX_THRESHOLD   = 2     # number of outbound txs to trigger alert
ACTIVITY_LOG_TTL     = 3600  # 1 hour TTL on activity log items

_secret_cache: dict[str, str] = {}


def _get_secret(name: str) -> str:
    if name not in _secret_cache:
        _secret_cache[name] = secrets_client.get_secret_value(
            SecretId=name
        )["SecretString"].strip()
    return _secret_cache[name]


def _get_secret_json(name: str, key: str) -> str:
    import json as _json
    return _json.loads(_get_secret(name))[key]


def _tg_token() -> str:
    return _get_secret_json(TG_SECRET_NAME, "telegram_bot_token")


def _verify_alchemy_signature(body: bytes, signature: str) -> bool:
    """Verify Alchemy webhook HMAC-SHA256 signature."""
    try:
        signing_key = _get_secret_json(ALCHEMY_SECRET_NAME, "signing_key")
        expected = hmac.new(
            signing_key.encode(), body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception as exc:
        logger.error("Signature verification error: %s", exc)
        return False


def _get_user_by_wallet(address: str) -> dict | None:
    """Look up user_id from relayshield_monitored_wallets, then fetch user record."""
    try:
        wt = dynamodb.Table(MONITORED_WALLETS_TABLE)
        resp = wt.get_item(Key={"wallet_address": address.lower()})
        item = resp.get("Item")
        if not item:
            return None
        user_id = item["user_id"]
        ut = dynamodb.Table(USERS_TABLE)
        resp2 = ut.get_item(Key={"user_id": user_id})
        return resp2.get("Item")
    except Exception as exc:
        logger.error("Wallet lookup failed for %s: %s", address, exc)
        return None


def _goplus_risk_check(address: str) -> dict:
    try:
        url = f"{GOPLUS_BASE_URL}/{address}?chain_id=1"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read())
            return data.get("result", {}).get(address.lower(), {})
    except Exception:
        return {}


def _send_telegram(chat_id: int, text: str) -> None:
    token  = _tg_token()
    url    = TELEGRAM_API_BASE.format(token=token, method="sendMessage")
    body   = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
    req    = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        logger.error("Telegram send failed chat_id=%s: %s", chat_id, exc)


def _record_outbound_tx(wallet_address: str, tx_hash: str, value: float, asset: str, network: str) -> None:
    """Record an outbound transaction in the activity log with a 1-hour TTL."""
    now = int(time.time())
    try:
        dynamodb.Table(ACTIVITY_LOG_TABLE).put_item(Item={
            "wallet_address": wallet_address,
            "tx_timestamp":   Decimal(now),
            "tx_hash":        tx_hash,
            "value":          Decimal(str(value)),
            "asset":          asset,
            "network":        network,
            "ttl":            Decimal(now + ACTIVITY_LOG_TTL),
        })
    except Exception as exc:
        logger.error("Activity log write failed wallet=%s: %s", wallet_address, exc)


def _check_drain_pattern(wallet_address: str) -> int:
    """
    Query recent outbound txs in the rolling window.
    Returns count of outbound txs in the last DRAIN_WINDOW_SECONDS.
    """
    window_start = Decimal(int(time.time()) - DRAIN_WINDOW_SECONDS)
    try:
        resp = dynamodb.Table(ACTIVITY_LOG_TABLE).query(
            KeyConditionExpression=(
                Key("wallet_address").eq(wallet_address) &
                Key("tx_timestamp").gte(window_start)
            )
        )
        return len(resp.get("Items", []))
    except Exception as exc:
        logger.error("Drain pattern query failed wallet=%s: %s", wallet_address, exc)
        return 0


def _format_drain_alert(monitored_address: str, tx_count: int, network: str) -> str:
    short_addr   = f"{monitored_address[:6]}...{monitored_address[-4:]}"
    network_name = network.replace("_", " ").title()
    return (
        f"🚨🚨 *POSSIBLE WALLET DRAIN IN PROGRESS* 🚨🚨\n\n"
        f"*Address:* `{short_addr}`\n"
        f"*Network:* {network_name}\n"
        f"*Outbound transactions:* {tx_count} in the last 10 minutes\n\n"
        f"⚠️ *Immediate actions:*\n"
        f"• Move remaining funds to a secure wallet NOW\n"
        f"• Revoke all token approvals at revoke\\.cash\n"
        f"• Check for malicious browser extensions\n"
        f"• Do NOT interact with any dApps until secured\n\n"
        f"_RelayShield Crypto Shield_"
    )


_EXPLORER_MAP = {
    "ETH_MAINNET":    "https://etherscan.io/tx/{}",
    "BASE_MAINNET":   "https://basescan.org/tx/{}",
    "MATIC_MAINNET":  "https://polygonscan.com/tx/{}",
    "ARB_MAINNET":    "https://arbiscan.io/tx/{}",
    "OPT_MAINNET":    "https://optimistic.etherscan.io/tx/{}",
    "SOLANA_MAINNET": "https://solscan.io/tx/{}",
    "TON_MAINNET":    "https://tonscan.org/tx/{}",
    "BTC_MAINNET":    "https://mempool.space/tx/{}",
}

_EVM_NETWORKS = {"ETH_MAINNET", "BASE_MAINNET", "MATIC_MAINNET", "ARB_MAINNET", "OPT_MAINNET"}


def _format_alert(activity: dict, monitored_address: str, risk: dict) -> str:
    from_addr = activity.get("fromAddress", "unknown")
    to_addr   = activity.get("toAddress", "unknown")
    value     = activity.get("value", 0)
    asset     = activity.get("asset", "ETH")
    raw_net   = activity.get("network", "ETH_MAINNET")
    network   = raw_net.replace("_", " ").title()
    tx_hash   = activity.get("hash", "")

    direction = "📥 IN" if to_addr.lower() == monitored_address.lower() else "📤 OUT"
    other     = from_addr if to_addr.lower() == monitored_address.lower() else to_addr

    risk_flags = [k for k, v in risk.items() if v == "1"]
    risk_level = "HIGH 🔴" if len(risk_flags) >= 2 else "MEDIUM 🟡" if risk_flags else "LOW 🟢"
    risk_line  = f"\n⚠️ *Counterparty Risk:* {risk_level}" if risk_flags else ""

    short_addr  = f"{monitored_address[:6]}...{monitored_address[-4:]}"
    short_other = f"{other[:6]}...{other[-4:]}" if len(other) > 10 else other

    explorer = _EXPLORER_MAP.get(raw_net)
    tx_line  = f"\n🔗 [View tx]({explorer.format(tx_hash)})" if tx_hash and explorer else ""

    return (
        f"🚨 *Wallet Activity Detected*\n\n"
        f"*Address:* `{short_addr}`\n"
        f"*Direction:* {direction}\n"
        f"*Amount:* {value} {asset}\n"
        f"*Network:* {network}\n"
        f"*Counterparty:* `{short_other}`"
        f"{risk_line}"
        f"{tx_line}\n\n"
        f"_RelayShield Crypto Shield_"
    )


def lambda_handler(event: dict, context) -> dict:
    body_raw = (event.get("body") or "").encode()
    signature = (event.get("headers") or {}).get("x-alchemy-signature", "")

    if not _verify_alchemy_signature(body_raw, signature):
        logger.warning("Alchemy signature verification failed")
        return {"statusCode": 401, "body": "Unauthorized"}

    try:
        payload = json.loads(body_raw)
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": "Bad Request"}

    webhook_type = payload.get("type")
    if webhook_type != "ADDRESS_ACTIVITY":
        logger.info("Ignoring webhook type: %s", webhook_type)
        return {"statusCode": 200, "body": "ok"}

    activities = payload.get("event", {}).get("activity", [])
    for activity in activities:
        from_addr = (activity.get("fromAddress") or "").lower()
        to_addr   = (activity.get("toAddress") or "").lower()

        # Determine which monitored address triggered this event
        monitored = None
        for addr in (from_addr, to_addr):
            user = _get_user_by_wallet(addr)
            if user:
                monitored = addr
                break

        if not user or not monitored:
            logger.info("No user found for activity addresses: %s / %s", from_addr, to_addr)
            continue

        chat_id = user.get("telegram_chat_id")
        if not chat_id:
            logger.info("User %s has no telegram_chat_id", user.get("user_id"))
            continue

        # GoPlus risk check on the counterparty address (EVM only)
        counterparty = from_addr if to_addr == monitored else to_addr
        network_raw  = (activity.get("network") or "").upper()
        is_evm       = network_raw in _EVM_NETWORKS
        risk = _goplus_risk_check(counterparty) if counterparty and is_evm else {}

        alert = _format_alert(activity, monitored, risk)
        _send_telegram(int(chat_id), alert)
        logger.info("Wallet alert sent — user=%s address=%s", user.get("user_id"), monitored)

        # Drainer detection — track outbound txs and alert on rapid drain pattern
        is_outbound = from_addr == monitored
        if is_outbound:
            value = activity.get("value", 0)
            asset = activity.get("asset", "ETH")
            tx_hash = activity.get("hash", "")
            _record_outbound_tx(monitored, tx_hash, value, asset, network_raw)
            tx_count = _check_drain_pattern(monitored)
            if tx_count >= DRAIN_TX_THRESHOLD:
                drain_alert = _format_drain_alert(monitored, tx_count, network_raw)
                _send_telegram(int(chat_id), drain_alert)
                logger.warning("Drain alert sent — user=%s address=%s tx_count=%d",
                               user.get("user_id"), monitored, tx_count)

    return {"statusCode": 200, "body": "ok"}
