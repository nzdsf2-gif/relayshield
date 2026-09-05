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

WHAT IS VERIFIED, AND WHAT IS NOT (updated 2026-09-04)
-------------------------------------------------------
The first version of this file shipped two Stripe wire shapes DERIVED from prose
and labelled as such. docs.stripe.com is still blocked from this container, but
two better sources are not: `mppx`, Stripe's own reference implementation, is on
the npm registry, and `github.com/tempoxyz/payment-auth-spec`, the IETF draft it
cites, is on raw.githubusercontent.com. Reading the implementation settled every
open question, and one of the two derived shapes was wrong in three places.

VERIFIED against mppx 0.9.2 and cited at each function:
  * the API version, 2026-07-29.preview -- the derived 2026-05-27 was wrong
  * the PaymentIntent transaction_verification shape, wrong in three keys
  * deposit addresses are LISTED before being created
  * the unit conversion, which the reference implementation computes identically
  * the MPP challenge: it is a WWW-Authenticate header under the `Payment` auth
    scheme with an HMAC-bound id, NOT a JSON block in the response body

NOT IMPLEMENTED, and the endpoint says so by staying quiet about it: redeeming
an MPP credential. We can issue a bound challenge and verify our own binding on
what comes back, but a Shared Payment Token has to be redeemed through Stripe,
and SPTs are in private preview on top of the crypto gate. So
RELAYSHIELD_MPP_CHALLENGE defaults to "off" and the 402 advertises only x402,
which is the rail we can actually honour. Advertising a payment method we would
then reject spends the agent's authorisation on a route that cannot complete.

