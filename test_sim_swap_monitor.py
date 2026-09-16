"""Tests for the SIM swap / port-out monitor.

WHY THIS FILE EXISTS. On 2026-09-16 this monitor sent the founder a CRITICAL
alert saying his number "may be transferred from T-Mobile USA to T-Mobile USA"
-- the same carrier on both sides of a transfer, which is not a port-out under
any reading. There was no test file for this Lambda at all, and the detector
was a raw string comparison of a VENDOR DISPLAY NAME assembled from a two-source
fallback that spells one carrier more than one way.

Everything below EXECUTES the real functions. A test that greps this file for
the word "normalise" would pass on a version that never calls it, which is the
mistake test_miniapp.py and test_watchlist_monitor.py have both already paid for.

THE TEST THIS SUITE EXISTS TO CARRY is
test_the_same_carrier_is_never_a_port_out. Every other failure costs a wrong
answer in a log. That one costs a customer a CRITICAL alert about an attack
that did not happen -- and the second one of those is the alert they ignore.
"""

import ast
import importlib
import sys
import types
import unittest
from unittest import mock


def _stub_boto3():
    """A boto3 that constructs without credentials and records nothing.

    Only the shapes the module touches at import time. Anything a test needs is
    patched per-test, so an unimplemented call raises rather than returning a
    Mock that compares equal to everything.
    """
    b = types.ModuleType("boto3")
    b.client = lambda *a, **k: mock.MagicMock()
    b.resource = lambda *a, **k: mock.MagicMock()
    conditions = types.ModuleType("boto3.dynamodb.conditions")

    class _Attr:
        def __init__(self, name): self.name = name
        def eq(self, v): return ("eq", self.name, v)

    conditions.Key = _Attr
    conditions.Attr = _Attr
    dynamodb_mod = types.ModuleType("boto3.dynamodb")
    dynamodb_mod.conditions = conditions
    b.dynamodb = dynamodb_mod
    sys.modules["boto3"] = b
    sys.modules["boto3.dynamodb"] = dynamodb_mod
    sys.modules["boto3.dynamodb.conditions"] = conditions


_stub_boto3()
mon = importlib.import_module("relayshield_sim_swap_monitor")


# ---------------------------------------------------------------------------
# The defect that shipped
# ---------------------------------------------------------------------------

class TestTheSameCarrierIsNeverAPortOut(unittest.TestCase):

    def test_the_same_carrier_is_never_a_port_out(self):
        """The exact alert that reached the founder on 2026-09-16.

        Both sides are T-Mobile. A carrier does not port a number to itself,
        and a security product that says it did has spent the credibility of
        every alert after it.
        """
        self.assertFalse(
            mon.detect_port_out("T-Mobile USA", "", "T-Mobile USA", "")
        )

    def test_two_spellings_of_one_carrier_are_not_a_port_out(self):
        """line_type_intelligence and sim_swap spell the same carrier
        differently, and the lookup falls back from one to the other whenever
        a package is unavailable. That flip is the likeliest cause of the live
        alert and it must not be a verdict."""
        for stored, current in (
            ("T-Mobile USA", "T-Mobile USA, Inc."),
            ("T-Mobile USA, Inc.", "T-Mobile USA"),
            ("T-MOBILE USA", "T-Mobile USA"),
            ("T-Mobile USA ", " T-Mobile USA"),
            ("T-Mobile  USA", "T-Mobile USA"),
            ("T‑Mobile USA", "T-Mobile USA"),      # non-breaking hyphen
            ("Verizon Wireless, LLC", "Verizon Wireless"),
        ):
            with self.subTest(stored=stored, current=current):
                self.assertFalse(mon.detect_port_out(stored, "", current, ""))

    def test_a_real_carrier_change_still_fires(self):
        """The guard is worthless if it also silences the thing we sell."""
        self.assertTrue(
            mon.detect_port_out("T-Mobile USA", "", "AT&T Mobility", "")
        )

    def test_mccmnc_decides_when_both_sides_have_it(self):
        """The numeric network identity is what a port-out actually changes.
        A reformatted display name over an unchanged MCC/MNC is not one."""
        self.assertFalse(
            mon.detect_port_out("T-Mobile USA", "310-160",
                                "T-Mobile USA, Inc.", "310-160")
        )
        self.assertTrue(
            mon.detect_port_out("T-Mobile USA", "310-160",
                                "AT&T Mobility", "310-410")
        )

    def test_a_missing_baseline_is_never_a_port_out(self):
        """First observation of a number reads as "changed from nothing" under
        a naive comparison. relayshield_watchlist_monitor.py's first rule, in
        the one place where the message is CRITICAL rather than informational."""
        for stored in ("", "unknown", "   "):
            with self.subTest(stored=stored):
                self.assertFalse(mon.detect_port_out(stored, "", "T-Mobile USA", ""))

    def test_a_missing_current_read_is_never_a_port_out(self):
        """"We could not read the carrier" must never render as "it moved".
        Absence of data is not evidence of a transfer."""
        for current in ("", "unknown"):
            with self.subTest(current=current):
                self.assertFalse(mon.detect_port_out("T-Mobile USA", "310-160", current, ""))

    def test_a_half_network_identity_is_ignored(self):
        """A bare MCC is a country. Comparing countries would call a port
        between two US carriers clean."""
        self.assertEqual(mon.network_identity("310", ""), "")
        self.assertEqual(mon.network_identity("", "160"), "")
        self.assertEqual(mon.network_identity("310", "160"), "310-160")

    def test_a_stale_stored_network_without_both_halves_is_ignored(self):
        """A record written before this code existed carries whatever the old
        version put there, so the guard is applied at the read as well."""
        self.assertTrue(
            mon.detect_port_out("T-Mobile USA", "310", "AT&T Mobility", "310-410")
        )


