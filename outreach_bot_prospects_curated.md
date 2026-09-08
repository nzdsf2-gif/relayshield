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

---

# BATCH 2, added 2026-09-08. EMAIL-FIRST, because batch 1 measured 50%.

**The founder's measurement, and it changes the pipeline rather than extending it:**
*"Less than 50% of the initial candidates resulted in actual outreach messages (I sent roughly 10
emails). In general, without actual email contacts, links to websites rarely produced actual
contacts to message."*

**So a website is no longer treated as contactability.** The old scoring gave 20 of 100 points for
"has a website or an email", which counted a contact form nobody fills as equal to an address you
can write to. Half the list was therefore unreachable through the only channel that actually got
used. Batch 2 is selected on FIT, and then `tools/resolve_prospect_emails.py` decides who is
mailable. A row with no resolved address is not a prospect for this channel.

**HOW THESE 24 WERE FOUND, and what is verified.** GitHub repository search, 2026-09-08,
`topic:telegram-bot` crossed with payments, wallets, crypto and trading, `stars:8..300`,
`pushed:>2026-05-01`, excluding awesome-lists. **Everything in the table below is from the search
response: name, stars, description, topics, last push. NONE of the emails are resolved yet** --
api.github.com is scoped away from the build container, so that step runs on the Mac. Do not treat
the fit ranking as a contact list.

**Four were deliberately excluded** and it is worth saying why, because they surface high in this
search and will keep doing so:

- `ReNothingg/telegram-check-catcher` -- automates collecting other people's crypto cheques.
- `ReNothingg/P2C-Crypto-Sniper-Bot` -- sells order-interception software.
- `DiegoBermud65/mirroredge-polymarket-...` -- description is one sentence repeated ten times, which
  is SEO padding, and 88 forks against 24 stars is not an audience.
- `exgun007/gramnetwork-bot`, `rygroup-dev/zolana-sentinel` -- farming and claim automation. No
  counterparty question for a user, so nothing of ours belongs in them.

Selling a counterparty-screening product to a tool whose purpose is intercepting someone else's
order is not a near-miss, it is the wrong customer, and one reply saying so publicly would cost more
than the sale.

## Tier A -- holds or moves other people's money. Mail these first.

| # | Repo | Stars | Why it fits | The line to lead with |
|---|---|---|---|---|
| 13 | `glazybyte/Crypto-Escrow-Telegram-Bot` | 15 | An escrow bot **holds crypto in its own wallet** and releases on both parties' approval. The counterparty question is the entire product. | Escrow decides WHEN to release. It does not decide whether the address it releases to has been seen in criminal channels. |
| 14 | `Libermall/Telegram-Cryptocurrency-Wallet-Libermall` | 14 | TON wallet, cheques, fiat invoices, staking and a DEX gateway. Says outright it is security-maintenance only, so the fit is the LIVE products it points at. | Five money paths in one bot and no screen on the address at the far end of any of them. |
| 15 | `TegroTON/Telegram-Cryptocurrency-Wallet-TON-Kotlin` | 29 | Non-custodial TON wallet, sends to friends via virtual cheques, accepts payments in-bot. Same org as batch 1's `ai-telegram-pay-miniapp`. | Follow-up on the same org rather than a cold approach. |
| 16 | `bruhxax/Link-Bot` | 23 | Sells and manages VPN subscriptions, payments plus a Mini App. Handles recurring money from strangers. | A subscription bot takes a payment method from someone it has never met. |
| 17 | `JumpCodeFrog/telegram-shop-bot` | 10 | Catalogue, Stars and USDT payments, subscriptions, Mini App, admin panel. | A shop bot's risk is the buyer's address, not its own code. |
| 18 | `king-tri-ton/TelegramStarsBot` | 17 | A reference implementation for taking Telegram Stars, so it is copied. Reach the pattern, not one bot. | The example everyone forks is the best place for a check to live. |
| 19 | `slightbasebo/fragment-api-dev` | 134 | Stars and Premium API with GRAM/USDT payments, **no API key**, Python SDK. Highest-star payments target here. | Keyless is our shape too: `/v1/wallet-risk` needs no key either. |
| 20 | `exmanka/ksiVPN-telegram-bot` | 46 | P2P payments plus YooKassa, promocodes, referrals. P2P is where the counterparty is a stranger by construction. | P2P means the other side is unvetted by definition. |
| 21 | `Tonwed/gpt-upi` | 54 | UPI scanner and order hub with Telegram login, wallets and worker dashboard. Payments outside crypto. | The only non-crypto payments target on this list, which is worth learning from. |

## Tier B -- agent-shaped, where the buyer is the agent

| # | Repo | Stars | Why it fits |
|---|---|---|---|
| 22 | `x402agent/SolanaOS` | 9 | The org name is `x402agent`. We run 28 live x402 endpoints. Whatever else is true, they already speak the protocol we settle in. |
| 23 | `gokhantos/opencrow` | 23 | Multi-agent platform across Telegram and WhatsApp, 90+ tools, **MCP in its topics**, crypto and DeFi. An agent mounting 90 tools is the agent-bait audience exactly. |
| 24 | `fciaf420/moonbags` | 40 | Solana auto-trading with an LLM exit advisor and Jupiter swaps. An LLM deciding a swap is an agent paying a counterparty. |
| 25 | `uerax/all-in-one-bot` | 181 | Smart-money tracking and on-chain address analysis, 181 stars. They already do address analysis, so this is an integration conversation rather than a pitch. |
| 26 | `vooi-app/vooi-signals-bot-example` | 18 | Telegram signals into an LLM parser into a trading API. An org account, so a support address is likely. |
| 27 | `punkpeye/awesome-remote-mcp-servers` | 47 | **Not outreach, a LISTING.** A curated index of remote MCP servers, which is FD-15's artefact. Submit rather than mail. |

## Tier C -- trading bots. Weaker fit, mail only if Tiers A and B run dry.

`skharchikov/polymarket-bot` (32) · `IvanWng97/TradingAgents-Telegram` (45) ·
`ozgen/binance-telegram-bot` (26) · `sbauwow/schwagent` (21) ·
`NadirAliOfficial/trading-scanner` (13) · `Formyselfonly/invest-alert-bot` (40) ·
`lukmanc405/neko-futures-trader` (8) · `zargarkhan1/quorum-alpha-dash` (119)

**Why they are Tier C and not simply rejected.** A trading bot's user is not paying an unknown
counterparty; they are trading on an exchange they chose. The wallet check has no natural moment.
What these do have is an LLM making a decision with money attached, which is the agent-bait audience
one step removed. `quorum-alpha-dash` at 119 stars is the only one worth an early look, and its
value is the audience rather than the fit.

## THE STEP THAT DECIDES WHO IS ACTUALLY MAILABLE

**ANDREW RUNS THIS.** It resolves a real address per candidate, or drops the row:

    export GITHUB_TOKEN=$(gh auth token)
    python3 tools/resolve_prospect_emails.py --in prospects_batch2.txt --out prospects_batch2.jsonl

It tries the owner's public profile email, then the owner's own recent commit author address, and
**rejects `users.noreply.github.com`** because that address is not deliverable and counting it is
how a list looks reachable and is not. `tools/contact_hygiene.py` screens the result, so
`root@203.0.113.4` and `trial@telegram.bot` cannot come back a second time.

**Then mail only the resolved rows, and record the conversion.** The number worth tracking is not
replies. It is **candidates that became a sent message**, which was under 50% for batch 1 and is the
number this batch is built to move.
