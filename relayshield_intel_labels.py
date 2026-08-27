"""Shared normalisation for the `malware` label namespace (A7).

WHY THIS EXISTS
---------------
`malware` is the hash key of the malware-index GSI, so its value is not
cosmetic: it is what a customer's hunting query matches on. Three writers
populate it independently -- relayshield_intel_monitor.py from its own curated
family regexes, relayshield_intel_feed.py from whatever the upstream feed
called it, and relayshield_intel_kev.py from CISA's vendor and product fields --
and nothing has ever agreed on a form.

Measured effect, and the reason this is a quality defect rather than tidiness:
`clearfake` returns 196 rows and `ClearFake` returns 608. A customer querying
either one silently sees a fraction of what we hold, and has no way to know it.
Roughly two thirds of the matches for that family are hidden from whichever
casing they happened to type.

Two defects, both documented in the feed data itself:

  1. Case is not normalised at source. ClearFake and clearfake are the same
     family and index as different keys.
  2. Some labels carry several comma-joined values in one string, so the whole
     string becomes one GSI key and none of its members are matchable.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
It lowercases, trims and splits. It does NOT strip spaces, hyphens or
underscores, so "agent tesla" and "agenttesla" stay distinct. Collapsing those
would be a guess about which families are the same, and a wrong guess merges
two real families into one key, which is worse than the problem being fixed and
is not reversible once written. Fixing genuine aliases is an alias-map problem,
separate from normalisation, and needs evidence per pair.
"""
from __future__ import annotations

__all__ = ["normalise_malware", "normalise_malware_query"]


def _clean_one(part: str) -> str:
    # Collapse internal whitespace runs so "agent  tesla" and "agent tesla"
    # agree, which is a formatting difference rather than a naming one.
    return " ".join(part.lower().split())


def normalise_malware(raw: str) -> str:
    """Canonical form for the `malware` attribute, ready to write.

    Comma-joined labels are split, each part normalised, blanks dropped,
    duplicates removed, and the result sorted so two writers producing the same
    set in different orders produce the same string.

    Returns "" for anything empty, and callers MUST NOT write an empty value:
    "" as a GSI hash key indexes every untagged IOC, a trap already documented
    in both _store_iocs() and relayshield_intel_feed._write_ioc().
    """
    if not raw:
        return ""
    parts = {_clean_one(p) for p in str(raw).split(",")}
    parts.discard("")
    return ",".join(sorted(parts))


def normalise_malware_query(raw: str) -> str:
    """Canonical form for a single family name being LOOKED UP.

    Queries are one family, not a list, so this never joins. Kept as its own
    function because normalising a query with the list form would turn a user
    searching "ClearFake, Lumma" into a single key that matches nothing, which
    is exactly the failure this module exists to remove.
    """
    return _clean_one(raw or "")
