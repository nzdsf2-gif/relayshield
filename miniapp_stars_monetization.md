# Telegram Stars in the Mini App: what they are for, and why not yet

Written 2026-09-10, answering: *"One thing you didn't build is the in-app Stars monetization where
user can optionally pay stars for more url lookups or Ton wallet/token checks. Its still not clear
how we can use the stars or what value they bring."*

**You are right that it was not built, and the reason it is not clear what value they bring is that
for the two things you named, they bring none.** Both are already free by deliberate design, and one
of them has almost no cost to us at all. But there is a third answer that is worth having in
writing, and it is the reason this document exists rather than a one-line no.

**Recommendation, up front: do not build it now. Gate it on the discovery routes producing measured
arrivals. And if it is ever built, Stars pay vendor bills -- they never cap the free checks.**

---

## 1. Both paywall candidates you named are already free, and one is free because it costs nothing

Read from the code rather than recalled.

**More URL lookups.** `/v1/link-check` is in `KEYLESS_SCAN_ENDPOINTS`, and the comment sitting on
that entry answers the question directly:

> Unlike the wallet endpoints above, this one has **no paid upstream at all**: DynamoDB, Safe
> Browsing's free tier and RDAP. The per-IP cap is here to stop it becoming an open proxy, **not to
> protect a vendor bill.**

So a Stars paywall on URL lookups would be charging for something that costs us essentially nothing,
and the cap it would sit behind was never a cost control in the first place. **It would also work
against us three ways at once:** more checks mean more corpus signal, more `?startapp=` arrivals on
the developers page, and more of the one behaviour the Mini App exists to produce. Capping it prices
the thing we are trying to cause.

And it contradicts the app's stated premise, in the Worker's own header: *"a stranger opening a
Telegram link gets an answer with no signup, no key and no wallet connect."*

**TON wallet checks.** `/v1/ton-address` is **already a keyless endpoint** and has been since Crypto
Shield Mobile. Putting Stars in front of it would not be adding a paid feature, it would be **taking
away a free one**.

**TON token checks are the one real gap.** There is no jetton or TON token endpoint anywhere in
`relayshield_api.py` -- only `/v1/ton-address`. So that is a BUILD, not a paywall, and item 1's route
(6) already says TON catalogues are worth submitting to only if TON wallet and token scans ship.

---

## 2. What Stars are actually for, and it is not revenue

**The revenue case is weak and should not be the reason.** Consumer micropayments, at Star prices,
minus Telegram's cut, against a user base that has not been measured, is pennies. RelayShield's
revenue is six subscription plans, x402 per-call, and AWS Marketplace -- and the PayPal decision
already settled the general shape: *a fourth rail that reaches no buyer the first three miss is not
worth its maintenance surface.*

**Stars differ from PayPal in one way that matters, though, and it is the honest case for them.**
PayPal's buyer was already served by card or wallet. Stars reach a buyer the other three rails
**structurally cannot**: an anonymous Telegram user with no account, no card and no wallet, who will
never sign up for anything. That is a genuinely unreachable segment today.

**So the real value is a signal, not a revenue line.** Every other thing the Mini App can measure --
opens, checks run, second-day returns -- measures interest. A payment measures value, and a Star
payment measures it with almost no friction distorting the result, because the user does not have to
produce a card. That is a better number than anything else this funnel can generate.

**But a willingness-to-pay signal from a funnel with no measured traffic is not a signal.** The Mini
App launched this week. The six discovery routes in item 1 have not run. `tools/source_arrivals.py`
has never been run against the `tg-miniapp` keys. Building a paywall now is optimising a funnel whose
size nobody has looked at, which is the same error as reasoning from rsscan's unmeasured reach.

---

## 3. The thing worth writing down today, even though we are building nothing

**If we ever charge a consumer for anything inside a Telegram Mini App, Stars is the only compliant
door.** Telegram requires digital goods and services sold inside Mini Apps to be paid for with
Stars, because that is how Telegram satisfies Apple's and Google's in-app-purchase rules. Sending a
user from inside the Mini App to a Stripe checkout, an x402 flow, or any card or crypto page for a
digital good is the route that gets a bot restricted.

**UNVERIFIED:** taken from Telegram's Bot API payments rules as I understand them; `core.telegram.org`
is egress-blocked from the container so I could not read the current page. **The check is one
browser tab** -- <https://core.telegram.org/bots/payments-stars> -- and it should be read before any
line of payment code, not after.

**Why record it now, having decided to build nothing:** this is the kind of constraint that costs
nothing to know and a restricted bot to discover. We already have a Stripe rail, an x402 rail and a
developers page one link away from the Mini App. A future session wiring "upgrade" to any of those
from inside the app would look entirely reasonable and would be the wrong door.

---

## 4. The expensive prerequisite is already built, which changes the cost if we revisit

Worth knowing, because it moves this from "a large build" to "a medium one".

Charging a per-user quota needs a verified, stable, non-spoofable user identity. The Mini App
Worker's own header used to say it deliberately had none. **It has one now:**
`relayshield_watchlist.py` verifies Telegram's `initData` HMAC against the bot token and derives the
user id as `HMAC-SHA256(pepper, telegram_user_id)`, with the pepper in Secrets Manager. Its comments
record why: taking `telegram_user_id` from the request body would let anyone post any id.

So the hard half exists and is live. What would remain: a Stars invoice flow, a payment webhook, a
quota table keyed on that hashed id, and a refund path. Call it two to three days plus a permanent
consumer support surface -- against pennies of revenue and a signal we cannot yet interpret.

---

## 5. The recommendation, and the gate

**Do not build it now.** The gate is not a date and not a feeling:

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/source_arrivals.py --days 30 \
        --key tg-miniapp --key tg-miniapp-channel --key tg-miniapp-directory \
        --key tg-miniapp-blog --key tg-miniapp-bot

Run it after the item 1 discovery routes have gone out. **If the Mini App is producing arrivals in
numbers that make a willingness-to-pay experiment interpretable, revisit this page.** If it is not,
the answer is that the Mini App is a discovery surface and monetising it was never the point.

**If it is ever built, one principle decides the shape: Stars pay vendor bills, they never tax the
free tier.**

- **Never** a cap on `/v1/link-check` or `/v1/ton-address`. Those cost us nothing and are free on
  purpose.
- **The honest candidate is `/v1/scan-url`** -- VirusTotal, a real per-call bill, which is exactly
  why it needs a key today and why it already carries a $0.05 price on the PAYG rail. "The free
  check found nothing known against it; spend N Stars for a full multi-engine scan" is a real upsell
  for a real cost, and it never makes the free product worse.
- **A TON token scan** would likely be the same case, if its data source turns out to be paid. That
  is a question to answer when the endpoint is scoped, not now.

This is self-limiting by construction, which is the property that matters: it can only ever charge
for things that cost money, so it cannot drift into taxing the thing the app is for.

---

## 6. What I would rather spend the same days on

Since the question is really "what is the best use of the Mini App", and a recommendation with no
alternative is half an answer:

1. **Run the six discovery routes** (item 1). Each announcement channel gives one first impression
   and they are all still unspent. This is the only work that changes the size of the funnel.
2. **Then measure it**, with the command above. Nothing else on this page is interpretable until
   that number exists.
3. **Then build the TON token scan** if the TON catalogues in route (6) look worth entering -- that
   is a capability gap rather than a monetisation one, and it is the prerequisite for a whole
   discovery channel we cannot currently enter.

Monetisation of a consumer surface comes after all three, if at all.
