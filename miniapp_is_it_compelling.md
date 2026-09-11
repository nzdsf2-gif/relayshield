# Is the Mini App compelling enough to be a destination people return to?

2026-09-11. My answer, to be overruled.

---

## Short answer

**Run route 1 now. Do not build anything else first.**

But the question contains a premise I think is wrong, and the premise matters
more than the answer.

---

## "A destination users want to return to" is the wrong bar, and chasing it makes the product worse

A security checker has a **rare, unpredictable moment of need**. Nobody wants to
open a scam checker on a Tuesday. The apps in this category that do get opened
daily are games with points attached, and that is a different product with a
different audience: points attract people who want points, and that audience
does not buy anything.

This repo already rejected points, streaks and a daily quota gate for exactly
that reason, and the quota gate for a sharper one: **a free-scan quota converts
genuine need into a paywall at the instant somebody is about to be defrauded.**

So the honest bar is not "do they come back". It is:

1. **Can we reach them at the moment of need?**
2. **Can we reach out when something changes, without them remembering us?**

Against that bar the app is in a materially different place than it was
yesterday.

---

## The three mechanics that matter, ranked

**1. The alert. Strongest, and it went from nonexistent to live today.**
`relayshield_watchlist_monitor.py` re-checks watched TON targets every six hours
and messages the user when the answer changes. This is the only mechanic that
brings somebody back **without them remembering we exist**.

Note where they come back to: **the bot chat, not the app.** That is fine, and
arguably better. An alert that arrives in a chat they already have pinned beats
an app they have to open.

**2. Inline mode. Highest value per unit of work, and it cost nothing because it
was already built.**

`handle_inline_query` has been complete, rate-limited and live the whole time:
type the bot's username then a link, **in any chat**, and the verdict posts into
that conversation. **Nothing told anyone.** Not the Mini App, not the share card,
not the bot's welcome.

That is the only surface that reaches the actual moment of need. The scam arrives
in a group chat while the user is thinking about something else; an app they have
to remember, find and open has already lost. Both the app and the share card
teach it now.

**3. The share card. The compounding one.**
It said "Checked with RelayShield" and left the reader to work out what to do
with that. It now names the mechanic, so a forwarded verdict teaches the next
person to run their own check in the chat they are already in.

---

## What is honestly still missing

**Nothing in the app.** The two gaps I would name are both measurement, not
features:

- **"Spot the fake" is the only repeat mechanic and nothing counts whether it is
  played.** It is not in `tools/miniapp_funnel.py`, so we cannot say whether the
  one deliberate return-visit feature works.
- **No route has ever run**, so every opinion about this app, mine included, is
  unmeasured. That is the same defect as rsscan: FD-1 says DONE, "done" is a fact
  about shipping, and nobody ever counted the arrivals.

---

## So: my recommendation, chosen rather than listed

**Run route 1, the Telegram blog channel, this week. Change nothing first.**

It is the only surface whose audience chose us, so a bad reception costs least
and the feedback is honest. It exists precisely to be the cheap answer before
anything larger is spent.

**Cost:** one post, plus two commands (`--snapshot before-blog`, then
`--compare before-blog` two days later).

**Who:** you. The commands are in `miniapp_discovery_funnel.md`.

---

## The one number that decides whether to spend @trendingapps

**BOT, not CHECKED.**

- **High CHECKED, low WATCHED, low BOT** means people use it once and leave. That
  is a utility, not a product, and four more channels will produce four more
  batches of people who use it once. **Fix the retention mechanic before
  spending 3.9M first impressions on it.**
- **CHECKED and WATCHED moving together** means the alert promise is landing, and
  `@trendingapps` is worth spending.
- **ALERTED above zero** is the strongest possible signal, because it means we
  told somebody something true that they could not have found themselves.

---

## Where I would be overruled, and it is your call not mine

If you believe the blog channel's audience is too small to produce a readable
number at all, then route 1 tells you nothing and you are better off spending
`@telegtapps` (9,671) first and treating the blog channel as a warm-up.

I would not, because a small honest number and a small unreadable number look
identical in the output and only you know that channel's size. **That is the one
figure in `miniapp_routes.json` recorded as UNMEASURED for our own surface**,
which is slightly embarrassing and worth one minute to fix before you decide.
