<!-- Verbatim sections moved out of CLAUDE.md on 2026-10-18, original order. Not auto-loaded.
     Find one with: grep -n 'WORDS' docs/claude_memory/INDEX.md -->

## WHERE 2026-09-03 LEFT THINGS — read this first

### THE LIST FOR THE NEXT SESSION, in order (10 items)

Written at the end of 2026-09-03. Everything above item 1 that used to be on the 2026-09-02 list is
either done or has moved into these.

1. **Stripe machine payments: probe, then build ONE endpoint.** The email to Jake is SENT with the
   four questions. The next move does not wait on his reply: run
   `tools/stripe_machine_payments_probe.py` (read-only) to learn whether the account can call the
   x402 surface at all. Enabled means build one endpoint settling to Stripe alongside the existing
   PayAI rail, which is the artefact their team responds to. Not enabled means that error text is a
   better follow-up to Jake than a second nudge. **Settlement question answered: stablecoin payments
   settle into the Stripe balance in USD, on the normal payout schedule.** Crypto in, dollars out,
   same balance as the subscriptions.
2. **Send the twelve.** `outreach_bot_prospects_curated.md` is written and hand-picked: five real
   inboxes first, then the seven websites where the page has to carry a form. Track replies per 100
   by channel. `TegroTON/ai-telegram-pay-miniapp` is the one worth the most care.
3. **Apify article: submit to `#apify-writers` at the next quarterly call.** Draft is
   `blog-apify-actor-as-agent-tool.md`. Three facts to confirm with the console open first, listed
   in its own NOT FOR PUBLICATION section. **It must not appear on blog.relayshield.net first:**
   originality is a programme rule and publishing early disqualifies it.
4. **FD-8, FD-9 and FD-10 in one publish.** `tools/fd8_prepare_republish.py --dir ~/mcp-live
   --write` makes all the edits, including the `?source=pypi` link in pyproject.toml, and refuses
   to invent the publish command. Then FD-11: submit the Smithery LISTING, decline hosting.
5. **Build `agent-bait-scan`.** Recommended, 3.5 days, scoped in `agent_baiting_scope.md`. Island's
   research names a gap our catalogue genuinely has: we screen the name and the domain, and nothing
   of ours reads the INSTRUCTIONS an agent is given. The differentiator is signal 4, joining those
   instructions to the criminal corpus, which nobody replicating this can do.
6. **Mini App v1**, then the channel submissions. The discovery list is measured and waiting:
   `@trendingapps` (3.9M, and `@twa_apps` is the SAME channel), `@web3telegrambotx` (72,742),
   `@findminiapp` (56,380), `@onclicka_tma_en` (33,723), `@telegtapps` (9,671). Each gives one first
   impression and we spend it by submitting before the Mini App exists.
7. **Measure the widget.** It is live and keyless. The number that matters is installs making a
   SECOND day of calls, not total calls, and `source=tg-widget` is on every request.
8. **`relayshield-agentic-api` drift.** Still recovered-but-unreconciled on
   `claude/recovered-live-relayshield-agentic-api`. Live carries a branded API_BASE_URL and a Bundle
   D Stripe branch main does not. Same shape as the developer-signup recovery that worked.
9. **INTEL-5 funnel.** `tools/diagnose_stolen_sessions.py` on the Mac. Until it runs, no count out
   of `relayshield_stolen_sessions` means anything about the criminal market.
10. **XSOAR.** Nothing to do. `xsoar_pack_watch.yml` runs daily and opens an issue the day the pack
    lands on master. Checked 2026-09-03: still not on master.

### What this session shipped

- **The Discord footer is live**, after the drift diff was read, the function mapped, and run 134's
  red probe understood as a denied `lambda:InvokeFunction` rather than a failed deploy.
- **`relayshield_developer_signup.py` recovered and reconciled** — 700 live-only lines including two
  Stripe revenue doors — then mapped in the deployer, in that order.
- **The Telegram widget**, keyless end to end, with `/v1/link-check` new and the gateway route live.
- **The prospecting pipeline**, now with contact hygiene that screens README examples out of both
  the extractor and the generator.
- **Attribution keys** for `tg-widget` and `pypi`, both registered BEFORE the links that use them.



### The founder could not see the Discord email-check footer. The diagnosis in the room was wrong.

It was reported as "not merged to main yet". **It is on main** — commit `4a688e8`, merged, and
`EMAIL_CHECK_FOOTER` is concatenated onto the `/scan` reply in `relayshield_discord_bot.py`. Merging
changed nothing, because **`relayshield_discord_bot.py` is in the deploy map of nothing.** No edit
to that file has ever shipped automatically. Main being right and live being wrong is the normal
state for this function, not an anomaly, and it stays that way until the function gets a deploy
path.

Worth keeping as a general correction: "it is not merged" and "it is not deployed" produce the
identical symptom, and only one of them is fixed by merging. Check which before promising a merge
will fix it.

### The drift check has still never run with the Discord bot in it

Two separate reasons, both now closed:

- The entry was added in `6a2bae7` at 00:56 on 2026-09-03. The last run that actually executed is
  **run 14, the scheduled run of 2026-09-02 16:56**, which predates it. The next scheduled run is
  13:00 UTC.
- Runs **15 to 24 are not drift runs at all.** They are `push`-event runs with **zero jobs** — the
  invalid-workflow failures from the YAML break that `9c87348` fixed. The workflow only triggers on
  `schedule` and `workflow_dispatch`, so a valid file produces NO run on a push. That is the useful
  tell: since `9c87348`, three pushes have produced no run at all, which is the positive evidence
  the file parses again.

### The Discord diff was read, and it was case 2: live was merely stale

`sh tools/discord_bot_drift.sh` ran on the Mac at 07:20. Findings, in the order
they matter:

- The function name **`relayshield-discord-bot` is CORRECT** — resolved against AWS in
  239677749008, python3.14, `CodeSize` 10021, **`LastModified` 2026-08-13T15:25**. Three weeks
  untouched, which is what "no deploy path" looks like from the AWS side.
- The live handler is **byte-identical to `relayshield_discord_bot.py` as of `0c429e0`**, missing
  exactly one commit: `4a688e8`, the email-check footer. Nothing live-only. **Nothing to recover.**
- No other `relayshield_*.py` in the package at all, so no shared-module drift either.

So the footer was never a merge problem and never a recovery problem. It was a function with no
deploy path, and it now has one: `relayshield_discord_bot.py` is in `deploy_lambdas.yml` — the
`paths:` trigger, `LAMBDA_MAP`, and the manual-dispatch list. No import-probe early return is
needed; the probe payload falls through the deferred branch, finds no Discord signature headers and
returns 401, which is a real response and all the probe asserts.

**The trap in mapping it, which nearly wasted the whole fix:** the deployer ships a function only
when the PUSH changed its source. A push that maps a function while touching only workflow files
deploys nothing. That is why the commit that maps it also writes the deploy path into the handler's
own docstring — the push has to touch the `.py`.

### The drift script's first verdict was WRONG, and the lesson generalises

It printed RECOVER FIRST on a function that needed nothing of the sort. It classified by **counting
diff lines** — any `+` line meant live carried something main did not — and **a modified line
produces a `+` and a `-` both**. The single `+` was `"content": rendered["text"] + UPSELL_FOOTER,`:
main's own line as it stood one commit earlier.

The fix is not a better heuristic, it is an exact question, and git can answer it directly: **is the
live file byte-identical to some commit's version of this file?** Yes means every byte is already
committed and there is nothing to recover, whatever shape the diff has. No means live holds content
no commit ever held, which is hand-deployed work. The script now walks `git log -- <file>` and says
which commit live matches and which commits it is missing.

Worth carrying to the next drift diff of any kind: **a diff's shape does not tell you which
direction drift runs. Matching a committed version does.**

### Run 134 was RED and the deploy SUCCEEDED. Read which step failed.

The merge shipped it. The log says so:

    → Packaging relayshield_discord_bot.py → relayshield-discord-bot
    ✅ relayshield-discord-bot deployed

What went red is the step AFTER it, the import probe:

    AccessDeniedException ... relayshield-github-deploy is not authorized to
    perform: lambda:InvokeFunction on ... function:relayshield-discord-bot

**`deploy_lambdas.yml` invokes what it deploys, and that grant is an EXPLICIT ARN LIST** in
`iam_github_deploy_invoke.json` — 22 functions, applied by hand on 2026-08-30, with nothing checking
it against `LAMBDA_MAP`. So mapping a 23rd function guaranteed a red run on its first deploy, and
the failure looks exactly like a broken deploy while being the opposite: the code is live and only
the verification was refused.

Two files that must agree with nothing checking that they do — the same shape as the four pattern
tables. Now closed three ways:

- **`tools/check_deploy_invoke_policy.py`** parses `LAMBDA_MAP` out of the deployer and fails if any
  function is missing from the policy file. `--write` adds them.
- **`test_workflows_parse.py` runs it**, because that is already the command this repo runs after
  every workflow edit. A workflow that parses can still be guaranteed to fail.
- **`tools/apply_deploy_invoke_policy.sh`** pushes the file to AWS, which the repo half does not do
  on its own. It LOOKS for where the policy lives (inline, then attached managed, matching on the
  Sid) rather than assuming, because 2026-08-30 recorded no location, and it proves the result with
  `simulate-principal-policy` against the ROLE — invoking from the operator's own shell would test
  the wrong identity entirely.
- The probe's error now says outright that the function was deployed and names the two commands.

**The general form: a red run names a step, not an outcome.** "The deploy failed" and "the check
after the deploy failed" are different facts with different fixes, and the second one costs nothing
if it is read correctly and a rollback if it is not.

### The widget shipped, and the cheap half was already built

`telegram_widget_scope.md` has the whole thing. The three findings worth carrying:

- **The prospect list is bot REPOSITORIES, not websites**, so a `<script>` embed is the wrong
  artefact for almost every prospect on it. v1 is a file you copy into your bot.
- **`/v1/wallet-risk` has been KEYLESS since Crypto Shield Mobile**, capped per source IP, so the
  address half of the widget needed no new product decision at all.
