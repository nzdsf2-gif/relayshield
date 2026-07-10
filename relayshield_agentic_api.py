"""
RelayShield Agentic API — AWS Marketplace Bundle D ("Agentic Attack Surface")

Isolated Lambda module for the two genuinely NEW endpoints in Bundle D
(mcp-registry-risk, prompt-injection-breach). Deliberately self-contained —
zero shared code path with relayshield_api.py or relayshield_aws_marketplace.py,
per the isolation mandate agreed 2026-07-06 (TODO.md item 32) and reaffirmed
2026-07-07 for the Agentic bundle specifically: a bug in this new, unproven
metering/detection logic must not be able to regress the already-live TI
Starter/Unlimited fulfillment or the already-approved Bundle A/B/C endpoints.

Endpoints:
  POST /v1/metered/mcp-registry-risk    ($0.35/call, proposed)
  POST /v1/metered/prompt-injection-breach  ($0.35/call, proposed)

Deploy as a new Lambda function (e.g. relayshield-agentic-api) with its own
API Gateway routes — do not merge into the existing relayshield-api Lambda.
"""

import base64
import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb        = boto3.resource("dynamodb")
kms_client      = boto3.client("kms")
secrets_client  = boto3.client("secretsmanager")

# ---------------------------------------------------------------------------
# Shared tables this Lambda READS from (read-only against all of them except
# its own two new tables below — never writes to relayshield_intel_iocs,
# relayshield_stolen_sessions, or relayshield_api_keys).
# ---------------------------------------------------------------------------
API_KEYS_TABLE          = "relayshield_api_keys"
INTEL_IOCS_TABLE        = "relayshield_intel_iocs"
STOLEN_SESSIONS_TABLE   = "relayshield_stolen_sessions"

STRIPE_SECRET_NAME = "relayshield/stripe_secret_key"
STRIPE_METER_API   = "https://api.stripe.com/v1/billing/meter_events"

STRIPE_METER_EVENTS = {
    "/v1/metered/mcp-registry-risk":      "relayshield_mcp_registry_risk_calls",
    "/v1/metered/prompt-injection-breach": "relayshield_prompt_injection_breach_calls",
}
PRICE_CENTS = {
    "/v1/metered/mcp-registry-risk":      35,   # $0.35/call — proposed, not yet in Stripe
    "/v1/metered/prompt-injection-breach": 35,   # $0.35/call — proposed, not yet in Stripe
}

_secret_cache: dict[str, str] = {}

# ---------------------------------------------------------------------------
# x402 PAYG configuration — mirrors relayshield_api.py's constants exactly
# (same destination wallets, same facilitators). Verification logic is
# duplicated rather than imported, same isolation rationale as the rest of
# this file.
# ---------------------------------------------------------------------------
X402_PAYTO_ADDRESS   = os.environ.get("RELAYSHIELD_X402_WALLET", "")
SOL_PAYTO_ADDRESS    = os.environ.get("RELAYSHIELD_SOL_WALLET", "")
X402_FACILITATOR_URL = "https://facilitator.payai.network"
SOL_FACILITATOR_URL  = "https://x402.org/facilitator"
USDC_BASE_ADDRESS    = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDC_SOL_ADDRESS     = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
BASE_CHAIN_ID        = "base"
SOL_CHAIN_ID         = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"
SOL_FEE_PAYER        = "EwWqGE4ZFKLofuestmU4LDdK7XM1N4ALgdZccwYugwGd"

API_BASE_URL = "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod"

PAYG_PRICE_UNITS = {
    "/v1/payg/mcp-registry-risk":       350000,   # $0.35 — mirrors metered price
    "/v1/payg/prompt-injection-breach": 350000,   # $0.35 — mirrors metered price
}

RDAP_URL = "https://rdap.org/domain/{domain}"

# Well-known, legitimate MCP ecosystem domains — used only as the comparison
# set for typosquat detection below, not an allowlist/denylist.
KNOWN_MCP_DOMAINS = [
    "modelcontextprotocol.io", "github.com", "npmjs.com", "pypi.org",
    "smithery.ai", "glama.ai", "mcp.so", "anthropic.com",
]


