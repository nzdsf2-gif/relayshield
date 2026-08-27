# SOCRadar gap-closure roadmap

*Written 2026-08-23, out of the benchmark exercise in `socradar_competitive_benchmark.md`.*

The benchmark catalogued where we lose. This document is the plan to stop losing there. It is
ordered by leverage, not by dimension, because the cheapest wins are not evenly distributed.

## The strategic call, stated once

**We are not going to beat SOCRadar on breadth, and chasing it would make the product worse.**
Their crawl surface spans forums, marketplaces and paste sites we have no access to, built over
years. Ingesting more public feeds to close the gap inflates the headline number and dilutes the
only thing that is ours — which is the mistake that killed the Segment 1 outreach.

So the plan wins on four axes where dominance is actually reachable:

1. **Exclusivity** — the share of our corpus that appears in no feed the buyer already has.
2. **Freshness** — provable lead time, measured, not asserted.
3. **Provenance** — every indicator carries where it came from and how confident we are. Nobody in
   this market does this well, and it is the thing a technical buyer actually audits.
4. **Integration reach** — currently our weakest column, and unlike breadth it is *purely* a matter
   of shipping work we have already started.

Breadth gets a containment plan, not a race. Sections C and E.

---

## PHASE 0 — Measure, before anything else

Nothing in this roadmap can be prioritised, and no claim in the benchmark can be published, until
we know the current numbers. This is a single command and it gates everything.

| # | ToDo | Effort | Blocks |
|---|---|---|---|
| **0.1** | Run `tools/exclusive_share_by_category.py --markdown` and paste the table into the benchmark | 10 min | Every `MEASURE` in the benchmark |
| **0.2** | Record the output as the **baseline**, dated, in the repo | 10 min | All trend tracking below |
| **0.3** | Add per-category exclusive share to `relayshield_weekly_metrics.py` so it is tracked over time, not measured once | 2h | 0.1 |

```
cd "$HOME/Side SaaS Hustle"
git pull origin main
AWS_PROFILE=relayshield python3 tools/exclusive_share_by_category.py --markdown
```

**0.3 is the one that matters long term.** A one-off measurement is a benchmark input. A tracked
weekly series is a KPI, and it is the number every decision below should be judged against.

---

## PHASE A — Corpus depth and quality (highest leverage)

This is the moat. Everything here raises exclusive share, freshness or provenance.

| # | ToDo | Why it wins | Effort | Depends on |
|---|---|---|---|---|
| **A1** | **Triage the 75 `pending_review` channels** — `tools/triage_channels.py --pending`, then `--activate … --apply` | The cheapest volume available, and it is all channel-collected, so it lands entirely in the exclusive column | 2–3h | AWS |
| **A2** | **Recover or replace the 27 unreachable channels** (95 of 122 active) | 22% of our collection surface is dead. `consecutive_failures` / `last_error` now record why — read them before replacing | 3h | One patched monitor run |
| **A3** | **Ship pivot enrichment to production** — wire `relayshield_intel_pivot.py` into the wallet and domain monitors | Turns one collected indicator into a cluster, all of it exclusive by derivation. Confidence decay is already enforced | 1–2 days | Module merged ✅ |
| **A4** | **Turn on the `/scan` ledger** across Telegram, WhatsApp, Discord | Produces the **measured lead-time claim** — the single strongest thing we will have. Structurally unavailable to SOCRadar | 1 day | Module merged ✅; ledger table |
| **A5** | **Create `relayshield_ransomware_victims` + grant the intel role `PutItem`** | Victims are being dropped on every run right now. Also unblocks the TI demo tab | 30 min | AWS |
| **A6** | **First-seen date on every indicator, backfilled where possible** | "A wallet address with no first-seen and no context is volume, not quality." First-seen is also what makes A4's lead-time claim auditable per indicator | 1 day | — |
| **A7** | **Normalise the `malware:` label namespace at source** | Case inconsistency currently hides two thirds of matches (`clearfake`: 196 vs 608). This is a *quality* defect visible to every customer running a hunting query | 1 day | — |
| **A8** | **Grow `tg_handle` deliberately** — it is the highest-uniqueness category we have, because feeds publish infrastructure, not people | Likely our best exclusive-share number. Needs a filtering pass first: `_RE_TG_CHANNEL` matches any `@mention`, so it is a lead list, not a verdict | 2 days | A1 |

