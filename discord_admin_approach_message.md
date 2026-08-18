# The admin approach: Famous Fox Federation, DRiP, Claynosaurz, Parcl

*Written 2026-08-13. Targets and ranking in `discord_midsize_pipeline_2026-08-13.md`.*

**This is a permission ask, not a post.** That distinction is the whole strategy. Reading Solana
Mobile's rules on 2026-08-13 established that a public post carrying a bot invite is advertising and
breaches most crypto servers' self-promo rules. Asking an admin whether you may is the one approach
no such rule prohibits.

---

## Before you send anything, per server

Ten minutes each, and skipping it is how a good target becomes a warning.

1. **Get the invite from the project's official website.** Three of fifteen guessed vanity codes
   resolved to unrelated servers on 2026-08-13, one of them a social-media-botting service.
2. **Read the rules channel.** Specifically for two things: a self-promotion policy, and whether
   they prohibit DMing the team. Solana Mobile's rule 2 is "the team will NEVER DM you, don't DM
   them either", and breaking that with the exact people whose goodwill you want is the worst
   possible opening.
3. **If a bot-request or suggestions channel exists, use it instead of a DM.** A designated channel
   is consent by construction. A DM is an interruption you have to justify.
4. **Check the member list for an existing scam bot, SecurityBot especially.** If one is already
   installed, do not open with "we do what they do". Open by asking what it misses.
5. **Read two weeks of their general channel.** If nobody is posting "is this link real?", the
   problem you are solving is not one they feel, and this is the wrong server.

---

## The message

Short on purpose. An admin decides in the first two lines whether this is a person or a campaign.

```text
Hi, I run a small security project and I would like your permission before doing anything, rather than just dropping a link in your server.

We built a Discord bot that checks a link, or an EVM / Solana / Bitcoin address, against criminal threat intelligence before someone acts on it. Three slash commands, and replies are private to whoever ran them unless they choose to share.

The part I would want you to check before saying yes: it does not request the Message Content Intent, so it is structurally unable to read your channels. It only ever sees what someone types into a slash command. It installs with zero permissions.

If it is of interest I am happy to put it in a staging server first so you can try it without touching your main one. And if it is not a fit, no problem at all, thanks for reading.
```

---

## Famous Fox Federation, the specific version. Send this one.

**Route corrected 2026-08-14.** The earlier plan was to post in `#collab-inquiry`. Reading the
channel shows that is wrong: it holds exactly one message, from 25 September 2022, with 1,091
reactions and nothing after it in three years. It is a read-only signpost, not a discussion channel,
and it routes collaboration asks to a DM.

**Contact Draxxts, fallback Sociosa.** The pinned post names both for "deeper collaboration
including: an AMA, NFT collaboration, utility offering". A free security bot is a utility offering,
so that is the right bucket. Draxxts over Sociosa because Draxxts wrote and later edited that post,
which is the only evidence either account is currently active, and carries the Active Developer
badge, which suits a bot install over a marketing collab.

**Do not use the `@WL Seeker` route.** That is whitelist-for-mint traffic. It would file this next to
every project asking for WLs, which is the opposite of the framing that works.

**Send from Cryptonomicon.** More important now that it is a DM than it was for a post.

**`#slyfox-scam-reporters` changes the opening, and it is the best thing we have.** Founder found it
2026-08-14. It is a channel where members manually report scams: screenshots, raw user IDs pasted as
bare numbers, and in one case a live impersonation attempt with a Solana address being pushed at
someone. That answers step 5 of the checklist below without having to guess. **They already decided
this problem is worth a channel.** The bot does not introduce a new idea to them, it automates one
they are doing by hand, which is a far smaller yes.

It also means the pitch is no longer "you have a scam problem", which is presumptuous, but "you have
a scam reporting channel", which is a fact and flattering.

```text
Hi Draxxts, your #collab-inquiry post says to DM you or Sociosa about a utility offering, so I hope this is the right door.

I run a small security project, and I wanted your permission before doing anything rather than dropping a link in your server.

I've been reading #slyfox-scam-reporters. People are doing that work by hand right now, posting screenshots and pasting user IDs, and someone still has to eyeball each one. We built a Discord bot that does the checking part: give it a link, or an EVM / Solana / Bitcoin address, and it checks it against criminal threat intelligence before anyone acts on it. Three slash commands, replies are private to whoever ran them unless they choose to share, and it is free for your members.

The part worth checking before you say yes: it does not request the Message Content Intent, so it is structurally unable to read your channels. It only ever sees what someone types into a slash command, and it installs with zero permissions. You can verify both yourself on the bot's profile.

One housekeeping note so the handles make sense: this is my own account. The bot's dev account is RelayShieldAdmin, which is only days old, and I would rather write to you from an account with some history behind it.

If it is of interest I am happy to put it in a staging server first, so you can try it without touching Famous Fox. And if it is not a fit, no problem at all, thanks for reading.
```

**The opening line is the highest-value part.** It proves you read their process and followed it,
which is the single thing separating this from the DMs they delete. Do not cut it for length.

**The housekeeping note is new** and exists because the account you send from is not the account that
owns the bot. An admin who spots that mismatch on their own reads it as evasion. Named up front, it
reads as care.

