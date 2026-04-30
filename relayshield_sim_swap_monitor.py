"""
RelayShield SIM/eSIM Swap Monitor Lambda

Runs on an EventBridge schedule (every 4 hours) to check all active users
with sim_swap_monitoring=True for SIM swap activity via Twilio Lookup v2.

Covers:
    - Physical SIM swap and eSIM provisioning events (IMSI change)
    - Port-out fraud: phone number transferred to a different carrier without
      authorisation — detected by carrier name change between checks

Alert severity:
    - SIM/eSIM swap detected:      HIGH — immediate carrier call required
    - Carrier change / port-out:   CRITICAL — all SMS 2FA compromised

Tiered alert content:
    personal_shield        — detection alert + carrier numbers + upgrade nudge
    business_basic/shield  — detection + carrier-specific hardening + eSIM audit
    business_shield_pro    — all above + eSIM disable guidance + FCC complaint

Business tiers (employee records):
    - Admin co-notification sent after employee alert is successfully delivered.

Deduplication:
    - `last_swap_alerted_at` ISO timestamp stored in relayshield_users.
      Alert suppressed if sent within the last 23 hours for the same user.
    - Port-out alerts bypass dedup — always fire on carrier change.

Port-out detection:
    - `last_known_carrier` stored in relayshield_users on every clean check.
    - When carrier changes from a known non-empty value, port-out is flagged.

Phone resolution:
    - Primary:  KMS decrypt of phone_encrypted (post-migration records)
    - Fallback: legacy plaintext whatsapp_number / phone_number field

Twilio Lookup v2 SIM Swap API:
    GET https://lookups.twilio.com/v2/PhoneNumbers/{phone}?Fields=sim_swap,carrier
    Auth: Basic (Account SID + Auth Token)
    Cost: ~$0.01 per query

Deployment:
    - Lambda name:   relayshield-sim-swap-monitor
    - Handler:       relayshield_sim_swap_monitor.lambda_handler
    - Trigger:       EventBridge rate(4 hours)
    - Runtime:       Python 3.12
    - Timeout:       300 seconds (5 minutes)
    - Memory:        128 MB
    - IAM requires:
        DynamoDB Scan + GetItem + UpdateItem on relayshield_users
        Secrets Manager GetSecretValue for Twilio credentials
        KMS Decrypt on alias/relayshield-data-key

Test payload (single-user, safe in production):
    { "test_user_id": "user-onboard-test-001" }

Force-test payload (simulates a positive swap for all monitored users):
    {
        "force_swap_test": true,
        "test_carrier": "T-Mobile",
        "test_swap_timestamp": "2026-04-25T12:00:00Z"
    }

Prerequisites before first deploy:
    1. Submit relayshield_sim_swap template to Meta for approval
       (3 variables: {{1}}=phone, {{2}}=swap time, {{3}}=carrier)
       Update SIM_SWAP_TEMPLATE_SID below once approved.
    2. Confirm Twilio account has Lookup v2 SIM Swap enabled
       (Twilio Console → Verify → SIM Swap)
"""

import base64
import json
import logging
import time
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
# AWS clients (module-level for Lambda container reuse)
# ---------------------------------------------------------------------------

secrets_client = boto3.client("secretsmanager")
dynamodb       = boto3.resource("dynamodb")
kms_client     = boto3.client("kms")

USERS_TABLE           = "relayshield_users"
KMS_PHONE_KEY_ALIAS   = "alias/relayshield-data-key"

# ---------------------------------------------------------------------------
# Twilio secrets
# ---------------------------------------------------------------------------

TWILIO_SID_SECRET   = "relayshield/twilio_account_sid"
TWILIO_TOKEN_SECRET = "relayshield/twilio_auth_token"
TWILIO_FROM_SECRET  = "relayshield/twilio_whatsapp_number"

TWILIO_LOOKUP_URL   = "https://lookups.twilio.com/v2/PhoneNumbers/{phone_number}"
TWILIO_MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

# ---------------------------------------------------------------------------
# SIM Swap WhatsApp template
# ---------------------------------------------------------------------------

