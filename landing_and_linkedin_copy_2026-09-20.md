# relayshield.net and LinkedIn: four new blocks, and three corrections that matter more

`relayshield_landing_page.md` is a **reference document for a Carrd build**, not code, so nothing
here deploys. Every block below is copy you paste into Carrd, and the same file in the repo is
updated so the two do not drift.

**Short answers to the four questions, before the copy:**

| Question | Answer |
|---|---|
| Email checker | **Yes.** It is live, it is free, and nothing on the consumer site mentions it |
| LinkedIn | **Yes**, and it needs its own `?source=` key, registered in this commit |
| Crypto Shield Mobile | **Yes, and link rather than describe.** It is already live on the Solana dApp Store and already has its own landing page at `cryptoshieldmobile.relayshield.net` |
| Telegram Mini App | **Yes, and it is the strongest of the four**, because it is the only one a visitor can try in ten seconds without giving us anything |

---

## FIRST: THREE THINGS ON THE PAGE TODAY THAT ARE WRONG. ONE IS A PRICE.

I found these while writing the blocks below, and they outrank the additions.

### 1. THE $499 CLAIM IS A PROMISE WE DO NOT KEEP

The Developer / API block says:

> subscribe at **$499/month for unlimited access** across all 23 endpoints

`relayshield_developer_signup.py` says, in its own comment above the price map:

    mp_499   = $499/mo -- 10,000 calls/month cap (enforced by
               _check_and_increment_intel_quota in relayshield_api.py)
    mssp_999 = $999/mo -- unlimited (intel_access=True, no quota gate)

**So $499 is capped and $999 is the unlimited one.** A buyer who pays $499 expecting unlimited
hits a quota gate at 10,000 calls, and the page is what sold them the expectation. This is the
rule that already cost this repo a listing correction once: **copy shown to a buyer that
disagrees with what the server grants is a price we do not honour.**

**Replace that sentence with:**

```text
Available as a REST API for SOAR playbooks, SIEM enrichment, AI governance workflows and incident response. Pay as you go from $0.10 a call with no minimum, or subscribe: $499/month for 10,000 calls, $999/month uncapped.
```

### 2. "23 endpoints" IS 31

Counted from the dispatcher rather than recalled: `relayshield_api.py` carries **31 distinct
`/v1/metered/*` paths**. The number in that sentence has been stale for some time.

**My recommendation is to drop the count rather than update it**, and the reasoning is the same
one that took the corpus figures off the AWS listing: a number that moves every time we ship
needs maintenance to stay honest, and "the endpoints the consumer product runs on a schedule,
callable directly" tells a developer more than "31" does. If you want a number, 31 is correct
today.

### 3. THE CORPUS FIGURES ARE BOTH STALE AND AGAINST OUR OWN RULE

The same block says *"exceeds 1,000,000+ indicators across 20 threat intelligence feeds,
tracking 1,000+ malware families"* and *"25+ criminal Telegram channels"*.

Measured figures are **494K distinct indicators, 5.8M sightings, 113 active channels** as of the
TI demo re-measurement on 2026-09-16, so the page understates the channels by four times and the
indicator figure is in a different unit from the one that matters.

**But the rule is not to correct them, it is to stop quoting them.** MEASUREMENT DOCTRINE: most
of the corpus is ingested public feeds every target buyer already has, quoting the headline
nearly killed the Segment 1 outreach in front of people who checked, and the AWS listing was
rewritten to name **sources and capabilities rather than counts** for exactly this reason.

**Replace the paragraph with:**

```text
RelayShield does not wrap public breach databases. Our intelligence pipeline collects continuously from criminal Telegram marketplaces, infostealer log dumps and public indicator feeds, and surfaces indicators before they reach the public aggregators. We deliberately do not quote a corpus headline: most of any vendor's total is ingested public feeds you already have, and the number that matters is what you find in it that you could not find anywhere else.
```

That last sentence is a differentiator rather than an omission, and it stays true without
maintenance.

---

## BLOCK A -- THE EMAIL CHECKER

