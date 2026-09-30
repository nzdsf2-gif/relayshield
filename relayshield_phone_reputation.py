"""Phone-number reputation: is this number criminal infrastructure, and was it just SIM-swapped?

Outside-in counterpart to the SIM-swap monitor (which watches numbers you
already know). This assesses a STRANGER's number — a caller, a smishing
sender — fusing criminal-corpus evidence with SIM-swap state into one verdict.

Tiers:
  keyed   (POST /v1/payg/phone-reputation, /v1/metered/phone-reputation):
      corpus sightings + attack-graph paths + Twilio Lookup v2 sim_swap +
      line_type_intelligence. Twilio results are cached ~24h per number so
      repeats don't re-burn the ~$0.01 lookup.
  keyless (POST /v1/phone-reputation):
      corpus + attack-graph ONLY. This module enforces the boundary
      structurally: the keyless path never receives Twilio credentials and
      never calls the lookup. See assess_phone_reputation().

Verdict ceiling is "unknown" — never "low", never "safe". An absence of flags
across these sources is not proof of safety.
"""

import base64
import json
import logging
import time
import urllib.request

from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Reuse the canonical E.164 helpers — one regex for the whole repo. Lazy so this
# module stays importable with zero AWS credentials (boto3 comes along with
# relayshield_sim_swap_consent).
def _consent():
    import relayshield_sim_swap_consent as simswap_consent

    return simswap_consent

INTEL_IOCS_TABLE = "relayshield_intel_iocs"
CACHE_TABLE = "relayshield_phone_reputation_cache"  # DEPLOY-TIME: create on-demand, pk=phone
CACHE_TTL_SECONDS = 24 * 3600
TWILIO_LOOKUP_URL = "https://lookups.twilio.com/v2/PhoneNumbers/{phone}"

PHONE_REPUTATION_NOTE = (
    "Phone reputation from RelayShield's criminal IOC corpus, attack-graph "
    "pivots, and (keyed tier) Twilio Lookup v2 SIM-swap and line-type "
    "intelligence. An absence of flags is not proof of safety."
)

# Line types that are cheap burner infrastructure, not real subscribers.
RISKY_LINE_TYPES = frozenset({"voip", "premium"})

# Confidence decay per attack-graph hop. Strictly decreasing: a derived
# finding is never as strong as its seed (the pivot module's invariant).
_HOP_DECAY = 0.8


class BadPhone(ValueError):
    """The supplied phone number is not usable E.164."""


class LookupUnavailable(Exception):
    """Twilio/carrier gave no SIM-swap answer. Never rendered as clean."""


def validate_phone(phone: str) -> str:
    """Normalise to E.164 or raise BadPhone. Strict: garbage gets a 4xx."""
    simswap_consent = _consent()
    raw = (phone or "").strip()
    # Tolerate common human formatting, then demand strict E.164.
    candidate = simswap_consent.normalise_e164(raw).replace("-", "").replace("(", "").replace(")", "")
    if not candidate.startswith("+"):
        candidate = "+" + candidate.lstrip("+")
    candidate = simswap_consent.normalise_e164(candidate)
    if not simswap_consent.is_valid_e164(candidate):
        raise BadPhone(
            "phone is required in E.164 format (e.g. +14155551234)"
        )
    return candidate


def _dynamodb():
    import boto3  # lazy: importable with zero AWS credentials for tests

    return boto3.resource("dynamodb")


def query_corpus_sightings(phone: str, table=None) -> dict:
    """Sightings of this number in the criminal IOC corpus.

    Returns {"count", "most_recent", "items": [{channel, malware, category,
    seen_ts, ioc_type}]}. Never raises: a corpus outage degrades to zero
    sightings, which the verdict treats as unknown, not clean — the count is
    what it is, and the reason strings say what was actually checked.
    """
    items = []
    try:
        from boto3.dynamodb.conditions import Key

        t = table if table is not None else _dynamodb().Table(INTEL_IOCS_TABLE)
        resp = t.query(
            KeyConditionExpression=Key("ioc_value").eq(phone),
            ScanIndexForward=False,  # newest seen_ts first
            Limit=25,
        )
        for it in resp.get("Items", []):
            items.append({
                "channel":  it.get("channel", ""),
                "malware":  it.get("malware", ""),
                "category": it.get("category", ""),
                "seen_ts":  it.get("seen_ts", ""),
                "ioc_type": it.get("ioc_type", ""),
            })
    except Exception as exc:
        logger.warning("phone-reputation corpus query failed: %s", exc)
    most_recent = items[0]["seen_ts"] if items else ""
    return {"count": len(items), "most_recent": most_recent, "items": items}


