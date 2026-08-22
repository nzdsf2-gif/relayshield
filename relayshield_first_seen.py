"""First-seen tracking: turn consumer bot /scan traffic into a collection surface.

GROWTH PLAN ITEM 4, and the reason it ranks so highly: /scan submissions across
Telegram, WhatsApp and Discord are real victims pasting real attacks in real
time — typically before the domain reaches any public feed. That is the
freshest possible signal and it is exclusive by construction, because nobody
else has our inbox.

THE MECHANISM, WHICH IS THE WHOLE POINT
---------------------------------------
Logging submissions alone proves nothing. The value comes from the second half:

  1. Someone submits a URL or address. We record it with the verdict we gave.
  2. A submission that came back UNKNOWN (no known flags) is queued.
  3. Days later we re-check it. If it is now flagged — by us, or by a public
     feed we ingest — then on the day it was submitted it was an indicator that
     existed in no feed, and we had it.

That gap is measurable, dated, and provable. It is a far better outreach claim
than corpus size, which is the claim that nearly went out to the
blockchain-analytics segment and would have failed on first inspection.

WHAT IS DELIBERATELY NOT STORED
-------------------------------
No user id, no chat id, no phone number, no email. The submitted VALUE and the
verdict, nothing else. A first-seen corpus is a research asset; a log of who
asked about what is a liability, and the two are separable at no cost.

Submitted values are hashed into the partition key so an identical URL from two
users is one row, not two.
"""

import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SUBMISSIONS_TABLE = "relayshield_scan_submissions"
REGION            = "us-east-1"

# How long before an unknown is worth re-checking. Under a day is too soon for
# a feed to have caught up; past three weeks the claim stops being interesting
# because "we saw it 21 days early" invites the question of why we did nothing.
RECHECK_AFTER_HOURS = int(os.environ.get("FIRST_SEEN_RECHECK_HOURS", "72"))
RECHECK_MAX_AGE_DAYS = int(os.environ.get("FIRST_SEEN_MAX_AGE_DAYS", "21"))
RECHECK_BATCH        = int(os.environ.get("FIRST_SEEN_BATCH", "150"))
SUBMISSION_TTL_DAYS  = int(os.environ.get("FIRST_SEEN_TTL_DAYS", "180"))

API_BASE     = os.environ.get("RS_API_BASE", "https://api.relayshield.net")
API_KEY_ENV  = "RS_INTERNAL_API_KEY"

_dynamodb = boto3.resource("dynamodb", region_name=REGION)


def _value_key(value: str) -> str:
    """Stable partition key. Hashed so the table cannot be read as a list of
    what individual people submitted, and so an over-long URL still keys."""
    return hashlib.sha256(value.strip().lower().encode("utf-8", "replace")).hexdigest()


def log_submission(value: str, kind: str, verdict: str, source: str) -> None:
    """Record one /scan submission. NEVER RAISES.

    Called from a user-facing request path, so a failure here must be invisible
    to the person who scanned something. A lost row costs one data point; a
    raised exception costs the user their answer.

    kind:    "url" | "wallet"
    verdict: "flagged" | "unknown"   (anything else is ignored)
    source:  "telegram" | "whatsapp" | "discord" | "api"
    """
    try:
        if not value or verdict not in ("flagged", "unknown"):
            return
        now = datetime.now(timezone.utc)
        table = _dynamodb.Table(SUBMISSIONS_TABLE)
        table.update_item(
            Key={"value_key": _value_key(value), "kind": kind},
            UpdateExpression=(
                "SET #v = :val, first_submitted = if_not_exists(first_submitted, :now), "
                "    last_submitted = :now, first_verdict = if_not_exists(first_verdict, :verdict), "
                "    #ttl = :ttl, sources = :src "
                "ADD submission_count :one"
            ),
            ExpressionAttributeNames={"#v": "value", "#ttl": "ttl"},
            ExpressionAttributeValues={
                ":val":     value[:2048],
                ":now":     now.isoformat(),
                # first_verdict is written once and never updated. It is the
                # claim: what we said on the day it was submitted. Overwriting
                # it later would destroy the only thing this table proves.
                ":verdict": verdict,
                ":one":     Decimal(1),
                ":src":     {source},
                ":ttl":     Decimal(int(time.time()) + SUBMISSION_TTL_DAYS * 86400),
            },
        )
    except Exception as exc:
        logger.warning("Submission log failed kind=%s: %s", kind, exc)


