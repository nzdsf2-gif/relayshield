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

## FD-1 — GitHub Marketplace Action. BLOCKED on a bug that has happened twice.

`rsscan/action.yml` pins `rsscan==0.1.3`. **PyPI is at 0.2.1**, verified live 2026-09-01. The
Action therefore installs a version two releases behind, and `rsscan/orb/rsscan.yml` carries the
same stale pin.

`rsscan/RELEASE_0.1.3.md` records this exact defect once already: *"the GitHub Action and CircleCI
orb both pinned `rsscan==0.1.0` while PyPI was at 0.1.3"*. It recurred because nothing asserts the
pin matches the published version.

**There are two copies of rsscan and they have diverged.** `pyproject.toml` in this repo says
0.1.3; PyPI says 0.2.1 and points its Source link at `github.com/RelayShield/rsscan`. So the
authoritative source is the other repo, and `rsscan/` here is a stale snapshot. Fixing the pin here
changes nothing anyone can install, and creates a second source of truth for the same file. This is
the DRIFT RULE in a place `lambda_drift_check.yml` does not look.

Order of work:

1. Decide which repo is authoritative and record it in the first line of `rsscan/README.md`. If it
   is `RelayShield/rsscan`, this directory should become a pointer or be deleted.
2. In the authoritative repo: bump the pin in `action.yml` and `orb/rsscan.yml` to the published
   version, **and add a test that fails when the pin and `pyproject.toml` disagree.** Without the
   test this recurs a third time.
3. Then publish: Releases → Draft a new release → tick *Publish this Action to the GitHub
   Marketplace*. `action.yml` already has the required `branding:` block (shield / purple), so
   nothing else blocks the listing itself.

## FD-2 — pre-commit.com hooks index. Ready.

`rsscan/.pre-commit-hooks.yaml` is present and correct: `id: rsscan`, `language: python`,
`pass_filenames: false`. That last one is deliberate — the hook reads the staged diff itself so it
scans only **added** lines, which is what stops pre-existing secrets making the hook unbypassable
on a repo with legacy findings.

The listing at <https://pre-commit.com/hooks.html> is generated from the repo
<https://github.com/pre-commit/pre-commit.com>. **Read that repo's contributing notes for the exact
file to edit before opening the PR** — I could not reach it from the container to confirm the
filename, and guessing it is how the first URL in this file came to 404.

Prerequisite: the hooks repo must be public and carry a tag matching the `rev:` in our own README.

## FD-3 — MCP registries. Manifests written.

Strongest thematic fit on the list: we ship an MCP server **and** sell `mcp-registry-risk`, an
endpoint whose entire subject is which MCP servers are safe to connect to. Being absent from the
registries our own product scores is the weakest position available.
`RelayShield_Strategy.md` has flagged `modelcontextprotocol/servers` as the "highest-priority new
candidate" for some time without it being done.

Material is committed at `mcp_registry/`:

- `listing.md` — the copy, with the four real tools read from the server's own source rather than
  from a description. A registry entry naming a tool the server does not implement is a support
  ticket from every agent that calls it.
- `smithery.yaml` — copy to the **root of the MCP server's own repo**, not this one.
- `README.md` — the three destinations and what each needs.

Three destinations, increasing effort: **mcp.so** (web form), **Smithery** (`smithery.yaml` in the
server repo), **`modelcontextprotocol/servers`** (a PR adding one row to their community list —
highest value, slowest, because a maintainer reviews it).

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
