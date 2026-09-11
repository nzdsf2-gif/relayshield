# CLAUDE.md — read this first, every session

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

## THE MERGE THAT FAILED THREE TIMES: REPRODUCED, AND THE FIX IS ONE LINE

**2026-09-11. Andrew ran the same block three times across two turns and got the same
"0" result each time.** Two of those turns were spent on my diagnosis rather than on the fix,
and the diagnosis was wrong twice before it was right. **It has now been REPRODUCED in a
scratch repo, byte for byte**, so this section is a measurement rather than a theory.

**The exact failure:**

    No local changes to save
    error: Your local changes to the following files would be overwritten by merge:
      ansible-relayshield relayshield-snap
    warning: unable to rmdir 'ansible-relayshield': Directory not empty
    Merge with strategy ort failed.

**The cause, and it is a LOOP I built.** Rule A2 already records that `git add -A` stages his
two embedded git repositories as gitlinks. What A2 did not work out is what happens next:

1. `git add -A` puts `ansible-relayshield` and `relayshield-snap` in the INDEX as gitlinks.
2. `git stash --include-untracked` **cannot stash a nested git repo.** It prints
   "No local changes to save" and leaves them exactly where they are.
3. A **fast-forward** merge survives this. A **three-way** merge does not -- and every merge
   from now on is three-way, because `origin/main` already carries a merge commit.
4. The failed merge partially unwinds the index, so a *second* run of a block WITHOUT
   `git add -A` would have worked.
5. **But the block HAD `git add -A` at the top**, which re-staged them before every attempt.

So each run re-created the exact condition that made the previous run fail. That is why three
identical failures looked like one stubborn problem and were actually the same fix, refused
three times by my own block.

**THE FIX, VERIFIED END TO END IN A SCRATCH REPO INCLUDING IDEMPOTENCY:**

    git rm -rf --cached -q --ignore-unmatch ansible-relayshield relayshield-snap

`--cached` touches only the index, so **the embedded repos and their history are untouched on
disk** -- confirmed by reading their git log after the merge. `-f` is required and the first
version of this line omitted it, failing with "staged content different from both the file and
the HEAD"; that was caught by running it, not by reading it. `--ignore-unmatch` makes it exit 0
when there is nothing to remove, so it is safe on every future merge.

**AND `git add -A` IS GONE FROM EVERY BLOCK, PERMANENTLY.** Rule A2 said so on 2026-09-11 and a
block shipped with it anyway on the same day. The standard merge block is now:

    cd ~/dev/relayshield
    git checkout main
    git --no-pager fetch origin claude/<branch>
    git rm -rf --cached -q --ignore-unmatch ansible-relayshield relayshield-snap
    git stash push --include-untracked -m "pre-merge untracked"
    git -c pull.rebase=false merge --no-edit FETCH_HEAD

**The permanent fix is his to choose and is one command:** move the two embedded repos out of
the clone, `mv ~/dev/relayshield/ansible-relayshield ~/dev/relayshield/relayshield-snap ~/dev/`.
A repository inside a repository will keep generating this class of problem no matter how many
lines the block carries -- the same reasoning that separated the clone from the documents
folder on 2026-09-05. Until he does, the `git rm --cached` line handles it.

**The general form, and it is the one worth carrying: when the same instruction fails three
times, the instruction is the loop.** I spent two turns hypothesising about `.gitignore` and
about gitlinks on `origin/main` -- both disproved by one `git ls-tree` -- when reproducing it
locally took four minutes and settled it completely. **A failure that reproduces is not a
mystery, it is a test case, and building the test case first is cheaper than the third guess.**

## STARS SELL WATCH SLOTS. NOT CHECKS, AND NOT ALERTS. DECIDED AND BUILT 2026-09-11.

**This SUPERSEDES the "charge for the alert, not the scan" conclusion in
`miniapp_stars_the_alert_not_the_scan.md`**, which was mine and was wrong, and the reason it was
wrong is worth more than the conclusion.

**Charging for the ALERT charges at the moment the user's money is already moving.** The free
tier's promise is "we will tell you if this changes"; attaching an invoice to that message makes
the promise bait. It is the same defect as a paywall on `/v1/link-check`, one step further down
the funnel and harder to see.

**A SLOT IS THE HONEST UNIT, because it is the one thing that actually costs us money.** Every
watched target is a TON Center call, a DexScreener call and a corpus query, on every cycle,
forever. That bill scales with slots and with nothing else. So:

  * **Checking: free, unlimited, unchanged.** `/v1/link-check` and `/v1/ton-address` are keyless
    and stay keyless. `test_checking_is_never_metered` fails if any of them appears in
    `relayshield_watchlist.py`, and it was proven by adding one.
  * **Watching: 3 slots free**, alerted fully and immediately, no delay and no degradation.
  * **Stars: 50 ⭐ raises it to 25 slots for 90 days.** A capability upgrade, never a tax.

This satisfies the standing principle exactly as written: **Stars pay vendor bills, they never
tax the free tier.** And it is self-limiting by construction -- it can only ever charge for the
thing with a marginal cost, so it cannot drift into taxing the thing the app is for.

**90 days rather than forever**, because Stars are a one-off purchase with no subscription
primitive, so an expiry has to live on our side or not exist at all, and a permanent
entitlement bought once outlives the feature.

### READING THE PAYMENT CODE BEFORE WIRING STARS FOUND TWO DEFECTS, ONE OF THEM A BILLING HOLE

Rule C says an instruction that writes to a live surface is preceded by the one that reads it.
Applied to code rather than to BotFather, it paid immediately.

**1. A 50-STAR PAYMENT WOULD HAVE BOUGHT A FULL SUBSCRIPTION.** `handle_successful_payment`
maps the payment amount to a plan with `tier_map.get(amount, TIER_PERSONAL)`. A Stars purchase
arrives as `total_amount=50`, matches no plan, and falls through to the **default**. The buyer
would have been given a paid subscription for about a dollar and then sent down the phone-number
onboarding for SIM-swap monitoring they never bought. **Currency is the discriminator, not the
amount:** `XTR` is Stars and every real plan is priced in fiat, so the XTR branch returns before
the tier map is ever consulted, and a test asserts that ORDER rather than merely the presence of
the branch.

**2. NO `pre_checkout_query` BRANCH EXISTED, SO NO TELEGRAM PAYMENT COULD EVER COMPLETE.**
Telegram sends a pre-checkout query and gives **ten seconds** to answer it. An unanswered query
fails the payment on the buyer's side and logs nothing on ours. The most expensive shape a
missing branch can take: every part of the purchase looks built, the invoice opens, and no money
can ever arrive. It approves unconditionally and **fulfils nothing** -- granting there would
hand out slots to anyone who opens an invoice and abandons it.

**The grant is idempotent on `telegram_payment_charge_id`.** Telegram retries a webhook it did
not get a 200 from, and a retry that extended the entitlement again is a free upgrade for anyone
who can make our handler time out once.

## PINNING A MINI APP: TELEGRAM HAS NO SUCH THING. YOU PIN A CHAT, AND WE HAD TO CREATE ONE.

**Asked four times across three turns and answered wrongly three times, because every answer was
about where to FIND the app.** That was not the question.

**The fact that settles it: Telegram has no primitive for pinning a Mini App.** What a user pins
is a CHAT. A Mini App opened from a direct link (`t.me/relayshield_bot/idcheck`) does not create
one -- the web view opens over the app and the bot never appears in the chat list. So a new user
who has never messaged `@relayshield_bot` has **nothing to long-press**, which is exactly what
Andrew kept reporting, on both laptop and phone, and it was correct every time.

**And pinning the BOT does not help**, which was his second question: the existing pinned chat is
the TI monitoring bot, and pinning it gives no route to the Mini App.

**THE FIX, AND IT IS IN OUR CONTROL RATHER THAN TELEGRAM'S.** A bot may message a user who has
opened it through a Mini App, and that message is what creates the chat entry. So **the first
watch now sends one**, and it says how to pin. Three things at once:

1. The chat exists, so it can be pinned, muted or archived -- all the things a user expects.
2. It **proves the alert channel before an alert is needed.** Finding out the bot was blocked at
   the moment something got drained is the worst possible time to find out.
3. It turns a Mini App user into a bot subscriber, which is the flywheel
   `relayshield_watchlist.py`'s own docstring has claimed since 2026-09-09 and did not do.

Only on the FIRST watch: a confirmation on every add is a notification tax on the feature's own
power users.

**The home-screen route (`addToHomeScreen`, Bot API 8.0) stays as it is** -- feature-detected,
Android-mostly, higher friction, and now the second option rather than the only one.

## THE WATCHLIST PROMISED ALERTS AND NOTHING SENT THEM, FOR TWO DAYS

Found 2026-09-11 while scoping the monitor, and it is the worst kind of gap because every part
of it looked finished.

`relayshield_watchlist.py` shipped on 2026-09-09. Its docstring says the chat_id is **encrypted
rather than hashed** specifically because "we cannot send an alert without the chat_id". The
table, the KMS grants, the initData verification and the CORS preflight were all built and all
correct. **There was no scheduled monitor, no notification code and no workflow.** Every user who
tapped "Tell me if this changes" was told something untrue.

`relayshield_watchlist_monitor.py` is the sender. **TON only, deliberately** -- Telegram Mini
Apps live inside Telegram's rules and TON is the chain Telegram ships, which is Andrew's
instruction and also the right call. Rows of other kinds are **counted and logged, never
deleted and never silently dropped**, and the Mini App labels them "not re-checked yet" in the
list: a watchlist that hides what it cannot re-check is indistinguishable from one that works.

**THE THREE RULES IN IT THAT MUST NOT BE RELAXED:**

1. **THE FIRST RUN AGAINST A ROW NEVER ALERTS.** Rows written before the monitor existed carry no
   snapshot, so every signal would read as "changed from nothing" and the first scheduled run
   would message every user about every target at once. That is how a security bot gets reported
   rather than uninstalled, and it is one `if` away. Proven by deleting the branch and watching
   the test fail.
2. **IMPROVEMENTS ARE RECORDED, NEVER SENT.** An alert is for action. "Good news" at 3am trains
   people to ignore the next one, and the next one is the one that mattered.
3. **"WE COULD NOT CHECK" MUST NEVER RENDER AS "IT IS GONE".** An upstream outage that reads as
   an emptied pool sends a false rug alert, which is the single mistake that would make this
   product actively harmful. Every unreadable number is `None`, never `0`, and a failed lookup
   leaves the stored snapshot untouched so the NEXT run diffs against the last real observation.

**It imports `handle_ton_address` from `relayshield_api.py` rather than calling the vendors
itself**, for two reasons and the second decided it. A fifth copy of the TON calls would drift
from the endpoint it is meant to be monitoring. And the alternative that looks cleaner is worse:
calling our own public `/v1/ton-address` over HTTP would work once per cap window, because the
**keyless per-IP cap would see every invocation arriving from one NAT address and throttle the
monitor against itself.** The dependency walk was run against the deployer's own `resolve_deps`
grep and packages five files -- checked, not assumed.

## A MEASUREMENT TOOL WRITTEN FROM WHAT THE CODE *SHOULD* LOG IS A FALSE ABSENCE

`tools/miniapp_funnel.py` answers the founder's high-priority question -- tg-miniapp arrivals,
bot signups, Stars, and traffic to the API landing site -- and **two of its seven filters were
wrong on the first draft, both in the direction that reports a live channel as dead.**

- It filtered the webhook log for `SRC_miniapp`. That is the **deep-link payload**; the webhook
  strips the prefix and lower-cases it before logging, so the line reads
  `acquisition source=miniapp` and the filter would have matched nothing, forever.
- **`/v1/ton-address` logged no source at all.** `/v1/link-check` has logged one since it was
  written, so half the Mini App's traffic was uncountable. Fixed in the same commit rather than
  noted: a key that is sent, accepted and never logged is the same false absence as a key that
  was never registered.

