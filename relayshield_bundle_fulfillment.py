"""
relayshield_bundle_fulfillment — AWS Marketplace Bundle fulfillment + entitlement Lambda

Isolated Lambda for the "RelayShield - Consumption Security API Bundles"
product (prod-kkvurtspreofy) — a Contract with Consumption product,
structurally different from the flat-rate TI Starter/Unlimited product
handled by relayshield_aws_marketplace.py. Deliberately separate/duplicated
rather than shared, per the isolation mandate agreed 2026-07-06 (TODO.md
item 32): a bug here must not be able to regress the already-live,
already-approved TI fulfillment flow.

Handles multiple bundles on the same product entity (Bundle D added
2026-07-07, Bundle A added 2026-07-13) — which bundle a customer has is
resolved from which contract dimension their entitlement is for (see
BUNDLE_CONFIGS below), not hardcoded to a single bundle.

Handles three entry points:

1. POST/GET/HEAD /marketplace/bundle-fulfillment
   "Redirect to Website" fulfillment URL. Customer lands here after
   subscribing on AWS Marketplace. Resolves the registration token,
   stores a pending record, redirects to the developer portal. Mirrors
   relayshield_aws_marketplace.py's handle_fulfillment pattern (AWS
   requires POST with x-amzn-marketplace-token in a form-encoded body,
   not a GET query string — confirmed against AWS's own guide during the
   TI product's integration).

2. SNS notification — aws-mp-subscription-notification
   subscribe-success / subscribe-fail / unsubscribe-pending / unsubscribe-success.

3. SNS notification — aws-mp-entitlement-notification (contract-specific;
   only exists for products with a contract dimension, per AWS docs).
   Contract created/renewed/expired — re-check entitlement, activate or
   deactivate accordingly.

Both SNS topics are separate ARNs from the TI product's topic (each AWS
Marketplace product gets its own). Fill in below once known from Seller
Central for this product listing — this file will run but SNS events
won't arrive until the subscription is created with the real ARN.

Usage metering (BatchMeterUsage) for the 5 per-call dimensions is NOT
handled here — that happens at the point of use, in relayshield_api.py
(tech-stack-cve, bulk-identity-risk, llm-credential-exposure) and
relayshield_agentic_api.py (mcp-registry-risk, prompt-injection-breach),
which each call report_bundle_d_usage() (duplicated locally in each file,
not imported, same isolation rationale).
This file only handles entitlement/provisioning — knowing *whether* a
customer is allowed to call Bundle D endpoints at all, not metering their
per-call usage once they do.
"""

import base64
import json
import logging
import os
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

API_KEYS_TABLE = "relayshield_api_keys"
FROM_EMAIL     = "noreply@relayshield.net"
ADMIN_EMAIL    = "relayshieldadmin@gmail.com"
API_BASE_URL   = "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod"
# Every customer-visible URL uses the branded host. Both hosts route all the
# same paths (verified 2026-07-30); the raw execute-api hostname breaks if the
# API Gateway ID ever changes, and reads as a phishing link to a buyer who just
# paid on AWS Marketplace -- including the AWS auditor walking this exact flow.
PUBLIC_API_BASE_URL = "https://api.relayshield.net"
DEVELOPERS_URL = f"{PUBLIC_API_BASE_URL}/developers"

# Fill in once available from AWS Marketplace Seller Central for this
# specific product listing — distinct from the TI product's values. Shared
# across all bundles on this product (Bundle A, D, ...) — the env var name
# is a historical artifact of Bundle D being built first.
PRODUCT_CODE = os.environ.get("BUNDLE_D_PRODUCT_CODE", "")

