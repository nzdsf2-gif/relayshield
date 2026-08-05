"""
RelayShield Social Monitor Lambda (MONITOR-1)
Scans Reddit and Google Alerts RSS feeds for keyword mentions related to
crypto security threats and the RelayShield brand.

Runs on EventBridge cron (every 4 hours).
New matches → Telegram admin alert to ADMIN_CHAT_ID.
Seen post IDs stored in DynamoDB with 30-day TTL to prevent re-alerting.

Reddit API: public read-only JSON (no OAuth required for search).
Google Alerts RSS: optional — user creates alerts at google.com/alerts,
  sets delivery to RSS, pastes feed URL(s) in the GOOGLE_ALERTS_RSS_URLS
  Lambda environment variable (comma-separated).

DynamoDB table: relayshield_monitor_seen
  - post_id  (String, PK)  — reddit fullname or RSS entry GUID
  - source   (String)
  - title    (String)
  - url      (String)
  - keyword  (String)
  - detected_at (String, ISO)
  - ttl      (Number, Unix epoch)  — auto-expire after 30 days

Lambda env vars:
  ADMIN_CHAT_ID           — your personal Telegram chat_id for alerts
  GOOGLE_ALERTS_RSS_URLS  — optional, comma-separated RSS feed URLs
"""

import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import boto3

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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEEN_TABLE          = "relayshield_monitor_seen"
DRAFTS_TABLE        = "relayshield_monitor_drafts"
TG_SECRET_NAME      = "relayshield/telegram_bot_token"
TG_SECRET_KEY       = "telegram_bot_token"
ADMIN_CHAT_ID       = int(os.environ.get("ADMIN_CHAT_ID", "0"))
GOOGLE_ALERTS_URLS  = [
    u.strip()
    for u in os.environ.get("GOOGLE_ALERTS_RSS_URLS", "").split(",")
    if u.strip()
]

# How long to remember a seen post before rechecking (seconds)
TTL_DAYS = 30

# ---------------------------------------------------------------------------
# Reddit search config
# ---------------------------------------------------------------------------

# Each entry: (label, subreddit_or_None, query)
#   subreddit=None → search all of Reddit
#   subreddit="cybersecurity" → r/cybersecurity only
REDDIT_SEARCHES = [
    # Brand monitoring
    ("Brand: RelayShield",      None,             '"RelayShield"'),
    # SIM swap — exact phrases to avoid false positives
    ("SIM swap",                None,             '"SIM swap" OR "SIM hijack" OR "SIM swapped"'),
    ("SIM swap (crypto subs)",  "CryptoCurrency", '"SIM swap" OR "SIM hijack"'),
    # Wallet / crypto theft — exact phrases only
    ("Wallet drained",          None,             '"wallet drained" OR "crypto stolen" OR "wallet hacked"'),
    ("Crypto phishing",         "CryptoCurrency", '"seed phrase" OR "wallet phishing" OR "crypto phishing"'),
    # Infostealers
    ("Infostealer",             "cybersecurity",  '"infostealer" OR "redline stealer" OR "raccoon stealer"'),
    ("Infostealer (netsec)",    "netsec",         '"infostealer" OR "credential stealer"'),
    # Telegram-specific threats
    ("Telegram scam",           None,             '"telegram scam" OR "telegram phishing" OR "telegram crypto"'),
    # Breach news
    ("Data breach",             "cybersecurity",  '"data breach" OR "email breach"'),
    # New threat actor / ransomware group candidates — supplemental to the
    # official MITRE ATT&CK feed (relayshield_intel_attack.py), which only
    # adds a group after MITRE itself has assigned it a G-number, typically
    # long after first public reporting. r/pwnhub surfaces these early
    # (e.g. "Spirals" ransomware, added to relayshield_mitre_attack as a
    # manual CUSTOM- entry 2026-07-16 before MITRE had picked it up).
    # Deliberately INTEL-only, not auto-ingested — a Reddit post is not a
    # reliable enough signal to auto-write into a customer-facing threat-
    # actor corpus (see the PhishTank domain-misattribution bug fixed the
    # same day for exactly this kind of automated-ingestion risk). Founder
    # reviews each FYI and adds real candidates manually, same workflow as
    # Spirals.
    ("New threat actor (pwnhub)", "pwnhub", '"ransomware group" OR "threat actor" OR "APT group" OR "new ransomware"'),
]

REDDIT_BASE  = "https://www.reddit.com/search.rss"
REDDIT_SUB   = "https://www.reddit.com/r/{sub}/search.rss"
REDDIT_UA    = "RelayShieldMonitor/1.0 (by /u/relayshield_bot)"
REDDIT_LIMIT = 10   # posts per search call
REDDIT_TIME  = "day"  # only posts from the last 24h

