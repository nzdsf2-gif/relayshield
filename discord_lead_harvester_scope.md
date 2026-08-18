# Broadening Discord lead discovery: scope

*Written 2026-08-13. Answers "can `relayshield_intel_discord_channels` be broadened to find
candidate servers for our bot over time?"*

**Short answer: yes, but as a second harvester, not a widened one.** The existing one cannot be
fixed by making it look harder, because its limit is its input, not its logic.

---

## Why widening the existing harvester does not work

`_queue_discovered_discord_invites()` scans the message text of the **criminal** Telegram channels
we monitor for threat intelligence. Widen the regex, widen the channel list, run it more often, and
every additional lead is still a server advertised inside a criminal Telegram channel.

Three weeks of running produced one lead: `rugpullbot.com - SOL & BSC`. That is not underperformance,
that is the population. Those servers are competitors or they are what we protect people from.

**The code is fine. Reuse it. Point it at a different input.**

Everything expensive is already built and working: invite-code extraction, the unauthenticated
resolve against `GET /invites/{code}?with_counts=true`, the DynamoDB write with dedupe via
`ConditionExpression`, and the `found_via` provenance field. None of that gets rewritten.

---

## Source 1: our own installs. Highest value, lowest effort, do this first.

**Every server that installs the bot already tells us its guild id, and Discord will tell us the
rest for free.**

When the bot is added to a server, the interaction payloads we already receive carry `guild_id`. We
currently do nothing with it. That single field is the highest-quality lead source available,
because those admins have **already said yes once**. They are not candidates, they are customers.

What it unlocks that nothing else can:

- **Real adoption numbers.** How many servers, how large, how active. Right now we cannot answer
  "how many servers is the bot in" without clicking through the Discord developer portal.
- **The 75-server threshold** for the Discord App Directory becomes a number we track rather than
  guess at.
- **The reference list.** The single hardest question a new admin asks is "who else runs this?"
  Today we cannot answer it with anything but Arjen, who holds no Manage Server permission anywhere.
- **Churn.** A server that removes the bot is the most valuable feedback we will ever get, and we
  are currently blind to it.

**Scope:** a new table `relayshield_discord_installs` (PK `guild_id`), written on every interaction,
storing guild id, resolved guild name and member count, first seen, last seen, and command counts by
type. Resolve the guild name via the same code path already in `relayshield_intel_monitor.py`.

**Privacy line, and it is not negotiable:** store the **guild**, never the user. No user ids, no
usernames, no command arguments. The bot's entire pitch is that it cannot read your server, and a
table of who ran `/exposure` on which email would make that a lie. Guild-level counts only.

**Effort:** small. One table, one write path in the existing interaction handler, one IAM policy.
Note the trap already recorded in memory: `relayshield-breach-check-role-1sapnwdl` uses **per-table**
policies, so without its own policy the write fails through an `except` and looks fine while doing
nothing.

---

## Source 2: the legitimate Telegram channels we already read

The monitor already processes a large number of Telegram channels. Only the criminal ones feed the
current harvester.

**Scope:** run the same invite extraction over the legitimate crypto and security channels in the
corpus, writing to a **separate** table or with a distinct `discovery_method` so the two populations
never mix. A lead is only useful if we know which pile it came from; merging them would poison the
one list we actually want.

**Effort:** small, mostly a routing change at the existing hook point.

**Honest expectation:** low volume. Legitimate project channels cross-promote less than criminal
ones do, so this is a trickle, not a pipeline. Worth doing because it is nearly free, not because it
will fill the list.

---

## Source 3: admins who reply to the Tier 1 posts. Not automatable.

`discord_server_targets.md` is right that this is the highest-value source, and it is a manual one.
An admin who replies to the Solana Mobile post has self-selected, and no harvester produces that.

**Scope:** nothing to build. Record replies against the same table by hand so the reference list has
one home.

---

## What NOT to build

**Do not scrape Discord server directories.** Disboard, top.gg server lists and similar are against
Discord's ToS to scrape, the data is stale, and the invites there are exactly the ones our own hard
rule says never to trust. We tell users that invite links from directories are a scam vector; we do
not get to make an exception for ourselves.

**Do not join servers with an automated account to assess them.** That is how an account gets
flagged, and the account at risk is the one the bot runs on.

**Do not build a scoring model yet.** With one confirmed install there is nothing to train or
calibrate against. Rank by the online percentage described in
`discord_midsize_pipeline_2026-08-13.md` and revisit when there are twenty installs to learn from.

---

## Recommended order

1. **Install tracking (Source 1).** Small, and it is the only one that produces a reference list, a
   churn signal and a real answer to "how many servers are we in".
2. **Legitimate-channel harvest (Source 2).** Nearly free once Source 1 exists.
3. Everything else stays manual.

**The honest frame:** none of this creates demand. It makes the demand we create visible, and it
turns a manual list into a maintained one. The thing that actually produces installs is still a
person posting into a server and answering whoever replies.
