"""
RelayShield Alchemy Notify Webhook Lambda

Receives ADDRESS_ACTIVITY webhook callbacks from Alchemy Notify,
looks up the RelayShield subscriber who owns the address, and sends
a Telegram alert with transfer details and GoPlus risk context.

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
import urllib.error
import urllib.request

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

secrets_client = boto3.client("secretsmanager")
dynamodb       = boto3.resource("dynamodb")

MONITORED_WALLETS_TABLE = "relayshield_monitored_wallets"
USERS_TABLE             = "relayshield_users"
ALCHEMY_SECRET_NAME     = "relayshield/alchemy_api_key"
TG_SECRET_NAME          = "relayshield/telegram_bot_token"
GOPLUS_BASE_URL         = "https://api.gopluslabs.io/api/v1/address_security"
TELEGRAM_API_BASE       = "https://api.telegram.org/bot{token}/{method}"

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


def _format_alert(activity: dict, monitored_address: str, risk: dict) -> str:
    from_addr = activity.get("fromAddress", "unknown")
    to_addr   = activity.get("toAddress", "unknown")
    value     = activity.get("value", 0)
    asset     = activity.get("asset", "ETH")
    network   = activity.get("network", "ETH_MAINNET").replace("_", " ").title()
    tx_hash   = activity.get("hash", "")

    direction = "📥 IN" if to_addr.lower() == monitored_address.lower() else "📤 OUT"
    other     = from_addr if to_addr.lower() == monitored_address.lower() else to_addr

    risk_flags = [k for k, v in risk.items() if v == "1"]
    risk_level = "HIGH 🔴" if len(risk_flags) >= 2 else "MEDIUM 🟡" if risk_flags else "LOW 🟢"
    risk_line  = f"\n⚠️ *Counterparty Risk:* {risk_level}" if risk_flags else ""

    short_addr  = f"{monitored_address[:6]}...{monitored_address[-4:]}"
    short_other = f"{other[:6]}...{other[-4:]}" if len(other) > 10 else other
    tx_line     = f"\n🔗 [View tx](https://etherscan.io/tx/{tx_hash})" if tx_hash else ""

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

        # GoPlus risk check on the counterparty address
        counterparty = from_addr if to_addr == monitored else to_addr
        risk = _goplus_risk_check(counterparty) if counterparty else {}

        alert = _format_alert(activity, monitored, risk)
        _send_telegram(int(chat_id), alert)
        logger.info("Wallet alert sent — user=%s address=%s", user.get("user_id"), monitored)

    return {"statusCode": 200, "body": "ok"}
