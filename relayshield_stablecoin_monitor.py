"""
RelayShield Stablecoin Depeg Monitor

Polls CoinGecko every 5 minutes for stablecoin prices.
Sends real-time Telegram alerts to all active Crypto Shield users
when any monitored stablecoin depegs.

Thresholds:
  ⚠️  Warning  — price drops below $0.997 (>0.3% depeg)
  🚨  Critical — price drops below $0.990 (>1.0% depeg)

Monitored stablecoins:
  USDC, USDT, DAI, FRAX, LUSD, PYUSD, USDS (formerly sDAI)

DynamoDB:
  relayshield_users             — scan for active Crypto Shield users
  relayshield_depeg_alerts      — dedup table: last alert sent per coin

Trigger: EventBridge schedule — every 5 minutes
  rate(5 minutes)

Secrets:
  relayshield/telegram_bot_token — {"telegram_bot_token": "..."}
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

USERS_TABLE        = "relayshield_users"
DEPEG_ALERTS_TABLE = "relayshield_depeg_alerts"
TG_SECRET_NAME     = "relayshield/telegram_bot_token"
TELEGRAM_API_BASE  = "https://api.telegram.org/bot{token}/{method}"
COINGECKO_URL      = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=usd-coin,tether,dai,frax,liquity-usd,paypal-usd,usd-coin-on-starknet"
    "&vs_currencies=usd&include_24hr_change=true"
)

CRYPTO_TIERS = {"crypto_shield", "crypto-shield"}

# Stablecoin metadata: coingecko_id → display info + per-coin thresholds
# warn  — price below this triggers a warning alert
# crit  — price below this triggers a critical alert
# repeg — price must recover above this to clear the alert
#
# FRAX uses wider thresholds — it is a fractional algorithmic stablecoin
# that routinely trades 0.3–0.5% off peg under normal market conditions.
STABLECOINS = {
    "usd-coin":    {"symbol": "USDC",  "name": "USD Coin",    "warn": 0.997, "crit": 0.990, "repeg": 0.999},
    "tether":      {"symbol": "USDT",  "name": "Tether",      "warn": 0.997, "crit": 0.990, "repeg": 0.999},
    "dai":         {"symbol": "DAI",   "name": "DAI",         "warn": 0.997, "crit": 0.990, "repeg": 0.999},
    "frax":        {"symbol": "FRAX",  "name": "Frax",        "warn": 0.995, "crit": 0.985, "repeg": 0.997},
    "liquity-usd": {"symbol": "LUSD",  "name": "Liquity USD", "warn": 0.997, "crit": 0.990, "repeg": 0.999},
    "paypal-usd":  {"symbol": "PYUSD", "name": "PayPal USD",  "warn": 0.997, "crit": 0.990, "repeg": 0.999},
}

_secret_cache: dict = {}


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

def _get_secret(name: str) -> str:
    if name not in _secret_cache:
        _secret_cache[name] = secrets_client.get_secret_value(
            SecretId=name
        )["SecretString"].strip()
    return _secret_cache[name]


def _tg_token() -> str:
    return json.loads(_get_secret(TG_SECRET_NAME))["telegram_bot_token"]


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# CoinGecko
# ---------------------------------------------------------------------------

def _fetch_stablecoin_prices() -> dict[str, dict]:
    """
    Returns { coingecko_id: { "usd": float, "usd_24h_change": float } }
    """
    try:
        req = urllib.request.Request(
            COINGECKO_URL,
            headers={"User-Agent": "RelayShield/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        logger.error("CoinGecko fetch failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# DynamoDB — dedup
# ---------------------------------------------------------------------------

def _get_active_depeg_alerts() -> dict[str, str]:
    """
    Returns { coingecko_id: severity } for coins currently in alert state.
    """
    try:
        table = dynamodb.Table(DEPEG_ALERTS_TABLE)
        resp  = table.scan()
        return {
            item["coin_id"]: item.get("severity", "warning")
            for item in resp.get("Items", [])
        }
    except Exception as exc:
        logger.warning("Depeg alert table scan failed: %s", exc)
        return {}


def _set_depeg_alert(coin_id: str, severity: str, price: float) -> None:
    try:
        dynamodb.Table(DEPEG_ALERTS_TABLE).put_item(Item={
            "coin_id":    coin_id,
            "severity":   severity,
            "price":      str(round(price, 6)),
            "alerted_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        logger.error("Failed to write depeg alert coin_id=%s: %s", coin_id, exc)


def _clear_depeg_alert(coin_id: str) -> None:
    try:
        dynamodb.Table(DEPEG_ALERTS_TABLE).delete_item(Key={"coin_id": coin_id})
        logger.info("Depeg alert cleared: %s", coin_id)
    except Exception as exc:
        logger.error("Failed to clear depeg alert coin_id=%s: %s", coin_id, exc)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def _get_crypto_shield_users() -> list[dict]:
    """Return all active Crypto Shield Telegram users."""
    table  = dynamodb.Table(USERS_TABLE)
    items  = []
    kwargs: dict = {
        "FilterExpression": (
            Attr("active").eq(True) &
            Attr("onboarding_state").eq("ACTIVE") &
            Attr("telegram_chat_id").exists()
        )
    }
    while True:
        resp = table.scan(**kwargs)
        for item in resp.get("Items", []):
            tier = item.get("subscription_tier") or item.get("tier", "")
            if tier in CRYPTO_TIERS:
                items.append(item)
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return items


# ---------------------------------------------------------------------------
# Alert messages
# ---------------------------------------------------------------------------

def _depeg_alert_text(coin_id: str, price: float, change_24h: float, severity: str) -> str:
    meta     = STABLECOINS.get(coin_id, {"symbol": coin_id.upper(), "name": coin_id})
    symbol   = meta["symbol"]
    name     = meta["name"]
    pct_off  = round((1.0 - price) * 100, 3)
    icon     = "🚨" if severity == "critical" else "⚠️"
    level    = "CRITICAL DEPEG" if severity == "critical" else "DEPEG WARNING"
    change   = f"{change_24h:+.2f}%" if change_24h is not None else "N/A"

    action = (
        "*Immediate action recommended:*\n"
        "• Exit stablecoin positions or reduce exposure\n"
        "• Check Aave/Curve collateral if using as collateral\n"
        "• Monitor for recovery — if price doesn't recover in 1h, act\n"
    ) if severity == "critical" else (
        "*Suggested actions:*\n"
        "• Monitor closely — this may recover quickly\n"
        "• Check any lending positions using this as collateral\n"
        "• Run `/riskcheck` to review your wallet exposure\n"
    )

    return (
        f"{icon} *{symbol} {level}*\n\n"
        f"*{name}* is trading at *${price:.4f}* — "
        f"*{pct_off:.3f}% below peg*\n"
        f"24h change: {change}\n\n"
        f"{action}\n"
        f"_RelayShield Crypto Shield — Real-time Stablecoin Monitor_"
    )


def _repeg_text(coin_id: str, price: float) -> str:
    meta   = STABLECOINS.get(coin_id, {"symbol": coin_id.upper(), "name": coin_id})
    symbol = meta["symbol"]
    return (
        f"✅ *{symbol} Peg Restored*\n\n"
        f"{meta['name']} has returned to *${price:.4f}* — within normal range.\n\n"
        f"_RelayShield Crypto Shield_"
    )


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context) -> dict:
    prices        = _fetch_stablecoin_prices()
    active_alerts = _get_active_depeg_alerts()

    if not prices:
        logger.warning("No price data returned — skipping cycle")
        return {"statusCode": 200, "body": "no_price_data"}

    alerts_to_send: list[dict] = []   # {coin_id, price, change, severity}
    repeg_to_send:  list[str]  = []   # coin_ids that have recovered

    for coin_id, meta in STABLECOINS.items():
        data  = prices.get(coin_id, {})
        price = data.get("usd")
        if price is None:
            continue
        change_24h = data.get("usd_24h_change")

        currently_alerting = coin_id in active_alerts
        warn_thresh  = meta["warn"]
        crit_thresh  = meta["crit"]
        repeg_thresh = meta["repeg"]

        if price < crit_thresh:
            severity = "critical"
            if active_alerts.get(coin_id) != "critical":
                alerts_to_send.append({
                    "coin_id": coin_id, "price": price,
                    "change": change_24h, "severity": severity,
                })
                _set_depeg_alert(coin_id, severity, price)

        elif price < warn_thresh:
            severity = "warning"
            if not currently_alerting:
                alerts_to_send.append({
                    "coin_id": coin_id, "price": price,
                    "change": change_24h, "severity": severity,
                })
                _set_depeg_alert(coin_id, severity, price)

        elif price >= repeg_thresh and currently_alerting:
            repeg_to_send.append(coin_id)
            _clear_depeg_alert(coin_id)

    if not alerts_to_send and not repeg_to_send:
        logger.info("All stablecoins within normal range — no alerts")
        return {"statusCode": 200, "body": "ok_no_alerts"}

    users = _get_crypto_shield_users()
    logger.info(
        "Depeg alerts=%d repeg=%d users=%d",
        len(alerts_to_send), len(repeg_to_send), len(users),
    )

    sent = 0
    for user in users:
        chat_id = user.get("telegram_chat_id")
        if not chat_id:
            continue
        try:
            for alert in alerts_to_send:
                text = _depeg_alert_text(
                    alert["coin_id"], alert["price"],
                    alert["change"], alert["severity"],
                )
                _send_telegram(int(chat_id), text)

            for coin_id in repeg_to_send:
                data  = prices.get(coin_id, {})
                price = data.get("usd", 1.0)
                _send_telegram(int(chat_id), _repeg_text(coin_id, price))

            sent += 1
        except Exception as exc:
            logger.error("Alert send failed chat_id=%s: %s", chat_id, exc)

    logger.info("Depeg alerts sent to %d users", sent)
    return {"statusCode": 200, "body": f"sent={sent}"}
