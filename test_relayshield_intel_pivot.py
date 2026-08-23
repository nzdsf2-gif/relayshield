"""Tests for relayshield_intel_pivot.

The invariants worth defending are the ones the growth plan says would cost
credibility if broken: a derived indicator must never claim its seed's
confidence, must always carry the path it came from, and a lead-time claim must
never be flattered by clock skew or a thin sample.

Runs without AWS: everything under test is pure logic.
"""

import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/home/user/relayshield")

from relayshield_intel_pivot import (  # noqa: E402
    CONFIDENCE_RANK,
    PivotRefused,
    VERDICT_CLEAN,
    VERDICT_FLAGGED,
    VERDICT_UNKNOWN,
    RECHECK_SCHEDULE_HOURS,
    apply_recheck,
    derive_confidence,
    is_due_for_recheck,
    lead_time_summary,
    log_submission,
    make_derived_ioc,
)

T0 = datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)

SEED = {
    "ioc_value": "0xdeadbeef",
    "ioc_type": "wallet_eth",
    "confidence": "observed",
    "channel": "chanA",
    "category": "drainer",
}


class TestConfidenceDecay(unittest.TestCase):
    def test_one_hop_drops_exactly_one_rank(self):
        self.assertEqual(derive_confidence("confirmed"), "observed")
        self.assertEqual(derive_confidence("observed"), "derived")
        self.assertEqual(derive_confidence("derived"), "weak")

    def test_never_returns_the_seed_level(self):
        for level, rank in CONFIDENCE_RANK.items():
            if rank == 0:
                continue  # nothing below it — refusal is covered separately
            self.assertNotEqual(derive_confidence(level), level,
                                f"{level} returned its own level")

    def test_is_strictly_below_the_seed(self):
        for level, rank in CONFIDENCE_RANK.items():
            if rank == 0:
                continue
            self.assertLess(CONFIDENCE_RANK[derive_confidence(level)], rank,
                            f"{level} did not decay")

    def test_refuses_at_the_floor_rather_than_returning_the_seed_level(self):
        """Flooring and returning `unverified` would hand back a confidence
        equal to the seed's, which is the one thing the ladder exists to stop."""
        with self.assertRaises(PivotRefused):
            derive_confidence("unverified")

    def test_unknown_seed_confidence_is_refused(self):
        with self.assertRaises(PivotRefused):
            derive_confidence("extremely-sure")


class TestDerivedRecord(unittest.TestCase):
    def test_carries_derivation_path(self):
        rec = make_derived_ioc(SEED, "0xC0FFEE", "wallet_eth", "wallet_counterparty", now=T0)
        self.assertEqual(rec["derived_from"], "0xdeadbeef")
        self.assertEqual(rec["derivation"], "wallet_counterparty")
        self.assertEqual(rec["derivation_hops"], 1)
        self.assertEqual(rec["derivation_root"], "0xdeadbeef")
        self.assertEqual(rec["confidence"], "derived")

    def test_value_is_normalised(self):
        rec = make_derived_ioc(SEED, "  0xC0FFEE  ", "wallet_eth", "wallet_counterparty", now=T0)
        self.assertEqual(rec["ioc_value"], "0xc0ffee")

    def test_second_hop_keeps_the_original_root(self):
        first = make_derived_ioc(SEED, "0xc0ffee", "wallet_eth", "wallet_counterparty", now=T0)
        second = make_derived_ioc(first, "0xfeed", "wallet_eth", "wallet_counterparty", now=T0)
        self.assertEqual(second["derivation_hops"], 2)
        self.assertEqual(second["derivation_root"], "0xdeadbeef",
                         "a cluster must trace back to the one observed indicator")
        self.assertEqual(second["confidence"], "weak")

    def test_confidence_decays_monotonically_then_the_chain_is_refused(self):
        """Each hop drops exactly one rank, and the chain stops on its own once
        the seed falls below the pivotable bar — no separate depth limit."""
        node, ranks = SEED, [CONFIDENCE_RANK[SEED["confidence"]]]
        hops = 0
        while True:
            try:
                node = make_derived_ioc(node, f"0xhop{hops}", "wallet_eth",
                                        "wallet_counterparty", now=T0)
            except PivotRefused:
                break
            hops += 1
            ranks.append(CONFIDENCE_RANK[node["confidence"]])
            self.assertLess(hops, 10, "chain failed to terminate")

        self.assertEqual(ranks, [3, 2, 1], "observed -> derived -> weak, then stop")
        self.assertEqual(hops, 2, "a cluster should not run further than two hops")
        self.assertEqual(ranks, sorted(set(ranks), reverse=True))

    def test_refuses_unrecognised_method(self):
        with self.assertRaises(PivotRefused):
            make_derived_ioc(SEED, "0xc0ffee", "wallet_eth", "vibes", now=T0)

    def test_refuses_self_derivation(self):
        with self.assertRaises(PivotRefused):
            make_derived_ioc(SEED, "0xDEADBEEF", "wallet_eth", "wallet_counterparty", now=T0)

    def test_refuses_empty_value_or_seed(self):
        with self.assertRaises(PivotRefused):
            make_derived_ioc(SEED, "   ", "wallet_eth", "wallet_counterparty", now=T0)
        with self.assertRaises(PivotRefused):
            make_derived_ioc({"ioc_value": ""}, "x", "domain", "ct_sibling", now=T0)

    def test_refuses_to_pivot_from_an_unverified_seed(self):
        """The victim-name sweep writes unverified rows; pivoting off one would
        invent a confidence level that does not exist."""
        weak_seed = {"ioc_value": "acme corp", "confidence": "unverified"}
        with self.assertRaises(PivotRefused):
            make_derived_ioc(weak_seed, "acme.com", "domain", "pdns_sibling", now=T0)

    def test_seed_without_confidence_is_treated_as_first_hand(self):
        """Collected IOCs predate the confidence field -- absent means observed."""
        legacy = {"ioc_value": "evil.com", "channel": "c", "category": "phish"}
        rec = make_derived_ioc(legacy, "evil2.com", "domain", "ct_sibling", now=T0)
        self.assertEqual(rec["confidence"], "derived")

    def test_attribution_survives_the_pivot(self):
        rec = make_derived_ioc(SEED, "0xc0ffee", "wallet_eth", "wallet_counterparty", now=T0)
        self.assertEqual(rec["channel"], "chanA")
        self.assertEqual(rec["category"], "drainer")