# ---------------------------------------------------------------------------
# Category + response config
# ---------------------------------------------------------------------------

# Priority 1 = highest (respond immediately), 4 = FYI/intel only
CATEGORY_MAP = {
    "Brand: RelayShield":     {"priority": 1, "action": "RESPOND", "type": "brand"},
    "SIM swap":               {"priority": 1, "action": "RESPOND", "type": "victim_sim"},
    "SIM swap (crypto subs)": {"priority": 1, "action": "RESPOND", "type": "victim_sim"},
    "Wallet drained":         {"priority": 2, "action": "RESPOND", "type": "victim_wallet"},
    "Crypto phishing":        {"priority": 2, "action": "RESPOND", "type": "scam"},
    "Telegram scam":          {"priority": 2, "action": "RESPOND", "type": "scam"},
    "Infostealer":            {"priority": 3, "action": "INTEL",   "type": "intel"},
    "Infostealer (netsec)":   {"priority": 3, "action": "INTEL",   "type": "intel"},
    "Data breach":            {"priority": 4, "action": "INTEL",   "type": "intel"},
    "New threat actor (pwnhub)": {"priority": 3, "action": "INTEL", "type": "intel_actor"},
}

# Default for Google Alerts entries — inferred by title keywords below
GOOGLE_ALERTS_CATEGORY_DEFAULT = {"priority": 3, "action": "INTEL", "type": "intel"}

# Keywords to detect RESPOND-worthy Google Alerts entries
GOOGLE_ALERTS_RESPOND_KEYWORDS = [
    "sim swap", "sim hijack", "wallet drained", "crypto stolen",
    "wallet hack", "phishing", "scam", "relayshield", "infostealer",
]

# Draft reply templates — Andrew edits before posting. Never auto-posted.
# ⚠️  ALWAYS vary wording before pasting to avoid Reddit spam detection.
RESPONSE_TEMPLATES = {
    "brand": (
        "Hey — founder of RelayShield here. Happy to answer any questions. "
        "[Add a specific, relevant comment about what they said before mentioning the product.]"
    ),
    "victim_sim": (
        "Really sorry this happened. Immediate steps:\n"
        "1. Call your carrier right now — ask for a SIM lock / port freeze\n"
        "2. Change passwords on any account using SMS 2FA (start with email + exchanges)\n"
        "3. Enable authenticator-app 2FA (Google Authenticator / Authy) everywhere you can\n"
        "4. Check if your email was in any breach — free check at HaveIBeenPwned\n\n"
        "*(Full disclosure: I built RelayShield, which monitors for SIM swap attacks and "
        "breach exposure. Happy to help further here, or free check via @relayshield_bot "
        "on Telegram — no card needed.)*"
    ),
    "victim_wallet": (
        "Really sorry. Quick triage:\n"
        "• Seed phrase compromised → that wallet is gone. Move any remaining funds to a "
        "fresh wallet immediately (new seed, never touched the old device)\n"
        "• Exchange hack → freeze your account via their emergency line, then revoke all "
        "OAuth-connected apps\n"
        "• Phishing site → change the email + password used, enable 2FA\n\n"
        "*(Full disclosure: I run RelayShield — we alert on infostealer exposure and "
        "breach data that often precedes these attacks. Happy to help here.)*"
    ),
    "scam": (
        "Classic pig butchering / advance fee pattern. Red flags: [add 2-3 specific "
        "things from their post].\n\n"
        "Don't send anything. Block and report the account. If you've already shared "
        "your email or phone number, worth checking for breach exposure — "
        "@relayshield_bot on Telegram does a free scan, no card needed."
    ),
}

# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

_tg_token_cache: str | None = None


def get_tg_token() -> str:
    global _tg_token_cache
    if _tg_token_cache:
        return _tg_token_cache
    resp = secrets_client.get_secret_value(SecretId=TG_SECRET_NAME)
    data = json.loads(resp["SecretString"])
    _tg_token_cache = data[TG_SECRET_KEY]
    return _tg_token_cache


def send_admin_message(text: str, reply_markup: dict | None = None) -> None:
    """Send a Telegram message to the admin chat, optionally with inline keyboard."""
    if not ADMIN_CHAT_ID:
        logger.warning("ADMIN_CHAT_ID not set — skipping Telegram alert")
        return
    token   = get_tg_token()
    url     = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id":                  ADMIN_CHAT_ID,
        "text":                     text,
        "parse_mode":               "Markdown",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            logger.info("Telegram alert sent: %s", resp.status)
    except Exception as exc:
        logger.error("Telegram send failed: %s", exc)