Both are pinned by tests that read the filter out of the tool and assert it against the line the
code actually writes, and both were proven by reintroducing them.

**The general form: a zero from a measurement tool GETS ACTED ON.** That makes a wrong filter
more expensive than no tool at all, and it is the `sorted()`-on-version-strings lesson in a new
place -- a number I print is evidence the reader will act on.

## TELEGRAM STARS IN THE MINI APP: NOT NOW, AND NEVER AS A CAP ON THE FREE CHECKS

Asked 2026-09-10: *"Its still not clear how we can use the stars or what value they bring."* Full
reasoning in `miniapp_stars_monetization.md`; the parts that must not be re-derived:

**BOTH PAYWALL CANDIDATES ARE ALREADY FREE, AND ONE COSTS US NOTHING.** `/v1/link-check`'s own entry
in `KEYLESS_SCAN_ENDPOINTS` says it: *"no paid upstream at all: DynamoDB, Safe Browsing's free tier
and RDAP. The per-IP cap is here to stop it becoming an open proxy, not to protect a vendor bill."*
And `/v1/ton-address` has been keyless since Crypto Shield Mobile, so charging for it would REMOVE a
free feature rather than add a paid one. TON *token* checks are the one real gap and they are a
BUILD, not a paywall -- only `/v1/ton-address` exists.

**THE VALUE IS A SIGNAL, NOT REVENUE, AND THE SIGNAL IS UNINTERPRETABLE TODAY.** Stars reach a buyer
the other three rails structurally cannot -- an anonymous Telegram user with no account, card or
wallet -- and a payment measures value where opens and returns measure interest. But the six
discovery routes have not run and `tools/source_arrivals.py` has never been run against the
`tg-miniapp` keys, so this would be optimising a funnel nobody has measured. **The gate is that
measurement, not a date.**

**THE CONSTRAINT WORTH KNOWING EVEN THOUGH WE ARE BUILDING NOTHING: Stars are the ONLY compliant way
to charge a consumer inside a Telegram Mini App.** Telegram requires digital goods sold in Mini Apps
to be paid in Stars, because that is how it satisfies Apple's and Google's IAP rules. **Wiring
"upgrade" from inside the Mini App to Stripe, x402 or the developers page for a digital good is the
route that gets a bot restricted** -- and it is exactly what a future session would do, reasonably,
because all three rails already exist one link away. UNVERIFIED from the container
(`core.telegram.org` is egress-blocked); the check is one tab,
<https://core.telegram.org/bots/payments-stars>, read BEFORE any payment code.

**IF IT IS EVER BUILT, ONE PRINCIPLE DECIDES THE SHAPE: Stars pay vendor bills, they never tax the
free tier.** Never a cap on `/v1/link-check` or `/v1/ton-address`. The honest candidate is
`/v1/scan-url` -- VirusTotal, a real per-call bill, already $0.05 on the PAYG rail. Self-limiting by
construction: it can only charge for things that cost money, so it cannot drift into taxing the thing
the app is for.

**The expensive prerequisite is already built**, which is worth knowing before anyone re-scopes this
as large: `relayshield_watchlist.py` verifies Telegram's `initData` HMAC and derives the user id as
`HMAC-SHA256(pepper, telegram_user_id)`. A verified non-spoofable per-user identity is the hard half
and it is live.

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

## AN ENDPOINT IS NOT SHIPPED UNTIL THE PREFLIGHT ANSWERS. curl CANNOT TELL YOU THIS.

**Found 2026-09-09 while wiring the Mini App watchlist, before it could cost anything, and it is a
new instance of the quiet-alarm shape rather than a new lesson.**

`relayshield_watchlist.py` returned no CORS headers at all. `relayshield_api.py` has carried
`Access-Control-Allow-Origin: *` for months, and the new file simply did not, because it was written
against the handler dispatch pattern and nobody looked at who calls it.

**The Mini App is served from its own hostname and posts `content-type: application/json`, which is
not a CORS-safelisted value.** So a browser sends an OPTIONS PREFLIGHT first and will not send the
POST at all unless it succeeds. Two consequences, and the second is the nasty one:

- A response without `Access-Control-Allow-Origin` is discarded by the browser AFTER it arrives. The
  Lambda logs a successful call and the user sees nothing.
- **A failed preflight means the real request is never sent, so there is no log line at all.** The
  symptom is a button that does nothing, and the server-side evidence is an empty log, which reads
  like the click never happened.

**And curl ignores CORS entirely**, so every terminal test passes on an endpoint that is dead in the
only client that uses it. That is the exact shape of the alarm that goes quiet rather than red.

So: `_CORS` on every response including the 400s and 404s, an OPTIONS branch answered BEFORE the
route lookup (a preflight carries no body and arrives at a path the browser has not been allowed to
POST to yet), `tools/create_watchlist_routes.sh` creates an OPTIONS method alongside every POST and
checks the preflight SEPARATELY and FIRST, and `test_miniapp.py` executes the dispatcher with boto3
stubbed rather than grepping it.

`*` rather than the Mini App's origin, deliberately: these endpoints authenticate on Telegram's
signed `initData` in the body, never on a cookie or an Origin header, so there is no ambient
authority for an origin allowlist to protect, and locking it down would break the widget for no gain.

**THE SECOND HALF, and it is the same mistake at a different layer.** The same script had to wait for
the Lambda to leave `Pending`:

    ResourceConflictException ... The function is currently in the following state: Pending

`create-function` RETURNS before the function can be invoked. That is the IAM propagation retry
already in that script, one operation later -- **an AWS call that succeeds, followed immediately by
one that assumes it finished.** Both failures were caused by doing the next thing at machine speed.
`aws lambda wait function-active-v2` is one line and the documented answer.

**The general form: after any AWS create, ask what the NEXT call assumes about it.** Creation
returning is not creation finishing, in IAM, in Lambda, in DynamoDB, or in API Gateway, where the
change is invisible until the stage is redeployed.

**AND THE CHECK I WROTE TO ENFORCE THE STATUS-CODE RULE BROKE THE STATUS-CODE RULE.** Its first real
run, the same day, printed exactly this and nothing else:

    -> 404, access-control-allow-origin: NONE
    STOP: the preflight did not succeed with an allow-origin header.

Correct verdict, unactionable output. **An API Gateway 404 and our own handler's 404 are different
problems with different fixes, and the BODY is the only thing that separates them** -- API Gateway
answers `{"message": ...}`, a shape our handler never produces, while our handler names the path it
was given, which is how a stage prefix leaking into `event.path` announces itself. The probe captured
the status code with `-o /dev/null` and threw the body away, so a stop that should have been
self-diagnosing cost a round trip instead.

So: **every probe in this repo prints the body of what it got, not a summary of it.** `curl -sS -i`,
and print it. `tools/diagnose_watchlist_routes.sh` is the read-only script that separates the four
causes in one run, including invoking the function DIRECTLY with the gateway taken out of the path,
which is the move that made `diagnose_agent_bait_routes.sh` pay for itself.

**The general form, and it is now three sessions old: a check that says a thing is wrong owes the
reader the evidence that says WHICH thing.** "It failed" is a round trip. "It failed and here is who
answered" is a fix.

### AND THE ANSWER WAS THE THIRD INSTANCE OF THE SAME RACE, IN THE SAME SCRIPT

The diagnostic settled it in one run, and the finding is worse than a bug.

Read the timestamps together. The Lambda's `LastModified` was **11:31:01 UTC**, so the CORS code was
live. The stage deployment `d41p0d` was created at **07:32:52 -04:00, which is 11:32:52 UTC**, and
the probe that 404'd ran seconds later inside the same script. An hour on, with nothing changed in
between, the identical request returned **204 with `access-control-allow-origin: *`** and the POST
returned `{"ok": false, "error": "unverified: open this inside Telegram"}` with CORS headers on it.
Steps 4 to 6 had already ruled out every other cause: six methods correct, six integrations pointing
at the right function, the stage serving the newest deployment, the function Active and answering a
synthetic OPTIONS with 204.

**`create-deployment` returns a deployment id before the edge serves the new resource set.** So this
is the same class as the two failures already fixed inside `create_watchlist_lambda.sh`, in the same
session, by the same person:

    create-role       -> "the role cannot be assumed by Lambda"
    create-function   -> "the function is in state: Pending"
    create-deployment -> a 404 at the edge for a few seconds

**AND THE REPO ALREADY KNEW.** `tools/create_mpp_settlement_lambda.sh` hit this exact race on
2026-09-05 and carries an inline retry with the diagnosis written above it, including the sentence
*"a propagation race that reports as a hard failure is worse than a slow script: it sends someone
diagnosing a routing bug that does not exist."* A script written four days later probed once,
because that knowledge lived in a neighbouring file's comments and nothing carried it across.

**A LESSON RECORDED IN ONE FILE IS NOT A LESSON THE NEXT FILE LEARNS.** That is the real finding, and
the fix is structural rather than another comment: `tools/lib_await_route.sh` holds `await_http`
once, and `create_watchlist_routes.sh`, `create_link_check_endpoint.sh` and
`create_agent_bait_scan_routes.sh` all source it. The last two had the same single-probe bug and had
simply been getting away with it.

**The half that keeps it from becoming a new problem: only 403, 404 and a failed connection are
waited on.** Those are what an undeployed route returns. Every other status is a real answer from a
component that is listening, so it returns immediately. A loop that waits out a 500 turns a clear
fault into a slow one, which is the "a probe that cannot tell must not block" rule pointed the other
way. Verified in this container against a live host: it succeeds on the first try, returns instantly
on a real non-matching answer, and retries only the 404.

**One place it deliberately is NOT used**, because the helper cannot tell: the second agent-bait
probe EXPECTS 403, which is also a propagation code. Ordering does that work instead -- the first
probe returning 402 proves the stage reached the edge, and the second request goes to the same stage
moments later.

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

## PUBLISHING TO DEV.TO. ONE COMMAND. DO NOT RE-DERIVE THIS.

**Written 2026-09-07 after ONE post took FOUR ROUNDS, every one of them my fault and none of them
about the writing.** Andrew's words: *"I'm frustrated and wasting way too much time."* He was right,
and the cost was not any single bug. It was that each round fixed one symptom and the next round
found the same cause somewhere else in the same file.

**THE PROCEDURE. Two commands, and nothing else.**

    python3 tools/publish_devto.py <file>.md --dry-run     # sends nothing
    python3 tools/publish_devto.py <file>.md --publish     # needs DEVTO_API_KEY

The key is read from the environment, never an argument, and is prompted with
`read -rs "DEVTO_API_KEY?..."` so it never echoes and never enters shell history. Get one at
<https://dev.to/settings/extensions>, under "DEV Community API Keys".

**NEVER PASTE FRONT MATTER INTO THEIR WEB EDITOR AGAIN.** Two attempts failed on 2026-09-07 and
neither produced an error: the front matter simply rendered as visible text. Retyping a structured
document into a web form is a step that fails silently, and the API is a step that fails with an
HTTP status and a message. The syndication file is generated and committed, and the script sends it.

**The keys are not the problem, and checking them again is a wasted round.** Verified 2026-09-07:
`title`, `published`, `description`, `tags` (four maximum, comma separated) and `canonical_url` are
all supported by the markdown editor. If a paste fails it is the paste, not the schema.

### THE ONE CAUSE BEHIND THREE OF THE FOUR ROUNDS: dev.to is behind Cloudflare

**Cloudflare 403s urllib's default `Python-urllib/3.x` user agent before the request reaches
anything.** That single fact produced, in order:

1. The canonical liveness probe reporting **403** on a page that a browser and `curl` both load at
   200, which blocked a finished post from publishing.
2. My first diagnosis of it, *"the Worker does not answer HEAD"*, which was wrong: a grep of
   `cloudflare_worker_blog.js` shows it does not branch on `request.method` at all.
