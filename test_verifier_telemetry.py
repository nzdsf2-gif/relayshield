"""Opt-in telemetry for the hosted verifiers (TAP, PAP, x401).

Everything here EXECUTES the code with boto3 stubbed. A suite that only reads the source
cannot see an ordering, a truthiness bug or a swallowed exception, and the privacy
promise made in cloudflare_worker_privacy.js section 13 depends on all three.

What each class guards:
  Pure         the row is exactly what the policy says, and nothing else
  OptIn        the default is OFF and only a real boolean True turns it on
  MaybeReport  accepts never touch DynamoDB; the agent's headers are not the customer's
  TapWiring    the verdict is final before telemetry runs, and telemetry cannot change it
  ConfigRoute  POST /v1/verifiers/config through the DISPATCHER, not the handler
  DeleteTool   the deletion promise in the policy has a tool behind it
"""
import ast
import hashlib
import json
import pathlib
import sys
import types
import unittest
import unittest.mock

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))


def _stub_aws():
    boto3 = types.ModuleType("boto3"); boto3.__path__ = []
    boto3.resource = lambda *a, **k: unittest.mock.MagicMock()
    boto3.client = lambda *a, **k: unittest.mock.MagicMock()
    conditions = types.ModuleType("boto3.dynamodb.conditions")
    conditions.Key = lambda *a, **k: unittest.mock.MagicMock()
    conditions.Attr = lambda *a, **k: unittest.mock.MagicMock()
    ddb = types.ModuleType("boto3.dynamodb"); ddb.__path__ = []
    ddb.conditions = conditions
    boto3.dynamodb = ddb
    sys.modules.setdefault("boto3", boto3)
    sys.modules.setdefault("boto3.dynamodb", ddb)
    sys.modules.setdefault("boto3.dynamodb.conditions", conditions)
    sys.modules.setdefault("boto3.session", types.ModuleType("boto3.session"))
    bc = types.ModuleType("botocore"); bc.__path__ = []
    ex = types.ModuleType("botocore.exceptions")

    class _CE(Exception):
        pass
    ex.ClientError = _CE; ex.BotoCoreError = _CE; bc.exceptions = ex
    sys.modules.setdefault("botocore", bc)
    sys.modules.setdefault("botocore.exceptions", ex)


_stub_aws()
import relayshield_verifier_telemetry as vt  # noqa: E402
import relayshield_tap_verifier as tap  # noqa: E402
import relayshield_api as api  # noqa: E402
import delete_verifier_reports as dvr  # noqa: E402

KEY = "rs_live_" + "a" * 32
NOW = 1_800_000_000  # 2027-01-15 UTC


class Verdict:
    def __init__(self, decision, reasons, details=None):
        self.decision, self.reasons, self.details = decision, reasons, details or {}


class FakeKeyTable:
    def __init__(self, record=None, boom=False):
        self.record, self.boom, self.gets = record, boom, []

    def get_item(self, Key, ConsistentRead=False):
        self.gets.append((Key, ConsistentRead))
        if self.boom:
            raise RuntimeError("lookup failed for " + Key["api_key"])
        return {"Item": self.record} if self.record is not None else {}


class FakeTelemetryTable:
    def __init__(self, boom=False):
        self.puts, self.boom = [], boom

    def put_item(self, Item):
        if self.boom:
            raise RuntimeError("write failed")
        self.puts.append(Item)


def active_record(**over):
    r = {"api_key": KEY, "active": True, vt.OPT_IN_FIELD: True}
    r.update(over)
    return r


def api_event(key=KEY):
    return {"headers": {"X-RS-API-KEY": key}} if key else {"headers": {}}