def _make_draft_key(post_id: str) -> str:
    """12-char hex key derived from post_id — fits safely in callback_data.

    usedforsecurity=False because this is a length-reduction key for Telegram's
    64-byte callback_data limit, not a digest anything trusts. Without it bandit
    reports B324 at HIGH, which fails Security Audit before pip-audit and
    gitleaks ever run, so secret scanning silently stops happening.
    """
    return hashlib.md5(post_id.encode(), usedforsecurity=False).hexdigest()[:12]


def _store_draft_context(draft_key: str, m: dict) -> None:
    """Persist post context in DynamoDB so the webhook can retrieve it on button tap."""
    now = datetime.now(timezone.utc)
    ttl = int(now.timestamp()) + (7 * 86400)  # 7-day expiry
    dynamodb.Table(DRAFTS_TABLE).put_item(Item={
        "draft_key":  draft_key,
        "title":      m.get("title", "")[:500],
        "url":        m.get("url", "")[:1000],
        "source":     m.get("source", ""),
        "cat_type":   m.get("cat_type", ""),
        "subreddit":  m.get("subreddit", ""),
        "label":      m.get("label", ""),
        "created_at": now.isoformat(),
        "ttl":        ttl,
    })

# ---------------------------------------------------------------------------
# DynamoDB dedup helpers
# ---------------------------------------------------------------------------

def _seen_table():
    return dynamodb.Table(SEEN_TABLE)


def is_seen(post_id: str) -> bool:
    """Return True if this post_id is already in the seen table."""
    resp = _seen_table().get_item(Key={"post_id": post_id})
    return "Item" in resp


def mark_seen(post_id: str, source: str, title: str, url: str, keyword: str) -> None:
    """Write the post_id to DynamoDB with a 30-day TTL."""
    now = datetime.now(timezone.utc)
    ttl = int(now.timestamp()) + (TTL_DAYS * 86400)
    _seen_table().put_item(Item={
        "post_id":     post_id,
        "source":      source,
        "title":       title[:500],
        "url":         url[:1000],
        "keyword":     keyword,
        "detected_at": now.isoformat(),
        "ttl":         ttl,
    })

# ---------------------------------------------------------------------------
# Reddit scanner
# ---------------------------------------------------------------------------

