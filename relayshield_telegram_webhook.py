"""
RelayShield Telegram Webhook Lambda
Receives Telegram Bot API updates and routes them based on update type
and user onboarding state.

Onboarding state machine (Telegram-first new customers):
  NEW                    → /start → show intent keyboard → plan selection
  AWAITING_PAYMENT       → waiting for successful_payment update
  AWAITING_PHONE         → request_contact button sent, waiting for phone share
  AWAITING_PHONE_CONFIRM → confirm monitored number is correct (Yes/No inline)
  AWAITING_EMAIL_1       → collect first monitored email address
  AWAITING_MORE_EMAILS   → collect additional emails (up to tier limit) or DONE
  ACTIVE                 → handle reply commands

Existing WA user linking (TELEGRAM command in WhatsApp):
  User sends 6-digit code from WhatsApp → bot validates → links telegram_chat_id

Commands (ACTIVE users):
  /help     — list all commands
  /sweep    — email security sweep
  /breach   — check breach status
  /sim      — SIM swap status
  /domain   — domain monitoring status
  /status   — account status (business admins)
  /verify   — personal verification protocol
  /otp      — unexpected OTP guidance
  /sessions — session revocation guidance
  /reuse    — cross-account password reuse walkthrough
  /phone    — carrier hardening steps
  /wascam   — suspicious message guidance
  /tgsecurity — Telegram account hardening guide
  /botcheck @username — typosquat + red flag analysis for any bot/channel
  /verifybot — confirm this is the official RelayShield bot
  /scan <url> — scan a URL or link for malware/phishing
  /analyze <text> — social engineering analysis of a suspicious message
  /addwallet <addr> — add EVM, Solana, or TON wallet to monitoring (Crypto Shield only)
  /removewallet <addr> — remove wallet from monitoring
  /wallets  — list monitored wallets with GoPlus risk scores
  LINK      — link existing WhatsApp account via 6-digit code
"""

import hashlib
import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Attr, Key

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# AWS clients
# ---------------------------------------------------------------------------

secrets_client = boto3.client("secretsmanager")
dynamodb = boto3.resource("dynamodb")
kms_client = boto3.client("kms")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KMS_KEY_ALIAS = "alias/relayshield-data-key"
PHONE_HASH_INDEX = "phone_hash-index"

USERS_TABLE             = "relayshield_users"
MONITORED_EMAILS_TABLE  = "relayshield_monitored_emails"
BREACH_ALERTS_TABLE     = "relayshield_breach_alerts"
MONITORED_WALLETS_TABLE = "relayshield_monitored_wallets"

ALCHEMY_SECRET_NAME     = "relayshield/alchemy_api_key"
GOPLUS_BASE_URL         = "https://api.gopluslabs.io/api/v1/address_security"
CHAINABUSE_URL          = "https://www.chainabuse.com/api/reports/addresses/{address}"
ALCHEMY_WEBHOOK_API     = "https://dashboard.alchemy.com/api"
WALLET_LIMIT_CRYPTO     = 5   # max wallets per Crypto Shield subscriber

TG_SECRET_NAME = "relayshield/telegram_bot_token"
TG_SECRET_KEY = "telegram_bot_token"

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"

# ---------------------------------------------------------------------------
# Tier constants (mirrors WhatsApp webhook)
# ---------------------------------------------------------------------------

TIER_PERSONAL        = "personal_shield"
TIER_STARTER         = "business_starter"
TIER_STARTER_DOMAIN  = "starter_domain"
TIER_BASIC           = "business_basic"
TIER_SHIELD          = "business_shield"
TIER_PRO             = "business_shield_pro"
TIER_CRYPTO          = "crypto_shield"

BUSINESS_TIERS = {TIER_STARTER, TIER_STARTER_DOMAIN, TIER_BASIC, TIER_SHIELD, TIER_PRO}
CRYPTO_TIERS   = {TIER_CRYPTO}

EMAIL_LIMITS = {
    TIER_PERSONAL:       3,
    TIER_STARTER:        3,
    TIER_STARTER_DOMAIN: 3,
    TIER_BASIC:          2,
    TIER_SHIELD:         2,
    TIER_PRO:            2,
}

SEAT_LIMITS = {
    TIER_STARTER: 2,
    TIER_BASIC:   5,
    TIER_SHIELD:  10,
    TIER_PRO:     25,
}

DOMAIN_TIERS = {TIER_STARTER_DOMAIN, TIER_BASIC, TIER_SHIELD, TIER_PRO}

DOMAIN_LIMITS = {
    TIER_STARTER_DOMAIN: 1,
    TIER_BASIC:          2,
    TIER_SHIELD:         2,
    TIER_PRO:            5,
}

# Plan metadata + direct Stripe monthly checkout links
PLAN_PRICES = {
    TIER_PERSONAL:       {"label": "Personal Shield",  "amount": 1499,  "currency": "usd",
                          "stripe_url": "https://buy.stripe.com/14A8wQa6y1qB8KM2JF0Ny00"},
    TIER_STARTER:        {"label": "Business Starter", "amount": 1999,  "currency": "usd",
                          "stripe_url": "https://buy.stripe.com/fZucN6ceGglv3qs9830Ny0a"},
    TIER_STARTER_DOMAIN: {"label": "Starter + Domain", "amount": 2499,  "currency": "usd",
                          "stripe_url": "https://buy.stripe.com/28EdRa2E61qB2mo3NJ0Ny0c"},
    TIER_BASIC:          {"label": "Business Basic",   "amount": 8999,  "currency": "usd",
                          "stripe_url": "https://buy.stripe.com/aFa8wQ3Iab1b8KM9830Ny03"},
    TIER_SHIELD:         {"label": "Business Shield",  "amount": 13999, "currency": "usd",
                          "stripe_url": "https://buy.stripe.com/8x24gA6Um2uF2mo9830Ny04"},
}

# ---------------------------------------------------------------------------
# Attack correlation engine
# ---------------------------------------------------------------------------

CORRELATION_WINDOW_HOURS = 72   # signals older than this are pruned
CORRELATION_DEDUP_HOURS  = 48   # suppress repeat alerts within this window

ATTACK_CHAINS = [
    {
        "chain":    "smishing_to_sim_swap",
        "signals":  {"suspicious_url", "sim_swap"},
        "severity": "CRITICAL",
        "label":    "Phishing Link → SIM Swap",
        "what": (
            "Attackers typically send a phishing link first to capture credentials, "
            "then swap or port your SIM to intercept 2FA codes. This is a known "
            "two-stage attack chain."
        ),
    },
    {
        "chain":    "breach_sim_swap",
        "signals":  {"breach_alert", "sim_swap"},
        "severity": "CRITICAL",
        "label":    "Credential Breach + SIM Swap",
        "what": (
            "Your credentials were found in a breach and your SIM was swapped or ported "
            "within the same attack window. Attackers may hold both your password and "
            "control of your phone number — all SMS 2FA is compromised."
        ),
    },
    {
        "chain":    "breach_otp_intercept",
        "signals":  {"breach_alert", "otp_warning"},
        "severity": "HIGH",
        "label":    "Credential Breach + OTP Interception",
        "what": (
            "Your credentials were recently found in a breach and you reported an "
            "unexpected OTP. This pattern suggests an active account takeover attempt — "
            "an attacker may be logging into your accounts right now."
        ),
    },
    {
        "chain":    "domain_phishing_breach",
        "signals":  {"domain_lookalike", "breach_alert"},
        "severity": "CRITICAL",
        "label":    "Phishing Domain + Credential Breach",
        "what": (
            "A domain impersonating your business was registered while your credentials "
            "are actively exposed in a breach. Attackers stand up fake login pages on "
            "lookalike domains after obtaining credentials — your employees and customers "
            "may already be targeted with phishing emails from this domain."
        ),
    },
    {
        "chain":    "oauth_breach_plus_credentials",
        "signals":  {"oauth_app_breach", "breach_alert"},
        "severity": "HIGH",
        "label":    "OAuth App Breach + Credential Exposure",
        "what": (
            "A SaaS app you may use for OAuth single sign-on was breached at the same "
            "time your credentials are exposed. Attackers who hold both your password "
            "and a compromised OAuth token can bypass 2FA entirely — they authenticate "
            "as the app, not as you. Revoke OAuth grants immediately and rotate passwords "
            "on all accounts connected to the breached app."
        ),
    },
    {
        "chain":    "oauth_breach_plus_sim_swap",
        "signals":  {"oauth_app_breach", "sim_swap"},
        "severity": "CRITICAL",
        "label":    "OAuth App Breach + SIM Swap",
        "what": (
            "A SIM swap was detected on your account in the same window as a breach of "
            "a major OAuth provider. If you use SMS-based 2FA on apps connected to that "
            "provider, both authentication factors are potentially in attacker hands. "
            "Revoke all OAuth grants, lock your SIM, and sign out of all active sessions."
        ),
    },
]

PREDICTIVE_WARNINGS = {
    "breach_sim_swap": {
        "breach_alert": (
            "⚠️ *Heads up:* Credential breaches are frequently followed by SIM swap attempts "
            "within 72 hours. Attackers use stolen credentials to pass carrier identity checks.\n\n"
            "Contact your carrier now and request a SIM lock or port freeze on your account. "
            "Use /phone for carrier-specific steps."
        ),
        "sim_swap": (
            "⚠️ *Heads up:* SIM swap activity has been detected on your line. Attackers who "
            "already hold breached credentials sometimes trigger a SIM swap to intercept your "
            "2FA codes and complete account takeovers.\n\n"
            "Check your email and banking apps for unauthorised login attempts immediately."
        ),
    },
    "smishing_to_sim_swap": {
        "suspicious_url": (
            "⚠️ *Heads up:* Phishing links are sometimes the first step in a SIM swap attack. "
            "Attackers harvest personal details from victims who click links, then use that "
            "information to impersonate you with your carrier.\n\n"
            "Do not click the link, and consider placing a SIM lock on your account as a precaution. "
            "Use /phone for steps."
        ),
        "sim_swap": (
            "⚠️ *Heads up:* A SIM swap attempt has been detected. If you recently scanned a "
            "suspicious link, the two events may be connected — attackers often use phishing "
            "to collect the personal details needed to pass carrier security checks.\n\n"
            "Report the suspicious link to your carrier immediately."
        ),
    },
    "breach_otp_intercept": {
        "breach_alert": (
            "⚠️ *Heads up:* After a credential breach, attackers sometimes trigger unexpected "
            "OTP codes to test which accounts they can access. If you receive any login codes "
            "you did not request, run /otp immediately."
        ),
        "otp_warning": (
            "⚠️ *Heads up:* To trigger this OTP, someone already has your username and password "
            "for that account. They are now trying to get past your 2FA.\n\n"
            "→ Change the password for that account immediately\n"
            "→ Run /reuse to check if that password is shared with other accounts\n"
            "→ Switch that account's 2FA from SMS to an authenticator app if possible"
        ),
    },
    "domain_phishing_breach": {
        "domain_lookalike": (
            "⚠️ *Heads up:* A lookalike domain has been registered near your business. "
            "Attackers who set up phishing domains often pair them with credential breach "
            "campaigns — your customers or employees may receive convincing phishing emails "
            "from this domain within the next 24–72 hours.\n\n"
            "Warn your team not to click unexpected login links."
        ),
        "breach_alert": (
            "⚠️ *Heads up:* A credential breach has been detected while a lookalike domain "
            "is active near your business. Attackers may direct breach victims to the fake "
            "domain to harvest additional credentials.\n\n"
            "Ensure all staff have changed passwords and enabled MFA."
        ),
    },
    "oauth_breach_plus_credentials": {
        "oauth_app_breach": (
            "⚠️ *Heads up:* A SaaS app used for OAuth login was just breached. Your credentials "
            "are also currently exposed. If you use this app for single sign-on, an attacker may "
            "be able to access your accounts without needing your password.\n\n"
            "→ Run /sessions to revoke all active sessions now\n"
            "→ Revoke OAuth grants: myaccount.google.com/permissions"
        ),
        "breach_alert": (
            "⚠️ *Heads up:* Your credentials are exposed in a breach. A major OAuth provider "
            "was recently breached in the same window. If you use OAuth/SSO to log in to apps, "
            "those sessions may be accessible to attackers without your password.\n\n"
            "Revoke OAuth grants on any breached app immediately."
        ),
    },
    "oauth_breach_plus_sim_swap": {
        "oauth_app_breach": (
            "⚠️ *Heads up:* A major OAuth provider was just breached. A SIM swap was also "
            "detected on your account recently. If you use SMS-based 2FA on apps connected to "
            "this provider, both your authentication factors may be compromised.\n\n"
            "→ Run /phone for SIM lock steps\n"
            "→ Revoke OAuth grants: myaccount.google.com/permissions"
        ),
        "sim_swap": (
            "⚠️ *Heads up:* A SIM swap was detected on your line. A major OAuth provider was "
            "also recently breached. Together these create a high-risk window — attackers with "
            "your SIM can intercept 2FA codes for any OAuth-connected app.\n\n"
            "Lock your SIM immediately and audit all OAuth grants."
        ),
    },
}

_SESSIONS_INLINE = (
    "1️⃣ *Revoke sessions now — before changing passwords:*\n"
    "→ Google: myaccount.google.com/device-activity\n"
    "→ Microsoft: mysignins.microsoft.com\n"
    "→ Facebook/Instagram: Settings → Security → Login Activity\n"
    "Sign out of every device and session you don't recognise."
)


def _fmt_delta(seconds: float) -> str:
    """Format elapsed seconds as 'Xh Ym ago'."""
    m = int(seconds // 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m ago" if h else f"{m}m ago"


def record_signal(user_id: str, signal_type: str, metadata: dict | None = None) -> list:
    """
    Append a timestamped security signal to recent_signals on the user record.
    Prunes entries older than CORRELATION_WINDOW_HOURS in the same write.
    Returns the updated signal list.
    """
    table  = dynamodb.Table(USERS_TABLE)
    now    = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=CORRELATION_WINDOW_HOURS)).isoformat()

    existing = table.get_item(Key={"user_id": user_id}).get("Item", {}).get("recent_signals", [])
    pruned   = [s for s in existing if isinstance(s, dict) and s.get("ts", "") > cutoff]
    pruned.append({"type": signal_type, "ts": now.isoformat(), "meta": metadata or {}})

    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET recent_signals = :s",
        ExpressionAttributeValues={":s": pruned},
    )
    logger.info("Signal recorded — user_id=%s type=%s", user_id, signal_type)
    return pruned


def check_and_warn_predictive(user_id: str, new_signal_type: str, signals: list, chat_id: int) -> None:
    """
    If the new signal is the first leg of a known attack chain, send a
    forward-looking warning about what may follow.
    """
    signal_types = {s.get("type") for s in signals if isinstance(s, dict)}
    for chain in ATTACK_CHAINS:
        required = set(chain["signals"])
        if new_signal_type not in required:
            continue
        present = required & signal_types
        # Only warn when this is the first signal in the chain (not a completion)
        if len(present) != 1:
            continue
        warning = PREDICTIVE_WARNINGS.get(chain["chain"], {}).get(new_signal_type)
        if warning:
            send_message(chat_id, warning)


def _build_coordinated_alert_tg(chain: dict, signals: list) -> str:
    now           = datetime.now(timezone.utc)
    chain_signals = chain["signals"]
    relevant      = sorted(
        [s for s in signals if isinstance(s, dict) and s.get("type") in chain_signals],
        key=lambda s: s.get("ts", ""),
    )

    lines = []
    for sig in relevant:
        try:
            ts  = datetime.fromisoformat(sig["ts"].replace("Z", "+00:00"))
            tsl = ts.strftime("%-d %b %H:%M UTC")
            age = _fmt_delta((now - ts).total_seconds())
        except Exception:
            tsl, age = "recently", ""
        label = sig["type"].replace("_", " ").title()
        lines.append(f"→ {label} — {tsl} ({age})" if age else f"→ {label} — {tsl}")

    # Timeline annotation for phishing→SIM swap chain
    timeline = ""
    if chain["chain"] == "smishing_to_sim_swap" and len(relevant) >= 2:
        try:
            t0    = datetime.fromisoformat(relevant[0]["ts"].replace("Z", "+00:00"))
            t1    = datetime.fromisoformat(relevant[1]["ts"].replace("Z", "+00:00"))
            gap_m = int((t1 - t0).total_seconds() / 60)
            gap_h, gap_m = divmod(gap_m, 60)
            gap_str = f"{gap_h}h {gap_m}m" if gap_h else f"{gap_m}m"
            timeline = (
                f"\n*Attack timeline:* Phishing link detected {gap_str} before SIM swap "
                f"— confirming a two-stage attack sequence.\n"
            )
        except Exception:
            pass

    # Lookalike domain block
    lookalike_block = ""
    if chain["chain"] == "domain_phishing_breach":
        for sig in relevant:
            if sig.get("type") == "domain_lookalike":
                lookalikes = sig.get("meta", {}).get("lookalikes", [])
                if lookalikes:
                    domain_lines = "\n".join(f"  • *{d}*" for d in lookalikes[:5])
                    lookalike_block = (
                        f"\n*Impersonating domain(s) detected:*\n{domain_lines}\n"
                        f"These domains may already be sending phishing emails "
                        f"to your employees and customers.\n"
                    )
                break

    icon          = "🚨" if chain["severity"] == "CRITICAL" else "⚠️"
    signals_block = "\n".join(lines) if lines else "→ Multiple signals detected"

    if chain["severity"] == "CRITICAL":
        action_block = (
            f"*Act immediately — in this order:*\n"
            f"{_SESSIONS_INLINE}\n\n"
            f"2️⃣ Run /sweep — close email backdoors the attacker may have planted\n"
            f"3️⃣ Run /phone — lock your SIM against further swaps or ports\n"
            f"4️⃣ Do not enter any one-time codes you receive"
        )
    else:
        action_block = (
            f"*Act immediately — in this order:*\n"
            f"1️⃣ Run /sessions — revoke all active sessions before changing passwords\n"
            f"2️⃣ Run /sweep — close email backdoors the attacker may have planted\n"
            f"3️⃣ Run /phone — lock your SIM against further swaps or ports\n"
            f"4️⃣ Do not enter any one-time codes you receive"
        )

    return (
        f"{icon} *{chain['severity']} — Coordinated Attack Detected*\n\n"
        f"RelayShield has identified a *{chain['label']}* attack pattern "
        f"targeting your identity.\n\n"
        f"*Signals detected:*\n{signals_block}\n"
        f"{timeline}"
        f"{lookalike_block}\n"
        f"*What this means:*\n{chain['what']}\n\n"
        f"{action_block}\n\n"
        f"🛡️ RelayShield — Coordinated Attack Detection"
    )


