"""
RelayShield Monthly Security Digest Sender Lambda

Triggered by EventBridge on the 1st of each month (9:00 AM UTC).
Sends a personalised WhatsApp security digest to every active subscriber
using the Meta-approved relayshield_monthly_digest template.

Digest content per user:
  - Month/year header
  - Monitored email count + scan total for the month
  - Breach status (all clear or count of breaches found)
  - Rotating monthly security tip (1 per month, 12-tip cycle)

Eligibility:
  - onboarding_state must be ACTIVE or EMPLOYEE_ACTIVE
  - active flag must be True
  - Must have at least 1 monitored email address

Deployment:
  - Lambda name: relayshield-digest-sender
  - Trigger: EventBridge scheduled rule — cron(0 9 1 * ? *)
  - Runtime: Python 3.12
  - Timeout: 5 minutes (allow for large subscriber base)
  - Memory: 256 MB
"""

import base64
import calendar
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Optional

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
kms_client = boto3.client("kms")

USERS_TABLE = "relayshield_users"

KMS_PHONE_KEY_ALIAS = "alias/relayshield-data-key"
MONITORED_EMAILS_TABLE = "relayshield_monitored_emails"
BREACH_ALERTS_TABLE = "relayshield_breach_alerts"

# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

TWILIO_SID_SECRET = "relayshield/twilio_account_sid"
TWILIO_TOKEN_SECRET = "relayshield/twilio_auth_token"
TWILIO_FROM_SECRET = "relayshield/twilio_whatsapp_number"

TWILIO_MESSAGES_URL = (
    "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
)

# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

ANTHROPIC_SECRET_NAME = "relayshield/anthropic_api_key"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------

# Update this SID once Meta approves the relayshield_monthly_digest template.
# Template body (4 variables):
#   {{1}} = Month + Year          e.g. "April 2026"
#   {{2}} = Scan summary line     e.g. "3 email addresses monitored — 90 scans completed"
#   {{3}} = Breach status line    e.g. "✅ All clear — no breaches detected this month."
#   {{4}} = Monthly security tip  (full tip text from MONTHLY_TIPS)
DIGEST_TEMPLATE_SID = "HX58cb69a1f9de4793ae225015d186c8e6"

# ---------------------------------------------------------------------------
# Eligible states
# ---------------------------------------------------------------------------

DIGEST_ELIGIBLE_STATES = {"ACTIVE", "EMPLOYEE_ACTIVE"}

# ---------------------------------------------------------------------------
# Rotating monthly security tips (indexed 1–12 by calendar month)
# ---------------------------------------------------------------------------

MONTHLY_TIPS = {
    1: (
        "New year, new passwords. Change any password you've reused for more than a year "
        "— start with email and banking accounts. Reply *RESET* for a strong password guide."
    ),
    2: (
        "Romance scams spike in February. Unexpected contacts asking for money, gift cards, "
        "or crypto — screenshot immediately and block. The urgency in the message is the attack."
    ),
    3: (
        "Tax season is peak phishing season. The IRS never contacts you by email, text, or "
        "social media. Any message claiming to be the IRS asking for payment or personal "
        "details is fraud — do not click, do not call back."
    ),
    4: (
        "Check your connected apps. Go to myaccount.google.com/permissions — remove anything "
        "you don't recognise or no longer actively use. Reply *SESSIONS* for a full guided "
        "walkthrough including Microsoft and social media."
    ),
    5: (
        "SIM swap attacks are rising. Add a PIN to your carrier account today — it takes "
        "5 minutes and blocks the most common account takeover method targeting phone numbers. "
        "Reply *PHONE* for carrier-specific steps."
    ),
    6: (
        "Mid-year password check. Reply *REUSE* to walk through your most critical accounts "
        "and identify reused passwords — the most common way one breach becomes five."
    ),
    7: (
        "AI-generated phishing emails are now indistinguishable from legitimate ones. "
        "New rule: never act on urgency in an email. Navigate directly to the company's "
        "website — never click a link in a message to log in."
    ),
    8: (
        "Session tokens outlast passwords. Even after changing your password, an attacker "
        "holding your session token retains full account access. Reply *SESSIONS* to audit "
        "and revoke all active sessions across Google, Microsoft, and social media."
    ),
    9: (
        "OAuth apps accumulate silently. Every app you've granted Google or Microsoft access "
        "to holds a live key to your account — even apps you stopped using years ago. "
        "Audit them quarterly. Reply *SESSIONS* to start."
    ),
    10: (
        "October is Cybersecurity Awareness Month. The single most effective upgrade you "
        "can make today: enable an authenticator app (not SMS) for two-factor authentication "
        "on your primary email — it eliminates the most common MFA bypass method."
    ),
    11: (
        "Holiday shopping season is card skimmer season. Use a virtual card number for "
        "online purchases — your bank or Apple Pay can generate one in seconds. "
        "Never shop on public Wi-Fi without a VPN."
    ),
    12: (
        "Year-end security review. Reply *SWEEP* to close email backdoors before the new "
        "year — forwarding rules, rogue recovery contacts, and unknown connected apps "
        "planted by attackers survive password resets if not removed."
    ),
}


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


