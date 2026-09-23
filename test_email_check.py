"""/v1/email-check -- a second door onto checkemail@relayshield.net's scoring
model, for a caller (an agent reading a mailbox) that hands over structured
JSON rather than raw RFC822.

Every test here EXECUTES the real handler with boto3 and urllib stubbed,
following test_muse_connector_features.py's pattern: a suite that only reads
the source cannot see a runtime-only defect, and this repo has shipped three
of those in one file already (INLINE_TEXT, the temporal-dead-zone build id,
the UnboundLocalError dispatcher bug).

TWO CLASSES OF GUARD:
  - Behavioural: does the handler score what it should.
  - Agreement: relayshield_api.py's copy of BRAND_DOMAINS etc. is a PORT of
    cloudflare_worker_checkemail.js's copy, not a shared import (different
    runtimes). Two copies of one scoring model that can silently drift is
    this repo's most-repeated defect, so TableAgreement reads both files and
    fails the day they diverge.
"""
import ast
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


def body(resp):
    return json.loads(resp["body"])


def _no_link_findings(urls):
    return {u: {"flagged": False, "reasons": [],
                "signals": {"ioc_corpus": False, "safe_browsing": False,
                            "domain_age_days": None}} for u in urls}


class HandlerBehaviour(unittest.TestCase):
    """Executed directly against handle_email_check, no dispatcher."""

    def _call(self, params, links_result=None):
        with unittest.mock.patch.object(
                api, "_heuristic_url_check_many",
                lambda urls: links_result if links_result is not None
                else _no_link_findings(urls)):
            return body(api.handle_email_check(params))

    def test_empty_request_is_refused(self):
        resp = api.handle_email_check({})
        self.assertEqual(resp["statusCode"], 400)

    def test_dmarc_fail_is_the_strongest_single_flag(self):
        d = self._call({"from_address": "a@example.com",
                        "auth_results": {"dmarc": "fail"}})
        texts = " ".join(f["text"] for f in d["data"]["flags"])
        self.assertIn("DMARC FAILED", texts)
        self.assertGreaterEqual(d["data"]["score"], 3)
        self.assertEqual(d["data"]["risk"], "high")

    def test_clean_message_is_low_risk_with_no_flags(self):
        d = self._call({"from_address": "andrew@gmail.com", "from_name": "Andrew Gibbs"})
        self.assertEqual(d["data"]["flags"], [])
        self.assertEqual(d["data"]["risk"], "low")

    def test_a_real_gmail_user_does_not_flag_on_name_vs_address(self):
        """The exact regression this repo already paid for in the Worker: a
        display name having nothing to do with the local part is not a
        finding on its own."""
        d = self._call({"from_address": "nzdsf2@gmail.com", "from_name": "Andrew Gibbs"})
        self.assertEqual(d["data"]["flags"], [])

    def test_brand_impersonation_on_a_real_company_domain(self):
        """The MetaMask/phrase.com case that widened the Worker's rule past
        free-webmail-only impersonation."""
        d = self._call({"from_address": "system@phrase.com",
                        "from_name": "ApplyAML Meta Mask Details"})
        texts = " ".join(f["text"] for f in d["data"]["flags"])
        self.assertIn("Metamask", texts)
        self.assertIn("phrase.com", texts)

    def test_unrelated_small_business_is_not_flagged(self):
        """'Apple Tree Nursery' <hello@appletreenursery.com> contains 'apple'
        and is a garden centre, not an impersonator."""
        d = self._call({"from_address": "hello@appletreenursery.com",
                        "from_name": "Apple Tree Nursery"})
        self.assertEqual(d["data"]["flags"], [])

    def test_brand_sent_from_its_own_domain_is_not_flagged(self):
        d = self._call({"from_address": "no-reply@paypal.com", "from_name": "PayPal"})
        self.assertEqual(d["data"]["flags"], [])

    def test_authority_word_on_free_webmail_is_flagged(self):
        d = self._call({"from_address": "x@gmail.com", "from_name": "Account Security Team"})
        texts = " ".join(f["text"] for f in d["data"]["flags"])
        self.assertIn("support desk", texts.lower() + " ".join(
            f["text"].lower() for f in d["data"]["flags"]))

    def test_ask_alone_is_not_a_flag(self):
        """Either ask or pressure alone is ordinary; only together do they
        score. This is the whole mechanism the Worker's pressureSignals
        exists to encode."""
        d = self._call({"from_address": "billing@acme.com",
                        "body_text": "Please verify your account when convenient."})
        self.assertEqual(d["data"]["flags"], [])

    def test_ask_plus_deadline_is_flagged(self):
        d = self._call({"from_address": "billing@acme.com",
                        "body_text": "Verify your account within 24 hours or lose access."})
        texts = " ".join(f["text"] for f in d["data"]["flags"])
        self.assertTrue(any("asks you to" in f["text"] for f in d["data"]["flags"]), texts)

    def test_reply_to_mismatch_is_flagged_on_a_direct_message(self):
        d = self._call({"from_address": "ceo@acme.com", "reply_to": "attacker@other.com"})
        texts = " ".join(f["text"] for f in d["data"]["flags"])
        self.assertIn("Reply-To mismatch", texts)

    def test_reply_to_mismatch_is_NOT_flagged_when_forwarded(self):
        """A forward's Reply-To belongs to the forwarder, not the original."""
        d = self._call({"from_address": "ceo@acme.com", "reply_to": "attacker@other.com",
                        "forwarded": True})
        texts = " ".join(f["text"] for f in d["data"]["flags"])
        self.assertNotIn("Reply-To mismatch", texts)

    def test_forwarded_auth_is_not_scored(self):
        """The most important honesty fix the Worker carries: on a forward,
        Authentication-Results belongs to the forwarder and must not be
        presented as a verdict on the original."""
        d = self._call({"from_address": "a@example.com", "forwarded": True,
                        "auth_results": {"dmarc": "fail"}})
        self.assertEqual(d["data"]["flags"], [])
        self.assertFalse(d["data"]["auth"]["about_original"])

    def test_public_file_host_link_is_flagged(self):
        d = self._call(
            {"from_address": "a@acme.com",
             "links": ["https://storage.googleapis.com/x/y.html"]},
            links_result=_no_link_findings(["https://storage.googleapis.com/x/y.html"]))
        texts = " ".join(f["text"] for f in d["data"]["flags"])
        self.assertIn("storage.googleapis.com", texts)

    def test_executable_attachment_is_flagged(self):
        d = self._call({"from_address": "a@acme.com", "attachment_names": ["invoice.exe"]})
        texts = " ".join(f["text"] for f in d["data"]["flags"])
        self.assertIn(".exe", texts)

    def test_double_extension_attachment_outranks_plain_executable(self):
        d = self._call({"from_address": "a@acme.com",
                        "attachment_names": ["invoice.pdf.exe"]})
        texts = " ".join(f["text"] for f in d["data"]["flags"])
        self.assertIn("two extensions", texts)

    def test_archive_attachment_is_a_note_not_a_flag(self):
        d = self._call({"from_address": "a@acme.com", "attachment_names": ["docs.zip"]})
        self.assertEqual(d["data"]["flags"], [])
        self.assertTrue(any("archive" in n for n in d["data"]["notes"]))

    def test_a_HIGH_link_pushes_risk_up_even_with_no_header_flags(self):
        url = "https://evil.example/login"
        d = self._call(
            {"from_address": "a@acme.com", "links": [url]},
            links_result={url: {"flagged": True, "reasons": ["in the IOC corpus"],
                                 "signals": {"ioc_corpus": True, "safe_browsing": False,
                                             "domain_age_days": None}}})
        self.assertEqual(d["data"]["risk"], "high")
        self.assertEqual(d["data"]["links"][0]["level"], "high")

    def test_authentication_results_header_is_parsed_as_a_fallback(self):
        d = self._call({"from_address": "a@example.com",
                        "authentication_results": "spf=fail dkim=pass dmarc=fail (reason)"})
        texts = " ".join(f["text"] for f in d["data"]["flags"])
        self.assertIn("DMARC FAILED", texts)
        self.assertIn("SPF FAILED", texts)

    def test_structured_auth_results_win_over_the_raw_header(self):
        d = self._call({"from_address": "a@example.com",
                        "authentication_results": "spf=fail dkim=fail dmarc=fail",
                        "auth_results": {"spf": "pass", "dkim": "pass", "dmarc": "pass"}})
        self.assertEqual(d["data"]["flags"], [])

    def test_links_are_capped_at_the_shared_ceiling(self):
        urls = [f"https://a{i}.example.com/" for i in range(30)]
        with unittest.mock.patch.object(
                api, "_heuristic_url_check_many",
                lambda passed: _no_link_findings(passed)) as mocked:
            d = self._call({"from_address": "a@acme.com", "links": urls})
        self.assertLessEqual(len(d["data"]["links"]), api.LINK_CHECK_MAX_URLS)


