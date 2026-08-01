"""
relayshield_intel_substack — Weekly Lambda
Polls configured Substack RSS feeds, extracts IOCs and named threat actors from
new posts, and ingests them into relayshield_intel_iocs with full attribution.

Scheduled: EventBridge weekly (Mondays 07:00 UTC)
Tracks processed article GUIDs in relayshield_intel_seen to avoid re-ingestion.

Configured feeds (add more in SUBSTACK_FEEDS):
  - cyberwarrior76.substack.com — threat actor + IOC bulletins

Threat-actor extraction (added 2026-08-01)
-----------------------------------------
Until 2026-08-01 every ingested IOC was written with a hardcoded
`threat_actor: "Unknown (Substack bulletin)"` — the pipeline never looked for
actor names at all, so named groups in these bulletins (Mango Sandstorm,
Seedworm, ...) contributed nothing to the Threat Actor surface. Actor names and
aliases are now resolved against the live MITRE ATT&CK corpus and recorded both
on the IOC records and as per-group `sighting:` records in
`relayshield_mitre_attack`, which /v1/intel/actor surfaces as recent reporting.

IOC precision (added 2026-08-01)
--------------------------------
The old extractor ingested every domain anywhere in the article body, so
citations became indicators: www.bbc.com, bloomberg.com, sans.org, owasp.org and
~40 other reference domains were sitting in the billed IOC corpus at confidence
0.70. Network indicators (domain/IP/URL) are now only ingested when the author
signalled intent — either defanged, or inside a section whose heading marks it as
indicator material. Self-evident indicator types (hashes, onions, CVEs) are still
taken from anywhere in the document, since a 64-hex string is never a citation.
"""

import hashlib
import json
import logging
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Attr, Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

IOCS_TABLE   = "relayshield_intel_iocs"
SEEN_TABLE   = "relayshield_intel_seen"
ATTACK_TABLE = "relayshield_mitre_attack"

_dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

# ── Configured Substack feeds ──────────────────────────────────────────────
SUBSTACK_FEEDS = [
    {
        "url":    "https://cyberwarrior76.substack.com/feed",
        "author": "Cyber News Network / cyberwarrior76",
        "tags":   ["threat_actor", "ioc", "apt"],
    },
    # Add more feeds here as needed:
    # { "url": "https://example.substack.com/feed", "author": "...", "tags": [...] },
]

# ── Defang normalisation ───────────────────────────────────────────────────

def _defang(text: str) -> str:
    """Re-fang common defanging patterns used in threat intel posts."""
    # Dot variants
    t = re.sub(r'\[\.\]', '.', text, flags=re.IGNORECASE)
    t = re.sub(r'\(\.\)', '.', t, flags=re.IGNORECASE)
    t = re.sub(r'\[dot\]', '.', t, flags=re.IGNORECASE)
    t = re.sub(r'\(dot\)', '.', t, flags=re.IGNORECASE)
    # HTTP variants
    t = re.sub(r'hxxps?://', lambda m: m.group(0).replace('xx', 'tt'), t, flags=re.IGNORECASE)
    t = re.sub(r'h\[tt\]ps?://', lambda m: 'https://' if 's' in m.group(0) else 'http://', t, flags=re.IGNORECASE)
    # At-sign variants
    t = re.sub(r'\[at\]', '@', t, flags=re.IGNORECASE)
    t = re.sub(r'\(at\)', '@', t, flags=re.IGNORECASE)
    return t


# ── IOC extraction ─────────────────────────────────────────────────────────

_RE_DOMAIN = re.compile(
    r'\b(?:[a-zA-Z0-9\-]{1,63}\.)+(?:'
    r'com|net|org|io|co|app|xyz|info|biz|ru|me|cc|pw|tk|top|site|online|'
    r'pro|to|su|cx|sh|gg|tv|dev|ai|cloud|host|group|online|store|tech|live'
    r')\b',
    re.IGNORECASE,
)
_RE_IPV4   = re.compile(
    r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b'
)
_RE_SHA256 = re.compile(r'\b[a-fA-F0-9]{64}\b')
_RE_MD5    = re.compile(r'\b[a-fA-F0-9]{32}\b')
_RE_SHA1   = re.compile(r'\b[a-fA-F0-9]{40}\b')
_RE_URL    = re.compile(r'https?://[^\s<>"\']{10,}')
_RE_CVE    = re.compile(r'CVE-\d{4}-\d{4,7}', re.IGNORECASE)
_RE_ONION  = re.compile(r'\b[a-z2-7]{16,56}\.onion\b', re.IGNORECASE)