def check_and_fire_correlation(user_id: str, signals: list, chat_id: int) -> bool:
    """
    Evaluate the current signal set against known attack chains.
    Sends a composite Telegram alert and stamps dedup timestamp if a chain fires.
    Returns True if a composite alert was sent.
    """
    table        = dynamodb.Table(USERS_TABLE)
    signal_types = {s["type"] for s in signals if isinstance(s, dict)}

    for chain in ATTACK_CHAINS:
        if not chain["signals"].issubset(signal_types):
            continue

        # Dedup — suppress if already alerted within CORRELATION_DEDUP_HOURS
        last_ts = table.get_item(Key={"user_id": user_id}).get("Item", {}).get(
            "last_coordinated_alert_at", ""
        )
        if last_ts:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(
                    last_ts.replace("Z", "+00:00")
                )).total_seconds()
                if age < CORRELATION_DEDUP_HOURS * 3600:
                    logger.info(
                        "Coordinated alert suppressed (dedup) — user_id=%s chain=%s",
                        user_id, chain["chain"],
                    )
                    continue
            except (ValueError, TypeError):
                pass

        alert_text = _build_coordinated_alert_tg(chain, signals)
        send_message(chat_id, alert_text)
        table.update_item(
            Key={"user_id": user_id},
            UpdateExpression="SET last_coordinated_alert_at = :t",
            ExpressionAttributeValues={":t": datetime.now(timezone.utc).isoformat()},
        )
        logger.warning("COORDINATED ALERT SENT — user_id=%s chain=%s", user_id, chain["chain"])
        return True

    return False


# ---------------------------------------------------------------------------
# Secret cache (warm Lambda reuse)
# ---------------------------------------------------------------------------

_secret_cache: dict = {}


def get_secret(secret_name: str, key: str) -> str:
    if secret_name not in _secret_cache:
        resp = secrets_client.get_secret_value(SecretId=secret_name)
        _secret_cache[secret_name] = json.loads(resp["SecretString"])
    return _secret_cache[secret_name][key]


def get_bot_token() -> str:
    return get_secret(TG_SECRET_NAME, TG_SECRET_KEY)


# ---------------------------------------------------------------------------
# KMS helpers (mirrors WhatsApp webhook)
# ---------------------------------------------------------------------------

def encrypt_field(plaintext: str) -> str:
    resp = kms_client.encrypt(
        KeyId=KMS_KEY_ALIAS,
        Plaintext=plaintext.encode("utf-8"),
    )
    import base64
    return base64.b64encode(resp["CiphertextBlob"]).decode("utf-8")


def decrypt_field(ciphertext_b64: str) -> str:
    import base64
    blob = base64.b64decode(ciphertext_b64)
    resp = kms_client.decrypt(CiphertextBlob=blob)
    return resp["Plaintext"].decode("utf-8")


def hash_phone(phone: str) -> str:
    normalized = re.sub(r"\D", "", phone)
    if not normalized.startswith("1") and len(normalized) == 10:
        normalized = "1" + normalized
    return hashlib.sha256(normalized.encode()).hexdigest()


def hash_email(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


# ---------------------------------------------------------------------------
# Telegram API helpers
# ---------------------------------------------------------------------------

def tg_api(method: str, payload: dict) -> dict:
    """Call Telegram Bot API. Returns parsed JSON response."""
    token = get_bot_token()
    url = TELEGRAM_API_BASE.format(token=token, method=method)
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error("Telegram API error %s %s: %s", method, e.code, body)
        return {}


def download_telegram_photo(photo_array: list) -> bytes | None:
    """
    Download the largest photo from a Telegram message.photo array.
    Returns raw image bytes or None on failure.
    """
    try:
        token = get_bot_token()
        # photo_array is sorted smallest→largest; take the last (highest res)
        file_id = photo_array[-1]["file_id"]
        # getFile → returns file_path
        url = TELEGRAM_API_BASE.format(token=token, method="getFile")
        data = json.dumps({"file_id": file_id}).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        file_path = result.get("result", {}).get("file_path")
        if not file_path:
            return None
        download_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
        with urllib.request.urlopen(download_url, timeout=20) as resp:
            return resp.read()
    except Exception as exc:
        logger.error("Failed to download Telegram photo: %s", exc)
        return None


def run_textract_ocr(image_bytes: bytes) -> str | None:
    """
    Extract text from an image using AWS Rekognition DetectText.
    Returns all LINE detections joined as a single string, or None on failure.
    """
    try:
        client = boto3.client("rekognition")
        response = client.detect_text(Image={"Bytes": image_bytes})
        lines = [
            d["DetectedText"]
            for d in response.get("TextDetections", [])
            if d.get("Type") == "LINE"
        ]
        return " ".join(lines) if lines else None
    except Exception as exc:
        logger.error("Rekognition OCR failed: %s", exc)
        return None


def send_message(chat_id: int, text: str, reply_markup: dict = None,
                 parse_mode: str = "Markdown") -> dict:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg_api("sendMessage", payload)


def answer_callback(callback_query_id: str, text: str = "") -> dict:
    return tg_api("answerCallbackQuery", {
        "callback_query_id": callback_query_id,
        "text": text,
    })


def request_contact(chat_id: int, text: str) -> dict:
    """Send a message with a request_contact keyboard button."""
    return send_message(
        chat_id,
        text,
        reply_markup={
            "keyboard": [[{
                "text": "📱 Share my phone number",
                "request_contact": True,
            }]],
            "resize_keyboard": True,
            "one_time_keyboard": True,
        },
        parse_mode="Markdown",
    )


def remove_keyboard(chat_id: int, text: str) -> dict:
    """Send a message that removes the custom keyboard."""
    return send_message(
        chat_id,
        text,
        reply_markup={"remove_keyboard": True},
    )


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def generate_invite_code() -> str:
    """Generate an 8-character alphanumeric invite code for team member onboarding."""
    import random
    import string
    chars = string.ascii_uppercase + string.digits
    # Ensure at least one letter so it never collides with 6-digit WA link codes
    return ''.join(random.choices(chars, k=8))


def get_team_members(admin_user_id: str) -> list[dict]:
    """Return all active team members belonging to this admin's team."""
    table = dynamodb.Table(USERS_TABLE)
    resp = table.scan(
        FilterExpression=Attr("team_id").eq(admin_user_id) & Attr("active").eq(True)
    )
    return resp.get("Items", [])


def find_invite_code(code: str) -> dict | None:
    """Find an admin user record with this pending invite code."""
    table = dynamodb.Table(USERS_TABLE)
    resp = table.scan(
        FilterExpression=Attr("pending_invite_code").eq(code)
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def get_user_by_chat_id(chat_id: int) -> dict | None:
    """Return active user record for this Telegram chat_id."""
    table = dynamodb.Table(USERS_TABLE)
    resp = table.scan(
        FilterExpression=Attr("telegram_chat_id").eq(str(chat_id)) & Attr("active").eq(True)
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def get_any_user_by_chat_id(chat_id: int) -> dict | None:
    """Return any record (active or pre-payment) for this Telegram chat_id."""
    table = dynamodb.Table(USERS_TABLE)
    resp = table.scan(
        FilterExpression=Attr("telegram_chat_id").eq(str(chat_id))
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def save_pre_payment_record(chat_id: int, tier: str) -> None:
    """
    Create or update a pre-payment placeholder record when user taps
    'Choose this plan'. The Stripe webhook finds this record via
    client_reference_id and advances state to AWAITING_PHONE.
    """
    existing = get_any_user_by_chat_id(chat_id)
    if existing:
        state = existing.get("onboarding_state", "")
        # Don't overwrite records that have progressed past payment
        if state in ("AWAITING_PHONE", "AWAITING_PHONE_CONFIRM",
                     "AWAITING_EMAIL_1", "AWAITING_MORE_EMAILS", "ACTIVE"):
            return
        # Update tier if user changed their plan selection
        update_user(existing["user_id"], {
            "subscription_tier": tier,
            "tier": tier,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        return

    # No record yet — create pre-payment placeholder
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    table = dynamodb.Table(USERS_TABLE)
    table.put_item(Item={
        "user_id": user_id,
        "telegram_chat_id": str(chat_id),
        "subscription_tier": tier,
        "tier": tier,
        "onboarding_state": "AWAITING_PAYMENT",
        "preferred_channel": "telegram",
        "delivery_channels": ["telegram"],
        "active": False,
        "monitored_emails": [],
        "recent_signals": [],
        "created_at": now,
        "updated_at": now,
    })


def create_telegram_user(chat_id: int, tier: str, first_name: str) -> dict:
    table = dynamodb.Table(USERS_TABLE)
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "user_id": user_id,
        "telegram_chat_id": str(chat_id),
        "preferred_channel": "telegram",
        "delivery_channels": ["telegram"],
        "tier": tier,
        "active": True,
        "onboarding_state": "AWAITING_PHONE",
        "created_at": now,
        "first_name": first_name,
        "monitored_emails": [],
        "recent_signals": [],
    }
    table.put_item(Item=item)
    return item


def update_user(user_id: str, updates: dict) -> None:
    table = dynamodb.Table(USERS_TABLE)
    expr_parts = []
    names = {}
    values = {}
    for i, (k, v) in enumerate(updates.items()):
        placeholder_name = f"#f{i}"
        placeholder_val = f":v{i}"
        names[placeholder_name] = k
        values[placeholder_val] = v
        expr_parts.append(f"{placeholder_name} = {placeholder_val}")
    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


# ---------------------------------------------------------------------------
# Inline keyboard builders
# ---------------------------------------------------------------------------

def intent_keyboard() -> dict:
    """Who are you protecting? — routes to relevant plan tiers."""
    return {
        "inline_keyboard": [
            [{"text": "🙋 Just myself", "callback_data": "intent_personal"}],
            [{"text": "🏢 My business + employees", "callback_data": "intent_business"}],
            [{"text": "🤝 My clients (MSP / consultant)", "callback_data": "intent_msp"}],
        ]
    }


def personal_plan_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "Personal Shield — $14.99/mo | 1 seat", "callback_data": f"planinfo_{TIER_PERSONAL}"}],
            [{"text": "Business Starter — $19.99/mo | 2 seats", "callback_data": f"planinfo_{TIER_STARTER}"}],
            [{"text": "Starter + Domain — $24.99/mo | 2 seats + domain", "callback_data": f"planinfo_{TIER_STARTER_DOMAIN}"}],
        ]
    }


def business_plan_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "Business Starter — $19.99/mo | 2 seats", "callback_data": f"planinfo_{TIER_STARTER}"}],
            [{"text": "Starter + Domain — $24.99/mo | 2 seats + domain", "callback_data": f"planinfo_{TIER_STARTER_DOMAIN}"}],
            [{"text": "Business Basic — $89.99/mo | up to 5 seats", "callback_data": f"planinfo_{TIER_BASIC}"}],
            [{"text": "Business Shield — $139.99/mo | up to 10 seats", "callback_data": f"planinfo_{TIER_SHIELD}"}],
            [{"text": "📞 Contact us for Business Shield Pro", "callback_data": "plan_contact"}],
        ]
    }


def see_all_plans_keyboard(intent: str) -> dict:
    """Back button to return to plan list after viewing a feature card."""
    return {
        "inline_keyboard": [
            [{"text": "◀️ See all plans", "callback_data": f"back_plans_{intent}"}],
        ]
    }


def plan_confirm_keyboard(tier: str, intent: str) -> dict:
    return {
        "inline_keyboard": [
            [{"text": "✅ Choose this plan", "callback_data": f"plan_{tier}"}],
            [{"text": "◀️ See all plans", "callback_data": f"back_plans_{intent}"}],
        ]
    }


# ---------------------------------------------------------------------------
# Plan feature cards
# ---------------------------------------------------------------------------

PLAN_FEATURE_CARDS = {
    TIER_PERSONAL: (
        "🛡️ *Personal Shield — $14.99/mo*\n\n"
        "👤 1 seat\n"
        "📧 Up to 3 email addresses monitored\n"
        "📱 SIM/eSIM swap detection\n"
        "🔍 Breach alerts with AI-powered remediation\n"
        "🔗 Phishing URL + attachment analysis\n"
        "📊 Monthly security digest\n"
        "💬 Telegram or WhatsApp delivery"
    ),
    TIER_STARTER: (
        "🛡️ *Business Starter — $19.99/mo*\n\n"
        "👥 2 seats (owner + contractor)\n"
        "📧 Up to 3 emails monitored per seat\n"
        "📱 SIM/eSIM swap detection\n"
        "🔍 Breach alerts with AI-powered remediation\n"
        "🔔 Admin notified when employee has a breach\n"
        "👥 /status dashboard for seat management\n"
        "📊 Monthly security digest\n"
        "💬 Telegram or WhatsApp delivery"
    ),
    TIER_STARTER_DOMAIN: (
        "🛡️ *Starter + Domain — $24.99/mo*\n\n"
        "👥 2 seats (owner + contractor)\n"
        "📧 Up to 3 emails monitored per seat\n"
        "🌐 1 domain monitored for lookalikes + cert transparency\n"
        "📱 SIM/eSIM swap detection\n"
        "🔍 Breach alerts with AI-powered remediation\n"
        "📊 Monthly security digest\n"
        "💬 Telegram or WhatsApp delivery"
    ),
    TIER_BASIC: (
        "🛡️ *Business Basic — $89.99/mo*\n\n"
        "👥 Up to 5 seats\n"
        "📧 2 emails monitored per person\n"
        "🌐 2 domains monitored for lookalikes\n"
        "📱 SIM/eSIM swap detection\n"
        "🔍 Breach alerts with AI-powered remediation\n"
        "🔔 Admin co-notification on all employee breaches\n"
        "📲 *Dual delivery: WhatsApp + Telegram simultaneously*\n"
        "🔐 Monthly OAuth connected-app audit\n"
        "📊 Monthly security digest"
    ),
    TIER_SHIELD: (
        "🛡️ *Business Shield — $139.99/mo*\n\n"
        "👥 Up to 10 seats\n"
        "📧 2 emails monitored per person\n"
        "🌐 2 domains monitored for lookalikes\n"
        "📱 SIM/eSIM swap detection + carrier disable guidance\n"
        "🔍 Breach alerts with AI-powered remediation\n"
        "🔔 Admin co-notification on all employee breaches\n"
        "📲 *Dual delivery: WhatsApp + Telegram simultaneously*\n"
        "🔐 Monthly OAuth connected-app audit\n"
        "⚡ Enhanced SIM swap response + FCC complaint guidance\n"
        "📊 Monthly security digest"
    ),
}


def confirm_phone_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "✅ Yes, that's correct", "callback_data": "phone_confirm_yes"}],
            [{"text": "❌ Use a different number", "callback_data": "phone_confirm_no"}],
        ]
    }


def done_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "✅ Done adding emails", "callback_data": "emails_done"}],
        ]
    }


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------

def msg_welcome() -> str:
    return (
        "🛡️ *Welcome to RelayShield*\n\n"
        "I monitor your identity 24/7 — breach alerts, SIM swap detection, "
        "domain lookalike scanning, and phishing analysis.\n\n"
        "✅ *You can verify this is the official bot* at relayshield.net "
        "or type /verify at any time.\n\n"
        "Who are you protecting?"
    )


def msg_help(tier: str) -> str:
    is_business = tier in BUSINESS_TIERS

    text = (
        "🛡️ *RelayShield — Commands*\n\n"

        "*🔐 Breach Response*\n"
        "• /breach — Breach monitoring status\n"
        "• /sweep — Close email backdoors (forwarding rules, filters, sessions)\n"
        "• /sessions — Revoke active sessions across Google, Microsoft, social media\n"
        "• /extensions — Audit browser extensions for infostealer malware\n"
        "• /reuse — Cross-account password reuse check\n\n"

        "*🚨 Threat Analysis*\n"
        "• /otp — Unexpected OTP guidance\n"
        "• /scam — Suspicious message, bot, or call guidance\n"
        "• /scan <url> — Scan a suspicious link for malware or phishing\n"
        "• /analyze — Screenshot a suspicious email or scam message and send the photo with caption /analyze\n"
        "• /verify — Callback rule, OTP rule, safe word, wire transfer protocol\n\n"

        "*📡 Phone Protection*\n"
        "• /sim — SIM swap monitoring status\n"
        "• /phone — Carrier hardening against SIM swap and smishing\n"
        "• /vishing — Voice phishing: how to recognise and respond to phone-based attacks\n\n"

        "*🤖 Telegram Security*\n"
        "• /tgsecurity — Harden your Telegram account against takeover\n"
        "• /botcheck @username — Analyse a bot or channel for typosquatting and red flags\n"
        "• /verifybot — Confirm this is the official RelayShield bot\n"
    )

    if is_business:
        text += (
            "\n*🏢 Team Management*\n"
            "• /status — Seat usage and team overview\n"
            "• /addmember — Generate an invite code for a new team member\n"
            "• /removemember — Remove a team member from your account\n"
        )

    if tier in CRYPTO_TIERS:
        text += (
            "\n*🪙 Crypto Shield*\n"
            "• /addwallet <address> — Add a wallet to monitoring (EVM, Solana, TON, Bitcoin)\n"
            "• /wallets — List your monitored wallets\n"
            "• /removewallet <address> — Remove a wallet from monitoring\n"
            "• /riskcheck — Risk score for all your monitored wallets\n"
            "• /approvals — Scan your EVM wallets for dangerous token approvals and revoke them\n"
            "• /checkvault <url> — Check a DeFi protocol for audit and contract risks\n"
            "• /checktoken <address> — Check a token contract for rug pull and honeypot risks\n"
            "• /checknft <address> — Check an NFT collection contract for risks\n"
        )

    if tier in DOMAIN_TIERS:
        text += (
            "\n*🌐 Domain Security*\n"
            "• /domain — Domain monitoring status and enrolled domains\n"
        "• /domainadd — Enroll a new domain for monitoring\n"
        )

    text += (
        "\n*⚙️ Admin*\n"
        "• /myid — Your Telegram chat ID (account linking & support)\n"
        "• /help — This menu\n\n"
        "Tap any command to get started."
    )

    return text


