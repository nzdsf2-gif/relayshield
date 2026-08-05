"""
RelayShield INTEL-MITRE — MITRE ATT&CK Ingest

Downloads the MITRE ATT&CK STIX 2.1 bundle from the official GitHub repository
and writes threat actor groups and their associated techniques to DynamoDB.

Primary value: enriches RelayShield's STIX/TAXII feed and IOC hit responses
with standardized ATT&CK Group IDs and Technique IDs that enterprise SIEMs
(Splunk, Sentinel, Elastic, QRadar) can match on natively — no custom parsing
required. Our hand-coded THREAT_ACTOR_MAP in relayshield_api.py maps to this
data and becomes machine-readable for SIEM rule engines.

Data stored in relayshield_mitre_attack:
  PK: group_id (e.g. G0102)
  SK: "info" | "technique:{T1234}" | "software:{S0001}"
  Attributes: name, aliases, description, techniques, url

Architecture:
  EventBridge cron (weekly, Sunday 07:00 UTC — low-change dataset)
  → Lambda (this file)
      → Download enterprise-attack.json STIX bundle from mitre-attack GitHub
      → Parse Group objects + Technique relationships
      → Write to relayshield_mitre_attack
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

ATTACK_TABLE     = "relayshield_mitre_attack"
TG_SECRET_NAME   = "relayshield/telegram_bot_token"
ADMIN_CHAT_ID    = int(os.environ.get("ADMIN_CHAT_ID", "1729226804"))

# MITRE ATT&CK Enterprise STIX bundle — official GitHub release
ATTACK_STIX_URL  = (
    "https://raw.githubusercontent.com/mitre/cti/master/"
    "enterprise-attack/enterprise-attack.json"
)

# TTL: 30 days — re-ingested weekly, long TTL to survive missed runs
ATTACK_TTL_DAYS  = 30

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


# Geopolitical attribution — country of origin from MITRE ATT&CK assessments
# Source: MITRE ATT&CK country attribution (public, publicly documented)
_GROUP_COUNTRY: dict[str, str] = {
    "APT1":             "China", "APT10":            "China",
    "APT19":            "China", "APT28":            "Russia",
    "APT29":            "Russia", "APT30":           "China",
    "APT32":            "Vietnam", "APT33":          "Iran",
    "APT34":            "Iran", "APT37":             "North Korea",
    "APT38":            "North Korea", "APT39":      "Iran",
    "APT40":            "China", "APT41":            "China",
    "Lazarus Group":    "North Korea", "Kimsuky":     "North Korea",
    "Sandworm Team":    "Russia", "Turla":            "Russia",
    "Fancy Bear":       "Russia", "Cozy Bear":        "Russia",
    "Wizard Spider":    "Russia", "Evil Corp":        "Russia",
    "TA505":            "Russia / Eastern Europe", "TA542":   "Unknown",
    "Carbanak":         "Russia / Eastern Europe",
    "FIN7":             "Russia / Eastern Europe",
    "Indrik Spider":    "Russia", "Temp.Veles":       "Russia",
    "Volt Typhoon":     "China", "Salt Typhoon":      "China",
    "Scattered Spider": "United Kingdom / United States",
    "Water Curupira":   "Unknown", "Exotic Lily":    "Unknown",
    "SocGholish":       "Unknown", "Shatak":          "Unknown",
    "Ember Bear":       "Russia",
}


def _fetch_attack_bundle() -> dict:
    logger.info("Fetching MITRE ATT&CK bundle from GitHub")
    req  = urllib.request.Request(
        ATTACK_STIX_URL,
        headers={"User-Agent": "RelayShield-MITRE-Ingest/1.0"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _parse_bundle(bundle: dict) -> tuple[dict, dict, dict, dict, dict]:
    """
    Returns:
      groups          — {group_id: {name, aliases, description, attack_id, url}}
      techniques      — {technique_id: {name, description, tactic_phases}}
      rel_map         — {group_id: set of technique_ids}
      software        — {software_id: {name, aliases, description, url, is_malware}}
        MITRE's "Software" category — STIX types "malware" and "tool" — named
        malware families and adversary tooling. Schema already anticipated
        this (SK "software:{S0001}" documented in the module docstring since
        this file was first written) but it was never actually parsed until
        2026-07-10, added specifically to grow the advertised malware family
        count using data already licensed for free (same MITRE feed already
        polled weekly for groups/techniques — zero new cost, zero new infra).
      software_rel_map — {group_id: set of software_ids}
        Group→Software "uses" relationships. The STIX bundle's relationship
        objects were already being scanned for "uses" edges, but the loop
        only kept ones where the target was a technique — Group→Software
        edges (the exact same relationship type, just pointing at malware/
        tool objects instead) were silently discarded. Added 2026-07-16 to
        power real threat-actor → malware-family → live-IOC attribution
        (RelayShield's IOC corpus already tags entries with a real `malware`
        family name), found while investigating why the Threat Actor tab's
        actor-lookup never returned any live IOCs for any group.
    """
    objects    = bundle.get("objects", [])
    groups:     dict[str, dict] = {}
    techniques: dict[str, dict] = {}
    software:   dict[str, dict] = {}
    # stix_id → attack_id mapping (for relationship resolution)
    stix_to_attack: dict[str, str] = {}

    for obj in objects:
        obj_type = obj.get("type", "")
        if obj_type in ("malware", "tool"):
            attack_id = next(
                (ref["external_id"] for ref in obj.get("external_references", [])
                 if ref.get("source_name") == "mitre-attack"),
                None,
            )
            if not attack_id:
                continue
            url = next(
                (ref.get("url", "") for ref in obj.get("external_references", [])
                 if ref.get("source_name") == "mitre-attack"),
                "",
            )
            software[obj["id"]] = {
                "software_id": attack_id,
                "name":        obj.get("name", ""),
                "aliases":     obj.get("x_mitre_aliases", obj.get("aliases", [])),
                "description": (obj.get("description") or "")[:500],
                "url":         url,
                "is_malware":  obj_type == "malware",
            }
            stix_to_attack[obj["id"]] = attack_id
        elif obj_type == "intrusion-set":
            # Threat actor group
            attack_id = next(
                (ref["external_id"] for ref in obj.get("external_references", [])
                 if ref.get("source_name") == "mitre-attack"),
                None,
            )
            if not attack_id:
                continue
            url = next(
                (ref.get("url", "") for ref in obj.get("external_references", [])
                 if ref.get("source_name") == "mitre-attack"),
                "",
            )
            groups[obj["id"]] = {
                "group_id":    attack_id,
                "name":        obj.get("name", ""),
                "aliases":     obj.get("aliases", []),
                "description": (obj.get("description") or "")[:500],
                "url":         url,
                "stix_id":     obj["id"],
            }
            stix_to_attack[obj["id"]] = attack_id

        elif obj_type == "attack-pattern":
            # Technique
            attack_id = next(
                (ref["external_id"] for ref in obj.get("external_references", [])
                 if ref.get("source_name") == "mitre-attack"),
                None,
            )
            if not attack_id:
                continue
            phases = [p.get("phase_name", "") for p in obj.get("kill_chain_phases", [])]
            techniques[obj["id"]] = {
                "technique_id": attack_id,
                "name":         obj.get("name", ""),
                "tactics":      phases,
            }
            stix_to_attack[obj["id"]] = attack_id

    # Build group → technique and group → software relationships. STIX 2.1
    # relationship objects have type "relationship" with the semantic edge
    # name in a separate "relationship_type" field ("uses", "mitigates",
    # "attributed-to", etc.) — NOT type "uses" directly. The previous check
    # (`obj.get("type") != "uses"`) never matched anything at all (confirmed
    # against the live bundle: 21,025 objects of type "relationship", zero of
    # type "uses"), so rel_map — and therefore every group's technique_ids —
    # has been silently empty since this file was written, not just the new
    # software_rel_map. Found and fixed 2026-07-16 alongside the software
    # relationship work.
    rel_map: dict[str, set] = {}
    software_rel_map: dict[str, set] = {}
    for obj in objects:
        if obj.get("type") != "relationship" or obj.get("relationship_type") != "uses":
            continue
        source = obj.get("source_ref", "")
        target = obj.get("target_ref", "")
        if source not in groups:
            continue
        if target in techniques:
            rel_map.setdefault(source, set()).add(stix_to_attack.get(target, target))
        elif target in software:
            software_rel_map.setdefault(source, set()).add(stix_to_attack.get(target, target))

    return groups, techniques, rel_map, software, software_rel_map


def _write_software_to_dynamo(software: dict) -> int:
    table = _dynamodb.Table(ATTACK_TABLE)
    now   = datetime.now(timezone.utc).isoformat()
    ttl   = Decimal(int(time.time()) + ATTACK_TTL_DAYS * 86400)
    written = 0

    with table.batch_writer() as batch:
        for entry in software.values():
            batch.put_item(Item={
                "group_id":    entry["software_id"],   # reuses the table's PK, matches "software:{S0001}" SK scheme
                "sk":          f"software:{entry['software_id']}",
                "name":        entry["name"],
                "aliases":     entry["aliases"],
                "description": entry["description"],
                "url":         entry["url"],
                "is_malware":  entry["is_malware"],
                "ingested_at": now,
                "ttl":         ttl,
            })
            written += 1

    logger.info("MITRE ATT&CK: wrote %d software/malware entries", written)
    return written


def _write_to_dynamo(groups: dict, rel_map: dict, software_rel_map: dict) -> int:
    table = _dynamodb.Table(ATTACK_TABLE)
    now   = datetime.now(timezone.utc).isoformat()
    ttl   = Decimal(int(time.time()) + ATTACK_TTL_DAYS * 86400)
    written = 0

    with table.batch_writer() as batch:
        for stix_id, group in groups.items():
            technique_ids = sorted(rel_map.get(stix_id, set()))
            software_ids  = sorted(software_rel_map.get(stix_id, set()))
            # Geopolitical attribution — country of origin where MITRE has assessed it
            country = _GROUP_COUNTRY.get(group["name"], _GROUP_COUNTRY.get(
                next((a for a in group["aliases"] if a in _GROUP_COUNTRY), ""), "Unknown"
            ))
            batch.put_item(Item={
                "group_id":        group["group_id"],
                "sk":              "info",
                "name":            group["name"],
                "aliases":         group["aliases"],
                "description":     group["description"],
                "url":             group["url"],
                "technique_ids":   technique_ids,
                "software_ids":    software_ids,
                "country_origin":  country,
                "ingested_at":     now,
                "ttl":             ttl,
            })
            written += 1

    logger.info("MITRE ATT&CK: wrote %d groups", written)
    return written


def lambda_handler(event, context):
    logger.info("INTEL-MITRE starting")
    try:
        bundle     = _fetch_attack_bundle()
        groups, techniques, rel_map, software, software_rel_map = _parse_bundle(bundle)
        written          = _write_to_dynamo(groups, rel_map, software_rel_map)
        software_written = _write_software_to_dynamo(software)
        _send_telegram(
            f"🛡️ *MITRE ATT&CK ingested*\n\n"
            f"Groups written: {written}\n"
            f"Techniques indexed: {len(techniques)}\n"
            f"Software/malware entries written: {software_written}\n"
            f"_RelayShield INTEL-MITRE — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_"
        )
        return {
            "statusCode": 200, "groups_written": written, "techniques": len(techniques),
            "software_written": software_written,
        }
    except Exception as exc:
        logger.exception("INTEL-MITRE failed: %s", exc)
        _send_telegram(f"🚨 *INTEL-MITRE error*\n\n`{str(exc)[:300]}`")
        return {"statusCode": 500, "error": str(exc)}
