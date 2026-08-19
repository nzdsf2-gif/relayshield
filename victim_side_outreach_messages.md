# Victim-side outreach — sendable drafts

Source of truth for targets and sequencing: `Victim_Side_Outreach_Targets.md` (Side SaaS
Hustle), measured 2026-08-17. Segments A/B/C (M&A diligence, vendor risk, cyber insurance)
are **PARKED** — 594 mostly-news domains and 11 emails will not survive one question from a
technical buyer. Everything below is crypto, which is where the 91.6% actually is.

**Order: Segment 2 (wallets) → Segment 1 (analytics) → Segment 3 (exchanges/embedded).**

**Numbers used below are the measured ones. Do not round them up, and re-measure before any
send that happens more than a week from 2026-08-17.**
13,358 distinct indicators · 7,927 URLs · 3,131 BTC · 1,215 SOL · 99.89% of channel
indicators appear in no public feed we ingest.

---

## Segment 2 — wallets (send first)

### MetaMask / Consensys — warmest thread, Snap already published

> Hi <name> — I built the RelayShield Snap that's live in the MetaMask directory. Following up
> with something that sits behind it rather than another integration ask.
>
> We monitor criminal Telegram channels and pull scam infrastructure out of them directly.
> Current corpus is 13,358 distinct indicators: 7,927 scam URLs, 3,131 BTC addresses, 1,215 SOL
> addresses. We measured overlap against the public feeds we ingest — 99.89% of what comes out
> of those channels appears in none of them. It is early, it is criminal-sourced, and it is not
> a re-packaged public list.
>
> Two things I'd value 20 minutes on: whether pre-signature warnings inside MetaMask could
> consume a feed like this, and what your bar is for accepting third-party threat data.
>
> Happy to send a sample slice for you to check against your own coverage before any call —
> that seems like the only honest way to make this claim.

### Phantom — Solana-first, 9.1% of the corpus is SOL

> Hi <name> — short version: we pull scam wallet and URL intelligence out of criminal Telegram
> channels. 1,215 distinct Solana addresses in the current corpus, and 99.89% of our channel
> indicators do not appear in the public feeds we ingest.
>
> Phantom already warns on known-malicious sites. The question I'd like to put to you is
> whether criminal-channel-sourced addresses arrive earlier than what you have now. That is a
> testable claim, not a pitch — I'll send a sample slice and you can check it against your
> own blocklist. If the overlap is high, I'll stop bothering you.

### Trust Wallet / Rabby — same shape, one paragraph shorter

> Hi <name> — we source scam wallet addresses and phishing URLs from criminal Telegram
> channels rather than from public feeds. 13,358 distinct indicators today; 99.89% of them do
> not appear in the public feeds we ingest. Solana and Bitcoin are the heaviest segments.
>
> Would a sample slice be useful to check against your existing blocklist? If it overlaps
> heavily there is nothing here for you and I'd rather find that out fast.

---

## Segment 1 — blockchain analytics and compliance

TRM Labs, Chainalysis, Elliptic, Merkle Science. Roles: Head of Data Partnerships, Director of
Threat Intelligence, VP Product (Investigations). Merkle Science decides fastest; Chainalysis
slowest — verify their current data-partner programme before writing.

> Hi <name> — data-partnership question rather than a product pitch.
>
> RelayShield collects scam infrastructure from criminal Telegram channels: 13,358 distinct
> indicators, of which 3,131 BTC and 1,215 SOL addresses, plus 7,927 scam URLs. Measured
> against the public feeds we ingest, 99.89% appear in none of them. It is attribution-adjacent
> data — addresses named in the channels where the scams are actually coordinated — which
> should be additive to on-chain analysis rather than competitive with it.
>
> Is there a route for evaluating an external attribution feed at <company>? I can provide a
> sample and the collection methodology, including the parts that are weak: it is crypto-scam
> heavy, and the breach/victim-domain side of our corpus is thin by comparison.

---

## Segment 3 — exchanges and embedded wallets (gated)

**Privy — only after the Kraken/Privy post publishes, and only as a courtesy heads-up.**
Not a pitch. If it reads as one, it damages the thing it is meant to open.

> Hi <name> — heads-up as a courtesy, not a pitch. I'm a Kraken user and received their notice
> about the Privy incident. I've written up the fourth-party exposure angle — a user of a
> product, exposed through a vendor's vendor — and it publishes at <URL> on <date>. It quotes
> the notice, it does not speculate beyond it, and it is a first-person account rather than a
> teardown. Wanted you to see it before it goes out rather than after.

**Kraken** — same note, addressed to their security team, referencing their own notice.
**Dynamic / Turnkey / Magic** — same fourth-party theme, send only after the post is live.

---

## Before sending anything

1. Find real names per the file's method: LinkedIn on the role titles, prefer someone who has
   spoken publicly on threat-intel sourcing, reference the specific thing they said.
2. **Sample slice must be prepared before the first send** — every message above offers one.
   Offering evidence and then stalling is worse than not offering it.
3. Log every send in the contact-log table in `Victim_Side_Outreach_Targets.md`.
