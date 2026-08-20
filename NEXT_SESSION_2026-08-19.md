# Next session pickup, written 2026-08-19

Durable handoff. Everything below is on `main` unless stated otherwise. Read the ENVIRONMENT
section before running anything — most of today's wasted time came from commands that could not
work in this sandbox, and repeating them will waste the next hour the same way.

## Shipped and verified today

| Commit | What |
|---|---|
| `0929612` | Telegram + WhatsApp scanners: parcel/delivery-fee lure category, international brands, word-boundary brand matching, screenshot-link caveat |
| `32e7481` | Merge to main (`--no-ff` deliberately, see below) |
| `65fb95f` | Victim-side outreach reworked for the founder's corrections |
| `3512294` | `tools/export_intel_sample.py` — outreach sample-slice exporter |
| `eba0a45` | rsscan licence corrected to MIT in the BTV draft |
| `07a4ba3` | `xsoar_techalliance_application.md` — Tech Alliance answers + the joint-customer gate |
| `ca7e612` | Exporter: exclude public-feed indicators, measure exclusivity per run |

**Lambdas deployed.** `relayshield-telegram-webhook` and `relayshield-whatsapp-webhook`, run
32248226923, both import-probed clean. Arjen's SPL screenshot now returns **HIGH RISK** with the
brand + fee-lure flags; it previously returned "no automatic red flags."

**Deploy gotcha worth keeping:** `deploy_lambdas.yml` detects changes with
`git diff --name-only HEAD~1 HEAD`. Merging a branch fast-forward puts the last commit on top; if
that commit is docs-only, **nothing deploys**. Merge with `--no-ff` so the merge commit's diff
against its first parent carries the `.py` files.

## The finding that matters most

**`relayshield_intel_iocs` is a MIXED table and the outreach numbers were wrong.**

`relayshield_intel_feed.py:180` writes public-feed indicators into the same table as the Telegram
monitor, with `category: "threat_feed"` and `channel` set to the feed name (`threatfox`, `urlhaus`,
`feodo_tracker`, `feodo_aggressive`, `cisa_kev`, `_system`).

First live export, 2026-08-19: **511,038 distinct exportable indicators** — 249,139 ip, 145,933
domain, 82,067 url, 26,239 hash_sha256 — against the 13,358 crypto-heavy corpus
`Victim_Side_Outreach_Targets.md` measured on 2026-08-17. The wallets barely moved
(3,131 → 3,385 BTC, 1,215 → 1,321 SOL): those are the channel-collected part. Everything else is
abuse.ch.

Sending that slice to TRM/Chainalysis/Elliptic/Merkle under "99.89% appears in no public feed we
ingest" would have handed them their own URLhaus and ThreatFox rows. They ingest those feeds. It
would have been disproved in minutes and ended the conversation.

`ca7e612` fixes the exporter: channel-collected only (`--include-feeds` opts back in), feed names
never used as source labels, type casing normalised (`IP`/`ip`, `SHA256`/`sha256`/`hash_sha256`),
`_control` dropped, and **exclusivity measured per run** — a channel-collected indicator that also
appears in an ingested feed counts against it. The manifest carries `measured_exclusive_share`.

**Consequence not yet worked through:** if the channel-collected corpus really is ~1% wallets by
volume, the Segment 1 pitch is thinner than the targets file assumed. Still real — a few thousand
criminal-channel wallet addresses is a legitimate offer — but the honest framing is closer to
"roughly 4,700 wallet addresses plus scam URLs" than "13,358 indicators, 91.6% crypto."

## State of each thread

### 1. Victim-side outreach — BLOCKED on a re-cut export

The four Segment 1 drafts in `victim_side_outreach_messages.md` still quote the **stale**
2026-08-17 figures. Do not send until the new manifest is in hand and the numbers are replaced.

Founder has a **Head of Product at Merkle Science**; the Head-of-Product-specific message is in
the session, not yet in the file — rewrite it into `victim_side_outreach_messages.md` next session.

Founder corrections already applied: Segment 2 on hold (MetaMask Snap **not approved**, so there is
no warm thread), Phantom excluded (ignored a previous message), Segment 3 ungated (Kraken/Privy
post is published).