class Pure(unittest.TestCase):
    def test_classify_maps_every_real_tap_reason(self):
        cases = {
            "bad_signature": "bad_signature", "bad_signature_encoding": "bad_signature",
            "missing_signature_for_label": "bad_signature",
            "signature_too_old": "expired", "signature_expired": "expired",
            "created_in_future": "expired", "replay_nonce": "replay",
            "unknown_keyid": "unknown_key", "intent_mismatch": "intent_mismatch",
            "ti_flagged": "ti_match", "mandate_scope_exceeded": "mandate_exceeded",
            "missing_signature_headers": "malformed", "missing_param_nonce": "malformed",
            "malformed_signature_input": "malformed", "unsupported_alg": "malformed",
            "bad_created": "malformed", "base_construction_failed": "malformed",
            "missing_covered_components": "malformed",
        }
        for raw, want in cases.items():
            self.assertEqual(vt.classify_reason([raw]), want, raw)
        self.assertTrue(set(cases.values()) <= set(vt.REJECTION_REASONS))

    def test_every_reason_the_tap_verifier_can_emit_is_classified(self):
        """Read the reasons out of verify_tap_request itself, so a new one added later
        either maps or lands on "other" -- it can never raise or be stored raw."""
        src = (ROOT / "relayshield_tap_verifier.py").read_text()
        tree = ast.parse(src)
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "verify_tap_request")
        reasons = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("_reject", "_review"):
                for a in node.args:
                    if isinstance(a, ast.Constant) and isinstance(a.value, str):
                        reasons.add(a.value)
                    elif isinstance(a, ast.JoinedStr):
                        reasons.add("missing_param_x")  # f"missing_param_{req_param}"
        self.assertGreater(len(reasons), 15, "the AST walk found too few reasons to mean anything")
        for r in reasons:
            got = vt.classify_reason([r])
            self.assertTrue(got is None or got in vt.REJECTION_REASONS, r)

    def test_our_own_infrastructure_failing_is_not_reported_as_an_attack(self):
        for raw in ("nonce_store_error", "ti_unavailable", "jwks_unavailable"):
            self.assertIsNone(vt.classify_reason([raw]))
            self.assertIsNone(vt.build_event("tap", Verdict("reject", [raw])))

    def test_unknown_reason_is_other_and_the_raw_string_is_never_stored(self):
        secret_looking = "some_new_reason_with_key_abc123"
        item = vt.build_event("tap", Verdict("reject", [secret_looking]), now=NOW)
        self.assertEqual(item["rejection_reason"], "other")
        self.assertNotIn("abc123", json.dumps(item))

    def test_network_prefix(self):
        self.assertEqual(vt.network_prefix("8.8.4.4"), "8.8.4.0/24")
        self.assertEqual(vt.network_prefix("2606:4700:4700::1111"), "2606:4700:4700::/48")
        for private in ("10.0.0.5", "192.168.1.9", "127.0.0.1", "169.254.1.1", "::1", "fe80::1",
                        "100.64.0.1"):
            self.assertEqual(vt.network_prefix(private), "", private)
        for junk in (None, "", "not an ip", 12345, "8.8.4", "8.8.4.4/24"):
            self.assertEqual(vt.network_prefix(junk), "", repr(junk))

    def test_hash_id(self):
        self.assertEqual(vt.hash_id("  did:web:agent.example  "),
                         hashlib.sha256(b"did:web:agent.example").hexdigest())
        for empty in (None, "", "   ", 5):
            self.assertEqual(vt.hash_id(empty), "")

    def test_only_a_rejection_produces_a_row(self):
        for decision in ("accept", "review"):
            self.assertIsNone(vt.build_event("tap", Verdict(decision, ["signature_valid"])))
        self.assertIsNotNone(vt.build_event("tap", Verdict("reject", ["bad_signature"])))
        self.assertIsNone(vt.build_event("tap", {"decision": "accept", "reasons": []}))
        self.assertIsNotNone(vt.build_event("tap", {"decision": "reject", "reasons": ["replay_nonce"]}))

    def test_unknown_verifier_type_is_refused(self):
        self.assertIsNone(vt.build_event("visa", Verdict("reject", ["bad_signature"])))

    def test_row_shape_and_ttl(self):
        item = vt.build_event("tap", Verdict("reject", ["bad_signature"]), agent_id="kid-1",
                              agent_ip="8.8.4.4", reporter="0123456789abcdef", now=NOW)
        self.assertEqual(item["pk"], "TELEMETRY#2027-01-15")
        self.assertRegex(item["sk"], r"^\d{10}#[0-9a-f]{32}$")
        self.assertEqual(item["ttl"], NOW + 90 * 86400)
        self.assertEqual(vt.TTL_DAYS, 90)
        self.assertEqual(item["agent_id_hash"], hashlib.sha256(b"kid-1").hexdigest())
        self.assertEqual(item["ip_prefix"], "8.8.4.0/24")
        self.assertEqual(item["verifier_type"], "tap")
        self.assertEqual(item["reporter_hash"], "0123456789abcdef")

    def test_no_raw_identifier_or_address_appears_in_any_value(self):
        item = vt.build_event("tap", Verdict("reject", ["bad_signature"]),
                              agent_id="did:web:very-recognisable.example", agent_ip="8.8.4.4",
                              now=NOW)
        blob = json.dumps(item)
        self.assertNotIn("very-recognisable", blob)
        self.assertNotIn("8.8.4.4", blob)

    def test_empty_attributes_are_omitted_so_the_gsi_stays_sparse(self):
        """agent_id_hash is the AgentHashIndex key and DynamoDB refuses an empty-string
        key attribute. A rejection with no agent id must simply not carry the attribute."""
        item = vt.build_event("tap", Verdict("reject", ["missing_signature_headers"]), now=NOW)
        for absent in ("agent_id_hash", "ip_prefix", "attack_pattern", "issuer_hash", "reporter_hash"):
            self.assertNotIn(absent, item)
        self.assertNotIn("", item.values())

    def test_attack_pattern_only_on_a_ti_match_and_never_an_indicator(self):
        ti = vt.build_event("tap", Verdict("reject", ["ti_flagged"]),
                            screened=["wallet", "domain"], now=NOW)
        self.assertEqual(ti["attack_pattern"], "wallet+domain")
        one = vt.build_event("tap", Verdict("reject", ["ti_flagged"]), screened=["domain"], now=NOW)
        self.assertEqual(one["attack_pattern"], "domain")
        other = vt.build_event("tap", Verdict("reject", ["bad_signature"]),
                               screened=["wallet"], now=NOW)
        self.assertNotIn("attack_pattern", other)
        junk = vt.build_event("tap", Verdict("reject", ["ti_flagged"]),
                              screened=["0xDEADBEEF", "evil.example"], now=NOW)
        self.assertNotIn("attack_pattern", junk)

    def test_issuer_hash_is_x401_only(self):
        tap_item = vt.build_event("tap", Verdict("reject", ["bad_signature"]),
                                  issuer="did:web:issuer.example", now=NOW)
        self.assertNotIn("issuer_hash", tap_item)
        for vtype in ("x401", "tap+x401"):
            x = vt.build_event(vtype, Verdict("reject", ["mandate_scope_exceeded"]),
                               issuer="did:web:issuer.example", now=NOW)
            self.assertEqual(x["issuer_hash"], hashlib.sha256(b"did:web:issuer.example").hexdigest())
            self.assertEqual(x["rejection_reason"], "mandate_exceeded")

    def test_the_attribute_set_is_closed(self):
        full = vt.build_event("x401", Verdict("reject", ["ti_flagged"]), agent_id="a",
                              agent_ip="8.8.4.4", issuer="i", screened=["wallet"],
                              reporter="0123456789abcdef", now=NOW)
        self.assertEqual(set(full), {"pk", "sk", "rejection_reason", "verifier_type", "ttl",
                                     "agent_id_hash", "ip_prefix", "attack_pattern",
                                     "issuer_hash", "reporter_hash"})


