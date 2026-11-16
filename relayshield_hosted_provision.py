"""RelayShield hosted MCP Proxy Firewall: provisioning Lambda.

Function: relayshield-hosted-provision
Runtime: Python 3.12, timeout 900s, memory 256 MB, region us-east-1.
Handler: relayshield_hosted_provision.lambda_handler
Deploy: create the function first (tools/create_* pattern), then add it
to the deploy workflow's LAMBDA_MAP. The user-data template is embedded
in this file (USER_DATA_TEMPLATE); the deploy workflow zips only .py
files, so a separate user_data_template.sh would NOT reach the Lambda.

Trigger (Step 4): invoked asynchronously (InvocationType=Event) by the
Stripe webhook (relayshield-stripe-webhook) when a Firewall subscription
is created with hosted_proxy=true. The webhook verifies the Stripe
signature and responds 200 fast; it never provisions inline. Event:
    {
        "tenant_id": "tnt_...",
        "subscription_id": "sub_...",
        "email": "customer@example.com",   # or "customer_email"
        "plan": "sme" or "msp",            # optional when price_id is given
        "price_id": "price_...",           # optional; authoritative when known
        "upstream_url": "https://...",     # optional; defaults to the free MCP server
        "action": "provision",             # optional; only "provision" is implemented
    }
Price to plan map (the $109 bundle is a direct developer product, so it
maps to plan "sme"):
    price_1UPNO3L2dcjOeFiYMHoSwomW  ($49 direct)  -> "sme"
    price_1UWRhCL2dcjOeFiYISogjCEq  ($69 MSP)     -> "msp"
    price_1Ub2rOL2dcjOeFiY5jiiKIbm  ($109 bundle) -> "sme"

What it does, in order:
    1. Idempotency: read the registry. A record with status "active",
       or "provisioning" (recent, under 1 hour) returns the existing
       record without launching a second instance. A record with status
       "failed", "terminated", or "terminating", or a stale
       "provisioning" record (1 hour or older), allows a retry. The
       claim is a conditional DynamoDB write, so two concurrent
       invocations cannot both launch an instance.
    2. Generate a proxy token (32 hex chars).
    3. Generate the license key itself, using the Ed25519 signing code
       copied from mcp_proxy/license.py and the signing key from Secrets
       Manager (relayshield/license_signing_key). There is no
       direct-invoke license-issue Lambda; both license Lambdas are API
       Gateway endpoints. The license is plan "sme" or "msp", calls null,
       exp now + 365 days.
    4. Create (or update on retry) the per-tenant secret
       relayshield/hosted/<tenant-id> with {proxy_token, license_key,
       api_key}. The api_key is empty for now.
    5. Allocate an Elastic IP.
    6. Launch a t3.micro from ami-02163c3eefea6a447 with the substituted
       user-data, wait for it to reach running, then associate the
       Elastic IP. (Associate must run after the instance is running;
       it fails on a pending instance.)
    7. Create (or update on retry) the Cloudflare DNS A record
       <sanitized-tenant-id>.proxy.relayshield.net -> Elastic IP.
       The subdomain sanitizes the tenant id (underscores become
       hyphens) because Let's Encrypt refuses hostnames containing
       underscores; the tenant id itself keeps its underscores
       everywhere else.
    8. Poll https://<sanitized-tenant-id>.proxy.relayshield.net/_rs/health (no
       auth) every 15s for up to 10 minutes until HTTP 200.
    9. On health 200: mark the registry record "active", write
       hosted_proxy_url and hosted_proxy_status into the tenant's
       CONFIG_KV record (display cache for the console, Step 7; a
       CONFIG_KV failure does not fail the provision), and send the
       SES welcome email (proxy URL + proxy token, plain text).
    10. On any failure: mark the record "failed" with the error and
        re-raise, so the invocation is visible. The instance is NOT
        deleted automatically on a health-poll timeout; it is left
        running for diagnosis. No welcome email is sent on failure.

Actions "terminate" and "sweep" (Step 5): "terminate" tears down one
tenant immediately (EC2 instance, Elastic IP, DNS record, secret, CONFIG_KV
status, registry marked "terminated"); "sweep" scans the registry for
records with status "terminating" whose terminate_after deadline has
passed and terminates each one. A daily EventBridge rule invokes the
sweep. Invoking this Lambda with any other action raises
NotImplementedError.

Secrets: this module never logs a secret value (proxy token, license
key, Cloudflare token, signing key). Logs carry only ids, statuses,
and the subdomain. The proxy token is included exactly once, in the
welcome email to the tenant, and nowhere else.
"""

import base64
import datetime
import hashlib
import json
import os
import secrets
import socket
import ssl
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request

import boto3
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# Constants (concrete values; no placeholders)
# ---------------------------------------------------------------------------

REGION = "us-east-1"
REGISTRY_TABLE = "relayshield_hosted_proxies"

AMI_ID = "ami-02163c3eefea6a447"
INSTANCE_TYPE = "t3.micro"
KEY_PAIR_NAME = "relayshield-hosted-support"
SECURITY_GROUP_ID = "sg-02553fdf6c3bb26ee"
INSTANCE_PROFILE_NAME = "relayshield-hosted-instance-profile"

SIGNING_KEY_SECRET = "relayshield/license_signing_key"
CLOUDFLARE_TOKEN_SECRET = "relayshield/cloudflare-hosted-dns"
CLOUDFLARE_ZONE_ID = "2df425c8e70ade2931b4deb87eab9697"
CLOUDFLARE_ACCOUNT_ID = "0e0f693d78cd5782b29c5f4c660a5e47"
CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"
# CONFIG_KV: the console (Step 7) reads the tenant's hosted proxy URL
# and status from the tenant's record in this namespace. The record
# key is the tenant_id; the value is a JSON object. The registry
# (DynamoDB) remains the source of truth; CONFIG_KV is a display
# cache. Step 7 confirms the exact key format on the Mac.
CONFIG_KV_NAMESPACE_ID = "d73105bd6b1449caa8a31abcaaaa209b"

SES_SENDER = "relayshieldadmin@gmail.com"
# Console URL for tenant login and the one-time setup link.
CONSOLE_URL = "https://mcpfw.relayshield.net"
# One-time console setup token lifetime (72 hours, single-use).
SETUP_TOKEN_TTL_SECONDS = 72 * 3600
# Customer-facing support address. The From stays the verified SES
# identity above (relayshield.net is not a verified SES sender, so
# sending From support@ would fail delivery). Replies go to support@
# via Reply-To, and support@ forwards to relayshieldadmin@gmail.com
# (Cloudflare Email Routing, confirmed Active Nov 12).
SUPPORT_EMAIL = "support@relayshield.net"

LICENSE_KID = "rslic-2026-11"
LICENSE_VALID_DAYS = 365
KNOWN_PLANS = ("trial", "msp", "sme", "oem", "distributor")

# The upstream the proxy forwards MCP traffic to. The event may override
# it with "upstream_url" (checkout/console metadata). Default is the
# free RelayShield MCP server, a real MCP endpoint.
DEFAULT_UPSTREAM_URL = "https://relayshieldadmin-relayshield-free-mcp.hf.space/mcp"

# Health poll: up to 10 minutes, every 15 seconds.
HEALTH_TIMEOUT_SECONDS = 600
HEALTH_INTERVAL_SECONDS = 15
HEALTH_PATH = "/_rs/health"

# Step 6: provision retry. Up to 3 attempts per invocation; a failed
# attempt cleans up its own instance/EIP/DNS before the next try.
# On final failure the Lambda sends an admin alert and attempts a
# first-month refund (best-effort) so the customer is not charged for
# a proxy that was never delivered.
PROVISION_MAX_ATTEMPTS = 3
ADMIN_ALERT_EMAIL = "relayshieldadmin@gmail.com"
STRIPE_SECRET_KEY_NAME = "relayshield/stripe_secret_key"

# A "provisioning" record older than this is stale (a crashed or timed
# out attempt) and no longer blocks a retry.
PROVISIONING_STALE_SECONDS = 3600

# Stripe price id -> license plan. The $109 bundle is a direct developer
# product, so it maps to plan "sme".
PRICE_TO_PLAN = {
    "price_1UPNO3L2dcjOeFiYMHoSwomW": "sme",
    "price_1UWRhCL2dcjOeFiYISogjCEq": "msp",
    "price_1Ub2rOL2dcjOeFiY5jiiKIbm": "sme",
}

# ---------------------------------------------------------------------------
# AWS clients (created once per Lambda container; reused across warm starts)
# ---------------------------------------------------------------------------

_DYNAMODB = boto3.resource("dynamodb", region_name=REGION)
_TABLE = _DYNAMODB.Table(REGISTRY_TABLE)
_SECRETS = boto3.client("secretsmanager", region_name=REGION)
_EC2 = boto3.client("ec2", region_name=REGION)
_SES = boto3.client("ses", region_name=REGION)
_SSM = boto3.client("ssm", region_name=REGION)


