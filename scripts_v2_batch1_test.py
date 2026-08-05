"""
One-off manual script — NOT part of the deployed Lambdas, run locally only.

Sends real, small x402 USDC payments (Base network) against the 4 endpoints
in x402 V2 migration batch 1 (breach, domain, supply-chain, sim-swap — see
TODO.md item 50) to confirm settlement + Bazaar re-indexing still work under
the new V2 wire format. Reuses the same pattern as scripts_bazaar_indexing_test.py.

Cost: ~$0.75 total real USDC across all 4 calls ($0.10 + $0.30 + $0.10 + $0.25).

Setup before running (the .venv-bazaar-test venv from the original Bazaar
rollout already has everything needed):
    source .venv-bazaar-test/bin/activate
    export EVM_PRIVATE_KEY="0x..."   # a wallet funded with a little USDC on Base
                                      # never paste this key into chat/commits

Run:
    python3 scripts_v2_batch1_test.py
"""

import os

from eth_account import Account
from x402 import x402ClientSync
from x402.http import x402HTTPClientSync
from x402.http.clients import x402_requests
from x402.mechanisms.evm import EthAccountSigner
from x402.mechanisms.evm.exact.register import register_exact_evm_client

API_BASE = "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod"

CALLS = [
    ("/v1/payg/breach", {"email": "user@example.com"}),                    # $0.10
    ("/v1/payg/domain", {"domain": "acme.com"}),                           # $0.30
    ("/v1/payg/supply-chain", {"vendor_domains": ["acme.com", "vendor2.com"]}),  # $0.10
    ("/v1/payg/sim-swap", {"phone": "+14155551234"}),                      # $0.25
    # Total: $0.75 -- confirms all 4 batch-1 endpoints settle under V2.
]


def main() -> None:
    private_key = os.getenv("EVM_PRIVATE_KEY")
    if not private_key:
        raise SystemExit("Set EVM_PRIVATE_KEY to a funded wallet's private key first.")

    client = x402ClientSync()
    account = Account.from_key(private_key)
    register_exact_evm_client(client, EthAccountSigner(account))
    http_client = x402HTTPClientSync(client)

    with x402_requests(client) as session:
        for path, body in CALLS:
            url = f"{API_BASE}{path}"
            print(f"\n--- POST {path} ---")
            response = session.post(url, json=body)
            print(f"status={response.status_code}")
            print(response.text[:500])
            if response.ok:
                settle = http_client.get_payment_settle_response(
                    lambda name: response.headers.get(name)
                )
                print(f"payment settled: {settle}")


if __name__ == "__main__":
    main()
