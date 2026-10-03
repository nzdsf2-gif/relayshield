"""The two verdict gaps from the 2026-09-30 live plugin test, EXECUTED not grepped.

Gap 1 -- IANA-reserved names must never be flagged. example.com returned
FLAGGED/high because the criminal IOC corpus holds rows keyed on it (threat
reports quote it as a placeholder). The fix short-circuits reserved names
BEFORE any signal is gathered: no corpus hit, no Safe Browsing, no RDAP --
so the corpus query must not even run for them.

Gap 2 -- corpus-miss lookalike. paypa1-secure.com drew no corpus match and
left as "unknown" with no reason at all. On the corpus-miss path the domain
now gets one conservative brand-lookalike shot (homoglyph fold + single-edit
resemblance against the email check's brand table); a hit grades "medium".

The never-say-safe framing is asserted throughout: no verdict may say
"safe", and no level may be "low" -- the best case stays "no flags found"
with caveats. Upstreams (GSB / RDAP / DynamoDB / redirect resolution) are
stubbed; the handlers under test are real.
"""
import json
import pathlib
import re
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


def _ddb(items):
    table = unittest.mock.MagicMock()
    table.query.return_value = {"Items": items}
    table.get_item.return_value = {}
    ddb = unittest.mock.MagicMock()
    ddb.Table.return_value = table
    return ddb, table


def _no_upstreams(items=()):
    ddb, table = _ddb(items)
    patches = [
        unittest.mock.patch.object(api, "_gsb_flagged_domains",
                                   lambda domains, key: set()),
        unittest.mock.patch.object(api, "_gsb_flagged_exact",
                                   lambda urls, key: set()),
        unittest.mock.patch.object(api, "_gsb_api_key", lambda: "k"),
        unittest.mock.patch.object(api, "_rdap_registration_age_days",
                                   lambda d: None),
        unittest.mock.patch.object(api, "dynamodb", ddb),
    ]
    return patches, table


def _resolve_map(mapping):
    def fake(url, *a, **k):
        if url in mapping:
            return mapping[url]
        return url, [{"url": url, "status": 200}], None
    return unittest.mock.patch.object(api, "_resolve_redirects", fake)


def _run_single(url, resolutions=None, items=()):
    patches, _ = _no_upstreams(items)
    patches.append(_resolve_map(resolutions or {}))
    for p in patches:
        p.start()
    try:
        return json.loads(api.handle_link_check({"url": url})["body"])["data"]
    finally:
        for p in patches:
            p.stop()


def _run_batch(urls, resolutions=None, items=()):
    patches, _ = _no_upstreams(items)
    patches.append(_resolve_map(resolutions or {}))
    # The batch path resolves redirects concurrently; patch the fan-out too.
    mapping = resolutions or {}
    def fake_many(urls_):
        return {u: mapping.get(u, (u, [{"url": u, "status": 200}], None))
                for u in urls_}
    patches.append(unittest.mock.patch.object(api, "_resolve_redirects_many",
                                              fake_many))
    for p in patches:
        p.start()
    try:
        return json.loads(api.handle_link_check({"urls": urls})["body"])["data"]
    finally:
        for p in patches:
            p.stop()


def _assert_never_says_safe(testcase, payload):
    """No "safe", no "low" verdict anywhere in a verdict payload.

    "Google Safe Browsing" is the vendor product's name, not a verdict, so it
    is exempted before scanning."""
    text = json.dumps(payload).lower()
    testcase.assertNotIn('"level": "low"', text)
    text = text.replace("safe browsing", "vendor-blocklist")
    for m in re.finditer(r"\bsafe\b", text):
        context = text[max(0, m.start() - 40):m.end() + 40]
        testcase.fail(f"verdict says 'safe': ...{context}...")


