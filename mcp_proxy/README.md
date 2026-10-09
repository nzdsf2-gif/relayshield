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

## Config scanner (free)

Before deploying the proxy, scan your MCP client config for security
issues. The scanner reads Claude Desktop style configs and flags:

- Hardcoded secrets (API keys, tokens, private keys) in env vars and args
- Filesystem servers rooted at `/` or your home directory
- Server versions with known advisories (e.g. mcp-server-git prompt
  injection before the 2025-12-08 fix)
- Remote servers with no authentication configured
- Servers that expose dangerous tools (shell exec, broad file write)

```bash
python3 -m mcp_proxy.scanner                      # auto-detect config
python3 -m mcp_proxy.scanner /path/to/config.json
python3 -m mcp_proxy.scanner --format json         # machine-readable
python3 -m mcp_proxy.scanner --ci                 # for CI pipelines
```

Findings are color-coded by severity (CRITICAL red, HIGH orange,
MEDIUM yellow, LOW blue) with remediation advice for each. Exit code
1 when CRITICAL or HIGH findings exist, so it works in CI.

Fix what the scanner finds, then deploy the proxy for runtime
protection of every tool call.

## Demo

Watch the proxy catch a poisoned neighbor in real time, no network
required. The demo wires the real Screener, NeighborRegistry,
QuarantineManager, and VerdictSigner in-process against two simulated
MCP servers (one clean, one poisoned) and streams every screening
step: argument screening, per-check result screening (prompt
injection, secret material, kit fingerprints, unredacted PII, novel
instruction phrasing), signed verdicts, reputation escalation, and
auto-quarantine after 3 flags.

```bash
python3 -m mcp_proxy.demo          # streaming, ~30 seconds
python3 -m mcp_proxy.demo --fast   # no delays
```

TI URL lookups are stubbed in demo mode; all content checks run the
real local detectors. Scenarios 7-9 cover OAuth attacks: tampered
OAuth URLs blocked on arguments, credential exfiltration flagged in
tool results, and legitimate IdP endpoints passing clean.

## Visual dashboard

A live HTML dashboard for partner demos. When the proxy is running,
open `http://localhost:8090/_rs/dashboard` in a browser: it polls
`/_rs/neighbors` every 2 seconds and shows neighbor reputations,
quarantine events, a live screening feed, and verdict-signing status.

For a standalone visual demo without a live proxy:

```bash
python3 -m mcp_proxy.dashboard --demo
# then open http://127.0.0.1:8091/_rs/dashboard
```

The dashboard is a single self-contained HTML file (inline CSS/JS,
no external dependencies).

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
- **Poison categories:** every screening verdict carries a
  `poison_category` taxonomy field, included in signed verdicts, MCP
  error responses, and structured logs. Categories, highest severity
  first: `credential_exfiltration` (OAuth/JWT material bound for
  non-IdP infrastructure) > `kit_match` (scam-kit fingerprint) >
  `malicious_url` (TI hit) > `oauth_tampering` (OAuth flow on a
  foreign, unaffiliated domain) > `prompt_injection` (known phrases)
  > `secret_leak` (private keys/credentials) > `pii_leak` (unredacted
  PII) > `unknown_synthetic` (novel instruction-like phrasing with
  no known pattern match; placeholder for the Phase 3 classifier)
  > `clean`.
  When several detections fire, the highest-severity category wins.
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
python3 -m unittest mcp_proxy.test_oauth -v      # OAuth: 26 tests
python3 -m unittest mcp_proxy.test_scanner -v   # scanner: 16 tests
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

## OAuth flow protection

Catches the OAuth discovery-tampering attack class disclosed against
MCP SDKs in 2026: a malicious server alters the OAuth flow so the
victim's login still runs at the legitimate identity provider while
credentials are redirected to attacker infrastructure.

- **Endpoint validation** (`mcp_proxy/oauth.py`): OAuth URLs in tool
  call arguments and tool results are checked against known identity
  providers (Google, GitHub, Microsoft, Auth0, Okta, including
  wildcard tenants). An IdP-specific path (or any OAuth flow) on a
  foreign, unaffiliated domain is `oauth_tampering` and blocks the
  call. Toggle: `MCP_PROXY_OAUTH_SCREENING` (default true).
- **Credential exfiltration**: tool results are scanned for JWTs,
  authorization codes, PKCE verifiers, and client secrets. When this
  material appears bound for non-IdP infrastructure it is flagged as
  `credential_exfiltration` (highest severity). Matched credential
  values are never logged or returned; only pattern types, counts,
  and destination domains appear in verdicts. Query strings are
  stripped from URLs in reasons via `redacted_url`.
- **New-domain caution**: OAuth flows toward plausible first-party
  auth hosts with no reputation history are flagged as
  `unknown_synthetic` (medium severity, caution only, no block).

Run the OAuth tests:

```bash
python3 -m unittest mcp_proxy.test_oauth -v   # 26 tests
```

## Phase 3: Behavioral baselining and reputation graph

Learns normal tool call patterns per agent and flags deviations, plus
maintains per-server reputation scores for the dashboard graph.

- **Behavioral baselining** (`mcp_proxy/behavior.py`): per-agent
  profiles track tool frequencies, tool bigrams (consecutive pairs),
  and hourly call distributions. Flags volume anomalies (10x baseline
  rate), sequence anomalies (never-seen tool transitions), and time
  anomalies (calls outside normal hours). Toggle:
  `MCP_PROXY_BEHAVIOR` (default true).
- **Attack chain detection**: matches known malicious sequences
  within a 2-minute window: `read` to `network` to `email` (data
  exfiltration), rapid calls across 5+ servers (lateral movement),
  and injection-flagged responses followed by privileged tools
  (escalation). Flagged as `poison_category: attack_chain`.
- **Risk scoring**: 0-100 per-agent score, decays with a 10-minute
  half-life. Scores at or above `MCP_PROXY_BEHAVIOR_QUARANTINE_SCORE`
  (default 80.0) trigger quarantine evaluation.
- **Server reputation graph** (`mcp_proxy/reputation.py`): per-server
  scores 0-100 (higher is more trustworthy). Bands: trusted (70+),
  watch (40-69), untrusted (below 40). Scores drop on TI hits (-25),
  flags (-10), quarantines (-40), and attack chains (-20); they
  recover slowly on clean operation. Served at `GET /_rs/reputation`
  with per-server score history for the dashboard graph.
- **New poison categories**: `behavioral_anomaly` (rank 6) and
  `attack_chain` (rank 9) added to the taxonomy.

Run the Phase 3 tests:

```bash
python3 -m pytest mcp_proxy/test_behavior.py mcp_proxy/test_reputation.py -v
```

Try the new demo scenarios (10-12) in the interactive dashboard:

```bash
python3 -m mcp_proxy.dashboard --demo
# open http://127.0.0.1:8091/_rs/dashboard
```
