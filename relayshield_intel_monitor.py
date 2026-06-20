"""
RelayShield INTEL-2 / INTEL-5 — Telegram Dark Channel Monitor

Monitors criminal Telegram channels for credential dumps, infostealer log sales,
SIM swap service listings, and card shop announcements.

INTEL-5 (session cookie + OAuth token extraction):
  For ZIP archive attachments in infostealer-category channels, downloads and
  parses Cookies/ (Netscape format) and Passwords/ (URL|user|pass) files.
  Extracted sessions are matched against monitored email domains, stored in
  relayshield_stolen_sessions, and fire CRITICAL alerts to matched users.

Fix 3 — Rekognition OCR:
  Image attachments (JPEG/PNG) from criminal channels are passed through AWS
  Rekognition detect_text. Extracted text is then run through the IOC regex
  pipeline, catching credential dumps posted as screenshots.

Fix 4 — Paste site URL following:
  When a message contains a link to a known paste site (pastebin.com, paste.ee,
  etc.), the Lambda fetches the raw content and extracts IOCs from it.

Architecture:
  EventBridge cron (every 6 hours)
  → Lambda (this file)
      → Telethon StringSession (Secrets Manager: relayshield/telethon_session)
      → Read new messages from active channels since last poll
      → Fix 4: follow paste URLs → extract IOCs from content
      → Fix 3: OCR image attachments → extract IOCs from text
      → INTEL-5: parse ZIP archives → extract stolen sessions
      → NLP extraction: emails / phones / wallets / domains
      → Match against DynamoDB user assets
      → Fire alerts to matched users
      → Dedup via relayshield_intel_seen (7-day TTL)

Environment variables:
  ADMIN_CHAT_ID — Andrew's Telegram chat ID for operational digests

Secrets:
  relayshield/telethon_session   — {"api_id": "...", "api_hash": "...", "session_string": "..."}
  relayshield/telegram_bot_token — {"telegram_bot_token": "..."}

DynamoDB tables:
  relayshield_intel_seen        — PK message_id (S), TTL 7 days
  relayshield_intel_alerts      — PK user_id (S), SK alert_ts (S), TTL 90 days
  relayshield_intel_iocs        — PK ioc_value (S), SK seen_ts (S), TTL 90 days
  relayshield_intel_channels    — PK username (S), active (BOOL) — dynamic channel list
  relayshield_stolen_sessions   — PK session_id (S), email-index GSI, TTL 90 days
  relayshield_users             — user asset lookup
  relayshield_monitored_emails  — email → user_id index
  relayshield_monitored_wallets — wallet → user_id index
"""

import asyncio
import gzip
import hashlib
import io
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INTEL_SEEN_TABLE      = "relayshield_intel_seen"
INTEL_ALERTS_TABLE    = "relayshield_intel_alerts"
INTEL_IOCS_TABLE      = "relayshield_intel_iocs"
INTEL_CHANNELS_TABLE  = "relayshield_intel_channels"
STOLEN_SESSIONS_TABLE  = "relayshield_stolen_sessions"
IDENTITY_GRAPH_TABLE   = "relayshield_identity_graph"
USERS_TABLE           = "relayshield_users"
EMAILS_TABLE          = "relayshield_monitored_emails"
WALLETS_TABLE         = "relayshield_monitored_wallets"

TELETHON_SECRET   = "relayshield/telethon_session"
TG_SECRET_NAME    = "relayshield/telegram_bot_token"
TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"

ADMIN_CHAT_ID  = int(os.environ.get("ADMIN_CHAT_ID", "1729226804"))
SEEN_TTL_DAYS  = 7
ALERT_TTL_DAYS = 90

# INTEL-5: archive size cap
MAX_ARCHIVE_BYTES = 25 * 1024 * 1024   # 25 MB

# Fix 3: image size cap for Rekognition inline bytes
MAX_IMAGE_BYTES = 5 * 1024 * 1024      # 5 MB

