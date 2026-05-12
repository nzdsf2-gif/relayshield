"""
RelayShield Token Approval Monitor Lambda

Scans monitored EVM wallets for new ERC-20 token approval transactions
(function selector 0x095ea7b3). Alerts via Telegram when an unlimited
approval (amount = uint256 max) is detected.

Trigger: EventBridge schedule — every 15 minutes
DynamoDB tables read:
  relayshield_monitored_wallets  — wallet_address → user_id,
                                   last_approval_block_eth_mainnet,
                                   last_approval_block_base_mainnet
  relayshield_users              — user_id → telegram_chat_id

Secrets:
  relayshield/alchemy_api_key    — {"api_key": "...", "webhook_id": "...", "signing_key": "..."}
  relayshield/telegram_bot_token — {"telegram_bot_token": "..."}
"""

import json
import logging
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

# Networks to scan — each has its own block tracker in DynamoDB
NETWORKS = ["eth-mainnet", "base-mainnet"]

# Block explorer URLs per network
_EXPLORER_MAP = {
    "eth-mainnet":  "https://etherscan.io/tx/{}",
    "base-mainnet": "https://basescan.org/tx/{}",
}

# Default lookback in blocks when no prior scan recorded (~15 min per network)
_DEFAULT_LOOKBACK = {
    "eth-mainnet":  75,   # ~12s/block
    "base-mainnet": 375,  # ~2s/block
}

# ERC-20 approve(address spender, uint256 amount) function selector
APPROVE_SELECTOR = "0x095ea7b3"
# Treat approvals >= this threshold as "unlimited"
UNLIMITED_THRESHOLD = 2**128

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


def _alchemy_url(network: str) -> str:
    return f"https://{network}.g.alchemy.com/v2/{_alchemy_api_key()}"


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


def _get_latest_block(network: str) -> int:
    url  = _alchemy_url(network)
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []}).encode()
    req  = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    return int(data["result"], 16)


def _get_outbound_txs(network: str, address: str, from_block: str, to_block: str) -> list[dict]:
    url  = _alchemy_url(network)
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
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return data.get("result", {}).get("transfers", [])
    except Exception as exc:
        logger.error("alchemy_getAssetTransfers failed network=%s address=%s: %s", network, address, exc)
        return []


def _get_tx_input(network: str, tx_hash: str) -> str:
    url  = _alchemy_url(network)
    body = json.dumps({
        "jsonrpc": "2.0",
        "id":      1,
        "method":  "eth_getTransactionByHash",
        "params":  [tx_hash],
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        return (data.get("result") or {}).get("input", "")
    except Exception as exc:
        logger.error("eth_getTransactionByHash failed network=%s tx=%s: %s", network, tx_hash, exc)
        return ""


def _parse_approve(input_data: str) -> tuple[str, int] | None:
    if not input_data.startswith(APPROVE_SELECTOR):
        return None
    data = input_data[len(APPROVE_SELECTOR):]
    if len(data) < 128:
        return None
    spender = "0x" + data[24:64]
    amount  = int(data[64:128], 16)
    return spender, amount


def _format_approval_alert(
    network: str,
    wallet: str,
    token_contract: str,
    spender: str,
    amount: int,
    tx_hash: str,
) -> str:
    short_wallet  = f"{wallet[:6]}\\.\\.\\."  + wallet[-4:]
    short_spender = f"{spender[:6]}\\.\\.\\." + spender[-4:]
    short_token   = f"{token_contract[:6]}\\.\\.\\." + token_contract[-4:]
    explorer      = _EXPLORER_MAP.get(network, "https://etherscan.io/tx/{}")
    tx_url        = explorer.format(tx_hash).replace(".", "\\.")
    tx_link       = f"[View tx]({tx_url})"
    network_label = "Base" if network == "base-mainnet" else "Ethereum"

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
        f"*Network:* {network_label}\n"
        f"*Wallet:* `{short_wallet}`\n"
        f"*Token contract:* `{short_token}`\n"
        f"*Spender approved:* `{short_spender}`\n"
        f"*Allowance:* {amount_str}"
        f"{warning}\n\n"
        f"{tx_link}\n\n"
        f"_RelayShield Crypto Shield_"
    )


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


def _block_attr(network: str) -> str:
    return "last_approval_block_" + network.replace("-", "_")


def _update_last_block(wallet_address: str, network: str, block: int) -> None:
    attr = _block_attr(network)
    dynamodb.Table(MONITORED_WALLETS_TABLE).update_item(
        Key={"wallet_address": wallet_address},
        UpdateExpression=f"SET {attr} = :b",
        ExpressionAttributeValues={":b": Decimal(block)},
    )


def lambda_handler(event: dict, context) -> dict:
    wallets = _get_all_monitored_evm_wallets()
    logger.info("Checking %d EVM wallets across %d networks", len(wallets), len(NETWORKS))

    for network in NETWORKS:
        try:
            current_block = _get_latest_block(network)
        except Exception as exc:
            logger.error("Failed to fetch latest block for %s: %s", network, exc)
            continue

        default_lookback = _DEFAULT_LOOKBACK.get(network, 75)
        to_block_hex     = hex(current_block)
        block_attr       = _block_attr(network)

        for wallet_item in wallets:
            address    = wallet_item.get("wallet_address", "").lower()
            user_id    = wallet_item.get("user_id")
            last_block = int(wallet_item.get(block_attr) or (current_block - default_lookback))

            if last_block >= current_block:
                continue

            user = _get_user(user_id) if user_id else None
            if not user:
                continue
            chat_id = user.get("telegram_chat_id")
            if not chat_id:
                continue

            from_block_hex = hex(last_block + 1)
            txs = _get_outbound_txs(network, address, from_block_hex, to_block_hex)

            for tx in txs:
                tx_hash = tx.get("hash", "")
                if not tx_hash:
                    continue

                input_data = _get_tx_input(network, tx_hash)
                parsed     = _parse_approve(input_data)
                if not parsed:
                    continue

                spender, amount = parsed
                token_contract  = tx.get("to", "unknown")

                logger.info(
                    "Approval detected — network=%s wallet=%s spender=%s amount=%s tx=%s",
                    network, address, spender, amount, tx_hash,
                )

                alert = _format_approval_alert(network, address, token_contract, spender, amount, tx_hash)
                _send_telegram(int(chat_id), alert)

            _update_last_block(address, network, current_block)

    return {"statusCode": 200, "body": "ok"}
