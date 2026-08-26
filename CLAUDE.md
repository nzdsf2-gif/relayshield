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

**macOS zsh does not treat `#` as a comment interactively.** Never append a trailing comment to a
command handed to Andrew — it becomes an argument and errors.

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

## SESSION STATE — 2026-08-24 (read this before touching TI demo, INTEL-2, or relayshield-mcp)

**PR #12** (`claude/redeploy-relayshield-api-5e5v2h` → `main`, 13 commits) is open and
mergeable but **not yet merged**. It carries everything below on the `rs-teleport`/`main`
side. Check its status before assuming any of this is on `main`.

**TI demo (`relayshield-ti-demo` Cloudflare Worker) — recovered, fixed, deployed, verified live.**
Recovered the hand-deployed Ransomware Victims tab (§7 of `lambda_recovery_and_deploy.md`),
re-derived it as clean source wired to `handle_ransomware_risk`'s `corpus_listing` mode. Two
mistakes made and fixed during recovery, both worth remembering: (1) rebuilding from the
pre-recovery source clobbered an independent 2026-08-22 header-stat correction ("5.4M+ IOC
indicators" was citations mislabelled as indicators) — restored to 500K+ distinct / 5.8M+
citations. (2) the new render function was defined but never added to the `${fn.toString()}`
list that ships render functions into the page's `<script>` block — that pattern (real
server-scope JS functions serialized into the client via `.toString()`) is easy to miss when
adding a tab; check the list in `renderFunctions()` any time a tab is added. Both caught by
actually executing the deployed bundle in Node against the real API, not by reading the diff —
do that again, not just `node --check`, before calling a Worker change done.

Also found and fixed: the ransomware-victim name-extraction regex (`_RE_RANSOM_VICTIM` in
`relayshield_intel_monitor.py`) was producing garbage ("rs Remote Control.", "d Linux Machines
Into SOCKS5...") from ordinary English sentences containing "hackers"/"compromised"/etc. — global
`re.IGNORECASE` let `[A-Z]` match lowercase, defeating the proper-noun check. Fixed; the 19
garbage rows already in `relayshield_ransomware_victims` were deleted. **Not fully addressed:**
false positives from ransom-note boilerplate ("Recover Your Files" read as an org name) are a
separate, still-open class of noise in the same table.

**INTEL-2/5 (Telegram monitor) — still down. Root cause fixed and deployed; session itself is not recovered.**
`relayshield/telethon_session` was revoked (`AuthKeyDuplicatedError`) 2026-08-24 ~08:50 UTC.
Root cause, confirmed via CloudWatch/CloudTrail: `relayshield-intel-discovery` was invoked
manually while `relayshield-intel-monitor`'s scheduled run was still finishing — both build a
`TelegramClient` from the same session, and each held its own DynamoDB lock under a *different*
key in the same table, so neither blocked the other. **Fixed and deployed**: both functions now
share one `LOCK_ID` ("singleton"), and a CI guardrail (`.github/workflows/security_audit.yml`,
"Guard against unlocked Telegram sessions") fails the build if any third file constructs
`TelegramClient(StringSession(...))` outside the two already-locked files. This is the *second*
time this exact failure class has happened (also 2026-07-23) — if it happens a third time despite
the guardrail, something is bypassing it, look there first.

**The session itself is still revoked and blocked** — this needs a human to actually receive an
OTP, and as of session end neither of two different phone numbers, on different carriers, with
WiFi off, via SMS, in-app, or a fresh official-app login, received one after several hours. That
rules out the usual causes (flood-wait, wrong number, shared network/carrier) and points at
something regional/Telegram-side, not fixable from a terminal. `regenerate_telethon_session.py`
(interactive, run locally — `.telethon_venv` in `~/Side SaaS Hustle` has the deps) is ready the
moment a code actually arrives. Do not re-run it repeatedly while troubleshooting delivery —
repeated `SendCodeRequest` calls risk their own flood-wait on top of whatever this is.

**relayshield-mcp (submodule, own repo at github.com/relayshield/relayshield-mcp) — several fixes plus a new Apify Actor.**
Added `check_llm_credential_exposure` (LLMjacking) tool. Fixed `mcp>=1.0.0` having no upper
bound — `mcp` 2.0.0 breaks this server's `Server.list_tools`/`call_tool` API outright; capped
`<2.0.0`. Fixed the root `Dockerfile`: was pinned to a stale PyPI release (0.2.3, this repo only
publishes to PyPI on a GitHub Release, not every push — 0.2.11 is on `main`, not on PyPI yet) and
its `CMD` ran `python -m relayshield_mcp`, which has never worked (no `__main__.py` — added one).

Built `.actor/` — an Apify Actor wrapping the existing stdio MCP server (unchanged) in a
FastMCP proxy, exposed over Streamable HTTP at `/mcp` for Apify's Standby mode. Added per-call
`rs_api_key`/`x_payment` tool arguments (injected onto every tool in `list_tools()`, preferred
over the env-var defaults in `call_tool()`) so a shared multi-tenant deployment lets each calling
agent pay for its own usage via x402, matching CDP bazaar's per-endpoint pricing, instead of every
caller sharing one operator credential. Verified end-to-end through the real Apify Standby proxy,
not just locally. Build `0.1.3` succeeded; Actor is **Private**, blocked on Apify's business
verification (submitted, 1-2 day lead time per Apify) before it can be Published. **Apify's own
"Pay for usage" platform pricing is separate from and stacks on top of RelayShield's x402
pricing** — already flagged to Andrew, worth re-flagging if this comes up again: publishing does
not make Apify's cut free just because the pass-through relay handles RelayShield's side.

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
