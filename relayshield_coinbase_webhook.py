"""
RelayShield Coinbase Business Webhook Lambda

Handles payment_link.payment.success events from Coinbase Business
Payment Link APIs (CDP) Webhooks Beta.

Registration (one-time via CDP CLI):
  cdp data webhooks subscriptions create \\
    description="Payment link status webhook" \\
    'eventTypes:=["payment_link.payment.success","payment_link.payment.failed"]' \\
    target.url=https://<api-gw-id>.execute-api.us-east-1.amazonaws.com/prod/coinbase-webhook \\
    target.method=POST \\
    'labels:={}' \\
    isEnabled:=true
  → Save metadata.secret from 201 response → Secrets Manager as
    "relayshield/coinbase_webhook_secret"

Flow:
  1. Verify X-CC-Webhook-Signature HMAC-SHA256 against webhook secret
     (header name TBC — verify from first live test payload in CloudWatch)
  2. On payment_link.payment.success:
     - Determine plan (monthly $19.99 vs annual $214.99) from payment amount
     - Extract payer wallet address where available
     - Create DynamoDB stub: tier=crypto_shield, onboarding_state=AWAITING_TELEGRAM_LINK
     - Store coinbase_charge_id so Telegram bot can match the subscriber
  3. Telegram bot completes onboarding when user sends /start <charge_code>
     or types their charge code directly into the bot.

DynamoDB record created:
  user_id              — new UUID
  tier                 — "crypto_shield"
  subscription_tier    — "crypto_shield"
  plan                 — "monthly" | "annual"
  delivery_channels    — ["telegram"]
  preferred_channel    — "telegram"
  coinbase_charge_id   — Coinbase charge code / payment ID
  onboarding_state     — "AWAITING_TELEGRAM_LINK"
  payer_wallet         — payer wallet address if present in payload
  wallets              — [] (filled during Telegram onboarding)
  monitored_emails     — [] (filled during Telegram onboarding)
  active               — False (set True when Telegram chat_id linked)
  subscription_start   — ISO timestamp
  subscription_expires — ISO timestamp (+31d monthly, +365d annual)
  created_at / updated_at

Idempotency:
  Scans for existing record with coinbase_charge_id before creating.
  Duplicate events (CB retries) are silently acknowledged.

Webhook secret:
  Stored in Secrets Manager as "relayshield/coinbase_webhook_secret".
  Value is metadata.secret from the CDP CLI subscription create response.

TODO — verify from first live CloudWatch log:
  - Exact signature header name (X-CC-Webhook-Signature or CB-Signature or similar)
  - Exact payload structure: event type field path, charge ID field path,
    payment amount field path, payer wallet field path
  - Update _extract_charge_id(), detect_plan(), and payer wallet extraction
    if field paths differ from current assumptions.
"""

import base64
import hashlib
import hmac
import json
import logging
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USERS_TABLE = "relayshield_users"
CB_WEBHOOK_SECRET_NAME = "relayshield/coinbase_webhook_secret"

# Recognised plan amounts (USD)
PLAN_MONTHLY_AMOUNT_USD = "19.99"
PLAN_ANNUAL_AMOUNT_USD  = "214.99"

MONTHLY_DAYS = 31
ANNUAL_DAYS  = 365


# ---------------------------------------------------------------------------
# Secret helper
# ---------------------------------------------------------------------------

def get_secret(secret_name: str) -> str:
    response = secrets_client.get_secret_value(SecretId=secret_name)
    return response["SecretString"].strip()


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------

def verify_coinbase_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    """
    Verify Coinbase Business HMAC-SHA256 webhook signature.
    Header: X-CC-Webhook-Signature (verify exact name from first live CloudWatch log)
    Expected: HMAC-SHA256(shared_secret, raw_body).hexdigest()
    Secret: metadata.secret from CDP CLI subscription create response.
    """
    try:
        expected = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, sig_header.strip())
    except Exception as exc:
        logger.exception("Coinbase signature verification error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def charge_already_processed(charge_id: str) -> bool:
    """
    Check if a record for this charge_id already exists (idempotency guard).
    CB Payment Links retries unacknowledged webhooks — prevent duplicate subscriber creation.
    """
    table = dynamodb.Table(USERS_TABLE)
    resp = table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr("coinbase_charge_id").eq(charge_id),
        ProjectionExpression="user_id",
    )
    return len(resp.get("Items", [])) > 0


