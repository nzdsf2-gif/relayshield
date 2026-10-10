# OpenClaw Integration: RelayShield MCP Proxy Firewall

Routes OpenClaw's MCP traffic (via the mcporter bridge) through the RelayShield Proxy Firewall, screening every tool call and tool result against threat intelligence before it reaches the agent.

## Why this exists

OpenClaw agents pull tools from ClawHub and third-party MCP servers. The ClawHavoc incident showed 800+ malicious skills reaching agents through exactly this channel. The proxy sits at the chokepoint between mcporter and upstream servers: the one place every tool call and response must pass through.

## Contents

- `skills/relayshield-mcp-firewall/SKILL.md`: ClawHub skill. Copy into `~/.openclaw/workspace/skills/relayshield-mcp-firewall/` (or publish to ClawHub). Walks the user through starting the proxy and re-pointing mcporter.
- `mcporter-proxy-setup.md`: Manual setup guide for users who prefer not to install the skill. Same steps, no skill required.
- `proxy_mcporter.py`: Helper script that rewrites an existing mcporter.json so every HTTP upstream routes through a local proxy instance. Stdio servers pass through unchanged.

## Quick start

```bash
# 1. Pre-scan the upstream server (offline, no proxy needed)
python3 -m mcp_proxy.tool_scanner --url https://your-mcp-server.example.com/mcp

# 2. Start the proxy
MCP_PROXY_UPSTREAM="https://your-mcp-server.example.com/mcp" \
MCP_PROXY_PORT="8090" \
python3 -m mcp_proxy

# 3. Point mcporter at the proxy
mcporter config add myserver http://127.0.0.1:8090 --scope home
mcporter list myserver
```

Or generate a fully proxied config in one step:

```bash
python3 openclaw-integration/proxy_mcporter.py \
  --in ~/.openclaw/workspace/config/mcporter.json \
  --out ~/.openclaw/workspace/config/mcporter.proxied.json \
  --port-base 8090
# then start one proxy per server on the printed ports
```

## Status

Preparation for partner outreach. Not yet submitted to ClawHub. The proxy itself is on main (`mcp_proxy/`); this directory holds the OpenClaw-specific integration layer.
