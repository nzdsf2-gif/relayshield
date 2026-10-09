"""Tests for mcp_proxy.reputation (Phase 3 server reputation graph).

Run: python3 -m pytest mcp_proxy/test_reputation.py -v
"""

from .reputation import (
    ReputationStore,
    ServerScore,
    band_for,
    BAND_TRUSTED,
    BAND_WATCH,
    BAND_UNTRUSTED,
)


def test_new_server_starts_trusted_but_unproven():
    s = ServerScore("http://srv.example/mcp")
    assert s.score == 80.0
    assert band_for(s.score) == BAND_TRUSTED
    assert s.domain == "srv.example"


def test_band_boundaries():
    assert band_for(100.0) == BAND_TRUSTED
    assert band_for(70.0) == BAND_TRUSTED
    assert band_for(69.9) == BAND_WATCH
    assert band_for(40.0) == BAND_WATCH
    assert band_for(39.9) == BAND_UNTRUSTED
    assert band_for(0.0) == BAND_UNTRUSTED


def test_ti_hit_drops_score():
    s = ServerScore("http://srv.example/mcp")
    s.ti_hit("malicious domain")
    assert s.score == 55.0
    assert s.event_counts["ti_hit"] == 1


def test_quarantine_drops_hard():
    s = ServerScore("http://srv.example/mcp")
    s.quarantined("auto-quarantine")
    assert s.score == 40.0
    assert band_for(s.score) == BAND_WATCH


def test_score_floors_at_zero():
    s = ServerScore("http://srv.example/mcp")
    for _ in range(10):
        s.ti_hit()
    assert s.score == 0.0


def test_score_caps_at_100():
    s = ServerScore("http://srv.example/mcp")
    s.score = 99.0
    s.quarantine_cleared()
    assert s.score == 100.0


def test_history_bounded():
    s = ServerScore("http://srv.example/mcp")
    for i in range(300):
        s.flag(f"flag {i}")
    assert len(s.history) <= 200
    # History still ends at the current score.
    assert s.history[-1][1] == s.score


def test_store_summary_counts():
    store = ReputationStore()
    store.get_or_create("http://good.example/mcp")
    bad = store.get_or_create("http://bad.example/mcp")
    bad.ti_hit()
    bad.ti_hit()
    ugly = store.get_or_create("http://ugly.example/mcp")
    for _ in range(4):
        ugly.ti_hit()
    summary = store.summary()
    assert summary["counts"]["total"] == 3
    assert summary["counts"]["trusted"] == 1   # good: 80
    assert summary["counts"]["watch"] == 0
    assert summary["counts"]["untrusted"] == 2  # bad (30), ugly (0)


def test_store_to_dict_has_history():
    store = ReputationStore()
    s = store.get_or_create("http://srv.example/mcp")
    s.flag("test")
    d = s.to_dict()
    assert len(d["history"]) == 3  # init + flag... (init, flag)
    assert d["history"][-1]["score"] == 70.0
    d_no_hist = s.to_dict(include_history=False)
    assert "history" not in d_no_hist


def test_record_helpers():
    store = ReputationStore()
    url = "http://srv.example/mcp"
    store.record_flag(url, "f")
    store.record_behavior_anomaly(url, "b")
    store.record_attack_chain(url, "c")
    store.record_ti_hit(url, "t")
    store.record_quarantine(url, "q")
    store.record_quarantine_cleared(url, "qc")
    s = store.get(url)
    assert s.event_counts["flag"] == 1
    assert s.event_counts["behavior_anomaly"] == 1
    assert s.event_counts["attack_chain"] == 1
    assert s.event_counts["ti_hit"] == 1
    assert s.event_counts["quarantine"] == 1
    # 80 -10 -5 -20 -25 -40 +15 = -5 -> floored at 0, then +15 = 15
    assert s.score == 15.0
