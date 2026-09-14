# The measured Mini App discovery funnel

2026-09-11. Nine routes, each with its own attribution key, each with a
before-and-after that is a saved file rather than a number in a terminal.
Generated from `miniapp_routes.json`, which is the source of truth.

---

## Why one key per DESTINATION and not one per category

Until today the five announcement channels shared a single key,
`tg-miniapp-channel`. That made `@trendingapps` at 3.9M subscribers and
`@telegtapps` at 9,671 indistinguishable in the logs.

**Which of those works is the entire question.** If the big channel produces
nothing and the small one produces returning users, that is the most valuable
thing we could learn about distribution, and a shared key throws it away. The
five now have five keys.

## The two ways attribution dies silently, both now tested

A key must appear in three places and a gap in any of them produces something
that looks like it worked:

1. `miniapp_routes.json` -- the source of truth.
2. `ALLOWED_SOURCES` in `cloudflare_worker_miniapp.js` -- the edge gate. A key
   missing here is **silently downgraded** to the generic `tg-miniapp`. The app
   opens, the check answers, nothing errors, the route is gone.
3. `_SOURCE_ALIASES` in `relayshield_developer_signup.py` -- the landing page.
   A key missing here logs `unmatched:` and renders no banner. That is FD-8,
   which ran for four months.

`test_miniapp_routes.py` fails if the three disagree. **It caught a live
regression on its first run**: rebuilding the Worker's list dropped
`tg-miniapp-bot`, which would have cost the `/app` command its attribution.

## And a defect it found in the measurement itself

`/v1/ton-address` had `source=` added yesterday. **The Mini App never calls
it.** Both the app and the widget go through `check()`, which routes URLs to
`/v1/link-check` and *every* address, TON included, to `/v1/wallet-risk`. So
the fix went to an endpoint this client does not touch, and the app's address
checks stayed uncountable while the fix looked done.

Found by tracing the call rather than by reading the endpoint list -- the only
way it could have been found, since both endpoints exist and both accept a TON
address. `/v1/wallet-risk` logs a source now.

---

## The routes, in rank order

| Rank | Destination | Audience | Key |
|---|---|---|---|
| 1 | The RelayShield Telegram blog channel | 4 | `tg-miniapp-blog` |
| 2 | @trendingapps | 3,900,000 | `tg-miniapp-trendingapps` |
| 3 | @web3telegrambotx | 72,742 | `tg-miniapp-web3botx` |
| 4 | @findminiapp | 56,380 | `tg-miniapp-findminiapp` |
| 5 | @onclicka_tma_en | 33,723 | `tg-miniapp-onclicka` |
| 6 | @telegtapps | 9,671 | `tg-miniapp-telegtapps` |
| 7 | tApps Center | unmeasured | `tg-miniapp-tapps` |
| 8 | Other Mini App directories | unmeasured | `tg-miniapp-directory` |
| 9 | TON catalogues | unmeasured | `tg-miniapp-ton` |
| 10 | The @relayshield_bot menu button | unmeasured | none, on purpose |
Ranking is from `miniapp_discovery_and_stripe_choice.md` section 2 and is not
to be re-litigated. Two things in it are worth restating because they are easy
to get backwards:

**The blog channel goes first even though it is the smallest.** It is the only
surface whose audience chose us, so a bad reception there costs least and the
feedback is honest.

**`@trendingapps` does not go second in practice.** It is the largest single
first impression we will ever spend, so it goes after at least one small
channel has put the app in front of strangers. The rank column is priority; the
running order below puts `@telegtapps` before it deliberately, and says why.

**The menu button is rank 10 and has NO KEY, on purpose.** `/setmenubutton`
*replaces* the existing button, which belongs to the TI monitoring product and
keeps the prominent control. That is a recorded product decision. A registered
key would make it look approved; shipping it means adding the key first, which
is the check firing correctly.

---

## Three keys that are counted but are NOT routes

- **`tg-miniapp-share`** -- the share card. Someone posts a scam link in a
  group, one member checks it, forwards the verdict. Not a submission we make,
  so there is no before-and-after to run. **It is the number that says whether
  any of the routes mattered**, because it is the only one that compounds.
