"""
RelayShield Monthly Security Digest Lambda

Sends a personalised monthly security summary to every active Telegram
subscriber on the 1st of each month.

Two tracks based on subscription tier:

  Crypto Shield — current wallet risk scores vs stored baseline,
                  Aave V3 health factor, gas baseline, any breach
                  alerts this month, command reminders.

  Business / Personal Shield — breach detections this month,
                  SIM swap monitoring status, domain alert summary
                  (domain tiers), command reminders.

Trigger: EventBridge schedule — 1st of each month at 10:00 UTC
  cron(0 10 1 * ? *)

DynamoDB tables:
  relayshield_users              — scan for all active users
  relayshield_monitored_wallets  — wallet risk data
  relayshield_breach_alerts      — breach detections this month

Secrets:
  relayshield/alchemy_api_key    — {"api_key": "..."}
  relayshield/telegram_bot_token — {"telegram_bot_token": "..."}

Dedup: sets last_monthly_digest_sent = "YYYY-MM" on user record.
       Skips users already sent a digest this calendar month.
"""

import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

secrets_client = boto3.client("secretsmanager")
dynamodb       = boto3.resource("dynamodb")

USERS_TABLE             = "relayshield_users"
MONITORED_WALLETS_TABLE = "relayshield_monitored_wallets"
BREACH_ALERTS_TABLE     = "relayshield_breach_alerts"
ALCHEMY_SECRET_NAME     = "relayshield/alchemy_api_key"
TG_SECRET_NAME          = "relayshield/telegram_bot_token"
TELEGRAM_API_BASE       = "https://api.telegram.org/bot{token}/{method}"
GOPLUS_ADDR_URL         = "https://api.gopluslabs.io/api/v1/address_security"
TONAPI_ACCOUNTS_URL     = "https://tonapi.io/v2/accounts/{address}"
BLOCKSTREAM_API         = "https://blockstream.info/api"

CRYPTO_TIERS   = {"crypto_shield", "crypto-shield"}
BUSINESS_TIERS = {"business_starter", "starter_domain", "business_basic",
                  "business_shield", "business_shield_pro"}
DOMAIN_TIERS   = {"starter_domain", "business_basic", "business_shield", "business_shield_pro"}

_GOPLUS_CHAIN_IDS = {"evm": 1, "solana": 101}
_MALICIOUS_FLAGS  = {
    "phishing_activities":  "phishing activity",
    "blacklist_doubt":      "blacklisted",
    "darkweb_transactions": "dark web activity",
    "stealing_attack":      "stealing attacks",
    "cybercrime":           "cybercrime",
}
_AAVE_V3_POOL          = "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"
_GET_USER_ACCOUNT_DATA = "0xbf92857c"
_RAY                   = 10 ** 27

_secret_cache: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

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
# Risk helpers
# ---------------------------------------------------------------------------

def _goplus_address_risk(address: str, chain_id: int = 1) -> dict:
    try:
        url = f"{GOPLUS_ADDR_URL}/{address}?chain_id={chain_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            return json.loads(resp.read()).get("result", {})
    except Exception:
        return {}


