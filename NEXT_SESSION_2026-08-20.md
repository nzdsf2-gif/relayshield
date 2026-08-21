# Next session pickup, written 2026-08-20

Durable handoff. **Supersedes `NEXT_SESSION_2026-08-19.md`** — that file was appended to five times
during the day and is now hard to read; treat this one as current and use it for the older threads
only where this file points back to it.

Everything below is on `main` unless stated. Read **ENVIRONMENT** before running anything.

---

## START HERE — three things block other work

| # | Blocker | Why it matters |
|---|---|---|
| 1 | **`relayshield_ransomware_victims` table does not exist** | The deployed intel monitor writes to it every run. It degrades safely (writes fail as logged warnings, collection continues) but **victims are being dropped right now**, and the Saturday demo item depends on the table having data |
| 2 | **Intel Lambda's execution role may lack `dynamodb:PutItem` on that table** | Creating the table does not grant it. Identical failure mode — a warning and silently dropped rows — so check both together |
| 3 | **12 Zapier Zaps still daily, cap still blown** | Nothing can be done until **1 September**. Dated ToDo, do not retry before then |

Commands for 1 and 2: `lambda_recovery_and_deploy.md` §6.

---

## Shipped and verified today

| Commit | What |
|---|---|
| `1e3f7b4` | Sentinel PR #14924 arm-ttk `Hardcoded.Url.Reference` fix — root-caused and pushed to the fork |
| `af079a1` | Gaming outreach focus list committed (was laptop-only), DFK decision, new candidates |
| `d5f5a16` | Zapier runbook, intel corpus growth plan, `relayshield_discord_bot.py` committed |
| `810d9e0` | **Telegram `/scan` fix** — pasted messages and bare screenshots now reach the fraud analyser |
| `5209876` | Telegram help category shortcuts rebuilt; `/msgscan` folded into `/scan` |
| `9239e1c` | `/scam` and `/infostealer` command hubs; **`lambda_drift_check.yml`** |
| `5ab1c69` | **Supplier-breach watch** — victim table, opt-in matcher, distinct alert copy |
| `c11e58b` | **`relayshield_intel_monitor.py` into CI**; CI import-probe guard |

**Deployed and import-probed clean:**
* `relayshield-telegram-webhook` — run **32413731965** (`ce1a6fe`)
* `relayshield-intel-monitor` — run **32428466551** (`a291f82`)

---

## The structural finding of the day

**Telegram help shortcuts and a `/scam` command merge, both shipped in a prior session, were
destroyed by an ordinary deploy.** They were written on the laptop, pushed straight to Lambda, never
committed — and `deploy_lambdas.yml`, which deploys **from the repo**, replaced the live function
with the repo's copy.

Nobody deprecated anything. **Anything not in the repo is erased by the next deploy of that Lambda.**

Three fixes went in:

1. **`lambda_drift_check.yml`** — daily, pulls each live function's package, diffs the handler
   against `main`, opens an issue on mismatch. The issue text says to **recover from the live
   function before anything redeploys over it**.
2. **`relayshield_intel_monitor.py` added to CI deploys** — it was the last Lambda that could only
   be hand-deployed, i.e. the likeliest to drift next.
3. **`relayshield_discord_bot.py` committed** (recovered by upload).

**Confirm after the first scheduled drift run** that the OIDC role has `lambda:GetFunction` and
`lambda:GetFunctionConfiguration`. It logs a warning per function if not.

### Faithful restore of the lost Telegram code — still worth one attempt

My "not recoverable" applied to **git only**. `lambda_recovery_and_deploy.md` §1 has three routes,
best first: the Mac's working tree / stash / reflog (**most likely** — the file may never have been
committed yet still be on disk), then published Lambda versions (CI does not use `--publish` and
`$LATEST` has been overwritten twice, so only helps if any were published by hand), then Time
Machine. **Run these with `AWS_PROFILE=relayshield`** — the earlier attempt hit the wrong account.

If all three are empty, the reconstruction on `main` is the only version there is. **Check it
against memory**, especially: which commands besides `/vishing`, `/botcheck`, `/verifybot` and
`/extensions` were pruned in the original? That list is not recoverable and was never described.

---

## State of each thread

### 1. Microsoft Sentinel PR #14924 — both reviewer asks answered, awaiting review

CLA accepted, and the arm-ttk failure is fixed and pushed (`1663444` on
`fix/ti-domain-commonsecuritylog-join`).

Root cause worth remembering: **the V3 repackaging introduced it.** Upstream master carries
`"management": "[concat('https://management','.azure','.com/')]"` — a split-string trick so
arm-ttk's regex cannot match — and regenerating from source flattened it back to the literal
`https://management.azure.com/.default`. The tool's own `azureManagementUrl` substitution only
covers playbooks, never data connectors. Fix restores master's form verbatim; 3 hunks, byte-identical.

`tools/armttk_hardcoded_uri.py` re-runs the check (no PowerShell in the sandbox, powershellgallery
is egress-blocked). Details in `sentinel/README_ti_hardcoded_uri_fix.md`.

