"""The shared VirusTotal allowance: budget, cache, and the unauthenticated poll leak.

Everything behavioural EXECUTES the real code with DynamoDB replaced by an in-memory
table and urllib patched, because every defect worth catching here (a poll that spends a
VT request for an id we never issued, a cache hit that still calls VT, a budget that
fails closed) is invisible to a reader of the source.
"""
import ast
import json
import pathlib
import sys
import types
import unittest
import unittest.mock as mock

ROOT = pathlib.Path(__file__).resolve().parent


def _stub_aws():
    boto3 = types.ModuleType("boto3"); boto3.__path__ = []
    boto3.resource = lambda *a, **k: mock.MagicMock()
    boto3.client = lambda *a, **k: mock.MagicMock()
    cond = types.ModuleType("boto3.dynamodb.conditions")
    cond.Key = lambda *a, **k: mock.MagicMock(); cond.Attr = lambda *a, **k: mock.MagicMock()
    ddb = types.ModuleType("boto3.dynamodb"); ddb.__path__ = []; ddb.conditions = cond
    boto3.dynamodb = ddb
    for n, m in (("boto3", boto3), ("boto3.dynamodb", ddb), ("boto3.dynamodb.conditions", cond),
                 ("boto3.session", types.ModuleType("boto3.session"))):
        sys.modules.setdefault(n, m)
    bc = types.ModuleType("botocore"); bc.__path__ = []
    ex = types.ModuleType("botocore.exceptions")

    class _CE(Exception):
        pass
    ex.ClientError = _CE; ex.BotoCoreError = _CE; bc.exceptions = ex
    sys.modules.setdefault("botocore", bc); sys.modules.setdefault("botocore.exceptions", ex)


_stub_aws()
sys.path.insert(0, str(ROOT))
import relayshield_vt_budget as vtb  # noqa: E402
import relayshield_api as api  # noqa: E402


class _Cond(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class FakeTable:
    """Just the UpdateItem forms relayshield_vt_budget uses."""
    def __init__(self):
        self.rows = {}
        self.fail = False

    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues, ConditionExpression=None,
                    ReturnValues=None):
        if self.fail:
            raise RuntimeError("dynamodb down")
        k = Key["usage_key"]
        item = self.rows.get(k)
        if ConditionExpression:
            attr = ConditionExpression[ConditionExpression.index("(") + 1:-1]
            if item is None or attr not in item:
                raise _Cond()
        item = self.rows.setdefault(k, {})
        v = ExpressionAttributeValues
        if UpdateExpression.startswith("ADD call_count"):
            item["call_count"] = item.get("call_count", 0) + 1
            item.setdefault("expires_at", v[":ttl"])
        else:
            for part in UpdateExpression[4:].split(","):
                name, val = [x.strip() for x in part.split("=")]
                item[name] = v[val]
        return {"Attributes": dict(item)}


class Base(unittest.TestCase):
    def setUp(self):
        self.t = FakeTable()
        vtb._table = lambda: self.t
        self._caps = (vtb.GLOBAL_CAP, vtb.BULK_CAP, vtb.PER_CALLER_CAP)

    def tearDown(self):
        vtb.GLOBAL_CAP, vtb.BULK_CAP, vtb.PER_CALLER_CAP = self._caps


class Budget(Base):
    def test_a_caller_cannot_take_the_whole_day(self):
        vtb.PER_CALLER_CAP = 3
        res = [vtb.charge("api", "poll", "abc12345") for _ in range(5)]
        self.assertEqual(res, [True, True, True, False, False])
        self.assertTrue(vtb.charge("api", "poll", "other999"))

    def test_bulk_surfaces_stop_early_and_the_bots_keep_a_reserve(self):
        vtb.BULK_CAP, vtb.GLOBAL_CAP = 2, 4
        self.assertTrue(vtb.charge("api", "x")); self.assertTrue(vtb.charge("api", "x"))
        self.assertFalse(vtb.charge("api", "x"), "bulk surface must be refused at its cap")
        self.assertTrue(vtb.charge("telegram", "x"), "a bot must still get through")
        self.assertTrue(vtb.charge("whatsapp", "x"))
        self.assertFalse(vtb.charge("telegram", "x"), "the global cap still applies to a bot")

    def test_it_fails_open_when_dynamodb_is_down(self):
        self.t.fail = True
        self.assertTrue(vtb.charge("api", "poll", "abc"))

    def test_only_hashes_and_counters_are_written(self):
        vtb.charge("api", "poll", vtb.caller_id("secret-key-value"))
        blob = json.dumps(self.t.rows)
        self.assertNotIn("secret-key-value", blob)


