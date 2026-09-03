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

### 12. Vendor documentation can contain YOUR OWN API KEY. Read before pasting.

Added 2026-09-03. A Stripe docs page was pasted into chat with its "Copy for LLM" content, and the
curl samples had the account's **live test secret key interpolated into them** — Stripe personalises
`sk_test_...` into the examples for a signed-in reader. Nobody typed a credential; copying the page
carried one.

It was a test-mode key, so no real money is reachable, but test data includes real email addresses
whenever a real address was used to test. Roll it in the Dashboard under Developers, API keys, and
treat the class as: **any vendor doc page read while signed in may be personalised with your
credentials.** Skim what you are pasting for `sk_`, `rk_`, `Bearer `, `api_key=` and long opaque
strings before it leaves the machine.

Nothing in this repo should ever carry one either: `tools/` scripts read secrets from Secrets
Manager at runtime, and that is the pattern to follow rather than an env var in a doc.

### 9. Every `aws` command in a pasted block uses `--no-cli-pager`.

Same failure as rule 8, different tool. AWS CLI **v2 pipes output through a pager** when stdout is
a terminal. On 2026-08-29 an `iam list-role-policies` on a role with 20-odd policies stopped a
four-command diagnostic block dead at the third command, ending in `:`, and the fourth never ran.

Either `--no-cli-pager` on each command, or `export AWS_PAGER=""` as the first line of the block.
Committed scripts should do both, as `tools/setup_first_seen.sh` does.

### 8. Every `git` command in a pasted block uses `--no-pager`.

`git log`, `git diff`, `git show` and `git branch` open `less` when stdout is a terminal. In a
multi-command block that means execution STOPS at the first one, the rest of the block never runs,
and what comes back is a truncated screenful ending in `:`. That happened on 2026-08-29 to a
diagnostic block: 24 of 35 commits came back and three of the four sections never executed.

Write `git --no-pager log ...`, not `git log ...`. The flag goes before the subcommand.

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

### 9. EVERY instruction says WHO does it. Andrew must never have to guess.

Asked for explicitly on 2026-08-30, after a reply said "Run **Recover Live Lambda Handler** with
function: ..., handler: ..." and there was no way to tell whether that was a note-to-self, something
already done, or a thing he was meant to go and do. He should not have to work that out. A reply
that leaves him guessing has not delivered anything.

**Every** step in a chat reply carries one of these labels, in bold, on its own line, immediately
before the block or sentence it governs. No step is unlabelled.

- **`ANDREW RUNS THIS:`** — followed by a ```zsh block, and nothing but real commands in it
  (rules 1-8 all apply). This is the only label that may precede a ```zsh block.
- **`ANDREW CLICKS THIS:`** — a browser action. GitHub Actions dispatch, a Cloudflare dashboard, a
  Stripe setting. Say the page, the exact control, and the exact field values. Workflow dispatch is
  403 for Claude, so every workflow run is this label, never "run the workflow".
- **`CLAUDE ALREADY DID THIS:`** — finished work being reported. No action for him. Say it in the
  past tense.
- **`FOR INFORMATION, DO NOT RUN:`** — file contents, YAML, JSON, logs, a diff. Fence it with its
  real language, never ```zsh. This is rule 7 restated as a label.

An imperative sentence with no label — "run the backfill", "check the drift issue", "recover the
live handler" — is the bug this rule exists to stop. If a reply contains one, it is not finished.

### 10. `git merge` and `git commit` open vim. Always pass `--no-edit`.

Same failure as rule 8, one command over. On 2026-08-30 a pasted `git merge` dropped him into a vim
buffer on the merge message with no way out that he knew, and the rest of the block never ran.
`git merge --no-edit`, `git commit --no-edit` when concluding a merge. This is also the fix for the
`MERGE_HEAD exists` recovery at the top of this file.

### 11. No placeholders in a runnable block. Ever. Especially not for a secret.

On 2026-08-30 a ```zsh block contained:

    export BP_PRIVATE_KEY=<paste the key>

Andrew pasted it, because rule 7 says a ```zsh block is a thing you paste, and got:

    zsh: parse error near `\n'

`<` is an input redirection in zsh, so `<paste` redirects from a file named `paste`, `the` is an
argument, and `key>` opens a redirection with nothing after it. The line was never a command. This
is rule 7's "every line must be a real command that runs as pasted" and it was broken anyway,
because a placeholder LOOKS like an instruction to a writer and IS a syntax error to a shell.

