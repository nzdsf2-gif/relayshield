"""
RelayShield Token Approval Monitor Lambda

Scans monitored EVM wallets for new ERC-20 token approval transactions
(function selector 0x095ea7b3). Alerts via Telegram when an unlimited
approval (amount = uint256 max) is detected.

Trigger: EventBridge schedule — every 15 minutes
DynamoDB tables read:
  relayshield_monitored_wallets  — wallet_address → user_id, last_approval_block
  relayshield_users              — user_id → telegram_chat_id

Secrets:
  relayshield/alchemy_api_key    — {"api_key": "...", "webhook_id": "...", "signing_key": "..."}
  relayshield/telegram_bot_token — {"telegram_bot_token": "..."}

Environment variables:
  ALCHEMY_NETWORK  — Alchemy network slug (default: eth-mainnet)
"""

import json
import logging
import os
import urllib.error
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

# ERC-20 approve(address spender, uint256 amount) function selector
APPROVE_SELECTOR = "0x095ea7b3"
# uint256 max — unlimited approval sentinel
UINT256_MAX = 2**256 - 1
# Treat approvals >= this threshold as "unlimited"
UNLIMITED_THRESHOLD = 2**128

ALCHEMY_NETWORK = os.environ.get("ALCHEMY_NETWORK", "eth-mainnet")

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


def _alchemy_api_key() -> str:
    return _get_secret_json(ALCHEMY_SECRET_NAME, "api_key")


def _alchemy_base_url() -> str:
    return f"https://{ALCHEMY_NETWORK}.g.alchemy.com/v2/{_alchemy_api_key()}"


def _send_telegram(chat_id: int, text: str) -> None:
    token = _tg_token()
    url   = TELEGRAM_API_BASE.format(token=token, method="sendMessage")
    body  = json.dumps({
        "chat_id":    chat_id,
        "text":       text,
        "parse_mode": "MarkdownV2",
    }).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        logger.error("Telegram send failed chat_id=%s: %s", chat_id, exc)


def _get_latest_block() -> int:
    """Fetch current block number via eth_blockNumber."""
    url  = _alchemy_base_url()
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []}).encode()
    req  = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    return int(data["result"], 16)


def _get_outbound_txs(address: str, from_block: str, to_block: str) -> list[dict]:
    """Fetch outbound transactions for an address using alchemy_getAssetTransfers."""
    url  = _alchemy_base_url()
    body = json.dumps({
        "jsonrpc": "2.0",
        "id":      1,
        "method":  "alchemy_getAssetTransfers",
        "params":  [{
            "fromBlock":        from_block,
            "toBlock":          to_block,
            "fromAddress":      address,
            "category":         ["external", "internal", "erc20"],
            "withMetadata":     False,
            "excludeZeroValue": False,
            "maxCount":         "0x64",
        }],
    }).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return data.get("result", {}).get("transfers", [])
    except Exception as exc:
        logger.error("alchemy_getAssetTransfers failed for %s: %s", address, exc)
        return []


def _get_tx_input(tx_hash: str) -> str:
    """Fetch transaction input data via eth_getTransactionByHash."""
    url  = _alchemy_base_url()
    body = json.dumps({
        "jsonrpc": "2.0",
        "id":      1,
        "method":  "eth_getTransactionByHash",
        "params":  [tx_hash],
    }).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        return (data.get("result") or {}).get("input", "")
    except Exception as exc:
        logger.error("eth_getTransactionByHash failed %s: %s", tx_hash, exc)
        return ""


def _parse_approve(input_data: str) -> tuple[str, int] | None:
    """
    Parse ERC-20 approve(address,uint256) calldata.
    Returns (spender_address, amount) or None if not an approve call.
    """
    if not input_data.startswith(APPROVE_SELECTOR):
        return None
    data = input_data[len(APPROVE_SELECTOR):]
    if len(data) < 128:
        return None
    spender = "0x" + data[24:64]
    amount  = int(data[64:128], 16)
    return spender, amount


def _format_approval_alert(
    wallet: str,
    token_contract: str,
    spender: str,
    amount: int,
    tx_hash: str,
) -> str:
    short_wallet  = f"{wallet[:6]}\\.\\.\\."  + wallet[-4:]
    short_spender = f"{spender[:6]}\\.\\.\\." + spender[-4:]
    short_token   = f"{token_contract[:6]}\\.\\.\\." + token_contract[-4:]
    tx_link       = f"[View tx](https://etherscan\\.io/tx/{tx_hash})"

    if amount >= UNLIMITED_THRESHOLD:
        amount_str = "⚠️ *UNLIMITED*"
        warning    = (
            "\n\n🚨 *Unlimited approvals allow a dApp to drain your entire token balance\\. "
            "If you did not intentionally set this, revoke it immediately at revoke\\.cash*"
        )
    else:
        amount_str = f"`{amount:,}`"
        warning    = ""

    return (
        f"🔐 *Token Approval Detected*\n\n"
        f"*Wallet:* `{short_wallet}`\n"
        f"*Token contract:* `{short_token}`\n"
        f"*Spender approved:* `{short_spender}`\n"
        f"*Allowance:* {amount_str}"
        f"{warning}\n\n"
        f"{tx_link}\n\n"
        f"_RelayShield Crypto Shield_"
    )


def _get_all_monitored_evm_wallets() -> list[dict]:
    """Scan relayshield_monitored_wallets for EVM addresses (0x prefix)."""
    table = dynamodb.Table(MONITORED_WALLETS_TABLE)
    items = []
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


def _update_last_block(wallet_address: str, block: int) -> None:
    dynamodb.Table(MONITORED_WALLETS_TABLE).update_item(
        Key={"wallet_address": wallet_address},
        UpdateExpression="SET last_approval_block = :b",
        ExpressionAttributeValues={":b": Decimal(block)},
    )


def lambda_handler(event: dict, context) -> dict:
    try:
        current_block = _get_latest_block()
    except Exception as exc:
        logger.error("Failed to fetch latest block: %s", exc)
        return {"statusCode": 500, "body": "block fetch failed"}

    # Scan ~15 minutes of blocks back (~75 blocks at 12s/block) as default window
    default_lookback = 75
    to_block_hex   = hex(current_block)

    wallets = _get_all_monitored_evm_wallets()
    logger.info("Checking %d EVM wallets for approval events", len(wallets))

    for wallet_item in wallets:
        address     = wallet_item.get("wallet_address", "").lower()
        user_id     = wallet_item.get("user_id")
        last_block  = int(wallet_item.get("last_approval_block") or (current_block - default_lookback))
        from_block_hex = hex(last_block + 1)

        if last_block >= current_block:
            continue

        user = _get_user(user_id) if user_id else None
        if not user:
            continue
        chat_id = user.get("telegram_chat_id")
        if not chat_id:
            continue

        txs = _get_outbound_txs(address, from_block_hex, to_block_hex)
        for tx in txs:
            tx_hash = tx.get("hash", "")
            if not tx_hash:
                continue

            input_data = _get_tx_input(tx_hash)
            parsed = _parse_approve(input_data)
            if not parsed:
                continue

            spender, amount = parsed
            token_contract  = tx.get("to", "unknown")

            logger.info(
                "Approval detected — wallet=%s spender=%s amount=%s tx=%s",
                address, spender, amount, tx_hash,
            )

            alert = _format_approval_alert(address, token_contract, spender, amount, tx_hash)
            _send_telegram(int(chat_id), alert)

        _update_last_block(address, current_block)

    return {"statusCode": 200, "body": "ok"}
