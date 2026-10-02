---
title: "What your XSOAR playbook cannot see about an identity, and the pack that adds it"
slug: what-an-xsoar-playbook-cannot-see-about-an-identity
date: 2026-10-01
---

# What your XSOAR playbook cannot see about an identity, and the pack that adds it

RelayShield's content pack is now on master in Palo Alto Networks' `demisto/content` repository, under `Packs/RelayShield`. It went through the contribution review, then through Palo Alto's own internal pipeline, and it is there now. Palo Alto's team told us in writing that a merged pack gets a Marketplace listing page and a mention in their Release Notes. We will link both here when we can see them.

This post is about why a SOC would want it. It is not a list of commands.

## The question an enrichment playbook usually cannot answer

A standard enrichment playbook takes an indicator and asks reputation sources about it. For a domain or an IP that works well. For an identity it mostly does not, because the interesting question is different: **has the credential behind this person already been stolen, and is the stolen session still alive?**

That is not a property of a hash or a URL. It lives in places a reputation feed does not read: infostealer log dumps traded in criminal Telegram channels, breach corpora, and the registration history of lookalike domains. An analyst triaging an impossible-travel alert for `jsmith@example.com` needs to know whether that mailbox appears in a fresh stealer log before deciding whether to revoke sessions or close the ticket.

## What the pack adds

The generic reputation commands `domain`, `ip` and `email` are invoked automatically by any enrichment playbook that already calls generic reputation commands. You do not edit a playbook to pick RelayShield up as one more source. Three further commands do things a reputation call does not:

- `relayshield-mcp-registry-risk` checks an MCP server URL or package name for typosquat, supply-chain and registry risk before an agent connects to it.
- `relayshield-supply-chain` reports combined breach and infostealer risk across up to ten vendor domains or emails in one call.
- `relayshield-cert-expiry` reports TLS certificate expiry risk for a domain.

Setup is a self-serve API key from the developers page and a configured integration instance. There is no subscription requirement.

## The scoring decision we want you to check

This is the part of the pack we care most about getting right, and the part a reviewer should read.

A clean result does **not** map to Good. It maps to **Unknown (0)**. Critical and high findings map to Bad (3). Medium and low findings map to Suspicious (2).

The reason is how playbooks aggregate. Many playbooks treat "all sources clean" as a reason to auto-close. If a source can only say "nothing flagged in the places I looked", then scoring that as Good lets an absence of evidence act as a vote of confidence, and it does so in exactly the playbooks that close tickets without a human. So RelayShield never contributes a clean vote. Only a genuine finding moves the aggregate.

That is a deliberate cost to us: a source that never says "good" looks less decisive. We would rather be less decisive than quietly auto-close a real compromise.

## What it does not do

It does not analyse binaries, replace your EDR, or tell you an identity is safe. It tells you when something is known against an identity or a counterparty, and it says so plainly when nothing is. We do not quote a corpus size here, because most headline numbers in this industry are dominated by public feeds you already subscribe to, and what matters for triage is whether the specific thing in front of you is known.

## Try it

The pack and its README are in the `Packs/RelayShield` directory of the `demisto/content` repository. An API key and the integration documentation are at [api.relayshield.net/developers](https://api.relayshield.net/developers?source=xsoar).
