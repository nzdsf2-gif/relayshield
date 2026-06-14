"""
RelayShield B2A API Lambda

Exposes RelayShield security intelligence as REST endpoints for
Business-to-Agent (B2A) and third-party developer consumption.

Subscription endpoints (API key required — enforced by API Gateway usage plan):
  POST /v1/breach                   — HIBP email breach check
  POST /v1/scan-url                 — VirusTotal URL malware analysis
  POST /v1/scan-file                — VirusTotal binary/file analysis
  POST /v1/scan-wallet              — GoPlus EVM wallet risk scan (legacy)
  POST /v1/wallet-risk              — Multi-chain wallet risk: EVM/Solana/TON/Bitcoin (auto-detect)
  POST /v1/token-security           — GoPlus token risk: honeypot, tax, ownership flags
  POST /v1/nft-security             — GoPlus NFT contract risk scan
  POST /v1/sim-swap                 — Twilio Lookup v2 SIM/eSIM swap detection
  POST /v1/domain                   — Typosquat/lookalike domain scan (DNS + CT + GSB)
  POST /v1/intel/telegram           — Threat Intelligence API: IOC lookup against live Telegram criminal channel pipeline (intel_access flag required)
  GET  /v1/result/{analysis_id}     — Poll VT scan result

Pay-as-you-go endpoints (no API key — x402 payment verified in Lambda):
  POST /v1/payg/breach              — $0.10 USDC
  POST /v1/payg/sim-swap            — $0.25 USDC
  POST /v1/payg/domain              — $0.50 USDC
  POST /v1/payg/oauth-watchlist     — $0.15 USDC
  POST /v1/payg/scan-wallet         — $0.10 USDC (legacy EVM-only)
  POST /v1/payg/scan-url            — $0.05 USDC
  POST /v1/payg/scan-file           — $0.10 USDC
  POST /v1/payg/wallet-risk         — $0.15 USDC — multi-chain EVM/Solana/TON/Bitcoin
  POST /v1/payg/token-security      — $0.10 USDC — token honeypot + tax analysis
  POST /v1/payg/nft-security        — $0.10 USDC — NFT contract risk
  POST /v1/payg/wallet-screen-batch — $0.50 USDC — batch up to 10 addresses
  POST /v1/payg/infostealer         — $0.15 USDC — Hudson Rock infostealer detection
  GET  /v1/payg/result/{id}         — $0.00 (free — poll a paid scan)

x402 payment flow:
  1. Call PAYG endpoint with no X-PAYMENT header → receive 402 + PAYMENT-REQUIRED header
  2. Pay USDC on Base to the address in PAYMENT-REQUIRED
  3. Retry with X-PAYMENT header containing payment proof
  4. Lambda verifies proof via PayAI x402 facilitator → executes and returns result

Authentication: Subscription routes — API key enforced by API Gateway usage plan.
               PAYG routes — no API key; x402 payment verified inside this Lambda.

Environment variables (set on Lambda):
  RELAYSHIELD_X402_WALLET — Coinbase Exchange USDC deposit address (x402 payTo)

Secrets used (all in Secrets Manager):
  relayshield/hibp_api_key
  relayshield/virustotal_api_key
  relayshield/twilio_account_sid / twilio_auth_token
  relayshield/google_safe_browsing
"""

import base64
import concurrent.futures
import json
import logging
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

import boto3

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# AWS clients
# ---------------------------------------------------------------------------

secrets_client  = boto3.client("secretsmanager")
dynamodb        = boto3.resource("dynamodb")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# x402 PAYG configuration
X402_PAYTO_ADDRESS   = os.environ.get("RELAYSHIELD_X402_WALLET", "")   # EVM (Base) payTo
SOL_PAYTO_ADDRESS    = os.environ.get("RELAYSHIELD_SOL_WALLET", "")    # Solana payTo
X402_FACILITATOR_URL = "https://facilitator.payai.network"   # EVM (Base) — PayAI facilitator; auto-listed in Bazaar, free tier 10k/month
SOL_FACILITATOR_URL  = "https://x402.org/facilitator"         # Solana — CDP Facilitator (manages CDP fee payer EwWqGE4Z...)
USDC_BASE_ADDRESS    = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"   # USDC on Base
USDC_SOL_ADDRESS     = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" # USDC on Solana mainnet
BASE_CHAIN_ID        = "base"           # V1 named network (eip155:8453 is V2 CAIP-2 format)
SOL_CHAIN_ID         = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"       # Solana mainnet CAIP-2
# CDP Facilitator Solana fee-payer public key (sponsors gas for all SVM x402 transactions)
SOL_FEE_PAYER        = "EwWqGE4ZFKLofuestmU4LDdK7XM1N4ALgdZccwYugwGd"

# PAYG pricing in USDC base units (6 decimals): $0.10 = 100000
PAYG_PRICE_UNITS: dict[str, int] = {
    "/v1/payg/breach":                100000,
    "/v1/payg/sim-swap":              250000,
    "/v1/payg/domain":                500000,
    "/v1/payg/oauth-watchlist":       150000,
    "/v1/payg/scan-wallet":           100000,   # legacy — EVM only
    "/v1/payg/scan-url":               50000,
    "/v1/payg/scan-file":             100000,
    # Crypto Shield intelligence endpoints
    "/v1/payg/wallet-risk":           150000,   # $0.15 — multi-chain EVM/Solana/TON
    "/v1/payg/token-security":        100000,   # $0.10 — GoPlus token risk
    "/v1/payg/nft-security":          100000,   # $0.10 — GoPlus NFT risk
    "/v1/payg/wallet-screen-batch":   500000,   # $0.50 — up to 10 addresses
    "/v1/payg/infostealer":           150000,   # $0.15 — Hudson Rock infostealer check
}

GOPLUS_BASE_URL        = "https://api.gopluslabs.io/api/v1/address_security"
GOPLUS_TOKEN_URL       = "https://api.gopluslabs.io/api/v1/token_security/{chain_id}"
GOPLUS_NFT_URL         = "https://api.gopluslabs.io/api/v1/nft_security"
TONAPI_ACCOUNTS_URL    = "https://tonapi.io/v2/accounts/{address}"

# OAuth supply chain watchlist — high-risk OAuth-capable SaaS apps
OAUTH_WATCHLIST = {
    "slack", "notion", "github", "zapier", "linear", "vercel", "loom",
    "hubspot", "okta", "salesforce", "dropbox", "box", "atlassian", "jira",
    "confluence", "asana", "monday", "clickup", "figma", "miro",
    "zoom", "webex", "intercom", "zendesk", "freshdesk",
    "openai", "anthropic", "canva", "jasper", "grammarly", "copy.ai",
}

OAUTH_REVOCATION_URLS: dict[str, str] = {
    "GitHub":     "https://github.com/settings/applications",
    "Slack":      "https://slack.com/apps/manage",
    "Notion":     "https://www.notion.so/my-integrations",
    "Vercel":     "https://vercel.com/account/tokens",
    "Zapier":     "https://zapier.com/app/connections",
    "Linear":     "https://linear.app/settings/api",
    "HubSpot":    "https://app.hubspot.com/integrations-settings",
    "Dropbox":    "https://www.dropbox.com/account/connected_apps",
    "Atlassian":  "https://id.atlassian.com/manage-profile/apps",
    "Salesforce": "https://help.salesforce.com/s/articleView?id=sf.remoteaccess_revoke_token.htm",
}

API_KEYS_TABLE   = "relayshield_api_keys"
INTEL_IOCS_TABLE = "relayshield_intel_iocs"
STRIPE_SECRET_NAME = "relayshield/stripe_secret_key"
STRIPE_METER_API   = "https://api.stripe.com/v1/billing/meter_events"

# Stripe Billing Meter event names — one per metered endpoint.
# These must match the event_name values on the meters created in Stripe Dashboard.
STRIPE_METER_EVENTS: dict[str, str] = {
    "/v1/metered/breach":           "relayshield_breach_calls",
    "/v1/metered/sim-swap":         "relayshield_sim_swap_calls",
    "/v1/metered/infostealer":      "relayshield_infostealer_calls",
    "/v1/metered/domain":           "relayshield_domain_calls",
    "/v1/metered/oauth-watchlist":  "relayshield_oauth_watchlist_calls",
    "/v1/metered/crypto-intel":     "relayshield_crypto_intel_calls",
}

# Credits deducted per successful call (1 credit = $0.01)
METERED_CREDIT_COSTS: dict[str, int] = {
    "/v1/metered/breach":          10,   # $0.10
    "/v1/metered/sim-swap":        25,   # $0.25
    "/v1/metered/infostealer":     50,   # $0.50
    "/v1/metered/domain":          30,   # $0.30
    "/v1/metered/oauth-watchlist": 20,   # $0.20
    "/v1/metered/crypto-intel":    30,   # $0.30
}

HIBP_SECRET_NAME  = "relayshield/hibp_api_key"
VT_SECRET_NAME    = "relayshield/virustotal_api_key"
TWILIO_SID_SECRET = "relayshield/twilio_account_sid"
TWILIO_TOK_SECRET = "relayshield/twilio_auth_token"
GSB_SECRET_NAME   = "relayshield/google_safe_browsing"

HIBP_BASE_URL     = "https://haveibeenpwned.com/api/v3/breachedaccount/"
VT_BASE_URL       = "https://www.virustotal.com/api/v3"
TWILIO_LOOKUP_URL = "https://lookups.twilio.com/v2/PhoneNumbers/{phone}"
GSB_URL           = "https://safebrowsing.googleapis.com/v4/threatMatches:find"
CRT_SH_URL        = "https://crt.sh/?q={domain}&output=json"

VT_POLL_INTERVAL  = 3    # seconds between VT status polls
VT_URL_MAX_WAIT   = 30   # max seconds for URL analysis
VT_FILE_MAX_WAIT  = 45   # max seconds for file analysis

