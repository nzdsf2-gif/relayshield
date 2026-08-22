"""
RelayShield INTEL-DISCOVERY — Telegram Channel Discovery

Searches Telegram for public channels matching threat-intel keywords using
Telethon's SearchGlobalRequest. Verifies each discovered channel is accessible
(get_entity succeeds), then writes confirmed channels to the
relayshield_intel_channels DynamoDB table.

At runtime, relayshield_intel_monitor reads its channel list from DynamoDB
instead of a hardcoded list — so new discoveries go live without a redeploy.

Architecture:
  EventBridge cron (1st of month, 08:00 UTC) OR GitHub Actions workflow_dispatch
  → Lambda (this file)
      → Telethon SearchGlobalRequest for each SEARCH_KEYWORDS term
      → get_entity() to verify accessibility
      → Write verified channels to relayshield_intel_channels
      → Telegram digest to ADMIN_CHAT_ID with new discoveries

DynamoDB table: relayshield_intel_channels
  PK: username (S)       — channel username (no @)
  category (S)           — inferred from keyword match
  description (S)
  member_count (N)
  first_seen (S)         — ISO timestamp
  last_verified (S)      — ISO timestamp
  active (BOOL)          — false = inaccessible on last check
"""

import asyncio
import json
import logging
import os
import re
import time
# Module level, not inside a function: _ransomlook_get() and
# _ransomlook_description() run at module scope. _send_telegram() has its
# own local import, which is why this was not already here.
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHANNELS_TABLE   = "relayshield_intel_channels"
TELETHON_SECRET  = "relayshield/telethon_session"
TG_SECRET_NAME   = "relayshield/telegram_bot_token"
TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"
ADMIN_CHAT_ID    = int(os.environ.get("ADMIN_CHAT_ID", "1729226804"))

# Max results per keyword search (Telegram caps at ~100)
MAX_PER_KEYWORD = 50

# Cross-promotion crawl (added 2026-07-22) — bounded messages read per
# already-tracked channel, to keep runtime and Telegram API load predictable
# regardless of how large the tracked-channel list grows.
MAX_MESSAGES_PER_CHANNEL = 100

# Matches both t.me/<username> links and bare @<username> mentions inside a
# message. Doesn't attempt to resolve t.me/joinchat/... private invite links
# (no username to extract — would need to actually join to resolve, out of
# scope for a read-only crawl).
TG_LINK_RE    = re.compile(r"(?:https?://)?t\.me/(\w{5,32})", re.IGNORECASE)
TG_MENTION_RE = re.compile(r"@(\w{5,32})")

