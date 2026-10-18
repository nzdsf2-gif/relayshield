<!-- Verbatim sections moved out of CLAUDE.md on 2026-10-18, original order. Not auto-loaded.
     Find one with: grep -n 'WORDS' docs/claude_memory/INDEX.md -->

## THE TI DEMO QUOTES SIGHTINGS UNDER AN INDICATORS LABEL, AND NOTHING CAN SEE WHAT IS LIVE

**2026-09-16, asked as "need to update the metrics for our TI corpus" on
`relayshield-ti-demo.relayshieldadmin.workers.dev`. Two findings, and the first
is not staleness.**

`cloudflare_worker_ti_demo.js` shows **"5.4M+ / IOC indicators"**, and its own
comment above the cards names the source: *"verified live against DynamoDB
2026-08-12: intel_iocs 5,483,159"*. That is the ROW COUNT of
`relayshield_intel_iocs` -- and `export_intel_sample.py`'s `collapse()` says in
its own docstring why that is not an indicator count: *"The table is keyed
(ioc_value, seen_ts), so a value seen on five days is five rows. Counting rows
would inflate every number we quote."*

**So the card is a SIGHTINGS count wearing an INDICATORS label**, and the two
differ by roughly an order of magnitude: the 2026-09-03 measurement recorded
**494K distinct against 5.8M sightings**. Refreshing the number would keep the
defect and change its date. This is MEASUREMENT DOCTRINE's exact warning, on the
page most likely to be read by somebody who checks.

`tools/ti_demo_metrics.py` re-measures all four cards with the right units and
prints two paste-ready replacements: **sources-not-counts** (recommended, what
the AWS listing already does, cannot go stale) and **corrected counts with a
date on every card**. The distinct count is a full multi-million-row scan, so it
is opt-in behind `--distinct`; without it the tool says outright that indicators
were NOT measured rather than printing the row count under that heading, which
is the defect it exists to stop.

### AND NOTHING IN THIS REPO CAN SEE WHAT THAT WORKER ACTUALLY SERVES

**The DRIFT RULE's third case, open since it was written: "The TI demo
Cloudflare Worker -- still outstanding. Nothing does it for Workers yet."** It is
worse than unwatched. `grep -rl ti-demo .github/workflows` returns NOTHING, so
no workflow has ever deployed it: every live version was pushed by hand, which
is precisely where an uncommitted edit survives. `wrangler deploy` would replace
it with the repo copy and print success.

**So the metrics edit could not safely be made blind, and that is the whole
reason this turn produced a recovery tool rather than a copy change.**
`tools/recover_live_worker.sh` downloads a deployed Worker through the Workers
API -- wrangler has no download command, the API is one GET -- and diffs it
against the repo copy. Read-only, writes only to the scratch directory.
`api.cloudflare.com` is egress-blocked here so it could not be run against the
real host, and all four branches were therefore exercised against a local
stand-in: unreachable, 403, identical, and drifted.

**One defect in it was found by running it and could not have been found by
reading it.** `CODE=$(curl ...)` under `set -e` ABORTS THE SCRIPT on a failed
connection, silently, and the pipeline downstream still reported exit 0 -- so an
unreachable API read as "nothing to recover", which is the worst of the three
outcomes. It carries `|| true` and an explicit no-answer branch now, and that
branch says the failure is a fact about the network and not about the Worker.

## THE FUNNEL PRINTED COUNTS AND "NO EVENTS" UNDER EVERY ONE OF THEM

**2026-09-16, in the `--snapshot before-tgapp` run.** Six stages reported real
numbers (CHECKED 2, WATCHED 2, BOT 1, STARS 1, DEVELOPERS 5) and the window
section under them said, for every single stage:

    CHECKED     no events, so no window was observed

**Two halves of one output contradicting each other, with nothing saying so.**
`min(@timestamp)` comes back from CloudWatch Insights as a FORMATTED STRING --
`2026-09-15 12:34:56.789` -- not as epoch milliseconds. `int(float(raw))` raises
on that, the old code caught it and returned `None`, and `None` renders as "no
events".

**That is not cosmetic, because the window IS the sliding-window caveat.** A
`--compare` delta only measures a submission if the two runs are close together
relative to the window each observed, and this section is the only thing that
reports what was observed. It has been silent on every run, so **every baseline
taken so far carries no way to check that afterwards** -- including
`before-telegtapps` and `before-tgapp`. The quiet alarm, in the tool written to
stop confident wrong numbers.

`_parse_insights_ts` accepts both shapes rather than assuming one, and returns
`None` for anything unparseable, because a wrong window is worse than an absent
one: it is a number the reader acts on. Four tests, proven by reintroducing the
old parse.

**The general form, and it is new: two numbers in one output that cannot both be
true is a defect even when each is individually plausible.** Nothing errored,
both halves looked like normal output, and only reading them TOGETHER shows it.

## THREE COMMANDS I SHIPPED ON 2026-09-16 AND ALL THREE FAILED ON HIM

Every one was mine, none was a typo, and each is a rule this file already
carries being broken in a new file.

### 1. tg.app KEYS A LISTING ON THE BOT, NOT ON THE LINK. THERE IS ONE PER BOT.

Submitting the bot returned *"a listing with this Tg link already exists"*. The
Mini App listing is `t.me/relayshield_bot/idcheck?startapp=...` and the bot is
`t.me/relayshield_bot?start=SRC_...`. **tg.app normalises both to the bot
username**, so they are the same listing to it, and the Mini App card already
holds that slot.

**I INFERRED THREE LISTINGS FROM THE SHAPE OF THEIR SIDEBAR.** Creator Studio
has separate routes for apps, bots, channels and groups, and I read four menu
items as four permitted entries per bot. That is rule C exactly -- a procedure
written for a surface whose rules I had not read -- and the menu was never
evidence about uniqueness.

**Nothing is lost and there is nothing to retry.** The slot went to the better
surface: the Mini App is the thing a catalogue visitor can open, and it is
approved and live. `t.me/RelayShield` is a DIFFERENT username, so the channel
listing is unaffected.

**The general form: a navigation menu tells you what KINDS of thing a system
holds. It never tells you the uniqueness constraint.** One is a layout, the
other is a rule, and only the second one rejects a submission.

### 2. "Cloudflare account id:" WAS ANSWERED WITH AN EMAIL ADDRESS, CORRECTLY

`tools/recover_live_worker.sh` prompted for an account id, got
`relayshieldadmin@gmail.com`, and returned a 404 whose own reading guide said
*"no deployed script by that name"* -- sending the reader to check the Worker.
**The Worker was never the problem.**

A Cloudflare account id is a 32-character hex string buried in a dashboard
sidebar. **A prompt that does not say so is rule 11's placeholder wearing a
question mark**: it looks like an instruction to whoever wrote it and is
unanswerable to whoever reads it. An email is the most reasonable guess there is.

Two fixes, and the first removes the question rather than explaining it: the
token LISTS the accounts it can see, so the script discovers the id and names
the account it picked. The second is a format check, because the failure it
prevents reads as a missing Worker rather than as a bad input.

**And the discovery itself shipped broken and was caught by running it.** It
grepped `"id":"..."` out of the JSON and matched nothing when there was a space
after the colon -- an empty result indistinguishable from "this token sees no
accounts". It parses with `json.load` now. **Grepping JSON is grepping a
template literal's source: it works until the shape moves by one character.**

### 3. THE METRICS TOOL HUNG, AND IT IS THE `filter_log_events` DEFECT REBUILT

`tools/ti_demo_metrics.py --distinct` printed its header and then nothing.
Nothing raised and no output was lost: `Select="COUNT"` **still reads every page
of the table**, so counting 5.5 million rows is thousands of sequential round
trips before a single number can print -- with a real read bill accruing behind
a silent screen.

**That is the defect this file records about `tools/miniapp_funnel.py`, in a new
file, four days later, by the same author.** The section is titled "THE FUNNEL
WAS HUNG, NOT BROKEN" and names the exact mechanism. A lesson recorded in one
file is not a lesson the next file learns, for the third time, and writing it
down again is evidently not the fix.

**The fix is `DescribeTable`, which is one call and free.** `ItemCount` is
approximate and refreshed roughly every six hours, which is fine for a headline
about to be rewritten as prose and never fine for a number quoted to the row --
another reason the recommendation is sources-not-counts. The two small tables
still scan, because they need a filter, and they now print a page counter:
**a tool that goes quiet is indistinguishable from a tool that has hung.**
`--distinct` states the cost and the row estimate BEFORE it starts.

**THE RULE, and it is the one all three share: a long-running read announces
itself before it starts and reports progress while it runs.** Anything else is
indistinguishable from a hang, and the reader's only move is Ctrl-C and a round
trip.

## THE TI DEMO CARDS ARE UPDATED, AND THE FIRST ONE NOW NAMES ITS UNIT

**2026-09-16. Measured by `tools/ti_demo_metrics.py`, which is the only route
these should ever be refreshed by:**

    intel_iocs rows            7,602,575   SIGHTINGS
    malpedia_families          3,815
    intel_channels active=true 113
    mitre_attack sk=info       193

**The card that read "5.4M+ / IOC indicators" now reads "7.6M+ / Indicator
sightings", and that half is not cosmetic.** The number was never merely stale:
`relayshield_intel_iocs` is keyed `(ioc_value, seen_ts)`, so refreshing the
figure alone would have carried the wrong unit forward with a newer date on it.
The hero was rewritten to match, because two numbers on one page that disagree
about what they count is the same defect one layer over.

**The founder chose counts over the sources-not-counts alternative, with the
MEASUREMENT DOCTRINE trade-off on the table.** That is a business call and it is
his. **The unit being correct is not a preference and was not part of it.**

### THE GUARDS, AND THE FIRST VERSION FAILED ON THE CORRECT LABEL

`test_ti_demo_metrics.py`, seven tests, read from the page the Worker ACTUALLY
SERVES via the new `tools/ti_demo_render.mjs` -- the TI demo holds its page in a
template literal exactly like the Mini App, and `node --check` answers "does
this parse" and never "does this run".