class TestLedgerScheduling(unittest.TestCase):
    def test_unknown_gets_a_schedule(self):
        item = log_submission("http://bad.example", "telegram", VERDICT_UNKNOWN, now=T0)
        self.assertEqual(item["next_recheck_ts"],
                         (T0 + timedelta(hours=RECHECK_SCHEDULE_HOURS[0])).isoformat())

    def test_flagged_and_clean_get_no_schedule(self):
        for verdict in (VERDICT_FLAGGED, VERDICT_CLEAN):
            item = log_submission("http://x.example", "discord", verdict, now=T0)
            self.assertNotIn("next_recheck_ts", item)

    def test_empty_target_is_rejected(self):
        with self.assertRaises(ValueError):
            log_submission("   ", "telegram", VERDICT_UNKNOWN, now=T0)

    def test_due_only_once_the_window_passes(self):
        item = log_submission("http://bad.example", "telegram", VERDICT_UNKNOWN, now=T0)
        self.assertFalse(is_due_for_recheck(item, now=T0 + timedelta(hours=23)))
        self.assertTrue(is_due_for_recheck(item, now=T0 + timedelta(hours=25)))

    def test_a_flagged_row_is_never_due(self):
        item = log_submission("http://bad.example", "telegram", VERDICT_FLAGGED, now=T0)
        self.assertFalse(is_due_for_recheck(item, now=T0 + timedelta(days=30)))

    def test_schedule_advances_through_every_stage_then_retires(self):
        item = log_submission("http://bad.example", "telegram", VERDICT_UNKNOWN, now=T0)
        for stage, hours in enumerate(RECHECK_SCHEDULE_HOURS[1:], start=1):
            item = apply_recheck(item, VERDICT_UNKNOWN, now=T0 + timedelta(hours=hours))
            self.assertEqual(item["next_recheck_ts"],
                             (T0 + timedelta(hours=RECHECK_SCHEDULE_HOURS[stage])).isoformat())
        item = apply_recheck(item, VERDICT_UNKNOWN, now=T0 + timedelta(days=8))
        self.assertNotIn("next_recheck_ts", item)
        self.assertTrue(item["recheck_exhausted"])
        self.assertFalse(is_due_for_recheck(item, now=T0 + timedelta(days=90)))


class TestLeadTime(unittest.TestCase):
    def test_flip_records_lead_time(self):
        item = log_submission("http://bad.example", "telegram", VERDICT_UNKNOWN, now=T0)
        flipped = apply_recheck(item, VERDICT_FLAGGED, now=T0 + timedelta(hours=72))
        self.assertEqual(flipped["verdict"], VERDICT_FLAGGED)
        self.assertEqual(flipped["lead_time_hours"], 72.0)
        self.assertNotIn("next_recheck_ts", flipped)

    def test_clock_skew_cannot_manufacture_a_negative_lead(self):
        item = log_submission("http://bad.example", "telegram", VERDICT_UNKNOWN, now=T0)
        flipped = apply_recheck(item, VERDICT_FLAGGED, now=T0 - timedelta(hours=5))
        self.assertEqual(flipped["lead_time_hours"], 0.0)

    def test_summary_reports_median_and_sample_share(self):
        rows = [
            {"verdict": VERDICT_FLAGGED, "lead_time_hours": 24.0},
            {"verdict": VERDICT_FLAGGED, "lead_time_hours": 72.0},
            {"verdict": VERDICT_FLAGGED, "lead_time_hours": 120.0},
            {"verdict": VERDICT_UNKNOWN},
        ]
        out = lead_time_summary(rows)
        self.assertEqual(out["flipped_to_flagged"], 3)
        self.assertEqual(out["median_lead_hours"], 72.0)
        self.assertEqual(out["min_lead_hours"], 24.0)
        self.assertEqual(out["max_lead_hours"], 120.0)
        self.assertEqual(out["still_unknown"], 1)
        self.assertEqual(out["sample_share"], 0.75)

    def test_even_sample_median_is_the_midpoint(self):
        rows = [
            {"verdict": VERDICT_FLAGGED, "lead_time_hours": 10.0},
            {"verdict": VERDICT_FLAGGED, "lead_time_hours": 20.0},
        ]
        self.assertEqual(lead_time_summary(rows)["median_lead_hours"], 15.0)

    def test_no_flips_makes_no_claim(self):
        out = lead_time_summary([{"verdict": VERDICT_UNKNOWN}, {"verdict": VERDICT_CLEAN}])
        self.assertEqual(out["flipped_to_flagged"], 0)
        self.assertIsNone(out["median_lead_hours"])
        self.assertIn("no unknown submission", out["note"])

    def test_empty_ledger_does_not_divide_by_zero(self):
        out = lead_time_summary([])
        self.assertEqual(out["submissions"], 0)
        self.assertIsNone(out["median_lead_hours"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
