"""
RelayShield Developer Signup Lambda

Routes:
  GET  /developers                 — developer landing page with signup form
  GET  /developer/success          — post-checkout confirmation page
  GET  /developer/topup            — credit pack purchase page
  GET  /developer/cs-mobile-link   — Crypto Shield Mobile app fetches its auto-provisioned
                                      API key by email (no separate developer signup/card)
  POST /developer/signup           — create Stripe Customer + Checkout session → return checkout_url
  POST /developer/topup            — create one-time Stripe Checkout for credit pack → return checkout_url
  POST /developer/stripe-webhook   — checkout.session.completed → issue key OR add credits
                                      (also auto-provisions CS Mobile subscribers, see
                                      _handle_cs_mobile_checkout)
"""

import base64
import hashlib
import hmac
import json
import logging
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

secrets_client = boto3.client("secretsmanager")
dynamodb       = boto3.resource("dynamodb")
ses            = boto3.client("ses", region_name="us-east-1")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_KEYS_TABLE   = "relayshield_api_keys"
STRIPE_API_BASE  = "https://api.stripe.com/v1"
FROM_EMAIL       = "noreply@relayshield.net"
API_BASE_URL     = "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod"
# Branded host for anything a customer's browser will actually see or submit to.
# Both hosts route every /marketplace/* path identically (verified 2026-07-30),
# but the raw execute-api hostname pins whoever sees it to an AWS-internal URL
# that breaks if the API Gateway ID changes, and it looks like a phishing target
# to a buyer who just paid on AWS Marketplace. Same reasoning that moved the
# TAXII discovery document's api_roots off this host on 2026-07-28.
PUBLIC_API_BASE_URL = "https://api.relayshield.net"
ADMIN_CHAT_ID    = 1729226804

# Threat Intelligence subscription prices → internal plan tier.
# mp_499  = $499/mo — 10,000 calls/month cap (enforced by _check_and_increment_intel_quota in relayshield_api.py)
# mssp_999 = $999/mo — unlimited (intel_access=True, no quota gate)
TI_PRICE_TIER_MAP = {
    "price_1TiIcqL2dcjOeFiY2wTZV8Kb": "mp_499",   # $499/mo MSP
    "price_1TiIcqL2dcjOeFiYDcuBewo2": "mssp_999",  # $999/mo MSSP unlimited
}

# Crypto Shield Mobile — $10.99/mo or $105.99/yr subscription prices, matched
# by PaywallScreen.tsx's Stripe Payment Links. Added 2026-07-11: subscribers
# previously had no automatic way to get a RelayShield API key — they had to
# separately sign up for the pay-per-call developer API with its own credit
# card, which is exactly the confusing double-billing experience that caused
# Arjen's support issue. This auto-provisions a key scoped to CS Mobile's own
# small set of endpoints (see CS_MOBILE_ALLOWED_ENDPOINTS in relayshield_api.py)
# at no extra per-call charge, tied to the $10.99/mo subscription itself.
CS_MOBILE_PRICE_IDS = frozenset({
    "price_1ToLjdL2dcjOeFiYVuBGPZgI",  # $10.99/mo
    "price_1ToLtuL2dcjOeFiYGivL2rts",  # $105.99/yr
})

# LLMjacking Detection API license — $39/mo or $399/yr flat-rate subscription
# scoped to /v1/metered/llm-credential-exposure only. Created 2026-07-26 as a
# standalone product (not a TI plan tier) since it's meant to be sold directly
# off the blog post to buyers who want just this one endpoint at a predictable
# flat rate, not the full $499+/mo TI catalog. Same flag-based bypass pattern
# as CS_MOBILE_PRICE_IDS/cs_mobile_access above — see is_llm_license_call in
# relayshield_api.py's handle_metered_request.
LLM_LICENSE_PRICE_IDS = frozenset({
    "price_1TxdQpL2dcjOeFiYeXtONMuK",  # $39/mo
    "price_1TxdQpL2dcjOeFiYe1XqvVGn",  # $399/yr
})

# One price per metered endpoint — created in Stripe Dashboard Jun 11 2026
STRIPE_PRICE_IDS = [
    # --- Original 5 (Jun 11 2026) ---
    "price_1Th6Q5L2dcjOeFiYG1RkNJeP",  # breach              $0.10/call
    "price_1Th6SaL2dcjOeFiYfumGGvde",  # sim-swap            $0.25/call
    "price_1Th6TGL2dcjOeFiYLLp55faD",  # infostealer         $0.50/call
    "price_1Th6U1L2dcjOeFiY0nGMVt9u",  # domain              $0.30/call
    "price_1ThtUrL2dcjOeFiYTYgh9BtZ",  # crypto-intel        $0.30/call
    # --- TC/RF competitive parity — first 3 (Jun 23 2026, prod_Ul5 series) ---
    "price_1TlZIkL2dcjOeFiYUgp7D22b",  # brand-monitor        $0.25/call
    "price_1TlZHTL2dcjOeFiYxwcT3Hzk",  # ioc-pivot            $0.20/call
    "price_1TlZFlL2dcjOeFiYsrxiG115",  # bulk-ioc             $0.50/batch
    # --- Remaining 12 endpoints (Jun 23 2026, prod_Ul7 series) ---
    "price_1Tlb9BL2dcjOeFiYXDs8JuoW",  # oauth-watchlist      $0.30/call
    "price_1TlbB1L2dcjOeFiYPh5XlpV6",  # supply-chain         $0.10/call
    "price_1TlbC6L2dcjOeFiYBOSc64xX",  # session-risk         $0.30/call
    "price_1TlbDAL2dcjOeFiYMmvUg1i2",  # identity-graph       $0.35/call
    "price_1TlbEEL2dcjOeFiY4BjNSfgd",  # ransomware-risk      $0.40/call
    "price_1TlbF3L2dcjOeFiYQqiev2KU",  # nhi-exposure         $0.40/call
    "price_1TxdgML2dcjOeFiYt2MRIm2o",  # llm-credential-exposure $0.40/call — created 2026-07-26.
    # Gap found and fixed same-day: this endpoint's Stripe meter event
    # (relayshield_llm_credential_exposure_calls in STRIPE_METER_EVENTS,
    # relayshield_api.py) had been firing since earlier in the session with
    # NO registered Billing Meter and NO subscription-item price behind it —
    # meaning fiat-PAYG developers could call it successfully but RelayShield
    # was never actually billed. Meter mtr_61V71dhQzZcKKhGbs41L2dcjOeFiYEZ6 +
    # this price now close that gap for all NEW developer signups. Does not
    # retroactively backfill this line item onto subscriptions created before
    # this fix — same accepted limitation as every other endpoint added after
    # initial launch (cert-expiry, ip-intel, card-exposure all have the same
    # gap for pre-existing developers, undocumented until now).
    "price_1TlbFwL2dcjOeFiYNVvkbWJY",  # secret-scan          $0.35/call
    "price_1TlbGxL2dcjOeFiYsROuaYuf",  # target-risk          $0.50/call
    "price_1TlbHeL2dcjOeFiYwoND91TG",  # asset-intel          $0.15/call
    "price_1TlbIUL2dcjOeFiYI9Jfjp6S",  # threat-actor         $0.30/call
    "price_1TlbJEL2dcjOeFiYOKAtQlDk",  # cve-identity-risk    $0.40/call
    "price_1TlbKYL2dcjOeFiYME8tih1m",  # identity-risk-score  $0.35/call
    # --- Agentic AI / OrcX (Jun 24 2026) ---
    "price_1TleexL2dcjOeFiYs0MZSoXv",  # bulk-identity-risk   $2.00/call (10 domains + 5 agents each)
    # NOTE: prod_Ul7 bulk-ioc/ioc-pivot/brand-monitor prices intentionally
    # excluded — same meters as prod_Ul5 prices above; adding both would double-bill.
    # Archive prod_Ul7azZTbGApOBz, prod_Ul7bh2YyggQKGE, prod_Ul7bL69PkqmNit in Stripe.
    # --- Competitive benchmark roadmap (Jul 24 2026) ---
    "price_1Twp6aL2dcjOeFiYXWr0GIkw",  # card-exposure        $0.30/call
    # brand-monitor's $0.25 -> $0.35 raise (same date) needed no new price ID
    # here — Stripe let the existing price_1TlZIkL2dcjOeFiYUgp7D22b be edited
    # in place (0 active subscriptions on it at the time), so the ID already
    # in this list above already reflects the new rate.
]

SUCCESS_URL        = f"{API_BASE_URL}/developer/success?session_id={{CHECKOUT_SESSION_ID}}"
TOPUP_SUCCESS_URL  = f"{API_BASE_URL}/developer/topup-success?session_id={{CHECKOUT_SESSION_ID}}"
CANCEL_URL         = f"{API_BASE_URL}/developers"

# Credit pack prices — one-time payments created Jun 12 2026
# credits = amount in cents (1 credit = $0.01)
CREDIT_PACKS = [
    {"price_id": "price_1TheYxL2dcjOeFiYmoBtCwS3", "dollars": 25,  "credits": 2500},
    {"price_id": "price_1TheYxL2dcjOeFiYs69xTFLm", "dollars": 50,  "credits": 5000},
    {"price_id": "price_1TheYyL2dcjOeFiY8qGn3tgX", "dollars": 100, "credits": 10000},
]

# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

_secret_cache: dict[str, str] = {}


def _get_secret(name: str) -> str:
    if name not in _secret_cache:
        _secret_cache[name] = secrets_client.get_secret_value(SecretId=name)["SecretString"].strip()
    return _secret_cache[name]


def _stripe_key() -> str:
    raw = _get_secret("relayshield/stripe_secret_key")
    try:
        d = json.loads(raw)
        return d.get("stripe_secret_key") or d.get("STRIPE_SECRET_KEY") or raw
    except (json.JSONDecodeError, KeyError):
        return raw


def _webhook_secret() -> str:
    return _get_secret("relayshield/stripe_developer_webhook_secret")


# ---------------------------------------------------------------------------
# Stripe helpers
# ---------------------------------------------------------------------------

def _stripe_post(path: str, data: dict) -> dict:
    payload = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        f"{STRIPE_API_BASE}{path}",
        data=payload,
        headers={
            "Authorization":  f"Bearer {_stripe_key()}",
            "Content-Type":   "application/x-www-form-urlencoded",
            "Stripe-Version": "2024-06-20",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _stripe_get_sub(subscription_id: str) -> dict:
    req = urllib.request.Request(
        f"{STRIPE_API_BASE}/subscriptions/{subscription_id}",
        headers={
            "Authorization":  f"Bearer {_stripe_key()}",
            "Stripe-Version": "2024-06-20",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _ok(data: dict, status: int = 200) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"ok": True, "data": data}),
    }


def _err(message: str, status: int = 400) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"ok": False, "error": message}),
    }


# ---------------------------------------------------------------------------
# POST /developer/signup
# ---------------------------------------------------------------------------

VALID_SOURCES = {"direct", "n8n", "tines", "hf-smolagents"}

def handle_signup(body: dict) -> dict:
    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _err("email is required")

    source = (body.get("source") or "direct").strip().lower()
    if source not in VALID_SOURCES:
        source = "direct"

    # Create Stripe Customer
    try:
        customer    = _stripe_post("/customers", {"email": email, "description": "RelayShield API developer"})
        customer_id = customer["id"]
    except Exception as exc:
        logger.error("Stripe customer creation failed email=%s error=%s", email, exc)
        return _err("could not create billing account — try again", 502)

    # Build Checkout session with all 4 metered prices
    session_params: dict = {
        "mode":        "subscription",
        "customer":    customer_id,
        "success_url": SUCCESS_URL,
        "cancel_url":  CANCEL_URL,
        # Store email + source in metadata so webhook can retrieve them without extra Stripe calls
        "subscription_data[metadata][developer_email]": email,
        "subscription_data[metadata][source]":          source,
    }
    for i, price_id in enumerate(STRIPE_PRICE_IDS):
        session_params[f"line_items[{i}][price]"] = price_id

    try:
        session      = _stripe_post("/checkout/sessions", session_params)
        checkout_url = session["url"]
    except Exception as exc:
        logger.error("Stripe checkout session failed customer=%s error=%s", customer_id, exc)
        return _err("could not create checkout session — try again", 502)

    logger.info("developer signup — email=%s customer=%s session=%s", email, customer_id, session["id"])
    return _ok({"checkout_url": checkout_url})


# ---------------------------------------------------------------------------
# GET /developer/cs-mobile-link
# ---------------------------------------------------------------------------

