"""Redirect/short-URL expansion for /v1/link-check, EXECUTED rather than grepped.

A short link is judged by its DESTINATION, not by bit.ly's reputation. These
tests run the real handlers with the network upstreams stubbed:

  - api._resolve_redirects is the seam: each test declares where a URL
    resolves (or that resolution fails), so no test touches the network.
  - GSB / RDAP / DynamoDB are stubbed exactly like
    test_muse_connector_features.py, so the batch tests run the real
    _heuristic_url_check_many fan-out, budget handling included.

The defects guarded here: a shortened link to a criminal host rendering as
"unknown" on the shortener's reputation; an unresolvable destination
rendering as a clean result; and the response shape drifting between the
single and batch forms.
"""
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
    table = unittest.mock.MagicMock()
    table.query.return_value = {"Items": []}
    table.get_item.return_value = {}
    ddb = unittest.mock.MagicMock()
    ddb.Table.return_value = table
    return ddb


def body(resp):
    return json.loads(resp["body"])


def _no_upstreams(flagged_domains=()):
    """Patch the network upstreams; the GSB verdict is caller-declared."""
    def fake_gsb(domains, key):
        return set(d for d in domains if d in flagged_domains)
    def fake_gsb_exact(urls, key):
        return set()
    return [
        unittest.mock.patch.object(api, "_gsb_flagged_domains", fake_gsb),
        unittest.mock.patch.object(api, "_gsb_flagged_exact", fake_gsb_exact),
        unittest.mock.patch.object(api, "_gsb_api_key", lambda: "k"),
        unittest.mock.patch.object(api, "_rdap_registration_age_days", lambda d: None),
        unittest.mock.patch.object(api, "dynamodb", _empty_ddb()),
    ]


def _resolve_map(mapping):
    """Stub api._resolve_redirects from a {url: (final_url, chain, error)} map.

    URLs absent from the map resolve to themselves with a single 200 hop.
    """
    def fake(url, *a, **k):
        if url in mapping:
            return mapping[url]
        return url, [{"url": url, "status": 200}], None
    return unittest.mock.patch.object(api, "_resolve_redirects", fake)


def _run(params, resolutions=None, flagged_domains=()):
    patches = _no_upstreams(flagged_domains)
    patches.append(_resolve_map(resolutions or {}))
    for p in patches:
        p.start()
    try:
        return api.handle_link_check(params)
    finally:
        for p in patches:
            p.stop()


class SingleFormRedirects(unittest.TestCase):
    def test_short_url_to_flagged_destination_is_flagged(self):
        """bit.ly -> evil.example, and GSB flags evil.example: the verdict is
        high, and the reason names the final destination, not bit.ly."""
        resolutions = {
            "https://bit.ly/abc": (
                "https://evil.example/x",
                [{"url": "https://bit.ly/abc", "status": 301},
                 {"url": "https://evil.example/x", "status": 200}],
                None),
        }
        d = body(_run({"url": "https://bit.ly/abc"},
                           resolutions, flagged_domains=("evil.example",)))["data"]
        self.assertTrue(d["flagged"])
        self.assertEqual(d["level"], "high")
        self.assertTrue(any("final destination (evil.example)" in r
                            for r in d["reasons"]),
                        f"destination flag not attributed: {d['reasons']}")
        self.assertEqual(d["final_url"], "https://evil.example/x")
        self.assertEqual(d["redirect_count"], 1)

    def test_short_url_to_clean_destination_is_unknown_with_chain(self):
        """No flags anywhere: the honest ceiling stays 'unknown', and the
        chain is in the evidence."""
        resolutions = {
            "https://bit.ly/ok": (
                "https://example.org/welcome",
                [{"url": "https://bit.ly/ok", "status": 301},
                 {"url": "https://example.org/welcome", "status": 200}],
                None),
        }
        d = body(_run({"url": "https://bit.ly/ok"}, resolutions))["data"]
        self.assertFalse(d["flagged"])
        self.assertEqual(d["level"], "unknown")
        self.assertTrue(d["checked"])
        self.assertEqual([h["url"] for h in d["redirect_chain"]],
                         ["https://bit.ly/ok", "https://example.org/welcome"])
        self.assertEqual(d["final_url"], "https://example.org/welcome")

    def test_url_without_redirects_keeps_single_hop_chain(self):
        d = body(_run({"url": "https://plain.example/"}))["data"]
        self.assertEqual(d["final_url"], "https://plain.example/")
        self.assertEqual(d["redirect_count"], 0)
        self.assertEqual(len(d["redirect_chain"]), 1)

    def test_redirect_loop_is_incomplete_never_clean(self):
        resolutions = {
            "https://loop.example/": (
                "https://loop.example/",
                [{"url": "https://loop.example/", "status": 301}],
                "redirect loop"),
        }
        d = body(_run({"url": "https://loop.example/"}, resolutions))["data"]
        self.assertIs(d["checked"], False)
        self.assertEqual(d["level"], "unknown")
        self.assertFalse(d["flagged"])
        self.assertIn("NOT fully checked", d["note"])
        # The partial hop is still evidence.
        self.assertEqual(d["redirect_chain"][0]["url"], "https://loop.example/")

    def test_resolution_timeout_is_incomplete_never_clean(self):
        resolutions = {
            "https://slow.example/": (
                "https://slow.example/", [], "redirect resolution timed out"),
        }
        d = body(_run({"url": "https://slow.example/"}, resolutions))["data"]
        self.assertIs(d["checked"], False)
        self.assertEqual(d["level"], "unknown")
        self.assertFalse(d["flagged"])
        self.assertIsNone(d["final_url"])
        for sig in d["signals"].values():
            self.assertIsNone(sig, "unresolved signals must be UNSET, not clean")

    def test_blocked_redirect_target_is_incomplete(self):
        """SSRF guard trip on a hop: the verdict degrades, it does not pass."""
        resolutions = {
            "https://s.example/": (
                "https://s.example/",
                [{"url": "https://s.example/", "status": 302}],
                "redirect target blocked: blocked non-public address"),
        }
        d = body(_run({"url": "https://s.example/"}, resolutions))["data"]
        self.assertIs(d["checked"], False)
        self.assertEqual(d["level"], "unknown")

    def test_flag_on_submitted_url_still_flags(self):
        """The submitted domain itself flagged: no redirect needed, still high."""
        d = body(_run({"url": "https://evil.example/landing"},
                           flagged_domains=("evil.example",)))["data"]
        self.assertTrue(d["flagged"])
        self.assertEqual(d["level"], "high")