# One entry per contract ("Entitled") dimension on this product. The
# dimension key on a customer's entitlement (GetEntitlements' Dimension
# field) is the lookup key — that's how a single fulfillment/SNS handler
# figures out *which* bundle a given customer/entitlement is for.
BUNDLE_CONFIGS = {
    "agentic_bundle_access": {
        "label":        "agentic_attack_surface",
        "dynamo_flag":  "bundle_d_access",
        "display_name": "Agentic Attack Surface (Bundle D)",
        "endpoints_text": (
            "- Agent Identity Risk Score (bulk-identity-risk) — hierarchical org + per-agent-email risk scoring\n"
            "- Agent Framework Exploit Monitoring (tech-stack-cve) — CVE targeting by declared tech stack\n"
            "- MCP Registry Risk (mcp-registry-risk) — malicious/typosquatted/newly-registered MCP server detection\n"
            "- Prompt Injection Breach Detection (prompt-injection-breach) — credential/session exposure from agentic-sourced breaches\n"
            "- LLM Credential Exposure (llm-credential-exposure) — leaked LLM provider API keys (OpenAI, Anthropic, Google, Groq, xAI, Replicate) in stealer logs and public repos"
        ),
    },
    "core_identity_bundle_access": {
        "label":        "core_identity_exposure",
        "dynamo_flag":  "bundle_a_access",
        "display_name": "Core Identity Exposure (Bundle A)",
        "endpoints_text": (
            "- Breach Exposure Check (breach) — aggregated breach corpus and dark web database lookup\n"
            "- SIM Swap Detection (sim-swap) — recent SIM swap activity, a classic account-takeover precursor\n"
            "- Infostealer Log Check (infostealer) — credentials found in infostealer malware logs\n"
            "- Domain Lookalike Detection (domain) — typosquatted/lookalike domains against your brand\n"
            "- OAuth Token Exposure Watchlist (oauth-watchlist) — exposed OAuth/API tokens across leaked credential sources\n"
            "- Crypto Intelligence Check (crypto-intel) — wallet/domain checks against RelayShield's crypto threat intel corpus"
        ),
    },
}

dynamodb  = boto3.resource("dynamodb", region_name="us-east-1")
ent_client = boto3.client("marketplace-entitlement", region_name="us-east-1")
mp_client  = boto3.client("meteringmarketplace", region_name="us-east-1")
ses        = boto3.client("ses", region_name="us-east-1")


# ---------------------------------------------------------------------------
# Token resolution / entitlement check
# ---------------------------------------------------------------------------

def _resolve_token(token: str) -> dict:
    try:
        resp = mp_client.resolve_customer(RegistrationToken=token)
        logger.info("Resolved token: customer=%s product=%s",
                    resp.get("CustomerIdentifier"), resp.get("ProductCode"))
        return resp
    except Exception as exc:
        logger.error("resolve_customer failed: %s", exc)
        raise


def _get_entitlement(customer_id: str) -> dict | None:
    """Active entitlement for *any* contract (Entitled) dimension on this
    product. A present, unexpired entitlement means the customer has an
    active contract for whichever bundle its Dimension resolves to (see
    _resolve_bundle) — this file no longer assumes a single bundle."""
    try:
        resp = ent_client.get_entitlements(
            ProductCode=PRODUCT_CODE,
            Filter={"CUSTOMER_IDENTIFIER": [customer_id]},
        )
        entitlements = resp.get("Entitlements", [])
        active = [e for e in entitlements if not e.get("ExpirationDate") or
                  e["ExpirationDate"] > datetime.now(timezone.utc)]
        # Prefer an entitlement whose Dimension is a known bundle-access
        # dimension (the contract-commitment dimension) over per-call
        # metered dimensions, which GetEntitlements can also return.
        for e in active:
            if e.get("Dimension") in BUNDLE_CONFIGS:
                return e
        return active[0] if active else None
    except Exception as exc:
        logger.error("get_entitlements failed customer=%s: %s", customer_id, exc)
        return None


def _resolve_bundle(entitlement: dict | None) -> dict:
    """Map an entitlement's Dimension to its BUNDLE_CONFIGS entry. Falls
    back to Bundle D (the original/default bundle on this product) if the
    dimension is unrecognized, so this never silently drops a customer."""
    dimension = (entitlement or {}).get("Dimension", "")
    return BUNDLE_CONFIGS.get(dimension, BUNDLE_CONFIGS["agentic_bundle_access"])


# ---------------------------------------------------------------------------
# API key provisioning
# ---------------------------------------------------------------------------

