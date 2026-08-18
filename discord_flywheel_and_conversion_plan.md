# Discord: flywheel, conversion ladder, and where to list

**Written 2026-08-11, after the bot went live and passed its first real `/scan`.**

Bot status: live, Discord-validated, `/scan` and `/scam` registered globally, installed in a private
test server, first flagged result confirmed end to end.

- Endpoint: `https://zquf6rgaeg.execute-api.us-east-1.amazonaws.com/prod/discord/interactions`
- Application ID `1536877675627552829`
- Install URL (Send Messages + Embed Links only):
  `https://discord.com/oauth2/authorize?client_id=1536877675627552829&scope=bot%20applications.commands&permissions=18432`

---

## 1. The flywheel, stated honestly

**Almost nobody shares a clean result.** There is no social reward for "this link is fine." The
share loop is powered by **flagged** results only, and hits are rare. Any plan that assumes the
share button is the growth engine is wrong.

What actually motivates a share on a hit:

- **Credit for catching it.** In a crypto server, being the person who spotted the drainer is
  status. This is why the shared card reads "Checked by @user with RelayShield" rather than just
  naming us.
- **Settling a live argument.** Someone posts a link, someone asks if it is legit, the result ends
  the thread in public.

**Shipped 2026-08-11 on the back of this:** the button now appears **only on a flagged result**,
relabelled "⚠️ Warn the channel" in primary style. Offering it on clean results trains people to
ignore it, and the one time it matters they would not see it.

### The real growth unit is the install, not the share

One admin installs the bot and every member of that server can use it. That single fact reframes
who we are selling to: **server admins and moderators, not end users.** Effort belongs in listings
and admin outreach, not in optimising a button.

---

## 2. The conversion ladder

`/scan` answers "is this link bad", which is close to a commodity. The paid layer answers a question
a free public tool cannot: **"are your own credentials already exposed?"** That is personal, urgent,
and must be private, which is exactly what an ephemeral reply is for.

| Step | What | Status |
|---|---|---|
| 1 | `/scan` free, public, builds the habit | **LIVE** |
| 2 | Quiet ephemeral footer naming what `/scan` cannot answer | **LIVE 2026-08-11** |
| 3 | `/exposure <email>`, ephemeral, honest teaser, gated detail | ✅ **BUILT AND DEPLOYED**. Capped dedicated key, 50/day server-side (founder decision 2026-08-11) |
| 4 | The org ask, aimed at the admin: a whole domain, not one address | not started |

Step 2 as shipped, deliberately two lines, because a long advert under a security verdict
undermines the verdict, which is the actual asset:

> _This checks the link. It cannot tell you whether your own credentials are already in a stealer
> log. `/exposure` checks that, privately._

---

## 3. `/exposure` specification, and the decision blocking it

**Not built, on purpose. It needs a billing decision first, and shipping it without one would
repeat a defect that is already open elsewhere.**

### Behaviour

- **Ephemeral always. No exceptions, and no share button.** The result is PII. A "post to channel"
  button on a breach result is a way to dox a member, and it must never exist on this command.
- Input: an email address.
- Output: a real, honest teaser. Number of breaches, most recent date, nothing else.
- Then a link to sign up for the detail.

Draft copy:

> **Found in 4 breaches**, most recent **March 2026**.
> Which breaches, which credentials, and whether the password is still in circulation are in the
> full report. [Get it →]
>
> _A clean result means nothing was found in the sources we queried. It is not proof of safety._

### The blocking decision: how does this get metered?

The Discord bot is free and unauthenticated. `/exposure` hits real breach data, which costs money
per call. Three options, and **the founder needs to pick one:**

1. **Free, rate-limited, unmetered.** Simplest. **This is exactly the shape of the still-open
   CS Mobile problem**, where free-tier scans run unauthenticated and unmetered in production. Do
   not repeat it without deciding to.
2. **A dedicated API key for the Discord bot**, metered like any other consumer, absorbed as
   marketing spend with a hard monthly cap.
3. **Per-Discord-user free allowance**, e.g. three checks, then a signup wall. Most work, best
   conversion shape, needs a small state table.

**Recommendation: option 2 with a cap.** It keeps one billing rail, makes the cost visible instead
of hidden, and does not need new state. Read
`project_stripe_aggregate_usage_meter` before implementing either 2 or 3.

### IAM note

The Discord Lambda runs a deliberately least-privilege role: query one table, read one secret,
invoke itself. `/exposure` will need one more grant. Keep it narrow; this endpoint is public.

---

## 4. Where to list the bot

Two surfaces, both functioning and documented, which is more than Telegram's directories managed.

| Surface | What it needs |
|---|---|
| **top.gg** | Bot online during review, public, invitable, main commands working, no spam or NSFW in the description. No fee in the published guidelines. |
| **Discord App Directory** | Discord's own, official, separate from top.gg. Has eligibility requirements worth reading before spending time. |

Both are **submissions**, not servers. You do not join them. This tripped us up once already:
"App Directory and top.gg" was misread as communities to add the bot to.

---

## 5. Servers: how to approach, and why there is no link list here

**I am not listing invite URLs.** Discord invite links rot, and a wrong one is worse than none.
More to the point, fake invite links are themselves a common scam vector, so the correct habit,
and the one we tell users to follow, is to get an invite from the project's own official site
rather than from a third party. We should follow our own advice.

**The method, which matters more than a list:**

1. Pick communities where scam links in-channel are a known, unsolved moderation problem. In
   practice that means large NFT and DeFi project servers, wallet communities, and chain
   ecosystem servers.
2. Get the invite from the project's official website, never from a directory or a DM.
3. Join. Read the rules. Find the channel for bot or tool suggestions, which is usually named
   something like `#suggestions`, `#feedback`, or `#mod-tools`.
4. **Do not install anything.** You cannot add a bot to a server you do not administer, and
   attempting it is how the account gets flagged. Ask the admins.

**What to say to an admin**, which is the whole pitch in three sentences:

> We built a slash-command bot that checks links against criminal IOC feeds before your members
> click them. It deliberately does not request Message Content Intent, so it is structurally
> unable to read your channels, and the install asks for exactly two permissions: Send Messages
> and Embed Links. Happy to put it in a staging server first if you would rather see it before
> your main one.

The second sentence is the one that works. Crypto server admins are justifiably paranoid about
bots, and "we cannot read your server even if we wanted to" is the only claim that answers the
objection they actually have.

**Start with one.** A single server where members genuinely use it teaches us more than ten
installs nobody touches, and it gives us the one thing an admin asks for next: a reference.

---

## 6. Honest limit, recorded so it is not oversold later

**Consumer crypto Discord users have no budget. Discord will not produce direct revenue.**

Its realistic value is top-of-funnel awareness plus reaching admins who happen also to be security
leads somewhere that does have budget. Measured against the founder's stated constraint, which is
channel sales, this is a credibility and reach play. It is worth doing. It is not worth expecting a
customer from, and it should not displace CPPO or the AWS listing work.

See `project_channel_sales_is_the_constraint`: roughly twenty distribution surfaces already exist
against zero paying customers. This is the twenty-first.