# Update this SID once Meta approves the relayshield_sim_swap template.
#
# Template body (3 variables — submit exactly this text to Meta):
#
#   🚨 *SIM/eSIM Change Detected — RelayShield*
#
#   A SIM or eSIM change was detected on *{{1}}* at {{2}}.
#
#   Carrier detected: {{3}}
#
#   *If you did not authorise this, act immediately.*
#   Reply YES to receive carrier-specific steps, or call your carrier now:
#   AT&T: 1-800-331-0500 | T-Mobile: 1-800-937-8997 | Verizon: 1-800-922-0204
#
#   🛡️ RelayShield — SIM monitoring active
#
# Category: UTILITY (security alert, not promotional)
SIM_SWAP_TEMPLATE_SID = "HX9df8877e110384af8835931dfeeff954"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Dedup: suppress re-alerts for the same user within this window.
DEDUP_WINDOW_SECONDS = 23 * 3600  # 23 hours

# Small pause between Twilio Lookup calls to avoid rate limits.
LOOKUP_DELAY_SECONDS = 0.5

# Subscription tier constants
TIER_PERSONAL = "personal_shield"
TIER_STARTER  = "business_starter"
TIER_BASIC    = "business_basic"
TIER_SHIELD   = "business_shield"
TIER_PRO      = "business_shield_pro"
BUSINESS_TIERS = {TIER_STARTER, TIER_BASIC, TIER_SHIELD, TIER_PRO}


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
    """Return (account_sid, auth_token, from_whatsapp_number)."""
    account_sid = get_secret_json(TWILIO_SID_SECRET,   "TWILIO_ACCOUNT_SID")
    auth_token  = get_secret_json(TWILIO_TOKEN_SECRET,  "TWILIO_AUTH_TOKEN")
    from_number = get_secret_json(TWILIO_FROM_SECRET,   "TWILIO_WHATSAPP_NUMBER")
    return account_sid, auth_token, from_number


# ---------------------------------------------------------------------------
# Phone helpers
# ---------------------------------------------------------------------------

def decrypt_phone(ciphertext_b64: str) -> str:
    """KMS-decrypt a base64-encoded phone ciphertext. Returns E.164 string."""
    response = kms_client.decrypt(CiphertextBlob=base64.b64decode(ciphertext_b64))
    return response["Plaintext"].decode()


def get_e164_phone(user: dict) -> str:
    """
    Return E.164 phone number (no whatsapp: prefix).
    Primary:  KMS decrypt of phone_encrypted (post-migration records).
    Fallback: legacy plaintext phone_number / whatsapp_number fields.
    """
    if "phone_encrypted" in user:
        phone = decrypt_phone(user["phone_encrypted"])
        return phone.replace("whatsapp:", "").strip()
    # Legacy fields
    phone = (
        user.get("phone_number", "")
        or user.get("whatsapp_number", "").replace("whatsapp:", "")
    ).strip()
    if phone and not phone.startswith("+"):
        phone = f"+{phone}"
    return phone


def to_whatsapp_number(phone: str) -> str:
    if phone.startswith("whatsapp:"):
        return phone
    return f"whatsapp:{phone}"


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def scan_sim_swap_users() -> list[dict]:
    """Return all active users with sim_swap_monitoring = True."""
    table  = dynamodb.Table(USERS_TABLE)
    users: list[dict] = []
    kwargs: dict = {
        "FilterExpression": Attr("sim_swap_monitoring").eq(True) & Attr("active").eq(True),
    }
    while True:
        response = table.scan(**kwargs)
        users.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    logger.info("Found %d user(s) with SIM swap monitoring enabled.", len(users))
    return users


def get_user_by_id(user_id: str) -> dict | None:
    table    = dynamodb.Table(USERS_TABLE)
    response = table.get_item(Key={"user_id": user_id})
    return response.get("Item")