- **`tg-miniapp-bot`** -- the `/app`, `/idcheck` and `/check` commands. Reaches
  people who already have the bot. Counting it as a route would flatter the
  funnel.
- **`tg-miniapp`** -- the generic fallback. **A rising count here is a defect,
  not a channel:** it means a published link is losing its attribution.

---

## The running order

See the table for priority. Run them in this order:

1. Blog channel (rank 1) -- cheapest honest feedback.
2. `@telegtapps` (rank 6) -- the smallest paid-attention channel, so it is the
   cheapest place to discover the listing copy is wrong.
3. Read both deltas. **Fix the copy before spending anything larger.**
4. `@findminiapp`, `@onclicka_tma_en`, `@web3telegrambotx` (ranks 4, 5, 3).
5. `@trendingapps` (rank 2) -- last of the channels, once the app has been
   opened by strangers and the copy has survived contact.
6. tApps Center and the other directories (ranks 7, 8) -- standing surfaces
   rather than one impression, so they can run any time.
7. TON catalogues (rank 9) -- **unblocked 2026-09-11**, because TON scans now
   ship: `/v1/ton-address` plus `relayshield_watchlist_monitor.py`, which
   watches TON and only TON. A TON catalogue is the one audience for whom that
   is the headline rather than a detail.

---

## The procedure, per route

### 1. The RelayShield Telegram blog channel

Audience: **4**, counted by the founder on 2026-09-12. That closes the UNMEASURED line this entry
carried, and it changes NOTHING about the running order.

**The blog channel does not rank first for reach and never did.** It ranks first because it is the
cheapest possible place to discover that something is wrong, and four subscribers makes that more
true rather than less. What this submission rehearses, in order of what it would cost to learn
later: that a `t.me/<bot>/<app>` link renders and opens from a channel post at all; that
`tg-miniapp-blog` survives the whole attribution chain into CloudWatch and out of
`tools/miniapp_funnel.py`; and that `--snapshot` then `--compare` prints something a reader can act
on. Each of those is a thing we would otherwise find out in front of 3.9M people.

**So read its delta accordingly.** One arrival is a success, because it proves the chain. Zero from
four subscribers says nothing about the app and quite a lot about the pipe, and the right response
is to check the pipe rather than to conclude the app is unappealing.

The post copy, and how to pin it, are in `miniapp_blog_channel_post.md`.

**ANDREW RUNS THIS, before submitting:**
```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30 --snapshot before-blog
```
EXPECT: the funnel, then `Snapshot saved: miniapp_funnel_snapshots/before-blog.json`.
STOP IF: `REFUSING to overwrite` -- a baseline already exists under that label, so
this route was already started. Do not delete it without deciding to.

**ANDREW SUBMITS** the link below to The RelayShield Telegram blog channel.

```text
https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-blog
```

**ANDREW RUNS THIS, 48 hours later:**
```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30 --compare before-blog
```
EXPECT: a `routes:` delta naming `tg-miniapp-blog`.
STOP IF: `no change` -- the submission produced nothing measurable. That is a
RESULT, not a failure of the tool, and it is the cheapest possible answer about
that channel.
STOP IF: `NEW UNKNOWN ROUTE KEYS` -- a link shipped carrying a key nobody
registered, and its arrivals are unattributed.

One first impression is spent per channel. Spend the first one where a bad reception costs least and the feedback is honest.

### 2. @trendingapps

Audience: 3,900,000. Measured by tools/find_miniapp_channels.py. @twa_apps is the SAME channel, do not submit twice.

**ANDREW RUNS THIS, before submitting:**
```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30 --snapshot before-trendingapps
```
EXPECT: the funnel, then `Snapshot saved: miniapp_funnel_snapshots/before-trendingapps.json`.
STOP IF: `REFUSING to overwrite` -- a baseline already exists under that label, so
this route was already started. Do not delete it without deciding to.

**ANDREW SUBMITS** the link below to @trendingapps.

```text
https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-trendingapps
```

