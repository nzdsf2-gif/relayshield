"""POST /v1/telemetry/mcp-proxy, through lambda_handler.

The property that matters most: an open endpoint that accepts indicators must
never write them to the IOC corpus. Indicators are claims, not findings.
"""
import ast
import json
import pathlib
import sys
import unittest
import unittest.mock as mock

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import test_muse_connector_features  # noqa: F401,E402  (installs the boto3 stubs)
import relayshield_api as api  # noqa: E402
from mcp_proxy import taxonomy, telemetry  # noqa: E402

INSTALL = "a" * 32
H = "b" * 64


class Fake:
    def __init__(self):
        self.tables, self.puts, self.updates, self.fail_all, self.fail_rate = set(), [], [], False, False
        self.rate = {}

    def Table(self, name):
        outer = self
        outer.tables.add(name)

        class T:
            def put_item(self, Item):
                if outer.fail_all:
                    raise RuntimeError("down")
                outer.puts.append(Item)

            def update_item(self, **kw):
                pk = kw["Key"]["pk"]
                if pk.startswith("RATE#"):
                    if outer.fail_rate:
                        raise RuntimeError("down")
                    outer.rate[pk] = outer.rate.get(pk, 0) + 1
                    return {"Attributes": {"n": outer.rate[pk]}}
                if outer.fail_all:
                    raise RuntimeError("down")
                outer.updates.append(kw)
                return {}
        return T()


def report(**over):
    r = {"install_id": INSTALL, "mode": "counts", "taxonomy_version": "2026-10-10",
         "counts": [{"category": "prompt_injection", "taxonomy_id": "mcp_2026_015_prompt_injection",
                     "kind": "discovery", "n": 3}]}
    r.update(over)
    return r


def post(body, key=None):
    headers = {"X-RS-API-KEY": key} if key else {}
    ev = {"path": "/v1/telemetry/mcp-proxy", "httpMethod": "POST", "body": json.dumps(body),
          "headers": headers, "requestContext": {"identity": {"sourceIp": "1.2.3.4"}}}
    r = api.lambda_handler(ev, None)
    return r["statusCode"], json.loads(r["body"])


class Base(unittest.TestCase):
    def setUp(self):
        self.db = Fake()
        for target, val in ((api, "dynamodb"),):
            p = mock.patch.object(target, val, self.db)
            p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(api, "_verify_rs_api_key",
                              lambda k: {"api_key": k, "active": True} if k == "rs_live_good" else None)
        p.start(); self.addCleanup(p.stop)


class Counts(Base):
    def test_counts_are_accepted_with_no_key(self):
        st, b = post(report())
        self.assertEqual(st, 200)
        self.assertTrue(b["data"]["recorded"])
        self.assertEqual(self.db.puts[0]["pk"], f"INSTALL#{INSTALL}")
        self.assertEqual(self.db.puts[0]["counts"][0]["n"], 3)

    def test_each_bad_field_is_refused_whole_and_nothing_is_written(self):
        bad = [report(install_id="short"), report(install_id="G" * 32), report(mode="all"),
               report(counts="x"), report(counts=[{"category": "policy_deny", "taxonomy_id": "", "kind": "call", "n": 1}]),
               report(counts=[{"category": "pii_leak", "taxonomy_id": "x; DROP", "kind": "call", "n": 1}]),
               report(counts=[{"category": "pii_leak", "taxonomy_id": "", "kind": "args", "n": 1}]),
               report(counts=[{"category": "pii_leak", "taxonomy_id": "", "kind": "call", "n": 0}]),
               report(counts=[{"category": "pii_leak", "taxonomy_id": "", "kind": "call", "n": True}]),
               report(counts=[{"category": "pii_leak", "taxonomy_id": "", "kind": "call", "n": 10**9}]),
               report(counts=[report()["counts"][0]] * 101),
               report(counts=[{"category": "pii_leak", "taxonomy_id": "", "kind": "call", "n": 1, "free": "text"}][0:0] + ["str"])]
        for b in bad:
            st, _ = post(b)
            self.assertEqual(st, 400, b)
        self.assertEqual(self.db.puts, [])

    def test_a_free_text_extra_field_is_never_stored(self):
        st, _ = post(report(counts=[dict(report()["counts"][0], note="SECRET-NOTE")], extra="SECRET-EXTRA"))
        self.assertEqual(st, 200)
        self.assertNotIn("SECRET", json.dumps(self.db.puts, default=str))

    def test_empty_report_records_nothing(self):
        st, b = post(report(counts=[]))
        self.assertEqual(st, 200)
        self.assertFalse(b["data"]["recorded"])
        self.assertEqual(self.db.puts, [])

    def test_storage_failure_is_503(self):
        self.db.fail_all = True
        self.assertEqual(post(report())[0], 503)

    def test_get_is_not_served(self):
        ev = {"path": "/v1/telemetry/mcp-proxy", "httpMethod": "GET", "headers": {}, "body": None,
              "requestContext": {"identity": {"sourceIp": "1.2.3.4"}}}
        self.assertNotEqual(api.lambda_handler(ev, None)["statusCode"], 200)


class RateLimit(Base):
    def test_twelve_per_hour_then_429(self):
        for _ in range(api._MCPT_REPORTS_PER_HOUR):
            self.assertEqual(post(report())[0], 200)
        self.assertEqual(post(report())[0], 429)

    def test_per_install(self):
        for _ in range(api._MCPT_REPORTS_PER_HOUR + 1):
            post(report())
        self.assertEqual(post(report(install_id="c" * 32))[0], 200)

    def test_rate_check_fails_open(self):
        self.db.fail_rate = True
        self.assertEqual(post(report())[0], 200)


