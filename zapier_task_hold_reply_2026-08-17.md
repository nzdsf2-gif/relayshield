# Zapier: 121 held tasks, reply to Abraham

**Context.** Abraham D. (Partner and Platform Support) confirmed on 2026-08-17 that exiting beta is
automatic after 3 months and does not depend on active users or Zaps. Separately, the account has hit
the **free plan's 100 tasks/month ceiling** and **121 tasks are being held**, with the upgrade prompt
as the only offered route.

**The angle:** we are an approved integration partner in beta, not an ordinary free user. Testing our
own integration consumes the same task quota as normal use, which is a legitimate partner-support
question rather than a billing complaint. Abraham is already the open thread.

**Ask for a partner or developer plan. Do not open with a complaint about the paywall.**

## The message

```text
Hi Abraham, thanks for the quick answer on the beta timeline, that clears it up.

One related thing. Our account has hit the free plan's 100 task per month limit and now has 121 tasks on hold, with an upgrade prompt as the only route offered.

The reason I am raising it with you rather than billing: a good part of that consumption is us exercising our own integration during beta, which is exactly what you asked partners to do. Testing our RelayShield integration draws down the same task quota as ordinary use, so the more thoroughly we test, the faster we hit a wall.

Two questions:

Is there a partner or developer plan for approved integrations that covers testing your own app? Several platforms do this and I did not want to assume either way.

If not, do the held tasks release on the next monthly reset, or are they lost unless the plan is upgraded? I would rather plan around the real behaviour than guess.

Not asking for a favour, just want to understand the options before deciding anything.
```

**181 words.** No complaint, no leverage attempt, and it gives him something easy to say yes to.

## Do this regardless of his answer

**Find out what is actually consuming 100 tasks a month.** The number matters more than the hold: if
a Zap is polling on a schedule, it will hit the ceiling again next month and every month after,
whatever Zapier says now.

- Zapier's Task History shows consumption per Zap. Sort by task count.
- **Polling triggers are the usual cause.** A Zap that polls every 15 minutes burns roughly 2,880
  checks a month even when nothing happens, and depending on the trigger type some of those count.
- Turn off any Zap that exists only as a demo or a leftover test. Those are pure waste.

**If the consumption is our own integration testing**, that is worth knowing precisely, because it is
also the strongest possible evidence for the partner-plan request above.

## What not to do

- **Do not upgrade to release the 121 tasks.** The tasks are the sunk cost; the plan is the recurring
  one. Paying a monthly fee to recover a one-off backlog is the trade Zapier is engineering here.
- **Do not treat the beta as at risk.** Abraham confirmed the 3 month exit is automatic and is not
  conditioned on usage, so a paused Zap does not threaten the listing.
