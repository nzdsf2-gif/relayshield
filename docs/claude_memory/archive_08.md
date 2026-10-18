<!-- Verbatim sections moved out of CLAUDE.md on 2026-10-18, original order. Not auto-loaded.
     Find one with: grep -n 'WORDS' docs/claude_memory/INDEX.md -->

## 2026-10-05: THE API WAS DOWN FOR A SYNTAX ERROR, THE DEPLOY WAS GREEN, AND CS MOBILE v1.7.0 IS BUILT

**A one-character slip took the whole API off the air and the deploy reported success.**
`relayshield_scamkit.py` closed a frozenset with `)` where `})` belonged (the 2026-10-04 PhantomSub
and Milk Dragon additions). `relayshield_api.py` imports that module at the top, so the function
could not load. Found when a test failed at import, not by any alarm. Hotfix `7b0cf9b` is pushed.

**WHY THE DEPLOY WAS GREEN.** The post-deploy import probe grepped for `ImportModuleError` and
`No module named`. A syntax error is reported by Lambda as `Runtime.UserCodeSyntaxError`, which
matched neither, so the probe printed "imports cleanly" over a function that could not start.
That is the third time this file has recorded the probe saying yes for a reason unrelated to the
question (run 134's denied invoke, the `ci.import-probe` early return that never reaches the
dispatcher). **A probe that greps for the failures you thought of passes on the one you did not.**
It matches `Runtime.[A-Za-z]+` now, and `test_python_sources_compile.py` parses every tracked
`.py` before a push (asserting more than 100 files, so it cannot scope itself down to nothing),
names the API's import chain explicitly, and reads the probe pattern out of the workflow rather
than restating it.

**UNVERIFIED from the container: whether production was actually down.** Nothing here can call the
live API. The first move of the next session is
`curl -sS -o /dev/null -w '%{http_code}\n' https://api.relayshield.net/v1/link-check -X POST -d '{}'`:
anything but a 4xx JSON answer means the fix has not deployed.

### THE FREE EMAIL CHECK (`POST /v1/app/free-exposure-check`)

**Decided by Andrew 2026-10-05.** HIBP is a flat $5 a month, so one free check per install costs
nothing at the margin. It is keyless, runs HIBP (via `handle_breach`, so it inherits the 24h cache)
and Hudson Rock Cavalier (free, keyless), and returns `found`, `nothing_known` or `incomplete`.

* **One per install, enforced by a reservation, not a counter.** reserve, then finalise on a
  completed answer or RELEASE on an incomplete one, so a check that could not finish does not
  burn the allowance. Written with UpdateItem only, because GetItem on the quota table is
  unverified for the shared role. It fails CLOSED: if the allowance cannot be recorded the check
  is refused rather than served unmetered, the opposite of the keyless IP cap, deliberately.
* **Privacy posture is a property, tested.** The email is never stored or logged. The install id
  is hashed (`sha256`, truncated) and is not derived from anything else. Counters carry no
  identifier. `cloudflare_worker_privacy.js` discloses all of it and names HIBP and Hudson Rock as
  recipients of the address, which it did not before. **A free check that quietly sends an email
  to two third parties is a disclosure problem however good the feature is.**
* **A subscriber keeps the paid check.** `ScanScreen` routes to the free path only when
  `scanType === "infostealer" && !apiKey`.
* **The words never say safe.** `exposureCopy.ts` is a pure function so the test EXECUTES it under
  node; "nothing known" is the ceiling, an incomplete check is never worded as clean, and what WAS
  found is shown even when the other half failed.

### THE FUNNEL COUNTERS, AND THE REASON THEY EXIST

Nothing could say whether "no trials" meant nobody saw the paywall or everybody did and declined:
Stripe sees only COMPLETED trials. `POST /v1/app/event` accepts four names
(`paywall_viewed`, `checkout_tapped`, `wallet_connected`, `onboarding_completed`) and writes
`app_event name=... ctx=... v=... platform=...`. Fields are validated against `^[a-z0-9_.-]{1,24}$`
rather than escaped, because they land in a line a regex parses and a space would forge another.

**`tools/miniapp_funnel.py` reads them (`APP FREE`, `APP PAYWALL`, `APP TAPPED`)**, and
`test_cs_mobile_free_check.py` matches each regex against the handler's own format string. A
counter nobody reads is a feature nothing points at; a counter read with a wrong filter is a
confident zero. `CHANNEL = "solana"` in `analytics.ts` is pinned equal to the Stripe
`client_reference_id`, so the two platform splits cannot disagree. **A Google Play build sets
`googleplay` in BOTH places.**

### FINDINGS MADE ON THE WAY, EACH ONE REAL

1. **`/v1/wallet-risk` is keyless and the free tier's one wallet could never be scanned.**
   `WalletsScreen.scanWallet` returned "Subscription required" before sending anything. So the free
   tier advertised on the paywall could not be used.
2. **The paid Email Check always showed zero infostealer hits.** `ScanScreen` read `data.hits`; the
   endpoint returns `stealer_count`. A paying user with a real exposure saw a clean result.
3. **Onboarding's terms and privacy links were `relayshield.net/terms` and `/privacy`**, the Carrd
   404 recorded on 2026-08-01. Fixed to the subdomains. The same class of mistake as the
   developer-URL rule, in the one screen every new user sees.
4. **Onboarding made a new user paste a 44-character address and then said the email check
   "unlocks once your subscription is linked".** The connect button existed in WalletsScreen and
   had one caller. Onboarding now connects, scans, and offers the check before asking for anything.

### WHAT THIS BUILD CANNOT FIX, AND SAYING SO IS THE POINT

**Nothing in v1.7.0 changes who can install the app.** The Solana dApp Store serves Solana Mobile
hardware; whether it installs on an ordinary Android phone is UNVERIFIED and decisive for every
plan to point the blog, the extension and the developers page at it. If it does not, the reason
for low demand is distribution and no amount of copy fixes it, and Google Play is the real
change. Read the Play crypto-app policy (secondary reporting says exchanges and custodial wallets
need licensing and non-custodial are excluded) before porting.

**Hold further store updates after this one** until the counters show real paywall traffic.

### OPEN, AND NOT VERIFIED THIS SESSION

* `relayshield_breach_cache` creation is still unconfirmed, so the free check's HIBP half falls
  through to a live call every time until `sh tools/setup_breach_cache.sh` has run. HIBP's rate
  limit is shared with the bots and every paying customer, so a promoted free check raises that
  exposure.
* Whether Hudson Rock's free Cavalier API permits commercial in-app use is UNREAD. Read their
  terms before the free check is promoted.
* The listing still says "Tech E&O and Cyber Insurance coverage" and "every alert is
  cryptographically verified". Neither is verifiable from this repo. Confirm both or drop them.
* The store copy must be pasted into the portal at the same time as the v1.7.0 build, never
  before: the free check and connect-and-scan do not exist in v1.6.0.

## 2026-10-06: THE v1.6.0 SCREENS FAILED FOR A PARTNER BECAUSE ENTITLEMENT IS FLAGS ON A RECORD NOBODY CAN SEE FROM THE REPO

**Asked as "will the v1.7.0 changes work for Arjen?"** He is a RelayShield partner holding a free
licence: not a trial user and not a paying subscriber. **The honest answer is that nothing in this
repository can say**, and that is the finding.

**What decides it, read from code rather than recalled.** Every paid CS Mobile call is admitted by
`is_cs_mobile_call = bool(key_record.get("cs_mobile_access")) and path in
CS_MOBILE_ALLOWED_ENDPOINTS` in `handle_metered_request`, and `cs_mobile_access` is written by exactly
one path: the Stripe webhook provisioning a key for a `CS_MOBILE_PRICE_IDS` subscription. A person
given a licence by hand never went through it, so unless somebody set the flag on his record the
paid screens fall through to the Stripe meter branch and 402. **Both the app's key link
(`/developer/cs-mobile-link`) and the billing portal also require the flag**, so a key without it
cannot even be linked by email.

`_find_key_by_email` does not check `active` either, while `_verify_rs_api_key` requires it. His
history makes that a live question: the code's own comment calls his a duplicate checkout "that was
later refunded/cancelled".

**What v1.7.0 changes for him, and what it does not.** He has a key, so he keeps the PAID Email Check
(the free check only runs for `!apiKey`), and the `stealer_count` fix helps him. Neither touches the
flag. The attack chain screen, SIM swap and every other paid call depend on the flag alone.

**`tools/diagnose_cs_partner_key.py --email <address>` is the read.** It prints every record for that
address (key last six characters only), `active`, `cs_mobile_access`, subscription and customer ids
present or absent, credits and free calls, and the endpoints the branch covers, parsed from
`relayshield_api.py` so there is one copy. It evaluates only the cs_mobile branch and says so. **The
fix is a write on a live record and goes in a separate step after Andrew has read the output**
(rule C): set `cs_mobile_access` true and `active` true, leave Stripe fields absent so he can never
be billed, and confirm the app's push token registers under that same key because the SIM swap
push join is on the key.

**The general form: an entitlement decided by flags written by one provisioning path is invisible to
every person provisioned another way.** Partners, staff and test accounts all hit it, and each
fails with a 402 that looks like a bug in the feature.

## 2026-10-06: STATE FROM ANDREW, SO THE NEXT SESSION DOES NOT RE-ASK

* **Solana dApp Store: hold further updates until real trial or paywall activity exists.** Agreed.
  **Arjen is travelling to London for a Solana event this autumn and will promote the app there**, so
  the Solana listing is the right surface for that moment even though Google Play is a roadmap item.
* **The Tech E&O and Cyber Insurance claim is TRUE** (Andrew confirmed he carries both), and so is the
  listing's "every alert is cryptographically verified" line per his instruction that the
  unconfirmed claims are valid. The listing keeps both.
* **I mislabelled the app.** I wrote that non-custodial wallets "like this one" are excluded from
  Google Play's crypto policy. Crypto Shield Mobile is not a wallet of any kind: it holds no keys or
  funds and is a read-only security monitor. Whether Play's wallet and exchange rules reach a
  monitoring app that CONNECTS to a wallet is the real question and it is UNREAD: support.google.com
  is egress-blocked, and only secondary reporting was seen (licensing for exchanges and custodial
  wallets). Read Play's own cryptocurrency and Financial Features declaration pages before a port.
