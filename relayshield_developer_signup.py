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
import os
import re
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr, Key

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
# ---------------------------------------------------------------------------
# Bundle D "Door 2" — direct Stripe purchase of the same bundle sold on AWS
# Marketplace as prod-kkvurtspreofy ($299/mo, agentic_bundle_access).
#
# Why this exists: AWS Marketplace is high-friction for anyone without an AWS
# procurement relationship, and Bundle D's audience includes developers who
# will never touch it. Same product, same price, two doors. Enterprises who
# want to draw down committed AWS spend keep using Marketplace; everyone else
# checks out with a card.
#
# AWS COMPLIANCE NOTE, read before touching this. Marketplace is not
# exclusive and dual-channel selling is permitted. What is NOT permitted is
# disintermediation: taking a customer who ARRIVED through Marketplace and
# moving them off it, or failing to meter Marketplace-originated usage
# through Marketplace. The separation that keeps us clean:
#
#   * An AWS-provisioned key carries aws_account_id + aws_license_arn and is
#     metered via BatchMeterUsage on every billed call, forever.
#   * A Stripe-provisioned key carries stripe_customer_id and source
#     "bundle_d_direct", and is billed through the Stripe meter.
#   * NEVER migrate a customer from an AWS key to a Stripe key, and never
#     steer a Marketplace-originated lead to the Stripe door.
#
# The `source` field on every api_keys record is the audit trail for exactly
# this question. Do not overload it.
#
# Set BUNDLE_D_DIRECT_PRICE_IDS once the Stripe Product and Price exist. The
# empty set is safe: an unmatched price falls through to the generic metered
# signup path below, exactly as it did before this block existed.
BUNDLE_D_DIRECT_PRICE_IDS = frozenset(
    p for p in os.environ.get("BUNDLE_D_DIRECT_PRICE_IDS", "").split(",") if p.strip()
)

# Bundle A "Door 2" — direct Stripe purchase of Core Identity Exposure, sold on
# AWS Marketplace as its own entity prod-f5qkfsxlxs4qg / product code
# cvfvhwhmichl13kcuuutkbwmp ($150/mo access + per-call, bundle_a_access).
# Added 2026-08-12. Every compliance note in the Bundle D block above applies
# here unchanged: never migrate an AWS key to Stripe, never steer a
# Marketplace-originated lead to this door.
BUNDLE_A_DIRECT_PRICE_IDS = frozenset(
    p for p in os.environ.get("BUNDLE_A_DIRECT_PRICE_IDS", "").split(",") if p.strip()
)

# The two doors must charge the same per-call rates, and the mechanism that
# guarantees it is that neither door has per-call prices of its own: both ride
# the aggregate meter below, whose amount relayshield_api.py looks up from the
# request path. A Checkout session for either bundle therefore carries exactly
# two line items -- the licensed monthly price, and STRIPE_USAGE_PRICE_ID.
#
# DO NOT add per-endpoint prices here. Stripe Checkout rejects more than 20
# recurring prices, and that ceiling is what killed self-serve developer signup
# for six weeks in June 2026.
#
# A subscription with ONLY the licensed price would give unlimited calls for the
# monthly fee, undercutting the AWS door. That is lost revenue and, in front of
# an AWS audit, bad optics.
BUNDLE_DIRECT_CHECKOUT = {
    "a": {
        "price_ids":  lambda: BUNDLE_A_DIRECT_PRICE_IDS,
        "env_var":    "BUNDLE_A_DIRECT_PRICE_IDS",
        "label":      "Core Identity Exposure",
        "monthly":    "$150/mo",
        "aws_listing": "https://aws.amazon.com/marketplace/pp/prodview-zgdxyqfd63hog",
    },
    "d": {
        "price_ids":  lambda: BUNDLE_D_DIRECT_PRICE_IDS,
        "env_var":    "BUNDLE_D_DIRECT_PRICE_IDS",
        "label":      "Agentic Attack Surface",
        "monthly":    "$299/mo",
        "aws_listing": "https://aws.amazon.com/marketplace/pp/prodview-6p6csngrcg3zq",
    },
}

LLM_LICENSE_PRICE_IDS = frozenset({
    "price_1TxdQpL2dcjOeFiYeXtONMuK",  # $39/mo
    "price_1TxdQpL2dcjOeFiYe1XqvVGn",  # $399/yr
})

# One price per metered endpoint — created in Stripe Dashboard Jun 11 2026
# The single metered Price a new developer's subscription carries, replacing
# the 29-entry per-endpoint list below on 2026-08-04.
#
# WHY THIS EXISTS: Stripe Checkout rejects a session with more than 20
# recurring prices ("You can not pass in more than 20 recurring prices"),
# verified by probing the live API — 20 succeeds, 21 fails. The per-endpoint
# list had reached 24, so handle_signup() had been returning HTTP 400 and
# self-serve developer signup had been completely dead since 2026-06-24, the
# day the 21st price was added. Nobody noticed because there were no signups
# to lose and the failure surfaced only as a generic error on the page.
#
# This price bills $0.01 per unit against the aggregate meter
# relayshield_api_usage (formula=sum), and both API Lambdas now post
# payload[value] = the call's price in CENTS. A $0.35 call posts 35 and bills
# $0.35 — identical amounts to the old model, one line item, and no ceiling to
# hit as endpoints are added.
STRIPE_USAGE_PRICE_ID = "price_1U0jLZL2dcjOeFiYG8VktTxK"