**Placement: directly after the EMAIL SECURITY SWEEP block.** They are about the same inbox and
the reader is already there. It also gives the page its first thing a visitor can DO, which it
currently does not have until the pricing table.

**Section heading:** Not sure about an email? Forward it.

**Body:**

```text
Forward any suspicious email to checkemail@relayshield.net and you get a plain-English verdict back, usually within a minute.

No account. No signup. Nothing to install. It works from the inbox you already have, on the phone you are already holding.

What it reads:
- Whether the sending domain is one we have seen in criminal markets
- Whether the reply-to address quietly differs from the sender, the oldest trick there is
- Whether the links go where the text claims they go
- Whether the display name is impersonating a brand you would trust

It will never tell you an email is safe. The most it says is that nothing is known against it, because an absence of evidence is not proof, and a checker that says "safe" is training you to trust the one it misses.
```

**CTA:** `Forward an email to checkemail@relayshield.net`
**Style:** text, not a button. There is nothing to click; the action is in their mail app.

**The address is `checkemail@`, not `emailcheck@`.** It has been written the wrong way round
twice, in the message asking for it to be put on four surfaces, which is why
`relayshield_forward_analysis.py` holds it as a single constant.

---

## BLOCK B -- THE TELEGRAM MINI APP

**Placement: immediately above PRICING.** It is the last thing a visitor reads before the money,
and it is the only thing on the page they can try without giving us anything.

**Section heading:** Check something right now, free.

**Body:**

```text
Paste a link, a TON address or a Telegram handle and get an answer in seconds. It runs inside Telegram, so there is nothing to install, no signup and no wallet to connect.

- A link is checked against Google Safe Browsing, our criminal indicator corpus and domain age
- A TON address is checked for drainer and scam-token signals
- A @handle is checked before you trust a bot or an account that messaged you

Watch up to three addresses free and get a message the moment something changes.

It is the same intelligence the monitoring plans run on a schedule. This is the part you can hold in your hand first.
```

**CTA button:** `Open the checker in Telegram →`
**URL:** `https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-blog`

**On the key:** `tg-miniapp-blog` is the registered key for arrivals from our own surfaces. If
you would rather keep the consumer site separable from the Telegram blog channel, say so and I
will register `tg-miniapp-landing` before the copy goes up, which is one commit. **Do not invent
one in Carrd** -- an unregistered key is silently downgraded to the generic `tg-miniapp` at the
Worker's edge and logs `unmatched:`, which is attribution that looks like it worked.

---

## BLOCK C -- CRYPTO SHIELD MOBILE: LINK IT, DO NOT DESCRIBE IT

**It is live.** `cloudflare_worker_cryptoshield_landing.js` says *"Available now on the Solana
dApp Store"*, and the file carries v1.5.0 certificate-rotation notes, so it has shipped and been
updated. **I checked rather than assumed, and I nearly got this wrong**: the store metadata in
the repo is headed "Draft", which reads as pre-launch and is actually a draft of a copy
CORRECTION to a live listing.

**So the recommendation is a short pointer, not a description.** A full product block on the
consumer page competes with the thing that page exists to sell, and the app already has a
landing page of its own that is better than anything I would write into this one.

**Placement: inside the FINAL TRUST BLOCK, as one line, or as a small card in the footer.**

```text
Hold crypto? Crypto Shield is our read-only wallet monitor for Solana, EVM, TON, Bitcoin and XRP. It never asks for a seed phrase and it cannot move your funds. Available now on the Solana dApp Store.
```

**CTA:** `See Crypto Shield →`
**URL:** `https://cryptoshieldmobile.relayshield.net`

**UNVERIFIED:** whether that page carries a `?source=` for arrivals from relayshield.net. It is
our own Worker, so it is one edit if you want the split; tell me and I will do it.

---

## BLOCK D -- LINKEDIN

Two different surfaces with two different jobs. **A key is registered for the first and not the
second**, deliberately.

### D1. The company page's About section, and its Website field