def update_user_swap_state(
    user_id: str,
    carrier_name: str,
    alert_fired: bool,
) -> None:
    """
    Persist carrier baseline and (when alert was sent) timestamp to the user record.
    Always updates last_known_carrier for port-out tracking.
    """
    table     = dynamodb.Table(USERS_TABLE)
    now_iso   = datetime.now(timezone.utc).isoformat()

    update_expr = "SET last_known_carrier = :c"
    expr_values: dict = {":c": carrier_name or "unknown"}

    if alert_fired:
        update_expr += ", last_swap_alerted_at = :t"
        expr_values[":t"] = now_iso

    table.update_item(
        Key={"user_id": user_id},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values,
    )


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def is_recently_alerted(user: dict) -> bool:
    """Return True if a swap alert was sent within DEDUP_WINDOW_SECONDS."""
    last_alerted = user.get("last_swap_alerted_at")
    if not last_alerted:
        return False
    try:
        last_dt     = datetime.fromisoformat(last_alerted.replace("Z", "+00:00"))
        age_seconds = (datetime.now(timezone.utc) - last_dt).total_seconds()
        return age_seconds < DEDUP_WINDOW_SECONDS
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Twilio Lookup v2 — SIM/eSIM Swap Detection
# ---------------------------------------------------------------------------

def call_twilio_sim_swap_lookup(
    phone_e164: str,
    account_sid: str,
    auth_token: str,
) -> dict | None:
    """
    Call Twilio Lookup v2 with Fields=sim_swap,carrier.

    Returns dict:
        swapped_in_period (bool)   — swap detected within the last 24 hours
        swap_event_timestamp (str) — ISO timestamp of the swap event (may be empty)
        carrier_name (str)         — current carrier name (may be empty)

    Both physical SIM swaps and eSIM provisioning events are detected via
    IMSI change — the same Lookup call covers both.

    Returns None on HTTP or network error.
    """
    encoded = urllib.parse.quote(phone_e164, safe="")
    url     = (
        TWILIO_LOOKUP_URL.format(phone_number=encoded)
        + "?Fields=sim_swap"
    )
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()

    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Basic {credentials}", "Accept": "application/json"},
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body         = json.loads(resp.read())
            sim_swap_obj = body.get("sim_swap") or {}
            last_swap    = sim_swap_obj.get("last_sim_swap") or {}

            result = {
                "swapped_in_period":    bool(last_swap.get("swapped_in_period", False)),
                "swap_event_timestamp": last_swap.get("last_sim_swap_date", ""),
                "carrier_name":         sim_swap_obj.get("carrier_name", ""),
            }
            logger.info(
                "Twilio Lookup %s — swapped=%s carrier=%s",
                phone_e164, result["swapped_in_period"], result["carrier_name"] or "unknown",
            )
            return result

    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Twilio Lookup HTTP %d for %s: %s", exc.code, phone_e164, error_body)
        return None
    except Exception as exc:
        logger.exception("Twilio Lookup failed for %s: %s", phone_e164, exc)
        return None


# ---------------------------------------------------------------------------
# Alert message builders — tiered by subscription plan
# ---------------------------------------------------------------------------

def _carrier_hardening_block(carrier_name: str) -> str:
    """Carrier-specific hardening steps for Business tiers."""
    carrier_upper = (carrier_name or "").upper()

    if "AT&T" in carrier_upper or carrier_upper == "ATT":
        return (
            "*AT&T — Steps to take now:*\n"
            "→ Call AT&T: *1-800-331-0500* — report unauthorised SIM change\n"
            "→ myAT&T app → Account → Device → *Wireless Account Lock* → Enable\n"
            "→ Audit eSIM profiles: myAT&T → Device → *Manage eSIM*\n"
            "  → Revoke any profiles you did not add"
        )
    if "T-MOBILE" in carrier_upper or "TMOBILE" in carrier_upper:
        return (
            "*T-Mobile — Steps to take now:*\n"
            "→ Call T-Mobile: *1-800-937-8997* — report unauthorised SIM change\n"
            "→ T-Mobile app → Account → Lines → *SIM Protection* → Enable\n"
            "→ Audit eSIM profiles: T-Mobile app → Lines → *eSIM Profiles*\n"
            "  → Revoke any profiles you did not add"
        )
    if "VERIZON" in carrier_upper:
        return (
            "*Verizon — Steps to take now:*\n"
            "→ Call Verizon: *1-800-922-0204* — report unauthorised SIM change\n"
            "→ My Verizon app → Device → *Number Lock* → Enable\n"
            "→ Audit eSIM profiles: My Verizon → Device → *eSIM Management*\n"
            "  → Revoke any profiles you did not add"
        )
    # Unknown / unsupported carrier
    return (
        "*Carrier hardening steps:*\n"
        "→ Call your carrier immediately and report an unauthorised SIM change\n"
        "  AT&T: 1-800-331-0500 | T-Mobile: 1-800-937-8997 | Verizon: 1-800-922-0204\n"
        "→ Request a SIM lock / Number lock on your account\n"
        "→ Check your carrier app for unauthorised eSIM profiles and revoke them"
    )