# RETIRED 2026-08-04 — kept for reference only, no longer sent to Checkout.
# Do NOT add new endpoints here; pricing now lives in METERED_CREDIT_COSTS
# (relayshield_api.py) and PRICE_CENTS (relayshield_agentic_api.py), which is
# what the meter event reads. Retained because these prices are still attached
# to the historical per-endpoint meters in Stripe.
_RETIRED_STRIPE_PRICE_IDS = [
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
    "price_1TzFdML2dcjOeFiYHmUg2UK8",  # secret-scan-text     $0.05/call — created 2026-07-31
    # with its own meter (mtr_61V8daayOdgGiVieY41L2dcjOeFiYH16). Priced well below
    # secret-scan because it runs locally with no external API call and is the
    # pre-commit path, which fires on every commit — $0.35 there would cost a
    # 20-commit-a-day developer $7/day and kill hook adoption. Same
    # no-retroactive-backfill limitation as every other post-launch endpoint:
    # developers who signed up before today do not get this line item.
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
    #
    # --- Billing-gap sweep (Aug 4 2026) ---
    # Found by cross-checking all 29 STRIPE_METER_EVENTS entries against live
    # Stripe: meter -> price -> this list. 24 lined up; these 5 did not, so
    # every fiat-PAYG developer could call them and never be charged. Three
    # already had a Product and an active Price and were simply never added
    # here; cert-expiry and ip-intel had no Price object at all and needed one
    # created (both mirror secret-scan-text's exact meter/price config).
    #
    # The lesson worth keeping: a meter firing events is NOT evidence of
    # billing, and neither is a Price existing. Only membership in this list
    # puts a line item on a developer's subscription. Verify all three layers
    # whenever an endpoint is added — see the check in
    # memory/project_agentic_api_no_credit_check.md.
    "price_1TqemTL2dcjOeFiYcx7fHdDW",  # mcp-registry-risk       $0.35/call — Product/Price
    # created 2026-07-07 with the endpoint (TODO AGENTIC-3), never added here. Served by the
    # isolated relayshield_agentic_api.py Lambda, which is why it was missed: that file has its
    # own STRIPE_METER_EVENTS, so a sweep that only reads relayshield_api.py cannot see it.
    "price_1TqemUL2dcjOeFiY9odgLrHB",  # prompt-injection-breach $0.35/call — same, TODO AGENTIC-4.
    "price_1TmKDTL2dcjOeFiYn8uq0Kkj",  # tech-stack-cve          $0.20/call — in relayshield_api.py,
    # not the agentic Lambda, so this one was an independent instance of the same omission.
    "price_1U0j0cL2dcjOeFiYqExONwf7",  # cert-expiry             $0.05/call — Product
    # prod_V0kVJ2n5aRukdE + this Price created 2026-08-04; only the meter existed before.
    "price_1U0j0cL2dcjOeFiYgPgBXs3u",  # ip-intel                $0.10/call — Product
    # prod_V0kVuMgavb9L2L + this Price created 2026-08-04; only the meter existed before.
    #
    # Same no-retroactive-backfill limitation as every previous post-launch
    # endpoint: these five line items land on NEW subscriptions only.
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

# Free tier, added 2026-08-04. A developer will not enter a card to try an API
# they have never called, and the numbers said so plainly: 462 views of
# /developers since June 1 produced 3 signup clicks (0.65%) and zero completed
# accounts. Every comparable product in this market (GreyNoise, AbuseIPDB,
# HIBP) has a free tier; "no free tier" was the wall.
#
# Raised 20 -> 100 on 2026-08-09. 20 was sized to "integrate and see a real
# response on a couple of endpoints", which is the wrong goal: the developer
# funnel depends on the evaluator producing an ARTIFACT worth forwarding to
# whoever holds the budget, and 20 calls does not survive one domain scan plus
# a handful of employee emails plus the calls you waste getting the request
# body right. The page's own worked example (10 breach checks) spent half of it.
#
# 100 still will not run anything in production, and the marginal cost to us is
# near zero: HIBP is a flat monthly subscription and GoPlus is called on its
# free public tier, so a free-tier call adds Lambda time and nothing else.
#
# The exception is the handful of endpoints that fan out to many upstream calls
# per request. Those are excluded from the free tier entirely rather than being
# allowed to burn 100 of them; see FREE_TIER_EXCLUDED_ENDPOINTS in
# relayshield_api.py, which is where the allowance is actually spent.
FREE_TIER_CALLS = 100


def _find_developer_key_by_email(email: str) -> dict | None:
    """Find an existing API key for this address, for the free-tier path.

    Deliberately NOT _find_key_by_email: that helper projects away
    free_calls_remaining and plan, and it prefers whichever record has
    cs_mobile_access set. A Crypto Shield Mobile subscriber signing up for a
    developer key would otherwise be handed their mobile key back.

    Uses the email-index GSI rather than a table scan. Prefers a real developer
    record (one with a subscription or a free allowance) over a mobile one.
    """
    try:
        resp = dynamodb.Table(API_KEYS_TABLE).query(
            IndexName="email-index",
            KeyConditionExpression=Key("email").eq(email.strip().lower()),
        )
        # Truthiness must match _verify_rs_api_key in relayshield_api.py exactly,
        # which does `if item and item.get("active")`. This previously defaulted
        # to True for a record with no `active` attribute, so a key the API
        # considers dead looked alive here. On 2026-08-04 that selected a
        # long-dormant Zapier test-account key with no `active` flag and emailed
        # it to a partner reviewer mid-review; every call with it returned
        # "Valid API key required". A lookup used to hand somebody a credential
        # must apply the same rule the authenticator applies.
        items = [i for i in resp.get("Items", []) if i.get("active")]
    except Exception as exc:
        logger.warning("email-index lookup failed for %s: %s", email, exc)
        return None
    if not items:
        return None
    for item in items:
        if item.get("free_calls_remaining") is not None or item.get("stripe_subscription_id"):
            return item
    return items[0]


def _issue_free_key(email: str, source: str = "direct") -> str:
    """Mint a no-card free-tier key.

    Deliberately carries NO stripe_customer_id and NO stripe_subscription_id.
    That matters for billing correctness: handle_metered_request only records a
    Stripe meter event when a customer id is present, so a free key cannot
    produce a usage event that nothing can bill. When the developer later adds
    a card, checkout attaches those ids to this same email.
    """
    api_key = f"rs_live_{uuid.uuid4().hex}"
    dynamodb.Table(API_KEYS_TABLE).put_item(Item={
        "api_key":              api_key,
        "email":                email,
        "active":               True,
        "source":               source,
        "plan":                 "free",
        "free_calls_remaining": FREE_TIER_CALLS,
        "created_at":           datetime.now(timezone.utc).isoformat(),
    })
    logger.info("free-tier key issued email=%s source=%s calls=%d", email, source, FREE_TIER_CALLS)
    return api_key


def handle_signup(body: dict) -> dict:
    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _err("email is required")

    source = (body.get("source") or "direct").strip().lower()
    if source not in VALID_SOURCES:
        source = "direct"

    # Free tier is the default path: no card, no Stripe, key by email in one
    # step. Callers who explicitly want the paid path send {"paid": true},
    # which is what the "Add a card" button on the success page uses.
    if not body.get("paid"):
        existing = _find_developer_key_by_email(email)
        if existing:
            # Do not mint a second key for the same address, and do not top the
            # free allowance back up -- that would make the limit meaningless.
            # Re-send the key they already have instead, so a developer who
            # lost the email is not stuck.
            try:
                # Report the allowance the key actually has. Reading only
                # free_calls_remaining told a credits-funded account it had
                # "0 free calls", which is both wrong and alarming. Credits are
                # in cents, so convert at the cheapest endpoint price to give a
                # floor rather than an overstatement.
                allowance = int(existing.get("free_calls_remaining") or 0)
                if not allowance:
                    allowance = int(int(existing.get("credit_balance") or 0) / 5)
                _send_free_key_email(email, existing["api_key"], allowance)
            except Exception as exc:
                logger.warning("free key re-send failed email=%s: %s", email, exc)
            logger.info("free-tier signup for existing email=%s — key re-sent", email)
            return _ok({"free_tier": True, "resent": True,
                        "message": "You already have a key. We have emailed it to you again."})
        try:
            api_key = _issue_free_key(email, source)
            _send_free_key_email(email, api_key, FREE_TIER_CALLS)
        except Exception as exc:
            logger.exception("free-tier signup failed email=%s: %s", email, exc)
            return _err("could not create your key — try again", 502)
        return _ok({"free_tier": True, "calls": FREE_TIER_CALLS,
                    "message": f"Your API key is on its way to {email}. "
                               f"{FREE_TIER_CALLS} free calls, no card needed."})

    # Create Stripe Customer
    try:
        customer    = _stripe_post("/customers", {"email": email, "description": "RelayShield API developer"})
        customer_id = customer["id"]
    except Exception as exc:
        logger.error("Stripe customer creation failed email=%s error=%s", email, exc)
        return _err("could not create billing account — try again", 502)

    # Build Checkout session with the single aggregate usage price.
    # One line item, not one per endpoint — Stripe caps a Checkout session at
    # 20 recurring prices and the per-endpoint list had grown to 24, which is
    # what broke this call. See STRIPE_USAGE_PRICE_ID.
    session_params: dict = {
        "mode":        "subscription",
        "customer":    customer_id,
        "success_url": SUCCESS_URL,
        "cancel_url":  CANCEL_URL,
        # Store email + source in metadata so webhook can retrieve them without extra Stripe calls
        "subscription_data[metadata][developer_email]": email,
        "subscription_data[metadata][source]":          source,
        "line_items[0][price]": STRIPE_USAGE_PRICE_ID,
    }

    try:
        session      = _stripe_post("/checkout/sessions", session_params)
        checkout_url = session["url"]
    except Exception as exc:
        logger.error("Stripe checkout session failed customer=%s error=%s", customer_id, exc)
        return _err("could not create checkout session — try again", 502)

    logger.info("developer signup — email=%s customer=%s session=%s", email, customer_id, session["id"])
    return _ok({"checkout_url": checkout_url})


def handle_bundle_checkout(body: dict) -> dict:
    """POST /developer/bundle-checkout — Door 2 for Bundle A and Bundle D.

    Builds a Checkout session with exactly two line items: the bundle's
    licensed monthly price, and the aggregate usage price. See
    BUNDLE_DIRECT_CHECKOUT for why it is two and not one, and not twenty-four.
    """
    bundle = (body.get("bundle") or "").strip().lower()
    cfg    = BUNDLE_DIRECT_CHECKOUT.get(bundle)
    if not cfg:
        return _err("bundle must be 'a' or 'd'")

    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _err("email is required")

    price_ids = sorted(cfg["price_ids"]())
    if not price_ids:
        # Fail loudly rather than falling through to the generic metered
        # signup. An unset env var previously meant a buyer silently got a
        # pay-as-you-go key instead of the bundle they clicked on.
        logger.error("bundle checkout requested but %s is unset — refusing", cfg["env_var"])
        return _err("this bundle is not available for direct purchase yet — "
                    f"buy it on AWS Marketplace at {cfg['aws_listing']}", 503)

    try:
        customer    = _stripe_post("/customers", {"email": email,
                                                  "description": f"RelayShield Bundle {bundle.upper()} direct"})
        customer_id = customer["id"]
    except Exception as exc:
        logger.error("Stripe customer creation failed (bundle_%s) email=%s error=%s", bundle, email, exc)
        return _err("could not create billing account — try again", 502)

    session_params: dict = {
        "mode":        "subscription",
        "customer":    customer_id,
        "success_url": SUCCESS_URL,
        "cancel_url":  CANCEL_URL,
        "subscription_data[metadata][developer_email]": email,
        "subscription_data[metadata][source]":          f"bundle_{bundle}_direct",
        "line_items[0][price]":    price_ids[0],
        "line_items[0][quantity]": "1",
        "line_items[1][price]":    STRIPE_USAGE_PRICE_ID,
    }

    try:
        session = _stripe_post("/checkout/sessions", session_params)
    except Exception as exc:
        logger.error("Stripe checkout session failed (bundle_%s) customer=%s error=%s",
                     bundle, customer_id, exc)
        return _err("could not create checkout session — try again", 502)

    logger.info("bundle %s direct checkout — email=%s customer=%s session=%s",
                bundle.upper(), email, customer_id, session["id"])
    return _ok({"checkout_url": session["url"], "bundle": bundle, "monthly": cfg["monthly"]})


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


def _send_free_key_email(to_email: str, api_key: str, calls_left: int) -> None:
    """Free-tier welcome. Deliberately short and copy-pasteable.

    The paid key email lists all 29 endpoints, which is the right reference for
    someone who has already committed. For a first-time free key it is a wall:
    the job of this email is to get one successful call made, so it leads with
    a curl that works and names the two wedge endpoints, not the catalogue.
    """
    subject = f"Your RelayShield API key ({calls_left} free calls)"
    body = f"""Your API key
------------
{api_key}

{calls_left} free calls, no card. Send it as a header on every request:
  X-RS-API-KEY: {api_key}

Make your first call now
------------------------
curl -X POST {API_BASE_URL}/v1/metered/breach \\
  -H "X-RS-API-KEY: {api_key}" \\
  -H "Content-Type: application/json" \\
  -d '{{"email":"you@example.com"}}'

Two worth trying with the rest of your free calls
-------------------------------------------------
Most secret scanners tell you what is in your code. These tell you what is
already in criminal hands, which is the part you cannot fix by scanning a repo.

POST /v1/metered/session-risk   stolen session cookies for an address. A stolen
                                cookie bypasses MFA and stays valid until the
                                session is revoked, so a password reset alone
                                does not close it.

POST /v1/metered/nhi-exposure   machine credentials tied to your domain in
                                stealer-log archives: AWS keys, GitHub PATs,
                                Stripe secrets, private keys, Slack tokens.

A clean result means nothing was found in the sources we queried. It is not
proof of safety.

Full reference: https://api.relayshield.net/docs
Every parameter, response field, error code and example for all 29 endpoints.

When your {calls_left} calls run out, add a card at
https://api.relayshield.net/developers and you are billed only for what you
call after that. No minimum, no subscription fee.

Questions: support@relayshield.net
"""
    try:
        ses.send_email(
            Source=FROM_EMAIL,
            Destination={"ToAddresses": [to_email]},
            Message={"Subject": {"Data": subject}, "Body": {"Text": {"Data": body}}},
        )
        logger.info("free-tier key email sent to %s", to_email)
    except Exception as exc:
        logger.exception("free-tier key email failed for %s: %s", to_email, exc)
        raise


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
POST {API_BASE_URL}/v1/metered/secret-scan     — GitHub secret scanning      $0.35/call
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


def _get_subscription_price_ids(subscription_id: str) -> list[str]:
    """Every price ID on a subscription, not just the first.

    WHY THIS EXISTS, added 2026-08-12. A bundle subscription carries TWO items:
    the licensed monthly price and the aggregate metered price. Stripe does not
    guarantee item order, so reading items[0] is a coin flip -- if the metered
    price came back first, the bundle branch in the webhook would not fire and
    the customer would be charged $150 or $299 a month and handed an ordinary
    pay-as-you-go key with no bundle access at all. Silent, and only visible
    when a real buyer complained.
    """
    credentials = base64.b64encode(f"{_stripe_key()}:".encode()).decode()
    req = urllib.request.Request(
        f"{STRIPE_API_BASE}/subscriptions/{subscription_id}",
        headers={"Authorization": f"Basic {credentials}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return [i.get("price", {}).get("id") for i in data.get("items", {}).get("data", [])
                    if i.get("price", {}).get("id")]
    except Exception as exc:
        logger.error("Stripe subscription lookup failed sub=%s error=%s", subscription_id, exc)
    return []


def _get_subscription_price_id(subscription_id: str) -> str | None:
    """First price ID on a subscription. Kept for the single-item paths (TI,
    CS Mobile, LLM licence), all of which have exactly one item. Anything that
    can be part of a multi-item bundle subscription must use
    _get_subscription_price_ids instead."""
    ids = _get_subscription_price_ids(subscription_id)
    return ids[0] if ids else None


def _find_key_by_customer(stripe_customer_id: str) -> dict | None:
    """
    Scan relayshield_api_keys for a record matching the given Stripe customer ID.
    Table PK is api_key — no GSI on stripe_customer_id yet (acceptable at current scale;
    add a GSI when the key count grows past a few hundred).
    """
    # The bundle fields and the aws_* fields are projected deliberately. The
    # bundle checkout handlers branch on record.get("aws_license_arn") to refuse
    # to modify an AWS-fulfilled key, and on record.get("bundle_?_access") to
    # avoid re-provisioning and re-emailing a key that already has it. A
    # ProjectionExpression that omits them does not raise -- it returns None for
    # every one, so both guards silently evaluate false. Added 2026-08-12; the
    # Bundle D door had shipped with them missing.
    resp = dynamodb.Table(API_KEYS_TABLE).scan(
        FilterExpression=Attr("stripe_customer_id").eq(stripe_customer_id),
        ProjectionExpression=(
            "api_key, email, intel_access, intel_plan_tier, stripe_subscription_id, "
            "bundle_a_access, bundle_d_access, aws_account_id, aws_customer_id, aws_license_arn"
        ),
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


def _provision_bundle_d_direct(api_key_str: str, stripe_subscription_id: str) -> None:
    """Set bundle_d_access=True for a DIRECT Stripe purchase of Bundle D.

    Same flag the AWS Marketplace fulfilment path sets, deliberately: the
    capability gate in relayshield_api.py keys on bundle_d_access, so one flag
    serves both doors and there is no second code path to keep in sync.

    What is NOT set here, and must never be: aws_account_id and
    aws_license_arn. Their absence is what stops the metering code reporting
    a Stripe customer's usage to AWS. See is_bundle_d_call in
    relayshield_api.py, which requires aws_customer_id before metering.
    """
    dynamodb.Table(API_KEYS_TABLE).update_item(
        Key={"api_key": api_key_str},
        UpdateExpression="SET bundle_d_access = :yes, stripe_subscription_id = :sid",
        ExpressionAttributeValues={":yes": True, ":sid": stripe_subscription_id},
    )
    logger.info("bundle_d_access provisioned (direct) api_key=%s", api_key_str[:16])


def _revoke_bundle_d_direct(api_key_str: str) -> None:
    """Set bundle_d_access=False on direct Bundle D cancellation.

    Only ever called for a subscription whose price is in
    BUNDLE_D_DIRECT_PRICE_IDS, so an AWS-fulfilled key can never be revoked
    by a Stripe event.
    """
    dynamodb.Table(API_KEYS_TABLE).update_item(
        Key={"api_key": api_key_str},
        UpdateExpression="SET bundle_d_access = :no",
        ExpressionAttributeValues={":no": False},
    )
    logger.info("bundle_d_access revoked (direct) api_key=%s", api_key_str[:16])


def _handle_bundle_d_direct_checkout(session: dict) -> None:
    """Provision Bundle D after a direct Stripe checkout. Mirrors
    _handle_llm_license_checkout's idempotency shape exactly."""
    stripe_customer_id     = session.get("customer") or ""
    stripe_subscription_id = session.get("subscription") or ""
    customer_email         = (session.get("customer_details") or {}).get("email") or ""

    record = _find_key_by_customer(stripe_customer_id)

    if record:
        api_key = record["api_key"]
        # Refuse to touch a key that came from AWS. If someone with a
        # Marketplace subscription also checks out on Stripe, that is exactly
        # the double-billing/disintermediation shape an audit looks for, and
        # silently flipping a flag on their AWS key would be the wrong repair.
        if record.get("aws_license_arn") or record.get("aws_account_id"):
            logger.error(
                "Bundle D direct checkout matched an AWS-fulfilled key, refusing to modify it. "
                "api_key=%s stripe_customer=%s sub=%s — resolve manually.",
                api_key[:16], stripe_customer_id, stripe_subscription_id,
            )
            return
        if not record.get("bundle_d_access"):
            _provision_bundle_d_direct(api_key, stripe_subscription_id)
            if customer_email:
                _send_bundle_d_direct_key_email(customer_email, api_key)
        else:
            logger.info("bundle_d_access already provisioned api_key=%s", api_key[:16])
    else:
        api_key = _issue_api_key(stripe_customer_id, stripe_subscription_id,
                                 customer_email, source="bundle_d_direct")
        _provision_bundle_d_direct(api_key, stripe_subscription_id)
        if customer_email:
            _send_bundle_d_direct_key_email(customer_email, api_key)
        else:
            logger.warning("Bundle D direct checkout with no email — key issued but not emailed, session=%s",
                           session.get("id"))


def _send_bundle_d_direct_key_email(to_email: str, api_key: str) -> None:
    subject = "Your RelayShield Agentic Attack Surface bundle is active"
    body = f"""Thanks for subscribing.

Your API key: {api_key}

Included endpoints:
  POST /v1/metered/tech-stack-cve
  POST /v1/metered/bulk-identity-risk
  POST /v1/metered/llm-credential-exposure
  POST /v1/metered/mcp-registry-risk
  POST /v1/metered/prompt-injection-breach

Send it as the X-RS-API-KEY header. Full reference and live examples:
https://api.relayshield.net/developers

Questions: support@relayshield.net

RelayShield
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
        logger.info("Bundle D direct key email sent to %s", to_email)
    except Exception as exc:
        logger.error("SES send failed (bundle_d_direct) to=%s error=%s", to_email, exc)


def _provision_bundle_a_direct(api_key_str: str, stripe_subscription_id: str) -> None:
    """Set bundle_a_access=True for a DIRECT Stripe purchase of Bundle A.

    Same flag the AWS Marketplace fulfilment path sets (see
    relayshield_bundle_fulfillment.py's core_identity_bundle_access ->
    bundle_a_access mapping), so one flag serves both doors.

    What is NOT set here, and must never be: aws_account_id, aws_customer_id
    and aws_license_arn. Their absence is what stops relayshield_api.py
    reporting a Stripe customer's usage to AWS through BatchMeterUsage, and
    what makes is_bundle_a_direct_call rather than is_bundle_a_call fire.
    """
    dynamodb.Table(API_KEYS_TABLE).update_item(
        Key={"api_key": api_key_str},
        UpdateExpression="SET bundle_a_access = :yes, stripe_subscription_id = :sid",
        ExpressionAttributeValues={":yes": True, ":sid": stripe_subscription_id},
    )
    logger.info("bundle_a_access provisioned (direct) api_key=%s", api_key_str[:16])


def _revoke_bundle_a_direct(api_key_str: str) -> None:
    """Set bundle_a_access=False on direct Bundle A cancellation.

    Only ever called for a subscription whose price is in
    BUNDLE_A_DIRECT_PRICE_IDS, so an AWS-fulfilled key can never be revoked
    by a Stripe event.
    """
    dynamodb.Table(API_KEYS_TABLE).update_item(
        Key={"api_key": api_key_str},
        UpdateExpression="SET bundle_a_access = :no",
        ExpressionAttributeValues={":no": False},
    )
    logger.info("bundle_a_access revoked (direct) api_key=%s", api_key_str[:16])


def _handle_bundle_a_direct_checkout(session: dict) -> None:
    """Provision Bundle A after a direct Stripe checkout. Mirrors
    _handle_bundle_d_direct_checkout exactly."""
    stripe_customer_id     = session.get("customer") or ""
    stripe_subscription_id = session.get("subscription") or ""
    customer_email         = (session.get("customer_details") or {}).get("email") or ""

    record = _find_key_by_customer(stripe_customer_id)

    if record:
        api_key = record["api_key"]
        # Refuse to touch a key that came from AWS -- the disintermediation
        # shape an audit looks for. Same guard as the Bundle D door.
        if record.get("aws_license_arn") or record.get("aws_account_id"):
            logger.error(
                "Bundle A direct checkout matched an AWS-fulfilled key, refusing to modify it. "
                "api_key=%s stripe_customer=%s sub=%s — resolve manually.",
                api_key[:16], stripe_customer_id, stripe_subscription_id,
            )
            return
        if not record.get("bundle_a_access"):
            _provision_bundle_a_direct(api_key, stripe_subscription_id)
            if customer_email:
                _send_bundle_a_direct_key_email(customer_email, api_key)
        else:
            logger.info("bundle_a_access already provisioned api_key=%s", api_key[:16])
    else:
        api_key = _issue_api_key(stripe_customer_id, stripe_subscription_id,
                                 customer_email, source="bundle_a_direct")
        _provision_bundle_a_direct(api_key, stripe_subscription_id)
        if customer_email:
            _send_bundle_a_direct_key_email(customer_email, api_key)
        else:
            logger.warning("Bundle A direct checkout with no email — key issued but not emailed, session=%s",
                           session.get("id"))


def _send_bundle_a_direct_key_email(to_email: str, api_key: str) -> None:
    subject = "Your RelayShield Core Identity Exposure bundle is active"
    # SIM swap is listed with its real status. It is a live paid endpoint that
    # currently returns 503 pending Twilio registration (#28883049), and a
    # welcome email that silently omits it would have the customer discover
    # that on their own. Founder's decision 2026-08-11: it stays in the copy.
    body = f"""Thanks for subscribing.

Your API key: {api_key}

Included endpoints, billed per call on top of the $150/mo access fee:

  POST /v1/metered/breach            $0.10   breach and dark web credential exposure
  POST /v1/metered/infostealer       $0.50   credentials harvested by stealer malware
  POST /v1/metered/domain            $0.30   typosquat and lookalike domain detection
  POST /v1/metered/oauth-watchlist   $0.30   leaked OAuth and API tokens
  POST /v1/metered/crypto-intel      $0.30   wallet and domain checks against our corpus
  POST /v1/metered/sim-swap          $0.25   recent SIM swap activity on a phone number

These are the same rates as the AWS Marketplace listing. Usage appears on your
monthly invoice as a single metered line.

Note on sim-swap: carrier registration is still in progress, so that endpoint
returns 503 today and is not billed while it does. We will email you when it
is live.

Send your key as the X-RS-API-KEY header. Full reference and live examples:
https://api.relayshield.net/developers

Questions: support@relayshield.net

RelayShield
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
        logger.info("Bundle A direct key email sent to %s", to_email)
    except Exception as exc:
        logger.error("SES send failed (bundle_a_direct) to=%s error=%s", to_email, exc)


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
Takes under a minute: solanadappstore://details?id=net.relayshield.cryptoshieldmobile

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
        # Bundles carry two items and Stripe does not guarantee order, so the
        # bundle branches below match against the whole set. Reading items[0]
        # alone meant a cancelled bundle subscription could fail to revoke and
        # the customer would keep access indefinitely. Fixed 2026-08-12.
        price_ids    = {i.get("price", {}).get("id") for i in items}
        if price_ids & BUNDLE_A_DIRECT_PRICE_IDS:
            record = _find_key_by_subscription(sub_id)
            if record:
                # A Stripe cancellation must never revoke an AWS entitlement.
                if record.get("aws_license_arn") or record.get("aws_account_id"):
                    logger.error("subscription.deleted (bundle_a_direct) matched an AWS-fulfilled key, "
                                 "refusing to revoke. api_key=%s sub=%s", record["api_key"][:16], sub_id)
                else:
                    _revoke_bundle_a_direct(record["api_key"])
            else:
                logger.warning("subscription.deleted (bundle_a_direct): no API key for sub=%s", sub_id)
            return {"statusCode": 200, "body": "ok"}
        if price_ids & BUNDLE_D_DIRECT_PRICE_IDS:
            record = _find_key_by_subscription(sub_id)
            if record:
                if record.get("aws_license_arn") or record.get("aws_account_id"):
                    logger.error("subscription.deleted (bundle_d_direct) matched an AWS-fulfilled key, "
                                 "refusing to revoke. api_key=%s sub=%s", record["api_key"][:16], sub_id)
                else:
                    _revoke_bundle_d_direct(record["api_key"])
            else:
                logger.warning("subscription.deleted (bundle_d_direct): no API key for sub=%s", sub_id)
            return {"statusCode": 200, "body": "ok"}
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
            # Bundles are checked FIRST and against the full item list, because
            # a bundle subscription has two items and the licensed price may not
            # be items[0]. Everything below this is single-item.
            price_ids = set(_get_subscription_price_ids(sub_id))
            if price_ids & BUNDLE_A_DIRECT_PRICE_IDS:
                logger.info("Bundle A direct checkout detected prices=%s sub=%s", sorted(price_ids), sub_id)
                _handle_bundle_a_direct_checkout(session)
                return {"statusCode": 200, "body": "ok"}
            if price_ids & BUNDLE_D_DIRECT_PRICE_IDS:
                logger.info("Bundle D direct checkout detected prices=%s sub=%s", sorted(price_ids), sub_id)
                _handle_bundle_d_direct_checkout(session)
                return {"statusCode": 200, "body": "ok"}

            price_id = next(iter(price_ids), None)
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
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="icon" href="/favicon.ico" sizes="any">
<title>RelayShield API: Security Intelligence for Developers</title>
<!--
  Discoverability block added 2026-07-30. Until then this page had NO meta
  description, NO Open Graph tags, no canonical and no structured data, while
  blog.relayshield.net and relayshield.net both had the full set. This is the
  page every blog post, integration listing and community message points at,
  so every one of those links rendered as a bare URL with no title card in
  Slack, Discord, LinkedIn, X and Telegram, throwing away the click-through
  at the last inch of a funnel we were paying for everywhere else.
-->
<meta name="description" content="Threat intelligence and identity-compromise APIs for developers and AI agents. 494K+ distinct indicators (5.8M+ sightings) from 95 monitored channels and 20 feeds. Breach, infostealer, SIM-swap, LLM credential exposure, MCP registry risk. Pay-as-you-go, no minimum.">
<link rel="canonical" href="https://api.relayshield.net/developers">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large">

<meta property="og:type" content="website">
<meta property="og:site_name" content="RelayShield">
<meta property="og:url" content="https://api.relayshield.net/developers">
<meta property="og:title" content="RelayShield API: Security Intelligence for Developers &amp; Agents">
<meta property="og:description" content="494K+ distinct indicators (5.8M+ sightings) from 95 monitored channels and 20 authoritative feeds. Breach, infostealer, SIM-swap, LLM credential exposure and MCP registry risk, over REST, MCP, STIX/TAXII and x402. Pay-as-you-go, no minimum.">
<meta property="og:image" content="https://blog.relayshield.net/developers-og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="RelayShield API: security intelligence for developers and agents">

<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="RelayShield API: Security Intelligence for Developers &amp; Agents">
<meta name="twitter:description" content="494K+ distinct indicators (5.8M+ sightings) from 95 monitored channels and 20 authoritative feeds. REST, MCP, STIX/TAXII and x402. Pay-as-you-go, no minimum.">
<meta name="twitter:image" content="https://blog.relayshield.net/developers-og.png">

<link rel="alternate" type="application/json" href="https://api.relayshield.net/openapi.json" title="RelayShield OpenAPI specification">
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": "https://relayshield.net/#org",
      "name": "RelayShield",
      "url": "https://relayshield.net",
      "email": "support@relayshield.net"
    },
    {
      "@type": "WebAPI",
      "name": "RelayShield API",
      "description": "Threat intelligence and identity-compromise APIs for developers and AI agents, covering breach exposure, infostealer logs, SIM-swap, domain lookalikes, LLM credential exposure and MCP registry risk.",
      "url": "https://api.relayshield.net/developers",
      "documentation": "https://api.relayshield.net/developers",
      "provider": {"@id": "https://relayshield.net/#org"},
      "termsOfService": "https://relayshield.net",
      "potentialAction": {
        "@type": "ConsumeAction",
        "target": "https://api.relayshield.net/openapi.json"
      }
    }
  ]
}
</script>
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

  /* Long unbroken tokens (URLs, header values, keys) must wrap rather than
     overflow their container. Without this the TAXII collection URL in the
     Elastic callout bled outside its border on a phone. `anywhere` also lets
     the box shrink to the viewport, which `break-word` alone does not. */
  code { overflow-wrap: anywhere; word-break: break-word; }

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
  .section-title { font-size: 1.4rem; font-weight: 700; margin: 0 0 .4rem; }
  h2.section-title, h3.section-title { line-height: 1.25; }
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

  /* Mobile. Added 2026-08-09: this page had NO media query at all, on any
     breakpoint, which is why the signup CTA overflowed its box on a phone.
     The direct cause was button[type=submit] carrying white-space:nowrap
     inside a non-wrapping flex row, so the button could not shrink and simply
     pushed out of the container. That button is the primary conversion action
     on the page, and rsscan and the MetaMask Snap both send arrivals who are
     plausibly on a phone. */
  @media (max-width: 640px) {
    nav { padding: .9rem 1.1rem; }
    .hero { margin-top: 2.5rem; padding: 0 1.1rem; }
    .section { padding-left: 1.1rem; padding-right: 1.1rem; }

    /* The actual bug: stack the field and the button instead of letting a
       nowrap button overflow. */
    .input-row { flex-direction: column; }
    .signup-box { padding: 1.4rem 1.1rem; }
    .signup-box button[type=submit] { width: 100%; padding-top: .8rem; padding-bottom: .8rem; }

    /* A fixed two-column grid cannot survive a 375px viewport. */
    .section div[style*="grid-template-columns:1fr 1fr"] { grid-template-columns: 1fr !important; }

    /* The TI tier table is wider than a phone. Let it scroll in place rather
       than widening the whole document and creating a horizontal page scroll. */
    table { display: block; width: 100%; overflow-x: auto; }

    pre { padding: 1rem .9rem; font-size: .76rem; }
  }

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
  <p>Breach detection, SIM swap monitoring, infostealer exposure, domain lookalike scanning, and live threat intelligence. REST API, priced per call.</p>
  <p style="margin-top:.6rem;font-size:1rem;color:var(--text)"><strong>Every comparable threat intelligence platform is quote-only.</strong> You book a call to find out the price, then pay per API key <em>and</em> per user seat, on an annual contract. RelayShield publishes every price on this page. One key, no seat fees, no minimum, no contract, no call. A breach check is $0.10 and you can run one in the next two minutes.</p>

  <!-- AWS Marketplace notice. Wording is deliberately verbatim from the
       UsageInstructions field AWS has already passed in audit, see TODO
       AGENTIC-6. Do not reword without re-reading that note. -->
  <div style="background:rgba(0,181,165,.08);border:1px solid rgba(0,181,165,.35);border-radius:10px;padding:1rem 1.25rem;margin-top:1.5rem;font-size:.9rem;color:var(--text);line-height:1.6">
    <strong style="color:var(--accent2,#00B5A5)">AWS Marketplace subscribers:</strong> your API key is provisioned
    automatically when your subscription activates. No separate account or payment method is required; all billing is
    handled by AWS Marketplace.
  </div>

  <div class="signup-box">
    <p><strong style="color:var(--accent)">100 free calls, no card required.</strong> Enter your email and your API key arrives instantly.</p>
    <form id="signup-form">
      <div class="input-row">
        <input type="email" id="email-input" placeholder="you@company.com" required autocomplete="email">
        <button type="submit" id="submit-btn">Get API key →</button>
      </div>
      <div id="form-error"></div>
    </form>
    <p class="form-note">No credit card · No subscription · Add a card only when your free calls run out</p>
  </div>

  <div style="background:rgba(108,99,255,.08);border:1px solid rgba(108,99,255,.25);border-radius:10px;padding:1rem 1.25rem;margin-top:1.25rem;font-size:.9rem;color:var(--text);line-height:1.6">
    <strong style="color:var(--accent)">How billing works:</strong> Every new key gets
    <strong>100 free calls with no payment method</strong>, enough to scan a domain, check a
    team's worth of employee emails, and have a real finding to show someone. When they run out, add
    a card and you are billed monthly for calls made, with no minimum and no subscription fee. Ten
    breach checks cost $1.00.
    Customers who subscribe through AWS Marketplace never add a payment method. Access is
    provisioned automatically and all billing is handled by AWS.
  </div>

  <!-- The subscriptions used to be disclosed here, one screen under a headline
       promising "no monthly minimum, no commitments". The page argued against
       its own hero before the reader reached the price list. They are still
       fully disclosed, just where they belong: in their own sections, below the
       per-call catalogue the hero is actually describing. -->
  <p style="margin-top:1rem;font-size:.88rem;color:var(--muted)">
    Prefer a flat rate? There are optional subscriptions for
    <a href="#llmjacking-license">LLMjacking detection</a> and
    <a href="#threat-intelligence">bulk threat intelligence</a>. Neither is required to use the API.
  </p>