3. `GET /api/articles/me/all` returning **403**, one function further on, **because I fixed the
   probe and did not generalise the fix.**

**So: every outbound request in `tools/publish_devto.py` sends a browser user agent, and any new
one must too.** A 403 from dev.to is Cloudflare rejecting the client far more often than the API
rejecting the key; a bad key gives 401.

**The general rule, which is now its own CLAUDE.md section:** a status code is a fact about the
REQUEST you made, not about the resource you asked about. And when a fix turns out to be about the
CLIENT rather than the endpoint, apply it to every call in the file in the same commit, because the
next call will have the same problem and finding that out is another round trip.

### THE DESIGN RULE THAT COST THE MOST: no probe may block the publish

Two checks in this script are probes rather than facts, and **both warn and continue** now:

- **Is the canonical live?** Only **404 and 410** block, because only those unambiguously mean "not
  published". 403, 405, 429, any 5xx and a refused connection mean *this probe could not tell*.
- **Does this post already exist?** If listing the account's articles fails, it posts anyway and
  says so. Worst case is a duplicate, which is visible on the dashboard and deletable. Blocking a
  finished post is worse than a duplicate.

Both behaviours are tested by triggering them, the second with the network faked so the POST is
observed to still happen.

### THE ORDERING RULE THAT IS REAL, AND IS THE ONLY HARD ONE

**The canonical must be live before dev.to publishes.** dev.to is a LIVE copy carrying
`canonical_url`, unlike Medium which takes a snapshot. A canonical that 404s tells every crawler our
canonical does not exist and hands dev.to the canonical position for our own post. Syndication files
therefore ship `published: false`, and `--publish` flips it.

That is the ONE thing worth stopping for. Everything else warns.

### HUGGING FACE IS NOT A SYNDICATION TARGET. IT TAKES AN ORIGINAL.

Verified 2026-09-08 from the community article editor: it has Owner, Slug,
thumbnail and Coauthors, and **no canonical URL field**. Every other channel in
the house order either sets a canonical properly (dev.to) or snapshots with one
(Medium). HF can do neither, so a full copy there is a duplicate competing with
our own canonical instead of pointing at it.

**So HF gets a shorter ORIGINAL piece written for its audience, linking the
canonical for the long version.** `blog-agent-bait-scan-hf.md` is the pattern.
Publish at <https://huggingface.co/new-blog>, owner `relayshieldadmin`; the title
is the first `#` heading in the body, so the file pastes as-is.

**AND THE CHECK THAT MATTERS BEFORE ANY HF POST: name only tools the Space
actually has.** On 2026-09-08 a draft claimed the agent-bait check was "already a
tool on the Space". It is not: `hf-space-mcp-server/app.py` declares thirteen
tools and no agent-bait scan. That is the `_APIFY_BANNER` mistake in a new place,
and it was caught only because the plan carried an explicit instruction to verify
it. huggingface.co is egress-blocked from the container, so the repo copy is the
best evidence available and the DRIFT RULE applies: it is not proof of what is
deployed. Grep `app.py` before naming a tool, and never upgrade "the repo has it"
into "the Space has it" without opening the Space.

### The file, and how to make the next one

`blog-agent-bait-scan-devto.md` is the pattern: DEV front matter, then a short runnable lead-in
because their readers want the thing before the thesis, then the canonical post body with the API
link switched to that channel's own `?source=` key. Generate it from `blog_markdown/`, never by
hand, and register the `?source=` key BEFORE it ships.

**Tags: four maximum and they must already exist on DEV.** `ai`, `security`, `devops`, `opensource`
are the safe set. `mcp` and `aiagents` are worth trying first for anything agent-shaped; a tag that
does not exist comes back as a 422 naming it.

---

## A STATUS CODE DESCRIBES YOUR REQUEST, NOT THE RESOURCE. AND A PROBE THAT CANNOT TELL MUST NOT BLOCK.

**Added 2026-09-07, after a check I wrote stopped a finished post from publishing over a page that
was perfectly fine, and after I then misdiagnosed it twice in a row.**

`tools/publish_devto.py` refused to publish because the canonical returned **403**. The canonical
loads in a browser and returned **200** to Andrew's own `curl` minutes earlier.

**First wrong diagnosis: "the Worker does not answer HEAD."** Plausible, since the probe used HEAD.
`cloudflare_worker_blog.js` does not branch on `request.method` anywhere, so it was wrong. **Second
wrong diagnosis avoided only by grepping the Worker before asserting it.** The likelier cause is
Cloudflare refusing urllib's default `Python-urllib/3.x` user agent, which curl and a browser do not
send.

**The lesson is the 402-price lesson in a new costume.** That one: two components can return the
same shape of success, so verify the field that differs. This one: **a status code is a fact about
the REQUEST you made, not about the resource you asked about.** A 403 answered "is a scripted
request from this client allowed", which nobody asked. Probe with the method, headers and user agent
a real reader would send, or accept that you have not asked the question you think you asked.

**And the half that actually cost the time, which is a design rule rather than a diagnosis.** The
check was a GATE, so an inconclusive probe became a hard stop between a finished post and its
publication. That is a worse failure than the thing it was guarding against.

**Only an unambiguous answer may block. Everything else warns and continues.** For "is this page
published", 404 and 410 are unambiguous. 403, 405, 429, every 5xx and a refused connection all mean
*this probe could not tell*, and a probe that cannot tell has no standing to stop the work. The
warning says so in those words and names the URL to open.

Applies to every guard in this repo, not just this one: **before writing a check that blocks, ask
what its inconclusive answer looks like, and make sure that answer does not read as failure.** A
check that cries wolf gets disabled, and then it is not a check at all.

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

## TWO THINGS RESCUED FROM THE SUPERSEDED 2026-09-05 LIST

Kept because regenerating a list deletes the reasoning inside it, and both of these are decisions
rather than status.

**A REGISTRY RECORD IS IMMUTABLE ONCE PUBLISHED, AND ITS VERSION IS NOT THE PACKAGE'S VERSION.**
That is what closed FD-8 after two failed attempts. A metadata fix needs a NEW VERSION STRING,
because the existing record cannot be edited. And the server entry's version is independent of
`packages[].version`: **0.2.12 pointing at package 0.2.11 is legal**, and is exactly what shipped,
with no PyPI release needed. Worth reading twice, because on 2026-09-07 I saw that same 0.2.12
against PyPI's 0.2.11 and called it a live breakage before checking the field that decides. The
record's own version and the version it PINS are different fields.

**`crewai-relayshield` IS FAIL-CLOSED, AND DECLARES NO HARD DEPENDENCY ON CREWAI. Do not
re-litigate either.** The gate core is pure stdlib and `install()` imports the framework lazily;
pinning crewai would make the package uninstallable next to a different crewai version for no gain.
Only `no_known_finding` proceeds, because a gate that lets a call through when the check times out
is a gate anyone can remove by causing a timeout. `fail_open=True` releases `DEFER` only, a check
that could not be COMPLETED, while a completed `REVIEW` still blocks and a `FINDING` always blocks.
There is deliberately no setting that lets a known-bad target through, and a test asserts it.

---

## WHERE 2026-09-05 LEFT THINGS — read this first

## READING THE LIVE BUNDLE D ENTITY ANSWERED THREE QUESTIONS AND FOUND TWO OF MY DEFECTS

**2026-09-09. The DescribeEntity capture is the most informative artefact this programme has
produced, and it was available the whole time.**

### 1. agent-bait-scan is NOT in Bundle D. Six dimensions, and none of them is it.

    agentic_bundle_access      Entitled            the monthly minimum
    bulk_identity_risk         ExternallyMetered
    tech_stack_cve             ExternallyMetered
    mcp_registry_risk          ExternallyMetered
    prompt_injection_breach    ExternallyMetered
    llm_credential_exposure    ExternallyMetered

`LastModifiedDate 2026-08-06`, `ProductState Active`, `Visibility Public`. So the listing is healthy
and the dimension is simply absent, exactly as `AWS_DIMENSION_NAMES` says it should be.

### 2. MY GUARD KNEW TWO OF THOSE SIX, AND THAT WAS THE DANGEROUS HALF

`tools/marketplace_add_dimension.py` refused any capture missing `mcp_registry_risk` or
`prompt_injection_breach`, because I took the list from `AWS_DIMENSION_NAMES`. **That table maps the
endpoints we METER through the Marketplace rail. It is not the listing's rate card.** Four
dimensions are on the product and not in that table, including the **Entitled** one that carries the
monthly commitment.

So a capture holding only those two would have PASSED, and a change set built from it could have
dropped four live dimensions and the monthly minimum with them. That is the 2026-07-27 "prices
rolled back to placeholders" failure, with a guard in front of it that was looking at the wrong
list. All six are named now, and a two-dimension capture is refused by test.

**The general form: a guard is only as good as where it got its expectations.** Deriving them from a
neighbouring table in our own code felt rigorous and was not; the authoritative list was one
DescribeEntity away.

### 3. THERE ARE TWO HF SPACES, AND THE WATCHER WAS WATCHING THE LESS IMPORTANT ONE

The listing carries `ApiType: MCP_SERVER` and this endpoint:

    https://relayshieldadmin-relayshield-agentic-attack-surface-aws.hf.space/gradio_api/mcp/sse

Note the `-aws` suffix. `hf-space-mcp-server/app.py` says outright that the same file is deployed
twice: the public Space, and a second one with `AWS_MARKETPLACE_MODE=true` that scrubs every
reference to the self-serve signup page, because **AWS's Tier-1 audit treats a reachable link to an
external payment page as a violation and that failed Bundle D's visibility request twice.**

**The AWS Space is a PUBLISHED product's declared endpoint.** If it stops answering, buyers who
arrived through AWS Marketplace hit a dead URL. That is worse than the public Space going quiet, and
until today nothing watched it: `tools/check_hf_space.py` named only the public one. It now checks
both, reports them separately, and the worst verdict decides the run.

### 4. TWO THINGS THE ENTITY SHOWS THAT ARE NOT MINE TO FIX SILENTLY

**The public listing quotes corpus figures this repo has since corrected.** Three times, in
ShortDescription, LongDescription and Highlights: *"5.0M+ indicators of compromise, 3,750+ malware
families, and 85+ monitored criminal Telegram marketplaces."* The corrected figures recorded on
2026-09-03 are 494K distinct indicators, 5.8M sightings and 95 channels. MEASUREMENT DOCTRINE says
the headline is not quoted at all, and this is a PUBLIC page a competitor can read. Changing listing
copy is a change set, so it batches with the dimension rather than being a separate submission.

**The delivery option targets ONE account.** The product's `Targeting.PositiveTargeting` lists eight
buyer accounts, but the DeliveryOption inside `version-baq5najnqgsam` lists only `239677749008`,
which is ours. Whether that restricts who can actually subscribe is a question for the Marketplace
console rather than something to assert from a JSON field, but it is worth asking, because a public
listing nobody outside our own account can take up would explain a lot.

---

## THE MINI APP MERGE DID NOT DEPLOY IT, AND A DEPLOYED WORKER IS NOT A MINI APP

Found 2026-09-09, asked as "I ran the merge that deployed the Tg miniApp. How do I access it on Tg?"
Two separate blockers, either one enough on its own, and neither is a defect in the code.

**1. The merge never reached GitHub.** `origin/main` is at `556b4f1` and carries neither
`cloudflare_worker_miniapp.js` nor `wrangler.miniapp.toml` nor `.github/workflows/deploy_miniapp.yml`.
That is the LOCAL MERGE IS NOT A PUSH rule, and **it has a second edge nobody had written down: a
workflow file that is not on the default branch cannot be dispatched from the Actions UI either.**
So the usual fallback -- Claude cannot dispatch, Andrew clicks *Run workflow* -- was not available.
There was no route to deploying this that did not start with pushing `main`.

