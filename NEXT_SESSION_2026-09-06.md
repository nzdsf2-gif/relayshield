# Handoff: 2026-09-06

*A record of one day, not a live queue. CLAUDE.md is the maintained source; this is the same
content extracted so it can be read on its own. If you are reading this more than a few days
later, check CLAUDE.md instead.*

## WHERE 2026-09-06 LEFT THINGS — read this first

**A DATING CORRECTION BEFORE ANYTHING ELSE.** Everything this session added is dated **2026-09-05**
in its commit messages and in most inline notes, and it was all done on **2026-09-06**. The previous
session was 09-05 and I carried its date forward without checking. The entries are not being
rewritten one by one, because a wrong day on a true record is cheaper than a sweep that might change
a fact by accident. **Read any "2026-09-05" added below or in today's commits as 2026-09-06.** The
general form is rule 14 applied to metadata: a date is a number the reader acts on when
reconstructing what happened when.

### WHAT CLOSED TODAY, and it was a good day for front doors

Seven items closed, four of them permanently.

- **The published MCP package was broken for every new install, and is fixed.** `relayshield-mcp`
  declared `mcp>=1.0.0` unbounded, so a fresh `pip install` resolved mcp 2.x and the server died at
  import. 0.2.11 is live and `tools/mcp_selftest.py --pypi` reports ACTIVE with 16 tools.
- **FD-8, FD-9 and FD-10 are DONE.** Registry entry 0.2.12 carries `?source=mcp-registry`, the repo
  casing is fixed, PyPI's metadata carries `?source=pypi`.
- **`crewai-relayshield` 0.1.0 is on PyPI**, built against CrewAI's SHIPPED `before_tool_call` hook.
- **The Claude Code plugin is built, installable, and SUBMITTED for review** (FD-12).
- **The MPP endpoint is live**, returning 402. It was a propagation race, not a routing bug.
- **The deploy-role invoke policy is applied.** All 26 mapped functions simulate as allowed.

### THE TOP 15 FOR THE NEXT SESSION

Regenerated, not annotated. Eight of the previous fifteen are closed, so this is mostly new work
rather than the same list with strikethroughs.

1. **Smithery, ONE decision then one click (FD-11).** The listing is live at 60/100 with metadata and
   config UX at full marks. Capability Quality is 0/40 because Smithery cannot enumerate the tools.
   **Do NOT use "Publish via URL" with `https://relayshield.net`** -- that is a website, it returns
   HTML, and it is the exact cause of the current zero. See the section below for the three options
   and the recommendation.
2. **Publish the agent-bait blog post (ABS-2).** `blog-agent-bait-scan.md` is written, ~1,600 words,
   no corpus numbers, Island's figures attributed to Island. **Add the link to Island's write-up in
   the first paragraph before publishing** -- the 2026-08-30 LLMjacking post shipped resting on
   someone else's reporting with no links, and on Medium that reads as if the reporting were ours.
3. **Post the Apify pre-call intro NOW.** `apify_writers_intro_post.md` is ready to paste into
   `#apify-writers`. Not a submission, spends nothing, and asks the dev.to access question.
4. **MPP selftest, reads-only.** `AWS_PROFILE=relayshield ~/.rsvenv/bin/python
   tools/mpp_settlement_selftest.py --reads-only`. Now unblocked: the endpoint is live. It answers
   whether the Stripe account has crypto deposit addresses and a business profile, and a 403 there is
   the text to send `machine-payments@stripe.com`.
5. **Map `relayshield-mpp-settlement` in `deploy_lambdas.yml`.** The function now EXISTS, which was
   the precondition. `check_deploy_invoke_policy.py` already notes it is granted but unmapped.
6. **FD-13, the Grok Build plugin marketplace.** `xai-org/plugin-marketplace`, `external_plugins/`,
   route is a PR. Same artefact as FD-12, so this is a port rather than new work. Its contribution
   note is *"open a PR, CI runs the validator, code-owner review required"* with no stated
   eligibility or security bar, so it is a thinner door than FD-12's.
7. **Watch FD-12.** Submitted for review with `privacy.relayshield.net` (verified live) and Claude
   Code ticked as the only supported platform, because Cowork was never tested. Approved plugins are
   pinned to a commit SHA and the catalog syncs nightly, so expect a delay. **If it is accepted,
   test Cowork and add it.**
8. **Submit the Apify article in NOVEMBER**, when the Typeform reopens. Three console facts to verify
   first, in `apify_writers_intro_post.md`. It must NOT appear on blog.relayshield.net first.
9. **Rewrite the MCP directory listing copy** to lead with counterparty authorization, across the
   registry, Glama, PyPI, the HF Space and Apify. The registry record is now correct structurally;
   this is about what it SAYS.
10. **Extend the Rain demo to the merchant-agent shape.** `tools/rain_demo.py` already does the hard
    part with verifiable on-chain payments. The Grok Bot story is the current hook: Stripe Link mints
    a single-use card for that merchant and that amount, which controls how much an agent spends and
    says nothing about whether the counterparty is legitimate.
11. **The Commerce Agents blog post.** Register `?source=commerce-agents` in `_SOURCE_BANNERS`
    BEFORE it ships, exactly as `claude-skill` was registered before the skill that links to it.