def _decay_confidence(hops: int) -> float:
    return round(_HOP_DECAY ** max(1, hops), 3)


def attack_paths(phone: str, seed_items: list, table=None) -> list:
    """Attack-graph paths from this number through the corpus.

    Pivots on the seed sighting's malware family (same shape as
    handle_ioc_pivot): number -> marketplace post (ts) -> related wallet /
    domain / kit. Each hop decays confidence — a derived finding is never as
    strong as its seed.
    """
    paths = []
    if not seed_items:
        return paths
    try:
        from boto3.dynamodb.conditions import Attr

        t = table if table is not None else _dynamodb().Table(INTEL_IOCS_TABLE)
        seen_families = set()
        for seed in seed_items[:5]:
            malware = (seed.get("malware") or "").strip()
            if not malware or malware in seen_families:
                continue
            seen_families.add(malware)
            try:
                scan_resp = t.scan(
                    FilterExpression=(
                        Attr("malware").eq(malware)
                        & Attr("ioc_value").ne(phone)
                    ),
                    Limit=200,
                )
            except Exception as exc:
                logger.warning("phone-reputation pivot scan failed: %s", exc)
                continue
            related = scan_resp.get("Items", [])
            # Keep the strongest, most recent neighbours — a phone book, not a dump.
            related.sort(key=lambda r: r.get("seen_ts", ""), reverse=True)
            for rel in related[:5]:
                rel_value = str(rel.get("ioc_value", ""))
                rel_type = rel.get("ioc_type", "") or "indicator"
                # Redact wallet-length values in the path label: the shape of
                # the connection matters, not the full address in a reason string.
                label = rel_value if len(rel_value) <= 20 else rel_value[:10] + "…"
                paths.append({
                    "path": [
                        f"number {phone}",
                        f"marketplace post ({(seed.get('seen_ts') or '')[:10]})",
                        f"{rel_type} {label} ({(rel.get('seen_ts') or '')[:10]})",
                    ],
                    "via": "malware_family",
                    "malware": malware,
                    "confidence": _decay_confidence(2),
                })
    except Exception as exc:
        logger.warning("phone-reputation attack paths failed: %s", exc)
    return paths


class ReputationCache:
    """~24h Twilio lookup cache. DynamoDB when the table exists, in-memory
    otherwise. A missing table degrades to memory-only — the verdict never
    fails because the cache is absent."""

    def __init__(self, table=None):
        self._table = table
        self._memory: dict = {}

    def _ddb_table(self):
        if self._table is not None:
            return self._table
        try:
            return _dynamodb().Table(CACHE_TABLE)
        except Exception:
            return None

    def get(self, phone: str):
        now = int(time.time())
        mem = self._memory.get(phone)
        if mem and mem["expires_at"] > now:
            return mem["value"]
        t = self._ddb_table()
        if t is None:
            return None
        try:
            item = t.get_item(Key={"phone": phone}).get("Item") or {}
            if item.get("expires_at", 0) > now:
                return item.get("value")
        except Exception as exc:
            logger.warning("phone-reputation cache read failed: %s", exc)
        return None

    def set(self, phone: str, value: dict):
        expires_at = int(time.time()) + CACHE_TTL_SECONDS
        self._memory[phone] = {"value": value, "expires_at": expires_at}
        t = self._ddb_table()
        if t is None:
            return
        try:
            t.put_item(Item={"phone": phone, "value": value,
                             "expires_at": expires_at})
        except Exception as exc:
            logger.warning("phone-reputation cache write failed: %s", exc)


