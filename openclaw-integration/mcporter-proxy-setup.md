# Routing mcporter Through the RelayShield Proxy Firewall

This guide covers manual setup for users who prefer not to install the ClawHub skill. The skill (`skills/relayshield-mcp-firewall/SKILL.md`) automates these steps.

## The idea

mcporter connects to MCP servers by URL. The RelayShield proxy is an HTTP server that speaks MCP (JSON-RPC 2.0) and forwards screened requests upstream. So you run the proxy locally and tell mcporter the proxy's address instead of the real server's address.

```
Before:  mcporter -> https://upstream-mcp-server.example.com/mcp
After:   mcporter -> http://127.0.0.1:8090 -> https://upstream-mcp-server.example.com/mcp
                           (proxy screens here)
```

## 1. Start the proxy

```bash
git clone https://github.com/nzdsf2-gif/relayshield.git
cd relayshield
MCP_PROXY_UPSTREAM="https://your-mcp-server.example.com/mcp" \
MCP_PROXY_PORT="8090" \
python3 -m mcp_proxy
```

Leave this running. One proxy instance per upstream server; use a different `MCP_PROXY_PORT` for each.

## 2a. Register via mcporter CLI

```bash
mcporter config add myserver http://127.0.0.1:8090 --scope home
mcporter list myserver
```

If `mcporter list` prints tool metadata, the chain works.

## 2b. Register via mcporter.json directly

If your mcporter version has different `config add` flags, write the config file directly. Default location is `~/.openclaw/workspace/config/mcporter.json`:

```json
{
  "mcpServers": {
    "myserver": {
      "baseUrl": "http://127.0.0.1:8090",
      "headers": {}
    }
  }
}
```

For an upstream server that requires auth, keep the credential out of mcporter. The proxy forwards requests upstream; configure any upstream Authorization header in the proxy's environment or policy file instead, so the secret never lives in the agent's config.

## 3. Pre-scan before you connect (recommended)

```bash
cd relayshield
python3 -m mcp_proxy.tool_scanner --url https://your-mcp-server.example.com/mcp
python3 -m mcp_proxy.tool_scanner --url https://your-mcp-server.example.com/mcp --ci
```

The second form exits 1 on HIGH or CRITICAL findings, so it works in CI. Scan first, fix findings, then route traffic through the proxy.

## 4. Confirm screening is active

Check the proxy log for the startup line:

```
MCP proxy listening on :8090, upstream=https://your-mcp-server.example.com/mcp, screening=true
```

`screening=true` confirms TI screening is on. To verify end to end, run the offline demo (14 attack scenarios, no network required):

```bash
python3 -m mcp_proxy.dashboard --demo
# open http://127.0.0.1:8091/_rs/dashboard
```

## Reference

- Full proxy configuration: `mcp_proxy/README.md` in the RelayShield repo
- Proxy env vars: `mcp_proxy/config.py` (all settings are environment variables)
- Pre-deployment scanner: `python3 -m mcp_proxy.tool_scanner --help`
- Config scanner (client setup mistakes): `python3 -m mcp_proxy.scanner --help`
- Pricing and API keys: https://api.relayshield.net/developers
