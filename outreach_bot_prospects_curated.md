# Outreach: the twelve worth sending first

*Built by hand from the 2026-09-03 sweep (`--stars 5..50`, 205 prospects, 64 with a contact
channel). This is the shortlist, not the whole file: `outreach_bot_prospects.md` is generated and
holds 40. Send from this one.*

---

## Rules that apply to every message below

**Never assert anything about their security.** Every draft is an offer of a capability, keyed to
what their own README says the bot does. We can read a README. We cannot see anyone's backend, and
"we analysed your app and found exposures" from an unknown security vendor is one word away from an
extortion email.

**Check the evidence line before you send.** It says what the classifier matched. If it looks wrong
for that repo when you open it, drop the prospect rather than softening the message.

**Send a few a day, by hand.** Volume is not the lever. A burst of near-identical mail is how a
sending domain gets blocked, and we have one.

**The five with real inboxes go first.** A website is a contact channel only if that page carries a
form or an address; if it does not, skip rather than opening a GitHub issue on a stranger's repo.

---

# Group A: real inboxes. Send these first.

## 1. M41NUL/all-media-downloader

- **Contact:** `devmainulislam@gmail.com`
- **Repo:** https://github.com/M41NUL/all-media-downloader
- **Score 71** · tags `links, files`
- **Rationale:** a downloader takes a URL from a user and fetches it. That is our link check's exact
  case, and it is the one category where a bad link is not just a scam risk to the user but a fetch
  the bot itself performs. Highest-fit prospect on the list.

```text
Subject: A link check for all-media-downloader

Hi,

Your bot takes a URL from a user and fetches it, which is the case our link check exists for. One call returns a verdict plus a ready-to-send reply for a link that is in a criminal IOC corpus, on Google Safe Browsing, or on a domain registered days ago.

    v = check(message.text)   # returns a verdict and a ready-to-send reply

No signup, no key and no card for the first calls. It never throws, and it never tells your users something is safe, only that nothing is known against it. That matters for a downloader: the bot fetches what the user pastes, so a verdict before the fetch is worth more than one after.

https://github.com/nzdsf2-gif/relayshield/tree/main/widget

If it looks useful and you would rather see it than wire it up, say so and I will open a PR against M41NUL/all-media-downloader with the handler wired in, and you can close it if you hate it.

Andrew
RelayShield
```

## 2. Matt0550/TagEveryoneTelegramBot

- **Contact:** `mail@matteosillitti.com`
- **Repo:** https://github.com/Matt0550/TagEveryoneTelegramBot
- **Score 71** · tags `wallets, payments, identity`
- **Rationale:** a maintainer with a personal domain and a mail address on it is a developer who
  answers mail. The tags suggest group tooling with a payment or donation path rather than a wallet
  product, so lead with the link check and mention addresses second.

```text
Subject: A link and address check for TagEveryoneTelegramBot

Hi,

Your bot runs inside group chats, which means it sits next to whatever links and addresses members paste. We publish a check for exactly that: one call, and you get a verdict plus a ready-to-send reply for a link or a wallet address, across EVM, Solana, TON and Bitcoin.

    v = check(message.text)   # returns a verdict and a ready-to-send reply

No signup, no key and no card for the first calls. It never throws, and a failed check reports as unchecked rather than as safe.

https://github.com/nzdsf2-gif/relayshield/tree/main/widget

If it looks useful and you would rather see it than wire it up, say so and I will open a PR against Matt0550/TagEveryoneTelegramBot with the handler wired in, and you can close it if you hate it.

Andrew
RelayShield
```

## 3. cubepy/cubepay-doc

- **Contact:** `info@cubevps.ir`
- **Repo:** https://github.com/cubepy/cubepay-doc
- **Score 68** · tags `wallets, payments, identity`
- **Rationale:** the name says payments and the contact is a hosting company, so this is a product
  with a business behind it rather than a weekend project. Address screening is the direct fit.
  **Check the sanctions position before sending:** an `.ir` company is one where payment tooling may
  carry restrictions we have not looked at. This one is worth ten minutes of your judgement first.

