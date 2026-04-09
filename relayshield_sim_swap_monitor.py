"""
RelayShield SIM/eSIM Swap Monitor Lambda

Scans monitored phone numbers for SIM swap and eSIM provisioning events
via Twilio Lookup v2. Records new swap events in DynamoDB and sends
tiered WhatsApp alerts based on subscription plan.

Tier behaviour:
  personal_shield      — Detection alert only: call your carrier numbers
  business_basic       — Detection + carrier-specific hardening + eSIM audit
  business_shield      — Same as business_basic (per-employee monitoring)
  business_shield_pro  — Full hardening + SIM lock + eSIM disable guidance
                         + FCC complaint steps

DynamoDB tables used:
  relayshield_users            — source of monitored phone numbers and tiers
  relayshield_sim_swap_alerts  — audit trail and de-duplication store

New fields required in relayshield_users:
  sim_swap_monitoring  Boolean  — True to monitor this user (default False)
  phone_number         String   — E.164 format (+1XXXXXXXXXX); falls back to
                                  whatsapp_number with 'whatsapp:' stripped
  subscription_tier    String   — personal_shield | business_basic |
                                  business_shield | business_shield_pro

EventBridge schedule: rate(1 hour)  [more frequent than daily breach check
given the time-sensitivity of SIM swap attacks]
"""

import base64
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

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
dynamodb = boto3.resource("dynamodb")

USERS_TABLE = "relayshield_users"
SIM_SWAP_ALERTS_TABLE = "relayshield_sim_swap_alerts"

# Secrets (reuse existing Twilio credentials — no new secrets required)
TWILIO_SID_SECRET = "relayshield/twilio_account_sid"
TWILIO_TOKEN_SECRET = "relayshield/twilio_auth_token"
TWILIO_FROM_SECRET = "relayshield/twilio_whatsapp_number"

# Twilio endpoints
TWILIO_LOOKUP_URL = "https://lookups.twilio.com/v2/PhoneNumbers/{phone_number}"
TWILIO_MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

# WhatsApp Message Template — pre-approved by Meta, always deliverable
# regardless of the 24-hour messaging window.
# Variables: {{1}}=phone number, {{2}}=swap time, {{3}}=carrier name
SIM_SWAP_TEMPLATE_SID = "HX9df8877e110384af8835931dfeeff954"

# De-duplication: suppress re-alerts for the same swap event within this window
DEDUP_WINDOW_HOURS = 23

# Small delay between Twilio Lookup calls to avoid rate limits
LOOKUP_DELAY_SECONDS = 0.5

# Subscription tier constants
TIER_PERSONAL = "personal_shield"
TIER_BASIC = "business_basic"
TIER_SHIELD = "business_shield"
TIER_PRO = "business_shield_pro"
BUSINESS_TIERS = {TIER_BASIC, TIER_SHIELD, TIER_PRO}


# ---------------------------------------------------------------------------
# Secrets Manager
# ---------------------------------------------------------------------------

def get_secret_plaintext(secret_name: str) -> str:
    """Retrieve the raw string value from a plaintext secret."""
    logger.info("Retrieving secret: %s", secret_name)
    response = secrets_client.get_secret_value(SecretId=secret_name)
    return response["SecretString"].strip()


def get_twilio_credentials() -> tuple[str, str, str]:
    """Return (account_sid, auth_token, from_whatsapp_number)."""
    account_sid = get_secret_plaintext(TWILIO_SID_SECRET)
    auth_token = get_secret_plaintext(TWILIO_TOKEN_SECRET)
    from_number = get_secret_plaintext(TWILIO_FROM_SECRET)
    logger.info("Twilio credentials retrieved successfully.")
    return account_sid, auth_token, from_number


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def scan_users_with_sim_monitoring() -> list[dict]:
    """Return all users with sim_swap_monitoring = True."""
    table = dynamodb.Table(USERS_TABLE)
    items: list[dict] = []
    kwargs: dict = {
        "FilterExpression": Attr("sim_swap_monitoring").eq(True),
    }
    while True:
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    logger.info("Found %d user(s) with SIM swap monitoring enabled.", len(items))
    return items


