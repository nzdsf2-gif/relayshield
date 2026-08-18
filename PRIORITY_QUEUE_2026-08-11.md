# Priority queue, ordered 2026-08-11

Written to answer one question: where does the Telegram Mini App belong? The ranking below is the
context that answer depends on, so it is recorded rather than asserted.

**The ordering principle is the founder's own, recorded earlier: channel sales is the constraint,
not more listings or more endpoints.** Anything that does not touch a real buyer conversation sorts
below anything that does, regardless of how interesting it is to build.

---

## 1. XSOAR demo (#8) — HARD EXTERNAL COMMITMENT, promised 21 August

The only item with a date owed to someone else. Ten days out.

**Check the blocking unknown first**, before any build: whether the free Community Edition still
allows installing a custom pack from a contribution branch. If it does not, the approach needs
rethinking and there is still time to do that. If that check slips past next week, there is not.

## 2. Bundle A listing-URL pass — UNBLOCKED, the URL is in hand

**https://aws.amazon.com/marketplace/pp/prodview-zgdxyqfd63hog**

Founder pulled it from the seller portal 2026-08-11. **Verified by content, not status code**:
"RelayShield" x10 and "Core Identity Exposure" x6 in the rendered page, so this is the real listing
and not AWS's 200-serving "Page not found".

**Storefront search indexing is a separate system and does not gate this.** The page is live now,
so update `/developers`, the blog, the API reference, the MSP brief and the XSOAR demo notes
**together**, not piecemeal.

Escalate only if the listing is still unsearchable after 2026-08-12 19:11Z, which is 48 hours from
the change set succeeding.

**Lead with procurement, not the badge:** buying through Marketplace draws down existing AWS
committed spend, which turns a new-vendor purchase into a line item they have already committed to.
That sentence belongs in every partner conversation, which is why this sits at 2 rather than 6.

## 3. Bundle D Stripe Door 2 — **MY TASK, NOT THE FOUNDER'S.** Corrected 2026-08-11.

I twice called this a founder action. It is not. The founder started creating the price in a prior
session, I determined it needed a monthly subscription **plus** variable per-call rates for the
components, and I agreed to complete it. Reading the code confirms his description exactly.

**The shape, from the code rather than from memory:**

1. **A licensed recurring Price at $299/mo** on a new Product. Its id is what goes into
   `BUNDLE_D_DIRECT_PRICE_IDS`, which `relayshield_developer_signup.py:113` reads to decide that a
   Stripe-sourced key gets `bundle_d_access=True`.
2. **The per-call rates need NO new Stripe prices.** They ride the existing aggregate meter,
   `relayshield_api_usage` / `price_1U0jLZL2dcjOeFiYG8VktTxK` at $0.01 per unit, because
   `_record_stripe_meter_event` looks the price up from the request path. See
   [[project-stripe-aggregate-usage-meter]]: **never add a per-endpoint price again**, that is what
   killed developer signup for six weeks.
3. **The Bundle D checkout session must carry BOTH line items**, the $299 licensed price and the
   aggregate metered price. Subscription only would give unlimited calls for $299 and undercut the
   AWS door, which the code comments explicitly call out as lost revenue and bad optics.
4. Then set `BUNDLE_D_DIRECT_PRICE_IDS` on `relayshield-api` **and** `relayshield-agentic-api`,
   both currently unset (verified 2026-08-11).

Verified live 2026-08-11: **zero** prices at $299.00 exist anywhere in the Stripe account.

## 4. ClickFix hosting-platform false positives — live correctness defect

Three of the 13 unique ClickFix domains are hosting platforms, not threats: `sites.google.com`,
`raw.githubusercontent.com`, `buyaneli876-oss.github.io`. A customer sweep matching those produces a
false positive with real operational cost, on a product whose whole pitch is the opposite.

Above the growth work because it damages credibility in exactly the sales conversations item 2 is
meant to open.

## 5. AWS architecture details (#11)

