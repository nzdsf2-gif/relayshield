"""
RelayShield Domain Monitor Lambda

Daily EventBridge schedule — scans Business Basic / Shield / Shield Pro domains for:
  1. Typosquat/lookalike domain registrations (custom permutation + parallel socket DNS)
  2. MX record changes (Cloudflare DNS-over-HTTPS)
  3. Domain expiry risk (RDAP API — alerts at 30, 14, 7 days)

No external library dependencies — stdlib only + boto3.

Monitoring state stored per-domain as JSON in `domain_monitor_state` on relayshield_users.
Admin co-notification for Business Basic+ employees (same pattern as breach co-notification).

Template SIDs — fill after Meta approval, then redeploy:
  DOMAIN_LOOKALIKE_TEMPLATE_SID  (3 variables: {{1}}=domain, {{2}}=lookalike, {{3}}=count)
  DOMAIN_MX_CHANGE_TEMPLATE_SID  (2 variables: {{1}}=domain, {{2}}=detection date e.g. "April 26, 2026")
  DOMAIN_EXPIRY_TEMPLATE_SID     (3 variables: {{1}}=domain, {{2}}=days, {{3}}=urgency word)

While these SIDs are empty the Lambda runs but skips alert delivery.
Alerts fire the moment you fill in the SIDs and redeploy.

Deployment:
  Lambda name:   relayshield-domain-monitor
  Handler:       relayshield_domain_monitor.lambda_handler
  Runtime:       Python 3.12
  Timeout:       300 s (DNS threading for large permutation sets)
  Memory:        256 MB
  EventBridge:   rate(1 day)
  IAM requires:
    DynamoDB Scan + GetItem + UpdateItem on relayshield_users
    Secrets Manager GetSecretValue for Twilio creds
    KMS Decrypt on alias/relayshield-data-key

Test payloads:
  Dry run — scans and logs, sends no WhatsApp alerts:
    { "dry_run": true }

  Force-test for a single admin user — runs all checks, sends freeform alerts
  (bypasses template gate so you can verify delivery before Meta approval):
    { "test_user_id": "user-onboard-test-001" }
"""

import base64
import concurrent.futures
import json
import logging
import socket
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# AWS clients
# ---------------------------------------------------------------------------

secrets_client = boto3.client("secretsmanager")
dynamodb       = boto3.resource("dynamodb")
kms_client     = boto3.client("kms")

USERS_TABLE         = "relayshield_users"
KMS_PHONE_KEY_ALIAS = "alias/relayshield-data-key"

# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

TWILIO_SID_SECRET   = "relayshield/twilio_account_sid"
TWILIO_TOKEN_SECRET = "relayshield/twilio_auth_token"
TWILIO_FROM_SECRET  = "relayshield/twilio_whatsapp_number"

TWILIO_MESSAGES_URL = (
    "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
)

# ---------------------------------------------------------------------------
# Meta-approved template SIDs
# Fill in after approval, then redeploy. Leave empty to suppress alert delivery
# (Lambda will scan and log findings but not send WhatsApp messages).
# ---------------------------------------------------------------------------

DOMAIN_LOOKALIKE_TEMPLATE_SID = "HX5c71336145c248642ec864a53a0320cf"  # 3 vars: {{1}}=domain {{2}}=lookalike {{3}}=count
DOMAIN_MX_CHANGE_TEMPLATE_SID = "HXaa1912f2a81ca440b025f61d5f6b51e8"  # 2 vars: {{1}}=domain {{2}}=detection date
DOMAIN_EXPIRY_TEMPLATE_SID    = "HXc5b861da1c21d8097e0d8830ed663d96"  # 3 vars: {{1}}=domain {{2}}=days {{3}}=urgency

# ---------------------------------------------------------------------------
# Tier constants — domain monitoring eligibility and limits
# ---------------------------------------------------------------------------

TIER_STARTER_DOMAIN = "starter_domain"
TIER_BASIC          = "business_basic"
TIER_SHIELD         = "business_shield"
TIER_PRO            = "business_shield_pro"

DOMAIN_TIERS = {TIER_STARTER_DOMAIN, TIER_BASIC, TIER_SHIELD, TIER_PRO}