# Fix 4: paste sites to follow
_RE_PASTE_URL = re.compile(
    r"https?://(?:www\.)?(?:pastebin\.com|paste\.ee|ghostbin\.com|"
    r"hastebin\.com|dpaste\.com|controlc\.com|rentry\.co|bin\.bz)"
    r"/(?:raw/)?[A-Za-z0-9_\-]+",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# INTEL-5: service severity classification
# ---------------------------------------------------------------------------

SESSION_SEVERITY: list[tuple[str, str, list[str]]] = [
    ("CRITICAL", "Cloud Infrastructure",    ["console.aws.amazon.com", "console.cloud.google.com", "portal.azure.com", "app.cloudflare.com", "cloudflare.com"]),
    ("CRITICAL", "Code Repository / CI-CD", ["github.com", "gitlab.com", "bitbucket.org", "app.circleci.com", "app.travis-ci.com", "argocd"]),
    ("CRITICAL", "Identity Provider",       ["okta.com", "auth0.com", "login.microsoftonline.com", "admin.google.com", "accounts.google.com"]),
    ("HIGH",     "Payment Processor",       ["dashboard.stripe.com", "paypal.com", "braintreegateway.com"]),
    ("HIGH",     "Domain Registrar / DNS",  ["godaddy.com", "namecheap.com", "name.com", "porkbun.com", "domains.google.com", "dnsimple.com"]),
    ("HIGH",     "Security Tooling",        ["falcon.crowdstrike.com", "app.datadoghq.com", "app.pagerduty.com", "splunk.com", "sentinelone.com"]),
    ("HIGH",     "Financial / Accounting",  ["quickbooks.intuit.com", "xero.com", "app.gusto.com"]),
    ("MEDIUM",   "Developer / Infra SaaS",  ["vercel.com", "app.netlify.com", "heroku.com", "render.com", "digitalocean.com"]),
    ("MEDIUM",   "Productivity / CRM",      ["slack.com", "notion.so", "app.hubspot.com", "salesforce.com", "linear.app", "atlassian.net"]),
    ("MEDIUM",   "Communication",           ["zoom.us", "teams.microsoft.com", "discord.com"]),
    ("LOW",      "Consumer / Social",       ["twitter.com", "x.com", "facebook.com", "instagram.com", "reddit.com", "linkedin.com"]),
]

SESSION_COOKIE_NAMES = {
    "github.com":               ["user_session", "dotcom_user", "__Host-user_session_sameSite"],
    "accounts.google.com":      ["SSID", "SID", "HSID", "SAPISID", "LSID"],
    "google.com":               ["SSID", "SID", "HSID", "SAPISID"],
    "login.microsoftonline.com":["ESTSAUTH", "ESTSAUTHPERSISTENT", "buid"],
    "okta.com":                 ["sid", "oktaStateToken"],
    "console.aws.amazon.com":   ["aws-userInfo", "aws-account-alias"],
    "dashboard.stripe.com":     ["__stripe_mid", "session"],
    "cloudflare.com":           ["CF_Authorization", "__cflb"],
    "app.datadoghq.com":        ["DD_AUTH", "session"],
    "slack.com":                ["d", "b"],
    "gitlab.com":               ["_gitlab_session", "known_sign_in"],
    "discord.com":              ["__dcfduid", "locale"],
    "notion.so":                ["token_v2", "notion_browser_id"],
}

# ---------------------------------------------------------------------------
# Monitored channels
#
# Loaded from relayshield_intel_channels DynamoDB at runtime (active=True).
# Hardcoded list is the fallback. Only verified channels remain in the
# hardcoded set — unverified candidates are commented out with a note.
#
# Format: (channel_username, category, description)
# Categories: sim_swap | credential_dump | infostealer | card_shop | general
# ---------------------------------------------------------------------------

MONITORED_CHANNELS = [
    # -------------------------------------------------------------------------
    # CONFIRMED ACCESSIBLE (verified in CloudWatch logs as of June 2026)
    # -------------------------------------------------------------------------

    # Credential dumps
    ("exposed_vc",       "credential_dump", "Exposed.vc — breach announcements"),
    ("breachforums",     "credential_dump", "BreachForums — cybercrime forum announcements"),
    ("leakbase",         "credential_dump", "LeakBase — breach and credential leak tracking"),

    # Infostealer log sales
    ("logsmarket",       "infostealer",     "LogsMarket — stealer log sales (ZIP archives)"),

    # Crypto
    ("cryptoscamdb",     "crypto",          "CryptoScamDB — wallet blacklist updates"),
    ("web3_security",    "crypto",          "Web3 security alerts and drainer warnings"),

    # General threat intelligence
    ("vxunderground",    "general",         "vx-underground — malware intelligence"),
    ("recordedfuture",   "general",         "Recorded Future — threat alerts"),

    # -------------------------------------------------------------------------
    # CANDIDATE CHANNELS — added June 2026, will verify on next run
    # If inaccessible they are silently skipped (ChannelPrivateError/ValueError)
    # -------------------------------------------------------------------------

    # Dark web / breach news channels (post breach data in text format)
    ("DarkWebInformer",  "credential_dump", "Dark Web Informer — breach announcements and IOCs"),
    ("H4ckManac",        "general",         "H4ckManac — OSINT IOC sharing channel"),
    ("breachforums_com", "credential_dump", "BreachForums alternate handle"),
    ("leakbase_io",      "credential_dump", "LeakBase alternate handle"),

    # Additional infostealer channels
    ("stealerlogs",      "infostealer",     "Stealer log sales — Redline/Vidar/LummaC2"),
    ("lummac2_logs",     "infostealer",     "LummaC2 stealer log announcements"),
    ("redline_market",   "infostealer",     "Redline stealer log market"),

    # SIM swap (highly relevant to RS B2C)
    ("simswappers",      "sim_swap",        "SIM swap service listings"),
    ("simswap_market",   "sim_swap",        "SIM swap market channel"),
    ("portout_alerts",   "sim_swap",        "Port-out fraud alerts"),

    # Additional TI
    ("darkfeed_io",      "general",         "DarkFeed threat intelligence"),
    ("socradar_official","general",         "SOCRadar threat intelligence"),
]

# ---------------------------------------------------------------------------
# IOC extraction regexes — Fix 2: expanded TLD list
# ---------------------------------------------------------------------------

_RE_EMAIL  = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)
_RE_PHONE  = re.compile(
    r"(?:\+?1[\s\-.]?)?"
    r"(?:\(?\d{3}\)?[\s\-.]?)"
    r"\d{3}[\s\-.]?\d{4}",
)
_RE_ETH    = re.compile(r"0x[a-fA-F0-9]{40}")
_RE_BTC    = re.compile(r"(?:bc1|[13])[a-zA-Z0-9]{25,39}")
_RE_SOL    = re.compile(r"[1-9A-HJ-NP-Za-km-z]{32,44}")
_RE_TON    = re.compile(r"(?:EQ|UQ)[A-Za-z0-9_\-]{46}")
_RE_DOMAIN = re.compile(
    r"\b(?:[a-zA-Z0-9\-]{1,63}\.)+(?:"
    r"com|net|org|io|co|app|xyz|info|biz|"
    r"ru|me|cc|pw|tk|top|site|online|pro|"
    r"to|su|cx|sh|gg|tv|dev|ai|cloud"
    r")\b",
    re.IGNORECASE,
)
_RE_IPV4   = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
)