Unblocked, answers already decided, upload `relayshield_bundle_a_architecture.png`. Not a gate for
public visibility, only the "Deployed on AWS" search designation. Cheap, so it clears fast.

## 6. Discord bot — APPROVED 2026-08-11, acquisition

Slash-command only, `/scan` and `/scam`, ephemeral by default, **deliberately not** requesting
Message Content Intent. The "post to channel" button is the growth mechanic, not a nicety, because
an ephemeral reply is seen by one person while a Telegram inline result is seen by the whole chat.

Founder overrode a recommendation to wait for inline data, correctly: four of five Telegram bot
directories are dead or paid, so a flat inline number over the next fortnight would measure the
directories rather than the channel.

## 7. Angle 2, maintainer watch (#17) — BUILD

Spec in `angle2_maintainer_watch_scope.md`. Reports at dependency level, never naming a maintainer.
Feasibility gate already passed.

## 7b. Add Angle 2 to Bundle D — SEPARATE TASK, do not let it ride on 7

Founder flagged 2026-08-11 that this was missing, correctly. "Folds into Bundle D" is a design
decision, not a delivery step. Building the capability and **selling** it are different work, and
the second half is the half that touches revenue:

- add the dimension to the Bundle D entity, remembering **pricing only updates bundled with
  `UpdateVisibility`**
- listing copy, so a buyer can tell what they are getting
- API reference and `/openapi.json`
- the Bundle D Stripe side, so Door 2 covers it as well as AWS

## 8. Video set (#15) — two videos, real screen recordings, one-time

Dropped from the first pass of this queue in error. Founder's calls, both taken:

1. **Discord bot demo, not Telegram inline.** The original idea was inline replying in a group chat,
   but effort is going to Discord and inline has zero queries, so the demo should show the thing we
   are actually building. Blocked until item 6 exists.
2. **Address poisoning demo for Crypto Shield Mobile.** Not blocked, can be recorded now.

**Host on YouTube, then re-upload natively per channel.** YouTube is the durable, embeddable,
searchable home, and it is the only option that also drops into an **AWS Marketplace listing video
field**, which makes it work for sales rather than only for social. Then upload the file natively to
LinkedIn, Telegram and Farcaster rather than posting a YouTube link, because every one of those
suppresses off-platform links and native video outperforms them. X is suspended, so it is not part
of the plan.

## 9. TELEGRAM MINI APP — added 2026-08-11. GATED ON A NUMBER, NOT A DATE.

**After Discord. Not because it is less valuable, because it is the wrong half of the funnel to
build next.**

Discord brings people in. The Mini App converts people who are already there. Right now there is
almost nobody there to convert:

| Measure | Value |
|---|---|
| Webhook invocations, last 30 days | **22** |
| Webhook invocations, last 4 days | 5 |
| Inline queries since launch | **0** |

A sprint of work to deepen engagement for an audience of roughly five people is the wrong trade,
and no amount of Mini App quality changes that denominator.

**The case FOR it is real and unchanged**, which is why it is on the list at all rather than parked.
Inline is public by construction: our handler answers with `is_personal: false` and a shared cache,
so every result is visible to the whole chat. That permanently rules out three things:

| Inline can never | Mini App can |
|---|---|
| show credential or breach exposure (PII in a public chat) | private, authenticated surface |
| show history or a watchlist (no per-user state) | persistent per user |
| accept an email or phone | yes, with consent |

**So the credential layer, which is the differentiator and the paid tier, is unreachable from inline
forever.** The Mini App is the only route to charging money inside Telegram.

Two supporting facts: the handoff is already scaffolded, since the inline handler attaches a
"Check your own exposure" button with a `start_parameter` that currently opens a DM and would point
at the Mini App instead. And Mini Apps have their own discovery surface, Telegram's Apps tab plus
global search, which is a different and non-decayed channel from the bot directories.

**The gate to open before building it:** sustained real usage from a source we do not control, from
Discord handoff or inline or both. A concrete threshold beats a vague one. Suggested: **50 distinct
users, or 100 inline queries in a fortnight.** If that number arrives quickly, this jumps the queue
and belongs above item 7. If it never arrives, we have learned the channel is wrong for the cost of
an afternoon, which was the entire point of shipping inline first.

