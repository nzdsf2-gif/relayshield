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

USERS_TABLE = "relayshield_users"
MONITORED_EMAILS_TABLE = "relayshield_monitored_emails"
BREACH_ALERTS_TABLE = "relayshield_breach_alerts"

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

BUSINESS_TIERS = {TIER_STARTER, TIER_STARTER_DOMAIN, TIER_BASIC, TIER_SHIELD, TIER_PRO}

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

# Stripe price IDs for Telegram Payments (monthly) — populate after creating
# Telegram payment invoices for each plan
PLAN_PRICES = {
    TIER_PERSONAL:       {"label": "Personal Shield",      "amount": 1499, "currency": "usd"},
    TIER_STARTER:        {"label": "Business Starter",     "amount": 1999, "currency": "usd"},
    TIER_STARTER_DOMAIN: {"label": "Starter + Domain",     "amount": 2499, "currency": "usd"},
    TIER_BASIC:          {"label": "Business Basic",        "amount": 8999, "currency": "usd"},
    TIER_SHIELD:         {"label": "Business Shield",       "amount": 13999, "currency": "usd"},
}

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

def get_user_by_chat_id(chat_id: int) -> dict | None:
    table = dynamodb.Table(USERS_TABLE)
    resp = table.scan(
        FilterExpression=Attr("telegram_chat_id").eq(str(chat_id)) & Attr("active").eq(True)
    )
    items = resp.get("Items", [])
    return items[0] if items else None


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
            [{"text": "Personal Shield — $14.99/mo", "callback_data": f"plan_{TIER_PERSONAL}"}],
            [{"text": "Business Starter — $19.99/mo", "callback_data": f"plan_{TIER_STARTER}"}],
            [{"text": "Starter + Domain — $24.99/mo", "callback_data": f"plan_{TIER_STARTER_DOMAIN}"}],
        ]
    }


def business_plan_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [{"text": "Business Starter — $19.99/mo", "callback_data": f"plan_{TIER_STARTER}"}],
            [{"text": "Starter + Domain — $24.99/mo", "callback_data": f"plan_{TIER_STARTER_DOMAIN}"}],
            [{"text": "Business Basic — $89.99/mo (up to 5 seats)", "callback_data": f"plan_{TIER_BASIC}"}],
            [{"text": "Business Shield — $139.99/mo (up to 10 seats)", "callback_data": f"plan_{TIER_SHIELD}"}],
            [{"text": "📞 Contact us for Business Shield Pro", "callback_data": "plan_contact"}],
        ]
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
        "Who are you protecting?"
    )


def msg_help(tier: str) -> str:
    is_business = tier in BUSINESS_TIERS
    cmds = [
        "/sweep — Email security sweep",
        "/breach — Check breach status",
        "/sim — SIM swap monitoring status",
        "/verify — Personal verification protocol",
        "/otp — Unexpected OTP guidance",
        "/phone — Carrier hardening steps",
        "/wascam — Suspicious message guidance",
        "/sessions — Session revocation guidance",
        "/reuse — Cross-account password reuse check",
        "/help — This menu",
    ]
    if is_business:
        cmds.insert(0, "/status — Account & seat status (admin)")
    if tier in DOMAIN_TIERS:
        cmds.append("/domain — Domain monitoring status")
    return "🛡️ *RelayShield Commands*\n\n" + "\n".join(cmds)


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
            "Choose your plan:",
            reply_markup=personal_plan_keyboard(),
        )
    elif intent in ("business", "msp"):
        send_message(
            chat_id,
            "Choose your plan:",
            reply_markup=business_plan_keyboard(),
        )


