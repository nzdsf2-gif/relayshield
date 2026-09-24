"""Three features built for the Muse connector, EXECUTED rather than grepped.

1. /v1/link-check takes urls[] -- one call, one Safe Browsing request.
2. handle_breach caches, so a shared rate-limited upstream is not hit twice
   for the same address.
3. A partner key carries a daily budget against that shared upstream, and it
   FAILS CLOSED.

Every test here runs the real code with boto3 and urllib stubbed. This file
exists because the defects it guards are all runtime-only: an ordering, a
fail-open, and a partial result rendering as a clean one. None of them is
visible to a reader of the source, which is how the first two shipped.
"""
import ast
import contextlib
import json
import pathlib
import sys
import types
import unittest
import unittest.mock

ROOT = pathlib.Path(__file__).resolve().parent


def _stub_aws():
    boto3 = types.ModuleType("boto3"); boto3.__path__ = []
    boto3.resource = lambda *a, **k: unittest.mock.MagicMock()
    boto3.client = lambda *a, **k: unittest.mock.MagicMock()
    conditions = types.ModuleType("boto3.dynamodb.conditions")
    conditions.Key = lambda *a, **k: unittest.mock.MagicMock()
    conditions.Attr = lambda *a, **k: unittest.mock.MagicMock()
    dynamodb_mod = types.ModuleType("boto3.dynamodb"); dynamodb_mod.__path__ = []
    dynamodb_mod.conditions = conditions
    boto3.dynamodb = dynamodb_mod
    sess = types.ModuleType("boto3.session")
    sys.modules.setdefault("boto3", boto3)
    sys.modules.setdefault("boto3.dynamodb", dynamodb_mod)
    sys.modules.setdefault("boto3.dynamodb.conditions", conditions)
    sys.modules.setdefault("boto3.session", sess)
    bc = types.ModuleType("botocore"); bc.__path__ = []
    ex = types.ModuleType("botocore.exceptions")
    class _CE(Exception):
        pass
    ex.ClientError = _CE; ex.BotoCoreError = _CE; bc.exceptions = ex
    sys.modules.setdefault("botocore", bc)
    sys.modules.setdefault("botocore.exceptions", ex)


_stub_aws()
sys.path.insert(0, str(ROOT))
import relayshield_api as api  # noqa: E402


def _empty_ddb():
    """A DynamoDB stub whose queries return NO items.

    A bare MagicMock is the wrong stub here and it cost a real debugging round:
    `resp.get("Items")` on a MagicMock returns a truthy MagicMock, so every
    domain scored an IOC-corpus hit and every link-check test passed with a
    "high" verdict it had not earned. The failure only surfaced on the one test
    that asserted a domain should NOT be flagged.
    """
    table = unittest.mock.MagicMock()
    table.query.return_value = {"Items": []}
    table.get_item.return_value = {}
    ddb = unittest.mock.MagicMock()
    ddb.Table.return_value = table
    return ddb


def body(resp):
    return json.loads(resp["body"])


