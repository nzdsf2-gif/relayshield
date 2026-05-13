"""
RelayShield Liquidation Monitor Lambda

Monitors Aave V3 DeFi positions for each monitored EVM wallet.
Alerts via Telegram when health factor drops near liquidation threshold.

Trigger: EventBridge schedule — every 15 minutes
DynamoDB tables read:
  relayshield_monitored_wallets  — wallet_address → user_id
  relayshield_users              — user_id → telegram_chat_id

Secrets:
  relayshield/alchemy_api_key    — {"api_key": "..."}
  relayshield/telegram_bot_token — {"telegram_bot_token": "..."}

Health factor thresholds:
  < 1.5  — WARNING alert
  < 1.2  — CRITICAL alert (liquidation imminent)
  >= 1.5 — safe, no alert
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

MONITORED_WALLETS_TABLE = "relayshield_monitored_wallets"
USERS_TABLE             = "relayshield_users"
ALCHEMY_SECRET_NAME     = "relayshield/alchemy_api_key"
TG_SECRET_NAME          = "relayshield/telegram_bot_token"
TELEGRAM_API_BASE       = "https://api.telegram.org/bot{token}/{method}"

# Aave V3 Pool contract address — Ethereum mainnet
AAVE_V3_POOL = "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"
# getUserAccountData(address) function selector
GET_USER_ACCOUNT_DATA_SELECTOR = "0xbf92857c"
# Health factor is returned in ray units (1e27 = 1.0)
RAY = 10 ** 27

HF_WARNING  = 99999  # TEST ONLY — revert to 1.5 after testing
HF_CRITICAL = 1.2

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


def _alchemy_url() -> str:
    api_key = _get_secret_json(ALCHEMY_SECRET_NAME, "api_key")
    return f"https://eth-mainnet.g.alchemy.com/v2/{api_key}"


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


def _encode_address(address: str) -> str:
    """ABI-encode an address as a 32-byte hex parameter."""
    return address.lower().replace("0x", "").zfill(64)


def _get_aave_health_factor(wallet: str) -> float | None:
    """
    Call Aave V3 getUserAccountData(address) and return the health factor.
    Returns None if the wallet has no Aave position or the call fails.
    """
    calldata = GET_USER_ACCOUNT_DATA_SELECTOR + _encode_address(wallet)
    url  = _alchemy_url()
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1,
        "method":  "eth_call",
        "params":  [{"to": AAVE_V3_POOL, "data": calldata}, "latest"],
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        result = data.get("result", "0x")
        if not result or result == "0x":
            return None
        # Result is 6 x 32-byte values: collateral, debt, borrows, liqThreshold, ltv, healthFactor
        result = result.replace("0x", "")
        if len(result) < 6 * 64:
            return None
        health_factor_raw = int(result[5 * 64: 6 * 64], 16)
        if health_factor_raw == 0:
            return None
        # uint256 max means no debt — wallet is safe
        if health_factor_raw >= 2 ** 128:
            return None
        return health_factor_raw / RAY
    except Exception as exc:
        logger.error("Aave health factor fetch failed wallet=%s: %s", wallet, exc)
        return None


def _get_all_monitored_evm_wallets() -> list[dict]:
    table  = dynamodb.Table(MONITORED_WALLETS_TABLE)
    items  = []
    kwargs: dict = {"FilterExpression": Attr("wallet_address").begins_with("0x")}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return items


def _get_user(user_id: str) -> dict | None:
    resp = dynamodb.Table(USERS_TABLE).get_item(Key={"user_id": user_id})
    return resp.get("Item")


def _format_liquidation_alert(wallet: str, health_factor: float, is_critical: bool) -> str:
    short = f"{wallet[:6]}...{wallet[-4:]}"
    hf    = f"{health_factor:.3f}"

    if is_critical:
        return (
            f"🚨 *LIQUIDATION IMMINENT*\n\n"
            f"*Wallet:* `{short}`\n"
            f"*Aave V3 Health Factor:* `{hf}` ⚠️\n\n"
            f"Your position is at critical risk. At health factor 1.0 your collateral "
            f"will be liquidated at a penalty.\n\n"
            f"*Act immediately:*\n"
            f"• Add collateral to your Aave position, OR\n"
            f"• Repay part of your debt at app.aave.com\n\n"
            f"_RelayShield Crypto Shield_"
        )
    else:
        return (
            f"⚠️ *Liquidation Warning*\n\n"
            f"*Wallet:* `{short}`\n"
            f"*Aave V3 Health Factor:* `{hf}`\n\n"
            f"Your health factor is below 1.5. If collateral value drops or "
            f"debt value rises, you risk liquidation.\n\n"
            f"*Recommended actions:*\n"
            f"• Add collateral to your Aave position, OR\n"
            f"• Repay part of your debt at app.aave.com\n\n"
            f"_RelayShield Crypto Shield_"
        )


def lambda_handler(event: dict, context) -> dict:
    wallets = _get_all_monitored_evm_wallets()
    logger.info("Checking %d EVM wallets for Aave liquidation risk", len(wallets))

    for wallet_item in wallets:
        address = wallet_item.get("wallet_address", "").lower()
        user_id = wallet_item.get("user_id")
        if not address or not user_id:
            continue

        hf = _get_aave_health_factor(address)
        if hf is None:
            continue  # no Aave position

        logger.info("Aave health factor — wallet=%s hf=%.3f", address, hf)

        if hf >= HF_WARNING:
            continue  # safe

        user = _get_user(user_id)
        if not user:
            continue
        chat_id = user.get("telegram_chat_id")
        if not chat_id:
            continue

        is_critical = hf < HF_CRITICAL
        alert = _format_liquidation_alert(address, hf, is_critical)
        _send_telegram(int(chat_id), alert)
        logger.info(
            "Liquidation alert sent — wallet=%s hf=%.3f critical=%s",
            address, hf, is_critical,
        )

    return {"statusCode": 200, "body": "ok"}