_SOL_MIN_LEN = 32
_SOL_MAX_LEN = 44

# ---------------------------------------------------------------------------
# AWS clients
# ---------------------------------------------------------------------------

_secrets     = boto3.client("secretsmanager", region_name="us-east-1")
_dynamodb    = boto3.resource("dynamodb",      region_name="us-east-1")
_rekognition = boto3.client("rekognition",     region_name="us-east-1")   # Fix 3
_secret_cache: dict[str, dict] = {}


def _get_secret(name: str) -> dict:
    if name not in _secret_cache:
        raw = _secrets.get_secret_value(SecretId=name)["SecretString"]
        _secret_cache[name] = json.loads(raw)
    return _secret_cache[name]


def _tg_token() -> str:
    return _get_secret(TG_SECRET_NAME)["telegram_bot_token"]


# ---------------------------------------------------------------------------
# Telegram alert delivery
# ---------------------------------------------------------------------------

def _send_telegram(chat_id: int, text: str) -> None:
    token = _tg_token()
    url   = TELEGRAM_API_BASE.format(token=token, method="sendMessage")
    body  = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
    req   = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as exc:
        logger.error("Telegram send failed chat_id=%s: %s %s", chat_id, exc.code, exc.read()[:200])
    except Exception as exc:
        logger.error("Telegram send failed chat_id=%s: %s", chat_id, exc)


# ---------------------------------------------------------------------------
# Fix 3: Rekognition OCR for image attachments
# ---------------------------------------------------------------------------

async def _extract_image_text(client, message) -> str:
    """Download image attachment and OCR via Rekognition. Returns extracted text."""
    if not message.document:
        return ""
    mime = getattr(message.document, "mime_type", "") or ""
    if mime not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
        return ""
    if message.document.size > MAX_IMAGE_BYTES:
        logger.info("OCR: skipping oversized image msg=%d size=%d", message.id, message.document.size)
        return ""
    try:
        raw = await client.download_media(message, file=bytes)
        resp = _rekognition.detect_text(Image={"Bytes": raw})
        lines = [
            d["DetectedText"] for d in resp.get("TextDetections", [])
            if d["Type"] == "LINE" and d.get("Confidence", 0) >= 70
        ]
        text = "\n".join(lines)
        if text:
            logger.info("OCR: extracted %d chars from msg=%d", len(text), message.id)
        return text
    except Exception as exc:
        logger.warning("OCR failed msg=%d: %s", message.id, exc)
        return ""


# ---------------------------------------------------------------------------
# Fix 4: Paste site URL following
# ---------------------------------------------------------------------------

def _fetch_paste_content(url: str) -> str:
    """Fetch raw text content from a paste site URL. Returns up to 100KB."""
    # Convert to raw URL where known
    if "pastebin.com/" in url and "/raw/" not in url:
        url = url.replace("pastebin.com/", "pastebin.com/raw/")
    if "rentry.co/" in url and "/raw" not in url:
        url = url.rstrip("/") + "/raw"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; RelayShield/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read(100_000)
        return raw.decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.warning("Paste fetch failed url=%s: %s", url[:80], exc)
        return ""


# ---------------------------------------------------------------------------
# IOC extraction
# ---------------------------------------------------------------------------

def _defang(text: str) -> str:
    t = text
    t = re.sub(r"\[at\]",  "@", t, flags=re.IGNORECASE)
    t = re.sub(r"\(at\)",  "@", t, flags=re.IGNORECASE)
    t = re.sub(r"\[\.\]",  ".", t, flags=re.IGNORECASE)
    t = re.sub(r"\(\.\)",  ".", t, flags=re.IGNORECASE)
    t = re.sub(r"\[dot\]", ".", t, flags=re.IGNORECASE)
    t = re.sub(r"\(dot\)", ".", t, flags=re.IGNORECASE)
    t = re.sub(r"hxxp://",  "http://",  t, flags=re.IGNORECASE)
    t = re.sub(r"hxxps://", "https://", t, flags=re.IGNORECASE)
    return t