</div>

<div class="section">
  <h2 class="section-title" id="from-rsscan">Came here from rsscan?</h2>
  <div class="section-sub">The scanner runs locally and reads your diff, so it catches the credential that is about to leak. This API answers the other half.</div>
  <div style="background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:8px;padding:1.15rem 1.25rem;margin:1.25rem 0 0;line-height:1.6">
    <p style="margin:0 0 .85rem"><code>rsscan</code> cannot see a credential that already left: committed months ago, shipped in a published package, or sitting in a public artifact somebody else owns. Those are the ones already being sold.</p>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:1rem;margin:1rem 0 .85rem">
      <div style="background:var(--bg,rgba(0,0,0,.15));border:1px solid var(--border);border-radius:8px;padding:.85rem 1rem">
        <div style="font-family:monospace;color:var(--accent);font-size:.85rem;margin-bottom:.35rem">/v1/metered/secret-scan</div>
        <div style="color:var(--muted);font-size:.87rem">Finds keys already published across GitHub, npm, PyPI, Docker Hub and Postman. $0.35 a call.</div>
      </div>
      <div style="background:var(--bg,rgba(0,0,0,.15));border:1px solid var(--border);border-radius:8px;padding:.85rem 1rem">
        <div style="font-family:monospace;color:var(--accent);font-size:.85rem;margin-bottom:.35rem">/v1/metered/nhi-exposure</div>
        <div style="color:var(--muted);font-size:.87rem">Finds machine credentials and tokens inside criminal infostealer logs, where a leaked key ends up after it is stolen rather than published. $0.40 a call.</div>
      </div>
    </div>
    <p style="margin:0;color:var(--muted);font-size:.9rem">Run <code>rsscan --org</code> and it reports across your whole organisation instead of one checkout. That output is the thing worth forwarding to whoever owns security where you work, and your 100 free calls are enough to produce it.</p>
  </div>
</div>

