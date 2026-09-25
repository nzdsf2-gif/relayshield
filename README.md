# relayshield-mcp

<!-- mcp-name: io.github.nzdsf2-gif/relayshield-mcp -->

`mcp-name: io.github.nzdsf2-gif/relayshield-mcp`

[RelayShield](https://relayshield.net) security intelligence as an MCP server — plug breach detection, SIM swap detection, domain lookalike monitoring, OAuth supply chain watchlist, and URL/file scanning directly into Claude and any MCP-compatible AI agent.

## Tools

| Tool | What it does | PAYG price |
|---|---|---|
| `check_breach` | Email breach lookup — 13 billion+ compromised-account records | $0.10 USDC |
| `check_sim_swap` | SIM swap / eSIM detection via live carrier data | $0.25 USDC |
| `check_domain_lookalikes` | Typosquat and lookalike domain detection with cert transparency | $0.50 USDC |
| `check_oauth_watchlist` | OAuth-app breach + stolen-token exposure from the stealer-log corpus | $0.30 USDC |
| `check_infostealer` | Infostealer malware log lookup — credentials harvested from infected devices | $0.15 USDC |
| `scan_wallet` | EVM wallet on-chain risk check | $0.10 USDC |
| `scan_url` | URL malware/phishing scan across 70+ engines (async) | $0.05 USDC |
| `scan_file` | Binary malware scan across 70+ AV engines (async) | $0.10 USDC |
| `check_scan_result` | Poll for verdict after `scan_url` / `scan_file` | free |
| `check_mcp_registry_risk` | Typosquat/IOC/registration-age check for MCP servers | $0.35 USDC |
| `check_prompt_injection_breach` | Breach exposure sourced from AI-agent prompt-injection attacks | $0.35 USDC |
| `check_supply_chain` | Up to 10 vendor domains checked for breach/infostealer exposure | $0.10 USDC |
| `check_session_risk` | Active/reusable stolen session (cookie/token) exposure check | $0.30 USDC |
| `check_nhi_exposure` | Non-human-identity credential exposure — API keys, service tokens, PATs | $0.40 USDC |
| `check_secret_scan` | Secrets exposed in public GitHub repositories | $0.35 USDC |

`check_oauth_watchlist`, `check_supply_chain`, `check_session_risk`, `check_nhi_exposure`, and
`check_secret_scan` cover related ground — connected-app, session, and machine-credential exposure
for an identity or its supply chain — and are a natural set to use together when vetting an agent's
current authority, not just a login.

## Access modes

**Subscription** — API key from [api.relayshield.net/developers](https://api.relayshield.net/developers). All 15 tools available. Free tier: 100 calls/month. Paid tiers from $29/month.

**Pay-as-you-go** — No API key needed. Pay per check in USDC on Base (x402 protocol). Set `RELAYSHIELD_X_PAYMENT` with your payment proof. All 15 tools available ($0.05–$0.50/check, `check_scan_result` free). Call a tool with no payment set to receive pricing and payment instructions.

**Discovery** — Set neither key nor payment. Tool calls return payment requirements and a subscription link.

## Install

```bash
pip install relayshield-mcp
```

Or run without installing:

```bash
uvx relayshield-mcp
```

## Configure Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

**Subscription (RelayShield API key):**
```json
{
  "mcpServers": {
    "relayshield": {
      "command": "relayshield-mcp",
      "env": {
        "RELAYSHIELD_API_URL": "https://api.relayshield.net",
        "RELAYSHIELD_API_KEY": "your-relayshield-api-key-here"
      }
    }
  }
}
```

**Pay-as-you-go (x402 USDC on Base):**
```json
{
  "mcpServers": {
    "relayshield": {
      "command": "relayshield-mcp",
      "env": {
        "RELAYSHIELD_API_URL": "https://api.relayshield.net",
        "RELAYSHIELD_X_PAYMENT": "your-x402-payment-proof-here"
      }
    }
  }
}
```

Quit and relaunch Claude Desktop after editing.

## Configure Claude Code (CLI)

```bash
claude mcp add relayshield \
  --command relayshield-mcp \
  --env RELAYSHIELD_API_URL=https://api.relayshield.net \
  --env RELAYSHIELD_API_KEY=your-relayshield-api-key-here
```

## Free checks server (no key, no signup)

`relayshield-free-mcp` ships in the same package and exposes RelayShield's free,
keyless threat-intel checks as four MCP tools. It is the funnel into the paid
server above: every summary links the deeper paid checks where they apply.

| Tool | What it does | Key needed |
|---|---|---|
| `check_link` | Screen 1–25 URLs for phishing/malware (IOC corpus + threat feeds + domain age) | no |
| `check_wallet` | Screen a crypto wallet before paying it (chain auto-detected) | no |
| `check_email` | Score a suspicious email for phishing signals; checks its links too | no |
| `check_breach` | Email vs 13B+ breached accounts | partner key only |

```bash
pip install relayshield-mcp
# or: uvx relayshield-mcp
relayshield-free-mcp
```

**Claude Desktop** — add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "relayshield-free": {
      "command": "relayshield-free-mcp",
      "env": {
        "RELAYSHIELD_API_URL": "https://api.relayshield.net",
        "RS_SOURCE_TAG": "mcp-free-claude"
      }
    }
  }
}
```

**ChatGPT** — ChatGPT connects to MCP servers through Developer Mode
connectors, which require a remote HTTP endpoint; it does not launch a local
stdio server. A hosted RelayShield MCP endpoint is planned — until then, use
Claude Desktop, Claude Code, Cursor, or any other stdio-capable MCP client.
Set `RS_SOURCE_TAG=mcp-free-chatgpt` once the hosted endpoint is live so usage
is attributed to the ChatGPT channel. `check_breach` stays disabled until a
partner key is set via `RELAYSHIELD_API_KEY`.

**Partner keys** — distributors (Claude, ChatGPT, registries) each get their own
RelayShield partner key with a per-key daily call cap, set via
`RELAYSHIELD_API_KEY`. Separate keys per channel mean one channel's abuse never
takes down the others, and `RS_SOURCE_TAG` attributes usage per channel. The
server runs fine without any key — link, wallet, and email checks stay keyless
on the free tier.

## Usage examples

Once configured, ask Claude:

```
Check whether user@example.com has been breached.
```

```
Has there been a SIM swap on +14155551234?
```

```
Check acme.com for lookalike domains.
```

```
Are any OAuth apps connected to user@example.com in a recent breach?
```

```
Scan this URL for malware: https://suspicious-link.example.com
```

For URL and file scans, Claude automatically polls `check_scan_result` every 5 seconds until the verdict is ready.

## Environment variables

| Variable | Description |
|---|---|
| `RELAYSHIELD_API_URL` | API Gateway base URL (required) |
| `RELAYSHIELD_API_KEY` | RelayShield subscription key (subscription mode) — get one at [api.relayshield.net/developers](https://api.relayshield.net/developers) |
| `RELAYSHIELD_X_PAYMENT` | x402 payment proof — USDC on Base (pay-as-you-go mode) |

Set `RELAYSHIELD_API_KEY` **or** `RELAYSHIELD_X_PAYMENT` — not both. API key takes priority if both are set.

## Links

- [Landing page](https://relayshield.net)
- [Get an API key](https://api.relayshield.net/developers)
- [GitHub](https://github.com/relayshield/relayshield-mcp)
- [Telegram bot / miniApp](https://t.me/relayshield_bot) — free scam checks in chat
- [WhatsApp scam-check bot](https://wa.me/17407373961) — message a link, wallet, or email