def _log(message):
    """Log to stdout (CloudWatch). Never pass a secret value here."""
    print("relayshield-hosted-provision: %s" % message)


def _dns_subdomain(tenant_id):
    """Return the DNS subdomain for a tenant.

    Tenant ids contain underscores (tnt_...), which are not valid in
    DNS hostnames and which Let's Encrypt refuses to issue for
    ("Domain name contains an invalid character"). The subdomain
    replaces underscores with hyphens, so tnt_test_provision_001
    becomes tnt-test-provision-001.proxy.relayshield.net. The
    tenant_id itself (with underscores) stays the DynamoDB key and
    the Secrets Manager secret name; only the DNS name is sanitized.
    """
    return tenant_id.replace("_", "-") + ".proxy.relayshield.net"


# ---------------------------------------------------------------------------
# Timestamps (Unix epoch seconds, int, per the scope schema: N)
# ---------------------------------------------------------------------------

def _now_ts():
    return int(time.time())


def _age_seconds(value):
    """Age in seconds of a stored timestamp. Accepts a Unix epoch
    int (the current schema) or a legacy ISO 8601 string. Returns
    None when the value is missing or unparsable."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return time.time() - float(value)
    if isinstance(value, str):
        try:
            return time.time() - float(value)
        except Exception:
            pass
        try:
            parsed = datetime.datetime.strptime(
                value, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=datetime.timezone.utc)
        except Exception:
            return None
        return (datetime.datetime.now(datetime.timezone.utc) - parsed
                ).total_seconds()
    return None


# ---------------------------------------------------------------------------
# License signing (pure-Python Ed25519, RFC 8032).
# Copied verbatim from mcp_proxy/license.py (Step 4 licensing) so this
# Lambda has no crypto dependency and works standalone. Keep the two in
# sync; the test suite in the appliance repo cross-checks them when both
# are importable. Only the signing path is needed here (no verify).
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


def _issue_license_key(signing_key, kid, tid, plan, exp, calls=None,
                       iat=None):
    """Issue a license key string (copied from license.py).

    signing_key is the 32-byte Ed25519 private key. kid names the
    signing key so the keyring can rotate. exp is a Unix timestamp.
    Returns the RS1 key string: RS1.<payload>.<signature>.
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
        "RS1",
        _b64url_encode(payload_bytes),
        _b64url_encode(signature),
    )


# ---------------------------------------------------------------------------
# Secrets Manager
# ---------------------------------------------------------------------------

def _get_secret_string(secret_id):
    """Return a secret's string value (handles SecretBinary too)."""
    resp = _SECRETS.get_secret_value(SecretId=secret_id)
    if "SecretString" in resp:
        return resp["SecretString"]
    if "SecretBinary" in resp:
        return base64.b64decode(resp["SecretBinary"]).decode("utf-8")
    raise ValueError("secret %s has no string value" % secret_id)


def _load_signing_key():
    """Load the Ed25519 signing key. Returns (kid, 32-byte key).

    The secret relayshield/license_signing_key is JSON with the same
    shape as the local key file: {"kid": ..., "private_key_hex": ...}.
    The private key value is never logged.
    """
    data = json.loads(_get_secret_string(SIGNING_KEY_SECRET))
    kid = data.get("kid") or LICENSE_KID
    private_hex = data.get("private_key_hex")
    if not private_hex:
        raise ValueError(
            "signing key secret %s has no private_key_hex"
            % SIGNING_KEY_SECRET)
    try:
        signing_key = bytes.fromhex(private_hex.strip())
    except Exception as exc:
        raise ValueError("signing key private_key_hex is not hex") from exc
    if len(signing_key) != 32:
        raise ValueError("signing key is not 32 bytes")
    if kid != LICENSE_KID:
        _log("signing key kid is %s (expected %s)" % (kid, LICENSE_KID))
    return kid, signing_key


def _load_cloudflare_token():
    """Return the Cloudflare API token. The value is never logged."""
    token = _get_secret_string(CLOUDFLARE_TOKEN_SECRET).strip()
    if not token:
        raise ValueError(
            "Cloudflare token secret %s is empty" % CLOUDFLARE_TOKEN_SECRET)
    return token


def _create_or_update_tenant_secret(secret_name, secret_dict):
    """Create the per-tenant secret, or overwrite it on a retry."""
    payload = json.dumps(secret_dict)
    try:
        _SECRETS.create_secret(Name=secret_name, SecretString=payload)
        _log("created tenant secret %s" % secret_name)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") \
                == "ResourceExistsException":
            _SECRETS.put_secret_value(
                SecretId=secret_name, SecretString=payload)
            _log("updated existing tenant secret %s" % secret_name)
        else:
            raise


# ---------------------------------------------------------------------------
# Registry (DynamoDB relayshield_hosted_proxies)
# ---------------------------------------------------------------------------

def _get_record(tenant_id):
    resp = _TABLE.get_item(Key={"tenant_id": tenant_id})
    return resp.get("Item")


def _is_active_or_recent_provisioning(record):
    """True when the record is a live or in-flight provision that must
    not be duplicated. "active" always blocks. "provisioning" blocks
    while it is recent (under 1 hour); a stale "provisioning" record
    is a crashed attempt and does not block a retry. A "provisioning"
    record with no instance_id yet is a concurrent claim in progress;
    it still blocks, because the other invocation is about to launch.
    """
    if not record:
        return False
    status = record.get("status")
    if status == "active":
        return bool(record.get("instance_id"))
    if status == "provisioning":
        age = _age_seconds(record.get("updated_at"))
        if age is None:
            return True
        return age < PROVISIONING_STALE_SECONDS
    return False


def _claim_provisioning(tenant_id, subscription_id, plan, existing):
    """Claim the tenant for this provision attempt.

    Writes a "provisioning" registry record with a conditional write,
    so two concurrent invocations cannot both launch an instance.
    Returns True when this invocation owns the provision, False when
    another invocation won the claim (the caller re-reads the record
    and returns it). Raises on any non-conditional DynamoDB error.
    """
    now_ts = _now_ts()
    created_at = None
    if existing and existing.get("created_at"):
        created_at = existing.get("created_at")
    item = {
        "tenant_id": tenant_id,
        "subscription_id": subscription_id,
        "plan": plan,
        "status": "provisioning",
        "created_at": created_at or now_ts,
        "updated_at": now_ts,
    }
    if existing is None:
        condition = "attribute_not_exists(tenant_id)"
        names = None
        values = None
    else:
        status = existing.get("status")
        if status in ("failed", "terminated", "terminating"):
            condition = "#s = :st"
            names = {"#s": "status"}
            values = {":st": status}
        elif status == "provisioning":
            # Stale provisioning only (the caller already checked it
            # is not recent). Condition on the exact record read, so a
            # concurrent claim cannot be overwritten.
            condition = "#s = :st AND #u = :u"
            names = {"#s": "status", "#u": "updated_at"}
            values = {":st": "provisioning",
                      ":u": existing.get("updated_at")}
        else:
            # "active" (or anything else): do not claim.
            return False
    kwargs = {"Item": item, "ConditionExpression": condition}
    if names:
        kwargs["ExpressionAttributeNames"] = names
    if values:
        kwargs["ExpressionAttributeValues"] = values
    try:
        _TABLE.put_item(**kwargs)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") \
                == "ConditionalCheckFailedException":
            return False
        raise
    _log("claimed provisioning for tenant %s (plan %s)"
         % (tenant_id, plan))
    return True


