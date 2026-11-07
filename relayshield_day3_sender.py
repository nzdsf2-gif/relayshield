"""
RelayShield Day 3 Onboarding Follow-Up Lambda

Triggered by a per-user EventBridge Scheduler one-time rule created 72 hours
after the subscriber's DynamoDB record is written (i.e. 72 hrs after payment).

The Day 3 window is the highest-churn point in the first week. This message
surfaces the three most valuable commands for the subscriber's tier to drive
first meaningful engagement before they go dormant.

Event payload (from EventBridge Scheduler):
    { "user_id": "...", "tier": "..." }

Template: relayshield_day3 (5 variables)
    {{1}} = Tier display name         e.g. "Personal Shield"
    {{2}} = Second command keyword    e.g. "REUSE" or "PHONE"
    {{3}} = Second command blurb      (short, tier-appropriate)
    {{4}} = Third command keyword     e.g. "SESSIONS" or "ADD"
    {{5}} = Third command blurb       (short, tier-appropriate)

Guard: if the user record is no longer active (cancelled in first 3 days),
the message is suppressed and the Lambda exits cleanly.

Deployment:
    - Lambda name: relayshield-day3-sender
    - Trigger: per-user EventBridge Scheduler one-time at() rule
    - Runtime: Python 3.12
    - Timeout: 30 seconds
    - Memory: 128 MB
    - IAM: requires DynamoDB GetItem on relayshield_users,
           Secrets Manager GetSecretValue for Twilio credentials

IAM prerequisites (set up once):
    1. Add scheduler:CreateSchedule to the stripe-webhook Lambda's IAM policy
    2. Create IAM role relayshield-scheduler-invoke-day3 with:
       - Trust policy: scheduler.amazonaws.com
       - Permission: lambda:InvokeFunction on this Lambda's ARN
    3. Set env vars on stripe-webhook Lambda:
       - DAY3_LAMBDA_ARN  = arn:aws:lambda:<region>:<account>:function:relayshield-day3-sender
       - DAY3_SCHEDULER_ROLE_ARN = arn:aws:iam::<account>:role/relayshield-scheduler-invoke-day3
"""

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from datetime import datetime, timezone

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

# ---------------------------------------------------------------------------
# Send idempotency (per-user, per-period markers)
# ---------------------------------------------------------------------------
# A second invocation for the same period must not re-send. Before sending
# to a user, claim a marker in relayshield_send_markers with a conditional
# write; only the invocation that wins the claim sends. The ci.import-probe
# guard above is layer one (probe); this is the durable layer two.

SEND_MARKERS_TABLE = "relayshield_send_markers"
SEND_TYPE = "day3"
MARKER_TTL_SECONDS = 120 * 24 * 3600  # 120 days


def _claim_send_marker(marker_id: str, user_id: str, period: str) -> bool:
    """Claim the marker for (user, period). True if this invocation owns the send."""
    now = datetime.now(timezone.utc)
    try:
        dynamodb.Table(SEND_MARKERS_TABLE).put_item(
            Item={
                "marker_id": marker_id,
                "user_id": user_id,
                "send_type": SEND_TYPE,
                "period": period,
                "status": "claimed",
                "claimed_at": now.isoformat(),
                "expires_at": int(now.timestamp()) + MARKER_TTL_SECONDS,
            },
            ConditionExpression="attribute_not_exists(marker_id)",
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            logger.info("Send marker already claimed marker_id=%s — skipping.", marker_id)
            return False
        raise


def _mark_send_sent(marker_id: str, message_id: str = "") -> None:
    """Mark a claimed marker as sent. Best effort; a failure here does not resend."""
    try:
        dynamodb.Table(SEND_MARKERS_TABLE).update_item(
            Key={"marker_id": marker_id},
            UpdateExpression="SET #st = :sent, sent_at = :now, message_id = :mid",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":sent": "sent",
                ":now": datetime.now(timezone.utc).isoformat(),
                ":mid": message_id,
            },
        )
    except Exception as exc:
        logger.warning("Failed to mark send marker sent marker_id=%s: %s", marker_id, exc)

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
# Template
# ---------------------------------------------------------------------------

