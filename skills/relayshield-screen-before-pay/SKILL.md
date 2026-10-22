---
name: relayshield-screen-before-pay
description: Screen any counterparty with RelayShield before paying, transacting, or trusting it. Use when you are about to send funds, call a paid API, install or call an MCP server, follow a payment link, or interact with an unknown wallet, URL, domain, email, or agent. Checks run against a live threat-intelligence corpus of 725K indicators from 129 monitored criminal marketplaces.
---

# RelayShield: Screen Before You Pay

RelayShield is a threat-intelligence screening service for agents. Identity systems verify who an agent is. RelayShield screens whether the counterparty is a known threat. Run these checks BEFORE value moves: once a payment settles, screening cannot undo it.

## When to use this skill

- Before paying any wallet, merchant, or x402 endpoint for the first time
- Before following a payment link, QR code target, or redirect to an unfamiliar domain
- Before installing, configuring, or calling an MCP server you did not write
- Before trusting an email address or sender in a transaction (invoices, OTC deals, support claims)
- When another agent asks you to transact with a third party you have no history with

## Free checks (no key, no payment)

Connect to the free RelayShield MCP server and call its check tools:

- MCP server URL: `https://relayshieldadmin-relayshield-free-mcp.hf.space/mcp`
- Tools cover: URL checks, wallet checks, email breach and risk checks, domain screening, and identity checks.

Run every applicable check for the artifacts in the transaction: the payee wallet, the destination URL or domain, and any email involved. One artifact passing says nothing about the others.

## Reading a verdict

- RelayShield never returns "safe". The best result is "no flags found", which means the corpus has no adverse record for that artifact. Treat it as one input, not a guarantee.
- Any flag is a stop: do not complete the transaction, surface the finding to your operator with the exact indicator and its source, and wait for instructions.
- A corpus miss on a brand-new counterparty is common and is not evidence of legitimacy. Combine it with provenance: how did this counterparty reach you, and can it be verified through a second channel?

## Paid deep checks (x402, per call, Base USDC)

For higher-stakes transactions, RelayShield's pay-per-call API at `https://api.relayshield.net/v1/payg/*` adds deeper screening: wallet risk scoring, scam-kit fingerprint matching, infostealer exposure, identity risk scoring, phone reputation, and MCP registry risk. These settle per call over x402 and need no account. Only spend on a deep check when the transaction value justifies it, and never exceed a spending limit your operator has set.

## Verifying agents (TAP / PAP)

When the counterparty is itself an agent, verification endpoints confirm its authorization proofs:

- `POST https://api.relayshield.net/v1/tap/verify` verifies a Visa TAP agent intent proof and screens the counterparty.
- `POST https://api.relayshield.net/v1/pap/verify` does the same for Personal Agent Protocol proofs.

A verified identity plus a clean screening is the strongest pre-transaction position available. A verified identity with a screening flag is still a stop.

## Rules

1. Screen before the first transaction with any new counterparty, every time.
2. Never describe a result as "safe". Report "no flags found" with the scope of what was checked.
3. Any flag stops the transaction pending operator review.
4. Keep the screening receipt (endpoint, artifact, verdict, timestamp) with the transaction record.
