"""Tests for relayshield_phone_reputation (no AWS, no network — all faked).

Covers:
  - E.164 validation rejects garbage (BadPhone)
  - keyed full verdict shapes: high on corpus hit, medium on SIM-swap-only,
    medium on VoIP-only, unknown on clean
  - keyless NEVER invokes the Twilio lookup (raising mock asserts unreachability)
  - 24h Twilio cache: second lookup for the same number hits no HTTP
  - verdict ceiling is unknown — the words "low"/"safe" never appear
  - attack-graph reasons carry timestamps and decayed (< 1.0) confidence
"""

import io
import json
import re
import sys
import time
import types
import urllib.request

import pytest

# relayshield_sim_swap_consent creates boto3 clients at import time (fine on
# Lambda, fatal in a hermetic test). Stub it with byte-identical E.164
# semantics before importing the module under test.
_consent_stub = types.ModuleType("relayshield_sim_swap_consent")
_consent_stub.E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def _stub_normalise(phone: str) -> str:
    return (phone or "").strip().replace("whatsapp:", "").replace(" ", "")


_consent_stub.normalise_e164 = _stub_normalise
_consent_stub.is_valid_e164 = lambda phone: bool(
    _consent_stub.E164_RE.match(_stub_normalise(phone)))
sys.modules["relayshield_sim_swap_consent"] = _consent_stub

sys.path.insert(0, "/home/hatch/workspace/builds/relayshield")

import relayshield_phone_reputation as pr


def _install_conditions_stub():
    """Pin a working boto3.dynamodb.conditions for these tests.

    test_sim_swap_monitor.py installs a minimal conditions stub into
    sys.modules at import time whose Attr supports only .eq() (no & or .ne()).
    This module resolves conditions lazily, so without this fixture a combined
    pytest run would pick up their stub and attack_paths would silently
    degrade. Production always has real boto3; this only affects tests.
    """
    conditions = types.ModuleType("boto3.dynamodb.conditions")

    class _Expr:
        def __init__(self, text):
            self.text = text

        def __and__(self, other):
            return _Expr(f"({self.text} AND {other.text})")

    class _Field:
        def __init__(self, name):
            self.name = name

        def eq(self, v):
            return _Expr(f"{self.name} == {v!r}")

        def ne(self, v):
            return _Expr(f"{self.name} != {v!r}")

    conditions.Key = _Field
    conditions.Attr = _Field
    sys.modules["boto3.dynamodb.conditions"] = conditions


@pytest.fixture(autouse=True)
def _conditions_stub():
    _install_conditions_stub()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeIocTable:
    """Stand-in for the relayshield_intel_iocs DynamoDB table."""

    def __init__(self, query_items=None, scan_items=None):
        self.query_items = query_items or []
        self.scan_items = scan_items or []

    def query(self, **kwargs):
        return {"Items": self.query_items}

    def scan(self, **kwargs):
        return {"Items": self.scan_items}


class FakeCacheTable:
    """Stand-in for the relayshield_phone_reputation_cache DynamoDB table."""

    def __init__(self):
        self.store = {}

    def get_item(self, Key):
        return {"Item": self.store.get(Key["phone"], {})}

    def put_item(self, Item):
        self.store[Item["phone"]] = Item


class FakeHttpResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _twilio_body(swapped=False, last_change="", line_type="mobile",
                 carrier="Test Carrier", error_code=None):
    sim_swap = {"error_code": error_code} if error_code else {
        "last_sim_swap": {
            "swapped_in_period": swapped,
            "last_sim_swap_date": last_change,
        },
        "carrier_name": carrier,
    }
    return {
        "sim_swap": sim_swap,
        "line_type_intelligence": {
            "line_type": line_type,
            "carrier_name": carrier,
        },
    }


