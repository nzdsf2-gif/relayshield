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
| AWS account | **239677749008.** A command without `AWS_PROFILE=relayshield` resolves to `620534471984` and returns `ResourceNotFoundException`, which looks like a missing resource and is not |
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

They are now in the **drift check only**. The sequence, and it must be in this order:

1. **Watch `lambda_drift_check.yml` for `relayshield-intel-feed` and `relayshield-intel-kev`.** It
   runs daily. A red run naming either is drift, not a broken check.
2. **If either has drifted**, recover it with `recover_live_handler.yml` and reconcile, exactly as
   the four handlers were on 2026-08-26. Do not skip to step 3.
3. **Only once the check is green on both**, add them to `deploy_lambdas.yml` and deploy.

**Until step 3, the feed and KEV halves of A7 (malware label normalisation) are inert.** The code is
in the repo and is not running.

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

- **XSOAR PR #45206 / Tech Alliance (roadmap D3)** — **DONE**, completed weeks ago. Do not
  re-raise it as blocked on "2 named joint customers".
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
