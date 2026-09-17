# Answers, 2026-09-17

Six questions. Where I was wrong, that is said first and plainly.

---

## 0. I was wrong about the WhatsApp front door, and the command that fooled me

You said we built it last session. **We did**, and my check said otherwise:

```text
git --no-pager log --all -S "wa.me" -- '*.py' '*.js'     -> nothing
```

**`--all` means every ref THIS CONTAINER HAS FETCHED, not every ref on origin.** A
session starts with `main` and its own branch. I had run `git fetch origin main`, so
`--all` covered two refs and the branch holding the answer was not one of them. One
`git fetch --all` returns it instantly, which is how I found it in the end. The
pathspec was a second hole: `*.py` and `*.js` would have missed a `wa.me` that landed
only in a `.md`.

It is on `origin/claude/laughing-bell-gxagsd`, commits `b641375` and `9e51b56`,
**unmerged**. The cost was not the wrong answer, it was that I built a recommendation,
a Top 10 item and a CLAUDE.md section on top of an absence I had not established.

**The rule, now recorded: before claiming something was never built,
`git fetch --all --prune` first, then search with NO pathspec.**

---

## 1. Bundle B doc: updated

`bundle_b_scope_2026-09-15.md` now opens with the shelf as it stands, so nothing has
to be inferred:

    Bundle D   prod-kkvurtspreofy    LIVE, public
    Bundle A   prod-f5qkfsxlxs4qg    LIVE
    Bundle B   no entity yet         change set written

**Bundle A is live, is not outstanding, and is not a prerequisite for Bundle B.** Every
bundle after D gets its own SaaSProduct entity, so Bundle B cannot touch or queue behind
either live product. The old claim and how I produced it stay in section 5, because the
method is what recurs.

**Two other things changed in that file:**

- The merge block named a branch from two sessions ago. It names this one now.
- Section 4 was titled *"the two real blockers"*. It is **one** blocker and one that
  turned out not to be. The catalog IAM grant is `tools/apply_marketplace_catalog_policy.sh`,
  already written, already targeting `relayshield-github-deploy`, never run. I had read
  the runtime role's snapshot and concluded the grant needed the IAM split. It does not.

---

## 2. Bot directories as a readable file

`bot_directories.md`, sent with this. **It is GENERATED from `bot_directories.json` by
`tools/bot_directories_md.py`** rather than written twice, because you read the markdown
and the funnel counts from the JSON, and two files that must agree with nothing checking
them is the defect this repo has paid for five times.

Eight destinations, BotsArchive folded in from the other session's measurement. Regenerate
after any change with `python3 tools/bot_directories_md.py --write`.

**The one line worth carrying out of it:** a bot key needs no registration anywhere, which
is the opposite of the Mini App rule. The unrecoverable mistake is leaving the
`?start=SRC_` suffix OFF, because those arrivals are organic `/start` traffic forever with
no unmatched row to find later.

---

## 3. WhatsApp: pointing at it, and what I added

### What existed already, on that unmerged branch

`parse_wa_source()` in the webhook, parsed **before** the user lookup (a front-door
arrival is by definition unknown, and the unknown-user branch returns 200 and stops, so
parsing after it would attribute every arrival to nothing forever). The token is stripped
from the body. Links on the blog footer (`wa-blog`) and the Mini App (`wa-miniapp`). A
WHATSAPP funnel stage. `tools/wa_front_door_link.py`. 18 tests. It also fixed a real
defect in passing: the inbound log line was writing the customer's phone number in the
clear into CloudWatch.

### What I added this session

**Two placements that were named and never built.** The link tool already listed
`wa-devs` as a destination and the developers page had no WhatsApp mention at all.

- **`api.relayshield.net/developers`**, key `wa-devs`, one quiet footer line. **It reads
  the number from Secrets Manager at request time rather than carrying a constant** --
  that Lambda already reads three secrets, and a third committed copy of the number would
  be a copy nothing pins.
- **The `checkemail@` reply**, key `wa-email`. This is the highest-intent surface we
  have: somebody forwards a suspicious email, has no account, and the reply's only onward
  link is a website. A `wa.me` line gives them a channel that needs no signup and that the
  bot can alert on later, which an email reply cannot.

**`tools/wa_front_door_link.py --write`**, so filling the number is one command instead of
three hand edits across three Workers. It refuses to CREATE a `WA_NUMBER` line and only
ever replaces one that exists, because appending a second `const` declaration is a
SyntaxError that would stop the Worker deploying and name a line nobody wrote.