def _patch_urlopen(monkeypatch, body: dict, counter: dict):
    def fake_urlopen(req, timeout=15):
        counter["n"] += 1
        return FakeHttpResponse(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


SIGHTING = {
    "channel": "carding-central",
    "malware": "pig-butchering-kit",
    "category": "smishing",
    "seen_ts": "2026-09-28T14:02:11+00:00",
    "ioc_type": "phone",
}


# ---------------------------------------------------------------------------
# E.164 validation
# ---------------------------------------------------------------------------

def test_validate_accepts_e164():
    assert pr.validate_phone("+15551234567") == "+15551234567"


def test_validate_tolerates_human_formatting():
    assert pr.validate_phone("  +1 (555) 123-4567 ") == "+15551234567"


@pytest.mark.parametrize("bad", [
    "", "   ", "abc", "call me", "+", "+0", "+0123456789",
    "++15551234567", "+1555", "+1" + "2" * 20,  # too long
    "not a number at all",
])
def test_validate_rejects_garbage(bad):
    with pytest.raises(pr.BadPhone):
        pr.validate_phone(bad)


def test_assess_rejects_garbage_with_badphone():
    with pytest.raises(pr.BadPhone):
        pr.assess_phone_reputation("definitely not a phone", keyless=True)


# ---------------------------------------------------------------------------
# Keyed verdict shapes
# ---------------------------------------------------------------------------

def _keyed(phone="+15551234567", query_items=None, scan_items=None,
           twilio=None, cache=None):
    table = FakeIocTable(query_items=query_items, scan_items=scan_items)
    return pr.assess_phone_reputation(
        phone,
        keyless=False,
        twilio_creds=("sid", "token"),
        ioc_table=table,
        cache=cache,
    )


def test_keyed_high_on_corpus_hit(monkeypatch):
    counter = {"n": 0}
    _patch_urlopen(monkeypatch,
                   _twilio_body(swapped=False, line_type="mobile"),
                   counter)
    out = _keyed(query_items=[SIGHTING,
                              {**SIGHTING, "seen_ts": "2026-09-20T09:00:00+00:00"}],
                 scan_items=[])
    assert out["target"] == "+15551234567"
    assert out["level"] == "high"
    assert out["flagged"] is True
    assert any("seen in 2 criminal marketplace posts" in r for r in out["reasons"])
    assert any("2026-09-28" in r for r in out["reasons"])  # recency timestamp
    assert out["signals"]["corpus_sightings"]["count"] == 2
    assert out["signals"]["corpus_sightings"]["most_recent"].startswith("2026-09-28")
    assert out["signals"]["sim_swap"]["checked"] is True  # keyed: Twilio ran
    blob = json.dumps(out).lower().replace("not proof of safety", "")
    assert not re.search(r"\bsafe\b", blob)
    assert '"low"' not in blob


def test_keyed_medium_on_sim_swap_only(monkeypatch):
    counter = {"n": 0}
    _patch_urlopen(monkeypatch,
                   _twilio_body(swapped=True,
                                last_change="2026-09-28T10:00:00+00:00",
                                line_type="mobile"),
                   counter)
    out = _keyed(query_items=[], scan_items=[])
    assert out["level"] == "medium"
    assert out["flagged"] is True
    assert any("SIM/eSIM changed" in r and "2026-09-28" in r
               for r in out["reasons"])
    assert out["signals"]["sim_swap"]["swapped"] is True


def test_keyed_medium_on_voip_only(monkeypatch):
    counter = {"n": 0}
    _patch_urlopen(monkeypatch,
                   _twilio_body(swapped=False, line_type="voip"),
                   counter)
    out = _keyed(query_items=[], scan_items=[])
    assert out["level"] == "medium"
    assert out["flagged"] is True
    assert any(r.startswith("line type: voip") for r in out["reasons"])


def test_keyed_unknown_on_clean(monkeypatch):
    counter = {"n": 0}
    _patch_urlopen(monkeypatch,
                   _twilio_body(swapped=False, line_type="mobile"),
                   counter)
    out = _keyed(query_items=[], scan_items=[])
    assert out["level"] == "unknown"
    assert out["flagged"] is False
    assert out["reasons"] == []
    assert "not proof of safety" in out["note"]
    blob = json.dumps(out).lower()
    assert '"low"' not in blob and "safe" not in blob.replace("not proof of safety", "")


def test_keyed_twilio_unavailable_degrades_honestly(monkeypatch):
    # Carrier gives no answer (per-package error_code): not a clean result.
    counter = {"n": 0}
    _patch_urlopen(monkeypatch, _twilio_body(error_code="60606"), counter)
    out = _keyed(query_items=[], scan_items=[])
    assert out["level"] == "unknown"  # corpus empty; Twilio silent
    assert out["signals"]["sim_swap"]["checked"] is False
    assert "60606" in out["signals"]["sim_swap"]["reason"]
    assert out["signals"]["line_type"]["checked"] is False


# ---------------------------------------------------------------------------
# Keyless: Twilio must be unreachable
# ---------------------------------------------------------------------------

def test_keyless_never_invokes_twilio(monkeypatch):
    calls = []

    def exploding_lookup(*args, **kwargs):
        calls.append(1)
        raise AssertionError("Twilio lookup must be unreachable on the keyless path")

    monkeypatch.setattr(pr, "twilio_lookup", exploding_lookup)
    table = FakeIocTable(query_items=[SIGHTING], scan_items=[])
    out = pr.assess_phone_reputation("+15551234567", keyless=True,
                                     ioc_table=table)
    assert calls == []
    assert out["level"] == "high"  # corpus still convicts
    assert out["signals"]["sim_swap"] == {"checked": False,
                                          "reason": "keyless tier"}
    assert out["signals"]["line_type"] == {"checked": False,
                                           "reason": "keyless tier"}


def test_keyless_unknown_when_corpus_empty(monkeypatch):
    def exploding_lookup(*args, **kwargs):
        raise AssertionError("unreachable")

    monkeypatch.setattr(pr, "twilio_lookup", exploding_lookup)
    out = pr.assess_phone_reputation("+15551234567", keyless=True,
                                     ioc_table=FakeIocTable())
    assert out["level"] == "unknown"
    assert out["flagged"] is False


# ---------------------------------------------------------------------------
# 24h Twilio cache
# ---------------------------------------------------------------------------

def test_twilio_cache_hit_avoids_second_lookup(monkeypatch):
    counter = {"n": 0}
    _patch_urlopen(monkeypatch, _twilio_body(swapped=False), counter)
    cache = pr.ReputationCache(table=FakeCacheTable())

    first = pr.twilio_lookup("+15551234567", "sid", "token", cache=cache)
    second = pr.twilio_lookup("+15551234567", "sid", "token", cache=cache)
    assert counter["n"] == 1
    assert first == second


def test_twilio_cache_entry_carries_24h_ttl(monkeypatch):
    counter = {"n": 0}
    _patch_urlopen(monkeypatch, _twilio_body(swapped=True), counter)
    fake_table = FakeCacheTable()
    cache = pr.ReputationCache(table=fake_table)
    pr.twilio_lookup("+15551234567", "sid", "token", cache=cache)
    item = fake_table.store["+15551234567"]
    ttl = item["expires_at"] - int(time.time())
    assert 23 * 3600 < ttl <= 24 * 3600


# ---------------------------------------------------------------------------
# Attack-graph paths: timestamps + decayed confidence
# ---------------------------------------------------------------------------

def test_attack_paths_carry_timestamps_and_decayed_confidence():
    seed = [SIGHTING]
    related = [{
        "ioc_value": "0xABCDEF1234567890ABCDEF1234567890ABCDEF12",
        "ioc_type": "wallet",
        "channel": "carding-central",
        "malware": "pig-butchering-kit",
        "seen_ts": "2026-09-27T08:00:00+00:00",
    }]
    paths = pr.attack_paths("+15551234567", seed,
                            table=FakeIocTable(scan_items=related))
    assert len(paths) == 1
    p = paths[0]
    assert 0 < p["confidence"] < 1.0  # decayed, never equal to the seed
    assert p["via"] == "malware_family"
    assert p["malware"] == "pig-butchering-kit"
    joined = " → ".join(p["path"])
    assert "2026-09-28" in joined  # seed post timestamp
    assert "2026-09-27" in joined  # related indicator timestamp
    assert "0xABCDEF12" in joined  # truncated wallet label


def test_attack_paths_empty_without_sightings():
    assert pr.attack_paths("+15551234567", [],
                           table=FakeIocTable()) == []


def test_keyed_reasons_expose_evidence_path(monkeypatch):
    counter = {"n": 0}
    _patch_urlopen(monkeypatch, _twilio_body(swapped=False), counter)
    related = [{
        "ioc_value": "evil.example",
        "ioc_type": "domain",
        "channel": "carding-central",
        "malware": "pig-butchering-kit",
        "seen_ts": "2026-09-27T08:00:00+00:00",
    }]
    out = _keyed(query_items=[SIGHTING], scan_items=related)
    assert out["level"] == "high"
    assert any("attack-graph path" in r and "confidence" in r
               for r in out["reasons"])
    sig_paths = out["signals"]["attack_paths"]
    assert sig_paths and all(p["confidence"] < 1.0 for p in sig_paths)
