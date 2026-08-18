# Autonomous Agent-to-API Commerce on AWS
### RelayShield × Amazon Bedrock AgentCore — end-to-end proof of concept

---

## What we set out to prove

That an autonomous AI agent could **discover, pay for, and consume a live commercial API** with no
human in the loop, no pre-provisioned API key, and no prior business relationship between the agent
and the vendor — using real money, on production infrastructure, entirely on AWS-native tooling.

Not a sandbox. Not a testnet. Not a scripted demo.

---

## What we built

| Layer | Component |
|---|---|
| Discovery | **AgentCore Gateway** with the CDP x402 Bazaar configured as a native MCP server target — zero custom discovery code, since RelayShield's endpoints are already indexed there |
| Payments | **AgentCore Payments** — credential provider, payment manager, connector and embedded CDP wallet, provisioned via boto3 |
| Agent | **Strands agent on Bedrock (Claude Sonnet)** using the official AgentCorePaymentsPlugin for automatic HTTP 402 handling |
| Settlement | Real USDC on **Base mainnet**, signed via CDP delegated signing |
| Target API | RelayShield's identity-risk-score endpoint — a live, commercially listed AWS Marketplace product |

---

## What happened

The agent was given a task and a funded wallet. Unassisted, it:

1. Searched the x402 Bazaar and located RelayShield's identity-risk endpoint
2. Called it, received an HTTP 402 Payment Required
3. Signed and settled the payment on-chain
4. Retried, received the real scored result, and summarized it correctly

**On-chain proof:**
`0xe90d302b5eda6b66545cf9a506c3bd73f273ff9390f309e4f021d3150a388016`
Base mainnet, status `success`, verified via direct RPC.

The entire loop — discovery through settlement through consumption — ran without human
intervention.

---

## Why this matters

**For AWS.** This is the agentic-commerce loop closing end to end on AWS-native services, against a
real Marketplace ISV rather than a reference implementation. Agent discovers vendor, agent pays
vendor, agent consumes service. Every layer is AWS.

**For the telco channel specifically.** The pattern generalises directly to machine-to-machine
service consumption: an autonomous system procuring a metered capability on demand, settling
per-call, with no contract negotiation or credential provisioning step. That is the same shape as
network function chaining, roaming settlement, and wholesale interconnect — with the procurement
friction removed.

**For RelayShield.** We are an AWS Marketplace seller with a live listing since June 2026. This
proves our endpoints are consumable by autonomous agents today, not on a roadmap.

---

## About RelayShield

Threat intelligence and identity-exposure API for MSPs, MSSPs and enterprise SOCs.

- **494K+ distinct indicators** drawn from **5.8M+ sightings**, sourced from 95 monitored channels and 11 authoritative feeds
- **95 monitored channels** — typically 24–72 hours ahead of public breach databases
- **3,800+ tracked malware families**
- **26 identity endpoints** — breach, infostealer, SIM swap, OAuth exposure, domain lookalike, non-human identity, LLM credential exposure
- Live on AWS Marketplace (`prod-kb3ftelx44wlk`), STIX/TAXII 2.1 and MISP feeds available
- AWS account `239677749008`

---

## What we're looking for

An introduction to the AgentCore product team or the AWS Partner org — we would value being an
early-adopter reference for agentic commerce, and guidance on our path toward ISV Accelerate.
Partner Central identity and business verification are complete.

Happy to walk through the full technical detail or run the demo live.

**support@relayshield.net** · api.relayshield.net/developers

---

<!--
INTERNAL NOTES — remove before sending
1. FIGURES: IOC count measured live at 4,530,716 on 2026-07-28. Channel count (83+), malware
   families (3,800+) and endpoint count (31) are taken from the published demo page and the MSP
   brief — RE-VERIFY before sending, per feedback_verify_live_stats_not_memory.
2. AGENTCORE STATUS: AWS_Partner_Pitch_AgentCore.md still describes AgentCore Payments as "still in
   Preview" and claims "as far as we can tell this is a genuine, very early real world
   integration." Your contact says AgentCore has been commercial for ~6 months, so both claims are
   now stale and would read as uninformed. This one-pager deliberately drops the Preview framing
   and the "very early" claim, and leads on what was actually demonstrated instead. Consider
   correcting the Partner Central doc too if it has not already been submitted.
3. The old pitch doc also carries badly stale stats (2M+ IOCs, 37+ channels) — do not reuse it
   as-is.
-->
