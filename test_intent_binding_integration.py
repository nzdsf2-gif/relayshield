#!/usr/bin/env python3
"""Integration tests for the intent-binding wiring in relayshield_api.py
(production candidate, main c8b2bf43 + intent binding).

The pure library is covered by test_intent_binding.py. This suite covers
the production glue: the KMS signer adapter (a fake KMS that performs
real Ed25519 over RAW messages, the exact contract the adapter uses),
the relayshield_intent_bindings DynamoDB registry (conditional-write
issue/consume, tenant isolation, TTL attribute), the corpus screeners
(a fake relayshield_tap_ti with controlled levels), the TAP admission
in lambda_handler (verifiers entitlement allowed/denied), the x402
pair, and the bind/settle lifecycle failure modes.

relayshield_api.py imports boto3 and several sibling modules at import
time, so the harness stubs them BEFORE the import (same pattern as the
scam-kit lineage integration suite): boto3's DynamoDB resource is an
in-memory fake that evaluates the ConditionExpressions the registry
uses and rejects native floats on write, like the real resource API.
The modules under test (relayshield_intent_binding, relayshield_passport,
relayshield_scamkit, relayshield_openapi_spec) are the real copies in
this directory.

Run:  python3 test_intent_binding_integration.py
"""

import base64
import copy
import json
import os
import re
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Fake DynamoDB (in-memory, production-faithful where it matters)
# ---------------------------------------------------------------------------

_TABLE_KEY_ATTRS = {
    "relayshield_api_keys": "api_key",
    "relayshield_intent_bindings": "binding_id",
}


class FakeClientError(Exception):
    def __init__(self, code, message=""):
        super().__init__(message or code)
        self.response = {"Error": {"Code": code, "Message": message or code}}


