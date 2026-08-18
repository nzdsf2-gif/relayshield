---
title: "Your Wallet Provider Had a Vendor, and That Vendor Had a Dashboard"
slug: your-wallet-provider-had-a-vendor-and-that-vendor-had-a-dashboard
date: 2026-08-17
---

# Your Wallet Provider Had a Vendor, and That Vendor Had a Dashboard

I got a security notice from Kraken this week. Not about Kraken.

It was about Privy, the company that provides the embedded wallets behind Kraken's DEX trading and
DeFi Earn. And it was not really about Privy either. It was about Metabase, an analytics and support
tool operated by one of Privy's vendors, which was compromised through a previously unknown
vulnerability.

Count the hops. I have a relationship with Kraken. Kraken has a relationship with Privy. Privy has a
relationship with a vendor. That vendor runs Metabase. **My email address was four parties away from
the company I actually signed up with, sitting in a business intelligence dashboard, and that is
where it was taken from.**

Nothing was drained. Kraken's systems were not involved, and Kraken says accounts, login details and
funds were not affected. Privy told Kraken that Metabase has no access to its wallet infrastructure
or authentication systems, and that it cut the tool off immediately. Both companies disclosed
quickly and in plain language, which is more than the median in this industry. I want to be precise
about that before making any argument on top of it.

So on the surface, this is a nothing event. A dashboard leaked some email addresses.

I think it is the opposite. I think it is the most instructive kind of incident there is, precisely
because no wallet was touched.

## The attacker did not need the wallet

Here is the part worth sitting with. **An attacker who wants your crypto does not have to break your
wallet if they can get your email address plus the knowledge that you hold crypto.**

That second half is what makes this list valuable. A generic email dump is worth very little. A list
of addresses known to belong to people with funded embedded wallets on a specific exchange is worth
a great deal, because it turns a spray campaign into a targeted one. The phisher already knows the
product you use, the company name that will not look out of place in a subject line, and the
plausible pretext.

Kraken's own notice says it directly: the main risk here is phishing.

That is the whole attack. There is no exploit in it. The compromise of a support and analytics tool
produced a high-quality targeting list, and the actual theft, if it happens, will occur weeks later
in someone's inbox, and will look like a completely separate event.

## Fourth-party risk is not a category most people have

Plenty of organisations run vendor risk programmes. You screen your suppliers. Some of the more
mature ones screen their suppliers' suppliers.

**Almost nobody screens their suppliers' suppliers' internal tooling choices.**

I could not have told you before this week that Privy used Metabase, and there is no reasonable
process by which I should have known. I am a Kraken customer. My diligence, if I did any, stopped at
Kraken. Kraken's stopped at Privy, sensibly. Privy's covered its vendor. And somewhere down that
chain a business intelligence tool with a support dataset in it became the soft edge of the whole
structure.

This is not a failure of any one link. It is a property of the shape. **Each party did diligence on
the party it could see, and the exposure happened one layer past everyone's visibility.**

## The concentration problem underneath it

There is a second thing here, and it is the one I would actually worry about.

Privy is not a niche dependency. Embedded wallet infrastructure is exactly the kind of component
that many products adopt at once, because building custodial-adjacent wallet UX yourself is
genuinely hard and buying it is genuinely sensible. I ran into this from an unrelated direction the
same week: the CLI for a completely separate agent platform I was evaluating turned out to list
Privy as a direct dependency for its wallet auth and signing.

I was not looking for Privy. It was simply there, underneath something else.

**When one provider sits beneath many products, a data exposure at one of its vendors produces a
cross-product targeting list, not a single-product one.** The blast radius is not defined by who
had the vulnerability. It is defined by how widely the affected component is adopted.

That is the same lesson as every recent package registry incident, and the same lesson as the
identity-provider breaches before those. We keep learning it in different vocabularies.

## What actually follows from this

I am not going to pretend a tool would have prevented this, because none would have. Nobody outside
Privy's vendor could have seen that Metabase instance. Let me be exact about what is and is not
addressable.

**Not addressable:** the compromise itself, the fourth-party relationship, or your email address
being in that dataset. That was decided by architecture choices several layers away from you.