def create_crypto_shield_stub(
    charge_id: str,
    plan: str,
    payer_wallet: str | None,
) -> str:
    """
    Create a DynamoDB placeholder record for a new Crypto Shield subscriber.
    onboarding_state=AWAITING_TELEGRAM_LINK — Telegram bot advances this after
    the subscriber sends their charge code and completes the onboarding conversation.

    Returns the new user_id.
    """
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    days = ANNUAL_DAYS if plan == "annual" else MONTHLY_DAYS
    expires_at = (now + timedelta(days=days)).isoformat()

    item = {
        "user_id":            user_id,
        "tier":               "crypto_shield",
        "subscription_tier":  "crypto_shield",
        "plan":               plan,
        "delivery_channels":  ["telegram"],
        "preferred_channel":  "telegram",
        "coinbase_charge_id": charge_id,
        "onboarding_state":   "AWAITING_TELEGRAM_LINK",
        "active":             False,
        "monitored_emails":   [],
        "wallets":            [],
        "recent_signals":     [],
        "subscription_start": now.isoformat(),
        "subscription_expires": expires_at,
        "created_at":         now.isoformat(),
        "updated_at":         now.isoformat(),
    }

    if payer_wallet:
        item["payer_wallet"] = payer_wallet

    dynamodb.Table(USERS_TABLE).put_item(Item=item)

    logger.info(
        "Crypto Shield stub created — user_id=%s charge_id=%s plan=%s payer_wallet=%s",
        user_id, charge_id, plan, payer_wallet,
    )
    return user_id


# ---------------------------------------------------------------------------
# Plan detection helper
# ---------------------------------------------------------------------------