# Domains that appear in these bulletins as citations, tooling references or
# standards links rather than as indicators. Everything here was observed in the
# live corpus on 2026-08-01, having been ingested as a threat indicator.
_SKIP_DOMAINS = {
    # platforms / infra
    "substack.com", "substackcdn.com", "example.com", "google.com",
    "github.com", "twitter.com", "x.com", "linkedin.com", "youtube.com",
    "cloudflare.com", "amazonaws.com", "microsoft.com", "learn.microsoft.com",
    "entra.microsoft.com", "login.microsoftonline.com", "cloud.google.com",
    "generativelanguage.googleapis.com", "kubernetes.io", "medium.com",
    "huggingface.co", "openai.com", "protonmail.com", "feedly.com",
    "modelcontextprotocol.io", "cursor.app",
    # news
    "www.bbc.com", "bbc.com", "www.bloomberg.com", "bloomberg.com",
    "www.cnbc.com", "cnbc.com", "techcrunch.com", "thenextweb.com",
    "www.techrepublic.com", "techrepublic.com", "apnews.com", "reuters.com",
    "wired.com", "arstechnica.com", "theregister.com",
    # security press / vendors / standards
    "cybersecuritynews.com", "gbhackers.com", "bleepingcomputer.com",
    "thehackernews.com", "krebsonsecurity.com", "darkreading.com",
    "www.sans.org", "sans.org", "owasp.org", "genai.owasp.org",
    "portswigger.net", "www.elastic.co", "elastic.co", "socprime.com",
    "www.synacktiv.com", "synacktiv.com", "www.cybertriage.com",
    "thinkdfir.com", "insiderthreatmatrix.org", "ransomware.live",
    "www.giac.org", "giac.org", "www.iso.org", "iso.org", "blackhat.com",
    "metr.org", "naic.org", "chamd5.org", "www.nri-secure.co",
    "gandalf.lakera.ai", "attack.mitre.org", "mitre.org", "cisa.gov",
    "virustotal.com", "abuse.ch", "malpedia.caad.fkie.fraunhofer.de",
    "claroty.com", "www.claroty.com", "atlas.mitre.org", "censys.io",
    "shodan.io", "cli.shodan.io", "anthropic.com", "asp.net",
    "crowdstrike.com", "sentinelone.com", "trellix.com", "mandiant.com",
    "unit42.paloaltonetworks.com", "securelist.com", "welivesecurity.com",
    "talosintelligence.com", "recordedfuture.com",
    # e-commerce / legitimate API infra / government reference material
    "alibaba.com", "aliexpress.com", "api-inference.huggingface.co",
    "public.cyber.mil", "intranet.corp.local", "gs.thc.org", "thc.org",
    "nvlpubs.nist.gov", "www.nist.gov", "nist.gov", "www.nsa.gov", "nsa.gov",
    "eur-lex.europa.eu", "rdi.berkeley.edu", "pluto.security",
}

# Public infrastructure that shows up in indicator sections as a technique
# example (DoH resolvers, RFC docs) rather than as an indicator.
_SKIP_IPS = {
    "1.1.1.1", "1.0.0.1", "8.8.8.8", "8.8.4.4", "9.9.9.9", "149.112.112.112",
    "208.67.222.222", "208.67.220.220", "1.2.3.4", "8.8.8.0",
}

# Section headings that mark their body as indicator material rather than prose.
_IOC_HEADING = re.compile(
    r"indicator|\bIOCs?\b|infrastructure|command[\s\-]and[\s\-]control|\bC2\b|"
    r"hashes|file\s+system|network\s+observable|detection|hunting|"
    r"blocklist|block\s+and\s+retro",
    re.IGNORECASE,
)

