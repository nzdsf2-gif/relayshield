# CLAUDE.md — read this first, every session

## HOW TO DELIVER WORK TO ANDREW — the rule that keeps getting broken

**Claude Code on the web runs in a remote container. It cannot write to
`~/Side SaaS Hustle`. Committing and merging to `main` does NOT put a file on Andrew's Mac.**

This has now cost time in more than one session: a document was written, committed, merged, and
reported as "delivered", and Andrew could not read a word of it. A file he cannot open is not a
deliverable, and describing its contents to him is worse than useless — it reads as sections of a
document that, to him, does not exist.

**So: whenever a session produces a `.md` deliverable — a benchmark, a roadmap, a blog draft, a
brief, a handoff — PASTE THE FULL FILE CONTENTS INTO THE CHAT, inside a fenced code block, in the
same reply that announces it.** Commit it as well, but the chat paste is the delivery. Do not
substitute a summary, a file path, a PR link, or "run `git pull`". Do not wait to be asked.

Andrew saves them into `~/Side SaaS Hustle` by hand. That is the established, working process.

If the file is genuinely too large to paste, say so explicitly and paste it in parts — do not
silently downgrade to a summary.

### When `git pull` fails on his Mac

`~/Side SaaS Hustle` is the local clone. A known recurring failure:

    error: You have not concluded your merge (MERGE_HEAD exists).

Fix, in that directory:

    git status                 # see what is unmerged
    git commit --no-edit       # conclude the in-progress merge
    # or, to abandon it:  git merge --abort
    git -c pull.rebase=false pull origin main

**Never rebase this repo** — always `pull.rebase=false`.

---

## ENVIRONMENT — what this container can and cannot do

| | Status |
|---|---|
| AWS credentials | **None usable.** The `AWS_*` env vars are placeholders; STS returns `InvalidClientTokenId`. Anything touching DynamoDB or Lambda runs on the Mac with `AWS_PROFILE=relayshield` |
| AWS account | **239677749008 is the ONLY RelayShield account.** Every table, Lambda, secret and role lives there. `620534471984` is a SEPARATE account used solely to pre-audit new AWS workflows before they touch production — **no RelayShield resource is ever meant to exist in it.** It is the shell default, so an `aws` command with no `AWS_PROFILE=relayshield` silently resolves to it. **Reads** there return `ResourceNotFoundException`, which looks like a missing resource and is not. **Writes there SUCCEED** — see below |
| GitHub | Read/write via MCP. **Workflow dispatch is blocked** (`403 Resource not accessible by integration`) — Andrew must click *Run workflow* in the UI |
| Egress | Blocked: `*.workers.dev`, `discord.com`, all `zapier.com`, `catalogapi.azure.com`, `powershellgallery.com`, arbitrary vendor sites. Reachable: GitHub, `raw.githubusercontent.com`, PyPI, WebSearch |
| Python | No `boto3`, no PowerShell. Use a throwaway venv in the scratchpad |

---

## COMMANDS HANDED TO ANDREW — his shell is zsh, on macOS

Every command written for him must run **exactly as pasted, in zsh**. Not bash, not "close enough".
Check each one against all five before sending it:

1. **No trailing `#` comments.** zsh does not treat `#` as a comment interactively, so it becomes an
   argument and the command errors.
2. **Quote the space in the repo path.** The clone root is `~/Side SaaS Hustle`, so:
   `cd ~/"Side SaaS Hustle"`. Unquoted, zsh sees three arguments.
3. **The repo root is `~/Side SaaS Hustle`, not `~/Side SaaS Hustle/relayshield`.** `relayshield/`
   is a subdirectory *inside* the repo holding only `README.md` and `mcp-server/`. `build_blog.py`,
   `wrangler.blog.toml` and every tool live at the root. He has landed in the subdirectory and hit
   "No such file or directory" more than once.
4. **Never hand him a `/tmp` path from an earlier session.** macOS clears `/tmp`, and a container's
   `/tmp` never existed on his Mac at all. `/tmp/rsvenv/bin/python` failed on 2026-08-26 for exactly
   this reason, copied out of a repo doc that assumed the venv from the session that wrote it. The
   durable venv is **`~/.rsvenv`**, and any command using it must be preceded by the one-time
   creation line or a check that it exists.
