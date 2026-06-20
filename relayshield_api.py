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
  POST /v1/metered/supply-chain     — Vendor/supply chain risk: breach + infostealer exposure per domain (up to 10 domains)
  POST /v1/metered/session-risk     — INTEL-5 active session hijack detection from stealer log corpus
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
  POST /v1/payg/supply-chain        — $0.10 USDC per domain — vendor breach + infostealer risk (up to 10 domains)
  POST /v1/payg/session-risk        — $0.30 USDC — INTEL-5 active session hijack / AiTM detection
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
ses             = boto3.client("ses", region_name="us-east-1")

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
    "/v1/payg/oauth-watchlist":       300000,   # $0.30 — combined HIBP watchlist + INTEL-5 stealer corpus (premium positioning vs SpyCloud)
    "/v1/payg/scan-wallet":           100000,   # legacy — EVM only
    "/v1/payg/scan-url":               50000,
    "/v1/payg/scan-file":             100000,
    # Crypto Shield intelligence endpoints
    "/v1/payg/wallet-risk":           150000,   # $0.15 — multi-chain EVM/Solana/TON
    "/v1/payg/token-security":        100000,   # $0.10 — GoPlus token risk
    "/v1/payg/nft-security":          100000,   # $0.10 — GoPlus NFT risk
    "/v1/payg/wallet-screen-batch":   500000,   # $0.50 — up to 10 addresses
    "/v1/payg/infostealer":           150000,   # $0.15 — Hudson Rock infostealer check
    "/v1/payg/supply-chain":          100000,   # $0.10 per call (up to 10 vendor domains)
    "/v1/payg/session-risk":          300000,   # $0.30 — INTEL-5 active session hijack / AiTM detection (premium)
    "/v1/payg/identity-graph":        350000,   # $0.35 — identity correlation: email → linked phones/domains from dumps
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
INTEL_CVE_TABLE  = "relayshield_intel_cve"
FROM_EMAIL       = "noreply@relayshield.net"

# Quota warning thresholds for mp_499 (10,000 call/month) TI plan.
# We fire one email per threshold per billing period; flags are stored on the key record.
INTEL_WARN_80_CALLS = 8_000   # 80% — nudge to upgrade, still 2K calls left
INTEL_WARN_95_CALLS = 9_500   # 95% — urgent, 500 calls remaining
STRIPE_SECRET_NAME = "relayshield/stripe_secret_key"
STRIPE_METER_API   = "https://api.stripe.com/v1/billing/meter_events"

# Threat Intelligence API subscription tiers — monthly call caps.
# None = unlimited. Tier is provisioned automatically by relayshield-developer-signup
# on checkout.session.completed for the $499/$999 Payment Links.
# Defaults to the $499 cap if intel_plan_tier is unset — fails safe rather than
# granting unlimited access to an unverified key.
INTEL_PLAN_LIMITS: dict[str, int | None] = {
    "mp_499":    10000,   # $499/mo — 10,000 calls
    "mssp_999":  None,    # $999/mo — unlimited
}
INTEL_DEFAULT_TIER = "mp_499"

# Stripe Billing Meter event names — one per metered endpoint.
# These must match the event_name values on the meters created in Stripe Dashboard.
STRIPE_METER_EVENTS: dict[str, str] = {
    "/v1/metered/breach":           "relayshield_breach_calls",
    "/v1/metered/sim-swap":         "relayshield_sim_swap_calls",
    "/v1/metered/infostealer":      "relayshield_infostealer_calls",
    "/v1/metered/domain":           "relayshield_domain_calls",
    "/v1/metered/oauth-watchlist":  "relayshield_oauth_watchlist_calls",   # combined HIBP + INTEL-5
    "/v1/metered/crypto-intel":     "relayshield_crypto_intel_calls",
    "/v1/metered/supply-chain":     "relayshield_supply_chain_calls",
    "/v1/metered/session-risk":     "relayshield_session_risk_calls",
    "/v1/metered/identity-graph":   "relayshield_identity_graph_calls",
}