class BatchLinkCheck(unittest.TestCase):
    """One call, many URLs, deduplicated by domain."""

    def setUp(self):
        self.gsb_calls = []

    def _no_upstreams(self, flagged=()):
        """Patch the three per-domain upstreams. Records GSB call count."""
        def fake_gsb(domains, key):
            self.gsb_calls.append(list(domains))
            return set(flagged)
        return (
            unittest.mock.patch.object(api, "_gsb_flagged_domains", fake_gsb),
            unittest.mock.patch.object(api, "_gsb_api_key", lambda: "k"),
            unittest.mock.patch.object(api, "_rdap_registration_age_days", lambda d: None),
            unittest.mock.patch.object(api, "dynamodb", _empty_ddb()),
        )

    def _run(self, params, flagged=()):
        patches = self._no_upstreams(flagged)
        for p in patches:
            p.start()
        try:
            return api.handle_link_check(params)
        finally:
            for p in patches:
                p.stop()

    def test_fifty_links_across_three_domains_make_one_gsb_call(self):
        """Deduplication, not concurrency, is what makes an inbox scan cheap."""
        urls = [f"https://a.com/{i}" for i in range(20)] + \
               [f"https://b.com/{i}" for i in range(20)] + \
               [f"https://c.com/{i}" for i in range(5)]
        r = self._run({"urls": urls[:api.LINK_CHECK_MAX_URLS]})
        self.assertEqual(r["statusCode"], 200, r["body"])
        self.assertEqual(len(self.gsb_calls), 1,
                         "a batch must make exactly one Safe Browsing request")
        self.assertLessEqual(len(self.gsb_calls[0]), 3,
                             f"domains were not deduplicated: {self.gsb_calls[0]}")

    def test_every_submitted_url_comes_back_in_order(self):
        urls = ["https://a.com/1", "https://b.com/2", "https://a.com/3"]
        d = body(self._run({"urls": urls}))["data"]
        self.assertEqual([x["target"] for x in d["results"]], urls)
        self.assertEqual(d["counts"]["submitted"], 3)

    def test_a_flagged_domain_marks_every_url_on_it(self):
        d = body(self._run({"urls": ["https://bad.com/a", "https://bad.com/b",
                                     "https://ok.com/c"]},
                           flagged=("bad.com",)))["data"]
        by = {x["target"]: x for x in d["results"]}
        self.assertEqual(by["https://bad.com/a"]["level"], "high")
        self.assertEqual(by["https://bad.com/b"]["level"], "high")
        self.assertEqual(by["https://ok.com/c"]["level"], "unknown")
        self.assertEqual(d["counts"]["flagged"], 2)

    def test_it_never_returns_a_safe_or_low_level(self):
        """The ceiling on a clean result is 'unknown'. Never 'low', never 'safe'."""
        d = body(self._run({"urls": ["https://clean.example/1"]}))["data"]
        for r in d["results"]:
            self.assertIn(r["level"], ("high", "medium", "unknown"))
            self.assertNotIn(r["level"], ("low", "safe", "clean"))

    def test_the_cap_is_enforced(self):
        urls = [f"https://x{i}.com/" for i in range(api.LINK_CHECK_MAX_URLS + 1)]
        r = self._run({"urls": urls})
        self.assertEqual(r["statusCode"], 400)
        self.assertIn("at most", body(r)["error"])

    def test_the_single_url_form_is_unchanged(self):
        """Every existing caller -- the widget, the bot, the Mini App -- sends
        {"url": ...} and must get the old shape back."""
        with unittest.mock.patch.object(api, "_heuristic_url_check",
                                        lambda u: {"flagged": False, "reasons": [],
                                                   "signals": {"ioc_corpus": False,
                                                               "safe_browsing": False,
                                                               "domain_age_days": None}}):
            d = body(api.handle_link_check({"url": "https://a.com/"}))["data"]
        self.assertEqual(d["target"], "https://a.com/")
        self.assertNotIn("results", d)

    def test_a_bad_scheme_is_refused_in_both_forms(self):
        self.assertEqual(api.handle_link_check({"url": "ftp://a.com"})["statusCode"], 400)
        self.assertEqual(self._run({"urls": ["ftp://a.com"]})["statusCode"], 400)


class IncompleteIsNeverClean(unittest.TestCase):
    """The single failure this product cannot afford."""

    def test_a_domain_that_times_out_is_reported_not_silently_cleaned(self):
        """_heuristic_url_check_many returns nothing for an unfinished domain.
        The handler must mark it, not present it as checked."""
        with unittest.mock.patch.object(api, "_heuristic_url_check_many",
                                        lambda urls: {urls[0]: {
                                            "flagged": False, "reasons": [],
                                            "signals": {"ioc_corpus": None,
                                                        "safe_browsing": None,
                                                        "domain_age_days": None},
                                            "incomplete": True}}):
            d = body(api.handle_link_check({"urls": ["https://slow.com/"]}))["data"]
        self.assertEqual(d["counts"]["checked"], 0)
        self.assertEqual(d["counts"]["incomplete"], 1)
        self.assertIn("https://slow.com/", d["incomplete_urls"])
        self.assertIs(d["results"][0]["checked"], False)

    def test_unfinished_domains_are_named_not_just_counted(self):
        """A caller that cannot see WHICH were missed presents the batch as
        checked, and a link nobody looked at reads as 'nothing known'."""
        src = (ROOT / "relayshield_api.py").read_text()
        self.assertIn("incomplete_urls", src)


