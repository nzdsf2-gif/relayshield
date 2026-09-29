#!/usr/bin/env python3
"""Stripe Checkout + metered-billing wiring for the scam-kit subscription tiers.

Why this module exists: Stripe Payment Links cannot carry metered prices (the
API demands a quantity on every line item), so the flat $199 payment link can
never sell the metered tiers. The replacement is a per-customer Checkout
Session created server-side, which supports metered prices with no quantity.

Flow:
  1. An authenticated developer calls POST /v1/billing/checkout-session with
     {"tier": "monthly"|"payg"}. The Lambda creates a Stripe Checkout Session
     in subscription mode (client_reference_id = the caller's RS API key)
     and returns its URL. The developer completes checkout in the browser.
  2. Stripe calls POST /v1/billing/webhook with checkout.session.completed.
     The webhook signature is verified, then the key record in
     relayshield_api_keys is updated with stripe_customer_id,
     stripe_subscription_id and scamkit_tier. On
     customer.subscription.deleted the tier is cleared again.
  3. Every later scam-kit execution on /v1/metered/scamkit-* reads the
     caller's key record (already fetched for auth), resolves the tier, and
     posts one billing meter event with the tier's event name and value=1.
     The scam-kit meters aggregate with formula=count, so value is always 1.

The x402 /v1/payg/ rail is untouched: per-call on-chain billing never goes
near this code.

Stripe objects (created 2026-09-28; verified read-only — DO NOT recreate):
  Monthly product prod_VLPP4OIMyYwEvE
    base    price_1UKibSL2dcjOeFiYTxYTaBUk  $199.00/mo (licensed)
    overage price_1UKicEL2dcjOeFiY7Lnxu4yU  500 included, then $0.40/unit
            meter mtr_61VU6Mgfd5aoGppB941L2dcjOeFiYKQC, event scamkit_monthly_execution
  PAYG product prod_VLPSTaRIACxi2l
    fingerprint price_1UKifPL2dcjOeFiYJP2LiFdP  $0.50
            meter mtr_61VU6bwXPb4poDsxz41L2dcjOeFiYVOq, event scamkit_payg_fingerprint
    match       price_1UKifOL2dcjOeFiYF6ZsLZbi  $0.10
            meter mtr_61VU6bwXPb4poDsxz41L2dcjOeFiYPYW, event scamkit_payg_match
    campaign    price_1UKifRL2dcjOeFiYv5Rj0D97  $5.50
            meter mtr_61VU6c7lipQBPZ9Q441L2dcjOeFiY6EC, event scamkit_payg_campaign

Secrets (AWS Secrets Manager, same convention as relayshield_api.py):
  relayshield/stripe_secret_key            — Stripe secret key (already exists)
  relayshield/stripe_billing_webhook_secret — signing secret for the
      /v1/billing/webhook endpoint, copied from the Stripe dashboard when the
      webhook endpoint is registered. MUST be created before the webhook can
      verify anything; until then every webhook call returns 500 and Stripe
      retries.

Design rules:
  * Pure functions stay pure (no network, no AWS) so they are unit-testable.
  * Anything that touches the network or DynamoDB takes its client/secret as
    an argument or via a lazy getter — never at import time — so importing
    this module never needs AWS credentials.
  * Meter-event reporting is fire-and-forget and never raises: a Stripe blip
    must not fail an already-completed scam-kit execution.
"""

import base64
import hashlib
import hmac
import json
import logging
import time
import urllib.parse
import urllib.request
import uuid

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Tiers, prices, meters — verified read-only against the Stripe API 2026-09-28
# ---------------------------------------------------------------------------

TIER_MONTHLY = "monthly"
TIER_PAYG = "payg"
VALID_TIERS = (TIER_MONTHLY, TIER_PAYG)

# Monthly: $199/mo base (licensed) + overage (metered, 500 included / $0.40).
PRICE_MONTHLY_BASE = "price_1UKibSL2dcjOeFiYTxYTaBUk"
PRICE_MONTHLY_OVERAGE = "price_1UKicEL2dcjOeFiY7Lnxu4yU"

