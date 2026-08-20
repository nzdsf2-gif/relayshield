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

**Merkle Science outreach TABLED 2026-08-20 (founder's call).** The re-cut export confirmed the
majority of the ~511K indicators come from ingested third-party feeds (abuse.ch et al), not from
our own channel collection. That guts the differentiator the Merkle pitch rested on — we would be
selling a blockchain-analytics firm a corpus largely composed of feeds they already ingest.

**Do not send.** The Head-of-Product message stays unwritten on purpose. Revisit only once the
channel-collected (genuinely exclusive) indicator volume has grown enough to carry the pitch on its
own. That growth is the prerequisite, and it is the thing to work on — not the message.

The same reasoning applies to the other Segment 1 targets (TRM, Chainalysis, Elliptic): they all
ingest the same public feeds, so the whole segment is gated on exclusive volume, not on copy.

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

### 2. Microsoft Sentinel PR #14924 — CLA accepted, arm-ttk fix pushed, awaiting review

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

**Pushed 2026-08-20** as `1663444` on `fix/ti-domain-commonsecuritylog-join`. Re-fetched from the
branch to confirm: the live file is the verified patched one and the check reports 0 errors.

**CLA accepted 2026-08-20** — founder posted
`@microsoft-github-policy-service agree company="RelayShield LLC"`. Both of v-shukore's asks on the
PR are now answered.

Also still open on this PR: the `apiVersions-Should-Be-Recent` finding (`Microsoft.Resources/deployments`
`2020-06-01`, ~2270 days old) is a *separate*, pre-existing issue from Microsoft's own templates —
already disclosed in the PR reply. Do not conflate the two.

### 2c. Telegram `/scan` was a dead end for pasted messages — FIXED 2026-08-20

**Founder report: "scan seems to be broken, it didn't recognize the screenshot."** Two real defects,
both fixed in `relayshield_telegram_webhook.py`.

1. **`/scan` rejected any non-URL.** `_normalize_scan_url()` returns `None` when the input contains
   a space, so a pasted scam SMS or job-offer message hit `"That doesn't look like a URL"` and the
   user was done. That is the most common thing a worried person does. Now: non-URL prose falls
   through to `handle_analyze()`, so `/scan` and `/msgscan` behave as one command. A short spaceless
   token still gets the error, because that is a typo'd URL, not a message.
2. **A captionless screenshot was ignored entirely.** The OCR branch required
   `caption in ("msgscan","analyze","analyse")`, so a bare image matched nothing and the bot replied
   *nothing at all* — which reads as broken. Now any uncaptioned image goes to OCR → fraud analysis.

**The merge never shipped.** The founder remembered `/scan` and `/msgscan` being merged; `git log
--all --grep=msgscan` returns zero commits and both are still separate in the help text. It was a
plan, not a release. The fix above delivers the behaviour without collapsing the commands.

**Not yet deployed.** Needs a Lambda deploy — and per the deploy gotcha at the top of this file,
merge with `--no-ff` or the docs-only commit on top means nothing ships.

### 2d. Corpus: 95 vs 122 explained, and five IOC types were being discarded

**Nothing ever set `active` back to `False`** — every `active=False` write is at row creation. So
122 vs 95 is not recorded attrition, it is two numbers that were never compared: `active=True`
("we intend to monitor") vs channels actually readable. On `ChannelPrivateError`/`ValueError` the
code did a bare `continue`, so a dead channel counted as healthy forever.

Fixed: `_record_channel_failure()` / `_clear_channel_failure()` track `consecutive_failures` and
`last_error`, and the digest now says **`Channels checked: 95 of 122 active ⚠️ 27 unreachable`**.
Nothing auto-deactivates — a private channel can come back, so it records and a human decides.
**Fields are empty until the patched monitor runs; an all-zero column proves nothing yet.**

**`extract_iocs()` extracted five types `type_map` never stored**, so none were ever persisted —
the identical defect to the documented `cves` one. Added `tg_handle` (**the scam-operator-handle
category the founder asked for** — highest uniqueness available, since feeds publish infrastructure
not people), `onion`, `hash_md5`, `hash_sha1`. **`ransomware_victims` deliberately excluded**: those
are victim organisations, and the IOC table is what customer watchlists match against.
`tg_handle` is a **lead list, not a verdict** — the regex matches any @mention; do not export it as
"known scam operators" without filtering.

**The 75 pending channels need AWS and could not be triaged here.**
`tools/triage_channels.py` does it from the founder's Mac — read-only unless `--apply`.

New ToDos: **pivot enrichment** (with confidence strictly below the seed) and **re-check unknowns on
delay** (a link clean Monday and flagged Friday was exclusive on Monday, and provably ours first).
Plus a test that fails when `extract_iocs()` and `type_map` diverge — it has broken silently twice.

### 2b. Discord bot outreach — DFK decision made, and the workstream is still laptop-only

**Recovered 2026-08-20 by upload, not from git.** `gaming_prediction_markets_focus_list_20260814.md`
is now committed. **`relayshield_discord_bot.py` is still missing from the repo**, along with
`discord_admin_approach_message.md`, `discord_midsize_pipeline_2026-08-13.md` and
`NEXT_SESSION_2026-08-14.md`. The address regex at `relayshield_discord_bot.py:112` gates the entire
outreach list and nobody but the founder can read it. **Third repeat of the single-laptop-only
failure** (rsscan 0.2.x is the standing example). Push it.

**DeFi Kingdoms — pitch the bot, not rsscan.** The bot serves 55,661 players and is something a
BizDev team can approve and announce; rsscan is free, MIT and needs no integration, so it has no
partnership shape and is a one-line mention for their engineers rather than the ask. Route: the
**partner channel first** (that standing is why the size band was overridden for DFK at all), the
BizDev form `https://forms.gle/fv4y1G3ppNgJDpEDA` only as fallback. Not the general contact form,
and never the bug-report route.

**New headwind, dated 2026:** DeFi protocols are leaving Discord — Morpho went read-only Feb 1 2026,
DefiLlama moved to ticketed support, and Discord's October Zendesk breach is the backdrop. It does
not kill the DFK pitch (a game's Discord is its social layer, not a support desk) but the pitch
should name it and turn it: teams are fleeing because they cannot screen what gets posted and DM'd,
which is what the bot does.

**Do not open a DeFi-protocol candidate list** — same structural dead end as prediction markets.
Gaming-adjacent DeFi (DFK's own shape) is the exception worth mining.

Four new gaming candidates added, all **UNRESOLVED**: Lumiterra and The Machines Arena (Ronin),
Guild of Guardians (Immutable, previously dismissed on a *guessed* code), and DFK JP as a second
shot. Alien Worlds ruled out on the address gate — WAX uses EOS-style account names, not `0x`.
`discord.com` is egress-blocked in the sandbox, so no invite could be resolved here.

### 3. XSOAR PR #45206 — awaiting Tech Alliance reply

Founder emailed `techpartners@paloaltonetworks.com` asking whether an already-approved community
content pack needs Tech Alliance membership to get demo-tenant access.

**The gate if they say yes:** the application requires **2 named joint customers with contact
info**, who get contacted during validation. RelayShield has none who run Cortex XSOAR. Do not
invent them. If Tech Alliance turns out to be mandatory, the next move is asking Arjen Peirce
whether any client runs XSOAR and would agree to be named — not another attempt at the form.

Everything else on the form is drafted in `xsoar_techalliance_application.md`.

### 4. Zapier — runbook written, founder action in the UI

133 tasks on hold. Root cause is arithmetic: 12 daily "Daily … — RelayShield" test Zaps ≈ 360
tasks/month against a 100-task cap. Recommendation given and accepted in principle: **move all 12
to weekly** (~52/month), which leaves headroom for the real embed signup that triggers the beta
early exit. Held tasks are not auto-replayed and replaying them would re-blow the cap.

Guardrails: do not delete any Zap or template (they are the live-usage validation evidence), do not
enable pay-per-task. This needs the founder in the Zapier UI — no API exists for editing Zap
schedules and this session cannot drive their browser.

**2026-08-20 — step-by-step click-path written to `zapier_weekly_cadence_runbook.md`.** Confirms
there is genuinely no CLI path: the Platform CLI manages published *integrations*, not the Zaps in
an account, and no REST endpoint edits a trigger schedule. The runbook says to spread the 12 across
different weekdays rather than stacking them on Monday, since a burst is what trips a cap.

**Partner Sandbox is available but does NOT fix the cap — corrected 2026-08-20.** ZPS is a separate
*workspace* ("access to a workspace with premium Zap features"), not an upgrade to the workspace the
12 Zaps live in, and it forbids production data. **So the weekly change is the fix, not a
tourniquet.** The Sandbox is only where new template development belongs. Route:
`https://developer.zapier.com/` → RelayShield → Manage → Manage team → Request access (the
per-integration deep link needs an app ID not recorded in this repo, and all zapier.com domains are
egress-blocked from the sandbox, so it could not be verified). Request it now; approval is not
instant and the template todo is blocked behind it. **Do not move the 12 Zaps into the Sandbox** —
open question whether sandbox usage still counts as the live-usage evidence they exist to produce;
ask Partners Support first.

**NEW TODO — add a template in the Zapier dev sandbox to pave a flywheel.** Published templates are
Zapier's own discovery surface: a user installing one becomes a live integration user without
touching relayshield.net. **Do not build it before Sandbox access lands** — building in the
production account re-blows the 100-task cap for the same reason it blew the first time. Five
template ideas already drafted; pick from those.

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

1. **Grow the channel-collected indicator corpus.** With Segment 1 outreach tabled (see thread 1),
   exclusive-indicator volume is the gating constraint on that whole segment — it is now the work,
   not a precondition to the work. **Plan written 2026-08-20:
   `intel_corpus_growth_plan.md`.** Top two by leverage: (a) build the decided-but-unbuilt Haiku 4.5
   classifier to triage the 75 `pending_review` channels — up to +60% collection surface for ~$0.17;
   (b) start extracting **scam operator handles** (Telegram/Discord usernames, channel IDs, invite
   codes) as a first-class indicator type — ~100% exclusive by construction, because no public feed
   publishes people rather than infrastructure. The KPI is `measured_exclusive_share` per category,
   not corpus size.
2. ~~Merkle Science Head-of-Product message~~ — **tabled 2026-08-20**, see thread 1.
3. **Zapier weekly cadence** — five minutes in the UI, and the task cap is actively stopping Zaps.
4. **Watch BTV for replies.**
5. **Chase the Tech Alliance reply** if nothing lands in ~3 business days.
6. Carried forward and still untouched: Bundle A on a new AWS entity, the bundle-subscriber usage
   counter, SentinelOne Technology Partner registration (DUNS 14-989-2087 in hand, fill the D&B
   profile first), Twilio balance at $5.00, `coinbase/agentkit#1449` stalled at 0/2 Heimdall
   reviews, Ansible Galaxy namespace approved and unclaimed, the 9 em-dashes on `/developers`.

---

## 2026-08-20 — Telegram help shortcuts: rebuilt, NOT restored

**Founder report: "several TG enhancements were deprecated without my consent" — category help
shortcuts, and a round of command-pruning that simplified the platform.**

**They are not in git, and never were.** `relayshield_telegram_webhook.py` entered the repo on
2026-07-30 (`26b16ae`) and has only **four commits** in its entire history. There is no earlier
version of the help menu anywhere in the repository, so `git checkout` cannot bring anything back.

### The likely mechanism, and it will happen again

`deploy_lambdas.yml` deploys `relayshield_telegram_webhook.py` **from the repo** to
`relayshield-telegram-webhook`. So the sequence is almost certainly:

1. Enhancements were written on the founder's Mac and pushed straight to Lambda.
2. They were never committed.
3. A later repo-sourced deploy — the 2026-08-19 run is the obvious candidate — replaced the live
   function with the repo's copy, silently reverting them.

**Nobody deprecated anything.** A deploy overwrote uncommitted work. This is the same
single-laptop-only failure as rsscan 0.2.x and the Discord bot, and it is the first time it has
destroyed shipped behaviour rather than just hidden it. **Anything not in the repo will be erased
by the next deploy of that Lambda.**

### Rebuilt 2026-08-20 — check it against memory

Category shortcuts are back as an inline keyboard on `/help`, two buttons per row, tier-gated so
nobody is offered a category their plan lacks: Breach Response, Threat Analysis, Phone Protection,
Telegram Security, then Team / Crypto Shield / Domain Security where the tier allows, then Account
and "See all commands". The keyboard stays attached after tapping a category, so users can move
between them without re-running `/help`.

Sections are **derived from `msg_help()`**, not duplicated from it — a second hardcoded copy of the
command list is precisely what let `extract_iocs()` and `type_map` drift apart twice in the intel
monitor.

**Command pruning: only `/msgscan` was folded in**, because `/scan` now takes links, pasted messages
and screenshots (see 2c), which makes a second command for the same job redundant. It is hidden from
help and from `setMyCommands`, and still works as an alias alongside `/analyze` and `/analyse`, so
nobody who learned the old name is broken.

**Open: which other commands were pruned?** That list is not recoverable from the repo and was not
described in the report. Name them and they can be re-pruned in one pass.

**This is a reconstruction, not a restore.** It matches the described behaviour; it may not match
the original in detail.

---

## 2026-08-20 late — deployed, merged commands, and the drift fix

**Telegram is DEPLOYED.** Merge `ce1a6fe` → run 32413731965, import-probed clean.
**Intel is NOT** — `relayshield_intel_monitor.py` has no CI deploy path at all (not in
`deploy_lambdas.yml`'s paths or FUNCS map). Commands and the safety check are in
`lambda_recovery_and_deploy.md`; do not hand-deploy it until the layers-vs-vendored check passes.

**Faithful restore is still possible** — my "not recoverable" applied to git only.
`lambda_recovery_and_deploy.md` §1 lists three places to look, best first: the Mac's own working
tree / stash / reflog (most likely — the file may never have been committed but could still be on
disk), then published Lambda versions (only if any were published by hand; CI does not use
`--publish`, and `$LATEST` has been overwritten twice), then Time Machine.

**Command merges restored and extended.** `/scam` is the hub again — `/vishing`, `/botcheck`,
`/verifybot` reachable from a keyboard under it, and it moves to Telegram Security as the founder
described. `/extensions` folded into `/infostealer` under Threat Analysis. Every folded command
still routes unadvertised. Visible commands: 20 → 13.

**Drift prevention shipped:** `.github/workflows/lambda_drift_check.yml`, daily, diffs each live
function's handler against `main` and opens an issue on mismatch. Covers `relayshield-intel-monitor`
deliberately, since a hand-deployed function is the likeliest to drift. Confirm the OIDC role has
`lambda:GetFunction`/`GetFunctionConfiguration` after the first scheduled run.

**Zapier: Zaps cannot be turned off while over quota either.** Nothing to do this cycle.
**TODO 1 SEPTEMBER 2026 — push the weekly change to all 12 Zaps**, full steps in
`zapier_weekly_cadence_runbook.md`.

**`ransomware_victims` rationale rewritten** in `intel_corpus_growth_plan.md` with the concrete
failure it avoids: the IOC table means "this thing is dangerous", victim names mean "this company
was attacked", and mixing them fires credential-rotation alerts at breach victims while inflating
the exclusivity metric with data published on the leak sites themselves. **Filed as a ToDo to build
properly** in its own table, not as a refusal.

---

## 2026-08-20 — wrong AWS account, and supplier-breach watch built

**The intel-monitor "Function not found" was the wrong account, not a missing function.** The error
named account `620534471984`; **RelayShield's Lambdas are in `239677749008`** (the OIDC role ARN in
`deploy_lambdas.yml`, the KMS key ARNs, and the Marketplace listing all agree). The command ran
without `AWS_PROFILE=relayshield`, so it hit the default-credential account. Every command in
`lambda_recovery_and_deploy.md` now carries the profile, and there is a
`sts get-caller-identity` check up front. **Re-run the packaging check with the profile before
deploying intel.**

**Supplier-breach watch BUILT** (was a ToDo, now code on `main`):

* `relayshield_ransomware_victims` — its own table, never the IOC table. Rows carry
  `confidence: "unverified"`, since the extraction regex will contain noise.
* `_match_supplier_breach()` — **opt-in only**, reads an explicit `supplier_watchlist` on the user
  record and infers suppliers from nothing else.
* Exact normalised-key matching, suffixes stripped both ways, so "Acme Corp." matches `acme` and
  `acmecorp` but not "Acme Technologies".
* `_format_supplier_breach_alert()` — separate copy: you are *not* compromised, rotate the
  credentials **you issued to them**, watch for invoice fraud and impersonation, and confirm with the
  supplier before treating it as fact.

**Caught by testing before it shipped:** a 4-character key floor silently dropped every three-letter
supplier (IBM, SAP, AWS). Matching is exact equality, not substring, so short keys were never the
risk; bare corporate suffixes were, and are now excluded by name. Floor is 3.

**BLOCKER: the table does not exist yet.** Create it before the next intel deploy —
`lambda_recovery_and_deploy.md` §6 has the `create-table` and TTL commands, plus how to opt a
customer in. Until then victim writes fail as logged warnings; collection continues, victims drop.

---

## 2026-08-20 — intel monitor into CI, and two new ToDos

**Packaging check passed**, so the hand-deploy risk is gone:
`Layers: [arn:aws:lambda:us-east-1:239677749008:layer:relayshield-telethon:1]`, `Runtime: python3.12`,
`CodeSize: 47796`. Telethon is in a layer and the package is handler-only, so a
`update-function-code` with just the `.py` is safe.

**`relayshield_intel_monitor.py` is now in `deploy_lambdas.yml`** — path filter, fallback CHANGED
list, and the FUNCS map as `relayshield-intel-monitor`. It stops being the one Lambda that could
only be hand-deployed, which is what made it the likeliest to drift.

**Found while wiring it up, and it would have bitten on every deploy:** the CI import probe invokes
the function with `{"source":"ci.import-probe"}`, and `lambda_handler` had no branch for that — an
unrecognised payload falls all the way through to a **real scraping run**, after taking the lock. So
adding it to CI naively would have started a full Telegram sweep on every deploy and risked a
flood-wait the next scheduled run inherits. Guarded with an early return **before `_acquire_lock()`**.

Note `relayshield_intel_monitor.py` imports `relayshield_siem_connector` — the workflow resolves
local imports from the handler's own imports, and that file is already in the path list, so the zip
carries both. Confirm on the first run.

**macOS zsh gotcha, again:** the `# expect Account: 239677749008` comment appended to the
`sts get-caller-identity` line became arguments and errored. Already documented in ENVIRONMENT —
never append comments to commands handed to the founder.

### New ToDos

**a. Add ransomware-victim monitoring to the TI demo — target Saturday.**
The supplier-breach watch is built (`relayshield_ransomware_victims`, opt-in matcher, distinct alert
copy) but is invisible to anyone evaluating us. The demo at `cloudflare_worker_ti_demo.js` is where
prospects actually see capability. Show the victim feed and a supplier-watchlist hit. **Note the
demo is gated behind Worker secrets (`b7955fe`), so wire it into the existing `/demo/*` gating rather
than adding an ungated route.** Prerequisite: the table must exist and have data, so create it and
let one intel run populate it first.

**b. Competitive benchmarking against SOCRadar.**
SOCRadar is the closest comparable on the threat-intel/dark-web-monitoring axis. What to produce: a
side-by-side of coverage (IOC categories and counts we can *defend* — exclusive slice, not the 511K
headline), collection surface (their dark-web/Telegram claims vs our 95 reachable channels), pricing
and packaging, and integration surface (Sentinel, XSOAR, MISP/STIX-TAXII, MCP). **The honest framing
matters more than the win column** — the last outreach nearly went out claiming a corpus that was
mostly ingested public feeds, and a benchmark built on the same number would fail the same way. Use
`measured_exclusive_share` per category as the defensible figure.
