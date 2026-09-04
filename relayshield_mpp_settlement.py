"""
RelayShield MPP settlement endpoint — machine payments on Stripe's rail.

ONE endpoint, deliberately:

    POST /v1/mpp/mcp-registry-risk    $0.35, settled through Stripe
    GET  /v1/mpp                      service descriptor and rail status

DEPLOY PATH
-----------
Lambda `relayshield-mpp-settlement`, its own function and its own API Gateway
routes. `tools/create_mpp_settlement_lambda.sh` creates both. It is NOT in
`deploy_lambdas.yml` yet and must not be added until that script has run and
the function exists in 239677749008 -- mapping a function the deployer cannot
find turns the first push red for a reason that has nothing to do with the code.

WHY A NEW FILE RATHER THAN A BRANCH IN relayshield_agentic_api.py
-----------------------------------------------------------------
`relayshield_agentic_api.py` carries UNRECONCILED live drift as of 2026-09-03:
the deployed artifact holds a branded API_BASE_URL and a Bundle D Stripe billing
branch that main has never seen, recovered onto
`claude/recovered-live-relayshield-agentic-api` and not yet merged. Adding code
there and giving it a deploy path is the 2026-08-17 mistake exactly: the next
repo-sourced deploy would delete the live-only billing branch with no error
anywhere. A new file has no live counterpart, so it cannot drift from one.

It also matches the isolation mandate that file already states for itself: new,
unproven payment logic gets its own package so a bug in it cannot regress the
28 endpoints that are collecting money today.

WHAT "STRIPE'S RAIL" ACTUALLY CHANGES
-------------------------------------
Nothing about the protocol. The agent still gets a 402, still signs an EIP-3009
authorisation, still retries with proof. What changes is WHERE THE MONEY LANDS:

  today      agent -> USDC on Base -> PayAI/CDP facilitator -> our Coinbase wallet
  this file  agent -> USDC on Base -> facilitator -> a Stripe crypto deposit
             address, recorded as a PaymentIntent, settling into the Stripe
             balance next to the subscriptions, with the same reporting,
             payouts, refunds and tax treatment.

See `miniapp_discovery_and_stripe_choice.md` section 7 for the sourcing.

THE RAIL IS NOT ENABLED ON THIS ACCOUNT YET, AND THIS FILE ASSUMES THAT
-----------------------------------------------------------------------
Stripe crypto reads `Ineligible` on acct_1TGqqsL2dcjOeFiY as a staged-rollout
gate. `tools/stripe_machine_payments_probe.py` is the read-only check that says
so in the account's own words. So every Stripe call here is BEST EFFORT and
falls back to the existing wallet:

  * cannot mint a deposit address -> the 402 quotes the existing payTo wallet
    and the endpoint keeps working on the rail that already collects money.
  * cannot record the PaymentIntent -> the caller still gets what they paid for,
    and the settlement row is written with `stripe_record_failed` so the
    reconciliation is a query rather than an archaeology exercise.

An endpoint that 500s because a preview product is not switched on is worse
than no endpoint. This one degrades to today's behaviour and says which rail it
used, in the response and in the row.
"""

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb       = boto3.resource("dynamodb")
secrets_client = boto3.client("secretsmanager")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MPP_PATH   = "/v1/mpp/mcp-registry-risk"
PRICE_UNITS = 350000          # $0.35 in USDC atomic units (6 decimals)

# Mirrors relayshield_agentic_api.py. Same wallets, same facilitators: the
# fallback rail has to be the rail that is already working, not a second one.
X402_PAYTO_ADDRESS = os.environ.get("RELAYSHIELD_X402_WALLET", "")
USDC_BASE_ADDRESS  = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
BASE_CHAIN_ID_V2   = "eip155:8453"
BASE_NETWORK_NAME  = "base"

X402_FACILITATOR_URL = "https://facilitator.payai.network"
CDP_API_KEY_ID       = os.environ.get("CDP_API_KEY_ID", "")
CDP_FACILITATOR_URL  = "https://api.cdp.coinbase.com/platform/v2/x402"