- **`/v1/scan-url` was the wrong shape and the new `/v1/link-check` is the right one.** VirusTotal
  submits and then needs polling, which a Telegram handler cannot do, and costs money per call,
  which is why it needs a key. The new endpoint returns the three signals that are immediate and
  free: IOC corpus, Safe Browsing, RDAP age. Keyless for the same reason the wallet ones are.

Two rules are pinned by 39 offline tests rather than by intent: **it never throws** (every failure
is `ok=false, level="unknown"`) and **it never says "safe"** (a heuristic pass is an absence of
evidence, and the ceiling is "nothing known against it"). Both exist because this code runs inside
someone else's product, in front of users who never chose us.

**`relayshield_developer_signup.py` is the SIXTH handler with source in the repo, live traffic and
no deploy path** — found while registering the `tg-widget` key in its `_SOURCE_BANNERS` table. It
serves api.relayshield.net/developers: pricing, the signup form, free-tier key issue, every landing
banner. So a registered attribution key reached nobody until that function deployed. **Its first
diff was read, recovered and reconciled the same day — see the section above. It is now in
`deploy_lambdas.yml`, and `iam_github_deploy_invoke.json` gained it too, so its first CI deploy does
not repeat run 134's denied probe.**

### relayshield_developer_signup.py IS THE 2026-08-17 CASE AGAIN, and this time the code takes money

The sixth handler's first drift diff was read the same day it was added, and it is not the stale
case. **Live holds roughly 700 lines that NO COMMIT OF THAT FILE HAS EVER HELD.** `handler_drift.sh`
settled it exactly rather than by counting: no version in `git log -- relayshield_developer_signup.py`
is byte-identical to the live file.

What is live and not in git, in the order it would hurt to lose:

- **The Bundle A and Bundle D direct-Stripe doors**, ~400 lines: `handle_bundle_checkout`, the
  `/developer/bundle-checkout` route, provisioning and revocation for both bundles, and both key
  emails. This is a second revenue path for products otherwise sold only on AWS Marketplace.
- **`_get_subscription_price_ids`.** A bundle subscription carries TWO Stripe items and Stripe does
  not guarantee order, so the old `items[0]` read was a coin flip: when the metered price came back
  first the bundle branch never fired and the customer was charged $150 or $299 a month and handed
  an ordinary pay-as-you-go key. Live has the fix. Main has the coin flip.
- **The `_find_key_by_customer` projection fix.** The AWS-disintermediation guards read
  `aws_license_arn` and `bundle_?_access`; a projection that omits them does not raise, it returns
  None, so both guards silently evaluate false. Live projects them. Main does not.
- **`_strip_html_comments`**, which stops engineering notes shipping to public View Source. One of
  them recorded a third party's rejection of our work.
- **The mobile media query**, the fix for the signup CTA overflowing its box on a phone. That button
  is the primary conversion action on the page.
- **`FREE_TIER_CALLS = 100`.** Main still says 20, while main's own `relayshield_api.py` says
  `FREE_TIER_CALLS_LABEL = 100`. The two halves of the free tier disagree in main and agree in live.
- **Eight source banners** main has never seen: `discord-bot`, `npm-worm`, `fourth-party`,
  `ansible-galaxy`, `bluenoroff`, `rsscan`, `rsscan-deps`, `metamask-snap`, with their alias tables.
  Note that `rsscan` has its OWN banner live, where main still aliases it to `github`.
- Corrected corpus figures throughout: 494K distinct indicators, 5.8M sightings, 95 channels, where
  main still says 5.0M IOCs and 85 channels.

**IT WAS SAFE ONLY BECAUSE THE FUNCTION WAS IN NO DEPLOY MAP.** Until the reconcile below landed,
adding it to `deploy_lambdas.yml` would have deleted all of the above on the next merge with no
error anywhere. That order — recover, reconcile, only then map — is the whole rule.

**RECOVERED AND RECONCILED THE SAME DAY.** `recover_live_handler.yml` pushed the live package to
`claude/recovered-live-relayshield-developer-signup` (`dfe60a2`), and it is now on main as two
commits, deliberately not one:

1. `93310e3` — the live bytes, verbatim, at the handler's own path. A pure move, no edits.
2. `4690b85` — the three registrations main had and live did not: `apify` (2026-08-27),
   `mcp-registry` (2026-09-02), `tg-widget` (2026-09-03), re-applied verbatim.

**Splitting it in two is what makes the result checkable.** Live is byte-identical to `93310e3` and
missing exactly `4690b85`, which is the ordinary stale case, so the function could finally be mapped
in `deploy_lambdas.yml`. One squashed commit would have left live matching nothing and the drift
check crying wolf forever.

**One thing from main was deliberately dropped: the alias `"rsscan" -> "github"`.** Live gives
`rsscan` its own banner and removes that alias, and `_resolve_source` applies aliases BEFORE the
banner table, so with the alias in place rsscan's own banner is unreachable. A key that exists,
resolves, and renders the wrong thing is worse than a missing key, because nothing looks broken.

The reconcile was verified structurally rather than by eye: comparing the two files' top-level
symbols and both attribution tables showed 15 live-only symbols, 8 live-only banners and 42
live-only aliases, all preserved, and exactly 3 banners plus 5 aliases re-added.
`test_developer_signup_banners.py` now pins those invariants with `ast` and no boto3.

**The general form, for the third time: a handler with source in the repo, live traffic and no
deploy path accumulates hand-deployed work silently, and the longer it goes unread the more
expensive the diff.** This one went unread from 2026-08-17 to 2026-09-03 and grew a billing path.

### The tg-widget banner is not missing. It is a per-arrival banner.

Asked on 2026-09-03 after all three runs went green: "I do not see the tg-widget banner on
api.relayshield.net/developers." It is not supposed to be there.

`_SOURCE_BANNERS` entries render into the `<!--REFERRER_BANNER-->` placeholder, which sits directly
under the nav and above the hero, and ONLY when the arrival carries `?source=`/`?src=` or a matching
Referer host. `tg-widget` deliberately claims no referer hosts, so the parameter is the only way in.
The bare `/developers` URL will never show it, by design.

    https://api.relayshield.net/developers?source=tg-widget

That is also the check: `curl -sS "…?source=tg-widget" | grep -c "Arriving from a Telegram bot"`
returns 1 when it is live, and the same command on the bare URL returns 0.

### MINI APP DISCOVERY — the ranking, decided 2026-09-03

Recorded here because the founder asked for it to be, and because the first version of this ranking
was wrong in a way that is easy to repeat.

**Re-ranked: blog channel first, then Mini App announcement channels, then directories, then
attributed deep links, with the menu button fifth because it is cheap rather than because it reaches
anyone.**

The error worth not repeating: the menu button on `@relayshield_bot` is the top lever for a bot with
an audience, and ours has a tiny number of users, so a Mini App hung off it inherits a tiny number of
users. **Rank a surface by how it performs for US, not by how it performs in general.** Reasoning and
the full list are in `miniapp_discovery_and_stripe_choice.md` §2.

**Four channels measured on the prospecting account** by `tools/find_miniapp_channels.py`:
`@swoptoky_news` (205,055, Cyrillic), `@web3telegrambotx` (72,742), `@findminiapp` (56,380),
`@telegtapps` (9,673). Three are usable; the Cyrillic one needs a Russian-language submission or a
skip, which is what `--latin-only` and the new `script` column are for.

**SEQUENCING, and it decides when any of this happens: WE DO NOT HAVE A MINI APP YET.** These
channels announce Mini Apps, and each will give us exactly one first impression. Submitting before
the thing exists spends it. The list is the target for the day v1 ships.

### Two things this session got wrong, and the founder caught both

**I claimed the MetaMask Snap was a live surface. It is not.** The integration request was submitted
and there has been no response. The repo already recorded that in three places
(`victim_side_outreach_messages.md`, `xcitium_outreach.md`, `NEXT_SESSION_2026-08-19.md`), and I
wrote "we already have the plugin-shaped surface that matters" without checking any of them. That is
CLAUDE.md's own rule broken by CLAUDE.md's own author: **a doc claiming something is done is a lead,
not a fact.** A `metamask-snap` key exists in `_SOURCE_BANNERS`, registered before shipping exactly
as the rule requires, and a registered key is not a live integration.

**I ranked the bot's menu button as the top Mini App discovery lever.** The bot has a tiny number of
users, so a Mini App hung off it inherits a tiny number of users. The ranking was right in general
and wrong for us, which is how a plan ends up describing somebody else's company. Re-ranked in
`miniapp_discovery_and_stripe_choice.md`: the Telegram blog channel first, then Mini App announcement
channels, then directories, then attributed deep links, and the menu button fifth because it costs
almost nothing rather than because it reaches anyone.

### The first real prospect sweep was mostly unusable, and it was the extractor

216 rows, and the top 25 included `root@203.0.113.4` (an RFC 5737 documentation IP),
`trial@telegram.bot`, `k7m2q9x1a3@yourdomain.com`, a YouTube demo link and several `t.me` links, all
counted as reachable contacts. `contacts_from` filtered exactly one thing, `example.com`.

That is not cosmetic. **Contactability is 20 of the 100 score points**, so the ranking was partly
measuring bad extraction, and mailing a documentation example is how a sending domain earns a spam
reputation. `tools/contact_hygiene.py` now screens both fields, in the extractor AND again in the
generator, because a `prospects_wide.jsonl` produced before the fix still holds those rows and the
generator is the last thing standing before a message goes out. Seven tests, every case taken from
that sweep.

**Also re-run it with `--stars 5..50`.** Without the flag the sweep spends its whole `--limit` inside
`stars:0..1`, which is why the results were dominated by brand-new repos: the script's own docstring
says so and the run log shows the single `stars:0..1` line.

### FD-8 re-publish now closes three things, not one

Checked live against the registry API on 2026-09-03, rather than from the doc:

- `websiteUrl` on the latest version is still the bare `https://relayshield.net`. The defect is real
  and current.