class Dispatcher(unittest.TestCase):
    """Through lambda_handler, not the bare handler -- this is where the
    UnboundLocalError defect and the missing-onward defect both lived, and a
    suite that only calls the handler cannot see either class."""

    def _call(self, payload, source_ip="1.2.3.4"):
        ev = {"path": "/v1/email-check", "httpMethod": "POST",
              "body": json.dumps(payload), "headers": {},
              "requestContext": {"identity": {"sourceIp": source_ip}}}
        with unittest.mock.patch.object(api, "_check_keyless_ip_quota", lambda *a, **k: True), \
             unittest.mock.patch.object(api, "_heuristic_url_check_many",
                                        lambda urls: _no_link_findings(urls)):
            return api.lambda_handler(ev, None)

    def test_is_registered_and_reachable(self):
        resp = self._call({"from_address": "a@example.com", "from_name": "PayPal Support"})
        self.assertEqual(resp["statusCode"], 200)

    def test_is_in_the_keyless_quota_set(self):
        self.assertIn("/v1/email-check", api.KEYLESS_SCAN_ENDPOINTS)

    def test_costs_exactly_one_quota_unit_however_many_links(self):
        """Unlike /v1/link-check's batch form, one email-check call is one
        logical check. _link_check_units must not scale it by link count,
        or a mailbox sweep of one message with ten links would cost ten."""
        self.assertEqual(
            api._link_check_units("/v1/email-check",
                                  {"links": [f"https://a{i}.com/" for i in range(10)]}),
            1)

    def test_a_registered_source_gets_an_onward_route(self):
        d = body(self._call({"from_address": "a@example.com", "source": "muse"}))["data"]
        self.assertIn("onward", d)

    def test_a_FAILED_request_carries_no_onward_advert(self):
        resp = self._call({"source": "muse"})  # empty -> 400
        self.assertNotEqual(resp["statusCode"], 200)
        self.assertNotIn("onward", resp["body"])


