"""
RelayShield Breach Monitor Lambda
Scans monitored emails against HIBP v3, records new breach alerts,
and sends WhatsApp alerts via Twilio with Claude AI severity scoring
and remediation guidance.
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

USER_AGENT = "RelayShield-BreachMonitor"
CLAUDE_MODEL = "claude-3-haiku-20240307"
CLAUDE_MAX_TOKENS = 1024

# HIBP Pwned 1 plan: 10 RPM → 1 request per 6 seconds
REQUEST_DELAY_SECONDS = 6
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 10

CLAUDE_SYSTEM_PROMPT = """You are RelayShield's AI security advisor. Your job is to assess breach severity and deliver concise, actionable WhatsApp alerts.

SEVERITY LEVELS:
CRITICAL — Email providers, financial institutions, healthcare, government. Act immediately.
HIGH — Social media, e-commerce with saved payment cards. Act within 24 hours.
MEDIUM — Shopping sites, forums, subscription services. Act within 1 week.
LOW — Gaming sites, old accounts with minimal PII. Note and monitor.

FORMATTING (WhatsApp markdown):
→ Use *text* for bold
→ Keep under 300 words total
→ No HTML
→ Use → for bullet points

MULTIPLE BREACHES:
If multiple breaches are provided, rank by severity and state clearly which to fix first.
Lead with: "⚠️ *X new breaches detected.* Fix in this order:"

PHONE NUMBER EXPOSURE:
If "Phone numbers" appears in exposed data types, add:
"📱 *Your phone number was exposed.* Risks: SIM swap attacks and smishing. Reply *PHONE* for carrier hardening steps."

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


def get_user_whatsapp_number(user_id: str) -> str | None:
    """Look up the whatsapp_number for a user from relayshield_users."""
    table = dynamodb.Table(USERS_TABLE)
    response = table.get_item(Key={"user_id": user_id})
    item = response.get("Item")
    if not item:
        logger.warning("No user record found for user_id=%s", user_id)
        return None
    number = item.get("whatsapp_number")
    if not number:
        logger.warning("user_id=%s has no whatsapp_number field.", user_id)
        return None
    if not number.startswith("whatsapp:"):
        number = f"whatsapp:{number}"
    return number


def get_existing_breach_names(user_id: str, email_address: str) -> set[str]:
    """Return breach names already recorded for this user/email pair."""
    table = dynamodb.Table(BREACH_ALERTS_TABLE)
    items: list[dict] = []
    kwargs: dict = {
        "FilterExpression": Attr("user_id").eq(user_id) & Attr("email_address").eq(email_address),
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
    }
    table.put_item(Item=item)
    logger.info(
        "Wrote breach alert %s for user %s: breach=%s",
        alert_id, user_id, breach_name,
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
# HIBP API
# ---------------------------------------------------------------------------

def call_hibp(email_address: str, api_key: str) -> list[dict] | None:
    """
    Call HIBP v3 breachedaccount for the given email.
    Returns list of breach objects, [] for no breaches, or None on error.
    """
    url = f"{HIBP_BASE_URL}{urllib.request.quote(email_address)}"
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
            logger.error("HTTP %d from HIBP for %s: %s", exc.code, email_address, exc.reason)
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
            logger.exception("Unexpected error calling HIBP for %s: %s", email_address, exc)
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
) -> str:
    """
    Call Claude to generate a severity-scored, prioritised WhatsApp alert
    covering all new breaches for one email. Falls back to static message
    if Claude is unavailable.
    """
    breach_lines = []
    for i, b in enumerate(new_breaches, 1):
        date_str = f" ({b['breach_date']})" if b.get("breach_date") else ""
        types_str = ", ".join(b["data_types_exposed"]) if b["data_types_exposed"] else "unknown"
        breach_lines.append(
            f"{i}. *{b['breach_name']}*{date_str}\n   Data exposed: {types_str}"
        )

    breach_summary = "\n".join(breach_lines)
    count_word = f"{len(new_breaches)} new breach{'es' if len(new_breaches) > 1 else ''}"

    user_message = (
        f"Email address: {email_address}\n"
        f"{count_word} detected:\n\n"
        f"{breach_summary}\n\n"
        f"Generate a WhatsApp alert following your system instructions."
    )

    logger.info(
        "Calling Claude for %d breach alert(s) on %s.",
        len(new_breaches), email_address,
    )

    result = call_claude_api(user_message, anthropic_api_key)

    if result:
        return result

    logger.warning("Claude unavailable — using static fallback message.")
    return build_static_fallback_message(email_address, new_breaches)


def build_static_fallback_message(
    email_address: str,
    new_breaches: list[dict],
) -> str:
    """Static fallback alert used when Claude API is unavailable."""
    if len(new_breaches) == 1:
        b = new_breaches[0]
        date_part = f" ({b['breach_date']})" if b.get("breach_date") else ""
        types_str = ", ".join(b["data_types_exposed"][:5]) if b["data_types_exposed"] else "unknown"
        return (
            f"🔴 *RelayShield Alert*\n\n"
            f"*{email_address}* was found in the *{b['breach_name']}* breach{date_part}.\n"
            f"Data exposed: {types_str}\n\n"
            f"Before resetting your password, reply *SWEEP* for a 5-minute Email Security Sweep.\n\n"
            f"— RelayShield"
        )
    else:
        names = ", ".join(b["breach_name"] for b in new_breaches)
        return (
            f"🔴 *RelayShield Alert*\n\n"
            f"*{email_address}* was found in *{len(new_breaches)} new breaches*: {names}\n\n"
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
) -> bool:
    """Send a WhatsApp message via the Twilio REST API."""
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
            logger.info("WhatsApp alert sent to %s. Twilio SID: %s", to_number, sid)
            return True

    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Twilio HTTP %d sending to %s: %s", exc.code, to_number, error_body)
        return False

    except Exception as exc:
        logger.exception("Unexpected error sending WhatsApp to %s: %s", to_number, exc)
        return False


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------