`npx mppx@latest validate <url>` is the objective test of MPP compliance and it
runs on the Mac. It is the acceptance criterion, not our own reading.
"""

import base64
import hashlib
import hmac
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
# Kept for the fallback rail's own wording. The Stripe-side network is
# MPP_NETWORK, which may differ (Stripe also records on tempo and solana).
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

# VERIFIED 2026-09-04 against mppx 0.9.2, Stripe's own reference implementation:
# dist/stripe/internal/constants.js sets stripePreviewVersion = '2026-07-29.preview'
# and says it is REQUIRED for shared_payment_granted_token, since SPTs are in
# private preview. The 2026-05-27 date this file shipped with yesterday was
# derived from a blog reading and was wrong.
#
# A preview version is still a MOVING TARGET. If calls that used to work start
# failing on parameter names, check whether mppx has bumped this before
# concluding an entitlement changed.
STRIPE_PREVIEW_VERSION = "2026-07-29.preview"

# Networks Stripe records crypto payments on, with the token decimals each uses.
# Verified from mppx dist/stripe/server/internal/record-payment.js NETWORK_CONFIG,
# which lists exactly these three, all at 6 decimals. Base is ours: it is where
# the 28 live endpoints already settle.
STRIPE_NETWORKS = {"tempo": 6, "base": 6, "solana": 6}
MPP_NETWORK = os.environ.get("RELAYSHIELD_MPP_NETWORK", "base").strip().lower()

# Marks a PaymentIntent as a machine payment. Verified: mppx sets exactly
# {machine_payment: 'true'} on every recorded crypto payment, so a Stripe-side
# query for machine revenue finds ours alongside anyone else's.
MACHINE_PAYMENT_METADATA = {"machine_payment": "true"}

# The Stripe business profile id (profile_...), used as `networkId` in an MPP
# challenge. Read from GET /v2/network/business_profiles/me when not pinned.
STRIPE_PROFILE_ID = os.environ.get("STRIPE_PROFILE_ID", "").strip()

# Whether to advertise an MPP challenge alongside the x402 one. OFF by default,
# and the reason is in build_mpp_challenge: we can ISSUE a compliant challenge
# and verify our own binding on it, but we cannot yet REDEEM a Shared Payment
# Token credential. Advertising a payment method we cannot honour is worse than
# not advertising it.
MPP_CHALLENGE_ENABLED = os.environ.get("RELAYSHIELD_MPP_CHALLENGE", "off").strip().lower() == "on"

SETTLEMENTS_TABLE = "relayshield_payg_settlements"

# "auto" prefers Stripe and falls back. "facilitator" pins the existing rail and
# never calls Stripe at all, which is the safe setting to deploy with before the
# account is enabled. "stripe" refuses to serve on the fallback, for a test that
# wants a hard failure rather than a quiet degrade.
MPP_RAIL = os.environ.get("RELAYSHIELD_MPP_RAIL", "auto").strip().lower()

# Secrets are cached for the life of the execution environment, which meant a
# rotated key was not picked up until a container recycled -- minutes to hours.
# Worse, _record_stripe_meter_event swallows its own errors, so a revoked key
# produced SILENT UNDER-BILLING rather than an alarm. A TTL fixes that at source
# and removes the need for anyone to hold lambda:UpdateFunctionConfiguration
# just to force a recycle. Added 2026-09-05.
_SECRET_TTL = 300
_secret_cache: dict[str, tuple[float, str]] = {}

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
    """Cached with a TTL. A rotated secret is picked up within _SECRET_TTL with
    no redeploy and no forced recycle. On a refresh failure the last known good
    value is returned rather than raising: a Secrets Manager blip must not take
    the endpoint down, and the old value is almost always still valid."""
    cached = _secret_cache.get(secret_name)
    if cached and (time.time() - cached[0]) < _SECRET_TTL:
        return cached[1]
    try:
        raw = secrets_client.get_secret_value(SecretId=secret_name)["SecretString"].strip()
    except Exception:
        if cached:
            logger.warning("secret refresh failed for %s, using the cached value", secret_name)
            return cached[1]
        raise
    _secret_cache[secret_name] = (time.time(), raw)
    return raw


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


def stripe_deposit_address_params(network: str = "") -> dict:
    """Parameters for POST /v1/crypto/deposit_addresses.

    VERIFIED 2026-09-04 against mppx 0.9.2
    (dist/stripe/server/internal/deposit-address.js): the create call takes
    exactly {network}. The same file also shows the read path, which this file
    got wrong yesterday -- see _stripe_deposit_address.
    """
    return {"network": network or MPP_NETWORK}


def _stripe_deposit_address(key: str, network: str = "") -> dict | None:
    """Finds an existing Stripe crypto deposit address for `network`, and only
    creates one if there is none.

    LIST FIRST. Verified from mppx's findOrCreateDepositAddress, which does
    `GET /v1/crypto/deposit_addresses?network=X&limit=1` and reuses data[0]
    before it will POST. Yesterday's version here POSTed unconditionally, which
    mints a fresh address every time the in-process cache expires -- on Lambda
    that is every cold start, and it scatters machine revenue across a growing
    set of addresses for no reason.

    Returns {"address", "id", "network"} or None when the account is not enabled
    for the product, which is the expected answer today. None is not an error
    condition: it is the signal to quote the existing wallet in the 402 instead.
    """
    network = network or MPP_NETWORK
    cached = _deposit_cache.get(network)
    if cached and (time.time() - cached[0]) < _DEPOSIT_ADDRESS_TTL:
        return cached[1]

    status, body = _stripe_request(
        f"/v1/crypto/deposit_addresses?network={urllib.parse.quote(network)}&limit=1",
        None, key,
    )
    record = None
    if status == 200 and (body.get("data") or []):
        first = body["data"][0]
        record = {"address": first.get("address", ""), "id": first.get("id", ""),
                  "network": network}
    elif status == 200:
        status, body = _stripe_request(
            "/v1/crypto/deposit_addresses", stripe_deposit_address_params(network), key
        )
        if status == 200:
            record = {"address": body.get("address", ""), "id": body.get("id", ""),
                      "network": network}

    if not record or not record["address"]:
        # 401/403/404 all mean the same thing from outside: not granted. Log the
        # message verbatim, because that exact text is the thing worth putting in
        # front of Stripe -- "the console returns the access request" is a
        # support ticket, "this endpoint returns this" reaches an engineer.
        logger.warning(
            "Stripe deposit address unavailable — HTTP %s network=%s message=%s",
            status, network, (body.get("error") or {}).get("message", ""),
        )
        return None

    _deposit_cache[network] = (time.time(), record)
    logger.info("Stripe deposit address ready — network=%s id=%s", network, record["id"])
    return record


def _stripe_profile_id(key: str) -> str:
    """The Stripe business profile id (profile_...), which MPP uses as networkId.

    Stripe's quickstart says to create a profile in the Dashboard and read it
    from GET /v2/network/business_profiles/me. Pin it with STRIPE_PROFILE_ID to
    skip the call. Returns "" when unavailable, which disables the MPP challenge
    rather than emitting one with a field missing.
    """
    if STRIPE_PROFILE_ID:
        return STRIPE_PROFILE_ID
    cached = _deposit_cache.get("__profile__")
    if cached and (time.time() - cached[0]) < _DEPOSIT_ADDRESS_TTL:
        return cached[1].get("id", "")
    status, body = _stripe_request("/v2/network/business_profiles/me", None, key)
    if status != 200:
        logger.warning("Stripe business profile unavailable — HTTP %s message=%s",
                       status, (body.get("error") or {}).get("message", ""))
        return ""
    pid = body.get("id", "")
    _deposit_cache["__profile__"] = (time.time(), {"id": pid})
    return pid


def stripe_payment_intent_params(cents: int, network: str, tx_hash: str,
                                 currency: str = "usd",
                                 metadata: dict | None = None) -> dict:
    """Parameters for POST /v1/payment_intents recording an already-settled
    on-chain payment in transaction_verification mode.

    VERIFIED 2026-09-04 against mppx 0.9.2, Stripe's own reference
    implementation (dist/stripe/server/internal/record-payment.js). The shape
    this file shipped with yesterday was DERIVED from a prose reading and was
    wrong in three ways, every one of which would have produced a rejected
    parameter rather than a wrong charge:

      * `mode` is its own key under `crypto`. It was missing entirely.
      * The sub-object is `transaction_verification_options`, not
        `transaction_verification`.
      * `payment_method_types: ["crypto"]` is required alongside
        `payment_method_data[type]`. It was missing.

    Also added from the same source: metadata {machine_payment: "true"}, which
    is how machine revenue is queried on the Stripe side, and which mppx sets on
    every recorded crypto payment.

    Form encoding, not JSON: Stripe's REST API takes bracketed keys, so the
    nesting mppx expresses as objects is flattened here. urlencode(doseq=True)
    handles the list.
    """
    params = {
        "amount":   cents,
        "currency": currency,
        "confirm":  "true",
        "payment_method_data[type]":   "crypto",
        "payment_method_types[]":      ["crypto"],
        "payment_method_options[crypto][mode]": "transaction_verification",
        "payment_method_options[crypto][transaction_verification_options][network]":          network,
        "payment_method_options[crypto][transaction_verification_options][transaction_hash]": tx_hash,
    }
    for k, v in {**MACHINE_PAYMENT_METADATA, **(metadata or {})}.items():
        params[f"metadata[{k}]"] = str(v)
    return params


def _record_stripe_payment_intent(key: str, cents: int, network: str, tx_hash: str,
                                  metadata: dict) -> str:
    """Records the settled transaction. Returns the PaymentIntent id, or "".

    The transaction hash is the idempotency key, bare, matching mppx's
    `idempotencyKey: reference`. A settlement retried by the facilitator, or a
    client that pays once and calls twice with the same proof, must not produce
    two PaymentIntents for one movement of money."""
    status, body = _stripe_request(
        "/v1/payment_intents",
        stripe_payment_intent_params(cents, network, tx_hash, metadata=metadata),
        key,
        idempotency_key=tx_hash,   # mppx uses the bare reference; match it
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


# ---------------------------------------------------------------------------
# The MPP challenge, implemented from the protocol rather than guessed at.
#
# Yesterday this file emitted an invented `mpp` JSON block in the 402 body and
# labelled it "unverified". It was not merely unverified, it was structurally
# wrong: MPP does not put its challenge in the response body at all. It uses the
# `Payment` HTTP authentication scheme -- a WWW-Authenticate header, per
# RFC 7235 -- and the credential comes back in Authorization.
#
# Everything below is verified against mppx 0.9.2 (dist/Challenge.js,
# dist/PaymentRequest.js, dist/Constants.js, dist/stripe/Methods.js), which is
# Stripe's own reference implementation, and against
# github.com/tempoxyz/payment-auth-spec, the IETF draft those files cite. Both
# are reachable from this container even though docs.stripe.com is not.
# ---------------------------------------------------------------------------

def _b64url(raw: bytes) -> str:
    """Base64url, unpadded. What mppx's Base64.fromBytes({url:true, pad:false})
    produces, and what every field in a challenge is encoded with."""
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _canonical_json(obj: dict) -> str:
    """RFC 8785 (JCS) canonical JSON, which is what mppx's Json.canonicalize
    emits before base64url-encoding a payment request.

    Sorted keys, no whitespace, and no unicode escaping of non-ASCII. For the
    ASCII string/integer payloads this module builds, Python's json.dumps with
    these arguments is byte-identical to JCS. It is NOT a general JCS
    implementation -- floats in particular serialise differently -- so do not
    reach for this with arbitrary data.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def mpp_payment_request(price_units: int, network_id: str,
                        payment_method_types: list[str] | None = None,
                        currency: str = "usd") -> dict:
    """The `request` object of a Stripe-method charge challenge.

    Shape from mppx dist/stripe/Methods.js: after its zod transform, `amount` is
    atomic units as a STRING, and networkId plus paymentMethodTypes move under
    `methodDetails`. networkId is the Stripe business profile id, not a chain.
    """
    return {
        "amount":   str(price_units),
        "currency": currency,
        "methodDetails": {
            "networkId":           network_id,
            "paymentMethodTypes":  payment_method_types or ["crypto"],
        },
    }