Re-cut on the founder's Mac:

    rm -rf "$HOME/Side SaaS Hustle/dist/intel_sample"
    git -C "$HOME/Side SaaS Hustle" fetch -q origin main
    git -C "$HOME/Side SaaS Hustle" show origin/main:tools/export_intel_sample.py > /tmp/rsexport.py
    AWS_PROFILE=relayshield /tmp/rsvenv/bin/python /tmp/rsexport.py --out "$HOME/Side SaaS Hustle/dist/intel_sample"

`/tmp/rsvenv` is a throwaway venv with boto3 (Homebrew Python 3.14 is PEP 668 externally-managed,
so a plain `pip install` fails). Recreate with `python3 -m venv /tmp/rsvenv && /tmp/rsvenv/bin/pip install boto3`.

### 2. Microsoft Sentinel PR #14924 — arm-ttk hardcoded-URI fix ready, NOT yet pushed

Commit `7c871321` on `fix/ti-domain-commonsecuritylog-join` carries the V3-regenerated package
(`mainTemplate.json`, `createUiDefinition.json`, `3.0.21.zip`). Verified against the pushed file:
exactly one `TI Map Domain entity to PaloAlto CommonSecurityLog`, query has `tolower(ObservableValue)`
and no `tolower(IndicatorType)`. Founder posted the reply to v-shukore.

- Version stayed **3.0.21** — catalog mode reports 3.0.20 published, so 3.0.21 is the pending one.
  An earlier local run said 3.0.22 only because it had no catalog access.
- The tool exits through its catch with an ARM-TTK finding: `Microsoft.Resources/deployments`
  apiVersion 2020-06-01 is 2270 days old. Pre-existing, from Microsoft's own templates. Disclosed
  in the PR reply.
- **A second rule has the same defect**: `TI Map Domain entity to Cloud App Events`
  (`DomainEntity_CloudAppEvents_Updated.yaml:32`) sets `DomainName = tolower(IndicatorType)` in its
  TLD-list block, so the TLD set resolves to `{"name"}`. Offered as a separate PR in the reply.
  **Open: does Microsoft want that PR?**
- Loose end: temporary branch `ci/v3-package` still on the fork. Deleting it from this sandbox
  fails with a proxy disconnect; delete via the Branches page.

**2026-08-20 — reviewer's arm-ttk ask is diagnosed and fixed.** v-shukore asked to "check the
arm-ttk validation failure causing due to hardcoded value in maintemplate". It is
`DeploymentTemplate-Must-Not-Contain-Hardcoded-Uri` / `Hardcoded.Url.Reference`, **2 hits**, both
the literal `https://management.azure.com/.default` in the Threat Intelligence Upload API
connector's "Get Microsoft Entra ID Access Token" step.

**It is a regression the V3 repackaging introduced** — master has zero occurrences, because master
carries `"management": "[concat('https://management','.azure','.com/')]"` and renders the step
through it. The source connector JSON has always held the literal; the tool's `azureManagementUrl`
substitution only covers playbooks, never data connectors. Master's form was a manual
post-generation patch, and regenerating flattened it back.

Fix prepared and verified (see `sentinel/README_ti_hardcoded_uri_fix.md` and
`sentinel/ti_maintemplate_hardcoded_uri.patch`): 3 hunks, all byte-identical to upstream master,
plus `3.0.21.zip` rebuilt to match. `tools/armttk_hardcoded_uri.py` reports 0 errors after.

**Not pushed to the fork yet** — pushing to `fix/ti-domain-commonsecuritylog-join` updates the live
Microsoft PR, so it needs the founder's go-ahead. Everything is staged and one push away.

Also still open on this PR: the `apiVersions-Should-Be-Recent` finding (`Microsoft.Resources/deployments`
`2020-06-01`, ~2270 days old) is a *separate*, pre-existing issue from Microsoft's own templates —
already disclosed in the PR reply. Do not conflate the two.

### 3. XSOAR PR #45206 — awaiting Tech Alliance reply

Founder emailed `techpartners@paloaltonetworks.com` asking whether an already-approved community
content pack needs Tech Alliance membership to get demo-tenant access.

**The gate if they say yes:** the application requires **2 named joint customers with contact
info**, who get contacted during validation. RelayShield has none who run Cortex XSOAR. Do not
invent them. If Tech Alliance turns out to be mandatory, the next move is asking Arjen Peirce
whether any client runs XSOAR and would agree to be named — not another attempt at the form.

