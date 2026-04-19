"""
RelayShield Breach Monitor Lambda
Scans monitored emails against HIBP v3, records new breach alerts,
and sends WhatsApp alerts via Twilio with Claude AI severity scoring
and remediation guidance.

Item 2 additions:
  - Password exposure detection from HIBP DataClasses ("Passwords" field)
  - Severity bump when passwords exposed (one level up; HIGH minimum if
    password_manager_user = True)
  - Cross-account reuse walkthrough triggered by REUSE reply command
  - Password manager master password alert when password_manager_user = True
  - MANAGER reply command delivers free Bitwarden setup guide

Strategic note: RelayShield does NOT check Pwned Passwords hashes or ask
users to submit passwords. Detection is not our lane — response is.
"""

import base64
import json
import logging
import time
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
# AWS clients (module-level for Lambda container reuse)
# ---------------------------------------------------------------------------

secrets_client = boto3.client("secretsmanager")
dynamodb = boto3.resource("dynamodb")

MONITORED_EMAILS_TABLE = "relayshield_monitored_emails"
BREACH_ALERTS_TABLE = "relayshield_breach_alerts"
USERS_TABLE = "relayshield_users"

HIBP_SECRET_NAME = "relayshield/hibp_api_key"
TWILIO_SID_SECRET = "relayshield/twilio_account_sid"
TWILIO_TOKEN_SECRET = "relayshield/twilio_auth_token"
TWILIO_FROM_SECRET = "relayshield/twilio_whatsapp_number"
ANTHROPIC_SECRET_NAME = "relayshield/anthropic_api_key"

HIBP_BASE_URL = "https://haveibeenpwned.com/api/v3/breachedaccount/"
TWILIO_MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"

# WhatsApp Message Template — pre-approved by Meta, can be sent at any time
# regardless of the 24-hour messaging window (error 63016).
# Variables: {{1}}=email, {{2}}=source, {{3}}=data classes, {{4}}=breach date
BREACH_ALERT_TEMPLATE_SID = "HXdb9685fae910b63fcfe056fbf6d03bc6"

# Twilio error code returned when the 24-hour session window is closed
TWILIO_ERROR_OUTSIDE_WINDOW = 63016

USER_AGENT = "RelayShield-BreachMonitor"
CLAUDE_MODEL = "claude-3-haiku-20240307"
CLAUDE_MAX_TOKENS = 1024

# HIBP Pwned 1 plan: 10 RPM → 1 request per 6 seconds
REQUEST_DELAY_SECONDS = 6
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 10

# ---------------------------------------------------------------------------
# Alert filtering constants
# ---------------------------------------------------------------------------

# Breaches older than this are recorded in DynamoDB but never alerted on.
# Keeps the initial onboarding scan from flooding users with decade-old news.
MAX_BREACH_AGE_YEARS = 5

# Data classes considered high-value. A breach must expose at least one of
# these to generate a WhatsApp alert. Pure email/username-only breaches are
# recorded silently — they're low-actionability noise for most users.
HIGH_VALUE_DATA_CLASSES = {
    "passwords",
    "credit cards",
    "bank account numbers",
    "financial data",
    "social security numbers",
    "health records",
    "medical records",
    "passport numbers",
    "driver's licence numbers",
    "phone numbers",
    "physical addresses",
    "dates of birth",
    "government issued ids",
    "partial credit card data",
    "pins",
    "security questions and answers",
    # Session hijacking additions — auth token exposure is immediately
    # exploitable without requiring password or 2FA
    "auth tokens",
    "session cookies",
    "authentication tokens",
}

# Data classes that enable convincing vishing (voice phishing) calls.
# When any of these are exposed, a vishing preparedness warning is appended.
VISHING_DATA_CLASSES = {
    "phone numbers",
    "physical addresses",
    "bank account numbers",
    "partial credit card data",
    "carrier details",
    "account numbers",
    "dates of birth",
    "government issued ids",
}

# Identity document exposure → escalate to CRITICAL regardless of breach source.
# Attacker with SSN, passport, or driver's licence can impersonate the victim
# on a voice call to financial institutions, carriers, and government agencies.
IDENTITY_DOCUMENT_DATA_CLASSES = {
    "social security numbers",
    "passport numbers",
    "driver's licence numbers",
}

# Session token exposure → immediately exploitable without password or 2FA.
# Attacker replays the token from a different device to gain full account access.
# Distinct from credential exposure: revocation must happen before password reset.
SESSION_HIJACKING_DATA_CLASSES = {
    "auth tokens",
    "session cookies",
    "authentication tokens",
}

# High-risk accounts for cross-account reuse walkthrough
CROSS_ACCOUNT_SERVICES = [
    ("Gmail / Outlook / Yahoo Mail", "email — the master key to every other account"),
    ("Banking and financial apps", "direct access to money"),
    ("Amazon / PayPal / shopping accounts", "saved payment cards"),
    ("Apple ID / Google Account", "device access and app purchases"),
    ("Facebook / LinkedIn / social media", "identity and contact data"),
    ("Square / payment processing tools", "business bank account access"),
]

