# Low-friction Telegram wallet integrations: assessment

**Written 2026-08-10.** Answers the question "are there low-friction Telegram wallets we can
integrate with that contribute to the flywheel?"

**Short answer:** not in the sense of "integrate with a wallet." Same finding as Coinbase, Bitget
and Kraken on 2026-08-09: no Telegram wallet runs third-party code, so there is nothing to build
against. But unlike those three, Telegram has a **permissionless surface that needs no partner at
all**, and we already own the harder half of it.

---

## The constraint that governs everything below

Telegram made TON Connect the **exclusive** wallet connection protocol for Mini Apps, with a
migration deadline of 21 February 2025, and the policy as reported goes further than protocol: Mini
Apps are restricted to TON, and "tokens and NFTs on other blockchains like Ethereum and BNB are not
permitted."

**This is reported, not primary-source verified.** It comes from Cointelegraph's coverage of the
terms change. Before committing engineering time, read Telegram's current Mini App terms directly.
The distinction that matters for us is whether the restriction covers *presenting* other chains'
assets or only *transacting* in them, because Crypto Shield never transacts anything.

What the constraint does not touch: **Telegram bots.** A bot has no TON Connect requirement and no
chain restriction. That is worth holding onto, because we already run one.

---

## The landscape, ranked by friction

### Tier 1: no partner required, buildable now

**1. The RelayShield Telegram bot we already operate.**
`relayshield_telegram_webhook.py`, 6,423 lines, live, with users, wallet handling and a payment
path already in it. This is the lowest-friction wallet-adjacent surface in the whole company and it
needs zero permission from anyone.

What it does not have is a **reason for a user to forward it**. That is the actual gap, and it is
the same gap the developer funnel solved with `rsscan --report`: the free thing has to produce
something a user wants to hand to someone else.

**2. TON Connect, in a Mini App.**
Permissionless. TON Connect supports 30-plus wallets, and every Telegram-relevant one speaks it:
Telegram's own Wallet, Tonkeeper, MyTonWallet, Tonhub. A Mini App can request a connection that
discloses the wallet address with **no transaction and no smart contract**, which is exactly and
only what a read-only security product needs.

We can already screen TON. `relayshield_api.py` handles TON addresses through TON Center and TONAPI
including the community scam flag, plus DexScreener for TON tokens. The backend work is done. A
Mini App is a front end over an endpoint that already exists.

### Tier 2: listing, not integration

**3. TON dApp catalogues and Mini App directories.** Cheap, and the same class of work as the
Snaps Directory submission. Only worth doing after a Mini App exists.

### Tier 3: partnership, high friction, park it

**4. Wallet in Telegram (`@wallet`).** Telegram's native wallet, TON, USDT and BTC, custodial-ish,
operated with the TON Foundation. It has **no third-party extension model**. There is no plugin, no
risk-provider hook, nothing to integrate into. The only route is being the intelligence behind its
own built-in warnings, which is the Blockaid pattern: a high-friction partnership sale, not a
self-serve integration.

**5. Tonkeeper.** Open source, which reads like an opportunity and is not one. Open source means we
could read the code, not that they run ours. No plugin surface.

**Tiers 4 and 5 are the identical finding to the 2026-08-09 wallet decision.** Named as targets,
not as work.

---

## Does a Mini App actually feed the flywheel?

This is the part worth being sceptical about, because "build a Telegram Mini App" is the kind of
idea that sounds like distribution and is often just more surface area. Nine ways to pay and zero
paying customers is the standing warning.

**The argument for it is specific, and it is about the forwarding mechanic.**

Telegram Mini Apps have a native share into a chat. That is not a "share" button bolted onto a
website, it is the platform's own primitive, and the audience is already sitting in group chats
about exactly this subject. A scan result card forwarded into a trading group is the same shape as
`rsscan --report`: a free artefact, safe to share, that carries the product with it.

**And the timing lines up with the blog post.** The BlueNoroff campaign propagates through Telegram
contact lists. A defence that propagates through Telegram contact lists is not a marketing
coincidence, it is the same graph. That is a real launch narrative rather than a manufactured one.

**The argument against, stated honestly:**

- **TON-only is a real product mismatch.** Crypto Shield's differentiator is multi-chain plus the
  credential layer. A TON-restricted Mini App shows the least differentiated slice of it.
- **The chain restriction may bite.** A scan field that accepts an Ethereum address is arguably
  "operating on another blockchain." I think it is defensible, since we never present a token, hold
  a balance or move a value, but it is a rejection risk and it should be raised with Telegram before
  building, not after.
- **It is another channel.** The 2026-08-09 decision was explicitly "low-friction self-serve is
  preferred, high-potential channels one at a time." There is already a MetaMask Snap in review, an
  XSOAR demo due 21 August and Bundle A not yet public.

## Recommendation

**Do not build a Mini App yet. Do the bot-side half first, this week, because it is hours not
weeks and it tests the same hypothesis for almost nothing.**

Concretely: give the existing bot a **forwardable scan result**. One command, one clean card,
result safe to forward, with a link carrying `?source=telegram-bot-share`. If forwards happen, the
flywheel premise is confirmed and the Mini App becomes a funded decision rather than a hopeful one.
If they do not, we have learned that for the cost of an afternoon instead of a sprint.

Two things to settle before any Mini App work starts:

1. **Read Telegram's current Mini App terms directly.** The TON-only restriction is the whole
   feasibility question and it is currently second-hand.
2. **Decide what the Mini App is for.** If the answer is "TON wallet screening," it is a weak
   product. If the answer is "the shareable front door to Crypto Shield, which happens to connect a
   TON wallet," it is a distribution asset. Only the second one is worth building.

---

## Sources

- [Telegram mandates TON Connect for all crypto wallets](https://cointelegraph.com/news/telegram-ton-wallet-mandate-crypto-mini-apps)
- [TON Connect overview, TON Docs](https://docs.ton.org/applications/ton-connect/overview)
- [TON Connect and how to connect apps, Wallet help](https://help.wallet.tg/article/281-ton-connect-and-how-to-connect-apps)
- [TON Wallet integration in Telegram Mini Apps](https://www.nadcab.com/blog/ton-wallet-integration-telegram-mini-apps)
- [TON embedded wallets via Dynamic and Fireblocks](https://www.mexc.co/news/994630)
