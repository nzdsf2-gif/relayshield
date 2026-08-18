# Discord server targets, and how to use each size

*Written 2026-08-12. Companion to `discord_flywheel_and_conversion_plan.md`, which covers the pitch
and the growth mechanic. This file is about WHICH servers and WHY, which that file deliberately
left out.*

---

## The distinction that changes the whole approach

**A bot can only be installed by someone holding Manage Server on that server.** Nobody else can do
it, no matter how much they like the product. That single fact splits every target into two groups
that need completely different asks.

| | **Big official servers** | **Mid-size community servers** |
|---|---|---|
| Who runs it | The company, with staff moderators | One or two identifiable people |
| Will they install a third-party bot? | **Almost never.** A company does not put an outside bot in its own flagship community. | **Yes, if convinced.** This is where installs actually happen. |
| So what are they for? | **Reach.** Dozens of people in the room each run their own server. | **Conversion.** One yes equals one install. |
| The ask | "If you run a server, here is a bot you can add." | "Can I add this to yours? Happy to start in a staging server." |
| Where | A tools, suggestions or self-promo channel, after checking the rules | DM to the admin, or their designated bot-request channel |

**Getting this backwards wastes the one shot you get per server.** Asking Solana Mobile to install
our bot reads as not understanding how their server works. Posting a generic "here's a tool" into a
50-person project server wastes a warm conversation that could have been a direct ask.

**Arjen is a reference, not a channel.** He holds no Manage Server permission anywhere relevant, so
sending him an invite achieves nothing. His value is answering the question every admin asks second:
"who else actually runs this?" Name him in the admin conversation, with his permission.

---

## STOP: the "post to a big server" play mostly does not survive the rules

**Found 2026-08-13 by actually reading Solana Mobile's rules before posting.** Their rule 5:

> No spam, links, or advertising, including via your Discord username. Sharing a new event or
> dApp store app is fine, but moderators may ask you to remove it at their discretion.

**A bot invite link is advertising, and the carve-out covers only events and dApp Store apps.** So
the Tier 1 reach post described below would have breached the rules of the very server where our
standing is best. It was not posted.

Assume this generalises. Large crypto servers almost all prohibit unsolicited promotion, so the
reach play is the exception, not the default. **Read the rules channel of any server before posting,
every time.** That check costs two minutes and it is the difference between a post and a warning.

Two further Solana Mobile rules worth carrying to every server:

- **Rule 2: "The team will NEVER DM you. Don't DM them either."** Check a person's role before
  DMing. Rule 14 there defines team as Core Contributor, Community Manager and Admin only; a
  Community Champion is an ordinary member. A DM to the wrong person breaks a posted rule with
  exactly the people whose goodwill we want.
- **Rule 12, no AI slop.** Polishing wording with AI is fine; having it write your argument is not.
  Anything drafted for these channels goes out in the founder's own voice.

**What this leaves.** Tier 2 was always a direct admin ask rather than a public post, and that is now
the primary play rather than the fallback. Asking an admin for permission is not advertising, and it
is the one approach no self-promo rule prohibits.

---

## Tier 1: verified standing, use for REACH

We are already a known participant in these. That is worth more than any cold introduction and it is
the reason to start here.

### 1. Solana Mobile Community Discord, START HERE

- **Our standing:** we hold the **Developer role**, we have had staff replies in `#dev-answers`, and
  Crypto Shield Mobile is published in their dApp Store. We are a publisher in their ecosystem, not
  a stranger.
- **Why first:** the members are precisely the wallet-address audience `/scan` serves, and a large
  share of them run their own project servers.
- **The ask:** post to a tools or developer channel aimed at admins in the audience. **Do not ask
  Solana Mobile to install it.**
- **Check first:** their self-promotion rules, and which channel permits a tool post. `#support` is
  not a support channel and blocks posting; that tripped us up before.

### 2. Coinbase Developer Platform Discord

- **Our standing:** active, evidenced participant in `#cdp-sdk` and in x402 issue #2814. We
  contributed a real root-cause finding before ever making an ask, which is the right pattern.
- **Hold for now:** `MKTPL-15` in TODO.md already gates a Show and Tell post here on the x402 V2
  stuck-resource issue resolving. Do not spend the credibility twice; when that unblocks, the bot
  can ride along with the x402 post.

### 3. MetaMask, HOLD until roughly 8 September

- **Our standing:** the RelayShield Snap is submitted and **under review, to approximately
  8 September**.
- **Why hold:** introducing a second product into their community mid-review adds a variable to a
  decision we want clean. It is a strong second move, after the Snap lands.

### 4. MSP Geek Discord

