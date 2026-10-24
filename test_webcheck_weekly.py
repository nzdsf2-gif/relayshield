"""Tests for the Free Webcheck section added to relayshield_weekly_metrics.py.

Run from the repo root:  python3 test_webcheck_weekly.py
No AWS access: boto3 is stubbed in sys.modules before the module is imported,
and urllib.request.urlopen is mocked per test.

Scope note: _build_email renders the whole weekly email, so fabricating its
full metrics dict here would be brittle against unrelated sections. These
tests therefore cover the webcheck pieces directly (_webcheck_stats and
_webcheck_section_html) plus static wiring assertions that _build_email and
lambda_handler actually include them.
"""

import io
import json
import os
import sys
import types
import unittest
from unittest import mock
from urllib.error import URLError

# --- stub boto3 before importing the module under test -----------------------
boto3_stub = types.ModuleType("boto3")
boto3_stub.resource = mock.MagicMock()
boto3_stub.client = mock.MagicMock()
conditions_stub = types.ModuleType("boto3.dynamodb.conditions")
conditions_stub.Attr = lambda name: mock.MagicMock(name="Attr(%s)" % name)
dynamodb_stub = types.ModuleType("boto3.dynamodb")
dynamodb_stub.conditions = conditions_stub
boto3_stub.dynamodb = dynamodb_stub
sys.modules["boto3"] = boto3_stub
sys.modules["boto3.dynamodb"] = dynamodb_stub
sys.modules["boto3.dynamodb.conditions"] = conditions_stub

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import relayshield_weekly_metrics as m  # noqa: E402


class FakeResp:
    def __init__(self, payload):
        self._data = payload if isinstance(payload, bytes) else payload.encode("utf-8")

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


METRICS_PAYLOAD = {
    "available": True,
    "checks_total": 123,
    "checks_by_type": {"link": 90, "wallet": 20, "email": 10, "upload": 3},
    "conversions_total": {"tg": 40, "wa": 25, "miniapp": 5},
    "last_7_days": {
        "checks": 50,
        "conversions": 12,
        "conversions_by_dest": {"tg": 8, "wa": 3, "miniapp": 1},
        "conversion_rate": 24.0,
    },
}


class TestWebcheckStats(unittest.TestCase):
    def test_success_sanitises(self):
        seen = {}

        def fake_urlopen(req, timeout=None):
            seen["url"] = req.full_url
            seen["timeout"] = timeout
            seen["ua"] = req.headers.get("User-agent") or req.headers.get("User-Agent")
            return FakeResp(json.dumps(METRICS_PAYLOAD))

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            stats = m._webcheck_stats()
        self.assertEqual(seen["url"], "https://relayshield.net/check/metrics")
        self.assertEqual(seen["timeout"], 10)
        self.assertTrue(stats["available"])
        self.assertEqual(stats["checks_total"], 123)
        self.assertEqual(stats["checks_by_type"]["upload"], 3)
        self.assertEqual(stats["checks_7d"], 50)
        self.assertEqual(stats["conversions_7d"]["tg"], 8)
        self.assertEqual(stats["conversion_rate_7d"], 24.0)

    def test_unreachable_returns_unavailable(self):
        with mock.patch("urllib.request.urlopen", side_effect=URLError("down")):
            self.assertEqual(m._webcheck_stats(), {"available": False})

    def test_unavailable_payload_returns_unavailable(self):
        with mock.patch(
            "urllib.request.urlopen",
            return_value=FakeResp(json.dumps({"available": False})),
        ):
            self.assertEqual(m._webcheck_stats(), {"available": False})

    def test_malformed_json_returns_unavailable(self):
        with mock.patch(
            "urllib.request.urlopen", return_value=FakeResp("not json{{")
        ):
            self.assertEqual(m._webcheck_stats(), {"available": False})

    def test_odd_types_coerce_to_zero(self):
        payload = {
            "available": True,
            "checks_total": "many",
            "checks_by_type": {"link": "12"},
            "last_7_days": {"checks": None, "conversion_rate": "n/a"},
        }
        with mock.patch(
            "urllib.request.urlopen",
            return_value=FakeResp(json.dumps(payload)),
        ):
            stats = m._webcheck_stats()
        self.assertTrue(stats["available"])
        self.assertEqual(stats["checks_total"], 0)
        self.assertEqual(stats["checks_by_type"]["link"], 12)
        self.assertEqual(stats["checks_by_type"]["wallet"], 0)
        self.assertEqual(stats["checks_7d"], 0)
        self.assertEqual(stats["conversion_rate_7d"], 0)


class TestWebcheckSection(unittest.TestCase):
    def test_available_renders_rows(self):
        stats = {
            "available": True,
            "checks_total": 123,
            "checks_7d": 50,
            "checks_by_type": {"link": 90, "wallet": 20, "email": 10, "upload": 3},
            "conversions_total": {"tg": 40, "wa": 25, "miniapp": 5},
            "conversions_7d": {"tg": 8, "wa": 3, "miniapp": 1},
            "conversion_rate_7d": 24.0,
        }
        html = m._webcheck_section_html(stats)
        self.assertIn("Free Webcheck (relayshield.net/check)", html)
        self.assertIn("Checks (last 7 days)", html)
        self.assertIn("<b>50</b>", html)
        self.assertIn("Telegram bot", html)
        self.assertIn("8 / 40", html)
        self.assertIn("Conversion rate (last 7 days)", html)
        self.assertIn("24%", html)

    def test_unavailable_renders_fallback(self):
        html = m._webcheck_section_html({"available": False})
        self.assertIn("Free Webcheck (relayshield.net/check)", html)
        self.assertIn("unreachable", html)

    def test_missing_or_empty_input_never_raises(self):
        for bad in ({}, None, {"available": True}, {"available": True, "checks_by_type": None}):
            html = m._webcheck_section_html(bad)
            self.assertIn("Free Webcheck (relayshield.net/check)", html)


class TestWiring(unittest.TestCase):
    def test_build_email_and_handler_include_webcheck(self):
        with open(m.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('"webcheck":', src)
        self.assertIn("_webcheck_stats()", src)
        self.assertIn("{webcheck_section}", src)
        self.assertIn("_webcheck_section_html", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
