"""Quarantined community reports ("Report this") for the consumer bots.

A user who just scanned something can report it as a missed scam. The report
lands in a QUARANTINE table, never in the curated corpus
(`relayshield_intel_iocs`). Promotion to the corpus happens only through an
explicit human review gate, and only on independent corroboration or a match
to existing corpus evidence.

Design invariants (all enforced in code, not just documented):

1. QUARANTINE ONLY. `submit_report()` writes to `relayshield_report_quarantine`
   and nothing else. The corpus table is touched only by `approve_report()`,
   the admin review gate -- and even there, the promoted record is capped at
   "unverified" confidence, strictly below curated "observed" TI. This is the
   confidence-decay principle from relayshield_intel_pivot.py applied to
   community input: a community report is a weaker seed than anything we
   collected first-hand, so nothing derived from it may sit at or above the
   curated levels.

2. PROVENANCE. Every report carries a hashed reporter id (never a raw phone
   number or raw Telegram id), the channel, a timestamp, the reported
   indicator, the verdict shown at report time, and an optional note.

3. NO AUTO-PROMOTION. Report counts alone never move anything into the
   corpus. Status flows quarantined -> suggested -> approved/rejected.
   "suggested" may be reached by corroboration weight, but "approved" --
   the only transition that writes to the corpus -- requires an explicit
   admin call.

4. ABUSE CONTROLS. Per-reporter rate limits, account-age weighting, a
   reporter reputation score that decays on rejected reports, and poisoner
   suppression: low-reputation reporters don't count toward corroboration,
   and burst reports from brand-new accounts on one indicator are flagged
   as sybil-suspect and down-weighted to zero.

5. DEMAND-SIDE SIGNAL ONLY. `community_report_count()` is surfaced in scan
   output as a clearly labeled user-report count ("reported by N users --
   community reports, not verified threat intelligence"). It never changes
   a verdict level.

6. DARK BY DEFAULT. Everything is behind the COMMUNITY_REPORTS_ENABLED env
   var (default off). When off, submit_report() refuses and the bots show
   no report affordance.

Pure logic at the top, DynamoDB persistence at the bottom. boto3 is imported
lazily so the rules are importable and testable with no AWS credentials --
pass a fake table object to the persistence functions in tests.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from datetime import datetime, timezone
from decimal import Decimal

logger = logging.getLogger()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPORT_QUARANTINE_TABLE = os.environ.get(
    "REPORT_QUARANTINE_TABLE", "relayshield_report_quarantine"
)
INTEL_IOCS_TABLE = os.environ.get("INTEL_IOCS_TABLE", "relayshield_intel_iocs")

# Domain separation for reporter hashing. Not a secret -- it only stops a
# quarantine-table reader from joining reporter_hash back to a user id with
# an unsalted guess.
REPORT_HASH_SALT = os.environ.get("REPORT_HASH_SALT", "relayshield-community-v1")


def reports_enabled() -> bool:
    """Feature flag. Default off -- the feature ships dark."""
    return os.environ.get("COMMUNITY_REPORTS_ENABLED", "false").strip().lower() in (
        "1", "true", "yes", "on",
    )


# ---------------------------------------------------------------------------
# Status lifecycle and confidence
# ---------------------------------------------------------------------------

STATUS_QUARANTINED = "quarantined"
STATUS_SUGGESTED   = "suggested"
STATUS_APPROVED    = "approved"
STATUS_REJECTED    = "rejected"

# Confidence ladder, extending relayshield_intel_pivot.CONFIDENCE_RANK.
# "community" sits BELOW "unverified" (rank 0): a user report is weaker than
# even our uncorroborated regex extractions. Anything promoted into the corpus
# through the review gate is capped at PROMOTED_CONFIDENCE_CAP, still strictly
# below curated "observed" (rank 3).
COMMUNITY_CONFIDENCE = "community"
PROMOTED_CONFIDENCE_CAP = "unverified"

try:
    from relayshield_intel_pivot import CONFIDENCE_RANK as _PIVOT_RANK
    CONFIDENCE_RANK = {**_PIVOT_RANK, COMMUNITY_CONFIDENCE: -1}
except Exception:  # pragma: no cover - module must stay importable standalone
    CONFIDENCE_RANK = {
        "community": -1,
        "unverified": 0,
        "weak": 1,
        "derived": 2,
        "observed": 3,
        "confirmed": 4,
    }


def community_confidence_below_corpus() -> bool:
    """Invariant check: community confidence is strictly below every curated
    corpus level (unverified and above)."""
    community_rank = CONFIDENCE_RANK[COMMUNITY_CONFIDENCE]
    return all(community_rank < rank for level, rank in CONFIDENCE_RANK.items()
               if level != COMMUNITY_CONFIDENCE)


# ---------------------------------------------------------------------------
# Abuse-control tuning
# ---------------------------------------------------------------------------

MAX_REPORTS_PER_WINDOW = 10       # per reporter per window
RATE_WINDOW_SECONDS  = 24 * 3600

REPUTATION_START   = 0.5
REPUTATION_MIN     = 0.05
REPUTATION_APPROVE_BUMP = 0.15
REPUTATION_REJECT_DECAY = 0.7    # multiply on each rejected report

# Below this reputation a reporter is "low trust": their reports are still
# accepted (poisoning by omission is worse than noise we can see), but they
# contribute zero corroboration weight.
LOW_TRUST_REPUTATION = 0.2

# Corroboration: sum of distinct-reporter weights that moves an indicator
# from quarantined to suggested (review queue, NOT the corpus).
SUGGEST_WEIGHT_THRESHOLD = 2.0

# Sybil burst: this many reports on one indicator from accounts younger than
# this, inside this window, flags the cluster as sybil-suspect (weight zero).
SYBIL_BURST_COUNT      = 5
SYBIL_MAX_ACCOUNT_AGE_DAYS = 1.0
SYBIL_WINDOW_SECONDS   = 3600

NOTE_MAX_CHARS = 280
QUARANTINE_TTL_DAYS = 365


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ReportsDisabled(Exception):
    """Raised when the feature flag is off."""


class ReportRefused(Exception):
    """Raised when a report or a review transition violates the rules."""


class RateLimited(Exception):
    """Raised when a reporter exceeds the per-window report budget."""


# ---------------------------------------------------------------------------
# Indicator classification and normalisation
# ---------------------------------------------------------------------------

_RE_URL    = re.compile(r"^https?://", re.IGNORECASE)
_RE_DOMAIN = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")
_RE_ETH    = re.compile(r"^0x[0-9a-fA-F]{40}$")
_RE_BTC    = re.compile(r"^(bc1|[13])[a-zA-Z0-9]{25,62}$")
_RE_SOL    = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_RE_PHONE  = re.compile(r"^\+?[1-9]\d{6,14}$")

INDICATOR_TYPES = ("url", "domain", "wallet", "phone", "message")


def classify_indicator(raw: str) -> str:
    """Best-effort type for a reported value. Anything that is not clearly a
    URL, domain, wallet or phone is treated as message text (stored as a
    hash, never raw)."""
    v = (raw or "").strip()
    if not v:
        return "message"
    compact = re.sub(r"\s+", "", v)
    if _RE_URL.match(compact):
        return "url"
    if _RE_ETH.match(compact) or _RE_BTC.match(compact) or _RE_SOL.match(compact):
        return "wallet"
    if _RE_PHONE.match(compact):
        return "phone"
    if _RE_DOMAIN.match(compact.lower()) and " " not in v:
        return "domain"
    return "message"


def normalize_indicator(raw: str, indicator_type: str | None = None) -> tuple[str, str, str]:
    """Return (indicator_type, indicator_key, stored_value).

    indicator_key is the quarantine partition key suffix: values that should
    group together share a key. Message text is NEVER stored raw -- the key
    and the stored value are both the sha256 of the normalised text.
    """
    v = (raw or "").strip()
    itype = indicator_type or classify_indicator(v)
    if itype not in INDICATOR_TYPES:
        raise ReportRefused(f"unknown indicator type {indicator_type!r}")

    if itype == "url":
        norm = re.sub(r"\s+", "", v).lower()
        norm = re.sub(r"/+$", "", norm)
        return itype, f"url#{norm}", norm
    if itype == "domain":
        norm = re.sub(r"\s+", "", v).lower().rstrip(".")
        return itype, f"domain#{norm}", norm
    if itype == "wallet":
        norm = re.sub(r"\s+", "", v)
        norm = norm.lower() if norm.startswith("0x") else norm
        return itype, f"wallet#{norm}", norm
    if itype == "phone":
        norm = re.sub(r"[\s\-().]", "", v)
        if not norm.startswith("+"):
            norm = "+" + norm
        return itype, f"phone#{norm}", norm
    # message: hash only, never raw text
    digest = hashlib.sha256(v.encode("utf-8")).hexdigest()
    return itype, f"msg#{digest}", digest


def hash_reporter(channel: str, user_id: str) -> str:
    """One-way reporter id. The raw phone number / Telegram id never lands
    in the quarantine table."""
    channel = (channel or "").strip().lower()
    if channel not in ("tg", "wa"):
        raise ReportRefused(f"unknown channel {channel!r}")
    if not user_id:
        raise ReportRefused("reporter user_id is required")
    return hashlib.sha256(
        f"{REPORT_HASH_SALT}:{channel}:{user_id}".encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# Reporter profiles: rate limit, reputation, account age
# ---------------------------------------------------------------------------

def new_reporter_profile(reporter_hash: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    iso = now.isoformat()
    return {
        "pk": f"REPORTER#{reporter_hash}",
        "sk": "PROFILE",
        "reporter_hash": reporter_hash,
        "first_seen": iso,
        "window_start": iso,
        "window_count": 0,
        "reports_total": 0,
        "reports_approved": 0,
        "reports_rejected": 0,
        "reputation": REPUTATION_START,
    }


def check_rate_limit(profile: dict, now: datetime | None = None) -> dict:
    """Return the profile with its window rolled forward if expired. Raises
    RateLimited when the reporter is over budget."""
    now = now or datetime.now(timezone.utc)
    profile = dict(profile)
    window_start = datetime.fromisoformat(profile["window_start"])
    if (now - window_start).total_seconds() >= RATE_WINDOW_SECONDS:
        profile["window_start"] = now.isoformat()
        profile["window_count"] = 0
    if int(profile["window_count"]) >= MAX_REPORTS_PER_WINDOW:
        raise RateLimited(
            f"report budget exhausted ({MAX_REPORTS_PER_WINDOW} per 24h)"
        )
    profile["window_count"] = int(profile["window_count"]) + 1
    profile["reports_total"] = int(profile.get("reports_total", 0)) + 1
    return profile


def reporter_weight(profile: dict, now: datetime | None = None) -> float:
    """Corroboration weight: reputation scaled by account age. New accounts
    count for little; low-trust (poisoner-suppressed) accounts count for
    nothing."""
    now = now or datetime.now(timezone.utc)
    reputation = float(profile.get("reputation", REPUTATION_START))
    if reputation < LOW_TRUST_REPUTATION:
        return 0.0
    first_seen = datetime.fromisoformat(profile["first_seen"])
    age_days = max(0.0, (now - first_seen).total_seconds() / 86400.0)
    age_factor = 0.25 + 0.75 * min(1.0, age_days / 30.0)
    return round(reputation * age_factor, 4)


def apply_review_outcome(profile: dict, approved: bool) -> dict:
    """Reputation update after a human review decision. Rejections decay the
    score multiplicatively, so a run of false reports sinks a poisoner fast;
    approvals nudge it back up slowly."""
    profile = dict(profile)
    rep = float(profile.get("reputation", REPUTATION_START))
    if approved:
        rep = min(1.0, rep + REPUTATION_APPROVE_BUMP)
        profile["reports_approved"] = int(profile.get("reports_approved", 0)) + 1
    else:
        rep = max(REPUTATION_MIN, rep * REPUTATION_REJECT_DECAY)
        profile["reports_rejected"] = int(profile.get("reports_rejected", 0)) + 1
    profile["reputation"] = round(rep, 4)
    return profile


# ---------------------------------------------------------------------------
# Corroboration
# ---------------------------------------------------------------------------

def corroboration_summary(
    reports: list[dict],
    profiles: dict[str, dict],
    now: datetime | None = None,
) -> dict:
    """Independent-corroboration state for one indicator.

    Only reports still in the pipeline (quarantined/suggested) count;
    rejected reports never corroborate. Weights are per distinct reporter.
    A sybil burst -- many brand-new accounts piling onto one indicator inside
    an hour -- is flagged and those reporters weigh zero.
    """
    now = now or datetime.now(timezone.utc)
    live = [r for r in reports
            if r.get("status") in (STATUS_QUARANTINED, STATUS_SUGGESTED)]

    by_reporter: dict[str, dict] = {}
    for r in live:
        by_reporter.setdefault(r["reporter_hash"], r)

    # Sybil-burst detection: distinct fresh reporters, one indicator, one hour.
    fresh_ts = [
        datetime.fromisoformat(by_reporter[h]["reported_at"]).timestamp()
        for h in by_reporter
        if (now - datetime.fromisoformat(
                profiles.get(h, {}).get("first_seen", now.isoformat()))
            ).total_seconds() / 86400.0 <= SYBIL_MAX_ACCOUNT_AGE_DAYS
    ]
    burst = False
    if len(fresh_ts) >= SYBIL_BURST_COUNT:
        fresh_ts.sort()
        for i in range(len(fresh_ts) - SYBIL_BURST_COUNT + 1):
            if fresh_ts[i + SYBIL_BURST_COUNT - 1] - fresh_ts[i] <= SYBIL_WINDOW_SECONDS:
                burst = True
                break

    weights = {}
    for h in by_reporter:
        prof = profiles.get(h)
        if prof is None:
            weights[h] = 0.0
            continue
        age_days = (now - datetime.fromisoformat(prof["first_seen"])).total_seconds() / 86400.0
        if burst and age_days <= SYBIL_MAX_ACCOUNT_AGE_DAYS:
            weights[h] = 0.0  # sybil-suspect cluster: down-weighted to zero
        else:
            weights[h] = reporter_weight(prof, now)

    total_weight = round(sum(weights.values()), 4)
    return {
        "distinct_reporters": len(by_reporter),
        "report_count": len(live),
        "total_weight": total_weight,
        "sybil_suspect": burst,
        "eligible_for_suggest": total_weight >= SUGGEST_WEIGHT_THRESHOLD,
    }


# ---------------------------------------------------------------------------
# Report construction
# ---------------------------------------------------------------------------

def build_report(
    indicator: str,
    channel: str,
    user_id: str,
    verdict_at_report: str,
    indicator_type: str | None = None,
    note: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Build the quarantine record. Never touches the corpus -- that is the
    whole point of this module."""
    if not reports_enabled():
        raise ReportsDisabled("community reports are disabled")
    now = now or datetime.now(timezone.utc)
    itype, indicator_key, stored = normalize_indicator(indicator, indicator_type)
    reporter_hash = hash_reporter(channel, user_id)
    ts = now.isoformat()
    clean_note = (note or "").strip()[:NOTE_MAX_CHARS]
    return {
        "pk": f"IND#{indicator_key}",
        "sk": f"RPT#{ts}#{reporter_hash[:12]}",
        "indicator_key": indicator_key,
        "indicator": stored,          # message text is a hash here, never raw
        "indicator_type": itype,
        "reporter_hash": reporter_hash,
        "channel": channel.strip().lower(),
        "reported_at": ts,
        "verdict_at_report": verdict_at_report or "unknown",
        "note": clean_note,
        "status": STATUS_QUARANTINED,
        "confidence": COMMUNITY_CONFIDENCE,  # below every curated level
        "ttl": Decimal(int(now.timestamp()) + QUARANTINE_TTL_DAYS * 86400),
    }