class OptIn(unittest.TestCase):
    def test_default_is_off_for_every_kind_of_not_true(self):
        for value in (None, False, "true", "false", "True", 1, 0, [], {}, "yes"):
            rec = {"api_key": KEY, "active": True}
            if value is not None:
                rec[vt.OPT_IN_FIELD] = value
            self.assertEqual(vt.opted_in(api_event(), FakeKeyTable(rec)), (False, ""), repr(value))

    def test_missing_record_inactive_key_and_wrong_prefix_are_all_off(self):
        self.assertEqual(vt.opted_in(api_event(), FakeKeyTable(None)), (False, ""))
        self.assertEqual(vt.opted_in(api_event(), FakeKeyTable(active_record(active=False))), (False, ""))
        self.assertEqual(vt.opted_in(api_event(), FakeKeyTable(active_record(active=None))), (False, ""))
        demo = "rs_demo_" + "b" * 32
        t = FakeKeyTable(active_record(api_key=demo))
        self.assertEqual(vt.opted_in(api_event(demo), t), (False, ""))
        self.assertEqual(t.gets, [], "a non-live key must not even reach DynamoDB")

    def test_no_key_header_never_reaches_dynamodb(self):
        t = FakeKeyTable(active_record())
        self.assertEqual(vt.opted_in(api_event(None), t), (False, ""))
        self.assertEqual(vt.opted_in({}, t), (False, ""))
        self.assertEqual(vt.opted_in(None, t), (False, ""))
        self.assertEqual(t.gets, [])

    def test_a_real_boolean_true_on_an_active_key_is_on(self):
        t = FakeKeyTable(active_record())
        ok, rhash = vt.opted_in(api_event(), t)
        self.assertTrue(ok)
        self.assertEqual(rhash, hashlib.sha256(KEY.encode()).hexdigest()[:16])
        self.assertNotIn(KEY, rhash)
        self.assertEqual(t.gets, [({"api_key": KEY}, True)], "must be a CONSISTENT read")

    def test_header_name_is_case_insensitive_and_x_api_key_is_accepted(self):
        for hdr in ("x-rs-api-key", "X-Rs-Api-Key", "X-API-Key", "x-api-key"):
            self.assertTrue(vt.opted_in({"headers": {hdr: KEY}}, FakeKeyTable(active_record()))[0], hdr)

    def test_a_failed_lookup_is_off_and_the_log_never_carries_the_key(self):
        with self.assertLogs(level="WARNING") as cm:
            res = vt.opted_in(api_event(), FakeKeyTable(boom=True))
        self.assertEqual(res, (False, ""))
        self.assertNotIn(KEY, "\n".join(cm.output))