def msg_onboarding_complete(first_name: str, email_count: int, tier: str) -> str:
    return (
        f"✅ *You're protected, {first_name}!*\n\n"
        f"*SIM swap monitoring:* Active\n"
        f"*Breach monitoring:* Active for {email_count} email(s)\n\n"
        "I'll alert you the moment a threat is detected.\n\n"
        "Type /help to see all available commands."
    )


# ---------------------------------------------------------------------------
# Onboarding handlers
# ---------------------------------------------------------------------------

def handle_start(chat_id: int, first_name: str) -> None:
    """Handle /start — check if existing user, otherwise begin onboarding."""
    user = get_user_by_chat_id(chat_id)
    if user and user.get("onboarding_state") == "ACTIVE":
        send_message(chat_id, f"Welcome back, {first_name}! Type /help to see your commands.")
        return

    send_message(chat_id, msg_welcome(), reply_markup=intent_keyboard())


def handle_intent_callback(chat_id: int, intent: str, callback_query_id: str,
                           first_name: str) -> None:
    """Route intent selection to the appropriate plan keyboard."""
    answer_callback(callback_query_id)

    if intent == "personal":
        send_message(
            chat_id,
            "Tap a plan to see what's included:",
            reply_markup=personal_plan_keyboard(),
        )
    elif intent in ("business", "msp"):
        send_message(
            chat_id,
            "Tap a plan to see what's included:",
            reply_markup=business_plan_keyboard(),
        )


def handle_planinfo_callback(chat_id: int, tier: str, callback_query_id: str,
                             intent: str) -> None:
    """User tapped a plan — show feature card with confirm/back buttons."""
    answer_callback(callback_query_id)
    card = PLAN_FEATURE_CARDS.get(tier, "Plan details coming soon.")
    send_message(
        chat_id,
        card,
        reply_markup=plan_confirm_keyboard(tier, intent),
    )


def handle_plan_callback(chat_id: int, tier: str, callback_query_id: str,
                         first_name: str) -> None:
    """User confirmed plan selection — initiate payment."""
    answer_callback(callback_query_id)

    if tier == "contact":
        send_message(
            chat_id,
            "📞 *Contact us for Business Shield Pro*\n\n"
            "📧 relayshieldadmin@gmail.com\n"
            "📱 RelayShield Support: +1 339 298-7368\n\n"
            "We'll get back to you within 24 hours.",
        )
        return

    plan = PLAN_PRICES.get(tier, {})
    label = plan.get("label", tier)
    amount_dollars = plan.get("amount", 0) / 100
    base_stripe_url = plan.get("stripe_url", "https://relayshield.net")

    # Save pre-payment record so Stripe webhook can link payment to this chat
    save_pre_payment_record(chat_id, tier)

    # Append chat_id as client_reference_id — Stripe passes this back on
    # checkout.session.completed so the webhook can find and advance this record
    stripe_url = f"{base_stripe_url}?client_reference_id={chat_id}"

    send_message(
        chat_id,
        f"✅ Great choice — *{label}* (${amount_dollars:.2f}/mo)\n\n"
        f"👉 [Subscribe now]({stripe_url})\n\n"
        f"Once payment is complete, return here and I'll finish setting up your protection.\n\n"
        f"_Prefer annual billing? Contact us at relayshieldadmin@gmail.com for a discounted annual plan._",
    )


def handle_link_code(chat_id: int, code: str, first_name: str) -> None:
    """Validate 6-digit code from existing WA user linking flow."""
    table = dynamodb.Table(USERS_TABLE)
    resp = table.scan(
        FilterExpression=Attr("telegram_link_code").eq(code)
    )
    items = resp.get("Items", [])
    if not items:
        send_message(chat_id, "❌ Invalid or expired code. Please request a new code via WhatsApp.")
        return

    user = items[0]
    expiry_str = user.get("telegram_link_expiry", "")
    if expiry_str:
        expiry = datetime.fromisoformat(expiry_str)
        if datetime.now(timezone.utc) > expiry:
            send_message(chat_id, "⏱️ That code has expired. Please request a new one via WhatsApp.")
            return

    tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)
    is_business_plus = tier in {TIER_BASIC, TIER_SHIELD, TIER_PRO}
    new_channel = "both" if is_business_plus else "telegram"
    new_channels = (["whatsapp", "telegram"] if is_business_plus else ["telegram"])

    update_user(user["user_id"], {
        "telegram_chat_id": str(chat_id),
        "preferred_channel": new_channel,
        "delivery_channels": new_channels,
        "telegram_link_code": None,
        "telegram_link_expiry": None,
    })

    send_message(
        chat_id,
        "✅ *RelayShield connected.*\n\n"
        + ("You'll now receive alerts on both WhatsApp and Telegram." if is_business_plus
           else "You'll now receive alerts here on Telegram."),
    )


def handle_phone_contact(chat_id: int, phone_number: str, user: dict) -> None:
    """User shared their phone number via request_contact."""
    send_message(
        chat_id,
        f"We'll monitor *{phone_number}* for SIM swap activity — is that correct?",
        reply_markup=confirm_phone_keyboard(),
    )
    update_user(user["user_id"], {"pending_phone": phone_number})


def handle_phone_confirm(chat_id: int, confirmed: bool, user: dict) -> None:
    """User confirmed or rejected the phone number."""
    if not confirmed:
        send_message(
            chat_id,
            "No problem — please type the number you'd like monitored.\n\nExample: `+1 555 123 4567`",
            parse_mode="Markdown",
        )
        return

    phone_raw = user.get("pending_phone", "")
    phone_enc = encrypt_field(phone_raw)
    phone_hash = hash_phone(phone_raw)

    update_user(user["user_id"], {
        "phone_encrypted": phone_enc,
        "phone_hash": phone_hash,
        "pending_phone": None,
        "onboarding_state": "AWAITING_EMAIL_1",
    })

    remove_keyboard(
        chat_id,
        "✅ SIM swap monitoring activated.\n\n"
        "Now let's monitor your email addresses for breaches.\n\n"
        "Send your first email address:",
    )


def handle_email_input(chat_id: int, email: str, user: dict) -> None:
    """Validate and store an email address during onboarding."""
    email = email.strip().lower()
    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        send_message(chat_id, "That doesn't look like a valid email address. Please try again:")
        return

    tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)
    limit = EMAIL_LIMITS.get(tier, 3)
    monitored = user.get("monitored_emails", [])

    email_hash = hash_email(email)
    if email_hash in [hash_email(e) for e in monitored]:
        send_message(chat_id, "That email is already being monitored. Send another or tap Done:")
        send_message(chat_id, "Add another email address, or tap Done:", reply_markup=done_keyboard())
        return

    monitored.append(email)
    # Store email in monitored_emails table
    me_table = dynamodb.Table(MONITORED_EMAILS_TABLE)
    email_enc = encrypt_field(email)
    me_table.put_item(Item={
        "email_id": str(uuid.uuid4()),
        "user_id": user["user_id"],
        "email_encrypted": email_enc,
        "email_hash": email_hash,
        "tier": tier,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "active": True,
    })

    update_user(user["user_id"], {"monitored_emails": monitored})

    if len(monitored) >= limit:
        # Reached email limit — complete onboarding
        _complete_onboarding(chat_id, user, monitored)
    else:
        send_message(
            chat_id,
            f"✅ *{email}* added ({len(monitored)}/{limit}).\n\n"
            "Add another email address, or tap Done:",
            reply_markup=done_keyboard(),
        )
        update_user(user["user_id"], {"onboarding_state": "AWAITING_MORE_EMAILS"})


def _complete_onboarding(chat_id: int, user: dict, emails: list) -> None:
    tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)

    # Domain tier users: collect business domain before finishing
    if tier in DOMAIN_TIERS and not user.get("monitored_domains"):
        update_user(user["user_id"], {"onboarding_state": "AWAITING_DOMAIN"})
        domain_limit = DOMAIN_LIMITS.get(tier, 1)
        send_message(
            chat_id,
            f"✅ Email monitoring activated.\n\n"
            f"🌐 *Domain Security Setup*\n\n"
            f"Your plan includes monitoring up to *{domain_limit}* business domain{'s' if domain_limit > 1 else ''} "
            f"for lookalike/typosquat attacks.\n\n"
            f"Send your business domain now (e.g. `acme.com`):",
            parse_mode="Markdown",
        )
        return

    update_user(user["user_id"], {"onboarding_state": "ACTIVE"})
    first_name = user.get("first_name", "there")
    send_message(chat_id, msg_onboarding_complete(first_name, len(emails), tier))


def handle_domain_input(chat_id: int, text: str, user: dict) -> None:
    """Validate and store a business domain during onboarding (AWAITING_DOMAIN state)."""
    domain = text.strip().lower()

    # Handle /domain relayshield.net syntax — strip the command prefix
    if domain.startswith("/domain"):
        parts = domain.split(None, 1)
        if len(parts) > 1:
            domain = parts[1].strip()
        else:
            send_message(
                chat_id,
                "Please send your business domain name, e.g. `relayshield.net`:",
                parse_mode="Markdown",
            )
            return

    # Strip protocol/www if user pastes a full URL
    domain = re.sub(r"^https?://", "", domain)
    domain = re.sub(r"^www\.", "", domain)
    domain = domain.split("/")[0]  # strip any path

    # Basic domain validation
    if not re.match(r"^[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?(\.[a-z]{2,})+$", domain):
        send_message(
            chat_id,
            "That doesn't look like a valid domain. Please send just the domain name, e.g. `acme.com`:",
            parse_mode="Markdown",
        )
        return

    tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)
    domain_limit = DOMAIN_LIMITS.get(tier, 1)
    monitored_domains = user.get("monitored_domains") or []

    if domain in monitored_domains:
        send_message(chat_id, f"`{domain}` is already being monitored.", parse_mode="Markdown")
    else:
        monitored_domains.append(domain)
        update_user(user["user_id"], {"monitored_domains": monitored_domains})

    emails = user.get("monitored_emails", [])
    first_name = user.get("first_name", "there")

    if len(monitored_domains) < domain_limit:
        send_message(
            chat_id,
            f"✅ *{domain}* added ({len(monitored_domains)}/{domain_limit}).\n\n"
            f"Send another domain, or type `done` to finish:",
            parse_mode="Markdown",
        )
    else:
        update_user(user["user_id"], {"onboarding_state": "ACTIVE"})
        send_message(
            chat_id,
            f"✅ *{domain}* added.\n\n" + msg_onboarding_complete(first_name, len(emails), tier),
            parse_mode="Markdown",
        )


# ---------------------------------------------------------------------------
# Active user command handlers
# ---------------------------------------------------------------------------

def handle_myid(chat_id: int) -> None:
    """Return the user's Telegram chat ID — useful for account linking and support."""
    send_message(
        chat_id,
        f"🪪 *Your Telegram Chat ID*\n\n`{chat_id}`\n\n"
        "Use this to link your account or when contacting RelayShield support.",
        parse_mode="Markdown",
    )


def handle_help(chat_id: int, user: dict) -> None:
    tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)
    send_message(chat_id, msg_help(tier))


def handle_verify(chat_id: int) -> None:
    send_message(
        chat_id,
        "🔐 *Personal Verification Protocol*\n\n"
        "*1. Callback rule:* Hang up. Call back on the official number.\n"
        "*2. OTP rule:* No legitimate organisation asks you to read back a code.\n"
        "*3. Family safe word:* Agree on a word now. If they can't say it, hang up.\n"
        "*4. Wire transfer rule:* Always call a known number to verify before sending money.\n\n"
        "Set these four rules with your family before an attack — not during one.",
    )


def handle_otp(chat_id: int, user: dict | None = None) -> None:
    send_message(
        chat_id,
        "🚨 *Unexpected OTP — Act Now*\n\n"
        "Someone is trying to access your account.\n\n"
        "*Immediate steps:*\n"
        "1. Do NOT share the code with anyone\n"
        "2. Change your password on that account immediately\n"
        "3. Check for other active sessions and sign them out\n"
        "4. Enable app-based 2FA (not SMS) if available\n"
        "5. If your phone number was involved, contact your carrier immediately\n\n"
        "This may be a SIM swap attempt in progress.",
    )
    if user:
        signals = record_signal(user["user_id"], "otp_warning")
        check_and_warn_predictive(user["user_id"], "otp_warning", signals, chat_id)
        check_and_fire_correlation(user["user_id"], signals, chat_id)


def handle_sweep(chat_id: int) -> None:
    send_message(
        chat_id,
        "🔍 *Email Security Sweep — 5 Steps*\n\n"
        "Attackers plant backdoors after a breach. They survive password resets.\n\n"
        "✅ *Steps 2, 4 and 5 work on any device — phone, tablet, or computer.*\n\n"
        "*Step 2 — Check recovery email and phone*\n"
        "Gmail: myaccount.google.com/security\n"
        "Yahoo: account.yahoo.com/security\n"
        "→ Remove any recovery contact you don't recognise.\n\n"
        "*Step 4 — Review connected apps*\n"
        "Gmail: myaccount.google.com/permissions\n"
        "Yahoo: account.yahoo.com/security/connected-apps\n"
        "→ Revoke anything unrecognised.\n\n"
        "*Step 5 — Check active sessions*\n"
        "Gmail: myaccount.google.com/device-activity\n"
        "Yahoo: account.yahoo.com/security/recent-activity\n"
        "→ Sign out of all unknown sessions.\n\n"
        "_(Steps 1 & 3 follow in the next message)_",
    )
    send_message(
        chat_id,
        "📋 *Steps 1 & 3 — Forwarding Rules & Inbox Filters*\n\n"
        "💻 *On a computer:* Open mail.google.com in any browser — no extra steps needed.\n\n"
        "📱 *On a phone or tablet:* The Gmail app cannot access these settings. "
        "Use Chrome or Safari with desktop view enabled:\n"
        "🍎 *iOS Safari:* mail.google.com → tap aA → Request Desktop Website\n"
        "🍎 *iOS Chrome:* tap ••• → Request Desktop Site\n"
        "🤖 *Android Chrome:* tap ⋮ → Request Desktop Site\n\n"
        "*Step 1 — Forwarding rules*\n"
        "Attackers plant a forwarding address so every email is silently copied to them — it survives password resets.\n"
        "Gmail: Settings → See all settings → Forwarding and POP/IMAP\n"
        "Outlook: Settings → Mail → Forwarding\n"
        "Yahoo: Settings → Mailboxes → your address → Forwarding\n"
        "✅ Safe: no forwarding addresses listed.\n"
        "⚠️ If you see an address you didn't add: disable it → remove → Save.\n\n"
        "*Step 3 — Inbox filters*\n"
        "Silent rules can hide breach warnings and delete bank alerts.\n"
        "Gmail: Settings → Filters and Blocked Addresses\n"
        "Outlook: Settings → Rules → delete unknown rules.\n"
        "→ Delete any filter you didn't create.\n\n"
        "✅ *Sweep complete. All 5 checks done.*",
    )


def handle_vishing(chat_id: int) -> None:
    send_message(
        chat_id,
        "📞 *Vishing — Voice Phishing Defence*\n\n"
        "Vishing is fraud conducted over the phone. The caller impersonates a trusted "
        "authority — a bank, government agency, carrier, tech company, or professional service. "
        "The goal is always the same: pressure you into acting before you think.\n\n"
        "*How to recognise an attack in progress:*\n"
        "• Unsolicited call, often urgent or threatening — your account is suspended, "
        "you owe an overdue payment, action required within 24 hours\n"
        "• Caller already knows some of your details (name, address, last 4 digits) "
        "and uses them to build false trust\n"
        "• Request to confirm identity by reading back a code you just received — "
        "this is the attacker triggering the code themselves\n"
        "• Pressure to stay on the line, not hang up, or keep the call confidential\n"
        "• Asked to pay via gift card, wire transfer, cryptocurrency, or a 'secure account'\n"
        "• Transferred to a 'supervisor' or 'fraud specialist' who increases the pressure\n\n"
        "*✅ Do:*\n"
        "→ Hang up and call back on the official number from the company's website or "
        "the back of your card — never redial a number the caller gives you\n"
        "→ Tell someone else about the call before taking any action\n"
        "→ Check your accounts independently after any unsolicited call\n"
        "→ Report the call: FTC reportfraud.ftc.gov / FCC fcc.gov/consumers\n\n"
        "*🚫 Don't:*\n"
        "→ Read back any OTP or verification code — no legitimate company needs this\n"
        "→ Allow remote access to your device under any circumstances\n"
        "→ Confirm, correct, or add to personal details the caller already seems to know\n"
        "→ Stay on the line because they told you not to hang up\n"
        "→ Act within any time limit they set — urgency is the weapon, not the deadline\n\n"
        "*After a suspected vishing call:*\n"
        "→ Run /sweep — vishing often runs alongside inbox takeover\n"
        "→ Run /sessions — sign out of all active sessions\n"
        "→ Run /verify — review your personal verification protocol\n\n"
        "Use /verify to set up your Callback Rule, OTP Rule, and Family Safe Word "
        "before an attack — not after.",
    )


def handle_phone_hardening(chat_id: int) -> None:
    send_message(
        chat_id,
        "📱 *Carrier Hardening — SIM Swap Defence*\n\n"
        "*AT&T:* att.com → Profile → Wireless passcode → Add extra security\n"
        "*T-Mobile:* Account Lock at t-mobile.com\n"
        "*Verizon:* Number Lock at verizon.com/myverizon\n\n"
        "*All carriers:*\n"
        "• Set a SIM PIN\n"
        "• Add a port freeze\n"
        "• Remove SMS as a 2FA method on critical accounts\n"
        "• Use an authenticator app instead",
    )