**Still open:** the `apiVersions-Should-Be-Recent` finding is separate and pre-existing (Microsoft's
own templates); do not conflate. And **does Microsoft want the second PR** for the same defect in
`TI Map Domain entity to Cloud App Events`?

### 2. Telegram bot — fixed, merged, deployed

* **`/scan` no longer dead-ends.** Non-URL prose falls through to `handle_analyze`, so `/scan` and
  `/msgscan` are one command from the user's side. A short spaceless token still errors (that is a
  typo'd URL, not a message).
* **Captionless screenshots work.** Previously an image with no caption matched no branch and the
  bot said *nothing*, which reads as broken. Tested across 9 cases including image-as-document; a
  PDF and a photo captioned with an unrelated command are correctly left alone.
* **Help category shortcuts** — tier-gated inline keyboard, two per row, keyboard stays attached
  after a tap. Sections are **derived from `msg_help()`**, not duplicated.
* **Command hubs**: `/scam` (Telegram Security) covers `/vishing`, `/botcheck`, `/verifybot`;
  `/infostealer` (Threat Analysis) covers `/extensions`. `/infostealer you@x.com` still runs
  directly — only the bare command shows the menu. **All folded commands still route, unadvertised.**
  Visible commands **20 → 13**.

### 3. Intel corpus — three real fixes

* **Five IOC types were extracted and discarded.** `extract_iocs()` produced `tg_mentions`,
  `onions`, `md5`, `sha1`, `ransomware_victims`; `_store_iocs`'s `type_map` never listed them, so
  none were ever written. Identical to the documented `cves` defect. Added `tg_handle`, `onion`,
  `hash_md5`, `hash_sha1`.
  **`tg_handle` is the scam-operator-handle category** — highest uniqueness available, because feeds
  publish infrastructure, not people. **It is a lead list, not a verdict**: `_RE_TG_CHANNEL` matches
  any `@mention`. Do not export it as "known scam operators" without filtering.
* **95 vs 122 explained.** Nothing ever set `active` back to `False`; an unreachable channel was
  skipped with a bare `continue` and counted as healthy forever. Now `consecutive_failures` /
  `last_error` are recorded, cleared on recovery, and the digest reads
  `Channels checked: 95 of 122 active ⚠️ 27 unreachable`. **Nothing auto-deactivates** — a private
  channel can come back. **Fields are empty until the patched monitor has run**; an all-zero column
  proves nothing yet.
* **Supplier-breach watch built.** Own table, `confidence: "unverified"`, **opt-in only** via an
  explicit `supplier_watchlist`. Exact normalised-key matching (substring matching gives "co" inside
  "cisco"), keys generated with and without corporate suffix. Alert copy is deliberately *not* the
  IOC copy: you are not compromised, rotate the credentials **you issued to them**, expect invoice
  fraud, confirm before treating as fact.
  *Testing caught a 4-char key floor that silently dropped every three-letter supplier (IBM, SAP,
  AWS). Lowered to 3; bare suffixes excluded by name.*

**Not done:** the 75 `pending_review` channels. Needs AWS, so run
`tools/triage_channels.py --pending` on the Mac (read-only unless `--apply`).

### 4. Zapier — nothing possible until 1 September

Publishing the weekly change was refused at **103/100 tasks**: Zapier will not turn a Zap *on* while
over quota, and publishing an edit is turning it on. **Turning them off does not work either**
(founder tested). Tasks do not decrease, so the cycle must reset.

**Partner Sandbox granted** — Integration ID **243026**, `relayshieldadmin@gmail.com`, **2,000
tasks/month**. It is a **separate workspace** and forbids production data, so it does **not** lift
the production cap and the 12 Zaps do not move there. It is where new template work belongs.

Full steps: `zapier_weekly_cadence_runbook.md`.

### 5. Gaming/DeFi outreach — DFK ready to send

`gaming_prediction_markets_focus_list_20260814.md` is now in the repo (was laptop-only).

**DeFi Kingdoms: pitch the Discord bot, not rsscan.** The bot serves 55.6K players and has a
partnership shape; rsscan is free/MIT with nothing to negotiate — one line for their engineers.
**Partner channel first** (that standing is why the size band was overridden), BizDev form
`https://forms.gle/fv4y1G3ppNgJDpEDA` as fallback. Draft message is in the file.
**Clear `#✅verify` first** — that gate is why no channels were visible, not a dead server.

**Ronin gap to fix before pitching Lumiterra or The Machines Arena:** Ronin is EVM and CS Mobile's
generic `evm` type accepts it, but the legacy `ronin:` address prefix is rejected by the bot's
`^0x` regex. One-line normalise. DFK itself is unaffected (DFK Chain uses plain `0x`).

**Headwind:** DeFi protocols are leaving Discord in 2026 (Morpho read-only Feb 1, DefiLlama
ticketed support). Games are stickier, but name it and turn it — teams flee because they cannot
screen what gets posted, which is what the bot does.

**Do not open a DeFi-protocol candidate list.** Same dead end as prediction markets.

### 6. Victim-side outreach — TABLED

