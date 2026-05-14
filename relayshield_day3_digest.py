"""
RelayShield Day 3 Onboarding Digest Lambda

Sends a personalised Day 3 baseline snapshot to every new subscriber
who joined 3 days ago and hasn't yet received this digest.

Two tracks based on subscription_tier:

  Crypto Shield — live GoPlus risk scan + Aave V3 health factor for each
                  monitored wallet; establishes the risk baseline the user
                  can compare against in future monthly digests.

  Business / Personal Shield — shows monitored coverage (emails, domains,
                  phone), any breach alerts detected in the first 3 days,
                  and command reminders to get the most from the service.

Trigger: EventBridge schedule — daily at 10:00 UTC
DynamoDB tables:
  relayshield_users              — scan for eligible users
  relayshield_breach_alerts      — recent breach detections (business track)

Secrets:
  relayshield/alchemy_api_key    — {"api_key": "..."}
  relayshield/telegram_bot_token — {"telegram_bot_token": "..."}

Dedup: sets day3_digest_sent = True on user record after sending.
Window: users whose created_at is between 72 and 96 hours ago.
"""

import json
import logging
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
ALCHEMY_SECRET_NAME  = "relayshield/alchemy_api_key"
TG_SECRET_NAME       = "relayshield/telegram_bot_token"
TELEGRAM_API_BASE    = "https://api.telegram.org/bot{token}/{method}"
GOPLUS_ADDR_URL      = "https://api.gopluslabs.io/api/v1/address_security"
GOPLUS_TOKEN_URL     = "https://api.gopluslabs.io/api/v1/token_security/{chain_id}"
CHAINABUSE_URL       = "https://www.chainabuse.com/api/reports/addresses/{address}"

# Tiers
CRYPTO_TIERS   = {"crypto_shield", "crypto-shield"}
BUSINESS_TIERS = {"business_starter", "starter_domain", "business_basic",
                  "business_shield", "business_shield_pro"}
PERSONAL_TIERS = {"personal_shield"}

# Aave V3 constants
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
# GoPlus helpers
# ---------------------------------------------------------------------------

def _goplus_address_risk(address: str, chain_id: int = 1) -> dict:
    try:
        url = f"{GOPLUS_ADDR_URL}/{address}?chain_id={chain_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read())
        return data.get("result", {})
    except Exception:
        return {}


_GOPLUS_CHAIN_IDS = {"evm": 1, "solana": 101}

_MALICIOUS_FLAGS = {
    "phishing_activities":  "phishing activity",
    "blacklist_doubt":      "blacklisted",
    "darkweb_transactions": "dark web activity",
    "stealing_attack":      "stealing attacks",
    "cybercrime":           "cybercrime",
}


# ---------------------------------------------------------------------------
# Aave V3 health factor
# ---------------------------------------------------------------------------

def _aave_health_factor(wallet: str) -> float | None:
    try:
        url      = _alchemy_url()
        calldata = _GET_USER_ACCOUNT_DATA + wallet.lower().replace("0x", "").zfill(64)
        body     = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "eth_call",
            "params": [{"to": _AAVE_V3_POOL, "data": calldata}, "latest"],
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


# ---------------------------------------------------------------------------
# Chainabuse — TON (and cross-chain) scam address check
# ---------------------------------------------------------------------------

