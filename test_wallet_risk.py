"""handle_wallet_risk -- EVM/Solana address checking, GoPlus address_security
plus a token_security cross-check.

Found 2026-09-27: an unverified Solana token contract
(F4K2SbLNgyz9gzNqT8bPeLpRkxy4oMA9twaffUDdZtB6) came back "Low risk" from the
Chrome extension. address_security answers "does this ACCOUNT have a history
of bad behaviour" -- a freshly-minted scam token contract has no such history
by definition, so it can NEVER be caught by that call alone.

**Round two, same day**: the first fix for the finding above assumed Solana
was just another chain_id on GoPlus's EVM token_security URL, and reused
EVM's field names (is_honeypot, is_airdrop_scam, fake_token, sell_tax). Three
MORE confirmed-scam Solana tokens still came back "Low risk" after that
shipped. GoPlus's Solana token_security is a SEPARATELY VERSIONED ("beta")
endpoint with the path segments in the OPPOSITE order
(/api/v1/solana/token_security, not /api/v1/token_security/solana) and an
entirely different response schema (nested {"status": "0"|"1"} capability
objects: freezable, mintable, closable, balance_mutable_authority,
metadata_mutable -- not EVM's flat is_x booleans), confirmed from GoPlus's own
official Python SDK on PyPI (`pip download goplus`), since api.gopluslabs.io
itself could not be reached from this container to verify directly.

Every test here EXECUTES the real handler with boto3 and urllib stubbed.
"""
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
import relayshield_api as api  # noqa: E402

TOKEN_ADDR = "F4K2SbLNgyz9gzNqT8bPeLpRkxy4oMA9twaffUDdZtB6"
WALLET_ADDR = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
EVM_ADDR = "0x" + "a" * 40


def _status(active):
    """One Solana capability-flag object, matching GoPlus's real nested
    {"status": "0"|"1", "authority": [...]} shape."""
    return {"status": "1" if active else "0", "authority": []}


class _FakeResp:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._body).encode()


def _urlopen_for(address_result, token_result, address=TOKEN_ADDR, token_raises=False):
    """Routes by URL: address_security vs (evm) token_security vs
    (solana) solana/token_security -- three distinct GoPlus endpoints."""
    def fake(req, timeout=None):
        url = req.full_url
        if "address_security" in url:
            return _FakeResp({"result": address_result})
        if "solana/token_security" in url or "token_security/" in url:
            if token_raises:
                raise RuntimeError("token security upstream down")
            return _FakeResp({"result": {address: token_result} if token_result else {}})
        raise AssertionError(f"unexpected URL: {url}")
    return fake


def body(resp):
    return json.loads(resp["body"])


class SolanaTokenSecurityRealSchema(unittest.TestCase):
    """The second bug: the FIRST fix used the wrong URL and EVM's field
    names for Solana. These are the real thing."""

    def test_the_solana_url_path_is_in_the_order_the_real_sdk_uses(self):
        """/api/v1/solana/token_security, NOT /api/v1/token_security/solana --
        the latter is what "just substitute the chain_id" would have produced
        and is what actually shipped for a few hours."""
        seen = []

        def fake(req, timeout=None):
            seen.append(req.full_url)
            return _FakeResp({"result": {}})

        with unittest.mock.patch.object(api.urllib.request, "urlopen", fake):
            api.handle_wallet_risk({"address": TOKEN_ADDR})

        token_url = next(u for u in seen if "token_security" in u)
        self.assertIn("/api/v1/solana/token_security", token_url)
        self.assertNotIn("/token_security/solana", token_url)

    def test_freezable_is_critical_the_solana_honeypot_equivalent(self):
        with unittest.mock.patch.object(
                api.urllib.request, "urlopen",
                _urlopen_for({}, {"freezable": _status(True)})):
            d = body(api.handle_wallet_risk({"address": TOKEN_ADDR}))
        self.assertEqual(d["data"]["risk_level"], "HIGH")
        self.assertIn("freeze", " ".join(d["data"]["risk_flags"]).lower())

    def test_balance_mutable_authority_is_critical(self):
        with unittest.mock.patch.object(
                api.urllib.request, "urlopen",
                _urlopen_for({}, {"balance_mutable_authority": _status(True)})):
            d = body(api.handle_wallet_risk({"address": TOKEN_ADDR}))
        self.assertEqual(d["data"]["risk_level"], "HIGH")

    def test_none_transferable_is_critical(self):
        with unittest.mock.patch.object(
                api.urllib.request, "urlopen",
                _urlopen_for({}, {"none_transferable": "1"})):
            d = body(api.handle_wallet_risk({"address": TOKEN_ADDR}))
        self.assertEqual(d["data"]["risk_level"], "HIGH")

    def test_mintable_alone_is_a_warning_not_a_high_verdict(self):
        """Mirrors EVM's own is_mintable tier: real, but also describes a
        normal early-stage legitimate token -- never decisive alone."""
        with unittest.mock.patch.object(
                api.urllib.request, "urlopen",
                _urlopen_for({}, {"mintable": _status(True)})):
            d = body(api.handle_wallet_risk({"address": TOKEN_ADDR}))
        self.assertEqual(d["data"]["risk_level"], "MEDIUM")

    def test_closable_and_metadata_mutable_are_warnings(self):
        with unittest.mock.patch.object(
                api.urllib.request, "urlopen",
                _urlopen_for({}, {"closable": _status(True),
                                   "metadata_mutable": _status(True)})):
            d = body(api.handle_wallet_risk({"address": TOKEN_ADDR}))
        self.assertEqual(d["data"]["risk_level"], "HIGH")  # 2 warnings >= threshold
        texts = " ".join(d["data"]["risk_flags"]).lower()
        self.assertIn("closed", texts)
        self.assertIn("name/symbol", texts)

    def test_status_zero_never_flags(self):
        with unittest.mock.patch.object(
                api.urllib.request, "urlopen",
                _urlopen_for({}, {"freezable": _status(False), "mintable": _status(False)})):
            d = body(api.handle_wallet_risk({"address": TOKEN_ADDR}))
        self.assertEqual(d["data"]["risk_level"], "LOW")
        self.assertEqual(d["data"]["risk_flags"], [])

    def test_a_missing_capability_key_is_treated_as_inactive_not_crashing(self):
        """A response that omits a field entirely (GoPlus does not always
        return every key) must not raise -- absence is not evidence of the
        capability being active."""
        with unittest.mock.patch.object(
                api.urllib.request, "urlopen",
                _urlopen_for({}, {"trusted_token": 1})):  # no capability keys at all
            d = body(api.handle_wallet_risk({"address": TOKEN_ADDR}))
        self.assertEqual(d["data"]["risk_level"], "LOW")


