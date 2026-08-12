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
import random
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

# Single aggregate Stripe Billing Meter, replacing per-endpoint meters for
# billing on 2026-08-04. formula=sum over payload[value] in CENTS, billed
# against a $0.01-per-unit price. Must match relayshield_api.py's constant.
STRIPE_USAGE_METER_EVENT = "relayshield_api_usage"

# Per-endpoint meter event names. NO LONGER USED FOR BILLING — retained because
# the meters still hold historical data in Stripe. PRICE_CENTS is now the
# authoritative "is this billable, and for how much" table.
STRIPE_METER_EVENTS = {
    "/v1/metered/mcp-registry-risk":      "relayshield_mcp_registry_risk_calls",
    "/v1/metered/prompt-injection-breach": "relayshield_prompt_injection_breach_calls",
}
# Corrected 2026-08-04: the old "proposed, not yet in Stripe" comment was
# wrong and cost real time. Both meters AND both $0.35 prices have existed
# since 2026-07-07 (TODO AGENTIC-3/4). What was actually missing was
# membership in STRIPE_PRICE_IDS, so no subscription ever carried the line
# item. Now billed through the aggregate meter above.
PRICE_CENTS = {
    "/v1/metered/mcp-registry-risk":      35,   # $0.35/call
    "/v1/metered/prompt-injection-breach": 35,   # $0.35/call
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
SOL_FACILITATOR_URL  = "https://facilitator.payai.network"    # Solana — PayAI (same facilitator as Base; x402.org was a testnet facilitator with no Bazaar support, confirmed 2026-07-10)

# CDP (Coinbase Developer Platform) facilitator — preferred over PayAI when
# configured. Added 2026-07-11: CDP's own Bazaar is the discovery registry
# AWS surfaces through Bedrock AgentCore's gateway, so routing settlements
# through CDP is what actually makes these endpoints reachable by any
# AgentCore-built agent, not just a nice-to-have second facilitator.
CDP_API_KEY_ID       = os.environ.get("CDP_API_KEY_ID", "")
CDP_API_KEY_SECRET   = os.environ.get("CDP_API_KEY_SECRET", "")
CDP_FACILITATOR_HOST = "api.cdp.coinbase.com"
CDP_FACILITATOR_URL  = f"https://{CDP_FACILITATOR_HOST}/platform/v2/x402"
USDC_BASE_ADDRESS    = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDC_SOL_ADDRESS     = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
BASE_CHAIN_ID        = "base"
BASE_CHAIN_ID_V2     = "eip155:8453"  # V2 CAIP-2 format — Base mainnet
SOL_CHAIN_ID         = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"  # same value in V1 and V2
SOL_FEE_PAYER        = "EwWqGE4ZFKLofuestmU4LDdK7XM1N4ALgdZccwYugwGd"

# x402 V2 staged migration (TODO.md item 50) — mirrors relayshield_api.py's
# allowlist. Empty by default, everything stays on V1.
# Batch E (CDPX-7), added 2026-07-20 — no prior V2 attempt/failure history.
X402_V2_ENABLED_PATHS: set[str] = {
    "/v1/payg/mcp-registry-risk",
    "/v1/payg/prompt-injection-breach",
}

API_BASE_URL = "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod"

PAYG_PRICE_UNITS = {
    "/v1/payg/mcp-registry-risk":       350000,   # $0.35 — mirrors metered price
    "/v1/payg/prompt-injection-breach": 350000,   # $0.35 — mirrors metered price
}

# AWS Marketplace Bundle D usage dimensions — API identifiers must match
# exactly what's configured in the AWS Marketplace pricing dimensions.
BUNDLE_D_PRODUCT_CODE = os.environ.get("BUNDLE_D_PRODUCT_CODE", "")
AWS_DIMENSION_NAMES = {
    "/v1/metered/mcp-registry-risk":       "mcp_registry_risk",
    "/v1/metered/prompt-injection-breach": "prompt_injection_breach",
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


def _header(headers: dict, name: str) -> str:
    """Case-insensitive header lookup.

    Duplicated from relayshield_api.py rather than imported, same isolation
    rationale used throughout this Lambda. API Gateway's REST API preserves
    client header casing, and Python's stdlib urllib normalizes header names
    with str.capitalize() -- "X-RS-API-KEY" arrives as "X-rs-api-key", which
    matched none of the spellings previously enumerated here, so every
    urllib-based caller got a 401. Found 2026-07-31.
    """
    if not headers:
        return ""
    target = name.lower()
    for k, v in headers.items():
        if k.lower() == target:
            return v or ""
    return ""


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


# Duplicated from relayshield_api.py (same isolation rationale as the rest of
# this file) — daily call cap for the "hf_smolagents_demo" key embedded in
# the public relayshield_smolagents_tool.py package. See that file's copy for
# the full rationale (public-source key = scrapable = must be quota-capped).
DEMO_QUOTA_TABLE   = "relayshield_demo_key_usage"
DEMO_QUOTA_SOURCES = {"hf_smolagents_demo": 20}

def _check_demo_quota(key_record: dict) -> bool:
    cap = DEMO_QUOTA_SOURCES.get(key_record.get("source"))
    if cap is None:
        return True
    usage_key = f"{key_record.get('api_key', '')}#{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    try:
        table = dynamodb.Table(DEMO_QUOTA_TABLE)
        resp  = table.update_item(
            Key={"usage_key": usage_key},
            UpdateExpression="ADD call_count :one SET expires_at = if_not_exists(expires_at, :ttl)",
            ExpressionAttributeValues={":one": 1, ":ttl": int(time.time()) + 3 * 86400},
            ReturnValues="UPDATED_NEW",
        )
        return int(resp["Attributes"]["call_count"]) <= cap
    except Exception as exc:
        logger.error("demo quota check failed key=%s error=%s", key_record.get("api_key", "")[:16], exc)
        return True


def _report_marketplace_usage(aws_account_id: str, license_arn: str, dimension: str) -> None:
    """Report one call of usage to AWS Marketplace Metering Service for a
    Bundle D contract customer. Fire-and-forget — never raises. Duplicated
    from relayshield_bundle_fulfillment.py rather than imported, same
    isolation rationale as the rest of this file.

    Uses CustomerAWSAccountId + LicenseArn, not the older CustomerIdentifier
    + ProductCode-only pattern — AWS's Concurrent Agreements model (rolled
    out 2026-06-01) rejects the old pattern for products created after that
    date with InvalidLicenseException, confirmed 2026-07-10."""
    if not aws_account_id or not license_arn or not dimension or not BUNDLE_D_PRODUCT_CODE:
        logger.warning("Skipping Bundle D usage report — missing account/license_arn/dimension/product_code")
        return
    try:
        mp_client = boto3.client("meteringmarketplace", region_name="us-east-1")
        mp_client.batch_meter_usage(
            UsageRecords=[{
                "Timestamp": datetime.now(timezone.utc),
                "CustomerAWSAccountId": aws_account_id,
                "LicenseArn": license_arn,
                "Dimension": dimension,
                "Quantity": 1,
            }],
        )
        logger.info("Bundle D usage reported account=%s dimension=%s", aws_account_id, dimension)
    except Exception as exc:
        logger.warning("Bundle D usage reporting failed (non-fatal) account=%s dimension=%s error=%s",
                       aws_account_id, dimension, exc)


def _record_stripe_meter_event(stripe_customer_id: str, path: str) -> None:
    """Post a usage event to Stripe Billing Meter. Fire-and-forget — never raises.

    Mirrors relayshield_api.py's version exactly (duplicated, not imported —
    same isolation rationale as the rest of this file). Rewritten 2026-08-04
    from one meter per endpoint to a single aggregate meter carrying the call's
    price in CENTS as payload[value], billed against a $0.01-per-unit price.

    The reason is in relayshield_api.py's copy: Stripe Checkout rejects more
    than 20 recurring prices, and per-endpoint prices had passed that ceiling,
    breaking developer signup outright. Keep the two copies in step — this
    Lambda's two endpoints are on the same customer subscription as the rest.
    """
    cents = PRICE_CENTS.get(path, 0)
    if not cents:
        logger.warning("no price for %s — skipping meter event rather than billing 0", path)
        return
    try:
        secret_key = _stripe_secret_key()
        identifier = f"{stripe_customer_id}-{uuid.uuid4().hex}"
        payload    = urllib.parse.urlencode({
            "event_name":                  STRIPE_USAGE_METER_EVENT,
            "payload[value]":              str(cents),
            "payload[stripe_customer_id]": stripe_customer_id,
            "payload[path]":               path,
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
            logger.info("stripe meter event recorded customer=%s path=%s cents=%d status=%d",
                        stripe_customer_id, path, cents, resp.status)
    except Exception as exc:
        logger.warning("stripe meter event failed (non-fatal) customer=%s path=%s error=%s",
                       stripe_customer_id, path, exc)


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
    # important given the corpus is 3.2M+ items (confirmed 2026-07-20).
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

def _bazaar_body_ext(input_example: dict, input_schema: dict, output_example: dict) -> dict:
    """V1 x402 discovery metadata for a POST endpoint.

    Corrected 2026-07-12 — this had been fundamentally wrong, not just
    incomplete. We send x402Version:1 payloads (confirmed our whole wire
    format matches PaymentRequirementsV1 in Coinbase's own SDK exactly:
    maxAmountRequired, a plain string `resource`, legacy network IDs). Read
    Coinbase's own reference extraction code for V1
    (x402/extensions/bazaar/v1/facilitator.py, extract_discovery_info_v1)
    and confirmed: for a V1 payload, Bazaar-compatible facilitators read
    discovery metadata from a top-level `outputSchema` field on each accept
    entry (sibling to scheme/network/payTo/etc.) — NOT from
    `extensions.bazaar`. That extension-wrapper shape is the V2 convention;
    we were declaring V2-shaped metadata inside a V1 payload, in a location
    the V1 extraction path never even looks at. This is very likely the true
    root cause of non-indexing on BOTH PayAI's and CDP's Bazaar (this is the
    open x402 spec's convention, not CDP-specific) — the 2026-07-11 fix
    (adding a missing `schema` key) was real and necessary but landed in the
    wrong top-level field, so it couldn't have worked alone.

    Exact required shape per extract_discovery_info_v1/_has_v1_output_schema:
        outputSchema: {
          input: {type: "http", method, discoverable: true, bodyType, body},
          output: <example object, used directly as the example — NOT
                   nested under a further "example" key>
        }
    "body" is one of several field names the extractor recognizes
    (bodyFields/body_fields/bodyParams/body/data/properties) — used here
    since it matches our example structure most directly.

    input_schema (added 2026-07-16, matching relayshield_api.py's fuller
    version): stored under `_input_schema`, used only by the V2 path below —
    not part of the V1 outputSchema wire shape."""
    return {
        "input": {
            "type":         "http",
            "method":       "POST",
            "discoverable": True,
            "bodyType":     "json",
            "body":         input_example,
        },
        "output":        output_example,
        "_input_schema": input_schema,
    }


def _schema_from_example(value):
    """Infer a JSON Schema from an example value.

    Deliberately permissive: types only, never `required`, and arrays are
    described by their first element. The point is to give a discovery client
    (and x402scan's auditor, which reports SCHEMA_OUTPUT_MISSING for a bare
    `{"type": "object"}`) a real description of the response, without turning
    an example into a contract we would then have to keep exactly true for
    every field on every call. Enrichment fields that come back null on some
    calls are typed from whatever the example happens to show, so a strict
    schema here would fail validation on perfectly good responses.
    """
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if value is None:
        # Not "null": the field is nullable, and in this API null means
        # "not determined" rather than a distinct type.
        return {}
    if isinstance(value, list):
        return {"type": "array", "items": _schema_from_example(value[0]) if value else {}}
    if isinstance(value, dict):
        return {"type": "object",
                "properties": {k: _schema_from_example(v) for k, v in value.items()}}
    return {}


def _bazaar_output_schema(output_example):
    """Schema for `info.output`, which is the WRAPPER `{type, example}`.

    Same trap that produced the CDP facilitator rejection documented in
    _v2_bazaar_extension: the SDK validates `info` against `schema`, so this
    must describe `{"type": "json", "example": ...}` and NOT the response
    payload directly. The payload's own inferred schema nests under `example`.
    """
    return {
        "type": "object",
        "properties": {
            "type": {"type": "string"},
            "example": _schema_from_example(output_example),
        },
    }


def _v2_bazaar_extension(bazaar_ext: dict) -> dict:
    """V2 extensions.bazaar shape — verified 2026-07-14 against the actual
    SDK source (python/x402/extensions/bazaar/types.py, BodyDiscoveryExtension).

    Fixed 2026-07-16 to match the same correction applied in
    relayshield_api.py: the SDK's validate_discovery_extension runs
    jsonschema.validate(instance=info, schema=schema), so `schema` describes
    the whole `info` object ({input, output}), and `_input_schema` (which
    describes the request BODY) must nest under
    schema.properties.input.properties.body — not directly under
    schema.properties.input, which would validate the {type, method,
    bodyType, body} wrapper against the body's own schema and fail (this
    file's X402_V2_ENABLED_PATHS is empty so the old generic-object fallback
    never actually failed here, but it also carried no real schema info)."""
    return {
        "info": {
            "input":  bazaar_ext["input"],
            "output": {"type": "json", "example": bazaar_ext["output"]},
        },
        "schema": {
            "type": "object",
            "properties": {
                "input": {
                    "type": "object",
                    "properties": {
                        "body": bazaar_ext.get("_input_schema") or {"type": "object"},
                    },
                    "required": ["body"],
                },
                "output": _bazaar_output_schema(bazaar_ext["output"]),
            },
            "required": ["input"],
        },
    }


BAZAAR_EXTENSIONS: dict[str, dict] = {
    "/v1/payg/mcp-registry-risk": _bazaar_body_ext(
        input_example={"server_url": "https://example-mcp-server.com"},
        input_schema={
            "type": "object",
            "properties": {"server_url": {"type": "string", "description": "URL of the MCP server to assess for registry/supply-chain risk"}},
            "required": ["server_url"],
        },
        output_example={"ok": True, "data": {"verdict": "LOW", "findings": []}},
    ),
    "/v1/payg/prompt-injection-breach": _bazaar_body_ext(
        input_example={"email": "user@example.com"},
        input_schema={
            "type": "object",
            "properties": {"email": {"type": "string", "description": "Email address to check for agent-session compromise from a prompt-injection-driven breach"}},
            "required": ["email"],
        },
        output_example={"ok": True, "data": {"found": False, "session_count": 0}},
    ),
}

# Rich descriptions for CDP Bazaar semantic search — same fix as
# relayshield_api.py's PAYG_DESCRIPTIONS, added 2026-07-17.
PAYG_DESCRIPTIONS: dict[str, str] = {
    "/v1/payg/mcp-registry-risk": (
        "Assess an MCP server URL for supply-chain and registry risk before your agent connects "
        "to it or grants it tool-calling access — flags unverified publishers, known-malicious "
        "servers, and other trust signals. Call before an autonomous agent adds a new MCP server "
        "to its toolset."
    ),
    "/v1/payg/prompt-injection-breach": (
        "Check whether an email address tied to an AI agent session has an active stolen "
        "session or credential exposure that could enable a prompt-injection-driven account "
        "takeover. Call to audit whether an agent's own session integrity has already been "
        "compromised upstream, not just what the agent is being asked to do."
    ),
}


def _build_payment_requirements(path: str, price_units: int) -> dict:
    resource    = f"{API_BASE_URL}{path}"
    description = PAYG_DESCRIPTIONS.get(
        path, f"RelayShield {path.split('/')[-1].replace('-', ' ')} check"
    )
    bazaar_ext  = BAZAAR_EXTENSIONS.get(path)

    if path in X402_V2_ENABLED_PATHS:
        base_entry: dict = {
            "scheme":            "exact",
            "network":           BASE_CHAIN_ID_V2,
            "amount":            str(price_units),
            "payTo":             X402_PAYTO_ADDRESS,
            "maxTimeoutSeconds": 300,
            "asset":             USDC_BASE_ADDRESS,
            "extra":             {"name": "USD Coin", "version": "2"},
        }
        accepts = [base_entry]
        if SOL_PAYTO_ADDRESS:
            accepts.append({
                "scheme":            "exact",
                "network":           SOL_CHAIN_ID,
                "amount":            str(price_units),
                "payTo":             SOL_PAYTO_ADDRESS,
                "maxTimeoutSeconds": 60,
                "asset":             USDC_SOL_ADDRESS,
                "extra":             {"feePayer": SOL_FEE_PAYER},
            })
        result: dict = {
            "x402Version": 2,
            "resource": {"url": resource, "description": description, "mimeType": "application/json"},
            "accepts": accepts,
        }
        if bazaar_ext:
            result["extensions"] = {"bazaar": _v2_bazaar_extension(bazaar_ext)}
        return result

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
        base_entry["outputSchema"] = bazaar_ext
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
            sol_entry["outputSchema"] = bazaar_ext
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


def _payload_network(parsed: dict) -> str:
    """V1 payloads carry `network` at the top level. V2 payloads nest it
    under `accepted.network` instead — mirrors relayshield_api.py's fix."""
    if parsed.get("network"):
        return parsed["network"]
    return (parsed.get("accepted") or {}).get("network", "")


def _detect_payment_chain(x_payment: str) -> str:
    try:
        decoded = base64.b64decode(x_payment + "==")
        parsed = json.loads(decoded)
        if _payload_network(parsed).startswith("solana"):
            return "solana"
        return "evm"
    except Exception:
        try:
            parsed = json.loads(x_payment)
            if _payload_network(parsed).startswith("solana"):
                return "solana"
        except Exception:
            pass
        return "evm"


def _parse_cdp_private_key(key_data: str):
    """Parses a CDP API key secret in either PEM (EC/ES256) or base64
    (Ed25519/EdDSA) format. Mirrors coinbase/cdp-sdk's Python
    _parse_private_key exactly — CDP's key-creation UI defaults to Ed25519
    but still offers ECDSA, so both formats must be supported."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec, ed25519

    if "\\n" in key_data:
        key_data = key_data.replace("\\n", "\n")

    try:
        key = serialization.load_pem_private_key(key_data.encode(), password=None)
        if isinstance(key, ec.EllipticCurvePrivateKey):
            return key, "ES256"
    except Exception:
        pass

    try:
        decoded = base64.b64decode(key_data)
        if len(decoded) == 64:
            return ed25519.Ed25519PrivateKey.from_private_bytes(decoded[:32]), "EdDSA"
    except Exception:
        pass

    raise ValueError("CDP_API_KEY_SECRET must be either a PEM EC key or a base64 Ed25519 key")


def _cdp_jwt_bearer_token(request_path: str) -> str | None:
    """Builds a short-lived JWT for CDP's REST API auth (ES256 or EdDSA,
    auto-detected from CDP_API_KEY_SECRET's format). Mirrors Coinbase's own
    cdp-sdk (python/cdp/auth/utils/jwt.py generate_jwt) exactly: header
    {alg, kid, typ, nonce}, claims {sub, iss=cdp, nbf, exp, uris}. Not using
    the cdp-sdk package itself to keep this Lambda's dependency footprint to
    just pyjwt + cryptography (bundled via the relayshield-cdp-auth layer).
    Returns None (triggering PayAI fallback) if creds are missing or invalid."""
    if not CDP_API_KEY_ID or not CDP_API_KEY_SECRET:
        return None
    try:
        import jwt as pyjwt

        private_key, algorithm = _parse_cdp_private_key(CDP_API_KEY_SECRET)
        now = int(time.time())
        header = {
            "alg":   algorithm,
            "kid":   CDP_API_KEY_ID,
            "typ":   "JWT",
            "nonce": "".join(random.choices("0123456789", k=16)),
        }
        claims = {
            "sub": CDP_API_KEY_ID,
            "iss": "cdp",
            "nbf": now,
            "exp": now + 120,
            "uris": [f"POST {CDP_FACILITATOR_HOST}{request_path}"],
        }
        return pyjwt.encode(claims, private_key, algorithm=algorithm, headers=header)
    except Exception as exc:
        logger.error("CDP JWT generation failed, falling back to PayAI — error=%s", exc)
        return None


def _select_facilitator(verify_path: str, settle_path: str, fallback_url: str) -> tuple[str, dict, dict]:
    """Returns (facilitator_base_url, verify_headers, settle_headers). Prefers
    CDP when CDP_API_KEY_ID/CDP_API_KEY_SECRET are configured (see note above
    _cdp_jwt_bearer_token); falls back to the PayAI facilitator otherwise."""
    if CDP_API_KEY_ID and CDP_API_KEY_SECRET:
        verify_jwt = _cdp_jwt_bearer_token(verify_path)
        settle_jwt = _cdp_jwt_bearer_token(settle_path)
        if verify_jwt and settle_jwt:
            return (
                CDP_FACILITATOR_URL,
                {"Content-Type": "application/json", "Authorization": f"Bearer {verify_jwt}"},
                {"Content-Type": "application/json", "Authorization": f"Bearer {settle_jwt}"},
            )
    plain_headers = {"Content-Type": "application/json"}
    return fallback_url, plain_headers, plain_headers


def _verify_and_settle_x402_payment(x_payment: str, path: str) -> dict | None:
    """Verifies AND settles the x402 payment. Returns the settlement
    response dict on success (to be encoded into the PAYMENT-RESPONSE
    header), or None if verification or settlement failed.

    Found 2026-07-10: calling /verify alone does NOT move funds — it only
    checks the signed payload is well-formed and funded. /settle is the
    separate call that actually submits the transaction on-chain. This
    Lambda previously only called /verify, meaning every PAYG call ever
    delivered the paid service without collecting payment. Confirmed via
    x402 spec research and PayAI's own facilitator (a bare POST to
    /settle returns HTTP 400, not 404, confirming the endpoint is real
    and was never being called)."""
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
            return None

    is_v2 = path in X402_V2_ENABLED_PATHS
    base_network_id = BASE_CHAIN_ID_V2 if is_v2 else BASE_CHAIN_ID

    if chain == "solana":
        if not SOL_PAYTO_ADDRESS:
            logger.error("RELAYSHIELD_SOL_WALLET not set — cannot verify Solana x402 payment")
            return None
        chain_requirements = next(
            (a for a in requirements.get("accepts", []) if a.get("network") == SOL_CHAIN_ID), None,
        )
        if not chain_requirements:
            logger.error("No Solana accepts entry in requirements for path=%s", path)
            return None
    else:
        if not X402_PAYTO_ADDRESS:
            logger.error("RELAYSHIELD_X402_WALLET not set — cannot verify EVM x402 payment")
            return None
        chain_requirements = next(
            (a for a in requirements.get("accepts", []) if a.get("network") == base_network_id), requirements,
        )

    fallback_url = SOL_FACILITATOR_URL if chain == "solana" else X402_FACILITATOR_URL
    facilitator_base, verify_headers, settle_headers = _select_facilitator(
        "/platform/v2/x402/verify", "/platform/v2/x402/settle", fallback_url,
    )

    # First attempt (2026-07-16) at this fix injected a bare string as
    # "resource" onto payment_payload_dict — broke /verify outright in
    # relayshield_api.py's identical code, caught before /settle ran so no
    # funds moved, reverted immediately. Root cause of THAT failure,
    # confirmed against the actual x402 Python SDK schema source
    # (x402/schemas/payments.py — not guessed): PaymentPayload.resource is
    # a real, valid, OPTIONAL field, but it's a structured ResourceInfo
    # object (url/description/mimeType), not a bare string — and it's
    # explicitly V2-only. Mirrors the corrected fix applied there the same
    # day: reuses the exact ResourceInfo-shaped dict
    # _build_payment_requirements already builds at requirements["resource"]
    # for V2, rather than constructing a second copy.
    if is_v2 and requirements.get("resource"):
        payment_payload_dict["resource"] = requirements["resource"]

    request_body = json.dumps({
        "x402Version": 2 if is_v2 else 1, "paymentPayload": payment_payload_dict, "paymentRequirements": chain_requirements,
    }).encode("utf-8")

    # Step 1: verify — well-formed + funded check only, does not move funds.
    verify_url = f"{facilitator_base}/verify"
    req = urllib.request.Request(
        verify_url, data=request_body, headers=verify_headers, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if not result.get("isValid", False):
                logger.warning("x402 payment invalid — chain=%s reason=%s path=%s",
                               chain, result.get("invalidReason"), path)
                return None
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = "<unreadable>"
        logger.error("x402 verify HTTP %d — chain=%s path=%s body=%s", exc.code, chain, path, body)
        return None
    except Exception as exc:
        logger.error("x402 verify call failed — chain=%s path=%s error=%s", chain, path, exc)
        return None

    # Step 2: settle — actually submits the transaction on-chain and moves funds.
    settle_url = f"{facilitator_base}/settle"
    req = urllib.request.Request(
        settle_url, data=request_body, headers=settle_headers, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            settle_result = json.loads(resp.read())
            if not settle_result.get("success", False):
                logger.error("x402 settlement failed — chain=%s path=%s result=%s", chain, path, settle_result)
                return None
            logger.info("x402 payment settled — chain=%s path=%s tx=%s",
                        chain, path, settle_result.get("transaction"))
            return settle_result
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = "<unreadable>"
        logger.error("x402 settle HTTP %d — chain=%s path=%s body=%s", exc.code, chain, path, body)
        return None
    except Exception as exc:
        logger.error("x402 settle call failed — chain=%s path=%s error=%s", chain, path, exc)
        return None


PAYG_SETTLEMENTS_TABLE = "relayshield_payg_settlements"


def _log_payg_settlement(path: str, price_units: int, settlement: dict) -> None:
    """Records a settled PAYG payment for weekly revenue reporting. Never
    raises -- a logging failure must not break the paid response the
    customer already funded. Shared table with relayshield_api.py's own
    copy of this function -- both write here, isolation principle only
    applies to the endpoint handler logic, not this shared reporting sink."""
    try:
        table = dynamodb.Table(PAYG_SETTLEMENTS_TABLE)
        now   = datetime.now(timezone.utc)
        table.put_item(Item={
            "settlement_id": str(uuid.uuid4()),
            "timestamp":     now.isoformat(),
            "path":          path,
            "amount_usd":    Decimal(str(price_units / 1_000_000)),
            "network":       settlement.get("network", "unknown"),
            "tx_hash":       settlement.get("transaction", ""),
            "payer":         settlement.get("payer", ""),
            "ttl":           int(now.timestamp()) + 90 * 86400,
        })
    except Exception as exc:
        logger.warning("Failed to log PAYG settlement for path=%s: %s", path, exc)


def _log_hf_mcp_call(path: str, price_cents: int, rail: str = "unknown",
                     account_ref: str = "") -> None:
    """Tags a metered call as attributable to the relayshield-agentic-attack-surface
    HF Space, for the weekly metrics report (TODO.md item added 2026-07-15).
    Shares the PAYG settlements table rather than a new one -- only the
    source/consuming query differs. Never raises, same rationale as
    _log_payg_settlement.

    `rail` and `account_ref` added 2026-07-30. The row previously recorded only
    a dollar amount, and the weekly report added those up under the heading
    "Revenue". That is wrong whenever the caller did not actually pay: a TI
    subscriber has unlimited access and is billed nothing, and a key with no
    billing relationship at all is billed nothing, yet both wrote a full list
    price row. The first real row this produced was the AWS Marketplace
    auditor (awsmpsaastest@amazon.com) during the Bundle D audit, reported as
    $0.35 of "revenue" from a compliance test.

    Recording the rail makes the number interpretable:
      aws       -- metered via BatchMeterUsage, collected through AWS disbursement
      stripe    -- meter event recorded against a Stripe customer
      included  -- subscriber with unlimited access, genuinely $0
      unbilled  -- no billing relationship found, genuinely $0
    """
    try:
        table = dynamodb.Table(PAYG_SETTLEMENTS_TABLE)
        now   = datetime.now(timezone.utc)
        billed = rail in ("aws", "stripe")
        table.put_item(Item={
            "settlement_id": str(uuid.uuid4()),
            "timestamp":     now.isoformat(),
            "path":          path,
            # List price for the call. Only counts as revenue when billed is True.
            "amount_usd":    Decimal(str(price_cents)) / Decimal(100),
            "billed":        billed,
            "rail":          rail,
            "account_ref":   account_ref,
            "source":        "hf-mcp-space",
            "ttl":           int(now.timestamp()) + 90 * 86400,
        })
    except Exception as exc:
        logger.warning("Failed to log HF MCP call for path=%s: %s", path, exc)


def handle_payg_request(path: str, event: dict) -> dict:
    headers   = event.get("headers") or {}
    # V2 clients send the signed payload as PAYMENT-SIGNATURE, not X-PAYMENT
    # (mirrors the same fix in relayshield_api.py, 2026-07-14).
    x_payment = _header(headers, "PAYMENT-SIGNATURE") or _header(headers, "X-PAYMENT")

    if not x_payment:
        return _x402_payment_required(path)

    settlement = _verify_and_settle_x402_payment(x_payment, path)
    if settlement is None:
        return _err("Invalid or expired payment proof, or settlement failed — pay again and retry.", 402)
    _log_payg_settlement(path, PAYG_PRICE_UNITS.get(path, 0), settlement)

    payg_routes = {
        "/v1/payg/mcp-registry-risk":       handle_mcp_registry_risk,
        "/v1/payg/prompt-injection-breach": handle_prompt_injection_breach,
    }
    handler = payg_routes.get(path)
    if not handler:
        return _err(f"unknown PAYG endpoint: {path}", 404)

    result = handler(_body(event))
    # Include the settlement receipt per x402 spec (PAYMENT-RESPONSE header,
    # base64-encoded JSON) so compliant client libraries get a verifiable
    # receipt instead of crashing on a missing header.
    encoded_settlement = base64.b64encode(json.dumps(settlement).encode()).decode()
    result.setdefault("headers", {})
    result["headers"]["PAYMENT-RESPONSE"] = encoded_settlement
    result["headers"]["Access-Control-Expose-Headers"] = "PAYMENT-RESPONSE"
    return result


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

    headers = event.get("headers") or {}
    api_key = _header(headers, "X-API-Key") or _header(headers, "X-RS-API-KEY")
    key_record = _verify_rs_api_key(api_key)
    if not key_record:
        return _err("Invalid or missing API key", 401)

    if key_record.get("source") in DEMO_QUOTA_SOURCES and not _check_demo_quota(key_record):
        return _err(
            "Shared demo key's daily call quota reached. Get your own free-tier key: "
            "https://api.relayshield.net/developers?source=hf-smolagents",
            429,
        )

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
        # Track which rail actually took the money, so the weekly report can
        # tell collected revenue apart from list price on a free call.
        rail, account_ref = "unbilled", ""
        if key_record.get("bundle_d_access") and key_record.get("aws_account_id") and key_record.get("aws_license_arn"):
            _report_marketplace_usage(
                key_record["aws_account_id"], key_record["aws_license_arn"], AWS_DIMENSION_NAMES.get(path, "")
            )
            rail, account_ref = "aws", key_record["aws_account_id"]
        else:
            has_subscription = bool(key_record.get("stripe_subscription_id")) or bool(key_record.get("intel_plan_tier"))
            if not has_subscription:
                stripe_customer_id = key_record.get("stripe_customer_id", "")
                if stripe_customer_id:
                    _record_stripe_meter_event(stripe_customer_id, path)
                    rail, account_ref = "stripe", stripe_customer_id
            else:
                # Unlimited under an existing subscription: genuinely $0 for
                # this call, not revenue.
                rail = "included"

        source = headers.get("X-RS-Source") or headers.get("x-rs-source")
        if source == "hf-mcp-space":
            _log_hf_mcp_call(path, PRICE_CENTS.get(path, 0), rail, account_ref)

    return result
