"""
RelayShield INTEL-ATLAS — MITRE ATLAS Ingest

Downloads the MITRE ATLAS (Adversarial Threat Landscape for AI Systems) YAML
dataset from the official GitHub repository and writes tactics, techniques,
mitigations, and case studies to DynamoDB.

Primary value: ATLAS is ATT&CK's counterpart for AI-specific attack surfaces
(training pipelines, model weights, inference APIs, prompt injection, RAG
poisoning, AI supply-chain compromise). Its 2026 additions cover exactly the
agentic-AI techniques RelayShield's Bundle D endpoints (mcp-registry-risk,
prompt-injection-breach) are built to detect — this gives those findings a
standardized, citable industry framework ID instead of just RelayShield's
own taxonomy, the same way MITRE ATT&CK IDs already enrich the IOC feed.

Data stored in relayshield_mitre_atlas:
  PK: item_id (e.g. AML.T0000, AML.TA0002, AML.M0000, AML.CS0000)
  SK: "info"
  Attributes vary by entity_type (technique | tactic | mitigation | case-study)

Architecture:
  EventBridge cron (weekly, Sunday 07:30 UTC — offset 30min from the existing
  ATT&CK ingest at 07:00, same low-change-dataset cadence)
  → Lambda (this file)
      → Download ATLAS.yaml from mitre-atlas/atlas-data GitHub
      → Parse tactics, techniques, mitigations, case studies
      → Write to relayshield_mitre_atlas
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
import yaml

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ATLAS_TABLE    = "relayshield_mitre_atlas"
TG_SECRET_NAME = "relayshield/telegram_bot_token"
ADMIN_CHAT_ID  = int(os.environ.get("ADMIN_CHAT_ID", "1729226804"))

# MITRE ATLAS — official GitHub distributable
ATLAS_YAML_URL = (
    "https://raw.githubusercontent.com/mitre-atlas/atlas-data/main/dist/ATLAS.yaml"
)

# TTL: 30 days — re-ingested weekly, long TTL to survive missed runs
ATLAS_TTL_DAYS = 30

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


def _fetch_atlas_bundle() -> dict:
    logger.info("Fetching MITRE ATLAS dataset from GitHub")
    req = urllib.request.Request(
        ATLAS_YAML_URL,
        headers={"User-Agent": "RelayShield-ATLAS-Ingest/1.0"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return yaml.safe_load(resp.read())


def _parse_bundle(bundle: dict) -> tuple[list, list, list, list]:
    """Returns (tactics, techniques, mitigations, case_studies) as lists of dicts."""
    matrix = bundle["matrices"][0]
    return (
        matrix.get("tactics", []),
        matrix.get("techniques", []),
        matrix.get("mitigations", []),
        bundle.get("case-studies", []),
    )


def _write_to_dynamo(tactics: list, techniques: list, mitigations: list, case_studies: list) -> dict:
    table = _dynamodb.Table(ATLAS_TABLE)
    now   = datetime.now(timezone.utc).isoformat()
    ttl   = Decimal(int(time.time()) + ATLAS_TTL_DAYS * 86400)
    counts = {"tactics": 0, "techniques": 0, "mitigations": 0, "case_studies": 0}

    with table.batch_writer() as batch:
        for tac in tactics:
            batch.put_item(Item={
                "item_id":     tac["id"],
                "sk":          "info",
                "entity_type": "tactic",
                "name":        tac.get("name", ""),
                "description": (tac.get("description") or "")[:500],
                "ingested_at": now,
                "ttl":         ttl,
            })
            counts["tactics"] += 1

        for tech in techniques:
            batch.put_item(Item={
                "item_id":     tech["id"],
                "sk":          "info",
                "entity_type": "technique",
                "name":        tech.get("name", ""),
                "description": (tech.get("description") or "")[:500],
                "tactic_ids":  tech.get("tactics") or [],
                "attack_ref":  tech.get("ATT&CK-reference", {}).get("id", "") if tech.get("ATT&CK-reference") else "",
                "ingested_at": now,
                "ttl":         ttl,
            })
            counts["techniques"] += 1

        for mit in mitigations:
            batch.put_item(Item={
                "item_id":     mit["id"],
                "sk":          "info",
                "entity_type": "mitigation",
                "name":        mit.get("name", ""),
                "description": (mit.get("description") or "")[:500],
                "ingested_at": now,
                "ttl":         ttl,
            })
            counts["mitigations"] += 1

        for cs in case_studies:
            procedure = [
                {"tactic": p.get("tactic", ""), "technique": p.get("technique", "")}
                for p in (cs.get("procedure") or [])
            ]
            batch.put_item(Item={
                "item_id":       cs["id"],
                "sk":            "info",
                "entity_type":   "case-study",
                "name":          cs.get("name", ""),
                "summary":       (cs.get("summary") or "")[:500],
                "incident_date": str(cs.get("incident-date", "")),
                "procedure":     procedure,
                "ingested_at":   now,
                "ttl":           ttl,
            })
            counts["case_studies"] += 1

    logger.info("MITRE ATLAS: wrote %s", counts)
    return counts


def lambda_handler(event, context):
    logger.info("INTEL-ATLAS starting")
    try:
        bundle = _fetch_atlas_bundle()
        tactics, techniques, mitigations, case_studies = _parse_bundle(bundle)
        counts = _write_to_dynamo(tactics, techniques, mitigations, case_studies)
        _send_telegram(
            f"🤖 *MITRE ATLAS ingested*\n\n"
            f"Tactics: {counts['tactics']}\n"
            f"Techniques: {counts['techniques']}\n"
            f"Mitigations: {counts['mitigations']}\n"
            f"Case studies: {counts['case_studies']}\n"
            f"_RelayShield INTEL-ATLAS — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_"
        )
        return {"statusCode": 200, **counts}
    except Exception as exc:
        logger.exception("INTEL-ATLAS failed: %s", exc)
        _send_telegram(f"🚨 *INTEL-ATLAS error*\n\n`{str(exc)[:300]}`")
        return {"statusCode": 500, "error": str(exc)}
