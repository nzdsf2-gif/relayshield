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
# Ransomware leak-site victims live in their OWN table, never in the IOC table.
# The IOC table means "this thing is dangerous"; a victim name means "this
# company was attacked". Mixing them would fire credential-rotation alerts at
# breach victims and inflate the exclusivity metric with data the leak sites
# publish themselves. Added 2026-08-20.
RANSOM_VICTIMS_TABLE  = "relayshield_ransomware_victims"
# Operator identity aggregate (growth plan item 2). One row per handle rather
# than one per sighting, because the question asked of a handle is "how long
# have we been seeing this and where", which a pile of sighting rows answers
# only after a scan. The per-sighting rows still land in the IOC table; this is
# the index over them.
OPERATOR_IDS_TABLE    = "relayshield_operator_identities"

# Pivot enrichment (growth plan item 3) is OFF by default and must be switched
# on deliberately. It is the only part of this monitor that makes an outbound
# call to a host other than Telegram, and a slow third party inside the per-run
# budget would cost collection -- which is the thing this pipeline exists to do.
# Turn it on only once the run has headroom, and watch the first few runs.
PIVOT_ENRICHMENT_ENABLED = os.environ.get("PIVOT_ENRICHMENT", "").lower() in ("1", "true", "yes")
PIVOT_MAX_SEEDS_PER_RUN  = int(os.environ.get("PIVOT_MAX_SEEDS", "15"))
PIVOT_MAX_DERIVED_PER_SEED = int(os.environ.get("PIVOT_MAX_DERIVED", "25"))
PIVOT_TIME_BUDGET_SECONDS  = int(os.environ.get("PIVOT_TIME_BUDGET", "60"))
# A derived indicator is never as good as the thing it was derived from. This
# is the single most important number in the pivot: without it, one collected
# domain becomes fifty weakly-associated ones carrying the seed's authority,
# and a technical buyer who spot-checks three of them stops trusting the whole
# corpus. Derived rows are also tagged provenance="derived" so an export can
# exclude them wholesale.
PIVOT_CONFIDENCE_FACTOR    = 0.5
# Categories whose domains are worth pivoting from. A "general" or "crypto"
# chat domain is usually a legitimate site someone linked, and pivoting from it
# produces siblings of a legitimate host -- noise with a confidence score
# attached, which is worse than nothing.
PIVOT_SEED_CATEGORIES = {"phaas", "infostealer", "credential_dump", "ransomware"}
INTEL_CHANNELS_TABLE  = "relayshield_intel_channels"
STOLEN_SESSIONS_TABLE  = "relayshield_stolen_sessions"
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
# Non-human identity / machine credentials (growth plan item 6, an under-served
# category). API keys and service tokens in stealer-log dumps are higher value
# and far rarer in public feeds than passwords, and /v1/metered/nhi-exposure
# already exists to sell them — but nothing was feeding it from this pipeline.
#
# WE NEVER STORE THE SECRET. Extraction yields a provider label plus a truncated
# SHA-256 of the value, and that is what goes in the IOC table. A customer can
# fingerprint their own key and ask "is mine in there"; nobody can read one out.
# Storing live credentials in a queryable table would make this corpus a
# liability the moment anyone got a read on it, and the same rule already keeps
# /exposure from printing passwords.
_NHI_PATTERNS = (
    ("aws_access_key",   re.compile(r"\b((?:AKIA|ASIA)[0-9A-Z]{16})\b")),
    ("github_pat",       re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{36,255})\b")),
    ("slack_token",      re.compile(r"\b(xox[baprs]-[A-Za-z0-9-]{10,})\b")),
    ("stripe_secret",    re.compile(r"\b(sk_live_[A-Za-z0-9]{16,})\b")),
    ("google_api_key",   re.compile(r"\b(AIza[0-9A-Za-z_-]{35})\b")),
    ("anthropic_key",    re.compile(r"\b(sk-ant-[A-Za-z0-9_-]{20,})\b")),
    # Deliberately after anthropic_key: sk-ant- also matches the generic
    # OpenAI-style prefix, and the specific label is the useful one.
    ("openai_key",       re.compile(r"\b(sk-[A-Za-z0-9]{32,})\b")),
    ("private_key_block", re.compile(r"(-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----)")),
)