def extract_iocs(text: str) -> dict:
    text    = _defang(text)
    emails  = list({m.lower() for m in _RE_EMAIL.findall(text)})
    phones  = list({_normalise_phone(m) for m in _RE_PHONE.findall(text)
                    if len(re.sub(r"\D", "", m)) >= 10})
    eth     = list({m.lower() for m in _RE_ETH.findall(text)})
    btc     = list(set(_RE_BTC.findall(text)))
    sol_raw = [m for m in _RE_SOL.findall(text) if _SOL_MIN_LEN <= len(m) <= _SOL_MAX_LEN]
    sol     = list(set(sol_raw))
    ton     = list(set(_RE_TON.findall(text)))
    domains = list({m.lower() for m in _RE_DOMAIN.findall(text) if "." in m and len(m) > 4})
    ips     = list({m for m in _RE_IPV4.findall(text)
                    if not m.startswith(("10.", "192.168.", "172.", "127."))})
    return {
        "emails": emails, "phones": phones,
        "eth": eth, "btc": btc, "sol": sol, "ton": ton,
        "domains": domains, "ips": ips,
    }


def _normalise_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        digits = "1" + digits
    return "+" + digits


def _hash_value(value: str) -> str:
    return hashlib.sha256(value.lower().encode()).hexdigest()


# ---------------------------------------------------------------------------
# Asset matching
# ---------------------------------------------------------------------------

def _match_emails(emails: list[str]) -> list[dict]:
    matches = []
    table   = _dynamodb.Table(EMAILS_TABLE)
    for email in emails:
        try:
            resp = table.query(
                IndexName="email-index",
                KeyConditionExpression=boto3.dynamodb.conditions.Key("email").eq(email.lower()),
            )
            for item in resp.get("Items", []):
                matches.append({"user_id": item["user_id"], "matched": email, "type": "email"})
        except Exception as exc:
            logger.warning("Email match failed email=%s: %s", email, exc)
    return matches


def _match_wallets(addresses: list[str], chain: str) -> list[dict]:
    matches = []
    table   = _dynamodb.Table(WALLETS_TABLE)
    for addr in addresses:
        try:
            resp = table.get_item(Key={"wallet_address": addr.lower()})
            item = resp.get("Item")
            if item:
                matches.append({"user_id": item["user_id"], "matched": addr, "type": f"wallet_{chain}"})
        except Exception as exc:
            logger.warning("Wallet match failed addr=%s: %s", addr, exc)
    return matches


def _match_domains(domains: list[str]) -> list[dict]:
    matches = []
    table   = _dynamodb.Table(USERS_TABLE)
    for domain in domains:
        try:
            resp = table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr("monitored_domain").eq(domain.lower()),
            )
            for item in resp.get("Items", []):
                matches.append({"user_id": item["user_id"], "matched": domain, "type": "domain"})
        except Exception as exc:
            logger.warning("Domain match failed domain=%s: %s", domain, exc)
    return matches


def _get_user_chat_id(user_id: str) -> int | None:
    try:
        resp = _dynamodb.Table(USERS_TABLE).get_item(Key={"user_id": user_id})
        chat = resp.get("Item", {}).get("telegram_chat_id")
        return int(chat) if chat else None
    except Exception:
        return None


def find_matches(iocs: dict) -> list[dict]:
    matches = []
    matches.extend(_match_emails(iocs["emails"]))
    matches.extend(_match_wallets(iocs["eth"], "eth"))
    matches.extend(_match_wallets(iocs["btc"], "btc"))
    matches.extend(_match_wallets(iocs["sol"], "sol"))
    matches.extend(_match_wallets(iocs["ton"], "ton"))
    matches.extend(_match_domains(iocs["domains"]))
    seen, dedup = set(), []
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
    resp = _dynamodb.Table(INTEL_SEEN_TABLE).get_item(Key={"message_id": message_id})
    return "Item" in resp


def _mark_seen(message_id: str) -> None:
    ttl = int(time.time()) + SEEN_TTL_DAYS * 86400
    _dynamodb.Table(INTEL_SEEN_TABLE).put_item(Item={"message_id": message_id, "ttl": Decimal(ttl)})


# ---------------------------------------------------------------------------
# Alert formatting
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


