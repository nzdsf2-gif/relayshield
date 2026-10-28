"""Tests for the 2026-10-27 weekly metrics settlement visibility patch.

Covers _x402_stats only: HF rows excluded, all endpoints listed,
recent settlements newest first with truncated payer and tx_hash,
and _build_email rendering with the new keys and with old fixtures.
Uses the same boto3 stub pattern as test_weekly_metrics.py.
"""
import pathlib
import sys
import types
import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent


def _stub_aws():
    boto3 = types.ModuleType("boto3")
    boto3.__path__ = []
    boto3.resource = lambda *a, **k: unittest.mock.MagicMock()
    boto3.client = lambda *a, **k: unittest.mock.MagicMock()
    conditions = types.ModuleType("boto3.dynamodb.conditions")
    conditions.Attr = lambda name: unittest.mock.MagicMock()
    conditions.Key = lambda *a, **k: unittest.mock.MagicMock()
    dynamodb_mod = types.ModuleType("boto3.dynamodb")
    dynamodb_mod.__path__ = []
    dynamodb_mod.conditions = conditions
    boto3.dynamodb = dynamodb_mod
    sys.modules.setdefault("boto3", boto3)
    sys.modules.setdefault("boto3.dynamodb", dynamodb_mod)
    sys.modules.setdefault("boto3.dynamodb.conditions", conditions)
    sys.modules.setdefault("boto3.session", types.ModuleType("boto3.session"))
    bc = types.ModuleType("botocore")
    bc.__path__ = []
    ex = types.ModuleType("botocore.exceptions")

    class _CE(Exception):
        pass

    ex.ClientError = _CE
    ex.BotoCoreError = _CE
    bc.exceptions = ex
    sys.modules.setdefault("botocore", bc)
    sys.modules.setdefault("botocore.exceptions", ex)


_stub_aws()
sys.path.insert(0, str(ROOT))
import relayshield_weekly_metrics as wm  # noqa: E402


class _FakeTable:
    PAGE_SIZE = 2

    def __init__(self, items):
        self.items = items

    def scan(self, FilterExpression=None, Select=None, ExclusiveStartKey=None, **kwargs):
        start = (ExclusiveStartKey or {}).get("offset", 0)
        page = self.items[start:start + self.PAGE_SIZE]
        result = {"Items": page, "Count": len(page)}
        if start + self.PAGE_SIZE < len(self.items):
            result["LastEvaluatedKey"] = {"offset": start + self.PAGE_SIZE}
        return result


class _FakeDynamo:
    def __init__(self, tables):
        self._tables = tables

    def Table(self, name):
        return self._tables.get(name, _FakeTable([]))


def _row(path, amount, ts, payer="0xabcdef1234567890abcdef1234567890", tx="0x1234567890abcdef1234567890abcdef", source=None):
    r = {
        "path": path,
        "amount_usd": amount,
        "timestamp": ts,
        "network": "eip155:8453",
        "payer": payer,
        "tx_hash": tx,
    }
    if source is not None:
        r["source"] = source
    return r


class X402Stats(unittest.TestCase):
    def test_excludes_hf_rows_and_lists_all_endpoints(self):
        now = datetime.now(timezone.utc)
        recent = now.isoformat()
        old = (now - timedelta(days=10)).isoformat()
        items = [
            _row("/v1/payg/domain", 0.5, recent),
            _row("/v1/payg/breach", 0.1, recent),
            _row("/v1/payg/domain", 0.5, old),
            _row("/v1/payg/domain", 0.5, recent, source="hf-mcp-space"),
        ]
        wm.dynamodb = _FakeDynamo({"relayshield_payg_settlements": _FakeTable(items)})
        stats = wm._x402_stats()
        self.assertEqual(stats["total_calls"], 3)
        self.assertEqual(stats["total_revenue"], 1.1)
        self.assertEqual(stats["calls_this_week"], 2)
        self.assertEqual(len(stats["all_endpoints"]), 2)
        self.assertEqual(stats["all_endpoints"][0]["path"], "/v1/payg/domain")
        self.assertEqual(len(stats["recent_settlements"]), 3)
        self.assertEqual(stats["recent_settlements"][0]["timestamp"], recent)
        self.assertIn("...", stats["recent_settlements"][0]["payer_short"])
        self.assertIn("...", stats["recent_settlements"][0]["tx_hash_short"])

    def test_email_renders_new_section_and_old_fixture(self):
        # Reuse the existing EmailRendering fixture from test_weekly_metrics,
        # so this test tracks whatever keys the current _build_email requires
        # on Mac, instead of hand-building a fixture that drifts. The previous
        # version missed users_by_channel, which Mac _build_email accesses at
        # line 1301 for the WhatsApp row, and that key was added after the VM
        # copy of the weekly file was taken.
        from test_weekly_metrics import EmailRendering
        fixture = EmailRendering()._fixture(
            x402={"total_calls": 1, "calls_this_week": 1, "total_revenue": 0.5,
                   "revenue_this_week": 0.5, "top_endpoints": [],
                   "all_endpoints": [{"path": "/v1/payg/domain", "calls": 1, "revenue": 0.5}],
                   "recent_settlements": [{"timestamp": "2026-10-27T05:02:34", "path": "/v1/payg/domain",
                                           "amount_usd": 0.5, "network": "eip155:8453",
                                           "payer_short": "0xcbc53981...65f789", "tx_hash_short": "0xd99087cf...ebf1728"}]},
        )
        html = wm._build_email(fixture)
        self.assertIn("last 90 days, table TTL", html)
        self.assertIn("All endpoints by revenue", html)
        self.assertIn("Recent settlements (last 20", html)
        self.assertIn("/v1/payg/domain", html)


if __name__ == "__main__":
    unittest.main()