def _update_record(tenant_id, **fields):
    """Update registry fields (always refreshes updated_at)."""
    if not fields:
        return
    fields["updated_at"] = _now_ts()
    names = {}
    values = {}
    sets = []
    for i, (key, value) in enumerate(fields.items()):
        name = "#f%d" % i
        placeholder = ":v%d" % i
        names[name] = key
        values[placeholder] = value
        sets.append("%s = %s" % (name, placeholder))
    _TABLE.update_item(
        Key={"tenant_id": tenant_id},
        UpdateExpression="SET " + ", ".join(sets),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def _mark_failed(tenant_id, reason):
    """Mark the registry record failed. Never raises (so it cannot
    mask the original provisioning error)."""
    try:
        _update_record(
            tenant_id, status="failed",
            failure_reason=str(reason)[:500])
        _log("marked tenant %s failed: %s" % (tenant_id, reason))
    except Exception as exc:
        _log("could not mark tenant %s failed: %s" % (tenant_id, exc))


def _public_result(record):
    """The return value: ids, subdomain, URL, and status only. No
    secret values are ever returned."""
    subdomain = record.get("subdomain") or ""
    url = record.get("url")
    if not url and subdomain:
        url = "https://" + subdomain
    return {
        "tenant_id": record.get("tenant_id"),
        "instance_id": record.get("instance_id"),
        "subdomain": subdomain or None,
        "proxy_url": url,
        "status": record.get("status"),
    }


# ---------------------------------------------------------------------------
# User-data template (embedded; the deploy workflow zips only .py
# files, so a separate user_data_template.sh would NOT reach the
# Lambda. The template is the Step 2 user-data script verbatim.
# Placeholders __TENANT_ID__, __SUBDOMAIN__, __SECRET_NAME__,
# __UPSTREAM_URL__ are substituted at launch time. ${SUBDOMAIN} in
# the Caddyfile is a bash variable, expanded on the instance at boot.)
# ---------------------------------------------------------------------------

USER_DATA_TEMPLATE = r"""#!/bin/bash
# RelayShield hosted MCP Proxy Firewall: first-boot user-data.
# Runs once via cloud-init on a fresh instance from ami-02163c3eefea6a447.
# Template: the provisioning Lambda (Step 3) substitutes __TENANT_ID__,
# __SUBDOMAIN__, __SECRET_NAME__, and __UPSTREAM_URL__ at launch time.
# For the Step 2 throwaway test, substitute them with sed before launching.
# Logs to /var/log/relayshield-provision.log.
# Secrets are NEVER in this file. The per-tenant secret
# (proxy_token, license_key, api_key) is fetched from Secrets Manager
# at boot via the instance profile. The license key file is written
# LAST so the proxy starts (via the license.path trigger) with the
# full config in place. RELAYSHIELD_LICENSE_KEY is left empty in the
# env file; the key file is the only license source.
set -euo pipefail
exec > >(tee -a /var/log/relayshield-provision.log) 2>&1
echo "relayshield-provision: starting $(date -u +%Y-%m-%dT%H:%M:%SZ)"

TENANT_ID="__TENANT_ID__"
SUBDOMAIN="__SUBDOMAIN__"
SECRET_NAME="__SECRET_NAME__"
UPSTREAM_URL="__UPSTREAM_URL__"
REGION="us-east-1"

CADDY_VERSION="2.11.9"
CADDY_SHA512="0e85544340290a16ce4bfb76fe7d65e9de1bf3a6e67f5ccfff30b30d27ea4c73e078077b7bf3e58ae60b6b12e44327705287059c775bca5782e8ee85ea7edd75"
CADDY_URL="https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_amd64.tar.gz"

echo "relayshield-provision: tenant=$TENANT_ID subdomain=$SUBDOMAIN secret=$SECRET_NAME"

# Base tools (curl, python3, unzip). Ubuntu 24.04 cloud image.
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl python3 unzip ca-certificates > /dev/null

# AWS CLI v2 (official installer; the Ubuntu cloud image has no AWS CLI).
if ! command -v aws >/dev/null 2>&1; then
  echo "relayshield-provision: installing AWS CLI v2"
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
  unzip -q /tmp/awscliv2.zip -d /tmp
  /tmp/aws/install --update > /dev/null
fi
aws --version

# Fetch the per-tenant secret. Fails the boot if the secret is missing.
echo "relayshield-provision: fetching secret $SECRET_NAME"
SECRET_JSON=$(aws secretsmanager get-secret-value --secret-id "$SECRET_NAME" --region "$REGION" --query SecretString --output text)
PROXY_TOKEN=$(printf '%s' "$SECRET_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['proxy_token'])")
LICENSE_KEY=$(printf '%s' "$SECRET_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['license_key'])")
API_KEY=$(printf '%s' "$SECRET_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('api_key',''))")
if [ -z "$PROXY_TOKEN" ] || [ -z "$LICENSE_KEY" ]; then
  echo "relayshield-provision: ERROR secret is missing proxy_token or license_key" >&2
  exit 1
fi

# Caddy user/group and directories.
groupadd --system caddy || true
useradd --system --gid caddy --home-dir /var/lib/caddy --shell /usr/sbin/nologin caddy || true
mkdir -p /etc/caddy /var/lib/caddy /etc/relayshield
chown caddy:caddy /etc/caddy /var/lib/caddy

# Install Caddy (pinned binary, SHA-512 verified against the official
# v2.11.9 release checksums). Fails the boot on a checksum mismatch.
echo "relayshield-provision: installing Caddy $CADDY_VERSION"
cd /tmp
curl -fsSL "$CADDY_URL" -o caddy.tar.gz
printf '%s  caddy.tar.gz\n' "$CADDY_SHA512" | sha512sum -c -
tar -xzf caddy.tar.gz caddy
install -m 0755 caddy /usr/local/bin/caddy
/usr/local/bin/caddy version

# Proxy env file FIRST (config only; the license key is NOT set here).
# RELAYSHIELD_LICENSE_KEY is intentionally left empty so the key file
# is the only license source.
mkdir -p /etc/relayshield
{
  printf 'MCP_PROXY_UPSTREAM=%s\n' "$UPSTREAM_URL"
  printf 'RELAYSHIELD_API_KEY=%s\n' "$API_KEY"
} > /etc/relayshield/relayshield.env
chown root:relayshield /etc/relayshield/relayshield.env
chmod 0640 /etc/relayshield/relayshield.env

# Caddy env (proxy token) and Caddyfile. The Caddyfile holds no secret.
printf 'PROXY_TOKEN=%s\n' "$PROXY_TOKEN" > /etc/caddy/caddy.env
chown root:caddy /etc/caddy/caddy.env
chmod 0600 /etc/caddy/caddy.env
cat > /etc/caddy/Caddyfile <<CADDY_EOF
${SUBDOMAIN} {
    @health path /_rs/health
    handle @health {
        reverse_proxy localhost:8090
    }
    @authed header Authorization "Bearer {\$PROXY_TOKEN}"
    handle @authed {
        reverse_proxy localhost:8090
    }
    handle {
        respond "Unauthorized" 401
    }
}
CADDY_EOF
chown root:caddy /etc/caddy/Caddyfile
chmod 0644 /etc/caddy/Caddyfile

# Caddy systemd unit.
cat > /etc/systemd/system/caddy.service <<UNIT_EOF
[Unit]
Description=Caddy
Documentation=https://caddyserver.com/docs/
After=network.target network-online.target
Requires=network-online.target

[Service]
Type=notify
User=caddy
Group=caddy
ExecStart=/usr/local/bin/caddy run --environ --config /etc/caddy/Caddyfile
ExecReload=/usr/local/bin/caddy reload --config /etc/caddy/Caddyfile --force
TimeoutStopSec=5s
LimitNOFILE=1048576
LimitNPROC=512
PrivateTmp=true
ProtectSystem=full
AmbientCapabilities=CAP_NET_BIND_SERVICE
EnvironmentFile=/etc/caddy/caddy.env

[Install]
WantedBy=multi-user.target
UNIT_EOF
systemctl daemon-reload
systemctl enable caddy.service > /dev/null

# License key file LAST. Writing it fires the relayshield-license.path
# trigger, which starts the proxy with the full config in place.
# (The proxy is in failed/exit-42 from its first boot attempt before
# the key lands; the path trigger starts it once the key is written.)
mkdir -p /var/lib/relayshield
printf '%s\n' "$LICENSE_KEY" > /var/lib/relayshield/license.key
chown relayshield:relayshield /var/lib/relayshield/license.key
chmod 0600 /var/lib/relayshield/license.key

# Start Caddy (obtains the Let's Encrypt cert for the subdomain;
# retries automatically if DNS has not propagated yet).
systemctl start caddy.service
echo "relayshield-provision: done $(date -u +%Y-%m-%dT%H:%M:%SZ)"
"""


def _build_user_data(tenant_id, subdomain, secret_name, upstream_url):
    user_data = (USER_DATA_TEMPLATE
                 .replace("__TENANT_ID__", tenant_id)
                 .replace("__SUBDOMAIN__", subdomain)
                 .replace("__SECRET_NAME__", secret_name)
                 .replace("__UPSTREAM_URL__", upstream_url))
    for placeholder in ("__TENANT_ID__", "__SUBDOMAIN__",
                        "__SECRET_NAME__", "__UPSTREAM_URL__"):
        if placeholder in user_data:
            raise ValueError(
                "user-data template still contains placeholder %s"
                % placeholder)
    return user_data


# ---------------------------------------------------------------------------
# EC2
# ---------------------------------------------------------------------------

def _allocate_eip():
    """Allocate an Elastic IP. Returns (allocation_id, public_ip)."""
    resp = _EC2.allocate_address(Domain="vpc")
    allocation_id = resp["AllocationId"]
    public_ip = resp["PublicIp"]
    _log("allocated Elastic IP %s (%s)" % (public_ip, allocation_id))
    return allocation_id, public_ip


def _launch_instance(tenant_id, subscription_id, user_data):
    """Launch the t3.micro. Returns the instance id.

    boto3 base64-encodes the UserData string for the EC2 API, so the
    plain substituted script is passed here.
    """
    resp = _EC2.run_instances(
        ImageId=AMI_ID,
        InstanceType=INSTANCE_TYPE,
        MinCount=1,
        MaxCount=1,
        KeyName=KEY_PAIR_NAME,
        SecurityGroupIds=[SECURITY_GROUP_ID],
        IamInstanceProfile={"Name": INSTANCE_PROFILE_NAME},
        UserData=user_data,
        TagSpecifications=[{
            "ResourceType": "instance",
            "Tags": [
                {"Key": "Name",
                 "Value": tenant_id + "-hosted-proxy"},
                {"Key": "Project", "Value": "relayshield"},
                {"Key": "tenant_id", "Value": tenant_id},
                {"Key": "subscription_id", "Value": subscription_id},
            ],
        }],
    )
    instance_id = resp["Instances"][0]["InstanceId"]
    _log("launched instance %s for tenant %s"
         % (instance_id, tenant_id))
    return instance_id


def _wait_instance_running(instance_id):
    """Wait until the instance is running. The Elastic IP may only be
    associated after this; associate_address fails on a pending
    instance. Budgeted to 5 minutes so the health poll still fits
    inside the 900s Lambda timeout."""
    waiter = _EC2.get_waiter("instance_running")
    waiter.wait(
        InstanceIds=[instance_id],
        WaiterConfig={"Delay": 15, "MaxAttempts": 20})
    _log("instance %s is running" % instance_id)


def _associate_eip(instance_id, allocation_id):
    resp = _EC2.associate_address(
        InstanceId=instance_id, AllocationId=allocation_id)
    _log("associated Elastic IP %s with instance %s"
         % (allocation_id, instance_id))
    return resp.get("AssociationId")


# ---------------------------------------------------------------------------
# Cloudflare DNS (v4 API, urllib; no third-party dependency)
# ---------------------------------------------------------------------------

def _cloudflare_request(token, method, path, body=None):
    """Call the Cloudflare v4 API. Returns the parsed "result" payload.
    Raises on HTTP errors and on success=false. The token is never
    logged."""
    url = CLOUDFLARE_API_BASE + path
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(
            "Cloudflare API %s %s failed: HTTP %s: %s"
            % (method, path, exc.code, detail)) from exc
    if not payload.get("success", False):
        raise RuntimeError(
            "Cloudflare API %s %s failed: %s"
            % (method, path, payload.get("errors")))
    return payload.get("result")


def _find_dns_record_id(token, name):
    """Return the id of the existing A record for the name, or None."""
    query = urllib.parse.urlencode({"type": "A", "name": name})
    result = _cloudflare_request(
        token, "GET",
        "/zones/%s/dns_records?%s" % (CLOUDFLARE_ZONE_ID, query))
    records = result if isinstance(result, list) else []
    if records:
        return records[0].get("id")
    return None


def _upsert_dns_record(token, name, content):
    """Create the A record, or update it if it already exists (retry).
    Returns the Cloudflare DNS record id."""
    body = {"type": "A", "name": name, "content": content,
            "ttl": 120, "proxied": False}
    existing_id = _find_dns_record_id(token, name)
    if existing_id:
        _log("DNS record for %s already exists; updating it" % name)
        result = _cloudflare_request(
            token, "PUT",
            "/zones/%s/dns_records/%s" % (CLOUDFLARE_ZONE_ID, existing_id),
            body)
        return result.get("id") if isinstance(result, dict) else existing_id
    result = _cloudflare_request(
        token, "POST",
        "/zones/%s/dns_records" % CLOUDFLARE_ZONE_ID, body)
    record_id = result.get("id") if isinstance(result, dict) else None
    if not record_id:
        raise RuntimeError(
            "Cloudflare DNS create for %s returned no record id" % name)
    _log("created DNS record %s for %s" % (record_id, name))
    return record_id


def _delete_dns_record(token, name):
    """Delete the A record for the name, if it exists. Returns True
    when a record was deleted, False when there was none. Never raises
    for a missing record; other Cloudflare errors propagate."""
    existing_id = _find_dns_record_id(token, name)
    if not existing_id:
        _log("no DNS record for %s to delete" % name)
        return False
    _cloudflare_request(
        token, "DELETE",
        "/zones/%s/dns_records/%s" % (CLOUDFLARE_ZONE_ID, existing_id))
    _log("deleted DNS record %s for %s" % (existing_id, name))
    return True


# ---------------------------------------------------------------------------
# Cloudflare KV (CONFIG_KV display cache for the console, Step 7)
# ---------------------------------------------------------------------------

def _write_config_kv(token, tenant_id, proxy_url, status):
    """Write hosted_proxy_url and hosted_proxy_status into the
    tenant's CONFIG_KV record (keyed by tenant_id, JSON value).
    Read-merge-write so existing tenant fields are preserved. A
    missing record is created. Failures here do not fail the
    provision; the registry (DynamoDB) is the source of truth and
    the console can be backfilled from it. Returns True on success.
    """
    path = ("/accounts/%s/storage/kv/namespaces/%s/values/%s"
            % (CLOUDFLARE_ACCOUNT_ID, CONFIG_KV_NAMESPACE_ID,
               urllib.parse.quote(tenant_id, safe="")))
    url = CLOUDFLARE_API_BASE + path
    record = {}
    # Read the current record (raw value; 404 means no record yet).
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {}
        if isinstance(parsed, dict):
            record = parsed
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise RuntimeError(
                "CONFIG_KV read for %s failed: HTTP %s"
                % (tenant_id, exc.code)) from exc
        record = {}
    record["hosted_proxy_url"] = proxy_url
    record["hosted_proxy_status"] = status
    data = json.dumps(record, sort_keys=True).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(
            "CONFIG_KV write for %s failed: HTTP %s: %s"
            % (tenant_id, exc.code, detail)) from exc
    if not payload.get("success", False):
        raise RuntimeError(
            "CONFIG_KV write for %s failed: %s"
            % (tenant_id, payload.get("errors")))
    _log("wrote CONFIG_KV hosted proxy for tenant %s (%s)"
         % (tenant_id, status))
    return True



def _config_kv_put(token, key, value_dict):
    """PUT an arbitrary key into CONFIG_KV. Used for the one-time
    console setup token ("setup-token:<token>") and the minimal
    tenant record ("tenant:<tenant-id>"). Returns True on success.
    Raises on failure; callers decide whether it is fatal."""
    path = ("/accounts/%s/storage/kv/namespaces/%s/values/%s"
            % (CLOUDFLARE_ACCOUNT_ID, CONFIG_KV_NAMESPACE_ID,
               urllib.parse.quote(key, safe="")))
    url = CLOUDFLARE_API_BASE + path
    data = json.dumps(value_dict, sort_keys=True).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(
            "CONFIG_KV put for %s failed: HTTP %s: %s"
            % (key, exc.code, detail)) from exc
    if not payload.get("success", False):
        raise RuntimeError(
            "CONFIG_KV put for %s failed: %s"
            % (key, payload.get("errors")))
    return True


def _create_console_setup(cf_token, tenant_id, email, stripe_customer_id,
                          plan):
    """Create a one-time console setup token in CONFIG_KV and return
    the setup URL, or None on failure (never raises: a setup failure
    must not fail the provision; the founder can re-issue it with
    the resend_setup action). The token is URL-safe so it can go in
    a link. The console redeems it once to create the client_admin
    user and mint a session. 72-hour expiry, single-use."""
    token = secrets.token_urlsafe(32)
    now = datetime.datetime.now(datetime.timezone.utc)
    expires = now + datetime.timedelta(seconds=SETUP_TOKEN_TTL_SECONDS)
    record = {
        "username": email.lower().strip(),
        "tenant_id": tenant_id,
        "stripe_customer_id": stripe_customer_id or "",
        "plan": plan,
        "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "used": False,
    }
    try:
        _config_kv_put(cf_token, "setup-token:" + token, record)
    except Exception as exc:
        _log("console setup token creation failed for tenant %s: %s"
             % (tenant_id, exc))
        return None
    _log("created console setup token for tenant %s (expires %s)"
         % (tenant_id, record["expires_at"]))
    return CONSOLE_URL + "/?setup=" + token


def _write_tenant_record(cf_token, tenant_id, email, stripe_customer_id,
                         subscription_id, plan, proxy_url):
    """Create the minimal "tenant:" record in CONFIG_KV so the tenant
    appears in the console tenant list and the usage/policy endpoints
    work. A provisioned direct dev tenant otherwise has no "tenant:"
    record (only the bare-key hosted proxy fields), so the console
    router returns 404 for it. Best-effort: returns True on success,
    False on failure, never raises."""
    now = datetime.datetime.now(datetime.timezone.utc)
    record = {
        "type": "tenant",
        "name": email,
        "parent_customer_id": "",
        "status": "active",
        "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "screening": {"ssrf": True, "path_traversal": True,
                      "threat_intel": True, "command_injection": True},
        "policies": {"quarantine_violation_threshold": 5,
                     "confidence_block_below": 0.60,
                     "confidence_flag_below": 0.85},
        "stripe_customer_id": stripe_customer_id or "",
        "subscription_id": subscription_id or "",
        "plan": plan,
        "hosted_proxy_url": proxy_url,
        "hosted_proxy_status": "active",
        "default_location_id": "",
        "usage_threshold_calls": 20000,
        "usage_overage_rate_per_call": 0.002,
    }
    try:
        _config_kv_put(cf_token, "tenant:" + tenant_id, record)
    except Exception as exc:
        _log("tenant record write failed for tenant %s: %s"
             % (tenant_id, exc))
        return False
    _log("wrote tenant record for %s" % tenant_id)
    return True

