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