# PAYG: three metered prices, no base.
PRICE_PAYG_FINGERPRINT = "price_1UKifPL2dcjOeFiYJP2LiFdP"
PRICE_PAYG_MATCH = "price_1UKifOL2dcjOeFiYF6ZsLZbi"
PRICE_PAYG_CAMPAIGN = "price_1UKifRL2dcjOeFiYv5Rj0D97"

# Meter event names. The meters aggregate with formula=count, so every event
# posts value=1 — the per-unit price on each metered price does the rest.
EVENT_MONTHLY_EXECUTION = "scamkit_monthly_execution"
EVENT_PAYG_FINGERPRINT = "scamkit_payg_fingerprint"
EVENT_PAYG_MATCH = "scamkit_payg_match"
EVENT_PAYG_CAMPAIGN = "scamkit_payg_campaign"

# Metered request path -> (monthly event, payg event).
SCAMKIT_METERED_PATHS: dict[str, tuple[str, str]] = {
    "/v1/metered/scamkit-fingerprint":   (EVENT_MONTHLY_EXECUTION, EVENT_PAYG_FINGERPRINT),
    "/v1/metered/scamkit-match":         (EVENT_MONTHLY_EXECUTION, EVENT_PAYG_MATCH),
    "/v1/metered/scamkit-campaign-scan": (EVENT_MONTHLY_EXECUTION, EVENT_PAYG_CAMPAIGN),
}

API_KEYS_TABLE = "relayshield_api_keys"

STRIPE_API_BASE = "https://api.stripe.com"
STRIPE_VERSION = "2024-06-20"

# Webhook signature tolerance — same 5 minutes as relayshield_stripe_webhook.py.
SIGNATURE_TOLERANCE_SECONDS = 300

DEFAULT_SUCCESS_URL = "https://api.relayshield.net/developers?billing=success&session_id={CHECKOUT_SESSION_ID}"
DEFAULT_CANCEL_URL = "https://api.relayshield.net/developers?billing=cancelled"


# ---------------------------------------------------------------------------
# Pure: checkout session construction
# ---------------------------------------------------------------------------

def checkout_line_items(tier: str) -> list[dict]:
    """Line-item specs for a tier. Metered items carry NO quantity — Stripe
    rejects quantity on metered prices, which is exactly why Payment Links
    cannot sell these tiers."""
    if tier == TIER_MONTHLY:
        return [
            {"price": PRICE_MONTHLY_BASE, "quantity": 1},
            {"price": PRICE_MONTHLY_OVERAGE},
        ]
    if tier == TIER_PAYG:
        return [
            {"price": PRICE_PAYG_FINGERPRINT},
            {"price": PRICE_PAYG_MATCH},
            {"price": PRICE_PAYG_CAMPAIGN},
        ]
    raise ValueError(f"unknown tier: {tier!r}")


def build_checkout_session_params(
    tier: str,
    client_reference_id: str,
    success_url: str = DEFAULT_SUCCESS_URL,
    cancel_url: str = DEFAULT_CANCEL_URL,
) -> dict:
    """Form params for POST /v1/checkout/sessions.

    client_reference_id is the caller's RS API key: it is what the webhook
    uses to map the Stripe customer back to the RelayShield key record.
    subscription_data[metadata] carries api_key + tier so that
    customer.subscription.deleted can clear the tier even though the
    session object is long gone by then.
    """
    if tier not in VALID_TIERS:
        raise ValueError(f"unknown tier: {tier!r}")
    if not client_reference_id or len(client_reference_id) > 200:
        raise ValueError("client_reference_id must be 1-200 chars (Stripe limit)")
    params: dict[str, str] = {
        "mode": "subscription",
        "client_reference_id": client_reference_id,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata[tier]": tier,
        "subscription_data[metadata][api_key]": client_reference_id,
        "subscription_data[metadata][tier]": tier,
    }
    for i, item in enumerate(checkout_line_items(tier)):
        params[f"line_items[{i}][price]"] = item["price"]
        if "quantity" in item:
            params[f"line_items[{i}][quantity]"] = str(item["quantity"])
    return params