def _recheck_value(value: str, kind: str, api_key: str) -> str | None:
    """Ask our own API what it thinks now. Returns "flagged"/"unknown"/None."""
    path = "/v1/scan-url" if kind == "url" else "/v1/wallet-risk"
    body = {"url": value} if kind == "url" else {"address": value}
    try:
        req = urllib.request.Request(
            f"{API_BASE}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "X-RS-API-KEY": api_key},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read()).get("data", {})
    except Exception as exc:
        logger.warning("Recheck failed kind=%s: %s", kind, exc)
        return None

    if kind == "url":
        level = str(data.get("level", "")).lower()
        return "flagged" if level in ("malicious", "suspicious", "flagged") else "unknown"
    return "flagged" if data.get("flagged") or data.get("risk_level") in ("HIGH", "CRITICAL") else "unknown"


def recheck_pending() -> dict:
    """Re-check unknowns that are old enough, and record any that turned.

    A row that flips unknown -> flagged is the asset: on `first_submitted` it
    was an indicator in no feed, and it was in our inbox.
    """
    api_key = os.environ.get(API_KEY_ENV, "")
    if not api_key:
        logger.error("%s not set — cannot re-check", API_KEY_ENV)
        return {"error": "no_api_key"}

    now    = datetime.now(timezone.utc)
    oldest = (now - timedelta(days=RECHECK_MAX_AGE_DAYS)).isoformat()
    ripe   = (now - timedelta(hours=RECHECK_AFTER_HOURS)).isoformat()
    table  = _dynamodb.Table(SUBMISSIONS_TABLE)

    flt = (
        boto3.dynamodb.conditions.Attr("first_verdict").eq("unknown")
        & boto3.dynamodb.conditions.Attr("rechecked_at").not_exists()
        & boto3.dynamodb.conditions.Attr("first_submitted").lt(ripe)
        & boto3.dynamodb.conditions.Attr("first_submitted").gt(oldest)
    )
    try:
        resp  = table.scan(FilterExpression=flt, Limit=RECHECK_BATCH * 4)
        items = resp.get("Items", [])[:RECHECK_BATCH]
    except Exception as exc:
        logger.exception("Recheck scan failed: %s", exc)
        return {"error": str(exc)}

    stats = {"checked": 0, "turned": 0, "still_unknown": 0, "errors": 0}
    for item in items:
        value, kind = item.get("value"), item.get("kind")
        if not value or not kind:
            continue
        verdict = _recheck_value(value, kind, api_key)
        if verdict is None:
            stats["errors"] += 1
            continue
        stats["checked"] += 1

        update = {
            "rechecked_at":    now.isoformat(),
            "recheck_verdict": verdict,
        }
        if verdict == "flagged":
            stats["turned"] += 1
            # The provable claim, computed once and stored, so nobody has to
            # re-derive it from two timestamps later.
            try:
                first = datetime.fromisoformat(str(item["first_submitted"]))
                update["lead_time_hours"] = Decimal(int((now - first).total_seconds() // 3600))
            except Exception:
                pass
            update["saw_it_first"] = True
            logger.info("FIRST-SEEN CONFIRMED kind=%s lead=%sh",
                        kind, update.get("lead_time_hours", "?"))
        else:
            stats["still_unknown"] += 1

        try:
            table.update_item(
                Key={"value_key": item["value_key"], "kind": kind},
                UpdateExpression="SET " + ", ".join(f"#{i} = :{i}" for i in range(len(update))),
                ExpressionAttributeNames={f"#{i}": k for i, k in enumerate(update)},
                ExpressionAttributeValues={f":{i}": v for i, v in enumerate(update.values())},
            )
        except Exception as exc:
            logger.warning("Recheck write failed: %s", exc)
        time.sleep(0.1)

    logger.info("Recheck complete: %s", stats)
    return stats


def lambda_handler(event, context):
    # CI import probe — return before doing any work or spending any API calls.
    if isinstance(event, dict) and event.get("source") == "ci.import-probe":
        return {"statusCode": 200, "skipped": "ci.import-probe"}
    return {"statusCode": 200, **recheck_pending()}