# Update this SID once Meta approves the relayshield_day3 template.
#
# Template body (5 variables — submit exactly this text to Meta):
#
#   🛡️ *3 days in — here's how to make RelayShield work harder for you.*
#
#   You're on {{1}}. Here are the 3 commands that make the biggest difference:
#
#   1️⃣ *SWEEP* — Full inbox security audit. Finds backdoors attackers leave
#   behind that survive a password reset.
#
#   2️⃣ *{{2}}* — {{3}}
#
#   3️⃣ *{{4}}* — {{5}}
#
#   Reply *HELP* for the full command menu.
#
# Category: UTILITY (onboarding sequence, not promotional)
DAY3_TEMPLATE_SID = "HXb8e3c80de422dae90addf0bd6561b2b4"

# ---------------------------------------------------------------------------
# Tier constants
# ---------------------------------------------------------------------------

TIER_PERSONAL = "personal_shield"
TIER_STARTER = "business_starter"
TIER_BASIC = "business_basic"
TIER_SHIELD = "business_shield"
TIER_PRO = "business_shield_pro"

TIER_DISPLAY_NAMES = {
    TIER_PERSONAL: "Personal Shield",
    TIER_STARTER:  "Business Starter",
    TIER_BASIC:    "Business Basic",
    TIER_SHIELD:   "Business Shield",
    TIER_PRO:      "Business Shield Pro",
}

BUSINESS_TIERS = {TIER_STARTER, TIER_BASIC, TIER_SHIELD, TIER_PRO}

# Eligible onboarding states — suppress if user cancelled before Day 3 fired
DAY3_ELIGIBLE_STATES = {"ACTIVE", "AWAITING_EMAIL_1", "AWAITING_EMAIL_2", "EMPLOYEE_ACTIVE"}

# ---------------------------------------------------------------------------
# Tier-specific template variable content
# ---------------------------------------------------------------------------

# Personal Shield: SWEEP + REUSE + SESSIONS
_PERSONAL_VARS = {
    "cmd2":  "REUSE",
    "cmd2_blurb": (
        "Identify passwords reused across multiple accounts — the most common "
        "way one breach becomes five."
    ),
    "cmd3":  "SESSIONS",
    "cmd3_blurb": (
        "Audit active sessions and log out any unrecognised devices from "
        "Google, Microsoft, and social media."
    ),
}

# Business tiers: SWEEP + PHONE + ADD
_BUSINESS_VARS = {
    "cmd2":  "PHONE",
    "cmd2_blurb": (
        "Harden your carrier account against SIM swap attacks — takes 5 minutes "
        "and blocks the most common account takeover method."
    ),
    "cmd3":  "ADD",
    "cmd3_blurb": (
        "Add a team member's email address to extend monitoring to your "
        "employees and contractors."
    ),
}


def get_tier_vars(tier: str) -> dict:
    return _BUSINESS_VARS if tier in BUSINESS_TIERS else _PERSONAL_VARS


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
    auth_token  = get_secret_json(TWILIO_TOKEN_SECRET, "TWILIO_AUTH_TOKEN")
    from_number = get_secret_json(TWILIO_FROM_SECRET, "TWILIO_WHATSAPP_NUMBER")
    return account_sid, auth_token, from_number


# ---------------------------------------------------------------------------
# DynamoDB helper
# ---------------------------------------------------------------------------

def get_user(user_id: str) -> dict | None:
    """Return the user record or None if not found."""
    table = dynamodb.Table(USERS_TABLE)
    response = table.get_item(Key={"user_id": user_id})
    return response.get("Item")


# ---------------------------------------------------------------------------
# Twilio
# ---------------------------------------------------------------------------

def decrypt_phone(ciphertext_b64: str) -> str:
    """Decrypt KMS-encrypted phone ciphertext (base64). Returns E.164 string."""
    response = kms_client.decrypt(
        CiphertextBlob=base64.b64decode(ciphertext_b64),
    )
    return response["Plaintext"].decode()