<div class="section">
  <h2 class="section-title" id="endpoints">Endpoints &amp; pricing</h2>
  <div class="section-sub">Pay only for what you use. Billed monthly. No monthly minimum. Low-volume ad-hoc testing costs pennies: a 10-call integration test runs $0.10 to $0.50 total.</div>
  <!-- Docs callout added 2026-08-04. The cards below give the price and a one-line
       summary of each endpoint, which is what a buyer needs, but a developer
       evaluating the API needs parameters, response attributes and errors, the
       exact gap Zapier's partner review raised. Placed at the top of this section
       rather than in the footer so it is seen by anyone scanning the endpoint list
       and wondering what the request body looks like. -->
  <div style="background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:8px;padding:1rem 1.15rem;margin:1.25rem 0 1.5rem">
    <div style="font-weight:650;margin-bottom:.35rem">Full API reference</div>
    <div style="color:var(--muted);font-size:.94rem;line-height:1.55">
      Every endpoint below is documented with its request parameters, response attributes,
      error codes and a worked example at
      <a href="/docs">api.relayshield.net/docs</a>.
      The machine-readable OpenAPI 3.1 specification is at
      <a href="/openapi.json">api.relayshield.net/openapi.json</a>. Point your client
      generator at it directly.
    </div>
  </div>
  <div class="price-grid">
    <div class="price-card">
      <div class="endpoint">/v1/metered/breach</div>
      <div class="price">$0.10<span class="per"> / call</span></div>
      <div class="desc">Email breach check: breach name, date, and exposed data classes across 13B+ compromised accounts</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/sim-swap</div>
      <div class="price">$0.25<span class="per"> / call</span></div>
      <div class="desc">SIM swap detection via telco carrier lookup database: confirms whether a number has been ported or swapped, with carrier name and swap timestamp</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/infostealer</div>
      <div class="price">$0.50<span class="per"> / call</span></div>
      <div class="desc">Infostealer malware log check: a single infected device exposes every saved password across 50+ services simultaneously: banking credentials, credit card autofill, email, SaaS tools, and active session cookies that bypass 2FA. Returns infection date, OS, malware path, and at-risk service counts</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/domain</div>
      <div class="price">$0.30<span class="per"> / call</span></div>
      <div class="desc">Typosquat domain scan: active lookalikes via DNS + cert transparency</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/oauth-watchlist</div>
      <div class="price">$0.30<span class="per"> / call</span></div>
      <div class="desc">OAuth &amp; token exposure: combines breach history watchlist with live stealer log corpus. Detects stolen credentials and OAuth tokens with category-level severity scores: cloud consoles and code repositories (CRITICAL), identity providers and payment processors (HIGH), productivity SaaS (MEDIUM)</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/supply-chain</div>
      <div class="price">$0.10<span class="per"> / call</span></div>
      <div class="desc">Vendor / supply chain risk: breach exposure + infostealer hits per vendor domain. Up to 10 domains per call. Returns per-domain risk score: CRITICAL · HIGH · MEDIUM · LOW</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/session-risk</div>
      <div class="price">$0.30<span class="per"> / call</span></div>
      <div class="desc">Active session hijack detection: identifies stolen session cookies in criminal stealer log archives before attackers use them. Detects AiTM attacks that bypass 2FA without needing the user&apos;s password. Returns severity-ranked results by service category</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/identity-graph</div>
      <div class="price">$0.35<span class="per"> / call</span></div>
      <div class="desc">Identity correlation: links an email to associated phone numbers and domains seen alongside it in criminal channel dumps. Pivot from one compromised identifier to find all others exposed in the same breach or stealer log</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/ransomware-risk</div>
      <div class="price">$0.40<span class="per"> / call</span></div>
      <div class="desc">Ransomware victim check: queries 100+ active ransomware group leak sites. Returns victim list status, responsible group(s), and count of pre-ransomware credentials found in stealer logs before the incident</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/nhi-exposure</div>
      <div class="price">$0.40<span class="per"> / call</span></div>
      <div class="desc">Non-human identity (NHI) detection: scans stealer log corpus for API keys, tokens, and machine credentials (AWS IAM keys, GitHub PATs, Stripe secrets, private keys, Slack tokens) linked to your domain or vendor supply chain domains</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/secret-scan</div>
      <div class="price">$0.35<span class="per"> / call</span></div>
      <div class="desc">Public artifact secret detection across <strong>six sources</strong>, GitHub repositories, <strong>npm</strong> and <strong>PyPI</strong> packages, <strong>Docker Hub</strong> images, <strong>Hugging Face</strong> models and Spaces, and <strong>Postman</strong> public workspaces and collections, for secrets (API keys, tokens, private keys) already published against your domain. Secrets ship inside released packages and images constantly, and repo-only scanners never see them. Every hit is verified against the matching credential pattern before it is reported, so a docs example or a placeholder is not billed to you as a CRITICAL. Covers your own domain and vendor supply-chain domains</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/target-risk</div>
      <div class="price">$0.50<span class="per"> / call</span></div>
      <div class="desc">Target probability scoring: correlates 6 threat signals (ransomware victim listing, stealer log hits, breach exposure, criminal channel mentions, high-EPSS CVEs, pre-ransomware credentials) into a 0 to 100 risk score with 4-tier rating and recommended action</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/crypto-intel</div>
      <div class="price">$0.30<span class="per"> / call</span></div>
      <div class="desc">Crypto asset surface: wallet address risk, token honeypot &amp; tax flags, NFT contract risk, counterparty screening across EVM, Solana, TON, and Bitcoin</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/asset-intel</div>
      <div class="price">$0.15<span class="per"> / call</span></div>
      <div class="desc">Asset watchlist &amp; continuous monitoring: register domains and IPs for ongoing IOC surveillance. Actions: <code>register</code> assets, <code>sweep</code> all registered assets against the 494K+ distinct indicator corpus (5.8M+ sightings), <code>list</code> or <code>remove</code>. Webhook push alerts fire automatically when new IOCs match your registered assets</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/threat-actor</div>
      <div class="price">$0.30<span class="per"> / call</span></div>
      <div class="desc">Threat actor intelligence: two actions in one endpoint. <code>exploit-chatter</code>: detect pre-publication CVE PoC discussion in criminal channels before NVD/KEV publication, with EPSS score and KEV status. <code>actor-lookup</code>: track a threat actor or malware campaign (e.g. LummaC2, APT29), returns IOC count, IOC breakdown by type, MITRE ATT&amp;CK group info, aliases, and techniques</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/cve-identity-risk</div>
      <div class="price">$0.40<span class="per"> / call</span></div>
      <div class="desc">CVE × identity risk correlation: pass a CVE ID and domain to get a composite risk score (0 to 100) combining CISA KEV status, EPSS exploitation probability, infostealer corpus hits for exploiting malware families, ransomware victim listing, and exploit chatter signals. The only API that closes the loop from vulnerability to live identity exposure for a specific organization</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/identity-risk-score</div>
      <div class="price">$0.35<span class="per"> / call</span></div>
      <div class="desc">Domain identity risk score: a security credit score (0 to 100, grade A to F) for any domain across 6 dimensions: breach exposure, infostealer density, IOC corpus presence, ransomware victim listing, active session exposure, and CVE exposure. MSPs can embed this in client QBRs, insurance renewal reports, and onboarding risk assessments</div>
    </div>
    <p style="margin:1.5rem 0 .75rem;padding:.9rem 1.1rem;background:rgba(108,99,255,.07);border:1px solid rgba(108,99,255,.2);border-radius:8px;font-size:.9rem;color:var(--muted)">
      <strong style="color:var(--accent)">🤗 Try the Agentic Attack Surface live on Hugging Face</strong>. No signup required to explore the MCP schema.
      <a href="https://huggingface.co/spaces/relayshieldadmin/relayshield-agentic-attack-surface" target="_blank" rel="noopener" style="color:var(--accent)">Space</a>
      · <a href="https://huggingface.co/blog/relayshieldadmin/relayshield-agentic-attack-surface-mcp" target="_blank" rel="noopener" style="color:var(--accent)">announcement post</a>
    </p>
    <div class="price-card" id="ep-tech-stack-cve">
      <div class="endpoint">/v1/metered/tech-stack-cve</div>
      <div class="price">$0.20<span class="per"> / call</span></div>
      <div class="desc">Agent framework &amp; tech stack exploit monitoring: pass a declared tech stack (or a domain to pull its stored stack) and get back CISA KEV / high-EPSS CVEs actively targeting it. Covers AI agent orchestration frameworks (Langflow, LangChain, AutoGPT, CrewAI, Flowise, n8n self-hosted) and their common companion infrastructure (Nacos, MinIO), the exact vector used in the first documented autonomous-AI-agent ransomware operation (JadePuffer, July 2026)</div>
    </div>
    <div class="price-card" id="ep-mcp-registry-risk">
      <div class="endpoint">/v1/metered/mcp-registry-risk</div>
      <div class="price">$0.35<span class="per"> / call</span></div>
      <div class="desc">MCP server &amp; agent-tool registry reputation: checks an MCP server URL or package name against RelayShield's criminal IOC corpus, typosquat/near-miss detection against well-known MCP domains, and domain registration age. Early-mover coverage for the MCP ecosystem, where dedicated security tooling is still minimal industry-wide</div>
    </div>
    <div class="price-card" id="ep-prompt-injection-breach">
      <div class="endpoint">/v1/metered/prompt-injection-breach</div>
      <div class="price">$0.35<span class="per"> / call</span></div>
      <div class="desc">Prompt-injection-sourced breach detection: flags stolen session/credential exposure whose source dump text suggests an AI agent (rather than a traditional phishing/malware campaign) was involved in obtaining it. A best-effort signal based on how the breach was described, not a confirmed attribution</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/bulk-ioc</div>
      <div class="price">$0.50<span class="per"> / batch (up to 100 IOCs)</span></div>
      <div class="desc">Bulk IOC enrichment: submit up to 100 indicators in a single call. Built for SIEM log-enrichment pipelines. Returns malware family, threat actor, confidence score, and first/last seen for each indicator</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/ioc-pivot</div>
      <div class="price">$0.20<span class="per"> / call</span></div>
      <div class="desc">IOC pivot: given one known-malicious indicator, discover all related infrastructure sharing the same malware family. Surfaces full C2 networks from a single indicator</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/brand-monitor</div>
      <div class="price">$0.35<span class="per"> / call</span></div>
      <div class="desc">Brand monitoring: scans the full IOC corpus for your brand name. Returns phishing domains, malware C2 infrastructure referencing your name, dark web mentions, and image/logo mentions extracted via OCR from infostealer-archive screenshots</div>
    </div>
    <div class="price-card" id="ep-card-exposure">
      <div class="endpoint">/v1/metered/card-exposure</div>
      <div class="price">$0.30<span class="per"> / call</span></div>
      <div class="desc">Stolen payment card exposure check: pass a client-computed SHA-256 hash of a card number, or just a 6-8 digit BIN, to check against RelayShield's stolen-card corpus (sourced from infostealer logs). RelayShield never accepts or stores a raw card number</div>
    </div>
    <div class="price-card" id="ep-bulk-identity-risk">
      <div class="endpoint">/v1/metered/bulk-identity-risk</div>
      <div class="price">$2.00<span class="per"> / call</span></div>
      <div class="desc">Hierarchical org + agent-level risk scoring: up to 10 organizational domains plus up to 5 agent/service-account identities per domain in a single call. Each domain returns a 0 to 100 risk score across 6 dimensions; each agent identity returns breach, infostealer, and stolen-session signals. A critically exposed agent automatically elevates the organizational risk rating. Purpose-built for MSP weekly client sweeps and AI agent governance use cases</div>
    </div>
    <div class="price-card" id="ep-cert-expiry">
      <div class="endpoint">/v1/metered/cert-expiry</div>
      <div class="price">$0.05<span class="per"> / call</span></div>
      <div class="desc">TLS certificate expiry &amp; renewal risk: checks Certificate Transparency logs for how many days remain before a domain&apos;s live certificate expires. Returns a 4-tier risk level (CRITICAL/HIGH/MEDIUM/LOW) and a plain-English recommendation. Increasingly relevant as CA/Browser Forum rules shrink standard certificate lifespans toward 47 days by 2029</div>
    </div>
    <div class="price-card" id="ep-ip-intel">
      <div class="endpoint">/v1/metered/ip-intel</div>
      <div class="price">$0.10<span class="per"> / call</span></div>
      <div class="desc">Passive DNS &amp; IP reputation: pass a domain to get its historical IP resolution history plus reputation, or pass an IP to get reverse resolution history (hostnames that have pointed to it), AS owner, country, and malicious/suspicious vendor detection counts</div>
    </div>
  </div>
</div>

<div class="section" style="margin-top:2rem">
  <h2 class="section-title" id="account-endpoints">Account &amp; integration endpoints</h2>
  <p style="color:var(--muted);font-size:.95rem;margin:.5rem 0 1.25rem">Free to call and not metered. These support key validation and webhook delivery, and are the endpoints our published integrations (Zapier, n8n, Make) use to verify a connection and register alert delivery.</p>
  <div class="price-grid" style="grid-template-columns: repeat(auto-fit, minmax(260px, 1fr))">
    <div class="price-card" id="ep-account-info">
      <div class="endpoint">/v1/account/info</div>
      <div class="price">Free<span class="per"> / call</span></div>
      <div class="desc"><strong>POST</strong>: returns the account behind the API key. Send an empty JSON body. Response: <code>plan</code>, <code>intel_access</code>, <code>calls_this_month</code>, <code>customer_id</code>, <code>email</code>, <code>active</code>. Used to confirm a key is live, and by integrations to label a connected account. Returns <code>401</code> if the key is missing, invalid or inactive.</div>
    </div>
    <div class="price-card" id="ep-webhook-configure">
      <div class="endpoint">/v1/webhook/configure</div>
      <div class="price">Free<span class="per"> / call</span></div>
      <div class="desc"><strong>POST</strong>: registers a URL to receive findings (breach, infostealer, session hijack, ransomware victim listing) as they are detected, instead of polling. Body: <code>{"webhook_url": "https://..."}</code>. Response: <code>{"webhook_url": "...", "status": "registered"}</code>. Posting an empty <code>webhook_url</code> clears the registration and returns <code>status: "cleared"</code>.</div>
    </div>
  </div>
  <pre style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem;overflow-x:auto;font-size:.82rem;margin-top:1rem"><code>curl -X POST https://api.relayshield.net/v1/account/info \
  -H "X-RS-API-KEY: rs_live_YOUR_KEY" \
  -H "Content-Type: application/json" -d '{}'

curl -X POST https://api.relayshield.net/v1/webhook/configure \
  -H "X-RS-API-KEY: rs_live_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"webhook_url": "https://hooks.example.com/relayshield"}'</code></pre>
</div>

<div class="section" style="margin-top:2rem">
  <h2 class="section-title" id="aws-bundles">Buy through AWS Marketplace</h2>
  <div class="section-sub">Same API, same keys, billed against your existing AWS account. No new vendor to onboard, no separate payment method, and it draws down committed spend.</div>
  <p style="color:var(--muted);font-size:.92rem;margin:1rem 0 1.25rem">If procurement is the reason a card is hard to get approved, this is the route around it. Your API key is provisioned automatically the moment the subscription activates.</p>
  <div class="price-grid" style="grid-template-columns:repeat(auto-fit,minmax(260px,1fr))">
    <div class="price-card" style="border-color:var(--accent)">
      <div class="endpoint" style="color:var(--accent)">Agentic Attack Surface</div>
      <div class="desc" style="margin-top:.5rem">MCP registry risk, prompt-injection breach correlation, agent-framework CVE targeting, bulk per-agent identity risk scoring, and LLM credential exposure detection. Licensed on its own, with no dependency on any other bundle.</div>
      <a href="https://aws.amazon.com/marketplace/pp/prodview-6p6csngrcg3zq" style="display:block;margin-top:1rem;background:var(--accent);color:#fff;text-align:center;padding:.5rem;border-radius:6px;text-decoration:none;font-size:.85rem;font-weight:600">View on AWS Marketplace</a>
    </div>
    <div class="price-card">
      <div class="endpoint" style="color:var(--accent)">Core Identity Exposure</div>
      <div class="desc" style="margin-top:.5rem">Breach exposure, SIM swap detection, infostealer log checks, domain lookalike detection, OAuth token exposure, and crypto threat intelligence. Six identity detection APIs as one metered bundle. $150/mo minimum commitment plus usage from $0.10 per call.</div>
      <a href="https://aws.amazon.com/marketplace/pp/prodview-zgdxyqfd63hog" style="display:block;margin-top:1rem;background:var(--accent);color:#fff;text-align:center;padding:.5rem;border-radius:6px;text-decoration:none;font-size:.85rem;font-weight:600">View on AWS Marketplace</a>
    </div>
  </div>
</div>

