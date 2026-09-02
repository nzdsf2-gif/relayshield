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
| FD-1 | GitHub Marketplace Action (rsscan) | API / developer | Hours | Blocked — version-pin defect, see below |
| FD-2 | pre-commit.com hooks index | rsscan | Hours | Ready, needs one PR |
| FD-3 | MCP registries (mcp.so, Smithery, `modelcontextprotocol/servers`) | Agentic bundle, TI | 1 day | Manifests written, needs accounts |
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

## FD-2 — pre-commit.com hooks index. STEP BY STEP.

**Why it is not done:** I could not reach `github.com/pre-commit/pre-commit.com` from this
container to confirm which file lists the hooks, and guessing a path is how an earlier URL in this
file came to 404. The check below takes ten seconds and removes the guess.

**Prerequisite:** the rsscan repo must be public and carry the tag from FD-1. Do FD-1 first.

**ANDREW RUNS THIS** — find the exact file, so we edit the right one:

```zsh
cd ~ && git clone --depth 1 https://github.com/pre-commit/pre-commit.com pc-site && grep -rl "pre-commit-hooks" ~/pc-site --include="*.md" --include="*.yaml" --include="*.yml" | head
```

Paste me the output. The list of hooks lives in one of those files, and it is either
`sections/hooks.md` or a YAML file that generates it. **Do not edit before we know which.**

**ANDREW CLICKS THIS** — once we know the file, on `github.com/pre-commit/pre-commit.com`:

1. Open that file → the **pencil** icon → GitHub offers to fork; accept.
2. Add one entry in the same shape as its neighbours, keeping alphabetical order if the file is
   ordered. The entry is:
   `https://github.com/RelayShield/rsscan` with the description
   **"Blocks commits that add API keys, cloud credentials and LLM provider keys, scanning only added lines."**
3. **Commit changes** → *Create a new branch* → **Propose changes**.
4. PR title: `Add rsscan hook`. Body: one sentence saying what it does and that it scans added lines
   only. Nothing else; that index takes small PRs.

---

## FD-3 — MCP registries. STEP BY STEP.

**Why it is not done:** the manifests are written and committed at `mcp_registry/`; nothing has been
submitted. Three destinations, do them in this order.

### FD-3a — mcp.so. Fastest, no PR.

**ANDREW CLICKS THIS:**

1. Go to <https://mcp.so> → **Submit** (top navigation).
2. Fill the form from `mcp_registry/listing.md`, which has the copy and the four real tool names
   read from the server's own source. **Do not retype the tool names from memory** — a registry
   entry naming a tool the server does not implement is a support ticket from every agent that
   calls it.
3. Submit. It is reviewed by hand, so expect days not minutes.

### FD-3b — Smithery. One file in the server's own repo.

`mcp_registry/smithery.yaml` goes in the **root of the MCP server's repo**, not this one.

**ANDREW RUNS THIS** — tell me where that repo is first if it is not `RelayShield/relayshield-mcp`:

```zsh
cd ~ && git clone https://github.com/RelayShield/relayshield-mcp mcp-live && cp ~/"Side SaaS Hustle"/mcp_registry/smithery.yaml ~/mcp-live/smithery.yaml && cd ~/mcp-live && git add smithery.yaml && git commit -m "chore: add smithery.yaml for the Smithery registry" && git push origin main
```

**ANDREW CLICKS THIS:** then <https://smithery.ai> → **Sign in with GitHub** → **Add Server** →
pick the repo. Smithery reads `smithery.yaml` from the default branch.

### FD-3c — modelcontextprotocol/servers. Highest value, slowest.

A maintainer reviews it, so it takes the longest and is worth the most.

**ANDREW CLICKS THIS:**

1. Go to <https://github.com/modelcontextprotocol/servers>.
2. Open `README.md` → **pencil** icon → accept the fork.
3. Find the **Third-Party Servers → Community Servers** list. Add one row in the same format as its
   neighbours, alphabetically. Content comes from `mcp_registry/listing.md`.
4. **Commit changes** → *Create a new branch* → **Propose changes**.
5. PR title: `Add RelayShield MCP server`. Body: two sentences. What it does, and the fact that it
   is live and versioned. No marketing.

**Do not claim a corpus number in any of the three.** MEASUREMENT DOCTRINE applies: these listings
are read by people who will check.

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