# ---------------------------------------------------------------------------
# Health poll
# ---------------------------------------------------------------------------

def _health_error_stage(exc):
    """Classify a health-poll failure from its traceback frames.
    Returns one of "dns", "connect", "tls", "http", "other".
    urllib collapses everything into str(exc), which is why the Nov 13
    logs only show "[Errno 16] Device or resource busy" with no clue
    which syscall raised it."""
    # Reason chain first: urllib wraps the real OSError in
    # exc.reason, and the traceback of a wrapped error does not
    # always name the syscall (a URLError raised by a stub, or by
    # urlopen itself, has no "connect" frame).
    reason = getattr(exc, "reason", None)
    if isinstance(reason, socket.gaierror):
        return "dns"
    if isinstance(reason, ConnectionRefusedError):
        return "connect"
    if isinstance(reason, ssl.SSLError):
        return "tls"
    tb = traceback.format_exc()
    if "getaddrinfo" in tb or "gaierror" in tb:
        return "dns"
    if "do_handshake" in tb or "SSLError" in tb or "ssl" in type(exc).__module__:
        return "tls"
    if "connect" in tb:
        return "connect"
    if isinstance(exc, urllib.error.HTTPError):
        return "http"
    return "other"


def _exc_errno(exc):
    """The errno of a health-poll failure. urllib wraps the real
    OSError in exc.reason, so exc.errno alone is None for URLError
    (that is why the first test of this patch logged errno=None)."""
    return (getattr(exc, "errno", None)
            or getattr(getattr(exc, "reason", None), "errno", None))