def _nhi_fingerprints(text: str) -> list:
    """Provider-labelled fingerprints of any machine credentials in `text`.

    Returns "<provider>:<first 16 hex of sha256>" — never the credential.

    The example that used to sit on this line was a made-up 16-hex string, and
    GitGuardian's generic api-key detector flagged it on commit 33d6a6f
    (incident #36505440) — a false positive on a docstring in the very function
    whose job is to make sure real credentials never get stored. It is a neat
    demonstration of the entropy-detector noise problem in
    blog-secret-scanning-false-positives.md, and it is also exactly the kind of
    alert that trains people to ignore the dashboard. No literal hex here.
    """
    out = set()
    for label, pattern in _NHI_PATTERNS:
        for m in pattern.findall(text):
            secret = m if isinstance(m, str) else m[0]
            if len(secret) < 12:
                continue
            digest = hashlib.sha256(secret.encode("utf-8", "replace")).hexdigest()[:16]
            out.add(f"{label}:{digest}")
    return sorted(out)


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
    # Invite codes were already being parsed out of this same text for channel
    # DISCOVERY (_queue_discovered_discord_invites); they were never kept as
    # indicators. An invite code is an operator-identity indicator of the same
    # kind as a Telegram handle -- it names a place a crew runs, and no public
    # feed we ingest publishes it.
    discord_invites = list({m.lower() for m in _RE_DISCORD_INVITE.findall(text)})
    nhi_tokens = _nhi_fingerprints(text)
    return {
        "emails": emails, "phones": phones,
        "eth": eth, "btc": btc, "sol": sol, "ton": ton,
        "domains": valid_domains, "ips": valid_ips,
        "sha256": sha256, "md5": md5, "sha1": sha1,
        "urls": urls, "onions": onions, "cves": cves,
        "ransomware_victims": victims,
        "tg_mentions": tg_mentions,
        "discord_invites": discord_invites,
        "nhi_tokens": nhi_tokens,
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

# ONE SOURCE OF TRUTH FOR CATEGORIES. Fixed 2026-08-21 after finding the
# vocabularies had drifted apart across four files.
#
# WHAT WAS BROKEN. `CATEGORY_LABELS` and `SEVERITY` listed five categories.
# relayshield_intel_discovery.py's SEARCH_KEYWORDS could already assign SEVEN,
# and relayshield_intel_classifier.py could assign seven more. Three of them --
# "ransomware", "crypto", "phaas" -- appeared in NEITHER dict, so
# `SEVERITY.get(category, "⚠️")` fell through to a bare warning glyph with no
# severity word, and `CATEGORY_LABELS.get(category, category)` printed the raw
# key. A user alert sourced from a ransomware channel therefore rendered as
# LESS severe than one from a card shop, which is exactly backwards.
#
# Nothing errored, nothing logged. Same silent-divergence shape as the `cves`
# and `type_map` defects, which is now the third instance in this pipeline --
# hence test_intel_category_drift.py, which fails the build when any two of the
# four vocabularies disagree.
#
# WHY IT WAS ABOUT TO GET WORSE. The OSINT-2 classifier assigns categories from
# its own list and is about to be run over the 75-channel pending_review
# backlog. Every channel it labels "ransomware", "crypto" or "phaas" would have
# produced degraded alerts from that moment on.
#
# ADDING A CATEGORY: add it here, add it to VALID_CATEGORIES in
# relayshield_intel_classifier.py, and the drift test will confirm the rest.
INTEL_CATEGORIES = {
    # category         label                       severity
    "sim_swap":        ("SIM Swap Service",        "🚨 CRITICAL"),
    "ransomware":      ("Ransomware Operation",    "🚨 CRITICAL"),
    "credential_dump": ("Credential Dump",         "🚨 HIGH"),
    "infostealer":     ("Infostealer Log Sale",    "⚠️ HIGH"),
    "phaas":           ("Phishing-as-a-Service",   "⚠️ HIGH"),
    "card_shop":       ("Card Shop",               "⚠️ MEDIUM"),
    # Added 2026-08-21 (sweep 002). Four of SOCRadar's ten most active Telegram
    # groups are hacktivist crews — NoName057(16), RipperSec, Dark Storm Team,
    # Z-Pentest Alliance — and none of the existing categories fit: they run
    # DDoS and OT-intrusion campaigns rather than selling credentials.
    # MEDIUM rather than HIGH on purpose: for an identity-protection customer a
    # hacktivist mention is context, not an account compromise. The collection
    # value is high (they publish target lists and leaked data early); the
    # per-user alert value is not, and the severity has to say which.
    "hacktivist":      ("Hacktivist Operation",    "⚠️ MEDIUM"),
    "crypto":          ("Crypto Fraud",            "⚠️ MEDIUM"),
    "general":         ("Threat Intelligence",     "ℹ️ INFO"),
}

CATEGORY_LABELS = {k: v[0] for k, v in INTEL_CATEGORIES.items()}
SEVERITY        = {k: v[1] for k, v in INTEL_CATEGORIES.items()}


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


def _record_channel_failure(username: str, error_type: str, detail: str) -> None:
    """Mark a channel as unreachable on this run, and count how many runs in a row.

    Added 2026-08-20 to make channel attrition visible. `active=True` in
    relayshield_intel_channels means "we intend to monitor this", and until now
    there was nothing anywhere meaning "and we actually can". A channel that is
    deleted, gone private, or has banned the account stayed indistinguishable
    from a healthy one in every count we report.

    Deliberately does NOT set active=False. Recovery is real (a channel can go
    private for a week and come back), and silently shrinking the collection
    surface on a transient error is the more expensive mistake. Once
    consecutive_failures is high and stable, that is a human's call to make --
    and now there is a number to make it from.
    """
    try:
        _dynamodb.Table(INTEL_CHANNELS_TABLE).update_item(
            Key={"username": username},
            UpdateExpression=(
                "SET last_error = :e, last_error_detail = :d, last_error_at = :t, "
                "consecutive_failures = if_not_exists(consecutive_failures, :zero) + :one"
            ),
            ExpressionAttributeValues={
                ":e": error_type,
                ":d": detail,
                ":t": datetime.now(timezone.utc).isoformat(),
                ":zero": 0,
                ":one": 1,
            },
        )
    except Exception as exc:
        logger.warning("Could not record failure for @%s: %s", username, exc)


def _clear_channel_failure(username: str) -> None:
    """Reset the failure counter after a channel is read successfully again."""
    try:
        _dynamodb.Table(INTEL_CHANNELS_TABLE).update_item(
            Key={"username": username},
            UpdateExpression="REMOVE last_error, last_error_detail, last_error_at, consecutive_failures",
            ConditionExpression="attribute_exists(consecutive_failures)",
        )
    except Exception:
        # No prior failure recorded is the normal case, and the conditional
        # write failing for that reason is not worth a log line.
        pass


_CORP_SUFFIXES = ("incorporated", "inc", "llc", "ltd", "limited", "corp",
                  "corporation", "group", "holdings", "co", "company", "plc", "gmbh", "sa", "ag")


def _victim_keys(raw: str) -> set:
    """Normalised match keys for a victim name.

    Returns BOTH the suffix-stripped and suffix-retained forms, because a
    customer's domain can encode either one: "Acme Corp." should match both
    acme.com and acmecorp.com, and there is no way to know in advance which
    the company actually uses.
    """
    base = re.sub(r"[^a-z0-9]+", "", (raw or "").lower())
    if not base:
        return set()
    keys = {base}
    for suf in _CORP_SUFFIXES:
        if base.endswith(suf) and len(base) > len(suf) + 2:
            keys.add(base[: -len(suf)])
    # Floor of 3, not 4. A floor of 4 silently dropped every three-letter
    # supplier -- IBM, SAP, AWS, EDF -- so a customer watching IBM could never
    # be alerted about IBM, which is a worse failure than the collision the
    # floor was guarding against. Matching is exact key equality rather than
    # substring, so "ibm" only ever matches "ibm"; short keys are not the risk
    # here. What IS a risk is a bare corporate suffix surviving as a key, so
    # those are dropped explicitly.
    return {k for k in keys if len(k) >= 3 and k not in _CORP_SUFFIXES}


def _store_ransomware_victims(victims: list, channel: str, category: str) -> int:
    """Record leak-site victim names in their own table.

    Storage is unconditional and cheap; ALERTING is not (see
    _match_supplier_breach). _RE_RANSOM_VICTIM is a loose pattern -- it takes
    capitalised words after "hacked"/"leaked"/"victim" -- so this table is a
    lead list that will contain noise, and nothing downstream should treat a
    row here as a confirmed breach.
    """
    if not victims:
        return 0
    now    = datetime.now(timezone.utc).isoformat()
    ttl    = Decimal(int(time.time()) + ALERT_TTL_DAYS * 86400)
    table  = _dynamodb.Table(RANSOM_VICTIMS_TABLE)
    stored = 0
    for name in victims:
        name = (name or "").strip()
        if len(name) < 4:
            continue
        try:
            table.put_item(Item={
                "victim_name":  name.lower(),
                "seen_ts":      now,
                "display_name": name,
                "match_keys":   sorted(_victim_keys(name)) or ["-"],
                "channel":      channel,
                "category":     category,
                "confidence":   "unverified",   # regex-extracted, never confirmed
                "ttl":          ttl,
            })
            stored += 1
        except Exception as exc:
            logger.warning("Victim store failed name=%s: %s", name[:40], exc)
    return stored


def _match_supplier_breach(victims: list) -> list:
    """Match leak-site victims against customers' declared supplier watchlists.

    OPT-IN ONLY, and deliberately so. Telling a customer "your vendor was
    breached" off a loose regex match would be worse than saying nothing: they
    would act on it, and the extraction is not reliable enough to carry that.
    So this reads `supplier_watchlist` -- an explicit list of names the customer
    entered -- and never infers suppliers from anything else.

    Matching is on normalised keys, not substrings. Substring matching on
    company names produces absurd hits ("co" inside "cisco"), and a false
    supplier-breach alert costs more trust than a missed one.
    """
    if not victims:
        return []
    wanted = {}
    for name in victims:
        for key in _victim_keys(name):
            wanted.setdefault(key, name)
    if not wanted:
        return []

    matches = []
    try:
        resp = _dynamodb.Table(USERS_TABLE).scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("supplier_watchlist").exists(),
        )
    except Exception as exc:
        logger.warning("Supplier watchlist scan failed: %s", exc)
        return []

    for item in resp.get("Items", []):
        for supplier in (item.get("supplier_watchlist") or []):
            for key in _victim_keys(str(supplier)):
                if key in wanted:
                    matches.append({
                        "user_id":  item["user_id"],
                        "matched":  str(supplier),
                        "type":     "supplier_breach",
                        "victim":   wanted[key],
                    })
                    break
    return matches