def demand_side_label(count: int) -> str:
    """Labeled demand-side signal for scan output. Never affects a verdict --
    callers append it as context only."""
    if count <= 0:
        return ""
    users = "user" if count == 1 else "users"
    return (
        f"\n\n👥 Reported as suspicious by {count} {users} — community reports, "
        "not verified threat intelligence."
    )


# ---------------------------------------------------------------------------
# Persistence -- boto3 imported lazily; every function accepts an injected
# `table` so tests run with no AWS at all.
# ---------------------------------------------------------------------------

def _table(name: str, table=None):
    if table is not None:
        return table
    import boto3
    return boto3.resource("dynamodb").Table(name)


def submit_report(
    indicator: str,
    channel: str,
    user_id: str,
    verdict_at_report: str,
    indicator_type: str | None = None,
    note: str | None = None,
    now: datetime | None = None,
    table=None,
) -> dict:
    """File a community report. Writes ONLY to the quarantine table.

    Raises ReportsDisabled / RateLimited / ReportRefused. Never raises on a
    DynamoDB failure -- a report write must not break a bot reply; the caller
    decides how to surface the failure.
    """
    now = now or datetime.now(timezone.utc)
    report = build_report(indicator, channel, user_id, verdict_at_report,
                          indicator_type, note, now)
    t = _table(REPORT_QUARANTINE_TABLE, table)
    try:
        # Dedupe: one live report per reporter per indicator.
        existing = get_reports_for_indicator(report["indicator_key"], table=t)
        for r in existing:
            if (r["reporter_hash"] == report["reporter_hash"]
                    and r.get("status") in (STATUS_QUARANTINED, STATUS_SUGGESTED)):
                raise ReportRefused("you have already reported this")

        prof_key = f"REPORTER#{report['reporter_hash']}"
        resp = t.get_item(Key={"pk": prof_key, "sk": "PROFILE"})
        profile = resp.get("Item") or new_reporter_profile(report["reporter_hash"], now)
        profile = check_rate_limit(profile, now)  # may raise RateLimited

        t.put_item(Item=report)
        t.put_item(Item={**profile, "pk": prof_key, "sk": "PROFILE"})
    except (ReportsDisabled, RateLimited, ReportRefused):
        raise
    except Exception as exc:
        logger.warning("Community report write failed indicator_key=%s: %s",
                       report["indicator_key"], exc)
        raise ReportRefused(f"report could not be stored: {exc}")
    return report