def _assert_dynamodb_types(obj, path="$"):
    """The real boto3 resource serializer rejects native floats."""
    if isinstance(obj, float):
        raise TypeError(f"Float types are not supported at {path}. "
                        "Use Decimal types instead.")
    if isinstance(obj, dict):
        for k, v in obj.items():
            _assert_dynamodb_types(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _assert_dynamodb_types(v, f"{path}[{i}]")


def _eval_condition(expr, item, values):
    """Evaluate the ConditionExpression shapes the registry glue uses:
    attribute_exists(name), attribute_not_exists(name), name = :value,
    combined with AND / OR / parentheses. Anything else is a loud
    failure: a fake that silently mis-evaluates a condition would
    hide real bugs in the consume path."""
    tokens = re.findall(
        r"attribute_not_exists|attribute_exists|AND|OR|\(|\)|=|:\w+|[A-Za-z_]\w*",
        expr)
    pos = [0]

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def parse_or():
        value = parse_and()
        while peek() == "OR":
            pos[0] += 1
            rhs = parse_and()
            value = value or rhs
        return value

    def parse_and():
        value = parse_atom()
        while peek() == "AND":
            pos[0] += 1
            rhs = parse_atom()
            value = value and rhs
        return value

    def parse_atom():
        tok = peek()
        if tok == "(":
            pos[0] += 1
            value = parse_or()
            assert peek() == ")", expr
            pos[0] += 1
            return value
        if tok in ("attribute_exists", "attribute_not_exists"):
            pos[0] += 1
            assert peek() == "("
            pos[0] += 1
            name = peek()
            pos[0] += 1
            assert peek() == ")"
            pos[0] += 1
            exists = item is not None and name in item
            return exists if tok == "attribute_exists" else not exists
        name = tok
        pos[0] += 1
        assert peek() == "=", expr
        pos[0] += 1
        vtok = peek()
        pos[0] += 1
        return item is not None and item.get(name) == (values or {}).get(vtok)

    result = parse_or()
    assert pos[0] == len(tokens), f"unparsed condition tail: {expr!r}"
    return result


def _split_assignments(set_expr: str) -> list:
    parts, depth, cur = [], 0, ""
    for ch in set_expr:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def _apply_update(item: dict, expression: str, values: dict, names: dict):
    assert expression.startswith("SET "), expression
    for part in _split_assignments(expression[4:]):
        target, rhs = part.split(" = ", 1)
        attr = names.get(target, target)
        m = re.fullmatch(r"(:\w+)", rhs)
        if m:
            item[attr] = values[m.group(1)]
            continue
        raise AssertionError(f"fake DynamoDB cannot evaluate update clause: {part!r}")


class FakeTable:
    def __init__(self, resource, name):
        self._resource = resource
        self.name = name

    @property
    def _items(self):
        return self._resource.store.setdefault(self.name, {})

    def _key_attr(self, Key=None, Item=None):
        attr = _TABLE_KEY_ATTRS.get(self.name)
        if attr:
            return attr
        return next(iter(Key or Item))

    def get_item(self, Key, **kwargs):
        item = self._items.get(Key[self._key_attr(Key=Key)])
        return {"Item": copy.deepcopy(item)} if item is not None else {}

    def put_item(self, Item, ConditionExpression=None, **kwargs):
        _assert_dynamodb_types(Item)
        key_attr = self._key_attr(Item=Item)
        existing = self._items.get(Item[key_attr])
        if ConditionExpression and not _eval_condition(
                ConditionExpression, existing, None):
            raise FakeClientError("ConditionalCheckFailedException")
        self._items[Item[key_attr]] = copy.deepcopy(Item)
        return {}

    def update_item(self, Key, UpdateExpression, ExpressionAttributeValues,
                    ExpressionAttributeNames=None, ConditionExpression=None,
                    **kwargs):
        _assert_dynamodb_types(ExpressionAttributeValues)
        key_attr = self._key_attr(Key=Key)
        item = self._items.get(Key[key_attr])
        if ConditionExpression and not _eval_condition(
                ConditionExpression, item, ExpressionAttributeValues):
            raise FakeClientError("ConditionalCheckFailedException")
        if item is None:
            item = {key_attr: Key[key_attr]}
            self._items[Key[key_attr]] = item
        _apply_update(item, UpdateExpression, ExpressionAttributeValues,
                      ExpressionAttributeNames or {})
        return {}


class FakeDynamoDBResource:
    def __init__(self):
        self.store = {}

    def Table(self, name):
        return FakeTable(self, name)

    def reset(self):
        self.store.clear()


FAKE_DDB = FakeDynamoDBResource()


class _KeyCondition:
    def __init__(self, name):
        self.name = name

    def eq(self, value):
        return ("eq", self.name, value)


class _AttrCondition:
    def __init__(self, name):
        self.name = name

    def eq(self, value):
        return ("eq", self.name, value)

    def is_in(self, values):
        return ("is_in", self.name, values)

    def gt(self, value):
        return ("gt", self.name, value)


class _DummyService:
    def __getattr__(self, name):
        return lambda *a, **k: {}


def _install_boto3_stub():
    boto3 = types.ModuleType("boto3")
    boto3.client = lambda *a, **k: _DummyService()

    def _resource(name, **kwargs):
        return FAKE_DDB if name == "dynamodb" else _DummyService()

    boto3.resource = _resource
    ddb = types.ModuleType("boto3.dynamodb")
    conditions = types.ModuleType("boto3.dynamodb.conditions")
    conditions.Key = _KeyCondition
    conditions.Attr = _AttrCondition
    ddb.conditions = conditions
    boto3.dynamodb = ddb
    sys.modules["boto3"] = boto3
    sys.modules["boto3.dynamodb"] = ddb
    sys.modules["boto3.dynamodb.conditions"] = conditions


def _stub_module(name, **attrs):
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    mod.__getattr__ = lambda attr: (lambda *a, **k: {})
    sys.modules[name] = mod
    return mod


_install_boto3_stub()
# Siblings relayshield_api imports at module level but the intent-binding
# handlers never call. ATTACK_CHAINS / normalise_malware_query are
# from-imported, so they must exist as real attributes.
_stub_module("relayshield_breach_monitor", ATTACK_CHAINS={})
_stub_module("relayshield_intel_labels", normalise_malware_query=lambda q: q)
_stub_module("relayshield_phone_reputation")
_stub_module("relayshield_corpus_provenance")
_stub_module("relayshield_vt_budget")
_stub_module("relayshield_sim_swap_consent")

import relayshield_api as api
import relayshield_openapi_spec as spec
import relayshield_intent_binding as ib
import relayshield_tap_ti as real_tap_ti


# ---------------------------------------------------------------------------
# Fake KMS: performs REAL Ed25519 over RAW messages (the adapter's exact
# contract), with the public key served as a KMS-shaped SPKI DER blob.
# ---------------------------------------------------------------------------

_KMS_SEED = bytes.fromhex("cd" * 32)
_KMS_ARN = "arn:aws:kms:us-east-1:239677749008:key/fake-bindings-key"


class FakeKMS:
    def __init__(self, seed=_KMS_SEED):
        self._seed = seed
        pub = ib._ed25519_publickey(seed)
        self._der = bytes.fromhex("302a300506032b6570032100") + pub

    def get_public_key(self, KeyId):
        return {"PublicKey": self._der, "KeyId": _KMS_ARN}

    def sign(self, KeyId, Message, MessageType, SigningAlgorithm):
        assert MessageType == "RAW", MessageType
        assert SigningAlgorithm == "ED25519_SHA_512", SigningAlgorithm
        assert len(Message) <= 4096
        return {"Signature": ib._ed25519_sign(self._seed, Message),
                "SigningAlgorithm": SigningAlgorithm, "KeyId": _KMS_ARN}


def _install_fake_tap_ti(screen_fn):
    mod = types.ModuleType("relayshield_tap_ti")
    mod.screen = screen_fn
    mod.normalise_domain = real_tap_ti.normalise_domain
    sys.modules["relayshield_tap_ti"] = mod


def _clean_screen(wallet=None, domain=None):
    return {"level": "unknown", "reasons": []}


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

WALLET = "0x1234567890abcdef1234567890abcdef12345678"
OTHER_WALLET = "0x9999999999999999999999999999999999999999"

ARTIFACTS = [
    {"artifact_id": "invoice", "kind": "invoice",
     "descriptor": {"number": "INV-100", "total": "25.00",
                    "currency": "USD", "payee": "Seller Example LLC"}},
    {"artifact_id": "cart", "kind": "cart",
     "descriptor": {"items": [], "total": "25.00"}},
    {"artifact_id": "invoice-img", "kind": "invoice_image",
     "descriptor": {"image_ref": "https://files.example/invoice.png",
                    "image_sha256": "0" * 64}},
]

BIND_PAYG = {
    "payer": WALLET,
    "counterparty": "seller.example",
    "amount": "25.00",
    "currency": "USD",
    "rail": "x402",
    "artifacts": ARTIFACTS,
}

NOW = [1_760_000_000]


def _data(resp, status=200):
    assert resp["statusCode"] == status, resp
    return json.loads(resp["body"])["data"]


def _executed(**overrides):
    executed = {
        "payer": WALLET,
        "counterparty": "seller.example",
        "amount": "25.00",
        "currency": "USD",
        "artifacts": ARTIFACTS,
    }
    executed.update(overrides)
    return executed


class BindingTestBase(unittest.TestCase):
    def setUp(self):
        FAKE_DDB.reset()
        _install_fake_tap_ti(_clean_screen)
        os.environ[api.INTENT_BINDING_KMS_KEY_ID_ENV] = \
            "alias/relayshield-intent-binding-test"
        api._BINDING_SIGNER = api._KmsBindingSigner(
            key_id="alias/relayshield-intent-binding-test", client=FakeKMS())
        api._BINDING_CLOCK = lambda: NOW[0]
        api._BINDING_OCR_EXTRACTOR = None

    def tearDown(self):
        api._BINDING_SIGNER = None
        api._BINDING_CLOCK = None
        api._BINDING_OCR_EXTRACTOR = None
        os.environ.pop(api.INTENT_BINDING_KMS_KEY_ID_ENV, None)
        sys.modules["relayshield_tap_ti"] = real_tap_ti

    def bind_payg(self, payload=None):
        resp = api.handle_payg_intent_bind(dict(payload or BIND_PAYG))
        return resp

    def bind_payg_ok(self, payload=None):
        resp = self.bind_payg(payload)
        return _data(resp, 201)["binding"]


# ---------------------------------------------------------------------------
# Wiring: registrations, placeholder pricing, spec
# ---------------------------------------------------------------------------

class TestWiring(BindingTestBase):
    def test_registrations(self):
        self.assertIn("/v1/payg/intent-bind", api.X402_V2_ENABLED_PATHS)
        self.assertIn("/v1/payg/intent-settle-check", api.X402_V2_ENABLED_PATHS)
        # Approved price constants (names kept from staging), referenced
        # (not literal) by the tables.
        self.assertEqual(api.PAYG_PRICE_UNITS["/v1/payg/intent-bind"],
                         api.INTENT_BIND_PRICE_UNITS_PLACEHOLDER)
        self.assertEqual(api.PAYG_PRICE_UNITS["/v1/payg/intent-settle-check"],
                         api.INTENT_SETTLE_CHECK_PRICE_UNITS_PLACEHOLDER)
        self.assertEqual(api.METERED_CREDIT_COSTS["/v1/metered/intent-bind"],
                         api.INTENT_BIND_CREDIT_COST_PLACEHOLDER)
        self.assertEqual(
            api.METERED_CREDIT_COSTS["/v1/metered/intent-settle-check"],
            api.INTENT_SETTLE_CHECK_CREDIT_COST_PLACEHOLDER)
        self.assertEqual(api.STRIPE_METER_EVENTS["/v1/metered/intent-bind"],
                         "relayshield_intent_bind_calls")
        self.assertEqual(
            api.STRIPE_METER_EVENTS["/v1/metered/intent-settle-check"],
            "relayshield_intent_settle_check_calls")
        self.assertEqual(api.INTENT_BINDINGS_TABLE, "relayshield_intent_bindings")
        # Placeholders are anchored to the scamkit-match price.
        self.assertEqual(api.INTENT_BIND_PRICE_UNITS_PLACEHOLDER,
                         api.PAYG_PRICE_UNITS["/v1/payg/scamkit-match"])

    def test_policy_loads_from_packaged_yaml(self):
        policy = api._binding_policy()
        self.assertEqual(policy.ttl_seconds, 900)
        self.assertEqual(policy.amount_tolerance_minor, 0)
        self.assertFalse(policy.image_ocr_hard_block)
        self.assertEqual(policy.step_up_satisfied_by, ("human_approval",))

    def test_spec_builds_with_all_four_endpoints(self):
        doc = spec.build_spec("https://api.relayshield.net",
                              dict(api.PAYG_PRICE_UNITS))
        for path in ("/v1/tap/intent-bind", "/v1/tap/settle-check",
                     "/v1/payg/intent-bind", "/v1/payg/intent-settle-check"):
            self.assertIn(path, doc["paths"], path)
        payg = spec.PAYG_ENDPOINTS["/v1/payg/intent-bind"]
        self.assertEqual(payg["x402_version"], 2)
        self.assertEqual(payg["price_units"],
                         api.INTENT_BIND_PRICE_UNITS_PLACEHOLDER)


# ---------------------------------------------------------------------------
# TAP pair: entitlement admission through lambda_handler
# ---------------------------------------------------------------------------

ENTITLED_KEY = "rs_live_entitled0000000000000001"
PLAIN_KEY = "rs_live_plain00000000000000000001"
SECOND_ENTITLED_KEY = "rs_live_entitled0000000000000002"


def _seed_key(key, **fields):
    item = {"api_key": key, "active": True}
    item.update(fields)
    FAKE_DDB.store.setdefault(api.API_KEYS_TABLE, {})[key] = item


def _tap_event(path, key, payload):
    headers = {"X-RS-API-KEY": key} if key else {}
    return {"path": path, "httpMethod": "POST", "headers": headers,
            "body": json.dumps(payload),
            "requestContext": {"identity": {"sourceIp": "127.0.0.1"}}}


TAP_BIND = {
    "payer": "agent-4471",
    "counterparty": "seller.example",
    "amount": "25.00",
    "currency": "USD",
    "tap_intent_ref": "tap_intent_9f2c",
    "artifacts": ARTIFACTS,
}


class TestTapEntitlement(BindingTestBase):
    def setUp(self):
        super().setUp()
        _seed_key(ENTITLED_KEY, verifiers_access=True)
        _seed_key(SECOND_ENTITLED_KEY, verifiers_access=True)
        _seed_key(PLAIN_KEY)

    def test_no_key_is_401(self):
        resp = api.lambda_handler(_tap_event("/v1/tap/intent-bind", None, TAP_BIND), None)
        self.assertEqual(resp["statusCode"], 401, resp)

    def test_key_without_verifiers_entitlement_is_403(self):
        resp = api.lambda_handler(
            _tap_event("/v1/tap/intent-bind", PLAIN_KEY, TAP_BIND), None)
        self.assertEqual(resp["statusCode"], 403, resp)
        body = json.loads(resp["body"])
        self.assertIn("verifiers entitlement", body["error"])

    def test_entitled_key_binds_and_settles(self):
        resp = api.lambda_handler(
            _tap_event("/v1/tap/intent-bind", ENTITLED_KEY, TAP_BIND), None)
        binding = _data(resp, 201)["binding"]
        self.assertEqual(binding["record"]["id_policy"], "tap")
        self.assertEqual(binding["record"]["tap_intent_ref"], "tap_intent_9f2c")
        bid = binding["record"]["binding_id"]

        executed = {"payer": "agent-4471", "counterparty": "seller.example",
                    "amount": "25.00", "currency": "USD", "artifacts": ARTIFACTS}
        resp = api.lambda_handler(
            _tap_event("/v1/tap/settle-check", ENTITLED_KEY,
                       {"binding_id": bid, "executed": executed}), None)
        data = _data(resp)
        self.assertEqual(data["decision"], "allow", data)
        self.assertEqual(data["reason_codes"], ["OK"])

    def test_other_tenants_binding_is_not_found(self):
        resp = api.lambda_handler(
            _tap_event("/v1/tap/intent-bind", ENTITLED_KEY, TAP_BIND), None)
        bid = _data(resp, 201)["binding"]["record"]["binding_id"]
        executed = {"payer": "agent-4471", "counterparty": "seller.example",
                    "amount": "25.00", "currency": "USD", "artifacts": ARTIFACTS}
        resp = api.lambda_handler(
            _tap_event("/v1/tap/settle-check", SECOND_ENTITLED_KEY,
                       {"binding_id": bid, "executed": executed}), None)
        data = _data(resp)
        self.assertEqual(data["decision"], "block")
        self.assertEqual(data["reason_codes"], ["BINDING_NOT_FOUND"])


# ---------------------------------------------------------------------------
# x402 pair + lifecycle
# ---------------------------------------------------------------------------

class TestPaygLifecycle(BindingTestBase):
    def test_bind_then_settle_happy_path(self):
        binding = self.bind_payg_ok()
        record = binding["record"]
        self.assertEqual(record["id_policy"], "x402")
        self.assertEqual(record["amount_minor"], 2500)
        self.assertTrue(ib.Binding.from_dict(binding).signature_valid())
        # The image bound by reference alone records no verdict.
        image_verdict = record["verdicts"]["invoice_images"]["invoice-img"]
        self.assertEqual(image_verdict["status"], "not_evaluated")

        resp = api.handle_payg_intent_settle_check(
            {"binding_id": record["binding_id"], "executed": _executed()})
        data = _data(resp)
        self.assertEqual(data["decision"], "allow", data)
        self.assertEqual(data["reason_codes"], ["OK"])
        self.assertEqual(data["step_up"]["required"], False)

    def test_settle_twice_is_already_consumed(self):
        binding = self.bind_payg_ok()
        bid = binding["record"]["binding_id"]
        first = _data(api.handle_payg_intent_settle_check(
            {"binding_id": bid, "executed": _executed()}))
        self.assertEqual(first["decision"], "allow")
        second = _data(api.handle_payg_intent_settle_check(
            {"binding_id": bid, "executed": _executed()}))
        self.assertEqual(second["decision"], "block")
        self.assertEqual(second["reason_codes"], ["BINDING_ALREADY_CONSUMED"])

    def test_expired_binding_is_refused(self):
        binding = self.bind_payg_ok()
        bid = binding["record"]["binding_id"]
        NOW[0] += 901  # policy TTL is 900s
        data = _data(api.handle_payg_intent_settle_check(
            {"binding_id": bid, "executed": _executed()}))
        self.assertEqual(data["decision"], "block")
        self.assertEqual(data["reason_codes"], ["BINDING_EXPIRED"])

    def test_amount_out_of_tolerance_is_refused_and_not_consumed(self):
        binding = self.bind_payg_ok()
        bid = binding["record"]["binding_id"]
        data = _data(api.handle_payg_intent_settle_check(
            {"binding_id": bid, "executed": _executed(amount="25.01")}))
        self.assertEqual(data["decision"], "block")
        self.assertEqual(data["reason_codes"], ["AMOUNT_MISMATCH"])
        # A block does not consume: the correct amount still settles.
        data = _data(api.handle_payg_intent_settle_check(
            {"binding_id": bid, "executed": _executed()}))
        self.assertEqual(data["decision"], "allow")

    def test_other_payers_binding_is_not_found(self):
        binding = self.bind_payg_ok()
        bid = binding["record"]["binding_id"]
        data = _data(api.handle_payg_intent_settle_check(
            {"binding_id": bid, "executed": _executed(payer=OTHER_WALLET)}))
        self.assertEqual(data["decision"], "block")
        self.assertEqual(data["reason_codes"], ["BINDING_NOT_FOUND"])

    def test_flagged_counterparty_refuses_the_binding(self):
        _install_fake_tap_ti(lambda wallet=None, domain=None: {
            "level": "high",
            "reasons": ["domain appears in the IOC corpus"]})
        resp = self.bind_payg()
        self.assertEqual(resp["statusCode"], 422, resp)
        body = json.loads(resp["body"])
        self.assertEqual(body["error"], "binding_refused")
        self.assertIn("COUNTERPARTY_FLAGGED", body["reason_codes"])
        self.assertIn("counterparty", body["verdicts"])

    def test_unconfigured_signer_is_503(self):
        api._BINDING_SIGNER = None
        os.environ.pop(api.INTENT_BINDING_KMS_KEY_ID_ENV, None)
        resp = self.bind_payg()
        self.assertEqual(resp["statusCode"], 503, resp)

    def test_metered_twins(self):
        key_record = {"api_key": ENTITLED_KEY, "active": True}
        resp = api.handle_metered_intent_bind(dict(BIND_PAYG), key_record)
        binding = _data(resp, 201)["binding"]
        self.assertEqual(binding["record"]["id_policy"], "x402")
        resp = api.handle_metered_intent_settle_check(
            {"binding_id": binding["record"]["binding_id"],
             "executed": _executed()}, key_record)
        self.assertEqual(_data(resp)["decision"], "allow")


# ---------------------------------------------------------------------------
# Registry semantics, direct against the store
# ---------------------------------------------------------------------------

class TestRegistryStore(BindingTestBase):
    def test_item_shape_and_consume_conditional_write(self):
        binding = self.bind_payg_ok()
        bid = binding["record"]["binding_id"]
        item = FAKE_DDB.store[api.INTENT_BINDINGS_TABLE][bid]
        self.assertEqual(item["tenant_id"],
                         ib.canonical_identifier(WALLET))
        self.assertEqual(item["rail"], "x402")
        self.assertEqual(item["consumed"], False)
        self.assertEqual(item["expires_at"], binding["record"]["expires_at"])
        self.assertEqual(json.loads(item["record"]), binding["record"])
        self.assertEqual(item["signature"], binding["signature"])

        store = api._DynamoBindingStore(
            tenant_id=ib.canonical_identifier(WALLET), rail="x402")
        self.assertTrue(store.consume(bid))
        self.assertTrue(store.is_consumed(bid))
        # The conditional write refuses the second consume.
        self.assertFalse(store.consume(bid))

    def test_cross_tenant_get_is_none(self):
        binding = self.bind_payg_ok()
        bid = binding["record"]["binding_id"]
        stranger = api._DynamoBindingStore(tenant_id="someone-else", rail="x402")
        self.assertIsNone(stranger.get(bid))


# ---------------------------------------------------------------------------
# Advisory OCR: flag + step-up, not a refusal
# ---------------------------------------------------------------------------

class TestOcrAdvisory(BindingTestBase):
    def test_advisory_ocr_flag_steps_up_instead_of_refusing(self):
        api._BINDING_OCR_EXTRACTOR = ib.FunctionTextExtractor(
            lambda image_bytes: (
                "ACME Industrial Supplies\n"
                "Invoice INV-100\n"
                "Total due: $2,500.00\n"
                f"Pay to wallet {OTHER_WALLET}\n"))
        image_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\nfake-image").decode()
        artifacts = [
            ARTIFACTS[0],
            {"artifact_id": "invoice-img", "kind": "invoice_image",
             "descriptor": {"image_ref": "https://files.example/invoice.png",
                            "image_sha256": "0" * 64},
             "content_b64": image_b64},
        ]
        payload = dict(BIND_PAYG, artifacts=artifacts)
        resp = self.bind_payg(payload)
        binding = _data(resp, 201)["binding"]  # issued, NOT refused
        record = binding["record"]
        self.assertTrue(record["step_up"]["required"], record["step_up"])
        trigger_types = [t["type"] for t in record["step_up"]["triggers"]]
        self.assertIn("invoice_image_advisory", trigger_types)
        verdict = record["verdicts"]["invoice_images"]["invoice-img"]
        self.assertEqual(verdict["status"], "flagged")
        self.assertTrue(verdict["advisory"])

        # Decided 2026-10-24: settle-check validates step-up
        # attestations. Without evidence the settlement blocks (and
        # does not consume); with a valid attestation for the
        # required method it allows. The response carries the
        # step-up requirement baked into the record either way.
        executed = _executed(artifacts=artifacts)
        data = _data(api.handle_payg_intent_settle_check(
            {"binding_id": record["binding_id"], "executed": executed}))
        self.assertEqual(data["decision"], "block", data)
        self.assertIn("STEP_UP_ATTESTATION_MISSING",
                      data["reason_codes"])
        self.assertTrue(data["step_up"]["required"])
        attestation = {
            "method": record["step_up"]["satisfied_by"][0],
            "evidence_ref": "https://approvals.example/records/appr-1001",
            "attested_at": record["issued_at"],
            "attestor": "approver-7",
        }
        data = _data(api.handle_payg_intent_settle_check(
            {"binding_id": record["binding_id"], "executed": executed,
             "attestations": [attestation]}))
        self.assertEqual(data["decision"], "allow", data)
        self.assertTrue(data["step_up"]["required"])

    def test_unavailable_extractor_reports_not_evaluated(self):
        # Explicitly no engine: the unavailable extractor reports the
        # image not_evaluated and the binding still issues (policy
        # posture). The Lambda default is the MSGSCAN Rekognition
        # extractor since 2026-10-24, so the not_evaluated path is
        # pinned here via the explicit fallback, not via the default.
        api._BINDING_OCR_EXTRACTOR = api._UnavailableTextExtractor()
        image_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\nfake-image").decode()
        artifacts = [
            ARTIFACTS[0],
            {"artifact_id": "invoice-img", "kind": "invoice_image",
             "descriptor": {"image_ref": "https://files.example/invoice.png",
                            "image_sha256": "0" * 64},
             "content_b64": image_b64},
        ]
        binding = self.bind_payg_ok(dict(BIND_PAYG, artifacts=artifacts))
        verdict = binding["record"]["verdicts"]["invoice_images"]["invoice-img"]
        self.assertEqual(verdict["status"], "not_evaluated")
        self.assertFalse(binding["record"]["step_up"]["required"])


# ---------------------------------------------------------------------------
# Step-up attestation validation (decided 2026-10-24)
# ---------------------------------------------------------------------------

class TestStepUpAttestationValidation(BindingTestBase):
    """Pure-function validation: presence, TTL window, evidence_ref shape."""

    STEP_UP = {"required": True, "triggers": [],
               "satisfied_by": ["human_approval"]}
    ISSUED = NOW[0]
    EXPIRES = NOW[0] + 900

    def _att(self, **overrides):
        att = {"method": "human_approval",
               "evidence_ref": "https://approvals.example/records/appr-1",
               "attested_at": self.ISSUED,
               "attestor": "approver-7"}
        att.update(overrides)
        return att

    def test_not_required_ignores_attestations(self):
        codes, _ = ib.validate_step_up_attestations(
            {"required": False}, None, self.ISSUED, self.EXPIRES)
        self.assertEqual(codes, [])
        codes, _ = ib.validate_step_up_attestations(
            {"required": False}, "garbage", self.ISSUED, self.EXPIRES)
        self.assertEqual(codes, [])

    def test_valid_attestation_passes(self):
        codes, _ = ib.validate_step_up_attestations(
            self.STEP_UP, [self._att()], self.ISSUED, self.EXPIRES)
        self.assertEqual(codes, [])

    def test_attestor_not_validated(self):
        # v1 validates presence, TTL, and evidence_ref shape only.
        att = self._att()
        del att["attestor"]
        codes, _ = ib.validate_step_up_attestations(
            self.STEP_UP, [att], self.ISSUED, self.EXPIRES)
        self.assertEqual(codes, [])

    def test_missing_attestation_blocks(self):
        codes, _ = ib.validate_step_up_attestations(
            self.STEP_UP, [], self.ISSUED, self.EXPIRES)
        self.assertIn("STEP_UP_ATTESTATION_MISSING", codes)
        codes, _ = ib.validate_step_up_attestations(
            self.STEP_UP, None, self.ISSUED, self.EXPIRES)
        self.assertIn("STEP_UP_ATTESTATION_MISSING", codes)

    def test_wrong_method_leaves_required_missing(self):
        # A well-formed attestation for a non-required method is
        # tolerated as extra evidence; the required method is still
        # missing, but nothing is malformed.
        codes, _ = ib.validate_step_up_attestations(
            self.STEP_UP, [self._att(method="policy_rule")],
            self.ISSUED, self.EXPIRES)
        self.assertIn("STEP_UP_ATTESTATION_MISSING", codes)
        self.assertNotIn("STEP_UP_ATTESTATION_INVALID", codes)

    def test_second_required_method_missing(self):
        step_up = {"required": True, "triggers": [],
                   "satisfied_by": ["human_approval",
                                    "second_agent_approval"]}
        codes, _ = ib.validate_step_up_attestations(
            step_up, [self._att()], self.ISSUED, self.EXPIRES)
        self.assertIn("STEP_UP_ATTESTATION_MISSING", codes)

    def test_required_with_no_methods_is_unsatisfiable(self):
        codes, _ = ib.validate_step_up_attestations(
            {"required": True, "satisfied_by": []}, [self._att()],
            self.ISSUED, self.EXPIRES)
        self.assertIn("STEP_UP_ATTESTATION_MISSING", codes)

    def test_unknown_method_invalid(self):
        codes, _ = ib.validate_step_up_attestations(
            self.STEP_UP, [self._att(method="sms_otp")],
            self.ISSUED, self.EXPIRES)
        self.assertIn("STEP_UP_ATTESTATION_INVALID", codes)

    def test_malformed_evidence_ref_invalid(self):
        for bad in ("", "short", "has space in it", 12345):
            codes, _ = ib.validate_step_up_attestations(
                self.STEP_UP, [self._att(evidence_ref=bad)],
                self.ISSUED, self.EXPIRES)
            self.assertIn("STEP_UP_ATTESTATION_INVALID", codes, bad)

    def test_attested_at_outside_ttl_invalid(self):
        for bad_ts in (self.ISSUED - 1, self.EXPIRES + 1, "soon", True):
            codes, _ = ib.validate_step_up_attestations(
                self.STEP_UP, [self._att(attested_at=bad_ts)],
                self.ISSUED, self.EXPIRES)
            self.assertIn("STEP_UP_ATTESTATION_INVALID", codes, bad_ts)

    def test_attested_at_window_edges_pass(self):
        for edge in (self.ISSUED, self.EXPIRES):
            codes, _ = ib.validate_step_up_attestations(
                self.STEP_UP, [self._att(attested_at=edge)],
                self.ISSUED, self.EXPIRES)
            self.assertEqual(codes, [], edge)

    def test_non_list_attestations_invalid(self):
        codes, _ = ib.validate_step_up_attestations(
            self.STEP_UP, {"method": "human_approval"},
            self.ISSUED, self.EXPIRES)
        self.assertIn("STEP_UP_ATTESTATION_INVALID", codes)


class TestStepUpAttestationGlue(BindingTestBase):
    """End to end through the PAYG settle-check handler: blocks never
    consume, so a corrected settle after a block still allows."""

    def _bind_required(self):
        api._BINDING_OCR_EXTRACTOR = ib.FunctionTextExtractor(
            lambda image_bytes: (
                "ACME Industrial Supplies\n"
                "Invoice INV-100\n"
                "Total due: $2,500.00\n"
                f"Pay to wallet {OTHER_WALLET}\n"))
        image_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\nfake-image").decode()
        artifacts = [
            ARTIFACTS[0],
            {"artifact_id": "invoice-img", "kind": "invoice_image",
             "descriptor": {"image_ref": "https://files.example/invoice.png",
                            "image_sha256": "0" * 64},
             "content_b64": image_b64},
        ]
        binding = self.bind_payg_ok(dict(BIND_PAYG, artifacts=artifacts))
        self.assertTrue(binding["record"]["step_up"]["required"])
        return binding, artifacts

    def _settle(self, binding, artifacts, attestations=None):
        body = {"binding_id": binding["record"]["binding_id"],
                "executed": _executed(artifacts=artifacts)}
        if attestations is not None:
            body["attestations"] = attestations
        return _data(api.handle_payg_intent_settle_check(body))

    def _valid_attestation(self, binding):
        return {
            "method": binding["record"]["step_up"]["satisfied_by"][0],
            "evidence_ref": "https://approvals.example/records/appr-1001",
            "attested_at": binding["record"]["issued_at"],
            "attestor": "approver-7",
        }

    def test_block_on_missing_then_allow(self):
        binding, artifacts = self._bind_required()
        data = self._settle(binding, artifacts)
        self.assertEqual(data["decision"], "block", data)
        self.assertIn("STEP_UP_ATTESTATION_MISSING",
                      data["reason_codes"])
        data = self._settle(binding, artifacts,
                            [self._valid_attestation(binding)])
        self.assertEqual(data["decision"], "allow", data)

    def test_block_on_stale_attestation_then_allow(self):
        binding, artifacts = self._bind_required()
        stale = self._valid_attestation(binding)
        stale["attested_at"] = binding["record"]["issued_at"] - 1
        data = self._settle(binding, artifacts, [stale])
        self.assertEqual(data["decision"], "block", data)
        self.assertIn("STEP_UP_ATTESTATION_INVALID",
                      data["reason_codes"])
        data = self._settle(binding, artifacts,
                            [self._valid_attestation(binding)])
        self.assertEqual(data["decision"], "allow", data)

    def test_block_on_malformed_evidence_then_allow(self):
        binding, artifacts = self._bind_required()
        bad = self._valid_attestation(binding)
        bad["evidence_ref"] = "x"
        data = self._settle(binding, artifacts, [bad])
        self.assertEqual(data["decision"], "block", data)
        self.assertIn("STEP_UP_ATTESTATION_INVALID",
                      data["reason_codes"])
        data = self._settle(binding, artifacts,
                            [self._valid_attestation(binding)])
        self.assertEqual(data["decision"], "allow", data)

    def test_non_list_attestations_block(self):
        binding, artifacts = self._bind_required()
        data = self._settle(binding, artifacts, "not-a-list")
        self.assertEqual(data["decision"], "block", data)
        self.assertIn("STEP_UP_ATTESTATION_INVALID",
                      data["reason_codes"])


# ---------------------------------------------------------------------------
# MSGSCAN Rekognition extractor (decided 2026-10-24)
# ---------------------------------------------------------------------------

class _StubRekognition:
    def __init__(self, detections=None, error=None):
        self.detections = detections
        self.error = error
        self.calls = []

    def detect_text(self, Image):
        self.calls.append(Image)
        if self.error is not None:
            raise self.error
        return {"TextDetections": self.detections or []}


class TestRekognitionExtractor(BindingTestBase):
    def test_joins_line_detections_only(self):
        extractor = api._RekognitionTextExtractor(
            client=_StubRekognition([
                {"Type": "WORD", "DetectedText": "Total"},
                {"Type": "LINE", "DetectedText": "Total due: $25.00"},
                {"Type": "LINE", "DetectedText": "Pay to seller.example"},
            ]))
        self.assertEqual(extractor.extract_text(b"fake-image-bytes"),
                         "Total due: $25.00 Pay to seller.example")

    def test_empty_detections_return_empty_string(self):
        extractor = api._RekognitionTextExtractor(
            client=_StubRekognition([]))
        self.assertEqual(extractor.extract_text(b"fake-image-bytes"), "")

    def test_engine_error_is_unavailable(self):
        extractor = api._RekognitionTextExtractor(
            client=_StubRekognition(error=RuntimeError("boom")))
        with self.assertRaises(ib.OCRUnavailableError):
            extractor.extract_text(b"fake-image-bytes")

    def test_oversize_image_is_unavailable(self):
        extractor = api._RekognitionTextExtractor(
            client=_StubRekognition([]))
        with self.assertRaises(ib.OCRUnavailableError):
            extractor.extract_text(b" " * (5 * 1024 * 1024 + 1))

    def test_no_bytes_is_unavailable(self):
        extractor = api._RekognitionTextExtractor(
            client=_StubRekognition([]))
        with self.assertRaises(ib.OCRUnavailableError):
            extractor.extract_text(b"")

    def test_glue_evaluates_image_with_stubbed_rekognition(self):
        api._BINDING_OCR_EXTRACTOR = api._RekognitionTextExtractor(
            client=_StubRekognition([
                {"Type": "LINE", "DetectedText": "Total due: $25.00"},
                {"Type": "LINE", "DetectedText": "Pay to seller.example"},
            ]))
        image_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\nfake-image").decode()
        artifacts = [
            ARTIFACTS[0],
            {"artifact_id": "invoice-img", "kind": "invoice_image",
             "descriptor": {"image_ref": "https://files.example/invoice.png",
                            "image_sha256": "0" * 64},
             "content_b64": image_b64},
        ]
        binding = self.bind_payg_ok(dict(BIND_PAYG, artifacts=artifacts))
        verdict = binding["record"]["verdicts"]["invoice_images"]["invoice-img"]
        self.assertEqual(verdict["status"], "no_flags_found")
        self.assertFalse(binding["record"]["step_up"]["required"])


if __name__ == "__main__":
    unittest.main()