class QuotaCountsWorkNotRequests(unittest.TestCase):
    """A batch must not multiply the keyless cap by the batch size."""

    def test_a_batch_costs_one_unit_per_url(self):
        self.assertEqual(api._link_check_units("/v1/link-check",
                                               {"urls": ["a", "b", "c"]}), 3)

    def test_a_single_url_still_costs_one(self):
        self.assertEqual(api._link_check_units("/v1/link-check",
                                               {"url": "https://a.com"}), 1)

    def test_units_are_capped_so_a_huge_array_cannot_overflow_the_counter(self):
        self.assertEqual(
            api._link_check_units("/v1/link-check", {"urls": ["x"] * 9999}),
            api.LINK_CHECK_MAX_URLS)

    def test_other_endpoints_are_unaffected(self):
        self.assertEqual(api._link_check_units("/v1/wallet-risk",
                                               {"urls": ["a", "b"]}), 1)

    def test_the_dispatcher_actually_passes_the_units(self):
        """A guard nothing calls is decoration. Read the CALL SITE."""
        tree = ast.parse((ROOT / "relayshield_api.py").read_text())
        found = False
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "_check_keyless_ip_quota"
                    and len(node.args) == 2):
                found = True
        self.assertTrue(found, "the dispatcher calls the quota check with no unit "
                               "count, so a batch costs one unit")

    def test_the_quota_increments_by_the_unit_count(self):
        table = unittest.mock.MagicMock()
        table.update_item.return_value = {"Attributes": {"call_count": 5}}
        ddb = unittest.mock.MagicMock()
        ddb.Table.return_value = table
        with unittest.mock.patch.object(api, "dynamodb", ddb):
            api._check_keyless_ip_quota("1.2.3.4", 7)
        vals = table.update_item.call_args.kwargs["ExpressionAttributeValues"]
        self.assertEqual(vals[":n"], 7, "the counter did not add the batch size")


class BreachCache(unittest.TestCase):

    def _hibp(self, payload=None, error=None):
        """Patch the HIBP call. Returns a list recording whether it was hit."""
        hits = []

        class FakeResp:
            def __enter__(s):
                return s

            def __exit__(s, *a):
                return False

            def read(s):
                return json.dumps(payload or []).encode()

        def fake_urlopen(req, timeout=None):
            hits.append(1)
            if error:
                raise error
            return FakeResp()
        return hits, unittest.mock.patch.object(api.urllib.request, "urlopen", fake_urlopen)

    def test_a_cache_hit_never_calls_hibp(self):
        hits, patch_url = self._hibp()
        with patch_url, \
             unittest.mock.patch.object(api, "_breach_cache_get", lambda e: []), \
             unittest.mock.patch.object(api, "_hibp_api_key", lambda: "k"):
            r = api.handle_breach({"email": "a@b.com"})
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(hits, [], "HIBP was called despite a cache hit")
        self.assertIs(body(r)["data"]["cached"], True)

    def test_a_miss_calls_hibp_and_writes_the_cache(self):
        hits, patch_url = self._hibp(payload=[{"Name": "X", "Domain": "x.com"}])
        wrote = []
        with patch_url, \
             unittest.mock.patch.object(api, "_breach_cache_get", lambda e: None), \
             unittest.mock.patch.object(api, "_breach_cache_put",
                                        lambda e, s: wrote.append((e, s))), \
             unittest.mock.patch.object(api, "_hibp_api_key", lambda: "k"):
            r = api.handle_breach({"email": "a@b.com"})
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(len(hits), 1)
        self.assertEqual(len(wrote), 1, "a real verdict was not cached")
        self.assertIs(body(r)["data"]["cached"], False)

    def test_a_RATE_LIMIT_is_never_cached(self):
        """Caching a 429 as 'no breaches' serves an outage as good news."""
        err = api.urllib.error.HTTPError("u", 429, "Too Many", {}, None)
        hits, patch_url = self._hibp(error=err)
        wrote = []
        with patch_url, \
             unittest.mock.patch.object(api, "_breach_cache_get", lambda e: None), \
             unittest.mock.patch.object(api, "_breach_cache_put",
                                        lambda e, s: wrote.append(1)), \
             unittest.mock.patch.object(api, "_hibp_api_key", lambda: "k"):
            r = api.handle_breach({"email": "a@b.com"})
        self.assertEqual(r["statusCode"], 429)
        self.assertEqual(wrote, [], "an upstream failure was written to the cache")

    def test_a_502_is_never_cached(self):
        err = api.urllib.error.HTTPError("u", 503, "Down", {}, None)
        hits, patch_url = self._hibp(error=err)
        wrote = []
        with patch_url, \
             unittest.mock.patch.object(api, "_breach_cache_get", lambda e: None), \
             unittest.mock.patch.object(api, "_breach_cache_put",
                                        lambda e, s: wrote.append(1)), \
             unittest.mock.patch.object(api, "_hibp_api_key", lambda: "k"):
            r = api.handle_breach({"email": "a@b.com"})
        self.assertEqual(r["statusCode"], 502)
        self.assertEqual(wrote, [], "an upstream failure was written to the cache")

    def test_the_email_is_never_stored_in_plaintext(self):
        table = unittest.mock.MagicMock()
        ddb = unittest.mock.MagicMock()
        ddb.Table.return_value = table
        with unittest.mock.patch.object(api, "dynamodb", ddb):
            api._breach_cache_put("Someone@Example.com", [])
        item = table.put_item.call_args.kwargs["Item"]
        blob = json.dumps(item, default=str).lower()
        self.assertNotIn("someone@example.com", blob)
        self.assertEqual(item["email_hash"], api._sha256("Someone@Example.com"))

    def test_the_cache_is_case_and_whitespace_stable(self):
        self.assertEqual(api._sha256("  A@B.com "), api._sha256("a@b.com"))

    def test_a_missing_table_degrades_to_a_live_call_rather_than_an_error(self):
        ddb = unittest.mock.MagicMock()
        ddb.Table.side_effect = RuntimeError("ResourceNotFoundException")
        with unittest.mock.patch.object(api, "dynamodb", ddb):
            self.assertIsNone(api._breach_cache_get("a@b.com"))
            api._breach_cache_put("a@b.com", [])   # must not raise