def handle_plan_callback(chat_id: int, tier: str, callback_query_id: str,
                         first_name: str) -> None:
    """User selected a plan — initiate payment (Phase 2: Telegram Payments)."""
    answer_callback(callback_query_id)

    if tier == "contact":
        send_message(
            chat_id,
            "For Business Shield Pro pricing, contact us at relayshieldadmin@gmail.com "
            "and we'll set you up directly.",
        )
        return

    # TODO Phase 2: Send Telegram Payments invoice here.
    # For now, direct to Stripe payment link on relayshield.net
    plan = PLAN_PRICES.get(tier, {})
    label = plan.get("label", tier)
    amount_dollars = plan.get("amount", 0) / 100

    send_message(
        chat_id,
        f"You selected *{label}* (${amount_dollars:.2f}/mo).\n\n"
        f"Complete your subscription at relayshield.net — then return here "
        f"and send your email address to begin monitoring.",
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

    tier = user.get("tier", TIER_PERSONAL)
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
        request_contact(
            chat_id,
            "No problem — please share the number you'd like monitored:",
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

    tier = user.get("tier", TIER_PERSONAL)
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
        "email_hash": email_hash,
        "user_id": user["user_id"],
        "email_encrypted": email_enc,
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
    update_user(user["user_id"], {"onboarding_state": "ACTIVE"})
    first_name = user.get("first_name", "there")
    send_message(chat_id, msg_onboarding_complete(first_name, len(emails), user.get("tier")))


# ---------------------------------------------------------------------------
# Active user command handlers
# ---------------------------------------------------------------------------

def handle_help(chat_id: int, user: dict) -> None:
    send_message(chat_id, msg_help(user.get("tier", TIER_PERSONAL)))


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


def handle_otp(chat_id: int) -> None:
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


def handle_sweep(chat_id: int) -> None:
    send_message(
        chat_id,
        "🔍 *Email Security Sweep — 5 Steps*\n\n"
        "*Step 1:* Check email forwarding rules\n"
        "Gmail: Settings → See all settings → Forwarding\n"
        "Delete any rules you didn't create.\n\n"
        "*Step 2:* Check inbox filters\n"
        "Settings → Filters and Blocked Addresses\n"
        "Delete filters hiding security emails.\n\n"
        "*Step 3:* Review account recovery settings\n"
        "Check recovery email and phone are still yours.\n\n"
        "*Step 4:* Review active sessions\n"
        "Sign out all sessions except your current device.\n\n"
        "*Step 5:* Review connected apps\n"
        "myaccount.google.com/permissions — revoke anything suspicious.",
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
        "*Verify any request:*\n"
        "• No legitimate org sends urgent payment requests via text\n"
        "• No legitimate org asks you to run a command or click a link to prove you're human\n"
        "• When in doubt, call back on a number you look up yourself",
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
    tier = user.get("tier", TIER_PERSONAL)
    emails = user.get("monitored_emails", [])
    state = user.get("onboarding_state", "UNKNOWN")
    channels = user.get("delivery_channels", ["telegram"])

    send_message(
        chat_id,
        f"📊 *Account Status*\n\n"
        f"*Plan:* {tier.replace('_', ' ').title()}\n"
        f"*Emails monitored:* {len(emails)}\n"
        f"*State:* {state}\n"
        f"*Channels:* {', '.join(channels)}\n"
        f"*SIM monitoring:* {'Active' if user.get('phone_encrypted') else 'Pending setup'}",
    )


# ---------------------------------------------------------------------------
# Main router
# ---------------------------------------------------------------------------

def route_active_command(chat_id: int, text: str, user: dict) -> None:
    """Route commands from ACTIVE users."""
    cmd = text.strip().lower().lstrip("/")

    if cmd == "help":
        handle_help(chat_id, user)
    elif cmd == "verify":
        handle_verify(chat_id)
    elif cmd == "otp":
        handle_otp(chat_id)
    elif cmd == "sweep":
        handle_sweep(chat_id)
    elif cmd == "phone":
        handle_phone_hardening(chat_id)
    elif cmd in ("wascam", "scam"):
        handle_wascam(chat_id)
    elif cmd == "sessions":
        handle_sessions(chat_id)
    elif cmd in ("status", "account"):
        handle_status(chat_id, user)
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

    # Handle /start
    if text.lower() in ("/start", "/start@relayshield_bot"):
        handle_start(chat_id, first_name)
        return

    # Existing user routing
    user = get_user_by_chat_id(chat_id)
    if not user:
        send_message(
            chat_id,
            "Welcome to RelayShield! Type /start to begin.",
        )
        return

    state = user.get("onboarding_state", "ACTIVE")

    if state == "AWAITING_EMAIL_1":
        handle_email_input(chat_id, text, user)
    elif state == "AWAITING_MORE_EMAILS":
        handle_email_input(chat_id, text, user)
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

    if data.startswith("intent_"):
        intent = data.replace("intent_", "")
        handle_intent_callback(chat_id, intent, cq_id, first_name)

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

def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))
        logger.info("Telegram update: %s", json.dumps(body)[:500])

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