def mpp_challenge_id(realm: str, method: str, intent: str, request: dict,
                     secret: str, expires: str = "", digest: str = "",
                     header: str = "", opaque: str = "") -> str:
    """The HMAC-bound challenge id, per §5.1.2.1.1 of the spec.

    Seven fixed positional slots, pipe-delimited, absent fields as empty strings
    so the slot count never moves:

        realm | method | intent | serialize(request) | expires | digest | opaque

    with the credential header inserted immediately before the final opaque slot
    when, and only when, a non-default one is advertised.

    Binding matters. The id covers every field, so a client cannot alter the
    amount, the recipient or the expiry and still present an id we would accept:
    any change produces a different HMAC. Yesterday's version had no binding at
    all, which is the difference between a payment challenge and a suggestion.
    """
    values = [realm, method, intent, _b64url(_canonical_json(request).encode()),
              expires, digest]
    if header and header.lower() != "authorization":
        values.append(header)
    values.append(opaque)
    mac = hmac.new(secret.encode(), "|".join(values).encode(), hashlib.sha256).digest()
    return _b64url(mac)


def _auth_param(name: str, value: str) -> str:
    """One quoted auth-param. Header values must be ByteStrings, so anything
    above Latin-1 is escaped rather than allowed to break the header -- mppx
    does the same, and an em dash in a description is the realistic way it
    happens here."""
    if "\r" in value or "\n" in value:
        raise ValueError("invalid quoted-string value")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = "".join(c if ord(c) <= 0xFF else "\\u%04x" % ord(c) for c in escaped)
    return f'{name}="{escaped}"'