class MaybeReport(unittest.TestCase):
    def _go(self, verdict, *, record=None, request=None, event=None, vtype="tap", **kw):
        keys = FakeKeyTable(record if record is not None else active_record())
        tel = FakeTelemetryTable()
        wrote = vt.maybe_report(vtype, verdict, api_event() if event is None else event,
                                request, key_table=keys, telemetry_table=tel, **kw)
        return wrote, keys, tel

    def test_an_accept_or_review_touches_nothing(self):
        for decision in ("accept", "review"):
            wrote, keys, tel = self._go(Verdict(decision, ["x"]))
            self.assertFalse(wrote)
            self.assertEqual(keys.gets, [], decision + " must not cost a DynamoDB read")
            self.assertEqual(tel.puts, [])

    def test_a_rejection_from_our_own_failure_touches_nothing(self):
        wrote, keys, tel = self._go(Verdict("reject", ["nonce_store_error"]))
        self.assertFalse(wrote)
        self.assertEqual(keys.gets, [])

    def test_opted_out_reads_the_record_once_and_writes_nothing(self):
        wrote, keys, tel = self._go(Verdict("reject", ["bad_signature"]),
                                    record={"api_key": KEY, "active": True})
        self.assertFalse(wrote)
        self.assertEqual(len(keys.gets), 1)
        self.assertEqual(tel.puts, [])

    def test_opted_in_writes_exactly_one_row(self):
        wrote, _, tel = self._go(
            Verdict("reject", ["unknown_keyid"], {"keyid": "kid-9"}),
            request={"headers": {}, "authority": "shop.example", "agent_ip": "8.8.4.4"})
        self.assertTrue(wrote)
        self.assertEqual(len(tel.puts), 1)
        row = tel.puts[0]
        self.assertEqual(row["rejection_reason"], "unknown_key")
        self.assertEqual(row["agent_id_hash"], hashlib.sha256(b"kid-9").hexdigest())
        self.assertEqual(row["ip_prefix"], "8.8.4.0/24")
        self.assertEqual(row["reporter_hash"], hashlib.sha256(KEY.encode()).hexdigest()[:16])
        self.assertNotIn("shop.example", json.dumps(row), "the merchant's domain is never stored")

    def test_agent_id_in_the_request_wins_over_the_verdict_keyid(self):
        _, _, tel = self._go(Verdict("reject", ["bad_signature"], {"keyid": "from-details"}),
                             request={"agent_id": "from-request"})
        self.assertEqual(tel.puts[0]["agent_id_hash"], hashlib.sha256(b"from-request").hexdigest())

    def test_ti_match_records_what_was_screened_and_never_the_indicator(self):
        _, _, tel = self._go(Verdict("reject", ["ti_flagged"], {"ti_reasons": ["0xBAD in corpus"]}),
                             request={"wallet": "0xBAD", "merchant_domain": "evil.example"})
        row = tel.puts[0]
        self.assertEqual(row["attack_pattern"], "wallet+domain")
        blob = json.dumps(row)
        self.assertNotIn("0xBAD", blob)
        self.assertNotIn("evil.example", blob)

    def test_the_agents_own_headers_are_not_the_customers_key(self):
        """request["headers"] are the AGENT's. Reading the customer's key from them would
        let any agent switch a customer's telemetry on or attribute rows to a stranger."""
        wrote, keys, tel = self._go(
            Verdict("reject", ["bad_signature"]), event=api_event(None),
            request={"headers": {"x-rs-api-key": KEY}})
        self.assertFalse(wrote)
        self.assertEqual(keys.gets, [])

    def test_the_callers_own_address_is_never_used_as_the_agents(self):
        ev = api_event()
        ev["requestContext"] = {"identity": {"sourceIp": "8.8.4.4"}}
        _, _, tel = self._go(Verdict("reject", ["bad_signature"]), event=ev, request={})
        self.assertNotIn("ip_prefix", tel.puts[0])

    def test_kill_switch(self):
        with unittest.mock.patch.dict("os.environ", {"VERIFIER_TELEMETRY_DISABLED": "1"}):
            wrote, keys, tel = self._go(Verdict("reject", ["bad_signature"]))
        self.assertFalse(wrote)
        self.assertEqual(keys.gets, [])

    def test_a_failed_write_returns_false_and_does_not_raise(self):
        keys = FakeKeyTable(active_record())
        wrote = vt.maybe_report("tap", Verdict("reject", ["bad_signature"]), api_event(), {},
                                key_table=keys, telemetry_table=FakeTelemetryTable(boom=True))
        self.assertFalse(wrote)

    def test_garbage_inputs_never_raise(self):
        for verdict in (None, object(), "reject", 5):
            self.assertFalse(vt.maybe_report("tap", verdict, None, None,
                                             key_table=FakeKeyTable(active_record()),
                                             telemetry_table=FakeTelemetryTable()))

    def test_pap_and_x401_use_the_same_call(self):
        for vtype in ("pap", "x401", "tap+x401"):
            wrote, _, tel = self._go(Verdict("reject", ["bad_signature"]), vtype=vtype)
            self.assertTrue(wrote, vtype)
            self.assertEqual(tel.puts[0]["verifier_type"], vtype)


