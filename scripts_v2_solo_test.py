"""
One-off manual script — NOT part of the deployed Lambdas, run locally only.

Solo settlement test: pays ONLY /v1/payg/breach, in isolation, to test the
hypothesis that CDP's Bazaar re-index pipeline debounces rapid back-to-back
settlements (scripts_v2_batch1_test.py fired 4 settlements within seconds of
each other; only 1 of 4 re-indexed to V2 shape). If this solo call updates
Bazaar's entry for breach specifically, that confirms batching settlements
too close together is the actual cause.

Cost: $0.10 real USDC.

Setup: same as scripts_v2_batch1_test.py — reuses .venv-bazaar-test and
EVM_PRIVATE_KEY (already exported in this terminal session per prior runs).

Run:
    python3 scripts_v2_solo_test.py
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
        path = "/v1/payg/breach"
        body = {"email": "user@example.com"}
        url = f"{API_BASE}{path}"
        print(f"\n--- POST {path} (solo settlement) ---")
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
