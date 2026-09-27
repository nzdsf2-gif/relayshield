"""handle_wallet_risk -- EVM/Solana address checking, GoPlus address_security
plus (NEW) a token_security cross-check.

Found 2026-09-27: an unverified Solana token contract
(F4K2SbLNgyz9gzNqT8bPeLpRkxy4oMA9twaffUDdZtB6) came back "Low risk" from the
Chrome extension's Link/Wallet check. address_security answers "does this
ACCOUNT have a history of bad behaviour" -- a freshly-minted scam token
contract has no such history by definition, so it can NEVER be caught by that
call alone, whatever GoPlus's separate token_security data says about it.

Every test here EXECUTES the real handler with boto3 and urllib stubbed,
following test_email_check.py's and test_muse_connector_features.py's own
pattern: this is a runtime-only defect (the right vendor call was never being
made), invisible to a reader of the source.
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


class _FakeResp:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._body).encode()


def _urlopen_for(address_result, token_result, token_raises=False):
    """Routes by URL: /address_security/ vs /token_security/, matching how
    handle_wallet_risk actually calls GoPlus with two separate endpoints."""
    def fake(req, timeout=None):
        url = req.full_url
        if "address_security" in url:
            return _FakeResp({"result": address_result})
        if "token_security" in url:
            if token_raises:
                raise RuntimeError("token security upstream down")
            return _FakeResp({"result": {TOKEN_ADDR: token_result} if token_result else {}})
        raise AssertionError(f"unexpected URL: {url}")
    return fake


def body(resp):
    return json.loads(resp["body"])


class TokenContractCrossCheck(unittest.TestCase):
    """The defect this file exists to catch: address_security alone cannot
    see a scam TOKEN, only a scam ACCOUNT."""

    def test_a_clean_address_with_no_token_data_is_low(self):
        """The common case -- an ordinary wallet, not a token contract at
        all. token_security returns an empty result and must be a no-op."""
        with unittest.mock.patch.object(
                api.urllib.request, "urlopen",
                _urlopen_for({}, None)):
            d = body(api.handle_wallet_risk({"address": WALLET_ADDR}))
        self.assertEqual(d["data"]["risk_level"], "LOW")
        self.assertEqual(d["data"]["risk_flags"], [])
        self.assertNotIn("is_token_contract", d["data"]["metadata"])

    def test_a_honeypot_token_is_flagged_high_even_with_clean_address_history(self):
        """This is the Jupiter case: address_security has nothing (a fresh
        token has no account history), but the token itself is a honeypot."""
        with unittest.mock.patch.object(
                api.urllib.request, "urlopen",
                _urlopen_for({}, {"is_honeypot": "1"})):
            d = body(api.handle_wallet_risk({"address": TOKEN_ADDR}))
        self.assertEqual(d["data"]["risk_level"], "HIGH")
        self.assertIn("honeypot", " ".join(d["data"]["risk_flags"]).lower())
        self.assertTrue(d["data"]["metadata"]["is_token_contract"])

    def test_a_single_critical_token_flag_is_high_with_no_second_flag_needed(self):
        """Mirrors /v1/token-security's own scoring: honeypot/airdrop-scam/
        fake-token are each definitive alone, same reasoning as sanctions_hit
        for address-reputation flags."""
        with unittest.mock.patch.object(
                api.urllib.request, "urlopen",
                _urlopen_for({}, {"fake_token": "1"})):
            d = body(api.handle_wallet_risk({"address": TOKEN_ADDR}))
        self.assertEqual(d["data"]["risk_level"], "HIGH")

    def test_a_high_sell_tax_token_is_flagged(self):
        with unittest.mock.patch.object(
                api.urllib.request, "urlopen",
                _urlopen_for({}, {"sell_tax": "0.99"})):
            d = body(api.handle_wallet_risk({"address": TOKEN_ADDR}))
        self.assertEqual(d["data"]["risk_level"], "HIGH")
        self.assertIn("sell tax", " ".join(d["data"]["risk_flags"]).lower())

    def test_a_token_with_no_critical_flags_is_recorded_as_a_token_but_stays_low(self):
        """GoPlus recognising the address as a token is metadata, not itself
        a risk signal -- most legitimate tokens are, correctly, tokens."""
        with unittest.mock.patch.object(
                api.urllib.request, "urlopen",
                _urlopen_for({}, {"is_mintable": "1"})):  # a WARNING-tier flag, not critical
            d = body(api.handle_wallet_risk({"address": TOKEN_ADDR}))
        self.assertEqual(d["data"]["risk_level"], "LOW")
        self.assertTrue(d["data"]["metadata"]["is_token_contract"])

    def test_address_reputation_and_token_flags_land_in_one_combined_list(self):
        """A reputation flag and a token flag both surface in risk_flags --
        the token cross-check EXTENDS the list, it does not replace it."""
        with unittest.mock.patch.object(
                api.urllib.request, "urlopen",
                _urlopen_for({"phishing_activities": "1"}, {"fake_token": "1"})):
            d = body(api.handle_wallet_risk({"address": TOKEN_ADDR}))
        texts = " ".join(d["data"]["risk_flags"]).lower()
        self.assertIn("phishing", texts)
        self.assertIn("impersonates", texts)
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

    def test_solana_and_evm_use_the_correct_goplus_chain_id_for_token_security(self):
        """GoPlus's two APIs use DIFFERENT chain-id conventions for Solana:
        address_security wants the numeric 101, token_security wants the
        literal string "solana". Reusing _GOPLUS_CHAIN_IDS (101) for the
        token_security URL would silently query the wrong chain forever."""
        seen_urls = []

        def fake(req, timeout=None):
            seen_urls.append(req.full_url)
            if "address_security" in req.full_url:
                return _FakeResp({"result": {}})
            return _FakeResp({"result": {}})

        with unittest.mock.patch.object(api.urllib.request, "urlopen", fake):
            api.handle_wallet_risk({"address": TOKEN_ADDR})

        token_url = next(u for u in seen_urls if "token_security" in u)
        self.assertIn("/token_security/solana", token_url)
        self.assertNotIn("/token_security/101", token_url)

    def test_evm_token_security_defaults_to_ethereum_mainnet(self):
        seen_urls = []
        evm_addr = "0x" + "a" * 40

        def fake(req, timeout=None):
            seen_urls.append(req.full_url)
            return _FakeResp({"result": {}})

        with unittest.mock.patch.object(api.urllib.request, "urlopen", fake):
            api.handle_wallet_risk({"address": evm_addr})

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