API_BASE_URL = os.environ.get(
    "RELAYSHIELD_API_BASE_URL",
    "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod",
)

STRIPE_SECRET_NAME = "relayshield/stripe_secret_key"
STRIPE_API         = "https://api.stripe.com"

# The preview API version Stripe's machine-payments documentation uses. Pinned
# on purpose and duplicated in tools/stripe_machine_payments_probe.py: a
# preview version is a MOVING TARGET. If calls that used to work start failing
# on parameter names, check whether this date has moved before concluding an
# entitlement changed.
STRIPE_PREVIEW_VERSION = "2026-05-27.preview"

SETTLEMENTS_TABLE = "relayshield_payg_settlements"

# "auto" prefers Stripe and falls back. "facilitator" pins the existing rail and
# never calls Stripe at all, which is the safe setting to deploy with before the
# account is enabled. "stripe" refuses to serve on the fallback, for a test that
# wants a hard failure rather than a quiet degrade.
MPP_RAIL = os.environ.get("RELAYSHIELD_MPP_RAIL", "auto").strip().lower()

_secret_cache: dict[str, str] = {}

# A deposit address is minted per challenge and cached briefly, because a 402 is
# cheap and Stripe's is not. Attribution does not depend on the address being
# unique per payer: the on-chain transaction hash is what ties a settlement to a
# payment, and it is what goes on the PaymentIntent.
_DEPOSIT_ADDRESS_TTL = 600
_deposit_cache: dict[str, tuple[float, dict]] = {}


# ---------------------------------------------------------------------------
# Response helpers, duplicated rather than imported, same isolation rationale
# as relayshield_agentic_api.py states for itself.
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


def _header(headers: dict, name: str) -> str:
    """Case-insensitive header lookup. urllib normalises header names with
    str.capitalize(), so "PAYMENT-SIGNATURE" arrives as "Payment-signature";
    matching on an exact spelling cost every urllib caller a 401 on 2026-07-31."""
    if not headers:
        return ""
    target = name.lower()
    for k, v in headers.items():
        if k.lower() == target:
            return v or ""
    return ""


def _body(event: dict) -> dict:
    try:
        raw = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode("utf-8")
        return json.loads(raw)
    except Exception:
        return {}


def _get_secret(secret_name: str) -> str:
    if secret_name not in _secret_cache:
        raw = secrets_client.get_secret_value(SecretId=secret_name)["SecretString"].strip()
        _secret_cache[secret_name] = raw
    return _secret_cache[secret_name]


def _stripe_secret_key() -> str:
    raw = _get_secret(STRIPE_SECRET_NAME)
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
    return parsed.get("stripe_secret_key") or parsed.get("STRIPE_SECRET_KEY") or raw


# ---------------------------------------------------------------------------
# The conversion. USDC carries 6 decimals; Stripe wants an integer minor unit.
# ---------------------------------------------------------------------------

