---
title: Why Our Cortex XSOAR Integration Never Sets DBotScore to Good
slug: cortex-xsoar-dbotscore-good
date: 2026-09-30
---

# Why Our Cortex XSOAR Integration Never Sets DBotScore to Good

RelayShield is now a Cortex XSOAR content pack, and the one design decision inside it worth
reading before the setup steps is a mapping table most vendors would have written the other way.

A clean result from any of our commands maps to DBotScore **Unknown (0)**, never **Good (1)**.
That is not an oversight. "No known finding" means nothing was flagged in the sources RelayShield
actually queried, which is not the same claim as verified-safe. A domain that has never been
reported is not the same thing as a domain that has been checked and cleared, and a reputation
integration that conflates the two is telling an analyst something it does not know.

## What it plugs into, with no new playbook work

The pack implements the generic `domain`, `ip` and `email` reputation commands, which is the part
that matters operationally: any enrichment playbook already calling those commands picks up
RelayShield the moment the integration is enabled and a reliability weight is set. Nothing to
rewire.

| RelayShield verdict | DBotScore |
|---|---|
| CRITICAL | 3 (Bad) |
| HIGH | 3 (Bad) |
| MEDIUM | 2 (Suspicious) |
| LOW | 2 (Suspicious) |
| No known finding | 0 (Unknown) |

`domain` checks for phishing-lookalike and typosquat risk against our IOC corpus. `email` checks
breach exposure and active stolen-session risk, the thing a password reset does not fix: whether a
session token was taken, which no rotation revokes. `ip` checks reputation against malicious and
suspicious votes. All three set the score above; none of them set Good.

## Three commands nothing else in the marketplace runs

Past the generic three, the pack carries commands with no equivalent we're aware of in the Cortex
XSOAR content marketplace, because they answer questions specific to what RelayShield collects:

- `relayshield-mcp-registry-risk` assesses an MCP server URL or package name for typosquat,
  supply-chain or registry risk before an agent connects to it. This is the same check behind our
  agent-bait screening: an agent that reads a repository's setup instructions and follows them is
  trusting whatever domain those instructions name, and this command is how a SOC checks that
  domain before the agent does.
- `relayshield-cert-expiry` checks a domain's TLS certificate expiry risk.
- `relayshield-supply-chain` checks up to ten vendor domains or emails in one call for combined
  breach and infostealer risk, sized for the shape a vendor-risk review actually comes in.

## Where the indicators come from, stated as capability rather than a count

We do not quote a corpus headline, here or anywhere. Most of any threat-intel vendor's total is
ingested public feeds a SOC already has through other packs, and the number that actually matters
is what is in it that those feeds are not. Our corpus is collected continuously from monitored
criminal Telegram marketplaces, infostealer log dumps, and authoritative public indicator feeds.
The first two categories are the ones a standard TAXII feed subscription does not reach, and they
are the reason a RelayShield hit on an indicator is worth pulling into the incident rather than
filed alongside the rest.

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