12. **ABS-1 Bundle D usage dimension.** Waits on a measured false-positive rate, not a date.
13. **Send the twelve** (`outreach_bot_prospects_curated.md`). Founder-side, carried for weeks.
14. **INTEL-5** (`tools/diagnose_stolen_sessions.py`). Until it runs, no count out of
    `relayshield_stolen_sessions` means anything about the criminal market.
15. **FD-3c, `modelcontextprotocol/servers`.** The highest-value MCP listing left and deliberately
    unscoped: nobody has read its contribution rules. Read the destination first. That is the FD-2
    lesson and it has already cost this programme a wasted day once.

### SMITHERY: THE "PUBLISH VIA URL" TRAP, AND THE THREE OPTIONS

Smithery's Publish dialog asks for an **MCP Server URL**, described as "the HTTP URL where your MCP
server is accessible". `https://relayshield.net?source=mcp-registry` was entered there. That is a
marketing website. It returns `text/html`, which is precisely the error in the Logs
(`Unexpected content type: text/html`) and the reason Capability Quality is 0/40.

**A stdio server distributed on PyPI has no HTTP URL.** That publish path does not apply to it.

Three options, and the recommendation is the third:

1. **Repo-based publish**, so Smithery reads `smithery.yaml` from the server repo. The corrected
   manifest is live at `RelayShield/relayshield-mcp/main/smithery.yaml` (uvx, sixteen real tool
   names, no required config). **UNVERIFIED whether Smithery introspects a stdio server without
   building it** -- if it does not, this earns metadata points and no capability points.
2. **Point it at one of our OWN hosted MCP surfaces.** The HF Space serves MCP at
   `/gradio_api/mcp/sse`, and the Apify Actor serves MCP over Streamable HTTP in Standby. Either is
   a real HTTP MCP endpoint. **This does NOT re-open the FD-11 security objection**, and the
   distinction matters: that objection was about Smithery BUILDING and HOSTING our server in their
   pipeline, not about us pointing at an endpoint we already run. **UNVERIFIED**: both are
   egress-blocked from the container, so neither the Space's exact URL nor whether Smithery accepts
   SSE has been checked.
3. **Stop at 60/100.** The listing is live, correct, honest, and points at the PyPI package. The
   remaining 40 points are a directory badge. Nothing about them reaches a user who installs the
   server, and two of the three routes to them are unverified.

**Recommended: option 3, unless the HF Space endpoint is confirmed live**, in which case option 2 is
free and correct. Do not spend a third session on a badge.

### THE LESSONS THIS SESSION PAID FOR

**Rules 13 and 14 were written today, and both fired again after being written.** That is the
honest record. Rule 13 (a slash command is not a shell command) was written after `/plugin` went
into zsh, then immediately needed a second half because the reply also asserted `/plugin` was
TUI-only when a `claude plugin` CLI exists. Rule 14 (a command is not verified until it has run in
HIS state) was written after five such failures, then fired again within the hour when a block ran
`mcp-publisher publish` without `mcp-publisher login` and returned 401 token expired.

**The pattern in all of them is the same and it is not carelessness.** Each was a command that was
correct in this container and could not work on the Mac, because the state differed: a file on a
feature branch when `owner/repo` reads the default branch; a script never run against real data; a
manifest key trusted from docs and never checked with `claude plugin details`; an authenticated CLI
whose token had expired. **The fix that actually works is the EXPECT / STOP IF line**, because it
turns a wasted round into a self-diagnosing one.

**Three of my own tools produced wrong output that was presented as evidence:**

- `fd8_prepare_republish.py` wrote a version DOWNGRADE (0.2.9 over 0.2.11) by comparing versions for
  inequality and assuming "different" meant "behind". Restoring the backup then undid the two GOOD
  edits alongside it, which is why the first registry publish shipped with the attribution still
  missing. **A backup restore is not selective.**
- The same script's pin matcher was too narrow and reported "no `mcp>=` dependency found" against a
  package whose own PyPI metadata declares one. **"Not found" from a narrow matcher is
  indistinguishable from "nothing to fix".**
- A throwaway one-liner printed `sorted(releases)[-6:]` and **`sorted()` on version STRINGS puts
  "0.2.11" before "0.2.4"**, so it cut off the very version being checked and read as "0.2.11 is not
  on PyPI". Andrew stopped the session over it, correctly.

**The general form, and it is rule 14 turned inward: a number I print is evidence the reader acts
on, so a sloppy diagnostic costs exactly what a wrong command costs.**

**And the one that nearly shipped:** `mcp_registry/smithery.yaml` described a DIFFERENT SERVER. It
ran `node dist/index.js` for a Python package, listed four tool names against the sixteen the server
actually serves, and made the API key required when the server runs keyless. It was written before
the server was published and never reconciled. Caught only because the tool names were checked
against a live handshake instead of trusted. **Copying it would have made the listing worse while
looking like progress.**

### A PLUGIN'S MCP SERVER GOES IN `.mcp.json`, NOT `plugin.json`

An `mcpServers` block inside `plugin.json` is **silently ignored**. The plugin installs,
`claude plugin validate` passes, and `claude plugin details` reports `MCP servers (0)`. Moving the
identical block to `.mcp.json` at the plugin root registered it immediately as `MCP servers (1)`.

The first version of the test asserted the ignored key, so it went green while the plugin shipped no
server at all. **A test that reads the same wrong file as the code proves nothing.**
`claude plugin details` is the check; `validate` only says the file is well formed.

---