5. **No bash-only syntax.** No `declare -A`, no `<(...)` process substitution in a one-liner, no
   `source` of a bashrc. Anything more involved than a pipeline belongs in a committed script he
   runs, not a pasted one-liner.

The durable venv, created once, because Homebrew Python is PEP 668 externally-managed:

    python3 -m venv ~/.rsvenv
    ~/.rsvenv/bin/pip install boto3

### 7. A fenced code block in a chat reply is a RUNNABLE zsh command block, or it is labelled.

There is no third kind. On 2026-08-29 a YAML fragment from `deploy_lambdas.yml`:

    role-to-assume: arn:aws:iam::239677749008:role/relayshield-github-deploy

was pasted into a bare fence as *evidence* about how the workflow authenticates. Andrew pasted it
into zsh, because that is what a fenced block means, and got `zsh: command not found: role-to-assume:`.

So:

- A block he is meant to run: fence it as ```zsh, and every line in it must be a real command that
  runs as pasted. Nothing else goes in that block.
- A block he is NOT meant to run — file contents, YAML, a log excerpt, JSON, a diff — gets a plain
  English sentence immediately before it saying what it is and that it is not a command, and is
  fenced with its real language (```yaml, ```json, ```text).
- Never mix the two in one block. Never put a `$` prompt prefix in a runnable block, and never put
  output and input in the same fence.

This is the same class of failure as rules 1-5: the command was not wrong, it was not a command.

### 6. Every `aws` command starts with `AWS_PROFILE=relayshield`. No exceptions.

**`620534471984` is NEVER the target of a RelayShield command.** It is the pre-audit account, kept
deliberately separate so a new AWS workflow can be trialled without touching production. It is also
the shell's default profile, which is the entire problem: omitting `AWS_PROFILE=relayshield` does
not error, it aims at the audit account. If a command in this repo, in a doc, or in a chat reply
targets `620534471984`, that command is wrong. There is no RelayShield resource there to talk to.

Rule 6 exists because the table above was read as "a missing profile is a harmless error". It is
not, and 2026-08-29 proved it — for the **third** time across sessions:

    aws dynamodb create-table --table-name relayshield_intel_first_seen ...

ran without the profile and **printed a success block**. It created the table in `620534471984`,
the wrong account, where the Lambda will never see it — and the next command, a read, then failed
with `ResourceNotFoundException`, which is what finally exposed it.

A read against the wrong account is a confusing error. **A write against the wrong account is a
resource that exists, looks right in the output, and is invisible to everything that needs it.**
So prefix every command, including the ones that look read-only, and prefer verifying with:

    AWS_PROFILE=relayshield aws sts get-caller-identity --query Account --output text
    # must print 239677749008

---

## THE DRIFT RULE — the most expensive lesson in this repo

**Anything not in the repo is erased by the next deploy of that component.**

It has happened three times:

1. **2026-08-19** — Telegram help shortcuts and command merges, written on the laptop, deployed by
   hand, never committed. An ordinary `deploy_lambdas.yml` run replaced them with the repo copy.
   Not recoverable from git, because they were never in git.
2. **2026-08-17 → discovered 08-23** — `relayshield-api` hand-deployed. 2,583 diff lines, plus
   `relayshield_sim_swap_consent.py`, a shared **consent** module that existed *only* in the
   deployed artifact. Recovered before the redeploy; a repo-sourced deploy would have deleted it
   with no error anywhere, because the repo's handler never imported it.
3. **The TI demo Cloudflare Worker** — still outstanding. See `lambda_recovery_and_deploy.md` §7.

**Before redeploying anything, check `lambda_drift_check.yml` and open `lambda-drift` issues.
Recover the live artifact into git FIRST.** `recover_live_handler.yml` does this for Lambdas
(dispatch from the Actions UI). Nothing does it for Workers yet.

---

## OPEN TODOS THAT MUST NOT BE FORGOTTEN

Added 2026-08-27. These are blocked on a wait, not on a decision, which is exactly the kind of item
that gets lost between sessions.

### A7 follow-through — two Lambdas with no deploy path

