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
import base64
import hashlib
import gzip
import hashlib
import io
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError

import relayshield_siem_connector as siem_connector

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INTEL_SEEN_TABLE      = "relayshield_intel_seen"
LOCK_TABLE            = "relayshield_intel_monitor_lock"
LOCK_ID               = "singleton"
LOCK_TTL_SECONDS      = 280  # just under the 300s Lambda timeout
INTEL_ALERTS_TABLE    = "relayshield_intel_alerts"
INTEL_IOCS_TABLE      = "relayshield_intel_iocs"
INTEL_CHANNELS_TABLE  = "relayshield_intel_channels"
STOLEN_SESSIONS_TABLE  = "relayshield_stolen_sessions"
# CORPUS-1, added 2026-08-16. Measured that day: of 489,990 distinct IOCs, only
# 8,171 (1.67%) came from the 90 monitored Telegram channels and 481,819
# (98.33%) from free public feeds any competitor also has. 73 of the 90 active
# channels had produced zero indicators.
#
# The cause was not collection -- every channel is polled every 6 hours without
# failure. The cause is that this pipeline only KEPT data that matched something
# it already knew: a message with no IOC regex hit was dropped by
# `if total_iocs == 0: continue`, and a stolen session was dropped unless it
# matched an existing customer's email. A marketplace sales post ("50k US logs,
# fresh, $200") contains neither, so the single most differentiated content we
# collect was being discarded on arrival.
#
# This table is where that content now lands. It is the differentiated asset:
# "your organisation's credentials are being sold, 50k records, $200, posted
# three hours ago" is something no free feed provides.
MARKETPLACE_LISTINGS_TABLE = "relayshield_marketplace_listings"
IDENTITY_GRAPH_TABLE   = "relayshield_identity_graph"
USERS_TABLE           = "relayshield_users"
EMAILS_TABLE          = "relayshield_monitored_emails"
WALLETS_TABLE         = "relayshield_monitored_wallets"
STOLEN_CARDS_TABLE    = "relayshield_stolen_cards"

TELETHON_SECRET   = "relayshield/telethon_session"
TG_SECRET_NAME    = "relayshield/telegram_bot_token"
TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"

TWILIO_SID_SECRET            = "relayshield/twilio_account_sid"
TWILIO_TOKEN_SECRET          = "relayshield/twilio_auth_token"
TWILIO_FROM_SECRET           = "relayshield/twilio_whatsapp_number"
TWILIO_MESSAGES_URL          = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
SESSION_HIJACK_TEMPLATE_SID  = "HX9cb2b24cadca7fe68623390c74158e3c"

ADMIN_CHAT_ID  = int(os.environ.get("ADMIN_CHAT_ID", "1729226804"))
SEEN_TTL_DAYS  = 7
ALERT_TTL_DAYS = 90

# INTEL-5: archive size cap
MAX_ARCHIVE_BYTES = 25 * 1024 * 1024   # 25 MB

# Fix 3: image size cap for Rekognition inline bytes
MAX_IMAGE_BYTES = 5 * 1024 * 1024      # 5 MB

# Fix 4: paste sites to follow (expanded — includes newer services + Telegram instant view)
_RE_PASTE_URL = re.compile(
    r"https?://(?:www\.)?(?:pastebin\.com|paste\.ee|ghostbin\.com|"
    r"hastebin\.com|dpaste\.com|controlc\.com|rentry\.co|bin\.bz|"
    r"paste\.mozilla\.org|bpaste\.net|pastecode\.io|termbin\.com|"
    r"privatebin\.net|pastes\.io|gist\.github\.com|"
    r"paste\.fo|pasty\.ee|paste\.gg|textbin\.net|temp\.sh|"
    r"paste\.rs|snipli\.com|toptal\.com/developers/hastebin)"
    r"/(?:raw/)?[A-Za-z0-9_\-/]+",
    re.IGNORECASE,
)

# Infostealer log sale price signals — extract record counts and prices from sale posts
_RE_LOG_COUNT  = re.compile(r'(\d[\d,\.]+)\s*(?:logs?|lines?|records?|entries|строк|записей|日志)', re.IGNORECASE)
_RE_LOG_PRICE  = re.compile(r'(?:\$|USD|usdt|BTC|XMR|€)\s*(\d[\d,\.]+)', re.IGNORECASE)

# Telegram forwarded message source extraction
_RE_TG_FORWARD = re.compile(r'(?:Forwarded from|Переслано из|转发自)\s+[@]?([A-Za-z0-9_]+)', re.IGNORECASE)

# ---------------------------------------------------------------------------
# INTEL-5: service severity classification
# ---------------------------------------------------------------------------

SESSION_SEVERITY: list[tuple[str, str, list[str]]] = [
    ("CRITICAL", "Cloud Infrastructure",    ["console.aws.amazon.com", "console.cloud.google.com", "portal.azure.com", "app.cloudflare.com", "cloudflare.com"]),
    ("CRITICAL", "Code Repository / CI-CD", ["github.com", "gitlab.com", "bitbucket.org", "app.circleci.com", "app.travis-ci.com", "argocd"]),
    ("CRITICAL", "Identity Provider",       ["okta.com", "auth0.com", "login.microsoftonline.com", "admin.google.com", "accounts.google.com"]),
    # AGENTIC-2, added 2026-07-07: a stolen session on one of these grants an
    # attacker (or another agent) the same tool/API access the legitimate
    # agent had — deliberately not added to SESSION_COOKIE_NAMES below since
    # exact cookie names for these platforms aren't verified; classification
    # here relies on the existing generic session-pattern fallback matcher.
    ("CRITICAL", "AI Agent Platform",       ["platform.openai.com", "chat.openai.com", "chatgpt.com", "console.anthropic.com", "claude.ai", "smith.langchain.com", "app.zapier.com", "www.make.com", "n8n.io", "app.n8n.cloud"]),
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
    # CONFIRMED ACTIVE — producing IOCs as of June 22 2026 CloudWatch audit
    # -------------------------------------------------------------------------
    ("threatintelfeeds",     "general",         "Threat intelligence text IOC feed — 2 IOCs/run"),
    ("vxunderground",        "general",         "vx-underground — malware intelligence + SHA256 hashes"),
    ("malware_traffic",      "general",         "Malware Traffic Analysis — IOC sharing"),
    ("DarkWebInformer",      "credential_dump", "Dark Web Informer — breach announcements and IOCs"),
    ("H4ckManac",            "general",         "H4ckManac — OSINT IOC sharing channel"),

    # -------------------------------------------------------------------------
    # ACCESSIBLE (0 messages last run — low volume but reachable)
    # -------------------------------------------------------------------------
    ("exposed_vc",           "credential_dump", "Exposed.vc — breach announcements"),
    ("breachforums",         "credential_dump", "BreachForums — cybercrime forum announcements"),
    ("leakbase",             "credential_dump", "LeakBase — breach and credential leak tracking"),
    ("cryptoscamdb",         "crypto",          "CryptoScamDB — wallet blacklist updates"),

    # -------------------------------------------------------------------------
    # INFOSTEALER LOG CHANNELS — trigger ZIP archive parsing (INTEL-5)
    # These are the channels that post stealer log ZIP archives.
    # category MUST be "infostealer" to activate _process_stealer_archive()
    # -------------------------------------------------------------------------
    ("logsmarket",           "infostealer",     "Logs Market — stealer log sales, ZIP archives"),
    ("stealerlogsmarket",    "infostealer",     "Stealer Logs Market — credential dump ZIPs"),
    ("darkwebintel",         "infostealer",     "Dark Web Intel — stealer log announcements"),
    ("logs_market",          "infostealer",     "Logs Market alt handle — stealer log ZIPs"),

    # -------------------------------------------------------------------------
    # NEW CANDIDATES — verified public Telegram channels June 2026
    # -------------------------------------------------------------------------
    ("thecyberexpress",      "general",         "The Cyber Express — breach and threat news"),
    ("falconfeeds",          "general",         "FalconFeeds — dark web threat intelligence"),
    ("uptycs_threatres",     "general",         "Uptycs threat research IOC feed"),
    ("cyberknow20",          "general",         "CyberKnow — APT and ransomware tracking"),

    # -------------------------------------------------------------------------
    # RANSOMWARE TRACKING — victim announcements + gang channels
    # -------------------------------------------------------------------------
    ("ransomwatch",          "ransomware",      "RansomWatch — multi-gang victim announcements aggregator"),
    ("darkfeed_io",          "ransomware",      "DarkFeed — APT + ransomware IOC feed"),
    ("RansomwareUpdates",    "ransomware",      "Ransomware group update announcements"),
    ("cti_feed",             "general",         "CTI Feed — community threat intel sharing"),

    # -------------------------------------------------------------------------
    # ADDITIONAL STEALER LOG / COMBO LIST CHANNELS
    # -------------------------------------------------------------------------
    ("logs_cloud",           "infostealer",     "Logs Cloud — stealer log ZIP distribution"),
    ("combolist_channel",    "infostealer",     "Combo lists — credential combo dumps"),
    ("stealer_logs_free",    "infostealer",     "Stealer logs free — credential stealer log drops"),

    # -------------------------------------------------------------------------
    # CRYPTO CRIME / WALLET DRAINER ALERTS
    # -------------------------------------------------------------------------
    ("scam_sniffer",         "crypto",          "ScamSniffer — phishing wallet drainer alerts"),
    ("revokecash_alerts",    "crypto",          "Revoke.cash — approval phishing token drain alerts"),
    ("cryptophishing",       "crypto",          "Crypto phishing domain tracking"),

    # -------------------------------------------------------------------------
    # EXPANDED IOC / THREAT INTEL FEEDS
    # -------------------------------------------------------------------------
    ("abuse_ch",             "general",         "Abuse.ch — URLhaus + MalwareBazaar announcements"),
    ("montysecurity",        "general",         "Monty's Security — threat intel sharing"),
    ("soc_prime_feed",       "general",         "SOC Prime — detection rule + IOC feed"),
    ("thecyberthrone",       "general",         "The Cyber Throne — breach and APT news"),
    ("BetterCyber",          "general",         "BetterCyber — breach and dark web alerts"),
    ("threatsintell",        "general",         "Threats Intel — IOC + vulnerability feed"),
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

_RE_SHA256  = re.compile(r"\b[a-fA-F0-9]{64}\b")
_RE_MD5     = re.compile(r"\b[a-fA-F0-9]{32}\b")
_RE_SHA1    = re.compile(r"\b[a-fA-F0-9]{40}\b")
_RE_URL     = re.compile(r"https?://[^\s<>\"']{10,}")
_RE_ONION   = re.compile(r"\b[a-z2-7]{16,56}\.onion\b", re.IGNORECASE)
_RE_CVE     = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)
_RE_RANSOM_VICTIM = re.compile(
    r"(?:hacked?|leaked?|compromised?|victim[s]?[:,]?\s*|added to our blog[:\s]*)"
    r"([A-Z][A-Za-z0-9\s&\-\.]{3,50}(?:Inc\.?|LLC|Ltd\.?|Corp\.?|Group|Co\.?)?)",
    re.IGNORECASE,
)
_RE_TG_CHANNEL = re.compile(r"@([a-zA-Z][a-zA-Z0-9_]{4,31})")  # @mention discovery

