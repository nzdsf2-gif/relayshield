#!/usr/bin/env python3
"""An AWS-licensed key gets a first-party-only data path; every other key is untouched.

WHY THIS EXISTS (2026-10-25)
----------------------------
The AWS Foundational Technical Review needs the listed product deployed on AWS, which
AWS defines as every plane AND every third-party service that handles customer data
running on AWS. Three Bundle D endpoints sent the queried domain or email to outside
services. For AWS-licensed keys only, those calls are now skipped. These tests exist
because the change is a quiet one in three ways:

  1. It must be a REAL absence. urlopen is replaced with a function that fails the test
     if called, so "we skip the lookup" is executed, not read.
  2. A missing signal must not read as a clean one. Dropping two dimensions and summing
     the rest caps a domain at 75/100 and an agent at 40/100, so a CRITICAL identity
     could never be reported as CRITICAL and the "critical agent elevates the org" rule
     could never fire. The remainder is rescaled, and every response names what did not
     run.
  3. It must not leak onto other customers. The marker is derived from the key record
     in the dispatcher; any value a caller sends under that name is removed first, so a
     direct Stripe customer can neither lose their enrichment nor fake the marker.

    python3 test_aws_first_party_path.py

No network, no AWS. The tables are fakes whose contents each test sets.
"""
import json
import pathlib
import sys
import types
import unittest
import unittest.mock
import urllib.error
from decimal import Decimal

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
import relayshield_agentic_api as agentic  # noqa: E402


class _Table:
    def __init__(self, items):
        self.items = items

    def scan(self, **kw):
        return {"Items": list(self.items)}

    def query(self, **kw):
        return {"Items": list(self.items)}


class _Dynamo:
    """Tables by name; any table not named is empty."""
    def __init__(self, tables=None):
        self.tables = tables or {}

    def Table(self, name):
        return _Table(self.tables.get(name, []))


def _data(resp):
    return json.loads(resp["body"])["data"]


def _no_outbound(*a, **k):
    raise AssertionError("an outbound HTTP call was made on the first-party path")


class _Outbound:
    """Records every urlopen and then fails it, so the code under test takes its own error path."""
    def __init__(self):
        self.urls = []

    def __call__(self, req, *a, **k):
        self.urls.append(getattr(req, "full_url", str(req)))
        raise urllib.error.URLError("recorded")


CRED = {"session_type": "credential", "category": "api_key"}


class DomainScore(unittest.TestCase):
    def setUp(self):
        self._saved = (api.dynamodb, api._hibp_api_key, api._query_ransomware_victims)
        api._hibp_api_key = lambda: "k"
        api._query_ransomware_victims = lambda d: []
        api.dynamodb = _Dynamo()

    def tearDown(self):
        api.dynamodb, api._hibp_api_key, api._query_ransomware_victims = self._saved

    def test_first_party_makes_no_outbound_call(self):
        with unittest.mock.patch.object(api.urllib.request, "urlopen", _no_outbound):
            out = api._domain_risk_fast("example.com", first_party_only=True)
        self.assertEqual(out["signals_not_run"], ["external_breach_history", "external_infostealer_lookup"])

    def test_first_party_omits_the_two_dimensions_instead_of_zeroing_them(self):
        with unittest.mock.patch.object(api.urllib.request, "urlopen", _no_outbound):
            out = api._domain_risk_fast("example.com", first_party_only=True)
        self.assertNotIn("breach_exposure", out["dimension_scores"])
        self.assertNotIn("infostealer_density", out["dimension_scores"])
        self.assertEqual(set(out["dimension_scores"]), {"ioc_presence", "ransomware_victim", "session_exposure", "cve_exposure"})

    def test_the_direct_path_still_calls_both_services(self):
        rec = _Outbound()
        with unittest.mock.patch.object(api.urllib.request, "urlopen", rec):
            out = api._domain_risk_fast("example.com")
        self.assertEqual(len(rec.urls), 2, rec.urls)
        self.assertNotIn("signals_not_run", out)
        self.assertIn("breach_exposure", out["dimension_scores"])

    def test_rescaling_lets_a_ransomware_victim_reach_the_level_its_points_deserve(self):
        # Raw 20 of a possible 75 on the first-party path = 26.7 of 100 -> 27 -> MEDIUM.
        # Un-rescaled it would read 20 -> LOW.
        api._query_ransomware_victims = lambda d: [{"group": "x"}]
        with unittest.mock.patch.object(api.urllib.request, "urlopen", _no_outbound):
            fp = api._domain_risk_fast("example.com", first_party_only=True)
        self.assertEqual(fp["risk_score"], 27)
        self.assertEqual(fp["risk_level"], "MEDIUM")
        with unittest.mock.patch.object(api.urllib.request, "urlopen", _Outbound()):
            direct = api._domain_risk_fast("example.com")
        self.assertEqual(direct["risk_score"], 20)
        self.assertEqual(direct["risk_level"], "LOW")

    def test_the_best_first_party_domain_can_still_reach_100(self):
        api._query_ransomware_victims = lambda d: [{"group": "x"}]
        api.dynamodb = _Dynamo({
            "relayshield_stolen_sessions": [{"x": 1}] * 10,
            api.INTEL_IOCS_TABLE: [{"x": 1}] * 20,
            api.INTEL_CVE_TABLE: [{"known_ransomware_campaign_use": "Known"}] * 60,
        })
        with unittest.mock.patch.object(api.urllib.request, "urlopen", _no_outbound):
            out = api._domain_risk_fast("example.com", first_party_only=True)
        self.assertEqual(out["risk_score"], 100)
        self.assertEqual(out["risk_level"], "CRITICAL")