def _tonapi_risk(address: str) -> dict:
    try:
        url = TONAPI_ACCOUNTS_URL.format(address=urllib.parse.quote(address, safe="-_="))
        req = urllib.request.Request(
            url, headers={"User-Agent": "RelayShield/1.0", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        return {
            "ok":         True,
            "is_scam":    data.get("is_scam", False),
            "interfaces": data.get("interfaces", []),
            "status":     data.get("status", ""),
        }
    except Exception as exc:
        logger.warning("TONAPI risk check failed address=%s: %s", address, exc)
        return {"ok": False}


def _bitcoin_risk(address: str) -> dict:
    try:
        url = f"{BLOCKSTREAM_API}/address/{address}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        chain   = data.get("chain_stats", {})
        mempool = data.get("mempool_stats", {})
        tx_count     = chain.get("tx_count", 0)
        balance_sats = chain.get("funded_txo_sum", 0) - chain.get("spent_txo_sum", 0)
        mempool_txs  = mempool.get("tx_count", 0)
        flags = []
        if tx_count == 0:
            flags.append("never_used")
        if tx_count > 500:
            flags.append("high_tx_volume")
        if balance_sats == 0 and tx_count > 10:
            flags.append("zero_balance_high_activity")
        if 0 < balance_sats < 1000:
            flags.append("dust_balance")
        if mempool_txs > 0:
            flags.append("unconfirmed_transactions")
        return {
            "ok": True, "flags": flags,
            "tx_count": tx_count,
            "balance_btc": round(balance_sats / 100_000_000, 8),
            "mempool_txs": mempool_txs,
        }
    except Exception as exc:
        logger.warning("Blockstream risk check failed address=%s: %s", address, exc)
        return {"ok": False}


def _aave_health_factor(wallet: str) -> float | None:
    try:
        url      = _alchemy_url()
        calldata = _GET_USER_ACCOUNT_DATA + wallet.lower().replace("0x", "").zfill(64)
        body     = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "eth_call",
            "params":  [{"to": _AAVE_V3_POOL, "data": calldata}, "latest"],
        }).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            result = json.loads(resp.read()).get("result", "0x").replace("0x", "")
        if len(result) < 6 * 64:
            return None
        raw = int(result[5 * 64: 6 * 64], 16)
        if raw == 0 or raw >= 2 ** 128:
            return None
        return raw / _RAY
    except Exception:
        return None


def _get_defi_security_events() -> list[dict]:
    """
    Fetch recent DeFi hacks from DeFiLlama — free, no API key.
    Returns up to 3 events from the last 30 days, sorted by USD lost descending.
    Each item: {"name": str, "date": str, "amount_m": float, "category": str}
    """
    try:
        url = "https://defillama.com/api/v2/hacks"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        # data is a list of hack objects
        hacks = data if isinstance(data, list) else data.get("events", data.get("hacks", []))
        cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=30)).timestamp()
        recent = []
        for h in hacks:
            # DeFiLlama uses "date" as a Unix timestamp (seconds)
            ts = h.get("date", 0)
            if isinstance(ts, str):
                try:
                    ts = int(ts)
                except ValueError:
                    continue
            if ts < cutoff_ts:
                continue
            amount = h.get("amount", 0) or 0
            recent.append({
                "name":     h.get("name") or h.get("projectName", "Unknown"),
                "date":     datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%b %d"),
                "amount_m": round(amount / 1_000_000, 1),
                "category": h.get("category") or h.get("type", ""),
            })
        recent.sort(key=lambda x: x["amount_m"], reverse=True)
        return recent[:3]
    except Exception as exc:
        logger.warning("DeFiLlama hacks fetch failed: %s", exc)
        return []


def _get_gas_gwei(network: str) -> float | None:
    try:
        api_key = _get_secret_json(ALCHEMY_SECRET_NAME, "api_key")
        url     = f"https://{network}.g.alchemy.com/v2/{api_key}"
        body    = json.dumps({
            "jsonrpc": "2.0", "id": 1,
            "method": "eth_gasPrice", "params": [],
        }).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read())
        return round(int(data["result"], 16) / 1e9, 1)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def _get_all_active_users() -> list[dict]:
    """Return all active Telegram users who haven't received a digest this month."""
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
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
            if item.get("last_monthly_digest_sent") != current_month:
                items.append(item)
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return items


def _mark_digest_sent(user_id: str) -> None:
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        dynamodb.Table(USERS_TABLE).update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET last_monthly_digest_sent = :m",
            ExpressionAttributeValues={":m": current_month},
        )
    except Exception as exc:
        logger.error("Failed to mark monthly digest sent user_id=%s: %s", user_id, exc)