def handle_verify_bot(chat_id: int) -> None:
    send_message(
        chat_id,
        "✅ *Verifying RelayShield Bot Authenticity*\n\n"
        "You are talking to the official RelayShield bot.\n\n"
        "*How to confirm independently:*\n"
        "1. Visit *relayshield.net* — the official bot username is listed there\n"
        "2. The official username is *@RelayShield\\_bot* — verify it matches exactly "
        "(watch for 0 vs O, l vs I, rn vs m)\n\n"
        "*What RelayShield will never ask for:*\n"
        "• Your password or PIN\n"
        "• Your Telegram login code\n"
        "• Seed phrases or private keys\n"
        "• Payment outside of the official Stripe checkout link\n\n"
        "If you received a suspicious message from a bot claiming to be RelayShield, "
        "report it immediately at relayshieldadmin@gmail.com.",
    )


def handle_tgsecurity(chat_id: int) -> None:
    send_message(
        chat_id,
        "🔐 *Telegram Account Hardening*\n\n"
        "Telegram accounts are phone-number based — a SIM swap gives an attacker full access. "
        "These steps close the most common takeover paths.\n\n"
        "*Step 1 — Enable Two-Step Verification (2SV)*\n"
        "Settings → Privacy and Security → Two-Step Verification\n"
        "→ Set a strong password *different* from all other accounts\n"
        "→ This blocks takeover even if your SIM is swapped\n\n"
        "*Step 2 — Review active sessions*\n"
        "Settings → Privacy and Security → Active Sessions\n"
        "→ Terminate any session you don't recognise\n"
        "→ Do this immediately if you suspect compromise\n\n"
        "*Step 3 — Lock down your phone number visibility*\n"
        "Settings → Privacy and Security → Phone Number\n"
        "→ Set 'Who can see my phone number' to *Nobody*\n"
        "→ Set 'Who can find me by my phone number' to *My Contacts*\n\n"
        "*Step 4 — Control who can add you to groups*\n"
        "Settings → Privacy and Security → Groups & Channels\n"
        "→ Set to *My Contacts* to block scam group adds\n\n"
        "*Step 5 — Never share your login code*\n"
        "Telegram will never ask for your SMS login code\n"
        "→ Any bot or person asking for it is an attacker\n"
        "→ Report and block immediately\n\n"
        "RelayShield monitors your phone number for SIM swap activity — "
        "if your carrier is compromised, you'll be alerted before your Telegram is taken over.",
    )


def _levenshtein(a: str, b: str) -> int:
    """Compute edit distance between two strings."""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (ca != cb)))
        prev = curr
    return prev[-1]


def _botcheck_analyze(username: str) -> str:
    """
    Analyse a Telegram username for typosquatting and red flag patterns.
    Returns a formatted risk summary string.
    """
    u = username.lower().strip().lstrip("@")

    # Known legitimate bot usernames (canonical lowercase, no @)
    # Covers common impersonation targets: Telegram official, crypto exchanges,
    # payment apps, utility bots, and RelayShield itself.
    KNOWN_BOTS = [
        # Telegram official
        "botfather", "telegram", "telegramtips", "storebot", "pollbot",
        "gif", "pic", "vote", "ifttt",
        # Utility / info bots
        "userinfobot", "getidsbot", "rose", "combot", "shieldsiobot",
        "controllerbot", "grouphelpbot",
        # Crypto exchanges
        "coinbase_bot", "binance_bot", "kraken_bot", "ledger_bot",
        "bybit_bot", "kucoin_bot", "okx_bot", "gemini_bot",
        # Payment / fintech
        "paypal_bot", "cashapp_bot", "venmo_bot", "wise_bot",
        "revolut_bot", "stripe_bot",
        # RelayShield
        "relayshield_bot",
    ]

    # Common visual substitutions used in typosquatting
    SUBSTITUTIONS = [
        ("rn", "m"), ("0", "o"), ("1", "l"), ("1", "i"),
        ("vv", "w"), ("ii", "u"), ("nn", "m"), ("cl", "d"),
        ("_", ""), ("-", ""),
    ]

    # Red flag keywords in usernames
    RED_FLAG_WORDS = [
        "support", "help", "official", "admin", "verify", "secure",
        "wallet", "crypto", "airdrop", "giveaway", "free", "bonus",
        "reward", "claim", "recovery", "refund", "urgent", "alert",
        "service", "care", "assist", "info", "real", "legit", "true",
        "original", "authentic", "safe", "trust", "login", "signin",
    ]

    flags = []
    warnings = []

    # Check red flag keywords
    for word in RED_FLAG_WORDS:
        if word in u:
            flags.append(f"contains '{word}' — common in scam/impersonator usernames")

    # Check for trailing numbers (e.g. relayshield_bot2, telegrambot123)
    if re.search(r"_?\d+$", u):
        flags.append("ends with numbers — impersonators often append digits to clone a taken username")

    # Check for double underscores or excessive underscores
    if "__" in u:
        flags.append("contains double underscore — unusual for legitimate bots")

    # Check for numeric character substitutions mid-name (0 for o, 1 for l/i)
    if re.search(r"[0-9]", u) and not re.search(r"_?\d+$", u):
        flags.append("contains numbers mid-name — check for 0→o or 1→l substitutions")

    # Lookalike similarity against known bots using proper edit distance
    lookalikes = []
    for known in KNOWN_BOTS:
        if u == known:
            # Exact match — this IS the known bot, not a lookalike
            continue
        # Normalise both strings with visual substitutions before comparing
        normalised_u = u
        normalised_k = known
        for fake, real in SUBSTITUTIONS:
            normalised_u = normalised_u.replace(fake, real)
            normalised_k = normalised_k.replace(fake, real)
        # Allow up to 2 edits for short names, 3 for longer ones
        dist = _levenshtein(normalised_u, normalised_k)
        threshold = 2 if len(normalised_k) <= 10 else 3
        if dist <= threshold and dist > 0:
            lookalikes.append(f"@{known} (edit distance: {dist})")

    if lookalikes:
        warnings.append(f"Similar to known bot(s): {', '.join(lookalikes)}")

    # Build result
    if not flags and not warnings:
        result = (
            f"🤖 *Botcheck: @{username}*\n\n"
            f"No automatic red flags detected.\n\n"
            f"⚠️ *This check has limits* — it catches known patterns only. "
            f"It cannot confirm a bot is safe or verify who operates it.\n\n"
            f"*Always check manually:*\n"
            f"→ Verify this exact username on the company's official website\n"
            f"→ Confirm the bot doesn't ask for passwords, codes, or crypto\n"
            f"→ Check for a blue verification checkmark on associated channels\n"
            f"→ Official channels have a blue ✓ — verify it links to the real company"
        )
    else:
        flag_lines = "\n".join(f"🚩 {f}" for f in flags)
        warn_lines = "\n".join(f"⚠️ {w}" for w in warnings)
        combined = "\n".join(filter(None, [warn_lines, flag_lines]))
        result = (
            f"🤖 *Botcheck: @{username}*\n\n"
            f"⚠️ *Risk signals detected:*\n"
            f"{combined}\n\n"
            f"*Recommended actions:*\n"
            f"→ Do not share credentials, codes, or payment with this bot\n"
            f"→ Verify the username character-by-character against the official website\n"
            f"→ If you've already interacted, run /sweep and /sessions immediately"
        )
    return result


def handle_botcheck(chat_id: int, username: str | None = None) -> None:
    if username:
        send_message(chat_id, _botcheck_analyze(username))
        return

    send_message(
        chat_id,
        "🤖 *Bot Verification*\n\n"
        "To analyze a specific bot or channel, type:\n"
        "`/botcheck @username`\n\n"
        "I'll check for typosquatting, red flag keywords, and similarity "
        "to known legitimate bots.\n\n"
        "*General rules before trusting any bot:*\n"
        "→ Find it from the official website — never from a link sent by a stranger\n"
        "→ Verify the username character by character (rn vs m, 0 vs o, l vs I)\n"
        "→ Legitimate bots never ask for passwords, seed phrases, or login codes\n"
        "→ Legitimate bots never ask you to send crypto 'to verify your wallet'\n"
        "→ Telegram admins cannot DM you first — anyone who does is an impersonator\n"
        "→ Official channels have a blue ✓ — verify it links to the real company\n\n"
        "Use /verifybot to confirm this bot is the official RelayShield.",
        parse_mode="Markdown",
    )


def handle_scan(chat_id: int, target: str | None = None, user: dict | None = None) -> None:
    """Scan a URL or file link for threats — Telegram equivalent of ATTACH."""
    if not target:
        send_message(
            chat_id,
            "🔍 *URL / File Scanner*\n\n"
            "Send me a suspicious link to scan:\n"
            "`/scan https://example.com`\n\n"
            "I'll check it for malware, phishing, and reputation signals.",
            parse_mode="Markdown",
        )
        return
    send_message(chat_id, f"🔍 Scanning `{target}` — one moment...", parse_mode="Markdown")
    try:
        from relayshield_mcp_server import check_url  # noqa: F401
        result = check_url(target)
        send_message(chat_id, f"🔍 *Scan result for* `{target}`\n\n{result}", parse_mode="Markdown")
    except Exception:
        send_message(
            chat_id,
            f"🔍 *Scan:* `{target}`\n\n"
            "*Red flags to check manually:*\n"
            "→ Domain registered recently (check whois)\n"
            "→ URL shortener hiding the real destination\n"
            "→ Mismatched domain (paypa1.com, g00gle.com)\n"
            "→ HTTP instead of HTTPS\n"
            "→ Urgent language prompting you to act immediately\n\n"
            "If in doubt, do not click the link.",
            parse_mode="Markdown",
        )
    # Record signal regardless of scan outcome — the user encountered a suspicious URL
    if user:
        signals = record_signal(user["user_id"], "suspicious_url", {"url": target})
        check_and_warn_predictive(user["user_id"], "suspicious_url", signals, chat_id)
        check_and_fire_correlation(user["user_id"], signals, chat_id)


def handle_analyze(chat_id: int, content: str | None = None) -> None:
    """Analyze suspicious message text — Telegram equivalent of SMS/EMAIL."""
    if not content:
        send_message(
            chat_id,
            "🧠 *Message Analyzer*\n\n"
            "Forward or paste a suspicious message:\n"
            "`/analyze <paste message here>`\n\n"
            "I'll identify social engineering patterns, urgency tactics, and impersonation signals.",
            parse_mode="Markdown",
        )
        return

    # Pattern-based analysis
    content_lower = content.lower()
    flags = []

    # Brand / authority impersonation
    BRANDS = [
        ("crypto.com", "Crypto.com"), ("coinbase", "Coinbase"), ("binance", "Binance"),
        ("paypal", "PayPal"), ("cash app", "Cash App"), ("venmo", "Venmo"),
        ("zelle", "Zelle"), ("bank of america", "Bank of America"), ("chase", "Chase"),
        ("wells fargo", "Wells Fargo"), ("citibank", "Citibank"), ("capital one", "Capital One"),
        ("at&t", "AT&T"), ("t-mobile", "T-Mobile"), ("verizon", "Verizon"),
        ("apple", "Apple"), ("google", "Google"), ("microsoft", "Microsoft"),
        ("amazon", "Amazon"), ("netflix", "Netflix"), ("irs", "IRS"),
        ("social security", "Social Security"), ("medicare", "Medicare"),
        ("usps", "USPS"), ("fedex", "FedEx"), ("ups", "UPS"),
        ("metamask", "MetaMask"), ("ledger", "Ledger"), ("kraken", "Kraken"),
        # Tech support / security software brands (common refund/renewal scam targets)
        ("geek squad", "Geek Squad"), ("best buy", "Best Buy"),
        ("norton", "Norton"), ("mcafee", "McAfee"), ("kaspersky", "Kaspersky"),
        ("avg", "AVG"), ("avast", "Avast"), ("malwarebytes", "Malwarebytes"),
        ("pc support", "PC Support"), ("tech support", "Tech Support"),
    ]
    matched_brands = [display for kw, display in BRANDS if kw in content_lower]
    if matched_brands:
        flags.append(f"🚩 Brand impersonation: *{', '.join(matched_brands)}*")

    # Callback phone number — biggest red flag in link-free smishing
    phone_matches = re.findall(r"\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}", content)
    if phone_matches:
        numbers_str = ", ".join(phone_matches)
        flags.append(
            f"🚩 Callback number: *{numbers_str}* — legitimate companies never ask you "
            f"to call a number in an unsolicited text"
        )

    # Account security pretense
    ACCOUNT_PRETENSE = [
        "new device", "unauthorized", "unusual activity", "suspicious login",
        "account suspended", "account locked", "security alert", "security notice",
        "verify your account", "confirm your identity", "unrecognized device",
        "prevent unauthorized", "secure your account",
    ]
    for phrase in ACCOUNT_PRETENSE:
        if phrase in content_lower:
            flags.append(f"🚩 Account security pretense: *'{phrase}'*")
            break

    # Urgency / threat language
    urgency_words = ["urgent", "immediately", "act now", "limited time", "expire", "suspended",
                     "verify now", "confirm now", "within 24", "account locked", "failure to",
                     "will be terminated", "right away"]
    for word in urgency_words:
        if word in content_lower:
            flags.append(f"🚩 Urgency tactic: *'{word}'*")
            break

    # Reward / prize bait
    reward_words = ["winner", "won", "prize", "claim", "reward", "gift card", "free", "bonus",
                    "airdrop", "giveaway", "investment", "guaranteed return"]
    for word in reward_words:
        if word in content_lower:
            flags.append(f"🚩 Reward/scarcity lure: *'{word}'*")
            break

    # Credential harvesting
    credential_words = ["password", "social security", "ssn", "credit card", "cvv",
                        "seed phrase", "private key", "login code", "verification code"]
    for word in credential_words:
        if word in content_lower:
            flags.append(f"🚩 Credential harvesting: asks for *'{word}'*")
            break

    # Tech support / refund scam patterns
    TECH_SUPPORT_PHRASES = [
        "renewal amount", "auto-renew", "auto renewal", "subscription renewing",
        "order received", "order id", "order date", "subscription id",
        "call us", "call immediately", "call our", "helpline", "toll-free",
        "to cancel", "to stop", "cancel your subscription", "cancel this charge",
        "refund", "we have charged", "you have been charged", "charged to your account",
        "3 year", "2 year", "annual subscription", "yearly subscription",
    ]
    tech_hits = [p for p in TECH_SUPPORT_PHRASES if p in content_lower]
    if tech_hits:
        flags.append(f"🚩 Tech support/refund scam pattern: *'{tech_hits[0]}'*")

    # Suspicious link
    if re.search(r"https?://\S+|bit\.ly|tinyurl|t\.co", content_lower):
        flags.append("🚩 Contains a link — verify with /scan before clicking")

    severity = "HIGH" if len(flags) >= 3 else "MEDIUM" if flags else "LOW"
    icon = "🚨" if severity == "HIGH" else "⚠️" if severity == "MEDIUM" else "✅"

    if flags:
        flag_text = "\n".join(flags)
        callback_warn = ""
        if phone_matches:
            callback_warn = (
                "\n*Do NOT call these numbers.* Look up the real company's number "
                "on their official website independently.\n"
            )
        send_message(
            chat_id,
            f"🧠 *Message Analysis — {severity} RISK*\n\n"
            f"{icon} *{len(flags)} social engineering signal(s) detected:*\n{flag_text}\n"
            f"{callback_warn}\n"
            f"*Recommended action:* Do not click, reply, or call any number in this message. "
            f"If this claims to be from a company, contact them directly via their official website.\n\n"
            f"Reply /vishing for a full guide on phone-based scam tactics.",
            parse_mode="Markdown",
        )
    else:
        send_message(
            chat_id,
            "🧠 *Message Analysis*\n\n"
            "✅ No automatic red flags detected in the text.\n\n"
            "This doesn't guarantee the message is safe — always verify unexpected requests "
            "by calling back on a number you look up yourself.",
            parse_mode="Markdown",
        )


def handle_wascam(chat_id: int) -> None:
    send_message(
        chat_id,
        "⚠️ *Suspicious Message — What to Check*\n\n"
        "*Bank/financial impersonation:*\n"
        "Hang up. Call the number on the back of your card.\n\n"
        "*Carrier impersonation:*\n"
        "Carriers never ask for your PIN or account number unsolicited.\n\n"
        "*Family emergency scam (Hi Mum/Dad):*\n"
        "Call your family member directly on their known number.\n\n"
        "*Government impersonation:*\n"
        "IRS, Social Security, HMRC, CRA, Medicare — they all contact you by postal mail first. "
        "No government agency demands immediate payment by gift card, wire transfer, or cryptocurrency. "
        "No government agency threatens arrest unless you pay right now. "
        "No government agency asks you to keep the call secret.\n"
        "• IRS: irs.gov/payments or call 1-800-829-1040\n"
        "• Social Security: ssa.gov or call 1-800-772-1213\n"
        "• Medicare: medicare.gov or call 1-800-633-4227\n"
        "• Report SSA/IRS scam calls: reportfraud.ftc.gov\n\n"
        "*Verify any request:*\n"
        "• No legitimate org sends urgent payment requests via text\n"
        "• No legitimate org asks you to run a command or click a link to prove you're human\n"
        "• When in doubt, call back on a number you look up yourself",
    )


def handle_extensions(chat_id: int) -> None:
    send_message(
        chat_id,
        "🔍 *Browser Extension Audit*\n\n"
        "Malicious extensions silently steal passwords, session cookies, and crypto wallet keys. "
        "Do this audit now:\n\n"
        "*Chrome / Edge:* chrome://extensions\n"
        "→ Remove anything you don't recognise or haven't used recently\n\n"
        "*Firefox:* about:addons\n"
        "→ Remove unfamiliar extensions\n\n"
        "*Safari:* Settings → Extensions\n"
        "→ Disable and remove unknown items\n\n"
        "*What to look for:*\n"
        "→ Extensions with vague names like 'PDF Helper', 'Video Downloader', 'AI Assistant'\n"
        "→ Extensions with broad permissions: 'Read and change all your data on all websites'\n"
        "→ Extensions you don't remember installing\n\n"
        "*After the audit:* restart your browser. If behaviour improves, an extension was the cause.\n\n"
        "If you suspect active infection, run *Malwarebytes Free* (malwarebytes.com) *before* "
        "changing any passwords — changing passwords on a compromised device gives attackers your new credentials.\n\n"
        "_RelayShield_",
    )