```text
Subject: An address check for cubepay

Hi,

Your product handles wallet addresses and payments. We publish an address check that covers EVM, Solana, TON and Bitcoin in one call, and returns a verdict plus a ready-to-send reply.

    v = check(message.text)   # returns a verdict and a ready-to-send reply

No signup, no key and no card for the first calls. It never throws, and a failed check reports as unchecked rather than as safe.

https://github.com/nzdsf2-gif/relayshield/tree/main/widget

If it looks useful and you would rather see it than wire it up, say so and I will open a PR against cubepy/cubepay-doc with the handler wired in, and you can close it if you hate it.

Andrew
RelayShield
```

## 4. mozharov/zapgram

- **Contact:** `zapgram@getalby.com`
- **Repo:** https://github.com/mozharov/zapgram
- **Score 66** · tags `wallets, payments, identity`
- **Rationale:** the strongest signal on the whole list, and it is in the contact itself. That is a
  Lightning address, so this is a Bitcoin Lightning bot moving real value between strangers. **Note
  the honest limit:** our address check covers EVM, Solana, TON and on-chain Bitcoin, not Lightning
  invoices. Say so rather than implying coverage we do not have. The link check still applies to
  every URL a user pastes.

```text
Subject: A link check for zapgram, and an honest note on Lightning

Hi,

Your bot moves value between people, so the two things a user pastes right before they lose some are a link and an address. We publish a check for both: one call, a verdict, and a reply you can send as is.

    v = check(message.text)   # returns a verdict and a ready-to-send reply

To be straight with you about the limits, because you will find them in five minutes anyway: the address side covers EVM, Solana, TON and on-chain Bitcoin. It does not decode Lightning invoices, so for zapgram the link check is the part that earns its place today.

No signup, no key and no card for the first calls. It never throws, and it never tells your users something is safe, only that nothing is known against it.

https://github.com/nzdsf2-gif/relayshield/tree/main/widget

Andrew
RelayShield
```

## 5. anishalx/SpyStroke

- **Contact:** `s7vdi6a8l@mozmail.com`
- **Repo:** https://github.com/anishalx/SpyStroke
- **Score 67** · tags `wallets, identity`
- **Rationale:** the address is a Firefox Relay mask, so it forwards to a real inbox and the
  maintainer deliberately keeps their address private. Fine to write to, and worth keeping the
  message short. **Read the repo before sending:** the name suggests keystroke tooling, and if it
  is offensive software we do not want the association. This is the one on the list most likely to
  be a skip.

```text
Subject: A link and address check for SpyStroke

Hi,

If your bot takes links or wallet addresses from users, we publish a one-call check for both: a verdict and a ready-to-send reply, across EVM, Solana, TON and Bitcoin for addresses, and our IOC corpus plus Safe Browsing and domain age for links.

    v = check(message.text)   # returns a verdict and a ready-to-send reply

No signup, no key and no card for the first calls.

https://github.com/nzdsf2-gif/relayshield/tree/main/widget

Andrew
RelayShield
```

---

# Group B: websites. Find the form or an address on the page first.

## 6. TegroTON/ai-telegram-pay-miniapp

- **Contact:** https://tegro.money (a payments company, so there will be a support address)
- **Repo:** https://github.com/TegroTON/ai-telegram-pay-miniapp
- **Score 67** · tags `wallets, payments, identity`
- **Rationale:** **the best strategic fit on the list.** A TON payments company, publishing a
  Mini App, with a second repo in the same sweep (`SMMPanel-SMOService-Telegram-Bot`, score 69).
  TON is Telegram's own chain and our address check covers it. One integration here is worth ten
  hobby bots, and they are a company that can also become a paying customer rather than only a
  free-tier user.