def _format_supplier_breach_alert(match: dict, channel: str, channel_desc: str) -> str:
    """Alert copy for a supplier appearing on a leak site.

    Deliberately a different message from _format_user_alert. That one says
    "your credential is in criminal hands, rotate it now". This one says "a
    company you depend on was attacked" -- the customer is not compromised, and
    the actions are third-party risk actions, not password rotation. Sending
    the IOC copy here would tell a breach victim's customer to rotate their own
    credentials for no reason, which is the whole reason victims are not in the
    IOC table.
    """
    return (
        "⚠️ *RelayShield — Supplier Breach Watch*\n\n"
        f"*{match['matched']}* is on your supplier watchlist, and a name matching it "
        "was named as a victim on a ransomware leak site.\n\n"
        f"*Named as:* `{match.get('victim', match['matched'])}`\n"
        f"*Source:* @{channel}\n"
        f"*Channel:* _{channel_desc}_\n\n"
        "*This is not a compromise of your systems.* It is a supplier of yours being "
        "attacked, which is early warning rather than an incident.\n\n"
        "*What to do now:*\n"
        "• Ask them directly what data of yours they hold and whether it was in scope\n"
        "• Rotate any credentials or API keys *you issued to them*, not your own\n"
        "• Watch for invoice-fraud and impersonation mail appearing to come from them — "
        "this is the most common follow-on\n"
        "• Do not act on any payment-detail change from them without an out-of-band call\n\n"
        "_Extracted from a criminal channel and unverified. Confirm with the supplier "
        "before acting on it as fact._"
    )


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
        # --- Added 2026-08-20. The SAME defect as the "cves" entry above, and
        # it went unnoticed for the same reason: extract_iocs() has been
        # pulling all five of these out of every monitored message since it
        # was written, and type_map never listed them, so not one was ever
        # persisted. Found while looking for ways to grow the corpus -- these
        # cost nothing to collect because we were already collecting them and
        # throwing them away.
        #
        # "tg_handle" is the scam-operator-handle category. It is the highest
        # -uniqueness type here by a distance: public feeds publish
        # infrastructure, not people, so almost none of this appears anywhere
        # else. Note _RE_TG_CHANNEL matches ANY @mention, so this is a lead
        # list, not a verdict -- the value is that each row carries the source
        # channel and its category, so a handle seen in an infostealer channel
        # can be told apart from one mentioned in passing. Filter downstream;
        # do not treat presence here as "this handle is a criminal".
        ("tg_mentions", "tg_handle"),
        # Added 2026-08-21, growth plan item 2 (operator identity). Same
        # exclusivity argument as tg_handle and the same caveat: an invite code
        # in a criminal channel is a lead, not a verdict. Kept as the bare code
        # rather than the full URL so the same server posted as discord.gg/X and
        # discord.com/invite/X deduplicates to one indicator.
        ("discord_invites", "discord_invite"),
        # Fingerprints, never secrets — see _nhi_fingerprints(). Feeds
        # /v1/metered/nhi-exposure, which existed with nothing supplying it
        # from this pipeline.
        ("nhi_tokens",      "nhi_token"),
        ("onions",      "onion"),
        ("md5",         "hash_md5"),
        ("sha1",        "hash_sha1"),
        # DELIBERATELY NOT ADDED: "ransomware_victims". Those are the names of
        # VICTIM organisations, not attacker indicators. Writing them into the
        # same table the watchlist matches against would mean a customer whose
        # company name appeared in a leak-site post gets matched as though
        # their name were an IOC. Needs its own table and its own decision.
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


