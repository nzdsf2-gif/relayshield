"""
RelayShield WhatsApp Webhook Lambda
Receives all inbound WhatsApp messages via Twilio and routes them based
on the user's current onboarding_state.

Onboarding state machine:
  AWAITING_EMAIL_1       → validate + store first email, ask for more
  AWAITING_MORE_EMAILS   → add email (up to tier limit) or DONE → next stage
  AWAITING_PASSWORD_MANAGER → YES/NO → set flag → confirm + activate
  ACTIVE                 → handle reply commands

Reply commands (ACTIVE users):
  SWEEP    — Email Security Sweep instructions
  RESET    — Strong password guide
  REUSE    — Cross-account password reuse walkthrough (next account in sequence)
  MANAGER  — Bitwarden setup guide
  PHONE    — Carrier hardening steps (SIM swap + smishing defence)
  OTP      — User received an unexpected OTP they did not request
  SMS <text> — User forwards a suspicious text for analysis
  SESSIONS — Revoke active sessions and OAuth tokens (Google, Microsoft, social media)
  SAFE     — Vishing warning acknowledged
  CALL     — User received a suspicious call
  HELP     — List all available commands
  ADD +1XXXXXXXXXX — Business tier: add employee phone number (admin only)

Employee onboarding (Business tiers):
  Admin sends: ADD +16175551234
  RelayShield messages that number with abbreviated onboarding:
    AWAITING_EMPLOYEE_EMAIL_1 → AWAITING_EMPLOYEE_MORE_EMAILS → EMPLOYEE_ACTIVE
  Employee is linked to admin's account via admin_user_id field.
"""

import base64
import hashlib
import hmac
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr

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

USERS_TABLE = "relayshield_users"
MONITORED_EMAILS_TABLE = "relayshield_monitored_emails"

# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

TWILIO_SID_SECRET = "relayshield/twilio_account_sid"
TWILIO_TOKEN_SECRET = "relayshield/twilio_auth_token"
TWILIO_FROM_SECRET = "relayshield/twilio_whatsapp_number"
TWILIO_AUTH_TOKEN_SECRET = "relayshield/twilio_auth_token"
GSB_SECRET_NAME = "relayshield/google_safe_browsing"
GSB_SECRET_KEY = "google_safe_browsing_api_key"

TWILIO_MESSAGES_URL = (
    "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
)
GSB_URL = "https://safebrowsing.googleapis.com/v4/threatMatches:find"

# ---------------------------------------------------------------------------
# Tier constants
# ---------------------------------------------------------------------------

TIER_PERSONAL = "personal_shield"
TIER_BASIC = "business_basic"
TIER_SHIELD = "business_shield"
TIER_PRO = "business_shield_pro"

BUSINESS_TIERS = {TIER_BASIC, TIER_SHIELD, TIER_PRO}

# Max emails per subscriber (personal) or per employee (business)
EMAIL_LIMITS = {
    TIER_PERSONAL: 3,
    TIER_BASIC: 2,
    TIER_SHIELD: 2,
    TIER_PRO: 2,
}

# Max employee seats per business tier
SEAT_LIMITS = {
    TIER_BASIC: 5,
    TIER_SHIELD: 10,
    TIER_PRO: 25,
}

# Onboarding states
STATE_EMAIL_1 = "AWAITING_EMAIL_1"
STATE_MORE_EMAILS = "AWAITING_MORE_EMAILS"
STATE_PASSWORD_MANAGER = "AWAITING_PASSWORD_MANAGER"
STATE_ACTIVE = "ACTIVE"

# Employee onboarding states
STATE_EMP_EMAIL_1 = "AWAITING_EMPLOYEE_EMAIL_1"
STATE_EMP_MORE_EMAILS = "AWAITING_EMPLOYEE_MORE_EMAILS"
STATE_EMP_ACTIVE = "EMPLOYEE_ACTIVE"

# ---------------------------------------------------------------------------
# Cross-account reuse walkthrough
# ---------------------------------------------------------------------------

CROSS_ACCOUNT_SERVICES = [
    ("Gmail / Outlook / Yahoo Mail", "email — the master key to every other account"),
    ("Banking and financial apps", "direct access to money"),
    ("Amazon / PayPal / shopping accounts", "saved payment cards"),
    ("Apple ID / Google Account", "device access and app purchases"),
    ("Facebook / LinkedIn / social media", "identity and contact data"),
    ("Square / payment processing tools", "business bank account access"),
]


# ---------------------------------------------------------------------------
# Secret helpers
# ---------------------------------------------------------------------------

def get_secret(secret_name: str) -> str:
    response = secrets_client.get_secret_value(SecretId=secret_name)
    return response["SecretString"].strip()


def get_secret_json(secret_name: str, key: str) -> str:
    raw = get_secret(secret_name)
    try:
        data = json.loads(raw)
        return data[key]
    except (json.JSONDecodeError, KeyError):
        return raw


def get_twilio_credentials() -> tuple[str, str, str]:
    """Return (account_sid, auth_token, from_whatsapp_number)."""
    account_sid = get_secret_json(TWILIO_SID_SECRET, "TWILIO_ACCOUNT_SID")
    auth_token = get_secret_json(TWILIO_TOKEN_SECRET, "TWILIO_AUTH_TOKEN")
    from_number = get_secret_json(TWILIO_FROM_SECRET, "TWILIO_WHATSAPP_NUMBER")
    return account_sid, auth_token, from_number


def get_gsb_api_key() -> str:
    """Retrieve Google Safe Browsing API key from Secrets Manager."""
    return get_secret_json(GSB_SECRET_NAME, GSB_SECRET_KEY)


# ---------------------------------------------------------------------------
# Google Safe Browsing URL analysis
# ---------------------------------------------------------------------------

