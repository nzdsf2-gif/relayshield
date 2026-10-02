"""Composite counterparty score: POST /v1/composite-check, EXECUTED not grepped.

One POST takes url / wallet / email (any subset), fans out to the existing
keyless check handlers server-side, and returns a single risk score + level
+ per-signal breakdown. Combination rule: RISKIEST SIGNAL WINS. Score is
monotonic in the worst signal (high=90, medium=55, unknown=15 base, +5 per
additional medium/high signal, capped at 100).

Invariants asserted throughout: no verdict ever says "safe"; levels are
only high/medium/unknown (email "low" and wallet "LOW" map to unknown);
every signal carries reasons; one failing sub-check degrades to unknown
instead of killing the composite. Sub-handlers are monkeypatched -- no
network, no corpus, no upstreams.
"""
import inspect
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


def _body_of(resp):
    return json.loads(resp["body"])


def _data_of(resp):
    body = _body_of(resp)
    assert body["ok"], body
    return body["data"]


def _fake_link(level, reasons=("link reason",), flagged=None):
    def h(params):
        return api._ok({
            "target": params.get("url"), "checked": True, "level": level,
            "flagged": level == "high" if flagged is None else flagged,
            "reasons": list(reasons), "signals": {},
        })
    return h


def _fake_wallet(risk_level, flags=()):
    def h(params):
        return api._ok({
            "address": params.get("address"), "chain": "evm",
            "risk_level": risk_level, "risk_flags": list(flags),
            "metadata": {},
        })
    return h


def _fake_email(risk, flags=()):
    def h(params):
        return api._ok({
            "risk": risk, "score": 0, "flags": list(flags), "notes": [],
        })
    return h


def _patch_subs(link=None, wallet=None, email=None):
    patches = []
    if link is not None:
        patches.append(unittest.mock.patch.object(api, "handle_link_check", link))
    if wallet is not None:
        patches.append(unittest.mock.patch.object(api, "handle_wallet_risk", wallet))
    if email is not None:
        patches.append(unittest.mock.patch.object(api, "handle_email_check", email))
    return patches


class CompositeBasics(unittest.TestCase):
    def test_empty_input_400(self):
        with _patch_subs(link=_fake_link("high"))[0]:
            resp = api.handle_composite_check({})
        self.assertEqual(resp["statusCode"], 400)
        self.assertIn("url", _body_of(resp)["error"])

    def test_email_must_be_object_400(self):
        with _patch_subs(link=_fake_link("high"))[0]:
            resp = api.handle_composite_check({"email": "a@b.com"})
        self.assertEqual(resp["statusCode"], 400)

    def test_routing_and_keyless(self):
        self.assertIs(api.ROUTES.get("/v1/composite-check"),
                      api.handle_composite_check)
        self.assertIn("/v1/composite-check", api.KEYLESS_SCAN_ENDPOINTS)

    def test_quota_units_per_input(self):
        u = api._link_check_units
        self.assertEqual(u("/v1/composite-check", {"url": "x"}), 1)
        self.assertEqual(u("/v1/composite-check",
                           {"url": "x", "wallet": "y"}), 2)
        self.assertEqual(u("/v1/composite-check",
                           {"url": "x", "wallet": "y",
                            "email": {"from_address": "a@b.com"}}), 3)
        self.assertEqual(u("/v1/composite-check", {}), 1)

    def test_sub_handler_param_shapes(self):
        seen = {}

        def link(params):
            seen["link"] = params
            return api._ok({"level": "unknown", "flagged": False,
                            "reasons": [], "signals": {}})

        def wallet(params):
            seen["wallet"] = params
            return api._ok({"risk_level": "LOW", "risk_flags": [],
                            "chain": "evm"})

        def email(params):
            seen["email"] = params
            return api._ok({"risk": "low", "flags": []})

        for p in _patch_subs(link=link, wallet=wallet, email=email):
            p.start()
        try:
            api.handle_composite_check({
                "url": "https://example.com",
                "wallet": "0xabc",
                "email": {"from_address": "a@b.com"},
            })
        finally:
            for p in _patch_subs(link=link, wallet=wallet, email=email):
                pass
        self.assertEqual(seen["link"], {"url": "https://example.com"})
        self.assertEqual(seen["wallet"], {"address": "0xabc"})
        self.assertEqual(seen["email"], {"from_address": "a@b.com"})