def _provision_api_key(customer_id: str, email: str, bundle_config: dict, license_arn: str = "", aws_account_id: str = "") -> str:
    """license_arn + aws_account_id are required for BatchMeterUsage under
    AWS's Concurrent Agreements model (rolled out 2026-06-01) — new SaaS
    products must meter using CustomerAWSAccountId + LicenseArn instead of
    the older CustomerIdentifier + ProductCode pattern. GetEntitlements
    returns both fields in the raw response, but older/cached botocore
    models may silently drop LicenseArn — confirmed present via a raw HTTP
    debug trace 2026-07-10, so .get("LicenseArn") below should work at
    runtime even though the AWS CLI's parsed output didn't show it."""
    api_key = f"rs_live_{uuid.uuid4().hex}"
    dynamodb.Table(API_KEYS_TABLE).put_item(Item={
        "api_key":                     api_key,
        "aws_customer_id":             customer_id,
        "aws_account_id":              aws_account_id,
        "aws_product_code":            PRODUCT_CODE,
        "aws_license_arn":             license_arn,
        "aws_bundle":                  bundle_config["label"],
        bundle_config["dynamo_flag"]:  True,
        "email":                       email,
        "active":                      True,
        "source":                      f"aws_marketplace_{bundle_config['label']}",
        "created_at":                  datetime.now(timezone.utc).isoformat(),
    })
    logger.info("%s API key provisioned customer=%s license_arn=%s",
                bundle_config["display_name"], customer_id, bool(license_arn))
    return api_key


def _deactivate_api_key(customer_id: str) -> None:
    """Filters by aws_customer_id only, not by bundle — an AWS Marketplace
    customer_id belongs to exactly one contract dimension/bundle at a time
    on this product, so this is unambiguous without knowing which bundle."""
    table = dynamodb.Table(API_KEYS_TABLE)
    resp  = table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr("aws_customer_id").eq(customer_id)
        & boto3.dynamodb.conditions.Attr("aws_product_code").eq(PRODUCT_CODE)
    )
    for item in resp.get("Items", []):
        table.update_item(
            Key={"api_key": item["api_key"]},
            UpdateExpression="SET active = :f, deactivated_at = :ts",
            ExpressionAttributeValues={":f": False, ":ts": datetime.now(timezone.utc).isoformat()},
        )
        logger.info("Deactivated key=%s bundle=%s customer=%s", item["api_key"][:20], item.get("aws_bundle"), customer_id)


def _find_api_key_for_customer(customer_id: str) -> dict | None:
    table   = dynamodb.Table(API_KEYS_TABLE)
    pending = table.get_item(Key={"api_key": f"pending_{customer_id}"}).get("Item")
    if pending:
        return pending
    resp  = table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr("aws_customer_id").eq(customer_id)
        & boto3.dynamodb.conditions.Attr("aws_product_code").eq(PRODUCT_CODE)
    )
    items = resp.get("Items", [])
    return items[0] if items else None


def _find_provisioned_key_for_customer(customer_id: str) -> dict | None:
    """The customer's live, active rs_live_ key, if one has been issued yet.

    Separate from _find_api_key_for_customer because that one intentionally
    prefers the pending placeholder. Used by the email-confirmation page, which
    must display a credential the customer can actually send.
    """
    table = dynamodb.Table(API_KEYS_TABLE)
    resp  = table.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr("aws_customer_id").eq(customer_id)
        & boto3.dynamodb.conditions.Attr("aws_product_code").eq(PRODUCT_CODE)
        & boto3.dynamodb.conditions.Attr("active").eq(True)
        & boto3.dynamodb.conditions.Attr("api_key").begins_with("rs_live_")
    )
    items = resp.get("Items", [])
    if not items:
        return None
    # Newest first: a customer who resubscribes accumulates keys, and the most
    # recently created one is the one their entitlement was provisioned against.
    items.sort(key=lambda i: str(i.get("created_at", "")), reverse=True)
    return items[0]


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------