def _millis_remaining(context):
    """Lambda milliseconds left in this invocation, or None when the
    context does not expose it (local tests). Never raises."""
    try:
        if context is not None and hasattr(context, "get_remaining_time_in_millis"):
            return context.get_remaining_time_in_millis()
    except Exception:
        pass
    return None


def _health_deadline(context):
    """Monotonic deadline for the health poll: Lambda time remaining
    minus 90s safety for cleanup / mark-failed / admin alert /
    refund. Returns None when the context does not expose remaining
    time (local tests), in which case the full 600s poll applies."""
    remaining = _millis_remaining(context)
    if remaining is None:
        return None
    return time.monotonic() + max(0, remaining / 1000.0 - 90.0)


def _wait_for_health(subdomain, deadline_monotonic=None):
    """Poll the health endpoint (no auth) until HTTP 200, up to 10
    minutes. DNS NXDOMAIN, connection refused, TLS errors, and
    non-200 responses in the first minutes are "not ready yet", not
    failure (Caddy is still obtaining its certificate and DNS is
    still propagating). Returns True on HTTP 200, False on timeout."""
    url = "https://" + subdomain + HEALTH_PATH
    try:
        infos = socket.getaddrinfo(subdomain, 443, proto=socket.IPPROTO_TCP)
        _log("health check for %s resolves to %s"
             % (subdomain, sorted({i[4][0] for i in infos})))
    except Exception as exc:
        _log("health check for %s DNS resolution failed: %s "
             "(stage=dns) %s" % (subdomain, exc, traceback.format_exc()))
    budget = HEALTH_TIMEOUT_SECONDS
    if deadline_monotonic is not None:
        budget = max(0, min(budget,
                            int(deadline_monotonic - time.monotonic())))
        _log("health check for %s poll budget capped to %d seconds "
             "by Lambda deadline" % (subdomain, budget))
    attempts = budget // HEALTH_INTERVAL_SECONDS
    for attempt in range(1, attempts + 1):
        if (deadline_monotonic is not None
                and time.monotonic() >= deadline_monotonic):
            _log("health check for %s stopping: Lambda deadline "
                 "reached" % subdomain)
            return False
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
                body = resp.read().decode("utf-8", "replace")
                if status == 200:
                    _log("health check passed for %s on attempt %d "
                         "(body: %s)" % (subdomain, attempt, body[:200]))
                    return True
                _log("health check for %s returned HTTP %s on attempt %d"
                     % (subdomain, status, attempt))
        except Exception as exc:
            _log("health check for %s not ready on attempt %d: %s "
                 "(stage=%s, type=%s, errno=%s) traceback: %s"
                 % (subdomain, attempt, exc, _health_error_stage(exc),
                    type(exc).__name__, _exc_errno(exc),
                    traceback.format_exc()))
        if attempt < attempts:
            time.sleep(HEALTH_INTERVAL_SECONDS)
    _log("health check for %s did not return 200 within %d seconds"
         % (subdomain, budget))
    return False


# ---------------------------------------------------------------------------
# SES welcome email
# ---------------------------------------------------------------------------

def _send_welcome_email(email, proxy_url, proxy_token, setup_url=None):
    """Send the provisioning email. The proxy token is included here
    exactly once so the tenant can configure it; it is never logged
    and never returned by this Lambda. When setup_url is given, the
    email also carries the console login (one-time setup link, 72
    hours, single-use)."""
    body = (
        "Your RelayShield hosted MCP Proxy Firewall is ready.\n"
        "\n"
        "Proxy URL: " + proxy_url + "\n"
        "Proxy token: " + proxy_token + "\n"
        "\n"
        "Point your agent's MCP client at the proxy URL and send the "
        "token as a bearer token:\n"
        "  Authorization: Bearer " + proxy_token + "\n"
        "\n"
        "Keep the token secret. Anyone with it can use your proxy.\n"
        "\n"
        "Manage your proxy in the RelayShield console:\n"
        "Console: " + CONSOLE_URL + "\n"
        "Username: " + email + "\n"
    )
    if setup_url:
        body += (
            "Set up your console password (one-time link, expires in "
            "72 hours):\n"
            "  " + setup_url + "\n"
            "\n"
            "Click the link above, then set your password in the "
            "\"Set Up Your Console Access\" form at the top of the "
            "page. Do not use the Sign In form until your password "
            "is set.\n"
            "\n"
            "After setup, sign in at the console to see your usage, "
            "billing, policy, event logs, and hosted proxy status.\n"
            "\n"
        )
    body += "Support: " + SUPPORT_EMAIL + "\n"
    _SES.send_email(
        Source=SES_SENDER,
        Destination={"ToAddresses": [email]},
        ReplyToAddresses=[SUPPORT_EMAIL],
        Message={
            "Subject": {"Data":
                        "Your RelayShield hosted MCP Proxy Firewall "
                        "is ready"},
            "Body": {"Text": {"Data": body}},
        },
    )
    _log("sent welcome email to %s for %s" % (email, proxy_url))


# ---------------------------------------------------------------------------
# Event handling
# ---------------------------------------------------------------------------

def _resolve_plan(event):
    """Resolve the license plan from the event.

    A known price_id is authoritative (it is the billing truth). The
    $109 bundle price maps to plan "sme". Otherwise the event's plan
    is used. Raises when neither gives a valid plan.
    """
    price_id = event.get("price_id")
    if price_id and price_id in PRICE_TO_PLAN:
        return PRICE_TO_PLAN[price_id]
    if price_id:
        _log("unknown price_id %s; falling back to the event plan"
             % price_id)
    plan = event.get("plan")
    if plan in ("sme", "msp"):
        return plan
    if price_id:
        raise ValueError(
            "unknown price_id %r and no valid plan in the event"
            % price_id)
    raise ValueError(
        "event must carry a valid plan (sme or msp) or a known price_id")