## 6b. CPPO + the MSP target list — immediately after the Discord bot

Founder direction 2026-08-11: build Discord, then CPPO.

CPPO (Channel Partner Private Offers) lets a reseller sell the existing Bundle A and D listings.
No new build, no new surface, and the listings are live so the precondition is met. Deliverables:

- how CPPO actually works, what the seller has to enable, and what the partner needs
- **a target list of high-profile MSPs** that (a) will do business with a startup and (b) already
  transact through AWS Marketplace, which is the real filter since an MSP not already buying on
  Marketplace cannot resell there without onboarding first
- an outreach message for that list

AWS ISV Accelerate: founder raised it with an AWS Partnership Sales contact on 2026-08-11, and
followed up with one new AWS sales lead the same day. Waiting on them, not a task.

## 9b. Buyer review directories: G2, Capterra, TrustRadius, Gartner Peer Insights

**Founder confirmed 2026-08-11 he has no profiles on any of them.** Free vendor profiles, and unlike
the ~20 developer surfaces already live, this is where a security buyer and their procurement team
actually search. Claim the profiles even before there are reviews, because the profile is the SEO
real estate and an unclaimed one can be created by anyone.

Realistic caveat: a profile with zero reviews ranks poorly. Arjen is a real user on regular calls
and is the obvious first review ask.

## 9c. MCP registry entry drift — minutes

The live registry description differs from the local `server.json`, so the published entry looks
stale. Local says "MCP registry risk, prompt-injection detection"; the registry copy does not.
Re-publish so the listed capabilities match what the server actually does.

## 9d. Zapier: 38 held tasks, and templates later — DEFERRED, founder said it can wait

**Do not solve this by upgrading the plan. The founder does not want to pay for a licence.**

38 tasks are held because the account hit the free plan's 100-task monthly limit. The card is
already updated; the only thing Zapier is asking for is the upgrade. So the real work is **cutting
task consumption**, not releasing the backlog:

- find which Zaps are burning the 100, since one chatty trigger usually accounts for most of it
- add filters so a Zap runs on the events that matter rather than every event
- confirm what actually happens to held tasks at the next cycle reset before promising they are
  recoverable, because on the free plan they may simply expire

**Separately, and unrelated: add templates to Zapier.** Our integration is approved, and published
templates are the discovery surface for it, the same way the three n8n templates are. Founder wants
this "when things calm down", so it sits below the revenue work rather than beside it.

## 10. Datadog scoping — gated on the XSOAR demo shipping

See `datadog_scoping_todo.md`. One question only: directory submission (worth an hour) or maintained
integration (a quarter, and therefore no).

## 11. Syndication (#14) and rsscan agent instruction scanning (#10)

Videos moved up to item 8; they no longer live here.

**HackerNoon is dead for us**, paywalled for company-owned domains, and the review step itself sits
behind the paywall so there is no free path at all. Remaining free canonical-accepting options are
dev.to and Substack. **Check the money question on each before writing anything**, which is the
lesson from the HackerNoon effort.

---

## Blocked. Not queue items. Do not re-raise as work.

Founder correction 2026-08-11: these were listed as if actionable and they are not.

- **Twilio #28883049.** Nothing to do until Twilio replies. `/v1/metered/sim-swap` continues to 503
  on a live public paid bundle, and that is a consequence to state honestly to any buyer, not a task
  to schedule.
- **Stripe Door 2 for Bundle A (#16).** Nothing to do until the listing indexes. Mirror of Bundle D
  when it does.
- **tgdr.io** submitted and acknowledged. **MetaMask Snaps Directory** submitted 2026-08-09.

## Deliberately deferred

- **`assetlinks.json` legacy statement.** v1.4.0 is unpublished but existing installs persist, and
  deleting the statement breaks Connect Wallet for those users. Both statements stay live for now.
  An extra entry costs nothing. Revisit in a few weeks.