def get_reports_for_indicator(indicator_key: str, table=None) -> list[dict]:
    from boto3.dynamodb.conditions import Key
    t = _table(REPORT_QUARANTINE_TABLE, table)
    try:
        resp = t.query(KeyConditionExpression=Key("pk").eq(f"IND#{indicator_key}"))
        return resp.get("Items", [])
    except Exception as exc:
        logger.warning("Quarantine query failed indicator_key=%s: %s", indicator_key, exc)
        return []


def community_report_count(indicator: str, indicator_type: str | None = None,
                           table=None) -> int:
    """Demand-side signal: live (non-rejected) community reports for this
    indicator. Labeled, never verdict-affecting."""
    _, indicator_key, _ = normalize_indicator(indicator, indicator_type)
    reports = get_reports_for_indicator(indicator_key, table=table)
    return sum(1 for r in reports
               if r.get("status") in (STATUS_QUARANTINED, STATUS_SUGGESTED,
                                      STATUS_APPROVED))


def get_reporter_profile(reporter_hash: str, table=None) -> dict | None:
    t = _table(REPORT_QUARANTINE_TABLE, table)
    try:
        resp = t.get_item(Key={"pk": f"REPORTER#{reporter_hash}", "sk": "PROFILE"})
        return resp.get("Item")
    except Exception as exc:
        logger.warning("Reporter profile read failed: %s", exc)
        return None


