"""
RelayShield Verdict Watcher
===========================

Re-screens every registered watch subject and pushes a webhook when the verdict
CHANGES. This is the delivery half of the flat-rate Verdict Watch licence; the
registration half lives in `relayshield_api.py` (`handle_watch_add` and
friends, gated on `watch_access`).

Why this exists
---------------
The freshness contract added in 2026-08 tells a caller when a verdict goes
stale, via `observed_at` / `valid_for_seconds` / `expires_at`. That is arithmetic
the caller already holds. What they cannot compute is that the answer CHANGED,
because discovering a flip costs them a re-screen. That asymmetry is the
product, so this is what gets billed as a licence rather than per call.

Two rules that matter more than the rest
----------------------------------------
1. **Never notify on a degraded result.** `degraded=true` means an upstream did
   not answer, so the finding list is unreliable. Treating that as a flip would
   page every customer during any upstream outage, and the first flip they ever
   saw would be a false one. A degraded check re-arms on the short TTL and
   changes nothing stored.
2. **Never notify on the baseline.** The first successful check on a new watch
   records the fingerprint silently. A customer registering a known-dirty
   address should not immediately be told it "changed to" dirty.

Cadence
-------
`next_check_at` is driven by the `valid_for_seconds` the API itself returns, so
the watcher re-checks exactly when the verdict it holds expires. Flagged
subjects are therefore polled rarely and clean ones often, which is the same
asymmetry the freshness contract encodes and the opposite of a fixed interval.

  - Trigger:  EventBridge, rate(15 minutes)
  - Table:    relayshield_verdict_watches  (PK api_key, SK watch_id)
  - Deploy:   SINGLE-file zip. No local imports.

Cost model, read before provisioning
------------------------------------
Re-screens run against the public API with `RELAYSHIELD_INTERNAL_API_KEY`. The
customer pays a flat licence, so WE bear the re-screen cost. That key must
therefore be provisioned as a non-billed key, otherwise every watch silently
bills someone. This is a provisioning decision, not something this file can
enforce, so it is called out here rather than assumed.
"""

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Attr

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

WATCHES_TABLE = "relayshield_verdict_watches"
API_KEYS_TABLE = "relayshield_api_keys"
API_BASE = os.environ.get("RELAYSHIELD_API_BASE", "https://api.relayshield.net")
INTERNAL_KEY = os.environ.get("RELAYSHIELD_INTERNAL_API_KEY", "")

WATCH_SUBJECT_ENDPOINTS = {
    "address": ("/v1/metered/crypto-intel", "address"),
    "email":   ("/v1/metered/breach",       "email"),
    "domain":  ("/v1/metered/domain",       "domain"),
    "phone":   ("/v1/metered/sim-swap",     "phone"),
    # Angle 2, added 2026-08-12. subject_value is one npm package name, but
    # dependency-risk takes a LIST, so _screen wraps it. See _LIST_PARAM_SUBJECTS.
    "dependency": ("/v1/metered/dependency-risk", "packages"),
}

# Subject types whose endpoint takes a list rather than a scalar. Wrapping is
# done in one place so a future list-shaped subject cannot silently POST a
# bare string and get a 400 that looks like "no findings".
_LIST_PARAM_SUBJECTS = frozenset({"dependency"})

# Safety rails. A single pass must stay well inside the Lambda timeout, and a
# runaway must not be able to hammer the upstreams.
MAX_CHECKS_PER_RUN = 200
FALLBACK_TTL_SECONDS = 3600
DEGRADED_RETRY_SECONDS = 300
HTTP_TIMEOUT = 20


def _verdict_fingerprint(subject_type: str, data: dict) -> str:
    """Canonical summary of the FINDING, never the envelope.

    Must stay byte-identical to `_verdict_fingerprint` in relayshield_api.py.
    Duplicated rather than imported because both are single-file Lambda
    deploys; if you change one, change the other.
    """
    if subject_type == "address":
        return "|".join(sorted(data.get("address_flags") or [])) or "clean"
    if subject_type == "email":
        return "|".join(sorted(b.get("name", "") for b in (data.get("breaches") or []))) or "clean"
    if subject_type == "domain":
        return "|".join(sorted(l.get("domain", "") for l in (data.get("lookalikes") or []))) or "clean"
    if subject_type == "phone":
        return "swapped" if data.get("swapped") else "clean"
    if subject_type == "dependency":
        return "|".join(sorted(
            f"{r.get('package','')}:{r.get('severity','')}"
            for r in (data.get("findings") or [])
        )) or "clean"
    return "unknown"


def _screen(subject_type: str, subject_value: str) -> dict | None:
    """Re-screen one subject via the public API. None on transport failure."""
    path, param = WATCH_SUBJECT_ENDPOINTS[subject_type]
    value = [subject_value] if subject_type in _LIST_PARAM_SUBJECTS else subject_value
    body = json.dumps({param: value}).encode()
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-RS-API-KEY": INTERNAL_KEY,
            "User-Agent": "RelayShield-VerdictWatcher/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            payload = json.loads(resp.read())
        return payload.get("data") or {}
    except urllib.error.HTTPError as exc:
        # A 503 here is the sim-swap "no carrier data" case, which is a
        # deliberate non-verdict rather than a fault. Either way: no data, so
        # no flip decision.
        logger.warning("watcher screen %s %s -> HTTP %s", subject_type, subject_value[:40], exc.code)
        return None
    except Exception as exc:
        logger.warning("watcher screen %s %s failed: %s", subject_type, subject_value[:40], exc)
        return None