def usdc_units_to_cents(units: int) -> int:
    """350000 atomic USDC units -> 35 cents.

    Rounds HALF UP, and may legitimately return 0 for a sub-cent amount. It does
    NOT floor a non-zero amount up to one cent: this number is a record of money
    that has already moved, and inflating $0.004 into $0.01 puts a wrong figure
    into Stripe's own reporting, which is the one place the number has to be
    right. The caller skips the PaymentIntent when this returns 0 and flags the
    row instead, so the residue is visible rather than invented.
    """
    if units <= 0:
        return 0
    return int(
        (Decimal(units) / Decimal(10 ** 4)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


# ---------------------------------------------------------------------------
# Stripe calls. Every one of them is best effort and returns None on failure.
# ---------------------------------------------------------------------------

def _stripe_request(path: str, params: dict | None, key: str,
                    idempotency_key: str = "") -> tuple[int, dict]:
    """Form-encoded Stripe call. Returns (status, body). Never raises, never
    logs the key, never logs the full response body on success."""
    data = None
    method = "GET"
    if params is not None:
        method = "POST"
        data = urllib.parse.urlencode(params, doseq=True).encode("utf-8")

    req = urllib.request.Request(f"{STRIPE_API}{path}", data=data, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Stripe-Version", STRIPE_PREVIEW_VERSION)
    if data is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    if idempotency_key:
        req.add_header("Idempotency-Key", idempotency_key)

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except Exception:
            return exc.code, {}
    except Exception as exc:
        return 0, {"error": {"message": str(exc)}}


def stripe_deposit_address_params(network: str = BASE_NETWORK_NAME) -> dict:
    """Parameters for POST /v1/crypto/deposit_addresses.

    Isolated in its own function so the wire shape is testable offline and
    correctable in one place. See the note on stripe_payment_intent_params
    about how these names were derived and how to settle them.
    """
    return {"network": network}


def _stripe_deposit_address(key: str, network: str = BASE_NETWORK_NAME) -> dict | None:
    """Mints (or reuses) a Stripe crypto deposit address for `network`.

    Returns {"address": ..., "id": ..., "network": ...} or None when the account
    is not enabled for the product, which is the expected answer today. A None
    here is not an error condition -- it is the signal to quote the existing
    wallet in the 402 instead."""
    cached = _deposit_cache.get(network)
    if cached and (time.time() - cached[0]) < _DEPOSIT_ADDRESS_TTL:
        return cached[1]

    status, body = _stripe_request(
        "/v1/crypto/deposit_addresses", stripe_deposit_address_params(network), key
    )
    if status != 200:
        # 401/403/404 all mean the same thing from outside: not granted. Log the
        # message verbatim, because that exact text is the thing worth putting in
        # front of Stripe -- "the console returns the access request" is a
        # support ticket, "this endpoint returns this" reaches an engineer.
        logger.warning(
            "Stripe deposit address unavailable — HTTP %s network=%s message=%s",
            status, network, (body.get("error") or {}).get("message", ""),
        )
        return None

    address = body.get("address") or (body.get("data") or [{}])[0].get("address", "")
    if not address:
        logger.warning("Stripe deposit address response carried no address — keys=%s",
                       sorted(body.keys()))
        return None

    record = {"address": address, "id": body.get("id", ""), "network": network}
    _deposit_cache[network] = (time.time(), record)
    logger.info("Stripe deposit address ready — network=%s id=%s", network, record["id"])
    return record


def stripe_payment_intent_params(cents: int, network: str, tx_hash: str,
                                 currency: str = "usd",
                                 metadata: dict | None = None) -> dict:
    """Parameters for POST /v1/payment_intents recording an already-settled
    on-chain payment in transaction_verification mode.

    ⚠ THE PARAMETER NAMES HERE ARE DERIVED, NOT VERIFIED. `docs.stripe.com` is
    blocked from the build container, so this shape comes from the reading in
    `miniapp_discovery_and_stripe_choice.md` section 7 of Stripe's published
    pages, not from the API reference. It is isolated in one function, with no
    branching, precisely so that correcting it is a one-line change.

    The check that settles it is `tools/mpp_settlement_selftest.py`, which posts
    exactly this dict against a TEST key and prints Stripe's own parameter
    errors. Run that before believing any of these names.
    """
    params = {
        "amount":   cents,
        "currency": currency,
        "confirm":  "true",
        "payment_method_data[type]": "crypto",
        "payment_method_options[crypto][transaction_verification][network]":          network,
        "payment_method_options[crypto][transaction_verification][transaction_hash]": tx_hash,
    }
    for k, v in (metadata or {}).items():
        params[f"metadata[{k}]"] = str(v)
    return params


def _record_stripe_payment_intent(key: str, cents: int, network: str, tx_hash: str,
                                  metadata: dict) -> str:
    """Records the settled transaction. Returns the PaymentIntent id, or "".

    The transaction hash is the idempotency key. A settlement retried by the
    facilitator, or a client that pays once and calls twice with the same proof,
    must not produce two PaymentIntents for one movement of money."""
    status, body = _stripe_request(
        "/v1/payment_intents",
        stripe_payment_intent_params(cents, network, tx_hash, metadata=metadata),
        key,
        idempotency_key=f"mpp-{tx_hash}",
    )
    if status != 200:
        logger.error(
            "Stripe PaymentIntent NOT recorded — HTTP %s tx=%s cents=%d code=%s message=%s",
            status, tx_hash, cents,
            (body.get("error") or {}).get("code", ""),
            (body.get("error") or {}).get("message", ""),
        )
        return ""
    pi_id = body.get("id", "")
    logger.info("Stripe PaymentIntent recorded — id=%s cents=%d tx=%s", pi_id, cents, tx_hash)
    return pi_id


# ---------------------------------------------------------------------------
# The 402 challenge.
# ---------------------------------------------------------------------------

def build_payment_requirements(pay_to: str, price_units: int = PRICE_UNITS,
                               path: str = MPP_PATH) -> dict:
    """x402 v2 requirements. Identical in shape to what the 28 live endpoints
    emit -- only `payTo` differs, and that is the whole point: an agent that can
    already pay RelayShield does not need to learn anything new to pay it on
    Stripe's rail."""
    return {
        "x402Version": 2,
        "resource": {
            "url":         f"{API_BASE_URL}{path}",
            "description": (
                "Risk assessment for an MCP server registry entry: typosquat distance "
                "against known-good registry names, domain registration age, and "
                "indicator-corpus matches."
            ),
            "mimeType": "application/json",
        },
        "accepts": [{
            "scheme":            "exact",
            "network":           BASE_CHAIN_ID_V2,
            "amount":            str(price_units),
            "payTo":             pay_to,
            "maxTimeoutSeconds": 300,
            "asset":             USDC_BASE_ADDRESS,
            "extra":             {"name": "USD Coin", "version": "2"},
        }],
    }


def build_mpp_challenge(pay_to: str, price_units: int = PRICE_UNITS,
                        path: str = MPP_PATH) -> dict:
    """The MPP half of the 402: Challenge, in MPP's Challenge/Credential/Receipt
    flow.

    ⚠ UNVERIFIED AGAINST THE SPEC, for the same reason as the PaymentIntent
    shape: the MPP specification is not reachable from the build container. This
    is assembled from the protocol description in
    `miniapp_discovery_and_stripe_choice.md` section 7 and is advisory.

    The `x402` block in the same response is the authoritative one and is what
    any client should pay against today. This block is emitted alongside it so
    an MPP-native agent has something to read, and so the field names are in one
    reviewable place when the spec can be checked. It is deliberately additive:
    removing it changes nothing for an x402 client.
    """
    return {
        "version":  "unverified",
        "amount":   {"value": str(price_units), "currency": "USDC", "decimals": 6},
        "accepts":  ["stablecoin"],
        "resource": f"{API_BASE_URL}{path}",
        "network":  BASE_CHAIN_ID_V2,
        "payTo":    pay_to,
        "note": (
            "Advisory. The x402 block in this response is authoritative. See "
            "build_mpp_challenge in relayshield_mpp_settlement.py."
        ),
    }


def _payment_required(pay_to: str, rail: str) -> dict:
    requirements = build_payment_requirements(pay_to)
    encoded      = base64.b64encode(json.dumps(requirements).encode()).decode()
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
            "price": f"${PRICE_UNITS / 1_000_000:.2f} USDC (Base)",
            "rail":  rail,
            "x402":  requirements,
            "mpp":   build_mpp_challenge(pay_to),
        }),
    }


