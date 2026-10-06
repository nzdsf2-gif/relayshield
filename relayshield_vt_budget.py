"""One shared VirusTotal key, one daily allowance, and nothing counting it.

VirusTotal's free key allows 500 requests per UTC day and EVERY request counts:
a report lookup, a submission and each status poll. Five surfaces spend that one
allowance (the API's /v1/scan-url, /v1/scan-file, /v1/ip-intel and
/v1/result, the Telegram bot, the WhatsApp bot, and the composite check's
fallback), nothing counted any of it, and on 2026-10-06 VirusTotal's own email
was the first sign it was gone.

THE LEAK THIS CLOSES, found while building it: GET /v1/result/{id} and
GET /v1/payg/result/{id} were unauthenticated, uncapped, and spent one VT
request per call on our key, whatever id was supplied. Anyone, or any crawler
probing endpoints, could drain the day. handle_result now polls only analyses
THIS API submitted (mapping_check), and every poll is charged here.

WHAT THIS MODULE DOES
  * charge(surface, kind, caller): the daily budget. A per-caller cap (one API
    key cannot take the day), a cap on the BULK surfaces so the bots keep a
    reserve, and a global cap with headroom for manual use of the same VT
    account (the web UI counts against the same 500).
  * Logs `vt_call surface=... kind=... caller=... global=N` for every allowed
    call, so the next spike is attributable. A refusal logs `vt_refused`.
  * A verdict cache and an analysis-id mapping, held in the existing
    relayshield_demo_key_usage table under their own key prefixes, because that
    table already works for the shared role and a NEW table would need an IAM
    grant the role has no room for (the relayshield_breach_cache lesson).
    Reads are UpdateItem with a ConditionExpression: it needs no GetItem grant
    and a miss creates no row.

FAILS OPEN on a DynamoDB error. This is a cost guardrail on an optional signal,
and an infra blip must not turn every scan into an outage. The opposite
choice was made for the breach partner budget, which protects OTHER customers'
access to a shared rate limit; here the failure mode of failing open is exactly
today's behaviour.

Stores hashes and counters only. No URL, no email and no IP is written.
"""
import hashlib
import logging
import os
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

TABLE = "relayshield_demo_key_usage"
GLOBAL_CAP = int(os.environ.get("VT_DAILY_GLOBAL_CAP", "450"))
BULK_CAP = int(os.environ.get("VT_DAILY_BULK_CAP", "300"))
PER_CALLER_CAP = int(os.environ.get("VT_DAILY_PER_CALLER_CAP", "120"))
# Surfaces that are user-initiated chat commands keep a reserve; everything
# else (the API, checkemail, unknown) is bulk.
PRIORITY_SURFACES = {"telegram", "whatsapp", "discord"}
CACHE_TTL_CLEAN_S = 6 * 3600
CACHE_TTL_FLAGGED_S = 24 * 3600
MAPPING_TTL_S = 2 * 3600

_dynamodb = None


def _table():
    global _dynamodb
    if _dynamodb is None:
        import boto3
        _dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    return _dynamodb.Table(TABLE)


def _day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def caller_id(api_key: str) -> str:
    """Eight hex characters of a hash. Enough to tell callers apart in a log."""
    return hashlib.sha256((api_key or "").encode()).hexdigest()[:8] if api_key else "-"


def _add(table, key: str, ttl_s: int) -> int:
    resp = table.update_item(
        Key={"usage_key": key},
        UpdateExpression="ADD call_count :one SET expires_at = if_not_exists(expires_at, :ttl)",
        ExpressionAttributeValues={":one": 1, ":ttl": int(time.time()) + ttl_s},
        ReturnValues="UPDATED_NEW",
    )
    return int(resp["Attributes"]["call_count"])


def charge(surface: str, kind: str = "call", caller: str = "-") -> bool:
    """Spend one VT request. False means do NOT call VirusTotal."""
    surface = (surface or "api")[:24]
    d = _day()
    try:
        t = _table()
        if caller and caller != "-":
            n = _add(t, f"vtk#{d}#{caller}", 3 * 86400)
            if n > PER_CALLER_CAP:
                logger.warning("vt_refused reason=per-caller surface=%s kind=%s caller=%s n=%d",
                               surface, kind, caller, n)
                return False
        if surface not in PRIORITY_SURFACES:
            n = _add(t, f"vtb#{d}", 3 * 86400)
            if n > BULK_CAP:
                logger.warning("vt_refused reason=bulk surface=%s kind=%s caller=%s n=%d",
                               surface, kind, caller, n)
                return False
        total = _add(t, f"vtg#{d}", 3 * 86400)
        if total > GLOBAL_CAP:
            logger.warning("vt_refused reason=global surface=%s kind=%s caller=%s n=%d",
                           surface, kind, caller, total)
            return False
        logger.info("vt_call surface=%s kind=%s caller=%s global=%d", surface, kind, caller, total)
        return True
    except Exception as exc:
        logger.warning("vt_budget unavailable, allowing the call: %s", exc)
        return True


def _read(key: str, must_have: str):
    """Conditional UpdateItem read. (found, attributes, error)."""
    try:
        resp = _table().update_item(
            Key={"usage_key": key},
            UpdateExpression="SET last_read = :t",
            ConditionExpression=f"attribute_exists({must_have})",
            ExpressionAttributeValues={":t": int(time.time())},
            ReturnValues="ALL_NEW",
        )
        return True, resp.get("Attributes") or {}, False
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        if code == "ConditionalCheckFailedException":
            return False, {}, False
        logger.warning("vt_budget read failed: %s", exc)
        return False, {}, True


def mapping_put(analysis_id: str, url_hash: str) -> None:
    try:
        _table().update_item(
            Key={"usage_key": f"vtm#{analysis_id}"},
            UpdateExpression="SET url_hash = :h, expires_at = :ttl",
            ExpressionAttributeValues={":h": url_hash or "-", ":ttl": int(time.time()) + MAPPING_TTL_S},
        )
    except Exception as exc:
        logger.warning("vt_budget mapping write failed: %s", exc)


def mapping_check(analysis_id: str):
    """('yes'|'no'|'error', url_hash). 'error' means the table could not be read,
    and the caller must NOT treat that as 'no'."""
    found, attrs, err = _read(f"vtm#{analysis_id}", "url_hash")
    if err:
        return "error", ""
    return ("yes" if found else "no"), str(attrs.get("url_hash") or "")


def _plain(v):
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    try:
        from decimal import Decimal
        if isinstance(v, Decimal):
            return int(v)
    except Exception:
        pass
    return v


def cache_get(url_hash: str):
    found, attrs, _ = _read(f"vtc#{url_hash}", "stats")
    return _plain(dict(attrs["stats"])) if found and attrs.get("stats") is not None else None


def cache_put(url_hash: str, stats: dict) -> None:
    flagged = int(stats.get("malicious") or 0) + int(stats.get("suspicious") or 0) > 0
    ttl = CACHE_TTL_FLAGGED_S if flagged else CACHE_TTL_CLEAN_S
    try:
        _table().update_item(
            Key={"usage_key": f"vtc#{url_hash}"},
            UpdateExpression="SET stats = :s, expires_at = :ttl",
            ExpressionAttributeValues={":s": {k: int(v) for k, v in stats.items() if isinstance(v, (int, float))},
                                       ":ttl": int(time.time()) + ttl},
        )
    except Exception as exc:
        logger.warning("vt_budget cache write failed: %s", exc)