# A token the author deliberately defanged. Author intent is unambiguous, so
# these are trusted wherever they appear in the document.
_RE_DEFANGED = re.compile(
    r"(?:hxxp|h\[tt\]p)s?://\S+"
    r"|(?:[a-zA-Z0-9\-]{1,63}(?:\[\.\]|\(\.\)|\[dot\]|\(dot\)))+[a-zA-Z0-9\-]{2,63}",
    re.IGNORECASE,
)

# Confidence by how the indicator was signalled.
_CONF_DEFANGED    = "0.90"   # author explicitly defanged it
_CONF_IOC_SECTION = "0.75"   # sat under an indicator/infrastructure heading
_CONF_DOCUMENT    = "0.75"   # self-evident type (hash/onion/CVE) anywhere


def _split_sections(html: str) -> list[tuple[str, str]]:
    """Split article HTML into (heading, body-text) blocks.

    Used to tell indicator material from prose: a domain under
    "B. CISA IOCs" is an indicator, the same domain in a sources list is not.
    """
    parts = re.split(r"<h[1-6][^>]*>(.*?)</h[1-6]>", html, flags=re.S | re.IGNORECASE)
    if not parts:
        return []
    sections = [("", _strip_html(parts[0]))]
    for i in range(1, len(parts) - 1, 2):
        sections.append((_strip_html(parts[i]), _strip_html(parts[i + 1])))
    return sections


def _network_iocs(text: str) -> dict[str, set]:
    """Domains / IPs / URLs from a block of already-refanged text."""
    domains = {
        d.lower() for d in _RE_DOMAIN.findall(text)
        if d.lower() not in _SKIP_DOMAINS and len(d) > 5
    }
    ips = {
        ip for ip in _RE_IPV4.findall(text)
        if ip not in _SKIP_IPS
        and not ip.startswith(("10.", "192.168.", "172.", "127.", "0.", "255."))
    }
    urls = {
        u for u in _RE_URL.findall(text)
        if not any(s in u for s in _SKIP_DOMAINS) and not any(s in u for s in _SKIP_IPS)
    }
    return {"domains": domains, "ips": ips, "urls": urls}


def extract_iocs(html: str) -> dict[str, list[dict]]:
    """Extract IOCs from article HTML, scoped by how the author signalled them.

    Returns {category: [{"value", "confidence", "provenance"}, ...]}.

    Network indicators are only taken when the author marked them as such
    (defanged, or under an indicator heading). Prose mentions are dropped —
    that path is what put www.bbc.com and sans.org into the corpus.
    """
    plain = _strip_html(html)
    clean = _defang(plain)

    picked: dict[str, dict[str, dict]] = {
        k: {} for k in ("domains", "ips", "urls", "sha256", "md5", "sha1", "cves", "onions")
    }

    def _add(category: str, value: str, confidence: str, provenance: str) -> None:
        if not value:
            return
        slot = picked[category]
        # First writer wins, and defanged (highest confidence) is applied first.
        if value not in slot:
            slot[value] = {"value": value, "confidence": confidence, "provenance": provenance}

    # (1) Defanged tokens — unambiguous author intent, trusted anywhere.
    for token in _RE_DEFANGED.findall(plain):
        refanged = _defang(token)
        for category, values in _network_iocs(refanged).items():
            for v in values:
                _add(category, v, _CONF_DEFANGED, "defanged")

    # (2) Self-evident indicator types — safe anywhere in the document.
    sha256 = {h.lower() for h in _RE_SHA256.findall(clean)}
    for h in sha256:
        _add("sha256", h, _CONF_DOCUMENT, "document")
    for h in {x.lower() for x in _RE_MD5.findall(clean)}:
        if h not in {s[:32] for s in sha256}:
            _add("md5", h, _CONF_DOCUMENT, "document")
    for h in {x.lower() for x in _RE_SHA1.findall(clean)}:
        if h not in {s[:40] for s in sha256}:
            _add("sha1", h, _CONF_DOCUMENT, "document")
    for c in {x.upper() for x in _RE_CVE.findall(clean)}:
        _add("cves", c, _CONF_DOCUMENT, "document")
    for o in {x.lower() for x in _RE_ONION.findall(clean)}:
        _add("onions", o, _CONF_DOCUMENT, "document")

    # (3) Network indicators under an indicator-bearing heading.
    for heading, body in _split_sections(html):
        if not heading or not _IOC_HEADING.search(heading):
            continue
        for category, values in _network_iocs(_defang(body)).items():
            for v in values:
                _add(category, v, _CONF_IOC_SECTION, "ioc_section")

    return {k: list(v.values()) for k, v in picked.items()}