class AgentScore(unittest.TestCase):
    def setUp(self):
        self._saved = (api.dynamodb, api._hibp_api_key)
        api._hibp_api_key = lambda: "k"

    def tearDown(self):
        api.dynamodb, api._hibp_api_key = self._saved

    def _with_credentials(self, n):
        api.dynamodb = _Dynamo({"relayshield_stolen_sessions": [dict(CRED) for _ in range(n)]})

    def test_first_party_makes_no_outbound_call_and_names_what_it_skipped(self):
        self._with_credentials(0)
        with unittest.mock.patch.object(api.urllib.request, "urlopen", _no_outbound):
            out = api._agent_risk("a@example.com", first_party_only=True)
        self.assertEqual(out["risk_score"], 0)
        self.assertEqual(out["signals_not_run"], ["external_breach_history", "external_infostealer_lookup"])

    def test_two_stolen_credentials_are_CRITICAL_not_capped_at_MEDIUM(self):
        # Raw = 40, the most the remaining signal can give. Un-rescaled that is MEDIUM
        # and CRITICAL is unreachable, which would disable the org-elevation rule.
        self._with_credentials(2)
        with unittest.mock.patch.object(api.urllib.request, "urlopen", _no_outbound):
            out = api._agent_risk("a@example.com", first_party_only=True)
        self.assertEqual((out["risk_score"], out["risk_level"]), (100, "CRITICAL"))

    def test_one_stolen_credential_is_HIGH(self):
        self._with_credentials(1)
        with unittest.mock.patch.object(api.urllib.request, "urlopen", _no_outbound):
            out = api._agent_risk("a@example.com", first_party_only=True)
        self.assertEqual((out["risk_score"], out["risk_level"]), (62, "HIGH"))

    def test_the_direct_path_is_unchanged(self):
        self._with_credentials(1)
        rec = _Outbound()
        with unittest.mock.patch.object(api.urllib.request, "urlopen", rec):
            out = api._agent_risk("a@example.com")
        self.assertEqual(len(rec.urls), 2, rec.urls)
        self.assertEqual((out["risk_score"], out["risk_level"]), (25, "MEDIUM"))
        self.assertNotIn("signals_not_run", out)


