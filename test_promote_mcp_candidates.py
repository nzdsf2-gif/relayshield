"""tools/promote_mcp_candidates.py: the only path from proxy telemetry into the IOC corpus.

Every rule here is a way a wrong host could start flagging for every user, because
relayshield_api._assess_domain treats ANY domain row in relayshield_intel_iocs as a hit.
"""
import ast
import importlib.util
import pathlib
import re
import unittest
from decimal import Decimal

ROOT = pathlib.Path(__file__).resolve().parent
sp = importlib.util.spec_from_file_location("p", ROOT / "tools" / "promote_mcp_candidates.py")
p = importlib.util.module_from_spec(sp)
sp.loader.exec_module(p)

API = (ROOT / "relayshield_api.py").read_text(encoding="utf-8")
DENY = p.load_denylists(API)
NOW = "2026-10-14T00:00:00+00:00"
TID = "mcp_2026_008_015_chained_prompt_injection"


def cand(**kw):
    c = {"pk": "CAND#" + "ab12cd34" * 8, "sk": "CAND", "host": "evil-mcp.dev", "payload_hash": "a" * 64,
         "category": "prompt_injection", "taxonomy_id": TID, "reporters": {"r1", "r2"},
         "report_count": Decimal(3), "status": "unreviewed",
         "first_seen": "2026-10-10", "last_seen": "2026-10-13"}
    c.update(kw)
    return c


def blockers(**kw):
    known = kw.pop("known", False)
    return p.evaluate(cand(**kw), DENY, 2, known)


class Eligibility(unittest.TestCase):
    def test_a_good_candidate_is_eligible(self):
        b, n = blockers()
        self.assertEqual(b, [])

    def test_echo_categories_are_never_promotable(self):
        # malicious_url and kit_match come from OUR corpus; promoting them is a feedback loop.
        for cat in ("malicious_url", "kit_match"):
            b, _ = blockers(category=cat)
            self.assertTrue(any("echo" in x for x in b), cat)

    def test_non_attack_categories_are_counts_only(self):
        for cat in ("pii_leak", "secret_leak", "unknown_synthetic", "behavioral_anomaly", "attack_chain"):
            self.assertTrue(blockers(category=cat)[0], cat)

    def test_a_result_kind_finding_is_not_attributable_to_the_host(self):
        b, _ = blockers(taxonomy_id="")
        self.assertTrue(any("tool-result" in x for x in b))

    def test_reporters_are_distinct_accounts_and_anon_does_not_count(self):
        self.assertTrue(blockers(reporters={"r1"})[0])
        self.assertTrue(blockers(reporters={"r1", "anon"})[0])
        self.assertTrue(blockers(reporters=set())[0])
        # volume is not corroboration
        self.assertTrue(blockers(reporters={"r1"}, report_count=Decimal(500))[0])

    def test_test_fixture_is_blocked(self):
        self.assertTrue(any("fixture" in x for x in blockers(payload_hash="0" * 64)[0]))

    def test_reserved_and_special_use_names_are_blocked(self):
        for h in ("example.com", "sub.example.org", "box.local", "svc.internal", "x.test"):
            self.assertTrue(blockers(host=h)[0], h)

    def test_brand_domains_and_their_subdomains_are_blocked(self):
        for h in ("paypal.com", "login.paypal.com"):
            self.assertTrue(any("brand" in x for x in blockers(host=h)[0]), h)

    def test_platform_itself_is_blocked_but_a_tenant_is_allowed_with_a_note(self):
        self.assertTrue(any("platform" in x for x in blockers(host="vercel.app")[0]))
        b, notes = blockers(host="evil-app.vercel.app")
        self.assertEqual(b, [])
        self.assertTrue(any("tenant" in n for n in notes))

    def test_private_and_malformed_hosts_are_blocked(self):
        for h in ("10.0.0.5", "127.0.0.1", "nodots", "bad host.com", ""):
            self.assertTrue(blockers(host=h)[0], h)
        self.assertEqual(blockers(host="8.8.4.4")[0], [])

    def test_already_decided_or_known_is_blocked(self):
        for s in ("promoted", "rejected", "promoting"):
            self.assertTrue(blockers(status=s)[0], s)
        self.assertTrue(any("corpus" in x for x in blockers(known=True)[0]))

    def test_the_denylists_are_read_from_the_api_and_are_not_empty(self):
        self.assertIn("paypal.com", DENY["brands"])
        self.assertIn("vercel.app", DENY["platforms"])
        self.assertIn("example.com", DENY["reserved_names"])
        self.assertIn("local", DENY["reserved_tlds"])
        with self.assertRaises(RuntimeError):
            p.load_denylists("_EMAIL_BRAND_DOMAINS = {}\n_EMAIL_PUBLIC_PAGE_HOSTS = []\n"
                             "_RESERVED_DOCUMENTATION_NAMES = frozenset()\n_RESERVED_SPECIAL_TLDS = frozenset()\n")