# ---------------------------------------------------------------------------
# AWS clients
# ---------------------------------------------------------------------------

_secrets     = boto3.client("secretsmanager", region_name="us-east-1")
_dynamodb    = boto3.resource("dynamodb",      region_name="us-east-1")
_rekognition = boto3.client("rekognition",     region_name="us-east-1")
_kms         = boto3.client("kms", region_name="us-east-1")
KMS_DATA_KEY = "alias/relayshield-data-key"


def _kms_encrypt(value: str) -> str:
    """KMS-encrypt a string. Returns base64-encoded ciphertext."""
    resp = _kms.encrypt(KeyId=KMS_DATA_KEY, Plaintext=value.encode("utf-8"))
    return base64.b64encode(resp["CiphertextBlob"]).decode("utf-8")


def _sha256_index(value: str) -> str:
    """SHA-256 hash for use as a DynamoDB index key — never stores plaintext PII."""
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()

   # Fix 3
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
# WhatsApp alert delivery (session hijack template)
# ---------------------------------------------------------------------------

def _get_twilio_creds() -> tuple[str, str, str]:
    sm = boto3.client("secretsmanager", region_name="us-east-1")
    account_sid  = sm.get_secret_value(SecretId=TWILIO_SID_SECRET)["SecretString"].strip()
    auth_token   = sm.get_secret_value(SecretId=TWILIO_TOKEN_SECRET)["SecretString"].strip()
    from_number  = sm.get_secret_value(SecretId=TWILIO_FROM_SECRET)["SecretString"].strip()
    return account_sid, auth_token, from_number


def _get_user_wa_number(user_id: str) -> str | None:
    """Return whatsapp:-prefixed number for a user, decrypting KMS if needed."""
    try:
        item = _dynamodb.Table(USERS_TABLE).get_item(Key={"user_id": user_id}).get("Item", {})
        if "phone_encrypted" in item:
            kms    = boto3.client("kms", region_name="us-east-1")
            number = kms.decrypt(CiphertextBlob=base64.b64decode(item["phone_encrypted"]))["Plaintext"].decode()
        else:
            number = item.get("whatsapp_number")
        if not number:
            return None
        return number if number.startswith("whatsapp:") else f"whatsapp:{number}"
    except Exception as exc:
        logger.warning("WA number lookup failed user_id=%s: %s", user_id, exc)
        return None


def _send_wa_session_hijack(user_id: str, email: str, sessions: list[dict]) -> bool:
    """Send rs_session_hijack_alert WA template.
    {{1}} = email, {{2}} = top affected services (comma-separated, max 3).
    """
    to_number = _get_user_wa_number(user_id)
    if not to_number:
        logger.info("No WA number for user_id=%s — skipping WA session alert", user_id)
        return False
    top_domains = ", ".join(
        list(dict.fromkeys(s["domain"] for s in sessions if s.get("severity") in ("CRITICAL", "HIGH")))[:3]
        or [s["domain"] for s in sessions[:3]]
    )
    try:
        account_sid, auth_token, from_number = _get_twilio_creds()
    except Exception as exc:
        logger.error("Twilio creds fetch failed: %s", exc)
        return False
    url = TWILIO_MESSAGES_URL.format(account_sid=account_sid)
    payload = urllib.parse.urlencode({
        "From": from_number,
        "To": to_number,
        "ContentSid": SESSION_HIJACK_TEMPLATE_SID,
        "ContentVariables": json.dumps({"1": email, "2": top_domains}),
    }).encode()
    creds   = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    headers = {"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"}
    req     = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        import urllib.parse as _up
        with urllib.request.urlopen(req, timeout=15) as resp:
            sid = json.loads(resp.read()).get("sid", "unknown")
            logger.info("Session hijack WA template sent user_id=%s SID=%s", user_id, sid)
            return True
    except Exception as exc:
        logger.error("Session hijack WA send failed user_id=%s: %s", user_id, exc)
        return False


# ---------------------------------------------------------------------------
# Fix 3: Rekognition OCR for image attachments
# ---------------------------------------------------------------------------

async def _extract_image_text(client, message) -> str:
    """Download image attachment and OCR via Rekognition. Returns extracted text.

    CORPUS-3 fix, 2026-08-16. This required message.document, but Telegram
    delivers a normally-posted screenshot as message.photo -- only an image sent
    explicitly "as file" arrives as a document. So every ordinary screenshot in
    every monitored channel was skipped, and images_ocrd was 0 on every run.
    Criminal channels post credential and panel screenshots constantly, which
    made this the single largest blind spot in collection.
    """
    media = getattr(message, "document", None) or getattr(message, "photo", None)
    if not media:
        return ""

    is_photo = getattr(message, "photo", None) is not None
    finfo = getattr(message, "file", None)
    mime = (getattr(finfo, "mime_type", "") or getattr(media, "mime_type", "") or "")
    size = getattr(finfo, "size", None) or getattr(media, "size", None) or 0

    # A photo has no reliable mime type on the media object, so accept it on
    # type. Documents still have to declare an image mime, which is what keeps
    # this cheap for the ZIPs and text files handled elsewhere.
    if not is_photo and mime not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
        return ""
    if size and size > MAX_IMAGE_BYTES:
        logger.info("OCR: skipping oversized image msg=%d size=%d", message.id, size)
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

def _normalize_multilingual(text: str) -> str:
    """Normalize IOC obfuscation patterns used in Russian, Chinese, and Arabic criminal channels.
    These channels use native-script lookalikes and transliterated defanging to evade filters."""
    t = text
    # Russian Cyrillic lookalike substitutions commonly used to obfuscate domains/IPs
    cyrillic_map = {
        'а': 'a', 'е': 'e', 'о': 'o', 'р': 'r', 'с': 'c',
        'х': 'x', 'у': 'y', 'і': 'i', 'ѕ': 's', 'ԁ': 'd',
    }
    for cyr, lat in cyrillic_map.items():
        t = t.replace(cyr, lat)
    # Chinese channel defang patterns — Chinese criminals use fullwidth chars and Chinese "dot"
    t = t.replace('。', '.').replace('．', '.').replace('·', '.')
    t = t.replace('：', ':').replace('＠', '@').replace('／', '/')
    # Fullwidth ASCII (common in Chinese/Japanese channels) → ASCII
    t = ''.join(chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else c for c in t)
    # Arabic channel defang — Arabic "dot" substitute and RTL mark removal
    t = t.replace('\u200f', '').replace('\u200e', '').replace('\u202b', '').replace('\u202a', '')
    t = t.replace('٫', '.').replace('،', ',')
    # Russian transliterated defang: "точка" = dot, "собака" = at-sign
    t = re.sub(r'\bточка\b', '.', t, flags=re.IGNORECASE)
    t = re.sub(r'\bсобака\b', '@', t, flags=re.IGNORECASE)
    # Chinese transliterated defang: "点" = dot
    t = t.replace('点', '.').replace('點', '.')
    return t


