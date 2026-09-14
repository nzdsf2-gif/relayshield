# Mini App catalogue submission: the corrected running order, and the @app_moderation_bot question

**Session 2026-09-14.** Written in answer to two questions: summarise the Top 15, and am I certain
`@app_moderation_bot` is dead.

---

## PART 1. AM I CERTAIN `@app_moderation_bot` IS DEAD? NO. AND THE FILE SAYING SO IS MINE.

**Short answer: no, I am not certain, and I should not have written it as a finding.**

CLAUDE.md currently reads *"`@app_moderation_bot` DOES NOT ANSWER `/start` ... A bot that does not
answer /start is dead."* That sentence has two halves and only the first is evidence.

* **What is measured:** you opened it twice, on mobile and on desktop, and got no reply. That is a
  real observation and I am not disputing it.
* **What is inference:** that silence means dead. I wrote that, in the same section that criticises
  me for naming the bot on four secondary sources without reading the destination's own page. I then
  drew a second conclusion from a single symptom, which is the same defect one paragraph later.

### WHAT I CHECKED TODAY, AND WHAT IT CHANGED

Egress from the container, re-tested rather than recalled (the BLOCKED SOURCE WAS REACHABLE ALL
ALONG rule says to re-try before recording anything as unreachable):

    t.me                  BLOCKED
    tapps.center          BLOCKED
    builders.ton.org      BLOCKED
    medium.com            BLOCKED
    core.telegram.org     BLOCKED

So I still cannot probe the bot, and that has not changed. **What did change is the weight of the
evidence on the other side.** Three independent sources, one of them the TON Studio blog that
introduced tApps Center, describe the Apps Moderation Bot as the current submission mechanism, and a
developer write-up from this year describes a COMPLETED listing through it with moderation taking
3 to 8 days. Somebody got in that way recently.

**A live bot and your two silent attempts are not contradictory.** Ranked by likelihood:

1. **It needs a deep-link start payload.** Submission bots are commonly entered from the catalogue or
   the website as `t.me/app_moderation_bot?start=<token>`. A bare `/start` typed from search hits a
   handler that expects a payload and returns nothing. This is the most likely reading and it
   explains mobile and desktop failing identically.
2. **The flow moved to the web** and the bot is now a legacy entry point kept alive but silent.
3. **Wrong username.** A squatter or a rename. A registered-but-abandoned username still opens a chat.
4. **Genuinely dead.**

### THE ONE OBSERVATION THAT SEPARATES THEM, AND IT COSTS YOU TEN SECONDS

When you opened `t.me/app_moderation_bot`, did Telegram show **a START button and a bot description
or profile photo**, or **an empty chat with nothing in it**?

* START button and a description present means the username is a live registered bot and we are in
  case 1 or 2, which is a routing problem and not a dead channel.
* Nothing at all, or "user not found", means case 3 or 4 and the name is wrong or abandoned.

I cannot see this from here and no amount of searching substitutes for it.

### AND THE RECOMMENDATION DOES NOT DEPEND ON THE ANSWER

This is the part worth acting on regardless: **the bot is not on the critical path any more.** See
Part 2. We should not spend a fifth round on tApps before something easier has actually worked.

---

## PART 2. THE RUNNING ORDER CHANGES. FINDMINI GOES FIRST, NOT miniTELEGRAM.

The Top 15 says miniTelegram first, because its flow was "described rather than inferred". Today's
reads beat that, and the correction is in our favour.

**`https://www.findmini.app/submit/` is a plain web form at a named URL.** No bot, no sign-in
ceremony, no deep link. Their own stated terms: free, new apps usually listed **within 24 hours or
less**, `support@findmini.app` for corrections, and a published exclusion list (no scams, clones,
18+, gambling, get-rich-quick). We are none of those.

That makes it strictly cheaper than both alternatives and it settles the open question -- can we get
listed in a catalogue at all -- inside a day, with no dependency on the bot mystery.

**Corrected order:**

| Rank | Catalogue | Route | Attribution key |
|---|---|---|---|
| 1 | **FindMini** | `https://www.findmini.app/submit/`, web form | needs a NEW key, see below |
| 2 | **miniTelegram** | `minitelegram.com`, sign in with Telegram, app card, team review | **has none, must be registered first** |
| 3 | **tApps Center** | unresolved, see Part 1 | `tg-miniapp-tapps`, registered |

### A DEFECT IN OUR OWN ROUTE TABLE, FOUND WHILE CHECKING THIS

`miniapp_routes.json` rank 4 is `tg-miniapp-findminiapp`, and its destination is the **Telegram
channel `@findminiapp`, 56,380 subscribers**. The web directory `findmini.app` is a **different
destination**: a standing listing rather than one broadcast impression, with a different lifetime and
a different question attached to it.

Submitting the directory under the channel's key merges them into one number, which is the
`tg-miniapp-channel` defect this table was rebuilt to remove. **The directory needs its own key** and
I have not added one yet, because per the three-lists rule a key must land in `miniapp_routes.json`,
`ALLOWED_SOURCES` in the Worker and `_SOURCE_ALIASES` on the landing page in the same commit, and
that is a code change I would rather make deliberately than bolt onto a document.

**UNVERIFIED:** whether `@findminiapp` the channel and `findmini.app` the site are the same
operation. Their bot is `@findminiappbot`, which suggests yes. It does not change the recommendation
either way, because two surfaces still want two keys.

### TWO tApps PREREQUISITES, CHECKED IN THE CODE RATHER THAN ASSUMED

tApps states two gates before submission. Both pass:

* **"Your bot replies to /start in English by default. Telegram checks this."** `handle_start` exists
  in `relayshield_telegram_webhook.py` with a normal English welcome, plus deep-link payload branches
  for Helio, acquisition source and legacy Coinbase codes.
* **"A basic Terms of Use and Privacy Policy."** Both exist as Workers: `cloudflare_worker_terms.js`
  on `terms.relayshield.net` and `cloudflare_worker_privacy.js` on `privacy.relayshield.net`.

**One thing to check before pasting those into any form.** The Worker routes serve
`terms.relayshield.net` and `privacy.relayshield.net`, while code elsewhere references
`https://relayshield.net/terms` and `https://relayshield.net/privacy`. Those are different
hostnames and one pair may 404. A moderator will click them.

**A third tApps rule is worth noting because it is a fit rather than a problem.** If an app uses
crypto it must be **TON-only, no other chains**. Our Check tab already refuses Ethereum, Solana and
Bitcoin by design, for Telegram TOS reasons. That decision now pays for itself at the catalogue door.
Their TON Connect requirement is about wallet connection, which we do not do at all, so it should be
N/A.

### AND ONE ORDERING RULE THAT IS EASY TO GET BACKWARDS

**Opening the deep link yourself logs nothing.** The counter reads `source=` lines in
`/aws/lambda/relayshield-api`, and opening the app calls nothing there. **Pressing "Check it" does.**
So verify the link works BEFORE taking the baseline. A self-visit inside the baseline is harmless;
the same visit after it becomes part of the delta.

Take the baseline with `--snapshot before-<id>` and never overwrite it afterwards.

---

## PART 3. THE TOP 15, AS IT STANDS TODAY

Regenerated 2026-09-14, unchanged by this session except item 1's running order above.

**Closed since 2026-09-09:** the watchlist is mapped in the deployer and the drift check; Stars is
proven end to end by a real purchase; the Stars IAM grant is measured closed; the funnel works; the
Watching tab can add a watch; the developer route is built and discoverable; CSM-SIMSWAP-1's copy is
corrected; BOT-TOKEN-1 phase 0 has shipped; the IAM snapshot is committed and the first migration is
chosen.

1. **Register the Mini App in a catalogue.** Web front door first. **Order corrected this session to
   FindMini, then miniTelegram, then tApps.** Register the `?source=` key before submitting, and take
   the baseline before the submission rather than after. Your explicit priority, and it overrules a
   recommendation I made to deprioritise it.
2. **IAM split, first migration.** `relayshield-intel-feed`, 5 statements, 1,124 bytes. The command
   is ready and the policy has been read. Verify with the next scheduled run's log, NOT the import
   probe, which returns before touching DynamoDB. Do not migrate a second function until rows are
   written.
3. **Batch 2 outreach addresses.** Two commands, both built, neither run. The merge writes a
   send-ready file where every draft carries a To: line and unreachable rows are parked, not hidden.
4. **CSM-SIMSWAP-2: the dApp Store listing copy.** A portal form field, no review cycle, and it is
   what a buyer reads before installing. Do it before the EAS build.
5. **The funnel's Insights IAM grant.** `logs:StartQuery`, `logs:GetQueryResults`, `logs:StopQuery`
   on `relayshield-deployer`. UNVERIFIED whether it already has them; the tool names a refusal rather
   than reporting a zero.
6. **CSM-SIMSWAP-1 proper: the enrol call.** About 3 days. `enrollSimSwap` posting
   `/v1/sim-swap/enroll`, not `/v1/metered/sim-swap`, the carrier authorization clause gating the
   button, `withdrawSimSwap`, and Expo push as a delivery channel on the monitor.
7. **BOT-TOKEN-1 phase 1.** `getMe` liveness, hash-only storage, username indexing, severity split on
   liveness, and the `getUpdates` prohibition as a test. One day, gated on nothing. Phase 2 is gated
   on a non-zero corpus count, not a date.
8. **Map `relayshield_watchlist_monitor.py` in `deploy_lambdas.yml`.** The mapping commit must touch
   the `.py`.
9. **Map `relayshield-mpp-settlement`**, same shape, same rule.
10. **FD-11: Smithery.** Still two commands, still the cheapest open item.
11. **Bundle D change set**, dimension and listing copy in one submission.
12. **Apify: the form is open now.** The article must NOT appear on blog.relayshield.net first.
13. **ABS-1: the measured agent-bait false-positive rate**, which gates the dimension in item 11.
14. **INTEL-5.** `tools/diagnose_stolen_sessions.py`. Until it runs, no count out of
    `relayshield_stolen_sessions` means anything.
15. **The Commerce Agents post.** Register `?source=commerce-agents` first.

---

## SOURCES READ TODAY

All via search result summaries; every destination page itself is egress-blocked from the container,
which is why the browser reads in Part 2 are yours and not mine.

* TON Studio blog introducing tApps Center, which names the Apps Moderation Bot as the mechanism.
* Adsgram's tApps Center write-up, which records that tApps is built by TON Studio and is **not
  affiliated with Telegram Messenger**. Worth knowing: it is a TON ecosystem catalogue, curated, and
  not every app is listed.
* A 2026 developer account of a completed tApps listing, giving the 3 to 8 day moderation window and
  the /start and Terms prerequisites.
* FindMini's own submit page and business pages, giving the form URL, the 24 hour turnaround, the
  support address and the exclusion list.
* miniTelegram's FAQ, giving the sign-in-with-Telegram submission flow.

**One thing I nearly got wrong and caught.** `tapps.center/management` turned up as an indexed page
and looked like a developer dashboard. It is not. It is one of four CATEGORY pages (Management, Web3,
Utilities, Games). Had I shipped it as the front door it would have been a fifth wasted round.