def _webhook_url_for(api_key: str) -> str:
    try:
        item = dynamodb.Table(API_KEYS_TABLE).get_item(Key={"api_key": api_key}).get("Item") or {}
    except Exception as exc:
        logger.warning("watcher could not read key record: %s", exc)
        return ""
    if not item.get("watch_access"):
        # Licence lapsed. Stop notifying rather than continuing to deliver a
        # product the customer is no longer paying for.
        return ""
    return item.get("webhook_url", "") or ""


def _notify(api_key: str, watch: dict, before: str, after: str, data: dict) -> bool:
    url = _webhook_url_for(api_key)
    if not url:
        logger.info("watcher flip with no deliverable webhook key=%s id=%s",
                    api_key[:16], watch.get("watch_id"))
        return False
    payload = {
        "event":          "verdict.changed",
        "watch_id":       watch.get("watch_id"),
        "subject_type":   watch.get("subject_type"),
        "subject_value":  watch.get("subject_value"),
        "previous_verdict": before,
        "current_verdict":  after,
        "observed_at":    data.get("observed_at"),
        "expires_at":     data.get("expires_at"),
        "detail":         data,
    }
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps({"source": "relayshield", "payload": payload}).encode(),
            headers={"Content-Type": "application/json",
                     "User-Agent": "RelayShield-Webhook/1.0"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=HTTP_TIMEOUT)
        logger.info("watcher notified key=%s id=%s %s -> %s",
                    api_key[:16], watch.get("watch_id"), before, after)
        return True
    except Exception as exc:
        logger.warning("watcher webhook delivery failed url=%s: %s", url[:60], exc)
        return False


def _due_watches(now_iso: str) -> list:
    table = dynamodb.Table(WATCHES_TABLE)
    items, kwargs = [], {"FilterExpression": Attr("next_check_at").lte(now_iso)}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        if not resp.get("LastEvaluatedKey") or len(items) >= MAX_CHECKS_PER_RUN:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    # Scan is fine at current scale and deliberately simple. If watch counts
    # ever reach the thousands this wants a GSI on next_check_at instead.
    return items[:MAX_CHECKS_PER_RUN]


def lambda_handler(event, context):
    if not INTERNAL_KEY:
        logger.error("RELAYSHIELD_INTERNAL_API_KEY is unset; watcher cannot screen. Aborting.")
        return {"checked": 0, "flips": 0, "error": "missing internal key"}

    now = datetime.now(timezone.utc)
    due = _due_watches(now.isoformat())
    logger.info("watcher pass: %d watches due", len(due))

    checked = flips = degraded = baselines = 0
    table = dynamodb.Table(WATCHES_TABLE)

    for w in due:
        subject_type = w.get("subject_type")
        if subject_type not in WATCH_SUBJECT_ENDPOINTS:
            continue
        data = _screen(subject_type, w.get("subject_value", ""))
        checked += 1

        if data is None:
            # No answer at all. Re-arm soon, change nothing.
            table.update_item(
                Key={"api_key": w["api_key"], "watch_id": w["watch_id"]},
                UpdateExpression="SET next_check_at = :n",
                ExpressionAttributeValues={
                    ":n": (now + timedelta(seconds=DEGRADED_RETRY_SECONDS)).isoformat()},
            )
            degraded += 1
            continue

        if data.get("degraded"):
            # Rule 1. An incomplete answer is not a flip, and must never page.
            logger.info("watcher skipping degraded result id=%s", w.get("watch_id"))
            table.update_item(
                Key={"api_key": w["api_key"], "watch_id": w["watch_id"]},
                UpdateExpression="SET next_check_at = :n, last_checked_at = :c",
                ExpressionAttributeValues={
                    ":n": (now + timedelta(seconds=DEGRADED_RETRY_SECONDS)).isoformat(),
                    ":c": now.isoformat()},
            )
            degraded += 1
            continue

        after = _verdict_fingerprint(subject_type, data)
        before = w.get("last_fingerprint")
        ttl = int(data.get("valid_for_seconds") or FALLBACK_TTL_SECONDS)

        if before is None:
            baselines += 1  # Rule 2. Record silently.
        elif after != before:
            flips += 1
            _notify(w["api_key"], w, before, after, data)

        table.update_item(
            Key={"api_key": w["api_key"], "watch_id": w["watch_id"]},
            UpdateExpression=("SET last_fingerprint = :f, last_checked_at = :c, "
                              "next_check_at = :n"),
            ExpressionAttributeValues={
                ":f": after,
                ":c": now.isoformat(),
                # Re-check exactly when the verdict we now hold expires.
                ":n": (now + timedelta(seconds=ttl)).isoformat(),
            },
        )

    logger.info("watcher done: checked=%d flips=%d degraded=%d baselines=%d",
                checked, flips, degraded, baselines)
    return {"checked": checked, "flips": flips, "degraded": degraded, "baselines": baselines}
