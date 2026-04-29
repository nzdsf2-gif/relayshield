"""
RelayShield Monthly OAuth Audit Reminder Lambda

Triggered by EventBridge every 30 days.
Sends a proactive WhatsApp reminder to all active Business Basic, Business Shield,
and Business Shield Pro subscribers to audit their connected Google and Microsoft
OAuth apps.

Personal Shield and Business Starter subscribers are excluded — proactive monthly
OAuth reminders are a Business Basic+ differentiator. All tiers can still trigger
the OAUTH command on demand.

Why this matters: OAuth supply chain attacks (e.g. the Vercel/Context.ai breach)
bypass every credential security control. The attack surface is the apps users
have trusted with access to their accounts — not the accounts themselves. Monthly
reminders keep this surface minimised.

Phone number resolution:
    Primary:  KMS decrypt of phone_encrypted (post-migration records)
    Fallback: legacy plaintext whatsapp_number (pre-migration records only)

Template: relayshield_monthly_oauth (2 variables)
    {{1}} = Tier display name        e.g. "Business Basic"
    {{2}} = Team or individual frame e.g. "your team's" or "your"

Submit exactly this body to Meta (Category: UTILITY):

    🔐 *Monthly Security Check — RelayShield*

    Time for {{2}} monthly connected app audit, {{1}}.

    Third-party apps with access to your Google and Microsoft accounts are one of
    the fastest-growing attack vectors — most people never review them.

    *2-minute audit:*
    → Google: myaccount.google.com/permissions
    → Microsoft: myapps.microsoft.com

    Remove anything you don't recognise or no longer need.

    Reply *OAUTH* for a step-by-step walkthrough.

    🛡️ RelayShield — monthly protection active

Deployment:
    - Lambda name:   relayshield-monthly-oauth-reminder
    - Handler:       relayshield_monthly_oauth_reminder.lambda_handler
    - Trigger:       EventBridge rate(30 days)
    - Runtime:       Python 3.12
    - Timeout:       300 seconds (5 minutes)
    - Memory:        256 MB
    - IAM:           Same role as quarterly sweep sender
                     (relayshield-breach-check-role-1sapnwdl)
                     Needs: dynamodb:Scan on relayshield_users,
                            kms:Decrypt on alias/relayshield-data-key,
                            secretsmanager:GetSecretValue for Twilio secrets

Test payload (single user, safe in production):
    { "test_user_id": "user-onboard-test-001" }
"""

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

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

USERS_TABLE         = "relayshield_users"
KMS_PHONE_KEY_ALIAS = "alias/relayshield-data-key"

# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

TWILIO_SID_SECRET   = "relayshield/twilio_account_sid"
TWILIO_TOKEN_SECRET = "relayshield/twilio_auth_token"
TWILIO_FROM_SECRET  = "relayshield/twilio_whatsapp_number"

TWILIO_MESSAGES_URL = (
    "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
)

# ---------------------------------------------------------------------------
# Template
# Update this SID once Meta approves the relayshield_monthly_oauth template.
# ---------------------------------------------------------------------------

MONTHLY_OAUTH_TEMPLATE_SID = "HXddda44b6746ae34ecf184a6ada284cc7"

# ---------------------------------------------------------------------------
# Tier constants
# ---------------------------------------------------------------------------

TIER_PERSONAL = "personal_shield"
TIER_STARTER  = "business_starter"
TIER_BASIC    = "business_basic"
TIER_SHIELD   = "business_shield"
TIER_PRO      = "business_shield_pro"

# Only these tiers receive the monthly OAuth reminder
OAUTH_REMINDER_TIERS = {TIER_BASIC, TIER_SHIELD, TIER_PRO}

TIER_DISPLAY_NAMES = {
    TIER_BASIC:   "Business Basic",
    TIER_SHIELD:  "Business Shield",
    TIER_PRO:     "Business Shield Pro",
}

# Eligible onboarding states — skip users still mid-onboarding
ELIGIBLE_STATES = {"ACTIVE", "AWAITING_EMAIL_1", "AWAITING_EMAIL_2", "EMPLOYEE_ACTIVE"}

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
    account_sid = get_secret_json(TWILIO_SID_SECRET,   "TWILIO_ACCOUNT_SID")
    auth_token  = get_secret_json(TWILIO_TOKEN_SECRET,  "TWILIO_AUTH_TOKEN")
    from_number = get_secret_json(TWILIO_FROM_SECRET,   "TWILIO_WHATSAPP_NUMBER")
    return account_sid, auth_token, from_number


# ---------------------------------------------------------------------------
# Phone helpers
# ---------------------------------------------------------------------------

def decrypt_phone(ciphertext_b64: str) -> str:
    """KMS-decrypt a base64-encoded phone ciphertext. Returns E.164 string."""
    response = kms_client.decrypt(CiphertextBlob=base64.b64decode(ciphertext_b64))
    return response["Plaintext"].decode()


