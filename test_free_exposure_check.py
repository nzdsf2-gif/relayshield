"""Crypto Shield Mobile: the one free exposure check per install, and the
anonymous funnel counters. EXECUTED against the real handler, through the real
dispatcher.

Three things here can only fail at runtime, which is why nothing is grepped:

  * the ORDER of the quota steps (an already-used install must cost no upstream
    call and no global-cap unit),
  * an incomplete answer must NOT spend the one check a user gets,
  * the table is written with UpdateItem expressions, and the fake below
    INTERPRETS the production expression strings rather than re-implementing
    their logic, so a wrong condition fails here instead of in production.
"""
import json
import logging
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


class _CondFail(Exception):
    def __init__(self, item):
        super().__init__("ConditionalCheckFailedException")
        self.response = {"Error": {"Code": "ConditionalCheckFailedException"},
                         "Item": {k: ({"S": v} if isinstance(v, str) else {"N": str(v)})
                                  for k, v in (item or {}).items()}}


class FakeQuotaTable:
    """Interprets the SPECIFIC UpdateItem/Condition shapes the handler writes.

    It evaluates the production ConditionExpression string itself (translated
    to Python), so changing the real expression changes what these tests see.
    Anything it does not recognise raises, so a new expression shape cannot
    slip past unexercised.
    """

    def __init__(self):
        self.items: dict[str, dict] = {}
        self.fail_writes = False
        self.calls = []

    def _eval_cond(self, cond, item, vals):
        expr = cond
        expr = re.sub(r"attribute_not_exists\(usage_key\)", "(__missing__)", expr)
        expr = re.sub(r"\bAND\b", " and ", expr)
        expr = re.sub(r"\bOR\b", " or ", expr)
        expr = re.sub(r"\bst = (:\w+)", lambda m: f"(__get__('st') == __v__['{m.group(1)}'])", expr)
        expr = re.sub(r"\brat < (:\w+)", lambda m: f"(__get__('rat') < __v__['{m.group(1)}'])", expr)
        env = {"__missing__": item is None,
               "__get__": lambda k: (item or {}).get(k, 0 if k == "rat" else None),
               "__v__": vals}
        leftover = re.sub(r"\(__missing__\)|\(__get__\('\w+'\) (==|<) __v__\['[:\w]+'\]\)|and|or|[() ]", "", expr)
        if leftover:
            raise AssertionError(f"fake cannot interpret condition fragment: {leftover!r} in {cond!r}")
        return bool(eval(expr, {"__builtins__": {}}, env))  # noqa: S307 - test-only, input is our own constant

    def update_item(self, **kw):
        self.calls.append(kw)
        if self.fail_writes:
            raise RuntimeError("dynamodb down")
        key = kw["Key"]["usage_key"]
        vals = kw.get("ExpressionAttributeValues", {})
        item = self.items.get(key)
        if kw.get("ConditionExpression") and not self._eval_cond(kw["ConditionExpression"], item, vals):
            raise _CondFail(item)
        upd = kw["UpdateExpression"]
        cur = dict(item or {"usage_key": key})
        add = re.search(r"ADD (\w+) (:\w+)", upd)
        if add:
            cur[add.group(1)] = cur.get(add.group(1), 0) + vals[add.group(2)]
        for attr, ph in re.findall(r"(\w+) = (:\w+)", upd.split("ADD")[0] if not add else upd.split("SET")[-1]):
            cur[attr] = vals[ph]
        m = re.search(r"(\w+) = if_not_exists\(\w+, (:\w+)\)", upd)
        if m:
            cur.setdefault(m.group(1), vals[m.group(2)])
        self.items[key] = cur
        return {"Attributes": {k: v for k, v in cur.items()}}


class FakeDDB:
    def __init__(self):
        self.table = FakeQuotaTable()

    def Table(self, name):  # noqa: N802
        return self.table


def _ok(data):
    return {"statusCode": 200, "headers": {}, "body": json.dumps({"ok": True, "data": data})}


def _err(msg, status):
    return {"statusCode": status, "headers": {}, "body": json.dumps({"ok": False, "error": msg})}


