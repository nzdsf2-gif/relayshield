"""
RelayShield MSP Weekly Digest

Sends a weekly threat intelligence summary to TI subscribers ($499/$999/mo)
showing what RelayShield detected this week — proving ongoing value and surfacing
trends that inform their client conversations.

Delivered via: SES email to the subscriber's registered email address.

Digest includes:
  • Total IOC corpus size and new IOCs added this week
  • Top malware families active this week (by ThreatFox/MalwareBazaar hits)
  • Ransomware groups active this week (from ransomwatch victim list)
  • Pre-ransomware credential counts
  • Threat actor attribution highlights
  • New infostealer families detected

Architecture:
  EventBridge cron (Mondays 09:00 UTC — after intel-feed daily run)
  → Lambda (this file)
      → Scan relayshield_api_keys for intel_access=True subscribers
      → Aggregate stats from relayshield_intel_iocs + relayshield_intel_ransomware
      → Send branded HTML email via SES

Secrets:
  relayshield/telegram_bot_token — for admin digest notification
"""

import json
import logging
import os
import time
from collections import Counter
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INTEL_IOCS_TABLE    = "relayshield_intel_iocs"
RANSOMWARE_TABLE    = "relayshield_intel_ransomware"
API_KEYS_TABLE      = "relayshield_api_keys"
FROM_EMAIL          = "noreply@relayshield.net"
TG_SECRET_NAME      = "relayshield/telegram_bot_token"
ADMIN_CHAT_ID       = int(os.environ.get("ADMIN_CHAT_ID", "1729226804"))

# Threat actor map (mirrors relayshield_api.py)
THREAT_ACTOR_MAP = {
    "qakbot": "TA505", "emotet": "TA542 (Mealybug)", "trickbot": "Wizard Spider",
    "dridex": "Evil Corp", "icedid": "Shatak (TA551)", "bumblebee": "Exotic Lily",
    "lummac2": "Multiple actors (MaaS)", "redline": "Multiple actors (MaaS)",
    "pikabot": "Water Curupira", "bazarloader": "Wizard Spider",
    "clearfake": "SocGholish operators", "cobalt_strike": "Multiple (post-exploitation)",
}

_secrets  = boto3.client("secretsmanager", region_name="us-east-1")
_dynamodb = boto3.resource("dynamodb",      region_name="us-east-1")
_ses      = boto3.client("ses",             region_name="us-east-1")


def _tg_token() -> str:
    raw = _secrets.get_secret_value(SecretId=TG_SECRET_NAME)["SecretString"]
    return json.loads(raw)["telegram_bot_token"]


def _send_telegram(chat_id: int, text: str) -> None:
    import urllib.request
    token = _tg_token()
    url   = f"https://api.telegram.org/bot{token}/sendMessage"
    body  = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
    req   = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        logger.warning("Telegram digest notify failed: %s", exc)


# ---------------------------------------------------------------------------
# Stats aggregation
# ---------------------------------------------------------------------------