def _defang(text: str) -> str:
    """Normalise defanged IOCs — covers all common evasion variants used in criminal channels."""
    t = _normalize_multilingual(text)
    # Email/at variants
    t = re.sub(r'\[at\]',   '@', t, flags=re.IGNORECASE)
    t = re.sub(r'\(at\)',   '@', t, flags=re.IGNORECASE)
    t = re.sub(r' at ',       '@', t)
    # Dot variants
    t = re.sub(r'\[\.\]',   '.', t, flags=re.IGNORECASE)
    t = re.sub(r'\(\.\)',   '.', t, flags=re.IGNORECASE)
    t = re.sub(r'\[dot\]',  '.', t, flags=re.IGNORECASE)
    t = re.sub(r'\(dot\)',  '.', t, flags=re.IGNORECASE)
    t = re.sub(r'\.com\b',  '.com', t, flags=re.IGNORECASE)
    t = re.sub(r'\.net\b',  '.net', t, flags=re.IGNORECASE)
    t = re.sub(r'\.org\b',  '.org', t, flags=re.IGNORECASE)
    t = re.sub(r'\.io\b',   '.io',  t, flags=re.IGNORECASE)
    # HTTP variants: hxxp, h**p, h[tt]p, h(tt)p
    t = re.sub(r'hxxps://', 'https://', t, flags=re.IGNORECASE)
    t = re.sub(r'hxxp://',  'http://',  t, flags=re.IGNORECASE)
    t = re.sub(r'h\*\*ps://', 'https://', t, flags=re.IGNORECASE)
    t = re.sub(r'h\*\*p://',  'http://',  t, flags=re.IGNORECASE)
    t = re.sub(r'h\[tt\]ps://', 'https://', t, flags=re.IGNORECASE)
    t = re.sub(r'h\[tt\]p://',  'http://',  t, flags=re.IGNORECASE)
    t = re.sub(r'h\(tt\)ps://', 'https://', t, flags=re.IGNORECASE)
    t = re.sub(r'h\(tt\)p://',  'http://',  t, flags=re.IGNORECASE)
    t = re.sub(r'hxxps?\[://\]', lambda m: 'https://' if 's' in m.group(0) else 'http://', t, flags=re.IGNORECASE)
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
    valid_ips     = list({m for m in _RE_IPV4.findall(text)
                          if not m.startswith(("10.", "192.168.", "172.", "127.", "0.", "255.", "169.254."))})
    domains_raw   = list({m.lower() for m in _RE_DOMAIN.findall(text) if "." in m and len(m) > 4})
    valid_domains = [d for d in domains_raw
                     if not d.endswith((".local", ".internal", ".localhost", ".example"))]
    sha256  = list({m.lower() for m in _RE_SHA256.findall(text)})
    md5     = list({m.lower() for m in _RE_MD5.findall(text)
                    if m.lower() not in [s[:32] for s in sha256]})  # avoid SHA256 prefix collisions
    sha1    = list({m.lower() for m in _RE_SHA1.findall(text)
                    if m.lower() not in [s[:40] for s in sha256]})
    urls    = list({m for m in _RE_URL.findall(text)
                    if not any(p in m for p in ("t.me/", "telegram.me/", "api.telegram.org"))})
    onions  = list({m.lower() for m in _RE_ONION.findall(text)})
    cves    = list({m.upper() for m in _RE_CVE.findall(text)})
    victims = list({m.strip() for m in _RE_RANSOM_VICTIM.findall(text) if len(m.strip()) > 3})
    tg_mentions = list({m.lower() for m in _RE_TG_CHANNEL.findall(text)})
    return {
        "emails": emails, "phones": phones,
        "eth": eth, "btc": btc, "sol": sol, "ton": ton,
        "domains": valid_domains, "ips": valid_ips,
        "sha256": sha256, "md5": md5, "sha1": sha1,
        "urls": urls, "onions": onions, "cves": cves,
        "ransomware_victims": victims,
        "tg_mentions": tg_mentions,
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
# Single-flight lock — prevents two invocations (overlapping schedule, CLI
# retry-on-timeout, manual re-invoke) from ever sharing the Telethon session
# concurrently. Telegram permanently revokes a session's auth key if it sees
# simultaneous use from two IPs, so this has to block before any connection
# is made, not just rate-limit within one.
# ---------------------------------------------------------------------------

def _acquire_lock() -> bool:
    now = int(time.time())
    try:
        _dynamodb.Table(LOCK_TABLE).put_item(
            Item={"lock_id": LOCK_ID, "ttl": Decimal(now + LOCK_TTL_SECONDS), "acquired_at": now},
            ConditionExpression="attribute_not_exists(lock_id) OR #ttl < :now",
            ExpressionAttributeNames={"#ttl": "ttl"},
            ExpressionAttributeValues={":now": now},
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


def _release_lock() -> None:
    try:
        _dynamodb.Table(LOCK_TABLE).delete_item(Key={"lock_id": LOCK_ID})
    except Exception:
        logger.warning("Failed to release intel-monitor lock", exc_info=True)


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


_COMMON_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "protonmail.com",
    "icloud.com", "aol.com", "live.com", "msn.com", "me.com",
}


def _store_identity_correlations(iocs: dict, channel: str) -> None:
    """Store email+phone/domain co-occurrences from same dump.
    Powers /v1/metered/identity-graph endpoint."""
    emails  = iocs.get("emails", [])
    phones  = iocs.get("phones", [])
    domains = [d for d in iocs.get("domains", []) if d not in _COMMON_EMAIL_DOMAINS]
    if not emails or (not phones and not domains):
        return
    table = _dynamodb.Table(IDENTITY_GRAPH_TABLE)
    now   = datetime.now(timezone.utc).isoformat()
    ttl   = Decimal(int(time.time()) + 365 * 86400)
    def _write(anchor, anchor_type, corr, corr_type):
        try:
            corr_norm = corr if corr_type == "phone" else corr.lower()
            anchor_hash = _sha256_index(anchor)
            corr_hash   = _sha256_index(corr_norm)
            # Enhancement 1: increment source_count for dedup scoring
            try:
                table.update_item(
                    Key={"anchor": anchor_hash, "correlated_id": corr_hash},
                    UpdateExpression="SET source_count = if_not_exists(source_count, :z) + :one, last_seen = :ts, ttl = :ttl",
                    ExpressionAttributeValues={":z": 0, ":one": 1, ":ts": now, ":ttl": ttl},
                )
                return  # record existed — updated count
            except Exception:
                pass  # new record — fall through to put_item
            table.put_item(Item={
                "anchor": anchor_hash,
                "correlated_id": corr_hash,
                "correlated_encrypted": _kms_encrypt(corr_norm),
                "anchor_type": anchor_type, "correlated_type": corr_type,
                "source": channel, "confidence": "HIGH",
                "source_count": 1,
                "first_seen": now, "last_seen": now, "ttl": ttl,
            })
        except Exception:
            pass
    for email in emails[:10]:
        for phone in phones[:5]:
            _write(email, "email", phone, "phone")
        for domain in domains[:5]:
            _write(email, "email", domain, "domain")

# ---------------------------------------------------------------------------
# Malware family attribution (added 2026-07-28)
# ---------------------------------------------------------------------------
# Until now _store_iocs never wrote the "malware" attribute at all, so every
# IOC harvested from Telegram was untagged and the malware-index GSI on
# relayshield_intel_iocs was populated *only* by the ThreatFox path in
# relayshield_intel_feed.py. That gave away the pipeline's main structural
# advantage: MaaS families are advertised and sold on these channels before
# their infrastructure reaches abuse.ch, so tagging at ingest lets a family be
# queryable here ahead of the public feeds.
#
# Two tiers, because false attribution is worse than no attribution:
#   DISTINCTIVE -- coined names that effectively never occur as ordinary words,
#                  matched on the name alone.
#   AMBIGUOUS   -- real English words also used as family names (atomic,
#                  aurora, meduza, phantom). These require a malware-context
#                  qualifier within ~40 chars, or they would tag every message
#                  containing the word "atomic".
#
# Canonical names follow the convention already in the corpus: lowercase and
# compressed (remusstealer, qakbot, zigclipper, purehvnc). Multiple families in
# one message are stored comma-joined, matching existing rows like
# "botnetdomain,mirai" and "payload,PureHVNC".
_MALWARE_CONTEXT = r"(?:stealer|logs?|malware|rat\b|loader|botnet|c2|panel|builder|crypt|hvnc|grabber)"

_MALWARE_DISTINCTIVE: list[tuple[str, str]] = [
    ("dolphinx",       r"dolphin\s?x\b"),
    ("medusahvnc",     r"medusa\s?hvnc\b"),
    ("purehvnc",       r"pure\s?hvnc\b"),
    ("lummastealer",   r"\blumma(?:c2|\s?stealer)?\b"),
    ("redlinestealer", r"\bredline\b"),
    ("vidarstealer",   r"\bvidar\b"),
    ("stealc",         r"\bstealc\b"),
    ("rhadamanthys",   r"\brhadamanthys\b"),
    ("raccoonstealer", r"\braccoon\s?(?:stealer|v2)\b"),
    ("risepro",        r"\brisepro\b"),
    ("metastealer",    r"\bmeta\s?stealer\b"),
    ("phemedrone",     r"\bphemedrone\b"),
    ("acrstealer",     r"\bacr\s?stealer\b"),
    ("braodostealer",  r"\bbraodo\b"),
    ("remusstealer",   r"\bremus\s?stealer\b"),
    ("qakbot",         r"\bqakbot\b|\bqbot\b"),
    ("zigclipper",     r"\bzigclipper\b"),
    # CaptiveCrunch / Midnight Blizzard (APT29), Microsoft + ReliaQuest, Aug 2026.
    # ChocoShell is an in-memory PowerShell stealer taking browser cookies,
    # saved passwords and auth tokens -- squarely the session-theft surface this
    # corpus already tracks. Distinctive enough to need no context guard.
    # Expect few or no hits: these are nation-state tools, and this pipeline
    # watches commodity stealer-log markets where APT29 does not sell. Added for
    # tagging completeness, not because volume is expected.
    ("chocoshell",     r"\bchoco\s?shell\b"),
]

# name -> alias regex; a _MALWARE_CONTEXT word must appear near the match
_MALWARE_AMBIGUOUS: list[tuple[str, str]] = [
    ("atomicstealer",  r"\batomic\b|\bamos\b"),
    ("aurorastealer",  r"\baurora\b"),
    ("meduzastealer",  r"\bmeduza\b"),
    ("phantomstealer", r"\bphantom\b"),
    # CornFlake — the Go RAT half of the same CaptiveCrunch campaign. Placed in
    # the AMBIGUOUS list deliberately: unlike ChocoShell, "cornflake" is an
    # ordinary English word, so it needs a malware-context word nearby before it
    # tags an IOC. A false family tag is worse than a missed one here, because
    # `malware` is the malware-index GSI hash key.
    ("cornflake",      r"\bcorn\s?flake\b"),
]

_MALWARE_DISTINCTIVE_RE = [(n, re.compile(p, re.I)) for n, p in _MALWARE_DISTINCTIVE]
_MALWARE_AMBIGUOUS_RE   = [(n, re.compile(p, re.I)) for n, p in _MALWARE_AMBIGUOUS]
_MALWARE_CONTEXT_RE     = re.compile(_MALWARE_CONTEXT, re.I)


def detect_malware_families(text: str) -> str:
    """Return a comma-joined list of malware families named in `text`.

    Empty string when nothing matches -- callers must not write an empty
    "malware" attribute, since it is the malware-index GSI hash key and an
    empty value would index every untagged IOC (same trap documented in
    relayshield_intel_feed._write_ioc).
    """
    if not text:
        return ""
    found: list[str] = []
    for name, rx in _MALWARE_DISTINCTIVE_RE:
        if rx.search(text) and name not in found:
            found.append(name)
    for name, rx in _MALWARE_AMBIGUOUS_RE:
        if name in found:
            continue
        m = rx.search(text)
        if not m:
            continue
        # require malware context within ~40 chars either side of the alias
        lo, hi = max(0, m.start() - 40), min(len(text), m.end() + 40)
        if _MALWARE_CONTEXT_RE.search(text[lo:hi]):
            found.append(name)
    return ",".join(sorted(found))


def _store_iocs(iocs: dict, channel: str, category: str, malware: str = "") -> None:
    now   = datetime.now(timezone.utc).isoformat()
    ttl   = Decimal(int(time.time()) + ALERT_TTL_DAYS * 86400)
    table = _dynamodb.Table(INTEL_IOCS_TABLE)
    type_map = [
        ("emails", "email"), ("eth", "wallet_eth"), ("btc", "wallet_btc"),
        ("sol", "wallet_sol"), ("ton", "wallet_ton"), ("domains", "domain"),
        ("phones", "phone"), ("ips", "ip"),
        ("sha256", "hash_sha256"), ("urls", "url"),
        # "cves" added 2026-07-24 -- real gap found while scoping the CVE
        # actor-discussion-heat score: extract_iocs() has extracted CVE IDs
        # from every monitored message all along (stats["cves_extracted"]
        # counts them), but this type_map never included them, so not one
        # was ever actually persisted. The heat score needs exactly this
        # history (which CVEs, how often, which channels, over time) --
        # it starts accumulating from this deploy forward, not backfilled,
        # since the raw past messages were never stored.
        ("cves", "cve"),
    ]
    for field, ioc_type in type_map:
        for value in iocs.get(field, []):
            if not value:
                continue
            try:
                item = {
                    "ioc_value": value.lower(), "seen_ts": now,
                    "ioc_type": ioc_type, "channel": channel,
                    "category": category, "ttl": ttl,
                }
                # Only set when non-empty -- "malware" is the malware-index GSI
                # hash key, and writing "" would index every untagged IOC.
                if malware:
                    item["malware"] = malware
                table.put_item(Item=item)
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
            domain = urlparse(url).netloc.lower().removeprefix("www.")
        except Exception:
            continue
        if not domain:
            continue
        severity, category = _classify_domain(domain)
        if severity == "LOW" and category == "General Web Service":
            continue
        results.append({"domain": domain, "severity": severity,
                         "category": category, "type": "credential"})
    # NHI detection: scan credential values for API key/token patterns.
    # Kept in sync with NHI_PATTERNS in relayshield_api.py — this is the
    # ingestion-side copy that populates the data the API-side list queries,
    # so a gap here means the API can never surface that credential type
    # even though it "knows" the pattern (found out of sync 2026-07-07).
    def _ctx(vendors, key_re):
        """Context-anchored regex; secret must be the single capturing group."""
        return (r"(?i)(?:%s)[\w.\-]{0,20}[\s'\"]{0,3}(?:=|:|=>|:=|\|\|)[\s'\"`]{0,5}(%s)"
                % (vendors, key_re))

    # (type, regex, severity, description, llm_provider)
    _NHI_PATS = [
        ("aws_access_key",   r"AKIA[A-Z0-9]{16}", "CRITICAL", "AWS IAM Access Key", None),
        ("github_pat",       r"gh[pousr]_[a-zA-Z0-9]{36,}", "CRITICAL", "GitHub PAT", None),
        ("github_pat_fine",  r"github_pat_[a-zA-Z0-9_]{82}", "CRITICAL", "GitHub Fine-Grained PAT", None),
        ("stripe_secret",    r"sk_live_[a-zA-Z0-9]{24,}", "CRITICAL", "Stripe Secret Key", None),
        ("private_key",      r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----", "CRITICAL", "Private Key", None),
        ("slack_bot",        r"xoxb-[0-9]+-[0-9]+-[a-zA-Z0-9]+", "HIGH", "Slack Bot Token", None),
        ("slack_user",       r"xoxp-[0-9]+-[0-9]+-[0-9]+-[a-zA-Z0-9]+", "HIGH", "Slack User Token", None),
        # --- LLM/AI provider keys (llm_provider set) ---
        ("google_api",       r"AIza[0-9A-Za-z\-_]{35}", "CRITICAL", "Google AI (Gemini) API Key", "google"),
        ("openai_key",       r"sk-(?:proj|svcacct|admin)-(?:[A-Za-z0-9_\-]{74}|[A-Za-z0-9_\-]{58})T3BlbkFJ(?:[A-Za-z0-9_\-]{74}|[A-Za-z0-9_\-]{58})", "CRITICAL", "OpenAI API Key", "openai"),
        ("openai_key_v1",    r"sk-[a-zA-Z0-9]{20}T3BlbkFJ[a-zA-Z0-9]{20}", "CRITICAL", "OpenAI API Key (v1 format)", "openai"),
        ("openai_key_legacy", _ctx(r"openai|OPENAI_API_KEY", r"sk-[a-zA-Z0-9]{48}"), "CRITICAL", "OpenAI API Key (legacy format)", "openai"),
        ("anthropic_key",    r"sk-ant-[a-zA-Z0-9_\-]{90,}", "CRITICAL", "Anthropic API Key", "anthropic"),
        ("groq_key",         r"gsk_[a-zA-Z0-9]{52}", "CRITICAL", "Groq API Key", "groq"),
        ("xai_key",          r"xai-[a-zA-Z0-9]{80}", "CRITICAL", "xAI (Grok) API Key", "xai"),
        ("replicate_key",    r"r8_[a-zA-Z0-9]{37}", "CRITICAL", "Replicate API Key", "replicate"),
        ("bedrock_key_long", r"ABSKQmVkcm9ja0FQSUtleS[A-Za-z0-9+/]{80,250}={0,2}", "CRITICAL", "Amazon Bedrock API Key (long-lived)", "bedrock"),
        ("bedrock_key_short", r"bedrock-api-key-YmVkcm9jay5hbWF6b25hd3MuY29t[A-Za-z0-9+/=]*", "CRITICAL", "Amazon Bedrock API Key (short-lived)", "bedrock"),
        ("huggingface_token", r"hf_[a-zA-Z]{34}", "CRITICAL", "Hugging Face User Access Token", "huggingface"),
        ("huggingface_org",  r"api_org_[a-zA-Z]{34}", "CRITICAL", "Hugging Face Organization Token", "huggingface"),
        ("alibaba_access_key_id", r"LTAI[a-zA-Z0-9]{20}", "HIGH", "Alibaba Cloud AccessKey ID (Qwen/Model Studio)", "alibaba"),
        ("nvidia_nim_key",   r"nvapi-[A-Za-z0-9_\-]{40,}", "CRITICAL", "NVIDIA NIM API Key", "nvidia"),
        ("deepseek_key",     _ctx(r"deepseek|DEEPSEEK_API_KEY", r"sk-[a-zA-Z0-9]{20,64}"), "CRITICAL", "DeepSeek API Key", "deepseek"),
        ("moonshot_key",     _ctx(r"moonshot|kimi|MOONSHOT_API_KEY", r"sk-[a-zA-Z0-9]{20,64}"), "CRITICAL", "Moonshot (Kimi) API Key", "moonshot"),
        ("qwen_key",         _ctx(r"dashscope|qwen|DASHSCOPE_API_KEY", r"sk-[a-zA-Z0-9]{20,64}"), "CRITICAL", "Alibaba DashScope (Qwen) API Key", "qwen"),
        ("langsmith_key",    r"lsv2_(?:pt|sk)_[a-f0-9]{32,}", "HIGH", "LangSmith API Key", "langsmith"),
        # --- non-LLM ---
        ("sendgrid_key",     r"SG\.[a-zA-Z0-9\-_.]{22}\.[a-zA-Z0-9\-_.]{43}", "HIGH", "SendGrid API Key", None),
        ("twilio_sid",       r"AC[a-f0-9]{32}", "MEDIUM", "Twilio Account SID", None),
        ("stripe_pub",       r"pk_live_[a-zA-Z0-9]{24,}", "MEDIUM", "Stripe Publishable Key", None),
        ("jwt_token",        r"eyJ[A-Za-z0-9\-_]{20,}\.[A-Za-z0-9\-_]{20,}\.[A-Za-z0-9\-_]{20,}", "MEDIUM", "JWT Token", None),
        ("mcp_token_generic", r"mcp_(?:live|sk|pat)_[a-zA-Z0-9]{20,}", "MEDIUM", "Possible MCP Server Auth Token", None),
        # Unattributed OpenAI-compatible catch-all -- MUST stay last.
        ("llm_key_generic_sk", r"sk-[a-zA-Z0-9]{32,64}", "HIGH", "OpenAI-compatible LLM API Key (provider unattributed)", "unknown_openai_compatible"),
    ]
    for line in text.splitlines():
        sep   = "\t" if "\t" in line else "|"
        parts = [p.strip() for p in line.split(sep)]
        raw   = " ".join(parts[1:] if len(parts) > 1 else parts)
        dom   = parts[0][:120] if parts else ""
        _attributed: set = set()
        for nhi_type, nhi_pat, nhi_sev, nhi_desc, nhi_prov in _NHI_PATS:
            m = re.search(nhi_pat, raw)
            if not m:
                continue
            # context-anchored patterns capture the secret in group(1)
            val = m.group(1) if m.re.groups else m.group(0)
            if nhi_prov == "unknown_openai_compatible":
                if val in _attributed:
                    continue
            elif nhi_prov:
                _attributed.add(val)
            entry = {"domain": dom, "severity": nhi_sev,
                     "category": f"NHI:{nhi_desc}", "type": "nhi",
                     "nhi_type": nhi_type, "nhi_description": nhi_desc}
            # llm_provider is what handle_llm_credential_exposure reads back --
            # without persisting it the LLMjacking endpoint can never return a
            # finding, since the stored record holds no raw key material to
            # re-scan at query time.
            if nhi_prov:
                entry["llm_provider"] = nhi_prov
            results.append(entry)
    return results


def _luhn_valid(digits: str) -> bool:
    """Standard Luhn checksum -- used only to filter card-shaped digit
    sequences down to ones that are actually valid card numbers, not random
    13-19 digit runs (phone numbers, IDs, timestamps) in autofill dumps."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


_RE_CARD_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ \-]?){13,19}(?!\d)")


def _parse_card_data(text: str, channel: str) -> int:
    """Extracts card numbers from stealer-log Autofill/CreditCards files.

    Deliberately does NOT return card numbers to the caller or include them
    in any returned dict -- unlike the other _parse_*_file functions, whose
    output eventually reaches _store_stolen_session()/user-facing alerts,
    a card number is materially more sensitive than a session cookie or a
    plaintext password and gets a narrower blast radius: hashed and written
    directly to relayshield_stolen_cards here, nothing else ever sees the
    raw digits, and this function returns only a count for logging.
    """
    import hashlib as _hl
    table = _dynamodb.Table(STOLEN_CARDS_TABLE)
    now = datetime.now(timezone.utc).isoformat()
    ttl = Decimal(int(time.time()) + 365 * 86400)
    seen_hashes: set[str] = set()
    stored = 0
    for m in _RE_CARD_CANDIDATE.finditer(text):
        digits = re.sub(r"[ \-]", "", m.group(0))
        if not (13 <= len(digits) <= 19) or not _luhn_valid(digits):
            continue
        pan_hash = _hl.sha256(digits.encode()).hexdigest()
        if pan_hash in seen_hashes:
            continue
        seen_hashes.add(pan_hash)
        try:
            table.put_item(Item={
                "pan_hash":       pan_hash,
                "bin":            digits[:6],
                "last4":          digits[-4:],
                "channel_source": channel,
                "seen_ts":        now,
                "ttl":            ttl,
            })
            stored += 1
        except Exception as exc:
            logger.warning("Card store failed (hash only, no PAN logged): %s", exc)
    return stored


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


# AGENTIC-4 (added 2026-07-07) — heuristic keyword classifier over the
# Telegram POST text describing an archive (not the archive's file contents).
# This is a v1 heuristic, not a labeled ground-truth classifier — it flags
# posts whose own description suggests the dump originated from a compromised
# or injected AI agent, rather than a traditional phishing/malware campaign.
_AGENTIC_SOURCE_KEYWORDS = (
    "prompt injection", "system prompt", "ai agent", "llm agent",
    "autonomous agent", "jailbreak", "agentic", "chatgpt leak",
    "claude leak", "copilot leak", "ai assistant leak",
)


def _looks_agentic_source(post_text: str) -> bool:
    low = (post_text or "").lower()
    return any(kw in low for kw in _AGENTIC_SOURCE_KEYWORDS)


def _store_stolen_session(session: dict, channel: str, matched_email: str, matched_user_id: str,
                           suspected_agentic_source: bool = False) -> None:
    ttl = int(time.time()) + ALERT_TTL_DAYS * 86400
    try:
        _dynamodb.Table(STOLEN_SESSIONS_TABLE).put_item(Item={
            "session_id":           str(uuid.uuid4()),
            "domain":               session["domain"],
            "session_type":         session["type"],
            "cookie_name":          session.get("cookie_name", ""),
            **({"llm_provider": session["llm_provider"]} if session.get("llm_provider") else {}),
            "severity":             session["severity"],
            "service_category":     session["category"],
            "channel_source":       channel,
            "matched_email":        _sha256_index(matched_email),   # hash — GSI key, never plaintext
            "matched_email_enc":    _kms_encrypt(matched_email),    # KMS-encrypted for decryption
            "matched_user_id":      matched_user_id,
            "ingested_at":          datetime.now(timezone.utc).isoformat(),
            "suspected_agentic_source": suspected_agentic_source,
            "ttl":                  Decimal(ttl),
        })
    except Exception as exc:
        logger.warning("Stolen session write failed domain=%s: %s", session.get("domain"), exc)


def _store_observed_session(session: dict, channel: str) -> None:
    """Record a stolen session seen in a criminal archive, matched or not.

    CORPUS-1 fix, 2026-08-16. _store_stolen_session above requires a
    matched_email and matched_user_id, so a session was only ever kept when it
    belonged to an existing customer. With a small customer base that discards
    essentially everything: the table held 9 rows on 2026-08-16, all of them
    source "demo", after months of collection.

    That is backwards. A stolen session for an organisation that is NOT yet a
    customer is exactly the intelligence worth having -- it is the reason to
    call them.

    PRIVACY: no email, no cookie value, no credential is stored on this path.
    Only the service domain, the session type and the channel it was seen in,
    which is aggregate exposure intelligence rather than personal data. The
    matched path above keeps its existing hashed-and-encrypted handling and is
    unchanged.
    """
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
            "source":           "observed",   # distinguishes from "demo" and matched rows
            "matched":          False,
            "ingested_at":      datetime.now(timezone.utc).isoformat(),
            "ttl":              Decimal(ttl),
        })
    except Exception as exc:
        logger.warning("Observed session write failed domain=%s: %s", session.get("domain"), exc)


def _extract_marketplace_listing(text: str, channel: str, category: str) -> dict | None:
    """Pull the sale signals out of a marketplace post.

    _RE_LOG_COUNT and _RE_LOG_PRICE have existed in this file since the sale
    signal work and were wired to NOTHING -- confirmed 2026-08-16, zero call
    sites. The regexes to capture our most differentiated content were written
    and then never connected to an output.

    Returns None when the post carries no commercial signal at all, so ordinary
    chatter does not create rows.
    """
    if not text:
        return None

    counts = [c.replace(",", "").replace(".", "") for c in _RE_LOG_COUNT.findall(text)]
    prices = [p.replace(",", "") for p in _RE_LOG_PRICE.findall(text)]
    victims = [v.strip() for v in _RE_RANSOM_VICTIM.findall(text) if len(v.strip()) > 3]

    # A listing needs at least a volume or a price. Victim alone is already
    # handled by the ransomware-victim path.
    if not counts and not prices:
        return None

    def _biggest(vals):
        nums = []
        for v in vals:
            try:
                nums.append(int(v))
            except ValueError:
                continue
        return max(nums) if nums else None

    record_count = _biggest(counts)
    price = _biggest(prices)

    # Domains in the post are the likeliest victim identifiers, and are far more
    # reliable than the prose victim regex.
    domains = [d.lower() for d in _RE_DOMAIN.findall(text)][:5]

    return {
        "record_count":  record_count,
        "price":         price,
        "victim_domain": domains[0] if domains else "",
        "victim_domains": domains,
        "victim_names":  victims[:3],
        "channel":       channel,
        "category":      category,
    }


def _store_marketplace_listing(listing: dict, channel: str, preview: str) -> bool:
    """Write one marketplace listing. Returns True if written."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        item = {
            "listing_id":    str(uuid.uuid4()),
            "observed_at":   now,
            "channel":       channel,
            "category":      listing.get("category", ""),
            # GSI partition key must exist on every row, so unattributed listings
            # get a sentinel rather than being silently excluded from the index.
            "victim_domain": listing.get("victim_domain") or "unattributed",
            "ttl":           Decimal(int(time.time()) + 365 * 86400),
        }
        if listing.get("record_count") is not None:
            item["record_count"] = Decimal(listing["record_count"])
        if listing.get("price") is not None:
            item["price_usd"] = Decimal(listing["price"])
        if listing.get("victim_domains"):
            item["victim_domains"] = listing["victim_domains"]
        if listing.get("victim_names"):
            item["victim_names"] = listing["victim_names"]
        if preview:
            item["preview"] = preview[:400]
        _dynamodb.Table(MARKETPLACE_LISTINGS_TABLE).put_item(Item=item)
        return True
    except Exception as exc:
        logger.warning("Marketplace listing write failed channel=%s: %s", channel, exc)
        return False


def _record_channel_yield(username: str, messages: int, iocs: int, listings: int) -> None:
    """Write per-channel yield back to the channel row.

    Until now the channels table held first_seen and last_verified but nothing
    about what a channel actually PRODUCED, so a channel that is quiet and one
    that is silently failing looked identical. That made every cull-or-keep
    decision guesswork, which is why 73 dead channels sat in an "active" list
    for months. Cumulative counters plus a last_message_at are enough to rank
    channels by measured yield.
    """
    try:
        _dynamodb.Table(INTEL_CHANNELS_TABLE).update_item(
            Key={"username": username},
            UpdateExpression=(
                "SET last_collected_at = :now, "
                "    last_message_at = if_not_exists(last_message_at, :never) "
                "ADD messages_total :m, iocs_total :i, listings_total :l"
            ),
            ExpressionAttributeValues={
                ":now":   datetime.now(timezone.utc).isoformat(),
                ":never": "",
                ":m": Decimal(messages), ":i": Decimal(iocs), ":l": Decimal(listings),
            },
        )
        if messages:
            _dynamodb.Table(INTEL_CHANNELS_TABLE).update_item(
                Key={"username": username},
                UpdateExpression="SET last_message_at = :now",
                ExpressionAttributeValues={":now": datetime.now(timezone.utc).isoformat()},
            )
    except Exception as exc:
        logger.warning("Channel yield write failed for @%s: %s", username, exc)


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
    # Support both ZIP and RAR archives
    zf = None
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw_bytes))
    except zipfile.BadZipFile:
        pass
    if zf is None:
        try:
            import rarfile
            rf = rarfile.RarFile(io.BytesIO(raw_bytes))
            # Wrap rarfile to match zipfile API
            class _RarWrapper:
                def __init__(self, r): self._r = r
                def namelist(self): return self._r.namelist()
                def read(self, name): return self._r.read(name)
                def getinfo(self, name): return self._r.getinfo(name)  # RarInfo.file_size mirrors ZipInfo.file_size
            zf = _RarWrapper(rf)
        except Exception:
            logger.info("INTEL-5: archive @%s is neither ZIP nor RAR — skipping", channel)
            return
    all_sessions: list[dict] = []
    discovered_channels = 0
    cards_stored = 0
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
            elif any(kw in low_name for kw in ("autofill", "card", "cc_", "creditcard")):
                # BIN/stolen-card monitoring, added 2026-07-24. Real stealer
                # log packages commonly include an Autofill/CreditCards file
                # alongside Cookies/Passwords -- never parsed before. See
                # _parse_card_data's docstring for why this stores directly
                # (hashed) rather than returning raw digits like the other
                # parsers do.
                if low_name.endswith((".txt", ".csv", ".log", "")):
                    raw = zf.read(name).decode("utf-8", errors="ignore")
                    cards_stored += _parse_card_data(raw, channel)
            elif low_name.endswith((".txt", ".log", "")) and zf.getinfo(name).file_size < 20_000:
                # Channel-discovery pass, added 2026-07-24: resold/repackaged
                # stealer archives on Telegram often carry a reseller-added
                # README/notice/contact file (branding, support contact,
                # "more logs at @channel") that the cookie/password parsing
                # above never reads at all -- this data is already
                # downloaded, just previously discarded. A README that
                # doesn't happen to follow this pattern just yields nothing;
                # no harm either way. Size-capped to skip anything that's
                # clearly a real data file misnamed with a .txt/.log
                # extension, not a small notice file.
                raw = zf.read(name).decode("utf-8", errors="ignore")
                _extract_invite_links(raw, channel, "infostealer")
                mentions = _RE_TG_CHANNEL.findall(raw)
                if mentions:
                    discovered_channels += _queue_discovered_channels(mentions, channel)
        except Exception as exc:
            logger.warning("INTEL-5: parse error file=%s: %s", name[:60], exc)
    if discovered_channels:
        logger.info("INTEL-5: @%s msg=%d — %d channel candidate(s) discovered from archive text",
                     channel, message.id, discovered_channels)
    if cards_stored:
        logger.info("INTEL-5: @%s msg=%d — %d card record(s) stored (hashed, no PAN logged)",
                     channel, message.id, cards_stored)
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
    # Enhancement 2: track this as a full infostealer package
    try:
        import hashlib as _hl
        pkg_id = _hl.sha256(f"{channel}_{message.id}".encode()).hexdigest()[:16]
        session_types = [s.get("type", "") for s in unique_sessions]
        _dynamodb.Table(INTEL_PACKAGES_TABLE).put_item(Item={
            "package_id":           pkg_id,
            "channel_source":       channel,
            "message_id":           str(message.id),
            "ingested_at":          datetime.now(timezone.utc).isoformat(),
            "session_count":        len(unique_sessions),
            "cookie_count":         session_types.count("cookie"),
            "credential_count":     session_types.count("credential"),
            "nhi_count":            session_types.count("nhi"),
            "severity_critical":    sum(1 for s in unique_sessions if s.get("severity") == "CRITICAL"),
            "ttl":                  Decimal(int(time.time()) + 365 * 86400),
        })
    except Exception as _exc:
        logger.warning("Package tracking write failed: %s", _exc)
    session_domains = {s["domain"] for s in unique_sessions}

    # CORPUS-1 fix, 2026-08-16. Everything below this point only keeps a session
    # if it matches a monitored customer email, so with a small customer base
    # essentially every session found in a criminal archive was parsed, matched
    # against nothing, and dropped. Measured that day: the table held 9 rows,
    # all of them source "demo", after months of collection.
    #
    # Record every session we observe first, then do the matching. A stolen
    # session for an organisation that is NOT yet a customer is the reason to
    # call them, not something to discard. No email, cookie value or credential
    # is written on this path; see _store_observed_session.
    for _s in unique_sessions:
        _store_observed_session(_s, channel)

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
        agentic_source = _looks_agentic_source(
            (message.text or "") + " " + (getattr(message, "caption", "") or "")
        )
        for s in dedup:
            _store_stolen_session(s, channel, email, user_id, suspected_agentic_source=agentic_source)
        chat_id          = _get_user_chat_id(user_id)
        nhi_findings     = [s for s in dedup if s.get("type") == "nhi"]
        session_findings = [s for s in dedup if s.get("type") != "nhi"]
        if session_findings:
            if chat_id:
                _send_telegram(chat_id, _format_session_alert(email, session_findings, channel))
            _send_wa_session_hijack(user_id, email, session_findings)
            stats["alerts_fired"] += 1
            logger.info("INTEL-5 session alert fired user_id=%s", user_id)
        if nhi_findings:
            nhi_msg = (
                f"\U0001f6a8 *CRITICAL \u2014 API Key / Token Found in Stealer Log*\n\n"
                f"Non-human credentials linked to *{email}* found in criminal stealer archive:\n\n"
                + "\n".join(f"  \U0001f534 {f['nhi_description']} detected" for f in nhi_findings[:5])
                + "\n\n*Rotate these credentials immediately.*\n"
                "Check IAM/cloud provider logs for unauthorised activity.\n\n"
                "\U0001f6e1\ufe0f _RelayShield NHI Detection_"
            )
            if chat_id:
                _send_telegram(chat_id, nhi_msg)
            stats["alerts_fired"] += 1
            logger.info("INTEL-5 NHI alert fired user_id=%s nhi=%d", user_id, len(nhi_findings))


