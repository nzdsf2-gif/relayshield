# RelayShield — Talking Points for AWS Sales Call (Friday, 30 min)

*Goal: give him enough to (1) understand what we do and why it's a real AWS-native business, (2) see the telco-specific angle given his focus, and (3) know exactly what to introduce us to.*

---

## The 30-second pitch

RelayShield detects identity attacks — credential breaches, infostealer log exposure, SIM swap / carrier-level account takeover, phishing domains, OAuth token theft — **while the attack is still forming**, not after. Founder background: 25 years in telecom security. The carrier-layer detection (SIM swap, port-out fraud) is the core differentiator — nobody else does this at SMB-accessible pricing, and it's a genuinely telecom-native problem, not a bolt-on.

Live, self-funded, real paying customers. Fully built on AWS.

---

## Why this is a real AWS-native business, not just "hosted on AWS"

- **Compute**: Lambda + API Gateway for everything — no other cloud dependency for core infrastructure. Two Lambdas split the workload: `relayshield-api` (main REST API, 20+ endpoints) and an isolated `relayshield-agentic-api` for the newer AI-agent-security product line.
- **Data**: DynamoDB across the board — user records, API keys, breach/SIM-swap alert history, and a live threat-intel corpus (3M+ IOC indicators, 4,500+ malware families, 40+ monitored criminal Telegram channels feeding it).
- **Why that matters to him**: every dollar of RelayShield revenue is AWS committed spend. This isn't a company that happens to have an EC2 instance somewhere — the entire product is AWS-native by construction.

## What's already live on AWS Marketplace (not "coming soon")

1. **TI Subscription — flat-rate SaaS, live today.** "RelayShield - Threat Intelligence & Identity Security API" (`prod-kb3ftelx44wlk`). $499/mo (10,000 API calls) or $999/mo (unlimited). Straightforward flat-rate billing through AWS — no metering infrastructure required on the buyer's side.
2. **Metered Consumption Bundles — contract-with-consumption pricing**, same product entity as our Bundle D listing (`prod-kkvurtspreofy`):
   - **Bundle D "Agentic Attack Surface"** — live/approved, $275/mo minimum. Built for AI-agent governance use cases (checking AI agents' credential exposure, MCP tool registry risk, prompt-injection-sourced breaches).
   - **Bundles A/B/C** — Core Identity Exposure, Attack Surface & Supply Chain, Advanced Risk Correlation ($150/$100/$200/mo minimums). Code shipped, AWS-side rollout in progress.
   - This is the "buy exactly the signal set you need" tier for MSPs/MSSPs and mid-market buyers, vs. the flat TI subscription for teams that want everything.

## The differentiated technical story: Bedrock AgentCore + CDP

Real, independently-verified proof (not a demo, not a mockup): an autonomous AI agent running on **Amazon Bedrock AgentCore** (Claude Sonnet via Strands, using the official `AgentCorePaymentsPlugin`) discovered RelayShield through **Coinbase Developer Platform's own x402 Bazaar** — wired in as a native AgentCore Gateway MCP target — and **autonomously paid for a real security check with real USDC**, settled on Base mainnet, confirmed via direct blockchain RPC. Done twice: once locally, once from a fully deployed AgentCore Runtime with zero local dependency. No custom payment client — entirely AWS-managed tooling (Gateway + Payments + Runtime).

Why this matters for him specifically: **AgentCore Payments is still in Preview** — AWS needs real usage proof for it, and this is a rare, concrete, on-chain-verifiable example of "AI agents autonomously paying other AI agents/services," which is exactly the story AWS is trying to tell about agentic AI on their platform right now.

## Why the telco angle specifically

- Founder's background is 25 years in telecom security — this isn't a generic security vendor bolting on a "carrier" feature.
- SIM swap / port-out fraud detection queries the carrier in real time (Twilio Lookup v2) — this is squarely inside telco fraud/security budgets, not a stretch pitch.
- Enterprise SIM swap monitoring elsewhere starts at $10K+/year; RelayShield delivers equivalent carrier-level detection at SMB-accessible pricing — a genuinely different price point for the same signal telcos already understand.

## The actual ask

1. **Introductions to telco accounts** he thinks would value proactive identity/SIM-swap monitoring — either as a direct AWS Marketplace purchase or an MSP/MSSP reselling motion.
2. **Introductions to other AWS sales colleagues**, particularly anyone else touching telco or MSP/MSSP accounts, in Canada or elsewhere.
3. Any informal guidance on **ISV Accelerate** — we're actively working toward the eligibility threshold (5 closed + 15 qualified ACE opportunities, $2K+ recognized AWS revenue), and early opportunity introductions from him would directly help get there. Once enrolled, deals he influences are attributable back to him — this is a two-way ask, not just "help us for free."

---

*One-liner if he wants something to forward internally: "RelayShield — carrier-layer identity threat detection built by a 25-year telecom security veteran, fully AWS-native (Lambda/DynamoDB), live on AWS Marketplace today (flat-rate + consumption bundles), with a verified Bedrock AgentCore + CDP agentic-payments proof."*
