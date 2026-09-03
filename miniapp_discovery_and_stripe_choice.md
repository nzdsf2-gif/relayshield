# Mini App discovery, and which Stripe agentic product to select

*2026-09-03. Answers two questions asked the same day, both of which turn on the same
distinction: who is the customer of a given surface.*

---

## 1. Should the widget carry a Mini App registration link?

**No, and there is nothing to link to yet.** The Mini App is scoped in
`telegram_miniapp_and_app_inventory_scope.md` Part 3 and has not been built.

But the answer would be no even once it exists, and the reason is worth writing down before
someone adds it as an obvious win.

**The widget runs inside somebody else's product, in front of users who never chose us.** Its
audience splits in two, and the split decides everything:

| Who | Where they are | What they should see |
|---|---|---|
| The maintainer, who is our customer | reading the README, wiring up the call | `api.relayshield.net/developers?source=tg-widget` |
| Their users, who are NOT our customers | reading a verdict inside a bot they already use | "Checked with RelayShield", and nothing more |

A link in the verdict inviting their users to our bot or Mini App is an advert for a competing
Telegram product injected into their conversation. It is the single fastest way to have the widget
removed, and it would be removed by exactly the maintainers who integrated it, which is the
expensive kind of churn. The footer already carries the brand, which is the right level of presence:
enough that a curious user searches the name, not so much that it reads as a poach.

So the widget stays a developer surface. Mini App discovery is a separate problem with its own
routes.

## 2. What actually drives Mini App discovery

In rough order of cost to value, and the first one is worth more than the rest combined.

1. **The menu button on `@relayshield_bot`.** This is in the scope doc as a requirement and it
   remains the strongest lever: the bot has users today, and a Mini App attached to a bot people
   already talk to needs no new audience. Everything else on this list is an attempt to buy what
   this gives away.
2. **Deep links with attribution.** `t.me/relayshield_bot/app?startapp=<source>` carries a
   parameter into the Mini App, so every placement is measurable. Register those `source=` keys in
   `_SOURCE_BANNERS` BEFORE the links go out. The MCP registry cost four months of unattributed
   arrivals by getting that order wrong.
3. **Telegram's own catalogues and the third-party Mini App directories** (tApps Center and
   similar). Worth a submission each, and worth exactly one afternoon: they are directories, and a
   directory listing converts like a directory listing. Check each one's terms before scraping
   anything from it, per the source-ranking table in the scope doc.
4. **The blog and the Telegram channel**, which we already publish to, plus the developers page.
   These cost nothing because the channels exist.
5. **TON app catalogues**, only if the TON wallet and token scans ship in v1, since that is the
   only part of the product that is TON-native.

What none of these change: a Mini App with one job done well is discoverable because people
recommend it. A Mini App that is a consumer product, a developer portal and a partner centre at
once is bad at all three and gets recommended by nobody. That constraint is in the scope doc and it
survives this question.

## 3. Is a browser extension worth building as a discovery surface?

**Not now, and probably not at all as a discovery play.**

- We already have the plugin-shaped surface that matters: the **MetaMask Snap**, which screens the
  counterparty at signing time. That is a moment of real intent. A general link-checking extension
  is the same capability at a moment of much lower intent.
- A security extension asks for permission to read every page the user visits. That is the single
  hardest permission to justify in a store review, and the justification does not get easier
  because our intentions are good.
- Extensions carry a permanent update treadmill across two stores and Manifest churn, for an
  audience that overlaps almost entirely with people who could use the bot.
- A Telegram Web specific extension is a real niche, but it is a niche of a niche: Telegram Web
  users, who are a minority of Telegram users, and the bot already covers them.

The same effort spent on the widget or the Snap converts better, and both are already built.

## 4. Which Stripe agentic commerce product to select

The console offers four. Only one describes what RelayShield does.

| Card | What it is | For us |
|---|---|---|
| **Accept machine payments** | Agents pay you programmatically, stablecoins or cards, settling into your Stripe balance | **YES. This is the one.** |
| Agentic commerce for retail | Sell products through AI shopping channels, or become an AI shopping interface | No. We sell API calls, not a product catalogue |
| Link agent wallet | Let agents spend on your behalf, with spend controls | Not yet. Buy side, not sell side |
| Stripe Projects | CLI for hosting, databases, auth, AI, analytics | No. Infrastructure we already have |

**Why Accept machine payments is the right selection.** It is the productised version of what we
already run by hand: 28 live x402 endpoints priced $0.05 to $0.35, settling in USDC on Base through
a facilitator, with no human in the loop at any point. An agent discovers an endpoint, takes the
402, pays it, and gets its answer. That is a machine payment by any definition, and it is our
entire pay-as-you-go rail.

**It is also the shortest path to the open question with Jake Lamoine**, which is whether x402
settlement counts toward early-adopter status for the Merchant Partner Programme. Selecting this
product makes that question concrete rather than hypothetical, and the price comparison is already
recorded: card via SPT has a $0.50 minimum, stablecoin $0.01 USDC, and the sample uses
`scheme: "exact"` on Base, which is identical to what our endpoints already do.

**Why not agentic commerce for retail, even though it looks interesting.** It is built around a
product catalogue being surfaced inside an AI shopping experience. We have no SKUs. The nearest
thing we have is a catalogue of endpoints, and that is discovered through the x402 Bazaar, the MCP
registry and the OpenAPI spec, which are already live and cost nothing more.

**Why not the agent wallet yet, and when it changes.** The agent wallet is spend control on the BUY
side: is this agent allowed to spend, and how much. We are on the sell side. It becomes relevant
the day our own agents spend money autonomously, which today is one demo wallet on Base rather than
a business process.

Worth carrying into any conversation with Stripe, because it is the pitch rather than a complaint:
the agent wallet answers "is this agent allowed to spend this much". Nothing in it answers "is the
thing it is about to pay legitimate". An agent with a valid card, inside its limits, paying a
fraudulent API is a fully authorised transaction. That gap is the same one Rain has, and it is
what we sell.

**One caution before clicking.** Selecting a product in that console changes what Stripe shows and
may start an onboarding flow, but it is not a commitment and it is not exclusive. Dual-channel
selling is permitted and we already do it: AWS Marketplace and direct Stripe both sell Bundle A and
Bundle D. The rule that matters there is the one already written into
`relayshield_developer_signup.py`: never migrate a customer who arrived through AWS onto a Stripe
key, and never steer a Marketplace-originated lead to the Stripe door.