DOMAIN_LIMITS = {
    TIER_STARTER_DOMAIN: 1,
    TIER_BASIC:          2,
    TIER_SHIELD:         2,
    TIER_PRO:            2,
}

# Onboarding states eligible for proactive alerts
ELIGIBLE_STATES = {"ACTIVE", "EMPLOYEE_ACTIVE", "AWAITING_EMAIL_1", "AWAITING_MORE_EMAILS"}

# ---------------------------------------------------------------------------
# Domain expiry thresholds (days)
# ---------------------------------------------------------------------------

EXPIRY_THRESHOLDS = [7, 14, 30]   # ascending severity — alert at first match

# ---------------------------------------------------------------------------
# Typosquat permutation — TLD variants to check
# ---------------------------------------------------------------------------

COMMON_TLDS = [
    ".com", ".net", ".org", ".co", ".io", ".biz",
    ".info", ".us", ".co.uk", ".ca", ".com.au",
]

# Common business-targeting prefix/suffix attacks
PHISHING_PREFIXES = ["secure-", "login-", "my-", "get-", "support-", "help-"]
PHISHING_SUFFIXES = ["-secure", "-login", "-online", "-support", "-portal", "-verify"]

# ---------------------------------------------------------------------------
# Secret helpers
# ---------------------------------------------------------------------------

def get_secret(secret_name: str) -> str:
    response = secrets_client.get_secret_value(SecretId=secret_name)
    return response["SecretString"].strip()


def get_secret_json(secret_name: str, key: str) -> str:
    raw = get_secret(secret_name)
    try:
        data = json.loads(raw)
        return data[key]
    except (json.JSONDecodeError, KeyError):
        return raw


def get_twilio_credentials() -> tuple[str, str, str]:
    account_sid = get_secret_json(TWILIO_SID_SECRET,   "TWILIO_ACCOUNT_SID")
    auth_token  = get_secret_json(TWILIO_TOKEN_SECRET,  "TWILIO_AUTH_TOKEN")
    from_number = get_secret_json(TWILIO_FROM_SECRET,   "TWILIO_WHATSAPP_NUMBER")
    return account_sid, auth_token, from_number


# ---------------------------------------------------------------------------
# Phone helpers
# ---------------------------------------------------------------------------

def decrypt_phone(ciphertext_b64: str) -> str:
    response = kms_client.decrypt(CiphertextBlob=base64.b64decode(ciphertext_b64))
    return response["Plaintext"].decode()


def get_whatsapp_number(user: dict) -> str:
    if "phone_encrypted" in user:
        phone = decrypt_phone(user["phone_encrypted"]).replace("whatsapp:", "").strip()
        return f"whatsapp:{phone}"
    legacy = user.get("whatsapp_number", "")
    if legacy and not legacy.startswith("whatsapp:"):
        legacy = f"whatsapp:{legacy}"
    return legacy


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def scan_domain_tier_admins() -> list[dict]:
    """
    Return all active admin users (no admin_user_id) in DOMAIN_TIERS
    who have at least one monitored domain registered.
    """
    table = dynamodb.Table(USERS_TABLE)
    users: list[dict] = []
    kwargs: dict = {"FilterExpression": Attr("active").eq(True)}

    while True:
        response = table.scan(**kwargs)
        for item in response.get("Items", []):
            tier  = item.get("subscription_tier", "")
            state = item.get("onboarding_state", "")
            is_admin  = not item.get("admin_user_id")
            has_domain = bool(item.get("monitored_domains"))
            if (
                tier in DOMAIN_TIERS
                and state in ELIGIBLE_STATES
                and is_admin
                and has_domain
            ):
                users.append(item)
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key

    return users


def get_user_by_id(user_id: str) -> dict | None:
    table    = dynamodb.Table(USERS_TABLE)
    response = table.get_item(Key={"user_id": user_id})
    return response.get("Item")


def update_domain_state(user_id: str, state: dict) -> None:
    table = dynamodb.Table(USERS_TABLE)
    now   = datetime.now(timezone.utc).isoformat()
    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET domain_monitor_state = :s, updated_at = :t",
        ExpressionAttributeValues={":s": json.dumps(state), ":t": now},
    )


