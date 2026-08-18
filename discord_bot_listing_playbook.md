# Listing the RelayShield Discord bot: top.gg and the Discord App Directory

*Written 2026-08-12. Every fact about our own app below was read from the live Discord API today,
not from notes.*

## Short answer to "this will enable initial surface discovery, right?"

**Half of it will. The other half is not open to us yet, and that is worth knowing before you spend
an evening on it.**

| Surface | Can we submit today? |
|---|---|
| **top.gg** | **Yes.** Two blockers, both fixable in about ten minutes, listed below. |
| **Discord App Directory** | **No.** It requires app verification, and verification eligibility starts at **75 servers**. We are in **1**. |

The App Directory is a chicken-and-egg by design: [Discord's own documentation says an app must be
verified before the App Directory section even appears in the Developer
Portal](https://support-dev.discord.com/hc/en-us/articles/6378525413143-App-Directory-App-profile-pages),
and [verification opens at the 75-server
mark](https://support-dev.discord.com/hc/en-us/articles/23926564536471-How-Do-I-Get-My-App-Verified).
So the directory that would bring us servers is gated behind already having servers. **It is a
milestone to aim at, not a task to schedule.**

**And set expectations on top.gg honestly.** Four of five Telegram bot directories turned out dead
or paid when we actually checked them. top.gg is genuinely alive, but a listing on a bot directory
is a lottery ticket, not a channel. The real growth unit for this bot is **one server admin
installing it**, because that single act exposes every member of their server. An hour spent
messaging three crypto-server moderators is worth more than an hour spent polishing a directory
entry.

---

## Verified state of our app, read live 2026-08-12

| Field | Value | Ready? |
|---|---|---|
| Application ID | `1536877675627552829` | |
| Name | RelayShield | yes |
| `bot_public` | `true` | yes, required by top.gg |
| `bot_require_code_grant` | `false` | yes, required |
| Icon | set | yes |
| Description | set, leads with the link and wallet check | yes |
| Tags | moderation, security, safety, utility, crypto | yes |
| Interactions endpoint | set and Discord-validated | yes |
| Commands | `/scan`, `/scam`, `/exposure` all registered and working | yes |
| `install_params` | `bot` + `applications.commands`, permissions `0` | **fixed today** |
| **Terms of Service URL** | **null** | **BLOCKER** |
| **Privacy Policy URL** | **null** | **BLOCKER** |
| Cover image / banner | null | not blocking, but do it |
| Servers | **1** (RelayShield Test) | blocks App Directory only |

---

## Blocker 1: the two legal URLs, and a trap

Both directories want a linked Terms of Service and Privacy Policy, and Discord names them as an
App Directory eligibility requirement outright. **Both fields are currently null on our app.**

The pages themselves already exist and return 200:

- https://terms.relayshield.net
- https://privacy.relayshield.net

**The trap, found today:** you cannot set these through the API with a bot token. A `PATCH` to
`/applications/@me` including `terms_of_service_url` and `privacy_policy_url` returns **HTTP 200
with the fields silently dropped**. It does not error. Re-reading the app shows them still null. In
the same call `install_params` persisted correctly, so it looks like a partial success and reads
like a success. **These two are Developer Portal only.**

### What you need to do (about two minutes)

1. https://discord.com/developers/applications/1536877675627552829/information
2. **Terms of Service URL** → `https://terms.relayshield.net`
3. **Privacy Policy URL** → `https://privacy.relayshield.net`
4. Save.

Tell me when it is done and I will confirm both are set by reading the API back.

## Blocker 2: the bot must be online during review

[top.gg declines a bot that is not online when a reviewer tries
it.](https://support.top.gg/hc/en-us/articles/23135162935708-How-to-Add-Your-Bot)

Ours is a Lambda behind API Gateway rather than a gateway-connected bot, so **it has no presence
and will show as offline in the member list.** That is normal for an interactions-only app and
Discord treats it as valid, but a human reviewer may read "offline" as broken.

**Mitigation: say so in the submission.** One line in the description prevents the whole problem:

> RelayShield is an interactions-only app. It uses Discord's HTTP interactions endpoint rather than
> a gateway connection, so it does not appear "online" in the member list. All three slash commands
> respond immediately. It deliberately does not request Message Content Intent and cannot read
> channel messages.

That last sentence is worth including everywhere. It is our strongest line with a server admin.

---

## top.gg submission, step by step

**Start:** https://top.gg/bot/new while logged in with the Discord account that owns the app.

### Fields, ready to paste

**Bot ID:** `1536877675627552829`

**Short description** (the card, keep it tight):

> Check a link or wallet address before anyone in the server acts on it. Screens against 5.4M
> criminal indicators from 89 monitored channels.

**Long description:**

> **RelayShield screens links and wallet addresses against live criminal threat intelligence, so
> nobody in your server has to guess.**
>
> **`/scan`** takes a URL or an EVM, Solana or Bitcoin wallet address. Links are checked against our
> own criminal indicator corpus, then against additional reputation and domain-age signals. Addresses are
> screened against criminal wallet intelligence. A flagged result comes back with the reasons, and a
> **Warn the channel** button so the person who caught it can share it publicly and get the credit.
>
> **`/scam`** gives a plain-language checklist for someone who thinks they are being scammed right
> now. No lookup, no waiting, works when the answer is needed in ten seconds.
>
> **`/exposure`** privately checks whether an email address appears in known breaches. Always
> ephemeral, never shareable, and it never posts to a channel. Breach data is nobody else's
> business.
>
> **What it does not do, deliberately:**
>
> RelayShield does not request Message Content Intent. It structurally cannot read your server's
> messages. It only ever sees what someone explicitly types into a slash command. That is a design
> decision, not an oversight, and it is why an admin can install it without a policy conversation.
>
> Replies are ephemeral by default. Only the person who ran the command sees the result unless they
> choose to share it.
>
> **One honest caveat:** a clean result means nothing was found in the sources we queried. It is not
> proof of safety. A phishing domain can be hours old and in no database yet, and we say so in the
> reply rather than implying an all-clear.
>
> Backed by RelayShield's live threat intelligence: 5.4M+ indicators of compromise from 89 monitored
> criminal Telegram channels and 20 authoritative feeds.
>
> **Note for reviewers:** this is an interactions-only app. It uses Discord's HTTP interactions
> endpoint rather than a gateway connection, so it does not show as "online" in the member list. All
> three commands respond immediately.

**Tags:** `moderation`, `security`, `safety`, `utility`, `crypto`

**Prefix:** slash commands only, no prefix.

**Invite link:**

```
https://discord.com/oauth2/authorize?client_id=1536877675627552829&scope=bot+applications.commands&permissions=0
```

Permissions `0` is correct and worth understanding: interaction responses do not need Send Messages
or Embed Links, including the public "Warn the channel" response. **Asking for zero permissions is a
selling point on a security bot.** Do not pad it.

**Website:** https://api.relayshield.net/developers?source=discord-topgg
**Support server:** you will need to decide whether to open the test server or create a proper one.
top.gg does not require it, but a listing without one looks abandoned.

### Before you hit submit, check each of these

- [ ] ToS and Privacy URLs set in the Developer Portal (blocker 1)
- [ ] Bot is public and invitable, `bot_require_code_grant` off. Both already correct.
- [ ] All three commands respond. Test each in a server.
- [ ] The reviewer note about being interactions-only is in the description.
- [ ] No admin permission requested. Ours asks for zero.
- [ ] Banner uploaded. We already have `relayshield_discord_banner_680x240.png` in the repo.

Then wait. It goes into a review queue and a human works through it.

---

## What to do instead, while the App Directory is out of reach

The 75-server gate is the real constraint, so the work that matters is whatever gets us from 1
server to 75. In rough order of expected return:

1. **Direct admin outreach to crypto and security servers.** One admin equals one whole community.
   This is the highest-leverage hour available and it is not a directory.
2. **The video demo** already on the priority list. A 30-second clip of `/scan` flagging a real
   drainer address is more convincing than any listing copy, and it is reusable on LinkedIn.
3. **Other bot lists** as low-effort submissions: discord.bots.gg, discordbotlist.com. **Check
   whether each is alive and free before writing a single word of copy.** That is the lesson from
   the Telegram directories, where four of five were dead or paid and we found out after doing the
   work.
4. **Cross-promote from Telegram.** There are real users on that bot. They are the cheapest source
   of the first handful of Discord servers.

## After a listing goes live

Add the attribution key so we can tell whether any of it worked. `?source=discord-topgg` is **not
currently registered** in `_SOURCE_BANNERS`, and an unregistered key logs `unmatched:` and renders
no banner, which is exactly how `?source=rsscan` shipped broken. Tell me when the listing is up and
I will register it before the link goes anywhere public.

Sources:
- [How Do I Get My App Verified? (Discord)](https://support-dev.discord.com/hc/en-us/articles/23926564536471-How-Do-I-Get-My-App-Verified)
- [App Directory: App profile pages (Discord)](https://support-dev.discord.com/hc/en-us/articles/6378525413143-App-Directory-App-profile-pages)
- [App Directory: App Content Requirements Policy (Discord)](https://support-dev.discord.com/hc/en-us/articles/9489299950487-App-Directory-App-Content-Requirements-Policy)
- [How to Add Your Bot (top.gg)](https://support.top.gg/hc/en-us/articles/23135162935708-How-to-Add-Your-Bot)
- [How the Project Reviewal Process Works (top.gg)](https://support.top.gg/hc/en-us/articles/23135298323996-How-the-Project-Reviewal-Process-Works)
- [Discord Bot Guidelines (top.gg)](https://support.top.gg/support/solutions/articles/73000502502-bot-guidelines)
