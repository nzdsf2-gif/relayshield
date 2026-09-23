"""BOT-TOKEN-1 phase 1: verify and attribute a leaked Telegram bot token.

Scoped in leaked_bot_token_finding_scope.md section 3, which draws the whole
ethical boundary this file exists to enforce: `getMe`, once per distinct
token, and NEVER `getUpdates`, `setWebhook` or `deleteWebhook` against a
token that is not ours. getUpdates is destructive against a stranger's bot
(it drains their pending update queue and returns other people's
conversations); getMe is read-only and returns only the bot's own username.

Every behavioural assertion here EXECUTES check_telegram_bot_token_liveness
and _store_bot_token_finding with urllib and boto3 stubbed, following this
repo's own rule that a suite calling only the handler cannot see a runtime
defect (ordering, fail-open, a partial result rendered as a clean one).
"""
import hashlib
import json
import pathlib
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
import relayshield_intel_monitor as mon  # noqa: E402

# A SYNTHETIC token, same shape as the one in test_bot_token_pattern.py and
# equally never a real credential.
FAKE_TOKEN = "8123456789:" + "A" * 10 + "BcD_eF-gH" + "i" * 16


class _FakeResp:
    def __init__(self, body: bytes):
        self._body = body
    def read(self):
        return self._body
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


class LivenessCheck(unittest.TestCase):
    """check_telegram_bot_token_liveness, executed against a stubbed urlopen."""

    def test_a_live_token_reports_live_and_the_username(self):
        body = json.dumps({"ok": True, "result": {"id": 1, "username": "AcmeSupportBot"}}).encode()
        with unittest.mock.patch.object(mon.urllib.request, "urlopen",
                                        lambda *a, **k: _FakeResp(body)):
            r = mon.check_telegram_bot_token_liveness(FAKE_TOKEN)
        self.assertEqual(r, {"checked": True, "live": True, "username": "AcmeSupportBot"})

    def test_a_401_is_a_checked_dead_answer_not_an_inconclusive_one(self):
        import urllib.error
        def boom(*a, **k):
            raise urllib.error.HTTPError(FAKE_TOKEN, 401, "Unauthorized", {}, None)
        with unittest.mock.patch.object(mon.urllib.request, "urlopen", boom):
            r = mon.check_telegram_bot_token_liveness(FAKE_TOKEN)
        self.assertEqual(r, {"checked": True, "live": False, "username": None})

    def test_a_timeout_is_NOT_reported_as_dead(self):
        """The exact failure the scope doc names: a live token whose getMe
        call times out must never come back as 'live: False'. That is a
        finding this product has no evidence for."""
        def boom(*a, **k):
            raise TimeoutError("timed out")
        with unittest.mock.patch.object(mon.urllib.request, "urlopen", boom):
            r = mon.check_telegram_bot_token_liveness(FAKE_TOKEN)
        self.assertFalse(r["checked"])
        self.assertIsNone(r["live"])

    def test_a_non_401_http_error_is_also_inconclusive(self):
        import urllib.error
        def boom(*a, **k):
            raise urllib.error.HTTPError(FAKE_TOKEN, 500, "Server Error", {}, None)
        with unittest.mock.patch.object(mon.urllib.request, "urlopen", boom):
            r = mon.check_telegram_bot_token_liveness(FAKE_TOKEN)
        self.assertFalse(r["checked"])
        self.assertIsNone(r["live"])

    def test_it_calls_getMe_and_names_no_other_method(self):
        """Executed, not read: capture the actual URL requested and assert
        on it, rather than trusting a comment describing the boundary."""
        seen = {}
        def fake_urlopen(req, timeout=None):
            seen["url"] = req.full_url if hasattr(req, "full_url") else str(req)
            return _FakeResp(json.dumps({"ok": True, "result": {"username": "x"}}).encode())
        with unittest.mock.patch.object(mon.urllib.request, "urlopen", fake_urlopen):
            mon.check_telegram_bot_token_liveness(FAKE_TOKEN)
        self.assertIn("/getMe", seen["url"])
        for forbidden in ("getUpdates", "setWebhook", "deleteWebhook"):
            self.assertNotIn(forbidden, seen["url"])


