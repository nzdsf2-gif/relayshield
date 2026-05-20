"""
RelayShield Infostealer Monitor Lambda

Near real-time infostealer detection: periodically checks all monitored email
addresses against infostealer malware log databases. When a previously-clean
email appears in new stealer logs, an alert is pushed to the user via WhatsApp
and/or Telegram.

Unlike HIBP breach monitoring (which covers historical corporate database leaks),
infostealer logs are ingested within days of appearing on dark web markets,
meaning this provides near real-time detection of active device compromises.

What infostealer malware steals from infected devices:
  - Every browser-saved password across all sites
  - Active session cookies (bypasses 2FA without needing the password)
  - Credit card and autofill data
  - Crypto wallet seed phrases and keys
  - Desktop app tokens (Discord, Telegram, etc.)

Trigger: EventBridge scheduled rule — recommended every 48 hours.
         No rate-limit concerns (Hudson Rock free API, no key required).

DynamoDB storage:
  - relayshield_monitored_emails: adds `infostealer_count` and
    `infostealer_last_checked` fields to existing records.
  - relayshield_users: alert delivery (WhatsApp number + Telegram chat_id).

Alert delivery:
  - WhatsApp via Twilio freeform message
  - Telegram via direct Lambda invoke (same pattern as breach monitor)

Environment variables:
  TG_WEBHOOK_LAMBDA — ARN/name of relayshield_telegram_webhook Lambda
                      (optional — Telegram alerts skipped if unset)

Secrets used (Secrets Manager):
  relayshield/twilio_account_sid
  relayshield/twilio_auth_token
  relayshield/twilio_whatsapp_number
"""

import base64
import json
import logging
import os
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
# AWS clients
# ---------------------------------------------------------------------------

secrets_client = boto3.client("secretsmanager")
dynamodb       = boto3.resource("dynamodb")
kms_client     = boto3.client("kms")
lambda_client  = boto3.client("lambda")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TG_WEBHOOK_LAMBDA = os.environ.get("TG_WEBHOOK_LAMBDA", "")

KMS_EMAIL_KEY_ALIAS  = "alias/relayshield-data-key"
KMS_PHONE_KEY_ALIAS  = "alias/relayshield-data-key"

MONITORED_EMAILS_TABLE = "relayshield_monitored_emails"
USERS_TABLE            = "relayshield_users"

TWILIO_SID_SECRET   = "relayshield/twilio_account_sid"
TWILIO_TOKEN_SECRET = "relayshield/twilio_auth_token"
TWILIO_FROM_SECRET  = "relayshield/twilio_whatsapp_number"

TWILIO_MESSAGES_URL      = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
CAVALIER_URL             = "https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-login"
TWILIO_ERROR_OUTSIDE_WINDOW = 63016

# Delay between Hudson Rock requests (courtesy rate limit — free API, no stated limit)
REQUEST_DELAY_SECONDS = 2

# ---------------------------------------------------------------------------
# Secrets helpers
# ---------------------------------------------------------------------------

_secret_cache: dict[str, str] = {}


def _get_secret(name: str) -> str:
    if name not in _secret_cache:
        raw = secrets_client.get_secret_value(SecretId=name)["SecretString"].strip()
        _secret_cache[name] = raw
    return _secret_cache[name]


def _get_secret_json(name: str, key: str) -> str:
    raw = _get_secret(name)
    try:
        return json.loads(raw)[key]
    except (json.JSONDecodeError, KeyError):
        return raw


def get_twilio_credentials() -> tuple[str, str, str]:
    sid   = _get_secret_json(TWILIO_SID_SECRET,   "TWILIO_ACCOUNT_SID")
    token = _get_secret_json(TWILIO_TOKEN_SECRET,  "TWILIO_AUTH_TOKEN")
    frm   = _get_secret(TWILIO_FROM_SECRET)
    if not frm.startswith("whatsapp:"):
        frm = f"whatsapp:{frm}"
    return sid, token, frm


# ---------------------------------------------------------------------------
# KMS decrypt helpers (same keys as breach monitor)
# ---------------------------------------------------------------------------

def decrypt_email(ciphertext_b64: str) -> str:
    ciphertext = base64.b64decode(ciphertext_b64)
    response   = kms_client.decrypt(
        CiphertextBlob=ciphertext,
        KeyId=KMS_EMAIL_KEY_ALIAS,
    )
    return response["Plaintext"].decode("utf-8")


