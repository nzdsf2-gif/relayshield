"""
RelayShield Developer Signup Lambda

Routes:
  GET  /developers                 — developer landing page with signup form
  GET  /developer/success          — post-checkout confirmation page
  GET  /developer/topup            — credit pack purchase page
  POST /developer/signup           — create Stripe Customer + Checkout session → return checkout_url
  POST /developer/topup            — create one-time Stripe Checkout for credit pack → return checkout_url
  POST /developer/stripe-webhook   — checkout.session.completed → issue key OR add credits
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

# One price per metered endpoint — created in Stripe Dashboard Jun 11 2026
STRIPE_PRICE_IDS = [
    "price_1Th6Q5L2dcjOeFiYG1RkNJeP",  # breach        $0.10/call
    "price_1Th6SaL2dcjOeFiYfumGGvde",  # sim-swap      $0.25/call
    "price_1Th6TGL2dcjOeFiYLLp55faD",  # infostealer   $0.50/call
    "price_1Th6U1L2dcjOeFiY0nGMVt9u",  # domain        $0.30/call
    "price_1ThtUrL2dcjOeFiYTYgh9BtZ",  # crypto-intel  $0.30/call
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

def handle_signup(body: dict) -> dict:
    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _err("email is required")

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
        # Store email in metadata so webhook can retrieve it without a second Stripe call
        "subscription_data[metadata][developer_email]": email,
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

def _issue_api_key(customer_id: str, subscription_id: str, email: str) -> str:
    api_key = f"rs_live_{uuid.uuid4().hex}"
    dynamodb.Table(API_KEYS_TABLE).put_item(Item={
        "api_key":                api_key,
        "stripe_customer_id":     customer_id,
        "stripe_subscription_id": subscription_id,
        "email":                  email,
        "active":                 True,
        "created_at":             datetime.now(timezone.utc).isoformat(),
    })
    logger.info("API key issued customer=%s subscription=%s email=%s", customer_id, subscription_id, email)
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
POST {API_BASE_URL}/v1/metered/breach        — email breach check       $0.10/call
POST {API_BASE_URL}/v1/metered/sim-swap      — SIM swap detection       $0.25/call
POST {API_BASE_URL}/v1/metered/infostealer   — infostealer log check    $0.50/call
POST {API_BASE_URL}/v1/metered/domain        — typosquat domain scan    $0.30/call

Quick start
-----------
curl -X POST {API_BASE_URL}/v1/metered/breach \\
  -H "X-RS-API-KEY: {api_key}" \\
  -H "Content-Type: application/json" \\
  -d '{{"email":"you@example.com"}}'

Billing: usage is metered monthly via Stripe. You will only be charged for calls made.

Docs & support: https://relayshield.net/developers
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

    if event_type == "checkout.session.completed":
        session         = event["data"]["object"]
        customer_id     = session.get("customer", "")
        metadata        = session.get("metadata") or {}
        checkout_type   = metadata.get("checkout_type", "subscription")
        email           = (
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
        else:
            # Metered subscription signup — issue new API key
            subscription_id = session.get("subscription", "")
            if not customer_id or not subscription_id:
                logger.error("missing customer or subscription in session=%s", session.get("id"))
                return {"statusCode": 200, "body": "ok"}

            # Idempotency — don't re-issue if key already exists for this subscription
            existing = dynamodb.Table(API_KEYS_TABLE).scan(
                FilterExpression=Attr("stripe_subscription_id").eq(subscription_id)
            )
            if existing.get("Items"):
                logger.info("API key already issued for subscription=%s — skipping", subscription_id)
                return {"statusCode": 200, "body": "ok"}

            api_key = _issue_api_key(customer_id, subscription_id, email)
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
        "headers": {"Content-Type": "text/html; charset=utf-8"},
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
  .price-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 1rem; }
  .price-card { background: var(--surface); border: 1px solid var(--border);
                border-radius: 12px; padding: 1.4rem 1.2rem; }
  .price-card .endpoint { font-size: .78rem; font-family: 'SF Mono', 'Fira Code', monospace;
                          color: var(--accent); background: rgba(108,99,255,.1);
                          padding: .2rem .55rem; border-radius: 5px; display: inline-block;
                          margin-bottom: .85rem; word-break: break-all; }
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

<div class="hero">
  <div class="badge">Developer API</div>
  <h1>Security intelligence<br>for <span>developers &amp; agents</span></h1>
  <p>Breach detection, SIM swap monitoring, infostealer exposure, and domain lookalike scanning — REST API, metered billing, no commitments.</p>

  <div class="signup-box">
    <p>Enter your email to get started. You'll be redirected to a secure checkout to save a card. Your API key arrives by email instantly.</p>
    <form id="signup-form">
      <div class="input-row">
        <input type="email" id="email-input" placeholder="you@company.com" required autocomplete="email">
        <button type="submit" id="submit-btn">Get API key →</button>
      </div>
      <div id="form-error"></div>
    </form>
    <p class="form-note">Metered billing · No monthly minimum · Cancel anytime</p>
  </div>
</div>

<div class="section">
  <div class="section-title">Endpoints &amp; pricing</div>
  <div class="section-sub">Pay only for what you use. Billed monthly via Stripe.</div>
  <div class="price-grid">
    <div class="price-card">
      <div class="endpoint">/v1/metered/breach</div>
      <div class="price">$0.10<span class="per"> / call</span></div>
      <div class="desc">Email breach check via HIBP — name, date, data classes exposed</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/sim-swap</div>
      <div class="price">$0.25<span class="per"> / call</span></div>
      <div class="desc">SIM swap detection via Twilio Lookup v2 — carrier + swap timestamp</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/infostealer</div>
      <div class="price">$0.50<span class="per"> / call</span></div>
      <div class="desc">Infostealer log check — stolen credentials, malware path, at-risk services</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/domain</div>
      <div class="price">$0.30<span class="per"> / call</span></div>
      <div class="desc">Typosquat domain scan — active lookalikes via DNS + cert transparency</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/oauth-watchlist</div>
      <div class="price">$0.20<span class="per"> / call</span></div>
      <div class="desc">OAuth supply chain check — 31 watched apps, breach exposure detection</div>
    </div>
    <div class="price-card">
      <div class="endpoint">/v1/metered/crypto-intel</div>
      <div class="price">$0.30<span class="per"> / call</span></div>
      <div class="desc">Asset surface — wallet address risk, token honeypot &amp; tax flags, counterparty screening</div>
    </div>
  </div>
</div>

<div class="section" style="margin-top:2rem">
  <div class="section-title">Threat Intelligence API <span style="background:var(--accent);color:#fff;font-size:.7rem;padding:.15rem .5rem;border-radius:4px;margin-left:.5rem;vertical-align:middle">NEW</span></div>
  <p style="color:var(--muted);font-size:.95rem;margin:.5rem 0 1.25rem">On-demand IOC lookup against RelayShield&apos;s live Telegram-sourced criminal channel intelligence — <strong>24–72 hours ahead of public breach databases.</strong> Emails, domains, phone numbers, and wallet addresses matched in real time against infostealer log markets, credential dump channels, and SIM swap service listings.</p>
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
        <td style="text-align:center;padding:.45rem .75rem" colspan="2">31 criminal Telegram channels (infostealer, credential dumps, SIM swap, crypto drainers)</td>
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
      <div class="desc">MSP tier — up to 10,000 IOC queries/month. Embed in SOAR playbooks, SIEM enrichment, or incident response workflows.</div>
      <a href="https://buy.stripe.com/28EcN66Umb1be56bgb0Ny0e" style="display:block;margin-top:1rem;background:var(--accent);color:#fff;text-align:center;padding:.5rem;border-radius:6px;text-decoration:none;font-size:.85rem;font-weight:600">Subscribe — $499/mo</a>
    </div>
    <div class="price-card" style="border-color:var(--accent)">
      <div class="endpoint" style="color:var(--accent)">/v1/intel/telegram</div>
      <div class="price">$999<span class="per"> / mo</span></div>
      <div class="desc">MSSP volume tier — unlimited calls, priority support + SLA. For MSSPs running continuous monitoring across multiple client environments.</div>
      <a href="https://buy.stripe.com/4gM3cw1A23yJf9a2JF0Ny0f" style="display:block;margin-top:1rem;background:var(--accent);color:#fff;text-align:center;padding:.5rem;border-radius:6px;text-decoration:none;font-size:.85rem;font-weight:600">Subscribe — $999/mo</a>
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
</div>

<footer>
  <p>RelayShield LLC · <a href="https://relayshield.net">relayshield.net</a> · <a href="mailto:support@relayshield.net">support@relayshield.net</a></p>
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
    const res  = await fetch('/developer/signup', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({email})
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

  <a class="btn" href="https://relayshield.net/developers">Back to docs</a>
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


def handle_landing_page() -> dict:
    return _html(LANDING_PAGE)


def handle_success_page() -> dict:
    return _html(SUCCESS_PAGE)


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
    logger.info("developer-signup request method=%s path=%s", method, path)

    if method == "GET" and path in ("/developers", "/developers/"):
        return handle_landing_page()

    if method == "GET" and path in ("/developer/success", "/developer/success/"):
        return handle_success_page()

    if method == "GET" and path in ("/developer/topup", "/developer/topup/"):
        return handle_topup_page()

    if method == "GET" and path in ("/developer/topup-success", "/developer/topup-success/"):
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