- **Different audience:** MSPs, not crypto. Relevant to the API and Bundle A, much less to `/scan`.
- **Blocker:** self-promotion policy unknown. TODO item 25 already says to ask a mod before posting
  rather than assume. Do that first.

### 5. Blue Team Village Discord

- 8,300+ members, security practitioners. Same rule recorded in TODO.md line 1365 applies to every
  practitioner community: contribute before promoting.
- Better fit for the npm maintainer post and the API than for the Discord bot.

### Do not use: PayAI Discord

Recorded track record of unanswered support queries. Not a channel.

---

## Tier 2: mid-size install targets, the ones that actually convert

> **BUILT 2026-08-13. See `discord_midsize_pipeline_2026-08-13.md`**, which holds 14 verified
> candidates in the 1k to 50k band with live member counts, 5 reach-only servers over 50k, and a
> competitive finding on SecurityBot that changes the pitch. The criteria below still stand. Point 4
> under "Where to look" was wrong and is corrected there.

**This list does not exist yet, and inventing names here would be worse than leaving it empty.**
Building it properly is roughly an hour of research and it is the highest-value hour available for
this channel.

### What qualifies a server

All four, not three:

1. **Scam links in-channel are a visible, unsolved problem.** Read the last two weeks of their
   general and support channels. If members are posting "is this link real?", that is the signal.
2. **Between roughly 1,000 and 50,000 members.** Small enough that one person decides, large enough
   that an install is worth having.
3. **An identifiable, reachable admin or head moderator.** A named human, not a support inbox.
4. **They already run third-party bots.** Look at the member list for existing bots. A server that
   already trusts one has answered the hardest objection for us.

### Where to look, in priority order

1. **The admins who reply to the Tier 1 posts.** This is the whole point of posting there. A
   self-selected admin who asked a question is worth ten cold ones.
2. **Wallet and chain ecosystem communities** beyond the official flagship server, which usually
   means regional, language-specific or project-specific servers in the same ecosystem.
3. **NFT and DeFi project servers**, which the landscape research already identified as
   Discord-first with a permanent scam-link problem.
4. ~~**Servers already surfaced by our own pipeline.**~~ **WRONG, corrected 2026-08-13. Do not go
   back to this table.** `relayshield_intel_discord_channels` holds **one** row after three weeks of
   harvesting, and it is not a shortlist for this purpose at all: it scans the **criminal** Telegram
   channels we monitor, so by construction it only surfaces servers advertised inside criminal
   Telegram channels. Its one lead is a rug-pull-bot shop. Those are competitors or they are what we
   protect people from, not communities that would install a protective bot. The table is fine at
   its actual job, which is finding criminal infrastructure to monitor.

   The method that does work is in `discord_midsize_pipeline_2026-08-13.md`, implemented by
   `scripts/resolve_discord_invites.py`: resolve invite codes taken from official project websites
   against Discord's unauthenticated preview endpoint, filter to the member band, then **rank by
   online percentage rather than member count.**

### The two hard rules

- **Get the invite from the project's own official website.** Never from a directory, never from a
  DM. Fake invite links are a scam vector we warn users about, so we follow our own advice.
- **Never attempt to install.** You cannot add a bot to a server you do not administer, and trying
  is how an account gets flagged. Ask.

---

## What to say

### To a big server, aimed at admins in the audience

> If you run a Discord where people post links, you might find this useful. We built a slash-command
> bot that checks a link or a wallet address against criminal threat intelligence before anyone acts
> on it. It deliberately does not request the Message Content Intent, so it is structurally unable
> to read your channels, and it installs with zero permissions. Replies are private to whoever ran
> the command unless they choose to share.
>
> Free to add: https://top.gg/bot/1536877675627552829

### To a mid-size admin, direct

> We built a slash-command bot that checks links and wallet addresses against criminal IOC feeds
> before your members click them. It deliberately does not request Message Content Intent, so it is
> structurally unable to read your channels, and the install asks for zero permissions. Happy to put
> it in a staging server first if you would rather see it before your main one.

**The middle sentence is the one that works.** Crypto server admins are justifiably paranoid about
bots, and "we cannot read your server even if we wanted to" is the only claim that answers the
objection they actually have.

---

## Start with one

A single server where members genuinely use it teaches more than ten installs nobody touches, and it
produces the reference an admin asks for next. The realistic sequence is: post to Solana Mobile,
answer whoever replies, convert one of those admins, then use that server as the reference for the
next five.

## Honest limit, already recorded and worth not forgetting

Consumer crypto Discord users have no budget. **This channel will not produce direct revenue.** Its
value is top-of-funnel awareness, the 75-server threshold that unlocks the Discord App Directory,
and reaching admins who happen also to be security practitioners with a work budget.