**2. A Cloudflare Worker at `app.relayshield.net` is a web page. Telegram does not serve an arbitrary
URL as a Mini App.** It exists only after `/newapp` in @BotFather, which is what mints
`t.me/relayshield_bot/<short_name>` and gives `?startapp=` something to attach to. **That step is not
in the repo and could not be** -- it is a conversation with a bot, not a file -- and its absence from
the Mini App v1 work was a real gap. `miniapp_launch_checklist.md` now carries it, with the short
name pinned to `app` because `miniapp_discovery_and_stripe_choice.md` and item 1 already assume
`t.me/<bot>/app` in every planned link. **SUPERSEDED 2026-09-10: the registered short name is
`idcheck`, and every planned link now reads `t.me/relayshield_bot/idcheck?startapp=<source>`.**

**The likely third failure, flagged before it fires:** `wrangler.miniapp.toml` uses the zone-route
form, like blog/badge/partners/pricing/support. **A zone route attaches to a hostname, it does not
create one.** If `app` has no proxied DNS record in the zone, wrangler reports a successful deploy
and the hostname does not resolve -- the deploy-succeeded-and-nothing-works shape again.

**Do not submit to any announcement channel before opening it on a phone.** Item 1 is explicit:
each channel gives one first impression, `@trendingapps` is 3.9M of them, and a submission landing
while the link 404s spends it.

## THE PRE-COMMIT HOOK'S DISCOVERY VALUE HAS NEVER BEEN MEASURED, AND IT HAS BEEN MEASURABLE SINCE 2026-09-03

Asked 2026-09-09 as "is there a similar benefit to an IDE widget". The question rests on rsscan
having been a good discovery surface, and **nothing in this repo could say whether that is true.**
`rsscan` and `rsscan-deps` are registered `_SOURCE_BANNERS` keys, so every arrival has been
attributed and logged in CloudWatch the whole time. Nobody counted them. FD-1 says **DONE**, and
"done" is a fact about shipping, not about reach.

`tools/source_arrivals.py` closes it, and it runs on the Mac:

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/source_arrivals.py --days 90 --key rsscan

It reports the window it OBSERVED rather than the one asked for, prints `unmatched:` rows first
because each is a live link naming a key that does not exist, and separates ZERO ARRIVALS from
UNREGISTERED, which are different findings with different fixes.

**IT ALSO CAUGHT ITSELF, which is the part worth carrying.** The first `registered_keys()` walked
only `ast.Assign`, so it read `_SOURCE_ALIASES` and silently skipped `_SOURCE_BANNERS` -- declared as
`_SOURCE_BANNERS: dict[...] = {`, an `ast.AnnAssign`. It returned 117 keys, which looks exactly like
a working parse, with every real banner missing. The tool would have reported `rsscan`, `tg-widget`
and `tg-miniapp` as UNREGISTERED when all three are registered, and an unregistered key is a
completely different conclusion from a channel that produced nothing. Nothing errored. Found by
running it and grepping the handler to check -- rule 14 applied to my own tool rather than to a
command. It now asserts a floor: an empty table raises rather than reporting a false absence, and
`test_source_arrivals.py` pins it against an independent parse.

**The answer to the widget question is in `ide_widget_scope.md`**, and the short form is: three of
the four named categories are not ours (no SAST anywhere in this codebase, and "malware detection"
overstates an indicator match), one is completely ours and has no IDE incumbent, and **rsscan is the
wrong host for it because the direction is opposite** -- rsscan reads `git diff --cached`, your own
authored change, while agent-baiting is about files somebody else wrote that your agent is about to
read. Measure first, read the VS Code Marketplace rules second, build one narrow thing third.

## A DEPLOY PATH IS NOT DRIFT DETECTION, AND relayshield-oauth-watchlist-monitor HAD ONLY THE FIRST

Asked 2026-09-09 as "we also need to map the rs-watchlist.py in the deployer". **It is already
mapped**, and has been: `deploy_lambdas.yml` carries it in the `paths:` trigger, the manual-dispatch
list and `LAMBDA_MAP`, and `iam_github_deploy_invoke.json` carries its ARN. Nothing to do there.

**What it did not have was a drift check**, and that is the gap that was real. The telegram, whatsapp
and discord handlers are all mapped in the deployer AND watched in `lambda_drift_check.yml`,
deliberately, because "having a deploy path is not the same as never being hand-deployed again". The
watchlist monitor was in the deployer only, so the question "has anyone hand-deployed over it" had
never been asked of it. It is now watched.

**`relayshield_mpp_settlement.py` was added to the drift check at the same time, and deliberately NOT
to the deployer.** `tools/check_deploy_invoke_policy.py` prints "granted but not in LAMBDA_MAP" for
it on every run and Top-15 item 4 is to close that -- but nothing has ever compared its live package
against main, so mapping it now would be mapping a function whose drift is unmeasured. Watch, read
the first diff, then map. A clean diff makes item 4 one line; a dirty one makes it a recovery, and
learning that from a red check costs nothing while learning it from a deploy costs the live code.

## SMITHERY NOW POINTS AT THE HOSTED HF SPACE. CHANGED 2026-09-09, AND THE CLI SCHEMA IS NOT WHAT WE THOUGHT.

**This SUPERSEDES the section immediately below it, which is kept because its finding was correct on
the morning it was written and its process note is the reason this one exists.**

Two things changed, and the second was a surprise that would have cost a round if it had been
guessed at instead of read.

**1. The file points at the hosted Space, because that is the listing we actually want.**
`mcp_registry/smithery.yaml` now carries `target: remote` and

    https://relayshieldadmin-relayshield-agentic-attack-surface.hf.space/gradio_api/mcp/sse

the SAME URL the AWS Marketplace entity registers as Bundle D's `EndpointUrl`. The PUBLIC Space, not
the `-aws` one: they run the same code, but `AWS_MARKETPLACE_MODE=true` scrubs every reference to the
self-serve signup page for AWS's Tier-1 audit, and a Smithery visitor is not an AWS buyer and should
be able to find the way to buy. That is FD-15 answered: one hosted URL, everywhere.

**2. THE MODERN SMITHERY CLI READS EXACTLY TWO KEYS OUT OF THAT FILE.** Read from `@smithery/cli`
4.11.1 on the npm registry, not from a docs page -- smithery.ai is egress-blocked from the container
and npm is not, which is the BLOCKED SOURCE WAS REACHABLE ALL ALONG rule paying for itself a second
time. Its parser is literally:

    z.object({ name: z.string().optional(),
               target: z.enum(["local","remote"]).optional() }).loose()

`.loose()` keeps unknown keys, which is why the rest of that file is harmless documentation. **The
elaborate `startCommand` / `configSchema` / `commandFunction` block that two previous sessions argued
about, corrected, and argued about again is the LEGACY v1 schema** from when Smithery scanned a
GitHub repo and built the server itself. It is not read by the CLI that publishes today. We spent
three sessions perfecting a file the tool mostly ignores.

**And publishing a hosted server is ONE command, from the CLI's own README:**

    smithery auth login
    smithery mcp publish <url> -n <org/server>

The login is not optional and is not "you logged in earlier" -- that is the `mcp-publisher` 401 that
cost a round, and the rule is that a block driving an authenticated CLI carries its auth step every
time.

**FD-11 IS THEREFORE NOT BLOCKED AND NEVER NEEDED A BUILD.** It is one command against a URL that
already answers.

**THE URL IS WATCHED, AND THE WATCH WAS LOOKING AT THE WRONG THING UNTIL TODAY.**
`tools/check_hf_space.py` checked the Space's HTTP front door and the HF API's runtime stage. Neither
says anything about whether the MCP server is MOUNTED. `app.py` passes `mcp_server=True` to
`demo.launch()`, and its own comments record a previous Gradio upgrade changing how that route is
served -- so dropping that argument, or upgrading past a rename, would have left the watcher green
forever while every directory we are listed in resolved to a 404. It now probes
`/gradio_api/mcp/sse` itself on both Spaces, treats 404/405/410 there as DOWN, and reports
`/gradio_api/mcp/` (streamable HTTP) as information so "the route moved" and "the server is down"
are one line apart instead of an afternoon apart. `test_hosted_mcp_pointer.py` pins the URL in
`smithery.yaml` against the one the watcher probes, because advertising a URL that nothing watches is
the quiet alarm with an audience, and advertising one the watcher does NOT probe is worse: the alarm
is green and pointed at the wrong target.

---

## SMITHERY POINTS AT THE PyPI STDIO SERVER. SETTLED 2026-09-09, IT IS NOT THE HF SPACE.

Andrew asked me to double-check the recollection that Smithery had been pointed at the HF MCP
server. It has not, and the check is now on record from the copy that actually matters.

**`~/mcp-live/smithery.yaml`, grepped on the Mac**, which is the file Smithery reads:

    27:  type: stdio
    44:  commandFunction: |
    46:      command: 'uvx',

No `url`, no `hf.space`, nothing hosted. It is the stdio PyPI package, identical to the copy in
`mcp_registry/`. So both copies agree and neither points at HF. The 2026-09-05 change corrected this
file to describe the RIGHT server (PyPI, sixteen real tool names) after a previous version described
a Node server that does not exist; it never pointed it at the Space.

**Why this matters rather than being a filing detail.** stdio and hosted-HTTP are two different
listings with two different visitors. A stdio entry tells someone to install a Python package; a
hosted entry hands them a URL. FD-15 exists because Grok Bot connectors, Smithery and possibly
OpenAI all want the SAME hosted URL, and we have two candidates already serving MCP over HTTP (the
HF Space and the Apify Actor) with no decision recorded about which one a stranger gets.

**So FD-11 is not blocked and never was: the stdio listing can ship today.** What is undecided is
whether we ALSO want a hosted entry, and that is FD-15's question, not this file's.

**The process note worth keeping.** The right answer here came from one grep on the machine that
holds the file, after this container could only report what `origin/main` said. That is the
"IT IS NOT IN THE REPO IS A CLAIM ABOUT ORIGIN" rule working in the direction it was written for:
report what you checked, name the one command that settles the rest, and let it be run.

---

### WHAT 2026-09-09 SHIPPED, so the next session does not re-derive it

**All of it is on `claude/top-15-todos-summary-cgjupn` and pushed.** The lessons are written up in
their own sections above; this is only the state.

- **The Mini App watchlist is LIVE end to end.** `relayshield-watchlist` exists, is Active, and all
  three `/v1/watchlist/*` routes answer with CORS. Proven by the refusal an unsigned request gets:
  `{"ok": false, "error": "unverified: open this inside Telegram"}` with
  `access-control-allow-origin: *` on it. Three defects were fixed getting there and every one is
  written up above: no CORS at all, `create-function` returning before Active, and
  `create-deployment` returning before the edge serves the route.
- **`tools/lib_await_route.sh`** is the shared propagation wait, sourced by three route scripts.
- **`tools/diagnose_watchlist_routes.sh`** is read-only and separates four causes in one run.
- **Smithery now points at the hosted public Space** and `test_hosted_mcp_pointer.py` pins that URL
  against the one `check_hf_space.py` probes.
- **The HF watcher probes the MCP endpoint itself**, on BOTH Spaces, not just the front door.
- **The Bundle D change set is built and unsubmitted**: dimension AND listing copy in ONE change
  set, guarded against the stale corpus figures.

**Tests: `test_miniapp.py` 39, `test_hosted_mcp_pointer.py` 8, `test_workflows_parse.py` 16
workflows, all green. `test_agent_bait_scan.py`, `test_agent_bait_skill.py`,
`test_relayshield_widget.py`, `test_mpp_settlement.py`, `test_developer_signup_banners.py` all OK.**

### THE TOP 15, REGENERATED 2026-09-09

**Regenerated, not annotated.** Item 1 of the 2026-09-08 list (build the Mini App) is BUILT, and
items 2 and 3 (FD-15, the HF watcher) are closed, so the top of the list has moved.