<div class="section" style="margin-top:2rem">
  <h2 class="section-title" id="llmjacking-license">LLMjacking Detection License <span style="background:var(--accent);color:#fff;font-size:.7rem;padding:.15rem .5rem;border-radius:4px;margin-left:.5rem;vertical-align:middle">NEW</span></h2>
  <p style="color:var(--muted);font-size:.95rem;margin:.5rem 0 1.25rem">Stolen LLM API keys drain a company&apos;s AI budget, not its data. Real incidents have run $46K/day to $500K/month from a single leaked key, while the underground price for a stolen key is about $30. <code>llm-credential-exposure</code> scans our criminal stealer-log corpus for exposed keys across <strong>14 LLM and AI providers</strong> tied to your domain: OpenAI, Anthropic Claude, Google Gemini, xAI Grok, Amazon Bedrock, Groq, Replicate, LangSmith, Hugging Face, NVIDIA NIM, DeepSeek, Moonshot Kimi, Alibaba Qwen and Alibaba Cloud. Available pay-per-call at $0.40 on any metered key, or as a dedicated unlimited-call license below.</p>
  <div style="background:var(--surface);border:1px solid var(--accent);border-radius:8px;padding:.85rem 1rem;margin:0 0 1.25rem;font-size:.85rem">
    <strong style="color:var(--accent)">Coverage standard secret scanners miss.</strong> <span style="color:var(--muted)">Gitleaks, the most widely deployed open-source secret scanner, ships <strong>zero</strong> detection rules for DeepSeek, Moonshot, Qwen or NVIDIA. Shadow-AI keys from those providers are invisible to conventional scanning. And a single leaked Hugging Face token bills against DeepSeek, Qwen, Kimi and NVIDIA models through Inference Providers without the attacker ever holding a vendor key. We are not scanning your repos for keys you might leak. We scan the criminal channels where leaked keys are already being sold.</span>
  </div>
  <div class="price-grid" style="grid-template-columns: repeat(auto-fit, minmax(220px, 1fr))">
    <div class="price-card" style="border-color:var(--accent)">
      <div class="endpoint" style="color:var(--accent)">/v1/metered/llm-credential-exposure</div>
      <div class="price">$39<span class="per"> / mo</span></div>
      <div class="desc">Unlimited calls to the LLMjacking detection endpoint: no per-call metering, no other endpoints included. Auto-provisions or upgrades your existing API key.</div>
      <a href="https://buy.stripe.com/9B600k92u2uFgde0Bx0Ny0i" style="display:block;margin-top:1rem;background:var(--accent);color:#fff;text-align:center;padding:.5rem;border-radius:6px;text-decoration:none;font-size:.85rem;font-weight:600">Subscribe: $39/mo</a>
    </div>
    <div class="price-card" style="border-color:var(--accent)">
      <div class="endpoint" style="color:var(--accent)">/v1/metered/llm-credential-exposure</div>
      <div class="price">$399<span class="per"> / yr</span></div>
      <div class="desc">Same unlimited-call license, billed annually, just under 2 months free vs. paying monthly.</div>
      <a href="https://buy.stripe.com/fZu4gA4Mec5f3qs4RN0Ny0j" style="display:block;margin-top:1rem;background:var(--accent);color:#fff;text-align:center;padding:.5rem;border-radius:6px;text-decoration:none;font-size:.85rem;font-weight:600">Subscribe: $399/yr</a>
    </div>
  </div>
</div>