# Credits deducted per successful call (1 credit = $0.01)
METERED_CREDIT_COSTS: dict[str, int] = {
    "/v1/metered/breach":          10,   # $0.10
    "/v1/metered/sim-swap":        25,   # $0.25
    "/v1/metered/infostealer":     50,   # $0.50
    "/v1/metered/domain":          30,   # $0.30
    "/v1/metered/oauth-watchlist": 30,   # $0.30 — combined HIBP watchlist + INTEL-5 stealer corpus (premium)
    "/v1/metered/crypto-intel":    30,   # $0.30
    "/v1/metered/supply-chain":    10,   # $0.10 per call (up to 10 vendor domains)
    "/v1/metered/session-risk":    30,   # $0.30 — INTEL-5 active session hijack / AiTM detection (premium)
    "/v1/metered/identity-graph":  35,   # $0.35 — identity correlation
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


def _send_intel_quota_warning(api_key_str: str, key_record: dict, threshold: int, calls_used: int) -> None:
    """
    Send a one-time SES email warning when an mp_499 key crosses a quota threshold.
    Sets a flag on the key record so the email fires exactly once per threshold per period.
    Non-fatal — never raises; quota enforcement continues even if the email fails.
    """
    email = key_record.get("email", "")
    if not email:
        logger.warning("intel quota warning: no email on key=%s — skipping send", api_key_str[:16])
        return

    flag_field  = "intel_quota_warned_80" if threshold == INTEL_WARN_80_CALLS else "intel_quota_warned_95"
    period      = key_record.get("intel_period_start", datetime.now(timezone.utc).strftime("%Y-%m"))
    flag_value  = key_record.get(flag_field)

    # Only fire once per billing period
    if flag_value == period:
        return

    calls_left  = 10_000 - calls_used
    pct         = threshold // 100  # 8000 → 80, 9500 → 95
    is_urgent   = threshold == INTEL_WARN_95_CALLS

    subject = (
        f"⚠️ Urgent: {calls_left} RelayShield TI calls remaining this month"
        if is_urgent else
        f"RelayShield Threat Intelligence: {pct}% of monthly quota used"
    )

    if is_urgent:
        body_html = f"""
<html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;color:#1a1a1a;">
  <h2 style="color:#dc2626;">⚠️ You have {calls_left:,} Threat Intelligence calls left this month</h2>
  <p>Your RelayShield Threat Intelligence API key has used <strong>{calls_used:,} of 10,000 calls</strong>
  on your current MSP plan ($499/month). At your current rate you will hit the limit before
  the month resets.</p>
  <p>When you reach 10,000 calls, the API returns <code>HTTP 429</code> and all subsequent
  TI queries will fail until the next billing period begins.</p>
  <h3 style="margin-top:2rem;">Upgrade to MSSP — $999/month, unlimited calls</h3>
  <ul>
    <li><strong>No monthly call cap</strong> — query as often as your pipeline demands</li>
    <li>Priority support + SLA</li>
    <li>Same IOC database, same API key — zero integration changes</li>
  </ul>
  <p style="margin-top:1.5rem;">
    <a href="https://buy.stripe.com/4gM3cw1A23yJf9a2JF0Ny0f"
       style="background:#6c63ff;color:#fff;padding:.65rem 1.4rem;border-radius:8px;
              text-decoration:none;font-weight:600;display:inline-block;">
      Upgrade to MSSP — $999/mo →
    </a>
  </p>
  <p style="margin-top:1.5rem;font-size:.85rem;color:#6b7280;">
    Questions? Reply to this email or contact
    <a href="mailto:support@relayshield.net">support@relayshield.net</a>.<br>
    Your billing period resets on the 1st of next month.
  </p>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:2rem 0;">
  <p style="font-size:.75rem;color:#9ca3af;">RelayShield LLC · relayshield.net · API key: {api_key_str[:16]}...</p>
</body></html>
"""
    else:
        body_html = f"""
<html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;color:#1a1a1a;">
  <h2 style="color:#d97706;">You've used 80% of your monthly Threat Intelligence quota</h2>
  <p>Your RelayShield Threat Intelligence API key has used <strong>{calls_used:,} of 10,000 calls</strong>
  on your current MSP plan ($499/month). You have <strong>{calls_left:,} calls remaining</strong>
  this billing period.</p>
  <p>This is an early heads-up — no action required yet. If your usage continues at the
  current rate, you may hit the limit before month end.</p>
  <h3 style="margin-top:2rem;">Consider upgrading to MSSP — $999/month</h3>
  <p>For MSSPs running continuous monitoring across multiple client environments,
  the MSSP tier removes the call cap entirely:</p>
  <ul>
    <li><strong>Unlimited calls/month</strong> — no quota, no 429 errors</li>
    <li>2.5× more value per dollar at scale</li>
    <li>Priority support + SLA</li>
    <li>Same API key, zero integration changes</li>
  </ul>
  <p style="margin-top:1.5rem;">
    <a href="https://buy.stripe.com/4gM3cw1A23yJf9a2JF0Ny0f"
       style="background:#6c63ff;color:#fff;padding:.65rem 1.4rem;border-radius:8px;
              text-decoration:none;font-weight:600;display:inline-block;">
      Upgrade to MSSP — $999/mo →
    </a>
  </p>
  <p style="margin-top:1rem;font-size:.85rem;color:#6b7280;">
    No rush — you still have {calls_left:,} calls this month. We'll send another reminder
    if you reach 95%.
  </p>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:2rem 0;">
  <p style="font-size:.75rem;color:#9ca3af;">RelayShield LLC · relayshield.net · API key: {api_key_str[:16]}...</p>
</body></html>
"""

    try:
        ses.send_email(
            Source=f"RelayShield <{FROM_EMAIL}>",
            Destination={"ToAddresses": [email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body":    {"Html": {"Data": body_html, "Charset": "UTF-8"}},
            },
        )
        logger.info("intel quota warning sent to=%s threshold=%d key=%s", email, threshold, api_key_str[:16])

        # Mark this threshold as warned for the current period
        dynamodb.Table(API_KEYS_TABLE).update_item(
            Key={"api_key": api_key_str},
            UpdateExpression=f"SET {flag_field} = :p",
            ExpressionAttributeValues={":p": period},
        )
    except Exception as exc:
        logger.error("intel quota warning email failed key=%s error=%s", api_key_str[:16], exc)


def _check_and_increment_intel_quota(api_key_str: str, key_record: dict) -> dict | None:
    """
    Enforce the Threat Intelligence API monthly call cap for the api key's
    intel_plan_tier (default mp_499 — fails safe to the capped tier if unset).
    Resets the counter on a new calendar month. Returns an error response
    dict if the key is over quota, or None if the call is allowed (and the
    counter has already been incremented).
    """
    tier  = key_record.get("intel_plan_tier") or INTEL_DEFAULT_TIER
    limit = INTEL_PLAN_LIMITS.get(tier, INTEL_PLAN_LIMITS[INTEL_DEFAULT_TIER])

    table          = dynamodb.Table(API_KEYS_TABLE)
    current_period = datetime.now(timezone.utc).strftime("%Y-%m")
    stored_period  = key_record.get("intel_period_start")

    if stored_period != current_period:
        # New billing month (or first call ever) — reset counter.
        try:
            table.update_item(
                Key={"api_key": api_key_str},
                UpdateExpression="SET intel_period_start = :p, intel_period_calls = :z",
                ExpressionAttributeValues={":p": current_period, ":z": 0},
            )
        except Exception as exc:
            logger.warning("intel quota reset failed key=%s error=%s", api_key_str[:16], exc)
        period_calls = 0
    else:
        period_calls = int(key_record.get("intel_period_calls") or 0)

    if limit is not None and period_calls >= limit:
        return {
            "statusCode": 429,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "ok":      False,
                "error":   f"Monthly call limit ({limit}) reached for the {tier} Threat Intelligence plan.",
                "upgrade_url": "https://relayshield.net/developers",
            }),
        }

    try:
        table.update_item(
            Key={"api_key": api_key_str},
            UpdateExpression="SET intel_period_calls = if_not_exists(intel_period_calls, :z) + :one, "
                              "intel_period_start = :p",
            ExpressionAttributeValues={":z": 0, ":one": 1, ":p": current_period},
        )
    except Exception as exc:
        logger.warning("intel quota increment failed (non-fatal) key=%s error=%s", api_key_str[:16], exc)

    # Quota warning emails — only for capped tier (mp_499); mssp_999 has no limit.
    # Check AFTER incrementing so `period_calls` reflects the call just made.
    if limit is not None:
        new_count = period_calls + 1
        if new_count >= INTEL_WARN_95_CALLS:
            _send_intel_quota_warning(api_key_str, key_record, INTEL_WARN_95_CALLS, new_count)
        elif new_count >= INTEL_WARN_80_CALLS:
            _send_intel_quota_warning(api_key_str, key_record, INTEL_WARN_80_CALLS, new_count)

    return None


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
        "/v1/metered/supply-chain":    handle_supply_chain,
        "/v1/metered/session-risk":    handle_session_risk,
        "/v1/metered/identity-graph":  handle_identity_graph,
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
# Endpoint: POST /v1/metered/oauth-watchlist  /  POST /v1/payg/oauth-watchlist
# ---------------------------------------------------------------------------
# Combined OAuth / token exposure check — two signal sources:
#   1. HIBP breach history × 31-app OAuth watchlist (historical risk)
#   2. INTEL-5 stealer corpus (relayshield_stolen_sessions) — active token theft
#      from stealer log archives captured from criminal Telegram channels
#
# Request:  { "email": "user@example.com" }
# Response: {
#   "email": "...",
#   "matched_count": N,           — HIBP-matched breached OAuth apps
#   "matched_apps":  [...],       — breach-source app list with revoke URLs
#   "stolen_token_count": N,      — INTEL-5: credentials found in stealer logs
#   "stolen_tokens": [...],       — service, severity, category, ingested_at
#   "highest_severity": "...",    — CRITICAL|HIGH|MEDIUM|LOW|NONE
#   "recommendation": "...",
#   "checked_at": "..."
# }

