"""
relayshield_monthly_team_report.py

Monthly team security report for Business Basic+ admins.
EventBridge schedule: cron(0 9 1 * ? *) — 09:00 UTC on the 1st of each month.

For each active team admin on Business Basic or higher:
  • Per team member: breach alert count, infostealer log count, SIM swap status
  • Company domain: lookalike count from domain_monitor_state.__company__
  • Personal domains: lookalike counts from domain_monitor_state
  • Delivered to admin Telegram via direct Bot API

Pass {"test_admin_id": "user-onboard-test-001"} as the test event to run for
a single admin without waiting for the EventBridge schedule.
"""

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

USERS_TABLE            = "relayshield_users"
MONITORED_EMAILS_TABLE = "relayshield_monitored_emails"
BREACH_ALERTS_TABLE    = "relayshield_breach_alerts"

TIER_BASIC  = "business_basic"
TIER_SHIELD = "business_shield"
TIER_PRO    = "business_shield_pro"
BUSINESS_ADMIN_TIERS = {TIER_BASIC, TIER_SHIELD, TIER_PRO}

dynamodb       = boto3.resource("dynamodb")
secrets_client = boto3.client("secretsmanager")


# ---------------------------------------------------------------------------
# Secrets / credentials
# ---------------------------------------------------------------------------

def _get_telegram_token() -> str:
    raw = secrets_client.get_secret_value(
        SecretId="relayshield/telegram_bot_token"
    )["SecretString"].strip()
    try:
        return json.loads(raw)["telegram_bot_token"]
    except (json.JSONDecodeError, KeyError):
        return raw


def _send_telegram(chat_id: int, message: str, token: str) -> bool:
    try:
        url     = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({
            "chat_id":    chat_id,
            "text":       message,
            "parse_mode": "Markdown",
        }).encode()
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=8)
        return True
    except Exception as exc:
        logger.exception("TG send failed chat_id=%s: %s", chat_id, exc)
        return False


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------

def _full_scan(table_name: str, filter_expr) -> list[dict]:
    """Paginated scan with FilterExpression."""
    table  = dynamodb.Table(table_name)
    items  = []
    kwargs = {"FilterExpression": filter_expr}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return items


def _count_scan(table_name: str, filter_expr) -> int:
    """Paginated COUNT scan — returns total matching item count."""
    table  = dynamodb.Table(table_name)
    count  = 0
    kwargs = {"FilterExpression": filter_expr, "Select": "COUNT"}
    while True:
        resp   = table.scan(**kwargs)
        count += resp.get("Count", 0)
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return count


def scan_team_admins() -> list[dict]:
    """Return active team admins on Business Basic or higher."""
    all_admins = _full_scan(
        USERS_TABLE,
        Attr("is_team_admin").eq(True) & Attr("active").eq(True),
    )
    return [a for a in all_admins if a.get("subscription_tier") in BUSINESS_ADMIN_TIERS]


def get_team_members(admin_user_id: str) -> list[dict]:
    """Return active employee records belonging to this admin."""
    return _full_scan(
        USERS_TABLE,
        Attr("team_id").eq(admin_user_id)
        & Attr("active").eq(True)
        & Attr("admin_user_id").exists(),
    )


def get_breach_count(user_id: str) -> int:
    return _count_scan(BREACH_ALERTS_TABLE, Attr("user_id").eq(user_id))


def get_infostealer_count(user_id: str) -> int:
    """Sum infostealer_count across all active monitored emails for this user."""
    records = _full_scan(
        MONITORED_EMAILS_TABLE,
        Attr("user_id").eq(user_id) & Attr("active").eq(True),
    )
    return sum(int(r.get("infostealer_count", 0)) for r in records)


# ---------------------------------------------------------------------------
# Report builders
# ---------------------------------------------------------------------------

def _member_block(member: dict) -> str:
    name    = member.get("employee_name") or "Unnamed member"
    user_id = member.get("user_id", "")

    # Breaches
    bc = get_breach_count(user_id)
    if bc == 0:
        breach_line = "✅ No breaches on record"
    elif bc <= 2:
        breach_line = f"⚠️ {bc} breach alert{'s' if bc != 1 else ''} sent"
    else:
        breach_line = f"🔴 {bc} breach alerts sent"

    # Infostealer
    sc = get_infostealer_count(user_id)
    if sc == 0:
        stealer_line = "✅ No infostealer logs"
    else:
        stealer_line = f"🔴 {sc} infostealer log{'s' if sc != 1 else ''} found"

    # SIM swap
    sim_enabled  = member.get("sim_swap_monitoring", False)
    last_carrier = member.get("last_known_carrier", "")
    last_alerted = member.get("last_swap_alerted_at", "")
    if last_alerted:
        sim_line = "⚠️ SIM swap alert sent this period"
    elif sim_enabled and last_carrier:
        sim_line = f"✅ Monitored — {last_carrier}"
    elif sim_enabled:
        sim_line = "✅ Monitored"
    else:
        sim_line = "➖ Not enabled"

    return (
        f"👤 *{name}*\n"
        f"  {breach_line}\n"
        f"  {stealer_line}\n"
        f"  📱 SIM: {sim_line}"
    )


