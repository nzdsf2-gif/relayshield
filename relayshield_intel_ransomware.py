"""
RelayShield INTEL-4 — Ransomware Victim Site Monitor

Scrapes active ransomware group leak sites via ransomwatch (open-source project
that maintains an updated list of .onion victim pages for 100+ ransomware groups).

Two components:
  1. Victim site scraping: fetches ransomwatch JSON, extracts victim company names
     and domains, stores in relayshield_intel_ransomware table, cross-references
     against relayshield_users monitored domains, fires CRITICAL alerts.

  2. Pre-ransomware credential labeling: when a monitored domain appears on a
     victim list, retroactively tags any existing IOCs for that domain in
     relayshield_intel_iocs with pre_ransomware=true. These credentials were
     exposed before the ransomware incident — the same positioning SpyCloud uses.

Architecture:
  EventBridge cron (daily at 08:00 UTC)
  → Lambda (this file)
      → Fetch ransomwatch posts.json (GitHub, no auth required)
      → Parse victim domains
      → Cross-reference relayshield_users monitored_domain fields
      → Tag pre-existing IOCs in relayshield_intel_iocs
      → Fire CRITICAL Telegram alert to affected users
      → Store victim records in relayshield_intel_ransomware (180-day TTL)

DynamoDB tables:
  relayshield_intel_ransomware — PK: domain (S), SK: group (S), TTL 180 days
  relayshield_intel_iocs       — existing table: add pre_ransomware flag
  relayshield_users            — monitored_domain field cross-reference

Environment variables:
  ADMIN_CHAT_ID — Andrew's Telegram chat ID

Secrets:
  relayshield/telegram_bot_token
"""

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RANSOMWARE_TABLE  = "relayshield_intel_ransomware"
IOCS_TABLE        = "relayshield_intel_iocs"
USERS_TABLE       = "relayshield_users"
EMAILS_TABLE      = "relayshield_monitored_emails"
TG_SECRET_NAME    = "relayshield/telegram_bot_token"
TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"

ADMIN_CHAT_ID     = int(os.environ.get("ADMIN_CHAT_ID", "1729226804"))
VICTIM_TTL_DAYS   = 180

# ransomwatch posts.json — maintained by joshhighet, updated continuously
RANSOMWATCH_URL   = "https://raw.githubusercontent.com/joshhighet/ransomwatch/main/posts.json"

# ---------------------------------------------------------------------------
# AWS clients
# ---------------------------------------------------------------------------

_secrets      = boto3.client("secretsmanager", region_name="us-east-1")
_dynamodb     = boto3.resource("dynamodb",      region_name="us-east-1")
_secret_cache: dict[str, str] = {}


def _tg_token() -> str:
    if "tg" not in _secret_cache:
        raw = _secrets.get_secret_value(SecretId=TG_SECRET_NAME)["SecretString"]
        _secret_cache["tg"] = json.loads(raw)["telegram_bot_token"]
    return _secret_cache["tg"]


def _send_telegram(chat_id: int, text: str) -> None:
    token = _tg_token()
    url   = TELEGRAM_API_BASE.format(token=token, method="sendMessage")
    body  = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
    req   = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        logger.error("Telegram send failed chat_id=%s: %s", chat_id, exc)


# ---------------------------------------------------------------------------
# Ransomwatch feed parsing
# ---------------------------------------------------------------------------

_RE_DOMAIN = re.compile(r"\b(?:[a-zA-Z0-9\-]{1,63}\.)+(?:com|net|org|io|co|uk|gov|edu|biz|info)\b", re.IGNORECASE)