def detect_plan_from_charge(charge: dict) -> str:
    """
    Infer monthly vs annual plan from the CB Payment Links payment amount.
    CB Payment Links payload shape (verify from CloudWatch on first live hit):
      charge.pricing.local.amount  — e.g. "19.99" or "214.99"
      charge.amount                — fallback
      charge.value                 — fallback

    Annual amount starts with "214" — safe prefix match.
    Falls back to "monthly" if amount cannot be determined.
    """
    # Try nested pricing.local.amount first (CB Commerce-style)
    pricing = charge.get("pricing", {})
    local = pricing.get("local", {})
    amount_str = str(local.get("amount", "")).strip()

    # Fallback paths for CB Payment Links
    if not amount_str or amount_str == "None":
        amount_str = str(charge.get("amount", "")).strip()
    if not amount_str or amount_str == "None":
        amount_str = str(charge.get("value", "")).strip()

    logger.info("Plan detection — raw amount string: %r", amount_str)

    if amount_str.startswith("214"):
        return "annual"

    return "monthly"


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """
    Entry point — API Gateway Lambda proxy integration.

    API Gateway passes:
      event["body"]            — raw request body (string, may be base64)
      event["headers"]         — HTTP headers dict (keys may be mixed case)
      event["isBase64Encoded"] — True if body was base64-encoded by API GW
    """
    # --- Decode raw body ---
    raw_body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw_body_bytes = base64.b64decode(raw_body)
    else:
        raw_body_bytes = raw_body.encode("utf-8")

    # --- Normalise headers to lowercase ---
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    sig_header = headers.get("x-cc-webhook-signature", "")

    if not sig_header:
        logger.warning("Missing X-CC-Webhook-Signature header — rejecting request")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing X-CC-Webhook-Signature header"}),
        }

    # --- 1. Retrieve webhook secret ---
    try:
        webhook_secret = get_secret(CB_WEBHOOK_SECRET_NAME)
    except Exception as exc:
        logger.exception("Failed to retrieve Coinbase webhook secret: %s", exc)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Secret retrieval failed"}),
        }

    # --- 2. Verify signature ---
    if not verify_coinbase_signature(raw_body_bytes, sig_header, webhook_secret):
        logger.warning("Coinbase signature verification failed — request rejected")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid signature"}),
        }

    # --- 3. Parse event body ---
    try:
        cb_payload = json.loads(raw_body_bytes)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse Coinbase event body: %s", exc)
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid JSON body"}),
        }

    # CB Payment Link APIs payload shape (verified from CDP docs):
    # { "type": "payment_link.payment.success", "data": { ... } }
    # Top-level "type" field (not nested under "event")
    event_type = cb_payload.get("type", "")
    if not event_type:
        # Fallback: some CB webhook implementations nest under "event"
        event_data = cb_payload.get("event", {})
        event_type = event_data.get("type", "")
    logger.info("Received Coinbase event type: %s", event_type)

    # --- 4. Only act on payment_link.payment.success; acknowledge everything else ---
    if event_type != "payment_link.payment.success":
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": f"Event '{event_type}' acknowledged, not processed",
            }),
        }

    # Payment data — CB Payment Link APIs uses top-level "data" object
    charge = cb_payload.get("data", {})

    # Charge/payment ID — CB Payment Links may use "id", "paymentId", or "code"
    # TODO: verify exact field name from first live CloudWatch log
    charge_id = (
        charge.get("id")
        or charge.get("paymentId")
        or charge.get("code")
        or ""
    )
    charge_id = str(charge_id).upper().strip()

    if not charge_id:
        logger.error("No charge code found in event data — cannot create subscriber record")
        return {
            "statusCode": 200,
            "body": json.dumps({"error": "No charge code in event"}),
        }

    logger.info("Processing charge:confirmed — charge_id=%s", charge_id)

    # --- 5. Idempotency — skip if already processed ---
    try:
        if charge_already_processed(charge_id):
            logger.info("Charge %s already processed — acknowledging duplicate", charge_id)
            return {
                "statusCode": 200,
                "body": json.dumps({"message": "Already processed", "charge_id": charge_id}),
            }
    except Exception as exc:
        logger.exception("Idempotency check failed for charge %s: %s", charge_id, exc)
        # Non-fatal — proceed (safer than blocking a real subscriber)

    # --- 6. Determine plan from payment amount ---
    plan = detect_plan_from_charge(charge)
    logger.info("Plan detected: %s (charge_id=%s)", plan, charge_id)

    # --- 7. Extract payer wallet address ---
    # CB Payment Links payload — try multiple possible field paths.
    # TODO: verify exact path from first live CloudWatch log.
    payer_wallet = (
        charge.get("payer_address")
        or charge.get("senderAddress")
        or charge.get("from_address")
    )
    # Fallback: Commerce-style payments array
    if not payer_wallet:
        payments = charge.get("payments", [])
        if payments:
            payer_addresses = payments[0].get("payer_addresses", [])
            if payer_addresses:
                payer_wallet = payer_addresses[0]
    logger.info("Payer wallet: %s", payer_wallet or "not available")

    # --- 8. Create subscriber stub in DynamoDB ---
    try:
        user_id = create_crypto_shield_stub(charge_id, plan, payer_wallet)
    except Exception as exc:
        logger.exception(
            "Failed to create Crypto Shield stub for charge %s: %s", charge_id, exc
        )
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "DynamoDB write failed"}),
        }

    logger.info(
        "Crypto Shield onboarding ready — user_id=%s charge_id=%s plan=%s",
        user_id, charge_id, plan,
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "user_id":      user_id,
            "charge_id":    charge_id,
            "plan":         plan,
            "payer_wallet": payer_wallet,
            "status":       "AWAITING_TELEGRAM_LINK",
        }),
    }
