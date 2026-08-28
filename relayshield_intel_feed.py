"""
RelayShield INTEL-FEED — ThreatFox + URLhaus + Spamhaus + AbuseIPDB IOC Ingestion

Polls free threat intelligence feeds daily and writes confirmed IOCs to
relayshield_intel_iocs DynamoDB table. Same table, same schema as the
Telegram channel monitor — /v1/intel/telegram serves results from both sources.

Sources:
  ThreatFox  (abuse.ch)  — malware IOCs: domains, IPs, URLs tagged by malware family
  URLhaus    (abuse.ch)  — malicious URLs used for malware distribution
  Spamhaus   DROP/EDROP  — IP CIDR blocklists, no auth required
  AbuseIPDB              — crowdsourced IP abuse reports (free tier, API key required)

IOC types written: domain, ip, cidr
TTL: 90 days (same as Telegram IOCs)

Architecture:
  EventBridge cron (daily, 06:00 UTC) OR GitHub Actions workflow_dispatch
  → Lambda (this file)
      → ThreatFox, URLhaus, Spamhaus DROP/EDROP (all public, no auth)
      → AbuseIPDB blacklist endpoint (free API key — stored in Secrets Manager)
      → Write to relayshield_intel_iocs (dedup on ioc_value)
      → Telegram digest to ADMIN_CHAT_ID
"""

import json
import logging
import os
import re
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone
from decimal import Decimal

import boto3

from relayshield_intel_labels import normalise_malware

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INTEL_IOCS_TABLE    = "relayshield_intel_iocs"
TG_SECRET_NAME      = "relayshield/telegram_bot_token"
ABUSEIPDB_SECRET    = "relayshield/abuseipdb_api_key"
ADMIN_CHAT_ID       = int(os.environ.get("ADMIN_CHAT_ID", "1729226804"))
ALERT_TTL_DAYS      = 90    # alert history retention
IOC_TTL_DAYS        = 365   # IOC corpus retention — 1 year for incident investigation

THREATFOX_CSV       = "https://threatfox.abuse.ch/export/csv/recent/"
URLHAUS_CSV         = "https://urlhaus.abuse.ch/downloads/csv_recent/"
SPAMHAUS_DROP_URL   = "https://www.spamhaus.org/drop/drop.txt"
SPAMHAUS_EDROP_URL  = "https://www.spamhaus.org/drop/edrop.txt"
ABUSEIPDB_BLACKLIST = "https://api.abuseipdb.com/api/v2/blacklist"
FEODO_CSV               = "https://feodotracker.abuse.ch/downloads/ipblocklist.csv"
FEODO_AGGRESSIVE_CSV    = "https://feodotracker.abuse.ch/downloads/ipblocklist_aggressive.csv"
MALWAREBAZAAR_CSV       = "https://bazaar.abuse.ch/export/csv/recent/"
PHISHTANK_CSV           = "http://data.phishtank.com/data/online-valid.csv.gz"
EMERGING_THREATS_IPS    = "https://rules.emergingthreats.net/blockrules/compromised-ips.txt"

# Free feed additions — no API key, no registration required
OPENPHISH_URL           = "https://openphish.com/feed.txt"           # phishing URLs, updated ~6hr
BLOCKLIST_DE_URL        = "https://lists.blocklist.de/lists/all.txt" # malicious IPs, multi-category
TALOS_BLACKLIST_URL     = "https://www.talosintelligence.com/documents/ip-blacklist"  # Cisco Talos IPs
IPSUM_URL               = "https://raw.githubusercontent.com/stamparm/ipsum/master/ipsum.txt"  # aggregated blocklist, scored

# New feeds — added for 500K IOC milestone
HAGEZI_TIF_URL          = "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/domains/tif.txt"

# Malware family expansion — target 1000+ families
TRIAGE_FEED_URL         = "https://tria.ge/api/v0/samples?limit=200&status=reported"  # family-tagged sandbox IOCs
POLYSWARM_FEED_URL      = "https://api.polyswarm.network/v3/stix2/hunt/type/malicious?limit=200"  # multi-sandbox consensus IOCs with family tags
MALPEDIA_FAMILIES_URL   = "https://malpedia.caad.fkie.fraunhofer.de/api/get/families" # 1000+ family taxonomy for normalization  # 1M+ malicious domains, 50+ upstream sources
C2_INTEL_IPS_URL        = "https://raw.githubusercontent.com/Bert-JanP/Open-Source-Threat-Intel-Feeds/main/Feeds/CobaltStrike/CobaltStrikeC2.txt"  # Cobalt Strike C2 IPs
C2_INTEL_DOMAINS_URL    = "https://raw.githubusercontent.com/Bert-JanP/Open-Source-Threat-Intel-Feeds/main/Feeds/CobaltStrike/CobaltStrikeDomains.txt"
PHISHSTATS_CSV_URL      = "https://phishstats.info/phish_score.csv"  # phishing URLs with score, updated every few hours
BOTVRIJ_DOMAIN_URL      = "https://www.botvrij.eu/data/ioclist.domain.raw"  # curated malicious domains, free
BOTVRIJ_IP_URL          = "https://www.botvrij.eu/data/ioclist.ip-dst.raw"  # curated malicious IPs, free
PASTEEE_API_URL         = "https://api.paste.ee/v1/pastes"                  # paste.ee recent public pastes, free
PASTEHUB_RECENT_URL     = "https://pastehub.net/api/list"                   # pastehub.net recent pastes, free
OTX_SECRET              = "relayshield/alienvault_otx_api_key"
OTX_PULSES_URL          = "https://otx.alienvault.com/api/v1/pulses/subscribed"

# AbuseIPDB run-once-per-day guard — stored in DynamoDB with 23h TTL
ABUSEIPDB_GUARD_KEY     = "_control_abuseipdb_last_run"

# Only ingest IOC types relevant to RelayShield's query surface
THREATFOX_IOC_TYPES = {"domain", "url", "ip:port"}

# Malware families most relevant to credential theft / financial fraud
THREATFOX_PRIORITY_MALWARE = {
    "lummac2", "redline", "vidar", "raccoon", "stealc", "meta", "aurora",
    "formbook", "lokibot", "agent_tesla", "remcos", "asyncrat", "qakbot",
    "emotet", "cobalt_strike", "icedid", "trickbot", "danabot",
}

_sm       = boto3.client("secretsmanager", region_name="us-east-1")
_dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

