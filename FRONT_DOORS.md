# RelayShield front doors — FD-1 to FD-7

*Written 2026-09-01. Also tracked in `TODO.md`; this file is the standalone copy.*

## What counts as a front door

A directory people already **search**, carrying a listing **we control**, that yields a
**self-serve first use**, with **attribution**. Outreach is not a front door. A blog post is not a
front door. If someone has to be told we exist before they can find us, it does not qualify.

Ranked by (available installs x fit) / effort.

## The rule that comes before all seven

**Every outbound link needs its `source=` key registered in `_SOURCE_BANNERS` in
`relayshield_developer_signup.py` BEFORE the listing goes live.** An unregistered key logs
`unmatched:` and renders no banner. That has bitten this project three times. A front door whose
attribution is broken cannot be measured, and a channel that cannot be measured cannot be defended
when deciding what to build next — it just becomes an opinion.

## The seven

| ID | Front door | Feeds | Effort | Status |
|---|---|---|---|---|
| FD-1 | GitHub Marketplace Action (rsscan) | API / developer | Hours | **DONE 2026-09-02.** v0.2.1 published, Marketplace badge live |
| FD-2 | pre-commit.com hooks index | rsscan | — | **DEAD AS SCOPED.** Curated page, >500 stars AND must operate on files. rsscan fails both |
| FD-3 | MCP registries (Smithery, `modelcontextprotocol/servers`) | Agentic bundle, TI | 1 day | mcp.so now charges $39 — skip. FD-3b and FD-3c are free and next |
| FD-4 | Splunkbase app | TI corpus licences | 3-5 days | Not started |
| FD-5 | OpenCTI connector (Filigran) | TI corpus licences | 2-3 days | Not started |
| FD-6 | Chrome Web Store extension | Consumer bots, CS Mobile | 1 week | Not started |
| FD-7 | Slack App Directory | Business tiers | 1 week | Not started |
| FD-8 | Official MCP Registry | Agentic bundle, TI | **DONE 2026-09-06, verified live 2026-09-07** | Latest record is 0.2.12, published 2026-09-06. `websiteUrl` carries `?source=mcp-registry`, `repository.url` is corrected to the `RelayShield` org, and the record pins `pypi relayshield-mcp==0.2.11`, which resolves. Read live from the registry API, package pin included |
| FD-9 | Glama | Agentic bundle | **DONE upstream, pending their sync** | Glama mirrors the registry record, which now carries the attribution. Nothing further to do on our side; re-check the listing in a few days |
| FD-10 | PyPI project page for `relayshield-mcp` | Agentic bundle | **DONE 2026-09-05** | 0.2.11's published metadata carries `Documentation: https://api.relayshield.net/developers?source=pypi`. Read from PyPI, not from the local file |
| FD-11 | Smithery | Agentic bundle | **LISTED, 60/100, tools not introspected** | Server metadata and config UX are full marks. Capability Quality is 0/40 because the deployment cannot start the server. `mcp_registry/smithery.yaml` was CORRECTED 2026-09-05 and still needs copying to `~/mcp-live` |
| FD-12 | Anthropic Claude Code plugin directory | Agentic bundle, API | **ROUTE OPEN, ARTEFACT BUILT** | Added 2026-09-05. Their README: *"Third-party partners can submit plugins"*, via <https://clau.de/plugin-directory-submission>. Our marketplace and plugin exist and both pass `claude plugin validate` |
| FD-13 | xAI Grok Build plugin marketplace | Agentic bundle, API | **SUBMITTED 2026-09-08, PR #612** | Open at `xai-org/plugin-marketplace`, from a `RelayShield`-owned fork, pinning `RelayShield/relayshield-plugin`. Socket checks green; `validate` is gated behind a maintainer approving the workflow, which is GitHub's first-time-contributor rule and not a failure. Awaiting review. **Do not push to the branch while it waits**: a push re-arms that approval gate |

---

## FD-1 — GitHub Marketplace Action. STEP BY STEP.

**Why it is not done:** `rsscan/` in THIS repo is a stale snapshot. PyPI is at 0.2.1 and its Source
link points at `github.com/RelayShield/rsscan`, which is the authoritative copy. Editing the pin
here changes nothing anyone can install. The work has to happen in the other repo, on the Mac,
because this container cannot reach it.

`tools/rsscan_sync_version.py` and `rsscan/tests/test_version_pin.py` are written and committed
here. Step 2 copies them across.

**ANDREW RUNS THIS** — clone the real repo and see what is stale:

```zsh
cd ~ && git clone https://github.com/RelayShield/rsscan rsscan-live && cd ~/rsscan-live && python3 tools/rsscan_sync_version.py --check
```

That will fail with "no such file" for the tool, because the tool lives in the other repo. So first:

```zsh
mkdir -p ~/rsscan-live/tools ~/rsscan-live/tests && cp ~/dev/relayshield/tools/rsscan_sync_version.py ~/rsscan-live/tools/ && cp ~/dev/relayshield/rsscan/tests/test_version_pin.py ~/rsscan-live/tests/ && cd ~/rsscan-live && python3 tools/rsscan_sync_version.py --check
```

It prints the version from `pyproject.toml` and every file that disagrees. Then rewrite them:

```zsh
cd ~/rsscan-live && python3 tools/rsscan_sync_version.py && python3 -m unittest tests.test_version_pin
```

Commit and tag. The tag matters: the README's pre-commit `rev:` points at it, so a missing tag
makes the documented install fail.

