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
       <tenant-id>.proxy.relayshield.net -> Elastic IP.
    8. Poll https://<tenant-id>.proxy.relayshield.net/_rs/health (no
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

Actions "terminate" and "sweep" are NOT implemented here; they belong
to Step 5 (cancellation flow / daily sweeper). Invoking this Lambda
with another action raises NotImplementedError.

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
import time
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


def _log(message):
    """Log to stdout (CloudWatch). Never pass a secret value here."""
    print("relayshield-hosted-provision: %s" % message)


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


# ---------------------------------------------------------------------------
# Health poll
# ---------------------------------------------------------------------------

def _wait_for_health(subdomain):
    """Poll the health endpoint (no auth) until HTTP 200, up to 10
    minutes. DNS NXDOMAIN, connection refused, TLS errors, and
    non-200 responses in the first minutes are "not ready yet", not
    failure (Caddy is still obtaining its certificate and DNS is
    still propagating). Returns True on HTTP 200, False on timeout."""
    url = "https://" + subdomain + HEALTH_PATH
    attempts = HEALTH_TIMEOUT_SECONDS // HEALTH_INTERVAL_SECONDS
    for attempt in range(1, attempts + 1):
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
            _log("health check for %s not ready on attempt %d: %s"
                 % (subdomain, attempt, exc))
        if attempt < attempts:
            time.sleep(HEALTH_INTERVAL_SECONDS)
    _log("health check for %s did not return 200 within %d seconds"
         % (subdomain, HEALTH_TIMEOUT_SECONDS))
    return False


# ---------------------------------------------------------------------------
# SES welcome email
# ---------------------------------------------------------------------------

def _send_welcome_email(email, proxy_url, proxy_token):
    """Send the provisioning email. The proxy token is included here
    exactly once so the tenant can configure it; it is never logged
    and never returned by this Lambda."""
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
        "Support: " + SUPPORT_EMAIL + "\n"
    )
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


def lambda_handler(event, context):
    """Provision a hosted MCP Proxy Firewall instance for one tenant.

    See the module docstring for the event contract and the
    idempotency contract. Returns the public result dict
    {tenant_id, instance_id, subdomain, proxy_url, status}. Raises on
    failure after marking the registry record "failed".
    """
    action = event.get("action", "provision")
    if action != "provision":
        raise NotImplementedError(
            "action %r is not implemented in this Lambda; terminate "
            "and sweep belong to Step 5" % action)

    tenant_id = event.get("tenant_id")
    subscription_id = event.get("subscription_id")
    email = event.get("email") or event.get("customer_email")
    if not tenant_id or not subscription_id or not email:
        raise ValueError(
            "event must carry tenant_id, subscription_id, and email")
    plan = _resolve_plan(event)
    upstream_url = event.get("upstream_url") or DEFAULT_UPSTREAM_URL
    subdomain = tenant_id + ".proxy.relayshield.net"
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

    # This invocation owns the provision. Any failure from here is
    # recorded as "failed" and re-raised.
    try:
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
        user_data = _build_user_data(
            tenant_id, subdomain, secret_name, upstream_url)
        instance_id = _launch_instance(
            tenant_id, subscription_id, user_data)
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
        if not _wait_for_health(subdomain):
            raise RuntimeError(
                "health check for %s did not return 200 within %d "
                "seconds" % (subdomain, HEALTH_TIMEOUT_SECONDS))

        # Active, then CONFIG_KV display cache, then welcome email.
        # A CONFIG_KV failure does not fail the provision; the
        # registry (DynamoDB) is the source of truth.
        _update_record(tenant_id, status="active")
        try:
            _write_config_kv(cf_token, tenant_id, proxy_url, "active")
        except Exception as exc:
            _log("CONFIG_KV write failed for tenant %s: %s "
                 "(registry is source of truth)" % (tenant_id, exc))
        _send_welcome_email(email, proxy_url, proxy_token)

        record = _get_record(tenant_id)
        _log("provision complete for tenant %s (instance %s, %s)"
             % (tenant_id, instance_id, proxy_url))
        return _public_result(record)
    except Exception as exc:
        _mark_failed(tenant_id, exc)
        raise
