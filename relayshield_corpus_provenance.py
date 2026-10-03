"""Corpus cross-correlation for verdicts.

Turns a bare risk level into an evidence line like::

    Seen in 3 criminal marketplaces · linked to 2 wallets · kit family milk-dragon

Shared by the API Lambda (POST /v1/composite-check) and the Telegram /
WhatsApp webhook Lambdas. Best-effort everywhere: every public function
degrades to empty/None on any error and never raises.

Data sources (verified against origin/main 2026-10-02):
- ``relayshield_intel_iocs`` -- the TI corpus sightings table, keyed
  (ioc_value HASH, seen_ts RANGE), one row per sighting (~11.9 sightings per
  distinct indicator). Rows carry ``channel`` (marketplace/source name),
  ``malware`` (comma-joined family labels), ``ioc_type``, and ``kit_family``
  when the pipeline attributed one.
- Wallet linkage reuses the pivot approach of ``handle_ioc_pivot`` in
  relayshield_api.py: indicators sharing the seed's exact ``malware`` value
  are related; related rows whose ioc_type is wallet-like count as linked
  wallets.

What this module does NOT do: kit families live in
``relayshield_kit_fingerprints`` keyed by fingerprint_id (kit_<sha256>)
with no reverse index by URL, so a URL is only reported with a kit family
when a sighting row already carries one. Nothing here invents a linkage.
"""

import logging

logger = logging.getLogger(__name__)

INTEL_IOCS_TABLE = "relayshield_intel_iocs"

_SIGHTINGS_LIMIT = 50
_PIVOT_LIMIT = 100
_MARKET_NAME_CAP = 3
_FAMILY_NAME_CAP = 2

_WALLET_IOC_TYPES = frozenset({
    "wallet", "address", "crypto_address", "evm", "bitcoin", "btc", "eth",
})

_PLACEHOLDER_FAMILIES = frozenset({"none", "n/a", "unknown", "null", ""})


def _dynamodb_table():
    import boto3
    return boto3.resource("dynamodb").Table(INTEL_IOCS_TABLE)


def _family_labels(items):
    """Family labels from IOC rows' comma-joined malware field.

    Mirrors _ioc_malware_labels in relayshield_api.py (split commas, drop
    placeholders, de-duplicate case-insensitively). Pure: never raises.
    """
    fams = []
    seen = set()
    for item in items or []:
        raw = (item or {}).get("malware", "")
        vals = raw if isinstance(raw, list) else str(raw or "").split(",")
        for val in vals:
            val = str(val).strip()
            if val.lower() in _PLACEHOLDER_FAMILIES:
                continue
            key = val.lower()
            if key in seen:
                continue
            seen.add(key)
            fams.append(val[:50])
    return sorted(fams, key=str.lower)


def corpus_provenance_summary(indicator, indicator_type=None):
    """Cross-correlate one indicator against the corpus sightings table.

    Returns a dict with sightings_count, markets_seen_count, market_names
    (capped at 3), linked_wallets_count, kit_families, malware_families and a
    human ``summary`` one-liner (None when the corpus knows nothing about
    the indicator). Never raises; any DynamoDB failure degrades to the
    empty result.
    """
    result = {
        "indicator": (indicator or "").strip(),
        "indicator_type": indicator_type or None,
        "sightings_count": 0,
        "markets_seen_count": 0,
        "market_names": [],
        "linked_wallets_count": 0,
        "kit_families": [],
        "malware_families": [],
        "summary": None,
    }
    norm = (indicator or "").strip().lower()
    if not norm:
        return result
    try:
        from boto3.dynamodb.conditions import Key, Attr
        table = _dynamodb_table()
        resp = table.query(
            KeyConditionExpression=Key("ioc_value").eq(norm),
            ProjectionExpression="ioc_type, seen_ts, malware, channel, kit_family",
            Limit=_SIGHTINGS_LIMIT,
        )
        items = resp.get("Items", []) or []
    except Exception as exc:
        logger.warning("corpus provenance sightings query failed: %s", exc)
        return result
    if not items:
        return result

    result["sightings_count"] = len(items)
    channels = sorted({
        str(i.get("channel", "")).strip()
        for i in items
        if str(i.get("channel", "")).strip()
    })
    result["markets_seen_count"] = len(channels)
    result["market_names"] = channels[:_MARKET_NAME_CAP]
    result["malware_families"] = _family_labels(items)
    result["kit_families"] = sorted({
        str(i.get("kit_family", "")).strip()
        for i in items
        if str(i.get("kit_family", "")).strip()
    })

    # Wallet linkage: pivot on the seed's exact malware value, the same
    # approach as handle_ioc_pivot (related IOCs share the malware family).
    seed_malware = next(
        (str(i.get("malware", "")).strip() for i in items
         if str(i.get("malware", "")).strip()),
        "",
    )
    if seed_malware:
        try:
            scan_resp = table.scan(
                FilterExpression=Attr("malware").eq(seed_malware)
                & Attr("ioc_value").ne(norm),
                ProjectionExpression="ioc_value, ioc_type",
                Limit=_PIVOT_LIMIT,
            )
            wallets = {
                str(r.get("ioc_value", "")).strip()
                for r in scan_resp.get("Items", []) or []
                if str(r.get("ioc_type", "")).strip().lower() in _WALLET_IOC_TYPES
                and str(r.get("ioc_value", "")).strip()
            }
            result["linked_wallets_count"] = len(wallets)
        except Exception as exc:
            logger.warning("corpus provenance wallet pivot failed: %s", exc)

    result["summary"] = provenance_one_liner(result)
    return result


def provenance_one_liner(prov):
    """Human one-liner for a provenance dict, e.g.::

        Seen in 3 criminal marketplaces (a, b, c) · linked to 2 wallets ·
        kit family milk-dragon

    Returns None when there is nothing to say. Pure: never raises.
    """
    try:
        parts = []
        n = int(prov.get("markets_seen_count") or 0)
        if n > 0:
            names = list(prov.get("market_names") or [])
            if names:
                shown = ", ".join(names)
                extra = " +%d more" % (n - len(names)) if n > len(names) else ""
                parts.append("Seen in %d criminal marketplace%s (%s%s)"
                             % (n, "" if n == 1 else "s", shown, extra))
            else:
                parts.append("Seen in %d criminal marketplace%s"
                             % (n, "" if n == 1 else "s"))
        w = int(prov.get("linked_wallets_count") or 0)
        if w > 0:
            parts.append("linked to %d wallet%s" % (w, "" if w == 1 else "s"))
        kit_fams = [f for f in list(prov.get("kit_families") or [])
                    [:_FAMILY_NAME_CAP]
                    if str(f).strip().lower() not in _PLACEHOLDER_FAMILIES]
        mal_fams = [f for f in list(prov.get("malware_families") or [])
                    [:_FAMILY_NAME_CAP]
                    if f not in kit_fams
                    and str(f).strip().lower() not in _PLACEHOLDER_FAMILIES]
        for fam in kit_fams:
            parts.append("kit family %s" % fam)
        for fam in mal_fams:
            parts.append("malware family %s" % fam)
        return " · ".join(parts) or None
    except Exception:
        return None