# ---------------------------------------------------------------------------
# Settlement, through the same facilitators the live endpoints already use.
# ---------------------------------------------------------------------------

def _facilitator_base() -> str:
    return CDP_FACILITATOR_URL if CDP_API_KEY_ID else X402_FACILITATOR_URL


def _verify_and_settle(x_payment: str, requirements: dict) -> dict | None:
    """Verify then settle. Two calls, not one: /verify only checks the payload is
    well-formed and funded, and calling it alone delivers the service without
    collecting the money. That was live for weeks in 2026-07 before it was found,
    which is why this comment is here and not a docstring line."""
    try:
        payload = json.loads(base64.b64decode(x_payment + "=="))
    except Exception:
        try:
            payload = json.loads(x_payment)
        except Exception:
            logger.error("Could not decode the payment payload")
            return None

    if requirements.get("resource"):
        payload["resource"] = requirements["resource"]

    accepts = requirements.get("accepts") or [{}]
    request_body = json.dumps({
        "x402Version":         2,
        "paymentPayload":      payload,
        "paymentRequirements": accepts[0],
    }).encode("utf-8")

    base = _facilitator_base()
    headers = {"Content-Type": "application/json"}

    for step, timeout, success_key in (("verify", 15, "isValid"), ("settle", 30, "success")):
        req = urllib.request.Request(f"{base}/{step}", data=request_body,
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = "<unreadable>"
            logger.error("x402 %s HTTP %d — body=%s", step, exc.code, detail)
            return None
        except Exception as exc:
            logger.error("x402 %s call failed — %s", step, exc)
            return None

        if not result.get(success_key, False):
            logger.warning("x402 %s rejected — result=%s", step, result)
            return None
        if step == "settle":
            logger.info("x402 settled — tx=%s", result.get("transaction"))
            return result
    return None


def _log_settlement(rail: str, settlement: dict, cents: int,
                    payment_intent: str, note: str = "") -> None:
    """Writes the settlement row. Never raises: the caller has already been
    charged and is owed a response, and a reporting failure must not turn a
    collected payment into a 500.

    `rail` and `note` are the reconciliation handles. A row with rail="stripe"
    and an empty payment_intent is money that moved on-chain and did not reach
    Stripe's ledger, and that is a query rather than a discovery."""
    try:
        table = dynamodb.Table(SETTLEMENTS_TABLE)
        now   = datetime.now(timezone.utc)
        table.put_item(Item={
            "settlement_id":  str(uuid.uuid4()),
            "timestamp":      now.isoformat(),
            "path":           MPP_PATH,
            "amount_usd":     Decimal(str(PRICE_UNITS / 1_000_000)),
            "amount_cents":   cents,
            "amount_units":   PRICE_UNITS,
            "rail":           rail,
            "network":        settlement.get("network", BASE_NETWORK_NAME),
            "tx_hash":        settlement.get("transaction", ""),
            "payer":          settlement.get("payer", ""),
            "payment_intent": payment_intent,
            "note":           note,
            "ttl":            int(now.timestamp()) + 90 * 86400,
        })
    except Exception as exc:
        logger.warning("Failed to log MPP settlement: %s", exc)


# ---------------------------------------------------------------------------
# The resource itself.
# ---------------------------------------------------------------------------

def _assess(params: dict) -> dict:
    """Delegates to the Bundle D implementation rather than carrying a fourth
    copy of it.

    The import is inside the function on purpose. It keeps module import cheap
    and probe-safe, and `deploy_lambdas.yml`'s resolve_deps matches
    `^[[:space:]]*(import|from) relayshield_`, so an indented import is still
    picked up and the module is still packaged. Verified against that grep, not
    assumed.

    Deliberately one-directional: this module depends on the detector, the
    detector does not depend on this module, so a bug here cannot reach the
    endpoints that are already collecting money.
    """
    try:
        import relayshield_agentic_api as agentic
    except Exception as exc:                                   # pragma: no cover
        logger.error("Bundle D detector unavailable: %s", exc)
        return {
            "statusCode": 503,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "ok": False,
                "error": "Risk engine unavailable. The payment settled and is refundable.",
            }),
        }
    return agentic.handle_mcp_registry_risk(params)


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------

