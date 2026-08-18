# Solana Mobile Community Discord: the post

*Written 2026-08-13. Companion to `discord_server_targets.md` (why this server first) and
`discord_midsize_pipeline_2026-08-13.md` (where the replies get converted).*

**Server verified live today: 68,882 members, 6,168 online.** That is a 9% online share on a server
of that size, which is a genuinely active room and not a member count left over from a launch.

---

## Before posting, two checks that are not optional

**1. Find the channel that permits a tool post, and confirm their self-promotion rules.**

`#support` is not a support channel in the sense you would assume and it blocks posting. That has
already tripped us up once. Read the rules channel, and if there is no channel explicitly for tools,
projects or showcases, **ask a moderator where this belongs rather than picking the closest match.**
One post in the wrong channel is the whole shot on a server this size.

**2. Confirm the top.gg listing status before choosing the link.**

The draft below uses the direct install link, which I verified returns 200 today:

`https://discord.com/oauth2/authorize?client_id=1536877675627552829&scope=bot+applications.commands&permissions=0`

top.gg returned 403 to an automated check, which is Cloudflare bot protection rather than evidence
either way, so I could not confirm whether the listing is live. **You know its real status.** If it
is approved and rendering, swap the link for the top.gg one, because a directory listing carries
more credibility to a cautious admin than a raw OAuth URL does. If it is still pending, the install
link above is correct and safe.

---

## The post

The ask is aimed at **admins reading in the audience**, never at Solana Mobile themselves. Asking
Solana Mobile to put an outside bot in their own flagship community reads as not understanding how
their server works.

```text
If you run a Discord where people paste links and wallet addresses, this might be useful to you.

We built a slash-command bot that checks a link, or an EVM / Solana / Bitcoin address, against criminal threat intelligence before anyone acts on it. Three commands: /scan for a URL or address, /scam for a what-to-do-right-now checklist, /exposure to privately check whether an email is in known breaches.

Two design decisions that matter more than the features:

It does not request the Message Content Intent, so it is structurally unable to read your channels. It only ever sees what someone types into a slash command. And it installs with zero permissions.

Replies are private to whoever ran the command unless they choose to share the result.

Free to add: https://discord.com/oauth2/authorize?client_id=1536877675627552829&scope=bot+applications.commands&permissions=0

Context on us, since a security bot asking for trust should say who it is: we are a RelayShield dev here, Crypto Shield Mobile is published in the dApp Store, and the same threat intelligence backs both. A clean result means nothing was found in the sources we queried. It is not proof something is safe, and we would rather say that up front than have someone lean on it.
```

**Why the third paragraph is the one that works.** Crypto server admins are justifiably paranoid
about bots, and every other line in that post is a feature. "We cannot read your server even if we
wanted to" is the only sentence that answers the objection they actually have. Do not cut it for
length.

**Why the last paragraph is there.** A security product posting into a security-conscious community
gets asked "who are you" immediately. Answering it before it is asked, and volunteering the limit of
the product in the same breath, is what separates this from the thirty other bot posts they have
seen. It also happens to be true, which is the only reason it works.

---

## After posting: the part that is the actual point

**Reply to everyone who responds, and treat every admin who asks a question as the real lead.**

That is not politeness, it is the mechanic. A self-selected admin who asked a question is worth ten
cold ones, and it is the reason for posting to a large server we can never convert directly. The
verified Tier 2 list exists for the ones who do not reply, and it is the fallback, not the plan.

Do not follow up in-channel if the post gets no traction. Take it to the mid-size list instead.

## Do not, in this post

- **Do not mention the AWS Marketplace listings or any price.** This audience has no budget and
  naming one converts a tool post into an ad.
- **Do not link the rsscan release or the npm article.** Different audience, and two asks in one
  post gets both ignored.
- **Do not name Arjen.** He is a reference for a direct admin conversation, with his permission, and
  not a name to drop in public.