class PartnerBudget(unittest.TestCase):

    def _ddb(self, count):
        table = unittest.mock.MagicMock()
        table.update_item.return_value = {"Attributes": {"call_count": count}}
        ddb = unittest.mock.MagicMock()
        ddb.Table.return_value = table
        return ddb

    def test_a_key_with_no_cap_is_completely_unaffected(self):
        """Every key issued to date. This must not change their behaviour."""
        self.assertTrue(api._check_partner_upstream_budget({"api_key": "k"}, "hibp"))
        self.assertTrue(api._check_partner_upstream_budget({}, "hibp"))
        self.assertTrue(api._check_partner_upstream_budget(None, "hibp"))

    def test_under_cap_is_allowed(self):
        with unittest.mock.patch.object(api, "dynamodb", self._ddb(5)):
            self.assertTrue(api._check_partner_upstream_budget(
                {"api_key": "k", "partner_daily_cap": 10}, "hibp"))

    def test_over_cap_is_refused(self):
        with unittest.mock.patch.object(api, "dynamodb", self._ddb(11)):
            self.assertFalse(api._check_partner_upstream_budget(
                {"api_key": "k", "partner_daily_cap": 10}, "hibp"))

    def test_it_FAILS_CLOSED(self):
        """The divergence from the two neighbouring quota checks, which fail
        open. Failing open here lets a partner starve paying customers during
        the exact blip that made the check unavailable."""
        ddb = unittest.mock.MagicMock()
        ddb.Table.side_effect = RuntimeError("dynamo down")
        with unittest.mock.patch.object(api, "dynamodb", ddb):
            self.assertFalse(api._check_partner_upstream_budget(
                {"api_key": "k", "partner_daily_cap": 10}, "hibp"))

    def test_a_garbage_cap_does_not_crash_or_silently_gate(self):
        self.assertTrue(api._check_partner_upstream_budget(
            {"api_key": "k", "partner_daily_cap": "not a number"}, "hibp"))

    def test_an_exhausted_partner_gets_429_from_the_endpoint(self):
        with unittest.mock.patch.object(api, "_breach_cache_get", lambda e: None), \
             unittest.mock.patch.object(api, "_check_partner_upstream_budget",
                                        lambda k, u: False):
            r = api.handle_breach({"email": "a@b.com"},
                                  api_key_record={"api_key": "k",
                                                  "partner_daily_cap": 1})
        self.assertEqual(r["statusCode"], 429)

    def test_a_CACHE_HIT_does_not_spend_the_budget(self):
        """The ordering that makes the cache the budget-saver. If the budget is
        charged first, it is spent on answers we already had."""
        charged = []
        with unittest.mock.patch.object(api, "_breach_cache_get", lambda e: []), \
             unittest.mock.patch.object(api, "_check_partner_upstream_budget",
                                        lambda k, u: charged.append(1) or True):
            r = api.handle_breach({"email": "a@b.com"},
                                  api_key_record={"api_key": "k",
                                                  "partner_daily_cap": 1})
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(charged, [], "a cache hit charged the partner budget")

    def test_the_budget_check_is_in_the_handler_not_just_defined(self):
        """A guard nothing calls is decoration."""
        tree = ast.parse((ROOT / "relayshield_api.py").read_text())
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "handle_breach")
        called = {n.func.id for n in ast.walk(fn)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertIn("_check_partner_upstream_budget", called)
        self.assertIn("_breach_cache_get", called)


class PartnerBudgetThroughTheDispatcher(unittest.TestCase):
    """PartnerBudget above proves _check_partner_upstream_budget itself, and
    calls handle_breach DIRECTLY. Neither proves a real partner call ever
    REACHES it: every developer -- a partner included -- is told to call
    /v1/metered/breach (see _send_key_email's own quickstart curl), and that
    path runs handle_metered_request's OWN credit/subscription/free-call gate
    BEFORE handle_breach runs at all. Without threading api_key_record
    through, a partner key with no credits, no subscription and no free
    calls left 402s at that outer gate and never reaches the budget check --
    the exact "fix landed on the endpoint in front of me, not the surface"
    shape this file is full of. These go through lambda_handler, not the
    handler, for the same reason TheOnwardRoute does.
    """

    PARTNER = {"api_key": "rs_live_muse", "active": True,
               "source": "muse_connector", "partner_daily_cap": 500}

    def _event(self):
        return {
            "path": "/v1/metered/breach", "httpMethod": "POST",
            "body": json.dumps({"email": "a@b.com"}),
            "headers": {"X-RS-API-KEY": "rs_live_muse"},
            "requestContext": {"identity": {"sourceIp": "1.2.3.4"}},
        }

    def test_a_partner_key_with_no_credits_still_reaches_the_budget_check(self):
        """Without is_partner_call this 402s at the outer billing gate and
        _check_partner_upstream_budget never runs."""
        with unittest.mock.patch.object(api, "_verify_rs_api_key", lambda k: self.PARTNER), \
             unittest.mock.patch.object(api, "_breach_cache_get", lambda e: None), \
             unittest.mock.patch.object(api, "_check_partner_upstream_budget",
                                        lambda k, u: False):
            resp = api.lambda_handler(self._event(), None)
        self.assertEqual(resp["statusCode"], 429,
                          "the budget gate never ran -- the dispatcher's own "
                          "credit/subscription/free-call gate answered instead")

    def test_handle_breach_ACTUALLY_SEES_the_real_key_record(self):
        """The regression the test above cannot catch: mocking
        _check_partner_upstream_budget to a fixed return value proves the
        dispatcher's OWN gate was bypassed, but says nothing about what
        handle_breach passed the check -- a metered_routes entry that still
        called the bare `handle_breach` function (no api_key_record) would
        pass that test too, because `None or {}` is still a dict the mock
        accepts, and the partner's actual cap would then be silently
        unenforced for real traffic. This spies on the CONTENT instead."""
        seen = []

        def spy(key_record, upstream):
            seen.append(key_record)
            return True

        with unittest.mock.patch.object(api, "_verify_rs_api_key", lambda k: self.PARTNER), \
             unittest.mock.patch.object(api, "_breach_cache_get", lambda e: None), \
             unittest.mock.patch.object(api, "_check_partner_upstream_budget", spy), \
             unittest.mock.patch.object(api, "_hibp_api_key", lambda: "k"), \
             unittest.mock.patch.object(api.urllib.request, "urlopen",
                                        lambda req, timeout=None: contextlib.nullcontext(
                                            types.SimpleNamespace(read=lambda: b"[]"))):
            resp = api.lambda_handler(self._event(), None)
        self.assertEqual(resp["statusCode"], 200)
        self.assertTrue(seen, "the budget check never ran at all")
        self.assertEqual(seen[0].get("partner_daily_cap"), 500,
                          "handle_breach saw an empty/default api_key_record, not "
                          "the real key -- the partner's cap is silently unenforced")

    def test_a_partner_key_with_no_credits_still_gets_a_real_answer(self):
        """A key with no credit_balance, no subscription and no
        free_calls_remaining must not 402 at the outer gate."""
        with unittest.mock.patch.object(api, "_verify_rs_api_key", lambda k: self.PARTNER), \
             unittest.mock.patch.object(api, "_breach_cache_get", lambda e: []):
            resp = api.lambda_handler(self._event(), None)
        self.assertEqual(resp["statusCode"], 200)

    def test_a_partner_key_is_never_charged_credits(self):
        """is_partner_call must bypass the credit-deduction branch too, not
        just the 402 gate -- a partner key legitimately has none to deduct."""
        with unittest.mock.patch.object(api, "_verify_rs_api_key", lambda k: self.PARTNER), \
             unittest.mock.patch.object(api, "_breach_cache_get", lambda e: []), \
             unittest.mock.patch.object(api, "dynamodb") as ddb:
            resp = api.lambda_handler(self._event(), None)
        self.assertEqual(resp["statusCode"], 200)
        ddb.Table.return_value.update_item.assert_not_called()

    def test_is_partner_call_is_scoped_to_breach_only(self):
        """Same shape as is_cs_mobile_call/is_llm_license_call: a
        partner_daily_cap must never unlock the rest of the metered catalog."""
        src = (ROOT / "relayshield_api.py").read_text()
        idx = src.index("is_partner_call = bool(key_record.get(PARTNER_CAP_FIELD))")
        line = src[idx:src.index("\n", idx)]
        self.assertIn('path == "/v1/metered/breach"', line)

    def test_a_non_partner_key_is_unaffected(self):
        """An ordinary free-tier key still hits the ordinary free-call path,
        not the partner bypass."""
        free_key = {"api_key": "rs_live_x", "active": True,
                    "free_calls_remaining": 5}
        with unittest.mock.patch.object(api, "_verify_rs_api_key", lambda k: free_key), \
             unittest.mock.patch.object(api, "_breach_cache_get", lambda e: []), \
             unittest.mock.patch.object(api, "dynamodb") as ddb:
            resp = api.lambda_handler(self._event(), None)
        self.assertEqual(resp["statusCode"], 200)
        ddb.Table.return_value.update_item.assert_called_once()


class GsbBatching(unittest.TestCase):

    def test_one_request_carries_every_domain(self):
        sent = []

        class FakeResp:
            def __enter__(s):
                return s

            def __exit__(s, *a):
                return False

            def read(s):
                return json.dumps({"matches": []}).encode()

        def fake_urlopen(req, timeout=None):
            sent.append(json.loads(req.data))
            return FakeResp()

        with unittest.mock.patch.object(api.urllib.request, "urlopen", fake_urlopen):
            api._gsb_flagged_domains(["a.com", "b.com", "c.com"], "k")
        self.assertEqual(len(sent), 1)
        urls = [e["url"] for e in sent[0]["threatInfo"]["threatEntries"]]
        self.assertEqual(len(urls), 6)          # http + https per domain

    def test_a_match_is_mapped_back_to_its_domain(self):
        class FakeResp:
            def __enter__(s):
                return s

            def __exit__(s, *a):
                return False

            def read(s):
                return json.dumps({"matches": [
                    {"threat": {"url": "https://bad.com/"}}]}).encode()

        with unittest.mock.patch.object(api.urllib.request, "urlopen",
                                        lambda r, timeout=None: FakeResp()):
            self.assertEqual(api._gsb_flagged_domains(["bad.com", "ok.com"], "k"),
                             {"bad.com"})

    def test_a_gsb_outage_flags_nothing_rather_than_raising(self):
        def boom(r, timeout=None):
            raise RuntimeError("gsb down")
        with unittest.mock.patch.object(api.urllib.request, "urlopen", boom):
            self.assertEqual(api._gsb_flagged_domains(["a.com"], "k"), set())

    def test_more_domains_than_fit_are_chunked_not_truncated(self):
        """A silently dropped domain reports as 'nothing known against it'."""
        sent = []

        class FakeResp:
            def __enter__(s):
                return s

            def __exit__(s, *a):
                return False

            def read(s):
                return json.dumps({"matches": []}).encode()

        def fake_urlopen(req, timeout=None):
            sent.append(json.loads(req.data))
            return FakeResp()

        n = (api._GSB_MAX_ENTRIES_PER_REQUEST // 2) + 5
        with unittest.mock.patch.object(api.urllib.request, "urlopen", fake_urlopen):
            api._gsb_flagged_domains([f"d{i}.com" for i in range(n)], "k")
        self.assertGreater(len(sent), 1, "domains beyond one chunk were dropped")
        total = sum(len(s["threatInfo"]["threatEntries"]) for s in sent)
        self.assertEqual(total, n * 2)

    def test_the_single_domain_wrapper_still_works(self):
        with unittest.mock.patch.object(api, "_gsb_flagged_domains",
                                        lambda ds, k: {"bad.com"}):
            self.assertTrue(api._check_gsb("bad.com", "k"))
            self.assertFalse(api._check_gsb("ok.com", "k"))


class TheOnwardRoute(unittest.TestCase):
    """A free check served to a partner is a check with no route back.

    Before this, nothing in relayshield_api.py named the bot, the Mini App or
    WhatsApp at all -- the note pointed at /v1/scan-url with an API key, a
    DEVELOPER upsell served to consumers. That is the inline-mode defect: live,
    working, pointed at by nothing.

    THESE GO THROUGH THE DISPATCHER, NOT THE HANDLER, and that is deliberate.
    The first version of this feature wrote the field inside the two
    link-check handlers and called the class done -- leaving /v1/wallet-risk,
    the OTHER half of the Muse connector, with no route back. Testing the
    handler would have stayed green through that. Testing the ROUTE cannot.
    """

    def _call(self, path, payload):
        ev = {"path": path, "httpMethod": "POST", "body": json.dumps(payload),
              "headers": {}, "requestContext": {"identity": {"sourceIp": "1.2.3.4"}}}
        with unittest.mock.patch.object(api, "_check_keyless_ip_quota", lambda *a, **k: True):
            return body(api.lambda_handler(ev, None))["data"]

    def _link(self, source):
        with unittest.mock.patch.object(
                api, "_heuristic_url_check",
                lambda u: {"flagged": False, "reasons": [],
                           "signals": {"ioc_corpus": False, "safe_browsing": False,
                                       "domain_age_days": None}}):
            return self._call("/v1/link-check", {"url": "https://a.com/", "source": source})

    def test_the_WIDGET_gets_no_onward_link(self):
        """relayshield-widget.js is copied into OTHER PEOPLE'S BOTS. Injecting
        'open our app' into somebody else's reply hijacks their user inside
        their own product, and is how an integration gets removed."""
        self.assertNotIn("onward", self._link("tg-widget"))

    def test_an_unnamed_source_gets_no_onward_link(self):
        self.assertNotIn("onward", self._link(""))
        self.assertNotIn("onward", self._link("some-random-caller"))

    def test_muse_gets_one_and_it_names_where_it_goes(self):
        d = self._link("muse")
        self.assertIn("onward", d)
        self.assertIn("t.me/relayshield_bot/idcheck", d["onward"]["url"])
        self.assertIn("telegram", d["onward"]["label"].lower(),
                      "a link that does not say where it goes is worse than none")

    def test_openai_gets_one_too_and_it_carries_its_own_key(self):
        """Registered 2026-09-24 alongside the OpenAI partner_daily_cap key.
        Own startapp key so the arrival is separable from muse's in the logs
        -- one key per DESTINATION, never a shared bucket two partners drown
        each other out in."""
        d = self._link("openai")
        self.assertIn("onward", d)
        self.assertIn("tg-miniapp-openai", d["onward"]["url"])
        self.assertNotIn("tg-miniapp-muse", d["onward"]["url"])

    def test_the_batch_form_carries_it_too(self):
        with unittest.mock.patch.object(
                api, "_heuristic_url_check_many",
                lambda urls: {u: {"flagged": False, "reasons": [],
                                  "signals": {"ioc_corpus": False,
                                              "safe_browsing": False,
                                              "domain_age_days": None}}
                              for u in urls}):
            d = self._call("/v1/link-check",
                           {"urls": ["https://a.com/"], "source": "muse"})
        self.assertIn("onward", d)

    def test_WALLET_RISK_carries_it_too(self):
        """The half that had none. /v1/wallet-risk is one of the connector's
        two endpoints, so a verdict from it with no route back is half the
        connector giving our answer away with nothing to come back to."""
        with unittest.mock.patch.object(api, "_detect_chain_api", lambda a: "ethereum"), \
             unittest.mock.patch.object(api, "dynamodb", _empty_ddb()), \
             unittest.mock.patch.object(api, "_screen_sanctions", lambda *a, **k: (False, [])) \
                 if hasattr(api, "_screen_sanctions") else contextlib.nullcontext():
            d = self._call("/v1/wallet-risk",
                           {"address": "0x" + "0" * 40, "source": "muse"})
        self.assertIn("onward", d,
                      "wallet-risk is half the connector and had no route back")

    def test_a_FAILED_check_carries_no_advert(self):
        """A 4xx says what went wrong. An onward link underneath it is noise,
        and it reads as a product deflecting its own failure."""
        resp = None
        ev = {"path": "/v1/wallet-risk", "httpMethod": "POST",
              "body": json.dumps({"source": "muse"}), "headers": {},
              "requestContext": {"identity": {"sourceIp": "1.2.3.4"}}}
        with unittest.mock.patch.object(api, "_check_keyless_ip_quota", lambda *a, **k: True):
            resp = api.lambda_handler(ev, None)
        self.assertNotEqual(resp["statusCode"], 200)
        self.assertNotIn("onward", resp["body"])

    def test_the_BODY_IS_PARSED_before_the_quota_reads_it(self):
        """THE LIVE DEFECT THIS CLASS FOUND, pinned as a property.

        _check_keyless_ip_quota(ip, _link_check_units(path, params)) sits ABOVE
        the try block, so an UnboundLocalError there is not caught: API Gateway
        returns 502 and no handler log line is written. It raised on every
        request to all fourteen keyless endpoints -- the widget, the Mini App,
        and both halves of the Muse connector.

        Forty-five tests were green, because every one called a HANDLER. The
        dispatcher was never exercised. Asserting the LINE ORDER is what a
        behavioural test cannot do once the bug is fixed, because by then both
        orders behave identically on the happy path.
        """
        tree = ast.parse((ROOT / "relayshield_api.py").read_text())
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "lambda_handler")
        uses = [n.lineno for n in ast.walk(fn)
                if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "_link_check_units"]
        self.assertTrue(uses, "_link_check_units is no longer called; the "
                              "keyless cap may have stopped counting units")
        # Only top-level binds count. One inside a branch that returns (the
        # /v1/app/feedback arm) does not reach the quota check at all, which is
        # precisely how this shipped looking correct.
        binds = [n.lineno for n in fn.body
                 if isinstance(n, ast.Assign)
                 and any(getattr(t, "id", "") == "params" for t in n.targets)]
        self.assertTrue(binds, "params is never bound at the top level of "
                               "lambda_handler, so the quota check reads an "
                               "unbound name and 502s")
        self.assertLess(min(binds), min(uses),
                        "params is bound AFTER the quota check reads it: "
                        "UnboundLocalError on every keyless request")

    def test_it_is_attached_in_exactly_ONE_place(self):
        """N copies of a three-line attach is N chances for one endpoint to be
        missed, which is exactly what happened. Asserted with ast rather than
        by counting a string, because a comment naming the helper is not a
        call to it."""
        tree = ast.parse((ROOT / "relayshield_api.py").read_text())
        calls = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call)
                 and getattr(n.func, "id", "") == "_onward_route"]
        # One inside _with_onward, and nowhere else.
        self.assertEqual(len(calls), 1,
                         "_onward_route is called in more than one place; the "
                         "dispatcher wrapper is the single owner")

    def test_every_onward_key_is_REGISTERED_at_the_worker_edge(self):
        """An unregistered startapp key is silently downgraded to the generic
        tg-miniapp, which is attribution that looks like it worked -- FD-8, and
        four months of it. The route and the gate are two files that must
        agree, so this reads both rather than trusting either."""
        import re
        worker = (ROOT / "cloudflare_worker_miniapp.js").read_text()
        allowed = set(re.findall(r'"(tg-miniapp[a-z0-9-]*)"', worker))
        for src, route in api.CONSUMER_ROUTES.items():
            m = re.search(r"startapp=([a-z0-9-]+)", route["url"])
            if not m:
                continue
            self.assertIn(m.group(1), allowed,
                          f"{src}'s onward key is not in ALLOWED_SOURCES, so "
                          f"every arrival through it logs as generic")

    def test_it_is_an_ALLOWLIST_not_an_echo_of_whatever_was_sent(self):
        """The property, not today's contents: a route is returned because the
        source is NAMED, never because a source was merely supplied."""
        tree = ast.parse((ROOT / "relayshield_api.py").read_text())
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "_onward_route")
        src = ast.unparse(fn)
        self.assertIn("CONSUMER_ROUTES", src)
        self.assertIn(".get(", src)