class ReservedNames(unittest.TestCase):
    def test_matcher_exact_and_subdomain(self):
        self.assertEqual(api._reserved_documentation_domain("example.com"),
                         "example.com")
        self.assertEqual(api._reserved_documentation_domain("mail.example.com"),
                         "example.com")
        self.assertEqual(api._reserved_documentation_domain("EXAMPLE.ORG"),
                         "example.org")

    def test_matcher_special_use_tlds(self):
        self.assertEqual(api._reserved_documentation_domain("foo.test"), ".test")
        self.assertEqual(api._reserved_documentation_domain("x.local"), ".local")
        self.assertEqual(api._reserved_documentation_domain("y.internal"),
                         ".internal")
        self.assertEqual(api._reserved_documentation_domain("localhost"),
                         "localhost")

    def test_matcher_rejects_suffix_tricks_and_real_domains(self):
        self.assertEqual(api._reserved_documentation_domain(
            "example.com.evil.com"), "")
        self.assertEqual(api._reserved_documentation_domain("paypal.com"), "")
        self.assertEqual(api._reserved_documentation_domain("myexample.com"), "")
        self.assertEqual(api._reserved_documentation_domain(""), "")

    def test_assess_domain_never_queries_corpus_for_reserved(self):
        """The corpus query must not even run: the rows keyed on example.com
        are legitimate corpus content (placeholders in threat reports)."""
        patches, table = _no_upstreams(items=[
            {"ioc_value": "example.com", "ioc_type": "domain"}])
        for p in patches:
            p.start()
        try:
            out = api._assess_domain("example.com", False)
        finally:
            for p in patches:
                p.stop()
        table.query.assert_not_called()
        self.assertFalse(out["flagged"])
        self.assertEqual(out["signals"]["ioc_corpus"], False)
        self.assertTrue(any("IANA-reserved" in r for r in out["reasons"]))
        self.assertEqual(api._link_check_level(out["signals"]), "unknown")
        _assert_never_says_safe(self, out)

    def test_single_link_check_example_com_is_unknown_not_high(self):
        """The 2026-09-30 live failure: example.com was FLAGGED/high."""
        out = _run_single("https://example.com", items=[
            {"ioc_value": "example.com", "ioc_type": "domain"}])
        self.assertFalse(out["flagged"])
        self.assertEqual(out["level"], "unknown")
        self.assertTrue(any("IANA-reserved" in r for r in out["reasons"]))
        _assert_never_says_safe(self, out)

    def test_batch_reserved_descendant_is_unknown(self):
        out = _run_batch(["https://docs.example.net", "https://sub.test/x"],
                         items=[{"ioc_value": "docs.example.net",
                                 "ioc_type": "domain"}])
        for entry in out["results"]:
            self.assertFalse(entry["flagged"])
            self.assertEqual(entry["level"], "unknown")
        _assert_never_says_safe(self, out)