CLAUDE_SYSTEM_PROMPT = """You are RelayShield's AI security advisor. Your job is to assess breach severity and deliver concise, actionable WhatsApp alerts.

SEVERITY LEVELS:
CRITICAL — Email providers, financial institutions, healthcare, government. Act immediately.
HIGH — Social media, e-commerce with saved payment cards. Act within 24 hours.
MEDIUM — Shopping sites, forums, subscription services. Act within 1 week.
LOW — Gaming sites, old accounts with minimal PII. Note and monitor.

SEVERITY BUMP RULES:
→ If "Passwords" appears in exposed data types: bump severity one level (LOW→MEDIUM, MEDIUM→HIGH, HIGH→CRITICAL)
→ If password_manager_user = True AND passwords exposed: severity is HIGH minimum regardless of breach type
→ If "Social security numbers", "Passport numbers", or "Driver's licence numbers" appear in exposed data types: severity is CRITICAL regardless of breach source. These enable full identity impersonation on a voice call.

FORMATTING (WhatsApp markdown):
→ Use *text* for bold
→ Keep under 300 words total
→ No HTML
→ Use → for bullet points

MULTIPLE BREACHES:
If multiple breaches are provided, rank by severity and state clearly which to fix first.
Lead with: "⚠️ *X new breaches detected.* Fix in this order:"

PHONE NUMBER EXPOSURE:
If "Phone numbers" appears in exposed data types, add this block:
"📱 *Your phone number was exposed.*
Smishing campaigns — fraudulent texts impersonating your bank, carrier, or a delivery service — frequently follow phone number exposure in breaches. Attackers may already know your name and reference this breach to appear legitimate.
→ Do not click links in unexpected texts, even if they look official
→ Forward any suspicious text to RelayShield for analysis — reply *SMS* followed by the text
→ Reply *PHONE* for carrier PIN hardening steps to protect your number from SIM swap and smishing attacks"

VISHING WARNING — add when ANY of the following appear in exposed data types:
Phone numbers, Physical addresses, Bank account numbers, Partial credit card data, Dates of birth, Government issued IDs, Carrier details, Account numbers

Insert this block:
"☎️ *Vishing (AI voice scam) risk — read this before you get a call.*
Attackers use this exact data to impersonate your bank, mobile carrier, or a government agency on a phone call — using your real name and details so they sound legitimate.

For the next 30 days, if you receive any unexpected call:
→ Never confirm personal details to an inbound caller
→ Never read an OTP code to a caller — no legitimate company ever asks for this
→ Hang up and call back on the official number from the company's website
→ If the caller says the matter is urgent, that urgency is the attack

Reply *SAFE* to confirm you have read this, or *CALL* if you have already received a suspicious call."

SESSION TOKEN ESCALATION — add when "Auth tokens", "Session cookies", or "Authentication tokens" appear in exposed data types:
Severity is CRITICAL. Add this block immediately after the severity line:
"🍪 *CRITICAL: Active session tokens exposed.*
An attacker with your session token can access your accounts RIGHT NOW — no password or 2FA required. They do not need to log in.

Immediate steps (do these BEFORE changing your password):
→ Google: myaccount.google.com/device-activity — sign out all unknown devices
→ Google: myaccount.google.com/permissions — revoke all unrecognised apps
→ Microsoft: account.microsoft.com/privacy/activity — sign out unknown sessions
→ Change your passwords only AFTER revoking sessions — revoking first forces immediate logout regardless of whether the attacker has your password

Reply *SESSIONS* for a full guided session revocation walkthrough across all major accounts."

IDENTITY DOCUMENT ESCALATION — add when "Social security numbers", "Passport numbers", or "Driver's licence numbers" appear:
Severity is CRITICAL. Add this block immediately after the severity line:
"🪪 *CRITICAL: Identity document data exposed.*
Your [SSN / passport number / driver's licence] was in this breach. An attacker with this data can:
→ Impersonate you by phone to banks, carriers, and government agencies
→ Open new lines of credit in your name
→ File fraudulent tax returns or insurance claims

Immediate steps:
→ Place a *credit freeze* at all three bureaus: Equifax, Experian, TransUnion (free, takes 10 minutes at each bureau's website)
→ File an identity theft report at identitytheft.gov if fraud has already occurred
→ Contact your carrier and ask for a verbal passcode on your account

Reply *SAFE* once you have read this, or *CALL* if you believe you have already been targeted."

PASSWORD EXPOSURE — add when "Passwords" appears in exposed data types:
"🔑 *Your password was exposed.* Treat it as compromised regardless of whether you've changed it.
→ Reply *REUSE* to check which other accounts are at risk from password reuse — the most common way one breach becomes five."

AITM PHISHING WARNING — add when "Passwords" appears in exposed data types (append after the password block above, unless SESSION TOKEN ESCALATION already applied):
"⚠️ *2FA bypass risk — AiTM phishing (Tycoon 2FA / EvilProxy).*
Attackers use leaked credentials to create convincing fake login pages that sit between you and the real site. You complete your login including 2FA — the proxy captures your authenticated session token and replays it from the attacker's device. No password needed. No 2FA prompt. Full access.
→ Only log in to accounts via saved bookmarks or by typing the URL directly — never via a link in an email or text
→ After changing your password, reply *SESSIONS* to revoke all active sessions across Google, Microsoft, and social media"

PASSWORD MANAGER ALERT — add only when password_manager_user = True AND passwords exposed:
"🔐 *Password Manager Alert:* Your master password may have been tested against your password manager login. If your master password resembles your breached password:
→ Change your master password immediately
→ Enable biometric unlock
→ Store your recovery code offline — not in email"

CROSS-ACCOUNT REUSE WALKTHROUGH — when user replies REUSE:
Walk through each high-risk account one at a time. Ask YES or NO for each:
1. Gmail / Outlook / Yahoo Mail — the master key to every other account
2. Banking and financial apps — direct money access
3. Amazon / PayPal / shopping — saved payment cards
4. Apple ID / Google Account — device and purchase access
5. Facebook / LinkedIn / social media — identity and contacts
6. Square / payment tools — business bank account (if applicable)
For each YES: provide the specific account's password reset URL and steps, then move to next.
End with: "✅ Cross-account check complete. Reply *MANAGER* for a free Bitwarden password manager setup guide — 5 minutes to set up, protects every account you have."

MANAGER COMMAND — when user replies MANAGER:
Deliver a concise Bitwarden setup guide:
→ Go to bitwarden.com → Create account with a strong unique master password
→ Install the browser extension and mobile app
→ Import any saved passwords from your browser
→ Enable two-factor authentication on the Bitwarden account itself
→ Generate and save new unique passwords for your highest-risk accounts first
"Bitwarden is free, open source, and independently audited. It is the recommended password manager for RelayShield users."

ALWAYS END WITH:
"Before resetting your password, reply *SWEEP* for a 5-minute Email Security Sweep — closes inbox backdoors that survive password resets.

— RelayShield"
"""