```zsh
cd ~/rsscan-live && git add -A && git commit -m "chore: sync version references to pyproject.toml, add a test that keeps them synced" && git push origin main
```

**ANDREW CLICKS THIS** — publish the Action. On `github.com/RelayShield/rsscan`:

1. **Releases** (right-hand sidebar) → **Draft a new release**.
2. **Choose a tag** → type `v0.2.1` → **Create new tag: v0.2.1 on publish**.
3. Release title: `v0.2.1`.
4. Tick **Publish this Action to the GitHub Marketplace**. It appears only because `action.yml`
   already has a `branding:` block. If the tick box is greyed out, the reason is printed next to it.
5. Primary category: **Code quality**. Secondary: **Security**.
6. **Publish release**.

**Then paste me the URL of the Marketplace listing** so it can go in the repo.

---

## FD-2 — pre-commit.com hooks index. **DEAD AS SCOPED. Do not open the PR.**

**Corrected 2026-09-02 by reading the file, which is what should have happened before any
instruction was given.** The earlier entry described this as "ready, needs one PR". It is not, and
that PR would have been closed without comment.

`sections/hooks.md` is not an open index. It is a hand-picked **featured hooks** page, and its last
section states the rules outright:

```text
this page is not intended to be exhaustive

you may send a pull request to expand this list however there are a few
requirements you *must* follow or your PR will be closed without comment:

- the tool must already be fairly popular (>500 stars)
- the tool must use a managed language
- the tool must operate on files
```

rsscan fails two of the three:

1. **>500 stars.** Not close. This is a gate on popularity, so it cannot be worked around; it can
   only be outgrown.
2. **"must operate on files".** rsscan sets `pass_filenames: false` and reads the staged diff
   itself. That is deliberate and it is the best thing about the hook -- scanning only ADDED lines
   is what stops pre-existing secrets making it unbypassable on a repo with legacy findings. The
   design choice that makes it good is the one that disqualifies it here. That trade is worth
   keeping; the listing is not worth losing it for.

(It passes the third: `language: python` is a managed language.)

**What to do instead, in order of value:**

- **Nothing, for now.** Revisit only if rsscan passes 500 stars, at which point requirement 2 still
  needs an answer.
- **The GitHub search path the page itself recommends.** It points readers at
  `path:.pre-commit-hooks.yaml language:YAML`. rsscan is already discoverable there for free, as
  long as the file stays in the public repo. Nothing to do, but it means "absent from the index" is
  not the same as "invisible to someone looking for hooks".
- **Add the `pre-commit-hooks` topic to the rsscan repo** (Settings -> topics). Free, and it is how
  the awesome-* lists and third-party aggregators find candidates.

**Effort saved: the PR, and the follow-up when it was closed.** Recorded here so no future session
re-derives "ready, needs one PR" from the old note.


## FD-3 — MCP registries. STEP BY STEP, per destination.

The copy and the four real tool names are in `mcp_registry/listing.md`. **Read the tool names from
that file, never from memory** — a registry entry naming a tool the server does not implement is a
support ticket from every agent that calls it.

### FD-3a — mcp.so. **PAID NOW ($39). Skip it.**

**Corrected 2026-09-02.** The submit form now offers only a **$39 one-time publishing fee**:
"publish immediately without review", verified badge, featured placement, dofollow link. The free
review queue that made this the ten-minute first step is either gone or no longer surfaced on that
page.

**Do not pay it**, for two reasons that are about measurement rather than the money:

1. A paid listing on a directory measures nothing. The whole point of the front-door programme is
   that a channel which cannot be attributed becomes an opinion, and "we bought placement" tells us
   nothing about whether the channel works.
2. FD-3b and FD-3c are free, carry more weight with the audience that matters, and are not yet
   done. Paying to jump a queue we have not tested is the wrong order.

**If you want to check for a free path anyway:** on the submit page, look above and below the paid
card for a "free", "community" or "submit for review" option, and check the **Discover** or
**Servers** pages for a "submit yours" link that skips the paid form. If the only route is the $39
one, close the tab. Revisit if FD-3b and FD-3c land and the traffic justifies it.


### FD-3b — Smithery. One file, in the SERVER's repo.

`mcp_registry/smithery.yaml` belongs in the root of the MCP server's own repository, **not** this
one.

**ANDREW RUNS THIS** — confirm the server repo first. If this does not clone, stop and tell me the
real repo name:

```zsh
cd ~ && git clone https://github.com/RelayShield/relayshield-mcp mcp-live && ls ~/mcp-live
```

Then, only if that cloned cleanly:

```zsh
cp ~/dev/relayshield/mcp_registry/smithery.yaml ~/mcp-live/smithery.yaml && cd ~/mcp-live && git add smithery.yaml && git commit -m "chore: add smithery.yaml for the Smithery registry" && git push origin main
```

**ANDREW CLICKS THIS:**

1. Go to <https://smithery.ai>.
2. **Sign in** (top right) → **Continue with GitHub** → authorise.
3. **Deploy** or **Add Server** in the top navigation.
4. Choose the `relayshield-mcp` repository. If it is not listed, click **Configure GitHub App**,
   grant access to that repo, then come back.
5. Smithery reads `smithery.yaml` from the default branch. Confirm and deploy.

### FD-3c — modelcontextprotocol/servers. Highest value, slowest.

A maintainer reviews this one, which is why it is worth the most.

**ANDREW CLICKS THIS:**

