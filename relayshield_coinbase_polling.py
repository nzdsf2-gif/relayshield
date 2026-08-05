"""
RelayShield Coinbase Business Polling Lambda

Polls the CB Business Payment Links API every 30 minutes for new
completed payments on both Crypto Shield payment links.
Creates DynamoDB stubs with onboarding_state=AWAITING_TELEGRAM_LINK
so the Telegram bot can complete onboarding when the subscriber
sends their charge/order ID.

Triggered by: EventBridge scheduled rule — rate(30 minutes)

Auth: JWT signed with EC private key (ES256 / CB Advanced Trade format)
Secret: relayshield/coinbase_business_api
  {
    "api_key":     "organizations/.../apiKeys/...",
    "private_key": "-----BEGIN EC PRIVATE KEY-----\n...\n-----END EC PRIVATE KEY-----\n"
  }

Idempotency:
  Scans DynamoDB for existing coinbase_charge_id before creating.
  Duplicate polls covering the same window are safe.

TODO — verify on first CloudWatch log:
  - Correct API endpoint (currently /v2/payment-links/{id}/orders)
  - Correct response field names for order ID, amount, status, payer wallet
  - Adjust _extract_order_id(), detect_plan(), _extract_payer_wallet()
    if field paths differ from current assumptions.
"""

import base64
import hashlib
import json
import logging
import secrets
import time
import uuid
from datetime import datetime, timezone, timedelta

import boto3
import requests
from ecdsa import SigningKey
from ecdsa.util import sigencode_string

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
CB_API_SECRET_NAME = "relayshield/coinbase_business_api"

# Both Crypto Shield payment link IDs.
# Plan (monthly/annual) is detected from payment amount — no need to map IDs.
PAYMENT_LINK_IDS = [
    "pl_01ks419cxjfgbvftsym81s5tra",
    "pl_01ks40rz0seeybnak5jrmmv99j",
]

CB_API_BASE = "https://api.coinbase.com"

MONTHLY_DAYS = 31
ANNUAL_DAYS  = 365

# Poll window — look back 35 min each run (5-min overlap prevents gaps)
LOOKBACK_MINUTES = 35


# ---------------------------------------------------------------------------
# Secret helper
# ---------------------------------------------------------------------------

def get_cb_credentials() -> dict:
    """
    Returns {"api_key": "...", "private_key": "-----BEGIN EC PRIVATE KEY-----\n..."}
    """
    response = secrets_client.get_secret_value(SecretId=CB_API_SECRET_NAME)
    return json.loads(response["SecretString"])


# ---------------------------------------------------------------------------
# JWT auth (CB Advanced Trade / Business API — ES256)
# ---------------------------------------------------------------------------

