# RelayShield MCP Proxy Firewall

A transparent proxy that sits between MCP clients (AI agents) and MCP
servers, screening tool calls against RelayShield's threat intelligence
corpus before forwarding.

## How it works

```
Agent → [MCP Proxy :8090] → Upstream MCP Server
              |
        TI screening per tools/call
```

1. Agent connects to the proxy as if it were the MCP server.
2. `initialize` and `tools/list` pass through untouched.
3. `tools/call`: the proxy extracts URLs, domains, and IPs from the
   tool arguments and screens them via RelayShield's composite-check API.
4. Flagged calls are blocked with an MCP error response.
5. Clean calls are forwarded to the upstream server.

## Quick start

```bash
export MCP_PROXY_UPSTREAM="https://your-mcp-server.example.com/mcp"
export MCP_PROXY_PORT="8090"
python3 -m mcp_proxy
```

Point your MCP client at `http://localhost:8090`.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `MCP_PROXY_UPSTREAM` | (required) | Upstream MCP server URL |
| `MCP_PROXY_PORT` | `8090` | Port to listen on |
| `MCP_PROXY_SCREENING` | `true` | Set `false` for pure passthrough |
| `RELAYSHIELD_API_URL` | `https://api.relayshield.net` | TI API base |
| `RELAYSHIELD_API_KEY` | (empty) | Optional; enables deeper checks |
| `MCP_PROXY_SCREEN_TIMEOUT` | `5.0` | TI check timeout in seconds |
| `MCP_PROXY_BLOCK_LEVELS` | `high,medium` | Verdict levels that block |

## Screening behavior

- Extracts URLs, domains, and IPv4 addresses from tool arguments
  (recursive, cycle-safe, capped at 10 URLs per call).
- Screens via the keyless `/v1/composite-check` API.
- Blocks on `high` (and `medium` by default). `unknown` never blocks.
- If the TI API is unreachable, calls are allowed through (fail-open)
  and the failure is logged.

## Logging

Every proxied call emits a structured JSON log line:

```json
{"event": "tools_call", "tool": "fetch", "verdict": "block",
 "level": "high", "score": 95, "reasons": ["phishing kit"],
 "screen_ms": 120.5, "total_ms": 135.2, "screening_enabled": true}
```

## Tests

```bash
python3 -m unittest mcp_proxy.test_proxy -v
```

Covers: indicator extraction, screener verdicts (block/allow/fail-open),
proxy passthrough for `initialize`/`tools/list`/`tools/call`, blocked
call error format, and proxy overhead under 50ms.

## Phase 1 scope

Passthrough + TI screening. Not yet built: behavioral baselining,
poisoned-neighbor detection, cross-tool correlation, policy enforcement.
See the MCP Proxy build scope doc for the full roadmap.