1. Go to <https://github.com/modelcontextprotocol/servers>.
2. Open `README.md` → the **pencil** icon → accept the fork.
3. Find (**Cmd-F**) **Community Servers**. That is the section for third-party servers. Do NOT add
   to *Reference Servers* or *Official Integrations* — different admission rules, instant rejection.
4. Add one row in the exact format of its neighbours, alphabetically. Content from
   `mcp_registry/listing.md`.
5. **Commit changes** → *Create a new branch* → **Propose changes**.
6. PR title: `Add RelayShield MCP server`. Body: two sentences — what it does, and that it is live
   and versioned. No marketing.

**Do not put a corpus number in any of the three.** MEASUREMENT DOCTRINE applies with force: these
listings are read by people who check.


## FD-8 — Official MCP Registry. **ALREADY OPEN. WAS UNATTRIBUTED.**

**Found 2026-09-02, by querying it rather than assuming.** RelayShield is listed at
`registry.modelcontextprotocol.io` and has been since **2026-05-10**:

```text
name        io.github.nzdsf2-gif/relayshield-mcp
title       RelayShield Security Intelligence
version     0.2.7   (six versions published; 0.2.7 is isLatest, 2026-07-19)
repository  https://github.com/relayshield/relayshield-mcp
websiteUrl  https://relayshield.net
package     relayshield-mcp (pypi, stdio)
status      active
```

This is the canonical MCP directory — the one clients read — and it was a live front door nobody in
this repo knew about. `mcp.so` was being treated as the priority while the registry that actually
matters was already answering.

**The defect: `websiteUrl` is a bare `https://relayshield.net`, with no `?source=` key.** Nearly four
months of arrivals from the canonical MCP directory have logged `unmatched:` and rendered no banner.
That is precisely the failure the rule at the top of this file exists to prevent, on a door nobody
opened deliberately.

**Done:** `mcp-registry` is now registered in `_SOURCE_BANNERS`
(`relayshield_developer_signup.py`), with `registry.modelcontextprotocol.io`, `glama.ai`,
`smithery.ai` and `mcp.so` as referer hosts so an arrival that loses the query parameter still
attributes. Registered BEFORE the URL changes, in that order, per the rule.

**Left to do, one edit and one publish:**

1. In `~/mcp-live/server.json`, change `websiteUrl` to
   `https://relayshield.net?source=mcp-registry`.
2. Re-publish with the `mcp-publisher` CLI (the registry is versioned, so this is a new version
   rather than an edit). Check the repo's own README first — it already publishes, so the command
   is established there; do not invent one.

Also worth a look while in there: the registry record's `repository.url` says
`github.com/relayshield/relayshield-mcp` while the namespace is `io.github.nzdsf2-gif/`. GitHub is
case-insensitive on owner, so this probably resolves, but it is the kind of mismatch that reads as
someone else's project.

---

## FD-8, THE PUBLISH COMMAND. Read from the registry's own docs, 2026-09-05.

`~/mcp-live` carries no Makefile, no PUBLISHING.md and no reference to `mcp-publisher` anywhere, so
`fd8_prepare_republish.py` correctly refused to invent one. These come from
`modelcontextprotocol/registry`'s own `docs/reference/cli/commands.md`, read from the repository
rather than guessed.

    brew install mcp-publisher
    mcp-publisher login github          # browser OAuth; grants io.github.{user}/*
    mcp-publisher validate server.json
    mcp-publisher publish               # defaults to ./server.json

`login` is the only subcommand that takes `--registry`; passing it to `publish` would be read as the
server.json PATH.

**PACKAGE OWNERSHIP VERIFICATION, and it is the step most likely to reject a publish.** The registry
proves we control the PyPI package by looking for an `mcp-name: <server name>` string **in the
package README**, which becomes the PyPI description. It may sit inside an HTML comment, and the
name must match `server.json` exactly.

**Checked on the published 0.2.11 and it is PRESENT:**
`mcp-name: io.github.nzdsf2-gif/relayshield-mcp`, both as an HTML comment and as a code span. So
ownership verification will pass, and nothing needs adding to the README before publishing.

**Three fields must be right in `server.json` before the publish**, and one of them was damaged by
this repo's own tooling on 2026-09-05:

- `version` must be **0.2.11**, matching the package on PyPI. An earlier `--write` run wrote a
  DOWNGRADE to 0.2.9; `server.json.bak` holds the pre-edit copy and the script now refuses to lower
  a version.
- `websiteUrl` must carry `?source=mcp-registry`.
- `repository.url` casing must match the git remote.

---

## FD-8, SECOND HALF: REGISTRY RECORDS ARE IMMUTABLE, so the fix needs a NEW version

Found 2026-09-05, after the first publish landed 0.2.11 with the attribution still missing.

**What happened, and it traces back to this repo's own bug.** `fd8_prepare_republish.py --write`
made three correct edits, then also wrote a version DOWNGRADE. Restoring `server.json.bak` undid the
downgrade AND the two good edits with it, so the publish shipped a correct version number and a bare
`websiteUrl`. **A backup restore is not selective**, and that is the cost of a tool that makes a
wrong edit alongside right ones.

**The registry will not let that record be edited.** From the registry's own FAQ:
*"Submit a new `server.json` with a unique version string. Once published, version metadata is
immutable (similar to npm)."*

**BUT IT DOES NOT NEED A NEW PYPI RELEASE.** The server entry's `version` and the `packages[].version`
are INDEPENDENT fields, and the registry's own `generic-server-json.md` example shows a server at
`1.0.2` carrying one package at `1.0.2` and another at `1.0.1`. So:

    server.json  "version": "0.2.12"            <- registry entry only, bumped
    packages[0]  "version": "0.2.11"            <- stays, and must stay: it names the real PyPI release

