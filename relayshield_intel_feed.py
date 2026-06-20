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

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INTEL_IOCS_TABLE    = "relayshield_intel_iocs"
TG_SECRET_NAME      = "relayshield/telegram_bot_token"
ABUSEIPDB_SECRET    = "relayshield/abuseipdb_api_key"
ADMIN_CHAT_ID       = int(os.environ.get("ADMIN_CHAT_ID", "1729226804"))
ALERT_TTL_DAYS      = 90

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
        raw = _sm.get_secret_value(SecretId=OTX_SECRET)["SecretString"]
        d = json.loads(raw)
        return d.get("api_key") or d.get("otx_api_key", "")
    except Exception:
        return ""


def _abuseipdb_already_ran_today(table) -> bool:
    """Return True if AbuseIPDB was already fetched in the last 23 hours."""
    try:
        resp = table.get_item(Key={"ioc_value": ABUSEIPDB_GUARD_KEY})
        return "Item" in resp
    except Exception:
        return False


def _mark_abuseipdb_ran(table) -> None:
    """Set a 23-hour TTL guard so AbuseIPDB only runs once per day."""
    ttl = Decimal(int(time.time()) + 23 * 3600)
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
    ttl    = Decimal(int(time.time()) + ALERT_TTL_DAYS * 86400)
    try:
        table.put_item(
            Item={
                "ioc_value":   ioc_value.lower().strip(),
                "seen_ts":     now_ts,
                "ioc_type":    ioc_type,
                "channel":     source,
                "category":    "threat_feed",
                "malware":     malware,
                "ttl":         ttl,
            },
            ConditionExpression="attribute_not_exists(ioc_value)",
        )
        return True
    except _dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return False  # duplicate
    except Exception as exc:
        logger.warning("IOC write failed %s: %s", ioc_value[:30], exc)
        return False


def _batch_write_iocs(table, items: list) -> int:
    """Batch-write IOCs using DynamoDB batch_writer (handles chunking + retries). Returns count attempted."""
    now_ts = datetime.now(timezone.utc).isoformat()
    ttl    = Decimal(int(time.time()) + ALERT_TTL_DAYS * 86400)
    written = 0
    try:
        with table.batch_writer() as batch:
            for ioc_value, ioc_type, source, malware in items:
                batch.put_item(Item={
                    "ioc_value": ioc_value.lower().strip(),
                    "seen_ts":   now_ts,
                    "ioc_type":  ioc_type,
                    "channel":   source,
                    "category":  "threat_feed",
                    "malware":   malware,
                    "ttl":       ttl,
                })
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
    written = 0
    for entry in records:
        ip = (entry.get("ipAddress") or "").strip()
        if not ip:
            continue
        if _write_ioc(table, ip, "ip", "abuseipdb"):
            written += 1

    _mark_abuseipdb_ran(table)
    logger.info("AbuseIPDB: fetched=%d written=%d", fetched, written)
    return {"fetched": fetched, "written": written}


# ---------------------------------------------------------------------------
# PhishTank ingestion (verified phishing URLs — public, gzipped CSV)
# ---------------------------------------------------------------------------

def _ingest_phishtank(table) -> dict:
    """Pull PhishTank verified phishing URLs (public, no auth, gzipped CSV)."""
    import csv, io, gzip
    logger.info("Fetching PhishTank CSV")
    req = urllib.request.Request(
        PHISHTANK_CSV,
        headers={"User-Agent": "RelayShield/1.0 (phishtank@relayshield.net)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
        content = gzip.decompress(raw).decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.error("PhishTank fetch failed: %s", exc)
        return {"fetched": 0, "written": 0}

    fetched = written = 0
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        url = (row.get("url") or "").strip()
        if not url:
            continue
        fetched += 1
        match = _RE_DOMAIN.search(url)
        if match and _write_ioc(table, match.group(0).lower(), "domain", "phishtank"):
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
    fetched = written = 0
    import re
    ip_re = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
    for line in lines:
        ip = line.strip()
        if not ip or not ip_re.match(ip):
            continue
        fetched += 1
        if _write_ioc(table, ip, "ip", "blocklist_de", ""):
            written += 1
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
    fetched = written = 0
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
        if _write_ioc(table, ip, "ip", "ipsum", ""):
            written += 1
    logger.info("IPsum: fetched=%d written=%d", fetched, written)
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
    et  = _ingest_emerging_threats(table)
    otx = _ingest_otx(table)
    op  = _ingest_openphish(table)
    bl  = _ingest_blocklist_de(table)
    ta  = _ingest_talos(table)
    ip  = _ingest_ipsum(table)

    total_written = (tf["written"] + uh["written"] + sh["written"] + ab["written"]
                     + fd["written"] + fa["written"] + mb["written"]
                     + et["written"] + otx["written"]
                     + op["written"] + bl["written"] + ta["written"] + ip["written"])
    total_fetched = (tf["fetched"] + uh["fetched"] + sh["fetched"] + ab["fetched"]
                     + fd["fetched"] + fa["fetched"] + mb["fetched"]
                     + et["fetched"] + otx["fetched"]
                     + op["fetched"] + bl["fetched"] + ta["fetched"] + ip["fetched"])

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
