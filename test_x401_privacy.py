"""Privacy claims in policy section 14 (Credential Verification), executed.

The policy says: presentations and claims are not stored and not logged; the only thing kept
is a one-way hash of a single-use identifier, deleted after an hour. These tests run real
credentials carrying a distinctive claim value through accept and reject paths and check the
claims never reach a log record or the nonce store.
"""
import io
import json
import logging
import re
import unittest

import relayshield_verifier_nonces as nonces
import test_x401_rp as base
import x401_jose as jose
import x401_rp as rp
import x401_testkit as kit

SECRET_NAME = "Zebulon-Quux-Marmalade"


class _Conflict(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class FakeTable:
    """Keeps the conditional-put semantics, so a repeated key really reports a replay."""

    def __init__(self):
        self.items = []
        self._keys = set()

    def put_item(self, **kw):
        pk = kw["Item"]["pk"]
        if pk in self._keys:
            raise _Conflict()
        self._keys.add(pk)
        self.items.append(kw)


class Privacy(base.Case):
    def setUp(self):
        super().setUp()
        self.table = FakeTable()
        self.e.store = nonces.DynamoNonceStore(table=self.table)
        self.buf = io.StringIO()
        self.h = logging.StreamHandler(self.buf)
        self.h.setLevel(logging.DEBUG)
        root = logging.getLogger()
        self._lvl = root.level
        root.setLevel(logging.DEBUG)
        root.addHandler(self.h)

    def tearDown(self):
        root = logging.getLogger()
        root.removeHandler(self.h)
        root.setLevel(self._lvl)

    def run_flows(self):
        e = self.e
        vc = e.vc(always={"given_name": SECRET_NAME})
        ch = e.challenge()
        self.assertTrue(e.verify(e.result(ch, vc)))
        # a replay, a wrong route and a tampered artifact all take rejection paths
        res2 = e.result(e.challenge(), vc)
        res3 = e.result(e.challenge(), vc)
        res3["data"]["vp_token"]["id_card"][0] += "AAAA"
        for args, kw in (((e.result(ch, vc),), {}), ((res2,), {"route": "/other"}),
                         ((res3,), {}), (("not-base64!!",), {})):
            with self.assertRaises(rp.X401Error):
                e.verify(*args, **kw)

    def test_claim_values_never_reach_a_log(self):
        self.run_flows()
        logged = self.buf.getvalue()
        self.assertNotIn(SECRET_NAME, logged)
        self.assertNotIn("age_over_18", logged)

    def test_nonce_store_holds_only_a_hash_and_an_expiry(self):
        self.run_flows()
        self.assertTrue(self.table.items)
        for call in self.table.items:
            item = call["Item"]
            self.assertEqual(set(item), {"pk", "ttl"})
            self.assertRegex(item["pk"], r"^[0-9a-f]{64}$")
            self.assertNotIn(SECRET_NAME, json.dumps(call, default=str))

    def test_stored_expiry_is_at_most_an_hour_out(self):
        self.run_flows()
        for call in self.table.items:
            now = call["ExpressionAttributeValues"][":now"]
            self.assertLessEqual(call["Item"]["ttl"] - now, 3600)

    def test_modules_that_handle_credentials_do_not_log_arguments(self):
        for name in ("x401_rp.py", "x401_jose.py", "x401_net.py"):
            src = open(name, encoding="utf-8").read()
            code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
            self.assertIsNone(re.search(r"\bprint\(", code), name)
            for m in re.finditer(r"log(?:ger)?\.(?:debug|info|warning|error|exception)\(([^\n]*)", code):
                # only the policy-drop and JSON-parse messages are allowed, never a presented value
                self.assertRegex(m.group(1), r'^"x401 (policies|policy|issuer)', name)


if __name__ == "__main__":
    unittest.main()
