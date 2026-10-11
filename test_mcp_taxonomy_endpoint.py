"""GET /v1/mcp-taxonomy, exercised THROUGH lambda_handler.

The dispatcher has shipped a runtime-dead defect that every handler-level test
missed (see CLAUDE.md, the 502 outage), so every request here arrives the way a
client's does. boto3 is stubbed; nothing touches AWS.
"""
import json
import pathlib
import sys
import types
import unittest
import unittest.mock as mock

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import test_muse_connector_features  # noqa: F401,E402  (installs the boto3 stubs)
import relayshield_api as api  # noqa: E402

ITEMS = [
    {"entry_id": "b", "disclosure": "MCP-2026-015", "fit": "STRONG", "poison_category": "prompt_injection",
     "attack_pattern": "pb", "description": "db", "indicators": ["i"], "mitigation": "mb",
     "taxonomy_version": "2026-10-10", "content_hash": "SECRET-HASH", "approved_by": "Andrew"},
    {"entry_id": "a", "disclosure": "MCP-2026-008", "fit": "MODERATE", "poison_category": "malicious_url",
     "attack_pattern": "pa", "description": "da", "indicators": ["i"], "mitigation": "ma",
     "taxonomy_version": "2026-10-10", "content_hash": "SECRET-HASH", "approved_by": "Andrew"},
]


class FakeTable:
    def __init__(self, pages):
        self.pages, self.calls = pages, 0

    def scan(self, **kw):
        self.calls += 1
        i = min(self.calls - 1, len(self.pages) - 1)
        out = {"Items": self.pages[i]}
        if i < len(self.pages) - 1 and self.calls <= len(self.pages) - 1:
            out["LastEvaluatedKey"] = {"entry_id": "x"}
        return out


def get(qs=None, method="GET"):
    ev = {"path": "/v1/mcp-taxonomy", "httpMethod": method, "headers": {},
          "queryStringParameters": qs, "requestContext": {"identity": {"sourceIp": "1.2.3.4"}}}
    r = api.lambda_handler(ev, None)
    return r, json.loads(r["body"])


class Endpoint(unittest.TestCase):
    def setUp(self):
        api._TAXONOMY_CACHE.update(at=0.0, items=None)
        self.table = FakeTable([ITEMS])
        p = mock.patch.object(api, "dynamodb", types.SimpleNamespace(Table=lambda n: self.table))
        p.start()
        self.addCleanup(p.stop)

    def test_public_read_needs_no_key_and_is_sorted(self):
        r, b = get()
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual([e["entry_id"] for e in b["data"]["entries"]], ["a", "b"])
        self.assertEqual(b["data"]["version"], "2026-10-10")
        self.assertEqual(r["headers"]["Access-Control-Allow-Origin"], "*")

    def test_internal_fields_are_not_served(self):
        _, b = get()
        text = json.dumps(b)
        self.assertNotIn("SECRET-HASH", text)
        self.assertNotIn("approved_by", text)
        self.assertNotIn("content_hash", text)

    def test_filters(self):
        self.assertEqual(get({"category": "malicious_url"})[1]["data"]["count"], 1)
        self.assertEqual(get({"disclosure": "MCP-2026-015"})[1]["data"]["entries"][0]["entry_id"], "b")
        self.assertEqual(get({"fit": "strong"})[1]["data"]["count"], 1)
        self.assertEqual(get({"category": "nope"})[1]["data"]["count"], 0)

    def test_pagination_is_followed(self):
        self.table.pages = [[ITEMS[0]], [ITEMS[1]]]
        self.assertEqual(get()[1]["data"]["count"], 2)

    def test_reads_are_cached_per_container(self):
        get(); get(); get()
        self.assertEqual(self.table.calls, 1)
        api._TAXONOMY_CACHE["at"] -= api._TAXONOMY_TTL + 1
        get()
        self.assertEqual(self.table.calls, 2)

    def test_unreachable_table_is_503_not_an_empty_list(self):
        self.table.scan = mock.Mock(side_effect=RuntimeError("AccessDenied"))
        r, b = get()
        self.assertEqual(r["statusCode"], 503)
        self.assertFalse(b["ok"])

    def test_last_good_copy_is_served_when_the_table_goes_away(self):
        get()
        api._TAXONOMY_CACHE["at"] -= api._TAXONOMY_TTL + 1
        self.table.scan = mock.Mock(side_effect=RuntimeError("blip"))
        r, b = get()
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(b["data"]["count"], 2)

    def test_it_is_a_get_only_route(self):
        r, _ = get(method="POST")
        self.assertNotEqual(r["statusCode"], 200)


class Placement(unittest.TestCase):
    def test_not_in_the_keyless_scan_set(self):
        # That set adds a per-IP daily cap and a consumer advert; neither fits
        # reference data with no upstream cost.
        self.assertNotIn("/v1/mcp-taxonomy", api.KEYLESS_SCAN_ENDPOINTS)

    def test_table_name_matches_the_loader(self):
        src = (ROOT / "tools" / "load_mcp_taxonomy.py").read_text()
        self.assertIn(f'TABLE = "{api.MCP_TAXONOMY_TABLE}"', src)


if __name__ == "__main__":
    unittest.main()
