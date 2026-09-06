# Claude plugin directory form: exact values to paste

Read off the form in the screenshot, step 2 "Plugin information". Copy each block
into the matching field.

---

## Plugin links

**Link to plugin**

```
https://github.com/nzdsf2-gif/relayshield
```

**Path within repository** (optional, but REQUIRED for us: the plugin is not at
the repo root)

```
plugins/relayshield
```

**Plugin homepage** (optional)

```
https://api.relayshield.net/developers?source=claude-skill
```

---

## Plugin details

**Plugin name**

```
relayshield
```

This matches `name` in `plugins/relayshield/.claude-plugin/plugin.json`. The form
warns against brand names you do not own; RelayShield is ours.

**Plugin description**

```
Screen what a repository tells an agent to do, before you connect an agent to it.

Supply-chain tools ask whether a package's code is malicious. This asks a
different question: what do the repository's instructions tell an agent to do?
It reads the agent-facing files of a GitHub repository (README, AGENTS.md,
CLAUDE.md, .cursorrules, copilot-instructions, mcp.json, smithery.yaml) and
reports what those files would cause an agent to do: fetch and execute remote
code, override prior instructions, read credential files, or follow directives
hidden in zero-width or Unicode tag characters that a human reviewer cannot see
and a model reads normally. Every domain the instructions reference is then
checked against RelayShield's indicator corpus, including the part collected from
criminal channels rather than public feeds.

It never reports a target as "safe": the ceiling is "nothing known against it".
It never calls a repository or a person malicious; it reports what the
instructions would cause an agent to do. An unreadable target returns an
explanatory result rather than an error, because it runs in front of a
deployment decision.

The bundled MCP server adds breach, SIM-swap, domain-lookalike, OAuth-watchlist
and infostealer lookups as callable tools. No credentials are required to try it:
without a key the API returns its payment requirements, which is a usable
discovery mode.
```

**Example use cases**

```
Example 1: Before adding an unfamiliar MCP server to an agent's toolset, screen
the server's repository for instructions that would make the agent fetch and
execute a remote script, and check whether any domain it references is already
known bad.

Example 2: An agent finds a tool on its own mid-task and proposes installing it.
The skill fires at that moment and reports what the repository's setup
instructions would actually cause the agent to do, before anything runs.

Example 3: Auditing a dependency that ships agent-facing files, to find
prompt-injection text or directives hidden in zero-width or Unicode tag
characters, which a human reading the README would not see.

Example 4: Using the bundled MCP server to check an email address for breach or
infostealer exposure, or a domain for lookalikes, from inside a Claude Code
session.
```

---

## If step 3 "Submission details" asks about security or maintenance

Volunteer these; the bar is not enumerated publicly.

- **Does it execute anything locally?** The skill does not. The MCP server is a
  stdio process launched by `uvx` from a PyPI package we publish. No install
  script, no `curl | sh`, no postinstall hook.
- **What leaves the machine?** Only what the user asks it to check: a repository
  identifier, or a value passed to an MCP tool. It does not read the user's
  files, environment or credentials.
- **Network destinations:** `api.relayshield.net`, plus
  `raw.githubusercontent.com` for the repository files being screened.
- **Credentials:** none embedded, and a test asserts the manifests contain no
  credential-shaped string. `RELAYSHIELD_API_KEY` and `RELAYSHIELD_X_PAYMENT`
  are optional and read from the user's own environment.
- **Dependency pinning:** the MCP server is pinned `relayshield-mcp>=0.2.10`.
  That floor is deliberate: earlier versions resolve an incompatible `mcp` major
  and cannot start, so the plugin cannot install a server that fails at import.
- **Costs:** the scan endpoint is paid per call ($0.50 in USDC over x402, or a
  subscription key). Calling without payment returns the payment requirements, so
  nothing is charged silently.
- **Validation:** `claude plugin validate ./plugins/relayshield --strict` passes
  with no warnings.

---

## Before you submit, one check

The reviewer clones the DEFAULT BRANCH and approved plugins are pinned to a
commit SHA, so what is on `main` at submission time is what gets reviewed.

    cd ~/dev/relayshield
    git ls-tree origin/main plugins/relayshield/ --name-only

**Confirmed 2026-09-05:** this returns `.claude-plugin`, `.mcp.json`, `README.md`
and `skills`, so the plugin is on `main` and the form can be submitted.