class MappingAndCache(Base):
    def test_a_miss_is_no_and_creates_no_row(self):
        self.assertEqual(vtb.mapping_check("zzz")[0], "no")
        self.assertEqual(self.t.rows, {}, "a probe must not create rows")
        self.assertIsNone(vtb.cache_get("h" * 8))
        self.assertEqual(self.t.rows, {})

    def test_a_read_error_is_error_never_no(self):
        self.t.fail = True
        self.assertEqual(vtb.mapping_check("zzz")[0], "error")

    def test_mapping_round_trips(self):
        vtb.mapping_put("an-analysis-id", "hash123")
        self.assertEqual(vtb.mapping_check("an-analysis-id"), ("yes", "hash123"))

    def test_cache_round_trips_and_flagged_lives_longer(self):
        vtb.cache_put("c" * 8, {"malicious": 0, "harmless": 70})
        vtb.cache_put("f" * 8, {"malicious": 5, "harmless": 60})
        self.assertEqual(vtb.cache_get("c" * 8), {"malicious": 0, "harmless": 70})
        self.assertGreater(self.t.rows["vtc#" + "f" * 8]["expires_at"],
                           self.t.rows["vtc#" + "c" * 8]["expires_at"])


def _resp(payload):
    r = mock.MagicMock()
    r.read.return_value = json.dumps(payload).encode()
    r.__enter__ = lambda s: s
    r.__exit__ = lambda *a: False
    return r


class ApiPaths(Base):
    def setUp(self):
        super().setUp()
        api._vt_api_key = lambda: "k"
        api._heuristic_url_check = lambda url: {"flagged": False, "reasons": []}
        api._VT_CTX.update({"surface": "api", "caller": "-"})

    def test_polling_an_id_this_api_never_issued_spends_no_vt_request(self):
        with mock.patch.object(api.urllib.request, "urlopen") as u:
            r = api.handle_result("someone-elses-analysis-id")
        self.assertEqual(r["statusCode"], 404)
        u.assert_not_called()

    def test_a_malformed_id_is_refused_before_anything(self):
        with mock.patch.object(api.urllib.request, "urlopen") as u:
            self.assertEqual(api.handle_result("../../etc/passwd")["statusCode"], 400)
        u.assert_not_called()

    def test_an_issued_id_polls_once_and_caches_the_verdict(self):
        vtb.mapping_put("issued-id-0001", "urlhash1")
        done = {"data": {"attributes": {"status": "completed",
                                        "stats": {"malicious": 0, "harmless": 60, "undetected": 5}}}}
        with mock.patch.object(api.urllib.request, "urlopen", return_value=_resp(done)) as u:
            r = api.handle_result("issued-id-0001")
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(u.call_count, 1)
        self.assertEqual(vtb.cache_get("urlhash1")["harmless"], 60)

    def test_a_cached_result_never_calls_vt(self):
        vtb.cache_put("abcd1234", {"malicious": 2, "harmless": 50})
        with mock.patch.object(api.urllib.request, "urlopen") as u:
            r = api.handle_result("rsc-abcd1234")
        self.assertEqual(json.loads(r["body"])["data"]["verdict"], "malicious")
        u.assert_not_called()

    def test_an_expired_cached_result_is_410_not_a_forever_pending(self):
        self.assertEqual(api.handle_result("rsc-nothere1")["statusCode"], 410)

    def test_a_poll_is_refused_when_the_budget_is_gone(self):
        vtb.mapping_put("issued-id-0002", "-")
        vtb.GLOBAL_CAP = 0
        with mock.patch.object(api.urllib.request, "urlopen") as u:
            r = api.handle_result("issued-id-0002")
        self.assertEqual(r["statusCode"], 503)
        u.assert_not_called()

    def test_scan_url_cache_hit_costs_no_vt_request_and_still_returns_an_id_to_poll(self):
        import hashlib
        url = "https://example.test/a"
        vtb.cache_put(hashlib.sha256(url.encode()).hexdigest(), {"malicious": 0, "harmless": 40})
        with mock.patch.object(api.urllib.request, "urlopen") as u:
            r = api.handle_scan_url({"url": url})
        u.assert_not_called()
        self.assertTrue(json.loads(r["body"])["data"]["analysis_id"].startswith("rsc-"))

    def test_scan_url_miss_submits_and_remembers_the_id(self):
        with mock.patch.object(api.urllib.request, "urlopen",
                               return_value=_resp({"data": {"id": "fresh-analysis-1"}})) as u:
            r = api.handle_scan_url({"url": "https://example.test/new"})
        self.assertEqual(u.call_count, 1)
        self.assertEqual(vtb.mapping_check("fresh-analysis-1")[0], "yes")
        self.assertEqual(r["statusCode"], 200)

    def test_scan_url_is_refused_not_silently_clean_when_the_budget_is_gone(self):
        vtb.GLOBAL_CAP = 0
        with mock.patch.object(api.urllib.request, "urlopen") as u:
            r = api.handle_scan_url({"url": "https://example.test/x"})
        self.assertEqual(r["statusCode"], 503)
        u.assert_not_called()

    def test_the_dispatcher_sets_the_caller_and_refuses_an_unknown_poll(self):
        ev = {"httpMethod": "GET", "path": "/v1/result/not-issued-id-123",
              "headers": {"X-RS-Source": "CheckEmail", "X-API-Key": "k1"}, "body": None}
        with mock.patch.object(api.urllib.request, "urlopen") as u:
            r = api.lambda_handler(ev, None)
        self.assertEqual(r["statusCode"], 404)
        u.assert_not_called()
        self.assertEqual(api._VT_CTX["surface"], "checkemail")
        self.assertEqual(api._VT_CTX["caller"], vtb.caller_id("k1"))


