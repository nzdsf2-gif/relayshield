# Mini App v1.2: the bot link, one paid scan, and the thing that actually made it feel blah

Written 2026-09-10, answering: *"Shouldn't there be a link to our Telegram monitoring bot with some
sort of plug highlighting its capabilities? ... it would be good to add one paid type scan where
user pays stars. Any other ideas to make this miniapp stickier and more interesting"*

**Read `miniapp_stickiness_plan.md` first; this does not repeat it.** That plan already covers the
watchlist, private scan history, the share card and the weekly digest, and it already rules out
points, streaks, leaderboards, a daily free-scan quota, TON Connect and a consumer referral tree,
each with a reason. **Items 1 to 3 of it are BUILT** -- the app has Check, Watching and Spot the
fake tabs, history, a watch button and a share card. This file covers only what that plan does not.

---

## 1. The bot link was a real hole, and it was worse than missing

**BUILT THIS SESSION.** `const BOT = "https://t.me/relayshield_bot"` was declared on line 41 of
`cloudflare_worker_miniapp.js` and **never used anywhere**. The only call to action in the entire
app was the footer link to the developers page: *"Run this check from your own bot or agent."*

So a consumer who had just been shown a flagged phishing domain was being sold an API.

**And it contradicted the plan's own mechanism.** The stickiness plan justifies the watchlist on the
grounds that it *"runs the flywheel in the right direction: the Mini App creates bot subscribers
rather than the bot's tiny audience carrying the Mini App."* That mechanism requires a path from
the Mini App to the bot. There was none.

**What shipped:**

- **An offer inside the verdict card**, shown only AFTER a result, with wording that follows the
  finding. On a high or critical verdict: *"Attacks like this start from a breached account.
  RelayShield watches your email, phone and wallets and tells you the moment one turns up."*
  On anything else, a plainer line. Pitching monitoring to somebody who has just been told "nothing
  known against it" in the same words used for a confirmed scam is how a product starts reading as
  an advert.
- **A footer link, first and above the developer one**, stacked rather than inline -- the two ran
  together as one unreadable sentence.
- **Attribution from day one, with nothing to register.** The link is
  `t.me/relayshield_bot?start=SRC_miniapp`. `SRC_` is the bot's existing acquisition-source deep
  link in `relayshield_telegram_webhook.py`, which takes a free-form channel label, logs it and
  stores it once on the user record. Unlike `_SOURCE_BANNERS` it needs no key registered in
  advance and cannot log `unmatched:`, so this is not the FD-8 shape.
- **`openTelegramLink`, not a bare anchor.** A plain `t.me` link inside a Mini App webview hands
  the URL to the system browser, and the user lands on a t.me web page asking them to open
  Telegram -- from inside Telegram. The href stays real as a fallback.

Six tests pin all of it, including that the bot still parses `SRC_`.

---

## 2. Stars: your instinct and the analysis agree, and the endpoint already exists

`miniapp_stars_monetization.md` recommended not building Stars yet, and it named one exception:

> **Stars pay vendor bills, they never tax the free tier.** The honest candidate is `/v1/scan-url`
> -- VirusTotal, a real per-call bill, already $0.05 on the PAYG rail.

**"One paid type scan" is exactly that exception, so this is not a reversal.** The thing that was
argued against was a QUOTA -- capping the free checks and charging to lift the cap. That remains a
no, for the reason the stickiness plan already gives: it converts a moment of genuine need into a
paywall at the instant somebody is about to be defrauded.

**The shape that works, and why it is self-limiting:**

| | |
|---|---|
| Free, unchanged | `/v1/link-check` (IOC corpus, Safe Browsing, RDAP) and `/v1/wallet-risk`. **No cost to us, no cap, ever.** |
| Paid, new | A deep scan on `/v1/scan-url` -- VirusTotal multi-engine. **Real per-call bill**, which is why it needs a key today |
| The offer | Appears only after a free check returns `low` or `unknown`: *"Nothing known against it. Run a full multi-engine scan for N Stars."* |

That last row is the part worth getting right. **The upsell belongs where the free answer is weakest,
not where it is strongest.** A `high` verdict needs no upsell -- the user has their answer. `low` and
`unknown` are exactly where a person is left thinking "but is it actually fine?", and that is a real
question a paid scan genuinely answers rather than a manufactured one.

**Cost to build, honestly:** the expensive half is done. `relayshield_watchlist.py` already verifies
Telegram's `initData` HMAC and derives `HMAC-SHA256(pepper, telegram_user_id)`, so a verified,
non-spoofable per-user identity exists and is live. What remains is an invoice via
`createInvoiceLink` with currency `XTR`, a `successful_payment` webhook branch, a credit ledger keyed
on that hashed id, and a refund path. **Two to three days**, plus a permanent consumer support
surface.

**The platform constraint, restated because it decides the design:** Stars are the ONLY compliant way
to charge a consumer inside a Telegram Mini App. Sending them to Stripe or x402 from inside the app
is the route that gets a bot restricted. **UNVERIFIED** from the container; the check is one tab,
<https://core.telegram.org/bots/payments-stars>, read BEFORE any payment code.

---

## 3. The real reason it felt blah, which neither plan had named

**Every item in the stickiness plan is a RETURN mechanic. None of them fixes the FIRST SCREEN.**

The watchlist, history, share card and digest all make the app better the second time you open it.
On first open the app is an empty text box, a button, and two tabs whose content is also empty. There
is nothing to look at, and nothing that demonstrates the product can do anything at all. A first-time
user has to supply their own scam URL before the app shows them a single interesting thing.

**That is what "blah" is, and it is the expensive one**, because the discovery plan's whole sequencing
rule is that each announcement channel gives ONE first impression. `@trendingapps` is 3.9M of them.
Those arrivals land on the empty state.

**The fix is one tap and it needs no new endpoint: demonstrate a real catch before asking for input.**

Under the input, on first open only, a single line: *"Not sure what to paste? See one we caught."*
Tapping it fills the box with a real flagged domain from the corpus and runs the check, so the user's
first experience of the app is a live CRITICAL verdict with real reasons, in about a second, having
typed nothing.

Three reasons this is the right first build rather than the obvious alternatives:

- **It uses the product to sell the product.** Not a screenshot, not marketing copy -- an actual
  scan of an actual flagged domain, running the same code path the user will use next.
- **It respects MEASUREMENT DOCTRINE.** No corpus headline, no counts, no "X million indicators".
  One concrete catch is both more persuasive and more defensible than any number we are allowed to
  quote.
- **It feeds the same moment the bot CTA now occupies.** A first-time user who sees a CRITICAL
  verdict immediately gets the monitoring offer immediately, in the wording matched to a high
  finding.

**Half a day.** The one care point: the demo domain must be one that is genuinely and durably
flagged, refreshed from the corpus rather than hardcoded to something that later goes clean, because
a demo that returns "nothing known against it" is worse than no demo.

---

## Recommended order

1. **The empty state.** Half a day, fixes the first impression, and the announcement channels are
   still unspent so the timing is right.
2. **Ship, then run the discovery routes** (Top 15 item 4). Nothing below is interpretable until
   there are arrivals to interpret.
3. **Measure.** `tools/source_arrivals.py --key tg-miniapp` and the `SRC_miniapp` acquisitions in the
   bot's own logs. **These two numbers together are the thing worth knowing:** how many people opened
   the app, and how many of them became bot subscribers. That is the flywheel, measured.
4. **Then the Stars deep scan**, if step 3 says there is a population worth charging.

Doing 4 before 3 is building a payment surface for a funnel nobody has counted, which is the same
error as reasoning from rsscan's unmeasured reach.