def decrypt_phone(ciphertext_b64: str) -> str:
    ciphertext = base64.b64decode(ciphertext_b64)
    response   = kms_client.decrypt(
        CiphertextBlob=ciphertext,
        KeyId=KMS_PHONE_KEY_ALIAS,
    )
    return response["Plaintext"].decode("utf-8")


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def scan_monitored_emails() -> list[dict]:
    """Return all active monitored email records."""
    table  = dynamodb.Table(MONITORED_EMAILS_TABLE)
    items: list[dict] = []
    kwargs: dict = {"FilterExpression": Attr("active").eq(True)}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    logger.info("Found %d active monitored email record(s).", len(items))
    return items


def get_user_record(user_id: str) -> dict | None:
    table = dynamodb.Table(USERS_TABLE)
    resp  = table.get_item(Key={"user_id": user_id})
    return resp.get("Item")


def update_infostealer_result(email_id: str, stealer_count: int, checked_at: str) -> None:
    """Persist latest infostealer check result on the monitored email record."""
    table = dynamodb.Table(MONITORED_EMAILS_TABLE)
    table.update_item(
        Key={"email_id": email_id},
        UpdateExpression=(
            "SET infostealer_count = :cnt, "
            "infostealer_last_checked = :ts"
        ),
        ExpressionAttributeValues={":cnt": stealer_count, ":ts": checked_at},
    )


def get_whatsapp_number(user_record: dict) -> str | None:
    """Decrypt and return the user's WhatsApp number in whatsapp:+1... format."""
    encrypted = user_record.get("phone_encrypted")
    if encrypted:
        try:
            number = decrypt_phone(encrypted)
            if not number.startswith("whatsapp:"):
                number = f"whatsapp:{number}"
            return number
        except Exception as exc:
            logger.error("Phone decrypt failed user_id=%s: %s", user_record.get("user_id"), exc)
    # Fallback: legacy plaintext field
    number = user_record.get("whatsapp_number")
    if number:
        if not number.startswith("whatsapp:"):
            number = f"whatsapp:{number}"
        return number
    return None


# ---------------------------------------------------------------------------
# Hudson Rock Cavalier API
# ---------------------------------------------------------------------------

