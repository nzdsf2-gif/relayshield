"""
relayshield_aws_marketplace — AWS Marketplace SaaS Integration Lambda

Handles two entry points:

1. POST /marketplace/fulfillment (token in form-encoded body)
   Customer is redirected here after clicking Subscribe on AWS Marketplace.
   AWS's actual fulfillment redirect is a POST with x-amzn-marketplace-token
   in the request body — NOT a GET with a query string, despite what an
   earlier version of this comment assumed (confirmed against AWS's own
   SaaS integration guide after this caused repeated listing-audit
   failures). GET/HEAD are also accepted for a customer manually
   revisiting the URL, or an older-style audit probe.
   Resolves the registration token → gets CustomerIdentifier + ProductCode
   → creates a pending record and redirects to the developer portal.

2. SNS notification (invoked by subscription-notification topic)
   Handles subscribe-success, unsubscribe-pending, unsubscribe-success.
   On subscribe-success: provisions API key with intel_access=True, sends welcome email.
   On unsubscribe: deactivates the API key.

Product code: 5s4a96a1ui1a5efrom6udnm2g
SNS topic:    arn:aws:sns:us-east-1:287250355862:aws-mp-subscription-notification-5s4a96a1ui1a5efrom6udnm2g

Routing: Add GET/HEAD/POST /marketplace/fulfillment and POST /marketplace/sns to
API Gateway pointing to this Lambda.
"""

import json
import logging
import uuid
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

API_KEYS_TABLE   = "relayshield_api_keys"
USERS_TABLE      = "relayshield_users"
FROM_EMAIL       = "noreply@relayshield.net"
ADMIN_EMAIL      = "relayshieldadmin@gmail.com"
API_BASE_URL     = "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod"
PRODUCT_CODE     = "5s4a96a1ui1a5efrom6udnm2g"
DEVELOPERS_URL   = f"{API_BASE_URL}/developers"

# Dimension → plan tier mapping
DIMENSION_TIER = {
    "ti_starter":   "mp_499",
    "ti_unlimited": "mssp_999",
}

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
mp_client = boto3.client("meteringmarketplace", region_name="us-east-1")
ses      = boto3.client("ses", region_name="us-east-1")


# ---------------------------------------------------------------------------
# Token resolution
# ---------------------------------------------------------------------------

