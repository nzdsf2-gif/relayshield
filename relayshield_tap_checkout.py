"""
RelayShield TAP Verifier Checkout Lambda

Creates Stripe Checkout Sessions for the TAP Verifier PAYG tier.

Why this exists:
  Stripe Payment Links do not support usage-based (metered) pricing, so the
  $0.10/verification PAYG tier cannot use a payment link. This Lambda creates
  a Checkout Session via the Stripe API, which does support metered prices.

Endpoint:
  POST /v1/tap/checkout

Request body (JSON):
  {
    "email": "buyer@example.com",      # required
    "name": "Jane Buyer",              # optional
    "success_url": "https://...",      # optional, defaults to developers page
    "cancel_url": "https://..."        # optional, defaults to developers page
  }

Response (200):
  {
    "checkout_url": "https://checkout.stripe.com/c/pay/...",
    "session_id": "cs_test_..."
  }

The metered price is resolved from the TAP Verifier PAYG product
(prod_VPQSzLW8w1whVy) at runtime, or from the TAP_PAYG_PRICE_ID env var
when set. The Stripe secret key comes from Secrets Manager
(relayshield/stripe_secret_key).

Nothing here provisions API entitlements. After checkout completes, the
existing Stripe webhook (relayshield_stripe_webhook.py) fires on
checkout.session.completed; entitlement provisioning for TAP is a
separate step.
"""

import base64
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

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

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

STRIPE_SECRET_KEY_NAME = "relayshield/stripe_secret_key"
TAP_PAYG_PRODUCT_ID = "prod_VPQSzLW8w1whVy"
STRIPE_API_BASE = "https://api.stripe.com/v1"

DEFAULT_SUCCESS_URL = "https://api.relayshield.net/developers?tap=subscribed"
DEFAULT_CANCEL_URL = "https://api.relayshield.net/developers#tap-verifier"

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
    "Content-Type": "application/json",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_stripe_secret_key() -> str:
    response = secrets_client.get_secret_value(SecretId=STRIPE_SECRET_KEY_NAME)
    return response["SecretString"].strip()


def stripe_request(method: str, path: str, secret_key: str, data: dict | None = None) -> dict:
    """Call the Stripe API with raw urllib (repo pattern: no Stripe SDK)."""
    url = f"{STRIPE_API_BASE}{path}"
    credentials = base64.b64encode(f"{secret_key}:".encode()).decode()
    headers = {"Authorization": f"Basic {credentials}"}
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data, doseq=True).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def resolve_payg_price_id(secret_key: str) -> str:
    """Return the metered price ID for the TAP Verifier PAYG product."""
    env_price = os.environ.get("TAP_PAYG_PRICE_ID", "").strip()
    if env_price:
        return env_price
    data = stripe_request(
        "GET",
        f"/prices?product={TAP_PAYG_PRODUCT_ID}&active=true&limit=10",
        secret_key,
    )
    for price in data.get("data", []):
        if price.get("recurring", {}).get("usage_type") == "metered":
            price_id = price.get("id", "")
            logger.info("Resolved metered PAYG price_id=%s", price_id)
            return price_id
    # Fall back to the first active price if none is explicitly metered.
    prices = data.get("data", [])
    if prices:
        price_id = prices[0].get("id", "")
        logger.warning("No metered price found; using first active price_id=%s", price_id)
        return price_id
    raise RuntimeError(f"No active prices found for product {TAP_PAYG_PRODUCT_ID}")


def create_checkout_session(secret_key: str, price_id: str, email: str,
                            name: str, success_url: str, cancel_url: str) -> dict:
    """Create a Stripe Checkout Session in subscription mode for metered billing."""
    payload = {
        "mode": "subscription",
        "customer_email": email,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items[0][price]": price_id,
        "metadata[tier]": "tap_verifier_payg",
        "metadata[product]": "tap_verifier",
    }
    if name:
        payload["metadata[customer_name]"] = name
    return stripe_request("POST", "/checkout/sessions", secret_key, payload)


def respond(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": CORS_HEADERS,
        "body": json.dumps(body),
    }


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """
    API Gateway proxy integration.

    Handles OPTIONS preflight for CORS and POST to create the session.
    """
    method = (event.get("httpMethod") or "").upper()
    if method == "OPTIONS":
        return respond(200, {})

    if method != "POST":
        return respond(405, {"error": "Method not allowed. Use POST."})

    raw_body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw_body = base64.b64decode(raw_body).decode("utf-8")

    try:
        payload = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        return respond(400, {"error": "Request body must be valid JSON."})

    email = (payload.get("email") or "").strip()
    if not email or "@" not in email:
        return respond(400, {"error": "A valid email address is required."})

    name = (payload.get("name") or "").strip()
    success_url = (payload.get("success_url") or "").strip() or DEFAULT_SUCCESS_URL
    cancel_url = (payload.get("cancel_url") or "").strip() or DEFAULT_CANCEL_URL

    try:
        secret_key = get_stripe_secret_key()
        price_id = resolve_payg_price_id(secret_key)
        session = create_checkout_session(
            secret_key, price_id, email, name, success_url, cancel_url
        )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        logger.exception("Stripe API error creating checkout session: %s", detail)
        return respond(502, {"error": "Payment provider error. Please try again."})
    except Exception:
        logger.exception("Failed to create TAP PAYG checkout session")
        return respond(500, {"error": "Could not create checkout session. Please try again."})

    checkout_url = session.get("url") or ""
    session_id = session.get("id") or ""
    if not checkout_url:
        logger.error("Stripe session missing url: %s", json.dumps(session)[:500])
        return respond(502, {"error": "Payment provider error. Please try again."})

    logger.info("Created TAP PAYG checkout session=%s for email hash", session_id)
    return respond(200, {"checkout_url": checkout_url, "session_id": session_id})