```text
Subject: TON address screening for the ai-telegram-pay Mini App

Hi,

You are publishing a Telegram Mini App that handles payments on TON. We publish an address check that covers TON natively, alongside EVM, Solana and Bitcoin: one call, a verdict, and a ready-to-send reply.

    v = check(message.text)   # returns a verdict and a ready-to-send reply

The first calls need no signup, no key and no card, so it costs a few minutes to find out whether it is useful. It never throws, and a failed check reports as unchecked rather than as safe, which matters when it sits in a payment path.

If it is useful at volume rather than as a widget, there is a keyed API behind it with the same checks plus breach and infostealer exposure, and I would rather talk about that than sell you anything today.

https://github.com/nzdsf2-gif/relayshield/tree/main/widget

Andrew
RelayShield
```

## 7. bbbuilt/fragment-stars-api

- **Contact:** https://fragment-api.space
- **Repo:** https://github.com/bbbuilt/fragment-stars-api
- **Score 64** · tags `wallets, payments, identity`
- **Rationale:** Fragment and Telegram Stars, so this is squarely inside Telegram's own payment
  economy and its users are handling TON addresses. Same pitch as Tegro, smaller operation.

```text
Subject: An address check for fragment-stars-api

Hi,

Your API sits in Telegram's own payment economy, where the addresses users paste are TON addresses. We publish an address check that covers TON natively, plus EVM, Solana and Bitcoin: one call, a verdict, and a ready-to-send reply.

    v = check(message.text)   # returns a verdict and a ready-to-send reply

No signup, no key and no card for the first calls. It never throws, and a failed check reports as unchecked rather than as safe.

https://github.com/nzdsf2-gif/relayshield/tree/main/widget

Andrew
RelayShield
```

## 8. opencrew-ai/oncellclaw

- **Contact:** https://oncell.ai/claw
- **Repo:** https://github.com/opencrew-ai/oncellclaw
- **Score 71** · tags `links, files, wallets, payments, identity`
- **Rationale:** the broadest capability match in the sweep, and an AI company, which makes the
  second half of our catalogue relevant too: MCP registry risk and prompt-injection exposure are
  checks an agent product cares about and a normal bot does not. Lead with the widget, mention the
  agent-side checks once.

```text
Subject: A link and address check for oncellclaw, and an agent-side one

Hi,

Your product takes links, files, addresses and signups from users, which is the case our check exists for. One call returns a verdict and a ready-to-send reply for a link or a wallet address.

    v = check(message.text)   # returns a verdict and a ready-to-send reply

No signup, no key and no card for the first calls.

Since you are building on agents rather than only bots, one other thing worth knowing about: the same API screens MCP servers for typosquats and reputation, and checks whether an identity shows up in prompt-injection-sourced breach data. Those are keyed rather than open, and they are the checks an agent product needs that an ordinary bot does not.

https://github.com/nzdsf2-gif/relayshield/tree/main/widget

Andrew
RelayShield
```

## 9. CarakaDev/caraka

- **Contact:** https://caraka.dev
- **Repo:** https://github.com/CarakaDev/caraka
- **Score 72** · tags `wallets, identity, ugc`
- **Rationale:** second highest score, a developer with their own domain, and user-generated content
  alongside wallets, which means links from strangers reach other users.

```text
Subject: An address and link check for caraka

Hi,

Your bot handles wallet addresses and carries content posted by users. We publish a check for both cases: one call, a verdict, and a ready-to-send reply, covering EVM, Solana, TON and Bitcoin for addresses, and our criminal IOC corpus plus Safe Browsing and domain age for links.

    v = check(message.text)   # returns a verdict and a ready-to-send reply

No signup, no key and no card for the first calls. It never throws, and a failed check reports as unchecked rather than as safe.

https://github.com/nzdsf2-gif/relayshield/tree/main/widget

Andrew
RelayShield
```

## 10. masudur-rahman/khorcha-pati

- **Contact:** https://khorcha-pati.mrahman.xyz/
- **Repo:** https://github.com/masudur-rahman/khorcha-pati
- **Score 69** · tags `wallets, payments, identity`
- **Rationale:** an expense tracker with a live deployment, so there is a running product and a
  maintainer who ships. Payments plus identity means the free-tier breach check is as relevant as
  the widget.

