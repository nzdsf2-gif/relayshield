# SPEC — Quarantined community reports ("Report this")

Branch: `feature/quarantined-community-reports`. No merge, no deploy, no AWS work.

## Goal

Let Telegram / WhatsApp bot users report a missed scam right after a scan
verdict, without ever letting user input touch the curated threat-intel
corpus directly.

## Non-goals

- No automatic ingestion into `relayshield_intel_iocs` — ever.
- No "safe" verdicts, no verdict changes driven by report counts.
- No new paid endpoints, no Stripe, no AWS provisioning in this change.

## User flow

**Telegram** (`relayshield_telegram_webhook.py`)
- After every `/scan` URL verdict (`_send_scan_verdict`) and every message
  analysis (`handle_analyze`), when the flag is on: the verdict carries a
  "🚩 Report this as a scam" inline button plus a one-line hint.
- Tapping it fires callback `rsreport` → `handle_report_callback`, which
  reads the user's `last_scan` (stashed on the user record at verdict time)
  and files the report.
- Confirmation: "Report received. It's queued for human review. Community
  reports are never added to our threat data automatically."

**WhatsApp** (`relayshield_whatsapp_webhook.py`)
- After SCAN and MSGSCAN verdicts, when the flag is on: verdict text ends
  with "Reply *REPORT* …". `REPORT` is a first-class command keyword (never
  swallowed as a pending-command argument).
- `handle_wa_report_command` reads `last_scan` from the user record and
  files the report; same confirmation copy as Telegram.
- HELP lists REPORT only when the flag is on.

## Quarantine store

Table: `relayshield_report_quarantine` (env `REPORT_QUARANTINE_TABLE`).
**Not created by this change** — table creation is a deploy-time step.

| Item kind | pk | sk | Key attributes |
|---|---|---|---|
| Report | `IND#<indicator_key>` | `RPT#<iso_ts>#<reporter_hash12>` | indicator, indicator_type, reporter_hash (sha256, never raw), channel (`tg`/`wa`), reported_at, verdict_at_report, note (≤280 chars), status, confidence=`community`, ttl (365d) |
| Reporter profile | `REPORTER#<reporter_hash>` | `PROFILE` | first_seen, window_start, window_count, reports_total, reports_approved, reports_rejected, reputation (0–1, starts 0.5) |

`indicator_key` groups reports: `url#…`, `domain#…`, `wallet#…`, `phone#…`,
`msg#<sha256>`. Message text is **never stored raw** — only its hash.

## Status lifecycle

`quarantined` → `suggested` → `approved` / `rejected`

- `submit_report()` always writes `quarantined`, and only to the quarantine
  table. One live report per reporter per indicator (dedupe).
- `suggest_for_review()` moves to `suggested` when independent corroboration
  clears the weight threshold. This queues for human review; it is NOT
  corpus promotion.
- `review_report()` is the single promotion gate (explicit `reviewer`
  identity required).

## Confidence rules

- Community confidence is a new ladder rank `community` = −1, strictly below
  every curated level (`unverified` 0 … `confirmed` 4) — the confidence-decay
  principle from `relayshield_intel_pivot.py`.
- A record promoted through the review gate is capped at `unverified`,
  still strictly below curated `observed`, and carries
  `source: "community_quarantine"` plus corroboration detail and the
  originating report ids.

## Promotion-gate rules (exact)

`review_report(indicator_key, decision, reviewer, …)`:

1. `decision` must be `approved` or `rejected`; `reviewer` is required.
2. Only reports in `quarantined`/`suggested` are decided; rejected reports
   never corroborate and never reach the corpus.
3. **Approval additionally requires** at least one of:
   - independent corroboration: Σ distinct-reporter weights ≥ 2.0, or
   - a match to existing corpus evidence (`corpus_match=True` or live lookup).
   Otherwise approval raises `ReportRefused`.
4. On approval, exactly one corpus record is written (capped confidence,
   full provenance); quarantine rows are marked `approved`, never deleted.
5. Reporter reputations move with the outcome: approval +0.15 (cap 1.0),
   rejection ×0.7 (floor 0.05).

## Abuse controls

- **Rate limit:** 10 reports per reporter per 24h (`RateLimited`).
- **Account-age weighting:** weight = reputation × (0.25 + 0.75 × age/30d).
- **Poisoner suppression:** reputation < 0.2 → corroboration weight 0
  (reports still accepted, visible, reviewable).
- **Sybil burst:** ≥5 reports on one indicator from accounts <1 day old
  within 1 hour → flagged `sybil_suspect`, those reporters weigh 0.

## Demand-side signal

`community_report_count()` counts live (non-rejected) reports per indicator.
Rendered in scan output only as labeled context, e.g.:

> 👥 Reported as suspicious by N users — community reports, not verified
> threat intelligence.

It never changes a verdict level.

## Feature flag

`COMMUNITY_REPORTS_ENABLED` env var, default **off**. When off: no buttons,
no hints, no HELP line, and `submit_report()` raises `ReportsDisabled`.
The DynamoDB table is only touched when the flag is on.

## Copy rules

Never "safe". Confirmation and hint copy state explicitly that reports are
queued for human review and never auto-added to threat data.

## Tests

`test_community_reports.py` — 20 tests, all green (fake dict-backed table,
no AWS): quarantine-not-corpus, disabled-by-default, provenance + hashing,
message-hash privacy, dedupe, confidence-cap invariant, no auto-promotion on
counts, approval-refused without corroboration/corpus-match, full
corroboration→suggest→approve path with capped corpus write, corpus-match
approval path, rejection decay + exclusion from counts, rate limit,
low-trust zero weight, sybil-burst zeroing, account-age weighting,
demand-side label rendering (incl. never-"safe"), indicator classification.
`test_relayshield_intel_pivot.py` still green (27 tests) — the confidence
ladder import is untouched.

## Rollout notes (for a future deploy — NOT done here)

1. Create the `relayshield_report_quarantine` DynamoDB table
   (pk `pk` STRING, sk `sk` STRING, on-demand).
2. Set `COMMUNITY_REPORTS_ENABLED=true` in the bot Lambdas when ready.
3. Admin review runs `review_report()` — no console/AWS work ships in this
   branch beyond the function itself.