- **The registry is TWO VERSIONS BEHIND PyPI.** Registry latest is 0.2.7 (2026-07-19); PyPI is on
  0.2.9. Whatever 0.2.8 and 0.2.9 changed has never reached the canonical directory.
- `repository.url` says `github.com/relayshield/relayshield-mcp` on every published version, and
  Glama's listing path mirrors it, so if that repo does not exist the mismatch is a broken link on
  two live surfaces rather than a cosmetic oddity.

So the single `mcp-publisher` re-publish fixes the attribution key, the version lag and the
repository URL together. Do all three in one version rather than three.

### The Apify Actor exists, and the session that could not find it was the one that was wrong

`relayshieldadmin/relayshield-security-tools` is public on Apify Store, pay per usage, 154 runs, an
MCP server over Streamable HTTP. `_APIFY_BANNER` was accurate all along. Two lessons, and the second
is the useful one:

- **Absence of evidence from a blocked container is not evidence of absence.** apify.com is egress
  blocked here and a web search found nothing, and the honest conclusion was "unresolved", which is
  what was recorded. Had it been recorded as "the Actor does not exist", the next session would have
  deleted a true claim from a live page.
- **The Actor's Dockerfile carries the best technical story we have written down this quarter**, and
  it was invisible to this repo because the Actor's source lives on Apify rather than here. Worth
  asking what else is like that.

### The developers page now points AT Apify, not just away from it

`_APIFY_BANNER` handles arrivals FROM Apify. Nothing on the page mentioned the Actor, so the only
way to find it was to already be on Apify. Added as a card in the SDK grid, linking the Store
listing, with no run count on it: numbers on a landing page are a maintenance burden and the listing
carries the real one.

### Changed 2026-09-03

- **`tools/discord_bot_drift.sh`** — read-only, runs on the Mac, needs no waiting for 13:00 UTC. It
  asserts account 239677749008, **resolves the Discord function's real name from AWS instead of
  trusting the map**, downloads the live package, diffs the handler AND every shared
  `relayshield_*.py` in it, and classifies the result the only way that matters: lines present in
  LIVE and not in main mean hand-deployed work that is RECOVERED first; only main's own commits
  missing means live is merely stale and the function can be mapped in `deploy_lambdas.yml`.
- **`relayshield_discord_bot.py` now has a deploy path** — `deploy_lambdas.yml`, after the diff
  above was read. It stays in the drift check too: having a deploy path is not the same as never
  being hand-deployed again.
- **`tools/handler_drift.sh`** — the Discord drift script, generalised, because a sixth handler
  needed the same three questions the same day. `tools/discord_bot_drift.sh` is now a wrapper, so
  every reference to it in this file and in the workflow comments still works.
- **`xsoar_pack_watch.yml`** — the XSOAR gate is watched daily instead of remembered.
- **`outreach_bot_prospects_curated.md`** — the twelve worth sending first, hand-picked from the
  generated 40, each with the contact, the rationale, and a message written to that prospect rather
  than to its tag. Includes the three that are deliberately NOT on it and why.
- **`tools/stripe_machine_payments_probe.py`** — read-only. Answers "is this account enabled for
  machine payments" before anybody writes an endpoint against it.
- **`tools/fd8_prepare_republish.py`** — makes the server.json edits for FD-8, FD-9 and FD-10 and
  refuses to invent a publish command: it greps the repo's own README for the one that already
  works.
- **`agent_baiting_scope.md`** — what Island's AgentBaiting research means for us, what
  `mcp-registry-risk` already covers, and the one endpoint worth building.
- **`blog-apify-actor-as-agent-tool.md`** — the Apify content-programme draft.
- **`tools/generate_outreach.py`** + `test_generate_outreach.py` — item 2's generator, and the ten
  tests that stop a draft ever diagnosing a prospect.
- **`miniapp_discovery_and_stripe_choice.md`** — why the widget must not carry a Mini App link, what
  actually drives Mini App discovery, why a browser extension is not the play, which Stripe agentic
  product to select, and the four questions to put to Jake while access is in review.
- **`tools/contact_hygiene.py`** + `test_contact_hygiene.py` — the screen that stops a README
  example becoming an outreach recipient. Wired into both the prospector and the generator.
- **`tools/find_miniapp_channels.py`** — searches for channels that announce new Mini Apps and
  reports measured member counts, ON THE PROSPECTING SESSION. Now also takes SEED_CHANNELS
  (`@trendingapps`, `@twa_apps`, and `@tapps_bot` as the submission route the first names in its own
  description), because search does not reach everything and a channel a human named should be
  measured rather than argued about. It refuses to run against
  `relayshield/telethon_session` at all: 99 channels of collection depend on that account, and a
  prospecting sweep is how it gets flood-limited.
- **`iam_github_deploy_invoke.json` gained `relayshield-discord-bot`**, plus the checker, the
  applier and the validator wiring described above.
- **An unreadable function now fails the drift run.** It previously emitted a `::warning::` inside
  an otherwise green run, so a wrong name in the map was indistinguishable from a clean check —
  the quiet-alarm failure again, and the Discord entry's name is exactly the case that would have
  hit it. `UNREADABLE` is tracked separately from `DRIFTED`, so it reddens the run without opening
  a `lambda-drift` issue about drift that was never measured.

## WHERE 2026-09-02 LEFT THINGS — read this first

### THE LIST FOR THE NEXT SESSION, in order (11 items)

1. **Scope and build the widget. BUILT 2026-09-03 — see `telegram_widget_scope.md`.** v1 is a
   copy-in file rather than a `<script>` embed, because the prospect list is bot REPOSITORIES and a
   bot is not a web page. `POST /v1/link-check` is new and KEYLESS: IOC corpus, Safe Browsing and
   domain age, no VirusTotal, so no marginal cost and no signup before the first call. The wallet
   half needed nothing new, because `/v1/wallet-risk` has been keyless since Crypto Shield Mobile.
   Clients in Python and JavaScript, 39 offline tests, `tg-widget` registered in `_SOURCE_BANNERS`
   first. **Not live until two more steps: the merge deploys the API, then
   `sh tools/create_link_check_endpoint.sh` adds the gateway route.** The original entry follows.
   An embeddable
   "check this link / check this address" widget for third-party Telegram bots and Mini Apps. The
   prospect list exists: `prospects_wide.jsonl`, 206 rows at `stars:5..50`, **109 with a website or
   an email**, and 19 of the top 25 tagged `wallets` or `payments` — bots already handling other
   people's money. **Register the `source=` keys in `_SOURCE_BANNERS` BEFORE any widget ships**;
   FD-8 below is what happens when that is skipped.
2. **Tailored outreach to the 109. THE GENERATOR IS BUILT, 2026-09-03: `tools/generate_outreach.py`.**
   It reads `prospects_wide.jsonl` and writes `outreach_bot_prospects.md`: one draft per prospect
   keyed on the capability their own README asserts, the contact channel, the evidence line the
   draft rests on, and a tracking table. **It cannot run in a container** — the prospect file is
   generated output and lives on the Mac. Ten tests pin the rule that matters: the drafts never
   assert anything about a prospect's security, because we can read a README and cannot see anyone's
   backend, and "we analysed your app and found exposures" from an unknown security vendor is one
   word away from an extortion email. Original entry follows. Founder wants it; agreed approach is a
   GENERATED DRAFT PER PROSPECT that he reviews and sends, keyed on what each repo actually does.
   Not mass mail: volume is not the lever, relevance is, and blasting maintainers who never asked is
   how a domain gets blocked.
3. **Apify post. UNBLOCKED 2026-09-03: THE ACTOR EXISTS AND THE DRAFT IS WRITTEN.**
   `relayshieldadmin/relayshield-security-tools`, public, pay-per-usage, an MCP server over
   Streamable HTTP in Standby mode, 154 runs, last build 0.1.7. So the banner was true and the
   session that could not find it was wrong, which is the right way round for once.
   `blog-apify-actor-as-agent-tool.md` is the draft: ~1,300 publishable words on why Standby rather
   than run-per-request, and the dependency conflict that crash-looped every real run
   (`apify>=2,<3` pulls a Crawlee whose `HttpHeaders` model dies against the Pydantic FastMCP
   needs, with "cannot specify both default and default_factory" at import time; `apify>=4,<5`
   fixes it by going FORWARD, not back). **Its NOT FOR PUBLICATION section carries the three facts
   to verify with the console open before submitting, and the one rule that would disqualify it:
   originality, so it must NOT go on blog.relayshield.net first.** That inverts our usual
   canonical-first order. Original entry follows. **BLOCKED ON A QUESTION NOBODY HAD ASKED:
   DOES OUR APIFY ACTOR EXIST?** The programme's own rule is that articles are "written by
   developers who've actually built the thing they're writing about", 1,000 to 5,000 words,
   original, submitted through their Discord, $500 on publication. Both halves of the theme
   ("Actors that plug into your stack", "your Actor as a tool for AI agents") require an Actor.
   **`_APIFY_BANNER` on the live developers page asserts one exists** — "The RelayShield actor runs
   breach, infostealer and SIM-swap checks as an Apify task" — and 2026-09-03 could find no
   evidence of it: no Actor code anywhere in this repo, and no store listing in a web search.
   apify.com is blocked from the container, so this is UNRESOLVED rather than disproved. It is the
   same shape as the MetaMask Snap claim, on a live page, and it gates the post either way. The
   July call closed 2026-08-16 and it is QUARTERLY, so there is time to settle it. Also **put
   dev.to back in the channel order** — it is missing entirely and costs nothing.
4. **Stripe MPP follow-up with Jake Lamoine.** Open question carried: does x402 settlement count
   toward early-adopter status. Card via SPT minimum is $0.50, stablecoin $0.01 USDC, and the sample
   uses `scheme: "exact"` on Base — identical to our 28 live x402 endpoints.
   **DECIDED 2026-09-03, of the four cards in the Agentic Commerce console: select ACCEPT MACHINE
   PAYMENTS.** It is the productised version of the rail we already run. Retail is a product
   catalogue and we have no SKUs; the agent wallet is spend control on the BUY side and we are the
   sell side; Projects is infrastructure we have. Reasoning, including why the agent wallet is the
   pitch TO Stripe rather than a fit for us, is in `miniapp_discovery_and_stripe_choice.md`.