def extract_urls(text: str) -> list[str]:
    """
    Extract all http/https URLs from a text string.
    Returns a deduplicated list, preserving order of first appearance.
    """
    found = re.findall(r'https?://[^\s<>"\']+', text)
    seen = set()
    unique = []
    for url in found:
        # Strip trailing punctuation that may have been captured
        url = url.rstrip(".,;:!?)")
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def check_urls_safe_browsing(urls: list[str], api_key: str) -> dict:
    """
    Submit a list of URLs to Google Safe Browsing API v4.
    Returns a dict with keys:
      "matches"  — list of threat match dicts (empty if all clean)
      "error"    — error message string if API call failed, else None

    Uses urllib.request to stay consistent with the rest of the codebase.
    POST to GSB_URL?key={api_key} with JSON body.
    """
    payload = json.dumps({
        "client": {
            "clientId": "relayshield",
            "clientVersion": "1.0",
        },
        "threatInfo": {
            "threatTypes": [
                "MALWARE",
                "SOCIAL_ENGINEERING",
                "UNWANTED_SOFTWARE",
                "POTENTIALLY_HARMFUL_APPLICATION",
            ],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": u} for u in urls],
        },
    }).encode("utf-8")

    url_with_key = f"{GSB_URL}?key={api_key}"
    headers = {
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(
        url_with_key,
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
            # GSB returns {} when no threats found; "matches" key only present
            # when threats are detected.
            return {"matches": body.get("matches", []), "error": None}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        logger.error("GSB API HTTPError %s: %s", e.code, error_body)
        return {"matches": [], "error": f"HTTP {e.code}"}
    except urllib.error.URLError as e:
        logger.error("GSB API URLError: %s", e.reason)
        return {"matches": [], "error": str(e.reason)}
    except Exception as e:
        logger.error("GSB API unexpected error: %s", e)
        return {"matches": [], "error": str(e)}


def build_sms_analysis_response(
    forwarded_text: str,
    urls: list[str],
    gsb_result: dict,
) -> str:
    """
    Build the WhatsApp response for the SMS command based on URL analysis results.
    Three outcomes:
      1. No URLs found — guidance only
      2. URLs found, all clean — low-risk guidance
      3. URLs found, threats detected — CRITICAL warning
    Always falls back gracefully if GSB errored.
    """
    immediate_steps = (
        "→ Do not click any links in the message\n"
        "→ Do not reply to the sender\n"
        "→ Block the sender on your phone\n"
        "→ Report to your carrier: forward the text to *7726* (SPAM) — "
        "works on AT&T, T-Mobile, and Verizon\n"
        "→ Report to the FTC: reportfraud.ftc.gov\n"
    )

    if not urls:
        return (
            "📨 *Suspicious text received — no URLs detected.*\n\n"
            "No links were found in the forwarded text to analyse. "
            "If the message asked you to call a number or reply with personal details, "
            "treat it as a smishing attempt.\n\n"
            + immediate_steps
            + "\nReply *OTP* if you received a verification code, "
            "or *CALL* if you also received a suspicious call.\n\n"
            "— RelayShield"
        )

    if gsb_result["error"]:
        # API failed — return guidance without a verdict rather than crash
        logger.warning("GSB analysis skipped due to error: %s", gsb_result["error"])
        return (
            "📨 *Suspicious text received.*\n\n"
            f"Found {len(urls)} link(s) — automated analysis temporarily unavailable. "
            "Treat the link(s) as unsafe until you can verify them.\n\n"
            + immediate_steps
            + "\nReply *OTP* if you received a verification code, "
            "or *CALL* if you also received a suspicious call.\n\n"
            "— RelayShield"
        )

    matches = gsb_result["matches"]
    flagged_urls = {m["threat"]["url"] for m in matches}

    if flagged_urls:
        url_list = "\n".join(f"⛔ {u}" for u in flagged_urls)
        return (
            "🚨 *MALICIOUS LINK DETECTED*\n\n"
            f"RelayShield flagged {len(flagged_urls)} of the "
            f"{len(urls)} link(s) in that text as a confirmed threat "
            "(malware, phishing, or social engineering):\n\n"
            f"{url_list}\n\n"
            "*Do NOT click these links under any circumstances.*\n\n"
            + immediate_steps
            + "\nIf you already clicked the link:\n"
            "→ Do not enter any information on the page that opened\n"
            "→ Close the browser tab immediately\n"
            "→ Reply *SWEEP* to check your email accounts for backdoors\n"
            "→ Reply *SESSIONS* to revoke active sessions on your accounts\n\n"
            "— RelayShield"
        )

    # URLs found, all clean
    url_list = "\n".join(f"✅ {u}" for u in urls)
    return (
        "📨 *Suspicious text analysed — no known threats detected.*\n\n"
        f"RelayShield checked {len(urls)} link(s) and found no "
        "confirmed malware or phishing:\n\n"
        f"{url_list}\n\n"
        "⚠️ *A clean result does not guarantee the link is safe.* "
        "New phishing sites can take hours to appear in threat databases. "
        "If the text was unexpected or asked for personal information, "
        "treat it with caution regardless.\n\n"
        + immediate_steps
        + "\n— RelayShield"
    )


# ---------------------------------------------------------------------------
# Twilio signature verification
# ---------------------------------------------------------------------------

def verify_twilio_signature(
    auth_token: str,
    signature: str,
    url: str,
    params: dict,
) -> bool:
    """
    Verify the X-Twilio-Signature header.
    Twilio signs: URL + sorted POST params (key+value concatenated).
    """
    try:
        sorted_params = "".join(
            f"{k}{v}" for k, v in sorted(params.items())
        )
        signed_data = url + sorted_params
        expected = base64.b64encode(
            hmac.new(
                auth_token.encode("utf-8"),
                signed_data.encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("utf-8")
        return hmac.compare_digest(expected, signature)
    except Exception as exc:
        logger.exception("Twilio signature verification error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Phone number helpers
# ---------------------------------------------------------------------------

def normalise_phone(phone: str) -> str:
    """Strip whatsapp: prefix and normalise to E.164."""
    phone = phone.replace("whatsapp:", "").strip()
    cleaned = "".join(c for c in phone if c.isdigit() or c == "+")
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    return cleaned


def to_whatsapp_number(phone: str) -> str:
    """Prefix E.164 number with whatsapp: for Twilio (idempotent)."""
    if phone.startswith("whatsapp:"):
        return phone
    return f"whatsapp:{phone}"


def is_valid_email(email: str) -> bool:
    """Basic email format validation."""
    pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email.strip()))


def is_valid_phone(phone: str) -> bool:
    """Validate E.164 phone number."""
    cleaned = "".join(c for c in phone if c.isdigit() or c == "+")
    return cleaned.startswith("+") and len(cleaned) >= 8


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def get_user_by_whatsapp(whatsapp_number: str) -> dict | None:
    """Look up a user record by their WhatsApp number."""
    table = dynamodb.Table(USERS_TABLE)
    wa = to_whatsapp_number(normalise_phone(whatsapp_number))
    response = table.scan(
        FilterExpression=Attr("whatsapp_number").eq(wa),
    )
    items = response.get("Items", [])
    return items[0] if items else None


def update_user(user_id: str, updates: dict) -> None:
    """Apply a dict of attribute updates to a user record."""
    table = dynamodb.Table(USERS_TABLE)
    now = datetime.now(timezone.utc).isoformat()
    updates["updated_at"] = now

    expr_parts = []
    attr_names: dict = {}
    attr_values: dict = {}

    for i, (k, v) in enumerate(updates.items()):
        placeholder = f"#a{i}"
        value_key = f":v{i}"
        attr_names[placeholder] = k
        attr_values[value_key] = v
        expr_parts.append(f"{placeholder} = {value_key}")

    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames=attr_names,
        ExpressionAttributeValues=attr_values,
    )


def add_monitored_email(user_id: str, email_address: str) -> str:
    """
    Add an email to relayshield_monitored_emails.
    Returns the new email_id.
    """
    email_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    table = dynamodb.Table(MONITORED_EMAILS_TABLE)
    table.put_item(Item={
        "email_id": email_id,
        "user_id": user_id,
        "email_address": email_address.strip().lower(),
        "created_at": now,
        "last_checked": None,
        "active": True,
    })
    logger.info("Monitored email added — user_id=%s email=%s", user_id, email_address)
    return email_id


def count_monitored_emails(user_id: str) -> int:
    """Count active monitored emails for a user."""
    table = dynamodb.Table(MONITORED_EMAILS_TABLE)
    response = table.scan(
        FilterExpression=Attr("user_id").eq(user_id) & Attr("active").eq(True),
        Select="COUNT",
    )
    return response.get("Count", 0)


def email_already_monitored(user_id: str, email_address: str) -> bool:
    """Check if this email is already being monitored for this user."""
    table = dynamodb.Table(MONITORED_EMAILS_TABLE)
    response = table.scan(
        FilterExpression=(
            Attr("user_id").eq(user_id)
            & Attr("email_address").eq(email_address.strip().lower())
            & Attr("active").eq(True)
        ),
        Limit=1,
    )
    return len(response.get("Items", [])) > 0


def count_employees(admin_user_id: str) -> int:
    """Count active employee accounts linked to an admin."""
    table = dynamodb.Table(USERS_TABLE)
    response = table.scan(
        FilterExpression=(
            Attr("admin_user_id").eq(admin_user_id)
            & Attr("active").eq(True)
        ),
        Select="COUNT",
    )
    return response.get("Count", 0)


def create_employee_record(
    phone_number: str,
    admin_user_id: str,
    subscription_tier: str,
) -> str:
    """
    Create an employee user record linked to the admin's account.
    Returns the new user_id.
    """
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    table = dynamodb.Table(USERS_TABLE)
    table.put_item(Item={
        "user_id": user_id,
        "whatsapp_number": to_whatsapp_number(phone_number),
        "phone_number": phone_number,
        "subscription_tier": subscription_tier,
        "admin_user_id": admin_user_id,
        "onboarding_state": STATE_EMP_EMAIL_1,
        "emails_added": 0,
        "password_manager_user": False,
        "sim_swap_monitoring": True,
        "active": True,
        "created_at": now,
        "updated_at": now,
    })
    logger.info(
        "Employee record created — user_id=%s admin=%s phone=%s",
        user_id, admin_user_id, phone_number,
    )
    return user_id


# ---------------------------------------------------------------------------
# Twilio WhatsApp sender
# ---------------------------------------------------------------------------

def send_whatsapp(
    to_number: str,
    body: str,
    account_sid: str,
    auth_token: str,
    from_number: str,
) -> bool:
    """Send a WhatsApp message via Twilio REST API. Returns True on success."""
    url = TWILIO_MESSAGES_URL.format(account_sid=account_sid)
    credentials = base64.b64encode(
        f"{account_sid}:{auth_token}".encode()
    ).decode()

    payload = urllib.parse.urlencode({
        "From": to_whatsapp_number(from_number),
        "To": to_whatsapp_number(to_number),
        "Body": body,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            logger.info(
                "WhatsApp sent to %s — SID: %s", to_number, result.get("sid")
            )
            return True
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Twilio HTTP %d to %s: %s", exc.code, to_number, error_body)
        return False
    except Exception as exc:
        logger.exception("Twilio send failed to %s: %s", to_number, exc)
        return False


# ---------------------------------------------------------------------------
# Response message builders
# ---------------------------------------------------------------------------

def msg_ask_for_more_emails(emails_added: int, email_limit: int) -> str:
    remaining = email_limit - emails_added
    return (
        f"✅ Got it. You have {remaining} email slot{'s' if remaining != 1 else ''} "
        f"remaining.\n\n"
        f"Send another email address to monitor, or reply *DONE* to continue."
    )


def msg_ask_password_manager() -> str:
    return (
        "One quick question to personalise your protection:\n\n"
        "Do you use a password manager like *Bitwarden*, *1Password*, *LastPass*, *Dashlane*, or *Proton Pass*?\n\n"
        "Reply *YES* or *NO*."
    )


def msg_onboarding_complete(email_limit: int, is_business: bool) -> str:
    business_note = (
        "\n\nTo add a team member, reply *ADD* followed by their phone number "
        "(e.g. *ADD +16175551234*). They'll receive their own onboarding message."
        if is_business else ""
    )
    return (
        "🛡️ *You're all set.*\n\n"
        "Your first breach scan runs within the hour. If I find anything, "
        "I'll alert you here with a severity score and walk you through exactly what to do.\n\n"
        f"Reply *HELP* any time to see available commands.{business_note}"
    )


def msg_help(is_business: bool, is_employee: bool = False) -> str:
    commands = (
        "*Available commands:*\n\n"
        "• *SWEEP* — 5-minute Email Security Sweep (closes backdoors that survive password resets)\n"
        "• *RESET* — Strong password guide (run after completing your Email Security Sweep)\n"
        "• *SESSIONS* — Revoke active sessions and OAuth tokens across Google, Microsoft, and social media\n"
        "• *REUSE* — Check cross-account password reuse step by step\n"
        "• *MANAGER* — Get a free Bitwarden password manager setup guide\n"
        "• *PHONE* — Carrier hardening steps to protect your number from SIM swap and smishing\n"
        "• *OTP* — You received an unexpected verification code — get immediate steps\n"
        "• *SMS* — Forward a suspicious text for analysis (reply SMS followed by the message)\n"
        "• *SAFE* — Confirm you have read a vishing or session hijacking warning\n"
        "• *CALL* — You received a suspicious call — get immediate steps\n"
    )
    if is_business and not is_employee:
        commands += "• *ADD +1XXXXXXXXXX* — Add a team member for monitoring\n"
    commands += "\nReply any command to get started."
    return commands


def msg_sweep() -> str:
    return (
        "🔍 *Email Security Sweep — 5 minutes to close the backdoors*\n\n"
        "Attackers plant these after a breach. They survive password resets.\n\n"
        "*Step 1 — Check email forwarding rules*\n"
        "Gmail: Settings → See all settings → Forwarding and POP/IMAP\n"
        "Outlook: Settings → Mail → Forwarding\n"
        "Yahoo: Settings → Mailboxes → your address → Forwarding\n"
        "→ Delete any rule you did not create.\n\n"
        "*Step 2 — Check recovery email and phone*\n"
        "Gmail: myaccount.google.com/security\n"
        "Yahoo: account.yahoo.com/security\n"
        "→ Remove any recovery contact you do not recognise.\n\n"
        "*Step 3 — Check inbox filters*\n"
        "Attackers create rules that silently delete security alerts, password reset "
        "emails, and bank notifications — so you never see warnings about suspicious activity.\n"
        "Gmail: Settings → Filters and Blocked Addresses\n"
        "→ Delete any filter that deletes, skips inbox, or forwards emails you did not create.\n"
        "Outlook: Settings → Rules → delete unknown rules.\n\n"
        "*Step 4 — Review connected apps*\n"
        "Gmail: myaccount.google.com/permissions\n"
        "Yahoo: account.yahoo.com/security/connected-apps\n"
        "→ Revoke anything unrecognised.\n\n"
        "*Step 5 — Check active sessions*\n"
        "Gmail: myaccount.google.com/device-activity\n"
        "Yahoo: account.yahoo.com/security/recent-activity\n"
        "→ Sign out of all unknown sessions.\n\n"
        "✅ *Sweep complete. All 5 checks done.*\n\n"
        "Reply *RESET* for a strong password guide — the next step after closing every backdoor.\n"
        "Reply *MANAGER* for a free Bitwarden password manager setup guide."
    )


def msg_reset() -> str:
    return (
        "🔑 *Strong Password Guide — reset after your sweep*\n\n"
        "Now that you have closed every inbox backdoor, reset your password for "
        "the breached service.\n\n"
        "*Rules for a strong password:*\n"
        "→ Minimum 16 characters\n"
        "→ Use a passphrase: 3 random words + a number + a symbol "
        "(e.g. *Coffee-Balloon-River7!*)\n"
        "→ Never reuse this password on any other service\n"
        "→ Never share it — not by SMS, not by call, not by email\n\n"
        "*Where to reset:*\n"
        "Go directly to the breached service's website — "
        "do not click a reset link in an email unless you requested it yourself.\n\n"
        "*After resetting:*\n"
        "→ Enable two-factor authentication (use an authenticator app, not SMS if possible)\n"
        "→ If you reused this password elsewhere, change it on those accounts too\n\n"
        "Reply *MANAGER* to set up Bitwarden — a free password manager that generates and "
        "remembers strong unique passwords for every service.\n\n"
        "Reply *HELP* to see all available commands."
    )


def msg_reuse_step(step_index: int) -> str:
    """Return the cross-account reuse check for a given step index."""
    if step_index >= len(CROSS_ACCOUNT_SERVICES):
        return (
            "✅ *Cross-account check complete.*\n\n"
            "Change passwords on any accounts you replied YES to — "
            "use a unique password for each one.\n\n"
            "Reply *MANAGER* to get a free Bitwarden setup guide "
            "so you never have to remember them."
        )
    service, risk = CROSS_ACCOUNT_SERVICES[step_index]
    return (
        f"*Account {step_index + 1} of {len(CROSS_ACCOUNT_SERVICES)}*\n\n"
        f"*{service}*\n"
        f"_{risk}_\n\n"
        f"Did you use the same password here as the breached account?\n"
        f"Reply *YES* to flag it for a change, or *NO* to continue."
    )


def msg_manager() -> str:
    return (
        "🔐 *Free Password Manager Setup — Bitwarden*\n\n"
        "Bitwarden is free, open-source, and independently audited. "
        "Here's how to get started in 5 minutes:\n\n"
        "*Step 1* — Go to bitwarden.com and create a free account\n"
        "*Step 2* — Choose a strong master password (use a passphrase: "
        "3 random words + a number)\n"
        "*Step 3* — Install the browser extension (Chrome/Firefox/Safari)\n"
        "*Step 4* — Install the mobile app (iOS or Android)\n"
        "*Step 5* — Enable biometric unlock (Face ID / fingerprint)\n"
        "*Step 6* — As you log into sites, let Bitwarden save each password\n"
        "*Step 7* — Enable the Bitwarden breach report "
        "(Tools → Breach Report in the web vault)\n\n"
        "💡 *Master password tip:* Write it on paper and store it somewhere "
        "physically safe — not in email.\n\n"
        "Reply *HELP* to see all available commands."
    )


def msg_phone_hardening(subscription_tier: str) -> str:
    base = (
        "📱 *Phone Number Protection — Carrier Hardening Steps*\n\n"
        "Your phone number is a target for two related attacks:\n"
        "→ *SIM swap* — attacker convinces your carrier to move your number to their SIM, "
        "intercepting every SMS code you receive\n"
        "→ *Smishing* — fraudulent texts impersonate your bank, carrier, or delivery services "
        "to steal credentials or carrier PINs. Attackers often use smishing to gather the "
        "information needed to execute a SIM swap.\n\n"
        "These steps lock your carrier account against both attacks.\n\n"
        "⚠️ *Your carrier will never text or call asking for your PIN. "
        "Any message asking for it is an attack.*\n\n"
    )
    if subscription_tier in BUSINESS_TIERS:
        carrier_steps = (
            "*AT&T*\n"
            "→ Enable Wireless Account Lock: att.com/accountlock\n"
            "→ Add a passcode to your account\n"
            "→ Review eSIM profiles: myAT&T app → Account → Device Management\n\n"
            "*T-Mobile*\n"
            "→ Enable SIM Protection: account.t-mobile.com → Profile → SIM Protection\n"
            "→ Set a PIN/passcode on your account\n"
            "→ Audit eSIM Profiles: T-Mobile app → Account → SIM & eSIM\n\n"
            "*Verizon*\n"
            "→ Enable Number Lock: verizon.com/myverizon → Account → Number Lock\n"
            "→ Set a PIN/passcode on your account\n"
            "→ Review eSIM: My Verizon app → Devices → Manage eSIM\n\n"
            "*All carriers*\n"
            "→ Never give out your account PIN on a phone call — carriers will never ask\n"
            "→ Set a unique carrier PIN not used anywhere else\n"
        )
    else:
        carrier_steps = (
            "*Lock your carrier account:*\n"
            "• AT&T: att.com/accountlock\n"
            "• T-Mobile: Account → Profile → SIM Protection\n"
            "• Verizon: verizon.com/myverizon → Number Lock\n\n"
            "→ Set a unique PIN/passcode on your carrier account\n"
            "→ Never share your account PIN — carriers will never call to ask for it\n\n"
            "💡 Business Shield plans include full carrier hardening walkthroughs "
            "and eSIM profile audit guidance."
        )
    return base + carrier_steps + "\n\nReply *HELP* to see all available commands."


def msg_employee_welcome(admin_tier: str) -> str:
    email_limit = EMAIL_LIMITS.get(admin_tier, 2)
    return (
        "🛡️ *Welcome to RelayShield — your employer has added you for protection.*\n\n"
        "I'm an AI security assistant. I'll monitor your work credentials, "
        "alert you here if anything is found, and walk you through every fix.\n\n"
        f"To get started: what's your work email address? "
        f"You can add up to {email_limit} addresses."
    )


def msg_vishing_safe() -> str:
    return (
        "✅ *Good. You are prepared.*\n\n"
        "Keep these rules in mind for any unexpected call:\n"
        "→ Never confirm personal details to an inbound caller\n"
        "→ Never read an OTP code — no legitimate company asks for this\n"
        "→ Hang up and call back on the official number\n"
        "→ Urgency is the attack — slow down\n\n"
        "Reply *SWEEP* to run your Email Security Sweep, or *HELP* to see all commands."
    )


def msg_vishing_call() -> str:
    return (
        "🚨 *If you believe you have received a vishing call — act now.*\n\n"
        "*Step 1 — Do not call them back on any number they gave you.*\n"
        "Look up the official number on the company's website independently.\n\n"
        "*Step 2 — Did you share any of these?*\n"
        "→ OTP or verification code → Contact the service immediately to lock your account\n"
        "→ Bank details → Call your bank's fraud line from the number on your card\n"
        "→ Account PIN or password → Change it now before doing anything else\n"
        "→ Remote access granted → Disconnect internet, contact your bank and carrier\n\n"
        "*Step 3 — Report the call*\n"
        "→ FTC (US): reportfraud.ftc.gov\n"
        "→ FCC (carrier impersonation): fcc.gov/consumers/guides/filing-informal-complaint\n"
        "→ Your carrier fraud line: AT&T 1-800-331-0500 / T-Mobile 1-877-778-2106 / Verizon 1-800-922-0204\n\n"
        "*Step 4 — Run your Email Security Sweep*\n"
        "Vishing often runs alongside inbox takeover. Reply *SWEEP* to check for backdoors now.\n\n"
        "— RelayShield"
    )


def msg_unexpected_otp() -> str:
    """
    Response when user reports receiving an OTP they did not request.
    This is a strong signal of an active account takeover attempt or
    credential stuffing in progress. May also be a SIM swap precursor
    if the OTP is carrier-related.
    """
    return (
        "🚨 *Unexpected OTP — an account takeover attempt may be in progress.*\n\n"
        "An OTP you did not request means someone is actively trying to log in to one "
        "of your accounts using your credentials right now.\n\n"
        "*Step 1 — Do NOT share the OTP with anyone.*\n"
        "No legitimate company — not your bank, not your carrier, not any tech support — "
        "will ever call or text asking you to read back an OTP. "
        "If anyone contacts you asking for this code, that contact is the attack.\n\n"
        "*Step 2 — Identify which account sent the OTP.*\n"
        "The sender name or message content will indicate the service. "
        "Go directly to that service by typing the URL — do not click any link in the text.\n\n"
        "*Step 3 — Lock the account immediately.*\n"
        "→ Change your password for that account now\n"
        "→ Check for active sessions you don't recognise — reply *SESSIONS* for a guided walkthrough\n"
        "→ If it's your bank — call the fraud line on the back of your card\n"
        "→ If it's your mobile carrier — call them immediately; this may be a SIM swap attempt\n\n"
        "*Step 4 — Run your Email Security Sweep.*\n"
        "If an attacker has your credentials, they may also have inbox access. "
        "Reply *SWEEP* to check for forwarding rules and backdoors.\n\n"
        "Reply *CALL* if you also received a suspicious phone call alongside this OTP.\n\n"
        "— RelayShield"
    )


def msg_sessions() -> str:
    """
    Guided active session revocation across Google, Microsoft, and social media.
    Triggered by SESSIONS command or when session token exposure detected in a breach.
    Critical ordering note: revoke BEFORE changing password so attacker is forced
    out immediately regardless of whether they already have the password.
    """
    return (
        "🔐 *Active Session Audit — revoke access before an attacker uses it*\n\n"
        "A stolen session token gives full account access — no password or 2FA needed. "
        "Complete all 4 steps in order.\n\n"
        "*Step 1 — Google: sign out unknown devices*\n"
        "→ myaccount.google.com/device-activity\n"
        "→ Sign out of every device you don't recognise\n\n"
        "*Step 2 — Google: revoke third-party app access*\n"
        "→ myaccount.google.com/permissions\n"
        "→ Remove any app you don't recognise or no longer use\n\n"
        "*Step 3 — Microsoft: sign out unknown sessions*\n"
        "→ account.microsoft.com/privacy/activity\n"
        "→ Sign out of all unknown sessions\n"
        "→ account.microsoft.com/permissions → remove unknown apps\n\n"
        "*Step 4 — Social media*\n"
        "Facebook: Settings → Security and Login → Where You're Logged In\n"
        "Instagram: Settings → Security → Login Activity\n"
        "→ Log out of all sessions you don't recognise\n\n"
        "⚠️ *Complete steps 1–3 BEFORE changing your password.*\n"
        "Revoking the session forces the attacker out immediately.\n"
        "Changing the password first does nothing if they already have your session token.\n\n"
        "✅ *Session audit complete.*\n\n"
        "Reply *SWEEP* to also check for email backdoors (forwarding rules, rogue recovery options).\n"
        "Reply *HELP* to see all available commands.\n\n"
        "— RelayShield"
    )


def msg_unknown_command() -> str:
    return (
        "I didn't recognise that command.\n\n"
        "Reply *HELP* to see everything I can do."
    )


# ---------------------------------------------------------------------------
# Onboarding handlers
# ---------------------------------------------------------------------------

def handle_awaiting_email_1(
    user: dict,
    message_body: str,
    twilio_creds: tuple,
) -> str:
    """First email address — validate, store, ask for more or move on."""
    account_sid, auth_token, from_number = twilio_creds
    user_id = user["user_id"]
    tier = user.get("subscription_tier", TIER_PERSONAL)
    email_limit = EMAIL_LIMITS.get(tier, 3)
    to_number = user["whatsapp_number"]
    email = message_body.strip().lower()

    if not is_valid_email(email):
        reply = (
            "That doesn't look like a valid email address. "
            "Please send your email address (e.g. *name@example.com*)."
        )
        send_whatsapp(to_number, reply, account_sid, auth_token, from_number)
        return "invalid_email"

    add_monitored_email(user_id, email)

    if email_limit == 1:
        # Edge case: move straight to password manager question
        update_user(user_id, {
            "onboarding_state": STATE_PASSWORD_MANAGER,
            "emails_added": 1,
        })
        send_whatsapp(to_number, msg_ask_password_manager(), account_sid, auth_token, from_number)
    else:
        update_user(user_id, {
            "onboarding_state": STATE_MORE_EMAILS,
            "emails_added": 1,
        })
        send_whatsapp(
            to_number,
            msg_ask_for_more_emails(1, email_limit),
            account_sid, auth_token, from_number,
        )
    return "email_1_added"


def handle_awaiting_more_emails(
    user: dict,
    message_body: str,
    twilio_creds: tuple,
) -> str:
    """Subsequent emails or DONE command."""
    account_sid, auth_token, from_number = twilio_creds
    user_id = user["user_id"]
    tier = user.get("subscription_tier", TIER_PERSONAL)
    email_limit = EMAIL_LIMITS.get(tier, 3)
    emails_added = int(user.get("emails_added", 1))
    to_number = user["whatsapp_number"]
    body = message_body.strip()

    if body.upper() == "DONE":
        update_user(user_id, {"onboarding_state": STATE_PASSWORD_MANAGER})
        send_whatsapp(to_number, msg_ask_password_manager(), account_sid, auth_token, from_number)
        return "done_collecting_emails"

    email = body.lower()
    if not is_valid_email(email):
        reply = (
            "That doesn't look like a valid email address.\n\n"
            "Send another email to monitor, or reply *DONE* to continue."
        )
        send_whatsapp(to_number, reply, account_sid, auth_token, from_number)
        return "invalid_email"

    if email_already_monitored(user_id, email):
        reply = (
            f"*{email}* is already being monitored.\n\n"
            "Send another email, or reply *DONE* to continue."
        )
        send_whatsapp(to_number, reply, account_sid, auth_token, from_number)
        return "duplicate_email"

    add_monitored_email(user_id, email)
    emails_added += 1

    if emails_added >= email_limit:
        # Tier limit reached — move to next stage automatically
        update_user(user_id, {
            "onboarding_state": STATE_PASSWORD_MANAGER,
            "emails_added": emails_added,
        })
        limit_msg = (
            f"✅ *{email}* added. You've reached your {email_limit}-email limit.\n\n"
        )
        send_whatsapp(
            to_number,
            limit_msg + msg_ask_password_manager(),
            account_sid, auth_token, from_number,
        )
    else:
        update_user(user_id, {"emails_added": emails_added})
        send_whatsapp(
            to_number,
            msg_ask_for_more_emails(emails_added, email_limit),
            account_sid, auth_token, from_number,
        )
    return f"email_{emails_added}_added"


def handle_awaiting_password_manager(
    user: dict,
    message_body: str,
    twilio_creds: tuple,
) -> str:
    """YES/NO password manager question."""
    account_sid, auth_token, from_number = twilio_creds
    user_id = user["user_id"]
    tier = user.get("subscription_tier", TIER_PERSONAL)
    to_number = user["whatsapp_number"]
    body = message_body.strip().upper()

    if body not in ("YES", "NO"):
        send_whatsapp(
            to_number,
            "Please reply *YES* or *NO* — do you use a password manager?",
            account_sid, auth_token, from_number,
        )
        return "invalid_response"

    pm_user = body == "YES"
    update_user(user_id, {
        "onboarding_state": STATE_ACTIVE,
        "password_manager_user": pm_user,
    })

    is_business = tier in BUSINESS_TIERS
    email_limit = EMAIL_LIMITS.get(tier, 3)
    completion_msg = msg_onboarding_complete(email_limit, is_business)

    if pm_user:
        completion_msg += (
            "\n\n💡 Since you use a password manager, I'll include a master password "
            "alert if your credentials ever appear in a breach."
        )

    send_whatsapp(to_number, completion_msg, account_sid, auth_token, from_number)
    logger.info(
        "Onboarding complete — user_id=%s tier=%s pm_user=%s",
        user_id, tier, pm_user,
    )
    return "onboarding_complete"


# ---------------------------------------------------------------------------
# Employee onboarding handlers
# ---------------------------------------------------------------------------

def handle_employee_email_1(
    user: dict,
    message_body: str,
    twilio_creds: tuple,
) -> str:
    """Employee first email collection."""
    account_sid, auth_token, from_number = twilio_creds
    user_id = user["user_id"]
    admin_user_id = user.get("admin_user_id", "")
    tier = user.get("subscription_tier", TIER_BASIC)
    email_limit = EMAIL_LIMITS.get(tier, 2)
    to_number = user["whatsapp_number"]
    email = message_body.strip().lower()

    if not is_valid_email(email):
        send_whatsapp(
            to_number,
            "That doesn't look like a valid email. Please send your work email address.",
            account_sid, auth_token, from_number,
        )
        return "invalid_email"

    add_monitored_email(user_id, email)

    if email_limit == 1:
        update_user(user_id, {
            "onboarding_state": STATE_EMP_ACTIVE,
            "emails_added": 1,
        })
        send_whatsapp(
            to_number,
            "✅ You're all set. I'll alert you here if your credentials appear in a breach.",
            account_sid, auth_token, from_number,
        )
    else:
        update_user(user_id, {
            "onboarding_state": STATE_EMP_MORE_EMAILS,
            "emails_added": 1,
        })
        send_whatsapp(
            to_number,
            msg_ask_for_more_emails(1, email_limit),
            account_sid, auth_token, from_number,
        )
    return "employee_email_1_added"


def handle_employee_more_emails(
    user: dict,
    message_body: str,
    twilio_creds: tuple,
) -> str:
    """Employee additional email or DONE."""
    account_sid, auth_token, from_number = twilio_creds
    user_id = user["user_id"]
    tier = user.get("subscription_tier", TIER_BASIC)
    email_limit = EMAIL_LIMITS.get(tier, 2)
    emails_added = int(user.get("emails_added", 1))
    to_number = user["whatsapp_number"]
    body = message_body.strip()

    if body.upper() == "DONE":
        update_user(user_id, {"onboarding_state": STATE_EMP_ACTIVE})
        send_whatsapp(
            to_number,
            "✅ You're all set. I'll alert you here if your credentials appear in a breach.\n\n"
            "Reply *HELP* to see available commands.",
            account_sid, auth_token, from_number,
        )
        return "employee_done"

    email = body.lower()
    if not is_valid_email(email):
        send_whatsapp(
            to_number,
            "That doesn't look like a valid email. Send another or reply *DONE* to continue.",
            account_sid, auth_token, from_number,
        )
        return "invalid_email"

    if email_already_monitored(user_id, email):
        send_whatsapp(
            to_number,
            f"*{email}* is already being monitored. Send another or reply *DONE*.",
            account_sid, auth_token, from_number,
        )
        return "duplicate_email"

    add_monitored_email(user_id, email)
    emails_added += 1

    if emails_added >= email_limit:
        update_user(user_id, {
            "onboarding_state": STATE_EMP_ACTIVE,
            "emails_added": emails_added,
        })
        send_whatsapp(
            to_number,
            f"✅ *{email}* added. You've reached your {email_limit}-email limit. "
            "I'll alert you here if your credentials appear in a breach.\n\n"
            "Reply *HELP* to see available commands.",
            account_sid, auth_token, from_number,
        )
    else:
        update_user(user_id, {"emails_added": emails_added})
        send_whatsapp(
            to_number,
            msg_ask_for_more_emails(emails_added, email_limit),
            account_sid, auth_token, from_number,
        )
    return f"employee_email_{emails_added}_added"


# ---------------------------------------------------------------------------
# Active command handlers
# ---------------------------------------------------------------------------

def handle_active_message(
    user: dict,
    message_body: str,
    twilio_creds: tuple,
) -> str:
    """Route commands for fully onboarded users."""
    account_sid, auth_token, from_number = twilio_creds
    user_id = user["user_id"]
    tier = user.get("subscription_tier", TIER_PERSONAL)
    to_number = user["whatsapp_number"]
    is_business = tier in BUSINESS_TIERS
    is_employee = bool(user.get("admin_user_id"))
    body = message_body.strip().upper()

    # --- SWEEP ---
    if body == "SWEEP":
        send_whatsapp(to_number, msg_sweep(), account_sid, auth_token, from_number)
        return "sweep_sent"

    # --- RESET ---
    if body == "RESET":
        send_whatsapp(to_number, msg_reset(), account_sid, auth_token, from_number)
        return "reset_sent"

    # --- REUSE ---
    if body == "REUSE":
        reuse_step = int(user.get("reuse_step", 0))
        update_user(user_id, {"reuse_step": 1})
        send_whatsapp(
            to_number, msg_reuse_step(0), account_sid, auth_token, from_number
        )
        return "reuse_started"

    # --- REUSE YES/NO continuation ---
    if body in ("YES", "NO"):
        reuse_step = int(user.get("reuse_step", 0))
        if reuse_step > 0:
            next_step = reuse_step
            update_user(user_id, {"reuse_step": next_step + 1})
            send_whatsapp(
                to_number,
                msg_reuse_step(next_step),
                account_sid, auth_token, from_number,
            )
            return f"reuse_step_{next_step}_answered"

    # --- MANAGER ---
    if body == "MANAGER":
        send_whatsapp(to_number, msg_manager(), account_sid, auth_token, from_number)
        return "manager_sent"

    # --- PHONE ---
    if body == "PHONE":
        send_whatsapp(
            to_number, msg_phone_hardening(tier), account_sid, auth_token, from_number
        )
        return "phone_hardening_sent"

    # --- SESSIONS (active session revocation walkthrough) ---
    if body == "SESSIONS":
        send_whatsapp(to_number, msg_sessions(), account_sid, auth_token, from_number)
        return "sessions_audit_sent"

    # --- SAFE (vishing warning acknowledged) ---
    if body == "SAFE":
        send_whatsapp(to_number, msg_vishing_safe(), account_sid, auth_token, from_number)
        return "vishing_safe_ack"

    # --- CALL (user received a suspicious call) ---
    if body == "CALL":
        send_whatsapp(to_number, msg_vishing_call(), account_sid, auth_token, from_number)
        return "vishing_call_reported"

    # --- OTP (user received an unexpected OTP they did not request) ---
    if body == "OTP":
        send_whatsapp(to_number, msg_unexpected_otp(), account_sid, auth_token, from_number)
        return "unexpected_otp_reported"

    # --- SMS with no content — prompt user to include the message ---
    if body == "SMS":
        send_whatsapp(
            to_number,
            "📨 *To analyse a suspicious text, reply with SMS followed by the message.*\n\n"
            "Example: *SMS https://suspicious-link.com* or paste the full text of the message.\n\n"
            "RelayShield will check any links for malware and phishing.",
            account_sid, auth_token, from_number,
        )
        return "sms_prompt_sent"

    # --- SMS (user forwards a suspicious text for analysis) ---
    # Extracts URLs from the forwarded text, checks via Google Safe Browsing
    # API v4, and returns a verdict: malicious / clean / no URLs found.
    # Falls back to guidance-only response if GSB API is unavailable.
    if body.startswith("SMS "):
        forwarded_text = message_body.strip()[4:].strip()
        urls = extract_urls(forwarded_text)

        if urls:
            try:
                gsb_api_key = get_gsb_api_key()
                gsb_result = check_urls_safe_browsing(urls, gsb_api_key)
            except Exception as e:
                logger.error("Failed to retrieve GSB API key or run analysis: %s", e)
                gsb_result = {"matches": [], "error": str(e)}
        else:
            gsb_result = {"matches": [], "error": None}

        response_text = build_sms_analysis_response(forwarded_text, urls, gsb_result)
        send_whatsapp(to_number, response_text, account_sid, auth_token, from_number)
        logger.info(
            "SMS analysis complete — urls_found=%d threats=%d error=%s",
            len(urls),
            len(gsb_result.get("matches", [])),
            gsb_result.get("error"),
        )
        return "suspicious_sms_analysed"

    # --- HELP ---
    if body == "HELP":
        send_whatsapp(
            to_number, msg_help(is_business, is_employee), account_sid, auth_token, from_number
        )
        return "help_sent"

    # --- ADD (Business tier admin only) ---
    if body.startswith("ADD ") and is_business and not is_employee:
        raw_phone = message_body.strip()[4:].strip()
        phone = normalise_phone(raw_phone)

        if not is_valid_phone(phone):
            send_whatsapp(
                to_number,
                "Please provide a valid phone number in international format.\n"
                "Example: *ADD +16175551234*",
                account_sid, auth_token, from_number,
            )
            return "invalid_employee_phone"

        # Check seat limit
        seat_limit = SEAT_LIMITS.get(tier, 5)
        current_employees = count_employees(user_id)
        if current_employees >= seat_limit:
            send_whatsapp(
                to_number,
                f"You've reached your {seat_limit}-seat limit for your plan.\n\n"
                "Contact us to upgrade to a higher tier.",
                account_sid, auth_token, from_number,
            )
            return "seat_limit_reached"

        # Create employee record
        employee_id = create_employee_record(phone, user_id, tier)

        # Confirm to admin
        send_whatsapp(
            to_number,
            f"✅ Team member added. They'll receive an onboarding message at {phone} shortly.",
            account_sid, auth_token, from_number,
        )

        # Send welcome to employee
        send_whatsapp(
            phone,
            msg_employee_welcome(tier),
            account_sid, auth_token, from_number,
        )

        logger.info(
            "Employee added — admin_user_id=%s employee_user_id=%s phone=%s",
            user_id, employee_id, phone,
        )
        return "employee_added"

    # --- Unknown ---
    send_whatsapp(
        to_number, msg_unknown_command(), account_sid, auth_token, from_number
    )
    return "unknown_command"


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def handler(event, context):
    """
    Entry point for API Gateway → Lambda (Twilio inbound webhook).

    Twilio sends form-encoded POST body with fields including:
      From  — sender's WhatsApp number (whatsapp:+1XXXXXXXXXX)
      Body  — message text
      X-Twilio-Signature header for verification
    """
    # --- Parse form-encoded body ---
    raw_body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body).decode("utf-8")

    params = dict(urllib.parse.parse_qsl(raw_body))
    from_number = params.get("From", "")
    message_body = params.get("Body", "").strip()

    logger.info("Inbound WhatsApp from=%s body_len=%d", from_number, len(message_body))

    if not from_number:
        logger.warning("No From number in webhook payload.")
        return {"statusCode": 400, "body": "Missing From number"}

    # --- Retrieve Twilio credentials ---
    try:
        account_sid, auth_token, twilio_from = get_twilio_credentials()
    except Exception as exc:
        logger.exception("Failed to retrieve Twilio credentials: %s", exc)
        return {"statusCode": 500, "body": "Credential retrieval failed"}

    twilio_creds = (account_sid, auth_token, twilio_from)

    # --- Verify Twilio signature ---
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    twilio_sig = headers.get("x-twilio-signature", "")
    # HTTP API v2.0 uses rawPath which includes the stage prefix (/prod/webhook/whatsapp)
    # This must match the exact URL Twilio used when computing the signature
    raw_path = (
        event.get("rawPath")
        or event.get("requestContext", {}).get("http", {}).get("path")
        or "/prod/webhook/whatsapp"
    )
    webhook_url = f"https://{headers.get('host', '')}{raw_path}"
    logger.info("Twilio signature check — url=%s sig=%s", webhook_url, twilio_sig[:10] if twilio_sig else "none")

    if not twilio_sig or not verify_twilio_signature(auth_token, twilio_sig, webhook_url, params):
        logger.warning("Twilio signature verification failed — request rejected. url=%s", webhook_url)
        return {"statusCode": 403, "body": "Invalid Twilio signature"}

    # --- Look up user ---
    user = get_user_by_whatsapp(from_number)

    if not user:
        logger.warning("No user found for WhatsApp number: %s", from_number)
        # Send a helpful message rather than silently failing
        send_whatsapp(
            from_number,
            "👋 Welcome! It looks like your account isn't set up yet.\n\n"
            "Visit *relayshield.net* to sign up and get started.",
            account_sid, auth_token, twilio_from,
        )
        return {"statusCode": 200, "body": "No user found"}

    onboarding_state = user.get("onboarding_state", STATE_ACTIVE)

    # --- Route by state ---
    if onboarding_state == STATE_EMAIL_1:
        result = handle_awaiting_email_1(user, message_body, twilio_creds)

    elif onboarding_state == STATE_MORE_EMAILS:
        result = handle_awaiting_more_emails(user, message_body, twilio_creds)

    elif onboarding_state == STATE_PASSWORD_MANAGER:
        result = handle_awaiting_password_manager(user, message_body, twilio_creds)

    elif onboarding_state == STATE_EMP_EMAIL_1:
        result = handle_employee_email_1(user, message_body, twilio_creds)

    elif onboarding_state == STATE_EMP_MORE_EMAILS:
        result = handle_employee_more_emails(user, message_body, twilio_creds)

    elif onboarding_state in (STATE_ACTIVE, STATE_EMP_ACTIVE):
        result = handle_active_message(user, message_body, twilio_creds)

    else:
        logger.warning(
            "Unknown onboarding_state '%s' for user_id=%s",
            onboarding_state, user.get("user_id"),
        )
        result = "unknown_state"

    logger.info(
        "Handled message from=%s state=%s result=%s",
        from_number, onboarding_state, result,
    )

    # Twilio expects a 200 with TwiML or empty body
    return {"statusCode": 200, "body": ""}
