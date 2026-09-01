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
  /scan — check a link, message or screenshot. One entry point for all three:
         paste a URL, paste/forward a suspicious email or SMS, or send a
         screenshot. (hidden aliases, still working: /msgscan /analyze /analyse)
  /infostealer <email> — check if email was harvested by infostealer malware
  /addwallet <addr> — add EVM, Solana, or TON wallet to monitoring (Crypto Shield only)
  /removewallet <addr> — remove wallet from monitoring
  /wallets  — list monitored wallets with GoPlus risk scores
  /teamstatus — per-seat security health summary (Business admin only)
  /setdomain  — set shared company domain for team-wide lookalike monitoring (Business admin only)
  LINK      — link existing WhatsApp account via 6-digit code
"""

import base64
import hashlib
import json
import secrets
import logging
import os
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
lambda_client = boto3.client("lambda")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

KMS_KEY_ALIAS = "alias/relayshield-data-key"
PHONE_HASH_INDEX = "phone_hash-index"

import relayshield_sim_swap_consent as simswap_consent
# Shared with relayshield_whatsapp_webhook.py. Provenance analysis for
# forwarded messages plus the Quickstart card. The CONTENT analysis stays in
# handle_analyze below -- see that module's docstring for why the split is
# drawn there, and for why the sender lookup runs on Telegram and cannot run
# on WhatsApp.
import relayshield_forward_analysis as fwd

USERS_TABLE             = "relayshield_users"
MONITORED_EMAILS_TABLE  = "relayshield_monitored_emails"
BREACH_ALERTS_TABLE     = "relayshield_breach_alerts"
MONITORED_WALLETS_TABLE = "relayshield_monitored_wallets"

TIER_FREE            = "free"
HIBP_SECRET_NAME     = "relayshield/hibp_api_key"
HIBP_SECRET_KEY      = "HIBP_API_KEY"
CRYPTO_MONTHLY_URL   = "https://payments.coinbase.com/payment-links/pl_01ks40rz0seeybnak5jrmmv99j"

ALCHEMY_SECRET_NAME     = "relayshield/alchemy_api_key"
GOPLUS_BASE_URL         = "https://api.gopluslabs.io/api/v1/address_security"
CHAINABUSE_URL          = "https://www.chainabuse.com/api/reports/addresses/{address}"
ALCHEMY_WEBHOOK_API     = "https://dashboard.alchemy.com/api"
WALLET_LIMIT_CRYPTO     = 5   # max wallets per Crypto Shield subscriber

TG_SECRET_NAME = "relayshield/telegram_bot_token"
TG_SECRET_KEY = "telegram_bot_token"

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"

# Admin
ADMIN_CHAT_ID = 1729226804  # Andrew — /stats and other privileged commands

# Monitor draft-reply feature (MONITOR-1)
MONITOR_DRAFTS_TABLE   = "relayshield_monitor_drafts"
ANTHROPIC_SECRET_NAME  = "relayshield/anthropic_api_key"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"

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
    # --- Crypto asset surface chains ---
    {
        "chain":    "sim_swap_wallet_flag",
        "signals":  {"sim_swap", "wallet_risk_flag"},
        "severity": "CRITICAL",
        "label":    "SIM Swap + Flagged Wallet Counterparty",
        "what": (
            "Your phone number is being hijacked at the same time your wallet received a "
            "transaction from an address flagged as malicious. This is the most common "
            "crypto theft chain: SIM swap to bypass exchange 2FA, then drain the wallet. "
            "Do not approve any pending transactions or sign anything until your SIM is locked."
        ),
    },
    {
        "chain":    "breach_wallet_flag",
        "signals":  {"breach_alert", "wallet_risk_flag"},
        "severity": "HIGH",
        "label":    "Credential Breach + Flagged Wallet Counterparty",
        "what": (
            "Your credentials were found in a breach while your wallet has a flagged "
            "transaction counterparty. Attackers who compromise exchange login credentials "
            "alongside wallet-adjacent malicious addresses may be coordinating a combined "
            "identity and asset drain. Change exchange passwords and revoke active sessions now."
        ),
    },
    {
        "chain":    "port_out_wallet_flag",
        "signals":  {"port_out", "wallet_risk_flag"},
        "severity": "CRITICAL",
        "label":    "Port-Out Fraud + Flagged Wallet Counterparty",
        "what": (
            "Your phone number has been ported to another carrier while your wallet has a "
            "flagged transaction counterparty. Port-out fraud gives attackers complete control "
            "of your SMS-based 2FA. Combined with a malicious wallet contact, this is an "
            "active coordinated crypto theft chain. Act immediately: call your carrier, "
            "freeze all exchange accounts, and do not sign any wallet transactions."
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
    # --- Crypto asset surface predictive warnings ---
    "sim_swap_wallet_flag": {
        "sim_swap": (
            "⚠️ *Heads up:* SIM swaps are the most common precursor to crypto account takeovers. "
            "Attackers who hijack your phone number can bypass SMS-based 2FA on exchanges and "
            "drain connected wallets.\n\n"
            "→ Lock your SIM with your carrier immediately\n"
            "→ Disable SMS 2FA on all crypto exchanges — switch to an authenticator app\n"
            "Use /phone for carrier-specific lock steps."
        ),
        "wallet_risk_flag": (
            "⚠️ *Heads up:* Your wallet has interacted with a flagged address. Attackers who "
            "have targeted your wallet may attempt to escalate by taking over your phone number "
            "to intercept exchange 2FA codes.\n\n"
            "→ Do not approve further transactions from unknown addresses\n"
            "→ Place a SIM lock on your account as a precaution — use /phone for steps"
        ),
    },
    "breach_wallet_flag": {
        "breach_alert": (
            "⚠️ *Heads up:* Credential breaches that include exchange logins are frequently "
            "paired with wallet-level attacks. If your breached credentials include a crypto "
            "exchange, attackers may be probing your wallet simultaneously.\n\n"
            "→ Change exchange passwords immediately\n"
            "→ Review your wallet for unexpected pending transactions"
        ),
        "wallet_risk_flag": (
            "⚠️ *Heads up:* Your wallet has a flagged transaction counterparty. If your "
            "credentials have also been exposed in any breach, attackers may use both vectors "
            "to access your exchange account and drain your wallet.\n\n"
            "→ Check /breach to see if your credentials are in any known database\n"
            "→ Enable withdrawal whitelisting on all exchanges"
        ),
    },
    "port_out_wallet_flag": {
        "port_out": (
            "⚠️ *Heads up:* Port-out fraud gives attackers full control of your phone number, "
            "including all SMS-based 2FA. This is a high-risk precursor to crypto account takeover.\n\n"
            "→ Contact your carrier immediately to reverse the port\n"
            "→ Freeze all crypto exchange withdrawals now\n"
            "Use /phone for carrier escalation steps."
        ),
        "wallet_risk_flag": (
            "⚠️ *Heads up:* Your wallet has a flagged transaction counterparty. Attackers who "
            "have made contact with your wallet may escalate by porting your phone number to "
            "intercept exchange 2FA codes.\n\n"
            "→ Place a port freeze on your account with your carrier — use /phone for steps\n"
            "→ Do not approve any pending wallet transactions"
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
    # photo_array is sorted smallest→largest; take the last (highest res)
    return download_telegram_file(photo_array[-1]["file_id"])


def download_telegram_file(file_id: str) -> bytes | None:
    """
    Download any Telegram file (photo or document) by file_id.
    Returns raw image bytes or None on failure.
    """
    try:
        token = get_bot_token()
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
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
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


def get_user_record(user_id: str) -> dict | None:
    """Fetch a user record directly by user_id."""
    table = dynamodb.Table(USERS_TABLE)
    resp = table.get_item(Key={"user_id": user_id})
    return resp.get("Item")


def _is_delegate(user: dict) -> bool:
    """True if this user has delegated admin access granted by their team admin."""
    admin_id = user.get("admin_user_id")
    if not admin_id:
        return False
    admin = get_user_record(admin_id)
    if not admin:
        return False
    return user.get("user_id", "") in admin.get("delegated_admin_ids", [])


def _effective_admin_id(user: dict) -> str:
    """Return the user_id of the team admin for both admins and delegates."""
    return user["user_id"] if user.get("is_team_admin") else user.get("admin_user_id", "")


def get_breach_alert_count(user_id: str) -> int:
    """Return the total number of breach alerts recorded for a user."""
    table = dynamodb.Table(BREACH_ALERTS_TABLE)
    count = 0
    kwargs: dict = {
        "FilterExpression": Attr("user_id").eq(user_id),
        "Select": "COUNT",
    }
    while True:
        resp = table.scan(**kwargs)
        count += resp.get("Count", 0)
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return count


def find_invite_code(code: str) -> dict | None:
    """Find an admin user record with this pending invite code."""
    table = dynamodb.Table(USERS_TABLE)
    resp = table.scan(
        FilterExpression=Attr("pending_invite_code").eq(code)
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def find_coinbase_charge(charge_id: str) -> dict | None:
    """
    Find a pending Crypto Shield stub record by Coinbase charge code.
    Only returns records still in AWAITING_TELEGRAM_LINK state (not yet linked).
    """
    table = dynamodb.Table(USERS_TABLE)
    resp = table.scan(
        FilterExpression=(
            Attr("coinbase_charge_id").eq(charge_id.upper().strip())
            & Attr("onboarding_state").eq("AWAITING_TELEGRAM_LINK")
        )
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def _create_trust_based_stub(charge_id: str, chat_id_str: str, first_name: str) -> str:
    """
    Create a Crypto Shield DynamoDB record on the spot when no webhook pre-created one.
    Used when the customer enters their Coinbase order ID directly in the bot.
    plan defaults to 'monthly' — upgraded manually if annual payment confirmed later.
    onboarding_source='trust_based' flags these records for audit.
    """
    now     = datetime.now(timezone.utc)
    expires = (now + timedelta(days=31)).isoformat()
    user_id = str(uuid.uuid4())

    item = {
        "user_id":              user_id,
        "tier":                 "crypto_shield",
        "subscription_tier":    "crypto_shield",
        "plan":                 "monthly",
        "delivery_channels":    ["telegram"],
        "preferred_channel":    "telegram",
        "coinbase_charge_id":   charge_id.upper().strip(),
        "onboarding_state":     "AWAITING_WALLET_CONFIRM",
        "onboarding_source":    "trust_based",
        "telegram_chat_id":     chat_id_str,
        "first_name":           first_name,
        "active":               True,
        "monitored_emails":     [],
        "wallets":              [],
        "recent_signals":       [],
        "subscription_start":   now.isoformat(),
        "subscription_expires": expires,
        "created_at":           now.isoformat(),
        "updated_at":           now.isoformat(),
    }

    dynamodb.Table(USERS_TABLE).put_item(Item=item)
    logger.info(
        "Trust-based Crypto Shield stub created — user_id=%s charge_id=%s",
        user_id, charge_id,
    )
    return user_id


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
            [{"text": "🆓 Try free — instant breach check", "callback_data": "intent_free"}],
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


def crypto_wallet_confirm_keyboard(wallet_addr: str) -> dict:
    """Inline keyboard asking if the payer wallet is the one to monitor."""
    short = wallet_addr[:6] + "..." + wallet_addr[-4:] if len(wallet_addr) > 12 else wallet_addr
    return {
        "inline_keyboard": [
            [{"text": f"✅ Yes — monitor {short}", "callback_data": "wallet_confirm_yes"}],
            [{"text": "❌ No — I'll enter a different address", "callback_data": "wallet_confirm_no"}],
        ]
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Freemium conversion prompts (CRYPTO-2 / MCP-9 pattern)
# Three triggers: post-sweep, 10th free check, /checktoken high-risk result
# ---------------------------------------------------------------------------

CRYPTO_SHIELD_CTA = (
    f"🛡️ *Upgrade to Crypto Shield — $19.99/month*\n"
    f"→ 24/7 SIM swap monitoring\n"
    f"→ Real-time wallet alerts (ETH, Base, Solana, BTC, TON)\n"
    f"→ Infostealer malware detection\n"
    f"→ Address poisoning detection\n"
    f"→ Liquidation warnings + token risk screening\n\n"
    f"Sets up in 2 minutes via Superfluid. No app required — alerts straight to Telegram.\n\n"
    f"👉 [Start monitoring → crypto.relayshield.net](https://crypto.relayshield.net)"
)


def _increment_free_check_count(user_id: str) -> int:
    """Increment free_check_count for a free-tier user. Returns the new count."""
    try:
        resp = dynamodb_resource.Table(USERS_TABLE).update_item(
            Key={"user_id": user_id},
            UpdateExpression="ADD free_check_count :one",
            ExpressionAttributeValues={":one": 1},
            ReturnValues="UPDATED_NEW",
        )
        return int(resp.get("Attributes", {}).get("free_check_count", 1))
    except Exception as exc:
        logger.error("free_check_count increment failed user=%s: %s", user_id, exc)
        return 0


def _maybe_send_check_milestone_prompt(chat_id: int, user: dict) -> None:
    """Fire a conversion prompt exactly at the 10th free command — once per user."""
    tier = user.get("tier") or user.get("subscription_tier", "")
    if tier != TIER_FREE:
        return
    user_id = user.get("user_id", "")
    count = _increment_free_check_count(user_id)
    if count == 10:
        send_message(
            chat_id,
            "👋 You've run 10 security checks — nice work staying sharp.\n\n"
            "Everything you've used so far is manual and on-demand. Crypto Shield runs the same "
            "checks automatically, 24/7 — and adds real-time wallet monitoring, SIM swap "
            "detection, and address poisoning alerts you can't trigger manually.\n\n"
            + CRYPTO_SHIELD_CTA,
        )


# ---------------------------------------------------------------------------
# HIBP helpers — free tier + paid onboarding breach check
# ---------------------------------------------------------------------------

def _run_hibp_check(email: str) -> list:
    """Call HIBP v3. Returns list of breach dicts; empty list if none found."""
    api_key = get_secret(HIBP_SECRET_NAME, HIBP_SECRET_KEY)
    encoded = urllib.parse.quote(email, safe="")
    url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{encoded}?truncateResponse=false"
    req = urllib.request.Request(url, headers={
        "hibp-api-key": api_key,
        "user-agent":   "RelayShield/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return []
        logger.error("HIBP HTTP %s for email=%s", exc.code, _hash_id(email))
        raise


def _send_free_breach_result(chat_id: int, email: str, breaches: list) -> None:
    """Gated result for free tier: breach names shown, remediation gated behind upgrade CTA."""
    if not breaches:
        send_message(
            chat_id,
            f"✅ *No breaches found* for `{email}`.\n\n"
            "Upgrade to Crypto Shield to add SIM swap monitoring, wallet protection, "
            "and infostealer malware detection — the complete crypto security stack.\n\n"
            f"👉 [Get Crypto Shield — $19.99/month]({CRYPTO_MONTHLY_URL})",
        )
    else:
        count = len(breaches)
        names = ", ".join(b["Name"] for b in breaches[:5])
        if count > 5:
            names += f" and {count - 5} more"
        send_message(
            chat_id,
            f"⚠️ *Found in {count} breach{'es' if count != 1 else ''}:* {names}.\n\n"
            "Upgrade to Crypto Shield to see exactly what data was exposed "
            "and get step-by-step remediation for each breach.\n\n"
            f"👉 [Get Crypto Shield — $19.99/month]({CRYPTO_MONTHLY_URL})",
        )


def _send_paid_breach_result(chat_id: int, email: str, breaches: list) -> None:
    """Full (ungated) breach result for paid users — used by ONBOARD-2."""
    if not breaches:
        send_message(
            chat_id,
            f"✅ *Breach check:* No breaches found for `{email}`.\n\n"
            "Ongoing monitoring is active — you'll be alerted immediately if this changes.\n\n"
            "🛡️ RelayShield",
        )
        return
    count = len(breaches)
    lines = [f"🔍 *Breach check:* `{email}` found in *{count} breach{'es' if count != 1 else ''}*\n"]
    for b in breaches[:5]:
        data_classes = ", ".join(b.get("DataClasses", [])[:4])
        lines.append(f"• *{b['Name']}* ({b.get('BreachDate', 'unknown')[:4]}) — {data_classes}")
    if count > 5:
        lines.append(f"…and {count - 5} more.")
    lines.append(
        "\n*Recommended actions:*\n"
        "→ Run /sweep — close email backdoors attackers may have planted\n"
        "→ Run /reuse — check cross-account password reuse\n"
        "→ Run /sessions — revoke all active sessions\n\n"
        "🛡️ RelayShield"
    )
    send_message(chat_id, "\n".join(lines))


def _start_free_signup(chat_id: int, first_name: str) -> None:
    """Create a free tier stub and prompt for email."""
    existing = get_user_by_chat_id(chat_id)
    if existing:
        send_message(
            chat_id,
            f"You already have an active RelayShield account, {first_name}. "
            "Type /help to see your commands.",
        )
        return
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    dynamodb.Table(USERS_TABLE).put_item(Item={
        "user_id":           user_id,
        "telegram_chat_id":  str(chat_id),
        "preferred_channel": "telegram",
        "delivery_channels": ["telegram"],
        "tier":              TIER_FREE,
        "active":            True,
        "onboarding_state":  "AWAITING_FREE_EMAIL",
        "first_name":        first_name,
        "monitored_emails":  [],
        "recent_signals":    [],
        "created_at":        now,
        "updated_at":        now,
    })
    send_message(
        chat_id,
        "🛡️ *Free Breach Check*\n\n"
        "Enter your email address and I'll check it against all known data breaches instantly:",
    )


def handle_coinbase_onboarding(chat_id: int, user: dict, first_name: str) -> None:
    """
    Called immediately after a Coinbase charge code is matched and
    telegram_chat_id has been linked to the subscriber record.
    Sends a welcome message then asks the wallet confirmation question.
    """
    plan_label = "Annual" if user.get("plan") == "annual" else "Monthly"
    payer_wallet = user.get("payer_wallet", "")

    send_message(
        chat_id,
        f"🪙 *Welcome to Crypto Shield, {first_name}!*\n\n"
        f"*Plan:* {plan_label}\n\n"
        "I monitor your wallets 24/7 — suspicious transactions, counterparty risk "
        "screening, SIM swap protection, credential breaches, and infostealer malware "
        "detection. Let's get you set up.",
    )

    if payer_wallet:
        update_user(user["user_id"], {"onboarding_state": "AWAITING_WALLET_CONFIRM"})
        send_message(
            chat_id,
            f"📍 *Your payment came from:*\n`{payer_wallet}`\n\n"
            "Is this the wallet you'd like to monitor?",
            reply_markup=crypto_wallet_confirm_keyboard(payer_wallet),
            parse_mode="Markdown",
        )
    else:
        # No payer wallet available — ask directly
        update_user(user["user_id"], {"onboarding_state": "AWAITING_WALLET_INPUT"})
        send_message(
            chat_id,
            "📍 Please enter the wallet address you'd like to monitor:\n\n"
            "_(Supports EVM 0x..., Solana, TON, and Bitcoin)_",
            parse_mode="Markdown",
        )


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
    if tier == TIER_FREE:
        return (
            "🛡️ *RelayShield Free — Commands*\n\n"
            "• /quickstart — Three things you can do right now\n"
            "• /verify — Callback rule, OTP rule, family safe word\n"
            "• /otp — Unexpected OTP guidance\n"
            "• /scan <url> — Scan a suspicious link for malware or phishing\n"
            "• /plan — Your license type\n"
            "• /help — This menu\n\n"
            "*Upgrade to Crypto Shield* to unlock:\n"
            "→ Breach remediation + inbox sweep + session revocation\n"
            "→ Infostealer malware detection\n"
            "→ SIM swap monitoring\n"
            "→ Wallet monitoring + counterparty risk screening\n"
            "→ 24/7 ongoing breach + domain monitoring\n\n"
            f"👉 [Get Crypto Shield — $19.99/month]({CRYPTO_MONTHLY_URL})"
        )

    is_business = tier in BUSINESS_TIERS

    text = (
        "🛡️ *RelayShield — Commands*\n\n"

        # Above the first section header on purpose: msg_help_section() slices
        # this text from one header to the next, so anything here belongs to no
        # category and shows only in the full list — which is what an
        # orientation line should do.
        "• /quickstart — Three things you can do right now\n\n"

        "*🔐 Breach Response*\n"
        "• /breach — Breach monitoring status\n"
        "• /sweep — Close email backdoors and sign out hijacked sessions across\n"
        "  Google, Microsoft, Apple, Facebook and X (was also /sessions)\n"
        "• /extensions — Audit browser extensions for infostealer malware\n"
        "• /reuse — Cross-account password reuse check\n\n"

        "*🚨 Threat Analysis*\n"
        "• /otp — Unexpected OTP guidance\n"
        "• /scam — Suspicious message, bot, or call? Get guidance, including what\n"
        "  to do during a live phone scam (was also /vishing)\n"
        "• /scan — Check a link, message or screenshot. Paste a URL, forward a "
        "suspicious email or SMS, or send a screenshot of one\n"
        "• /infostealer <email> — Check if an email was stolen by malware\n"
        "• /verify — Callback rule, OTP rule, safe word, wire transfer protocol\n\n"

        "*📡 Phone Protection*\n"
        "• /sim — SIM swap monitoring status\n"
        "• /phone — Carrier hardening against SIM swap and smishing\n"


        "*🤖 Telegram Security*\n"
        "• /tgsecurity — Harden Telegram, audit linked devices, and confirm this\n"
        "  bot is really RelayShield (was also /linkeddevices, /verifybot)\n"
        "• /tgsecurity @username — Typosquat and red-flag analysis of any bot or\n"
        "  channel (was /botcheck)\n"
    )

    if is_business:
        text += (
            "\n*🏢 Team Management*\n"
            "• /status — Seat usage and team overview\n"
            "• /teamstatus — Per-seat security health: SIM, emails, breach alerts\n"
            "• /setdomain — Set shared company domain for team-wide lookalike monitoring\n"
            "• /addmember — Generate an invite code for a new team member\n"
            "• /removemember — Remove a team member from your account\n"
            "• /delegate — Grant a team member admin access (addmember/removemember/teamstatus)\n"
            "• /revoke — Remove delegate access from a team member\n"
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
        "\n*⚙️ Account*\n"
        "• /plan — Your license type and upgrade options\n"
        "• /myid — Your Telegram chat ID (account linking & support)\n"
        "• /help — This menu\n\n"
        "Tap any command to get started.\n\n"
        "📢 *Security intel & updates:* t.me/RelayShield"
    )

    return text


def msg_onboarding_complete(first_name: str, email_count: int, tier: str,
                            wallet_count: int = 0) -> str:
    base = (
        f"✅ *You're protected, {first_name}!*\n\n"
        f"*SIM swap monitoring:* Active\n"
        f"*Breach monitoring:* Active for {email_count} email(s)\n"
    )
    if tier == TIER_CRYPTO:
        base += f"*Wallet monitoring:* Active for {wallet_count} wallet(s)\n"
    base += (
        "\nI'll alert you the moment a threat is detected.\n\n"
        "Type /help to see all available commands."
    )
    return base


def msg_first_run_tips(tier: str) -> str:
    """
    Tier-specific 'top 3 commands to try first' message sent immediately after
    onboarding completes. Varies by plan to surface the most relevant features.
    """
    if tier == TIER_CRYPTO:
        return (
            "🚀 *Start here — your top 3 commands:*\n\n"
            "1️⃣ /wallet — screen your wallet for counterparty risk and suspicious activity right now\n"
            "2️⃣ /breach — scan your email for known data breaches\n"
            "3️⃣ /sim — confirm SIM swap protection is active on your number\n\n"
            "_Tip: Send a wallet address anytime to run an instant counterparty check._"
        )
    elif tier == TIER_STARTER_DOMAIN:
        return (
            "🚀 *Start here — your top 3 commands:*\n\n"
            "1️⃣ /breach — scan your email for data breaches right now\n"
            "2️⃣ /domain — check your business domain for lookalike attacks\n"
            "3️⃣ /sim — confirm SIM swap protection is active on your number\n\n"
            "_Tip: /sweep runs a deep audit of your email account for backdoors attackers leave behind after a breach._"
        )
    elif tier in (TIER_BASIC, TIER_SHIELD, TIER_PRO):
        return (
            "🚀 *Start here — your top 3 commands:*\n\n"
            "1️⃣ /breach — scan your email for data breaches right now\n"
            "2️⃣ /status — check your team's monitoring status and seat usage\n"
            "3️⃣ /domain — check your business domain for lookalike attacks\n\n"
            "_Tip: Share /help with your team members so they know how to use their alerts._"
        )
    elif tier == TIER_STARTER:
        return (
            "🚀 *Start here — your top 3 commands:*\n\n"
            "1️⃣ /breach — scan your email for data breaches right now\n"
            "2️⃣ /sim — confirm SIM swap protection is active on your number\n"
            "3️⃣ /sweep — deep audit of your email for backdoors attackers leave behind after a breach\n\n"
            "_Tip: Most people change their password after a breach and stop there. /sweep catches what a password reset misses._"
        )
    elif tier == TIER_FREE:
        return (
            "🚀 *Start here — your top 3 commands:*\n\n"
            "1️⃣ /scan — paste a suspicious link or check a URL before you click it\n"
            "2️⃣ /breach — run a free breach check on your email\n"
            "3️⃣ /help — see everything available on the free tier\n\n"
            "_Tip: Upgrade to Personal Shield anytime for 24/7 monitoring and instant breach alerts._"
        )
    else:
        # TIER_PERSONAL and any future tiers
        return (
            "🚀 *Start here — your top 3 commands:*\n\n"
            "1️⃣ /breach — scan your email for data breaches right now\n"
            "2️⃣ /sim — confirm SIM swap protection is active on your number\n"
            "3️⃣ /plan — see everything your Personal Shield account covers\n\n"
            "_Tip: /sweep runs a deep audit of your email for backdoors attackers may have already planted._"
        )


# ---------------------------------------------------------------------------
# Onboarding handlers
# ---------------------------------------------------------------------------

def find_helio_link_code(link_code: str) -> dict | None:
    """
    Find a pending Crypto Shield stub record by Helio link_code UUID.
    Only returns records in AWAITING_TELEGRAM_LINK state (payment confirmed,
    but Telegram not yet linked).
    """
    table = dynamodb.Table(USERS_TABLE)
    resp = table.scan(
        FilterExpression=(
            Attr("link_code").eq(link_code)
            & Attr("onboarding_state").eq("AWAITING_TELEGRAM_LINK")
        )
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def handle_helio_onboarding(chat_id: int, user: dict, first_name: str) -> None:
    """
    Called after a Helio link_code has been matched and telegram_chat_id linked.
    Sends welcome message then starts the wallet-setup flow (same as Coinbase path).
    """
    plan_label = "Annual" if user.get("plan") == "annual" else "Monthly"

    send_message(
        chat_id,
        f"🪙 *Welcome to Crypto Shield, {first_name}!*\n\n"
        f"*Plan:* {plan_label}\n\n"
        "I monitor your wallets 24/7 — suspicious transactions, counterparty risk "
        "screening, SIM swap protection, credential breaches, and infostealer malware "
        "detection. Let's get you set up.",
    )

    # ONBOARD-2: immediate breach check on signup email (~60s after Telegram link)
    signup_email = user.get("email", "")
    if signup_email:
        send_message(chat_id, "🔍 Running a breach check on your email...")
        try:
            breaches = _run_hibp_check(signup_email)
            _send_paid_breach_result(chat_id, signup_email, breaches)
        except Exception as exc:
            logger.error("ONBOARD-2 breach check failed email=%s: %s", _hash_id(signup_email), exc)

    # Ask for wallet address to monitor
    update_user(user["user_id"], {"onboarding_state": "AWAITING_WALLET_INPUT"})
    send_message(
        chat_id,
        "📍 Please enter the wallet address you'd like to monitor:\n\n"
        "_(Supports EVM 0x..., Solana, TON, and Bitcoin)_",
        parse_mode="Markdown",
    )


def handle_start(chat_id: int, first_name: str, payload: str = "") -> None:
    """
    Handle /start — with optional Telegram deep link payload.

    Deep link paths:
      Helio web signup: payload is a UUID (link_code) — e.g.
        t.me/RelayShield_bot?start=f47ac10b-58cc-4372-a567-0e02b2c3d479
      Coinbase (legacy): payload is a short alphanumeric charge code — e.g.
        t.me/RelayShield_bot?start=ABCD1234

    Normal path:
      No payload → show welcome + intent keyboard.
    """
    # --- Helio web signup: /start UUID-link-code ---
    # Telegram deep links can't contain hyphens in the payload, so the UUID
    # is passed URL-safe (hyphens stripped) or as the full UUID string.
    # We accept both forms.
    if payload:
        # Normalise: if hyphens are missing but length is 32 hex chars, reinsert
        clean = payload.strip()
        if re.match(r"^[0-9a-f]{32}$", clean, re.IGNORECASE):
            # Reconstitute UUID format
            clean = f"{clean[0:8]}-{clean[8:12]}-{clean[12:16]}-{clean[16:20]}-{clean[20:32]}"
        if re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
            clean,
            re.IGNORECASE,
        ):
            user = find_helio_link_code(clean.lower())
            if user:
                now = datetime.now(timezone.utc)
                # Check link_code hasn't expired
                expiry_str = user.get("link_code_expiry", "")
                if expiry_str:
                    try:
                        expiry = datetime.fromisoformat(expiry_str)
                        if now > expiry:
                            send_message(
                                chat_id,
                                "⏱️ That activation link has expired.\n\n"
                                "Please contact support@relayshield.net for a new link.",
                            )
                            return
                    except (ValueError, TypeError):
                        pass  # If expiry can't be parsed, allow through

                update_user(user["user_id"], {
                    "telegram_chat_id": str(chat_id),
                    "first_name":       first_name,
                    "active":           True,
                    "link_code":        None,  # consume the code
                    "link_code_expiry": None,
                    "updated_at":       now.isoformat(),
                })
                user["telegram_chat_id"] = str(chat_id)
                user["first_name"] = first_name
                handle_helio_onboarding(chat_id, user, first_name)
                return
            else:
                # UUID format but no matching record — may already be used or invalid
                send_message(
                    chat_id,
                    "❌ That activation link has already been used or is invalid.\n\n"
                    "If you've already set up your account, type /status to check.\n"
                    "Otherwise contact support@relayshield.net.",
                )
                return

    # --- Acquisition source: /start SRC_<channel> ---
    #
    # Added 2026-08-10 so directory listings, the Snap, CS Mobile and the blog
    # are distinguishable instead of all arriving as anonymous /start traffic.
    #
    # Why the SRC_ prefix rather than a bare name like "botsarchive": the
    # Coinbase branch immediately below matches ^[A-Z0-9]{6,12}$, and
    # "BOTSARCHIVE" is 11 characters of A-Z. A bare payload would fire a
    # pointless charge lookup on every directory arrival before falling
    # through. An underscore cannot match that pattern, so the two schemes
    # can never collide. Telegram allows A-Za-z0-9_- in deep link payloads.
    #
    # Note the caller upper-cases the payload (see the /start routing), so
    # everything here is case-insensitive by construction.
    if payload and payload.upper().startswith("SRC_"):
        source = payload.upper()[4:].lower()[:32]
        # Source names are channel labels we choose, never user data, so they
        # are safe to log in the clear. The chat id is hashed, as everywhere.
        logger.info("acquisition source=%s chat=%s", source or "(empty)", _hash_id(chat_id))
        existing = get_any_user_by_chat_id(chat_id)
        if existing and not existing.get("acquisition_source"):
            # Only set once. The first touch is the one that earned the arrival;
            # overwriting on a later visit would credit the wrong channel.
            try:
                update_user(existing["user_id"], {"acquisition_source": source})
            except Exception as exc:
                logger.warning("acquisition source store failed: %s", exc)
        # Deliberately falls through to the normal /start welcome below. The
        # parameter is attribution only and must never change what the user sees.

    # --- Coinbase deep link (legacy): /start CHARGECODE ---
    if payload and re.match(r"^[A-Z0-9]{6,12}$", payload.upper()):
        charge = find_coinbase_charge(payload.upper())
        if charge:
            update_user(charge["user_id"], {
                "telegram_chat_id": str(chat_id),
                "first_name":       first_name,
                "active":           True,
                "updated_at":       datetime.now(timezone.utc).isoformat(),
            })
            charge["telegram_chat_id"] = str(chat_id)
            charge["first_name"] = first_name
            handle_coinbase_onboarding(chat_id, charge, first_name)
            return

    # --- Normal /start ---
    user = get_user_by_chat_id(chat_id)
    # Accept any state that indicates setup is complete — including manually-provisioned
    # accounts where onboarding_state may have been set to "DONE" or another non-standard value.
    _ACTIVE_STATES = ("ACTIVE", "FREE_ACTIVE", "DONE", "AWAITING_MORE_EMAILS",
                      "AWAITING_DOMAIN", "AWAITING_WALLET_INPUT", "AWAITING_WALLET_CONFIRM")
    if user and user.get("onboarding_state") in _ACTIVE_STATES:
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
    elif intent == "free":
        _start_free_signup(chat_id, first_name)


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
    """User shared their phone number via request_contact.

    Telegram's request_contact only ever shares the sharer's OWN number, so this
    is genuinely a self enrollment. The carrier authorization clause is shown
    here, before the Yes/No, because the Yes IS the consent event and a carrier
    audit asks what the person was shown at that moment.
    """
    send_message(
        chat_id,
        f"We'll monitor *{phone_number}* for SIM swap activity.\n\n"
        f"_{simswap_consent.CARRIER_CONSENT_TEXT}_\n\n"
        "Full terms: https://terms.relayshield.net\n\n"
        "Do you agree, and is the number correct?",
        parse_mode="Markdown",
        reply_markup=confirm_phone_keyboard(),
    )
    update_user(user["user_id"], {"pending_phone": phone_number})


def handle_phone_confirm(chat_id: int, confirmed: bool, user: dict) -> None:
    """User confirmed or rejected the phone number.

    FIXED 2026-08-14. This used to write phone_encrypted and phone_hash and then
    tell the user "SIM swap monitoring activated" WITHOUT ever setting
    sim_swap_monitoring. scan_sim_swap_users() filters on that flag, so every
    Telegram user who completed this flow was told they were protected and was
    monitored by nothing. Enrollment now goes through the shared consent module,
    which is the only thing permitted to set the flag.
    """
    if not confirmed:
        send_message(
            chat_id,
            "No problem — please type the number you'd like monitored.\n\nExample: `+1 555 123 4567`",
            parse_mode="Markdown",
        )
        return

    phone_raw = user.get("pending_phone", "")
    if not simswap_consent.is_valid_e164(phone_raw):
        # Telegram sometimes hands back a number without the leading +.
        candidate = "+" + simswap_consent.normalise_e164(phone_raw).lstrip("+")
        phone_raw = candidate if simswap_consent.is_valid_e164(candidate) else phone_raw

    try:
        # Consent belongs to the NUMBER, session state belongs to THIS record.
        # They are not always the same row when a number appears on more than
        # one account, so the session update is done separately rather than
        # passed through enroll(). See the matching note in the WhatsApp handler.
        simswap_consent.enroll(
            phone_raw,
            enrollment_type="self",
            consent_source="telegram",
            consent_acknowledged=True,
        )
        update_user(user["user_id"], {"pending_phone": None,
                                      "onboarding_state": "AWAITING_EMAIL_1"})
        activated = True
    except simswap_consent.AmbiguousPhone:
        logger.error("telegram phone confirm: ambiguous phone for user=%s", user["user_id"])
        activated = False
    except Exception as exc:
        logger.error("telegram phone confirm: enrollment failed: %s", exc)
        activated = False

    if not activated:
        # Never claim protection we did not switch on. That false assurance is
        # the exact defect this change fixes.
        update_user(user["user_id"], {"pending_phone": None,
                                      "onboarding_state": "AWAITING_EMAIL_1"})
        remove_keyboard(
            chat_id,
            "⚠️ We couldn't switch on SIM swap monitoring for that number just now, "
            "and we won't tell you it's active when it isn't. Our team has been alerted. "
            "Email support@relayshield.net if it isn't sorted shortly.\n\n"
            "Let's carry on with your email addresses. Send your first one:",
        )
        return

    remove_keyboard(
        chat_id,
        "✅ SIM swap monitoring activated.\n\n"
        "You can stop it at any time by sending STOPSIM.\n\n"
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
    set_commands_for_user(chat_id, tier)
    first_name = user.get("first_name", "there")
    wallet_count = len(user.get("wallets", []))
    send_message(chat_id, msg_onboarding_complete(first_name, len(emails), tier, wallet_count))
    send_message(chat_id, msg_first_run_tips(tier), parse_mode="Markdown")


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
        set_commands_for_user(chat_id, tier)
        send_message(
            chat_id,
            f"✅ *{domain}* added.\n\n" + msg_onboarding_complete(first_name, len(emails), tier),
            parse_mode="Markdown",
        )
        send_message(chat_id, msg_first_run_tips(tier), parse_mode="Markdown")


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


def msg_help_top(tier: str) -> str:
    """Short, curated 'commands to try first' teaser — shown instead of the full
    command list, which can run long enough to need real scrolling in Telegram's
    UI once a tier has team/crypto/domain sections. Full list is one tap away via
    the 'See all commands' button (Telegram has no in-message anchor/scroll, so
    a follow-up message is the closest equivalent)."""
    lines = [
        "🛡️ *RelayShield — Quick Start*\n",
        # First, and not a command, because it is the fastest useful action
        # and the only one that needs nothing typed. /quickstart expands it.
        "• *Forward me a suspicious message* — no command needed. I check the "
        "text, any link in it, and who sent it",
        "• /scan <url> — Scan a suspicious link for malware or phishing",
        "• /otp — Unexpected OTP? Get guidance now",
        "• /sweep — Close email backdoors and sign out hijacked sessions",
    ]
    if tier in CRYPTO_TIERS:
        lines.append("• /riskcheck — Risk score for all your monitored wallets")
    lines.append("• /plan — Your license type and upgrade options")
    lines.append("\n/quickstart for the three-step version.")
    return "\n".join(lines)


# Category shortcuts on the Quick Start card, added 2026-08-11.
#
# DELIBERATELY ADDITIVE. "See all commands" stays exactly as it was, because
# the complaint that started this was never "I can't find commands", it was
# "two of these look identical". Removing the flat list would solve a problem
# nobody has and slow down everyone who already knows the bot. These buttons
# are a shortcut for people who know roughly what they want, nothing more.
#
# key, emoji and label must match the section headers msg_help() emits, since
# msg_help_section() slices that text rather than duplicating it. One source of
# truth: add a command to msg_help and it appears in its category for free.
_HELP_SECTIONS = [
    ("breach", "🔐", "Breach Response",   None),
    ("threat", "🚨", "Threat Analysis",   None),
    ("phone",  "📡", "Phone Protection",  None),
    ("tg",     "🤖", "Telegram Security", None),
    ("team",   "🏢", "Team Management",   "business"),
    ("wallet", "🪙", "Crypto Shield",     "crypto"),
    ("domain", "🌐", "Domain Security",   "domain"),
]


def help_categories_for_tier(tier: str) -> list[tuple[str, str, str]]:
    """Which category buttons this tier may actually use. Free tier gets none:
    msg_help() returns a flat five-command list for free users with no section
    headers at all, so a category button would open an empty message."""
    if tier == TIER_FREE:
        return []
    gates = {"business": BUSINESS_TIERS, "crypto": CRYPTO_TIERS, "domain": DOMAIN_TIERS}
    return [(k, e, l) for k, e, l, gate in _HELP_SECTIONS
            if gate is None or tier in gates[gate]]


def msg_help_section(tier: str, key: str) -> str | None:
    """One category, sliced out of msg_help(tier) so the two can never drift."""
    full = msg_help(tier)
    headers = {k: f"*{e} {l}*" for k, e, l, _ in _HELP_SECTIONS}
    headers["account"] = "*⚙️ Account*"
    head = headers.get(key)
    if not head or head not in full:
        return None
    start = full.index(head)
    after = start + len(head)
    ends = [full.index(o, after) for o in headers.values()
            if o != head and o in full[after:]]
    return full[start:(min(ends) if ends else len(full))].strip()


def help_expand_keyboard(tier: str = TIER_PERSONAL) -> dict:
    rows = [[{"text": "📋 See all commands", "callback_data": "help_more"}]]
    cats = help_categories_for_tier(tier)
    # Two per row: Telegram renders long single-column keyboards as a wall,
    # which is the thing we are trying to avoid.
    for i in range(0, len(cats), 2):
        rows.append([{"text": f"{e} {l}", "callback_data": f"help_cat_{k}"}
                     for k, e, l in cats[i:i + 2]])
    return {"inline_keyboard": rows}


# Telegram's native "/" command menu (populated via setMyCommands) is a
# SEPARATE mechanism from msg_help's in-chat text menu above — that text
# menu was already correctly tier-filtered, but nothing in this codebase
# ever called setMyCommands, so every user saw the exact same global
# command list in Telegram's own autocomplete/menu UI regardless of tier
# (whatever was configured once, manually, via BotFather). Selecting an
# unavailable command there just ran it normally and hit the existing
# tier-gate message inside the handler — confusing, since the menu itself
# offered something the plan doesn't include. Fixed 2026-07-16 using
# Telegram's per-chat command scope (BotCommandScopeChat) so each user's
# native menu only ever lists what their plan actually has.
_BOT_COMMANDS_FREE = [
    ("quickstart", "Three things you can do right now"),
    ("help", "This menu"),
    ("verify", "Callback rule, OTP rule, family safe word"),
    ("otp", "Unexpected OTP guidance"),
    ("scan", "Scan a suspicious link for malware or phishing"),
    ("plan", "Your license type"),
]

_BOT_COMMANDS_BASE = [
    ("quickstart", "Three things you can do right now"),
    ("breach", "Breach monitoring status"),
    # Merged 2026-08-11, all on one test: would a real user fail to tell these
    # apart? /sessions into /sweep (sweep's own description already claimed
    # sessions), /vishing into /scam (scam already said "or call"),
    # /linkeddevices + /botcheck + /verifybot into /tgsecurity. Every merged
    # command still works as a hidden alias.
    ("sweep", "Close email backdoors and sign out hijacked sessions"),
    ("extensions", "Audit browser extensions for infostealer malware"),
    ("reuse", "Cross-account password reuse check"),
    ("otp", "Unexpected OTP guidance"),
    ("scam", "Suspicious message, bot, or call? Get guidance"),
    # Merged 2026-08-10 in the handler, but msgscan survived here and in the
    # /help text until 2026-08-11, so a paid user's native menu still offered
    # both and Arjen's original complaint was still live. msgscan, analyze and
    # analyse remain working ALIASES in cmd_scan; they are simply not advertised
    # as separate commands anywhere a user looks.
    ("scan", "Check a link, message or screenshot"),
    ("infostealer", "Check if an email was stolen by malware"),
    ("verify", "Callback rule, OTP rule, safe word, wire transfer protocol"),
    ("sim", "SIM swap monitoring status"),
    ("phone", "Carrier hardening against SIM swap and smishing"),
    ("tgsecurity", "Telegram security: harden, linked devices, check a bot"),
    ("plan", "Your license type and upgrade options"),
    ("myid", "Your Telegram chat ID (account linking & support)"),
    ("help", "This menu"),
]

_BOT_COMMANDS_BUSINESS = [
    ("status", "Seat usage and team overview"),
    ("teamstatus", "Per-seat security health: SIM, emails, breach alerts"),
    ("setdomain", "Set shared company domain for team-wide lookalike monitoring"),
    ("checkllm", "Check company domain for exposed LLM/AI provider API keys (LLMjacking)"),
    ("addmember", "Generate an invite code for a new team member"),
    ("removemember", "Remove a team member from your account"),
    ("delegate", "Grant a team member admin access"),
    ("revoke", "Remove delegate access from a team member"),
]

_BOT_COMMANDS_CRYPTO = [
    ("addwallet", "Add a wallet to monitoring (EVM, Solana, TON, Bitcoin)"),
    ("wallets", "List your monitored wallets"),
    ("removewallet", "Remove a wallet from monitoring"),
    ("riskcheck", "Risk score for all your monitored wallets"),
    ("approvals", "Scan EVM wallets for dangerous token approvals"),
    ("checkvault", "Check a DeFi protocol for audit and contract risks"),
    ("checktoken", "Check a token contract for rug pull and honeypot risks"),
    ("checknft", "Check an NFT collection contract for risks"),
]

_BOT_COMMANDS_DOMAIN = [
    ("domain", "Domain monitoring status and enrolled domains"),
    ("domainadd", "Enroll a new domain for monitoring"),
]


def commands_for_tier(tier: str) -> list[tuple[str, str]]:
    if tier == TIER_FREE:
        return _BOT_COMMANDS_FREE
    commands = list(_BOT_COMMANDS_BASE)
    if tier in BUSINESS_TIERS:
        commands += _BOT_COMMANDS_BUSINESS
    if tier in CRYPTO_TIERS:
        commands += _BOT_COMMANDS_CRYPTO
    if tier in DOMAIN_TIERS:
        commands += _BOT_COMMANDS_DOMAIN
    return commands


def set_commands_for_user(chat_id: int, tier: str) -> None:
    """Scopes Telegram's native command menu to this chat_id so it only
    ever shows commands the user's plan actually includes. Best-effort —
    a failure here shouldn't block whatever triggered it."""
    try:
        tg_api("setMyCommands", {
            "commands": [{"command": c, "description": d} for c, d in commands_for_tier(tier)],
            "scope": {"type": "chat", "chat_id": chat_id},
        })
    except Exception as exc:
        logger.warning("setMyCommands failed for chat_id=%s tier=%s: %s", chat_id, tier, exc)