def to_whatsapp_number(phone: str) -> str:
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
) -> str | None:
    """Send an approved WhatsApp template via Twilio Content API. Returns the Twilio message SID on success, None on failure."""
    url = TWILIO_MESSAGES_URL.format(account_sid=account_sid)
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()

    payload = urllib.parse.urlencode({
        "From": to_whatsapp_number(from_number),
        "To":   to_whatsapp_number(to_number),
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
                "Day 3 template sent to %s — SID: %s status: %s",
                to_number, result.get("sid"), result.get("status"),
            )
            return result.get("sid")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error(
            "Twilio HTTP %d sending Day 3 to %s: %s", exc.code, to_number, error_body
        )
        return None
    except Exception as exc:
        logger.exception("Twilio Day 3 send failed for %s: %s", to_number, exc)
        return None


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """
    Entry point for EventBridge Scheduler one-time trigger.

    Expected event shape:
        { "user_id": "...", "tier": "..." }
    """
    # ci.import-probe guard: the Deploy Changed Lambdas smoke step
    # invokes every deployed function with {"source": "ci.import-probe"}.
    # Without this early return the probe sends a real message to all
    # subscribers. Mirrors the guard in relayshield_intel_feed.py.
    if isinstance(event, dict) and event.get("source") == "ci.import-probe":
        logger.info("ci.import-probe: module imported, returning without sending")
        return {"statusCode": 200, "probe": "ok"}
    if DAY3_TEMPLATE_SID == "PENDING_META_APPROVAL":
        logger.error(
            "Day 3 template SID not configured — Meta approval still pending. "
            "Update DAY3_TEMPLATE_SID and redeploy."
        )
        return {"statusCode": 500, "body": "Template SID not configured"}

    user_id = event.get("user_id", "")
    tier    = event.get("tier", "")

    if not user_id:
        logger.error("Day 3 event missing user_id — cannot proceed.")
        return {"statusCode": 400, "body": "Missing user_id"}

    # Confirm user is still active — suppress if cancelled in first 3 days
    try:
        user = get_user(user_id)
    except Exception as exc:
        logger.exception("DynamoDB lookup failed for user_id=%s: %s", user_id, exc)
        return {"statusCode": 500, "body": "DynamoDB error"}

    if not user:
        logger.warning("user_id=%s not found — skipping Day 3 send.", user_id)
        return {"statusCode": 200, "body": "User not found — suppressed"}

    if not user.get("active", False):
        logger.info("user_id=%s is inactive — suppressing Day 3 message.", user_id)
        return {"statusCode": 200, "body": "User inactive — suppressed"}

    onboarding_state = user.get("onboarding_state", "")
    if onboarding_state not in DAY3_ELIGIBLE_STATES:
        logger.info(
            "user_id=%s onboarding_state=%s — suppressing Day 3 message.",
            user_id, onboarding_state,
        )
        return {"statusCode": 200, "body": f"State {onboarding_state!r} — suppressed"}

    try:
        to_number = get_user_whatsapp_number(user)
    except Exception as exc:
        logger.exception("Failed to resolve phone for user_id=%s: %s", user_id, exc)
        return {"statusCode": 200, "body": "Phone resolution failed — suppressed"}

    if not to_number:
        logger.error("user_id=%s has no phone number — cannot send Day 3.", user_id)
        return {"statusCode": 200, "body": "No number — suppressed"}

    # Use tier from DynamoDB (source of truth) rather than event payload
    resolved_tier = user.get("subscription_tier", tier)
    tier_name = TIER_DISPLAY_NAMES.get(resolved_tier, "RelayShield")
    tv = get_tier_vars(resolved_tier)

    try:
        account_sid, auth_token, from_number = get_twilio_credentials()
    except Exception as exc:
        logger.exception("Failed to retrieve Twilio credentials: %s", exc)
        return {"statusCode": 500, "body": "Credential retrieval failed"}

    # Idempotency: claim the one-time per-user marker before sending.
    # Only the invocation that wins the claim sends.
    marker_id = f"day3#{user_id}"
    try:
        claimed = _claim_send_marker(marker_id, user_id, "once")
    except Exception as exc:
        logger.exception(
            "Send marker claim failed user_id=%s: %s — skipping send.",
            user_id, exc,
        )
        return {"statusCode": 200, "body": "Marker claim failed — suppressed"}
    if not claimed:
        logger.info("Day 3 already sent user_id=%s — skipping.", user_id)
        return {"statusCode": 200, "body": "Already sent — suppressed"}

    message_sid = send_whatsapp_template(
        to_number=to_number,
        template_sid=DAY3_TEMPLATE_SID,
        variables={
            "1": tier_name,
            "2": tv["cmd2"],
            "3": tv["cmd2_blurb"],
            "4": tv["cmd3"],
            "5": tv["cmd3_blurb"],
        },
        account_sid=account_sid,
        auth_token=auth_token,
        from_number=from_number,
    )
    sent = bool(message_sid)
    if message_sid:
        _mark_send_sent(marker_id, message_sid)

    logger.info(
        "Day 3 follow-up complete — user_id=%s tier=%s sent=%s",
        user_id, resolved_tier, sent,
    )

    return {
        "statusCode": 200,
        "body": json.dumps({"user_id": user_id, "tier": resolved_tier, "sent": sent}),
    }