# ---------------------------------------------------------------------------
# The rendering floor
# ---------------------------------------------------------------------------

class TestTheAlertCannotNameOneCarrierTwice(unittest.TestCase):

    def test_the_customer_alert_never_says_from_x_to_x(self):
        body = mon.build_port_out_alert_message(
            "+15550000000", "T-Mobile USA", "T-Mobile USA, Inc.", mon.TIER_PERSONAL
        )
        self.assertNotIn("to *T-Mobile USA, Inc.*", body)
        self.assertIn("transferred to a new carrier", body)

    def test_the_admin_alert_never_says_from_x_to_x(self):
        body = mon.build_admin_swap_notification(
            "Sam", "0000", "T-Mobile USA", "port_out", old_carrier="T-Mobile USA"
        )
        self.assertIn("to a new carrier", body)
        self.assertNotIn("from *T-Mobile USA* to *T-Mobile USA*", body)

    def test_a_genuine_change_still_names_both_carriers(self):
        """The floor must not flatten the useful case. Knowing WHICH carrier to
        call is the first action step in the message."""
        body = mon.build_port_out_alert_message(
            "+15550000000", "T-Mobile USA", "AT&T Mobility", mon.TIER_PERSONAL
        )
        self.assertIn("from *T-Mobile USA* to *AT&T Mobility*", body)


# ---------------------------------------------------------------------------
# The lookup carries the identity through
# ---------------------------------------------------------------------------

class TestTheLookupReadsTheNetworkIdentity(unittest.TestCase):

    def _lookup(self, payload):
        class _Resp:
            def __enter__(self_inner): return self_inner
            def __exit__(self_inner, *a): return False
            def read(self_inner): return __import__("json").dumps(payload).encode()
        with mock.patch.object(mon.urllib.request, "urlopen", return_value=_Resp()):
            return mon.call_twilio_sim_swap_lookup("+15550000000", "AC", "tok")

    def test_mcc_and_mnc_are_captured(self):
        out = self._lookup({
            "sim_swap": {"last_sim_swap": {"swapped_in_period": False}},
            "line_type_intelligence": {
                "carrier_name": "T-Mobile USA, Inc.",
                "mobile_country_code": "310",
                "mobile_network_code": "160",
            },
        })
        self.assertEqual(out["network_id"], "310-160")
        self.assertEqual(out["carrier_name"], "T-Mobile USA, Inc.")

    def test_a_missing_lti_package_yields_no_network_and_does_not_raise(self):
        """The fallback path. It must degrade to the normalised-name comparison
        rather than to an exception or to a bare MCC."""
        out = self._lookup({
            "sim_swap": {"carrier_name": "T-Mobile USA",
                         "last_sim_swap": {"swapped_in_period": False}},
        })
        self.assertEqual(out["network_id"], "")
        self.assertEqual(out["carrier_name"], "T-Mobile USA")

    def test_a_package_error_still_returns_none_rather_than_a_clean_result(self):
        """Pre-existing behaviour, pinned here because this change touched the
        same function. Twilio answers HTTP 200 with error_code 60606 when the
        SIM swap package is not enabled, and reading that as "not swapped" is
        how this product reported clean for months."""
        out = self._lookup({"sim_swap": {"error_code": 60606}})
        self.assertIsNone(out)


# ---------------------------------------------------------------------------
# The detector is the one the handler calls
# ---------------------------------------------------------------------------

class TestTheHandlerUsesTheDetector(unittest.TestCase):

    def test_process_user_does_not_compare_carrier_strings_directly(self):
        """A guard nothing calls is decoration. The original defect was a raw
        `last_known_carrier != carrier_name` inside process_user, so this
        asserts that expression is gone from its body, not merely that
        detect_port_out exists somewhere in the file."""
        tree = ast.parse(open("relayshield_sim_swap_monitor.py").read())
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "process_user")
        body = "\n".join(ast.unparse(n) for n in fn.body)
        self.assertIn("detect_port_out(", body)
        self.assertNotIn("port_out_suspected = bool(", body)

    def test_an_empty_network_read_never_erases_a_stored_baseline(self):
        """Overwriting a good MCC/MNC with "" would leave the next run with
        nothing to compare against, so a genuine port-out would pass as clean.
        Losing a baseline is a silent failure on a security product."""
        calls = {}

        class _Table:
            def update_item(self_inner, **kw):
                calls.update(kw)

        with mock.patch.object(mon.dynamodb, "Table", return_value=_Table()):
            mon.update_user_swap_state("u1", "T-Mobile USA", alert_fired=False,
                                       network_id="")
        self.assertNotIn("last_known_network", calls["UpdateExpression"])

        with mock.patch.object(mon.dynamodb, "Table", return_value=_Table()):
            mon.update_user_swap_state("u1", "T-Mobile USA", alert_fired=False,
                                       network_id="310-160")
        self.assertIn("last_known_network", calls["UpdateExpression"])
        self.assertEqual(calls["ExpressionAttributeValues"][":n"], "310-160")


if __name__ == "__main__":
    unittest.main(verbosity=2)
