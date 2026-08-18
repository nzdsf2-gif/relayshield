"""
RelayShield INTEL-4 — Ransomware Victim Site Monitor

Tracks active ransomware group leak sites via ransomware.live, which maintains
victim listings scraped from the groups' own .onion pages.

Two components:
  1. Victim site scraping: fetches ransomware.live JSON, extracts victim company names
     and domains, stores in relayshield_intel_ransomware table, cross-references
     against relayshield_users monitored domains, fires CRITICAL alerts.

  2. Pre-ransomware credential labeling: when a monitored domain appears on a
     victim list, retroactively tags any existing IOCs for that domain in
     relayshield_intel_iocs with pre_ransomware=true. These credentials were
     exposed before the ransomware incident — the same positioning SpyCloud uses.

Architecture:
  EventBridge cron (daily at 08:00 UTC)
  → Lambda (this file)
      → Fetch ransomware.live /v2/recentvictims (no auth required)
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
import urllib.parse
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

# WA template SID for ransomware victim alert (Meta approval pending)
WA_TEMPLATE_SID   = "HX1e77a6d255976d5cd827e27120cc8c59"
TWILIO_SID_SECRET = "relayshield/twilio_account_sid"
TWILIO_TOK_SECRET = "relayshield/twilio_auth_token"
TWILIO_FROM_SECRET = "relayshield/twilio_whatsapp_number"
TWILIO_MESSAGES_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
VICTIM_TTL_DAYS   = 180
# A live leak-site feed publishes most days. Fourteen days without a single new
# record means the source is very likely dead, not that ransomware stopped.
STALE_FEED_DAYS   = 14

# INTEL-4-SOURCE, migrated 2026-08-18.
#
# The previous source was joshhighet/ransomwatch posts.json. That repository is
# ARCHIVED. It still served 16,072 records and every fetch returned 200, but the
# newest `discovered` value was 2025-06-16 and there were zero 2026 posts. The
# feed had been dead for 14 months and the failure was silent, because a stale
# feed and a quiet week look identical. `ransomware-risk` is billed at $0.40 a
# call and is a certified Power Platform operation, so it was answering both
# with stale data.
RANSOMWARE_LIVE_URL = "https://api.ransomware.live/v2/recentvictims"

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
# Feed parsing
# ---------------------------------------------------------------------------

_RE_DOMAIN = re.compile(r"\b(?:[a-zA-Z0-9\-]{1,63}\.)+(?:com|net|org|io|co|uk|gov|edu|biz|info)\b", re.IGNORECASE)


def _normalise(rec: dict) -> dict:
    """Map a ransomware.live v2 record onto the field names this module uses.

    Everything downstream - _extract_victim_domain, the watermark, the alert
    text and the DynamoDB writes - was written against ransomwatch's names.
    Normalising here keeps the migration to one function instead of threading a
    second schema through all of them.

        ransomware.live      ransomwatch (internal)
        group            ->  group_name
        victim           ->  post_title
        discovered       ->  discovered      (same name, ISO 8601)
        description      ->  description
        website          ->  website
    """
    return {
        "group_name":  rec.get("group") or rec.get("group_name") or "unknown",
        "post_title":  rec.get("victim") or rec.get("post_title") or "",
        # attackdate is the fallback: `discovered` is when the listing was seen,
        # which is what the watermark orders on, but not every record carries it.
        "discovered":  str(rec.get("discovered") or rec.get("attackdate") or ""),
        "description": rec.get("description") or "",
        "website":     rec.get("website") or "",
    }


def fetch_victims() -> list[dict]:
    """Fetch recent ransomware victims. Returns records in the internal shape.

    Returns [] on any failure, which the handler treats as "nothing new" rather
    than an error. That is the behaviour that hid the dead feed for 14 months,
    so the staleness guard below is what actually catches a source going quiet:
    an empty list is indistinguishable from a quiet day, but a newest-record
    date weeks in the past is not.
    """
    try:
        req = urllib.request.Request(
            RANSOMWARE_LIVE_URL,
            headers={"User-Agent": "RelayShield-INTEL4/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read())
    except Exception as exc:
        logger.error("ransomware.live fetch failed: %s", exc)
        return []

    if not isinstance(raw, list):
        logger.error("ransomware.live returned %s, expected a list", type(raw).__name__)
        return []

    posts = [_normalise(r) for r in raw if isinstance(r, dict)]
    _warn_if_stale(posts)
    return posts


def _warn_if_stale(posts: list[dict], max_age_days: int = STALE_FEED_DAYS) -> None:
    """Log loudly when the newest record is older than a source should ever be.

    INTEL-4-SOURCE went unnoticed because a feed that returns plenty of rows
    looks healthy. Age of the newest record is the signal that distinguishes a
    live source from an archived one.
    """
    dates = [p["discovered"][:10] for p in posts if p.get("discovered")]
    if not dates:
        logger.error("STALE FEED: no record carries a discovered date")
        return
    newest = max(dates)
    try:
        age = (datetime.now(timezone.utc).date()
               - datetime.strptime(newest, "%Y-%m-%d").date()).days
    except ValueError:
        logger.warning("could not parse newest discovered value %r", newest)
        return
    if age > max_age_days:
        logger.error(
            "STALE FEED: newest ransomware record is %s, %d days old (limit %d). "
            "The source may be archived, as joshhighet/ransomwatch was.",
            newest, age, max_age_days,
        )
    else:
        logger.info("feed freshness OK: newest record %s, %d days old", newest, age)


def _canonical_domain(raw: str) -> str:
    """Lower-case and strip a leading www.

    _find_monitored_users matches monitored_domain with eq(), an exact compare.
    A victim record whose website is "https://www.acme.com" yields
    "www.acme.com", which never equals the "acme.com" a user actually
    registered, so the CRITICAL alert silently does not fire. Same failure
    shape as the dead feed: it goes wrong by finding nothing.
    """
    d = raw.lower().strip().rstrip(".")
    return d[4:] if d.startswith("www.") else d


def _extract_victim_domain(post: dict) -> str | None:
    """Extract the most likely domain from a normalised victim record."""
    # normalised shape: group_name, post_title, discovered, description, website
    website = post.get("website", "")
    if website:
        m = _RE_DOMAIN.search(website)
        if m:
            return _canonical_domain(m.group(0))
    # Fall back to extracting from title/description
    for field in ("post_title", "description"):
        text = post.get(field, "")
        if text:
            m = _RE_DOMAIN.search(text)
            if m:
                return _canonical_domain(m.group(0))
    return None


# ---------------------------------------------------------------------------
# DynamoDB operations
# ---------------------------------------------------------------------------

_WATERMARK_KEY = {"domain": "__state__", "group": "__watermark__"}
FIRST_RUN_LIMIT = 500


def _get_watermark() -> str:
    """Newest `discovered` value processed by the last successful run."""
    try:
        item = _dynamodb.Table(RANSOMWARE_TABLE).get_item(Key=_WATERMARK_KEY).get("Item") or {}
        return str(item.get("discovered", ""))
    except Exception as exc:
        logger.warning("watermark read failed, treating as first run: %s", exc)
        return ""


def _set_watermark(value: str) -> None:
    """Fire-and-forget. A failed write means the next run reprocesses a small
    overlap, which _store_victim's conditional put already deduplicates."""
    try:
        _dynamodb.Table(RANSOMWARE_TABLE).put_item(Item={**_WATERMARK_KEY, "discovered": value})
    except Exception as exc:
        logger.warning("watermark write failed: %s", exc)


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
            ConditionExpression="attribute_not_exists(#d) AND attribute_not_exists(#g)",
            ExpressionAttributeNames={"#d": "domain", "#g": "group"},
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