def handle_cs_mobile_link(query_params: dict) -> dict:
    """Lets the Crypto Shield Mobile app retrieve its subscriber's auto-provisioned
    API key by the email used at Stripe checkout — no manual developer signup,
    no separate card. Returns 404-equivalent (ok=False) if no active CS Mobile
    subscription is found for that email, e.g. checkout hasn't completed yet or
    they used a different email than they typed here."""
    email = (query_params.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _err("a valid email is required")

    record = _find_key_by_email(email)
    if not record or not record.get("cs_mobile_access"):
        return _err("No active Crypto Shield subscription found for that email. "
                     "Double-check the email you used at checkout, or subscribe first.", 404)

    return _ok({"api_key": record["api_key"]})


# ---------------------------------------------------------------------------
# GET /developer/cs-mobile-link-by-session
# ---------------------------------------------------------------------------

def handle_cs_mobile_link_by_session(query_params: dict) -> dict:
    """Zero-touch counterpart to handle_cs_mobile_link -- the app deep-links
    back here with the Stripe Checkout Session ID (from the payment link's
    after_completion redirect) instead of asking the subscriber to type their
    checkout email. The session ID is real proof of purchase, so no other
    verification is needed. Returns ok=False if the webhook hasn't landed yet
    (rare race: user returns to the app before Stripe's webhook fires) --
    the app should fall back to the email field in that case."""
    session_id = (query_params.get("session_id") or "").strip()
    if not session_id:
        return _err("session_id is required")

    record = _find_key_by_checkout_session(session_id)
    if not record or not record.get("cs_mobile_access"):
        return _err("Subscription not found yet for that checkout session -- "
                     "it may still be processing. Try again in a few seconds, "
                     "or use the email field below.", 404)

    return _ok({"api_key": record["api_key"]})


# ---------------------------------------------------------------------------
# GET /developer/cs-mobile-portal
# ---------------------------------------------------------------------------

CS_MOBILE_PORTAL_RETURN_URL = "https://cryptoshieldmobile.relayshield.net"


def handle_cs_mobile_portal(query_params: dict) -> dict:
    """Self-service billing management for Crypto Shield Mobile subscribers --
    creates a Stripe-hosted Customer Portal session (cancel, update card, view
    invoices) so a subscriber can cancel during their 7-day trial (or any time
    after) without emailing support. Prefers api_key (the app already has this
    stored locally post-link, so the user isn't asked to retype their checkout
    email just to manage billing) -- a direct point lookup, not a scan. Falls
    back to email (same lookup handle_cs_mobile_link uses) if no api_key is
    passed. Same allowlist gating either way (must have cs_mobile_access)."""
    api_key = (query_params.get("api_key") or "").strip()
    email   = (query_params.get("email") or "").strip().lower()

    if api_key:
        resp = dynamodb.Table(API_KEYS_TABLE).get_item(
            Key={"api_key": api_key},
            ProjectionExpression="cs_mobile_access, stripe_customer_id",
        )
        record = resp.get("Item")
    elif email and "@" in email:
        record = _find_key_by_email(email)
    else:
        return _err("api_key or a valid email is required")

    if not record or not record.get("cs_mobile_access"):
        return _err("No active Crypto Shield subscription found.", 404)

    stripe_customer_id = record.get("stripe_customer_id")
    if not stripe_customer_id:
        return _err("Subscription found but not linked to billing yet -- try again shortly.", 404)

    try:
        session = _stripe_post("/billing_portal/sessions", {
            "customer":   stripe_customer_id,
            "return_url": CS_MOBILE_PORTAL_RETURN_URL,
        })
    except Exception as exc:
        logger.error("cs-mobile-portal Stripe error email=%s error=%s", email, exc)
        return _err("Could not open billing management right now. Try again shortly.", 502)

    return _ok({"portal_url": session["url"]})


# ---------------------------------------------------------------------------
# Stripe webhook signature verification
# ---------------------------------------------------------------------------

def _verify_stripe_sig(payload: bytes, sig_header: str, secret: str) -> bool:
    try:
        parts     = dict(item.split("=", 1) for item in sig_header.split(","))
        timestamp = parts.get("t", "")
        v1_sig    = parts.get("v1", "")
        signed    = timestamp.encode() + b"." + payload
        expected  = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, v1_sig)
    except Exception as exc:
        logger.error("Stripe sig verification error: %s", exc)
        return False


# ---------------------------------------------------------------------------
# POST /developer/stripe-webhook
# ---------------------------------------------------------------------------

def _issue_api_key(customer_id: str, subscription_id: str, email: str, source: str = "direct") -> str:
    api_key = f"rs_live_{uuid.uuid4().hex}"
    dynamodb.Table(API_KEYS_TABLE).put_item(Item={
        "api_key":                api_key,
        "stripe_customer_id":     customer_id,
        "stripe_subscription_id": subscription_id,
        "email":                  email,
        "active":                 True,
        "source":                 source,
        "created_at":             datetime.now(timezone.utc).isoformat(),
    })
    logger.info("API key issued customer=%s subscription=%s email=%s source=%s", customer_id, subscription_id, email, source)
    return api_key


def _send_key_email(to_email: str, api_key: str) -> None:
    subject = "Your RelayShield API Key"
    body    = f"""Welcome to RelayShield API.

Your API key
------------
{api_key}

Add this header to every request:
  X-RS-API-KEY: {api_key}

Endpoints
---------
POST {API_BASE_URL}/v1/metered/breach          — email breach check              $0.10/call
POST {API_BASE_URL}/v1/metered/sim-swap        — SIM swap detection              $0.25/call
POST {API_BASE_URL}/v1/metered/infostealer     — infostealer log check           $0.50/call
POST {API_BASE_URL}/v1/metered/domain          — typosquat domain scan           $0.30/call
POST {API_BASE_URL}/v1/metered/oauth-watchlist — OAuth + stolen token check      $0.30/call
POST {API_BASE_URL}/v1/metered/supply-chain    — vendor/supply chain risk        $0.10/call
POST {API_BASE_URL}/v1/metered/session-risk    — active session hijack detection $0.30/call
POST {API_BASE_URL}/v1/metered/identity-graph  — identity correlation             $0.35/call
POST {API_BASE_URL}/v1/metered/ransomware-risk — ransomware victim + pre-creds    $0.40/call
POST {API_BASE_URL}/v1/metered/nhi-exposure    — API key/token NHI detection       $0.40/call
POST {API_BASE_URL}/v1/metered/secret-scan     — GitHub/GitLab secret scanning      $0.35/call
POST {API_BASE_URL}/v1/metered/target-risk     — 6-signal target probability score  $0.50/call
POST {API_BASE_URL}/v1/metered/tech-stack-cve          — agent framework exploit monitoring $0.20/call
POST {API_BASE_URL}/v1/metered/mcp-registry-risk       — MCP server registry reputation     $0.35/call
POST {API_BASE_URL}/v1/metered/prompt-injection-breach — prompt-injection-sourced breach     $0.35/call
POST {API_BASE_URL}/v1/metered/bulk-ioc                — bulk IOC enrichment (up to 100)     $0.50/batch
POST {API_BASE_URL}/v1/metered/ioc-pivot               — related-infrastructure IOC pivot    $0.20/call
POST {API_BASE_URL}/v1/metered/brand-monitor           — brand name IOC corpus scan          $0.35/call
POST {API_BASE_URL}/v1/metered/bulk-identity-risk      — hierarchical org + agent risk score $2.00/call
POST {API_BASE_URL}/v1/metered/card-exposure           — stolen card BIN/hash exposure check $0.30/call

Quick start
-----------
curl -X POST {API_BASE_URL}/v1/metered/breach \\
  -H "X-RS-API-KEY: {api_key}" \\
  -H "Content-Type: application/json" \\
  -d '{{"email":"you@example.com"}}'

Billing: usage is metered monthly via Stripe. You will only be charged for calls made.

Docs & support: https://api.relayshield.net/developers
"""
    try:
        ses.send_email(
            Source=FROM_EMAIL,
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject},
                "Body":    {"Text": {"Data": body}},
            },
        )
        logger.info("API key email sent to %s", to_email)
    except Exception as exc:
        logger.error("SES send failed to=%s error=%s", to_email, exc)


# ---------------------------------------------------------------------------
# Threat Intelligence provisioning helpers
# ---------------------------------------------------------------------------

def _tg_alert(text: str) -> None:
    """Send a plain-text message to the admin Telegram chat."""
    import urllib.request as _ur
    try:
        token = _get_secret("relayshield/telegram_bot_token")
        try:
            token = json.loads(token).get("telegram_bot_token", token)
        except Exception:
            pass
        payload = json.dumps({"chat_id": ADMIN_CHAT_ID, "text": text}).encode()
        req = _ur.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        _ur.urlopen(req, timeout=10)
    except Exception as exc:
        logger.error("Admin TG alert failed: %s", exc)