def _format_user_alert(match: dict, channel: str, category: str, channel_desc: str, msg_preview: str) -> str:
    ioc_type   = match["type"]
    matched    = match["matched"]
    severity   = SEVERITY.get(category, "⚠️")
    cat_label  = CATEGORY_LABELS.get(category, category)
    type_labels = {
        "email":      "📧 Your email address",
        "wallet_eth": "🔷 Your Ethereum wallet",
        "wallet_btc": "🟠 Your Bitcoin wallet",
        "wallet_sol": "🟣 Your Solana wallet",
        "wallet_ton": "💎 Your TON wallet",
        "domain":     "🌐 Your monitored domain",
    }
    type_label  = type_labels.get(ioc_type, f"Your {ioc_type}")
    short_match = f"{matched[:6]}...{matched[-4:]}" if len(matched) > 12 and "@" not in matched else matched
    return (
        f"{severity} *RelayShield Intel Alert*\n\n"
        f"*{type_label}* was found in a criminal Telegram channel.\n\n"
        f"*Match:* `{short_match}`\n"
        f"*Source:* {cat_label} — @{channel}\n"
        f"*Channel:* _{channel_desc}_\n\n"
        f"*Context preview:*\n_{msg_preview}_\n\n"
        f"*What to do now:*\n" + _remediation(ioc_type, category) +
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


# ---------------------------------------------------------------------------
# IOC storage and alert logging
# ---------------------------------------------------------------------------

def _store_iocs(iocs: dict, channel: str, category: str) -> None:
    now   = datetime.now(timezone.utc).isoformat()
    ttl   = Decimal(int(time.time()) + ALERT_TTL_DAYS * 86400)
    table = _dynamodb.Table(INTEL_IOCS_TABLE)
    type_map = [
        ("emails", "email"), ("eth", "wallet_eth"), ("btc", "wallet_btc"),
        ("sol", "wallet_sol"), ("ton", "wallet_ton"), ("domains", "domain"),
        ("phones", "phone"), ("ips", "ip"),
    ]
    for field, ioc_type in type_map:
        for value in iocs.get(field, []):
            if not value:
                continue
            try:
                table.put_item(Item={
                    "ioc_value": value.lower(), "seen_ts": now,
                    "ioc_type": ioc_type, "channel": channel,
                    "category": category, "ttl": ttl,
                })
            except Exception as exc:
                logger.warning("IOC store failed value=%s: %s", value[:20], exc)


def _log_alert(user_id: str, match: dict, channel: str, category: str) -> None:
    ttl = int(time.time()) + ALERT_TTL_DAYS * 86400
    try:
        _dynamodb.Table(INTEL_ALERTS_TABLE).put_item(Item={
            "user_id":  user_id,
            "alert_ts": datetime.now(timezone.utc).isoformat(),
            "matched":  match["matched"],
            "ioc_type": match["type"],
            "channel":  channel,
            "category": category,
            "ttl":      Decimal(ttl),
        })
    except Exception as exc:
        logger.warning("Alert log failed user_id=%s: %s", user_id, exc)


# ---------------------------------------------------------------------------
# INTEL-5: Stealer archive parsing
# ---------------------------------------------------------------------------

def _classify_domain(domain: str) -> tuple[str, str]:
    domain = domain.lower().lstrip(".")
    for severity, label, patterns in SESSION_SEVERITY:
        for pat in patterns:
            if pat in domain:
                return severity, label
    return "LOW", "General Web Service"


def _is_session_cookie(domain: str, cookie_name: str) -> bool:
    domain = domain.lower().lstrip(".")
    for known_domain, names in SESSION_COOKIE_NAMES.items():
        if known_domain in domain:
            return cookie_name in names
    session_patterns = ["session", "sess", "token", "auth", "login", "sid",
                        "JSESSIONID", "PHPSESSID", "ASP.NET_SessionId"]
    return any(p.lower() in cookie_name.lower() for p in session_patterns)


def _parse_netscape_cookies(text: str) -> list[dict]:
    results = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain      = parts[0].lstrip(".")
        cookie_name = parts[5]
        low = cookie_name.lower()
        if any(skip in low for skip in ("_ga", "_gid", "_fbp", "_fbc", "utm_", "ajs_", "__gads")):
            continue
        if not _is_session_cookie(domain, cookie_name):
            continue
        severity, category = _classify_domain(domain)
        results.append({"domain": domain, "cookie_name": cookie_name,
                         "severity": severity, "category": category, "type": "cookie"})
    return results


def _parse_passwords_file(text: str) -> list[dict]:
    results = []
    url_re  = re.compile(r"https?://[^\s|]+", re.IGNORECASE)
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        sep   = "\t" if "\t" in line else "|"
        parts = [p.strip() for p in line.split(sep)]
        url   = parts[0] if parts else ""
        if not url.startswith(("http://", "https://")):
            m   = url_re.search(line)
            url = m.group(0) if m else ""
        if not url:
            continue
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.lower().lstrip("www.")
        except Exception:
            continue
        if not domain:
            continue
        severity, category = _classify_domain(domain)
        if severity == "LOW" and category == "General Web Service":
            continue
        results.append({"domain": domain, "severity": severity,
                         "category": category, "type": "credential"})
    return results


def _monitored_email_domains() -> dict[str, list[dict]]:
    domain_map: dict[str, list[dict]] = {}
    try:
        table  = _dynamodb.Table(EMAILS_TABLE)
        kwargs = {"FilterExpression": boto3.dynamodb.conditions.Attr("active").eq(True)}
        while True:
            resp = table.scan(**kwargs)
            for item in resp.get("Items", []):
                email = item.get("email", "")
                if "@" in email:
                    domain = email.split("@", 1)[1].lower()
                    domain_map.setdefault(domain, []).append(item)
            last = resp.get("LastEvaluatedKey")
            if not last:
                break
            kwargs["ExclusiveStartKey"] = last
    except Exception as exc:
        logger.warning("Could not load monitored email domains: %s", exc)
    return domain_map


def _store_stolen_session(session: dict, channel: str, matched_email: str, matched_user_id: str) -> None:
    ttl = int(time.time()) + ALERT_TTL_DAYS * 86400
    try:
        _dynamodb.Table(STOLEN_SESSIONS_TABLE).put_item(Item={
            "session_id":       str(uuid.uuid4()),
            "domain":           session["domain"],
            "session_type":     session["type"],
            "cookie_name":      session.get("cookie_name", ""),
            "severity":         session["severity"],
            "service_category": session["category"],
            "channel_source":   channel,
            "matched_email":    matched_email,
            "matched_user_id":  matched_user_id,
            "ingested_at":      datetime.now(timezone.utc).isoformat(),
            "ttl":              Decimal(ttl),
        })
    except Exception as exc:
        logger.warning("Stolen session write failed domain=%s: %s", session.get("domain"), exc)


def _format_session_alert(email: str, sessions: list[dict], channel: str) -> str:
    by_severity: dict[str, list[dict]] = {}
    for s in sessions:
        by_severity.setdefault(s["severity"], []).append(s)
    lines = [
        "🚨 *CRITICAL — Active Session Hijack Detected*\n",
        f"RelayShield found stolen session data linked to *{email}* "
        f"in a criminal Telegram stealer log archive.\n",
        "*An attacker may have access to these accounts RIGHT NOW — "
        "2FA does NOT protect you once a session cookie is stolen.*\n",
    ]
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        bucket = by_severity.get(sev, [])
        if not bucket:
            continue
        emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "⚪"}.get(sev, "•")
        lines.append(f"\n{emoji} *{sev} risk sessions:*")
        seen_domains: set[str] = set()
        for s in bucket:
            if s["domain"] in seen_domains:
                continue
            seen_domains.add(s["domain"])
            entry = f"  • {s['domain']} ({s['category']})"
            if s["type"] == "cookie" and s.get("cookie_name"):
                entry += f" — `{s['cookie_name']}`"
            lines.append(entry)
    lines.append(
        "\n*Immediate actions — from a clean device:*\n"
        "→ Log out of all sessions for each service listed above\n"
        "→ For Google: security.google.com → Your devices → Sign out all\n"
        "→ For GitHub: Settings → Sessions → Revoke all\n"
        "→ For AWS: IAM Console → revoke temporary credentials\n"
        "→ Rotate any API keys or OAuth tokens for affected services\n\n"
        "Changing your password alone is *not enough* — the stolen session "
        "remains valid until explicitly revoked.\n\n"
        "🛡️ _RelayShield — active session hijack detection_"
    )
    return "\n".join(lines)