class LivenessSourceNamesOnlyGetMe(unittest.TestCase):
    """The hard boundary, asserted against the SOURCE of the two functions
    that touch a stranger's token -- not the whole file, which legitimately
    calls setWebhook and getUpdates-adjacent methods for OUR OWN bot
    elsewhere. Comments describing the rule are not the rule; this repo has
    been fooled by its own prose on this exact class of guard six times."""

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "relayshield_intel_monitor.py").read_text()

    def _function_source(self, name, strip_docstring=True):
        start = self.src.index(f"def {name}(")
        # Next top-level `def ` at column 0 ends this function.
        end = self.src.index("\ndef ", start + 1)
        body = self.src[start:end]
        if strip_docstring:
            # STRIPPED FIRST, NOT AFTER A FALSE POSITIVE. This file's own
            # docstrings AND inline comments name "getMe" as prose describing
            # what is delegated to or deliberately avoided, which a guard
            # searching the whole function text counts as the function
            # calling it -- the guard-fooled-by-its-own-comment shape this
            # repo has hit on its first run more times than any other single
            # defect. Both are stripped, not just the docstring.
            import re as _re
            body = _re.sub(r'"""[\s\S]*?"""', "", body, count=1)
            body = "\n".join(_re.sub(r"#.*$", "", line) for line in body.splitlines())
        return body

    def test_liveness_function_names_only_getMe(self):
        body = self._function_source("check_telegram_bot_token_liveness")
        self.assertIn("getMe", body)
        for forbidden in ("getUpdates", "setWebhook", "deleteWebhook"):
            self.assertNotIn(forbidden, body,
                             f"check_telegram_bot_token_liveness names {forbidden}")

    def test_storage_function_names_no_telegram_method_at_all(self):
        body = self._function_source("_store_bot_token_finding")
        for forbidden in ("getUpdates", "setWebhook", "deleteWebhook", "getMe"):
            self.assertNotIn(forbidden, body,
                             f"_store_bot_token_finding should delegate to the "
                             f"liveness function, not call {forbidden} itself")

    def test_the_docstring_stripping_itself_is_not_hiding_a_real_call(self):
        """Proves the strip above is not silently eating a real getMe call:
        the UNSTRIPPED liveness function still contains it."""
        body = self._function_source("check_telegram_bot_token_liveness", strip_docstring=False)
        self.assertIn("getMe", body)


class Storage(unittest.TestCase):
    """_store_bot_token_finding, executed against a stubbed DynamoDB table."""

    def _table(self, existing_item=None):
        table = unittest.mock.MagicMock()
        table.get_item.return_value = {"Item": existing_item} if existing_item else {}
        return table

    def test_the_raw_token_never_appears_in_the_stored_item(self):
        table = self._table()
        with unittest.mock.patch.object(mon, "_dynamodb",
                                        unittest.mock.MagicMock(Table=lambda name: table)), \
             unittest.mock.patch.object(mon, "check_telegram_bot_token_liveness",
                                        lambda t: {"checked": True, "live": True, "username": "x"}):
            mon._store_bot_token_finding(FAKE_TOKEN, "some_channel")
        item = table.put_item.call_args.kwargs["Item"]
        for value in item.values():
            self.assertNotIn(FAKE_TOKEN, str(value))

    def test_a_live_token_is_stored_as_CRITICAL(self):
        table = self._table()
        with unittest.mock.patch.object(mon, "_dynamodb",
                                        unittest.mock.MagicMock(Table=lambda name: table)), \
             unittest.mock.patch.object(mon, "check_telegram_bot_token_liveness",
                                        lambda t: {"checked": True, "live": True, "username": "AcmeBot"}):
            mon._store_bot_token_finding(FAKE_TOKEN, "chan")
        item = table.put_item.call_args.kwargs["Item"]
        self.assertEqual(item["severity"], "CRITICAL")
        self.assertEqual(item["username"], "AcmeBot")

    def test_a_dead_token_is_stored_as_MEDIUM_not_CRITICAL(self):
        table = self._table()
        with unittest.mock.patch.object(mon, "_dynamodb",
                                        unittest.mock.MagicMock(Table=lambda name: table)), \
             unittest.mock.patch.object(mon, "check_telegram_bot_token_liveness",
                                        lambda t: {"checked": True, "live": False, "username": None}):
            mon._store_bot_token_finding(FAKE_TOKEN, "chan")
        item = table.put_item.call_args.kwargs["Item"]
        self.assertEqual(item["severity"], "MEDIUM")

    def test_an_unchecked_token_is_neither_CRITICAL_NOR_MEDIUM(self):
        """The exact failure this whole phase exists to prevent: an
        inconclusive getMe call rendering as a definite answer."""
        table = self._table()
        with unittest.mock.patch.object(mon, "_dynamodb",
                                        unittest.mock.MagicMock(Table=lambda name: table)), \
             unittest.mock.patch.object(mon, "check_telegram_bot_token_liveness",
                                        lambda t: {"checked": False, "live": None, "username": None}):
            mon._store_bot_token_finding(FAKE_TOKEN, "chan")
        item = table.put_item.call_args.kwargs["Item"]
        self.assertNotIn(item["severity"], ("CRITICAL", "MEDIUM"))

    def test_a_token_already_recorded_gets_no_second_getMe_call(self):
        """'getMe, once per distinct token.' A second sighting of the same
        token across a different channel sweep must not spend a second call."""
        token_hash = hashlib.sha256(FAKE_TOKEN.encode()).hexdigest()
        table = self._table(existing_item={"token_hash": token_hash, "severity": "CRITICAL"})
        calls = []
        def spy(t):
            calls.append(t)
            return {"checked": True, "live": True, "username": "x"}
        with unittest.mock.patch.object(mon, "_dynamodb",
                                        unittest.mock.MagicMock(Table=lambda name: table)), \
             unittest.mock.patch.object(mon, "check_telegram_bot_token_liveness", spy):
            mon._store_bot_token_finding(FAKE_TOKEN, "chan")
        self.assertEqual(calls, [], "a second sighting of the same token re-ran getMe")
        table.put_item.assert_not_called()

    def test_the_dedup_key_is_the_token_hash(self):
        table = self._table()
        with unittest.mock.patch.object(mon, "_dynamodb",
                                        unittest.mock.MagicMock(Table=lambda name: table)), \
             unittest.mock.patch.object(mon, "check_telegram_bot_token_liveness",
                                        lambda t: {"checked": True, "live": True, "username": "x"}):
            mon._store_bot_token_finding(FAKE_TOKEN, "chan")
        item = table.put_item.call_args.kwargs["Item"]
        self.assertEqual(item["token_hash"], hashlib.sha256(FAKE_TOKEN.encode()).hexdigest())