# Typosquat generation config (mirrors domain_monitor)
COMMON_TLDS = [
    ".com", ".net", ".org", ".co", ".io", ".biz",
    ".info", ".us", ".co.uk", ".ca", ".com.au",
]
PHISHING_PREFIXES = ["secure-", "login-", "my-", "get-", "support-", "help-"]
PHISHING_SUFFIXES = ["-secure", "-login", "-online", "-support", "-portal", "-verify"]

# ---------------------------------------------------------------------------
# Secrets helpers
# ---------------------------------------------------------------------------

_secret_cache: dict[str, str] = {}


def _get_secret(secret_name: str) -> str:
    if secret_name not in _secret_cache:
        raw = secrets_client.get_secret_value(SecretId=secret_name)["SecretString"].strip()
        _secret_cache[secret_name] = raw
    return _secret_cache[secret_name]


def _get_secret_json(secret_name: str, key: str) -> str:
    raw = _get_secret(secret_name)
    try:
        return json.loads(raw)[key]
    except (json.JSONDecodeError, KeyError):
        return raw


def _hibp_api_key() -> str:
    return _get_secret_json(HIBP_SECRET_NAME, "HIBP_API_KEY")


def _vt_api_key() -> str:
    return _get_secret_json(VT_SECRET_NAME, "virustotal_api_key")


def _twilio_creds() -> tuple[str, str]:
    sid   = _get_secret_json(TWILIO_SID_SECRET, "TWILIO_ACCOUNT_SID")
    token = _get_secret_json(TWILIO_TOK_SECRET, "TWILIO_AUTH_TOKEN")
    return sid, token


def _gsb_api_key() -> str:
    raw = _get_secret(GSB_SECRET_NAME)
    try:
        return json.loads(raw)["google_safe_browsing_api_key"]
    except (json.JSONDecodeError, KeyError):
        return raw


def _stripe_secret_key() -> str:
    raw = _get_secret(STRIPE_SECRET_NAME)
    try:
        return json.loads(raw).get("stripe_secret_key") or json.loads(raw).get("STRIPE_SECRET_KEY") or raw
    except (json.JSONDecodeError, KeyError):
        return raw


# ---------------------------------------------------------------------------
# Stripe metered billing helpers
# ---------------------------------------------------------------------------

def _verify_rs_api_key(api_key_str: str) -> dict | None:
    """Look up a RelayShield API key in DynamoDB. Returns the record or None."""
    if not api_key_str or not api_key_str.startswith("rs_live_"):
        return None
    try:
        table  = dynamodb.Table(API_KEYS_TABLE)
        result = table.get_item(Key={"api_key": api_key_str})
        item   = result.get("Item")
        if item and item.get("active"):
            return item
        return None
    except Exception as exc:
        logger.error("API key lookup failed key=%s error=%s", api_key_str[:16], exc)
        return None


def _record_stripe_meter_event(stripe_customer_id: str, event_name: str) -> None:
    """Post a usage event to Stripe Billing Meter. Fire-and-forget — never raises."""
    try:
        secret_key = _stripe_secret_key()
        identifier = f"{stripe_customer_id}-{uuid.uuid4().hex}"
        payload    = urllib.parse.urlencode({
            "event_name":                  event_name,
            "payload[value]":              "1",
            "payload[stripe_customer_id]": stripe_customer_id,
            "identifier":                  identifier,
        }).encode("utf-8")
        req = urllib.request.Request(
            STRIPE_METER_API,
            data=payload,
            headers={
                "Authorization":  f"Bearer {secret_key}",
                "Content-Type":   "application/x-www-form-urlencoded",
                "Stripe-Version": "2024-06-20",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            logger.info("stripe meter event recorded customer=%s event=%s status=%d",
                        stripe_customer_id, event_name, resp.status)
    except Exception as exc:
        logger.warning("stripe meter event failed (non-fatal) customer=%s event=%s error=%s",
                       stripe_customer_id, event_name, exc)


def handle_metered_request(path: str, method: str, event: dict) -> dict:
    """Auth + dispatch for /v1/metered/* routes. Verifies RS API key, runs handler,
    then records a Stripe Billing Meter event on success."""
    if method != "POST":
        return _err(f"{path} only accepts POST requests", 405)

    headers    = event.get("headers") or {}
    api_key_str = (
        headers.get("X-RS-API-KEY")
        or headers.get("x-rs-api-key")
        or headers.get("Authorization", "").removeprefix("Bearer ").strip()
    )

    key_record = _verify_rs_api_key(api_key_str)
    if not key_record:
        return {
            "statusCode": 401,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "ok":    False,
                "error": "Invalid or missing API key. Pass your key as X-RS-API-KEY header.",
                "docs":  "https://relayshield.net/developers",
            }),
        }

    metered_routes = {
        "/v1/metered/breach":          handle_breach,
        "/v1/metered/sim-swap":        handle_sim_swap,
        "/v1/metered/infostealer":     handle_infostealer,
        "/v1/metered/domain":          handle_domain,
        "/v1/metered/oauth-watchlist": handle_oauth_watchlist,
        "/v1/metered/crypto-intel":    handle_crypto_intel,
    }
    handler = metered_routes.get(path)
    if not handler:
        return _err(f"unknown metered endpoint: {path}", 404)

    # Billing check before executing — must have credits OR active subscription
    credit_balance     = int(key_record.get("credit_balance") or 0)
    has_subscription   = bool(key_record.get("stripe_subscription_id"))
    credit_cost        = METERED_CREDIT_COSTS.get(path, 0)
    use_credits        = credit_balance >= credit_cost

    if not use_credits and not has_subscription:
        return {
            "statusCode": 402,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "ok":      False,
                "error":   "Insufficient credits and no active subscription.",
                "topup_url": "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod/developer/topup",
            }),
        }

    params = _body(event)
    try:
        result = handler(params)
    except Exception as exc:
        logger.exception("Unhandled error in metered %s: %s", path, exc)
        return _err("internal server error", 500)

    # Only bill on success
    if result.get("statusCode", 200) < 300:
        if use_credits:
            # Deduct credits atomically
            try:
                dynamodb.Table(API_KEYS_TABLE).update_item(
                    Key={"api_key": api_key_str},
                    UpdateExpression="SET credit_balance = credit_balance - :cost",
                    ConditionExpression="credit_balance >= :cost",
                    ExpressionAttributeValues={":cost": credit_cost},
                )
                logger.info("credits deducted key=%s cost=%d remaining=%d",
                            api_key_str[:16], credit_cost, credit_balance - credit_cost)
            except Exception as exc:
                logger.warning("credit deduction failed (non-fatal) key=%s error=%s", api_key_str[:16], exc)
        else:
            # Fall back to Stripe meter event
            event_name         = STRIPE_METER_EVENTS.get(path)
            stripe_customer_id = key_record.get("stripe_customer_id", "")
            if event_name and stripe_customer_id:
                _record_stripe_meter_event(stripe_customer_id, event_name)

    return result


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _ok(data: dict, status: int = 200) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"ok": True, "data": data}),
    }


def _err(message: str, status: int = 400) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"ok": False, "error": message}),
    }


def _body(event: dict) -> dict:
    try:
        raw = event.get("body") or "{}"
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/breach
# ---------------------------------------------------------------------------
# Request:  { "email": "user@example.com" }
# Response: { "email": "...", "breach_count": N, "breaches": [...] }
#
# Breaches list contains summarised HIBP objects: Name, Domain, BreachDate,
# DataClasses. Full HIBP schema preserved so callers can apply their own
# filtering logic.