async def _process_stealer_archive(client, message, channel: str,
                                    email_domain_map: dict, stats: dict) -> None:
    if message.document.size > MAX_ARCHIVE_BYTES:
        logger.info("INTEL-5: skipping oversized archive @%s size=%d", channel, message.document.size)
        return
    try:
        raw_bytes = await client.download_media(message, file=bytes)
    except Exception as exc:
        logger.warning("INTEL-5: archive download failed @%s msg=%d: %s", channel, message.id, exc)
        return
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw_bytes))
    except zipfile.BadZipFile:
        return
    all_sessions: list[dict] = []
    for name in zf.namelist():
        low_name = name.lower()
        try:
            if "cookies" in low_name and low_name.endswith((".txt", "")):
                raw = zf.read(name).decode("utf-8", errors="ignore")
                all_sessions.extend(_parse_netscape_cookies(raw))
            elif any(kw in low_name for kw in ("password", "login", "credential", "pass")):
                if low_name.endswith((".txt", ".csv", ".log", "")):
                    raw = zf.read(name).decode("utf-8", errors="ignore")
                    all_sessions.extend(_parse_passwords_file(raw))
        except Exception as exc:
            logger.warning("INTEL-5: parse error file=%s: %s", name[:60], exc)
    if not all_sessions:
        return
    seen_keys: set[tuple] = set()
    unique_sessions = []
    for s in all_sessions:
        key = (s["domain"], s["type"], s.get("cookie_name", ""))
        if key not in seen_keys:
            seen_keys.add(key)
            unique_sessions.append(s)
    logger.info("INTEL-5: @%s msg=%d — %d unique sessions parsed", channel, message.id, len(unique_sessions))
    session_domains = {s["domain"] for s in unique_sessions}
    matched_users: dict[str, tuple[str, list[dict]]] = {}
    for email_domain, records in email_domain_map.items():
        relevant = [s for s in unique_sessions
                    if email_domain in s["domain"] or s["domain"] in email_domain]
        if not relevant:
            continue
        for record in records:
            user_id = record.get("user_id", "")
            email   = record.get("email", "")
            if not user_id or not email:
                continue
            if user_id not in matched_users:
                matched_users[user_id] = (email, [])
            matched_users[user_id][1].extend(relevant)
    for user_id, (email, user_sessions) in matched_users.items():
        seen: set[tuple] = set()
        dedup = []
        for s in user_sessions:
            k = (s["domain"], s["type"], s.get("cookie_name", ""))
            if k not in seen:
                seen.add(k)
                dedup.append(s)
        for s in dedup:
            _store_stolen_session(s, channel, email, user_id)
        chat_id = _get_user_chat_id(user_id)
        if chat_id:
            _send_telegram(chat_id, _format_session_alert(email, dedup, channel))
            stats["alerts_fired"] += 1
            logger.info("INTEL-5 session alert fired — user_id=%s sessions=%d", user_id, len(dedup))