* **FD-13, xAI Grok Build marketplace: PR #612 is still OPEN with no reviews, no assignees and no
  maintainer comment**, read from the public PR page on 2026-10-06. Latest activity is the
  2026-09-08 team-review request, so 28 days of silence. The rule recorded on 2026-09-08 stands: do
  NOT push to its branch while it waits, because a push re-arms the first-time-contributor approval
  gate.
* **TODO, when v1.7.0 is uploaded: paste the strengthened store copy into the Solana publisher
  portal.** It is already in `crypto-shield-app/store-assets/dapp-store-metadata.md` (subtitle "Is
  your crypto email already in a leak?", the free-check lead, no vendor names). Never before the
  build: the free check does not exist in v1.6.0.
* **The v1.7.0 build is blocked on a JDK on Andrew's Mac**: `./gradlew assembleRelease` reported
  "Unable to locate a Java Runtime". `TODO.md` item 57 records the real build route as gradle with
  `cryptoshield-release.keystore`, so a JDK once existed and has gone, plausibly with the move of the
  clone to `~/dev/relayshield`. The EXISTING path to find it first: `/usr/libexec/java_home -V`, then
  Android Studio's bundled runtime.

## 2026-10-06: THE VIRUSTOTAL KEY WAS UNCOUNTED, AND ONE ENDPOINT LET ANYONE SPEND IT

VirusTotal emailed that the free key's 500-a-day allowance (resets 00:00 UTC, every request counts: lookup,
submission and each poll) was spent. **The first diagnostic returned ZERO for every log line it knew about**,
which is the finding: the burn was not coming from any surface that logs a VT call.

**THE LEAK.** `GET /v1/result/{id}` and `GET /v1/payg/result/{id}` were unauthenticated, uncapped, and spent one
VT request per call on our key whatever id was supplied. A failed poll logs only at ERROR, so a probing crawler
leaves almost nothing behind. UNPROVEN as the cause: the diagnostic now counts `path=/v1/result` requests
exactly (every request logs its path), so run it for the answer rather than trusting this paragraph.

**WHAT SHIPPED (`d42f48b`).** `relayshield_vt_budget.py`: a daily budget with per-caller, bulk and global caps
(fails OPEN, the opposite of the breach partner budget, because here failing open is exactly the old behaviour),
a 6h/24h verdict cache and an analysis-id mapping, all in the existing `relayshield_demo_key_usage` table so no
IAM grant is needed (the shared role has no room). `handle_result` now polls only analyses this API issued.
Every VT request site in the API and both bots charges first, and `test_vt_budget.py` fails if one does not.
Every allowed call logs `vt_call surface= kind= caller=`. The checkemail Worker now sends `x-rs-source`
(needs a Worker deploy to take effect). The scan-url log lines no longer carry the raw URL.

**THE EXISTING `relayshield_vt_url_cache` TABLE HAS NO CREATION SCRIPT AND NO IAM REFERENCE ANYWHERE**, so the
composite check's "24h cache" is very probably inert, the breach cache's twin. Not created: the new cache does
not use it.

**PRIVACY POLICY.** Another session rewrote it on `main` (Section 11, 90 days). Mine was the stale one; main is
the base now, with the free-email-check disclosure re-added. UNVERIFIED claim in it: the bot section says links
are not logged readably, but the WhatsApp handler logs `url=%s` in plaintext (`VT URL scan complete`).

## 2026-10-06: THE VT URL CACHE HAS A SCRIPT, THE EMAIL CHECKER IS COUNTED, AND THE MUSE KEY IS A TOOL NOW

* **`relayshield_vt_url_cache` was never created and no script ever created it**, so the composite check's "24h cache" was inert and every fallback spent a VT request. `tools/setup_vt_url_cache.sh` creates it (hash key `url_hash`, TTL on `ttl`), and `tools/grant_breach_cache_access.py --table relayshield_vt_url_cache` extends the existing managed policy. Each table has its OWN statement Sid, because the merge drops a statement with its Sid before appending and a shared Sid would make the second grant delete the first. Dry run first, then `--apply`.
* **`checkemail_use` is a telemetry event.** The Worker posts one ping per message it actually processes, BEFORE the rate limit (a person turned away is still a user), skipped for the exempt allowlist, fail-open via `ctx.waitUntil`. The identifier is an HMAC of the sender keyed with `RS_API_KEY`, never the address: a bare SHA-256 of an email is reversible by hashing candidates. The weekly report gained unique, new-this-week and total rows for the checker, and new-this-week for Chrome and Mini App. **"New" means FIRST seen this week**, not seen this week.
* **DEPLOY TRAP, UNFIXED: `relayshield_telemetry.py` is in the `paths:` trigger of `deploy_lambdas.yml` and NOT in `LAMBDA_MAP`.** A push deploys nothing, and the file looks wired. The live function name is UNVERIFIED (nothing in the repo names it); `sh tools/handler_drift.sh relayshield_telemetry.py` resolves it from AWS and reads the diff. `relayshield_weekly_metrics` and the checkemail Worker likewise need hand deploys. Until the telemetry Lambda is updated it answers 400 to `checkemail_use`, and the Worker swallows that, so nothing is counted and nothing errors.
* **`tools/setup_partner_key.py` was brought in from the unmerged `claude/gallant-hawking-4oerzg` on its own**, not the branch. Its closing text says the key is "scoped to /v1/metered/breach only", which is true of that branch and incomplete on main: here a valid key skips the per-IP cap on every keyless endpoint. See the credentials section in `muse_connector_submission_2026-09-22.md`.
* **Stale bytecode lies after a same-size mutation proof.** `<` to `>` keeps the file size, `cp` restores within the same second, and Python keeps the mutated `.pyc`: a correct file failed three tests. `rm -rf __pycache__` between proof steps.
* **`test_weekly_metrics.py`'s email fixture was missing `users_by_channel` and `telemetry`**, so three tests errored on clean main. Repaired.

## 2026-10-06 (later): STATE FROM ANDREW, THE HUDSON ROCK TERMS ARE STILL UNREAD, AND CANCELLING ARJEN'S STRIPE SUBSCRIPTION WOULD REVOKE HIS ACCESS

* **Breach-cache grant: NOT closed. I misread "close the outcome" as "it is done"; Andrew meant the CODE for the grant should exist so the table stops being inert.** The code does: `tools/grant_breach_cache_access.py` (tested, 10 tests), measured need being `implicitDeny` on `GetItem` and `PutItem` for `relayshield_breach_cache` against `relayshield-api`'s role. What remains is the operator run, dry run first then `--apply`, which cannot be automated: a role cannot widen its own permissions, so Actions' deploy role cannot make this grant. The VT URL cache is the same pattern with `--table relayshield_vt_url_cache`.
* **The Muse partner key already exists and Andrew has entered it in the Muse credentials form.** `tools/setup_partner_key.py` does not need to run for `muse_connector`.
* **The privacy page is settled.** The live version is current and valid; do not diff or redeploy it. The WhatsApp `url=%s` plaintext log line versus the policy's "not recorded in a readable form" claim was NOT examined and stays open as a code question, not a page question.
* **Hudson Rock Cavalier terms: NOT READ.** `docs.hudsonrock.com`, `cavalier.hudsonrock.com` and `www.hudsonrock.com` are all egress-blocked (WebFetch refuses, curl returns 000), and search returned nothing quoting terms: the one result that mentioned terms was Ransomware.live's, which is a different company and says nothing about Cavalier. Secondary sources describe it as a free community API needing no key; none states attribution or commercial-use conditions, and absence from a summary is not absence from the terms. **Andrew's read, one look in a browser:** the Terms link on `cavalier.hudsonrock.com/docs`, looking for commercial use, attribution and redistribution. If attribution is required, it collides with the no-vendor-names rule and the choice is his.
* **ARJEN ALREADY HAS A 100% DISCOUNT ON HIS STRIPE SUBSCRIPTION (Andrew, 2026-10-06), so there is nothing to cancel and the flag stays.** The note below is the reason NOT to cancel it.
* **CANCELLING A CS MOBILE SUBSCRIPTION IN STRIPE REVOKES THE FLAG.** `customer.subscription.deleted` for a `CS_MOBILE_PRICE_IDS` price calls `_revoke_cs_mobile_access` on the key record whose `stripe_subscription_id` matches (`relayshield_developer_signup.py`, around line 1769). Arjen's two records both carry Stripe ids, so the obvious fix for "do not bill him" removes the access we set on purpose. Order matters: read the subscription status first (Stripe dashboard, customer by his email), cancel only an active or trialing one, wait for the webhook, THEN run `tools/set_cs_mobile_access.py --email ... --key-suffix <suffix> --apply`. A replayed deletion event would revoke it again; nothing here prevents that.

* **Muse Business verification fails after the emailed code is entered**: the page answers "We couldn't confirm the latest status. Reload the saved details before trying again" every time. That is a Muse platform message, not ours, and nothing in this repo or container can see their backend. The email field already shows masked and greyed, which suggests the address is saved and the page is showing stale state. Steps in cheapest-first order are in the reply of 2026-10-06; the outcome is not yet known.

## 2026-10-06 (later): "WAS IT A SCRAPER" CANNOT BE ANSWERED FOR THE DAY IT HAPPENED, AND THE REASON WAS A PRIVACY CHOICE

Asked as whether a scraper drained the VT quota. **It cannot be determined from anything that exists for 2026-10-05 or 06.** The API's per-request log line carried `method` and `path` only, `relayshield_vt_budget.py` states "no IP is written", and every caller without a key was `-`, so a scraper and an honest user were the same line. The CloudWatch counts (`tools/diagnose_vt_usage.py`) can say whether `/v1/result` volume was big enough to spend the day, not who made it.

**What changed so the next spike is attributable:** callers with no key now get `anon_caller()`, a six-character hash of the UTC day plus the source IP (24 bits, rotates at midnight, about 256 candidate IPv4 addresses per value, logged and used as a per-day counter key, never stored). It is on the request line as `caller=`, in the `vt_call` lines, and the diagnostic groups `/v1/result` by it and prints a reading-aid verdict. **Side effect worth knowing: anonymous sources are now held to the 120-a-day per-caller cap**, which they were exempt from before. A shared NAT or office is one bucket.