def handle_oauth_watchlist(params: dict) -> dict:
    email = (params.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _err("email is required and must be a valid address")

    # --- Signal 1: HIBP breach × OAuth watchlist ---
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

    matched_apps = []
    for b in breaches:
        name   = (b.get("Name")   or "").lower()
        domain = (b.get("Domain") or "").lower()
        title  = (b.get("Title")  or "").lower()
        for app in OAUTH_WATCHLIST:
            if app in name or app in domain or app in title:
                app_name = b.get("Name", "")
                matched_apps.append({
                    "app":          app_name,
                    "source":       "breach_history",
                    "breach_date":  b.get("BreachDate"),
                    "data_classes": b.get("DataClasses", []),
                    "revoke_url":   OAUTH_REVOCATION_URLS.get(
                                        app_name, "https://myaccount.google.com/permissions"
                                    ),
                })
                break

    # --- Signal 2: INTEL-5 stealer log corpus ---
    stolen_tokens: list[dict] = []
    try:
        resp  = dynamodb.Table(STOLEN_SESSIONS_TABLE_API).query(
            IndexName="email-index",
            KeyConditionExpression=boto3.dynamodb.conditions.Key("matched_email").eq(email),
            FilterExpression=boto3.dynamodb.conditions.Attr("session_type").eq("credential"),
        )
        severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        raw_tokens = sorted(
            resp.get("Items", []),
            key=lambda x: severity_order.get(x.get("severity", "LOW"), 0),
            reverse=True,
        )
        stolen_tokens = [
            {
                "domain":           t.get("domain", ""),
                "source":           "stealer_log",
                "severity":         t.get("severity", "LOW"),
                "service_category": t.get("service_category", ""),
                "channel_source":   t.get("channel_source", ""),
                "ingested_at":      t.get("ingested_at", ""),
            }
            for t in raw_tokens
        ]
    except Exception as exc:
        logger.warning("oauth-watchlist INTEL-5 query failed email=%s: %s", email, exc)
        # Non-fatal — return HIBP results even if INTEL-5 query fails

    # Derive highest severity across both signals
    severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "NONE": 0}
    intel5_highest = max(
        (severity_order.get(t["severity"], 0) for t in stolen_tokens),
        default=0,
    )
    hibp_severity  = 3 if matched_apps else 0   # HIBP match = HIGH by default
    combined_score = max(intel5_highest, hibp_severity)
    highest = {4: "CRITICAL", 3: "HIGH", 2: "MEDIUM", 1: "LOW", 0: "NONE"}.get(combined_score, "NONE")

    # Build recommendation from the most severe signal present
    if stolen_tokens and stolen_tokens[0]["severity"] in ("CRITICAL", "HIGH"):
        rec = (
            "URGENT: Stolen credentials for high-value services were found in criminal stealer logs. "
            "Rotate API keys, revoke OAuth tokens, and invalidate active sessions for all listed services immediately. "
            "For cloud consoles and code repos, treat this as an active incident."
        )
    elif stolen_tokens:
        rec = (
            "Stolen credentials detected in stealer logs. Revoke OAuth tokens and rotate passwords "
            "for all listed services. Check each service's connected-apps or API keys page."
        )
    elif matched_apps:
        rec = (
            "Revoke OAuth access for matched apps immediately using the revoke_url for each. "
            "Also audit all connected apps at myaccount.google.com/permissions and myapps.microsoft.com."
        )
    else:
        rec = "No OAuth exposure detected via breach history or active stealer log corpus."

    logger.info(
        "oauth-watchlist email=%s hibp_matched=%d stolen_tokens=%d highest=%s",
        email, len(matched_apps), len(stolen_tokens), highest,
    )
    return _ok({
        "email":             email,
        "matched_count":     len(matched_apps),
        "matched_apps":      matched_apps,
        "stolen_token_count": len(stolen_tokens),
        "stolen_tokens":     stolen_tokens,
        "highest_severity":  highest,
        "recommendation":    rec,
        "checked_at":        datetime.now(timezone.utc).isoformat(),
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

CAVALIER_URL        = "https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-login"
CAVALIER_DOMAIN_URL = "https://cavalier.hudsonrock.com/api/json/v2/osint-tools/search-by-domain"


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
# Endpoint: POST /v1/metered/supply-chain  /  POST /v1/payg/supply-chain
# ---------------------------------------------------------------------------
# Supply chain / vendor identity risk monitoring.
# For each vendor domain supplied, checks:
#   1. HIBP breacheddomain — how many accounts at that domain appeared in breaches
#   2. Hudson Rock Cavalier — infostealer log hits for that domain
#
# Billing: $0.10 per domain checked (PAYG) / 10 credits per domain (metered).
# For PAYG callers the x402 payment covers up to MAX_VENDOR_DOMAINS domains
# in one call. Metered callers are billed once per call regardless of domain count
# (up to the per-call maximum); the credit cost reflects one unit of work.
#
# Request:
#   { "vendor_domains": ["acme.com", "widget.io"] }          — explicit domain list
#   { "vendor_emails":  ["alice@acme.com", "bob@widget.io"] } — domains extracted
#   Both keys may be supplied; they are merged and deduplicated.
#   Maximum MAX_VENDOR_DOMAINS domains per call.
#
# Response per domain:
#   {
#     "domain":              "acme.com",
#     "breach_count":        3,
#     "breached_accounts":   12,         # distinct email prefixes seen across breaches
#     "breach_names":        ["Adobe", "LinkedIn", ...],
#     "infostealer_found":   true,
#     "infostealer_count":   2,          # infected machines linked to this domain
#     "risk_level":          "HIGH",     # CRITICAL | HIGH | MEDIUM | LOW | CLEAN
#     "risk_factors":        ["active_stealer_logs", "multiple_breaches"],
#     "recommendation":      "...",
#   }

HIBP_DOMAIN_URL   = "https://haveibeenpwned.com/api/v3/breacheddomain/{domain}"
MAX_VENDOR_DOMAINS = 10

# Risk scoring — both signals contribute independently
def _supply_chain_risk(breach_count: int, breached_accounts: int, stealer_count: int) -> tuple[str, list[str]]:
    factors: list[str] = []
    score = 0

    if stealer_count > 0:
        factors.append("active_stealer_logs")
        score += 40 if stealer_count >= 3 else 30

    if breach_count >= 5:
        factors.append("many_breaches")
        score += 20
    elif breach_count >= 2:
        factors.append("multiple_breaches")
        score += 10
    elif breach_count == 1:
        factors.append("one_breach")
        score += 5

    if breached_accounts >= 50:
        factors.append("high_account_exposure")
        score += 20
    elif breached_accounts >= 10:
        factors.append("moderate_account_exposure")
        score += 10

    if score >= 60:
        level = "CRITICAL"
    elif score >= 35:
        level = "HIGH"
    elif score >= 15:
        level = "MEDIUM"
    elif score > 0:
        level = "LOW"
    else:
        level = "CLEAN"

    return level, factors


def _check_vendor_domain(domain: str, hibp_key: str) -> dict:
    """Run HIBP domain breach check + Cavalier infostealer check for one vendor domain."""
    # --- HIBP domain breach check ---
    breach_count      = 0
    breached_accounts = 0
    breach_names: list[str] = []
    try:
        url = HIBP_DOMAIN_URL.format(domain=urllib.parse.quote(domain, safe=""))
        req = urllib.request.Request(
            url,
            headers={"hibp-api-key": hibp_key, "user-agent": "RelayShield-SupplyChain/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            # HIBP breacheddomain returns { "BreachName": ["email_prefix", ...], ... }
            domain_data = json.loads(resp.read())
        breach_count      = len(domain_data)
        breached_accounts = sum(len(v) for v in domain_data.values())
        breach_names      = list(domain_data.keys())
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            logger.warning("HIBP domain check failed domain=%s status=%d", domain, exc.code)
    except Exception as exc:
        logger.warning("HIBP domain check error domain=%s: %s", domain, exc)

    # --- Cavalier infostealer domain check ---
    stealer_count = 0
    stealer_dates: list[str] = []
    try:
        url = f"{CAVALIER_DOMAIN_URL}?domain={urllib.parse.quote(domain, safe='')}"
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield-SupplyChain/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            cav_data      = json.loads(resp.read())
        stealers      = cav_data.get("stealers", [])
        stealer_count = len(stealers)
        stealer_dates = [s.get("date_compromised", "") for s in stealers[:5] if s.get("date_compromised")]
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            logger.warning("Cavalier domain check failed domain=%s status=%d", domain, exc.code)
    except Exception as exc:
        logger.warning("Cavalier domain check error domain=%s: %s", domain, exc)

    risk_level, risk_factors = _supply_chain_risk(breach_count, breached_accounts, stealer_count)

    rec_map = {
        "CRITICAL": (
            "Immediate action required. Active infostealer infections at this vendor mean credentials "
            "they hold for your systems may be compromised right now. Rotate any shared secrets, "
            "revoke API tokens, and request an incident report from this vendor."
        ),
        "HIGH": (
            "High risk. This vendor has significant breach and/or infostealer exposure. "
            "Audit their access to your systems, enforce MFA on any shared portals, "
            "and consider reducing their permission scope."
        ),
        "MEDIUM": (
            "Moderate risk. This vendor has some breach history. Review what data and access "
            "they hold in your environment and confirm they are following credential hygiene practices."
        ),
        "LOW": (
            "Low risk. Minor breach exposure detected. No immediate action required "
            "but include in your next vendor security review cycle."
        ),
        "CLEAN": "No breach or infostealer exposure found for this vendor domain.",
    }

    result = {
        "domain":            domain,
        "breach_count":      breach_count,
        "breached_accounts": breached_accounts,
        "breach_names":      breach_names[:10],   # cap list length in response
        "infostealer_found": stealer_count > 0,
        "infostealer_count": stealer_count,
        "risk_level":        risk_level,
        "risk_factors":      risk_factors,
        "recommendation":    rec_map[risk_level],
    }
    if stealer_dates:
        result["infostealer_dates"] = stealer_dates
    return result


def handle_supply_chain(params: dict) -> dict:
    # Collect domains from both input keys
    raw_domains: list[str] = list(params.get("vendor_domains") or [])
    raw_emails:  list[str] = list(params.get("vendor_emails")  or [])

    # Extract domain portion from any email addresses supplied
    for email in raw_emails:
        email = email.strip().lower()
        if "@" in email:
            raw_domains.append(email.split("@", 1)[1])

    # Normalise + deduplicate
    domains = list({d.strip().lower() for d in raw_domains if d.strip()})

    if not domains:
        return _err("supply_chain requires at least one entry in vendor_domains or vendor_emails")
    if len(domains) > MAX_VENDOR_DOMAINS:
        return _err(f"maximum {MAX_VENDOR_DOMAINS} vendor domains per call; {len(domains)} supplied")

    hibp_key = _hibp_api_key()
    results  = []
    for domain in domains:
        results.append(_check_vendor_domain(domain, hibp_key))

    # Aggregate summary
    risk_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "CLEAN": 0}
    highest    = max(results, key=lambda r: risk_order.get(r["risk_level"], 0))
    critical   = [r["domain"] for r in results if r["risk_level"] == "CRITICAL"]
    high       = [r["domain"] for r in results if r["risk_level"] == "HIGH"]

    logger.info(
        "supply-chain domains=%d critical=%d high=%d",
        len(domains), len(critical), len(high),
    )
    return _ok({
        "domains_checked":   len(domains),
        "highest_risk":      highest["risk_level"],
        "critical_vendors":  critical,
        "high_risk_vendors": high,
        "results":           results,
        "checked_at":        datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# INTEL-5 shared data — service severity classification (mirrors intel_monitor)
# ---------------------------------------------------------------------------

_INTEL5_SEVERITY: list[tuple[str, str, list[str]]] = [
    ("CRITICAL", "Cloud Infrastructure",       ["console.aws.amazon.com", "console.cloud.google.com", "portal.azure.com", "app.cloudflare.com", "cloudflare.com"]),
    ("CRITICAL", "Code Repository / CI-CD",    ["github.com", "gitlab.com", "bitbucket.org", "app.circleci.com", "app.travis-ci.com", "argocd"]),
    ("CRITICAL", "Identity Provider",          ["okta.com", "auth0.com", "login.microsoftonline.com", "admin.google.com", "accounts.google.com"]),
    ("HIGH",     "Payment Processor",          ["dashboard.stripe.com", "paypal.com", "braintreegateway.com"]),
    ("HIGH",     "Domain Registrar / DNS",     ["godaddy.com", "namecheap.com", "name.com", "porkbun.com", "domains.google.com", "dnsimple.com"]),
    ("HIGH",     "Security Tooling",           ["falcon.crowdstrike.com", "app.datadoghq.com", "app.pagerduty.com", "splunk.com", "sentinelone.com"]),
    ("HIGH",     "Financial / Accounting",     ["quickbooks.intuit.com", "xero.com", "app.gusto.com"]),
    ("MEDIUM",   "Developer / Infra SaaS",     ["vercel.com", "app.netlify.com", "heroku.com", "render.com", "digitalocean.com"]),
    ("MEDIUM",   "Productivity / CRM SaaS",    ["slack.com", "notion.so", "app.hubspot.com", "salesforce.com", "linear.app", "atlassian.net", "jira.com"]),
    ("MEDIUM",   "Communication",              ["zoom.us", "teams.microsoft.com", "discord.com"]),
    ("LOW",      "Consumer / Social",          ["twitter.com", "x.com", "facebook.com", "instagram.com", "reddit.com", "linkedin.com"]),
]


def _intel5_classify(domain: str) -> tuple[str, str]:
    domain = domain.lower().lstrip(".")
    for severity, label, patterns in _INTEL5_SEVERITY:
        for pat in patterns:
            if pat in domain:
                return severity, label
    return "LOW", "General Web Service"


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/metered/session-risk  /  POST /v1/payg/session-risk
# ---------------------------------------------------------------------------
# Queries the INTEL-5 stolen-sessions corpus (relayshield_stolen_sessions)
# for active session hijack findings linked to the supplied email address.
# Returns categorized stolen sessions with severity scores.
#
# Request:  { "email": "user@example.com" }
# Response: {
#   "email": "...",
#   "found": true/false,
#   "session_count": N,
#   "highest_severity": "CRITICAL|HIGH|MEDIUM|LOW",
#   "sessions": [
#     { "domain": "github.com", "session_type": "cookie", "cookie_name": "user_session",
#       "severity": "CRITICAL", "service_category": "Code Repository / CI-CD",
#       "channel_source": "logsmarket", "ingested_at": "..." }
#   ]
# }

STOLEN_SESSIONS_TABLE_API = "relayshield_stolen_sessions"


def handle_session_risk(params: dict) -> dict:
    email = (params.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _err("email is required and must be a valid address")

    try:
        table = dynamodb.Table(STOLEN_SESSIONS_TABLE_API)
        resp  = table.query(
            IndexName="email-index",
            KeyConditionExpression=boto3.dynamodb.conditions.Key("matched_email").eq(email),
        )
        items = resp.get("Items", [])
    except Exception as exc:
        logger.exception("session-risk DynamoDB query failed email=%s: %s", email, exc)
        return _err("session risk query failed — internal error", 500)

    if not items:
        return _ok({
            "email":            email,
            "found":            False,
            "session_count":    0,
            "highest_severity": None,
            "sessions":         [],
        })

    severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    sessions = sorted(items, key=lambda x: severity_order.get(x.get("severity", "LOW"), 0), reverse=True)

    highest = sessions[0].get("severity", "LOW") if sessions else "LOW"

    result_sessions = [
        {
            "domain":           s.get("domain", ""),
            "session_type":     s.get("session_type", ""),
            "cookie_name":      s.get("cookie_name", ""),
            "severity":         s.get("severity", "LOW"),
            "service_category": s.get("service_category", ""),
            "channel_source":   s.get("channel_source", ""),
            "ingested_at":      s.get("ingested_at", ""),
        }
        for s in sessions
    ]

    logger.info("session-risk email=%s found=%d highest=%s", email, len(sessions), highest)
    return _ok({
        "email":            email,
        "found":            True,
        "session_count":    len(sessions),
        "highest_severity": highest,
        "sessions":         result_sessions,
        "action_required":  (
            "IMMEDIATE: Log out of all listed services from a clean device and revoke active sessions. "
            "Changing your password alone is insufficient — stolen session cookies bypass 2FA and "
            "remain valid until explicitly invalidated."
        ),
    })


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/metered/identity-graph  /  POST /v1/payg/identity-graph
# ---------------------------------------------------------------------------
# Identity correlation — links an email to associated phones, usernames, and
# domains seen alongside it in criminal channel dumps. Built from co-occurrence
# data extracted by the INTEL-2 monitor (relayshield_identity_graph table).
#
# Customer value:
#   • Pivot from one compromised identifier to find all others exposed in same dump
#   • Correlation engine signal: if linked phone is SIM-swapped, alert email holder
#   • B2A incident responders: full identity surface from a single compromised email
#
# Request:  { "email": "user@example.com" }
# Response: {
#   "email": "...", "found": bool, "correlated_identifiers": N,
#   "correlated_phones": [...], "correlated_domains": [...],
#   "sources": [...], "checked_at": "..."
# }

IDENTITY_GRAPH_TABLE_API = "relayshield_identity_graph"


def handle_identity_graph(params: dict) -> dict:
    email = (params.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _err("email is required and must be a valid address")

    try:
        resp  = dynamodb.Table(IDENTITY_GRAPH_TABLE_API).query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("anchor").eq(email),
        )
        items = resp.get("Items", [])
    except Exception as exc:
        logger.exception("identity-graph query failed email=%s: %s", email, exc)
        return _err("identity graph query failed — internal error", 500)

    if not items:
        return _ok({
            "email":                   email,
            "found":                   False,
            "correlated_identifiers":  0,
            "correlated_phones":       [],
            "correlated_domains":      [],
            "sources":                 [],
            "checked_at":              datetime.now(timezone.utc).isoformat(),
        })

    phones  = list({i["correlated_id"] for i in items if i.get("correlated_type") == "phone"})
    domains = list({i["correlated_id"] for i in items if i.get("correlated_type") == "domain"})
    sources = list({i.get("source", "") for i in items if i.get("source")})

    logger.info("identity-graph email=%s phones=%d domains=%d", email, len(phones), len(domains))
    return _ok({
        "email":                   email,
        "found":                   True,
        "correlated_identifiers":  len(phones) + len(domains),
        "correlated_phones":       phones,
        "correlated_domains":      domains,
        "sources":                 sources,
        "recommendation": (
            "All listed identifiers were found alongside this email in criminal channel dumps. "
            "Treat each as potentially compromised — change passwords and check accounts linked to "
            "any of the correlated phone numbers or domains."
        ),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# STIX/TAXII 2.1 — /v1/intel/taxii/*
# ---------------------------------------------------------------------------
# TAXII 2.1 compliant feed of RelayShield IOCs as STIX 2.1 Indicator objects.
# Enterprise SIEMs (Splunk, Sentinel, Elastic, QRadar) can point their built-in
# TAXII client at this endpoint and pull IOCs on a schedule automatically.
#
# Requires TI subscription API key (intel_access flag).
#
# TAXII 2.1 endpoints:
#   GET /v1/intel/taxii/             — server discovery
#   GET /v1/intel/taxii/collections/ — available collections
#   GET /v1/intel/taxii/collections/iocs/objects/ — STIX Indicator objects
#     ?added_after=<ISO8601>          — only IOCs added after this timestamp
#     ?limit=<N>                      — page size (default 500, max 2000)
#     ?next=<cursor>                  — pagination cursor

import uuid as _uuid_mod


def _ioc_to_stix(item: dict) -> dict | None:
    """Convert a relayshield_intel_iocs record to a STIX 2.1 Indicator object."""
    ioc_val  = item.get("ioc_value", "")
    ioc_type = item.get("ioc_type", "")
    seen_ts  = item.get("seen_ts", datetime.now(timezone.utc).isoformat())
    malware  = item.get("malware", "")
    channel  = item.get("channel", "")
    category = item.get("category", "")

    pattern_map = {
        "ip":         f"[ipv4-addr:value = '{ioc_val}']",
        "domain":     f"[domain-name:value = '{ioc_val}']",
        "url":        f"[url:value = '{ioc_val}']",
        "hash_sha256":f"[file:hashes.SHA-256 = '{ioc_val}']",
        "email":      f"[email-message:from_ref.value = '{ioc_val}']",
        "phone":      None,    # not a standard STIX observable
        "wallet_eth": None,
        "wallet_btc": None,
        "wallet_sol": None,
        "wallet_ton": None,
    }
    pattern = pattern_map.get(ioc_type)
    if pattern is None:
        return None

    indicator_id = f"indicator--{str(_uuid_mod.uuid5(_uuid_mod.NAMESPACE_URL, f'relayshield:{ioc_val}'))}"
    labels       = ["malicious-activity"]
    if malware and malware not in ("None", "n/a", ""):
        labels.append(f"malware:{malware[:50]}")

    return {
        "type":          "indicator",
        "spec_version":  "2.1",
        "id":            indicator_id,
        "created":       seen_ts,
        "modified":      seen_ts,
        "name":          ioc_val,
        "description":   f"Observed in {channel} ({category})" + (f" — {malware}" if malware and malware not in ("None","n/a","") else ""),
        "pattern":       pattern,
        "pattern_type":  "stix",
        "valid_from":    seen_ts,
        "labels":        labels,
        "external_references": [{"source_name": "relayshield", "url": "https://relayshield.net"}],
    }


def handle_taxii_discovery(params: dict, api_key_record: dict) -> dict:
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/taxii+json;version=2.1",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps({
            "title":       "RelayShield Threat Intelligence",
            "description": "RelayShield TAXII 2.1 server — 200,000+ IOCs from criminal Telegram channels and 11 authoritative feeds",
            "contact":     "relayshieldadmin@gmail.com",
            "api_roots":   ["https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod/v1/intel/taxii/"],
        }),
    }


def handle_taxii_collections(params: dict, api_key_record: dict) -> dict:
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/taxii+json;version=2.1"},
        "body": json.dumps({
            "collections": [
                {
                    "id":          "relayshield-iocs",
                    "title":       "RelayShield IOCs",
                    "description": "Malicious IPs, domains, URLs, and file hashes from 8 criminal Telegram channels and 11 authoritative threat feeds. 450+ malware families tracked.",
                    "can_read":    True,
                    "can_write":   False,
                    "media_types": ["application/stix+json;version=2.1"],
                }
            ]
        }),
    }


def handle_taxii_objects(params: dict, api_key_record: dict, query_params: dict) -> dict:
    added_after = query_params.get("added_after", "")
    try:
        limit = min(int(query_params.get("limit", 500)), 2000)
    except (ValueError, TypeError):
        limit = 500

    table = dynamodb.Table(INTEL_IOCS_TABLE)
    scan_kwargs: dict = {
        "ProjectionExpression":     "ioc_value, ioc_type, seen_ts, malware, channel, category",
        "FilterExpression":         boto3.dynamodb.conditions.Attr("ioc_type").is_in(
                                        ["ip", "domain", "url", "hash_sha256", "email"]
                                    ),
        "Limit":                    limit * 3,  # over-fetch to account for type filtering
    }
    if added_after:
        scan_kwargs["FilterExpression"] = (
            scan_kwargs["FilterExpression"] &
            boto3.dynamodb.conditions.Attr("seen_ts").gte(added_after)
        )
    if cursor := query_params.get("next"):
        try:
            scan_kwargs["ExclusiveStartKey"] = json.loads(cursor)
        except Exception:
            pass

    try:
        resp  = table.scan(**scan_kwargs)
        items = resp.get("Items", [])
        next_key = resp.get("LastEvaluatedKey")
    except Exception as exc:
        logger.exception("TAXII objects scan failed: %s", exc)
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/taxii+json;version=2.1"},
            "body": json.dumps({"title": "Internal Server Error", "description": str(exc)}),
        }

    indicators = []
    for item in items:
        stix_obj = _ioc_to_stix(item)
        if stix_obj:
            indicators.append(stix_obj)
        if len(indicators) >= limit:
            break

    bundle = {
        "type":           "bundle",
        "id":             f"bundle--{str(_uuid_mod.uuid4())}",
        "spec_version":   "2.1",
        "objects":        indicators,
    }

    response_body = {"objects": indicators, "more": bool(next_key)}
    if next_key:
        response_body["next"] = json.dumps(next_key)

    logger.info("TAXII objects returned=%d more=%s", len(indicators), bool(next_key))
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/stix+json;version=2.1"},
        "body": json.dumps(response_body),
    }


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
    if not api_key_record or not api_key_record.get("intel_access"):
        return {
            "statusCode": 403,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "ok":    False,
                "error": "Threat Intelligence API access required. Upgrade at relayshield.net/developers.",
            }),
        }

    # Monthly call cap — $499/mo tier capped at 10K, $999/mo unlimited.
    # Fails safe to the capped tier if intel_plan_tier was never set.
    quota_error = _check_and_increment_intel_quota(api_key_record["api_key"], api_key_record)
    if quota_error:
        return quota_error

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
        "/v1/payg/supply-chain":          handle_supply_chain,
        "/v1/payg/session-risk":          handle_session_risk,
        "/v1/payg/identity-graph":        handle_identity_graph,
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
# Threat Intelligence API — /v1/intel/cve
# ---------------------------------------------------------------------------
# Request: POST /v1/intel/cve
#   { "cve_id": "CVE-2024-1234" }   — exact CVE ID lookup
#   { "keyword": "apache" }          — case-insensitive keyword scan across
#                                      vendor_project, product, vulnerability_name
#
# Response:
#   { ok: true, data: { count: int, results: [...] } }
# ---------------------------------------------------------------------------

