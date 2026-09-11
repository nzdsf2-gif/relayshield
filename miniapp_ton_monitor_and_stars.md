# The TON monitor, Stars, pinning, and whether the Mini App is a discovery surface

2026-09-11. Everything below is built, tested and pushed to
`claude/tg-miniapp-rs-ide-widget-ltz7e3`. Nothing here is a plan.

---

## 1. The merge failure, reproduced and fixed

Three identical failures across two turns, and it was a loop I built rather than a stubborn
problem.

`git add -A` staged your two embedded git repositories (`ansible-relayshield`,
`relayshield-snap`) as gitlinks. `git stash --include-untracked` **cannot stash a nested git
repo** -- it prints "No local changes to save" and leaves them. A fast-forward merge survives
that; a three-way merge does not, and every merge from now on is three-way because `origin/main`
already carries a merge commit. The failed merge partly unwinds the index, so a second run of a
block *without* `git add -A` would have worked -- but the block had `git add -A` at the top, so
each run re-created the condition that made the previous one fail.

Reproduced byte for byte in a scratch repo, including the two `rmdir` warnings. The fix is one
line, verified end to end and idempotent:

    git rm -rf --cached -q --ignore-unmatch ansible-relayshield relayshield-snap

`--cached` touches only the index. **The embedded repos and their history are untouched on
disk** -- confirmed by reading their git log after the merge.

**The permanent fix is yours to choose and is one command:**
`mv ~/dev/relayshield/ansible-relayshield ~/dev/relayshield/relayshield-snap ~/dev/`.
A repo inside a repo will keep generating this class of problem however many lines the block
carries. Until then the line above handles it.

---

## 2. The TON monitor

`relayshield_watchlist_monitor.py`. TON only, per Telegram's rules and your instruction.

**Eight signals, every one a case where money is on the line, and every one a CHANGE rather
than a state** -- a target that has always been flagged produces silence forever, which is what
keeps the bot unmuted:

| Signal | Fires when | Level |
|---|---|---|
| `IOC_LISTED` | the address appears in our criminal-channel corpus | critical |
| `SCAM_FLAGGED` | TON's community database flips `is_scam` | critical |
| `LIQUIDITY_GONE` | the token had a pool and now has none | critical |
| `LIQUIDITY_DRAIN` | pool depth falls below 40% of what it was | critical |
| `PRICE_COLLAPSE` | price falls below 20% of what it was | high |
| `BALANCE_DRAINED` | a wallet holding >1 TON falls below 10% | high |
| `CONTRACT_DEPLOYED` | an uninitialized address is now running code | medium |
| `VERDICT_WORSENED` | the upstream verdict rose for any other reason | varies |

That covers wallet, jetton/token, NFT collection and DeFi vault, because all four are accounts
on TON and `tonapi`'s account endpoint classifies and flags all four.

**Three rules that must not be relaxed.** Each was proven by reintroducing the defect and
watching the test fail:

1. **The first run against a row never alerts.** Rows written before the monitor existed carry
   no snapshot, so every signal would read as changed-from-nothing and the first scheduled run
   would message every user about every target at once. That is how a security bot gets
   *reported*, not uninstalled.
2. **Improvements are recorded, never sent.** An alert is for action.
3. **"We could not check" never renders as "it is gone."** An upstream outage that reads as an
   emptied pool sends a false rug alert. Every unreadable number is `None`, never `0`, and a
   failed lookup leaves the stored snapshot untouched.

**Six hours between runs.** A rug happens in minutes and no polling interval catches that, so
the honest job is "you find out the same day without opening the app", not "we beat the
attacker". Anything tighter multiplies the vendor bill for a promise we could not keep either
way.

---

## 3. Stars: slots, not checks, and not alerts

**This supersedes the "charge for the alert" conclusion I wrote on 2026-09-10.** That was
wrong, and the reason matters: charging for the alert charges at the moment the money is already
moving, which makes the free tier's promise bait.

**A slot is the honest unit because it is the only thing that costs us money.** Every watched
target is a TON Center call, a DexScreener call and a corpus query, every cycle, forever.

- **Checking: free, unlimited, unchanged.** A test fails if any check endpoint ever appears
  behind the gate.
