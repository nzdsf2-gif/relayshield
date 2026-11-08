"""Corpus citations on flagged verdicts, context-engine item 5.

When the proxy flags a result, the verdict carries the specific
corpus citations behind the flag: which indicators matched, which
sightings, which kit family. The agent or the human reviewing the
flag can then check the evidence instead of taking the verdict on
trust. This is a presentation and evidence-completeness change, not
a new engine.

Citation fields, per Andrew's decisions 2026-11-08:
- Q7: first seen, last seen, and sighting count, plus indicator,
  indicator type, kit family, and confidence.
- Q8: citations visible to both the agent (in the verdict payload)
  and the human (in the console verdict detail). Same evidence
  fields for both, and no corpus-internal identifiers.
- Q9: cap 5 citations per flagged verdict, ordered by confidence
  highest first. When more than 5 indicators match, the verdict
  carries the top 5 and notes the total matched count.

Safety rules this module enforces:
- Citations are evidence only. Building or attaching citations
  never changes the verdict, the score, or the poison category.
- Citations appear only on flagged verdicts. A verdict with no
  flags found carries no citations.
- Citations are drawn only from the corpus record for the indicator
  matched on that call, for that tenant. No other tenant's data,
  no raw corpus internals, no collection methods, no honeypot
  internals, no raw corpus rows.
- If the citation data for a matched indicator cannot be retrieved
  at verdict time, the verdict is still issued with its reasons,
  scores, and poison categories, and the citations list is empty
  or marked unavailable. A missing citation never delays, weakens,
  or changes a verdict, and never causes a flagged call to pass.
- Citations are computed from the screening result the proxy
  already has, so a console outage does not block verdicts. This
  module takes matched-indicator records as input and never makes
  a network call.

This module is pure logic: no I/O, no network, no storage. It runs
identically on the proxy wherever a flagged verdict is issued.
"""

# Q9: maximum citations carried on one flagged verdict.
MAX_CITATIONS_PER_VERDICT = 5


class Citation:
    """One corpus citation attached to a flagged verdict.

    All fields are plain JSON values. A field the screening result
    did not carry is an empty string (for text) or 0 (for numbers),
    never a corpus-internal identifier.
    """

    def __init__(self, indicator="", indicator_type="", kit_family="",
                 confidence=0.0, first_seen="", last_seen="",
                 sighting_count=0):
        self.indicator = indicator or ""
        self.indicator_type = indicator_type or ""
        self.kit_family = kit_family or ""
        try:
            self.confidence = float(confidence or 0.0)
        except (TypeError, ValueError):
            self.confidence = 0.0
        self.first_seen = first_seen or ""
        self.last_seen = last_seen or ""
        try:
            self.sighting_count = int(sighting_count or 0)
        except (TypeError, ValueError):
            self.sighting_count = 0

    def to_dict(self):
        """Plain dict, safe to attach to a verdict and to store."""
        return {
            "indicator": self.indicator,
            "indicator_type": self.indicator_type,
            "kit_family": self.kit_family,
            "confidence": self.confidence,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "sighting_count": self.sighting_count,
        }


def _citation_from_record(record):
    """Normalize one matched-indicator record into a Citation.

    Accepts the record shapes the proxy's screening already produces:
    - bulk-ioc style: ioc_value, ioc_type, malware (kit family),
      confidence_score, first_seen, last_seen, hit_count.
    - composite-check signal style: indicator/value, type,
      kit_family/family, confidence, first_seen, last_seen,
      sighting_count/hit_count.
    - kit evidence style: kit_id, family, verdict, confidence.
    Unknown shapes yield a Citation with only the fields present;
    a record with no usable indicator value yields None and is
    skipped, never an error.
    """
    if not isinstance(record, dict):
        return None
    indicator = (
        record.get("indicator")
        or record.get("ioc_value")
        or record.get("value")
        or record.get("kit_id")
        or record.get("id")
        or ""
    )
    if not indicator:
        return None
    indicator_type = (
        record.get("indicator_type")
        or record.get("ioc_type")
        or record.get("type")
        or ""
    )
    kit_family = (
        record.get("kit_family")
        or record.get("family")
        or record.get("malware")
        or record.get("threat_actor")
        or ""
    )
    confidence = (
        record.get("confidence")
        if record.get("confidence") is not None
        else record.get("confidence_score", 0.0)
    )
    sighting_count = (
        record.get("sighting_count")
        if record.get("sighting_count") is not None
        else record.get("hit_count", 0)
    )
    return Citation(
        indicator=str(indicator),
        indicator_type=str(indicator_type or ""),
        kit_family=str(kit_family or ""),
        confidence=confidence,
        first_seen=record.get("first_seen", "") or "",
        last_seen=record.get("last_seen", "") or "",
        sighting_count=sighting_count,
    )


def build_citations(matched_indicators, limit=MAX_CITATIONS_PER_VERDICT):
    """Build the citations list for one flagged verdict.

    matched_indicators: a list of matched-indicator records from the
    screening result the proxy already has (see _citation_from_record
    for the accepted shapes). Records that cannot be normalized are
    skipped, never an error.

    Returns (citations, total_matched) where citations is a list of
    citation dicts, at most `limit` entries, ordered by confidence
    highest first (Q9), and total_matched is the number of
    indicators that produced a citation before the cap, so the
    verdict can note how many more matched. When matched_indicators
    is empty or None, returns ([], 0): the verdict is still issued,
    with an empty citations list.

    This function never raises on bad input. A failure to build
    citations must never delay, weaken, or change a verdict.
    """
    if not matched_indicators:
        return [], 0
    try:
        records = list(matched_indicators)
    except TypeError:
        return [], 0
    citations = []
    for record in records:
        try:
            citation = _citation_from_record(record)
        except Exception:
            continue
        if citation is not None:
            citations.append(citation)
    total_matched = len(citations)
    citations.sort(key=lambda c: c.confidence, reverse=True)
    capped = citations[:limit] if limit and limit > 0 else citations
    return [c.to_dict() for c in capped], total_matched


def citations_for_verdict(verdict_decision, matched_indicators,
                          limit=MAX_CITATIONS_PER_VERDICT):
    """Decide what citations, if any, a verdict carries.

    verdict_decision: the verdict's decision string ("block",
    "quarantine", "flag", "allow"). Citations attach only to a
    flagged verdict: decision "flag", "block", or "quarantine".
    An "allow" verdict, or any verdict with no flags found, carries
    no citations, because there is nothing to cite.

    Returns a dict: {"citations": [...], "citations_total_matched": n,
    "citations_available": bool}. citations_available is False when
    the verdict is flagged but no citation data could be built, so
    the verdict can mark the citations unavailable without changing
    the verdict itself.
    """
    flagged = verdict_decision in ("flag", "block", "quarantine")
    if not flagged:
        return {
            "citations": [],
            "citations_total_matched": 0,
            "citations_available": False,
        }
    citations, total_matched = build_citations(matched_indicators, limit)
    return {
        "citations": citations,
        "citations_total_matched": total_matched,
        "citations_available": bool(citations),
    }