That closes FD-8 with a registry publish and no PyPI upload at all.

**The three edits, and `fd8_prepare_republish.py --write` still makes two of them:**

1. `websiteUrl` -> `https://relayshield.net?source=mcp-registry`
2. `repository.url` casing -> matches the git remote
3. `version` -> `0.2.12` **by hand**, because the script sets it from PyPI's latest and PyPI has no
   0.2.12. Bump it after running the script, and leave `packages[].version` at 0.2.11.

Then `mcp-publisher publish`. Ownership verification passes: the `mcp-name:` marker is in 0.2.11's
README and unchanged.

---

## FD-13 — xAI's Grok Build plugin marketplace. **A DIRECT PARALLEL, and the route is a PR.**

Added 2026-09-05, prompted by the Grok Bot agentic-payments story. It is the same shape as FD-12 and
the same artefact fits it.

`xai-org/plugin-marketplace` on GitHub is an OPEN catalog for Grok Build, xAI's terminal coding
agent, launched 2026-06-11 with six plugins (MongoDB, Vercel, Sentry, Chrome DevTools, Cloudflare,
Superpowers). It carries an `external_plugins/` directory for third-party plugins, and a catalog
entry in `.grok-plugin/marketplace.json`. Its structure mirrors Claude Code's closely: `skills/` with
`SKILL.md`, plus commands, agents, hooks, MCP servers.

**CORRECTED 2026-09-07, and the correction is the reason to re-read this entry.** The paragraph
that stood here said there was *"no stated eligibility policy, no quality bar and no security
vetting process"*, and concluded FD-13 was a thinner door than FD-12. **That was read from
`README.md`. The rules are in `CONTRIBUTING.md`, and they are extensive.** Verified 2026-09-07 by
cloning the repo: live, last commit `b73728b` of 2026-09-04, `external_plugins/` holding exactly one
third-party entry so far (`neon`).

What `CONTRIBUTING.md` actually states:

- A **Security expectations** section enumerating five rejection classes: arbitrary code execution
  including `curl | bash`, secret or data exfiltration, over-broad hooks or MCP scope, obfuscation,
  and **prompt injection planted in a `SKILL.md` or in descriptions aimed at the installing agent**.
- A **What review checks** table with five named dimensions: source legitimacy, security,
  components, duplication, conventions and CI.
- Review is **code-owner review plus CI**, and submissions are *"statically reviewed for
  supply-chain and execution risk"*.

So the bar is **not thinner than FD-12's, it is more explicitly specified**: Anthropic says "quality
and security standards" without enumerating them; xAI enumerates. What xAI disclaims is *authoring
and verifying* third-party plugins, which is a liability statement rather than an absence of review,
and reading it as the latter is how a submission gets sent back. The only genuinely thinner thing is
the mechanism: a PR against a public repo, versus a form.

**The general form, for the third time in this file: read the destination's CONTRIBUTING, not just
its README.** FD-2 was scoped from a landing page whose own last section said the PR would be closed
without comment. This entry was scoped from a README while the rules sat one file over.

### The requirement that actually blocks us, and it is not the security bar

> **"Source from your official org, not a personal account.** A branded plugin (`acme`) sourced from
> `some-personal-account/acme-thing` reads as a possible impersonation and *will* be questioned."

Their guide calls this *"the single biggest thing that speeds up review"*. **Our marketplace is
`nzdsf2-gif/relayshield`**, a personal account, for a plugin branded RelayShield. That names our
exact shape. A `RelayShield` org exists and is already authoritative for the MCP registry record and
for rsscan.

**It cannot be fixed from a `nzdsf2-gif/*` session.** Repo sources are one owner, fixed at session
creation, and a cross-tier `add_repo` for `relayshield/*` is refused. Moving the plugin to the org is
a SEPARATE SESSION, decided in the repository picker before the prompt is typed.

**And it reaches FD-12, which is already submitted.** That submission carries
`nzdsf2-gif/relayshield` as its install path. Moving the plugin to the org afterwards changes the
install path of a listing that may by then be live, which is a worse problem than deciding it now.
FD-12 states no org requirement so it was not blocked, but the decision is no longer free.

### What ports as-is, and it is more than expected

`CONTRIBUTING.md`, requirements checklist: *"Local plugins include a `README.md` and a valid
`.grok-plugin/plugin.json` manifest (`.claude-plugin/plugin.json` is also accepted for
Claude-ecosystem plugins)."*

**No manifest rewrite.** Our `plugins/relayshield/.claude-plugin/plugin.json` is accepted verbatim,
and a remote source vendors nothing and only pins a SHA, so the submission is a catalog entry rather
than a port.

**MEASURED 2026-09-07, not assumed, by running their own scripts against our entry.** The open
question was whether the MCP server declared in our `.mcp.json` is picked up by their loader the way
Claude Code picks it up. That question cost a round on FD-12, where `claude plugin details` settled
it and `validate` did not, so it was worth answering the same way here rather than reasoning about
it. Their catalog was cloned, our entry appended, and both CI scripts run:

    python3 scripts/validate-catalog.py          ->  Catalog OK
    python3 scripts/generate-plugin-index.py     ->  Wrote .grok-plugin/plugin-index.json
    python3 scripts/generate-plugin-index.py --check  ->  Plugin index OK