class TokenContractCrossCheck(unittest.TestCase):
    """The general shape, chain-agnostic."""

    def test_a_clean_address_with_no_token_data_is_low(self):
        """The common case -- an ordinary wallet, not a token contract at
        all. token_security returns an empty result and must be a no-op."""
        with unittest.mock.patch.object(
                api.urllib.request, "urlopen",
                _urlopen_for({}, None, address=WALLET_ADDR)):
            d = body(api.handle_wallet_risk({"address": WALLET_ADDR}))
        self.assertEqual(d["data"]["risk_level"], "LOW")
        self.assertEqual(d["data"]["risk_flags"], [])
        self.assertNotIn("is_token_contract", d["data"]["metadata"])

    def test_a_token_with_no_critical_flags_is_recorded_as_a_token_but_stays_low(self):
        with unittest.mock.patch.object(
                api.urllib.request, "urlopen",
                _urlopen_for({}, {"mintable": _status(False)})):
            d = body(api.handle_wallet_risk({"address": TOKEN_ADDR}))
        self.assertEqual(d["data"]["risk_level"], "LOW")
        self.assertTrue(d["data"]["metadata"]["is_token_contract"])

    def test_address_reputation_and_token_flags_land_in_one_combined_list(self):
        """A reputation flag and a token flag both surface in risk_flags --
        the token cross-check EXTENDS the list, it does not replace it."""
        with unittest.mock.patch.object(
                api.urllib.request, "urlopen",
                _urlopen_for({"phishing_activities": "1"},
                              {"freezable": _status(True)})):
            d = body(api.handle_wallet_risk({"address": TOKEN_ADDR}))
        texts = " ".join(d["data"]["risk_flags"]).lower()
        self.assertIn("phishing", texts)
        self.assertIn("freeze", texts)
        self.assertEqual(len(d["data"]["risk_flags"]), 2)
        self.assertEqual(d["data"]["risk_level"], "HIGH")

    def test_a_failed_token_cross_check_marks_the_result_degraded(self):
        """'We could not check' must never render as a confident clean
        result -- the same rule the address_security path already follows
        for its own upstream failures."""
        with unittest.mock.patch.object(
                api.urllib.request, "urlopen",
                _urlopen_for({}, None, token_raises=True)):
            d = body(api.handle_wallet_risk({"address": TOKEN_ADDR}))
        self.assertTrue(d["data"]["degraded"])
        self.assertEqual(d["data"]["risk_level"], "LOW")  # still not FALSELY flagged

    def test_evm_token_security_still_uses_its_own_confirmed_field_names(self):
        """The EVM path is unchanged by the Solana rewrite -- is_honeypot
        etc. are confirmed real EVM field names (GoPlus's own SDK model
        ResponseWrapperTokenSecurityResult), unlike the Solana ones that
        were wrong."""
        with unittest.mock.patch.object(
                api.urllib.request, "urlopen",
                _urlopen_for({}, {"is_honeypot": "1"}, address=EVM_ADDR)):
            d = body(api.handle_wallet_risk({"address": EVM_ADDR}))
        self.assertEqual(d["data"]["risk_level"], "HIGH")
        self.assertIn("honeypot", " ".join(d["data"]["risk_flags"]).lower())

    def test_evm_token_security_defaults_to_ethereum_mainnet(self):
        seen_urls = []

        def fake(req, timeout=None):
            seen_urls.append(req.full_url)
            return _FakeResp({"result": {}})

        with unittest.mock.patch.object(api.urllib.request, "urlopen", fake):
            api.handle_wallet_risk({"address": EVM_ADDR})

        token_url = next(u for u in seen_urls if "token_security" in u)
        self.assertIn("/token_security/1", token_url)

    def test_bitcoin_and_ton_never_call_token_security(self):
        """The cross-check is GoPlus-specific (evm/solana only) -- bitcoin
        and TON addresses have their own dedicated upstreams already."""
        calls = []

        def fake(req, timeout=None):
            calls.append(req.full_url)
            return _FakeResp({"chain_stats": {}, "mempool_stats": {}})

        with unittest.mock.patch.object(api.urllib.request, "urlopen", fake):
            api.handle_wallet_risk({"address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"})
        self.assertFalse(any("token_security" in u for u in calls))


if __name__ == "__main__":
    unittest.main()