class TapWiring(unittest.TestCase):
    def _event(self, body):
        return {"body": json.dumps(body), "headers": {"X-RS-API-KEY": KEY}}

    def test_a_rejection_is_reported_with_the_customers_event_and_the_agents_request(self):
        calls = []
        with unittest.mock.patch.object(vt, "maybe_report", lambda *a, **k: calls.append(a)):
            resp = tap.lambda_handler(self._event({"headers": {}, "authority": "shop.example"}), None)
        self.assertEqual(resp["statusCode"], 403)
        self.assertEqual(len(calls), 1)
        vtype, verdict, ev, request = calls[0]
        self.assertEqual(vtype, "tap")
        self.assertEqual(verdict.decision, "reject")
        self.assertEqual(ev["headers"]["X-RS-API-KEY"], KEY)
        self.assertEqual(request["authority"], "shop.example")

    def test_an_accept_or_review_is_never_reported(self):
        for decision, code in (("accept", 200), ("review", 202)):
            calls = []
            with unittest.mock.patch.object(tap, "verify_tap_request",
                                            lambda r, d=decision: tap.Verdict(d, ["x"])), \
                    unittest.mock.patch.object(vt, "maybe_report", lambda *a, **k: calls.append(a)):
                resp = tap.lambda_handler(self._event({}), None)
            self.assertEqual(resp["statusCode"], code)
            self.assertEqual(calls, [], decision)

    def test_telemetry_failing_cannot_change_the_verdict_or_the_response(self):
        def boom(*a, **k):
            raise RuntimeError("telemetry exploded")
        clean = tap.lambda_handler(self._event({"headers": {}}), None)
        with unittest.mock.patch.object(vt, "maybe_report", boom):
            hurt = tap.lambda_handler(self._event({"headers": {}}), None)
        self.assertEqual(clean, hurt)

    def test_the_module_missing_from_the_package_cannot_change_the_verdict(self):
        """A hand-deployed zip that forgot relayshield_verifier_telemetry.py must still
        verify. The import is inside the guarded helper, not at module top."""
        with unittest.mock.patch.dict(sys.modules, {"relayshield_verifier_telemetry": None}):
            resp = tap.lambda_handler(self._event({"headers": {}}), None)
        self.assertEqual(resp["statusCode"], 403)
        top = [n for n in ast.parse((ROOT / "relayshield_tap_verifier.py").read_text()).body
               if isinstance(n, (ast.Import, ast.ImportFrom))]
        for n in top:
            names = [a.name for a in n.names] + [getattr(n, "module", "") or ""]
            self.assertFalse(any("telemetry" in x for x in names), "import must not be top-level")

    def test_the_report_runs_after_the_verdict_and_never_reassigns_it(self):
        tree = ast.parse((ROOT / "relayshield_tap_verifier.py").read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "lambda_handler")
        verdict_line = report_line = None
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "verdict" for t in node.targets):
                self.assertIsNone(verdict_line, "verdict assigned twice")
                verdict_line = node.lineno
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "_report_rejection":
                report_line = node.lineno
        self.assertIsNotNone(verdict_line)
        self.assertIsNotNone(report_line)
        self.assertGreater(report_line, verdict_line)