class BulkIdentityRisk(unittest.TestCase):
    def setUp(self):
        self._saved = (api.dynamodb, api._hibp_api_key, api._query_ransomware_victims)
        api._hibp_api_key = lambda: "k"
        api._query_ransomware_victims = lambda d: []
        api.dynamodb = _Dynamo({"relayshield_stolen_sessions": [dict(CRED), dict(CRED)]})

    def tearDown(self):
        api.dynamodb, api._hibp_api_key, api._query_ransomware_victims = self._saved

    def _call(self, **extra):
        return api.handle_bulk_identity_risk(
            {"targets": [{"domain": "example.com", "agents": ["a@example.com"]}], **extra})

    def test_aws_path_end_to_end_makes_no_outbound_call_and_says_so(self):
        with unittest.mock.patch.object(api.urllib.request, "urlopen", _no_outbound):
            d = _data(self._call(_aws_data_path=True))
        self.assertEqual(d["data_path"], "first_party")
        self.assertEqual(d["signals_not_run"], ["external_breach_history", "external_infostealer_lookup"])
        self.assertIn("not proof of safety", d["note"])

    def test_a_critical_agent_still_elevates_the_org_on_the_aws_path(self):
        with unittest.mock.patch.object(api.urllib.request, "urlopen", _no_outbound):
            d = _data(self._call(_aws_data_path=True))
        r = d["results"][0]
        self.assertEqual(r["agents"][0]["risk_level"], "CRITICAL")
        self.assertIn(r["domain_risk"], ("HIGH", "CRITICAL"))
        self.assertGreaterEqual(d["high_count"] + d["critical_count"], 1)

    def test_the_direct_response_keeps_exactly_the_old_shape(self):
        with unittest.mock.patch.object(api.urllib.request, "urlopen", _Outbound()):
            d = _data(self._call())
        self.assertNotIn("data_path", d)
        self.assertNotIn("signals_not_run", d)
        self.assertNotIn("note", d)


class TechStackCve(unittest.TestCase):
    def setUp(self):
        self._saved = (api.dynamodb, api._check_github_poc_exists)
        api.dynamodb = _Dynamo({api.INTEL_CVE_TABLE: [{
            "cve_id": "CVE-2026-1", "description": "flaw in langchain", "epss_score": Decimal("0.5"),
            "in_kev": False, "ransomware_campaign": False,
        }]})

    def tearDown(self):
        api.dynamodb, api._check_github_poc_exists = self._saved

    def test_aws_path_never_looks_up_exploit_availability(self):
        api._check_github_poc_exists = lambda cve: self.fail("public-exploit lookup ran on the first-party path")
        d = _data(api.handle_tech_stack_cve({"tech_stack": ["langchain"], "_aws_data_path": True}))
        self.assertEqual(d["signals_not_run"], ["public_exploit_lookup"])
        self.assertEqual(d["total_matches"], 1)
        # ABSENT, not False: "no exploit found" is a claim the lookup did not make.
        self.assertNotIn("poc_available", d["all_matches"][0])

    def test_direct_path_still_looks_it_up(self):
        api._check_github_poc_exists = lambda cve: True
        d = _data(api.handle_tech_stack_cve({"tech_stack": ["langchain"]}))
        self.assertIs(d["all_matches"][0]["poc_available"], True)
        self.assertNotIn("signals_not_run", d)


class McpRegistryRisk(unittest.TestCase):
    def setUp(self):
        self._saved = (agentic.dynamodb, agentic._rdap_registration_age_days)
        agentic.dynamodb = _Dynamo()

    def tearDown(self):
        agentic.dynamodb, agentic._rdap_registration_age_days = self._saved

    def test_aws_path_never_asks_the_registry_and_says_so(self):
        agentic._rdap_registration_age_days = lambda d: self.fail("registration lookup ran on the first-party path")
        d = _data(agentic.handle_mcp_registry_risk({"server_url": "https://brand-new.example/mcp", "_aws_data_path": True}))
        self.assertEqual(d["signals_not_run"], ["domain_registration_age"])
        self.assertNotIn("newly_registered_domain", [f["type"] for f in d["findings"]])

    def test_direct_path_still_flags_a_young_domain(self):
        agentic._rdap_registration_age_days = lambda d: 3
        d = _data(agentic.handle_mcp_registry_risk({"server_url": "https://brand-new.example/mcp"}))
        self.assertIn("newly_registered_domain", [f["type"] for f in d["findings"]])
        self.assertNotIn("signals_not_run", d)


