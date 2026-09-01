# MCP registry listings — FD-3

Submission material for listing the RelayShield MCP server in the public MCP
registries. Written 2026-09-01.

**Why this front door, and not a bigger one first.** We already ship an MCP
server, and `mcp-registry-risk` is a paid endpoint whose entire subject is which
MCP servers are safe to connect to. Being absent from the registries our own
product scores is the weakest position available: it is the one directory where
a listing is both free distribution and a credibility argument.
`RelayShield_Strategy.md` has flagged `modelcontextprotocol/servers` as the
"highest-priority new candidate" and it has not been done.

## What the server actually exposes

Taken from `relayshield/mcp-server/src`, not from a description — four tools:

| Tool | What it does |
|---|---|
| `relayshield_check_wallet` | Counterparty risk on a wallet address |
| `relayshield_check_breach` | Breach exposure for an email |
| `relayshield_check_infostealer` | Whether credentials appear in stealer logs |
| `relayshield_scan_url` | URL reputation against the IOC corpus, GSB and VirusTotal |

**Before submitting anywhere, confirm this list is still accurate.** A registry
listing that names a tool the server does not implement is a support ticket from
every agent that tries to call it.

## The three destinations

Increasing effort, and they are independent — do them in any order.

### 1. mcp.so

Web submission. Paste `listing.md` into the description field. No repo change.

### 2. Smithery

Needs `smithery.yaml` at the root of the server's own repository (not this
directory). `smithery.yaml` here is the file to copy there.

### 3. `modelcontextprotocol/servers`

A PR adding one row to the community-servers list in their README. Use the
one-line description from `listing.md`. This is the highest-value of the three
and the slowest, because it is a review by a maintainer.

## Attribution — do this FIRST

Every URL in every listing carries `?source=mcp-registry`. That key **must be
registered in `_SOURCE_BANNERS` in `relayshield_developer_signup.py` before any
submission goes in.** An unregistered key logs `unmatched:` and renders no
banner, which has happened three times on this project, and a front door whose
attribution is broken cannot be measured — so it cannot be defended later when
deciding what to build next.

## What NOT to claim in any of these listings

- No corpus size. Not 511K, not any total. The measurement doctrine applies to a
  registry listing exactly as it applies to a deck, and a directory entry is
  more likely to be checked, not less.
- No "used by" or customer names.
- Nothing about Cortex XSOAR until `sh tools/check_xsoar_pack.sh` shows the pack
  in demisto master. PR #45206 is open, not merged.