def handle_breach(params: dict) -> dict:
    email = (params.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _err("email is required and must be a valid address")

    api_key = _hibp_api_key()
    url     = f"{HIBP_BASE_URL}{urllib.parse.quote(email)}?truncateResponse=false"
    req     = urllib.request.Request(
        url,
        headers={"hibp-api-key": api_key, "user-agent": "RelayShield-API"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            breaches = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            breaches = []
        elif exc.code == 429:
            return _err("HIBP rate limit reached — retry in a few seconds", 429)
        else:
            logger.error("HIBP HTTP %d for %s", exc.code, email)
            return _err(f"HIBP returned HTTP {exc.code}", 502)
    except Exception as exc:
        logger.exception("HIBP call failed for %s: %s", email, exc)
        return _err("breach check failed — upstream error", 502)

    summary = [
        {
            "name":         b.get("Name"),
            "domain":       b.get("Domain"),
            "breach_date":  b.get("BreachDate"),
            "data_classes": b.get("DataClasses", []),
            "is_verified":  b.get("IsVerified", False),
        }
        for b in breaches
    ]

    logger.info("breach check — email=%s count=%d", email, len(summary))
    return _ok({
        "email":        email,
        "breach_count": len(summary),
        "breaches":     summary,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/scan-url
# ---------------------------------------------------------------------------
# Request:  { "url": "https://example.com/path" }
# Response: { "status": "pending", "analysis_id": "...", "poll_endpoint": "/v1/result/{id}" }
#
# Submits to VirusTotal and returns immediately with an analysis_id.
# Caller polls GET /v1/result/{analysis_id} for the verdict.

def handle_scan_url(params: dict) -> dict:
    url = (params.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return _err("url is required and must start with http:// or https://")

    api_key = _vt_api_key()
    payload = urllib.parse.urlencode({"url": url}).encode("utf-8")
    req = urllib.request.Request(
        f"{VT_BASE_URL}/urls",
        data=payload,
        headers={
            "x-apikey": api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            analysis_id = json.loads(resp.read()).get("data", {}).get("id")
    except Exception as exc:
        logger.error("VT URL submit failed for %s: %s", url, exc)
        return _err("URL submission to VirusTotal failed", 502)

    if not analysis_id:
        return _err("VirusTotal did not return an analysis ID", 502)

    logger.info("scan-url submitted — url=%s analysis_id=%s", url, analysis_id)
    return _ok({
        "status":        "pending",
        "target":        url,
        "analysis_id":   analysis_id,
        "poll_endpoint": f"/v1/result/{analysis_id}",
        "note":          "Poll /v1/result/{analysis_id} every 5s until status is completed",
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/scan-file
# ---------------------------------------------------------------------------
# Request:  { "file_url": "https://cdn.example.com/report.pdf",
#             "filename": "report.pdf" }          ← filename optional
# Response: same shape as /v1/scan-url
#
# RelayShield downloads the file from file_url, then submits the bytes to
# VirusTotal /files. The caller never needs to forward raw bytes — only a URL.

def handle_scan_file(params: dict) -> dict:
    file_url = (params.get("file_url") or "").strip()
    filename = (params.get("filename") or file_url.split("/")[-1] or "upload").strip()

    if not file_url.startswith(("http://", "https://")):
        return _err("file_url is required and must start with http:// or https://")

    # Download the file
    try:
        req = urllib.request.Request(file_url, method="GET")
        with urllib.request.urlopen(req, timeout=20) as resp:
            file_bytes   = resp.read()
            content_type = resp.headers.get_content_type() or "application/octet-stream"
    except Exception as exc:
        logger.error("File download failed for %s: %s", file_url, exc)
        return _err(f"could not download file from file_url: {exc}", 400)

    if not file_bytes:
        return _err("downloaded file was empty", 400)

    api_key  = _vt_api_key()
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n"
        "\r\n"
    ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{VT_BASE_URL}/files",
        data=body,
        headers={
            "x-apikey": api_key,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            analysis_id = json.loads(resp.read()).get("data", {}).get("id")
    except Exception as exc:
        logger.error("VT file submit failed: %s", exc)
        return _err("file submission to VirusTotal failed", 502)

    if not analysis_id:
        return _err("VirusTotal did not return an analysis ID", 502)

    logger.info("scan-file submitted — file_url=%s analysis_id=%s", file_url, analysis_id)
    return _ok({
        "status":        "pending",
        "target":        file_url,
        "filename":      filename,
        "analysis_id":   analysis_id,
        "poll_endpoint": f"/v1/result/{analysis_id}",
        "note":          "Poll /v1/result/{analysis_id} every 5s until status is completed",
    })


def _poll_vt(analysis_id: str, api_key: str, max_wait: int) -> dict | None:
    """Poll VT analyses/{id} until completed or timeout. Returns stats dict or None."""
    req = urllib.request.Request(
        f"{VT_BASE_URL}/analyses/{analysis_id}",
        headers={"x-apikey": api_key},
        method="GET",
    )
    waited = 0
    while waited <= max_wait:
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data  = json.loads(resp.read())
                attrs = data.get("data", {}).get("attributes", {})
                if attrs.get("status") == "completed":
                    return attrs.get("stats", {})
        except Exception as exc:
            logger.error("VT poll error %s: %s", analysis_id, exc)
            return None
        time.sleep(VT_POLL_INTERVAL)
        waited += VT_POLL_INTERVAL
    logger.warning("VT analysis %s timed out after %ds", analysis_id, max_wait)
    return None


def _vt_response(target: str, analysis_id: str, stats: dict | None) -> dict:
    if stats is None:
        return _ok({
            "target":       target,
            "analysis_id":  analysis_id,
            "verdict":      "timeout",
            "note":         "analysis did not complete in time — treat as unverified",
        })
    malicious  = stats.get("malicious", 0)
    suspicious = stats.get("suspicious", 0)
    harmless   = stats.get("harmless", 0)
    undetected = stats.get("undetected", 0)
    total      = malicious + suspicious + harmless + undetected
    if malicious > 0:
        verdict = "malicious"
    elif suspicious > 0:
        verdict = "suspicious"
    else:
        verdict = "clean"
    logger.info("VT result — target=%s verdict=%s malicious=%d/%d",
                target, verdict, malicious, total)
    return _ok({
        "target":         target,
        "analysis_id":    analysis_id,
        "verdict":        verdict,
        "malicious":      malicious,
        "suspicious":     suspicious,
        "harmless":       harmless,
        "undetected":     undetected,
        "total_engines":  total,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/sim-swap
# ---------------------------------------------------------------------------
# Request:  { "phone": "+14155551234" }
# Response: { "phone": "...", "swapped": bool, "swap_timestamp": "...",
#             "carrier": "...", "checked_at": "..." }

def handle_sim_swap(params: dict) -> dict:
    phone = (params.get("phone") or "").strip()
    if not phone.startswith("+"):
        return _err("phone is required in E.164 format (e.g. +14155551234)")

    account_sid, auth_token = _twilio_creds()
    encoded     = urllib.parse.quote(phone, safe="")
    url         = TWILIO_LOOKUP_URL.format(phone=encoded) + "?Fields=sim_swap"
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()

    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Basic {credentials}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body         = json.loads(resp.read())
            sim_swap_obj = body.get("sim_swap") or {}
            last_swap    = sim_swap_obj.get("last_sim_swap") or {}
            result = {
                "phone":          phone,
                "swapped":        bool(last_swap.get("swapped_in_period", False)),
                "swap_timestamp": last_swap.get("last_sim_swap_date", ""),
                "carrier":        sim_swap_obj.get("carrier_name", ""),
                "checked_at":     datetime.now(timezone.utc).isoformat(),
            }
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Twilio Lookup HTTP %d for %s: %s", exc.code, phone, error_body)
        return _err(f"Twilio returned HTTP {exc.code}", 502)
    except Exception as exc:
        logger.exception("Twilio Lookup failed for %s: %s", phone, exc)
        return _err("SIM swap check failed — upstream error", 502)

    logger.info("sim-swap check — phone=%s swapped=%s carrier=%s",
                phone, result["swapped"], result["carrier"] or "unknown")
    return _ok(result)


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/domain
# ---------------------------------------------------------------------------
# Request:  { "domain": "acme.com" }
# Response: { "domain": "...", "lookalikes_found": N,
#             "lookalikes": [{ "domain": "...", "gsb_flagged": bool,
#                              "cert_count": N, "cert_recent": bool,
#                              "latest_cert_issued": "..." }],
#             "candidates_checked": N, "checked_at": "..." }

def handle_domain(params: dict) -> dict:
    domain = (params.get("domain") or "").strip().lower()
    if not domain or "." not in domain:
        return _err("domain is required (e.g. acme.com)")
    # Strip scheme if someone passes a full URL
    for prefix in ("https://", "http://", "www."):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]

    candidates  = _generate_typosquat_permutations(domain)
    prioritised = _prioritise_candidates(domain, candidates)
    active      = _find_active_lookalikes(prioritised)

    lookalikes = [{"domain": d} for d in active]

    logger.info("domain scan — domain=%s candidates=%d active=%d",
                domain, len(prioritised), len(active))
    return _ok({
        "domain":             domain,
        "lookalikes_found":   len(active),
        "lookalikes":         lookalikes,
        "candidates_checked": len(prioritised),
        "checked_at":         datetime.now(timezone.utc).isoformat(),
    })


def _generate_typosquat_permutations(domain: str) -> set[str]:
    if "." not in domain:
        return set()
    dot_pos = domain.rfind(".")
    name    = domain[:dot_pos]
    tld     = domain[dot_pos:]
    perms: set[str] = set()

    for i in range(len(name)):
        candidate = name[:i] + name[i + 1:]
        if candidate:
            perms.add(candidate + tld)
    for i, c in enumerate(name):
        perms.add(name[:i] + c + c + name[i + 1:] + tld)
    for i in range(len(name) - 1):
        t = list(name)
        t[i], t[i + 1] = t[i + 1], t[i]
        perms.add("".join(t) + tld)
    for i, c in enumerate(name):
        if c == "o":
            perms.add(name[:i] + "0" + name[i + 1:] + tld)
        elif c == "0":
            perms.add(name[:i] + "o" + name[i + 1:] + tld)
        elif c == "l":
            perms.add(name[:i] + "1" + name[i + 1:] + tld)
            perms.add(name[:i] + "i" + name[i + 1:] + tld)
        elif c == "i":
            perms.add(name[:i] + "1" + name[i + 1:] + tld)
            perms.add(name[:i] + "l" + name[i + 1:] + tld)
        elif c == "1":
            perms.add(name[:i] + "l" + name[i + 1:] + tld)
            perms.add(name[:i] + "i" + name[i + 1:] + tld)
    for i in range(1, len(name)):
        perms.add(name[:i] + "-" + name[i:] + tld)
    if "-" in name:
        perms.add(name.replace("-", "") + tld)
    for alt_tld in COMMON_TLDS:
        if alt_tld != tld:
            perms.add(name + alt_tld)
    for prefix in PHISHING_PREFIXES:
        perms.add(prefix + name + tld)
    for suffix in PHISHING_SUFFIXES:
        perms.add(name + suffix + tld)
    perms.add("www" + domain)
    perms.discard(domain)
    return {p for p in perms if p and len(p) > 2}


def _prioritise_candidates(domain: str, candidates: set[str]) -> list[str]:
    """Return up to 60 candidates, highest-risk first."""
    dot_pos = domain.rfind(".")
    name    = domain[:dot_pos]
    tld     = domain[dot_pos:]
    high, med, low = [], [], []
    for c in candidates:
        if any(c == name + alt for alt in COMMON_TLDS if alt != tld):
            high.append(c)  # TLD swap — most commonly registered by attackers
        elif any(c.startswith(p + name) or c.endswith(name + s)
                 for p in PHISHING_PREFIXES for s in PHISHING_SUFFIXES):
            med.append(c)   # phishing prefix/suffix
        else:
            low.append(c)   # char-level typos
    combined = high + med + low
    return combined[:30]


def _dns_resolves(domain: str, timeout: float = 1.0) -> bool:
    old = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout)
        socket.gethostbyname(domain)
        return True
    except (socket.gaierror, OSError):
        return False
    finally:
        socket.setdefaulttimeout(old)


def _find_active_lookalikes(candidates: list[str], max_workers: int = 50,
                             overall_timeout: float = 12.0) -> list[str]:
    active = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_dns_resolves, d): d for d in candidates}
        done, _ = concurrent.futures.wait(futures, timeout=overall_timeout)
        for fut in done:
            if fut.result():
                active.append(futures[fut])
    return sorted(active)


def _check_gsb(domain: str, api_key: str) -> bool:
    urls    = [f"http://{domain}/", f"https://{domain}/"]
    payload = json.dumps({
        "client": {"clientId": "relayshield", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes":      ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"],
            "platformTypes":    ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries":    [{"url": u} for u in urls],
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{GSB_URL}?key={api_key}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return bool(json.loads(resp.read()).get("matches"))
    except Exception as exc:
        logger.warning("GSB check failed for %s: %s", domain, exc)
        return False


def _check_ct(domain: str) -> dict:
    url = CRT_SH_URL.format(domain=urllib.parse.quote(domain))
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            certs = json.loads(resp.read())
        if not certs:
            return {"cert_count": 0, "recent": False, "latest_issued": None}
        now   = datetime.now(timezone.utc)
        dates = []
        for cert in certs:
            raw = cert.get("not_before") or cert.get("entry_timestamp", "")
            if raw:
                try:
                    dt = datetime.fromisoformat(raw.replace("Z", "+00:00").split(".")[0])
                    if not dt.tzinfo:
                        dt = dt.replace(tzinfo=timezone.utc)
                    dates.append(dt)
                except Exception:
                    pass
        if not dates:
            return {"cert_count": len(certs), "recent": False, "latest_issued": None}
        latest   = max(dates)
        days_old = (now - latest).days
        return {
            "cert_count":    len(certs),
            "recent":        days_old <= 30,
            "latest_issued": latest.strftime("%-d %b %Y"),
        }
    except Exception as exc:
        logger.warning("CT check failed for %s: %s", domain, exc)
        return {"cert_count": 0, "recent": False, "latest_issued": None}


# ---------------------------------------------------------------------------
# Endpoint: GET /v1/result/{analysis_id}
# ---------------------------------------------------------------------------
# Polls VirusTotal for the result of a previously submitted scan-url or scan-file.
# Returns verdict once completed, or {"status":"pending"} if still processing.

def handle_result(analysis_id: str) -> dict:
    if not analysis_id:
        return _err("analysis_id is required")
    api_key = _vt_api_key()
    req = urllib.request.Request(
        f"{VT_BASE_URL}/analyses/{analysis_id}",
        headers={"x-apikey": api_key},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data  = json.loads(resp.read())
            attrs = data.get("data", {}).get("attributes", {})
            status = attrs.get("status")
            if status != "completed":
                return _ok({"status": "pending", "analysis_id": analysis_id})
            stats = attrs.get("stats", {})
            return _vt_response(analysis_id, analysis_id, stats)
    except Exception as exc:
        logger.error("VT result poll failed for %s: %s", analysis_id, exc)
        return _err("could not retrieve analysis result", 502)


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/payg/oauth-watchlist  (also callable from subscription path)
# ---------------------------------------------------------------------------
# Request:  { "email": "user@example.com" }
# Response: { "email": "...", "matched_count": N, "matched_apps": [...],
#             "recommendation": "...", "checked_at": "..." }
#
# Checks HIBP breaches for the email and cross-references against the
# OAuth watchlist. Matched apps may have issued tokens granting access
# to Google Workspace / M365 without touching the user's password.

def handle_oauth_watchlist(params: dict) -> dict:
    email = (params.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _err("email is required and must be a valid address")

    api_key = _hibp_api_key()
    url     = f"{HIBP_BASE_URL}{urllib.parse.quote(email)}?truncateResponse=false"
    req     = urllib.request.Request(
        url,
        headers={"hibp-api-key": api_key, "user-agent": "RelayShield-API"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            breaches = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            breaches = []
        elif exc.code == 429:
            return _err("HIBP rate limit reached — retry in a few seconds", 429)
        else:
            logger.error("HIBP HTTP %d for oauth-watchlist %s", exc.code, email)
            return _err(f"HIBP returned HTTP {exc.code}", 502)
    except Exception as exc:
        logger.exception("oauth-watchlist HIBP call failed for %s: %s", email, exc)
        return _err("oauth watchlist check failed — upstream error", 502)

    matched = []
    for b in breaches:
        name  = (b.get("Name")   or "").lower()
        domain = (b.get("Domain") or "").lower()
        title  = (b.get("Title")  or "").lower()
        for app in OAUTH_WATCHLIST:
            if app in name or app in domain or app in title:
                app_name = b.get("Name", "")
                matched.append({
                    "app":           app_name,
                    "breach_date":   b.get("BreachDate"),
                    "data_classes":  b.get("DataClasses", []),
                    "revoke_url":    OAUTH_REVOCATION_URLS.get(
                                         app_name, "https://myaccount.google.com/permissions"
                                     ),
                })
                break

    logger.info("oauth-watchlist — email=%s matched=%d total_breaches=%d",
                email, len(matched), len(breaches))
    return _ok({
        "email":         email,
        "matched_count": len(matched),
        "matched_apps":  matched,
        "recommendation": (
            "Revoke OAuth access for matched apps immediately using the revoke_url for each. "
            "Also audit all connected apps at myaccount.google.com/permissions and myapps.microsoft.com."
            if matched else
            "No breached OAuth-capable apps detected for this email."
        ),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Endpoint: POST /v1/scan-wallet  (subscription) / POST /v1/payg/scan-wallet (PAYG)
# ---------------------------------------------------------------------------
# Request:  { "address": "0x..." }
# Response: { "address": "...", "chain_id": "1", "risk_level": "LOW|MEDIUM|HIGH",
#             "risk_flags": [...], "raw": {...} }

def handle_scan_wallet(params: dict) -> dict:
    address = (params.get("address") or "").strip()
    if not address:
        return _err("address is required")
    if not re.match(r"^0x[0-9a-fA-F]{40}$", address):
        return _err("address must be a valid EVM address (0x + 40 hex chars)")

    chain_id = (params.get("chain_id") or "1").strip()

    try:
        url = f"{GOPLUS_BASE_URL}/{address}?chain_id={chain_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data     = json.loads(resp.read())
            raw      = data.get("result", {}).get(address.lower(), {})
    except Exception as exc:
        logger.error("GoPlus scan failed for %s: %s", address, exc)
        return _err("wallet scan failed — upstream error", 502)

    risk_flags = [k for k, v in raw.items() if v == "1"]
    risk_level = "HIGH" if len(risk_flags) >= 2 else "MEDIUM" if risk_flags else "LOW"

    logger.info("scan-wallet address=%s chain=%s risk=%s flags=%d", address, chain_id, risk_level, len(risk_flags))
    return _ok({
        "address":    address.lower(),
        "chain_id":   chain_id,
        "risk_level": risk_level,
        "risk_flags": risk_flags,
        "raw":        raw,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/token-security  (subscription) / POST /v1/payg/token-security (PAYG)
# ---------------------------------------------------------------------------
# Request:  { "contract_address": "0x...", "chain_id": "1" }
# Response: { "contract_address": "...", "chain_id": "...", "risk_level": "LOW|MEDIUM|HIGH",
#             "critical_flags": [...], "warning_flags": [...], "raw": {...} }
#
# Supports any GoPlus chain: 1=ETH, 56=BSC, 137=Polygon, 8453=Base, etc.

def handle_token_security(params: dict) -> dict:
    contract = (params.get("contract_address") or "").strip().lower()
    if not contract:
        return _err("contract_address is required")
    if not re.match(r"^0x[0-9a-fA-F]{40}$", contract):
        return _err("contract_address must be a valid EVM address (0x + 40 hex chars)")

    chain_id = str(params.get("chain_id") or "1").strip()

    try:
        url = GOPLUS_TOKEN_URL.format(chain_id=chain_id) + f"?contract_addresses={contract}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        raw = (data.get("result") or {}).get(contract, {})
    except Exception as exc:
        logger.error("GoPlus token security failed contract=%s: %s", contract, exc)
        return _err("token security check failed — upstream error", 502)

    _CRITICAL = {
        "is_honeypot":     "honeypot",
        "is_airdrop_scam": "airdrop scam",
        "fake_token":      "fake token",
    }
    _WARNINGS = {
        "transfer_pausable":       "transfers can be paused",
        "hidden_owner":            "hidden owner",
        "can_take_back_ownership": "owner can reclaim contract",
        "is_mintable":             "mintable supply",
        "external_call":           "external call risk",
    }

    critical_flags = [label for k, label in _CRITICAL.items() if str(raw.get(k, "0")) == "1"]
    warning_flags  = [label for k, label in _WARNINGS.items() if str(raw.get(k, "0")) == "1"]

    # Sell tax — critical if >=50%, warning if >=10%
    try:
        sell_tax = float(raw.get("sell_tax", 0))
        if sell_tax >= 0.5:
            critical_flags.append(f"sell tax {sell_tax*100:.0f}%")
        elif sell_tax >= 0.1:
            warning_flags.append(f"sell tax {sell_tax*100:.0f}%")
    except (TypeError, ValueError):
        pass

    risk_level = "HIGH" if critical_flags else "MEDIUM" if warning_flags else "LOW"

    logger.info("token-security contract=%s chain=%s risk=%s", contract, chain_id, risk_level)
    return _ok({
        "contract_address": contract,
        "chain_id":         chain_id,
        "risk_level":       risk_level,
        "critical_flags":   critical_flags,
        "warning_flags":    warning_flags,
        "token_name":       raw.get("token_name", ""),
        "token_symbol":     raw.get("token_symbol", ""),
        "holder_count":     raw.get("holder_count"),
        "raw":              raw,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/nft-security  (subscription) / POST /v1/payg/nft-security (PAYG)
# ---------------------------------------------------------------------------
# Request:  { "contract_address": "0x...", "chain_id": "1" }
# Response: { "contract_address": "...", "risk_level": "LOW|MEDIUM|HIGH",
#             "risk_flags": [...], "raw": {...} }

def handle_nft_security(params: dict) -> dict:
    contract = (params.get("contract_address") or "").strip().lower()
    if not contract:
        return _err("contract_address is required")
    if not re.match(r"^0x[0-9a-fA-F]{40}$", contract):
        return _err("contract_address must be a valid EVM address (0x + 40 hex chars)")

    chain_id = str(params.get("chain_id") or "1").strip()

    try:
        url = f"{GOPLUS_NFT_URL}?chain_id={chain_id}&contract_addresses={contract}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        raw = (data.get("result") or {}).get(contract, {})
    except Exception as exc:
        logger.error("GoPlus NFT security failed contract=%s: %s", contract, exc)
        return _err("NFT security check failed — upstream error", 502)

    _NFT_FLAGS = {
        "malicious_contract": "malicious contract",
        "privileged_burn":    "owner can burn tokens",
        "can_freeze_transfer": "transfers can be frozen",
        "transfer_without_approval": "transfer without approval",
        "fake_token":         "fake/counterfeit collection",
    }
    risk_flags = [label for k, label in _NFT_FLAGS.items() if str(raw.get(k, "0")) == "1"]
    risk_level = "HIGH" if len(risk_flags) >= 2 else "MEDIUM" if risk_flags else "LOW"

    logger.info("nft-security contract=%s chain=%s risk=%s", contract, chain_id, risk_level)
    return _ok({
        "contract_address": contract,
        "chain_id":         chain_id,
        "risk_level":       risk_level,
        "risk_flags":       risk_flags,
        "nft_name":         raw.get("nft_name", ""),
        "nft_symbol":       raw.get("nft_symbol", ""),
        "raw":              raw,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/metered/crypto-intel  (Stripe metered — $0.30/call)
# ---------------------------------------------------------------------------
# Composite asset-surface intelligence: address risk + optional token risk,
# synthesised into a single risk object with cross-surface correlation advisories.
#
# Request:  { "address": "0x...",            # required — wallet or EOA
#             "token_address": "0x...",       # optional — token/contract to check
#             "chain_id": "1" }              # optional — default ETH mainnet
#
# Response: { "address": "...", "chain_id": "...",
#             "composite_risk": "LOW|MEDIUM|HIGH|CRITICAL",
#             "address_flags": [...], "token_risk": {...},
#             "correlation_advisories": [...] }

_ADDR_CRITICAL = {"phishing_activities", "blacklist_doubt", "honeypot_related_address",
                  "cybercrime", "money_laundering", "sanctioned"}
_ADDR_WARNING  = {"darkweb_transactions", "fake_kyc", "gas_abuse"}

def handle_crypto_intel(params: dict) -> dict:
    address = (params.get("address") or "").strip()
    if not address:
        return _err("address is required")
    if not re.match(r"^0x[0-9a-fA-F]{40}$", address):
        return _err("address must be a valid EVM address (0x + 40 hex chars)")

    chain_id      = str(params.get("chain_id") or "1").strip()
    token_address = (params.get("token_address") or "").strip().lower()

    # --- Address security (GoPlus address_security) ---
    address_flags    = []
    address_critical = False
    try:
        url = f"{GOPLUS_BASE_URL}/{address}?chain_id={chain_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            addr_raw = json.loads(resp.read()).get("result", {}).get(address.lower(), {})
        for k, v in addr_raw.items():
            if v == "1":
                address_flags.append(k)
                if k in _ADDR_CRITICAL:
                    address_critical = True
    except Exception as exc:
        logger.error("crypto-intel address_security failed address=%s: %s", address, exc)
        addr_raw = {}

    # --- Token security (GoPlus token_security) — only if token_address supplied ---
    token_result = None
    token_critical = False
    token_high     = False
    if token_address and re.match(r"^0x[0-9a-fA-F]{40}$", token_address):
        try:
            url = GOPLUS_TOKEN_URL.format(chain_id=chain_id) + f"?contract_addresses={token_address}"
            req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                tok_raw = json.loads(resp.read()).get("result", {}).get(token_address, {})

            tok_critical = []
            tok_warnings = []
            for k, label in [("is_honeypot", "honeypot"), ("is_airdrop_scam", "airdrop scam"),
                              ("fake_token", "fake token")]:
                if str(tok_raw.get(k, "0")) == "1":
                    tok_critical.append(label)
            for k, label in [("transfer_pausable", "transfers pausable"),
                              ("is_mintable", "mintable supply"),
                              ("hidden_owner", "hidden owner")]:
                if str(tok_raw.get(k, "0")) == "1":
                    tok_warnings.append(label)
            try:
                sell_tax = float(tok_raw.get("sell_tax", 0))
                if sell_tax >= 0.5:
                    tok_critical.append(f"sell tax {sell_tax*100:.0f}%")
                elif sell_tax >= 0.1:
                    tok_warnings.append(f"sell tax {sell_tax*100:.0f}%")
            except (TypeError, ValueError):
                pass

            token_critical = bool(tok_critical)
            token_high     = bool(tok_warnings)
            token_result   = {
                "contract_address": token_address,
                "token_name":       tok_raw.get("token_name", ""),
                "token_symbol":     tok_raw.get("token_symbol", ""),
                "critical_flags":   tok_critical,
                "warning_flags":    tok_warnings,
            }
        except Exception as exc:
            logger.error("crypto-intel token_security failed contract=%s: %s", token_address, exc)

    # --- Composite risk ---
    if address_critical or token_critical:
        composite_risk = "CRITICAL"
    elif address_flags or token_high:
        composite_risk = "HIGH"
    elif set(address_flags) & _ADDR_WARNING:
        composite_risk = "MEDIUM"
    else:
        composite_risk = "LOW"

    # --- Cross-surface correlation advisories ---
    advisories = []
    if address_critical:
        advisories.append(
            "CRITICAL: This address appears in phishing/sanctions/cybercrime databases. "
            "If the associated account owner has an active SIM swap, call /v1/metered/sim-swap — "
            "this combination indicates an in-progress coordinated crypto theft chain."
        )
    if token_critical:
        advisories.append(
            "CRITICAL: Token contract shows honeypot or scam indicators. "
            "Cross-reference with /v1/metered/infostealer if the wallet owner's email is known — "
            "device credential theft is a common precursor to honeypot-targeted asset drain."
        )
    if address_flags and not advisories:
        advisories.append(
            "ELEVATED: Address has risk flags. Recommend also checking "
            "/v1/metered/breach on the account email and /v1/metered/sim-swap on the associated "
            "phone number to detect coordinated identity + asset attack chains."
        )
    if not advisories:
        advisories.append(
            "No risk signals detected on this address. For complete protection, monitor "
            "the associated email via /v1/metered/breach and phone via /v1/metered/sim-swap."
        )

    logger.info("crypto-intel address=%s chain=%s risk=%s addr_flags=%d token=%s",
                address, chain_id, composite_risk, len(address_flags),
                token_result["token_symbol"] if token_result else "none")

    result = {
        "address":                address.lower(),
        "chain_id":               chain_id,
        "composite_risk":         composite_risk,
        "address_flags":          address_flags,
        "correlation_advisories": advisories,
    }
    if token_result:
        result["token_risk"] = token_result
    return _ok(result)


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/wallet-risk  (subscription) / POST /v1/payg/wallet-risk (PAYG)
# ---------------------------------------------------------------------------
# Multi-chain wallet risk: EVM and Solana via GoPlus, TON via TONAPI v2,
# Bitcoin via Blockstream heuristics. Chain is auto-detected from address format.
#
# Request:  { "address": "0x...|SolanaAddr|EQTonAddr" }
# Response: { "address": "...", "chain": "evm|solana|ton|bitcoin",
#             "risk_level": "LOW|MEDIUM|HIGH", "risk_flags": [...],
#             "metadata": {...} }

_GOPLUS_CHAIN_IDS = {"evm": 1, "solana": 101}

def _detect_chain_api(address: str) -> str:
    if re.match(r"^0x[0-9a-fA-F]{40}$", address):
        return "evm"
    if re.match(r"^[EUeu][Qq][A-Za-z0-9_\-]{46}$", address):
        return "ton"
    if re.match(r"^(bc1|[13])[a-zA-HJ-NP-Z0-9]{6,87}$", address):
        return "bitcoin"
    if re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", address):
        return "solana"
    return "unknown"


def handle_wallet_risk(params: dict) -> dict:
    address = (params.get("address") or "").strip()
    if not address:
        return _err("address is required")

    chain = _detect_chain_api(address)
    if chain == "unknown":
        return _err("unrecognised address format — supported: EVM (0x), Solana, TON (EQ.../UQ...), Bitcoin")

    risk_flags = []
    metadata   = {}

    if chain == "bitcoin":
        try:
            btc_url = f"https://blockstream.info/api/address/{address}"
            req = urllib.request.Request(btc_url, headers={"User-Agent": "RelayShield/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                btc_data = json.loads(resp.read())
            chain_stats  = btc_data.get("chain_stats", {})
            mempool_stats = btc_data.get("mempool_stats", {})
            tx_count     = chain_stats.get("tx_count", 0)
            funded_sum   = chain_stats.get("funded_txo_sum", 0)
            spent_sum    = chain_stats.get("spent_txo_sum", 0)
            balance_sats = funded_sum - spent_sum
            mempool_txs  = mempool_stats.get("tx_count", 0)

            if tx_count == 0:
                risk_flags.append("never_used")
            if tx_count > 500:
                risk_flags.append("high_tx_volume")
            if balance_sats == 0 and tx_count > 10:
                risk_flags.append("zero_balance_high_activity")
            if 0 < balance_sats < 1000:
                risk_flags.append("dust_balance")
            if mempool_txs > 0:
                risk_flags.append("unconfirmed_transactions")

            metadata["tx_count"]      = tx_count
            metadata["balance_sats"]  = balance_sats
            metadata["balance_btc"]   = round(balance_sats / 100_000_000, 8)
            metadata["mempool_txs"]   = mempool_txs
            metadata["explorer"]      = f"https://mempool.space/address/{address}"
        except Exception as exc:
            logger.error("Blockstream wallet-risk failed address=%s: %s", address, exc)
            metadata["blockstream_error"] = "upstream unavailable"

        risk_level = "HIGH" if "zero_balance_high_activity" in risk_flags or "high_tx_volume" in risk_flags \
            else "MEDIUM" if risk_flags else "LOW"
        logger.info("wallet-risk address=%s chain=bitcoin risk=%s flags=%d", address, risk_level, len(risk_flags))
        return _ok({
            "address":    address,
            "chain":      "bitcoin",
            "risk_level": risk_level,
            "risk_flags": risk_flags,
            "metadata":   metadata,
        })

    if chain in ("evm", "solana"):
        goplus_chain_id = _GOPLUS_CHAIN_IDS[chain]
        try:
            url = f"{GOPLUS_BASE_URL}/{address}?chain_id={goplus_chain_id}"
            req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            raw = data.get("result", {})
            _MALICIOUS = {
                "phishing_activities":  "linked to phishing",
                "blacklist_doubt":      "security blacklisted",
                "darkweb_transactions": "dark web activity",
                "stealing_attack":      "stealing attacks",
                "cybercrime":           "cybercrime",
            }
            risk_flags = [label for k, label in _MALICIOUS.items() if raw.get(k) == "1"]
        except Exception as exc:
            logger.error("GoPlus wallet-risk failed address=%s: %s", address, exc)
            metadata["goplus_error"] = "upstream unavailable"

    elif chain == "ton":
        try:
            ton_url = TONAPI_ACCOUNTS_URL.format(
                address=urllib.parse.quote(address, safe="-_=")
            )
            req = urllib.request.Request(ton_url, headers={"User-Agent": "RelayShield/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                ton_data = json.loads(resp.read())
            if ton_data.get("is_scam"):
                risk_flags.append("flagged as scam in TON community database")
            metadata["contract_type"]  = ton_data.get("interfaces", [])
            metadata["account_status"] = ton_data.get("status", "")
        except Exception as exc:
            logger.error("TONAPI wallet-risk failed address=%s: %s", address, exc)
            metadata["tonapi_error"] = "upstream unavailable"

    risk_level = "HIGH" if len(risk_flags) >= 2 else "MEDIUM" if risk_flags else "LOW"
    logger.info("wallet-risk address=%s chain=%s risk=%s flags=%d", address, chain, risk_level, len(risk_flags))
    return _ok({
        "address":    address.lower() if chain == "evm" else address,
        "chain":      chain,
        "risk_level": risk_level,
        "risk_flags": risk_flags,
        "metadata":   metadata,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/payg/wallet-screen-batch  (PAYG only — $0.50 for up to 10)
# ---------------------------------------------------------------------------
# Screens up to 10 addresses in parallel. Mixed chains supported.
#
# Request:  { "addresses": ["0x...", "SolAddr", "EQTonAddr"] }
# Response: { "results": [ { "address": "...", "chain": "...",
#                             "risk_level": "...", "risk_flags": [...] }, ... ] }

def handle_wallet_screen_batch(params: dict) -> dict:
    addresses = params.get("addresses") or []
    if not isinstance(addresses, list) or not addresses:
        return _err("addresses must be a non-empty list")
    if len(addresses) > 10:
        return _err("maximum 10 addresses per batch request")
    addresses = [str(a).strip() for a in addresses if str(a).strip()]

    def _screen_one(addr: str) -> dict:
        result = handle_wallet_risk({"address": addr})
        body   = json.loads(result.get("body", "{}"))
        data   = body.get("data", {})
        return {
            "address":    data.get("address", addr),
            "chain":      data.get("chain", "unknown"),
            "risk_level": data.get("risk_level", "UNKNOWN"),
            "risk_flags": data.get("risk_flags", []),
            "error":      body.get("error") if not body.get("ok") else None,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(_screen_one, addresses))

    high_count = sum(1 for r in results if r["risk_level"] == "HIGH")
    logger.info("wallet-screen-batch count=%d high_risk=%d", len(addresses), high_count)
    return _ok({
        "screened":   len(results),
        "high_risk":  high_count,
        "results":    results,
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/payg/infostealer  (PAYG only — $0.15)
# ---------------------------------------------------------------------------
# Checks an email address against Hudson Rock Cavalier (free, no API key).
# Returns whether the email appears in infostealer logs, and summary details
# about compromised machines.
#
# Request:  { "email": "user@example.com" }
# Response: { "email": "...", "found": true/false, "stealer_count": N,
#             "stealers": [ { "date_compromised": "...", "computer_name": "...",
#                             "operating_system": "...", "malware_path": "...",
#                             "total_corporate_services": N,
#                             "total_user_services": N } ] }

CAVALIER_URL = "https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-login"


def handle_infostealer(params: dict) -> dict:
    email = (params.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _err("email is required and must be a valid address")

    encoded_email = urllib.parse.quote(email, safe="")
    url = f"{CAVALIER_URL}?email={encoded_email}"
    req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            # Hudson Rock returns 404 when email is not found
            return _ok({"email": email, "found": False, "stealer_count": 0, "stealers": []})
        logger.error("Cavalier API HTTP error: %s", exc)
        return _err(f"infostealer check failed: HTTP {exc.code}", 502)
    except Exception as exc:
        logger.error("Cavalier API error: %s", exc)
        return _err("infostealer check failed: upstream error", 502)

    stealers_raw = raw.get("stealers", [])
    stealers = []
    for s in stealers_raw:
        stealers.append({
            "date_compromised":         s.get("date_compromised"),
            "computer_name":            s.get("computer_name"),
            "operating_system":         s.get("operating_system"),
            "malware_path":             s.get("malware_path"),
            "total_corporate_services": s.get("total_corporate_services", 0),
            "total_user_services":      s.get("total_user_services", 0),
        })

    found = len(stealers) > 0
    logger.info("infostealer email=%s found=%s count=%d", email, found, len(stealers))
    return _ok({
        "email":         email,
        "found":         found,
        "stealer_count": len(stealers),
        "stealers":      stealers,
    })


# ---------------------------------------------------------------------------
# Threat Intelligence API — /v1/intel/telegram
# ---------------------------------------------------------------------------
# Subscription endpoint (API key + intel_access flag required).
# Queries relayshield_intel_iocs — IOCs extracted from INTEL-2 Telegram channel
# pipeline — 24–72 hours ahead of HIBP and public breach databases.
#
# Request: POST /v1/intel/telegram
#   { "email": "...", "phone": "...", "domain": "...", "wallet": "..." }
#   At least one field required. Each queried independently; results merged.
#
# Response:
#   { ok: true, matched: bool, hit_count: int, ioc_types: [...],
#     earliest_seen: ISO, latest_seen: ISO,
#     hits: [{ ioc_value, ioc_type, channel, category, seen_ts }] }
# ---------------------------------------------------------------------------

def handle_intel_telegram(params: dict, api_key_record: dict | None = None) -> dict:
    # Verify caller has intel_access — TI API subscribers get this flag provisioned
    if api_key_record and not api_key_record.get("intel_access"):
        return {
            "statusCode": 403,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "ok":    False,
                "error": "Threat Intelligence API access required. Upgrade at relayshield.net/developers.",
            }),
        }

    # Collect IOC values to query
    targets: list[tuple[str, str]] = []
    if params.get("email"):
        targets.append((params["email"].strip().lower(), "email"))
    if params.get("phone"):
        phone = re.sub(r"[^\d+]", "", params["phone"].strip())
        if phone:
            targets.append((phone, "phone"))
    if params.get("domain"):
        targets.append((params["domain"].strip().lower(), "domain"))
    if params.get("wallet"):
        targets.append((params["wallet"].strip().lower(), "wallet"))

    if not targets:
        return _err("at least one of email, phone, domain, or wallet is required")

    table = dynamodb.Table(INTEL_IOCS_TABLE)
    all_hits: list[dict] = []

    for ioc_value, _ in targets:
        try:
            resp = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key("ioc_value").eq(ioc_value),
                ScanIndexForward=False,  # newest first
                Limit=50,
            )
            all_hits.extend(resp.get("Items", []))
        except Exception as exc:
            logger.error("intel_iocs query failed ioc=%s: %s", ioc_value[:20], exc)

    if not all_hits:
        return _ok({
            "matched":       False,
            "hit_count":     0,
            "ioc_types":     [],
            "earliest_seen": None,
            "latest_seen":   None,
            "hits":          [],
        })

    timestamps   = [h.get("seen_ts", "") for h in all_hits if h.get("seen_ts")]
    ioc_types    = sorted({h.get("ioc_type", "") for h in all_hits})
    safe_hits    = [
        {
            "ioc_value": h.get("ioc_value"),
            "ioc_type":  h.get("ioc_type"),
            "channel":   h.get("channel"),
            "category":  h.get("category"),
            "seen_ts":   h.get("seen_ts"),
        }
        for h in all_hits
    ]

    logger.info("intel_telegram queried=%d hits=%d", len(targets), len(all_hits))
    return _ok({
        "matched":       True,
        "hit_count":     len(all_hits),
        "ioc_types":     ioc_types,
        "earliest_seen": min(timestamps) if timestamps else None,
        "latest_seen":   max(timestamps) if timestamps else None,
        "hits":          safe_hits,
    })


# ---------------------------------------------------------------------------
# x402 Bazaar discovery extensions — per-endpoint metadata for Agentic.Market
# ---------------------------------------------------------------------------
# Format follows the x402 BodyDiscoveryExtension schema (POST endpoints).
# These are injected into the `extensions` field of each payment-requirements
# `accepts` entry so the CDP Facilitator can catalog them on settlement.

def _bazaar_body_ext(input_example: dict, input_schema: dict, output_example: dict) -> dict:
    """Build a Bazaar BodyDiscoveryExtension dict for a POST endpoint."""
    return {
        "bazaar": {
            "info": {
                "input": {
                    "type":     "http",
                    "bodyType": "json",
                    "body":     input_example,
                },
                "output": {
                    "type":    "json",
                    "example": output_example,
                },
            },
            "schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type":    "object",
                "properties": {
                    "input": {
                        "type": "object",
                        "properties": {
                            "type":     {"type": "string", "const": "http"},
                            "method":   {"type": "string", "enum": ["POST", "PUT", "PATCH"]},
                            "bodyType": {"type": "string", "enum": ["json", "form-data", "text"]},
                            "body":     input_schema,
                        },
                        "required":             ["type", "method", "bodyType", "body"],
                        "additionalProperties": False,
                    },
                    "output": {
                        "type": "object",
                        "properties": {
                            "type":    {"type": "string"},
                            "example": {"type": "object"},
                        },
                        "required": ["type"],
                    },
                },
                "required": ["input"],
            },
        }
    }


BAZAAR_EXTENSIONS: dict[str, dict] = {
    "/v1/payg/breach": _bazaar_body_ext(
        input_example={"email": "user@example.com"},
        input_schema={
            "type": "object",
            "properties": {"email": {"type": "string", "description": "Email address to check"}},
            "required": ["email"],
        },
        output_example={
            "ok": True,
            "data": {
                "email": "user@example.com",
                "breach_count": 3,
                "breaches": [
                    {"name": "ExampleBreach", "domain": "example.com",
                     "breach_date": "2023-06-01",
                     "data_classes": ["Passwords", "Email addresses"],
                     "is_verified": True},
                ],
            },
        },
    ),
    "/v1/payg/sim-swap": _bazaar_body_ext(
        input_example={"phone": "+14155551234"},
        input_schema={
            "type": "object",
            "properties": {"phone": {"type": "string", "description": "Phone number in E.164 format"}},
            "required": ["phone"],
        },
        output_example={
            "ok": True,
            "data": {
                "phone": "+14155551234",
                "swapped": True,
                "swap_timestamp": "2026-05-18T14:23:00Z",
                "carrier": "T-Mobile",
                "checked_at": "2026-05-19T10:00:00+00:00",
            },
        },
    ),
    "/v1/payg/domain": _bazaar_body_ext(
        input_example={"domain": "acme.com"},
        input_schema={
            "type": "object",
            "properties": {"domain": {"type": "string", "description": "Root domain to scan for lookalikes"}},
            "required": ["domain"],
        },
        output_example={
            "ok": True,
            "data": {
                "domain": "acme.com",
                "lookalikes_found": 2,
                "lookalikes": [
                    {"domain": "acrne.com"},
                    {"domain": "acme-login.com"},
                ],
                "candidates_checked": 30,
                "checked_at": "2026-05-19T10:00:00+00:00",
            },
        },
    ),
    "/v1/payg/oauth-watchlist": _bazaar_body_ext(
        input_example={"email": "user@example.com"},
        input_schema={
            "type": "object",
            "properties": {"email": {"type": "string", "description": "Email address to check for OAuth exposure"}},
            "required": ["email"],
        },
        output_example={
            "ok": True,
            "data": {
                "email": "user@example.com",
                "matched_count": 1,
                "matched_apps": [
                    {"app": "GitHub", "breach_date": "2023-01-15",
                     "data_classes": ["Usernames", "Email addresses"],
                     "revoke_url": "https://github.com/settings/applications"},
                ],
                "recommendation": "Revoke OAuth access for matched apps immediately.",
                "checked_at": "2026-05-19T10:00:00+00:00",
            },
        },
    ),
    "/v1/payg/scan-wallet": _bazaar_body_ext(
        input_example={"address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "chain_id": "1"},
        input_schema={
            "type": "object",
            "properties": {
                "address":  {"type": "string", "description": "EVM wallet address (0x + 40 hex chars)"},
                "chain_id": {"type": "string", "description": "EVM chain ID: 1=ETH, 8453=Base, 137=Polygon"},
            },
            "required": ["address"],
        },
        output_example={
            "ok": True,
            "data": {
                "address": "0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
                "chain_id": "1",
                "risk_level": "LOW",
                "risk_flags": [],
                "raw": {},
            },
        },
    ),
    "/v1/payg/scan-url": _bazaar_body_ext(
        input_example={"url": "https://suspicious-site.example.com"},
        input_schema={
            "type": "object",
            "properties": {"url": {"type": "string", "description": "URL to scan (must start with http:// or https://)"}},
            "required": ["url"],
        },
        output_example={
            "ok": True,
            "data": {
                "status":        "pending",
                "target":        "https://suspicious-site.example.com",
                "analysis_id":   "u-abc123def456",
                "poll_endpoint": "/v1/result/u-abc123def456",
                "note":          "Poll /v1/result/{analysis_id} every 5s until status is completed",
            },
        },
    ),
    "/v1/payg/scan-file": _bazaar_body_ext(
        input_example={"file_url": "https://cdn.example.com/invoice.pdf", "filename": "invoice.pdf"},
        input_schema={
            "type": "object",
            "properties": {
                "file_url": {"type": "string", "description": "Publicly accessible download URL"},
                "filename": {"type": "string", "description": "Optional filename hint for AV engines"},
            },
            "required": ["file_url"],
        },
        output_example={
            "ok": True,
            "data": {
                "status":        "pending",
                "target":        "https://cdn.example.com/invoice.pdf",
                "filename":      "invoice.pdf",
                "analysis_id":   "f-abc123def456",
                "poll_endpoint": "/v1/result/f-abc123def456",
                "note":          "Poll /v1/result/{analysis_id} every 5s until status is completed",
            },
        },
    ),
    "/v1/payg/wallet-risk": _bazaar_body_ext(
        input_example={"address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"},
        input_schema={
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Wallet address — EVM (0x), Solana (base58), TON (EQ.../UQ...), or Bitcoin",
                },
            },
            "required": ["address"],
        },
        output_example={
            "ok": True,
            "data": {
                "address":    "0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
                "chain":      "evm",
                "risk_level": "LOW",
                "risk_flags": [],
                "metadata":   {},
            },
        },
    ),
    "/v1/payg/token-security": _bazaar_body_ext(
        input_example={"contract_address": "0x6982508145454ce325ddbe47a25d4ec3d2311933", "chain_id": "1"},
        input_schema={
            "type": "object",
            "properties": {
                "contract_address": {"type": "string", "description": "EVM token contract address"},
                "chain_id":         {"type": "string", "description": "EVM chain ID (default: 1 for Ethereum)"},
            },
            "required": ["contract_address"],
        },
        output_example={
            "ok": True,
            "data": {
                "contract_address": "0x6982508145454ce325ddbe47a25d4ec3d2311933",
                "chain_id":         "1",
                "risk_level":       "HIGH",
                "critical_flags":   ["honeypot"],
                "warning_flags":    ["mintable supply"],
                "token_name":       "Example Token",
                "token_symbol":     "EXT",
                "holder_count":     "12345",
                "raw":              {},
            },
        },
    ),
    "/v1/payg/nft-security": _bazaar_body_ext(
        input_example={"contract_address": "0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d", "chain_id": "1"},
        input_schema={
            "type": "object",
            "properties": {
                "contract_address": {"type": "string", "description": "NFT contract address"},
                "chain_id":         {"type": "string", "description": "EVM chain ID (default: 1 for Ethereum)"},
            },
            "required": ["contract_address"],
        },
        output_example={
            "ok": True,
            "data": {
                "contract_address": "0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d",
                "chain_id":         "1",
                "risk_level":       "LOW",
                "risk_flags":       [],
                "nft_name":         "Bored Ape Yacht Club",
                "nft_symbol":       "BAYC",
                "raw":              {},
            },
        },
    ),
    "/v1/payg/wallet-screen-batch": _bazaar_body_ext(
        input_example={"addresses": ["0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"]},
        input_schema={
            "type": "object",
            "properties": {
                "addresses": {
                    "type":        "array",
                    "items":       {"type": "string"},
                    "maxItems":    10,
                    "description": "Up to 10 wallet addresses (any chain: EVM, Solana, TON, Bitcoin)",
                },
            },
            "required": ["addresses"],
        },
        output_example={
            "ok": True,
            "data": {
                "screened":  2,
                "high_risk": 0,
                "results": [
                    {"address": "0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
                     "chain": "evm", "risk_level": "LOW", "risk_flags": [], "error": None},
                    {"address": "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",
                     "chain": "solana", "risk_level": "LOW", "risk_flags": [], "error": None},
                ],
            },
        },
    ),
    "/v1/payg/infostealer": _bazaar_body_ext(
        input_example={"email": "user@example.com"},
        input_schema={
            "type": "object",
            "properties": {"email": {"type": "string", "description": "Email address to check for infostealer compromise"}},
            "required": ["email"],
        },
        output_example={
            "ok": True,
            "data": {
                "email":         "user@example.com",
                "found":         False,
                "stealer_count": 0,
                "stealers":      [],
            },
        },
    ),
}


# ---------------------------------------------------------------------------
# x402 PAYG — payment requirements, verification, 402 response
# ---------------------------------------------------------------------------

def _build_payment_requirements(path: str, price_units: int) -> dict:
    api_base    = "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod"
    resource    = f"{api_base}{path}"
    description = f"RelayShield {path.split('/')[-1].replace('-', ' ')} check"
    bazaar_ext  = BAZAAR_EXTENSIONS.get(path)

    # Base (EVM) entry — always included
    base_entry: dict = {
        "scheme":            "exact",
        "network":           BASE_CHAIN_ID,
        "maxAmountRequired": str(price_units),
        "resource":          resource,
        "description":       description,
        "mimeType":          "application/json",
        "payTo":             X402_PAYTO_ADDRESS,
        "maxTimeoutSeconds": 300,
        "asset":             USDC_BASE_ADDRESS,
        "extra":             {"name": "USD Coin", "version": "2"},
    }
    if bazaar_ext:
        base_entry["extensions"] = bazaar_ext

    accepts = [base_entry]

    # Solana (SVM) entry — added when RELAYSHIELD_SOL_WALLET is configured.
    # CDP Facilitator sponsors gas; client signs a partial SPL TransferChecked
    # transaction and sends it base64-encoded in X-PAYMENT.
    if SOL_PAYTO_ADDRESS:
        sol_entry: dict = {
            "scheme":            "exact",
            "network":           SOL_CHAIN_ID,
            "maxAmountRequired": str(price_units),
            "resource":          resource,
            "description":       description,
            "mimeType":          "application/json",
            "payTo":             SOL_PAYTO_ADDRESS,
            "maxTimeoutSeconds": 60,          # Solana blockhash TTL ~60–90s
            "asset":             USDC_SOL_ADDRESS,
            "extra": {
                "feePayer": SOL_FEE_PAYER,    # CDP Facilitator sponsors transaction gas
            },
        }
        if bazaar_ext:
            sol_entry["extensions"] = bazaar_ext
        accepts.append(sol_entry)

    return {
        "x402Version": 1,
        "accepts":     accepts,
    }


def _x402_payment_required(path: str) -> dict:
    price_units  = PAYG_PRICE_UNITS.get(path, 250000)
    requirements = _build_payment_requirements(path, price_units)
    encoded      = base64.b64encode(json.dumps(requirements).encode()).decode()
    price_usd    = f"${price_units / 1_000_000:.2f}"
    chains       = "Base or Solana" if SOL_PAYTO_ADDRESS else "Base"
    return {
        "statusCode": 402,
        "headers": {
            "Content-Type":                  "application/json",
            "PAYMENT-REQUIRED":              encoded,
            "Access-Control-Expose-Headers": "PAYMENT-REQUIRED",
        },
        "body": json.dumps({
            "ok":             False,
            "error":          "Payment required",
            "price":          f"{price_usd} USDC ({chains})",
            "x402":           requirements,
            "subscribe_url":  "https://rapidapi.com/relayshield/relayshield-security-intelligence",
            "subscribe_note": f"Subscribe for 96%+ lower per-check cost vs {price_usd} PAYG rate.",
        }),
    }


def _detect_payment_chain(x_payment: str) -> str:
    """Detect chain by parsing the network field from the x402 payment payload.
    Both EVM and Solana payloads are base64-encoded JSON — check network field.
    Returns 'solana' or 'evm'.
    """
    try:
        decoded = base64.b64decode(x_payment + "==")
        parsed = json.loads(decoded)
        network = parsed.get("network", "")
        if network.startswith("solana"):
            return "solana"
        return "evm"
    except Exception:
        # Try raw JSON (non-base64)
        try:
            parsed = json.loads(x_payment)
            if parsed.get("network", "").startswith("solana"):
                return "solana"
        except Exception:
            pass
        return "evm"  # default to EVM on decode failure


def _verify_x402_payment(x_payment: str, path: str) -> bool:
    price_units  = PAYG_PRICE_UNITS.get(path, 0)
    requirements = _build_payment_requirements(path, price_units)

    chain = _detect_payment_chain(x_payment)
    logger.info("x402 payment detected chain=%s path=%s", chain, path)

    # Decode x_payment from base64 JSON to dict — PayAI expects decoded object
    try:
        payment_payload_dict = json.loads(base64.b64decode(x_payment + "=="))
    except Exception:
        try:
            payment_payload_dict = json.loads(x_payment)
        except Exception:
            logger.error("Failed to decode x_payment for path=%s", path)
            return False

    if chain == "solana":
        if not SOL_PAYTO_ADDRESS:
            logger.error("RELAYSHIELD_SOL_WALLET not set — cannot verify Solana x402 payment")
            return False
        sol_requirements = next(
            (a for a in requirements.get("accepts", []) if a.get("network") == SOL_CHAIN_ID),
            None,
        )
        if not sol_requirements:
            logger.error("No Solana accepts entry in requirements for path=%s", path)
            return False
        verify_payload = json.dumps({
            "x402Version":        1,
            "paymentPayload":     payment_payload_dict,
            "paymentRequirements": sol_requirements,
        }).encode("utf-8")
    else:
        if not X402_PAYTO_ADDRESS:
            logger.error("RELAYSHIELD_X402_WALLET not set — cannot verify EVM x402 payment")
            return False
        evm_requirements = next(
            (a for a in requirements.get("accepts", []) if a.get("network") == BASE_CHAIN_ID),
            requirements,
        )
        verify_payload = json.dumps({
            "x402Version":        1,
            "paymentPayload":     payment_payload_dict,
            "paymentRequirements": evm_requirements,
        }).encode("utf-8")

    # Solana → CDP Facilitator (manages the CDP fee payer key)
    # EVM    → PayAI Facilitator (auto-lists RelayShield in Bazaar)
    facilitator_base = SOL_FACILITATOR_URL if chain == "solana" else X402_FACILITATOR_URL
    verify_url = f"{facilitator_base}/verify"
    logger.info("Sending verify to %s payload_keys=%s", verify_url, list(payment_payload_dict.keys()))
    logger.info("verify_body_preview=%s", verify_payload.decode("utf-8")[:800])

    req = urllib.request.Request(
        verify_url,
        data=verify_payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            valid  = result.get("isValid", False)
            if not valid:
                logger.warning("x402 payment invalid — chain=%s reason=%s path=%s",
                               chain, result.get("invalidReason"), path)
            return valid
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = "<unreadable>"
        logger.error("x402 facilitator HTTP %d — chain=%s path=%s body=%s",
                     exc.code, chain, path, body)
        return False
    except Exception as exc:
        logger.error("x402 facilitator call failed — chain=%s path=%s error=%s", chain, path, exc)
        return False


def handle_payg_request(path: str, method: str, event: dict) -> dict:
    headers   = event.get("headers") or {}
    x_payment = headers.get("X-PAYMENT") or headers.get("x-payment", "")

    # Free poll endpoint — no payment needed
    if method == "GET" and path.startswith("/v1/payg/result/"):
        analysis_id = path[len("/v1/payg/result/"):]
        return handle_result(analysis_id)

    if method != "POST":
        return _err(f"{path} only accepts POST requests", 405)

    # Require payment proof
    if not x_payment:
        return _x402_payment_required(path)

    if not _verify_x402_payment(x_payment, path):
        return {
            "statusCode": 402,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "ok":    False,
                "error": "Invalid or expired payment proof — pay again and retry.",
            }),
        }

    payg_routes = {
        "/v1/payg/breach":                handle_breach,
        "/v1/payg/sim-swap":              handle_sim_swap,
        "/v1/payg/domain":                handle_domain,
        "/v1/payg/oauth-watchlist":       handle_oauth_watchlist,
        "/v1/payg/scan-wallet":           handle_scan_wallet,       # legacy EVM-only
        "/v1/payg/scan-url":              handle_scan_url,
        "/v1/payg/scan-file":             handle_scan_file,
        "/v1/payg/wallet-risk":           handle_wallet_risk,
        "/v1/payg/token-security":        handle_token_security,
        "/v1/payg/nft-security":          handle_nft_security,
        "/v1/payg/wallet-screen-batch":   handle_wallet_screen_batch,
        "/v1/payg/infostealer":           handle_infostealer,
    }
    handler = payg_routes.get(path)
    if not handler:
        return _err(f"unknown PAYG endpoint: {path}", 404)

    params = _body(event)
    try:
        return handler(params)
    except Exception as exc:
        logger.exception("Unhandled error in PAYG %s: %s", path, exc)
        return _err("internal server error", 500)


# ---------------------------------------------------------------------------
# Router / Lambda handler
# ---------------------------------------------------------------------------

ROUTES = {
    "/v1/breach":           handle_breach,
    "/v1/scan-url":         handle_scan_url,
    "/v1/scan-file":        handle_scan_file,
    "/v1/sim-swap":         handle_sim_swap,
    "/v1/domain":           handle_domain,
    "/v1/oauth-watchlist":  handle_oauth_watchlist,
    "/v1/scan-wallet":      handle_scan_wallet,       # legacy EVM-only
    "/v1/wallet-risk":      handle_wallet_risk,       # multi-chain EVM/Solana/TON
    "/v1/token-security":   handle_token_security,
    "/v1/nft-security":     handle_nft_security,
    "/v1/intel/telegram":   handle_intel_telegram,    # TI API — requires intel_access flag
}

PAYG_PATHS = set(PAYG_PRICE_UNITS.keys()) | {"/v1/payg/result/"}


def lambda_handler(event: dict, context) -> dict:
    path   = event.get("path", "")
    method = event.get("httpMethod", "")

    logger.info("API request — method=%s path=%s", method, path)

    # Discovery
    if method == "GET" and path in ("/", "/v1", "/v1/"):
        return _ok({
            "service":  "RelayShield B2A API",
            "version":  "1.0",
            "subscription_endpoints": list(ROUTES.keys()) + ["GET /v1/result/{analysis_id}"],
            "metered_endpoints": list(STRIPE_METER_EVENTS.keys()),
            "metered_note": "Stripe card billing — pass RS API key as X-RS-API-KEY header.",
            "payg_endpoints": list(PAYG_PRICE_UNITS.keys()) + ["GET /v1/payg/result/{analysis_id}"],
            "payg_note": "x402 payment required — USDC on Base. No API key needed.",
        })

    # Stripe metered billing routes (RS API key verified inside Lambda)
    if path.startswith("/v1/metered/"):
        return handle_metered_request(path, method, event)

    # PAYG routes (x402 payment verified inside Lambda)
    if path.startswith("/v1/payg/"):
        return handle_payg_request(path, method, event)

    # Subscription: GET /v1/result/{analysis_id}
    if method == "GET" and path.startswith("/v1/result/"):
        analysis_id = path[len("/v1/result/"):]
        return handle_result(analysis_id)

    # Subscription routes (API key enforced by API Gateway)
    handler = ROUTES.get(path)
    if not handler:
        return _err(f"unknown endpoint: {path}", 404)

    if method != "POST":
        return _err(f"{path} only accepts POST requests", 405)

    params = _body(event)
    try:
        if path == "/v1/intel/telegram":
            headers    = event.get("headers") or {}
            api_key    = (headers.get("X-API-Key") or headers.get("x-api-key") or
                          headers.get("X-RS-API-KEY") or headers.get("x-rs-api-key", ""))
            key_record = _verify_rs_api_key(api_key) if api_key else None
            return handler(params, api_key_record=key_record)
        return handler(params)
    except Exception as exc:
        logger.exception("Unhandled error in %s: %s", path, exc)
        return _err("internal server error", 500)