class TableAgreement(unittest.TestCase):
    """relayshield_api.py's copies of the Worker's scoring tables are a PORT,
    not an import -- different runtimes. Two copies of one scoring model
    that can silently drift is this repo's most-repeated defect, and here it
    would mean the API and checkemail@ tell two users different things
    about the same email."""

    @classmethod
    def setUpClass(cls):
        raw = (ROOT / "cloudflare_worker_checkemail.js").read_text()
        # STRIPPED FIRST, NOT AFTER A FALSE POSITIVE. This repo's own history
        # (CLAUDE.md: "stripping comments before grepping") is that a guard
        # written by searching the file matches prose describing the rule as
        # often as the rule itself -- proved immediately here: the comment
        # above ASK_PHRASES quotes "please add your email now" and "verify or
        # lose access" as EXAMPLES, and an unstripped regex counts both as
        # table entries that do not exist.
        cls.worker_src = re.sub(r"//[^\n]*", "", raw)

    def _worker_brand_keys(self):
        m = re.search(r"const BRAND_DOMAINS = \{(.*?)\n\};", self.worker_src, re.S)
        self.assertIsNotNone(m, "BRAND_DOMAINS not found in the Worker source")
        return set(re.findall(r'^\s*"([^"]+)":\s*\[', m.group(1), re.M))

    def test_brand_keys_match(self):
        self.assertEqual(self._worker_brand_keys(),
                         set(api._EMAIL_BRAND_DOMAINS.keys()),
                         "the API's brand table has drifted from the Worker's")

    def test_ask_phrases_match(self):
        m = re.search(r"const ASK_PHRASES = \[(.*?)\];", self.worker_src, re.S)
        worker_phrases = set(re.findall(r'"([^"]+)"', m.group(1)))
        self.assertEqual(worker_phrases, set(api._EMAIL_ASK_PHRASES))

    def test_deadline_phrases_match(self):
        m = re.search(r"const DEADLINE_PHRASES = \[(.*?)\];", self.worker_src, re.S)
        worker_phrases = set(re.findall(r'"([^"]+)"', m.group(1)))
        self.assertEqual(worker_phrases, set(api._EMAIL_DEADLINE_PHRASES))

    def test_threat_phrases_match(self):
        m = re.search(r"const THREAT_PHRASES = \[(.*?)\];", self.worker_src, re.S)
        worker_phrases = set(re.findall(r'"([^"]+)"', m.group(1)))
        self.assertEqual(worker_phrases, set(api._EMAIL_THREAT_PHRASES))

    def test_webmail_set_matches(self):
        m = re.search(r"const WEBMAIL = new Set\(\[(.*?)\]\);", self.worker_src, re.S)
        worker_set = set(re.findall(r'"([^"]+)"', m.group(1)))
        self.assertEqual(worker_set, set(api._EMAIL_WEBMAIL))

    def test_public_page_hosts_match(self):
        m = re.search(r"const PUBLIC_PAGE_HOSTS = \[(.*?)\];", self.worker_src, re.S)
        worker_list = re.findall(r'"([^"]+)"', m.group(1))
        self.assertEqual(worker_list, list(api._EMAIL_PUBLIC_PAGE_HOSTS))


class TheSpec(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import relayshield_openapi_spec
        cls.spec = relayshield_openapi_spec.build_spec()

    def test_it_is_in_the_spec(self):
        self.assertIn("/v1/email-check", self.spec["paths"])

    def test_it_requires_no_credential(self):
        op = self.spec["paths"]["/v1/email-check"]["post"]
        self.assertEqual(op.get("security"), [])


class ScoringIsPure(unittest.TestCase):
    """_score_email must not be called in more than one place with different
    weighting, or the Worker/API pair drifts a third way: the model itself
    diverging from its own two callers inside one file."""

    def test_handle_email_check_calls_score_email_exactly_once(self):
        tree = ast.parse((ROOT / "relayshield_api.py").read_text())
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == "handle_email_check")
        calls = [n for n in ast.walk(fn)
                 if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "_score_email"]
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