**Closed since 2026-09-08:** FD-15 is decided and implemented (one hosted URL, watched). The HF
Space watcher is built and now checks the MCP endpoint rather than the front door. The Mini App and
its watchlist are built and live. The Bundle D tooling is finished and its guard defect is fixed.

---

1. **Map `relayshield_watchlist.py` in the deployer. THIS IS NOW UNBLOCKED AND IT IS THE TOP ITEM.**
   The function exists in AWS, the routes are wired, and it is in NEITHER `deploy_lambdas.yml`,
   `lambda_drift_check.yml` NOR `iam_github_deploy_invoke.json`. That is the exact combination --
   source in the repo, live traffic, no deploy path -- that this repo has now been bitten by SIX
   times, most expensively by `relayshield_developer_signup.py`, which grew a 700-line billing path
   nobody could see. **Do it before the file accumulates a single hand-deployed edit.**
   Three edits, in this order and no other:
   (a) `iam_github_deploy_invoke.json` FIRST, then `sh tools/apply_deploy_invoke_policy.sh`, or the
       first CI deploy repeats run 134's denied import probe;
   (b) the `paths:` trigger and `LAMBDA_MAP` in `deploy_lambdas.yml`, plus the drift check;
   (c) `python3 test_workflows_parse.py`.
   **The mapping commit MUST touch `relayshield_watchlist.py` itself** -- the deployer ships a
   function only when the push changed its source, so a commit touching only workflow files deploys
   nothing and the map looks applied while nothing has moved.

2. **FD-11: Smithery. Two commands, ten minutes, the cheapest open item on this list.**

       npx -y @smithery/cli@latest auth login
       npx -y @smithery/cli@latest mcp publish https://relayshieldadmin-relayshield-agentic-attack-surface.hf.space/gradio_api/mcp/sse -n relayshield/relayshield

   UNVERIFIED from the container: there is no Smithery credential here. Node 20+. If the namespace
   does not exist, run `namespace list` rather than guessing a name.

3. **Bundle D: submit the change set.** `ANDREW CLICKS`: Actions, Marketplace Dimension,
   mode `plan` first and READ the four `was:`/`now:` blocks, then mode `apply` with
   `confirm_entity: prod-kkvurtspreofy` and `include_listing_copy: true`. It carries the
   `agent_bait_scan` dimension AND the copy in one change set, which is one AWS review cycle.
   **Carry this with it:** `AWS_DIMENSION_NAMES` in `relayshield_agentic_api.py` still says
   agent-bait is held back pending a measured false-positive rate, which will contradict the live
   listing the moment this lands. One-line comment fix, same session as the submission.

4. **Run the six Mini App discovery routes, now that v1 exists.** The sequencing risk is spent
   otherwise: each announcement channel gives ONE first impression. The ranking, from
   `miniapp_discovery_and_stripe_choice.md` §2 and NOT to be re-litigated:
   (1) the Telegram blog channel, the only surface whose audience chose us;
   (2) Mini App announcement channels -- `@trendingapps` 3.9M, `@web3telegrambotx` 72,742,
       `@findminiapp` 56,380, `@onclicka_tma_en` 33,723, `@telegtapps` 9,671;
   (3) Mini App directories, tApps Center and family;
   (4) attributed deep links `t.me/relayshield_bot/idcheck?startapp=<source>`, keys registered FIRST;
   (5) the bot's menu button, cheap rather than high-reach;
   (6) TON catalogues, only if TON scans ship.

5. **Watch the first few HF watcher runs.** `.github/workflows/hf_space_watch.yml` runs every six
   hours and now probes `/gradio_api/mcp/sse` on both Spaces. A DOWN opens an issue; UNREACHABLE
   reddens the run without one. **The first runs are the ones that tell us whether the MCP probe is
   calibrated** -- if a sleeping Space reports UNCLEAR every time, the wake ordering needs work.

6. **Map `relayshield-mpp-settlement` in `deploy_lambdas.yml`.** Still in neither the `paths:`
   trigger nor `LAMBDA_MAP`; `tools/check_deploy_invoke_policy.py` prints it as
   "granted but not in LAMBDA_MAP" on every run of `test_workflows_parse.py`. Same rule as item 1:
   the commit must touch the `.py`.

7. **MPP settlement selftest, reads-only.**
   `AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/mpp_settlement_selftest.py --reads-only`.
   Answers whether the account has crypto deposit addresses and a business profile. A 403 is the
   text to send `machine-payments@stripe.com`.

8. **FD-14: read OpenAI's plugin directory rules. Reading IS the task.** Largest audience of the
   three directories. **Do not scope the work before reading the rules** -- FD-2 cost a day on a
   destination whose own page said the PR would be closed unread. Three questions decide it: is a
   plain MCP server submittable or must it carry Apps SDK components, what is the stated bar, and is
   a paid pay-per-call tool eligible at all. The hosted URL FD-15 settled is ready if it needs one.

9. **Rewrite the MCP registry listing copy to lead with counterparty authorization.** The record
   still describes the server as a list of tools. Needs an `mcp-publisher` run, so batch it with
   anything else the record needs rather than spending a version on copy alone.

10. **Apify: the form is OPEN NOW, not November.** Saurav Jain in `#apify-writers`, 2026-09-07.
    Andrew has DM'd his username and asked for the form link. **The disqualifier is unchanged: the
    article must NOT appear on blog.relayshield.net first.** Submitting is not publishing.

11. **The Commerce Agents blog post.** `commerce_agents_integration.md` has the argument, resting on
    a primary source Anthropic published saying authorization is the deployment's problem.
    **Register `?source=commerce-agents` BEFORE it ships.** No PR to that repo; its README says it
    accepts nothing.

12. **ABS-1: the measured false-positive rate.** `tools/agent_bait_fp_rate.py --pull` runs inside
    the Marketplace workflow so the numbers and the change set come from the same run. This is the
    gate item 3's code comment names, and the agent-bait post is the thing most likely to produce
    the traffic that makes the measurement possible.

13. **Extend the Rain demo to the merchant-agent shape.** `tools/rain_demo.py` does the hard part.
    Audience order unchanged: Routavo, Rain, Stripe, Coinbase CDP, Aduna. Not Anthropic.

14. **Send the twelve** (`outreach_bot_prospects_curated.md`). Five real inboxes first, then the
    seven websites. Track replies per 100 by channel.

15. **INTEL-5.** `AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/diagnose_stolen_sessions.py`.
    Until it runs, no count out of `relayshield_stolen_sessions` means anything about the criminal
    market, and the OpenRouter revocation webhook stays gated on it.

### THE PUBLISHED MCP PACKAGE IS BROKEN FOR EVERY NEW INSTALL. FOUND 2026-09-05.

**This is the most serious finding of the day and it was not on any list.** It came out of a
question about bundling the MCP server into the Claude Code plugin, which is the only reason anyone
looked.

`relayshield-mcp` declares its dependency as **`mcp>=1.0.0`, with no upper bound**, on 0.2.9 AND on
the 0.2.7 that the official registry still pins. A resolver picks the newest thing allowed, so a
fresh `pip install relayshield-mcp` today installs **mcp 2.1.1** and the server dies at import:

    AttributeError: 'Server' object has no attribute 'list_tools'

Reproduced end to end in a clean venv, not inferred from the metadata. **The wheel is fine. The
dependency range is not.**

**Why nothing caught it, and this is the part worth carrying.** Every check in this repo tests the
code we WROTE. Nothing tested the thing users INSTALL, and on this date those were different. A
developer's venv already holds a working `mcp` pinned months ago, so it passes forever; the resolver
would never choose that version for a new user. **The failure also needs no change on our side at
all** -- somebody else published a major version and our shipped package broke, silently, for new
installs only. That is the quiet-alarm rule applied to packaging.

`python3 tools/mcp_selftest.py --pypi` now builds a throwaway venv, installs the published package
the way a new user would, prints what the resolver actually chose, and handshakes it. Exit 1 on
DEAD. It reproduces this in about a minute.

**RESOLVED 2026-09-05. `relayshield-mcp` 0.2.11 is on PyPI and the check is green:**
`resolved: mcp 1.29.1, relayshield-mcp 0.2.11 -- ACTIVE, 16 tools`. The source in `~/mcp-live`
already carried `mcp>=1.0.0,<2.0.0`; it had simply never been released, so this was always "ship
the fix that exists" rather than "fix the pin".

**TWO WAYS THE VERIFICATION LOOKED LIKE A FAILURE WHEN IT WAS NOT, and both were mine.**

First, the check run minutes after the upload resolved **0.2.9**, because a just-published version
takes time to reach the index pip reads. Identical output to a genuinely broken release. The
checker now compares what the resolver took against PyPI's latest and says outright when they
differ, so "the new release is broken" and "the index has not served it yet" stop looking the same.

Second, and worse because it was a throwaway diagnostic presented as evidence: a one-off command
printed `all versions` using `sorted(releases)[-6:]`, and **`sorted()` on version STRINGS puts
"0.2.11" before "0.2.4"**, so the slice cut off the very version being checked. It read as "0.2.11
is not on PyPI" when 0.2.11 was there the whole time. Andrew stopped the session over it, correctly.

The lesson is rule 14 applied to my own output, not just to commands: **a number I print is evidence
the reader will act on, so a sloppy one-liner is as expensive as a wrong command.** Version strings
are never sorted lexically; compare them as tuples or do not print an ordering at all.

**Do not bundle the MCP server into the Claude Code plugin until this ships.** A plugin that
installs a server which dies at import would fail on first use for everyone, and it would fail that
way inside a submission to Anthropic's directory.

### "THE DEPLOY SUCCEEDED" IS NOT "THE ITEM IS CLOSED"

Recorded 2026-09-05 because it nearly cost the item. A status line reading *"Item 2: still open, and
confirmed from run 137's log — relayshield-agentic-api WAS DEPLOYED, only the probe was denied"* was
read as evidence the item could be closed.

It is the opposite, and the sentence contains both halves. "The deploy succeeded" is the reason the
failure is survivable; **"only the probe was denied" is the open item**, because the policy that
would authorise the probe has still never been pushed to AWS. Nothing about run 137 changed that,
and nothing will until `apply_deploy_invoke_policy.sh` runs.

The general form, and it is the counterpart to "a red run names a step, not an outcome": **reading a
red run correctly tells you what did NOT break. It does not close anything.** The diagnosis and the
fix are separate events, and only the second one is a state change.

### A SKILL IN OUR OWN REPO REACHES NOBODY

The honest answer to "this increases our discovery surface, right?", recorded because the optimistic
version is very easy to write.

**Building it does not increase discovery. Distributing it does.** A skill at
`.claude/skills/` in this repo is available to people who have cloned this repo, which is us. The
artefact is real and it is a prerequisite; it is not the channel.

What makes it a discovery surface is that it puts the check **at the moment of the decision** -- a
developer in Claude Code about to add an MCP server -- which is a far better moment than a blog post
read later by someone with no pending decision. That is why item 11 ranked above two posts. But the
moment is only reachable if the skill is somewhere they can install it from.

**Do not write submission instructions for any route before reading its rules.** That is the FD-2
lesson (a PR that would have been closed without comment, against a page whose own last section said
so) and the CrewAI lesson (PR #6550, opened against a live repo and still unreviewed months later:
open is not the same as responsive). Both cost real effort against destinations that never took it.

**CORRECTION, 2026-09-05.** An earlier draft of this line described CrewAI as "a repo whose README
says it is unmaintained and accepts nothing". That is `anthropics/commerce-agents`, not CrewAI, and
the two were conflated in a single sentence. **CrewAI is actively maintained** -- `crewai` 1.15.20
was published to PyPI on 2026-09-04, the day before this was written. The lesson from #6550 is about
an unreviewed PR, not a dead framework, and the difference decides whether item 7 is worth doing.

### A PLUGIN'S MCP SERVER GOES IN `.mcp.json`, NOT IN `plugin.json`

Measured 2026-09-05, and found only because the install was VERIFIED rather than
declared done.