**A3, A4 and A5 are the priority.** A3 and A4 are already built and merged; they are wiring jobs,
not builds. A5 is thirty minutes and unblocks two other things.

---

## PHASE B — Provenance as a product feature

Nobody in this market ships this, and it converts our smaller corpus from a weakness into a
credibility argument. This is the differentiation play, not a hygiene task.

| # | ToDo | Why it wins | Effort |
|---|---|---|---|
| **B1** | **Expose `confidence` and `derivation` on every API response** and in the STIX/TAXII output | Lets a buyer filter to `confirmed` + `observed` and ignore derived. Turns "we have fewer" into "ours are typed" | 2 days |
| **B2** | **Publish the exclusivity methodology** — how `measured_exclusive_share` is computed, with the classification rules | A competitor quoting a corpus size cannot answer "which of these are yours?". We can, in public | 1 day |
| **B3** | **Per-indicator source attribution in the sample export** (already pseudonymised by `channel_labels`) | Already built — surface it | 0.5 day |
| **B4** | **A public "what we do not cover" page** | Counter-intuitive, and it is the single most trust-building thing a small vendor can do against a big one. It also pre-empts the breadth objection instead of losing to it in the room | 0.5 day |

---

## PHASE C — Collection surface expansion

Where the breadth gap actually gets narrowed, without pretending we can crawl the dark web.

| # | ToDo | Assessment | Effort |
|---|---|---|---|
| **C1** | **Cooperating-admin access to closed Discord rooms**, as a by-product of gaming outreach | Genuinely new and genuinely exclusive. Keep it consensual and documented — a partner sharing their own server's abuse reports, never covert collection. That distinction is the whole difference between an asset and a liability | Ongoing |
| **C2** | **Paste sites** — cheap, public, we do not collect them today | Low exclusivity (SOCRadar covers them) but high volume and near-zero cost. Do it for coverage parity, do not claim it as a differentiator | 2 days |
| **C3** | **Expand ransomware leak-site group coverage** in `relayshield_intel_ransomware` | We already have the pipeline; more groups is incremental work with a direct demo payoff | 2 days |
| **C4** | **Evaluate licensing forum/marketplace coverage rather than building it** | Building it is a multi-year programme with legal exposure. Licensing closes a checkbox gap at known cost. **Recommend evaluate-and-decide, not build** | 1 day to scope |
| **C5** | **Do NOT backfill history by ingesting more public feeds** | Explicitly out of scope. It raises the headline and lowers exclusive share — the exact trade this roadmap exists to refuse | — |

---

## PHASE D — Integrations (our weakest column, and the most winnable)

Everything here is shipping work, not research. This is where the benchmark is bluntest: SOCRadar
leads every classical SOC integration and both of our entries are open PRs.

| # | ToDo | Status | Effort |
|---|---|---|---|
| **D1** | **Land Microsoft Sentinel PR #14924** | Both reviewer asks answered, awaiting review. Chase it | Chase |
| **D2** | **Decide on the second Sentinel PR** for the same defect in `TI Map Domain entity to Cloud App Events` | Open question — ask whether Microsoft wants it | 1 day |
| **D3** | ~~XSOAR PR #45206 / Tech Alliance~~ | ✅ **DONE weeks ago.** `NEXT_SESSION_2026-08-20.md` still lists it as carried-forward and blocked on joint customers; that file is stale | — |
| **D4** | **Ship an Elastic integration for our TAXII feed** | **The highest-leverage item in this phase.** SOCRadar's TAXII server ships as a first-class Elastic integration — that is distribution we have no equivalent to, and ours is a config-and-submit job because the TAXII endpoint already exists and is conformant | 3–5 days |
| **D5** | **Splunk TA** | Named in their SIEM list, absent from ours | 1 week |
| **D6** | **Complete MISP server compatibility** (currently partial) | Their MISP server is a named integration; ours is partial | 3 days |
| **D7** | **Keep the MCP / agent-native lead** | The one column we lead. Small market today, but it is ours and costs nothing to hold | Maintain |

