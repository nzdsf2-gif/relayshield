"""
relayshield_weekly_status — EventBridge Lambda (every 6 days)

Sends the rs_weekly_status WhatsApp template to every active WA subscriber.
The template includes a quick-reply ACK button so users tap it, which reopens
the 24-hour messaging window and prevents Meta from passively disabling
outbound non-template messages.

Template SID: HX40e4928181216f15aeaf05ebb9e76c43
"""

import base64
import json
import logging
import urllib.parse
import urllib.request
from boto3 import resource as boto3_resource
from boto3 import client as boto3_client
from boto3.dynamodb.conditions import Attr

KMS_PHONE_KEY_ALIAS = "alias/relayshield-data-key"

logger = logging.getLogger()
logger.setLevel(logging.INFO)

USERS_TABLE = "relayshield_users"
WEEKLY_STATUS_TEMPLATE_SID = "HX40e4928181216f15aeaf05ebb9e76c43"
TWILIO_MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

TWILIO_SID_SECRET   = "relayshield/twilio_account_sid"
TWILIO_TOKEN_SECRET = "relayshield/twilio_auth_token"
TWILIO_FROM_SECRET  = "relayshield/twilio_whatsapp_number"

MONITORED_EMAILS_TABLE = "relayshield_monitored_emails"

dynamodb  = boto3_resource("dynamodb", region_name="us-east-1")
secretsm  = boto3_client("secretsmanager", region_name="us-east-1")
kms       = boto3_client("kms", region_name="us-east-1")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_secret(name: str) -> str:
    return secretsm.get_secret_value(SecretId=name)["SecretString"].strip()


def get_twilio_credentials() -> tuple[str, str, str]:
    return get_secret(TWILIO_SID_SECRET), get_secret(TWILIO_TOKEN_SECRET), get_secret(TWILIO_FROM_SECRET)


def decrypt_phone(ciphertext_b64: str) -> str:
    response = kms.decrypt(CiphertextBlob=base64.b64decode(ciphertext_b64))
    return response["Plaintext"].decode()


def get_whatsapp_number(user: dict) -> str | None:
    """Supports both KMS-encrypted phone_encrypted and legacy plaintext whatsapp_number."""
    if "phone_encrypted" in user:
        try:
            number = decrypt_phone(user["phone_encrypted"])
        except Exception as exc:
            logger.error("Failed to decrypt phone for user_id=%s: %s", user.get("user_id"), exc)
            return None
    else:
        number = user.get("whatsapp_number")
        if not number:
            logger.warning("No phone for user_id=%s — skipping", user.get("user_id"))
            return None
    return number if number.startswith("whatsapp:") else f"whatsapp:{number}"


def load_monitored_email_counts() -> dict[str, int]:
    """Scan relayshield_monitored_emails once and return {user_id: count}."""
    table = dynamodb.Table(MONITORED_EMAILS_TABLE)
    counts: dict[str, int] = {}
    kwargs: dict = {"FilterExpression": Attr("active").eq(True)}
    while True:
        resp = table.scan(**kwargs)
        for item in resp.get("Items", []):
            uid = item.get("user_id")
            if uid:
                counts[uid] = counts.get(uid, 0) + 1
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return counts


def scan_active_wa_subscribers() -> list[dict]:
    """Return all users with active=True and a whatsapp_number."""
    table = dynamodb.Table(USERS_TABLE)
    users: list[dict] = []
    filt = Attr("active").eq(True) & (Attr("whatsapp_number").exists() | Attr("phone_encrypted").exists())
    resp = table.scan(FilterExpression=filt)
    users.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(
            FilterExpression=filt,
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        users.extend(resp.get("Items", []))
    return users


def send_weekly_status(
    account_sid: str,
    auth_token: str,
    from_number: str,
    to_number: str,
    content_variables: dict,
) -> bool:
    url = TWILIO_MESSAGES_URL.format(account_sid=account_sid)
    payload = urllib.parse.urlencode({
        "From": from_number,
        "To": to_number,
        "ContentSid": WEEKLY_STATUS_TEMPLATE_SID,
        "ContentVariables": json.dumps(content_variables),
    }).encode("utf-8")
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
            logger.info("Weekly status sent to %s — Twilio SID: %s", to_number, body.get("sid"))
            return True
    except urllib.error.HTTPError as exc:
        logger.error("Twilio HTTP %d sending weekly status to %s: %s", exc.code, to_number, exc.read().decode())
        return False
    except Exception as exc:
        logger.exception("Unexpected error sending weekly status to %s: %s", to_number, exc)
        return False


def _send_security_tip(account_sid: str, auth_token: str, from_number: str, to_number: str) -> None:
    """Send a weekly security tip as a freeform follow-up after the template opens the window."""
    tip = (
        "🔐 *Weekly Security Tip — Linked Device Alerts*\n\n"
        "WhatsApp now alerts you when someone tries to link your account to a new device. "
        "If you get a linked-device alert you didn't initiate — *tap Don't Link immediately*. "
        "This is a sign someone may have stolen your phone number via SIM swap.\n\n"
        "RelayShield monitors your carrier layer for SIM swap activity. "
        "Reply *STATUS* to see your current protection status."
    )
    url = TWILIO_MESSAGES_URL.format(account_sid=account_sid)
    payload = urllib.parse.urlencode({"From": from_number, "To": to_number, "Body": tip}).encode()
    creds   = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    req     = urllib.request.Request(url, data=payload,
                headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            logger.info("Security tip sent to %s", to_number)
    except Exception as exc:
        logger.warning("Security tip failed to %s: %s", to_number, exc)


# ---------------------------------------------------------------------------
# Template variable builder — UPDATE once you have the template body from Twilio
# ---------------------------------------------------------------------------

def build_content_variables(user: dict, email_counts: dict[str, int]) -> dict:
    """
    Template body:
      🛡 RelayShield Weekly
      {{1}} email(s) monitored · {{2}} scans completed this week · No new threats detected.
      Tap below to confirm your alerts are active.

    {{1}} = monitored email count
    {{2}} = scans this week (emails × 7 daily scans)
    """
    email_count = email_counts.get(user["user_id"], 1)
    email_count = max(email_count, 1)
    scan_count  = email_count * 7
    return {
        "1": str(email_count),
        "2": str(scan_count),
    }


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    account_sid, auth_token, from_number = get_twilio_credentials()
    users        = scan_active_wa_subscribers()
    email_counts = load_monitored_email_counts()
    logger.info("Found %d active WA subscribers", len(users))

    sent = 0
    failed = 0
    for user in users:
        to_number = get_whatsapp_number(user)
        if not to_number:
            logger.warning("No WA number for user_id=%s — skipping", user.get("user_id"))
            continue
        content_vars = build_content_variables(user, email_counts)
        ok = send_weekly_status(account_sid, auth_token, from_number, to_number, content_vars)
        if ok:
            sent += 1
            # Send a security tip as freeform follow-up (window opened by template above)
            _send_security_tip(account_sid, auth_token, from_number, to_number)
        else:
            failed += 1

    logger.info("Weekly status complete — sent=%d failed=%d", sent, failed)
    return {"sent": sent, "failed": failed}
