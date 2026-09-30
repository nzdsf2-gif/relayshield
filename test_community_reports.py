"""Tests for relayshield_community_reports.

Uses a dict-backed FakeTable that speaks the same small boto3 surface the
module uses (put_item / get_item / query / scan), so the quarantine rules
are tested with no AWS credentials and no moto.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

import relayshield_community_reports as cr


# ---------------------------------------------------------------------------
# Fake DynamoDB table
# ---------------------------------------------------------------------------

class FakeTable:
    def __init__(self):
        self.items = {}  # key-tuple -> item

    @staticmethod
    def _key(item):
        # quarantine table keys on (pk, sk); the curated corpus table keys
        # on (ioc_value, seen_ts)
        return (item.get("pk") or item.get("ioc_value"),
                item.get("sk") or item.get("seen_ts"))

    # -- writes ----------------------------------------------------------
    def put_item(self, Item):
        self.items[self._key(Item)] = dict(Item)
        return {}

    # -- reads -----------------------------------------------------------
    def get_item(self, Key):
        item = self.items.get((Key.get("pk"), Key.get("sk")))
        return {"Item": dict(item)} if item else {}

    @staticmethod
    def _parse_condition(cond):
        expr = cond.get_expression()
        assert expr["operator"] == "=", f"fake only supports eq, got {expr}"
        name = expr["values"][0].name
        value = expr["values"][1]
        return name, value

    def query(self, KeyConditionExpression=None, Limit=None):
        name, value = self._parse_condition(KeyConditionExpression)
        out = [dict(i) for (pk, _), i in self.items.items()
               if i.get(name) == value]
        # quarantine reports share pk; keep deterministic order
        out.sort(key=lambda i: i.get("sk", ""))
        if Limit is not None:
            out = out[:Limit]
        return {"Items": out}

    def scan(self, FilterExpression=None, Limit=None):
        out = [dict(i) for i in self.items.values()]
        if FilterExpression is not None:
            name, value = self._parse_condition(FilterExpression)
            out = [i for i in out if i.get(name) == value]
        out.sort(key=lambda i: i.get("reported_at", ""))
        if Limit is not None:
            out = out[:Limit]
        return {"Items": out}


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setenv("COMMUNITY_REPORTS_ENABLED", "true")


@pytest.fixture()
def tables():
    return {"quarantine": FakeTable(), "corpus": FakeTable()}


def _old_trusted_profile(reporter_hash, days=60, reputation=1.0):
    first = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    return {
        "pk": f"REPORTER#{reporter_hash}",
        "sk": "PROFILE",
        "reporter_hash": reporter_hash,
        "first_seen": first,
        "window_start": first,
        "window_count": 0,
        "reports_total": 0,
        "reports_approved": 0,
        "reports_rejected": 0,
        "reputation": reputation,
    }


# ---------------------------------------------------------------------------
# Submission: quarantine only, provenance, flag
# ---------------------------------------------------------------------------

def test_report_lands_in_quarantine_not_corpus(tables):
    cr.submit_report(
        "http://evil.example/phish", channel="tg", user_id="12345",
        verdict_at_report="unknown", table=tables["quarantine"],
    )
    assert len(tables["quarantine"].items) == 2  # report + reporter profile
    assert len(tables["corpus"].items) == 0      # corpus never touched


def test_reports_disabled_by_default(monkeypatch, tables):
    monkeypatch.setenv("COMMUNITY_REPORTS_ENABLED", "false")
    with pytest.raises(cr.ReportsDisabled):
        cr.submit_report("http://evil.example/x", channel="tg", user_id="1",
                         verdict_at_report="unknown", table=tables["quarantine"])


def test_provenance_fields_present_and_hashed(tables):
    report = cr.submit_report(
        "http://evil.example/phish", channel="wa", user_id="+15551234567",
        verdict_at_report="unknown", note="  looks like a bank phish  ",
        table=tables["quarantine"],
    )
    assert report["channel"] == "wa"
    assert report["reported_at"]
    assert report["indicator"] == "http://evil.example/phish"
    assert report["indicator_type"] == "url"
    assert report["verdict_at_report"] == "unknown"
    assert report["note"] == "looks like a bank phish"
    assert report["status"] == "quarantined"
    # reporter id is a one-way hash, never the raw phone number
    assert len(report["reporter_hash"]) == 64
    assert "+15551234567" not in str(report)
    assert "+15551234567" not in str(tables["quarantine"].items)


def test_message_indicator_stored_as_hash_never_raw(tables):
    body = "Dear customer your account is locked, wire $500 to ..."
    report = cr.submit_report(body, channel="tg", user_id="999",
                              verdict_at_report="unknown",
                              table=tables["quarantine"])
    assert report["indicator_type"] == "message"
    assert len(report["indicator"]) == 64  # sha256 hex
    assert body not in str(report)
    assert body not in str(tables["quarantine"].items)


def test_duplicate_report_refused(tables):
    kw = dict(channel="tg", user_id="42", verdict_at_report="unknown",
              table=tables["quarantine"])
    cr.submit_report("http://evil.example/dup", **kw)
    with pytest.raises(cr.ReportRefused):
        cr.submit_report("http://evil.example/dup", **kw)


# ---------------------------------------------------------------------------
# Confidence: community capped below curated corpus TI
# ---------------------------------------------------------------------------

def test_community_confidence_below_every_curated_level():
    assert cr.community_confidence_below_corpus()
    assert cr.CONFIDENCE_RANK[cr.COMMUNITY_CONFIDENCE] \
        < cr.CONFIDENCE_RANK["unverified"] \
        < cr.CONFIDENCE_RANK["observed"]


def test_promotion_cap_below_curated_observed():
    assert cr.CONFIDENCE_RANK[cr.PROMOTED_CONFIDENCE_CAP] \
        < cr.CONFIDENCE_RANK["observed"]


# ---------------------------------------------------------------------------
# No auto-promotion on counts alone
# ---------------------------------------------------------------------------

def test_many_reports_never_auto_promote(tables):
    for i in range(6):
        cr.submit_report("http://evil.example/popular", channel="tg",
                         user_id=f"user-{i}", verdict_at_report="unknown",
                         table=tables["quarantine"])
    _, key, _ = cr.normalize_indicator("http://evil.example/popular")
    reports = cr.get_reports_for_indicator(key, table=tables["quarantine"])
    assert len(reports) == 6
    assert {r["status"] for r in reports} == {"quarantined"}
    assert len(tables["corpus"].items) == 0


def test_approve_without_corroboration_or_corpus_match_refused(tables):
    cr.submit_report("http://evil.example/lonely", channel="tg", user_id="solo",
                     verdict_at_report="unknown", table=tables["quarantine"])
    _, key, _ = cr.normalize_indicator("http://evil.example/lonely")
    with pytest.raises(cr.ReportRefused):
        cr.review_report(key, decision="approved", reviewer="andrew",
                         table=tables["quarantine"],
                         iocs_table=tables["corpus"], corpus_match=False)
    assert len(tables["corpus"].items) == 0


# ---------------------------------------------------------------------------
# Promotion gate: corroboration -> suggest -> approve -> capped corpus write
# ---------------------------------------------------------------------------

def test_full_promotion_path_with_corroboration(tables):
    url = "http://evil.example/corroborated"
    hashes = [cr.hash_reporter("tg", f"trusted-{i}") for i in range(2)]
    for h in hashes:  # old, reputable reporters -> weight 1.0 each
        tables["quarantine"].put_item(Item=_old_trusted_profile(h))
    for i in range(2):
        cr.submit_report(url, channel="tg", user_id=f"trusted-{i}",
                         verdict_at_report="unknown",
                         table=tables["quarantine"])
    _, key, _ = cr.normalize_indicator(url)

    moved = cr.suggest_for_review(key, table=tables["quarantine"])
    assert moved["moved"] == 2
    assert moved["eligible_for_suggest"]

    result = cr.review_report(key, decision="approved", reviewer="andrew",
                              table=tables["quarantine"],
                              iocs_table=tables["corpus"], corpus_match=False)
    assert result["decision"] == "approved"
    assert result["corpus_written"] is True
    assert len(tables["corpus"].items) == 1

    corpus_item = next(iter(tables["corpus"].items.values()))
    assert corpus_item["ioc_value"] == url
    # capped below curated "observed", with community provenance
    assert corpus_item["confidence"] == "unverified"
    assert corpus_item["source"] == "community_quarantine"
    assert corpus_item["reviewer"] == "andrew"
    assert len(corpus_item["community_report_ids"]) == 2


def test_approve_on_corpus_match_without_corroboration(tables):
    url = "http://evil.example/known"
    tables["corpus"].put_item(Item={  # pre-existing corpus evidence
        "pk": "x", "sk": "y", "ioc_value": url, "confidence": "observed"})
    cr.submit_report(url, channel="tg", user_id="one-user",
                     verdict_at_report="unknown", table=tables["quarantine"])
    _, key, _ = cr.normalize_indicator(url)
    result = cr.review_report(key, decision="approved", reviewer="andrew",
                              table=tables["quarantine"],
                              iocs_table=tables["corpus"], corpus_match=True)
    assert result["corpus_written"] is True


def test_reject_marks_reports_and_decays_reputation(tables):
    url = "http://evil.example/falsealarm"
    cr.submit_report(url, channel="tg", user_id="noisy",
                     verdict_at_report="unknown", table=tables["quarantine"])
    _, key, _ = cr.normalize_indicator(url)
    before = cr.get_reporter_profile(cr.hash_reporter("tg", "noisy"),
                                     table=tables["quarantine"])
    assert before["reputation"] == pytest.approx(0.5)
    cr.review_report(key, decision="rejected", reviewer="andrew",
                     table=tables["quarantine"], iocs_table=tables["corpus"])
    after = cr.get_reporter_profile(cr.hash_reporter("tg", "noisy"),
                                    table=tables["quarantine"])
    assert after["reputation"] == pytest.approx(0.5 * 0.7)
    assert after["reports_rejected"] == 1
    reports = cr.get_reports_for_indicator(key, table=tables["quarantine"])
    assert {r["status"] for r in reports} == {"rejected"}
    # rejected reports never corroborate and never reach the corpus
    assert cr.community_report_count(url, table=tables["quarantine"]) == 0
    assert len(tables["corpus"].items) == 0


# ---------------------------------------------------------------------------
# Abuse controls
# ---------------------------------------------------------------------------

def test_rate_limit_enforced(tables):
    for i in range(cr.MAX_REPORTS_PER_WINDOW):
        cr.submit_report(f"http://evil.example/r{i}", channel="tg",
                         user_id="spammer", verdict_at_report="unknown",
                         table=tables["quarantine"])
    with pytest.raises(cr.RateLimited):
        cr.submit_report("http://evil.example/r-over", channel="tg",
                         user_id="spammer", verdict_at_report="unknown",
                         table=tables["quarantine"])


def test_low_trust_reporter_contributes_zero_weight():
    now = datetime.now(timezone.utc)
    prof = _old_trusted_profile("x" * 64)
    prof["reputation"] = 0.1  # below LOW_TRUST_REPUTATION
    assert cr.reporter_weight(prof, now) == 0.0


def test_reputation_decays_with_repeated_false_reports():
    prof = cr.new_reporter_profile("h" * 64)
    for _ in range(3):
        prof = cr.apply_review_outcome(prof, approved=False)
    assert prof["reputation"] == pytest.approx(0.5 * 0.7 ** 3)
    assert prof["reputation"] >= cr.REPUTATION_MIN


def test_sybil_burst_down_weighted_to_zero(tables):
    url = "http://evil.example/sybil"
    now = datetime.now(timezone.utc)
    reports, profiles = [], {}
    for i in range(6):  # six brand-new accounts, same indicator, same hour
        h = cr.hash_reporter("tg", f"sybil-{i}")
        prof = cr.new_reporter_profile(h, now)
        profiles[h] = prof
        reports.append({
            "reporter_hash": h, "reported_at": now.isoformat(),
            "status": "quarantined",
        })
    summary = cr.corroboration_summary(reports, profiles, now)
    assert summary["sybil_suspect"] is True
    assert summary["total_weight"] == 0.0
    assert summary["eligible_for_suggest"] is False


def test_account_age_weighting():
    now = datetime.now(timezone.utc)
    fresh = cr.new_reporter_profile("f" * 64, now)
    old = _old_trusted_profile("o" * 64, days=60, reputation=0.5)
    assert cr.reporter_weight(fresh, now) < cr.reporter_weight(old, now)
    assert cr.reporter_weight(old, now) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Demand-side signal rendering
# ---------------------------------------------------------------------------

def test_demand_side_label():
    assert cr.demand_side_label(0) == ""
    one = cr.demand_side_label(1)
    assert "1 user" in one and "community reports" in one
    many = cr.demand_side_label(7)
    assert "7 users" in many
    assert "not verified threat intelligence" in many
    # copy rules: never "safe"
    assert "safe" not in cr.demand_side_label(3).lower()


def test_community_report_count_labeled_signal(tables):
    url = "http://evil.example/counted"
    assert cr.community_report_count(url, table=tables["quarantine"]) == 0
    for i in range(3):
        cr.submit_report(url, channel="wa", user_id=f"w{i}",
                         verdict_at_report="unknown",
                         table=tables["quarantine"])
    assert cr.community_report_count(url, table=tables["quarantine"]) == 3


def test_indicator_classification():
    assert cr.classify_indicator("https://evil.example/x") == "url"
    assert cr.classify_indicator("evil.example") == "domain"
    assert cr.classify_indicator("0x" + "ab" * 20) == "wallet"
    assert cr.classify_indicator("+15551234567") == "phone"
    assert cr.classify_indicator("hello this is your bank calling") == "message"