def build_sim_swap_alert_message(
    phone_number: str,
    subscription_tier: str,
    carrier_name: str,
    swap_event_timestamp: str,
) -> str:
    """
    Build the tiered WhatsApp alert body (freeform).

    Personal Shield        — detection + carrier numbers + upgrade nudge
    Business Basic/Shield  — detection + carrier-specific hardening + eSIM audit
    Business Shield Pro    — all above + eSIM disable guidance + FCC complaint
    """
    try:
        dt       = datetime.fromisoformat(swap_event_timestamp.replace("Z", "+00:00"))
        time_str = dt.strftime("%H:%M UTC on %d %b %Y")
    except Exception:
        time_str = swap_event_timestamp or "unknown time"

    header = (
        f"🚨 *SIM/eSIM Change Detected — RelayShield*\n\n"
        f"A SIM or eSIM change was detected on *{phone_number}* at {time_str}.\n\n"
        f"*If you did not authorise this, act immediately.*\n\n"
    )

    # ── Personal Shield ────────────────────────────────────────────────────
    if subscription_tier not in BUSINESS_TIERS:
        return (
            header
            + "*Call your carrier immediately:*\n"
            + "→ AT&T: 1-800-331-0500\n"
            + "→ T-Mobile: 1-800-937-8997\n"
            + "→ Verizon: 1-800-922-0204\n\n"
            + 'Say: _"I did not authorise a SIM or eSIM change on my account."_\n\n'
            + "Reply *PHONE* for carrier-specific SIM lock steps.\n"
            + "Reply *SWEEP* to audit your inbox for backdoors left by attackers.\n\n"
            + "⬆️ Upgrade to Business Shield for carrier-specific hardening steps and eSIM audit guidance.\n\n"
            + "🛡️ RelayShield"
        )

    # ── Business Basic / Business Shield ──────────────────────────────────
    hardening     = _carrier_hardening_block(carrier_name)
    account_steps = (
        "\n\n*Secure your accounts:*\n"
        "→ Change passwords on any account using SMS two-factor authentication\n"
        "→ Reply *SWEEP* to audit your email inbox for backdoors\n"
        "→ Enable an authenticator app (Google Authenticator / Authy) on all key accounts"
    )

    if subscription_tier != TIER_PRO:
        return header + hardening + account_steps + "\n\n🛡️ RelayShield"

    # ── Business Shield Pro — adds eSIM disable + FCC complaint ───────────
    esim_disable = (
        "\n\n*Disable remote eSIM provisioning (strongest protection):*\n"
        "→ AT&T: Contact AT&T support to disable remote eSIM provisioning on your account\n"
        "→ T-Mobile: Visit a T-Mobile store with photo ID to restrict eSIM provisioning\n"
        "→ Verizon: Call 1-800-922-0204 and request eSIM provisioning restriction"
    )
    fcc_block = (
        "\n\n*File an FCC complaint:*\n"
        "→ fcc.gov/consumers/guides/filing-informal-complaint\n"
        "→ Carriers are legally required to respond within 30 days\n"
        "→ Creates a formal audit trail and accelerates carrier response"
    )

    return header + hardening + account_steps + esim_disable + fcc_block + "\n\n🛡️ RelayShield"


