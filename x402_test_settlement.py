"""
x402 test settlement script — CDPX-7 staged V2 migration.

Fires one real x402 payment against one or more Batch endpoints so CDP's
Bazaar catalog gets a fresh call to recrawl (see CDPX-2's finding: V1 vs V2
doesn't gate rich descriptions, but a stale catalog entry needs a new call
to refresh). Reusable across Batches B/C/D/E — just change ENDPOINTS below.

Uses the real installed x402 Python SDK (.venv-bazaar-test), not a hand-
rolled payload — same mechanism verified working against supply-chain.

Requires a funded EVM wallet private key in the env var named below.
Never pass the key on the command line or hardcode it here.

Usage:
    source .venv-bazaar-test/bin/activate
    python3 x402_test_settlement.py
"""

import json
import os

from eth_account import Account
from x402 import x402ClientSync
from x402.http.clients.requests import x402_requests
from x402.mechanisms.evm.exact.register import register_exact_evm_client
from x402.mechanisms.evm.signers import EthAccountSigner

API_BASE = "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod"

# Phase 2 trio, with known-good example request bodies (pulled from each
# handler's own signature in relayshield_api.py — handle_domain, handle_breach,
# handle_sim_swap — not guessed). This is the retry of the 3 endpoints held
# back since 2026-07-15 after 2 prior failed real-money cataloging attempts
# on `domain` specifically — every other batch has since resolved cleanly.
ENDPOINTS = [
    ("/v1/payg/domain", {"domain": "acme.com"}),
    ("/v1/payg/breach", {"email": "agent@acme.com"}),
    ("/v1/payg/sim-swap", {"phone": "+14155551234"}),
]

# Batch D (previous batch — kept here as reference, not active).
_BATCH_D_ENDPOINTS = [
    ("/v1/payg/wallet-risk", {"address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"}),
    ("/v1/payg/token-security", {"contract_address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"}),
    ("/v1/payg/scan-url", {"url": "https://example.com"}),
    ("/v1/payg/nft-security", {"contract_address": "0xBC4CA0EdA7647A8aB7C2061c2E118A18a936f13D"}),
    ("/v1/payg/scan-file", {"file_url": "https://raw.githubusercontent.com/octocat/Hello-World/master/README"}),
    ("/v1/payg/scan-wallet", {"address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"}),
    ("/v1/payg/infostealer", {"email": "test@example.com"}),
]

PRIVATE_KEY_ENV_VAR = "BP_PRIVATE_KEY"  # <-- adjust to match your actual env var name


def main() -> None:
    private_key = os.environ.get(PRIVATE_KEY_ENV_VAR)
    if not private_key:
        raise SystemExit(
            f"Set {PRIVATE_KEY_ENV_VAR} to your funded Base-mainnet wallet's "
            f"private key before running (e.g. `export {PRIVATE_KEY_ENV_VAR}=0x...`)."
        )

    # This machine's Anaconda base environment reliably reinjects whitespace/
    # quote characters around env vars exported before .venv-bazaar-test is
    # activated (binascii.Error: Non-hexadecimal digit found otherwise) — strip
    # all whitespace and surrounding quotes so the key parses regardless.
    private_key = "".join(private_key.split()).strip("'\"")

    account = Account.from_key(private_key)
    signer = EthAccountSigner(account)

    client = x402ClientSync()
    register_exact_evm_client(client, signer, networks="eip155:8453")  # Base mainnet
    session = x402_requests(client)

    print(f"Paying from {account.address}\n")

    for path, body in ENDPOINTS:
        url = f"{API_BASE}{path}"
        print(f"--- {path} ---")
        resp = session.post(url, json=body)
        print(f"status: {resp.status_code}")
        try:
            print(json.dumps(resp.json(), indent=2)[:500])
        except ValueError:
            print(resp.text[:500])
        print()


if __name__ == "__main__":
    main()