**D4 first.** It is the only item in this phase that adds a *distribution channel* rather than a
checkbox, and the work is mostly packaging something that already works.

---

## PHASE E — Packaging

The benchmark's finding here was that we win on **commitment**, not price. Protect that and close
the one real gap.

| # | ToDo | Rationale | Effort |
|---|---|---|---|
| **E1** | **Match their free on-ramp** — a genuine free tier with a meaningful window, not a trial | They offer a year of freemium CTI access. Ours is per-endpoint and harder to describe. Their on-ramp is better than ours and that is a fixable | 2 days |
| **E2** | **Publish a per-category exclusivity page** as a trust artefact | Turns Phase 0's measurement into a sales asset | 1 day |
| **E3** | **Never lead on price** | Anchoring on cheap makes an enterprise buyer read thin. Lead on no-commitment: a team wanting to check 400 domains once cannot do that with SOCRadar at any tier. Different purchase, not a cheaper one | Discipline |
| **E4** | **Confirm SOCRadar's actual pricing** against their own page | Benchmark figures are third-party aggregators, marked indicative | 30 min |

---

## Recommended sequence

**This week**
0.1, 0.2 (measure — gates everything) → A5 (30 min, unblocks the demo and A4) → A1 (cheapest volume) → D1 chase

**Next two weeks**
A3, A4 (wire up what is already merged) → A7 (label normalisation) → D4 (Elastic integration)

**The month after**
A2, A6, A8 → B1, B2, B4 → C2, C3 → E1

**Decide, do not drift**
C4 (licence vs build forums) needs a decision from you rather than work from me.

## How we will know it worked

Not "corpus size". These:

| Metric | Source | Target |
|---|---|---|
| `measured_exclusive_share` per category, weekly | 0.3 | Rising in `tg_handle`, `wallet_*`, `url` |
| Median lead time on `/scan` submissions, with sample size | A4 | Any defensible number at n > 100 |
| Categories above the 100-indicator defensibility floor | 0.1 | All the ones we quote |
| Shipped SIEM/SOAR integrations | D1, D2, D4–D6 | 1 shipped (XSOAR) → 5 |
| Indicators carrying confidence + derivation | B1 | 100% |

The first two are the ones that decide whether the benchmark can be published aimed at their
customers rather than at ourselves.

---

# ToDo added 2026-08-26 — scope the Solana agentic-payments integration angle

## Why this is on the list

Two things landed on 2026-08-18, the same day, and together they describe a market that exists now
rather than one being announced:

- **Rain launched the Agentic Payments Alliance**, 25+ organisations, founding members including
  Visa, Mastercard, Fiserv, Circle, Solana and Remitly. Its stated purpose is standardising
  **authorisation and risk management for agentic commerce**. That is our product category, named by
  a coalition that includes the card networks.
- **Arthur Hayes took the CEO role at Flop Labs** (Flop Network, FLOP token, proof-of-useful-
  inference). Airdrop planned Q4 2026, genesis block targeted Q1 2027.

Separately, roughly **65% of agentic AI payments already run on Solana**, with Solana Pay as the
default settlement layer for several agent marketplaces.

## The call

**Flop is not an integration target yet and should not be scoped as one.** The token ships a full
quarter before the chain it powers exists, so there is no settlement, no counterparties and no
transaction flow to screen. Revisit near genesis.

**The Alliance and Solana Pay agent marketplaces are the real target**, because payments are
settling there this quarter.

## What we already have pointed at this

Not a new product, a positioning exercise on shipped capability:

- `check_wallet_risk` and `wallet-screen-batch`, the counterparty screening endpoints
- The x402 counterparty work and its published post, whose thesis is precisely that nothing in the
  agent payment flow asks who is being paid
- Address-poisoning detection, which is an agent-payment failure mode as much as a human one

## Scope this ToDo as

