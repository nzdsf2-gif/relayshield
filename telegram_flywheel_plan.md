# The Telegram flywheel: which bot, is it enough, and how traffic actually arrives

**Written 2026-08-10.** Follows `telegram_wallet_integration_assessment.md`. Two live checks changed
the shape of the answer, so they come first.

---

## Two facts checked live, both of which reframe the question

### 1. There is one bot, not two

The question assumed a choice between a Business Starter+ bot and a Crypto Shield bot. There is
**one**: `@relayshield_bot`, confirmed against `getMe` using the token in
`relayshield/telegram_bot_token`. `relayshield_telegram_webhook.py` serves both the business
onboarding flow and the crypto wallet flow through that single bot.

That is good news. One bot means one audience to grow rather than two to split, and it removes the
decision entirely. The real choice is not which bot, it is **which command** the free tool lives
behind, and it should be one command in the existing bot, not a second bot.

### 2. The installed base is 5 active users

Telegram-linked user records in `relayshield_users`: **6, of which 5 are active.**

So the direct answer to "are those channels sufficient to build the flywheel" is **no, not as they
stand.** Five people is not a distribution channel, it is a pilot group. A flywheel needs an input,
and today the bot has essentially none.

This is not an argument against the plan. It is an argument that **the plan has to be about acquiring
the first users, not about converting existing ones**, and any proposal that assumes an existing
audience is solving the wrong problem.

---

## The mechanism that is currently switched off

`getMe` also returns:

```
supports_inline_queries: False
can_join_groups:         True
```

**Inline mode is the viral primitive on Telegram, and ours is disabled.**

With inline mode on, anyone in any Telegram group can type `@relayshield_bot <address>` directly in
the message box, get a result, and post it into that group. The group does not install anything. The
group does not need to know we exist beforehand. And every result posted this way carries a
**"via @relayshield_bot"** attribution visible to everyone in the chat.

That is the entire flywheel in one feature:

- The unit of distribution is **one person answering someone else's question in a group they are
  already in**, which is a thing people do for status, unprompted, for free.
- The audience is a crypto group chat, which is exactly where "is this address safe" gets asked
  several times a day.
- Attribution is automatic and built into the platform, so no `?source=` plumbing is needed for the
  social loop to work.

This is the same structural insight as `rsscan --report`: the free thing has to produce something a
user wants to hand to someone else. On Telegram, inline mode *is* the handing.

**Cost to enable:** a BotFather setting (`/setinline`) plus an `inline_query` handler in the existing
webhook. Hours. It is the single highest-leverage change available on this channel and it is not on
any list.

`can_join_groups: True` already, and privacy mode is on (`can_read_all_group_messages: False`), which
is the correct posture: the bot can be added to a group without being able to read everything, which
is what a security-conscious group admin will check first.

---

## What the free tool should be

Not a port of `rsscan`. `rsscan` scans a local repo for secrets, and nobody is running a repo scan
from a phone in a Telegram group.

The Telegram-native equivalent, meaning the free thing that is instantly valuable, needs no account
and produces something worth forwarding, is **address and URL screening**:

- `@relayshield_bot 0xabc...` in any chat, returns a verdict inline.
- The same for a Solana, TON, Bitcoin or XRP address. `/v1/wallet-risk` already auto-detects the
  chain across all of them.
- The same for a URL. `scan_url` already exists.

Both of these already work server-side. This is a front end over live endpoints, not new capability.

**And the BlueNoroff post makes the URL case the timely one.** A campaign that spreads by sending
meeting links through Telegram, screened by a bot that works inside Telegram, is the same graph. That
is a real launch narrative rather than a manufactured one, and it is the reason to sequence these two
pieces of work together rather than separately.

**Guard rails, from our own history:**

- Do not return a clean verdict when the check did not run. Three defects this month have had that
  exact shape. An inline result that says "safe" because a lookup failed is the worst possible
  version of this feature, in the most public possible place.
- Free tier must be metered and rate-limited from day one. CS Mobile's free-tier scans are still
  unauthenticated and unmetered in prod and that is an open item, not a precedent to copy.
- Inline queries are public by nature. Never echo anything a user has stored privately.

---

## How traffic actually arrives

Ordered by cost, honestly. The first three are the ones worth doing.

**1. Inline mode itself.** Every use inside a group is an impression for that whole group. This is
the only item on the list where usage produces distribution rather than consuming it, which is what
makes it a flywheel rather than a funnel.

**2. Attach it to the BlueNoroff post.** The post is drafted and going to LinkedIn, Telegram,
Mastodon and Farcaster. A "paste a suspicious meeting link into `@relayshield_bot`" line inside the
Telegram version costs nothing and is genuinely useful in exactly that moment. Do not write it as a
CTA; write it as part of the advice.

**3. Answer real questions in the groups where they are asked.** Crypto Shield Solana channel
research already exists in `crypto_shield_solana_channels.md`. Inline mode makes this
non-promotional: you are answering a question with a result, and the attribution comes along on its
own. This is the same play Reddit needs and has never got, with the difference that here the tool
does the talking.

**4. The existing surfaces, retrofitted.** CS Mobile, `/developers`, the blog and the Snap can all
point at the bot. Low effort, low yield, worth doing once the bot is worth arriving at.

**Not recommended:** buying Telegram ads, or paying channel admins for posts. Wrong stage, and the
audience for a security tool is the least likely to convert from a paid placement.

---

