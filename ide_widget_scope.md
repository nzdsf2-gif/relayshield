# A RelayShield IDE widget: is there a rsscan-shaped benefit?

Written 2026-09-09, in answer to: *"In the past we launched a GH precommit webhook as a discovery
surface. Is there a similar benefit to build a RS IDE widget to detect malware, vulnerabilities,
backdoors and prompt injection attacks?"*

**Short answer: yes to the moment, no to the scope, and not yet to the build.**

One of the four categories is genuinely ours and has no incumbent in the IDE. The other three are
either not something this product does or are somebody else's much better product, and shipping all
four would invite a comparison we lose on three of them. And the premise the question rests on --
that the pre-commit hook was a good discovery surface -- **has never been measured**, though it has
been measurable since 2026-09-03. That measurement is now one command and it should decide this.

---

## 1. Two corrections to the premise, and the second one is the important one

**rsscan is a pre-commit HOOK and a GitHub Action, not a webhook.** It runs locally, on the
developer's machine, against `git diff --cached -U0`, before the commit enters history. No network
call, no account, no API key. That distinction matters here because it is exactly what makes it an
*IDE-time* artefact rather than a CI one, which is the property the question is really asking about.

**Its benefit is unmeasured.** `rsscan` and `rsscan-deps` have both been registered keys in
`_SOURCE_BANNERS` since 2026-09-03, so every arrival on `api.relayshield.net/developers` carrying
`?source=rsscan` has been attributed and logged in CloudWatch this whole time. Nobody has ever
counted them. FD-1 is recorded as **DONE** -- v0.2.1 published, Marketplace badge live -- and "done"
is a fact about shipping, not about reach.

So the sentence "the pre-commit hook was a good discovery surface, therefore an IDE widget would be
too" has an unverified first half, and this repo's own doctrine says what to do about that rather
than reasoning past it. The check does not need AWS in this container; it moves:

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/source_arrivals.py --days 90 \
        --key rsscan --key rsscan-deps --key github --key pypi --key tg-widget

`tools/source_arrivals.py` is written and committed for this. It reports the window it **observed**
rather than the one asked for, prints `unmatched:` keys first because each one is a live link
pointing at a key that does not exist, and distinguishes ZERO ARRIVALS from UNREGISTERED -- those are
different findings with different fixes and conflating them is FD-8, four months of it.

**Cost asymmetry, and it is the argument for doing this first:** the measurement is minutes. The
widget is a week. Spending the week on the strength of an unread number is how a plan ends up
describing somebody else's company.

---

## 2. We already have three IDE surfaces. A widget would be the fourth, not the first

Worth listing, because "build an IDE widget" reads as though the IDE is empty for us and it is not:

| Surface | What it is | Reaches | Distribution state |
|---|---|---|---|
| `relayshield-mcp` on PyPI | stdio MCP server, 16 tools | Any MCP client: Claude Code, Cursor, VS Code, Windsurf | Live, 0.2.11. **44 downloads/week, 6/day** -- the realest adoption signal we have, and it has had the least marketing |
| `plugins/relayshield` | Claude Code plugin: agent-bait skill + `.mcp.json` | Claude Code | Installable today. FD-12 (Anthropic directory) and FD-13 (xAI, PR #612) are its routes |
| `rsscan` | pre-commit hook, GitHub Action, GitLab CI, Docker, CircleCI orb | Any repo | FD-1 DONE. **FD-2 DEAD** -- see below |

The `relayshield-mcp` line is the one to sit with. It is a stdio MCP server, and the population that
can install it is much wider than "Claude Code users": Cursor, Windsurf and VS Code with Copilot all
take MCP servers. **So before building an extension to reach VS Code users, establish whether MCP
already reaches them.** If it does, the marginal reach of an extension is much smaller than it looks.
That is a checkable fact about current VS Code and Copilot MCP support, and I have not checked it --
it is step two below, and it is cheap.

---

## 3. The four categories, tested against what this product actually does

This is where a widget scoped as asked would go wrong, and the failure mode has a name in this repo:
the `_APIFY_BANNER` mistake, naming a capability on a live surface that the thing does not have.

| Category | Can we? | Verdict |
|---|---|---|
| **Vulnerabilities** | **No.** There is no SAST anywhere in this codebase | **Drop it.** Semgrep, Snyk, SonarLint and CodeQL all ship free IDE extensions with years of rules and full-time teams. A RelayShield "vulnerability" checkbox is a losing comparison offered voluntarily |
| **Malware** | **Not as stated.** We do not analyse code for malicious behaviour. We match indicators -- domains, wallets, credentials -- against a corpus | **Rename, do not drop.** "Does this code reference infrastructure our corpus has seen in criminal channels" is true, defensible and narrow. "Malware detection" is not |
| **Backdoors** | **Partly, and the part is real.** A hardcoded C2 domain or exfil endpoint matched against the corpus is exactly what we can see and what a SAST tool cannot | **Keep, narrowly**, and describe it as the indicator match it is |
| **Prompt injection / agent baiting** | **Yes, and uniquely.** The skill is written, `/v1/payg/agent-bait-scan` and `/v1/metered/agent-bait-scan` are live at $0.50, and the handler now logs what it fires on | **This is the product.** No incumbent occupies it in the IDE |

**Three of four are not ours. One is, completely.** A widget that claims all four is a worse product
than one that claims one, because the three weak claims are the ones a developer checks first.

---

## 4. Why agent-baiting is specifically an IDE problem, and rsscan cannot host it

The payload lives in files -- `README.md`, `AGENTS.md`, `CLAUDE.md`, `.cursorrules`,
`copilot-instructions`, `mcp.json`, `smithery.yaml` -- that a developer opens and an agent reads. No
linter looks at them. No SAST tool parses them. They are prose to every existing tool in the editor,
and instructions to the agent sitting next to it.

**And the direction is the whole point.** rsscan asks *"what am I about to commit"* -- it reads
`git diff --cached`, your own authored change. Agent-baiting asks *"what did somebody else write,
that my agent is about to read"*. You are not the one committing the malicious README; you are the
one cloning the repo that carries it.

So rsscan is the wrong host, and that is worth stating plainly because "add a detector to the thing
that already ships" is the obvious cheap answer and it does not fit. The artefacts that already face
*other people's* files at IDE time are the MCP server and the Claude Code skill -- which is to say,
**the capability is built and the question is purely one of reach.**

---

## 5. The real question is the route, and FD-2 is why

The rsscan precedent's most useful lesson is not that the hook worked. It is that **the artefact
shipped and the distribution route died on the destination's published rules.** FD-2, pre-commit.com's
hooks index: a curated page requiring >500 stars AND hooks that operate on files. rsscan fails both.
Effort spent, door shut, and the rules that shut it were readable in advance.

That happened again with CrewAI PR #6550 (open, unreviewed, months) and nearly again with FD-2's
sibling. The standing rule from all three: **do not scope the work before reading the destination's
rules.**

So the honest comparison is not "hook vs widget", it is "which doors are open":

| Route | Status | Note |
|---|---|---|
| **VS Code Marketplace** | Believed open, free, uncurated, no star gate | **Materially better than FD-2 turned out to be** -- if true. Microsoft's publishing requirements have NOT been read. That is step one, not step two |
| **JetBrains Marketplace** | Believed open, moderated with a review | Same: unread |
| **Anthropic plugin directory** | **ROUTE OPEN** (FD-12), artefact built | Reaches the moment already, with no new codebase |
| **xAI plugin marketplace** | **SUBMITTED**, PR #612 (FD-13) | Awaiting review |

The two rows at the bottom already carry the agent-bait check to a developer at the moment of the
decision. The two at the top would carry it to a *different and larger* population -- but nobody has
read whether they take it, and that reading is an afternoon.

---

## 6. Recommendation

**Not "no". "Not in that shape, and not before three cheap checks."**

**Step 1 -- measure the precedent. One command, minutes.**
Run `tools/source_arrivals.py` as above. If `rsscan` has produced arrivals, the analogy holds and the
widget has evidence behind it. If it has produced approximately none across the whole observed
window, then the pre-commit hook was a good *artefact* and a poor *discovery surface*, and building a
fourth one on the same theory is the expensive way to learn that twice. Either answer is worth
having and neither is available today.

**Step 2 -- establish whether MCP already reaches VS Code and Cursor users.** If `relayshield-mcp`
installs into VS Code + Copilot as an MCP server, the extension's unique reach shrinks to developers
who want a passive check with no agent involved, which is a much smaller and more honest claim.

**Step 3 -- read the VS Code Marketplace publishing rules before scoping anything.** FD-2 is the
entire argument for putting this before the build rather than after it.

**Then, if all three come back favourably, build ONE thing:** an extension that screens *incoming*
agent-facing files -- on clone, on a new dependency, on an `mcp.json` edit -- for injected
instructions, and checks the domains they reference against the corpus. Not four categories. One,
described accurately, in the place where no other tool is looking.

**And one constraint on the build, from this repo's own scar tissue:** the check must be the *same
implementation* as the skill and the endpoint, imported or called, never reimplemented. This
codebase already carries four copies of one pattern table with nothing verifying they agree, and the
Mini App went out of its way not to become the fifth. An extension carrying a sixth copy of the
agent-bait heuristics would drift from the endpoint within a release, and the drift would be silent.

---

## 7. What would change this answer

- **`rsscan` arrivals come back materially non-zero.** Then the analogy is evidenced rather than
  assumed, and step 3 becomes urgent rather than merely cheap.
- **MCP turns out not to reach VS Code or Cursor in practice.** Then the extension is reaching a
  population nothing of ours can currently touch, which is the strongest possible case for it.
- **The agent-bait false-positive rate gets measured and is good.** `tools/agent_bait_fp_rate.py`
  exists for this and refuses to report a number under 30 adjudicated rows. A widget that flags
  legitimate repositories is a widget that gets uninstalled, and the FP rate is the same gate that
  currently holds ABS-1 (the Bundle D dimension) closed. **The same measurement unblocks both**,
  which makes it the highest-leverage thing on this page.