So: **no `<...>`, no `YOUR_KEY_HERE`, no `/path/to/thing` inside a ```zsh block.** If a value has
to come from Andrew, the command must ASK for it at runtime.

For a secret, this is the pattern, and it is zsh-specific — `read -rsp` is bash and is wrong here:

    read -rs "BP_PRIVATE_KEY?Paste the Base wallet private key, then press Enter: "
    export BP_PRIVATE_KEY

`-s` suppresses the echo, so the value never appears on screen, never lands in a screen recording,
and never enters shell history. Verified in zsh 2026-08-30, along with the failure above.

For a non-secret, ask the same way without `-s`, or have him edit a committed file rather than a
pasted line.

**A secret must never be assigned inline in a block that will be pasted, recorded, or committed.**
The Rain demo was going to be screen-recorded and sent to a third party, so an echoed key would
have been in a file leaving the building.

---

## A SESSION THAT CANNOT PUSH HAS NOT DELIVERED ANYTHING

Added 2026-08-30, after intel sweep 003 was written, committed locally as `a08104f`, and then could
not be pushed: that session's environment did not carry `nzdsf2-gif/relayshield` as an authorised
repo source. The commit exists only inside a container that will be reclaimed. **The work is gone
unless it is recovered as text.**

Two rules, and they apply to every session.

**1. Prove the push path BEFORE doing the work, not after.** The first git operation of any session
that will produce commits is a reachability check, not a commit:

    git ls-remote --heads origin >/dev/null && echo "push path OK"

If that fails, say so immediately and STOP. Do not write half a day of work into a container that
cannot hand it back.

**2. If a push is impossible, the deliverable is a patch in the chat, not a commit.** Any session
that finds itself unable to push must emit the full diff as a fenced block for Andrew to save, the
same way the CHAT PASTE rule at the top of this file works for `.md` files. A commit nobody can
fetch is not a deliverable.

To recover stranded work from a session that is still open, ask it for:

    git format-patch --stdout origin/main..HEAD

and paste the output into a session that can push. `git am` applies it.

---

## "NO AWS IN THIS SANDBOX" IS NEVER A REASON TO SKIP A CHECK

Also 2026-08-30. Sweep 002's keywords went unverified against `relayshield_intel_channels` because
the session had no AWS, and it was recorded as a limitation and left there. That is the wrong
conclusion every time.

The container not having credentials is a fact about the container, not about the check. The check
still has to happen, so it moves rather than disappearing:

- **Write it as a committed script** that runs on the Mac with `AWS_PROFILE=relayshield`, exactly as
  `tools/setup_first_seen.sh`, `tools/iam_snapshot_role.py` and `tools/backfill_first_seen.py` all
  do. Then hand Andrew the one command, labelled `ANDREW RUNS THIS`.
- **Or run it in Actions**, which has the OIDC role, exactly as `lambda_drift_check.yml` and
  `recover_live_handler.yml` do.

A session may never close an item as done, or report a number, on the basis of a check it skipped
for want of credentials. Say which check did not run, and ship the script that runs it.

---

## IAM — one role per Lambda, not one role for all of them

`relayshield-breach-check-role-1sapnwdl` is the console-generated role from the
first Lambda ever created, and it became the answer to every "which role?"
question since. It carries **26 inline policies** — one per table, by convention —
which fill the 10,240-byte inline budget. That is a hard IAM limit. On 2026-08-29
a single `PutItem` grant could not be added and had to fall back to a customer-
managed policy; a role may have only 10 of those attached, so the fallback is the
next cap, not a fix.

**Do not add another policy to that role.** The tooling to move a function onto
its own role is in the repo, the derived policies are all under 1,900 bytes
against a 10,240-byte budget, and the runbook is `iam_role_split.md`:

- `tools/iam_snapshot_role.py` — read-only, run this FIRST and commit the output.
  The 26 inline policies exist only in AWS. The DRIFT RULE applies to IAM harder
  than it applies to code: a missing permission does not fail at deploy time, it
  fails on whichever code path needs it, whenever that path next runs.
- `tools/iam_scan_sources.py` — no AWS. Which resources each Lambda touches.
- `tools/iam_split_roles.py` — derives a per-function role from the shared role's
  own statements. Dry-run by default; `--apply` requires `--only <function>`.

Actions are never inferred from source — they are taken from the shared role,
which is what is running today. Only resources come from the source, and only for
services whose resources appear there as names. Step one is a pure move with
identical permissions; narrowing is `--narrow-wildcards`, separately, afterwards.

Nothing deletes from the shared role until the snapshot's
`functions_using_this_role` list is empty. That list is authoritative and
`deploy_lambdas.yml`'s `LAMBDA_MAP` is not — 46 `relayshield_*.py` sources are
not in it.

---

## A BROKEN WORKFLOW FAILS SILENTLY. VALIDATE AFTER EVERY EDIT.

Added 2026-09-02, the same day it cost a day of drift detection.

A comment was inserted into `lambda_drift_check.yml` at the wrong indentation. The lines dedented
out of the `run: |` block and broke the YAML. GitHub's response to a workflow it cannot parse is:

    .github/workflows/lambda_drift_check.yml: No jobs were run

**That is quieter than a failure.** A red run gets read. A run that did not happen reads like
nothing happened, so the check that exists to catch silent drift became silently dead itself and
stayed that way across scheduled runs.

**After ANY edit to a file under `.github/workflows/`, run:**

    python3 test_workflows_parse.py

It checks every workflow parses AND defines jobs — a file that parses but has no `jobs:` also runs
nothing and looks identical from the outside. It is deliberately a standalone script and NOT a
workflow: a workflow that validates workflows fails the same way it is meant to detect.

The general form, which is the part worth remembering: **the alarm you must check hardest is the one
that goes quiet, not the one that goes red.**

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

## WHERE 2026-09-03 LEFT THINGS — read this first

### The founder could not see the Discord email-check footer. The diagnosis in the room was wrong.

It was reported as "not merged to main yet". **It is on main** — commit `4a688e8`, merged, and
`EMAIL_CHECK_FOOTER` is concatenated onto the `/scan` reply in `relayshield_discord_bot.py`. Merging
changed nothing, because **`relayshield_discord_bot.py` is in the deploy map of nothing.** No edit
to that file has ever shipped automatically. Main being right and live being wrong is the normal
state for this function, not an anomaly, and it stays that way until the function gets a deploy
path.

Worth keeping as a general correction: "it is not merged" and "it is not deployed" produce the
identical symptom, and only one of them is fixed by merging. Check which before promising a merge
will fix it.

### The drift check has still never run with the Discord bot in it

Two separate reasons, both now closed:

- The entry was added in `6a2bae7` at 00:56 on 2026-09-03. The last run that actually executed is
  **run 14, the scheduled run of 2026-09-02 16:56**, which predates it. The next scheduled run is
  13:00 UTC.
- Runs **15 to 24 are not drift runs at all.** They are `push`-event runs with **zero jobs** — the
  invalid-workflow failures from the YAML break that `9c87348` fixed. The workflow only triggers on
  `schedule` and `workflow_dispatch`, so a valid file produces NO run on a push. That is the useful
  tell: since `9c87348`, three pushes have produced no run at all, which is the positive evidence
  the file parses again.

### The Discord diff was read, and it was case 2: live was merely stale

`sh tools/discord_bot_drift.sh` ran on the Mac at 07:20. Findings, in the order
they matter:

- The function name **`relayshield-discord-bot` is CORRECT** — resolved against AWS in
  239677749008, python3.14, `CodeSize` 10021, **`LastModified` 2026-08-13T15:25**. Three weeks
  untouched, which is what "no deploy path" looks like from the AWS side.
- The live handler is **byte-identical to `relayshield_discord_bot.py` as of `0c429e0`**, missing
  exactly one commit: `4a688e8`, the email-check footer. Nothing live-only. **Nothing to recover.**
- No other `relayshield_*.py` in the package at all, so no shared-module drift either.

So the footer was never a merge problem and never a recovery problem. It was a function with no
deploy path, and it now has one: `relayshield_discord_bot.py` is in `deploy_lambdas.yml` — the
`paths:` trigger, `LAMBDA_MAP`, and the manual-dispatch list. No import-probe early return is
needed; the probe payload falls through the deferred branch, finds no Discord signature headers and
returns 401, which is a real response and all the probe asserts.

**The trap in mapping it, which nearly wasted the whole fix:** the deployer ships a function only
when the PUSH changed its source. A push that maps a function while touching only workflow files
deploys nothing. That is why the commit that maps it also writes the deploy path into the handler's
own docstring — the push has to touch the `.py`.

### The drift script's first verdict was WRONG, and the lesson generalises

It printed RECOVER FIRST on a function that needed nothing of the sort. It classified by **counting
diff lines** — any `+` line meant live carried something main did not — and **a modified line
produces a `+` and a `-` both**. The single `+` was `"content": rendered["text"] + UPSELL_FOOTER,`:
main's own line as it stood one commit earlier.

The fix is not a better heuristic, it is an exact question, and git can answer it directly: **is the
live file byte-identical to some commit's version of this file?** Yes means every byte is already
committed and there is nothing to recover, whatever shape the diff has. No means live holds content
no commit ever held, which is hand-deployed work. The script now walks `git log -- <file>` and says
which commit live matches and which commits it is missing.

Worth carrying to the next drift diff of any kind: **a diff's shape does not tell you which
direction drift runs. Matching a committed version does.**

### Run 134 was RED and the deploy SUCCEEDED. Read which step failed.

The merge shipped it. The log says so:

    → Packaging relayshield_discord_bot.py → relayshield-discord-bot
    ✅ relayshield-discord-bot deployed

What went red is the step AFTER it, the import probe:

    AccessDeniedException ... relayshield-github-deploy is not authorized to
    perform: lambda:InvokeFunction on ... function:relayshield-discord-bot

**`deploy_lambdas.yml` invokes what it deploys, and that grant is an EXPLICIT ARN LIST** in
`iam_github_deploy_invoke.json` — 22 functions, applied by hand on 2026-08-30, with nothing checking
it against `LAMBDA_MAP`. So mapping a 23rd function guaranteed a red run on its first deploy, and
the failure looks exactly like a broken deploy while being the opposite: the code is live and only
the verification was refused.

Two files that must agree with nothing checking that they do — the same shape as the four pattern
tables. Now closed three ways:

- **`tools/check_deploy_invoke_policy.py`** parses `LAMBDA_MAP` out of the deployer and fails if any
  function is missing from the policy file. `--write` adds them.
- **`test_workflows_parse.py` runs it**, because that is already the command this repo runs after
  every workflow edit. A workflow that parses can still be guaranteed to fail.
- **`tools/apply_deploy_invoke_policy.sh`** pushes the file to AWS, which the repo half does not do
  on its own. It LOOKS for where the policy lives (inline, then attached managed, matching on the
  Sid) rather than assuming, because 2026-08-30 recorded no location, and it proves the result with
  `simulate-principal-policy` against the ROLE — invoking from the operator's own shell would test
  the wrong identity entirely.
- The probe's error now says outright that the function was deployed and names the two commands.

**The general form: a red run names a step, not an outcome.** "The deploy failed" and "the check
after the deploy failed" are different facts with different fixes, and the second one costs nothing
if it is read correctly and a rollback if it is not.

### The widget shipped, and the cheap half was already built

`telegram_widget_scope.md` has the whole thing. The three findings worth carrying:

- **The prospect list is bot REPOSITORIES, not websites**, so a `<script>` embed is the wrong
  artefact for almost every prospect on it. v1 is a file you copy into your bot.
- **`/v1/wallet-risk` has been KEYLESS since Crypto Shield Mobile**, capped per source IP, so the
  address half of the widget needed no new product decision at all.
- **`/v1/scan-url` was the wrong shape and the new `/v1/link-check` is the right one.** VirusTotal
  submits and then needs polling, which a Telegram handler cannot do, and costs money per call,
  which is why it needs a key. The new endpoint returns the three signals that are immediate and
  free: IOC corpus, Safe Browsing, RDAP age. Keyless for the same reason the wallet ones are.

Two rules are pinned by 39 offline tests rather than by intent: **it never throws** (every failure
is `ok=false, level="unknown"`) and **it never says "safe"** (a heuristic pass is an absence of
evidence, and the ceiling is "nothing known against it"). Both exist because this code runs inside
someone else's product, in front of users who never chose us.

**`relayshield_developer_signup.py` is the SIXTH handler with source in the repo, live traffic and
no deploy path** — found while registering the `tg-widget` key in its `_SOURCE_BANNERS` table. It
serves api.relayshield.net/developers: pricing, the signup form, free-tier key issue, every landing
banner. So a registered attribution key reached nobody until that function deployed. **Its first
diff was read, recovered and reconciled the same day — see the section above. It is now in
`deploy_lambdas.yml`, and `iam_github_deploy_invoke.json` gained it too, so its first CI deploy does
not repeat run 134's denied probe.**

### relayshield_developer_signup.py IS THE 2026-08-17 CASE AGAIN, and this time the code takes money

The sixth handler's first drift diff was read the same day it was added, and it is not the stale
case. **Live holds roughly 700 lines that NO COMMIT OF THAT FILE HAS EVER HELD.** `handler_drift.sh`
settled it exactly rather than by counting: no version in `git log -- relayshield_developer_signup.py`
is byte-identical to the live file.

What is live and not in git, in the order it would hurt to lose:

- **The Bundle A and Bundle D direct-Stripe doors**, ~400 lines: `handle_bundle_checkout`, the
  `/developer/bundle-checkout` route, provisioning and revocation for both bundles, and both key
  emails. This is a second revenue path for products otherwise sold only on AWS Marketplace.
- **`_get_subscription_price_ids`.** A bundle subscription carries TWO Stripe items and Stripe does
  not guarantee order, so the old `items[0]` read was a coin flip: when the metered price came back
  first the bundle branch never fired and the customer was charged $150 or $299 a month and handed
  an ordinary pay-as-you-go key. Live has the fix. Main has the coin flip.
- **The `_find_key_by_customer` projection fix.** The AWS-disintermediation guards read
  `aws_license_arn` and `bundle_?_access`; a projection that omits them does not raise, it returns
  None, so both guards silently evaluate false. Live projects them. Main does not.
- **`_strip_html_comments`**, which stops engineering notes shipping to public View Source. One of
  them recorded a third party's rejection of our work.
- **The mobile media query**, the fix for the signup CTA overflowing its box on a phone. That button
  is the primary conversion action on the page.
- **`FREE_TIER_CALLS = 100`.** Main still says 20, while main's own `relayshield_api.py` says
  `FREE_TIER_CALLS_LABEL = 100`. The two halves of the free tier disagree in main and agree in live.
- **Eight source banners** main has never seen: `discord-bot`, `npm-worm`, `fourth-party`,
  `ansible-galaxy`, `bluenoroff`, `rsscan`, `rsscan-deps`, `metamask-snap`, with their alias tables.
  Note that `rsscan` has its OWN banner live, where main still aliases it to `github`.
- Corrected corpus figures throughout: 494K distinct indicators, 5.8M sightings, 95 channels, where
  main still says 5.0M IOCs and 85 channels.

**IT WAS SAFE ONLY BECAUSE THE FUNCTION WAS IN NO DEPLOY MAP.** Until the reconcile below landed,
adding it to `deploy_lambdas.yml` would have deleted all of the above on the next merge with no
error anywhere. That order — recover, reconcile, only then map — is the whole rule.

**RECOVERED AND RECONCILED THE SAME DAY.** `recover_live_handler.yml` pushed the live package to
`claude/recovered-live-relayshield-developer-signup` (`dfe60a2`), and it is now on main as two
commits, deliberately not one:

1. `93310e3` — the live bytes, verbatim, at the handler's own path. A pure move, no edits.
2. `4690b85` — the three registrations main had and live did not: `apify` (2026-08-27),
   `mcp-registry` (2026-09-02), `tg-widget` (2026-09-03), re-applied verbatim.

**Splitting it in two is what makes the result checkable.** Live is byte-identical to `93310e3` and
missing exactly `4690b85`, which is the ordinary stale case, so the function could finally be mapped
in `deploy_lambdas.yml`. One squashed commit would have left live matching nothing and the drift
check crying wolf forever.

**One thing from main was deliberately dropped: the alias `"rsscan" -> "github"`.** Live gives
`rsscan` its own banner and removes that alias, and `_resolve_source` applies aliases BEFORE the
banner table, so with the alias in place rsscan's own banner is unreachable. A key that exists,
resolves, and renders the wrong thing is worse than a missing key, because nothing looks broken.

The reconcile was verified structurally rather than by eye: comparing the two files' top-level
symbols and both attribution tables showed 15 live-only symbols, 8 live-only banners and 42
live-only aliases, all preserved, and exactly 3 banners plus 5 aliases re-added.
`test_developer_signup_banners.py` now pins those invariants with `ast` and no boto3.

**The general form, for the third time: a handler with source in the repo, live traffic and no
deploy path accumulates hand-deployed work silently, and the longer it goes unread the more
expensive the diff.** This one went unread from 2026-08-17 to 2026-09-03 and grew a billing path.

### The tg-widget banner is not missing. It is a per-arrival banner.

Asked on 2026-09-03 after all three runs went green: "I do not see the tg-widget banner on
api.relayshield.net/developers." It is not supposed to be there.

`_SOURCE_BANNERS` entries render into the `<!--REFERRER_BANNER-->` placeholder, which sits directly
under the nav and above the hero, and ONLY when the arrival carries `?source=`/`?src=` or a matching
Referer host. `tg-widget` deliberately claims no referer hosts, so the parameter is the only way in.
The bare `/developers` URL will never show it, by design.

    https://api.relayshield.net/developers?source=tg-widget

That is also the check: `curl -sS "…?source=tg-widget" | grep -c "Arriving from a Telegram bot"`
returns 1 when it is live, and the same command on the bare URL returns 0.

### MINI APP DISCOVERY — the ranking, decided 2026-09-03

Recorded here because the founder asked for it to be, and because the first version of this ranking
was wrong in a way that is easy to repeat.

**Re-ranked: blog channel first, then Mini App announcement channels, then directories, then
attributed deep links, with the menu button fifth because it is cheap rather than because it reaches
anyone.**

The error worth not repeating: the menu button on `@relayshield_bot` is the top lever for a bot with
an audience, and ours has a tiny number of users, so a Mini App hung off it inherits a tiny number of
users. **Rank a surface by how it performs for US, not by how it performs in general.** Reasoning and
the full list are in `miniapp_discovery_and_stripe_choice.md` §2.

**Four channels measured on the prospecting account** by `tools/find_miniapp_channels.py`:
`@swoptoky_news` (205,055, Cyrillic), `@web3telegrambotx` (72,742), `@findminiapp` (56,380),
`@telegtapps` (9,673). Three are usable; the Cyrillic one needs a Russian-language submission or a
skip, which is what `--latin-only` and the new `script` column are for.

**SEQUENCING, and it decides when any of this happens: WE DO NOT HAVE A MINI APP YET.** These
channels announce Mini Apps, and each will give us exactly one first impression. Submitting before
the thing exists spends it. The list is the target for the day v1 ships.

### Two things this session got wrong, and the founder caught both

**I claimed the MetaMask Snap was a live surface. It is not.** The integration request was submitted
and there has been no response. The repo already recorded that in three places
(`victim_side_outreach_messages.md`, `xcitium_outreach.md`, `NEXT_SESSION_2026-08-19.md`), and I
wrote "we already have the plugin-shaped surface that matters" without checking any of them. That is
CLAUDE.md's own rule broken by CLAUDE.md's own author: **a doc claiming something is done is a lead,
not a fact.** A `metamask-snap` key exists in `_SOURCE_BANNERS`, registered before shipping exactly
as the rule requires, and a registered key is not a live integration.

**I ranked the bot's menu button as the top Mini App discovery lever.** The bot has a tiny number of
users, so a Mini App hung off it inherits a tiny number of users. The ranking was right in general
and wrong for us, which is how a plan ends up describing somebody else's company. Re-ranked in
`miniapp_discovery_and_stripe_choice.md`: the Telegram blog channel first, then Mini App announcement
channels, then directories, then attributed deep links, and the menu button fifth because it costs
almost nothing rather than because it reaches anyone.

### The first real prospect sweep was mostly unusable, and it was the extractor

216 rows, and the top 25 included `root@203.0.113.4` (an RFC 5737 documentation IP),
`trial@telegram.bot`, `k7m2q9x1a3@yourdomain.com`, a YouTube demo link and several `t.me` links, all
counted as reachable contacts. `contacts_from` filtered exactly one thing, `example.com`.

That is not cosmetic. **Contactability is 20 of the 100 score points**, so the ranking was partly
measuring bad extraction, and mailing a documentation example is how a sending domain earns a spam
reputation. `tools/contact_hygiene.py` now screens both fields, in the extractor AND again in the
generator, because a `prospects_wide.jsonl` produced before the fix still holds those rows and the
generator is the last thing standing before a message goes out. Seven tests, every case taken from
that sweep.

**Also re-run it with `--stars 5..50`.** Without the flag the sweep spends its whole `--limit` inside
`stars:0..1`, which is why the results were dominated by brand-new repos: the script's own docstring
says so and the run log shows the single `stars:0..1` line.

### Changed 2026-09-03

- **`tools/discord_bot_drift.sh`** — read-only, runs on the Mac, needs no waiting for 13:00 UTC. It
  asserts account 239677749008, **resolves the Discord function's real name from AWS instead of
  trusting the map**, downloads the live package, diffs the handler AND every shared
  `relayshield_*.py` in it, and classifies the result the only way that matters: lines present in
  LIVE and not in main mean hand-deployed work that is RECOVERED first; only main's own commits
  missing means live is merely stale and the function can be mapped in `deploy_lambdas.yml`.
- **`relayshield_discord_bot.py` now has a deploy path** — `deploy_lambdas.yml`, after the diff
  above was read. It stays in the drift check too: having a deploy path is not the same as never
  being hand-deployed again.
- **`tools/handler_drift.sh`** — the Discord drift script, generalised, because a sixth handler
  needed the same three questions the same day. `tools/discord_bot_drift.sh` is now a wrapper, so
  every reference to it in this file and in the workflow comments still works.
- **`xsoar_pack_watch.yml`** — the XSOAR gate is watched daily instead of remembered.
- **`tools/generate_outreach.py`** + `test_generate_outreach.py` — item 2's generator, and the ten
  tests that stop a draft ever diagnosing a prospect.
- **`miniapp_discovery_and_stripe_choice.md`** — why the widget must not carry a Mini App link, what
  actually drives Mini App discovery, why a browser extension is not the play, which Stripe agentic
  product to select, and the four questions to put to Jake while access is in review.
- **`tools/contact_hygiene.py`** + `test_contact_hygiene.py` — the screen that stops a README
  example becoming an outreach recipient. Wired into both the prospector and the generator.
- **`tools/find_miniapp_channels.py`** — searches for channels that announce new Mini Apps and
  reports measured member counts, ON THE PROSPECTING SESSION. It refuses to run against
  `relayshield/telethon_session` at all: 99 channels of collection depend on that account, and a
  prospecting sweep is how it gets flood-limited.
- **`iam_github_deploy_invoke.json` gained `relayshield-discord-bot`**, plus the checker, the
  applier and the validator wiring described above.
- **An unreadable function now fails the drift run.** It previously emitted a `::warning::` inside
  an otherwise green run, so a wrong name in the map was indistinguishable from a clean check —
  the quiet-alarm failure again, and the Discord entry's name is exactly the case that would have
  hit it. `UNREADABLE` is tracked separately from `DRIFTED`, so it reddens the run without opening
  a `lambda-drift` issue about drift that was never measured.

## WHERE 2026-09-02 LEFT THINGS — read this first

### THE LIST FOR THE NEXT SESSION, in order (11 items)

1. **Scope and build the widget. BUILT 2026-09-03 — see `telegram_widget_scope.md`.** v1 is a
   copy-in file rather than a `<script>` embed, because the prospect list is bot REPOSITORIES and a
   bot is not a web page. `POST /v1/link-check` is new and KEYLESS: IOC corpus, Safe Browsing and
   domain age, no VirusTotal, so no marginal cost and no signup before the first call. The wallet
   half needed nothing new, because `/v1/wallet-risk` has been keyless since Crypto Shield Mobile.
   Clients in Python and JavaScript, 39 offline tests, `tg-widget` registered in `_SOURCE_BANNERS`
   first. **Not live until two more steps: the merge deploys the API, then
   `sh tools/create_link_check_endpoint.sh` adds the gateway route.** The original entry follows.
   An embeddable
   "check this link / check this address" widget for third-party Telegram bots and Mini Apps. The
   prospect list exists: `prospects_wide.jsonl`, 206 rows at `stars:5..50`, **109 with a website or
   an email**, and 19 of the top 25 tagged `wallets` or `payments` — bots already handling other
   people's money. **Register the `source=` keys in `_SOURCE_BANNERS` BEFORE any widget ships**;
   FD-8 below is what happens when that is skipped.
2. **Tailored outreach to the 109. THE GENERATOR IS BUILT, 2026-09-03: `tools/generate_outreach.py`.**
   It reads `prospects_wide.jsonl` and writes `outreach_bot_prospects.md`: one draft per prospect
   keyed on the capability their own README asserts, the contact channel, the evidence line the
   draft rests on, and a tracking table. **It cannot run in a container** — the prospect file is
   generated output and lives on the Mac. Ten tests pin the rule that matters: the drafts never
   assert anything about a prospect's security, because we can read a README and cannot see anyone's
   backend, and "we analysed your app and found exposures" from an unknown security vendor is one
   word away from an extortion email. Original entry follows. Founder wants it; agreed approach is a
   GENERATED DRAFT PER PROSPECT that he reviews and sends, keyed on what each repo actually does.
   Not mass mail: volume is not the lever, relevance is, and blasting maintainers who never asked is
   how a domain gets blocked.
3. **Apify: "your Actor as a tool for AI agents" post.** Their content programme pays **$500 per
   article** on the Apify/Crawlee blog and $100 credits for dev.to under their org. The July call
   closed 2026-08-16; it is QUARTERLY, so the next call is the target. Theme 2 fits
   `mcp-registry-risk` exactly. Also **put dev.to back in the channel order** — it is missing
   entirely and costs nothing.
4. **Stripe MPP follow-up with Jake Lamoine.** Open question carried: does x402 settlement count
   toward early-adopter status. Card via SPT minimum is $0.50, stablecoin $0.01 USDC, and the sample
   uses `scheme: "exact"` on Base — identical to our 28 live x402 endpoints.
   **DECIDED 2026-09-03, of the four cards in the Agentic Commerce console: select ACCEPT MACHINE
   PAYMENTS.** It is the productised version of the rail we already run. Retail is a product
   catalogue and we have no SKUs; the agent wallet is spend control on the BUY side and we are the
   sell side; Projects is infrastructure we have. Reasoning, including why the agent wallet is the
   pitch TO Stripe rather than a fit for us, is in `miniapp_discovery_and_stripe_choice.md`.
5. **Aduna — Reggie Daniels.** Founder's former colleague works there and will text him. Outreach
   messaging is written in `aduna_outreach.md`.
6. **FD-8 finish — official MCP registry attribution. ONE EDIT, ONE PUBLISH.**
   `registry.modelcontextprotocol.io` has carried RelayShield since 2026-05-10 (six versions, latest
   0.2.7, status active) with a bare `https://relayshield.net` as its `websiteUrl` — so four months
   of arrivals from the canonical MCP directory logged `unmatched:` and rendered no banner. The
   `mcp-registry` key is now registered in `_SOURCE_BANNERS`, so the only remaining steps are:
   change `websiteUrl` in `~/mcp-live/server.json` to `https://relayshield.net?source=mcp-registry`,
   then re-publish with `mcp-publisher` (the registry is versioned, so this is a new version, not an
   edit — read that repo's README for the established command rather than inventing one). While
   there: the record's `repository.url` says `github.com/relayshield/...` while the namespace is
   `io.github.nzdsf2-gif/`. Probably harmless, worth a look.
7. **FD-9 — verify Glama by hand.** `glama.json` is present in the MCP server repo, but `glama.ai`
   is rejected by the container's egress policy, so the listing status is genuinely UNKNOWN, not
   absent. Open <https://glama.ai/mcp/servers>, search RelayShield. If listed, get
   `?source=mcp-registry` onto the link it points at — the key is registered and `glama.ai` is
   already a referer host. If not listed, Glama indexes from GitHub, so the route is making sure
   `glama.json` is on the default branch, not a submission form.
8. **relayshield-agentic-api drift.** Recovered onto `claude/recovered-live-relayshield-agentic-api`
   by `recover_live_handler.yml`. **NOT yet reconciled into main.** Live carries a branded
   `API_BASE_URL` and a Bundle D Stripe billing branch that main does not; deploying main over it
   would make the direct Stripe door free.
9. **INTEL-5 funnel.** Instrumented but the answer is not in yet. Re-run
   `tools/diagnose_stolen_sessions.py` after the monitor has run on the instrumented build; its
   section 0 now says outright whether that build is live.
10. **XSOAR blog + landing line**, triggered by `check_xsoar_pack.sh` reporting ON MASTER, never by
    a date. **Checked 2026-09-03: still NOT on master.** `#45206` has lost its `/merge` ref,
    `#45742` still has one so it is open in Palo Alto's pipeline, and
    `Packs/RelayShield/pack_metadata.json` is 404 on master while the control pack is 200, so the
    absence is real rather than a blocked request. Nothing to publish yet. **The gate is now
    watched rather than remembered:** `xsoar_pack_watch.yml` runs the check daily and opens an
    issue the day it flips, and the script's last line is a machine-readable
    `XSOAR_PACK_STATUS=merged|absent|undetermined`.
11. **`relayshield_discord_bot.py` — read its first drift diff, then decide.** FIFTH instance of
    source-in-repo, live, and in NEITHER map. It was added to `lambda_drift_check.yml` ONLY on
    2026-09-02, deliberately: a red diff is the alarm and gets read before anything is mapped in the
    deployer, because live may carry hand-deployed code a repo-sourced deploy would delete with no
    error anywhere. **The function name in the map is UNVERIFIED** — if the check reports "not
    readable", fix the name, do not drop the entry. Only when the diff shows live is merely stale
    does it go into `deploy_lambdas.yml`. Until then no edit to that file ships automatically, which
    is why the email-check footer added this session is not visible in Discord.
    **2026-09-03: COMPLETE. The footer is live in Discord.** The diff was read with
    `sh tools/handler_drift.sh relayshield_discord_bot.py`: live was byte-identical to `0c429e0`,
    stale by exactly one commit and holding nothing of its own, so the function went into
    `deploy_lambdas.yml` and run 134 shipped it (`✅ relayshield-discord-bot deployed`). That run is
    RED, and the red is the import probe being denied `lambda:InvokeFunction`, not the deploy. See
    the 2026-09-03 section above for all three findings and what closed each.

### Done and verified 2026-09-02

- **`checkemail@relayshield.net` is LIVE and returns correct HIGH verdicts.** It took nine distinct
  defects to get there, and every one was found by the founder testing rather than by me:
  a malformed `References` header, a fallback that fired a second reply Cloudflare forbids, HTML
  entities left undecoded, `stripHtml` collapsing a message to one line, `parseAddress` trusting the
  first angle brackets, the API's `{ok, data}` envelope read at the wrong level, a scoring model that
  counted flags instead of weighing them, brand impersonation gated on free webmail, and RFC 2047
  subjects printed raw. 78 verdict tests and 11 reply tests now pin all of it.
- **The email check is on every surface**: WhatsApp hint, Telegram hint, both Quickstart cards,
  Discord `/scan` footer, and the blog footer on every page.
- **Telegram Markdown escaping never worked.** Legacy Markdown has NO escape syntax, so `\_`
  rendered a visible backslash. Quickstart is HTML now; the forward note uses code spans.
- **The drift check was silently dead** for a day, from a YAML indentation error of mine.
  `test_workflows_parse.py` guards the class.
- FD-1 done (rsscan v0.2.1 on the Marketplace). FD-2 killed on their published rules. mcp.so now
  charges $39 — skipped.

### Things this session got WRONG, recorded so they are not repeated

- **Handed over commands that did not exist** (`--stars`) and instructions written without reading
  the target (FD-2's PR would have been closed without comment; the mcp.so form is paid). **Read the
  destination before writing the instruction.**
- **Diagnosed by guessing** three times before adding logging. The logging found it in one round
  each time. Instrument first.
- **Wrote `emailcheck@` for `checkemail@` twice**, in the message asking to put it on four surfaces.
  One constant now, and a test.

### Two open items with no owner yet

- **`relayshield_discord_bot.py` is in the deploy map of nothing.** Fifth instance of that
  combination. Added to the drift check only; read its first red diff before mapping it.
- **`relayshield_stolen_sessions` still holds 9 rows, all `demo`.** The CORPUS-1 storage fix is
  correct and has never been reached.

---

## WHERE 2026-08-30 LEFT THINGS — read this first

### The list that session left, as of 2026-08-30 (HISTORY, not a queue)

1. **Telegram + WhatsApp forward handler and compromised-contact check.** Designed, decided, NOT
   built. Integration points already located: `handle_message` (`relayshield_telegram_webhook.py`
   ~6072) for the `forward_origin` branch, `handle_scan_dispatch` for the URL path,
   `handle_infostealer_check` and the `relayshield_stolen_sessions` lookup for the contact check.
   Decisions made: a clean result says so plainly with the "not proof of safety" caveat; the contact
   stolen-session lookup runs ONLY when text, URL or first-time-sender has already flagged
   something, so no social graph accumulates. Forwarding needs no command; `/wascam` becomes the
   discovery path that explains it.
2. **Quickstart guide hints**, same build: tell users they can paste screenshots (already works, OCR
   via Rekognition since 2026-08-11) and forward suspicious messages to `@relayshield_bot`.
3. **IAM split, step 2.** The snapshot is committed and it is worse than assumed: 26 inline policies
   at 10,127/10,240 bytes AND 10/10 managed slots, both budgets full, with **42 Lambdas** on the
   role rather than the 22 in `LAMBDA_MAP`. `tools/iam_scan_sources.py` must read the snapshot's
   `functions_using_this_role` before any migration, or 20 functions get no derived policy.
4. **Re-run the prospector** with the new gates: `python3 tools/prospect_github_bots.py --limit 200`.
   The first run was mostly noise; the gates are tested against that exact output but not yet against
   live data.
5. **`relayshield_agentic_api.py` deploy path.** In the drift check since 2026-08-30, deliberately
   NOT in the deploy map. Read its first red diff, then map it.
6. **Sweep 003's 17th keyword** is unrecoverable. Either accept 16 or re-derive from TI reporting.
7. **XSOAR PR #45206 is MERGED (2026-09-02)** and no demo was required after all. The work is now
   in Palo Alto's internal PR #45742, which is open and approved. Nothing for us to do; the pack is
   not on master yet, so the marketing claim is still gated. See STATUS CORRECTIONS.
8. **Rain** waits on a reply. Two open questions carried: whether the Agent Control Layer has a
   pre-issuance hook, and the Sardine/Chainalysis paragraph never got its outside read.
9. **Medium quote bars**: house style is now none. `build_blog.py` renders `> ` as a plain `<p>`.
10. **OpenRouter revocation webhook** still gated on the first non-zero `sk-or-v1-` count.

### Done 2026-08-30

- **Rain closed after four sessions.** `tools/rain_demo.py`, recorded, both submissions sent.
- **LLMjacking coverage materially widened.** Venice (`VENICE_INFERENCE_KEY_` + base62, taken from a
  real key), Anthropic OAuth and session tokens split from API keys because they need REVOCATION not
  rotation and the old `{90,}` pattern likely missed them entirely, and `/checkllm` brought from 6
  providers to 14 — it had been silently behind the corpus, with OpenRouter missing.
- **Four pattern tables must agree**: `relayshield_api.py` (source of truth), `rsscan/rsscan/patterns.py`
  (generated, `tools/sync_patterns.py`), `relayshield_intel_monitor.py` (collection), and
  `_LLM_KEY_PATTERNS` in `relayshield_telegram_webhook.py` (customer-facing). The last one is the one
  that drifts unnoticed, because nothing checks it.
- IAM per-role tooling and runbook; `relayshield-mcp` gitlink removed; deploy-role invoke policy
  applied and the Lambda deploy green; the LLMjacking blog published; CLAUDE.md rules 9, 10, 11.

---

## WHERE 2026-08-29 LEFT THINGS — read before starting anything

`main` is at the merge of everything below. **One branch is unmerged:
`feat/partner-center-and-aws-setup`.** It carries the Partner Center, the Stripe attribution fix,
`tools/setup_first_seen.sh`, `tools/check_xsoar_pack.sh` and the Telethon simplification. Merging it
deploys `relayshield-stripe-webhook`, which is in the deploy map.

### Done and verified this session

- **The 35/46 local-vs-GitHub divergence is closed.** Andrew's clone held 36 unpushed commits
  (Microsoft Security Copilot MS-3/MS-4, the Sentinel Content Hub solution, TAXII dedup, CORPUS-1/2,
  the XSOAR email). Merged with only three contested files, resolved hunk by hunk, and
  `tools/reconcile_guard.py` run against **both** parents: `relayshield_api.py` 349/349,
  `relayshield_intel_monitor.py` 156/156, `build_blog.py` with `RSS`/`from_rss` as named drops.
  Backup branches `backup-main-20260829` and `origin/local-main-20260829` still exist.
- **intel-feed and intel-kev now have a deploy path**, plus `ci.import-probe` early-returns so the
  deployer's probe cannot trigger a full ingest.
- **`deploy_lambdas.yml` change detection was broken for merges** and would have shipped nothing on
  the very merge meant to ship those two. Now diffs from `github.event.before`.
- **The prospecting Telegram account is live.** Session in
  `relayshield/telethon_session_prospecting`. **Nothing reads it yet, and that is deliberate** — per
  `telegram_miniapp_and_app_inventory_scope.md`, Item 16's GitHub half is built first. The
  collection session was never touched.
- **XSOAR PR #45206 is NOT merged.** Verified by content, not just refs. See STATUS CORRECTIONS.
- **Partner commission decided: 20% / 12 months.** See PARTNER COMMISSION below.

### BLOCKED — A6 first-seen, the only thing left hanging

`relayshield_intel_first_seen` **exists in the right account** (239677749008). What fails is granting
the Lambda write access.

`relayshield-intel-monitor` runs as **`relayshield-breach-check-role-1sapnwdl`** — one shared role
carrying 22+ inline policies spanning Rekognition, Bedrock, marketplace metering and a dozen
DynamoDB tables. IAM caps the **aggregate size of a role's inline policies at 10,240 characters**,
and that budget is spent, so `put-role-policy` fails.

**Ask the cheap question first, which the first version of the script did not:** the role already
has a `relayshield-intel-dynamodb` policy. If its Resource is a `relayshield_intel_*` wildcard, the
permission already exists and there is nothing to grant. `tools/setup_first_seen.sh` now checks that
before trying anything, and falls back to a **customer-managed policy** (separate budget: 10 per
role, 6,144 chars each) if a real grant is needed.

**The backfill is NOT blocked by this and never was.** `tools/backfill_first_seen.py` runs as
`relayshield-deployer`, the operator, not as the Lambda role. It can populate the table today. What
the missing grant blocks is the LIVE monitor recording first-seen for anything collected from here
on, so the table would freeze at whatever the backfill writes. The script's grant step is now
non-fatal for exactly this reason: `set -e` was aborting before the backfill instructions printed,
which is what turned one IAM error into "I cannot backfill".

### Also outstanding

- **`relayshield-feed-maintainer`** — live on the stream, source in the repo since
  TAXII-PAGINATION-2, and was in NEITHER map. Third instance of that combination. Added to the
  **drift check only**. Read its first red diff before mapping it in the deployer.
- **An empty `relayshield_intel_first_seen` sits in `620534471984`** from the wrong-account write.
  Costs nothing on PAY_PER_REQUEST with no items. No delete command has been written for it on
  purpose.
- **The `relayshield-mcp` submodule is broken**: a gitlink in the index with no `.gitmodules` entry,
  which is why CI logs `fatal: No url found for submodule path`. Pre-existing, harmless, unfixed.

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

### Rain — DONE 2026-08-30. Demo recorded, both submissions sent.

Carried across four sessions and closed. The demo is `tools/rain_demo.py`: one command, an agent
discovers two MCP servers, pays $0.35 over x402 to check each before connecting, refuses
`modelcontextprotoco1.io` on an edit-distance-1 typosquat finding, connects to `mcp.so`. Unattended,
no account.

The payments are real and are the artifact that outlasts the video:
`basescan.org/address/0xa26054A4188e6D5c31A4DcdFcA27b0FfE247228d#tokentxns`. **Link that tab, never
the bare address** — the address page shows "Transactions Sent: N/A" and an empty list, because
x402's exact EVM scheme has the agent sign an EIP-3009 authorisation and the facilitator broadcast
it. The wallet never sends a transaction and never holds gas.

Agentic Startup Program form submitted, and the email sent to `apa@rain.xyz` from
`andrew@relayshield.net` with the recording attached. Both answer sets are in `rain_submission.md`,
verbatim, including the target-audience and stage decisions and why they were made.

Two things left open, and both are the reply's problem now: whether the Agent Control Layer has a
pre-issuance hook (the email asks rather than assumes), and the Sardine/Chainalysis paragraph never
got its outside read.

### Routavo — registered for early access 2026-09-02

`routavo.com`. "Connect your API once. Agents find it, call it, and pay for it." Metered per call,
settled the moment the API returns 2xx, 1% of what settles capped at a cent, no per-call fee, failed
calls cost nothing. Points at an OpenAPI spec rather than needing a rewrite.

Directly relevant: 28 live x402 endpoints priced $0.05-$0.35, already settling on Base, and
`relayshield_openapi_spec.py` is the artefact they want. **Founder registered for early access.**

Their "Control" pillar is SPEND control on the buy side -- allow, deny, rate-limit, cap per agent.
It answers "is this agent allowed to spend", not "is the thing it is about to pay legitimate". That
is the same gap as Rain, and it is the pitch TO them, not a conflict with them.

### OpenRouter key-revocation webhook — build it when the corpus has OR tokens

Sequenced behind data, like A8, and for the same reason.

The LLMjacking detector's OpenRouter pattern shipped in `844a2c3` (deployed 2026-08-27 11:11). It
has been live two days, so **there is no corpus of captured `sk-or-v1-*` keys yet** and nothing to
notify anyone about.

When there is, the integration is the revocation webhook: RelayShield detects a leaked OpenRouter
key in a criminal Telegram channel and calls OpenRouter to revoke it, before the key is drained.
That is the thing their own tooling cannot do, because they cannot see the channel.

**Trigger to build:** the first non-zero count of `sk-or-v1-*` in **`relayshield_stolen_sessions`**, NOT `relayshield_intel_iocs`.

**Corrected 2026-09-02.** A scan of `relayshield_intel_iocs` for `sk-or-v1-` returned 0 of 6,712,425 rows and was briefly read as "no OpenRouter keys collected". It is not: `_NHI_PATS` in `relayshield_intel_monitor.py` writes credential findings to `relayshield_stolen_sessions` (`type: nhi`), and `relayshield_intel_iocs` never receives them. A zero from the wrong table is not evidence of absence, and this one nearly became a recorded fact. Check it
before writing any of it.

**Then the RIGHT table was scanned, same day, and the answer was worse.**
`relayshield_stolen_sessions` returned `Count: 0, ScannedCount: 9`. Nine rows is
the WHOLE TABLE. And nine is a number this repo has seen before: the docstring of
`_store_observed_session` records "the table held 9 rows on 2026-08-16, all of
them source `demo`, after months of collection" -- the CORPUS-1 finding that
`_store_stolen_session` required a `matched_email` and so discarded every session
not already belonging to a customer.

If it is still nine, and still the demo rows, **the CORPUS-1 fix has written
nothing since it shipped**. `_store_observed_session` is only ever called from
the archive-parsing path, so "no observed rows" and "no archive was parsed" are
the same finding. A matching count is a LEAD, not a fact -- settle it with:

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/diagnose_stolen_sessions.py

It reports the table by `source`, says whether the observed path has ever fired,
and reads the INTEL-5 log lines to say WHERE the pipeline stops -- archives never
seen, oversized, download failed, wrong format, or handler raised. Each is a
different bug with a different fix, which is why `archives_parsed` as a single
number cannot tell you.

**Until that is fixed, no count out of this table means anything about the
criminal market.** It measures our collection. Do not read a zero here as absence
of OpenRouter keys in the wild, and do not quote any number from it. Do not build the webhook against zero rows, and **do not quote a captured
OpenRouter key count to OpenRouter, Stripe, or anyone else until the category clears 100** — the
standing measurement rule applies here with force, because this is a number that would be checked.

Rationale, and why this is the right ask of Stripe post-acquisition, is in
`openrouter_stripe_integration_angle.md`.

### Rain Agentic Startup Program — SUBMITTED 2026-08-30

See the Rain entry above. Kept only for the framing, which still applies to any follow-up: Rain's
Agent Control Layer already answers "is this agent allowed to spend this much". Nothing in it
answers "is the thing it is about to pay legitimate". An agent with a valid card, inside its limits,
paying a fraudulent API is a fully authorised transaction.

**Do not pitch against Sardine or Chainalysis.** They score the user and the funds; we score the
counterparty and the tool. Full analysis in `socradar_gap_closure_roadmap.md`.

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

## WHERE THE CURRENT WORK LIST LIVES — read this before answering "what's next"

**Added 2026-09-01, after a session answered "summarise the Top 10" by reciting the numbered list
in `NEXT_SESSION_2026-08-20.md` — twelve days stale, with at least three items already done and one
recorded as done that was never built.** The list was found by grepping for "Top 10", which is
exactly how a stale list gets promoted back to current: it is the only thing in the repo wearing
that name.

**There is no file called "the Top 10". Do not go looking for one.** The ordered list in
`NEXT_SESSION_2026-08-20.md` is a snapshot of one day in August and nothing has updated it since.
Any `NEXT_SESSION_*.md` is a historical record of the session that wrote it, never a live queue.

**The current state of the work is, in this order:**

1. **This file.** The "WHERE 2026-08-29 LEFT THINGS", "BLOCKED", "Also outstanding" and "OPEN TODOS"
   sections are maintained; a dated handoff file is not.
2. **`git --no-pager log --oneline -40`,** and the diff of anything it names. What was actually
   committed beats what a doc says was planned.
3. **Open GitHub issues, and the last run of every workflow** — `lambda_drift_check.yml` and
   `intel_channel_review.yml` especially. A red run that nobody has read is an open item whether or
   not any document mentions it.
4. **The roadmap files for a specific programme** — `socradar_gap_closure_roadmap.md` (A1-A8),
   `intel_corpus_growth_plan.md`, `telegram_miniapp_and_app_inventory_scope.md`. These carry IDs and
   are kept closer to current than the handoffs.

**Then say where each answer came from, and how old it is.** A status line with no source is
unverifiable, and this repo has now been bitten three times by a doc that said "done".

**A doc claiming something is done is a lead, not a fact — VERIFY IT IN THE CODE.** Two proven cases:
the XSOAR entry below, which needed `git ls-remote` to disprove, and **Top-10 item 8, "Ronin
`ronin:` prefix normalise", recorded in this file as done on 2026-08-29 and never written** —
`_looks_like_wallet_address` in `relayshield_telegram_webhook.py` tests EVM, Solana, TON, Bitcoin
and XRP, and `ronin:0x…` fails all five. One grep would have caught it. Grep before repeating a
"done".

**If asked to summarise the priorities and the sources disagree, say so rather than picking one.**
"The only list named Top 10 is twelve days old and these four items have moved since" is the useful
answer. Reciting the stale list as if it were current is not.

---

## STATUS CORRECTIONS — docs that are stale

`NEXT_SESSION_2026-08-20.md` is the last full handoff, but items have completed since and the file
was not updated. **Ask before treating anything in its "carried forward" list as open.**

Known completed after that handoff was written:

- **XSOAR PR #45206 / Tech Alliance (roadmap D3)** — **MOVED 2026-09-02. #45206 IS MERGED; THE
  PACK IS STILL NOT ON MASTER.** Both facts matter and neither replaces the other.

  demisto/content does not merge an external contribution straight to master. A bot merges it into
  an INTERNAL PR, which then runs their own pipeline. On 2026-09-02 `#45206` had lost its `/merge`
  ref (merged), and the bot comment named the successor: **#45742**, which is OPEN, has an
  approving review, and carries `Packs/RelayShield/`. Verified by content, not by refs alone:
  `pack_metadata.json` returns 200 on both PR heads and **404 on master**, with a control pack
  returning 200 so the 404 is real and not a blocked request.

  So the state is a three-stage pipeline and the claim only becomes safe at stage three:

  1. Contribution PR #45206 — **merged.** It has left our hands.
  2. Internal PR #45742 — **open**, approved, 1 failing check (`ci/gitlab/gitlab.xdr.pan.local`).
     That is Palo Alto's own internal GitLab pipeline, inside their infrastructure, on a PR authored
     by their `content-bot`. **We cannot see it and cannot fix it. There is no action for us.**
  3. `Packs/RelayShield` on master — **not there yet.** This is what a prospect checks.

  **Do NOT write "ships with Cortex XSOAR", "in the XSOAR Marketplace", or "available to XSOAR
  customers" anywhere yet.** What is true and checkable today: *"RelayShield's Cortex XSOAR content
  pack has been contributed to Palo Alto Networks' content repository and accepted; it is
  progressing through their internal release pipeline."*

  Moshe Eichler confirmed on the PR, in writing, that on merge the pack **gets a Marketplace listing
  page** and **is named in their Release Notes**. That is the moment the stronger claim unlocks, and
  it is worth a blog post and a landing-page line when it lands.

  `sh tools/check_xsoar_pack.sh` now tracks all three stages and prints the exact wording that is
  safe at the current one. Run it before the claim goes in any deck, email or landing page.

  **TODO, TRIGGERED BY THE MERGE, NOT BY A DATE.** When `check_xsoar_pack.sh` reports ON MASTER:

  1. **Blog post**, canonical on `blog.relayshield.net`, then the usual channel order. The angle is
     not "we shipped an integration" -- it is what the pack DOES that a Cortex XSOAR customer cannot
     do today: enrich an incident with indicators collected from criminal Telegram channels, which
     is the exclusive half of the corpus rather than the public-feed half. Do not quote a corpus
     number in it; MEASUREMENT DOCTRINE applies, and this is a post a competitor will read.
  2. **Landing-page line on the API site**, and only then. Wording once it is true:
     *"Available as a Cortex XSOAR content pack."* Link the Marketplace listing page directly, since
     Moshe confirmed in writing that one is created on merge.
  3. **Link their Release Notes entry** from the blog post. Also confirmed in writing. It is
     third-party proof, which is worth more than our own claim about ourselves.
  4. Re-run `check_xsoar_pack.sh` immediately BEFORE publishing either. The gap between writing and
     publishing is exactly where a false claim gets in.

  Note also: the demo requirement recorded under OPEN TODOS as gating the merge did **not** block
  #45206 — it merged without one. Do not carry that as a blocker again without re-checking.

  Two separate things were being conflated under "DONE", and they must stay separate:

  1. **The content pack PR (#45206)** — technical, in `demisto/content`, **still open**.
  2. **The Palo Alto Tech Alliance partnership** — commercial, and now gated on Palo Alto's new
     requirement of **3 named joint customers**.

  Neither blocks the other. The pack is a public contribution and does not need the Alliance. Do not
  report either as complete without checking the refs above.

  **VERIFIED 2026-08-29 by content, not just by refs.** A blobless sparse clone of `demisto/content`
  at master (`2c87a93`) holds **1,350 packs and zero files matching "relayshield" anywhere in the
  tree**, while `refs/pull/45206/head` carries all 13 files of `Packs/RelayShield/`. The pack exists
  only on the branch. **`sh tools/check_xsoar_pack.sh`** runs both checks; run it before "our pack
  ships with Cortex XSOAR" goes into any deck, email or landing page, because that is a claim a
  prospect can check in ten seconds.

---

## PARTNER COMMISSION — decided 2026-08-29, do not re-open

**20% recurring for 12 months**, on the six monitored subscription plans only. Not PAYG/x402 per-call
revenue, not the TI subscription. 60-day clawback on refund or chargeback, no self-referrals, and the
flat $25/$75 Tier 1 bounty is restricted to the business tiers.

Live at **`partners.relayshield.net`** (`cloudflare_worker_partners.js`, `wrangler.partners.toml`).
Full reasoning, including why not 30-40% and why not lifetime, is in `RelayShield_Strategy.md` §18.

**The attribution is `client_reference_id=p_<code>`, and the prefix is load-bearing.**
`client_reference_id` already carries the Telegram chat_id, and `relayshield_stripe_webhook.py`
branched on `if client_ref:` — any non-empty value entered the Telegram flow, failed to find a
pre-payment record and returned **200**, so Stripe never retries. A partner-referred customer would
have paid and never been onboarded. The webhook now requires a numeric value for the Telegram path,
routes `p_`-prefixed values to `referred_by` on the user record, and logs anything else loudly.
Never put a bare partner code in that field.
- **DFK outreach** (Top-10 item 7) — done 2026-08-22.
- **Ronin `ronin:` prefix normalise** (Top-10 item 8) — **NOT DONE. This line was wrong.**
  Corrected 2026-09-01 by grep: there is no `ronin` string anywhere in any `.py` file except two
  unrelated comments in `relayshield_api.py` about the Ronin bridge exploiter.
  `_looks_like_wallet_address` (`relayshield_telegram_webhook.py`) accepts EVM, Solana, TON, Bitcoin
  and XRP; `ronin:0x…` matches none of them and is rejected. Still blocks any Ronin-game pitch.

---

## Writing conventions

- **No em-dashes** in published copy. Applies to the short syndication versions too.
- Blog files carry a `NOT FOR PUBLICATION` line; everything below it is internal plan and checklist.
- **Do NOT post to X** (`@RelayShieldHQ` suspended) or **Hashnode** (abandoned 2026-07-29).
- Medium: **import with the canonical URL, never paste** — Medium has no Markdown paste.
- **No quote bars. Quoted text renders as an ordinary paragraph.** House style, decided
  2026-08-30. A `> ` block in the source still means "this is quoted"; `build_blog.py` renders it as
  a plain `<p>`. Do not regress this to `<blockquote>`.

  Two reasons. The bar is visually loud and does not suit these posts. And on Medium it is
  unreliable: the 2026-08-30 LLMjacking post imported with an empty paragraph inside every quote,
  showing as a gap with the bar running past the text, and the only fix after import is a
  forward-delete inside each quote by hand. Rendering `<blockquote><p>...</p></blockquote>` instead
  of a bare `<blockquote>` did NOT fix it, which is worth recording because it looked like it should.

  **So attribution lives in the prose, in the lead-in sentence before the quote** ("Anthropic is
  explicit about what that means:"). That is more robust regardless: prose survives every importer
  and every formatting change, and a dropped bar silently turns a vendor's words into our own
  assertion.

  Posts already frozen in `blog_content/` keep whatever html they were published with. Do not
  rewrite them to match; they are live pages.
- **A Medium import is a snapshot.** Editing the canonical post afterwards does not propagate. Any
  correction means editing the Medium copy by hand or deleting and re-importing, so get the
  canonical right BEFORE the import rather than publishing and fixing forward.
- **A post built on someone else's reporting links to it, in the first paragraph.** The 2026-08-30
  post quoted a vendor email at length and rested entirely on BleepingComputer's write-up, and
  shipped with no links at all. On our own page that is an editorial gap; on Medium it reads as if
  the reporting were ours. Say explicitly where the quotes come from too, in prose, because prose
  survives a formatting change and blockquote styling does not.
- Channel order: `blog.relayshield.net` canonical → Medium → **dev.to** → LinkedIn → Telegram →
  Farcaster → Mastodon.
- **dev.to was missing from this list entirely and was restored 2026-09-02.** It costs nothing, it
  accepts a canonical URL properly (unlike Medium, which snapshots), and it is where the developer
  audience for the API and the MCP server actually reads. It also unlocks the Apify content
  programme's second payout: $100 in Apify credits per article published on dev.to under their
  organisation, on top of $500 for the blog piece.
- Length limits: Mastodon 500 chars · Farcaster ~1024 bytes · LinkedIn 3000 · Telegram 4096.
  Write each short version to its own limit. dev.to has no practical limit; publish the full post
  with `canonical_url` set to the blog.relayshield.net URL.