An `mcpServers` block written into `plugins/relayshield/.claude-plugin/plugin.json`
is **silently ignored**. The plugin installs, `claude plugin validate` passes, and
`claude plugin details` reports:

    MCP servers (0)

Moving the identical block into `plugins/relayshield/.mcp.json` at the plugin
root registered it immediately:

    MCP servers (1)  relayshield

Nothing errors in the wrong configuration. A validator that passes and a field
that does nothing look exactly like a working plugin, which is the quiet-alarm
shape again -- and the first version of the test asserted the ignored key, so it
went green while the plugin shipped no server at all. **A test that reads the
same wrong file as the code proves nothing.** `test_agent_bait_skill.py` now
reads `.mcp.json` AND fails if `mcpServers` reappears in `plugin.json`.

The general form, for the third time this session: `claude plugin details` is the
check, not `claude plugin validate`. Validation says the file is well formed;
details says what the plugin actually contributes.

### THE FLOOR ON `relayshield-mcp` IS A SAFETY PROPERTY

`.mcp.json` pins `relayshield-mcp>=0.2.10`, and that is not tidiness. 0.2.9 and
earlier declare `mcp>=1.0.0` unbounded, resolve mcp 2.x, and die at import. The
floor makes it impossible for the plugin to install a version that cannot start.

Verified today that it fails CLOSED: `pip install 'relayshield-mcp>=0.2.10'`
returns `No matching distribution found`, because 0.2.10 is not published yet. A
loud failure at install time is much better than the alternative, which is a
server that installs, starts, dies, and presents to the user as "disconnected"
with a configuration that looks perfectly correct.

**So the plugin is complete and the MCP half is inert until the release ships.**
That is deliberate and it is the right way round.

### A LOCAL MERGE IS NOT A PUSH, AND `owner/repo` READS THE DEFAULT BRANCH

Found 2026-09-05 when `claude plugin marketplace add nzdsf2-gif/relayshield` failed with

    Marketplace file not found at
    ~/.claude/plugins/marketplaces/nzdsf2-gif-relayshield/.claude-plugin/marketplace.json

Nothing was wrong with the manifest. **`.claude-plugin/` was on the feature branch and not on
`origin/main`**, and the `owner/repo` source form clones GitHub's DEFAULT BRANCH. Confirmed with
`git ls-tree origin/main --name-only | grep claude-plugin`, which returned nothing.

This is the DRIFT RULE's mirror image and it is worth stating in both directions:

- A push from the container puts a file on GitHub and **not** on Andrew's Mac. That is why every
  command block starts with the merge.
- A merge on Andrew's Mac puts a file in his clone and **not** on GitHub. That is why anything
  fetched by `owner/repo` -- a plugin marketplace, a raw.githubusercontent URL, a CI checkout --
  keeps failing until `main` is actually pushed.

**Two routes, and the local one needs no push:**

    claude plugin marketplace add ~/dev/relayshield        # works right after the merge
    claude plugin install relayshield@relayshield

Verified end to end. Note `claude plugin marketplace add .` is REJECTED as an invalid source
format; use an absolute path or `./` with the trailing slash. The `nzdsf2-gif/relayshield` form
starts working the moment `main` carries `.claude-plugin/marketplace.json` on GitHub, and that is
the form to put in any published copy, because a reader has no local clone.

### THE ROUTE WAS CHECKED, 2026-09-05, AND IT IS OPEN

Unlike FD-2 and CrewAI. Read from the destination's own files rather than assumed:

**`anthropics/claude-plugins-official` accepts third-party submissions.** Its README says so in
those words -- *"Third-party partners can submit plugins for inclusion in the marketplace"* -- and
names a formal route, the plugin directory submission form at
<https://clau.de/plugin-directory-submission>. The bar it states is *"External plugins must meet
quality and security standards for approval"*, and it does not enumerate them. So this is a real
door, and the first one in this programme that did not turn out to be shut.

**The unit of distribution is a PLUGIN, not a skill**, which is why the skill alone was never
installable by anyone. A plugin is `.claude-plugin/plugin.json` plus a `skills/` directory; a
marketplace is `.claude-plugin/marketplace.json` at a repo root listing plugins by source. Both now
exist here, so this repo IS a marketplace and the skill is installable today:

    /plugin marketplace add nzdsf2-gif/relayshield
    /plugin install relayshield@relayshield

That is the prerequisite for the directory submission, not a substitute for it. **Our own
marketplace reaches people we tell; the directory is the part that reaches people we do not.**

`test_agent_bait_skill.py` pins both manifests, that they agree on the plugin name, that the source
path resolves, and that the declared `skills/` reaches the SKILL.md. Two files that must agree with
nothing checking that they do is the shape that produced run 134's red probe.

**The skill lives at `plugins/relayshield/skills/` and `.claude/skills/` is a SYMLINK to it.** One
file, two places it has to appear. A copy would drift, and this repo already carries four copies of
one pattern table.

### ITEM 10, APIFY SUBMISSION: the mechanics, so it is actionable

Recorded 2026-09-05 because "submit to Discord" left every real question unanswered, and an
instruction nobody can act on is how this item fell off the list in the first place.

**Where, corrected TWICE on 2026-09-05, and the second correction came from the channel itself.**

The programme page says to join the Discord, go to `#apify-writers`, check the quarterly theme, read
the guide and fill out the form. Andrew then looked at the actual channel and there was **no theme,
no guide and no form** -- because those only exist while a call is OPEN. A writer in the channel
that day stated it plainly: *"the July Typeform is closed and the next call opens in November."*

So the submission mechanism is a **Typeform that appears per call**, and today there is nothing to
fill in. **The next call is NOVEMBER.** That is the date this item waits on, and reading the
programme page alone would have had us hunting a form that does not currently exist.

**Posting in the channel while the call is closed is fine and is what other people do.** An observed
example from 2026-09-04: a developer introduced their Actor, described their finished Theme 2
article, noted the Typeform was closed, asked how to get dev.to publishing access, and linked the
draft. Nobody was penalised for it. So a pre-call introduction is available to us now if we want the
contact, and it is not a submission.

**The lesson, which is the FD-2 lesson with the label already read:** the programme page describes
the process in the abstract; the channel shows its current state. Both were needed, and only the
second one carried the date.

**SUBMITTING EARLY DOES NOT COST THE $500. PUBLISHING EARLY DOES.** Asked directly on 2026-09-05,
and the distinction is the whole risk. The rule is *"only original, previously unpublished
content"* -- it is about PRIOR PUBLICATION, and a submission is not a publication. So sending the
draft into `#apify-writers` or the form is the intended action and carries no downside. Putting the
same article on `blog.relayshield.net`, Medium or dev.to before Apify publishes it is what
disqualifies it. Their guidelines do not address republishing AFTER they publish, and the
programme's own $100 dev.to bonus is a post-publication republish under their organisation, so the
canonical-first channel order resumes once the article is live on their blog.

**Cadence, and it decides the date.** The programme is QUARTERLY. The July call closed 2026-08-16
and the next opens in NOVEMBER, per the channel. Use the wait for the three verifications below
rather than treating the wait as the blocker.

**The three facts to confirm with the Apify console open**, because the draft asserts them and no
session has verified them directly:

1. **The 154 runs figure**, and whether to quote it at all. It is small enough that a reviewer may
   read it as a toy. Consider dropping the number and keeping "in production since August".
2. **The exact Standby configuration** (memory, timeout), if we want to quote it. The draft
   deliberately does not.
3. **The dependency versions as they stand today.** The draft says `apify>=2,<3` crash-looped and
   `apify>=4,<5` fixed it, taken from a Dockerfile comment dated 2026-08-25. If the pin has moved,
   the article moves with it.

**What is actually at stake:** $500 on publication, plus $100 in Apify credits for a dev.to version
under their organisation. The money is not the point. It is a technical article on a platform
developers read, about a category we sell into, written from work we actually did, and both the
Actor and the API get a link carrying `?source=apify`, which is already a registered key.


### THE MOVE BROKE SOMETHING THE REPO COULD NOT SEE, AND THE LOG HAD BEEN SAYING SO FOR HOURS

The most instructive failure of the session, because the fix that was supposed to prevent it was
already in place and could never have worked.

Moving the clone to `~/dev/relayshield` was made safe INSIDE the repo by deriving paths from
`Path(__file__).resolve().parent`. It killed the RelayShield MCP server anyway, in both Claude
Desktop and Claude Code, because both configs launch it by absolute path into `~/Side SaaS Hustle`.
Those files live in `~/Library/Application Support` and `~/.claude.json` — **directories the repo
does not own and cannot enumerate**, so no amount of discipline inside the repo reaches them.

Two things made it invisible for hours:

- **The client says "disconnected", which describes the symptom and not the cause.** The actual
  cause was in the log, repeating every few minutes since 04:24 UTC: `can't open file
  '.../Side SaaS Hustle/relayshield_mcp_server.py': [Errno 2] No such file or directory`.
- **Nobody was reading the log**, because the config is the thing you look at when a server will not
  start, and the config looked fine. It WAS fine, for a machine layout that no longer existed.

`tools/mcp_inventory.sh` reads every client config path AND the client's own logs, redacting every
credential-looking value first. `tools/fix_mcp_config_paths.py` repoints them, rewriting dict KEYS as
well as strings because Claude Code files its MCP servers under the project's absolute path.

**The general form, and it is the second half of the move checklist: an absolute path to the clone
can exist anywhere on the machine.** After relocating it, fix what names it from outside — MCP client
configs, launchd plists, cron, shell aliases, IDE run configurations. And when a process "will not
start", read its log before re-reading its config: the config says what was attempted, the log says
what happened, and they are usually different problems.

### THE DEPLOY WENT RED AND THE DEPLOY SUCCEEDED. AGAIN.

Run 134's lesson, second occurrence, and this time the improved error message did its job:

    relayshield-agentic-api WAS DEPLOYED. Only the probe was denied — the deploy
    role has no lambda:InvokeFunction on it.

`iam_github_deploy_invoke.json` gained `relayshield-agentic-api` when that function was mapped, and
**the repo half does not push the policy to AWS**. `sh tools/apply_deploy_invoke_policy.sh` does, and
until it runs every deploy touching that function is red for a reason unrelated to the code.

Worth restating because it keeps costing time: **a red run names a step, not an outcome.** "The
deploy failed" and "the check after the deploy failed" are different facts with different fixes, and
the second one costs nothing if read correctly and a rollback if it is not.

### THERE ARE FIVE MCP SURFACES, NOT ONE

Asked as "I think I only have one MCP server, can you check". Inventoried 2026-09-05:

| Surface | What it is | State |
|---|---|---|
| `relayshield-mcp` on PyPI | stdio, the one that appears in a client | live, 0.2.9 |
| MCP registry entry | the canonical directory listing | active, pinned 0.2.7 |
| HuggingFace Space | hosted MCP over HTTP | egress-blocked from the container |
| Apify Actor | MCP over Streamable HTTP, Standby | egress-blocked from the container |
| `@relayshield/bankr-mcp` | a TypeScript stdio server built for Bankr | never published |

**Only the first can show "disconnected" in a client.** The hosted two would present as a failing
URL, and the Bankr one has never shipped. Knowing which surface is which is what turned an
open-ended "the MCP server is down" into one log line. Full detail in `mcp_surfaces_inventory.md`.


### THE DIAGNOSTIC PAID FOR ITSELF ON ITS FIRST RUN

Written the same day as the script it describes, because the result is the argument for the habit.

Two candidate causes with different fixes: the gateway resource wired to the wrong function, or the
route right and the deployed code stale. Guessing would have been a coin flip, and the wrong guess
means deleting and recreating gateway methods on a live API for no reason.

`diagnose_agent_bait_routes.sh` answered it in one run and left nothing to interpret:

- Step 3: **both** resources integrate with `relayshield-agentic-api`. The routes were never wrong.
- Step 5: that function, invoked DIRECTLY with the gateway taken out of the path, returns
  `x402Version: 2` and this endpoint's own description — so the handler is current.