# ---------------------------------------------------------------------------
# Operator identity aggregate (growth plan item 2)
# ---------------------------------------------------------------------------
# WHY A SECOND TABLE. The IOC table is append-only, one row per sighting, keyed
# (ioc_value, seen_ts). That is the right shape for infrastructure: an IP is
# malicious or it is not, and when you saw it barely matters. It is the wrong
# shape for a person. Handles get recycled, sold and abandoned, so the question
# actually asked of one is "since when, how often, and in which rooms" -- and
# answering that from sighting rows means scanning them.
#
# This keeps one row per handle, updated in place. It costs one update_item per
# handle per run and no reads, because `if_not_exists` and `ADD` let DynamoDB do
# the first-seen and the counter server-side.
#
# STILL A LEAD LIST. _RE_TG_CHANNEL matches any @mention. A handle here is not a
# criminal; it is a handle that appeared in a room we monitor. `channels` and
# `categories` are what make a row worth anything -- a handle seen four times
# across two infostealer channels reads very differently from one mentioned once
# in a general chat. Do not export this as "known scam operators".

def _store_operator_identities(iocs: dict, channel: str, category: str) -> int:
    now   = datetime.now(timezone.utc).isoformat()
    table = _dynamodb.Table(OPERATOR_IDS_TABLE)
    stored = 0
    # (field in extract_iocs output, platform label)
    for field, platform in (("tg_mentions", "telegram"), ("discord_invites", "discord")):
        for handle in iocs.get(field, []):
            handle = (handle or "").strip().lower().lstrip("@")
            if len(handle) < 3:
                continue
            try:
                table.update_item(
                    Key={"handle": handle, "platform": platform},
                    UpdateExpression=(
                        "SET first_seen = if_not_exists(first_seen, :now), "
                        "    last_seen  = :now, "
                        "    #ttl       = :ttl "
                        "ADD sightings :one, channels :ch, categories :cat"
                    ),
                    # `ttl` is a DynamoDB reserved word.
                    ExpressionAttributeNames={"#ttl": "ttl"},
                    ExpressionAttributeValues={
                        ":now": now,
                        ":one": Decimal(1),
                        # String sets, so re-seeing the same handle in the same
                        # channel does not grow the row. This is what makes
                        # "seen across N distinct rooms" cheap to read later.
                        ":ch":  {channel},
                        ":cat": {category or "unknown"},
                        # Refreshed on every sighting, so an operator we keep
                        # seeing never expires while one that goes quiet ages
                        # out. Infrastructure TTL is fixed from first write;
                        # identity should not be.
                        ":ttl": Decimal(int(time.time()) + ALERT_TTL_DAYS * 86400),
                    },
                )
                stored += 1
            except Exception as exc:
                logger.warning("Operator identity store failed handle=%s: %s", handle[:32], exc)
    return stored