def load_domain_state(user: dict) -> dict:
    """
    Load the domain_monitor_state JSON from a user record.
    Returns an empty dict if the field is absent or malformed.
    """
    raw = user.get("domain_monitor_state", "")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def blank_domain_entry() -> dict:
    return {
        "registered_at":     datetime.now(timezone.utc).isoformat(),
        "last_scanned":      None,
        "known_lookalikes":  [],
        "mx_fingerprint":    None,
        "expiry_days_alerted": None,
    }


# ---------------------------------------------------------------------------
# Typosquat permutation generator
# ---------------------------------------------------------------------------

def generate_typosquat_permutations(domain: str) -> set[str]:
    """
    Generate candidate lookalike domains for a given domain.
    Returns a set of strings (without the original domain).
    """
    if "." not in domain:
        return set()

    # Split on LAST dot to preserve multi-part TLDs like co.uk
    dot_pos = domain.rfind(".")
    name    = domain[:dot_pos]
    tld     = domain[dot_pos:]   # includes the dot e.g. ".com"

    perms: set[str] = set()

    # --- Character omission ---
    for i in range(len(name)):
        candidate = name[:i] + name[i + 1:]
        if candidate:
            perms.add(candidate + tld)

    # --- Character repetition ---
    for i, c in enumerate(name):
        perms.add(name[:i] + c + c + name[i + 1:] + tld)

    # --- Adjacent character transposition ---
    for i in range(len(name) - 1):
        t      = list(name)
        t[i], t[i + 1] = t[i + 1], t[i]
        perms.add("".join(t) + tld)

    # --- Homoglyph substitution (ASCII-resolvable chars only) ---
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

    # --- Hyphen insertion ---
    for i in range(1, len(name)):
        perms.add(name[:i] + "-" + name[i:] + tld)

    # --- Hyphen removal (if domain has a hyphen) ---
    if "-" in name:
        perms.add(name.replace("-", "") + tld)

    # --- TLD substitution ---
    for alt_tld in COMMON_TLDS:
        if alt_tld != tld:
            perms.add(name + alt_tld)

    # --- Phishing prefix/suffix attacks ---
    for prefix in PHISHING_PREFIXES:
        perms.add(prefix + name + tld)
    for suffix in PHISHING_SUFFIXES:
        perms.add(name + suffix + tld)

    # --- www typo confusion ---
    perms.add("www" + domain)       # wwwacme.com (missing dot)

    # Remove the original domain and any empty strings
    perms.discard(domain)
    perms = {p for p in perms if p and len(p) > 2}

    return perms


def _dns_resolves(domain: str, timeout: float = 3.0) -> bool:
    """Return True if the domain has a DNS A record."""
    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout)
        socket.gethostbyname(domain)
        return True
    except (socket.gaierror, OSError):
        return False
    finally:
        socket.setdefaulttimeout(old_timeout)


def find_active_lookalikes(
    domain: str,
    known_lookalikes: list[str],
    max_workers: int = 25,
    overall_timeout: float = 60.0,
) -> list[str]:
    """
    Generate permutations, DNS-resolve in parallel, return newly registered
    lookalikes not already in known_lookalikes.
    """
    candidates = generate_typosquat_permutations(domain)
    known_set  = set(known_lookalikes)
    new_candidates = candidates - known_set  # skip ones we've already alerted on

    logger.info(
        "Typosquat check — domain=%s total_permutations=%d new_to_check=%d",
        domain, len(candidates), len(new_candidates),
    )

    registered: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_dns_resolves, d): d for d in new_candidates
        }
        try:
            for future in concurrent.futures.as_completed(
                future_map, timeout=overall_timeout
            ):
                d = future_map[future]
                try:
                    if future.result():
                        registered.append(d)
                except Exception as exc:
                    logger.debug("DNS check exception for %s: %s", d, exc)
        except concurrent.futures.TimeoutError:
            logger.warning(
                "Typosquat DNS check timed out after %.0f s for domain=%s",
                overall_timeout, domain,
            )

    logger.info(
        "Typosquat check complete — domain=%s new_lookalikes=%d",
        domain, len(registered),
    )
    return sorted(registered)


# ---------------------------------------------------------------------------
# MX record check (Cloudflare DNS-over-HTTPS)
# ---------------------------------------------------------------------------

DOH_URL = "https://cloudflare-dns.com/dns-query"