**ANDREW RUNS THIS, 48 hours later:**
```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30 --compare before-trendingapps
```
EXPECT: a `routes:` delta naming `tg-miniapp-trendingapps`.
STOP IF: `no change` -- the submission produced nothing measurable. That is a
RESULT, not a failure of the tool, and it is the cheapest possible answer about
that channel.
STOP IF: `NEW UNKNOWN ROUTE KEYS` -- a link shipped carrying a key nobody
registered, and its arrivals are unattributed.

The largest single first impression we will ever spend. It goes AFTER the blog channel and after at least one small channel, so the app has been opened by strangers before it is shown to 3.9M of them.

### 3. @web3telegrambotx

Audience: 72,742. Measured by tools/find_miniapp_channels.py, 2026-09-03.

**ANDREW RUNS THIS, before submitting:**
```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30 --snapshot before-web3botx
```
EXPECT: the funnel, then `Snapshot saved: miniapp_funnel_snapshots/before-web3botx.json`.
STOP IF: `REFUSING to overwrite` -- a baseline already exists under that label, so
this route was already started. Do not delete it without deciding to.

**ANDREW SUBMITS** the link below to @web3telegrambotx.

```text
https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-web3botx
```

**ANDREW RUNS THIS, 48 hours later:**
```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30 --compare before-web3botx
```
EXPECT: a `routes:` delta naming `tg-miniapp-web3botx`.
STOP IF: `no change` -- the submission produced nothing measurable. That is a
RESULT, not a failure of the tool, and it is the cheapest possible answer about
that channel.
STOP IF: `NEW UNKNOWN ROUTE KEYS` -- a link shipped carrying a key nobody
registered, and its arrivals are unattributed.

### 4. @findminiapp

Audience: 56,380. Measured by tools/find_miniapp_channels.py, 2026-09-03.

**ANDREW RUNS THIS, before submitting:**
```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30 --snapshot before-findminiapp
```
EXPECT: the funnel, then `Snapshot saved: miniapp_funnel_snapshots/before-findminiapp.json`.
STOP IF: `REFUSING to overwrite` -- a baseline already exists under that label, so
this route was already started. Do not delete it without deciding to.

**ANDREW SUBMITS** the link below to @findminiapp.

```text
https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-findminiapp
```

**ANDREW RUNS THIS, 48 hours later:**
```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30 --compare before-findminiapp
```
EXPECT: a `routes:` delta naming `tg-miniapp-findminiapp`.
STOP IF: `no change` -- the submission produced nothing measurable. That is a
RESULT, not a failure of the tool, and it is the cheapest possible answer about
that channel.
STOP IF: `NEW UNKNOWN ROUTE KEYS` -- a link shipped carrying a key nobody
registered, and its arrivals are unattributed.

### 5. @onclicka_tma_en

Audience: 33,723. From the 2026-09-09 Top 15. NOT re-measured by find_miniapp_channels.py, which returned four channels and not this one.

**ANDREW RUNS THIS, before submitting:**
```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30 --snapshot before-onclicka
```
EXPECT: the funnel, then `Snapshot saved: miniapp_funnel_snapshots/before-onclicka.json`.
STOP IF: `REFUSING to overwrite` -- a baseline already exists under that label, so
this route was already started. Do not delete it without deciding to.

**ANDREW SUBMITS** the link below to @onclicka_tma_en.

```text
https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-onclicka
```

**ANDREW RUNS THIS, 48 hours later:**
```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30 --compare before-onclicka
```
EXPECT: a `routes:` delta naming `tg-miniapp-onclicka`.
STOP IF: `no change` -- the submission produced nothing measurable. That is a
RESULT, not a failure of the tool, and it is the cheapest possible answer about
that channel.
STOP IF: `NEW UNKNOWN ROUTE KEYS` -- a link shipped carrying a key nobody
registered, and its arrivals are unattributed.

### 5a. tApps Center -- THE SUBMISSION ROUTE, RESOLVED 2026-09-14

**THE SUBMISSION BOT IS `@app_moderation_bot`. IT IS NOT `@tapps_bot`.**

