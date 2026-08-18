# x402 directory submissions

Checked live 2026-08-08: neither directory listed RelayShield, despite us being registered on
x402scan (59 of 60 resources) and having awesome-x402 PR #1154 open. agent-tools.cloud claims to
aggregate from x402scan, awesome-x402 and CDP Bazaar, so the aggregation did not pick us up and a
direct self-submission is needed.

All values below are verified against the live 402 challenge on
`POST https://api.relayshield.net/v1/payg/wallet-risk`, not from memory.

---

## 1. agent-tools.cloud

**Founder action.** The in-app browser blocks this host by policy, so paste it yourself.

Form: `https://agent-tools.cloud/submit`, the **x402 Service** form. No login, free.

| Field | Value |
|---|---|
| Name * | `RelayShield` |
| URL * | `https://api.relayshield.net/v1/payg/wallet-risk` |
| Category | `Security` |
| Price (USDC / call) | `0.05` |
| Chains | `Base, Solana` |
| Contact email * | `support@relayshield.net` |

Description:

> Screen a wallet address across EVM, Solana, TON, or Bitcoin for known scam, exploit, drainer, or
> sanctions-list association before your agent transacts with it. Returns a risk level, specific
> risk flags, and a freshness contract stating how long the verdict can be cached. One of 28 x402
> endpoints covering wallet screening, credential and breach exposure, infostealer logs, lookalike
> domains and SIM swap risk.

The freshness sentence is deliberate. It is the one thing in that description no competing listing
says, and a directory entry is read by agents and by people skimming for a differentiator.

**Worth also submitting the MCP Server form** while you are there, since we run a real remote MCP
server and it is a separate listing on the same site:

| Field | Value |
|---|---|
| Endpoint URL * | the HuggingFace Space MCP endpoint (`hf-space-mcp-server/app.py`, Gradio `mcp_server=True`) |
| Name | `RelayShield Agentic Attack Surface` |
| Transport | SSE |
| Contact email * | `support@relayshield.net` |

Confirm the listing by loading `https://agent-tools.cloud/x402` and searching the rendered page for
"relayshield". Do not trust a submission confirmation screen; that is how the Hashnode silent
unpublish went unnoticed twice.

---

## 2. PipRail

**Not a form.** Registration is `client.register()` in their SDK, described as "one POST, no auth"
against a default target called **402 Index**. The raw HTTP endpoint and payload are not documented,
so this needs `npm i` and a short Node script rather than a paste. Deferred as its own task.

Registration is asynchronous and returns a visibility status of `live`, `pending-review` or
`not-listable`. There is an expedited path via domain verification that needs no credentials, only
serving a file, which we can do trivially on a Cloudflare Worker.

Fields to use, same as above: `name`, `category: security`, `priceUsd: 0.05`, `asset: USDC`,
`description`, and tags `wallet-screening`, `crypto-security`, `defi`, `identity`, `x402`.
Their docs call `category` "the #1 findability lever", so do not leave it blank.

---

## 3. 402 Index, newly surfaced

PipRail's default registration target is a directory in its own right. Not yet investigated, and we
are presumably not on it either. Check separately.

---

## Verified listing facts

| | |
|---|---|
| Flagship endpoint | `POST https://api.relayshield.net/v1/payg/wallet-risk` |
| Price | $0.05 USDC |
| Networks | Base `eip155:8453`, Solana `solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp` |
| Base payTo | `0x002CfD89c5636F45E3C8576D6E35154748412bAc` |
| Solana payTo | `E64PiTT7U8ZUWFKdkrBFw1YzdD2bU1gKcuGnBRVqp7M6` |
| Total x402 endpoints | 28 |
| Tags on the live resource | `defi`, `wallet-screening`, `crypto-security` |