5. **Aduna — Reggie Daniels.** Founder's former colleague works there and will text him. Outreach
   messaging is written in `aduna_outreach.md`.
6. **FD-8 finish — official MCP registry attribution. ONE EDIT, ONE PUBLISH.**
   `registry.modelcontextprotocol.io` has carried RelayShield since 2026-05-10 (six versions, latest
   0.2.7, status active) with a bare `https://relayshield.net` as its `websiteUrl` — so four months
   of arrivals from the canonical MCP directory logged `unmatched:` and rendered no banner. The
   `mcp-registry` key is now registered in `_SOURCE_BANNERS`, so the only remaining steps are:
   change `websiteUrl` in `~/mcp-live/server.json` to `https://relayshield.net?source=mcp-registry`,
   then re-publish with `mcp-publisher` (the registry is versioned, so this is a new version, not an
   edit — read that repo's README for the established command rather than inventing one). While
   there: the record's `repository.url` says `github.com/relayshield/...` while the namespace is
   `io.github.nzdsf2-gif/`. Probably harmless, worth a look.
7. **FD-9 — VERIFIED 2026-09-03: WE ARE LISTED.** `glama.ai/mcp/servers/relayshield/relayshield-mcp`,
   found by web search because glama.ai is still egress-blocked here. The listing path is
   `relayshield/…`, matching the registry's `repository.url`, so Glama indexed from there — which
   turns the "probably harmless" owner mismatch in item 6 into a possible broken link on a live
   listing. **Two more doors found the same day:** PyPI's project page links to the developers page
   with no `?source=` (FD-10), and Smithery has no RelayShield entry at all (FD-11). Both are
   written up in `FRONT_DOORS.md`, including why a Smithery LISTING is fine and Smithery HOSTING
   deserves a decision. Original entry follows. **FD-9 — verify Glama by hand.** `glama.json` is present in the MCP server repo, but `glama.ai`
   is rejected by the container's egress policy, so the listing status is genuinely UNKNOWN, not
   absent. Open <https://glama.ai/mcp/servers>, search RelayShield. If listed, get
   `?source=mcp-registry` onto the link it points at — the key is registered and `glama.ai` is
   already a referer host. If not listed, Glama indexes from GitHub, so the route is making sure
   `glama.json` is on the default branch, not a submission form.
8. **relayshield-agentic-api drift.** Recovered onto `claude/recovered-live-relayshield-agentic-api`
   by `recover_live_handler.yml`. **NOT yet reconciled into main.** Live carries a branded
   `API_BASE_URL` and a Bundle D Stripe billing branch that main does not; deploying main over it
   would make the direct Stripe door free.
9. **INTEL-5 funnel.** Instrumented but the answer is not in yet. Re-run
   `tools/diagnose_stolen_sessions.py` after the monitor has run on the instrumented build; its
   section 0 now says outright whether that build is live.
10. **XSOAR blog + landing line**, triggered by `check_xsoar_pack.sh` reporting ON MASTER, never by
    a date. **Checked 2026-09-03: still NOT on master.** `#45206` has lost its `/merge` ref,
    `#45742` still has one so it is open in Palo Alto's pipeline, and
    `Packs/RelayShield/pack_metadata.json` is 404 on master while the control pack is 200, so the
    absence is real rather than a blocked request. Nothing to publish yet. **The gate is now
    watched rather than remembered:** `xsoar_pack_watch.yml` runs the check daily and opens an
    issue the day it flips, and the script's last line is a machine-readable
    `XSOAR_PACK_STATUS=merged|absent|undetermined`.
11. **`relayshield_discord_bot.py` — read its first drift diff, then decide.** FIFTH instance of
    source-in-repo, live, and in NEITHER map. It was added to `lambda_drift_check.yml` ONLY on
    2026-09-02, deliberately: a red diff is the alarm and gets read before anything is mapped in the
    deployer, because live may carry hand-deployed code a repo-sourced deploy would delete with no
    error anywhere. **The function name in the map is UNVERIFIED** — if the check reports "not
    readable", fix the name, do not drop the entry. Only when the diff shows live is merely stale
    does it go into `deploy_lambdas.yml`. Until then no edit to that file ships automatically, which
    is why the email-check footer added this session is not visible in Discord.
    **2026-09-03: COMPLETE. The footer is live in Discord.** The diff was read with
    `sh tools/handler_drift.sh relayshield_discord_bot.py`: live was byte-identical to `0c429e0`,
    stale by exactly one commit and holding nothing of its own, so the function went into
    `deploy_lambdas.yml` and run 134 shipped it (`✅ relayshield-discord-bot deployed`). That run is
    RED, and the red is the import probe being denied `lambda:InvokeFunction`, not the deploy. See
    the 2026-09-03 section above for all three findings and what closed each.

### Done and verified 2026-09-02

- **`checkemail@relayshield.net` is LIVE and returns correct HIGH verdicts.** It took nine distinct
  defects to get there, and every one was found by the founder testing rather than by me:
  a malformed `References` header, a fallback that fired a second reply Cloudflare forbids, HTML
  entities left undecoded, `stripHtml` collapsing a message to one line, `parseAddress` trusting the
  first angle brackets, the API's `{ok, data}` envelope read at the wrong level, a scoring model that
  counted flags instead of weighing them, brand impersonation gated on free webmail, and RFC 2047
  subjects printed raw. 78 verdict tests and 11 reply tests now pin all of it.
- **The email check is on every surface**: WhatsApp hint, Telegram hint, both Quickstart cards,
  Discord `/scan` footer, and the blog footer on every page.
- **Telegram Markdown escaping never worked.** Legacy Markdown has NO escape syntax, so `\_`
  rendered a visible backslash. Quickstart is HTML now; the forward note uses code spans.
- **The drift check was silently dead** for a day, from a YAML indentation error of mine.
  `test_workflows_parse.py` guards the class.
- FD-1 done (rsscan v0.2.1 on the Marketplace). FD-2 killed on their published rules. mcp.so now
  charges $39 — skipped.

### Things this session got WRONG, recorded so they are not repeated

- **Handed over commands that did not exist** (`--stars`) and instructions written without reading
  the target (FD-2's PR would have been closed without comment; the mcp.so form is paid). **Read the
  destination before writing the instruction.**
- **Diagnosed by guessing** three times before adding logging. The logging found it in one round
  each time. Instrument first.
- **Wrote `emailcheck@` for `checkemail@` twice**, in the message asking to put it on four surfaces.
  One constant now, and a test.

### Two open items with no owner yet

- **`relayshield_discord_bot.py` is in the deploy map of nothing.** Fifth instance of that
  combination. Added to the drift check only; read its first red diff before mapping it.
- **`relayshield_stolen_sessions` still holds 9 rows, all `demo`.** The CORPUS-1 storage fix is
  correct and has never been reached.

---

## WHERE 2026-08-30 LEFT THINGS — read this first

### The list that session left, as of 2026-08-30 (HISTORY, not a queue)

1. **Telegram + WhatsApp forward handler and compromised-contact check.** Designed, decided, NOT
   built. Integration points already located: `handle_message` (`relayshield_telegram_webhook.py`
   ~6072) for the `forward_origin` branch, `handle_scan_dispatch` for the URL path,
   `handle_infostealer_check` and the `relayshield_stolen_sessions` lookup for the contact check.
   Decisions made: a clean result says so plainly with the "not proof of safety" caveat; the contact
   stolen-session lookup runs ONLY when text, URL or first-time-sender has already flagged
   something, so no social graph accumulates. Forwarding needs no command; `/wascam` becomes the
   discovery path that explains it.
2. **Quickstart guide hints**, same build: tell users they can paste screenshots (already works, OCR
   via Rekognition since 2026-08-11) and forward suspicious messages to `@relayshield_bot`.
3. **IAM split, step 2.** The snapshot is committed and it is worse than assumed: 26 inline policies
   at 10,127/10,240 bytes AND 10/10 managed slots, both budgets full, with **42 Lambdas** on the
   role rather than the 22 in `LAMBDA_MAP`. `tools/iam_scan_sources.py` must read the snapshot's
   `functions_using_this_role` before any migration, or 20 functions get no derived policy.
4. **Re-run the prospector** with the new gates: `python3 tools/prospect_github_bots.py --limit 200`.
   The first run was mostly noise; the gates are tested against that exact output but not yet against
   live data.
5. **`relayshield_agentic_api.py` deploy path.** In the drift check since 2026-08-30, deliberately
   NOT in the deploy map. Read its first red diff, then map it.
6. **Sweep 003's 17th keyword** is unrecoverable. Either accept 16 or re-derive from TI reporting.
7. **XSOAR PR #45206 is MERGED (2026-09-02)** and no demo was required after all. The work is now
   in Palo Alto's internal PR #45742, which is open and approved. Nothing for us to do; the pack is
   not on master yet, so the marketing claim is still gated. See STATUS CORRECTIONS.
8. **Rain** waits on a reply. Two open questions carried: whether the Agent Control Layer has a
   pre-issuance hook, and the Sardine/Chainalysis paragraph never got its outside read.
9. **Medium quote bars**: house style is now none. `build_blog.py` renders `> ` as a plain `<p>`.
10. **OpenRouter revocation webhook** still gated on the first non-zero `sk-or-v1-` count.

### Done 2026-08-30

- **Rain closed after four sessions.** `tools/rain_demo.py`, recorded, both submissions sent.
- **LLMjacking coverage materially widened.** Venice (`VENICE_INFERENCE_KEY_` + base62, taken from a
  real key), Anthropic OAuth and session tokens split from API keys because they need REVOCATION not
  rotation and the old `{90,}` pattern likely missed them entirely, and `/checkllm` brought from 6
  providers to 14 — it had been silently behind the corpus, with OpenRouter missing.
- **Four pattern tables must agree**: `relayshield_api.py` (source of truth), `rsscan/rsscan/patterns.py`
  (generated, `tools/sync_patterns.py`), `relayshield_intel_monitor.py` (collection), and
  `_LLM_KEY_PATTERNS` in `relayshield_telegram_webhook.py` (customer-facing). The last one is the one
  that drifts unnoticed, because nothing checks it.
- IAM per-role tooling and runbook; `relayshield-mcp` gitlink removed; deploy-role invoke policy
  applied and the Lambda deploy green; the LLMjacking blog published; CLAUDE.md rules 9, 10, 11.

---

## WHERE 2026-08-29 LEFT THINGS — read before starting anything

`main` is at the merge of everything below. **One branch is unmerged:
`feat/partner-center-and-aws-setup`.** It carries the Partner Center, the Stripe attribution fix,
`tools/setup_first_seen.sh`, `tools/check_xsoar_pack.sh` and the Telethon simplification. Merging it
deploys `relayshield-stripe-webhook`, which is in the deploy map.

### Done and verified this session

- **The 35/46 local-vs-GitHub divergence is closed.** Andrew's clone held 36 unpushed commits
  (Microsoft Security Copilot MS-3/MS-4, the Sentinel Content Hub solution, TAXII dedup, CORPUS-1/2,
  the XSOAR email). Merged with only three contested files, resolved hunk by hunk, and
  `tools/reconcile_guard.py` run against **both** parents: `relayshield_api.py` 349/349,
  `relayshield_intel_monitor.py` 156/156, `build_blog.py` with `RSS`/`from_rss` as named drops.
  Backup branches `backup-main-20260829` and `origin/local-main-20260829` still exist.
- **intel-feed and intel-kev now have a deploy path**, plus `ci.import-probe` early-returns so the
  deployer's probe cannot trigger a full ingest.
- **`deploy_lambdas.yml` change detection was broken for merges** and would have shipped nothing on
  the very merge meant to ship those two. Now diffs from `github.event.before`.
- **The prospecting Telegram account is live.** Session in
  `relayshield/telethon_session_prospecting`. **Nothing reads it yet, and that is deliberate** — per
  `telegram_miniapp_and_app_inventory_scope.md`, Item 16's GitHub half is built first. The
  collection session was never touched.
- **XSOAR PR #45206 is NOT merged.** Verified by content, not just refs. See STATUS CORRECTIONS.
- **Partner commission decided: 20% / 12 months.** See PARTNER COMMISSION below.

### BLOCKED — A6 first-seen, the only thing left hanging

`relayshield_intel_first_seen` **exists in the right account** (239677749008). What fails is granting
the Lambda write access.

`relayshield-intel-monitor` runs as **`relayshield-breach-check-role-1sapnwdl`** — one shared role
carrying 22+ inline policies spanning Rekognition, Bedrock, marketplace metering and a dozen
DynamoDB tables. IAM caps the **aggregate size of a role's inline policies at 10,240 characters**,
and that budget is spent, so `put-role-policy` fails.

**Ask the cheap question first, which the first version of the script did not:** the role already
has a `relayshield-intel-dynamodb` policy. If its Resource is a `relayshield_intel_*` wildcard, the
permission already exists and there is nothing to grant. `tools/setup_first_seen.sh` now checks that
before trying anything, and falls back to a **customer-managed policy** (separate budget: 10 per
role, 6,144 chars each) if a real grant is needed.

**The backfill is NOT blocked by this and never was.** `tools/backfill_first_seen.py` runs as
`relayshield-deployer`, the operator, not as the Lambda role. It can populate the table today. What
the missing grant blocks is the LIVE monitor recording first-seen for anything collected from here
on, so the table would freeze at whatever the backfill writes. The script's grant step is now
non-fatal for exactly this reason: `set -e` was aborting before the backfill instructions printed,
which is what turned one IAM error into "I cannot backfill".

### Also outstanding

- **`relayshield-feed-maintainer`** — live on the stream, source in the repo since
  TAXII-PAGINATION-2, and was in NEITHER map. Third instance of that combination. Added to the
  **drift check only**. Read its first red diff before mapping it in the deployer.
- **An empty `relayshield_intel_first_seen` sits in `620534471984`** from the wrong-account write.
  Costs nothing on PAY_PER_REQUEST with no items. No delete command has been written for it on
  purpose.
- **The `relayshield-mcp` submodule is broken**: a gitlink in the index with no `.gitmodules` entry,
  which is why CI logs `fatal: No url found for submodule path`. Pre-existing, harmless, unfixed.

---

## OPEN TODOS THAT MUST NOT BE FORGOTTEN

Added 2026-08-27. These are blocked on a wait, not on a decision, which is exactly the kind of item
that gets lost between sessions.

### A7 follow-through — two Lambdas with no deploy path

`relayshield_intel_feed.py` and `relayshield_intel_kev.py` were in NEITHER `deploy_lambdas.yml` NOR
`lambda_drift_check.yml`: source in the repo, no automated deploy, no drift detection. That is the
same combination that produced ~1,900 undeployed lines across four handlers on 2026-08-26.

**RESOLVED 2026-08-29.** Run 9 of `lambda_drift_check.yml` (2026-08-28 22:49, red, 2 annotations)
named both functions. The diffs were read in full and were **one-directional**: the live code is
`main` minus the A7 commit and nothing else. No live-only symbol, no live-only import, nothing to
recover. That is not the 2026-08-26 hand-deploy pattern, it is "the repo is ahead and there is no
deploy path" — so the check could never have gone green on its own, and the original step 3
("only once the check is green") was unreachable by construction.

Both are now in `deploy_lambdas.yml`, with `relayshield_intel_labels.py` mapped alongside them.
**The next merge to `main` touching either file deploys them and the drift goes away.** Until that
merge lands, the feed and KEV halves of A7 (malware label normalisation) are still inert.

The general rule this replaces it with, for the next handler that turns up unmapped:

1. A red drift run is the alarm, always. Read the diff before doing anything.
2. **Only if the live side contains something `main` does not** — a symbol, an import, a whole file
   — recover it with `recover_live_handler.yml` and reconcile, exactly as the four handlers were on
   2026-08-26.
3. If the diff is only `main`'s own commits appearing in reverse, live is simply stale. Add the
   function to `deploy_lambdas.yml` and deploy; there is nothing to recover.

Note on the deploy probe: `relayshield_intel_feed.py` and `relayshield_intel_kev.py` begin ingesting
on the first line of `lambda_handler`, and the deployer invokes everything it deploys to prove the
package imports. Both now return early on `{"source": "ci.import-probe"}`. Any future handler that
does real work on invoke needs the same three lines.

### Rain — DONE 2026-08-30. Demo recorded, both submissions sent.

Carried across four sessions and closed. The demo is `tools/rain_demo.py`: one command, an agent
discovers two MCP servers, pays $0.35 over x402 to check each before connecting, refuses
`modelcontextprotoco1.io` on an edit-distance-1 typosquat finding, connects to `mcp.so`. Unattended,
no account.

The payments are real and are the artifact that outlasts the video:
`basescan.org/address/0xa26054A4188e6D5c31A4DcdFcA27b0FfE247228d#tokentxns`. **Link that tab, never
the bare address** — the address page shows "Transactions Sent: N/A" and an empty list, because
x402's exact EVM scheme has the agent sign an EIP-3009 authorisation and the facilitator broadcast
it. The wallet never sends a transaction and never holds gas.

Agentic Startup Program form submitted, and the email sent to `apa@rain.xyz` from
`andrew@relayshield.net` with the recording attached. Both answer sets are in `rain_submission.md`,
verbatim, including the target-audience and stage decisions and why they were made.

Two things left open, and both are the reply's problem now: whether the Agent Control Layer has a
pre-issuance hook (the email asks rather than assumes), and the Sardine/Chainalysis paragraph never
got its outside read.

### Routavo — registered for early access 2026-09-02

`routavo.com`. "Connect your API once. Agents find it, call it, and pay for it." Metered per call,
settled the moment the API returns 2xx, 1% of what settles capped at a cent, no per-call fee, failed
calls cost nothing. Points at an OpenAPI spec rather than needing a rewrite.

Directly relevant: 28 live x402 endpoints priced $0.05-$0.35, already settling on Base, and
`relayshield_openapi_spec.py` is the artefact they want. **Founder registered for early access.**

Their "Control" pillar is SPEND control on the buy side -- allow, deny, rate-limit, cap per agent.
It answers "is this agent allowed to spend", not "is the thing it is about to pay legitimate". That
is the same gap as Rain, and it is the pitch TO them, not a conflict with them.

### OpenRouter key-revocation webhook — build it when the corpus has OR tokens

Sequenced behind data, like A8, and for the same reason.

The LLMjacking detector's OpenRouter pattern shipped in `844a2c3` (deployed 2026-08-27 11:11). It
has been live two days, so **there is no corpus of captured `sk-or-v1-*` keys yet** and nothing to
notify anyone about.

When there is, the integration is the revocation webhook: RelayShield detects a leaked OpenRouter
key in a criminal Telegram channel and calls OpenRouter to revoke it, before the key is drained.
That is the thing their own tooling cannot do, because they cannot see the channel.

**Trigger to build:** the first non-zero count of `sk-or-v1-*` in **`relayshield_stolen_sessions`**, NOT `relayshield_intel_iocs`.

**Corrected 2026-09-02.** A scan of `relayshield_intel_iocs` for `sk-or-v1-` returned 0 of 6,712,425 rows and was briefly read as "no OpenRouter keys collected". It is not: `_NHI_PATS` in `relayshield_intel_monitor.py` writes credential findings to `relayshield_stolen_sessions` (`type: nhi`), and `relayshield_intel_iocs` never receives them. A zero from the wrong table is not evidence of absence, and this one nearly became a recorded fact. Check it
before writing any of it.

**Then the RIGHT table was scanned, same day, and the answer was worse.**
`relayshield_stolen_sessions` returned `Count: 0, ScannedCount: 9`. Nine rows is
the WHOLE TABLE. And nine is a number this repo has seen before: the docstring of
`_store_observed_session` records "the table held 9 rows on 2026-08-16, all of
them source `demo`, after months of collection" -- the CORPUS-1 finding that
`_store_stolen_session` required a `matched_email` and so discarded every session
not already belonging to a customer.

If it is still nine, and still the demo rows, **the CORPUS-1 fix has written
nothing since it shipped**. `_store_observed_session` is only ever called from
the archive-parsing path, so "no observed rows" and "no archive was parsed" are
the same finding. A matching count is a LEAD, not a fact -- settle it with:

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/diagnose_stolen_sessions.py

It reports the table by `source`, says whether the observed path has ever fired,
and reads the INTEL-5 log lines to say WHERE the pipeline stops -- archives never
seen, oversized, download failed, wrong format, or handler raised. Each is a
different bug with a different fix, which is why `archives_parsed` as a single
number cannot tell you.

**Until that is fixed, no count out of this table means anything about the
criminal market.** It measures our collection. Do not read a zero here as absence
of OpenRouter keys in the wild, and do not quote any number from it. Do not build the webhook against zero rows, and **do not quote a captured
OpenRouter key count to OpenRouter, Stripe, or anyone else until the category clears 100** — the
standing measurement rule applies here with force, because this is a number that would be checked.

Rationale, and why this is the right ask of Stripe post-acquisition, is in
`openrouter_stripe_integration_angle.md`.

### Rain Agentic Startup Program — SUBMITTED 2026-08-30

See the Rain entry above. Kept only for the framing, which still applies to any follow-up: Rain's
Agent Control Layer already answers "is this agent allowed to spend this much". Nothing in it
answers "is the thing it is about to pay legitimate". An agent with a valid card, inside its limits,
paying a fraudulent API is a fully authorised transaction.

**Do not pitch against Sardine or Chainalysis.** They score the user and the funds; we score the
counterparty and the tool. Full analysis in `socradar_gap_closure_roadmap.md`.

### A8 — grow `tg_handle`, but only after the filter

Sequenced behind a two-week measurement, deliberately. The evidence for waiting is already in:
`relayshield_operator_identities` holds 7 rows, every one at `sightings=1`, several of them English
words (`catching`, `normanonrock`) caught because `_RE_TG_CHANNEL` matches any `@mention`.

**Growing collection before filtering multiplies the noise, not the signal.**

- Watch `tools/check_operator_identities.py`'s cross-channel number. Handles seen in 2+ channels are
  the exclusive asset; a row count is not.
- If it is still 0 after two weeks of hourly runs while channels are producing messages, the problem
  is extraction and the fix is a filter, not more collection. Strongest option: require a SECOND
  sighting before writing the row at all, which filters on repetition rather than guessing what a
  handle looks like.
- **Do not quote a `tg_handle` exclusive-share number until the category clears 100 collected
  indicators and `exclusive_share_by_category.py` has run on it.** This is the number most likely to
  be quoted at a competitor, so the standing rule applies with extra force.

---

## STATUS CORRECTIONS — docs that are stale

`NEXT_SESSION_2026-08-20.md` is the last full handoff, but items have completed since and the file
was not updated. **Ask before treating anything in its "carried forward" list as open.**

Known completed after that handoff was written:

- **XSOAR PR #45206 / Tech Alliance (roadmap D3)** — **MOVED 2026-09-02. #45206 IS MERGED; THE
  PACK IS STILL NOT ON MASTER.** Both facts matter and neither replaces the other.

  demisto/content does not merge an external contribution straight to master. A bot merges it into
  an INTERNAL PR, which then runs their own pipeline. On 2026-09-02 `#45206` had lost its `/merge`
  ref (merged), and the bot comment named the successor: **#45742**, which is OPEN, has an
  approving review, and carries `Packs/RelayShield/`. Verified by content, not by refs alone:
  `pack_metadata.json` returns 200 on both PR heads and **404 on master**, with a control pack
  returning 200 so the 404 is real and not a blocked request.

  So the state is a three-stage pipeline and the claim only becomes safe at stage three:

  1. Contribution PR #45206 — **merged.** It has left our hands.
  2. Internal PR #45742 — **open**, approved, 1 failing check (`ci/gitlab/gitlab.xdr.pan.local`).
     That is Palo Alto's own internal GitLab pipeline, inside their infrastructure, on a PR authored
     by their `content-bot`. **We cannot see it and cannot fix it. There is no action for us.**
  3. `Packs/RelayShield` on master — **not there yet.** This is what a prospect checks.

  **Do NOT write "ships with Cortex XSOAR", "in the XSOAR Marketplace", or "available to XSOAR
  customers" anywhere yet.** What is true and checkable today: *"RelayShield's Cortex XSOAR content
  pack has been contributed to Palo Alto Networks' content repository and accepted; it is
  progressing through their internal release pipeline."*

  Moshe Eichler confirmed on the PR, in writing, that on merge the pack **gets a Marketplace listing
  page** and **is named in their Release Notes**. That is the moment the stronger claim unlocks, and
  it is worth a blog post and a landing-page line when it lands.

  `sh tools/check_xsoar_pack.sh` now tracks all three stages and prints the exact wording that is
  safe at the current one. Run it before the claim goes in any deck, email or landing page.

  **TODO, TRIGGERED BY THE MERGE, NOT BY A DATE.** When `check_xsoar_pack.sh` reports ON MASTER:

  1. **Blog post**, canonical on `blog.relayshield.net`, then the usual channel order. The angle is
     not "we shipped an integration" -- it is what the pack DOES that a Cortex XSOAR customer cannot
     do today: enrich an incident with indicators collected from criminal Telegram channels, which
     is the exclusive half of the corpus rather than the public-feed half. Do not quote a corpus
     number in it; MEASUREMENT DOCTRINE applies, and this is a post a competitor will read.
  2. **Landing-page line on the API site**, and only then. Wording once it is true:
     *"Available as a Cortex XSOAR content pack."* Link the Marketplace listing page directly, since
     Moshe confirmed in writing that one is created on merge.
  3. **Link their Release Notes entry** from the blog post. Also confirmed in writing. It is
     third-party proof, which is worth more than our own claim about ourselves.
  4. Re-run `check_xsoar_pack.sh` immediately BEFORE publishing either. The gap between writing and
     publishing is exactly where a false claim gets in.

  Note also: the demo requirement recorded under OPEN TODOS as gating the merge did **not** block
  #45206 — it merged without one. Do not carry that as a blocker again without re-checking.

  Two separate things were being conflated under "DONE", and they must stay separate:

  1. **The content pack PR (#45206)** — technical, in `demisto/content`, **still open**.
  2. **The Palo Alto Tech Alliance partnership** — commercial, and now gated on Palo Alto's new
     requirement of **3 named joint customers**.

  Neither blocks the other. The pack is a public contribution and does not need the Alliance. Do not
  report either as complete without checking the refs above.

  **VERIFIED 2026-08-29 by content, not just by refs.** A blobless sparse clone of `demisto/content`
  at master (`2c87a93`) holds **1,350 packs and zero files matching "relayshield" anywhere in the
  tree**, while `refs/pull/45206/head` carries all 13 files of `Packs/RelayShield/`. The pack exists
  only on the branch. **`sh tools/check_xsoar_pack.sh`** runs both checks; run it before "our pack
  ships with Cortex XSOAR" goes into any deck, email or landing page, because that is a claim a
  prospect can check in ten seconds.

---

## THE FIRST CATALOGUE SUBMISSION IS IN. FINDMINI, 2026-09-14, VIA A WEB FORM.

**Top 15 item 1, and it went through on the first attempt after four rounds failed at it.**
`findmini.app/submit/` accepted the app and answered *"Thanks for your submission! We'll review your
app and add it to the catalog."* Stated turnaround under 24 hours; corrections go to
`support@findmini.app`.

**WHAT ACTUALLY UNBLOCKED IT WAS THE WEB-FRONT-DOOR FINDING, NOT MORE EFFORT.** Every earlier attempt
went through Telegram, where a catalogue shows its contents and hides its plumbing: `@telegtapps`
turned out to be an ad broker, `@tapps_bot` is the catalogue rather than the route, and
`@app_moderation_bot` did not answer `/start`. FindMini put "Submit your app" at a plain URL and the
whole thing took one form. **Prefer a web directory's own site over its Telegram surface, every
time.**

**AND I HAD THE RANKING WRONG UNTIL THE DAY OF.** The 2026-09-14 Top 15 said miniTelegram first,
because its flow was "described rather than inferred". FindMini's was better than described: a named
form URL, a named turnaround and a published exclusion list. **"Described" beats "inferred" and
"a URL that loads" beats both.**

### `@app_moderation_bot` IS NOT PROVEN DEAD, AND THIS FILE SAID IT WAS

Asked directly, and the honest answer is no. The measured fact is that a founder's `/start` got no
reply on mobile and on desktop. **"Therefore dead" is inference from one symptom**, written by me, in
the same section that criticises me for naming that bot on four secondary sources without reading the
destination's own page.

Re-tested from the container rather than recalled: `t.me`, `tapps.center`, `builders.ton.org`,
`medium.com` and `core.telegram.org` are ALL egress-blocked, so the bot still cannot be probed here.
**What is now on the other side of the scale:** the TON Studio blog that introduced tApps Center names
the Apps Moderation Bot as the mechanism, and a 2026 developer account describes a COMPLETED listing
through it with 3 to 8 day moderation. Somebody got in that way recently.

**A live bot and a silent `/start` are not contradictory.** Most likely first: it needs a deep-link
payload (`?start=<token>` handed out by the catalogue), so a bare `/start` typed from search hits a
handler expecting one. Then: the flow moved to the web; a squatted or renamed username; genuinely
dead. **The observation that separates them costs ten seconds and is the founder's: does the chat show
a START button and a bot description, or nothing at all?** Do not spend another round on tApps until
that is answered.

### THE FUNNEL'S INSIGHTS IAM GRANT IS ALREADY IN PLACE. TOP 15 ITEM 5 IS CLOSED.

`miniapp_funnel_snapshots/before-telegtapps.json`, generated **2026-09-13T23:38 UTC**, carries real
stage numbers (`WATCHED 2`, `BOT 1`, `STARS 1`, `DEVELOPERS 5`) and no `AccessDeniedException`. The
tool names a refusal rather than rendering it as a zero, so numbers coming back at all is the
evidence. `relayshield-deployer` has `logs:StartQuery`, `logs:GetQueryResults` and `logs:StopQuery`.

**AND THIS FILE'S CLAIM THAT `miniapp_funnel_snapshots/` "HOLDS ONLY ITS README" IS NOW WRONG.** It
was true when written and a baseline has been taken since. Corrected here rather than left, because
a stale status in this file is exactly what the WHERE THE CURRENT WORK LIST LIVES section warns costs
a round to disprove.

### THE KEY IS `tg-miniapp-findminiweb`, AND IT IS A SEPARATE DESTINATION ON PURPOSE

`tg-miniapp-findminiapp` is the CHANNEL, 56,380 subscribers. This is the web directory. Same
operation very probably, and still two destinations: **a channel post is one impression lasting a
day; a directory listing is a standing shelf that keeps returning arrivals for as long as it is up.**
Sharing a key merges a broadcast with a permanent surface and makes the delta uninterpretable, which
is the `tg-miniapp-channel` defect the route table was rebuilt to remove.

Registered in all three lists that must agree: `miniapp_routes.json` rank 5, `ALLOWED_SOURCES` in
`cloudflare_worker_miniapp.js`, `_SOURCE_ALIASES` in `relayshield_developer_signup.py`.

**THE ORDERING THAT IS EASY TO GET BACKWARDS, AND THE WINDOW IS ABOUT 24 HOURS:** merge and push so
the key deploys, THEN open the deep link and press "Check it" to prove it logs, THEN take
`--snapshot before-findminiweb`. Opening the link logs NOTHING on its own; pressing "Check it" is
what writes the `source=` line. A self-visit inside the baseline is harmless; the same visit after it
becomes part of the delta. The snapshot REFUSES to overwrite, which is the most important line in
that tool.

### THE LISTING ARTWORK IS GENERATED, NOT CROPPED

The profile picture field wants SQUARE, minimum 256x256. `idcheck_botfather_640x360.jpg` is the right
brand mark and is 16:9, a two-column lockup with the shield left and the type right, so **no square
inside it contains both** and any crop loses one. `assets/miniapp/idcheck_icon_512.html` re-lays the
identical shield SVG and ID/Check lockup into 512x512 and renders through the same headless Chromium
path, pinning the same `#17212b` and `#3b82f6` that `cloudflare_worker_miniapp.js` declares as the
Telegram theme defaults. Tagline and eyebrow are dropped: a catalogue renders this at 80 to 120px,
where a 22px line of body copy is a grey smudge.

**The descriptions were written against the page the Worker ACTUALLY SERVES**, rendered with
`tools/miniapp_render.mjs`, and that caught a real omission: the paste box takes *"a link, a TON
address (EQ... / UQ... / 0:...), or @handle"* and the first draft described two of the three inputs.
Full copy is in `findmini_submission_2026-09-14.md`.

## AN IMAGE SENT THROUGH THE CHAT ARRIVES AS `.webp`. SEND IMAGES VIA THE REPO.

**2026-09-14, and it cost three rounds on the miniTelegram submission before anyone said the word
"webp".** The founder reported the icon upload failing with a full-page *"Something didn't go
according to plan"*, then that the downloaded file *"shows as .webp and is greyed out in my desktop
folder"*.

**Greyed out in a file picker is the whole diagnosis.** An upload dialog that accepts JPG and PNG
filters everything else out, so a `.webp` cannot even be SELECTED. miniTelegram never rejected our
icon. It never received it.

**THE FILE WAS NEVER THE PROBLEM AND I HAD ALREADY PROVED THAT.** Inspected rather than assumed:
512x512, 8-bit RGB, no alpha, non-interlaced, 65 KB against a 5 MB cap, IHDR and IDAT and nothing
else. I then generated four format and size variants to "remove the variable" -- and every one of
them would have arrived as `.webp` too, because **the re-encoding happens in the delivery, not in
the file.** Four variants of the right answer, all destroyed in transit by the same step.

**THE RULE. The chat is the DELIVERY for a `.md`. It is NOT the delivery for an image.** The
top-of-file rule says send the file so he can download it, and that rule was written about
documents. Markdown survives the trip; a PNG or a JPEG does not.

**So any image deliverable -- an app icon, a store screenshot, a listing asset, an OG image --
travels in the REPO, and the instruction is the merge.** After it, the file on his Mac is
byte-identical to the one generated here, because git moves bytes and nothing re-encodes them:

    cd ~/dev/relayshield
    git checkout main
    git --no-pager fetch origin claude/<branch>
    git rm -rf --cached -q --ignore-unmatch ansible-relayshield relayshield-snap
    git stash push --include-untracked -m "pre-merge untracked"
    git -c pull.rebase=false merge --no-edit FETCH_HEAD
    file assets/miniapp/idcheck_icon_512.png
    open assets/miniapp

Send the image in chat as well if it helps him SEE it -- a preview is genuinely useful and a webp
previews fine. **Just never as the copy he is meant to upload somewhere.** Say which one is which in
the same reply, because a sent file looks like a deliverable whatever it is for.

**AND IT IS WHY `.gitignore` NOW CARRIES `!assets/miniapp/*.png` AND `!assets/miniapp/*.jpg`.** The
blanket `*.png` and `*.jpg` rules exist because `relayshield_favicon.png` is 87 MB. An image that has
to reach the founder intact must be TRACKED, or the merge that is supposed to deliver it delivers
nothing. Keep these small and the exception is free.

**THE GENERAL FORM, and it is the reading-guide lesson in a new place: a pipeline can transform the
artefact after you have verified it.** Every check I ran read the bytes on disk here. None of them
described the bytes that arrived there. That is the template-literal defect exactly -- the source and
the served text are different documents -- and it is the third time this repo has paid for verifying
an artefact at the wrong end of a pipe.

## CATALOGUE STATE AT THE END OF 2026-09-14. TWO SUBMITTED, ONE PARKED, TWO NEXT.

**Top 15 item 1 is no longer theoretical.** Two catalogue submissions are in, after four earlier
rounds reached none.

| Destination | Key | State |
|---|---|---|
| findmini.app | `tg-miniapp-findminiweb` | **SUBMITTED**, web form, under 24h review stated |
| awesome-telegram-mini-apps | `tg-miniapp-awesome` | **SUBMITTED**, pull request **#77**, open |
| minitelegram.com | `tg-miniapp-minitelegram` | **PARKED**, their form crashes on icon upload |
| ton.app | `tg-miniapp-tonapp` | next, key registered |
| tg.app | `tg-miniapp-tgapp` | after that, key registered, weakest evidence |

**`tg-miniapp-findminiweb` IS DEPLOYED** -- deploy_miniapp run 16 and deploy_lambdas run 149 both
green on `538c35f`. The other three keys are registered in all three lists and ship on the next
merge.

**THE AWESOME-LIST ROUTE IS THE ONE TO REACH FOR WHEN A FORM FIGHTS BACK.** It has no file picker
anywhere in it: edit the README on GitHub, which auto-forks and opens the PR. That property is why
it was ranked first despite being a developer list rather than a consumer catalogue -- two rounds
had just been lost to an upload dialog. **When a submission surface is costing rounds, ask whether a
PR-shaped destination exists before generating another asset for the one that is failing.**

**miniTelegram is parked on THEIR defect, not ours.** Four separate icon files -- 512 and 1024, PNG
and baseline JPEG, every one RGB with no alpha and far under their 5 MB cap -- each crashed the page
and discarded the filled form. A validator that rejects a file gives a message; a page that crashes
and destroys a session is a bug. Their FAQ carries a contact and the report costs one email. Do not
spend another round generating images for it.

**AND THE ICON EPISODE IS RECORDED AS A LOOP I RAN, because the rule already existed.** I decided
the chat layer was re-encoding to `.webp` -- true -- without ever confirming which files the four
attempts used, then handed back a file already tried and called it different. Same bytes. The right
move after the FIRST failure was one question about what he was holding. This file says that when
the same instruction fails three times the instruction is the loop; I ran it to four, and the
correction came from the founder each time.

**One rejection recorded so it is not rediscovered:** `telesearch/Telegram-Mini-Apps-List` is not a
candidate. Last updated December 2024 by its own header, **no CONTRIBUTING.md at all** (404, so no
submission route exists), and ranked purely by monthly users with a top thirty of PAWS, Blum and
Hamster Kombat. A stale clicker leaderboard.

## THE VERIFICATION STEP I SHIPPED COULD NOT RETURN A PASS IN ANY STATE

**2026-09-15.** The founder pushed main, deploy_miniapp run 17 went green on
`120a1cf`, the key deployed correctly, and he ran the check I had written
directly underneath it:

    curl -sS https://app.relayshield.net/ | grep -c tg-miniapp-tonapp
    0

**Nothing was wrong. The probe was incapable of returning 1.** The Worker
resolves the key with `sourceFor(url.searchParams.get("startapp") || "")`, so a
request carrying NO `?startapp=` resolves to the generic `tg-miniapp` and
substitutes that into `__SOURCE__`. The key being asked about never appears in
the response of an unparameterised request, deployed or not.

**That is this repo's own "a probe that takes a route the real client does not
take proves nothing" rule, broken in the verification step of the very commit
that deploys the key** -- and it is the `/v1/ton-address` instrumentation
lesson and the unsigned-POST watchlist probe for the third time. The cheapest
request is the one a probe reaches for, and it is systematically the one that
skips the thing being tested.

**AND IT COST MORE THAN A ROUND, WHICH IS THE PART WORTH CARRYING.** A `0` from
a check I labelled EXPECT/STOP IF reads as "the deploy failed" and the next move
is to go looking at Cloudflare, at wrangler, at the DNS record -- all of which
were fine. **A wrong verification is more expensive than no verification**,
exactly as a wrong filter in a measurement tool is worse than no tool: both
produce a number the reader acts on.

**THE FIX IS A COMMITTED SCRIPT, NOT A BETTER ONE-LINER.**
`tools/verify_miniapp_source_key.sh <key>` requests the page WITH the parameter
and separates the three states, which are three different problems:

    LIVE        the edge echoes the key into const SOURCE
    DOWNGRADED  the edge answered with the GENERIC key -- registered on a branch,
                or the deploy did not run. This is the state that looks like
                working attribution and is not.
    UNREACHABLE nothing answered. Says nothing about the key either way.

It prints the `const SOURCE = "..."` line it matched on rather than a count,
because a check that says something is wrong owes the reader the evidence that
says WHICH thing. `RS_MINIAPP_ORIGIN` exists so the live code path can be
EXERCISED against a local render instead of only read -- all three branches were
run before it shipped, which is the thing that did not happen to the curl line.

**THE GENERAL FORM: a verification line in a chat reply is a command, and rule
14 applies to it exactly as it applies to the fix above it.** Run it, or label
it UNVERIFIED. I had run neither, because a one-line curl does not feel like a
command -- and it is the line the reader trusts most, because it is the one that
tells them whether everything else worked.

## THERE ARE THREE AWS PRODUCT ENTITIES, NOT ONE. BUNDLE A AND BUNDLE D ARE BOTH LIVE.

**2026-09-15, after I told the founder Bundle A's dimensions had never been added to AWS
and he corrected it in three words: "You are wrong!!!"** He is right, and the way I got
there is worth more than the fact.

    prod-kkvurtspreofy    Bundle D, Agentic Attack Surface      LIVE, public
    prod-f5qkfsxlxs4qg    Bundle A, Core Identity Exposure      LIVE
    (a third)             Bundle B, Attack Surface & Supply Chain -- change set written

**EVERY BUNDLE AFTER D GETS ITS OWN SaaSProduct ENTITY.** That is not a detail, it is the
architecture, and two hazards this file records loudly do not apply because of it: a
change set cannot replace another product's rate card, and the one-change-set-in-flight
limit is PER ENTITY, so bundles do not queue behind each other.

### TWO MISTAKES, BOTH SHAPES THIS FILE ALREADY NAMES

**1. I read the wrong entity and called the absence evidence.** The DescribeEntity capture
recorded above is of `prod-kkvurtspreofy`. Bundle A's dimensions were never going to
appear in a capture of a different product. **"A guard is only as good as where it got its
expectations"**, one directory over: I had the right discipline and pointed it at the
wrong artefact.

**2. I read a July plan as current status.** `TODO.md` item 33 describes Bundle A as
dimensions ON Bundle D's entity, and `aws_marketplace/bundle_a_add_dimensions.json` still
targets `prod-kkvurtspreofy` because it is from that abandoned plan. **The plan changed.**
`bundle_a_create_entity.json` creates a new product and `bundle_a_go_public.json` names
`prod-f5qkfsxlxs4qg` on its own first lines. **Both files sat in the same directory as the
one I did read, and I did not open either.** This file's own rule is that a doc recording
an open item is a LEAD, not a fact -- and a stale CHANGE SET is a doc.

### THE RULE, and it is one line

**When a repo holds more than one product entity, any claim about a product names the
entity id it was read from.** "Bundle A is not live" is unsupportable without
`prod-f5qkfsxlxs4qg` beside it. The same applies to any surface with siblings: two HF
Spaces, two Telegram sessions, three bundles. **Naming the id is what makes the claim
checkable, and it is what stops the next session reading a neighbour's capture as this
one's.**

### WHAT IS BUILT FOR BUNDLE B, so it is not re-derived

`aws_marketplace/bundle_b_create_entity.json` -- CreateProduct, UpdateInformation,
UpdateTargeting, AddDeliveryOptions, AddDimensions. Built by READING Bundle A's change set
and reusing its envelope rather than retyping it, so the shape AWS already accepted is
preserved. Six dimensions: `attack_surface_bundle_access` Entitled, plus five
ExternallyMetered at the prices the live tables carry -- supply-chain $0.10, asset-intel
$0.15, secret-scan $0.35, threat-actor $0.30, session-risk $0.30.

`test_bundle_b_changeset.py` holds six guards, and two of them are the AWS review cycles
this programme has already paid for: **no corpus count** (matched as a SHAPE, not as
today's stale figures, because the next wrong number is a different number) and **no
external payment route**, with a positive assertion that the usage instructions say
outright that AWS handles billing -- the Tier-1 clause that failed Bundle D's visibility
request twice. The other four pin that every endpoint has a dimension, every dimension has
an endpoint, exactly one dimension is Entitled, and every change targets the product the
change set CREATES rather than an existing entity.

**Still blocked on two things, both verified from the artefact rather than recalled.** The
role has `MeterUsage` and `ResolveCustomer` and lacks `DescribeEntity`, `ListEntities` and
`StartChangeSet`, read straight out of the IAM snapshot. And
`relayshield_bundle_fulfillment.py` -- where `BUNDLE_CONFIGS` and `PRODUCT_CODES` live, so
where two of Bundle B's code edits must land -- is in NEITHER `deploy_lambdas.yml` NOR
`lambda_drift_check.yml`. **Seventh instance of source-in-repo, live traffic, no deploy
path.** Added to the drift check only; `sh tools/handler_drift.sh
relayshield_bundle_fulfillment.py` reads the first diff.

## THE FIRST LIVE CATALOGUE LISTING. tg.app APPROVED THE SAME DAY, 2026-09-15.

**Top 15 item 1 has produced a listing that is actually on a shelf, not queued behind a review.**
tg.app's Creator Studio accepted the Mini App through a plain web form and the card came back
**Approved** in the same session: *Scam Checker | RelayShield IDCheck*, Mini App, Tools,
Sep 15 2026, 0 views 0 opens.

| Destination | Key | State |
|---|---|---|
| tg.app | `tg-miniapp-tgapp` | **APPROVED**, live |
| ton.app | `tg-miniapp-tonapp` | **SUBMITTED** 2026-09-15, under review |
| findmini.app | `tg-miniapp-findminiweb` | **SUBMITTED** 2026-09-14, under review |
| awesome-telegram-mini-apps | `tg-miniapp-awesome` | **SUBMITTED**, PR #77 open |
| minitelegram.com | `tg-miniapp-minitelegram` | **PARKED**, their form crashes on icon upload |

**FOUR OF THE FIVE WENT THROUGH A WEB FRONT DOOR.** The web-first finding is now measured
rather than argued: every Telegram-first attempt this programme made reached nothing, and four
web forms in two days produced four submissions and one live listing. Reach for the site.

### THE LISTING TITLE IS NOT THE BRAND, AND BOTFATHER DOES NOT CHANGE

tg.app's own guidance: *"Telegram search favors titles that match what users type, not brand
names alone."* Nobody types "RelayShield". The listing leads with the term and keeps the brand
attached -- `Scam Checker | RelayShield IDCheck`.

**This changes NOTHING in BotFather, deliberately.** The app title stays `RelayShield IDCheck`
and the short name stays `idcheck`. A catalogue title and a Mini App title are different fields
on different systems, three catalogues already carry `t.me/relayshield_bot/idcheck`, and
renaming a live shared surface to buy a search benefit the listing already delivers is a write
with no upside -- rule C, in the direction where the cheap answer is to do nothing.

## THE 4-SECOND DEADLINE WAS A BOT'S, AND THIS SCREEN INHERITED IT BY SAYING NOTHING

**Found 2026-09-15 from a founder screenshot: a valid TON address, pasted through the tg.app
deep link, rendering "Could not complete the check" with NO reason line under it.**

**THE ABSENCE OF THE REASON IS THE EVIDENCE, and it is worth learning to read.**
`serverReason()` prints `v.raw.error`, and `check()` only leaves `raw` empty when the fetch
THREW. So a blank card under that heading rules out, in one glance, the daily 429 cap, every
5xx, and every JSON error we send -- all of those carry a body. What is left is a rejection, a
network failure, or **our own deadline**. A card with no reason is a narrower finding than a
card with one, which is the opposite of how it looks.

**THE DEADLINE WAS THE WIDGET'S, AND THE PAGE ACQUIRED IT BY OMISSION.** Both call sites read
`check(value, { source })` with no `timeoutMs`, so they inherited `timeoutMs = 4000` from
`widget/relayshield-widget.js` -- whose own docstring says why: *"this runs inside a Telegram
handler, and a bot that stalls is worse than a bot that says it could not check."* **That is a
statement about a HANDLER**, where a late reply is a reply nobody is waiting for. A Mini App
screen is the opposite case: a person is watching a button that says "Checking..." and would
far rather wait eight seconds than be told the product failed.

**A DEFAULT IS A DECISION MADE FOR A DIFFERENT CALLER.** Nothing was misconfigured; the page
simply never stated its own requirement, so it silently took a bot's. `CHECK_TIMEOUT_MS = 12000`
is declared IN THE PAGE (Worker scope is a `ReferenceError` at load that `node --check` cannot
see), and `widget/relayshield-widget.js` KEEPS 4000 -- that file is copied into other people's
bots, where 4000 is right, and raising it there would lift the stall ceiling in every one of
them to fix a screen they do not have. A test asserts both halves, proven by reintroducing each.

### AND MY OWN DIAGNOSTIC CANNOT SEE A COLD START. IT WARMS THE FUNCTION IT MEASURES.

`tools/diagnose_miniapp_check.sh` step 1 sends the request with no deadline; step 2 re-sends it
under the app's own 4 seconds. **Step 1 warms the Lambda, so step 2 always measures a WARM
one** -- and the phone that failed hit a cold one. So "step 2 answered" is real evidence about
a warm function and **no evidence at all** about the case that failed.

That is the probe-takes-the-cheap-path trap for the fourth time (the unsigned watchlist POST,
`/v1/ton-address` instrumentation, the source-key curl that could not pass in any state), and
this time it is inside the tool written to end the previous one. **A two-step probe where step
1 changes the state step 2 measures is one probe, not two.** The fix shipped on the asymmetry
rather than on the measurement, which is the right call when the measurement cannot reach the
failing case: a slow answer costs seconds, a premature abort tells a first-time user the product
does not work and cannot even say why.