class CompositeCombination(unittest.TestCase):
    def _run(self, url_level=None, wallet_level=None, email_risk=None):
        patches = []
        params = {}
        if url_level is not None:
            params["url"] = "https://u.example"
            patches.append(unittest.mock.patch.object(
                api, "handle_link_check", _fake_link(url_level)))
        if wallet_level is not None:
            params["wallet"] = "0xabc"
            patches.append(unittest.mock.patch.object(
                api, "handle_wallet_risk", _fake_wallet(wallet_level)))
        if email_risk is not None:
            params["email"] = {"from_address": "a@b.com"}
            patches.append(unittest.mock.patch.object(
                api, "handle_email_check", _fake_email(email_risk)))
        for p in patches:
            p.start()
        try:
            return _data_of(api.handle_composite_check(params))
        finally:
            for p in patches:
                p.stop()

    def test_url_only_high(self):
        d = self._run(url_level="high")
        self.assertEqual(d["level"], "high")
        self.assertEqual(d["score"], 90)
        self.assertEqual(len(d["signals"]), 1)
        self.assertEqual(d["signals"][0]["type"], "url")
        self.assertIn("checked_at", d)

    def test_wallet_low_maps_to_unknown(self):
        d = self._run(wallet_level="LOW")
        self.assertEqual(d["level"], "unknown")
        self.assertEqual(d["score"], 15)
        self.assertEqual(d["signals"][0]["reasons"],
                         ["no risk flags from wallet screening"])

    def test_email_low_maps_to_unknown(self):
        d = self._run(email_risk="low")
        self.assertEqual(d["level"], "unknown")
        self.assertEqual(d["score"], 15)

    def test_riskiest_wins_matrix(self):
        cases = [
            # (url, wallet, email, expected composite level)
            ("high", "MEDIUM", "medium", "high"),
            ("medium", "LOW", "low", "medium"),
            ("unknown", "LOW", "low", "unknown"),
            (None, "HIGH", "low", "high"),
            ("medium", None, "high", "high"),
            (None, None, "medium", "medium"),
        ]
        for url_l, wal_l, em_r, expected in cases:
            with self.subTest(url=url_l, wallet=wal_l, email=em_r):
                d = self._run(url_level=url_l, wallet_level=wal_l,
                              email_risk=em_r)
                self.assertEqual(d["level"], expected)

    def test_corroboration_bump_and_cap(self):
        d = self._run(url_level="high", wallet_level="MEDIUM")
        self.assertEqual(d["score"], 95)
        d = self._run(url_level="high", wallet_level="MEDIUM",
                      email_risk="medium")
        self.assertEqual(d["score"], 100)  # 90 + 5 + 5, capped
        d = self._run(url_level="medium", wallet_level="MEDIUM")
        self.assertEqual(d["score"], 60)  # 55 + 5
        # unknown signals never corroborate
        d = self._run(url_level="high", wallet_level="LOW")
        self.assertEqual(d["score"], 90)

    def test_score_monotonic_in_worst_signal(self):
        s_high = self._run(url_level="high")["score"]
        s_med = self._run(url_level="medium")["score"]
        s_unk = self._run(url_level="unknown")["score"]
        self.assertGreater(s_high, s_med)
        self.assertGreater(s_med, s_unk)

    def test_signal_types_and_reasons(self):
        d = self._run(url_level="medium", wallet_level="HIGH",
                      email_risk="high")
        by_type = {s["type"]: s for s in d["signals"]}
        self.assertEqual(set(by_type), {"url", "wallet", "email"})
        for s in d["signals"]:
            self.assertIn(s["level"], ("high", "medium", "unknown"))
            self.assertTrue(s["reasons"])
        self.assertEqual(by_type["wallet"]["chain"], "evm")


