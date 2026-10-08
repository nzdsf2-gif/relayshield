# RelayShield Scam Checks for Gemini CLI

Free scam checks for links, wallets, emails, and breach exposure, inside
Gemini CLI. No signup, no API key.

## Install

```bash
gemini extensions install github:nzdsf2-gif/relayshield --ref feature/gemini-cli-extension
```

Or, once merged to main:

```bash
gemini extensions install github:nzdsf2-gif/relayshield
```

Note: this installs the `relayshield-scam-checks` extension from the
`gemini-cli-extension/` directory of the RelayShield monorepo.

## What it does

Registers RelayShield's public MCP server
(`https://relayshieldadmin-relayshield-free-mcp.hf.space/mcp`) with Gemini CLI
and bundles a `scam-check` skill so the agent knows when to screen suspicious
input.

## Checks

- Link and URL screening against the RelayShield threat-intel corpus
- Crypto wallet scam and exposure checks
- Email breach and scam-association checks
- Credential and identifier breach exposure

## Skill

The bundled `scam-check` skill (`skills/scam-check/SKILL.md`) teaches the
agent when to invoke these tools and how to report tri-state outcomes
(BLOCKED, FLAGGED, ALLOWED).

## Links

- RelayShield developers and API keys: https://api.relayshield.net/developers
- Extension gallery: https://geminicli.com/extensions