# ── Threat-actor extraction (MITRE ATT&CK backed) ──────────────────────────
#
# Matching is tiered by how distinctive the name is, because MITRE aliases
# include ordinary English words. "Play" and "Karma" are real groups but also
# common prose; matching them naively would attribute half the feed to them.
#
#   distinctive — multi-word, contains a digit, or >= 8 chars. Case-insensitive.
#                 ("Mango Sandstorm", "MuddyWater", "APT33")
#   exact       — short single word. Requires MITRE's exact capitalisation.
#                 ("Turla", "OilRig", "ZINC")
#   guarded     — short single word that is also ordinary English. Requires
#                 exact case AND a threat-context word within 80 characters.
#                 ("Play", "Karma", "Snake", "Akira")

_GENERIC_ALIASES = {
    "akira", "axiom", "bahamut", "chimera", "cicada", "cleaver", "elfin",
    "karma", "krypton", "machete", "mantis", "mirage", "play", "radium",
    "rancor", "reaper", "silence", "silicon", "snake", "spirals", "strider",
    "tick", "mofang", "moafee", "chafer", "sowbug", "thrip", "windigo",
}

_ACTOR_CONTEXT = re.compile(
    r"\b(actors?|groups?|APT\d*|ransomware|gang|crew|cluster|campaign|operation|"
    r"threat|adversar\w*|intrusion|attribut\w*|nation.state|espionage|operators?|"
    r"affiliates?|persona[es]?|linked|backed|sponsored|tracked)\b",
    re.IGNORECASE,
)


def build_actor_index() -> list[dict]:
    """Build a name/alias -> MITRE group index from the live ATT&CK corpus."""
    table = _dynamodb.Table(ATTACK_TABLE)
    entries: dict[str, dict] = {}
    kwargs: dict = {"FilterExpression": Attr("sk").eq("info")}

    while True:
        resp = table.scan(**kwargs)
        for group in resp.get("Items", []):
            gid   = group.get("group_id")
            canon = group.get("name", "")
            if not gid or not canon:
                continue
            for name in [canon] + list(group.get("aliases") or []):
                name = (name or "").strip()
                if len(name) < 3:
                    continue
                entry = entries.setdefault(name.lower(), {"label": name, "groups": {}})
                entry["groups"][gid] = canon
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    index = []
    for key, entry in entries.items():
        name = entry["label"]
        if key in _GENERIC_ALIASES:
            tier = "guarded"
        elif " " in name or any(c.isdigit() for c in name) or len(name) >= 8:
            tier = "distinctive"
        else:
            tier = "exact"
        index.append({
            "name":   name,
            "tier":   tier,
            "groups": sorted(entry["groups"].items()),
            "regex":  re.compile(
                r"(?<![\w\-])" + re.escape(name) + r"(?![\w\-])",
                re.IGNORECASE if tier == "distinctive" else 0,
            ),
        })
    logger.info("Actor index built: %d distinct names/aliases", len(index))
    return index


def extract_actors(text: str, index: list[dict]) -> list[dict]:
    """Find MITRE-known threat actors named in an article."""
    found: dict[str, dict] = {}

    for entry in index:
        for match in entry["regex"].finditer(text):
            if entry["tier"] == "guarded":
                lo = max(0, match.start() - 80)
                hi = min(len(text), match.end() + 80)
                if not _ACTOR_CONTEXT.search(text[lo:hi]):
                    continue
            for gid, canon in entry["groups"]:
                rec = found.setdefault(gid, {
                    "mitre_id": gid, "actor": canon, "matched_as": set(),
                })
                rec["matched_as"].add(entry["name"])
            break

    return sorted(
        ({"mitre_id": r["mitre_id"], "actor": r["actor"],
          "matched_as": sorted(r["matched_as"])} for r in found.values()),
        key=lambda r: r["mitre_id"],
    )


