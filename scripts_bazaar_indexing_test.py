"""
One-off manual script — NOT part of the deployed Lambdas, run locally only.

Sends real, small x402 USDC payments (Base network) against RelayShield
PAYG endpoints to confirm CDP Bazaar indexing. Both Lambdas have CDP
(Coinbase Developer Platform) credentials configured, and
_select_facilitator() automatically prefers CDP over PayAI whenever those
creds are present — so this script settles through CDP with zero
facilitator-specific code here.

2026-07-12 update: 6 of 24 endpoints are CONFIRMED indexed in CDP's Bazaar
as of this date (mcp-registry-risk, prompt-injection-breach, breach,
sim-swap, domain, identity-risk-score), after fixing the real root cause —
Bazaar discovery metadata for a V1 x402 payload must live in a top-level
`outputSchema` field (matching Coinbase's own V1 reference extractor), not
`extensions.bazaar` (the V2-only convention). That fix is proven to
generalize across the whole catalog. This run settles the remaining 18
untested endpoints to get full Bazaar coverage.

Cost: ~$6.15 total real USDC spend across all 18 calls below (see per-call
comments), plus Base gas (CDP sponsors gas — confirmed zero ETH spent from
the buyer wallet across all prior test runs). Comment out any lines you
want to skip to reduce cost.

Setup before running (if not already done — a working venv from the last
run may already have everything):
    python3 -m venv .venv-bazaar-test && source .venv-bazaar-test/bin/activate
    pip install "x402[requests,evm]" web3 eth-account
    export EVM_PRIVATE_KEY="0x..."   # a wallet funded with a little USDC on Base
                                      # never paste this key into chat/commits

Run:
    python3 scripts_bazaar_indexing_test.py
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
    ("/v1/payg/scan-url", {"url": "https://suspicious-site.example.com"}),                                    # $0.05
    ("/v1/payg/scan-wallet", {"address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "chain_id": "1"}),      # $0.10
    ("/v1/payg/scan-file", {"file_url": "https://cdn.example.com/invoice.pdf", "filename": "invoice.pdf"}),    # $0.10
    ("/v1/payg/token-security", {"contract_address": "0x6982508145454ce325ddbe47a25d4ec3d2311933", "chain_id": "1"}),  # $0.10
    ("/v1/payg/nft-security", {"contract_address": "0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d", "chain_id": "1"}),    # $0.10
    ("/v1/payg/wallet-risk", {"address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"}),                       # $0.15
    ("/v1/payg/oauth-watchlist", {"email": "user@example.com"}),                                               # $0.30
    ("/v1/payg/secret-scan", {"domain": "acme.com"}),                                                          # $0.35
    ("/v1/payg/wallet-screen-batch", {"addresses": ["0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"]}),  # $0.50
    # Total: $1.75 -- completes all 24 endpoints in the catalog.

    # Already confirmed indexed, no need to re-run:
    # ("/v1/payg/tech-stack-cve", ...),        -- DONE
    # ("/v1/payg/nhi-exposure", ...),          -- DONE
    # ("/v1/payg/bulk-identity-risk", ...),    -- DONE
    # ("/v1/payg/target-risk", ...),           -- DONE
    # ("/v1/payg/infostealer", ...),           -- DONE
    # ("/v1/payg/supply-chain", ...),          -- DONE
    # ("/v1/payg/session-risk", ...),          -- DONE
    # ("/v1/payg/identity-graph", ...),        -- DONE
    # ("/v1/payg/ransomware-risk", ...),       -- DONE
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