def process_email(
    monitored_record: dict,
    api_key: str,
    twilio_creds: tuple[str, str, str],
    anthropic_api_key: str,
    user_cache: dict[str, str | None],
) -> list[dict]:
    """
    Check a single monitored email against HIBP, persist new breaches,
    call Claude to generate one consolidated severity-scored WhatsApp alert,
    send it, and return new breach summaries.
    """
    email_id = monitored_record["email_id"]
    user_id = monitored_record["user_id"]
    email_address = monitored_record["email_address"]
    now = datetime.now(timezone.utc).isoformat()

    logger.info("Processing email_id=%s (%s) for user_id=%s", email_id, email_address, user_id)

    breaches = call_hibp(email_address, api_key)

    if breaches is None:
        logger.warning("Skipping last_checked update for email_id=%s due to HIBP error.", email_id)
        return []

    update_last_checked(email_id, user_id, now)

    if not breaches:
        return []

    # Resolve user's WhatsApp number (cached per user_id)
    if user_id not in user_cache:
        user_cache[user_id] = get_user_whatsapp_number(user_id)
    to_number = user_cache[user_id]

    existing_breach_names = get_existing_breach_names(user_id, email_address)
    new_breaches: list[dict] = []

    # Write all new breaches to DynamoDB first
    for breach in breaches:
        breach_name = breach.get("Name", "")
        if not breach_name:
            logger.warning("Breach record missing Name field; skipping: %s", breach)
            continue
        if breach_name in existing_breach_names:
            logger.debug("Breach %s already recorded for %s — skipping.", breach_name, email_address)
            continue

        breach_date = breach.get("BreachDate") or breach.get("AddedDate") or ""
        data_types_exposed = breach.get("DataClasses", [])

        alert_id = write_breach_alert(
            user_id=user_id,
            email_address=email_address,
            breach_name=breach_name,
            breach_date=breach_date,
            data_types_exposed=data_types_exposed,
            alert_sent_at=now,
        )

        new_breaches.append({
            "alert_id": alert_id,
            "user_id": user_id,
            "email_address": email_address,
            "breach_name": breach_name,
            "breach_date": breach_date,
            "data_types_exposed": data_types_exposed,
        })

    if not new_breaches:
        logger.info("email_id=%s: no new breaches.", email_id)
        return []

    # Generate one Claude-powered alert covering all new breaches for this email
    if to_number:
        account_sid, auth_token, from_number = twilio_creds
        message = generate_breach_alert(email_address, new_breaches, anthropic_api_key)
        sent = send_whatsapp_alert(
            account_sid=account_sid,
            auth_token=auth_token,
            from_number=from_number,
            to_number=to_number,
            message_body=message,
        )
        whatsapp_sent = sent
        if not sent:
            logger.warning(
                "WhatsApp alert failed for %d breach(es) on email_id=%s.",
                len(new_breaches), email_id,
            )
    else:
        whatsapp_sent = False
        logger.warning(
            "No WhatsApp number for user_id=%s — %d breach(es) recorded but not sent.",
            user_id, len(new_breaches),
        )

    for b in new_breaches:
        b["whatsapp_sent"] = whatsapp_sent
        b.pop("data_types_exposed", None)  # remove from return payload, already in DynamoDB

    logger.info(
        "email_id=%s: %d new breach(es) recorded out of %d returned by HIBP.",
        email_id, len(new_breaches), len(breaches),
    )
    return new_breaches


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context) -> dict:  # noqa: ANN001
    """Entry point for the RelayShield breach monitoring Lambda."""
    logger.info("RelayShield breach monitor started.")
    start_time = time.time()

    # 1. Fetch all credentials once per invocation
    try:
        api_key = get_hibp_api_key()
    except Exception as exc:
        logger.exception("Failed to retrieve HIBP API key: %s", exc)
        return {"statusCode": 500, "body": {"error": "Failed to retrieve HIBP API key", "detail": str(exc)}}

    try:
        twilio_creds = get_twilio_credentials()
    except Exception as exc:
        logger.exception("Failed to retrieve Twilio credentials: %s", exc)
        return {"statusCode": 500, "body": {"error": "Failed to retrieve Twilio credentials", "detail": str(exc)}}

    try:
        anthropic_api_key = get_anthropic_api_key()
    except Exception as exc:
        logger.exception("Failed to retrieve Anthropic API key: %s", exc)
        return {"statusCode": 500, "body": {"error": "Failed to retrieve Anthropic API key", "detail": str(exc)}}

    # 2. Load all monitored email records
    try:
        monitored_emails = scan_monitored_emails()
    except Exception as exc:
        logger.exception("Failed to scan monitored emails table: %s", exc)
        return {"statusCode": 500, "body": {"error": "Failed to scan monitored emails", "detail": str(exc)}}

    if not monitored_emails:
        logger.info("No monitored emails found. Exiting.")
        return {"statusCode": 200, "body": {"new_breaches_found": 0, "new_breaches": []}}

    # 3. Process each email with rate-limit delay between HIBP calls
    all_new_breaches: list[dict] = []
    user_cache: dict[str, str | None] = {}

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