---

## Overtime, 2026-08-14. Channel decision and message.

**Send to `#open-a-ticket`. Name `#dev-and-integrations` inside the message as where you would post.**

Their rule is "no self-promotion without permission". That phrasing is the whole answer: permission
is obtainable, so there must be a route to ask for it, and `#open-a-ticket` is the designated route
to reach the team. **A request for permission sent through the sanctioned intake channel cannot
itself breach a no-self-promo rule.** Same logic that made `#collab-inquiry` the right door at Famous
Fox.

**Why not post straight into `#dev-and-integrations`:** it is the natural home for the bot and it is
where the post should eventually go, but posting there first is the self-promotion the rule covers.
Ask, then post. One extra step buys the difference between a welcome post and a warning.

> **Check whether `#dev-and-integrations` is archived before naming it.** In the sidebar it appears
> beneath an `AGORA-ARCHIVE-5` category header. If it sits inside that category it is a dead room and
> naming it makes you look like you skimmed. If it is live, it is the perfect venue.

**Ruled out:** `#report-scammers` is for reports, so do not pitch in it, only cite it.
`#overtime-team` is internal hiring announcements, correctly identified by the founder.
`#plz-admin-resolve` is for disputes. `#announcements` and `#promotions` are read-only.

### The honesty problem specific to Overtime, and it matters

**The scams in `#report-scammers` are not the scams this bot catches.** The example there is a betting
tout: a stranger DMs "Hey fam", asks if you want a good win tonight, and posts a screenshot of a
winning FanDuel parlay. That is social engineering with an image. **The bot cannot look at a username
or a screenshot and tell you the person is a fraud**, and implying otherwise breaks the playbook rule
against claiming it prevents scams.

What it genuinely does is check the **link or deposit address** those approaches end in, which is
where the money actually moves. **Say that limit out loud in the message.** With an audience that
watches people get worked every day, volunteering the limitation is what makes the rest credible.

This is a real difference from Famous Fox, where `#slyfox-scam-reporters` had a live Solana address
being pushed at someone and the product fit was direct.

### The message

```text
Hi, I wanted to ask permission before posting anything, since the rules say no self-promotion without it.

I've been reading #report-scammers. We built a Discord bot that checks a link, or an EVM / Solana / Bitcoin address, against criminal threat intelligence before someone acts on it. Three slash commands, replies are private to whoever ran them unless they choose to share, and it's free for your members.

To be straight about what it does and doesn't do: it won't tell you that a stranger sliding into your DMs offering locks is a tout. It checks the thing they eventually send you, the link or the deposit address, which is usually where those end up.

The part worth checking before you say yes: it doesn't request the Message Content Intent, so it's structurally unable to read your channels. It only ever sees what someone types into a slash command, and it installs with zero permissions. You can verify both on the bot's profile.

If it's of interest, #dev-and-integrations looks like the right home for a post, or I'm happy to put it in a staging server first so you can try it without touching Overtime.

One housekeeping note so the handles make sense: this is my own account, and the bot's dev account is RelayShieldAdmin.

And if it's not a fit, no problem at all, thanks for reading.
```

**Do not call Overtime a Solana community.** It is EVM, on Optimism, Arbitrum and Base. The bot
covers both so nothing breaks, but getting a project's own chain wrong in the first message is an
avoidable own goal.

### Why each part is there

**"I would like your permission before doing anything."** Opens by naming the thing they are worried
about. Every admin has been spammed by bot developers this week.

**The third paragraph is the one that works.** Crypto admins are justifiably paranoid about bots, and
"we cannot read your server even if we wanted to" is the only claim that answers the objection they
actually have. It is also verifiable: they can check the bot's requested intents themselves. Do not
cut this for length.

**The staging-server offer** converts "let a stranger's bot into my community" into "look at a thing
in a sandbox", which is a much smaller yes.

**The explicit easy no** costs one line and measurably raises reply rates. It also means a no is a
clean no rather than silence you spend a week wondering about.

## Do not, in this message

- **No pricing, no API, no bundle.** This is a free bot for their members. The moment money appears
  it is a sales pitch and the answer is no.
- **No rsscan, no blog links, no second ask.** One ask. A second halves the first.
- **Do not name Arjen** unless they ask who else uses it, and only with his permission.
- **Do not claim it prevents scams.** It checks against known intelligence and a clean result is not
  proof of safety. Overclaiming to a suspicious admin ends the conversation.
- **Never attempt to add the bot yourself.** You cannot add a bot to a server you do not administer,
  and trying is how an account gets flagged.

## If they say yes

Send the zero-permission install link, then **go quiet**. Do not follow up with feature suggestions
or ask them to promote it. The install is the win. The next thing you want from them is a reference
in three months, and that is earned by the bot working, not by more messages.

## If they say no

Thank them and leave. A polite no from an admin who now knows the product exists is worth more than
an argument, and these communities talk to each other.

## Measuring it

`relayshield_discord_installs.py` records every server the bot is in, so an install shows up in the
next run and in the Monday report. Baseline on 2026-08-13 was **1 server, our own, 0 external
installs, 74 short of the App Directory threshold.** That is the number this whole exercise moves.
