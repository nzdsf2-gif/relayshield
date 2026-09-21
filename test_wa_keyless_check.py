#!/usr/bin/env python3
"""The WhatsApp front door answers a stranger's first message.

WHY THESE EXIST. Until 2026-09-21 the `if not user` branch could only describe
the product, so a wa.me link or a directory listing landed somebody in a chat
that could not answer their question. /v1/link-check and /v1/wallet-risk are
keyless by design, so there was never a commercial reason to refuse -- it was
simply not wired.

EXECUTED, NOT GREPPED. Every case below runs keyless_check() with urlopen
replaced, because the defects worth catching here are runtime ones: a verdict
that says "safe", an exception reaching a stranger's first message, and a 429
rendering as a clean result. Reading the function shows none of those.

    python3 test_wa_keyless_check.py
"""
import ast
import io
import json
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "relayshield_whatsapp_webhook.py"


def _load():
    """Import the module without its AWS side effects."""
    import importlib.util
    import sys
    import types
    # boto3 is not installed in CI or in this container, and the module does
    # `from boto3.dynamodb.conditions import Attr, Key` at import time, so a
    # flat stub is not enough: it has to be a PACKAGE with submodules.
    boto3 = types.ModuleType("boto3")
    boto3.__path__ = []
    boto3.client = lambda *a, **k: mock.MagicMock()
    boto3.resource = lambda *a, **k: mock.MagicMock()
    ddb = types.ModuleType("boto3.dynamodb")
    ddb.__path__ = []
    cond = types.ModuleType("boto3.dynamodb.conditions")
    cond.Attr = cond.Key = mock.MagicMock()
    exc = types.ModuleType("botocore.exceptions")
    exc.ClientError = type("ClientError", (Exception,), {})
    botocore = types.ModuleType("botocore")
    botocore.__path__ = []
    for name, mod in (("boto3", boto3), ("boto3.dynamodb", ddb),
                      ("boto3.dynamodb.conditions", cond),
                      ("botocore", botocore), ("botocore.exceptions", exc)):
        sys.modules.setdefault(name, mod)
    spec = importlib.util.spec_from_file_location("wa_webhook", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode()
    def read(self):
        return self._b
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


class KeylessCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load()

    def _run(self, text, payload=None, exc=None):
        def fake(req, timeout=None):
            self.sent = json.loads(req.data.decode())
            self.url = req.full_url
            if exc:
                raise exc
            return _Resp(payload)
        with mock.patch.object(self.mod.urllib.request, "urlopen", fake):
            return self.mod.keyless_check(text)

    # --- routing -----------------------------------------------------------

    def test_a_url_goes_to_link_check(self):
        self._run("https://example.com/x", {"ok": True, "data": {"level": "low"}})
        self.assertTrue(self.url.endswith("/v1/link-check"))
        self.assertEqual(self.sent["url"], "https://example.com/x")

    def test_a_bare_domain_is_given_a_scheme(self):
        # The API takes a URL. A bare domain is what a person actually types.
        self._run("example.com", {"ok": True, "data": {"level": "low"}})
        self.assertEqual(self.sent["url"], "https://example.com")

    def test_an_evm_address_goes_to_wallet_risk(self):
        self._run("0x" + "a" * 40, {"ok": True, "data": {"risk_level": "clean"}})
        self.assertTrue(self.url.endswith("/v1/wallet-risk"))

    def test_a_ton_friendly_address_goes_to_wallet_risk(self):
        self._run("EQ" + "A" * 46, {"ok": True, "data": {"risk_level": "clean"}})
        self.assertTrue(self.url.endswith("/v1/wallet-risk"))

    def test_ronin_prefix_is_stripped_rather_than_rejected(self):
        # Every wallet regex rejects the prefix, and the address behind it is
        # ordinary EVM. Stripping turns a refused message into a checked one.
        self._run("ronin:0x" + "b" * 40, {"ok": True, "data": {"risk_level": "clean"}})
        self.assertTrue(self.url.endswith("/v1/wallet-risk"))
        self.assertEqual(self.sent["address"], "0x" + "b" * 40)

    def test_ordinary_prose_is_not_checkable(self):
        self.assertEqual(self.mod.keyless_check("hello is this thing on"), "")
        self.assertEqual(self.mod.keyless_check(""), "")
        self.assertEqual(self.mod.keyless_check("x" * 600), "")

    def test_every_call_carries_the_source(self):
        # An arrival that is not attributed is indistinguishable from organic
        # traffic forever, which is FD-8's shape.
        self._run("https://example.com", {"ok": True, "data": {"level": "low"}})
        self.assertEqual(self.sent["source"], "wa-frontdoor")

    # --- the two rules that are not negotiable -----------------------------

    def test_it_never_says_safe(self):
        for level in ("critical", "high", "medium", "low", "unknown", "clean"):
            out = self._run("https://example.com",
                            {"ok": True, "data": {"level": level}})
            self.assertNotIn("safe.", out.lower().replace("proof of safety.", ""))
            self.assertNotIn("is safe", out.lower())

    def test_a_clean_answer_carries_the_caveat(self):
        out = self._run("https://example.com", {"ok": True, "data": {"level": "low"}})
        self.assertIn("not proof of safety", out.lower())

    def test_it_never_raises(self):
        for exc in (urllib.error.URLError("down"),
                    TimeoutError("slow"),
                    ValueError("nonsense")):
            out = self._run("https://example.com", exc=exc)
            self.assertIn("unchecked", out.lower())
            self.assertNotIn("no known red flags", out.lower())

    def test_the_daily_cap_is_named_separately_from_an_outage(self):
        # A 429 is a real answer, not an outage, and the two have different
        # advice. Folding them together is how a capped check reads as a
        # working one.
        cap = self._run("https://example.com",
                        exc=urllib.error.HTTPError("u", 429, "Too Many", {}, None))
        out = self._run("https://example.com",
                        exc=urllib.error.HTTPError("u", 500, "Boom", {}, None))
        self.assertIn("busy", cap.lower())
        self.assertNotIn("busy", out.lower())
        for text in (cap, out):
            self.assertIn("unchecked", text.lower())

    def test_a_malformed_body_is_unchecked_not_clean(self):
        for payload in ({"ok": False}, {"nope": 1}, []):
            out = self._run("https://example.com", payload)
            self.assertIn("unchecked", out.lower())

    def test_a_high_verdict_says_do_not_proceed(self):
        out = self._run("https://example.com",
                        {"ok": True, "data": {"level": "high", "reasons": ["known_phish"]}})
        self.assertIn("do not proceed", out.lower())
        self.assertIn("known phish", out.lower())

    # --- the call site, which behaviour tests cannot see -------------------

    def test_the_stranger_branch_actually_calls_it(self):
        # A helper nothing calls is decoration. This is the only assertion here
        # that catches the branch being reverted to a description-only reply.
        src = io.open(SRC, encoding="utf-8").read()
        tree = ast.parse(src)
        handler = next(n for n in ast.walk(tree)
                       if isinstance(n, ast.FunctionDef) and n.name == "handler")
        calls = [n for n in ast.walk(handler)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "keyless_check"]
        self.assertEqual(len(calls), 1,
                         "handler() must call keyless_check exactly once, in the "
                         "`if not user` branch")

    def test_the_stranger_reply_leads_with_capability_not_a_signup_wall(self):
        # ANCHORED ON THE SECOND REPLY, not on the branch. The first version of
        # this test sliced from "No user found" and compared across BOTH
        # messages -- the verdict reply mentions relayshield.net near its top,
        # so it failed on correct code. A prose guard anchors on the sentence
        # that makes the claim, never on the region that happens to contain it.
        src = io.open(SRC, encoding="utf-8").read()
        i = src.index('"\U0001f44b *RelayShield*')
        block = src[i:i + 1500]
        send = block.index("Send me a link or a wallet address")
        wall = block.index("relayshield.net")
        self.assertLess(send, wall,
                        "in the no-message-to-check reply the capability "
                        "sentence must come before the signup line; leading "
                        "with a wall is what this branch used to do")


if __name__ == "__main__":
    unittest.main(verbosity=2)
