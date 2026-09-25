"""/.well-known/x402.json must list every priced endpoint in BOTH
relayshield_api.py and relayshield_agentic_api.py, not just the first.

Found 2026-09-24: handle_x402_manifest() in relayshield_api.py only ever
iterated its OWN PAYG_PRICE_UNITS table. relayshield_agentic_api.py runs as a
separate Lambda under the same branded host (api.relayshield.net) and has no
manifest handler of its own, so its three priced endpoints -- agent-bait-scan,
mcp-registry-risk, prompt-injection-breach -- were invisible to every x402
indexer reading the manifest, despite being live, correctly priced, and
challenging at the right x402 version. Worse than the single agent-bait-scan
gap previously recorded in CLAUDE.md: all three were missing, because the
handler never looked at that file's table at all.

Executed against the real handler (with boto3 stubbed) rather than read from
source, per this repo's own "a dispatcher/composition gap is invisible to a
suite that only calls handlers or only reads source" lesson
(test_incident_timeline.py, test_muse_connector_features.py). Proven by
reintroducing the exact defect -- monkeypatching handle_x402_manifest back to
reading only PAYG_PRICE_UNITS -- and watching it fail before restoring.
"""
import json
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
import relayshield_agentic_api as agentic  # noqa: E402


def _body(resp):
    return json.loads(resp["body"])


class ManifestCoversBothLambdas(unittest.TestCase):
    def test_every_relayshield_api_path_is_in_the_manifest(self):
        urls = {r["url"] for r in _body(api.handle_x402_manifest())["resources"]}
        for path in api.PAYG_PRICE_UNITS:
            self.assertIn(f"https://api.relayshield.net{path}", urls)

    def test_every_agentic_api_path_is_in_the_manifest(self):
        urls = {r["url"] for r in _body(api.handle_x402_manifest())["resources"]}
        for path in agentic.PAYG_PRICE_UNITS:
            self.assertIn(f"https://api.relayshield.net{path}", urls,
                           f"{path} is a live, priced agentic_api endpoint "
                           "absent from the discovery manifest")

    def test_agent_bait_scan_mcp_registry_risk_and_prompt_injection_breach_present(self):
        # Named explicitly: these three are the concrete case, not an
        # abstraction over "whatever agentic_api.py happens to contain".
        urls = {r["url"] for r in _body(api.handle_x402_manifest())["resources"]}
        for path in ("/v1/payg/agent-bait-scan", "/v1/payg/mcp-registry-risk",
                     "/v1/payg/prompt-injection-breach"):
            self.assertIn(f"https://api.relayshield.net{path}", urls)

    def test_resource_count_matches_both_tables_combined(self):
        body = _body(api.handle_x402_manifest())
        expected = len(api.PAYG_PRICE_UNITS) + len(agentic.PAYG_PRICE_UNITS)
        self.assertEqual(body["resourceCount"], expected)
        self.assertEqual(len(body["resources"]), expected)

    def test_agentic_entries_carry_a_real_x402_challenge(self):
        # Not just present -- each entry must carry the same accepts/version
        # shape as a relayshield_api.py entry, built from the live challenge.
        by_url = {r["url"]: r for r in _body(api.handle_x402_manifest())["resources"]}
        entry = by_url["https://api.relayshield.net/v1/payg/agent-bait-scan"]
        self.assertEqual(entry["x402Version"], 2)
        self.assertTrue(entry["accepts"])
        self.assertEqual(entry["priceUsd"], 0.5)


if __name__ == "__main__":
    unittest.main()
