# Intel channel recommendations — OSINT sweep

> **STATUS, 2026-11-16 (added when this file was first merged to main). Read before the paragraph below.**
> This file lived only on the unmerged branch `claude/daily-todo-summary-7zpsvv` from 2026-08-22 until now. The
> paragraph below describes the original set-up (push to that branch, no pull request) and is out of date: each
> sweep now starts a fresh branch from latest `main` and opens a pull request for Andrew to review and merge.
> The sweep 001, 001b and 002 keywords were also missing from `main` and were ported in the same pull request.
> The category-drift test and `INTEL_CATEGORIES`, mentioned in Sweep 002, exist only on that branch and are NOT on
> main; the category list on main is `VALID_CATEGORIES` in `relayshield_intel_classifier.py`. Sweep 003 is at the
> end of this file. The next sweep is **004**. Earlier sweeps below are unchanged.

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

---

# Sweep 002 — 2026-08-21, founder-supplied (SOCRadar)

Named channels from SOCRadar's stealer-log and top-groups tables. **This is the sweep working as
intended**: a source I cannot reach was read in a browser, and the names came back.

## Shipped as keywords

Added as **keywords, not channel rows**, because SOCRadar publishes display names rather than
`@handles` and the rule against inventing one holds. A brand name also survives the renames these
operations rely on.

| Keyword | Category | Why |
|---|---|---|
| `moon cloud` | infostealer | Curates and republishes other channels' logs — an aggregator, so it reaches further than its own sources |
| `daisy cloud` | infostealer | "Fresh one-hand logs", mostly RedLine, banking/crypto/enterprise creds |
| `log sync` | infostealer | Free and premium tiers, community uploads |
| `observer cloud` | credential_dump | Long-standing combo-list distribution |
| `alien txtbase` | credential_dump | The large infostealer-derived dump. Inflated, but contains valid credentials |
| `data leak monitoring` | credential_dump | SOCRadar rates activity "very high" |
| `mailpass` | credential_dump | EMP/mailpass/sqli chat |
| `bidencash shop` | card_shop | Refines the `bidencash` keyword from sweep 001 |
| `cti now` | general | News tracking. Low direct value, useful as a cross-promotion seed |
| `noname057` | **hacktivist** | DDoS / geopolitical |
| `rippersec` | **hacktivist** | DDoS |
| `dark storm team` | **hacktivist** | DDoS / hacking services |
| `z-pentest` | **hacktivist** | OT intrusion — the most operationally serious of the four |

**Not added: bare `alien`.** It is an ordinary English word and would match hundreds of unrelated
channels. That is the generic-phrase trap this list has been burned by once already; `alien txtbase`
is the operation's actual name.

## New category: `hacktivist`

Four of SOCRadar's ten most active groups are hacktivist crews, and **none of the existing eight
categories fit** — they run DDoS and OT-intrusion campaigns rather than selling credentials. Forcing
them into `general` would have made the corpus's most active segment invisible to any
category-aware query.

Added to `INTEL_CATEGORIES` and the classifier vocabulary, at **MEDIUM, not HIGH**, deliberately:
for an identity-protection customer a hacktivist mention is context, not an account compromise. The
*collection* value is high — they publish target lists and leaked data early — but per-user alert
value is not, and the severity has to say which. `test_intel_category_drift.py` passes.

## What the founder should notice about this sweep

**Two of the five stealer-log channels supplied were already covered.** `omega cloud` and
`bidencash` went in with sweep 001 from open reporting. That is a useful calibration: the automated
sweep and a manual browse of SOCRadar overlap meaningfully, so the manual pass is worth doing
fortnightly rather than weekly.

**`observer cloud` was mis-categorised on first pass.** Reporting describes it as log aggregation,
which reads as infostealer, but SOCRadar's own threat-type column says *credential leaks / combo
lists*. Combo lists are a distinct product from raw stealer logs, so it is `credential_dump`. Worth
recording because the same ambiguity will recur for every "cloud"-branded channel.

## Scoreboard

| Sweep | Date | Keywords added | Entity leads | Confirmed active later |
|---|---|---|---|---|
| 001 | 2026-08-21 | 7 | 4 | *pending — needs a discovery + classifier run* |
| 001b | 2026-08-22 | 4 | 0 (1 operator handle) | *pending* |
| 002 | 2026-08-21 | 13 | 0 (all became keywords) | *pending* |

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

---

# Sweep 003 — keywords written 2026-08-30, rebuilt 2026-09-01 (recorded here 2026-11-16)

**What this is.** The original sweep-003 commit (`a08104f`) was stranded in a session that could not push. Commit
`0e0334b` rebuilt the keywords from the surviving record and they are live in `SEARCH_KEYWORDS` in
`relayshield_intel_discovery.py`, under the comment "OSINT sweep 003, 2026-08-30 (rebuilt)". There was never a
section for it in this file, which is why the 2026-11-15 scheduled run reported "last recorded sweep is 002".

**Shipped as keywords: 16.** The original commit message said 17. The 17th is not recoverable and is deliberately
not invented.

| Category | Keywords |
|---|---|
| sim_swap | astro otp, sms buster, smsranger |
| phaas | tycoon 2fa, lucid panel, lighthouse phishing, evilproxy, sneaky 2fa, xinxin group |
| card_shop | brians club, b1acks stash |
| hacktivist | serverkillers, cyb3rdrag0nz, cyber fattah team, handala hack team, conquerors electronic army |

**Why brand names.** sim_swap, phaas, card_shop and hacktivist still held zero channels after sweeps 001 to 002,
whose keywords were generic. Operators advertise the product, not the category. Sources named in the code comment:
Intel 471, Proofpoint, Microsoft, Netcraft, DomainTools, Bitsight.

**Not verified.** Whether any of these produced channels. That needs AWS (`relayshield_intel_channels`), which
scheduled sessions do not have.

## Scoreboard

| Sweep | Date | Keywords | Channels produced | Result |
|---|---|---|---|---|
| 001 | 2026-08-21 | 7 (+3 card shop) | not measured | *pending, needs a founder query* |
| 001b | 2026-08-22 | 4 | not measured | *pending* |
| 002 | 2026-08-21 | 13 | not measured | *pending* |
| 003 | 2026-08-30 | 16 | not measured | *pending* |

## Gap found when this file was merged

Six fortnightly runs (2026-09-01 to 2026-11-15) produced no record. The scheduled task had no repository attached,
so every push was refused with a 403. The runs were not at fault; the task's configuration was. Repository attached
on 2026-11-16.

## Not ported, and why

Present on the old branch only, deliberately left out of this pull request because each changes production Lambda
behaviour and needs its own review: the RansomLook ingest (`ingest_ransomlook_channels()` and its hooks in
`relayshield_intel_discovery.py`), the category-drift test, and the monitor and classifier changes that add
`hacktivist` to the classifier vocabulary. With this pull request, 33 of 112 keywords carry a category that is not in
`VALID_CATEGORIES` (24 of 86 before it; `android_banking`, `hacktivist`, `card_shop`). The alert formatter in
`relayshield_intel_monitor.py` falls back to the raw category name and a generic severity for any category it has no
label for (`CATEGORY_LABELS.get(category, category)`), so this is cosmetic there. Not traced: whether the classifier's
`VALID_CATEGORIES` check changes anything for a channel found by one of these keywords.