`relayshield_intel_feed.py` and `relayshield_intel_kev.py` were in NEITHER `deploy_lambdas.yml` NOR
`lambda_drift_check.yml`: source in the repo, no automated deploy, no drift detection. That is the
same combination that produced ~1,900 undeployed lines across four handlers on 2026-08-26.

**RESOLVED 2026-08-29.** Run 9 of `lambda_drift_check.yml` (2026-08-28 22:49, red, 2 annotations)
named both functions. The diffs were read in full and were **one-directional**: the live code is
`main` minus the A7 commit and nothing else. No live-only symbol, no live-only import, nothing to
recover. That is not the 2026-08-26 hand-deploy pattern, it is "the repo is ahead and there is no
deploy path" — so the check could never have gone green on its own, and the original step 3
("only once the check is green") was unreachable by construction.

Both are now in `deploy_lambdas.yml`, with `relayshield_intel_labels.py` mapped alongside them.
**The next merge to `main` touching either file deploys them and the drift goes away.** Until that
merge lands, the feed and KEV halves of A7 (malware label normalisation) are still inert.

The general rule this replaces it with, for the next handler that turns up unmapped:

1. A red drift run is the alarm, always. Read the diff before doing anything.
2. **Only if the live side contains something `main` does not** — a symbol, an import, a whole file
   — recover it with `recover_live_handler.yml` and reconcile, exactly as the four handlers were on
   2026-08-26.
3. If the diff is only `main`'s own commits appearing in reverse, live is simply stale. Add the
   function to `deploy_lambdas.yml` and deploy; there is nothing to recover.

Note on the deploy probe: `relayshield_intel_feed.py` and `relayshield_intel_kev.py` begin ingesting
on the first line of `lambda_handler`, and the deployer invokes everything it deploys to prove the
package imports. Both now return early on `{"source": "ci.import-probe"}`. Any future handler that
does real work on invoke needs the same three lines.

### NEXT SESSION, TOP OF THE LIST — record the Rain demo video

Carried explicitly to 2026-08-30 at Andrew's instruction. It has slipped once already. It is not
blocked on anything: no code, no AWS, no approval. Details in the section below.

### OpenRouter key-revocation webhook — build it when the corpus has OR tokens

Sequenced behind data, like A8, and for the same reason.

The LLMjacking detector's OpenRouter pattern shipped in `844a2c3` (deployed 2026-08-27 11:11). It
has been live two days, so **there is no corpus of captured `sk-or-v1-*` keys yet** and nothing to
notify anyone about.

When there is, the integration is the revocation webhook: RelayShield detects a leaked OpenRouter
key in a criminal Telegram channel and calls OpenRouter to revoke it, before the key is drained.
That is the thing their own tooling cannot do, because they cannot see the channel.

**Trigger to build:** the first non-zero count of `sk-or-v1-*` in `relayshield_intel_iocs`. Check it
before writing any of it. Do not build the webhook against zero rows, and **do not quote a captured
OpenRouter key count to OpenRouter, Stripe, or anyone else until the category clears 100** — the
standing measurement rule applies here with force, because this is a number that would be checked.

Rationale, and why this is the right ask of Stripe post-acquisition, is in
`openrouter_stripe_integration_angle.md`.

### Rain Agentic Startup Program — record the demo, then submit

Not blocked on anything. The reason it is here is that it is the one item where a two-minute video
beats every paragraph we could write, and video is the kind of task that slips.

**Record a 2-minute unattended demo:** an agent discovers an endpoint, calls `mcp-registry-risk`,
**refuses a typosquatted one**, then pays the legitimate one over x402 (USDC on Base) with no human
in the loop and no account.

**Then submit to both:** Rain's **Agentic Startup Program**, and **apa@rain.xyz**, the Agentic
Payments Alliance's stated contact for organisations wanting to join.

Why this framing and not a deck: Rain's Agent Control Layer already answers "is this agent allowed
to spend this much". Nothing in it answers "is the thing it is about to pay legitimate". An agent
with a valid card, inside its limits, paying a fraudulent API is a fully authorised transaction. The
demo shows that gap being closed in the only way that is not arguable.

