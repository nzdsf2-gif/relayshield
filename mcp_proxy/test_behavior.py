"""Tests for mcp_proxy.behavior (Phase 3 behavioral baselining).

Run: python3 -m pytest mcp_proxy/test_behavior.py -v
"""

import time

from .behavior import (
    AgentProfile,
    AttackChainDetector,
    BehaviorTracker,
    RiskScorer,
    POISON_BEHAVIORAL_ANOMALY,
    POISON_ATTACK_CHAIN,
)


def _tracker_with_baseline(agent="agent-1", calls=25):
    """A tracker whose agent has a stable baseline of search_docs calls."""
    t = BehaviorTracker()
    base = time.time() - 3600  # an hour of history
    for i in range(calls):
        t.check(agent, "search_docs", {}, ts=base + i * 120)
    return t


def test_volume_anomaly_flags():
    t = _tracker_with_baseline()
    # Flood: 30 calls in the last few seconds.
    now = time.time()
    result = None
    for i in range(30):
        result = t.check("agent-1", "search_docs", {}, ts=now + i * 0.1)
    assert result["verdict"] == "flag"
    assert result["poison_category"] == POISON_BEHAVIORAL_ANOMALY
    assert any("volume anomaly" in r for r in result["reasons"])


def test_sequence_anomaly_flags():
    t = _tracker_with_baseline()
    result = t.check("agent-1", "delete_everything", {})
    assert result["verdict"] == "flag"
    assert any("sequence anomaly" in r for r in result["reasons"])


def test_time_anomaly_flags():
    t = BehaviorTracker()
    # Baseline built entirely at 10:00.
    base = time.time()
    # Force all baseline calls into hour 10 by mocking _hour_of_day
    # behavior: instead, build the profile directly.
    p = t.profile_for("agent-9")
    for _ in range(25):
        p.hour_counts[10] += 1
        p.total_calls += 1
    p.tool_counts["search_docs"] = 25
    # Now call at a fabricated timestamp in hour 3.
    import mcp_proxy.behavior as bmod
    orig = bmod._hour_of_day
    bmod._hour_of_day = lambda ts: 3
    try:
        result = t.check("agent-9", "search_docs", {})
    finally:
        bmod._hour_of_day = orig
    assert result["verdict"] == "flag"
    assert any("time anomaly" in r for r in result["reasons"])


def test_clean_traffic_passes():
    t = _tracker_with_baseline()
    result = t.check("agent-1", "search_docs", {"query": "x"})
    assert result["verdict"] == "allow"
    assert result["poison_category"] == "clean"
    assert result["reasons"] == []


def test_new_agent_no_false_positive():
    t = BehaviorTracker()
    # Fewer than _MIN_BASELINE_CALLS: never flags.
    for i in range(5):
        result = t.check("fresh", "weird_tool", {})
        assert result["verdict"] == "allow"


def test_exfiltration_chain_detected():
    d = AttackChainDetector(window_s=600)
    d.record("a", "read_customer_file", server_url="s1")
    d.record("a", "http_post_external", server_url="s1")
    matched = d.record("a", "send_email_report", server_url="s1")
    assert any(c["name"] == "data_exfiltration" for c in matched)


def test_exfiltration_chain_out_of_order_not_detected():
    d = AttackChainDetector(window_s=600)
    d.record("a", "send_email_report", server_url="s1")
    d.record("a", "read_customer_file", server_url="s1")
    matched = d.record("a", "http_post_external", server_url="s1")
    assert not any(c["name"] == "data_exfiltration" for c in matched)


def test_lateral_movement_detected():
    d = AttackChainDetector(window_s=600)
    matched = []
    for i in range(5):
        matched = d.record("a", "list_tools",
                           server_url=f"http://srv{i}.example")
    assert any(c["name"] == "lateral_movement" for c in matched)


def test_escalation_chain_detected():
    d = AttackChainDetector(window_s=600)
    d.record("a", "fetch_page", server_url="s1", had_injection=True)
    matched = d.record("a", "run_shell_command", server_url="s1")
    assert any(c["name"] == "privilege_escalation" for c in matched)


def test_chain_flagged_with_attack_chain_category():
    t = BehaviorTracker()
    agent = "chain-agent"
    t.check(agent, "read_customer_file", {})
    t.check(agent, "http_post_external", {})
    result = t.check(agent, "send_email_report", {})
    assert result["verdict"] == "flag"
    assert result["poison_category"] == POISON_ATTACK_CHAIN
    assert any("attack_chain" in r for r in result["reasons"])


def test_risk_score_increases_and_decays():
    r = RiskScorer(half_life_s=100000)  # effectively no decay
    assert r.get("x") == 0.0
    r.add("x", 30.0, "test")
    assert r.get("x") == 30.0
    r.add("x", 80.0, "test")
    assert r.get("x") == 100.0  # capped

    r2 = RiskScorer(half_life_s=10.0)
    r2.add("y", 80.0, "test")
    # Simulate 10s passing by backdating.
    r2._scores["y"]["updated"] -= 10.0
    assert abs(r2.get("y") - 40.0) < 0.01


def test_profile_to_dict():
    p = AgentProfile("a")
    p.record("search_docs")
    d = p.to_dict()
    assert d["agent_id"] == "a"
    assert d["total_calls"] == 1
    assert d["baseline_ready"] is False


def test_tracker_disabled():
    t = BehaviorTracker(enabled=False)
    result = t.check("any", "any_tool", {})
    assert result["verdict"] == "allow"
    assert result["risk_score"] == 0.0
