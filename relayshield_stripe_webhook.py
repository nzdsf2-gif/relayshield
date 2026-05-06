"""
RelayShield Stripe Webhook Lambda
Handles checkout.session.completed events from Stripe.

Flow:
  1. Verify Stripe webhook signature (HMAC-SHA256, 5-minute tolerance)
  2. Extract phone number + subscription tier from session
  3. Create user record in DynamoDB (onboarding_state: AWAITING_EMAIL_1)
  4. Send first WhatsApp message via Twilio to kick off onboarding conversation

Tier detection:
  Tier is resolved by mapping session.payment_link to a tier constant via
  PAYMENT_LINK_TIER_MAP. Covers all 8 payment links (monthly + annual
  variants). Falls back to session metadata key "tier" if present.

Phone collection:
  Enable "Phone number" collection in Stripe Checkout settings, or collect
  via a custom field with key "phone_number". Both are handled.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone, timedelta

import boto3

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
scheduler_client = boto3.client("scheduler")
kms_client = boto3.client("kms")

USERS_TABLE = "relayshield_users"

# KMS key alias for field-level phone encryption
KMS_PHONE_KEY_ALIAS = "alias/relayshield-data-key"

# GSI name for phone number hash lookup
PHONE_HASH_INDEX = "phone_hash-index"

# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

STRIPE_WEBHOOK_SECRET_NAME = "relayshield/stripe_webhook_secret"
STRIPE_SECRET_KEY_NAME = "relayshield/stripe_secret_key"
TWILIO_SID_SECRET = "relayshield/twilio_account_sid"
TWILIO_TOKEN_SECRET = "relayshield/twilio_auth_token"
TWILIO_FROM_SECRET = "relayshield/twilio_whatsapp_number"
TELEGRAM_BOT_TOKEN_SECRET_NAME = "relayshield/telegram_bot_token"

TWILIO_MESSAGES_URL = (
    "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
)

# Approved Meta/Twilio WhatsApp template for new subscriber welcome message.
# Variables: {{1}} = tier display name, {{2}} = email limit (as string).
WELCOME_TEMPLATE_SID = "HX45e6bac7d790f79414f7b067e1a3edd9"

# ---------------------------------------------------------------------------
# Tier constants
# ---------------------------------------------------------------------------

TIER_PERSONAL = "personal_shield"
TIER_STARTER = "business_starter"
TIER_BASIC = "business_basic"
TIER_SHIELD = "business_shield"
TIER_PRO = "business_shield_pro"

VALID_TIERS = {TIER_PERSONAL, TIER_STARTER, TIER_BASIC, TIER_SHIELD, TIER_PRO}

TIER_DISPLAY_NAMES = {
    TIER_PERSONAL: "Personal Shield",
    TIER_STARTER: "Business Starter",
    TIER_BASIC: "Business Basic",
    TIER_SHIELD: "Business Shield",
    TIER_PRO: "Business Shield Pro",
}

# Map Stripe price IDs → tier (used for pricing table checkouts where
# payment_link is null — tier is resolved via the subscription's price ID)
PRICE_TIER_MAP = {
    "price_1THD5CL2dcjOeFiY0mmsnci8": TIER_PERSONAL,   # Personal Shield (monthly)
    "price_1TIVqYL2dcjOeFiYLr4rxapo": TIER_PERSONAL,   # Personal Shield (annual)
    "price_1TIVc6L2dcjOeFiY1QeWTh2S": TIER_BASIC,      # Business Basic (monthly)
    "price_1TIVsRL2dcjOeFiYG3iz7GcL": TIER_BASIC,      # Business Basic (annual)
    "price_1TIVjpL2dcjOeFiY0VO19g56": TIER_SHIELD,     # Business Shield (monthly)
    "price_1TIVuML2dcjOeFiY0cZ5jWOk": TIER_SHIELD,     # Business Shield (annual)
    "price_1TIVndL2dcjOeFiY4gkxfykz": TIER_PRO,        # Business Shield Pro (monthly)
    "price_1TIVwDL2dcjOeFiY93cyK3qd": TIER_PRO,        # Business Shield Pro (annual)
}

# Map Stripe payment link IDs → tier (covers both monthly and annual variants)
# These IDs appear in the session's payment_link field on checkout.session.completed
PAYMENT_LINK_TIER_MAP = {
    "plink_1THTZrL2dcjOeFiYO4RQryp6": TIER_PERSONAL,   # Personal Shield (monthly)
    "plink_1TIVqjL2dcjOeFiYT0N51SFA": TIER_PERSONAL,   # Personal Shield (annual)
    "plink_1TMA7lL2dcjOeFiYqfHQ7qkj": TIER_STARTER,    # Business Starter (monthly)
    "plink_1TMAF5L2dcjOeFiYJZJrFiEz": TIER_STARTER,    # Business Starter (annual)
    "plink_1TIVhuL2dcjOeFiYeeNFYccF": TIER_BASIC,      # Business Basic (monthly)
    "plink_1TIVsoL2dcjOeFiYvHs8YgXU": TIER_BASIC,      # Business Basic (annual)
    "plink_1TIVkIL2dcjOeFiYCB6i7g5g": TIER_SHIELD,     # Business Shield (monthly)
    "plink_1TIVuzL2dcjOeFiYvb9UDBhD": TIER_SHIELD,     # Business Shield (annual)
    "plink_1TIVo1L2dcjOeFiYi2IDD2az": TIER_PRO,        # Business Shield Pro (monthly)
    "plink_1TIVwiL2dcjOeFiYMdy7fWfu": TIER_PRO,        # Business Shield Pro (annual)
}

# Max emails per subscriber (personal) or per employee (business)
EMAIL_LIMITS = {
    TIER_PERSONAL: 3,
    TIER_STARTER: 3,
    TIER_BASIC: 2,
    TIER_SHIELD: 2,
    TIER_PRO: 2,
}

# Stripe signature tolerance — reject webhooks older than this
SIGNATURE_TOLERANCE_SECONDS = 300  # 5 minutes

# ---------------------------------------------------------------------------
# Day 3 follow-up scheduler config (set as Lambda environment variables)
# ---------------------------------------------------------------------------

# ARN of the relayshield-day3-sender Lambda
DAY3_LAMBDA_ARN = os.environ.get("DAY3_LAMBDA_ARN", "")

# ARN of the IAM role allowing EventBridge Scheduler to invoke the Day 3 Lambda
# Trust policy: scheduler.amazonaws.com
# Permission: lambda:InvokeFunction on DAY3_LAMBDA_ARN
DAY3_SCHEDULER_ROLE_ARN = os.environ.get("DAY3_SCHEDULER_ROLE_ARN", "")


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
# Stripe API helper (for pricing table tier resolution)
# ---------------------------------------------------------------------------

def get_price_id_from_subscription(subscription_id: str, stripe_secret_key: str) -> str | None:
    """
    Call the Stripe API to retrieve a subscription and extract the price ID.
    Used when checkout came via pricing table (no payment_link field).
    """
    url = f"https://api.stripe.com/v1/subscriptions/{subscription_id}"
    credentials = base64.b64encode(f"{stripe_secret_key}:".encode()).decode()
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Basic {credentials}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            items = data.get("items", {}).get("data", [])
            if items:
                price_id = items[0].get("price", {}).get("id")
                logger.info("Retrieved price_id=%s from subscription=%s", price_id, subscription_id)
                return price_id
    except Exception as exc:
        logger.exception("Failed to retrieve subscription %s from Stripe: %s", subscription_id, exc)
    return None


# ---------------------------------------------------------------------------
# Stripe signature verification
# ---------------------------------------------------------------------------

def verify_stripe_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    """
    Verify the Stripe-Signature header using HMAC-SHA256.
    Format: t=<timestamp>,v1=<signature>[,v1=<signature>...]
    Rejects requests older than SIGNATURE_TOLERANCE_SECONDS.
    """
    try:
        timestamp = None
        v1_sigs: list[str] = []

        for part in sig_header.split(","):
            k, _, v = part.strip().partition("=")
            if k == "t":
                timestamp = v
            elif k == "v1":
                v1_sigs.append(v)

        if not timestamp or not v1_sigs:
            logger.warning("Missing timestamp or v1 signature in Stripe-Signature header.")
            return False

        age = abs(time.time() - int(timestamp))
        if age > SIGNATURE_TOLERANCE_SECONDS:
            logger.warning(
                "Stripe webhook timestamp %ds old — exceeds %ds tolerance. "
                "Possible replay attack.",
                int(age), SIGNATURE_TOLERANCE_SECONDS,
            )
            return False

        signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
        expected = hmac.new(
            secret.encode("utf-8"),
            signed_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return any(hmac.compare_digest(expected, sig) for sig in v1_sigs)

    except Exception as exc:
        logger.exception("Stripe signature verification error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Phone number helpers
# ---------------------------------------------------------------------------

def normalise_phone(phone: str) -> str | None:
    """
    Normalise to E.164 format (+XXXXXXXXXXX).
    Stripe collects phone in E.164 — strip spaces/dashes/parentheses.
    Returns None if the result looks invalid.
    """
    if not phone:
        return None
    cleaned = "".join(c for c in phone if c.isdigit() or c == "+")
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    # E.164 minimum length: country code (1-3) + subscriber (min 4) = 7 digits
    if len(cleaned) < 8:
        logger.warning("Phone number too short after normalisation: %s", cleaned)
        return None
    return cleaned


def to_whatsapp_number(phone: str) -> str:
    """Prefix E.164 number with whatsapp: for Twilio (idempotent)."""
    if phone.startswith("whatsapp:"):
        return phone
    return f"whatsapp:{phone}"


# ---------------------------------------------------------------------------
# KMS phone encryption helpers
# ---------------------------------------------------------------------------

def hash_phone(phone: str) -> str:
    """SHA-256 of normalised E.164 phone — deterministic GSI lookup key."""
    normalised = phone.strip().replace("whatsapp:", "")
    return hashlib.sha256(normalised.encode()).hexdigest()


def encrypt_phone(phone: str) -> str:
    """Encrypt normalised E.164 phone via KMS. Returns base64-encoded ciphertext."""
    normalised = phone.strip().replace("whatsapp:", "")
    response = kms_client.encrypt(
        KeyId=KMS_PHONE_KEY_ALIAS,
        Plaintext=normalised.encode(),
    )
    return base64.b64encode(response["CiphertextBlob"]).decode()


# ---------------------------------------------------------------------------
# DynamoDB
# ---------------------------------------------------------------------------

def user_exists_for_phone(phone_number: str) -> bool:
    """
    Check if a user record already exists for this phone number.
    Prevents duplicate onboarding if Stripe fires the webhook twice.
    Primary path: GSI query on phone_hash (encrypted records).
    Fallback: scan on plaintext phone_number (pre-migration records).
    """
    table = dynamodb.Table(USERS_TABLE)
    ph = hash_phone(phone_number)

    # Primary: GSI lookup on phone_hash
    response = table.query(
        IndexName=PHONE_HASH_INDEX,
        KeyConditionExpression=boto3.dynamodb.conditions.Key("phone_hash").eq(ph),
        Select="COUNT",
    )
    if response.get("Count", 0) > 0:
        return True

    # Fallback: scan for legacy plaintext records (pre-migration)
    response = table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr("phone_number").eq(phone_number),
        ProjectionExpression="user_id",
    )
    return len(response.get("Items", [])) > 0


def create_user_record(
    phone_number: str,
    subscription_tier: str,
    stripe_customer_id: str,
    stripe_subscription_id: str,
) -> str:
    """
    Create a new user record in relayshield_users.
    Sets onboarding_state to AWAITING_EMAIL_1.
    Returns the new user_id.
    """
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    table = dynamodb.Table(USERS_TABLE)
    table.put_item(Item={
        "user_id": user_id,
        "phone_encrypted": encrypt_phone(phone_number),
        "phone_hash": hash_phone(phone_number),
        "subscription_tier": subscription_tier,
        "stripe_customer_id": stripe_customer_id,
        "stripe_subscription_id": stripe_subscription_id,
        "onboarding_state": "AWAITING_EMAIL_1",
        "emails_added": 0,
        "password_manager_user": False,
        "sim_swap_monitoring": True,
        "active": True,
        "created_at": now,
        "updated_at": now,
    })

    logger.info(
        "User record created — user_id=%s tier=%s (phone encrypted)",
        user_id, subscription_tier,
    )
    return user_id


# ---------------------------------------------------------------------------
# Twilio WhatsApp
# ---------------------------------------------------------------------------

def send_whatsapp(
    to_number: str,
    body: str,
    account_sid: str,
    auth_token: str,
    from_number: str,
) -> bool:
    """Send a WhatsApp message via Twilio REST API. Returns True on success."""
    url = TWILIO_MESSAGES_URL.format(account_sid=account_sid)
    credentials = base64.b64encode(
        f"{account_sid}:{auth_token}".encode()
    ).decode()

    payload = urllib.parse.urlencode({
        "From": to_whatsapp_number(from_number),
        "To": to_whatsapp_number(to_number),
        "Body": body,
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
                "WhatsApp sent to %s — SID: %s status: %s",
                to_number, result.get("sid"), result.get("status"),
            )
            return True
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Twilio HTTP %d sending to %s: %s", exc.code, to_number, error_body)
        return False
    except Exception as exc:
        logger.exception("Twilio send failed for %s: %s", to_number, exc)
        return False


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
    Uses ContentSid + ContentVariables instead of Body — required for
    business-initiated messages outside the 24-hour messaging window.
    variables must be a dict of string keys matching template placeholders,
    e.g. {"1": "Personal Shield", "2": "3"}.
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
                "WhatsApp template %s sent to %s — SID: %s status: %s",
                template_sid, to_number, result.get("sid"), result.get("status"),
            )
            return True
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error(
            "Twilio template HTTP %d sending to %s: %s", exc.code, to_number, error_body
        )
        return False
    except Exception as exc:
        logger.exception("Twilio template send failed for %s: %s", to_number, exc)
        return False


# ---------------------------------------------------------------------------
# Day 3 follow-up scheduler
# ---------------------------------------------------------------------------

def schedule_day3_followup(user_id: str, subscription_tier: str) -> None:
    """
    Create a one-time EventBridge Scheduler rule to fire the Day 3 follow-up
    Lambda exactly 72 hours from now. The schedule self-deletes after firing
    (ActionAfterCompletion=DELETE).

    Silently skipped if DAY3_LAMBDA_ARN or DAY3_SCHEDULER_ROLE_ARN are not
    configured — prevents blocking onboarding during initial deployment before
    the Day 3 Lambda exists.
    """
    if not DAY3_LAMBDA_ARN or not DAY3_SCHEDULER_ROLE_ARN:
        logger.warning(
            "DAY3_LAMBDA_ARN or DAY3_SCHEDULER_ROLE_ARN not set — "
            "skipping Day 3 schedule for user_id=%s.", user_id,
        )
        return

    fire_time = (
        datetime.now(timezone.utc) + timedelta(hours=72)
    ).strftime("%Y-%m-%dT%H:%M:%S")

    # EventBridge Scheduler names: alphanumeric + hyphens, max 64 chars.
    # UUID is 36 chars; prefix is 17 chars → 53 chars total, within limit.
    schedule_name = f"relayshield-day3-{user_id}"

    try:
        scheduler_client.create_schedule(
            Name=schedule_name,
            ScheduleExpression=f"at({fire_time})",
            ScheduleExpressionTimezone="UTC",
            FlexibleTimeWindow={"Mode": "OFF"},
            Target={
                "Arn": DAY3_LAMBDA_ARN,
                "RoleArn": DAY3_SCHEDULER_ROLE_ARN,
                "Input": json.dumps({
                    "user_id": user_id,
                    "tier": subscription_tier,
                }),
            },
            ActionAfterCompletion="DELETE",
        )
        logger.info(
            "Day 3 follow-up scheduled — user_id=%s fires at %s UTC",
            user_id, fire_time,
        )
    except Exception as exc:
        # Non-fatal: log and continue — onboarding must not fail over this
        logger.exception(
            "Failed to schedule Day 3 follow-up for user_id=%s: %s", user_id, exc
        )


# ---------------------------------------------------------------------------
# Telegram helpers (Telegram-first payment flow)
# ---------------------------------------------------------------------------

def get_pre_payment_record(telegram_chat_id: str) -> dict | None:
    """
    Find a pre-payment DynamoDB record by Telegram chat_id.
    Created by the Telegram webhook when user taps 'Choose this plan'.
    """
    table = dynamodb.Table(USERS_TABLE)
    resp = table.scan(
        FilterExpression=(
            boto3.dynamodb.conditions.Attr("telegram_chat_id").eq(telegram_chat_id)
            & boto3.dynamodb.conditions.Attr("onboarding_state").eq("AWAITING_PAYMENT")
        )
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def advance_telegram_record(
    user_id: str,
    stripe_customer_id: str,
    stripe_subscription_id: str,
    subscription_tier: str,
) -> None:
    """Advance pre-payment record to AWAITING_PHONE after confirmed Stripe payment."""
    table = dynamodb.Table(USERS_TABLE)
    now = datetime.now(timezone.utc).isoformat()
    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression=(
            "SET onboarding_state = :state, "
            "stripe_customer_id = :cid, "
            "stripe_subscription_id = :sid, "
            "subscription_tier = :tier, "
            "#act = :active, "
            "updated_at = :now"
        ),
        ExpressionAttributeNames={"#act": "active"},
        ExpressionAttributeValues={
            ":state": "AWAITING_PHONE",
            ":cid": stripe_customer_id,
            ":sid": stripe_subscription_id,
            ":tier": subscription_tier,
            ":active": True,
            ":now": now,
        },
    )
    logger.info(
        "Telegram record advanced to AWAITING_PHONE — user_id=%s tier=%s",
        user_id, subscription_tier,
    )


def send_telegram_phone_request(chat_id: str, token: str, tier_name: str) -> bool:
    """
    Send payment confirmation + request_contact keyboard to Telegram user.
    Called immediately after Stripe payment is confirmed.
    """
    text = (
        f"✅ *Payment confirmed! Welcome to RelayShield — {tier_name} is now active.*\n\n"
        f"Let's finish setting up your protection.\n\n"
        f"Tap the button below to share your phone number — "
        f"I'll use it to monitor for SIM/eSIM swap attacks."
    )
    keyboard = {
        "keyboard": [[{
            "text": "📱 Share my phone number",
            "request_contact": True,
        }]],
        "one_time_keyboard": True,
        "resize_keyboard": True,
    }
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": keyboard,
    }).encode()

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                logger.info("Telegram phone request sent to chat_id=%s", chat_id)
                return True
            logger.error("Telegram API error for chat_id=%s: %s", chat_id, result)
            return False
    except Exception as exc:
        logger.exception("Failed to send Telegram message to chat_id=%s: %s", chat_id, exc)
        return False


# ---------------------------------------------------------------------------
# Welcome message
# ---------------------------------------------------------------------------

def build_welcome_message(subscription_tier: str) -> str:
    """
    First message sent immediately after payment is confirmed.
    Kicks off the onboarding conversation in WhatsApp.
    """
    tier_name = TIER_DISPLAY_NAMES.get(subscription_tier, "RelayShield")
    email_limit = EMAIL_LIMITS.get(subscription_tier, 3)

    if subscription_tier == TIER_PERSONAL:
        limit_context = f"up to {email_limit} email addresses"
    else:
        limit_context = (
            f"up to {email_limit} email addresses per team member — "
            f"your business address plus one additional"
        )

    return (
        f"🛡️ *Welcome to RelayShield — {tier_name} is now active.*\n\n"
        f"I'm your AI security assistant. I monitor your credentials around the clock, "
        f"alert you here the moment anything is found, and walk you through every fix "
        f"— step by step, no jargon.\n\n"
        f"To get started: what's the first email address you'd like me to monitor? "
        f"You can add {limit_context}."
    )


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """
    Entry point for API Gateway → Lambda invocation.

    API Gateway passes:
      event["body"]            — raw request body (string, may be base64)
      event["headers"]         — HTTP headers dict
      event["isBase64Encoded"] — True if body is base64-encoded
    """
    # --- Decode raw body (needed for signature verification) ---
    raw_body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw_body_bytes = base64.b64decode(raw_body)
    else:
        raw_body_bytes = raw_body.encode("utf-8")

    # Normalise headers to lowercase keys
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    sig_header = headers.get("stripe-signature", "")

    # --- TEST MODE BYPASS (Lambda console testing only) ---
    # Remove this block before going to production with real traffic.
    # Only bypasses signature check when X-Test-Mode: true header is present.
    test_mode = headers.get("x-test-mode", "").lower() == "true"
    if test_mode:
        logger.warning("TEST MODE ACTIVE — Stripe signature verification bypassed.")
    else:
        if not sig_header:
            logger.warning("Request missing Stripe-Signature header.")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing Stripe-Signature header"}),
            }

        # --- 1. Retrieve webhook secret ---
        try:
            webhook_secret = get_secret(STRIPE_WEBHOOK_SECRET_NAME)
        except Exception as exc:
            logger.exception("Failed to retrieve Stripe webhook secret: %s", exc)
            return {
                "statusCode": 500,
                "body": json.dumps({"error": "Secret retrieval failed"}),
            }

        # --- 2. Verify Stripe signature ---
        if not verify_stripe_signature(raw_body_bytes, sig_header, webhook_secret):
            logger.warning("Stripe signature verification failed — request rejected.")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Invalid Stripe signature"}),
            }

    # --- 3. Parse Stripe event ---
    try:
        stripe_event = json.loads(raw_body_bytes)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Stripe event body: %s", exc)
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid JSON body"}),
        }

    event_type = stripe_event.get("type", "")
    logger.info("Received Stripe event type: %s", event_type)

    # Only act on checkout completion — acknowledge all others silently
    # (Stripe requires a 2xx response for all webhook deliveries)
    if event_type != "checkout.session.completed":
        return {
            "statusCode": 200,
            "body": json.dumps({"message": f"Event type '{event_type}' acknowledged, not processed"}),
        }

    session = stripe_event.get("data", {}).get("object", {})
    session_id = session.get("id", "unknown")
    logger.info("Processing checkout.session.completed — session_id=%s", session_id)

    stripe_customer_id = session.get("customer") or ""
    stripe_subscription_id = session.get("subscription") or ""

    # --- 4. Telegram-first flow (client_reference_id = telegram chat_id) ---
    # Check this BEFORE phone extraction — Telegram users have no phone in session
    client_ref = session.get("client_reference_id", "")
    if client_ref:
        logger.info("Telegram payment flow detected — client_reference_id=%s", client_ref)
        pre_payment = get_pre_payment_record(client_ref)

        if not pre_payment:
            logger.error(
                "No pre-payment record found for telegram_chat_id=%s session=%s",
                client_ref, session_id,
            )
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "error": "No pre-payment Telegram record found",
                    "telegram_chat_id": client_ref,
                }),
            }

        user_id = pre_payment["user_id"]

        # Idempotency: skip if already advanced
        if pre_payment.get("onboarding_state") != "AWAITING_PAYMENT":
            logger.warning(
                "Telegram record user_id=%s already at state=%s — skipping duplicate webhook",
                user_id, pre_payment.get("onboarding_state"),
            )
            return {"statusCode": 200, "body": json.dumps({"message": "Already processed"})}

        # Use tier from pre-payment record (set when user selected plan in bot)
        resolved_tier = pre_payment.get("subscription_tier") or subscription_tier

        # Advance record to AWAITING_PHONE
        advance_telegram_record(user_id, stripe_customer_id, stripe_subscription_id, resolved_tier)

        # Schedule Day 3 follow-up
        schedule_day3_followup(user_id, resolved_tier)

        # Send phone request via Telegram
        try:
            bot_token = get_secret_json(TELEGRAM_BOT_TOKEN_SECRET_NAME, "telegram_bot_token")
        except Exception as exc:
            logger.exception("Failed to retrieve Telegram bot token: %s", exc)
            return {"statusCode": 500, "body": json.dumps({"error": "Token retrieval failed"})}

        tier_name = TIER_DISPLAY_NAMES.get(resolved_tier, "RelayShield")
        tg_sent = send_telegram_phone_request(client_ref, bot_token, tier_name)

        logger.info(
            "Telegram onboarding triggered — user_id=%s tier=%s telegram_sent=%s",
            user_id, resolved_tier, tg_sent,
        )
        return {
            "statusCode": 200,
            "body": json.dumps({
                "user_id": user_id,
                "subscription_tier": resolved_tier,
                "onboarding_state": "AWAITING_PHONE",
                "channel": "telegram",
                "telegram_sent": tg_sent,
            }),
        }

    # --- 5. WhatsApp flow — extract phone number from Stripe session ---
    # Primary: Stripe built-in phone collection → customer_details.phone
    # Fallback: custom_fields with key "phone_number"
    phone: str | None = None
    customer_details = session.get("customer_details") or {}
    phone = customer_details.get("phone")

    if not phone:
        for field in session.get("custom_fields") or []:
            if field.get("key") in ("phone_number", "whatsapp_number", "phone"):
                phone = (field.get("text") or {}).get("value")
                if phone:
                    break

    phone = normalise_phone(phone) if phone else None

    if not phone:
        logger.error(
            "No valid phone number found in session %s — cannot initiate onboarding.",
            session_id,
        )
        return {
            "statusCode": 200,
            "body": json.dumps({
                "error": "No phone number in session",
                "session_id": session_id,
                "action": "Manual onboarding required",
            }),
        }

    # --- 6. Extract subscription tier (three methods, in priority order) ---
    subscription_tier = None

    # Method 1: payment_link field (standard Payment Link checkout)
    payment_link_id = session.get("payment_link")
    if payment_link_id:
        subscription_tier = PAYMENT_LINK_TIER_MAP.get(payment_link_id)
        logger.info("Resolved tier '%s' from payment_link=%s", subscription_tier, payment_link_id)

    # Method 2: session metadata (manual override)
    if not subscription_tier:
        metadata = session.get("metadata") or {}
        tier_meta = metadata.get("tier", "").lower().strip().replace(" ", "_")
        if tier_meta in VALID_TIERS:
            subscription_tier = tier_meta
            logger.info("Resolved tier '%s' from session metadata", subscription_tier)

    # Method 3: pricing table checkout — fetch subscription from Stripe API to get price ID
    if not subscription_tier:
        subscription_id = session.get("subscription")
        if subscription_id:
            try:
                stripe_secret_key = get_secret(STRIPE_SECRET_KEY_NAME)
                price_id = get_price_id_from_subscription(subscription_id, stripe_secret_key)
                if price_id:
                    subscription_tier = PRICE_TIER_MAP.get(price_id)
                    logger.info(
                        "Resolved tier '%s' from subscription=%s price=%s",
                        subscription_tier, subscription_id, price_id,
                    )
            except Exception as exc:
                logger.exception("Failed to resolve tier via subscription API: %s", exc)

    if not subscription_tier:
        logger.error(
            "Could not determine tier for session %s — "
            "payment_link=%s, no metadata, subscription lookup failed.",
            session_id, payment_link_id,
        )
        return {
            "statusCode": 200,
            "body": json.dumps({
                "error": "Could not determine subscription tier",
                "session_id": session_id,
                "payment_link": payment_link_id,
            }),
        }

    # --- 7. Idempotency check — prevent duplicate onboarding ---
    try:
        if user_exists_for_phone(phone):
            logger.warning(
                "User with phone %s already exists — skipping duplicate onboarding "
                "for session %s.", phone, session_id,
            )
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": "User already exists for this phone number",
                    "phone": phone,
                }),
            }
    except Exception as exc:
        logger.exception("Idempotency check failed: %s", exc)
        # Non-fatal — proceed with creation (safer than blocking a real subscriber)

    # --- 9. Create user record ---
    try:
        user_id = create_user_record(
            phone_number=phone,
            subscription_tier=subscription_tier,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
        )
    except Exception as exc:
        logger.exception("Failed to create user record for phone %s: %s", phone, exc)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "DynamoDB write failed"}),
        }

    # --- 10. Schedule Day 3 follow-up (72 hrs from now, self-deleting) ---
    schedule_day3_followup(user_id, subscription_tier)

    # --- 11. Retrieve Twilio credentials ---
    try:
        account_sid, auth_token, from_number = get_twilio_credentials()
    except Exception as exc:
        logger.exception("Failed to retrieve Twilio credentials: %s", exc)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Twilio credentials retrieval failed"}),
        }

    # --- 10. Send welcome WhatsApp message via approved Meta template ---
    # Template send works outside the 24-hour window (business-initiated).
    # Falls back to free-form send if template delivery fails.
    tier_name = TIER_DISPLAY_NAMES.get(subscription_tier, "RelayShield")
    email_limit = EMAIL_LIMITS.get(subscription_tier, 3)

    sent = send_whatsapp_template(
        to_number=phone,
        template_sid=WELCOME_TEMPLATE_SID,
        variables={"1": tier_name, "2": str(email_limit)},
        account_sid=account_sid,
        auth_token=auth_token,
        from_number=from_number,
    )

    if not sent:
        logger.warning(
            "Template send failed for %s (user_id=%s) — attempting free-form fallback.",
            phone, user_id,
        )
        welcome_msg = build_welcome_message(subscription_tier)
        sent = send_whatsapp(
            to_number=phone,
            body=welcome_msg,
            account_sid=account_sid,
            auth_token=auth_token,
            from_number=from_number,
        )

    if not sent:
        logger.error(
            "Failed to send welcome WhatsApp to %s (user_id=%s). "
            "User record created — manual WhatsApp outreach required.",
            phone, user_id,
        )

    logger.info(
        "Onboarding complete — user_id=%s tier=%s phone=%s whatsapp_sent=%s",
        user_id, subscription_tier, phone, sent,
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "user_id": user_id,
            "subscription_tier": subscription_tier,
            "onboarding_state": "AWAITING_EMAIL_1",
            "whatsapp_sent": sent,
        }),
    }