def _send_welcome_email(email: str, api_key: str, bundle_config: dict) -> None:
    body = f"""Welcome to RelayShield's {bundle_config['display_name']} API.

You subscribed via AWS Marketplace.

Your API Key
------------
{api_key}

Add this header to every request:
  X-RS-API-KEY: {api_key}

Endpoints included in your contract:
{bundle_config['endpoints_text']}

Your monthly contract covers the base commitment; per-call usage beyond
that is billed through AWS Marketplace automatically.

Developer documentation: {DEVELOPERS_URL}

Support: support@relayshield.net

-- RelayShield
"""
    try:
        ses.send_email(
            Source=FROM_EMAIL,
            Destination={"ToAddresses": [email], "BccAddresses": [ADMIN_EMAIL]},
            Message={
                "Subject": {"Data": f"Your RelayShield API Key - {bundle_config['display_name']} (AWS Marketplace)"},
                "Body":    {"Text": {"Data": body}},
            },
        )
        logger.info("%s welcome email sent to %s", bundle_config["display_name"], email)
    except Exception as exc:
        logger.error("%s welcome email failed to %s: %s", bundle_config["display_name"], email, exc)


def _handle_email_confirmation(customer_id: str, email: str) -> dict:
    """Email-capture form POST from the developer portal's AWS landing page.

    Added 2026-07-30 after AWS failed the Bundle D public-visibility request
    (change set 7rjip57niylpdl9uo5u3l735k) with:
        "After subscribing to your product, when trying to get the API key,
         we get an error message 'Something went wrong'."

    Root cause: this branch did not exist. The email-capture page in
    relayshield_developer_signup.py hardcoded its form action to the TI
    product's /marketplace/fulfillment, so a Bundle A-D subscriber's email
    submission was handled by relayshield_aws_marketplace.py -- which sent them
    a Threat Intelligence welcome email for endpoints they had not bought, then
    redirected with the bare source=aws_marketplace and email_confirmed=1. That
    combination falls through to the ordinary Stripe self-serve landing page,
    whose "Get API key" button posts /developer/signup and fails for an AWS
    customer with no Stripe record -- printing the exact string AWS quoted.

    So the fix is not only to route bundle customers here: this response also
    shows the key on screen. AWS's complaint was that the key was not
    retrievable, and an email alone leaves the buyer staring at a page that
    does not contain what they asked for.
    """
    email = email.strip().lower()
    record = None
    try:
        # Deliberately NOT _find_api_key_for_customer(): that one returns the
        # "pending_{customer_id}" placeholder first, which is right for the SNS
        # paths but wrong here -- this page has to show a usable credential, and
        # by the time a buyer types an email the real rs_live_ key normally
        # exists alongside the placeholder.
        record = _find_provisioned_key_for_customer(customer_id) or _find_api_key_for_customer(customer_id)
        if record:
            dynamodb.Table(API_KEYS_TABLE).update_item(
                Key={"api_key": record["api_key"]},
                UpdateExpression="SET email = :e",
                ExpressionAttributeValues={":e": email},
            )
            logger.info("Bundle email captured customer=%s key=%s", customer_id, record["api_key"][:20])
        else:
            logger.warning("No key record found for customer=%s during bundle email confirmation", customer_id)
    except Exception as exc:
        logger.warning("Failed to store email for customer=%s: %s", customer_id, exc)

    bundle_config = BUNDLE_CONFIGS.get("agentic_bundle_access")
    if record:
        for cfg in BUNDLE_CONFIGS.values():
            if record.get("aws_bundle") == cfg["label"]:
                bundle_config = cfg
                break

    api_key = (record or {}).get("api_key", "")
    provisioned = api_key.startswith("rs_live_")
    if provisioned:
        _send_welcome_email(email, api_key, bundle_config)

    # SNS subscribe-success normally lands before the buyer finishes typing an
    # email, but it is asynchronous and not guaranteed to. When the real key is
    # not there yet, say so plainly instead of showing a "pending_" placeholder
    # that would fail as a credential.
    key_block = (
        f"""<p class="lbl">Your API key</p><code>{api_key}</code>
<p class="hint">Send it as the <b>X-RS-API-KEY</b> header on every request.
We also emailed a copy to {email}.</p>"""
        if provisioned else
        """<p class="hint">Your key is being provisioned and will arrive by email within a
few minutes. If it does not, contact <a href="mailto:support@relayshield.net">support@relayshield.net</a>
and we will issue it directly.</p>"""
    )
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html"},
        "body": f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Your RelayShield API key</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d0f14;