def review_queue(status: str = STATUS_SUGGESTED, table=None,
                 limit: int = 100) -> list[dict]:
    """Admin view: reports awaiting a decision. Default is the suggested
    queue; pass STATUS_QUARANTINED to triage the raw intake."""
    from boto3.dynamodb.conditions import Attr
    t = _table(REPORT_QUARANTINE_TABLE, table)
    try:
        resp = t.scan(FilterExpression=Attr("status").eq(status), Limit=limit)
        items = resp.get("Items", [])
        items.sort(key=lambda r: r.get("reported_at", ""))
        return items
    except Exception as exc:
        logger.warning("Review queue scan failed: %s", exc)
        return []


def suggest_for_review(indicator_key: str, table=None,
                       now: datetime | None = None) -> dict:
    """Move an indicator's quarantined reports to suggested once independent
    corroboration clears the weight threshold. This only queues for human
    review -- it never writes to the corpus."""
    now = now or datetime.now(timezone.utc)
    t = _table(REPORT_QUARANTINE_TABLE, table)
    reports = get_reports_for_indicator(indicator_key, table=t)
    profiles = {}
    for r in reports:
        h = r["reporter_hash"]
        if h not in profiles:
            profiles[h] = get_reporter_profile(h, table=t) or {}
    summary = corroboration_summary(reports, profiles, now)
    if not summary["eligible_for_suggest"]:
        raise ReportRefused(
            f"insufficient independent corroboration "
            f"(weight {summary['total_weight']} < {SUGGEST_WEIGHT_THRESHOLD})"
        )
    moved = 0
    for r in reports:
        if r.get("status") == STATUS_QUARANTINED:
            r["status"] = STATUS_SUGGESTED
            r["suggested_at"] = now.isoformat()
            r["suggest_basis"] = {
                "distinct_reporters": summary["distinct_reporters"],
                "total_weight": summary["total_weight"],
                "sybil_suspect": summary["sybil_suspect"],
            }
            t.put_item(Item=r)
            moved += 1
    return {"indicator_key": indicator_key, "moved": moved, **summary}