def _get_wallets_for_user(user_id: str) -> list[dict]:
    try:
        table  = dynamodb.Table(MONITORED_WALLETS_TABLE)
        items  = []
        kwargs: dict = {"FilterExpression": Attr("user_id").eq(user_id)}
        while True:
            resp = table.scan(**kwargs)
            items.extend(resp.get("Items", []))
            last = resp.get("LastEvaluatedKey")
            if not last:
                break
            kwargs["ExclusiveStartKey"] = last
        seen, deduped = set(), []
        for item in items:
            addr = (item.get("wallet_address") or "").lower()
            if addr and addr not in seen:
                seen.add(addr)
                deduped.append(item)
        return deduped
    except Exception as exc:
        logger.warning("Wallet lookup failed user_id=%s: %s", user_id, exc)
        return []


def _get_monthly_breach_alerts(user_id: str) -> list[dict]:
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        resp   = dynamodb.Table(BREACH_ALERTS_TABLE).query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("user_id").eq(user_id),
            FilterExpression=Attr("detected_at").gte(cutoff),
        )
        return resp.get("Items", [])
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Crypto Shield — monthly message
# ---------------------------------------------------------------------------

def _build_crypto_digest(user: dict, month_label: str) -> str:
    first_name = user.get("first_name", "there")
    wallets    = _get_wallets_for_user(user["user_id"])
    if not wallets:
        wallets = user.get("monitored_wallets", [])

    lines = [
        f"📊 *{first_name}'s Monthly Crypto Shield Report — {month_label}*\n",
        "_Your security snapshot for the past 30 days._\n",
    ]

    # SIM swap status
    if user.get("phone_hash") or user.get("phone_encrypted"):
        lines.append("📱 *SIM swap monitoring:* ✅ Active\n")
    else:
        lines.append("📱 *SIM swap monitoring:* ⚠️ Not activated — use /sim to check\n")

    # Breach alerts this month
    breach_alerts = _get_monthly_breach_alerts(user["user_id"])
    if breach_alerts:
        lines.append(f"🚨 *{len(breach_alerts)} new breach alert(s) this month*")
        for alert in breach_alerts[:3]:
            email  = alert.get("email", "")
            source = alert.get("breach_name") or alert.get("source", "Unknown source")
            short  = f"{email[:4]}...{email.split('@')[-1]}" if "@" in email else email
            lines.append(f"  • `{short}` — {source}")
        if len(breach_alerts) > 3:
            lines.append(f"  _...and {len(breach_alerts) - 3} more_")
        lines.append("→ Run `/breach` for details and remediation.\n")
    else:
        lines.append("✅ *No new breach alerts this month.*\n")

    # Gas baseline
    eth_gas  = _get_gas_gwei("eth-mainnet")
    base_gas = _get_gas_gwei("base-mainnet")
    gas_parts = []
    if eth_gas is not None:
        gas_parts.append(f"ETH: *{eth_gas} gwei*")
    if base_gas is not None:
        gas_parts.append(f"Base: *{base_gas} gwei*")
    if gas_parts:
        lines.append(f"⛽ *Current gas:* {' | '.join(gas_parts)}\n")

    # Wallet risk scans
    if not wallets:
        lines.append(
            "📭 *No wallets monitored.*\n"
            "Add up to 5 with `/addwallet <address>`\n"
            "Supports Bitcoin, EVM, Solana, and TON."
        )
    else:
        lines.append(f"🔍 *{len(wallets)} wallet(s) — current risk scores:*\n")
        for w in wallets:
            address    = w.get("wallet_address") or w.get("address", "")
            chain_type = w.get("chain_type", "evm")
            chain_label = {"evm": "EVM", "solana": "Solana",
                           "ton": "TON", "bitcoin": "Bitcoin"}.get(chain_type, chain_type.upper())
            short = f"{address[:6]}...{address[-4:]}" if len(address) > 12 else address
            stored_risk = (w.get("risk_level") or "LOW").upper()
            risk_badge  = {"HIGH": "🔴", "MEDIUM": "🟡"}.get(stored_risk, "🟢")
            wallet_lines = [f"\n{risk_badge} *{chain_label}* `{short}` — {stored_risk} RISK"]

            if chain_type in ("evm", "solana"):
                goplus_chain_id = _GOPLUS_CHAIN_IDS.get(chain_type)
                risk  = _goplus_address_risk(address, goplus_chain_id)
                flags = [_MALICIOUS_FLAGS[k] for k in _MALICIOUS_FLAGS if risk.get(k) == "1"]
                if flags:
                    wallet_lines.append(f"🚨 Risk flags: {', '.join(flags)}")
                else:
                    wallet_lines.append("✅ No malicious flags")

            elif chain_type == "ton":
                ton_risk = _tonapi_risk(address)
                if ton_risk.get("ok"):
                    if ton_risk.get("is_scam"):
                        wallet_lines.append("🚨 Flagged as scam in TON community database")
                    else:
                        wallet_lines.append("✅ No scam flags in TON community database")
                else:
                    wallet_lines.append("ℹ️ TON risk data temporarily unavailable")

            elif chain_type == "bitcoin":
                btc = _bitcoin_risk(address)
                if btc.get("ok"):
                    if btc["flags"]:
                        wallet_lines.append(f"⚠️ Risk flags: {', '.join(btc['flags'])}")
                    else:
                        wallet_lines.append("✅ No risk flags")
                    wallet_lines.append(f"ℹ️ Balance: {btc['balance_btc']} BTC | Txs: {btc['tx_count']}")
                else:
                    wallet_lines.append("ℹ️ Bitcoin risk data temporarily unavailable")

            if chain_type == "evm":
                hf = _aave_health_factor(address)
                if hf is not None:
                    if hf < 1.2:
                        wallet_lines.append(f"🚨 Aave health factor: {hf:.3f} — liquidation imminent")
                    elif hf < 1.5:
                        wallet_lines.append(f"⚠️ Aave health factor: {hf:.3f} — monitor closely")
                    else:
                        wallet_lines.append(f"✅ Aave health factor: {hf:.3f} — safe")
                else:
                    wallet_lines.append("ℹ️ No active Aave V3 position")

            lines.extend(wallet_lines)

    # DeFi security events this month
    defi_events = _get_defi_security_events()
    if defi_events:
        lines.append("\n\n⚠️ *Notable DeFi Security Events This Month:*\n")
        for ev in defi_events:
            cat  = f" ({ev['category']})" if ev["category"] else ""
            lines.append(f"  • *{ev['name']}*{cat} — ${ev['amount_m']}M lost on {ev['date']}")
        lines.append("_Source: DeFiLlama Hacks Tracker_")
    else:
        lines.append("\n\n✅ *No major DeFi exploits reported in the last 30 days.*")

    lines.append(
        "\n\n*Commands to run this month:*\n"
        "• `/riskcheck` — re-run full wallet risk scan\n"
        "• `/checktoken <address>` — screen a token before buying\n"
        "• `/checkvault <url>` — audit a DeFi protocol\n"
        "• `/sweep` — close any email backdoors\n\n"
        "_RelayShield Crypto Shield_"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Business / Personal Shield — monthly message
# ---------------------------------------------------------------------------

def _build_business_digest(user: dict, month_label: str) -> str:
    first_name    = user.get("first_name", "there")
    tier          = user.get("subscription_tier") or user.get("tier", "")
    emails        = user.get("monitored_emails", [])
    domains       = user.get("monitored_domains", [])
    has_phone     = bool(user.get("phone_hash") or user.get("phone_encrypted"))
    breach_alerts = _get_monthly_breach_alerts(user["user_id"])

    tier_labels = {
        "personal_shield":     "Personal Shield",
        "business_starter":    "Business Starter",
        "starter_domain":      "Starter + Domain",
        "business_basic":      "Business Basic",
        "business_shield":     "Business Shield",
        "business_shield_pro": "Business Shield Pro",
    }
    tier_label = tier_labels.get(tier, "RelayShield")

    lines = [
        f"📊 *{first_name}'s Monthly Security Report — {month_label}*\n",
        f"_Your {tier_label} coverage summary for the past 30 days._\n",
        "*📡 Active Monitoring:*\n",
    ]

    # Email coverage
    if emails:
        lines.append(f"📧 *{len(emails)} email address(es) monitored*")
    else:
        lines.append("📧 No email addresses added — use /breach to add one")

    # SIM swap
    if has_phone:
        lines.append("📱 *SIM swap monitoring:* ✅ Active")
    else:
        lines.append("📱 *SIM swap monitoring:* ⚠️ Not activated — use /sim to check")

    # Domain coverage
    if tier in DOMAIN_TIERS:
        if domains:
            lines.append(f"🌐 *{len(domains)} domain(s) monitored*")
        else:
            lines.append("🌐 No domains added yet — use /domain to add one")

    # Breach detections
    lines.append("\n*🔍 Detections this month:*\n")
    if breach_alerts:
        lines.append(f"⚠️ *{len(breach_alerts)} breach alert(s) detected*")
        for alert in breach_alerts[:3]:
            email  = alert.get("email", "")
            source = alert.get("breach_name") or alert.get("source", "Unknown source")
            short  = f"{email[:4]}...{email.split('@')[-1]}" if "@" in email else email
            lines.append(f"  • `{short}` — {source}")
        if len(breach_alerts) > 3:
            lines.append(f"  _...and {len(breach_alerts) - 3} more_")
        lines.append("\nRun `/breach` for full details and remediation steps.")
    else:
        lines.append("✅ No new breaches detected this month.")

    # Monthly security tip
    lines.append(
        "\n*💡 This month's security reminder:*\n"
        "Run `/sweep` to check for email forwarding rules, inbox filters, "
        "and active sessions that attackers plant after a breach. "
        "These survive password resets.\n"
    )

    lines.append(
        "*Quick commands:*\n"
        "• `/breach` — full breach status\n"
        "• `/sweep` — close email backdoors\n"
        "• `/sim` — SIM swap monitoring status\n"
        "• `/scan <url>` — scan a suspicious link\n"
        "• `/analyse <text>` — analyse a suspicious message\n\n"
        "_RelayShield Security_"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context) -> dict:
    now         = datetime.now(timezone.utc)
    month_label = now.strftime("%B %Y")   # e.g. "May 2026"

    # TEST MODE: pass {"_test_chat_id": "123456"} to preview the digest
    # without date/dedup checks. Optionally pass "_test_tier" to override tier.
    test_chat_id = event.get("_test_chat_id")
    if test_chat_id:
        table = dynamodb.Table(USERS_TABLE)
        resp  = table.scan(FilterExpression=Attr("telegram_chat_id").eq(str(test_chat_id)))
        items = resp.get("Items", [])
        if not items:
            logger.error("Test mode — no user found chat_id=%s", test_chat_id)
            return {"statusCode": 404, "body": "user_not_found"}
        test_user = items[0]
        tier_override = event.get("_test_tier")
        if tier_override:
            test_user = dict(test_user)
            test_user["subscription_tier"] = tier_override
        tier = test_user.get("subscription_tier") or test_user.get("tier", "")
        if tier in CRYPTO_TIERS:
            message = _build_crypto_digest(test_user, month_label)
        else:
            message = _build_business_digest(test_user, month_label)
        _send_telegram(int(test_chat_id), message)
        logger.info("Monthly digest TEST sent — chat_id=%s tier=%s", test_chat_id, tier)
        return {"statusCode": 200, "body": "test_sent=1"}

    users = _get_all_active_users()
    logger.info("Monthly digest — %d eligible users for %s", len(users), month_label)

    sent = 0
    for user in users:
        chat_id = user.get("telegram_chat_id")
        if not chat_id:
            continue
        tier = user.get("subscription_tier") or user.get("tier", "")
        try:
            if tier in CRYPTO_TIERS:
                message = _build_crypto_digest(user, month_label)
            else:
                message = _build_business_digest(user, month_label)
            _send_telegram(int(chat_id), message)
            _mark_digest_sent(user["user_id"])
            sent += 1
            logger.info("Monthly digest sent — user_id=%s tier=%s", user["user_id"], tier)
        except Exception as exc:
            logger.error("Monthly digest failed — user_id=%s: %s", user["user_id"], exc)

    logger.info("Monthly digest complete — sent=%d / eligible=%d", sent, len(users))
    return {"statusCode": 200, "body": f"sent={sent}"}