1. Read the Alliance's published scope and membership terms. Determine whether membership is open,
   what it costs, and whether "risk management" there means fraud scoring, authorisation policy, or
   both. Do not assume a fit before reading it.
2. Identify which Solana Pay agent marketplaces expose a pre-payment hook a counterparty check could
   sit in. An integration needs a place in the flow, not just a shared topic.
3. Only then decide between: join the Alliance, integrate with one marketplace as a reference, or
   publish into the category and let inbound find us. All three are cheaper than building for a
   chain that does not exist yet.

**Measurement rule applies.** Any claim we make in this category about our own coverage of agent or
wallet risk must come from `exclusive_share_by_category.py`, not from the 511K headline, and not
from the number of endpoints we happen to expose.

---

# 2026-08-27 — A6, A7, A8 scoped; A7 built

## A7, DONE (deployed pending, see the caveat)

`relayshield_intel_labels.normalise_malware()` is applied at every write and the
malware-index query. `tools/backfill_malware_labels.py` collapses existing rows, read-only until
`--apply`. Full reasoning in the commit; the two things to carry forward:

- **KEV was worse than case-inconsistent.** It wrote `vendorProject + " " + product` into `malware`,
  so `Microsoft Windows` was indexed as a malware family. Moved to `affected_product`; `malware` now
  unset for KEV rows. Reversible if any surface depended on it.
- **The feed and KEV halves are inert.** Neither `relayshield_intel_feed.py` nor
  `relayshield_intel_kev.py` is in `deploy_lambdas.yml`. They are now in `lambda_drift_check.yml`
  only. Check drift, recover if drifted, then add them to the deployer.

## A6 — first-seen on every indicator

**The obstacle, stated first.** `relayshield_intel_iocs` is keyed `(ioc_value, seen_ts)`, so every
sighting is its own row and `seen_ts` is that sighting's ingest time. There is no per-indicator
record, which means "first seen" today is `min(seen_ts)` over a query, and `_store_iocs` uses
`put_item`, which cannot express "write this only if absent".

**Rejected: make `_store_iocs` read-then-write.** A read before every IOC write, on a path that
handles hundreds of IOCs per message, doubles the request count and adds a race between concurrent
runs. The cost is real and the correctness is worse.

**Proposed: a separate first-seen projection, one row per indicator.**

    relayshield_intel_first_seen
      PK  ioc_value (S)
      first_seen (S)    ISO8601
      first_channel (S) where we first saw it
      first_category (S)

Written with `update_item` and `attribute_not_exists(ioc_value)` on the condition, so the first
writer wins and every subsequent one is a no-op that costs one conditional write. No read, no race.

**Backfill** is a single pass over the existing corpus taking `min(seen_ts)` per `ioc_value`, which
is exactly the value a live query would compute today, so the backfilled rows are correct rather
than approximate. Runs on the Mac, one-off.

**Why it enhances A4:** A4's lead-time claim is currently "we saw this N days before the public
feed", computed per query. With a first-seen row it becomes a stored, auditable per-indicator fact
that survives TTL expiry of individual sightings. **That is also the risk:** sightings carry a TTL
and first-seen must not, or the claim erases itself. Give this table no TTL, deliberately.

**Estimate:** half a day for the writer, half a day for the backfill, plus the table and an IAM
statement. Both need AWS, so both run from the Mac or a workflow.

## A8 — grow `tg_handle` deliberately

**Do the filtering pass first, and the evidence for that is now on the table.** A4's
`relayshield_operator_identities` has 7 rows after two days and every one is at `sightings=1`.
Several are English words (`catching`, `normanonrock`) caught because `_RE_TG_CHANNEL` matches any
`@mention`. Growing collection before filtering multiplies the noise rather than the signal.

**The measurement that decides this, and it is already built.** `tools/check_operator_identities.py`
now reports handles seen more than once, in 2+ channels, and in 2+ categories. Cross-channel
handles are the exclusive asset: a handle in a ransomware room one month and a phaas room the next
is a correlation no single-sighting feed can produce. A count of rows is not.

**Sequence:**