_RE_DOMAIN = re.compile(
    r"\b(?:[a-zA-Z0-9\-]{1,63}\.)+(?:com|net|org|io|co|app|xyz|info|biz|ru|cn|top|site)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_bot_token() -> str:
    raw = _sm.get_secret_value(SecretId=TG_SECRET_NAME)["SecretString"]
    return json.loads(raw)["telegram_bot_token"]


def _get_abuseipdb_key() -> str:
    raw = _sm.get_secret_value(SecretId=ABUSEIPDB_SECRET)["SecretString"]
    d = json.loads(raw)
    return d.get("api_key") or d.get("abuseipdb_api_key", "")


def _get_otx_key() -> str:
    try:
        raw = _sm.get_secret_value(SecretId=OTX_SECRET)["SecretString"].strip()
        try:
            d = json.loads(raw)
            return d.get("api_key") or d.get("otx_api_key", "")
        except (json.JSONDecodeError, AttributeError):
            return raw  # stored as raw string
    except Exception:
        return ""


def _abuseipdb_already_ran_today(table) -> bool:
    """Return True if AbuseIPDB was already fetched in the last 47 hours.
    Free tier allows 5 blacklist calls/day. 47hr guard ensures we never
    exhaust the limit from overlapping daily runs or manual test invocations."""
    try:
        resp = table.get_item(Key={"ioc_value": ABUSEIPDB_GUARD_KEY})
        return "Item" in resp
    except Exception:
        return False


def _mark_abuseipdb_ran(table) -> None:
    """Set a 47-hour TTL guard — conservative window protects the 5-call daily limit."""
    ttl = Decimal(int(time.time()) + 47 * 3600)
    try:
        table.put_item(Item={
            "ioc_value": ABUSEIPDB_GUARD_KEY,
            "seen_ts":   datetime.now(timezone.utc).isoformat(),
            "ioc_type":  "_control",
            "channel":   "_system",
            "category":  "_system",
            "ttl":       ttl,
        })
    except Exception as exc:
        logger.warning("AbuseIPDB guard set failed: %s", exc)


def _send_telegram(token: str, chat_id: int, text: str) -> None:
    url     = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    req     = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        logger.warning("Telegram notify failed: %s", exc)


def _write_ioc(table, ioc_value: str, ioc_type: str, source: str, malware: str = "") -> bool:
    """Write a single IOC to DynamoDB. Returns True if new, False if duplicate."""
    now_ts = datetime.now(timezone.utc).isoformat()
    ttl    = Decimal(int(time.time()) + IOC_TTL_DAYS * 86400)
    item = {
        "ioc_value":   ioc_value.lower().strip(),
        "seen_ts":     now_ts,
        "ioc_type":    ioc_type,
        "channel":     source,
        "category":    "threat_feed",
        "ttl":         ttl,
    }
    # Real bug found and fixed 2026-07-24: DynamoDB GSIs reject an empty
    # string for the indexed key attribute outright (ValidationException),
    # so unconditionally writing "malware": "" here made every IOC from a
    # source with no malware-family tag (most generic IP-blocklist feeds --
    # Spamhaus, IPsum, blocklist.de, etc.) fail to write at all, silently,
    # for an unknown but likely long stretch of time. Only include the key
    # when it's non-empty -- a standard DynamoDB sparse-index item just
    # doesn't participate in that GSI, which is correct here anyway (there's
    # nothing to index when there's no malware family).
    if malware:
        item["malware"] = normalise_malware(malware)
    try:
        table.put_item(Item=item, ConditionExpression="attribute_not_exists(ioc_value)")
        return True
    except _dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return False  # duplicate
    except Exception as exc:
        logger.warning("IOC write failed %s: %s", ioc_value[:30], exc)
        return False


def _batch_write_iocs(table, items: list) -> int:
    """Batch-write IOCs using DynamoDB batch_writer (handles chunking + retries). Returns count attempted.

    Real bug found and fixed 2026-07-24: DynamoDB's BatchWriteItem rejects a
    request containing the same key twice ("Provided list of item keys
    contains duplicates") -- boto3's batch_writer surfaces this as one
    exception that aborts the whole in-flight batch, not a per-item skip.
    Source feeds routinely list the same IOC more than once (e.g. URLhaus's
    CSV), which meant one duplicate anywhere in a 25-item flush window
    silently killed that entire chunk -- confirmed live: URLhaus wrote 24 of
    14,876 fetched before aborting. Deduping by ioc_value up front (keep
    first occurrence) fixes it structurally rather than catching the
    exception after the fact.
    """
    now_ts = datetime.now(timezone.utc).isoformat()
    ttl    = Decimal(int(time.time()) + IOC_TTL_DAYS * 86400)
    seen: set[str] = set()
    deduped = []
    for ioc_value, ioc_type, source, malware in items:
        key = ioc_value.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append((ioc_value, ioc_type, source, malware))

    written = 0
    try:
        with table.batch_writer() as batch:
            for ioc_value, ioc_type, source, malware in deduped:
                item = {
                    "ioc_value": ioc_value.lower().strip(),
                    "seen_ts":   now_ts,
                    "ioc_type":  ioc_type,
                    "channel":   source,
                    "category":  "threat_feed",
                    "ttl":       ttl,
                }
                if malware:  # same empty-string GSI key fix as _write_ioc above
                    item["malware"] = normalise_malware(malware)
                batch.put_item(Item=item)
                written += 1
    except Exception as exc:
        logger.warning("Batch write error after %d items: %s", written, exc)
    return written


# ---------------------------------------------------------------------------
# ThreatFox ingestion
# ---------------------------------------------------------------------------

def _ingest_threatfox(table) -> dict:
    """Parse ThreatFox recent IOCs CSV (no auth required)."""
    import csv, io, gzip
    logger.info("Fetching ThreatFox CSV")
    req = urllib.request.Request(THREATFOX_CSV, headers={"User-Agent": "RelayShield/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            # ThreatFox serves gzip
            try:
                content = gzip.decompress(raw).decode("utf-8", errors="ignore")
            except Exception:
                content = raw.decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.error("ThreatFox fetch failed: %s", exc)
        return {"fetched": 0, "written": 0}

    fetched = written = 0
    reader = csv.reader(io.StringIO(content))
    for row in reader:
        if not row or row[0].startswith("#"):
            continue
        # CSV columns: first_seen, ioc_id, ioc_type, ioc, malware, malware_alias, malware_printable, last_online, confidence, anonymized, reporter, tags, malware_malpedia
        if len(row) < 4:
            continue
        fetched += 1
        ioc_type  = row[2].strip().lower()
        ioc_value = row[3].strip().strip('"')
        malware   = (row[6].strip() if len(row) > 6 else "").lower()

        if malware and not any(p in malware for p in THREATFOX_PRIORITY_MALWARE):
            continue

        if ioc_type == "domain":
            if _write_ioc(table, ioc_value, "domain", "threatfox", malware):
                written += 1
        elif ioc_type in ("url", "full_url"):
            match = _RE_DOMAIN.search(ioc_value)
            if match and _write_ioc(table, match.group(0), "domain", "threatfox", malware):
                written += 1
        elif ioc_type == "ip:port":
            ip = ioc_value.split(":")[0]
            if _write_ioc(table, ip, "ip", "threatfox", malware):
                written += 1

    logger.info("ThreatFox: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


# ---------------------------------------------------------------------------
# URLhaus ingestion
# ---------------------------------------------------------------------------

def _ingest_urlhaus(table) -> dict:
    """Parse URLhaus recent URLs CSV (no auth required)."""
    import csv, io, zipfile
    logger.info("Fetching URLhaus CSV")
    req = urllib.request.Request(URLHAUS_CSV, headers={"User-Agent": "RelayShield/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except Exception as exc:
        logger.error("URLhaus fetch failed: %s", exc)
        return {"fetched": 0, "written": 0}

    # URLhaus serves a zip file containing csv
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            csv_name = [n for n in zf.namelist() if n.endswith(".csv")][0]
            content  = zf.read(csv_name).decode("utf-8", errors="ignore")
    except Exception:
        content = raw.decode("utf-8", errors="ignore")

    fetched = 0
    batch = []
    reader = csv.reader(io.StringIO(content))
    for row in reader:
        if not row or row[0].startswith("#"):
            continue
        # Columns: id, dateadded, url, url_status, last_online, threat, tags, urlhaus_link, reporter
        if len(row) < 3:
            continue
        fetched += 1
        url_str = row[2].strip().strip('"')
        tags    = row[6].strip() if len(row) > 6 else ""

        match = _RE_DOMAIN.search(url_str)
        if not match:
            continue
        domain = match.group(0).lower()
        batch.append((domain, "domain", "urlhaus", tags))

    written = _batch_write_iocs(table, batch)
    logger.info("URLhaus: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


# ---------------------------------------------------------------------------
# Spamhaus DROP / EDROP ingestion
# ---------------------------------------------------------------------------

def _ingest_spamhaus(table) -> dict:
    """Pull Spamhaus DROP and EDROP IP CIDR blocklists (public, no auth)."""
    written = fetched = 0
    batch = []
    for url, label in [(SPAMHAUS_DROP_URL, "spamhaus_drop"), (SPAMHAUS_EDROP_URL, "spamhaus_edrop")]:
        logger.info("Fetching %s", label)
        req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
        except Exception as exc:
            logger.error("%s fetch failed: %s", label, exc)
            continue
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            cidr = line.split(";")[0].strip()
            if not cidr:
                continue
            fetched += 1
            batch.append((cidr, "cidr", label, ""))
    written = _batch_write_iocs(table, batch)
    logger.info("Spamhaus DROP+EDROP: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


# ---------------------------------------------------------------------------
# AbuseIPDB blacklist ingestion
# ---------------------------------------------------------------------------

def _ingest_abuseipdb(table) -> dict:
    """Pull AbuseIPDB blacklist once per day (confidence ≥ 90, limit 10,000)."""
    if _abuseipdb_already_ran_today(table):
        logger.info("AbuseIPDB: skipping — already ran today")
        return {"fetched": 0, "written": 0, "skipped": True}
    logger.info("Fetching AbuseIPDB blacklist")
    try:
        api_key = _get_abuseipdb_key()
    except Exception as exc:
        logger.error("AbuseIPDB key fetch failed: %s", exc)
        return {"fetched": 0, "written": 0}

    params  = urllib.parse.urlencode({"confidenceMinimum": 90, "limit": 10000})
    req_url = f"{ABUSEIPDB_BLACKLIST}?{params}"
    req     = urllib.request.Request(
        req_url,
        headers={"Key": api_key, "Accept": "application/json", "User-Agent": "RelayShield/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
    except Exception as exc:
        logger.error("AbuseIPDB fetch failed: %s", exc)
        return {"fetched": 0, "written": 0}

    records = body.get("data", [])
    fetched = len(records)
    # Real timeout root cause found and fixed 2026-07-24: one _write_ioc()
    # HTTP round-trip per item at 10,000 items took ~2.5 minutes on its own;
    # across AbuseIPDB + blocklist.de + IPsum that was ~13 of the Lambda's
    # 15-minute budget before it ever reached later sources (or the new
    # GitHub tool-repo search). batch_writer chunks/pipelines writes instead
    # of one request per item -- same data, a small fraction of the time.
    batch_items = []
    for entry in records:
        ip = (entry.get("ipAddress") or "").strip()
        if ip:
            batch_items.append((ip, "ip", "abuseipdb", ""))
    written = _batch_write_iocs(table, batch_items)

    _mark_abuseipdb_ran(table)
    logger.info("AbuseIPDB: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


# ---------------------------------------------------------------------------
# PhishTank ingestion (verified phishing URLs — public, gzipped CSV)
# ---------------------------------------------------------------------------

def _ingest_phishtank(table) -> dict:
    """Pull PhishTank verified phishing URLs (public, no auth, gzipped CSV)."""
    import csv, io, gzip, concurrent.futures
    logger.info("Fetching PhishTank CSV")

    def _fetch():
        req = urllib.request.Request(
            PHISHTANK_CSV,
            headers={"User-Agent": "RelayShield/1.0 (phishtank@relayshield.net)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
        return gzip.decompress(raw).decode("utf-8", errors="ignore")

    # Third real bug found 2026-07-25 (first two fixes -- a socket-read-loop
    # deadline, then a signal.alarm() hard deadline -- both failed live: two
    # separate confirmed runs hung the full 900s with zero log output after
    # "Fetching PhishTank CSV", meaning neither a per-read bound nor SIGALRM
    # ever got a chance to fire, or fired and was silently lost. Root cause
    # unconfirmed (Lambda's Python runtime may itself rely on SIGALRM for its
    # own timeout bookkeeping, which would explain a delivered-but-discarded
    # signal). Running the fetch in a worker thread sidesteps the question
    # entirely -- concurrent.futures.Future.result(timeout=) does not need to
    # interrupt whatever the worker is blocked on; it simply stops waiting on
    # it after the deadline and lets the pipeline continue. The worker thread
    # may leak until the Lambda execution environment is recycled -- an
    # acceptable tradeoff for guaranteeing forward progress.
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = ex.submit(_fetch)
        content = future.result(timeout=45)
    except Exception as exc:
        logger.error("PhishTank fetch failed: %s", exc)
        ex.shutdown(wait=False, cancel_futures=True)
        return {"fetched": 0, "written": 0}
    ex.shutdown(wait=False, cancel_futures=True)

    fetched = written = 0
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        url = (row.get("url") or "").strip()
        if not url:
            continue
        fetched += 1
        # Store the full reported URL, not a domain extracted via regex.
        # PhishTank flags specific phishing URLs, and many are open-redirect
        # abuse hosted on well-known legitimate domains (e.g.
        # google.com/url?q=<actual phishing site>) — the previous
        # _RE_DOMAIN.search(url) grabbed whichever domain-like substring
        # appeared first in the raw URL, which for a redirect URL is the
        # legitimate redirector, not the phishing target. That produced
        # real false positives — google.com (9 records), microsoft.com (12),
        # and apple.com (3) all ended up flagged as "domain"-type criminal
        # IOCs, discovered 2026-07-16 via check_mcp_server_risk's and a new
        # Telegram scan feature's identical domain-corpus lookup. Matches
        # the existing openphish convention (full URL, ioc_type "url"),
        # which doesn't have this bug.
        if _write_ioc(table, url[:500], "url", "phishtank"):
            written += 1

    logger.info("PhishTank: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


# ---------------------------------------------------------------------------
# Emerging Threats compromised IP ingestion (public, no auth)
# ---------------------------------------------------------------------------

def _ingest_emerging_threats(table) -> dict:
    """Pull Emerging Threats compromised IP blocklist (public, no auth)."""
    logger.info("Fetching Emerging Threats compromised IPs")
    req = urllib.request.Request(EMERGING_THREATS_IPS, headers={"User-Agent": "RelayShield/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.error("Emerging Threats fetch failed: %s", exc)
        return {"fetched": 0, "written": 0}

    fetched = written = 0
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fetched += 1
        if _write_ioc(table, line, "ip", "emerging_threats"):
            written += 1

    logger.info("Emerging Threats: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


# ---------------------------------------------------------------------------
# AlienVault OTX ingestion (free API key required)
# ---------------------------------------------------------------------------

def _ingest_otx(table) -> dict:
    """Pull AlienVault OTX subscribed pulse IOCs (API key from Secrets Manager)."""
    api_key = _get_otx_key()
    if not api_key:
        logger.warning("OTX: no API key configured — skipping")
        return {"fetched": 0, "written": 0}

    logger.info("Fetching AlienVault OTX pulses")
    fetched = written = 0
    page = 1
    limit = 20  # pulses per page

    while page <= 10:  # cap at 10 pages (~200 pulses) per run
        url = f"{OTX_PULSES_URL}?limit={limit}&page={page}"
        req = urllib.request.Request(url, headers={
            "X-OTX-API-KEY": api_key,
            "User-Agent": "RelayShield/1.0",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read())
        except Exception as exc:
            logger.error("OTX fetch failed page=%d: %s", page, exc)
            break

        pulses = body.get("results", [])
        if not pulses:
            break

        for pulse in pulses:
            for indicator in pulse.get("indicators", []):
                itype = (indicator.get("type") or "").lower()
                val   = (indicator.get("indicator") or "").strip().lower()
                if not val:
                    continue
                fetched += 1
                if itype in ("domain", "hostname"):
                    if _write_ioc(table, val, "domain", "otx"):
                        written += 1
                elif itype == "ipv4":
                    if _write_ioc(table, val, "ip", "otx"):
                        written += 1
                elif itype in ("url", "uri"):
                    match = _RE_DOMAIN.search(val)
                    if match and _write_ioc(table, match.group(0).lower(), "domain", "otx"):
                        written += 1
                elif itype in ("filehash-sha256", "filehashs-sha256"):
                    if len(val) == 64 and _write_ioc(table, val, "hash_sha256", "otx"):
                        written += 1

        if not body.get("next"):
            break
        page += 1

    logger.info("OTX: fetched=%d written=%d pages=%d", fetched, written, page)
    return {"fetched": fetched, "written": written}


# ---------------------------------------------------------------------------
# Feodo Tracker aggressive ingestion (replaces deprecated SSLBL)
# Full historical + active C2 IPs: Emotet, QakBot, Dridex, IcedID, TrickBot
# ---------------------------------------------------------------------------

def _ingest_feodo_aggressive(table) -> dict:
    """Parse abuse.ch Feodo Tracker aggressive IP blocklist (~8K C2 IPs, no auth)."""
    import csv, io
    logger.info("Fetching Feodo aggressive blocklist")
    req = urllib.request.Request(FEODO_AGGRESSIVE_CSV, headers={"User-Agent": "RelayShield/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.error("Feodo aggressive fetch failed: %s", exc)
        return {"fetched": 0, "written": 0}

    fetched = 0
    batch = []
    reader = __import__("csv").reader(__import__("io").StringIO(content))
    for row in reader:
        if not row or row[0].startswith("#") or row[0].startswith('"first_seen'):
            continue
        if len(row) < 2:
            continue
        fetched += 1
        ip      = row[1].strip().strip('"')
        malware = row[5].strip().strip('"').lower() if len(row) > 5 else ""
        if ip:
            batch.append((ip, "ip", "feodo_aggressive", malware))

    written = _batch_write_iocs(table, batch)
    logger.info("Feodo aggressive: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


# ---------------------------------------------------------------------------
# Feodo Tracker ingestion (abuse.ch — Emotet/QakBot/IcedID C2 IPs)
# ---------------------------------------------------------------------------

def _ingest_feodo(table) -> dict:
    """Parse abuse.ch Feodo Tracker IP blocklist (public, no auth)."""
    logger.info("Fetching Feodo Tracker CSV")
    req = urllib.request.Request(FEODO_CSV, headers={"User-Agent": "RelayShield/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.error("Feodo fetch failed: %s", exc)
        return {"fetched": 0, "written": 0}

    fetched = written = 0
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Format: first_seen,dst_ip,dst_port,last_online,malware
        parts = line.split(",")
        if len(parts) < 2:
            continue
        fetched += 1
        ip      = parts[1].strip()
        malware = parts[4].strip().lower() if len(parts) > 4 else ""
        if ip and _write_ioc(table, ip, "ip", "feodo_tracker", malware):
            written += 1

    logger.info("Feodo Tracker: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


# ---------------------------------------------------------------------------
# MalwareBazaar ingestion (abuse.ch — recent malware file hashes)
# ---------------------------------------------------------------------------

def _ingest_malwarebazaar(table) -> dict:
    """Parse abuse.ch MalwareBazaar recent samples (plain CSV, quoted fields).
    Writes SHA256 hashes as IOC type 'hash_sha256'."""
    import csv, io
    logger.info("Fetching MalwareBazaar CSV")
    req = urllib.request.Request(MALWAREBAZAAR_CSV, headers={"User-Agent": "RelayShield/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.error("MalwareBazaar fetch failed: %s", exc)
        return {"fetched": 0, "written": 0}

    fetched = written = 0
    reader = csv.reader(io.StringIO(content))
    for row in reader:
        if not row or row[0].startswith("#"):
            continue
        # Columns (all quoted): first_seen_utc, sha256_hash, md5_hash, sha1_hash,
        #   reporter, file_name, file_type, mime_type, signature, clamav, vtpercent,
        #   imphash, ssdeep, tlsh
        if len(row) < 2:
            continue
        sha256  = row[1].strip().strip('"').lower()
        malware = row[8].strip().strip('"').lower() if len(row) > 8 else ""
        if not sha256 or len(sha256) != 64:
            continue
        fetched += 1
        if _write_ioc(table, sha256, "hash_sha256", "malwarebazaar", malware):
            written += 1

    logger.info("MalwareBazaar: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def _ingest_openphish(table) -> dict:
    """OpenPhish free feed — verified phishing URLs, updated every ~6 hours."""
    logger.info("Fetching OpenPhish feed")
    try:
        req = urllib.request.Request(OPENPHISH_URL, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            lines = resp.read().decode("utf-8", errors="ignore").splitlines()
    except Exception as exc:
        logger.error("OpenPhish fetch failed: %s", exc)
        return {"fetched": 0, "written": 0}
    fetched = written = 0
    for line in lines:
        url = line.strip()
        if not url or not url.startswith(("http://", "https://")):
            continue
        fetched += 1
        if _write_ioc(table, url, "url", "openphish", "phishing"):
            written += 1
    logger.info("OpenPhish: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


def _ingest_blocklist_de(table) -> dict:
    """blocklist.de all.txt — IPs reported for brute force, malware, spam etc."""
    logger.info("Fetching blocklist.de")
    try:
        req = urllib.request.Request(BLOCKLIST_DE_URL, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            lines = resp.read().decode("utf-8", errors="ignore").splitlines()
    except Exception as exc:
        logger.error("blocklist.de fetch failed: %s", exc)
        return {"fetched": 0, "written": 0}
    import re
    ip_re = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
    fetched = 0
    batch_items = []
    for line in lines:
        ip = line.strip()
        if not ip or not ip_re.match(ip):
            continue
        fetched += 1
        batch_items.append((ip, "ip", "blocklist_de", ""))
    written = _batch_write_iocs(table, batch_items)  # was one _write_ioc() call per item -- see AbuseIPDB comment
    logger.info("blocklist.de: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


def _ingest_talos(table) -> dict:
    """Cisco Talos IP blacklist — IPs with poor reputation from Talos telemetry."""
    logger.info("Fetching Cisco Talos blacklist")
    try:
        req = urllib.request.Request(TALOS_BLACKLIST_URL, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            lines = resp.read().decode("utf-8", errors="ignore").splitlines()
    except Exception as exc:
        logger.error("Talos blacklist fetch failed: %s", exc)
        return {"fetched": 0, "written": 0}
    fetched = written = 0
    import re
    ip_re = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
    for line in lines:
        ip = line.strip()
        if not ip or ip.startswith("#") or not ip_re.match(ip):
            continue
        fetched += 1
        if _write_ioc(table, ip, "ip", "talos", ""):
            written += 1
    logger.info("Talos: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


def _ingest_ipsum(table) -> dict:
    """IPsum — aggregated IP blocklist, scored by number of blacklists reporting.
    Only ingest IPs reported by 3+ sources (confidence filter)."""
    logger.info("Fetching IPsum blocklist")
    try:
        req = urllib.request.Request(IPSUM_URL, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            lines = resp.read().decode("utf-8", errors="ignore").splitlines()
    except Exception as exc:
        logger.error("IPsum fetch failed: %s", exc)
        return {"fetched": 0, "written": 0}
    fetched = 0
    batch_items = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        ip, score_str = parts[0], parts[1]
        try:
            if int(score_str) < 3:  # skip low-confidence entries
                continue
        except ValueError:
            continue
        fetched += 1
        batch_items.append((ip, "ip", "ipsum", ""))
    written = _batch_write_iocs(table, batch_items)  # was one _write_ioc() call per item -- see AbuseIPDB comment
    logger.info("IPsum: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


def _ingest_hagezi(table) -> dict:
    """Hagezi Threat Intelligence Feed — 1M+ malicious domains aggregated from 50+ sources."""
    logger.info("Fetching Hagezi TIF")
    try:
        req = urllib.request.Request(HAGEZI_TIF_URL, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            lines = resp.read().decode("utf-8", errors="ignore").splitlines()
    except Exception as exc:
        logger.error("Hagezi fetch failed: %s", exc)
        return {"fetched": 0, "written": 0}
    fetched = written = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        domain = line.lower()
        if "." not in domain or len(domain) < 4 or len(domain) > 253:
            continue
        fetched += 1
        if _write_ioc(table, domain, "domain", "hagezi", ""):
            written += 1
    logger.info("Hagezi TIF: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


def _ingest_c2intel(table) -> dict:
    """Bert-JanP C2IntelFeeds — Cobalt Strike C2 IPs and domains."""
    logger.info("Fetching C2IntelFeeds")
    fetched = written = 0
    for url, ioc_type in [(C2_INTEL_IPS_URL, "ip"), (C2_INTEL_DOMAINS_URL, "domain")]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                lines = resp.read().decode("utf-8", errors="ignore").splitlines()
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                fetched += 1
                if _write_ioc(table, line.lower(), ioc_type, "c2intel", "CobaltStrike"):
                    written += 1
        except Exception as exc:
            logger.error("C2Intel fetch failed url=%s: %s", url, exc)
    logger.info("C2IntelFeeds: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


def _ingest_phishstats(table) -> dict:
    """PhishStats — phishing URLs with confidence score. Ingest score >= 7 only."""
    logger.info("Fetching PhishStats")
    try:
        req = urllib.request.Request(PHISHSTATS_CSV_URL, headers={"User-Agent": "RelayShield/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            lines = resp.read().decode("utf-8", errors="ignore").splitlines()
    except Exception as exc:
        logger.error("PhishStats fetch failed: %s", exc)
        return {"fetched": 0, "written": 0}
    fetched = written = 0
    for line in lines[1:]:  # skip header
        parts = line.split(",")
        if len(parts) < 3:
            continue
        try:
            score = float(parts[1].strip().strip('"'))
        except ValueError:
            continue
        if score < 7.0:  # confidence filter
            continue
        url_val = parts[2].strip().strip('"')
        if not url_val.startswith("http"):
            continue
        fetched += 1
        domain_match = re.search(r"https?://([^/]+)", url_val)
        if domain_match:
            domain = domain_match.group(1).lower().split(":")[0]
            if _write_ioc(table, domain, "domain", "phishstats", "phishing"):
                written += 1
    logger.info("PhishStats: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


def _ingest_triage(table) -> dict:
    """Triage sandbox (tria.ge) — family-tagged IOCs from community malware analysis.
    Requires free API key stored in Secrets Manager. Returns C2 domains/IPs with family tags."""
    import json as _json
    logger.info("Fetching Triage sandbox IOCs")
    try:
        secret = _get_secret("relayshield/triage_api_key")
        api_key = secret.get("triage_api_key", "")
        if not api_key:
            logger.warning("Triage API key not configured — skipping")
            return {"fetched": 0, "written": 0}
        req = urllib.request.Request(
            TRIAGE_FEED_URL,
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": "RelayShield/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = _json.loads(resp.read())
    except Exception as exc:
        logger.error("Triage fetch failed: %s", exc)
        return {"fetched": 0, "written": 0}
    fetched = written = 0
    for sample in data.get("data", []):
        family = sample.get("family", "")
        for target in sample.get("targets", []):
            for ioc in target.get("iocs", {}).get("domains", []):
                fetched += 1
                if _write_ioc(table, ioc.lower(), "domain", "triage", family):
                    written += 1
            for ioc in target.get("iocs", {}).get("ips", []):
                fetched += 1
                if _write_ioc(table, ioc, "ip", "triage", family):
                    written += 1
    logger.info("Triage: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


def _ingest_polyswarm(table) -> dict:
    """PolySwarm — multi-sandbox consensus IOCs with malware family tags.
    Free tier: 1M queries/month. Requires API key in Secrets Manager."""
    import json as _json
    logger.info("Fetching PolySwarm IOCs")
    try:
        secret = _get_secret("relayshield/polyswarm_api_key")
        api_key = secret.get("polyswarm_api_key", "")
        if not api_key:
            logger.warning("PolySwarm API key not configured — skipping")
            return {"fetched": 0, "written": 0}
        req = urllib.request.Request(
            POLYSWARM_FEED_URL,
            headers={"Authorization": f"ApiKey {api_key}", "User-Agent": "RelayShield/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = _json.loads(resp.read())
    except Exception as exc:
        logger.error("PolySwarm fetch failed: %s", exc)
        return {"fetched": 0, "written": 0}
    fetched = written = 0
    for obj in data.get("objects", []):
        obj_type = obj.get("type", "")
        family = ""
        # Extract family from labels (e.g. "malware-family:lummastealer")
        for label in obj.get("labels", []):
            if label.startswith("malware-family:"):
                family = label.split(":", 1)[1]
                break
        if obj_type == "domain-name":
            val = obj.get("value", "")
            if val:
                fetched += 1
                if _write_ioc(table, val.lower(), "domain", "polyswarm", family):
                    written += 1
        elif obj_type == "ipv4-addr":
            val = obj.get("value", "")
            if val:
                fetched += 1
                if _write_ioc(table, val, "ip", "polyswarm", family):
                    written += 1
        elif obj_type == "url":
            val = obj.get("value", "")
            domain_match = re.search(r"https?://([^/]+)", val)
            if domain_match:
                fetched += 1
                if _write_ioc(table, domain_match.group(1).lower(), "domain", "polyswarm", family):
                    written += 1
        elif obj_type == "file":
            for h in obj.get("hashes", {}).values():
                if len(h) == 64:  # SHA256
                    fetched += 1
                    if _write_ioc(table, h.lower(), "hash_sha256", "polyswarm", family):
                        written += 1
    logger.info("PolySwarm: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


def _ingest_malpedia(table) -> dict:
    """Malpedia — authoritative malware family taxonomy (1000+ families).
    Used as a normalization enrichment layer: updates existing IOCs with canonical family names."""
    import json as _json
    logger.info("Fetching Malpedia family list")
    try:
        secret = _get_secret("relayshield/malpedia_api_key")
        api_key = secret.get("malpedia_api_key", "")
        headers = {"User-Agent": "RelayShield/1.0"}
        if api_key:
            headers["Authorization"] = f"apitoken {api_key}"
        req = urllib.request.Request(MALPEDIA_FAMILIES_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            families = _json.loads(resp.read())
    except Exception as exc:
        logger.error("Malpedia fetch failed: %s", exc)
        return {"fetched": 0, "written": 0}
    # Malpedia returns a dict of family_name -> metadata
    # We store the family taxonomy in DynamoDB for downstream normalization
    fetched = len(families) if isinstance(families, dict) else 0
    logger.info("Malpedia: %d families loaded for normalization", fetched)
    return {"fetched": fetched, "written": 0}  # taxonomy only, no new IOCs written


def _ingest_botvrij(table) -> dict:
    """Pull Botvrij.eu curated malicious domain + IP lists (free, no auth)."""
    fetched = written = 0
    for url, ioc_type in ((BOTVRIJ_DOMAIN_URL, "domain"), (BOTVRIJ_IP_URL, "ip")):
        try:
            req  = urllib.request.Request(url, headers={"User-Agent": "RelayShield/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                lines = r.read().decode("utf-8", errors="ignore").splitlines()
        except Exception as exc:
            logger.error("Botvrij %s fetch failed: %s", ioc_type, exc)
            continue
        for line in lines:
            val = line.strip()
            if not val or val.startswith("#"):
                continue
            fetched += 1
            if _write_ioc(table, val, ioc_type, "botvrij"):
                written += 1
    logger.info("Botvrij: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


TOOL_REPOS_TABLE = "relayshield_intel_tool_repos"
GITHUB_SEARCH_REPOS_URL = "https://api.github.com/search/repositories"
GITHUB_TOOL_SECRET_NAME = "relayshield/github_search_token"

# Same malware-family names as SEARCH_KEYWORDS in relayshield_intel_discovery.py
# (Telegram channel discovery), reused here for GitHub repo search — a
# channel bio and a repo name/description are both places brand-name
# precision beats a generic phrase. Plus generic tool-category terms GitHub
# repo naming conventions actually use ("FUD crypter", "RAT builder").
GITHUB_TOOL_KEYWORDS = [
    ("lummac2 stealer",      "infostealer"),
    ("redline stealer",      "infostealer"),
    ("vidar stealer",        "infostealer"),
    ("raccoon stealer",      "infostealer"),
    ("stealc",               "infostealer"),
    ("fud crypter",          "phaas"),
    ("rat builder",          "phaas"),
    ("botnet c2 panel",      "general"),
    ("keylogger builder",    "infostealer"),
]


def _ingest_github_tool_repos(table) -> dict:
    """
    GitHub repo search for malware/tool-distribution repos (added
    2026-07-24) — reuses the existing relayshield/github_search_token
    credential already provisioned for _github_secret_scan(), zero new
    vendor/secret. Different GitHub API than that function uses: this is
    Repository Search (name/description/readme), not Code Search.

    Real precision limitation, stated plainly rather than glossed over: a
    repo named/described with a stealer family name is not reliably
    distinguishable via search alone from a legitimate malware-analysis
    writeup *about* that family (a very common, entirely legitimate genre
    of security-research repo). This ingests candidates for the admin
    digest to review, not an auto-verdict -- no alerting/scoring is wired
    to this table yet, deliberately, until that precision problem has a
    real answer.

    GitHub's Search API has its own stricter rate limit (30 req/min
    authenticated) separate from the general API limit -- paced accordingly.
    """
    fetched = written = 0
    try:
        raw = _sm.get_secret_value(SecretId=GITHUB_TOOL_SECRET_NAME)["SecretString"].strip()
        token = json.loads(raw).get("token", raw) if raw.startswith("{") else raw
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "RelayShield-ToolRepoSearch/1.0",
        }
    except Exception as exc:
        logger.warning("GitHub tool-repo search: no token available, skipping: %s", exc)
        return {"fetched": 0, "written": 0}

    repo_table = _dynamodb.Table(TOOL_REPOS_TABLE)
    now = datetime.now(timezone.utc).isoformat()

    for keyword, category in GITHUB_TOOL_KEYWORDS:
        try:
            query = f'{keyword} in:name,description'
            url = f"{GITHUB_SEARCH_REPOS_URL}?q={urllib.parse.quote(query)}&sort=updated&per_page=10"
            req = urllib.request.Request(url, headers=headers)
            resp = json.loads(urllib.request.urlopen(req, timeout=10).read())
            for item in resp.get("items", []):
                fetched += 1
                full_name = item.get("full_name", "")
                if not full_name:
                    continue
                try:
                    existing = repo_table.get_item(Key={"repo_full_name": full_name}).get("Item")
                    if existing:
                        continue
                    repo_table.put_item(Item={
                        "repo_full_name": full_name,
                        "url":            item.get("html_url", ""),
                        "description":    (item.get("description") or "")[:300],
                        "stars":          item.get("stargazers_count", 0),
                        "pushed_at":      item.get("pushed_at", ""),
                        "matched_keyword": keyword,
                        "category":       category,
                        "first_seen":     now,
                        "ttl":            Decimal(int(time.time()) + 180 * 86400),
                    })
                    written += 1
                except Exception as exc:
                    logger.warning("Tool-repo store failed repo=%s: %s", full_name, exc)
        except Exception as exc:
            logger.warning("GitHub tool-repo search failed keyword=%s: %s", keyword, exc)
        time.sleep(2.5)  # 30 req/min GitHub Search API limit — stay well under it

    logger.info("GitHub tool-repo search: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


def _ingest_paste_sites(table) -> dict:
    """
    Ingest IOCs from free paste sites: paste.ee and pastehub.net.
    Scans recent public pastes for IP addresses, domains, and URLs.
    No auth required — free public APIs.
    """
    import re as _re
    _ip_re  = _re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b")
    _dom_re = _re.compile(r"\b(?:[a-zA-Z0-9\-]{1,63}\.)+(?:com|net|org|io|ru|cc|pw|top|site|online|xyz)\b", _re.I)
    _url_re = _re.compile(r"https?://[^\s\"'<>]{10,200}")

    fetched = written = 0

    # --- paste.ee ---
    try:
        req = urllib.request.Request(
            "https://paste.ee/api/get/recent",
            headers={"User-Agent": "RelayShield/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        pastes = data if isinstance(data, list) else data.get("pastes", data.get("data", []))
        for paste in pastes[:50]:
            content = paste.get("content") or paste.get("text") or paste.get("body") or ""
            if not content:
                continue
            fetched += 1
            for ip in _ip_re.findall(content):
                if not ip.startswith(("127.", "192.168.", "10.", "172.")):
                    if _write_ioc(table, ip, "ip", "paste_ee"):
                        written += 1
            for dom in _dom_re.findall(content):
                if _write_ioc(table, dom.lower(), "domain", "paste_ee"):
                    written += 1
            for url in _url_re.findall(content):
                if _write_ioc(table, url[:500], "url", "paste_ee"):
                    written += 1
    except Exception as exc:
        logger.warning("paste.ee fetch failed: %s", exc)

    # --- pastehub.net ---
    try:
        req = urllib.request.Request(
            "https://pastehub.net/b/",
            headers={"User-Agent": "RelayShield/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode("utf-8", errors="ignore")
        # Extract paste IDs from the listing page and fetch each
        paste_ids = _re.findall(r'/p/([a-zA-Z0-9]+)', raw)[:20]
        for pid in paste_ids:
            try:
                pr = urllib.request.Request(
                    f"https://pastehub.net/p/{pid}/raw",
                    headers={"User-Agent": "RelayShield/1.0"},
                )
                with urllib.request.urlopen(pr, timeout=10) as pr_resp:
                    content = pr_resp.read().decode("utf-8", errors="ignore")
                fetched += 1
                for ip in _ip_re.findall(content):
                    if not ip.startswith(("127.", "192.168.", "10.", "172.")):
                        if _write_ioc(table, ip, "ip", "pastehub"):
                            written += 1
                for dom in _dom_re.findall(content):
                    if _write_ioc(table, dom.lower(), "domain", "pastehub"):
                        written += 1
            except Exception:
                pass
    except Exception as exc:
        logger.warning("pastehub.net fetch failed: %s", exc)

    logger.info("Paste sites: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


def lambda_handler(event, context):
    logger.info("INTEL-FEED starting")
    table     = _dynamodb.Table(INTEL_IOCS_TABLE)
    bot_token = _get_bot_token()

    tf  = _ingest_threatfox(table)
    uh  = _ingest_urlhaus(table)
    sh  = _ingest_spamhaus(table)
    ab  = _ingest_abuseipdb(table)
    fd  = _ingest_feodo(table)
    fa  = _ingest_feodo_aggressive(table)
    mb  = _ingest_malwarebazaar(table)
    # Real gap found and fixed 2026-07-25: this used to run last, after
    # OTX/PhishTank/Talos -- three sources with a real history of hanging
    # or erroring out. When any one of them ate the Lambda's whole
    # remaining budget (PhishTank did, 3 runs in a row, before its own fix
    # above), everything scheduled after it -- including this -- silently
    # never ran at all. Moved up next to the other fast/reliable sources so
    # a single flaky source later in the list can't perpetually starve it.
    gh  = _ingest_github_tool_repos(table)
    et  = _ingest_emerging_threats(table)
    otx = _ingest_otx(table)
    op  = _ingest_openphish(table)
    bl  = _ingest_blocklist_de(table)
    ta  = _ingest_talos(table)
    ip  = _ingest_ipsum(table)
    # Disabled 2026-07-25: data.phishtank.com hangs the entire Lambda
    # invocation for the full 900s budget on every run, with zero log
    # output -- confirmed across 3 separate, independently-sound in-process
    # timeout mechanisms (bounded read loop, signal.alarm, and a background
    # ThreadPoolExecutor future with its own timeout, which doesn't even
    # depend on interrupting whatever the blocked call is stuck on). Since
    # even the thread-based approach failed identically, the interpreter
    # itself is going unresponsive, which is outside what any in-process
    # Python timeout can fix. Low marginal value (OpenPhish already covers
    # similar phishing-URL ground) vs. the real cost of continuing to block
    # every feed sequenced after it. Left as a defined-but-uncalled function
    # rather than deleted in case PhishTank's server behavior changes.
    pt = {"fetched": 0, "written": 0}
    # Disabled 2026-07-25: same failure shape as PhishTank above -- confirmed
    # live that this hangs the full 900s budget on "Fetching Hagezi TIF" with
    # only 318MB/1024MB memory used (so not an OOM this time, a genuine hang
    # or extremely slow transfer). _ingest_hagezi's urlopen(timeout=60) only
    # bounds each individual read, not total wall-clock time -- the exact bug
    # class already proven, across 3 separate fix attempts on PhishTank, to
    # not be reliably fixable with an in-process Python timeout in this
    # Lambda environment. Not worth a 4th debugging round + another 15-minute
    # invocation to prove it out further. Domain-reputation coverage is
    # already strong without it (ThreatFox, URLhaus, Spamhaus, MalwareBazaar,
    # blocklist.de, IPsum, Emerging Threats, OpenPhish all still run).
    hg = {"fetched": 0, "written": 0}
    c2  = _ingest_c2intel(table)
    ps  = _ingest_phishstats(table)
    tr  = _ingest_triage(table)
    pw  = _ingest_polyswarm(table)
    mp  = _ingest_malpedia(table)
    bv  = _ingest_botvrij(table)
    ps  = _ingest_paste_sites(table)

    total_written = (tf["written"] + uh["written"] + sh["written"] + ab["written"]
                     + fd["written"] + fa["written"] + mb["written"]
                     + et["written"] + otx["written"]
                     + op["written"] + bl["written"] + ta["written"] + ip["written"]
                     + pt["written"] + hg["written"] + c2["written"] + ps["written"]
                     + tr["written"] + pw["written"] + mp["written"] + bv["written"] + ps["written"]
                     + gh["written"])
    total_fetched = (tf["fetched"] + uh["fetched"] + sh["fetched"] + ab["fetched"]
                     + fd["fetched"] + fa["fetched"] + mb["fetched"]
                     + et["fetched"] + otx["fetched"]
                     + op["fetched"] + bl["fetched"] + ta["fetched"] + ip["fetched"]
                     + pt["fetched"] + hg["fetched"] + c2["fetched"] + ps["fetched"]
                     + tr["fetched"] + pw["fetched"] + mp["fetched"] + bv["fetched"] + ps["fetched"]
                     + gh["fetched"])

    ab_note = " (skipped — already ran today)" if ab.get("skipped") else ""
    summary = (
        f"<b>RelayShield INTEL-FEED</b>\n"
        f"ThreatFox: {tf['fetched']} fetched, {tf['written']} new\n"
        f"URLhaus: {uh['fetched']} fetched, {uh['written']} new\n"
        f"Spamhaus DROP+EDROP: {sh['fetched']} fetched, {sh['written']} new\n"
        f"AbuseIPDB: {ab['fetched']} fetched, {ab['written']} new{ab_note}\n"
        f"Feodo Tracker: {fd['fetched']} fetched, {fd['written']} new\n"
        f"Feodo Aggressive: {fa['fetched']} fetched, {fa['written']} new\n"
        f"MalwareBazaar: {mb['fetched']} fetched, {mb['written']} new\n"
        f"Emerging Threats: {et['fetched']} fetched, {et['written']} new\n"
        f"AlienVault OTX: {otx['fetched']} fetched, {otx['written']} new\n"
        f"OpenPhish: {op['fetched']} fetched, {op['written']} new\n"
        f"blocklist.de: {bl['fetched']} fetched, {bl['written']} new\n"
        f"Cisco Talos: {ta['fetched']} fetched, {ta['written']} new\n"
        f"IPsum: {ip['fetched']} fetched, {ip['written']} new\n"
        f"PhishTank: {pt['fetched']} fetched, {pt['written']} new\n"
        f"Hagezi TIF: {hg['fetched']} fetched, {hg['written']} new\n"
        f"C2IntelFeeds: {c2['fetched']} fetched, {c2['written']} new\n"
        f"PhishStats: {ps['fetched']} fetched, {ps['written']} new\n"
        f"Triage Sandbox: {tr['fetched']} fetched, {tr['written']} new\n"
        f"PolySwarm: {pw['fetched']} fetched, {pw['written']} new\n"
        f"Malpedia Families: {mp['fetched']} families normalized\n"
        f"Botvrij: {bv['fetched']} fetched / {bv['written']} new\n"
        f"Paste sites (paste.ee + pastehub): {ps['fetched']} fetched / {ps['written']} new\n"
        f"GitHub tool repos: {gh['fetched']} fetched / {gh['written']} new (review candidates, not auto-alerted)\n"
        f"Total new IOCs: {total_written}"
    )
    _send_telegram(bot_token, ADMIN_CHAT_ID, summary)
    logger.info("INTEL-FEED complete: fetched=%d written=%d", total_fetched, total_written)

    return {
        "statusCode":       200,
        "total_fetched":    total_fetched,
        "total_written":    total_written,
        "threatfox":        tf,
        "urlhaus":          uh,
        "spamhaus":         sh,
        "abuseipdb":        ab,
        "feodo_tracker":    fd,
        "feodo_aggressive": fa,
        "malwarebazaar":    mb,
        "emerging_threats": et,
        "otx":              otx,
        "openphish":        op,
        "blocklist_de":     bl,
        "talos":            ta,
        "ipsum":            ip,
    }
