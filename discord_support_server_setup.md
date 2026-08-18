# Support server: rename and prepare for the top.gg listing

*Written 2026-08-12. This replaces "RelayShield Test" as the server linked from the listing.*

## The name

```text
RelayShield
```

Plain, no suffix. Not "RelayShield Support", not "RelayShield Community", not "RelayShield HQ".

**Why plain.** It has to match the bot name exactly, because a visitor clicking "support server" on
the listing needs to land somewhere that is obviously the same product. A suffix like "Support"
also frames it as a helpdesk, which sets the expectation that someone is staffing it. Nobody is.
"RelayShield" frames it as the product's home, where an announcement channel and a place to ask a
question is exactly what anyone expects.

It also leaves the door open. If the server ever becomes a real community, the name still works. If
we had called it "RelayShield Support" we would be renaming it again later, and the invite link on
the listing would be pointing at something with a stale identity.

---

## Rename it, and the four other things worth doing while you are in there

**Server Settings → Overview**

1. **Server Name** → `RelayShield`
2. **Server Icon** → upload `relayshield_discord_app_icon_1024.png` from the repo. Same mark as the
   bot, so the listing, the bot avatar and the server all match.

**Channels.** Delete or rename anything that says "test". A visitor arriving from a public listing
into a channel called `#test-2` learns something we would rather they did not. Four channels is
plenty:

| Channel | Purpose |
|---|---|
| `#announcements` | Read-only. New commands, incidents, changes. |
| `#start-here` | One pinned message: what the bot does, the invite link, the two commands worth trying. |
| `#bot-commands` | Where people can run `/scan` without cluttering anything. |
| `#support` | Questions. |

**Post one pinned message in `#start-here` so it is not empty.** An empty server reads worse than a
small one:

```text
**RelayShield checks links and wallet addresses against live criminal threat intelligence.**

Three commands, all of them private by default. Only you see the result unless you choose to share it.

`/scan` for a URL, or an EVM, Solana or Bitcoin wallet address
`/scam` for a checklist for when you think something is a scam right now
`/exposure` to privately check whether an email appears in known breaches

We do not request the Message Content Intent, so this bot is structurally unable to read your messages. It only ever sees what you type into a slash command.

Add it to your own server: https://discord.com/oauth2/authorize?client_id=1536877675627552829&scope=bot+applications.commands&permissions=0

A clean result means nothing was found in the sources we queried. It is not proof of safety.
```

---

## The invite link, and the one thing that actually breaks listings

**Make a permanent invite. This is the step that matters most.**

Discord's default invite expires after **7 days**. A top.gg listing pointing at an expired invite
is a dead link on a public page, and nothing tells you it has happened.

1. Right-click `#start-here` → **Invite People**
2. Click **Edit invite link**
3. **Expire after:** `Never`
4. **Max number of uses:** `No limit`
5. Generate, copy, and use that link in the top.gg **Support server** field

Do not use a link you generated earlier in this session unless you set those two values on it.

---

## Do not enable Community mode

Server Settings offers to convert it to a Community server. Skip it. It forces rules and
moderation-policy screens, a mandatory verification level, and a public-server checklist that costs
time and buys nothing for a support server this size. It can be enabled later if the server ever
grows into something.

---

## Quick check before you paste the link into top.gg

- [ ] Server name is `RelayShield`, no "test" anywhere in it
- [ ] Icon set
- [ ] No channel with "test" in the name
- [ ] `#start-here` has the pinned message
- [ ] Invite is set to never expire, unlimited uses
- [ ] Open the invite link in a private window. It should show a join screen for `RelayShield`, not
      an "Invalid Invite" page. **Check this in a private window, not your normal one**, since you
      are already a member and will see a different screen.

## One note on the bot's permissions in that server

The bot holds **zero** permissions there, deliberately, which is why I could not rename the server
for you. Keep it that way. "This bot requests no permissions" is one of the strongest lines in the
listing copy, and it stops being true the moment we grant it something for convenience.