def create_checkout_session(
    secret_key: str,
    tier: str,
    client_reference_id: str,
    success_url: str = DEFAULT_SUCCESS_URL,
    cancel_url: str = DEFAULT_CANCEL_URL,
) -> dict:
    """Create the Stripe Checkout Session. Returns {"id", "url"}.

    Raises on Stripe/API errors — the caller converts to a 4xx/5xx response.
    Creates no customer up front: Checkout collects email and creates the
    customer itself.
    """
    params = build_checkout_session_params(
        tier, client_reference_id, success_url, cancel_url
    )
    req = urllib.request.Request(
        f"{STRIPE_API_BASE}/v1/checkout/sessions",
        data=urllib.parse.urlencode(params).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Stripe-Version": STRIPE_VERSION,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        session = json.loads(resp.read().decode("utf-8"))
    if not session.get("url"):
        raise RuntimeError("Stripe returned a session with no checkout URL")
    logger.info("checkout session created tier=%s session=%s", tier, session.get("id"))
    return {"id": session["id"], "url": session["url"]}


# ---------------------------------------------------------------------------
# Pure: webhook signature verification (same algorithm as
# relayshield_stripe_webhook.verify_stripe_signature)
# ---------------------------------------------------------------------------

def verify_stripe_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    """Verify the Stripe-Signature header (t=<ts>,v1=<sig>[,v1=<sig>...]).

    Rejects missing/expired signatures. Pure — no network, no AWS.
    """
    try:
        timestamp = None
        v1_sigs: list[str] = []
        for part in (sig_header or "").split(","):
            k, _, v = part.strip().partition("=")
            if k == "t":
                timestamp = v
            elif k == "v1":
                v1_sigs.append(v)
        if not timestamp or not v1_sigs or not secret:
            return False
        if abs(time.time() - int(timestamp)) > SIGNATURE_TOLERANCE_SECONDS:
            logger.warning("billing webhook signature %ds old — rejecting",
                           int(abs(time.time() - int(timestamp))))
            return False
        signed = f"{timestamp}.{payload.decode('utf-8')}"
        expected = hmac.new(secret.encode("utf-8"), signed.encode("utf-8"),
                            hashlib.sha256).hexdigest()
        return any(hmac.compare_digest(expected, s) for s in v1_sigs)
    except Exception as exc:
        logger.warning("billing webhook signature check error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Pure: webhook event parsing
# ---------------------------------------------------------------------------

def extract_subscription_mapping(session: dict) -> dict | None:
    """Pull the RelayShield key mapping out of a checkout.session.completed
    session object. Returns None when the session is not one of ours (no
    client_reference_id or no tier metadata)."""
    api_key = session.get("client_reference_id") or ""
    metadata = session.get("metadata") or {}
    tier = metadata.get("tier") or ""
    customer_id = session.get("customer") or ""
    subscription_id = session.get("subscription") or ""
    if not api_key or tier not in VALID_TIERS or not customer_id:
        return None
    return {
        "api_key": api_key,
        "stripe_customer_id": customer_id,
        "stripe_subscription_id": subscription_id,
        "scamkit_tier": tier,
    }


def extract_deleted_mapping(subscription: dict) -> str | None:
    """API key whose tier must be cleared, from a customer.subscription.deleted
    subscription object. The api_key was stored in subscription metadata at
    checkout-session creation."""
    metadata = subscription.get("metadata") or {}
    return metadata.get("api_key") or None


def dispatch_billing_event(event: dict) -> tuple[str, dict | str | None]:
    """Classify a parsed Stripe event. Returns (action, payload) where action
    is "activate" (payload=mapping dict), "deactivate" (payload=api_key str),
    or "ignore" (payload=None). Pure — the caller does the DynamoDB write."""
    event_type = event.get("type") or ""
    obj = (event.get("data") or {}).get("object") or {}
    if event_type == "checkout.session.completed":
        mapping = extract_subscription_mapping(obj)
        return ("activate", mapping) if mapping else ("ignore", None)
    if event_type == "customer.subscription.deleted":
        api_key = extract_deleted_mapping(obj)
        return ("deactivate", api_key) if api_key else ("ignore", None)
    return ("ignore", None)


# ---------------------------------------------------------------------------
# DynamoDB persistence (table is injectable for tests)
# ---------------------------------------------------------------------------

_dynamodb = None


def _dynamodb_resource():
    global _dynamodb
    if _dynamodb is None:
        import boto3
        _dynamodb = boto3.resource("dynamodb")
    return _dynamodb


def api_keys_table(table=None):
    """The relayshield_api_keys table. Pass a fake in tests."""
    if table is not None:
        return table
    return _dynamodb_resource().Table(API_KEYS_TABLE)


def store_subscription_mapping(table, mapping: dict) -> None:
    """Activate a scam-kit tier on the caller's key record. Idempotent — a
    retried webhook writes the same values."""
    table.update_item(
        Key={"api_key": mapping["api_key"]},
        UpdateExpression=(
            "SET stripe_customer_id = :cus, "
            "stripe_subscription_id = :sub, "
            "scamkit_tier = :tier, "
            "scamkit_subscribed_at = :now"
        ),
        ExpressionAttributeValues={
            ":cus": mapping["stripe_customer_id"],
            ":sub": mapping.get("stripe_subscription_id") or "",
            ":tier": mapping["scamkit_tier"],
            ":now": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    )
    logger.info("scamkit tier activated api_key=%s tier=%s customer=%s",
                mapping["api_key"][:16], mapping["scamkit_tier"],
                mapping["stripe_customer_id"])


def clear_subscription_tier(table, api_key: str) -> None:
    """Deactivate: remove the tier (and subscription id) so the key stops
    passing the subscription gate. stripe_customer_id is kept for history
    and cancellation lookups."""
    table.update_item(
        Key={"api_key": api_key},
        UpdateExpression="REMOVE scamkit_tier, stripe_subscription_id",
    )
    logger.info("scamkit tier cleared api_key=%s", api_key[:16])


# ---------------------------------------------------------------------------
# Pure: meter event resolution + payload
# ---------------------------------------------------------------------------

def scamkit_meter_event_for(tier: str, path: str) -> str | None:
    """Resolve the Stripe meter event name for a tier + endpoint. None when
    the path is not a scam-kit metered endpoint (caller must not report)."""
    events = SCAMKIT_METERED_PATHS.get(path)
    if not events:
        return None
    return events[0] if tier == TIER_MONTHLY else events[1] if tier == TIER_PAYG else None


def build_meter_event_payload(stripe_customer_id: str, event_name: str,
                              value: int = 1) -> dict:
    """Form params for POST /v1/billing/meter_events. value is always 1:
    the scam-kit meters aggregate with formula=count."""
    return {
        "event_name": event_name,
        "payload[stripe_customer_id]": stripe_customer_id,
        "payload[value]": str(value),
        "identifier": f"{stripe_customer_id}-{uuid.uuid4().hex}",
    }


def report_scamkit_meter_event(secret_key: str, stripe_customer_id: str,
                               event_name: str, value: int = 1) -> None:
    """Post one usage event to the tier's Stripe meter. Fire-and-forget —
    never raises, so a Stripe blip cannot fail a completed execution."""
    if not stripe_customer_id or not event_name:
        logger.warning("skipping meter event — missing customer (%s) or event",
                       bool(stripe_customer_id))
        return
    try:
        req = urllib.request.Request(
            f"{STRIPE_API_BASE}/v1/billing/meter_events",
            data=urllib.parse.urlencode(
                build_meter_event_payload(stripe_customer_id, event_name, value)
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {secret_key}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Stripe-Version": STRIPE_VERSION,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            logger.info("scamkit meter event recorded customer=%s event=%s status=%d",
                        stripe_customer_id, event_name, resp.status)
    except Exception as exc:
        logger.warning("scamkit meter event failed (non-fatal) customer=%s event=%s error=%s",
                       stripe_customer_id, event_name, exc)


def raw_body_bytes(event: dict) -> bytes:
    """Raw request body bytes for signature verification. API Gateway may
    base64-encode the body — the signature is computed over the RAW bytes,
    so decode first."""
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        return base64.b64decode(raw)
    return raw.encode("utf-8")