def handle_sessions(chat_id: int) -> None:
    send_message(
        chat_id,
        "🔒 *Session Revocation — Sign Out Everything*\n\n"
        "*Google:* myaccount.google.com → Security → Your devices\n"
        "*Microsoft:* mysignins.microsoft.com\n"
        "*Apple:* Settings → Your name → scroll down to devices\n"
        "*Facebook:* Settings → Security → Where you're logged in\n"
        "*Twitter/X:* Settings → Security → Sessions\n\n"
        "After signing out all sessions, change your password immediately.",
    )


def handle_status(chat_id: int, user: dict) -> None:
    tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)
    emails = user.get("monitored_emails", [])
    channels = user.get("delivery_channels", ["telegram"])
    is_business = tier in BUSINESS_TIERS
    seat_limit = SEAT_LIMITS.get(tier, 1)

    text = (
        f"📊 *Account Status*\n\n"
        f"*Plan:* {tier.replace('_', ' ').title()}\n"
        f"*SIM monitoring:* {'✅ Active' if user.get('phone_encrypted') else '⚠️ Pending setup'}\n"
        f"*Emails monitored:* {len(emails)}\n"
        f"*Delivery:* {', '.join(channels)}\n"
    )

    if is_business:
        is_admin = user.get("is_team_admin", False)
        team_id = user.get("team_id")

        if is_admin:
            members = get_team_members(user["user_id"])
            seats_used = len(members) + 1  # +1 for admin
            text += f"\n*👥 Team Seats:* {seats_used} of {seat_limit} used\n"
            if members:
                text += "\n*Team Members:*\n"
                for m in members:
                    name = m.get("first_name", "Unknown")
                    sim = "✅" if m.get("phone_encrypted") else "⚠️"
                    breach = "✅" if m.get("monitored_emails") else "⚠️"
                    text += f"• {name} — SIM {sim} Breach {breach}\n"
            text += "\nUse /addmember to invite a new member or /removemember to remove one."
        elif team_id:
            text += f"\n*Role:* Team Member\n"

    send_message(chat_id, text, parse_mode="Markdown")


def handle_addmember(chat_id: int, user: dict) -> None:
    """Generate a one-time invite code for a new team member."""
    tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)
    if tier not in BUSINESS_TIERS:
        send_message(chat_id, "Team management is available on Business plans. Upgrade at relayshield.net.")
        return

    seat_limit = SEAT_LIMITS.get(tier, 1)
    members = get_team_members(user["user_id"])
    seats_used = len(members) + 1  # +1 for admin

    if seats_used >= seat_limit:
        send_message(
            chat_id,
            f"👥 You've reached your seat limit ({seat_limit} seats on your current plan).\n\n"
            "To add more members, upgrade your plan at relayshield.net or contact relayshieldadmin@gmail.com.",
            parse_mode="Markdown",
        )
        return

    code = generate_invite_code()
    expiry = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

    update_user(user["user_id"], {
        "is_team_admin": True,
        "team_id": user["user_id"],
        "pending_invite_code": code,
        "pending_invite_expiry": expiry,
    })

    send_message(
        chat_id,
        f"✅ *Team Invite Code*\n\n"
        f"`{code}`\n\n"
        f"Share this code with your new team member. They should open @RelayShield\\_bot, "
        f"type /start, and enter this code when prompted.\n\n"
        f"*Expires in:* 7 days\n"
        f"*Seats:* {seats_used} of {seat_limit} used\n\n"
        f"_Generate a new code at any time with /addmember._",
        parse_mode="Markdown",
    )


def handle_removemember(chat_id: int, user: dict) -> None:
    """List team members for removal selection."""
    tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)
    if tier not in BUSINESS_TIERS:
        send_message(chat_id, "Team management is available on Business plans.")
        return

    if not user.get("is_team_admin"):
        send_message(chat_id, "Only the account admin can remove team members.")
        return

    members = get_team_members(user["user_id"])
    if not members:
        send_message(chat_id, "No team members enrolled yet. Use /addmember to invite someone.")
        return

    lines = []
    member_ids = []
    for i, m in enumerate(members, 1):
        name = m.get("first_name", "Unknown")
        sim = "✅ SIM" if m.get("phone_encrypted") else "⚠️ SIM"
        lines.append(f"{i}. {name} — {sim}")
        member_ids.append(m["user_id"])

    update_user(user["user_id"], {
        "onboarding_state": "AWAITING_REMOVE_SELECT",
        "pending_remove_list": member_ids,
    })

    send_message(
        chat_id,
        f"👥 *Remove a Team Member*\n\n"
        + "\n".join(lines)
        + "\n\nType the *list number* to remove that member (e.g. `1`), or type `cancel` to go back:",
        parse_mode="Markdown",
    )


def handle_sim_status(chat_id: int, user: dict) -> None:
    """Show SIM swap monitoring status for this account."""
    phone_enc = user.get("phone_encrypted")
    sim_active = bool(phone_enc)
    tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)

    if sim_active:
        send_message(
            chat_id,
            "📡 *SIM Swap Monitoring — Active*\n\n"
            "✅ Your phone number is enrolled and being monitored 24/7.\n\n"
            "We alert you immediately if your carrier shows signs of a SIM or eSIM swap — "
            "before an attacker can use your number to access your accounts.\n\n"
            "*What we detect:*\n"
            "• Unexpected SIM/eSIM changes at your carrier\n"
            "• Port-out fraud attempts\n"
            "• Number re-assignment activity\n\n"
            "If you receive a SIM swap alert, reply immediately — time is critical.\n\n"
            "🛡️ RelayShield",
            parse_mode="Markdown",
        )
    else:
        send_message(
            chat_id,
            "📡 *SIM Swap Monitoring — Not Active*\n\n"
            "Your phone number has not been enrolled.\n\n"
            "To activate monitoring, restart setup with /start or contact support at "
            "relayshieldadmin@gmail.com.\n\n"
            "🛡️ RelayShield",
            parse_mode="Markdown",
        )


def handle_breach_status(chat_id: int, user: dict) -> None:
    """Show breach monitoring status — list monitored emails and alert count."""
    user_id = user.get("user_id")
    me_table = dynamodb.Table(MONITORED_EMAILS_TABLE)

    try:
        response = me_table.query(
            IndexName="user_id-index",
            KeyConditionExpression=Key("user_id").eq(user_id),
        )
        emails = response.get("Items", [])
    except Exception:
        emails = []

    if not emails:
        update_user(user["user_id"], {"onboarding_state": "AWAITING_BREACH_EMAIL"})
        send_message(
            chat_id,
            "🔍 *Breach Monitoring — No emails enrolled*\n\n"
            "Send an email address to start monitoring (e.g. `you@example.com`):\n\n"
            "_Type_ `cancel` _to go back._",
            parse_mode="Markdown",
        )
        return

    lines = []
    for item in emails:
        active = item.get("active", True)
        label = "✅ Active" if active else "⏸ Paused"
        # Email is encrypted — show partial info only
        lines.append(f"• {label} (enrolled {item.get('created_at', '')[:10]})")

    email_block = "\n".join(lines)
    count = len(emails)
    send_message(
        chat_id,
        f"🔍 *Breach Monitoring — {count} email{'s' if count != 1 else ''} enrolled*\n\n"
        f"{email_block}\n\n"
        "You'll receive an alert here the moment any monitored address appears in a new breach.\n\n"
        "🛡️ RelayShield",
        parse_mode="Markdown",
    )


def handle_domain_add(chat_id: int, domain_raw: str, user: dict) -> None:
    """Add a new domain to monitoring for an active domain-tier user."""
    tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)

    if tier not in DOMAIN_TIERS:
        send_message(
            chat_id,
            "🌐 Domain monitoring is available on Business Basic and higher plans.\n\n"
            "Upgrade at relayshield.net.",
            parse_mode="Markdown",
        )
        return

    # Normalise — strip protocol, www, path
    domain = domain_raw.strip().lower()
    domain = re.sub(r"^https?://", "", domain)
    domain = re.sub(r"^www\.", "", domain)
    domain = domain.split("/")[0]

    if not re.match(r"^[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?(\.[a-z]{2,})+$", domain):
        send_message(
            chat_id,
            "That doesn't look like a valid domain. Please send just the domain name, e.g. `acme.com`:",
            parse_mode="Markdown",
        )
        return

    domain_limit = DOMAIN_LIMITS.get(tier, 1)
    monitored_domains = user.get("monitored_domains") or []

    if domain in monitored_domains:
        send_message(
            chat_id,
            f"✅ `{domain}` is already enrolled for monitoring.",
            parse_mode="Markdown",
        )
        return

    if len(monitored_domains) >= domain_limit:
        send_message(
            chat_id,
            f"🌐 You've reached your domain limit ({domain_limit} domain{'s' if domain_limit > 1 else ''} "
            f"on your current plan).\n\n"
            "To monitor additional domains, upgrade your plan at relayshield.net or contact "
            "relayshieldadmin@gmail.com.",
            parse_mode="Markdown",
        )
        return

    monitored_domains.append(domain)
    update_user(user["user_id"], {"monitored_domains": monitored_domains})

    send_message(
        chat_id,
        f"✅ *{domain}* enrolled for domain monitoring.\n\n"
        f"*{len(monitored_domains)} of {domain_limit}* domain slot{'s' if domain_limit > 1 else ''} in use.\n\n"
        "We'll alert you if lookalike or typosquat domains are registered against it.\n\n"
        "🛡️ RelayShield",
        parse_mode="Markdown",
    )


def handle_domainadd_prompt(chat_id: int, user: dict) -> None:
    """Tap /domainadd — set state and ask for domain name conversationally."""
    tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)
    if tier not in DOMAIN_TIERS:
        send_message(
            chat_id,
            "🌐 Domain monitoring is available on Business Basic and higher plans.\n\n"
            "Upgrade at relayshield.net.",
            parse_mode="Markdown",
        )
        return
    domain_limit = DOMAIN_LIMITS.get(tier, 1)
    monitored_domains = user.get("monitored_domains") or []
    if len(monitored_domains) >= domain_limit:
        send_message(
            chat_id,
            f"🌐 You've reached your domain limit ({domain_limit} domain{'s' if domain_limit > 1 else ''} "
            f"on your current plan).\n\n"
            "To monitor additional domains, upgrade at relayshield.net.",
            parse_mode="Markdown",
        )
        return
    update_user(user["user_id"], {"onboarding_state": "AWAITING_DOMAIN_ADD"})
    send_message(
        chat_id,
        f"🌐 *Enroll a Domain*\n\n"
        f"Send your business domain name (e.g. `acme.com`):\n\n"
        f"_Type_ `done` _to cancel._",
        parse_mode="Markdown",
    )


def handle_domain_status(chat_id: int, user: dict) -> None:
    """Show domain monitoring status — Business Basic+ only."""
    tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)

    if tier not in DOMAIN_TIERS:
        send_message(
            chat_id,
            "🌐 *Domain Monitoring* is available on Business Basic and higher plans.\n\n"
            "Upgrade at relayshield.net to protect your domain against lookalike/typosquat attacks.",
            parse_mode="Markdown",
        )
        return

    domains = user.get("monitored_domains") or []
    domain_limit = DOMAIN_LIMITS.get(tier, 1)

    if not domains:
        send_message(
            chat_id,
            f"🌐 *Domain Security Monitoring*\n\n"
            "No business domain enrolled yet.\n\n"
            "Domain monitoring checks for:\n"
            "• Lookalike/typosquat domains used to phish your customers\n"
            "• Email configuration (MX) changes\n"
            "• Domain expiry risk\n\n"
            f"Your plan supports up to *{domain_limit}* domain{'s' if domain_limit > 1 else ''}.\n\n"
            "Tap /domainadd to enroll your first domain.\n\n"
            "🛡️ RelayShield",
            parse_mode="Markdown",
        )
        return

    domain_state = user.get("domain_state") or {}
    lines = []
    for d in domains:
        entry = domain_state.get(d, {})
        last_scanned = entry.get("last_scanned")
        scan_label = "Never scanned" if not last_scanned else last_scanned[:10]
        lookalikes = entry.get("known_lookalikes") or []
        lookalike_line = f"⚠️ {len(lookalikes)} lookalike(s) on record" if lookalikes else "✅ No lookalikes detected"
        lines.append(f"*{d}*\n  Last scan: {scan_label}\n  {lookalike_line}")

    usage = f"{len(domains)} of {domain_limit} domain{'s' if domain_limit > 1 else ''} in use"
    send_message(
        chat_id,
        f"🌐 *Domain Security Status* — {usage}\n\n"
        + "\n\n".join(lines)
        + "\n\n🛡️ RelayShield",
        parse_mode="Markdown",
    )