def _corpus_lookup(indicator_key: str, iocs_table=None) -> bool:
    """Does this indicator already have corpus evidence? Used as one of the
    two promotion bases. Read-only against the curated table."""
    from boto3.dynamodb.conditions import Key
    t = _table(INTEL_IOCS_TABLE, iocs_table)
    try:
        # indicator_key is "type#value"; corpus rows key on ioc_value.
        value = indicator_key.split("#", 1)[1]
        if indicator_key.startswith("msg#"):
            return False  # message hashes never live in the corpus
        resp = t.query(KeyConditionExpression=Key("ioc_value").eq(value),
                       Limit=1)
        return bool(resp.get("Items"))
    except Exception as exc:
        logger.warning("Corpus lookup failed indicator_key=%s: %s",
                       indicator_key, exc)
        return False


def review_report(
    indicator_key: str,
    decision: str,
    reviewer: str,
    table=None,
    iocs_table=None,
    corpus_match: bool | None = None,
    now: datetime | None = None,
) -> dict:
    """THE promotion gate. Explicit human decision on one indicator's reports.

    decision is "approved" or "rejected". Approval additionally requires one
    of the two promotion bases:
      - independent corroboration (weight threshold met), or
      - a match to existing corpus evidence (corpus_match=True, or a live
        lookup when not supplied).
    On approval the corpus record is written with confidence capped at
    PROMOTED_CONFIDENCE_CAP ("unverified") -- strictly below curated
    "observed" -- and full community provenance. The quarantine rows are
    marked approved, never deleted, so the decision stays auditable.
    Reporter reputations move with the outcome.
    """
    if decision not in (STATUS_APPROVED, STATUS_REJECTED):
        raise ReportRefused(f"decision must be approved/rejected, got {decision!r}")
    if not reviewer:
        raise ReportRefused("reviewer identity is required")
    now = now or datetime.now(timezone.utc)
    t = _table(REPORT_QUARANTINE_TABLE, table)

    reports = [r for r in get_reports_for_indicator(indicator_key, table=t)
               if r.get("status") in (STATUS_QUARANTINED, STATUS_SUGGESTED)]
    if not reports:
        raise ReportRefused("no live reports for this indicator")

    profiles = {}
    for r in reports:
        h = r["reporter_hash"]
        if h not in profiles:
            profiles[h] = get_reporter_profile(h, table=t) \
                or new_reporter_profile(h, now)

    summary = corroboration_summary(reports, profiles, now)
    if corpus_match is None:
        corpus_match = _corpus_lookup(indicator_key, iocs_table)

    if decision == STATUS_APPROVED:
        if not (summary["eligible_for_suggest"] or corpus_match):
            raise ReportRefused(
                "approval requires independent corroboration or a corpus match"
            )

    decided_at = now.isoformat()
    for r in reports:
        r["status"] = decision
        r["decided_at"] = decided_at
        r["reviewer"] = reviewer
        t.put_item(Item=r)

    for h, prof in profiles.items():
        # Only reporters with a live report on this indicator move.
        if h in {r["reporter_hash"] for r in reports}:
            t.put_item(Item={**apply_review_outcome(prof, decision == STATUS_APPROVED),
                             "pk": f"REPORTER#{h}", "sk": "PROFILE"})

    corpus_written = False
    if decision == STATUS_APPROVED:
        corpus_written = _promote_to_corpus(
            indicator_key, reports, summary, corpus_match, reviewer,
            decided_at, iocs_table,
        )

    return {
        "indicator_key": indicator_key,
        "decision": decision,
        "reviewer": reviewer,
        "reports_decided": len(reports),
        "corroboration": summary,
        "corpus_match": corpus_match,
        "corpus_written": corpus_written,
    }


