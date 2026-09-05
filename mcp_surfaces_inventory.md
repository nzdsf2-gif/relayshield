# The RelayShield MCP surfaces — what exists, checked 2026-09-05

Written because "I think I only have one MCP server" turned out to be five, and the difference
matters: they fail in different ways and only one of them is a thing you install.

## The five

| # | Surface | What it is | Where it lives | Reachable from the build container? |
|---|---|---|---|---|
| 1 | **`relayshield-mcp` on PyPI** | stdio server, the one you install in a client | `pypi.org/project/relayshield-mcp` — **0.2.9** | yes, checked |
| 2 | **MCP registry entry** | the canonical directory listing | `io.github.nzdsf2-gif/relayshield-mcp` — **0.2.7**, status active | yes, checked |
| 3 | **HuggingFace Space** | hosted MCP over HTTP, Gradio | `hf-space-mcp-server/` in this repo | no, egress-blocked |
| 4 | **Apify Actor** | MCP over Streamable HTTP, Standby mode | `relayshieldadmin/relayshield-security-tools` | no, egress-blocked |
| 5 | **`@relayshield/bankr-mcp`** | a separate TypeScript stdio server built for Bankr | `relayshield/mcp-server/` in this repo | n/a, not published |

Only **#1** is a thing that appears in a client and can show "disconnected". #3 and #4 are hosted and
would show as a failing URL, not a failing process. #5 has never been published.

## What the registry record actually says, read today

```
name        io.github.nzdsf2-gif/relayshield-mcp
title       RelayShield Security Intelligence
version     0.2.7            <-- PyPI is on 0.2.9
websiteUrl  https://relayshield.net          <-- no ?source=mcp-registry
repository  https://github.com/relayshield/relayshield-mcp
status      active, isLatest true, published 2026-07-19
packages    pypi: relayshield-mcp 0.2.7, transport stdio
env         RELAYSHIELD_API_URL (required), RELAYSHIELD_API_KEY, RELAYSHIELD_X_PAYMENT
```

**Three defects confirmed live, all of them FD-8's, none of them new:**

1. **Two versions behind.** The registry says 0.2.7; PyPI says 0.2.9. Whatever 0.2.8 and 0.2.9
   changed has never reached the canonical directory, so anyone installing from the registry's
   pinned version gets old code.
2. **`websiteUrl` carries no `?source=mcp-registry`**, so four months of arrivals from the canonical
   MCP directory have logged `unmatched:` and rendered no banner. The key is registered; the link
   is not.
3. **`repository.url` says `github.com/relayshield/...` while the namespace is
   `io.github.nzdsf2-gif/`.** Glama indexed from that URL, so the mismatch is a broken link on two
   live surfaces rather than a cosmetic oddity.

`RELAYSHIELD_API_URL` in the record is also the raw execute-api hostname, not `api.relayshield.net`.
The live agentic handler was deliberately moved to the branded host for exactly this reason: a raw
AWS hostname pins callers to a URL that breaks if the gateway id changes. Worth fixing in the same
re-publish.

**All three are fixed by one `mcp-publisher` re-publish**, which is FD-8/9/10 and is already item 14
on the next-session list. `tools/fd8_prepare_republish.py --dir ~/mcp-live --write` makes the edits.

## Finding the one on your Mac

`tools/mcp_inventory.sh` reads every MCP client config path on macOS — Claude Desktop, Claude Code,
Cursor, Windsurf, VS Code, and project-scoped `.mcp.json` — lists what each declares, and then reads
the client's own logs for the reason a server stopped.

**Every environment value is redacted to its first four characters and a length** before printing,
because an MCP config holds `RELAYSHIELD_API_KEY` in plain text and this output is going into a
chat. Enough to tell "the key is set" from "the key is empty"; not enough to use.

**Read section 3 first.** The config says what the client tried to run; the log says why it stopped,
and those are usually different problems. A server that "disconnected" has almost always exited, and
the two common causes are a config pointing at a python that does not have the package installed,
and an API key the server starts fine with and then gets 401s on. Those look identical in the client
and have nothing in common as fixes.