**Guards:** 22 tests now. Every Worker the tool writes must carry the same number; each
must use a DISTINCT key; the Lambda must hold no constant; and the developers page must
substitute `<!--WA_FRONT_DOOR-->` BEFORE `_strip_html_comments` runs. That last one
matters because the placeholder IS an html comment: strip first and it is deleted, every
later replace matches nothing, and the page renders perfectly with no link and no error
anywhere. Both new guards were proven by reintroducing their defect.

### The one thing blocking all of it

**`WA_NUMBER` is the empty string in all three Workers, so every link renders as nothing
today.** That is fail-closed on purpose: `wa.me` answers a malformed number with HTTP 200
and an "invalid" page rather than a 404, so a broken front door looks live to every probe
we own. The number is in Secrets Manager and no session can read it.

### And the honest limit, which survives my being wrong about the code

The webhook's stranger path is better than it was -- it leads with what the bot does
instead of a signup wall -- but **it still cannot run a check for somebody without an
account.** Telegram can: a stranger gets keyless checks, inline mode in a group, and the
Mini App, none of which needs an account. WhatsApp has none of those.

**My recommendation, and it is yours to overrule because it commits a day:** place the
links now (they cost nothing and the attribution is correct), and make the NEXT WhatsApp
build a keyless first-contact check -- the same `/v1/link-check` and `/v1/wallet-risk`
pair the Telegram widget already calls, both keyless, both capped per source. Roughly a
day. Until that exists, every link we place converts attention we already had rather
than creating reach, because WhatsApp has no directory ecosystem to be listed in.

---

## 4. Apify: ignore it

**Your dashboard answers it.** Free usage **$0.06 of $10.00**, with $9.94 remaining, and
0.2754 compute units against a billing period running to Sep 23. You are at **0.6% of the
allowance.**

The email is about the **Maximum platform usage per month** limit -- a hard cap, not a
bill. Apify's own documentation is explicit that exceeding it suspends platform services
rather than charging on. Yours is a custom limit at $10 where the Free plan default is $5,
so when it expires the cap halves.

**$0.06 is nowhere near either number.** Nothing stops, nothing breaks, and there is no
plan to upgrade. Ignore it.

**One thing worth knowing rather than acting on:** the Actor runs in Standby, which is
billed for active time, and $0.06 a month says it is barely waking up. That is fine. It
also means the Actor is doing almost nothing for us, which is worth remembering when the
Apify writers-programme article comes round and its premise is that we built and ran the
thing.

**And nothing watches it.** `tools/check_hf_space.py` probes both HF Spaces every six
hours and opens an issue on failure; there is no equivalent for the Actor, so if it did
go dark we would learn from a prospect. Small, and not this week's problem.

---

## 5. FD-12: what the task is, and how to submit

**The task is a form. The artefact is finished.**

`FRONT_DOORS.md` has carried FD-12 as **ROUTE OPEN, ARTEFACT BUILT** since 2026-09-05.
Anthropic's `claude-plugins-official` README says in its own words that *"Third-party
partners can submit plugins for inclusion in the marketplace"*, and names the route. The
stated bar is *"External plugins must meet quality and security standards for approval"*,
unenumerated.

**What we ship, and it is all in the repo and tested:**

- `plugins/relayshield/.claude-plugin/plugin.json` -- the plugin manifest
- `.claude-plugin/marketplace.json` at the repo root -- so this repo IS a marketplace
- `plugins/relayshield/skills/` -- the `relayshield-agent-bait` skill, with
  `.claude/skills/` a symlink to it rather than a second copy
- `plugins/relayshield/.mcp.json` -- the MCP server, pinned `relayshield-mcp>=0.2.10`
- `test_agent_bait_skill.py` pins both manifests, that they agree on the plugin name,
  that the source path resolves, and that the declared `skills/` reaches the SKILL.md

**STEP 1 -- ANDREW RUNS THIS.** Confirms the marketplace resolves from GitHub's default
branch, which is what a stranger's install actually reads:

```zsh
cd ~/dev/relayshield
git --no-pager ls-tree origin/main --name-only | grep claude-plugin
```
EXPECT: `.claude-plugin` on its own line.
STOP IF: nothing prints. The manifest is not on `main`, so `owner/repo` installs cannot
find it and the submission would point at a marketplace nobody can add. Tell me and I
will say which branch carries it.

**STEP 2 -- ANDREW RUNS THIS.** Proves the install path a reviewer will take. The `claude`
CLI form, not the `/plugin` TUI form, because the CLI works in more places:

```zsh
claude plugin marketplace add nzdsf2-gif/relayshield
claude plugin install relayshield@relayshield
claude plugin details relayshield
```
EXPECT: `MCP servers (1)  relayshield` in the details output.
STOP IF: `MCP servers (0)`. That means the server block has moved back into
`plugin.json`, where it is silently ignored. The working key is `.mcp.json`.
STOP IF: `Marketplace file not found`. That is step 1 failing, not a broken manifest.

**STEP 3 -- ANDREW CLICKS THIS.** The submission form:
<https://clau.de/plugin-directory-submission>

Fields to expect and what to put:

| Field | Value |
|---|---|
| Plugin name | `relayshield` |
| Marketplace / source | `nzdsf2-gif/relayshield` |
| What it does | Screens a repository's agent-facing instructions before an agent reads them: README, AGENTS.md, CLAUDE.md, .cursorrules, copilot-instructions, mcp.json, smithery.yaml. Reports what those instructions would cause an agent to DO, and checks every referenced domain against a criminal indicator corpus. |
| Website | `https://api.relayshield.net/developers` |
| Contact | `andrew@relayshield.net` |

**Do not describe it as "a security scanner".** The differentiator is the direction: it
reads files somebody ELSE wrote that your agent is about to act on, which is the opposite
of what a normal scanner does and is the thing no incumbent covers.

**UNVERIFIED:** clau.de is egress-blocked from the container, so I have not seen that
form and the field names above are what a submission of this kind normally asks for. If
the form asks for something not here, send me the field and I will write the answer.

**And the question this rests on:** the repo records FD-12 as never submitted. If you
already submitted it, say so and I will correct the row -- a doc recording an open item is
a lead, not a fact, and that cuts both ways.

---

## 6. Typesafe.ai: join the waitlist, scope nothing

**There is a real integration angle, and it is narrower than it first looks.**

TypeSafe emerged from stealth on 2026-09-15 with **Jev**, a "System One" model that takes
a piece of state plus a list of typed questions and returns typed answers -- a choice from
a set you supplied, a score on a rubric, or a yes/no -- **each carrying its own confidence
value**. Not chat. Their launch materials claim 20-200x faster and 40-400x cheaper than
comparable LLMs, at $0.042 per million input tokens with output billed at zero. Founded by
Diogo Almeida, ex-OpenAI, ~$40M led by DCVC.

**We already do exactly that shape, in one place.** `relayshield_intel_classifier.py`
invokes Claude Haiku 4.5 through Bedrock, hands it a channel record (username +
description + discovery provenance) and gets back APPROVE or REJECT plus a category. That
is a typed decision over a small piece of state, which is Jev's stated use case almost
word for word.

**Three places it would fit, ranked by whether it improves anything:**

1. **`agent-bait-scan`'s false-positive rate (ABS-1, an open item).** The strongest fit.
   That endpoint decides whether a repo's instructions are baiting an agent, its FP rate
   has never been measured, and a published AWS dimension is gated on measuring it. A
   typed score with a native confidence value is what that verdict wants, and it is not on
   a customer's critical path while we measure.
2. **The intel classifier.** Its docstring says it "defaults to REJECT when there isn't
   enough signal to be reasonably confident" -- confidence expressed as a prompt
   instruction rather than returned as a number. Jev returns it natively. A real
   improvement in kind rather than in cost.
3. **`checkemail@`'s scoring model.** 78 verdict tests, and its worst historical defect
   was a model that counted flags instead of weighing them.

**Why I still recommend scoping nothing:**

- **We have no cost problem.** The one model call we make runs on a backlog of pending
  channels, not at customer request time. 40-400x cheaper than approximately nothing is
  approximately nothing.
- **The classifier's own docstring says why Bedrock was chosen: "zero new vendor/secret --
  same AWS IAM already used everywhere else".** Adding TypeSafe reverses a decision that
  was made deliberately, for a saving we do not need.
- **Those speed and cost figures are their own launch materials.** MEASUREMENT DOCTRINE
  applies to numbers we quote inward as much as outward.
- **A lab that left stealth two days ago is not a dependency for a customer-facing
  verdict.** No SLA, no track record, waitlisted access.

**So: join the waitlist. It is free, it commits nothing, and it buys an option.** When
access arrives, point it at ABS-1 and nowhere else -- measure agent-bait's false-positive
rate with a confidence-carrying typed score, compare it against the heuristic we already
run, and let that measurement decide whether anything else moves. That is a half-day
experiment against an open item, not an integration.

**This is my recommendation and it is yours to overrule** -- it is a judgement about where
a day goes, not a fact about the code.
