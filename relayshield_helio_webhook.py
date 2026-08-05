"""
RelayShield Helio Webhook Lambda
Receives payment lifecycle events from Helio (USDC on Base — Crypto Shield).

Helio calls this endpoint at POST /helio-webhook with an X-Signature header.
Signature is HMAC-SHA256(shared_webhook_secret, raw_body) — hex-encoded.

Event flow:
  STARTED  → subscriber paid; set onboarding_state=AWAITING_TELEGRAM_LINK,
             send SES QR-code email so user can link their Telegram account.
  RENEWED  → existing subscriber renewed; extend subscription_expires.
  ENDED    → subscription cancelled / payment lapsed; deactivate.
  CREATED  → payment initiated (pre-confirmation); no state change.

DynamoDB record is pre-created by the signup Lambda (relayshield_signup_api)
at the point the user enters their email. The Helio webhook finds that record
by email and advances its state.

If no pre-created stub exists (edge case: user skipped the signup page and
paid directly via a Helio link), a new active record is created on the spot.
"""

import hashlib
import hmac
import json
import logging
import urllib.parse  # noqa: F401 — used in send_onboarding_email
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

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
ses_client = boto3.client("ses", region_name="us-east-1")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USERS_TABLE = "relayshield_users"
SECRET_NAME_HELIO = "relayshield/helio_webhook_secret"
SECRET_NAME_TELEGRAM = "relayshield/telegram_bot_token"
SES_SENDER = "RelayShield <noreply@relayshield.net>"
SIGNUP_BASE_URL = "https://signup.crypto.relayshield.net"
TELEGRAM_DEEP_LINK_BASE = "https://t.me/RelayShield_bot?start="

# Subscription lengths
PLAN_DAYS = {"monthly": 31, "annual": 365}

# ---------------------------------------------------------------------------
# Secret cache
# ---------------------------------------------------------------------------

_secret_cache: dict = {}


def _get_secret(name: str) -> str:
    if name not in _secret_cache:
        resp = secrets_client.get_secret_value(SecretId=name)
        _secret_cache[name] = resp["SecretString"]
    return _secret_cache[name]


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------