class FakeTel:
    def __init__(self, item, fail_condition_for=None):
        self.item, self.updates, self.fail_for = dict(item), [], fail_condition_for

    def get_item(self, Key):
        return {"Item": dict(self.item)}

    def update_item(self, Key, UpdateExpression, ConditionExpression, ExpressionAttributeNames,
                    ExpressionAttributeValues):
        expect, new = ExpressionAttributeValues[":expect"], ExpressionAttributeValues[":new"]
        if self.item.get("status") != expect or self.fail_for == new:
            raise RuntimeError("ConditionalCheckFailed")
        self.item["status"] = new
        for k, v in ExpressionAttributeValues.items():
            if k.startswith(":x"):
                self.item[ExpressionAttributeNames["#x" + k[2:]]] = v
        self.updates.append(new)


class FakeIocs:
    def __init__(self, fail=False):
        self.puts, self.fail = [], fail

    def put_item(self, Item):
        if self.fail:
            raise RuntimeError("AccessDenied")
        self.puts.append(Item)


GOOD = dict(reviewer="andrew", evidence="fetched tools/list from the host and read the injected description",
            confirm_host="evil-mcp.dev")


def run(tel, iocs, apply=True, known=False, **over):
    kw = dict(GOOD, **over)
    return p.approve(tel, iocs, [cand()], "ab12cd34", deny=DENY, min_reporters=2,
                     corpus_known=lambda h: known, apply=apply, now_iso=NOW, **kw)