class LookalikeHeuristic(unittest.TestCase):
    def test_pure_helpers(self):
        self.assertEqual(api._lookalike_brand_hit("paypa1-secure.com"), "paypal")
        self.assertEqual(api._lookalike_brand_hit("paypla.com"), "paypal")
        self.assertEqual(api._lookalike_brand_hit("login-paypal.com"), "paypal")
        self.assertEqual(api._lookalike_brand_hit("micros0ft-login.com"),
                         "microsoft")
        self.assertEqual(api._lookalike_brand_hit("secure.appleid.verify.com"),
                         "apple")

    def test_official_brand_domains_never_hit(self):
        self.assertEqual(api._lookalike_brand_hit("paypal.com"), "")
        self.assertEqual(api._lookalike_brand_hit("secure.paypal.com"), "")
        self.assertEqual(api._lookalike_brand_hit("login.microsoft.com"), "")
        self.assertEqual(api._lookalike_brand_hit("accounts.google.com"), "")

    def test_unrelated_domains_stay_silent(self):
        self.assertEqual(api._lookalike_brand_hit("totally-unrelated-site.org"),
                         "")
        self.assertEqual(api._lookalike_brand_hit("myblog123.net"), "")
        self.assertEqual(api._lookalike_brand_hit("example.com"), "")

    def test_assess_domain_corpus_miss_flags_lookalike_medium(self):
        patches, _ = _no_upstreams(items=[])
        for p in patches:
            p.start()
        try:
            out = api._assess_domain("paypa1-secure.com", False)
        finally:
            for p in patches:
                p.stop()
        self.assertTrue(out["flagged"])
        self.assertEqual(out["signals"]["lookalike"], "paypal")
        self.assertEqual(api._link_check_level(out["signals"]), "medium")
        self.assertTrue(any("paypal" in r for r in out["reasons"]))
        _assert_never_says_safe(self, out)

    def test_assess_domain_corpus_hit_skips_lookalike(self):
        """Corpus-hit path is unchanged: the heuristic only acts on a miss."""
        patches, _ = _no_upstreams(items=[
            {"ioc_value": "paypa1-secure.com", "ioc_type": "domain"}])
        for p in patches:
            p.start()
        try:
            out = api._assess_domain("paypa1-secure.com", False)
        finally:
            for p in patches:
                p.stop()
        self.assertTrue(out["flagged"])
        self.assertEqual(out["signals"]["lookalike"], "")
        self.assertEqual(api._link_check_level(out["signals"]), "high")

    def test_unresolvable_lookalike_is_caught_medium(self):
        """The 2026-09-30 live failure: paypa1-secure.com never resolved
        (DNS), so the corpus was never consulted. The submitted domain still
        gets the lookalike check -- a hit is a medium warning, and the
        NOT-fully-checked note stays."""
        out = _run_single(
            "https://paypa1-secure.com",
            resolutions={"https://paypa1-secure.com":
                         ("https://paypa1-secure.com", [],
                          "target blocked: dns resolution failed")})
        self.assertTrue(out["flagged"])
        self.assertEqual(out["level"], "medium")
        self.assertEqual(out["signals"]["lookalike"], "paypal")
        self.assertIn("NOT fully checked", out["note"])
        _assert_never_says_safe(self, out)

    def test_unresolvable_reserved_stays_silent(self):
        out = _run_single(
            "https://example.com",
            resolutions={"https://example.com":
                         ("https://example.com", [], "dns resolution failed")})
        self.assertFalse(out["flagged"])
        self.assertEqual(out["level"], "unknown")
        _assert_never_says_safe(self, out)

    def test_unresolvable_unrelated_stays_unknown(self):
        out = _run_single(
            "https://random-xyz123-no-brand.net",
            resolutions={"https://random-xyz123-no-brand.net":
                         ("https://random-xyz123-no-brand.net", [],
                          "dns resolution failed")})
        self.assertFalse(out["flagged"])
        self.assertEqual(out["level"], "unknown")
        self.assertEqual(out["signals"]["lookalike"], None)
        _assert_never_says_safe(self, out)

    def test_batch_mixed_verdicts(self):
        out = _run_batch(
            ["https://paypa1-secure.com",
             "https://example.com",
             "https://random-xyz123-no-brand.net"],
            resolutions={
                "https://paypa1-secure.com":
                    ("https://paypa1-secure.com", [], "dns resolution failed"),
                "https://random-xyz123-no-brand.net":
                    ("https://random-xyz123-no-brand.net", [],
                     "dns resolution failed"),
            })
        by_target = {e["target"]: e for e in out["results"]}
        self.assertTrue(by_target["https://paypa1-secure.com"]["flagged"])
        self.assertEqual(by_target["https://paypa1-secure.com"]["level"],
                         "medium")
        self.assertFalse(by_target["https://example.com"]["flagged"])
        self.assertEqual(by_target["https://example.com"]["level"], "unknown")
        self.assertFalse(
            by_target["https://random-xyz123-no-brand.net"]["flagged"])
        self.assertEqual(
            by_target["https://random-xyz123-no-brand.net"]["level"], "unknown")
        self.assertEqual(out["counts"]["flagged"], 1)
        _assert_never_says_safe(self, out)

    def test_legitimate_brand_link_unaffected(self):
        """A real brand login page keeps its verdict: no lookalike noise."""
        out = _run_single("https://www.paypal.com/signin")
        self.assertEqual(api._link_check_level(out["signals"]), "unknown")
        self.assertFalse(out["flagged"])
        _assert_never_says_safe(self, out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