def record_sightings(actors: list[dict], source: str, title: str,
                     url: str, published: str) -> int:
    """Write per-group `sighting:` records so /v1/intel/actor can surface
    recent open-source reporting alongside the static MITRE profile."""
    if not actors:
        return 0

    table = _dynamodb.Table(ATTACK_TABLE)
    now   = datetime.now(timezone.utc).isoformat()
    slug  = hashlib.sha256(url.encode()).hexdigest()[:16]
    count = 0

    for actor in actors:
        try:
            table.put_item(Item={
                "group_id":    actor["mitre_id"],
                "sk":          f"sighting:{slug}",
                "actor":       actor["actor"],
                "matched_as":  actor["matched_as"],
                "title":       title[:200],
                "article_url": url,
                "published":   published,
                "source":      source,
                "recorded_at": now,
            })
            count += 1
        except Exception as exc:
            logger.warning("sighting write failed for %s: %s", actor["mitre_id"], exc)

    return count


def ioc_type_for(category: str) -> str:
    return {
        "domains": "DOMAIN", "ips": "IP", "sha256": "SHA256",
        "md5": "MD5", "sha1": "SHA1", "urls": "URL",
        "cves": "CVE", "onions": "ONION",
    }.get(category, "UNKNOWN")


def ioc_id(value: str, ioc_type: str) -> str:
    return hashlib.sha256(f"{ioc_type}:{value.lower()}".encode()).hexdigest()[:16]


# ── RSS parsing ────────────────────────────────────────────────────────────