# ---------------------------------------------------------------------------
# Shared helpers (intentionally duplicated from relayshield_api.py rather
# than imported — keeps this Lambda's deployment package fully independent)
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
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode("utf-8")
        return json.loads(raw)
    except Exception:
        return {}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def _get_secret(secret_name: str) -> str:
    if secret_name not in _secret_cache:
        raw = secrets_client.get_secret_value(SecretId=secret_name)["SecretString"].strip()
        _secret_cache[secret_name] = raw
    return _secret_cache[secret_name]


def _stripe_secret_key() -> str:
    raw = _get_secret(STRIPE_SECRET_NAME)
    try:
        return json.loads(raw).get("stripe_secret_key") or json.loads(raw).get("STRIPE_SECRET_KEY") or raw
    except (json.JSONDecodeError, KeyError):
        return raw


def _verify_rs_api_key(api_key_str: str) -> dict | None:
    """Look up a RelayShield API key in DynamoDB. Read-only. Returns the record or None."""
    if not api_key_str or not (api_key_str.startswith("rs_live_") or api_key_str.startswith("rs_demo_")):
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


def _levenshtein(a: str, b: str) -> int:
    """Standard edit distance — used for MCP registry typosquat detection."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/metered/mcp-registry-risk  (AGENTIC-3)
# ---------------------------------------------------------------------------
# v1 design — reuses existing signal types rather than building new
# detection infra from scratch:
#   1. IOC corpus lookup (relayshield_intel_iocs) — known-malicious domain/URL
#   2. Typosquat/near-miss check against well-known MCP ecosystem domains
#   3. RDAP domain-registration-age check — newly registered domains hosting
#      MCP servers warrant extra scrutiny
#
# Request:  { "server_url": "https://..." } or { "package_name": "..." }
# Response: { "verdict": "CRITICAL"|"HIGH"|"MEDIUM"|"LOW", "findings": [...] }

def handle_mcp_registry_risk(params: dict) -> dict:
    server_url   = (params.get("server_url") or "").strip()
    package_name = (params.get("package_name") or "").strip()

    if not server_url and not package_name:
        return _err("server_url or package_name is required")

    findings: list[dict] = []
    domain = ""
    if server_url:
        try:
            domain = urllib.parse.urlparse(server_url).netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
        except Exception:
            domain = ""

    # 1. IOC corpus lookup — direct known-malicious match.
    # ioc_value is the table's partition key (seen_ts is the sort key, no
    # GSI) — this is a targeted Query against one partition, not a Scan,
    # important given the corpus is 2.2M+ items (confirmed 2026-07-07).
    if domain:
        try:
            table = dynamodb.Table(INTEL_IOCS_TABLE)
            resp  = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key("ioc_value").eq(domain),
                FilterExpression=boto3.dynamodb.conditions.Attr("ioc_type").is_in(["domain", "url"]),
                Limit=5,
            )
            if resp.get("Items"):
                findings.append({
                    "type": "known_malicious_ioc", "severity": "CRITICAL",
                    "detail": f"{domain} appears in RelayShield's criminal IOC corpus",
                })
        except Exception as exc:
            logger.warning("mcp-registry-risk IOC lookup failed domain=%s: %s", domain, exc)

    # 2. Typosquat / near-miss check against well-known MCP ecosystem domains
    if domain:
        for known in KNOWN_MCP_DOMAINS:
            if domain == known:
                break  # exact match to a known-good domain — not a typosquat
            dist = _levenshtein(domain, known)
            if 0 < dist <= 2 and len(domain) > 4:
                findings.append({
                    "type": "typosquat_suspected", "severity": "HIGH",
                    "detail": f"{domain} is a close match (edit distance {dist}) to known domain {known}",
                })
                break

    # 3. RDAP registration-age check — newly registered domains are higher risk
    if domain:
        age_days = _rdap_registration_age_days(domain)
        if age_days is not None and age_days < 30:
            findings.append({
                "type": "newly_registered_domain", "severity": "MEDIUM",
                "detail": f"{domain} was registered {age_days} days ago",
            })

    if not domain and package_name:
        findings.append({
            "type": "package_name_only", "severity": "LOW",
            "detail": "No server_url provided — package-name-only checks are limited to the IOC corpus, "
                      "which has no dedicated MCP package coverage yet",
        })

    severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    verdict = max((f["severity"] for f in findings), key=lambda s: severity_order.get(s, 0), default="LOW")

    return _ok({
        "queried":  server_url or package_name,
        "domain":   domain,
        "verdict":  verdict,
        "findings": findings,
        "note": (
            "No red flags found — this is not proof of safety. MCP registry security tooling "
            "coverage is minimal industry-wide as of 2026-07; treat absence of findings as "
            "'unknown,' not 'verified safe.'" if not findings else None
        ),
    })


def _rdap_registration_age_days(domain: str) -> int | None:
    url = RDAP_URL.format(domain=urllib.parse.quote(domain))
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        for event in data.get("events", []):
            if event.get("eventAction") == "registration":
                reg_str = event.get("eventDate", "")
                if reg_str:
                    reg_dt = datetime.fromisoformat(reg_str.replace("Z", "+00:00"))
                    return (datetime.now(timezone.utc) - reg_dt).days
    except urllib.error.HTTPError as exc:
        if exc.code not in (404, 400):
            logger.warning("RDAP HTTP %d for %s", exc.code, domain)
    except Exception as exc:
        logger.warning("RDAP registration lookup failed for %s: %s", domain, exc)
    return None


# ---------------------------------------------------------------------------
# Endpoint: POST /v1/metered/prompt-injection-breach  (AGENTIC-4)
# ---------------------------------------------------------------------------
# v1 heuristic, not a labeled ground-truth classifier — queries
# relayshield_stolen_sessions (same table + email-index GSI as the existing
# session-risk endpoint) for records the ingestion pipeline flagged
# suspected_agentic_source=True based on keyword matches in the Telegram
# post text describing the archive (see relayshield_intel_monitor.py
# _looks_agentic_source, added 2026-07-07).
#
# Request:  { "email": "user@example.com" }
# Response: { "found": bool, "session_count": N, "sessions": [...] }

def handle_prompt_injection_breach(params: dict) -> dict:
    email = (params.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return _err("email is required and must be a valid address")

    email_hash = _sha256(email)
    try:
        table = dynamodb.Table(STOLEN_SESSIONS_TABLE)
        resp  = table.query(
            IndexName="email-index",
            KeyConditionExpression=boto3.dynamodb.conditions.Key("matched_email").eq(email_hash),
            FilterExpression=boto3.dynamodb.conditions.Attr("suspected_agentic_source").eq(True),
        )
        items = resp.get("Items", [])
    except Exception as exc:
        logger.exception("prompt-injection-breach query failed email=%s: %s", email, exc)
        return _err("prompt-injection-breach query failed — internal error", 500)

    if not items:
        return _ok({
            "email": email, "found": False, "session_count": 0, "sessions": [],
            "note": "No exposure found with a suspected-agentic-source marker. This is a heuristic "
                    "keyword classifier over dump-announcement text, not a confirmed attribution — "
                    "absence of a match does not rule out an AI-agent-involved breach.",
        })

    sessions = [
        {
            "domain":           s.get("domain", ""),
            "severity":         s.get("severity", "LOW"),
            "service_category": s.get("service_category", ""),
            "channel_source":   s.get("channel_source", ""),
            "ingested_at":      s.get("ingested_at", ""),
        }
        for s in items
    ]
    return _ok({
        "email": email,
        "found": True,
        "session_count": len(sessions),
        "sessions": sessions,
        "action_required": (
            "This exposure surfaced from a dump whose own announcement text suggests an AI agent "
            "(rather than a traditional phishing/malware campaign) was involved in obtaining it. "
            "Treat with the same urgency as an active session hijack — revoke sessions and rotate "
            "credentials for the listed services."
        ),
    })


# ---------------------------------------------------------------------------
# x402 PAYG — payment requirements, verification, 402 response.
# Logic mirrored from relayshield_api.py (same facilitators, same wallets),
# not imported — keeps this Lambda's deployment package independent.
# ---------------------------------------------------------------------------

def _bazaar_body_ext(input_example: dict, output_example: dict) -> dict:
    """Minimal Bazaar BodyDiscoveryExtension — same shape as relayshield_api.py's
    version, trimmed since these 2 endpoints don't need the full JSON-schema
    validation block to be cataloged on Agentic.Market."""
    return {
        "bazaar": {
            "info": {
                "input":  {"type": "http", "bodyType": "json", "body": input_example},
                "output": {"type": "json", "example": output_example},
            },
        },
    }


BAZAAR_EXTENSIONS: dict[str, dict] = {
    "/v1/payg/mcp-registry-risk": _bazaar_body_ext(
        input_example={"server_url": "https://example-mcp-server.com"},
        output_example={"ok": True, "data": {"verdict": "LOW", "findings": []}},
    ),
    "/v1/payg/prompt-injection-breach": _bazaar_body_ext(
        input_example={"email": "user@example.com"},
        output_example={"ok": True, "data": {"found": False, "session_count": 0}},
    ),
}


def _build_payment_requirements(path: str, price_units: int) -> dict:
    resource    = f"{API_BASE_URL}{path}"
    description = f"RelayShield {path.split('/')[-1].replace('-', ' ')} check"
    bazaar_ext  = BAZAAR_EXTENSIONS.get(path)

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

    if SOL_PAYTO_ADDRESS:
        sol_entry = {
            "scheme":            "exact",
            "network":           SOL_CHAIN_ID,
            "maxAmountRequired": str(price_units),
            "resource":          resource,
            "description":       description,
            "mimeType":          "application/json",
            "payTo":             SOL_PAYTO_ADDRESS,
            "maxTimeoutSeconds": 60,
            "asset":             USDC_SOL_ADDRESS,
            "extra": {"feePayer": SOL_FEE_PAYER},
        }
        if bazaar_ext:
            sol_entry["extensions"] = bazaar_ext
        accepts.append(sol_entry)

    return {"x402Version": 1, "accepts": accepts}


def _x402_payment_required(path: str) -> dict:
    price_units  = PAYG_PRICE_UNITS.get(path, 350000)
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
            "ok":    False,
            "error": "Payment required",
            "price": f"{price_usd} USDC ({chains})",
            "x402":  requirements,
        }),
    }


def _detect_payment_chain(x_payment: str) -> str:
    try:
        decoded = base64.b64decode(x_payment + "==")
        parsed = json.loads(decoded)
        if parsed.get("network", "").startswith("solana"):
            return "solana"
        return "evm"
    except Exception:
        try:
            parsed = json.loads(x_payment)
            if parsed.get("network", "").startswith("solana"):
                return "solana"
        except Exception:
            pass
        return "evm"


def _verify_x402_payment(x_payment: str, path: str) -> bool:
    price_units  = PAYG_PRICE_UNITS.get(path, 0)
    requirements = _build_payment_requirements(path, price_units)
    chain = _detect_payment_chain(x_payment)
    logger.info("x402 payment detected chain=%s path=%s", chain, path)

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
            (a for a in requirements.get("accepts", []) if a.get("network") == SOL_CHAIN_ID), None,
        )
        if not sol_requirements:
            logger.error("No Solana accepts entry in requirements for path=%s", path)
            return False
        verify_payload = json.dumps({
            "x402Version": 1, "paymentPayload": payment_payload_dict, "paymentRequirements": sol_requirements,
        }).encode("utf-8")
    else:
        if not X402_PAYTO_ADDRESS:
            logger.error("RELAYSHIELD_X402_WALLET not set — cannot verify EVM x402 payment")
            return False
        evm_requirements = next(
            (a for a in requirements.get("accepts", []) if a.get("network") == BASE_CHAIN_ID), requirements,
        )
        verify_payload = json.dumps({
            "x402Version": 1, "paymentPayload": payment_payload_dict, "paymentRequirements": evm_requirements,
        }).encode("utf-8")

    facilitator_base = SOL_FACILITATOR_URL if chain == "solana" else X402_FACILITATOR_URL
    verify_url = f"{facilitator_base}/verify"
    req = urllib.request.Request(
        verify_url, data=verify_payload, headers={"Content-Type": "application/json"}, method="POST",
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
        logger.error("x402 facilitator HTTP %d — chain=%s path=%s body=%s", exc.code, chain, path, body)
        return False
    except Exception as exc:
        logger.error("x402 facilitator call failed — chain=%s path=%s error=%s", chain, path, exc)
        return False


def handle_payg_request(path: str, event: dict) -> dict:
    headers   = event.get("headers") or {}
    x_payment = headers.get("X-PAYMENT") or headers.get("x-payment", "")

    if not x_payment:
        return _x402_payment_required(path)
    if not _verify_x402_payment(x_payment, path):
        return _err("Invalid or expired payment proof — pay again and retry.", 402)

    payg_routes = {
        "/v1/payg/mcp-registry-risk":       handle_mcp_registry_risk,
        "/v1/payg/prompt-injection-breach": handle_prompt_injection_breach,
    }
    handler = payg_routes.get(path)
    if not handler:
        return _err(f"unknown PAYG endpoint: {path}", 404)
    return handler(_body(event))


# ---------------------------------------------------------------------------
# Lambda entry point — deliberately minimal, no shared dispatch/auth code
# with relayshield_api.py.
# ---------------------------------------------------------------------------

ROUTES = {
    "/v1/metered/mcp-registry-risk":       handle_mcp_registry_risk,
    "/v1/metered/prompt-injection-breach": handle_prompt_injection_breach,
}


def lambda_handler(event: dict, context) -> dict:
    path   = event.get("path", "")
    method = event.get("httpMethod", "")
    logger.info("Agentic API request — method=%s path=%s", method, path)

    if method in ("GET", "HEAD") and path in ("/", "/v1", "/v1/"):
        return _ok({
            "service": "RelayShield Agentic API (Bundle D)",
            "metered_endpoints": list(ROUTES.keys()),
            "payg_endpoints": list(PAYG_PRICE_UNITS.keys()),
        })

    if path.startswith("/v1/payg/"):
        if method != "POST":
            return _err(f"{path} only accepts POST requests", 405)
        return handle_payg_request(path, event)

    handler = ROUTES.get(path)
    if method != "POST" or handler is None:
        return _err("Not found", 404)

    api_key = (event.get("headers") or {}).get("X-RS-API-KEY") or (event.get("headers") or {}).get("x-rs-api-key")
    key_record = _verify_rs_api_key(api_key or "")
    if not key_record:
        return _err("Invalid or missing API key", 401)

    params = _body(event)
    result = handler(params)

    # Only meter successful calls (2xx) — never bill a request that errored.
    # TI Starter/Unlimited subscribers get unlimited access to all metered
    # endpoints as part of their subscription (documented policy, see
    # api.relayshield.net/developers). Covers both billing paths: direct
    # Stripe TI subscribers (stripe_subscription_id) and AWS Marketplace TI
    # subscribers (intel_plan_tier — set exclusively by
    # relayshield_aws_marketplace.py's _provision_api_key, never elsewhere).
    # Mirrors the identical fix applied to relayshield_api.py's
    # handle_metered_request 2026-07-08 — same bug, same fix, both files,
    # kept consistent even though this Lambda is otherwise fully isolated.
    if result.get("statusCode", 200) < 300:
        has_subscription = bool(key_record.get("stripe_subscription_id")) or bool(key_record.get("intel_plan_tier"))
        if not has_subscription:
            stripe_customer_id = key_record.get("stripe_customer_id", "")
            if stripe_customer_id:
                _record_stripe_meter_event(stripe_customer_id, STRIPE_METER_EVENTS.get(path, ""))

    return result