def build_mpp_challenge(realm: str, network_id: str, secret: str,
                        price_units: int = PRICE_UNITS,
                        description: str = "") -> str:
    """The full `WWW-Authenticate: Payment ...` value.

    Returns the header VALUE, not a dict, because that is what MPP is: an HTTP
    authentication scheme. Parameter order follows mppx's serialize() so a
    byte-comparison against its output is meaningful.

    NOT ADVERTISED BY DEFAULT. RELAYSHIELD_MPP_CHALLENGE gates it, and it is off
    until the credential side exists. We can issue a bound challenge and verify
    our own binding on what comes back, but redeeming a Shared Payment Token is
    a Stripe call this module does not yet make, and SPTs are in private preview
    besides. A 402 that advertises a payment method we would then reject is
    worse for the agent than one that never offered it -- it spends the agent's
    authorisation on a route that cannot complete.
    """
    request = mpp_payment_request(price_units, network_id)
    cid = mpp_challenge_id(realm, "stripe", "charge", request, secret)
    parts = [
        _auth_param("id", cid),
        _auth_param("realm", realm),
        _auth_param("method", "stripe"),
        _auth_param("intent", "charge"),
        _auth_param("request", _b64url(_canonical_json(request).encode())),
    ]
    if description:
        parts.append(_auth_param("description", description))
    return "Payment " + ", ".join(parts)


