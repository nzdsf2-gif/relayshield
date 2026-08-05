# AWS Bedrock AgentCore + x402 Bazaar — Launch Announcement Copy
*All channels. Ready to post. Anchor date: land before the OrcX/Gary call, Thursday 2026-07-16.*

The hook is the real thing that shipped, not a borrowed news cycle: a Bedrock-hosted AI agent autonomously found one of RelayShield's live security APIs through Coinbase's own discovery registry, paid for it, and got a real result — with a real, independently-verifiable transaction on Base mainnet, running entirely on AWS's own managed infrastructure. That's evergreen and doesn't need the JadePuffer news cycle to land (which has largely closed since 2026-07-09).

---

## Main narrative post (LinkedIn — post first)

```
We just proved something we've been building toward for a while: an AI agent that autonomously finds and pays for a security check, with no human in the loop, using only AWS's and Coinbase's own infrastructure.

Here's what actually happened. We built a Bedrock agent using AWS's new AgentCore Runtime and Gateway. We pointed its Gateway at Coinbase's own x402 Bazaar — a public discovery registry where paid APIs list themselves for AI agents to find. RelayShield's threat-intelligence endpoints are indexed there. We gave the agent one instruction: find a service that checks a domain's identity risk, and pay for it if you find one.

It searched the Bazaar, found our identity-risk-score endpoint, signed a real payment using Coinbase's delegated-signing wallet infrastructure, and settled it on-chain. Transaction hash: 0x1cb95ce37d54201b4def745269c42790fdb9bc7255f102aa648cf6f91fab0e3a on Base — verifiable by anyone, no trust required.

No custom payment code. No custom discovery code. Just AWS Bedrock AgentCore Payments, AgentCore Gateway, and Coinbase's x402 protocol, wired together the way they're meant to be used.

Why this matters for security specifically: as AI agents start acting autonomously — researching, transacting, calling tools — they become an attack surface nobody's really built defenses for yet. Malicious MCP servers. Prompt-injection breaches. Compromised agent credentials. RelayShield's identity-risk API is now itself discoverable and payable by exactly the kind of autonomous agent it's built to help secure.

23 of our 24 API endpoints are now indexed in Coinbase's x402 Bazaar. Any AI agent built on AWS Bedrock AgentCore — or any x402-compatible agent framework — can find and pay for them today, no partnership or integration required.

api.relayshield.net/developers

#ArtificialIntelligence #AWS #Cybersecurity #Web3 #AIAgents
```

---

## Shorter version (Telegram / Farcaster)

```
Shipped: an AI agent on AWS Bedrock AgentCore autonomously found and paid for one of our threat-intel APIs through Coinbase's x402 Bazaar — real USDC, real on-chain settlement, zero custom payment code.

tx: 0x1cb95ce37d54201b4def745269c42790fdb9bc7255f102aa648cf6f91fab0e3a (Base)

23 of 24 RelayShield endpoints are now discoverable and payable by any AI agent on AWS or x402-compatible frameworks — no integration needed on their end. This is what "agentic attack surface" defense looks like when the defender is also agent-native.

relayshield.net

#AI #Web3 #x402 #AWS
```

---

## Mastodon (character-limited, security/infosec audience)

```
An AI agent on AWS Bedrock AgentCore just autonomously found and paid for one of our security APIs via Coinbase's x402 Bazaar. Real on-chain payment, zero custom code, verifiable tx:

0x1cb95ce37d54201b4def745269c42790fdb9bc7255f102aa648cf6f91fab0e3a (Base)

As agents start transacting autonomously, they become an attack surface. We built the security layer to be agent-native too — 23/24 endpoints now agent-discoverable + payable.

#infosec #AI #x402

api.relayshield.net/developers
```

---

## Technical blog post — full draft (the durable, canonical piece — publish first, link to it from everything else)

