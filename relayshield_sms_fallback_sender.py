"""
RelayShield SMS Fallback Sender Lambda

Scans relayshield_users for records with pending_sms_fallback set and
pending_sms_fallback_at older than 4 hours. Fires a plain SMS via Twilio
to the user's registered phone number, then clears the fallback fields.

An inbound WhatsApp message clears pending_sms_fallback immediately in the
webhook (proving the user has an active session). This Lambda only fires
when no WhatsApp activity has been detected in 4 hours.

Fallback alerts are set for:
  - Port-out fraud detection (CRITICAL — no pre-approved SMS template exists)
  - Coordinated attack alerts (freeform-only, CRITICAL/HIGH)

SIM swap alerts are covered by the pre-approved WhatsApp template (bypasses
the 24-hour session window) and do not require SMS fallback.

Deployment:
  Lambda name:   relayshield-sms-fallback-sender
  Handler:       relayshield_sms_fallback_sender.lambda_handler
  Runtime:       Python 3.12
  Timeout:       120 s
  Memory:        128 MB
  EventBridge:   rate(4 hours)
  IAM requires:
    DynamoDB Scan + UpdateItem on relayshield_users
    Secrets Manager GetSecretValue for Twilio creds + KMS phone key
    KMS Decrypt on alias/relayshield-data-key

Test payload:
  { "dry_run": true }   — logs users with pending fallback, sends no SMS
"""

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

secrets_client = boto3.client("secretsmanager")
dynamodb       = boto3.resource("dynamodb")
kms_client     = boto3.client("kms")

USERS_TABLE         = "relayshield_users"
KMS_PHONE_KEY_ALIAS = "alias/relayshield-data-key"
TWILIO_SID_SECRET   = "relayshield/twilio_account_sid"
TWILIO_TOKEN_SECRET = "relayshield/twilio_auth_token"
TWILIO_FROM_SECRET  = "relayshield/twilio_whatsapp_number"
TWILIO_MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

FALLBACK_DELAY_HOURS = 4


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

def get_secret(secret_name: str) -> str:
    resp = secrets_client.get_secret_value(SecretId=secret_name)
    return resp["SecretString"].strip()


def get_twilio_credentials() -> tuple[str, str, str]:
    account_sid  = get_secret(TWILIO_SID_SECRET)
    auth_token   = get_secret(TWILIO_TOKEN_SECRET)
    from_raw     = get_secret(TWILIO_FROM_SECRET)
    # Strip whatsapp: prefix — SMS sends from bare E.164
    from_number  = from_raw.replace("whatsapp:", "").strip()
    return account_sid, auth_token, from_number


# ---------------------------------------------------------------------------
# Phone decryption
# ---------------------------------------------------------------------------

def decrypt_phone(ciphertext_b64: str) -> str:
    ciphertext = base64.b64decode(ciphertext_b64)
    resp = kms_client.decrypt(
        CiphertextBlob=ciphertext,
        KeyId=KMS_PHONE_KEY_ALIAS,
    )
    return resp["Plaintext"].decode("utf-8").strip()


def get_e164_phone(user: dict) -> str | None:
    if "phone_encrypted" in user:
        try:
            return decrypt_phone(user["phone_encrypted"])
        except Exception as exc:
            logger.exception("KMS decrypt failed: %s", exc)
            return None
    return user.get("whatsapp_number", "").replace("whatsapp:", "").strip() or None


# ---------------------------------------------------------------------------
# SMS send (plain SMS — no whatsapp: prefix)
# ---------------------------------------------------------------------------

def send_sms(
    to_number: str,
    body: str,
    account_sid: str,
    auth_token: str,
    from_number: str,
) -> bool:
    """Send a plain SMS via Twilio. to_number and from_number are bare E.164."""
    url         = TWILIO_MESSAGES_URL.format(account_sid=account_sid)
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()

    payload = urllib.parse.urlencode({
        "From": from_number,
        "To":   to_number,
        "Body": body,
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
            logger.info("SMS fallback sent to %s SID: %s", to_number, result.get("sid"))
            return True
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Twilio HTTP %d sending SMS to %s: %s", exc.code, to_number, error_body)
        return False
    except Exception as exc:
        logger.exception("SMS send failed to %s: %s", to_number, exc)
        return False


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def scan_pending_fallback_users() -> list[dict]:
    table    = dynamodb.Table(USERS_TABLE)
    cutoff   = (datetime.now(timezone.utc) - timedelta(hours=FALLBACK_DELAY_HOURS)).isoformat()
    results  = []
    kwargs: dict = {
        "FilterExpression": (
            Attr("active").eq(True)
            & Attr("pending_sms_fallback").exists()
            & Attr("pending_sms_fallback_at").lte(cutoff)
        )
    }
    while True:
        resp = table.scan(**kwargs)
        results.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return results


def clear_pending_fallback(user_id: str) -> None:
    dynamodb.Table(USERS_TABLE).update_item(
        Key={"user_id": user_id},
        UpdateExpression="REMOVE pending_sms_fallback, pending_sms_fallback_at",
    )


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context) -> dict:
    dry_run = bool(event.get("dry_run"))
    if dry_run:
        logger.info("DRY RUN — no SMS will be sent.")

    try:
        account_sid, auth_token, from_number = get_twilio_credentials()
    except Exception as exc:
        logger.exception("Failed to retrieve Twilio credentials: %s", exc)
        return {"statusCode": 500, "body": "Credential retrieval failed"}

    users = scan_pending_fallback_users()
    logger.info("Found %d user(s) with pending SMS fallback.", len(users))

    sent_count    = 0
    skipped_count = 0
    failed_count  = 0

    for user in users:
        user_id      = user.get("user_id", "unknown")
        alert_text   = user.get("pending_sms_fallback", "")
        fallback_at  = user.get("pending_sms_fallback_at", "")

        phone = get_e164_phone(user)
        if not phone:
            logger.warning("user_id=%s — no phone number, skipping fallback.", user_id)
            skipped_count += 1
            continue

        logger.info(
            "SMS fallback — user_id=%s phone=***%s queued_at=%s",
            user_id, phone[-4:], fallback_at,
        )

        if dry_run:
            skipped_count += 1
            continue

        success = send_sms(phone, alert_text, account_sid, auth_token, from_number)
        if success:
            try:
                clear_pending_fallback(user_id)
            except Exception as exc:
                logger.exception(
                    "Failed to clear pending_sms_fallback user_id=%s: %s", user_id, exc
                )
            sent_count += 1
        else:
            failed_count += 1

    logger.info(
        "SMS fallback complete — sent=%d skipped=%d failed=%d",
        sent_count, skipped_count, failed_count,
    )
    return {
        "statusCode": 200,
        "body": json.dumps({
            "sent": sent_count,
            "skipped": skipped_count,
            "failed": failed_count,
        }),
    }