def _fetch_url(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "RelayShield-Intel/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _strip_html(html: str) -> str:
    """Minimal HTML stripping — preserve text including defanged IOC patterns."""
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def parse_feed(feed_url: str) -> list[dict]:
    """Parse RSS feed and return list of articles with guid, title, link, content."""
    raw = _fetch_url(feed_url)
    root = ET.fromstring(raw)
    ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
    articles = []
    for item in root.iter("item"):
        guid    = (item.findtext("guid") or "").strip()
        title   = (item.findtext("title") or "").strip()
        link    = (item.findtext("link") or "").strip()
        pub     = (item.findtext("pubDate") or "").strip()
        desc    = (item.findtext("description") or "")
        encoded = (item.find("content:encoded", ns))
        html    = encoded.text if encoded is not None and encoded.text else desc
        articles.append({
            "guid": guid or link,
            "title": title,
            "link": link,
            "published": pub,
            # Raw HTML is kept as well as text: heading structure is what
            # separates indicator sections from prose during extraction.
            "html": html,
            "content": _strip_html(html),
        })
    return articles


# ── Seen-article tracking ──────────────────────────────────────────────────

def _is_seen(guid: str) -> bool:
    table = _dynamodb.Table(SEEN_TABLE)
    resp  = table.get_item(Key={"message_id": f"substack_{hashlib.sha256(guid.encode()).hexdigest()[:16]}"}  )
    return "Item" in resp


def _mark_seen(guid: str, title: str) -> None:
    table = _dynamodb.Table(SEEN_TABLE)
    table.put_item(Item={
        "message_id": f"substack_{hashlib.sha256(guid.encode()).hexdigest()[:16]}",
        "guid":       guid,
        "title":      title,
        "seen_at":    datetime.now(timezone.utc).isoformat(),
    })


# ── IOC ingestion ──────────────────────────────────────────────────────────

def ingest_iocs(iocs: dict, source: str, article_title: str, article_url: str,
                actors: list[dict] | None = None) -> int:
    """Write extracted IOCs to relayshield_intel_iocs. Returns count written."""
    table  = _dynamodb.Table(IOCS_TABLE)
    now    = datetime.now(timezone.utc).isoformat()
    ttl    = int(datetime(2028, 1, 1, tzinfo=timezone.utc).timestamp())
    actors = actors or []
    count  = 0

    # Attribute only when the article names exactly one group. A strategic
    # briefing naming eight actors tells us nothing about which one owns a
    # given indicator, so those stay explicitly unattributed rather than
    # being credited to whichever name happened to sort first.
    if len(actors) == 1:
        threat_actor = actors[0]["actor"]
    elif len(actors) > 1:
        threat_actor = "Multiple (see actors_mentioned)"
    else:
        threat_actor = "Unattributed (Substack bulletin)"

    actors_mentioned = [f'{a["mitre_id"]}:{a["actor"]}' for a in actors]
    mitre_group_ids  = [a["mitre_id"] for a in actors]

    with table.batch_writer() as batch:
        for category, entries in iocs.items():
            ioc_t = ioc_type_for(category)
            for entry in entries:
                value = entry["value"]
                if not value or len(value) < 4:
                    continue
                item = {
                    "ioc_id":       ioc_id(value, ioc_t),
                    "ioc_value":    value,
                    "ioc_type":     ioc_t,
                    "threat_actor": threat_actor,
                    "campaign":     article_title[:120],
                    "description":  f"Extracted from: {article_title}",
                    "confidence":   entry["confidence"],
                    "provenance":   entry["provenance"],
                    "source":       source,
                    "article_url":  article_url,
                    "seen_ts":      now,
                    "ingested_at":  now,
                    "active":       True,
                    "ttl":          ttl,
                }
                if actors_mentioned:
                    item["actors_mentioned"] = actors_mentioned
                    item["mitre_group_ids"]  = mitre_group_ids
                batch.put_item(Item=item)
                count += 1

    return count


# ── Lambda handler ─────────────────────────────────────────────────────────

def lambda_handler(event, context):
    stats = {
        "feeds_checked": 0, "articles_new": 0, "iocs_ingested": 0,
        "actors_matched": 0, "sightings_written": 0, "errors": 0,
    }

    try:
        actor_index = build_actor_index()
    except Exception as exc:
        # Actor enrichment is additive — a MITRE outage must not stop IOC
        # ingestion, but it must be visible rather than silently degrading.
        logger.error("Actor index build failed, continuing without actors: %s", exc)
        actor_index = []
        stats["errors"] += 1
    stats["actor_index_size"] = len(actor_index)

    # Backfill hook: {"reprocess": N} re-runs the N most recent articles per
    # feed regardless of seen-state. Needed whenever extraction logic changes,
    # since seen-tracking would otherwise permanently hide already-read posts
    # from an improved extractor.
    reprocess = int((event or {}).get("reprocess") or 0)
    if reprocess:
        logger.info("Reprocess mode: forcing %d most recent articles per feed", reprocess)
        stats["reprocess"] = reprocess

    for feed_cfg in SUBSTACK_FEEDS:
        feed_url = feed_cfg["url"]
        author   = feed_cfg["author"]
        stats["feeds_checked"] += 1

        try:
            articles = parse_feed(feed_url)
            logger.info("Feed %s — %d articles found", feed_url, len(articles))
        except Exception as exc:
            logger.error("Failed to fetch feed %s: %s", feed_url, exc)
            stats["errors"] += 1
            continue

        for position, article in enumerate(articles):
            guid  = article["guid"]
            title = article["title"]
            forced = position < reprocess

            if not forced and _is_seen(guid):
                logger.debug("Already processed: %s", title[:60])
                continue

            logger.info("New article: %s", title[:80])
            stats["articles_new"] += 1

            actors = extract_actors(article["content"], actor_index) if actor_index else []
            if actors:
                stats["actors_matched"] += len(actors)
                logger.info(
                    "Actors in '%s': %s", title[:50],
                    ", ".join(f'{a["actor"]} ({a["mitre_id"]})' for a in actors),
                )
                try:
                    stats["sightings_written"] += record_sightings(
                        actors, author, title, article["link"], article["published"],
                    )
                except Exception as exc:
                    logger.error("Sighting write failed for %s: %s", title[:60], exc)
                    stats["errors"] += 1

            iocs  = extract_iocs(article["html"])
            total = sum(len(v) for v in iocs.values())

            if total == 0:
                logger.info("No IOCs found in: %s", title[:60])
                _mark_seen(guid, title)
                continue

            try:
                ingested = ingest_iocs(iocs, author, title, article["link"], actors)
                stats["iocs_ingested"] += ingested
                logger.info("Ingested %d IOCs from: %s", ingested, title[:60])
                _mark_seen(guid, title)
            except Exception as exc:
                logger.error("IOC ingestion failed for %s: %s", title[:60], exc)
                stats["errors"] += 1

    logger.info("Substack ingest complete: %s", stats)
    return {"statusCode": 200, "body": json.dumps(stats)}