def _domain_block(admin: dict) -> str:
    state_raw = admin.get("domain_monitor_state", "{}")
    try:
        state = json.loads(state_raw) if isinstance(state_raw, str) else state_raw
    except Exception:
        state = {}

    company_domain = admin.get("company_domain", "")
    lines = []

    # Company domain — state stored under __company__ (after process_company_domains runs)
    # or under the domain name itself (from personal domain monitor). Fall back to domain name.
    if company_domain:
        co_state   = state.get("__company__") or state.get(company_domain, {})
        lookalikes = co_state.get("known_lookalikes", [])
        count      = len(lookalikes)
        if count:
            lines.append(f"  ⚠️ `{company_domain}` *(company)* — {count} lookalike{'s' if count != 1 else ''} detected:")
            for lk in lookalikes[:4]:
                lines.append(f"    · `{lk}`")
            if count > 4:
                lines.append(f"    · …and {count - 4} more")
            lines.append(f"  Reply *DOMAIN* to run a fresh scan or broadcast a phishing warning to your team.")
        else:
            lines.append(f"  ✅ `{company_domain}` *(company)* — Clean")

    # Personal monitored domains
    for domain, dstate in state.items():
        if domain == "__company__":
            continue
        if domain == company_domain:
            continue  # already shown above
        lookalikes = dstate.get("known_lookalikes", [])
        count      = len(lookalikes)
        if count:
            lines.append(f"  ⚠️ `{domain}` — {count} lookalike{'s' if count != 1 else ''} detected:")
            for lk in lookalikes[:4]:
                lines.append(f"    · `{lk}`")
            if count > 4:
                lines.append(f"    · …and {count - 4} more")
        else:
            lines.append(f"  ✅ `{domain}` — Clean")

    if not lines:
        return "  No domains monitored"

    return "\n".join(lines)


def build_report(admin: dict, members: list[dict], month_label: str) -> str:
    seat_count = len(members)

    if members:
        member_section = "\n\n".join(_member_block(m) for m in members)
    else:
        member_section = "_No team members added yet._"

    domain_section = _domain_block(admin)

    tier_labels = {
        TIER_BASIC:  "Business Basic",
        TIER_SHIELD: "Business Shield",
        TIER_PRO:    "Business Shield Pro",
    }
    tier = tier_labels.get(admin.get("subscription_tier", ""), "Business")

    return (
        f"📊 *Monthly Team Security Report — {month_label}*\n"
        f"_{tier} · {seat_count} member{'s' if seat_count != 1 else ''}_\n\n"
        f"{member_section}\n\n"
        f"🌐 *Domain Monitoring*\n"
        f"{domain_section}\n\n"
        f"Reply /teamstatus for a live snapshot at any time.\n"
        f"🛡️ RelayShield"
    )


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def handler(event: dict, context) -> dict:
    now = datetime.now(timezone.utc)
    months = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    if now.month == 1:
        month_label = f"December {now.year - 1}"
    else:
        month_label = f"{months[now.month - 2]} {now.year}"

    logger.info("Monthly team report — %s", month_label)

    try:
        tg_token = _get_telegram_token()
    except Exception as exc:
        logger.exception("Failed to retrieve TG token: %s", exc)
        return {"statusCode": 500, "body": "tg_token_failed"}

    test_admin_id = event.get("test_admin_id")

    admins = scan_team_admins()
    if test_admin_id:
        admins = [a for a in admins if a.get("user_id") == test_admin_id]
        logger.info("Test mode — running for admin_id=%s only", test_admin_id)

    sent = skipped = errors = 0

    for admin in admins:
        admin_id = admin.get("user_id", "")
        tg_id    = admin.get("telegram_chat_id")
        tg_chs   = admin.get("delivery_channels", [])

        if not tg_id or "telegram" not in tg_chs:
            logger.info("Admin %s has no TG delivery — skipping.", admin_id)
            skipped += 1
            continue

        try:
            members = get_team_members(admin_id)
            report  = build_report(admin, members, month_label)
            ok      = _send_telegram(int(tg_id), report, tg_token)
            if ok:
                sent += 1
                logger.info("Team report sent — admin_id=%s members=%d", admin_id, len(members))
            else:
                errors += 1
        except Exception as exc:
            logger.exception("Report failed for admin_id=%s: %s", admin_id, exc)
            errors += 1

    logger.info(
        "Monthly team report done — month=%s admins=%d sent=%d skipped=%d errors=%d",
        month_label, len(admins), sent, skipped, errors,
    )
    return {
        "statusCode": 200,
        "body": {
            "month":            month_label,
            "admins_processed": len(admins),
            "reports_sent":     sent,
            "skipped":          skipped,
            "errors":           errors,
        },
    }