def twilio_lookup(phone: str, account_sid: str, auth_token: str,
                  cache: ReputationCache | None = None) -> dict:
    """Twilio Lookup v2: sim_swap + line_type_intelligence.

    KEYED TIER ONLY — the keyless path never calls this (it never receives
    credentials). Results are cached ~24h per number so repeats don't re-burn
    the ~$0.01 lookup.

    Raises LookupUnavailable when the carrier gives no answer. That is NOT a
    clean result: callers must render it as unchecked, never as safe.
    """
    if cache is None:
        cache = ReputationCache()
    cached = cache.get(phone)
    if cached is not None:
        return cached

    import urllib.parse

    encoded = urllib.parse.quote(phone, safe="")
    url = TWILIO_LOOKUP_URL.format(phone=encoded) + "?Fields=sim_swap,line_type_intelligence"
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Basic {credentials}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
    except Exception as exc:
        raise LookupUnavailable(f"Twilio lookup failed: {exc}")

    sim_swap_obj = body.get("sim_swap") or {}
    lti = body.get("line_type_intelligence") or {}

    # Twilio answers 200 with a per-package error_code when the package is
    # unavailable. Reading that as "not swapped" turns "we have no idea" into
    # "you are fine" on a security product. Refuse instead.
    pkg_error = sim_swap_obj.get("error_code")
    if pkg_error:
        raise LookupUnavailable(
            f"SIM swap data unavailable from the carrier (code {pkg_error})"
        )

    last_swap = sim_swap_obj.get("last_sim_swap") or {}
    result = {
        "swapped": bool(last_swap.get("swapped_in_period", False)),
        "last_change": last_swap.get("last_sim_swap_date", "") or "",
        "line_type": (lti.get("line_type") or "").lower(),
        "carrier": lti.get("carrier_name") or sim_swap_obj.get("carrier_name", ""),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    cache.set(phone, result)
    return result


def _ts_date(ts: str) -> str:
    return (ts or "")[:10]


def assess_phone_reputation(phone: str, *, keyless: bool,
                            twilio_creds: tuple | None = None,
                            ioc_table=None,
                            cache: ReputationCache | None = None) -> dict:
    """The composite verdict. Pure orchestration over the signal functions.

    keyless=True: corpus + attack-graph only. The Twilio lookup is not merely
    skipped — this branch never receives credentials, so the lookup is
    unreachable, not just unused. Tests assert this with a raising mock.
    """
    target = validate_phone(phone)

    sightings = query_corpus_sightings(target, table=ioc_table)
    paths = attack_paths(target, sightings["items"], table=ioc_table)

    reasons: list[str] = []
    signals: dict = {
        "corpus_sightings": {
            "count": sightings["count"],
            "most_recent": sightings["most_recent"],
        },
        "attack_paths": paths,
    }

    corpus_hit = sightings["count"] > 0 or bool(paths)
    if sightings["count"] > 0:
        mr = _ts_date(sightings["most_recent"])
        reasons.append(
            f"seen in {sightings['count']} criminal marketplace "
            f"post{'s' if sightings['count'] != 1 else ''}"
            + (f" (most recent {mr})" if mr else "")
        )
    for p in paths[:3]:
        step_str = " → ".join(p["path"])
        reasons.append(
            f"attack-graph path (confidence {p['confidence']}): {step_str}"
        )

    if keyless:
        # STRUCTURAL: no creds in, no lookup out. The keyless tier is
        # corpus + attack-graph, and the response says so plainly.
        signals["sim_swap"] = {"checked": False, "reason": "keyless tier"}
        signals["line_type"] = {"checked": False, "reason": "keyless tier"}
    else:
        lk = None
        if twilio_creds:
            try:
                lk = twilio_lookup(target, twilio_creds[0], twilio_creds[1],
                                   cache=cache)
            except LookupUnavailable as exc:
                # No carrier answer is not a clean bill of health.
                signals["sim_swap"] = {"checked": False, "reason": str(exc)}
                signals["line_type"] = {"checked": False, "reason": str(exc)}
        else:
            # Keyed tier, but Twilio is not configured on this deployment.
            # The corpus verdict still stands; the Twilio halves report
            # unchecked, never clean.
            signals["sim_swap"] = {"checked": False,
                                   "reason": "Twilio lookup not configured"}
            signals["line_type"] = {"checked": False,
                                    "reason": "Twilio lookup not configured"}
        if lk is not None:
            signals["sim_swap"] = {
                "checked": True,
                "swapped": lk["swapped"],
                "last_change": lk["last_change"],
                "carrier": lk["carrier"],
            }
            signals["line_type"] = {
                "checked": True,
                "line_type": lk["line_type"] or "unknown",
            }
            if lk["swapped"]:
                lc = _ts_date(lk["last_change"])
                reasons.append(
                    "SIM/eSIM changed"
                    + (f" on {lc}" if lc else " recently")
                    + " — a number that changed hands just before it called you "
                      "is a classic takeover pattern"
                )
            if (lk["line_type"] or "") in RISKY_LINE_TYPES:
                reasons.append(
                    f"line type: {lk['line_type']} — cheap burner "
                    "infrastructure; a real bank or agency does not call from one"
                )

    # Verdict grading. Corpus/attack-graph evidence is blocklist-grade: high.
    # A SIM swap or burner line-type alone warns; it never convicts.
    # Nothing: unknown. The ceiling is honesty, never "safe".
    if corpus_hit:
        level, flagged = "high", True
    elif any("SIM/eSIM changed" in r for r in reasons) or any(
        r.startswith("line type:") for r in reasons
    ):
        level, flagged = "medium", True
    else:
        level, flagged = "unknown", False

    return {
        "target": target,
        "level": level,
        "flagged": flagged,
        "reasons": reasons,
        "signals": signals,
        "note": PHONE_REPUTATION_NOTE,
    }
