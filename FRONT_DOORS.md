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
| FD-8 | Official MCP Registry | Agentic bundle, TI | Done, needs attribution | **ALREADY LISTED since 2026-05-10.** `source=` key now registered; `server.json` websiteUrl still to update. **Registry is on 0.2.7 while PyPI is on 0.2.9** |
| FD-9 | Glama | Agentic bundle | **LISTED, needs attribution** | Verified 2026-09-03: `glama.ai/mcp/servers/relayshield/relayshield-mcp` |
| FD-10 | PyPI project page for `relayshield-mcp` | Agentic bundle | **OPEN AND UNATTRIBUTED** | Its `Documentation` link points at the developers page with no `?source=`. Found 2026-09-03 |
| FD-11 | Smithery | Agentic bundle | Not listed | Searched 2026-09-03, no RelayShield entry. `mcp_registry/smithery.yaml` is written and unshipped. See the note below before submitting |

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
cp ~/"Side SaaS Hustle"/mcp_registry/smithery.yaml ~/mcp-live/smithery.yaml
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
