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

## 2. What actually drives Mini App discovery, corrected

**The first version of this section was wrong, and the founder corrected it the same day.** It
ranked the menu button on `@relayshield_bot` above everything else. That is right for a bot with an
audience and wrong for ours: the bot has a tiny number of users, so a Mini App hung off it inherits
a tiny number of users. Ranking a surface by how well it works in general, rather than by how well
it works for us, is how a plan ends up describing somebody else's company.

Re-ranked for the audience we actually have.

1. **The Telegram blog channel, linked from every post.** Agreed the same day. It is ours, it
   already publishes, and it costs one line per post. Small, but it is the only surface on this list
   where the audience already chose to hear from us.
2. **Channels that announce new Mini Apps.** The founder has seen them; the question was which ones.
   `tools/find_miniapp_channels.py` searches for them on the prospecting account and reports each
   one's member count, description and how it was found, because a list of channel names written
   from memory is unverifiable and this repo has been bitten three times by exactly that. These are
   SUBMISSION targets: one polite submission each, through whatever route the channel publishes.
   Not a DM campaign, and not posting into them.
3. **Mini App directories and catalogues**, tApps Center and the others in the same family. Worth
   one afternoon of submissions. They convert like directories convert, which is to say modestly and
   forever.
4. **Deep links with attribution, everywhere we already appear.** `t.me/<bot>/app?startapp=<source>`
   carries the parameter into the Mini App, so blog posts, the developers page, the widget's README
   and any directory listing each get their own key. Register those keys in `_SOURCE_BANNERS` BEFORE
   the links go out. The official MCP registry cost four months of unattributed arrivals by getting
   that order wrong.
5. **The menu button on `@relayshield_bot`.** Still worth doing, because it costs almost nothing and
   converts the users we do have at a high rate. It is simply not a growth channel at our size, and
   calling it one was the error.
6. **TON app catalogues**, only if the TON wallet and token scans ship in v1, since that is the only
   part of the product that is TON-native.

Two things worth saying plainly about all of it. Every route here is small, and the honest framing
is that Mini App discovery is a portfolio of small routes rather than one lever. And a Mini App with
one job done well is the only version that gets recommended onward, which is the one channel that
compounds.

## 3. Is a browser extension worth building as a discovery surface?

**No, and one leg of the first version of this argument was wrong.**

I wrote that "we already have the plugin-shaped surface that matters" in the MetaMask Snap. **We do
not.** The founder submitted an integration request and has had no response, and the repo already
said so in three places: `victim_side_outreach_messages.md` records that Segment 2 is not the warm
thread because the Snap is not approved, and `xcitium_outreach.md` and `NEXT_SESSION_2026-08-19.md`
gate on the same fact. A `metamask-snap` key exists in `_SOURCE_BANNERS`, registered before shipping
exactly as the rule requires, and a registered key is not a live integration.

**A doc claiming something is done is a lead, not a fact.** That is CLAUDE.md's own rule, and the
first draft of this file broke it.

The conclusion survives without that leg, on the reasons that do not depend on the Snap:

- A security extension asks permission to read every page the user visits. That is the hardest
  permission to justify in a store review, and it does not get easier because our intentions are
  good.
- Two stores, permanent manifest churn, and a review queue we do not control, for an audience that
  overlaps almost entirely with people who could use the bot or the Mini App.
- Nothing about an extension is Telegram-native, and the Mini App's whole argument is that it is.

The Snap remains the better version of this idea precisely because it fires at signing time, which
is a moment of real intent. It is also sitting in someone else's queue with no reply, which is worth
remembering before building a second thing that will also sit in a queue.

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

## 5. What else to ask Jake, now that access is back in review

Clicking through to Accept machine payments returned the same access request Jake shared, so the
programme is gated on their review rather than on a product choice, and the extra detail they asked
for has already been sent. Four questions worth putting to him while it sits, chosen because each
one changes what we do next rather than being nice to know.

1. **Does x402 settlement count toward early-adopter status, and if not, what does?** Carried since
   the first conversation and still unanswered. We have 28 endpoints settling in USDC on Base today.
   If that counts, we are already qualified and the review is a formality. If it does not, the
   qualifying activity is card or SPT volume, and we should know that before building toward it.
2. **What is the actual gate on this review, and what is the queue?** Not a nudge: a named criterion
   and a rough timeline. "In review" with no criterion is indistinguishable from declined, and three
   other distribution routes are competing for the same week of work.
3. **Can machine payments settle against an account that already runs metered subscriptions and an
   AWS Marketplace fulfilment path?** We already sell the same bundles through two doors, and the
   disintermediation rules we follow are strict. If accepting machine payments creates a third
   billing surface over the same customers, we need the shape before turning it on, not after.
4. **Is there a design-partner or early-access track for the SELL side specifically?** Every public
   example of agentic commerce so far is a buyer paying a merchant for goods. We are an API that
   agents pay in order to check a counterparty, which is a different shape, and vendors usually want
   exactly that kind of example. Offer the Rain demo as the artefact: an agent discovers two MCP
   servers, pays to check each before connecting, and refuses one on an edit-distance-1 typosquat
   finding, with the payments verifiable on Basescan.

The framing that has worked in every one of these conversations, and that is worth repeating: their
agent wallet answers "is this agent allowed to spend this much". Nothing in the stack answers "is
the thing it is about to pay legitimate". An agent with a valid card, inside its limits, paying a
fraudulent API is a fully authorised transaction.