def get_mx_fingerprint(domain: str) -> str | None:
    """
    Query Cloudflare DoH for MX records. Returns a canonical sorted string
    suitable for fingerprinting, or None on failure.
    """
    url = f"{DOH_URL}?name={urllib.parse.quote(domain)}&type=MX"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/dns-json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data    = json.loads(resp.read())
            answers = [a["data"].strip().lower() for a in data.get("Answer", [])]
            return ",".join(sorted(answers)) if answers else ""
    except Exception as exc:
        logger.warning("MX check failed for %s: %s", domain, exc)
        return None


# ---------------------------------------------------------------------------
# Domain expiry check (RDAP)
# ---------------------------------------------------------------------------

RDAP_URL = "https://rdap.org/domain/{domain}"


def get_days_until_expiry(domain: str) -> int | None:
    """
    Query rdap.org for domain expiry date.
    Returns days until expiry (can be negative if expired), or None on failure.
    Covers .com, .net, .org, .io, .co, .us and most gTLDs.
    Does not cover all ccTLDs — gracefully returns None when unsupported.
    """
    url = RDAP_URL.format(domain=urllib.parse.quote(domain))
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        for event in data.get("events", []):
            if event.get("eventAction") == "expiration":
                expiry_str = event.get("eventDate", "")
                if expiry_str:
                    expiry_dt  = datetime.fromisoformat(
                        expiry_str.replace("Z", "+00:00")
                    )
                    now        = datetime.now(timezone.utc)
                    return (expiry_dt - now).days
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 400):
            logger.info("RDAP: no data for %s (code %d — ccTLD likely unsupported)", domain, exc.code)
        else:
            logger.warning("RDAP HTTP %d for %s", exc.code, domain)
    except Exception as exc:
        logger.warning("RDAP check failed for %s: %s", domain, exc)
    return None


def expiry_threshold_to_alert(days: int, already_alerted: int | None) -> int | None:
    """
    Return the threshold (7/14/30) to alert at, or None if no alert needed.
    Resets state when domain is clearly renewed (days > 60).
    """
    if days > 30:
        return None
    for threshold in EXPIRY_THRESHOLDS:  # [7, 14, 30]
        if days <= threshold:
            if already_alerted is None or already_alerted > threshold:
                return threshold
            return None  # already alerted at this or lower threshold
    return None


# ---------------------------------------------------------------------------
# WhatsApp delivery — freeform and template
# ---------------------------------------------------------------------------