class TheSpecTheConnectorGeneratesFrom(unittest.TestCase):
    """Muse writes the integration from the OpenAPI document, so the document
    IS the integration. Two things about it are load-bearing and neither is
    visible by reading the endpoint tables.
    """

    @classmethod
    def setUpClass(cls):
        import relayshield_openapi_spec
        cls.spec = relayshield_openapi_spec.build_spec()

    def test_both_free_endpoints_are_in_it(self):
        """They were live and keyless for months and the spec listed only
        /v1/metered/*, so a partner generating a client could not see either
        of the two endpoints this connector is built on."""
        for path in ("/v1/link-check", "/v1/wallet-risk"):
            self.assertIn(path, self.spec["paths"], f"{path} missing from the spec")

    def test_the_free_endpoints_REQUIRE_NO_CREDENTIAL(self):
        """The document's top-level `security` requires an API key. An
        operation that inherits it tells every generated client that a
        credential is mandatory on an endpoint that needs none -- which is
        precisely the thing the keyless scope exists to avoid, and would have
        been found by a reviewer rather than by us.

        `security: []` is OpenAPI's explicit 'no security', distinct from
        omitting the field, which inherits.
        """
        for path in ("/v1/link-check", "/v1/wallet-risk"):
            op = self.spec["paths"][path]["post"]
            self.assertEqual(op.get("security"), [],
                             f"{path} inherits the document's security and would "
                             f"generate a client demanding an API key")

    def test_a_METERED_endpoint_still_demands_one(self):
        """The guard above must not be satisfiable by deleting security
        everywhere. A paid route with no security is a free route."""
        op = self.spec["paths"]["/v1/metered/breach"]["post"]
        self.assertTrue(op.get("security"),
                        "a metered endpoint advertising no auth is a paid route "
                        "documented as free")

    def test_link_check_documents_the_BATCH_form(self):
        """`urls` is the whole reason this connector is interesting: an agent
        reading a mailbox checks every link in one call. A spec documenting
        only `url` makes the generated client loop, which is 25x the quota."""
        props = (self.spec["paths"]["/v1/link-check"]["post"]["requestBody"]
                 ["content"]["application/json"]["schema"]["properties"])
        self.assertIn("urls", props)
        self.assertIn("url", props)


if __name__ == "__main__":
    unittest.main(verbosity=1)