BREACH_HIT = _ok({"breach_count": 2, "breaches": [
    {"name": "Adobe", "breach_date": "2013-10-04", "data_classes": ["Email addresses", "Passwords"]},
    {"name": "Canva", "breach_date": "2019-05-24", "data_classes": ["Email addresses", "Usernames"]},
]})
BREACH_CLEAN = _ok({"breach_count": 0, "breaches": []})
STEAL_HIT = _ok({"found": True, "stealer_count": 1, "stealers": [
    {"date_compromised": "2024-03-01", "computer_name": "DESKTOP-ABC123",
     "malware_path": "C:\\Users\\x\\a.exe", "operating_system": "Windows 10"}]})
STEAL_CLEAN = _ok({"found": False, "stealer_count": 0, "stealers": []})

INSTALL = "a1b2c3d4-e5f6-4789-8abc-def012345678"
EMAIL = "alice.wonder@example.org"


class Harness(unittest.TestCase):
    def setUp(self):
        self.ddb = FakeDDB()
        self.table = self.ddb.table
        self.calls = {"breach": 0, "steal": 0}
        self._patches = [
            unittest.mock.patch.object(api, "dynamodb", self.ddb),
            unittest.mock.patch.object(api, "_check_keyless_ip_quota", lambda *a, **k: True),
        ]
        for p in self._patches:
            p.start()
        self.breach = BREACH_CLEAN
        self.steal = STEAL_CLEAN
        self._p_b = unittest.mock.patch.object(api, "handle_breach", self._breach)
        self._p_s = unittest.mock.patch.object(api, "handle_infostealer", self._steal)
        self._p_b.start(); self._p_s.start()

    def tearDown(self):
        self._p_b.stop(); self._p_s.stop()
        for p in self._patches:
            p.stop()

    def _breach(self, params, *a, **k):
        self.calls["breach"] += 1
        return self.breach

    def _steal(self, params):
        self.calls["steal"] += 1
        return self.steal

    def run_check(self, email=EMAIL, install=INSTALL):
        return api.handle_free_exposure_check({"email": email, "install_id": install}, "1.2.3.4")


def data(resp):
    return json.loads(resp["body"])["data"]


class TheAllowance(Harness):
    def test_a_clean_answer_is_nothing_known_never_safe(self):
        r = self.run_check()
        self.assertEqual(r["statusCode"], 200)
        d = data(r)
        self.assertEqual(d["level"], "nothing_known")
        self.assertNotIn("safe", json.dumps(d).lower())

    def test_findings_are_reported_with_the_data_that_leaked(self):
        self.breach, self.steal = BREACH_HIT, STEAL_HIT
        d = data(self.run_check())
        self.assertEqual(d["level"], "found")
        self.assertEqual(d["breach"]["count"], 2)
        self.assertTrue(d["breach"]["password_exposed"])
        self.assertEqual(d["breach"]["names"][0], "Canva")        # newest first
        self.assertEqual(d["infostealer"]["found"], True)
        self.assertEqual(d["infostealer"]["newest"], "2024-03-01")

    def test_no_device_identifying_field_is_returned(self):
        self.steal = STEAL_HIT
        blob = json.dumps(data(self.run_check()))
        for leaked in ("DESKTOP-ABC123", "malware_path", "computer_name", "a.exe"):
            self.assertNotIn(leaked, blob)

    def test_a_second_check_on_the_same_install_is_refused_and_costs_nothing(self):
        self.run_check()
        before = dict(self.calls)
        days_before = {k: dict(v) for k, v in self.table.items.items() if k.startswith("fxday#")}
        d = data(self.run_check(email="someone.else@example.org"))
        self.assertTrue(d["already_used"])
        self.assertEqual(self.calls, before, "an already-used install reached an upstream")
        days_after = {k: dict(v) for k, v in self.table.items.items() if k.startswith("fxday#")}
        self.assertEqual(days_before, days_after, "a refused call still spent a global-cap unit")

    def test_an_INCOMPLETE_answer_does_not_spend_the_one_check(self):
        self.breach = _err("HIBP rate limit reached", 429)
        self.steal = STEAL_HIT
        d = data(self.run_check())
        self.assertEqual(d["level"], "found")           # what WAS found is still said
        self.assertFalse(d["complete"])
        self.assertFalse(d["breach"]["checked"])
        self.assertEqual(d["allowance"], {"used": False, "remaining": 1})
        # ...and the retry is allowed and completes.
        self.breach = BREACH_CLEAN
        d2 = data(self.run_check())
        self.assertTrue(d2["complete"])
        self.assertEqual(d2["allowance"], {"used": True, "remaining": 0})

    def test_could_not_check_is_never_rendered_as_clear(self):
        self.breach = _err("upstream", 502)
        self.steal = _err("upstream", 502)
        d = data(self.run_check())
        self.assertEqual(d["level"], "incomplete")
        self.assertIsNone(d["breach"]["count"])
        self.assertIsNone(d["infostealer"]["found"])

    def test_a_sub_check_that_RAISES_is_treated_as_not_completed(self):
        def boom(params, *a, **k):
            raise RuntimeError("socket")
        with unittest.mock.patch.object(api, "handle_infostealer", boom):
            d = data(self.run_check())
        self.assertFalse(d["infostealer"]["checked"])
        self.assertEqual(d["level"], "incomplete")