def _resolve_token(token: str) -> dict:
    """
    Call AWS Marketplace ResolveCustomer API to exchange the registration
    token for CustomerIdentifier and ProductCode.
    Returns dict with CustomerIdentifier, ProductCode, CustomerAWSAccountId.
    """
    try:
        resp = mp_client.resolve_customer(RegistrationToken=token)
        logger.info("Resolved token: customer=%s product=%s",
                    resp.get("CustomerIdentifier"), resp.get("ProductCode"))
        return resp
    except Exception as exc:
        logger.error("resolve_customer failed: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Entitlement check
# ---------------------------------------------------------------------------

def _get_entitlement(customer_id: str) -> dict | None:
    """
    Check AWS Marketplace Entitlement Service for active entitlements.
    Returns the first active entitlement dict or None.
    """
    try:
        ent_client = boto3.client("marketplace-entitlement", region_name="us-east-1")
        resp = ent_client.get_entitlements(
            ProductCode=PRODUCT_CODE,
            Filter={"CUSTOMER_IDENTIFIER": [customer_id]},
        )
        entitlements = resp.get("Entitlements", [])
        active = [e for e in entitlements if not e.get("ExpirationDate") or
                  e["ExpirationDate"] > datetime.now(timezone.utc)]
        return active[0] if active else None
    except Exception as exc:
        logger.error("get_entitlements failed customer=%s: %s", customer_id, exc)
        return None


# ---------------------------------------------------------------------------
# API key provisioning
# ---------------------------------------------------------------------------

def _provision_api_key(customer_id: str, email: str, dimension: str) -> str:
    """Issue a RelayShield API key for an AWS Marketplace customer."""
    tier       = DIMENSION_TIER.get(dimension, "mp_499")
    intel_plan = tier  # mp_499 = 10K calls cap, mssp_999 = unlimited
    api_key    = f"rs_live_{uuid.uuid4().hex}"

    dynamodb.Table(API_KEYS_TABLE).put_item(Item={
        "api_key":              api_key,
        "aws_customer_id":      customer_id,
        "aws_product_code":     PRODUCT_CODE,
        "aws_dimension":        dimension,
        "email":                email,
        "active":               True,
        "intel_access":         True,
        "intel_plan_tier":      intel_plan,
        "source":               "aws_marketplace",
        "created_at":           datetime.now(timezone.utc).isoformat(),
    })
    logger.info("API key provisioned customer=%s dimension=%s tier=%s", customer_id, dimension, tier)
    return api_key


def _deactivate_api_key(customer_id: str) -> None:
    """Deactivate all API keys for an AWS Marketplace customer."""
    table = dynamodb.Table(API_KEYS_TABLE)
    resp  = table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr("aws_customer_id").eq(customer_id)
    )
    for item in resp.get("Items", []):
        table.update_item(
            Key={"api_key": item["api_key"]},
            UpdateExpression="SET active = :f, deactivated_at = :ts",
            ExpressionAttributeValues={
                ":f":  False,
                ":ts": datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.info("Deactivated key=%s customer=%s", item["api_key"][:20], customer_id)


def _find_api_key_for_customer(customer_id: str) -> dict | None:
    """Find the key record for a customer — pending or already provisioned.
    Added 2026-07-09 for the email-confirmation flow, which may run before
    or after SNS subscribe-success provisions the real key: AWS does not
    guarantee ordering between the fulfillment redirect and the SNS
    notification, so this has to handle both cases."""
    table   = dynamodb.Table(API_KEYS_TABLE)
    pending = table.get_item(Key={"api_key": f"pending_{customer_id}"}).get("Item")
    if pending:
        return pending
    resp  = table.scan(FilterExpression=boto3.dynamodb.conditions.Attr("aws_customer_id").eq(customer_id))
    items = resp.get("Items", [])
    return items[0] if items else None


def _handle_email_confirmation(customer_id: str, email: str) -> dict:
    """Receives the email-capture form POST from the developer portal
    landing page (relayshield_developer_signup.py's _aws_email_capture_page)
    and stores the real email on whichever key record currently exists for
    this customer — pending or already-provisioned (see
    _find_api_key_for_customer for why both cases matter)."""
    email = email.strip().lower()
    try:
        record = _find_api_key_for_customer(customer_id)
        if record:
            dynamodb.Table(API_KEYS_TABLE).update_item(
                Key={"api_key": record["api_key"]},
                UpdateExpression="SET email = :e",
                ExpressionAttributeValues={":e": email},
            )
            logger.info("Email captured for customer=%s key=%s", customer_id, record["api_key"][:20])
            # If the real key was already provisioned (SNS fired before this
            # form was submitted), the original welcome email went to the
            # unreachable placeholder address — resend now that we have a
            # real one. startswith(), not ==, since 2026-07-18 — same reason
            # as relayshield_developer_signup.py's handle_landing_page(): bundle
            # customers have source="aws_marketplace_{bundle_label}", not the
            # bare string, so an exact match silently skipped their resend.
            if record.get("source", "").startswith("aws_marketplace"):
                _send_welcome_email(email, record["api_key"], record.get("aws_dimension", "ti_starter"))
        else:
            logger.warning("No key record found for customer=%s during email confirmation", customer_id)
    except Exception as exc:
        logger.warning("Failed to store email for customer=%s: %s", customer_id, exc)

    redirect_url = f"{DEVELOPERS_URL}?aws_customer_id={urllib.parse.quote(customer_id)}&source=aws_marketplace&email_confirmed=1"
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html"},
        "body": f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta http-equiv="refresh" content="0;url={redirect_url}">
<title>RelayShield — Setting up your account</title></head>
<body><p>Thanks! Setting up your RelayShield account... <a href="{redirect_url}">Click here</a> if not redirected.</p>
</body></html>""",
    }


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------

def _send_welcome_email(email: str, api_key: str, dimension: str) -> None:
    tier_label = "TI Unlimited (unlimited calls/month)" if "unlimited" in dimension else "TI Starter (10,000 calls/month)"
    body = f"""Welcome to RelayShield Threat Intelligence API.

You subscribed via AWS Marketplace: {tier_label}

Your API Key
------------
{api_key}

Add this header to every request:
  X-RS-API-KEY: {api_key}

Key capabilities included in your subscription:
- 1,000,000+ IOC corpus query (domains, IPs, URLs, hashes)
- MITRE ATT&CK actor profiles and related-actor attribution
- Trending threats (top IOCs in last 24/48 hours)
- Bulk IOC enrichment (100 IOCs per call)
- IOC pivot for lateral infrastructure discovery
- Brand protection monitoring
- Early Warning Intelligence (CVE chatter before NVD)
- STIX/TAXII 2.1 feed for SIEM integration
- All 23 identity security endpoints

Developer documentation: {API_BASE_URL}/developers

Support: support@relayshield.net

-- RelayShield
"""
    try:
        ses.send_email(
            Source=FROM_EMAIL,
            Destination={"ToAddresses": [email], "BccAddresses": [ADMIN_EMAIL]},
            Message={
                "Subject": {"Data": "Your RelayShield API Key - AWS Marketplace"},
                "Body":    {"Text": {"Data": body}},
            },
        )
        logger.info("Welcome email sent to %s", email)
    except Exception as exc:
        logger.error("Welcome email failed to %s: %s", email, exc)


def _send_admin_notification(action: str, customer_id: str, dimension: str, email: str = "") -> None:
    try:
        ses.send_email(
            Source=FROM_EMAIL,
            Destination={"ToAddresses": [ADMIN_EMAIL]},
            Message={
                "Subject": {"Data": f"AWS Marketplace: {action} — {dimension}"},
                "Body":    {"Text": {"Data": f"Action: {action}\nCustomer: {customer_id}\nDimension: {dimension}\nEmail: {email}"}},
            },
        )
    except Exception as exc:
        logger.error("Admin notification failed: %s", exc)


# ---------------------------------------------------------------------------
# Fulfillment URL handler — GET /marketplace/fulfillment
# ---------------------------------------------------------------------------

def handle_fulfillment(event: dict) -> dict:
    """
    Customer lands here after clicking Subscribe on AWS Marketplace.
    Resolve the token, store a pending record, redirect to developer portal.

    AWS actually redirects here via POST with the token as a form-encoded
    body parameter (application/x-www-form-urlencoded), not GET with a
    query string, despite what the "GET /marketplace/fulfillment" comment
    elsewhere in this file assumed. GET/HEAD is also accepted below for
    safety (e.g. a customer manually revisiting the URL), so both sources
    are checked here.
    """
    method = event.get("httpMethod", "GET")
    token  = None

    if method == "POST":
        body = event.get("body") or ""
        if event.get("isBase64Encoded"):
            import base64
            body = base64.b64decode(body).decode("utf-8", errors="replace")
        parsed = urllib.parse.parse_qs(body)
        token = (parsed.get("x-amzn-marketplace-token") or [None])[0]

        # Email confirmation step (added 2026-07-09) — the customer submitted
        # their real email via the form in _email_confirmation_page(), after
        # AWS's fulfillment redirect but with no marketplace token in this
        # request. Handle it here rather than routing to a new endpoint, to
        # avoid an API Gateway change — same Lambda, same path, distinguished
        # by which fields are present in the POST body.
        confirmed_customer_id = (parsed.get("customer_id") or [None])[0]
        confirmed_email       = (parsed.get("email") or [None])[0]
        if not token and confirmed_customer_id and confirmed_email:
            return _handle_email_confirmation(confirmed_customer_id, confirmed_email)

    if not token:
        params = event.get("queryStringParameters") or {}
        token = params.get("x-amzn-marketplace-token")

    # AWS audit probe hits this URL without a token — must return 200
    if not token:
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "text/html"},
            "body": """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>RelayShield</title>
<style>body{font-family:sans-serif;background:#0F1F3D;color:#E8EDF5;display:flex;align-items:center;
justify-content:center;min-height:100vh;margin:0}.box{background:#1A2E4A;border:1px solid #243B5A;
border-top:3px solid #00B5A5;border-radius:8px;padding:40px;max-width:420px;text-align:center}
h2{color:#fff;margin-bottom:12px}p{color:#6B8CAE;font-size:14px;line-height:1.6}a{color:#00B5A5}</style>
</head><body><div class="box"><h2>RelayShield</h2>
<p>To access RelayShield Threat Intelligence API, please subscribe via
<a href="https://aws.amazon.com/marketplace">AWS Marketplace</a>.<br><br>
Existing subscribers: check your email for your API key and setup instructions.<br><br>
Support: <a href="mailto:support@relayshield.net">support@relayshield.net</a></p>
</div></body></html>""",
        }

    try:
        resolved    = _resolve_token(token)
        customer_id = resolved.get("CustomerIdentifier", "")
        product     = resolved.get("ProductCode", "")

        if product != PRODUCT_CODE:
            logger.warning("Product code mismatch: got %s expected %s", product, PRODUCT_CODE)

        # Call GetEntitlements — required by AWS Marketplace audit before going public
        entitlement = _get_entitlement(customer_id)
        dimension   = entitlement.get("Dimension", "ti_starter") if entitlement else "ti_starter"
        logger.info("Fulfillment entitlement check customer=%s dimension=%s", customer_id, dimension)

        # Store pending record — SNS subscribe-success will provision the key
        dynamodb.Table(API_KEYS_TABLE).put_item(Item={
            "api_key":          f"pending_{customer_id}",
            "aws_customer_id":  customer_id,
            "aws_product_code": product,
            "active":           False,
            "source":           "aws_marketplace_pending",
            "created_at":       datetime.now(timezone.utc).isoformat(),
        })

        logger.info("Fulfillment pending customer=%s", customer_id)

        # Return 200 registration page with redirect script — AWS audit requires 200 not 302
        redirect_url = f"{DEVELOPERS_URL}?aws_customer_id={urllib.parse.quote(customer_id)}&source=aws_marketplace"
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "text/html"},
            "body": f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta http-equiv="refresh" content="0;url={redirect_url}">
<title>RelayShield — Setting up your account</title></head>
<body><p>Setting up your RelayShield account... <a href="{redirect_url}">Click here</a> if not redirected.</p>
</body></html>""",
        }

    except Exception as exc:
        logger.exception("Fulfillment error: %s", exc)
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "text/html"},
            "body": f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta http-equiv="refresh" content="3;url={DEVELOPERS_URL}?error=marketplace_error">
<title>RelayShield</title></head>
<body><p>Processing your subscription... redirecting shortly.</p></body></html>""",
        }

    # unreachable but satisfies linter
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html"},
        "body": "",
            "body": "",
        }


# ---------------------------------------------------------------------------
# SNS notification handler
# ---------------------------------------------------------------------------

def handle_sns(event: dict) -> dict:
    """
    Receives AWS Marketplace subscription notifications via SNS.
    Actions: subscribe-success, subscribe-fail, unsubscribe-pending, unsubscribe-success,
             entitlement-updated
    """
    for record in event.get("Records", []):
        sns_msg = record.get("Sns", {})

        # Handle SNS subscription confirmation
        if sns_msg.get("Type") == "SubscriptionConfirmation":
            confirm_url = sns_msg.get("SubscribeURL")
            if confirm_url:
                urllib.request.urlopen(confirm_url, timeout=10)
                logger.info("SNS subscription confirmed")
            continue

        try:
            msg = json.loads(sns_msg.get("Message", "{}"))
        except json.JSONDecodeError:
            logger.error("Could not parse SNS message: %s", sns_msg.get("Message", ""))
            continue

        action      = msg.get("action", "")
        customer_id = msg.get("customer-identifier", "")
        product     = msg.get("product-code", "")

        logger.info("Marketplace SNS action=%s customer=%s", action, customer_id)

        if action == "subscribe-success":
            # Get entitlement to determine dimension
            entitlement = _get_entitlement(customer_id)
            dimension   = entitlement.get("Dimension", "ti_starter") if entitlement else "ti_starter"

            # Look up email from pending record if available
            pending = dynamodb.Table(API_KEYS_TABLE).get_item(
                Key={"api_key": f"pending_{customer_id}"}
            ).get("Item", {})
            email = pending.get("email", f"aws_customer_{customer_id}@marketplace.aws")

            api_key = _provision_api_key(customer_id, email, dimension)
            _send_welcome_email(email, api_key, dimension)
            _send_admin_notification("subscribe-success", customer_id, dimension, email)

            # Clean up pending record
            try:
                dynamodb.Table(API_KEYS_TABLE).delete_item(Key={"api_key": f"pending_{customer_id}"})
            except Exception:
                pass

        elif action in ("unsubscribe-pending", "unsubscribe-success"):
            _deactivate_api_key(customer_id)
            _send_admin_notification(action, customer_id, "", "")

        elif action == "subscribe-fail":
            logger.warning("Subscribe failed customer=%s", customer_id)
            _send_admin_notification("subscribe-fail", customer_id, "", "")

        elif action == "entitlement-updated":
            entitlement = _get_entitlement(customer_id)
            if not entitlement:
                _deactivate_api_key(customer_id)
                _send_admin_notification("entitlement-expired", customer_id, "", "")

    return {"statusCode": 200, "body": "OK"}


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context) -> dict:
    # SNS direct invocation (subscription notifications)
    if event.get("Records") and event["Records"][0].get("EventSource") == "aws:sns":
        return handle_sns(event)

    # HTTP request via API Gateway
    path   = event.get("path", "")
    method = event.get("httpMethod", "GET")

    # AWS actually redirects here via POST (real subscriptions and the
    # audit probe both use POST, per AWS's own SaaS integration guide).
    # GET/HEAD are also accepted for a customer manually revisiting the URL.
    if "/marketplace/fulfillment" in path and method in ("GET", "HEAD", "POST"):
        return handle_fulfillment(event)

    if "/marketplace/sns" in path and method == "POST":
        # Manual SNS webhook if needed
        try:
            body = json.loads(event.get("body") or "{}")
            return handle_sns({"Records": [{"Sns": body, "EventSource": "aws:sns"}]})
        except Exception as exc:
            logger.error("SNS webhook error: %s", exc)
            return {"statusCode": 400, "body": "Bad request"}

    return {"statusCode": 404, "body": "Not found"}
