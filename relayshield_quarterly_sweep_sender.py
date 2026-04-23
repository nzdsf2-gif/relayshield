"""
RelayShield Quarterly Sweep Reminder Lambda

Triggered by EventBridge every 90 days.
Sends a WhatsApp proactive sweep nudge to every fully-onboarded active
subscriber using the Meta-approved relayshield_quarterly_sweep template.

All tiers receive the nudge — no breach required to trigger this.
Business tiers receive a team-framing variant via the template variable.

Phone number resolution:
  Primary path: KMS decrypt of phone_encrypted field (all post-migration records).
  Fallback: legacy plaintext whatsapp_number field (pre-migration records only).

Deployment:
  - Lambda name: relayshield-quarterly-sweep-sender
  - Trigger: EventBridge scheduled rule — rate(90 days)
  - Runtime: Python 3.12
  - Timeout: 5 minutes
  - Memory: 256 MB
  - IAM: relayshield-breach-check-role-1sapnwdl (same role as digest)
    Needs: dynamodb:Scan on relayshield_users, kms:Decrypt on relayshield-data-key
"""

import base64
import hashlib
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
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
kms_client = boto3.client("kms")

USERS_TABLE = "relayshield_users"

KMS_PHONE_KEY_ALIAS = "alias/relayshield-data-key"

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

# Populate once Meta approves the relayshield_quarterly_sweep template.
# Template body — 1 variable:
#   {{1}} = tier-aware sweep prompt
#           Personal/Starter: "Your quarterly security sweep is due."
#           Business Basic+:  "Your team's quarterly security sweep is due."
#
# Suggested template body for Meta submission (UTILITY category):
#
#   🛡️ RelayShield quarterly check-in
#
#   {{1}}
#
#   Reply SWEEP to run your 5-minute Email Security Sweep — closes forwarding
#   rules, session backdoors, and rogue connected apps that survive password
#   resets if left unchecked.
#
#   Reply HELP for all available commands.
#   — RelayShield
QUARTERLY_TEMPLATE_SID = "PENDING_META_APPROVAL"

# ---------------------------------------------------------------------------
# Tier constants
# ---------------------------------------------------------------------------

TIER_STARTER = "business_starter"
TIER_BASIC = "business_basic"
TIER_SHIELD = "business_shield"
TIER_PRO = "business_shield_pro"

BUSINESS_TIERS = {TIER_STARTER, TIER_BASIC, TIER_SHIELD, TIER_PRO}

ELIGIBLE_STATES = {"ACTIVE", "EMPLOYEE_ACTIVE"}

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


# ---------------------------------------------------------------------------
# KMS phone decryption
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


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def get_all_active_users() -> list[dict]:
    """
    Return all user records where active=True and onboarding_state is
    ACTIVE or EMPLOYEE_ACTIVE. Handles DynamoDB pagination.
    """
    table = dynamodb.Table(USERS_TABLE)
    results = []

    for state in ELIGIBLE_STATES:
        response = table.scan(
            FilterExpression=(
                Attr("active").eq(True) & Attr("onboarding_state").eq(state)
            )
        )
        results.extend(response.get("Items", []))

        while "LastEvaluatedKey" in response:
            response = table.scan(
                FilterExpression=(
                    Attr("active").eq(True) & Attr("onboarding_state").eq(state)
                ),
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            results.extend(response.get("Items", []))

    return results


# ---------------------------------------------------------------------------
# Template variable builder
# ---------------------------------------------------------------------------

def build_sweep_prompt(subscription_tier: str, is_employee: bool) -> str:
    """
    Return the tier-aware sweep prompt for template variable {{1}}.
    Employees use the same personal framing (their sweep covers their own emails).
    Business admins get the team framing.
    """
    if subscription_tier in BUSINESS_TIERS and not is_employee:
        return "Your team's quarterly security sweep is due."
    return "Your quarterly security sweep is due."


# ---------------------------------------------------------------------------
# Twilio template sender
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
                "Quarterly sweep sent to %s — SID: %s status: %s",
                to_number, result.get("sid"), result.get("status"),
            )
            return True
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error(
            "Twilio HTTP %d sending quarterly sweep to %s: %s",
            exc.code, to_number, error_body,
        )
        return False
    except Exception as exc:
        logger.exception("Twilio quarterly sweep send failed for %s: %s", to_number, exc)
        return False


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """
    Entry point for EventBridge 90-day trigger.
    Sends quarterly sweep reminder to all eligible active subscribers.

    Optional test parameter:
      {"test_user_id": "your-user-id"}  — restricts send to a single user.
      Use to verify end-to-end delivery without messaging all subscribers.
    """
    test_user_id = event.get("test_user_id") if isinstance(event, dict) else None

    if QUARTERLY_TEMPLATE_SID == "PENDING_META_APPROVAL":
        logger.error(
            "Quarterly sweep template SID not configured — Meta approval still pending. "
            "Update QUARTERLY_TEMPLATE_SID in code and redeploy before triggering."
        )
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Template SID not configured"}),
        }

    now = datetime.now(timezone.utc).isoformat()
    logger.info("Quarterly sweep reminder starting — triggered_at=%s", now)

    try:
        account_sid, auth_token, from_number = get_twilio_credentials()
    except Exception as exc:
        logger.exception("Failed to retrieve Twilio credentials: %s", exc)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Credential retrieval failed"}),
        }

    try:
        users = get_all_active_users()
    except Exception as exc:
        logger.exception("Failed to retrieve active users: %s", exc)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "User retrieval failed"}),
        }

    logger.info("Found %d active users eligible for quarterly sweep.", len(users))

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

        tier = user.get("subscription_tier", "personal_shield")
        is_employee = bool(user.get("admin_user_id"))
        sweep_prompt = build_sweep_prompt(tier, is_employee)

        try:
            success = send_whatsapp_template(
                to_number=to_number,
                template_sid=QUARTERLY_TEMPLATE_SID,
                variables={"1": sweep_prompt},
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
                "Unexpected error sending quarterly sweep to user_id=%s: %s",
                user_id, exc,
            )

    logger.info(
        "Quarterly sweep complete — sent=%d skipped=%d failed=%d total=%d",
        sent, skipped, failed, len(users),
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "triggered_at": now,
            "sent": sent,
            "skipped": skipped,
            "failed": failed,
            "total_users": len(users),
        }),
    }
