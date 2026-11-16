#!/usr/bin/env python3
"""RelayShield Stripe license issuance: Stripe purchase to license key.

Wires a Stripe purchase to license key generation for the MCP Proxy
Firewall appliance. A customer buys a license through Stripe
Checkout; Stripe sends a checkout.session.completed webhook; this
Lambda verifies the webhook signature, generates a signed license
key, stores the issued license, and emails the key to the customer.
A refund or a cancelled subscription revokes the license.

Flow
----
1. The console (or a Stripe Payment Link) creates a Checkout
   Session for an appliance license. The session MUST carry this
   metadata (the contract this Lambda reads):
       tenant_id:  the licensed tenant/org id (the billing entity)
       plan:       trial, msp, sme, oem, or distributor
       calls:      screened-call allowance per month (int, optional)
       days:       license length in days (int, e.g. 30 for a trial,
                   365 for an annual plan)
   The customer's email comes from the Checkout Session
   (customer_details.email). A trial Checkout Session is created
   only for a tenant Andrew approved; this Lambda does not re-check
   approval, because the approval decision is made when the session
   is created, not at webhook time.
2. Stripe POSTs the webhook to this Lambda (API Gateway route
   POST /v1/license/stripe-webhook, raw body, Stripe-Signature
   header). The signature is verified with HMAC-SHA256 against the
   webhook secret, using only hashlib and hmac (no stripe library).
3. On checkout.session.completed: the Lambda loads the license
   signing private key from Secrets Manager
   (relayshield/license_signing_key, JSON with private_key_hex and
   kid), issues a signed RS1 license key, stores the issued license
   in DynamoDB table relayshield_licenses (the key itself is
   KMS-encrypted, following the API's _kms_encrypt pattern), and
   emails the key to the customer via SES with activation
   instructions.
4. On customer.subscription.deleted or charge.refunded: the Lambda
   writes a revocation record to relayshield_license_revocations
   for the tenant (revoked_kids, or revoked_all when the whole
   subscription is gone), so the license service answers revoked
   and the appliance stops at its next online check.

Secrets and tables (env vars, set at deploy time)
-------------------------------------------------
    STRIPE_WEBHOOK_SECRET_NAME  Secrets Manager name for the Stripe
                                webhook secret (default
                                relayshield/stripe_webhook_secret)
    LICENSE_SIGNING_KEY_NAME    Secrets Manager name for the signing
                                key (default relayshield/license_signing_key)
    LICENSES_TABLE              DynamoDB table for issued licenses
                                (default relayshield_licenses)
    LICENSE_REVOCATIONS_TABLE   DynamoDB table for revocations
                                (default relayshield_license_revocations)
    LICENSE_KMS_KEY_ID          KMS key id for encrypting the stored
                                license key (default relayshield/license-kms)
    LICENSE_SENDER_EMAIL        SES sender (default licenses@relayshield.net)
    LICENSE_SERVICE_URL         base URL for the license service
                                (default https://api.relayshield.net)

Deployment: standalone Lambda (boto3, DynamoDB, Secrets Manager,
KMS, SES), following the RelayShield breach monitor Lambda pattern.
Wire it to API Gateway as POST /v1/license/stripe-webhook on
api.relayshield.net. Deploy with the "Deploy Changed Lambdas to
AWS" workflow from main, on Andrew's separate go. Do NOT create
live Stripe objects from this file; the Stripe products, prices,
and Checkout Sessions are created in the live Stripe Dashboard
(or the console Worker) and only the webhook is handled here.

The Ed25519 functions below are copied from mcp_proxy/license.py
(Step 4 licensing) so this Lambda deploys as a single-file zip with
no local cross-file imports (the relayshield-deploy skill
convention). Keep the two in sync; the test suite cross-checks
them. No em dashes in user-facing copy.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# boto3 is available in the Lambda runtime. It is not installed in
# the Muse VM, so the import is lazy: the pure logic (signature
# verification, event routing, key issuance) is testable without
# it, and the Lambda path raises a clear error when boto3 is absent.
try:
    import boto3
    secrets_client = boto3.client("secretsmanager")
    dynamodb = boto3.resource("dynamodb")
    kms_client = boto3.client("kms")
    ses_client = boto3.client("ses")
except ImportError:  # pragma: no cover - local test only
    boto3 = None
    secrets_client = None
    dynamodb = None
    kms_client = None
    ses_client = None

STRIPE_WEBHOOK_SECRET_NAME = os.environ.get(
    "STRIPE_WEBHOOK_SECRET_NAME", "relayshield/stripe_webhook_secret")
LICENSE_SIGNING_KEY_NAME = os.environ.get(
    "LICENSE_SIGNING_KEY_NAME", "relayshield/license_signing_key")
LICENSES_TABLE = os.environ.get(
    "LICENSES_TABLE", "relayshield_licenses")
LICENSE_REVOCATIONS_TABLE = os.environ.get(
    "LICENSE_REVOCATIONS_TABLE", "relayshield_license_revocations")
LICENSE_KMS_KEY_ID = os.environ.get(
    "LICENSE_KMS_KEY_ID", "relayshield/license-kms")
LICENSE_SENDER_EMAIL = os.environ.get(
    "LICENSE_SENDER_EMAIL", "licenses@relayshield.net")
LICENSE_SERVICE_URL = os.environ.get(
    "LICENSE_SERVICE_URL", "https://api.relayshield.net")

KNOWN_PLANS = ("trial", "msp", "sme", "oem", "distributor")
KEY_PREFIX = "RS1"
# Stripe allows a few minutes of clock skew on webhook signatures.
STRIPE_SIGNATURE_TOLERANCE_SECONDS = 300

# ---------------------------------------------------------------------------
# Pure-Python Ed25519 (RFC 8032), copied from mcp_proxy/license.py.
# Keep the two in sync.
# ---------------------------------------------------------------------------

_B = 256
_Q = (1 << 255) - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _Q - 2, _Q) % _Q
_I = pow(2, (_Q - 1) // 4, _Q)


def _ed25519_H(data):
    return hashlib.sha512(data).digest()


def _ed25519_xrecover(y):
    xx = (y * y - 1) * pow(_D * y * y + 1, _Q - 2, _Q) % _Q
    x = pow(xx, (_Q + 3) // 8, _Q)
    if (x * x - xx) % _Q != 0:
        x = (x * _I) % _Q
    if x % 2 != 0:
        x = _Q - x
    return x


_GY = 4 * pow(5, _Q - 2, _Q) % _Q
_GX = _ed25519_xrecover(_GY)
_G = (_GX, _GY, 1, (_GX * _GY) % _Q)


def _ed25519_edwards_add(p, q):
    (x1, y1, z1, t1) = p
    (x2, y2, z2, t2) = q
    a = ((y1 - x1) * (y2 - x2)) % _Q
    b = ((y1 + x1) * (y2 + x2)) % _Q
    c = 2 * _D * t1 * t2 % _Q
    d = 2 * z1 * z2 % _Q
    e = (b - a) % _Q
    f = (d - c) % _Q
    g = (d + c) % _Q
    h = (b + a) % _Q
    return (e * f % _Q, g * h % _Q, f * g % _Q, e * h % _Q)


def _ed25519_scalarmult(p, e):
    q = (0, 1, 1, 0)
    while e:
        if e & 1:
            q = _ed25519_edwards_add(q, p)
        p = _ed25519_edwards_add(p, p)
        e >>= 1
    return q


def _ed25519_encodepoint(p):
    (x, y, z, _) = p
    zi = pow(z, _Q - 2, _Q)
    x = (x * zi) % _Q
    y = (y * zi) % _Q
    bits = bin(y)[2:].zfill(256)[::-1]
    bits = list(bits)
    bits[255] = "1" if x & 1 else "0"
    bits = "".join(bits[::-1])
    return int(bits, 2).to_bytes(32, "little")


def _ed25519_sign(sk, msg):
    h = _ed25519_H(sk)
    a = int.from_bytes(h[:32], "little")
    a &= ~(1 | (1 << 255))
    a |= 1 << 254
    pk = _ed25519_encodepoint(_ed25519_scalarmult(_G, a))
    r = int.from_bytes(_ed25519_H(h[32:] + msg), "little") % _L
    big_r = _ed25519_encodepoint(_ed25519_scalarmult(_G, r))
    s = (r + int.from_bytes(
        _ed25519_H(big_r + pk + msg), "little") % _L * a) % _L
    return big_r + s.to_bytes(32, "little")


def _b64url_encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _canonical_payload_bytes(payload):
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def issue_license_key(signing_key, kid, tid, plan, exp, calls=None,
                      iat=None):
    """Issue an RS1 license key. Same format as mcp_proxy/license.py.
    """
    if plan not in KNOWN_PLANS:
        raise ValueError("unknown plan: %r" % (plan,))
    payload = {
        "v": 1,
        "kid": kid,
        "tid": tid,
        "plan": plan,
        "exp": int(exp),
        "calls": calls,
        "iat": int(iat if iat is not None else time.time()),
    }
    payload_bytes = _canonical_payload_bytes(payload)
    signature = _ed25519_sign(signing_key, payload_bytes)
    return "%s.%s.%s" % (
        KEY_PREFIX,
        _b64url_encode(payload_bytes),
        _b64url_encode(signature),
    )


# ---------------------------------------------------------------------------
# Stripe webhook signature verification (no stripe library)
# ---------------------------------------------------------------------------

def verify_stripe_signature(payload_bytes, signature_header,
                            webhook_secret, now=None,
                            tolerance=STRIPE_SIGNATURE_TOLERANCE_SECONDS):
    """Verify a Stripe webhook signature header.

    Stripe sends: Stripe-Signature: t=<timestamp>,v1=<hmac>
    The HMAC is SHA256 over "<timestamp>.<payload>" with the
    webhook secret. Returns True when the signature is valid and
    the timestamp is within tolerance (prevents replay). Returns
    False for a missing or malformed header, a bad HMAC, or a
    timestamp outside tolerance. Uses hmac.compare_digest so the
    comparison is constant-time.
    """
    if not signature_header or not webhook_secret:
        return False
    now = int(now if now is not None else time.time())
    parts = {}
    for item in signature_header.split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            parts.setdefault(k.strip(), []).append(v.strip())
    timestamps = parts.get("t", [])
    signatures = parts.get("v1", [])
    if not timestamps or not signatures:
        return False
    try:
        ts = int(timestamps[0])
    except ValueError:
        return False
    if abs(now - ts) > tolerance:
        return False
    signed = ("%d." % ts).encode("utf-8") + payload_bytes
    expected = hmac.new(
        webhook_secret.encode("utf-8"), signed,
        hashlib.sha256).hexdigest()
    return any(
        hmac.compare_digest(expected, sig) for sig in signatures)


# ---------------------------------------------------------------------------
# Checkout session parsing
# ---------------------------------------------------------------------------

def parse_checkout_session(event_data):
    """Extract the license fields from a checkout.session.completed
    event. Returns a dict with tenant_id, plan, calls, days, email,
    and stripe_session_id, or (None, error) when the session is
    missing a required field. The metadata contract is: tenant_id,
    plan, calls (optional), days. The email comes from
    customer_details.email.
    """
    session = event_data.get("object") or {}
    metadata = session.get("metadata") or {}
    tenant_id = (metadata.get("tenant_id") or "").strip()
    plan = (metadata.get("plan") or "").strip()
    email = ((session.get("customer_details") or {}).get("email")
             or "").strip().lower()
    if not tenant_id:
        return None, "checkout session has no tenant_id metadata"
    if plan not in KNOWN_PLANS:
        return None, (
            "checkout session plan %r is not a known license plan"
            % plan)
    if not email:
        return None, "checkout session has no customer email"
    try:
        days = int(metadata.get("days") or 0)
    except (TypeError, ValueError):
        return None, "checkout session days metadata is not an int"
    if days <= 0:
        return None, "checkout session days metadata must be positive"
    calls = None
    if metadata.get("calls") not in (None, ""):
        try:
            calls = int(metadata["calls"])
        except (TypeError, ValueError):
            return None, "checkout session calls metadata is not an int"
    return {
        "tenant_id": tenant_id,
        "plan": plan,
        "calls": calls,
        "days": days,
        "email": email,
        "stripe_session_id": session.get("id") or "",
        "stripe_customer_id": session.get("customer") or "",
    }, None


# ---------------------------------------------------------------------------
# AWS helpers (Secrets Manager, KMS, DynamoDB, SES)
# ---------------------------------------------------------------------------

def _require_aws():
    if boto3 is None:
        raise RuntimeError(
            "boto3 is not available; run in Lambda, not locally")


def get_webhook_secret():
    _require_aws()
    resp = secrets_client.get_secret_value(
        SecretId=STRIPE_WEBHOOK_SECRET_NAME)
    secret = resp.get("SecretString") or ""
    try:
        data = json.loads(secret)
        return data.get("secret") or data.get("webhook_secret") or secret
    except Exception:
        return secret.strip()


def get_signing_key():
    """Load the license signing private key from Secrets Manager.
    Returns (private key bytes, kid). The secret is JSON with
    private_key_hex and kid.
    """
    _require_aws()
    resp = secrets_client.get_secret_value(
        SecretId=LICENSE_SIGNING_KEY_NAME)
    data = json.loads(resp["SecretString"])
    sk = bytes.fromhex(data["private_key_hex"])
    if len(sk) != 32:
        raise ValueError("signing private key must be 32 bytes")
    return sk, data["kid"]


def kms_encrypt_key(license_key):
    """KMS-encrypt a license key for storage. Returns base64."""
    _require_aws()
    resp = kms_client.encrypt(
        KeyId=LICENSE_KMS_KEY_ID,
        Plaintext=license_key.encode("utf-8"))
    return base64.b64encode(resp["CiphertextBlob"]).decode("ascii")


def store_issued_license(record):
    """Store an issued license in DynamoDB. The key itself is
    stored KMS-encrypted, never in plaintext. The record is keyed
    by tid (partition) and license_id (sort).
    """
    _require_aws()
    table = dynamodb.Table(LICENSES_TABLE)
    table.put_item(Item={
        "tid": record["tenant_id"],
        "license_id": record["license_id"],
        "plan": record["plan"],
        "kid": record["kid"],
        "exp": record["exp"],
        "calls": record["calls"],
        "email": record["email"],
        "stripe_session_id": record["stripe_session_id"],
        "stripe_customer_id": record["stripe_customer_id"],
        "license_key_encrypted": kms_encrypt_key(record["license_key"]),
        "issued_at": record["issued_at"],
        "status": "active",
    })
    logger.info(
        "stored issued license %s for tenant %s (plan %s)",
        record["license_id"], record["tenant_id"], record["plan"])


def revoke_license(tid, kid=None, reason=""):
    """Write a revocation record for a tenant. When kid is given,
    only that kid is revoked; when kid is None, every key for the
    tenant is revoked. Used on refund and subscription cancel.
    """
    _require_aws()
    table = dynamodb.Table(LICENSE_REVOCATIONS_TABLE)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if kid is None:
        update = (
            "SET revoked_all = :t, updated_at = :u, "
            "revoked_reason = :r")
        values = {":t": True, ":u": now, ":r": reason}
    else:
        update = (
            "SET revoked_kids = list_append(if_not_exists("
            "revoked_kids, :empty), :kid), updated_at = :u, "
            "revoked_reason = :r")
        values = {
            ":empty": [], ":kid": [kid], ":u": now, ":r": reason,
        }
    table.update_item(
        Key={"tid": tid},
        UpdateExpression=update,
        ExpressionAttributeValues=values,
    )
    logger.info(
        "revoked license for tenant %s (kid=%s, reason=%s)",
        tid, kid, reason)


def email_license_key(email, license_key, plan, exp):
    """Email the license key to the customer with activation
    instructions. Uses SES. The key is the only credential in the
    email; the email tells the customer to paste it on the
    activation page or set it as RELAYSHIELD_LICENSE_KEY.
    """
    _require_aws()
    exp_date = time.strftime("%Y-%m-%d", time.gmtime(exp))
    body = (
        "Your RelayShield MCP Proxy Firewall license is ready.\n\n"
        "License key:\n%s\n\n"
        "Plan: %s\n"
        "Expires: %s\n\n"
        "To activate your appliance, paste this key on the "
        "activation page (port 8091) on first boot, or set it at "
        "deploy time as the RELAYSHIELD_LICENSE_KEY app variable. "
        "The gateway does not start until a valid license key is "
        "entered.\n\n"
        "Keep this key private. If you lose it, contact "
        "support@relayshield.net and RelayShield will re-issue it.\n\n"
        "RelayShield\n"
        "https://relayshield.net\n" % (
            license_key, plan, exp_date)
    )
    ses_client.send_email(
        Source=LICENSE_SENDER_EMAIL,
        Destination={"ToAddresses": [email]},
        Message={
            "Subject": {"Data": (
                "Your RelayShield MCP Proxy Firewall license key")},
            "Body": {"Text": {"Data": body}},
        },
    )
    logger.info("emailed license key to %s (plan %s)", email, plan)


# ---------------------------------------------------------------------------
# Event handling
# ---------------------------------------------------------------------------

def handle_checkout_completed(event_data):
    """Handle checkout.session.completed: issue the license key,
    store it, and email it. Returns (status_code, body dict).
    Idempotency: the license_id is the Stripe session id, so a
    duplicate webhook for the same session stores the same record
    and re-emails the same key rather than issuing a second key.
    A second key is never issued for the same session.
    """
    fields, error = parse_checkout_session(event_data)
    if error:
        logger.warning("checkout session rejected: %s", error)
        return 400, {"error": error}
    sk, kid = get_signing_key()
    now = int(time.time())
    exp = now + fields["days"] * 86400
    license_id = "stripe_%s" % (
        fields["stripe_session_id"] or "manual")
    license_key = issue_license_key(
        sk, kid=kid, tid=fields["tenant_id"], plan=fields["plan"],
        exp=exp, calls=fields["calls"], iat=now)
    record = {
        "license_id": license_id,
        "tenant_id": fields["tenant_id"],
        "plan": fields["plan"],
        "kid": kid,
        "exp": exp,
        "calls": fields["calls"],
        "email": fields["email"],
        "stripe_session_id": fields["stripe_session_id"],
        "stripe_customer_id": fields["stripe_customer_id"],
        "license_key": license_key,
        "issued_at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
    }
    store_issued_license(record)
    email_license_key(
        fields["email"], license_key, fields["plan"], exp)
    logger.info(
        "issued %s license for tenant %s (session %s)",
        fields["plan"], fields["tenant_id"],
        fields["stripe_session_id"])
    return 200, {"issued": True, "license_id": license_id,
                 "tenant_id": fields["tenant_id"],
                 "plan": fields["plan"]}


def handle_subscription_deleted(event_data):
    """Handle customer.subscription.deleted: revoke every license
    for the tenant. The tenant id comes from the subscription
    metadata (tenant_id), the same contract as checkout.
    """
    obj = event_data.get("object") or {}
    metadata = obj.get("metadata") or {}
    tenant_id = (metadata.get("tenant_id") or "").strip()
    if not tenant_id:
        logger.warning(
            "subscription.deleted without tenant_id metadata; "
            "cannot revoke")
        return 400, {"error": "subscription has no tenant_id metadata"}
    revoke_license(
        tenant_id, kid=None,
        reason="stripe subscription cancelled")
    return 200, {"revoked": True, "tenant_id": tenant_id}


def handle_charge_refunded(event_data):
    """Handle charge.refunded: revoke the license for the tenant.
    The tenant id comes from the charge metadata (tenant_id) when
    present; otherwise the payment intent metadata. When no tenant
    id is found, the refund is logged and no revocation is written,
    because revoking the wrong tenant would be worse than missing
    one (the manual revoke path in the issuer tool covers it).
    """
    obj = event_data.get("object") or {}
    metadata = obj.get("metadata") or {}
    tenant_id = (metadata.get("tenant_id") or "").strip()
    if not tenant_id:
        pi = obj.get("payment_intent") or {}
        if isinstance(pi, dict):
            tenant_id = (
                (pi.get("metadata") or {}).get("tenant_id") or ""
            ).strip()
    if not tenant_id:
        logger.warning(
            "charge.refunded without tenant_id metadata; no "
            "revocation written, use the issuer revoke command")
        return 200, {"revoked": False,
                     "note": "no tenant_id metadata"}
    revoke_license(
        tenant_id, kid=None, reason="stripe charge refunded")
    return 200, {"revoked": True, "tenant_id": tenant_id}


def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def lambda_handler(event, context):
    """API Gateway proxy integration entry point.

    POST /v1/license/stripe-webhook. The raw body is in event
    body (base64 when isBase64Encoded is true) and the signature
    is in the Stripe-Signature header. The signature is verified
    before anything else; an invalid signature is a 400 and the
    event is ignored. Recognised event types are
    checkout.session.completed, customer.subscription.deleted, and
    charge.refunded. Any other event type returns 200 with
    ignored=true, so Stripe does not retry it.
    """
    headers = event.get("headers") or {}
    sig_header = None
    for k, v in headers.items():
        if k.lower() == "stripe-signature":
            sig_header = v
            break
    raw_body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        payload_bytes = base64.b64decode(raw_body)
    else:
        payload_bytes = raw_body.encode("utf-8")
    try:
        webhook_secret = get_webhook_secret()
    except Exception as exc:
        logger.exception("cannot load Stripe webhook secret: %s", exc)
        return _response(500, {"error": "webhook secret unavailable"})
    if not verify_stripe_signature(
            payload_bytes, sig_header, webhook_secret):
        logger.warning("Stripe webhook signature invalid; ignoring")
        return _response(400, {"error": "invalid signature"})
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return _response(400, {"error": "invalid JSON"})
    event_type = payload.get("type") or ""
    event_data = payload.get("data") or {}
    logger.info("Stripe webhook event %s", event_type)
    try:
        if event_type == "checkout.session.completed":
            code, body = handle_checkout_completed(event_data)
        elif event_type == "customer.subscription.deleted":
            code, body = handle_subscription_deleted(event_data)
        elif event_type == "charge.refunded":
            code, body = handle_charge_refunded(event_data)
        else:
            return _response(200, {"ignored": True,
                                   "type": event_type})
    except Exception as exc:
        logger.exception("Stripe webhook handling failed: %s", exc)
        return _response(500, {"error": "webhook handling failed"})
    return _response(code, body)


if __name__ == "__main__":
    # Local smoke test: signature verification round trip only.
    # No AWS calls are made. Run the full test suite in
    # step4-stripe-license-tests-2026-11-09.py for coverage.
    import secrets as _secrets
    secret = "whsec_test"
    ts = int(time.time())
    payload = b'{"type": "checkout.session.completed"}'
    signed = ("%d." % ts).encode("utf-8") + payload
    sig = hmac.new(
        secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    header = "t=%d,v1=%s" % (ts, sig)
    print("valid signature verifies:",
          verify_stripe_signature(payload, header, secret))
    print("bad signature fails:",
          verify_stripe_signature(payload, header, "wrong"))
