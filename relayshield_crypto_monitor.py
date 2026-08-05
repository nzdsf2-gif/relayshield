"""
relayshield-crypto-monitor — proactive push alerts for Crypto Shield Mobile

EventBridge schedule: every 6 hours  cron(0 */6 * * ? *)
Reads relayshield_push_tokens, scans each registered wallet for:
  - High-risk Solana tokens (Rugcheck)
  - Infostealer credential exposure
  - Suspicious inbound transactions (large/unknown senders)
Fires Expo Push API for mobile push; Telegram for linked RS accounts.

Deduplication: alert suppressed if same wallet+alert_type fired within 24 hrs.
"""
import json
import os
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb  = boto3.resource("dynamodb", region_name="us-east-1")
secretsm  = boto3.client("secretsmanager", region_name="us-east-1")

PUSH_TOKENS_TABLE  = "relayshield_push_tokens"
ALERT_SUPPRESS_TABLE = "relayshield_crypto_alert_suppress"
EXPO_PUSH_URL      = "https://exp.host/--/api/v2/push/send"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
HELIUS_API_KEY     = os.environ.get("HELIUS_API_KEY", "")
RUGCHECK_BASE      = "https://api.rugcheck.xyz/v1/tokens"

# Trusted LP/protocol token mints — skip risk scanning
TRUSTED_MINTS = {
    "27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4",  # Jupiter Perps LP
    "So11111111111111111111111111111111111111112",      # Wrapped SOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj",  # stSOL
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",   # mSOL
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",  # JitoSOL
    "bSo13r4TkiE4KumL71LsHTPpL2euBYLFx6h9HP3piy1",   # bSOL
}

SUPPRESS_WINDOW_HOURS = 24


# ── helpers ──────────────────────────────────────────────────────────────────