def _get_subscription_price_id(subscription_id: str) -> str | None:
    """Call the Stripe API to get the price ID for a subscription."""
    credentials = base64.b64encode(f"{_stripe_key()}:".encode()).decode()
    req = urllib.request.Request(
        f"{STRIPE_API_BASE}/subscriptions/{subscription_id}",
        headers={"Authorization": f"Basic {credentials}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            items = data.get("items", {}).get("data", [])
            if items:
                return items[0].get("price", {}).get("id")
    except Exception as exc:
        logger.error("Stripe subscription lookup failed sub=%s error=%s", subscription_id, exc)
    return None


def _find_key_by_customer(stripe_customer_id: str) -> dict | None:
    """
    Scan relayshield_api_keys for a record matching the given Stripe customer ID.
    Table PK is api_key — no GSI on stripe_customer_id yet (acceptable at current scale;
    add a GSI when the key count grows past a few hundred).
    """
    resp = dynamodb.Table(API_KEYS_TABLE).scan(
        FilterExpression=Attr("stripe_customer_id").eq(stripe_customer_id),
        ProjectionExpression="api_key, email, intel_access, intel_plan_tier, stripe_subscription_id",
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def _find_key_by_subscription(stripe_subscription_id: str) -> dict | None:
    """Scan relayshield_api_keys for a record matching the given Stripe subscription ID."""
    resp = dynamodb.Table(API_KEYS_TABLE).scan(
        FilterExpression=Attr("stripe_subscription_id").eq(stripe_subscription_id),
        ProjectionExpression="api_key, email, intel_access, intel_plan_tier",
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def _find_key_by_email(email: str) -> dict | None:
    """Scan relayshield_api_keys for a record matching the given email. Used by
    the CS Mobile app to retrieve an already-provisioned key (no GSI on email
    yet — acceptable at current table scale, same as the customer/subscription
    scans above).

    A single email can have multiple records (e.g. a duplicate checkout that
    was later refunded/cancelled, like Arjen's), so prefer whichever match
    actually has cs_mobile_access set rather than an arbitrary/unordered scan
    result -- otherwise an unflagged duplicate can shadow the real one."""
    resp = dynamodb.Table(API_KEYS_TABLE).scan(
        FilterExpression=Attr("email").eq(email.strip().lower()),
        ProjectionExpression="api_key, cs_mobile_access, active, stripe_subscription_id, stripe_customer_id",
    )
    items = resp.get("Items", [])
    if not items:
        return None
    for item in items:
        if item.get("cs_mobile_access"):
            return item
    return items[0]


def _find_key_by_checkout_session(session_id: str) -> dict | None:
    """Scan relayshield_api_keys for a record matching the given Stripe Checkout
    Session ID -- used by the CS Mobile zero-touch deep-link-back flow so a
    subscriber never has to type their checkout email. The session ID itself
    is real proof of purchase (returned by Stripe only to the person who just
    paid), unlike an email which anyone could type."""
    resp = dynamodb.Table(API_KEYS_TABLE).scan(
        FilterExpression=Attr("stripe_checkout_session_id").eq(session_id),
        ProjectionExpression="api_key, cs_mobile_access, active",
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def _provision_intel_access(api_key_str: str, stripe_subscription_id: str, intel_plan_tier: str, source: str = "direct") -> None:
    """
    Set intel_access=True, intel_plan_tier, and reset the monthly call counter.
    Called on checkout.session.completed and customer.subscription.updated for TI plans.
    """
    current_period = datetime.now(timezone.utc).strftime("%Y-%m")
    dynamodb.Table(API_KEYS_TABLE).update_item(
        Key={"api_key": api_key_str},
        UpdateExpression=(
            "SET intel_access = :yes, "
            "intel_plan_tier = :tier, "
            "stripe_subscription_id = :sid, "
            "intel_period_calls = :zero, "
            "intel_period_start = :period, "
            "#src = :source"
        ),
        ExpressionAttributeNames={"#src": "source"},
        ExpressionAttributeValues={
            ":yes":    True,
            ":tier":   intel_plan_tier,
            ":sid":    stripe_subscription_id,
            ":zero":   0,
            ":period": current_period,
            ":source": source,
        },
    )
    logger.info("intel_access provisioned api_key=%s tier=%s source=%s", api_key_str[:16], intel_plan_tier, source)


def _revoke_intel_access(api_key_str: str) -> None:
    """Set intel_access=False on cancellation."""
    dynamodb.Table(API_KEYS_TABLE).update_item(
        Key={"api_key": api_key_str},
        UpdateExpression="SET intel_access = :no",
        ExpressionAttributeValues={":no": False},
    )
    logger.info("intel_access revoked api_key=%s", api_key_str[:16])


def _provision_cs_mobile_access(api_key_str: str, stripe_subscription_id: str) -> None:
    """Set cs_mobile_access=True. Deliberately separate from intel_access/
    has_subscription — CS Mobile keys are scoped to a small allowlist of
    endpoints (CS_MOBILE_ALLOWED_ENDPOINTS in relayshield_api.py), not the
    full metered catalog, so a $10.99/mo subscriber can't reach $2.00/call
    enterprise endpoints for free."""
    dynamodb.Table(API_KEYS_TABLE).update_item(
        Key={"api_key": api_key_str},
        UpdateExpression="SET cs_mobile_access = :yes, stripe_subscription_id = :sid",
        ExpressionAttributeValues={":yes": True, ":sid": stripe_subscription_id},
    )
    logger.info("cs_mobile_access provisioned api_key=%s", api_key_str[:16])


def _revoke_cs_mobile_access(api_key_str: str) -> None:
    """Set cs_mobile_access=False on CS Mobile subscription cancellation."""
    dynamodb.Table(API_KEYS_TABLE).update_item(
        Key={"api_key": api_key_str},
        UpdateExpression="SET cs_mobile_access = :no",
        ExpressionAttributeValues={":no": False},
    )
    logger.info("cs_mobile_access revoked api_key=%s", api_key_str[:16])


def _provision_llm_access(api_key_str: str, stripe_subscription_id: str) -> None:
    """Set llm_access=True. Same scoped-bypass shape as cs_mobile_access —
    gates only /v1/metered/llm-credential-exposure, not the full metered
    catalog, so a $39/mo license can't be used as a backdoor into $2.00/call
    enterprise endpoints."""
    dynamodb.Table(API_KEYS_TABLE).update_item(
        Key={"api_key": api_key_str},
        UpdateExpression="SET llm_access = :yes, stripe_subscription_id = :sid",
        ExpressionAttributeValues={":yes": True, ":sid": stripe_subscription_id},
    )
    logger.info("llm_access provisioned api_key=%s", api_key_str[:16])


def _revoke_llm_access(api_key_str: str) -> None:
    """Set llm_access=False on LLMjacking license subscription cancellation."""
    dynamodb.Table(API_KEYS_TABLE).update_item(
        Key={"api_key": api_key_str},
        UpdateExpression="SET llm_access = :no",
        ExpressionAttributeValues={":no": False},
    )
    logger.info("llm_access revoked api_key=%s", api_key_str[:16])


def _send_llm_license_key_email(to_email: str, api_key: str) -> None:
    subject = "Your RelayShield LLMjacking Detection API license"
    body = f"""Thanks for licensing LLMjacking detection.

Your API key
------------
{api_key}

Add this header to every request:
  X-RS-API-KEY: {api_key}

Endpoint (unlimited calls, included in your subscription):
  POST {API_BASE_URL}/v1/metered/llm-credential-exposure
  Body: {{"domain": "yourcompany.com"}}

Detects exposed OpenAI, Anthropic, Google, Groq, xAI, and Replicate API keys
in our criminal stealer-log corpus — the same signal that's let attackers run
up bills from $46K/day to $500K/month on a single leaked key.

Also available with no signup, as a free tool on our MCP server for agentic
workflows: https://huggingface.co/spaces/relayshieldadmin/relayshield-agentic-attack-surface

Docs & full endpoint catalog: https://api.relayshield.net/developers

Questions? support@relayshield.net
"""
    try:
        ses.send_email(
            Source=FROM_EMAIL,
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject},
                "Body":    {"Text": {"Data": body}},
            },
        )
        logger.info("LLM license key email sent to %s", to_email)
    except Exception as exc:
        logger.error("SES send failed (llm_license) to=%s error=%s", to_email, exc)


def _handle_llm_license_checkout(session: dict) -> None:
    """Auto-provision a key scoped to llm_access after a LLMjacking Detection
    API checkout.session.completed ($39/mo or $399/yr). Mirrors
    _handle_cs_mobile_checkout's idempotency shape exactly."""
    stripe_customer_id     = session.get("customer") or ""
    stripe_subscription_id = session.get("subscription") or ""
    customer_email         = (session.get("customer_details") or {}).get("email") or ""

    record = _find_key_by_customer(stripe_customer_id)

    if record:
        api_key = record["api_key"]
        if not record.get("llm_access"):
            _provision_llm_access(api_key, stripe_subscription_id)
            if customer_email:
                _send_llm_license_key_email(customer_email, api_key)
        else:
            logger.info("llm_access already provisioned api_key=%s", api_key[:16])
    else:
        api_key = _issue_api_key(stripe_customer_id, stripe_subscription_id, customer_email, source="llm_license")
        _provision_llm_access(api_key, stripe_subscription_id)
        if customer_email:
            _send_llm_license_key_email(customer_email, api_key)
        else:
            logger.warning("LLM license checkout with no email — key issued but not emailed, session=%s", session.get("id"))


def _send_cs_mobile_key_email(to_email: str, api_key: str) -> None:
    subject = "Your Crypto Shield Mobile subscription is unlocked"
    body    = f"""Thanks for subscribing to Crypto Shield Pro!

Your subscription is already linked in the app — live wallet risk scans,
breach checks, and phishing detection are unlocked now, no extra step
needed. (For reference, your account's key is {api_key} — you won't
normally need to enter this anywhere.)

If you ever reinstall the app or switch devices, just re-open the app and
enter this same email address when asked -- it re-links automatically, no
separate signup or extra charge. You can also manage or cancel your
subscription any time from Settings -> Manage Subscription.

One favor: if Crypto Shield Pro is working well for you, a quick rating on
the Solana dApp Store genuinely helps other people find it -- most apps
there have zero reviews, and honest ones from real subscribers stand out.
Takes under a minute: solanadappstore://details?id=net.relayshield.cryptoshield

Questions? support@relayshield.net
"""
    try:
        ses.send_email(
            Source=FROM_EMAIL,
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject},
                "Body":    {"Text": {"Data": body}},
            },
        )
        logger.info("CS Mobile key email sent to %s", to_email)
    except Exception as exc:
        logger.error("SES send failed (cs_mobile) to=%s error=%s", to_email, exc)


def _handle_cs_mobile_checkout(session: dict) -> None:
    """
    Auto-provision a scoped API key after a Crypto Shield Mobile
    checkout.session.completed ($10.99/mo or $105.99/yr).

    If the customer already has a key (e.g. they'd separately signed up for
    the developer API before subscribing to CS Mobile), we just flip on
    cs_mobile_access for their existing key. Otherwise we issue a fresh key
    and email it — same idempotency pattern as _handle_ti_checkout.
    """
    stripe_customer_id     = session.get("customer") or ""
    stripe_subscription_id = session.get("subscription") or ""
    customer_email         = (session.get("customer_details") or {}).get("email") or ""
    checkout_session_id    = session.get("id") or ""

    record = _find_key_by_customer(stripe_customer_id)

    if record:
        api_key = record["api_key"]
        if not record.get("cs_mobile_access"):
            _provision_cs_mobile_access(api_key, stripe_subscription_id)
        else:
            logger.info("cs_mobile_access already provisioned api_key=%s", api_key[:16])
    else:
        api_key = _issue_api_key(stripe_customer_id, stripe_subscription_id, customer_email, source="cs_mobile")
        _provision_cs_mobile_access(api_key, stripe_subscription_id)
        if customer_email:
            _send_cs_mobile_key_email(customer_email, api_key)
        else:
            logger.warning("CS Mobile checkout with no email — key issued but not emailed, session=%s", checkout_session_id)

    # Stamp the Checkout Session ID on the key record regardless of the
    # branch above -- lets the mobile app exchange it for the API key via
    # the deep-link-back zero-touch flow (see handle_cs_mobile_link_by_session)
    # without the user having to type their checkout email.
    if checkout_session_id:
        dynamodb.Table(API_KEYS_TABLE).update_item(
            Key={"api_key": api_key},
            UpdateExpression="SET stripe_checkout_session_id = :sid",
            ExpressionAttributeValues={":sid": checkout_session_id},
        )


def _handle_ti_checkout(session: dict, source: str = "direct") -> None:
    """
    Provision TI access after a $499/$999 checkout.session.completed.

    If the customer already has a metered API key (stripe_customer_id match), we set
    intel_access=True on that record. If they subscribed to TI without going through the
    metered signup first, we create a new API key and email it to them.
    """
    stripe_customer_id     = session.get("customer") or ""
    stripe_subscription_id = session.get("subscription") or ""
    customer_email         = (session.get("customer_details") or {}).get("email") or ""

    price_id        = _get_subscription_price_id(stripe_subscription_id)
    intel_plan_tier = TI_PRICE_TIER_MAP.get(price_id or "")

    if not intel_plan_tier:
        logger.error("TI checkout: unknown price_id=%s sub=%s", price_id, stripe_subscription_id)
        _tg_alert(
            f"⚠️ TI checkout — unknown price ID.\n"
            f"price_id: {price_id}\ncustomer: {stripe_customer_id}\n"
            f"Manual provisioning required."
        )
        return

    record = _find_key_by_customer(stripe_customer_id)

    if record:
        # Idempotency: skip if already at the same tier
        if record.get("intel_access") and record.get("intel_plan_tier") == intel_plan_tier:
            logger.info("TI already provisioned api_key=%s tier=%s — skip", record["api_key"][:16], intel_plan_tier)
            return
        _provision_intel_access(record["api_key"], stripe_subscription_id, intel_plan_tier, source=source)
        _tg_alert(
            f"✅ TI access provisioned.\n"
            f"email: {customer_email or record.get('email', '?')}\n"
            f"plan: {intel_plan_tier}\nsource: {source}\n"
            f"api_key: {record['api_key'][:16]}..."
        )
    else:
        # No metered key exists — create one so the customer gets a working key immediately
        api_key = _issue_api_key(stripe_customer_id, stripe_subscription_id, customer_email, source=source)
        _provision_intel_access(api_key, stripe_subscription_id, intel_plan_tier, source=source)
        if customer_email:
            _send_ti_key_email(customer_email, api_key, intel_plan_tier)
        _tg_alert(
            f"✅ TI access provisioned (new key created — no prior metered account).\n"
            f"email: {customer_email}\nplan: {intel_plan_tier}\napi_key: {api_key[:16]}..."
        )


def _send_ti_key_email(to_email: str, api_key: str, intel_plan_tier: str) -> None:
    """Send the API key and TI endpoint instructions to a new TI-only subscriber."""
    tier_label = "$499/mo — 10,000 calls/month" if intel_plan_tier == "mp_499" else "$999/mo — unlimited"
    subject = "Your RelayShield Threat Intelligence API Key"
    body = f"""Welcome to RelayShield Threat Intelligence.

Your API key
------------
{api_key}

Plan: {tier_label}

Add this header to every request:
  X-RS-API-KEY: {api_key}

Threat Intelligence endpoint
-----------------------------
GET  {API_BASE_URL}/v1/intel/telegram?indicator=<value>&type=<email|domain|ip|phone|wallet>

Example:
  curl "{API_BASE_URL}/v1/intel/telegram?indicator=example.com&type=domain" \\
    -H "X-RS-API-KEY: {api_key}"

CVE / ransomware intelligence:
  GET  {API_BASE_URL}/v1/intel/cve?cve_id=CVE-2024-1234
  GET  {API_BASE_URL}/v1/intel/cve?keyword=apache

All metered endpoints are also available on this key:
  POST {API_BASE_URL}/v1/metered/breach
  POST {API_BASE_URL}/v1/metered/sim-swap
  POST {API_BASE_URL}/v1/metered/infostealer
  POST {API_BASE_URL}/v1/metered/domain

Docs & support: https://api.relayshield.net/developers
"""
    try:
        ses.send_email(
            Source=FROM_EMAIL,
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject},
                "Body":    {"Text": {"Data": body}},
            },
        )
        logger.info("TI key email sent to %s", to_email)
    except Exception as exc:
        logger.error("SES TI email failed to=%s error=%s", to_email, exc)


def handle_webhook(headers: dict, raw_body: bytes) -> dict:
    sig_header = headers.get("Stripe-Signature") or headers.get("stripe-signature", "")

    try:
        secret = _webhook_secret()
    except Exception as exc:
        logger.error("webhook secret not found: %s", exc)
        return {"statusCode": 500, "body": "webhook secret not configured"}

    if not _verify_stripe_sig(raw_body, sig_header, secret):
        logger.warning("invalid Stripe webhook signature")
        return {"statusCode": 400, "body": "invalid signature"}

    try:
        event = json.loads(raw_body)
    except Exception:
        return {"statusCode": 400, "body": "invalid JSON"}

    event_type = event.get("type")
    logger.info("Stripe webhook event_type=%s", event_type)

    # --- TI subscription lifecycle events ---
    if event_type == "customer.subscription.updated":
        subscription = event["data"]["object"]
        sub_id       = subscription.get("id", "")
        items        = subscription.get("items", {}).get("data", [])
        price_id     = items[0].get("price", {}).get("id") if items else None
        tier         = TI_PRICE_TIER_MAP.get(price_id or "")
        if tier:
            record = _find_key_by_subscription(sub_id)
            if record:
                _provision_intel_access(record["api_key"], sub_id, tier)
                logger.info("TI plan updated api_key=%s tier=%s", record["api_key"][:16], tier)
            else:
                logger.warning("subscription.updated: no API key for sub=%s", sub_id)
        return {"statusCode": 200, "body": "ok"}

    if event_type == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        sub_id       = subscription.get("id", "")
        items        = subscription.get("items", {}).get("data", [])
        price_id     = items[0].get("price", {}).get("id") if items else None
        if price_id in TI_PRICE_TIER_MAP:
            record = _find_key_by_subscription(sub_id)
            if record:
                _revoke_intel_access(record["api_key"])
                _tg_alert(
                    f"⚠️ TI subscription cancelled.\n"
                    f"email: {record.get('email', '?')}\n"
                    f"api_key: {record['api_key'][:16]}..."
                )
            else:
                logger.warning("subscription.deleted: no API key for sub=%s", sub_id)
        elif price_id in CS_MOBILE_PRICE_IDS:
            record = _find_key_by_subscription(sub_id)
            if record:
                _revoke_cs_mobile_access(record["api_key"])
            else:
                logger.warning("subscription.deleted (cs_mobile): no API key for sub=%s", sub_id)
        elif price_id in LLM_LICENSE_PRICE_IDS:
            record = _find_key_by_subscription(sub_id)
            if record:
                _revoke_llm_access(record["api_key"])
            else:
                logger.warning("subscription.deleted (llm_license): no API key for sub=%s", sub_id)
        return {"statusCode": 200, "body": "ok"}

    if event_type == "checkout.session.completed":
        session       = event["data"]["object"]
        customer_id   = session.get("customer", "")
        sub_id        = session.get("subscription", "")
        metadata      = session.get("metadata") or {}
        checkout_type = metadata.get("checkout_type", "subscription")
        email         = (
            session.get("customer_details", {}).get("email")
            or session.get("customer_email")
            or ""
        )

        if checkout_type == "topup":
            # Credit pack purchase — add credits to existing key
            api_key_str = metadata.get("api_key", "")
            credits     = int(metadata.get("credits") or 0)
            if api_key_str and credits:
                _add_credits(api_key_str, credits)
                logger.info("topup complete key=%s credits=%d", api_key_str[:16], credits)
            else:
                logger.error("topup missing api_key or credits in metadata session=%s", session.get("id"))
            return {"statusCode": 200, "body": "ok"}

        # Pull source from subscription metadata (set at checkout creation time)
        sub_metadata = {}
        if sub_id:
            try:
                sub_data     = _stripe_get_sub(sub_id)
                sub_metadata = sub_data.get("metadata") or {}
            except Exception:
                pass
        source = sub_metadata.get("source") or metadata.get("source") or "direct"
        if source not in VALID_SOURCES:
            source = "direct"

        # Check if this is a TI or CS Mobile subscription checkout before assuming
        # it's a generic metered developer signup
        if sub_id:
            price_id = _get_subscription_price_id(sub_id)
            if price_id in TI_PRICE_TIER_MAP:
                logger.info("TI checkout detected price=%s sub=%s", price_id, sub_id)
                _handle_ti_checkout(session, source=source)
                return {"statusCode": 200, "body": "ok"}
            if price_id in CS_MOBILE_PRICE_IDS:
                logger.info("CS Mobile checkout detected price=%s sub=%s", price_id, sub_id)
                _handle_cs_mobile_checkout(session)
                return {"statusCode": 200, "body": "ok"}
            if price_id in LLM_LICENSE_PRICE_IDS:
                logger.info("LLM license checkout detected price=%s sub=%s", price_id, sub_id)
                _handle_llm_license_checkout(session)
                return {"statusCode": 200, "body": "ok"}

        # Metered subscription signup — issue new API key
        if not customer_id or not sub_id:
            logger.error("missing customer or subscription in session=%s", session.get("id"))
            return {"statusCode": 200, "body": "ok"}

        # Idempotency — don't re-issue if key already exists for this subscription
        existing = dynamodb.Table(API_KEYS_TABLE).scan(
            FilterExpression=Attr("stripe_subscription_id").eq(sub_id)
        )
        if existing.get("Items"):
            logger.info("API key already issued for subscription=%s — skipping", sub_id)
            return {"statusCode": 200, "body": "ok"}

        api_key = _issue_api_key(customer_id, sub_id, email, source=source)
        if email:
            _send_key_email(email, api_key)
        else:
            logger.warning("no email on session=%s — key issued but not emailed", session.get("id"))

    return {"statusCode": 200, "body": "ok"}