def verify_signature(raw_body: bytes, signature_header: str) -> bool:
    """
    Helio signs the raw request body with HMAC-SHA256 using the shared
    webhook secret configured in the Helio dashboard.
    """
    try:
        secret = _get_secret(SECRET_NAME_HELIO)
        expected = hmac.new(
            secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature_header.lower())
    except Exception as exc:
        logger.error("Signature verification error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def find_user_by_email(email: str) -> dict | None:
    """Scan for a user record matching email (case-insensitive)."""
    table = dynamodb.Table(USERS_TABLE)
    resp = table.scan(
        FilterExpression=Attr("signup_email").eq(email.lower().strip())
    )
    items = resp.get("Items", [])
    if items:
        # Prefer AWAITING_PAYMENT or AWAITING_TELEGRAM_LINK records
        for item in items:
            if item.get("onboarding_state") in (
                "AWAITING_PAYMENT", "AWAITING_TELEGRAM_LINK"
            ):
                return item
        return items[0]
    return None


def update_user(user_id: str, updates: dict) -> None:
    table = dynamodb.Table(USERS_TABLE)
    expr_parts, names, values = [], {}, {}
    for k, v in updates.items():
        safe = f"#f{len(names)}"
        names[safe] = k
        values[f":v{len(values)}"] = v
        expr_parts.append(f"{safe} = :v{len(values) - 1}")
    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET " + ", ".join(expr_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def create_stub_record(email: str, plan: str, helio_tx_id: str) -> dict:
    """
    Fallback: create an active record on-the-spot for a Helio payment
    where no pre-signup stub exists.
    """
    now = datetime.now(timezone.utc)
    days = PLAN_DAYS.get(plan, 31)
    link_code = str(uuid.uuid4())
    user_id = str(uuid.uuid4())

    item = {
        "user_id": user_id,
        "signup_email": email.lower().strip(),
        "tier": "crypto_shield",
        "subscription_tier": "crypto_shield",
        "plan": plan,
        "delivery_channels": ["telegram"],
        "preferred_channel": "telegram",
        "link_code": link_code,
        "link_code_expiry": (now + timedelta(hours=24)).isoformat(),
        "helio_transaction_id": helio_tx_id,
        "onboarding_state": "AWAITING_TELEGRAM_LINK",
        "onboarding_source": "helio_direct",
        "active": False,
        "monitored_emails": [],
        "wallets": [],
        "recent_signals": [],
        "subscription_start": now.isoformat(),
        "subscription_expires": (now + timedelta(days=days)).isoformat(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    dynamodb.Table(USERS_TABLE).put_item(Item=item)
    logger.info("Helio direct stub created — user_id=%s email=%s", user_id, email)
    return item


# ---------------------------------------------------------------------------
# SES: send QR-code onboarding email
# ---------------------------------------------------------------------------

def send_onboarding_email(email: str, link_code: str, first_name: str) -> None:
    """
    Send the Telegram link QR code to the subscriber's email as a backup.
    The QR code encodes the Telegram deep link.
    The email includes both a clickable link and instructions to scan the QR.
    We generate the QR as an image URL pointing to a server-side endpoint
    or use a third-party QR URL (quickchart.io — no account needed).
    """
    deep_link = f"{TELEGRAM_DEEP_LINK_BASE}{link_code}"
    qr_url = (
        f"https://quickchart.io/qr?text={urllib.parse.quote(deep_link, safe='')}"
        f"&size=300&margin=2"
    )
    success_url = f"{SIGNUP_BASE_URL}/success.html?link_code={link_code}"

    name_part = f"Hi {first_name}," if first_name else "Hi there,"

    html = f"""
    <html>
    <body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;color:#1a1a2e;">
      <img src="https://relayshield.net/assets/logo.png" alt="RelayShield" width="180" style="margin-bottom:24px;">
      <h2 style="color:#2563eb;">Welcome to Crypto Shield 🛡️</h2>
      <p>{name_part}</p>
      <p>Your payment was confirmed. One last step — link your Telegram account to activate 24/7 monitoring.</p>

      <h3>Option 1 — Scan the QR code (on desktop)</h3>
      <p>Open your phone camera, point it at the code below, and tap the link:</p>
      <img src="{qr_url}" alt="Telegram QR code" width="240" style="display:block;margin:16px 0;border:1px solid #e5e7eb;border-radius:8px;padding:8px;">

      <h3>Option 2 — Tap the link (on mobile)</h3>
      <p><a href="{deep_link}" style="display:inline-block;background:#2563eb;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold;">Open RelayShield in Telegram →</a></p>

      <p style="margin-top:24px;">Or visit your <a href="{success_url}">activation page</a> to get your QR code again.</p>

      <hr style="border:none;border-top:1px solid #e5e7eb;margin:32px 0;">
      <p style="color:#6b7280;font-size:12px;">This link expires in 24 hours. If it expires, contact support@relayshield.net.<br>
      © 2026 RelayShield · <a href="https://relayshield.net" style="color:#6b7280;">relayshield.net</a></p>
    </body>
    </html>
    """

    text = (
        f"{name_part}\n\n"
        f"Your Crypto Shield payment was confirmed.\n\n"
        f"Link your Telegram account to activate monitoring:\n{deep_link}\n\n"
        f"Or visit: {success_url}\n\n"
        f"This link expires in 24 hours."
    )

    try:
        ses_client.send_email(
            Source=SES_SENDER,
            Destination={"ToAddresses": [email]},
            Message={
                "Subject": {"Data": "🛡️ Activate your Crypto Shield — link Telegram now"},
                "Body": {
                    "Html": {"Data": html},
                    "Text": {"Data": text},
                },
            },
        )
        logger.info("Onboarding SES email sent to %s", email)
    except Exception as exc:
        logger.error("SES send failed for %s: %s", email, exc)


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------

def _extract_payload(body: dict) -> tuple[str, str, str, str]:
    """
    Extract (email, first_name, plan, helio_tx_id) from the Helio payload.
    Returns empty strings for missing fields.
    """
    tx_obj = body.get("transactionObject", {})
    meta = tx_obj.get("meta", {})
    customer = meta.get("customerDetails", {})
    email = (customer.get("email") or "").lower().strip()
    first_name = (customer.get("fullName") or "").split()[0] if customer.get("fullName") else ""
    helio_tx_id = body.get("transaction") or tx_obj.get("id", "")

    # Determine plan from USDC amount (6 decimals: 1 USDC = 1_000_000)
    # Monthly = $19.99 → 19_990_000 | Annual = $214.99 → 214_990_000
    # Use $100 as threshold — anything above that is the annual plan
    amount_raw = int(meta.get("amount", 0) or 0)
    plan = "annual" if amount_raw >= 100_000_000 else "monthly"

    return email, first_name, plan, helio_tx_id


def handle_started(body: dict) -> None:
    """New subscription started — activate record and send onboarding email."""
    email, first_name, plan, helio_tx_id = _extract_payload(body)
    if not email:
        logger.warning("STARTED event missing email — skipping")
        return

    now = datetime.now(timezone.utc)
    days = PLAN_DAYS.get(plan, 31)

    user = find_user_by_email(email)
    if user:
        link_code = user.get("link_code") or str(uuid.uuid4())
        updates = {
            "tier": "crypto_shield",
            "subscription_tier": "crypto_shield",
            "plan": plan,
            "helio_transaction_id": helio_tx_id,
            "onboarding_state": "AWAITING_TELEGRAM_LINK",
            "link_code": link_code,
            "link_code_expiry": (now + timedelta(hours=24)).isoformat(),
            "subscription_start": now.isoformat(),
            "subscription_expires": (now + timedelta(days=days)).isoformat(),
            "updated_at": now.isoformat(),
        }
        update_user(user["user_id"], updates)
        logger.info("Helio STARTED — advanced existing record user_id=%s", user["user_id"])
    else:
        user = create_stub_record(email, plan, helio_tx_id)
        link_code = user["link_code"]
        logger.info("Helio STARTED — no stub found, created direct record for %s", email)

    send_onboarding_email(email, link_code, first_name)


def handle_renewed(body: dict) -> None:
    """Subscription renewed — extend subscription_expires."""
    email, _, plan, helio_tx_id = _extract_payload(body)
    if not email:
        return

    now = datetime.now(timezone.utc)
    days = PLAN_DAYS.get(plan, 31)

    user = find_user_by_email(email)
    if not user:
        logger.warning("RENEWED event — no record found for email %s", email)
        return

    # Extend from current expiry if still in the future, else extend from now
    current_expiry_str = user.get("subscription_expires", "")
    try:
        current_expiry = datetime.fromisoformat(current_expiry_str)
        base = max(current_expiry, now)
    except (ValueError, TypeError):
        base = now

    update_user(user["user_id"], {
        "subscription_expires": (base + timedelta(days=days)).isoformat(),
        "helio_transaction_id": helio_tx_id,
        "active": True,
        "updated_at": now.isoformat(),
    })
    logger.info("Helio RENEWED — extended subscription for user_id=%s", user["user_id"])


def handle_ended(body: dict) -> None:
    """Subscription ended — deactivate the record."""
    email, _, _, _ = _extract_payload(body)
    if not email:
        return

    user = find_user_by_email(email)
    if not user:
        logger.warning("ENDED event — no record found for email %s", email)
        return

    now = datetime.now(timezone.utc)
    update_user(user["user_id"], {
        "active": False,
        "onboarding_state": "CANCELLED",
        "updated_at": now.isoformat(),
    })
    logger.info("Helio ENDED — deactivated user_id=%s", user["user_id"])

    # Optionally send a cancellation message via Telegram if linked
    chat_id = user.get("telegram_chat_id")
    if chat_id:
        _send_telegram_cancellation(chat_id)


def _send_telegram_cancellation(chat_id: str) -> None:
    """Notify the subscriber on Telegram that their subscription ended."""
    try:
        token = _get_secret(SECRET_NAME_TELEGRAM)
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({
            "chat_id": chat_id,
            "text": (
                "⚠️ *Crypto Shield subscription ended*\n\n"
                "Your protection has been paused. Renew at any time:\n"
                "👉 https://relayshield.net\n\n"
                "Questions? Contact support@relayshield.net"
            ),
            "parse_mode": "Markdown",
        }).encode()
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception as exc:
        logger.error("Telegram cancellation notify failed chat_id=%s: %s", chat_id, exc)


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context) -> dict:
    # API Gateway passes raw body as string
    raw_body_str = event.get("body") or ""
    raw_body = raw_body_str.encode("utf-8")

    # Signature check
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    sig_header = headers.get("x-signature", "")

    if not sig_header:
        logger.warning("Helio webhook missing X-Signature header")
        return {"statusCode": 401, "body": "Missing signature"}

    if not verify_signature(raw_body, sig_header):
        logger.warning("Helio webhook signature mismatch")
        return {"statusCode": 403, "body": "Invalid signature"}

    try:
        body = json.loads(raw_body_str)
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": "Invalid JSON"}

    event_type = (body.get("event") or "").upper()
    logger.info("Helio webhook event=%s", event_type)

    if event_type == "STARTED":
        handle_started(body)
    elif event_type == "RENEWED":
        handle_renewed(body)
    elif event_type == "ENDED":
        handle_ended(body)
    elif event_type == "CREATED":
        logger.info("Helio CREATED event received — no action needed")
    else:
        logger.warning("Unknown Helio event type: %s", event_type)

    return {"statusCode": 200, "body": "OK"}