# ---------------------------------------------------------------------------
# Pivot enrichment (growth plan item 3)
# ---------------------------------------------------------------------------
# One collected phishing domain is rarely alone. The certificate that covers it
# usually covers the rest of the campaign's hosts, and Certificate Transparency
# publishes that for free. A sibling found this way is OURS by derivation -- it
# inherits the seed's exclusivity without inheriting a public feed.
#
# THE RISK IS THE WHOLE POINT OF THE DESIGN. A pivot with no confidence decay
# turns one good indicator into fifty mediocre ones that all claim the seed's
# authority. So every derived row carries:
#   provenance      = "derived"          (so an export can drop them wholesale)
#   derived_from    = the seed value     (so any row can be walked back)
#   derivation      = the method used
#   confidence_score = seed * PIVOT_CONFIDENCE_FACTOR
# and nothing derived is ever used to derive again -- one hop only, enforced by
# only ever seeding from freshly collected domains.
#
# crt.sh is the same source relayshield_cert_monitor.py already uses, so this
# adds no new vendor and no new secret.

_CRT_SH_PIVOT_URL = "https://crt.sh/?q=%25.{domain}&output=json"


def _pivot_domain_siblings(domain: str) -> list[str]:
    """Sibling hostnames sharing certificate coverage with `domain`.

    Returns [] on any failure. A pivot that cannot run is a missed enrichment,
    never a failed collection run -- the caller must not care why.
    """
    try:
        req = urllib.request.Request(
            _CRT_SH_PIVOT_URL.format(domain=urllib.parse.quote(domain)),
            headers={"User-Agent": "RelayShield-IntelMonitor/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            rows = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:
        logger.info("Pivot crt.sh failed domain=%s: %s", domain, exc)
        return []

    siblings: set = set()
    for row in rows if isinstance(rows, list) else []:
        # name_value can hold several SANs separated by newlines.
        for name in str(row.get("name_value", "")).split("\n"):
            name = name.strip().lower().lstrip("*.")
            if not name or name == domain or not name.endswith("." + domain):
                continue
            if any(name.endswith(s) for s in (".local", ".internal", ".localhost", ".example")):
                continue
            siblings.add(name)
            if len(siblings) >= PIVOT_MAX_DERIVED_PER_SEED:
                return sorted(siblings)
    return sorted(siblings)


def _store_derived_iocs(derived: list, seed: str, derivation: str,
                        channel: str, category: str, seed_confidence: float = 1.0) -> int:
    """Write derived indicators, marked as derived and scored below their seed."""
    if not derived:
        return 0
    now   = datetime.now(timezone.utc).isoformat()
    ttl   = Decimal(int(time.time()) + ALERT_TTL_DAYS * 86400)
    table = _dynamodb.Table(INTEL_IOCS_TABLE)
    confidence = round(seed_confidence * PIVOT_CONFIDENCE_FACTOR, 4)
    stored = 0
    for value in derived:
        try:
            table.put_item(Item={
                "ioc_value":        value.lower(),
                "seen_ts":          now,
                "ioc_type":         "domain",
                "channel":          channel,
                "category":         category,
                "provenance":       "derived",
                "derived_from":     seed,
                "derivation":       derivation,
                "confidence_score": Decimal(str(confidence)),
                "ttl":              ttl,
            })
            stored += 1
        except Exception as exc:
            logger.warning("Derived IOC store failed value=%s: %s", value[:40], exc)
    return stored


def _run_domain_pivots(seed_domains: list, channel: str, category: str) -> int:
    """Pivot a run's freshly collected domains into campaign siblings.

    Hard-bounded on seeds, derived-per-seed and wall clock. Collection is the
    job; enrichment is a bonus that must never eat the budget.
    """
    if not PIVOT_ENRICHMENT_ENABLED or category not in PIVOT_SEED_CATEGORIES:
        return 0
    started = time.time()
    total   = 0
    for seed in seed_domains[:PIVOT_MAX_SEEDS_PER_RUN]:
        if time.time() - started > PIVOT_TIME_BUDGET_SECONDS:
            logger.info("Pivot time budget reached after %d seeds", total)
            break
        siblings = _pivot_domain_siblings(seed)
        if siblings:
            total += _store_derived_iocs(
                siblings, seed, "crt.sh:san-siblings", channel, category,
            )
    return total


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
    # Report reached-vs-intended, not just reached. "Channels checked: 95" on
    # its own looks healthy; "95 of 122 active, 27 unreachable" is the same run
    # and tells you the collection surface is degrading. Added 2026-08-20 after
    # the active count and the reachable count were found to disagree by 27
    # with nothing anywhere recording it.
    _operator_line = (
        f"Operator identities: {stats.get('operator_ids_stored', 0)} updated"
        f" ({stats.get('discord_invites', 0)} Discord invites)\n"
        # Reads 0 whenever PIVOT_ENRICHMENT is off, which is the default. A zero
        # here means "not switched on", not "found nothing".
        f"Derived indicators (pivot): {stats.get('derived_iocs', 0)}\n"
        f"Machine credentials (NHI): {stats.get('nhi_tokens', 0)} fingerprinted\n"
    )
    _victims_line = (
        f"Ransomware victims named: {stats.get('ransomware_victims', 0)}"
        f" ({stats.get('victims_stored', 0)} stored)\n"
        + (f"Supplier-breach alerts: {stats['supplier_alerts']}\n"
           if stats.get("supplier_alerts") else "")
    )
    _unreachable = stats.get("channels_unreachable", 0)
    _channels_line = (
        f"Channels checked: {stats['channels_checked']} of {stats['channels_attempted']} active"
        + (f"  ⚠️ {_unreachable} unreachable\n" if _unreachable else "\n")
    )
    text = (
        f"🔍 *INTEL-2/5 Monitor Run*\n\n"
        f"{warning}"
        f"{_channels_line}"
        f"Messages processed: {stats['messages_processed']}\n"
        f"IOCs extracted: {stats['iocs_extracted']}\n"
        f"Images OCR'd: {stats.get('images_ocrd', 0)}\n"
        f"Paste URLs followed: {stats.get('pastes_fetched', 0)}\n"
        f"ZIP/RAR archives parsed: {stats.get('archives_parsed', 0)}\n"
        f"Identity correlations: {stats.get('correlations_stored', 0)}\n"
        f"User matches: {stats['user_matches']}\n"
        f"Alerts fired: {stats['alerts_fired']}\n"
        f"Brand mentions detected: {stats.get('brand_alerts', 0)}\n"
        f"{_victims_line}"
        f"{_operator_line}"
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
                    # RECORD THE FAILURE, do not just skip it. Until 2026-08-20
                    # this was a bare `continue`: the channel stayed active=True
                    # forever and silently contributed nothing, so every count
                    # and every digest reported a collection surface larger than
                    # the one that actually exists. That is how "122 active
                    # channels" and 95 reachable ones can both be true at once,
                    # and the gap was invisible because nothing wrote it down.
                    #
                    # Nothing here flips active=False on its own -- a private
                    # channel can come back, and auto-deactivating on one bad
                    # run would quietly shrink the corpus. It records, counts,
                    # and lets the digest surface it for a human decision.
                    logger.warning("Cannot access channel @%s: %s", username, exc)
                    _record_channel_failure(username, type(exc).__name__, str(exc)[:200])
                    stats["channels_unreachable"] = stats.get("channels_unreachable", 0) + 1
                    continue
                except Exception as exc:
                    logger.warning("Entity lookup failed @%s: %s", username, exc)
                    _record_channel_failure(username, type(exc).__name__, str(exc)[:200])
                    stats["channels_unreachable"] = stats.get("channels_unreachable", 0) + 1
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
            _clear_channel_failure(username)
            msg_count = 0

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

                    # IOC extraction
                    iocs       = extract_iocs(msg_text)
                    total_iocs = sum(len(v) for v in iocs.values())

                    # Auto-discover new Telegram channels from @mentions
                    if iocs.get("tg_mentions"):
                        discovered = _queue_discovered_channels(iocs["tg_mentions"], username)
                        stats["channels_discovered"] += discovered

                    # Leak-site victims: own table, own matcher, own alert copy.
                    # Stored unconditionally (cheap, and the corpus is the
                    # point); alerts fire only for customers who explicitly
                    # entered a supplier watchlist.
                    _victims = iocs.get("ransomware_victims", [])
                    if _victims:
                        stats["victims_stored"] = stats.get("victims_stored", 0) + \
                            _store_ransomware_victims(_victims, username, category)
                        for _m in _match_supplier_breach(_victims):
                            _chat = _get_user_chat_id(_m["user_id"])
                            if _chat:
                                try:
                                    _send_telegram(_chat, _format_supplier_breach_alert(
                                        _m, username, desc))
                                    stats["supplier_alerts"] = stats.get("supplier_alerts", 0) + 1
                                    _log_alert(_m["user_id"], _m, username, category)
                                except Exception as exc:
                                    logger.warning("Supplier alert failed user=%s: %s",
                                                   _m["user_id"], exc)

                    # Operator identity: one row per handle, first/last seen and
                    # the set of rooms it appears in. Runs before the total_iocs
                    # early-return below, because a message whose only content
                    # is an @mention still tells us something about an operator.
                    if iocs.get("tg_mentions") or iocs.get("discord_invites"):
                        stats["operator_ids_stored"] = stats.get("operator_ids_stored", 0) + \
                            _store_operator_identities(iocs, username, category)

                    # Tally new IOC type stats
                    stats["ransomware_victims"] += len(iocs.get("ransomware_victims", []))
                    stats["cves_extracted"]     += len(iocs.get("cves", []))
                    stats["onions_extracted"]   += len(iocs.get("onions", []))
                    stats["discord_invites"]     = stats.get("discord_invites", 0) + \
                        len(iocs.get("discord_invites", []))
                    stats["nhi_tokens"]          = stats.get("nhi_tokens", 0) + \
                        len(iocs.get("nhi_tokens", []))

                    if total_iocs == 0:
                        continue
                    stats["iocs_extracted"] += total_iocs
                    _fam = detect_malware_families(msg_text)
                    if _fam:
                        stats["malware_tagged"] = stats.get("malware_tagged", 0) + total_iocs
                    _store_iocs(iocs, username, category, _fam)

                    # Pivot: freshly collected domains -> campaign siblings.
                    # No-ops unless PIVOT_ENRICHMENT is switched on AND the
                    # channel is in a seed category; see the block comment on
                    # _run_domain_pivots for why both gates exist.
                    if iocs.get("domains"):
                        stats["derived_iocs"] = stats.get("derived_iocs", 0) + \
                            _run_domain_pivots(iocs["domains"], username, category)

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

            logger.info("Channel @%s — processed %d messages", username, msg_count)

            # Enhancement 6: Harvest replies on high-engagement posts (reply_to set)
            # Scans the last 20 messages for those with reply counts > 0 and reads their replies.
            # Criminal channels often post IOC-rich content in replies to announcements.
            try:
                async for post in client.iter_messages(entity, limit=20):
                    if post.date and post.date.replace(tzinfo=timezone.utc) < since:
                        break
                    reply_count = getattr(getattr(post, 'replies', None), 'replies', 0)
                    if reply_count and reply_count > 0:
                        async for reply in client.iter_messages(entity, reply_to=post.id, limit=20):
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
    # CI import probe from deploy_lambdas.yml. Returning HERE -- before
    # _acquire_lock() and before any Telegram work -- is the entire point.
    # The probe only asserts that the module imported; an unrecognised payload
    # otherwise falls all the way through to a real scraping run, which on
    # every deploy would take the lock, start a full Telegram sweep, and risk a
    # flood-wait that the next scheduled run then inherits. Added 2026-08-20
    # alongside putting this function into CI deploys for the first time.
    if (event or {}).get("source") == "ci.import-probe":
        logger.info("CI import probe — module loaded, returning without a run")
        return {"statusCode": 200, "body": json.dumps({"probe": "ok"})}

    stats = {
        "channels_checked":       0,
        "channels_attempted":     0,
        "messages_processed":     0,
        "iocs_extracted":         0,
        "images_ocrd":            0,
        "pastes_fetched":         0,
        "archives_parsed":        0,
        "user_matches":           0,
        "alerts_fired":           0,
        "ransomware_victims":     0,
        "discord_invites":        0,
        "nhi_tokens":             0,
        "operator_ids_stored":    0,
        "derived_iocs":           0,
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