# ---------------------------------------------------------------------------
# Channel discovery — invite links
# ---------------------------------------------------------------------------

_RE_TG_INVITE = re.compile(
    r"(?:https?://)?t\.me/(?:\+[a-zA-Z0-9_\-]{16,}|joinchat/[a-zA-Z0-9_\-]+|([a-zA-Z][a-zA-Z0-9_]{3,}))",
    re.IGNORECASE,
)
# Discord invite codes — cross-platform discovery only (OSINT Sprint 2 Part 2),
# not IOC storage. Matches discord.gg/<code>, discord.com/invite/<code>, and
# the legacy discordapp.com/invite/<code> host.
_RE_DISCORD_INVITE = re.compile(
    r"(?:discord\.gg|discord(?:app)?\.com/invite)/([A-Za-z0-9\-]{2,32})",
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


DISCORD_CHANNELS_TABLE = "relayshield_intel_discord_channels"


def _queue_discovered_discord_invites(text: str, source_channel: str, category: str) -> int:
    """OSINT Sprint 2 Part 2 — cross-platform discovery. Scans Telegram message
    text already being processed for Discord invite links, resolves each via
    Discord's public unauthenticated invite endpoint (no bot token needed —
    same metadata the Discord client shows on an invite preview), and queues
    the result into relayshield_intel_discord_channels for manual review.

    Writes with active=False always — a resolved channel_id/guild_id does NOT
    mean the bot can read it. The bot still needs a server admin's OAuth
    authorization to be added; this only produces a lead list."""
    if not text:
        return 0
    codes = {m.group(1) for m in _RE_DISCORD_INVITE.finditer(text)}
    if not codes:
        return 0

    table   = _dynamodb.Table(DISCORD_CHANNELS_TABLE)
    now_ts  = datetime.now(timezone.utc).isoformat()
    queued  = 0

    for code in codes:
        req = urllib.request.Request(
            f"https://discord.com/api/v10/invites/{code}?with_counts=true",
            headers={"User-Agent": "RelayShield-INTEL (https://relayshield.net, 1.0)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                invite = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                logger.warning("Discord invite resolve failed code=%s: HTTP %s", code, exc.code)
            continue
        except Exception as exc:
            logger.warning("Discord invite resolve failed code=%s: %s", code, exc)
            continue

        channel = invite.get("channel") or {}
        guild   = invite.get("guild") or {}
        channel_id = channel.get("id")
        if not channel_id:
            continue

        try:
            table.put_item(
                Item={
                    "channel_id":        channel_id,
                    "guild_id":          guild.get("id", ""),
                    "guild_name":        guild.get("name", ""),
                    "channel_name":      channel.get("name", ""),
                    "category":          category,
                    "active":            False,
                    "invite_code":       code,
                    "member_count":      invite.get("approximate_member_count", 0),
                    "discovery_method":  "telegram_cross_promotion",
                    "found_via":         source_channel,
                    "first_seen":        now_ts,
                    "last_verified":     now_ts,
                },
                ConditionExpression="attribute_not_exists(channel_id)",
            )
            queued += 1
            logger.info(
                "Discord channel discovered via @%s: guild=%s channel=%s (%s members, invite=%s)",
                source_channel, guild.get("name"), channel.get("name"),
                invite.get("approximate_member_count", "?"), code,
            )
        except Exception:
            pass  # already known — not an error, just a repeat mention

    return queued


def _load_channels() -> list[tuple[str, str, str, int | None, int | None]]:
    """Return active channel list from DynamoDB; fall back to hardcoded list.

    channel_id/access_hash are a cached Telegram peer, written back by
    _poll_channels() after the first successful username resolve. When
    present, the caller can skip get_entity(username) entirely (a
    ResolveUsernameRequest) in favor of a local InputPeerChannel — avoiding
    the per-session flood-wait that call is subject to."""
    try:
        table = _dynamodb.Table(INTEL_CHANNELS_TABLE)
        resp  = table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("active").eq(True),
            ProjectionExpression="username, category, description, channel_id, access_hash",
        )
        items = resp.get("Items", [])
        if items:
            return [
                (
                    i["username"],
                    i["category"],
                    i.get("description", ""),
                    int(i["channel_id"]) if "channel_id" in i else None,
                    int(i["access_hash"]) if "access_hash" in i else None,
                )
                for i in items
            ]
    except Exception as exc:
        logger.warning("Could not load channels from DynamoDB, using fallback: %s", exc)
    return [(u, c, d, None, None) for u, c, d in MONITORED_CHANNELS]


# ---------------------------------------------------------------------------
# Admin digest
# ---------------------------------------------------------------------------

def _send_admin_digest(stats: dict) -> None:
    # Suppress only when there was genuinely nothing to check (e.g. the
    # Telethon-not-configured path, which already sends its own message).
    # channels_checked==0 with channels_attempted>0 means every resolve
    # failed this run (e.g. a Telegram flood-wait) -- that's exactly the
    # case that must NOT go silent, since it's the one time something is
    # actually wrong. A prior version of this guard checked channels_checked
    # instead of channels_attempted, which silently swallowed the digest
    # (and all visibility into the problem) on every such run.
    if not stats.get("channels_attempted"):
        return
    warning = ""
    if not stats["channels_checked"]:
        warning = "⚠️ *0 of {} channels resolved this run* — likely a Telegram flood-wait or session issue. No IOCs were processed.\n\n".format(
            stats["channels_attempted"]
        )
    text = (
        f"🔍 *INTEL-2/5 Monitor Run*\n\n"
        f"{warning}"
        f"Channels checked: {stats['channels_checked']}\n"
        f"Messages processed: {stats['messages_processed']}\n"
        f"IOCs extracted: {stats['iocs_extracted']}\n"
        f"Images OCR'd: {stats.get('images_ocrd', 0)}\n"
        f"Paste URLs followed: {stats.get('pastes_fetched', 0)}\n"
        f"ZIP/RAR archives parsed: {stats.get('archives_parsed', 0)}\n"
        f"Identity correlations: {stats.get('correlations_stored', 0)}\n"
        f"User matches: {stats['user_matches']}\n"
        f"Alerts fired: {stats['alerts_fired']}\n"
        f"Brand mentions detected: {stats.get('brand_alerts', 0)}\n"
        f"Ransomware victims named: {stats.get('ransomware_victims', 0)}\n"
        f"CVEs extracted: {stats.get('cves_extracted', 0)}\n"
        f"Onion addresses: {stats.get('onions_extracted', 0)}\n"
        f"Channels auto-discovered: {stats.get('channels_discovered', 0)}\n"
        f"Discord channels discovered: {stats.get('discord_channels_discovered', 0)}\n\n"
        f"_RelayShield INTEL — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_"
    )
    _send_telegram(ADMIN_CHAT_ID, text)


# ---------------------------------------------------------------------------
# One-time targeted message fetch (added 2026-07-24)
#
# _poll_channels() only looks at messages *since the last check* -- correct
# for ongoing monitoring, but useless for pulling a specific, already-known
# high-value message (e.g. a pinned "menu" post referenced by a credible
# external source) that predates when RelayShield started tracking the
# channel. This fetches specific message IDs directly instead, via the same
# Telethon session/connection setup _poll_channels uses -- invoked through
# the same lambda_handler lock so it can never race a scheduled poll.
#
# Not wired into the scheduled cron. Invoke manually with:
#   {"action": "fetch_specific", "targets": [{"channel": "gqdh", "msg_id": 582},
#                                             {"channel": "yewucidian", "msg_id": 16}]}
# ---------------------------------------------------------------------------

async def _fetch_specific_messages(targets: list[dict]) -> list[dict]:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    secret      = _get_secret(TELETHON_SECRET)
    api_id      = int(secret["api_id"])
    api_hash    = secret["api_hash"]
    session_str = secret["session_string"]
    client = TelegramClient(StringSession(session_str), api_id, api_hash)

    results = []
    async with client:
        for t in targets:
            channel = t["channel"]
            msg_id  = int(t["msg_id"])
            try:
                entity  = await client.get_entity(channel)
                message = await client.get_messages(entity, ids=msg_id)
                if message is None:
                    results.append({"channel": channel, "msg_id": msg_id, "error": "message not found (deleted or never existed)"})
                    continue
                text = (message.text or "") + " " + (getattr(message, "caption", "") or "")
                text = text.strip()
                if not text and message.document:
                    text = await _extract_image_text(client, message)
                results.append({
                    "channel": channel,
                    "msg_id":  msg_id,
                    "date":    message.date.isoformat() if message.date else None,
                    "views":   getattr(message, "views", None),
                    "text":    text,
                })
            except Exception as exc:
                logger.warning("Targeted fetch failed @%s msg=%s: %s", channel, msg_id, exc)
                results.append({"channel": channel, "msg_id": msg_id, "error": str(exc)})
            await asyncio.sleep(1.5)
    return results


# ---------------------------------------------------------------------------
# Telethon channel polling
# ---------------------------------------------------------------------------

async def _poll_channels(stats: dict) -> None:
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.errors import FloodWaitError, ChannelPrivateError, ChannelInvalidError
        from telethon.tl.types import InputPeerChannel
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
        since          = datetime.now(timezone.utc) - timedelta(hours=6, minutes=10)
        channels       = _load_channels()
        channels_table = _dynamodb.Table(INTEL_CHANNELS_TABLE)
        stats["channels_attempted"] = len(channels)
        logger.info("Polling %d channels", len(channels))

        for username, category, desc, channel_id, access_hash in channels:
            if channel_id is not None and access_hash is not None:
                # Cached peer — skip get_entity(username) (a ResolveUsernameRequest)
                # entirely. This is what makes the run scale past a handful of
                # channels: ResolveUsernameRequest has a tight per-session flood
                # limit that a 122-channel resolve burst trips almost immediately,
                # while InputPeerChannel makes zero Telegram calls to construct.
                entity = InputPeerChannel(channel_id, access_hash)
            else:
                try:
                    entity = await client.get_entity(username)
                except (ValueError, ChannelPrivateError) as exc:
                    logger.warning("Cannot access channel @%s: %s", username, exc)
                    continue
                except Exception as exc:
                    logger.warning("Entity lookup failed @%s: %s", username, exc)
                    continue

                # Cache the resolved peer so future runs use the fast path above.
                # Only Channel/supergroup entities carry access_hash.
                resolved_hash = getattr(entity, "access_hash", None)
                if resolved_hash is not None:
                    try:
                        channels_table.update_item(
                            Key={"username": username},
                            UpdateExpression="SET channel_id = :cid, access_hash = :ah",
                            ExpressionAttributeValues={":cid": entity.id, ":ah": resolved_hash},
                        )
                    except Exception as exc:
                        logger.warning("Failed to cache resolved peer for @%s: %s", username, exc)

                # Pace fresh resolves only — the cached path above makes no
                # Telegram call at all, so it doesn't need pacing.
                await asyncio.sleep(1.5)

            stats["channels_checked"] += 1
            msg_count = 0
            chan_iocs = chan_listings = 0

            try:
                async for message in client.iter_messages(entity, limit=300):
                    if message.date and message.date.replace(tzinfo=timezone.utc) < since:
                        break

                    msg_id = f"{username}_{message.id}"
                    if _already_seen(msg_id):
                        continue

                    # --- Build text corpus ---
                    # Captions on photos/videos are separate from text
                    msg_text = (message.text or "") + " " + (getattr(message, "caption", "") or "")
                    msg_text = msg_text.strip()

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

                    # Fix 3: OCR image attachments. Real gap found and fixed
                    # 2026-07-24: this only ran when the photo had NO caption
                    # at all (`not msg_text.strip()`) -- a phishing screenshot
                    # posted with even a one-word caption skipped OCR
                    # entirely, despite _extract_image_text already
                    # self-guarding on mime type (returns "" instantly for
                    # non-image documents, so calling it unconditionally on
                    # every message.document costs nothing extra for ZIPs/
                    # text files already handled above). Runs on every image
                    # now, appending to whatever caption already exists
                    # rather than requiring an empty one.
                    if message.document:
                        ocr_text = await _extract_image_text(client, message)
                        if ocr_text:
                            msg_text = (msg_text + "\n" + ocr_text).strip()
                            stats["images_ocrd"] = stats.get("images_ocrd", 0) + 1
                            # Image/logo brand monitoring (competitive
                            # benchmark roadmap item, added 2026-07-24):
                            # OCR'd text was already feeding the live
                            # per-message brand-alert check below, but was
                            # never persisted anywhere -- so the paid
                            # brand-monitor endpoint (a separate, on-demand
                            # lookup a customer can call any time, not just
                            # at the moment a message is first polled) had
                            # no way to search past image-derived content.
                            # Reuses the exact same relayshield_intel_iocs
                            # table + ioc_value substring-scan mechanism
                            # handle_brand_monitor() already uses -- no new
                            # table or endpoint needed for this part.
                            try:
                                _dynamodb.Table(INTEL_IOCS_TABLE).put_item(Item={
                                    "ioc_value": ocr_text[:2000].lower(),
                                    "seen_ts":   datetime.now(timezone.utc).isoformat(),
                                    "ioc_type":  "image_text",
                                    "channel":   username,
                                    "category":  category,
                                    "ttl":       Decimal(int(time.time()) + ALERT_TTL_DAYS * 86400),
                                })
                            except Exception as exc:
                                logger.warning("OCR text store failed msg=%d: %s", message.id, exc)

                    # Fix 4: Follow paste site URLs in message text
                    if msg_text:
                        for paste_url in _RE_PASTE_URL.findall(msg_text):
                            paste_content = _fetch_paste_content(paste_url)
                            if paste_content:
                                msg_text += "\n" + paste_content
                                stats["pastes_fetched"] = stats.get("pastes_fetched", 0) + 1
                                logger.info("Paste fetched url=%s chars=%d", paste_url[:60], len(paste_content))

                    # INTEL-5 archive parsing.
                    #
                    # CORPUS-3 fix, 2026-08-16. This used to read:
                    #
                    #   if category == "infostealer" and message.document and email_domain_map:
                    #
                    # Two of those three conditions made the capability nearly
                    # dead, and archives_parsed was 0 on every run:
                    #
                    # 1. The category gate allowed only 10 of 90 active channels.
                    #    It excluded ALL 19 credential_dump channels, which are
                    #    the ones most likely to post a stealer archive, plus 12
                    #    ransomware and 14 phaas. A channel's category label is
                    #    a curation note, not a statement about what it attaches.
                    # 2. email_domain_map is the monitored-customer map, so
                    #    collection itself was gated on already having customers.
                    #    That is the same "only keep what matches something we
                    #    already know" pattern that left the marketplace
                    #    contribution at 1.67%, except here it stopped us even
                    #    LOOKING.
                    #
                    # The file type is the only filter that should apply.
                    if message.document:
                        fname = ""
                        for attr in (message.document.attributes or []):
                            if hasattr(attr, "file_name"):
                                fname = (attr.file_name or "").lower()
                        if fname.endswith((".zip", ".rar", ".7z", ".tar", ".gz", ".tgz")) or (
                            not fname and getattr(message.document, "mime_type", "") in (
                                "application/zip", "application/x-zip-compressed", "application/octet-stream",
                                "application/x-rar-compressed", "application/vnd.rar", "application/x-7z-compressed",
                            )
                        ):
                            try:
                                await _process_stealer_archive(client, message, username, email_domain_map, stats)
                                stats["archives_parsed"] = stats.get("archives_parsed", 0) + 1
                            except Exception as arch_exc:
                                logger.warning("INTEL-5 archive failed @%s msg=%d: %s", username, message.id, arch_exc)

                    if not msg_text:
                        continue

                    # Enhancement: auto-queue channels found via message forwards
                    if getattr(message, "forward", None):
                        fwd = message.forward
                        try:
                            fwd_entity = getattr(fwd, "chat", None) or getattr(fwd, "sender", None)
                            if fwd_entity and hasattr(fwd_entity, "username") and fwd_entity.username:
                                fwd_username = fwd_entity.username.lower()
                                known = {ch[0].lower() for ch in channels}
                                if fwd_username not in known:
                                    tbl = _dynamodb.Table(INTEL_CHANNELS_TABLE)
                                    existing = tbl.get_item(Key={"username": fwd_username}).get("Item")
                                    if not existing:
                                        tbl.put_item(Item={
                                            "username":    fwd_username,
                                            "category":    category,
                                            "description": f"Auto-discovered via forward from @{username}",
                                            "first_seen":  datetime.now(timezone.utc).isoformat(),
                                            "active":      category in ("infostealer", "credential_dump"),
                                            "auto_joined": True,
                                        })
                                        logger.info("Forward-discovered channel @%s from @%s (auto_active=%s)",
                                                    fwd_username, username, category in ("infostealer", "credential_dump"))
                        except Exception:
                            pass
                    _mark_seen(msg_id)
                    msg_count += 1
                    stats["messages_processed"] += 1

                    # Channel discovery
                    _extract_invite_links(msg_text, username, category)
                    stats["discord_channels_discovered"] += _queue_discovered_discord_invites(msg_text, username, category)

                    # Auto-discover channels mentioned in forwarded text (Russian/Chinese/Arabic format)
                    for fwd_handle in _RE_TG_FORWARD.findall(msg_text):
                        fwd_handle = fwd_handle.lower().strip()
                        known = {ch[0].lower() for ch in channels}
                        if fwd_handle and fwd_handle not in known and len(fwd_handle) > 3:
                            try:
                                tbl = _dynamodb.Table(INTEL_CHANNELS_TABLE)
                                if not tbl.get_item(Key={"username": fwd_handle}).get("Item"):
                                    tbl.put_item(Item={
                                        "username":    fwd_handle,
                                        "category":    category,
                                        "description": f"Text-forward discovered from @{username}",
                                        "first_seen":  datetime.now(timezone.utc).isoformat(),
                                        "active":      False,
                                        "auto_joined": True,
                                    })
                                    logger.info("Text-forward discovered @%s from @%s", fwd_handle, username)
                            except Exception:
                                pass

                    # Enhancement 6+8: brand/company name monitoring — domain in plain text
                    # catches "targeting XYZ corp" mentions in criminal channels
                    try:
                        from boto3.dynamodb.conditions import Attr as _Attr
                        _user_tbl = _dynamodb.Table(USERS_TABLE)
                        _scan = _user_tbl.scan(
                            FilterExpression=_Attr("active").eq(True),
                            ProjectionExpression="user_id, monitored_domain, telegram_chat_id",
                        )
                        for _u in _scan.get("Items", []):
                            _dom = (_u.get("monitored_domain") or "").lower()
                            if _dom and len(_dom) > 4 and _dom in msg_text.lower():
                                _cid = int(_u["telegram_chat_id"]) if _u.get("telegram_chat_id") else None
                                if _cid:
                                    _brand_msg = (
                                        f"⚠️ *RelayShield Brand Alert*\n\n"
                                        f"Your domain *{_dom}* was mentioned in a criminal "
                                        f"Telegram channel (@{username}).\n\n"
                                        f"*Category:* {CATEGORY_LABELS.get(category, category)}\n"
                                        f"*Context:* _{preview}_\n\n"
                                        f"_RelayShield INTEL — brand monitoring_"
                                    )
                                    _send_telegram(_cid, _brand_msg)
                                    stats["alerts_fired"] += 1
                                    logger.info("Brand alert fired user_id=%s domain=%s channel=@%s",
                                                _u["user_id"], _dom, username)
                    except Exception as _exc:
                        logger.warning("Brand monitoring scan failed: %s", _exc)

                    # Marketplace listing extraction, CORPUS-1 2026-08-16.
                    # MUST run before the `total_iocs == 0: continue` below. A
                    # sales post is exactly the message that carries no IOC, so
                    # anything that runs after that guard never sees the content
                    # this pipeline exists to collect.
                    _listing = _extract_marketplace_listing(msg_text, username, category)
                    if _listing and _store_marketplace_listing(_listing, username, preview):
                        stats["listings_captured"] = stats.get("listings_captured", 0) + 1
                        chan_listings += 1

                    # IOC extraction
                    iocs       = extract_iocs(msg_text)
                    total_iocs = sum(len(v) for v in iocs.values())

                    # Auto-discover new Telegram channels from @mentions
                    if iocs.get("tg_mentions"):
                        discovered = _queue_discovered_channels(iocs["tg_mentions"], username)
                        stats["channels_discovered"] += discovered

                    # Tally new IOC type stats
                    stats["ransomware_victims"] += len(iocs.get("ransomware_victims", []))
                    stats["cves_extracted"]     += len(iocs.get("cves", []))
                    stats["onions_extracted"]   += len(iocs.get("onions", []))

                    if total_iocs == 0:
                        continue
                    stats["iocs_extracted"] += total_iocs
                    chan_iocs += total_iocs
                    _fam = detect_malware_families(msg_text)
                    if _fam:
                        stats["malware_tagged"] = stats.get("malware_tagged", 0) + total_iocs
                    _store_iocs(iocs, username, category, _fam)

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
                        # SIEM/SOAR forwarding — no-ops cleanly if no destination configured.
                        try:
                            user_rec = _dynamodb.Table(USERS_TABLE).get_item(Key={"user_id": user_id}).get("Item") or {}
                            siem_email = user_rec.get("email", "")
                            if siem_email:
                                siem_connector.dispatch_finding(_dynamodb, {
                                    "alert_type":  "dark_channel_match",
                                    "severity":    "HIGH",
                                    "customer_id": siem_email,
                                    "summary":     f"Criminal Telegram channel match: {match.get('type', 'unknown')} found in @{username}",
                                    "details": {
                                        "match_type": match.get("type", ""),
                                        "channel":    username,
                                        "category":   category,
                                        "preview":    preview,
                                    },
                                    "detected_at": datetime.now(timezone.utc).isoformat(),
                                })
                        except Exception as exc:
                            logger.warning("SIEM dispatch failed (non-fatal) for user_id=%s: %s", user_id, exc)

            except FloodWaitError as exc:
                logger.warning("Telegram flood wait @%s — sleeping %ds", username, exc.seconds)
                await asyncio.sleep(min(exc.seconds, 30))
            except ChannelInvalidError:
                # The cached channel_id/access_hash Telegram's server itself
                # rejects — not a transient error. Clear it so the fallback
                # get_entity() path on the next run re-resolves and re-caches
                # a fresh, valid peer instead of failing on this channel forever.
                logger.warning("Cached peer for @%s rejected by Telegram — clearing cache to force re-resolve next run", username)
                try:
                    channels_table.update_item(
                        Key={"username": username},
                        UpdateExpression="REMOVE channel_id, access_hash",
                    )
                except Exception as exc2:
                    logger.warning("Failed to clear bad cached peer for @%s: %s", username, exc2)
            except Exception as exc:
                logger.error("Error processing channel @%s: %s", username, exc)

            # CORPUS-1: record what this channel actually produced, so a quiet
            # channel and a broken one stop looking identical.
            _record_channel_yield(username, msg_count, chan_iocs, chan_listings)
            logger.info("Channel @%s: %d messages, %d IOCs, %d listings",
                        username, msg_count, chan_iocs, chan_listings)

            # Enhancement 6: Harvest replies on high-engagement posts (reply_to set)
            # Scans the last 20 messages for those with reply counts > 0 and reads their replies.
            # Criminal channels often post IOC-rich content in replies to announcements.
            try:
                # CORPUS-3: raised from 20/20. Criminal channels post an
                # announcement and put the actual payload in the replies, so a
                # 20x20 window was sampling a fraction of the richest content.
                async for post in client.iter_messages(entity, limit=60):
                    if post.date and post.date.replace(tzinfo=timezone.utc) < since:
                        break
                    reply_count = getattr(getattr(post, 'replies', None), 'replies', 0)
                    if reply_count and reply_count > 0:
                        async for reply in client.iter_messages(entity, reply_to=post.id, limit=60):
                            reply_text = (reply.text or "") + " " + (getattr(reply, "caption", "") or "")
                            reply_text = reply_text.strip()
                            if not reply_text:
                                continue
                            reply_id = f"{username}_reply_{reply.id}"
                            if _already_seen(reply_id):
                                continue
                            _mark_seen(reply_id)
                            r_iocs = extract_iocs(reply_text)
                            r_total = sum(len(v) for v in r_iocs.values())
                            if r_total > 0:
                                stats["iocs_extracted"] += r_total
                                _rfam = detect_malware_families(reply_text)
                                if _rfam:
                                    stats["malware_tagged"] = stats.get("malware_tagged", 0) + r_total
                                _store_iocs(r_iocs, username, category, _rfam)
                                logger.info("Reply IOCs: @%s post=%d reply=%d iocs=%d",
                                            username, post.id, reply.id, r_total)
            except Exception as reply_exc:
                logger.debug("Reply harvest skipped @%s: %s", username, reply_exc)


# ---------------------------------------------------------------------------
# Auto-discovery — queue @mentions from processed messages for review
# ---------------------------------------------------------------------------

_KNOWN_CHANNELS = {ch[0].lower() for ch in MONITORED_CHANNELS}
_IGNORED_MENTIONS = {
    "everyone", "here", "channel", "admin", "bot", "telegram",
    "relayshield", "relayshieldbot", "support", "help",
}

def _queue_discovered_channels(mentions: list[str], source_channel: str) -> int:
    """Write newly seen @mentions to a DynamoDB discovery queue for manual review."""
    if not mentions:
        return 0
    table   = _dynamodb.Table(INTEL_CHANNELS_TABLE)
    queued  = 0
    for mention in mentions:
        m = mention.lower().strip("@")
        if m in _KNOWN_CHANNELS or m in _IGNORED_MENTIONS or len(m) < 5:
            continue
        try:
            table.put_item(
                Item={
                    "username":      m,
                    "active":        False,          # pending review — not yet monitored
                    "discovered_from": source_channel,
                    "discovered_at": datetime.now(timezone.utc).isoformat(),
                    "category":      "pending_review",
                    "description":   f"Auto-discovered from @{source_channel}",
                },
                ConditionExpression="attribute_not_exists(username)",
            )
            queued += 1
            logger.info("Auto-discovered channel candidate: @%s (from @%s)", m, source_channel)
        except Exception:
            pass  # already exists — ignore
    return queued


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    stats = {
        "channels_checked":       0,
        "channels_attempted":     0,
        "messages_processed":     0,
        "iocs_extracted":         0,
        "images_ocrd":            0,
        "pastes_fetched":         0,
        "archives_parsed":        0,
        "listings_captured":      0,
        "user_matches":           0,
        "alerts_fired":           0,
        "ransomware_victims":     0,
        "cves_extracted":         0,
        "onions_extracted":       0,
        "channels_discovered":    0,
        "discord_channels_discovered": 0,
    }
    if not _acquire_lock():
        logger.warning("Another invocation already holds the lock — exiting without touching the Telegram session")
        return {"statusCode": 200, "body": json.dumps({"skipped": "lock_held"})}

    if (event or {}).get("action") == "fetch_specific":
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(_fetch_specific_messages(event["targets"]))
            loop.close()
            logger.info("Targeted fetch complete: %s", json.dumps(results, default=str))
            return {"statusCode": 200, "body": json.dumps(results, default=str)}
        finally:
            _release_lock()

    try:
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
    finally:
        _release_lock()