Four defects, each proven by reintroducing it: the row count labelled "IOC
indicators" (two guards fire), an approximate `ItemCount` printed as the exact
`7,602,575`, the hero and the card disagreeing on the unit, and a `+` on a
small exactly-counted card.

**AND THE FIRST VERSION OF THE UNIT GUARD WAS A BANNED-WORD LIST, WHICH FAILED
ON "Indicator sightings" -- the correct label.** That is the CSM-SIMSWAP-1
mistake exactly: a check that forces you to delete a true sentence to pass is a
check that gets loosened rather than obeyed. The rule is narrower than the first
draft and is the real one: **a card may name indicators, and if it does it must
also name the unit.**

### IT IS EDITED, NOT DEPLOYED, AND THAT ORDER IS THE WHOLE POINT

`grep -rl ti-demo .github/workflows` still returns nothing, so every live
version of this Worker was pushed by hand and `wrangler deploy` would replace it
with the repo copy and print success. **`sh tools/recover_live_worker.sh
relayshield-ti-demo cloudflare_worker_ti_demo.js` runs FIRST**; only an
`IDENTICAL` verdict makes the deploy safe. `THEY DIFFER` means live holds
something no commit does, and that is recovered into git before anything
overwrites it -- the 2026-08-17 rule, on the one component that still has no
automated path.

## THE MONITOR SAID A NUMBER WAS PORTED FROM T-MOBILE TO T-MOBILE. IT IS OURS AND IT IS WRONG.

**2026-09-16, reported by the founder as "I received a potential sim swap port out fraud message
indicating my mobile number may be transferred from T-Mobile USA to T-Mobile USA... I'm highly
suspicious it is a bogus message."**

**It is bogus and it is OURS, which is the worse of the two answers.** The wording is
`build_port_out_alert_message` in `relayshield_sim_swap_monitor.py` verbatim -- *"Your phone number
appears to have been transferred from \*{old}\* to \*{new}\*"* -- so this was never a phisher. A
security product told its own founder his number had been stolen, and the sentence it used is not
one that can be true.

**THE DETECTOR WAS RAW STRING EQUALITY ON A VENDOR DISPLAY NAME:**

    port_out_suspected = bool(last_known_carrier != carrier_name and ...)

and `carrier_name` is assembled from a TWO-SOURCE FALLBACK inside
`call_twilio_sim_swap_lookup`: `lti.get("carrier_name") or sim_swap_obj.get("carrier_name", "")`.
Those two Lookup v2 packages spell one carrier more than one way -- "T-Mobile USA" against
"T-Mobile USA, Inc." -- and **either can be transiently unavailable**, so the stored baseline and
the current read disagree byte for byte while naming the same carrier. There was no normalisation
anywhere in the file. **On a phone the difference renders invisibly**, which is why the message
reads as nonsense rather than as a mismatch.

**THE TIMING IS NOT A COINCIDENCE AND IT IS THE PART TO CARRY.** This file records that Twilio
approved SIM swap for the United States on 2026-09-12, and that the code was SELF-GATING until
then: `handle_sim_swap` read `error_code=60606` off a Twilio 200 and returned 503 rather than a
verdict. **So this Lambda began producing real customer-facing CRITICAL alerts four days ago, for
the first time, and the first one it sent was wrong.** The approval did not break anything. It
removed the gate that had been hiding a latent defect, and nothing was watching for that.
**When a vendor approval, a feature flag or a quota lifts a gate, the code behind it is running for
the first time -- treat the first outputs as unproven, not as a resumption.**

### THE FIX IS AN IDENTITY, NOT A BETTER STRING COMPARE

**MCC/MNC is what a port-out actually changes.** Lookup v2 returns `mobile_country_code` and
`mobile_network_code` beside the name; that pair is the carrier's identity on the network, numeric
and not a label anyone reformats. It was being thrown away. `network_identity()` captures it,
`last_known_network` stores it, and it decides whenever both sides carry it. The display name is
what we SHOW; it is no longer what we compare.

`normalise_carrier()` is the fallback for the runs where the vendor withholds MCC/MNC -- NFKC, case,
unicode dashes, collapsed spaces, trailing corporate suffixes -- so the two spellings above land on
one value. And under both, the floor: **a port-out is never reported when the two sides normalise
equal**, restated a second time inside the message builder so the sentence is unemittable whatever
the builder is handed.

**Both halves refuse to alert on a missing read, in both directions.** No baseline is not a
port-out (`relayshield_watchlist_monitor.py`'s first-run rule, in the one place where the message is
CRITICAL), and an unreadable current carrier is not a port-out either -- **"we could not check" must
never render as "it moved"**, which is that file's rule 3 in a new file. `update_user_swap_state`
also refuses to write an EMPTY network over a good one: erasing a baseline is silent, and the run
after it would pass a genuine port-out as clean.

`test_sim_swap_monitor.py` is 16 tests and the file had NO test suite at all. Five defects were
reintroduced to prove them. **One of those five is only caught by the `ast` test**: restoring the raw
comparison inside `process_user` leaves every behavioural test green, because they call
`detect_port_out` directly. **A guard nothing calls is decoration, and only a test that reads the
CALL SITE can tell.**

### THE SECOND FINDING: THE ALERT NEVER GOES TO TELEGRAM, AND THAT IS THE CODE, NOT A FAILURE

He also reported *"I didn't receive this alert on Telegram"*, and that is expected behaviour rather
than a delivery fault -- which is itself evidence the message was ours. Traced rather than assumed:

* the customer alert is **WhatsApp only** (`send_whatsapp` / `send_whatsapp_template`),
* `_push_tg_signal` invokes the Telegram webhook with a **correlation signal**, and
  `handle_inbound_signal` runs predictive warnings and attack-chain checks with it. It does not
  deliver the alert,
* `_send_telegram_admin` is the only Telegram path that sends a body, and it is **admin
  co-notification for business-tier employee records only**.

**So a user whose `delivery_channels` include Telegram still gets nothing on Telegram for the most
severe alert we produce.** That is a real gap and it is NOT fixed here -- the ask was a diagnosis,
and widening a CRITICAL alert's delivery is a product change. Recommended, roughly half a day:
reuse the `action: "send_message"` shape `handle_inbound_signal` already implements, gated on
`"telegram" in delivery_channels`, after the WhatsApp send rather than instead of it.

### AND THE FUNCTION WAS IN NO DRIFT CHECK

`relayshield_sim_swap_monitor.py` is in `deploy_lambdas.yml` and in `iam_github_deploy_invoke.json`
and was in `lambda_drift_check.yml` nowhere. Same shape as `relayshield_oauth_watchlist_monitor.py`:
**a deploy path is not drift detection.** Added. A function that has just started speaking to
customers is the worst one to have no drift answer for.

### THE DIAGNOSTIC, AND WHAT IT SEPARATES

`sh tools/diagnose_sim_swap_alert.sh [+1...]` is read-only and answers three questions that have
three different answers:

1. **Did Twilio report an actual SIM change (`swapped=True`)?** That is the independent signal and
   it is NOT what a port-out alert is built from. True on any recent run means treat the number as
   compromised whatever the carrier strings say. **No lines is the good answer.**
2. **What were the two carrier strings, byte for byte?** The log line now uses `%r` rather than
   `%s`, deliberately: a bare `%s` renders an invisible difference invisibly, in the one log
   somebody reads to diagnose it.
3. **What is stored as the baseline right now**, which is what the NEXT run compares against.

**The phone number is an ARGUMENT and is never written into the repo.** It is personal data and this
repository is public -- rule 12's shape, where the credential-like thing arrives in a pasted message
rather than in a vendor doc.

## TWO SESSIONS FIXED THE SIM SWAP BUG IN PARALLEL. THE MERGE BLOCK I SHIPPED WAS WRONG.

**2026-09-16. The founder ran the merge block and got conflicts in FOUR files**, including an
`add/add` conflict on `test_sim_swap_monitor.py` -- two sessions had independently written a file
of that name on the same day, for the same defect.

**MY FAILURE, AND IT IS A RULE THIS FILE ALREADY CARRIES IN THOSE WORDS.** I checked
`origin/main..HEAD`, saw one commit, and told him the merge was a fast-forward with no CLAUDE.md
conflict. His own output says what I could not see:

    Your branch is ahead of 'origin/main' by 5 commits.

**`origin/main` is a claim about origin. It is not a claim about his clone.** The
"IT IS NOT IN THE REPO IS A CLAIM ABOUT ORIGIN" section says exactly this, and I had even corrected
a stale-ref reading an hour earlier and still drew the conclusion from the wrong end. **A merge
block must anticipate the conflict it is going to cause** -- rule A -- and mine asserted there
would be none. The one command that settles it costs him nothing and belongs in the block before
any claim about the merge:

    git --no-pager log --oneline origin/main..main

**AND THE PUSH AT THE END OF A CONFLICTED BLOCK STILL RAN.** `git push origin main` pushed his five
local commits (`2e6fa37..0a6da4c`) while the merge sat unresolved in the working tree, because
`push` sends HEAD and an uncommitted merge is not in HEAD. So the block half-succeeded: his work
went up, mine did not, and the tree was left full of conflict markers. **A block whose later steps
assume an earlier one succeeded must stop when it does not.**

### THE RECONCILE: THEIRS IS THE BASE, BECAUSE THEIRS IS BETTER

Both sessions found the same three-part defect. The other session's detection is **strictly better
and it is already live**, so it is the base and nothing of it was overwritten:

- **MCC/MNC (`mobile_country_code` / `mobile_network_code`) as the discriminator**, with the
  normalised display name only as a fallback. That is the carrier's identity ON THE NETWORK and it
  does not move when a vendor restyles a string. My branch compared display names and tracked which
  Twilio package supplied them -- a correct answer to a smaller question.
- `detect_port_out()` as one decision point, plus **the same floor again inside both message
  builders**, so "transferred from X to X" is unemittable whatever it is handed.
- `update_user_swap_state` refusing to write an empty network over a good baseline.

**What that branch did NOT carry, and this commit adds on top of it:**

