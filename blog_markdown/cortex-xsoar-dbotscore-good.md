---
title: RelayShield's Agentic Attack Surface Intelligence Now Ships as a Cortex XSOAR Content Pack
slug: cortex-xsoar-dbotscore-good
date: 2026-09-30
---

# RelayShield's Agentic Attack Surface Intelligence Now Ships as a Cortex XSOAR Content Pack

An agent that reads a repository's setup instructions, connects to an MCP server, or follows a
tool's README is extending trust to whatever domain, package or command those instructions name.
Nothing else in the Cortex XSOAR content marketplace looks at that trust before the agent acts on
it. RelayShield does, and as of this release a SOC or MSSP running Cortex XSOAR, XSIAM or the
Cortex platform can pull that intelligence straight into an incident without building anything.

## What nothing else in the marketplace runs

Three commands answer questions specific to the agentic attack surface, not the general reputation
questions every other feed already covers:

- `relayshield-mcp-registry-risk` assesses an MCP server URL or package name for typosquat,
  supply-chain or registry risk before an agent connects to it. This is the same logic behind our
  agent-bait screening, exposed as a command a SOC can run against anything an agent is about to be
  pointed at.
- `relayshield-cert-expiry` checks a domain's TLS certificate expiry risk, which matters for the
  same reason: a certificate quietly expiring on infrastructure an agent depends on is an outage an
  automated system will not notice on its own.
- `relayshield-supply-chain` checks up to ten vendor domains or emails in one call for combined
  breach and infostealer risk, sized for the shape a vendor-risk review actually comes in.

## The part that costs nothing to adopt: it's the format your playbooks already speak

The pack also implements the generic `domain`, `ip` and `email` reputation commands. That is the
part that matters operationally as much as the agentic-specific commands do: any enrichment
playbook already calling those three commands picks up RelayShield the moment the integration is
enabled and a reliability weight is set. No rewiring, no new playbook logic, no waiting for a
custom integration to be written and reviewed. `domain` checks phishing-lookalike and typosquat
risk; `email` checks breach exposure and active stolen-session risk, the thing a password reset
does not fix; `ip` checks reputation against malicious and suspicious votes.

One design decision inside that mapping is worth knowing before you configure it: a clean result
from any of these commands sets DBotScore to Unknown (0), never Good (1). "No known finding" means
nothing was flagged in the sources RelayShield queried, which is a narrower claim than
verified-safe, and a reputation integration that conflates the two is telling an analyst something
it does not actually know.

| RelayShield verdict | DBotScore |
|---|---|
| CRITICAL | 3 (Bad) |
| HIGH | 3 (Bad) |
| MEDIUM | 2 (Suspicious) |
| LOW | 2 (Suspicious) |
| No known finding | 0 (Unknown) |

## Where the intelligence comes from

RelayShield's corpus is collected continuously from monitored criminal Telegram marketplaces,
infostealer log dumps, and authoritative public indicator feeds: 123 monitored channels and 8.3
million citations as of this release. The first two categories are the ones a standard TAXII feed
subscription does not reach, and they are the reason a RelayShield hit on an indicator is worth
pulling into the incident rather than filed alongside everything else. We quote specific, measured
figures like these when they are current and worth knowing; what we do not do is lean on a single
aggregate corpus headline, since most of any threat-intel vendor's total volume is ingested public
feeds a SOC already has through other packs, and the number that actually matters is what is in it
that those feeds are not.

## Setup

Category: Data Enrichment & Threat Intelligence. Requires Cortex XSOAR 6.8.0 or later, and it also
ships for Cortex XSIAM and the Cortex platform. Configuration takes a Server URL (defaults to
`api.relayshield.net`) and a RelayShield API key. Get a free-tier key at
[api.relayshield.net/developers](https://api.relayshield.net/developers?source=xsoar-blog), then
follow the [full integration reference](https://xsoar.pan.dev/docs/reference/integrations/relay-shield)
for every command's inputs and context outputs.

Free checks that need no key at all, if you want to see a verdict before configuring anything:
forward a suspicious email to
[checkemail@relayshield.net](mailto:checkemail@relayshield.net), or paste a link or a wallet
address into [the checker in Telegram](https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-blog).