class BatchFormRedirects(unittest.TestCase):
    def test_batch_flags_short_url_via_destination(self):
        resolutions = {
            "https://bit.ly/abc": (
                "https://evil.example/x",
                [{"url": "https://bit.ly/abc", "status": 301},
                 {"url": "https://evil.example/x", "status": 200}],
                None),
        }
        d = body(_run({"urls": ["https://bit.ly/abc", "https://ok.example/"]},
                           resolutions, flagged_domains=("evil.example",)))["data"]
        by = {x["target"]: x for x in d["results"]}
        self.assertTrue(by["https://bit.ly/abc"]["flagged"])
        self.assertEqual(by["https://bit.ly/abc"]["level"], "high")
        self.assertEqual(by["https://bit.ly/abc"]["final_url"],
                         "https://evil.example/x")
        self.assertEqual(by["https://bit.ly/abc"]["redirect_count"], 1)
        self.assertEqual(by["https://ok.example/"]["level"], "unknown")
        self.assertEqual(d["counts"]["flagged"], 1)

    def test_batch_chain_evidence_on_every_result(self):
        resolutions = {
            "https://bit.ly/abc": (
                "https://evil.example/x",
                [{"url": "https://bit.ly/abc", "status": 301},
                 {"url": "https://evil.example/x", "status": 200}],
                None),
        }
        d = body(_run({"urls": ["https://bit.ly/abc", "https://ok.example/"]},
                           resolutions))["data"]
        for r in d["results"]:
            self.assertIn("redirect_chain", r)
            self.assertIn("final_url", r)
            self.assertTrue(r["checked"])

    def test_batch_unresolvable_url_is_named_incomplete(self):
        resolutions = {
            "https://slow.example/": (
                "https://slow.example/", [], "redirect resolution timed out"),
        }
        d = body(_run({"urls": ["https://slow.example/", "https://ok.example/"]},
                           resolutions))["data"]
        by = {x["target"]: x for x in d["results"]}
        self.assertIs(by["https://slow.example/"]["checked"], False)
        self.assertEqual(by["https://slow.example/"]["level"], "unknown")
        self.assertIn("https://slow.example/", d["incomplete_urls"])
        self.assertEqual(d["counts"]["incomplete"], 1)
        self.assertEqual(d["counts"]["checked"], 1)
        self.assertTrue(by["https://ok.example/"]["checked"])

    def test_batch_too_many_hops_is_incomplete(self):
        chain = [{"url": f"https://h{i}.example/", "status": 302}
                 for i in range(6)]
        resolutions = {
            "https://h0.example/": (
                "https://h0.example/", chain, "too many redirects (>5)"),
        }
        d = body(_run({"urls": ["https://h0.example/"]}, resolutions))["data"]
        self.assertIs(d["results"][0]["checked"], False)
        self.assertIn("https://h0.example/", d["incomplete_urls"])
        self.assertEqual(len(d["results"][0]["redirect_chain"]), 6,
                         "partial hops must stay in the evidence")

    def test_batch_never_returns_low_or_safe(self):
        d = body(_run({"urls": ["https://bit.ly/abc", "https://ok.example/"]}))["data"]
        for r in d["results"]:
            self.assertIn(r["level"], ("high", "medium", "unknown"))
            self.assertNotIn(r["level"], ("low", "safe", "clean"))

    def test_batch_dedupes_shared_destinations(self):
        """Two short links to one criminal host: one domain assessment."""
        resolutions = {
            "https://bit.ly/a": ("https://evil.example/1",
                                 [{"url": "https://bit.ly/a", "status": 301},
                                  {"url": "https://evil.example/1", "status": 200}],
                                 None),
            "https://bit.ly/b": ("https://evil.example/2",
                                 [{"url": "https://bit.ly/b", "status": 301},
                                  {"url": "https://evil.example/2", "status": 200}],
                                 None),
        }
        d = body(_run({"urls": ["https://bit.ly/a", "https://bit.ly/b"]},
                           resolutions, flagged_domains=("evil.example",)))["data"]
        self.assertEqual(d["counts"]["flagged"], 2)
        self.assertTrue(all(r["checked"] for r in d["results"]))