- The `$0.25` was `relayshield-api`'s fallback for a path it does not know, reached only because the
  gateway had been sending it there before the deploy.

**Cause B, and the fix was a push rather than anything touching AWS.** A `/{proxy+}` at the API root
turned up in step 4 and is not a factor: an explicit resource beats a greedy proxy. Recorded so
nobody re-opens that question.

The habit worth keeping: **when two causes produce the same symptom, the cheap read-only script that
separates them is worth writing before the first guess, not after the third.**

### A 402 IS NOT PROOF THE RIGHT LAMBDA ANSWERED

The most useful mistake of the session, and it is run 134's lesson in a new costume.

`create_agent_bait_scan_routes.sh` printed **"LIVE. The x402 door challenges for payment at $0.50"**
over a response body that plainly said `"price": "$0.25 USDC"`. The script asserted the status code
and never looked at the body.

**`relayshield_api.py` answers `/v1/payg/*` too, and its unknown-path default is 250000 units.
`relayshield_agentic_api.py`'s is 350000.** So a route wired to the wrong function, or a stale
deployment, returns a perfectly well-formed 402 at the wrong price, and every structural check
passes. The price is the only discriminator, and nothing was checking it.

Both scripts now assert the price. **The general form: when two components can produce the same
shape of success, verify the field that differs between them, not the shape.**

### THE PYPI NUMBERS CAME BACK, AND THE HONEST READING IS MIXED

    langchain-relayshield       last_day 2   last_week 4    last_month 137
    openai-agents-relayshield   last_day 2   last_week 6    last_month 143
    relayshield-mcp             last_day 6   last_week 44   last_month 322

**`relayshield-mcp` is the real one.** 44 a week and 6 a day is a steady rate consistent with actual
use, and it is the package with the least marketing behind it.

**The two framework packages are a burst plus a trickle, and the monthly number flatters them.** 137
a month against 4 a week is not a rate — 4 a week annualises to about 17 a month, so most of that
137 landed at once. That shape is a mirror scrape or a CI matrix, not adoption.

**It still justifies `crewai-relayshield`**, because the marginal cost is half a day against code
that already exists, and because a trickle from a package nobody has promoted is a better base rate
than zero. It does NOT justify treating framework packages as a growth channel. Rank the work
accordingly, and quote none of these numbers externally — MEASUREMENT DOCTRINE applies to our own
download counts exactly as it does to the corpus.

### A MODULE-LEVEL SECRET CACHE WITH NO TTL WAS A SILENT BILLING RISK

Found while answering "can I delete the old Stripe key". Three handlers cached the Stripe secret for
the life of the execution environment with no expiry, while `relayshield_stripe_webhook.py` re-read
it every call. So the two halves disagreed for minutes to hours after any rotation.

That would be a harmless race except for what fails in it: `_record_stripe_meter_event` is
fire-and-forget and never raises, so a 401 from a revoked key is caught, logged at WARNING, and the
customer is served the paid response anyway. **Revoking early produced no outage and no red alarm.
It produced silent under-billing.**

`_get_secret` now carries `_SECRET_TTL = 300` in `relayshield_api.py`, `relayshield_agentic_api.py`
and `relayshield_mpp_settlement.py`, and falls back to the last known good value if a refresh fails.
Rotation is now: write the secret, wait six minutes, revoke. **It also removed an IAM dependency
rather than adding one** — the operator identity's implicitDeny on
`lambda:UpdateFunctionConfiguration` stopped mattering, because nothing needs to force a recycle any
more. Fixing the cause beat granting the permission.

### THE DEMO'S AUDIENCE, since it was asked

Ranked by whether the recipient has a DISTRIBUTION interest, not just interest:

1. **Routavo.** Their "Control" pillar is spend control on the buy side; we are the sell side and
   the counterparty question is the gap they do not cover. Already registered for early access, so
   it is a follow-up rather than a cold approach.
2. **Rain, `apa@rain.xyz`.** The first demo is what they responded to. A merchant-agent version is
   new information rather than a nudge, and the two open questions from that submission are still
   unanswered.
3. **Stripe, Jake Lamoine.** The MPP conversation is live and stuck on eligibility. A working demo
   is the concrete artefact, and it pairs with the carried question about early-adopter status.
4. **Coinbase CDP / the x402 Foundation.** We are in the Bazaar, we have filed on their repo, and
   they run a community show-and-tell — see `cdp_discord_show_and_tell_post.md` for the format that
   worked last time.
5. **Aduna, via Reggie Daniels.** Warm intro pending; `aduna_outreach.md` has the messaging.

**Not Anthropic.** `anthropics/commerce-agents` says in its own README that it is unmaintained and
does not accept contributions. There is no channel there, and sending a demo to a repo that says it
takes nothing is the CrewAI mistake with the label already read.

---

## WHERE 2026-09-04 LEFT THINGS — read this first

### THE BLOCKED SOURCE WAS REACHABLE ALL ALONG, AND IT MADE A DERIVED SHAPE WRONG

The single most useful thing this session found, and it generalises well past Stripe.

Two sessions recorded `docs.stripe.com` as egress-blocked and derived Stripe's wire shapes from
prose instead, labelling them "derived, not verified". Both statements were true. The conclusion
drawn from them was not: **that the shapes could not be verified from this container.**

They could. Nobody had tried the two obvious neighbours:

- **`registry.npmjs.org` is reachable**, and `mppx` — Stripe's OWN reference implementation of MPP —
  is published there with readable source. `npm view` needs no browser.
- **`raw.githubusercontent.com` is reachable**, and `github.com/tempoxyz/payment-auth-spec` is the
  IETF draft that mppx cites, co-authored by Tempo and Stripe.

Reading the implementation settled every open question in an hour, and **one of the two derived
shapes was wrong in three separate places** — a missing `mode` key, `transaction_verification`
where the real name is `transaction_verification_options`, and a missing
`payment_method_types: ["crypto"]`. The pinned API version was wrong too: `2026-05-27.preview`
where mppx pins `2026-07-29.preview`, which matters because **a probe on the wrong preview version
reports "not enabled" for an account that is enabled.**

**The general form, and it belongs next to "NO AWS IN THIS SANDBOX IS NEVER A REASON TO SKIP A
CHECK": a blocked documentation site is not a blocked FACT.** Before recording anything as
underived, try the package registry, the vendor's own SDK source, the spec repository, and
raw.githubusercontent.com. A vendor that documents a protocol almost always ships an
implementation of it somewhere fetchable, and the implementation is better evidence than the docs
anyway.

### MPP is an HTTP AUTHENTICATION SCHEME, not a JSON block in a response body

The invented `mpp` block this endpoint shipped with on 2026-09-04 was not merely unverified, it was
structurally wrong. MPP uses the `Payment` scheme under RFC 7235: the challenge rides
**`WWW-Authenticate`**, the credential comes back in `Authorization`, the receipt goes out in
`Payment-Receipt`. The challenge `id` is **HMAC-SHA256 bound to the challenge's own contents** over
seven fixed pipe-delimited slots, which is what stops a client altering the amount and presenting an
id we would still accept.

That is implemented and tested now. **The credential side is not**, and the challenge is therefore
switched OFF by default (`RELAYSHIELD_MPP_CHALLENGE=off`): redeeming a Shared Payment Token is a
Stripe call this module does not make, and SPTs are in private preview on top of the crypto gate.
**Advertising a payment method we would then reject is worse for the agent than never offering it**
— it spends the agent's authorisation on a route that cannot complete.

`npx mppx@latest validate <url>` is the objective compliance test and it runs on the Mac. It is the
acceptance criterion, not our own reading.

### relayshield_agentic_api.py IS RECONCILED. Item 8 is closed.

It was far smaller than four sessions of carrying it implied: **+22 / -1**, both hunks live-only,
fully readable in one screen.

- **The branded `API_BASE_URL`** (`https://api.relayshield.net`, not the execute-api host), with a
  five-line comment explaining that this URL is advertised as the resource in every 402 and is what
  x402 indexers persist.
- **The Bundle D "Door 2" branch**: a direct-Stripe bundle key must be metered ABOVE the
  `has_subscription` test, or it is classed "unlimited under an existing subscription" and billed
  nothing while the AWS door bills per call.

Main has been moved to the live bytes VERBATIM — a pure move, no edits — so live is byte-identical
to main, and `relayshield_agentic_api.py` is now in `deploy_lambdas.yml`: the `paths:` trigger, the
`LAMBDA_MAP`, and `iam_github_deploy_invoke.json`. Recover, read, reconcile, then map, in that
order and no other.

### RULE 12 FIRED AGAIN, THE DAY AFTER IT WAS WRITTEN

Stripe documentation was pasted into the session on 2026-09-04 with the account's **live
`sk_test_` secret key interpolated into the curl samples**, exactly as on 2026-09-03. Stripe
personalises examples for a signed-in reader; nobody typed a credential and one arrived anyway.

**Roll it in the Dashboard under Developers, API keys.** And read rule 12 as what it is: not a
one-off, a property of every vendor doc page read while signed in. Screenshots carry it too — the
key is rendered into the image, so "I only sent a picture" is not a mitigation.


### The MPP settlement endpoint is BUILT. Item 1 of the 2026-09-03 list, second half.

`relayshield_mpp_settlement.py`, one endpoint, `POST /v1/mpp/mcp-registry-risk` at $0.35 on Base,
settled through Stripe with a fallback to the rail that already collects. 30 offline tests. Full
write-up in `mpp_settlement_endpoint.md`.

**It is NOT live yet and needs two commands on the Mac**, in this order and no other. Note the
shapes below were CORRECTED on 2026-09-04 against Stripe's own reference implementation — see
"THE BLOCKED SOURCE WAS REACHABLE ALL ALONG" above:

1. `sh tools/create_mpp_settlement_lambda.sh` — creates the function, its own IAM role, both gateway
   routes, and proves the 402.
2. `AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/mpp_settlement_selftest.py` — settles whether
   the Stripe parameter shapes are right.

**Three things in it worth carrying:**

- **It is a NEW FILE and not a branch in `relayshield_agentic_api.py`, on purpose.** That file still
  carries unreconciled live drift (item 8 below). Adding an endpoint there and giving it a deploy
  path is the 2026-08-17 mistake exactly. A new file has no live counterpart, so it cannot drift
  from one. The detector is IMPORTED from agentic_api rather than copied, because this repo already
  has four copies of one pattern table and does not need a fifth. The deployer's `resolve_deps` grep
  is `^[[:space:]]*(import|from) relayshield_`, so a function-level indented import is still
  packaged — checked against that grep, not assumed.
- **It is not in `deploy_lambdas.yml`, and must not be until the function exists in AWS.** The
  deployer calls `update-function-code` on whatever `LAMBDA_MAP` names, so mapping a function that
  does not exist turns the first push red with a `ResourceNotFoundException` that reads exactly like
  a broken deploy. Create first, map second. `relayshield-mpp-settlement` IS already in
  `iam_github_deploy_invoke.json`, so the first CI deploy will not repeat run 134's denied probe.
  **`sh tools/apply_deploy_invoke_policy.sh` still has to push that file to AWS** — the repo half
  does not do it on its own.
- **Two Stripe wire shapes in it are DERIVED, not verified**, because `docs.stripe.com` is blocked
  from the container. Both are isolated in single builder functions with no branching so a
  correction is one line, and `tools/mpp_settlement_selftest.py` exists to have Stripe name the
  wrong parameter rather than guessing again. The `mpp` block in the 402 body says
  `"version": "unverified"` in its own payload for the same reason. **Derived is not verified, and
  saying so in the artefact is cheaper than being wrong in production.**

### Andrew's merge failed, and BOTH halves of the failure came from one cause

    error: The following untracked working tree files would be overwritten by merge:
        agent_baiting_scope.md
        outreach_bot_prospects_curated.md