def handle_reuse(chat_id: int) -> None:
    """Cross-account password reuse walkthrough."""
    send_message(
        chat_id,
        "🔑 *Cross-Account Password Reuse Check*\n\n"
        "Reusing a password across accounts means one breach exposes all of them. "
        "Work through this checklist now.\n\n"
        "*High priority — change immediately if shared with any other account:*\n"
        "• Email (Gmail, Outlook, iCloud) — your master key to everything\n"
        "• Banking and investment accounts\n"
        "• Work accounts and SSO (Okta, Google Workspace)\n"
        "• Password manager (if you use one)\n\n"
        "*Also review:*\n"
        "• Social media (Facebook, Instagram, LinkedIn, Twitter/X)\n"
        "• Crypto exchanges and wallets\n"
        "• Shopping accounts with saved payment cards\n"
        "• Any account where you receive 2FA codes\n\n"
        "*Rules for new passwords:*\n"
        "→ Unique password for every account — no reuse\n"
        "→ Minimum 16 characters; use a passphrase if easier\n"
        "→ Use a password manager (Bitwarden is free and open source)\n\n"
        "*After changing:*\n"
        "→ Revoke all active sessions on changed accounts\n"
        "→ Check /sweep to close email backdoors\n\n"
        "🛡️ RelayShield",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# Main router
# ---------------------------------------------------------------------------

def _is_valid_wallet_address(addr: str) -> bool:
    """Accept EVM (0x...), Solana (base58 32-44 chars), TON (EQ.../UQ...),
    Bitcoin P2PKH (1...), P2SH (3...), and bech32 (bc1...)."""
    if re.match(r"^0x[0-9a-fA-F]{40}$", addr):
        return True  # EVM
    if re.match(r"^[EUeu][Qq][A-Za-z0-9_\-]{46}$", addr):
        return True  # TON user-friendly (EQ.../UQ..., 48 chars)
    if re.match(r"^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$", addr):
        return True  # Bitcoin P2PKH / P2SH
    if re.match(r"^bc1[a-z0-9]{6,87}$", addr, re.IGNORECASE):
        return True  # Bitcoin bech32
    if re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", addr):
        return True  # Solana base58 (checked last — most permissive)
    return False


def _detect_chain(addr: str) -> str:
    """Detect blockchain from address format.
    Returns 'evm', 'solana', 'ton', 'bitcoin', or 'unknown'."""
    if re.match(r"^0x[0-9a-fA-F]{40}$", addr):
        return "evm"
    if re.match(r"^[EUeu][Qq][A-Za-z0-9_\-]{46}$", addr):
        return "ton"
    if re.match(r"^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$", addr) or \
       re.match(r"^bc1[a-z0-9]{6,87}$", addr, re.IGNORECASE):
        return "bitcoin"
    if re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", addr):
        return "solana"
    return "unknown"


_CHAIN_LABELS = {
    "evm":     "Ethereum/EVM",
    "solana":  "Solana",
    "ton":     "TON",
    "bitcoin": "Bitcoin",
}

# GoPlus chain IDs for address security checks
_GOPLUS_CHAIN_IDS = {
    "evm":    1,    # Ethereum mainnet default; overridden per-network when known
    "solana": 101,
}


def _goplus_risk_check(address: str, chain_id: int = 1) -> dict:
    """Query GoPlus address_security. Returns risk dict or {} on failure.
    chain_id: 1=Ethereum, 101=Solana."""
    try:
        url = f"{GOPLUS_BASE_URL}/{address}?chain_id={chain_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
            return data.get("result", {})
    except Exception as exc:
        logger.warning("GoPlus check failed for %s: %s", address, exc)
        return {}


def _chainabuse_risk(address: str) -> dict:
    """Check cross-chain scam database for community-reported activity on an address.
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


def _bitcoin_risk_check(address: str) -> dict:
    """
    Heuristic risk scoring for a Bitcoin address using Blockstream API.
    Returns dict with keys: risk_level, flags, stats, ok.
    Free — no API key required.
    """
    BLOCKSTREAM_API = "https://blockstream.info/api"
    try:
        url = f"{BLOCKSTREAM_API}/address/{address}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        logger.warning("Blockstream address check failed address=%s: %s", address, exc)
        return {"ok": False}

    chain  = data.get("chain_stats", {})
    mempool = data.get("mempool_stats", {})

    tx_count      = chain.get("tx_count", 0)
    funded_sum    = chain.get("funded_txo_sum", 0)   # total received (sats)
    spent_sum     = chain.get("spent_txo_sum", 0)    # total spent (sats)
    balance_sats  = funded_sum - spent_sum
    mempool_txs   = mempool.get("tx_count", 0)

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

    risk_level = "HIGH" if "zero_balance_high_activity" in flags or "high_tx_volume" in flags \
        else "MEDIUM" if flags else "LOW"

    return {
        "ok":         True,
        "risk_level": risk_level,
        "flags":      flags,
        "stats": {
            "tx_count":     tx_count,
            "balance_sats": balance_sats,
            "mempool_txs":  mempool_txs,
        },
    }


def _tonapi_risk(address: str) -> dict:
    """Check TONAPI v2 for TON address risk intelligence.
    Returns dict with keys: is_scam, is_sanctioned, name, interfaces, ok.
    Uses the TON community scam/sanction database natively."""
    try:
        # TON friendly addresses (EQ.../UQ...) are base64url — safe to use directly in path
        url = f"https://tonapi.io/v2/accounts/{urllib.parse.quote(address, safe='-_=')}"
        req = urllib.request.Request(
            url, headers={"User-Agent": "RelayShield/1.0", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        return {
            "ok":           True,
            "is_scam":      data.get("is_scam", False),
            "name":         data.get("name") or data.get("memo_required") or "",
            "interfaces":   data.get("interfaces", []),
            "status":       data.get("status", ""),
        }
    except Exception as exc:
        logger.warning("TONAPI risk check failed address=%s: %s", address, exc)
        return {"ok": False}


def _get_user_wallets(user_id: str, user: dict) -> list[dict]:
    """Return monitored wallets for a user, preferring the relayshield_monitored_wallets
    table (source of truth for all chains). Falls back to user record's monitored_wallets
    list for older accounts that may not have migrated."""
    try:
        from boto3.dynamodb.conditions import Attr as _Attr
        table  = dynamodb.Table(MONITORED_WALLETS_TABLE)
        items  = []
        kwargs: dict = {"FilterExpression": _Attr("user_id").eq(user_id)}
        while True:
            resp = table.scan(**kwargs)
            items.extend(resp.get("Items", []))
            last = resp.get("LastEvaluatedKey")
            if not last:
                break
            kwargs["ExclusiveStartKey"] = last
        if items:
            # Deduplicate by normalised address
            seen, deduped = set(), []
            for item in items:
                key = (item.get("wallet_address") or "").lower()
                if key and key not in seen:
                    seen.add(key)
                    # Normalise field name: table uses wallet_address, handlers expect address
                    if "address" not in item:
                        item = dict(item)
                        item["address"] = item.get("wallet_address", "")
                    deduped.append(item)
            return deduped
    except Exception as exc:
        logger.warning("_get_user_wallets table scan failed user_id=%s: %s", user_id, exc)
    # Fallback: user record embedded list
    return user.get("monitored_wallets", [])


_AAVE_V3_POOL             = "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"
_GET_USER_ACCOUNT_DATA    = "0xbf92857c"
_RAY                      = 10 ** 27


def _aave_health_factor(wallet: str) -> float | None:
    """Return Aave V3 health factor for wallet, or None if no position."""
    try:
        api_key  = get_secret(ALCHEMY_SECRET_NAME, "api_key")
        url      = f"https://eth-mainnet.g.alchemy.com/v2/{api_key}"
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


def _goplus_dapp_security(url_input: str) -> dict:
    """Query GoPlus dApp security by URL. Returns result dict or {} on failure."""
    try:
        if not url_input.startswith("http"):
            url_input = "https://" + url_input
        import urllib.parse
        api_url = "https://api.gopluslabs.io/api/v1/dapp_security?url=" + urllib.parse.quote(url_input, safe="")
        req = urllib.request.Request(api_url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        return data.get("result", {})
    except Exception as exc:
        logger.warning("dApp security check failed url=%s: %s", url_input, exc)
        return {}


def _alchemy_add_wallet(address: str) -> bool:
    """Add address to the global RelayShield Alchemy ADDRESS_ACTIVITY webhook."""
    try:
        alchemy_key = get_secret(ALCHEMY_SECRET_NAME, "signing_key").strip()
        webhook_id  = get_secret(ALCHEMY_SECRET_NAME, "webhook_id").strip()
        url  = f"{ALCHEMY_WEBHOOK_API}/update-webhook-addresses"
        body = json.dumps({
            "webhook_id":          webhook_id,
            "addresses_to_add":    [address],
            "addresses_to_remove": [],
        }).encode()
        req = urllib.request.Request(
            url, data=body, method="PATCH",
            headers={
                "Content-Type": "application/json",
                "X-Alchemy-Token": alchemy_key,
                "User-Agent": "Mozilla/5.0 (compatible; RelayShield/1.0)",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as exc:
        logger.error("Alchemy add wallet failed for %s: %s", address, exc)
        return False


def _alchemy_remove_wallet(address: str) -> bool:
    """Remove address from the global RelayShield Alchemy webhook."""
    try:
        alchemy_key = get_secret(ALCHEMY_SECRET_NAME, "signing_key").strip()
        webhook_id  = get_secret(ALCHEMY_SECRET_NAME, "webhook_id").strip()
        url  = f"{ALCHEMY_WEBHOOK_API}/update-webhook-addresses"
        body = json.dumps({
            "webhook_id":          webhook_id,
            "addresses_to_remove": [address],
        }).encode()
        req = urllib.request.Request(
            url, data=body, method="PATCH",
            headers={
                "Content-Type": "application/json",
                "X-Alchemy-Token": alchemy_key,
                "User-Agent": "Mozilla/5.0 (compatible; RelayShield/1.0)",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as exc:
        logger.error("Alchemy remove wallet failed for %s: %s", address, exc)
        return False


def _canonical_address(address: str, chain_type: str) -> str:
    """Return the canonical storage form of an address.
    EVM: lowercase hex. Solana/TON/Bitcoin: original case, stripped."""
    if chain_type == "evm":
        return address.lower()
    return address.strip()


def _store_wallet_mapping(address: str, user_id: str, chain_type: str = "evm") -> None:
    """Write wallet_address → user_id (+chain_type) to relayshield_monitored_wallets table."""
    table = dynamodb.Table(MONITORED_WALLETS_TABLE)
    table.put_item(Item={
        "wallet_address": _canonical_address(address, chain_type),
        "user_id":        user_id,
        "chain_type":     chain_type,
        "added_at":       datetime.now(timezone.utc).isoformat(),
    })


def _remove_wallet_mapping(address: str, chain_type: str = "evm") -> None:
    table = dynamodb.Table(MONITORED_WALLETS_TABLE)
    table.delete_item(Key={"wallet_address": _canonical_address(address, chain_type)})


def handle_addwallet(chat_id: int, address_raw: str | None, user: dict) -> None:
    tier = user.get("tier") or user.get("subscription_tier", "")
    if tier not in CRYPTO_TIERS:
        send_message(
            chat_id,
            "🔐 *Crypto Shield required*\n\n"
            "Wallet monitoring is available on the Crypto Shield plan ($19.99/month).\n\n"
            "Contact relayshieldadmin@gmail.com to upgrade.",
            parse_mode="Markdown",
        )
        return

    if not address_raw:
        send_message(
            chat_id,
            "Please provide the wallet address:\n\n"
            "`/addwallet 0xYourEVMAddress`\n"
            "`/addwallet YourSolanaAddress`\n"
            "`/addwallet EQYourTONAddress`",
            parse_mode="Markdown",
        )
        return

    address = address_raw.strip()
    if not _is_valid_wallet_address(address):
        send_message(
            chat_id,
            "❌ That doesn't look like a valid wallet address.\n\n"
            "Supported networks:\n"
            "• *Ethereum/EVM:* `0x` followed by 40 hex characters\n"
            "• *Solana:* base58 address (32–44 characters)\n"
            "• *TON:* starts with `EQ` or `UQ` (48 characters)\n"
            "• *Bitcoin:* starts with `1`, `3`, or `bc1`\n\n"
            "Example EVM: `/addwallet 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045`",
            parse_mode="Markdown",
        )
        return

    chain_type  = _detect_chain(address)
    chain_label = _CHAIN_LABELS.get(chain_type, chain_type.upper())
    canonical   = _canonical_address(address, chain_type)

    wallets = user.get("monitored_wallets", [])
    # Duplicate check — case-insensitive for EVM, exact for others
    already = any(
        w["address"].lower() == canonical.lower() if chain_type == "evm"
        else w["address"] == canonical
        for w in wallets
    )
    if already:
        send_message(chat_id, f"✅ `{canonical}` is already being monitored.", parse_mode="Markdown")
        return

    if len(wallets) >= WALLET_LIMIT_CRYPTO:
        send_message(
            chat_id,
            f"You've reached the wallet limit ({WALLET_LIMIT_CRYPTO} wallets on Crypto Shield).\n"
            "Remove a wallet with `/removewallet <address>` to add a new one.",
            parse_mode="Markdown",
        )
        return

    send_message(chat_id, f"🔍 Checking `{canonical}` ({chain_label})...", parse_mode="Markdown")

    # Risk check — GoPlus for EVM/Solana; Blockstream heuristics for Bitcoin; skipped for TON
    goplus_chain_id = _GOPLUS_CHAIN_IDS.get(chain_type)
    if goplus_chain_id:
        risk = _goplus_risk_check(canonical, goplus_chain_id)
        risk_flags = [k for k, v in risk.items() if v == "1"]
        risk_level = "HIGH" if len(risk_flags) >= 2 else "MEDIUM" if risk_flags else "LOW"
    elif chain_type == "bitcoin":
        btc_risk   = _bitcoin_risk_check(canonical)
        risk_flags = btc_risk.get("flags", []) if btc_risk.get("ok") else []
        risk_level = btc_risk.get("risk_level", "LOW") if btc_risk.get("ok") else "LOW"
    else:
        risk_flags = []
        risk_level = "LOW"

    # Register with Alchemy Notify — EVM only (Solana/TON/Bitcoin use polling monitors)
    if chain_type == "evm":
        alchemy_ok = _alchemy_add_wallet(canonical)
        if not alchemy_ok:
            send_message(
                chat_id,
                "⚠️ Could not register wallet with the monitoring network. "
                "Please try again in a few minutes.",
            )
            return

    # Store in DynamoDB user record + wallet mapping
    wallet_entry = {
        "address":    canonical,
        "chain_type": chain_type,
        "label":      f"Wallet {len(wallets) + 1}",
        "added_at":   datetime.now(timezone.utc).isoformat(),
        "risk_level": risk_level,
        "risk_flags": risk_flags,
    }
    wallets.append(wallet_entry)
    update_user(user["user_id"], {"monitored_wallets": wallets})
    _store_wallet_mapping(canonical, user["user_id"], chain_type)

    risk_line = ""
    if risk_flags:
        risk_line = f"\n⚠️ *Risk flags:* {risk_level} — {', '.join(risk_flags[:3])}"

    # Alert cadence note differs by chain
    if chain_type == "evm":
        alert_note = "You'll receive a Telegram alert for any transfer activity on this address."
    elif chain_type == "solana":
        alert_note = (
            "Your Solana wallet is monitored every 15 minutes. "
            "You'll receive an alert for new transaction activity."
        )
    elif chain_type == "ton":
        alert_note = (
            "Your TON wallet is monitored every 15 minutes. "
            "You'll receive an alert for new transaction activity."
        )
    elif chain_type == "bitcoin":
        alert_note = (
            "Your Bitcoin wallet is monitored every 15 minutes. "
            "You'll receive an alert with transaction direction and BTC value for any new activity."
        )
    else:
        alert_note = "Wallet stored. Activity monitoring will check periodically."

    send_message(
        chat_id,
        f"✅ *Wallet added to monitoring*\n\n"
        f"*Address:* `{canonical}`\n"
        f"*Network:* {chain_label}{risk_line}\n\n"
        f"{alert_note}\n\n"
        f"Wallets monitored: {len(wallets)}/{WALLET_LIMIT_CRYPTO}",
        parse_mode="Markdown",
    )


def handle_removewallet(chat_id: int, address_raw: str | None, user: dict) -> None:
    wallets = user.get("monitored_wallets", [])
    if not wallets:
        send_message(chat_id, "You have no wallets being monitored.")
        return

    if not address_raw:
        lines = "\n".join(
            f"• `{w['address']}` ({_CHAIN_LABELS.get(w.get('chain_type', 'evm'), 'EVM')})"
            for w in wallets
        )
        send_message(
            chat_id,
            f"Your monitored wallets:\n\n{lines}\n\n"
            "To remove one: `/removewallet <address>`",
            parse_mode="Markdown",
        )
        return

    query = address_raw.strip()
    # Case-insensitive for EVM, case-sensitive for others
    match = next(
        (w for w in wallets
         if (w.get("chain_type", "evm") == "evm" and w["address"].lower() == query.lower())
         or (w.get("chain_type", "evm") != "evm" and w["address"] == query)),
        None,
    )
    if not match:
        send_message(chat_id, f"❌ `{query}` is not in your monitored wallets.", parse_mode="Markdown")
        return

    stored_address = match["address"]
    chain_type     = match.get("chain_type", "evm")

    # Only Alchemy Notify needs a removal call for EVM wallets
    if chain_type == "evm":
        _alchemy_remove_wallet(stored_address)
    _remove_wallet_mapping(stored_address, chain_type)
    wallets = [w for w in wallets if w["address"] != stored_address]
    update_user(user["user_id"], {"monitored_wallets": wallets})
    send_message(chat_id, f"✅ `{address}` removed from monitoring.", parse_mode="Markdown")


def handle_wallets(chat_id: int, user: dict) -> None:
    tier = user.get("tier") or user.get("subscription_tier", "")
    if tier not in CRYPTO_TIERS:
        send_message(
            chat_id,
            "Wallet monitoring is available on the Crypto Shield plan.\n"
            "Contact relayshieldadmin@gmail.com to upgrade.",
        )
        return

    wallets = _get_user_wallets(user.get("user_id", ""), user)
    if not wallets:
        send_message(
            chat_id,
            "No wallets monitored yet.\n\nAdd one with:\n`/addwallet 0xYourAddress`",
            parse_mode="Markdown",
        )
        return

    lines = []
    for w in wallets:
        risk_tag    = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(w.get("risk_level", "LOW"), "⚪")
        chain_label = _CHAIN_LABELS.get(w.get("chain_type", "evm"), "EVM")
        addr        = w.get("address") or w.get("wallet_address", "")
        short       = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 12 else addr
        added       = (w.get("added_at") or "")[:10]
        lines.append(f"{risk_tag} `{addr}`\n   *Network:* {chain_label} | Added: {added}")

    send_message(
        chat_id,
        f"👛 *Monitored Wallets* ({len(wallets)}/{WALLET_LIMIT_CRYPTO})\n\n"
        + "\n\n".join(lines)
        + "\n\nTo remove: `/removewallet <address>`",
        parse_mode="Markdown",
    )


def handle_approvals(chat_id: int, user: dict) -> None:
    """
    Scan all EVM wallets for dangerous token approvals via GoPlus.
    Returns a list of unlimited/high-risk approvals with revoke.cash deep-links.
    """
    tier = user.get("subscription_tier") or user.get("tier", "")
    if tier not in CRYPTO_TIERS:
        send_message(
            chat_id,
            "🔒 *Token Approval Scanner* is a Crypto Shield feature.\n\n"
            "Upgrade at relayshield.net to monitor wallet approvals.",
        )
        return

    wallets = _get_wallets_for_user(user["user_id"])
    evm_wallets = [w for w in wallets if w.get("chain_type", "evm") == "evm"]

    if not evm_wallets:
        send_message(
            chat_id,
            "📭 *No EVM wallets found.*\n\n"
            "Add one with `/addwallet <0x...>` to scan for token approvals.",
        )
        return

    send_message(chat_id, f"🔍 *Scanning {len(evm_wallets)} EVM wallet(s) for token approvals...*")

    GOPLUS_APPROVAL_URL = "https://api.gopluslabs.io/api/v1/address_security"
    lines = ["*🔓 Token Approval Report*\n"]
    any_risk = False

    for w in evm_wallets:
        address = w.get("wallet_address", "")
        short   = f"{address[:6]}...{address[-4:]}"

        try:
            url = f"{GOPLUS_APPROVAL_URL}/{address}?chain_id=1"
            req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read()).get("result", {})

            # GoPlus flags risky approval state in address security
            approval_abuse = data.get("approval_abuse", "0")
            is_contract    = data.get("is_contract", "0")

            if approval_abuse == "1":
                any_risk = True
                revoke_link = f"https://revoke.cash/address/{address}"
                lines.append(
                    f"🚨 `{short}` — *Dangerous approvals detected*\n"
                    f"   → [Revoke on revoke.cash]({revoke_link})\n"
                    f"   → Or search your address on [Etherscan Token Approvals]"
                    f"(https://etherscan.io/tokenapprovalchecker?search={address})"
                )
            else:
                lines.append(f"✅ `{short}` — No high-risk approvals flagged")

        except Exception as exc:
            logger.warning("GoPlus approval check failed %s: %s", address, exc)
            lines.append(f"ℹ️ `{short}` — Could not retrieve approval data")

    if any_risk:
        lines.append(
            "\n*What are token approvals?*\n"
            "When you use a DeFi protocol, you grant it permission to spend your tokens. "
            "Unlimited approvals let the contract drain your wallet at any time — even after you stop using it. "
            "Revoking removes that permission without affecting your assets."
        )
        lines.append(
            "\n*To revoke manually:*\n"
            f"1. Go to [revoke.cash](https://revoke.cash)\n"
            "2. Connect your wallet\n"
            "3. Find unlimited approvals and revoke them one by one\n"
            "4. Each revoke is a small gas transaction (~$0.10–$2.00 on Ethereum)"
        )
    else:
        lines.append("\n✅ *No dangerous approvals found across your EVM wallets.*")

    send_message(chat_id, "\n".join(lines), parse_mode="Markdown")


def handle_riskcheck(chat_id: int, user: dict) -> None:
    tier = user.get("tier") or user.get("subscription_tier", "")
    if tier not in CRYPTO_TIERS:
        send_message(
            chat_id,
            "Wallet risk checks are available on the Crypto Shield plan.\n"
            "Contact relayshieldadmin@gmail.com to upgrade.",
        )
        return

    wallets = _get_user_wallets(user.get("user_id", ""), user)
    if not wallets:
        send_message(
            chat_id,
            "No wallets monitored yet. Add one with `/addwallet <address>` first.\n\n"
            "Supported: EVM (`0x...`), Solana, TON (`EQ...`/`UQ...`), Bitcoin.",
            parse_mode="Markdown",
        )
        return

    send_message(chat_id, f"🔍 Running risk check on {len(wallets)} wallet(s)...", parse_mode="Markdown")

    _malicious_fields = {
        "phishing_activities":  "linked to phishing activity",
        "blacklist_doubt":      "on security blacklists",
        "darkweb_transactions": "linked to dark web activity",
        "stealing_attack":      "linked to stealing attacks",
        "cybercrime":           "linked to cybercrime",
    }

    for wallet in wallets:
      try:
        address    = wallet.get("address") or wallet.get("wallet_address", "")
        chain_type = wallet.get("chain_type", "evm")
        chain_label = _CHAIN_LABELS.get(chain_type, chain_type.upper())
        short      = f"{address[:6]}...{address[-4:]}" if len(address) > 12 else address
        critical   = []
        warnings   = []
        info_lines = []
        logger.info("riskcheck processing — chain=%s address=%s", chain_type, address[:12])

        if chain_type in ("evm", "solana"):
            # GoPlus address-level security flags
            goplus_chain_id = _GOPLUS_CHAIN_IDS.get(chain_type, 1)
            addr_risk = _goplus_risk_check(address, goplus_chain_id)
            for field, label in _malicious_fields.items():
                if addr_risk.get(field) == "1":
                    critical.append(f"🚨 Address {label}")

        if chain_type == "evm":
            # Aave V3 health factor — EVM only
            hf = _aave_health_factor(address)
            if hf is not None:
                if hf < 1.2:
                    critical.append(f"🚨 Aave health factor: {hf:.3f} — liquidation imminent")
                elif hf < 1.5:
                    warnings.append(f"⚠️ Aave health factor: {hf:.3f} — approaching liquidation threshold")
                else:
                    info_lines.append(f"✅ Aave health factor: {hf:.3f} — safe")
            else:
                info_lines.append("ℹ️ No active Aave V3 position detected")
        elif chain_type == "solana":
            info_lines.append("ℹ️ DeFi position monitoring (Solana) — coming soon")
        elif chain_type == "ton":
            # TON — native risk intelligence via TONAPI v2
            ton_risk = _tonapi_risk(address)
            if ton_risk.get("ok"):
                if ton_risk.get("is_scam"):
                    critical.append("🚨 Flagged as scam address in TON community database")
                else:
                    info_lines.append("✅ No scam flags found in TON community database")
                ifaces = ton_risk.get("interfaces", [])
                if ifaces:
                    safe = ", ".join(f"`{i}`" for i in ifaces[:3])
                    info_lines.append(f"ℹ️ Contract type: {safe}")
                status = ton_risk.get("status", "")
                if status and status != "active":
                    warnings.append(f"⚠️ Account status: `{status}`")
            else:
                info_lines.append("ℹ️ TON risk data temporarily unavailable")
            info_lines.append("ℹ️ Wallet activity monitored via 15-minute polling")
        elif chain_type == "bitcoin":
            btc_risk = _bitcoin_risk_check(address)
            if btc_risk.get("ok"):
                stats = btc_risk.get("stats", {})
                btc_flags = btc_risk.get("flags", [])
                FLAG_LABELS = {
                    "never_used":               "⚠️ Address has never been used — verify this is the correct address",
                    "high_tx_volume":           "⚠️ High transaction volume — may be an exchange or mixing service",
                    "zero_balance_high_activity": "🚨 Zero balance with high activity — potential tumbler or mixer",
                    "dust_balance":             "⚠️ Dust balance detected — possible dust attack",
                    "unconfirmed_transactions": "ℹ️ Unconfirmed transactions pending in mempool",
                }
                for flag in btc_flags:
                    label = FLAG_LABELS.get(flag)
                    if label:
                        if label.startswith("🚨"):
                            critical.append(label)
                        elif label.startswith("⚠️"):
                            warnings.append(label)
                        else:
                            info_lines.append(label)
                balance_btc = stats.get("balance_sats", 0) / 100_000_000
                info_lines.append(f"ℹ️ Balance: {balance_btc:.8f}".rstrip("0").rstrip(".") + " BTC")
                info_lines.append(f"ℹ️ Total transactions: {stats.get('tx_count', 0)}")
                if not btc_flags:
                    info_lines.append("✅ No risk flags detected on this Bitcoin address")
            else:
                info_lines.append("ℹ️ Bitcoin risk data temporarily unavailable")
            info_lines.append("ℹ️ Wallet activity monitored via 15-minute polling")

        if critical:
            risk_badge = "🔴 *CRITICAL*"
        elif warnings:
            risk_badge = "🟡 *MEDIUM RISK*"
        else:
            risk_badge = "🟢 *LOW RISK*"

        lines = [
            f"🛡 *Wallet Risk Check*\n",
            f"*Address:* `{short}`",
            f"*Network:* {chain_label}",
            f"*Risk Level:* {risk_badge}\n",
        ]
        lines.extend(critical)
        lines.extend(warnings)
        lines.extend(info_lines)
        if not critical and not warnings:
            lines.append("✅ No active risk flags on this wallet.")
        lines.append("\n_RelayShield Crypto Shield_")

        send_message(chat_id, "\n".join(lines), parse_mode="Markdown")
        logger.info("riskcheck — chat_id=%s address=%s chain=%s", chat_id, address, chain_type)
      except Exception as exc:
        logger.error("riskcheck wallet error — chain=%s address=%s: %s", chain_type, address[:12] if address else "?", exc)
        send_message(chat_id, f"⚠️ Risk check error for {chain_type.upper()} wallet — please try again.")


def handle_checkvault(chat_id: int, url_raw: str | None, user: dict) -> None:
    tier = user.get("tier") or user.get("subscription_tier", "")
    if tier not in CRYPTO_TIERS:
        send_message(
            chat_id,
            "Vault risk checks are available on the Crypto Shield plan.\n"
            "Contact relayshieldadmin@gmail.com to upgrade.",
        )
        return

    if not url_raw:
        send_message(
            chat_id,
            "Please provide the DeFi protocol URL:\n\n"
            "`/checkvault app.aave.com`\n"
            "`/checkvault app.uniswap.org`\n"
            "`/checkvault curve.fi`",
            parse_mode="Markdown",
        )
        return

    send_message(chat_id, f"🔍 Checking vault: `{url_raw}`...", parse_mode="Markdown")

    info = _goplus_dapp_security(url_raw)
    if not info:
        send_message(
            chat_id,
            "⚠️ No security data found for that URL.\n"
            "Only major DeFi protocols with tracked contracts are supported.",
        )
        return

    project   = info.get("project_name", url_raw)
    is_audit  = info.get("is_audit", 0)
    trust     = info.get("trust_list", 0)
    audits    = info.get("audit_info", [])
    contracts = []
    for chain in info.get("contracts_security", []):
        contracts.extend(chain.get("contracts", []))

    critical = []
    warnings = []
    good     = []

    malicious_contracts = [c for c in contracts if c.get("malicious_contract") == 1]
    malicious_creators  = [c for c in contracts if c.get("malicious_creator") == 1]
    unverified          = [c for c in contracts if c.get("is_open_source") == 0]

    if malicious_contracts:
        critical.append(f"🚨 {len(malicious_contracts)} malicious contract(s) detected")
    if malicious_creators:
        critical.append(f"🚨 {len(malicious_creators)} contract(s) deployed by a malicious creator")
    if not is_audit:
        warnings.append("⚠️ No security audit on record — unaudited protocol")
    if unverified:
        warnings.append(f"⚠️ {len(unverified)} unverified (closed-source) contract(s)")

    if is_audit and audits:
        firms = ", ".join(a.get("audit_firm", "") for a in audits if a.get("audit_firm"))
        good.append(f"✅ Audited by: {firms}")
    if trust:
        good.append("✅ On verified protocol trust list")
    if not critical and not warnings:
        good.append("✅ No contract risk flags detected")

    if critical:
        risk_badge = "🔴 *CRITICAL RISK*"
    elif warnings:
        risk_badge = "🟡 *MEDIUM RISK*"
    else:
        risk_badge = "🟢 *LOW RISK*"

    lines = [
        "🏦 *Vault / Protocol Risk Check*\n",
        f"*Protocol:* {project}",
        f"*Risk Level:* {risk_badge}\n",
    ]
    lines.extend(critical)
    lines.extend(warnings)
    lines.extend(good)
    lines.append("\n_RelayShield Crypto Shield_")

    send_message(chat_id, "\n".join(lines), parse_mode="Markdown")
    logger.info("checkvault — chat_id=%s url=%s", chat_id, url_raw)


def _goplus_token_security(address: str, chain_id: int = 1) -> dict:
    try:
        url = f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}?contract_addresses={address.lower()}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        return data.get("result", {}).get(address.lower(), {})
    except Exception as exc:
        logger.error("Token security check failed addr=%s: %s", address, exc)
        return {}


def _goplus_nft_security(address: str, chain_id: int = 1) -> dict:
    try:
        url = f"https://api.gopluslabs.io/api/v1/nft_security/{chain_id}?contract_addresses={address.lower()}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        # NFT security API returns result as a flat object, not keyed by address
        return data.get("result", {})
    except Exception as exc:
        logger.error("NFT security check failed addr=%s: %s", address, exc)
        return {}


def _format_token_risk(address: str, info: dict) -> str:
    short  = f"{address[:6]}...{address[-4:]}"
    name   = info.get("token_name", "Unknown Token")
    symbol = info.get("token_symbol", "?")

    critical_flags = []
    warning_flags  = []

    if info.get("is_honeypot") == "1":
        critical_flags.append("🚨 Honeypot — you cannot sell this token")
    if info.get("cannot_sell_all") == "1":
        critical_flags.append("🚨 Cannot sell all tokens — honeypot variant")
    if info.get("owner_change_balance") == "1":
        critical_flags.append("🚨 Owner can change any holder's balance")
    if info.get("selfdestruct") == "1":
        critical_flags.append("🚨 Contract can self-destruct, destroying all funds")
    buy_tax  = float(info.get("buy_tax")  or 0)
    sell_tax = float(info.get("sell_tax") or 0)
    if sell_tax >= 0.5:
        critical_flags.append(f"🚨 Sell tax: {sell_tax*100:.0f}% — effectively unsellable")
    elif sell_tax >= 0.1:
        warning_flags.append(f"⚠️ Sell tax: {sell_tax*100:.0f}% — verify before buying")
    if buy_tax >= 0.1:
        warning_flags.append(f"⚠️ Buy tax: {buy_tax*100:.0f}%")
    if info.get("is_mintable") == "1":
        warning_flags.append("⚠️ Mintable — owner can create unlimited supply, diluting your holdings")
    if info.get("hidden_owner") == "1":
        warning_flags.append("⚠️ Hidden owner — true controller is not publicly visible")
    if info.get("can_take_back_ownership") == "1":
        warning_flags.append("⚠️ Ownership can be silently reclaimed after appearing renounced")
    if info.get("transfer_pausable") == "1":
        warning_flags.append("⚠️ Transfers can be paused — owner can freeze your funds")
    if info.get("is_open_source") == "0":
        warning_flags.append("⚠️ Contract not open source — code is unverifiable")
    if info.get("is_proxy") == "1":
        warning_flags.append(
            "⚠️ Proxy contract — logic can be upgraded by the owner. "
            "Only hold if issued by a verified, reputable team."
        )
    if info.get("is_blacklisted") == "1":
        warning_flags.append("⚠️ Blacklist function — owner can block any wallet from selling")

    if critical_flags:
        risk_badge = "🔴 *CRITICAL RISK*"
    elif len(warning_flags) >= 3:
        risk_badge = "🟡 *HIGH RISK*"
    elif warning_flags:
        risk_badge = "🟡 *MEDIUM RISK*"
    else:
        risk_badge = "🟢 *LOW RISK*"

    lines = [
        "🔍 *Token Risk Check*\n",
        f"*Token:* {name} ({symbol})",
        f"*Address:* `{short}`",
        f"*Risk Level:* {risk_badge}\n",
    ]
    if critical_flags:
        lines.append("\n".join(critical_flags))
    if warning_flags:
        lines.append("\n".join(warning_flags))
    if not critical_flags and not warning_flags:
        lines.append("✅ No major risk flags detected.")
    lines.append("\n_RelayShield Crypto Shield_")
    return "\n".join(lines)


def _format_nft_risk(address: str, info: dict) -> str:
    short = f"{address[:6]}...{address[-4:]}"
    name  = info.get("nft_name", info.get("nft_symbol", "Unknown Collection"))

    critical_flags = []
    warning_flags  = []

    # Integer fields (0/1)
    if info.get("malicious_nft_contract") == 1:
        critical_flags.append("🚨 Known malicious contract")
    if info.get("nft_open_source") == 0:
        warning_flags.append("⚠️ Contract not open source — code is unverifiable")
    if info.get("nft_proxy") == 1:
        warning_flags.append(
            "⚠️ Proxy contract — logic can be upgraded by the owner. "
            "Only hold if issued by a verified, reputable team."
        )
    if info.get("restricted_approval") == 1:
        warning_flags.append("⚠️ Approval restricted — transferability may be limited")

    # Object fields — value 1 = risky, 0 = safe, -1 = blackhole (owner burned = safe)
    if (info.get("privileged_burn") or {}).get("value") == 1:
        warning_flags.append("⚠️ Owner can burn your NFTs without your consent")
    if (info.get("privileged_minting") or {}).get("value") == 1:
        warning_flags.append("⚠️ Owner can mint unlimited NFTs, diluting collection value")
    if (info.get("transfer_without_approval") or {}).get("value") == 1:
        critical_flags.append("🚨 Owner can transfer your NFTs without your approval")

    if critical_flags:
        risk_badge = "🔴 *CRITICAL RISK*"
    elif len(warning_flags) >= 3:
        risk_badge = "🟡 *HIGH RISK*"
    elif warning_flags:
        risk_badge = "🟡 *MEDIUM RISK*"
    else:
        risk_badge = "🟢 *LOW RISK*"

    lines = [
        "🖼 *NFT Collection Risk Check*\n",
        f"*Collection:* {name}",
        f"*Address:* `{short}`",
        f"*Risk Level:* {risk_badge}\n",
    ]
    if critical_flags:
        lines.append("\n".join(critical_flags))
    if warning_flags:
        lines.append("\n".join(warning_flags))
    if not critical_flags and not warning_flags:
        lines.append("✅ No major risk flags detected.")
    lines.append("\n_RelayShield Crypto Shield_")
    return "\n".join(lines)


def handle_checktoken(chat_id: int, address_raw: str | None, user: dict) -> None:
    tier = user.get("tier") or user.get("subscription_tier", "")
    if tier not in CRYPTO_TIERS:
        send_message(
            chat_id,
            "Token risk checks are available on the Crypto Shield plan.\n"
            "Contact relayshieldadmin@gmail.com to upgrade.",
        )
        return

    if not address_raw or not address_raw.startswith("0x") or len(address_raw) < 10:
        send_message(
            chat_id,
            "Please provide a token contract address:\n\n"
            "`/checktoken 0xTokenContractAddress`",
            parse_mode="Markdown",
        )
        return

    address = address_raw.strip().lower()
    send_message(chat_id, f"🔍 Checking token `{address[:6]}...{address[-4:]}`...", parse_mode="Markdown")

    info = _goplus_token_security(address)
    if not info:
        send_message(
            chat_id,
            "⚠️ No data found for this contract address.\n"
            "It may not be on Ethereum mainnet, or it may be too new to have security data.",
        )
        return

    send_message(chat_id, _format_token_risk(address, info), parse_mode="Markdown")
    logger.info("checktoken — chat_id=%s address=%s", chat_id, address)


def handle_checknft(chat_id: int, address_raw: str | None, user: dict) -> None:
    tier = user.get("tier") or user.get("subscription_tier", "")
    if tier not in CRYPTO_TIERS:
        send_message(
            chat_id,
            "NFT risk checks are available on the Crypto Shield plan.\n"
            "Contact relayshieldadmin@gmail.com to upgrade.",
        )
        return

    if not address_raw or not address_raw.startswith("0x") or len(address_raw) < 10:
        send_message(
            chat_id,
            "Please provide an NFT contract address:\n\n"
            "`/checknft 0xNFTContractAddress`",
            parse_mode="Markdown",
        )
        return

    address = address_raw.strip().lower()
    send_message(chat_id, f"🔍 Checking NFT collection `{address[:6]}...{address[-4:]}`...", parse_mode="Markdown")

    info = _goplus_nft_security(address)
    if not info:
        send_message(
            chat_id,
            "⚠️ No data found for this contract address.\n"
            "It may not be on Ethereum mainnet, or it may be too new to have security data.",
        )
        return

    send_message(chat_id, _format_nft_risk(address, info), parse_mode="Markdown")
    logger.info("checknft — chat_id=%s address=%s", chat_id, address)


def route_active_command(chat_id: int, text: str, user: dict) -> None:
    """Route commands from ACTIVE users."""
    cmd = text.strip().lower().lstrip("/")

    if cmd == "help":
        handle_help(chat_id, user)
    elif cmd == "verify":
        handle_verify(chat_id)
    elif cmd == "otp":
        handle_otp(chat_id, user)
    elif cmd == "sweep":
        handle_sweep(chat_id)
    elif cmd == "sim":
        handle_sim_status(chat_id, user)
    elif cmd == "breach":
        handle_breach_status(chat_id, user)
    elif cmd == "domainadd":
        handle_domainadd_prompt(chat_id, user)
    elif cmd.startswith("domain"):
        parts = text.strip().split(None, 2)
        # /domain add <domainname> — power-user shorthand still works
        if len(parts) >= 3 and parts[1].lower() == "add":
            handle_domain_add(chat_id, parts[2], user)
        elif len(parts) == 2 and parts[1].lower() != "add":
            handle_domain_add(chat_id, parts[1], user)
        else:
            handle_domain_status(chat_id, user)
    elif cmd == "reuse":
        handle_reuse(chat_id)
    elif cmd == "phone":
        handle_phone_hardening(chat_id)
    elif cmd == "vishing":
        handle_vishing(chat_id)
    elif cmd in ("wascam", "scam"):
        handle_wascam(chat_id)
    elif cmd == "tgsecurity":
        handle_tgsecurity(chat_id)
    elif cmd.startswith("botcheck"):
        # /botcheck          → general guidance
        # /botcheck @somebot → typosquat + red flag analysis
        parts = text.strip().split(None, 1)
        username = parts[1].lstrip("@") if len(parts) > 1 else None
        handle_botcheck(chat_id, username)
    elif cmd in ("verifybot", "legit", "relayshield"):
        handle_verify_bot(chat_id)
    elif cmd.startswith("scan"):
        parts = text.strip().split(None, 1)
        target = parts[1] if len(parts) > 1 else None
        handle_scan(chat_id, target, user)
    elif cmd.startswith("analyze") or cmd.startswith("analyse"):
        parts = text.strip().split(None, 1)
        content = parts[1] if len(parts) > 1 else None
        handle_analyze(chat_id, content)
    elif cmd == "sessions":
        handle_sessions(chat_id)
    elif cmd in ("status", "account"):
        handle_status(chat_id, user)
    elif cmd == "addmember":
        handle_addmember(chat_id, user)
    elif cmd == "removemember":
        handle_removemember(chat_id, user)
    elif cmd == "riskcheck":
        handle_riskcheck(chat_id, user)
    elif cmd == "approvals":
        handle_approvals(chat_id, user)
    elif cmd.startswith("checkvault"):
        arg = text.split(maxsplit=1)[1].strip() if len(text.split()) > 1 else None
        handle_checkvault(chat_id, arg, user)
    elif cmd.startswith("checktoken"):
        address = text.split(maxsplit=1)[1].strip() if len(text.split()) > 1 else None
        handle_checktoken(chat_id, address, user)
    elif cmd.startswith("checknft"):
        address = text.split(maxsplit=1)[1].strip() if len(text.split()) > 1 else None
        handle_checknft(chat_id, address, user)
    elif cmd.startswith("addwallet"):
        parts = text.strip().split(None, 1)
        address = parts[1] if len(parts) > 1 else None
        handle_addwallet(chat_id, address, user)
    elif cmd.startswith("removewallet"):
        parts = text.strip().split(None, 1)
        address = parts[1] if len(parts) > 1 else None
        handle_removewallet(chat_id, address, user)
    elif cmd == "wallets":
        handle_wallets(chat_id, user)
    elif cmd == "extensions":
        handle_extensions(chat_id)
    else:
        send_message(
            chat_id,
            "I didn't recognise that command. Type /help to see all available commands.",
        )


def handle_message(update: dict) -> None:
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "").strip()
    contact = message.get("contact")
    first_name = message.get("from", {}).get("first_name", "there")

    if not chat_id:
        return

    # --- Photo + /analyze caption → Rekognition OCR + fraud analysis ---
    # User sends a screenshot of a suspicious email/message with caption /analyze
    photo = message.get("photo")
    caption = message.get("caption", "").strip()
    if photo and caption.lower().lstrip("/") in ("analyze", "analyse"):
        send_message(
            chat_id,
            "📧 *Scanning your screenshot...* This may take a few seconds.",
        )
        image_bytes = download_telegram_photo(photo)
        extracted_text = run_textract_ocr(image_bytes) if image_bytes else None
        if extracted_text:
            handle_analyze(chat_id, extracted_text)
        else:
            send_message(
                chat_id,
                "⚠️ *Could not read text from that image.*\n\n"
                "Try a clearer screenshot, or paste the text directly:\n"
                "`/analyze <paste message text here>`",
                parse_mode="Markdown",
            )
        return

    # Handle contact share (phone number)
    if contact:
        user = get_user_by_chat_id(chat_id)
        if user and user.get("onboarding_state") == "AWAITING_PHONE":
            handle_phone_contact(chat_id, contact.get("phone_number", ""), user)
        return

    # Handle 6-digit WA linking code
    if re.match(r"^\d{6}$", text):
        user = get_user_by_chat_id(chat_id)
        if not user:
            handle_link_code(chat_id, text, first_name)
            return

    # Handle 8-character team invite code (alphanumeric, at least one letter)
    if re.match(r"^[A-Z0-9]{8}$", text) and not re.match(r"^\d{8}$", text):
        existing = get_user_by_chat_id(chat_id)
        if not existing:
            admin = find_invite_code(text)
            if admin:
                expiry_str = admin.get("pending_invite_expiry", "")
                if expiry_str and datetime.fromisoformat(expiry_str) > datetime.now(timezone.utc):
                    # Valid invite — create member record and begin onboarding
                    tier = admin.get("tier") or admin.get("subscription_tier", TIER_PERSONAL)
                    member = create_telegram_user(chat_id, tier, first_name)
                    update_user(member["user_id"], {
                        "team_id": admin["user_id"],
                        "is_team_admin": False,
                    })
                    # Clear the used invite code
                    update_user(admin["user_id"], {
                        "pending_invite_code": None,
                        "pending_invite_expiry": None,
                    })
                    # Notify admin
                    admin_chat_id = admin.get("telegram_chat_id")
                    if admin_chat_id:
                        send_message(
                            int(admin_chat_id),
                            f"✅ *New team member joined:* {first_name}\n\n"
                            "They are now completing their security setup.",
                            parse_mode="Markdown",
                        )
                    request_contact(
                        chat_id,
                        f"✅ *Welcome to RelayShield, {first_name}!*\n\n"
                        "You've been added to your team's account.\n\n"
                        "Let's set up your personal protection. Please share your phone number to enable SIM swap monitoring:",
                    )
                    return
                else:
                    send_message(chat_id, "⏱️ That invite code has expired. Ask your admin to generate a new one with /addmember.")
                    return
            # Not an invite code — fall through to normal routing

    # Handle /start
    if text.lower() in ("/start", "/start@relayshield_bot"):
        handle_start(chat_id, first_name)
        return

    # Handle /myid — works at any onboarding state, no user record needed
    if text.lower().lstrip("/") == "myid":
        handle_myid(chat_id)
        return

    # Existing user routing
    user = get_user_by_chat_id(chat_id)
    if not user:
        send_message(
            chat_id,
            "Welcome to RelayShield! Type /start to begin.",
        )
        return

    # Persist first_name if not already stored (Stripe-initiated users skip /start)
    if first_name and first_name != "there" and not user.get("first_name"):
        update_user(user["user_id"], {"first_name": first_name})
        user["first_name"] = first_name

    state = user.get("onboarding_state", "ACTIVE")

    if state == "AWAITING_PHONE":
        # Accept typed phone number (e.g. +1 555 123 4567)
        digits = re.sub(r"[\s\-\(\)]", "", text)
        if re.match(r"^\+?[\d]{7,15}$", digits):
            phone = digits if digits.startswith("+") else "+" + digits
            handle_phone_contact(chat_id, phone, user)
        else:
            send_message(
                chat_id,
                "Please type your mobile phone number to enable SIM swap monitoring.\n\n"
                "Example: `+1 555 123 4567`",
                parse_mode="Markdown",
            )
    elif state == "AWAITING_EMAIL_1":
        handle_email_input(chat_id, text, user)
    elif state == "AWAITING_MORE_EMAILS":
        handle_email_input(chat_id, text, user)
    elif state in ("AWAITING_REMOVE_SELECT", "AWAITING_DOMAIN_ADD", "AWAITING_BREACH_EMAIL") and text.startswith("/"):
        # Slash command received mid-flow — cancel current operation and route normally
        update_user(user["user_id"], {
            "onboarding_state": "ACTIVE",
            "pending_remove_list": None,
        })
        user["onboarding_state"] = "ACTIVE"
        send_message(
            chat_id,
            "↩️ Previous operation cancelled.",
        )
        route_active_command(chat_id, text, user)
    elif state == "AWAITING_REMOVE_SELECT":
        if text.strip().lower() == "cancel":
            update_user(user["user_id"], {"onboarding_state": "ACTIVE"})
            send_message(chat_id, "Cancelled. No members were removed.")
        elif text.strip().isdigit():
            idx = int(text.strip()) - 1
            member_ids = user.get("pending_remove_list", [])
            if 0 <= idx < len(member_ids):
                member_id = member_ids[idx]
                # Deactivate member record
                table = dynamodb.Table(USERS_TABLE)
                resp = table.get_item(Key={"user_id": member_id})
                member = resp.get("Item", {})
                update_user(member_id, {"active": False, "team_id": None})
                # Notify removed member via Telegram if linked
                member_chat_id = member.get("telegram_chat_id")
                member_name = member.get("first_name", "Team member")
                if member_chat_id:
                    send_message(
                        int(member_chat_id),
                        "🔔 *RelayShield Account Update*\n\n"
                        "You have been removed from your team's RelayShield account by the admin.\n\n"
                        "Your monitoring has been deactivated. Contact your admin or visit relayshield.net to set up an individual account.",
                        parse_mode="Markdown",
                    )
                update_user(user["user_id"], {
                    "onboarding_state": "ACTIVE",
                    "pending_remove_list": None,
                })
                send_message(
                    chat_id,
                    f"✅ *{member_name}* has been removed from your team and notified.\n\n"
                    "Use /status to see your updated seat usage.",
                    parse_mode="Markdown",
                )
            else:
                send_message(chat_id, "Invalid selection. Please reply with a number from the list, or type `cancel`:")
        else:
            send_message(chat_id, "Please reply with a number from the list, or type `cancel`:")
    elif state == "AWAITING_BREACH_EMAIL":
        if text.strip().lower() == "cancel":
            update_user(user["user_id"], {"onboarding_state": "ACTIVE"})
            send_message(chat_id, "Cancelled. Type /breach any time to check your monitoring status.")
        else:
            email = text.strip().lower()
            if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
                send_message(chat_id, "That doesn't look like a valid email address. Please try again or type `cancel`:", parse_mode="Markdown")
            else:
                tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)
                limit = EMAIL_LIMITS.get(tier, 3)
                monitored = user.get("monitored_emails", [])
                email_hash = hash_email(email)
                if email_hash in [hash_email(e) for e in monitored]:
                    send_message(chat_id, f"`{email}` is already being monitored.", parse_mode="Markdown")
                    update_user(user["user_id"], {"onboarding_state": "ACTIVE"})
                elif len(monitored) >= limit:
                    send_message(chat_id, f"You've reached your email limit ({limit} on your plan). Contact relayshieldadmin@gmail.com to upgrade.")
                    update_user(user["user_id"], {"onboarding_state": "ACTIVE"})
                else:
                    monitored.append(email)
                    me_table = dynamodb.Table(MONITORED_EMAILS_TABLE)
                    email_enc = encrypt_field(email)
                    me_table.put_item(Item={
                        "email_id": str(uuid.uuid4()),
                        "user_id": user["user_id"],
                        "email_encrypted": email_enc,
                        "email_hash": email_hash,
                        "tier": tier,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "active": True,
                    })
                    update_user(user["user_id"], {
                        "monitored_emails": monitored,
                        "onboarding_state": "ACTIVE",
                    })
                    remaining = limit - len(monitored)
                    send_message(
                        chat_id,
                        f"✅ *{email}* enrolled for breach monitoring.\n\n"
                        f"{len(monitored)} of {limit} email slot{'s' if limit > 1 else ''} used.\n\n"
                        f"{'You can add ' + str(remaining) + ' more. Use /breach to add another.' if remaining > 0 else 'You have reached your email limit.'}\n\n"
                        "🛡️ RelayShield",
                        parse_mode="Markdown",
                    )
    elif state == "AWAITING_DOMAIN_ADD":
        if text.strip().lower() == "done":
            update_user(user["user_id"], {"onboarding_state": "ACTIVE"})
            send_message(chat_id, "✅ Done. Type /domain to see your enrolled domains.")
        else:
            # Validate and add the domain
            tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)
            domain_limit = DOMAIN_LIMITS.get(tier, 1)
            monitored_domains = user.get("monitored_domains") or []
            handle_domain_add(chat_id, text, user)
            # If limit now reached, return to ACTIVE; otherwise stay in AWAITING_DOMAIN_ADD
            updated_user = get_user_by_chat_id(chat_id)
            updated_domains = (updated_user or {}).get("monitored_domains") or []
            if len(updated_domains) >= domain_limit:
                update_user(user["user_id"], {"onboarding_state": "ACTIVE"})
    elif state == "AWAITING_DOMAIN":
        if text.strip().lower() == "done":
            # User skipped remaining domain slots — complete onboarding
            emails = user.get("monitored_emails", [])
            first_name = user.get("first_name", "there")
            tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)
            update_user(user["user_id"], {"onboarding_state": "ACTIVE"})
            send_message(chat_id, msg_onboarding_complete(first_name, len(emails), tier))
        else:
            handle_domain_input(chat_id, text, user)
    elif state == "ACTIVE":
        route_active_command(chat_id, text, user)
    else:
        send_message(chat_id, "Type /start to begin your setup.")


def handle_callback_query(update: dict) -> None:
    cq = update.get("callback_query", {})
    cq_id = cq.get("id", "")
    data = cq.get("data", "")
    chat_id = cq.get("message", {}).get("chat", {}).get("id")
    first_name = cq.get("from", {}).get("first_name", "there")

    if not chat_id:
        return

    user = get_user_by_chat_id(chat_id)

    # Persist first_name if not already stored (Stripe-initiated users skip /start)
    if user and first_name and first_name != "there" and not user.get("first_name"):
        update_user(user["user_id"], {"first_name": first_name})
        user["first_name"] = first_name

    if data.startswith("intent_"):
        intent = data.replace("intent_", "")
        handle_intent_callback(chat_id, intent, cq_id, first_name)

    elif data.startswith("planinfo_"):
        # Tap on plan button → show feature card
        tier = data.replace("planinfo_", "")
        # Determine intent from context (default personal for routing back)
        intent = "personal" if tier in (TIER_PERSONAL, TIER_STARTER, TIER_STARTER_DOMAIN) else "business"
        handle_planinfo_callback(chat_id, tier, cq_id, intent)

    elif data.startswith("back_plans_"):
        # Back button from feature card → re-show plan keyboard
        answer_callback(cq_id)
        intent = data.replace("back_plans_", "")
        if intent == "personal":
            send_message(chat_id, "Tap a plan to see what's included:", reply_markup=personal_plan_keyboard())
        else:
            send_message(chat_id, "Tap a plan to see what's included:", reply_markup=business_plan_keyboard())

    elif data.startswith("plan_"):
        tier = data.replace("plan_", "")
        handle_plan_callback(chat_id, tier, cq_id, first_name)

    elif data == "phone_confirm_yes" and user:
        answer_callback(cq_id)
        handle_phone_confirm(chat_id, True, user)

    elif data == "phone_confirm_no" and user:
        answer_callback(cq_id)
        handle_phone_confirm(chat_id, False, user)

    elif data == "emails_done" and user:
        answer_callback(cq_id)
        emails = user.get("monitored_emails", [])
        if not emails:
            send_message(chat_id, "Please add at least one email address to monitor:")
        else:
            _complete_onboarding(chat_id, user, emails)

    else:
        answer_callback(cq_id)


def handle_successful_payment(update: dict) -> None:
    """
    Telegram Payments 2.0 — successful_payment update.
    TODO Phase 2: Map payment amount to tier, create user record,
    begin onboarding (request_contact).
    """
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    first_name = message.get("from", {}).get("first_name", "there")
    payment = message.get("successful_payment", {})
    amount = payment.get("total_amount", 0)

    logger.info("Successful payment: chat_id=%s amount=%s", chat_id, amount)

    # Map payment amount to tier
    tier_map = {v["amount"]: k for k, v in PLAN_PRICES.items()}
    tier = tier_map.get(amount, TIER_PERSONAL)

    # Create user record
    user = create_telegram_user(chat_id, tier, first_name)

    # Begin onboarding — request phone
    request_contact(
        chat_id,
        f"✅ Payment confirmed! Welcome to RelayShield.\n\n"
        f"To enable SIM swap monitoring, please share your phone number:",
    )


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def handle_inbound_signal(body: dict) -> str:
    """
    Internal signal injection path — called by external monitors (SIM swap,
    breach, domain) via Lambda invoke after they have already recorded the
    signal in DynamoDB.

    The monitor has already called record_signal() — this function reads the
    current recent_signals from DynamoDB and runs Telegram-specific predictive
    warnings and correlation checks WITHOUT recording the signal again.

    Expected body shape:
        {
            "source":           "relayshield_internal",
            "user_id":          "<DynamoDB user_id>",
            "signal_type":      "sim_swap" | "breach_alert" | "domain_lookalike" | ...,
            "telegram_chat_id": <int>   # must be supplied by the monitor
        }
    """
    user_id     = body.get("user_id")
    signal_type = body.get("signal_type")
    chat_id     = body.get("telegram_chat_id")

    if not user_id or not signal_type:
        logger.warning("handle_inbound_signal: missing user_id or signal_type — %s", body)
        return "bad_signal_payload"

    if not chat_id:
        logger.info("handle_inbound_signal: no telegram_chat_id — skipping TG delivery user_id=%s", user_id)
        return "no_chat_id"

    # Read signals already written by the monitor — do NOT record again
    table   = dynamodb.Table(USERS_TABLE)
    now     = datetime.now(timezone.utc)
    cutoff  = (now - timedelta(hours=CORRELATION_WINDOW_HOURS)).isoformat()
    signals = [
        s for s in
        table.get_item(Key={"user_id": user_id}).get("Item", {}).get("recent_signals", [])
        if isinstance(s, dict) and s.get("ts", "") > cutoff
    ]

    chat_id = int(chat_id)

    # Infostealer awareness — send on every breach alert
    if signal_type == "breach_alert":
        send_message(chat_id, (
            "🦠 *Infostealer malware risk*\n\n"
            "Credential breaches are actively used to distribute infostealers — malware "
            "hidden in malicious browser extensions, cracked software, and fake AI tools "
            "that silently harvests passwords, session cookies, and crypto wallet keys.\n\n"
            "→ Check your browser extensions — remove any you don't recognise\n"
            "→ Never install software from unofficial sources, cracked apps, or links in Discord/Telegram\n"
            "→ If your device behaves unusually, run a malware scan *before* changing passwords — "
            "changing passwords on a compromised device hands attackers your new credentials immediately\n\n"
            "Reply */extensions* for a step\\-by\\-step browser extension audit guide\\.\n\n"
            "_RelayShield_"
        ))

    check_and_warn_predictive(user_id, signal_type, signals, chat_id)
    check_and_fire_correlation(user_id, signals, chat_id)
    logger.info("Inbound signal handled — user_id=%s type=%s chat_id=%s", user_id, signal_type, chat_id)
    return "signal_handled"


def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))
        logger.info("Telegram update: %s", json.dumps(body)[:500])

        # Internal signal injection from monitors (SIM swap, breach, domain)
        if body.get("source") == "relayshield_internal":
            result = handle_inbound_signal(body)
            return {"statusCode": 200, "body": result}

        if "message" in body:
            msg = body["message"]
            if "successful_payment" in msg:
                handle_successful_payment(body)
            else:
                handle_message(body)
        elif "callback_query" in body:
            handle_callback_query(body)
        else:
            logger.info("Unhandled update type: %s", list(body.keys()))

    except Exception as e:
        logger.exception("Unhandled error: %s", e)

    # Always return 200 to Telegram — otherwise it retries endlessly
    return {"statusCode": 200, "body": "ok"}