# ---------------------------------------------------------------------------
# Secrets Manager
# ---------------------------------------------------------------------------

def get_secret_json(secret_name: str, key: str) -> str:
    """Retrieve a single key from a JSON-formatted secret."""
    logger.info("Retrieving secret: %s", secret_name)
    response = secrets_client.get_secret_value(SecretId=secret_name)
    secret = json.loads(response["SecretString"])
    return secret[key]


def get_secret_plaintext(secret_name: str) -> str:
    """Retrieve the raw string value from a plaintext secret."""
    logger.info("Retrieving secret: %s", secret_name)
    response = secrets_client.get_secret_value(SecretId=secret_name)
    return response["SecretString"].strip()


def get_hibp_api_key() -> str:
    return get_secret_json(HIBP_SECRET_NAME, "HIBP_API_KEY")


def get_twilio_credentials() -> tuple[str, str, str]:
    """Return (account_sid, auth_token, from_whatsapp_number)."""
    account_sid = get_secret_plaintext(TWILIO_SID_SECRET)
    auth_token = get_secret_plaintext(TWILIO_TOKEN_SECRET)
    from_number = get_secret_plaintext(TWILIO_FROM_SECRET)
    logger.info("Twilio credentials retrieved successfully.")
    return account_sid, auth_token, from_number


def get_anthropic_api_key() -> str:
    return get_secret_plaintext(ANTHROPIC_SECRET_NAME)


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def scan_monitored_emails() -> list[dict]:
    """Return all records from relayshield_monitored_emails."""
    table = dynamodb.Table(MONITORED_EMAILS_TABLE)
    items: list[dict] = []
    kwargs: dict = {}

    logger.info("Scanning table: %s", MONITORED_EMAILS_TABLE)
    while True:
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key

    logger.info("Found %d monitored email record(s).", len(items))
    return items


def get_user_record(user_id: str) -> dict | None:
    """
    Return the full user record from relayshield_users.
    Used to retrieve whatsapp_number, password_manager_user,
    subscription_tier, and any other user attributes.
    """
    table = dynamodb.Table(USERS_TABLE)
    response = table.get_item(Key={"user_id": user_id})
    item = response.get("Item")
    if not item:
        logger.warning("No user record found for user_id=%s", user_id)
        return None
    return item


def get_whatsapp_number_from_record(user_record: dict) -> str | None:
    """Extract and normalise the WhatsApp number from a user record."""
    number = user_record.get("whatsapp_number")
    if not number:
        logger.warning(
            "user_id=%s has no whatsapp_number field.", user_record.get("user_id")
        )
        return None
    if not number.startswith("whatsapp:"):
        number = f"whatsapp:{number}"
    return number


def get_existing_breach_names(user_id: str, email_address: str) -> set[str]:
    """Return breach names already recorded for this user/email pair."""
    table = dynamodb.Table(BREACH_ALERTS_TABLE)
    items: list[dict] = []
    kwargs: dict = {
        "FilterExpression": (
            Attr("user_id").eq(user_id) & Attr("email_address").eq(email_address)
        ),
    }

    while True:
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key

    existing = {item["breach_name"] for item in items}
    logger.debug(
        "User %s / %s already has %d recorded breach(es).",
        user_id, email_address, len(existing),
    )
    return existing


def write_breach_alert(
    user_id: str,
    email_address: str,
    breach_name: str,
    breach_date: str,
    data_types_exposed: list[str],
    alert_sent_at: str,
    passwords_exposed: bool = False,
) -> str:
    """Write a new breach alert record and return its alert_id."""
    table = dynamodb.Table(BREACH_ALERTS_TABLE)
    alert_id = str(uuid.uuid4())
    item = {
        "alert_id": alert_id,
        "user_id": user_id,
        "email_address": email_address,
        "breach_name": breach_name,
        "breach_date": breach_date,
        "data_types_exposed": data_types_exposed,
        "alert_sent_at": alert_sent_at,
        "remediation_status": "pending",
        "passwords_exposed": passwords_exposed,
    }
    table.put_item(Item=item)
    logger.info(
        "Wrote breach alert %s for user %s: breach=%s passwords_exposed=%s",
        alert_id, user_id, breach_name, passwords_exposed,
    )
    return alert_id


def update_last_checked(email_id: str, user_id: str, timestamp: str) -> None:
    """Update last_checked on a monitored email record."""
    table = dynamodb.Table(MONITORED_EMAILS_TABLE)
    table.update_item(
        Key={"email_id": email_id, "user_id": user_id},
        UpdateExpression="SET last_checked = :ts",
        ExpressionAttributeValues={":ts": timestamp},
    )
    logger.info("Updated last_checked for email_id=%s to %s", email_id, timestamp)


