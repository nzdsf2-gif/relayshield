# Intel channel recommendations — OSINT sweep

**Sweep 001 · 2026-08-21**

Runs automatically on the **1st and 15th of each month at 09:00 UTC** (Routine
`trig_012eVHz4xEby12AJAXQRG8N2`, first fire 2026-09-01). Each run appends a new numbered section
here, pushes to `claude/daily-todo-summary-7zpsvv`, and notifies by push and email. It does not open
a pull request and it does not rewrite earlier sweeps.

Standing replacement for subjective channel picks. Each sweep produces candidates with a published
source and a rationale, so the decision to activate rests on evidence rather than a guess.

---

## Read this before acting on anything below

**No handle here has been verified as live.** This sandbox has no Telegram access and no AWS
credentials. Everything below is sourced from published threat-intelligence reporting and is a
**lead**, in the same sense as `pending_review` — it becomes a monitored channel only after
`tools/triage_channels.py` or the OSINT-2 classifier has looked at it.

**Named channels rot fast, and that is the central finding of this sweep.** Reporting is explicit
that these operations survive takedowns by *rotating channel names, running mirrors, and keeping
backup groups*, and that many have moved to request-to-join gating specifically to defeat automated
crawling. A hand-curated list of handles is therefore worth little a month from now.

**So the primary deliverable of this sweep is keywords, not handles.** A keyword feeds
`relayshield_intel_discovery.py`, which finds whatever the current name is, queues it as
`pending_review`, and hands it to the classifier. That loop keeps working after the handle changes.
Handles are the secondary output.

---

## A. Keyword additions — shipped this sweep

Added to `SEARCH_KEYWORDS` in `relayshield_intel_discovery.py`. Malware-family and platform brand
names, following the 2026-07-24 finding that a bio containing "StealC" is a far stronger signal than
one containing "stealer logs".

| Keyword | Category | Why it earns a slot |
|---|---|---|
| `omega cloud` | `infostealer` | Named in current reporting as a Telegram-based stealer-log distribution platform. Platform brand, so it survives channel renames |
| `moon cloud` | `infostealer` | Named as a high-traffic channel circulating infostealer credentials |
| `bidencash` | `card_shop` | Runs automated bots surfacing stolen card data in real time — and it exercises the `card_shop` category that until today nothing could produce |
| `darcula` | `phaas` | The dominant smishing PhaaS platform; reporting attributes ~80% of US phishing texts to Darcula / Magic Cat |
| `magic cat` | `phaas` | The same operation's other tracked name. Both are needed — reporting uses them interchangeably |
| `otp bot` | `sim_swap` | OTP-interception services operate as Telegram bots or run customer support on a Telegram channel. Directly upstream of the SIM-swap product |
| `sim swap service` | `sim_swap` | The literal phrasing these listings use, distinct from the existing `sim swap` |

**Rationale for weighting toward `phaas`, `sim_swap` and `card_shop`:** those three are the thinnest
categories in the corpus. The seeded channel list is 13 `general`, 7 `infostealer`, 4 `crypto`,
3 `credential_dump`, 2 `ransomware` — and **zero** of the other three. Adding another infostealer
channel improves a category that is already the strongest; adding a PhaaS channel creates coverage
that does not exist.

## B. Named entity leads — verification required

Given as entity names, not `@handles`. **I will not invent a handle**, and reporting names the
operations without consistently publishing current channel identifiers. Feed the name to the
discovery crawl, or search it directly in Telegram.

| Entity | Category | Basis | Confidence |
|---|---|---|---|
| **Omega Cloud** | `infostealer` | Telegram platform distributing stealer logs from infostealer infections | Medium — named in reporting, current handle unknown |
| **Moon Cloud** | `infostealer` | High-traffic channel circulating infostealer-derived credentials | Medium — same caveat |
| **BidenCash CVV** | `card_shop` | Marketing arm for a larger carding marketplace, automated card-data bots | Medium — long-lived brand, channel identifier unverified |
| **Darcula / Magic Cat** | `phaas` | Chinese-language PhaaS, 20,000+ counterfeit domains, 200+ templates | Medium — group exists and is documented; Chinese-language, so expect our extractors to underperform |

⚠️ **Darcula operates in Chinese.** `extract_iocs()` is regex-driven over Latin-script patterns, so
URLs, wallets and hashes will extract normally but the surrounding context will not classify well.
Worth monitoring for the infrastructure; do not expect the narrative signal.

## C. Structural findings worth more than any single channel

**1. The public-channel surface is shrinking, and our collection model assumes it isn't.**
Reporting describes a deliberate migration to request-to-join gating, precisely to defeat automated
crawling. The 27 unreachable channels in the current digest are consistent with that, not with
random attrition. **This should inform how the 122-active number is read**: the collectible
population is contracting, so flat collection over time is a real decline. Worth a metric.

