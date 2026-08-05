"""
RelayShield Signup API Lambda
Handles the pre-signup step for Crypto Shield web onboarding.

Endpoints (via API Gateway):
  POST /signup  — user submits email; creates DynamoDB stub, returns link_code + Helio URL
  GET  /signup/status?email=...  — check onboarding state (for polling on success page)

Flow:
  1. User enters email on signup.html
  2. Browser POSTs to /signup → this Lambda
  3. Lambda creates DynamoDB stub:
       - user_id: new UUID
       - signup_email: email (lowercased)
       - link_code: new UUID (for Telegram deep link)
       - onboarding_state: AWAITING_PAYMENT
  4. Lambda returns: { link_code, helio_url, success_url }
  5. Browser stores link_code in sessionStorage, redirects user to helio_url
  6. After Helio payment: Helio webhook Lambda advances state to AWAITING_TELEGRAM_LINK
  7. Browser (on success.html) reads link_code from sessionStorage, shows QR code

Idempotency:
  If a stub already exists for this email in AWAITING_PAYMENT state (user hit back
  and resubmitted), return the existing link_code rather than creating a duplicate.
  If state is AWAITING_TELEGRAM_LINK, payment already went through — redirect to success.
"""

import json
import logging
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

dynamodb = boto3.resource("dynamodb")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USERS_TABLE = "relayshield_users"

# Helio payment link IDs — configure in Helio dashboard
# Monthly: $19.99 USDC/month | Annual: $214.99 USDC/year (10% off)
HELIO_MONTHLY_URL = "https://hel.io/pay/relayshield-crypto-monthly"
HELIO_ANNUAL_URL  = "https://hel.io/pay/relayshield-crypto-annual"

SIGNUP_BASE_URL = "https://signup.crypto.relayshield.net"

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
    "Content-Type": "application/json",
}

# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def find_stub_by_email(email: str) -> dict | None:
    """Look for an existing pre-signup stub for this email."""
    table = dynamodb.Table(USERS_TABLE)
    resp = table.scan(
        FilterExpression=(
            Attr("signup_email").eq(email)
            & Attr("onboarding_state").is_in(
                ["AWAITING_PAYMENT", "AWAITING_TELEGRAM_LINK"]
            )
        )
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def create_pre_signup_stub(email: str, plan: str) -> dict:
    """Create a stub DynamoDB record before the user pays."""
    now = datetime.now(timezone.utc)
    user_id   = str(uuid.uuid4())
    link_code = str(uuid.uuid4())

    item = {
        "user_id":            user_id,
        "signup_email":       email,
        "tier":               "crypto_shield",
        "subscription_tier":  "crypto_shield",
        "plan":               plan,
        "delivery_channels":  ["telegram"],
        "preferred_channel":  "telegram",
        "link_code":          link_code,
        "link_code_expiry":   (now + timedelta(hours=24)).isoformat(),
        "onboarding_state":   "AWAITING_PAYMENT",
        "onboarding_source":  "helio_web",
        "active":             False,
        "monitored_emails":   [],
        "wallets":            [],
        "recent_signals":     [],
        "created_at":         now.isoformat(),
        "updated_at":         now.isoformat(),
    }
    dynamodb.Table(USERS_TABLE).put_item(Item=item)
    logger.info("Pre-signup stub created — user_id=%s email=%s plan=%s", user_id, email, plan)
    return item


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

def handle_post_signup(body: dict) -> dict:
    """
    POST /signup
    Body: { "email": "user@example.com", "plan": "monthly" | "annual" }
    Returns: { "link_code": "...", "helio_url": "...", "state": "AWAITING_PAYMENT" }
    """
    email = (body.get("email") or "").lower().strip()
    plan  = body.get("plan", "monthly")

    if not email or "@" not in email:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Valid email required"}),
        }
    if plan not in ("monthly", "annual"):
        plan = "monthly"

    # Idempotency check
    existing = find_stub_by_email(email)
    if existing:
        state = existing.get("onboarding_state", "")
        link_code = existing.get("link_code", "")

        if state == "AWAITING_TELEGRAM_LINK":
            # Payment already confirmed — send them straight to success
            return {
                "statusCode": 200,
                "headers": CORS_HEADERS,
                "body": json.dumps({
                    "link_code":  link_code,
                    "helio_url":  None,
                    "state":      "AWAITING_TELEGRAM_LINK",
                    "success_url": f"{SIGNUP_BASE_URL}/success.html?link_code={link_code}",
                }),
            }

        # AWAITING_PAYMENT — reuse existing stub
        helio_url = HELIO_ANNUAL_URL if existing.get("plan") == "annual" else HELIO_MONTHLY_URL
        logger.info("Reusing existing stub for email=%s link_code=%s", email, link_code)
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({
                "link_code":   link_code,
                "helio_url":   helio_url,
                "state":       "AWAITING_PAYMENT",
                "success_url": f"{SIGNUP_BASE_URL}/success.html?link_code={link_code}",
            }),
        }

    # New signup
    stub     = create_pre_signup_stub(email, plan)
    helio_url = HELIO_ANNUAL_URL if plan == "annual" else HELIO_MONTHLY_URL

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({
            "link_code":   stub["link_code"],
            "helio_url":   helio_url,
            "state":       "AWAITING_PAYMENT",
            "success_url": f"{SIGNUP_BASE_URL}/success.html?link_code={stub['link_code']}",
        }),
    }


def handle_get_status(query_params: dict) -> dict:
    """
    GET /signup/status?email=user@example.com
    Allows the success page to poll for payment confirmation.
    Returns: { "state": "AWAITING_PAYMENT" | "AWAITING_TELEGRAM_LINK" | "ACTIVE" | "NOT_FOUND" }
    """
    email = (query_params.get("email") or "").lower().strip()
    if not email:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "email required"}),
        }

    user = find_stub_by_email(email)
    if not user:
        # Also check ACTIVE records
        table = dynamodb.Table(USERS_TABLE)
        resp = table.scan(
            FilterExpression=(
                Attr("signup_email").eq(email)
                & Attr("onboarding_state").eq("ACTIVE")
            )
        )
        items = resp.get("Items", [])
        user = items[0] if items else None

    if not user:
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"state": "NOT_FOUND"}),
        }

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({
            "state":      user.get("onboarding_state", "UNKNOWN"),
            "link_code":  user.get("link_code", ""),
        }),
    }


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context) -> dict:
    method = event.get("httpMethod", "").upper()
    path   = event.get("path", "").rstrip("/")

    # CORS preflight
    if method == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    if method == "POST" and path.endswith("/signup"):
        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return {
                "statusCode": 400,
                "headers": CORS_HEADERS,
                "body": json.dumps({"error": "Invalid JSON"}),
            }
        return handle_post_signup(body)

    if method == "GET" and "/signup/status" in path:
        query_params = event.get("queryStringParameters") or {}
        return handle_get_status(query_params)

    return {
        "statusCode": 404,
        "headers": CORS_HEADERS,
        "body": json.dumps({"error": "Not found"}),
    }
