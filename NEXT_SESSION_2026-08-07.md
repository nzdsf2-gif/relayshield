# Next session pickup, written 2026-08-06 evening

Durable copy of the task list, in case the in-app tasks do not survive a restart. The full
narrative is in memory as `project_session_snapshot_2026-08-06.md`, which is the START HERE.

## Suggested order

### 1. Bundle A on its own NEW AWS entity

**Why first:** the only surface that has ever converted. One real paying customer, and they came
through AWS Marketplace.

**The question that was asked and answered:** adding Bundle A does **not** affect the two flat-rate
TI licences, which sit on a separate entity (`prod-kb3ftelx44wlk`). It **does** put Bundle D at risk
**if** Bundle A is added to the shared entity `prod-kkvurtspreofy`, because `AddDimensions` cannot be
submitted without pricing, and a change set replaces the whole rate card. That is what caused the
2026-07-27 rollback to placeholder prices.

**So: create a NEW product entity for Bundle A.** Risk disappears, and it fixes the fact that
`prod-kkvurtspreofy`'s listing text describes only Bundle D.

- Dimensions: 1 `Entitled` contract dimension (`core_identity_bundle_access`, carries the monthly
  minimum) plus 6 `ExternallyMetered`. The 6-vs-7 confusion is settled, both numbers were right.
- **Check first:** AWS serialises submissions per SELLER ACCOUNT. If any change set is in flight
  anywhere, this is blocked. The 2026-08-05 corrections both SUCCEEDED so it should be clear.
- Verify live state first, I did not get to run this:
  `AWS_PROFILE=relayshield aws marketplace-catalog list-entities --catalog AWSMarketplace --entity-type SaaSProduct`
- No em-dashes, en-dashes or smart quotes in listing text, the Catalog API rejects them.
- Baseline if the shared entity is ever touched: `aws_marketplace/offer_baseline_2026-07-31.json`.

### 2. Usage counter on the bundle-access branch

**Why early:** the first AWS disbursement lands around **Aug 10**. Right now you cannot tell whether
the one paying customer has made a single call, which is the wrong footing for a conversation with
them.

There is **no** per-call record for a bundle subscriber anywhere:

- Successful requests do not log the API key. It only appears on error paths, truncated to
  `api_key_str[:16]`.
- Bundle calls take the `is_bundle_d_call` bypass at `relayshield_api.py:1030` and write no counter.
- `intel_period_calls` only increments on the intel quota path, which needs an `intel_plan_tier` the
  Bundle D key does not have.

Increment on SUCCESS only, matching how `free_calls_remaining` is decremented. Observability only:
do not bill on it, do not gate on it, and do not change what AWS is charged (Bundle D is
contract/entitlement based via License Manager). Verify with a real call, not by reading the source.
`relayshield_api.py` is a TWO-file deploy with `relayshield_openapi_spec.py`.

### 3. BB-8 developer remediation channels

GitHub Checks / PR annotations first (highest value, inline where the developer already is), then
Slack, then a generic webhook. Not WhatsApp or Telegram, wrong audience for this buyer.

Honest framing: this feeds the developer funnel, which has produced **zero** keys so far. Investment,
not pipeline.

### 4. Zapier Workflow Element on /developers, plus template 1

**BLOCKED on the founder signing into Zapier in Chrome.** Two console checks first:

1. Does Workflow Element **Discover mode** render with ZERO public templates? If yes, ship the embed
   first, since the embed (not template count) is the early-exit trigger. If no, template 1 ships
   first and the sequencing flips.
2. Does it require a paid plan or partner tier?

Also check what consumed 80% of the 100-task limit at `zapier.com/app/history/usage`.

**Task limit guidance:** hitting 100 stops your OWN Zaps. It does NOT unpublish the integration or
remove templates. **Do not delete any Zap or template.** Pay-per-task costs real money; do not
enable it yet.

Template 1 = employee offboarding credential check, the proven n8n 16694 shape, with the
access-revocation branch from day one per MKTPL-14 (a public commitment made in a LinkedIn reply).

### 5. SentinelOne Technology Partner registration

DUNS **14-989-2087** arrived, so it is unblocked. `partners.sentinelone.com/partner/registration`.
**TECHNOLOGY track**, not reseller and not MSSP.

**Do first:** the D&B profile shows "Year Started: 0 Years (2026)" and "Last updated: N/A". Fill it
in via "Manage Company Profile" before submitting.

### 6. Microsoft Sentinel connector PR

The integration GUIDE is already live at `/guides/microsoft-sentinel`. The `Azure/Azure-Sentinel`
community PR is what is NOT started, confirmed by checking the repo for artifacts.

Opening the PR needs only GitHub, but a connector never run against a real workspace will get
bounced. Confirm current Sentinel free-tier terms before signing up for anything. Read
`project_taxii_conformance_verified` first for the ObservableKey map.

### 7. The 9 em-dashes on /developers

Live count is 9, not the 16 an older note claims. Source is `relayshield_developer_signup.py`,
single-file deploy. Replace each **individually**, never find-replace. Verify with a live curl
returning 0.

### 8. Check awesome-x402 PR #1154

https://github.com/xpaysh/awesome-x402/pull/1154 — opened 2026-08-06, adds RelayShield to
`### Agent Verification & Security`.

## Waiting on the founder

- Zapier login, for the two console checks.
- Twilio **Lookup v2 usage**, at Console then Monitor then Usage then the by-category view. If it
  shows zero, drop the Lookup claim from the ask before sending it to `sales@twilio.com`. There is no
  Account Executive, the account is self-serve pay-as-you-go.
- D&B profile fill-in, before SentinelOne.
- **XSOAR**: no reply as of 2026-08-06. The Community Edition form is a sales lead capture, not
  provisioning. If nothing lands, message Moshe on the PANW DFIR Slack.

## Still not done, carried forward

Per-post `og:image` on the blog (one shared card for every post is what wrecked the Medium import,
fix written up in `medium_import_fixes.md`), and Hacker News, which stays deliberately held.
