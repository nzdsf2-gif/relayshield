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
| `MCP_PROXY_RESULT_SCREENING` | `true` | Screen upstream tool results for poisoned content |
| `MCP_PROXY_QUARANTINE_AFTER` | `3` | Flags before a server is auto-quarantined |
| `MCP_PROXY_ALERT_WEBHOOK` | (empty) | Webhook URL for quarantine/flag alerts (POST JSON) |

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

## Phase 2: poisoned neighbor detection

The proxy tracks the reputation of each upstream MCP server:

- **Registration:** each upstream's domain is TI-screened on first sight.
- **Result screening:** every `tools/call` response is checked for
  prompt-injection phrases, embedded malicious URLs, leaked secret
  material, scam-kit fingerprints, and unredacted PII (SSN, credit
  card via Luhn, bulk email). PII verdicts carry pattern types and
  counts only; matched values are never logged or returned. Flagged
  responses mark the server suspicious (fail-open: the response still
  reaches the caller, but the flag is recorded). Toggle with
  `MCP_PROXY_PII_SCREENING` (default true).
- **Quarantine:** after `MCP_PROXY_QUARANTINE_AFTER` flags (default 3),
  the server is auto-quarantined. Quarantined servers get zero traffic
  (fail-closed) until cleared.
- **Admin:** `GET /_rs/neighbors` lists server reputations;
  `POST /_rs/neighbors/clear {"url": ...}` clears a quarantine.
  `GET /_rs/health` is a liveness check.

## Tests

```bash
python3 -m unittest mcp_proxy.test_proxy -v      # Phase 1: 19 tests
python3 -m unittest mcp_proxy.test_neighbor -v  # Phase 2/2.5: 43 tests
```

Covers: indicator extraction, screener verdicts (block/allow/fail-open),
proxy passthrough for `initialize`/`tools/list`/`tools/call`, blocked
call error format, and proxy overhead under 50ms.

## Phase 1 scope

Passthrough + TI screening on tool call arguments.

## Phase 2 scope

Poisoned neighbor detection: upstream reputation tracking, tool result
screening (prompt injection, malicious URLs, secret material, unredacted
PII), auto-quarantine with per-server fail-closed enforcement.

## Phase 2.5 scope: barbed wire

Signed verdicts plus kit fingerprint integration make the proxy's
decisions cryptographically provable and tied to RelayShield's TI
corpus. A copied proxy without the live backend and signing key
produces verdicts nobody can verify.

- **Signed verdicts** (`mcp_proxy/verdicts.py`): every block/flag
  decision gets an Ed25519 signature (pure-Python RFC 8032, zero
  dependencies). The private key comes only from `MCP_PROXY_SIGNING_KEY`
  (64 hex chars); it is never logged. Without a key, verdicts are
  unsigned but still carry full TI evidence.
- **Kit fingerprints**: tool results are scanned for `kit_<sha256>`
  IDs. Matches are included in verdict evidence as
  `kit_fingerprint` entries, optionally enriched via the
  `/v1/payg/scamkit-match` API (`MCP_PROXY_KIT_LOOKUP=true`).
- **Evidence-backed quarantine**: quarantine events carry structured
  TI evidence (`{"type", "id", "detail"}`), visible via
  `GET /_rs/neighbors`. The verdict public key is published at
  `GET /_rs/neighbors` (`verdict_pubkey`) for partner verification.
per-server quarantine (fail-closed), admin endpoints. Not yet built:
behavioral baselining, cross-tool correlation, policy enforcement.
See the MCP Proxy build scope doc for the full roadmap.