1. Watch the cross-channel number for two weeks. If it stays at 0 while channels are producing, the
   problem is extraction, not volume.
2. Filter. Options, cheapest first: drop mentions matching a common-word list; require the mention to
   appear near contact-intent language (`dm`, `contact`, `@admin`, `escrow`); require a second
   sighting before the row is written at all. The third is the strongest and the least destructive,
   because it filters on repetition rather than on a guess about what a handle looks like.
3. Only then grow collection, via the `otp_vouches` and marketplace categories where operators
   actually advertise.

**Do not quote a `tg_handle` exclusive-share number until the category clears 100 collected
indicators and `exclusive_share_by_category.py` has been run on it.** The standing rule applies with
extra force here, because this is the number most likely to be quoted at a competitor.

**Estimate:** 2 days, unchanged, but sequenced after a two-week measurement window rather than
started now.

---

# 2026-08-27 — Solana agentic payments: scoped

Follows the ToDo filed earlier. This is the scope, not a build.

## What is actually true today, and what is not

**True and current:** roughly 65% of agentic AI payments settle on Solana, with Solana Pay as the
default settlement layer for several agent marketplaces. The Agentic Payments Alliance launched
2026-08-18 with 25+ members including Visa, Mastercard, Fiserv, Circle, Solana and Remitly, formed
to standardise **authorisation and risk management for agentic commerce**. That last phrase is our
product category, named by a coalition that includes the card networks.

**Not yet true:** Flop Network does not exist. FLOP's airdrop is planned Q4 2026 and genesis Q1
2027, so the token ships a quarter before the chain it powers. There is no settlement, no
counterparties and no flow to screen. **Not a target this quarter.** Revisit near genesis.

## The asset we already have

Nothing new needs building to evaluate this. `check_wallet_risk`, `wallet-screen-batch`, the x402
counterparty work and its published post (whose thesis is exactly that nothing in the agent payment
flow asks who is being paid), and address-poisoning detection, which is an agent-payment failure
mode as much as a human one.

## Phase 0 — answer three questions before writing any code (1 to 2 days)

1. **Read the Alliance's published scope and membership terms.** Is membership open, what does it
   cost, and does "risk management" there mean fraud scoring, authorisation policy, or both? Do not
   assume a fit before reading it. A coalition founded by card networks may define risk management
   as chargeback and dispute mechanics, which is not what we do.
2. **Find a marketplace with a pre-payment hook.** An integration needs a place in the flow, not a
   shared topic. Concretely: does any Solana Pay agent marketplace expose a callback, webhook or
   policy check between "agent decides to pay" and "transaction is signed"? If none does, there is
   no integration to build regardless of how good the fit sounds.
3. **Establish what we can honestly claim about Solana coverage.** We screen addresses. Run
   `exclusive_share_by_category.py` on the wallet/address categories and find out what our
   Solana-specific exclusive share actually is. **If it is under 100 collected indicators the
   category is not defensible and must not be quoted**, which would make "join the Alliance" the
   wrong move and "publish into the category" the right one.

## Phase 1 — pick exactly one of three, based on Phase 0 (effort varies)

- **Join the Alliance.** Cheapest in engineering, most expensive in credibility risk: a 25+ member
  coalition with Visa in it will ask what we bring, and the answer must survive Q3 above.
- **Integrate with one marketplace as a reference.** Highest proof value. Requires Q2 to have found
  a real hook. One named integration is worth more than membership in a list.
- **Publish into the category.** Lowest cost, no dependency on anyone answering an email, and it is
  the motion we are demonstrably good at. The x402 post already argued the thesis; a follow-up
  aimed at agent payments on Solana writes itself and can carry a measurement.

**Recommendation if Phase 0 is inconclusive:** publish. It is the only one of the three that cannot
be blocked by someone else's roadmap, and it generates the inbound that makes the other two easier.

## Measurement rule

Any claim in this category about our coverage of agent or wallet risk comes from
`exclusive_share_by_category.py`, per category, never from a corpus total and never from the number
of endpoints we expose. This is a market where the other participants can check.