class ResolverUnit(unittest.TestCase):
    """The redirect-only follower itself, with a fake opener. No network."""

    def _fake(self, routes, host_check=None):
        import urllib.error
        import relayshield_scamkit_fetch as fetch

        class FakeResp:
            def __init__(self, status, headers):
                self.status = status
                self.headers = headers
            def getcode(self):
                return self.status
            def close(self):
                pass

        class FakeOpener:
            def open(self, req, timeout=None):
                u = req.full_url
                if u not in routes:
                    raise urllib.error.URLError("no route")
                status, headers = routes[u]
                return FakeResp(status, headers)

        return lambda url, **kw: fetch.resolve_redirects(
            url, opener=FakeOpener(),
            host_check=host_check or (lambda h: (True, "")),
            overall_timeout=5.0, **kw)

    def test_follows_chain_and_records_hops(self):
        resolve = self._fake({
            "https://bit.ly/abc": (301, {"Location": "https://evil.example/x"}),
            "https://evil.example/x": (200, {}),
        })
        final, chain, err = resolve("https://bit.ly/abc")
        self.assertIsNone(err)
        self.assertEqual(final, "https://evil.example/x")
        self.assertEqual([h["status"] for h in chain], [301, 200])

    def test_relative_location_is_resolved(self):
        resolve = self._fake({
            "https://s.example/a": (302, {"Location": "/b"}),
            "https://s.example/b": (200, {}),
        })
        final, chain, err = resolve("https://s.example/a")
        self.assertIsNone(err)
        self.assertEqual(final, "https://s.example/b")

    def test_loop_is_an_error_not_a_hang(self):
        resolve = self._fake({
            "https://l.example/": (301, {"Location": "https://l.example/"}),
        })
        _final, chain, err = resolve("https://l.example/")
        self.assertEqual(err, "redirect loop")
        self.assertEqual(len(chain), 1)

    def test_too_many_hops_is_an_error(self):
        routes = {f"https://h{i}.example/": (302, {"Location": f"https://h{i+1}.example/"})
                  for i in range(7)}
        resolve = self._fake(routes)
        _final, chain, err = resolve("https://h0.example/", max_hops=5)
        self.assertIn("too many redirects", err)
        self.assertLessEqual(len(chain), 6)

    def test_redirect_to_internal_ip_is_blocked(self):
        resolve = self._fake(
            {"https://s.example/": (302, {"Location": "http://169.254.169.254/"})},
            host_check=lambda h: (False, "blocked non-public")
            if h == "169.254.169.254" else (True, ""))
        _final, chain, err = resolve("https://s.example/")
        self.assertIn("blocked", err)
        self.assertEqual(len(chain), 1)

    def test_non_http_target_stops_cleanly(self):
        resolve = self._fake({
            "https://a.example/": (302, {"Location": "myapp://open"}),
        })
        final, _chain, err = resolve("https://a.example/")
        self.assertIsNone(err)
        self.assertEqual(final, "https://a.example/")

    def test_head_rejection_falls_back_to_get(self):
        import urllib.error
        import relayshield_scamkit_fetch as fetch

        class FakeResp:
            status = 200
            headers = {}
            def getcode(self):
                return 200
            def close(self):
                pass

        calls = []

        class FakeOpener:
            def open(self, req, timeout=None):
                calls.append(req.get_method())
                if req.get_method() == "HEAD":
                    raise urllib.error.HTTPError(
                        req.full_url, 405, "Method Not Allowed", {}, None)
                return FakeResp()

        final, _chain, err = fetch.resolve_redirects(
            "https://nohead.example/", opener=FakeOpener(),
            host_check=lambda h: (True, ""), overall_timeout=5.0)
        self.assertIsNone(err)
        self.assertEqual(final, "https://nohead.example/")
        self.assertEqual(calls, ["HEAD", "GET"])


if __name__ == "__main__":
    unittest.main()