def get_whatsapp_number(user: dict) -> str:
    """
    Return the whatsapp:-prefixed number for outbound sends.
    Primary:  KMS decrypt of phone_encrypted (post-migration records).
    Fallback: legacy plaintext whatsapp_number field.
    """
    if "phone_encrypted" in user:
        phone = decrypt_phone(user["phone_encrypted"])
        phone = phone.replace("whatsapp:", "").strip()
        return f"whatsapp:{phone}"
    legacy = user.get("whatsapp_number", "")
    if legacy and not legacy.startswith("whatsapp:"):
        legacy = f"whatsapp:{legacy}"
    return legacy


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def scan_oauth_reminder_users() -> list[dict]:
    """Return all active Business Basic+ users in eligible onboarding states."""
    table  = dynamodb.Table(USERS_TABLE)
    users: list[dict] = []
    kwargs: dict = {
        "FilterExpression": Attr("active").eq(True),
    }
    while True:
        response = table.scan(**kwargs)
        for item in response.get("Items", []):
            tier  = item.get("subscription_tier", "")
            state = item.get("onboarding_state", "")
            if tier in OAUTH_REMINDER_TIERS and state in ELIGIBLE_STATES:
                users.append(item)
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    return users


def get_user_by_id(user_id: str) -> dict | None:
    table    = dynamodb.Table(USERS_TABLE)
    response = table.get_item(Key={"user_id": user_id})
    return response.get("Item")


# ---------------------------------------------------------------------------
# Twilio — send template
# ---------------------------------------------------------------------------

def send_whatsapp_template(
    to_number: str,
    template_sid: str,
    variables: dict,
    account_sid: str,
    auth_token: str,
    from_number: str,
) -> bool:
    """Send an approved WhatsApp template via Twilio Content API. Returns True on success."""
    url         = TWILIO_MESSAGES_URL.format(account_sid=account_sid)
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()

    to_number   = to_number if to_number.startswith("whatsapp:") else f"whatsapp:{to_number}"
    from_number = from_number if from_number.startswith("whatsapp:") else f"whatsapp:{from_number}"

    payload = urllib.parse.urlencode({
        "From":             from_number,
        "To":               to_number,
        "ContentSid":       template_sid,
        "ContentVariables": json.dumps(variables),
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type":  "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            logger.info(
                "OAuth reminder sent to %s — SID: %s status: %s",
                to_number, result.get("sid"), result.get("status"),
            )
            return True
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error(
            "Twilio HTTP %d sending OAuth reminder to %s: %s",
            exc.code, to_number, error_body,
        )
        return False
    except Exception as exc:
        logger.exception("OAuth reminder send failed for %s: %s", to_number, exc)
        return False


# ---------------------------------------------------------------------------
# Per-user processing
# ---------------------------------------------------------------------------

def process_user(
    user: dict,
    account_sid: str,
    auth_token: str,
    from_number: str,
) -> str:
    """
    Send monthly OAuth reminder to one user.
    Returns: "sent" | "skipped" | "failed"
    """
    user_id = user.get("user_id", "unknown")
    tier    = user.get("subscription_tier", "")

    if tier not in OAUTH_REMINDER_TIERS:
        logger.info("user_id=%s tier=%s — not eligible, skipping.", user_id, tier)
        return "skipped"

    # Resolve phone
    try:
        to_number = get_whatsapp_number(user)
    except Exception as exc:
        logger.exception("Phone resolution failed user_id=%s: %s", user_id, exc)
        return "skipped"

    if not to_number or to_number == "whatsapp:":
        logger.warning("user_id=%s has no phone number — skipping.", user_id)
        return "skipped"

    # Build template variables
    tier_name  = TIER_DISPLAY_NAMES.get(tier, "RelayShield")
    is_admin   = not bool(user.get("admin_user_id"))   # admins have no admin_user_id
    team_frame = "your team's" if is_admin else "your"

    sent = send_whatsapp_template(
        to_number=to_number,
        template_sid=MONTHLY_OAUTH_TEMPLATE_SID,
        variables={
            "1": tier_name,
            "2": team_frame,
        },
        account_sid=account_sid,
        auth_token=auth_token,
        from_number=from_number,
    )

    logger.info(
        "OAuth reminder — user_id=%s tier=%s is_admin=%s sent=%s",
        user_id, tier, is_admin, sent,
    )
    return "sent" if sent else "failed"


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """
    Entry point for EventBridge scheduled trigger (rate: 30 days).

    Test payload (single user, safe in production):
        { "test_user_id": "user-onboard-test-001" }
    """
    if MONTHLY_OAUTH_TEMPLATE_SID == "PENDING_META_APPROVAL":
        logger.error(
            "Monthly OAuth reminder template SID not configured — "
            "Meta approval still pending. Update MONTHLY_OAUTH_TEMPLATE_SID and redeploy."
        )
        return {"statusCode": 500, "body": "Template SID not configured"}

    logger.info("Monthly OAuth reminder starting.")

    try:
        account_sid, auth_token, from_number = get_twilio_credentials()
    except Exception as exc:
        logger.exception("Failed to retrieve Twilio credentials: %s", exc)
        return {"statusCode": 500, "body": "Credential retrieval failed"}

    # Determine user list
    test_user_id = event.get("test_user_id")
    if test_user_id:
        user  = get_user_by_id(test_user_id)
        users = [user] if user else []
        logger.info("Test mode — single user: %s", test_user_id)
    else:
        users = scan_oauth_reminder_users()
        logger.info(
            "Sending monthly OAuth reminder to %d Business Basic+ user(s).", len(users)
        )

    counters: dict[str, int] = {"sent": 0, "skipped": 0, "failed": 0}

    for user in users:
        outcome = process_user(user, account_sid, auth_token, from_number)
        counters[outcome] = counters.get(outcome, 0) + 1

    logger.info(
        "Monthly OAuth reminder complete — sent=%d skipped=%d failed=%d",
        counters["sent"], counters["skipped"], counters["failed"],
    )

    return {
        "statusCode": 200,
        "body": json.dumps(counters),
    }