def handle_help_no_account(chat_id: int) -> None:
    """/help for a chat with no user record.

    Deliberately does NOT reuse msg_help(TIER_FREE). Every command in that list
    is routed through route_active_command, which needs a record, so showing it
    here would advertise commands that answer "Type /start" when tapped. Say
    what the bot does and what the one working command is instead.
    """
    send_message(
        chat_id,
        "🛡️ *RelayShield*\n\n"
        "I watch for the things that precede an account takeover: credential "
        "breaches, infostealer malware, SIM swaps, and lookalike domains.\n\n"
        "You do not have an account on this chat yet, so commands will not run.\n\n"
        "👉 Type /start to set one up. The free tier needs no card.",
        parse_mode="Markdown",
    )


def handle_help(chat_id: int, user: dict) -> None:
    tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)
    set_commands_for_user(chat_id, tier)
    if tier == TIER_FREE:
        send_message(chat_id, msg_help(tier))
        return
    send_message(chat_id, msg_help_top(tier), reply_markup=help_expand_keyboard(tier))


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
        "Yahoo: login.yahoo.com/account/security\n"
        "→ Remove any recovery contact you don't recognise.\n\n"
        "*Step 4 — Review connected apps*\n"
        "Gmail: myaccount.google.com/permissions\n"
        "Yahoo: login.yahoo.com/account/security → \"External connections\"\n"
        "→ Revoke anything unrecognised.\n\n"
        # /sessions was merged in here 2026-08-11. Its provider list was wider
        # than this step's Gmail/Yahoo pair, and a user with a hijacked session
        # has no way to guess which of two commands to run, so the full list
        # lives here now. /sessions still works as a hidden alias.
        "*Step 5 — Check active sessions and sign out*\n"
        "A stolen session cookie survives a password change, so this step is the one\n"
        "that actually ends an intruder's access.\n"
        "Gmail: myaccount.google.com/device-activity\n"
        "Yahoo: login.yahoo.com/account/security → \"Recent activity\"\n"
        "Google (all devices): myaccount.google.com → Security → Your devices\n"
        "Microsoft: mysignins.microsoft.com\n"
        "Apple: Settings → Your name → scroll to devices\n"
        "Facebook: Settings → Security → Where you're logged in\n"
        "X/Twitter: Settings → Security → Sessions\n"
        "→ Sign out of every session you don't recognise, then change your password.\n"
        "→ Do this from a device you trust. If malware is on the machine you're\n"
        "  using, a password change from it just hands over the new one.\n\n"
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
        "Gmail: Settings → See all settings → Filters and Blocked Addresses\n"
        "Outlook: Settings → Rules → delete unknown rules.\n"
        "→ Delete any filter you didn't create.\n\n"
        "✅ *Sweep complete. All 5 checks done.*",
    )
    # Conversion prompt — free tier only
    user = get_user_by_chat_id(chat_id)
    if user and (user.get("tier") or user.get("subscription_tier", "")) == TIER_FREE:
        send_message(
            chat_id,
            "💡 *You just did this manually — Crypto Shield does it automatically.*\n\n"
            "SIM swap, infostealer exposure, wallet drains, and address poisoning run 24/7 "
            "in the background. You get a Telegram alert the moment anything changes — "
            "no manual checks required.\n\n"
            + CRYPTO_SHIELD_CTA,
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
        "• Use an authenticator app instead\n\n"
        "─────────────────────\n"
        "⚠️ *eSIM myth: \"eSIM protects against SIM swap\"*\n\n"
        "It doesn't. eSIM changes *how* the attack happens — not whether it can.\n\n"
        "With a physical SIM, an attacker walks into a carrier store and social-engineers "
        "a rep. With eSIM, they call the carrier and do the same thing over the phone. "
        "The attack is now fully remote — arguably easier, since they never leave the house.\n\n"
        "Some carriers have also *loosened* eSIM verification to reduce switching friction "
        "for legitimate customers. That's a gift to attackers.\n\n"
        "eSIM does prevent physical SIM theft — someone removing the card from your phone. "
        "That's a real but rare attack. SIM swap is almost always social engineering, "
        "and eSIM doesn't touch that surface at all.\n\n"
        "✅ *The same defences protect both physical SIM and eSIM:*\n"
        "carrier account PIN + number lock + authenticator app 2FA.",
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


def handle_linkeddevices(chat_id: int) -> None:
    send_message(
        chat_id,
        "🔗 Linked Device Audit\n\n"
        "Attackers abuse QR-based device-linking to silently read your messages — "
        "no malware, no password needed. Audit all three apps now:\n\n"
        "TELEGRAM\n"
        "Settings → Devices\n"
        "Remove any device you don't recognise.\n"
        "Tap 'Terminate All Other Sessions' if unsure.\n\n"
        "WHATSAPP\n"
        "Settings → Linked Devices\n"
        "Log out any unfamiliar session.\n"
        "WhatsApp sends NO alert when a device is linked.\n\n"
        "SIGNAL\n"
        "Settings → Account → Linked Devices\n"
        "Tap minus next to any unrecognised device.\n\n"
        "KEY RULE: Never scan a QR code from a message link — "
        "Telegram, WhatsApp and Signal never send QR codes via message.\n\n"
        "If you found an unrecognised device:\n"
        "1. Unlink it immediately\n"
        "2. Enable 2-step verification on all messaging apps\n"
        "3. Run /breach to check for credential exposure\n\n"
        "Repeat this audit monthly.\n\n"
        "📢 t.me/RelayShield\n"
        "🛡️ RelayShield",
    )


def handle_tgsecurity(chat_id: int, username: str | None = None) -> None:
    """One Telegram-security command with three jobs, merged 2026-08-11.

        /tgsecurity            -> harden the account, audit linked devices,
                                  and confirm this bot is the real RelayShield
        /tgsecurity @somebot   -> typosquat and red-flag analysis of that bot

    Why the merge: nobody types /verifybot while being impersonated, because
    doubting the bot is exactly the thought an impersonation attack prevents.
    Folding it into the command people DO reach for makes it discoverable at
    the moment it matters. /linkeddevices, /botcheck and /verifybot all still
    work as hidden aliases, so nothing anyone has learned breaks.
    """
    if username:
        handle_botcheck(chat_id, username)
        return

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
    # /linkeddevices and /verifybot merged in here 2026-08-11.
    handle_linkeddevices(chat_id)
    send_message(
        chat_id,
        "🤖 *Checking a bot, including this one*\n\n"
        "*Is this really RelayShield?* Run /tgsecurity any time and compare what you see "
        "here against the official details. An impostor can copy a name and a picture, "
        "but not the username.\n\n"
        "*Checking someone else's bot or channel:*\n"
        "`/tgsecurity @thebotusername`\n"
        "→ Typosquat and red-flag analysis before you interact with it.\n\n"
        "Telegram will never ask for your login code. Neither will we.",
    )
    handle_verify_bot(chat_id)


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


# Reply-prompt markers — each is a unique, fixed substring of its command's
# "no argument given" prompt. handle_message matches these against
# reply_to_message.text (Telegram echoes the prompt's own text back on a
# reply) so users can reply directly with their answer instead of retyping
# "/command <arg>". Originally built for /scan only; generalized to every
# argument-taking command 2026-07-15 for consistency (see REPLY_PROMPT_HANDLERS).
# Per-cold-start salt, same construction as relayshield_api.py's redaction.
# A hash is stable within one container so a single conversation can be
# followed through the logs, and unlinkable across time because the salt dies
# with the container.
_LOG_SALT = secrets.token_hex(16)


def _hash_id(value) -> str:
    """Short, salted, one-way handle for an identifier destined for a log."""
    if value in (None, ""):
        return "-"
    return hashlib.sha256(f"{_LOG_SALT}|{value}".encode()).hexdigest()[:12]


def _summarise_update(body: dict) -> str:
    """Describe a Telegram update for the log WITHOUT its content.

    Replaced a raw `json.dumps(body)[:500]` on 2026-08-10. That line wrote
    every inbound message body to CloudWatch in plaintext, so any email or
    phone number a user typed was retained for the full 90 days, along with
    Telegram user ids and usernames. The 2026-08-09 PII sweep covered
    relayshield_api.py and missed this file completely.

    Newly urgent because inline mode went live the same day: inline queries
    arrive from people who have never started the bot and have no account
    with us at all.

    What is safe to keep, and why: the update type and a salted chat-id hash
    are enough to trace one conversation through a debugging session, which is
    what the original line was actually used for. The message text never was.
    """
    kind = next((k for k in (
        "message", "callback_query", "inline_query", "chosen_inline_result",
        "edited_message", "channel_post", "my_chat_member",
    ) if k in body), "unknown")

    payload = body.get(kind) or {}
    if not isinstance(payload, dict):
        payload = {}
    chat = payload.get("chat") or {}
    frm  = payload.get("from") or {}

    parts = [f"type={kind}",
             f"chat={_hash_id(chat.get('id') or frm.get('id'))}"]

    if kind == "message":
        # Shape only. Never the text itself.
        parts.append("has_text=%s" % bool(payload.get("text")))
        parts.append("has_photo=%s" % bool(payload.get("photo")))
        if payload.get("text", "").startswith("/"):
            parts.append("cmd=%s" % payload["text"].split()[0].split("@")[0][:20])
    elif kind == "inline_query":
        # Length, not content: an inline query can be a wallet address.
        parts.append("qlen=%d" % len(payload.get("query", "")))
    elif kind == "callback_query":
        parts.append("data=%s" % str(payload.get("data", ""))[:24])

    return " ".join(parts)


SCAN_PROMPT_MARKER         = "URL / File Scanner"
ANALYZE_PROMPT_MARKER      = "Message Analyzer"
INFOSTEALER_PROMPT_MARKER  = "Infostealer Check"
CHECKVAULT_PROMPT_MARKER   = "Vault Risk Check"
CHECKTOKEN_PROMPT_MARKER   = "Token Risk Check"
CHECKNFT_PROMPT_MARKER     = "NFT Risk Check"
ADDWALLET_PROMPT_MARKER    = "Add Wallet"
REMOVEWALLET_PROMPT_MARKER = "Your Monitored Wallets"

VT_SECRET_NAME = "relayshield/virustotal_api_key"
VT_BASE_URL    = "https://www.virustotal.com/api/v3"

GSB_SECRET_NAME  = "relayshield/google_safe_browsing"
GSB_URL          = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
RDAP_URL         = "https://rdap.org/domain/{domain}"


def _vt_api_key() -> str:
    return get_secret(VT_SECRET_NAME, "virustotal_api_key")


def _check_gsb(domain: str) -> bool:
    """Google Safe Browsing blocklist check — mirrors relayshield_api.py's
    _check_gsb (same request shape), duplicated here rather than shared
    since the two Lambdas are otherwise fully isolated."""
    try:
        api_key = get_secret(GSB_SECRET_NAME, "google_safe_browsing_api_key")
    except Exception as exc:
        logger.warning("GSB secret unavailable: %s", exc)
        return False
    urls = [f"http://{domain}/", f"https://{domain}/"]
    payload = json.dumps({
        "client": {"clientId": "relayshield", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes":      ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"],
            "platformTypes":    ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries":    [{"url": u} for u in urls],
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{GSB_URL}?key={api_key}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            return bool(json.loads(resp.read()).get("matches"))
    except Exception as exc:
        logger.warning("GSB check failed for %s: %s", domain, exc)
        return False


def _rdap_registration_age_days(domain: str) -> int | None:
    """Mirrors relayshield_agentic_api.py's helper of the same name."""
    url = RDAP_URL.format(domain=urllib.parse.quote(domain))
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read())
        for event in data.get("events", []):
            if event.get("eventAction") == "registration":
                reg_str = event.get("eventDate", "")
                if reg_str:
                    reg_dt = datetime.fromisoformat(reg_str.replace("Z", "+00:00"))
                    return (datetime.now(timezone.utc) - reg_dt).days
    except Exception as exc:
        logger.warning("RDAP lookup failed for %s: %s", domain, exc)
    return None


def _normalize_scan_url(raw: str) -> str | None:
    """Accepts a shortform domain (e.g. "evil.com") as well as a full URL —
    added 2026-07-16, users shouldn't have to type https:// themselves.
    Prepends https:// when no scheme is given. Without this, a bare
    domain silently broke _heuristic_url_check's domain extraction
    (urlparse("evil.com").netloc is empty without a scheme) rather than
    erroring — same fix as relayshield_whatsapp_webhook.py's version.
    Returns None if the input doesn't look like a URL/domain at all."""
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith(("http://", "https://")):
        return raw
    if "." not in raw or " " in raw:
        return None
    return f"https://{raw}"


def _heuristic_url_check(url: str) -> dict:
    """Fast, VT-independent red-flag check so a URL VT hasn't analyzed yet
    can still get a definitive-ish verdict instead of a blanket "unknown"
    reply. Added 2026-07-16. Three signals, matching check_mcp_server_risk's
    identical-looking check: a direct hit in RelayShield's own criminal IOC
    corpus, Google Safe Browsing's real-time blocklist, and very recent
    domain registration. The IOC-corpus signal was deliberately left out of
    the first version of this function — testing that day found
    relayshield_intel_iocs contained false-positive "domain" records for
    google.com (9), microsoft.com (12), and apple.com (3), all from
    PhishTank's classic redirect-URL misattribution bug (a phishing page
    reached via e.g. google.com/url?q=... gets ingested under the
    redirector's own domain). That's now fixed at the source
    (relayshield_intel_feed.py's _ingest_phishtank stores the full URL as an
    ioc_type "url" now, matching openphish's already-correct convention) and
    the existing bad records (1,147 across 8 contaminated domains, found via
    a broader audit) were deleted — safe to re-add here. Not as
    authoritative as a real multi-engine VT verdict — callers should word a
    heuristic-only "flagged" result more cautiously than a VT one.
    Returns {"flagged": bool, "reasons": [str, ...]}."""
    try:
        domain = urllib.parse.urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
    except Exception:
        domain = ""

    reasons: list[str] = []
    if not domain:
        return {"flagged": False, "reasons": reasons}

    # ORDER IS THE DESIGN, not an accident. Cheapest and most authoritative
    # first, and RETURN as soon as a blocklist-grade signal fires, so a known
    # bad domain costs one local DynamoDB query and no external calls at all.
    # Restored 2026-08-11 after the ordering was found inverted in production.
    #
    # `blocklist_hit` is what the caller uses to skip VirusTotal entirely. The
    # domain-age signal deliberately does NOT set it: young is not guilty, so
    # that one still needs corroboration.
    try:
        table = dynamodb.Table("relayshield_intel_iocs")
        # NO FilterExpression with a Limit. DynamoDB applies Limit to items
        # EXAMINED, before filtering, so `Limit=5` + a type filter could return
        # empty for a domain with thousands of matching rows -- the same shape
        # of bug that made actor-lookup blind to 83% of the MITRE table. Pull a
        # bounded page newest-first and filter in Python instead: one round
        # trip, 100 rows instead of 5, and no false clean.
        resp = table.query(
            KeyConditionExpression=Key("ioc_value").eq(domain),
            ScanIndexForward=False,
            Limit=100,
        )
        if any(i.get("ioc_type") in ("domain", "url") for i in resp.get("Items", [])):
            reasons.append("this domain appears in RelayShield's criminal IOC corpus")
            return {"flagged": True, "blocklist_hit": True, "reasons": reasons}
    except Exception as exc:
        logger.warning("Heuristic IOC lookup failed domain=%s: %s", domain, exc)

    if _check_gsb(domain):
        reasons.append("Google Safe Browsing flags this domain")
        return {"flagged": True, "blocklist_hit": True, "reasons": reasons}

    age_days = _rdap_registration_age_days(domain)
    if age_days is not None and age_days < 30:
        reasons.append(f"the domain was registered only {age_days} day{'s' if age_days != 1 else ''} ago")

    return {"flagged": bool(reasons), "blocklist_hit": False, "reasons": reasons}


def check_url_sync(url: str) -> dict:
    """Synchronous URL reputation check against VirusTotal's existing-report
    lookup (GET /urls/{id}) — deliberately not the submit-then-poll flow used
    by /v1/scan-url, since that's async and doesn't fit a single Telegram
    reply. Most URLs a user would actually paste here (known phishing/malware
    sites) have already been scanned by someone else, so a plain GET usually
    has an answer immediately. Added 2026-07-11 — current volume is low
    enough that a straightforward per-call VT lookup is the right tradeoff;
    revisit if/when volume grows enough to need VT's commercial API tier.

    Returns {"status": "clean"|"malicious"|"suspicious"|"unknown", "detail": str}.
    "unknown" means VT has no report yet — fires a fire-and-forget submission
    for future reference but does not wait for that analysis to complete."""
    url_id = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
    try:
        vt_key = _vt_api_key()
    except Exception as exc:
        logger.error("VT secret unavailable: %s", exc)
        return {"status": "unknown", "detail": "Scan service temporarily unavailable"}

    req = urllib.request.Request(
        f"{VT_BASE_URL}/urls/{url_id}",
        headers={"x-apikey": vt_key},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            attrs = json.loads(resp.read()).get("data", {}).get("attributes", {})
            stats = attrs.get("last_analysis_stats", {})
            malicious  = stats.get("malicious", 0)
            suspicious = stats.get("suspicious", 0)
            total      = sum(stats.values()) or 1
            if malicious > 0:
                return {"status": "malicious", "detail": f"{malicious}/{total} security vendors flagged this URL as malicious"}
            if suspicious > 0:
                return {"status": "suspicious", "detail": f"{suspicious}/{total} security vendors flagged this URL as suspicious"}
            return {"status": "clean", "detail": f"Scanned by {total} security vendors — no threats found"}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            try:
                submit_body = urllib.parse.urlencode({"url": url}).encode("utf-8")
                submit_req = urllib.request.Request(
                    f"{VT_BASE_URL}/urls", data=submit_body,
                    headers={"x-apikey": vt_key, "Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                urllib.request.urlopen(submit_req, timeout=5)
            except Exception:
                pass  # best-effort — not knowing the submission result is fine here
            return {"status": "unknown", "detail": "Not yet analyzed — submitted for scanning"}
        logger.error("VT lookup HTTP %d for url=%s", exc.code, url)
        return {"status": "unknown", "detail": "Scan service temporarily unavailable"}
    except Exception as exc:
        logger.error("VT lookup failed url=%s error=%s", url, exc)
        return {"status": "unknown", "detail": "Scan service temporarily unavailable"}


def _send_scan_verdict(chat_id: int, target: str, verdict: str, detail: str, prefix: str = "Scan result") -> None:
    """Shared formatting for a scan verdict — used by both the immediate
    handle_scan reply and handle_deferred_url_scan's follow-up, so the two
    messages read consistently."""
    if verdict in ("malicious", "suspicious"):
        send_message(
            chat_id,
            f"⚠️ *{prefix} for* `{target}`\n\n"
            f"{detail}.\n\n"
            "Do not click this link. Report it and delete the message if it was sent to you.",
            parse_mode="Markdown",
        )
    elif verdict == "clean":
        send_message(
            chat_id,
            f"🔍 *{prefix} for* `{target}`\n\n"
            f"{detail}. No suspicious scam signals detected.\n\n"
            "Still worth a second look if something feels off:\n"
            "→ Check the domain's registration date (whois)\n"
            "→ Watch for URL shorteners hiding the real destination\n"
            "→ Look for mismatched domains (paypa1.com, g00gle.com)\n\n"
            "Still unsure? Don't click — ask us.",
            parse_mode="Markdown",
        )
    else:
        send_message(
            chat_id,
            f"🔍 *{prefix}:* `{target}`\n\n"
            f"{detail}. Here's what to check manually in the meantime:\n\n"
            "→ Check the domain's registration date (whois)\n"
            "→ Watch for URL shorteners hiding the real destination\n"
            "→ Look for mismatched domains (paypa1.com, g00gle.com)\n"
            "→ Confirm HTTPS, not HTTP\n"
            "→ Be wary of urgent language pushing you to act immediately\n\n"
            "Still unsure? Don't click — ask us.",
            parse_mode="Markdown",
        )


def handle_scan_dispatch(chat_id: int, content: str | None = None, user: dict | None = None) -> None:
    """Single entry point for /scan, /msgscan, /analyze and /analyse.

    Merged 2026-08-10. A real user (Arjen) could not tell /scan and /msgscan
    apart, which is a fair complaint: both are "check this thing for me".
    One command now, and the input decides which engine runs.

    IMPORTANT, and the reason this is a dispatcher rather than a deletion:
    the two paths are NOT interchangeable, in the opposite direction to what
    you would guess from the command names.

      handle_scan     URL only. Calls check_url_sync (VirusTotal, multi-engine)
                      plus _heuristic_url_check, and schedules a deferred
                      follow-up when VT has not finished processing. This is
                      the ONLY VirusTotal path in the bot.
      handle_analyze  Text or OCR'd image. Social-engineering and impersonation
                      analysis, and it heuristically checks any embedded URL
                      via _heuristic_url_check, which is IOC corpus + Google
                      Safe Browsing + domain age and, in its own docstring,
                      "not as authoritative as a real multi-engine VT verdict".

    So retiring either one loses capability. Retiring handle_scan would have
    silently removed VirusTotal from the product. The commands merge; the
    engines do not.
    """
    if not content:
        # No argument: ask for input rather than guessing. Accepts either kind.
        send_message(
            chat_id,
            f"🔍 *{SCAN_PROMPT_MARKER}*\n\n"
            "Reply with any of these and I'll check it:\n"
            "• a link, before you click it\n"
            "• a suspicious email or text, pasted in\n"
            "• a screenshot of one\n",
            reply_markup={"force_reply": True, "input_field_placeholder": "Paste a link or message…"},
            parse_mode="Markdown",
        )
        return

    # A bare URL and nothing else goes to the VirusTotal path. Anything with
    # prose around it is a message to analyse, and handle_analyze checks any
    # URLs inside it on the way through.
    stripped = content.strip()
    if _normalize_scan_url(stripped) and len(stripped.split()) == 1:
        handle_scan(chat_id, stripped, user)
    else:
        handle_analyze(chat_id, content)


def handle_scan(chat_id: int, target: str | None = None, user: dict | None = None) -> None:
    """Scan a URL or file link for threats — Telegram equivalent of ATTACH.

    Reached via handle_scan_dispatch, not routed directly from a command since
    2026-08-10.
    """
    if not target:
        send_message(
            chat_id,
            f"🔍 *{SCAN_PROMPT_MARKER}*\n\n"
            "Reply to this message with a suspicious link to scan.\n\n"
            "I'll check it for malware, phishing, and reputation signals.",
            reply_markup={"force_reply": True, "input_field_placeholder": "Paste URL here…"},
            parse_mode="Markdown",
        )
        return

    normalized = _normalize_scan_url(target)
    if not normalized:
        # 810d9e0, restored 2026-08-26. Someone who pastes a suspicious message
        # after /scan is not going to read the help and retype it as /msgscan,
        # so pasted prose goes to the fraud analyser rather than erroring. Kept
        # narrow: a short token with no spaces ("asdf", "htttp:/x") is a typo'd
        # URL, not a message, and saying so is more useful than running fraud
        # analysis on four characters.
        if _looks_like_message(target):
            handle_analyze(chat_id, target)
            return
        send_message(chat_id, f"That doesn't look like a URL: `{target}`", parse_mode="Markdown")
        return
    target = normalized

    send_message(chat_id, f"🔍 Scanning `{target}` — one moment...", parse_mode="Markdown")

    # OUR CORPUS FIRST, VIRUSTOTAL LAST. Restored 2026-08-11: production had
    # inverted this and was calling VT unconditionally on every scan, before
    # the local checks, which cost a third-party call and its latency even
    # when our own corpus already had the answer. VT is an external HTTP call
    # with an 8s timeout; the IOC query is a single local DynamoDB read.
    #
    #   1. IOC corpus, then Safe Browsing, then domain age (_heuristic_url_check)
    #   2. blocklist-grade hit -> malicious, and VT is never called
    #   3. domain-age-only hit -> soft signal, so still ask VT
    #   4. nothing -> ask VT, then the deferred follow-up path below
    heuristics = _heuristic_url_check(target)

    if heuristics.get("blocklist_hit"):
        # Named source beats an anonymous vendor count, and we already know.
        verdict, detail = "malicious", "; ".join(heuristics["reasons"]).capitalize()
        result = {"status": "not_queried", "detail": detail}
    else:
        result = check_url_sync(target)
        # VT's own verdict wins when it has one. A VT "clean" or "unknown"
        # never overrides a real heuristic hit.
        if result["status"] in ("malicious", "suspicious"):
            verdict, detail = result["status"], result["detail"]
        elif heuristics["flagged"]:
            verdict, detail = "suspicious", "; ".join(heuristics["reasons"]).capitalize()
        elif result["status"] == "clean":
            verdict, detail = "clean", result["detail"]
        else:
            verdict, detail = "unknown", result["detail"]

    is_suspicious = verdict in ("malicious", "suspicious")

    if verdict == "unknown":
        # Truly unknown: VT has no report yet and the fast heuristics found
        # nothing either. Give an honest immediate answer, then follow up
        # once VT has had a few seconds to process the submission
        # check_url_sync just fired — avoids blocking this reply on VT's
        # queue (which doesn't fit a single synchronous Telegram response)
        # while still surfacing a real verdict if one lands shortly.
        send_message(
            chat_id,
            f"🔍 *Scan:* `{target}`\n\n"
            "No immediate red flags from quick checks. Running a deeper scan — I'll follow up in a few seconds.",
            parse_mode="Markdown",
        )
        try:
            lambda_client.invoke(
                FunctionName=os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "relayshield-telegram-webhook"),
                InvocationType="Event",
                Payload=json.dumps({
                    "source": "relayshield_deferred_scan",
                    "chat_id": chat_id,
                    "target": target,
                }).encode("utf-8"),
            )
        except Exception as exc:
            logger.warning("Failed to schedule deferred scan follow-up for %s: %s", target, exc)
    else:
        _send_scan_verdict(chat_id, target, verdict, detail)

    # Only record a signal / fire the predictive "Heads up" warning when the scan
    # actually flagged something — not on every /scan call regardless of outcome
    # (previously fired unconditionally here, which meant a clean scan could still
    # trigger a scary phishing/SIM-swap warning with nothing to back it up).
    if user and is_suspicious:
        signals = record_signal(user["user_id"], "suspicious_url", {"url": target})
        check_and_warn_predictive(user["user_id"], "suspicious_url", signals, chat_id)
        check_and_fire_correlation(user["user_id"], signals, chat_id)


def handle_deferred_url_scan(chat_id: int, target: str) -> None:
    """Runs in a separate async Lambda invocation (self-invoked from
    handle_scan via lambda_client.invoke, InvocationType="Event") so the
    original Telegram reply doesn't have to block on VT's analysis queue.
    Gives VT a short window to finish processing the URL check_url_sync
    already submitted for scanning, then re-checks and sends the
    definitive follow-up message. Added 2026-07-16."""
    time.sleep(8)
    result = check_url_sync(target)
    if result["status"] == "unknown":
        _send_scan_verdict(chat_id, target, "unknown", "Still not analyzed yet", prefix="Follow-up scan")
    else:
        _send_scan_verdict(chat_id, target, result["status"], result["detail"], prefix="Follow-up scan result")


def handle_analyze(chat_id: int, content: str | None = None,
                   from_image: bool = False, forward_note: str = "") -> None:
    """Analyze suspicious message text — Telegram equivalent of SMS/EMAIL.

    forward_note carries the provenance block built by
    relayshield_forward_analysis when this text arrived as a forward. It is
    prepended to the verdict rather than sent as its own message: two replies
    to one forward reads as the bot answering twice, and the provenance is
    context for the verdict, not a separate finding.

    It is prepended in BOTH branches deliberately. The no-flags branch is
    exactly where provenance matters most — "no red flags in the text" plus a
    sender who has turned up across several criminal channels is not a clean
    result, and dropping the note there would make it look like one.
    """
    if not content:
        send_message(
            chat_id,
            f"🧠 *{ANALYZE_PROMPT_MARKER}*\n\n"
            "Reply to this message with a suspicious message to analyze.\n\n"
            "I'll identify social engineering patterns, urgency tactics, and impersonation signals.",
            reply_markup={"force_reply": True, "input_field_placeholder": "Paste message here…"},
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
        # --- International couriers / postal operators (added 2026-08-19) ---
        # A parcel-fee lure impersonates whatever carrier is local to the
        # victim. A US-only carrier list is why the SPL case scored zero.
        ("dhl", "DHL"), ("tnt", "TNT"), ("dpd", "DPD"), ("gls", "GLS"),
        ("aramex", "Aramex"), ("smsa", "SMSA Express"), ("naqel", "Naqel Express"),
        ("spl", "SPL (Saudi Post)"), ("saudi post", "Saudi Post"),
        ("emirates post", "Emirates Post"), ("qatar post", "Qatar Post"),
        ("royal mail", "Royal Mail"), ("evri", "Evri"), ("hermes", "Hermes"),
        ("yodel", "Yodel"), ("parcelforce", "Parcelforce"), ("an post", "An Post"),
        ("postnl", "PostNL"), ("poste italiane", "Poste Italiane"),
        ("correos", "Correos"), ("correios", "Correios"),
        ("la poste", "La Poste"), ("colissimo", "Colissimo"),
        ("chronopost", "Chronopost"), ("deutsche post", "Deutsche Post"),
        ("canada post", "Canada Post"), ("purolator", "Purolator"),
        ("australia post", "Australia Post"), ("auspost", "AusPost"),
        ("nz post", "NZ Post"), ("singpost", "SingPost"),
        ("pos malaysia", "Pos Malaysia"), ("j&t", "J&T Express"),
        ("sf express", "SF Express"), ("china post", "China Post"),
        ("cainiao", "Cainiao"), ("india post", "India Post"),
        ("blue dart", "Blue Dart"), ("bluedart", "Blue Dart"),
        ("delhivery", "Delhivery"), ("ptt kargo", "PTT Kargo"),
        # --- Non-US banks / payment rails ---
        ("hsbc", "HSBC"), ("barclays", "Barclays"), ("lloyds", "Lloyds"),
        ("natwest", "NatWest"), ("halifax", "Halifax"), ("monzo", "Monzo"),
        ("revolut", "Revolut"), ("santander", "Santander"), ("bbva", "BBVA"),
        ("caixabank", "CaixaBank"), ("deutsche bank", "Deutsche Bank"),
        ("rabobank", "Rabobank"), ("emirates nbd", "Emirates NBD"),
        ("al rajhi", "Al Rajhi Bank"), ("alrajhi", "Al Rajhi Bank"),
        ("saudi national bank", "Saudi National Bank"), ("riyad bank", "Riyad Bank"),
        ("qnb", "QNB"), ("adcb", "ADCB"), ("mashreq", "Mashreq"),
        ("interac", "Interac"), ("commonwealth bank", "Commonwealth Bank"),
        ("westpac", "Westpac"), ("anz", "ANZ"), ("icici", "ICICI"),
        ("hdfc", "HDFC"), ("paytm", "Paytm"), ("m-pesa", "M-Pesa"),
        ("mpesa", "M-Pesa"), ("nubank", "Nubank"),
        # --- Non-US carriers / telcos ---
        ("vodafone", "Vodafone"), ("stc", "STC"), ("mobily", "Mobily"),
        ("zain", "Zain"), ("etisalat", "Etisalat"), ("airtel", "Airtel"),
        ("jio", "Jio"), ("mtn", "MTN"), ("safaricom", "Safaricom"),
        ("telstra", "Telstra"), ("optus", "Optus"), ("telus", "Telus"),
        ("swisscom", "Swisscom"), ("movistar", "Movistar"), ("telcel", "Telcel"),
        # --- Non-US government / tax authorities ---
        ("hmrc", "HMRC"), ("dvla", "DVLA"), ("dwp", "DWP"), ("gov.uk", "GOV.UK"),
        ("service canada", "Service Canada"), ("absher", "Absher"),
        ("tawakkalna", "Tawakkalna"), ("nhs", "NHS"),
        # --- Non-US exchanges / wallets ---
        ("bybit", "Bybit"), ("okx", "OKX"), ("kucoin", "KuCoin"),
        ("bitfinex", "Bitfinex"), ("trust wallet", "Trust Wallet"),
        ("phantom", "Phantom"), ("trezor", "Trezor"),
    ]
    # Word-boundary match, not substring: substring matching silently produced
    # false positives ("ups" inside "groups"/"signups") and would have made the
    # short international tokens below ("spl", "dpd", "anz") unusable.
    matched_brands = []
    for _kw, _display in BRANDS:
        if re.search(r"(?<![a-z0-9])" + re.escape(_kw) + r"(?![a-z0-9])", content_lower):
            if _display not in matched_brands:
                matched_brands.append(_display)
    if matched_brands:
        flags.append(f"🚩 Brand impersonation: *{', '.join(matched_brands)}*")

    # Parcel / delivery-fee lure — added 2026-08-19 after a real miss reported
    # by Arjen: an OCR'd SPL (Saudi Post) "a handling fee is required to
    # complete the delivery" screenshot scored ZERO flags. Nothing above covers
    # the most common smishing shape worldwide, and the payment link sat behind
    # a "Pay for fees" button, so no URL was extractable from the image either.
    DELIVERY_CONTEXT = [
        "shipment", "parcel", "package", "delivery", "courier", "tracking",
        "consignment", "customs", "shipping", "postal", "post office",
        "pickup point", "collection point", "regional facility",
    ]
    FEE_DEMAND = [
        "handling fee", "customs fee", "customs duty", "customs charge",
        "delivery fee", "shipping fee", "service fee", "clearance fee",
        "import fee", "import duty", "unpaid fee", "outstanding fee",
        "small fee", "fee is required", "fee to complete", "pay for fees",
        "pay the fee", "pay this fee", "amount due", "payment is required",
        "payment required", "complete the delivery", "complete your delivery",
        "redelivery", "re-delivery", "reschedule your delivery",
        "reschedule the delivery", "view payment details", "unpaid shipping",
        "incomplete address", "address is incomplete",
    ]
    # Any currency, not just dollars — the missed message was priced in SAR.
    CURRENCY_AMOUNT = re.compile(
        r"(?:(?:sar|aed|qar|kwd|bhd|omr|jod|egp|usd|eur|gbp|cad|aud|nzd|chf|sek|nok"
        r"|dkk|pln|try|inr|pkr|bdt|lkr|ngn|kes|zar|ghs|mad|dzd|tnd|myr|sgd|thb|php"
        r"|idr|vnd|jpy|cny|krw|brl|mxn|ars|clp|cop)\s?\d|[$\u20ac\u00a3\u00a5\u20b9\u20a6\u20ba\u20a9\u20aa\u20b1\u0e3f]\s?\d)",
        re.IGNORECASE,
    )
    delivery_hits = [p for p in DELIVERY_CONTEXT if p in content_lower]
    fee_hits = [p for p in FEE_DEMAND if p in content_lower]
    money_hit = bool(CURRENCY_AMOUNT.search(content))
    fee_lure = bool(fee_hits or (delivery_hits and money_hit))
    if fee_lure:
        detail = fee_hits[0] if fee_hits else delivery_hits[0]
        flags.append(
            f"🚩 Parcel/delivery fee lure: *'{detail}'* — a delivery notice that asks "
            "for a payment is the most-copied scam template in the world. Real couriers "
            "collect customs or handling charges through their own app or at the door, "
            "never through a link in an unexpected message. Track the parcel yourself "
            "from the carrier's official site using a number you already had."
        )

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

    # Personal/nostalgic bait (hijacked-contact or romance-scam lure) — added
    # 2026-07-22, same real-world case as the WhatsApp fix: a spoofed display
    # name + fresh-looking domain + "pics you might remember" + link scored
    # zero flags under every category above, since none of them cover this
    # shape of scam (a stranger or hijacked contact posing as someone
    # familiar, not corporate/brand impersonation).
    BAIT_PHRASES = [
        "pics you might remember", "photos you might remember",
        "thought you'd want to see", "thought you would want to see",
        "check this out", "look what i found", "you might remember",
        "take a look at these", "remember this one", "remember these",
    ]
    bait_hits = [p for p in BAIT_PHRASES if p in content_lower]
    if bait_hits:
        flags.append(
            f"🚩 Personal/nostalgic bait: *'{bait_hits[0]}'* paired with a link — "
            "a hijacked-contact or romance-scam pattern, not just corporate impersonation"
        )

    # Sender display-name / email-domain mismatch — added 2026-07-22. Only
    # fires when the pasted/OCR'd text includes a "From:" header, the common
    # case for a forwarded/screenshotted email. A personal-looking display
    # name paired with an unrelated domain is the single strongest signal in
    # the case that prompted this fix, and nothing above checked for it.
    sender_match = re.search(
        r'from:\s*"?([^"<\n]{2,60}?)"?\s*<([^<>\s]+@[^<>\s]+)>',
        content, re.IGNORECASE,
    )
    if sender_match:
        display_name = sender_match.group(1).strip().strip("'\"")
        sender_email = sender_match.group(2).strip().lower()
        sender_domain = sender_email.split("@")[-1] if "@" in sender_email else ""
        KNOWN_WEBMAIL = {
            "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
            "aol.com", "live.com", "msn.com", "me.com", "protonmail.com",
        }
        name_tokens = [tok.lower() for tok in re.findall(r"[a-zA-Z]+", display_name) if len(tok) > 1]
        is_brand_name = any(display in display_name for display in matched_brands)
        name_in_domain = bool(name_tokens) and any(tok in sender_domain for tok in name_tokens)
        if (
            sender_domain
            and name_tokens
            and not is_brand_name
            and sender_domain not in KNOWN_WEBMAIL
            and not name_in_domain
        ):
            flags.append(
                f"🚩 Sender mismatch: display name *\"{display_name}\"* does not match the "
                f"actual email address *{sender_email}* — a classic spoofed-sender or "
                "hijacked-account pattern, especially if you know a real person by that name"
            )

    # Suspicious link — checked automatically via the same multi-signal
    # heuristic used by /scan (IOC corpus + Google Safe Browsing + domain
    # registration age), not just flagged for the user to verify manually.
    # Changed 2026-07-22: previously this only added a "verify yourself with
    # /scan" note and never actually checked the link, which is exactly how
    # a same-day-registered phishing domain got a false-reassuring result.
    found_urls = re.findall(r"https?://\S+", content)
    link_flagged = False
    checked_clean_note = ""
    for url in found_urls:
        url = url.rstrip(".,;:!?)")
        try:
            result = _heuristic_url_check(url)
        except Exception as exc:
            logger.warning("MSGSCAN heuristic URL check failed url=%s: %s", url, exc)
            result = {"flagged": False, "reasons": []}
        if result["flagged"]:
            link_flagged = True
            flags.append(f"🚩 Link {url} flagged — {'; '.join(result['reasons'])}")
    if found_urls and not link_flagged:
        checked_clean_note = (
            f"\nChecked {len(found_urls)} link(s) — none matched a known threat, but a clean "
            "result never guarantees safety; new phishing domains can take hours to appear "
            "in any threat database.\n"
        )

    # A screenshot hides its links: "Pay for fees" is a button whose URL lives
    # in the message's markup, not in the pixels, so OCR never sees it and the
    # link check below has nothing to check. Say so rather than letting the
    # result read as an all-clear.
    image_note = (
        "\n\U0001F5BC *Read from an image.* Buttons like *Pay* or *View details* keep "
        "their real link inside the message, not in the picture, so I could not check "
        "where they lead. Forward the original message, or send me the link with "
        "`/scan <link>`, for an actual link check.\n"
    ) if from_image else ""

    severity = "HIGH" if (len(flags) >= 3 or link_flagged or fee_lure) else "MEDIUM" if flags else "LOW"
    icon = "🚨" if severity == "HIGH" else "⚠️" if severity == "MEDIUM" else "✅"

    fwd_block = f"{forward_note}\n\n———\n\n" if forward_note else ""

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
            f"{fwd_block}"
            f"🧠 *Message Analysis — {severity} RISK*\n\n"
            f"{icon} *{len(flags)} social engineering signal(s) detected:*\n{flag_text}\n"
            f"{callback_warn}"
            f"{checked_clean_note}"
            f"{image_note}\n"
            f"*Recommended action:* Do not click, reply, or call any number in this message. "
            f"If this claims to be from a company, contact them directly via their official website.\n\n"
            f"Reply /vishing for a full guide on phone-based scam tactics.",
            parse_mode="Markdown",
        )
    else:
        send_message(
            chat_id,
            f"{fwd_block}"
            "🧠 *Message Analysis*\n\n"
            "✅ No automatic red flags detected in the text.\n"
            f"{checked_clean_note}"
            f"{image_note}\n"
            "This doesn't guarantee the message is safe — always verify unexpected requests "
            "by calling back on a number you look up yourself. And no dollar signs doesn't "
            "mean it's genuine — a stranger building rapport fast or pushing to move platforms "
            "is a manipulation pattern too. If you don't know them, consider blocking.",
            parse_mode="Markdown",
        )


# ---------------------------------------------------------------------------
# RESTORED 2026-08-26 from main. These came from 9239e1c "restore merged
# command hubs" and 810d9e0 "route pasted messages and bare screenshots to
# the fraud analyser", both committed 2026-08-20, and neither reached the
# deployed package. The hubs were destroyed once already on 2026-08-19 by a
# hand deploy; 9239e1c put them back in git, and the live artifact lost them
# a second time. Restoring them here is the whole reason the reconciliation
# runs both directions rather than trusting whichever side is newer.
# ---------------------------------------------------------------------------
_MESSAGE_MIN_LEN = 40


def _looks_like_message(raw: str) -> bool:
    raw = (raw or "").strip()
    if not raw:
        return False
    return bool(re.search(r"\s", raw)) or len(raw) >= _MESSAGE_MIN_LEN


def msg_infostealer_hub() -> str:
    return (
        "🕵️ *Infostealer Check*\n\n"
        "Infostealer malware scrapes saved passwords, cookies and session tokens off a "
        "device and sells them. Two things worth checking:\n\n"
        "• *Your email* — whether credentials tied to it are already in stealer logs\n"
        "• *Your browser extensions* — the most common way the malware gets on the device\n\n"
        "Pick one below, or send `/infostealer you@example.com` directly."
    )


def infostealer_hub_keyboard() -> dict:
    return {"inline_keyboard": [
        [{"text": "📧 Check an email address", "callback_data": "stealhub_email"}],
        [{"text": "🧩 Audit browser extensions", "callback_data": "stealhub_extensions"}],
    ]}


def scam_hub_keyboard() -> dict:
    return {"inline_keyboard": [
        [{"text": "🤖 Check a bot or channel",   "callback_data": "scamhub_botcheck"}],
        [{"text": "✅ Is this the real RelayShield?", "callback_data": "scamhub_verifybot"}],
    ]}


def handle_wascam(chat_id: int, reply_markup: dict | None = None) -> None:
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
    # /vishing merged in here 2026-08-11. This command already said "message,
    # bot, or call", so a user with a suspicious CALL had two commands and no
    # way to choose between them. /vishing still works as a hidden alias.
    # Sent as a second message: the combined body would otherwise approach
    # Telegram's 4,096 character limit per message.
    send_message(
        chat_id,
        "📞 *If it's a phone call*\n\n"
        "The caller impersonates a bank, government agency, carrier or tech support. "
        "They may already know your name, address, or the last four digits of a card, "
        "and they use that to build trust. Urgency is the weapon, not the deadline.\n\n"
        "*Signs it's an attack in progress:*\n"
        "• Unsolicited, urgent, or threatening: account suspended, payment overdue, act within 24 hours\n"
        "• Asked to read back a code you just received. That code was triggered by the caller\n"
        "• Pressure to stay on the line, not hang up, or keep the call confidential\n"
        "• Payment by gift card, wire, crypto, or a 'secure account'\n"
        "• Transferred to a 'supervisor' or 'fraud specialist' who raises the pressure\n\n"
        "*Do:*\n"
        "→ Hang up. Call back on the number from the company's website or the back of your card, "
        "never a number the caller gave you\n"
        "→ Tell someone else before you act\n"
        "→ Report it: reportfraud.ftc.gov or fcc.gov/consumers\n\n"
        "*Don't:*\n"
        "→ Read back any OTP or verification code. No legitimate company needs one\n"
        "→ Allow remote access to your device, under any circumstances\n"
        "→ Confirm or correct personal details the caller already seems to know\n\n"
        "*After a suspected call:* run /sweep, which now also signs you out of "
        "hijacked sessions, then /verify to set your callback rule and safe word.",
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


def handle_infostealer_check(chat_id: int, email_raw: str | None, user: dict) -> None:
    """
    /infostealer <email> — Check if credentials tied to an email were stolen by malware.
    Checks your own email to see if your device was compromised, or a sender's email
    to see if their account may have been hijacked.
    Available to all tiers.
    """
    email = (email_raw or "").strip().lower()
    if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        send_message(
            chat_id,
            f"🦠 *{INFOSTEALER_PROMPT_MARKER}*\n\n"
            "Infostealer malware infects a device and silently exfiltrates *everything* the "
            "browser knows — saved passwords for every site, active session cookies (bypassing 2FA), "
            "credit card autofill, and crypto wallet keys.\n\n"
            "Reply to this message with an email address — your own, to see if your device has "
            "been compromised, or a suspicious sender's, to see if their account may have been hijacked.",
            reply_markup={"force_reply": True, "input_field_placeholder": "you@example.com"},
            parse_mode="Markdown",
        )
        return

    send_message(chat_id, f"🔍 Checking `{email}` for infostealer exposure...", parse_mode="Markdown")

    encoded = urllib.parse.quote(email, safe="")
    url = f"https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-login?email={encoded}"
    req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        stealers = data.get("stealers", [])
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            stealers = []
        else:
            logger.error("Cavalier API error: %s", exc)
            send_message(chat_id, "⚠️ Infostealer check is temporarily unavailable. Please try again later.")
            return
    except Exception as exc:
        logger.error("Cavalier API error: %s", exc)
        send_message(chat_id, "⚠️ Infostealer check is temporarily unavailable. Please try again later.")
        return

    if not stealers:
        send_message(
            chat_id,
            f"✅ *{email}* was not found in any infostealer logs.\n\n"
            "Infostealer malware silently exfiltrates everything a browser holds — "
            "saved passwords for every site, active session cookies (bypassing 2FA), "
            "credit card autofill, and crypto wallet keys. A clean result here means "
            "no known infections were detected for this email.\n\n"
            "*As a precaution:*\n"
            "→ Audit browser extensions: /extensions\n"
            "→ Review active sessions: /sessions\n"
            "→ Check for email backdoors: /sweep",
            parse_mode="Markdown",
        )
        return

    count = len(stealers)
    lines = [f"🦠 *{email}* found in *{count}* infostealer log{'s' if count != 1 else ''}:\n"]
    for s in stealers[:3]:
        date  = s.get("date_compromised", "unknown date")
        os_   = s.get("operating_system", "unknown OS")
        corp  = s.get("total_corporate_services", 0)
        user_ = s.get("total_user_services", 0)
        lines.append(
            f"• *{date}* — {os_}\n"
            f"  {corp} work + {user_} personal site credentials exfiltrated"
        )
    if count > 3:
        lines.append(f"\n…and {count - 3} more infection{'s' if count - 3 != 1 else ''}.")

    lines.append(
        "\n\n*What was stolen:*\n"
        "Infostealer malware silently exfiltrates everything the browser holds — saved passwords "
        "for every site, active session cookies (bypassing 2FA without needing a password), "
        "credit card autofill, and crypto wallet keys.\n\n"
        "*Step 1 — Isolate the infected device now:*\n"
        "→ Disconnect it from Wi-Fi and unplug ethernet\n"
        "→ Do NOT log into any accounts on it until it is cleaned\n\n"
        "*Step 2 — From a different clean device:*\n"
        "→ Change all passwords — email, banking, social, crypto\n"
        "→ Revoke all active sessions: /sessions\n"
        "→ Close email backdoors: /sweep\n"
        "→ Enable 2FA on every account\n\n"
        "*Step 3 — Clean the infected device:*\n"
        "→ Download Malwarebytes Free (malwarebytes.com) on a USB from a clean device\n"
        "→ Run a full scan and remove everything flagged\n"
        "→ For a severe infection, a full OS reinstall is the safest option\n\n"
        "*Step 4 — After cleaning:*\n"
        "→ Update your OS and all software\n"
        "→ Audit browser extensions: /extensions\n"
        "→ Reconnect to the internet\n\n"
        "🛡️ _RelayShield_"
    )

    send_message(chat_id, "\n".join(lines), parse_mode="Markdown")
    logger.info("infostealer-check chat_id=%s email=%s count=%d", _hash_id(chat_id), _hash_id(email), count)


def handle_plan(chat_id: int, user: dict) -> None:
    """Show license type + feature-led upgrade nudge. Available to all tiers."""
    tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)
    plan_label = PLAN_PRICES.get(tier, {}).get("label") or (
        "Free Tier" if tier == TIER_FREE else tier.replace("_", " ").title()
    )
    _upgrade_nudges = {
        TIER_FREE:           "💡 *Unlock Crypto Shield* — wallet monitoring, SIM swap detection, breach remediation + infostealer alerts → crypto.relayshield.net",
        TIER_PERSONAL:       "💡 *Add team coverage* — share breach alerts, SIM monitoring, and incident response across your whole team → relayshield.net",
        TIER_STARTER_DOMAIN: "💡 *Add team seats* — Business Starter extends breach, SIM, and domain monitoring to every member of your team → relayshield.net",
        TIER_STARTER:        "💡 *Growing your team?* — Business Basic covers up to 5 seats with per-member SIM swap and breach monitoring → relayshield.net",
    }
    nudge = _upgrade_nudges.get(tier, "")
    text = f"🪪 *License Type:* {plan_label}"
    if nudge:
        text += f"\n\n{nudge}"
    send_message(chat_id, text, parse_mode="Markdown")


def handle_status(chat_id: int, user: dict) -> None:
    tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)
    emails = user.get("monitored_emails", [])
    channels = user.get("delivery_channels", ["telegram"])
    is_business = tier in BUSINESS_TIERS
    seat_limit = SEAT_LIMITS.get(tier, 1)

    text = (
        f"📊 *Account Status*\n\n"
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
    """Generate a one-time invite code for a new team member. Supports delegates."""
    is_admin   = user.get("is_team_admin", False)
    is_del     = _is_delegate(user)
    if not is_admin and not is_del:
        send_message(chat_id, "🔒 Only the account admin or a delegated admin can add team members.")
        return

    admin_id   = _effective_admin_id(user)
    admin_user = user if is_admin else (get_user_record(admin_id) or user)
    tier       = admin_user.get("tier") or admin_user.get("subscription_tier", TIER_PERSONAL)

    if tier not in BUSINESS_TIERS:
        send_message(chat_id, "Team management is available on Business plans. Upgrade at relayshield.net.")
        return

    seat_limit = SEAT_LIMITS.get(tier, 1)
    members    = get_team_members(admin_id)
    seats_used = len(members) + 1  # +1 for admin

    if seats_used >= seat_limit:
        send_message(
            chat_id,
            f"👥 You've reached your seat limit ({seat_limit} seats on your current plan).\n\n"
            "To add more members, upgrade your plan at relayshield.net or contact relayshieldadmin@gmail.com.",
            parse_mode="Markdown",
        )
        return

    code   = generate_invite_code()
    expiry = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

    # Invite code always stored on the main admin's record
    update_user(admin_id, {
        "is_team_admin": True,
        "team_id": admin_id,
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
    """List team members for removal selection. Supports delegates."""
    if not user.get("is_team_admin") and not _is_delegate(user):
        send_message(chat_id, "🔒 Only the account admin or a delegated admin can remove team members.")
        return

    admin_id = _effective_admin_id(user)
    admin_user = user if user.get("is_team_admin") else (get_user_record(admin_id) or user)
    tier = admin_user.get("tier") or admin_user.get("subscription_tier", TIER_PERSONAL)
    if tier not in BUSINESS_TIERS:
        send_message(chat_id, "Team management is available on Business plans.")
        return

    members = get_team_members(admin_id)
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


def handle_teamstatus(chat_id: int, user: dict) -> None:
    """Return a per-seat security health summary — Business admin and delegates."""
    if not user.get("is_team_admin") and not _is_delegate(user):
        send_message(
            chat_id,
            "🔒 /teamstatus is only available to the account admin or a delegated admin.\n\n"
            "Contact your admin to check team security status.",
        )
        return

    admin_id   = _effective_admin_id(user)
    admin_user = user if user.get("is_team_admin") else (get_user_record(admin_id) or user)
    tier       = admin_user.get("tier") or admin_user.get("subscription_tier", TIER_PERSONAL)

    if tier not in BUSINESS_TIERS:
        send_message(
            chat_id,
            "👥 /teamstatus is available on Business plans.\n\n"
            "Upgrade at relayshield.net to unlock team management.",
        )
        return

    members = get_team_members(admin_id)
    seat_limit = SEAT_LIMITS.get(tier, 2)
    seats_used = len(members) + 1  # +1 for admin
    tier_label = PLAN_PRICES.get(tier, {}).get("label", tier.replace("_", " ").title())

    # Build rows — admin first, then team members
    all_seats = [{"record": admin_user, "is_admin": True}] + [
        {"record": m, "is_admin": False} for m in members
    ]

    seats_needing_attention = 0
    seat_lines = []

    for seat in all_seats:
        rec = seat["record"]
        name = rec.get("first_name", "Unknown")
        role_tag = " _(Admin)_" if seat["is_admin"] else ""

        sim_ok      = bool(rec.get("phone_encrypted"))
        email_count = len(rec.get("monitored_emails") or [])
        breach_count = get_breach_alert_count(rec["user_id"])

        sim_icon    = "✅" if sim_ok else "⚠️"
        email_icon  = "✅" if email_count else "⚠️"
        breach_text = f"⚠️ {breach_count}" if breach_count else "✅ 0"

        if not sim_ok or not email_count:
            seats_needing_attention += 1

        seat_lines.append(
            f"👤 *{name}*{role_tag}\n"
            f"  SIM {sim_icon}  |  Emails: {email_count} {email_icon}  |  Breaches: {breach_text}"
        )

    divider = "─" * 26
    text = (
        f"🏢 *Team Security Status*\n"
        f"{tier_label} · {seats_used} of {seat_limit} seats active\n"
        f"{divider}\n\n"
        + "\n\n".join(seat_lines)
        + f"\n\n{divider}\n"
    )

    if seats_needing_attention:
        text += (
            f"⚠️ *{seats_needing_attention} seat(s) need attention* — "
            "SIM monitoring unset or no emails enrolled."
        )
    else:
        text += "✅ *All seats healthy.*"

    seats_remaining = seat_limit - seats_used
    if seats_remaining > 0:
        text += f"\n💺 {seats_remaining} seat(s) available — use /addmember to invite."

    send_message(chat_id, text, parse_mode="Markdown")


def handle_delegate(chat_id: int, user: dict) -> None:
    """Admin-only: grant a team member delegated admin access (addmember/removemember/teamstatus)."""
    if not user.get("is_team_admin"):
        send_message(chat_id, "🔒 Only the account admin can grant delegate access.")
        return

    members   = get_team_members(user["user_id"])
    delegated = user.get("delegated_admin_ids", [])
    eligible  = [m for m in members if m["user_id"] not in delegated]

    if not members:
        send_message(chat_id, "No team members enrolled yet. Use /addmember to invite someone first.")
        return
    if not eligible:
        send_message(
            chat_id,
            "All team members already have delegate access.\n\nUse /revoke to remove access from someone.",
        )
        return

    lines = []
    member_ids = []
    for i, m in enumerate(eligible, 1):
        name = m.get("employee_name") or m.get("first_name", "Unknown")
        lines.append(f"{i}. *{name}*")
        member_ids.append(m["user_id"])

    update_user(user["user_id"], {
        "onboarding_state":    "AWAITING_DELEGATE_SELECT",
        "pending_delegate_list": member_ids,
    })
    send_message(
        chat_id,
        "🔑 *Grant Delegate Access*\n\n"
        "Select a team member to grant admin access.\n"
        "Delegates can: /addmember, /removemember, /teamstatus\n\n"
        + "\n".join(lines)
        + "\n\nReply with the number, or `cancel` to go back:",
        parse_mode="Markdown",
    )


def handle_revoke(chat_id: int, user: dict) -> None:
    """Admin-only: revoke delegated admin access from a team member."""
    if not user.get("is_team_admin"):
        send_message(chat_id, "🔒 Only the account admin can revoke delegate access.")
        return

    delegated = user.get("delegated_admin_ids", [])
    if not delegated:
        send_message(chat_id, "No delegates currently set.\n\nUse /delegate to grant access to a team member.")
        return

    lines     = []
    valid_ids = []
    for uid in delegated:
        record = get_user_record(uid)
        if record and record.get("active"):
            name = record.get("employee_name") or record.get("first_name", "Unknown")
            lines.append(f"{len(valid_ids) + 1}. *{name}*")
            valid_ids.append(uid)

    if not valid_ids:
        update_user(user["user_id"], {"delegated_admin_ids": []})
        send_message(chat_id, "No active delegates found. Delegate list has been cleared.")
        return

    update_user(user["user_id"], {
        "onboarding_state":   "AWAITING_REVOKE_SELECT",
        "pending_revoke_list": valid_ids,
    })
    send_message(
        chat_id,
        "🔒 *Revoke Delegate Access*\n\n"
        "Select a delegate to remove:\n\n"
        + "\n".join(lines)
        + "\n\nReply with the number, or `cancel` to go back:",
        parse_mode="Markdown",
    )


def handle_setdomain(chat_id: int, domain_arg: str | None, user: dict) -> None:
    """Set the shared company domain for team-wide lookalike monitoring — admin only."""
    tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)

    if tier not in {TIER_BASIC, TIER_SHIELD, TIER_PRO}:
        send_message(
            chat_id,
            "🏢 */setdomain* is available on Business Basic and above.\n\n"
            "Business Basic ($89.99/mo) includes shared company domain monitoring — "
            "lookalike alerts delivered to you and all team seats the moment an attacker "
            "registers a domain designed to impersonate your company.\n\n"
            "Upgrade at relayshield.net.",
            parse_mode="Markdown",
        )
        return

    if not user.get("is_team_admin"):
        send_message(
            chat_id,
            "🔒 /setdomain is only available to the account admin.",
        )
        return

    if not domain_arg:
        current = user.get("company_domain")
        if current:
            send_message(
                chat_id,
                f"🏢 *Company Domain Monitoring*\n\n"
                f"Currently monitoring: `{current}`\n\n"
                f"To change it: `/setdomain yourdomain.com`\n"
                f"To remove it: `/setdomain remove`",
                parse_mode="Markdown",
            )
        else:
            send_message(
                chat_id,
                "🏢 *Company Domain Monitoring*\n\n"
                "No company domain set.\n\n"
                "Set one with: `/setdomain yourdomain.com`\n\n"
                "RelayShield will monitor for lookalike domains (typosquatting, phishing "
                "impersonation) and alert your entire team if an attacker registers a "
                "domain designed to impersonate your company.",
                parse_mode="Markdown",
            )
        return

    domain = domain_arg.strip().lower()

    if domain == "remove":
        update_user(user["user_id"], {"company_domain": None})
        send_message(chat_id, "✅ Company domain monitoring removed.")
        return

    domain = re.sub(r"^https?://", "", domain)
    domain = re.sub(r"^www\.", "", domain)
    domain = domain.split("/")[0]

    if not re.match(r"^[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?(\.[a-z]{2,})+$", domain):
        send_message(
            chat_id,
            "⚠️ That doesn't look like a valid domain. Use the format: `yourdomain.com`",
            parse_mode="Markdown",
        )
        return

    update_user(user["user_id"], {"company_domain": domain})

    members = get_team_members(user["user_id"])
    seat_count = len(members) + 1

    send_message(
        chat_id,
        f"✅ *Company domain set: `{domain}`*\n\n"
        f"RelayShield will monitor `{domain}` for lookalike domains — typosquatting and "
        f"phishing impersonation attempts.\n\n"
        f"Alerts will be delivered to you and all {seat_count} team seat(s) if an attacker "
        f"registers a domain designed to impersonate your company.\n\n"
        f"🛡️ RelayShield",
        parse_mode="Markdown",
    )


# LLM/AI provider key patterns for LLMjacking detection (added 2026-07-26) —
# deliberately a small, curated duplicate of the CRITICAL-severity subset of
# relayshield_api.py's NHI_PATTERNS, not an import. Each Lambda in this
# codebase is self-contained by design (separate deployment zips, no shared
# module), and this list is small and stable enough (well-documented provider
# key formats) that the duplication risk is low and matches the established
# pattern the rest of this file already uses for its own checks.
import re as _llm_re

_LLM_KEY_PATTERNS = [
    ("openai",    _llm_re.compile(r"sk-[a-zA-Z0-9]{48}"),             "OpenAI"),
    ("anthropic", _llm_re.compile(r"sk-ant-[a-zA-Z0-9\-]{90,}"),      "Anthropic"),
    ("google",    _llm_re.compile(r"AIza[0-9A-Za-z\-_]{35}"),         "Google AI (Gemini)"),
    ("groq",      _llm_re.compile(r"gsk_[a-zA-Z0-9]{52}"),            "Groq"),
    ("xai",       _llm_re.compile(r"xai-[a-zA-Z0-9]{80}"),            "xAI (Grok)"),
    ("replicate", _llm_re.compile(r"r8_[a-zA-Z0-9]{37}"),             "Replicate"),
]


def handle_checkllm(chat_id: int, user: dict) -> None:
    """Check the account's set company domain for exposed LLM/AI provider API
    keys (LLMjacking) in RelayShield's stealer-log corpus — a live, uncapped
    billing liability, not just a data exposure. Business Basic and above,
    reuses the same company_domain set via /setdomain."""
    tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)

    if tier not in {TIER_BASIC, TIER_SHIELD, TIER_PRO}:
        send_message(
            chat_id,
            "🤖 */checkllm* is available on Business Basic and above.\n\n"
            "Checks your company domain for exposed OpenAI/Anthropic/Google/Groq/xAI/Replicate "
            "API keys in criminal stealer logs — a leaked key is a live, uncapped billing "
            "liability, not just a data exposure. Real incidents have run from tens of "
            "thousands of dollars per day to a $500K single-month bill from one unthrottled key.\n\n"
            "Upgrade at relayshield.net.",
            parse_mode="Markdown",
        )
        return

    domain = user.get("company_domain")
    if not domain:
        send_message(
            chat_id,
            "🤖 No company domain set yet.\n\n"
            "Set one first with `/setdomain yourdomain.com`, then run /checkllm again.",
            parse_mode="Markdown",
        )
        return

    send_message(chat_id, f"🤖 Checking `{domain}` for exposed LLM/AI provider API keys...", parse_mode="Markdown")

    findings = []
    try:
        table = dynamodb.Table("relayshield_stolen_sessions")
        resp  = table.scan(
            FilterExpression=(
                boto3.dynamodb.conditions.Attr("session_type").eq("credential") &
                boto3.dynamodb.conditions.Attr("domain").contains(domain)
            ),
        )
        items = resp.get("Items", [])
    except Exception:
        items = []

    seen = set()
    for item in items:
        text = item.get("domain", "")
        for slug, pattern, label in _LLM_KEY_PATTERNS:
            for match in pattern.finditer(text):
                key = (slug, match.group(0)[:16])
                if key not in seen:
                    seen.add(key)
                    findings.append(label)

    if not findings:
        send_message(
            chat_id,
            f"✅ No exposed LLM/AI provider API keys found for `{domain}`.\n\n"
            "This checks OpenAI, Anthropic, Google, Groq, xAI, and Replicate key formats "
            "specifically. An AWS key exposure (see infostealer checks) can also enable "
            "LLMjacking if it has Bedrock access — this check doesn't cover that route.",
            parse_mode="Markdown",
        )
        return

    providers = ", ".join(sorted(set(findings)))
    send_message(
        chat_id,
        f"🚨 *LLMjacking risk detected for `{domain}`*\n\n"
        f"Exposed provider key(s) found: *{providers}*\n\n"
        "This is a live, uncapped billing liability, not just a data exposure — rotate "
        "immediately and check your provider's usage dashboard for anomalous spend right now, "
        "don't wait for the invoice. Real incidents have run from tens of thousands of dollars "
        "per day to a $500K single-month bill from one unthrottled key.\n\n"
        "🛡️ RelayShield",
        parse_mode="Markdown",
    )


def handle_sim_status(chat_id: int, user: dict) -> None:
    """Live Twilio Lookup v2 carrier check on the user's registered phone number."""
    import base64 as _b64
    phone_enc = user.get("phone_encrypted")

    if not phone_enc:
        send_message(
            chat_id,
            "📡 *SIM Swap Monitoring — Not Active*\n\n"
            "Your phone number has not been enrolled.\n\n"
            "To activate monitoring, restart setup with /start or contact support at "
            "relayshieldadmin@gmail.com.\n\n"
            "🛡️ RelayShield",
            parse_mode="Markdown",
        )
        return

    send_message(chat_id, "📡 Checking your number at the carrier level…", parse_mode="Markdown")

    try:
        phone_e164 = decrypt_field(phone_enc)
    except Exception:
        send_message(chat_id, "⚠️ Unable to retrieve your phone number. Please contact support.", parse_mode="Markdown")
        return

    try:
        sid   = get_secret("relayshield/twilio_account_sid", "TWILIO_ACCOUNT_SID")
        token = get_secret("relayshield/twilio_auth_token",  "TWILIO_AUTH_TOKEN")
        creds = _b64.b64encode(f"{sid}:{token}".encode()).decode()
        url   = (
            "https://lookups.twilio.com/v2/PhoneNumbers/"
            + urllib.parse.quote(phone_e164, safe="")
            + "?Fields=sim_swap"
        )
        req = urllib.request.Request(url, headers={"Authorization": f"Basic {creds}", "Accept": "application/json"}, method="GET")
        with urllib.request.urlopen(req, timeout=15) as resp:
            body        = json.loads(resp.read())
            sim_obj     = body.get("sim_swap") or {}
            last_swap   = sim_obj.get("last_sim_swap") or {}
            swapped     = bool(last_swap.get("swapped_in_period", False))
            swap_ts     = last_swap.get("last_sim_swap_date", "")
            carrier     = sim_obj.get("carrier_name", "your carrier")
        lookup_ok = True
    except Exception:
        lookup_ok = False
        swapped   = False
        carrier   = ""

    if not lookup_ok:
        # Fixed 2026-08-10. This used to reply "SIM Swap Monitoring - Active"
        # and promise "ongoing monitoring is active and will alert you
        # immediately if a swap is detected". Both were false whenever the
        # lookup failed, and today the lookup ALWAYS fails: Twilio's SIM-swap
        # registration (#28883049) is still pending, so the API returns 60606
        # and /v1/metered/sim-swap 503s by design.
        #
        # That is not failing silently, it is failing reassuringly, which is
        # the dangerous version. A user reading the old text believed they were
        # covered against the exact attack they came here to avoid. Same defect
        # family as the sim-swap false-clean (162d31e) and the asset-intel
        # sweep, and worse than both because it made an affirmative promise of
        # protection rather than merely omitting a warning.
        send_message(
            chat_id,
            "📡 *SIM Swap Check — Could not complete*\n\n"
            "We could not reach your carrier to check for a SIM swap, so we "
            "cannot tell you either way right now. *Please do not read this as "
            "an all-clear.*\n\n"
            "If you have any reason to suspect a swap, contact your carrier's "
            "fraud line directly. Reply /phone for their numbers and for SIM "
            "lock hardening steps.\n\n"
            "🛡️ RelayShield",
            parse_mode="Markdown",
        )
    elif swapped:
        swap_time = f" at {swap_ts[:16].replace('T', ' ')} UTC" if swap_ts else ""
        send_message(
            chat_id,
            f"🚨 *SIM Swap Detected — IMMEDIATE ACTION REQUIRED*\n\n"
            f"A SIM swap or port event was recorded on your number{swap_time} via {carrier}.\n\n"
            "*Do this now:*\n"
            f"→ Call {carrier} fraud line and report an unauthorized SIM swap\n"
            "→ Ask them to reverse the swap and place a SIM lock / port freeze\n"
            "→ Change passwords on your bank, email, and any account that uses SMS 2FA\n\n"
            "Reply /phone for your carrier's exact fraud contact numbers.\n\n🛡️ RelayShield",
            parse_mode="Markdown",
        )
    else:
        carrier_display = f" on {carrier}" if carrier else ""
        send_message(
            chat_id,
            f"✅ *SIM Swap Monitoring — No swap detected*\n\n"
            f"Your number{carrier_display} shows no SIM swap or port activity in the last 24 hours.\n\n"
            "RelayShield monitors your number continuously — you'll receive an alert the moment "
            "any carrier-level change is detected, before the attacker can intercept your 2FA codes.\n\n"
            "Reply /phone for SIM lock hardening steps.\n\n🛡️ RelayShield",
            parse_mode="Markdown",
        )


def handle_breach_status(chat_id: int, user: dict) -> None:
    """Live HIBP breach check on all enrolled emails."""
    user_id  = user.get("user_id")
    tier     = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)
    me_table = dynamodb.Table(MONITORED_EMAILS_TABLE)

    try:
        response = me_table.scan(FilterExpression=Attr("user_id").eq(user_id))
        emails   = response.get("Items", [])
    except Exception:
        emails = []

    email_limit = EMAIL_LIMITS.get(tier, 3)

    if not emails:
        update_user(user["user_id"], {"onboarding_state": "AWAITING_BREACH_EMAIL"})
        send_message(
            chat_id,
            f"🔍 Breach Monitoring — No emails enrolled\n\n"
            f"You can monitor up to {email_limit} email addresses.\n\n"
            "Send an email address to start monitoring (e.g. you@example.com):\n\n"
            "Type 'cancel' to go back.",
        )
        return

    count = len(emails)
    send_message(chat_id, f"🔍 Checking {count} enrolled address{'es' if count != 1 else ''} for breach exposure…", parse_mode=None)

    try:
        hibp_api_key = get_secret(HIBP_SECRET_NAME, HIBP_SECRET_KEY)
    except Exception:
        hibp_api_key = None

    lines      = [f"🔍 Breach Monitoring — {count} email{'s' if count != 1 else ''} enrolled\n"]
    any_breach = False

    for item in emails:
        active       = item.get("active", True)
        status_icon  = "✅" if active else "⏸"
        enrolled_date = item.get("created_at", "")[:10]

        try:
            email_plain = decrypt_field(item["email_encrypted"])
        except Exception:
            email_plain = None

        if email_plain and hibp_api_key and active:
            try:
                encoded  = urllib.parse.quote(email_plain, safe="")
                hibp_url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{encoded}?truncateResponse=false"
                req = urllib.request.Request(hibp_url, headers={"hibp-api-key": hibp_api_key, "user-agent": "RelayShield/1.0"})
                with urllib.request.urlopen(req, timeout=12) as resp:
                    breaches = json.loads(resp.read())
            except urllib.error.HTTPError as exc:
                breaches = [] if exc.code == 404 else None
            except Exception:
                breaches = None

            at_idx = email_plain.index("@")
            masked = email_plain[0] + "***" + email_plain[at_idx:]

            if breaches is None:
                lines.append(f"{status_icon} {masked} — ⚠️ check unavailable (since {enrolled_date})")
            elif not breaches:
                lines.append(f"{status_icon} {masked} — ✅ No breaches found (since {enrolled_date})")
            else:
                any_breach = True
                bcount = len(breaches)
                recent = sorted(breaches, key=lambda b: b.get("BreachDate", ""), reverse=True)[:3]
                names  = ", ".join(b["Name"] for b in recent)
                if bcount > 3:
                    names += f" +{bcount - 3} more"
                lines.append(f"⚠️ {masked} — {bcount} breach{'es' if bcount != 1 else ''}: {names} (since {enrolled_date})")
        else:
            lines.append(f"{status_icon} (enrolled {enrolled_date})")

    lines.append("\nAlerts fire automatically when any address appears in a new breach.")
    if any_breach:
        lines.append("\nRecommended: /sweep to close email backdoors, /reuse to check password reuse.")
    remaining = max(0, email_limit - count)
    if remaining > 0:
        lines.append(f"\nSend an email address to add {remaining} more slot{'s' if remaining != 1 else ''}.")
    lines.append("🛡️ RelayShield")

    send_message(chat_id, "\n".join(lines), parse_mode=None)


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

    raw_state = user.get("domain_monitor_state") or "{}"
    try:
        import json as _json
        domain_state = _json.loads(raw_state) if isinstance(raw_state, str) else (raw_state or {})
    except Exception:
        domain_state = {}
    lines = []
    for d in domains:
        entry = domain_state.get(d, {})
        last_scanned = entry.get("last_scanned")
        scan_label = "Never scanned" if not last_scanned else last_scanned[:10]
        lookalikes = entry.get("known_lookalikes") or []
        if lookalikes:
            names = ", ".join(f"`{lk}`" for lk in lookalikes[:5])
            more  = f" +{len(lookalikes) - 5} more" if len(lookalikes) > 5 else ""
            lookalike_line = f"⚠️ {len(lookalikes)} lookalike domain{'s' if len(lookalikes) != 1 else ''}: {names}{more}"
        else:
            lookalike_line = "✅ No lookalike domains detected"
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

# Keys in a GoPlus address_security result that are "1"/non-empty but are NOT
# risk signals. Anything that enumerates the raw result looking for "1" must
# subtract this set, or it invents a risk flag out of a descriptor.
#
# `contract_address` means "this address is a contract", nothing more. Verified
# live 2026-08-14 against vitalik.eth, the USDC contract and a Tornado router:
# all three return contract_address=1 and no other non-zero key, so /addwallet
# told anyone monitoring a contract that it was MEDIUM risk.
#
# `data_source` is a provider credit string ("SlowMist,BlockSec"), so it never
# equals "1" and is listed here for documentation rather than for effect.
#
# The allowlist-driven checks in this file (RISK_FLAGS in the approvals scan,
# _malicious_fields in /riskcheck, the inline-mode tuple) never had the bug and
# do not need this set.
_ADDR_NON_RISK_KEYS = {"contract_address", "data_source"}


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
            f"👛 *{ADDWALLET_PROMPT_MARKER}*\n\n"
            "Reply to this message with a wallet address — EVM (`0x...`), Solana, or TON (`EQ...`).",
            reply_markup={"force_reply": True, "input_field_placeholder": "0xYourEVMAddress"},
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
        risk_flags = [k for k, v in risk.items()
                      if v == "1" and k not in _ADDR_NON_RISK_KEYS]
        # Sanctions alone forces HIGH. The count rule would grade a
        # sanctions-only hit as MEDIUM, and dealing with an OFAC-listed address
        # is a compliance event on the first flag, not the second. Matches
        # handle_wallet_risk in relayshield_api.py.
        risk_level = "HIGH" if risk.get("sanctioned") == "1" or len(risk_flags) >= 2 \
            else "MEDIUM" if risk_flags else "LOW"
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
            f"*{REMOVEWALLET_PROMPT_MARKER}*\n\n{lines}\n\n"
            "Reply to this message with the address to remove.",
            reply_markup={"force_reply": True, "input_field_placeholder": "Address to remove…"},
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
    Scan all EVM wallets for on-chain risk signals and surface revoke.cash
    deep-links so users can review and revoke token approvals.

    Uses GoPlus address_security (working public API) for risk flags.
    Revoke.cash is the authoritative source for enumerating approvals —
    we provide direct deep-links per chain.

    Note: TON and Bitcoin do not use the EVM token approval model.
    Their on-chain risk is covered by /riskcheck.
    """
    tier = user.get("subscription_tier") or user.get("tier", "")
    if tier not in CRYPTO_TIERS:
        send_message(
            chat_id,
            "🔒 *Token Approval Scanner* is a Crypto Shield feature.\n\n"
            "Upgrade at relayshield.net to monitor wallet approvals.",
        )
        return

    wallets = _get_user_wallets(user["user_id"], user)
    evm_wallets = [w for w in wallets if w.get("chain_type", "evm") == "evm"]

    if not evm_wallets:
        send_message(
            chat_id,
            "📭 *No EVM wallets found.*\n\n"
            "Add one with `/addwallet <0x...>` to scan for token approvals.\n\n"
            "ℹ️ TON and Bitcoin don't use the EVM approval model — "
            "use /riskcheck for on-chain risk on those chains.",
        )
        return

    # Chains: name, GoPlus chain_id, block explorer base URL
    CHAINS = [
        ("Ethereum", 1,     "https://etherscan.io/address/"),
        ("Base",     8453,  "https://basescan.org/address/"),
        ("Polygon",  137,   "https://polygonscan.com/address/"),
        ("Arbitrum", 42161, "https://arbiscan.io/address/"),
        ("BSC",      56,    "https://bscscan.com/address/"),
    ]

    # GoPlus risk flag keys that indicate active compromise
    RISK_FLAGS = [
        "cybercrime", "money_laundering", "phishing_activities",
        "stealing_attack", "blackmail_activities", "sanctioned",
        "darkweb_transactions", "gas_abuse", "financial_crime",
    ]

    wallet_count = len(evm_wallets)
    send_message(
        chat_id,
        f"🔍 *Scanning {wallet_count} EVM wallet(s) for approval risk...*\n"
        "_Ethereum · Base · Polygon · Arbitrum · BSC_"
    )

    for w in evm_wallets:
        address = w.get("wallet_address", "")
        short   = f"{address[:6]}...{address[-4:]}"
        lines   = [f"*🔓 Token Approvals — `{short}`*\n"]

        # GoPlus address_security check (Ethereum — most signal-rich chain)
        risk = _goplus_risk_check(address, chain_id=1)
        active_flags = [f for f in RISK_FLAGS if str(risk.get(f, "0")) != "0"]

        if active_flags:
            lines.append(
                "🚨 *GoPlus Risk Flags Detected:*\n" +
                "\n".join(f"   • {f.replace('_', ' ').title()}" for f in active_flags) +
                "\n⚠️ This wallet has known threat associations. Remove all token approvals immediately."
            )
        else:
            lines.append("✅ *No known risk flags on this address (GoPlus)*")

        # Per-chain block explorer links
        lines.append("\n*View wallet on each chain:*")
        for chain_name, _, explorer_base in CHAINS:
            lines.append(f"   • [{chain_name}]({explorer_base}{address})")

        lines.append(
            "\n_To remove token approvals, connect your wallet on the relevant chain explorer "
            "and remove any unlimited approvals from DeFi protocols you no longer use._"
        )

        send_message(chat_id, "\n".join(lines), parse_mode="Markdown")

    send_message(
        chat_id,
        "*What are token approvals?*\n"
        "When you use a DeFi app, you grant it permission to spend your tokens. "
        "Unlimited approvals let the contract drain your wallet at any time — "
        "even after you stop using the app.\n\n"
        "*Best practice:* Remove approvals for any protocol you no longer use. "
        "Each removal is a small on-chain transaction (~$0.10–$2 on Ethereum, less on L2s).",
        parse_mode="Markdown"
    )


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


def handle_stats(chat_id: int) -> None:
    """Admin-only command: show signup and conversion stats.
    Silently no-ops for non-admin chat IDs — command is invisible to users.
    """
    if chat_id != ADMIN_CHAT_ID:
        return

    try:
        table = dynamodb.Table(USERS_TABLE)

        # Full scan — table is small, this is fine
        raw: list[dict] = []
        resp = table.scan()
        raw.extend(resp.get("Items", []))
        while "LastEvaluatedKey" in resp:
            resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
            raw.extend(resp.get("Items", []))

        # Exclude test/beta records — user_ids with known test prefixes AND demo/internal accounts
        TEST_PREFIXES = ("beta-", "test-", "user-onboard-test", "onboard-test")
        items = [u for u in raw if not any(
            u.get("user_id", "").startswith(p) for p in TEST_PREFIXES
        ) and not u.get("is_demo") and not u.get("is_sales_agent")]
        excluded = len(raw) - len(items)

        now      = datetime.now(timezone.utc)
        week_ago = (now - timedelta(days=7)).isoformat()

        # Split into genuinely active paid, pending/trial, and free
        PAID_TIERS = {TIER_PERSONAL, TIER_STARTER, TIER_STARTER_DOMAIN,
                      TIER_BASIC, TIER_SHIELD, TIER_PRO, TIER_CRYPTO}

        active_paid   = [u for u in items if u.get("active") and u.get("tier") in PAID_TIERS]
        pending_users = [u for u in items if not u.get("active") and u.get("tier") in PAID_TIERS
                         and u.get("onboarding_state") == "AWAITING_PAYMENT"]
        free_users    = [u for u in items if u.get("tier") == "free" or u.get("tier") is None]
        active_count  = sum(1 for u in items if u.get("active"))

        total        = len(items)
        paid_count   = len(active_paid)
        pending_count = len(pending_users)
        free_count   = len(free_users)

        # Paid tier breakdown (active paid only)
        tier_counts: dict[str, int] = {}
        for u in active_paid:
            t = u.get("tier") or "unknown"
            tier_counts[t] = tier_counts.get(t, 0) + 1

        TIER_LABELS = {
            TIER_PERSONAL:       "Personal Shield",
            TIER_STARTER:        "Business Starter",
            TIER_STARTER_DOMAIN: "Starter + Domain",
            TIER_BASIC:          "Business Basic",
            TIER_SHIELD:         "Business Shield",
            TIER_PRO:            "Business Shield Pro",
            TIER_CRYPTO:         "Crypto Shield",
        }
        paid_lines = [
            f"  • {label}: {tier_counts[key]}"
            for key, label in TIER_LABELS.items()
            if tier_counts.get(key, 0) > 0
        ]
        paid_breakdown = "\n".join(paid_lines) if paid_lines else "  • (none yet)"

        # Pending/trial breakdown by tier
        pending_tier_counts: dict[str, int] = {}
        for u in pending_users:
            t = u.get("tier") or "unknown"
            pending_tier_counts[t] = pending_tier_counts.get(t, 0) + 1
        pending_lines = [
            f"  • {TIER_LABELS.get(k, k)}: {v}"
            for k, v in pending_tier_counts.items()
        ]
        pending_breakdown = "\n".join(pending_lines) if pending_lines else "  • (none)"

        week_signups = sum(1 for u in items if u.get("created_at", "") >= week_ago)
        conversions  = sum(1 for u in items if u.get("converted_from_free"))

        text = (
            f"📊 *RelayShield Stats*\n\n"
            f"👥 *Users* _(test/demo excluded: {excluded})_\n"
            f"  • Total: {total}\n"
            f"  • Active: {active_count}\n"
            f"  • Free tier: {free_count}\n"
            f"  • Paid (active): {paid_count}\n"
            f"  • Pending payment: {pending_count}\n\n"
            f"💳 *Paid breakdown*\n"
            f"{paid_breakdown}\n\n"
            f"⏳ *Pending / AWAITING\\_PAYMENT*\n"
            f"{pending_breakdown}\n\n"
            f"🔄 *Conversion*\n"
            f"  • Free → Paid: {conversions}\n\n"
            f"📅 *Signups this week*: {week_signups}\n\n"
            f"_RelayShield Admin_"
        )
        send_message(chat_id, text, parse_mode="Markdown")
        logger.info("stats — chat_id=%s total=%s free=%s paid=%s", chat_id, total, free_count, paid_count)
    except Exception as exc:
        logger.error("handle_stats error: %s", exc)
        send_message(chat_id, f"⚠️ Stats error: {exc}")


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
            f"🔍 *{CHECKVAULT_PROMPT_MARKER}*\n\n"
            "Reply to this message with a DeFi protocol URL (e.g. `app.aave.com`, `app.uniswap.org`, `curve.fi`).",
            reply_markup={"force_reply": True, "input_field_placeholder": "app.aave.com"},
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
    is_free = (tier == TIER_FREE)
    is_paid_crypto = (tier in CRYPTO_TIERS)

    # Fully blocked tiers (non-crypto paid plans) — keep hard gate
    if tier and tier not in CRYPTO_TIERS and tier != TIER_FREE:
        send_message(
            chat_id,
            "Token risk checks are available on the Crypto Shield plan.\n"
            "Contact relayshieldadmin@gmail.com to upgrade.",
        )
        return

    if not address_raw or not address_raw.startswith("0x") or len(address_raw) < 10:
        send_message(
            chat_id,
            f"🔍 *{CHECKTOKEN_PROMPT_MARKER}*\n\n"
            "Reply to this message with a token contract address (`0x...`).",
            reply_markup={"force_reply": True, "input_field_placeholder": "0xTokenContractAddress"},
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

    if is_free:
        # Free tier: show risk verdict only, gate full detail + remediation
        is_honeypot   = info.get("is_honeypot") == "1"
        is_scam       = info.get("is_airdrop_scam") == "1" or info.get("fake_token") == "1"
        try:
            sell_tax = float(info.get("sell_tax") or 0)
        except (ValueError, TypeError):
            sell_tax = 0.0
        is_high_tax   = sell_tax >= 50
        is_high_risk  = is_honeypot or is_scam or is_high_tax

        if is_high_risk:
            danger_label = (
                "HONEYPOT — you cannot sell this token" if is_honeypot else
                "AIRDROP SCAM / FAKE TOKEN" if is_scam else
                f"SELL TAX {sell_tax:.0f}% — effectively unsellable"
            )
            send_message(
                chat_id,
                f"🚨 *HIGH RISK TOKEN DETECTED*\n\n"
                f"*Contract:* `{address[:6]}...{address[-4:]}`\n"
                f"*Verdict:* {danger_label}\n\n"
                f"⛔ Do NOT swap, approve, or interact with this token.\n\n"
                f"_Crypto Shield subscribers get full risk detail — buy/sell tax breakdown, "
                f"owner privileges, hidden mint functions, and step-by-step safe disposal "
                f"instructions — plus automatic detection when risky tokens land in your wallet "
                f"before you even know they're there._\n\n"
                + CRYPTO_SHIELD_CTA,
                parse_mode="Markdown",
            )
        else:
            send_message(
                chat_id,
                f"✅ *No critical flags detected* for `{address[:6]}...{address[-4:]}`.\n\n"
                f"_Full risk detail — owner privileges, tax rates, hidden mint, contract audit — "
                f"is available on Crypto Shield. Continuous monitoring alerts you the moment "
                f"a token's risk profile changes after you hold it._\n\n"
                + CRYPTO_SHIELD_CTA,
                parse_mode="Markdown",
            )
        logger.info("checktoken free-tier — chat_id=%s address=%s high_risk=%s", chat_id, address, is_high_risk)
        return

    # Paid crypto tier — full result
    send_message(chat_id, _format_token_risk(address, info), parse_mode="Markdown")

    # Conversion prompt: if HIGH-risk found, reinforce the value of continuous monitoring
    is_honeypot  = info.get("is_honeypot") == "1"
    is_scam      = info.get("is_airdrop_scam") == "1" or info.get("fake_token") == "1"
    try:
        sell_tax = float(info.get("sell_tax") or 0)
    except (ValueError, TypeError):
        sell_tax = 0.0
    if is_honeypot or is_scam or sell_tax >= 50:
        send_message(
            chat_id,
            "☝️ *This is exactly what Crypto Shield catches automatically.*\n\n"
            "Every token that lands in your monitored wallets is screened in real time — "
            "honeypots, rug pulls, airdrop scams — before you interact with them. "
            "Share Crypto Shield with anyone who trades actively:\n\n"
            f"👉 crypto.relayshield.net",
        )
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
            f"🔍 *{CHECKNFT_PROMPT_MARKER}*\n\n"
            "Reply to this message with an NFT contract address (`0x...`).",
            reply_markup={"force_reply": True, "input_field_placeholder": "0xNFTContractAddress"},
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

    # STOPSIM / SIMSWAP. Added 2026-08-14: the onboarding completion message
    # told users "You can stop it at any time by sending STOPSIM" before the
    # command existed. Promising a control that does nothing is the same defect
    # class as claiming monitoring is on when it is not.
    if cmd in ("stopsim", "stop sim"):
        try:
            phone = decrypt_field(user["phone_encrypted"]) if user.get("phone_encrypted") else ""
            simswap_consent.withdraw(phone)
            send_message(
                chat_id,
                "SIM swap monitoring is now *off* for your number and we've stopped "
                "all carrier lookups for it.\n\nSend /simswap if you want it back on.",
                parse_mode="Markdown",
            )
        except LookupError:
            send_message(chat_id, "SIM swap monitoring isn't currently on. Send /simswap to enable it.")
        except Exception as exc:
            logger.error("telegram STOPSIM failed user=%s: %s", user.get("user_id"), exc)
            send_message(
                chat_id,
                "⚠️ We couldn't turn it off just now and we won't pretend we did. "
                "Email support@relayshield.net and we'll stop it manually.",
            )
        return

    if cmd in ("simswap", "sim swap"):
        update_user(user["user_id"], {"onboarding_state": "AWAITING_PHONE"})
        request_contact(
            chat_id,
            "To enable SIM swap monitoring, please share your phone number.\n\n"
            "We only ever monitor a number its own owner has shared with us.",
        )
        return

    # Bare address or link, no command. Handled FIRST, before the free-tier
    # gate below, because that gate keys on the first token: an address is not
    # in _FREE_ALLOWED, so a free user pasting one would be shown the upgrade
    # paywall instead of a result. Scanning is already free, so gating it here
    # would be wrong as well as hostile.
    #
    # Added 2026-08-10. Someone who has just seen an inline result in a group
    # and opened a DM will paste an address, not type /scan, and "I didn't
    # recognise that command" is the worst possible first impression for a bot
    # whose entire growth problem is strangers arriving.
    _bare = text.strip()
    if not _bare.startswith("/") and (
        _looks_like_wallet_address(_bare)
        or (_normalize_scan_url(_bare) and " " not in _bare)
    ):
        handle_scan_dispatch(chat_id, _bare, user)
        return

    # Free tier: allowlist — only awareness commands, no remediation tools
    tier = user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)
    if tier == TIER_FREE:
        # checktoken is allowed for free tier (teaser result — see handle_checktoken)
        # sweep is allowed for free tier (CTA appended in handle_sweep)
        # The msgscan/analyze/analyse aliases must be here too, or the free
        # tier silently breaks for anyone who learned the old command name.
        # /scan and its aliases all reach the same dispatcher.
        _FREE_ALLOWED = {"help", "verify", "otp", "scan", "msgscan", "analyze", "analyse",
                         "sweep", "checktoken", "plan", "license", "lictype",
                         # quickstart is orientation, not a remediation tool.
                         # Gating it would paywall the explanation of what the
                         # free tier can already do.
                         "quickstart"}
        base_cmd = cmd.split()[0] if cmd else ""
        if base_cmd not in _FREE_ALLOWED:
            send_message(
                chat_id,
                "🔒 This command requires a Crypto Shield subscription.\n\n"
                "Crypto Shield adds:\n"
                "→ Breach remediation + inbox sweep\n"
                "→ Infostealer malware detection\n"
                "→ SIM swap monitoring\n"
                "→ Wallet monitoring + counterparty screening\n\n"
                f"👉 [Upgrade — $19.99/month]({CRYPTO_MONTHLY_URL})",
            )
            return
        # Track free check usage — fire conversion prompt at check #10
        _maybe_send_check_milestone_prompt(chat_id, user)

    if cmd == "help":
        handle_help(chat_id, user)
    elif cmd in ("quickstart", "quick start", "start here"):
        # Deliberately separate from /help. /help answers "what commands are
        # there"; this answers "what do I do with the thing in my hand right
        # now", and its first line is the one action that needs no command at
        # all. Without it the forward handler is a feature nobody is told
        # about, which is the same as not having built it.
        send_message(chat_id, fwd.quickstart_text(fwd.PLATFORM_TELEGRAM))
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
    # /vishing is a hidden alias for /scam since the 2026-08-11 merge. It
    # routes to the SAME handler rather than the old standalone one, so the
    # phone-scam guidance has a single source of truth and cannot drift.
    elif cmd in ("wascam", "scam", "vishing"):
        handle_wascam(chat_id, reply_markup=scam_hub_keyboard())
    # /tgsecurity is the one visible Telegram-security command. linkeddevices,
    # botcheck, verifybot, legit and relayshield stay as hidden aliases so
    # existing muscle memory keeps working. Merged 2026-08-11.
    #   /tgsecurity            → hardening + linked devices + verify this bot
    #   /tgsecurity @somebot   → typosquat + red flag analysis of that bot
    elif cmd.startswith("tgsecurity") or cmd.startswith("botcheck"):
        parts = text.strip().split(None, 1)
        username = parts[1].lstrip("@") if len(parts) > 1 else None
        if username:
            handle_botcheck(chat_id, username)
        elif cmd.startswith("botcheck"):
            # Bare /botcheck kept its own general-guidance reply.
            handle_botcheck(chat_id, None)
        else:
            handle_tgsecurity(chat_id)
    elif cmd == "linkeddevices":
        handle_linkeddevices(chat_id)
    elif cmd in ("verifybot", "legit", "relayshield"):
        handle_verify_bot(chat_id)
    # /scan is the one visible command; msgscan, analyze and analyse stay as
    # hidden aliases so existing users' muscle memory keeps working. All four
    # go through the dispatcher, which picks the engine from the input.
    elif (cmd.startswith("scan") or cmd.startswith("msgscan")
          or cmd.startswith("analyze") or cmd.startswith("analyse")):
        parts = text.strip().split(None, 1)
        content = parts[1] if len(parts) > 1 else None
        handle_scan_dispatch(chat_id, content, user)
    # /sessions is a hidden alias for /sweep since the 2026-08-11 merge, and
    # routes to the same handler for the same reason.
    elif cmd == "sessions":
        handle_sweep(chat_id)
    elif cmd in ("plan", "license", "lictype"):
        handle_plan(chat_id, user)
    elif cmd in ("status", "account"):
        handle_status(chat_id, user)
    elif cmd == "addmember":
        handle_addmember(chat_id, user)
    elif cmd == "removemember":
        handle_removemember(chat_id, user)
    elif cmd == "delegate":
        handle_delegate(chat_id, user)
    elif cmd == "revoke":
        handle_revoke(chat_id, user)
    elif cmd == "teamstatus":
        handle_teamstatus(chat_id, user)
    elif cmd.startswith("setdomain"):
        domain_arg = text.split(maxsplit=1)[1].strip() if len(text.split()) > 1 else None
        handle_setdomain(chat_id, domain_arg, user)
    elif cmd == "checkllm":
        handle_checkllm(chat_id, user)
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
    elif cmd.startswith("infostealer"):
        parts = text.strip().split(None, 1)
        email = parts[1].strip() if len(parts) > 1 else None
        if email:
            # An address was supplied -- run it, exactly as before. The hub is
            # for the bare command only; making someone who already typed the
            # email tap a button would be a step backwards.
            handle_infostealer_check(chat_id, email, user)
        else:
            send_message(chat_id, msg_infostealer_hub(),
                         reply_markup=infostealer_hub_keyboard())
    elif cmd == "stats":
        handle_stats(chat_id)  # silently no-ops for non-admin
    else:
        # Bare addresses and links are already handled at the top of this
        # function, above the free-tier gate. Anything reaching here is neither.
        send_message(
            chat_id,
            "I didn't recognise that. Send me a wallet address or a link and "
            "I'll check it, or use /scan for a suspicious email or text.\n\n"
            "Type /help to see everything I can do.",
        )


# Maps each ForceReply prompt marker to the handler that should receive the
# replied-to text as its argument — see handle_message. handle_analyze takes
# no user param, so it's wrapped to match the common (chat_id, text, user) shape.
REPLY_PROMPT_HANDLERS = [
    # Must be the dispatcher, not handle_scan: the merged /scan prompt invites
    # "a link, a message, or a screenshot", so a reply is often prose. Routing
    # it straight to handle_scan would answer "That doesn't look like a URL".
    (SCAN_PROMPT_MARKER,         handle_scan_dispatch),
    (ANALYZE_PROMPT_MARKER,      lambda chat_id, text, user: handle_scan_dispatch(chat_id, text, user)),
    (INFOSTEALER_PROMPT_MARKER,  handle_infostealer_check),
    (CHECKVAULT_PROMPT_MARKER,   handle_checkvault),
    (CHECKTOKEN_PROMPT_MARKER,   handle_checktoken),
    (CHECKNFT_PROMPT_MARKER,     handle_checknft),
    (ADDWALLET_PROMPT_MARKER,    handle_addwallet),
    (REMOVEWALLET_PROMPT_MARKER, handle_removewallet),
]


# Every onboarding_state the chain in handle_message actually branches on.
# Kept next to nothing else on purpose: its ONLY job is to make an orphaned
# state loud in the logs instead of silently bricking an account. If you add a
# state to the chain, add it here; if this list goes stale the worst outcome is
# a spurious ERROR line, never a broken user.
_KNOWN_ONBOARDING_STATES = frozenset({
    "ACTIVE", "FREE_ACTIVE",
    "AWAITING_WALLET_CONFIRM", "AWAITING_WALLET_INPUT", "AWAITING_PHONE",
    "AWAITING_EMAIL_1", "AWAITING_MORE_EMAILS", "AWAITING_FREE_EMAIL",
    "AWAITING_REMOVE_SELECT", "AWAITING_DOMAIN_ADD", "AWAITING_BREACH_EMAIL",
    "AWAITING_DELEGATE_SELECT", "AWAITING_REVOKE_SELECT", "AWAITING_DOMAIN",
})


def handle_message(update: dict) -> None:
    message = update.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    text = message.get("text", "").strip()
    contact = message.get("contact")
    first_name = message.get("from", {}).get("first_name", "there")

    if not chat_id:
        return

    # --- Forwarded message provenance ---
    # Parsed ONCE here, before any routing, because a forward can arrive as
    # text or as a photo and both paths below want the note. Returns None for
    # an ordinary message, which leaves every existing path untouched.
    #
    # This is the half WhatsApp cannot do. Telegram's forward_origin carries
    # the original sender, so the note can name them and check the account;
    # Twilio gives the WhatsApp side two booleans and no sender at all. Both
    # bots call the same builder and it words each case for what that platform
    # actually knows -- see relayshield_forward_analysis.
    forward_note = ""
    fwd_origin = fwd.parse_telegram_forward(message)
    if fwd_origin:
        try:
            forward_note = fwd.render_forward_note(fwd.analyze_forward(fwd_origin))
        except Exception as exc:
            # Provenance is an enrichment. It must never cost the user the
            # content verdict, which is the part that says do not click.
            logger.warning("Forward provenance failed chat_id=%s: %s", chat_id, exc)
            forward_note = ""

    # --- Photo + /analyze caption → Rekognition OCR + fraud analysis ---
    # User sends a screenshot of a suspicious email/message with caption /analyze
    photo = message.get("photo")
    document = message.get("document")
    is_image_document = bool(
        document and str(document.get("mime_type", "")).startswith("image/")
    )
    caption = message.get("caption", "").strip()
    # "scan" added 2026-08-10 alongside the command merge: /scan is now the
    # documented name, so a screenshot captioned /scan must work too.
    #
    # NO CAPTION REQUIRED, from 2026-08-11. Someone who has just been sent a
    # scam SMS screenshots it and sends the image. Requiring them to remember a
    # caption first meant the bot silently ignored exactly the person it exists
    # for. In a DM with a security bot there is no other plausible reason to
    # send an image, so a bare screenshot now goes straight to OCR.
    #
    # A caption that is some OTHER slash command still falls through to the
    # normal dispatcher, so a photo captioned "/help" does not get OCR'd. Free
    # text captions ("is this a scam?") DO scan, which is what the words mean.
    _cap_cmd = (caption.lower().lstrip("/").split()[0]
                if caption.startswith("/") and len(caption) > 1 else "")
    if (photo or is_image_document) and (
            not _cap_cmd or _cap_cmd in ("scan", "msgscan", "analyze", "analyse")):
        send_message(
            chat_id,
            "📧 *Scanning your screenshot...* This may take a few seconds.",
        )
        if photo:
            image_bytes = download_telegram_photo(photo)
        else:
            image_bytes = download_telegram_file(document["file_id"])
        extracted_text = run_textract_ocr(image_bytes) if image_bytes else None
        if extracted_text:
            handle_analyze(chat_id, extracted_text, from_image=True,
                           forward_note=forward_note)
        else:
            send_message(
                chat_id,
                "⚠️ *Could not read text from that image.*\n\n"
                "Try a clearer screenshot, or paste the text directly:\n"
                "`/analyze <paste message text here>`",
                parse_mode="Markdown",
            )
        return

    # --- Forwarded text → straight to the fraud analyser ---
    # Forwarding the message IS the request. Nobody who has just been sent
    # something frightening forwards it and then types /scan, and until this
    # existed a forwarded scam landed in route_active_command and came back
    # "I didn't recognise that" — the worst possible answer to the one action
    # a worried person takes without being told to.
    #
    # Gated on the two states that reach route_active_command, so a forward
    # arriving mid-onboarding still feeds the step the user is actually on
    # rather than being swallowed here. Anything else falls through untouched.
    #
    # A forward that IS a command ("/help" forwarded from somewhere) still
    # routes as a command: that is a person showing the bot a command, and
    # running it is the less surprising of the two readings.
    # The single-token codes below (WA link code, team invite, Coinbase order
    # ID) are excluded by shape. The Coinbase block in particular has no
    # existing-user check on purpose -- a Personal Shield user can also
    # subscribe to Crypto Shield -- so intercepting a bare order ID here would
    # answer a paying customer's onboarding with a fraud verdict. A forwarded
    # order confirmation is prose and does not match any of these.
    _fwd_is_code = bool(
        re.match(r"^\d{6}$", text)
        or re.match(r"^[A-Z0-9]{8}$", text)
        or re.match(r"^[A-Z0-9_]{10,}$", text, re.IGNORECASE)
    )
    if fwd_origin and text and not text.startswith("/") and not _fwd_is_code:
        _fwd_user = get_user_by_chat_id(chat_id)
        if _fwd_user and _fwd_user.get("onboarding_state", "ACTIVE") in ("ACTIVE", "FREE_ACTIVE"):
            handle_analyze(chat_id, text, forward_note=forward_note)
            return

    # Reply to any ForceReply prompt above — treat the plain text as that
    # command's argument directly, no need to retype "/command <arg>".
    # Stateless (no DB field needed): Telegram echoes the prompt's own text
    # back on reply_to_message, so matching against each command's marker is
    # enough to identify which one it was replying to.
    reply_to = message.get("reply_to_message") or {}
    reply_text = reply_to.get("text", "")
    if text and reply_text:
        for marker, handler in REPLY_PROMPT_HANDLERS:
            if marker in reply_text:
                user = get_user_by_chat_id(chat_id)
                handler(chat_id, text, user)
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

    # Handle CB Business ULID-format order IDs (e.g. ord_01ks..., pay_01ks..., 01ks...)
    # These are longer than invite codes — handle before the 8-char block.
    # No existing-user check: a Personal Shield user can also subscribe to Crypto Shield.
    if re.match(r"^[A-Z0-9_]{10,}$", text, re.IGNORECASE) and not re.match(r"^(0x[0-9A-Fa-f]{40}|[1-9A-HJ-NP-Za-km-z]{32,44}|EQ[0-9A-Za-z_-]{46}|UQ[0-9A-Za-z_-]{46})$", text):
        charge = find_coinbase_charge(text)
        if charge:
            update_user(charge["user_id"], {
                "telegram_chat_id": str(chat_id),
                "first_name":       first_name,
                "active":           True,
                "updated_at":       datetime.now(timezone.utc).isoformat(),
            })
            charge["telegram_chat_id"] = str(chat_id)
            charge["first_name"] = first_name
            handle_coinbase_onboarding(chat_id, charge, first_name)
            return
        # Trust-based: create on the spot for longer order ID formats
        user_id = _create_trust_based_stub(text, str(chat_id), first_name)
        charge = {
            "user_id":            user_id,
            "tier":               "crypto_shield",
            "subscription_tier":  "crypto_shield",
            "plan":               "monthly",
            "coinbase_charge_id": text,
            "telegram_chat_id":   str(chat_id),
            "first_name":         first_name,
            "payer_wallet":       None,
        }
        handle_coinbase_onboarding(chat_id, charge, first_name)
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
            # Not an invite code — try as a Coinbase charge code
            # 1. Check if webhook pre-created a stub for this charge ID
            charge = find_coinbase_charge(text)
            if charge:
                update_user(charge["user_id"], {
                    "telegram_chat_id": str(chat_id),
                    "first_name":       first_name,
                    "active":           True,
                    "updated_at":       datetime.now(timezone.utc).isoformat(),
                })
                charge["telegram_chat_id"] = str(chat_id)
                charge["first_name"] = first_name
                handle_coinbase_onboarding(chat_id, charge, first_name)
                return
            # 2. No pre-existing stub — create on the spot (trust-based onboarding).
            #    Customer has their Coinbase order confirmation; we trust it and onboard.
            user_id = _create_trust_based_stub(text, str(chat_id), first_name)
            charge = {
                "user_id":            user_id,
                "tier":               "crypto_shield",
                "subscription_tier":  "crypto_shield",
                "plan":               "monthly",
                "coinbase_charge_id": text,
                "telegram_chat_id":   str(chat_id),
                "first_name":         first_name,
                "payer_wallet":       None,
            }
            handle_coinbase_onboarding(chat_id, charge, first_name)
            return

    # Handle /start (with optional deep link payload e.g. /start CHARGECODE)
    if text.lower().startswith("/start"):
        parts = text.split(None, 1)
        payload = parts[1].strip().upper() if len(parts) > 1 else ""
        handle_start(chat_id, first_name, payload)
        return

    # Handle /myid — works at any onboarding state, no user record needed
    if text.lower().lstrip("/") == "myid":
        handle_myid(chat_id)
        return

    # Existing user routing
    user = get_user_by_chat_id(chat_id)
    if not user:
        # A record can exist and still miss the lookup above, which filters on
        # active==True. That combination is invisible from the user's side:
        # every command answered "Type /start", and /start itself re-ran the
        # plan picker because handle_start uses the same active-only lookup —
        # so a lapsed subscriber was told to sign up again rather than told
        # their account was inactive. Checked BEFORE /help, because telling a
        # real subscriber they have no account is the same lie in a nicer tone.
        lapsed = get_any_user_by_chat_id(chat_id)
        if lapsed:
            send_message(
                chat_id,
                "🔒 *Your RelayShield account is inactive.*\n\n"
                "Monitoring is paused, so alerts are not being delivered and "
                "commands will not run.\n\n"
                "Type /start to choose a plan and reactivate, or email "
                "support@relayshield.net if you believe this is wrong.",
                parse_mode="Markdown",
            )
            return
        # /help must never dead-end. It is the discovery command, it is in the
        # native "/" menu for every chat, and answering it costs nothing — so
        # bouncing an unknown chat to /start makes the bot look broken to
        # exactly the person trying to work out how to use it.
        if text.lower().lstrip("/").split()[:1] == ["help"]:
            handle_help_no_account(chat_id)
            return
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

    # /help answers in EVERY state, before the onboarding chain gets a look.
    # Two reasons. First, "/help" is never a valid email, wallet, domain or
    # YES/NO, so no awaiting-input state loses anything by not consuming it.
    # Second, the chain below ends in a catch-all that tells the user to type
    # /start — so any state without a handler silently bricks the account, and
    # /start does not recover it because handle_start's _ACTIVE_STATES will not
    # match the orphan either. That is not hypothetical: a live business_basic
    # account sat in AWAITING_EMPLOYEE_EMAIL_1, a state with no handler
    # anywhere in this file, and every command answered "Type /start".
    if text.lower().lstrip("/").split()[:1] == ["help"]:
        if state not in _KNOWN_ONBOARDING_STATES:
            logger.error(
                "orphaned onboarding_state=%r on user_id=%s — no handler exists; "
                "every non-/help command will dead-end for this account",
                state, user.get("user_id"),
            )
        handle_help(chat_id, user)
        return

    if state == "AWAITING_WALLET_CONFIRM":
        # Text fallback for users who type YES/NO instead of tapping inline buttons
        t = text.strip().upper()
        payer_wallet = user.get("payer_wallet", "")
        if t in ("YES", "Y") and payer_wallet:
            wallets = user.get("wallets", [])
            if payer_wallet not in wallets:
                wallets.append(payer_wallet)
            update_user(user["user_id"], {
                "wallets":          wallets,
                "onboarding_state": "AWAITING_PHONE",
            })
            request_contact(
                chat_id,
                "✅ *Wallet enrolled for monitoring.*\n\n"
                "Now let's protect your phone against SIM swap attacks.\n\n"
                "Please share your phone number:",
            )
        elif t in ("NO", "N"):
            update_user(user["user_id"], {"onboarding_state": "AWAITING_WALLET_INPUT"})
            send_message(
                chat_id,
                "📍 Please enter the wallet address you'd like to monitor:\n\n"
                "_(Supports EVM 0x..., Solana, TON, and Bitcoin)_",
                parse_mode="Markdown",
            )
        else:
            # Re-prompt with keyboard
            send_message(
                chat_id,
                "Please use the buttons above to confirm — or type YES or NO:",
                reply_markup=crypto_wallet_confirm_keyboard(payer_wallet) if payer_wallet else None,
            )

    elif state == "AWAITING_WALLET_INPUT":
        # Allow slash commands to escape the wallet input state
        if text.startswith("/"):
            update_user(user["user_id"], {"onboarding_state": "ACTIVE"})
            user["onboarding_state"] = "ACTIVE"
            route_active_command(chat_id, text, user)
            return
        addr = text.strip()
        if not _is_valid_wallet_address(addr):
            send_message(
                chat_id,
                "❌ That doesn't look like a valid wallet address. Please try again.\n\n"
                "_(Supports EVM 0x..., Solana base58, TON EQ.../UQ..., Bitcoin 1.../3.../bc1...)_",
                parse_mode="Markdown",
            )
        else:
            wallets = user.get("wallets", [])
            if addr not in wallets:
                wallets.append(addr)
            update_user(user["user_id"], {
                "wallets":          wallets,
                "onboarding_state": "AWAITING_PHONE",
            })
            request_contact(
                chat_id,
                "✅ *Wallet enrolled for monitoring.*\n\n"
                "Now let's protect your phone against SIM swap attacks.\n\n"
                "Please share your phone number:",
            )

    elif state == "AWAITING_PHONE":
        # Allow slash commands to escape the phone input state
        if text.startswith("/"):
            update_user(user["user_id"], {"onboarding_state": "ACTIVE"})
            user["onboarding_state"] = "ACTIVE"
            route_active_command(chat_id, text, user)
            return
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
    elif state in (
        "AWAITING_REMOVE_SELECT", "AWAITING_DOMAIN_ADD", "AWAITING_BREACH_EMAIL",
        "AWAITING_DELEGATE_SELECT", "AWAITING_REVOKE_SELECT",
    ) and text.startswith("/"):
        # Slash command received mid-flow — cancel current operation and route normally
        update_user(user["user_id"], {
            "onboarding_state":      "ACTIVE",
            "pending_remove_list":   None,
            "pending_delegate_list": None,
            "pending_revoke_list":   None,
        })
        user["onboarding_state"] = "ACTIVE"
        send_message(chat_id, "↩️ Previous operation cancelled.")
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
    elif state == "AWAITING_DELEGATE_SELECT":
        if text.strip().lower() == "cancel":
            update_user(user["user_id"], {"onboarding_state": "ACTIVE", "pending_delegate_list": None})
            send_message(chat_id, "Cancelled. No changes made.")
        elif text.strip().isdigit():
            idx     = int(text.strip()) - 1
            pending = user.get("pending_delegate_list", [])
            if 0 <= idx < len(pending):
                delegate_id = pending[idx]
                record      = get_user_record(delegate_id)
                name        = (record.get("employee_name") or record.get("first_name", "This member")) if record else "This member"
                current     = [uid for uid in user.get("delegated_admin_ids", []) if uid != delegate_id]
                current.append(delegate_id)
                update_user(user["user_id"], {
                    "onboarding_state":      "ACTIVE",
                    "delegated_admin_ids":   current,
                    "pending_delegate_list": None,
                })
                if record:
                    delegate_tg = record.get("telegram_chat_id")
                    if delegate_tg:
                        send_message(
                            int(delegate_tg),
                            "🔑 *Delegate Access Granted*\n\n"
                            "Your admin has granted you delegate access on RelayShield.\n\n"
                            "You can now use: /addmember, /removemember, /teamstatus\n\n"
                            "🛡️ RelayShield",
                            parse_mode="Markdown",
                        )
                send_message(
                    chat_id,
                    f"✅ *{name}* is now a delegate admin.\n\n"
                    "They can add/remove team members and view team status.\n"
                    "Use /revoke to remove their access at any time.",
                    parse_mode="Markdown",
                )
            else:
                send_message(chat_id, "Invalid selection. Reply with a number from the list, or `cancel`:")
        else:
            send_message(chat_id, "Reply with a number from the list, or `cancel`:")
    elif state == "AWAITING_REVOKE_SELECT":
        if text.strip().lower() == "cancel":
            update_user(user["user_id"], {"onboarding_state": "ACTIVE", "pending_revoke_list": None})
            send_message(chat_id, "Cancelled. No changes made.")
        elif text.strip().isdigit():
            idx     = int(text.strip()) - 1
            pending = user.get("pending_revoke_list", [])
            if 0 <= idx < len(pending):
                revoke_id = pending[idx]
                record    = get_user_record(revoke_id)
                name      = (record.get("employee_name") or record.get("first_name", "This member")) if record else "This member"
                current   = [uid for uid in user.get("delegated_admin_ids", []) if uid != revoke_id]
                update_user(user["user_id"], {
                    "onboarding_state":    "ACTIVE",
                    "delegated_admin_ids": current,
                    "pending_revoke_list": None,
                })
                if record:
                    delegate_tg = record.get("telegram_chat_id")
                    if delegate_tg:
                        send_message(
                            int(delegate_tg),
                            "🔔 *Delegate Access Removed*\n\n"
                            "Your admin has removed your delegate access on RelayShield.\n\n"
                            "🛡️ RelayShield",
                            parse_mode="Markdown",
                        )
                send_message(
                    chat_id,
                    f"✅ Delegate access removed from *{name}*.\n\n"
                    "Use /delegate to grant access to another team member.",
                    parse_mode="Markdown",
                )
            else:
                send_message(chat_id, "Invalid selection. Reply with a number from the list, or `cancel`:")
        else:
            send_message(chat_id, "Reply with a number from the list, or `cancel`:")
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
            set_commands_for_user(chat_id, tier)
            send_message(chat_id, msg_onboarding_complete(first_name, len(emails), tier))
            send_message(chat_id, msg_first_run_tips(tier), parse_mode="Markdown")
        else:
            handle_domain_input(chat_id, text, user)
    elif state == "AWAITING_FREE_EMAIL":
        email = text.strip().lower()
        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
            send_message(chat_id, "That doesn't look like a valid email address. Please try again:")
            return
        email_hash = hash_email(email)
        email_enc  = encrypt_field(email)
        me_table   = dynamodb.Table(MONITORED_EMAILS_TABLE)
        me_table.put_item(Item={
            "email_id":        str(uuid.uuid4()),
            "user_id":         user["user_id"],
            "email_encrypted": email_enc,
            "email_hash":      email_hash,
            "tier":            TIER_FREE,
            "created_at":      datetime.now(timezone.utc).isoformat(),
            "active":          True,
        })
        update_user(user["user_id"], {
            "monitored_emails": [email],
            "onboarding_state": "FREE_ACTIVE",
        })
        send_message(chat_id, "🔍 Checking for breaches...")
        try:
            breaches = _run_hibp_check(email)
        except Exception as exc:
            logger.error("Free tier HIBP check failed: %s", exc)
            send_message(chat_id, "⚠️ Breach check temporarily unavailable. Please try /breach later.")
            return
        _send_free_breach_result(chat_id, email, breaches)
    elif state in ("ACTIVE", "FREE_ACTIVE"):
        route_active_command(chat_id, text, user)
    else:
        send_message(chat_id, "Type /start to begin your setup.")


def _get_anthropic_key() -> str:
    resp = secrets_client.get_secret_value(SecretId=ANTHROPIC_SECRET_NAME)
    return resp["SecretString"].strip()


def _claude_draft_reply(title: str, url: str, source: str,
                        cat_type: str, subreddit: str) -> str:
    """Call Claude to draft a contextual reply for a monitor alert."""
    src_str = f"r/{subreddit} on Reddit" if subreddit else source.replace("_", " ").title()
    cat_descriptions = {
        "victim_sim":    "someone who was SIM swapped or is at risk",
        "victim_wallet": "someone whose crypto wallet was drained or hacked",
        "scam":          "someone asking if a Telegram/crypto message is a scam",
        "brand":         "a mention of RelayShield by name",
        "intel":         "a news article about a security threat",
    }
    cat_desc = cat_descriptions.get(cat_type, "a security-related post")

    prompt = (
        f"You are drafting a reply for Andrew, founder of RelayShield "
        f"(crypto & identity security SaaS). He will edit and post this manually.\n\n"
        f"Post title: {title}\n"
        f"Platform: {src_str}\n"
        f"Context: This is {cat_desc}.\n\n"
        f"Write a reply that:\n"
        f"- Opens with genuinely useful, specific advice (not generic)\n"
        f"- Sounds like a knowledgeable person, not a marketer\n"
        f"- Mentions RelayShield only at the very end as a natural aside, "
        f"phrased as 'Full disclosure — I built RelayShield which does X'\n"
        f"- Is under 150 words\n"
        f"- Does NOT start with 'Great post', 'Thanks for sharing', or similar\n"
        f"- For victims: lead with empathy and immediate action steps\n"
        f"- For scam posts: call out specific red flags from the title\n"
        f"- For brand mentions: be engaged and add value to the conversation\n\n"
        f"Output ONLY the reply text. No preamble, no explanation."
    )

    api_key = _get_anthropic_key()
    payload = json.dumps({
        "model":      "claude-haiku-4-5-20251001",
        "max_tokens": 300,
        "messages":   [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        ANTHROPIC_MESSAGES_URL,
        data=payload,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        return result["content"][0]["text"].strip()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.error("Anthropic HTTP %s: %s", exc.code, body[:500])
        raise


def handle_monitor_callback(chat_id: int, draft_key: str,
                             action: str, cq_id: str) -> None:
    """
    Handle 📝 Reply Drafted / ⏭ Skip button taps from monitor alerts.
    action: "draft" or "skip"
    """
    answer_callback(cq_id)

    if action == "skip":
        send_message(chat_id, "⏭ _Skipped._", parse_mode="Markdown")
        return

    # Look up post context from DynamoDB
    resp = dynamodb.Table(MONITOR_DRAFTS_TABLE).get_item(Key={"draft_key": draft_key})
    item = resp.get("Item")
    if not item:
        send_message(chat_id, "⚠️ Draft context expired — open the link and draft manually.")
        return

    send_message(chat_id, "✍️ _Drafting reply with Claude..._", parse_mode="Markdown")

    try:
        draft = _claude_draft_reply(
            title     = item.get("title", ""),
            url       = item.get("url", ""),
            source    = item.get("source", ""),
            cat_type  = item.get("cat_type", ""),
            subreddit = item.get("subreddit", ""),
        )
    except Exception as exc:
        logger.error("Claude draft failed: %s", exc)
        send_message(chat_id, "⚠️ Draft generation failed. Check CloudWatch.")
        return

    send_message(
        chat_id,
        f"📝 *Draft reply* — edit before posting:\n\n"
        f"```\n{draft}\n```\n\n"
        f"⚠️ _Vary the wording. Never paste verbatim twice._",
        parse_mode="Markdown",
    )


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

    if data.startswith("mdr_"):
        handle_monitor_callback(chat_id, data[4:], "draft", cq_id)

    elif data.startswith("msk_"):
        handle_monitor_callback(chat_id, data[4:], "skip", cq_id)

    elif data.startswith("intent_"):
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

    elif data == "help_more":
        answer_callback(cq_id)
        tier = (user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)) if user else TIER_PERSONAL
        send_message(chat_id, msg_help(tier))

    # Category shortcut from the Quick Start card. Falls back to the full
    # list if the section is missing for this tier, so a stale button can
    # never produce an empty reply.
    # RESTORED 2026-08-26. These two branches were in main (9239e1c) and in no
    # deployed package, so the hub buttons the same commit added had nothing to
    # dispatch them. The keyboards are restored above; without this they would
    # render and do nothing, which is worse than not restoring them at all. The
    # guard cannot see this: it is inside a function, not a top-level symbol.
    elif data.startswith("scamhub_"):
        answer_callback(cq_id)
        sub = data[len("scamhub_"):]
        if sub == "verifybot":
            handle_verify_bot(chat_id)
        elif sub == "botcheck":
            # No argument to hand over from a button press, so ask for one the
            # same way every other argument-taking command does.
            handle_botcheck(chat_id, None)
        elif sub == "vishing":
            # The vishing BUTTON is gone from scam_hub_keyboard(), because the
            # 2026-08-11 merge folded phone-scam guidance into handle_wascam()
            # and a button that re-shows the message it is attached to is a
            # loop. This branch stays so that hub messages already sitting in
            # people's chat history keep working instead of silently failing.
            handle_wascam(chat_id)

    elif data.startswith("stealhub_"):
        answer_callback(cq_id)
        sub = data[len("stealhub_"):]
        if sub == "extensions":
            handle_extensions(chat_id)
        elif sub == "email":
            handle_infostealer_check(chat_id, None, user or {})

    elif data.startswith("help_cat_"):
        answer_callback(cq_id)
        tier = (user.get("tier") or user.get("subscription_tier", TIER_PERSONAL)) if user else TIER_PERSONAL
        body = msg_help_section(tier, data[len("help_cat_"):])
        send_message(chat_id, body or msg_help(tier),
                     reply_markup=help_expand_keyboard(tier))

    elif data == "wallet_confirm_yes" and user:
        answer_callback(cq_id)
        payer_wallet = user.get("payer_wallet", "")
        if payer_wallet:
            wallets = user.get("wallets", [])
            if payer_wallet not in wallets:
                wallets.append(payer_wallet)
            update_user(user["user_id"], {
                "wallets":          wallets,
                "onboarding_state": "AWAITING_PHONE",
            })
            request_contact(
                chat_id,
                "✅ *Wallet enrolled for monitoring.*\n\n"
                "Now let's protect your phone against SIM swap attacks.\n\n"
                "Please share your phone number:",
            )

    elif data == "wallet_confirm_no" and user:
        answer_callback(cq_id)
        update_user(user["user_id"], {"onboarding_state": "AWAITING_WALLET_INPUT"})
        send_message(
            chat_id,
            "📍 Please enter the wallet address you'd like to monitor:\n\n"
            "_(Supports EVM 0x..., Solana, TON, and Bitcoin)_",
            parse_mode="Markdown",
        )

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
    Maps payment amount → tier, creates or upgrades user record,
    tracks free→paid conversions, then begins onboarding.
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
    now = datetime.now(timezone.utc).isoformat()

    # Check for free→paid conversion — upgrade in place to preserve user_id + emails
    existing = get_user_by_chat_id(chat_id)
    if existing and existing.get("tier") == TIER_FREE:
        update_user(existing["user_id"], {
            "tier":                tier,
            "subscription_tier":   tier,
            "active":              True,
            "onboarding_state":    "AWAITING_PHONE",
            "converted_from_free": True,
            "conversion_date":     now,
            "updated_at":          now,
        })
        logger.info(
            "Free→paid conversion — user_id=%s chat_id=%s tier=%s",
            existing["user_id"], chat_id, tier,
        )
    else:
        # Brand new paid user — create fresh record
        create_telegram_user(chat_id, tier, first_name)

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

    Supported payload shapes:

    Correlation signal (predictive warnings + attack chain detection):
        {
            "source":           "relayshield_internal",
            "user_id":          "<DynamoDB user_id>",
            "signal_type":      "sim_swap" | "breach_alert" | "domain_lookalike" | ...,
            "telegram_chat_id": <int>
        }

    Direct message delivery (admin co-notifications):
        {
            "source":           "relayshield_internal",
            "action":           "send_message",
            "telegram_chat_id": <int>,
            "message":          "<text>"
        }
    """
    # Direct message delivery — admin co-notifications and custom alerts
    if body.get("action") == "send_message":
        chat_id = body.get("telegram_chat_id")
        message = body.get("message", "")
        if chat_id and message:
            send_message(int(chat_id), message, parse_mode="Markdown")
            return "message_sent"
        return "bad_send_payload"

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


# ---------------------------------------------------------------------------
# Inline mode — added 2026-08-10
#
# `@relayshield_bot <address or link>` typed inside ANY chat. The group installs
# nothing, and Telegram stamps every posted result with "via @relayshield_bot",
# so each use is an impression for everyone in that chat. This is the only
# surface where usage produces distribution rather than consuming it.
#
# Three constraints that make this different from every other handler here:
#
# 1. NO ACCOUNT. An inline query arrives from someone who has never pressed
#    Start. There is no user record, no tier, no onboarding state. Nothing in
#    this path may call get_user_record or assume one exists.
# 2. NEVER FALSELY CLEAN. This is the most public thing the product does, so
#    "we could not check" must never render as "safe". Same defect class as the
#    sim-swap false-clean and the asset-intel sweep.
# 3. PUBLIC BY CONSTRUCTION. The result may be posted into a group chat, so it
#    may only ever contain what the user typed and a verdict on it. No stored
#    data, no account details, nothing about the sender.
# ---------------------------------------------------------------------------

INLINE_CACHE_SECONDS = 300
_INLINE_RATE: dict = {}          # {chat_hash: [epoch, ...]} per warm container
INLINE_MAX_PER_MIN = 12


def _inline_rate_ok(user_id) -> bool:
    """Crude per-container throttle. Inline queries come from strangers at
    unbounded volume and there is no other rate limit anywhere in this file.
    Not exact across concurrent containers, and does not need to be: it exists
    to stop one actor hammering the upstreams, not to meter billing."""
    now = time.time()
    key = _hash_id(user_id)
    hits = [t for t in _INLINE_RATE.get(key, []) if now - t < 60]
    hits.append(now)
    _INLINE_RATE[key] = hits
    if len(_INLINE_RATE) > 500:                     # bound container memory
        for k in list(_INLINE_RATE)[:250]:
            _INLINE_RATE.pop(k, None)
    return len(hits) <= INLINE_MAX_PER_MIN


def _inline_article(rid: str, title: str, desc: str, body: str) -> dict:
    return {
        "type": "article", "id": rid, "title": title, "description": desc,
        "input_message_content": {
            "message_text": body, "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        },
    }


# The one line that carries the funnel. A wallet address is public by nature so
# screening it in a group is fine; a breach or stealer-log result is private by
# nature, so the user has to leave the group and DM the bot to get it. The
# medium enforces the split, which is why no detail belongs here.
_INLINE_UPSELL = (
    "\n\n_Addresses are only half of it. Most drains start with a leaked "
    "credential, not a bad contract. DM_ @relayshield\\_bot _to check whether "
    "your email or phone is exposed._"
)


def handle_inline_query(update: dict) -> None:
    iq       = update.get("inline_query") or {}
    query_id = iq.get("id")
    raw      = (iq.get("query") or "").strip()
    user_id  = (iq.get("from") or {}).get("id")
    if not query_id:
        return

    def answer(results, placeholder=None):
        payload = {
            "inline_query_id": query_id,
            "results": json.dumps(results),
            "cache_time": INLINE_CACHE_SECONDS,
            "is_personal": False,
        }
        if placeholder:
            payload["button"] = json.dumps(
                {"text": placeholder, "start_parameter": "inline"})
        try:
            tg_api("answerInlineQuery", payload)
        except Exception as exc:
            logger.warning("answerInlineQuery failed: %s", exc)

    if not raw:
        answer([_inline_article(
            "empty", "Paste a wallet address or link",
            "I'll check it and post the result here",
            "Type `@relayshield_bot` followed by a wallet address or a link, "
            "and I'll check it before you act on it.")],
            placeholder="Open RelayShield")
        return

    if not _inline_rate_ok(user_id):
        answer([_inline_article(
            "rate", "Too many checks, one moment",
            "Rate limited, try again shortly",
            "⏳ Too many checks in a short window. Try again in a minute.")])
        return

    if len(raw) > 200:
        answer([_inline_article("toolong", "That input is too long",
                                "Paste a single address or link",
                                "That is longer than a single address or link.")])
        return

    normalized = _normalize_scan_url(raw)
    try:
        if normalized and " " not in raw:
            title, desc, body = _inline_check_url(normalized)
        elif _looks_like_wallet_address(raw):
            title, desc, body = _inline_check_address(raw)
        else:
            answer([_inline_article(
                "unknown", "Not an address or a link",
                "Paste a wallet address or a URL",
                "I check wallet addresses and links. That did not look like "
                "either. For suspicious emails and texts, DM me and use /scan.")])
            return
    except Exception as exc:
        # Constraint 2. An upstream failure is reported as a failure.
        logger.warning("inline check failed: %s", exc)
        answer([_inline_article(
            "err", "Could not complete the check",
            "Upstream unavailable, this is NOT an all-clear",
            "⚠️ *Check did not complete.* An upstream source was unavailable, "
            "so this is *not* an all-clear. Try again shortly.")])
        return

    answer([_inline_article("res", title, desc, body + _INLINE_UPSELL)],
           placeholder="Check your own exposure")
    logger.info("inline query answered user=%s kind=%s qlen=%d",
                _hash_id(user_id), "url" if normalized else "address", len(raw))


def _looks_like_wallet_address(s: str) -> bool:
    if " " in s:
        return False
    if re.fullmatch(r"0x[a-fA-F0-9]{40}", s):                       return True   # EVM
    if re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", s):             return True   # Solana
    if re.fullmatch(r"(EQ|UQ)[A-Za-z0-9_-]{46}", s):                return True   # TON
    if re.fullmatch(r"(bc1[a-z0-9]{25,62}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})", s): return True
    if re.fullmatch(r"r[1-9A-HJ-NP-Za-km-z]{24,34}", s):            return True   # XRP
    return False


def _inline_check_url(url: str):
    res = _heuristic_url_check(url)
    short = url if len(url) <= 60 else url[:57] + "..."
    if res.get("flagged"):
        return ("⚠️ Flagged", "; ".join(res.get("reasons", []))[:80],
                f"⚠️ *Flagged:* `{short}`\n\n" + "\n".join(f"• {r}" for r in res.get("reasons", []))
                + "\n\nDo not enter credentials or connect a wallet.")
    # Deliberately not the word "safe". This path is IOC corpus + Safe Browsing
    # + domain age, which is real but not a multi-engine verdict, and a new
    # phishing domain can be hours old and in no database yet.
    return ("No known flags", "Not a guarantee, see the note",
            f"🔍 *No known flags:* `{short}`\n\nNot found in criminal IOC feeds "
            "or Safe Browsing, and the domain is not brand new. That is not the "
            "same as safe: new phishing domains take hours to appear anywhere.")


def _inline_check_address(addr: str):
    chain_id = 101 if not addr.startswith("0x") else 1
    goplus   = _goplus_risk_check(addr, chain_id) if re.fullmatch(r"0x[a-fA-F0-9]{40}|[1-9A-HJ-NP-Za-km-z]{32,44}", addr) else {}
    abuse    = _chainabuse_risk(addr)
    short    = addr[:10] + "..." + addr[-6:]

    flags = []
    for k, label in (("honeypot_related_address", "linked to honeypot contracts"),
                     ("phishing_activities",      "phishing activity"),
                     ("blacklist_doubt",          "on a blacklist"),
                     ("stealing_attack",          "stealing attack activity"),
                     ("fake_kyc",                 "fake KYC"),
                     ("darkweb_transactions",     "dark web transactions"),
                     ("money_laundering",         "money laundering signals"),
                     ("sanctioned",               "sanctioned")):
        if str(goplus.get(k, "0")) not in ("0", "", "None"):
            flags.append(label)
    if abuse.get("count"):
        cats = ", ".join(abuse.get("categories", [])[:3])
        flags.append(f"{abuse['count']} community scam report(s)"
                     + (f" ({cats})" if cats else ""))

    if flags:
        return ("⚠️ Risk found", "; ".join(flags)[:80],
                f"⚠️ *Risk found:* `{short}`\n\n" + "\n".join(f"• {f}" for f in flags)
                + "\n\nDo not send funds or approve this address.")

    # Constraint 2: if BOTH sources failed, that is not clean.
    if not goplus and not abuse:
        raise RuntimeError("no upstream returned data")

    return ("No known flags", "Not a guarantee, see the note",
            f"🔍 *No known flags:* `{short}`\n\nNot in the scam-address databases "
            "we check. A clean record is not proof of safety, and a new address "
            "has no history to check at all.")


def lambda_handler(event, context):
    try:
        # Direct Lambda invoke (monitors calling us without API Gateway wrapping)
        if event.get("source") == "relayshield_internal":
            result = handle_inbound_signal(event)
            return {"statusCode": 200, "body": result}

        # Self-invoked async follow-up for a /scan that came back "unknown" —
        # see handle_scan. Not a real Telegram update, so it's checked before
        # the body-parsing path below.
        if event.get("source") == "relayshield_deferred_scan":
            handle_deferred_url_scan(event["chat_id"], event["target"])
            return {"statusCode": 200, "body": "ok"}

        body = json.loads(event.get("body", "{}"))
        logger.info("Telegram update: %s", _summarise_update(body))

        # Internal signal injection from monitors via API Gateway path
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
        elif "inline_query" in body:
            handle_inline_query(body)
        elif "chosen_inline_result" in body:
            # Inline Feedback is at 100%, so this fires whenever someone
            # actually POSTS a result rather than merely seeing one. It is the
            # single metric that distinguishes the flywheel working from not.
            logger.info("inline result chosen user=%s",
                        _hash_id((body["chosen_inline_result"].get("from") or {}).get("id")))
        else:
            logger.info("Unhandled update type: %s", list(body.keys()))

    except Exception as e:
        logger.exception("Unhandled error: %s", e)

    # Always return 200 to Telegram — otherwise it retries endlessly
    return {"statusCode": 200, "body": "ok"}