def get_phone_number_for_user(user: dict) -> str | None:
    """
    Return the E.164 phone number to monitor for this user.
    Uses 'phone_number' if set; falls back to stripping 'whatsapp:' from
    'whatsapp_number'. Ensures + prefix. Returns None if unavailable.
    """
    phone = user.get("phone_number") or ""
    if not phone:
        whatsapp = user.get("whatsapp_number", "")
        phone = whatsapp.replace("whatsapp:", "").strip()
    if not phone:
        return None
    if not phone.startswith("+"):
        phone = f"+{phone}"
    return phone


def get_whatsapp_number_for_user(user: dict) -> str | None:
    """Return the 'whatsapp:'-prefixed number for sending alerts."""
    number = user.get("whatsapp_number", "")
    if not number:
        return None
    if not number.startswith("whatsapp:"):
        number = f"whatsapp:{number}"
    return number


def already_alerted_for_swap(phone_number: str, swap_event_timestamp: str) -> bool:
    """
    Return True if we have already sent an alert for this exact swap event
    (same phone_number + same swap_event_timestamp) within DEDUP_WINDOW_HOURS.
    Prevents re-alerting on every hourly check after the first detection.
    """
    table = dynamodb.Table(SIM_SWAP_ALERTS_TABLE)
    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=DEDUP_WINDOW_HOURS)
    ).isoformat()

    response = table.scan(
        FilterExpression=(
            Attr("phone_number").eq(phone_number)
            & Attr("detected_at").gte(cutoff)
        )
    )
    items = response.get("Items", [])

    if not items:
        return False

    for item in items:
        if item.get("swap_event_timestamp") == swap_event_timestamp:
            logger.info(
                "Duplicate suppressed: phone=%s swap_event_timestamp=%s already alerted.",
                phone_number,
                swap_event_timestamp,
            )
            return True

    return False


def write_sim_swap_alert(
    user_id: str,
    phone_number: str,
    swap_event_timestamp: str,
    carrier_name: str,
    subscription_tier: str,
    alert_sent: bool,
) -> str:
    """Persist a SIM swap alert record. Returns alert_id."""
    table = dynamodb.Table(SIM_SWAP_ALERTS_TABLE)
    alert_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "alert_id": alert_id,
        "user_id": user_id,
        "phone_number": phone_number,
        "swap_event_timestamp": swap_event_timestamp,
        "carrier_name": carrier_name,
        "subscription_tier": subscription_tier,
        "detected_at": now,
        "alert_sent": alert_sent,
        "remediation_status": "pending",
    }
    table.put_item(Item=item)
    logger.info(
        "Wrote SIM swap alert %s — user=%s phone=%s",
        alert_id, user_id, phone_number,
    )
    return alert_id


# ---------------------------------------------------------------------------
# Twilio Lookup v2 — SIM/eSIM Swap Detection
# ---------------------------------------------------------------------------

def call_twilio_sim_swap_lookup(
    phone_number: str,
    account_sid: str,
    auth_token: str,
) -> dict | None:
    """
    Call Twilio Lookup v2 with Fields=sim_swap,carrier for the given number.

    Returns dict:
      sim_swap     — Twilio sim_swap object (swapped_in_period, last_sim_swap_date)
                     or None if the carrier does not support detection
      carrier_name — carrier name string (e.g. "AT&T", "T-Mobile", "Verizon")

    Both physical SIM swaps and eSIM provisioning events are detected via
    IMSI change — the same Lookup call covers both.

    Returns None on HTTP or network error.
    """
    encoded = urllib.parse.quote(phone_number)
    url = (
        TWILIO_LOOKUP_URL.format(phone_number=encoded)
        + "?Fields=sim_swap,carrier"
    )

    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Accept": "application/json",
    }

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
            sim_swap = body.get("sim_swap")
            carrier = body.get("carrier") or {}
            carrier_name = carrier.get("name", "")
            logger.info(
                "Twilio Lookup for %s: sim_swap=%s carrier=%s",
                phone_number,
                sim_swap,
                carrier_name or "unknown",
            )
            return {"sim_swap": sim_swap, "carrier_name": carrier_name}

    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error(
            "Twilio Lookup HTTP %d for %s: %s", exc.code, phone_number, error_body
        )
        return None

    except Exception as exc:
        logger.exception(
            "Unexpected error in Twilio Lookup for %s: %s", phone_number, exc
        )
        return None