class TheLimits(Harness):
    def test_a_check_already_running_is_busy_not_used(self):
        h = api._sha256(INSTALL)[:40]
        self.table.items[f"fxi#{h}"] = {"usage_key": f"fxi#{h}", "st": "r", "rat": int(__import__("time").time())}
        r = self.run_check()
        self.assertEqual(r["statusCode"], 429)
        self.assertEqual(self.calls, {"breach": 0, "steal": 0})

    def test_a_STALE_reservation_does_not_lock_the_install_out_forever(self):
        h = api._sha256(INSTALL)[:40]
        old = int(__import__("time").time()) - api.FREE_EXPOSURE_RESERVE_TTL - 5
        self.table.items[f"fxi#{h}"] = {"usage_key": f"fxi#{h}", "st": "r", "rat": old}
        self.assertEqual(self.run_check()["statusCode"], 200)

    def test_the_global_daily_cap_refuses_releases_the_install_and_calls_nothing(self):
        day = f"fxday#{api.datetime.now(api.timezone.utc).strftime('%Y-%m-%d')}"
        self.table.items[day] = {"usage_key": day, "n": api.FREE_EXPOSURE_DAILY_CAP}
        r = self.run_check()
        self.assertEqual(r["statusCode"], 429)
        self.assertEqual(self.calls, {"breach": 0, "steal": 0})
        # The user was refused through no fault of theirs: tomorrow it must work.
        self.table.items[day]["n"] = 0
        self.assertEqual(self.run_check()["statusCode"], 200)

    def test_it_FAILS_CLOSED_when_the_quota_table_is_down(self):
        self.table.fail_writes = True
        r = self.run_check()
        self.assertEqual(r["statusCode"], 503)
        self.assertEqual(self.calls, {"breach": 0, "steal": 0},
                         "a quota outage must not become unmetered access to the shared HIBP key")

    def test_the_per_ip_cap_is_enforced_before_anything_is_reserved(self):
        with unittest.mock.patch.object(api, "_check_keyless_ip_quota", lambda *a, **k: False):
            r = self.run_check()
        self.assertEqual(r["statusCode"], 429)
        self.assertEqual(self.table.items, {})

    def test_bad_input_is_rejected_before_any_write(self):
        for email, install in (("not-an-email", INSTALL), ("a@b", INSTALL), ("", INSTALL),
                               (EMAIL, "short"), (EMAIL, "has spaces in it which is invalid"),
                               (EMAIL, "")):
            r = self.run_check(email=email, install=install)
            self.assertEqual(r["statusCode"], 400, (email, install))
        self.assertEqual(self.table.items, {})


class ThePrivacyPosture(Harness):
    def test_neither_the_email_nor_the_raw_install_id_is_stored(self):
        self.run_check()
        stored = json.dumps(self.table.items, default=str)
        self.assertNotIn(INSTALL, stored)
        self.assertNotIn(EMAIL, stored)
        self.assertNotIn("alice", stored)

    def test_the_email_never_reaches_a_log_line(self):
        self.breach, self.steal = BREACH_HIT, STEAL_HIT
        with self.assertLogs(api.logger, level=logging.DEBUG) as cm:
            self.run_check()
        joined = "\n".join(cm.output)
        self.assertNotIn(EMAIL, joined)
        self.assertNotIn("alice", joined)
        self.assertNotIn(INSTALL, joined)
        self.assertRegex(joined, r"free_exposure_check outcome=served level=found")


