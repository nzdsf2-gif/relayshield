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
| FD-1 | GitHub Marketplace Action (rsscan) | API / developer | Hours | In progress — `--check` run, pins NOT yet rewritten |
| FD-2 | pre-commit.com hooks index | rsscan | Hours | File confirmed: `sections/hooks.md`. Needs one PR |
| FD-3 | MCP registries (mcp.so, Smithery, `modelcontextprotocol/servers`) | Agentic bundle, TI | 1 day | Manifests written. FD-3a is ten minutes and needs no repo |
| FD-4 | Splunkbase app | TI corpus licences | 3-5 days | Not started |
| FD-5 | OpenCTI connector (Filigran) | TI corpus licences | 2-3 days | Not started |
| FD-6 | Chrome Web Store extension | Consumer bots, CS Mobile | 1 week | Not started |
| FD-7 | Slack App Directory | Business tiers | 1 week | Not started |

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
mkdir -p ~/rsscan-live/tools ~/rsscan-live/tests && cp ~/"Side SaaS Hustle"/tools/rsscan_sync_version.py ~/rsscan-live/tools/ && cp ~/"Side SaaS Hustle"/rsscan/tests/test_version_pin.py ~/rsscan-live/tests/ && cd ~/rsscan-live && python3 tools/rsscan_sync_version.py --check
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

## FD-2 — pre-commit.com hooks index. FILE CONFIRMED: `sections/hooks.md`.

The grep on 2026-09-02 returned seven files. `sections/hooks.md` is the index that renders at
<https://pre-commit.com/hooks.html>. The others mention the phrase for unrelated reasons:
`new-hooks.md` is the how-to-write-a-hook guide, `.pre-commit-config.yaml` is the site's own config.
**Edit `sections/hooks.md` and nothing else.**

**Prerequisite:** FD-1 finished — repo public, versions synced, tag pushed. The index links to a
repo, and a broken link is a rejected PR.

**ANDREW RUNS THIS** — see the exact shape of a neighbouring entry, so the new one matches:

```zsh
cd ~/pc-site && head -30 sections/hooks.md && echo "=== entries near where R goes ===" && grep -n -i -B 1 -A 3 "github.com/re" sections/hooks.md | head -40
```

Paste that back and I will write the exact line. The file is ordered, and matching the neighbours'
punctuation exactly is what gets a one-line PR merged without discussion.

**ANDREW CLICKS THIS** — on <https://github.com/pre-commit/pre-commit.com>:

1. Open `sections/hooks.md` → the **pencil** icon → GitHub offers to fork; accept.
2. Paste the line I give you, in the right alphabetical position.
3. **Commit changes** → *Create a new branch* → **Propose changes**.
4. PR title: `Add rsscan`. Body, one sentence:
   *"Adds rsscan, which blocks commits that add API keys, cloud credentials and LLM provider keys, scanning only added lines."*
   Nothing else. That index takes small PRs and rejects essays.

---

## FD-3 — MCP registries. STEP BY STEP, per destination.

The copy and the four real tool names are in `mcp_registry/listing.md`. **Read the tool names from
that file, never from memory** — a registry entry naming a tool the server does not implement is a
support ticket from every agent that calls it.

### FD-3a — mcp.so. Do this first: no repo access, no PR, ten minutes.

**ANDREW RUNS THIS** — print the copy you will paste into the form:

```zsh
cd ~/"Side SaaS Hustle" && cat mcp_registry/listing.md
```

**ANDREW CLICKS THIS:**

1. Go to <https://mcp.so>.
2. Top navigation → **Submit** (it may read *Submit Server*, or be a **+** button).
3. Sign in with GitHub if asked.
4. Fill the form from the file you just printed:
   - **Repository URL** — the MCP server's GitHub URL.
   - **Name** — `RelayShield`.
   - **Description** — the one-paragraph description from `listing.md`.
   - **Category / Tags** — `security`, `threat-intelligence`.
5. **Submit.** Reviewed by a human, so expect days.

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
cp ~/"Side SaaS Hustle"/mcp_registry/smithery.yaml ~/mcp-live/smithery.yaml && cd ~/mcp-live && git add smithery.yaml && git commit -m "chore: add smithery.yaml for the Smithery registry" && git push origin main
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