That distinction is the whole reason this took three rounds. `@tapps_bot` IS the
Telegram Apps Center -- the catalogue itself, a Mini App you browse, "a
community-driven catalog of apps developed by third-party developers, not
affiliated with Telegram Messenger", roughly 56K users. **Opening it shows you
the catalogue and no submission flow, because submissions do not go through it.**
The founder looked and correctly reported there was no way in.

Submissions go to a separate, purpose-built **Apps Moderation Bot**, and its
handle appears nowhere on the catalogue itself:

    https://t.me/app_moderation_bot

**Found by web search from the container after three of these channels turned out
to hide their route.** tapps.center, docs.ton.org, medium.com and peakd.com are
all egress-blocked here, so this rests on multiple secondary sources agreeing --
Adsgram's write-up of the Apps Center, the TON blog's tApps announcement, the TON
Builders Portal listing page, and a developer's own account of getting listed.
**UNVERIFIED against the bot itself**, which is the founder's first step and
settles it in one message.

**IT IS THE RIGHT CATALOGUE FOR US, which is worth saying because the ranking got
the last one wrong.** tApps Center is the TON ecosystem's own catalogue, and this
Mini App checks TON and only TON. That is the one audience for whom our
restriction is the headline rather than a limitation.

**WHAT MODERATION CHECKS, so nothing is discovered at rejection:**

1. **The bot must reply to `/start` in ENGLISH by default.** Reviewers check it.
   `handle_start` in `relayshield_telegram_webhook.py` does, with no payload.
2. **Terms of Use and a Privacy Policy must exist**, even for an app that stores
   very little. `https://relayshield.net/terms` and `https://relayshield.net/privacy`
   are live and already linked from the pricing page and the mobile app.
3. **Graphic assets**: a logo, an icon, and up to SIX screenshots. A developer who
   has been through it describes the screenshots as the thing that sells the
   listing -- treat them as ads, not as documentation.
4. **A category**, chosen from the catalogue's own list.
5. **A security check** on the app itself.

**Review takes roughly 3 to 8 days.** That is the gap between submitting and the
delta being measurable, so take the baseline before submitting and do not read a
flat `--compare` in the first week as a result.

### 6. @telegtapps -- DO NOT SUBMIT. It is a paid ad channel, not a directory.

**Checked by opening it, 2026-09-13, and the ranking was wrong.** Its own
description reads **"Clickers. Telegram apps. HighRisk Dapps."** Every post is
forwarded from a single source channel ("ZN") and is a product advertisement --
ShortsLab, PassportPhotoSnap, Aidentika, mostly Russian-language. 9.53K
subscribers, 8 photos, 9 links, **no pinned message and no submission process**.

**There is nothing to register with.** The only route in is buying a post from
the admin, which is an ad spend and not a listing.

**And the audience is wrong twice over.** Clicker and tap-to-earn traffic does
not buy identity security, and a security product appearing in a channel whose
own strapline advertises HIGH-RISK DAPPS, between a Shorts-script generator and
a passport photo app, is a bad first impression rather than a cheap one.

**THE DEFECT IS IN HOW THIS TABLE WAS BUILT, AND IT AFFECTS THE OTHER FOUR.**
`tools/find_miniapp_channels.py` measured SUBSCRIBER COUNTS and never recorded
channel TYPE, so paid promo channels were ranked alongside real catalogues on
audience size alone. That is this repo's own rule -- rank a surface by how it
performs for US, not in general -- broken by the tool that produced the ranking.

**So every remaining channel gets a TYPE CHECK before anything is spent on it**,
and it is the same one-minute read: open it and ask whether it is a curated
catalogue with a submission route, or a broker selling posts. A channel whose
posts are all forwarded from one source is the second kind.

The baseline and compare commands below are kept because they are correct for
any channel; the submission step is not to be run for this one.

### 6a. @telegtapps, original entry (superseded above)

Audience: 9,671. Measured by tools/find_miniapp_channels.py, 2026-09-03 (9,673 on that run; 9,671 in the Top 15. The difference is two subscribers and a week, not a discrepancy worth chasing).