class Approve(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        tel, iocs = FakeTel(cand()), FakeIocs()
        row = run(tel, iocs, apply=False)
        self.assertEqual(iocs.puts, [])
        self.assertEqual(tel.updates, [])
        self.assertEqual(row["ioc_value"], "evil-mcp.dev")

    def test_apply_writes_exactly_one_labelled_row_and_marks_promoted(self):
        tel, iocs = FakeTel(cand()), FakeIocs()
        run(tel, iocs)
        self.assertEqual(len(iocs.puts), 1)
        r = iocs.puts[0]
        self.assertEqual((r["ioc_type"], r["source"], r["confidence"], r["channel"]),
                         ("domain", "mcp_proxy_telemetry", "unverified", "mcp_proxy_telemetry"))
        self.assertEqual(r["corroboration"], {"distinct_reporters": 2, "report_count": 3})
        self.assertIn("tools/list", r["evidence"])
        self.assertIsInstance(r["ttl"], Decimal)
        self.assertEqual(tel.updates, ["promoting", "promoted"])
        self.assertEqual(tel.item["status"], "promoted")

    def test_an_ip_host_is_typed_ip(self):
        c = cand(host="8.8.4.4")
        row = p.approve(FakeTel(c), FakeIocs(), [c], "ab12cd34", deny=DENY, min_reporters=2,
                        corpus_known=lambda h: False, apply=False, now_iso=NOW,
                        **dict(GOOD, confirm_host="8.8.4.4"))
        self.assertEqual(row["ioc_type"], "ip")

    def test_evidence_reviewer_and_confirm_host_are_required(self):
        for over in ({"evidence": ""}, {"evidence": "looked fine"}, {"reviewer": " "},
                     {"confirm_host": "other.dev"}, {"confirm_host": ""}):
            iocs = FakeIocs()
            with self.assertRaises(p.Refused, msg=str(over)):
                run(FakeTel(cand()), iocs, **over)
            self.assertEqual(iocs.puts, [])

    def test_blockers_are_rechecked_at_approval_not_trusted_from_the_list(self):
        iocs = FakeIocs()
        with self.assertRaises(p.Refused):
            run(FakeTel(cand(category="malicious_url")), iocs)      # fresh read is the echo category
        with self.assertRaises(p.Refused):
            run(FakeTel(cand()), iocs, known=True)
        self.assertEqual(iocs.puts, [])

    def test_a_decided_candidate_cannot_be_promoted_twice(self):
        tel, iocs = FakeTel(cand()), FakeIocs()
        run(tel, iocs)
        with self.assertRaises(p.Refused):
            run(tel, iocs)
        self.assertEqual(len(iocs.puts), 1)

    def test_a_failed_corpus_write_releases_the_candidate(self):
        tel, iocs = FakeTel(cand()), FakeIocs(fail=True)
        with self.assertRaises(p.Refused) as cm:
            run(tel, iocs)
        self.assertIn("released", str(cm.exception))
        self.assertEqual(tel.item["status"], "unreviewed")

    def test_a_failed_release_says_so_loudly(self):
        tel, iocs = FakeTel(cand(), fail_condition_for="unreviewed"), FakeIocs(fail=True)
        with self.assertRaises(p.Refused) as cm:
            run(tel, iocs)
        self.assertIn("LEFT at status=promoting", str(cm.exception))

    def test_a_lost_claim_race_writes_nothing(self):
        tel, iocs = FakeTel(cand(), fail_condition_for="promoting"), FakeIocs()
        with self.assertRaises(p.Refused):
            run(tel, iocs)
        self.assertEqual(iocs.puts, [])

    def test_prefix_must_be_unambiguous(self):
        a, b = cand(), cand(pk="CAND#ab12cd35" + "0" * 56)
        with self.assertRaises(p.Refused):
            p._resolve([a, b], "ab12cd3")        # under 8 chars
        self.assertEqual(p._resolve([a, b], "ab12cd34")["pk"], a["pk"])
        with self.assertRaises(p.Refused):
            p._resolve([a, cand(pk="CAND#ab12cd34" + "1" * 56)], "ab12cd34")
        with self.assertRaises(p.Refused):
            p._resolve([a], "ffffffff")


class Reject(unittest.TestCase):
    def test_reject_marks_rejected_and_needs_a_reason(self):
        tel = FakeTel(cand())
        p.reject(tel, [cand()], "ab12cd34", reviewer="andrew", reason="a legitimate relay", now_iso=NOW)
        self.assertEqual(tel.item["status"], "rejected")
        with self.assertRaises(p.Refused):
            p.reject(FakeTel(cand()), [cand()], "ab12cd34", reviewer="andrew", reason="", now_iso=NOW)

    def test_a_rejected_candidate_cannot_be_approved_later(self):
        tel = FakeTel(cand(status="rejected"))
        with self.assertRaises(p.Refused):
            run(tel, FakeIocs())


class SourceGuards(unittest.TestCase):
    """Read the code, because the behaviour above cannot see what the script never calls."""

    def setUp(self):
        self.src = (ROOT / "tools" / "promote_mcp_candidates.py").read_text(encoding="utf-8")
        self.tree = ast.parse(self.src)

    def test_the_corpus_is_written_in_exactly_one_place_and_nothing_else_is(self):
        puts = [n for n in ast.walk(self.tree) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.attr == "put_item"]
        self.assertEqual(len(puts), 1)
        for bad in ("first_seen", "FIRST_SEEN", "delete_item", "batch_writer"):
            self.assertNotIn(bad, re.sub(r'""".*?"""', "", self.src, flags=re.S).split("# --- CLI")[0], bad)

    def test_nothing_in_the_ingest_path_writes_the_corpus(self):
        # The endpoint must stay write-free toward relayshield_intel_iocs.
        m = re.search(r"def handle_mcp_proxy_telemetry.*?\nROUTES = ", API, re.S)
        self.assertIsNotNone(m)
        body = re.sub(r"#.*", "", m.group(0))
        self.assertNotIn("INTEL_IOCS_TABLE", body)
        self.assertNotIn("relayshield_intel_iocs", body)

    def test_categories_agree_with_the_proxy_and_the_endpoint(self):
        tel = (ROOT / "mcp_proxy" / "telemetry.py").read_text(encoding="utf-8")
        reportable = set(re.findall(r'"([a-z_]+)"', re.search(
            r"REPORTABLE_CATEGORIES = frozenset\(\{(.*?)\}\)", tel, re.S).group(1)))
        self.assertTrue(p.PROMOTABLE_CATEGORIES <= reportable)
        self.assertTrue(p.ECHO_CATEGORIES <= reportable)
        self.assertFalse(p.PROMOTABLE_CATEGORIES & p.ECHO_CATEGORIES)

    def test_taxonomy_id_is_empty_exactly_for_tool_results(self):
        # evaluate() treats "no taxonomy id" as "a tool result, host not shown to be the actor".
        # That holds only while proxy.py records results with an empty id list and discovery
        # findings with real ids. If this fails, the host-attribution rule is no longer sound.
        px = ast.parse((ROOT / "mcp_proxy" / "proxy.py").read_text(encoding="utf-8"))
        seen = {}
        for n in ast.walk(px):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "record"
                    and len(n.args) >= 3 and isinstance(n.args[1], ast.Constant)
                    and n.args[1].value in ("result", "discovery")):
                seen[n.args[1].value] = n.args[2]
        self.assertIn("result", seen)
        self.assertIn("discovery", seen)
        self.assertTrue(isinstance(seen["result"], ast.List) and not seen["result"].elts)
        self.assertFalse(isinstance(seen["discovery"], ast.List) and not seen["discovery"].elts)

    def test_the_privacy_promise_and_the_evidence_requirement_agree(self):
        policy = (ROOT / "cloudflare_worker_privacy.js").read_text(encoding="utf-8")
        self.assertIn("independently confirmed", policy)
        self.assertGreaterEqual(p.MIN_EVIDENCE_CHARS, 20)

    def test_the_corpus_reader_still_ignores_confidence(self):
        # If this starts failing, _assess_domain began honouring confidence/source and the
        # warning in the tool's docstring (a promoted row flags immediately) is out of date.
        m = re.search(r"def _assess_domain.*?\ndef _heuristic_url_check\(", API, re.S).group(0)
        code = re.sub(r"#.*", "", m)
        self.assertNotIn("confidence", code)
        self.assertNotIn('"source"', code)


if __name__ == "__main__":
    unittest.main()
