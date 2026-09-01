# RelayShield

**One-line (for the `modelcontextprotocol/servers` table):**

RelayShield — check a wallet, email, URL or credential against identity-compromise and criminal-source threat intelligence before an agent acts on it.

**Short description (mcp.so, Smithery):**

RelayShield gives an agent four checks it cannot safely make on its own: whether a
wallet address has criminal counterparty exposure, whether an email appears in a
breach, whether its credentials are in infostealer logs, and whether a URL is
known-malicious. Each returns a verdict the agent can branch on, so a workflow can
refuse to pay, refuse to connect, or refuse to send before the irreversible step,
rather than reporting the loss afterwards.

Free tier needs no card. Per-call pricing is available over x402 for agents that
pay for themselves.

**Tools**

- `relayshield_check_wallet` — counterparty risk for a wallet address (EVM, Solana, TON, Bitcoin)
- `relayshield_check_breach` — breach exposure for an email address
- `relayshield_check_infostealer` — whether credentials for an email appear in stealer logs
- `relayshield_scan_url` — URL reputation against RelayShield's IOC corpus, Google Safe Browsing and VirusTotal

**Links** (every one carries the attribution key)

- Docs: https://api.relayshield.net/developers?source=mcp-registry
- Home: https://relayshield.net?source=mcp-registry