And what their generator recorded for us, which is the actual answer:

```json
"relayshield": {
  "version": "0.2.0",
  "components": {
    "mcpServers": [{"name": "relayshield", "description": "stdio"}],
    "skills":     [{"name": "relayshield-agent-bait", ...}]
  }
}
```

**Both components are detected. The MCP server IS wired up, and no manifest rewrite is needed.**
Their generator clones the pinned SHA and reads the plugin itself, so this is their loader's own
report rather than our reading of it.

**Two schema details that would have failed CI if guessed**, and both were taken from their repo:

1. **The inner key is `source`, not `type`.** The shape is
   `"source": {"source": "url", "url": ..., "sha": ...}`. Writing `"type": "remote"` is the obvious
   guess and is wrong.
2. **A url source accepts an optional relative `path`,** which is the only reason this works at all:
   our plugin lives at `plugins/relayshield` inside a monorepo rather than at a repo root, and
   without `path` their loader would look for a plugin manifest beside our MARKETPLACE manifest and
   read the wrong file. Their validator rejects a `path` that is absolute, contains `..`, or uses
   backslashes.

`tools/fd13_grok_entry.py` emits the entry with the SHA READ rather than typed, and refuses to emit
one for a commit that is not an ancestor of `origin/main` or that does not carry the plugin at that
path. Both refusals were tested by triggering them. A SHA pasted from a document is stale the moment
`main` moves, and that failure surfaces as a red CI run on somebody else's repository.

### Our pitch there is one that is already written

The Grok Bot payments story runs on Stripe Link minting a single-use virtual card, scoped to that
merchant and that amount, with the user approving the spend. **That controls how much the agent
spends, not whether the counterparty is legitimate.** An agent inside its limits paying a fraudulent
API is a fully authorised transaction. That is the Rain gap and the Routavo gap word for word, and
the argument is already in `socradar_gap_closure_roadmap.md`. Do not re-derive it, and note it is
the pitch TO them rather than a conflict with them.

**Why it is worth doing anyway:** the port is small. Our plugin is a `SKILL.md` plus an MCP server
declaration, which is exactly what their structure takes, and the catalog being six plugins deep is
the argument for going early rather than against it.

**Do FD-12 first.** Same artefact, a documented review process, and a submission that has been
prepared. FD-13 is the second copy of the same work, not a different piece of work.

**That ranking stands after the correction**, and for a better reason than before: the artefact is
built, the manifest is accepted as-is and the argument is written, so the marginal cost of FD-13
after FD-12 is small. **FD-12's form was submitted 2026-09-06.**

### THE ORG MOVE. Decided 2026-09-07, and it is a SYNC rather than a move.

Andrew called it: the plugin gets an official-org home. What follows is the shape,
and the reason it is not the obvious one.

**`RelayShield/relayshield-plugin` becomes the canonical plugin**, with its files
at the repo ROOT, which is what a remote catalog source wants and removes the need
for a `path` field entirely.

**The monorepo KEEPS its copy, and that is deliberate.** The published agent-bait
post tells readers, on a live page:

    claude plugin marketplace add nzdsf2-gif/relayshield
    claude plugin install relayshield@relayshield

`.claude-plugin/marketplace.json` sources `./plugins/relayshield`, so deleting the
monorepo copy would make a published instruction false. Nothing that works stops
working: the monorepo stays a marketplace, the org repo becomes what FD-13
submits.

**Which means two copies, which is the rsscan trap.** FD-1's own entry has to warn
that `rsscan/` here is a stale snapshot and that editing the pin changes nothing
anyone can install. A second copy with nothing comparing them drifts silently.
So:

- `plugins/relayshield/.claude-plugin/plugin.json` now declares
  `"repository": "https://github.com/RelayShield/relayshield-plugin"`, so the two
  copies can be BYTE-IDENTICAL rather than nearly so.
- **`tools/sync_plugin_repo.py`** mirrors and, with `--check`, compares. It fails
  on a file that differs, on a file missing over there, AND on a file present over
  there that this repo does not know about. That last case **refuses to write**
  rather than overwriting, because a file only in the other copy is the 2026-08-17
  hand-deploy shape in a second repository. Every one of those was tested by
  triggering it.
- A `LICENSE` was added. `plugin.json` declared MIT while no LICENSE file existed
  anywhere in the repo, and xAI's checklist requires the plugin be licensed **and**
  the license stated.

**What is verified and what is not, precisely.** The root layout is confirmed
correct: `.claude-plugin/plugin.json`, `.mcp.json`, `skills/`, `README.md` and
`LICENSE` at the top level of a real git repo. What could NOT be checked here is
their generator indexing that repo, because `generate-plugin-index.py` rejects
anything that is not an `https://` URL and refuses a local path stand-in:

    ERROR: url source must be an https:// url, got '/tmp/.../orgsim'

So **the root-source index run is UNVERIFIED until the org repo exists**, and it
is one command after the first push. The harder case, a monorepo source with a
`path`, IS verified and indexed both components, so this is the simpler shape of a
thing already known to work.

### SUBMITTED 2026-09-08. PR #612.

Opened against `xai-org/plugin-marketplace` from a fork owned by the `RelayShield`
org, pinning `RelayShield/relayshield-plugin` at `72fe82c`. Diff: 31 insertions, 0
deletions, across `marketplace.json` and `plugin-index.json`.

**The first check state, and how to read it, because two of the three lines look
worse than they are:**

