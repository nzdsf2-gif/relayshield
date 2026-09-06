# Anthropic plugin directory submission: RelayShield

**Form:** <https://clau.de/plugin-directory-submission>

**The field list below is UNVERIFIED.** `clau.de` is egress-blocked from the
container, so I could not read the form and these are the fields any such
submission asks for, not fields I have seen. Open the form first and map these
answers onto whatever it actually asks. If it wants something not covered here,
say so and I will draft it.

**What IS verified** is everything in the "Evidence" section: those came from
running the commands, not from reading documentation.

---

## Blocking prerequisites. Do not submit before BOTH are true.

**1. `relayshield-mcp` 0.2.11 must be on PyPI.**
The plugin declares `relayshield-mcp>=0.2.10`. That floor is deliberate: 0.2.9
and earlier resolve `mcp` 2.x and die at import. Until the release ships, the
plugin installs and its MCP server fails to start, which a reviewer would see
immediately. This is currently the case, and it is the fail-closed behaviour
working, not a defect.

**2. `.claude-plugin/marketplace.json` must be on GitHub's `main`.**
Verified 2026-09-05: it is not. `git ls-tree origin/main --name-only | grep
claude-plugin` returns nothing. The `owner/repo` source form clones the DEFAULT
BRANCH, so a reviewer running `claude plugin marketplace add nzdsf2-gif/relayshield`
gets "Marketplace file not found" until `main` is pushed.

---

## The answers

**Plugin name:** `relayshield`
**Display name:** RelayShield
**Version:** 0.2.0
**Marketplace / source:** `nzdsf2-gif/relayshield` (GitHub)
**Repository:** <https://github.com/nzdsf2-gif/relayshield>
**Homepage:** <https://api.relayshield.net/developers?source=claude-skill>
**Licence:** MIT
**Category:** Security
**Keywords:** security, mcp, prompt-injection, supply-chain, agent-safety
**Author:** RelayShield, <https://relayshield.net>

**Install commands:**

    claude plugin marketplace add nzdsf2-gif/relayshield
    claude plugin install relayshield@relayshield

### Short description (one line)

Screen what a repository tells an agent to do, before you connect an agent to it.

### Longer description

Supply-chain tooling asks whether a package's code is malicious. RelayShield asks
a different question: what do this repository's *instructions* tell an agent to
do?

The plugin's skill reads the agent-facing surfaces of a GitHub repository, the
README, `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, copilot instructions, `mcp.json`
and `smithery.yaml`, and reports what those files would cause an agent to do:
fetch and execute remote code, override prior instructions, read credential
files, or carry directives hidden in zero-width or Unicode tag characters that a
human reviewer cannot see and a model reads normally. Every domain the
instructions reference is then checked against RelayShield's indicator corpus,
including the portion collected from criminal channels rather than public feeds.

It fires at the moment of the decision, when a developer is about to add an MCP
server or install a tool an agent found on its own, rather than requiring anyone
to remember a check later.

The bundled MCP server adds breach, SIM-swap, domain-lookalike, OAuth-watchlist
and infostealer lookups as callable tools.

### Components

| Type | Name | Notes |
|---|---|---|
| Skill | `relayshield-agent-bait` | ~280 always-on tokens, ~1.7k on invoke |
| MCP server | `relayshield` | stdio, launched with `uvx`, pinned `relayshield-mcp>=0.2.10` |

---

## Security and quality answers

The stated bar is "External plugins must meet quality and security standards for
approval", unenumerated. These are the answers worth volunteering.

**Does it execute anything on the user's machine?** The skill does not. The MCP
server is a stdio process launched by `uvx` from a PyPI package we publish. No
install script, no `curl | sh`, no postinstall hook.

**What does it send off the machine?** Only what the user asks it to check: a
repository identifier, or a value passed to an MCP tool. It does not read the
user's files, environment or credentials, and it does not phone home.

**Credentials.** None are embedded, and a test asserts the manifests contain no
credential-shaped string. Both `RELAYSHIELD_API_KEY` and `RELAYSHIELD_X_PAYMENT`
are optional and read from the user's own environment. With neither, the API
answers with its payment requirements, which is a usable discovery mode rather
than an error, so the plugin is safe to try without an account.

**Network destinations.** `api.relayshield.net` only, plus
`raw.githubusercontent.com` for the repository files being screened.

**Dependency pinning.** `relayshield-mcp>=0.2.10` carries a floor because earlier
versions cannot start. This is enforced by a test, not by convention.

**What it deliberately will not claim.** Three properties are enforced in the
endpoint and restated in the skill so that an agent paraphrasing a result to a
user cannot lose them:

1. It never says "safe". No findings means no hostile instructions in the files
   that could be read; the ceiling is "nothing known against it".
2. It never calls a repository or a person malicious. It reports what the
   instructions would cause an agent to do. The alternative is a libel risk
   aimed at a named maintainer on the basis of a heuristic.
3. It never throws. An unreadable target returns an explanatory verdict, because
   this runs in front of a deployment decision.

**Costs.** The scan endpoint is paid per call ($0.50 in USDC over x402, or a
subscription key). Calling it without payment returns the payment requirements,
so discovery is free and nothing is charged silently.

---

## Evidence, all of it from running the commands

- `claude plugin validate plugins/relayshield` -> Validation passed
- `claude plugin validate .` -> Validation passed
- `claude plugin marketplace add` then `install` then `details` -> Skills (1),
  MCP servers (1)
- `python3 test_agent_bait_skill.py` -> 22 tests, OK. They pin both manifests,
  that they agree on the plugin name, that the marketplace source path resolves,
  that the declared `skills/` reaches the SKILL.md, that the MCP floor is >= 0.2.10,
  that no credential-shaped string is in either manifest, and that `mcpServers`
  never reappears in `plugin.json` where it is silently ignored.
- `pip install 'relayshield-mcp>=0.2.10'` -> "No matching distribution found",
  confirming the floor fails closed rather than installing a broken server.

## After submitting

Nothing about the submission changes the install path, so the marketplace stays
the primary route in the meantime. Record the outcome in `FRONT_DOORS.md` under
FD-12 either way: a refusal with a reason is worth more than a listing, because
it is the only way anyone learns what the unenumerated bar actually is.