color:#e8eaf0;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:2rem}}
.card{{background:#161a23;border:1px solid #242836;border-top:3px solid #6c63ff;border-radius:18px;
padding:2.5rem;max-width:560px;width:100%}}
h1{{font-size:1.35rem;font-weight:800;margin:0 0 .5rem}}
.sub{{color:#8b91a8;font-size:.9rem;margin:0 0 1.6rem}}
.lbl{{color:#8b91a8;font-size:.78rem;text-transform:uppercase;letter-spacing:.05em;margin:0 0 .4rem}}
code{{display:block;background:#0d0f14;border:1px solid #242836;border-radius:8px;padding:.85rem;
font-size:.9rem;word-break:break-all;color:#7ee0c0}}
.hint{{color:#8b91a8;font-size:.85rem;line-height:1.6;margin:1rem 0 0}}
a{{color:#6c63ff}}</style>
</head><body><div class="card">
<h1>You're all set</h1>
<p class="sub">{bundle_config['display_name']} &middot; billed through AWS Marketplace</p>
{key_block}
<p class="hint">Documentation: <a href="{DEVELOPERS_URL}">{DEVELOPERS_URL}</a><br>
Support: <a href="mailto:support@relayshield.net">support@relayshield.net</a></p>
</div></body></html>""",
    }


def _send_admin_notification(action: str, customer_id: str, email: str = "", bundle_label: str = "") -> None:
    try:
        ses.send_email(
            Source=FROM_EMAIL,
            Destination={"ToAddresses": [ADMIN_EMAIL]},
            Message={
                "Subject": {"Data": f"AWS Marketplace {bundle_label or 'bundle'}: {action}"},
                "Body":    {"Text": {"Data": f"Action: {action}\nCustomer: {customer_id}\nEmail: {email}"}},
            },
        )
    except Exception as exc:
        logger.error("Admin notification failed: %s", exc)


# ---------------------------------------------------------------------------
# Fulfillment URL handler — /marketplace/bundle-fulfillment
# ---------------------------------------------------------------------------

def handle_fulfillment(event: dict) -> dict:
    method = event.get("httpMethod", "GET")
    token  = None

    if method == "POST":
        body = event.get("body") or ""
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode("utf-8", errors="replace")
        parsed = urllib.parse.parse_qs(body)
        token  = (parsed.get("x-amzn-marketplace-token") or [None])[0]

        # Email-capture form submit: no marketplace token, but customer_id and
        # email. Mirrors relayshield_aws_marketplace.py's branch -- same Lambda,
        # same path, distinguished by which fields the POST carries, so no API
        # Gateway change is needed. Must be checked before the tokenless
        # "please subscribe" fallback below, which this used to fall into.
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
border-top:3px solid #00B5A5;border-radius:8px;padding:40px;max-width:440px;text-align:center}
h2{color:#fff;margin-bottom:12px}p{color:#6B8CAE;font-size:14px;line-height:1.6}a{color:#00B5A5}</style>
</head><body><div class="box"><h2>RelayShield — Consumption Security API Bundles</h2>
<p>To access these APIs, please subscribe via
<a href="https://aws.amazon.com/marketplace">AWS Marketplace</a>.<br><br>
Existing subscribers: check your email for your API key and setup instructions.<br><br>
Support: <a href="mailto:support@relayshield.net">support@relayshield.net</a></p>
</div></body></html>""",
        }

    try:
        resolved    = _resolve_token(token)
        customer_id = resolved.get("CustomerIdentifier", "")
        product     = resolved.get("ProductCode", "")

        if PRODUCT_CODE and product != PRODUCT_CODE:
            logger.warning("Product code mismatch: got %s expected %s", product, PRODUCT_CODE)

        entitlement   = _get_entitlement(customer_id)
        bundle_config = _resolve_bundle(entitlement)
        logger.info("%s fulfillment entitlement check customer=%s active=%s",
                    bundle_config["display_name"], customer_id, bool(entitlement))

        dynamodb.Table(API_KEYS_TABLE).put_item(Item={
            "api_key":          f"pending_{customer_id}",
            "aws_customer_id":  customer_id,
            "aws_product_code": product,
            "aws_bundle":       bundle_config["label"],
            "active":           False,
            "source":           f"aws_marketplace_{bundle_config['label']}_pending",
            "created_at":       datetime.now(timezone.utc).isoformat(),
        })

        redirect_url = f"{DEVELOPERS_URL}?aws_customer_id={urllib.parse.quote(customer_id)}&source=aws_marketplace_{bundle_config['label']}"
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "text/html"},
            "body": f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta http-equiv="refresh" content="0;url={redirect_url}">
<title>RelayShield — Setting up your account</title></head>
<body><p>Setting up your {bundle_config['display_name']} account... <a href="{redirect_url}">Click here</a> if not redirected.</p>
</body></html>""",
        }

    except Exception as exc:
        logger.exception("Bundle D fulfillment error: %s", exc)
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "text/html"},
            "body": f"""<!DOCTYPE html><html><head><meta charset="UTF-8">
<meta http-equiv="refresh" content="3;url={DEVELOPERS_URL}?error=marketplace_error">
<title>RelayShield</title></head>
<body><p>Processing your subscription... redirecting shortly.</p></body></html>""",
        }


# ---------------------------------------------------------------------------
# SNS notification handler — subscription + entitlement (contract) topics
# ---------------------------------------------------------------------------

def handle_sns(event: dict) -> dict:
    for record in event.get("Records", []):
        sns_msg = record.get("Sns", {})

        if sns_msg.get("Type") == "SubscriptionConfirmation":
            confirm_url = sns_msg.get("SubscribeURL")
            if confirm_url:
                urllib.request.urlopen(confirm_url, timeout=10)
                logger.info("SNS subscription confirmed (Bundle D)")
            continue

        try:
            msg = json.loads(sns_msg.get("Message", "{}"))
        except json.JSONDecodeError:
            logger.error("Could not parse Bundle D SNS message: %s", sns_msg.get("Message", ""))
            continue

        action      = msg.get("action", "")
        customer_id = msg.get("customer-identifier", "")

        logger.info("Bundle D marketplace SNS action=%s customer=%s", action, customer_id)

        if action == "subscribe-success":
            pending = dynamodb.Table(API_KEYS_TABLE).get_item(
                Key={"api_key": f"pending_{customer_id}"}
            ).get("Item", {})
            email = pending.get("email", f"aws_customer_{customer_id}@marketplace.aws")

            entitlement    = _get_entitlement(customer_id)
            bundle_config  = _resolve_bundle(entitlement)
            license_arn    = (entitlement or {}).get("LicenseArn", "")
            aws_account_id = (entitlement or {}).get("CustomerAWSAccountId", "")
            api_key = _provision_api_key(customer_id, email, bundle_config, license_arn, aws_account_id)
            _send_welcome_email(email, api_key, bundle_config)
            _send_admin_notification("subscribe-success", customer_id, email, bundle_config["display_name"])

            try:
                dynamodb.Table(API_KEYS_TABLE).delete_item(Key={"api_key": f"pending_{customer_id}"})
            except Exception:
                pass

        elif action in ("unsubscribe-pending", "unsubscribe-success"):
            _deactivate_api_key(customer_id)
            _send_admin_notification(action, customer_id)

        elif action == "subscribe-fail":
            logger.warning("Marketplace subscribe failed customer=%s", customer_id)
            _send_admin_notification("subscribe-fail", customer_id)

        elif action == "entitlement-updated":
            # Contract renewed, upgraded, or expired — aws-mp-entitlement-notification
            entitlement = _get_entitlement(customer_id)
            if not entitlement:
                _deactivate_api_key(customer_id)
                _send_admin_notification("entitlement-expired", customer_id)

    return {"statusCode": 200, "body": "OK"}


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event: dict, context) -> dict:
    if event.get("Records") and event["Records"][0].get("EventSource") == "aws:sns":
        return handle_sns(event)

    path   = event.get("path", "")
    method = event.get("httpMethod", "GET")

    if "/marketplace/bundle-fulfillment" in path and method in ("GET", "HEAD", "POST"):
        return handle_fulfillment(event)

    return {"statusCode": 404, "body": "Not found"}
