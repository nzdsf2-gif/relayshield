---
title: "Your wallet agent moves real money. Give it a firewall."
slug: "2026-11-13-hosted-mcp-proxy-firewall"
date: "2026-11-13"
---

A wallet agent is an agent with a bank account. It sends funds, swaps tokens, and signs batched contract calls, all on your behalf, all at machine speed. That is the point of building one. It is also the risk. A single malicious MCP server, or a single poisoned tool call slipped into an otherwise normal session, can drain a wallet before a human notices anything is wrong. The agent does not get a second chance to check. The call either goes through or it does not.

Today we are launching the RelayShield Hosted MCP Proxy Firewall. It sits between your wallet agent and its MCP servers and screens every write call before it reaches the wallet.

Here is how it works.

**1. Every write call is screened first.** When your agent issues a send, a swap, or a batched contract call, the Firewall checks it against two things before it goes anywhere near the wallet. First, RelayShield's live threat intelligence corpus: 139 monitored Telegram marketplaces, 800K+ indicators, 10.9M citations. If the counterparty, the contract, or the destination is known to the corpus, the call is flagged or blocked. Second, your tenant's intent binding: the action has to match what you actually authorized. A call that drifts from the bound intent does not go through.

**2. It works with the wallets you already use.** The Firewall supports Coinbase Wallet MCP and the MetaMask Agent Wallet (Embedded Wallets MCP). Your agent connects to the Firewall the same way it would connect to any MCP server. The Firewall forwards the screened calls to the wallet upstream. No changes to your agent code beyond pointing it at your Firewall URL.

**3. It is hosted, not self-hosted.** Every paying tenant gets a dedicated EC2 instance, single tenant by construction. Your instance has its own URL, your-tenant-id.proxy.relayshield.net, with TLS handled by Caddy and a per-tenant proxy token checked on every request. There is nothing to install, nothing to patch, nothing to keep running. You subscribe, you get your URL and your token, you point your agent at it.

**4. The verifiers close the loop.** A screened call is only half the story. The Agent Verifiers Bundle adds TAP Verifier, Passport identity, intent binding, and settle check, so the agent you are paying through is the agent you think it is, the intent is bound before the call, and the settlement is checked after it. The bundle is $79 per month standalone, with 100 free verifications per month. Pair it with the Firewall and the combined license is $109 per month, which saves $19 against buying them separately.

Pricing is flat and monthly. The Firewall is $49 per month for a direct single-tenant subscription, with 20,000 screened calls included and $0.002 per call above that. For MSPs, it is $69 per month per client org, with the same 20,000 screened calls per org. The combined Firewall plus Agent Verifiers Bundle is $109 per month for a direct developer.

The Hosted MCP Proxy Firewall is launching now. If you are building a wallet agent on Base or MetaMask, start at api.relayshield.net/developers. Questions: support@relayshield.net.