- **"1 workflow awaiting approval"** and `validate` sitting at *Expected, waiting
  for status to be reported*. This is GitHub's own rule for a first-time
  contributor from a fork: workflows do not run until a maintainer clicks approve.
  It is **not** a failure and there is nothing on our side to fix. `validate` is
  the required check, so it stays pending until they approve it.
- **"Review required"** and **"Merging is blocked"** are the same fact stated
  twice: one approving review from someone with write access. Expected.
- Socket Security **Project Report** and **Pull Request Alerts** both passed;
  `semgrep-cloud-platform/scan` was still running.

**THE ONE THING NOT TO DO WHILE IT WAITS: do not push to the branch.** Every push
from a first-time contributor re-arms the workflow-approval gate, so a tidy-up
commit costs another wait on a maintainer, and it would also dismiss any review
already given. If a change is genuinely needed, make it once, deliberately.

**What we expect to hold up, and why it is not a guess:** their three CI scripts
were run here against this exact pinned SHA before the PR was opened, and all
three passed, with their generator recording both components. If `validate` goes
red after approval it is something their CI does that those three scripts do not,
which is new information and worth reading rather than re-running.

**And a worry that does not apply:** the `curl -sL ... | sh` string in `SKILL.md`
is not in this diff. The PR changes two JSON files and nothing else, so a code
scanner on this repository never sees it. It is disclosed in the PR body anyway,
because a human reviewer auditing the pinned source will.

### The eight submission steps, from their own guide

1. **Settle the org question first.** See above. If the plugin moves to `RelayShield/`, that is a
   separate session and it changes FD-12's install path too.
2. **Fork `xai-org/plugin-marketplace` INTO THE `RelayShield` ORG, not the personal
   account.** GitHub's fork dialog defaults to the personal account and has an
   **Owner** dropdown; pick `RelayShield`. Then branch from `main`.

   **Why, and it was Andrew who caught this on 2026-09-08 after a personal-account
   fork was handed over as a default rather than a decision.** Their guide's
   ownership rule is about `source.url`, which is already
   `RelayShield/relayshield-plugin`, so the fork owner does not decide acceptance.
   But their review matrix grades **Source legitimacy** as *"Official org vs
   personal/throwaway account; repo exists; SHA pinned; brand matches source"*, and
   a PR header reading `RelayShield:add-relayshield-plugin -> xai-org:main`
   corroborates first-party ownership in the one place a reviewer looks first. A
   header reading `nzdsf2-gif:...` invites the exact question the org move exists to
   pre-empt, on a PR whose whole argument is that we are who we say we are.

   Verified 2026-09-08: `RelayShield/plugin-marketplace` does not exist, so the fork
   name is free. A fork into an org is refused only when a repo of that name is
   already there.

   **The general form, worth more than this instance: a default is not a decision.**
   GitHub picked the personal account and it was passed on unexamined. Anywhere an
   owner, a branch, a visibility or a name is being chosen, say which one and why,
   because the reader cannot tell a considered choice from an accepted default.
3. Add ONE entry to `.grok-plugin/marketplace.json`. Remote source recommended for third-party:
   point `source.url` at our public repo and pin a **full 40-character lowercase commit SHA**.
   Nothing is vendored.
4. Get the SHA with `git ls-remote <repo> HEAD`. **`main`, a tag and an abbreviated SHA are all
   rejected by their validator**, because a moving ref would let a later force-push ship new code to
   every user silently.
5. Keep `keywords` and `domains` **brand-scoped**. They power Grok Build's proactive plugin CTA, and
   their guide names `postgres`, `database`, `api`, `cli` and `deploy` as terms that get pushed back
   for mis-firing the CTA on unrelated requests. Ours are `relayshield`, `mcp registry risk`,
   `agent bait scan`, and only `relayshield.net` as a domain.
6. **Regenerate the component index, never hand-edit it:** `python3 scripts/generate-plugin-index.py`.
   CI fails on a stale `.grok-plugin/plugin-index.json`.
7. **Validate exactly what their CI runs**, before opening anything:
   `python3 scripts/validate-catalog.py` and `python3 scripts/generate-plugin-index.py --check`.
8. **Declare the network endpoints the plugin calls and the credentials it needs, in the README.**
   Their guide says outright this speeds review. Then open the PR against their template and wait
   for CI plus code-owner review.

**Self-check against their five rejection classes before opening it.** Two points are in our favour
and neither states itself: our skill is a DETECTOR for prompt injection planted in a `SKILL.md`,
which is one of the five classes by name, and `.mcp.json` pins `relayshield-mcp>=0.2.10` as a safety
property rather than tidiness, because 0.2.9 and earlier resolve `mcp` 2.x and die at import. Say
both in the PR body.

---

## FD-9 — Glama. **LISTED. VERIFIED 2026-09-03.**

The listing exists at **`https://glama.ai/mcp/servers/relayshield/relayshield-mcp`**, found through
web search because `glama.ai` itself is still blocked by the container's egress policy. So the
question the section below leaves open is answered: we are listed, and `glama.json` did its job.

**Two things follow, and the second is the interesting one.**

1. `glama.ai` is already a referer host on the `mcp-registry` banner, so an arrival that clicks
   through from that listing already attributes. Nothing more is needed for measurement unless we
   want Glama distinguished from the other registries, which needs its own key rather than a shared
   one.
