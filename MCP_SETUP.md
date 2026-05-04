# RelayShield MCP Server — Setup Guide

## What this does

The RelayShield MCP server exposes your 5 security intelligence tools as callable
functions that Claude (and any other MCP-compatible AI agent) can invoke directly
during a conversation — without the user having to copy-paste curl commands.

Example: "Check whether example@gmail.com has been breached" → Claude calls
`check_breach` → returns breach list inline in the conversation.

---

## Tools exposed

| Tool | What it does |
|---|---|
| `check_breach` | Email breach lookup (HIBP) |
| `scan_url` | URL malware scan — returns analysis_id |
| `scan_file` | File malware scan — returns analysis_id |
| `check_scan_result` | Poll for verdict after scan_url / scan_file |
| `check_sim_swap` | SIM swap detection (Twilio) |
| `check_domain_lookalikes` | Typosquat / lookalike domain detection |

---

## Step 1 — Install dependencies

```bash
pip install mcp httpx
```

Or add to `requirements.txt`:
```
mcp>=1.0.0
httpx>=0.27.0
```

---

## Step 2 — Get your values

You need two values from your AWS setup:

**API URL** — API Gateway → APIs → relayshield-api → Stages → prod → Invoke URL
```
https://xhh3tfrhng.execute-api.us-east-1.amazonaws.com/prod
```

**API Key** — API Gateway → API Keys → relayshield-test-key → API key value (the long string, not the ID)

---

## Step 3 — Configure Claude Desktop

Open (or create) `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "relayshield": {
      "command": "/Users/andrewgibbs/anaconda3/bin/python3",
      "args": ["/Users/andrewgibbs/Side SaaS Hustle/relayshield_mcp_server.py"],
      "env": {
        "RELAYSHIELD_API_URL": "https://xhh3tfrhng.execute-api.us-east-1.amazonaws.com/prod",
        "RELAYSHIELD_API_KEY": "YOUR_API_KEY_VALUE_HERE"
      }
    }
  }
}
```

Replace `YOUR_API_KEY_VALUE_HERE` with your actual key value (the long string).

**Then quit and relaunch Claude Desktop.**

In the bottom-left of a new conversation you should see a hammer icon — click it to
confirm the 6 RelayShield tools are listed.

---

## Step 4 — Configure Claude Code (CLI)

Add the MCP server to your Claude Code project settings:

```bash
claude mcp add relayshield \
  --command python3 \
  --args "/Users/andrewgibbs/Side SaaS Hustle/relayshield_mcp_server.py" \
  --env RELAYSHIELD_API_URL=https://xhh3tfrhng.execute-api.us-east-1.amazonaws.com/prod \
  --env RELAYSHIELD_API_KEY=YOUR_API_KEY_VALUE_HERE
```

Or add to `.claude/settings.json` in the project directory (same JSON structure as above).

Verify with:
```bash
claude mcp list
```

---

## Step 5 — Test it

Start a Claude Desktop conversation and try:

```
Check whether test@example.com has been breached.
```

```
Check if the domain acme.com has any lookalike domains registered.
```

```
Has there been a SIM swap on +14155551234?
```

For URL/file scans (async — Claude will poll automatically):
```
Scan this URL for malware: https://google.com
```

---

## Step 6 — Verify the server runs standalone

Before trusting it in Claude, verify the server launches cleanly:

```bash
cd "/Users/andrewgibbs/Side SaaS Hustle"
RELAYSHIELD_API_URL="https://xhh3tfrhng.execute-api.us-east-1.amazonaws.com/prod" \
RELAYSHIELD_API_KEY="YOUR_KEY" \
python3 relayshield_mcp_server.py
```

It should block (waiting for stdio input) with no errors. Press Ctrl+C to exit.

---

## For developers using your API

Publish this server so MSPs and developers can add RelayShield tools to their own
Claude agents. Distribution options:

### Option A — PyPI package (recommended)

Wrap in a `pyproject.toml`, publish to PyPI as `relayshield-mcp`.
Developers install with:
```bash
pip install relayshield-mcp
```

Claude Desktop config becomes:
```json
{
  "mcpServers": {
    "relayshield": {
      "command": "relayshield-mcp",
      "env": {
        "RELAYSHIELD_API_URL": "https://...",
        "RELAYSHIELD_API_KEY": "their-api-key"
      }
    }
  }
}
```

### Option B — npx-style (uvx)

Publish to PyPI and developers run without installing:
```bash
uvx relayshield-mcp
```

### Option C — GitHub README

Link to this repo/file in your RapidAPI listing. Developers clone and configure.

---

## Pricing note for MCP users

MCP calls hit your API Gateway exactly like curl — each tool call counts against
the customer's usage plan quota. A developer using Claude Desktop with RelayShield
MCP configured will consume API calls from their RapidAPI subscription.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Tools not visible in Claude Desktop | Quit fully (Cmd+Q) and relaunch — not just close the window |
| `{"ok": false, "error": "RELAYSHIELD_API_URL..."}` | Env vars not set — check claude_desktop_config.json |
| `{"ok": false, "error": "Network error"}` | Wrong API URL or API key — verify both in AWS console |
| scan_url / scan_file returns `pending` | Normal — Claude should call check_scan_result every 5 seconds |
| `ModuleNotFoundError: mcp` | Run `pip install mcp httpx` |