Both files are on `claude/top-10-todos-discord-lambda-vn4583` AND were saved by hand into
`~/Side SaaS Hustle` from a chat paste — the delivery process at the top of this file, working. Git
will not clobber an untracked file it did not write, so the copies collided and the merge aborted.
`tools/stripe_machine_payments_probe.py` and `tools/fd8_prepare_republish.py` were then "missing"
only because the merge that would have delivered them never completed.

**The general form, and it will recur:** the chat-paste delivery rule and `git merge` collide by
design. Anything pasted into chat AND committed blocks a later merge. The fix is to delete the
hand-saved copy immediately before merging — the branch copy is identical, so nothing is lost.

### The drift check RAN with the Discord bot in it, and the bot is clean

Run 25, scheduled 2026-09-03 16:56, executed and went red. It opened issue #23, naming
**relayshield-agentic-api and relayshield-developer-signup** — and NOT relayshield-discord-bot.
That is the positive evidence 2026-09-03 was waiting for: the bot deployed, and live matches main.
Closes the "the drift check has still never run with the Discord bot in it" item below.

Deploy runs 135 and 136 are both GREEN, so the invoke-policy fix took and run 134's red probe is
behind us.

**Do not close #23's developer-signup half without re-checking.** Run 25 fired at 16:56 and deploy
run 136 shipped at 17:57, an hour later, so the drift it names may already be gone. The next
scheduled drift run answers it; a stale issue is not a finding.

---

## WHERE 2026-09-03 LEFT THINGS — read this first

### THE LIST FOR THE NEXT SESSION, in order (10 items)

Written at the end of 2026-09-03. Everything above item 1 that used to be on the 2026-09-02 list is
either done or has moved into these.

1. **Stripe machine payments: probe, then build ONE endpoint.** The email to Jake is SENT with the
   four questions. The next move does not wait on his reply: run
   `tools/stripe_machine_payments_probe.py` (read-only) to learn whether the account can call the
   x402 surface at all. Enabled means build one endpoint settling to Stripe alongside the existing
   PayAI rail, which is the artefact their team responds to. Not enabled means that error text is a
   better follow-up to Jake than a second nudge. **Settlement question answered: stablecoin payments
   settle into the Stripe balance in USD, on the normal payout schedule.** Crypto in, dollars out,
   same balance as the subscriptions.
2. **Send the twelve.** `outreach_bot_prospects_curated.md` is written and hand-picked: five real
   inboxes first, then the seven websites where the page has to carry a form. Track replies per 100
   by channel. `TegroTON/ai-telegram-pay-miniapp` is the one worth the most care.
3. **Apify article: submit to `#apify-writers` at the next quarterly call.** Draft is
   `blog-apify-actor-as-agent-tool.md`. Three facts to confirm with the console open first, listed
   in its own NOT FOR PUBLICATION section. **It must not appear on blog.relayshield.net first:**
   originality is a programme rule and publishing early disqualifies it.
4. **FD-8, FD-9 and FD-10 in one publish.** `tools/fd8_prepare_republish.py --dir ~/mcp-live
   --write` makes all the edits, including the `?source=pypi` link in pyproject.toml, and refuses
   to invent the publish command. Then FD-11: submit the Smithery LISTING, decline hosting.
5. **Build `agent-bait-scan`.** Recommended, 3.5 days, scoped in `agent_baiting_scope.md`. Island's
   research names a gap our catalogue genuinely has: we screen the name and the domain, and nothing
   of ours reads the INSTRUCTIONS an agent is given. The differentiator is signal 4, joining those
   instructions to the criminal corpus, which nobody replicating this can do.
6. **Mini App v1**, then the channel submissions. The discovery list is measured and waiting:
   `@trendingapps` (3.9M, and `@twa_apps` is the SAME channel), `@web3telegrambotx` (72,742),
   `@findminiapp` (56,380), `@onclicka_tma_en` (33,723), `@telegtapps` (9,671). Each gives one first
   impression and we spend it by submitting before the Mini App exists.
7. **Measure the widget.** It is live and keyless. The number that matters is installs making a
   SECOND day of calls, not total calls, and `source=tg-widget` is on every request.
8. **`relayshield-agentic-api` drift.** Still recovered-but-unreconciled on
   `claude/recovered-live-relayshield-agentic-api`. Live carries a branded API_BASE_URL and a Bundle
   D Stripe branch main does not. Same shape as the developer-signup recovery that worked.
9. **INTEL-5 funnel.** `tools/diagnose_stolen_sessions.py` on the Mac. Until it runs, no count out
   of `relayshield_stolen_sessions` means anything about the criminal market.
10. **XSOAR.** Nothing to do. `xsoar_pack_watch.yml` runs daily and opens an issue the day the pack
    lands on master. Checked 2026-09-03: still not on master.

### What this session shipped

- **The Discord footer is live**, after the drift diff was read, the function mapped, and run 134's
  red probe understood as a denied `lambda:InvokeFunction` rather than a failed deploy.
- **`relayshield_developer_signup.py` recovered and reconciled** — 700 live-only lines including two
  Stripe revenue doors — then mapped in the deployer, in that order.
- **The Telegram widget**, keyless end to end, with `/v1/link-check` new and the gateway route live.
- **The prospecting pipeline**, now with contact hygiene that screens README examples out of both
  the extractor and the generator.
- **Attribution keys** for `tg-widget` and `pypi`, both registered BEFORE the links that use them.



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

### FD-8 re-publish now closes three things, not one

Checked live against the registry API on 2026-09-03, rather than from the doc:

- `websiteUrl` on the latest version is still the bare `https://relayshield.net`. The defect is real
  and current.
- **The registry is TWO VERSIONS BEHIND PyPI.** Registry latest is 0.2.7 (2026-07-19); PyPI is on
  0.2.9. Whatever 0.2.8 and 0.2.9 changed has never reached the canonical directory.
- `repository.url` says `github.com/relayshield/relayshield-mcp` on every published version, and
  Glama's listing path mirrors it, so if that repo does not exist the mismatch is a broken link on
  two live surfaces rather than a cosmetic oddity.

So the single `mcp-publisher` re-publish fixes the attribution key, the version lag and the
repository URL together. Do all three in one version rather than three.

### The Apify Actor exists, and the session that could not find it was the one that was wrong

`relayshieldadmin/relayshield-security-tools` is public on Apify Store, pay per usage, 154 runs, an
MCP server over Streamable HTTP. `_APIFY_BANNER` was accurate all along. Two lessons, and the second
is the useful one:

- **Absence of evidence from a blocked container is not evidence of absence.** apify.com is egress
  blocked here and a web search found nothing, and the honest conclusion was "unresolved", which is
  what was recorded. Had it been recorded as "the Actor does not exist", the next session would have
  deleted a true claim from a live page.
- **The Actor's Dockerfile carries the best technical story we have written down this quarter**, and
  it was invisible to this repo because the Actor's source lives on Apify rather than here. Worth
  asking what else is like that.

### The developers page now points AT Apify, not just away from it

`_APIFY_BANNER` handles arrivals FROM Apify. Nothing on the page mentioned the Actor, so the only
way to find it was to already be on Apify. Added as a card in the SDK grid, linking the Store
listing, with no run count on it: numbers on a landing page are a maintenance burden and the listing
carries the real one.

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
- **`outreach_bot_prospects_curated.md`** — the twelve worth sending first, hand-picked from the
  generated 40, each with the contact, the rationale, and a message written to that prospect rather
  than to its tag. Includes the three that are deliberately NOT on it and why.
- **`tools/stripe_machine_payments_probe.py`** — read-only. Answers "is this account enabled for
  machine payments" before anybody writes an endpoint against it.
- **`tools/fd8_prepare_republish.py`** — makes the server.json edits for FD-8, FD-9 and FD-10 and
  refuses to invent a publish command: it greps the repo's own README for the one that already
  works.
- **`agent_baiting_scope.md`** — what Island's AgentBaiting research means for us, what
  `mcp-registry-risk` already covers, and the one endpoint worth building.
- **`blog-apify-actor-as-agent-tool.md`** — the Apify content-programme draft.
- **`tools/generate_outreach.py`** + `test_generate_outreach.py` — item 2's generator, and the ten
  tests that stop a draft ever diagnosing a prospect.
- **`miniapp_discovery_and_stripe_choice.md`** — why the widget must not carry a Mini App link, what
  actually drives Mini App discovery, why a browser extension is not the play, which Stripe agentic
  product to select, and the four questions to put to Jake while access is in review.
- **`tools/contact_hygiene.py`** + `test_contact_hygiene.py` — the screen that stops a README
  example becoming an outreach recipient. Wired into both the prospector and the generator.
- **`tools/find_miniapp_channels.py`** — searches for channels that announce new Mini Apps and
  reports measured member counts, ON THE PROSPECTING SESSION. Now also takes SEED_CHANNELS
  (`@trendingapps`, `@twa_apps`, and `@tapps_bot` as the submission route the first names in its own
  description), because search does not reach everything and a channel a human named should be
  measured rather than argued about. It refuses to run against
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
3. **Apify post. UNBLOCKED 2026-09-03: THE ACTOR EXISTS AND THE DRAFT IS WRITTEN.**
   `relayshieldadmin/relayshield-security-tools`, public, pay-per-usage, an MCP server over
   Streamable HTTP in Standby mode, 154 runs, last build 0.1.7. So the banner was true and the
   session that could not find it was wrong, which is the right way round for once.
   `blog-apify-actor-as-agent-tool.md` is the draft: ~1,300 publishable words on why Standby rather
   than run-per-request, and the dependency conflict that crash-looped every real run
   (`apify>=2,<3` pulls a Crawlee whose `HttpHeaders` model dies against the Pydantic FastMCP
   needs, with "cannot specify both default and default_factory" at import time; `apify>=4,<5`
   fixes it by going FORWARD, not back). **Its NOT FOR PUBLICATION section carries the three facts
   to verify with the console open before submitting, and the one rule that would disqualify it:
   originality, so it must NOT go on blog.relayshield.net first.** That inverts our usual
   canonical-first order. Original entry follows. **BLOCKED ON A QUESTION NOBODY HAD ASKED:
   DOES OUR APIFY ACTOR EXIST?** The programme's own rule is that articles are "written by
   developers who've actually built the thing they're writing about", 1,000 to 5,000 words,
   original, submitted through their Discord, $500 on publication. Both halves of the theme
   ("Actors that plug into your stack", "your Actor as a tool for AI agents") require an Actor.
   **`_APIFY_BANNER` on the live developers page asserts one exists** — "The RelayShield actor runs
   breach, infostealer and SIM-swap checks as an Apify task" — and 2026-09-03 could find no
   evidence of it: no Actor code anywhere in this repo, and no store listing in a web search.
   apify.com is blocked from the container, so this is UNRESOLVED rather than disproved. It is the
   same shape as the MetaMask Snap claim, on a live page, and it gates the post either way. The
   July call closed 2026-08-16 and it is QUARTERLY, so there is time to settle it. Also **put
   dev.to back in the channel order** — it is missing entirely and costs nothing.
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
7. **FD-9 — VERIFIED 2026-09-03: WE ARE LISTED.** `glama.ai/mcp/servers/relayshield/relayshield-mcp`,
   found by web search because glama.ai is still egress-blocked here. The listing path is
   `relayshield/…`, matching the registry's `repository.url`, so Glama indexed from there — which
   turns the "probably harmless" owner mismatch in item 6 into a possible broken link on a live
   listing. **Two more doors found the same day:** PyPI's project page links to the developers page
   with no `?source=` (FD-10), and Smithery has no RelayShield entry at all (FD-11). Both are
   written up in `FRONT_DOORS.md`, including why a Smithery LISTING is fine and Smithery HOSTING
   deserves a decision. Original entry follows. **FD-9 — verify Glama by hand.** `glama.json` is present in the MCP server repo, but `glama.ai`
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