class ExtractionWiresIntoTheStore(unittest.TestCase):
    """_parse_passwords_file must reach _store_bot_token_finding for both
    telegram_bot_token shapes, with the raw token and the channel."""

    def test_a_bare_token_line_reaches_the_store(self):
        calls = []
        with unittest.mock.patch.object(
                mon, "_store_bot_token_finding",
                lambda token, channel: calls.append((token, channel))), \
             unittest.mock.patch.object(mon, "_classify_domain", lambda d: ("LOW", "x")):
            mon._parse_passwords_file(f"example.com|TELEGRAM_BOT_TOKEN={FAKE_TOKEN}", "c1")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], (FAKE_TOKEN, "c1"))

    def test_the_url_form_reaches_the_store(self):
        calls = []
        with unittest.mock.patch.object(
                mon, "_store_bot_token_finding",
                lambda token, channel: calls.append((token, channel))), \
             unittest.mock.patch.object(mon, "_classify_domain", lambda d: ("LOW", "x")):
            mon._parse_passwords_file(
                f"example.com|curl https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage", "c2")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], (FAKE_TOKEN, "c2"))

    def test_an_unrelated_credential_never_reaches_the_store(self):
        calls = []
        with unittest.mock.patch.object(
                mon, "_store_bot_token_finding",
                lambda token, channel: calls.append((token, channel))), \
             unittest.mock.patch.object(mon, "_classify_domain", lambda d: ("LOW", "x")):
            mon._parse_passwords_file("example.com|AWS_ACCESS_KEY=AKIAABCDEFGHIJKLMNOP", "c3")
        self.assertEqual(calls, [])


class RemediationNeverSaysRotateForABotToken(unittest.TestCase):
    """CLAUDE.md: 'Remediation says REVOKE IN BOTFATHER, never rotate.' This
    guards the NHI alert message built in _process_stealer_archive, which
    told a bot-token victim to rotate before this phase."""

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "relayshield_intel_monitor.py").read_text()

    def test_nhi_alert_has_a_bot_token_specific_remediation_branch(self):
        i = self.src.index("if nhi_findings:")
        j = self.src.index("\n\n", self.src.index("nhi_msg = (", i))
        block = self.src[i:j]
        self.assertIn("BotFather", block)
        self.assertIn("cannot be rotated", block.lower().replace("—", "").strip() and block)

    def test_the_unconditional_rotate_line_is_gone(self):
        i = self.src.index("if nhi_findings:")
        j = self.src.index("\n\n", self.src.index("nhi_msg = (", i))
        block = self.src[i:j]
        # The OLD defect: "Rotate these credentials immediately." concatenated
        # unconditionally into every NHI alert regardless of finding type.
        self.assertNotIn('+ "\\n\\n*Rotate these credentials immediately.*\\n"', block)


if __name__ == "__main__":
    unittest.main(verbosity=1)