**Addressable:** the gap between the exposure and the phishing campaign. That gap is usually weeks,
sometimes months, and it is the only part of this timeline where a defender gets to act. Knowing
that an address has landed in a breach corpus is what converts "an unexpected email arrived" into
"an unexpected email arrived and I already knew I was on a list." Those two states produce very
different click rates.

Concretely, and in order of how much they matter:

1. **Treat every message about this incident as hostile.** The notice tells you the risk is
   phishing. The phishers know the notice went out, and a warning about a breach is itself a
   perfect pretext. Navigate to the exchange yourself. Do not follow links.
2. **Assume the pretext will be specific.** This list is not generic. Expect the sender to know
   which product you use.
3. **Know when your addresses appear in a corpus**, so that a targeted approach arrives against a
   background of knowledge rather than surprise. This is the layer we work on at RelayShield, and I
   will not overstate it: it does not stop the exposure, it shortens the window in which you are the
   only party who does not know about it.
4. **If you are building on embedded wallet infrastructure**, write down which of your dependencies
   would produce a customer-facing disclosure if one of *their* vendors were compromised. That list
   is shorter than you expect and it is worth having before you need it.

## The part I keep coming back to

The security industry is very good at analysing artifacts. We read the package, inspect the
contract, scan the endpoint, diff the binary.

**This incident had no artifact.** There was nothing to scan. A vulnerability in an analytics tool
at a vendor of a vendor produced a list of people who own crypto, and that list will be monetised
through a channel that no code scanner watches, using no malicious code at all, against people whose
only mistake was signing up for a product.

The identity layer is where the loss actually happens. It is just that it happens late enough, and
far enough from the original incident, that we usually file it as something else.

---

*RelayShield screens the identity layer: breach and infostealer exposure, SIM swap, lookalike
domains, and vendor risk. 494K+ distinct indicators drawn from 5.8M+ sightings, collected from 95
monitored channels and 20 authoritative feeds.
[api.relayshield.net/developers](https://api.relayshield.net/developers?source=blog-fourth-party)*

<!-- NOT FOR PUBLICATION BELOW THIS LINE -->

## Pre-publication checklist

**Verify before publishing. Nothing in the factual account should be softened or sharpened.**

1. **Re-read the Kraken notice against the post.** Every claim about what happened is drawn from it:
   Privy is the embedded wallet provider for DEX trading and DeFi Earn; the compromised tool was
   Metabase, operated by a Privy vendor, via a previously unknown vulnerability; it is used for
   support and analytics; the accessed data included email addresses; Metabase had no access to
   wallet infrastructure or authentication systems; access was cut immediately; Kraken systems,
   accounts, credentials and funds were unaffected; the stated main risk is phishing. **If any of
   that is not in the notice, cut the sentence rather than rewording it.**
2. **Check whether Privy has published its own statement** by Monday. If it has, link it and
   reconcile any difference. If its account differs from Kraken's relay of it, use Privy's.
3. **The agent platform reference is deliberately unnamed.** It is Virtuals ACP, whose CLI lists
   `@privy-io/node` as a direct dependency. Naming it invites a "you are picking on them" read for
   no gain, and the point stands without it. **Do not name it.** Do confirm the dependency still
   holds before publishing, since it is a load-bearing factual claim.
4. **Do not add a "we would have caught this" line.** Section four exists specifically to say we
   would not have. That honesty is the reason the post is publishable at all.
5. **No em-dashes, en-dashes, or ` -- `.** Replace individually. Never find-replace.

## Distribution

Canonical on the self-hosted blog, then:

- **Medium** (import, do not paste)
- **LinkedIn**
- **Telegram**
- **Farcaster** (counts BYTES, not characters)
- **Mastodon**

**NOT X** (@RelayShieldHQ suspended). **NOT Hashnode** (retired). **NOT HackerNoon** (paid for
company domains).

**Reddit is worth considering for this one specifically**, r/CryptoCurrency or r/ethdev, because the
post is a first-person account of a notice many people received rather than a product announcement.
Check each subreddit's self-promotion rule first. That is the lesson from the Discord work on
2026-08-13.