1. **TELEGRAM WAS NOT A DELIVERY CHANNEL AT ALL** -- the half the founder actually asked for.
   `sent` was WhatsApp's result alone, so a user written with `delivery_channels: ["telegram"]`
   enrolled with `/simswap`, was scanned correctly, and was alerted nowhere, with `sent` False so
   the state was never stamped and the same check re-ran every cycle. `sent = wa_sent or tg_sent`
   now, with the bodies built `is_telegram=True` (code spans, `/phone` and `/sweep` instead of
   `Reply PHONE`).
2. **PORT-OUT STILL BYPASSED DEDUP ENTIRELY.** Their detector makes a false transition far less
   likely; it does not make a repeat quiet. Dedup is keyed on the TRANSITION now, preferring the
   MCC/MNC pair, so a different carrier change still fires immediately while a repeat of the same
   one is suppressed for seven days.

**One tool was dropped rather than merged: my `tools/diagnose_sim_swap_alert.py`.** Theirs is
`tools/diagnose_sim_swap_alert.sh`, already on main and already doing the job. Two tools one
extension apart is drift with a delay on it.

### THE TEST FILE APPENDED CLEAN AND RAN NOTHING

`unittest.main()` sat in the MIDDLE of their file, so classes appended below it were defined after
the runner had already exited. The file passed, reported **16 tests**, and silently skipped the
seventeen just added. Caught only by reading the count rather than the OK. **A test file that grows
by appending needs its `__main__` block last**, and the number of tests is the thing to read, not
the word OK -- the quiet alarm, inside the suite written to stop one.

33 tests now, and the four added guards were each proven by reintroducing their defect:

    sent = wa_sent (Telegram gap)   -> 3 failures
    port-out bypasses dedup         -> 1 failure
    carrier bolded on Telegram      -> 2 failures
    transition key never stamped    -> 1 failure

### THE GENERAL FORM, and it is new

**When two sessions ship the same fix, the reconcile is not "mine vs theirs", it is "which half
does each one have".** Both were right about the defect and each missed something the other saw.
Taking either branch whole would have shipped a regression: theirs alone leaves Telegram users
alerted nowhere, mine alone throws away MCC/MNC for a weaker string comparison. **Read both, keep
the better base, and add only what it lacks.**

## WE COULD NOT DETECT A SINGLE GITLAB CREDENTIAL. FOUND BY WRITING ABOUT SOMEBODY ELSE'S CVE.

**2026-09-16, asked as "develop a blog on this GitLab vulnerability, is there an integration angle
for rsscan".** The angle was real and the check for it found a hole.

**41 credential patterns in `NHI_PATTERNS`. GitHub covered TWICE (`github_pat`,
`github_pat_fine`). GitLab: nothing, in any of the three tables.** So the corpus count for GitLab
tokens was **UNMEASURED, not zero** -- the BOT-TOKEN-1 finding in a second place, four days later.

**It matters here specifically because of what the CVE is.** CVE-2026-85706 is an unauthenticated
arbitrary file read on self-hosted GitLab, and watchTowr's own description of the payoff is
*"read local files and configs to obtain credentials, secrets and sensitive information"*. **A
GitLab runner token landing in the corpus would have been collected as ordinary text and counted
as nothing**, in the week that class of credential was being stolen at scale.

**Eight formats added to all three tables** (`relayshield_api.py`, the regenerated rsscan mirror,
and `_NHI_PATS` in the collection path): PAT classic and routable, deploy, runner, OAuth
application, Kubernetes agent, pipeline trigger, CI job. `glffct-`, `glft-` and `glimt-` were
deliberately skipped and the reason is in the comment: none reaches source, CI or a cluster, and
every pattern is a maintenance cost paid in four places.

**ORDERING IS LOAD-BEARING AND IT IS THE TON-INSIDE-SOLANA SHAPE AGAIN.** `glpat-[\w-]{20}`
matches the **first twenty characters of a routable token**, so a table that tries classic first
reports the wrong type with the wrong remediation and never says it was unsure. The routable rule
goes first, and the test asserts the ORDER by resolving a real routable token through the table
rather than asserting both rules merely exist.

**THE REGEXES CAME FROM gitleaks' OWN RULE SOURCE**, not from a docs page:
`raw.githubusercontent.com/gitleaks/gitleaks/master/cmd/generate/config/rules/gitlab.go`.
`docs.gitlab.com` is egress-blocked from the container and `raw.githubusercontent.com` is not,
which is BLOCKED SOURCE WAS REACHABLE ALL ALONG paying for itself a fourth time. **A scanner's
implementation is better evidence about a token format than prose describing it.**

`test_gitlab_token_pattern.py`, 9 tests, every guard proven by reintroducing its defect: ordering
swapped (4 failures), a rule dropped from one table (1), severities disagreeing across tables (1),
and the PAT gated behind `_ctx_key` so it stops matching a clone URL or a CI log (4 plus an error).

### THE POST SAYS WHAT rsscan DOES NOT DO, AND THAT IS THE REASON IT IS PUBLISHABLE

`rsscan` reads `git diff --cached`, on a laptop, before a commit exists. **It has no view of
`gitlab.rb`, `secrets.yml`, or the CI variables in the database**, which is the half of a GitLab
file-read that actually hurts. A post implying otherwise would be selling a laptop tool as a
server control to an audience that would notice within a paragraph.

**So the post states the limit in its own voice and keeps the narrower true claim**: a credential
that never reaches a commit is not in the history the NEXT file-read bug walks. That is a
statement about blast radius, not a mitigation, and saying so is what makes the rest credible.

**And it publishes the gap above as a confession rather than hiding it**, because "clean" and "we
have never looked for this" are the same output from a detector, which is the most useful sentence
in the piece and is true of every scanner the reader runs.

### NOTHING IN THE PUBLISHED COPY RESTS ON A NUMBER I COULD NOT CHECK

`cve.org`, `cisa.gov`, `docs.gitlab.com`, `nvd.nist.gov` and `rapid7.com` are **ALL egress-blocked**
(all HTTP 000, checked rather than assumed). So the CVSS score, the three version strings and the
CISA deadline are **attributed in prose to the party that published them** rather than asserted by
us -- the house rule for a post built on somebody else's reporting, and also what makes an
unverified number safe to print. The argument rests on the MECHANISM, which the source states in
watchTowr's own words. The NOT FOR PUBLICATION section names the three things to confirm in a
browser before it goes out.

## tapps.center IS UNDER CONSTRUCTION. THAT CLOSES `@app_moderation_bot` FOR GOOD.

**2026-09-16, from a founder screenshot of the site itself.** tapps.center now renders
*"Something new is coming -- We're building the next chapter for apps on TON & Telegram"* over an
ecosystem link list (Tonkeeper, Wallet, STON.fi, DeDust, EVAA). **There is no submission route
because there is no catalogue right now.**

**This retires a question this file has spent three rounds on.** The section above asks whether
`@app_moderation_bot` is dead and says the discriminating observation is whether its chat shows a
START button. **That observation is no longer worth ten seconds.** The bot's catalogue is being
rebuilt, so a silent `/start` is explained whatever the bot's state is, and the honest reading of
the earlier evidence is that the TON Studio blog and the 2026 developer write-up were both
describing a mechanism that has since been taken down.

**Do not spend another round on tApps.** Re-check it when something else brings us back to TON
catalogues, and treat the site's own front page as the signal rather than the bot.

**The general form, and it is cheap: when a submission route goes quiet, look at whether the
DESTINATION still exists before diagnosing the route.** Three rounds went into a bot's silence
and one page load explains it.

### AND MY REACHABILITY PROBE WAS UNINFORMATIVE, WHICH I ALMOST REPORTED AS A FINDING

Probing eleven candidate directories from the container returned **HTTP 000 for every one** --
including `tg.app`, `findmini.app` and `ton.app`, all three of which have **accepted a submission
from us in the last two days**. So 000 here means the container's egress policy and nothing about
the destination.

**That is the Apify Actor lesson exactly** (absence of evidence from a blocked container is not
evidence of absence) **and the status-code rule**: 000 is a fact about the request, not about the
site. Had it been written up as "these directories do not resolve", the next session would have
deleted live candidates from the list. **A probe whose negative result is indistinguishable from
its blocked result has no standing to report a negative.**

## tg.app CHANNEL LISTING IS PENDING, NOT APPROVED. READ THE CARD, NOT THE BANNER.