**Platform: Hashnode** (RelayShield's actual existing blog, 9 posts so far — post #10, may trigger the planned Cloudflare Pages migration per `BLOG-CF-PAGES`). **Cross-post to Paragraph** (crypto-native audience, already used successfully once before for the QR-code AI article) and **Medium** (established cross-post target per prior launches).

### Publishing metadata

- **Display title**: "We Proved an AI Agent Can Find and Pay for a Security API With Zero Custom Code"
- **SEO title** (Hashnode has a separate field, ~60 char budget — pack it with the searchable terms the display title trades away): "AWS Bedrock AgentCore + Coinbase x402 Bazaar: Real Agent Payment"
- **Meta description** (~155 chars): "An AI agent on AWS Bedrock AgentCore autonomously found and paid for a live security API via Coinbase's x402 Bazaar — real on-chain settlement, zero custom code."
- **Slug**: `aws-bedrock-agentcore-x402-bazaar-autonomous-agent-payment`
- **Tags** (Hashnode caps around 5 — pick for search volume + precision, not cleverness): `ai`, `web3`, `aws`, `cybersecurity`, `blockchain`
- **Cover image**: none generated here — a screenshot of the Basescan tx or a simple architecture diagram (Gateway → Bazaar → Payments → wallet) would work; don't block publishing on this, Hashnode allows adding it after the fact.

### Full post body

*(Copy everything below this line through the end of the curl command — do not include any triple-backtick fence lines, there aren't any at the top level anymore.)*

We just proved something we've been building toward for a while: an AI agent that autonomously finds and pays for a security check, with no human in the loop, using only AWS's and Coinbase's own infrastructure — not a local script, not a sandboxed demo, a real transaction on Base mainnet that anyone can verify right now.

## The setup

Two pieces of infrastructure make this possible, both new enough that most builders haven't touched them yet.

**AWS Bedrock AgentCore** is AWS's managed runtime for autonomous agents. Two parts of it matter here: **AgentCore Gateway**, which lets an agent discover and call tools through the Model Context Protocol (MCP) without you writing custom integration code, and **AgentCore Payments**, which gives an agent its own wallet and lets it sign and settle payments on an agent's behalf, gated behind AWS's own consent and credential-provider infrastructure.

**Coinbase's x402 Bazaar** is a public discovery registry for the x402 protocol — a way for APIs to say "this costs $0.01 per call, and here's how to pay in USDC" directly in an HTTP 402 response. The Bazaar is where those APIs list themselves so agents can search for them, the same way a package registry lets a build tool search for a library.

RelayShield's threat-intelligence API is one of the services listed there.

## What we built

We wired an AgentCore Gateway directly to Coinbase's own x402 Bazaar as a native MCP server target — no custom discovery code, because the Bazaar already speaks MCP. We gave the agent an AgentCore Payments session backed by an embedded CDP wallet, funded with a small amount of real USDC on Base. We built a Strands agent (AWS's agent framework) using the official `AgentCorePaymentsPlugin`, which handles the entire "you got a 402, here's how to pay it" exchange automatically. Then we gave the agent one instruction: find a service that checks a domain's identity risk, and pay for it if you find one.

No custom payment client. No custom discovery layer. Every piece is AWS and Coinbase's own tooling, wired together the way it's meant to be used.

## The bug we found and fixed along the way

While wiring this up, we hit something worth documenting on its own: our endpoints kept settling real payments successfully, but never showed up in Bazaar search results. Settlement succeeded; discovery silently failed, with no error anywhere.

The root cause: RelayShield's entire wire protocol is x402 **V1**-shaped (`x402Version: 1`, string-typed network fields, `maxAmountRequired`). V1's Bazaar discovery metadata has to live in a top-level `outputSchema` field on each `accepts` entry — a sibling of `scheme`, `network`, and `payTo` — not inside an `extensions.bazaar` wrapper, which is a V2-only convention. We'd been declaring the metadata in a field no V1-aware extractor ever reads. We documented the full root cause in [x402-foundation/x402#2844](https://github.com/x402-foundation/x402/issues/2844), and once we moved the metadata to the correct field, indexing worked immediately and now generalizes across our whole catalog.

One honest update since we opened that issue: a maintainer replied noting that V1 is deprecated — V2 has been live for over seven months, and while most facilitators still support V1 today, that isn't guaranteed indefinitely. We're scoping our migration to V2 now. We're glad this finding is useful to other V1 sellers in the meantime, and we'll follow up in that thread once the migration ships.

## The proof

The agent searched the Bazaar, found RelayShield's `identity-risk-score` endpoint, signed a real payment through Coinbase's delegated-signing wallet infrastructure, and settled it on-chain: `0xe90d302b5eda6b66545cf9a506c3bd73f273ff9390f309e4f021d3150a388016` on Base, verifiable by anyone.

Then we took it a step further and deployed the same agent to a live AgentCore Runtime — a real, AWS-hosted container, not a script on a laptop — and ran the same test again. Same result, second independent transaction, second independent proof: `0x1cb95ce37d54201b4def745269c42790fdb9bc7255f102aa648cf6f91fab0e3a` on Base. Getting there required fixing two real infrastructure bugs along the way: `MCPClient`'s initialization has to happen at module-import time, not lazily inside an async request handler, since it can't start inside an already-running asyncio event loop; and the Runtime's own execution role needed broader permissions to invoke its own Gateway, since Gateway-to-MCP invocation is a raw SigV4-signed HTTP call with no dedicated boto3 API method.

Both transactions are permanent, independently verifiable, on-chain facts — not something either of us can undo or overstate.

## Why this matters for security

As agents start acting autonomously — researching, transacting, calling tools on their own initiative — they become an attack surface nobody has really built defenses for yet: malicious MCP servers, prompt-injection breaches, compromised agent credentials, poisoned tool ecosystems. RelayShield's identity-risk API is now itself discoverable and payable by exactly the kind of autonomous agent it exists to help secure. A security vendor building for an agentic world should be agent-native and agent-payable itself, not just agent-aware.

## What's next

23 of our 24 API endpoints are now confirmed indexed in Coinbase's x402 Bazaar (Base and Solana each). Any AI agent built on AWS Bedrock AgentCore — or any x402-compatible agent framework — can find and pay for them today, no partnership or integration required on their end.

Don't take our word for any of this. Query the Bazaar yourself:

\`\`\`bash
curl https://api.cdp.coinbase.com/platform/v2/x402/discovery/search?query=relayshield
\`\`\`

---

## Directory / community submissions (cheap, targeted builder audience — do alongside the main posts)

- **`Merit-Systems/awesome-agentic-commerce`** (GitHub — plain markdown list, no CONTRIBUTING.md required. Add one line under the `### Ecosystem` section, same style as existing entries like Strale/CardZero. PR-based.)
- **`x402-list.com`** (real web submission form at `x402-list.com/submit` — confirmed, no GitHub involved.)
- **PWN Hacker Substack community** (900+ security practitioners, per existing `INTEL-PAWN-1` plan — cross-post the blog post's angle there, following their stated submission process.)
- All three are low-effort, high-relevance — the exact audiences actively looking for real x402 services or security-practitioner content to engage with.

---

## Sequencing (mirrors the rollout pattern used for the Crypto Shield launch)

| Day | Action | Channel |
|---|---|---|
| Day 1 (target: 2026-07-14 or 07-15) | Publish the technical blog post first (durable canonical link) | Hashnode |
| Day 1, same day | Cross-post | Paragraph, Medium |
| Day 1, same day | Main narrative post, linking to the blog post | LinkedIn |
| Day 1 evening | Shorter version | Farcaster |
| Day 2 | Telegram post | t.me/RelayShield |
| Day 2 | Mastodon post | Mastodon |
| Day 2-3 | Directory + community submissions | awesome-agentic-commerce PR, x402-list.com, PWN Hacker Substack |
| Day 3 (2026-07-16) | OrcX/Gary call — reference the announcement as a live, citable proof point | — |
