"""/v1/metered/incident-timeline -- Item 4's on-demand, chargeable version of
the WhatsApp monitor's ATTACK_CHAINS correlation. See CLAUDE.md "ITEM 4 IS
NOT A GAP" and the endpoint's own docstring in relayshield_api.py.

Every behavioural test EXECUTES the real handler, with the four sub-checks
(handle_breach, handle_session_risk, handle_sim_swap, handle_domain)
monkeypatched to fixed responses rather than making network calls -- this is
a composition test, not a re-test of those four handlers, which already have
their own suites. Following test_muse_connector_features.py's and
test_email_check.py's pattern: a suite that only reads the source cannot see
a dispatcher-registration gap or a chain-matching defect, both of which this
repo has shipped before while every source-only check stayed green.
"""
import json
import re
import sys
import types
import unittest
import unittest.mock
import pathlib

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
import relayshield_breach_monitor as monitor  # noqa: E402


def _body(resp):
    return json.loads(resp["body"])


def _ok_breach(count):
    def _f(params, api_key_record=None):
        return api._ok({"email": params["email"], "record_type": "credential_exposure",
                         "breach_count": count, "breaches": [], "cached": False})
    return _f


def _ok_session(found, severity=None):
    def _f(params):
        return api._ok({"email": params["email"], "found": found, "session_count": 1 if found else 0,
                         "highest_severity": severity, "sessions": []})
    return _f


def _ok_swap(swapped):
    def _f(params):
        return api._ok({"phone": params["phone"], "swapped": swapped,
                         "swap_timestamp": "", "carrier": "T-Mobile"})
    return _f


def _ok_domain(count):
    def _f(params):
        return api._ok({"domain": params["domain"], "lookalikes_found": count, "lookalikes": []})
    return _f


class Composition(unittest.TestCase):
    def setUp(self):
        self._orig = (api.handle_breach, api.handle_session_risk, api.handle_sim_swap, api.handle_domain)
        api.handle_breach       = _ok_breach(0)
        api.handle_session_risk = _ok_session(False)
        api.handle_sim_swap     = _ok_swap(False)
        api.handle_domain       = _ok_domain(0)

    def tearDown(self):
        (api.handle_breach, api.handle_session_risk,
         api.handle_sim_swap, api.handle_domain) = self._orig

    def test_email_is_required(self):
        resp = api.handle_incident_timeline({})
        self.assertEqual(resp["statusCode"], 400)
        self.assertFalse(_body(resp)["ok"])

    def test_email_only_runs_breach_and_session_risk_and_skips_the_rest(self):
        api.handle_breach = _ok_breach(1)
        data = _body(api.handle_incident_timeline({"email": "u@example.com"}))["data"]
        self.assertIn("breach", data["checks"])
        self.assertIn("session_risk", data["checks"])
        self.assertNotIn("sim_swap", data["checks"])
        self.assertNotIn("domain", data["checks"])
        self.assertIn("sim_swap (no phone supplied)", data["checks_skipped"])
        self.assertIn("domain (none supplied)", data["checks_skipped"])

    def test_breach_plus_sim_swap_matches_breach_sim_swap_chain(self):
        api.handle_breach   = _ok_breach(2)
        api.handle_sim_swap = _ok_swap(True)
        data = _body(api.handle_incident_timeline(
            {"email": "u@example.com", "phone": "+14155551234"}))["data"]
        self.assertEqual(data["chain_matched"]["chain"], "breach_sim_swap")
        self.assertEqual(data["chain_matched"]["severity"], "CRITICAL")
        self.assertIn("breach_alert", data["signals_detected"])
        self.assertIn("sim_swap", data["signals_detected"])

    def test_breach_plus_domain_lookalike_matches_domain_phishing_breach_chain(self):
        api.handle_breach = _ok_breach(1)
        api.handle_domain  = _ok_domain(1)
        data = _body(api.handle_incident_timeline(
            {"email": "u@example.com", "domain": "acme.com"}))["data"]
        self.assertEqual(data["chain_matched"]["chain"], "domain_phishing_breach")

    def test_breach_alone_matches_no_chain(self):
        api.handle_breach = _ok_breach(3)
        data = _body(api.handle_incident_timeline({"email": "u@example.com"}))["data"]
        self.assertIsNone(data["chain_matched"])
        self.assertEqual(data["signals_detected"], ["breach_alert"])

    def test_session_risk_never_joins_signal_types_or_decides_the_chain(self):
        """session_risk is context, not an ATTACK_CHAINS signal. A found
        session must never, by itself or alongside a lone breach, produce a
        chain match -- if it did, this endpoint would be inventing a
        SESSION_RISK-shaped signal ATTACK_CHAINS itself has no definition
        for, a silent second definition of what 'session_risk' means."""
        api.handle_breach       = _ok_breach(1)
        api.handle_session_risk = _ok_session(True, "CRITICAL")
        data = _body(api.handle_incident_timeline({"email": "u@example.com"}))["data"]
        self.assertNotIn("session_risk", data["signals_detected"])
        self.assertIsNone(data["chain_matched"])
        self.assertTrue(data["checks"]["session_risk"]["flagged"])  # still reported, just not a signal

    def test_a_failed_sub_check_is_checked_false_never_treated_as_clean(self):
        """A sub-check that could not be completed (4xx/5xx from HIBP, no
        carrier answer, ...) must read as 'we could not check', never as
        'nothing found' -- the SIM-swap monitor's own rule, applied here."""
        def _err_breach(params, api_key_record=None):
            return api._err("HIBP returned HTTP 502", 502)
        api.handle_breach = _err_breach
        data = _body(api.handle_incident_timeline({"email": "u@example.com"}))["data"]
        self.assertFalse(data["checks"]["breach"]["checked"])
        self.assertFalse(data["checks"]["breach"]["flagged"])
        self.assertIsNone(data["checks"]["breach"]["breach_count"])
        self.assertNotIn("breach_alert", data["signals_detected"])

    def test_domain_scheme_and_www_are_stripped(self):
        api.handle_breach = _ok_breach(1)
        captured = {}
        def _capturing_domain(params):
            captured["domain"] = params["domain"]
            return api._ok({"domain": params["domain"], "lookalikes_found": 0, "lookalikes": []})
        api.handle_domain = _capturing_domain
        api.handle_incident_timeline({"email": "u@example.com", "domain": "https://www.acme.com"})
        self.assertEqual(captured["domain"], "acme.com")

    def test_chain_priority_is_atack_chains_order_first_match_wins(self):
        """Both breach_sim_swap and (if it were possible here) an earlier
        chain in the table must resolve to the FIRST matching entry, exactly
        as check_and_fire_correlation does, so the two paths can never
        disagree about which chain fires on an overlapping signal set."""
        first_signals = monitor.ATTACK_CHAINS[0]["signals"]
        # Sanity: the table's own first entry is smishing_to_sim_swap, which
        # this endpoint can never satisfy (no suspicious_sms signal exists
        # here) -- so on a signal set only this endpoint can produce, the
        # first REACHABLE match is breach_sim_swap, and it must win over
        # domain_phishing_breach even if a caller supplied both phone and
        # domain and both matched.
        api.handle_breach   = _ok_breach(1)
        api.handle_sim_swap = _ok_swap(True)
        api.handle_domain   = _ok_domain(1)
        data = _body(api.handle_incident_timeline(
            {"email": "u@example.com", "phone": "+14155551234", "domain": "acme.com"}))["data"]
        self.assertEqual(data["chain_matched"]["chain"], "breach_sim_swap")
        idx_bss = next(i for i, c in enumerate(monitor.ATTACK_CHAINS) if c["chain"] == "breach_sim_swap")
        idx_dpb = next(i for i, c in enumerate(monitor.ATTACK_CHAINS) if c["chain"] == "domain_phishing_breach")
        self.assertLess(idx_bss, idx_dpb)


