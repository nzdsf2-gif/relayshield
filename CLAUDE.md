# CLAUDE.md — read this first, every session

## HOW THIS FILE IS ORGANISED. READ THIS BEFORE ADDING ANYTHING TO IT.

**Changed 2026-10-18.** This file had grown to 802,620 characters across 212 sections, because
every session appended a dated record to it. Andrew reported that his local Claude Code reads only
up to 150,000 characters (his figure; not checked against Claude Code's own documentation), so most
of the file, including the rules written for him, was never seen by a session on his Mac.

**The split was lossless: every section was moved byte for byte, none was reworded.** The text
before the split is in git history (`git log -S "HOW THIS FILE IS ORGANISED"` finds this commit;
its parent has the old file).

    CLAUDE.md                            STANDING RULES ONLY. Hard cap 120,000 characters.
    docs/claude_memory/LOG_CURRENT.md    the recent session records. READ ITS LAST
                                         "WHERE ... LEFT THINGS" SECTION FIRST.
    docs/claude_memory/archive_NN.md     older records, original order, not auto-loaded
    docs/claude_memory/INDEX.md          every section heading, with file:line

* **NEW SESSION RECORDS ARE APPENDED TO `docs/claude_memory/LOG_CURRENT.md`, NEVER TO THIS FILE.**
  Appending here is what made it unreadable. A lesson that has become a rule EVERY session needs
  may be promoted into this file, as a deliberate edit, verbatim.
* **Where a section below says "this file" or "the Top 15 in this file", the current list is the
  last "WHERE ... LEFT THINGS" section of `LOG_CURRENT.md`.** Older lists were superseded by newer ones
  and are in the archive, which is a record of a day and not a queue.
* **A code comment or test that names a CLAUDE.md section may be naming one that now lives in the
  archive.** Find it with `grep -n "WORDS FROM THE HEADING" docs/claude_memory/INDEX.md`.
* **When `LOG_CURRENT.md` passes 90,000 characters:** `python3 tools/claude_memory.py --rotate`
  (dry run), then `--rotate --write`. `python3 tools/claude_memory.py --check` reports sizes and
  whether `INDEX.md` is current, and `test_claude_md_size.py` fails the build if a cap is passed.
* **A merge conflict in `LOG_CURRENT.md` is the same append conflict as before:** keep both sides
  with `python3 tools/resolve_md_conflict.py docs/claude_memory/LOG_CURRENT.md --write`. The
  standing rules in this file almost never change, so it should now rarely conflict at all.
* **Check the size before claiming a doc is "in CLAUDE.md":** a status that lives in the archive is
  invisible to a session that only read this file, which is how the old file hid its own rules.

## HOW TO DELIVER WORK TO ANDREW — the rule that keeps getting broken

**Claude Code on the web runs in a remote container. It cannot write to
`~/Side SaaS Hustle`. Committing and merging to `main` does NOT put a file on Andrew's Mac.**

**UPDATED 2026-09-03, and this SUPERSEDES the old "paste it into the chat" rule.** Andrew's
instruction, in his words: *"When you cite a file it means I expect you to provide a .md I can
download. I don't want you to paste the content inline."*

So: **whenever a session produces or updates a `.md` deliverable, SEND THE FILE so he can download
it, in the same reply that mentions it.** Use the file-sending mechanism, not a fenced code block.
A 400-line document pasted inline is unreadable in a chat window and he cannot save it.

- **Send the file. Do not paste it.** Mentioning a filename without sending it is the failure this
  rule exists to stop, and it happened three times on 2026-09-03 alone.
- **He saves it to `~/Side SaaS Hustle`, which is no longer the clone.** See the next section.
  Saving a delivered `.md` into the clone is what blocked three merges; the two directories are
  now separate so it cannot happen again.
- Commit it as well. The commit is the durable copy; the sent file is the delivery.
- If he asks for the content inline, paste it. Otherwise send.
- A file path, a PR link, or "run `git pull`" is not a deliverable.

## THE CLONE LIVES AT `~/dev/relayshield`. `~/Side SaaS Hustle` IS NOW A DOCUMENTS FOLDER.

**Changed 2026-09-05, at Andrew's request, and it SUPERSEDES every earlier statement in this file
that the repo root is `~/Side SaaS Hustle`.**

    ~/dev/relayshield        the git clone. Nothing is ever saved here by hand.
    ~/Side SaaS Hustle       a plain folder, NOT a git repo. Every .md sent to Andrew goes here.

**Why, and it is structural rather than a habit to remember.** The delivery rule above says send
every `.md` deliverable so he can download it. Git refuses to overwrite an untracked file it did not
write. So for as long as the download folder and the clone were the same directory, every file
delivered was a file that would block the next merge — and it did, three times across two sessions,
including once on the very file the same reply had just sent him.

Naming the colliding files never fixed it, because the next delivery collides too. Stashing works
but is a workaround applied forever. **Separating the two directories removes the collision instead
of managing it**, and he can save anything he likes into `~/Side SaaS Hustle` without ever thinking
about git again.

**Second benefit, free: `~/dev/relayshield` has no space in it.** Rule 2 below exists entirely
because `cd ~/Side SaaS Hustle` unquoted is three arguments. That whole class of failure is gone for
the clone. Keep the quoting rule anyway for the documents folder, which still has the space.

**MOVING THE CLONE BREAKS ABSOLUTE PATHS THAT LIVE OUTSIDE IT, AND THE REPO CANNOT SEE THEM.**
Found within hours on 2026-09-05: the RelayShield MCP server went dead in Claude Desktop AND Claude
Code, because both configs launch it by absolute path —

    /Users/andrewgibbs/anaconda3/bin/python3 \
      /Users/andrewgibbs/Side SaaS Hustle/relayshield_mcp_server.py

— and the client reported "disconnected", not "the path moved". The log said it plainly, every few
minutes for hours, and nobody was reading the log:

    can't open file '.../Side SaaS Hustle/relayshield_mcp_server.py': [Errno 2] No such file

Deriving paths from `Path(__file__)` fixed everything INSIDE the repo and could never have reached
these: they live in application-support directories the repo does not own. **So the move checklist
has a second half.** After relocating the clone, fix the places outside it that name it:

    python3 tools/fix_mcp_config_paths.py            # dry run
    python3 tools/fix_mcp_config_paths.py --write    # apply, with a backup

It rewrites strings AND dict keys, because Claude Code files its MCP servers under the project's
absolute path, so the key itself names the old location. Then QUIT AND REOPEN the client: an MCP
config is read at startup, so editing the file changes nothing until the app restarts.

Other places an absolute path to the clone can hide, none of which the repo can check for itself:
launchd plists, cron, shell aliases and functions, IDE run configurations.

**Never hardcode either path in a committed script.** `generate_pdfs.py` and `rsscan/test_verify.py`
both carried `/Users/andrewgibbs/Side SaaS Hustle/...` and would have broken silently on the move.
Both now derive the repo root from `Path(__file__).resolve().parent`, which is correct wherever the
clone lives and makes the next move free. A script that needs the repo root computes it; it does not
know Andrew's home directory.

Historical `NEXT_SESSION_*.md` files and other dated records still say the old path. Leave them —
they are records of a day, not instructions, exactly as the WHERE THE CURRENT WORK LIST LIVES
section says.

## EVERY COMMAND BLOCK STARTS WITH THE MERGE. NO EXCEPTIONS.

Added 2026-09-03 after the same failure three times in one session:

    python3: can't open file '/Users/andrewgibbs/Side SaaS Hustle/tools/x.py': No such file

Nothing was wrong with the script. **It was on the branch and not on his Mac**, because a push from
this container puts a file on GitHub and nothing else. Handing him a command that runs a tool
written this session, without the merge in front of it, guarantees that error.

So every ```zsh block that runs anything from this repo begins with these five lines, verbatim:

    cd ~/dev/relayshield
    git checkout main
    git --no-pager fetch origin claude/<this session's branch>
    git stash push --include-untracked -m "pre-merge untracked"
    git -c pull.rebase=false merge --no-edit FETCH_HEAD

**THE STASH LINE IS NOT OPTIONAL, AND IT WAS ADDED 2026-09-04 AFTER THE SAME MERGE FAILED THREE
TIMES ACROSS TWO SESSIONS.** The delivery rule at the top of this file and `git merge` collide by
design: any `.md` sent to Andrew and saved into `~/Side SaaS Hustle` is an untracked file, and git
refuses to clobber an untracked file it did not write. So the merge aborts, and every command after
it in the block fails with "No such file or directory" — which reads like a broken script and is a
blocked merge.

Naming the colliding files does not fix it, because the NEXT delivery collides too. That is exactly
what happened: a block that deleted `agent_baiting_scope.md` and `outreach_bot_prospects_curated.md`
then aborted on `mpp_settlement_endpoint.md`, the file the same reply had just sent him.

`git stash push --include-untracked` clears the tree unconditionally, so the block works whatever he
saved. **Stash, never `rm`**: the copies are recoverable with `git stash pop` if one turns out to
have been his own work rather than a paste of ours.

**The stash line stays even though the clone moved out of the download folder on 2026-09-05.** The
move removes the cause of the collision; the stash removes the consequence of any other untracked
file, from a half-finished experiment to a stray build artefact. Belt and braces, and it costs one
line.

Then the actual command. It is four wasted lines when he is already up to date, and it is the
difference between a working instruction and a broken one when he is not. **He is never up to date
by default: the branch is pushed, and merging is a thing he does, not a thing the push does.**

### When `git pull` fails on his Mac

`~/dev/relayshield` is the local clone. A known recurring failure:

    error: You have not concluded your merge (MERGE_HEAD exists).

Fix, in that directory:

    git status                 # see what is unmerged
    git commit --no-edit       # conclude the in-progress merge
    # or, to abandon it:  git merge --abort
    git -c pull.rebase=false pull origin main

**Never rebase this repo** — always `pull.rebase=false`.

---

## THREE INSTRUCTIONS I SHIPPED ON 2026-09-09 THAT COST ANDREW A ROUND EACH. READ BEFORE WRITING ANY BLOCK.

He asked for this section in these words: *"We've now wasted another needless turn... This needs to
stop."* All three were mine, none was a typo, and rules 1 to 14 above did not catch any of them.
They are one failure wearing three costumes: **I wrote instructions for states I had not looked at.**

### A. A MERGE BLOCK MUST ANTICIPATE THE CONFLICT IT IS GOING TO CAUSE

He ran the standard five-line merge block and got:

    Automatic merge failed; fix conflicts and then commit the result.

The block had a STOP IF for `MERGE_HEAD exists` and **nothing for the conflict itself**, so it ended
mid-way with no instruction for the state it had just produced. He had to resolve it himself.

**This is not bad luck, it is arithmetic, and it will happen on almost every merge from now on.**
EVERY session appends to CLAUDE.md. Two sessions running the same day therefore both append to the
same region of the same file, and git cannot know that appending two different sections to one
document is not a contradiction. **Proved immediately:** merging `origin/main` into this branch
minutes later produced the identical conflict, in CLAUDE.md, and nowhere else.

**So the merge block carries the resolution, and the resolution for CLAUDE.md is KEEP BOTH SIDES.**
It is an append-structured document; two new sections are two new sections, never an either/or.
Never resolve one by deleting the other, and never `git checkout --ours CLAUDE.md`, which silently
discards the other session's work.

    git checkout --merge CLAUDE.md
    # then delete the three marker lines by hand, keeping the text on both sides

**And the second half, which is what makes it cheap:** a conflict in CLAUDE.md ALONE is expected and
resolvable in ten seconds. A conflict in a `.py`, a `.toml` or a workflow is not, and means two
sessions edited the same code. **The block must say which it got**, because those are different
situations with different answers and "there was a conflict" does not distinguish them.

### A2. NEVER PUT `git add -A` IN A BLOCK HANDED TO ANDREW

Added 2026-09-11, after the merge block failed on him again and the failure was mine.

    No local changes to save
    error: Your local changes to the following files would be overwritten by merge:
      ansible-relayshield relayshield-snap
    warning: unable to rmdir 'ansible-relayshield': Directory not empty
    Merge with strategy ort failed.
    ...
    warning: adding embedded git repository: ansible-relayshield
    Aborting commit due to empty commit message.

**His clone holds two EMBEDDED GIT REPOSITORIES** -- `ansible-relayshield/` and
`relayshield-snap/`, separate projects cloned inside `~/dev/relayshield`. Two things follow and
the block assumed neither:

- **`git stash --include-untracked` CANNOT stash a nested git repo.** It reports
  "No local changes to save" and leaves them exactly where they are, so the stash line -- which
  exists precisely to clear the tree before a merge -- silently did nothing.
- **`git add -A` STAGES them as gitlinks**, which is what the "adding embedded git repository"
  warnings are. That is my line doing it, in a block I wrote, to a repository that is not ours.

Then the merge aborted, the resolver correctly reported nothing to do, the commit aborted with
an empty message because no merge was in progress, and the push said "Everything up-to-date".
**Every line after the first failure produced output that looked like a different problem.**

**THE RULE: a block handed over stages only the files it means to.** `git add CLAUDE.md`, never
`git add -A`. A wildcard add in someone else's working tree picks up whatever is lying in it --
embedded repos, build output, a half-finished experiment -- and the damage is silent because
`add` does not fail.

**And the stash line is not a substitute for knowing what is in the tree.** It handles untracked
FILES. It does not handle nested repositories, and this file has claimed since 2026-09-04 that
it "clears the tree unconditionally". **That claim is wrong and is corrected here.**

### B. PREDICTING A FAILURE AND SHIPPING IT ANYWAY IS WORSE THAN NOT PREDICTING IT

Step 3 of the Mini App checklist told him to check `app.relayshield.net`, and warned in writing that
a zone route attaches to a hostname without creating one. He ran it:

    curl: (6) Could not resolve host: app.relayshield.net

**The prediction was exactly right, which is the problem.** I had already reasoned my way to the
cause, written it down, and then shipped `wrangler.miniapp.toml` with the broken form anyway and
handed him a dashboard step as the remedy. **The fix was one line in a file I was already editing.**

A warning is not a fix. If a session can name the failure, it can name the change, and the change
goes in the same commit as the warning. Shipping a known-broken config with a note explaining that
it is broken spends the reader's round to discover something already known.

`wrangler.miniapp.toml` now uses `custom_domain = true`, which creates the DNS record. The general
rule is in that file's own comment: **an existing hostname may use a zone route; a NEW one uses
`custom_domain`.**

### C. AN INSTRUCTION THAT WRITES TO A LIVE SHARED SURFACE MUST BE PRECEDED BY THE ONE THAT READS IT

**The serious one.** Step 4 told him to run `/newapp` on `@relayshield_bot` with short name `app`,
then `/setmenubutton`. That bot **already carries the Telegram TI monitoring app**, and:

- **`/setmenubutton` REPLACES the existing menu button.** It does not add a second one. Following
  that step would have taken a live customer-facing surface off the bot, with nothing to undo it
  except knowing what had been there before -- which nobody wrote down, because nobody read it.
- **`app` is a generic short name on a bot that already has apps**, and Andrew had to say so.

**CORRECTED 2026-09-10, BY THE VERY CHECK THIS SECTION DEMANDS, AND THE CORRECTION IS AGAINST ME
IN BOTH DIRECTIONS.** He ran `/myapps` and it returned **"You currently have no web apps."** So:

- **The short-name collision I claimed did not exist.** `app` was free. That half of my warning was
  me over-reading his objection and describing a risk I had still not looked up -- the same defect
  one paragraph later, which is why the correction belongs here rather than in a footnote.
- **The destructive half was REAL, and the mechanism was the menu button, not a registered app.**
  `@relayshield_bot` runs the TI monitoring product through its MENU, and Andrew's instruction is
  that **the menu keeps the prominent control**. `/setmenubutton` would have replaced it. So the
  step was dangerous for exactly the reason given and for none of the reasons I evidenced.

**The rule survives the correction intact and is arguably strengthened by it.** I could not tell,
before he read the list, which of the two risks was the real one -- and I wrote a destructive
command anyway, on a guess that happened to point at the wrong hazard. **List first. What comes back
decides which danger you were actually in**, and a plausible-sounding reason for a warning is not
the same as knowing the reason.

**The registration went ahead on that evidence: title `RelayShield IDCheck`, short name `idcheck`,
`t.me/relayshield_bot/idcheck`.** The menu button was left alone, permanently, and that is a product
decision recorded rather than a checklist step deferred.

**I wrote a registration procedure for a surface I had never listed the contents of.** BotFather
state is not in the repo, is not visible from this container, and no session had recorded it. That
is the `_APIFY_BANNER` and MetaMask-Snap class exactly: asserting the state of a surface I cannot
see. The difference is that those two were false claims, and this one was a WRITE.

**THE RULE, and it is broader than BotFather.** Before handing over any command that creates,
renames, replaces or configures something on a live shared surface -- BotFather, a Cloudflare zone,
a Stripe product, an AWS resource, an npm or PyPI name, a marketplace listing -- **the block before
it lists what is already there, and Andrew reads that output before the write runs.** Two blocks,
never one; rule 14's "one block, one outcome" already says diagnosis and fix do not share a block,
and this is that rule where the fix is destructive.

**A name is never chosen by me for a surface I cannot enumerate.** Propose one, say why, and have
the listing step settle it -- a collision is invisible to a writer and obvious to the reader who can
see the list.

**And the specific facts, so no session re-derives them:** `/myapps` in BotFather lists a bot's
existing web apps. `/newapp` adds one. `/setmenubutton` REPLACES. `@relayshield_bot` carries the TI
monitoring app, so the Mini App takes a distinct short name and **must not touch the menu button
until it is settled what that button currently does** -- a direct link works without it, so there is
no reason to spend a destructive command on convenience.

### WHAT THE THREE HAVE IN COMMON, which is the part worth carrying

Rules 1 to 14 fix instructions that were malformed. **These three were well-formed instructions
written against an unexamined state**: the state of the two branches, the state of the DNS zone, the
state of the bot. Each was one read away from being right, and in every case I had access to the
read or could have asked for it.

**So, before a block ships: name the state it assumes, and say how that state was established.** If
the answer is "I assumed it", the block is not finished. "I could not check it from the container"
is not an exemption -- it is the trigger for making the check the reader's first step, which is what
NO AWS IN THIS SANDBOX IS NEVER A REASON TO SKIP A CHECK has said all along.

## THE MINI APP CHECKS LINKS AND TON. NOTHING ELSE, AND NOT AS A PRODUCT LIMIT.

Founder's instruction, 2026-09-11: *"The check tab should only show Ton addresses, not BitCoin or
Solana so we don't violate Tg TOS."*

A Telegram Mini App lives inside Telegram's rules and TON is the chain Telegram ships. Screening
Ethereum, Solana or Bitcoin from inside one is a fight with the host we have no reason to pick.
**UNVERIFIED from the container** -- core.telegram.org is egress-blocked, so the precise clause has
not been read here. The instruction is the conservative direction whatever the clause says.

**THE GATE IS IN THE WORKER, NOT IN `widget/relayshield-widget.js`, AND THAT IS THE WHOLE DESIGN.**
That file is copied into other people's bots and called from servers that are not Telegram at all,
where every chain is fine. `/v1/wallet-risk` still answers for EVM, Solana and Bitcoin and nothing
about the API changed. Putting the gate in the shared file would break every other caller to satisfy
one host's terms, and a test asserts it is absent there.

**A REFUSED ADDRESS IS NOT REDIRECTED ANYWHERE.** Pointing an Ethereum address at another of our own
surfaces from inside the Mini App is the same rule broken one link further out -- exactly the shape
of the Stars-to-Stripe trap that gets a bot restricted. It says what was pasted and stops.

**And a refused address cannot be watched or shared.** Watching an EVM address would write a row the
TON monitor will never re-check, which is the promise-nothing-keeps defect the monitor was built to
end, re-created one screen earlier.

**The ordering matters and is tested by EXECUTION rather than by reading.** TON's 48-character
friendly form sits inside Solana's base58 range, so testing Solana first refuses every address this
app exists to check, silently. Twelve real address shapes are run through the actual gate in node.

## THE MINI APP IS `t.me/relayshield_bot/idcheck`. THE MENU BUTTON STAYS WITH TI MONITORING.

Settled 2026-09-10, after `/myapps` returned **"You currently have no web apps."**

Registered as title `RelayShield IDCheck`, short name **`idcheck`**. Every planned deep link reads
`t.me/relayshield_bot/idcheck?startapp=<source>` -- corrected in
`miniapp_discovery_and_stripe_choice.md` §2, item 1 route (4), and the `TOP_15_2026-09-09.md`
snapshot. Nothing still says `/app`.

**`@relayshield_bot`'s menu button belongs to the TI monitoring product and KEEPS the prominent
control.** Andrew's instruction, and it is a decision rather than a deferred step: `/setmenubutton`
is not part of this launch and is not a later one. The Mini App does not need it -- the direct link
works on its own and item 1 already ranks the menu button fifth of six.

## NEVER SHIP TELEGRAM COPY THAT RELIES ON LEGACY MARKDOWN ESCAPING. IT HAS NONE.

**Asked for explicitly on 2026-09-11: "Write a note to memory not to merge and push future
changes to the Tg bot that allow legacy markdown with no escape syntax. This problem has
happened in multiple sessions."** He is right that it has recurred, and the reason it recurred
is the part worth recording.

**THE RULE. Telegram's legacy `Markdown` parse mode has NO ESCAPE SYNTAX.** A backslash before
`_` or `*` is not consumed. It renders visibly, or Telegram links `@relayshield` as a mention
and strands `_bot` beside it in a different colour, which is what the founder saw and called
sloppy. There were ELEVEN in `relayshield_telegram_webhook.py` and one in
`relayshield_forward_analysis.py`.

**So a value containing `_` or `*` goes in a CODE SPAN**, which legacy Markdown treats as
literal. Not a backslash. Never a backslash.

**AND A CODE SPAN CANNOT LIVE INSIDE A BOLD RUN.** `*Label: ` + code + `*` does not nest.
Close the bold first: `*Label:* ` then the code span. Three of these had shipped long before
anyone was looking at the handle -- `*Company domain set: {domain}*`,
`*LLMjacking risk detected for {domain}*`, `*Token Approvals - {short}*`.

**WHY IT KEPT COMING BACK, AND THIS IS THE ACTUAL FINDING: A TEST WAS ENFORCING IT.**
`test_relayshield_forward_analysis.py` carried `test_telegram_cards_name_the_bot_escaped`,
asserting `src.count("@relayshield\\_bot") >= 3` -- it REQUIRED at least three escaped
underscores, believing escaping was the fix. So the defect was not merely present, it was
PINNED, and any correct fix would have been reverted by CI as a regression.

This file had recorded the true cause on 2026-09-02 -- *"Telegram Markdown escaping never
worked... Quickstart is HTML now; the forward note uses code spans"* -- and that knowledge
fixed quickstart while a test in a different file held every other surface broken. **A lesson
recorded in one file is not a lesson the next file learns.** Same finding as the
`create-deployment` propagation race, which one script knew about and a script written four
days later did not.

**IT IS ENFORCED NOW, NOT REMEMBERED.** `test_telegram_markdown_escapes.py` fails on any
backslash-escaped underscore in either file, on any code span nested in a bold run, and on an
italic run opened across the handle. It skips comment lines, because prose describing the bug
is not the bug. Both guards were proven by REINTRODUCING the defect and watching them fail.

**Before any change to Telegram copy, run it:**

    python3 test_telegram_markdown_escapes.py

**And the standing preference, in order:** a code span for any value with `_` or `*`; HTML
parse mode for anything with real structure (that is why Quickstart is HTML); plain prose if
neither. **`parse_mode="Markdown"` plus a backslash is always wrong and there is no case where
it is not.**

**One constant, `BOT_HANDLE_MD`, for the bot's own handle.** This file already learned that
lesson when `checkemail@` was written as `emailcheck@` twice in one message.

## ENVIRONMENT — what this container can and cannot do

| | Status |
|---|---|
| AWS credentials | **None usable.** The `AWS_*` env vars are placeholders; STS returns `InvalidClientTokenId`. Anything touching DynamoDB or Lambda runs on the Mac with `AWS_PROFILE=relayshield` |
| AWS account | **239677749008 is the ONLY RelayShield account.** Every table, Lambda, secret and role lives there. `620534471984` is a SEPARATE account used solely to pre-audit new AWS workflows before they touch production — **no RelayShield resource is ever meant to exist in it.** It is the shell default, so an `aws` command with no `AWS_PROFILE=relayshield` silently resolves to it. **Reads** there return `ResourceNotFoundException`, which looks like a missing resource and is not. **Writes there SUCCEED** — see below |
| GitHub | Read/write via MCP. **Workflow dispatch is blocked** (`403 Resource not accessible by integration`) — Andrew must click *Run workflow* in the UI |
| Session repo sources | **One owner per session, fixed at session creation.** The repos a session can push to are chosen in the claude.ai/code repository picker BEFORE the prompt is typed. `add_repo` attaches more mid-session but **only from the same owner as the existing source**: from a `nzdsf2-gif/relayshield` session, `relayshield/rsscan` is refused with `cross-tier adds are not supported in v1` — not an authorisation error, and it fires even though both repos are public and `list_repos` reports `can_push: true` on them. **Reads are unaffected**, so `git clone --depth 1 https://github.com/relayshield/<repo>` works through the proxy with nothing attached. A task needing WRITE access to both `nzdsf2-gif/*` and `relayshield/*` is therefore **two sessions**, decided before any work starts. Verified 2026-09-03 |
| Egress | Blocked: `*.workers.dev`, `discord.com`, all `zapier.com`, `catalogapi.azure.com`, `powershellgallery.com`, arbitrary vendor sites. Reachable: GitHub, `raw.githubusercontent.com`, PyPI, WebSearch |
| Python | No `boto3`, no PowerShell. Use a throwaway venv in the scratchpad |

---

## COMMANDS HANDED TO ANDREW — his shell is zsh, on macOS

Every command written for him must run **exactly as pasted, in zsh**. Not bash, not "close enough".
Check each one against all five before sending it:

1. **No trailing `#` comments.** zsh does not treat `#` as a comment interactively, so it becomes an
   argument and the command errors.
2. **Quote any path with a space in it.** **Superseded in part 2026-09-05**: the clone is now
   `~/dev/relayshield`, which has no space, so `cd ~/dev/relayshield` needs no quoting. The rule
   still applies to `~/Side SaaS Hustle`, which is now the documents folder: unquoted, zsh sees
   three arguments.
3. **The repo root is `~/dev/relayshield`, not `~/dev/relayshield/relayshield`.** `relayshield/`
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

### 13. A CLAUDE CODE SLASH COMMAND IS NOT A SHELL COMMAND. Label it.

Added 2026-09-05, the same day it fired. A reply handed over:

    /plugin marketplace add nzdsf2-gif/relayshield
    /plugin install relayshield@relayshield

in a fenced block. Andrew pasted it into zsh, because rules 7 and 9 say that is
what a fenced block under **ANDREW RUNS THIS** means, and got:

    zsh: no such file or directory: /plugin

`/plugin`, `/mcp`, `/agents` and every other slash command are typed INSIDE the
Claude Code TUI. They are not executables and there is no `/plugin` binary. Same
class as rule 7's `role-to-assume:` and rule 11's `<paste the key>`: the text was
not wrong, it was not a command.

So slash commands get their own label, and never share a block with shell:

- **`ANDREW TYPES THIS IN CLAUDE CODE:`** followed by a ```text block. Never
  ```zsh, because that fence means "paste me into a terminal".

**AND THE SECOND HALF, which cost a further round on the same day.** The reply
that got the label right then asserted the TUI was the ONLY place, and it is not.
`/plugin` turned out to be unavailable in the environment Andrew was using, and
he was left with no route at all. There is a shell CLI that does the same job,
verified against `claude` 2.1.263:

    claude plugin marketplace add nzdsf2-gif/relayshield
    claude plugin install relayshield@relayshield

So the rule has two parts. Label which interpreter a block is for, AND **when a
capability has both a TUI and a CLI form, give the CLI form** -- it works in more
places, it is pasteable, and it is the one that can go in a ```zsh block under
ANDREW RUNS THIS. Check `claude <thing> --help` before claiming something is
TUI-only; that is one command and it would have settled this the first time.

The general form, for the fourth time: **every block a reader might paste needs
to say which interpreter it is for.** zsh, the Claude Code prompt, a browser
address bar and a Python REPL all look identical inside a fence.

### 14. A COMMAND IS NOT VERIFIED UNTIL IT HAS RUN IN *HIS* STATE. And every block says what success looks like.

Written 2026-09-05 at Andrew's request, after a session burned several rounds on
commands that were wrong in ways rules 1 to 13 do not cover. His words: this
"burns time and my scarce tokens". Rules 1-13 each fix ONE syntax defect. This
one fixes the process that keeps producing new ones.

**THE ACTUAL CAUSE, from five failures in one session.** Not one of them was a
typo. Every one was a command that worked in the container and could not work on
his Mac, because the STATE differed:

| What was sent | Why it failed | What would have caught it |
|---|---|---|
| `/plugin marketplace add ...` in a ```zsh block | slash command, not a shell command | rule 13 |
| "slash commands are TUI-only" | a `claude plugin` CLI exists | running `claude plugin --help` |
| `claude plugin marketplace add nzdsf2-gif/relayshield` | `owner/repo` reads GitHub's DEFAULT BRANCH; the files were only on a feature branch | checking `git ls-tree origin/main` |
| `fd8_prepare_republish.py --write` | wrote a version DOWNGRADE and missed the real pin | running it against real data, not a fixture I wrote to match my own assumption |
| `mcpServers` in `plugin.json` | silently ignored; the working key is `.mcp.json` | running `claude plugin details`, not `validate` |

**The container is not his Mac, and the differences are knowable.** Before sending
any command, check it against this list:

- **Files on disk here are not files on GitHub, and not files on his Mac.** A
  push reaches GitHub only. A merge reaches his clone only. Anything resolved by
  `owner/repo`, a raw.githubusercontent URL, or a CI checkout reads GitHub's
  DEFAULT BRANCH, so it fails until `main` is pushed.
- **Credentials.** No AWS, no PyPI token, no Stripe. Anything needing one is his.
- **Egress.** apify.com, clau.de, glama.ai, api.relayshield.net and more are
  blocked here. "I could not check" is a fact about the container, never about
  the thing (see NO AWS IN THIS SANDBOX IS NEVER A REASON TO SKIP A CHECK).
- **Installed tooling.** `claude`, `git` and `python3` exist here. `uv`, `~/.rsvenv`
  and `AWS_PROFILE=relayshield` are his side.

**THE RULE, in three parts.**

**1. Run it, or label it.** Every line of a ```zsh block must have been executed
in this container in a state equivalent to his, OR carry an explicit
`UNVERIFIED:` note saying what could differ. Presenting an unrun command as
verified is the failure. There is no third option, and "it is obviously right" is
how four of the five above were sent.

**2. Every block states its expected output.** This is the half that turns a
wasted round into a self-diagnosing one. The expensive failures above were not
merely wrong -- they gave him no way to tell "this failed because the branch is
not pushed" from "this failed because you are wrong", so the only move left was
another round trip. Each block ends with:

    EXPECT: <the exact line or shape that means success>
    STOP IF: <the specific failure, and what it means>

**3. One block, one outcome.** Never mix diagnosis with a fix in the same block:
he cannot act on step 5 before reading step 3's output. Diagnose, get the output,
then send the fix.

**THE FAILURE MODE RULE 14 DID NOT PREVENT, added the same day it fired again.**
A block was sent as `cd ~/mcp-live` then `mcp-publisher publish`, and it returned
401 `token is expired`. The command was correct and the block was not, because it
omitted the `login` step. Rule 14 says run it or label it, and this could not be
run here (no registry credential) so it owed an UNVERIFIED label and did not get
one.

So, concretely: **a block that drives an authenticated CLI includes the auth step
every time.** Not "you already logged in earlier" -- tokens expire, and the cost
of a redundant `login` is three seconds while the cost of omitting it is a round
trip. The same applies to `aws sso login`, `gh auth login`, `twine` and
`mcp-publisher`.

**Worked example of the required shape:**

    ANDREW RUNS THIS:
    ```zsh
    cd ~/dev/relayshield
    git --no-pager log --oneline -1
    ```
    EXPECT: one commit line.
    STOP IF: "not a git repository" -- the clone is somewhere else, say where.

**And the check that would have caught the worst one:** when a command depends on
a file being somewhere, verify the file is THERE, in that state, not merely that
it exists locally. `git ls-tree origin/main --name-only | grep <path>` is one
command and it would have saved two rounds.

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

### 6. Every command that RESOLVES AWS CREDENTIALS starts with `AWS_PROFILE=relayshield`.

**Widened 2026-09-13, after I broke this rule by reading it too narrowly.** A block
handed over read:

    python3 tools/iam_split_roles.py --from-snapshot ... --only relayshield-intel-feed --apply

with no profile, and the script refused:

    Refusing to run: credentials resolve to account 620534471984, not 239677749008.

**The rule said "every `aws` command" and I read that as the `aws` CLI.** It is not
about the CLI. It is about anything that resolves a credential chain -- a `python3`
script using boto3, a committed tool, a one-liner in a venv, `terraform`, an SDK
call from a REPL. The default profile is the pre-audit account, so omitting the
prefix does not error, it aims at `620534471984`.

**This one was an `--apply`, so it was a WRITE**, which is the expensive direction
this rule exists for: a write against the wrong account succeeds, prints a success
block, and creates a resource invisible to everything that needs it. The script's
own account guard caught it, and that guard is why this cost one line instead of a
stray IAM role in the audit account.

**So: if a command can talk to AWS, the block carries the profile, whatever the
command is spelled like.** The original rule text follows unchanged.



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


## "I CANNOT REACH AWS" IS A CLAIM ABOUT THIS CONTAINER, NOT ABOUT THE WORK

**Rewritten 2026-09-08 after Andrew pushed back on the first version of this section, and he was
right.** The first answer to "can you add agent-bait-scan to Bundle D remotely" was that it needs a
human at the AWS console. **That was wrong, and it broke a rule this file already carries.**

**What is true, and it was tested rather than quoted:** this container's `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY` are invalid. `boto3` `get_caller_identity()` returns
`InvalidClientTokenId`. AWS endpoints themselves ARE reachable through the proxy: `sts.amazonaws.com`
answers 302 and the marketplace catalog host answers 404, so egress was never the problem.

**What follows from that is what NO AWS IN THIS SANDBOX IS NEVER A REASON TO SKIP A CHECK already
says: the work MOVES, it does not stop.** Into a committed script run on the Mac, or into GitHub
Actions, which holds `relayshield-github-deploy` via OIDC. `lambda_drift_check.yml` and
`recover_live_handler.yml` are the precedent and have been for weeks. Answering "a human must do it
in a browser" ignored our own established route, and the failure is that I described the container's
limits as the task's limits.

**Adding a dimension is an API call**, `StartChangeSet` on the Marketplace Catalog API against
`prod-kkvurtspreofy`. Nothing in it needs a browser. `tools/marketplace_add_dimension.py` and
`.github/workflows/marketplace_dimension.yml` now do it.

### The danger is real, and it is not the one I named

From `relayshield_bundle_fulfillment.py`, written before anyone asked:

> Bundle A was originally planned for that same entity, but adding it there meant submitting a change
> set that **replaces the whole rate card**, which had already **rolled Bundle D's prices back to
> placeholders once (2026-07-27)**.

A change set does not add a dimension to a rate card. It replaces the card with whatever you hand
it, and an empty card is a valid document. So the tool reads before it writes, refuses a capture
older than 24 hours, and requires the entity id typed by hand in the workflow input.

**AND RUNNING IT FOUND A TRAP IN OUR OWN ARTEFACT.** `aws_marketplace/offer_baseline_2026-07-31.json`
is an **`Offer@1.0`** entity carrying **zero dimensions**, while the product plainly has two live
(`mcp_registry_risk`, `prompt_injection_breach`). **Dimensions live on the SaaS PRODUCT entity, not
on the offer.** Building a change set from that file would have submitted an empty rate card, which
is exactly the 2026-07-27 failure. Two guards now refuse it: the entity must be a `SaaSProduct`, and
the capture must already contain both known-live dimensions. Both were tested by triggering them.

### Two prerequisites, neither satisfied today

1. **The role has no catalog permissions.** The IAM snapshot carries
   `aws-marketplace:MeterUsage`, `BatchMeterUsage` and `ResolveCustomer` -- metering only.
   `DescribeEntity`, `ListEntities` and `StartChangeSet` are all absent, so even `--describe` fails
   until they are granted. That grant is itself an IAM change, and note the shared role's inline
   budget is full, so it is a customer-managed policy.
2. **The product decision, which this tooling does not overrule.** `AWS_DIMENSION_NAMES` in
   `relayshield_agentic_api.py` says agent-bait-scan is deliberately absent until the endpoint has a
   MEASURED false-positive rate, because a published dimension is an expensive place to discover a
   heuristic needs tuning. **Access was never the gap:** a Bundle D key already reaches
   `/v1/metered/agent-bait-scan`, because the gate keys on `bundle_d_access` rather than a
   per-endpoint allowlist, and an AWS-licensed caller falls through to the Stripe rail and IS billed.
   No revenue leak, no access gap.

**So the capability now exists and the decision is the only thing left**, which is the right way
round and was not the case this morning.

---

## A PUBLIC LISTING CARRIES ONLY CLAIMS THAT STAY TRUE WITHOUT MAINTENANCE

**Andrew's observation, 2026-09-09, and it is better than the answer it corrected:** *"Your
corrected metrics are also stale which was a lazy response. The numbers are constantly getting
outdated so they're always going to be out-dated which make me wonder if we should at a minimum cite
only metrics that change infrequently."*

He is right, and the first fix I proposed was wrong in an instructive way. The Bundle D listing
quoted *"5.0M+ indicators of compromise, 3,750+ malware families, and 85+ monitored criminal Telegram
marketplaces"* in three places. My answer was to replace them with the corrected figures. **That
swaps one expiry date for another** -- and each refresh is an AWS change set with their review
latency attached, on a PUBLISHED page, which is an absurd amount of machinery to spend on a number
that is wrong again next month.

**The rule: on any page we cannot cheaply edit, name the SOURCES and the CAPABILITIES, not the
COUNTS.** "Collected continuously from monitored criminal Telegram marketplaces, infostealer log
dumps and public indicator feeds" is true today, was true in June, and needs no maintenance. "5.0M
indicators" needs a change set to stay honest.

**This is MEASUREMENT DOCTRINE arriving where it was always pointed.** That section has said since
August that the corpus headline is never quoted, because most of it is ingested public feeds every
target buyer already has, and quoting it nearly killed the Segment 1 outreach in front of people who
checked. The AWS listing was the most public place we were still doing it, and it took a question
about staleness to notice. The listing now says outright that we do not quote a corpus headline and
why, which turns the doctrine into a differentiator instead of an omission.

**A count that IS allowed is one that changes by a deliberate act with a commit behind it.** "An MCP
server exposing 13 tools" is fine: it moves when we ship a tool. Counted from
`hf-space-mcp-server/app.py`'s own manifest, which is the file deployed as this listing's registered
MCP endpoint, and verifiable in one command:

    grep -c '"name": "' hf-space-mcp-server/app.py

**It is enforced, not remembered.** `tools/marketplace_add_dimension.py --with-copy` refuses to build
a change set whose copy quotes any of those figures, and says why.

**And the copy ships in the SAME change set as the agent-bait dimension.** One submission is one AWS
review cycle. Two is two cycles plus a window where the copy advertises a capability the rate card
cannot bill.

---

## WHEN SOMETHING IS WRONG, SAY WHAT TO DO ABOUT IT. A DIAGNOSIS IS NOT AN ANSWER.

**Asked for explicitly on 2026-09-09, in Andrew's words: "Make a note in Claude.md if something is
wrong to provide concrete recommendations. Dont leave me hanging as you did."**

What earned it: a reply reported that `smithery.yaml` was `type: stdio` rather than pointing at the
HF Space, said the recollection was mistaken, and stopped there. Every word was accurate and it left
him holding a problem with no next move. He had to come back and ask what to do, which is a round
trip spent on something that should have been in the first reply.

**This is the same failure as rule 14's, one level up.** Rule 14 says a command must run in HIS
state. This says a FINDING must come with the action it implies. A finding with no recommendation
outsources the thinking to the person with less context, which is exactly backwards.

**So every "this is wrong", "this is missing", "this cannot work" is followed, in the same reply, by:**

1. **What I recommend**, named as a recommendation and not a menu. One option, chosen. If there is a
   real trade-off, say which one I would take and why, then list the alternative -- never a list of
   three with no pick, and never "it depends on your priorities", which is a way of not answering.
2. **What it costs**, roughly. Half an hour, a day, a review cycle, a round trip.
3. **Who does it and how**, with the label rule 9 requires. If it is mine, do it in the same session
   rather than describing it.

**And where I genuinely cannot decide -- because it is a business call, a spend, or a thing only he
can see -- say THAT explicitly and give the recommendation anyway**, marked as mine to be overruled.
"I would do X, but this is your call because it commits money" is an answer. "Here are the options"
is not.

The one exception is a question that is genuinely his to answer and has no default: those go through
a direct question, asked once, with my own recommendation attached to it.

---

## PAYPAL ON relayshield.net: NO. DECIDED 2026-09-08.

Asked directly, and the answer is not close.

**What we sell and how it is paid for today.** Six monitored subscription plans and bundle
checkouts on Stripe; pay-per-call on x402 settling USDC on Base with no account at all; AWS
Marketplace for Bundle D and the TI tiers. Three rails, each matched to a buyer.

**PayPal adds a fourth rail and reaches no buyer the first three miss.** The API buyer is a
developer who pays by card or by wallet, both already served. The AWS buyer must transact through
AWS by definition. The agentic buyer is the entire reason x402 exists and cannot use PayPal at all,
because there is no human present to approve a checkout.

**And it is not free to add.** A payment rail is not a button: it is a webhook to verify, a
subscription lifecycle to reconcile, a refund and chargeback path, and a second source of truth for
"is this customer entitled". `relayshield_stripe_webhook.py` and the `client_reference_id` incident
are the evidence for how much care one rail already takes -- a non-numeric value in that field
silently returned 200 and a paid customer was never onboarded. Doubling that surface for a buyer
segment we cannot name is the wrong trade.

**The one condition that would change it**, so this is not re-litigated on a hunch: a named
prospect who says they cannot buy without it. Not a general belief that PayPal converts, which is
true in retail and irrelevant here. Until that person exists, the answer is no.

---

## "IT IS NOT IN THE REPO" IS A CLAIM ABOUT ORIGIN, NOT ABOUT THE REPO

**Added 2026-09-07, after I made exactly this mistake and billed it to somebody else.**

I grepped this repo for `FD-13`, got nothing, and told Andrew there was no FD-13 and that an earlier
session had said *"Added as FD-13"* without ever writing it down. **All of that was wrong.** FD-13
was written properly, as a full section in `FRONT_DOORS.md`, by commit `63fc78d`. That session did
its job. The commit was sitting on Andrew's local `main`, unpushed, and this container reads GitHub.

So the sequence was: a correct session, a correct commit, an unpushed clone, a container that can
only see `origin`, and then me converting "absent from origin" into "never written" and asking
Andrew to re-paste a decision the repo already held. He had to do the work twice because I read my
own blind spot as his omission.

**This is the LOCAL MERGE IS NOT A PUSH rule, running in the direction nobody wrote down.** That
section already says a merge on his Mac puts a file in his clone and NOT on GitHub. The unstated
corollary is what bites: **a grep in this container therefore proves nothing about his clone.** It
proves the file is not on `origin/main`, which is a different and much weaker statement.

**THE RULE, in two halves.**

**1. Say what you actually checked.** `git grep` here answers "is it on origin". It does not answer
"was it ever written", "is it on his Mac", or "did a session do its job". Report the first. Never
report the second, third or fourth on the evidence of the first:

    git --no-pager grep -n "FD-13" origin/main -- '*.md'     # answers: is it on origin/main
    git --no-pager log --all --oneline -S "FD-13"            # answers: has any FETCHED branch held it

Neither reaches an unpushed commit on his machine. Nothing in this container can. **When something
expected is missing, the first hypothesis is that it is unpushed, not that it was never done** --
and the way to settle it costs him one command:

    cd ~/dev/relayshield && git --no-pager log --oneline origin/main..main

Empty output means his clone holds nothing we cannot see, and only THEN is "not written" supported.

**2. A gap in this repo's memory is written in the first person, and only after that check.** If it
really is missing, it is mine, and it is fixed in the same reply rather than reported as a condition
of the repo. Continuity across sessions is the entire purpose of these files; it is not a thing
Andrew maintains by re-pasting decisions into a prompt.

**And the part that survives regardless of who was at fault.** A statement in a chat reply that
something *has been* added -- added, registered, recorded, decided, noted, created, documented,
closed, scoped -- is a promise that a commit exists in the same session. The container is reclaimed;
the chat reply is not the record. New front doors and status changes go in `FRONT_DOORS.md`, both
the table row and the section, because a row with no section is half a record. Changes to what is
next go in this file's Top 15, regenerated rather than annotated.

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

## THE AWS-LICENSED PATH MAKES NO THIRD-PARTY CALLS. ANY NEW LOOKUP ON THESE ENDPOINTS MUST HONOUR THE FLAG.

**2026-10-25, decided by Andrew.** The AWS Foundational Technical Review needs `prod-kkvurtspreofy` "deployed on AWS", which AWS defines as every plane AND every
third-party service that handles customer data running on AWS. So for a key with `aws_customer_id` the dispatchers set `params["_aws_data_path"]` (from the key
record, never from the request), and `bulk-identity-risk`, `tech-stack-cve` and `mcp-registry-risk` skip their outbound lookups, rescale the remaining score and name
`signals_not_run`. Stripe-direct, x402 and free callers are unchanged. Detail and tests: `test_aws_first_party_path.py`, LOG_CURRENT "decision + build".

**THE RULE: a new outbound call inside any of those five endpoints, or inside anything they call, is skipped when `_aws_data_path` is set, in the same commit, with a
test that fails if it runs.** Otherwise the architecture declaration on the listing becomes false and nothing says so. A missing signal must be rescaled and named,
never zeroed: a lookup that scores 0 reads as clean. The AWS MCP server is limited by `RS_MCP_TOOLS` to the tools the listing sells, for the same reason.

**Never "dilute, get validated, switch it back on".** The declaration has to stay true after approval.

**PRICE, decided the same day:** the AWS edition is sold 5 to 10 percent BELOW Stripe-direct (`aws_marketplace/bundle_d_aws_prices.json`, applied by
`tools/marketplace_update_offer_prices.py`). Code comments that say Bundle D is "same product, same price, two doors" predate that and are wrong. Never change the
AWS rate card by any other route: a change set replaces the whole card.

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

## THE API LANDING PAGE IS `https://api.relayshield.net/developers`. SETTLED. DO NOT RELITIGATE.

**Written 2026-09-15 at Andrew's explicit instruction, in his words: *"The actual url is
https://api.relayshield.net/developers. We've been through this ad infinitum in prior sessions.
Write a note to your Claude.md memory so you never relitigate this statement of fact again."***

**THE FACT, and it is not a preference, a recommendation, or a thing to re-derive:**

    https://api.relayshield.net/developers        the API landing page. THIS URL.
    https://api.relayshield.net                   the API HOST. Not the landing page.

**The bare host is where ENDPOINTS live** -- `/v1/link-check`, `/v1/wallet-risk`, `/badge.js`, the
marketplace fulfillment path, `zapier-relayshield`'s `API_BASE`, the XSOAR "Server URL" field. Those
uses are correct and must not be "fixed" into `/developers`; they are a different thing.

**Everywhere a HUMAN or a LISTING is pointed at the landing page, the path is `/developers`.** A
catalogue's Website field, an outreach message, a blog link, a marketplace listing, a README, a chat
reply that names the URL. `cloudflare_worker_miniapp.js` already has this right --
`const DEVELOPERS = API_BASE + "/developers";` -- and that constant, not a hand-typed string, is the
shape to copy.

**THE ROOT RENDERING SOMETHING IS NOT EVIDENCE AND IS PROBABLY WHY THIS KEEPS COMING BACK.**
`api.relayshield.net` in a browser returns a page titled *"RelayShield API: Security Intelligence for
Developers"*. **That does not make the root the address.** A future session that opens the root, sees
the developer page, and concludes the landing page "is at api.relayshield.net" will be wrong in
exactly the way every previous session was wrong, and will spend one of Andrew's rounds being
corrected. The page having more than one route to it does not give it more than one address.

**AND `?source=` BELONGS ON `/developers`, WHICH IS THE HALF THAT COSTS REAL MONEY IF IT DRIFTS.**
Every attribution key in `_SOURCE_BANNERS` is read by `handle_landing_page` in
`relayshield_developer_signup.py`. So:

    https://api.relayshield.net/developers?source=tg-miniapp-tonapp    CORRECT
    https://api.relayshield.net?source=tg-miniapp-tonapp               WRONG, and it is FD-8's shape

A `?source=` hung on the bare root is a key that is sent, is not read by the banner table, and logs
nothing under that key -- attribution that looks like it worked, which is the four-month defect this
repo already paid for once. **`test_miniapp_routes.py` fails on that form**, proven by writing one.

**In PROSE, say the URL rather than "the API landing site"** whenever the reader might need to open
it. The phrase is fine as a category -- it is Andrew's own, and this file uses it -- but a sentence
that leaves someone guessing the path has not delivered the thing they needed, which is rule 9 in a
new place. When a reply names it as a destination, name it as `api.relayshield.net/developers`.

**There is nothing here to weigh up and no trade-off to surface.** It is a statement of fact about a
live surface. Do not propose the root, do not ask which one is meant, and do not write a section
reasoning about it. Read this line and move on.

## I SAID THE WHATSAPP FRONT DOOR DID NOT EXIST. IT DID. `--all` IS NOT ALL.

**2026-09-17, and the founder corrected it in five exclamation marks: *"We implemented
the WA front door in the last session!!!!!"*** He is right. It is commit `b641375` on
`origin/claude/laughing-bell-gxagsd`, complete with the parser, the links, 260 lines of
tests and a funnel stage.

**THE COMMAND THAT PRODUCED THE FALSE NEGATIVE, AND IT LOOKS AIRTIGHT:**

    git --no-pager log --all -S "wa.me" -- '*.py' '*.js'     -> nothing

**`--all` MEANS EVERY REF THIS CONTAINER HAS FETCHED. IT DOES NOT MEAN EVERY REF ON
ORIGIN.** A session starts with `main` and whatever branch it was given. I had run
`git fetch origin main`, so `--all` covered exactly two refs, and the branch holding the
answer was never among them. One `git fetch --all` before the search returns it
instantly, which is how it was found in the end.

**And the pathspec was a second, independent hole.** `-- '*.py' '*.js'` would also have
missed a `wa.me` that landed only in a `.md` or a `.json`, which is where half this
repo's decisions live.

**THIS IS THE "IT IS NOT IN THE REPO IS A CLAIM ABOUT ORIGIN" RULE, ONE LAYER FURTHER
IN, AND THE NEW HALF IS WORSE THAN THE OLD ONE.** That section warns that a grep here
says nothing about the founder's unpushed clone. What it did not say is that a grep here
says nothing about **pushed branches this container never fetched either**. The work was
on GitHub, public, fetchable in one command, and I reported it as non-existent -- then
built a recommendation, a section of this file and a Top 10 item on top of that.

**THE RULE: before any claim that something was never built, `git fetch --all --prune`,
then search with NO pathspec.** Both halves. And the search that actually settles it is
one line:

    git fetch --all --prune && git --no-pager log --all --oneline -S "<string>"

**The cost was not the wrong answer, it was what I did with it.** I wrote a
recommendation ("open the door, then point at it"), a Top 10 item and a CLAUDE.md
section from an absence I had not established, and the founder had to spend a round
telling me the thing already existed. An absence is a finding like any other and it
needs the same evidence a presence does.

### WHAT IS ACTUALLY BUILT, AND THE ONE THING THAT IS NOT

`b641375` and `9e51b56` carry, all on that branch and none of it on `main`:

* **`parse_wa_source()`** in `relayshield_whatsapp_webhook.py` -- `SRC_<key>` out of the
  prefilled message BODY, because WhatsApp has no deep-link payload, **parsed BEFORE the
  user lookup** since a front-door arrival is by definition unknown and the unknown-user
  branch returns 200 and stops. Parsing after it would attribute every arrival to
  nothing, forever, while looking correct in the diff.
* The token is **stripped from the body**, so the user's first real instruction is not
  prefixed by a string our command parsing has never seen.
* `SRC-` accepted as well as `SRC_`, because the prefill is editable text a human can
  retype and every key we register is itself hyphenated.
* **A real defect fixed in passing: the inbound log line wrote the customer's phone
  number in the clear** into CloudWatch on every message. It is hashed now, like every
  other identifier in that file.
* Links on the **blog footer** (`wa-blog`) and the **Mini App** (`wa-miniapp`), a
  **WHATSAPP funnel stage**, a **DIRECTORY stage**, and `tools/wa_front_door_link.py`.

**THE ONE THING MISSING IS THE NUMBER.** Both Workers declare `const WA_NUMBER = ""` and
render the paragraph only when it is non-empty, so today the links are absent rather than
broken -- deliberately, because `wa.me/` with a hole in it renders as a page rather than
failing. The number is in Secrets Manager and no session can see it.

**THE CORRECTION THAT MATTERS FOR THE PRODUCT, AND IT SURVIVES MY BEING WRONG ABOUT THE
CODE:** `relayshield_whatsapp_webhook.py` still answers an unknown number with *"It looks
like your account isn't set up yet. Visit relayshield.net to sign up"* and returns. So
the front door is built, the attribution is correct, and **what a stranger finds behind it
is still a closed door.** That is a product decision rather than a defect -- it is worth
knowing before the link is placed widely, not after.

## THE PRE-HANDOVER CHECKLIST. ASKED FOR BY NAME, 2026-09-19, AFTER SEVEN REFUSALS.

**His words: *"Step 7 failed again and so did you!!!! I feel your approach is careless trial
and error. You've not learned anything. Write a message to Claude.memory to explain how you
will avoid foolish errors to avoid unnecessary future turns."*** He is right, and the
sections above are the evidence: I have written a post-mortem after every one of these and
the next step still failed. **A record of what went wrong is not a method for making the
next thing right.** This section is the method. It is deliberately short, because the
previous ones were long and did not work.

### WHAT ACTUALLY FAILED, WHICH IS NOT WHAT THE ERRORS SAID

    a logo URL never uploaded          I did not fetch what AWS would fetch
    5 changes where 13 are required    I read the accepted example halfway
    a fix sitting on a branch          I did not check which files the job reads
    four descriptions over 90          I compared the shape and not the fields
    a step numbered 6, run sixth       I put the ordering in prose, not the artefact
    CREATE-NEW_PRODUCT                 I made a human type an 18-character phrase

**Every one was knowable before the click, from inside this container, for free.** Not one
needed AWS to answer. I handed the step over anyway and let the reader discover it, and the
apology afterwards has never once prevented the next one.

### THE CHECKLIST. FOUR QUESTIONS, BEFORE ANY STEP LEAVES THIS SESSION.

**1. What must the reader TYPE? Make it impossible to get wrong instead of instructing them.**
A free-text box in a workflow input is a keystroke away from a wasted round. If the set of
valid values is known, it is a `type: choice`. If it is not known (an id AWS assigns), the
TOOL validates the shape and normalises it -- strip the `@1`, strip the whitespace -- and
refuses locally with a message naming where the right value is. **A dropdown keeps every bit
of a confirmation's safety: the dangerous value is not the default and has to be chosen.**

**2. What does the job READ? Every file, not just the workflow.** A dispatch runs `main`'s
copy of the workflow, the tool it runs, and the DATA it is pointed at. If any of them is on
my branch, the step is a merge followed by a click, and the merge is IN the step.

**3. What will the remote system VALIDATE? Reproduce it here, before spending the call.**
It fetches a URL -- `curl -I` it. It requires every dimension priced -- assert it. It caps a
field -- measure the accepted example. **And point the check at the document actually being
sent**: the field comparison existed for two days and was hard-wired to the create set, so
the test offer it never read carried an over-length description the whole time.

**4. Does the ARTEFACT carry the order and the values, or does my prose?** A numbered list is
read by its numbers. A fenced block under a heading is what gets run. An `EXPECT:` line is
read as truth. **Prose beside any of them loses**, so reorder the file, fix the number, move
the step. And an `EXPECT` is written from the requirement or the accepted example, never from
our own artefact -- one written from our own document confirms our own document.

### THE ONE RULE UNDERNEATH ALL FOUR

**When a remote system has refused you once, stop fixing the thing it named and diff your
artefact against one it accepted, field by field, in both directions.** The refusal is a
symptom and names one field. The accepted example is the specification and names all of them.
`bundle_a_*.json` answered every single one of these failures and was sitting in the same
directory each time.

### AND THE COST OF THIS SECTION ITSELF

This file is enormous and I have added to it every turn. **Adding a section is the cheapest
thing I can do and it is not the fix.** The fix is the artefact change in the same commit:
the dropdown, the shape validator, the moved step, the preflight. If a turn produces a
CLAUDE.md section and no change that makes the failure impossible, it has not delivered
anything -- it has written down an apology and billed a round for it.

## A TEST THAT BUILDS THE INPUT IT EXPECTS PROVES NOTHING. RUN CODE THAT PARSES A LIBRARY'S OUTPUT AGAINST THAT LIBRARY.

**2026-10-20, and it cost Andrew a round.** `tools/corpus_distinct.py` shipped with 67 green tests and died on its first real
run with `'str' object has no attribute 'get'`. The code parsed DynamoDB's low-level `{"S": "text"}` items. It was handed
`dynamodb.meta.client`, the resource's client, which returns plain Python values. **The fake client in the tests returned
`{"S": ...}`, because that is what I had written the code to expect**, so the suite tested my assumption against itself and
could not fail.

**THE RULE.** When code parses the output of boto3, botocore, an HTTP API or any library, at least one check must use THAT
LIBRARY'S real output, not a stand-in written by the same hand as the code. For boto3 this is cheap and needs no AWS:
`botocore.stub.Stubber` validates every request AND response against the real service model. A throwaway venv in the
scratchpad is enough (`python3 -m venv`, `pip install boto3`), and it caught two further mistakes in the same session
(the wrong request-parameter form, and a probe that reused a mutated dict). The repo's own suites stub `boto3` out, so this
check lives outside them: say so, and say what it covered.

**The same session, second half of the lesson:** before handing Andrew a command that scans a large table, read its memory
profile. `ti_demo_metrics.py --distinct` holds every sighting row in one list (~9.5M rows) and ended on his Mac with no
result. And a tool that writes in bulk must not be serial and silent: `backfill_first_seen.py --apply` was ~470K one-at-a-time
writes with no output, about two hours, and had been started and abandoned (194,987 rows were already there).

## 2026-10-06: NO THIRD-PARTY ATTRIBUTION IN ANYTHING A CUSTOMER READS. I BROKE IT ONE TURN AFTER WRITING THE PRIVACY POLICY.

**Andrew's rule of thumb, restated 2026-10-06: we never name a third-party data partner in our
documents.** It was not written down in this file before today, which is why I put Have I Been
Pwned and Hudson Rock by name into the privacy policy, the Data Sharing list and the in-app result
card in the v1.7.0 work. `exposureCopy.ts`, `cloudflare_worker_privacy.js` and the listing now say
"breach records and infostealer logs" and "third-party data providers".

**The policy still DISCLOSES that the typed address goes to third parties, and that is not
negotiable.** A free check that quietly sends an email address to two recipients is a disclosure
failure however good the feature is. Not naming a vendor and not disclosing a recipient are different
acts; the rule removes the first and never the second. **A distinct paragraph for each category
("one for breach records, one for infostealer logs") keeps it specific without a name.**

`test_cs_mobile_free_check.py::test_no_customer_facing_surface_names_a_data_vendor` fails on
`have i been pwned`, `hudson rock` or `hibp` in the privacy Worker, the store listing and every app
source file, proven by putting a vendor name back. This file, the code comments and internal docs are
exempt on purpose: the rule is about what a customer reads.

**OPEN, and it may collide with the rule:** Hudson Rock's free Cavalier API terms are still UNREAD.
Free community APIs sometimes REQUIRE attribution as the condition of free use. If theirs does, the
rule and the licence cannot both be kept, and the answer is a call for Andrew, not a guess. Read their
terms before the free check is promoted.