# Keyword → inferred category
SEARCH_KEYWORDS = [
    ("stealer logs",        "infostealer"),
    ("infostealer logs",    "infostealer"),
    ("lummac2",             "infostealer"),
    ("redline stealer",     "infostealer"),

    # Malware-family / threat-actor brand names, added 2026-07-24. Higher
    # precision than the generic phrases above -- a channel bio literally
    # containing "StealC" or "LockBit" is a much stronger signal than one
    # containing "stealer logs". Dominant 2025-2026 stealer families and
    # active ransomware gangs not already covered.
    ("vidar stealer",       "infostealer"),
    ("raccoon stealer",     "infostealer"),
    ("meta stealer",        "infostealer"),
    ("stealc",              "infostealer"),
    ("lockbit",             "ransomware"),
    ("blackcat ransomware", "ransomware"),
    ("alphv",               "ransomware"),
    ("ransomhub",           "ransomware"),
    ("akira ransomware",    "ransomware"),
    ("play ransomware",     "ransomware"),
    ("cl0p",                "ransomware"),

    # --- OSINT sweep 002, 2026-08-21: SOCRadar named channels (founder-supplied) ---
    # Real channel NAMES from SOCRadar's stealer-log and top-groups tables.
    # Added as keywords rather than as channel rows because SOCRadar publishes
    # display names, not @handles, and this document's own rule is never to
    # invent one. A brand name also survives the renames these operations rely
    # on, which handles do not.
    #
    # Stealer-log distribution and credential aggregation:
    ("moon cloud",          "infostealer"),   # curates + republishes other channels' logs
    ("daisy cloud",         "infostealer"),   # "fresh one-hand logs", mostly RedLine
    ("log sync",            "infostealer"),   # free + premium tiers, community uploads
    ("observer cloud",      "credential_dump"),  # long-standing combo-list distribution
    ("alien txtbase",       "credential_dump"),  # the massive infostealer-derived dump
    ("data leak monitoring","credential_dump"),  # SOCRadar rates activity "very high"
    ("mailpass",            "credential_dump"),  # EMP/mailpass/sqli chat
    ("bidencash shop",      "card_shop"),
    ("cti now",             "general"),          # news tracking, useful as a cross-promo seed
    #
    # Hacktivist crews — four of SOCRadar's ten most active groups. New
    # category; see INTEL_CATEGORIES in relayshield_intel_monitor.py for why
    # these are MEDIUM rather than HIGH.
    ("noname057",           "hacktivist"),
    ("rippersec",           "hacktivist"),
    ("dark storm team",     "hacktivist"),
    ("z-pentest",           "hacktivist"),
    #
    # NOT added: bare "alien". It is an ordinary English word and would match
    # hundreds of unrelated channels — the generic-phrase trap this list has
    # already been burned by once. "alien txtbase" is the operation's actual
    # name and is specific.

    # --- OSINT sweep 001b, 2026-08-22 ---
    # The four most active ransomware operations of 2026 per current reporting,
    # NONE of which were in this list: the existing ransomware keywords are the
    # 2024-2025 cohort (LockBit, ALPHV, Cl0p, Play), and the leaderboard has
    # moved. Qilin and DragonForce in particular post-date every keyword here.
    #
    # Ransomware is also one of the thinnest categories in the seeded channel
    # list -- 2 channels against 7 infostealer -- so this is coverage that does
    # not exist rather than depth on a category that is already strong.
    ("qilin",               "ransomware"),
    ("dragonforce",         "ransomware"),
    ("thegentlemen",        "ransomware"),
    ("babuk",               "ransomware"),

    # --- OSINT sweep 001, 2026-08-21 (intel_channel_recommendations.md) ---
    # Platform and operation BRAND names, not generic phrases. Reporting is
    # explicit that these operations survive takedowns by rotating channel
    # names and running mirrors, so a hand-curated handle list decays within
    # weeks. A brand name keeps finding whatever the current channel is called,
    # which is the whole reason the sweep outputs keywords rather than handles.
    #
    # Weighted deliberately toward phaas / sim_swap / card_shop: the seeded
    # channel list carries ZERO of all three, so these create coverage that does
    # not exist rather than deepening infostealer, which is already the
    # strongest category.
    ("omega cloud",         "infostealer"),
    ("moon cloud",          "infostealer"),
    ("bidencash",           "card_shop"),
    ("darcula",             "phaas"),
    ("magic cat",           "phaas"),
    ("otp bot",             "sim_swap"),
    ("sim swap service",    "sim_swap"),

    # Card-shop keywords added 2026-08-21. The monitor has carried a label and a
    # severity for "card_shop" since it was written, but no discovery path and
    # no classifier vocabulary could ever produce one, so the category existed
    # only as a dead branch in the alert formatter.
    ("cc shop",             "card_shop"),
    ("dumps and pins",      "card_shop"),
    ("fullz",               "card_shop"),

    ("credential dump",     "credential_dump"),
    ("data breach",         "credential_dump"),
    ("leaked database",     "credential_dump"),
    ("combolist",           "credential_dump"),
    ("sim swap",            "sim_swap"),
    ("port out fraud",      "sim_swap"),
    ("crypto drainer",      "crypto"),
    ("wallet drainer",      "crypto"),
    ("web3 security",       "crypto"),
    ("rug pull",            "crypto"),
    ("threat intelligence", "general"),
    ("darkfeed",            "general"),
    ("malware analysis",    "general"),
    ("phishing kit",        "phaas"),
    ("phishing as a service", "phaas"),
    ("smishing kit",        "phaas"),
    ("scam page builder",   "phaas"),

    # Non-English keywords, added 2026-07-22 — the English-only list above
    # plateaued around ~40 channels since it can only find channels whose
    # name/bio literally contains one of these phrases. Russian, Portuguese,
    # and Spanish-language criminal Telegram markets are a real, documented
    # segment this couldn't reach at all. Direct translations/transliterations
    # of the same concepts above — a first pass, not a claimed-authoritative
    # slang lexicon. English loanwords are genuinely common even in non-English
    # criminal channels (e.g. "стиллер" is a transliteration, not translation),
    # so both forms are included where that's the more realistic real-world term.
    ("логи стилера",        "infostealer"),   # RU: stealer logs
    ("стиллер логи",        "infostealer"),   # RU: stealer logs (transliterated)
    ("logs de stealer",     "infostealer"),   # PT/ES: stealer logs
    ("дамп базы",           "credential_dump"),  # RU: database dump
    ("комболист",           "credential_dump"),  # RU: combolist (transliterated)
    ("lista combo",         "credential_dump"),  # PT/ES: combolist
    ("base de dados vazada", "credential_dump"), # PT: leaked database
    ("base de datos filtrada", "credential_dump"), # ES: leaked database
    ("дренер кошельков",    "crypto"),          # RU: wallet drainer (transliterated)
    ("drainer de carteira", "crypto"),          # PT: wallet drainer
    ("drainer de billetera", "crypto"),         # ES: wallet drainer
    ("фишинг кит",          "phaas"),           # RU: phishing kit (transliterated)
    ("kit de phishing",     "phaas"),           # PT/ES: phishing kit
    ("phishing como servico", "phaas"),         # PT: phishing as a service
    ("sim swap fraude",     "sim_swap"),        # PT/ES: SIM swap fraud

    # Chinese + Korean keywords, added 2026-07-24 — same "first pass, not an
    # authoritative slang lexicon" caveat as the RU/PT/ES batch above. Chinese
    # is the stronger addition: a real, documented overseas/diaspora criminal
    # Telegram ecosystem (carding, crypto "pig-butchering" scam operations,
    # credential-stuffing crews) that GFW blocking domestic access doesn't
    # prevent. Korean's documented Telegram-criminal footprint is thinner —
    # included on the same near-zero marginal cost basis, not a strong claim
    # of expected yield. Worth a native-speaker sanity check on results if
    # either language starts surfacing real candidates.
    ("撞库",                "credential_dump"),  # ZH: credential stuffing (precise infosec term, not a vague translation)
    ("料子",                "credential_dump"),  # ZH: carding/personal-data slang for "goods"
    ("肉鸡",                "general"),          # ZH: botnet/compromised host ("meat chicken")
    ("窃密木马",             "infostealer"),      # ZH: info-stealer trojan
    ("스틸러 로그",          "infostealer"),      # KO: stealer logs
    ("유출 데이터",          "credential_dump"),  # KO: leaked data
]