class TheRoutes(Harness):
    """Through lambda_handler, because the 502 that took every keyless endpoint
    down on 2026-09-22 lived in the dispatcher and a handler-only suite is
    structurally blind to that class."""

    def _post(self, path, payload):
        ev = {"path": path, "httpMethod": "POST", "body": json.dumps(payload), "headers": {},
              "requestContext": {"identity": {"sourceIp": "9.9.9.9"}}}
        return api.lambda_handler(ev, None)

    def test_the_free_check_is_reachable_with_NO_api_key(self):
        r = self._post("/v1/app/free-exposure-check", {"email": EMAIL, "install_id": INSTALL})
        self.assertEqual(r["statusCode"], 200, r["body"])
        self.assertTrue(json.loads(r["body"])["ok"])

    def test_the_trailing_slash_form_routes_too(self):
        r = self._post("/v1/app/free-exposure-check/", {"email": EMAIL, "install_id": INSTALL})
        self.assertEqual(r["statusCode"], 200)

    def test_a_GET_is_not_a_free_check(self):
        ev = {"path": "/v1/app/free-exposure-check", "httpMethod": "GET", "headers": {}}
        self.assertNotEqual(api.lambda_handler(ev, None)["statusCode"], 200)
        self.assertEqual(self.calls, {"breach": 0, "steal": 0})

    def test_the_source_ip_reaches_the_quota(self):
        seen = []
        with unittest.mock.patch.object(api, "_check_keyless_ip_quota",
                                        lambda ip, units=1: seen.append((ip, units)) or True):
            self._post("/v1/app/free-exposure-check", {"email": EMAIL, "install_id": INSTALL})
        self.assertEqual(seen, [("9.9.9.9", api.FREE_EXPOSURE_IP_UNITS)])


class TheFunnelCounters(unittest.TestCase):
    def _event(self, **p):
        with self.assertLogs(api.logger, level=logging.INFO) as cm:
            r = api.handle_app_event(p)
        return r, [line for line in cm.output if "app_event" in line]

    def test_an_allowed_event_is_logged_in_the_shape_the_funnel_tool_reads(self):
        r, lines = self._event(event="paywall_viewed", ctx="scan_gate", version="1.7.0", platform="solana")
        self.assertEqual(r["statusCode"], 200)
        self.assertEqual(len(lines), 1)
        self.assertIn("app_event name=paywall_viewed ctx=scan_gate v=1.7.0 platform=solana", lines[0])

    def test_an_unknown_event_is_refused_and_logs_nothing(self):
        with self.assertNoLogs(api.logger, level=logging.INFO):
            self.assertEqual(api.handle_app_event({"event": "anything_else"})["statusCode"], 400)

    def test_a_forged_second_line_cannot_be_injected(self):
        r, lines = self._event(event="checkout_tapped",
                               ctx="x\napp_event name=paywall_viewed ctx=forged v=9 platform=z",
                               version="1.7.0 extra", platform="solana\r\nboo")
        self.assertEqual(len(lines), 1)
        self.assertNotIn("forged", lines[0])
        self.assertIn("ctx=- v=- platform=-", lines[0])

    def test_no_identifier_is_ever_accepted_into_the_line(self):
        _, lines = self._event(event="wallet_connected", ctx="ok", version="1.7.0", platform="solana",
                               install_id=INSTALL, push_token="ExponentPushToken[abc]",
                               email=EMAIL, ip="1.2.3.4")
        for needle in (INSTALL, "ExponentPushToken", EMAIL, "1.2.3.4"):
            self.assertNotIn(needle, lines[0])

    def test_the_four_events_are_exactly_the_funnel_questions(self):
        self.assertEqual(api.APP_EVENT_NAMES, frozenset(
            {"paywall_viewed", "checkout_tapped", "wallet_connected", "onboarding_completed"}))

    def test_the_route_is_open_and_needs_no_key(self):
        ev = {"path": "/v1/app/event", "httpMethod": "POST", "headers": {},
              "body": json.dumps({"event": "paywall_viewed", "ctx": "modal", "version": "1.7.0",
                                  "platform": "solana"}),
              "requestContext": {"identity": {"sourceIp": "9.9.9.9"}}}
        r = api.lambda_handler(ev, None)
        self.assertEqual(r["statusCode"], 200, r["body"])


if __name__ == "__main__":
    unittest.main()