Full analysis, including where a pre-payment check could sit across the 26 Alliance members and why
Sardine and Chainalysis must not be pitched against, is in `socradar_gap_closure_roadmap.md`.

### A8 — grow `tg_handle`, but only after the filter

Sequenced behind a two-week measurement, deliberately. The evidence for waiting is already in:
`relayshield_operator_identities` holds 7 rows, every one at `sightings=1`, several of them English
words (`catching`, `normanonrock`) caught because `_RE_TG_CHANNEL` matches any `@mention`.

**Growing collection before filtering multiplies the noise, not the signal.**

- Watch `tools/check_operator_identities.py`'s cross-channel number. Handles seen in 2+ channels are
  the exclusive asset; a row count is not.
- If it is still 0 after two weeks of hourly runs while channels are producing messages, the problem
  is extraction and the fix is a filter, not more collection. Strongest option: require a SECOND
  sighting before writing the row at all, which filters on repetition rather than guessing what a
  handle looks like.
- **Do not quote a `tg_handle` exclusive-share number until the category clears 100 collected
  indicators and `exclusive_share_by_category.py` has run on it.** This is the number most likely to
  be quoted at a competitor, so the standing rule applies with extra force.

---

## MEASUREMENT DOCTRINE — non-negotiable

**Never quote the ~511K corpus headline.** Most of it is ingested public feeds (abuse.ch URLhaus /
ThreatFox / Feodo, CISA KEV) that every target buyer already has. Quoting it nearly killed the
Segment 1 outreach in front of people who would have checked.

- The KPI is **`measured_exclusive_share`, per category** —
  `tools/exclusive_share_by_category.py` (needs AWS, so it runs on the Mac).
- Any category under **100 collected indicators** is not defensible and does not get quoted.
- **Never invent a number for a customer-facing or competitor-facing document.** Use an explicit
  `MEASURE` placeholder with the command that fills it.
- Growing total volume by ingesting another public feed makes the headline better and the product
  worse.

---

## STATUS CORRECTIONS — docs that are stale

`NEXT_SESSION_2026-08-20.md` is the last full handoff, but items have completed since and the file
was not updated. **Ask before treating anything in its "carried forward" list as open.**

Known completed after that handoff was written:

- **XSOAR PR #45206 / Tech Alliance (roadmap D3)** — **THIS ENTRY IS WRONG. Re-checked 2026-08-29.**
  `git ls-remote https://github.com/demisto/content 'refs/pull/45206/*'` returns **both**
  `refs/pull/45206/head` and `refs/pull/45206/merge`. GitHub deletes the `/merge` ref once a PR is
  merged or closed, so its presence means **#45206 is still open**. The contrib branch
  `refs/heads/contrib/nzdsf2-gif_add-relayshield-pack` is also still live in their repo, and their
  "Auto Merge Docker Update" workflow was still firing against it on 2026-08-29. Automation does not
  run on a branch that merged weeks ago.

  Two separate things were being conflated under "DONE", and they must stay separate:

  1. **The content pack PR (#45206)** — technical, in `demisto/content`, **still open**.
  2. **The Palo Alto Tech Alliance partnership** — commercial, and now gated on Palo Alto's new
     requirement of **3 named joint customers**.

  Neither blocks the other. The pack is a public contribution and does not need the Alliance. Do not
  report either as complete without checking the refs above.
- **DFK outreach** (Top-10 item 7) — done 2026-08-22.
- **Ronin `ronin:` prefix normalise** (Top-10 item 8) — done.

---

## Writing conventions

- **No em-dashes** in published copy. Applies to the short syndication versions too.
- Blog files carry a `NOT FOR PUBLICATION` line; everything below it is internal plan and checklist.
- **Do NOT post to X** (`@RelayShieldHQ` suspended) or **Hashnode** (abandoned 2026-07-29).
- Medium: **import with the canonical URL, never paste** — Medium has no Markdown paste.
- Channel order: `blog.relayshield.net` canonical → Medium → LinkedIn → Telegram → Farcaster →
  Mastodon.
- Length limits: Mastodon 500 chars · Farcaster ~1024 bytes · LinkedIn 3000 · Telegram 4096.
  Write each short version to its own limit.
