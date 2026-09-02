# Aduna — partner outreach

*Written 2026-09-01, for a warm intro through Andrew's own contact. Verified
against Aduna's public material the same day.*

---

## What Aduna is, in one paragraph

Aduna is the joint venture between Ericsson and the major operators — AT&T,
T-Mobile and Verizon as equity partners, with Bharti Airtel, Deutsche Telekom,
e&, KDDI, Orange, Reliance Jio, Singtel, Telefonica, Telstra and Vodafone as
venture partners — that aggregates **CAMARA-standardised network APIs** behind a
single integration point. Its two flagship APIs are **SIM Swap Detection** and
**Number Verification**. It is the only company with agreements covering
CAMARA-compliant network API access across the entire US market.

## The trap to avoid, and it is the obvious pitch

**Do not pitch SIM-swap detection to Aduna. That is their product.** We would be
walking into the one company on earth with better SIM-swap coverage than us and
offering them SIM-swap coverage. It is also the pitch they will assume we are
making, so getting off it in the first two sentences is the whole job.

## The actual position

> **Aduna tells you a SIM swapped. RelayShield tells you why it was about to.**

A SIM swap is the *last* step of an account takeover, not the first. Before it
happens there is almost always a signal we already hold and the network does not:
credentials for that identity in an infostealer log, an active session cookie
being sold, an OAuth grant to an app the user never authorised, a lookalike
domain registered against their employer.

The network sees the swap. It cannot see the criminal channel where the target
was chosen. Those are different data sources and neither substitutes for the
other — which is what makes this complementary rather than competitive.

## Two concrete asks, in order

### 1. We become a consumer of their SIM Swap API

Honest and immediately actionable. RelayShield already runs SIM-swap monitoring
via carrier lookups. Aduna's CAMARA API is better coverage, standardised across
operators, and would replace a patchwork we maintain ourselves. This costs them
nothing to say yes to and makes us a paying customer rather than a supplicant.

It also puts a real integration in place before any partnership conversation,
which is the difference between a partner and a pitch deck.

### 2. We become a demand-side reference for enterprise identity-fraud use cases

Aduna's problem is not supply — it has the operators. It is **demand**: showing
enterprises why to call a network API at all. They are already doing this
publicly (the BTS partnership on fraud prevention and identity verification, the
Microsoft collaboration). RelayShield is exactly the shape of ISV that makes the
case concrete: a small security product that can show, with a real workflow, why
a SIM Swap call belongs inside an account-takeover defence.

The joint story writes itself: *"criminal-channel signal says this identity is
being targeted; Aduna's network API confirms the SIM just changed; the account
is frozen before the transfer clears."* Neither half is sufficient alone.

## What NOT to say

- **No corpus size.** Not 511K, not any total. The measurement doctrine applies
  hardest in front of a company with real telco data, and it is a number they
  can check in a way most prospects cannot.
- **No customer names**, and no "used by" claims.
- **Nothing about Cortex XSOAR shipping.** PR #45206 is open, not merged. "In
  review with Palo Alto, all checks passing" is true and is enough.
- **Do not present as a competitor to their fraud partners.** We score the
  counterparty and the criminal source; the incumbents score the user and the
  funds. Say it that way if it comes up.

---

## The message — short version, for the warm intro

> Hi [name] — a favour, and tell me if it is the wrong ask.
>
> I run RelayShield. We do identity-compromise intelligence: breached
> credentials, infostealer logs, stolen sessions, and the criminal Telegram
> channels where account-takeover targets get traded.
>
> I have been reading what Aduna is doing with CAMARA and the SIM Swap API, and
> I do not want to pitch you SIM swap — you are better at it than anyone. What I
> think is interesting is the other half of the same attack.
>
> A SIM swap is the last step of an account takeover. Before it, there is usually
> a signal in a place a network cannot see: that identity's credentials sitting
> in a stealer log, or a session cookie being sold. We see those. You see the
> swap. Put together, that is a prediction rather than a notification.
>
> Two things I would genuinely like:
>
> 1. To become a customer of your SIM Swap API — we already do SIM-swap
>    monitoring through carrier lookups, and standardised coverage would be
>    better than what we maintain ourselves.
> 2. To be useful to you on the demand side, as a worked example of why an
>    enterprise calls a network API in the first place.
>
> Is there someone there it is worth me talking to? Happy to be told this is not
> a fit.

## The message — longer version, if the intro wants substance attached

Use the short version to open. Send this only if asked for detail.

> **What we do.** RelayShield monitors the sources an account takeover comes
> from, not the account itself: infostealer log dumps, credential-dump markets,
> phishing-as-a-service channels, and lookalike-domain registrations. We expose
> it as an API — breach exposure, stealer-log presence, active-session exposure,
> domain impersonation, and an identity risk score that combines them.
>
> **Why your API and ours belong in the same call.** The strongest signal in an
> account takeover is sequence. Credentials appear in a stealer log; a session
> cookie for the same identity is listed for sale; then the SIM changes. Any one
> of those alone is ambiguous. In order, it is an attack in progress. We can see
> the first two and cannot see the third. You can see the third.
>
> **What I am proposing, concretely.**
>
> - RelayShield integrates Aduna's SIM Swap Detection API in place of our
>   existing carrier lookups. We are a paying customer from day one.
> - We build one reference workflow, jointly reviewable, showing the combined
>   signal: our stealer-log finding plus your SIM-swap confirmation producing a
>   single account-freeze decision.
> - If it holds up, it is a case study you can point enterprises at, and a
>   distribution channel we could not build alone.
>
> **What I am not proposing.** I am not offering you SIM-swap detection, and I
> am not asking to resell network APIs. The integration is the point.
>
> Happy to run our side of the workflow live on a call rather than send a deck.

---

## Before sending — three checks

1. **Register the attribution key.** Any link in the message needs its `source=`
   key registered in `_SOURCE_BANNERS` in `relayshield_developer_signup.py`
   first. An unregistered key logs `unmatched:` and renders no banner, and this
   is a channel worth measuring.
2. **Re-read for a number.** If a corpus figure has crept in, take it out.
3. **Check CAMARA in `TODO.md`.** The CAMARA item there was scoped as "expose
   RelayShield endpoints TO telcos" and classified honestly as a deal rather
   than a flywheel. This outreach is the aggregator variant of that item and
   should update it rather than sit beside it.
