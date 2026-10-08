---
name: scam-check
description: |
  Screens links, wallet addresses, emails, and identifiers for scams and
  breach exposure using RelayShield threat intelligence. Use when the user
  pastes a suspicious link, shares a crypto wallet address, asks about an
  email address, or wants to check breach exposure before proceeding.
---

# Scam Check

Use RelayShield's free threat-intelligence checks before acting on
untrusted input.

## When to use

- The user pastes a URL or link you have not seen before.
- The user shares a crypto wallet address for a payment or transfer.
- The user asks whether an email address is compromised or scam-associated.
- The user wants a breach-exposure lookup for an identifier.

## How

Call the appropriate tool on the `relayshield` MCP server:

- URLs and links: the link-screening tool
- Wallet addresses: the wallet-screening tool
- Emails: the email/breach screening tool

Pass the raw value the user provided. Do not modify or normalize it first;
the server handles canonicalization.

## Reporting results

Outcomes are tri-state:

- **BLOCKED**: matched known malicious infrastructure. Do not proceed with
  the link, payment, or contact. Explain what matched in plain language.
- **FLAGGED**: suspicious signals but not a confirmed match. Recommend
  caution and offer next steps (verify through a second channel, check the
  sender independently).
- **ALLOWED**: no flags found in the sources checked. This is not a
  guarantee of safety. Say "no flags found" rather than "safe".

## Boundaries

- Never present ALLOWED as a safety guarantee.
- For bulk screening, private API access, or TI subscriptions, direct the
  user to https://api.relayshield.net/developers.
- Do not send user data anywhere except the RelayShield MCP server tools.