**2. Vidar and LummaC2 reportedly account for 60%+ of documented credential theft in 2026.** Both
are already in `SEARCH_KEYWORDS`. That is a coverage confirmation, not a gap — worth recording so it
is not re-researched next sweep.

**3. Forum-to-Telegram migration continues** post-BreachForums and LeakBase enforcement. This
supports continued investment in Telegram collection over forum scraping, which is the more
expensive path.

---

---

# Sweep 001b — 2026-08-22

Follow-up to the "recommend channels worth adding" question. **The honest headline: I can recommend
what to hunt for, and I have shipped that. I cannot hand over verified handles from this sandbox,
and the automated answer is a source, not a list.**

## A. Shipped — the 2026 ransomware cohort was missing entirely

The existing ransomware keywords are the **2024–2025 cohort**: LockBit, ALPHV/BlackCat, Cl0p, Play,
RansomHub, Akira. Current reporting names the most active groups of 2026 as **Qilin, TheGentlemen,
DragonForce and Akira** — so three of the top four could not be discovered at all, and two of them
(Qilin, DragonForce) post-date every keyword in the file.

Added to `SEARCH_KEYWORDS`: `qilin`, `dragonforce`, `thegentlemen`, `babuk`.

**This is the highest-value item in either sweep.** Ransomware is also one of the thinnest categories
in the seeded list — 2 channels against 7 infostealer — so this creates coverage rather than depth.
**The general lesson: a keyword list decays as the leaderboard turns over, and nothing was checking.
That is what this sweep is for.**

## B. The automation answer: wire a public aggregator, do not curate by hand

Asking me for handles produces a list that is stale in weeks — that was sweep 001's central finding
and it has not changed. **The automated answer is to add a source that publishes them continuously.**

**[RansomLook](https://www.ransomlook.io)** is the strongest candidate: a public, free aggregator
that tracks ransomware groups **including their Telegram channels**, with an API surface
(`/api/groups`, and an apparent Telegram listing). Feeding it into `relayshield_intel_discovery.py`
would give a self-updating supply of ransomware-group channels with no hand-curation and no vendor.

⚠️ **`ransomlook.io` is blocked by this sandbox's egress proxy** (403 on CONNECT), so I could not
confirm the endpoint paths, the response shape, or whether the Telegram listing is exposed via API
at all. **Verify from an unblocked machine before scoping**, exactly as the BB-3 lesson requires:

    curl -sS "https://www.ransomlook.io/api/groups" | head -c 2000

If it holds up, this is a small, high-yield addition — a `_ingest_ransomlook_channels()` alongside
the existing keyword search, writing candidates as `pending_review` for the classifier. Same pattern
as `_queue_discovered_channels()`, different source.

## C. Named leads, unchanged and still unverified

Sweep 001's four entities stand: **Omega Cloud** and **Moon Cloud** (infostealer), **BidenCash CVV**
(card_shop), **Darcula / Magic Cat** (phaas). Published reporting names the operations but does not
publish current channel identifiers.

**Two sources that do publish channel lists are both egress-blocked here** — `socradar.io` and
`breachsense.com`. Both are reachable from an ordinary browser and both maintain running lists of
infostealer and threat-actor Telegram channels. **That is the fastest manual path to verified
handles**, and it is a ten-minute job from the Mac, not a research problem.

## D. One verified operator handle — different destination

**`@bjorkanesiaaaa`** — published as the current administrator of **Babuk**.

**This belongs in `relayshield_operator_identities`, not the channel list.** It is a person, not a
room; there is nothing to monitor. It is worth recording because it is exactly the indicator class
the operator-identity work was built for, and the class no public feed publishes — infrastructure is
published, people are not. Add it as a seed once the table exists.

## Scoreboard

| Sweep | Date | Keywords added | Entity leads | Confirmed active later |
|---|---|---|---|---|
| 001 | 2026-08-21 | 7 | 4 | *pending — needs a discovery + classifier run* |
| 001b | 2026-08-22 | 4 | 0 (1 operator handle) | *pending* |

---

## Method, so each sweep is comparable

1. Search current published threat-intelligence reporting for named Telegram operations, per
   category, weighted toward the thinnest categories in the corpus.
2. Discard anything without a published source. **Never invent a handle.**
3. Convert durable brands (malware families, platform names) into `SEARCH_KEYWORDS` entries —
   these outlive channel renames.
4. List named entities separately as verification-required leads.
5. Record structural findings about the collection surface itself.
6. Re-check whether the previous sweep's keywords produced anything.

## Closing the loop

**Closing the loop matters more than the sweep.** A keyword that has produced nothing after two
discovery runs should be removed, not left to accumulate. Check
`relayshield_intel_channels` for rows whose `keyword_match` is one of this sweep's additions before
the next sweep, and record the result above.
