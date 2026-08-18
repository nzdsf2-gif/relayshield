# top.gg submission pack

*Every precondition re-verified live 2026-08-12. Paste from here, field by field.*

## Getting to the form

**Log in to top.gg with Discord first, then use the nav: `Add` in the header, then
`Add a Discord Bot`.** Do not type the URL.

Verified 2026-08-12: `https://top.gg/bot/new` is the correct path and it exists, but typing it
directly returned "Page not found" for the founder while an anonymous request to the same path
returns 200 and redirects to `/auth/login?redir=%2Fen%2Fbot%2Fnew`. top.gg resolves it against
session and locale state, so the nav link is the reliable route. For reference, genuinely wrong
paths behave differently: `/add`, `/bots/new` and `/apps/new` all return a real 404.

If the nav link also 404s, in order of likelihood: not actually signed in on that tab (the page
chrome renders for anonymous visitors, so check for your avatar top-right rather than a Login
button), top.gg terms not yet accepted on the account, or the Space selector has flipped off
Discord. The locale-prefixed `https://top.gg/en/bot/new` is the form top.gg's own redirect uses.

## Preflight, all verified today

| Check | State |
|---|---|
| `bot_public` | `true` |
| `bot_require_code_grant` | `false` |
| Terms of Service URL | `https://terms.relayshield.net` |
| Privacy Policy URL | `https://privacy.relayshield.net` |
| App icon | set |
| `/scan` on a URL | responds clean |
| `/scan` on a wallet address | responds clean |
| `/scam` | responds clean |
| `/exposure` | responds clean |
| Attribution key `discord-topgg` | registered, banner verified |
| Referer fallback from `top.gg` | verified, fires with no query string |

| Privacy policy covers the bots | **DONE**, approved and deployed 2026-08-12 |

Privacy policy is now section 5, "Chat Bots (Discord and Telegram)", live at
https://privacy.relayshield.net. It states that the app cannot read server messages, stores nothing,
logs no command content, and that replies are ephemeral by default. All four claims were verified
against `relayshield_discord_bot.py` before being written.

**Google Safe Browsing is deliberately not named** anywhere in this pack. Founder decision
2026-08-12. Note that the bot's own reply text still says "Flagged by Google Safe Browsing" and
"Not found in criminal IOC feeds or Safe Browsing", which a reviewer running `/scan` will see. That
is product copy rather than listing copy so it was left alone; say the word and I will change it to
match.

---

## Field 1: Bot ID

```text
1536877675627552829
```

## Field 2: Short description

```text
Check a link or wallet address before anyone in the server acts on it. Screens against 5.4M criminal indicators from 89 monitored channels.
```

## Field 3: Long description

```text
RelayShield screens links and wallet addresses against live criminal threat intelligence, so nobody in your server has to guess.

/scan takes a URL or an EVM, Solana or Bitcoin wallet address. Links are checked against our own criminal indicator corpus, then against additional reputation and domain-age signals. Addresses are screened against criminal wallet intelligence. A flagged result comes back with the reasons and a "Warn the channel" button, so the person who caught it can share it publicly and get the credit.

/scam gives a plain-language checklist for someone who thinks they are being scammed right now. No lookup, no waiting, works when the answer is needed in ten seconds.

/exposure privately checks whether an email address appears in known breaches. Always ephemeral, never shareable, and it never posts to a channel. Breach data is nobody else's business.

WHAT IT DOES NOT DO, DELIBERATELY

RelayShield does not request the Message Content Intent. It is structurally unable to read your server's messages, including messages sent while it is present. It only ever sees what someone explicitly types into a slash command. That is a design decision, not an oversight, and it is why an admin can install it without a policy conversation first.

It also requests zero permissions. Not "few". Zero. Slash command replies do not need Send Messages or Embed Links, including the public "Warn the channel" response, so we do not ask for them.

Replies are ephemeral by default. Only the person who ran the command sees the result, unless they choose to share it.

ONE HONEST CAVEAT

A clean result means nothing was found in the sources we queried. It is not proof of safety. A phishing domain can be hours old and in no database yet, and the bot says so in the reply rather than implying an all-clear.

Backed by RelayShield's live threat intelligence: 5.4M+ indicators of compromise from 89 monitored criminal Telegram channels and 20 authoritative feeds.
```

## Field 4: Categories (max 12, but do not pad)

These are real top.gg tag names, taken from their live tag vocabulary on 2026-08-12. Six accurate
ones beat twelve loose ones: a category we do not actually serve brings people who bounce, and
reads as tag-stuffing to a reviewer.