class DispatcherMarker(unittest.TestCase):
    """The marker comes from the KEY RECORD. Run the real dispatchers, not a reading of them."""

    AWS_KEY = {"api_key": "rs_live_aws", "bundle_d_access": True, "aws_customer_id": "cust-1",
               "aws_account_id": "111122223333", "aws_license_arn": "arn:aws:license-manager::lic"}
    DIRECT_KEY = {"api_key": "rs_live_direct", "bundle_d_access": True, "stripe_customer_id": "cus_1",
                  "stripe_subscription_id": "sub_1"}

    def _event(self, key, body):
        return {"headers": {"X-RS-API-KEY": key}, "body": json.dumps(body)}

    def _run_main(self, record, body):
        seen = {}

        def spy(params):
            seen.update(params)
            return api._ok({})
        with unittest.mock.patch.object(api, "_verify_rs_api_key", lambda k: record), \
                unittest.mock.patch.object(api, "handle_bulk_identity_risk", spy), \
                unittest.mock.patch.object(api, "_report_marketplace_usage", lambda *a, **k: None), \
                unittest.mock.patch.object(api, "_record_stripe_meter_event", lambda *a, **k: None):
            resp = api.handle_metered_request("/v1/metered/bulk-identity-risk", "POST",
                                              self._event(record["api_key"], body))
        return resp, seen

    def test_an_aws_key_gets_the_marker(self):
        resp, seen = self._run_main(self.AWS_KEY, {"targets": [{"domain": "a.com"}]})
        self.assertEqual(resp["statusCode"], 200, resp)
        self.assertIs(seen.get("_aws_data_path"), True)

    def test_a_direct_key_does_not(self):
        resp, seen = self._run_main(self.DIRECT_KEY, {"targets": [{"domain": "a.com"}]})
        self.assertEqual(resp["statusCode"], 200, resp)
        self.assertNotIn("_aws_data_path", seen)

    def test_a_direct_caller_cannot_forge_the_marker(self):
        resp, seen = self._run_main(self.DIRECT_KEY, {"targets": [{"domain": "a.com"}], "_aws_data_path": True})
        self.assertNotIn("_aws_data_path", seen)

    def test_an_aws_caller_cannot_switch_it_off(self):
        resp, seen = self._run_main(self.AWS_KEY, {"targets": [{"domain": "a.com"}], "_aws_data_path": False})
        self.assertIs(seen.get("_aws_data_path"), True)

    def test_the_agentic_dispatcher_does_the_same(self):
        for record, forged, expected in ((self.AWS_KEY, False, True), (self.DIRECT_KEY, True, None)):
            seen = {}

            def spy(params):
                seen.update(params)
                return agentic._ok({})
            event = {"httpMethod": "POST", "path": "/v1/metered/mcp-registry-risk",
                     "headers": {"X-RS-API-KEY": record["api_key"]},
                     "body": json.dumps({"server_url": "https://x.example", "_aws_data_path": forged})}
            with unittest.mock.patch.dict(agentic.ROUTES, {"/v1/metered/mcp-registry-risk": spy}), \
                    unittest.mock.patch.object(agentic, "_verify_rs_api_key", lambda k, r=record: r), \
                    unittest.mock.patch.object(agentic, "_report_marketplace_usage", lambda *a, **k: None), \
                    unittest.mock.patch.object(agentic, "_record_stripe_meter_event", lambda *a, **k: None):
                try:
                    agentic.lambda_handler(event, None)
                except Exception:
                    pass  # metering after the handler is not what this test is about
            # The handler must actually have run, or a missing marker proves nothing.
            self.assertIn("server_url", seen, (record["api_key"], "handler never ran"))
            self.assertEqual(seen.get("_aws_data_path"), expected, (record["api_key"], seen))


if __name__ == "__main__":
    unittest.main()