Everything else on the form is drafted in `xsoar_techalliance_application.md`.

### 4. Zapier — NOT DONE, founder action

133 tasks on hold. Root cause is arithmetic: 12 daily "Daily … — RelayShield" test Zaps ≈ 360
tasks/month against a 100-task cap. Recommendation given and accepted in principle: **move all 12
to weekly** (~52/month), which leaves headroom for the real embed signup that triggers the beta
early exit. Held tasks are not auto-replayed and replaying them would re-blow the cap.

Guardrails: do not delete any Zap or template (they are the live-usage validation evidence), do not
enable pay-per-task. This needs the founder in the Zapier UI — no API exists for editing Zap
schedules and this session cannot drive their browser.

### 5. BTV — SENT

rsscan availability ask posted to Blue Team Village from the founder's personal handle with the
affiliation disclosed. Draft retained in `btv_rsscan_outreach.md`. The CFP submission
("LLMjacking: the credential theft your SIEM structurally cannot see") is a separate track, not
started. **Watch for replies and answer them.**

Caught during review: the draft said Apache-2.0; rsscan is **MIT** (LICENSE, pyproject, PyPI
classifier all agree). Fixed in `eba0a45`.

## ENVIRONMENT — read before running anything

**Blocked by this sandbox's egress policy** (403 on CONNECT; do not route around, report instead):
`catalogapi.azure.com`, `www.powershellgallery.com`, `ppa.launchpadcontent.net`, and arbitrary
vendor sites (`trmlabs.com`, `merklescience.com`, …). Reachable: GitHub, `raw.githubusercontent.com`,
`api.nuget.org`, `packages.microsoft.com`, PyPI.

- **No AWS credentials in this session.** Anything touching DynamoDB runs on the founder's Mac.
  The GitHub Actions OIDC role has CloudWatch read + one Lambda invoke only, no DynamoDB.
- **The V3 Sentinel tool cannot complete here** — `getParserDetails()` in
  `Tools/Create-Azure-Sentinel-Solution/common/commonFunctions.ps1:299` calls `catalogapi.azure.com`
  unconditionally. The working answer was a GitHub Actions runner in the fork; that pattern is
  reusable for anything else needing network the sandbox lacks.
- **`workflow_dispatch` only shows a Run button when the workflow file is on the repo's default
  branch.** On a non-default branch use `on: push: branches: [<that branch>]` instead.
- This session's GitHub App **cannot dispatch workflows** (`403 Resource not accessible by
  integration`) and cannot attach repos outside the `nzdsf2-gif` owner, so no commenting on
  `Azure/Azure-Sentinel` or `demisto/content` — the founder posts those.
- **macOS zsh does not treat `#` as a comment interactively.** A trailing comment on a command line
  becomes arguments: `cd ~/foo # note` → "cd: too many arguments". Never append comments to
  commands handed to the founder.
- **`~/Side SaaS Hustle` IS the local clone** of `nzdsf2-gif/relayshield`. Its `main` had unpushed
  commits (the rsscan 0.2.x work) and diverged from origin; reconcile with
  `git -c pull.rebase=false pull origin main`, never rebase.
- **rsscan on PyPI is 0.2.1; this repo has 0.1.3.** `--deps` (npm publisher counting) ships in
  0.2.0+ and exists only on the founder's laptop. **Push that work.** It is the second time a
  single-laptop-only state has caused a wrong answer here.

## Suggested order next session

1. **Re-cut the export and fix the four outreach messages' numbers** — everything else in the
   outreach thread is blocked behind it, and the founder wants to send today.
2. **Rewrite the Merkle Science Head-of-Product message into the file** so it stops living only in
   a chat transcript.
3. **Zapier weekly cadence** — five minutes in the UI, and the task cap is actively stopping Zaps.
4. **Watch BTV for replies.**
5. **Chase the Tech Alliance reply** if nothing lands in ~3 business days.
6. Carried forward and still untouched: Bundle A on a new AWS entity, the bundle-subscriber usage
   counter, SentinelOne Technology Partner registration (DUNS 14-989-2087 in hand, fill the D&B
   profile first), Twilio balance at $5.00, `coinbase/agentkit#1449` stalled at 0/2 Heimdall
   reviews, Ansible Galaxy namespace approved and unclaimed, the 9 em-dashes on `/developers`.
