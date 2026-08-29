# OpenRouter, now Stripe: the integration angle

*Written 2026-08-27. Both premises verified before anything was built on them.*

## The two facts this rests on

1. **Stripe agreed to acquire OpenRouter for $7B+**, announced 2026-08-16, confirmed on Stripe's own
   newsroom. OpenRouter routes across 400+ models from 80+ providers. The price is roughly 5.4x the
   $1.3B Series B valuation from three months earlier.
2. **We can now detect stolen OpenRouter keys.** `sk-or-v1-[0-9a-f]{64}`, CRITICAL, provider
   `openrouter`, added 2026-08-27 to the monitor, the API and the rsscan mirror. Before that the
   corpus could not see them at all: the generic `sk-` catch-all has no hyphen in its body class, so
   it stopped at `sk-` and every router key that crossed our collection surface was dropped silently.

Our standing: **we are a customer**, and we want to partner with Stripe. That is a better opening
than a cold vendor email, and it is true.

## Why a router key is the one worth catching

Every other LLM key on our list is single-vendor. A leaked OpenRouter key is **standing access to
every model the account can reach, billed to the account owner, with no per-vendor key anywhere to
revoke.** It is the master key of LLMjacking. That was true before the acquisition; the acquisition
changes who cares.

**Reframe for a Stripe-owned OpenRouter:** a stolen router key is not primarily a security incident,
it is **unauthorised spend on an account**. That is card-not-present fraud with a different
credential, and knowing that a charge is not the customer is the thing Stripe's entire business is
built on. The pitch lands differently at Stripe than it would have at standalone OpenRouter.

## The integration, and it is a closed loop rather than a feed

This is the part that makes it real rather than a data sale. OpenRouter already ships the second
half.

**Their side, verified:** a **Provisioning API key** manages other keys and cannot call completions.
Under `/api/v1/keys` it can create, read, update and **delete** keys, each with a spend limit and
optional daily/weekly/monthly reset and a label. OpenRouter's own documented use cases include **key
rotation for security compliance** and **automatically disabling keys that exceed limits**.

**Our side:** detection of a specific `sk-or-v1-` key appearing in criminal Telegram channels and
stealer logs.

**The loop:**

    RelayShield sees the key in a criminal channel
        -> alert names the key (hash and prefix, never the full secret)
        -> customer's automation calls DELETE /api/v1/keys/{hash} with a provisioning key
        -> key is dead before the spend

No human in the loop, and the outcome is measurable in one number: **time from leak to revocation**.
That is a metric a payments company understands immediately, and it is the same shape as the
agentic-commerce story we are already telling elsewhere.

## The objection that will come first, and the honest answer

**"GitGuardian already detects OpenRouter keys."** True, and they have a published detector for this
exact pattern. Do not argue the detection; argue the surface.

| | Where it looks | When it catches the key |
|---|---|---|
| GitGuardian and repo scanners | source code, commits, CI | at the moment of the mistake |
| RelayShield | criminal Telegram channels, stealer logs | at the moment of **resale** |

A key exfiltrated by an infostealer from a developer's machine was never in a repository. Nothing
that scans code will ever see it. It surfaces when someone tries to sell or use it, which is the
surface we collect. **These are complements, and saying so is more credible than claiming to replace
a tool they may already run.**

## What we must not say

- **No number.** We have detected zero OpenRouter keys, because the pattern is not deployed yet.
  Any implication that we hold a corpus of router keys is false and checkable. The claim is
  capability and collection surface, not volume.
- **No "we would have caught X".** We have no such case.
- Do not describe this as fraud detection for Stripe's core payments business. It is credential
  exposure upstream of spend on one specific product they just bought.
- The standing measurement rule applies: nothing quoted until
  `exclusive_share_by_category.py` has run on the category and it clears 100 collected indicators.

## Sequence

1. **Deploy the pattern.** It is committed and not yet live. Until then this is a design, not a
   capability. Forward-only once deployed: it matches what is collected after the deploy and does
   not re-scan history.
2. **Let it run.** Two to four weeks. Either router keys appear in the collection surface or they do
   not, and both answers are worth having before any conversation.
3. **Build the revocation loop as a reference implementation.** Small: a webhook that takes our alert
   and calls `DELETE /api/v1/keys/{hash}`. It is the difference between selling a feed and shipping
   an outcome, and it is a weekend of work.
4. **Then approach**, as a customer with a working loop and a measured answer, through the Stripe
   partner motion rather than an OpenRouter support address.

## The connection worth making explicitly

This and the Rain work are the same argument in two markets. Rain: nothing checks whether the thing
an agent pays is legitimate. OpenRouter: nothing checks whether the credential an agent spends with
is still the owner's. Both are the question of **who is actually transacting**, which is the thing we
built. Neither is a threat-intel feed pitch, and both should be told as one story if they ever end up
in the same room.