def _week_start() -> str:
    """ISO timestamp for 7 days ago."""
    return (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()


def _aggregate_ioc_stats() -> dict:
    """Scan recent IOCs for top malware families, source breakdown, total count."""
    table    = _dynamodb.Table(INTEL_IOCS_TABLE)
    week_ago = _week_start()
    malware_counter: Counter = Counter()
    source_counter:  Counter = Counter()
    total_new = 0

    kwargs = {
        "FilterExpression": Attr("seen_ts").gte(week_ago),
        "ProjectionExpression": "malware, channel",
    }
    while True:
        resp  = table.scan(**kwargs)
        items = resp.get("Items", [])
        total_new += len(items)
        for item in items:
            m = (item.get("malware") or "").strip()
            s = (item.get("channel") or "unknown").strip()
            if m and m not in ("None", "n/a", ""):
                # Split compound tags
                for family in m.split(","):
                    family = family.strip().lower()
                    if family and family not in ("none", "n/a", "opendir", "elf", "rat",
                                                  "encoded", "ascii", "sh", "apk"):
                        malware_counter[family] += 1
            if s:
                source_counter[s] += 1
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last

    top_malware  = malware_counter.most_common(10)
    top_sources  = source_counter.most_common(5)

    # Total corpus size (approximate via item count)
    try:
        total_corpus = table.item_count  # DynamoDB approximate count (updated every 6h)
    except Exception:
        total_corpus = 0

    return {
        "total_new_iocs":  total_new,
        "total_corpus":    total_corpus,
        "top_malware":     top_malware,
        "top_sources":     top_sources,
    }


def _aggregate_ransomware_stats() -> dict:
    """Get ransomware victims listed this week."""
    table    = _dynamodb.Table(RANSOMWARE_TABLE)
    week_ago = _week_start()
    victims  = []
    groups:  Counter = Counter()

    kwargs = {
        "FilterExpression": Attr("ingested_at").gte(week_ago),
        "ProjectionExpression": "#d, #g, discovered",
        "ExpressionAttributeNames": {"#d": "domain", "#g": "group"},
    }
    while True:
        resp = table.scan(**kwargs)
        for item in resp.get("Items", []):
            victims.append({"domain": item.get("domain", ""), "group": item.get("group", "")})
            if item.get("group"):
                groups[item["group"]] += 1
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last

    return {
        "new_victims":   len(victims),
        "victims":       victims[:10],   # cap for email length
        "active_groups": groups.most_common(5),
    }


# ---------------------------------------------------------------------------
# Email rendering
# ---------------------------------------------------------------------------

def _build_html(stats: dict, ransomware: dict, week_label: str) -> str:
    malware_rows = "".join(
        f"<tr><td style='padding:6px 12px;border-bottom:1px solid #e5e7eb'>{fam}</td>"
        f"<td style='padding:6px 12px;border-bottom:1px solid #e5e7eb;text-align:right'>{cnt}</td>"
        f"<td style='padding:6px 12px;border-bottom:1px solid #e5e7eb;color:#6b7280;font-size:0.85em'>"
        f"{THREAT_ACTOR_MAP.get(fam, '')}</td></tr>"
        for fam, cnt in stats["top_malware"]
    )
    victim_rows = "".join(
        f"<tr><td style='padding:6px 12px;border-bottom:1px solid #e5e7eb'>{v['domain']}</td>"
        f"<td style='padding:6px 12px;border-bottom:1px solid #e5e7eb;color:#dc2626'>{v['group']}</td></tr>"
        for v in ransomware["victims"]
    )
    ransomware_section = f"""
    <h2 style='color:#0f1f3d;font-size:1rem;margin:24px 0 8px'>🦠 Ransomware Activity</h2>
    <p style='color:#374151;margin:0 0 8px'>{ransomware['new_victims']} new victim listing(s) this week.</p>
    {'<table style="width:100%;border-collapse:collapse;font-size:0.9rem"><thead><tr><th style="text-align:left;padding:6px 12px;background:#f3f4f6">Domain</th><th style="text-align:left;padding:6px 12px;background:#f3f4f6">Group</th></tr></thead><tbody>' + victim_rows + '</tbody></table>' if ransomware['victims'] else '<p style="color:#6b7280">No new victim listings this week.</p>'}
    """ if ransomware["new_victims"] > 0 else ""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f9fafb;margin:0;padding:24px">
<div style="max-width:640px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1)">
  <div style="background:#0f1f3d;padding:24px 32px">
    <div style="color:#00b5a5;font-size:1.4rem;font-weight:700">RelayShield</div>
    <div style="color:#a0b4cc;font-size:0.9rem;margin-top:4px">Weekly Threat Intelligence Digest — {week_label}</div>
  </div>
  <div style="padding:28px 32px">
    <h2 style="color:#0f1f3d;font-size:1rem;margin:0 0 16px">📊 IOC Corpus</h2>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:24px">
      <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;text-align:center">
        <div style="font-size:1.6rem;font-weight:700;color:#15803d">{stats['total_new_iocs']:,}</div>
        <div style="color:#6b7280;font-size:0.85rem">New IOCs this week</div>
      </div>
      <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:16px;text-align:center">
        <div style="font-size:1.6rem;font-weight:700;color:#1d4ed8">{stats['total_corpus']:,}</div>
        <div style="color:#6b7280;font-size:0.85rem">Total corpus</div>
      </div>
    </div>

    <h2 style="color:#0f1f3d;font-size:1rem;margin:0 0 8px">🦠 Top Malware Families</h2>
    <table style="width:100%;border-collapse:collapse;font-size:0.9rem;margin-bottom:24px">
      <thead><tr>
        <th style="text-align:left;padding:6px 12px;background:#f3f4f6">Family</th>
        <th style="text-align:right;padding:6px 12px;background:#f3f4f6">IOCs</th>
        <th style="text-align:left;padding:6px 12px;background:#f3f4f6">Threat Actor</th>
      </tr></thead>
      <tbody>{malware_rows if malware_rows else '<tr><td colspan="3" style="padding:12px;color:#6b7280;text-align:center">No malware-tagged IOCs this week</td></tr>'}</tbody>
    </table>

    {ransomware_section}

    <div style="margin-top:24px;padding:16px;background:#f8fafc;border-radius:8px;border-left:4px solid #00b5a5">
      <div style="font-size:0.85rem;color:#374151">
        <strong>Query your IOC feed:</strong> POST /v1/intel/telegram with any domain, IP, email, or phone.<br>
        <strong>STIX/TAXII:</strong> GET /v1/intel/taxii/collections/iocs/objects/ for SIEM ingestion.<br>
        <strong>Ransomware risk:</strong> POST /v1/metered/ransomware-risk for per-domain victim + pre-credential check.
      </div>
    </div>
  </div>
  <div style="padding:16px 32px;background:#f9fafb;border-top:1px solid #e5e7eb;font-size:0.8rem;color:#9ca3af;text-align:center">
    RelayShield — relayshield.net · Unsubscribe: reply with UNSUBSCRIBE
  </div>
</div></body></html>"""


def _build_text(stats: dict, ransomware: dict, week_label: str) -> str:
    malware_lines = "\n".join(
        f"  {fam}: {cnt} IOCs{' — ' + THREAT_ACTOR_MAP[fam] if fam in THREAT_ACTOR_MAP else ''}"
        for fam, cnt in stats["top_malware"]
    )
    victim_lines = "\n".join(
        f"  {v['domain']} — {v['group']}" for v in ransomware["victims"]
    )
    return f"""RelayShield Weekly Threat Intelligence Digest — {week_label}

IOC CORPUS
  New this week: {stats['total_new_iocs']:,}
  Total corpus: {stats['total_corpus']:,}

TOP MALWARE FAMILIES
{malware_lines or '  None detected this week'}

RANSOMWARE ACTIVITY ({ransomware['new_victims']} new victims)
{victim_lines or '  No new victim listings'}

Query your feed: POST /v1/intel/telegram
STIX/TAXII: GET /v1/intel/taxii/collections/iocs/objects/
Ransomware risk: POST /v1/metered/ransomware-risk

— RelayShield (relayshield.net)
"""


# ---------------------------------------------------------------------------
# Subscriber lookup + email send
# ---------------------------------------------------------------------------

def _get_ti_subscribers() -> list[dict]:
    """Return all active TI subscribers (intel_access=True)."""
    table = _dynamodb.Table(API_KEYS_TABLE)
    subs  = []
    kwargs = {"FilterExpression": Attr("intel_access").eq(True)}
    while True:
        resp = table.scan(**kwargs)
        subs.extend(resp.get("Items", []))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return subs


def _send_digest_email(email: str, subject: str, html: str, text: str) -> bool:
    try:
        _ses.send_email(
            Source=FROM_EMAIL,
            Destination={"ToAddresses": [email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": text,  "Charset": "UTF-8"},
                    "Html": {"Data": html,  "Charset": "UTF-8"},
                },
            },
        )
        return True
    except Exception as exc:
        logger.error("Digest email failed email=%s: %s", email, exc)
        return False


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    logger.info("MSP weekly digest starting")
    week_label = datetime.now(timezone.utc).strftime("Week of %B %d, %Y")
    subject    = f"RelayShield Weekly TI Digest — {datetime.now(timezone.utc).strftime('%b %d')}"

    stats      = _aggregate_ioc_stats()
    ransomware = _aggregate_ransomware_stats()
    html       = _build_html(stats, ransomware, week_label)
    text       = _build_text(stats, ransomware, week_label)

    subscribers = _get_ti_subscribers()
    sent = 0
    for sub in subscribers:
        email = sub.get("developer_email") or sub.get("email", "")
        if email and "@" in email:
            if _send_digest_email(email, subject, html, text):
                sent += 1
                logger.info("Digest sent to %s", email)

    summary = (
        f"📊 *MSP Weekly Digest sent*\n\n"
        f"Week: {week_label}\n"
        f"Subscribers notified: {sent}/{len(subscribers)}\n"
        f"New IOCs this week: {stats['total_new_iocs']:,}\n"
        f"Ransomware victims: {ransomware['new_victims']}\n"
        f"Top family: {stats['top_malware'][0][0] if stats['top_malware'] else 'none'}\n\n"
        f"_RelayShield — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_"
    )
    _send_telegram(ADMIN_CHAT_ID, summary)

    return {
        "statusCode":   200,
        "sent":         sent,
        "subscribers":  len(subscribers),
        "new_iocs":     stats["total_new_iocs"],
        "new_victims":  ransomware["new_victims"],
    }