def fetch_ransomwatch() -> list[dict]:
    """Fetch ransomwatch posts.json. Returns list of victim records."""
    try:
        req = urllib.request.Request(
            RANSOMWATCH_URL,
            headers={"User-Agent": "RelayShield-INTEL4/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        logger.error("ransomwatch fetch failed: %s", exc)
        return []


def _extract_victim_domain(post: dict) -> str | None:
    """Extract the most likely domain from a ransomwatch post record."""
    # ransomwatch provides: group_name, post_title, discovered, description, website
    website = post.get("website", "")
    if website:
        m = _RE_DOMAIN.search(website)
        if m:
            return m.group(0).lower()
    # Fall back to extracting from title/description
    for field in ("post_title", "description"):
        text = post.get(field, "")
        if text:
            m = _RE_DOMAIN.search(text)
            if m:
                return m.group(0).lower()
    return None


# ---------------------------------------------------------------------------
# DynamoDB operations
# ---------------------------------------------------------------------------

def _store_victim(domain: str, group: str, post: dict) -> bool:
    """Store victim record. Returns True if new (not previously seen)."""
    ttl = int(time.time()) + VICTIM_TTL_DAYS * 86400
    try:
        _dynamodb.Table(RANSOMWARE_TABLE).put_item(
            Item={
                "domain":       domain,
                "group":        group,
                "post_title":   post.get("post_title", "")[:500],
                "discovered":   post.get("discovered", datetime.now(timezone.utc).isoformat()),
                "website":      post.get("website", ""),
                "ingested_at":  datetime.now(timezone.utc).isoformat(),
                "ttl":          Decimal(ttl),
            },
            ConditionExpression="attribute_not_exists(domain) AND attribute_not_exists(#g)",
            ExpressionAttributeNames={"#g": "group"},
        )
        return True
    except _dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return False  # already stored
    except Exception as exc:
        logger.warning("Victim store failed domain=%s: %s", domain, exc)
        return False


def _tag_pre_ransomware_iocs(domain: str, group: str) -> int:
    """Tag existing IOCs for this domain as pre_ransomware in relayshield_intel_iocs.
    Returns count of IOCs tagged."""
    table   = _dynamodb.Table(IOCS_TABLE)
    tagged  = 0
    try:
        resp = table.scan(
            FilterExpression=(
                boto3.dynamodb.conditions.Attr("ioc_value").contains(domain) |
                boto3.dynamodb.conditions.Attr("channel").contains(domain)
            ),
            ProjectionExpression="ioc_value, seen_ts",
        )
        for item in resp.get("Items", []):
            try:
                table.update_item(
                    Key={"ioc_value": item["ioc_value"], "seen_ts": item["seen_ts"]},
                    UpdateExpression="SET pre_ransomware = :true, ransomware_group = :grp",
                    ExpressionAttributeValues={":true": True, ":grp": group},
                )
                tagged += 1
            except Exception:
                pass
    except Exception as exc:
        logger.warning("Pre-ransomware IOC tagging failed domain=%s: %s", domain, exc)
    return tagged


def _find_monitored_users(domain: str) -> list[dict]:
    """Find users monitoring this domain."""
    matches = []
    try:
        resp = _dynamodb.Table(USERS_TABLE).scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("monitored_domain").eq(domain),
        )
        matches.extend(resp.get("Items", []))
    except Exception as exc:
        logger.warning("User lookup failed domain=%s: %s", domain, exc)
    return matches


# ---------------------------------------------------------------------------
# Alert formatting
# ---------------------------------------------------------------------------

def _format_ransomware_alert(domain: str, group: str, post: dict) -> str:
    discovered = post.get("discovered", "recently")[:10]
    title      = post.get("post_title", "")[:100]
    return (
        f"🚨 *CRITICAL — Ransomware Victim Detected*\n\n"
        f"Your monitored domain *{domain}* has been listed as a ransomware victim.\n\n"
        f"*Threat group:* {group}\n"
        f"*Listed:* {discovered}\n"
        f"{'*Title:* ' + title + chr(10) if title else ''}\n"
        f"*What this means:*\n"
        f"The {group} ransomware group has claimed to have compromised *{domain}*. "
        f"If this is a vendor or partner domain, credentials they hold for your systems "
        f"may be at risk. If this is your own domain, treat this as an active incident.\n\n"
        f"*Immediate actions:*\n"
        f"→ Verify with the affected organisation directly\n"
        f"→ Rotate any shared credentials or API tokens\n"
        f"→ Audit access logs for the affected domain\n"
        f"→ Check for any lateral movement in your own systems\n\n"
        f"🛡️ _RelayShield INTEL-4 — ransomware victim early warning_"
    )


def _get_user_tg_chat(user: dict) -> int | None:
    chat = user.get("telegram_chat_id")
    return int(chat) if chat else None


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    logger.info("INTEL-4 ransomware monitor starting")

    posts = fetch_ransomwatch()
    if not posts:
        logger.warning("No ransomwatch posts returned")
        return {"statusCode": 200, "new_victims": 0, "alerts_fired": 0}

    logger.info("ransomwatch: %d posts fetched", len(posts))

    new_victims     = 0
    iocs_tagged     = 0
    alerts_fired    = 0
    monitored_hits  = 0

    for post in posts:
        group  = post.get("group_name", "unknown")
        domain = _extract_victim_domain(post)
        if not domain:
            continue

        is_new = _store_victim(domain, group, post)
        if not is_new:
            continue

        new_victims += 1
        logger.info("New ransomware victim: domain=%s group=%s", domain, group)

        # Tag pre-existing IOCs
        tagged = _tag_pre_ransomware_iocs(domain, group)
        iocs_tagged += tagged

        # Alert monitored users
        users = _find_monitored_users(domain)
        monitored_hits += len(users)
        for user in users:
            chat_id = _get_user_tg_chat(user)
            if chat_id:
                _send_telegram(chat_id, _format_ransomware_alert(domain, group, post))
                alerts_fired += 1
                logger.info("Ransomware alert fired user_id=%s domain=%s", user.get("user_id"), domain)

    # Admin digest
    summary = (
        f"🦠 *INTEL-4 Ransomware Monitor*\n\n"
        f"Posts fetched: {len(posts)}\n"
        f"New victims: {new_victims}\n"
        f"Monitored domain hits: {monitored_hits}\n"
        f"IOCs tagged pre-ransomware: {iocs_tagged}\n"
        f"Alerts fired: {alerts_fired}\n\n"
        f"_RelayShield INTEL-4 — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_"
    )
    _send_telegram(ADMIN_CHAT_ID, summary)

    return {
        "statusCode":   200,
        "posts_fetched": len(posts),
        "new_victims":   new_victims,
        "iocs_tagged":   iocs_tagged,
        "alerts_fired":  alerts_fired,
    }