def _reddit_rss_fetch(url: str, params: dict) -> list[dict]:
    """
    Fetch a Reddit RSS feed and return parsed entries as list of dicts.
    Reddit RSS is publicly accessible without OAuth.
    Each entry: {post_id, title, url, subreddit, author}
    """
    full_url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        full_url,
        headers={"User-Agent": REDDIT_UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_text = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        logger.warning("Reddit RSS HTTP %s for %s", exc.code, full_url)
        return []
    except Exception as exc:
        logger.error("Reddit RSS request error: %s", exc)
        return []

    entries = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.error("Reddit RSS parse error: %s", exc)
        return []

    # Reddit returns Atom format: <feed xmlns="http://www.w3.org/2005/Atom">
    # Extract namespace prefix from root tag (e.g. "{http://www.w3.org/2005/Atom}")
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    for entry in root.findall(f"{ns}entry"):
        post_id  = (entry.findtext(f"{ns}id") or "").strip()   # e.g. t3_abc123
        title    = (entry.findtext(f"{ns}title") or "").strip()
        link_el  = entry.find(f"{ns}link")
        link     = link_el.get("href", "") if link_el is not None else ""
        author_el = entry.find(f"{ns}author/{ns}name")
        author   = (author_el.text or "") if author_el is not None else ""

        # Extract subreddit from URL: /r/cybersecurity/comments/...
        sub_name = ""
        parts = link.split("/")
        if "r" in parts:
            idx = parts.index("r")
            if idx + 1 < len(parts):
                sub_name = parts[idx + 1]

        if post_id:
            entries.append({
                "post_id":   post_id,
                "title":     title,
                "url":       link,
                "subreddit": sub_name,
                "author":    author,
            })

    return entries


def scan_reddit() -> list[dict]:
    """
    Run all REDDIT_SEARCHES via RSS feeds (no OAuth required).
    Returns list of new match dicts.
    """
    new_matches = []

    for label, subreddit, query in REDDIT_SEARCHES:
        if subreddit:
            base_url = REDDIT_SUB.format(sub=subreddit)
        else:
            base_url = REDDIT_BASE

        params = {
            "q":           query,
            "sort":        "new",
            "limit":       REDDIT_LIMIT,
            "t":           REDDIT_TIME,
            "restrict_sr": "on" if subreddit else "off",
        }

        entries = _reddit_rss_fetch(base_url, params)

        for entry in entries:
            post_id  = entry["post_id"]
            title    = entry["title"]
            url      = entry["url"]
            sub_name = entry["subreddit"]

            if not post_id:
                continue

            if is_seen(post_id):
                continue

            cat = CATEGORY_MAP.get(label, {"priority": 4, "action": "INTEL", "type": "intel"})
            mark_seen(post_id, "reddit", title, url, label)
            new_matches.append({
                "label":     label,
                "source":    "reddit",
                "subreddit": sub_name,
                "keyword":   query,
                "title":     title,
                "url":       url,
                "post_id":   post_id,
                "priority":  cat["priority"],
                "action":    cat["action"],
                "cat_type":  cat["type"],
            })
            logger.info("New Reddit match [%s][%s]: %s", label, cat["action"], title[:80])

        # Respect Reddit's rate limit between calls
        time.sleep(1.5)

    return new_matches

# ---------------------------------------------------------------------------
# Google Alerts RSS scanner
# ---------------------------------------------------------------------------

def _parse_rss_entries(xml_text: str) -> list[dict]:
    """Parse Atom/RSS feed XML, return list of {id, title, url, summary}."""
    entries = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.error("RSS parse error: %s", exc)
        return entries

    # Handle both Atom (xmlns="http://www.w3.org/2005/Atom") and RSS 2.0
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    # Atom feed
    for entry in root.findall(f"{ns}entry"):
        entry_id = (entry.findtext(f"{ns}id") or "").strip()
        title    = (entry.findtext(f"{ns}title") or "").strip()
        # link is an attribute, not text
        link_el  = entry.find(f"{ns}link")
        url      = link_el.get("href", "") if link_el is not None else ""
        summary  = (entry.findtext(f"{ns}summary") or "").strip()
        if entry_id:
            entries.append({"id": entry_id, "title": title, "url": url, "summary": summary})

    # RSS 2.0 fallback (no namespace)
    if not entries:
        for item in root.findall(".//item"):
            guid  = (item.findtext("guid") or "").strip()
            title = (item.findtext("title") or "").strip()
            url   = (item.findtext("link") or "").strip()
            desc  = (item.findtext("description") or "").strip()
            if guid:
                entries.append({"id": guid, "title": title, "url": url, "summary": desc})

    return entries


def scan_google_alerts() -> list[dict]:
    """
    Fetch each Google Alerts RSS feed URL and return new match dicts.
    Feed URLs are set via GOOGLE_ALERTS_RSS_URLS env var (comma-separated).
    """
    new_matches = []
    if not GOOGLE_ALERTS_URLS:
        logger.info("No Google Alerts RSS URLs configured — skipping")
        return new_matches

    for feed_url in GOOGLE_ALERTS_URLS:
        req = urllib.request.Request(
            feed_url,
            headers={"User-Agent": "RelayShieldMonitor/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                xml_text = resp.read().decode("utf-8", errors="replace")
        except Exception as exc:
            logger.error("Google Alerts fetch failed for %s: %s", feed_url, exc)
            continue

        entries = _parse_rss_entries(xml_text)
        for entry in entries:
            entry_id = entry["id"]
            title    = entry["title"]
            url      = entry["url"]
            summary  = entry["summary"]

            if not entry_id:
                continue

            if is_seen(entry_id):
                continue

            # Infer category from title keywords
            title_lower = title.lower()
            if any(kw in title_lower for kw in GOOGLE_ALERTS_RESPOND_KEYWORDS):
                cat = {"priority": 2, "action": "RESPOND", "type": "scam"}
                # Refine type
                if "sim swap" in title_lower or "sim hijack" in title_lower:
                    cat["type"] = "victim_sim"
                elif "wallet" in title_lower or "crypto stolen" in title_lower:
                    cat["type"] = "victim_wallet"
                elif "relayshield" in title_lower:
                    cat = {"priority": 1, "action": "RESPOND", "type": "brand"}
            else:
                cat = GOOGLE_ALERTS_CATEGORY_DEFAULT.copy()

            mark_seen(entry_id, "google_alerts", title, url, "google_alerts")
            new_matches.append({
                "label":    "Google Alerts",
                "source":   "google_alerts",
                "title":    title,
                "url":      url,
                "summary":  summary[:300],
                "post_id":  entry_id,
                "priority": cat["priority"],
                "action":   cat["action"],
                "cat_type": cat["type"],
            })
            logger.info("New Google Alerts match [%s]: %s", cat["action"], title[:80])

    return new_matches

# ---------------------------------------------------------------------------
# Format and dispatch alerts
# ---------------------------------------------------------------------------

def _safe_title(title: str, max_len: int = 80) -> str:
    """Strip characters that break Telegram Markdown link syntax."""
    return title[:max_len].replace("[", "").replace("]", "").replace("`", "")


# Source emoji map
_SOURCE_EMOJI = {
    "reddit":        "📡",
    "google_alerts": "🔔",
}

# Action header config
_ACTION_HEADER = {
    "RESPOND": "🔴 *ACTION REQUIRED*",
    "INTEL":   "📊 *FYI / Intel*",
}


def _format_respond_item(m: dict) -> tuple[str, dict]:
    """
    Format a single RESPOND-priority match.
    Returns (message_text, reply_markup) — markup has Reply Drafted / Skip buttons.
    """
    sub      = m.get("subreddit", "")
    sub_str  = f" · r/{sub}" if sub else ""
    src      = "Google Alerts" if m["source"] == "google_alerts" else f"Reddit"
    draft_key = _make_draft_key(m["post_id"])

    text = "\n".join([
        f"🔴 *ACTION — {m['label']}*{sub_str}",
        f"_{src}_",
        f"[{_safe_title(m['title'])}]({m['url']})",
    ])

    reply_markup = {
        "inline_keyboard": [[
            {"text": "📝 Reply Drafted",  "callback_data": f"mdr_{draft_key}"},
            {"text": "⏭ Skip",            "callback_data": f"msk_{draft_key}"},
        ]]
    }
    return text, reply_markup


def _format_intel_batch(matches: list[dict]) -> str:
    """
    Format a batch of INTEL-only matches as a compact FYI message.
    No reply template — use for product/content research only.
    """
    count = len(matches)
    lines = [f"📊 *Intel / FYI — {count} item{'s' if count != 1 else ''}*\n"]
    for m in matches:
        src_emoji = _SOURCE_EMOJI.get(m["source"], "📌")
        sub       = m.get("subreddit", "")
        sub_str   = f" · r/{sub}" if sub else ""
        lines.append(
            f"{src_emoji} *{m['label']}*{sub_str}\n"
            f"  [{_safe_title(m['title'])}]({m['url']})\n"
        )
    return "\n".join(lines)


def dispatch_alerts(reddit_matches: list[dict], alerts_matches: list[dict]) -> None:
    """
    Priority-sorted dispatch:
      • RESPOND items → one Telegram message each, with draft reply template
      • INTEL items   → batched FYI messages, 8 per message
    Sends nothing if all lists are empty.
    """
    all_matches = reddit_matches + alerts_matches
    total = len(all_matches)
    if total == 0:
        logger.info("No new matches — nothing to send")
        return

    # Sort: priority ASC (1=highest), then action (RESPOND before INTEL)
    all_matches.sort(key=lambda m: (m.get("priority", 99), m.get("action", "Z")))

    respond_items = [m for m in all_matches if m.get("action") == "RESPOND"]
    intel_items   = [m for m in all_matches if m.get("action") != "RESPOND"]

    # Send each RESPOND item as its own message with inline keyboard
    for m in respond_items:
        text, markup = _format_respond_item(m)
        _store_draft_context(_make_draft_key(m["post_id"]), m)
        send_admin_message(text, reply_markup=markup)
        time.sleep(0.5)

    # Batch INTEL items (8 per message to stay under Telegram length limits)
    BATCH = 8
    for i in range(0, len(intel_items), BATCH):
        batch = intel_items[i:i + BATCH]
        send_admin_message(_format_intel_batch(batch))
        time.sleep(0.5)

    logger.info(
        "Dispatched: %d RESPOND + %d INTEL (%d Reddit, %d Google Alerts)",
        len(respond_items), len(intel_items), len(reddit_matches), len(alerts_matches),
    )

# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """
    Entry point. Called by EventBridge cron (every 4 hours).
    Also callable manually via Lambda test console with event={}.
    """
    logger.info("MONITOR-1 scan started — %s UTC", datetime.now(timezone.utc).isoformat())

    reddit_matches = scan_reddit()
    alerts_matches = scan_google_alerts()

    dispatch_alerts(reddit_matches, alerts_matches)

    total = len(reddit_matches) + len(alerts_matches)
    logger.info("MONITOR-1 scan complete — %d new matches total", total)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "reddit_new":        len(reddit_matches),
            "google_alerts_new": len(alerts_matches),
            "total_new":         total,
        }),
    }
