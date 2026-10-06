"""
relayshield_telemetry — self-reported install/open telemetry.

Receives pings from:
  - Chrome extension on install (chrome.runtime.onInstalled, reason=install)
  - Telegram Mini App on page open (beacon from the worker page)

Stores events in DynamoDB relayshield_telemetry for the weekly metrics report.
No PII: client identifiers are hashed by the caller before sending.

Endpoint: POST /v1/telemetry
Body: {"event_type": "chrome_install" | "miniapp_open", "client_hash": "<sha256>", "version": "<optional>"}
"""

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
TABLE_NAME = os.environ.get("TELEMETRY_TABLE", "relayshield_telemetry")

VALID_EVENTS = {"chrome_install", "miniapp_open"}


def lambda_handler(event, context):
    try:
        body = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            import base64
            body = base64.b64decode(body).decode()
        data = json.loads(body) if isinstance(body, str) else body
    except Exception:
        return _resp(400, {"error": "Invalid JSON body"})

    event_type = (data.get("event_type") or "").strip().lower()
    if event_type not in VALID_EVENTS:
        return _resp(400, {"error": f"event_type must be one of {sorted(VALID_EVENTS)}"})

    # Client hash is optional but recommended — lets us count unique installs
    # without storing anything identifiable.
    client_hash = (data.get("client_hash") or "").strip()[:128]
    version = (data.get("version") or "").strip()[:32]

    event_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    item = {
        "event_id": event_id,
        "event_type": event_type,
        "created_at": now,
    }
    if client_hash:
        item["client_hash"] = client_hash
    if version:
        item["version"] = version

    try:
        table = dynamodb.Table(TABLE_NAME)
        table.put_item(Item=item)
    except Exception as exc:
        logger.exception("Failed to write telemetry event: %s", exc)
        return _resp(500, {"error": "Write failed"})

    logger.info("Telemetry recorded: %s", event_type)
    return _resp(200, {"ok": True, "event_id": event_id})


def _resp(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }

# Deploy trigger: workflow paths now include this file.