def _b64url(data: bytes) -> str:
    """URL-safe base64 encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def build_jwt(api_key: str, private_key_pem: str, method: str, url: str) -> str:
    """
    Build a signed JWT for CB Business API authentication.
    Format: ES256 (ECDSA P-256 + SHA-256), iss=coinbase-cloud.
    Uses pure-Python ecdsa library — no compiled C extensions needed.
    """
    uri_claim = url.replace("https://", "").replace("http://", "")
    uri_claim = f"{method.upper()} {uri_claim}"

    now = int(time.time())

    header = {
        "alg":   "ES256",
        "kid":   api_key,
        "nonce": secrets.token_hex(16),
    }
    payload = {
        "sub": api_key,
        "iss": "coinbase-cloud",
        "nbf": now,
        "exp": now + 120,
        "uri": uri_claim,
    }

    header_b64  = _b64url(json.dumps(header,  separators=(",", ":")).encode())
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()

    # Load EC private key and sign — ecdsa is pure Python, no platform issues
    sk = SigningKey.from_pem(private_key_pem)
    sig = sk.sign_deterministic(
        signing_input,
        hashfunc=hashlib.sha256,
        sigencode=sigencode_string,   # raw r||s — correct format for JWT ES256
    )

    return f"{header_b64}.{payload_b64}.{_b64url(sig)}"


def cb_get(url: str, api_key: str, private_key_pem: str, params: dict = None) -> dict:
    """
    Authenticated GET against CB Business API.
    Logs full response on non-200 for debugging.
    """
    token = build_jwt(api_key, private_key_pem, "GET", url)
    resp = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
        },
        params=params,
        timeout=10,
    )

    logger.info("GET %s → %s", url, resp.status_code)

    if resp.status_code != 200:
        logger.error(
            "CB API error — status=%s body=%s",
            resp.status_code,
            resp.text[:1000],
        )
        return {}

    return resp.json()


# ---------------------------------------------------------------------------
# Plan detection
# ---------------------------------------------------------------------------

def detect_plan(order: dict) -> str:
    """
    Infer monthly vs annual from the order amount.
    Tries multiple field paths — adjust after first live CloudWatch log.
    Annual amount starts with "214".
    """
    # Try common CB API amount field paths
    amount_str = (
        str(order.get("amount", {}).get("value", "") or "")
        or str(order.get("total_price", {}).get("value", "") or "")
        or str(order.get("subtotal", {}).get("value", "") or "")
        or str(order.get("price", "") or "")
        or str(order.get("amount", "") or "")
    ).strip()

    logger.info("Plan detection — raw amount string: %r", amount_str)

    if amount_str.startswith("214"):
        return "annual"
    return "monthly"


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def charge_already_processed(charge_id: str) -> bool:
    """Idempotency guard — returns True if this charge_id already exists."""
    table = dynamodb.Table(USERS_TABLE)
    resp = table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr("coinbase_charge_id").eq(charge_id),
        ProjectionExpression="user_id",
    )
    return len(resp.get("Items", [])) > 0


def create_crypto_shield_stub(charge_id: str, plan: str, payer_wallet: str | None) -> str:
    """
    Create DynamoDB placeholder for a new Crypto Shield subscriber.
    Mirrors relayshield_coinbase_webhook.py — keep in sync.
    """
    user_id = str(uuid.uuid4())
    now     = datetime.now(timezone.utc)
    days    = ANNUAL_DAYS if plan == "annual" else MONTHLY_DAYS
    expires = (now + timedelta(days=days)).isoformat()

    item = {
        "user_id":              user_id,
        "tier":                 "crypto_shield",
        "subscription_tier":    "crypto_shield",
        "plan":                 plan,
        "delivery_channels":    ["telegram"],
        "preferred_channel":    "telegram",
        "coinbase_charge_id":   charge_id,
        "onboarding_state":     "AWAITING_TELEGRAM_LINK",
        "active":               False,
        "monitored_emails":     [],
        "wallets":              [],
        "recent_signals":       [],
        "subscription_start":   now.isoformat(),
        "subscription_expires": expires,
        "created_at":           now.isoformat(),
        "updated_at":           now.isoformat(),
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
# Order parsing helpers
# ---------------------------------------------------------------------------

def _extract_order_id(order: dict) -> str:
    """
    Extract the unique order/charge ID from a CB payment link order.
    Tries multiple field names — verify from first CloudWatch log.
    """
    return (
        order.get("id")
        or order.get("order_id")
        or order.get("charge_id")
        or order.get("code")
        or ""
    )


def _extract_payer_wallet(order: dict) -> str | None:
    """
    Extract payer crypto wallet address if present.
    Tries multiple field paths — verify from first CloudWatch log.
    """
    return (
        order.get("payer_address")
        or order.get("sender_address")
        or order.get("from_address")
        or order.get("crypto", {}).get("payer_address")
        or None
    )


def _is_completed(order: dict) -> bool:
    """
    Return True if the order represents a successful payment.
    Adjust status string if CB uses a different value.
    """
    status = str(order.get("status", "")).lower()
    logger.info("Order status: %r", status)
    return status in {"completed", "paid", "confirmed", "success", "payment_success"}


# ---------------------------------------------------------------------------
# Core poll logic
# ---------------------------------------------------------------------------

def probe_endpoints(link_id: str, api_key: str, private_key_pem: str) -> None:
    """
    Probe candidate API endpoints to find the correct path.
    Logs status + first 500 chars of response body for each.
    Call this from lambda_handler during debugging — remove once correct path confirmed.
    """
    candidates = [
        # CB Business API v2
        f"{CB_API_BASE}/v2/payment-links/{link_id}",
        f"{CB_API_BASE}/v2/payment-links/{link_id}/orders",
        f"{CB_API_BASE}/v2/payment-links",
        # CB Advanced Trade / Business API v3
        f"{CB_API_BASE}/api/v3/brokerage/payment-links/{link_id}",
        f"{CB_API_BASE}/api/v3/brokerage/payment-links/{link_id}/orders",
        f"{CB_API_BASE}/api/v3/brokerage/payment-links",
        # CB Business payments
        f"{CB_API_BASE}/api/v3/payment-links/{link_id}/orders",
    ]
    for url in candidates:
        try:
            token = build_jwt(api_key, private_key_pem, "GET", url)
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout=10,
            )
            logger.info("PROBE %s → %d | %s", url, resp.status_code, resp.text[:500])
        except Exception as exc:
            logger.error("PROBE %s → exception: %s", url, exc)


def poll_payment_link(
    link_id: str,
    api_key: str,
    private_key_pem: str,
    since: datetime,
) -> int:
    """
    Poll one payment link for orders completed since `since`.
    Returns count of new subscribers created.
    """
    url = f"{CB_API_BASE}/v2/payment-links/{link_id}/orders"
    logger.info("Polling payment link %s since %s", link_id, since.isoformat())

    data = cb_get(
        url,
        api_key,
        private_key_pem,
        params={"limit": 100},
    )

    if not data:
        logger.warning("Empty response for payment link %s — check endpoint", link_id)
        return 0

    # Log full response structure on first call to help verify field names
    logger.info("Response keys: %s", list(data.keys()))

    # CB API typically wraps results in "data" or "orders"
    orders = (
        data.get("data")
        or data.get("orders")
        or data.get("items")
        or (data if isinstance(data, list) else [])
    )

    if not orders:
        logger.info("No orders found for payment link %s", link_id)
        return 0

    logger.info("Found %d orders for payment link %s", len(orders), link_id)

    new_subscribers = 0

    for order in orders:
        # Log raw order structure on first real run to verify field names
        logger.info("Raw order sample: %s", json.dumps(order)[:500])

        if not _is_completed(order):
            continue

        # Filter by time window
        created_raw = order.get("created_at") or order.get("created_time") or ""
        if created_raw:
            try:
                created_dt = datetime.fromisoformat(
                    created_raw.replace("Z", "+00:00")
                )
                if created_dt < since:
                    continue
            except ValueError:
                pass  # Can't parse date — include it to avoid missing payments

        charge_id = _extract_order_id(order)
        if not charge_id:
            logger.warning("Order with no ID — skipping: %s", json.dumps(order)[:300])
            continue

        # Idempotency check
        try:
            if charge_already_processed(charge_id):
                logger.info("Order %s already processed — skipping", charge_id)
                continue
        except Exception as exc:
            logger.exception("Idempotency check failed for %s: %s", charge_id, exc)

        plan         = detect_plan(order)
        payer_wallet = _extract_payer_wallet(order)

        try:
            create_crypto_shield_stub(charge_id, plan, payer_wallet)
            new_subscribers += 1
        except Exception as exc:
            logger.exception(
                "Failed to create stub for order %s: %s", charge_id, exc
            )

    return new_subscribers


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """
    Entry point — invoked by EventBridge on schedule (every 30 minutes).
    Can also be invoked manually for testing.

    Manual test payload: {} (empty dict is fine)
    """
    logger.info("Coinbase polling Lambda started")

    # --- Load credentials ---
    try:
        creds = get_cb_credentials()
        api_key         = creds["api_key"]
        private_key_pem = creds["private_key"]
    except Exception as exc:
        logger.exception("Failed to load CB credentials: %s", exc)
        return {"statusCode": 500, "error": "Credential load failed"}

    # --- Time window: last 35 minutes ---
    now   = datetime.now(timezone.utc)
    since = now - timedelta(minutes=LOOKBACK_MINUTES)
    logger.info("Poll window: %s → %s", since.isoformat(), now.isoformat())

    # --- Endpoint probe (debug only — remove after correct path confirmed) ---
    logger.info("Running endpoint probe on first payment link...")
    probe_endpoints(PAYMENT_LINK_IDS[0], api_key, private_key_pem)

    # --- Poll both payment links ---
    total_new = 0
    for link_id in PAYMENT_LINK_IDS:
        try:
            count = poll_payment_link(link_id, api_key, private_key_pem, since)
            total_new += count
        except Exception as exc:
            logger.exception("Error polling payment link %s: %s", link_id, exc)

    logger.info("Poll complete — %d new subscribers created", total_new)

    return {
        "statusCode":       200,
        "new_subscribers":  total_new,
        "poll_window_start": since.isoformat(),
        "poll_window_end":   now.isoformat(),
    }