The `/v1/result` leak itself was closed by the analysis-id mapping gate and does not depend on this. 7 new tests in `test_vt_budget.py`; the guard was proven by dropping the label and watching it fail.

## WHERE 2026-10-07 LEFT THINGS. READ THIS FIRST; IT SUPERSEDES THE 2026-10-06 FRAGMENTS ABOVE FOR "WHAT IS NEXT".

**Andrew stopped for the night.** Branch `claude/compassionate-bell-e3cfej`, last code commit `86053e8`, all of it pushed and unmerged.

### THE OPENAI LISTING IS LIVE, AND NO SESSION RECORDED IT UNTIL THE SCREENSHOTS

**"RelayShield Scam Checks", v1.0.0, Security, ChatGPT plugin directory.** Four tools (link check, wallet screening, email phishing scoring, breached-email lookup), free, no key, and it says it never reports anything as safe. This is FD-14 closing; `FRONT_DOORS.md` is updated. **The repo carried no record of the submission**: a `git grep` of `origin/main` for an OpenAI key finds only `package-lock.json` hits. The route/key work (`CONSUMER_ROUTES["openai"]`, `?source=openai`, `tg-miniapp-openai`, the `openai_connector` partner key) exists only on unmerged `claude/gallant-hawking-4oerzg`, and whether that key was ever issued is unconfirmed. A free MCP server was built on `feature/scamkit-demo-screen` (`6f1c602`, "free-server 0.3.0"); an `mcp__...free-mcp_hf_space` server is also attached to some sessions.

**Three things to settle, in this order, none checked yet:**
1. **Its description quotes stale figures** ("115 monitored Telegram marketplaces, 494K+ indicators, 7.8M+ citations"). Measured: 123 channels, 661,609 distinct indicators (2026-09-30), 8.3M+ citations. Per the standing rule, propose copy that names sources, not counts, since we cannot cheaply edit the listing. The edit is Andrew's to submit.
2. **Which attribution string does the connector send?** Without one, ChatGPT arrivals are indistinguishable. Register the key in all three lists BEFORE changing anything.
3. **Does it hit the keyless endpoints, and under the 300/day per-IP cap?** A partner key lifts the cap, but ChatGPT's egress IPs are shared, so the cap may bite all users at once. The breach tool shares the HIBP key with every paying customer, so `relayshield_breach_cache` must exist first (below). Keep it keyless: the compliance gate forbids selling digital goods inside the host.

### NEXT-SESSION TODOS, IN ORDER

1. **Andrew's stuck merge.** His clone reported `cloudflare_worker_privacy.js: needs merge`. Ask for the output of the read-only diagnostic (branch, last commit, `git status --short`, MERGE_HEAD present?). Expect `UU cloudflare_worker_privacy.js`. His rule: the live privacy page is current and valid, so keep that version, then `git add` it and `git commit --no-edit`, or `git merge --abort`. Then the standard merge block; a conflict in CLAUDE.md alone means keep both sides. Never `git add -A`.
2. **Apply the cache grants, dry run first, and send me the output before `--apply`.**
   `AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/grant_breach_cache_access.py` then `--apply`.
   For the VT cache: `AWS_PROFILE=relayshield sh tools/setup_vt_url_cache.sh`, then the same grant tool with `--table relayshield_vt_url_cache`.
   `relayshield_breach_cache` creation (`sh tools/setup_breach_cache.sh`) is **still unconfirmed**. A role cannot widen its own permissions, so Actions cannot do the grants.
3. **Hand deploys, none of which CI does.** The telemetry Lambda (`relayshield_telemetry.py` is in the `paths:` trigger but NOT `LAMBDA_MAP`; run `sh tools/handler_drift.sh relayshield_telemetry.py` to resolve the live name and read the diff first). `relayshield-weekly-metrics`. The checkemail Worker (needs the new `recordUse` call). **Until the telemetry Lambda is updated it answers 400 to `checkemail_use` and the Worker swallows it, so nothing is counted and nothing errors.**
4. **Run `tools/diagnose_vt_usage.py --date 2026-10-05` and `--date 2026-10-06`** after the merge deploys. For those days the answer is volume only: there is no caller label. The next spike carries `caller=`. Anonymous sources are now capped at 120 a day; Andrew decides whether to keep the day-rotating hashed-IP logging.
5. **Hudson Rock Cavalier terms: still UNREAD** (all their hosts are egress-blocked). Andrew's read: the Terms link on `cavalier.hudsonrock.com/docs`, looking for commercial use, attribution and redistribution. If attribution is required it collides with the no-vendor-names rule and the choice is his.
6. **Muse**: connector shows "Submitted"; the Business verification error was Muse-side. Nothing to do; if it recurs, contact Muse support.
7. **Arjen**: 100% Stripe discount exists. **Do not cancel his subscription**, because cancelling revokes `cs_mobile_access`. If he still gets a 402 on paid screens in v1.7.0, suspect his other key record (`...84a19f`, flag false); `tools/set_cs_mobile_access.py` sets it.

