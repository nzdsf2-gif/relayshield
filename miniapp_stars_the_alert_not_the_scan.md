# Stars: charge for the alert, not the scan

Written 2026-09-10, after the founder rejected the previous proposal in one line:
*"Not sure I like the idea to charge Stars for a service a user can get for free on HIBP."*

**He is right, and the objection kills more than the HIBP idea.** It rules out every SCAN-shaped
paid product we could offer, for a reason worth stating once: **a scan is a one-off answer, and its
value evaporates the second you have it.** Any single scan is therefore comparable to something free
somewhere, and comparison is the only thing a consumer does before spending money.

**A SERVICE OVER TIME cannot be got free, because it requires somebody to keep watching.** That is
what RelayShield actually sells. It is also, it turns out, the thing the Mini App already promises
and does not do.

---

## The finding that decides this, and it is a live defect

`relayshield_watchlist.py` encrypts the chat_id and says why, in its own words:

> reversible: we cannot send an alert without the chat_id, and we cannot re-run [the check] without
> the target.

So it was designed to alert. **Nothing re-checks a watch and nothing sends an alert.** There is no
scheduled monitor, no EventBridge rule, no notification code anywhere in the file, and no workflow
naming it.

**"Tell me if this changes" is a button in the shipped app that makes a promise nothing keeps.**
That is the `_APIFY_BANNER` shape -- a live surface asserting a capability we do not have -- and it
needs fixing whether or not a single Star is ever charged.

---

## The proposal

| | |
|---|---|
| **Free, unlimited, keyless** | Check any link or address. Unchanged, forever. This is the urgent moment and it is never paywalled |
| **Free** | Watch up to 25 things and see their current status when you open the app |
| **Stars** | **We message you in Telegram the moment one of them flips** |

**Why this survives the objection that killed the last one:**

1. **Nobody offers it free, because nobody else can.** HIBP tells you about the past. Etherscan
   tells you what a wallet did. Neither watches YOUR list against indicators collected from criminal
   Telegram channels and pushes you a message. The comparison a user makes before paying has no
   answer on the other side.
2. **The data exists today.** It reads the same corpus the free check already reads. **No INTEL-5
   dependency**, which is what sank the last two proposals.
3. **It is the clearest vendor-bill case in the product.** A scan costs one lookup. A watch costs a
   lookup per item per interval, forever. "Stars pay vendor bills, they never tax the free tier" is
   not a principle being stretched here; this is the case it was written for.
4. **It never paywalls the moment of need.** The stickiness plan rejects a daily free-scan quota
   because it *"converts a moment of genuine need into a paywall at the exact instant somebody is
   about to be defrauded."* This is the opposite: the urgent check stays free and unlimited, and the
   paid thing is a convenience nobody needs in an emergency.
5. **It is the monitoring subscription in miniature, so it is an on-ramp rather than a competitor.**
   Somebody who spends Stars to be told when a wallet turns bad has demonstrated exactly the
   willingness-to-pay that converts to a plan. A one-off scan sale demonstrates nothing and teaches
   them we are a utility.
6. **The alert IS the retention mechanic.** Every other item in `miniapp_stickiness_plan.md` hopes
   the user comes back. This one gives them a reason, delivered to the surface they already have
   open. Stickiness and monetisation from one build.

---

## What it costs, honestly

**The work is not "add Stars". It is "make the watchlist actually watch", and that is owed
regardless** because the button already promises it.

- **A scheduled monitor Lambda** -- read watches, re-run each through the same endpoint the widget
  calls, compare to the stored verdict, send on change. This is the same shape as
  `relayshield_domain_monitor.py` and `relayshield_oauth_watchlist_monitor.py`, both of which already
  exist and can be copied rather than designed.
- **The payment half** -- `createInvoiceLink` with currency `XTR`, a `successful_payment` branch, an
  entitlement flag on the existing hashed user key, and a refund path.

Call it **two days for the monitor and two for payments**, and the first two are not optional.

**Ship the monitor FIRST and free**, for everyone, for a while. Three reasons: the button stops
lying immediately; the alert is the strongest retention mechanic in the app and should not be behind
a paywall while the funnel is still unmeasured; and when Stars does arrive, the thing being sold is
something users have already felt the value of rather than something they have to imagine.

---

## The one number that decides the price

Not a guess: **how many watches actually flip.** If a watched item changes state once a month across
the whole user base, the alert is worth little and this is the wrong product. If it is common, the
price can be real.

That number does not exist yet and cannot until the monitor runs. **So the monitor is the
measurement as well as the feature**, which is another reason to ship it free first and price it
second.

---

## What is now ruled out, so it is not re-proposed

- **HIBP breach lookup.** Free elsewhere. Founder's call, 2026-09-10, and correct.
- **Infostealer / stolen-session lookup.** The right product, no data. `relayshield_stolen_sessions`
  holds 9 rows, all `demo`, and INTEL-5 fixes collection going forward with no history.
- **A deeper scan of the same URL.** After a CRITICAL verdict the user has their answer; after
  UNKNOWN, a second opinion on the same three sources is not a different answer. The founder made
  this argument and it was right.
- **A daily free-scan quota.** Rejected in `miniapp_stickiness_plan.md` for a reason that has not
  changed.
