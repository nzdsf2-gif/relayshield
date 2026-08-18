# Outreach Target List: where the intelligence actually sells

**Created 2026-08-17, after measuring the corpus rather than assuming its shape.**

**Headline: the corpus is 91.6% URLs and crypto wallets. It is a crypto-scam corpus, not a
breach-data corpus.** The victim-side company-exposure pitch (M&A diligence, vendor risk, cyber
insurance) is PARKED because the data does not support it yet. The crypto segments are contactable
now. Read the composition section before sending anything.

---

## What the corpus actually is, measured 2026-08-17

Before any pitch, the composition. Of **13,358 distinct indicators** sourced from the monitored
Telegram channels:

| Type | Distinct | Share |
|---|---|---|
| url | 7,927 | 59.3% |
| wallet_btc | 3,131 | 23.4% |
| wallet_sol | 1,215 | 9.1% |
| **domain** | **594** | **4.4%** |
| phone | 122 | 0.9% |
| wallet_ton / cve / hash / ip | ~284 | 2.1% |
| **email** | **11** | **0.1%** |

**91.6% of the corpus is URLs plus crypto wallets.** This is a crypto-scam corpus. It is not a
breach-data corpus.

## The absence signal does not work yet, and this kills the diligence pitch

"This domain has not appeared across 95 monitored criminal channels" needs a denominator with power.
Ours has 594 domains, and a random sample of 30 is almost entirely **news sites and web
infrastructure**: youtube.com, facebook.com, schema.org, github.githubassets.com, malwarebytes.com,
7news.com, sundayguardianlive.com, serbiantimes.info, thedailyaus.com, auburnpub.com.

Those are domains scraped out of **article links in CTI news reposts**, not companies named as
victims. Not one of the 30 sampled was victim-shaped.

**So "your domain is not in our corpus" is trivially true for essentially every company on earth,
and a technical buyer will work that out in one question.** With 11 emails and 594 mostly-news
domains, the victim-side company-exposure product does not have data behind it today.

**Segments A, B and C below are therefore PARKED, not ready.** They are recorded because the thesis
is sound and the data gap is fixable, not because they are contactable this quarter.

---

## Where the data DOES support outreach: crypto

The 91.6% is not a consolation prize. It is a genuine asset, it is exclusive on the same measured
basis (99.89% of channel indicators appear in no public feed we ingest), and it aligns exactly with
the products that already exist: Crypto Shield Mobile, the MetaMask Snap, the wallet-scanning
endpoints, and the Kraken/Privy post publishing today.

**Pitch:** scam URL and wallet intelligence sourced from criminal channels, covering addresses and
sites that public feeds do not carry.

### Segment 1: Blockchain analytics and compliance

They buy attribution data and they have budget for it. Scam-wallet coverage from criminal channels
is additive to on-chain analysis rather than competitive with it.

| Organisation | Angle |
|---|---|
| TRM Labs | Buys/ingests external attribution data; strong partner motion |
| Chainalysis | Largest; slowest procurement; verify current data-partner programme |
| Elliptic | Mid-size, data-partnership friendly |
| Merkle Science | Smaller, faster to a decision |

**Roles:** Head of Data Partnerships; Director of Threat Intelligence; VP Product (Investigations).

### Segment 2: Wallets and consumer crypto surfaces

The distribution play. One integration reaches an entire user base, which is worth more than any
number of direct sales.

| Organisation | Angle |
|---|---|
| MetaMask / Consensys | **Snap already published**; warmest existing thread |
| Phantom | Solana-first, and 9.1% of our corpus is SOL wallets |
| Trust Wallet | Large consumer base, security-feature hungry |
| Rabby | Security-positioned wallet, small team, fast |
| Blockaid / Web3 Antivirus | Competitors OR data customers; treat as partnership probes |

### Segment 3: Exchanges and embedded-wallet providers

The Kraken/Privy post is the door-opener here. It is a first-person account of a real notice, not a
pitch, which is exactly what makes it sendable.

| Organisation | Angle |
|---|---|
| Privy | Named in the post; approach only after it publishes, and only as a courtesy heads-up |
| Kraken | Post references their notice; security team may engage on the fourth-party theme |
| Dynamic / Turnkey / Magic | Embedded-wallet providers with the same fourth-party exposure |

**Sequencing: Segment 2 first.** The MetaMask Snap is already published, which makes it the only
thread here with prior contact and a working artefact.

---

## Segment D: MSP/MSSP channel (existing motion)

Already the stated constraint. The victim-side signal changes the pitch from "another feed" (which
an MSP cannot resell) to "a report your client's board will read" (which they can bill for).
**Reframe rather than re-prospect.**

---

## How to find the actual contacts

Contact names are deliberately not listed here, because a stale or wrong name is worse than none.
For each target:

1. LinkedIn search the role titles above, filtered to the company.
2. Prefer someone who has spoken publicly about threat-intel sourcing (conference talk, podcast,
   blog). Reference the specific thing they said.
3. For partnership motions, the partnerships page usually lists a real intake address. Use it.
4. Log every contact below as you make it, so this file becomes the record.

## Contact log

| Date | Org | Person / role | Channel | Sent | Response |
|---|---|---|---|---|---|
| | | | | | |

---

## Sequencing recommendation

**Crypto Segment 2 first** (wallets), because the MetaMask Snap is already published and it is the
only thread with prior contact. **Crypto Segment 1 second** (blockchain analytics), because they buy
data and our corpus is the right shape for them. **Crypto Segment 3** rides the Kraken/Privy post.

The parked segments unblock only when the corpus carries victim-shaped domains and emails. That is a
collection problem, not a sales problem: it needs the marketplace-listing extractor producing real
rows, and it needs channels that post breach dumps rather than CTI news. Revisit when
`relayshield_marketplace_listings` holds real listings with real victim domains.
