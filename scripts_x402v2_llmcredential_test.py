"""
One-off manual script — NOT part of the deployed Lambdas, run locally only.

Sends ONE real, small x402 V2 USDC payment (Base network) against
/v1/payg/llm-credential-exposure to get CDP's Bazaar discovery catalog to
index/re-index this endpoint (item 79 — this endpoint has never had a real
test settlement run against it, so its indexing status is unverified).
Mirrors the exact proven pattern from scripts_x402v2_domain_test.py
(2026-07-16 fix), same SDK usage, same facilitator.

Cost: $0.40 USDC + Base gas (CDP sponsors gas — confirmed zero ETH spent
from the buyer wallet across all prior test runs of this pattern).

Setup (venv from prior test runs already has everything needed):
    source .venv-bazaar-test/bin/activate
    export EVM_PRIVATE_KEY="0x..."   # never paste this key into chat/commits

Run:
    python3 scripts_x402v2_llmcredential_test.py

After running: check CDP's Bazaar discovery search for
llm-credential-exposure's quality.lastCalledAt — it should reflect this
settlement's timestamp, confirming the endpoint is now indexed/current.
"""

import os

from eth_account import Account
from x402 import x402ClientSync
from x402.http import x402HTTPClientSync
from x402.http.clients import x402_requests
from x402.mechanisms.evm import EthAccountSigner
from x402.mechanisms.evm.exact.register import register_exact_evm_client

API_BASE = "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod"


def main() -> None:
    private_key = os.getenv("EVM_PRIVATE_KEY")
    if not private_key:
        raise SystemExit("Set EVM_PRIVATE_KEY to a funded wallet's private key first.")

    client = x402ClientSync()
    account = Account.from_key(private_key)
    register_exact_evm_client(client, EthAccountSigner(account))
    http_client = x402HTTPClientSync(client)

    with x402_requests(client) as session:
        url = f"{API_BASE}/v1/payg/llm-credential-exposure"
        print(f"\n--- POST /v1/payg/llm-credential-exposure ---")
        response = session.post(url, json={"domain": "example.com"})
        print(f"status={response.status_code}")
        print(response.text[:500])
        if response.ok:
            settle = http_client.get_payment_settle_response(
                lambda name: response.headers.get(name)
            )
            print(f"payment settled: {settle}")


if __name__ == "__main__":
    main()