**ANDREW RUNS THIS, before submitting:**
```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30 --snapshot before-telegtapps
```
EXPECT: the funnel, then `Snapshot saved: miniapp_funnel_snapshots/before-telegtapps.json`.
STOP IF: `REFUSING to overwrite` -- a baseline already exists under that label, so
this route was already started. Do not delete it without deciding to.

**ANDREW READS THE CHANNEL FIRST.** Open `t.me/telegtapps` and read its
DESCRIPTION, its PINNED MESSAGE and the last few posts. One of those names the
submission route: these channels take submissions through a bot, a form, or a
DM to an admin, and which one it is differs per channel and changes over time.

**This step exists because the line below used to say "ANDREW SUBMITS" and
never said how.** That is the FD-2 and Apify defect recorded in CLAUDE.md --
an instruction nobody can act on -- and it was asked about on the first channel
we tried. The container cannot reach Telegram, so this read is the reader's and
cannot be done for them.

**Record what you find in this file** under the channel, so the remaining five
do not each cost a round.

**ANDREW SUBMITS** the link below, through whatever route that read turned up.

```text
https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-telegtapps
```

**OPENING THAT LINK YOURSELF IS A TEST, NOT A SUBMISSION, AND THE ORDER
MATTERS.** Tapping OPEN APP logs nothing against the route key: the route
counter reads `source=` lines in `/aws/lambda/relayshield-api`, and simply
opening the app calls nothing there. **Pressing "Check it" does** -- that is one
arrival credited to this channel, by us.

So verify the link BEFORE taking the baseline, never after. A self-visit inside
the baseline is harmless; the same visit after it becomes part of the delta and
reads as the channel producing a user. On a channel where single digits are the
likely result, one of ours is material.

**ANDREW RUNS THIS, 48 hours later:**
```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30 --compare before-telegtapps
```
EXPECT: a `routes:` delta naming `tg-miniapp-telegtapps`.
STOP IF: `no change` -- the submission produced nothing measurable. That is a
RESULT, not a failure of the tool, and it is the cheapest possible answer about
that channel.
STOP IF: `NEW UNKNOWN ROUTE KEYS` -- a link shipped carrying a key nobody
registered, and its arrivals are unattributed.

The smallest, so it is the cheapest place to discover the listing copy is wrong. Worth running BEFORE @trendingapps for that reason alone.

### 7. tApps Center

Audience: unmeasured. UNMEASURED. A directory listing is a standing surface rather than one impression, so it is worth doing whatever the number turns out to be.

**ANDREW RUNS THIS, before submitting:**
```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30 --snapshot before-tapps
```
EXPECT: the funnel, then `Snapshot saved: miniapp_funnel_snapshots/before-tapps.json`.
STOP IF: `REFUSING to overwrite` -- a baseline already exists under that label, so
this route was already started. Do not delete it without deciding to.

**ANDREW SUBMITS** the link below to tApps Center.

```text
https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-tapps
```

**ANDREW RUNS THIS, 48 hours later:**
```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30 --compare before-tapps
```
EXPECT: a `routes:` delta naming `tg-miniapp-tapps`.
STOP IF: `no change` -- the submission produced nothing measurable. That is a
RESULT, not a failure of the tool, and it is the cheapest possible answer about
that channel.
STOP IF: `NEW UNKNOWN ROUTE KEYS` -- a link shipped carrying a key nobody
registered, and its arrivals are unattributed.

### 8. Other Mini App directories

Audience: unmeasured. UNMEASURED. A shared key deliberately: these are long-tail listings and one key per directory would be attribution nobody reads.

**ANDREW RUNS THIS, before submitting:**
```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30 --snapshot before-directory
```
EXPECT: the funnel, then `Snapshot saved: miniapp_funnel_snapshots/before-directory.json`.
STOP IF: `REFUSING to overwrite` -- a baseline already exists under that label, so
this route was already started. Do not delete it without deciding to.

**ANDREW SUBMITS** the link below to Other Mini App directories.

```text
https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-directory
```