## Is address and URL screening enough to make people buy? No, and it is not supposed to be.

**Honest answer: address and URL screening will acquire users and will convert almost none of them.**

Free address screening is everywhere. Blockaid, GoPlus, Scam Sniffer, block explorer labels, and the
warnings built into every major wallet. Our version is good, but a user has no reason to pay for more
of a thing they already get free in five places. If the pitch is "screening, but ours," the ceiling
is low.

**That is fine, because it is the acquisition mechanic, not the conversion mechanic.** Conflating the
two is how this plan would fail.

Look at how the developer funnel actually converts. `rsscan` does not convert because local secret
scanning is valuable. It converts because it finds what it can see and then names what it cannot:
what is already public, on the org, at the identity layer. **The free tool reveals a problem the free
tool cannot solve.**

The Telegram equivalent:

> Address clean. No flags on this contract.
>
> Separately: the email you use with this wallet appears in 3 breach corpora and in an infostealer
> log from March. Message me privately to see which.

The first line is the free thing that spreads. The second line is Bundle A capability, it is what
nobody else in that group chat can offer, and it is the reason someone pays.

**And the medium enforces the split for us, which is the elegant part.** A wallet address is public
by nature, so screening it inline in a group is socially fine. A breach or stealer-log result is
private by nature, so nobody wants it posted in a group. The user has to leave the group and DM the
bot to get it.

That DM is the funnel step. It converts a person who used us inside **someone else's** group into a
direct conversation with our bot, which is where onboarding, the free trial and the subscription
already live in `relayshield_telegram_webhook.py`.

**So the build order inside the feature is:**

1. Inline address / URL verdict. Free, fast, no account. This is what spreads.
2. A single credential-layer teaser line on every inline result. No detail, no numbers that identify
   anyone, just the existence of a finding and an invitation to DM.
3. The DM flow, which already exists, takes it from there.

**Do not skip step 2 and hope.** An inline tool with no upgrade path is a free service we pay to run.

**One caution on the framing in the question:** the NHI and open-source repo scanning incentive is
aimed at developers and security leads. Telegram crypto users are a different audience with a
different wallet and a different buying decision. They are two funnels that happen to share a
differentiator, not one funnel with two doors. Do not let the Telegram copy inherit the developer
pitch.

## So: is it sufficient, and what about a Mini App?

**Sufficient to build a flywheel? Not today, and not because the channel is wrong.** The channel is
right. The mechanism that makes it a flywheel is turned off, and the installed base is five people.
Fix the first and the second stops mattering, because inline mode does not need an installed base to
work. That is the whole point of it.

**A Mini App is still later, and the case for it is now clearer.** A Mini App is the right home for
anything that needs a screen: history, watchlists, a connected TON wallet, a scan result with detail.
None of that matters until people are using the bot. Inline mode tests the entire premise for the
cost of an afternoon; a Mini App tests it for the cost of a sprint, under a TON-only restriction that
is still second-hand and unverified.

**Sequence:**

1. Enable inline mode, add the handler, one address-or-URL verdict. Days.
2. Ship it alongside the BlueNoroff post so the launch has a reason to exist.
3. Watch one number: **inline queries issued in chats we do not control.** That is the flywheel
   working or not, and nothing else is.
4. If that number moves, build the Mini App, and read Telegram's current Mini App terms first.
5. If it does not move, we have learned the channel is wrong for the cost of an afternoon, which is
   the entire reason to do it in this order.

---

## Inline mode versus Bundle A: I partly disagree, and the disagreement is about time, not value

**Where I agree completely:** channel sales is the stated number one constraint, inline mode is the
first genuine self-serve acquisition mechanic anyone has proposed for this business, and it is worth
more strategically than another listing. As a *strategic* priority it deserves to be top of the list.

**Where the framing is off:** "Bundle A is higher-touch and will require real sales outreach" is true
of **selling** Bundle A and not true of **finishing** it. What remains is a $0.01 test subscription
from account `442429445748` against offer `offer-d75uqa4lwqsuo`, a check that six endpoints return
200 and Bundle D returns 402, a metering record, and an `UpdateVisibility` change set. That is a
couple of hours of mechanical work, not a sales motion. The sales motion is what comes *after*, and
that is the part that can wait.

So they are not competing for the same resource. Two hours against two days.

**Three reasons not to leave Bundle A at 95%:**

1. **AWS Marketplace serializes submissions per seller.** An unfinished change set is a standing
   block on other listing work, including anything the Snap or Crypto Shield might want later.
2. It has been one test away for three days. Work that sits at 95% across multiple sessions is
   usually blocked on appetite rather than effort, and switching to a more interesting project is
   how it stays at 95% permanently.
3. **Bundle A is what the Telegram funnel converts into.** The credential-layer teaser in step 2
   above upsells Bundle A capability. Building the acquisition funnel for a product that is still
   Limited is building a door to a room that is locked.

Point 3 is the one that actually settles it. These are not competing priorities, they are the two
halves of one funnel, and the paid half has to exist first.

**Recommended order:** finish Bundle A this week, in one sitting, because it is hours. Then make
inline mode the next real project rather than another list item. If Bundle A slips again, that is
useful information in itself and worth naming rather than working around.

**One thing worth doing before either:** enable inline mode in BotFather now. It is a settings toggle
and costs a minute. Telegram sometimes takes time to propagate bot capability changes, and having it
already on removes a dependency from the day the handler is ready.