def send_whatsapp(
    to_number: str,
    body: str,
    account_sid: str,
    auth_token: str,
    from_number: str,
) -> bool:
    url         = TWILIO_MESSAGES_URL.format(account_sid=account_sid)
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    to_wa   = to_number   if to_number.startswith("whatsapp:")   else f"whatsapp:{to_number}"
    from_wa = from_number if from_number.startswith("whatsapp:") else f"whatsapp:{from_number}"

    payload = urllib.parse.urlencode({
        "From": from_wa, "To": to_wa, "Body": body,
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type":  "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            logger.info("Freeform sent to %s sid=%s", to_number, result.get("sid"))
            return True
    except urllib.error.HTTPError as exc:
        logger.error("Twilio HTTP %d to %s: %s", exc.code, to_number, exc.read().decode("utf-8", errors="replace"))
        return False
    except Exception as exc:
        logger.exception("WhatsApp send failed to %s: %s", to_number, exc)
        return False


def send_whatsapp_template(
    to_number: str,
    content_sid: str,
    content_variables: dict,
    account_sid: str,
    auth_token: str,
    from_number: str,
) -> bool:
    if not content_sid:
        logger.warning("Template SID not set — skipping alert to %s", to_number)
        return False

    url         = TWILIO_MESSAGES_URL.format(account_sid=account_sid)
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    to_wa   = to_number   if to_number.startswith("whatsapp:")   else f"whatsapp:{to_number}"
    from_wa = from_number if from_number.startswith("whatsapp:") else f"whatsapp:{from_number}"

    payload = urllib.parse.urlencode({
        "From":             from_wa,
        "To":               to_wa,
        "ContentSid":       content_sid,
        "ContentVariables": json.dumps(content_variables),
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type":  "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            logger.info("Template sent to %s sid=%s", to_number, result.get("sid"))
            return True
    except urllib.error.HTTPError as exc:
        logger.error("Twilio template HTTP %d to %s: %s", exc.code, to_number, exc.read().decode("utf-8", errors="replace"))
        return False
    except Exception as exc:
        logger.exception("Template send failed to %s: %s", to_number, exc)
        return False


# ---------------------------------------------------------------------------
# Alert message builders (freeform — used for test_user_id mode)
# ---------------------------------------------------------------------------

def build_lookalike_alert(domain: str, new_lookalikes: list[str]) -> str:
    count   = len(new_lookalikes)
    listing = "\n".join(f"→ *{d}*" for d in new_lookalikes[:5])
    more    = f"\n(and {count - 5} more)" if count > 5 else ""
    return (
        f"⚠️ *Domain Alert — Lookalike Detected*\n\n"
        f"{count} domain{'s' if count > 1 else ''} impersonating *{domain}* "
        f"{'are' if count > 1 else 'is'} registered and active:\n\n"
        f"{listing}{more}\n\n"
        f"Lookalike domains are commonly used to send phishing emails that appear "
        f"to come from your business — targeting customers, employees, and vendors.\n\n"
        f"*Immediate steps:*\n"
        f"1. Check if it's actively hosting a site (paste into browser)\n"
        f"2. If live — report to the registrar's abuse team\n"
        f"3. Alert your team not to trust emails from these domains\n"
        f"4. Consider defensively registering the closest lookalikes\n\n"
        f"Reply *DOMAIN* to see your full domain security status.\n\n"
        f"🛡️ RelayShield"
    )


def build_mx_change_alert(domain: str, old_mx: str, new_mx: str) -> str:
    old_display = old_mx or "(none previously recorded)"
    new_display = new_mx or "(MX records removed)"
    return (
        f"⚠️ *Domain Alert — Email Configuration Changed*\n\n"
        f"The MX records for *{domain}* have changed. "
        f"MX records control where your email is delivered — an unexpected change "
        f"may indicate DNS hijacking or a compromised registrar account.\n\n"
        f"Previous: {old_display}\n"
        f"Current:  {new_display}\n\n"
        f"*Immediate steps:*\n"
        f"1. Log into your domain registrar NOW and check DNS settings\n"
        f"2. Verify MX records match your expected mail provider\n"
        f"3. Change your registrar password and enable 2FA immediately\n"
        f"4. Contact your IT provider if records don't match\n\n"
        f"Reply *DOMAIN SCAN* to re-check, or *DOMAIN* for full status.\n\n"
        f"🛡️ RelayShield"
    )


def build_expiry_alert(domain: str, days: int) -> str:
    if days <= 7:
        icon    = "🔴"
        urgency = "CRITICAL"
        advice  = "Renew *immediately* — do not wait."
    elif days <= 14:
        icon    = "🟠"
        urgency = "URGENT"
        advice  = "Renew in the next 24 hours."
    else:
        icon    = "⚠️"
        urgency = "Warning"
        advice  = "Renew now — enable auto-renew to prevent this risk in future."

    return (
        f"{icon} *Domain {urgency} — Renewal Required*\n\n"
        f"Your domain *{domain}* expires in *{days} day{'s' if days != 1 else ''}*.\n\n"
        f"If your domain lapses, anyone can register it — including attackers who can "
        f"use it to impersonate your business, intercept email, and send phishing "
        f"messages to your contacts.\n\n"
        f"{advice}\n\n"
        f"Log into your registrar and renew now. Enable auto-renew if not already set.\n\n"
        f"Reply *DOMAIN* for your full domain security status.\n\n"
        f"🛡️ RelayShield"
    )


# ---------------------------------------------------------------------------
# Per-domain scan logic
# ---------------------------------------------------------------------------

def scan_domain(
    domain: str,
    entry: dict,
    user_id: str,
    to_number: str,
    account_sid: str,
    auth_token: str,
    from_number: str,
    dry_run: bool,
    force_freeform: bool,
) -> dict:
    """
    Run all three checks for a single domain. Updates `entry` in place.
    Returns updated entry dict with last_scanned set.

    force_freeform=True bypasses template gate and sends freeform (used in test mode).
    """
    now = datetime.now(timezone.utc).isoformat()

    # --- 1. Typosquat check ---
    known = entry.get("known_lookalikes") or []
    new_lookalikes = find_active_lookalikes(domain, known_lookalikes=known)

    if new_lookalikes:
        logger.warning(
            "LOOKALIKE HIT — domain=%s new=%s", domain, new_lookalikes,
        )
        if not dry_run:
            if force_freeform:
                body = build_lookalike_alert(domain, new_lookalikes)
                send_whatsapp(to_number, body, account_sid, auth_token, from_number)
            else:
                count = len(new_lookalikes)
                send_whatsapp_template(
                    to_number,
                    DOMAIN_LOOKALIKE_TEMPLATE_SID,
                    {"1": domain, "2": new_lookalikes[0], "3": str(count)},
                    account_sid, auth_token, from_number,
                )
        # Always update known_lookalikes so we don't re-alert next run
        entry["known_lookalikes"] = list(set(known) | set(new_lookalikes))
    else:
        logger.info("Typosquat clear — domain=%s", domain)

    # --- 2. MX record check ---
    current_mx = get_mx_fingerprint(domain)
    stored_mx  = entry.get("mx_fingerprint")

    if current_mx is None:
        logger.warning("MX check failed for domain=%s — skipping", domain)
    elif stored_mx is None:
        # First run — record baseline, no alert
        logger.info("MX baseline recorded for domain=%s: %s", domain, current_mx)
        entry["mx_fingerprint"] = current_mx
    elif current_mx != stored_mx:
        logger.warning(
            "MX CHANGE — domain=%s old=%r new=%r", domain, stored_mx, current_mx,
        )
        if not dry_run:
            if force_freeform:
                body = build_mx_change_alert(domain, stored_mx, current_mx)
                send_whatsapp(to_number, body, account_sid, auth_token, from_number)
            else:
                detected_date = datetime.now(timezone.utc).strftime("%B %-d, %Y")
                send_whatsapp_template(
                    to_number,
                    DOMAIN_MX_CHANGE_TEMPLATE_SID,
                    {"1": domain, "2": detected_date},
                    account_sid, auth_token, from_number,
                )
        entry["mx_fingerprint"] = current_mx
    else:
        logger.info("MX unchanged — domain=%s fingerprint=%s", domain, current_mx)

    # --- 3. Expiry check ---
    days = get_days_until_expiry(domain)

    if days is None:
        logger.info("Expiry check unavailable for domain=%s (RDAP unsupported or failed)", domain)
    else:
        already_alerted = entry.get("expiry_days_alerted")

        # Reset alert state if domain was renewed (now safely far from expiry)
        if already_alerted is not None and days > 60:
            entry["expiry_days_alerted"] = None
            already_alerted = None
            logger.info("Expiry alert state reset for domain=%s (days=%d — likely renewed)", domain, days)

        threshold = expiry_threshold_to_alert(days, already_alerted)
        if threshold is not None:
            logger.warning(
                "EXPIRY ALERT — domain=%s days=%d threshold=%d", domain, days, threshold,
            )
            if not dry_run:
                if force_freeform:
                    body = build_expiry_alert(domain, days)
                    send_whatsapp(to_number, body, account_sid, auth_token, from_number)
                else:
                    urgency = "CRITICAL" if days <= 7 else "urgent" if days <= 14 else "soon"
                    send_whatsapp_template(
                        to_number,
                        DOMAIN_EXPIRY_TEMPLATE_SID,
                        {"1": domain, "2": str(days), "3": urgency},
                        account_sid, auth_token, from_number,
                    )
            entry["expiry_days_alerted"] = threshold
        else:
            logger.info(
                "Expiry OK or already alerted — domain=%s days=%d already_alerted=%s",
                domain, days, already_alerted,
            )

    entry["last_scanned"] = now
    return entry


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """
    Entry point for EventBridge daily trigger.

    Dry run — scans and logs, sends no WhatsApp alerts:
      { "dry_run": true }

    Force-test for a single admin user — full scan + freeform alerts
    (bypasses template gate, use before Meta approval to verify end-to-end):
      { "test_user_id": "user-onboard-test-001" }
    """
    logger.info("Domain monitor starting.")

    dry_run      = bool(event.get("dry_run", False))
    test_user_id = event.get("test_user_id", "")

    if dry_run:
        logger.info("DRY RUN — no WhatsApp alerts will be sent.")

    try:
        account_sid, auth_token, from_number = get_twilio_credentials()
    except Exception as exc:
        logger.exception("Failed to retrieve Twilio credentials: %s", exc)
        return {"statusCode": 500, "body": "Credential retrieval failed"}

    # ── Force-test mode ───────────────────────────────────────────────────
    if test_user_id:
        user = get_user_by_id(test_user_id)
        if not user:
            return {"statusCode": 404, "body": f"User {test_user_id} not found"}

        domains = user.get("monitored_domains") or []
        if not domains:
            return {"statusCode": 400, "body": f"User {test_user_id} has no monitored_domains"}

        to_number    = get_whatsapp_number(user)
        domain_state = load_domain_state(user)

        for domain in domains:
            entry = domain_state.get(domain) or blank_domain_entry()
            entry = scan_domain(
                domain=domain,
                entry=entry,
                user_id=test_user_id,
                to_number=to_number,
                account_sid=account_sid,
                auth_token=auth_token,
                from_number=from_number,
                dry_run=dry_run,
                force_freeform=True,
            )
            domain_state[domain] = entry

        update_domain_state(test_user_id, domain_state)
        logger.info("Force-test complete — user=%s domains=%s", test_user_id, domains)
        return {
            "statusCode": 200,
            "body": json.dumps({"test_user_id": test_user_id, "domains_scanned": domains}),
        }

    # ── Production mode ───────────────────────────────────────────────────
    admins = scan_domain_tier_admins()
    logger.info("Found %d domain-tier admin(s) with registered domains.", len(admins))

    total_scanned  = 0
    total_lookalike = 0
    total_mx        = 0
    total_expiry    = 0
    total_errors    = 0

    for user in admins:
        user_id      = user["user_id"]
        domains      = user.get("monitored_domains") or []
        tier         = user.get("subscription_tier", "")
        domain_state = load_domain_state(user)

        try:
            to_number = get_whatsapp_number(user)
        except Exception as exc:
            logger.exception("Phone resolution failed user_id=%s: %s", user_id, exc)
            total_errors += 1
            continue

        if not to_number or to_number == "whatsapp:":
            logger.warning("user_id=%s has no phone — skipping.", user_id)
            total_errors += 1
            continue

        for domain in domains:
            entry = domain_state.get(domain) or blank_domain_entry()

            # Track pre-scan state to count findings
            pre_lookalikes = len(entry.get("known_lookalikes") or [])
            pre_mx         = entry.get("mx_fingerprint")
            pre_expiry     = entry.get("expiry_days_alerted")

            try:
                entry = scan_domain(
                    domain=domain,
                    entry=entry,
                    user_id=user_id,
                    to_number=to_number,
                    account_sid=account_sid,
                    auth_token=auth_token,
                    from_number=from_number,
                    dry_run=dry_run,
                    force_freeform=False,
                )
            except Exception as exc:
                logger.exception(
                    "Domain scan error — user_id=%s domain=%s: %s", user_id, domain, exc
                )
                total_errors += 1
                continue

            domain_state[domain] = entry
            total_scanned += 1

            if len(entry.get("known_lookalikes") or []) > pre_lookalikes:
                total_lookalike += 1
            if pre_mx is not None and entry.get("mx_fingerprint") != pre_mx:
                total_mx += 1
            if entry.get("expiry_days_alerted") != pre_expiry and entry.get("expiry_days_alerted") is not None:
                total_expiry += 1

        # Persist updated state for this user
        try:
            update_domain_state(user_id, domain_state)
        except Exception as exc:
            logger.exception("State update failed for user_id=%s: %s", user_id, exc)
            total_errors += 1

    summary = {
        "admins_scanned":   len(admins),
        "domains_scanned":  total_scanned,
        "lookalike_alerts": total_lookalike,
        "mx_alerts":        total_mx,
        "expiry_alerts":    total_expiry,
        "errors":           total_errors,
    }
    logger.info("Domain monitor complete — %s", summary)

    return {"statusCode": 200, "body": json.dumps(summary)}
