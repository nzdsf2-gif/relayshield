"""
One-off manual script — NOT part of the deployed Lambdas, run locally only.

Sends ONE real x402 V2 USDC payment (Base network) against
/v1/payg/supply-chain to confirm the corrected _v2_bazaar_extension()
schema fix (2026-07-17, root-caused via Ethan Oroshiba's GitHub report on
x402-foundation/x402#2814: "(root).input: domain is required") actually
lets CDP Bazaar catalog/update the resource on settlement. Before this
test: supply-chain's quality.lastCalledAt was stuck at 2026-07-14T14:03:11Z
despite this being the one endpoint that's been live in V2 the whole time.

Cost: $0.10 USDC + Base gas (CDP sponsors gas — confirmed zero ETH spent
from the buyer wallet across all prior test runs this session).

Setup (venv from prior test runs already has everything needed):
    source .venv-bazaar-test/bin/activate
    read -s -p "Paste private key: " EVM_PRIVATE_KEY && echo && export EVM_PRIVATE_KEY

Run:
    python3 scripts_x402v2_supplychain_test.py

After running: check CDP's Bazaar discovery search for supply-chain's
quality.lastCalledAt — it should now reflect this settlement's timestamp
instead of the frozen 2026-07-14 value:

    curl -s "https://api.cdp.coinbase.com/platform/v2/x402/discovery/search?urlSubstring=payg%2Fsupply-chain" \\
      | python3 -c "import json,sys; d=json.load(sys.stdin); [print(r['quality'].get('lastCalledAt')) for r in d['resources']]"
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
        url = f"{API_BASE}/v1/payg/supply-chain"
        print("\n--- POST /v1/payg/supply-chain ---")
        response = session.post(url, json={"vendor_domains": ["example.com"]})
        print(f"status={response.status_code}")
        print(response.text[:500])
        if response.ok:
            settle = http_client.get_payment_settle_response(
                lambda name: response.headers.get(name)
            )
            print(f"payment settled: {settle}")


if __name__ == "__main__":
    main()