class ConfigRoute(unittest.TestCase):
    """Through api.lambda_handler: handler-only tests cannot see a missing route."""

    def _call(self, method, body=None, key=KEY, record=None):
        updates = []

        class Table:
            def update_item(self, **kw):
                updates.append(kw)

        fake_ddb = unittest.mock.MagicMock()
        fake_ddb.Table = lambda name: Table()
        rec = record if record is not None else {"api_key": KEY, "active": True}
        ev = {"httpMethod": method, "path": "/v1/verifiers/config",
              "headers": {"X-RS-API-KEY": key} if key else {},
              "body": json.dumps(body) if body is not None else None}
        with unittest.mock.patch.object(api, "dynamodb", fake_ddb), \
                unittest.mock.patch.object(api, "_verify_rs_api_key",
                                           lambda k: rec if k == KEY else None):
            resp = api.lambda_handler(ev, None)
        return resp, json.loads(resp["body"]), updates

    def test_no_key_is_401(self):
        resp, body, updates = self._call("POST", {"telemetry_opt_in": True}, key=None)
        self.assertEqual(resp["statusCode"], 401)
        self.assertEqual(updates, [])

    def test_a_bad_key_is_401(self):
        resp, _, updates = self._call("POST", {"telemetry_opt_in": True}, key="rs_live_" + "z" * 32)
        self.assertEqual(resp["statusCode"], 401)
        self.assertEqual(updates, [])

    def test_get_reports_off_by_default(self):
        resp, body, _ = self._call("GET")
        self.assertEqual(resp["statusCode"], 200)
        self.assertIs(body["data"]["telemetry_opt_in"], False)

    def test_get_reports_on_only_for_a_real_true(self):
        for stored, want in ((True, True), ("true", False), (1, False), (False, False)):
            _, body, _ = self._call("GET", record={"api_key": KEY, "active": True,
                                                    "verifier_telemetry_opt_in": stored})
            self.assertIs(body["data"]["telemetry_opt_in"], want, repr(stored))

    def test_post_true_writes_a_real_boolean_and_a_timestamp(self):
        resp, body, updates = self._call("POST", {"telemetry_opt_in": True})
        self.assertEqual(resp["statusCode"], 200)
        self.assertIs(body["data"]["telemetry_opt_in"], True)
        self.assertEqual(len(updates), 1)
        u = updates[0]
        self.assertEqual(u["Key"], {"api_key": KEY})
        self.assertIs(u["ExpressionAttributeValues"][":v"], True)
        self.assertEqual(u["ExpressionAttributeNames"]["#f"], vt.OPT_IN_FIELD)
        self.assertEqual(u["ExpressionAttributeNames"]["#at"], vt.OPT_IN_AT_FIELD)
        self.assertIn("attribute_exists", u["ConditionExpression"], "must not CREATE a record")

    def test_post_false_turns_it_off(self):
        resp, _, updates = self._call("POST", {"telemetry_opt_in": False})
        self.assertEqual(resp["statusCode"], 200)
        self.assertIs(updates[0]["ExpressionAttributeValues"][":v"], False)

    def test_anything_that_is_not_a_json_boolean_is_refused_and_writes_nothing(self):
        for bad in ("true", "false", 1, 0, None, [], {}, "yes"):
            resp, _, updates = self._call("POST", {"telemetry_opt_in": bad})
            self.assertEqual(resp["statusCode"], 400, repr(bad))
            self.assertEqual(updates, [], repr(bad))
        resp, _, updates = self._call("POST", {})
        self.assertEqual(resp["statusCode"], 400)

    def test_the_response_never_contains_the_key(self):
        resp, _, _ = self._call("POST", {"telemetry_opt_in": True})
        self.assertNotIn(KEY, resp["body"])

    def test_other_methods_do_not_reach_the_handler(self):
        resp, _, updates = self._call("DELETE", {"telemetry_opt_in": True})
        self.assertNotEqual(resp["statusCode"], 200)
        self.assertEqual(updates, [])

    def test_what_the_api_writes_is_what_the_verifier_reads(self):
        """Two files that must agree: the attribute this route writes and the one the
        verifier reads. A rename in one would turn every opt-in into a silent no-op."""
        src = (ROOT / "relayshield_api.py").read_text()
        self.assertIn('field = "verifier_telemetry_opt_in"', src)
        self.assertEqual(vt.OPT_IN_FIELD, "verifier_telemetry_opt_in")
        self.assertEqual(vt.OPT_IN_AT_FIELD, "verifier_telemetry_opt_in_at")