# ---------------------------------------------------------------------------
# AWS / Telethon helpers (mirror of intel_monitor pattern)
# ---------------------------------------------------------------------------

_sm      = boto3.client("secretsmanager", region_name="us-east-1")
_dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

# Single-flight lock — shares the same table as relayshield_intel_monitor.py's
# own lock (relayshield_intel_monitor_lock) but a distinct lock_id, since this
# is a separate Lambda that also opens the same shared Telethon session.
# Added 2026-07-27 after two overlapping invocations (EventBridge's stale
# monthly rule + the GH Actions weekly workflow, both targeting this same
# function) triggered AuthKeyDuplicatedError — same failure class as
# INCIDENT-4, which is why intel_monitor.py already has this pattern and this
# file didn't. TTL kept just under this Lambda's own 600s timeout.
LOCK_TABLE       = "relayshield_intel_monitor_lock"
LOCK_ID          = "discovery_singleton"
LOCK_TTL_SECONDS = 580


def _acquire_lock() -> bool:
    now = int(time.time())
    try:
        _dynamodb.Table(LOCK_TABLE).put_item(
            Item={"lock_id": LOCK_ID, "ttl": Decimal(now + LOCK_TTL_SECONDS), "acquired_at": now},
            ConditionExpression="attribute_not_exists(lock_id) OR #ttl < :now",
            ExpressionAttributeNames={"#ttl": "ttl"},
            ExpressionAttributeValues={":now": now},
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


def _release_lock() -> None:
    try:
        _dynamodb.Table(LOCK_TABLE).delete_item(Key={"lock_id": LOCK_ID})
    except Exception:
        logger.warning("Failed to release intel-discovery lock", exc_info=True)


def _get_secret(name: str) -> dict:
    return json.loads(_sm.get_secret_value(SecretId=name)["SecretString"])


def _get_bot_token() -> str:
    return _get_secret(TG_SECRET_NAME)["telegram_bot_token"]


def _send_telegram(token: str, chat_id: int, text: str) -> None:
    import urllib.request, urllib.error
    url = TELEGRAM_API_BASE.format(token=token, method="sendMessage")
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        logger.error("Telegram notify failed: %s", exc)


# ---------------------------------------------------------------------------
# Core discovery logic (async — runs inside asyncio.run())
# ---------------------------------------------------------------------------

async def _get_member_count(client, entity) -> int:
    """participants_count isn't populated on the basic entity get_entity()
    returns — it only comes back on a full GetFullChannelRequest lookup."""
    from telethon.tl.functions.channels import GetFullChannelRequest

    try:
        full = await client(GetFullChannelRequest(entity))
        return getattr(full.full_chat, "participants_count", 0) or 0
    except Exception as exc:
        logger.info("Could not fetch member count for @%s: %s", getattr(entity, "username", entity), exc)
        return 0


async def _discover(session_data: dict) -> dict:
    from telethon import TelegramClient
    from telethon.tl.functions.contacts import SearchRequest
    from telethon.sessions import StringSession

    api_id      = int(session_data["api_id"])
    api_hash    = session_data["api_hash"]
    session_str = session_data["session_string"]

    client = TelegramClient(StringSession(session_str), api_id, api_hash)
    await client.connect()

    table = _dynamodb.Table(CHANNELS_TABLE)
    now_ts = datetime.now(timezone.utc).isoformat()

    seen_usernames: set[str] = set()
    newly_added: list[dict] = []
    re_verified: list[str]  = []
    inaccessible: list[str] = []

    for keyword, category in SEARCH_KEYWORDS:
        logger.info("Searching keyword: %s", keyword)
        try:
            result = await client(SearchRequest(q=keyword, limit=MAX_PER_KEYWORD))
        except Exception as exc:
            logger.warning("Search failed for '%s': %s", keyword, exc)
            await asyncio.sleep(2)
            continue

        for chat in getattr(result, "chats", []):
            username = getattr(chat, "username", None)
            if not username:
                continue
            username = username.lower()
            if username in seen_usernames:
                continue
            seen_usernames.add(username)

            # Check if already in table
            existing = table.get_item(Key={"username": username}).get("Item")
            if existing and existing.get("active"):
                re_verified.append(username)
                table.update_item(
                    Key={"username": username},
                    UpdateExpression="SET last_verified = :ts",
                    ExpressionAttributeValues={":ts": now_ts},
                )
                continue

            # Verify accessibility
            try:
                entity = await client.get_entity(username)
            except Exception as exc:
                logger.info("Inaccessible: @%s — %s", username, exc)
                inaccessible.append(username)
                await asyncio.sleep(1)
                continue
            member_count = await _get_member_count(client, entity)

            description = getattr(chat, "title", username)
            item = {
                "username":      username,
                "category":      existing.get("category", category) if existing else category,
                "description":   description,
                "member_count":  member_count,
                "first_seen":    existing.get("first_seen", now_ts) if existing else now_ts,
                "last_verified": now_ts,
                "active":        True,
                "keyword_match": keyword,
            }
            table.put_item(Item=item)
            newly_added.append({"username": username, "description": description, "members": member_count, "category": category})
            logger.info("Added channel: @%s (%d members, %s)", username, member_count, category)
            await asyncio.sleep(1)  # rate-limit courtesy pause

        await asyncio.sleep(3)  # pause between keyword searches

    # --- Cross-promotion graph crawl (added 2026-07-22) ---
    # Criminal channels routinely link/promote each other in pinned or recent
    # posts. A channel found this way doesn't need to match any keyword at
    # all — the already-tracked channel vouching for it is a stronger signal
    # than a generic keyword hit, and reaches channels the keyword search
    # structurally can't (coded names, slang, non-covered languages).
    crossp_added, crossp_inaccessible = await _crawl_cross_promotion(
        client, table, seen_usernames, now_ts,
    )
    newly_added.extend(crossp_added)
    inaccessible.extend(crossp_inaccessible)

    await client.disconnect()

    return {
        "newly_added":   newly_added,
        "re_verified":   re_verified,
        "inaccessible":  inaccessible,
    }



# Seed categories for the cross-promotion crawl, curated 2026-07-24 against
# real data from the OSINT-2 classifier run: of 141 pending_review candidates
# classified, every single approval (breachforums, evil_proxy, evilproxy)
# came from a credential_dump or phaas source; zero came from "crypto" or
# "general" sources, which together accounted for the bulk of the 138
# rejections (web3/rugpull chat participants, generic personal accounts).
# Crawling those two categories as seeds was mostly wasted Bedrock spend and
# Telegram API calls on candidates that were essentially always rejected.
CROSS_PROMOTION_SEED_CATEGORIES = {"infostealer", "credential_dump", "phaas", "ransomware", "sim_swap"}


async def _crawl_cross_promotion(client, table, seen_usernames: set[str], now_ts: str) -> tuple[list[dict], list[str]]:
    """
    Reads recent messages from already-tracked active channels in the
    curated CROSS_PROMOTION_SEED_CATEGORIES (see rationale above), looking
    for t.me links and @mentions pointing at channels not yet tracked.
    Bounded to MAX_MESSAGES_PER_CHANNEL per source channel to keep runtime
    and API load predictable as the tracked-channel list grows.
    """
    newly_added: list[dict] = []
    inaccessible: list[str] = []

    resp = table.scan(FilterExpression=Attr("active").eq(True) & Attr("category").is_in(list(CROSS_PROMOTION_SEED_CATEGORIES)))
    tracked = resp.get("Items", [])

    for source in tracked:
        source_username = source["username"]
        try:
            source_entity = await client.get_entity(source_username)
            messages = await client.get_messages(source_entity, limit=MAX_MESSAGES_PER_CHANNEL)
        except Exception as exc:
            logger.warning("Cross-promo crawl failed for @%s: %s", source_username, exc)
            await asyncio.sleep(1)
            continue

        candidates: set[str] = set()
        for msg in messages:
            text = getattr(msg, "message", "") or ""
            candidates.update(m.lower() for m in TG_LINK_RE.findall(text))
            candidates.update(m.lower() for m in TG_MENTION_RE.findall(text))
        # A channel mentioning itself isn't a cross-promotion find.
        candidates.discard(source_username.lower())

        for candidate in candidates:
            if candidate in seen_usernames:
                continue
            seen_usernames.add(candidate)

            existing = table.get_item(Key={"username": candidate}).get("Item")
            if existing and existing.get("active"):
                continue  # already tracked — the main keyword loop already re-verifies it

            try:
                cand_entity = await client.get_entity(candidate)
            except Exception as exc:
                logger.info("Cross-promo candidate inaccessible: @%s — %s", candidate, exc)
                inaccessible.append(candidate)
                await asyncio.sleep(1)
                continue
            member_count = await _get_member_count(client, cand_entity)

            description = getattr(cand_entity, "title", candidate)
            item = {
                "username":         candidate,
                # New candidates default to pending_review -- the same safe
                # queue _queue_discovered_channels and _extract_invite_links
                # already use -- so the OSINT-2 classifier (which only scans
                # category=pending_review) actually sees them. Bug found and
                # fixed 2026-07-24: this previously inherited the *source*
                # channel's real category (e.g. "crypto"), which made new
                # cross-promotion candidates invisible to the classifier --
                # inactive, but never queued for review, sitting inert
                # forever. Existing entries still preserve whatever category
                # they already have, unchanged.
                "category":         existing.get("category") if existing else "pending_review",
                "description":      description,
                "member_count":     member_count,
                "first_seen":       existing.get("first_seen", now_ts) if existing else now_ts,
                "last_verified":    now_ts,
                "active":           False,
                "discovery_method": "cross_promotion",
                "found_via":        source_username,
            }
            table.put_item(Item=item)
            newly_added.append({
                "username": candidate, "description": description,
                "members": member_count, "category": item["category"],
            })
            logger.info("Cross-promo added: @%s (via @%s, %d members)", candidate, source_username, member_count)
            await asyncio.sleep(1)  # rate-limit courtesy pause

        await asyncio.sleep(2)  # pause between source channels

    return newly_added, inaccessible


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# RansomLook — a discovery source that needs no Telegram session
# ---------------------------------------------------------------------------
# WHY. Every other path here finds channels by searching Telegram, which needs
# the Telethon session and is rate-limited. RansomLook is a free public
# aggregator that already tracks ransomware-gang Telegram channels and
# publishes them over a plain unauthenticated API. It is a self-updating supply
# of exactly the category this corpus is thinnest in — 2 seeded ransomware
# channels against 7 infostealer.
#
# CONTRACT, READ FROM THEIR SOURCE, NOT GUESSED. `www.ransomlook.io` is blocked
# by this dev sandbox's egress proxy, so the endpoints below were taken from
# RansomLook/RansomLook `website/web/api/telegramapi.py` on GitHub rather than
# from a live call:
#
#   GET /api/telegram/channels        -> ["channelname", ...]   (flat string list)
#   GET /api/telegram/channel/<name>  -> [group, posts]         (group.meta = description)
#
# THIS HAS NOT BEEN EXERCISED AGAINST THE LIVE SERVICE. It is written to fail
# soft everywhere and to add nothing on an unexpected shape, so the worst case
# is a no-op run and a log line. Confirm the first real run's admin digest
# before trusting the count.
#
# WHAT IT DOES NOT DO. It does not resolve channels through Telethon and does
# not activate anything. Every row lands as category="pending_review",
# active=False — the same safe queue as the cross-promotion crawl — so the
# OSINT-2 classifier is what decides, not this.

RANSOMLOOK_BASE          = os.environ.get("RANSOMLOOK_BASE", "https://www.ransomlook.io")
RANSOMLOOK_ENABLED       = os.environ.get("RANSOMLOOK_INGEST", "1").lower() in ("1", "true", "yes")
RANSOMLOOK_MAX_CHANNELS  = int(os.environ.get("RANSOMLOOK_MAX", "200"))
# One extra call per NEW channel to fetch its description, which is most of what
# the classifier has to reason about. Bounded separately because it is the part
# that scales with their catalogue rather than with ours.
RANSOMLOOK_MAX_DETAIL    = int(os.environ.get("RANSOMLOOK_MAX_DETAIL", "40"))


def _ransomlook_get(path: str, timeout: int = 20):
    """GET a RansomLook API path. Returns None on any failure, never raises."""
    try:
        req = urllib.request.Request(
            f"{RANSOMLOOK_BASE}{path}",
            headers={"User-Agent": "RelayShield-IntelDiscovery/1.0",
                     "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:
        logger.warning("RansomLook fetch failed path=%s: %s", path, exc)
        return None


def _ransomlook_description(name: str) -> str:
    """Channel description from /api/telegram/channel/<name>.

    Their handler returns [group, posts]; `group['meta']` is the description and
    can be None. Anything unexpected yields "" rather than an error — a missing
    description costs the classifier some signal, which is survivable; a raised
    exception would cost the whole run.
    """
    data = _ransomlook_get(f"/api/telegram/channel/{urllib.parse.quote(name)}")
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return ""
    meta = data[0].get("meta") or ""
    return str(meta).replace("<br/>", " ").strip()[:400]


def ingest_ransomlook_channels() -> list[dict]:
    """Queue RansomLook's tracked ransomware Telegram channels for review.

    Returns the rows added, for the admin digest. Never raises.
    """
    if not RANSOMLOOK_ENABLED:
        return []

    names = _ransomlook_get("/api/telegram/channels")
    if not isinstance(names, list):
        logger.warning("RansomLook /channels returned %s, not a list — skipping",
                       type(names).__name__)
        return []

    # Defend against the shape changing under us: keep only plain strings that
    # look like Telegram usernames. A dict-of-objects response would otherwise
    # write garbage usernames into the channel table.
    clean = []
    for n in names:
        if not isinstance(n, str):
            continue
        u = n.strip().lstrip("@").lower()
        if u and re.fullmatch(r"[a-z0-9_]{4,32}", u):
            clean.append(u)
    if not clean:
        logger.warning("RansomLook /channels held no usable usernames (%d raw entries)", len(names))
        return []

    logger.info("RansomLook: %d channels published, %d usable", len(names), len(clean))

    table   = _dynamodb.Table(CHANNELS_TABLE)
    now_ts  = datetime.now(timezone.utc).isoformat()
    added: list[dict] = []
    detail_budget = RANSOMLOOK_MAX_DETAIL

    for username in clean[:RANSOMLOOK_MAX_CHANNELS]:
        try:
            existing = table.get_item(Key={"username": username}).get("Item")
        except Exception as exc:
            logger.warning("RansomLook: channel lookup failed @%s: %s", username, exc)
            continue

        # Never touch a channel we already know about. An active one is being
        # monitored, and a rejected one was rejected on purpose — re-queueing it
        # every run would make the classifier re-pay for the same verdict.
        if existing:
            continue

        description = ""
        if detail_budget > 0:
            description = _ransomlook_description(username)
            detail_budget -= 1
            time.sleep(0.2)   # courtesy pause against a free community service

        try:
            table.put_item(Item={
                "username":         username,
                "category":         "pending_review",
                "description":      description or f"RansomLook-tracked ransomware channel: {username}",
                "member_count":     0,          # unknown until Telethon resolves it
                "first_seen":       now_ts,
                "last_verified":    now_ts,
                "active":           False,
                "discovery_method": "ransomlook",
                "found_via":        "ransomlook.io/api/telegram/channels",
                # The category RansomLook implies, kept separately from
                # `category` so the classifier still makes its own call but has
                # the provenance to weigh.
                "source_category":  "ransomware",
            })
            added.append({"username": username, "description": description,
                          "members": 0, "category": "pending_review"})
        except Exception as exc:
            logger.warning("RansomLook: queue failed @%s: %s", username, exc)

    logger.info("RansomLook ingest: %d new channels queued", len(added))
    return added


def lambda_handler(event, context):
    logger.info("INTEL-DISCOVERY starting")

    if not _acquire_lock():
        logger.warning("Another invocation already holds the discovery lock — exiting without touching the Telegram session")
        return {"statusCode": 200, "skipped": "lock_held"}

    try:
        session_data = _get_secret(TELETHON_SECRET)
        bot_token    = _get_bot_token()

        results = asyncio.run(_discover(session_data))

        # Runs AFTER the Telegram sweep, deliberately: it needs no session and
        # must not be able to burn the run's Telethon budget or trip a
        # flood-wait before the keyword search has had its turn.
        try:
            ransomlook_added = ingest_ransomlook_channels()
        except Exception as exc:
            logger.warning("RansomLook ingest failed, continuing: %s", exc)
            ransomlook_added = []

        newly_added  = results["newly_added"]
        re_verified  = results["re_verified"]
        inaccessible = results["inaccessible"]

        logger.info(
            "Discovery complete: %d new, %d re-verified, %d inaccessible",
            len(newly_added), len(re_verified), len(inaccessible),
        )

        # Build admin digest
        lines = ["<b>RelayShield INTEL-DISCOVERY</b>"]
        if newly_added:
            lines.append(f"\n<b>{len(newly_added)} new channels found:</b>")
            for ch in newly_added:
                lines.append(f"  @{ch['username']} — {ch['description']} ({ch['members']:,} members, {ch['category']})")
        else:
            lines.append("\nNo new channels discovered this run.")

        if ransomlook_added:
            lines.append(f"\n<b>{len(ransomlook_added)} channels queued from RansomLook:</b>")
            for ch in ransomlook_added[:15]:
                lines.append(f"  @{ch['username']} — {(ch['description'] or '')[:60]}")
            if len(ransomlook_added) > 15:
                lines.append(f"  …and {len(ransomlook_added) - 15} more")
            lines.append("  <i>All pending_review — run the classifier to triage.</i>")

        lines.append(f"\n{len(re_verified)} existing channels re-verified active.")
        if inaccessible:
            lines.append(f"{len(inaccessible)} channels inaccessible (private/banned).")

        _send_telegram(bot_token, ADMIN_CHAT_ID, "\n".join(lines))

        return {
            "statusCode": 200,
            "newly_added": len(newly_added),
            "ransomlook_queued": len(ransomlook_added),
            "re_verified": len(re_verified),
            "inaccessible": len(inaccessible),
        }
    finally:
        _release_lock()