**2026-09-16.** The founder reported the blog channel approved. The green banner on that page says
*"Your listing was approved"* about **"Scam Checker | RelayShield IDCheck"**, which is the MINI APP
and was approved the day before. The channel's own card, lower on the same page, reads
**`RelayShield Blog | Crypto Scam Alerts` / Channel / Tools / Sep 16, 2026 / Pending`**.

**Two listings, one page, and the persistent banner describes the older one.** Nothing was wrong
with the submission and the name recommended for search was accepted verbatim.

**It changes one thing that matters: the funnel baseline.** `--snapshot before-tgappblog` is taken
when the listing goes LIVE, not when it is submitted, because arrivals cannot start before then
and a baseline taken too early measures the window sliding rather than the listing.

**The general form: a status banner and a status field are different claims, and the banner is the
one that persists.** Read the row for the thing you just did.

## THE GITLAB POST IS PUBLISHED, AND `build_blog.py` DOES NOT STRIP THE INTERNAL SECTION

**2026-09-16. The canonical 404'd because the post was never published**, only written: it sat at
the repo root as `blog-gitlab-file-read-credential-theft.md` and the publish path is
`blog_markdown/*.md` with front matter, then `python3 build_blog.py`, then a push to main, which
`deploy_blog.yml` picks up on any change under `blog_markdown/**`. **Writing a blog file is not
publishing one**, which is the LOCAL MERGE IS NOT A PUSH rule wearing a third costume.

**AND THE TRAP THAT WAS ONE `cp` AWAY FROM FIRING.** `build_blog.py` has **no handling of the
`NOT FOR PUBLICATION` marker at all** -- `grep -c` returns 0. Every file in `blog_markdown/` is
pre-stripped BY HAND, so the omission has never fired, while CLAUDE.md prescribes writing that
section on every blog file. Dropping this post in unedited would have published the verification
notes, the attribution key table and the list of what shipped alongside it, to a live page, with
no error anywhere.

**A convention followed by hand every time is a convention that fails the first time somebody is
in a hurry.** `test_blog_publish_hygiene.py` now enforces it, reading the BUILT artifact rather
than the markdown because the source and the served text are different documents.

### THE HOUSE-STYLE GUARDS FAILED ON FIFTEEN LIVE PAGES, AND THE TEST WAS WRONG

The first version asserted no em-dashes and no quote bars across every post and went red on
fifteen of them. **CLAUDE.md says in terms that this is not retroactive:** *"Posts already frozen
in blog_content/ keep whatever html they were published with. Do not rewrite them to match; they
are live pages."* A check that forces you to edit a live page to go green is the CSM-SIMSWAP-1
mistake, and it gets loosened rather than obeyed.

**The cutoff is taken from the data rather than picked:** the newest post carrying an em-dash is
2026-07-29 and the newest carrying a `<blockquote>` is 2026-08-12, so `2026-08-31` sits after
every historical offender and before every post written under the current conventions. A separate
test asserts the cutoff still has posts behind it, because **a scoped guard that scopes itself
down to nothing passes forever** -- the empty-set-reads-as-clean shape.

### TWO OF THE FOUR GUARDS DID NOT FIRE ON THEIR FIRST PROOF, AND BOTH WERE MINE

**The em-dash guard read only `html`.** Proving it by injecting an em-dash put it in the **TITLE**,
because `.replace(..., 1)` hit the front matter first, and the guard reported OK over a post whose
most visible string carried the character. It checks `title`, `excerpt` and `html` now. **A guard
that checks one field of a record is a guard against one field.**

**The quote-bar guard could not be tripped from markdown at all**, and that is correct rather than
broken: `build_blog.py` already renders `> ` as a plain `<p>`, so the house style is implemented
rather than remembered. The path that can still produce one is a post added straight to
`blog_content/*.json`, where the html is hand-written and nothing renders it, and the proof was
redone that way. **When a guard will not fire, establish whether the defect is unreachable before
concluding the guard is broken.**

All four proven: internal section attached (2 failures), em-dash in the title (1), `<blockquote>`
via a hand-written JSON (1), `?source=` on the bare host (1).

## INLINE MODE IS ON THE BLOG FOOTER NOW. IT IS THE ONLY SURFACE WHERE USE DISTRIBUTES.

**Asked as "I'm unclear how you propose to use @rs_bot <link> as a discovery surface. Can we list
it in our blog site or other surfaces?"** The answer is yes and the explanation was mine to get
right the first time.

**WHAT IT ACTUALLY DOES**, read from `handle_inline_query` rather than described from memory: type
`@relayshield_bot` followed by a link or a wallet address **in any Telegram chat**, including a
group the bot is not in and has never been added to. Telegram shows a result card; tapping it
posts the verdict into that conversation, stamped **"via @relayshield_bot"**. No install, no
membership, nobody leaves the chat.

**WHY THAT IS A DISCOVERY SURFACE RATHER THAN A FEATURE.** Every other surface we have consumes
attention to deliver a check. This one produces an impression for everyone else in the room as a
by-product of one person doing something useful: a check run in a 200-person group is seen by 200
people, carrying our handle, **at the moment a scam link was actually posted**. That is a better
moment than any blog post read later by somebody with no pending decision.

**It is on the blog footer, on every page, alongside the email-check line, and for the same
stated reason that line exists**: the blog is read by people who arrived worried about something,
and inline mode needs no account, no signup and no API key. That footer comment records that the
email check "was live for a day with nowhere pointing at it". **Inline mode was live for weeks
with nowhere pointing at it**, which is worse and is the same defect.

**Still pointed at by nothing and worth doing next**, in this order: the Mini App (its users are
already checking things and the group chat is where the next one arrives), the bot's own welcome,
and the share card.

## ON DECK: THE WHATSAPP BOT HAS NO FRONT DOOR AND NO ATTRIBUTION

**Recorded 2026-09-16 at Andrew's request as an on-deck item.** Asked as whether there are
catalogues to register the WhatsApp bot in. **There is no WhatsApp catalogue ecosystem to
register in**, and that is structural rather than a gap in our research: Telegram has a public
username namespace and deep links, so third parties can build directories on top of it. WhatsApp
has neither, Meta runs no bot directory, and Click-to-WhatsApp is paid advertising.

**So the WA problem is not a missing catalogue. It is a missing front door, and two greps settle
it:**

1. **`wa.me`, `whatsapp.com/send` and `api.whatsapp.com` appear NOWHERE** in any `.py`, `.js` or
   `.json` in this repo. The developers page and the Mini App do not mention WhatsApp at all. The
   bot is live and there is no link to it on any surface we control.
2. **`relayshield_whatsapp_webhook.py` has no acquisition-source parsing.** The Telegram webhook
   reads an `SRC_` deep-link payload and logs `acquisition source=`; the WhatsApp handler has
   nothing equivalent. `consent_source="whatsapp"` is SIM-swap consent, a different thing. So even
   if a link existed, the arrival would be unattributable.

**THE ITEM: a `wa.me/<number>?text=` front door with a source token in the prefilled message**,
parsed the way `SRC_` already is, then placed on the developers page, the blog footer and the Mini
App. Roughly half a day. It makes WhatsApp measurable for the first time, and until it exists
**no number about WhatsApp arrivals means anything** -- the same rule this file applies to the
stolen-sessions table.

**Register nothing and place no link before the parsing exists.** A link that is sent, accepted
and never logged is the same false absence as a key that was never registered, which is FD-8 and
four months of it.

## tg.app: THE BLOG CHANNEL IS APPROVED. I READ THE WRONG SCREENSHOT FIELD.

**2026-09-16.** I reported the channel as Pending. It is **Approved**, and the banner on the
current page names it directly: *"RelayShield Blog | Crypto Scam Alerts is now live in the TG.app
catalog."*

**The reading that produced the error is worth keeping even though the conclusion was wrong.** On
the earlier screenshot the green banner described the MINI APP and the channel's own row said
Pending, so the banner and the row disagreed. The correction is not "trust the banner" but
**check the row for the thing you are asking about, and check it again if the page has been
reloaded since** -- a status field moves and a screenshot does not.

**Two RelayShield listings are now live on tg.app:** the Mini App (`Scam Checker | RelayShield
IDCheck`) and the channel (`RelayShield Blog | Crypto Scam Alerts`). That confirms what the
one-listing-per-bot section predicted: `t.me/RelayShield` is a different username from
`t.me/relayshield_bot`, so the channel never contended for the Mini App's slot.

**The baseline is due NOW rather than on approval**, because approval already happened:

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --snapshot before-tgappblog

It REFUSES to overwrite, so a late one cannot quietly become a comparison of a number with itself.

## BUNDLE B WAS NEVER GATED BEHIND THE IAM SPLIT. I READ THE WRONG ROLE.

**2026-09-17, asked as "which is higher priority, AWS Bundle B or the OpenAI plugin
marketplace".** Answering it meant reading Bundle B's blockers, and one of the two was
mine and was wrong.

`bundle_b_scope_2026-09-15.md` said the catalog grant (`DescribeEntity`, `ListEntities`,
`StartChangeSet`) was an IAM change on **`relayshield-breach-check-role-1sapnwdl`** -- 26
inline policies at 10,127 of 10,240 bytes, 11 of 10 managed slots -- so a customer-managed
policy on a role already over its cap. That reads as *Bundle B is gated behind the IAM
split*, which is a week of work in front of a revenue item.

**A change set is not a runtime operation, and that role is the runtime role.** The
fulfillment Lambda needs `ResolveCustomer` and `MeterUsage` at runtime and HAS both.
`.github/workflows/marketplace_dimension.yml:64` assumes
`role/relayshield-github-deploy`, and that is the identity that calls `StartChangeSet`.

**`tools/apply_marketplace_catalog_policy.sh` already exists, already targets
`relayshield-github-deploy`, and has simply never been run.** Its own header explains why
it is operator-side and once: a role cannot widen its own permissions, so the first grant
cannot happen inside Actions. So the blocker is one command, not an IAM migration.

**Third occurrence of the repo half of a policy being mistaken for the AWS half**, after
`apply_deploy_invoke_policy.sh` twice and the Stars grant that measured closed. And it is
the Bundle-A-entity mistake one directory over, in the same document that confesses to it:
**a claim about a permission names the ROLE it was read from**, exactly as a claim about a
product names the entity id. The repo holds a snapshot of one role and a workflow naming a
different one, and reading only the first is how "not granted" becomes "cannot be granted".

## SUBMITTING THE BOT TO DIRECTORIES WAS UNMEASURABLE. CAUGHT BEFORE THE LINKS SHIPPED.

The Mini App has five catalogue submissions and **@relayshield_bot has none**, so bot
directories are the obvious next surface. Checking what would count them found nothing:

* `tools/miniapp_funnel.py`'s BOT stage is
  `re.compile(r"acquisition source=(miniapp|tg-miniapp[a-z-]*)")` -- Mini App arrivals and
  nothing else, by design.
* `tools/source_arrivals.py` hard-coded `/aws/lambda/relayshield-developer-signup`, and a
  bot arrival is logged by the TELEGRAM webhook.

**Five submissions would have produced one number nobody could split.** That is the
`tg-miniapp-channel` defect and FD-8's, arrived at from a third direction.

**THE TWO SURFACES ATTRIBUTE DIFFERENTLY AND GETTING IT BACKWARDS COSTS A ROUND.** A Mini
App link carries `?startapp=<key>` and the Worker GATES it: an unregistered key is
silently downgraded and logs `unmatched:`, which is recoverable later because the
unmatched row names it. A bot link carries `?start=SRC_<key>` and
`relayshield_telegram_webhook.py` has **no allowlist** -- any key up to 32 characters is
lower-cased and logged verbatim. So **a bot key needs no registration in
`ALLOWED_SOURCES`, `_SOURCE_ALIASES` or `_SOURCE_BANNERS`**, and putting one there
measures nothing because the bot never reads those tables. **On this surface the
unrecoverable mistake is OMISSION**: a listing pointing at a bare `t.me/relayshield_bot`
logs nothing, leaves no unmatched row, and is indistinguishable from organic `/start`
traffic forever.

`tools/source_arrivals.py --surface bot` reads the webhook's log group, and
`bot_directories.json` is the route table. **One tool with two surfaces rather than a
second counter**, because two files that must agree with nothing checking that they do is
this repo's most-repeated defect and a second counter would have drifted from this one's
doctrine while both kept printing numbers.

**The guard reads the filter out of the TOOL and matches it against the line the handler
ACTUALLY WRITES**, both sides parsed rather than retyped, and the bot-surface report
refuses to render a zero as a dead channel -- it names the failure that looks identical.
16 tests, and the funnel's own historical defect (a filter written against the `SRC_`
payload rather than the logged line) was reintroduced to prove they fire.

## FD-14: THE RULES ARE PARTLY READ NOW, AND THERE ARE TWO GATES NOBODY HAD NAMED

FD-14 has said "ROUTE OPEN, RULES NOT READ" since 2026-09-08, with step one being the
read. `developers.openai.com` and `platform.openai.com` are **egress-blocked** from the
container (WebFetch refuses the domain outright, curl returns 000), so this is read from
search results quoting their pages and is **secondary evidence** -- which is precisely how
`@app_moderation_bot` cost three rounds, so it is labelled rather than promoted.

**Two things it surfaced, and both are gates rather than tasks:**

1. **Identity verification in the OpenAI Platform Dashboard is a PREREQUISITE**, business
   verification to publish under a business name. That is Andrew's, it has its own
   latency, and it blocks the submission rather than the build.
2. **Selling digital goods, subscriptions or in-app services is NOT YET ALLOWED**, and
   the documented link-out-to-your-own-site route is scoped to PHYSICAL goods.

**The second one is the Telegram Stars trap with a different host's name on it.** This
file already records that wiring "upgrade" from inside a Mini App to Stripe or x402 for a
digital good is the route that gets a bot restricted. A pay-per-call API sold inside a
ChatGPT app is the same shape. **The keyless half is unaffected** -- `/v1/link-check` and
`/v1/wallet-risk` cost us nothing and sell nothing -- so a listing built on those is
compliant, and the paid rails stay outside the host, reached the way every other API
customer reaches them.

**So FD-14 is a listing of the free checks or it is a compliance problem, and that is
decided BEFORE any submission metadata is written.**

## FD-12 IS BUILT AND, AS FAR AS THIS REPO KNOWS, NEVER SUBMITTED

`FRONT_DOORS.md` has carried FD-12 as **ROUTE OPEN, ARTEFACT BUILT** since 2026-09-05:
the plugin and the marketplace manifest both exist, both pass `claude plugin validate`,
`test_agent_bait_skill.py` pins them, and the submission form is named
(<https://clau.de/plugin-directory-submission>). FD-13 next to it says **SUBMITTED, PR
#612**. The difference between those two words is a form.

**A doc recording an open item is a LEAD, not a fact**, in this direction as much as the
other, so this is a question rather than a finding: if it was submitted, the row is stale
and should say so. If it was not, it is the cheapest open item on the board -- finished,
tested work sitting behind a form, against the directory whose artefact we already ship.
## EVERY DEV.TO POST SHIPS A GENERATED FILE. THE SCRIPT SENDS IT. NEITHER HALF IS OPTIONAL.

**Written 2026-09-17 at Andrew's request, after the GitLab post reached DEV's web editor with its
front matter rendering as visible text** -- the exact failure recorded on 2026-09-07, repeated ten
days later, and the cause was mine and was NOT the paste.

**THE RULE THAT ALREADY EXISTED SAID "NEVER THE WEB EDITOR" AND HAD NO ARTEFACT BEHIND IT.** The
channels doc for that post carried the front matter in a ```yaml block and the sentence *"publish
with tools/publish_devto.py, never the web editor"* -- and **no file was ever generated for the
script to send.** So the instruction forbade the only route that was actually available. A reader
holding a yaml block and a script that takes a filename has one move, and it is the forbidden one.

**So the rule has two halves now and the first is the new one:**

1. **THE GENERATED FILE EXISTS, in the same commit as the canonical.** `<slug>-devto.md`, generated
   FROM `blog_markdown/`'s published body rather than written by hand, so the two cannot diverge.
   A channels doc that describes front matter without committing a file has not delivered the
   dev.to channel, whatever it says.
2. **`tools/publish_devto.py` sends it.** `--dry-run` first, then `--publish`. The key comes from
   the environment via `read -rs`, never an argument.

**GENERATING IT IS FOUR MECHANICAL STEPS AND ALL FOUR MATTER:**

  * Take the body from `blog_markdown/<slug>.md`, never the root working copy -- that one still
    carries its `NOT FOR PUBLICATION` section, and `build_blog.py` does not strip it.
  * **Strip the leading `# ` heading.** It becomes DEV's `title` field, so leaving it in publishes
    the title twice.
  * **Switch the one `?source=` key to that channel's own**, `<key>-devto`. One key per
    DESTINATION, never per category.
  * Add a short runnable lead-in above the body. DEV's readers want the thing before the thesis.

**AND RULE 14 APPLIES TO A LEAD-IN EXACTLY AS IT APPLIES TO A PASTED BLOCK.** The first draft of
that lead-in said `rsscan install-hook`, **which does not exist.** I wrote it because it is what
such a command is usually called. Read from `scan.py` instead: `--staged` is the DEFAULT, so bare
`rsscan` reads `git diff --cached -U0`, and CI is `--rev-range A...B`. A wrong command in a pasted
block costs one reader a round trip; a wrong command in a published post is wrong for everybody who
reads it, forever, on a developers' site where being wrong about your own CLI is the whole
impression.

**Four tags maximum and they must already exist on DEV.** `security`, `devops`, `opensource` and
`ai` are the known-safe set. A tag that does not exist returns 422 naming it; drop it and re-run.

### rsscan TOLD INSTALLERS IT HAD 31 PATTERNS WHILE HOLDING 49

Found in the same turn, and it is the two-files-must-agree shape landing on the artefact a stranger
actually installs. Eight GitLab formats shipped on 2026-09-16 and neither sentence moved:
`rsscan/README.md` and the module docstring in `rsscan/rsscan/scan.py` both said 31, **beside a
provider list that named GitHub and did not name GitLab** -- in the same week we published a post
whose entire argument is that a detector reports only what it has a pattern for.

`PATTERN_COUNT` is already derived (`len(_COMPILED)`), so only the prose can drift.
`test_rsscan_stated_count.py` pins every `"<n> credential patterns"` string against it, pins the
README's prefix/severity table against the rules themselves in BOTH directions, and fails if the
guard ever scopes itself down to nothing. It deliberately does NOT strip comments: the thing being
checked IS prose.

**MY FIRST PROVIDER GUARD WAS DECORATION AND ITS OWN PROOF RUN SHOWED IT.** It searched the whole
README for "gitlab" and PASSED with the provider clause deleted, because the README also documents
a GitLab CI component -- so the word is present whatever the table holds. **Anchor a prose guard on
the SENTENCE that makes the claim, never on the file.** A word that appears for an unrelated reason
is a guard that cannot fail.

## THE WHATSAPP FRONT DOOR IS BUILT, AND THE NUMBER IS THE ONE THING A SESSION CANNOT FILL IN

**Built 2026-09-17. The on-deck item recorded on 2026-09-16 said the WA bot had no front door and
no attribution, and both halves shipped together, deliberately.** A link placed before the parsing
exists is a key that is sent, accepted and never logged, which is FD-8 and four months of it.

**WHATSAPP HAS NO USERNAME NAMESPACE AND NO DEEP-LINK PAYLOAD.** Telegram hands
`t.me/<bot>?start=SRC_<key>` to the handler as a payload. The only thing WhatsApp offers is
`wa.me/<number>?text=<prefill>`, which puts the token in the MESSAGE BODY -- visible to the user,
editable by the user, and arriving as ordinary text. `parse_wa_source()` therefore tolerates
`SRC-` as well as `SRC_`, is case-insensitive, and **STRIPS the token from the body**, because the
prefill IS the user's first message and anything after the token is a real instruction our command
parsing has never seen prefixed.

**THE ORDERING IS THE WHOLE BUILD AND IT IS EASY TO GET BACKWARDS.** A front-door arrival is BY
DEFINITION a number we have never seen, and `handler()`'s `if not user` branch sends a welcome and
returns 200. **So a parse placed after `get_user_by_whatsapp()` attributes every arrival the link
ever produces to nothing, forever, while reading perfectly in a diff.** It is the only defect here
that running the code cannot reveal -- both orderings pass every behavioural test, because those
test the parser in isolation -- so `test_wa_front_door.py` checks source ORDER inside the handler,
proven by moving the call.

**THE UNKNOWN-NUMBER REPLY WAS A DEAD END AND IS PART OF THE DOOR.** It said *"your account isn't
set up yet, visit relayshield.net"*. Bouncing a stranger to a website one message after they tapped
our own link is worse than having no link: they came to ask about something and we answered with
homework. It leads with what the bot does now. **It still cannot run a check for them, and saying
so plainly is the honest scope** -- the keyless WA check is the next build, not this one.

**THE NUMBER LIVES IN SECRETS MANAGER AND NOWHERE ELSE, AND NO SESSION CAN READ IT.**
`relayshield/twilio_whatsapp_number`, read at runtime by six handlers, hardcoded by none. So
`WA_NUMBER` in both Workers is the EMPTY STRING and **each renders no link at all while it is
empty.** That is not a placeholder to tidy up later, it is a fail-closed:

**wa.me ANSWERS A MALFORMED OR MISSING NUMBER WITH HTTP 200 AND AN "INVALID" PAGE, NOT A 404.** So
a broken front door looks live to every probe we own -- the quiet alarm, on the link itself. Bare
digits only, no `+` and no spaces. Fill both from:

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/wa_front_door_link.py

It is read-only, prints the number and never the raw SecretString, and **refuses to print a link
for anything that is not E.164** rather than emitting one that would pass a probe and reach nobody.

**AND THE GUARD I WROTE FOUND A SECOND RAW PHONE NUMBER I HAD MISSED.** `handler()` logged
`from_number` in the clear into CloudWatch on every inbound message, and a second line logged it
again on every handled message. A phone number is personal data and log retention is not where we
get to decide it stops being that; every other identifier in that file is hashed or encrypted and
these two were the exception because they were written first. Both hashed, and an `ast` test now
fails on any `logger` call passing `from_number` raw.

**Two constants that must agree**, `WA_NUMBER` in `cloudflare_worker_blog.js` and in
`cloudflare_worker_miniapp.js`, are pinned equal by test. The Mini App takes it through a
`__WA_LINK__` substitution rather than reading the Worker constant from page scope -- the
`INLINE_TEXT` defect, which `node --check` cannot see.

**`tools/miniapp_funnel.py` HAS A WHATSAPP STAGE NOW**, filtered on the line the code actually
writes rather than on what it ought to write. Its zero-means note says the thing that will
otherwise cost a round: **a zero here is more likely to be an unset `WA_NUMBER` than an unpopular
link.** Check the constant before the channel.

## BOTSARCHIVE IS A REAL DIRECTORY THAT ALSO SELLS POSTS. THE FREE HALF IS WORTH TAKING; THE POST IS $408.

**Asked 2026-09-17 as "is this legit and should I sign up our Tg bot and/or our miniApp".**

**It is real, and it is BOTH KINDS OF THING AT ONCE**, which is why the 2026-09-14 rule (*"a curated
catalogue with a submission route, or a broker selling posts"*) needs its correction recorded here:
**those two categories are not exclusive.** `@telegtapps` was purely a broker. BotsArchive runs a
genuine database with a website and a search bot AND sells advertising in its channel.

Measured rather than recalled, from third-party trackers because `botsarchive.com`, `t.me`,
`tgstat.com` and `telega.io` are ALL egress-blocked from the container:

    channel subscribers      ~110,000-112,800   (four trackers, consistent)
    average post reach       ~6,100 views       engagement ~5.5%
    advertising post price   $408 on Telega.io  category "Directory of Channels & Bots"

**SO THE "ACTION REQUIRED -- CONTACT @BotsArchiveSupportBot TO PROCEED WITH THE LISTING" STEP IS
VERY LIKELY THE FEE GATE, AND THAT IS AN INFERENCE, NOT A MEASUREMENT.** A free submission that
passes moderation and then requires a support conversation "to proceed", on a channel with a
published $408 ad rate, is the shape of a paywall. **It has NOT been confirmed.** Nothing found
suggests deception either -- selling posts in your own channel is an ordinary business, and no
complaint, scam report or payment dispute turned up against them anywhere.

**THE RECOMMENDATION, AND IT IS A SPLIT BECAUSE THE PRODUCT IS TWO PRODUCTS:**

* **The website database entry: take it if it is free.** A directory row is a standing shelf that
  keeps returning arrivals, which is the whole reason the 2026-09-14 finding ranks a listing above
  a channel post.
* **The $408 channel post: NO, and this is my call to be overruled.** That is about 6.7 cents per
  view of an audience that collects Telegram bots. They are not people with money at risk, which is
  who buys identity monitoring, and the catalogue work already in flight has produced four
  submissions and a live listing for nothing. **Spend the $408 only after a free listing has
  produced measurable arrivals**, which is a thing we can now count.
* **Ask the price outright in the first message, before anything else.** "Is a channel post
  required for the database listing, and what does it cost?" A support bot that answers with a
  figure has settled it; one that does not is the answer too.
* **The Mini App is a SEPARATE submission and should not be bundled into this conversation.**
  BotsArchive archives BOTS. tg.app already taught us that a catalogue keys on the bot username,
  so a Mini App and its bot can collide into one slot -- ask which they list before submitting the
  second thing.

**REGISTER THE `?source=` KEY BEFORE ANY OF IT.** `SRC_botsarchive` already parses on the Telegram
side (the SRC_ prefix exists precisely because "BOTSARCHIVE" is 11 characters of A-Z and would
otherwise hit the Coinbase charge-code branch -- that comment has been in the webhook since
2026-08-10). Take the `--snapshot before-botsarchive` baseline BEFORE the listing goes live, never
after.

## OMARCHY: THE ANGLE IS REAL AND I RECOMMEND NOT BUILDING IT. THE INTERESTING PART IS A POST.

**Asked 2026-09-17: "is there a RS angle here to build a desktop plugin".**

**WHAT AN OMARCHY PLUGIN ACTUALLY IS**, read from the marketplace's own README rather than inferred:
a public GitHub repository carrying a `manifest.json`, a README and a licence, installed by pointing
`omarchy plugin` at the URL. A bar widget is a Quickshell QML component loaded into a slot.

**AND THE MARKETPLACE SAYS IN ITS OWN WORDS THAT IT DOES NOT AUDIT THEM.** Plugins run
**unsandboxed** and "may access or modify files, settings, credentials, network resources, or other
parts of your system"; the marketplace performs "limited automated checks" which are explicitly
"not a security audit, certification, endorsement, or guarantee".

**THAT IS OUR THESIS ARRIVING IN A NEW REGISTRY, AND IT IS NOT A REASON TO SHIP A WIDGET.** Two
candidate builds, and I would take neither today:

* **A bar widget running our scam checks.** Weak. It is a QML component in a language nothing in
  this repo uses, for an audience that has to already want it, and a desktop widget does not reach
  the moment of need the way inline mode does.
* **Screening an Omarchy plugin repo before install.** Strong on fit and **nearly free**, because
  `.claude/skills/relayshield-agent-bait` already reads a GitHub repo's manifest, README and
  agent-facing files and checks every referenced domain against the corpus. An Omarchy plugin IS a
  GitHub repo with a manifest. The marginal work is a `manifest.json` reader and a README line, not
  a build.

**WHY STILL NO: rank a surface by how it performs for US, not in general.** Omarchy is a niche Arch
distribution whose users are the most technical audience available and the least likely to buy
identity monitoring, and this repo has already recorded that exact error once -- ranking the bot's
menu button top for a bot with almost no users.

**WHAT I WOULD DO INSTEAD, and it costs an afternoon rather than a week: a post.** "Your distro's
plugin marketplace says, in its own README, that it does not audit plugins. Here is what to read
before you install one." It reaches the Omarchy audience without building anything, it rests on a
primary source we have actually read, and it is the agent-bait argument we already publish aimed at
a registry that is currently describing the problem for us. Register `?source=omarchy` first.

**THE CONDITION THAT WOULD CHANGE THE ANSWER**, so this is not re-litigated on a hunch: a named
Omarchy plugin that turns out to be malicious, or a request from someone inside that community.
Either makes the screening case concrete rather than theoretical.

## WHERE 2026-09-17 LEFT THINGS — READ THIS FIRST. IT SUPERSEDES THE 2026-09-14 TOP 15.

### THE COMMAND THAT FAILED WAS NOT ON HIS MACHINE, AND THE TOOL HAD A SECOND DEPENDENCY

**Reported as "WA front-door: command failed" with no error text**, which is the
right way to report it and left me two candidate causes with different fixes.
`origin/main` was at `e2e9224` and the WhatsApp commit was `b641375`, **so the
file did not exist on his Mac.** That is the LOCAL MERGE IS NOT A PUSH rule, in
the direction where the block I sent was correct and the one he ran was the
second of two.

**AND I HAD GIVEN IT A SECOND WAY TO FAIL FOR A DIFFERENT REASON.** The tool
imported `boto3`, so `~/.rsvenv` had to exist and be populated before a one-line
question could be answered -- and the three failures (file absent, venv absent,
secret unreadable) are indistinguishable from the error text. It shells out to
the **AWS CLI** now, which every other command in this file already assumes, and
falls back to boto3 only if `aws` is absent. `--no-cli-pager`, per rule 9. A CLI
error is printed VERBATIM and the reading guide names ExpiredToken and
AccessDenied separately, because those have different fixes.

**THE GENERAL FORM, and it is rule 14 pointed at a dependency rather than a
command: every prerequisite a tool adds is another thing that can be the reason
it failed, and the reader cannot see which.** Prefer the dependency the reader
already has.

### WHATSAPP DOES HAVE A DIRECTORY. IT IS FOR CHANNELS, NOT FOR BOTS.

**This CORRECTS the 2026-09-16 on-deck note, which said "there is no WhatsApp
catalogue ecosystem to register in".** Half right, and the wrong half is the
half with the opportunity in it.

* **There is no directory for WhatsApp BOTS.** Meta runs none. That stands.
* **There IS a directory for WhatsApp CHANNELS** -- searchable inside the app
  from the Updates tab, browsable by category and country, and on the web at
  `whatsapp.com/channels`. Channels rank in their declared primary country, and
  the stated signals are category fit, follower growth in the first seven days,
  reaction rate per post, and post frequency. Meta has since added **Promoted
  Channels**, which is paid placement in that directory.

**SO THE WA DISCOVERY SURFACE IS A CHANNEL, AND THE BOT IS ITS DESTINATION.** It
is the exact shape that already works for us on Telegram: `t.me/RelayShield` is
the blog channel, it is now listed on tg.app, and it is a different username
from `t.me/relayshield_bot`. A WhatsApp Channel carrying scam alerts is
discoverable; the `wa.me/<number>?text=SRC_wa-channel` front door in every post
is what turns a follower into a conversation.

**THE THING TO CHECK BEFORE BUILDING IT, and it is the founder's read because
the container cannot see it:** a Channel is created from a WhatsApp account, and
ours is a **Twilio-hosted business number**. Whether that number can own a
Channel at all is the question that decides whether this is half a day or
impossible, and it is one look in the app. **Do not scope the work before that
read** -- FD-2 cost a day on a destination whose own page said no.

**And the measured caveat from the same reading: directory-only Channels grow
far slower than Channels whose link is on owned surfaces.** So the Channel is
not a substitute for the front door, it is a second surface that needs the same
link. Both, or neither is worth much.

### BOTSARCHIVE IS A DEAD END IN PRACTICE. STOREBOT IS THE LIVE ONE.

`@BotsArchiveSupportBot` did not answer. Combined with the $408 published ad
rate on that channel, the honest reading is that the free half is not staffed,
and **the recommendation from 2026-09-17 morning stands unchanged: do not pay.**
Nothing is lost -- the submission was free and produced no listing.

**`storebot.me/add-bot/` is the replacement and it is a plain web form**, which
is the web-front-door finding paying for itself a fifth time. Free, no payment
field, jpg/png/gif upload with a 256 MB cap, and it is one of the oldest
Telegram bot directories. Copy is committed at
`storebot_submission_2026-09-17.md`, field by field.

**THE BOT, NOT THE MINI APP, and the reason is the form rather than a
preference.** Its required fields are Bot Direct Link, Bot Status and Bot
Commands. A Mini App has no commands and no online state, so three fields would
be empty or invented. The Mini App is named inside Bot Info and reachable with
`/app`, so the listing costs us nothing there, and three catalogues already
carry `t.me/relayshield_bot/idcheck` directly.

**THE COLD START WAS CHECKED RATHER THAN ASSUMED**, which is rule C applied to
our own surface: `msg_welcome()` greets a stranger with what the product does
and an intent keyboard, and asks "Who are you protecting?" It does not demand a
phone number, an email or a payment first. A directory visitor lands somewhere
sensible, so the bot is a defensible thing to point a catalogue at.

**`storebot` IS REGISTERED IN ALL THREE PLACES BEFORE THE SUBMISSION**, with
`storebot-me` and `botsarchive` as aliases. It has its OWN banner rather than an
alias to `tg-miniapp`, because a Mini App arrival has already run a check and
that banner says so -- a directory visitor has run nothing, and a first screen
claiming otherwise is a false claim about the reader.

**AND THE FUNNEL HAS A DIRECTORY STAGE**, deliberately separate from the BOT
stage. That one answers "does the Mini App feed the bot" and its regex is
`(miniapp|tg-miniapp[a-z-]*)`; widening it to catch directory traffic would
destroy that answer to gain this one. **Two questions, two stages.**

### I INVENTED A COMMAND IN A PUBLIC LISTING, ONE TURN AFTER WRITING THE RULE

The first draft of the StoreBot copy advertised `/watch`, `/wascam` and
`/simswap`. **`/watch` does not exist at all**; the Mini App command is `/app`.
`/wascam` and `/simswap` are handler ALIASES that `setMyCommands` never
registers, so a reader typing them from our own public listing would be using
commands their Telegram menu does not offer.

**This is the `rsscan install-hook` failure, in the next turn after I wrote that
lesson into this file.** Writing a rule down is evidently not the same as
applying it. The list is now generated from `_BOT_COMMANDS_BASE` by `ast` --
that table is what `setMyCommands` actually registers, and a handler branch with
no entry in it is invisible to everyone who does not already know it exists.

**THE RULE, and it is narrower and more usable than "run it or label it": a
command list, a price, a version or a count going into a PUBLIC artefact is read
out of the code that defines it, mechanically, never typed from memory.** The
`ast` extraction took one command and would have caught all three.

### THE TOP 15, REGENERATED 2026-09-17

**Regenerated, not annotated. This supersedes the 2026-09-14 list.**

**Closed since then:** four catalogue submissions and two live tg.app listings;
the funnel's window parse; the TI demo cards and their unit; the SIM swap
port-out defect and its Telegram delivery; GitLab credential detection in all
three tables; the GitLab post published on every channel including dev.to;
inline mode pointed at from the blog footer and the Mini App; the WhatsApp
front door built.

1. **FILL `WA_NUMBER` AND MERGE. The WhatsApp front door is built and renders
   nothing until this is done**, deliberately, because wa.me answers a bad
   number with a 200 and an "invalid" page. Merge first, then
   `AWS_PROFILE=relayshield python3 tools/wa_front_door_link.py`, then paste the
   bare digits into `WA_NUMBER` in BOTH `cloudflare_worker_blog.js` and
   `cloudflare_worker_miniapp.js`. A test pins them equal.

2. **Submit the bot to StoreBot.** `storebot.me/add-bot/`, copy committed at
   `storebot_submission_2026-09-17.md`. Search their site for RelayShield first
   -- tg.app keys one listing per bot username and StoreBot may too. Take
   `--snapshot before-storebot` BEFORE it goes live.

3. **The WhatsApp Channel question, and READING IS THE TASK.** Can a
   Twilio-hosted business number own a WhatsApp Channel? One look in the app
   decides whether the only real WA discovery surface is available to us at all.
   Do not scope the build before that answer.

4. **IAM split, first migration.** The command is ready and the policy read.
   `AWS_PROFILE=relayshield python3 tools/iam_split_roles.py --from-snapshot iam/snapshots/relayshield-breach-check-role-1sapnwdl.json --only relayshield-intel-feed --apply`
   Verify with the next scheduled run's log, NOT the import probe. The shared
   role is at 11 managed policies of 10 allowed, so this is closer to forced
   than it looks.

5. **Deploy the TI demo Worker, recovery FIRST.** The cards are edited and
   unshipped. `sh tools/recover_live_worker.sh relayshield-ti-demo
   cloudflare_worker_ti_demo.js` runs before anything; only `IDENTICAL` makes
   the deploy safe. It is the one component with no automated path, so every
   live version was hand-pushed.

6. **`relayshield_bundle_fulfillment.py` first drift diff.** Seventh instance of
   source-in-repo, live traffic, no deploy path. In the drift check only.
   `sh tools/handler_drift.sh relayshield_bundle_fulfillment.py`. It holds
   `BUNDLE_CONFIGS` and `PRODUCT_CODES`, so Bundle B is blocked behind it.

7. **Batch 2 outreach addresses.** Two commands, both built, neither run.
   `export GITHUB_TOKEN=$(gh auth token)`, then `resolve_prospect_emails.py`,
   then `merge_prospect_emails.py`.

8. **CSM-SIMSWAP-2: the dApp Store listing copy.** A portal field, no review
   cycle, read by a buyer before installing. Before the EAS build.

9. **BOT-TOKEN-1 phase 1.** `getMe` liveness, hash-only storage, username
   indexing, severity split on liveness, and the `getUpdates` prohibition as a
   test. One day, gated on nothing.

10. **Map `relayshield_watchlist_monitor.py` in `deploy_lambdas.yml`.** In the
    drift check and the invoke policy, not the deployer, so
    `check_deploy_invoke_policy.py` prints it on every run. The mapping commit
    must touch the `.py`.

11. **Map `relayshield-mpp-settlement`**, same shape, same rule.

12. **FD-11: Smithery.** Two commands, still the cheapest open item.
    `npx -y @smithery/cli@latest auth login`, then
    `mcp publish <hf sse url> -n relayshield/relayshield`.

13. **Bundle D change set**, dimension AND listing copy in one submission, which
    is one AWS review cycle. Blocked on the role's catalog permissions.

14. **The Omarchy post**, if the marketplace angle is taken up: their own README
    says plugins run unsandboxed and that their checks are not a security audit.
    An afternoon, and it needs `?source=omarchy` registered first.

15. **INTEL-5.** `tools/diagnose_stolen_sessions.py`. Until it runs, no count
    out of `relayshield_stolen_sessions` means anything.

## THE WA FRONT DOOR IS POINTED AT TWO MORE SURFACES, AND THE NUMBER IS STILL THE GATE

**2026-09-17, second session of the day, extending `claude/laughing-bell-gxagsd` rather
than duplicating it.** That branch built the parser, the blog and Mini App links, the
funnel stage and the tool. Two placements it NAMED and did not build are now built:

* **`api.relayshield.net/developers`, key `wa-devs`.** It **reads the number from Secrets
  Manager at request time** rather than carrying a constant, and that is the design rather
  than convenience: a Cloudflare Worker cannot read Secrets Manager, which is the ONLY
  reason `WA_NUMBER` exists as a constant anywhere. This handler already reads three
  secrets. A fourth copy of the number would be a copy `--write` does not target and no
  test pins. `_wa_number()` never raises (a landing page that 500s over a footer link is
  worse than a missing line), unwraps the JSON secret (three of four call sites of the BOT
  TOKEN secret were dead for days because they did not, failing with a WRONG VALUE rather
  than an exception), and refuses anything outside 8-15 digits.
* **The `checkemail@` reply, key `wa-email`.** The highest-intent surface we have:
  somebody forwards a suspicious email, has no account, and the reply's only onward link
  is a website.

**THE SUBSTITUTION ORDER ON THE DEVELOPERS PAGE IS LOAD-BEARING AND ONE LINE FROM BEING
WRONG.** `<!--WA_FRONT_DOOR-->` IS an html comment, like `<!--REFERRER_BANNER-->`. Strip
the comments first and both placeholders are deleted, every later `.replace` matches
nothing, and the page renders perfectly with no banner and no front door while nothing
anywhere errors. A test asserts the ORDER, proven by inverting it.

**`tools/wa_front_door_link.py --write` fills every Worker constant in one pass.** Three
files to edit by hand and two of them enforced is the copy that drifts. It **refuses to
CREATE a `WA_NUMBER` line** and only replaces one that exists: appending a second `const`
declaration is a SyntaxError that stops the Worker deploying and names a line nobody
wrote. Verified by running it, including idempotency and `node --check` on all three.

**AND THE DIRECTORY COUNTERS ARE ONE LIST NOW.** Two sessions shipped bot-directory
counting the same day: a funnel stage hardcoding `(storebot|botsarchive)` and a route
table holding eight destinations. `_bot_directory_alternation()` reads the keys out of
`bot_directories.json`, so adding a destination is one edit, and a missing key raises
rather than matching nothing -- a regex that matches nothing is indistinguishable from a
channel that produced nothing. No loose suffix, deliberately: `storebot[a-z0-9-]*` would
swallow a future `storebot-paid` and merge two destinations into one number.

**`bot_directories.md` is GENERATED from the JSON** by `tools/bot_directories_md.py`. The
founder reads the markdown, the funnel counts from the JSON, and writing both by hand is
the two-files-must-agree defect with a new hat on.

**WHAT IS STILL NOT TRUE, and it survives my having been wrong about the code:** the
WhatsApp bot cannot run a check for somebody without an account. Telegram gives a stranger
keyless checks, inline mode in a group and the Mini App; WhatsApp has none of those. So
every link placed converts attention we already had rather than creating reach -- which is
fine, and is worth doing, and is not the same thing as a discovery surface. The next
WhatsApp build is a keyless first-contact check, roughly a day.

## TYPESAFE.AI: JOIN THE WAITLIST, SCOPE NOTHING, AND POINT IT AT ABS-1 IF IT ARRIVES

**Asked 2026-09-17.** TypeSafe left stealth 2026-09-15 with **Jev**, a "System One" model
returning TYPED decisions with a per-answer CONFIDENCE VALUE rather than text. Their own
launch numbers: 20-200x faster, 40-400x cheaper, $0.042/M input with output free.

**The fit is real and specific, which is why this is recorded rather than dismissed.**
`relayshield_intel_classifier.py` already invokes Claude Haiku through Bedrock and asks it
for APPROVE/REJECT plus a category from a channel record. That IS a typed decision over a
small piece of state.

**And the recommendation is still to build nothing**, for reasons that are about us rather
than about them:

* **There is no cost problem to solve.** That call runs on a backlog, not at request time.
* **That file's docstring states why Bedrock was chosen: "zero new vendor/secret".**
  Adding TypeSafe reverses a deliberate decision to buy a saving we do not need.
* **The speed and cost figures are their own launch materials**, and MEASUREMENT DOCTRINE
  applies to numbers quoted inward as much as outward.

**The one place worth pointing it when access arrives is ABS-1**, the unmeasured
agent-bait false-positive rate that gates the Bundle D dimension. A confidence-carrying
typed score is exactly what that verdict wants and it is off the customer path while it is
being measured. Half a day against an open item, not an integration.

## APIFY'S LIMIT EMAIL WAS ANSWERED BY THE DASHBOARD, NOT BY REASONING

**2026-09-17.** The "Maximum platform usage per month custom limit is expiring in 6 days"
email is a HARD CAP notice, not a bill: Apify suspends platform services rather than
charging on. The account carries a custom $10 where the Free default is $5, so the cap
halves when it lapses.

**Actual usage: $0.06 of $10.00, 0.2754 compute units.** 0.6% of the allowance, so neither
number is reachable and there is nothing to do. **Ignore it.**

**The founder settled it with one screenshot after I had written a section about how to
read two numbers in the console.** That is the right outcome and the cheap one: when the
answer is a number on a screen the founder can see and the container cannot, ask for the
screen rather than writing the procedure for reading it.

**The thing worth carrying is not the answer.** $0.06 a month on a Standby Actor says the
Actor is barely waking up, which matters for the Apify writers-programme article whose
whole premise is that we built and ran it. And nothing watches that Actor:
`tools/check_hf_space.py` probes both HF Spaces every six hours and there is no equivalent
here, so a dead Actor would reach us through a prospect.

## BUNDLE B'S CHANGE SET HAD NO DOOR. THE ARTEFACT WAS REAL AND NOTHING COULD SEND IT.

**2026-09-17, asked as "can you remotely publish our Bundle B license and prompt me to
run the E2E test AWS auditors require".** Answering the first half found the blocker.

`aws_marketplace/bundle_b_create_entity.json` has been written and guarded by six tests
since 2026-09-15. **The only submitter in the repo cannot send it.**
`tools/marketplace_add_dimension.py` opens with `ENTITY_ID = os.environ.get(
"BUNDLE_D_ENTITY_ID", "prod-kkvurtspreofy")`, calls `describe_entity` on it, and builds a
dimension change set FROM that capture. A `CreateProduct` names no entity, because AWS
assigns the id. So the tool's first action is the one thing this change set cannot
supply.

**Every check we had was checking the artefact.** Six guards on the JSON, all green, and
nothing asserted that a route existed to submit it. That is "a route added to the
handler's dispatch table is not a route" one layer out, and this time the missing half
was not at the gateway edge but in our own toolbox.

**`tools/marketplace_submit_changeset.py` is the door**, plus
`.github/workflows/marketplace_changeset.yml` because Actions holds the identity
`StartChangeSet` is called by. **A second workflow rather than a mode on the first**: the
Bundle D one reads the live entity, round-trips every field it is not changing, and
requires the ENTITY ID typed by hand, and all three are correct for MODIFYING a
published listing and meaningless for creating one. Folding them together means a mode in
which every one of those guards is skipped, which is the guard that gets skipped by
accident.

### THE ANSWER TO "REMOTELY" IS NO, AND THE REASON IS IAM WORKING CORRECTLY

`tools/apply_marketplace_catalog_policy.sh` has still never been run, and **it cannot be
automated**: a role cannot widen its own permissions, so the first grant is operator-side
by construction. Workflow dispatch is separately 403 for me. Two steps are the founder's
and no amount of tooling changes that.

### FOUR GUARDS IN THE SUBMITTER, AND ONE OF THEM WAS A FALSE POSITIVE I FIXED

It refuses a change set targeting `prod-kkvurtspreofy` or `prod-f5qkfsxlxs4qg` by name,
refuses an empty change set (a valid document that does nothing and returns success),
refuses `--apply` without a typed phrase, and refuses **any unsubstituted
`__PLACEHOLDER__`** -- rule 11 one layer out, where `<paste the key>` is a syntax error a
reader sees at once and `__BUNDLE_B_PRODUCT_ID__` is a string AWS accepts into a field.

**And the first version refused `UpdateVisibility`, which is the go-public step.** That is
the CSM-SIMSWAP-1 mistake exactly: a check that forces you to skip a legitimate step to
pass. Worse, its message named `marketplace_add_dimension.py`, **which cannot do
UpdateVisibility either**, so the reader was sent to a tool that would also refuse them.
Narrowed rather than loosened, and a test now pins BOTH directions: go-public validates,
and a visibility flip on a live listing is still refused.

### TWO GUARDS DID NOT FIRE ON THEIR FIRST PROOF AND BOTH WERE MINE

**The negation guard was satisfied by the defect.** It asserted `"not " in block` for the
direct-door condition, and rewriting `not key_record.get("aws_customer_id")` into
`key_record.get("aws_customer_id") is not None` -- the inversion that bills an AWS
customer on the AWS rail AND the Stripe rail for the same call -- left it GREEN, because
`is not None` contains `not `. **A substring the defect also satisfies is not a guard.**
It asserts the exact negation now.

**And one proof was a no-op I nearly recorded as a pass.** The edit meant to introduce a
dimension-key drift used two spaces where the file has three, so nothing changed and the
suite was green for the right reason and the wrong one. **Reading "OK" after a proof step
proves nothing unless the edit is confirmed to have applied.**

### THE E2E TEST IS A REAL SUBSCRIPTION, AND BUNDLE A ALREADY SHOWS ITS SHAPE

`aws_marketplace/bundle_a_test_offer.json` is the vehicle, and reading it answered the
question better than any doc could: a private offer targeted at ONE buyer account
(`442429445748`, not the seller account), granting the Entitled dimension once and pricing
every metered dimension at `0.00000001` -- free in practice and **non-zero on purpose, so
BatchMeterUsage is genuinely exercised rather than skipped.** Subscribe, get redirected to
the fulfillment URL with `x-amzn-marketplace-token`, resolve, provision, meter, THEN ask
for public visibility.

`bundle_b_test_offer.json` is built from that accepted envelope with four fields changed
rather than retyped. **Its ChargeDate is a placeholder and Bundle A's is not:** that file
carries `2026-08-08`, correct on the day and a date in the PAST for anyone since, and a
payment schedule in the past is rejected. The submitter fills it at send time and prints
the date it used. A test fails if a literal date is ever committed there.

**AWS's own validation requirements were NOT read**: `docs.aws.amazon.com` returns 000
from the container. So the sequence is derived from our own accepted artefact, which is
strong evidence and is not the same as their published bar, and the runbook says so where
a reader will hit it rather than in a footnote.

### AND THE DRIFT READ UNBLOCKED THE THING EVERYTHING ELSE WAITED ON

`sh tools/handler_drift.sh relayshield_bundle_fulfillment.py` came back **NO DRIFT, live
byte-identical to main**, LastModified 2026-08-07. That is the stale case, so the rule
applies in the direction that allows action: map it. It is now in `deploy_lambdas.yml`'s
`paths:` trigger, `LAMBDA_MAP` and the dispatch list, and `iam_github_deploy_invoke.json`
gained its ARN, which is 27 mapped functions all invocable.

**No `ci.import-probe` early return is needed and that was checked rather than assumed**:
the probe payload has no `Records` and no `path`, so it falls through to a real
`{"statusCode": 404}`, which is all the probe asserts. Same reasoning as the Discord bot.

**The Bundle B code ships INERT**, and that is what makes it safe to deploy before the
product exists. `BUNDLE_B_PRODUCT_CODE` is an env var defaulting to the empty string and
`PRODUCT_CODES` filters empties, so the file behaves exactly as it does today until AWS
assigns an id. The same pattern Bundle A already used, and the reason step 3 of the
runbook can precede step 5.

**ONE TRAP NAMED BEFORE IT FIRES, because predicting a failure and shipping it anyway is
worse than not predicting it:** `update-function-configuration --environment` REPLACES the
whole variables block. Setting `BUNDLE_B_PRODUCT_CODE` with a bare command **deletes
`BUNDLE_A_PRODUCT_CODE` and `BUNDLE_D_PRODUCT_CODE`** if they are there, and Bundles A and
D stop resolving with no error until a customer subscribes. The runbook reads the existing
block first. It is the change-set lesson in a different API: **it replaces, it does not
merge.**