def _send_wa_ransomware_alert(domain: str, group: str, user: dict) -> bool:
    """Send ransomware victim alert via WhatsApp template (pending Meta approval)."""
    try:
        raw_sid   = _secrets.get_secret_value(SecretId=TWILIO_SID_SECRET)["SecretString"].strip()
        raw_token = _secrets.get_secret_value(SecretId=TWILIO_TOK_SECRET)["SecretString"].strip()
        raw_from  = _secrets.get_secret_value(SecretId=TWILIO_FROM_SECRET)["SecretString"].strip()
        # Decrypt phone
        phone_enc = user.get("phone_encrypted")
        if not phone_enc:
            return False
        import base64
        kms = boto3.client("kms", region_name="us-east-1")
        to_number = kms.decrypt(CiphertextBlob=base64.b64decode(phone_enc))["Plaintext"].decode()
        if not to_number.startswith("whatsapp:"):
            to_number = f"whatsapp:{to_number}"
        from_number = raw_from if raw_from.startswith("whatsapp:") else f"whatsapp:{raw_from}"

        payload = urllib.parse.urlencode({
            "To":               to_number,
            "From":             from_number,
            "ContentSid":       WA_TEMPLATE_SID,
            "ContentVariables": json.dumps({"1": domain, "2": group}),
        }).encode()
        creds = base64.b64encode(f"{raw_sid}:{raw_token}".encode()).decode()
        req = urllib.request.Request(
            TWILIO_MESSAGES_URL.format(sid=raw_sid),
            data=payload,
            headers={"Authorization": f"Basic {creds}",
                     "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=15)
        return True
    except Exception as exc:
        logger.warning("WA ransomware alert failed user_id=%s: %s", user.get("user_id"), exc)
        return False


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    logger.info("INTEL-4 ransomware monitor starting")

    posts = fetch_victims()
    if not posts:
        logger.warning("No ransomware victim records returned")
        return {"statusCode": 200, "new_victims": 0, "alerts_fired": 0}

    logger.info("ransomware.live: %d victim records fetched", len(posts))

    # Only process posts newer than the last successful run.
    #
    # /v2/recentvictims returns a recent window rather than the full archive,
    # so the 16k-record timeout that forced this watermark no longer applies.
    # The watermark stays: it is what stops a re-alert when the same listing
    # appears in consecutive windows, and it makes the backlog fill in
    # incrementally instead of in one replay.
    #
    # The high-water mark is stored as a reserved row in the same table
    # (domain="__state__", group="__watermark__"), which the (domain, group)
    # key schema makes safe - no real victim domain can collide with it, and
    # it needs no new table.
    watermark = _get_watermark()
    if watermark:
        before = len(posts)
        posts = [p for p in posts if str(p.get("discovered", "")) > watermark]
        logger.info("watermark=%s -> %d of %d posts are new", watermark, len(posts), before)
    else:
        # First run after this change: the archive is entirely backfill, and
        # replaying it would re-alert every monitored user for victims
        # discovered years ago. Take the newest slice only and set the mark.
        posts = sorted(posts, key=lambda p: str(p.get("discovered", "")))[-FIRST_RUN_LIMIT:]
        logger.info("no watermark, seeding from newest %d posts", len(posts))

    if posts:
        _set_watermark(max(str(p.get("discovered", "")) for p in posts))

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
            alert_text = _format_ransomware_alert(domain, group, post)
            # Telegram delivery
            chat_id = _get_user_tg_chat(user)
            if chat_id:
                _send_telegram(chat_id, alert_text)
            # WhatsApp delivery via template (activates on Meta approval)
            _send_wa_ransomware_alert(domain, group, user)
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