- **Watching: 3 free slots**, alerted fully and immediately, no delay, no degradation.
- **50 ⭐ raises it to 25 slots for 90 days.**

### Reading the payment code before wiring it found two defects

**A 50-Star payment would have bought a full subscription.** `handle_successful_payment` maps
amount to plan with `tier_map.get(amount, TIER_PERSONAL)`. Stars arrive as `total_amount=50`,
match no plan, and fall through to the default -- a paid subscription for about a dollar, then
sent down phone-number onboarding for SIM-swap monitoring they never bought. Currency is now the
discriminator, and a test asserts the XTR branch returns *before* the map is consulted.

**There was no `pre_checkout_query` branch at all, so no Telegram payment could ever
complete.** Telegram gives ten seconds to answer; an unanswered query fails the payment on the
buyer's side and logs nothing on ours. Every part of the purchase looked built and no money
could have arrived.

---

## 4. Pinning: Telegram has no such thing, and that is the answer

Asked four times, answered wrongly three times, because every answer was about where to *find*
the app. That was not the question.

**Telegram has no primitive for pinning a Mini App. What you pin is a CHAT.** A Mini App opened
from a direct link creates none -- the web view opens over the app and the bot never appears in
the chat list. A new user who has never messaged `@relayshield_bot` has **nothing to
long-press**. You were right both times, on laptop and phone.

And pinning the bot does not help, which was your second question: the pinned chat is the TI
monitoring bot, and it gives no route to the Mini App.

**The fix is in our control.** A bot may message a user who opened it through a Mini App, and
that message creates the chat. **The first watch now sends one**, and it says how to pin. It
also proves the alert channel works before an alert is needed -- discovering the bot was blocked
at the moment something gets drained is the worst possible time -- and it converts a Mini App
user into a bot subscriber.

Home-screen pinning stays as the second option: feature-detected, Android-mostly, higher
friction.

---

## 5. Measurement

`tools/miniapp_funnel.py`. Six stages, reported separately and never summed, because a single
number hides the only thing worth knowing, which is where people stop.

    CHECKED     link and TON checks from the Mini App
    WATCHED     watchlist adds
    BOT         Mini App to bot subscribers
    STARS       paid upgrades
    ALERTED     verdict-change alerts sent
    DEVELOPERS  arrivals on the API landing page

**Two of its filters were wrong on the first draft**, both in the direction that reports a live
channel as dead: it filtered on `SRC_miniapp`, which is the deep-link payload rather than what
gets logged, and `/v1/ton-address` logged no source at all, so half the Mini App's traffic was
uncountable. Both fixed and both pinned by tests that read the filter out of the tool and assert
it against the line the code writes.

None of these numbers go in a deck. Measurement doctrine applies to our own funnel exactly as it
applies to the corpus.

---

## 6. Is this a sufficient discovery surface? My honest answer: not yet, and it is now
## one measurement away from being knowable

**What changed today makes it a product rather than a demo.** Before this, the Mini App was a
checker -- a utility with no reason to return, whose most common answer is "nothing known", and
which promised an alert nothing could send. Now it does something with a reason to come back and
a reason to pay.

**But "compelling" is not the bar, and this is the trap.** rsscan has been a registered,
attributed key since 2026-09-03 and **nobody ever counted its arrivals**. FD-1 says DONE, and
"done" is a fact about shipping, not about reach. The honest position is that no surface in this
programme has ever been measured, so an opinion about this one is worth exactly as much as the
opinion about rsscan was.

**The number that decides it is BOT, not CHECKED.** A high CHECKED with a low BOT is a utility
people use once -- which is what a checker is without the watchlist attached, and what it was
until this morning. A BOT number that moves means the Mini App feeds the business rather than
sitting beside it.

**So: run the six discovery routes now that v1 is real, and run `miniapp_funnel.py` before and
after each one.** Each announcement channel gives exactly one first impression and
`@trendingapps` is 3.9M of them; spending them on an unmeasured funnel is how we would end up
having this argument again in a month with no more evidence.

**The one thing I would add before the announcements**, and it is small: the "See one we caught"
example. A first screen that is an empty box asking for input converts worse than one that shows
you what a verdict looks like. It needs a verified flagged URL and a verified flagged TON
address, and `api.relayshield.net` is egress-blocked from the container, so that is a check on
your side or one run of the monitor away.