# ---------------------------------------------------------------------------
# Channel discovery — invite links
# ---------------------------------------------------------------------------

_RE_TG_INVITE = re.compile(
    r"(?:https?://)?t\.me/(?:\+[a-zA-Z0-9_\-]{16,}|joinchat/[a-zA-Z0-9_\-]+|([a-zA-Z][a-zA-Z0-9_]{3,}))",
    re.IGNORECASE,
)


def _extract_invite_links(text: str, source_channel: str, category: str) -> None:
    if not text:
        return
    now_ts = datetime.now(timezone.utc).isoformat()
    table  = _dynamodb.Table(INTEL_CHANNELS_TABLE)
    for m in _RE_TG_INVITE.finditer(text):
        full_url        = m.group(0)
        public_username = m.group(1)
        is_private      = public_username is None
        key = full_url.lower().replace("https://", "").replace("http://", "")
        username_key = public_username.lower() if public_username else key
        try:
            existing = table.get_item(Key={"username": username_key}).get("Item")
            if existing:
                continue
            table.put_item(Item={
                "username":       username_key,
                "category":       category,
                "description":    f"Discovered in @{source_channel}",
                "first_seen":     now_ts,
                "last_verified":  now_ts,
                "active":         False,
                "invite_url":     full_url,
                "is_private":     is_private,
                "source_channel": source_channel,
            })
            logger.info("New invite link discovered: %s (private=%s) from @%s", full_url, is_private, source_channel)
        except Exception as exc:
            logger.warning("Failed to store invite link %s: %s", full_url[:50], exc)


def _load_channels() -> list[tuple[str, str, str]]:
    """Return active channel list from DynamoDB; fall back to hardcoded list."""
    try:
        table = _dynamodb.Table(INTEL_CHANNELS_TABLE)
        resp  = table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("active").eq(True),
            ProjectionExpression="username, category, description",
        )
        items = resp.get("Items", [])
        if items:
            return [(i["username"], i["category"], i.get("description", "")) for i in items]
    except Exception as exc:
        logger.warning("Could not load channels from DynamoDB, using fallback: %s", exc)
    return MONITORED_CHANNELS


# ---------------------------------------------------------------------------
# Admin digest
# ---------------------------------------------------------------------------

def _send_admin_digest(stats: dict) -> None:
    if not stats["channels_checked"]:
        return
    text = (
        f"🔍 *INTEL-2/5 Monitor Run*\n\n"
        f"Channels checked: {stats['channels_checked']}\n"
        f"Messages processed: {stats['messages_processed']}\n"
        f"IOCs extracted: {stats['iocs_extracted']}\n"
        f"Images OCR'd: {stats.get('images_ocrd', 0)}\n"
        f"Paste URLs followed: {stats.get('pastes_fetched', 0)}\n"
        f"ZIP archives parsed: {stats.get('archives_parsed', 0)}\n"
        f"User matches: {stats['user_matches']}\n"
        f"Alerts fired: {stats['alerts_fired']}\n\n"
        f"_RelayShield INTEL — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_"
    )
    _send_telegram(ADMIN_CHAT_ID, text)


# ---------------------------------------------------------------------------
# Telethon channel polling
# ---------------------------------------------------------------------------

