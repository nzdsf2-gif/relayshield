"""Tests for corpus cross-correlation verdicts (feature/corpus-provenance-verdicts).

Covers relayshield_corpus_provenance.corpus_provenance_summary (empty input,
multi-market sightings, family links, DynamoDB failure) and the
POST /v1/composite-check `corpus_provenance` wiring in relayshield_api.

DynamoDB is faked; boto3 is stubbed before import because relayshield_api
creates AWS clients at module level.
"""

import json
import os
import sys
import types

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


# --- Stub boto3 before importing relayshield_api (module-level clients) ---
class _Cond:
    def __init__(self, *a):
        pass

    def __and__(self, other):
        return self

    def eq(self, v):
        return self

    def ne(self, v):
        return self

    def is_in(self, v):
        return self


class _Dummy:
    def __init__(self, *a, **k):
        pass

    def __call__(self, *a, **k):
        return _Dummy()

    def __getattr__(self, name):
        return lambda *a, **k: _Dummy()


_fake_conditions = types.ModuleType("boto3.dynamodb.conditions")
_fake_conditions.Key = _Cond
_fake_conditions.Attr = _Cond
_fake_dynamodb = types.ModuleType("boto3.dynamodb")
_fake_dynamodb.conditions = _fake_conditions
_fake_boto3 = types.ModuleType("boto3")
_fake_boto3.client = lambda *a, **k: _Dummy()
_fake_boto3.resource = lambda *a, **k: _Dummy()
_fake_boto3.dynamodb = _fake_dynamodb
sys.modules["boto3"] = _fake_boto3
sys.modules["boto3.dynamodb"] = _fake_dynamodb
sys.modules["boto3.dynamodb.conditions"] = _fake_conditions

# Stub remaining module-level sibling imports of relayshield_api that are
# irrelevant to these tests (avoids a download cascade).
_breach = types.ModuleType("relayshield_breach_monitor")
_breach.ATTACK_CHAINS = {}
sys.modules["relayshield_breach_monitor"] = _breach
_labels = types.ModuleType("relayshield_intel_labels")
_labels.normalise_malware_query = lambda q: q
sys.modules["relayshield_intel_labels"] = _labels
_consent = types.ModuleType("relayshield_sim_swap_consent")
_consent.CONSENT_TERMS_VERSION = "test"
sys.modules["relayshield_sim_swap_consent"] = _consent

import relayshield_api as api  # noqa: E402
import relayshield_corpus_provenance as prov  # noqa: E402


# --- Fake DynamoDB table ---
class FakeTable:
    def __init__(self, items, scan_items=None):
        self._items = items
        self._scan_items = scan_items if scan_items is not None else []

    def query(self, **kwargs):
        return {"Items": self._items}

    def scan(self, **kwargs):
        return {"Items": self._scan_items}


def _sighting(channel, malware="", ioc_type="url", kit_family=""):
    return {
        "ioc_value": "evil.example",
        "ioc_type": ioc_type,
        "seen_ts": "2026-09-15T00:00:00+00:00",
        "channel": channel,
        "malware": malware,
        "kit_family": kit_family,
    }


# --- Helper tests ---
def test_empty_indicator_returns_empty(monkeypatch):
    monkeypatch.setattr(prov, "_dynamodb_table", lambda: FakeTable([_sighting("@x")]))
    for bad in ("", "   ", None):
        out = prov.corpus_provenance_summary(bad, "url")
        assert out["sightings_count"] == 0
        assert out["markets_seen_count"] == 0
        assert out["market_names"] == []
        assert out["linked_wallets_count"] == 0
        assert out["kit_families"] == []
        assert out["malware_families"] == []
        assert out["summary"] is None


def test_multi_market_sightings(monkeypatch):
    items = [
        _sighting("@market-a"),
        _sighting("@market-a"),
        _sighting("@market-b"),
        _sighting("@market-c"),
        _sighting("@market-d"),
    ]
    monkeypatch.setattr(prov, "_dynamodb_table", lambda: FakeTable(items))
    out = prov.corpus_provenance_summary("evil.example", "url")
    assert out["sightings_count"] == 5
    assert out["markets_seen_count"] == 4
    # market names capped at 3
    assert out["market_names"] == ["@market-a", "@market-b", "@market-c"]
    assert out["summary"] is not None
    assert "4 criminal marketplaces" in out["summary"]
    assert "+1 more" in out["summary"]