def build_port_out_alert_message(
    phone_number: str,
    old_carrier: str,
    new_carrier: str,
    subscription_tier: str,
) -> str:
    """CRITICAL alert body for suspected port-out fraud."""
    if old_carrier and new_carrier:
        change_line = f"transferred from *{old_carrier}* to *{new_carrier}*"
    else:
        change_line = "transferred to a new carrier"

    header = (
        f"🚨 *CRITICAL — Possible Port-Out Fraud: {phone_number}*\n\n"
        f"Your phone number appears to have been {change_line}.\n\n"
        f"Port-out fraud gives attackers full control of your incoming calls and SMS — "
        f"including all OTP codes and account recovery messages.\n\n"
    )

    base_steps = (
        f"*Act immediately:*\n"
        f"1️⃣ Call *{old_carrier or 'your original carrier'}*: report an unauthorised port-out\n"
        f"2️⃣ Request a port-back and freeze your account against further changes\n"
        f"3️⃣ Contact your bank and email provider — treat all SMS two-factor as compromised\n"
        f"4️⃣ Do not rely on SMS for any authentication until your number is restored\n\n"
        f"Reply *PHONE* for carrier fraud escalation numbers."
    )

    if subscription_tier == TIER_PRO:
        fcc_note = (
            "\n\n*File an FCC complaint:*\n"
            "→ fcc.gov/consumers/guides/filing-informal-complaint\n"
            "→ Creates a formal record — carriers must respond within 30 days"
        )
        return header + base_steps + fcc_note + "\n\n🛡️ RelayShield — CRITICAL alert"

    return header + base_steps + "\n\n🛡️ RelayShield — CRITICAL alert"


def build_admin_swap_notification(
    employee_name: str,
    phone_last4: str,
    carrier_name: str,
    alert_type: str,
    old_carrier: str = "",
) -> str:
    """Admin co-notification body for employee SIM swap or port-out."""
    name_str = employee_name if employee_name else f"a team member (···{phone_last4})"

    if alert_type == "port_out":
        change_line = (
            f"from *{old_carrier}* to *{carrier_name}*"
            if (old_carrier and carrier_name)
            else "to a new carrier"
        )
        return (
            f"🚨 *CRITICAL — Port-Out Fraud Detected: {name_str}*\n\n"
            f"A possible port-out fraud has been detected on {name_str}'s phone number "
            f"({change_line}).\n\n"
            f"Their mobile number may have been transferred without authorisation — "
            f"all SMS two-factor authentication on their accounts is potentially compromised.\n\n"
            f"*Recommended action:*\n"
            f"Contact {name_str} immediately and direct them to call their carrier to report "
            f"the fraud and request a port-back. Consider restricting access to sensitive "
            f"systems until resolved.\n\n"
            f"🛡️ RelayShield — admin CRITICAL alert"
        )

    carrier_line = f" on *{carrier_name}*" if carrier_name else ""
    return (
        f"⚠️ *SIM/eSIM Swap Alert: {name_str}*\n\n"
        f"A SIM or eSIM change was detected on {name_str}'s phone number{carrier_line}.\n\n"
        f"{name_str} has been sent immediate action steps. "
        f"Consider restricting access to sensitive systems until they confirm the change "
        f"was authorised.\n\n"
        f"🛡️ RelayShield — admin alert"
    )


# ---------------------------------------------------------------------------
# WhatsApp delivery
# ---------------------------------------------------------------------------

