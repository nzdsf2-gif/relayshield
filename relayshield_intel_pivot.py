"""INTEL corpus growth: pivot enrichment, and re-checking unknowns on a delay.

Implements the two items from `intel_corpus_growth_plan.md` that grow the
*exclusive* share of the corpus rather than its headline size.

1. PIVOT ENRICHMENT -- turn one collected indicator into a cluster.
   A drainer wallet has counterparties; a scam domain has certificate-transparency
   and passive-DNS siblings. Those derived indicators are ours by derivation, not
   ingested from a feed, so they inherit the exclusivity of their seed.

   The plan is blunt about the risk and so is this module: a pivot without
   confidence decay produces a large volume of weakly-associated indicators,
   which is precisely what makes a technical buyer distrust the whole corpus.
   So the invariant here is not advisory:

       A derived indicator's confidence is STRICTLY BELOW its seed's,
       and it always carries the path it was derived by.

   `derive_confidence()` cannot return the seed's own level, and
   `make_derived_ioc()` refuses to build a record without a seed and a method.

2. RE-CHECK UNKNOWNS ON A DELAY -- prove we saw it first.
   Every consumer-bot /scan submission is logged with its verdict. The ones that
   came back `unknown` are re-checked at 24h, 72h and 7d. A link that was clean
   on Monday and is flagged everywhere by Friday *was an exclusive indicator on
   Monday*, and the ledger holds the timestamps that prove it.

   That lead time is a far better claim than corpus size, because it is
   falsifiable: `lead_time_summary()` reports the measured distribution and the
   sample it rests on, never a round number.

Pure logic at the top, DynamoDB persistence at the bottom. Nothing here touches
AWS at import time, so the decision rules are testable without credentials.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

logger = logging.getLogger()

SCAN_LEDGER_TABLE = os.environ.get("SCAN_LEDGER_TABLE", "relayshield_scan_ledger")
INTEL_IOCS_TABLE  = os.environ.get("INTEL_IOCS_TABLE", "relayshield_intel_iocs")

LEDGER_TTL_DAYS = 90


# ---------------------------------------------------------------------------
# Confidence ladder
# ---------------------------------------------------------------------------
# Ordered, and the order is the whole point -- every rule below is expressed as
# a comparison on these ranks rather than a string test, so a new level slots in
# without revisiting the logic.
#
# "observed" is what _store_iocs in relayshield_intel_monitor.py writes today:
# pulled directly out of a monitored channel message. "unverified" is what the
# victim-name sweep writes: regex-extracted and never corroborated.
CONFIDENCE_RANK: dict[str, int] = {
    "unverified": 0,   # regex-extracted, no corroboration
    "weak":       1,   # two or more pivot hops from an observed seed
    "derived":    2,   # one pivot hop from an observed seed
    "observed":   3,   # collected first-hand from a monitored source
    "confirmed":  4,   # corroborated malicious
}
RANK_CONFIDENCE: dict[int, str] = {v: k for k, v in CONFIDENCE_RANK.items()}

# A seed below this rank cannot be pivoted from. Deriving off an unconfirmed
# regex hit is exactly the "flood the corpus with weak associations" failure the
# plan warns about, so the honest answer is to refuse rather than invent a
# confidence for it.
#
# This also caps cluster depth without a separate depth limit: observed -> derived
# -> weak, and `weak` sits below the bar, so a chain stops at two hops. Anything
# further from the one thing actually observed is not worth the corpus noise.
MIN_PIVOTABLE_RANK = CONFIDENCE_RANK["derived"]

# Recognised pivots. Naming them explicitly keeps an ad-hoc string out of the
# derivation path, which is the field a buyer would audit.
PIVOT_METHODS = {
    "wallet_counterparty": "transaction counterparty of a collected wallet",
    "ct_sibling":          "certificate-transparency sibling of a collected domain",
    "pdns_sibling":        "passive-DNS sibling of a collected domain",
}


class PivotRefused(Exception):
    """Raised when a pivot would violate the confidence or provenance rules."""


def derive_confidence(seed_confidence: str) -> str:
    """One rank below `seed_confidence`. Never equal to it, never above.

    Decay is measured against the IMMEDIATE seed, not the root, because the
    immediate seed has already decayed itself -- applying a hop-count-sized drop
    on top of that double-counts and sends a two-hop pivot straight to the floor.
    Chaining single steps is what keeps the ladder monotonic.

    There is deliberately no floor-and-return: at `unverified` there is no
    honest level left to sit at, so this raises rather than handing back a
    confidence equal to the seed's.
    """
    seed_rank = CONFIDENCE_RANK.get(seed_confidence)
    if seed_rank is None:
        raise PivotRefused(f"unknown seed confidence {seed_confidence!r}")
    if seed_rank <= 0:
        raise PivotRefused(
            f"cannot derive from {seed_confidence!r} -- no confidence level below it"
        )
    return RANK_CONFIDENCE[seed_rank - 1]


def make_derived_ioc(
    seed: dict,
    value: str,
    ioc_type: str,
    method: str,
    now: datetime | None = None,
) -> dict:
    """Build a derived IOC record carrying its full derivation path.

    `seed` is the collected indicator this was pivoted from, in the shape
    _store_iocs writes. Raises PivotRefused rather than silently producing a
    record that would overstate what we know.
    """
    if method not in PIVOT_METHODS:
        raise PivotRefused(f"unrecognised pivot method {method!r}")
    value = (value or "").strip().lower()
    if not value:
        raise PivotRefused("derived indicator has no value")

    seed_value = (seed.get("ioc_value") or "").strip().lower()
    if not seed_value:
        raise PivotRefused("pivot requires a seed indicator")
    if value == seed_value:
        raise PivotRefused("a pivot cannot derive an indicator from itself")

    # Collected IOCs predate the confidence field; absent means first-hand.
    seed_confidence = seed.get("confidence") or "observed"
    seed_rank = CONFIDENCE_RANK.get(seed_confidence)
    if seed_rank is None:
        raise PivotRefused(f"unknown seed confidence {seed_confidence!r}")
    if seed_rank < MIN_PIVOTABLE_RANK:
        raise PivotRefused(
            f"refusing to pivot from a {seed_confidence!r} seed -- "
            "a derived indicator would have no honest confidence to sit at"
        )

    hops = int(seed.get("derivation_hops") or 0) + 1
    now = now or datetime.now(timezone.utc)

    return {
        "ioc_value":       value,
        "seen_ts":         now.isoformat(),
        "ioc_type":        ioc_type,
        "confidence":      derive_confidence(seed_confidence),
        # Provenance. `derived_from` is the immediate seed; `derivation_root` is
        # the original collected indicator, so a cluster can be traced back to
        # the one thing that was actually observed however deep it goes.
        "derived_from":    seed_value,
        "derivation":      method,
        "derivation_hops": hops,
        "derivation_root": seed.get("derivation_root") or seed_value,
        # Carried so a derived indicator can still be attributed to the surface
        # its seed came from, which is what makes it exclusive.
        "channel":         seed.get("channel", ""),
        "category":        seed.get("category", ""),
    }


# ---------------------------------------------------------------------------
# Re-check ledger
# ---------------------------------------------------------------------------
# Hours after submission at which an `unknown` verdict is re-checked. Three
# stages, widening: most flips happen early, and a 7-day tail catches the
# campaigns that stage their infrastructure before using it.
RECHECK_SCHEDULE_HOURS = (24, 72, 168)

VERDICT_UNKNOWN = "unknown"
VERDICT_FLAGGED = "flagged"
VERDICT_CLEAN   = "clean"


def _next_recheck_ts(stage: int, base: datetime) -> str | None:
    """ISO timestamp of the next re-check, or None once the schedule is spent."""
    if stage >= len(RECHECK_SCHEDULE_HOURS):
        return None
    return (base + timedelta(hours=RECHECK_SCHEDULE_HOURS[stage])).isoformat()


def log_submission(
    target: str,
    surface: str,
    verdict: str,
    now: datetime | None = None,
) -> dict:
    """Ledger record for one consumer-bot /scan submission.

    Only `unknown` verdicts get a re-check schedule. A flagged verdict is
    already known, and a clean one is a judgement we made rather than an absence
    of signal -- re-checking either would measure nothing about our lead time.
    """
    target = (target or "").strip().lower()
    if not target:
        raise ValueError("submission has no target")
    now = now or datetime.now(timezone.utc)

    item = {
        "target":        target,
        "submitted_ts":  now.isoformat(),
        "surface":       surface,
        "verdict":       verdict,
        # The claim rests on this field, so it is written once at submission and
        # never recomputed on a later pass.
        "first_seen_by_us": now.isoformat(),
        "recheck_stage": 0,
        "ttl":           Decimal(int(time.time()) + LEDGER_TTL_DAYS * 86400),
    }
    if verdict == VERDICT_UNKNOWN:
        item["next_recheck_ts"] = _next_recheck_ts(0, now)
    return item


def is_due_for_recheck(item: dict, now: datetime | None = None) -> bool:
    """True when this ledger row is an unknown whose next re-check has come due."""
    if item.get("verdict") != VERDICT_UNKNOWN:
        return False
    nxt = item.get("next_recheck_ts")
    if not nxt:
        return False
    now = now or datetime.now(timezone.utc)
    return str(nxt) <= now.isoformat()


def apply_recheck(item: dict, new_verdict: str, now: datetime | None = None) -> dict:
    """Fold a re-check result into a ledger row.

    A flip from unknown to flagged is the event the whole mechanism exists to
    capture: it stamps when the rest of the world caught up and how many hours
    we were ahead. Everything else just advances the schedule.
    """
    now = now or datetime.now(timezone.utc)
    updated = dict(item)
    stage = int(item.get("recheck_stage") or 0) + 1
    updated["recheck_stage"] = stage
    updated["last_recheck_ts"] = now.isoformat()

    if new_verdict == VERDICT_FLAGGED:
        updated["verdict"] = VERDICT_FLAGGED
        updated["first_flagged_ts"] = now.isoformat()
        first_seen = _parse_ts(item.get("first_seen_by_us") or item.get("submitted_ts"))
        if first_seen is not None:
            delta_h = (now - first_seen).total_seconds() / 3600.0
            # Clamp at zero: clock skew between the bot and the re-check job must
            # never manufacture a negative -- or a flattering -- lead time.
            updated["lead_time_hours"] = round(max(0.0, delta_h), 2)
        updated.pop("next_recheck_ts", None)
        return updated

    # Still unknown. Advance to the next stage, or retire the row when the
    # schedule is spent -- an indicator nobody flagged in 7 days is not evidence
    # of a lead, and leaving it due forever would re-check it indefinitely.
    nxt = _next_recheck_ts(stage, _parse_ts(item.get("submitted_ts")) or now)
    if nxt:
        updated["next_recheck_ts"] = nxt
    else:
        updated.pop("next_recheck_ts", None)
        updated["recheck_exhausted"] = True
    return updated


def _parse_ts(raw) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def lead_time_summary(items: list[dict]) -> dict:
    """Measured lead-time distribution over ledger rows that flipped to flagged.

    Reports the sample it rests on, deliberately. The claim this supports is
    "we saw N of these first, by a median of H hours" -- which is checkable --
    and not a headline corpus number, which is not.
    """
    leads = sorted(
        float(i["lead_time_hours"])
        for i in items
        if i.get("verdict") == VERDICT_FLAGGED and i.get("lead_time_hours") is not None
    )
    submitted = len(items)
    unknowns = sum(1 for i in items if i.get("verdict") == VERDICT_UNKNOWN)

    if not leads:
        return {
            "submissions":     submitted,
            "still_unknown":   unknowns,
            "flipped_to_flagged": 0,
            "median_lead_hours": None,
            "note": "no unknown submission has been flagged elsewhere yet",
        }

    mid = len(leads) // 2
    median = leads[mid] if len(leads) % 2 else (leads[mid - 1] + leads[mid]) / 2
    return {
        "submissions":        submitted,
        "still_unknown":      unknowns,
        "flipped_to_flagged": len(leads),
        "median_lead_hours":  round(median, 2),
        "min_lead_hours":     round(leads[0], 2),
        "max_lead_hours":     round(leads[-1], 2),
        # The share of submissions this rests on. A median over 3 rows and a
        # median over 3,000 are not the same claim, and the reader is entitled
        # to tell them apart without asking.
        "sample_share":       round(len(leads) / submitted, 4) if submitted else 0.0,
    }


# ---------------------------------------------------------------------------
# Persistence -- boto3 is imported lazily so the logic above stays importable
# (and testable) in an environment with no AWS at all.
# ---------------------------------------------------------------------------

def _table(name: str):
    import boto3
    return boto3.resource("dynamodb").Table(name)


def store_derived_iocs(records: list[dict]) -> int:
    """Persist derived indicators. Returns the number written."""
    if not records:
        return 0
    table = _table(INTEL_IOCS_TABLE)
    ttl = Decimal(int(time.time()) + 180 * 86400)
    written = 0
    for rec in records:
        try:
            table.put_item(Item={**rec, "ttl": ttl})
            written += 1
        except Exception as exc:
            logger.warning("Derived IOC store failed value=%s: %s",
                           str(rec.get("ioc_value", ""))[:32], exc)
    return written


def record_submission(target: str, surface: str, verdict: str) -> bool:
    """Log one /scan submission. Never raises -- a ledger write must not break a scan."""
    try:
        _table(SCAN_LEDGER_TABLE).put_item(Item=log_submission(target, surface, verdict))
        return True
    except Exception as exc:
        logger.warning("Scan ledger write failed target=%s: %s", str(target)[:48], exc)
        return False


def due_rechecks(limit: int = 500, now: datetime | None = None) -> list[dict]:
    """Ledger rows whose next re-check has come due."""
    now = now or datetime.now(timezone.utc)
    try:
        import boto3
        resp = _table(SCAN_LEDGER_TABLE).scan(
            FilterExpression=(
                boto3.dynamodb.conditions.Attr("verdict").eq(VERDICT_UNKNOWN) &
                boto3.dynamodb.conditions.Attr("next_recheck_ts").lte(now.isoformat())
            ),
            Limit=limit,
        )
        return resp.get("Items", [])
    except Exception as exc:
        logger.warning("Due-recheck scan failed: %s", exc)
        return []
