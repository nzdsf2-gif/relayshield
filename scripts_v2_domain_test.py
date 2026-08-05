"""
One-off manual script — NOT part of the deployed Lambdas, run locally only.

Solo settlement test: pays ONLY /v1/payg/domain, to test the "entry age"
hypothesis — domain is an original July 12 rollout entry (like breach and
sim-swap, which never re-indexed to V2), unlike supply-chain (added later,
indexed cleanly on first try). If this settlement re-indexes domain to V2
shape, entry age is not the cause; if it stays stuck on the stale V1 shape
like breach/sim-swap did, that's real evidence for the age hypothesis.

Cost: $0.50 real USDC.

Setup: same as scripts_v2_solo_test.py — reuses .venv-bazaar-test and
EVM_PRIVATE_KEY (export it fresh in this terminal session first).

Run:
    python3 scripts_v2_domain_test.py
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
        path = "/v1/payg/domain"
        body = {"domain": "acme.com"}
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