def _release_eip_by_ip(public_ip):
    """Release the Elastic IP with this public IP, if it exists.
    Looks up the AllocationId via describe-addresses. Returns True
    when released, False when there was no such EIP. Never raises for
    a missing EIP."""
    if not public_ip:
        return False
    try:
        resp = _EC2.describe_addresses(PublicIps=[public_ip])
    except Exception as exc:
        _log("describe-addresses failed for %s: %s" % (public_ip, exc))
        return False
    addresses = resp.get("Addresses") or []
    if not addresses:
        _log("no Elastic IP found for %s" % public_ip)
        return False
    allocation_id = addresses[0].get("AllocationId")
    if not allocation_id:
        return False
    try:
        _EC2.release_address(AllocationId=allocation_id)
    except Exception as exc:
        _log("release-address failed for %s (%s): %s"
             % (public_ip, allocation_id, exc))
        return False
    _log("released Elastic IP %s (%s)" % (public_ip, allocation_id))
    return True


def _delete_tenant_secret(secret_name):
    """Delete the per-tenant secret. Returns True when deleted, False
    when there was none. Never raises for a missing secret."""
    if not secret_name:
        return False
    try:
        _SECRETS.delete_secret(
            SecretId=secret_name, ForceDeleteWithoutRecovery=True)
    except _SECRETS.exceptions.ResourceNotFoundException:
        _log("no secret %s to delete" % secret_name)
        return False
    except Exception as exc:
        _log("delete-secret failed for %s: %s" % (secret_name, exc))
        return False
    _log("deleted secret %s" % secret_name)
    return True


def _terminate_tenant(tenant_id):
    """Tear down one tenant immediately: EC2 instance, Elastic IP, DNS
    record, secret, CONFIG_KV status, registry marked "terminated".
    Each step is best-effort (a failure is logged, not fatal) except
    the final registry mark. Returns the public result dict. A missing
    record returns status "not_found"; an already-terminated record
    returns its existing result."""
    record = _get_record(tenant_id)
    if not record:
        _log("terminate: no record for tenant %s" % tenant_id)
        return {"tenant_id": tenant_id, "instance_id": None,
                "subdomain": None, "proxy_url": None, "status": "not_found"}
    if record.get("status") == "terminated":
        _log("tenant %s already terminated" % tenant_id)
        return _public_result(record)

    instance_id = record.get("instance_id")
    public_ip = record.get("eip") or record.get("public_ip") or record.get("elastic_ip")
    subdomain = record.get("subdomain") or ""
    secret_name = record.get("hosted_secret") or ("relayshield/hosted/" + tenant_id)

    _log("terminating tenant %s (instance %s)" % (tenant_id, instance_id))
    if instance_id:
        try:
            _EC2.terminate_instances(InstanceIds=[instance_id])
            _log("terminate-instances issued for %s" % instance_id)
        except Exception as exc:
            _log("terminate-instances failed for %s: %s" % (instance_id, exc))
    if public_ip:
        _release_eip_by_ip(public_ip)
    if subdomain:
        try:
            cf_token = _load_cloudflare_token()
            _delete_dns_record(cf_token, subdomain)
        except Exception as exc:
            _log("DNS delete failed for %s: %s" % (subdomain, exc))
    _delete_tenant_secret(secret_name)
    try:
        cf_token = _load_cloudflare_token()
        _write_config_kv(cf_token, tenant_id,
                         record.get("url") or ("https://" + subdomain if subdomain else ""),
                         "terminated")
    except Exception as exc:
        _log("CONFIG_KV terminated write failed for %s: %s" % (tenant_id, exc))

    _update_record(tenant_id, status="terminated", terminated_at=_now_ts())
    record = _get_record(tenant_id)
    _log("terminate complete for tenant %s" % tenant_id)
    return _public_result(record)


def _sweep_terminating():
    """Terminate every registry record with status "terminating" whose
    terminate_after deadline has passed. Returns a summary dict
    {terminated: [tenant_ids], skipped: [tenant_ids], errors: {tid: reason}}.
    Records not yet past their deadline are skipped, not terminated."""
    now_ts = _now_ts()
    terminated = []
    skipped = []
    errors = {}
    try:
        resp = _TABLE.scan(
            FilterExpression="#s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "terminating"},
        )
    except Exception as exc:
        _log("sweep scan failed: %s" % exc)
        return {"terminated": terminated, "skipped": skipped,
                "errors": {"scan": str(exc)}}
    items = resp.get("Items") or []
    # Paginate the scan (the table is small, but be correct).
    while "LastEvaluatedKey" in resp:
        resp = _TABLE.scan(
            FilterExpression="#s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "terminating"},
            ExclusiveStartKey=resp["LastEvaluatedKey"],
        )
        items.extend(resp.get("Items") or [])
    for item in items:
        tenant_id = item.get("tenant_id")
        terminate_after = item.get("terminate_after")
        if terminate_after is None:
            skipped.append(tenant_id)
            continue
        try:
            deadline = int(terminate_after)
        except Exception:
            skipped.append(tenant_id)
            continue
        if deadline > now_ts:
            skipped.append(tenant_id)
            continue
        try:
            _terminate_tenant(tenant_id)
            terminated.append(tenant_id)
        except Exception as exc:
            errors[tenant_id] = str(exc)
            _log("sweep terminate failed for %s: %s" % (tenant_id, exc))
    _log("sweep complete: terminated %d, skipped %d, errors %d"
         % (len(terminated), len(skipped), len(errors)))
    return {"terminated": terminated, "skipped": skipped, "errors": errors}


def _send_admin_alert(tenant_id, subscription_id, reason):
    """Email the admin that a provision failed after all retries.
    Best-effort; a failure here does not mask the original error."""
    subject = "Hosted proxy provision FAILED for %s" % tenant_id
    body = ("RelayShield hosted proxy provisioning failed after %d attempts.\n\n"
            "Tenant: %s\nSubscription: %s\nReason: %s\n\n"
            "The customer has not been provisioned. Check CloudWatch "
            "/aws/lambda/relayshield-hosted-provision for detail."
            % (PROVISION_MAX_ATTEMPTS, tenant_id, subscription_id, reason))
    try:
        _SES.send_email(
            Source="RelayShield <relayshieldadmin@gmail.com>",
            Destination={"ToAddresses": [ADMIN_ALERT_EMAIL]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            },
        )
        _log("admin alert sent for failed provision of %s" % tenant_id)
        return True
    except Exception as exc:
        _log("admin alert failed for %s: %s" % (tenant_id, exc))
        return False