class AnonymousCaller(Base):
    """A caller with no key used to be "-" for everybody: indistinguishable in the log and
    exempt from the per-caller cap. It is a day-rotating six-character label now."""

    def _event(self, ip, headers=None):
        return {"httpMethod": "GET", "path": "/v1/result/not-issued-id-123", "headers": headers or {},
                "requestContext": {"identity": {"sourceIp": ip}}, "body": None}

    def test_two_sources_get_different_labels_and_one_source_gets_a_stable_one(self):
        with mock.patch.object(api.urllib.request, "urlopen"):
            api.lambda_handler(self._event("203.0.113.5"), None)
            a1 = api._VT_CTX["caller"]
            api.lambda_handler(self._event("203.0.113.5"), None)
            a2 = api._VT_CTX["caller"]
            api.lambda_handler(self._event("198.51.100.9"), None)
            b = api._VT_CTX["caller"]
        self.assertEqual(a1, a2)
        self.assertNotEqual(a1, b)
        self.assertTrue(a1.startswith("ip-") and len(a1) == 9)

    def test_the_label_never_contains_the_address(self):
        self.assertNotIn("203", vtb.anon_caller("203.0.113.5").replace("ip-", ""))
        self.assertNotIn("203.0.113.5", vtb.anon_caller("203.0.113.5"))

    def test_the_label_rotates_with_the_day(self):
        with mock.patch.object(vtb, "_day", return_value="2026-10-06"):
            a = vtb.anon_caller("203.0.113.5")
        with mock.patch.object(vtb, "_day", return_value="2026-10-07"):
            b = vtb.anon_caller("203.0.113.5")
        self.assertNotEqual(a, b)

    def test_no_source_ip_stays_unlabelled_rather_than_inventing_one(self):
        self.assertEqual(vtb.anon_caller(""), "-")

    def test_a_key_still_wins_over_the_ip(self):
        with mock.patch.object(api.urllib.request, "urlopen"):
            api.lambda_handler(self._event("203.0.113.5", {"X-API-Key": "k1"}), None)
        self.assertEqual(api._VT_CTX["caller"], vtb.caller_id("k1"))

    def test_an_anonymous_source_is_now_held_to_the_per_caller_cap(self):
        vtb.PER_CALLER_CAP = 2
        caller = vtb.anon_caller("203.0.113.5")
        self.assertTrue(vtb.charge("api", "poll", caller))
        self.assertTrue(vtb.charge("api", "poll", caller))
        self.assertFalse(vtb.charge("api", "poll", caller))
        self.assertTrue(vtb.charge("api", "poll", vtb.anon_caller("198.51.100.9")))

    def test_the_request_line_carries_the_caller_for_the_diagnostic(self):
        import re
        src = ast.unparse(ast.parse((ROOT / "relayshield_api.py").read_text(encoding="utf-8")))
        self.assertRegex(src, r"API request.{0,40}caller=%s")
        diag = (ROOT / "tools" / "diagnose_vt_usage.py").read_text()
        self.assertIn('parse @message "caller=*"', diag)


class EveryVtCallIsCharged(unittest.TestCase):
    """A VT request site with no charge() is a hole in the allowance. unparse drops
    comments, so prose that mentions the rule cannot satisfy this."""
    FILES = ["relayshield_api.py", "relayshield_telegram_webhook.py", "relayshield_whatsapp_webhook.py"]

    def test_every_function_that_calls_vt_charges_first(self):
        checked, missing = 0, []
        for f in self.FILES:
            tree = ast.parse((ROOT / f).read_text(encoding="utf-8"))
            for fn in ast.walk(tree):
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    body = ast.unparse(fn)
                    if "VT_BASE_URL" in body and "urlopen" in body:
                        checked += 1
                        if "charge(" not in body:
                            missing.append(f"{f}:{fn.name}")
        self.assertGreaterEqual(checked, 10, "guard scoped itself down to nothing")
        self.assertEqual(missing, [], f"VirusTotal request sites with no budget charge: {missing}")


if __name__ == "__main__":
    unittest.main()