class DeleteTool(unittest.TestCase):
    def test_hash_matches_the_writers_hash(self):
        self.assertEqual(dvr.reporter_hash(KEY), vt.reporter_hash(KEY))
        self.assertEqual(dvr.TABLE, vt.TABLE)

    def test_only_sixteen_lowercase_hex_is_accepted(self):
        self.assertTrue(dvr.is_reporter_hash("0123456789abcdef"))
        for bad in ("", "abc", "0123456789ABCDEF", "0123456789abcdeg", "0123456789abcdef0", None, 5):
            self.assertFalse(dvr.is_reporter_hash(bad), repr(bad))

    def test_scan_pages_through_everything_and_collects_only_keys(self):
        pages = [{"Items": [{"pk": "TELEMETRY#d1", "sk": "1#a"}], "LastEvaluatedKey": {"pk": "x"}},
                 {"Items": [{"pk": "TELEMETRY#d2", "sk": "2#b"}, {"pk": "TELEMETRY#d2", "sk": "3#c"}]}]

        class T:
            def __init__(self):
                self.calls = []

            def scan(self, **kw):
                self.calls.append(kw)
                return pages[len(self.calls) - 1]
        t, seen = T(), []
        rows = dvr.scan_matching(t, "0123456789abcdef", progress=seen.append)
        self.assertEqual(len(rows), 3)
        self.assertEqual(set(rows[0]), {"pk", "sk"})
        self.assertEqual(len(t.calls), 2)
        self.assertEqual(t.calls[1]["ExclusiveStartKey"], {"pk": "x"})
        self.assertEqual(len(seen), 2, "one progress line per page, so a long scan is not silent")

    def test_delete_rows_deletes_by_the_rows_own_key(self):
        deleted = []

        class Batch:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def delete_item(s, Key): deleted.append(Key)

        class T:
            def batch_writer(s): return Batch()
        n = dvr.delete_rows(T(), [{"pk": "TELEMETRY#d", "sk": "1#a"}, {"pk": "TELEMETRY#d", "sk": "2#b"}])
        self.assertEqual(n, 2)
        self.assertEqual(deleted, [{"pk": "TELEMETRY#d", "sk": "1#a"}, {"pk": "TELEMETRY#d", "sk": "2#b"}])

    def test_the_tool_defaults_to_a_dry_run(self):
        src = (ROOT / "tools" / "delete_verifier_reports.py").read_text()
        self.assertIn('"--apply", action="store_true"', src)
        self.assertRegex(src, r"if not args\.apply:\s+print\(\"DRY RUN")


if __name__ == "__main__":
    unittest.main()