# ---------------------------------------------------------------------------
# Alert message builder — tiered by subscription plan
# ---------------------------------------------------------------------------

def _carrier_hardening_block(carrier_name: str) -> str:
    """
    Return carrier-specific hardening steps for Business tiers.
    Falls back to generic multi-carrier block when carrier is unknown.
    """
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

    # Unknown carrier
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
    Build the tiered WhatsApp alert message.

    Personal Shield  → detection + carrier numbers only + upgrade nudge
    Business Basic/Shield → detection + carrier hardening + eSIM audit
    Business Shield Pro   → all above + eSIM disable guidance + FCC complaint
    """
    # Format timestamp for human-readable display
    try:
        dt = datetime.fromisoformat(swap_event_timestamp.replace("Z", "+00:00"))
        time_str = dt.strftime("%H:%M UTC on %d %b %Y")
    except Exception:
        time_str = swap_event_timestamp or "unknown time"

    # Header — all tiers
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
            + "Reply *SWEEP* to also audit your email inbox for backdoors left by attackers.\n\n"
            + "⬆️ Upgrade to Business Shield for carrier-specific hardening steps and eSIM audit guidance.\n\n"
            + "— RelayShield"
        )

    # ── Business Basic / Business Shield ──────────────────────────────────
    hardening = _carrier_hardening_block(carrier_name)

    account_steps = (
        "\n\n*Secure your accounts:*\n"
        "→ Change passwords on accounts using SMS two-factor authentication\n"
        "→ Reply *SWEEP* to audit your email inbox for backdoors\n"
        "→ Enable an authenticator app (Google Authenticator / Authy) on all key accounts"
    )

    if subscription_tier != TIER_PRO:
        return header + hardening + account_steps + "\n\n— RelayShield"

    # ── Business Shield Pro — adds eSIM disable + FCC ─────────────────────
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
        "→ FCC complaints create a formal audit trail and accelerate carrier response"
    )

    return header + hardening + account_steps + esim_disable + fcc_block + "\n\n— RelayShield"


# ---------------------------------------------------------------------------
# Twilio WhatsApp delivery
# ---------------------------------------------------------------------------

def send_whatsapp_alert(
    account_sid: str,
    auth_token: str,
    from_number: str,
    to_number: str,
    phone_number: str,
    swap_time_str: str,
    carrier_name: str,
) -> bool:
    """
    Send a SIM swap alert via pre-approved WhatsApp Message Template.
    Always deliverable regardless of the 24-hour messaging window.

    Variables:
        {{1}} = phone number being monitored
        {{2}} = swap detected time (human-readable)
        {{3}} = carrier name
    """
    url = TWILIO_MESSAGES_URL.format(account_sid=account_sid)

    content_variables = json.dumps({
        "1": phone_number,
        "2": swap_time_str,
        "3": carrier_name or "Unknown carrier",
    })

    payload = urllib.parse.urlencode({
        "From": from_number,
        "To": to_number,
        "ContentSid": SIM_SWAP_TEMPLATE_SID,
        "ContentVariables": content_variables,
    }).encode("utf-8")

    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
            sid = body.get("sid", "unknown")
            logger.info(
                "SIM swap template alert sent to %s. Twilio SID: %s", to_number, sid
            )
            return True
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.error(
            "Twilio HTTP %d sending SIM swap template to %s: %s",
            exc.code, to_number, error_body,
        )
        return False
    except Exception as exc:
        logger.exception(
            "Unexpected error sending WhatsApp template to %s: %s", to_number, exc
        )
        return False


# ---------------------------------------------------------------------------
# Core per-user processing
# ---------------------------------------------------------------------------

def process_user_sim_swap(
    user: dict,
    twilio_creds: tuple[str, str, str],
) -> dict | None:
    """
    Check one user's phone number for SIM/eSIM swap events.
    Writes to DynamoDB and sends WhatsApp alert if a new swap is detected.
    Returns a summary dict on alert, None otherwise.
    """
    user_id = user.get("user_id", "unknown")
    subscription_tier = user.get("subscription_tier", TIER_PERSONAL)

    phone_number = get_phone_number_for_user(user)
    if not phone_number:
        logger.warning("user_id=%s has no resolvable phone_number — skipping.", user_id)
        return None

    whatsapp_to = get_whatsapp_number_for_user(user)
    if not whatsapp_to:
        logger.warning("user_id=%s has no whatsapp_number — skipping.", user_id)
        return None

    account_sid, auth_token, from_number = twilio_creds

    # Query Twilio Lookup v2 for SIM/eSIM change
    lookup_result = call_twilio_sim_swap_lookup(phone_number, account_sid, auth_token)
    if lookup_result is None:
        logger.warning(
            "Twilio Lookup failed for user_id=%s phone=%s — skipping.",
            user_id, phone_number,
        )
        return None

    sim_swap = lookup_result.get("sim_swap")
    carrier_name = lookup_result.get("carrier_name", "")

    # Carrier may not support SIM swap detection
    if not sim_swap:
        logger.info(
            "No SIM swap data for phone=%s — carrier may not support detection.",
            phone_number,
        )
        return None

    swapped = sim_swap.get("swapped_in_period", False)
    swap_event_timestamp = sim_swap.get("last_sim_swap_date") or ""

    if not swapped:
        logger.info("No SIM/eSIM swap detected for phone=%s.", phone_number)
        return None

    logger.warning(
        "🚨 SIM/eSIM swap DETECTED — user_id=%s phone=%s swap_at=%s carrier=%s tier=%s",
        user_id, phone_number, swap_event_timestamp, carrier_name or "unknown",
        subscription_tier,
    )

    # De-duplication: skip if already alerted for this exact swap event
    if swap_event_timestamp and already_alerted_for_swap(phone_number, swap_event_timestamp):
        return None

    # Format swap time for template variable {{2}}
    try:
        dt = datetime.fromisoformat(swap_event_timestamp.replace("Z", "+00:00"))
        swap_time_str = dt.strftime("%H:%M UTC on %d %b %Y")
    except Exception:
        swap_time_str = swap_event_timestamp or "unknown time"

    # Send via pre-approved WhatsApp template (always deliverable)
    sent = send_whatsapp_alert(
        account_sid=account_sid,
        auth_token=auth_token,
        from_number=from_number,
        to_number=whatsapp_to,
        phone_number=phone_number,
        swap_time_str=swap_time_str,
        carrier_name=carrier_name,
    )

    if not sent:
        logger.warning(
            "WhatsApp delivery failed for user_id=%s — alert still written to DynamoDB.",
            user_id,
        )

    # Always persist to DynamoDB (audit trail even if delivery fails)
    alert_id = write_sim_swap_alert(
        user_id=user_id,
        phone_number=phone_number,
        swap_event_timestamp=swap_event_timestamp,
        carrier_name=carrier_name,
        subscription_tier=subscription_tier,
        alert_sent=sent,
    )

    return {
        "alert_id": alert_id,
        "user_id": user_id,
        "phone_number": phone_number,
        "swap_event_timestamp": swap_event_timestamp,
        "carrier_name": carrier_name,
        "subscription_tier": subscription_tier,
        "whatsapp_sent": sent,
    }


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def handler(event: dict, context) -> dict:  # noqa: ANN001
    """
    Entry point for the RelayShield SIM/eSIM swap monitoring Lambda.

    Test mode — pass this event payload to simulate a positive swap detection
    without waiting for a real swap to occur:

        {
            "force_swap_test": true,
            "test_carrier": "T-Mobile",
            "test_swap_timestamp": "2026-04-09T12:00:00Z"
        }

    test_carrier and test_swap_timestamp are optional (sensible defaults applied).
    The simulated alert fires for every user with sim_swap_monitoring = True.
    """
    logger.info("RelayShield SIM/eSIM swap monitor started.")
    start_time = time.time()

    force_test = bool(event.get("force_swap_test", False))
    if force_test:
        logger.warning(
            "⚠️  FORCE SWAP TEST MODE — simulating a positive SIM swap detection."
        )

    # Fetch Twilio credentials once per invocation
    try:
        twilio_creds = get_twilio_credentials()
    except Exception as exc:
        logger.exception("Failed to retrieve Twilio credentials: %s", exc)
        return {
            "statusCode": 500,
            "body": {"error": "Failed to retrieve Twilio credentials", "detail": str(exc)},
        }

    # Load users with SIM monitoring enabled
    try:
        users = scan_users_with_sim_monitoring()
    except Exception as exc:
        logger.exception("Failed to scan users table: %s", exc)
        return {
            "statusCode": 500,
            "body": {"error": "Failed to scan users table", "detail": str(exc)},
        }

    if not users:
        logger.info("No users with SIM swap monitoring enabled. Exiting.")
        return {
            "statusCode": 200,
            "body": {"users_checked": 0, "swaps_detected": 0, "alerts": []},
        }

    alerts_fired: list[dict] = []

    if force_test:
        # ── Test mode: inject a simulated swap for every monitored user ──────
        test_carrier = event.get("test_carrier", "T-Mobile")
        test_timestamp = event.get(
            "test_swap_timestamp",
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        account_sid, auth_token, from_number = twilio_creds

        for user in users:
            user_id = user.get("user_id", "unknown")
            subscription_tier = user.get("subscription_tier", TIER_PERSONAL)
            phone_number = get_phone_number_for_user(user)
            whatsapp_to = get_whatsapp_number_for_user(user)

            if not phone_number or not whatsapp_to:
                logger.warning(
                    "TEST: user_id=%s missing phone/whatsapp — skipping.", user_id
                )
                continue

            logger.warning(
                "TEST: Firing simulated SIM swap alert — user_id=%s phone=%s "
                "carrier=%s tier=%s",
                user_id, phone_number, test_carrier, subscription_tier,
            )

            # Format test timestamp for template variable {{2}}
            try:
                dt = datetime.fromisoformat(test_timestamp.replace("Z", "+00:00"))
                test_time_str = dt.strftime("%H:%M UTC on %d %b %Y")
            except Exception:
                test_time_str = test_timestamp

            sent = send_whatsapp_alert(
                account_sid=account_sid,
                auth_token=auth_token,
                from_number=from_number,
                to_number=whatsapp_to,
                phone_number=phone_number,
                swap_time_str=test_time_str,
                carrier_name=test_carrier,
            )

            # Write to DynamoDB with a unique test timestamp so dedup doesn't
            # suppress future real alerts
            alert_id = write_sim_swap_alert(
                user_id=user_id,
                phone_number=phone_number,
                swap_event_timestamp=f"TEST-{test_timestamp}",
                carrier_name=test_carrier,
                subscription_tier=subscription_tier,
                alert_sent=sent,
            )

            alerts_fired.append({
                "alert_id": alert_id,
                "user_id": user_id,
                "phone_number": phone_number,
                "swap_event_timestamp": test_timestamp,
                "carrier_name": test_carrier,
                "subscription_tier": subscription_tier,
                "whatsapp_sent": sent,
                "test_mode": True,
            })

    else:
        # ── Production mode: real Twilio Lookup v2 per user ──────────────────
        for index, user in enumerate(users):
            if index > 0:
                time.sleep(LOOKUP_DELAY_SECONDS)
            try:
                result = process_user_sim_swap(user, twilio_creds)
                if result:
                    alerts_fired.append(result)
            except Exception as exc:
                logger.exception(
                    "Unhandled error processing user_id=%s: %s",
                    user.get("user_id", "unknown"),
                    exc,
                )

    elapsed = round(time.time() - start_time, 2)
    logger.info(
        "SIM/eSIM swap monitor finished. %d user(s) checked, %d swap(s) detected. "
        "test_mode=%s Elapsed: %ss.",
        len(users), len(alerts_fired), force_test, elapsed,
    )

    return {
        "statusCode": 200,
        "body": {
            "users_checked": len(users),
            "swaps_detected": len(alerts_fired),
            "alerts": alerts_fired,
            "test_mode": force_test,
        },
    }