async def _poll_channels(stats: dict) -> None:
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.errors import FloodWaitError, ChannelPrivateError
    except ImportError:
        logger.error("Telethon not installed — add to Lambda layer")
        return

    secret      = _get_secret(TELETHON_SECRET)
    api_id      = int(secret["api_id"])
    api_hash    = secret["api_hash"]
    session_str = secret["session_string"]

    if session_str == "PLACEHOLDER":
        logger.error("Telethon session not configured")
        _send_telegram(ADMIN_CHAT_ID,
            "⚠️ *INTEL-2 not active* — Telethon session not configured.\n"
            "Run the local setup script to authenticate and store the session string.")
        return

    client = TelegramClient(StringSession(session_str), api_id, api_hash)

    # INTEL-5: pre-load monitored email domain map once per run
    email_domain_map = _monitored_email_domains()
    logger.info("INTEL-5: loaded %d monitored email domains", len(email_domain_map))

    async with client:
        logger.info("Telethon client connected")
        since    = datetime.now(timezone.utc) - timedelta(hours=6, minutes=10)
        channels = _load_channels()
        logger.info("Polling %d channels", len(channels))

        for username, category, desc in channels:
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
                    if message.date and message.date.replace(tzinfo=timezone.utc) < since:
                        break

                    msg_id = f"{username}_{message.id}"
                    if _already_seen(msg_id):
                        continue

                    # --- Build text corpus ---
                    msg_text = message.text or ""

                    # Small text/log file attachments
                    if message.document:
                        fname = ""
                        for attr in (message.document.attributes or []):
                            if hasattr(attr, "file_name"):
                                fname = (attr.file_name or "").lower()
                        if fname.endswith((".txt", ".csv", ".log")) and message.document.size < 512_000:
                            try:
                                raw_bytes = await client.download_media(message, file=bytes)
                                msg_text += "\n" + raw_bytes.decode("utf-8", errors="ignore")[:50_000]
                            except Exception as dl_exc:
                                logger.warning("File download failed @%s msg=%d: %s", username, message.id, dl_exc)

                    # Fix 3: OCR image attachments
                    if message.document and not msg_text.strip():
                        ocr_text = await _extract_image_text(client, message)
                        if ocr_text:
                            msg_text += "\n" + ocr_text
                            stats["images_ocrd"] = stats.get("images_ocrd", 0) + 1

                    # Fix 4: Follow paste site URLs in message text
                    if msg_text:
                        for paste_url in _RE_PASTE_URL.findall(msg_text):
                            paste_content = _fetch_paste_content(paste_url)
                            if paste_content:
                                msg_text += "\n" + paste_content
                                stats["pastes_fetched"] = stats.get("pastes_fetched", 0) + 1
                                logger.info("Paste fetched url=%s chars=%d", paste_url[:60], len(paste_content))

                    # INTEL-5: ZIP archive parsing for infostealer channels
                    if category == "infostealer" and message.document and email_domain_map:
                        fname = ""
                        for attr in (message.document.attributes or []):
                            if hasattr(attr, "file_name"):
                                fname = (attr.file_name or "").lower()
                        if fname.endswith(".zip") or (
                            not fname and getattr(message.document, "mime_type", "") in (
                                "application/zip", "application/x-zip-compressed", "application/octet-stream"
                            )
                        ):
                            try:
                                await _process_stealer_archive(client, message, username, email_domain_map, stats)
                                stats["archives_parsed"] = stats.get("archives_parsed", 0) + 1
                            except Exception as arch_exc:
                                logger.warning("INTEL-5 archive failed @%s msg=%d: %s", username, message.id, arch_exc)

                    if not msg_text:
                        continue

                    _mark_seen(msg_id)
                    msg_count += 1
                    stats["messages_processed"] += 1

                    # Channel discovery
                    _extract_invite_links(msg_text, username, category)

                    # IOC extraction
                    iocs       = extract_iocs(msg_text)
                    total_iocs = sum(len(v) for v in iocs.values())
                    if total_iocs == 0:
                        continue
                    stats["iocs_extracted"] += total_iocs
                    _store_iocs(iocs, username, category)

                    # User asset matching + alerts
                    matches = find_matches(iocs)
                    if not matches:
                        continue
                    stats["user_matches"] += len(matches)
                    preview = msg_text[:120].replace("\n", " ").strip()
                    if len(msg_text) > 120:
                        preview += "..."
                    for match in matches:
                        user_id = match["user_id"]
                        chat_id = _get_user_chat_id(user_id)
                        if not chat_id:
                            continue
                        _send_telegram(chat_id, _format_user_alert(match, username, category, desc, preview))
                        _log_alert(user_id, match, username, category)
                        stats["alerts_fired"] += 1
                        logger.info("INTEL alert fired — user_id=%s type=%s channel=@%s",
                                    user_id, match["type"], username)

            except FloodWaitError as exc:
                logger.warning("Telegram flood wait @%s — sleeping %ds", username, exc.seconds)
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
        "images_ocrd":        0,
        "pastes_fetched":     0,
        "archives_parsed":    0,
        "user_matches":       0,
        "alerts_fired":       0,
    }
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_poll_channels(stats))
    except Exception as exc:
        logger.exception("INTEL-2/5 monitor failed: %s", exc)
        _send_telegram(ADMIN_CHAT_ID, f"🚨 *INTEL-2/5 monitor error*\n\n`{str(exc)[:300]}`")
    finally:
        try:
            loop.close()
        except Exception:
            pass
    _send_admin_digest(stats)
    logger.info("INTEL-2 run complete — stats=%s", stats)
    return {"statusCode": 200, "body": json.dumps(stats)}