def generate_security_tip(month_name: str, year: int, fallback_month: int) -> str:
    """
    Call Claude Haiku to generate a fresh, current security tip for the digest.
    Prompt is grounded in the current month so tips stay topical.
    Falls back to the hardcoded MONTHLY_TIPS rotation on any failure.
    Called once per digest run — not per user.
    """
    try:
        api_key = get_secret(ANTHROPIC_SECRET_NAME)
        prompt = (
            f"Generate ONE concise, actionable security tip for a monthly security digest "
            f"sent to SMB owners and individual users. Current month: {month_name} {year}.\n\n"
            "Requirements:\n"
            "- Focus on a specific, real attack vector relevant right now — choose from: "
            "credential stuffing, SIM swap fraud, phishing, session hijacking, OAuth token abuse, "
            "infostealer malware, business email compromise, fake invoice fraud, or similar\n"
            "- Include ONE specific action the user can take immediately\n"
            "- Where appropriate, end with one RelayShield command the user can reply with: "
            "SWEEP, SESSIONS, REUSE, PHONE, OTP, OAUTH, ATTACH, or SMS\n"
            "- Maximum 220 characters total\n"
            "- Plain language, no bullet points, no jargon\n"
            "- Do not start with 'Tip:' or any label — go straight to the content"
        )

        payload = json.dumps({
            "model": ANTHROPIC_MODEL,
            "max_tokens": 120,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()

        req = urllib.request.Request(
            ANTHROPIC_API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            tip = data["content"][0]["text"].strip()
            logger.info("Claude security tip generated for %s %d: %s", month_name, year, tip[:80])
            return tip

    except Exception as exc:
        logger.warning("Claude tip generation failed — falling back to MONTHLY_TIPS: %s", exc)
        return MONTHLY_TIPS.get(fallback_month, MONTHLY_TIPS[1])


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def get_all_active_users() -> list[dict]:
    """
    Return all user records where active=True and onboarding_state is
    ACTIVE or EMPLOYEE_ACTIVE. Excludes incomplete onboarding.
    """
    table = dynamodb.Table(USERS_TABLE)
    results = []

    for state in DIGEST_ELIGIBLE_STATES:
        response = table.scan(
            FilterExpression=(
                Attr("active").eq(True) & Attr("onboarding_state").eq(state)
            )
        )
        results.extend(response.get("Items", []))

        # Handle DynamoDB pagination
        while "LastEvaluatedKey" in response:
            response = table.scan(
                FilterExpression=(
                    Attr("active").eq(True) & Attr("onboarding_state").eq(state)
                ),
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            results.extend(response.get("Items", []))

    return results


def count_monitored_emails(user_id: str) -> int:
    """Count active monitored emails for a user."""
    table = dynamodb.Table(MONITORED_EMAILS_TABLE)
    response = table.scan(
        FilterExpression=(
            Attr("user_id").eq(user_id) & Attr("active").eq(True)
        ),
        Select="COUNT",
    )
    return response.get("Count", 0)


def count_recent_breaches(user_id: str, days: int = 30) -> int:
    """
    Count breach alerts for a user in the past N days.
    Uses alert_sent_at ISO timestamp for filtering.
    """
    table = dynamodb.Table(BREACH_ALERTS_TABLE)
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).isoformat()

    response = table.scan(
        FilterExpression=(
            Attr("user_id").eq(user_id) & Attr("alert_sent_at").gte(cutoff)
        ),
        Select="COUNT",
    )
    return response.get("Count", 0)


# ---------------------------------------------------------------------------
# Twilio template sender
# ---------------------------------------------------------------------------

def decrypt_phone(ciphertext_b64: str) -> str:
    """Decrypt KMS-encrypted phone ciphertext (base64). Returns E.164 string."""
    response = kms_client.decrypt(
        CiphertextBlob=base64.b64decode(ciphertext_b64),
    )
    return response["Plaintext"].decode()


def to_whatsapp_number(phone: str) -> str:
    """Prefix E.164 number with whatsapp: for Twilio (idempotent)."""
    if phone.startswith("whatsapp:"):
        return phone
    return f"whatsapp:{phone}"


def get_user_whatsapp_number(user: dict) -> str:
    """
    Return the whatsapp:-prefixed number for outbound sends.
    Primary: KMS decrypt of phone_encrypted (post-migration records).
    Fallback: legacy plaintext whatsapp_number (pre-migration records).
    """
    if "phone_encrypted" in user:
        return to_whatsapp_number(decrypt_phone(user["phone_encrypted"]))
    legacy = user.get("whatsapp_number", "")
    return to_whatsapp_number(legacy) if legacy else ""


def send_whatsapp_template(
    to_number: str,
    template_sid: str,
    variables: dict,
    account_sid: str,
    auth_token: str,
    from_number: str,
) -> bool:
    """
    Send an approved WhatsApp template message via Twilio Content API.
    Returns True on success.
    """
    url = TWILIO_MESSAGES_URL.format(account_sid=account_sid)
    credentials = base64.b64encode(
        f"{account_sid}:{auth_token}".encode()
    ).decode()

    payload = urllib.parse.urlencode({
        "From": to_whatsapp_number(from_number),
        "To": to_whatsapp_number(to_number),
        "ContentSid": template_sid,
        "ContentVariables": json.dumps(variables),
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
                "Digest sent to %s — SID: %s status: %s",
                to_number, result.get("sid"), result.get("status"),
            )
            return True
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error(
            "Twilio HTTP %d sending digest to %s: %s",
            exc.code, to_number, error_body,
        )
        return False
    except Exception as exc:
        logger.exception("Twilio digest send failed for %s: %s", to_number, exc)
        return False


# ---------------------------------------------------------------------------
# Digest content builders
# ---------------------------------------------------------------------------

def build_scan_summary(email_count: int, days_in_month: int, month_name: str) -> str:
    """Build the scan summary line for the digest template."""
    scan_count = email_count * days_in_month
    word = "address" if email_count == 1 else "addresses"
    return f"{email_count} email {word} monitored — {scan_count} scans completed in {month_name}"


def build_status_line(breach_count: int, month_name: str) -> str:
    """Build the breach status line for the digest template."""
    if breach_count == 0:
        return f"✅ All clear — no new breaches detected in {month_name}."
    elif breach_count == 1:
        return (
            "⚠️ 1 known breach on record — remediation steps sent for all new detections."
        )
    else:
        return (
            f"⚠️ {breach_count} known breaches on record — remediation steps sent "
            "for all new detections."
        )


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """
    Entry point for EventBridge monthly trigger.
    Sends security digest to all eligible active subscribers.

    Optional test parameter:
      {"test_user_id": "your-user-id"}  — restricts send to a single user.
      Use to verify end-to-end delivery without messaging all subscribers.
    """
    test_user_id = event.get("test_user_id") if isinstance(event, dict) else None

    if DIGEST_TEMPLATE_SID == "PENDING_META_APPROVAL":
        logger.error(
            "Digest template SID not configured — Meta approval still pending. "
            "Update DIGEST_TEMPLATE_SID in code and redeploy before triggering."
        )
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Template SID not configured"}),
        }

    now = datetime.now(timezone.utc)
    # Digest fires on the 1st — report on the previous (completed) month
    if now.month == 1:
        prev_month_num = 12
        prev_year = now.year - 1
    else:
        prev_month_num = now.month - 1
        prev_year = now.year
    month_name     = datetime(prev_year, prev_month_num, 1).strftime("%B")
    days_in_month  = calendar.monthrange(prev_year, prev_month_num)[1]
    month_year     = f"{month_name} {prev_year}"

    logger.info(
        "Monthly digest starting — month=%s days_in_month=%d",
        month_year, days_in_month,
    )

    # Retrieve Twilio credentials once for the run
    try:
        account_sid, auth_token, from_number = get_twilio_credentials()
    except Exception as exc:
        logger.exception("Failed to retrieve Twilio credentials: %s", exc)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Credential retrieval failed"}),
        }

    # Generate security tip via Claude — falls back to MONTHLY_TIPS rotation on failure
    monthly_tip = generate_security_tip(month_name, prev_year, prev_month_num)

    # Fetch all eligible users
    try:
        users = get_all_active_users()
    except Exception as exc:
        logger.exception("Failed to retrieve active users: %s", exc)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "User retrieval failed"}),
        }

    logger.info("Found %d active users eligible for digest.", len(users))

    if test_user_id:
        users = [u for u in users if u.get("user_id") == test_user_id]
        logger.info(
            "TEST MODE — restricted to user_id=%s (%d user found).",
            test_user_id, len(users),
        )
        if not users:
            return {
                "statusCode": 404,
                "body": json.dumps({"error": f"test_user_id={test_user_id} not found or not active"}),
            }

    sent = 0
    skipped = 0
    failed = 0

    for user in users:
        user_id = user.get("user_id", "unknown")
        try:
            to_number = get_user_whatsapp_number(user)
        except Exception as exc:
            logger.error(
                "Failed to resolve phone for user_id=%s: %s — skipping.", user_id, exc
            )
            skipped += 1
            continue

        if not to_number:
            logger.warning("Skipping user_id=%s — no phone number resolved.", user_id)
            skipped += 1
            continue

        try:
            # Count monitored emails — skip users who haven't completed onboarding
            email_count = count_monitored_emails(user_id)
            if email_count == 0:
                logger.info(
                    "Skipping user_id=%s — no active monitored emails.", user_id
                )
                skipped += 1
                continue

            # Count breaches in the past 30 days
            breach_count = count_recent_breaches(user_id, days=30)

            # Build template variable values
            scan_summary = build_scan_summary(email_count, days_in_month, month_name)
            status_line = build_status_line(breach_count, month_name)

            success = send_whatsapp_template(
                to_number=to_number,
                template_sid=DIGEST_TEMPLATE_SID,
                variables={
                    "1": month_year,
                    "2": scan_summary,
                    "3": status_line,
                    "4": monthly_tip,
                },
                account_sid=account_sid,
                auth_token=auth_token,
                from_number=from_number,
            )

            if success:
                sent += 1
            else:
                failed += 1

        except Exception as exc:
            failed += 1
            logger.exception(
                "Unexpected error processing digest for user_id=%s: %s",
                user_id, exc,
            )

    logger.info(
        "Monthly digest complete — sent=%d skipped=%d failed=%d total=%d",
        sent, skipped, failed, len(users),
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "month": month_year,
            "sent": sent,
            "skipped": skipped,
            "failed": failed,
            "total_users": len(users),
        }),
    }