<div class="section" style="margin-top:2rem">
  <h2 class="section-title" id="threat-intelligence">Threat Intelligence API <span style="background:var(--accent);color:#fff;font-size:.7rem;padding:.15rem .5rem;border-radius:4px;margin-left:.5rem;vertical-align:middle">NEW</span></h2>
  <p style="color:var(--muted);font-size:.95rem;margin:.5rem 0 1.25rem">RelayShield&apos;s edge is OSINT threat hunting most vendors can&apos;t reach: our own collection pipeline runs continuous, verified monitoring across <strong>95 monitored channels</strong> (infostealer markets, credential dumps, breach announcements), not a static feed subscription. That&apos;s layered with <strong>494K+ distinct indicators</strong> (5.8M+ sightings) aggregated from <strong>20 authoritative external sources</strong> (abuse.ch, Spamhaus, AbuseIPDB, AlienVault OTX, PhishTank, CISA KEV, MITRE ATT&amp;CK/ATLAS, and more). Emails, domains, IPs, hashes, phone numbers, and wallet addresses, <strong>24 to 72 hours ahead of public breach databases.</strong></p>
  <p style="color:var(--muted);font-size:.9rem;margin:.5rem 0 1.25rem;background:rgba(108,99,255,.07);border:1px solid rgba(108,99,255,.2);border-radius:8px;padding:.75rem 1rem"><strong style="color:var(--accent)">All 26 metered endpoints included.</strong> Both TI subscription tiers cover unlimited access to all metered API endpoints above: breach, SIM swap, infostealer, domain, OAuth &amp; token exposure, supply chain, session hijack detection, crypto asset surface, asset intel monitoring, threat actor intelligence, CVE × identity risk correlation, domain identity risk scoring, bulk IOC enrichment, IOC pivot, brand monitoring, bulk identity risk, agent framework exploit monitoring, MCP registry risk, prompt-injection breach detection, certificate expiry risk, and passive DNS/IP reputation, in addition to the Threat Intelligence IOC and CVE feeds. No per-endpoint add-ons. One subscription, full access.</p>
  <table style="width:100%;border-collapse:collapse;font-size:.88rem;margin-bottom:1.5rem">
    <thead>
      <tr style="border-bottom:1px solid var(--border)">
        <th style="text-align:left;padding:.5rem .75rem;color:var(--muted);font-weight:600"></th>
        <th style="text-align:center;padding:.5rem .75rem;color:var(--accent);font-weight:700">MSP: $499/mo</th>
        <th style="text-align:center;padding:.5rem .75rem;color:var(--accent);font-weight:700">MSSP: $999/mo</th>
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
        <td style="text-align:center;padding:.45rem .75rem" colspan="2">24 to 72 hours</td>
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
      <div class="desc">In-house SOC teams: up to 10,000 calls/month across all endpoints. Includes IOC lookup, CVE intelligence, and all 8 metered endpoints. Embed in SOAR playbooks, SIEM enrichment, or incident response workflows.</div>
      <a href="https://buy.stripe.com/28EcN66Umb1be56bgb0Ny0e" style="display:block;margin-top:1rem;background:var(--accent);color:#fff;text-align:center;padding:.5rem;border-radius:6px;text-decoration:none;font-size:.85rem;font-weight:600">Subscribe: $499/mo</a>
    </div>
    <div class="price-card" style="border-color:var(--accent)">
      <div class="endpoint" style="color:var(--accent)">/v1/intel/telegram</div>
      <div class="price">$999<span class="per"> / mo</span></div>
      <div class="desc">MSSPs &amp; MDRs: unlimited calls across all endpoints, priority support + SLA. Includes IOC lookup, CVE intelligence, and all 8 metered endpoints. For teams running continuous enrichment pipelines across multiple client environments.</div>
      <a href="https://buy.stripe.com/4gM3cw1A23yJf9a2JF0Ny0f" style="display:block;margin-top:1rem;background:var(--accent);color:#fff;text-align:center;padding:.5rem;border-radius:6px;text-decoration:none;font-size:.85rem;font-weight:600">Subscribe: $999/mo</a>
    </div>
  </div>


  <div style="margin-top:2rem">
    <h3 class="section-title" style="font-size:1rem;margin-bottom:.75rem">CVE &amp; Ransomware Intelligence</h3>
    <p style="color:var(--muted);font-size:.9rem;margin-bottom:1rem">Look up CISA Known Exploited Vulnerabilities by CVE ID or keyword, cross-referenced for active ransomware campaign activity. Included on all TI subscription tiers.</p>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;font-size:.85rem">
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem">
        <div style="font-family:monospace;color:var(--accent);margin-bottom:.5rem">POST /v1/intel/cve</div>
        <div style="color:var(--muted);margin-bottom:.75rem">Exact CVE ID lookup</div>
        <pre style="background:var(--bg);border-radius:6px;padding:.75rem;font-size:.78rem;overflow-x:auto"><span class="str">{"cve_id": "CVE-2024-1234"}</span></pre>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem">
        <div style="font-family:monospace;color:var(--accent);margin-bottom:.5rem">POST /v1/intel/cve</div>
        <div style="color:var(--muted);margin-bottom:.75rem">Keyword scan: vendor, product, or CVE name</div>
        <pre style="background:var(--bg);border-radius:6px;padding:.75rem;font-size:.78rem;overflow-x:auto"><span class="str">{"keyword": "apache"}</span></pre>
      </div>
    </div>
    <div style="margin-top:.75rem;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem;font-size:.83rem;color:var(--muted)">
      <strong style="color:var(--text)">Response includes:</strong> CVE ID · vendor/product · vulnerability name · date added to KEV ·
      <span style="color:#f87171;font-weight:600">ransomware_campaign_use</span> flag · known ransomware groups
    </div>
  </div>

  <div style="margin-top:2rem">
    <h3 class="section-title" style="font-size:1rem;margin-bottom:.75rem">Automated Feed Formats: STIX/TAXII, MISP &amp; SIEM/SOAR Push</h3>
    <p style="color:var(--muted);font-size:.9rem;margin-bottom:1rem">Pull our IOC corpus with your SIEM's built-in TAXII client or MISP instance. No custom integration work, both require a TI subscription and support incremental pulls via <code>added_after</code> + pagination. Or configure a destination once and have real-time findings pushed to you as they fire.</p>
    <div style="background:var(--surface);border:1px solid var(--accent);border-radius:8px;padding:.85rem 1rem;margin-bottom:1rem;font-size:.85rem">
      <strong style="color:var(--accent)">Elastic Security users:</strong> <span style="color:var(--muted)">RelayShield works with Elastic's built-in <em>Custom Threat Intelligence</em> integration (switch on <em>Enable TAXII 2.1</em>) or its <em>MISP</em> integration, configuration only, no connector to build. Point it at <code>https://api.relayshield.net/v1/intel/taxii/collections/iocs/objects/</code> with <code>Authorization: Bearer YOUR_API_KEY</code>. <a href="https://blog.relayshield.net/elastic-security-threat-intelligence-integration" style="color:var(--accent)">Full step-by-step guide &rarr;</a></span>
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem;font-size:.85rem">
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem">
        <div style="font-family:monospace;color:var(--accent);margin-bottom:.5rem">GET /v1/intel/taxii/*</div>
        <div style="color:var(--muted)">STIX 2.1 compliant feed: Indicator objects for Splunk, Sentinel, Elastic, or QRadar's built-in TAXII client.</div>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem">
        <div style="font-family:monospace;color:var(--accent);margin-bottom:.5rem">GET /v1/intel/misp/event</div>
        <div style="color:var(--muted)">Native MISP Event JSON with tagged Attributes, the default/co-primary format for government, CERT/ISAC, and mid-market SOC tooling that STIX-only integration doesn't reach.</div>
      </div>
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem">
        <div style="font-family:monospace;color:var(--accent);margin-bottom:.5rem">POST /v1/siem/configure</div>
        <div style="color:var(--muted)">Push delivery to Splunk HEC, CEF/QRadar, or Cortex XSOAR's Generic Webhook incident-creation shape. Configure a destination once, then real-time findings from breach, domain, infostealer, SIM swap, OAuth, and dark-web-channel monitoring dispatch automatically, no polling required.</div>
      </div>
    </div>
  </div>

  <div style="margin-top:2rem">
    <h3 class="section-title" style="font-size:1rem;margin-bottom:.75rem">Shareable Report Links</h3>
    <p style="color:var(--muted);font-size:.9rem;margin-bottom:1rem">Turn any wallet scan, domain check, or vendor sweep result into a persistent, shareable URL. Generation requires a subscription; viewing the resulting link is public with no login required. Paste it into a client ticket or incident report.</p>
    <div style="background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1rem;font-size:.85rem">
      <div style="font-family:monospace;color:var(--accent);margin-bottom:.5rem">POST /v1/report/share</div>
      <div style="color:var(--muted)">Returns a <code>report_id</code> and public <code>share_url</code> for the summary you submit.</div>
    </div>
  </div>
</div>

<div class="code-section">
  <h2 class="section-title" id="quick-start" style="margin-bottom:1rem">Quick start</h2>
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

  <h3 class="section-title" style="margin-top:2rem;margin-bottom:.5rem">Python sample: breach + infostealer in sequence</h3>
  <p style="color:var(--muted);font-size:.88rem;margin-bottom:.75rem">Copy-paste to run immediately. No SDK required, standard library only.</p>
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
  <h2 class="section-title" id="sdks" style="font-size:1.2rem;margin:0 0 1rem">Agent framework SDKs</h2>
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
    <!--
      Apify, added 2026-09-03. The Actor has been public and taking real runs
      since August and this page has never mentioned it, so the only way to
      find it was to already be on Apify. An _APIFY_BANNER exists for arrivals
      FROM Apify; this is the other direction, and it is the cheaper one.

      Hosted rather than installed, so no pip line: the card links straight to
      the Store listing. Nothing here claims a run count. Numbers on a landing
      page are a maintenance burden and a prospect can read the real one on the
      listing itself.
    -->
    <a href="https://apify.com/relayshieldadmin/relayshield-security-tools" target="_blank" rel="noopener" style="text-decoration:none;background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:1rem">
      <p style="color:var(--text);font-size:.9rem;font-weight:600;margin:0 0 .35rem">Apify Actor (MCP)</p>
      <code style="display:block;color:var(--muted);font-size:.8rem;background:var(--surface);border-radius:5px;padding:.4rem .55rem;margin-bottom:.5rem">relayshield-security-tools</code>
      <span style="color:var(--accent);font-size:.82rem;font-weight:600">Hosted MCP server, pay per usage &rarr;</span>
    </a>
  </div>
</div>

<div style="background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:1.5rem 1.75rem;margin:2rem 0">
  <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.6rem;margin-bottom:1rem">
    <h2 class="section-title" id="templates" style="font-size:1.2rem;margin:0">What practitioners are building</h2>
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
    <code style="background:var(--bg);border-radius:4px;padding:.1rem .4rem">n8n-nodes-relayshield</code> is verified and available directly on n8n Cloud. Search for it on the canvas, no manual install needed.
  </p>
  <div style="display:flex;align-items:center;gap:.5rem;margin:0 0 .35rem">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="2" y="2" width="20" height="20" rx="5" fill="#FF4F00"/>
      <path d="M12 6.5v11M6.5 12h11M8.1 8.1l7.8 7.8M15.9 8.1l-7.8 7.8" stroke="#fff" stroke-width="1.9" stroke-linecap="round"/>
    </svg>
    <span style="font-size:.82rem;font-weight:700;color:#FF4F00">Zapier</span>
    <span style="font-size:.68rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;background:var(--bg);color:var(--muted);border-radius:4px;padding:.1rem .38rem">Beta</span>
  </div>
  <p style="color:var(--muted);font-size:.82rem;margin:0 0 1rem">
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="vertical-align:-2px;margin-right:.3rem">
      <path d="M9 12l2 2 4-4" stroke="#22c55e" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="12" cy="12" r="10" stroke="#22c55e" stroke-width="1.6"/>
    </svg>
    The RelayShield Zapier integration is approved and live in the Zapier App Directory, currently in
    its 90-day beta. Connect it with your API key to reach 8,000+ apps, no invite code needed.
  </p>
  <div style="display:flex;align-items:center;gap:.5rem;margin:0 0 .35rem">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="12" cy="12" r="10" fill="#EE0000"/>
      <path d="M12 6.2l4.6 9.6h-2.5l-2.1-4.6-2.1 4.6H7.4z" fill="#fff"/>
    </svg>
    <span style="font-size:.82rem;font-weight:700;color:#EE0000">Ansible Galaxy</span>
  </div>
  <p style="color:var(--muted);font-size:.82rem;margin:0 0 1rem">
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" style="vertical-align:-2px;margin-right:.3rem">
      <path d="M9 12l2 2 4-4" stroke="#22c55e" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="12" cy="12" r="10" stroke="#22c55e" stroke-width="1.6"/>
    </svg>
    <code style="background:var(--bg);border-radius:4px;padding:.1rem .4rem">ansible-galaxy collection install relayshield.security</code>
    installs three modules for gating a play on identity risk: <code style="background:var(--bg);border-radius:4px;padding:.1rem .4rem">breach_check</code>,
    <code style="background:var(--bg);border-radius:4px;padding:.1rem .4rem">domain_lookalikes</code> and
    <code style="background:var(--bg);border-radius:4px;padding:.1rem .4rem">supply_chain_risk</code>.
    Published and installable from Ansible Galaxy.
  </p>
  <!--
    Template links must point at n8n.io/workflows/<id>, NOT creators.n8n.io.
    A creators.n8n.io URL returns HTTP 200 for an unauthenticated visitor but
    renders n8n's login page, so it passes a link check while being useless to
    a reader. Only templates that are approved and live in the public gallery
    belong here - verify with:
      curl -s "https://api.n8n.io/api/templates/search?search=relayshield&rows=50"
    The new-hire onboarding template (17255) was demoted to "Implement changes"
    by the reviewer and is deliberately absent until it is re-approved.
  -->
  <a href="https://n8n.io/workflows/16694" target="_blank" rel="noopener" style="display:flex;align-items:center;gap:.9rem;text-decoration:none;background:rgba(255,109,90,.08);border:1px solid rgba(255,109,90,.25);border-radius:8px;padding:.85rem 1rem;margin-bottom:.6rem">
    <div style="flex:1;min-width:0">
      <p style="color:var(--text);font-size:.9rem;font-weight:600;margin:0 0 .2rem">Featured in n8n&apos;s official template gallery</p>
      <p style="color:var(--muted);font-size:.82rem;margin:0">&ldquo;Check offboarding credential risks with RelayShield, Slack, Notion and Gmail&rdquo;: HR trigger → parallel breach, infostealer and OAuth-token checks → Slack alert, manager email and Notion audit log. n8n.io/workflows/16694</p>
    </div>
    <span style="color:var(--accent);font-size:.82rem;font-weight:600;white-space:nowrap">View template &rarr;</span>
  </a>
  <a href="https://n8n.io/workflows/17386" target="_blank" rel="noopener" style="display:flex;align-items:center;gap:.9rem;text-decoration:none;background:rgba(255,109,90,.08);border:1px solid rgba(255,109,90,.25);border-radius:8px;padding:.85rem 1rem;margin-bottom:1rem">
    <div style="flex:1;min-width:0">
      <p style="color:var(--text);font-size:.9rem;font-weight:600;margin:0 0 .2rem">Shadow AI &amp; vendor approval gate</p>
      <p style="color:var(--muted);font-size:.82rem;margin:0">&ldquo;Gate SaaS and AI tool approvals with RelayShield, Notion, Slack, and Gmail&rdquo;: a new tool request branches on SaaS vs AI tool, then runs supply-chain, secret-scan, OAuth-watchlist and MCP registry-risk checks before anyone approves it. n8n.io/workflows/17386</p>
    </div>
    <span style="color:var(--accent);font-size:.82rem;font-weight:600;white-space:nowrap">View template &rarr;</span>
  </a>
  <div style="border-left:3px solid var(--accent);padding-left:1rem;margin-bottom:1rem">
    <p style="color:var(--text);font-size:.95rem;margin:0 0 .4rem">&ldquo;Nice work! You could extend this to trigger when an employee is deactivated in your HR system: run breach + infostealer checks on offboarding, then log to Notion or alert Slack if their credentials are circulating.&rdquo;</p>
    <p style="color:var(--muted);font-size:.82rem;margin:0">n8n community member, on the RelayShield breach monitoring workflow template</p>
  </div>
  <p style="color:var(--muted);font-size:.85rem;margin:0">Used in SOAR playbooks, SIEM enrichment pipelines, MSP onboarding/offboarding automations, and incident response triage workflows. <a href="https://n8n.io/creators/relayshieldadmin" target="_blank" rel="noopener" style="color:var(--accent)">All our n8n templates</a> &middot; <a href="mailto:support@relayshield.net" style="color:var(--accent)">Tell us what you&apos;re building.</a></p>
</div>

<footer>
  <!--
    Blog link added 2026-07-30. The blog was reachable only from two inline
    mentions deep in the page body; there was no way to browse the archive from
    here at all. Now that we self-host it, the archive is 17 posts of threat
    research that nothing on this page pointed at.
  -->
  <p style="margin-bottom:.6rem">
    <a href="https://api.relayshield.net/docs" style="color:var(--accent);font-weight:600">API reference</a>
    <span style="color:var(--muted)">&nbsp;·&nbsp;</span>
    <a href="https://api.relayshield.net/openapi.json" style="color:var(--accent)">OpenAPI spec</a>
    <span style="color:var(--muted)">&nbsp;·&nbsp;</span>
    <a href="https://blog.relayshield.net" style="color:var(--accent);font-weight:600">Threat research blog</a>
    <span style="color:var(--muted)">&nbsp;·&nbsp;</span>
    <a href="https://api.relayshield.net/guides/microsoft-sentinel" style="color:var(--accent)">Microsoft Sentinel guide</a>
    <span style="color:var(--muted)">&nbsp;·&nbsp;</span>
    <a href="https://api.relayshield.net/guides/elastic-security" style="color:var(--accent)">Elastic Security guide</a>
    <span style="color:var(--muted)">&nbsp;·&nbsp;</span>
    <a href="https://blog.relayshield.net/rss.xml" style="color:var(--accent)">RSS</a>
  </p>
  <p>RelayShield LLC · <a href="https://relayshield.net">relayshield.net</a> · <a href="mailto:support@relayshield.net">support@relayshield.net</a></p>
  <p style="margin-top:.6rem">
    <a href="https://x402-list.com/services/relayshield?utm_source=badge&amp;utm_medium=referral&amp;utm_campaign=embed" target="_blank" rel="noopener">
      <img src="https://x402-list.com/badge/relayshield.svg?data=uptime&amp;period=30d" alt="RelayShield on x402-list.com: continuously monitored" style="height:20px;vertical-align:middle" />
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
    if (data.ok && data.data.free_tier) {
      // Free tier: no redirect, the key is already in their inbox. Replacing
      // the form with confirmation is deliberate, bouncing them to a
      // separate success page loses the momentum, and there is nothing on
      // that page they need.
      const box = document.querySelector('.signup-box');
      box.innerHTML =
        '<p style="font-size:1.05rem;font-weight:650;color:var(--green);margin-bottom:.5rem">' +
        (data.data.resent ? 'Key re-sent.' : 'Key sent.') + '</p>' +
        '<p style="line-height:1.6">' + (data.data.message || '') + '</p>' +
        '<p style="line-height:1.6;margin-top:.75rem;color:var(--muted);font-size:.92rem">' +
        'Not there in a minute? Check spam, or email support@relayshield.net. ' +
        'Full reference: <a href="/docs" style="color:var(--accent);font-weight:600">api.relayshield.net/docs</a></p>';
    } else if (data.ok && data.data.checkout_url) {
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
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="icon" href="/favicon.ico" sizes="any">
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


def _banner(kicker: str, body_html: str) -> str:
    return f"""
<div style="background:var(--surface);border:1px solid var(--accent);border-radius:10px;padding:1.25rem 1.5rem;margin:1.5rem 0 0">
  <p style="color:var(--accent);font-size:.78rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;margin:0 0 .5rem">{kicker}</p>
  {body_html}
  <p style="color:var(--muted);font-size:.85rem;margin:.9rem 0 0">Need a key? <a href="#get-started" style="color:var(--accent);font-weight:600">Grab one below</a> &mdash; pay per call, no monthly minimum.</p>
</div>
"""


def _p(text: str) -> str:
    return f'<p style="color:var(--text);font-size:.95rem;margin:0">{text}</p>'


# Per-source landing variants, added 2026-07-30.
#
# One generic page was serving LangChain developers, SOC engineers, MSPs and AWS
# Marketplace buyers identically, so everyone arriving from a specific integration
# had to re-find the one thing that brought them. The LangChain banner had already
# shown this works; this generalises it to every channel we actually publish on.
#
# Matched on the Referer host, or forced with ?src=<key> so a link we control can
# select its own framing even when the referrer is stripped (which is what happens
# with most Slack, Discord and native app clicks).
_APIFY_BANNER = _banner("Arriving from Apify", _p(
    "The RelayShield actor runs breach, infostealer and SIM-swap checks as an Apify task, so a "
    "list of employee emails or phone numbers can be screened on a schedule and the results pushed "
    "into whatever the rest of your Apify pipeline already feeds. Same API underneath, no "
    "integration code."))


_SOURCE_BANNERS: dict[str, tuple[tuple[str, ...], str]] = {
    "discord-bot": (
        ("top.gg", "discordbotlist.com", "discord.bots.gg"),
        _banner("Arriving from the RelayShield Discord bot", _p(
            "The bot runs the same checks this API exposes. "
            '<code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">/scan</code> is '
            '<code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">wallet-risk</code> and our IOC corpus, '
            '<code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">/exposure</code> is '
            '<code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">breach</code>. '
            "Everything the bot does in one server, your own code can do across every account you are "
            "responsible for: breach and infostealer exposure, SIM swap, leaked OAuth tokens, "
            "typosquat domains and wallet screening. Free tier is 100 calls, no card.")),
    ),
    "npm-worm": (
        # The last three entries are the ARTICLE SLUG, not a domain, and that is
        # deliberate. `_resolve_source` substring-matches the whole Referer
        # string rather than just its host, so any page whose URL contains the
        # slug resolves here: our blog, the Medium syndication, the dev.to
        # syndication, or anyone who reposts it.
        #
        # WHY, found live 2026-08-12: Medium STRIPS the query string from the
        # rendered anchor href. Its own GraphQL payload stores
        # `.../developers?source=npm-worm-medium` correctly and the visible link
        # text shows it, but the `<a href>` the browser actually follows is the
        # bare path. So a click arrives with no ?source at all, logs as "-", and
        # renders no banner. Re-editing the link on Medium does not fix it,
        # because it is Medium's renderer and not our link.
        #
        # Referer matching is the durable answer: it survives any platform that
        # rewrites, shortens or strips outbound URLs, which is most of them.
        # The query parameter still wins when present, since it is checked
        # first, so per-channel attribution is unaffected wherever it survives.
        ("npmjs.com", "socket.dev",
         "the-npm-worm-does-not-start-with-malicious-code",
         "npm-worm-does-not-start",
         "the-npm-worm"),
        _banner("Arriving from the npm maintainer post", _p(
            '<code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">POST /v1/metered/dependency-risk</code> '
            "takes a list of package names, or your package.json or package-lock.json, and tells you which "
            "dependencies are maintained by an account that appears in a recent infostealer log. Findings come "
            "back at the dependency level: we never return, log or store the identity of a maintainer. "
            "<b>Included at no per-call charge in the Agentic Attack Surface bundle</b> at $299/mo, or $0.50 "
            "a call outside it. Register a package as a <b>dependency</b> watch and you are told when the "
            "answer changes rather than on a schedule.")),
    ),
    "fourth-party": (
        # The last three entries are the ARTICLE SLUG, not a domain. _resolve_source
        # substring-matches the whole Referer, so any page whose URL carries the slug
        # resolves here: our blog, the Medium syndication, or anyone who reposts it.
        # This is the durable path, because Medium strips the query string from the
        # rendered anchor href (found live 2026-08-12 on the npm post).
        ("your-wallet-provider-had-a-vendor",
         "that-vendor-had-a-dashboard",
         "fourth-party-risk"),
        _banner("Arriving from the fourth-party exposure post", _p(
            '<code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">POST /v1/metered/breach-check</code> '
            "and "
            '<code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">/v1/metered/infostealer-check</code> '
            "answer the question this post is really about: not whether your vendor was breached, but whether "
            "an address you are responsible for has surfaced in the exposure that followed. Register an address "
            "as a watch and you are told when the answer changes, rather than finding out from a notice four "
            "parties downstream. <b>$0.10 a call, no monthly minimum</b>, or included in the bundles.")),
    ),
    "ansible-galaxy": (
        # Referer entries cover a Galaxy collection page and the docs site. The
        # collection's own galaxy.yml points documentation/homepage here without
        # a query string, so referer matching is the primary path, not a fallback.
        ("galaxy.ansible.com", "ansible.com", "console.redhat.com"),
        _banner("Arriving from Ansible Galaxy", _p(
            'The <code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">relayshield.security</code> '
            "collection gives you three modules: <b>breach_check</b>, <b>domain_lookalikes</b> and "
            "<b>supply_chain_risk</b>. They are built to gate a play before it grants access or deploys, so a "
            "playbook can refuse to onboard an identity that is already in a stealer log. Every module needs an "
            "API key, which is what this page issues. <b>Pay per call, no monthly minimum</b>, and the same key "
            "works across REST, MCP and STIX/TAXII.")),
    ),
    # Apify, registered 2026-08-27 BEFORE any listing link goes out. An
    # unregistered key logs unmatched: and renders no banner, which is exactly
    # how ?source=rsscan shipped broken. Referer hosts included so an arrival
    # that loses the query parameter still attributes.
    "apify": (("apify.com", "console.apify.com"), _APIFY_BANNER),
    # MCP registries, registered 2026-09-02, and this one is a CORRECTION
    # rather than a precaution.
    #
    # RelayShield has been listed in the official MCP registry
    # (registry.modelcontextprotocol.io) since 2026-05-10 -- six versions,
    # latest 0.2.7 on 2026-07-19, status active. Nobody in this repo knew. Its
    # websiteUrl is a bare https://relayshield.net with NO ?source= key, so
    # nearly four months of arrivals from the canonical MCP directory have
    # logged unmatched: and rendered no banner.
    #
    # That is the exact failure the rule at the top of FRONT_DOORS.md exists to
    # prevent, and it happened on a front door nobody opened deliberately. A
    # channel that cannot be measured cannot be defended when deciding what to
    # build next; it just becomes an opinion.
    #
    # Registered BEFORE the server.json websiteUrl is updated, in that order,
    # so the key exists the moment the first attributed arrival lands.
    "mcp-registry": (
        ("registry.modelcontextprotocol.io", "modelcontextprotocol.io",
         "glama.ai", "smithery.ai", "mcp.so"),
        _banner("Arriving from an MCP registry", _p(
            "The RelayShield MCP server is published to the official registry and "
            "installs with your client's usual command. It exposes the same checks "
            "the REST API documents below &mdash; breach exposure, infostealer "
            "credentials, SIM swap, domain lookalikes and URL scanning &mdash; as "
            "tools an agent can call directly, so a security check becomes a step "
            "in an agent's own reasoning rather than a separate system someone has "
            "to remember to consult.")),
    ),
    # The Telegram bot widget, registered 2026-09-03 BEFORE the widget ships,
    # which is the whole point of this rule. Four months of arrivals from the
    # official MCP registry logged unmatched: because the key was created after
    # the link went out; this one exists first.
    #
    # NO REFERER HOSTS, deliberately, and that is a departure from every other
    # entry here. The widget writes its own links and always appends
    # ?source=tg-widget, so referer matching adds nothing it needs. Adding t.me
    # would be actively wrong: every un-keyed click from our OWN Telegram bot
    # and blog channel would then be attributed to third-party widget installs,
    # and the number we most want from this channel is how many installs are
    # real. An empty tuple means "explicit parameter only".
    "tg-widget": (
        (),
        _banner("Arriving from a Telegram bot", _p(
            "Someone added RelayShield to the bot you were just using. The same check "
            'runs from one function call &mdash; <code style="background:var(--bg);border-radius:5px;'
            'padding:.15rem .4rem">check(text)</code> returns a verdict and a ready-to-send reply for '
            "any link or wallet address a user pastes, across EVM, Solana, TON and Bitcoin. "
            "The first calls need no key, no card and no signup: link checking and address "
            "screening are open endpoints, capped per address rather than billed. A key raises "
            "the cap and adds multi-engine URL analysis.")),
    ),
    # PyPI, registered 2026-09-03 BEFORE the package's project_urls change, in
    # that order, because that order is the whole rule. Found while verifying
    # FD-8: relayshield-mcp's PyPI page links "Documentation" straight at this
    # page with no ?source= at all, so every arrival from the place the MCP
    # server is actually installed from has been logging unattributed.
    #
    # Referer hosts included: pypi.org sends a referer on an outbound click,
    # unlike most of the app surfaces, so this one attributes even when the
    # query string is lost.
    "pypi": (
        ("pypi.org", "files.pythonhosted.org"),
        _banner("Arriving from PyPI", _p(
            "You found the package. The same checks it wraps are a REST API, and the key "
            "works across both: "
            '<code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">relayshield-mcp</code> '
            "is a client for the endpoints documented below, not a separate product. Breach "
            "exposure, infostealer credentials, SIM swap, domain lookalikes, MCP registry risk "
            "and prompt-injection exposure, priced per call with 100 free and no card. The "
            "pay-as-you-go endpoints need no key at all.")),
    ),
    "langchain": (("langchain.com",), _LANGCHAIN_BANNER),
    "n8n": (
        ("n8n.io", "creators.n8n.io"),
        _banner("Arriving from n8n", _p(
            'The <code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">n8n-nodes-relayshield</code> '
            "community node is verified and installable directly on n8n Cloud &mdash; search for RelayShield on the canvas. "
            "It exposes breach, infostealer, SIM-swap and domain-lookalike checks as native nodes, so identity risk drops "
            "into an existing onboarding, offboarding or alert-triage workflow without custom HTTP nodes.")),
    ),
    "x402": (
        ("x402scan.com", "x402-list.com", "warpcast.com", "farcaster.xyz"),
        _banner("Arriving from the x402 ecosystem", _p(
            "Every counterparty check below is <b>x402 native</b> on Base and Solana, discoverable in the "
            "CDP Bazaar, with no signup and no API key: "
            '<code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">wallet-risk</code> $0.05, '
            '<code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">token-security</code> $0.05, '
            '<code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">scan-wallet</code> $0.10, '
            '<code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">mcp-registry-risk</code> $0.35, '
            '<code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">wallet-screen-batch</code> $0.50. '
            "Point an agent at the endpoint, take the 402, pay it. A wallet-risk check costs less than the "
            "average x402 payment it protects.")),
    ),
    "elastic": (
        ("elastic.co", "discuss.elastic.co"),
        _banner("Arriving from Elastic", _p(
            "RelayShield's IOC corpus ingests into Elastic Security through the <b>Custom Threat Intelligence</b> "
            "integration (<code>ti_custom</code>) with its TAXII 2.1 mode &mdash; configuration only, no development. "
            'Field mappings were measured against a live 8.15 stack: see the '
            '<a href="https://blog.relayshield.net" style="color:var(--accent);font-weight:600">Elastic ingestion guide</a>.')),
    ),
    "sentinel": (
        ("learn.microsoft.com", "portal.azure.com", "security.microsoft.com"),
        _banner("Arriving from Microsoft Sentinel", _p(
            "Point Sentinel's <b>Threat Intelligence - TAXII</b> connector at "
            '<code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">https://api.relayshield.net/v1/intel/taxii/</code> '
            "with collection ID <code>iocs</code>. Indicators land in <code>ThreatIntelIndicators</code>, ready for "
            "analytics rules. Note the legacy <code>ThreatIntelligenceIndicator</code> table retired 2026-05-31.")),
    ),
    "xsoar": (
        ("xsoar.pan.dev", "paloaltonetworks.com", "demisto.com"),
        _banner("Arriving from Cortex XSOAR", _p(
            "The RelayShield content pack implements the generic <code>domain</code>, <code>ip</code> and "
            "<code>email</code> reputation commands, so existing enrichment playbooks pick it up as an additional "
            "source with no playbook changes &mdash; plus MCP registry risk, certificate expiry and supply-chain "
            "vendor risk commands.")),
    ),
    "aws": (
        ("aws.amazon.com", "console.aws.amazon.com"),
        _banner("Arriving from AWS Marketplace", _p(
            "RelayShield is available through AWS Marketplace with billing handled by AWS &mdash; no separate account "
            "or payment method required. The <b>Agentic Attack Surface</b> bundle covers LLM credential exposure, MCP "
            "registry risk, prompt-injection breach detection, agent identity risk scoring and framework CVE monitoring.")),
    ),
    "github": (
        ("github.com",),
        _banner("Arriving from GitHub", _p(
            "Client libraries and integrations are open source: LangChain, LlamaIndex, OpenAI Agents SDK, n8n, Zapier "
            "and an MCP server. Every one of them talks to the same REST API documented below, so you can drop to raw "
            "HTTP whenever the wrapper is in the way.")),
    ),
    # rsscan arrivals. Previously aliased to "github", so every developer sent
    # here by the scanner read a paragraph about client libraries, which is the
    # wrong answer to the question they arrived with. rsscan's own source states
    # the right one above EXPOSURE_URL: a local hook can only prevent the NEXT
    # leak, it cannot see what has already been scraped. Checking what is
    # already public is the one job that genuinely needs a key, so it is the
    # only honest reason for this visitor to sign up.
    # Added 2026-08-09 with the MetaMask Snap. Registered at the same time as the
    # link that points here, deliberately: rsscan shipped its link first and was
    # silently aliased to the generic "github" banner for months, so roughly 397
    # arrivals a month read a paragraph about client libraries instead of an
    # answer to the question they arrived with. A source key with no banner is
    # not a cosmetic gap, it is a wasted arrival.
    "metamask-snap": (
        (),
        _banner("Arriving from the MetaMask Snap", _p(
            "The Snap screens the counterparty on transactions you are about to sign. Everything it "
            "checks, it checks through this API, and the same key works everywhere else here. "
            "The screening call itself is "
            "<code style=\"background:var(--bg);border-radius:5px;padding:.15rem .4rem\">/v1/metered/wallet-risk</code> "
            "at $0.05. What the Snap cannot see is the rest of the attack: the breach that leaked the "
            "credential, the infostealer log holding the session, the lookalike domain that sent the "
            "link. Those are the endpoints below, and your free calls cover them with no card.")),
    ),
    "rsscan": (
        (),
        _banner("Arriving from rsscan", _p(
            "rsscan reads your diff, so it catches what is <b>about to</b> leak. It cannot see a credential that "
            "already left: committed months ago, shipped in a published package, or baked into a container image, "
            "and possibly indexed and scraped since. That is a different question and it needs a search of public "
            "artifacts rather than a local scan. "
            "<code style=\"background:var(--bg);border-radius:5px;padding:.15rem .4rem\">/v1/metered/secret-scan</code> "
            "checks six public sources for credentials belonging to your org: GitHub, npm, PyPI, Docker Hub, Hugging "
            "Face and Postman. Your free calls cover it, and there is no card required.")),
    ),
    # Readers arriving from the `rsscan --deps` release post, 2026-08-13. Its own
    # variant rather than an alias onto "rsscan", for the same reason rsscan is
    # not aliased onto "github": the rsscan banner pitches secret-scan, which
    # answers "are my org's credentials already public". Somebody who just
    # counted 275 publisher accounts in their dependency tree is asking a
    # different question, and dependency-risk is the answer to that one.
    "rsscan-deps": (
        (),
        _banner("Arriving from the rsscan --deps release", _p(
            "<code style=\"background:var(--bg);border-radius:5px;padding:.15rem .4rem\">rsscan --deps</code> "
            "counts the accounts that can publish into your dependencies, and deliberately stops there. It "
            "cannot tell you whether any of them is compromised right now, because that means screening "
            "identities against infostealer corpora rather than reading registry metadata. "
            '<span style="display:block;margin-top:.7rem">'
            "<code style=\"background:var(--bg);border-radius:5px;padding:.15rem .4rem\">POST /v1/metered/dependency-risk</code> "
            "is that step. Send a package list or a <code>package-lock.json</code>; findings come back at the "
            "dependency level and never name the maintainer. Included at no per-call charge in the Agentic "
            "Attack Surface bundle, because re-screening 400 maintainers costs us about what re-screening "
            "four does.</span>"
            '<span style="display:block;margin-top:.7rem;opacity:.85">'
            "A clean result means nothing was found in the sources we queried. Registry metadata is not always "
            "current, so an address the registry has gone stale on screens clean.</span>")),
    ),
    # Readers arriving from the LLMjacking / Bundle D launch post. Added
    # 2026-07-30 after the published post was found linking to ?src=blog, which
    # was never a registered key and therefore rendered no banner at all. The
    # aliases below exist because the post is syndicated to Medium, LinkedIn and
    # Telegram, and each of those will carry whatever src the copy was written
    # with. Give them all the same landing rather than relying on one string.
    "llmjacking": (
        ("blog.relayshield.net", "medium.com"),
        _banner("Arriving from the LLMjacking post", _p(
            "Run the check on your own domain. No API key, no signup, shared free tier:"
            '<pre style="background:var(--bg);border:1px solid var(--border);border-radius:8px;'
            'padding:.9rem 1rem;overflow-x:auto;margin:.8rem 0 0;font-size:.82rem;line-height:1.55">'
            "<code>curl -X POST https://api.relayshield.net/v1/payg/llm-credential-exposure \\\n"
            '  -H "Content-Type: application/json" \\\n'
            "  -d '{\"domain\": \"yourcompany.com\"}'</code></pre>"
            '<span style="display:block;margin-top:.7rem">We match 19 LLM credential formats across 14 '
            "providers against 494K+ distinct indicators (5.8M+ sightings) from 95 monitored channels. A clean result means "
            "nothing was found in the sources we queried, which is not the same as proof your keys are safe."
            "</span>")),
    ),
    # Readers arriving from the secret-scanning post. Deliberately NO hosts: the
    # llmjacking variant above already claims blog.relayshield.net and medium.com,
    # and the referer loop returns the first host match, so claiming them here
    # would make which post you appear to arrive from depend on dict order. This
    # variant is reachable only by an explicit ?source=, which every link in the
    # post carries.
    "secret-scan": (
        (),
        _banner("Arriving from the secret scanning post", _p(
            "Start with the free local scanner &mdash; all 31 credential patterns run on your own machine. "
            "No API key, no account, no network call, MIT licensed:"
            '<pre style="background:var(--bg);border:1px solid var(--border);border-radius:8px;'
            'padding:.9rem 1rem;overflow-x:auto;margin:.8rem 0 0;font-size:.82rem;line-height:1.55">'
            "<code>pip install rsscan &amp;&amp; rsscan .</code></pre>"
            '<span style="display:block;margin-top:.7rem">The hosted scan is the half a pre-commit hook '
            "cannot do: it searches <b>GitHub, npm, PyPI, Docker Hub and Hugging Face</b> for credentials "
            "already public against a domain you own, and re-matches every candidate against the full "
            "pattern set so you get findings rather than search hits. "
            '<code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">POST /v1/metered/secret-scan</code>, '
            "$0.35 a call. A clean result means nothing was found in the sources we queried, which is not "
            "the same as proof your keys are safe.</span>")),
    ),
    # BlueNoroff post, 2026-08-10. No hosts claimed, same reasoning as
    # secret-scan above: reachable only by an explicit ?source=, which every
    # link in the post carries.
    #
    # What this banner may and may not claim: we ingested JUMPSEC's published
    # campaign infrastructure with attribution intact. We did NOT detect this
    # campaign, and the copy must never imply otherwise. The audience for this
    # post checks.
    "bluenoroff": (
        (),
        _banner("Arriving from the DPRK ClickFix post", _p(
            "The post's argument is that the compromise is an identity event, not a chain event: "
            "a trusted contact's Telegram session becomes the delivery channel for the next round. "
            "These are the checks that look at that layer."
            '<span style="display:block;margin-top:.7rem">'
            '<code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">POST /v1/metered/session-risk</code> '
            "$0.30 a call &mdash; stolen session cookies for an address, severity-ranked. Step 6 of the "
            "chain in the post is session theft, and this is where that output surfaces."
            "</span>"
            '<span style="display:block;margin-top:.55rem">'
            '<code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">POST /v1/metered/asset-intel</code> '
            "$0.15 a call &mdash; sweep your own domains and IPs against our indicator corpus, which now "
            "carries the 60 domains and 10 IPs JUMPSEC published for this campaign, each row citing the "
            "research it came from."
            "</span>"
            '<span style="display:block;margin-top:.7rem;opacity:.85">'
            "We did not discover this campaign. JUMPSEC did, and we ingested what they published. "
            "A clean result means nothing was found in the sources we queried, which is not the same "
            "as proof you were not targeted.</span>")),
    ),
    "session-hijack": (
        (),
        _banner("Arriving from the session hijacking post", _p(
            "The post's argument is that the password is the delivery mechanism and the session cookie "
            "and machine credential are the payload. These are the two checks that look for exactly that, "
            "against criminal stealer-log archives rather than your own repositories."
            '<span style="display:block;margin-top:.7rem">'
            '<code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">POST /v1/metered/session-risk</code> '
            "$0.30 a call &mdash; stolen session cookies for an address, severity-ranked by service category. "
            "A stolen cookie bypasses MFA and stays valid until the session is explicitly revoked, so a "
            "password reset alone does not close it.</span>"
            '<span style="display:block;margin-top:.55rem">'
            '<code style="background:var(--bg);border-radius:5px;padding:.15rem .4rem">POST /v1/metered/nhi-exposure</code> '
            "$0.40 a call &mdash; machine credentials tied to your domain in the same corpus: AWS IAM keys, "
            "GitHub PATs, Stripe secrets, private keys, Slack tokens.</span>"
            '<span style="display:block;margin-top:.7rem">A clean result means nothing was found in the '
            "sources we queried. It is not proof of safety, and we do not claim detection of the two "
            "malware families named in the post.</span>")),
    ),
    "huggingface": (
        ("huggingface.co", "hf.space"),
        _banner("Arriving from Hugging Face", _p(
            "The RelayShield MCP server exposes 13 tools over the Model Context Protocol, and "
            "<code>check_llm_credential_exposure</code> works with no API key at all on a shared demo quota &mdash; "
            "check whether your own LLM provider keys are circulating in stealer logs before you commit to anything.")),
    ),
}


# Extra ?src= spellings that should resolve to an existing variant. Cheaper than
# discovering after publication that a link in a live post matches nothing, which
# is exactly what happened with ?src=blog on the Bundle D launch post.
_SOURCE_ALIASES = {
    # These five stay on llmjacking. The published LLMjacking post links with
    # ?src=blog (that is why they were added), so repointing them at whatever the
    # newest post happens to be would silently hand its existing readers the wrong
    # landing. Generic channel keys belong to the post that already shipped with
    # them; a new post registers its own, as secret-scan-* does below.
    "blog": "llmjacking",
    "medium": "llmjacking",
    "linkedin": "llmjacking",
    "telegram": "llmjacking",
    "post": "llmjacking",
    # Secret-scanning post, 2026-08-03. One key per syndication channel: the raw
    # parameter is what gets logged, so these stay distinguishable in CloudWatch
    # while all rendering the same banner. Registered BEFORE the post is
    # published -- an unregistered key logs unmatched: and renders nothing, which
    # is exactly how ?source=rsscan shipped broken.
    # npm maintainer-compromise post, 2026-08-12 ("The npm Worm Does Not Start
    # With Malicious Code"). Registered BEFORE syndication for the reason spelt
    # out below: an unregistered key logs unmatched: and renders no banner, so
    # the link looks fine and quietly attributes nothing.
    # Discord bot listings, 2026-08-12. Registered BEFORE the top.gg submission
    # goes in, because the listing's website field is public the moment it is
    # approved and an unregistered key renders no banner.
    "discord":             "discord-bot",
    "discord-bot":         "discord-bot",
    "discord-topgg":       "discord-bot",
    "discord-appdir":      "discord-bot",
    "discord-exposure":    "discord-bot",
    "discord-wallet":      "discord-bot",
    # Fourth-party / Privy-Metabase post, 2026-08-17 ("Your Wallet Provider Had a
    # Vendor, and That Vendor Had a Dashboard"). Registered BEFORE syndication:
    # an unregistered key logs unmatched: and renders no banner, so the link
    # looks fine and quietly attributes nothing.
    # Ansible Galaxy collection relayshield.security, published 2026-08-17.
    # Registered at publish time: an unregistered key logs unmatched: and renders
    # no banner, so the link looks fine and attributes nothing.
    "galaxy":              "ansible-galaxy",
    "ansible":             "ansible-galaxy",
    "ansible-galaxy":      "ansible-galaxy",
    "galaxy-collection":   "ansible-galaxy",
    "fourth-party":            "fourth-party",
    "blog-fourth-party":       "fourth-party",
    "fourth-party-medium":     "fourth-party",
    "fourth-party-linkedin":   "fourth-party",
    "fourth-party-telegram":   "fourth-party",
    "fourth-party-mastodon":   "fourth-party",
    "fourth-party-farcaster":  "fourth-party",
    "fourth-party-reddit":     "fourth-party",
    "npm-worm":            "npm-worm",
    "blog-npm-worm":       "npm-worm",
    "npm-worm-medium":     "npm-worm",
    "npm-worm-linkedin":   "npm-worm",
    "npm-worm-telegram":   "npm-worm",
    "npm-worm-mastodon":   "npm-worm",
    "npm-worm-farcaster":  "npm-worm",
    "npm-worm-hf":         "npm-worm",
    "npm-worm-devto":      "npm-worm",
    "npm-worm-hn":         "npm-worm",
    "secret-scan":           "secret-scan",
    "secretscan":            "secret-scan",
    "secret-scan-post":      "secret-scan",
    "secret-scan-medium":    "secret-scan",
    "secret-scan-linkedin":  "secret-scan",
    "secret-scan-telegram":  "secret-scan",
    "secret-scan-farcaster": "secret-scan",
    "secret-scan-mastodon":  "secret-scan",
    "secret-scan-hn":        "secret-scan",
    # Session-hijacking post, 2026-08-04 ("The Malware Stopped Stealing
    # Passwords"). Same one-key-per-channel pattern: the raw parameter is what
    # CloudWatch logs, so channels stay distinguishable while all rendering the
    # same banner. Registered BEFORE any link goes out -- the CloudWatch source
    # report currently shows live unmatched:circleci / unmatched:rsscan /
    # unmatched:docker entries, which is what an unregistered key looks like.
    "session-hijack":           "session-hijack",
    "sessionhijack":            "session-hijack",
    "session-hijack-post":      "session-hijack",
    "session-hijack-medium":    "session-hijack",
    "session-hijack-linkedin":  "session-hijack",
    "session-hijack-telegram":  "session-hijack",
    "session-hijack-farcaster": "session-hijack",
    "session-hijack-mastodon":  "session-hijack",
    "session-hijack-reddit":    "session-hijack",
    # BlueNoroff / DPRK ClickFix post, 2026-08-10 ("Sender Recognition Is Not
    # Authentication"). Registered BEFORE the post goes out, same rule as above.
    "bluenoroff":           "bluenoroff",
    "bluenoroff-post":      "bluenoroff",
    "bluenoroff-linkedin":  "bluenoroff",
    "bluenoroff-telegram":  "bluenoroff",
    "bluenoroff-mastodon":  "bluenoroff",
    "bluenoroff-farcaster": "bluenoroff",
    "bluenoroff-medium":    "bluenoroff",
    "bluenoroff-reddit":    "bluenoroff",
    # Agent counterparty screening post, 2026-08-05 ("Your Agent Has a Wallet
    # Now"). Same one-key-per-channel pattern so CloudWatch keeps channels
    # distinguishable while all rendering the x402 banner. Registered BEFORE the
    # post goes out, which is the whole point: an unregistered key logs
    # unmatched: and renders no banner at all.
    "x402":           "x402",
    "x402-post":      "x402",
    "x402-blog":      "x402",
    "x402-farcaster": "x402",
    "x402-linkedin":  "x402",
    "x402-telegram":  "x402",
    "x402-mastodon":  "x402",
    "x402-medium":    "x402",
    "x402scan":       "x402",
    # Added 2026-08-06 for the syndication run. The distribution plan named five
    # channels and only five keys were registered; these three cover the
    # x402-native channels the plan added later, registered before anything is
    # posted rather than after. `x402-hn` is registered now even though Hacker
    # News is deliberately held back, so the one shot there cannot go out
    # untracked.
    "x402-discord":   "x402",
    "x402-merit":     "x402",
    "x402-hn":        "x402",
    "hn": "github",
    "reddit": "github",
    "opencti": "xsoar",
    "awsmarketplace": "aws",
    "marketplace": "aws",
    # Already published in the wild and previously matching nothing. The
    # smolagents PyPI package and both APIs' quota-exceeded messages all send
    # users to ?source=hf-smolagents; that string was never a registered key.
    "hf-smolagents": "huggingface",
    "hf_smolagents": "huggingface",
    "smolagents": "huggingface",
    "hf": "huggingface",
    # n8n template attribution. Each approved template carries its own key so a
    # signup can be traced to the specific workflow that produced it, which is
    # the open question blocking the Make.com decision. All render the n8n
    # banner; they differ only in what gets logged.
    "n8n-offboarding": "n8n",
    "n8n-onboarding": "n8n",
    "n8n-shadow-ai": "n8n",
    "n8n-template": "n8n",
    "creators.n8n.io": "n8n",
    # The creator profile's own links field (n8n.io/creators/relayshieldadmin).
    # Distinct from the per-template keys so profile traffic -- someone browsing
    # the author rather than arriving from one specific workflow -- does not get
    # miscredited to whichever template happens to be linked. Registered 2026-08-02
    # BEFORE the link went live; an unregistered key logs unmatched: and renders
    # no banner, which is the failure the ?source=hf-smolagents entry above records.
    "n8n-profile": "n8n",
    # rsscan — the free local scanner. `rsscan` is the CTA in the escalation
    # report a developer forwards to whoever owns security, which is THE
    # dev -> security-lead bridge in the funnel; it shipped in the published
    # PyPI package and GitHub release on 2026-08-02 pointing at ?source=rsscan
    # while that key did not exist, so every arrival logged unmatched: and
    # rendered no banner. Registered 2026-08-02.
    #
    # 2026-08-08: rsscan now has its OWN banner and is deliberately NOT aliased
    # here. It was mapped to "github" on the reasoning "same developer audience",
    # which is true about the audience and wrong about the moment: someone who
    # just watched a secret scanner block their commit is not asking which client
    # library to install. The remaining catalogs stay on github, since a Docker
    # Hub or pre-commit arrival really is a generic integration visit.
    # Apify, 2026-08-27. One key per surface, same banner, so the store listing,
    # the actor README and the run output stay distinguishable in the logs and
    # in the Monday report's source breakdown.
    "apify":         "apify",
    "apify-store":   "apify",
    "apify-actor":   "apify",
    "apify-readme":  "apify",
    "apify-run":     "apify",
    "dockerhub":  "github",
    "docker":     "github",
    "circleci":   "github",
    "pre-commit": "github",
    "zapier": "github",
    # rsscan --deps release post, 2026-08-13. Registered BEFORE anything is
    # published, which is the rule this file keeps relearning: an unregistered
    # key renders no banner and logs unmatched:, so the link looks fine in the
    # post and quietly attributes nothing.
    #
    # `rsscan-deps` (no channel suffix) is the CTA inside the canonical post.
    # The suffixed keys keep the syndication channels distinguishable in
    # CloudWatch while all landing on the same banner.
    "rsscan-deps":           "rsscan-deps",
    "rsscan-deps-hf":        "rsscan-deps",
    "rsscan-deps-medium":    "rsscan-deps",
    "rsscan-deps-linkedin":  "rsscan-deps",
    "rsscan-deps-telegram":  "rsscan-deps",
    "rsscan-deps-devto":     "rsscan-deps",
    "rsscan-deps-mastodon":  "rsscan-deps",
}


def _resolve_source(referer: str, query_params: dict) -> tuple[str, str]:
    """Resolve an arrival to (logged_source_key, banner_html).

    Accepts BOTH ?src= and ?source=. Only ?src= was ever read, so every link
    already published using ?source= -- which is all of the smolagents ones --
    silently rendered no banner and recorded no attribution. Same failure the
    ?src=blog comment above describes, so both spellings are honoured now
    rather than trying to keep every published link in step with the code.

    The raw parameter is returned as the logged key, not the variant it maps
    to, so that n8n-offboarding and n8n-onboarding stay distinguishable in
    logs even though both render the same banner.
    """
    raw = (query_params.get("src") or query_params.get("source") or "").strip().lower()
    key = _SOURCE_ALIASES.get(raw, raw)
    if key in _SOURCE_BANNERS:
        return (raw or key), _SOURCE_BANNERS[key][1]

    host = (referer or "").lower()
    if host:
        for _key, (hosts, html) in _SOURCE_BANNERS.items():
            if any(h in host for h in hosts):
                return f"referer:{_key}", html

    # An unrecognised ?src=/?source= is worth logging loudly: it means a live
    # link points at a key that does not exist, which is invisible otherwise.
    if raw:
        return f"unmatched:{raw}", ""
    return "", ""


def _banner_for(referer: str, query_params: dict) -> str:
    """Pick the landing variant from an explicit ?src=/?source= or the Referer."""
    return _resolve_source(referer, query_params)[1]


# Matches an HTML comment. Applied to the rendered page, never to the literal,
# so authors can keep annotating the markup inline.
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _strip_html_comments(html: str) -> str:
    """Drop HTML comments before the page is served.

    Added 2026-08-09. The comments in LANDING_PAGE are engineering notes, and
    they were shipping to the public: one of them recorded that an n8n template
    "was demoted to Implement changes by the reviewer", which is a third party's
    rejection of our work, readable by anyone using View Source. Others named
    internal TODO ids and audit history.

    Stripping at render time rather than deleting them keeps the notes next to
    the markup they explain, which is where they are useful, and makes it
    impossible to leak the next one by forgetting. Verified safe: no <script>
    or <style> block in the page contains a comment marker, so there is no
    JavaScript string this can cut through.

    Runs AFTER the referrer banner substitution, since that placeholder is
    itself an HTML comment and must still be there to be replaced.
    """
    return _HTML_COMMENT_RE.sub("", html)


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
    banner = _banner_for(referer, query_params)
    return _html(_strip_html_comments(LANDING_PAGE.replace("<!--REFERRER_BANNER-->", banner)))


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
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="icon" href="/favicon.ico" sizes="any">
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
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="icon" href="/favicon.ico" sizes="any">
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
  <a class="btn" id="manual-open" href="net.relayshield.cryptoshieldmobile://unlock?session_id={session_id}">
    Open Crypto Shield
  </a>
</div>
<script>
  (function() {{
    // The app package was renamed to net.relayshield.cryptoshieldmobile for the
    // v1.5.0 release (dApp Store certificate rotation forced a new app record).
    // During the changeover both the new and the old build are in the wild, and
    // this page sits on the paid-conversion path, so try the new scheme first and
    // fall back to the legacy one before giving up and showing the manual button.
    var NEW_URL = "net.relayshield.cryptoshieldmobile://unlock?session_id={session_id}";
    var OLD_URL = "net.relayshield.cryptoshield://unlock?session_id={session_id}";

    var handedOff = false;
    document.addEventListener("visibilitychange", function() {{
      if (document.hidden) handedOff = true;   // the app took over
    }});

    window.location.href = NEW_URL;

    setTimeout(function() {{
      if (!handedOff) window.location.href = OLD_URL;
    }}, 1200);

    setTimeout(function() {{
      if (handedOff) return;
      document.getElementById("msg").textContent =
        "If the app didn't open automatically, tap the button below.";
    }}, 2400);
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
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="icon" href="/favicon.ico" sizes="any">
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
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="icon" href="/favicon.ico" sizes="any">
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
    #
    # `source=` added 2026-08-01. Referer alone was never enough: it is stripped
    # on Slack, Discord and native-app clicks, and n8n's own template gallery is
    # exactly that kind of click. Since the resolved key is logged even when no
    # banner renders, an "unmatched:" entry now surfaces a live link pointing at
    # a key that does not exist -- previously silent, and the reason
    # ?source=hf-smolagents went unnoticed.
    #
    # CloudWatch Logs Insights, arrivals by source over 30 days:
    #   fields @timestamp, @message
    #   | filter @message like /developer-signup request/ and source != "-"
    #   | parse @message "source=*" as src
    #   | stats count() by src
    #   | sort by count() desc
    source_key = _resolve_source(referer, event.get("queryStringParameters") or {})[0]
    logger.info(
        "developer-signup request method=%s path=%s referer=%s source=%s",
        method, path, referer or "-", source_key or "-",
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

    if method == "POST" and path in ("/developer/bundle-checkout", "/developer/bundle-checkout/"):
        try:
            body = json.loads(event.get("body") or "{}")
        except Exception:
            body = {}
        return handle_bundle_checkout(body)

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