# ---------------------------------------------------------------------------
# HTML pages
# ---------------------------------------------------------------------------

def _html(body: str, status: int = 200) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store, no-cache, must-revalidate",
        },
        "body": body,
    }


LANDING_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RelayShield API — Security Intelligence for Developers</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0d0f14; --surface: #161a23; --border: #242836;
    --accent: #6c63ff; --accent-dim: #4e47d6; --green: #22c55e;
    --text: #e8eaf0; --muted: #8b91a8;
    --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  }
  body { background: var(--bg); color: var(--text); font-family: var(--font); line-height: 1.6; }
  a { color: var(--accent); text-decoration: none; }

  /* Nav */
  nav { display: flex; align-items: center; justify-content: space-between;
        padding: 1.1rem 2rem; border-bottom: 1px solid var(--border); }
  .logo { display: flex; align-items: center; gap: .6rem; font-weight: 700; font-size: 1.05rem; }
  .logo-icon { width: 28px; height: 28px; }
  nav a.nav-link { color: var(--muted); font-size: .9rem; }
  nav a.nav-link:hover { color: var(--text); }

  /* Hero */
  .hero { max-width: 760px; margin: 5rem auto 0; padding: 0 1.5rem; text-align: center; }
  .badge { display: inline-block; background: rgba(108,99,255,.15); color: var(--accent);
           border: 1px solid rgba(108,99,255,.35); border-radius: 99px;
           font-size: .78rem; font-weight: 600; letter-spacing: .06em;
           padding: .3rem .85rem; margin-bottom: 1.4rem; text-transform: uppercase; }
  h1 { font-size: clamp(2rem, 5vw, 3.1rem); font-weight: 800; line-height: 1.18;
       letter-spacing: -.02em; margin-bottom: 1.1rem; }
  h1 span { color: var(--accent); }
  .hero p { font-size: 1.1rem; color: var(--muted); max-width: 560px; margin: 0 auto 2.5rem; }

  /* Signup form */
  .signup-box { background: var(--surface); border: 1px solid var(--border);
                border-radius: 14px; padding: 2rem; max-width: 460px; margin: 0 auto 1rem; }
  .signup-box p { font-size: .85rem; color: var(--muted); margin-bottom: 1.1rem; }
  .input-row { display: flex; gap: .6rem; }
  input[type=email] { flex: 1; background: var(--bg); border: 1px solid var(--border);
                      color: var(--text); border-radius: 8px; padding: .65rem 1rem;
                      font-size: .95rem; outline: none; }
  input[type=email]:focus { border-color: var(--accent); }
  input[type=email]::placeholder { color: var(--muted); }
  button[type=submit] { background: var(--accent); color: #fff; border: none; border-radius: 8px;
                        padding: .65rem 1.3rem; font-size: .95rem; font-weight: 600;
                        cursor: pointer; white-space: nowrap; transition: background .15s; }
  button[type=submit]:hover { background: var(--accent-dim); }
  button[type=submit]:disabled { opacity: .55; cursor: default; }
  .form-note { font-size: .78rem; color: var(--muted); text-align: center; margin-top: .7rem; }
  #form-error { color: #f87171; font-size: .85rem; margin-top: .6rem; display: none; }

  /* Pricing table */
  .section { max-width: 860px; margin: 4.5rem auto; padding: 0 1.5rem; }
  .section-title { font-size: 1.4rem; font-weight: 700; margin-bottom: .4rem; }
  .section-sub { color: var(--muted); font-size: .95rem; margin-bottom: 2rem; }
  .price-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem; }
  .price-card { background: var(--surface); border: 1px solid var(--border);
                border-radius: 12px; padding: 1.4rem 1.2rem; min-width: 0; overflow-wrap: break-word; }
  .price-card .endpoint { font-size: .78rem; font-family: 'SF Mono', 'Fira Code', monospace;
                          color: var(--accent); background: rgba(108,99,255,.1);
                          padding: .2rem .55rem; border-radius: 5px; display: block;
                          margin-bottom: .85rem; word-break: break-all; white-space: normal; }
  .price-card .price { font-size: 1.6rem; font-weight: 800; }
  .price-card .per { font-size: .82rem; color: var(--muted); }
  .price-card .desc { font-size: .85rem; color: var(--muted); margin-top: .5rem; }

  /* Code block */
  .code-section { max-width: 860px; margin: 0 auto 4.5rem; padding: 0 1.5rem; }
  pre { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
        padding: 1.4rem 1.6rem; overflow-x: auto; font-family: 'SF Mono','Fira Code',monospace;
        font-size: .82rem; line-height: 1.7; color: #abb2bf; }
  .kw { color: #c678dd; } .str { color: #98c379; } .key { color: #e06c75; }
  .cmt { color: #5c6370; font-style: italic; }

  /* Footer */
  footer { border-top: 1px solid var(--border); text-align: center;
           padding: 2rem; color: var(--muted); font-size: .83rem; }
  footer a { color: var(--muted); }
  footer a:hover { color: var(--text); }
</style>
</head>
<body>

<nav>
  <div class="logo">
    <svg class="logo-icon" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="28" height="28" rx="7" fill="#6c63ff"/>
      <path d="M14 5L7 9v5.5c0 3.6 2.9 6.9 7 8 4.1-1.1 7-4.4 7-8V9L14 5z" fill="white" fill-opacity=".9"/>
    </svg>
    RelayShield API
  </div>
  <a class="nav-link" href="https://relayshield.net">← Back to relayshield.net</a>
</nav>

<!--REFERRER_BANNER-->

<div class="hero">
  <div class="badge">Developer API</div>
  <h1>Security intelligence<br>for <span>developers &amp; agents</span></h1>
  <p>Breach detection, SIM swap monitoring, infostealer exposure, domain lookalike scanning, and live threat intelligence — REST API, no monthly minimum, no commitments.</p>
  <p style="margin-top:.6rem;font-size:.95rem;color:var(--muted)">Unlike leading enterprise threat intelligence platforms that charge per API key <em>and</em> per user seat, RelayShield charges only for the calls you make. One API key, no seat fees, no per-user licensing.</p>

  <!-- AWS Marketplace notice. Wording is deliberately verbatim from the
       UsageInstructions field AWS has already passed in audit — see TODO
       AGENTIC-6. Do not reword without re-reading that note. -->
  <div style="background:rgba(0,181,165,.08);border:1px solid rgba(0,181,165,.35);border-radius:10px;padding:1rem 1.25rem;margin-top:1.5rem;font-size:.9rem;color:var(--text);line-height:1.6">
    <strong style="color:var(--accent2,#00B5A5)">AWS Marketplace subscribers:</strong> your API key is provisioned
    automatically when your subscription activates. No separate account or payment method is required; all billing is
    handled by AWS Marketplace.
  </div>

  <div class="signup-box">
    <p>Enter your email to get started. Your API key arrives by email instantly.</p>
    <form id="signup-form">
      <div class="input-row">
        <input type="email" id="email-input" placeholder="you@company.com" required autocomplete="email">
        <button type="submit" id="submit-btn">Get API key →</button>
      </div>
      <div id="form-error"></div>
    </form>
    <p class="form-note">No monthly minimum · Pay only for calls made · Cancel anytime</p>
  </div>

  <div style="background:rgba(108,99,255,.08);border:1px solid rgba(108,99,255,.25);border-radius:10px;padding:1rem 1.25rem;margin-top:1.25rem;font-size:.9rem;color:var(--text);line-height:1.6">
    <strong style="color:var(--accent)">How billing works:</strong> There is no free tier, but there is no minimum spend either.
    Direct customers add a payment method to activate a key and are billed monthly for calls made. Customers who
    subscribe through AWS Marketplace do not add a payment method &mdash; access is provisioned automatically and all
    billing is handled by AWS.
    A test run of 10 breach checks costs $1.00. Most teams spend $0 in their first week while integrating.
    Threat Intelligence subscriptions ($499/$999/mo) are separate and billed monthly.
  </div>
</div>

<div class="section">
  <div class="section-title">Endpoints &amp; pricing</div>
  <div class="section-sub">Pay only for what you use. Billed monthly. No monthly minimum. Low-volume ad-hoc testing costs pennies — a 10-call integration test runs $0.10–$0.50 total.</div>
  <div class="price-grid">
    <div class="price-card">
      <div class="endpoint">/v1/metered/breach</div>
      <div class="price">$0.10<span class="per"> / call</span></div>
      <div class="desc">Email breach check — breach name, date, and exposed data classes across 13B+ compromised accounts</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/sim-swap</div>
      <div class="price">$0.25<span class="per"> / call</span></div>
      <div class="desc">SIM swap detection via telco carrier lookup database — confirms whether a number has been ported or swapped, with carrier name and swap timestamp</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/infostealer</div>
      <div class="price">$0.50<span class="per"> / call</span></div>
      <div class="desc">Infostealer malware log check — a single infected device exposes every saved password across 50+ services simultaneously: banking credentials, credit card autofill, email, SaaS tools, and active session cookies that bypass 2FA. Returns infection date, OS, malware path, and at-risk service counts</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/domain</div>
      <div class="price">$0.30<span class="per"> / call</span></div>
      <div class="desc">Typosquat domain scan — active lookalikes via DNS + cert transparency</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/oauth-watchlist</div>
      <div class="price">$0.30<span class="per"> / call</span></div>
      <div class="desc">OAuth &amp; token exposure — combines breach history watchlist with live stealer log corpus. Detects stolen credentials and OAuth tokens with category-level severity scores: cloud consoles and code repositories (CRITICAL), identity providers and payment processors (HIGH), productivity SaaS (MEDIUM)</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/supply-chain</div>
      <div class="price">$0.10<span class="per"> / call</span></div>
      <div class="desc">Vendor / supply chain risk — breach exposure + infostealer hits per vendor domain. Up to 10 domains per call. Returns per-domain risk score: CRITICAL · HIGH · MEDIUM · LOW</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/session-risk</div>
      <div class="price">$0.30<span class="per"> / call</span></div>
      <div class="desc">Active session hijack detection — identifies stolen session cookies in criminal stealer log archives before attackers use them. Detects AiTM attacks that bypass 2FA without needing the user&apos;s password. Returns severity-ranked results by service category</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/identity-graph</div>
      <div class="price">$0.35<span class="per"> / call</span></div>
      <div class="desc">Identity correlation — links an email to associated phone numbers and domains seen alongside it in criminal channel dumps. Pivot from one compromised identifier to find all others exposed in the same breach or stealer log</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/ransomware-risk</div>
      <div class="price">$0.40<span class="per"> / call</span></div>
      <div class="desc">Ransomware victim check — queries 100+ active ransomware group leak sites. Returns victim list status, responsible group(s), and count of pre-ransomware credentials found in stealer logs before the incident</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/nhi-exposure</div>
      <div class="price">$0.40<span class="per"> / call</span></div>
      <div class="desc">Non-human identity (NHI) detection — scans stealer log corpus for API keys, tokens, and machine credentials (AWS IAM keys, GitHub PATs, Stripe secrets, private keys, Slack tokens) linked to your domain or vendor supply chain domains</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/secret-scan</div>
      <div class="price">$0.35<span class="per"> / call</span></div>
      <div class="desc">GitHub/GitLab public repo secret detection — searches public code repositories for accidentally committed secrets (API keys, tokens, private keys) associated with a domain. Covers own domain and vendor supply chain domains</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/target-risk</div>
      <div class="price">$0.50<span class="per"> / call</span></div>
      <div class="desc">Target probability scoring — correlates 6 threat signals (ransomware victim listing, stealer log hits, breach exposure, criminal channel mentions, high-EPSS CVEs, pre-ransomware credentials) into a 0–100 risk score with 4-tier rating and recommended action</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/crypto-intel</div>
      <div class="price">$0.30<span class="per"> / call</span></div>
      <div class="desc">Crypto asset surface — wallet address risk, token honeypot &amp; tax flags, NFT contract risk, counterparty screening across EVM, Solana, TON, and Bitcoin</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/asset-intel</div>
      <div class="price">$0.15<span class="per"> / call</span></div>
      <div class="desc">Asset watchlist &amp; continuous monitoring — register domains and IPs for ongoing IOC surveillance. Actions: <code>register</code> assets, <code>sweep</code> all registered assets against 2.1M+ IOC corpus, <code>list</code> or <code>remove</code>. Webhook push alerts fire automatically when new IOCs match your registered assets</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/threat-actor</div>
      <div class="price">$0.30<span class="per"> / call</span></div>
      <div class="desc">Threat actor intelligence — two actions in one endpoint. <code>exploit-chatter</code>: detect pre-publication CVE PoC discussion in criminal channels before NVD/KEV publication, with EPSS score and KEV status. <code>actor-lookup</code>: track a threat actor or malware campaign (e.g. LummaC2, APT29) — returns IOC count, IOC breakdown by type, MITRE ATT&amp;CK group info, aliases, and techniques</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/cve-identity-risk</div>
      <div class="price">$0.40<span class="per"> / call</span></div>
      <div class="desc">CVE × identity risk correlation — pass a CVE ID and domain to get a composite risk score (0–100) combining CISA KEV status, EPSS exploitation probability, infostealer corpus hits for exploiting malware families, ransomware victim listing, and exploit chatter signals. The only API that closes the loop from vulnerability to live identity exposure for a specific organization</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/identity-risk-score</div>
      <div class="price">$0.35<span class="per"> / call</span></div>
      <div class="desc">Domain identity risk score — a security credit score (0–100, grade A–F) for any domain across 6 dimensions: breach exposure, infostealer density, IOC corpus presence, ransomware victim listing, active session exposure, and CVE exposure. MSPs can embed this in client QBRs, insurance renewal reports, and onboarding risk assessments</div>
    </div>
    <p style="margin:1.5rem 0 .75rem;padding:.9rem 1.1rem;background:rgba(108,99,255,.07);border:1px solid rgba(108,99,255,.2);border-radius:8px;font-size:.9rem;color:var(--muted)">
      <strong style="color:var(--accent)">🤗 Try the Agentic Attack Surface live on Hugging Face</strong> — no signup required to explore the MCP schema.
      <a href="https://huggingface.co/spaces/relayshieldadmin/relayshield-agentic-attack-surface" target="_blank" rel="noopener" style="color:var(--accent)">Space</a>
      · <a href="https://huggingface.co/blog/relayshieldadmin/relayshield-agentic-attack-surface-mcp" target="_blank" rel="noopener" style="color:var(--accent)">announcement post</a>
    </p>
    <div class="price-card" id="ep-tech-stack-cve">
      <div class="endpoint">/v1/metered/tech-stack-cve</div>
      <div class="price">$0.20<span class="per"> / call</span></div>
      <div class="desc">Agent framework &amp; tech stack exploit monitoring — pass a declared tech stack (or a domain to pull its stored stack) and get back CISA KEV / high-EPSS CVEs actively targeting it. Covers AI agent orchestration frameworks (Langflow, LangChain, AutoGPT, CrewAI, Flowise, n8n self-hosted) and their common companion infrastructure (Nacos, MinIO) — the exact vector used in the first documented autonomous-AI-agent ransomware operation (JadePuffer, July 2026)</div>
    </div>
    <div class="price-card" id="ep-mcp-registry-risk">
      <div class="endpoint">/v1/metered/mcp-registry-risk</div>
      <div class="price">$0.35<span class="per"> / call</span></div>
      <div class="desc">MCP server &amp; agent-tool registry reputation — checks an MCP server URL or package name against RelayShield's criminal IOC corpus, typosquat/near-miss detection against well-known MCP domains, and domain registration age. Early-mover coverage for the MCP ecosystem, where dedicated security tooling is still minimal industry-wide</div>
    </div>
    <div class="price-card" id="ep-prompt-injection-breach">
      <div class="endpoint">/v1/metered/prompt-injection-breach</div>
      <div class="price">$0.35<span class="per"> / call</span></div>
      <div class="desc">Prompt-injection-sourced breach detection — flags stolen session/credential exposure whose source dump text suggests an AI agent (rather than a traditional phishing/malware campaign) was involved in obtaining it. A best-effort signal based on how the breach was described, not a confirmed attribution</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/bulk-ioc</div>
      <div class="price">$0.50<span class="per"> / batch (up to 100 IOCs)</span></div>
      <div class="desc">Bulk IOC enrichment — submit up to 100 indicators in a single call. Built for SIEM log-enrichment pipelines. Returns malware family, threat actor, confidence score, and first/last seen for each indicator</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/ioc-pivot</div>
      <div class="price">$0.20<span class="per"> / call</span></div>
      <div class="desc">IOC pivot — given one known-malicious indicator, discover all related infrastructure sharing the same malware family. Surfaces full C2 networks from a single indicator</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/brand-monitor</div>
      <div class="price">$0.35<span class="per"> / call</span></div>
      <div class="desc">Brand monitoring — scans the full IOC corpus for your brand name. Returns phishing domains, malware C2 infrastructure referencing your name, dark web mentions, and image/logo mentions extracted via OCR from infostealer-archive screenshots</div>
    </div>
    <div class="price-card" id="ep-card-exposure">
      <div class="endpoint">/v1/metered/card-exposure</div>
      <div class="price">$0.30<span class="per"> / call</span></div>
      <div class="desc">Stolen payment card exposure check — pass a client-computed SHA-256 hash of a card number, or just a 6-8 digit BIN, to check against RelayShield's stolen-card corpus (sourced from infostealer logs). RelayShield never accepts or stores a raw card number</div>
    </div>
    <div class="price-card" id="ep-bulk-identity-risk">
      <div class="endpoint">/v1/metered/bulk-identity-risk</div>
      <div class="price">$2.00<span class="per"> / call</span></div>
      <div class="desc">Hierarchical org + agent-level risk scoring — up to 10 organizational domains plus up to 5 agent/service-account identities per domain in a single call. Each domain returns a 0–100 risk score across 6 dimensions; each agent identity returns breach, infostealer, and stolen-session signals. A critically exposed agent automatically elevates the organizational risk rating. Purpose-built for MSP weekly client sweeps and AI agent governance use cases</div>
    </div>
    <div class="price-card" id="ep-cert-expiry">
      <div class="endpoint">/v1/metered/cert-expiry</div>
      <div class="price">$0.05<span class="per"> / call</span></div>
      <div class="desc">TLS certificate expiry &amp; renewal risk — checks Certificate Transparency logs for how many days remain before a domain&apos;s live certificate expires. Returns a 4-tier risk level (CRITICAL/HIGH/MEDIUM/LOW) and a plain-English recommendation. Increasingly relevant as CA/Browser Forum rules shrink standard certificate lifespans toward 47 days by 2029</div>
    </div>
    <div class="price-card" id="ep-ip-intel">
      <div class="endpoint">/v1/metered/ip-intel</div>
      <div class="price">$0.10<span class="per"> / call</span></div>
      <div class="desc">Passive DNS &amp; IP reputation — pass a domain to get its historical IP resolution history plus reputation, or pass an IP to get reverse resolution history (hostnames that have pointed to it), AS owner, country, and malicious/suspicious vendor detection counts</div>
    </div>
  </div>
</div>

<div class="section" style="margin-top:2rem">
  <div class="section-title">Threat Intelligence API <span style="background:var(--accent);color:#fff;font-size:.7rem;padding:.15rem .5rem;border-radius:4px;margin-left:.5rem;vertical-align:middle">NEW</span></div>
  <p style="color:var(--muted);font-size:.95rem;margin:.5rem 0 1.25rem">RelayShield&apos;s edge is OSINT threat hunting most vendors can&apos;t reach — our own collection pipeline runs continuous, verified monitoring across <strong>83+ active criminal Telegram channels</strong> (infostealer markets, credential dumps, breach announcements), not a static feed subscription. That&apos;s layered with <strong>4.4M+ indicators</strong> aggregated from <strong>17 authoritative external sources</strong> (abuse.ch, Spamhaus, AbuseIPDB, AlienVault OTX, PhishTank, CISA KEV, MITRE ATT&amp;CK/ATLAS, and more). Emails, domains, IPs, hashes, phone numbers, and wallet addresses — <strong>24–72 hours ahead of public breach databases.</strong></p>
  <p style="color:var(--muted);font-size:.9rem;margin:.5rem 0 1.25rem;background:rgba(108,99,255,.07);border:1px solid rgba(108,99,255,.2);border-radius:8px;padding:.75rem 1rem"><strong style="color:var(--accent)">All 26 metered endpoints included.</strong> Both TI subscription tiers cover unlimited access to all metered API endpoints above — breach, SIM swap, infostealer, domain, OAuth &amp; token exposure, supply chain, session hijack detection, crypto asset surface, asset intel monitoring, threat actor intelligence, CVE × identity risk correlation, domain identity risk scoring, bulk IOC enrichment, IOC pivot, brand monitoring, bulk identity risk, agent framework exploit monitoring, MCP registry risk, prompt-injection breach detection, certificate expiry risk, and passive DNS/IP reputation — in addition to the Threat Intelligence IOC and CVE feeds. No per-endpoint add-ons. One subscription, full access.</p>
  <table style="width:100%;border-collapse:collapse;font-size:.88rem;margin-bottom:1.5rem">
    <thead>
      <tr style="border-bottom:1px solid var(--border)">
        <th style="text-align:left;padding:.5rem .75rem;color:var(--muted);font-weight:600"></th>
        <th style="text-align:center;padding:.5rem .75rem;color:var(--accent);font-weight:700">MSP — $499/mo</th>
        <th style="text-align:center;padding:.5rem .75rem;color:var(--accent);font-weight:700">MSSP — $999/mo</th>
      </tr>
    </thead>
    <tbody style="color:var(--text)">
      <tr style="border-bottom:1px solid var(--border)">
        <td style="padding:.45rem .75rem">Calls / month</td>
        <td style="text-align:center;padding:.45rem .75rem">10,000</td>
        <td style="text-align:center;padding:.45rem .75rem"><strong>Unlimited</strong></td>
      </tr>
      <tr style="border-bottom:1px solid var(--border)">
        <td style="padding:.45rem .75rem">IOC types</td>
        <td style="text-align:center;padding:.45rem .75rem" colspan="2">Email · Phone · Domain · Wallet</td>
      </tr>
      <tr style="border-bottom:1px solid var(--border)">
        <td style="padding:.45rem .75rem">Intel sources</td>
        <td style="text-align:center;padding:.45rem .75rem" colspan="2">Criminal Telegram channels, ThreatFox, URLhaus, CISA KEV, Feodo Tracker, AbuseIPDB, MalwareBazaar, PhishTank, Emerging Threats, AlienVault OTX</td>
      </tr>
      <tr style="border-bottom:1px solid var(--border)">
        <td style="padding:.45rem .75rem">Lead time vs HIBP</td>
        <td style="text-align:center;padding:.45rem .75rem" colspan="2">24–72 hours</td>
      </tr>
      <tr style="border-bottom:1px solid var(--border)">
        <td style="padding:.45rem .75rem">Rate limit</td>
        <td style="text-align:center;padding:.45rem .75rem">~333 calls/day</td>
        <td style="text-align:center;padding:.45rem .75rem">None</td>
      </tr>
      <tr style="border-bottom:1px solid var(--border)">
        <td style="padding:.45rem .75rem">Support</td>
        <td style="text-align:center;padding:.45rem .75rem">Standard email</td>
        <td style="text-align:center;padding:.45rem .75rem"><strong>Priority + SLA</strong></td>
      </tr>
      <tr>
        <td style="padding:.45rem .75rem">Best for</td>
        <td style="text-align:center;padding:.45rem .75rem">SOC teams, SOAR playbooks, incident response</td>
        <td style="text-align:center;padding:.45rem .75rem">MSSPs with continuous multi-client monitoring</td>
      </tr>
    </tbody>
  </table>
  <div class="price-grid" style="grid-template-columns: repeat(auto-fit, minmax(220px, 1fr))">
    <div class="price-card" style="border-color:var(--accent)">
      <div class="endpoint" style="color:var(--accent)">/v1/intel/telegram</div>
      <div class="price">$499<span class="per"> / mo</span></div>
      <div class="desc">In-house SOC teams — up to 10,000 calls/month across all endpoints. Includes IOC lookup, CVE intelligence, and all 8 metered endpoints. Embed in SOAR playbooks, SIEM enrichment, or incident response workflows.</div>
      <a href="https://buy.stripe.com/28EcN66Umb1be56bgb0Ny0e" style="display:block;margin-top:1rem;background:var(--accent);color:#fff;text-align:center;padding:.5rem;border-radius:6px;text-decoration:none;font-size:.85rem;font-weight:600">Subscribe — $499/mo</a>
    </div>
    <div class="price-card" style="border-color:var(--accent)">
      <div class="endpoint" style="color:var(--accent)">/v1/intel/telegram</div>
      <div class="price">$999<span class="per"> / mo</span></div>
      <div class="desc">MSSPs &amp; MDRs — unlimited calls across all endpoints, priority support + SLA. Includes IOC lookup, CVE intelligence, and all 8 metered endpoints. For teams running continuous enrichment pipelines across multiple client environments.</div>
      <a href="https://buy.stripe.com/4gM3cw1A23yJf9a2JF0Ny0f" style="display:block;margin-top:1rem;background:var(--accent);color:#fff;text-align:center;padding:.5rem;border-radius:6px;text-decoration:none;font-size:.85rem;font-weight:600">Subscribe — $999/mo</a>
    </div>
  </div>

  <div style="margin-top:2rem">
    <div class="section-title">LLMjacking Detection License <span style="background:var(--accent);color:#fff;font-size:.7rem;padding:.15rem .5rem;border-radius:4px;margin-left:.5rem;vertical-align:middle">NEW</span></div>
    <p style="color:var(--muted);font-size:.95rem;margin:.5rem 0 1.25rem">Stolen LLM API keys drain a company&apos;s AI budget, not its data &mdash; real incidents have run $46K/day to $500K/month from a single leaked key, while the underground price for a stolen key is about $30. <code>llm-credential-exposure</code> scans our criminal stealer-log corpus for exposed keys across <strong>14 LLM and AI providers</strong> tied to your domain: OpenAI, Anthropic Claude, Google Gemini, xAI Grok, Amazon Bedrock, Groq, Replicate, LangSmith, Hugging Face, NVIDIA NIM, DeepSeek, Moonshot Kimi, Alibaba Qwen and Alibaba Cloud. Available pay-per-call at $0.40 on any metered key, or as a dedicated unlimited-call license below.</p>
    <div style="background:var(--surface);border:1px solid var(--accent);border-radius:8px;padding:.85rem 1rem;margin:0 0 1.25rem;font-size:.85rem">
      <strong style="color:var(--accent)">Coverage standard secret scanners miss.</strong> <span style="color:var(--muted)">Gitleaks &mdash; the most widely deployed open-source secret scanner &mdash; ships <strong>zero</strong> detection rules for DeepSeek, Moonshot, Qwen or NVIDIA. Shadow-AI keys from those providers are invisible to conventional scanning. And a single leaked Hugging Face token bills against DeepSeek, Qwen, Kimi and NVIDIA models through Inference Providers without the attacker ever holding a vendor key. We are not scanning your repos for keys you might leak &mdash; we scan the criminal channels where leaked keys are already being sold.</span>
    </div>
    <div class="price-grid" style="grid-template-columns: repeat(auto-fit, minmax(220px, 1fr))">
      <div class="price-card" style="border-color:var(--accent)">
        <div class="endpoint" style="color:var(--accent)">/v1/metered/llm-credential-exposure</div>
        <div class="price">$39<span class="per"> / mo</span></div>
        <div class="desc">Unlimited calls to the LLMjacking detection endpoint — no per-call metering, no other endpoints included. Auto-provisions or upgrades your existing API key.</div>
        <a href="https://buy.stripe.com/9B600k92u2uFgde0Bx0Ny0i" style="display:block;margin-top:1rem;background:var(--accent);color:#fff;text-align:center;padding:.5rem;border-radius:6px;text-decoration:none;font-size:.85rem;font-weight:600">Subscribe — $39/mo</a>
      </div>
      <div class="price-card" style="border-color:var(--accent)">
        <div class="endpoint" style="color:var(--accent)">/v1/metered/llm-credential-exposure</div>
        <div class="price">$399<span class="per"> / yr</span></div>
        <div class="desc">Same unlimited-call license, billed annually — just under 2 months free vs. paying monthly.</div>
        <a href="https://buy.stripe.com/fZu4gA4Mec5f3qs4RN0Ny0j" style="display:block;margin-top:1rem;background:var(--accent);color:#fff;text-align:center;padding:.5rem;border-radius:6px;text-decoration:none;font-size:.85rem;font-weight:600">Subscribe — $399/yr</a>
      </div>
    </div>
  </div>

  <div style="margin-top:2rem">
    <div class="section-title" style="font-size:1rem;margin-bottom:.75rem">CVE &amp; Ransomware Intelligence</div>
    <p style="color:var(--muted);font-size:.9rem;margin-bottom:1rem">Look up CISA Known Exploited Vulnerabilities by CVE ID or keyword — cross-referenced for active ransomware campaign activity. Included on all TI subscription tiers.</p>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;font-size:.85rem">
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem">
        <div style="font-family:monospace;color:var(--accent);margin-bottom:.5rem">POST /v1/intel/cve</div>
        <div style="color:var(--muted);margin-bottom:.75rem">Exact CVE ID lookup</div>
        <pre style="background:var(--bg);border-radius:6px;padding:.75rem;font-size:.78rem;overflow-x:auto"><span class="str">{"cve_id": "CVE-2024-1234"}</span></pre>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem">
        <div style="font-family:monospace;color:var(--accent);margin-bottom:.5rem">POST /v1/intel/cve</div>
        <div style="color:var(--muted);margin-bottom:.75rem">Keyword scan — vendor, product, or CVE name</div>
        <pre style="background:var(--bg);border-radius:6px;padding:.75rem;font-size:.78rem;overflow-x:auto"><span class="str">{"keyword": "apache"}</span></pre>
      </div>
    </div>
    <div style="margin-top:.75rem;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem;font-size:.83rem;color:var(--muted)">
      <strong style="color:var(--text)">Response includes:</strong> CVE ID · vendor/product · vulnerability name · date added to KEV ·
      <span style="color:#f87171;font-weight:600">ransomware_campaign_use</span> flag · known ransomware groups
    </div>
  </div>

  <div style="margin-top:2rem">
    <div class="section-title" style="font-size:1rem;margin-bottom:.75rem">Automated Feed Formats — STIX/TAXII, MISP &amp; SIEM/SOAR Push</div>
    <p style="color:var(--muted);font-size:.9rem;margin-bottom:1rem">Pull our IOC corpus with your SIEM's built-in TAXII client or MISP instance — no custom integration work, both require a TI subscription and support incremental pulls via <code>added_after</code> + pagination. Or configure a destination once and have real-time findings pushed to you as they fire.</p>
    <div style="background:var(--surface);border:1px solid var(--accent);border-radius:8px;padding:.85rem 1rem;margin-bottom:1rem;font-size:.85rem">
      <strong style="color:var(--accent)">Elastic Security users:</strong> <span style="color:var(--muted)">RelayShield works with Elastic's built-in <em>Custom Threat Intelligence</em> integration (switch on <em>Enable TAXII 2.1</em>) or its <em>MISP</em> integration &mdash; configuration only, no connector to build. Point it at <code>https://api.relayshield.net/v1/intel/taxii/collections/iocs/objects/</code> with <code>Authorization: Bearer YOUR_API_KEY</code>. <a href="https://blog.relayshield.net/elastic-security-threat-intelligence-integration" style="color:var(--accent)">Full step-by-step guide &rarr;</a></span>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem;font-size:.85rem">
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem">
        <div style="font-family:monospace;color:var(--accent);margin-bottom:.5rem">GET /v1/intel/taxii/*</div>
        <div style="color:var(--muted)">STIX 2.1 compliant feed — Indicator objects for Splunk, Sentinel, Elastic, or QRadar's built-in TAXII client.</div>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem">
        <div style="font-family:monospace;color:var(--accent);margin-bottom:.5rem">GET /v1/intel/misp/event</div>
        <div style="color:var(--muted)">Native MISP Event JSON with tagged Attributes — the default/co-primary format for government, CERT/ISAC, and mid-market SOC tooling that STIX-only integration doesn't reach.</div>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem">
        <div style="font-family:monospace;color:var(--accent);margin-bottom:.5rem">POST /v1/siem/configure</div>
        <div style="color:var(--muted)">Push delivery to Splunk HEC, CEF/QRadar, or Cortex XSOAR's Generic Webhook incident-creation shape — configure a destination once, then real-time findings from breach, domain, infostealer, SIM swap, OAuth, and dark-web-channel monitoring dispatch automatically, no polling required.</div>
      </div>
    </div>
  </div>

  <div style="margin-top:2rem">
    <div class="section-title" style="font-size:1rem;margin-bottom:.75rem">Shareable Report Links</div>
    <p style="color:var(--muted);font-size:.9rem;margin-bottom:1rem">Turn any wallet scan, domain check, or vendor sweep result into a persistent, shareable URL. Generation requires a subscription; viewing the resulting link is public with no login required — paste it into a client ticket or incident report.</p>
    <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem;font-size:.85rem">
      <div style="font-family:monospace;color:var(--accent);margin-bottom:.5rem">POST /v1/report/share</div>
      <div style="color:var(--muted)">Returns a <code>report_id</code> and public <code>share_url</code> for the summary you submit.</div>
    </div>
  </div>
</div>

<div class="code-section">
  <div class="section-title" style="margin-bottom:1rem">Quick start</div>
<pre><span class="cmt"># Breach check</span>
curl -X POST https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod/v1/metered/breach \\
  -H <span class="str">"X-RS-API-KEY: rs_live_your_key_here"</span> \\
  -H <span class="str">"Content-Type: application/json"</span> \\
  -d <span class="str">'{"email": "user@example.com"}'</span>

<span class="cmt"># Response</span>
{
  <span class="key">"ok"</span>: <span class="kw">true</span>,
  <span class="key">"data"</span>: {
    <span class="key">"email"</span>: <span class="str">"user@example.com"</span>,
    <span class="key">"breach_count"</span>: 3,
    <span class="key">"breaches"</span>: [{ <span class="key">"name"</span>: <span class="str">"LinkedIn"</span>, <span class="key">"breach_date"</span>: <span class="str">"2021-06-22"</span>, ... }]
  }
}</pre>

  <div class="section-title" style="margin-top:2rem;margin-bottom:.5rem">Python sample — breach + infostealer in sequence</div>
  <p style="color:var(--muted);font-size:.88rem;margin-bottom:.75rem">Copy-paste to run immediately. No SDK required — standard library only.</p>
<pre><span class="cmt">import urllib.request, json</span>

API_KEY = <span class="str">"rs_live_your_key_here"</span>
BASE    = <span class="str">"https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod"</span>

<span class="kw">def</span> <span class="fn">rs_post</span>(path, payload):
    data = json.dumps(payload).encode()
    req  = urllib.request.Request(
        f<span class="str">"{BASE}{path}"</span>,
        data=data,
        headers={<span class="str">"Content-Type"</span>: <span class="str">"application/json"</span>, <span class="str">"X-RS-API-KEY"</span>: API_KEY},
    )
    <span class="kw">with</span> urllib.request.urlopen(req, timeout=10) <span class="kw">as</span> r:
        <span class="kw">return</span> json.loads(r.read())

email  = <span class="str">"user@example.com"</span>
breach = rs_post(<span class="str">"/v1/metered/breach"</span>, {<span class="str">"email"</span>: email})
print(f<span class="str">"Breaches: {breach.get('breach_count', 0)}"</span>)

<span class="kw">if</span> breach.get(<span class="str">"breach_count"</span>, 0) &gt; 0:
    stealer = rs_post(<span class="str">"/v1/metered/infostealer"</span>, {<span class="str">"email"</span>: email})
    print(f<span class="str">"Infostealer exposure: {stealer.get('exposed', False)}"</span>)
    <span class="kw">if</span> stealer.get(<span class="str">"exposed"</span>):
        print(f<span class="str">"  Markets: {stealer.get('markets', [])}"</span>)
        print(<span class="str">"  ACTION: credential reset + session revocation"</span>)</pre>
</div>

<div style="background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.5rem 1.75rem;margin:2rem 0">
  <div class="section-title" style="font-size:1.2rem;margin:0 0 1rem">Agent framework SDKs</div>
  <p style="color:var(--muted);font-size:.88rem;margin-bottom:1rem">MCP registry-risk and prompt-injection-breach checks, plus a mandatory pre-execution gate, packaged natively for the agent frameworks you're already building on.</p>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.85rem">
    <a href="https://github.com/nzdsf2-gif/openai-agents-relayshield" target="_blank" rel="noopener" style="text-decoration:none;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:1rem">
      <p style="color:var(--text);font-size:.9rem;font-weight:600;margin:0 0 .35rem">OpenAI Agents SDK</p>
      <code style="display:block;color:var(--muted);font-size:.8rem;background:var(--surface);border-radius:5px;padding:.4rem .55rem;margin-bottom:.5rem">pip install openai-agents-relayshield</code>
      <span style="color:var(--accent);font-size:.82rem;font-weight:600">View on GitHub &rarr;</span>
    </a>
    <a href="https://github.com/nzdsf2-gif/langchain-relayshield" target="_blank" rel="noopener" style="text-decoration:none;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:1rem">
      <p style="color:var(--text);font-size:.9rem;font-weight:600;margin:0 0 .35rem">LangChain</p>
      <code style="display:block;color:var(--muted);font-size:.8rem;background:var(--surface);border-radius:5px;padding:.4rem .55rem;margin-bottom:.5rem">pip install langchain-relayshield</code>
      <span style="color:var(--accent);font-size:.82rem;font-weight:600">View on GitHub &rarr;</span>
    </a>
    <a href="https://github.com/nzdsf2-gif/ai-sdk-relayshield" target="_blank" rel="noopener" style="text-decoration:none;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:1rem">
      <p style="color:var(--text);font-size:.9rem;font-weight:600;margin:0 0 .35rem">Vercel AI SDK</p>
      <code style="display:block;color:var(--muted);font-size:.8rem;background:var(--surface);border-radius:5px;padding:.4rem .55rem;margin-bottom:.5rem">npm install ai-sdk-relayshield</code>
      <span style="color:var(--accent);font-size:.82rem;font-weight:600">View on GitHub &rarr;</span>
    </a>
    <a href="https://github.com/nzdsf2-gif/llamaindex-relayshield" target="_blank" rel="noopener" style="text-decoration:none;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:1rem">
      <p style="color:var(--text);font-size:.9rem;font-weight:600;margin:0 0 .35rem">LlamaIndex</p>
      <code style="display:block;color:var(--muted);font-size:.8rem;background:var(--surface);border-radius:5px;padding:.4rem .55rem;margin-bottom:.5rem">pip install llamaindex-relayshield</code>
      <span style="color:var(--accent);font-size:.82rem;font-weight:600">View on GitHub &rarr;</span>
    </a>
  </div>
</div>

<div style="background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.5rem 1.75rem;margin:2rem 0">
  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.6rem;margin-bottom:1rem">
    <div class="section-title" style="font-size:1.2rem;margin:0">What practitioners are building</div>
    <div style="display:flex;align-items:center;gap:.4rem;background:rgba(255,109,90,.12);border:1px solid rgba(255,109,90,.3);border-radius:20px;padding:.35rem .8rem">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="5" cy="12" r="3" fill="#FF6D5A"/>
        <circle cx="19" cy="6" r="3" fill="#FF6D5A"/>
        <circle cx="19" cy="18" r="3" fill="#FF6D5A"/>
        <path d="M8 12h8M13 9l4-2M13 15l4 2" stroke="#FF6D5A" stroke-width="1.6" stroke-linecap="round"/>
      </svg>
      <span style="font-size:.82rem;font-weight:700;color:#FF6D5A">n8n</span>
    </div>
  </div>
  <p style="color:var(--muted);font-size:.82rem;margin:0 0 1rem">
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="vertical-align:-2px;margin-right:.3rem">
      <path d="M9 12l2 2 4-4" stroke="#22c55e" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="12" cy="12" r="10" stroke="#22c55e" stroke-width="1.6"/>
    </svg>
    <code style="background:var(--bg);border-radius:4px;padding:.1rem .4rem">n8n-nodes-relayshield</code> is verified and available directly on n8n Cloud — search for it on the canvas, no manual install needed.
  </p>
  <a href="https://creators.n8n.io/workflows/17255" target="_blank" rel="noopener" style="display:flex;align-items:center;gap:.9rem;text-decoration:none;background:rgba(255,109,90,.08);border:1px solid rgba(255,109,90,.25);border-radius:8px;padding:.85rem 1rem;margin-bottom:1rem">
    <div style="flex:1;min-width:0">
      <p style="color:var(--text);font-size:.9rem;font-weight:600;margin:0 0 .2rem">Featured in n8n&apos;s official template gallery</p>
      <p style="color:var(--muted);font-size:.82rem;margin:0">&ldquo;Check new-hire identity risk and provision Google Workspace accounts with RelayShield&rdquo; — HR webhook → parallel breach/infostealer checks → Google Workspace provisioning → Notion + Slack. creators.n8n.io/workflows/17255</p>
    </div>
    <span style="color:var(--accent);font-size:.82rem;font-weight:600;white-space:nowrap">View template &rarr;</span>
  </a>
  <div style="border-left:3px solid var(--accent);padding-left:1rem;margin-bottom:1rem">
    <p style="color:var(--text);font-size:.95rem;margin:0 0 .4rem">&ldquo;Nice work! You could extend this to trigger when an employee is deactivated in your HR system — run breach + infostealer checks on offboarding, then log to Notion or alert Slack if their credentials are circulating.&rdquo;</p>
    <p style="color:var(--muted);font-size:.82rem;margin:0">— n8n community member, on the RelayShield breach monitoring workflow template</p>
  </div>
  <p style="color:var(--muted);font-size:.85rem;margin:0">Used in SOAR playbooks, SIEM enrichment pipelines, MSP onboarding/offboarding automations, and incident response triage workflows. <a href="mailto:support@relayshield.net" style="color:var(--accent)">Tell us what you&apos;re building.</a></p>
</div>

<footer>
  <p>RelayShield LLC · <a href="https://relayshield.net">relayshield.net</a> · <a href="mailto:support@relayshield.net">support@relayshield.net</a></p>
  <p style="margin-top:.6rem">
    <a href="https://x402-list.com/services/relayshield?utm_source=badge&amp;utm_medium=referral&amp;utm_campaign=embed" target="_blank" rel="noopener">
      <img src="https://x402-list.com/badge/relayshield.svg?data=uptime&amp;period=30d" alt="RelayShield on x402-list.com — continuously monitored" style="height:20px;vertical-align:middle" />
    </a>
  </p>
</footer>

<script>
document.getElementById('signup-form').addEventListener('submit', async function(e) {
  e.preventDefault();
  const email = document.getElementById('email-input').value.trim();
  const btn   = document.getElementById('submit-btn');
  const err   = document.getElementById('form-error');
  err.style.display = 'none';
  btn.disabled = true;
  btn.textContent = 'Redirecting…';
  try {
    const source = new URLSearchParams(window.location.search).get('source') || 'direct';
    const res  = await fetch('/developer/signup', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({email, source})
    });
    const data = await res.json();
    if (data.ok && data.data.checkout_url) {
      window.location.href = data.data.checkout_url;
    } else {
      throw new Error(data.error || 'Something went wrong');
    }
  } catch(ex) {
    err.textContent = ex.message;
    err.style.display = 'block';
    btn.disabled = false;
    btn.textContent = 'Get API key →';
  }
});
</script>
</body>
</html>"""


SUCCESS_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>You're set — RelayShield API</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0d0f14; --surface: #161a23; --border: #242836;
    --accent: #6c63ff; --green: #22c55e; --text: #e8eaf0; --muted: #8b91a8;
    --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  }
  body { background: var(--bg); color: var(--text); font-family: var(--font);
         min-height: 100vh; display: flex; align-items: center; justify-content: center; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 18px;
          padding: 3rem 2.5rem; max-width: 500px; width: 90%; text-align: center; }
  .icon { width: 60px; height: 60px; background: rgba(34,197,94,.15);
          border-radius: 50%; display: flex; align-items: center; justify-content: center;
          margin: 0 auto 1.5rem; }
  .icon svg { width: 28px; height: 28px; }
  h1 { font-size: 1.7rem; font-weight: 800; margin-bottom: .6rem; }
  .sub { color: var(--muted); font-size: 1rem; margin-bottom: 2rem; line-height: 1.5; }
  .info-box { background: var(--bg); border: 1px solid var(--border); border-radius: 10px;
              padding: 1.2rem 1.4rem; text-align: left; margin-bottom: 1.5rem; }
  .info-box p { font-size: .85rem; color: var(--muted); margin-bottom: .3rem; }
  .info-box code { font-family: 'SF Mono','Fira Code',monospace; color: var(--accent);
                   font-size: .82rem; }
  .endpoints { text-align: left; margin-bottom: 2rem; }
  .endpoints p { font-size: .83rem; color: var(--muted); margin-bottom: .8rem; }
  .ep { font-family: 'SF Mono','Fira Code',monospace; font-size: .78rem;
        color: #abb2bf; line-height: 1.9; }
  .btn { display: inline-block; background: var(--accent); color: #fff; border-radius: 9px;
         padding: .7rem 1.6rem; font-weight: 600; font-size: .95rem; text-decoration: none; }
  .btn:hover { opacity: .88; }
  .footer-note { font-size: .78rem; color: var(--muted); margin-top: 1.2rem; }
</style>
</head>
<body>
<div class="card">
  <div class="icon">
    <svg viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2.5"
         stroke-linecap="round" stroke-linejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  </div>
  <h1>You're all set</h1>
  <p class="sub">Your API key is on its way. Check your inbox — it usually arrives within 30 seconds.</p>

  <div class="info-box">
    <p>Use this header on every request:</p>
    <code>X-RS-API-KEY: rs_live_your_key</code>
  </div>

  <div class="endpoints">
    <p>Your endpoints:</p>
    <div class="ep">
      POST /v1/metered/breach<br>
      POST /v1/metered/sim-swap<br>
      POST /v1/metered/infostealer<br>
      POST /v1/metered/domain
    </div>
  </div>

  <a class="btn" href="https://api.relayshield.net/developers">Back to docs</a>
  <p class="footer-note">Questions? <a href="mailto:support@relayshield.net" style="color:var(--muted)">support@relayshield.net</a></p>
</div>
</body>
</html>"""


def handle_topup(body: dict) -> dict:
    """Create a one-time Stripe Checkout session for a credit pack."""
    api_key_str = (body.get("api_key") or "").strip()
    pack_index  = int(body.get("pack") or 0)

    if not api_key_str or not api_key_str.startswith("rs_live_"):
        return _err("api_key is required (your rs_live_... key)")
    if pack_index not in (0, 1, 2):
        return _err("pack must be 0 ($25), 1 ($50), or 2 ($100)")

    pack = CREDIT_PACKS[pack_index]

    # Look up existing customer_id so Stripe pre-fills their email
    table  = dynamodb.Table(API_KEYS_TABLE)
    record = table.get_item(Key={"api_key": api_key_str}).get("Item")
    if not record or not record.get("active"):
        return _err("API key not found or inactive", 404)

    customer_id = record.get("stripe_customer_id", "")

    session_params: dict = {
        "mode":                      "payment",
        "line_items[0][price]":      pack["price_id"],
        "line_items[0][quantity]":   "1",
        "success_url":               TOPUP_SUCCESS_URL,
        "cancel_url":                CANCEL_URL,
        "metadata[api_key]":         api_key_str,
        "metadata[credits]":         str(pack["credits"]),
        "metadata[checkout_type]":   "topup",
    }
    if customer_id:
        session_params["customer"] = customer_id

    try:
        session = _stripe_post("/checkout/sessions", session_params)
    except Exception as exc:
        logger.error("Stripe topup checkout failed key=%s error=%s", api_key_str[:16], exc)
        return _err("could not create checkout session", 502)

    logger.info("topup checkout created key=%s pack=$%d", api_key_str[:16], pack["dollars"])
    return _ok({"checkout_url": session["url"]})


def _add_credits(api_key_str: str, credits: int) -> None:
    """Add credits to an existing API key record."""
    dynamodb.Table(API_KEYS_TABLE).update_item(
        Key={"api_key": api_key_str},
        UpdateExpression="SET credit_balance = if_not_exists(credit_balance, :zero) + :credits",
        ExpressionAttributeValues={":credits": credits, ":zero": 0},
    )
    logger.info("credits added key=%s credits=%d", api_key_str[:16], credits)


_LANGCHAIN_BANNER = """
<div style="background:var(--surface);border:1px solid var(--accent);border-radius:10px;padding:1.25rem 1.5rem;margin:1.5rem 0 0">
  <p style="color:var(--accent);font-size:.78rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;margin:0 0 .5rem">Arriving from the LangChain docs</p>
  <p style="color:var(--text);font-size:.95rem;margin:0 0 .9rem"><code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">langchain-relayshield</code> adds a mandatory pre-execution gate that blocks <code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">connect_mcp_server</code> and <code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">install_mcp_package</code> tool calls when RelayShield reports risk. Two minutes to wire in:</p>
  <pre style="background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:.9rem 1rem;overflow-x:auto;margin:0 0 .9rem;font-size:.82rem;line-height:1.55"><code>pip install langchain-relayshield

from langchain_relayshield import RelayShieldGate

gate = RelayShieldGate(api_key=RELAYSHIELD_API_KEY)
agent = create_agent(model, tools=tools, middleware=[gate])</code></pre>
  <p style="color:var(--muted);font-size:.85rem;margin:0">Need a key first? <a href="#get-started" style="color:var(--accent);font-weight:600">Grab one below</a> &mdash; pay per call, no monthly minimum. Or <a href="https://github.com/nzdsf2-gif/langchain-relayshield" target="_blank" rel="noopener" style="color:var(--accent);font-weight:600">read the integration source</a>.</p>
</div>
"""


def handle_landing_page(query_params: dict | None = None, referer: str = "") -> dict:
    query_params = query_params or {}
    # Email-capture prompt for AWS Marketplace subscribers (added 2026-07-09).
    # Gated strictly on both params being present — AWS's own audit crawler
    # probes this page with a bare GET/HEAD and no query string at all, so
    # this branch never fires for that traffic; only real subscribers
    # arriving via the /marketplace/fulfillment redirect see it.
    # startswith(), not ==, since 2026-07-18: relayshield_bundle_fulfillment.py
    # sends "aws_marketplace_{bundle_label}" (e.g. "aws_marketplace_agentic_attack_surface")
    # for Bundle A-D, not the bare "aws_marketplace" the original TI-subscription
    # flow sends — an exact match here silently sent every bundle customer to
    # the Stripe-checkout landing page instead of this bypass, which is exactly
    # what AWS's Bundle D visibility audit rejected as external payment collection.
    aws_customer_id = query_params.get("aws_customer_id", "")
    already_confirmed = query_params.get("email_confirmed") == "1"
    aws_source = query_params.get("source", "")
    if aws_source.startswith("aws_marketplace") and aws_customer_id and not already_confirmed:
        return _html(_aws_email_capture_page(aws_customer_id, aws_source))

    # Referrer-aware framing: developers arriving from the LangChain integration
    # tables land on a general API page and have to hunt for the piece that
    # brought them. Swap in a LangChain-specific quickstart above the fold.
    banner = _LANGCHAIN_BANNER if "langchain.com" in (referer or "").lower() else ""
    return _html(LANDING_PAGE.replace("<!--REFERRER_BANNER-->", banner))


def _aws_email_capture_page(aws_customer_id: str, source: str = "aws_marketplace") -> str:
    """One-field form shown only to AWS Marketplace subscribers immediately
    after the fulfillment redirect. AWS's ResolveCustomer API never returns
    an email, so this is the only point in the flow where we can capture a
    real, deliverable address for the welcome email / API key delivery.

    The form action is chosen from `source`, added 2026-07-30. It was hardcoded
    to the TI product's /marketplace/fulfillment, so every Bundle A-D subscriber
    submitted their email to the wrong product's Lambda -- which has no record
    of a bundle contract, mailed them the Threat Intelligence welcome text, and
    bounced them to the Stripe self-serve signup page where "Get API key" fails.
    That is what AWS hit on the Bundle D public-visibility audit
    (change set 7rjip57niylpdl9uo5u3l735k, failed 2026-07-30): "when trying to
    get the API key, we get an error message 'Something went wrong'".

    Bundle fulfillment sends source="aws_marketplace_{bundle_label}"; the flat-
    rate TI product sends the bare "aws_marketplace". Anything more specific
    than the bare value is a bundle, so the default stays on the TI path and
    the already-approved TI flow is untouched.
    """
    is_bundle = source.startswith("aws_marketplace_")
    action = f"{PUBLIC_API_BASE_URL}/marketplace/" + ("bundle-fulfillment" if is_bundle else "fulfillment")
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RelayShield — Almost done</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d0f14;
color:#e8eaf0;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:2rem}}
.card{{background:#161a23;border:1px solid #242836;border-top:3px solid #6c63ff;border-radius:18px;
padding:2.5rem;max-width:440px;width:100%;text-align:center}}
h1{{font-size:1.4rem;font-weight:800;margin-bottom:.6rem}}
p{{color:#8b91a8;font-size:.9rem;line-height:1.6;margin-bottom:1.5rem}}
input{{width:100%;padding:.75rem;border-radius:8px;border:1px solid #242836;background:#0d0f14;
color:#e8eaf0;box-sizing:border-box;margin-bottom:1rem;font-size:.95rem}}
button{{background:#6c63ff;color:#fff;border:none;border-radius:8px;padding:.75rem 1.5rem;
font-size:.95rem;font-weight:600;cursor:pointer;width:100%}}</style>
</head><body><div class="card">
<h1>You're subscribed to RelayShield!</h1>
<p>Enter your email so we can send your API key and setup instructions.</p>
<form method="POST" action="{action}">
<input type="hidden" name="customer_id" value="{aws_customer_id}">
<input type="hidden" name="source" value="{source}">
<input type="email" name="email" placeholder="you@company.com" required autofocus>
<button type="submit">Get my API key</button>
</form>
</div></body></html>"""


def handle_success_page() -> dict:
    return _html(SUCCESS_PAGE)


CS_MOBILE_SUCCESS_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>You're subscribed — Crypto Shield</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0a1628; --surface: #0F1F3D; --border: #1e3a5f;
    --accent: #00B5A5; --text: #e2e8f0; --muted: #64748b;
    --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--font);
         min-height: 100vh; display: flex; flex-direction: column; align-items: center;
         justify-content: center; padding: 2rem; text-align: center; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 18px;
          padding: 2.5rem; max-width: 440px; width: 100%; }}
  .icon {{ font-size: 2.5rem; margin-bottom: 1rem; }}
  h1 {{ font-size: 1.4rem; font-weight: 800; margin-bottom: .5rem; }}
  p {{ color: var(--muted); font-size: .92rem; line-height: 1.6; margin-bottom: 1.6rem; }}
  a.btn {{ display: inline-block; background: var(--accent); color: #0a1628; border-radius: 9px;
       padding: .8rem 1.8rem; font-weight: 800; font-size: .95rem; text-decoration: none; }}
</style>
</head>
<body>
<div class="card">
  <div class="icon">✅</div>
  <h1>You're subscribed to Crypto Shield Pro</h1>
  <p id="msg">Opening the app to finish setup automatically...</p>
  <a class="btn" id="manual-open" href="net.relayshield.cryptoshield://unlock?session_id={session_id}">
    Open Crypto Shield
  </a>
</div>
<script>
  (function() {{
    var url = "net.relayshield.cryptoshield://unlock?session_id={session_id}";
    window.location.href = url;
    setTimeout(function() {{
      document.getElementById("msg").textContent =
        "If the app didn't open automatically, tap the button below.";
    }}, 1500);
  }})();
</script>
</body>
</html>"""


def handle_cs_mobile_success_page(query_params: dict) -> dict:
    """Landing page the Crypto Shield Mobile Pro Stripe Payment Link redirects
    to after checkout (after_completion.redirect.url with the {{CHECKOUT_SESSION_ID}}
    template variable). Immediately deep-links back into the app with the
    session ID so the app can auto-provision without the user typing their
    email -- see handle_cs_mobile_link_by_session."""
    import re as _re
    session_id = (query_params.get("session_id") or "").strip()
    # Stripe Checkout Session IDs are always cs_(test|live)_<alphanumeric> --
    # validate before embedding in returned HTML/JS rather than trusting an
    # arbitrary query param verbatim.
    if not _re.match(r"^cs_(test|live)_[A-Za-z0-9]+$", session_id):
        session_id = ""
    return _html(CS_MOBILE_SUCCESS_PAGE.format(session_id=session_id))


TOPUP_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Top up credits — RelayShield API</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0d0f14; --surface: #161a23; --border: #242836;
    --accent: #6c63ff; --accent-dim: #4e47d6; --text: #e8eaf0; --muted: #8b91a8;
    --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  }
  body { background: var(--bg); color: var(--text); font-family: var(--font);
         min-height: 100vh; display: flex; flex-direction: column; align-items: center;
         justify-content: center; padding: 2rem; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 18px;
          padding: 2.5rem; max-width: 500px; width: 100%; }
  h1 { font-size: 1.5rem; font-weight: 800; margin-bottom: .4rem; }
  .sub { color: var(--muted); font-size: .9rem; margin-bottom: 2rem; }
  label { font-size: .82rem; color: var(--muted); display: block; margin-bottom: .4rem; }
  input[type=text] { width: 100%; background: var(--bg); border: 1px solid var(--border);
                     color: var(--text); border-radius: 8px; padding: .65rem 1rem;
                     font-size: .9rem; font-family: 'SF Mono','Fira Code',monospace;
                     margin-bottom: 1.4rem; outline: none; }
  input[type=text]:focus { border-color: var(--accent); }
  .pack-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: .75rem; margin-bottom: 1.5rem; }
  .pack { background: var(--bg); border: 2px solid var(--border); border-radius: 10px;
          padding: 1.1rem .8rem; text-align: center; cursor: pointer; transition: border-color .15s; }
  .pack:hover { border-color: var(--accent); }
  .pack.selected { border-color: var(--accent); background: rgba(108,99,255,.08); }
  .pack .amount { font-size: 1.5rem; font-weight: 800; }
  .pack .credits { font-size: .75rem; color: var(--muted); margin-top: .25rem; }
  button { width: 100%; background: var(--accent); color: #fff; border: none; border-radius: 8px;
           padding: .75rem; font-size: 1rem; font-weight: 600; cursor: pointer; }
  button:hover { background: var(--accent-dim); }
  button:disabled { opacity: .5; cursor: default; }
  #err { color: #f87171; font-size: .85rem; margin-top: .75rem; display: none; }
  .rates { margin-top: 1.5rem; padding-top: 1.2rem; border-top: 1px solid var(--border);
           display: grid; grid-template-columns: 1fr 1fr; gap: .3rem .5rem; }
  .rates span { font-size: .78rem; color: var(--muted); }
  .rates span:nth-child(odd) { color: var(--text); }
</style>
</head>
<body>
<div class="card">
  <h1>Top up credits</h1>
  <p class="sub">Credits never expire. One credit = $0.01.</p>

  <label>Your API key</label>
  <input type="text" id="api-key" placeholder="rs_live_..." autocomplete="off" spellcheck="false">

  <label>Select a pack</label>
  <div class="pack-grid">
    <div class="pack selected" data-pack="0">
      <div class="amount">$25</div>
      <div class="credits">2,500 credits</div>
    </div>
    <div class="pack" data-pack="1">
      <div class="amount">$50</div>
      <div class="credits">5,000 credits</div>
    </div>
    <div class="pack" data-pack="2">
      <div class="amount">$100</div>
      <div class="credits">10,000 credits</div>
    </div>
  </div>

  <button id="btn" onclick="checkout()">Buy credits →</button>
  <div id="err"></div>

  <div class="rates">
    <span>/breach</span>        <span>10 credits ($0.10)</span>
    <span>/sim-swap</span>      <span>25 credits ($0.25)</span>
    <span>/infostealer</span>   <span>50 credits ($0.50)</span>
    <span>/domain</span>        <span>30 credits ($0.30)</span>
    <span>/oauth-watchlist</span><span>20 credits ($0.20)</span>
    <span>/crypto-intel</span>    <span>30 credits ($0.30)</span>
  </div>
</div>
<script>
let selectedPack = 0;
document.querySelectorAll('.pack').forEach(el => {
  el.addEventListener('click', () => {
    document.querySelectorAll('.pack').forEach(p => p.classList.remove('selected'));
    el.classList.add('selected');
    selectedPack = parseInt(el.dataset.pack);
  });
});
async function checkout() {
  const key = document.getElementById('api-key').value.trim();
  const btn = document.getElementById('btn');
  const err = document.getElementById('err');
  err.style.display = 'none';
  if (!key.startsWith('rs_live_')) { err.textContent = 'Enter your rs_live_... API key'; err.style.display='block'; return; }
  btn.disabled = true; btn.textContent = 'Redirecting…';
  try {
    const res  = await fetch('/developer/topup', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({api_key: key, pack: selectedPack})
    });
    const data = await res.json();
    if (data.ok) { window.location.href = data.data.checkout_url; }
    else { throw new Error(data.error || 'Something went wrong'); }
  } catch(e) {
    err.textContent = e.message; err.style.display = 'block';
    btn.disabled = false; btn.textContent = 'Buy credits →';
  }
}
</script>
</body>
</html>"""

TOPUP_SUCCESS_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Credits added — RelayShield API</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root { --bg: #0d0f14; --surface: #161a23; --border: #242836; --accent: #6c63ff;
          --green: #22c55e; --text: #e8eaf0; --muted: #8b91a8;
          --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
  body { background: var(--bg); color: var(--text); font-family: var(--font);
         min-height: 100vh; display: flex; align-items: center; justify-content: center; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 18px;
          padding: 3rem 2.5rem; max-width: 420px; width: 90%; text-align: center; }
  .icon { width: 60px; height: 60px; background: rgba(34,197,94,.15); border-radius: 50%;
          display: flex; align-items: center; justify-content: center; margin: 0 auto 1.5rem; }
  h1 { font-size: 1.7rem; font-weight: 800; margin-bottom: .5rem; }
  p  { color: var(--muted); font-size: .95rem; line-height: 1.6; margin-bottom: 1.8rem; }
  a  { display: inline-block; background: var(--accent); color: #fff; border-radius: 9px;
       padding: .7rem 1.6rem; font-weight: 600; font-size: .95rem; text-decoration: none; }
</style>
</head>
<body>
<div class="card">
  <div class="icon">
    <svg viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2.5"
         stroke-linecap="round" stroke-linejoin="round" width="28" height="28">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  </div>
  <h1>Credits added</h1>
  <p>Your balance has been updated. Start making API calls immediately — no restart needed.</p>
  <a href="javascript:history.back()">← Back</a>
</div>
</body>
</html>"""


def handle_topup_page() -> dict:
    return _html(TOPUP_PAGE)


def handle_topup_success_page() -> dict:
    return _html(TOPUP_SUCCESS_PAGE)


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context) -> dict:
    path   = event.get("path", "")
    method = event.get("httpMethod", "")

    # Header names arrive with inconsistent casing depending on the client and
    # API Gateway payload version, so normalise before reading Referer.
    _hdrs = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    referer = _hdrs.get("referer") or _hdrs.get("referrer") or ""

    # Referrer logged so inbound traffic from integration listings (LangChain's
    # docs, PyPI, AWS Marketplace) is attributable. Query with CloudWatch Logs
    # Insights on `referer=`; see TODO ELASTIC/LANGCHAIN notes for the query.
    logger.info(
        "developer-signup request method=%s path=%s referer=%s", method, path, referer or "-"
    )

    # AWS Marketplace's audit crawler (and other automated link checkers) probe
    # with HEAD before accepting listing metadata URLs — must return 200, not just GET.
    # That probe hits this path with no query string, so passing query params
    # through here doesn't affect it — see handle_landing_page's gating.
    if method in ("GET", "HEAD") and path in ("/developers", "/developers/"):
        return handle_landing_page(event.get("queryStringParameters") or {}, referer)

    if method in ("GET", "HEAD") and path in ("/developer/success", "/developer/success/"):
        return handle_success_page()

    if method in ("GET", "HEAD") and path in ("/developer/cs-mobile-success", "/developer/cs-mobile-success/"):
        return handle_cs_mobile_success_page(event.get("queryStringParameters") or {})

    if method == "GET" and path in ("/developer/cs-mobile-link", "/developer/cs-mobile-link/"):
        return handle_cs_mobile_link(event.get("queryStringParameters") or {})

    if method == "GET" and path in ("/developer/cs-mobile-link-by-session", "/developer/cs-mobile-link-by-session/"):
        return handle_cs_mobile_link_by_session(event.get("queryStringParameters") or {})

    if method == "GET" and path in ("/developer/cs-mobile-portal", "/developer/cs-mobile-portal/"):
        return handle_cs_mobile_portal(event.get("queryStringParameters") or {})

    if method in ("GET", "HEAD") and path in ("/developer/topup", "/developer/topup/"):
        return handle_topup_page()

    if method in ("GET", "HEAD") and path in ("/developer/topup-success", "/developer/topup-success/"):
        return handle_topup_success_page()

    if method == "POST" and path == "/developer/topup":
        try:
            body = json.loads(event.get("body") or "{}")
        except Exception:
            body = {}
        return handle_topup(body)

    if method == "POST" and path == "/developer/signup":
        try:
            body = json.loads(event.get("body") or "{}")
        except Exception:
            body = {}
        return handle_signup(body)

    if method == "POST" and path == "/developer/stripe-webhook":
        raw_body = event.get("body") or ""
        if event.get("isBase64Encoded"):
            raw_body = base64.b64decode(raw_body)
        elif isinstance(raw_body, str):
            raw_body = raw_body.encode("utf-8")
        return handle_webhook(event.get("headers") or {}, raw_body)

    return _err("not found", 404)