def mpp_secret_key(stripe_key: str) -> str:
    """The server secret that binds our challenges.

    Stripe's quickstart derives one as an HMAC over the account's secret key.
    The exact label it hashes is cut off in the published snippet, and it does
    not matter for correctness: this secret is ours alone, used to sign
    challenges we issue and to verify what comes back to us. Stripe never checks
    it. What matters is that it is stable across Lambda instances, secret, and
    not the raw API key -- so a leaked challenge id cannot be walked back to the
    credential that reads our account.
    """
    return _b64url(hmac.new(stripe_key.encode(), b"mppx.challenge", hashlib.sha256).digest())


def _mpp_challenge_header() -> str:
    """The WWW-Authenticate value, or "" when MPP is not being advertised.

    Never raises and never blocks the 402: if the profile id or the key cannot
    be read, the x402 challenge still goes out on its own. An agent that can pay
    us today must not lose that ability because a preview product is unreachable.
    """
    if not MPP_CHALLENGE_ENABLED:
        return ""
    try:
        key = _stripe_secret_key()
        network_id = _stripe_profile_id(key)
        if not network_id:
            return ""
        realm = urllib.parse.urlparse(API_BASE_URL).netloc or "api.relayshield.net"
        return build_mpp_challenge(
            realm, network_id, mpp_secret_key(key),
            description="RelayShield MCP registry risk check",
        )
    except Exception as exc:
        logger.warning("MPP challenge not built: %s", exc)
        return ""


def _payment_required(pay_to: str, rail: str) -> dict:
    requirements = build_payment_requirements(pay_to)
    encoded      = base64.b64encode(json.dumps(requirements).encode()).decode()
    headers = {
        "Content-Type":                  "application/json",
        "PAYMENT-REQUIRED":              encoded,
        "Access-Control-Expose-Headers": "PAYMENT-REQUIRED",
    }
    body = {
        "ok":    False,
        "error": "Payment required",
        "price": f"${PRICE_UNITS / 1_000_000:.2f} USDC ({MPP_NETWORK})",
        "rail":  rail,
        "x402":  requirements,
    }

    challenge = _mpp_challenge_header()
    if challenge:
        # RFC 7235: a 402 offering more than one scheme lists them all here.
        # x402 does not use WWW-Authenticate, so there is nothing to merge with.
        headers["WWW-Authenticate"] = challenge
        headers["Access-Control-Expose-Headers"] = "PAYMENT-REQUIRED, WWW-Authenticate"
        body["mpp"] = {"scheme": "Payment", "header": "WWW-Authenticate"}

    return {"statusCode": 402, "headers": headers, "body": json.dumps(body)}


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
            "network":        settlement.get("network", MPP_NETWORK),
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
            "stripe_network": MPP_NETWORK,
            "mpp_challenge":  "advertised" if MPP_CHALLENGE_ENABLED else "not advertised",
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
                    settlement.get("network", MPP_NETWORK),
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