def handle_intel_cve(params: dict, api_key_record: dict | None = None) -> dict:
    cve_id  = (params.get("cve_id") or "").strip().upper()
    keyword = (params.get("keyword") or "").strip().lower()

    if not cve_id and not keyword:
        return _err("cve_id or keyword is required")

    table = dynamodb.Table(INTEL_CVE_TABLE)

    if cve_id:
        try:
            resp = table.get_item(Key={"cve_id": cve_id})
            item = resp.get("Item")
        except Exception as exc:
            logger.error("cve lookup failed cve_id=%s: %s", cve_id, exc)
            return _err("CVE lookup failed", 500)

        if not item:
            return _ok({"count": 0, "results": []})

        item.pop("ttl", None)
        return _ok({"count": 1, "results": [item]})

    # Keyword scan — scan table and filter in Python (table is small, <2K rows)
    try:
        resp  = table.scan()
        items = resp.get("Items", [])
        while "LastEvaluatedKey" in resp:
            resp  = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
            items.extend(resp.get("Items", []))
    except Exception as exc:
        logger.error("cve keyword scan failed keyword=%s: %s", keyword, exc)
        return _err("CVE keyword scan failed", 500)

    matches = []
    for item in items:
        haystack = " ".join([
            item.get("vendor_project", ""),
            item.get("product", ""),
            item.get("vulnerability_name", ""),
            item.get("short_description", ""),
        ]).lower()
        if keyword in haystack:
            item.pop("ttl", None)
            matches.append(item)

    matches.sort(key=lambda x: x.get("date_added", ""), reverse=True)
    return _ok({"count": len(matches), "results": matches[:50]})


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
    "/v1/intel/cve":        handle_intel_cve,         # CISA KEV lookup by CVE ID or keyword
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

    # TAXII 2.1 endpoints (GET, intel_access required)
    if path.startswith("/v1/intel/taxii"):
        headers    = event.get("headers") or {}
        api_key    = (headers.get("X-RS-API-KEY") or headers.get("x-rs-api-key") or
                      headers.get("X-API-Key") or headers.get("x-api-key", ""))
        key_record = _verify_rs_api_key(api_key) if api_key else None
        if not key_record or not key_record.get("intel_access"):
            return {"statusCode": 401, "headers": {"Content-Type": "application/taxii+json;version=2.1"},
                    "body": json.dumps({"title": "Unauthorized", "description": "TI subscription required. Pass your RS API key as X-RS-API-KEY."})}
        qp = event.get("queryStringParameters") or {}
        if path == "/v1/intel/taxii/" or path == "/v1/intel/taxii":
            return handle_taxii_discovery({}, key_record)
        if path in ("/v1/intel/taxii/collections/", "/v1/intel/taxii/collections"):
            return handle_taxii_collections({}, key_record)
        if path.startswith("/v1/intel/taxii/collections/iocs/objects"):
            return handle_taxii_objects({}, key_record, qp)
        return {"statusCode": 404, "headers": {"Content-Type": "application/taxii+json;version=2.1"},
                "body": json.dumps({"title": "Not Found"})}

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
        if path in ("/v1/intel/telegram", "/v1/intel/cve"):
            headers    = event.get("headers") or {}
            api_key    = (headers.get("X-API-Key") or headers.get("x-api-key") or
                          headers.get("X-RS-API-KEY") or headers.get("x-rs-api-key", ""))
            key_record = _verify_rs_api_key(api_key) if api_key else None
            return handler(params, api_key_record=key_record)
        return handler(params)
    except Exception as exc:
        logger.exception("Unhandled error in %s: %s", path, exc)
        return _err("internal server error", 500)