**ANDREW RUNS THIS, 48 hours later:**
```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30 --compare before-directory
```
EXPECT: a `routes:` delta naming `tg-miniapp-directory`.
STOP IF: `no change` -- the submission produced nothing measurable. That is a
RESULT, not a failure of the tool, and it is the cheapest possible answer about
that channel.
STOP IF: `NEW UNKNOWN ROUTE KEYS` -- a link shipped carrying a key nobody
registered, and its arrivals are unattributed.

### 9. TON catalogues

Audience: unmeasured. UNMEASURED.

**ANDREW RUNS THIS, before submitting:**
```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30 --snapshot before-ton
```
EXPECT: the funnel, then `Snapshot saved: miniapp_funnel_snapshots/before-ton.json`.
STOP IF: `REFUSING to overwrite` -- a baseline already exists under that label, so
this route was already started. Do not delete it without deciding to.

**ANDREW SUBMITS** the link below to TON catalogues.

```text
https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-ton
```

**ANDREW RUNS THIS, 48 hours later:**
```zsh
cd ~/dev/relayshield
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30 --compare before-ton
```
EXPECT: a `routes:` delta naming `tg-miniapp-ton`.
STOP IF: `no change` -- the submission produced nothing measurable. That is a
RESULT, not a failure of the tool, and it is the cheapest possible answer about
that channel.
STOP IF: `NEW UNKNOWN ROUTE KEYS` -- a link shipped carrying a key nobody
registered, and its arrivals are unattributed.

UNBLOCKED 2026-09-11. This route was gated on 'only if TON scans ship' and they now do: /v1/ton-address plus relayshield_watchlist_monitor.py, which watches TON and only TON. A TON catalogue is the one audience for whom that is the headline rather than a detail.

---

## Reading the numbers

**Commit every snapshot.** A baseline that exists on one machine is not a
baseline, and the container these tools were written in is reclaimed.

**The tool REFUSES to overwrite a baseline.** Overwriting it after the
submission has run turns the before-and-after into a comparison of a number
with itself, which reads as "the channel did nothing". If a baseline was taken
at the wrong moment, delete it by hand -- that should be a decision.

**The sliding window is the one thing that would make these numbers a lie.**
Both runs count a rolling `--days` window back from now, so a delta is only the
submission's effect if the two runs are close together relative to that window.
A `--days 30` baseline compared five weeks later measures the window sliding.
The tool prints this caveat on every comparison.

**BOT is the stage that decides whether any of this worked.** A high CHECKED
with a low BOT is a utility people use once. A BOT number that moves means the
Mini App is producing subscribers, which is the flywheel the watchlist was
built for.

**A zero is ambiguous on its own.** "We have not submitted here yet" and "we
submitted and nobody came" are different findings with different fixes, and
only the snapshot labels tell them apart.

**None of these numbers go in a deck.** Measurement doctrine applies to our own
funnel exactly as it applies to the corpus.

---

## Before any of it runs

Two AWS commands are outstanding and both are one line. Neither blocks a
submission, but the second one silently breaks Stars.

**ANDREW RUNS THIS:**
```zsh
cd ~/dev/relayshield
sh tools/apply_deploy_invoke_policy.sh
```
EXPECT: `simulate-principal-policy` reporting allowed for
`relayshield-watchlist`.
STOP IF: it cannot find where the policy lives -- send the output, that is a
different problem.

Deploy run 142 went red for exactly this and **the deploy itself succeeded**:
`relayshield-watchlist WAS DEPLOYED. Only the probe was denied.` Third
occurrence of that shape; the code is live either way.

**ANDREW RUNS THIS:**
```zsh
cd ~/dev/relayshield
sh tools/grant_stars_watchlist_iam.sh --apply
```
EXPECT: `dynamodb:PutItem -> allowed`, then `DONE. A Stars purchase can now be
credited.`
STOP IF: it stays `implicitDeny` after 50 seconds -- read step 2's output, the
role may carry an explicit Deny, which no Allow overrides.

The read-only run already answered this: `dynamodb:GetItem` and
`dynamodb:PutItem` are both **implicitDeny** on
`relayshield-breach-check-role-1sapnwdl`, which is the role the Telegram
webhook runs as. Until this is applied, a Stars purchase takes the money and
fails to credit it.
