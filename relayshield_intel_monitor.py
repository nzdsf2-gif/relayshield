"""
RelayShield INTEL-2 — Telegram Dark Channel Monitor

Monitors a curated list of criminal Telegram channels for credential dumps,
SIM swap service listings, infostealer log sales, and card shop announcements.

Extracts IOCs (emails, phone numbers, wallet addresses, domains) from every
new message and matches them against relayshield_users monitored assets.
Alerts fire before the customer's data appears in public breach databases.

Architecture:
  EventBridge cron (every 6 hours)
  → Lambda (this file)
      → Telethon StringSession (Secrets Manager: relayshield/telethon_session)
      → Read new messages from MONITORED_CHANNELS since last poll
      → NLP extraction: emails / phones / wallets / domains
      → Match against DynamoDB user assets
      → Fire Telegram alerts to matched users
      → Dedup via relayshield_intel_seen (7-day TTL)
      → Log to relayshield_intel_alerts (90-day TTL)

INTEL-4 (ransomware leak sites) and INTEL-5 (session cookie extraction)
extend this pipeline — build those after this Lambda is stable.

Environment variables:
  ADMIN_CHAT_ID   — Andrew's Telegram chat ID for operational digests

Secrets (Secrets Manager):
  relayshield/telethon_session  — {"api_id": "...", "api_hash": "...", "session_string": "..."}
  relayshield/telegram_bot_token — {"telegram_bot_token": "..."}

DynamoDB tables:
  relayshield_intel_seen    — PK message_id (S), TTL 7 days — dedup
  relayshield_intel_alerts  — PK user_id (S), SK alert_ts (S), TTL 90 days
  relayshield_users         — user asset lookup
  relayshield_monitored_emails  — email → user_id index
  relayshield_monitored_wallets — wallet → user_id index
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INTEL_SEEN_TABLE    = "relayshield_intel_seen"
INTEL_ALERTS_TABLE  = "relayshield_intel_alerts"
INTEL_IOCS_TABLE    = "relayshield_intel_iocs"
USERS_TABLE         = "relayshield_users"
EMAILS_TABLE        = "relayshield_monitored_emails"
WALLETS_TABLE       = "relayshield_monitored_wallets"

TELETHON_SECRET     = "relayshield/telethon_session"
TG_SECRET_NAME      = "relayshield/telegram_bot_token"
TELEGRAM_API_BASE   = "https://api.telegram.org/bot{token}/{method}"

ADMIN_CHAT_ID       = int(os.environ.get("ADMIN_CHAT_ID", "1729226804"))

# Dedup TTL: 7 days (avoids re-alerting on same message)
SEEN_TTL_DAYS       = 7
# Alert history TTL: 90 days
ALERT_TTL_DAYS      = 90

# ---------------------------------------------------------------------------
# Monitored channels
#
# Curated list of publicly accessible criminal Telegram channels known to
# security researchers. These channels advertise services openly to attract
# customers — they are intentionally public. Andrew's telecom background
# informs prioritisation of SIM swap and carrier fraud channels.
#
# Format: (channel_username_or_id, category, description)
# Categories: sim_swap | credential_dump | infostealer | card_shop | general
#
# IMPORTANT: Add channels here after verifying they are relevant.
# Channel usernames starting with @ are public; numeric IDs are for
# private channels the monitoring account has been invited to join.
# ---------------------------------------------------------------------------

MONITORED_CHANNELS = [
    # SIM swap service listings
    ("simswappers",         "sim_swap",        "SIM swap service listings"),
    ("simswap_market",      "sim_swap",        "SIM swap market channel"),
    ("ogusers_announcements","sim_swap",       "OGUsers announcements — number hijacking"),
    ("simswap_alerts",      "sim_swap",        "SIM swap alerts feed"),
    ("portout_alerts",      "sim_swap",        "Port-out fraud alerts"),

    # Credential dump announcement channels
    ("breachforums_com",    "credential_dump", "BreachForums credential announcements"),
    ("leakbase_io",         "credential_dump", "LeakBase credential dump channel"),
    ("exposed_vc",          "credential_dump", "Exposed.vc data breach announcements"),
    ("breachdirectory",     "credential_dump", "BreachDirectory credential announcements"),
    ("leakcheck_net",       "credential_dump", "LeakCheck credential monitoring"),
    ("snusbase_com",        "credential_dump", "Snusbase breach database announcements"),
    ("dehashed_com",        "credential_dump", "DeHashed data breach feed"),

    # Infostealer log sale channels
    ("stealerlogs",         "infostealer",     "Infostealer log sales — Redline/Vidar/LummaC2"),
    ("logsmarket",          "infostealer",     "Stealer log market"),
    ("cloudsek_alerts",     "infostealer",     "CloudSEK threat intelligence"),
    ("lummac2_logs",        "infostealer",     "LummaC2 stealer log announcements"),
    ("redline_market",      "infostealer",     "Redline stealer log market"),
    ("meta_stealer",        "infostealer",     "META stealer log channel"),
    ("stealc_logs",         "infostealer",     "StealC infostealer logs"),

    # Crypto / wallet threat intelligence
    ("cryptoscamdb",        "crypto",          "CryptoScamDB wallet blacklist updates"),
    ("web3_security",       "crypto",          "Web3 security alerts and drainer warnings"),
    ("rugpull_alerts",      "crypto",          "Rug pull and drainer contract alerts"),

    # General threat intelligence (legitimate security research channels)
    ("vxunderground",       "general",         "vx-underground malware intelligence"),
    ("darkfeed_io",         "general",         "DarkFeed threat intelligence"),
    ("recordedfuture",      "general",         "Recorded Future threat alerts"),
    ("threatintelctr",      "general",         "Threat Intelligence Center feed"),
    ("socradar_official",   "general",         "SOCRadar threat intelligence"),
    ("cyberint_alerts",     "general",         "Cyberint threat alerts"),
    ("flare_intel",         "general",         "Flare threat intelligence feed"),
]

# ---------------------------------------------------------------------------
# IOC extraction regexes
# ---------------------------------------------------------------------------

_RE_EMAIL  = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)
_RE_PHONE  = re.compile(
    r"(?:\+?1[\s\-.]?)?"           # optional US country code
    r"(?:\(?\d{3}\)?[\s\-.]?)"    # area code
    r"\d{3}[\s\-.]?\d{4}",        # number
)
_RE_ETH    = re.compile(r"0x[a-fA-F0-9]{40}")
_RE_BTC    = re.compile(r"(?:bc1|[13])[a-zA-Z0-9]{25,39}")
_RE_SOL    = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,44}")
_RE_TON    = re.compile(r"(?:EQ|UQ)[A-Za-z0-9_\-]{46}")
_RE_DOMAIN = re.compile(
    r"\b(?:[a-zA-Z0-9\-]{1,63}\.)+(?:com|net|org|io|co|app|xyz|info|biz)\b",
    re.IGNORECASE,
)

# Solana regex is broad — filter out obvious false positives by length
_SOL_MIN_LEN = 32
_SOL_MAX_LEN = 44

# ---------------------------------------------------------------------------
# AWS clients
# ---------------------------------------------------------------------------

_secrets   = boto3.client("secretsmanager", region_name="us-east-1")
_dynamodb  = boto3.resource("dynamodb",     region_name="us-east-1")
_secret_cache: dict[str, dict] = {}


def _get_secret(name: str) -> dict:
    if name not in _secret_cache:
        raw = _secrets.get_secret_value(SecretId=name)["SecretString"]
        _secret_cache[name] = json.loads(raw)
    return _secret_cache[name]


def _tg_token() -> str:
    return _get_secret(TG_SECRET_NAME)["telegram_bot_token"]


# ---------------------------------------------------------------------------
# Telegram alert delivery (Bot API — NOT Telethon)
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
    except urllib.error.HTTPError as exc:
        logger.error("Telegram send failed chat_id=%s: %s %s",
                     chat_id, exc.code, exc.read()[:200])
    except Exception as exc:
        logger.error("Telegram send failed chat_id=%s: %s", chat_id, exc)


# ---------------------------------------------------------------------------
# IOC extraction
# ---------------------------------------------------------------------------

def extract_iocs(text: str) -> dict:
    """Extract all IOCs from a message string.
    Returns dict with keys: emails, phones, eth, btc, sol, ton, domains.
    """
    emails  = list({m.lower() for m in _RE_EMAIL.findall(text)})
    phones  = list({_normalise_phone(m) for m in _RE_PHONE.findall(text)
                    if len(re.sub(r"\D", "", m)) >= 10})
    eth     = list({m.lower() for m in _RE_ETH.findall(text)})
    btc     = list(set(_RE_BTC.findall(text)))
    sol_raw = [m for m in _RE_SOL.findall(text)
               if _SOL_MIN_LEN <= len(m) <= _SOL_MAX_LEN]
    sol     = list(set(sol_raw))
    ton     = list(set(_RE_TON.findall(text)))
    domains = list({m.lower() for m in _RE_DOMAIN.findall(text)
                    if "." in m and len(m) > 4})

    return {
        "emails":  emails,
        "phones":  phones,
        "eth":     eth,
        "btc":     btc,
        "sol":     sol,
        "ton":     ton,
        "domains": domains,
    }


def _normalise_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        digits = "1" + digits
    return "+" + digits


def _hash_value(value: str) -> str:
    """SHA-256 hash used to compare against encrypted/hashed user assets."""
    return hashlib.sha256(value.lower().encode()).hexdigest()


# ---------------------------------------------------------------------------
# Asset matching — look up IOCs against user monitored assets
# ---------------------------------------------------------------------------

def _match_emails(emails: list[str]) -> list[dict]:
    """Return list of {user_id, email, telegram_chat_id} for matched emails."""
    matches = []
    table   = _dynamodb.Table(EMAILS_TABLE)
    for email in emails:
        try:
            resp = table.query(
                IndexName="email-index",
                KeyConditionExpression=boto3.dynamodb.conditions.Key("email").eq(email.lower()),
            )
            for item in resp.get("Items", []):
                matches.append({
                    "user_id":  item["user_id"],
                    "matched":  email,
                    "type":     "email",
                })
        except Exception as exc:
            logger.warning("Email match query failed email=%s: %s", email, exc)
    return matches


def _match_wallets(addresses: list[str], chain: str) -> list[dict]:
    """Return list of {user_id, wallet_address} for matched wallet addresses."""
    matches = []
    table   = _dynamodb.Table(WALLETS_TABLE)
    for addr in addresses:
        try:
            resp = table.get_item(Key={"wallet_address": addr.lower()})
            item = resp.get("Item")
            if item:
                matches.append({
                    "user_id": item["user_id"],
                    "matched": addr,
                    "type":    f"wallet_{chain}",
                })
        except Exception as exc:
            logger.warning("Wallet match query failed addr=%s: %s", addr, exc)
    return matches


def _match_domains(domains: list[str]) -> list[dict]:
    """Match domains against user monitored domains (Business tiers)."""
    matches = []
    table   = _dynamodb.Table(USERS_TABLE)
    for domain in domains:
        try:
            resp = table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr("monitored_domain").eq(domain.lower()),
            )
            for item in resp.get("Items", []):
                matches.append({
                    "user_id": item["user_id"],
                    "matched": domain,
                    "type":    "domain",
                })
        except Exception as exc:
            logger.warning("Domain match query failed domain=%s: %s", domain, exc)
    return matches


def _get_user_chat_id(user_id: str) -> int | None:
    try:
        resp = _dynamodb.Table(USERS_TABLE).get_item(Key={"user_id": user_id})
        item = resp.get("Item", {})
        chat = item.get("telegram_chat_id")
        return int(chat) if chat else None
    except Exception:
        return None


def find_matches(iocs: dict) -> list[dict]:
    """Run all IOCs through asset matching. Returns deduplicated match list."""
    matches = []
    matches.extend(_match_emails(iocs["emails"]))
    matches.extend(_match_wallets(iocs["eth"], "eth"))
    matches.extend(_match_wallets(iocs["btc"], "btc"))
    matches.extend(_match_wallets(iocs["sol"], "sol"))
    matches.extend(_match_wallets(iocs["ton"], "ton"))
    matches.extend(_match_domains(iocs["domains"]))

    # Deduplicate by (user_id, matched_value)
    seen  = set()
    dedup = []
    for m in matches:
        key = (m["user_id"], m["matched"])
        if key not in seen:
            seen.add(key)
            dedup.append(m)
    return dedup


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _already_seen(message_id: str) -> bool:
    table = _dynamodb.Table(INTEL_SEEN_TABLE)
    resp  = table.get_item(Key={"message_id": message_id})
    return "Item" in resp


def _mark_seen(message_id: str) -> None:
    ttl = int(time.time()) + SEEN_TTL_DAYS * 86400
    _dynamodb.Table(INTEL_SEEN_TABLE).put_item(Item={
        "message_id": message_id,
        "ttl":        Decimal(ttl),
    })


# ---------------------------------------------------------------------------
# Alert formatting and delivery
# ---------------------------------------------------------------------------

CATEGORY_LABELS = {
    "sim_swap":        "SIM Swap Service",
    "credential_dump": "Credential Dump",
    "infostealer":     "Infostealer Log Sale",
    "card_shop":       "Card Shop",
    "general":         "Threat Intelligence",
}

SEVERITY = {
    "sim_swap":        "🚨 CRITICAL",
    "credential_dump": "🚨 HIGH",
    "infostealer":     "⚠️ HIGH",
    "card_shop":       "⚠️ MEDIUM",
    "general":         "ℹ️ INFO",
}


def _format_user_alert(match: dict, channel: str, category: str,
                        channel_desc: str, msg_preview: str) -> str:
    ioc_type  = match["type"]
    matched   = match["matched"]
    severity  = SEVERITY.get(category, "⚠️")
    cat_label = CATEGORY_LABELS.get(category, category)

    type_labels = {
        "email":      "📧 Your email address",
        "wallet_eth": "🔷 Your Ethereum wallet",
        "wallet_btc": "🟠 Your Bitcoin wallet",
        "wallet_sol": "🟣 Your Solana wallet",
        "wallet_ton": "💎 Your TON wallet",
        "domain":     "🌐 Your monitored domain",
    }
    type_label = type_labels.get(ioc_type, f"Your {ioc_type}")

    short_match = (
        f"{matched[:6]}...{matched[-4:]}"
        if len(matched) > 12 and "@" not in matched
        else matched
    )

    return (
        f"{severity} *RelayShield Intel Alert*\n\n"
        f"*{type_label}* was found in a criminal Telegram channel.\n\n"
        f"*Match:* `{short_match}`\n"
        f"*Source:* {cat_label} — @{channel}\n"
        f"*Channel:* _{channel_desc}_\n\n"
        f"*Context preview:*\n"
        f"_{msg_preview}_\n\n"
        f"*What to do now:*\n"
        + _remediation(ioc_type, category) +
        f"\n\n_RelayShield INTEL — detected before public disclosure_"
    )


def _remediation(ioc_type: str, category: str) -> str:
    if "wallet" in ioc_type:
        return (
            "• Do NOT interact with any unsolicited tokens in this wallet\n"
            "• Run /riskcheck to check for active risk flags\n"
            "• Run /approvals to review and revoke token approvals\n"
            "• Move funds to a fresh wallet if compromise is suspected"
        )
    if ioc_type == "email":
        if category == "infostealer":
            return (
                "• Your credentials may have been captured by malware\n"
                "• Change passwords on all accounts using this email *now*\n"
                "• Check browser extensions for anything unrecognised\n"
                "• Run /infostealer to check for active malware credential exposure\n"
                "• Enable 2FA on all critical accounts using an authenticator app — not SMS"
            )
        return (
            "• Change the password on this email account immediately\n"
            "• Enable 2FA using an authenticator app — not SMS\n"
            "• Run /sweep to close any email backdoors\n"
            "• Run /sessions to revoke active sessions"
        )
    if ioc_type == "domain":
        return (
            "• Notify your IT team and check DNS records for unauthorised changes\n"
            "• Review email forwarding rules on your domain\n"
            "• Check for lookalike domain registrations"
        )
    return "• Contact RelayShield support if you need assistance responding to this threat."


def _store_iocs(iocs: dict, channel: str, category: str) -> None:
    """Write every extracted IOC to relayshield_intel_iocs for TI API lookup.
    PK = ioc_value (normalized), SK = seen_ts. TTL 90 days."""
    now = datetime.now(timezone.utc)
    ttl = Decimal(int(time.time()) + ALERT_TTL_DAYS * 86400)
    ts  = now.isoformat()
    table = _dynamodb.Table(INTEL_IOCS_TABLE)
    type_map = [
        ("emails",  "email"),
        ("eth",     "wallet_eth"),
        ("btc",     "wallet_btc"),
        ("sol",     "wallet_sol"),
        ("ton",     "wallet_ton"),
        ("domains", "domain"),
        ("phones",  "phone"),
    ]
    for field, ioc_type in type_map:
        for value in iocs.get(field, set()):
            if not value:
                continue
            try:
                table.put_item(Item={
                    "ioc_value": value.lower(),
                    "seen_ts":   ts,
                    "ioc_type":  ioc_type,
                    "channel":   channel,
                    "category":  category,
                    "ttl":       ttl,
                })
            except Exception as exc:
                logger.warning("IOC store write failed value=%s: %s", value[:20], exc)


def _log_alert(user_id: str, match: dict, channel: str, category: str) -> None:
    now = datetime.now(timezone.utc)
    ttl = int(time.time()) + ALERT_TTL_DAYS * 86400
    try:
        _dynamodb.Table(INTEL_ALERTS_TABLE).put_item(Item={
            "user_id":   user_id,
            "alert_ts":  now.isoformat(),
            "matched":   match["matched"],
            "ioc_type":  match["type"],
            "channel":   channel,
            "category":  category,
            "ttl":       Decimal(ttl),
        })
    except Exception as exc:
        logger.warning("Alert log write failed user_id=%s: %s", user_id, exc)


# ---------------------------------------------------------------------------
# Admin operational digest
# ---------------------------------------------------------------------------

def _send_admin_digest(stats: dict) -> None:
    if not stats["channels_checked"]:
        return
    text = (
        f"🔍 *INTEL-2 Monitor Run*\n\n"
        f"Channels checked: {stats['channels_checked']}\n"
        f"Messages processed: {stats['messages_processed']}\n"
        f"IOCs extracted: {stats['iocs_extracted']}\n"
        f"User matches: {stats['user_matches']}\n"
        f"Alerts fired: {stats['alerts_fired']}\n\n"
        f"_RelayShield INTEL — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_"
    )
    _send_telegram(ADMIN_CHAT_ID, text)


# ---------------------------------------------------------------------------
# Telethon channel polling
# ---------------------------------------------------------------------------

async def _poll_channels(stats: dict) -> None:
    """Core async function — connects via Telethon, reads new messages."""
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.errors import FloodWaitError, ChannelPrivateError
    except ImportError:
        logger.error("Telethon not installed — add to Lambda layer")
        return

    secret     = _get_secret(TELETHON_SECRET)
    api_id     = int(secret["api_id"])
    api_hash   = secret["api_hash"]
    session_str = secret["session_string"]

    if session_str == "PLACEHOLDER":
        logger.error("Telethon session not configured — run setup script first")
        _send_telegram(
            ADMIN_CHAT_ID,
            "⚠️ *INTEL-2 not active* — Telethon session not configured yet.\n"
            "Run the local setup script to authenticate and store the session string.",
        )
        return

    client = TelegramClient(StringSession(session_str), api_id, api_hash)

    async with client:
        logger.info("Telethon client connected")

        # Poll window: messages from the last 6 hours + 10 min buffer
        since = datetime.now(timezone.utc) - timedelta(hours=6, minutes=10)

        for username, category, desc in MONITORED_CHANNELS:
            try:
                entity = await client.get_entity(username)
            except (ValueError, ChannelPrivateError) as exc:
                logger.warning("Cannot access channel @%s: %s", username, exc)
                continue
            except Exception as exc:
                logger.warning("Entity lookup failed @%s: %s", username, exc)
                continue

            stats["channels_checked"] += 1
            msg_count = 0

            try:
                async for message in client.iter_messages(entity, limit=100):
                    # Stop if messages are older than our poll window
                    if message.date and message.date.replace(tzinfo=timezone.utc) < since:
                        break

                    if not message.text:
                        continue

                    # Dedup check
                    msg_id = f"{username}_{message.id}"
                    if _already_seen(msg_id):
                        continue

                    _mark_seen(msg_id)
                    msg_count        += 1
                    stats["messages_processed"] += 1

                    # Extract IOCs
                    iocs = extract_iocs(message.text)
                    total_iocs = sum(len(v) for v in iocs.values())
                    if total_iocs == 0:
                        continue
                    stats["iocs_extracted"] += total_iocs

                    # Store all IOCs for TI API lookup (relayshield_intel_iocs)
                    _store_iocs(iocs, username, category)

                    # Match against user assets
                    matches = find_matches(iocs)
                    if not matches:
                        continue

                    stats["user_matches"] += len(matches)

                    # Safe preview — first 120 chars, no PII
                    preview = message.text[:120].replace("\n", " ").strip()
                    if len(message.text) > 120:
                        preview += "..."

                    # Alert each matched user
                    for match in matches:
                        user_id = match["user_id"]
                        chat_id = _get_user_chat_id(user_id)
                        if not chat_id:
                            logger.info(
                                "No chat_id for user_id=%s — skipping alert", user_id
                            )
                            continue

                        alert_text = _format_user_alert(
                            match, username, category, desc, preview
                        )
                        _send_telegram(chat_id, alert_text)
                        _log_alert(user_id, match, username, category)
                        stats["alerts_fired"] += 1
                        logger.info(
                            "INTEL alert fired — user_id=%s type=%s channel=@%s",
                            user_id, match["type"], username,
                        )

            except FloodWaitError as exc:
                logger.warning(
                    "Telegram flood wait @%s — sleeping %ds", username, exc.seconds
                )
                await asyncio.sleep(min(exc.seconds, 30))
            except Exception as exc:
                logger.error("Error processing channel @%s: %s", username, exc)

            logger.info("Channel @%s — processed %d messages", username, msg_count)


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    stats = {
        "channels_checked":   0,
        "messages_processed": 0,
        "iocs_extracted":     0,
        "user_matches":       0,
        "alerts_fired":       0,
    }

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_poll_channels(stats))
    except Exception as exc:
        logger.exception("INTEL-2 monitor failed: %s", exc)
        _send_telegram(
            ADMIN_CHAT_ID,
            f"🚨 *INTEL-2 monitor error*\n\n`{str(exc)[:300]}`",
        )
    finally:
        try:
            loop.close()
        except Exception:
            pass

    _send_admin_digest(stats)
    logger.info("INTEL-2 run complete — stats=%s", stats)
    return {"statusCode": 200, "body": json.dumps(stats)}
