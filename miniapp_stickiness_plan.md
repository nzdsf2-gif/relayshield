# Mini App v1: what makes it sticky, and what would only look like it

Written 2026-09-09 after the founder's objection, which is correct and is the
right time to raise it: *"I think our miniApp needs some compelling additional
capabilities, to gamify or make it stickier. If users don't find it engaging, our
flywheel wont succeed and users will have no motivation to click a link to try and
buy our Tg bot."*

## The actual problem with v1 as built

**A checker is a utility with no reason to return.** You paste a link, you get a
verdict, you close it. Nothing about that produces a second visit, and a Mini App
that is opened once is worth roughly one impression, which is not a flywheel.

Worse for our specific case: the moment a user needs it is the moment they have
already been sent something suspicious. That moment is real but rare, and it
arrives when they are NOT thinking about us. So v1's retention depends entirely
on the user remembering an app they used once, weeks ago, under stress.

## The trap, and it is the one this repo keeps writing down

**Gamification that is not attached to the product produces engagement with the
game, not with the product.** Streaks, points and daily-spin wheels are the
TON-ecosystem default precisely because they are cheap, and they attract people
who want the points. That audience does not convert to a paid security bot, and
the metric it moves, DAU, is exactly the number that looks like progress while
nothing is happening. `MEASUREMENT DOCTRINE` applies to our own funnel numbers as
much as to the corpus.

So the test for every idea below: **does it get better the more the user uses it,
in a way that makes them safer?** If the answer is "no, but they get a badge",
it is out.

## The four that pass, in build order

### 1. WATCHLIST. The one that turns a checker into a habit. (v1.1, ~2 days)

The user saves an address or a domain. We tell them when the answer CHANGES.

This is the single highest-value addition and it is the natural shape of our own
product: `api.relayshield.net/developers` already sells "register a watch and you
are told when the answer changes rather than on a schedule". The Mini App version
is the consumer face of a thing we already do.

**Why it is sticky and honest at the same time:** a clean result today is not a
promise about tomorrow, which our own copy says in every response. A watchlist is
the only correct answer to "so should I check again later?", and it produces a
notification we are *invited* to send.

**The mechanism is the interesting part.** A Telegram bot may message a user who
has started it, so the Mini App hands off to `@relayshield_bot` to register the
watch. That is the flywheel the founder is asking for, running in the right
direction: **the Mini App creates bot subscribers**, rather than the bot's tiny
audience being asked to carry the Mini App.

### 2. SCAN HISTORY, private and local. (v1.1, half a day)

Every check the user has run, kept in `localStorage`, with the verdict and the
date. No account, nothing sent anywhere.

Cheap, and it does three things: it makes a return visit useful (`what was that
address again?`), it makes the watchlist obvious (a repeated check is a candidate
to watch), and it is a visible reason to open the app when nothing is wrong.

**It must stay local.** A server-side history of what a person checked is a
behavioural profile of their financial anxieties, and `miniapp_discovery` already
records the decision not to accumulate a social graph for the contact check. Same
principle, same answer.

### 3. THE SHARE CARD. The only growth mechanic here that is not a gimmick. (v1.2, ~1 day)

A verdict renders as a clean image the user can forward INTO the group chat where
they were sent the thing.

**This is the loop.** Someone posts a scam link in a Telegram group; one member
checks it and forwards a card saying what the instructions would cause; every
other member sees the card, the verdict, and the app that produced it. Telegram's
native surface is forwarding, and a security verdict is one of the few things
people genuinely forward.

Carries `startapp=tg-miniapp-share`, which is why the key list is already
registered. **Never render a card that says "safe"** -- a forwarded false
reassurance is the worst artefact this product could produce.

### 4. THE WEEKLY DIGEST, only if the watchlist ships. (v2)

"Three domains you watch changed this week." A reason to return that we send,
rather than one the user has to remember.

It is fourth because it is worthless without item 1 and actively annoying
without item 2: a digest about nothing trains people to mute the bot, and a muted
bot cannot deliver the alert that matters.

## What is deliberately OUT, and why

- **Points, streaks and leaderboards.** They would work, in the sense of moving
  DAU. They attract the airdrop-farming audience, who are the least likely
  people on Telegram to pay for a security subscription, and the number they move
  is the one most likely to be mistaken for progress.
- **A daily free scan quota with a "come back tomorrow" gate.** It converts a
  moment of genuine need into a paywall at the exact instant somebody is about to
  be defrauded. That is the wrong thing to do regardless of what it does to
  retention.
- **TON Connect / wallet login.** It gates the first answer behind a wallet, which
  is the opposite of the keyless design that makes the first use complete at all.
  Revisit only if TON-native scans ship, per the discovery ranking's item 6.
- **A referral programme.** We have one, at `partners.relayshield.net`, aimed at
  people with an audience. Bolting a consumer referral tree onto a security tool
  invites exactly the mercenary traffic the first bullet describes.

## The honest sizing

Items 1-3 are about three and a half days together and they change the app from
"a thing you used once" to "a thing that tells you when something changed". That
is the difference the founder is pointing at.

**And the sequencing rule from the discovery plan still holds and now matters
more:** each announcement channel gives ONE first impression. Submitting v1 as
built spends that impression on a checker. **Ship the watchlist first, then
submit.**