Segment 1 (Merkle Science, TRM, Chainalysis, Elliptic) is tabled: the majority of ~511K indicators
come from ingested third-party feeds, so we would be selling analytics firms feeds they already
ingest. **Gated on exclusive-indicator volume, not on copy.** Growing that corpus is the work.

### 7. Carried forward, untouched

XSOAR PR #45206 Tech Alliance reply (gate: 2 named joint customers — ask Arjen, do not invent);
BTV replies; Bundle A on a new AWS entity; bundle-subscriber usage counter; SentinelOne registration;
Twilio balance $5.00; `coinbase/agentkit#1449`; Ansible Galaxy namespace; 9 em-dashes on
`/developers`; **push rsscan 0.2.x from the laptop**; delete stale `ci/v3-package` branch on the fork.

---

## ToDo list for tomorrow, in order

1. **Create `relayshield_ransomware_victims` + check the Lambda role's `PutItem`.** Blocks #4 below.
2. **Try the faithful restore** of the Telegram code (Mac working tree / stash / reflog first).
   Then tell me which other commands were pruned originally so they can be re-folded in one pass.
3. **Triage the 75 pending channels** — `tools/triage_channels.py --pending`, then `--activate … --apply`.
4. **Ransomware-victim monitoring in the TI demo — target Saturday.** Wire into the existing
   `/demo/*` gating (secrets-gated since `b7955fe`), do not add an ungated route. Needs the table
   populated by at least one intel run.
5. **Competitive benchmarking vs SOCRadar** — coverage, collection surface, pricing/packaging,
   integrations (Sentinel, XSOAR, MISP/STIX-TAXII, MCP). **Build it on `measured_exclusive_share`
   per category, never the 511K headline** — a benchmark resting on that number fails the same way
   the Segment 1 outreach nearly did, and it fails in front of a competitor's customers.
6. **New Zapier template in the Sandbox** to seed the flywheel. **Must not be one of the existing 12.**
   Slack first (biggest directory, clearest one-line value). Measure installs, not tasks.
7. **DFK outreach** — partner channel, then BizDev form.
8. **Ronin `ronin:` prefix normalise** before any Ronin-game pitch.
9. **1 SEPTEMBER: push the weekly change to all 12 Zaps.** Spread across weekdays.
10. Build the pivot enrichment and "re-check unknowns on delay" items in `intel_corpus_growth_plan.md`
    — the second one turns the consumer bots into a collection channel and produces a provable
    "we saw it first" claim.

Also queued, small: a test that fails when `extract_iocs()` and `_store_iocs`'s `type_map` diverge
(it has broken silently twice), and a decision on the `check_url` duplication between the Telegram
and Discord bots that `relayshield_discord_bot.py`'s own docstring flags as a drift risk.

---

## ENVIRONMENT — read before running anything

**AWS account: `239677749008`.** A command run without `AWS_PROFILE=relayshield` resolved to
`620534471984` and returned `ResourceNotFoundException`, which looked like a missing Lambda and was
not. **Prefix every AWS command with `AWS_PROFILE=relayshield`** and sanity-check with
`aws sts get-caller-identity`.

**macOS zsh does not treat `#` as a comment interactively.** `aws sts get-caller-identity # expect …`
became arguments and errored. **Never append a comment to a command handed to the founder.** (Second
occurrence; it is in the 08-19 file too.)

**Blocked by sandbox egress** (403 on CONNECT; report, do not route around): `discord.com` (so no
invite code can be resolved here), all `zapier.com` domains, `catalogapi.azure.com`,
`www.powershellgallery.com`, `docs.zapier.com`, arbitrary vendor sites. Reachable: GitHub,
`raw.githubusercontent.com`, PyPI, `api.nuget.org`, `packages.microsoft.com`.

**No AWS credentials in this session.** Anything touching DynamoDB or Lambda runs on the Mac.

**`deploy_lambdas.yml` detects changes with `git diff --name-only HEAD~1 HEAD`.** Merge with
`--no-ff` or a docs-only commit on top means **nothing deploys**.

**The CI import probe invokes the function.** `relayshield_intel_monitor.py` now returns early on
`{"source":"ci.import-probe"}` **before `_acquire_lock()`** — without that guard, every deploy would
have started a full Telegram sweep and risked a flood-wait inherited by the next scheduled run. Any
future Lambda added to CI needs the same consideration.

**`~/Side SaaS Hustle` IS the local clone.** Reconcile with
`git -c pull.rebase=false pull origin main`, never rebase.

**Sandbox has no `boto3` and no PowerShell.** `tools/triage_channels.py` and the arm-ttk port are
written to run on the Mac; use the throwaway venv
(`python3 -m venv /tmp/rsvenv && /tmp/rsvenv/bin/pip install boto3`) because Homebrew Python is
PEP 668 externally-managed.

**Watch on the next real intel run:** `relayshield_intel_monitor.py` imports
`relayshield_siem_connector`. The workflow resolves local imports and that file is in the path list,
so the zip should carry both — but the import probe would not catch a missing local module unless it
is imported at module level. Glance at the first scheduled run's logs.