**The Website field is the one that matters**, because it is the only link on a LinkedIn company
page that a visitor sees without scrolling. Set it to:

```text
https://api.relayshield.net/developers?source=linkedin-about
```

**`linkedin-about`, not `linkedin`.** The bare `linkedin` key resolves to the LLMjacking post's
banner, on purpose -- that published post links with it and repointing it would hand its existing
readers the wrong landing. A general company-page visitor shown a banner about leaked LLM
provider keys is being told what they came for, wrongly. `linkedin-about` has its own banner,
registered in this commit, which is the order the rule requires.

**About section, ~1,300 characters:**

```text
RelayShield is identity-exposure intelligence with a response layer on top of it.

Most tools detect a breach and stop. We monitor what happens after it: the SIM swap that silences your alerts, the infostealer log that carries a live session rather than a password, and the account takeover at the end of the chain. Then we walk the person through the fix, step by step, in the messaging app they already use.

The intelligence comes from criminal Telegram marketplaces, infostealer log dumps and public indicator feeds. We deliberately do not quote a corpus headline: most of any vendor's total is ingested public feeds you already have, and what matters is what you find in it that you could not find anywhere else.

Three ways to use it:

Consumers and small teams: monitored plans with breach, SIM swap and session-hijack alerts delivered in WhatsApp and Telegram, plus a guided remediation that follows up until the fix is actually done.

Developers and security teams: a REST API over the same intelligence. Pay as you go from $0.10 a call, no minimum. Link screening and wallet screening need no key at all.

AWS Marketplace: bundled subscriptions for procurement teams who would rather buy through a contract they already have.

Free, no signup: forward a suspicious email to checkemail@relayshield.net, or open the checker in Telegram at t.me/relayshield_bot/idcheck.

Built by a 25-year telecom security professional.
```

**Tagline, 120 characters:**

```text
Identity-exposure intelligence with a response layer. We monitor what happens after the breach, then fix it with you.
```

### D2. A post announcing the free checks

**Post, not the About section**, because a post is what the feed distributes and the About
section is what somebody reads once they have arrived.

```text
Two things we run that cost nothing and need no account.

Forward a suspicious email to checkemail@relayshield.net and you get a plain-English verdict back, usually inside a minute. It reads the sending domain against criminal-market activity, checks whether the reply-to quietly differs from the sender, and checks whether the links go where the text says they go.

Or paste a link, a TON address or a Telegram handle into the checker at t.me/relayshield_bot/idcheck and get an answer in seconds.

Neither will ever tell you something is safe. The most either says is that nothing is known against it, because an absence of evidence is not proof, and a checker that says "safe" is training people to trust the one it misses.

That ceiling is deliberate and it is the whole product philosophy. Detection is not protection. What you do in the next ten minutes is.
```

**EXISTING POSTS EACH HAVE THEIR OWN KEY** -- `gitlab-cve-linkedin`, `secret-scan-linkedin`,
`session-hijack-linkedin`, `x402-linkedin` -- which is one key per POST, and it is the right
pattern. **This post links to Telegram and to an email address, neither of which reaches the
landing page**, so there is nothing for a `?source=` to attach to and none is registered. If you
add a "read more" link to `api.relayshield.net/developers`, tell me and I will register
`linkedin-freechecks` first.

---

## WHAT IS REGISTERED IN THIS COMMIT, BEFORE ANY OF THIS SHIPS

Two keys in `_SOURCE_BANNERS`, each with its own banner rather than an alias, because
`_resolve_source` applies aliases BEFORE the banner table and an alias makes an own banner
unreachable:

- **`relayshield-net`** -- the consumer site's "View Developer API" button. **That button has
  always pointed at the bare `/developers` with no `?source=` at all**, so every developer
  arrival from our own consumer site has been indistinguishable from organic traffic, for as long
  as the page has existed. Change the URL in Carrd to
  `https://api.relayshield.net/developers?source=relayshield-net`.
- **`linkedin-about`** -- the company page Website field, above.

Count arrivals on either with:

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/source_arrivals.py --days 30 --key relayshield-net
