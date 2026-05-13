"""
RelayShield Gas Spike Monitor Lambda

Monitors Ethereum and Base gas prices every 15 minutes.
Alerts all Crypto Shield users when gas drops to a low threshold
(good time to transact) or spikes above a high threshold (avoid transactions).

Trigger: EventBridge schedule — every 15 minutes
DynamoDB tables read:
  relayshield_users              — scan for crypto-shield tier users with telegram_chat_id
  relayshield_gas_state          — tracks last alerted gas state to avoid repeat alerts

Secrets:
  relayshield/alchemy_api_key    — {"api_key": "..."}
  relayshield/telegram_bot_token — {"telegram_bot_token": "..."}
"""

import json
import logging
import urllib.request
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

secrets_client = boto3.client("secretsmanager")
dynamodb       = boto3.resource("dynamodb")

USERS_TABLE         = "relayshield_users"
GAS_STATE_TABLE     = "relayshield_gas_state"
ALCHEMY_SECRET_NAME = "relayshield/alchemy_api_key"
TG_SECRET_NAME      = "relayshield/telegram_bot_token"
TELEGRAM_API_BASE   = "https://api.telegram.org/bot{token}/{method}"

CRYPTO_TIERS = {"crypto-shield", "crypto_shield"}

# Gas thresholds in gwei
GAS_LOW_THRESHOLD  = 10   # below this → good time to transact
GAS_HIGH_THRESHOLD = 1    # TEST ONLY — revert to 80 after testing

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


def _alchemy_url(network: str) -> str:
    api_key = _get_secret_json(ALCHEMY_SECRET_NAME, "api_key")
    return f"https://{network}.g.alchemy.com/v2/{api_key}"


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


def _get_gas_gwei(network: str) -> float | None:
    url  = _alchemy_url(network)
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1,
        "method": "eth_gasPrice", "params": [],
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        wei = int(data["result"], 16)
        return round(wei / 1e9, 1)
    except Exception as exc:
        logger.error("Gas price fetch failed network=%s: %s", network, exc)
        return None


def _get_last_state(network: str) -> str:
    try:
        resp = dynamodb.Table(GAS_STATE_TABLE).get_item(Key={"network": network})
        return resp.get("Item", {}).get("last_state", "normal")
    except Exception:
        return "normal"


def _set_last_state(network: str, state: str) -> None:
    try:
        dynamodb.Table(GAS_STATE_TABLE).put_item(Item={
            "network":    network,
            "last_state": state,
        })
    except Exception as exc:
        logger.error("Gas state write failed: %s", exc)


def _get_crypto_shield_users() -> list[dict]:
    table  = dynamodb.Table(USERS_TABLE)
    items  = []
    kwargs: dict = {"FilterExpression": Attr("tier").is_in(list(CRYPTO_TIERS))}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return [u for u in items if u.get("telegram_chat_id")]


def lambda_handler(event: dict, context) -> dict:
    users = _get_crypto_shield_users()
    logger.info("Gas monitor — %d Crypto Shield users", len(users))

    for network, label in [("eth-mainnet", "Ethereum"), ("base-mainnet", "Base")]:
        gwei = _get_gas_gwei(network)
        if gwei is None:
            continue

        last_state = _get_last_state(network)
        logger.info("Gas %s: %.1f gwei (last state: %s)", network, gwei, last_state)

        if gwei <= GAS_LOW_THRESHOLD and last_state != "low":
            new_state = "low"
            message   = (
                f"⛽ *{label} Gas: Low*\n\n"
                f"Current gas price: *{gwei} gwei*\n\n"
                f"Now is a good time to make non-urgent on-chain transactions — "
                f"gas fees are significantly below average.\n\n"
                f"_RelayShield Crypto Shield_"
            )
        elif gwei >= GAS_HIGH_THRESHOLD and last_state != "high":
            new_state = "high"
            message   = (
                f"⛽ *{label} Gas: High*\n\n"
                f"Current gas price: *{gwei} gwei*\n\n"
                f"Gas fees are elevated. Consider delaying non-urgent transactions "
                f"until gas returns to normal levels.\n\n"
                f"_RelayShield Crypto Shield_"
            )
        elif GAS_LOW_THRESHOLD < gwei < GAS_HIGH_THRESHOLD and last_state in ("low", "high"):
            new_state = "normal"
            message   = None  # Return to normal — no need to alert
        else:
            continue

        _set_last_state(network, new_state)

        if message:
            for user in users:
                _send_telegram(int(user["telegram_chat_id"]), message)
            logger.info("Gas alert sent (%s) — %s gwei — %d users", new_state, gwei, len(users))

    return {"statusCode": 200, "body": "ok"}