```text
Subject: A link and address check for khorcha-pati

Hi,

Your bot handles money and signups. The check we publish screens the two things a user pastes right before they lose some: a link, or a wallet address. One call, a verdict, and a reply you can send as is.

    v = check(message.text)   # returns a verdict and a ready-to-send reply

No signup, no key and no card for the first calls, so it costs a few minutes to find out whether it is useful to you.

https://github.com/nzdsf2-gif/relayshield/tree/main/widget

Andrew
RelayShield
```

## 11. antlis/tg-media-bot

- **Contact:** https://antlis.is-a.dev/tg-media-bot
- **Repo:** https://github.com/antlis/tg-media-bot
- **Score 71** · tags `links, files, identity, ugc`
- **Rationale:** same shape as prospect 1: users paste links, the bot fetches them. Written in
  JavaScript by the look of the toolchain, so the draft uses the JS snippet.

```text
Subject: A link check for tg-media-bot

Hi,

Your bot takes links from users and fetches what is behind them, which is the case our link check exists for. One call returns a verdict and a ready-to-send reply for a domain that is in a criminal IOC corpus, on Safe Browsing, or newly registered.

    const v = await check(ctx.message.text);

No signup, no key and no card for the first calls. It never throws, and it never tells your users something is safe, only that nothing is known against it.

https://github.com/nzdsf2-gif/relayshield/tree/main/widget

Andrew
RelayShield
```

## 12. Exdenta/OinkAIJobSearch

- **Contact:** https://oinkjobsearch.com
- **Repo:** https://github.com/Exdenta/OinkAIJobSearch
- **Score 64** · tags `files, payments, identity, ugc`
- **Rationale:** a job-search bot handles CVs and job links, and recruitment is one of the most
  heavily phished categories there is: fake recruiter links are a standing infostealer delivery
  route. The link check is the fit, and the framing writes itself without ever claiming they have a
  problem.

```text
Subject: A link check for OinkAIJobSearch

Hi,

Your bot puts job links in front of people. Recruitment is one of the categories criminal campaigns imitate most, so a link check before a user clicks is worth having: one call, a verdict, and a ready-to-send reply for a domain in a criminal IOC corpus, on Safe Browsing, or registered days ago.

    v = check(message.text)   # returns a verdict and a ready-to-send reply

No signup, no key and no card for the first calls. It never throws, and it never tells your users something is safe, only that nothing is known against it.

https://github.com/nzdsf2-gif/relayshield/tree/main/widget

Andrew
RelayShield
```

---

## Tracking

Fill this in as you send. The number that decides whether this channel is worth continuing is
**replies per 100 contacted, by channel**, not the number sent.

| # | Repo | Channel | Sent | Reply | Integrated |
|---|---|---|---|---|---|
| 1 | M41NUL/all-media-downloader | email | | | |
| 2 | Matt0550/TagEveryoneTelegramBot | email | | | |
| 3 | cubepy/cubepay-doc | email | | | |
| 4 | mozharov/zapgram | email | | | |
| 5 | anishalx/SpyStroke | email | | | |
| 6 | TegroTON/ai-telegram-pay-miniapp | website | | | |
| 7 | bbbuilt/fragment-stars-api | website | | | |
| 8 | opencrew-ai/oncellclaw | website | | | |
| 9 | CarakaDev/caraka | website | | | |
| 10 | masudur-rahman/khorcha-pati | website | | | |
| 11 | antlis/tg-media-bot | website | | | |
| 12 | Exdenta/OinkAIJobSearch | website | | | |

## Two prospects deliberately left off

**arunrajiah/odoopilot** scored highest at 75, and its only contact is an **Odoo marketplace listing
page**, not the author's site. Use it only if that page carries a support address.

**The Claude bridge bots** (`xhyumiracle/tg-claude-bot`, `Mark-Life/telegram-claude-codex`,
`jedarden/telegram-claude-bridge`, `maleon17/claude-telegram-bridge`, `qwwiwi/dashi-plugin-claude-code`)
are the most interesting cluster in the sweep and every one of them is reachable only through
GitHub. They are agent products, so the pitch is MCP registry risk and prompt-injection exposure
rather than the widget. **That is a different message and a different week.** Worth doing properly
once the widget outreach has told us whether any of this converts.