def _chainabuse_risk(address: str) -> dict:
    """Check Chainabuse for community-reported scam activity on an address.
    Returns {'count': N, 'categories': [...]} or {} on failure."""
    try:
        url = CHAINABUSE_URL.format(address=address)
        req = urllib.request.Request(
            url, headers={"User-Agent": "RelayShield/1.0", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read())
        reports = data.get("reports", []) if isinstance(data, dict) else data
        if not reports:
            return {"count": 0, "categories": []}
        categories = list({r.get("category", "") for r in reports if r.get("category")})
        return {"count": len(reports), "categories": categories}
    except Exception as exc:
        logger.warning("Chainabuse check failed address=%s: %s", address, exc)
        return {}


# ---------------------------------------------------------------------------
# Gas baseline — ETH + Base current prices
# ---------------------------------------------------------------------------

def _get_gas_gwei(network: str) -> float | None:
    """Fetch current gas price in gwei for a given Alchemy network slug."""
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
        wei = int(data["result"], 16)
        return round(wei / 1e9, 1)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def _get_eligible_users() -> list[dict]:
    """Return active Telegram users created 72–96 hours ago who haven't
    received the Day 3 digest yet."""
    now        = datetime.now(timezone.utc)
    window_end = now - timedelta(hours=72)
    window_start = now - timedelta(hours=96)

    table  = dynamodb.Table(USERS_TABLE)
    items  = []
    kwargs: dict = {
        "FilterExpression": (
            Attr("active").eq(True) &
            Attr("onboarding_state").eq("ACTIVE") &
            Attr("telegram_chat_id").exists() &
            Attr("day3_digest_sent").ne(True)
        )
    }
    while True:
        resp = table.scan(**kwargs)
        for item in resp.get("Items", []):
            created = item.get("created_at", "")
            if not created:
                continue
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                if window_start <= dt <= window_end:
                    items.append(item)
            except ValueError:
                continue
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return items


def _mark_digest_sent(user_id: str) -> None:
    try:
        dynamodb.Table(USERS_TABLE).update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET day3_digest_sent = :t",
            ExpressionAttributeValues={":t": True},
        )
    except Exception as exc:
        logger.error("Failed to mark day3_digest_sent user_id=%s: %s", user_id, exc)


def _get_wallets_for_user(user_id: str) -> list[dict]:
    """Fetch monitored wallets from relayshield_monitored_wallets table by user_id.
    Falls back to empty list if none found."""
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
        # Deduplicate by normalised address (EVM lowercase, others as-is)
        seen = set()
        deduped = []
        for item in items:
            addr = (item.get("wallet_address") or "").lower()
            if addr and addr not in seen:
                seen.add(addr)
                deduped.append(item)
        return deduped
    except Exception as exc:
        logger.warning("Wallet lookup failed for user_id=%s: %s", user_id, exc)
        return []