def _rail_and_payto() -> tuple[str, str, str]:
    """Decides which rail this request runs on. Returns (rail, pay_to, reason).

    rail is "stripe" or "facilitator". pay_to is empty only when neither is
    usable, which is a misconfiguration and a 503, not a silent free call."""
    if MPP_RAIL == "facilitator":
        return "facilitator", X402_PAYTO_ADDRESS, "pinned by RELAYSHIELD_MPP_RAIL"

    try:
        deposit = _stripe_deposit_address(_stripe_secret_key())
    except Exception as exc:
        logger.warning("Stripe rail unusable: %s", exc)
        deposit = None

    if deposit:
        return "stripe", deposit["address"], "stripe crypto deposit address"
    if MPP_RAIL == "stripe":
        return "stripe", "", "stripe rail pinned but not enabled on this account"
    return "facilitator", X402_PAYTO_ADDRESS, "stripe not enabled, fell back to the live wallet"


def lambda_handler(event: dict, context) -> dict:
    path   = event.get("path", "")
    method = event.get("httpMethod", "")

    # The deployer's import probe sends {"source": "ci.import-probe"} with no
    # path and no method. It falls through to the 404 below, which is a real
    # response and all the probe asserts. No early return is needed.
    logger.info("MPP request — method=%s path=%s rail=%s", method, path, MPP_RAIL)

    if method in ("GET", "HEAD") and path in ("/v1/mpp", "/v1/mpp/"):
        return _ok({
            "service":  "RelayShield MPP settlement",
            "endpoint": MPP_PATH,
            "price":    f"${PRICE_UNITS / 1_000_000:.2f} USDC",
            "network":  BASE_CHAIN_ID_V2,
            "rail":     MPP_RAIL,
            "note": (
                "Stripe-settled machine payments. Falls back to the existing "
                "facilitator wallet while the account is not enabled for crypto."
            ),
        })

    if path != MPP_PATH:
        return _err("Not found", 404)
    if method != "POST":
        return _err(f"{MPP_PATH} only accepts POST requests", 405)

    rail, pay_to, reason = _rail_and_payto()
    if not pay_to:
        logger.error("No usable payTo — %s", reason)
        return _err("Payment rail unavailable", 503)

    headers   = event.get("headers") or {}
    x_payment = _header(headers, "PAYMENT-SIGNATURE") or _header(headers, "X-PAYMENT")
    if not x_payment:
        return _payment_required(pay_to, rail)

    requirements = build_payment_requirements(pay_to)
    settlement   = _verify_and_settle(x_payment, requirements)
    if settlement is None:
        return _err("Invalid or expired payment proof, or settlement failed — pay again and retry.", 402)

    cents          = usdc_units_to_cents(PRICE_UNITS)
    payment_intent = ""
    note           = reason

    if rail == "stripe":
        if cents <= 0:
            note = "sub-cent settlement, not recorded in Stripe"
            logger.warning("MPP settlement below one cent — units=%d tx=%s",
                           PRICE_UNITS, settlement.get("transaction", ""))
        else:
            try:
                payment_intent = _record_stripe_payment_intent(
                    _stripe_secret_key(), cents,
                    settlement.get("network", BASE_NETWORK_NAME),
                    settlement.get("transaction", ""),
                    {"path": MPP_PATH, "payer": settlement.get("payer", ""),
                     "usdc_units": str(PRICE_UNITS)},
                )
            except Exception as exc:
                logger.error("Stripe recording raised: %s", exc)
            if not payment_intent:
                note = "stripe_record_failed"

    _log_settlement(rail, settlement, cents, payment_intent, note)

    result = _assess(_body(event))
    result.setdefault("headers", {})
    result["headers"]["PAYMENT-RESPONSE"] = base64.b64encode(
        json.dumps(settlement).encode()
    ).decode()
    result["headers"]["X-RelayShield-Rail"] = rail
    result["headers"]["Access-Control-Expose-Headers"] = "PAYMENT-RESPONSE, X-RelayShield-Rail"
    return result