class Indicators(Base):
    IND = {"host": "evil.example.org", "payload_hash": H, "category": "prompt_injection",
           "taxonomy_id": "mcp_2026_015_prompt_injection"}

    def test_indicators_without_a_key_are_refused(self):
        st, _ = post(report(mode="indicators", indicators=[self.IND]))
        self.assertEqual(st, 401)
        self.assertEqual(self.db.puts + self.db.updates, [])

    def test_a_bad_key_is_refused(self):
        self.assertEqual(post(report(mode="indicators", indicators=[self.IND]), key="rs_live_bad")[0], 401)

    def test_indicators_land_as_unreviewed_candidates(self):
        st, b = post(report(mode="indicators", indicators=[self.IND]), key="rs_live_good")
        self.assertEqual(st, 200)
        u = self.db.updates[0]
        self.assertTrue(u["Key"]["pk"].startswith("CAND#"))
        self.assertEqual(u["ExpressionAttributeValues"][":unrev"], "unreviewed")
        self.assertIn("if_not_exists(#st", u["UpdateExpression"])  # a reviewed status is never reset
        self.assertNotIn("rs_live_good", json.dumps(u, default=str))  # reporter is hashed

    def test_the_same_claim_is_one_candidate_row(self):
        post(report(mode="indicators", indicators=[self.IND]), key="rs_live_good")
        post(report(mode="indicators", indicators=[self.IND]), key="rs_live_good")
        self.assertEqual(len({u["Key"]["pk"] for u in self.db.updates}), 1)

    def test_private_hosts_and_bad_hashes_are_refused(self):
        for bad in (dict(self.IND, host="10.0.0.1"), dict(self.IND, host="localhost"),
                    dict(self.IND, host="srv.internal"), dict(self.IND, host="HOST.Example.org"),
                    dict(self.IND, payload_hash="zz"), dict(self.IND, category="policy_deny"),
                    dict(self.IND, payload_hash="b" * 63)):
            self.assertEqual(post(report(mode="indicators", indicators=[bad]), key="rs_live_good")[0], 400, bad)

    def test_indicators_in_counts_mode_are_refused(self):
        self.assertEqual(post(report(mode="counts", indicators=[self.IND]), key="rs_live_good")[0], 400)

    def test_indicator_cap(self):
        many = [dict(self.IND, payload_hash=f"{i:064x}") for i in range(api._MCPT_MAX_INDICATORS + 1)]
        self.assertEqual(post(report(mode="indicators", indicators=many), key="rs_live_good")[0], 400)

    def test_it_never_touches_the_ioc_corpus(self):
        post(report(mode="indicators", indicators=[self.IND]), key="rs_live_good")
        self.assertEqual(self.db.tables, {api.MCP_PROXY_TELEMETRY_TABLE})
        src = (ROOT / "relayshield_api.py").read_text()
        tree = ast.parse(src)
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef) and fn.name in ("handle_mcp_proxy_telemetry", "_mcpt_validate", "_mcpt_rate_ok"):
                body = ast.get_source_segment(src, fn)
                for banned in ("INTEL_IOCS", "relayshield_intel_iocs", "_store_ioc", "first_seen_table"):
                    self.assertNotIn(banned, body, fn.name)


class ContractWithTheProxy(Base):
    """The two halves live in different packages and must agree."""

    def test_a_real_proxy_report_passes_the_real_validator(self):
        t = telemetry.Telemetry("indicators", "https://x.invalid", "k", 3600, "d" * 32,
                                sender=lambda r: None, start_thread=False)
        t.record("prompt_injection", "discovery", ["mcp_2026_015_prompt_injection", "mcp_2026_008_015_chained_prompt_injection"],
                 "https://evil.example.org/mcp", {"r": 1})
        t.record("malicious_url", "call")
        rep = t.snapshot_and_reset()
        clean, bad = api._mcpt_validate(rep, authenticated=True)
        self.assertIsNone(bad)
        self.assertEqual(len(clean["indicators"]), 2)

    def test_every_taxonomy_id_the_proxy_can_send_matches_the_server_pattern(self):
        for i in taxonomy.ENTRIES:
            self.assertRegex(i, api._MCPT_TAXID_RE.pattern)

    def test_category_and_kind_sets_agree(self):
        self.assertEqual(telemetry.REPORTABLE_CATEGORIES, api._MCPT_CATEGORIES)
        self.assertEqual(telemetry.KINDS, api._MCPT_KINDS)
        self.assertEqual(telemetry.MAX_INDICATORS_PER_REPORT, api._MCPT_MAX_INDICATORS)

    def test_the_two_public_host_checks_agree(self):
        cases = ["evil.example.org", "a.b.c.io", "8.8.8.8", "1.1.1.1", "10.0.0.1", "127.0.0.1", "169.254.169.254",
                 "localhost", "intranet", "srv.internal", "x.local", "foo.corp", "::1", "2001:4860:4860::8888",
                 "fe80::1", "a_b.example.org", "-a.example.org", "a..example.org", "example", "x.test"]
        for c in cases:
            self.assertEqual(bool(telemetry.public_host(c)), api._mcpt_public_host(c), c)


if __name__ == "__main__":
    unittest.main()