### CARRIED, UNCHANGED
Privacy-policy claim vs the WhatsApp `url=%s` plaintext log line (a code question, not a page question). CS Mobile v1.7.0 build blocked on a JDK on his Mac (`/usr/libexec/java_home -V`, or Android Studio's `jbr`); paste the store copy only together with the build. Grok PR #612: leave untouched. D&B change decision about 2026-10-10, then the Chrome Web Store support ticket. `support@relayshield.net` mailbox unconfirmed. `tools/backfill_first_seen.py --apply` unconfirmed. Decision on `claude/gallant-hawking-4oerzg` (it holds the OpenAI route work, so item 1 above feeds it). `WA_NUMBER` in the Mini App Worker. StoreBot. Smithery FD-11. IAM split beyond `relayshield-intel-feed`.

## 2026-10-08: THE VT DRAIN IS CLOSED IN CODE, BOTH CACHES ARE GRANTED, AND THE ONLY THING LEFT IS TO WATCH IT

**Root cause (strongly supported, not proven).** `/v1/composite-check` is keyless and, from 2026-10-04
(579de4c), fell back to a VirusTotal URL report on an unknown URL. The Mini App, the Chrome extension and the
Telegram widget have all called it since 2026-10-02 (aa697dd). On 2026-10-06 and 10-07 one client looping on
429s (capped at 300 served a day) plus a pool of about 37 cloud IPs each under the 300 per-IP cap spent the
500-a-day key: roughly 300 + 845 against 1,100 composite requests. The per-IP cap cannot stop a pool.
Inferred from the counts, not proven; Telegram `/scan` and any other use of the same VT account are unmeasured.

**Fix, on main and deployed (deploy_lambdas run 199, `331aec3`).** The fallback runs for callers with a
VERIFIED API key only. `_VT_CTX["keyed"]` is reset every invocation and set from `_verify_rs_api_key`; an
invented key does not count. Anonymous requests log `vt_fallback_withheld`. Tests go through `lambda_handler`.

**AWS-side, done 2026-10-08 by Andrew and confirmed from the script's own output:**
- `relayshield_vt_url_cache` grant APPLIED: GetItem and PutItem `allowed` (were `implicitDeny`, so that cache
  had never worked and every repeat URL for a keyed caller was a fresh VT request).
- `relayshield_breach_cache` grant APPLIED: same result (also `implicitDeny` before, so every breach check was
  a live HIBP call on a key shared with the bots and paying customers).
- `relayshield_breach_cache` exists, ACTIVE, TTL ENABLED on `ttl`.
- Both live as statements `VtUrlCacheReadWrite` and `BreachCacheReadWrite` in the managed policy
  `relayshield-first-seen-write` (552 of 6144 characters). The grant script pruned v1 to stay inside IAM's
  5-version cap. Roles cannot widen their own permissions, so Actions could not have done this.

**To confirm it held, after a day of traffic:**
`AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/diagnose_vt_usage.py | grep -A12 "VT requests actually spent"`
Expect no anonymous composite spend. The "VT fallback skipped or failed" row will be large, which is the gate
working. If the VirusTotal quota email does not arrive tomorrow, that is the first sign it held.

## WHERE 2026-10-08 LEFT THINGS. READ THIS FIRST; IT SUPERSEDES THE 2026-10-07 LIST FOR "WHAT IS NEXT".

Everything below was established this session and is not recorded elsewhere. The VT root cause, fix and the
two cache grants are in the section directly above this one and are not repeated.

### HOW THE VT DIAGNOSIS ACTUALLY WENT, BECAUSE THE FIRST ANSWER WAS WRONG

**I told Andrew the free surfaces had been "ruled out". They had not.** `tools/diagnose_vt_usage.py`'s
docstring said the Mini App, the Chrome extension and the widget do not call VirusTotal. That was true until
2026-10-02 (`aa697dd`, all three moved to `/v1/composite-check`) and false from 2026-10-04 (`579de4c`, the
composite check gained a VT fallback). **A docstring that rules a surface out is a lead, not a fact**, and this
one had been stale for four days while two quota emails arrived. It is corrected in the tool, and the tool now
counts `composite-check signals=` lines (an upper bound on fallback spend) and `VT fallback` lines.

**The measurement that settled it was a different table.** The composite log line carries no source, so the
diagnostic could say HOW MANY but not WHO. `_check_keyless_ip_quota` already wrote one counter per source IP per
UTC day to `relayshield_demo_key_usage` (key `ip#<ip>#<YYYY-MM-DD>`, 3-day TTL), so the answer was already in
DynamoDB. `tools/keyless_ip_top.py` reads it (read-only, masks to two octets by default; IPs are personal data
and are not recorded here). Shape on 2026-10-06/07: one client looping on 429s (5,113 attempts one day, 2,120 the
next, capped at 300 served) plus a pool of about 37 cloud addresses each under the per-IP cap. **A per-IP cap
cannot stop a pool**, which is why the fix is a gate on who may spend the key and not a lower cap.

**The counter keeps incrementing past the cap**, so "5,113" is attempts and "300" is what was served. Quoting
the first as spend would overstate it.

**Not covered by this fix and still unmeasured:** Telegram `/scan` (logs nothing countable), anything else on the
same VT account, and Andrew's own use of the VT web UI on that login.

### THREE TEST-WRITING SLIPS, ALL CAUGHT BY RUNNING, ALL THE SAME FAMILY

1. **A splice guard matched my own comment.** `"VtFallbackIsKeyedOnly" not in s` was satisfied by a comment
   that named the class, so the splice refused, and my first "proof" runs then ran against a file that did not
   contain the new tests and proved nothing. The guard is `"class VtFallbackIsKeyedOnly" not in s`. This is the
   seventh occurrence of a guard fooled by prose in this repo; the rule stays: strip comments in the FIRST version.
2. **An `ast.unparse` comparison assumed double quotes.** `ast.unparse` emits single quotes, so a test comparing
   to `'_VT_CTX["keyed"]'` failed on correct code. Check the node (Subscript, Constant), never its string form.
3. **A decoy row was counted.** The stub test for `keyless_ip_top.py` surfaced a `demo#abc#...` row because the
   filter was server-side only. The tool re-checks `startswith("ip#")` and the day suffix client-side.

### AWS PARTNER CENTRAL, DONE THIS SESSION (all Andrew's clicks)

* **Enrolled in the Software Path** (Partner Scorecard confirmed it pointed the same way). APN membership is
  not automatic from account `239677749008`; Dave Shapiro's "self-service for early stage partners" means
  Marketplace listing needs no APN tier, but co-sell programmes do.
* **A Partner Central solution was created** from the four public Marketplace products (Bundle A, B, D and the
  TI product). **"Update visibility" was deliberately NOT clicked.** Reason: the Partner Solutions Finder is a
  Partner Central surface, not AWS Marketplace, and nothing needs to be public for the Foundational Technical
  Review to start. A multi-product solution is possible later.
* **THE RULE FROM ANDREW: no "Bundle D" (or any internal bundle name) in anything a buyer or AWS reviewer reads.**
  The solution Value proposition, Description, Integration details and the three use-case details were rewritten
  to describe capabilities and sources only, with no corpus counts (MEASUREMENT DOCTRINE). The copy lives in the
  chat only; if it is needed again, rebuild it from `aws_bundle_d_short_description.txt` and
  `aws_marketplace/bundle_d_listing_copy.json` and strip the names.
* **UNVERIFIED, AWS pages are egress-blocked from the container:** ISV Accelerate's thresholds (I recalled "5
  launched plus 15 qualified opportunities in 12 months" and a small revenue floor). Read AWS's own page before
  relying on either number. Andrew's catch-22 is real: ISV Accelerate wants ACE opportunities, ACE needs the
  Software Path, and the first opportunities have to come from somewhere.

### THE STATE OF EACH SURFACE THE VT QUESTION TOUCHED, FROM ANDREW

* **Mini App: not the source.** He has run no URL scans.
* **Chrome extension: tabled.** A zip submitted after the store's privacy-policy change did not pass; changes are
  resubmitted and pending review. (This sits oddly beside the 2026-10-02 record of a live v0.2.1 listing; both
  are Andrew's reports. Treat the CURRENT review status as unknown until he reads the dashboard.)
* **Shopify screening Worker** calls composite-check with a per-shop key, so it is a keyed caller and keeps the
  VT fallback. It returns 200 on failure, so a failing upstream does not become a retry storm.

### NEXT-SESSION TODOS, IN ORDER

1. **Prove the VT fix held.** After a full UTC day of traffic:
   `AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/diagnose_vt_usage.py | grep -A12 "VT requests actually spent"`.
   Expect no anonymous composite spend and a large "VT fallback skipped or failed" row. If a quota email arrives
   anyway, send the output: it names the surface, and Telegram `/scan` is the spender still uncounted.
2. **Hand deploys that CI does not do, status UNKNOWN since 2026-10-07:** the telemetry Lambda
   (`relayshield_telemetry.py` is in the `paths:` trigger but not `LAMBDA_MAP`; `sh tools/handler_drift.sh
   relayshield_telemetry.py` resolves the live name and reads the diff first), `relayshield-weekly-metrics`,
   and the checkemail Worker. Until the telemetry Lambda is updated it answers 400 to `checkemail_use` and
   nothing is counted or logged as an error.
3. **Partner Central, in this order:** start the Foundational Technical Review on the solution; log the first
   ACE opportunities and confirm the Opportunities page works (there was a migration banner); open the
   Co-Selling with AWS module; ask Dave Shapiro for a Partner Development Manager intro; read AWS's ISV
   Accelerate page for the real thresholds. Do not click "Update visibility".
4. **OpenAI listing ("RelayShield Scam Checks", live).** Its description quotes stale figures (115 channels,
   494K indicators, 7.8M citations; measured 123, 661,609 distinct, 8.3M+). Propose copy that names sources, not
   counts. Settle which attribution key it sends and register it in all three lists BEFORE changing anything.
   The route/key work for it sits on unmerged `claude/gallant-hawking-4oerzg`.
5. **Hudson Rock Cavalier terms: still UNREAD.** Andrew's one look: the Terms link on
   `cavalier.hudsonrock.com/docs` for commercial use, attribution, redistribution. If attribution is required it
   collides with the no-vendor-names rule and the choice is his.
6. **CS Mobile v1.7.0 build is blocked on a JDK on Andrew's Mac**
   (`/usr/libexec/java_home -V`, else Android Studio's bundled `jbr`). Paste the store copy only together with
   the build. Arjen: 100% Stripe discount exists, so do NOT cancel his subscription (cancelling revokes
   `cs_mobile_access`); if he still gets a 402 on paid screens, suspect his other key record.
7. **Chrome Web Store:** read the CURRENT review status on the dashboard. D&B change decision is due about
   2026-10-10; if approved, open a Chrome support ticket asking it to re-pull trader info.
8. **`support@relayshield.net` mailbox is still unconfirmed** and is the contact on the live XSOAR pack.
9. **`relayshield-signup-api` is reported by `check_deploy_invoke_policy.py` as missing from the invoke
   policy.** Seen in passing, unrelated to the VT work, not investigated. It is run 134's shape waiting for its
   first mapped deploy.
10. **Carried, unchanged:** `tools/backfill_first_seen.py --apply` unconfirmed; `WA_NUMBER` empty in both
    Workers; StoreBot submission; Smithery FD-11; the decision on `claude/gallant-hawking-4oerzg`; mapping
    `relayshield_watchlist_monitor.py` and `relayshield-mpp-settlement` in the deployer; INTEL-5; the IAM split
    beyond `relayshield-intel-feed`; the WhatsApp plaintext `url=%s` log line versus the privacy page's claim.

## 2026-10-08: THE AWS FTR NEEDS A SINGLE-PRODUCT SOLUTION, AND THE PARTNER CENTRAL SOLUTION WE BUILT HAS FOUR

**Found by reading AWS's FTR request guide (via search results quoting it; docs.aws.amazon.com is
egress-blocked, so this is SECONDARY evidence, and the FTR Guide inside Partner Central is the
authority).** The Validation tab's prerequisite check requires the solution to link to EXACTLY ONE
AWS Marketplace product, of a software type (SaaS, AMI, Container or ML), and checks run in
sequence so later ones stay blocked until earlier ones pass.

**The solution created on 2026-10-08 was built from FOUR public products (Bundle A, Bundle B,
Bundle D and the TI product), so it will fail that first check.** Do not edit it and do not click
"Update visibility" on it. The FTR needs a SEPARATE single-product solution.

**Route** (navigation from search results, unverified): Partner Central, Build, Solutions, open the
solution, Validation tab, Request validation, then the self-assessment checklist and evidence
uploads (3 MB each). AWS says review is AI-assisted, with an expert contact within two weeks if it
fails. Approval validity is reported as two years by one source and three by another; read the FTR
Guide.

**Evidence required: a SOC 2 Type II report OR a Well-Architected Framework Review (WAFR)** covering
the solution's primary AWS-hosted workload. We have no SOC 2, so the WAFR (run in the Well-Architected
Tool, account 239677749008) is the realistic route and the longest lead item. It does NOT depend on
the solution existing, only on its scope matching the product the solution links.

**The product must also show it runs on AWS, with an architecture diagram uploaded in the
Marketplace Management Portal.** Bundle B's Architecture details tab was left on "None of the above"
because third-party vendor APIs run outside AWS; check what the chosen product's tab says before
requesting validation. `bundle_b_architecture_details_2026-09-20.md` has that reasoning.

**Chosen product: Bundle D (`prod-kkvurtspreofy`)**, the longest-public and strongest listing. Its
declared MCP endpoint is a Hugging Face Space, but `hf-space-mcp-server/app.py` is a thin proxy that
posts to `API_BASE_URL = https://api.relayshield.net`, so the compute and data are API Gateway,
Lambda and DynamoDB in 239677749008. Say so in the diagram and the WAFR scope rather than leaving
the HF host to read as the workload.

## 2026-10-08 (later): WEEKLY METRICS SHOWS THE CUMULATIVE INDICATOR COUNT BESIDE THE WEEKLY INCREMENT

**Measured by the backfill's own output, 2026-10-08: 687,011 distinct indicators, first-seen range
2026-06-21 to 2026-10-08.** It was 661,609 on 2026-09-30, so the distinct count grows by tens of
thousands a week. Per MEASUREMENT DOCTRINE this is internal reporting, not a number for a listing.
**Whether `--apply` ran is NOT established**: the dry run and the apply both print that line, and the
`wrote N, skipped M ... failure(s)` line that proves a write was not pasted back.

**The report was already cumulative in code.** `_unique_indicators()` counts every row of
`relayshield_intel_first_seen`, so a small figure in the email meant the table was under-seeded, not
that the query was incremental. What was missing was the weekly increment beside it. Added:
`_new_unique_indicators()` = rows whose `first_seen` falls in the last 7 days, same table and same
definition, so cumulative minus new is last week's cumulative. The email now reads "Unique indicators
(cumulative, all-time)" with "+N new this week" under it. Three tests added to
`test_weekly_metrics.py` (29 pass), each proven by reintroducing its defect: wrong table, and the
dispatcher entry removed.

**NOT DEPLOYED.** `relayshield_weekly_metrics.py` has no CI deploy path, so the merge alone changes
nothing in AWS. Three commits to it landed 2026-10-06 and whether they were hand-deployed is
unknown, so read `sh tools/handler_drift.sh relayshield_weekly_metrics.py` before deploying.

## 2026-10-08 (later): FTR SOLUTION VALUES, AND WHAT THE WAFR MUST COVER

The single-product Partner Central solution for the FTR links ONE Marketplace product, the
Agentic Attack Surface listing (`prod-kkvurtspreofy`). Names carry no internal bundle letter, per
Andrew's rule that nothing a buyer or AWS reviewer reads says "Bundle D". Solution name
`RelayShield Agentic Attack Surface API - FTR`, external title `RelayShield Agentic Attack Surface
API`. Both are unverified against uniqueness: the form says each must be unique, so a collision with
`RelayShield Agentic Attack Surface API` for BOTH the internal name and the external title (Andrew
dropped the " - FTR" suffix I first suggested, 2026-10-08). Both are unverified against uniqueness: the form says each must be unique, so a collision with
the four-product solution's name is possible and the form will say so.

The Well-Architected review scope is the `api.relayshield.net` stack in account `239677749008`,
region `us-east-1` (read from `deploy_lambdas.yml`), described by capability and with no corpus
counts. Which lens AWS expects for the FTR is UNVERIFIED (docs.aws.amazon.com is egress-blocked):
the Framework lens is the baseline, and the FTR Guide inside Partner Central is the authority.

**Drift read 2026-10-08, `sh tools/handler_drift.sh relayshield_weekly_metrics.py`:** live
`relayshield-weekly-metrics` (python3.12, handler `relayshield_weekly_metrics.lambda_handler`,
LastModified 2026-09-28T23:52:37Z) is byte-identical to commit `a56ee4ad` and merely STALE: nothing
live-only, nothing to recover. It lacks the three 2026-10-06 commits (channel breakdown, telemetry,
email-checker rows) and the cumulative-plus-weekly indicator rows, and it is a single-file package.
It is still in neither `deploy_lambdas.yml` nor the invoke policy, so a deploy is a hand
`update-function-code` until it is mapped (the mapping commit must touch the `.py`).

## 2026-10-08 (later): THE SIX MARKETPLACE SAAS PRODUCTS, BY ID, READ FROM `list-entities`

Read by Andrew from AWS (`aws marketplace-catalog list-entities`, SaaSProduct), not recalled. **The
Name column is the entity name, and it does NOT match the "Agentic Attack Surface" label this file
has used for `prod-kkvurtspreofy`.**

    prod-kkvurtspreofy   RelayShield - Consumption Security API Bundles            Public   (the old "Bundle D")
    prod-szi2wdww3obry   RelayShield - Attack Surface & Supply Chain API            Public   (Bundle B, the live one)
    prod-v5nr5gjtdnofi   RelayShield - Attack Surface & Supply Chain API            Restricted (duplicate)
    prod-p3ei5nmgufnnq   RelayShield - Attack Surface & Supply Chain API            Restricted (duplicate)
    prod-f5qkfsxlxs4qg   RelayShield - Core Identity Exposure API Bundle            Public   (Bundle A)
    prod-kb3ftelx44wlk   RelayShield - Threat Intelligence & Identity Security API  Public   (TI product)

**The Partner Central FTR solution ("RS Agentic Attack Surface API") was linked to a product Andrew
picked by display name as "Agentic Attack Surface and Supply Chain API", a title that appears in NO row
above.** The nearest match is the Attack Surface & Supply Chain API (Bundle B). Which entity it is
linked to is UNVERIFIED until the solution's Products section is read. Select by id, not name: this is
the seven-rejections lesson again, in a picker.

**RESOLVED 2026-10-08 (screenshot of the solution's Products tab):** solution `soln-aicwx4eiyofnm` ("RS Agentic Attack Surface API") is linked to **`prod-szi2wdww3obry`**, the live Attack Surface & Supply Chain API (Bundle B), not `prod-kkvurtspreofy`. The Products tab has an **Edit products** button, so the link is changeable. Recommendation given: keep Bundle B (public, real agreement, fulfillment and metering proven in our account) and rewrite the use-case details to match its capabilities. The use-case texts drafted earlier the same day describe agent screening and identity exposure and no longer fit.

**DECIDED 2026-10-08 (Andrew overruled the keep-Bundle-B recommendation):** the FTR solution is to be linked to **`prod-kkvurtspreofy`** ("RelayShield - Consumption Security API Bundles", the old Bundle D), on the grounds that it is the most attractive bundle to AWS partners. Steps: Products tab, Edit products, select by Product ID. The original agent-screening and identity-exposure use-case texts apply again, and the solution name "RS Agentic Attack Surface API" fits. **Known cost, recorded so it is not rediscovered:** this product's declared MCP endpoint is a Hugging Face Space outside AWS, so the architecture diagram and the WAFR scope must show the compute and data (API Gateway, Lambda, DynamoDB in 239677749008) as the workload and the Space as a thin proxy, and its Architecture details tab must be read before requesting validation.

## 2026-10-09: WAFR READS FOUND A ROOT ACCESS KEY, AND THE OIDC TRUST IS TIGHT

Read during the Well-Architected review for the AWS FTR, from Andrew's console and CLI output, not recalled.

* **A root user access key exists** (key id ends `N2XZ`, created about 279 days before 2026-10-09). Console shows last used 279 days ago, us-east-2, s3, so it has not been used since the day it was made. Root MFA is on (one virtual device). `get-account-summary` printed `1 1`: `AccountMFAEnabled=1`, `AccountAccessKeysPresent=1`. The `relayshield` CLI profile is the IAM user `relayshield-deployer`, NOT root, so the key is not what the CLI uses. Plan: deactivate (reversible), wait about a week, then delete. Do not delete it first: deactivating costs nothing and tells us whether anything unknown used it.
* **`relayshield-github-deploy`'s trust policy is scoped** to `repo:nzdsf2-gif/relayshield:ref:refs/heads/main` with `aud=sts.amazonaws.com`. The `sub` list names that same line twice, harmless but untidy. Only the main branch of this repo can assume the deploy role.
* **IAM Access Analyzer is NOT enabled in us-east-1**: `list-analyzers` returned nothing. It may exist in another region, unchecked. An account-type analyzer is free.
* `relayshield-deployer` is an IAM user, so its CLI credentials are long-lived keys, not temporary credentials.

## 2026-10-09 (later): ROOT KEY DEACTIVATED, ACCESS ANALYZER ENABLED. CONFIRMED BY ANDREW'S OUTPUT.

* **The root access key (ends `N2XZ`) was DEACTIVATED by Andrew on 2026-10-09**, not deleted. Delete it on or after 2026-10-16 if nothing has broken. Deactivation is reversible; deletion is not.
* **IAM Access Analyzer is ENABLED in us-east-1**: `arn:aws:access-analyzer:us-east-1:239677749008:analyzer/relayshield-account-analyzer`, type ACCOUNT (free external-access analyzer), created by the `relayshield-deployer` identity, so that identity holds `access-analyzer:CreateAnalyzer`. It has produced no reviewed findings yet; the WAFR box for analysing public and cross-account access stays unticked until Andrew has read the first findings in the console.

## 2026-10-10: WAFR SECURITY READS, AND KMS ROTATION TURNED ON. CONFIRMED BY ANDREW'S OUTPUT.

Read during the Well-Architected review for the AWS FTR, from his CLI, not recalled. An AWS write that
succeeds outside a session that can commit is invisible to every later session, so it is recorded here.

* **KMS automatic rotation was OFF on both customer-managed keys and is now ON** (enabled by Andrew
  2026-10-10, re-read `True` on both): `alias/relayshield-data-key` (`1479c3fa-88e9-4096-a736-32968ba5812f`)
  and `alias/relayshield-dynamodb-key` (`2ece080e-0cb0-499e-b2d1-6a496bbb4a1a`).
* **CloudTrail:** one multi-region trail, `relayshield-trail`, delivering to S3 bucket
  `relayshield-config-logs`. Log file validation and encryption on it are UNVERIFIED.
* **GuardDuty: no detector in us-east-1** (other regions unchecked). **Security Hub: not subscribed.**
  AWS Config recorder status UNVERIFIED.
* **No regional WAF web ACL found** (the first read printed nothing; the run had an extra output line, so
  re-run `aws wafv2 list-web-acls --scope REGIONAL --region us-east-1` alone to be certain). One API Gateway
  usage plan, `relayshield-growth`, throttles at 50 rps with burst 100, and applies to keyed requests only.
* **Zero Lambda functions are VPC-attached.**
* `.github/workflows/security_audit.yml` runs Bandit (fails on high), pip-audit and gitleaks on every push and
  pull request. No Dependabot or CodeQL.
* **Post-FTR improvement list:** regional WAF with a rate-based rule on the API, Lambda versions plus aliases
  for rollback, GuardDuty and Security Hub, Dependabot, a written data classification scheme, tracing and
  dashboards.
* WAFR answers given so far are in the session transcript only; OPS 1-11 and SEC 1-8 are done, SEC 9 is next.

## WHERE 2026-10-10 LEFT THINGS. THE AWS FTR WAFR IS HALF DONE. READ THIS FIRST FOR "WHAT IS NEXT".

**State, from Andrew's console and CLI, not recalled.** AWS Partner Central solution `soln-aicwx4eiyofnm`
("RS Agentic Attack Surface API") is linked to `prod-kkvurtspreofy`. The Well-Architected review is
workload "RelayShield API", Production, us-east-1, account 239677749008, Framework lens, 57 questions.
**Done: OPS 1-11 and SEC 1-11 (the whole Security pillar).** Next question: **REL 1**. About 40 remain
across Reliability, Performance Efficiency, Cost Optimization and Sustainability. Paste-ready answers were
given in chat only; the texts are not saved, so the rule for each remaining question is: tick only what
we can back up, state gaps in Notes, never claim a tool or practice we have not verified.

**How the review is evaluated (secondary sources; docs.aws.amazon.com is egress-blocked, the FTR Guide in
Partner Central is the authority).** The WAFR is a self-assessment: unticked practices become flagged risks,
nobody has a clean report. The FTR is the real review and uses the WAFR as evidence; AI-assisted, expert
contact within about two weeks if it fails, resubmittable. UNVERIFIED: the FTR checklist itself, and whether
unresolved high risks block approval. READ THAT SECTION OF THE FTR GUIDE BEFORE REQUESTING VALIDATION. An
overclaimed answer is what fails, because the evidence upload will not match it.

**What approval buys: credibility and co-sell eligibility (ACE), not a discovery flood.** Marketplace
search is the discovery surface that already works. UNVERIFIED: exact badge wording and programme
dependencies.

**Dave Shapiro and a Partner Development Manager.** His own words were "self-service for early stage
partners", so the likelier reason there is no PDM yet is that none is assigned at this stage, not that he is
unfamiliar with onboarding. Andrew chose to finish the WAFR and submit the validation request FIRST, then
write to Dave with the evidence. Ask WHO OWNS co-sell for early-stage ISVs, not for a PDM by name.

### TODOS FOR THE NEXT SESSION, IN ORDER

1. **Finish the WAFR: REL 1 onward.** Then Save milestone, Generate report (PDF under 3 MB).
2. **Optional reads that sharpen answers, all read-only, none run yet:** AWS Config recorder
   (`aws configservice describe-configuration-recorders`), and re-run `aws wafv2 list-web-acls --scope
   REGIONAL --region us-east-1` ALONE to confirm no WAF (the earlier run had an extra output line).
3. **Read Bundle D's Architecture details tab** (`prod-kkvurtspreofy`) in the Marketplace Management
   Portal, then produce an architecture diagram showing the Hugging Face Space as a thin proxy over
   API Gateway, Lambda and DynamoDB in 239677749008.
4. **Request validation** on the solution (Validation tab) with the WAFR report. Do NOT click "Update
   visibility" on the four-product solution.
5. **Email Dave Shapiro** after item 4, specifics first: Software Path enrollment, the single-product
   solution, the WAFR report attached, and the co-sell question. Claude drafts it.
6. **Delete the deactivated root access key** (ends N2XZ) on or after 2026-10-16 if nothing has broken.
7. **Decide on the Access Analyzer box in SEC 3** after reading the first findings in the console.
8. **Fixes the review exposed, cheapest first:** regional WAF with a rate-based rule on the API; run the
   test suite in CI (65 test files, none run by any workflow; some fail on clean main, so fix or exclude
   those first); Lambda versions plus aliases for rollback; Dependabot; a one-page written incident
   runbook (credential compromise, key leak, customer notification) if the Notes promised it; GuardDuty
   and Security Hub; a written data classification scheme; the IAM role split beyond
   `relayshield-intel-feed`.
9. **Hand-deploy `relayshield_weekly_metrics.py`**; the drift read says live is merely stale, nothing
   live-only. It is still in neither the deployer nor the invoke policy.
10. **Confirm `tools/backfill_first_seen.py --apply` ran** (dry run measured 687,011 distinct indicators
    on 2026-10-08).

**Carried, unchanged:** the 2026-10-08 list above (VT fix proof, telemetry Lambda hand deploy, Hudson Rock
terms, CS Mobile v1.7.0 build blocked on a JDK, Chrome Web Store review state, `support@relayshield.net`
mailbox, the OpenAI listing's stale figures, `relayshield-signup-api` missing from the invoke policy).

## WHERE 2026-10-11 LEFT THINGS. THE TWILIO "FRAUD" CAUSE IS NOT SETTLED, AND MY FIRST THEORY WAS A COINCIDENCE.

**2026-10-11.** After the PR #49 rate limit, I proposed that FREE-TIER KEYS reached the Twilio-backed
endpoints (a free key is minted from an email address alone and carries 100 calls, and neither
`/v1/metered/phone-reputation` nor `/v1/metered/sim-swap` was in `FREE_TIER_EXCLUDED_ENDPOINTS`). **That
hole was real and is closed, but the claim that it caused the $19.79 rested on one thing: about 14 keys
times 100 calls is about 1,407.** A number coincidence is a lead, not a finding, and Andrew's own
investigation then pointed at the Telegram Mini App instead.

**What is established, from the account and the code:**
* The Mini App page and the widget call only `composite-check`, `link-check`, `wallet-risk` and the
  watchlist routes. None reaches Twilio. Its only route to Twilio is through the bot it links to.
* The SIM swap monitor accounted for **393 lookups** in 2026-10-03 to 10-10 (215 runs, 1 to 3 users per
  run), **not 1,407**. 7 numbers are enrolled now, 1 consented in the window, 0 Telegram-delivered.
* **215 runs in 7 days is about 31 a day against the documented `rate(4 hours)`, which is 6.** Something
  ran it more often than its docstring says. The EventBridge list shows `rate(15 minutes)` rules (four
  enabled, one disabled); which one targets the monitor is not yet read.
* The figure "1,407" may be a VirusTotal count, not Twilio's. Andrew recalls one script attributing 1,407
  calls to one source, believed to be the Mini App, which is the VT drain already fixed on 2026-10-08.
  **Twilio's own usage page for the same dates settles it; nothing in AWS can.**

**The diagnostic hung the first time, and it was a defect this file already recorded.** It counted API
log lines with `filter-log-events`, which scans every stream. `tools/diagnose_twilio_spend.sh` now uses
Logs Insights, with a per-day table and the monitor's actual schedule. **A lesson recorded in one file
is still not a lesson the next file learns, for the fourth time.**

### WAFR (AWS FTR) STATE: SEC DONE, REL ANSWERED, 4 PILLARS LEFT

`tools/wafr_evidence.sh` read the account. The findings that matter, none previously recorded:
* **Lambda account concurrency limit is 10** (unreserved 10), peak concurrency 10, **427 throttles in 7
  days.** Reserved concurrency cannot even be set until it is raised. Quota code `L-B99A9384` is from
  memory and UNVERIFIED; read it before requesting.
* **11,227 errors against 70,202 invocations (16%)**, not yet split by function.
* PITR off on 19 of 57 tables, deletion protection off on 50, no AWS Backup plan, no budgets.
* 8 of 62 log groups have no retention, no X-Ray, no DLQs, one published version and no aliases on the
  main function, API Gateway has no access logging because no CloudWatch role is set.
* GuardDuty none, regional WAF none, one AWS Config recorder.
Answers for REL 1 to 13 are in `wafr_answers_reliability_2026-10-11.md`. **Next: PERF, COST, SUS.**

### BUILT 2026-10-11, ALL ON `claude/tender-cerf-ds0u0d`

* **MCP proxy discovery screening** (`mcp_proxy/discovery.py`): `initialize`, `tools/list`, `prompts/list`
  and `resources/list` were forwarded untouched, so MCP-2026-008 and 015 could not be seen. Flag-only,
  fail-open; public `cacheScope` alone is not a finding. Verdicts carry the matching taxonomy entries
  and mitigations from a generated snapshot (`mcp_proxy/taxonomy.py`, pinned to the JSON by test).
* **`GET /v1/mcp-taxonomy`**, live, `"count": 9`. Table `relayshield_mcp_taxonomy`, loaded by
  `tools/load_mcp_taxonomy.py`.
* **Opt-in proxy telemetry**, off by default. `counts` and `indicators` levels; indicators need an API
  key, send only public hostnames and a hash, and land as `unreviewed` candidates, **never in the IOC
  corpus**: an open endpoint's indicator is a claim, not a finding. Table
  `relayshield_mcp_proxy_telemetry` (not yet created), `tools/mcp_proxy_telemetry_report.py`.
* **Privacy policy section 12** (Contact is now 13), retention figures pinned to the ingest TTLs by test.
  **The proxy also sends each upstream server's domain to screening, which the first draft denied; the
  test now reads `neighbor.py` for it.** `deploy_privacy.yml` is dispatch-only until the live Worker has
  been diffed once.
* **Free tier no longer reaches `phone-reputation` or `sim-swap`**; per-key hourly cap is 50.
* Read-only tools: `diagnose_twilio_spend.sh`, `wafr_evidence.sh`, `lambda_errors_by_function.sh`,
  `protect_dynamodb_tables.sh` (dry run by default).

## 2026-10-11 (later): WHAT THE READS SHOWED, AND THE TWILIO PICTURE CHANGED AGAIN

* **The API path is cleared as the Twilio spender for 10-03 to 10-10.** Logs Insights counted ZERO
  `phone-reputation keyed` lines, zero `free-tier call` lines for either Twilio endpoint, and zero rate-limit
  hits. So neither the free-tier theory nor the keyed-abuse theory in PR #49 is supported by the logs.
* **The SIM swap monitor runs `rate(1 hour)`, not the `rate(4 hours)` its docstring states.** 215 runs in 7 days,
  and lookups per day rose 30, 31, 30, 41, 81, 90, 90 as enrolled users went from 1 to 3. **That is a structural
  cost, not abuse:** every enrolled number is one lookup per hour, so at the 7 numbers enrolled now it is about
  168 lookups a day. At the $0.014 per lookup quoted in PR #49 (UNVERIFIED against Twilio's price page) that is
  about $70 a month, against about $12 at 4 hours. Cadence is a product decision; nobody has recorded who set it.
* **Counts of "runs" include automatic retries.** A scheduled function that fails every run is invoked three
  times per tick. `relayshield-gas-monitor` (a 15-minute schedule) shows 2,021 invocations in 7 days, about three
  times its 672 ticks, and 2,021 errors: it has failed every time. Cause not yet read.
* **`relayshield-api` errors on 19.7% of invocations (9,171 of 46,551) with 411 throttles.** Cause not yet read.
  The account concurrency limit is 10 and adjustable, so throttling is real and customer-facing.
* **The Worker drift check cried wolf on a clean Worker.** `tools/recover_live_worker.sh` reported eight
  "live-only" names for `relayshield-privacy`. Every one was bundler output: the multipart wrapper of the API
  download, esbuild's `<stem>_default` export, a sourceMappingURL comment and `\u2190` / `\xA9` escapes. It now
  strips those, and a test against a clean and a hand-edited fixture shows it still flags real additions.
  **The live privacy page was BEHIND the repo, not ahead:** it lacked the free-email-check disclosure added on
  2026-10-06, so deploying it publishes that too.
* **The monitor's lookups alone cannot be 1,407.** Twilio Console > Monitor > Usage > Lookups for the same dates,
  split by product (line type versus SIM swap), is the only count for the Telegram `/sim` command and the WhatsApp
  lookup, neither of which logs one line per lookup.

## 2026-10-12: WHAT THE ERROR READS SHOWED. THE API HAD INIT OUTAGES, AND NOTHING ALARMED.

* **`relayshield-api`'s 9,171 errors are overwhelmingly INIT failures**, not request errors: 5,956
  `Runtime.UserCodeSyntaxError` and 3,667 `Runtime.ImportModuleError`, with the error-line count spiking on
  **2026-10-05 (17,607)** and **2026-10-11 (10,777)** against about 285 a day otherwise. 10-05 is the
  `relayshield_scamkit.py` syntax slip already recorded. **10-11 is a SECOND outage that was not noticed**: the
  hand-deploy at 01:12 UTC replaced a good package, and the import probe that guards CI never ran on it. The
  five CloudWatch alarms cover other functions and none covers the API, so a broken API raised nothing.
  `tools/diagnose_lambda_errors.sh` now prints which module was missing and the first and last time, per hour.
* **The ~285 a day baseline is `Badge score fetch failed ... ResourceNotFoundException` every five minutes**: a
  badge route reads a DynamoDB table that does not exist. Logged as ERROR, handled, not a Lambda error.
* **`relayshield-gas-monitor` has failed every run since at least 10-05 on a KMS permission, not a code bug**:
  `relayshield-gas-monitor-role` was never allowed to use the customer-managed key on `relayshield_users`. It is
  the same shape as the Stars and watchlist defects, a feature that could never run. `tools/grant_gas_monitor_kms.sh`
  reads the key from the table, simulates, and grants only what is missing, through DynamoDB only. **Its proof is
  the next scheduled run, not the simulation**, because the grant is conditioned on `kms:ViaService`.
* **The SIM swap monitor schedule is AWS state and now has a script**, `tools/set_sim_swap_monitor_schedule.sh`.
  Andrew confirmed hourly detection was never promised. **If it is run, record the date here**: the change lives
  in no file, which is exactly how an hourly rule replaced a documented four-hourly one without a trace.
* **A new Twilio clue, UNRESOLVED:** Andrew recalls the Mini App theory came from a Twilio count showing **one
  user with 1,407 calls in an hour**. No Lambda of ours can have made that: Telegram webhook 19 invocations and
  WhatsApp 22 in seven days, API Twilio paths zero. **If Twilio really shows that, the calls did not come from our
  code, and the Twilio credentials should be treated as exposed until shown otherwise.** No SID or token appears
  in any ref or in history. The check is Twilio Console, Monitor, Usage and the request logs, for the source of
  those calls; the response, if they are not ours, is to rotate the auth token in Twilio and in the secret
  `relayshield/twilio_auth_token`.


## 2026-10-12: SIM SWAP MONITOR SCHEDULE MOVED TO `rate(4 hours)`. CONFIRMED BY ANDREW'S OUTPUT.

`tools/set_sim_swap_monitor_schedule.sh --apply` ran on Andrew's Mac. The rule
`relayshield-sim-swap-monitor-schedule` read `rate(1 hour)` before and `rate(4 hours)` ENABLED after, and the
target is still `relayshield-sim-swap-monitor`. This change lives in AWS only and no commit carries it, which
is why it is written down here.

* **The rule's Description still says "Hourly SIM swap detection for all monitored numbers".** The script
  deliberately passes the old description back, so the text is now wrong. Harmless, but whoever reads the
  console will be misled; correct it next time the rule is touched.
* **Expected effect:** about 42 lookups a day at 7 enrolled numbers instead of about 168. UNMEASURED: confirm
  with Twilio's Lookups usage a few days from now, since the $0.014 per lookup figure is unverified.
* **The WAFR "moved to four-hourly" sentences and the SUS 3 tick are now true** and may stay in the Notes.
* Still not run: `tools/grant_gas_monitor_kms.sh`, `tools/create_cost_budget.sh`,
  `tools/diagnose_lambda_errors.sh relayshield-api`.

## 2026-10-12: SIM SWAP POLLING DECIDED AT EVERY 12 HOURS, AND THE REAL COST PER LOOKUP IS $0.058, NOT $0.014

**DECIDED by Andrew, 2026-10-12, on a cost-per-enrolled-number argument. APPLIED STATE IS NOT YET CONFIRMED:**
the dry run was read (rule `relayshield-sim-swap-monitor-schedule` at `rate(4 hours)`, ENABLED, target
`relayshield-sim-swap-monitor`), and the change is
`NEW='rate(12 hours)' AWS_PROFILE=relayshield sh tools/set_sim_swap_monitor_schedule.sh --apply`. **Whoever sees the
`after` table printing `rate(12 hours)` records the date here.** The schedule lives in AWS only, so no commit proves it.

**The numbers, read off Andrew's Twilio usage summary (October 1 to 12, 12:33 UTC) and not estimated:**

    SIM Swap Lookups        346    $17.30   = $0.05 each
    Line Type Intelligence  663    $5.30    = $0.008 each
    Number Format Lookups   664    $0.00    free
    Lookup total           1673    $22.60   (all lookups), month total $24.28
    September bill about $33.5, against about $2 to $2.70 a month from March to July

**THE EARLIER "$0.014 PER LOOKUP" WAS A GUESS AND WAS 4x TOO LOW.** Every monitor lookup asks for both
`sim_swap` and `line_type_intelligence`, so one lookup is about **$0.058**. The 2026-10-12 note above that says "about
42 lookups a day at 7 enrolled numbers" is also wrong: scan runs see 1 to 3 users (`sim_swap_monitoring` AND `active`),
not all 7 enrolled, and some enrolled numbers may be non-US (an errored SIM swap package is probably not billed;
346 billed against about 393 observed monitor lookups hints at it, UNVERIFIED).

**Cost per enrolled number per month, which is the number that matters:**

    hourly 720 lookups $42    every 4h 180 lookups $10.50    every 12h 60 lookups $3.50    every 24h 30 lookups $1.75

**WHY SEPTEMBER JUMPED.** Twilio approved SIM swap for the US on 2026-09-12, which lifted the 60606 self-gate, and the
monitor then polled hourly. About one enrolled number for 19 days comes to about $26 plus other lookups. Consistent
with the bill, INFERRED, not read from per-day data. All of October to date was billed at the hourly rate: the
four-hour change ran on 10-12 at about 01:24 UTC.

**WHY 12 HOURS LOSES NOTHING ON DETECTION.** The lookup returns `swapped_in_period`, "a swap in the last 24 hours" per
the code's own docstring (NOT checked against Twilio's docs). A swap stays visible for 24 hours, so a 12-hour poll
sees every swap and hourly polling only shortened the alert delay. Average delay is about 6 hours at 12h, about 2 at
4h. The alert dedup window is 23 hours, so nothing there needs to change.

**THE ECONOMICS THAT DECIDED IT.** CS Mobile is $10.99 a month and includes SIM swap. One enrolled subscriber costs
about $10.50 at four hours, which is nearly all of the revenue, and $3.50 (about 32%) at twelve.

### THE OPTION FOR FASTER ALERTS, UNBUILT. Sell it, do not give it away.

If faster alerts are wanted, make them a paid tier instead of lowering the global interval. Two shapes, cheapest first:

1. **Two EventBridge rules.** Keep the 12-hour rule as the default and add a second, `rate(4 hours)`, whose event
   payload carries a tier filter, with `scan_sim_swap_users()` honouring it (`subscription_tier` is already on the
   record). No new state. A user on the fast tier is scanned by both rules, so the filter must EXCLUDE the fast tier from
   the 12-hour rule or it is billed twice.
2. **One rule, per-user interval.** Run the rule at the fastest tier's rate and have `process_user` skip a user whose
   stored `last_checked` is newer than their tier's interval. Needs one extra DynamoDB write per user per run and a new
   attribute, and a skipped user must NOT count as a clean check.

**Price it from the table above:** a 4-hour tier costs about $10.50 per number a month in Twilio fees alone, so it
cannot be priced under about $15 a month for that number. An hourly tier is $42 and not a product at current prices.
**Do NOT build either until a customer asks for faster alerts or the paid tier exists.** The honest value of a SIM swap
alert is the response (lock the accounts), and 12 hours against 4 changes less than having it at all.

### OTHER LEVERS, NOT TAKEN

* **Unenrol Andrew's and test numbers.** Cheapest of all, and the diagnostic can list who is enrolled.
* **Drop `line_type_intelligence` from the monitor's lookup** saves about 14% but supplies the MCC/MNC that port-out
  detection compares, so it needs a code change and a test. Not done.
* **About 317 lookups a month are not the monitor** (663 line type against 346 SIM swap): phone-reputation, `/phone`.
  About $2.50, so not the problem. `tools/diagnose_twilio_spend.sh` splits them by code path.
* **`relayshield_sim_swap_monitor.py`'s docstring still says "every 4 hours"** in three places. The schedule is AWS
  state, so the docstring is not authoritative, which is exactly how an hourly rule replaced a documented four-hourly
  one unnoticed. Left alone this turn because editing the file redeploys a live function; fix it with the next change
  to that file.
* **WAFR wording updated conditionally.** `wafr_answers_perf_cost_sus_2026-10-12.md` now says "twelve-hourly". Those
  sentences are only true once the apply has run.

### CORRECTION TO THIS SESSION'S OWN STATEMENTS ABOUT BRANCHES

I said the three "still not run" tools were on `origin/main`. They are not: `grant_gas_monitor_kms.sh`,
`create_cost_budget.sh`, `set_sim_swap_monitor_schedule.sh` and the 2026-10-12 sections were on
`claude/tender-cerf-ds0u0d` only, and reached Andrew's clone through his unpushed local merge. That merge is exactly
what "push local main" delivers. The schedule script ran for him because his local `main` carried it; `origin/main`
did not.

## 2026-10-12: SIM SWAP SCHEDULE IS NOW `rate(12 hours)`, CONFIRMED. `main` PUSHED. THE API ERROR READ CAME BACK.

**Applied by Andrew on 2026-10-12, confirmed from the script's own `after` table:** rule
`relayshield-sim-swap-monitor-schedule` reads `rate(12 hours)`, ENABLED, target still `relayshield-sim-swap-monitor`.
The Description still says "Hourly SIM swap detection", which is wrong and harmless. The decision and the cost
reasoning are in the section above. **Measure it:** Twilio SIM Swap Lookups should fall to about 2 per enrolled billable
number per day from 10-13; if they do not, the rule is not what is driving them.

Local `main` was pushed at `c916768` (it carried the tender-cerf work, the WAFR PERF/COST/SUS answers and the three
tools), so `origin/main` now has `set_sim_swap_monitor_schedule.sh`, `grant_gas_monitor_kms.sh` and
`create_cost_budget.sh`.

**`tools/diagnose_lambda_errors.sh relayshield-api` (7 days), read:**

* **10-11 is the missing module `relayshield_openapi_spec`**, first failure 01:14:26 UTC and last 20:47:38 UTC, 3,667
  `Runtime.ImportModuleError`. The 01:12 UTC hand-deploy packaged `relayshield_api.py` without the file it imports.
  Nothing failed on 10-12, so a later deploy fixed it. **About 19.5 hours of the API failing to start, and no alarm.**
* **10-05 is the scamkit `Runtime.UserCodeSyntaxError` in `relayshield_api`**, 2,296, 13:02 to 20:23 UTC, already recorded.
* **The ~285 a day baseline is the badge route**, every five minutes, `relayshield_badge_cache` GetItem
  `ResourceNotFoundException`. **The table has never existed**, so the public badge has rendered "UNKNOWN" every time.
  `iam/snapshots/relayshield-breach-check-role-1sapnwdl.json` line 122 already names its ARN, so no grant is expected.
  `tools/setup_badge_cache.sh` (dry run by default, hash key `domain`, TTL on `ttl`) creates it. UNVERIFIED against real
  AWS: only a stubbed dry run was exercised.
* **UNEXPLAINED: 2,294 `AccessDeniedException` lines in the API's log group.** Not shown in the five recent lines, and
  the count sits suspiciously near the 2,296 syntax-error count, so it may be the same events. Unread; settle it before
  anyone calls the API's errors accounted for.
* Invocations per day on the API: 3,279 (10-05), 11,370 (10-06), then 4,450 to 7,799. 10-06 matches the VirusTotal loop.
* **Gas monitor KMS dry run read:** `relayshield_users` uses key `2ece080e-0cb0-499e-b2d1-6a496bbb4a1a`
  (the `relayshield-dynamodb-key`), `relayshield_gas_state` has no customer-managed key, and the role is `implicitDeny` on
  all four KMS actions. The proposed inline policy is the four actions on that one key, conditioned on
  `kms:ViaService = dynamodb.us-east-1.amazonaws.com`. **Not yet applied.**
* **Cost budget dry run read:** `relayshield-monthly-cost`, USD 50, alerts at 80% actual and 100% forecast to
  `relayshieldadmin@gmail.com`. **Not yet applied.** It does not see Twilio or VirusTotal.

## 2026-10-12: GAS MONITOR KMS GRANT APPLIED, COST BUDGET CREATED AT $50 AND ORDERED DOWN TO $10

**Applied by Andrew on 2026-10-12, confirmed from the scripts' own output:**
* **`tools/grant_gas_monitor_kms.sh --apply`** printed `attached.` for inline policy `GasMonitorKmsViaDynamoDB` on
  `relayshield-gas-monitor-role` (four KMS actions on key `2ece080e-0cb0-499e-b2d1-6a496bbb4a1a`, only `kms:ViaService =
  dynamodb.us-east-1.amazonaws.com`). **The simulation printed `implicitDeny` on all four AFTER the attach, as the script
  said it might, because the simulator cannot evaluate the `ViaService` condition.** That line is not the proof.
  **THE PROOF IS NOT YET IN:** the gas monitor's next 15-minute runs must stop logging `AccessDeniedException`
  (`sh tools/diagnose_lambda_errors.sh relayshield-gas-monitor`). Until that is read, this is "attached", not "fixed".
* **`tools/create_cost_budget.sh --apply`** created `relayshield-monthly-cost` at **USD 50** (alerts at 80% actual and
  100% forecast to `relayshieldadmin@gmail.com`). **Andrew's target is under USD 10 a month**, so the limit is to be lowered.
  The script used to say "already exists, leaving it alone", which made a second run a silent no-op; it now CHANGES an
  existing budget's limit with `update-budget` (alerts untouched), defaults to 10, and does nothing if it is already there.
  Exercised against a stub `aws` for all three paths (dry run, apply, already-at-target). **The new limit is NOT applied until
  Andrew runs it and the output reads USD 10.**
* **The $10 budget covers AWS charges only.** Twilio was $24.28 for October 1 to 12 alone and VirusTotal is a separate
  quota, and a budget alert tells Andrew AFTER the spend, it never stops it. Twilio's own usage trigger (Console, Monitor,
  Usage, Triggers) is the control for the biggest line and is Andrew's click.
* **`tools/setup_badge_cache.sh` dry run read:** table absent, role `relayshield-breach-check-role-1sapnwdl` `allowed` on
  GetItem and PutItem, so no grant is needed. **Not yet applied.**

## 2026-10-12 (later): LAMBDA CONCURRENCY QUOTA APPROVED; WEEKLY METRICS NOW SAYS WHETHER ITS "ALL-TIME" INDICATOR COUNT IS ALL-TIME

* **AWS approved the Lambda concurrency quota increase to 1,000** (Andrew, 2026-10-12; case 1791763915000769). The WAFR REL notes that waited on it may now be ticked, and reserved concurrency can finally be set (it could not be while the account limit was 10). Nothing was changed in AWS by this session. Record the date a reserved-concurrency setting is applied, since it lives in AWS only.
* **THE 255,580 FIGURE WAS READ AS A CUMULATIVE TOTAL AND IS NOT ONE.** The measured distinct-indicator count was **687,011 on 2026-10-08** (`tools/backfill_first_seen.py` scan of the sightings table, first-seen range 2026-06-21 to 2026-10-08), up from 661,609 on 2026-09-30. It grows by tens of thousands a week. What a report shows depends on two facts nobody could see from the repo: (a) whether the 2026-10-08 code was hand-deployed (the live function was stale then and `relayshield_weekly_metrics` has no CI deploy path), and (b) whether `tools/backfill_first_seen.py --apply` ever ran. **If it did not, `relayshield_intel_first_seen` holds only what the live monitor recorded since 2026-08-27, and a count of it is a plausible, partial number that looks like a total.** That is the most likely reading of 255,580 and it is UNVERIFIED: this session cannot read the email or AWS.
* **Built:** `_indicators_backfilled()` counts first-seen rows dated before `FIRST_SEEN_LIVE_SINCE` (2026-08-27), which only the backfill can have written. The email prints it under the cumulative figure, and prints a red `NOT ALL-TIME` row when it is zero. A zero is now the report saying the backfill never ran, instead of a clean-looking number.
* **Built:** "API keys by discovery surface". `relayshield_api_keys.source` already held the raw attribution key, and the report already counted keys per source, but as one ungrouped list with no weekly column and only for keys that had a signup. Keys are now grouped into discovery-surface groups (`SURFACE_GROUPS`), each with an all-time and a this-week column and its per-key detail, every group shown even at zero. `unmatched:` keys stay in their own red alarm.
* **Guard:** `test_weekly_metrics.py` fails if any key registered in `_SOURCE_BANNERS`, `_SOURCE_ALIASES`, `miniapp_routes.json` or the default `SOURCES` falls into the unclassified group, so a new surface cannot be added without being grouped. Proven by deleting a prefix. 50 tests. The grouping lives in the weekly-metrics file rather than being imported, because that Lambda is a single-file package with no deploy path that could package a second module.
* **NOT DEPLOYED.** Merging changes nothing in AWS. A hand deploy is required, and `sh tools/handler_drift.sh relayshield_weekly_metrics.py` is read first as always.

## 2026-10-13: THE MCP PROXY TELEMETRY TABLE IS LIVE. THIS FILE SAID "NOT YET CREATED" AND WAS STALE.

Measured on Andrew's Mac, not recalled:
* `relayshield_mcp_proxy_telemetry` **already existed** with TTL `ENABLED` on `ttl`
  (`tools/setup_mcp_proxy_telemetry_table.sh` found it and left it alone).
* `tools/grant_breach_cache_access.py --table relayshield_mcp_proxy_telemetry` reported
  `dynamodb:PutItem` and `dynamodb:UpdateItem` already **allowed** for
  `relayshield-breach-check-role-1sapnwdl`. Nothing to apply.
* An unsigned counts-only `POST /v1/telemetry/mcp-proxy` returned HTTP 200 with
  `{"ok": true, "data": {"recorded": true, "counts": 1, "indicators": 0}}`. That proves the
  gateway route, the deployed Lambda code and the table write on the path a real proxy uses.
  It left one test install row (`install_id` = `deadbeef` x4), TTL 180 days, so a report will
  show it as 1 install.
* The earlier line "`relayshield_mcp_proxy_telemetry` (not yet created)" is superseded. It was a
  lead, not a fact, and nobody recorded the creation: an AWS write made outside a session that
  can commit is invisible to every later session, the same shape as the Stars grant.

**INDICATOR TIER PROVEN 2026-10-14.** A keyed `mode: indicators` POST returned 200
`{"recorded": true, "counts": 0, "indicators": 1}`, so the `CAND#` write (`update_item` with a
set `ADD`) works under the granted `UpdateItem`. It left ONE TEST CANDIDATE: host
`probe-test.example.com`, payload hash 64 zeros, category `malicious_url`, `status: unreviewed`,
key `CAND#2eeba7d775165d837c9b8bf581aae269c3a084aa2c461ead7862d6d591f192f3`, TTL 365 days. **Any future promotion step must exclude it** (host
`probe-test.example.com`, or an all-zero hash); the API role cannot delete it. I predicted a 400
for that host and was wrong: the internal-suffix blocklist matches a trailing `.example` TLD, and
this host ends in `.com`.

**STILL TRUE: nothing promotes a candidate into the IOC corpus.** The only reader of `CAND#`
rows is `tools/mcp_proxy_telemetry_report.py`. Size and accuracy gains need a reviewed
promotion step that does not exist yet.

**Housekeeping found on the way:** Andrew's clone holds about 55 stashes, ~50 of them
"pre-merge untracked", because the standard merge block's stash line runs on every merge. The
stash line also swept up an uncommitted tracked edit to `mcp_proxy/proxy.py` (`git stash
--include-untracked` stashes tracked changes too, not just untracked files). Read it with
`git diff "stash@{0}^" "stash@{0}" -- mcp_proxy/proxy.py` before deciding anything.
