# 5 Crypto Security Signals in One API Call — Wallet Risk, Token Honeypots, SIM Swap and More

If you're building a crypto app, a trading bot, a DeFi dashboard, or an AI agent that touches wallets or tokens, you need security signals baked in — not bolted on after something goes wrong.

RelayShield Security Intelligence is a single REST API that gives you:

- **Wallet risk scoring** — multi-chain (EVM, Solana, TON)
- **Token honeypot + rug pull detection** — before your users ape in
- **NFT contract risk scanning** — ownership, minting, verification flags
- **SIM swap detection** — live carrier-layer data via Twilio Lookup v2
- **Email breach checking** — 13B+ compromised records

No SDKs. Plain JSON in, plain JSON out. Available on RapidAPI (subscription) or x402 USDC micropayments on Base (pay per call, no subscription needed).

---

## Quickstart — Wallet Risk in Python

```python
import requests

url = "https://relayshield-security-intelligence.p.rapidapi.com/v1/wallet-risk"

payload = { "address": "0xYourWalletAddress" }
headers = {
    "x-rapidapi-key": "YOUR_RAPIDAPI_KEY",
    "x-rapidapi-host": "relayshield-security-intelligence.p.rapidapi.com",
    "Content-Type": "application/json"
}

response = requests.post(url, json=payload, headers=headers)
print(response.json())
```

Works with EVM addresses, Solana public keys, and TON wallet addresses — the API auto-detects chain type.

---

## Quickstart — Token Security (Honeypot Check)

```python
payload = {
    "chain_id": "1",  # Ethereum mainnet — use 8453 for Base
    "contract_address": "0xTokenContractAddress"
}

response = requests.post(
    "https://relayshield-security-intelligence.p.rapidapi.com/v1/token-security",
    json=payload,
    headers=headers
)
print(response.json())
```

Returns honeypot status, buy/sell tax flags, ownership renounced, hidden owner, and more — powered by GoPlus Security.

---

## Pay Per Call with x402 (No Subscription Needed)

If you're building an agent or a low-volume integration and don't want a monthly subscription, the PAYG endpoints accept x402 USDC micropayments on Base:

| Endpoint | Price |
|---|---|
| `/v1/payg/wallet-risk` | $0.15 USDC |
| `/v1/payg/token-security` | $0.10 USDC |
| `/v1/payg/nft-security` | $0.10 USDC |
| `/v1/payg/wallet-screen-batch` | $0.50 USDC (up to 10 addresses) |
| `/v1/payg/breach` | $0.10 USDC |
| `/v1/payg/sim-swap` | $0.25 USDC |

x402 flow:
1. Call the endpoint with no payment header → receive `402` + `PAYMENT-REQUIRED`
2. Pay USDC on Base to the address in the response
3. Retry with `X-PAYMENT` header containing payment proof
4. API verifies via Coinbase x402 facilitator → returns result

---

## Use Cases

- **DeFi dashboard** — screen every inbound token for honeypots automatically
- **Trading bot** — run wallet-risk on counterparties before executing swaps
- **AI agent** — give your Claude/GPT agent live security intelligence via MCP or direct API
- **Wallet app** — alert users when their SIM is swapped before their 2FA is compromised
- **Portfolio tracker** — flag high-risk wallets and scam tokens in real time

---

## MCP Server (Claude / AI Agents)

If you're building with Claude or want to use these signals inside Claude Desktop:

```bash
pip install relayshield-mcp
```

Exposes all endpoints as native MCP tools — no API calls to write.

---

## Links

- **RapidAPI listing** (subscribe + test in browser): [RelayShield Security Intelligence](https://rapidapi.com/relayshield/api/relayshield-security-intelligence)
- **API docs + landing page**: [relayshield.net](https://relayshield.net)
- **MCP package**: [pypi.org/project/relayshield-mcp](https://pypi.org/project/relayshield-mcp)

Built by a 25-year telecom security professional. Questions welcome in the comments.
