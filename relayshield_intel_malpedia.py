"""
RelayShield INTEL-MALPEDIA — Malpedia Malware Family Taxonomy Ingest

Downloads the full malware family catalog from Malpedia (Fraunhofer FKIE),
a free, publicly-accessible taxonomy of named malware families — no API
key or account required for the bulk family list/detail endpoints used
here (confirmed 2026-07-10; account-gated content like samples and
non-public YARA rules is a separate, unrelated part of their service).

Primary value: by far the largest free source of distinct, named malware
families available — ~3,800 entries vs. MITRE ATT&CK's ~800 (see
relayshield_intel_attack.py, which already covers MITRE's Software list).
Directly grows RelayShield's advertised "malware families tracked" metric.

Data stored in relayshield_malpedia_families:
  PK: family_id (Malpedia's own namespaced slug, e.g. "win.emotet")
  Attributes: common_name, alt_names, attribution, description, url

Architecture:
  EventBridge cron (weekly — low-change dataset, same cadence as MITRE)
  → Lambda (this file)
      → GET https://malpedia.caad.fkie.fraunhofer.de/api/get/families (bulk, no auth)
      → Write to relayshield_malpedia_families
      → Telegram admin digest
"""

import json
import logging
import os
import time
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MALPEDIA_TABLE   = "relayshield_malpedia_families"
TG_SECRET_NAME   = "relayshield/telegram_bot_token"
ADMIN_CHAT_ID    = int(os.environ.get("ADMIN_CHAT_ID", "1729226804"))

# Bulk "get all families with detail" endpoint — public, no Authorization
# header required. Confirmed 2026-07-10 via direct curl (HTTP 200, no key).
MALPEDIA_URL     = "https://malpedia.caad.fkie.fraunhofer.de/api/get/families"

# TTL: 30 days — re-ingested weekly, long TTL to survive missed runs
MALPEDIA_TTL_DAYS = 30

_secrets  = boto3.client("secretsmanager", region_name="us-east-1")
_dynamodb = boto3.resource("dynamodb",      region_name="us-east-1")


def _tg_token() -> str:
    return json.loads(_secrets.get_secret_value(SecretId=TG_SECRET_NAME)["SecretString"])["telegram_bot_token"]


def _send_telegram(text: str) -> None:
    token = _tg_token()
    url   = f"https://api.telegram.org/bot{token}/sendMessage"
    body  = json.dumps({"chat_id": ADMIN_CHAT_ID, "text": text, "parse_mode": "Markdown"}).encode()
    req   = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        logger.warning("Telegram notify failed: %s", exc)


def _fetch_malpedia_families() -> dict:
    logger.info("Fetching Malpedia family catalog (bulk, no auth)")
    req = urllib.request.Request(
        MALPEDIA_URL,
        headers={"User-Agent": "RelayShield-Malpedia-Ingest/1.0"},
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read())


def _write_to_dynamo(families: dict) -> int:
    table = _dynamodb.Table(MALPEDIA_TABLE)
    now   = datetime.now(timezone.utc).isoformat()
    ttl   = Decimal(int(time.time()) + MALPEDIA_TTL_DAYS * 86400)
    written = 0

    with table.batch_writer() as batch:
        for family_id, entry in families.items():
            common_name = entry.get("common_name", "") or family_id
            batch.put_item(Item={
                "family_id":    family_id,
                "common_name":  common_name,
                "alt_names":    entry.get("alt_names", []),
                "attribution":  entry.get("attribution", []),
                "description":  (entry.get("description") or "")[:500],
                "updated":      entry.get("updated", ""),
                "ingested_at":  now,
                "ttl":          ttl,
            })
            written += 1

    logger.info("Malpedia: wrote %d families", written)
    return written


def lambda_handler(event, context):
    logger.info("INTEL-MALPEDIA starting")
    try:
        families = _fetch_malpedia_families()
        written  = _write_to_dynamo(families)
        _send_telegram(
            f"\U0001f9a0 *Malpedia families ingested*\n\n"
            f"Families written: {written}\n"
            f"_RelayShield INTEL-MALPEDIA — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_"
        )
        return {"statusCode": 200, "families_written": written}
    except Exception as exc:
        logger.exception("INTEL-MALPEDIA failed: %s", exc)
        _send_telegram(f"\U0001f6a8 *INTEL-MALPEDIA error*\n\n`{str(exc)[:300]}`")
        return {"statusCode": 500, "error": str(exc)}