def _stripe_api_get(path, stripe_secret_key):
    """GET a Stripe API path. Returns the parsed JSON dict."""
    credentials = base64.b64encode(f"{stripe_secret_key}:".encode()).decode()
    req = urllib.request.Request(
        "https://api.stripe.com" + path,
        headers={"Authorization": f"Basic {credentials}"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _stripe_api_post(path, stripe_secret_key, data):
    """POST form-encoded data to a Stripe API path. Returns parsed JSON."""
    credentials = base64.b64encode(f"{stripe_secret_key}:".encode()).decode()
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        "https://api.stripe.com" + path,
        data=body,
        headers={"Authorization": f"Basic {credentials}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _refund_first_invoice(subscription_id):
    """Refund the first-month payment for a subscription whose provision
    failed after all retries. Finds the subscription's latest invoice,
    takes its charge, and refunds it. Best-effort: returns the refund
    id on success, None when there is nothing to refund or the refund
    fails. Never raises."""
    try:
        stripe_secret_key = _load_secret(STRIPE_SECRET_KEY_NAME)
    except Exception as exc:
        _log("refund: could not load Stripe secret key: %s" % exc)
        return None
    try:
        sub = _stripe_api_get("/v1/subscriptions/%s" % subscription_id,
                              stripe_secret_key)
        invoice_id = sub.get("latest_invoice")
        if not invoice_id:
            _log("refund: no latest invoice for %s" % subscription_id)
            return None
        invoice = _stripe_api_get("/v1/invoices/%s" % invoice_id,
                                  stripe_secret_key)
        charge_id = invoice.get("charge")
        if not charge_id:
            _log("refund: invoice %s has no charge" % invoice_id)
            return None
        if invoice.get("amount_paid", 0) <= 0:
            _log("refund: invoice %s amount_paid is 0, nothing to refund"
                 % invoice_id)
            return None
        refund = _stripe_api_post(
            "/v1/refunds", stripe_secret_key,
            {"charge": charge_id, "reason": "requested_by_customer"})
        refund_id = refund.get("id")
        _log("refund: refunded charge %s for subscription %s (refund %s)"
             % (charge_id, subscription_id, refund_id))
        return refund_id
    except Exception as exc:
        _log("refund failed for subscription %s: %s" % (subscription_id, exc))
        return None


def _load_secret(secret_name):
    """Fetch a Secrets Manager secret string value."""
    resp = _SECRETS.get_secret_value(SecretId=secret_name)
    return resp.get("SecretString") or ""


def _diagnose_tenant(tenant_id):
    """Read-only diagnosis of a (possibly failed) tenant. Returns the
    registry record, EC2 instance state + status checks, the EC2
    console output tail, and, when SSM is available, Caddy status
    plus a local health curl on the instance. Never launches,
    terminates, or modifies anything. SSM failure is reported, not
    raised."""
    record = _get_record(tenant_id) or {}
    result = {"tenant_id": tenant_id, "registry": record,
              "instance": {}, "console_output_tail": "",
              "ssm": {"available": False, "output": ""}}
    instance_id = record.get("instance_id")
    if not instance_id:
        result["error"] = "no instance_id in registry record"
        return result
    try:
        resp = _EC2.describe_instances(InstanceIds=[instance_id])
        inst = resp["Reservations"][0]["Instances"][0]
        result["instance"] = {
            "state": inst["State"]["Name"],
            "public_ip": inst.get("PublicIpAddress"),
            "private_ip": inst.get("PrivateIpAddress"),
            "launch_time": str(inst.get("LaunchTime")),
        }
        try:
            checks = _EC2.describe_instance_status(
                InstanceIds=[instance_id])
            st = checks.get("InstanceStatuses", [{}])[0]
            result["instance"]["system_status"] = st.get("SystemStatus", {}).get("Status")
            result["instance"]["instance_status"] = st.get("InstanceStatus", {}).get("Status")
        except Exception as exc:
            result["instance"]["status_error"] = str(exc)
    except Exception as exc:
        result["instance_error"] = str(exc)
        return result
    try:
        out = _EC2.get_console_output(InstanceId=instance_id, Latest=True)
        result["console_output_tail"] = (out.get("Output") or "")[-4000:]
    except Exception as exc:
        result["console_output_error"] = str(exc)
    try:
        cmd = ("systemctl is-active caddy; "
               "curl -s -m 5 http://127.0.0.1:8090/_rs/health || echo CURL_FAILED; "
               "journalctl -u caddy -n 30 --no-pager || true")
        resp = _SSM.send_command(
            InstanceIds=[instance_id],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": [cmd]},
            TimeoutSeconds=60)
        command_id = resp["Command"]["CommandId"]
        for _ in range(12):
            time.sleep(5)
            inv = _SSM.get_command_invocation(
                CommandId=command_id, InstanceId=instance_id)
            if inv.get("Status") in ("Success", "Failed", "TimedOut", "Cancelled"):
                result["ssm"] = {"available": True,
                                 "status": inv.get("Status"),
                                 "output": (inv.get("StandardOutputContent") or "")[-4000:],
                                 "error": (inv.get("StandardErrorContent") or "")[-2000:]}
                break
        else:
            result["ssm"] = {"available": True, "status": "poll-timeout",
                             "output": ""}
    except Exception as exc:
        result["ssm"] = {"available": False, "output": str(exc)}
    return result


def _cleanup_attempt_resources(instance_id, allocation_id, eip, subdomain):
    """Tear down the resources of a single failed provision attempt so
    the next retry starts clean. Best-effort; every step is logged
    and never raises."""
    if instance_id:
        try:
            _EC2.terminate_instances(InstanceIds=[instance_id])
            _log("retry cleanup: terminated instance %s" % instance_id)
        except Exception as exc:
            _log("retry cleanup: terminate failed for %s: %s" % (instance_id, exc))
    if allocation_id:
        try:
            _EC2.release_address(AllocationId=allocation_id)
            _log("retry cleanup: released EIP %s" % allocation_id)
        except Exception as exc:
            _log("retry cleanup: release failed for %s: %s" % (allocation_id, exc))
    elif eip:
        _release_eip_by_ip(eip)
    if subdomain:
        try:
            cf_token = _load_cloudflare_token()
            _delete_dns_record(cf_token, subdomain)
        except Exception as exc:
            _log("retry cleanup: DNS delete failed for %s: %s" % (subdomain, exc))



def _rotate_proxy_token(tenant_id):
    """Rotate the tenant's proxy token. Order matters, and the secret
    is the source of truth:
      1. Read the current secret (for rollback) and the registry
         record (for the instance id).
      2. Generate the new token and update the secret.
      3. SSM Run Command on the instance: rewrite /etc/caddy/caddy.env
         with the new token and reload Caddy (systemd reads the
         updated env file for the reload, so the new token takes
         effect). Poll for completion.
      4. On SSM failure, roll the secret back to the old token and
         raise, so the old token keeps working (safe failure).
    Returns {tenant_id, instance_id, proxy_token}. The new token is
    returned once so the console can show it to the tenant; it is
    never logged. Requires the SSM IAM prerequisites (see the module
    docstring in the patch script)."""
    record = _get_record(tenant_id)
    if not record or record.get("status") != "active":
        raise ValueError("tenant %s is not active" % tenant_id)
    instance_id = record.get("instance_id")
    if not instance_id:
        raise ValueError("tenant %s has no instance" % tenant_id)
    secret_name = "relayshield/hosted/" + tenant_id
    current = json.loads(_get_secret_string(secret_name))
    old_token = current.get("proxy_token")
    if not old_token:
        raise ValueError("tenant %s secret has no proxy_token" % tenant_id)
    new_token = secrets.token_hex(16)
    updated = dict(current)
    updated["proxy_token"] = new_token
    _create_or_update_tenant_secret(secret_name, updated)
    _log("rotated secret for tenant %s; reloading Caddy on %s"
         % (tenant_id, instance_id))
    script = (
        "set -e\n"
        "printf 'PROXY_TOKEN=%s\n' '" + new_token + "' > /etc/caddy/caddy.env\n"
        "chown root:caddy /etc/caddy/caddy.env\n"
        "chmod 0600 /etc/caddy/caddy.env\n"
        "systemctl reload caddy.service\n"
        "systemctl is-active caddy.service\n"
    )
    try:
        cmd = _SSM.send_command(
            InstanceIds=[instance_id],
            DocumentName="AWS-RunShellScript",
            Parameters={"commands": [script]},
            TimeoutSeconds=120,
        )
        command_id = cmd["Command"]["CommandId"]
    except Exception as exc:
        _log("SSM send_command failed for tenant %s: %s"
             % (tenant_id, exc))
        _create_or_update_tenant_secret(secret_name, current)
        raise RuntimeError("SSM send_command failed: %s" % exc) from exc
    for _ in range(12):
        time.sleep(10)
        try:
            inv = _SSM.get_command_invocation(
                CommandId=command_id, InstanceId=instance_id)
        except Exception as exc:
            _log("SSM get_command_invocation failed for tenant %s: %s"
                 % (tenant_id, exc))
            continue
        status = inv.get("Status")
        if status == "Success":
            _log("rotated proxy token for tenant %s (instance %s)"
                 % (tenant_id, instance_id))
            return {"tenant_id": tenant_id, "instance_id": instance_id,
                    "proxy_token": new_token}
        if status in ("Failed", "Cancelled", "TimedOut"):
            detail = (inv.get("StandardErrorContent") or "")[:500]
            _log("SSM reload failed for tenant %s: %s %s"
                 % (tenant_id, status, detail))
            _create_or_update_tenant_secret(secret_name, current)
            raise RuntimeError(
                "Caddy reload failed on the instance (%s): %s"
                % (status, detail))
    _create_or_update_tenant_secret(secret_name, current)
    raise RuntimeError("Caddy reload timed out on the instance")


def _resend_setup(tenant_id, email):
    """Regenerate a console setup token and re-send the welcome email.
    For when a setup link expired (72h) or was never used. Requires
    the tenant to be active. Returns {tenant_id, setup_url}."""
    record = _get_record(tenant_id)
    if not record or record.get("status") != "active":
        raise ValueError("tenant %s is not active" % tenant_id)
    cf_token = _load_cloudflare_token()
    proxy_url = record.get("url") or ("https://" + (record.get("subdomain") or ""))
    proxy_token = ""
    try:
        secret = json.loads(_get_secret_string(
            "relayshield/hosted/" + tenant_id))
        proxy_token = secret.get("proxy_token") or ""
    except Exception as exc:
        _log("could not read tenant secret for resend_setup %s: %s"
             % (tenant_id, exc))
    setup_url = _create_console_setup(
        cf_token, tenant_id, email,
        record.get("stripe_customer_id") or "", record.get("plan") or "sme")
    _send_welcome_email(email, proxy_url, proxy_token,
                        setup_url=setup_url)
    return {"tenant_id": tenant_id, "setup_url": setup_url}

def lambda_handler(event, context):
    """Provision a hosted MCP Proxy Firewall instance for one tenant.

    See the module docstring for the event contract and the
    idempotency contract. Returns the public result dict
    {tenant_id, instance_id, subdomain, proxy_url, status}. Raises on
    failure after marking the registry record "failed".
    """
    action = event.get("action", "provision")
    if action == "terminate":
        tenant_id = event.get("tenant_id")
        if not tenant_id:
            raise ValueError("terminate requires tenant_id")
        return _terminate_tenant(tenant_id)
    if action == "sweep":
        return _sweep_terminating()
    if action == "rotate_token":
        tenant_id = event.get("tenant_id")
        if not tenant_id:
            raise ValueError("rotate_token requires tenant_id")
        return _rotate_proxy_token(tenant_id)
    if action == "resend_setup":
        tenant_id = event.get("tenant_id")
        email = event.get("email") or event.get("customer_email")
        if not tenant_id or not email:
            raise ValueError("resend_setup requires tenant_id and email")
        return _resend_setup(tenant_id, email)
    if action == "diagnose":
        tenant_id = event.get("tenant_id")
        if not tenant_id:
            raise ValueError("diagnose requires tenant_id")
        return _diagnose_tenant(tenant_id)
    if action != "provision":
        raise NotImplementedError(
            "action %r is not implemented in this Lambda" % action)

    tenant_id = event.get("tenant_id")
    subscription_id = event.get("subscription_id")
    email = event.get("email") or event.get("customer_email")
    if not tenant_id or not subscription_id or not email:
        raise ValueError(
            "event must carry tenant_id, subscription_id, and email")
    plan = _resolve_plan(event)
    upstream_url = event.get("upstream_url") or DEFAULT_UPSTREAM_URL
    subdomain = _dns_subdomain(tenant_id)
    proxy_url = "https://" + subdomain
    secret_name = "relayshield/hosted/" + tenant_id

    _log("provision requested for tenant %s (plan %s, subscription %s)"
         % (tenant_id, plan, subscription_id))

    # Idempotency first: never launch a second instance for a tenant
    # that already has a live or in-flight provision.
    existing = _get_record(tenant_id)
    if existing and _is_active_or_recent_provisioning(existing):
        _log("tenant %s already %s (instance %s); returning existing "
             "record" % (tenant_id, existing.get("status"),
                         existing.get("instance_id")))
        return _public_result(existing)

    # Claim the provision. A conditional write makes this safe against
    # a concurrent duplicate invocation.
    if not _claim_provisioning(tenant_id, subscription_id, plan, existing):
        existing = _get_record(tenant_id)
        if existing and _is_active_or_recent_provisioning(existing):
            _log("lost the claim race for tenant %s; returning the "
                 "existing record" % tenant_id)
            return _public_result(existing)
        raise RuntimeError(
            "could not claim provisioning for tenant %s" % tenant_id)

    # This invocation owns the provision. Up to PROVISION_MAX_ATTEMPTS
    # attempts; a failed attempt cleans up its own instance/EIP/DNS
    # before the next try. On final failure the record is marked
    # "failed", an admin alert is sent, and a first-month refund is
    # attempted (best-effort). Then the error is re-raised.
    last_exc = None
    for attempt in range(1, PROVISION_MAX_ATTEMPTS + 1):
        # Attempt 1 always runs: a fresh invocation has 900s and one
        # attempt costs at most 300s (instance wait) + 600s (poll),
        # which just fits, and the poll itself is now deadline-capped
        # (P3 above) so it stops 90s before the timeout. A retry
        # attempt can only start if at least 180s remain; otherwise
        # fail fast through the normal final-failure path (mark
        # failed, admin alert, refund) instead of being killed
        # silently mid-poll, which is what stranded
        # tnt_test_tenant_login_002 on 2026-11-13 (invocation
        # 21:04:48 UTC, attempt 2 launched 21:14:59, then nothing:
        # no attempt 3, no alert, registry stuck provisioning).
        if attempt > 1:
            remaining = _millis_remaining(context)
            if remaining is not None and remaining < 180000:
                _log("provision for tenant %s: only %d ms remain, "
                     "not starting retry attempt %d; failing fast so "
                     "the admin alert fires"
                     % (tenant_id, remaining, attempt))
                last_exc = RuntimeError(
                    "insufficient Lambda time remaining (%d ms) for "
                    "provision attempt %d" % (remaining, attempt))
                break
        attempt_instance_id = None
        attempt_allocation_id = None
        attempt_eip = None
        try:
            _log("provision attempt %d/%d for tenant %s"
                 % (attempt, PROVISION_MAX_ATTEMPTS, tenant_id))
            # Proxy token (32 hex chars).
            proxy_token = secrets.token_hex(16)

        # License, generated here (no license Lambda to invoke).
            kid, signing_key = _load_signing_key()
            license_exp = int(time.time()) + LICENSE_VALID_DAYS * 86400
            license_key = _issue_license_key(
                signing_key, kid, tenant_id, plan, license_exp, calls=None)
            _log("issued license for tenant %s (plan %s, kid %s)"
                 % (tenant_id, plan, kid))

            # Per-tenant secret (created, or overwritten on a retry).
            _create_or_update_tenant_secret(secret_name, {
                "proxy_token": proxy_token,
                "license_key": license_key,
                "api_key": "",
            })

            # Elastic IP, then launch. The EIP is associated only after
            # the instance is running.
            allocation_id, eip = _allocate_eip()
            attempt_allocation_id = allocation_id
            attempt_eip = eip
            user_data = _build_user_data(
                tenant_id, subdomain, secret_name, upstream_url)
            instance_id = _launch_instance(
                tenant_id, subscription_id, user_data)
            attempt_instance_id = instance_id
            _wait_instance_running(instance_id)
            _associate_eip(instance_id, allocation_id)

            # Record the instance while it is still provisioning.
            _update_record(
                tenant_id,
                instance_id=instance_id,
                public_ip=eip,
                elastic_ip=eip,
                eip=eip,
                subdomain=subdomain,
                url=proxy_url + "/",
                ami_id=AMI_ID,
                license_key_id=kid + ":" + tenant_id,
                hosted_secret=secret_name,
                status="provisioning")

            # DNS A record (created, or updated on a retry).
            cf_token = _load_cloudflare_token()
            dns_record_id = _upsert_dns_record(cf_token, subdomain, eip)
            _update_record(tenant_id, dns_record_id=dns_record_id)

            # Health poll. DNS NXDOMAIN / TLS errors in the first minutes
            # are "not ready yet". On timeout the instance is left running
            # for diagnosis (it is NOT deleted here).
            if not _wait_for_health(subdomain, _health_deadline(context)):
                raise RuntimeError(
                    "health check for %s did not return 200 within %d "
                    "seconds" % (subdomain, HEALTH_TIMEOUT_SECONDS))

            # Active, then CONFIG_KV display cache, then console
            # access (setup token + tenant record), then welcome email.
            # A CONFIG_KV failure does not fail the provision; the
            # registry (DynamoDB) is the source of truth.
            _update_record(tenant_id, status="active")
            try:
                _write_config_kv(cf_token, tenant_id, proxy_url, "active")
            except Exception as exc:
                _log("CONFIG_KV write failed for tenant %s: %s "
                     "(registry is source of truth)" % (tenant_id, exc))
            setup_url = _create_console_setup(
                cf_token, tenant_id, email,
                event.get("stripe_customer_id") or "", plan)
            _write_tenant_record(
                cf_token, tenant_id, email,
                event.get("stripe_customer_id") or "", subscription_id,
                plan, proxy_url)
            _send_welcome_email(email, proxy_url, proxy_token,
                                setup_url=setup_url)

            record = _get_record(tenant_id)
            _log("provision complete for tenant %s (instance %s, %s)"
                 % (tenant_id, instance_id, proxy_url))
            return _public_result(record)
        except Exception as exc:
            last_exc = exc
            _log("provision attempt %d/%d failed for tenant %s: %s"
                 % (attempt, PROVISION_MAX_ATTEMPTS, tenant_id, exc))
            if attempt < PROVISION_MAX_ATTEMPTS:
                _cleanup_attempt_resources(
                    attempt_instance_id, attempt_allocation_id,
                    attempt_eip, subdomain)
                _update_record(tenant_id, status="provisioning")
                continue
            # Final attempt: do NOT clean up. Leave the instance, EIP
            # and DNS record running so the failure can be diagnosed
            # (SSM / EC2 console output / Caddy journal) instead of
            # destroying the evidence, as happened to attempt 1 of
            # tnt_test_tenant_login_002. Terminate cleans it up.
            _log("final provision attempt failed for tenant %s; "
                 "leaving instance %s (%s) running for diagnosis"
                 % (tenant_id, attempt_instance_id, attempt_eip))
            _mark_failed(tenant_id, exc)
            _send_admin_alert(tenant_id, subscription_id, exc)
            _refund_first_invoice(subscription_id)
            raise
    if last_exc is not None:
        _mark_failed(tenant_id, last_exc)
        _send_admin_alert(tenant_id, subscription_id, last_exc)
        _refund_first_invoice(subscription_id)
    raise RuntimeError(
        "provision failed for tenant %s after %d attempts: %s"
        % (tenant_id, PROVISION_MAX_ATTEMPTS, last_exc))