def check_infostealer(email: str) -> list[dict]:
    """
    Query Hudson Rock Cavalier for infostealer logs matching email.
    Returns list of stealer dicts (empty = clean).
    Raises on non-404 HTTP errors.
    """
    encoded = urllib.parse.quote(email, safe="")
    url     = f"{CAVALIER_URL}?email={encoded}"
    req     = urllib.request.Request(url, headers={"User-Agent": "RelayShield-InfostealerMonitor/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        return data.get("stealers", [])
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return []   # clean — not found
        raise


# ---------------------------------------------------------------------------
# Alert delivery
# ---------------------------------------------------------------------------

def send_whatsapp(
    account_sid: str,
    auth_token: str,
    from_number: str,
    to_number: str,
    body: str,
) -> tuple[bool, int | None]:
    """Send a freeform WhatsApp message. Returns (sent, twilio_error_code)."""
    url        = TWILIO_MESSAGES_URL.format(account_sid=account_sid)
    payload    = urllib.parse.urlencode({"From": from_number, "To": to_number, "Body": body}).encode()
    creds      = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    headers    = {"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"}
    req        = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            sid = json.loads(resp.read()).get("sid", "unknown")
            logger.info("WhatsApp infostealer alert sent to %s SID=%s", to_number, sid)
            return True, None
    except urllib.error.HTTPError as exc:
        body_txt = exc.read().decode("utf-8", errors="replace")
        logger.error("Twilio HTTP %d to %s: %s", exc.code, to_number, body_txt)
        twilio_code = None
        try:
            twilio_code = json.loads(body_txt).get("code")
        except Exception:
            pass
        return False, twilio_code
    except Exception as exc:
        logger.exception("WhatsApp send error to %s: %s", to_number, exc)
        return False, None


def send_telegram_alert(tg_chat_id: int, message: str) -> bool:
    """
    Send a Telegram message by invoking the TG webhook Lambda directly.
    Uses the same _push_tg_signal-style async invoke pattern.
    """
    if not TG_WEBHOOK_LAMBDA:
        return False
    try:
        payload = json.dumps({
            "source":           "relayshield_internal",
            "action":           "send_message",
            "telegram_chat_id": tg_chat_id,
            "message":          message,
        }).encode()
        lambda_client.invoke(
            FunctionName=TG_WEBHOOK_LAMBDA,
            InvocationType="Event",
            Payload=payload,
        )
        logger.info("Telegram infostealer alert queued for chat_id=%s", tg_chat_id)
        return True
    except Exception as exc:
        logger.exception("Telegram invoke failed chat_id=%s: %s", tg_chat_id, exc)
        return False


# ---------------------------------------------------------------------------
# Alert message builder
# ---------------------------------------------------------------------------

def build_alert(email: str, stealers: list[dict], new_count: int, is_telegram: bool = False) -> str:
    """
    Build the infostealer alert message for WhatsApp or Telegram.
    new_count = number of NEW infections detected since last check
    (first detection: all infections are new; subsequent: delta only shown)
    """
    total = len(stealers)
    lines = [
        f"🦠 *RelayShield Infostealer Alert*\n",
        f"Credentials linked to *{email}* have appeared in new infostealer logs.\n",
    ]

    # Show up to 2 most recent infections
    for s in stealers[:2]:
        date = s.get("date_compromised", "unknown date")
        os_  = s.get("operating_system", "unknown OS")
        corp = s.get("total_corporate_services", 0)
        usr  = s.get("total_user_services", 0)
        lines.append(f"• *{date}* — {os_}\n  {corp} work + {usr} personal site credentials exfiltrated")

    if total > 2:
        lines.append(f"…and {total - 2} more infection{'s' if total - 2 != 1 else ''}.")

    lines.append(
        "\n*What was stolen:*\n"
        "Infostealer malware silently exfiltrates everything the browser holds — saved passwords "
        "for every site, active session cookies (bypassing 2FA without needing a password), "
        "credit card autofill, and crypto wallet keys.\n"
    )

    if is_telegram:
        lines.append(
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
    else:
        lines.append(
            "*Step 1 — Isolate the infected device now:*\n"
            "→ Disconnect it from Wi-Fi and unplug ethernet\n"
            "→ Do NOT log into any accounts on it until it is cleaned\n\n"
            "*Step 2 — From a different clean device:*\n"
            "→ Change all passwords — email, banking, social, crypto\n"
            "→ Revoke active sessions: reply *SESSIONS*\n"
            "→ Close email backdoors: reply *SWEEP*\n"
            "→ Enable 2FA on every account\n\n"
            "*Step 3 — Clean the infected device:*\n"
            "→ Download Malwarebytes Free (malwarebytes.com) on a USB from a clean device\n"
            "→ Run a full scan and remove everything flagged\n"
            "→ For a severe infection, a full OS reinstall is the safest option\n\n"
            "*Step 4 — After cleaning:*\n"
            "→ Update your OS and all software\n"
            "→ Remove unfamiliar browser extensions\n"
            "→ Reconnect to the internet\n\n"
            "Reply *HELP* to see all commands.\n\n"
            "— RelayShield"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-email processor
# ---------------------------------------------------------------------------

def process_email(
    record: dict,
    twilio_creds: tuple[str, str, str],
    user_cache: dict,
) -> dict:
    """
    Check one monitored email against the infostealer database.
    Returns a summary dict with alert outcome.
    """
    email_id   = record.get("email_id", "")
    user_id    = record.get("user_id", "")
    now        = datetime.now(timezone.utc).isoformat()

    # Decrypt email
    try:
        email_enc = record.get("email_encrypted", "")
        email     = decrypt_email(email_enc) if email_enc else record.get("email", "")
    except Exception as exc:
        logger.error("Email decrypt failed email_id=%s: %s", email_id, exc)
        return {"email_id": email_id, "error": "decrypt_failed"}

    if not email:
        logger.warning("Empty email for email_id=%s — skipping.", email_id)
        return {"email_id": email_id, "error": "empty_email"}

    # Query Hudson Rock
    try:
        stealers = check_infostealer(email)
    except Exception as exc:
        logger.error("Cavalier API error email_id=%s email=%s: %s", email_id, email, exc)
        return {"email_id": email_id, "email": email, "error": "api_error"}

    current_count = len(stealers)
    previous_count = int(record.get("infostealer_count", -1))  # -1 = never checked

    logger.info(
        "email_id=%s previous_count=%d current_count=%d",
        email_id, previous_count, current_count,
    )

    # Persist updated count and timestamp regardless of alert outcome
    try:
        update_infostealer_result(email_id, current_count, now)
    except Exception as exc:
        logger.error("DynamoDB update failed email_id=%s: %s", email_id, exc)

    # No new infections — nothing to alert
    if current_count == 0:
        return {"email_id": email_id, "email": email, "stealer_count": 0, "alerted": False}

    # If count has not increased since last check, no new alert needed
    if previous_count >= current_count:
        logger.info("email_id=%s no new infections (prev=%d cur=%d) — skip.", email_id, previous_count, current_count)
        return {"email_id": email_id, "email": email, "stealer_count": current_count, "alerted": False}

    # New infections detected — load user record and send alert
    new_count = current_count if previous_count == -1 else (current_count - previous_count)

    if user_id not in user_cache:
        user_cache[user_id] = get_user_record(user_id)
    user_record = user_cache[user_id]

    if not user_record:
        logger.warning("No user record for user_id=%s — alert skipped.", user_id)
        return {"email_id": email_id, "email": email, "stealer_count": current_count, "alerted": False}

    wa_sent = False
    tg_sent = False
    account_sid, auth_token, from_number = twilio_creds

    # WhatsApp alert
    to_number = get_whatsapp_number(user_record)
    if to_number:
        msg     = build_alert(email, stealers, new_count, is_telegram=False)
        sent, _ = send_whatsapp(account_sid, auth_token, from_number, to_number, msg)
        wa_sent = sent
    else:
        logger.warning("No WhatsApp number for user_id=%s — WA alert skipped.", user_id)

    # Telegram alert
    tg_chat_id  = user_record.get("telegram_chat_id")
    tg_channels = user_record.get("delivery_channels", [])
    if tg_chat_id and "telegram" in tg_channels:
        msg    = build_alert(email, stealers, new_count, is_telegram=True)
        tg_sent = send_telegram_alert(int(tg_chat_id), msg)

    logger.info(
        "email_id=%s new_infections=%d wa_sent=%s tg_sent=%s",
        email_id, new_count, wa_sent, tg_sent,
    )
    return {
        "email_id":      email_id,
        "email":         email,
        "stealer_count": current_count,
        "new_count":     new_count,
        "wa_sent":       wa_sent,
        "tg_sent":       tg_sent,
        "alerted":       wa_sent or tg_sent,
    }


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def handler(event: dict, context) -> dict:  # noqa: ANN001
    """
    Entry point for the RelayShield infostealer monitor Lambda.
    Triggered by EventBridge on a schedule (recommended: every 48 hours).
    """
    logger.info("RelayShield infostealer monitor started.")
    start_time = time.time()

    try:
        twilio_creds = get_twilio_credentials()
    except Exception as exc:
        logger.exception("Failed to retrieve Twilio credentials: %s", exc)
        return {"statusCode": 500, "body": {"error": "twilio_credentials_failed", "detail": str(exc)}}

    try:
        monitored_emails = scan_monitored_emails()
    except Exception as exc:
        logger.exception("Failed to scan monitored emails: %s", exc)
        return {"statusCode": 500, "body": {"error": "scan_failed", "detail": str(exc)}}

    if not monitored_emails:
        logger.info("No monitored emails found. Exiting.")
        return {"statusCode": 200, "body": {"emails_checked": 0, "new_infections_found": 0}}

    results: list[dict] = []
    user_cache: dict[str, dict | None] = {}

    for index, record in enumerate(monitored_emails):
        if index > 0:
            time.sleep(REQUEST_DELAY_SECONDS)
        try:
            result = process_email(record, twilio_creds, user_cache)
            results.append(result)
        except Exception as exc:
            logger.exception(
                "Unhandled error processing email_id=%s: %s",
                record.get("email_id", "unknown"), exc,
            )

    alerted    = [r for r in results if r.get("alerted")]
    infections = [r for r in results if r.get("stealer_count", 0) > 0]
    elapsed    = round(time.time() - start_time, 2)

    logger.info(
        "Infostealer monitor finished. %d email(s) checked, "
        "%d with infections, %d new alert(s) sent. Elapsed: %ss.",
        len(monitored_emails), len(infections), len(alerted), elapsed,
    )

    return {
        "statusCode": 200,
        "body": {
            "emails_checked":       len(monitored_emails),
            "infections_found":     len(infections),
            "new_alerts_sent":      len(alerted),
            "elapsed_seconds":      elapsed,
            "alerts":               alerted,
        },
    }