def send_whatsapp(
    to_number: str,
    body: str,
    account_sid: str,
    auth_token: str,
    from_number: str,
) -> bool:
    """Send a freeform WhatsApp message. Returns True on success."""
    url         = TWILIO_MESSAGES_URL.format(account_sid=account_sid)
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()

    payload = urllib.parse.urlencode({
        "From": to_whatsapp_number(from_number),
        "To":   to_whatsapp_number(to_number),
        "Body": body,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type":  "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            logger.info("WhatsApp sent to %s SID: %s", to_number, result.get("sid"))
            return True
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Twilio HTTP %d to %s: %s", exc.code, to_number, error_body)
        return False
    except Exception as exc:
        logger.exception("WhatsApp send failed to %s: %s", to_number, exc)
        return False


# ---------------------------------------------------------------------------
# Per-user processing
# ---------------------------------------------------------------------------

def process_user(
    user: dict,
    account_sid: str,
    auth_token: str,
    from_number: str,
    user_cache: dict,
) -> str:
    """
    Check one user for SIM swap / port-out and fire alerts as needed.
    Returns one of: "sim_swap" | "port_out" | "clean" | "skipped" | "error"
    """
    user_id = user.get("user_id", "unknown")

    # Resolve phone
    try:
        phone_e164 = get_e164_phone(user)
    except Exception as exc:
        logger.exception("Phone decryption failed user_id=%s: %s", user_id, exc)
        return "error"

    if not phone_e164:
        logger.warning("user_id=%s has no phone number — skipping.", user_id)
        return "skipped"

    # Query Twilio Lookup
    lookup = call_twilio_sim_swap_lookup(phone_e164, account_sid, auth_token)
    if lookup is None:
        return "error"

    swapped             = lookup["swapped_in_period"]
    swap_ts             = lookup["swap_event_timestamp"]
    carrier_name        = lookup["carrier_name"]
    last_known_carrier  = user.get("last_known_carrier", "")

    # Port-out detection: carrier changed from a known non-empty value
    port_out_suspected = bool(
        last_known_carrier
        and carrier_name
        and last_known_carrier not in ("unknown", "")
        and last_known_carrier != carrier_name
    )

    # Nothing to report
    if not swapped and not port_out_suspected:
        if carrier_name and carrier_name != last_known_carrier:
            update_user_swap_state(user_id, carrier_name, alert_fired=False)
        return "clean"

    # Dedup (port-out always fires; swap deduped by 23-hr window)
    if not port_out_suspected and is_recently_alerted(user):
        logger.info("user_id=%s swap recently alerted — suppressed.", user_id)
        return "skipped"

    alert_type        = "port_out" if port_out_suspected else "sim_swap"
    subscription_tier = user.get("subscription_tier", TIER_PERSONAL)

    # Build user alert body
    if alert_type == "port_out":
        body = build_port_out_alert_message(
            phone_e164, last_known_carrier, carrier_name, subscription_tier
        )
    else:
        body = build_sim_swap_alert_message(
            phone_e164, subscription_tier, carrier_name, swap_ts
        )

    # Send to user
    sent = send_whatsapp(
        to_whatsapp_number(phone_e164), body, account_sid, auth_token, from_number
    )

    if sent:
        update_user_swap_state(user_id, carrier_name, alert_fired=True)
        logger.warning(
            "Alert sent — user_id=%s alert_type=%s carrier=%s",
            user_id, alert_type, carrier_name,
        )

        # Admin co-notification for business-tier employee records
        is_employee = bool(user.get("admin_user_id"))
        if is_employee and subscription_tier in BUSINESS_TIERS:
            admin_user_id = user.get("admin_user_id")
            if admin_user_id:
                admin_record = user_cache.get(admin_user_id)
                if admin_record is None:
                    admin_record = get_user_by_id(admin_user_id)
                    user_cache[admin_user_id] = admin_record

                if admin_record and admin_record.get("active"):
                    try:
                        admin_phone = get_e164_phone(admin_record)
                        if admin_phone:
                            phone_last4   = phone_e164[-4:] if len(phone_e164) >= 4 else phone_e164
                            employee_name = user.get("employee_name", "")
                            admin_body    = build_admin_swap_notification(
                                employee_name, phone_last4, carrier_name,
                                alert_type, old_carrier=last_known_carrier,
                            )
                            admin_sent = send_whatsapp(
                                to_whatsapp_number(admin_phone),
                                admin_body,
                                account_sid, auth_token, from_number,
                            )
                            logger.info(
                                "Admin co-notification — admin_user_id=%s employee=%s sent=%s",
                                admin_user_id, user_id, admin_sent,
                            )
                    except Exception as exc:
                        logger.exception(
                            "Admin co-notification failed admin_user_id=%s: %s",
                            admin_user_id, exc,
                        )
    else:
        logger.error("Alert send failed — user_id=%s alert_type=%s", user_id, alert_type)

    return alert_type if sent else "error"


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """
    Entry point for EventBridge scheduled trigger (rate: 4 hours).

    Single-user test (safe in production):
        { "test_user_id": "user-onboard-test-001" }

    Force-test mode (simulates a positive swap for all monitored users):
        {
            "force_swap_test": true,
            "test_carrier": "T-Mobile",
            "test_swap_timestamp": "2026-04-25T12:00:00Z"
        }
    """
    logger.info("RelayShield SIM/eSIM swap monitor starting.")
    start_time = time.time()

    # Load Twilio credentials once per invocation
    try:
        account_sid, auth_token, from_number = get_twilio_credentials()
    except Exception as exc:
        logger.exception("Failed to retrieve Twilio credentials: %s", exc)
        return {"statusCode": 500, "body": "Credential retrieval failed"}

    # Determine user list
    test_user_id = event.get("test_user_id")
    force_test   = bool(event.get("force_swap_test", False))

    if test_user_id:
        user  = get_user_by_id(test_user_id)
        users = [user] if user else []
        logger.info("Single-user test mode: %s", test_user_id)
    else:
        try:
            users = scan_sim_swap_users()
        except Exception as exc:
            logger.exception("Failed to scan users table: %s", exc)
            return {"statusCode": 500, "body": "DynamoDB scan failed"}

    if not users:
        logger.info("No users with SIM swap monitoring enabled — nothing to check.")
        return {"statusCode": 200, "body": json.dumps({"users_checked": 0})}

    counters: dict[str, int] = {
        "sim_swap": 0, "port_out": 0,
        "clean":    0, "skipped": 0, "error": 0,
    }
    user_cache: dict = {}

    if force_test:
        # ── Force-test: inject a simulated swap for every monitored user ──
        logger.warning("FORCE SWAP TEST MODE — simulating positive detection.")
        test_carrier   = event.get("test_carrier", "T-Mobile")
        test_timestamp = event.get(
            "test_swap_timestamp",
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        for user in users:
            user_id           = user.get("user_id", "unknown")
            subscription_tier = user.get("subscription_tier", TIER_PERSONAL)
            try:
                phone_e164 = get_e164_phone(user)
            except Exception as exc:
                logger.exception("Phone decrypt failed user_id=%s: %s", user_id, exc)
                counters["error"] += 1
                continue

            if not phone_e164:
                counters["skipped"] += 1
                continue

            body = build_sim_swap_alert_message(
                phone_e164, subscription_tier, test_carrier, test_timestamp
            )
            sent = send_whatsapp(
                to_whatsapp_number(phone_e164), body, account_sid, auth_token, from_number
            )
            counters["sim_swap" if sent else "error"] += 1
            logger.info(
                "TEST alert — user_id=%s carrier=%s sent=%s", user_id, test_carrier, sent
            )

    else:
        # ── Production mode ───────────────────────────────────────────────
        for index, user in enumerate(users):
            if index > 0:
                time.sleep(LOOKUP_DELAY_SECONDS)
            try:
                outcome = process_user(user, account_sid, auth_token, from_number, user_cache)
                counters[outcome] = counters.get(outcome, 0) + 1
            except Exception as exc:
                logger.exception(
                    "Unhandled error processing user_id=%s: %s",
                    user.get("user_id", "unknown"), exc,
                )
                counters["error"] += 1

    elapsed = round(time.time() - start_time, 2)
    logger.info(
        "SIM swap monitor complete — sim_swap=%d port_out=%d clean=%d "
        "skipped=%d error=%d elapsed=%ss",
        counters["sim_swap"], counters["port_out"], counters["clean"],
        counters["skipped"], counters["error"], elapsed,
    )

    return {"statusCode": 200, "body": json.dumps(counters)}