```text
security
utility
moderation
crypto
protection
tools
```

**Deliberately NOT selected**, even though they exist and are tempting: `antiraid`, `antinuke`,
`antispam`, `automoderation`, `verification`. Those all mean server-raid and member-management
tooling. We do none of it, and an admin who installs expecting raid protection gets a link scanner.

## Field 5: Languages

```text
English
```

This field means human languages the bot replies in, not programming languages. All replies are
English only.

## Field 6: Prefix

We have no prefix. Slash commands only. Leave blank if the form allows it; if it insists on a
value, use:

```text
/
```

## Field 7: Note for reviewer

This is a dedicated field on the real form, which is better than burying it in the description.
Put it here, and it can be removed from the long description.

```text
This is an interactions-only app. It uses Discord's HTTP interactions endpoint rather than a gateway connection, so it will not show as "online" in the member list. That is normal for interactions-only apps and Discord validated the endpoint itself.

All three slash commands respond immediately. Quickest test: /scan https://google.com or /scam.

The app deliberately does not request the Message Content Intent and requests zero permissions.
```

## Field 8: Invite URL

Should already be prefilled. Confirm it is exactly this, and that permissions stays `0`:

```text
https://discord.com/oauth2/authorize?client_id=1536877675627552829&scope=bot+applications.commands&permissions=0
```

## Field 9: Repository URL

**Leave blank.** The prompt ("Is your app open-source?") is inviting a claim we cannot make. The bot
is not open source. `rsscan` is, but that is a different product and putting its repo here would be
misleading.

## Field 10: Support URL

The field already supplies the `https://discord.gg/` prefix, so enter only the code:

```text
cKtE4Rn9Xd
```

Verified live 2026-08-12 against Discord's API: resolves, `expires_at` is null (never), guild name
`RelayShield`, icon set, description set.

## Field 11: Website URL

```text
https://api.relayshield.net/developers?source=discord-topgg
```

## Field 12: Support Server Link (optional)

**Skip it.** This dropdown lists servers already listed on top.gg's server directory, and ours is
not one. Field 10 already carries the invite. Listing the server separately is its own submission
and is not worth doing yet.

## Field 13: Add Link (optional)

The dropdown offers social platforms only: Twitter, Telegram, TikTok, Instagram, Facebook, Reddit,
YouTube. There is no generic "Website" type, so the blog goes in Field 11 and nowhere else.

**Add exactly one:**

```text
Link type: Telegram    Link URL: https://t.me/RelayShield_bot
```

**Do NOT add Twitter.** @RelayShieldHQ is suspended. A dead link to a suspended account on a public
listing is worse than an empty field.

**Do NOT add the Telegram channel** `t.me/RelayShield`, even though it is live and on-topic. Checked
2026-08-12: it publicly displays **4 subscribers**. Anyone who clicks sees that number and reads it
as abandoned.

The bot link is the only one of the seven that shows a real working product without exposing a weak
metric. Its Telegram preview reads "Check a link, message or screenshot for scams. Free...", which
reinforces the same claim the listing makes.

Leaving the field empty is also fine. An empty socials row is neutral; a wrong entry costs us.

## Field 14: Banner

Upload `relayshield_discord_banner_680x240.png`. Confirmed 680x240, which is the size top.gg asks
for.

---

## Submit checklist

- [x] Privacy policy updated to cover the bots, and deployed
- [ ] Support server decided and linked
- [ ] Banner uploaded
- [ ] Reviewer note left in the long description, so "offline" is not read as broken
- [ ] Invite link tested in a browser: it should offer to add the bot and request no permissions

Then submit and wait. It goes into a human review queue.

## When it is approved

Tell me and I will:

1. Check the live listing renders our description and banner correctly
2. Confirm the website link still carries `?source=discord-topgg` and has not been rewritten, which
   is exactly what Medium did to us today
3. Start the `discord-topgg` counter in the weekly CloudWatch query

## What this does and does not buy us

**It does not unlock the Discord App Directory.** That needs app verification, verification opens at
**75 servers**, and we are in **1**. The directory that would bring servers is gated behind already
having servers.

**And a directory listing is a lottery ticket, not a channel.** Four of five Telegram bot
directories turned out dead or paid when we actually checked. top.gg is alive, but the real growth
unit here is one server admin installing the bot, because that single act exposes every member of
their server. An hour spent messaging three crypto-server moderators is worth more than an hour
spent polishing this listing.

Submit it because it is cheap and permanent. Do not wait on it.