2. **The listing path is `relayshield/relayshield-mcp`, not `nzdsf2-gif/…`.** That is the same owner
   the MCP registry record carries in `repository.url`, so Glama almost certainly indexed it from
   there. If `github.com/relayshield/relayshield-mcp` does not exist, the listing links at a
   repository that is not ours and possibly at nothing at all. **This is now the reason to fix
   `repository.url`, and it is a better reason than tidiness.** It could not be checked from the
   container: `github.com` returns 403 to the agent proxy for HTML.

**ANDREW CLICKS THIS:** open <https://github.com/relayshield/relayshield-mcp>. A 404 means the
registry record and the Glama listing both point at nothing, and the FD-8 re-publish below should
correct `repository.url` at the same time as `websiteUrl`.

---

## FD-9 (original text, kept) — Glama. Manifest present, listing status UNVERIFIED.

`~/mcp-live/glama.json` exists, so the repo is prepared for Glama. **Whether it is actually listed
could not be checked from the container:** `glama.ai:443` is rejected by the egress policy. Not
"absent" — unchecked. Do not record it either way until someone opens the site.

**ANDREW CLICKS THIS:** open <https://glama.ai/mcp/servers> and search RelayShield.

- If listed: check the link it points at, and get `?source=mcp-registry` onto it. The key is already
  registered and `glama.ai` is already a referer host.
- If not listed: Glama indexes from GitHub, so the usual route is to make sure `glama.json` is on
  the default branch and let it pick the repo up, rather than a submission form.

---

## FD-4 — Splunkbase. Not started.

The biggest enterprise TI directory we have not touched. Sentinel is shipped, XSOAR is in review,
MISP is done — Splunk is the gap, and it is where TI budget actually sits. A Splunkbase app needs a
`app.conf`, a saved-search pack and Splunk's AppInspect to pass, which is the 3-5 day figure.

## FD-5 — OpenCTI connector. Not started.

Already tracked as DISTRIB-FILIGRAN-1 and gated on OpenCTI-1. Filigran's connector catalogue is
browsed by precisely our buyer, and a connector is a smaller build than a Splunk app because the
STIX/TAXII surface already exists.

## FD-6 — Chrome Web Store extension. Not started.

Right-click a link, get a verdict, same `/scan` backend. The **only** front door on this list that
reaches consumers who are not already on Telegram or WhatsApp — which matters more than it did,
because the Telegram bot currently has no measurable active users.

## FD-7 — Slack App Directory. Not started.

The largest business directory available to us. The Zapier Slack template is a proxy for this; a
native Slack app is the real door, and it lands inside a recurring business process rather than an
alert feed.

---

## Sequencing

**FD-1, FD-2 and FD-3 first.** All three are publish-or-list steps against code that already
exists, they cost under two days combined, and none needs a new product surface. FD-1 is blocked
only by the version-pin decision, which is an hour's work in the right repo.

**FD-4 is the one that moves TI licensing revenue.** Do it once FD-1 to FD-3 are live and the
attribution keys are proven to be recording.

**FD-6 is the one that matters if consumer distribution stays the priority**, because it is the
only consumer surface here that does not depend on someone already using a messenger bot.


---

## FD-10 — PyPI. The package page is a front door and it is unattributed.

Found 2026-09-03 while verifying FD-8, by querying PyPI's own JSON rather than assuming:

```text
relayshield-mcp  version 0.2.9
  Homepage       https://relayshield.net
  Documentation  https://api.relayshield.net/developers
```

**Neither link carries a `?source=` key.** The Documentation link goes straight to the page whose
whole attribution system we have spent two sessions fixing, and every arrival through it logs as
unattributed. PyPI is where the MCP server is actually installed from, so this is not a minor door:
anyone who finds the package, reads its page and clicks through is invisible.

It is also the same failure as FD-8, on a second surface, found the same way. Worth assuming there
is a third.

**Step 1 is DONE: the `pypi` key is registered** in `_SOURCE_BANNERS`
(`relayshield_developer_signup.py`), with `pypi.org` and `files.pythonhosted.org` as referer hosts,
registered before the link changes because that order is the rule.

**Step 2, concretely.** `tools/fd8_prepare_republish.py --dir ~/mcp-live --write` rewrites the
`Documentation` entry under `[project.urls]` in `~/mcp-live/pyproject.toml` to
`https://api.relayshield.net/developers?source=pypi`, and prints what it changed. If there is no
`[project.urls]` section it says so and prints the two lines to add rather than guessing at the file
layout.

**The link goes live when a PyPI release ships, not when the registry publishes.** Those are two
different publishes and the registry one does not carry it. So the sequence is: run the script,
publish the new version to the MCP registry (which fixes FD-8 and FD-9), and let the pyproject
change ride the next PyPI release.

**Verify afterwards, without a browser:**

```text
python3 -c "import json,urllib.request; d=json.load(urllib.request.urlopen('https://pypi.org/pypi/relayshield-mcp/json')); print(d['info']['project_urls'])"
```

The `Documentation` value should carry `?source=pypi`.

**While there: the registry is two versions behind PyPI.** The MCP registry's latest is 0.2.7
(2026-07-19) and PyPI is on 0.2.9. Whatever 0.2.8 and 0.2.9 changed has never reached the canonical
directory, so a client installing from the registry record gets an older package than a client
installing from PyPI. The FD-8 re-publish fixes that too, which makes one publish close three
things: `websiteUrl`, `repository.url` and the version lag.

---

## FD-12 — Anthropic's Claude Code plugin directory. **The route was READ, and it is open.**

Added 2026-09-05. This is the first door in this programme that turned out not to be shut, and it
was checked the FD-2 way -- from the destination's own files, before anything was written for it.

