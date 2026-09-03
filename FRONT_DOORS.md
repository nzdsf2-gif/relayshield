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
