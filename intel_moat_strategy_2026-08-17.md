# Widening the moat from the 95 monitored channels

**2026-08-17.** Ranked by defensibility against time-to-value, grounded in what the corpus measurably
contains rather than what we hoped it contained.

> **Provenance note, added 2026-08-18.** This document was reconstructed from the founder's session
> transcript after a host crash. The 2026-08-17 working session was never committed or pushed: the
> last push to `nzdsf2-gif/relayshield` is `b7955fe`, 2026-08-12. **The code this document assumes
> is not in this repository.** See `SESSION_2026-08-18.md` for the gap analysis before implementing
> anything below.

## The constraint

13,358 distinct indicators from the 95 monitored channels, **99.89% of which appear in no public
feed we ingest**. Composition:

| Type | Distinct | Share |
|---|---|---|
| url | 7,927 | 59.3% |
| **crypto wallets (btc+sol+ton+eth)** | **4,460** | **33.4%** |
| domain | 594 | 4.4% |
| phone | 122 | 0.9% |
| cve | 83 | 0.6% |
| hash / image_text / ip / email | ~172 | 1.3% |

**92.7% of the value is URLs and wallets.** Every idea below is ranked by how much of that it uses.
Anything that depends on domains or emails is dead on arrival: 594 domains that are mostly news
sites, and 11 email addresses.

---

## 1. Wallet attestation. Absence, aimed at the right object.

**"Absence is the signal" was right. It was pointed at the wrong noun.**

It fails for company domains because the denominator is 594 news sites. It works for **crypto
addresses**, where the denominator is 4,460 addresses observed in criminal channels, because the
question "has this address ever been seen in a criminal channel" is one that exchanges, wallets and
analytics firms genuinely ask before moving funds.

Both directions sell:
- **Presence:** "first observed in a criminal channel on 2026-06-14, in 3 channels."
- **Absence:** "not observed across 95 monitored channels."

**`relayshield_address_first_seen` is already recording and nothing reads it.** That is a shipped
asset sitting unused. This is the shortest path from the corpus to revenue.

**Defensibility:** high. **Time to value: days.**

## 2. Scam URL freshness and lifetime decay

The largest slice (59.3%) and the least exploited. What nobody else has is **the moment a scam URL
was advertised in a criminal channel**. Pair that with a periodic liveness check and two products
appear:

- A blocklist with provenance: "advertised 2026-08-17 in @channel, still live 40 hours later."
- A statistic only we can compute: median scam URL lifetime, by kit and by channel.

The second is marketing that doubles as proof of access, which is the thing we struggle to
demonstrate.

**Defensibility:** high, and it compounds with the archive. **Time to value: 1 to 2 weeks** (needs a
liveness checker).

## 3. Actor and alias graph across channels

**The archive shipped today makes this possible for the first time.** Same seller handle appearing
across N channels, what they offer, when they appear and go quiet, which channels co-occur.

This is the only genuinely non-reconstructable asset on this page. A competitor starting in 2027
cannot rebuild what these channels said in 2026, at any price. It requires nothing but retention and
time, and it started accruing today.

**Defensibility:** highest. **Time to value: 3 to 6 months of accumulation**, but the clock started.

## 4. PhaaS kit to targeted brand mapping

15 phaas channels. Phishing kits name the brands they impersonate, and kit authors advertise which
brands they support. "Kit X currently targets Brand Y, first seen date Z" is differentiated, and it
is **victim-side with a buyer who does not need enterprise domain IOCs**: the impersonated consumer
brand itself.

**This is the honest recovery of the victim-side thesis.** The victim is a brand, not a domain, and
brand names are extractable from kit copy in a way company domains are not.

**Defensibility:** high. **Time to value: 2 to 4 weeks.**

## 5. CVE discussion heat

83 CVEs, accumulating since 2026-07-24. "Which CVEs are criminals actually discussing, and how
often" is a prioritisation signal that differs from CVSS and EPSS because it measures attacker
attention rather than theoretical severity. Small, cheap, and genuinely ours.

**Defensibility:** medium. **Time to value: already accumulating**, needs a scoring endpoint.

## 6. Phone numbers into SIM swap

122 phone numbers from criminal channels are a natural input to the SIM swap product. **Blocked on
that product, which has never worked end to end.** Listed for completeness, not as a priority.

---

## Discovery surface: converting eyeballs

The distribution problem is not only channel sales. What has actually worked is **a free artefact
that produces a shareable result**, which is the rsscan pattern.

**The wallet lookup is the same play.** A free, no-auth, rate-limited "has this address been seen in
criminal channels" page:

- The output is inherently shareable, because people paste addresses into group chats to ask exactly
  this question.
- It needs no account, so it converts curiosity into a first touch with zero friction.
- The paid conversion is obvious and honest: one free lookup, paid for bulk and API.
- It demonstrates the moat instead of asserting it. Every clean result still says "checked against
  95 monitored channels", which is the claim we want in front of people.

**Do not build a page per queried address.** That is thin-content SEO poison. Build one page, plus a
periodically regenerated "recently observed scam addresses" index that is genuinely useful and
genuinely indexable.

---

## Recommended order

1. **Wallet attestation** (days, data exists, unused table already recording)
2. **Free wallet lookup** as the discovery surface on top of it
3. **Scam URL freshness** (largest data slice)
4. **PhaaS brand mapping** (recovers victim-side with a real buyer)
5. **Actor graph** (compounds passively; no action needed beyond retention)

Items 1 and 2 are the same build and should ship together. That pairing turns the corpus into both a
product and a funnel, which is the only combination that addresses distribution rather than adding
another thing to sell.

---

## The honest positioning

Not more, not faster: **the only place you can see what is being sold about you.** Exclusivity and
victim-side, both of which the data supports.

The measured facts kill three candidate moats outright. Volume is 98.3% free public feeds. Speed is
unmeasurable. Enrichment is 99.84% MalwareBazaar/URLhaus labels. None of those can be defended, and
we should stop paying for copy that claims them.

**Two structural risks named in the same session:**

- **We are throwing away the compounding part every 6 hours.** There is no raw message retention in
  the pipeline: `relayshield_intel_seen` stores `message_id` for dedup only. We extract IOCs
  (commodity, 1.67% yield) and discard the message text. An 18-month archive of what these channels
  actually posted is not reconstructable by anyone starting later.
- **The cadence threatens the only differentiated asset.** `rate(6 hours)` with a 6h10m lookback.
  Criminal sale posts get deleted, so we only ever see what survives six hours. Tier it: 15 min for
  genuine marketplace channels, 6h for the CTI aggregators. That protects the 1.67% without
  multiplying flood-wait risk across the 73 dead channels.

**The unit of value is the listing, not the IOC.** An IOC says a hash is bad and every vendor sells
that. A listing says "4.2M records from acme.com, $8,000, posted three hours ago." Nobody sells that
as a feed at our price point, and it is the only artifact that is intrinsically victim-side rather
than attacker-side, which is what MSPs actually buy. `relayshield_marketplace_listings` having 0 rows
means the entire differentiated product is currently uncaptured.