def _get_recent_breach_alerts(user_id: str, days: int = 3) -> list[dict]:
    """Return breach alerts for this user in the last N days."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        resp   = dynamodb.Table(BREACH_ALERTS_TABLE).query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("user_id").eq(user_id),
            FilterExpression=Attr("detected_at").gte(cutoff),
        )
        return resp.get("Items", [])
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Crypto Shield — Day 3 message
# ---------------------------------------------------------------------------

def _build_crypto_digest(user: dict) -> str:
    first_name = user.get("first_name", "there")
    # Prefer the separate monitored_wallets table — source of truth for all chains
    wallets = _get_wallets_for_user(user["user_id"])
    if not wallets:
        wallets = user.get("monitored_wallets", [])

    lines = [
        f"👋 Hey {first_name}, it's been 3 days since you activated *Crypto Shield*.\n",
        "Here's your *baseline risk snapshot* — we'll compare against this in your monthly digest.\n",
    ]

    # ── SIM swap monitoring status ──────────────────────────────────────────
    # Phone is stored encrypted — check for phone_hash as proof of registration
    if user.get("phone_hash") or user.get("phone_encrypted"):
        lines.append("📱 *SIM swap monitoring:* ✅ Active\n")
    else:
        lines.append("📱 *SIM swap monitoring:* Not activated — contact support to register your number\n")

    # ── Gas baseline ─────────────────────────────────────────────────────────
    eth_gas  = _get_gas_gwei("eth-mainnet")
    base_gas = _get_gas_gwei("base-mainnet")
    gas_parts = []
    if eth_gas is not None:
        gas_parts.append(f"ETH: *{eth_gas} gwei*")
    if base_gas is not None:
        gas_parts.append(f"Base: *{base_gas} gwei*")
    if gas_parts:
        lines.append(f"⛽ *Gas baseline:* {' | '.join(gas_parts)}\n")

    # ── Wallet risk scans ────────────────────────────────────────────────────
    if not wallets:
        lines.append(
            "📭 *No wallets monitored yet.*\n\n"
            "Add up to 5 wallets with:\n"
            "`/addwallet 0xYourEVMAddress`\n"
            "`/addwallet YourSolanaAddress`\n"
            "`/addwallet EQYourTONAddress`"
        )
    else:
        lines.append(f"🔍 *{len(wallets)} wallet(s) scanned:*\n")
        for w in wallets:
            # relayshield_monitored_wallets uses wallet_address; user record uses address
            address     = w.get("wallet_address") or w.get("address", "")
            chain_type  = w.get("chain_type", "evm")
            chain_label = {"evm": "EVM", "solana": "Solana", "ton": "TON",
                           "bitcoin": "Bitcoin"}.get(chain_type, chain_type.upper())
            short       = f"{address[:6]}...{address[-4:]}" if len(address) > 12 else address

            wallet_lines = [f"\n*{chain_label}* `{short}`"]

            # GoPlus address risk (EVM + Solana)
            goplus_chain_id = _GOPLUS_CHAIN_IDS.get(chain_type)
            if goplus_chain_id:
                risk  = _goplus_address_risk(address, goplus_chain_id)
                flags = [_MALICIOUS_FLAGS[k] for k in _MALICIOUS_FLAGS if risk.get(k) == "1"]
                if flags:
                    wallet_lines.append(f"🚨 Risk flags: {', '.join(flags)}")
                else:
                    wallet_lines.append("✅ No malicious flags detected")
            elif chain_type == "ton":
                # TON — cross-chain scam database check
                cb = _chainabuse_risk(address)
                if cb.get("count", 0) > 0:
                    cats = ", ".join(cb["categories"][:3]) if cb.get("categories") else "scam activity"
                    wallet_lines.append(f"🚨 {cb['count']} scam report(s) found — {cats}")
                else:
                    wallet_lines.append("✅ No scam reports found")
            else:
                wallet_lines.append("ℹ️ Address risk screening not available for this chain")

            # Aave V3 health factor (EVM only)
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

    # ── DeFi vault prompt ────────────────────────────────────────────────────
    lines.append(
        "\n\n🏦 *Using DeFi protocols?*\n"
        "Audit any protocol before depositing:\n"
        "`/checkvault app.aave.com`\n"
        "`/checkvault app.uniswap.org`\n"
        "`/checkvault curve.fi`\n"
    )

    # ── Command reminders ────────────────────────────────────────────────────
    lines.append(
        "*Risk Intelligence commands:*\n"
        "• `/riskcheck` — re-run risk score anytime\n"
        "• `/checktoken <address>` — screen any token before buying\n"
        "• `/checkvault <url>` — audit a DeFi protocol\n"
        "• `/checknft <address>` — NFT collection risk scan\n\n"
        "_RelayShield Crypto Shield_"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Business / Personal Shield — Day 3 message
# ---------------------------------------------------------------------------

def _build_business_digest(user: dict) -> str:
    first_name      = user.get("first_name", "there")
    tier            = user.get("subscription_tier") or user.get("tier", "")
    emails          = user.get("monitored_emails", [])
    domains         = user.get("monitored_domains", [])
    phone           = user.get("monitored_phone") or user.get("phone_number", "")
    breach_alerts   = _get_recent_breach_alerts(user["user_id"], days=3)

    tier_labels = {
        "personal_shield":    "Personal Shield",
        "business_starter":   "Business Starter",
        "starter_domain":     "Starter + Domain",
        "business_basic":     "Business Basic",
        "business_shield":    "Business Shield",
        "business_shield_pro": "Business Shield Pro",
    }
    tier_label = tier_labels.get(tier, "RelayShield")

    lines = [
        f"👋 Hey {first_name}, it's been 3 days since you activated *{tier_label}*.\n",
        "Here's a summary of your *security coverage* and what we've detected so far.\n",
        "*📡 What We're Monitoring:*\n",
    ]

    # Email coverage
    if emails:
        lines.append(f"📧 *{len(emails)} email address(es):*")
        for e in emails[:3]:
            addr = e if isinstance(e, str) else e.get("email", "")
            lines.append(f"  • `{addr}`")
    else:
        lines.append("📧 No email addresses added yet — use `/sweep` to add one")

    # Domain coverage
    if domains:
        lines.append(f"\n🌐 *{len(domains)} domain(s) monitored:*")
        for d in domains[:3]:
            lines.append(f"  • `{d}`")
    elif tier in {"starter_domain", "business_basic", "business_shield", "business_shield_pro"}:
        lines.append("\n🌐 No domains added yet — use `/domain` to add one")

    # Phone coverage
    if phone:
        short_phone = f"...{phone[-4:]}" if len(phone) > 4 else phone
        lines.append(f"\n📱 SIM swap monitoring active for `{short_phone}`")
    else:
        lines.append("\n📱 SIM swap monitoring — no phone number registered yet")

    # Breach detections in first 3 days
    lines.append("\n*🔍 Detections in your first 3 days:*\n")
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
        lines.append("✅ No new breaches detected in your first 3 days.")

    # Command reminders
    lines.append(
        "\n*Quick commands:*\n"
        "• `/breach` — check breach status for all monitored emails\n"
        "• `/sim` — SIM swap status\n"
        "• `/scan <url>` — scan a suspicious link\n"
        "• `/analyse <text>` — analyse a suspicious message\n"
    )

    if domains:
        lines.append("• `/domain` — domain monitoring status\n")

    lines.append("_RelayShield Security_")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context) -> dict:
    # TEST MODE: pass {"_test_chat_id": "123456"} to force a digest using the
    # real DynamoDB user record for that chat ID — no date window check.
    # Optionally pass "_test_tier": "business_starter" to override the tier
    # and preview a different digest track without changing the real record.
    test_chat_id = event.get("_test_chat_id")
    if test_chat_id:
        table = dynamodb.Table(USERS_TABLE)
        resp  = table.scan(
            FilterExpression=Attr("telegram_chat_id").eq(str(test_chat_id))
        )
        items = resp.get("Items", [])
        if not items:
            logger.error("Test mode — no user found for chat_id=%s", test_chat_id)
            return {"statusCode": 404, "body": "user_not_found"}
        test_user = items[0]
        # Allow tier override for previewing alternate digest tracks
        tier_override = event.get("_test_tier")
        if tier_override:
            test_user = dict(test_user)          # don't mutate the real item
            test_user["subscription_tier"] = tier_override
        tier = test_user.get("subscription_tier") or test_user.get("tier", "crypto_shield")
        if tier in CRYPTO_TIERS:
            message = _build_crypto_digest(test_user)
        else:
            message = _build_business_digest(test_user)
        _send_telegram(int(test_chat_id), message)
        logger.info("Day 3 digest TEST sent — chat_id=%s tier=%s", test_chat_id, tier)
        return {"statusCode": 200, "body": "test_sent=1"}

    users = _get_eligible_users()
    logger.info("Day 3 digest — %d eligible users", len(users))

    sent = 0
    for user in users:
        chat_id = user.get("telegram_chat_id")
        if not chat_id:
            continue

        tier = user.get("subscription_tier") or user.get("tier", "")

        try:
            if tier in CRYPTO_TIERS:
                message = _build_crypto_digest(user)
            else:
                message = _build_business_digest(user)

            _send_telegram(int(chat_id), message)
            _mark_digest_sent(user["user_id"])
            sent += 1
            logger.info(
                "Day 3 digest sent — user_id=%s tier=%s",
                user["user_id"], tier,
            )
        except Exception as exc:
            logger.error(
                "Day 3 digest failed — user_id=%s: %s",
                user["user_id"], exc,
            )

    logger.info("Day 3 digest complete — sent=%d / eligible=%d", sent, len(users))
    return {"statusCode": 200, "body": f"sent={sent}"}