def test_family_links_and_wallet_pivot(monkeypatch):
    items = [
        _sighting("@market-a", malware="Emotet", kit_family="milk-dragon"),
        _sighting("@market-b", malware="Emotet", kit_family="milk-dragon"),
    ]
    scan_items = [
        {"ioc_value": "0xabc123", "ioc_type": "wallet"},
        {"ioc_value": "bc1qxyz", "ioc_type": "address"},
        {"ioc_value": "other-evil.example", "ioc_type": "domain"},
    ]
    monkeypatch.setattr(
        prov, "_dynamodb_table", lambda: FakeTable(items, scan_items))
    out = prov.corpus_provenance_summary("evil.example", "url")
    assert out["malware_families"] == ["Emotet"]
    assert out["kit_families"] == ["milk-dragon"]
    assert out["linked_wallets_count"] == 2
    assert "kit family milk-dragon" in out["summary"]
    assert "linked to 2 wallets" in out["summary"]


def test_unknown_indicator_returns_empty(monkeypatch):
    monkeypatch.setattr(prov, "_dynamodb_table", lambda: FakeTable([]))
    out = prov.corpus_provenance_summary("never-seen.example", "domain")
    assert out["sightings_count"] == 0
    assert out["summary"] is None


def test_dynamodb_failure_degrades(monkeypatch):
    def _boom():
        raise RuntimeError("no network")

    monkeypatch.setattr(prov, "_dynamodb_table", _boom)
    out = prov.corpus_provenance_summary("evil.example", "url")
    assert out["sightings_count"] == 0
    assert out["summary"] is None


def test_one_liner_placeholders_dropped():
    line = prov.provenance_one_liner({
        "markets_seen_count": 1,
        "market_names": ["@a"],
        "linked_wallets_count": 0,
        "kit_families": [],
        "malware_families": ["unknown", "Emotet"],
    })
    assert line == "Seen in 1 criminal marketplace (@a) · malware family Emotet"


def test_one_liner_empty():
    assert prov.provenance_one_liner({}) is None


# --- Composite-check wiring tests ---
def _canned_subcall(handler, sub_params):
    return True, {"level": "high", "flagged": True, "reasons": ["test flag"]}


def _canned_provenance(target, sig_type):
    return {
        "indicator": target,
        "indicator_type": sig_type,
        "sightings_count": 12,
        "markets_seen_count": 3,
        "market_names": ["@a", "@b", "@c"],
        "linked_wallets_count": 2,
        "kit_families": ["milk-dragon"],
        "malware_families": [],
        "summary": ("Seen in 3 criminal marketplaces (@a, @b, @c) · "
                    "linked to 2 wallets · kit family milk-dragon"),
    }


def _composite_data(resp):
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["ok"] is True
    return body["data"]


def test_composite_includes_provenance(monkeypatch):
    monkeypatch.setattr(api, "_composite_subcall", _canned_subcall)
    monkeypatch.setattr(
        api._provenance, "corpus_provenance_summary", _canned_provenance)
    data = _composite_data(
        api.handle_composite_check({"url": "https://evil.example/x"}))
    assert "corpus_provenance" in data
    entries = data["corpus_provenance"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["type"] == "url"
    assert entry["target"] == "https://evil.example/x"
    assert entry["sightings_count"] == 12
    assert entry["markets_seen_count"] == 3
    assert entry["market_names"] == ["@a", "@b", "@c"]
    assert entry["linked_wallets_count"] == 2
    assert entry["kit_families"] == ["milk-dragon"]
    assert entry["summary"].startswith("Seen in 3 criminal marketplaces")


def test_composite_omits_provenance_when_empty(monkeypatch):
    monkeypatch.setattr(api, "_composite_subcall", _canned_subcall)

    def _empty(target, sig_type):
        return {"summary": None, "sightings_count": 0,
                "markets_seen_count": 0, "market_names": [],
                "linked_wallets_count": 0, "kit_families": [],
                "malware_families": []}

    monkeypatch.setattr(api._provenance, "corpus_provenance_summary", _empty)
    data = _composite_data(
        api.handle_composite_check({"url": "https://clean.example/"}))
    assert "corpus_provenance" not in data
    # existing fields untouched
    assert data["level"] in ("high", "medium", "unknown")
    assert isinstance(data["score"], int)
    assert isinstance(data["signals"], list)


def test_composite_wallet_signal_provenance(monkeypatch):
    monkeypatch.setattr(api, "_composite_subcall", _canned_subcall)
    seen = []

    def _spy(target, sig_type):
        seen.append((target, sig_type))
        return _canned_provenance(target, sig_type)

    monkeypatch.setattr(api._provenance, "corpus_provenance_summary", _spy)
    data = _composite_data(api.handle_composite_check(
        {"wallet": "0xAbC123"}))
    assert "corpus_provenance" in data
    assert data["corpus_provenance"][0]["type"] == "wallet"
    assert ("0xAbC123", "wallet") in seen
