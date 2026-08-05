"""
One-off manual script — NOT part of the deployed Lambdas, run locally only.

CS-BADGE-2 research scan: checks a batch of 4 real company domains via
/v1/payg/domain (check_domain_lookalikes) for active typosquat/phishing
domains, paid via real x402 USDC on Base. Domain-only input, no PII — see
TODO.md CS-BADGE-2 methodology note for the legal safeguard (never publish
per-company results, category-aggregated only, ~8-10 samples/category).

24 domains total across 3 categories (DeFi, Prediction Markets, Fintech),
split into 6 batches of 4 domains each so cost stays visible in $2
increments rather than one $12 lump sum.

Cost per batch: $2.00 real USDC ($0.50 x 4).

Setup before running:
    source .venv-bazaar-test/bin/activate   # or any venv with x402 + eth_account installed
    export EVM_PRIVATE_KEY="0x..."          # your funded Backpack wallet's private key
                                             # never paste this key into chat/commits

Run one batch at a time:
    python3 scripts_badge_research_domain_batch.py 1
    python3 scripts_badge_research_domain_batch.py 2
    ...through 6

Or re-run a single domain on its own ($0.50) — e.g. after a one-off failure:
    python3 scripts_badge_research_domain_batch.py --domain uniswap.org

Full untruncated JSON for every call is appended to cs_badge_research_results.jsonl
(one line per domain) in the current directory — terminal output is now
truncated to 300 chars just as a live sanity check. Share that file (or its
contents) back with Claude after each run to aggregate results into the
category-level research findings, rather than relying on the terminal
scrollback.
"""

import json
import sys

from eth_account import Account
from x402 import x402ClientSync
from x402.http import x402HTTPClientSync
from x402.http.clients import x402_requests
from x402.mechanisms.evm import EthAccountSigner
from x402.mechanisms.evm.exact.register import register_exact_evm_client

import os

RESULTS_FILE = "cs_badge_research_results.jsonl"

API_BASE = "https://atq6wtkp6k.execute-api.us-east-1.amazonaws.com/prod"

BATCHES = {
    1: ("DeFi",              ["lido.fi", "aave.com", "eigenlayer.xyz", "uniswap.org"]),
    2: ("DeFi",              ["sky.money", "compound.finance", "curve.fi", "pancakeswap.finance"]),
    3: ("Prediction Markets", ["polymarket.com", "kalshi.com", "manifold.markets", "predictit.org"]),
    4: ("Prediction Markets", ["limitless.exchange", "myriad.markets", "azuro.org", "predict.fun"]),
    5: ("Fintech",            ["stripe.com", "paypal.com", "block.xyz", "adyen.com"]),
    6: ("Fintech",            ["coinbase.com", "chime.com", "revolut.com", "n26.com"]),
}


def main() -> None:
    usage = f"Usage: python3 {sys.argv[0]} <batch_number 1-6> | --domain <domain>"

    if len(sys.argv) == 3 and sys.argv[1] == "--domain":
        domains = [sys.argv[2]]
        header = f"=== Single domain — {domains[0]} — $0.50 ==="
    elif len(sys.argv) == 2 and sys.argv[1] in map(str, BATCHES):
        batch_num = int(sys.argv[1])
        category, domains = BATCHES[batch_num]
        header = f"=== Batch {batch_num}/6 — {category} — {len(domains)} domains — $2.00 total ==="
    else:
        raise SystemExit(usage)

    private_key = os.getenv("EVM_PRIVATE_KEY")
    if not private_key:
        raise SystemExit("Set EVM_PRIVATE_KEY to your funded wallet's private key first.")

    client = x402ClientSync()
    account = Account.from_key(private_key)
    register_exact_evm_client(client, EthAccountSigner(account))
    http_client = x402HTTPClientSync(client)

    print(header)

    with x402_requests(client) as session, open(RESULTS_FILE, "a") as out:
        for domain in domains:
            url = f"{API_BASE}/v1/payg/domain"
            print(f"\n--- POST /v1/payg/domain domain={domain} ---")
            response = session.post(url, json={"domain": domain})
            print(f"status={response.status_code}")
            print(response.text[:300], "..." if len(response.text) > 300 else "")
            print(f"[full response written to {RESULTS_FILE}]")
            out.write(json.dumps({"domain": domain, "status": response.status_code,
                                   "response": response.text}) + "\n")
            out.flush()
            if response.ok:
                settle = http_client.get_payment_settle_response(
                    lambda name: response.headers.get(name)
                )
                print(f"payment settled: {settle}")


if __name__ == "__main__":
    main()
