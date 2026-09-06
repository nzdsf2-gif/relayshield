# Claude Code plugin directory submission: RelayShield

**CORRECTED 2026-09-05.** An earlier version of this file named
`clau.de/plugin-directory-submission` and said the destination was
`anthropics/claude-plugins-official`. That came from that repo's README, and the
current documentation is more specific and partly contradicts it. The corrected
facts:

- **Submissions land in `anthropics/claude-plugins-community`**, the public
  community marketplace, after review. Users add it with
  `claude plugin marketplace add anthropics/claude-plugins-community`.
- **`claude-plugins-official` is curated separately, at Anthropic's discretion.
  There is no application process, and the submission form does not add plugins
  to it.** So the realistic target is the community marketplace, and the
  official one is not something to plan around.
- **There are two forms, and which one applies depends on the account:**
  - claude.ai: `claude.ai/admin-settings/directory/submissions/plugins/new`
    **requires a Team or Enterprise organization and directory management
    access.**
  - Console: `platform.claude.com/plugins/submit` is the route for individual
    authors not in a Team or Enterprise org. **This is almost certainly ours.**
- **Approved plugins are pinned to a specific commit SHA**, and CI bumps the pin
  as new commits are pushed. The public catalog syncs nightly, so there is a
  delay between approval and appearing in `marketplace.json`.
- **Run `claude plugin validate ./plugins/relayshield --strict` before
  submitting.** The review pipeline runs the same check, plus automated safety
  screening. `--strict` turns warnings into errors, which is what to submit
  against.

**Verified 2026-09-05:** `claude plugin validate ./plugins/relayshield --strict`
prints `Validation passed`, with no warnings.

---

## Blocking prerequisites. Do not submit before BOTH are true.

**1. `relayshield-mcp` 0.2.11 must be on PyPI.**
The plugin declares `relayshield-mcp>=0.2.10`. That floor is deliberate: 0.2.9
and earlier resolve `mcp` 2.x and die at import. Until the release ships, the
plugin installs and its MCP server fails to start, which a reviewer would see
immediately. This is currently the case, and it is the fail-closed behaviour
working, not a defect.

**2. `.claude-plugin/marketplace.json` must be on GitHub's `main`.**
The reviewer clones the DEFAULT BRANCH, and approved plugins are pinned to a
commit SHA in the community catalog, so whatever is on `main` at submission time
is what gets reviewed. Confirm with
`git ls-tree origin/main --name-only | grep claude-plugin` before submitting.

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

**Install commands (from our own marketplace, which works today):**

    claude plugin marketplace add nzdsf2-gif/relayshield
    claude plugin install relayshield@relayshield

Once accepted into the community catalog, users would instead run:

    claude plugin marketplace add anthropics/claude-plugins-community
    claude plugin install relayshield@claude-community

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

- `claude plugin validate ./plugins/relayshield --strict` -> Validation passed,
  no warnings. This is the check the review pipeline itself runs.
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