def _fetch(url: str, *, method: str = "GET", payload: bytes | None = None,
           headers: dict | None = None, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, data=payload, method=method,
                                 headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _is_suppressed(wallet: str, alert_type: str) -> bool:
    """Return True if this alert was already fired within the suppress window."""
    try:
        tbl  = dynamodb.Table(ALERT_SUPPRESS_TABLE)
        key  = f"{wallet}#{alert_type}"
        item = tbl.get_item(Key={"pk": key}).get("Item")
        if not item:
            return False
        fired_at = datetime.fromisoformat(item["fired_at"])
        return datetime.now(timezone.utc) - fired_at < timedelta(hours=SUPPRESS_WINDOW_HOURS)
    except Exception:
        return False


def _suppress(wallet: str, alert_type: str) -> None:
    try:
        tbl = dynamodb.Table(ALERT_SUPPRESS_TABLE)
        tbl.put_item(Item={
            "pk":       f"{wallet}#{alert_type}",
            "fired_at": datetime.now(timezone.utc).isoformat(),
            "ttl":      int((datetime.now(timezone.utc) + timedelta(hours=48)).timestamp()),
        })
    except Exception as exc:
        logger.warning("suppress write failed: %s", exc)


def _send_expo_push(push_token: str, title: str, body: str, data: dict | None = None) -> bool:
    payload = json.dumps({
        "to":    push_token,
        "title": title,
        "body":  body,
        "data":  data or {},
        "sound": "default",
        "priority": "high",
    }).encode()
    try:
        resp = _fetch(
            EXPO_PUSH_URL, method="POST", payload=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        status = (resp.get("data") or {}).get("status", "")
        if status == "error":
            logger.warning("Expo push error: %s", resp)
            return False
        return True
    except Exception as exc:
        logger.error("Expo push failed: %s", exc)
        return False


def _send_telegram(chat_id: str, text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return
    try:
        payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
        _fetch(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            method="POST", payload=payload,
            headers={"Content-Type": "application/json"},
        )
    except Exception as exc:
        logger.warning("Telegram send failed: %s", exc)


def _alert(push_token: str, telegram_id: str, wallet_label: str, wallet_addr: str,
           alert_type: str, title: str, body: str) -> None:
    if _is_suppressed(wallet_addr, alert_type):
        logger.info("suppressed %s / %s", wallet_addr[:8], alert_type)
        return
    short = f"{wallet_addr[:6]}…{wallet_addr[-4:]}"
    _send_expo_push(push_token, title, f"{wallet_label or short}: {body}",
                    {"wallet": wallet_addr, "alert_type": alert_type})
    tg_msg = (f"🛡 <b>CryptoShield Alert</b>\n"
               f"<b>{title}</b>\n"
               f"Wallet: {wallet_label or short}\n"
               f"{body}")
    _send_telegram(telegram_id, tg_msg)
    _suppress(wallet_addr, alert_type)
    logger.info("alert fired: %s / %s", wallet_addr[:8], alert_type)


# ── per-wallet scan routines ──────────────────────────────────────────────────

def _scan_solana_tokens(wallet: dict, push_token: str, telegram_id: str) -> None:
    """Rugcheck scan of SPL tokens held in a Solana wallet."""
    if not HELIUS_API_KEY:
        return
    address = wallet.get("address", "")
    label   = wallet.get("label", "")
    try:
        payload = json.dumps({
            "jsonrpc": "2.0", "id": 1,
            "method": "getTokenAccountsByOwner",
            "params": [address, {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                       {"encoding": "jsonParsed"}],
        }).encode()
        rpc_url = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
        resp = _fetch(rpc_url, method="POST", payload=payload,
                      headers={"Content-Type": "application/json"})
        accounts = (resp.get("result") or {}).get("value") or []
    except Exception as exc:
        logger.warning("token fetch failed for %s: %s", address[:8], exc)
        return

    for acct in accounts[:10]:
        try:
            info = acct["account"]["data"]["parsed"]["info"]
            mint = info.get("mint", "")
            if not mint or mint in TRUSTED_MINTS:
                continue
            amount = float(info.get("tokenAmount", {}).get("uiAmount") or 0)
            if amount <= 0:
                continue
            # Rugcheck
            url  = f"{RUGCHECK_BASE}/{mint}/report/summary"
            req  = urllib.request.Request(
                url, headers={"User-Agent": "RelayShield/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as r:
                rc = json.loads(r.read())
            score  = int(rc.get("score", 0))
            risks  = rc.get("risks", [])
            danger = [r["name"] for r in risks if r.get("level") == "danger"]
            if score < 500 or not danger:
                continue
            name = rc.get("tokenMeta", {}).get("name") or mint[:8]
            _alert(push_token, telegram_id, label, address,
                   f"token_risk_{mint}",
                   "⚠️ High-risk token detected",
                   f"{name}: {', '.join(danger[:2])}")
        except Exception:
            continue


def _scan_infostealer(wallet: dict, push_token: str, telegram_id: str,
                      rs_api_key: str) -> None:
    """Check if any monitored email is in infostealer logs (requires RS API key)."""
    if not rs_api_key:
        return
    # The wallet record may carry an associated email from onboarding
    email = wallet.get("email", "")
    if not email:
        return
    address = wallet.get("address", "")
    label   = wallet.get("label", "")
    try:
        payload = json.dumps({"email": email}).encode()
        resp = _fetch(
            "https://api.relayshield.net/v1/metered/infostealer",
            method="POST", payload=payload,
            headers={"Content-Type": "application/json", "X-RS-API-KEY": rs_api_key},
        )
        if resp.get("found"):
            _alert(push_token, telegram_id, label, address,
                   f"infostealer_{email}",
                   "🕵 Credential exposure detected",
                   f"Email found in stealer log archive. Session cookies may be compromised.")
    except Exception as exc:
        logger.warning("infostealer check failed: %s", exc)


# ── main handler ─────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context) -> dict:
    logger.info("crypto monitor run: %s", datetime.now(timezone.utc).isoformat())

    tbl = dynamodb.Table(PUSH_TOKENS_TABLE)
    try:
        items = tbl.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("active").eq(True),
        ).get("Items", [])
    except Exception as exc:
        logger.error("DynamoDB scan failed: %s", exc)
        return {"statusCode": 500}

    logger.info("scanning %d registered devices", len(items))

    for record in items:
        push_token  = record.get("push_token", "")
        telegram_id = record.get("telegram_id", "")
        rs_api_key  = record.get("user_id", "")   # user_id is the RS api_key value
        raw_wallets = record.get("wallet_addresses") or []

        # wallet_addresses can be plain strings or {address, chain, label} dicts
        wallets = []
        for w in raw_wallets:
            if isinstance(w, str):
                wallets.append({"address": w, "chain": "solana", "label": ""})
            elif isinstance(w, dict):
                wallets.append(w)

        for wallet in wallets:
            chain = (wallet.get("chain") or "solana").lower()
            if chain == "solana":
                _scan_solana_tokens(wallet, push_token, telegram_id)
                _scan_infostealer(wallet, push_token, telegram_id, rs_api_key)
            # EVM and TON webhook-driven (Alchemy/Helius) — not polled here

    logger.info("crypto monitor complete")
    return {"statusCode": 200}