`anthropics/claude-plugins-official`'s README says, in these words: *"Third-party partners can
submit plugins for inclusion in the marketplace"*, and names the route: the plugin directory
submission form at <https://clau.de/plugin-directory-submission>. The stated bar is *"External
plugins must meet quality and security standards for approval"*, unenumerated.

**Why this ranks above another blog post.** It puts the check at the moment of the decision -- a
developer in Claude Code about to add an MCP server -- rather than in an article read later by
someone with no pending decision.

### What exists already

- `.claude-plugin/marketplace.json` at the repo root, so **this repo IS a marketplace**.
- `plugins/relayshield/` with `.claude-plugin/plugin.json` and the agent-bait skill.
- `.claude/settings.json` declaring the marketplace and enabling the plugin, so anyone who clones
  and trusts the folder gets it with no command at all.
- Both manifests pass `claude plugin validate`, and the full install was run end to end
  (`marketplace add` -> `install` -> `list` -> `details`) rather than assumed.

### Installing it, and the correction that goes with it

**`/plugin` is the in-TUI form and it is NOT the only one.** A previous reply asserted that slash
commands are typed inside Claude Code, full stop, and handed over `/plugin marketplace add`. That
answer was incomplete and cost a round: `/plugin` was unavailable in the environment being used, and
there is a perfectly good shell CLI that does the same job. Verified against `claude` 2.1.263:

    claude plugin marketplace add nzdsf2-gif/relayshield
    claude plugin install relayshield@relayshield
    claude plugin list

`claude plugin marketplace add ./` also works for a local path -- note the trailing slash, because a
bare `.` is rejected as an invalid source format.

### The submission is PREPARED. `plugin_directory_submission.md` holds it.

Written 2026-09-05: every answer a directory form asks for, plus the security answers worth
volunteering against an unenumerated bar, plus the evidence, all of it from running the commands
rather than reading documentation. **The field list in it is UNVERIFIED** because `clau.de` is
egress-blocked from the container; open the form and map the answers onto what it actually asks.

**The server IS bundled now**, in `plugins/relayshield/.mcp.json` and NOT in `plugin.json`, where
the key is silently ignored. See CLAUDE.md, A PLUGIN'S MCP SERVER GOES IN `.mcp.json`.

### Two blocking prerequisites, and neither is optional

1. **`relayshield-mcp` 0.2.11 must be on PyPI.** The plugin pins `>=0.2.10` because 0.2.9 and
   earlier resolve `mcp` 2.x and die at import. Until the release ships the plugin installs and its
   server fails to start, which a reviewer sees immediately. `tools/mcp_release_check.py` says what
   to publish; `tools/mcp_selftest.py --pypi` confirms it afterwards.
2. **`.claude-plugin/marketplace.json` must be on GitHub's `main`.** Verified 2026-09-05: it is
   not. `git ls-tree origin/main --name-only | grep claude-plugin` returns nothing, and the
   `owner/repo` form clones the DEFAULT BRANCH, so a reviewer gets "Marketplace file not found".

Re-run `claude plugin validate` on both manifests immediately before submitting, and
`claude plugin details` after installing, because validate only says the file is well formed.

---

## FD-11 — Smithery. Not listed, and worth a deliberate decision rather than a reflex.

Searched 2026-09-03: no RelayShield entry on `smithery.ai`. `mcp_registry/smithery.yaml` has been
written and never shipped, and FD-3b already has the steps.

**Read this before submitting.** Smithery does not just list a server, it can BUILD and HOST it, and
in June 2025 a path-traversal flaw in that build pipeline let a researcher escape the build
directory and read an authentication token with control over more than 3,000 hosted MCP servers.
Smithery rotated the token and fixed the flaw within two days, and there is no evidence it was
exploited. It is a reasonable outcome for a young platform, and it is still a fact a security vendor
should weigh before handing over a build.

The distinction that resolves it: **being listed is not the same as being hosted.** A listing that
points at our PyPI package, which users install themselves, carries none of that risk. A hosted
build does. So submit the listing, do not opt into hosting, and do not put any RelayShield
credential into a Smithery-side configuration.

### FD-11, step by step

**1. Put the manifest in the SERVER's repo, not this one.** `mcp_registry/smithery.yaml` lives here
for version control; Smithery reads it from the default branch of the repo it indexes.

```text
cp ~/dev/relayshield/mcp_registry/smithery.yaml ~/mcp-live/smithery.yaml
cd ~/mcp-live && git add smithery.yaml && git commit -m "chore: add smithery.yaml" && git push origin main
```

**2. Sign in at <https://smithery.ai> with GitHub**, using the account that owns the MCP server
repo. Smithery indexes what that account can see.

**3. Add the server**, choosing the repository, and when it offers to build or deploy a hosted
version, **decline it.** The listing is the goal. See the reason above.

**4. Point the listing at the PyPI package.** The install line users should see is the ordinary one:
`pip install relayshield-mcp`. If the form asks for a hosted endpoint, leave it empty.

**5. Set the website link to `https://relayshield.net?source=mcp-registry`.** That key already
exists and `smithery.ai` is already one of its referer hosts, so arrivals attribute either way, but
the explicit parameter is what survives a referrer being stripped.

**6. Do not paste any RelayShield API key into a Smithery configuration field.** Users bring their
own key or use the keyless endpoints. Nothing about a listing needs a credential from us, and the
2025 incident is the reason to keep it that way.