# ---------------------------------------------------------------------------
# Password exposure detection
# ---------------------------------------------------------------------------

def passwords_in_breach(data_types_exposed: list[str]) -> bool:
    """
    Return True if the breach exposed passwords.
    HIBP DataClasses uses 'Passwords' (capital P).
    """
    return any(
        "password" in dt.lower() for dt in data_types_exposed
    )


def any_passwords_exposed(new_breaches: list[dict]) -> bool:
    """Return True if any new breach in the batch exposed passwords."""
    return any(b.get("passwords_exposed", False) for b in new_breaches)


def is_breach_recent(breach_date: str, max_years: int = MAX_BREACH_AGE_YEARS) -> bool:
    """
    Return True if the breach occurred within the last max_years years.
    Breaches with no date default to True (alert to be safe).
    """
    if not breach_date:
        return True
    try:
        breach_dt = datetime.strptime(breach_date[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        cutoff_year = datetime.now(timezone.utc).year - max_years
        cutoff = datetime.now(timezone.utc).replace(year=cutoff_year)
        return breach_dt >= cutoff
    except ValueError:
        logger.warning("Could not parse breach_date '%s' — treating as recent.", breach_date)
        return True


def is_breach_high_value(data_types_exposed: list[str]) -> bool:
    """
    Return True if the breach contains data classes worth alerting on.
    Pure email/username-only breaches are recorded silently.
    """
    exposed_lower = {dt.lower() for dt in data_types_exposed}
    return bool(exposed_lower & HIGH_VALUE_DATA_CLASSES)


# ---------------------------------------------------------------------------
# HIBP API
# ---------------------------------------------------------------------------

def call_hibp(email_address: str, api_key: str) -> list[dict] | None:
    """
    Call HIBP v3 breachedaccount for the given email.
    Returns list of breach objects, [] for no breaches, or None on error.
    """
    url = f"{HIBP_BASE_URL}{urllib.request.quote(email_address)}?truncateResponse=false"
    headers = {
        "hibp-api-key": api_key,
        "user-agent": USER_AGENT,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read()
                breaches: list[dict] = json.loads(body)
                logger.info(
                    "HIBP returned %d breach(es) for %s.", len(breaches), email_address
                )
                return breaches

        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                logger.info("No breaches found (404) for %s.", email_address)
                return []
            if exc.code == 429:
                wait = BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "Rate limited (429) on attempt %d/%d for %s. Backing off %ds.",
                    attempt, MAX_RETRIES, email_address, wait,
                )
                time.sleep(wait)
                continue
            logger.error(
                "HTTP %d from HIBP for %s: %s", exc.code, email_address, exc.reason
            )
            return None

        except urllib.error.URLError as exc:
            logger.error(
                "Network error contacting HIBP for %s (attempt %d/%d): %s",
                email_address, attempt, MAX_RETRIES, exc.reason,
            )
            if attempt < MAX_RETRIES:
                backoff = BACKOFF_BASE_SECONDS * attempt
                logger.info("Retrying in %ds…", backoff)
                time.sleep(backoff)
                continue
            return None

        except Exception as exc:
            logger.exception(
                "Unexpected error calling HIBP for %s: %s", email_address, exc
            )
            return None

    logger.error("Exhausted %d retries for %s. Skipping.", MAX_RETRIES, email_address)
    return None


# ---------------------------------------------------------------------------
# Claude AI
# ---------------------------------------------------------------------------

def call_claude_api(user_message: str, api_key: str) -> str | None:
    """
    Call the Claude API and return the response text.
    Returns None on failure — caller falls back to static message.
    """
    payload = json.dumps({
        "model": CLAUDE_MODEL,
        "max_tokens": CLAUDE_MAX_TOKENS,
        "system": CLAUDE_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_message}],
    }).encode("utf-8")

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    req = urllib.request.Request(
        ANTHROPIC_MESSAGES_URL,
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            response_body = json.loads(resp.read())
            text = response_body["content"][0]["text"]
            logger.info("Claude API response received (%d chars).", len(text))
            return text

    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Claude API HTTP %d: %s", exc.code, error_body)
        return None

    except Exception as exc:
        logger.exception("Unexpected error calling Claude API: %s", exc)
        return None


def generate_breach_alert(
    email_address: str,
    new_breaches: list[dict],
    anthropic_api_key: str,
    password_manager_user: bool = False,
) -> str:
    """
    Call Claude to generate a severity-scored, prioritised WhatsApp alert
    covering all new breaches for one email. Passes password_manager_user
    flag so Claude can include the master password warning when relevant.
    Falls back to static message if Claude is unavailable.
    """
    breach_lines = []
    for i, b in enumerate(new_breaches, 1):
        date_str = f" ({b['breach_date']})" if b.get("breach_date") else ""
        types_str = (
            ", ".join(b["data_types_exposed"]) if b["data_types_exposed"] else "unknown"
        )
        breach_lines.append(
            f"{i}. *{b['breach_name']}*{date_str}\n   Data exposed: {types_str}"
        )

    breach_summary = "\n".join(breach_lines)
    count_word = f"{len(new_breaches)} new breach{'es' if len(new_breaches) > 1 else ''}"

    # Include password manager flag so Claude applies the right alert tier
    pm_context = (
        "password_manager_user = True — include Password Manager Alert if passwords exposed."
        if password_manager_user
        else "password_manager_user = False — skip Password Manager Alert, use REUSE prompt instead."
    )

    user_message = (
        f"Email address: {email_address}\n"
        f"{count_word} detected:\n\n"
        f"{breach_summary}\n\n"
        f"User context: {pm_context}\n\n"
        f"Generate a WhatsApp alert following your system instructions."
    )

    logger.info(
        "Calling Claude for %d breach alert(s) on %s. password_manager_user=%s",
        len(new_breaches), email_address, password_manager_user,
    )

    result = call_claude_api(user_message, anthropic_api_key)

    if result:
        # Programmatically append security blocks Claude may omit due to token limits
        # or prompt prioritisation. Checked against result text to avoid duplication.
        exposed_classes = _get_exposed_classes(new_breaches)
        pw_exposed = any_passwords_exposed(new_breaches)
        session_exposed = bool(exposed_classes & SESSION_HIJACKING_DATA_CLASSES)

        # AiTM block — append when passwords exposed and session block not already present.
        # Session token exposure already instructs users to reply SESSIONS, so skip to
        # avoid duplicate guidance.
        if pw_exposed and not session_exposed and "SESSIONS" not in result:
            result += (
                "\n\n⚠️ *2FA bypass risk — AiTM phishing (Tycoon 2FA / EvilProxy).*\n"
                "Attackers use leaked credentials to run fake login pages that steal your "
                "session token after you complete 2FA — bypassing 2FA entirely.\n"
                "→ Only log in via saved bookmarks — never via a link in an email or text\n"
                "→ After resetting your password, reply *SESSIONS* to revoke all active sessions"
            )
            logger.info("Appended AiTM phishing warning to Claude response.")

        # Session token block — append when session tokens exposed and not already present.
        if session_exposed and "SESSIONS" not in result:
            result += (
                "\n\n🍪 *CRITICAL: Active session tokens exposed.*\n"
                "An attacker can access your accounts RIGHT NOW — no password or 2FA needed.\n"
                "Reply *SESSIONS* immediately for a guided session revocation walkthrough."
            )
            logger.info("Appended session token escalation block to Claude response.")

        return result

    logger.warning("Claude unavailable — using static fallback message.")
    return build_static_fallback_message(email_address, new_breaches, password_manager_user)


def _get_exposed_classes(new_breaches: list[dict]) -> set[str]:
    """Return the union of all exposed data class names (lowercased) across all breaches."""
    exposed = set()
    for b in new_breaches:
        for dt in b.get("data_types_exposed", []):
            exposed.add(dt.lower())
    return exposed


def build_static_fallback_message(
    email_address: str,
    new_breaches: list[dict],
    password_manager_user: bool = False,
) -> str:
    """Static fallback alert used when Claude API is unavailable."""
    pw_exposed = any_passwords_exposed(new_breaches)
    exposed_classes = _get_exposed_classes(new_breaches)

    # --- Session token block (CRITICAL — check before password block) ---
    session_block = ""
    session_hits = exposed_classes & SESSION_HIJACKING_DATA_CLASSES
    if session_hits:
        session_block = (
            "\n🍪 *CRITICAL: Active session tokens exposed.*\n"
            "An attacker with your session token can access your accounts RIGHT NOW — "
            "no password or 2FA needed.\n"
            "Do these steps BEFORE changing your password:\n"
            "→ Google: myaccount.google.com/device-activity — sign out unknown devices\n"
            "→ Google: myaccount.google.com/permissions — revoke unknown apps\n"
            "→ Microsoft: account.microsoft.com/privacy/activity — sign out unknown sessions\n"
            "Reply *SESSIONS* for a full guided walkthrough.\n"
        )

    # --- AiTM phishing warning block ---
    # Only shown when passwords exposed but no session token exposure
    # (session block already covers revocation — avoid duplication)
    aitm_block = ""
    if pw_exposed and not session_hits:
        aitm_block = (
            "\n⚠️ *2FA bypass risk — AiTM phishing.*\n"
            "Leaked passwords are used to create fake login pages (Tycoon 2FA, EvilProxy) "
            "that steal your session token after you complete 2FA — making 2FA ineffective.\n"
            "→ Only log in via saved bookmarks — never via a link in an email\n"
            "→ After resetting your password, reply *SESSIONS* to revoke all active sessions\n"
        )

    # --- Password block ---
    password_block = ""
    if pw_exposed:
        password_block = (
            "\n🔑 *Your password was exposed.* Reply *REUSE* to check "
            "which other accounts are at risk.\n"
        )
        if password_manager_user:
            password_block += (
                "🔐 *Password Manager Alert:* Change your master password "
                "immediately if it resembles your breached password.\n"
            )

    # --- Identity document block (CRITICAL escalation) ---
    identity_block = ""
    identity_hits = exposed_classes & IDENTITY_DOCUMENT_DATA_CLASSES
    if identity_hits:
        identity_block = (
            "\n🪪 *CRITICAL: Identity document data exposed.*\n"
            "Immediately place a credit freeze at Equifax, Experian, and TransUnion "
            "(free at each bureau's website — takes 10 minutes).\n"
            "File an identity theft report at identitytheft.gov if fraud has occurred.\n"
            "Reply *SAFE* once you have read this.\n"
        )

    # --- Smishing warning block ---
    # Fires specifically when phone numbers are exposed — separate from the
    # vishing block below. Smishing (SMS phishing) campaigns frequently launch
    # within days of a breach that exposes phone numbers.
    smishing_block = ""
    if "phone numbers" in exposed_classes:
        smishing_block = (
            "\n📱 *Your phone number was exposed.*\n"
            "Smishing campaigns — fraudulent texts impersonating your bank, carrier, "
            "or a delivery service — frequently follow phone number exposure in breaches.\n"
            "→ Do not click links in unexpected texts, even if they look legitimate\n"
            "→ Attackers already know your name and may reference this breach\n"
            "→ Forward any suspicious text to RelayShield for analysis — reply *SMS* followed by the text\n"
            "Reply *PHONE* for carrier PIN hardening steps to protect your number from SIM swap and smishing.\n"
        )

    # --- Vishing warning block ---
    vishing_block = ""
    vishing_hits = exposed_classes & VISHING_DATA_CLASSES
    if vishing_hits and not identity_hits:
        # Identity block already covers vishing escalation — avoid duplication
        vishing_block = (
            "\n☎️ *Vishing (AI voice scam) risk.*\n"
            "This data can be used to impersonate your bank, carrier, or a government "
            "agency on a phone call. For the next 30 days:\n"
            "→ Never confirm personal details to an inbound caller\n"
            "→ Never read an OTP code — no legitimate company asks for this\n"
            "→ Hang up and call back on the official number\n"
            "→ Urgency on a call is the attack\n"
            "Reply *SAFE* to confirm you have read this, or *CALL* if you have already "
            "received a suspicious call.\n"
        )

    if len(new_breaches) == 1:
        b = new_breaches[0]
        date_part = f" ({b['breach_date']})" if b.get("breach_date") else ""
        types_str = (
            ", ".join(b["data_types_exposed"][:5]) if b["data_types_exposed"] else "unknown"
        )
        return (
            f"🔴 *RelayShield Alert*\n\n"
            f"*{email_address}* was found in the *{b['breach_name']}* breach{date_part}.\n"
            f"Data exposed: {types_str}\n"
            f"{session_block}"
            f"{identity_block}"
            f"{smishing_block}"
            f"{vishing_block}"
            f"{aitm_block}"
            f"{password_block}\n"
            f"Before resetting your password, reply *SWEEP* for a 5-minute Email Security Sweep.\n\n"
            f"— RelayShield"
        )
    else:
        names = ", ".join(b["breach_name"] for b in new_breaches)
        return (
            f"🔴 *RelayShield Alert*\n\n"
            f"*{email_address}* was found in *{len(new_breaches)} new breaches*: {names}\n"
            f"{session_block}"
            f"{identity_block}"
            f"{smishing_block}"
            f"{vishing_block}"
            f"{aitm_block}"
            f"{password_block}\n"
            f"Before resetting any passwords, reply *SWEEP* for a 5-minute Email Security Sweep.\n\n"
            f"— RelayShield"
        )


# ---------------------------------------------------------------------------
# Twilio WhatsApp
# ---------------------------------------------------------------------------

def send_whatsapp_alert(
    account_sid: str,
    auth_token: str,
    from_number: str,
    to_number: str,
    message_body: str,
) -> tuple[bool, int | None]:
    """
    Send a freeform WhatsApp message via Twilio REST API.

    Returns:
        (True, None)          — message sent successfully
        (False, twilio_code)  — failed; twilio_code is the Twilio error code
                                (e.g. 63016 = outside 24-hour window)
        (False, None)         — failed; non-Twilio error
    """
    url = TWILIO_MESSAGES_URL.format(account_sid=account_sid)

    payload = urllib.parse.urlencode({
        "From": from_number,
        "To": to_number,
        "Body": message_body,
    }).encode("utf-8")

    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            response_body = json.loads(resp.read())
            sid = response_body.get("sid", "unknown")
            logger.info("WhatsApp freeform alert sent to %s. Twilio SID: %s", to_number, sid)
            return True, None

    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error(
            "Twilio HTTP %d sending freeform to %s: %s", exc.code, to_number, error_body
        )
        # Parse Twilio error code from response body so caller can check for 63016
        twilio_code = None
        try:
            error_json = json.loads(error_body)
            twilio_code = error_json.get("code")
        except Exception:
            pass
        return False, twilio_code

    except Exception as exc:
        logger.exception(
            "Unexpected error sending WhatsApp to %s: %s", to_number, exc
        )
        return False, None


def send_whatsapp_template_alert(
    account_sid: str,
    auth_token: str,
    from_number: str,
    to_number: str,
    alertable_breaches: list[dict],
    email_address: str,
) -> bool:
    """
    Send a pre-approved WhatsApp Message Template breach alert via Twilio.
    Templates bypass the 24-hour messaging window restriction (error 63016).

    For multiple breaches, the primary (first) breach is used in the template
    fields, with the count noted in the source field.

    Variables map:
        {{1}} = monitored email address
        {{2}} = breach source name (e.g. "LinkedIn" or "LinkedIn and 2 others")
        {{3}} = exposed data classes (comma-separated, capped at 80 chars)
        {{4}} = breach date (YYYY-MM-DD or "Unknown")
    """
    url = TWILIO_MESSAGES_URL.format(account_sid=account_sid)

    primary = alertable_breaches[0]
    breach_count = len(alertable_breaches)

    # {{2}}: source name — mention count if multiple breaches
    if breach_count == 1:
        source = primary["breach_name"]
    else:
        others = breach_count - 1
        source = f"{primary['breach_name']} and {others} other{'s' if others > 1 else ''}"

    # {{3}}: data classes — deduplicated across all alertable breaches, capped at 80 chars
    all_classes: list[str] = []
    seen: set[str] = set()
    for b in alertable_breaches:
        for dc in b.get("data_types_exposed", []):
            if dc.lower() not in seen:
                seen.add(dc.lower())
                all_classes.append(dc)
    classes_str = ", ".join(all_classes)
    if len(classes_str) > 80:
        classes_str = classes_str[:77] + "…"

    # {{4}}: breach date
    breach_date = primary.get("breach_date") or "Unknown"

    content_variables = json.dumps({
        "1": email_address,
        "2": source,
        "3": classes_str or "Unknown",
        "4": breach_date,
    })

    payload = urllib.parse.urlencode({
        "From": from_number,
        "To": to_number,
        "ContentSid": BREACH_ALERT_TEMPLATE_SID,
        "ContentVariables": content_variables,
    }).encode("utf-8")

    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            response_body = json.loads(resp.read())
            sid = response_body.get("sid", "unknown")
            logger.info(
                "WhatsApp template alert sent to %s. Twilio SID: %s "
                "(covering %d breach(es))",
                to_number, sid, breach_count,
            )
            return True

    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error(
            "Twilio HTTP %d sending template to %s: %s", exc.code, to_number, error_body
        )
        return False

    except Exception as exc:
        logger.exception(
            "Unexpected error sending WhatsApp template to %s: %s", to_number, exc
        )
        return False


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def process_email(
    monitored_record: dict,
    api_key: str,
    twilio_creds: tuple[str, str, str],
    anthropic_api_key: str,
    user_cache: dict[str, dict | None],
) -> list[dict]:
    """
    Check a single monitored email against HIBP, persist new breaches,
    call Claude to generate one consolidated severity-scored WhatsApp alert,
    send it, and return new breach summaries.

    Password exposure is detected from HIBP DataClasses — no user password
    submission required. password_manager_user flag from DynamoDB controls
    whether the master password warning is appended.
    """
    email_id = monitored_record["email_id"]
    user_id = monitored_record["user_id"]
    email_address = monitored_record["email_address"]
    now = datetime.now(timezone.utc).isoformat()

    logger.info(
        "Processing email_id=%s (%s) for user_id=%s", email_id, email_address, user_id
    )

    breaches = call_hibp(email_address, api_key)

    if breaches is None:
        logger.warning(
            "Skipping last_checked update for email_id=%s due to HIBP error.", email_id
        )
        return []

    update_last_checked(email_id, user_id, now)

    if not breaches:
        return []

    # Resolve full user record (cached per user_id)
    if user_id not in user_cache:
        user_cache[user_id] = get_user_record(user_id)
    user_record = user_cache[user_id]

    to_number = None
    password_manager_user = False

    if user_record:
        to_number = get_whatsapp_number_from_record(user_record)
        password_manager_user = bool(user_record.get("password_manager_user", False))
    else:
        logger.warning("No user record for user_id=%s", user_id)

    existing_breach_names = get_existing_breach_names(user_id, email_address)

    # new_breaches    — all newly seen breaches; written to DynamoDB for deduplication
    # alertable       — subset that passes recency + high-value filters; triggers WhatsApp
    new_breaches: list[dict] = []
    alertable: list[dict] = []

    for breach in breaches:
        breach_name = breach.get("Name", "")
        if not breach_name:
            logger.warning("Breach record missing Name field; skipping: %s", breach)
            continue
        if breach_name in existing_breach_names:
            logger.debug(
                "Breach %s already recorded for %s — skipping.", breach_name, email_address
            )
            continue

        breach_date = breach.get("BreachDate") or breach.get("AddedDate") or ""
        data_types_exposed = breach.get("DataClasses", [])
        pw_exposed = passwords_in_breach(data_types_exposed)

        # Always write to DynamoDB so we never re-evaluate this breach
        alert_id = write_breach_alert(
            user_id=user_id,
            email_address=email_address,
            breach_name=breach_name,
            breach_date=breach_date,
            data_types_exposed=data_types_exposed,
            alert_sent_at=now,
            passwords_exposed=pw_exposed,
        )

        breach_record = {
            "alert_id": alert_id,
            "user_id": user_id,
            "email_address": email_address,
            "breach_name": breach_name,
            "breach_date": breach_date,
            "data_types_exposed": data_types_exposed,
            "passwords_exposed": pw_exposed,
        }
        new_breaches.append(breach_record)

        # Apply recency + high-value filters before alerting
        recent = is_breach_recent(breach_date)
        high_value = is_breach_high_value(data_types_exposed)

        if recent and high_value:
            alertable.append(breach_record)
            if pw_exposed:
                logger.info(
                    "Password exposure in alertable breach %s for user_id=%s pm_user=%s",
                    breach_name, user_id, password_manager_user,
                )
        else:
            logger.info(
                "Breach %s for %s recorded but filtered from alert "
                "(recent=%s high_value=%s date=%s).",
                breach_name, email_address, recent, high_value, breach_date,
            )

    if not new_breaches:
        logger.info("email_id=%s: no new breaches.", email_id)
        return []

    if not alertable:
        logger.info(
            "email_id=%s: %d new breach(es) recorded but all filtered "
            "(too old or low-value). No WhatsApp alert sent.",
            email_id, len(new_breaches),
        )
        return new_breaches

    # Always send via pre-approved Message Template.
    #
    # WHY: Twilio's 63016 (outside 24-hour window) error is asynchronous —
    # the API call returns HTTP 200 with a SID, so a freeform-first approach
    # cannot detect the failure in-Lambda. The template is always deliverable
    # regardless of session state, so we use it as the primary alert mechanism.
    #
    # UX flow:
    #   Step 1 — Template → concise breach alert, always arrives
    #   Step 2 — Claude freeform → detailed severity-scored analysis with AiTM/session
    #             warnings sent immediately after. Succeeds when an active WhatsApp
    #             session exists (user recently texted us). Gracefully skipped on 63016.
    #   Step 3 — User replies → webhook handles SWEEP / SAFE / SESSIONS etc.
    if to_number:
        account_sid, auth_token, from_number = twilio_creds
        sent = send_whatsapp_template_alert(
            account_sid=account_sid,
            auth_token=auth_token,
            from_number=from_number,
            to_number=to_number,
            alertable_breaches=alertable,
            email_address=email_address,
        )
        whatsapp_sent = sent
        if not sent:
            logger.warning(
                "WhatsApp template alert failed for %d alertable breach(es) on email_id=%s.",
                len(alertable), email_id,
            )

        # Step 2 — Claude freeform follow-up with full severity analysis.
        # Sent immediately after the template. Works when the user has an active
        # WhatsApp session (recently messaged us). Gracefully skipped on 63016
        # (outside window) — template already delivered the core breach notification.
        if sent:
            detailed_alert = generate_breach_alert(
                email_address=email_address,
                new_breaches=alertable,
                anthropic_api_key=anthropic_api_key,
                password_manager_user=password_manager_user,
            )
            freeform_sent, twilio_code = send_whatsapp_alert(
                account_sid=account_sid,
                auth_token=auth_token,
                from_number=from_number,
                to_number=to_number,
                message_body=detailed_alert,
            )
            if freeform_sent:
                logger.info(
                    "Claude freeform analysis sent to %s for email_id=%s.",
                    to_number, email_id,
                )
            elif twilio_code == TWILIO_ERROR_OUTSIDE_WINDOW:
                logger.info(
                    "Freeform follow-up skipped — no active session (63016). "
                    "Template delivered. Detailed analysis sent on next user reply."
                )
            else:
                logger.warning(
                    "Freeform follow-up failed (code=%s) for email_id=%s.",
                    twilio_code, email_id,
                )
    else:
        whatsapp_sent = False
        logger.warning(
            "No WhatsApp number for user_id=%s — %d breach(es) recorded but not sent.",
            user_id, len(new_breaches),
        )

    for b in new_breaches:
        b["whatsapp_sent"] = whatsapp_sent if b in alertable else False
        b.pop("data_types_exposed", None)  # already in DynamoDB

    logger.info(
        "email_id=%s: %d new breach(es) recorded, %d alerted via WhatsApp "
        "(%d filtered by age/severity).",
        email_id, len(new_breaches), len(alertable),
        len(new_breaches) - len(alertable),
    )
    return new_breaches


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def handler(event: dict, context) -> dict:  # noqa: ANN001
    """Entry point for the RelayShield breach monitoring Lambda."""
    logger.info("RelayShield breach monitor started.")
    start_time = time.time()

    # 1. Fetch all credentials once per invocation
    try:
        api_key = get_hibp_api_key()
    except Exception as exc:
        logger.exception("Failed to retrieve HIBP API key: %s", exc)
        return {
            "statusCode": 500,
            "body": {"error": "Failed to retrieve HIBP API key", "detail": str(exc)},
        }

    try:
        twilio_creds = get_twilio_credentials()
    except Exception as exc:
        logger.exception("Failed to retrieve Twilio credentials: %s", exc)
        return {
            "statusCode": 500,
            "body": {"error": "Failed to retrieve Twilio credentials", "detail": str(exc)},
        }

    try:
        anthropic_api_key = get_anthropic_api_key()
    except Exception as exc:
        logger.exception("Failed to retrieve Anthropic API key: %s", exc)
        return {
            "statusCode": 500,
            "body": {"error": "Failed to retrieve Anthropic API key", "detail": str(exc)},
        }

    # 2. Load all monitored email records
    try:
        monitored_emails = scan_monitored_emails()
    except Exception as exc:
        logger.exception("Failed to scan monitored emails table: %s", exc)
        return {
            "statusCode": 500,
            "body": {"error": "Failed to scan monitored emails", "detail": str(exc)},
        }

    if not monitored_emails:
        logger.info("No monitored emails found. Exiting.")
        return {
            "statusCode": 200,
            "body": {"new_breaches_found": 0, "new_breaches": []},
        }

    # 3. Process each email with rate-limit delay between HIBP calls
    all_new_breaches: list[dict] = []
    user_cache: dict[str, dict | None] = {}

    for index, record in enumerate(monitored_emails):
        if index > 0:
            logger.info(
                "Waiting %ds before next HIBP request (%d/%d)…",
                REQUEST_DELAY_SECONDS, index + 1, len(monitored_emails),
            )
            time.sleep(REQUEST_DELAY_SECONDS)

        try:
            new_for_email = process_email(
                record, api_key, twilio_creds, anthropic_api_key, user_cache
            )
            all_new_breaches.extend(new_for_email)
        except Exception as exc:
            logger.exception(
                "Unhandled error processing email_id=%s: %s",
                record.get("email_id", "unknown"), exc,
            )

    elapsed = round(time.time() - start_time, 2)
    logger.info(
        "RelayShield breach monitor finished. "
        "%d email(s) checked, %d new breach(es) found. Elapsed: %ss.",
        len(monitored_emails), len(all_new_breaches), elapsed,
    )

    return {
        "statusCode": 200,
        "body": {
            "emails_checked": len(monitored_emails),
            "new_breaches_found": len(all_new_breaches),
            "new_breaches": all_new_breaches,
        },
    }