def _promote_to_corpus(indicator_key: str, reports: list[dict], summary: dict,
                       corpus_match: bool, reviewer: str, decided_at: str,
                       iocs_table=None) -> bool:
    """Write the single sanctioned corpus record for an approved indicator.
    Confidence is capped BELOW curated levels; provenance names the community
    origin and the reports behind it. This is the only write path from the
    quarantine system into relayshield_intel_iocs."""
    itype, _, stored = normalize_indicator(
        reports[0]["indicator"], reports[0]["indicator_type"])
    if itype == "message":
        logger.warning("Refusing corpus promotion for message-hash indicator")
        return False
    item = {
        "ioc_value": stored,
        "ioc_type": itype,
        "seen_ts": decided_at,
        # Capped: community-promoted evidence never reaches curated levels.
        "confidence": PROMOTED_CONFIDENCE_CAP,
        "source": "community_quarantine",
        "corroboration": {
            "distinct_reporters": summary["distinct_reporters"],
            "total_weight": str(summary["total_weight"]),
            "corpus_match": corpus_match,
        },
        "community_report_ids": [r["sk"] for r in reports],
        "reviewer": reviewer,
        "ttl": Decimal(int(time.time()) + QUARANTINE_TTL_DAYS * 86400),
    }
    try:
        _table(INTEL_IOCS_TABLE, iocs_table).put_item(Item=item)
        return True
    except Exception as exc:
        logger.warning("Corpus promotion write failed indicator_key=%s: %s",
                       indicator_key, exc)
        return False