class ChainTableIsImportedNeverCopied(unittest.TestCase):
    def test_atack_chains_is_the_same_object_not_a_second_copy(self):
        """Identity, not equality: if relayshield_api ever gained its own
        ATTACK_CHAINS literal instead of importing the real one, this table
        would still be equal today and silently diverge the next time the
        monitor's chain list changes -- the exact shape CLAUDE.md names as
        this repo's most-repeated defect."""
        self.assertIs(api.ATTACK_CHAINS, monitor.ATTACK_CHAINS)


class Dispatcher(unittest.TestCase):
    def setUp(self):
        self.src = (ROOT / "relayshield_api.py").read_text()
        # Strip comments before any substring search on this file, per this
        # repo's own repeated lesson: a guard fooled by a comment describing
        # the thing it checks for is not a guard.
        self.code = re.sub(r"#[^\n]*", "", self.src)

    def test_registered_in_metered_credit_costs(self):
        self.assertEqual(api.METERED_CREDIT_COSTS.get("/v1/metered/incident-timeline"), 50)

    def test_registered_in_the_dispatch_table(self):
        m = re.search(
            r'metered_routes\s*=\s*\{([\s\S]*?)\n    \}', self.code)
        self.assertIsNotNone(m, "could not find the metered_routes dict in handle_metered_request")
        self.assertIn('"/v1/metered/incident-timeline"', m.group(1))
        self.assertIn("handle_incident_timeline", m.group(1))

    def test_price_matches_the_openapi_spec(self):
        spec_src = (ROOT / "relayshield_openapi_spec.py").read_text()
        m = re.search(
            r'"path":\s*"/v1/metered/incident-timeline",\s*\n\s*"price_cents":\s*(\d+)', spec_src)
        self.assertIsNotNone(m, "spec entry not found")
        self.assertEqual(int(m.group(1)), api.METERED_CREDIT_COSTS["/v1/metered/incident-timeline"])

    def test_it_has_a_price_card_on_the_landing_page(self):
        """A price wired into billing with no card on api.relayshield.net/
        developers is the inline-mode defect: live, charged, pointed at by
        nobody who is not already reading the OpenAPI spec. This is a
        generated-artefact check the same shape as the others -- read the
        SERVED price grid, not a claim that a card exists."""
        page_src = (ROOT / "relayshield_developer_signup.py").read_text()
        m = re.search(
            r'<div class="endpoint">/v1/metered/incident-timeline</div>\s*\n'
            r'\s*<div class="price">\$([\d.]+)<span class="per"> / call</span></div>',
            page_src)
        self.assertIsNotNone(m, "no price-card found for /v1/metered/incident-timeline "
                              "on the api.relayshield.net/developers price grid")
        cents_on_page = round(float(m.group(1)) * 100)
        self.assertEqual(cents_on_page, api.METERED_CREDIT_COSTS["/v1/metered/incident-timeline"],
                          "the landing page quotes a different price than METERED_CREDIT_COSTS "
                          "-- copy shown to a buyer that disagrees with what we charge is a "
                          "price we do not honour")


if __name__ == "__main__":
    unittest.main()