class CompositeFailSoft(unittest.TestCase):
    def test_subcheck_exception_degrades_to_unknown(self):
        def boom(params):
            raise RuntimeError("upstream exploded")

        patches = [
            unittest.mock.patch.object(api, "handle_link_check",
                                       _fake_link("high")),
            unittest.mock.patch.object(api, "handle_wallet_risk", boom),
        ]
        for p in patches:
            p.start()
        try:
            d = _data_of(api.handle_composite_check(
                {"url": "https://u.example", "wallet": "0xabc"}))
        finally:
            for p in patches:
                p.stop()
        by_type = {s["type"]: s for s in d["signals"]}
        self.assertEqual(by_type["wallet"]["level"], "unknown")
        self.assertIn("failed", by_type["wallet"]["reasons"][0])
        # the good signal still wins
        self.assertEqual(d["level"], "high")
        self.assertEqual(d["score"], 90)

    def test_subcheck_400_becomes_unknown_signal(self):
        patches = [
            unittest.mock.patch.object(
                api, "handle_link_check",
                lambda params: api._err("url is required and must start with http")),
        ]
        for p in patches:
            p.start()
        try:
            d = _data_of(api.handle_composite_check({"url": "notaurl"}))
        finally:
            for p in patches:
                p.stop()
        self.assertEqual(d["level"], "unknown")
        self.assertIn("url is required", d["signals"][0]["reasons"][0])

    def test_all_subchecks_fail_still_responds(self):
        def boom(params):
            raise RuntimeError("down")

        patches = [unittest.mock.patch.object(api, n, boom) for n in
                   ("handle_link_check", "handle_wallet_risk",
                    "handle_email_check")]
        for p in patches:
            p.start()
        try:
            d = _data_of(api.handle_composite_check(
                {"url": "https://u.example", "wallet": "0xabc",
                 "email": {"from_address": "a@b.com"}}))
        finally:
            for p in patches:
                p.stop()
        self.assertEqual(d["level"], "unknown")
        self.assertEqual(len(d["signals"]), 3)
        self.assertTrue(all(s["level"] == "unknown" for s in d["signals"]))


class CompositeInvariants(unittest.TestCase):
    NEW_FUNCS = ("handle_composite_check", "_composite_signal_url",
                 "_composite_signal_wallet", "_composite_signal_email",
                 "_composite_subcall")

    def _scenario_payloads(self):
        payloads = []
        combos = [
            ({"url": "https://u.example"},
             {"link": _fake_link("high")}),
            ({"wallet": "0xabc"},
             {"wallet": _fake_wallet("HIGH", ["sanctioned"])}),
            ({"email": {"from_address": "a@b.com"}},
             {"email": _fake_email("low")}),
            ({"url": "https://u.example", "wallet": "0xabc",
              "email": {"from_address": "a@b.com"}},
             {"link": _fake_link("medium"), "wallet": _fake_wallet("LOW"),
              "email": _fake_email("medium", ["urgency"])}),
        ]
        name_map = {"link": "handle_link_check", "wallet": "handle_wallet_risk",
                    "email": "handle_email_check"}
        for params, fakes in combos:
            patches = [unittest.mock.patch.object(api, name_map[k], v)
                       for k, v in fakes.items()]
            for p in patches:
                p.start()
            try:
                payloads.append(json.dumps(
                    _data_of(api.handle_composite_check(params))).lower())
            finally:
                for p in patches:
                    p.stop()
        return payloads

    def test_never_says_safe_in_payloads(self):
        for payload in self._scenario_payloads():
            self.assertNotRegex(payload, r"\bsafe\b")

    def test_levels_only_high_medium_unknown(self):
        allowed = ("high", "medium", "unknown")
        for payload in self._scenario_payloads():
            data = json.loads(payload)
            self.assertIn(data["level"], allowed)
            for s in data["signals"]:
                self.assertIn(s["level"], allowed)

    def test_no_safe_or_low_in_new_code(self):
        src = "\n".join(inspect.getsource(getattr(api, f))
                        for f in self.NEW_FUNCS)
        stripped = re.sub(r'"[^"]*"|\'[^\']*\'', "", src)
        self.assertNotRegex(stripped, r"(?i)\bsafe\b")
        self.assertNotRegex(stripped, r"(?i)\blow\b")


if __name__ == "__main__":
    unittest.main()
