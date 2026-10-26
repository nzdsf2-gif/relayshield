# LOG_CURRENT: recent session records

<!-- NEW SESSION RECORDS ARE APPENDED HERE, NEVER TO CLAUDE.md. Newest last. The last
     'WHERE ... LEFT THINGS' section supersedes the ones above it. When this passes
     90,000 characters run: python3 tools/claude_memory.py --rotate --write -->

## WHERE 2026-10-17 (SECOND SESSION) LEFT THINGS. THE SHOPIFY APP IS SUBMITTED FOR REVIEW.

**2026-10-17, "RelayShield Order Screening", Partner dashboard App Store review page: Submitted, "We're assigning a
reviewer to your submission".** Review emails go to `relayshieldadmin@gmail.com`. The Submit button was greyed for ten days on
the two Embedded app checks and went live the same afternoon. This supersedes the "SHOPIFY ORDER SCREENING: THE EMBEDDED APP
CHECKS ARE STUCK" section of the 10-17 first-session record (that one lives on `claude/ecstatic-davinci-wh8xxr`).

### WHAT UNBLOCKED THE CHECKS, AND WHAT IS NOT PROVEN

* Andrew opened the app in a NEW Chrome profile with no extensions, reloaded it a few times and cancelled one order. About two
  hours later the Embedded app checks row was ticked. **The cause is not proven:** it could be the clean profile (Shopify staff
  advice, read only from forum snippets) or ordinary telemetry lag of up to two days. Nothing in our code changed between the
  stuck state and the pass. I told him the two-hour wait would probably flip it with no basis for saying so, and he caught it.
  **Do not repeat the claim that a clean profile fixes this; it is a hypothesis that happened to be followed by the result.**
* The console evidence, from the clean profile, before the check turned: `[RelayShield] App Bridge session token acquired`
  then `[RelayShield] session auth check: 200`. So App Bridge initialised and our backend saw the Bearer header. The code was
  right all along, which is why waiting and escalating, not rebuilding, was the correct response.
* **Do not post to the Shopify community forum.** Andrew's account was suspended on a first post and a repost was closed by a
  moderator. The support ticket was the channel used; no reply from a person is recorded.
* Chrome DevTools renamed the setting: it is **"Keep log on navigation"** (Console) and **"Keep log"** (Network), not "Preserve log".

### THE DRIFT READ WAS A FALSE ALARM, THE SAME ONE AS THE PRIVACY WORKER. THE SCRIPT STILL CRIES WOLF.

`sh tools/recover_live_worker.sh relayshield-order-screening shopify/worker.js` printed THEY DIFFER with 2 live-only identifiers
(`configurable`, `target`) and 47 live-only strings (`hmacSha256`, `handleCallback`, `buildTimelineNote` and so on). Every one is
esbuild's keep-names helper: wrangler bundles with `__name(fn, "fn")`, which writes each function name as a string, and the
helper definition carries those two identifiers. **Reproduced, not assumed:** `esbuild --bundle --format=esm --keep-names` on the
repo file, fed to the script's own comparison, gives exactly 2 and 47, and its opening lines match the live paste. Live was 26,076
bytes against 25,905 for that build, the gap being the multipart wrapper. So live equalled the repo copy, comments aside.
**The script does not filter `__name(...)` strings or those two identifiers yet.** Fix when convenient; it changes nothing about
the Shopify submission. A "THEY DIFFER" from it on any wrangler-deployed Worker should be tested this way before it is believed.

### WHAT WAS DEPLOYED, AND HOW TO REPEAT IT

* `relayshield-order-screening`, version `eab0bfb6-ec2e-42ad-9255-f3be5f6057f2`, from the merged branch (token exchange for
  managed installation). Tests first, on the merge: `node shopify/test_worker_session.mjs` (5 pass) and
  `python3 test_shopify_worker.py`, against stubs only.
* The KV namespace for the `RS_KV` binding is `d95c371db8754acd9e8e791e0a558915`, the only namespace titled `RS_KV`.
  `shopify/wrangler.toml` on main still holds the placeholder; the id goes into the LOCAL copy only, then
  `git checkout -- shopify/wrangler.toml`. `APP_URL` in that file is unused; the Worker reads only `RS_KV`, `SHOPIFY_API_KEY`,
  `SHOPIFY_API_SECRET`.
* **Deploy with `--keep-vars`.** A deploy replaces dashboard-set plain variables with the toml's; the flag keeps them.
* **`wrangler kv key list` reads a LOCAL copy by default and printed `[]` for a namespace with data.** Every `wrangler kv`
  read needs `--remote`. A read that is empty because it asked the wrong store looks exactly like a wrong id.
* Rollback if needed: `npx wrangler rollback` from `shopify/`.
* The local merge of `claude/ecstatic-davinci-wh8xxr` into Andrew's `main` was NOT pushed. Pushing `main` can trigger the Lambda
  deploy workflow, so it is a separate decision.

### THE FRESH-INSTALL TEST PASSED, WITH ONE HOLE

Dev store `relayshield-fresh-test`, installed after the deploy and opened once BEFORE any order. `shop:relayshield-fresh-test...`
appeared in KV (the token exchange stored a token), then order #1001 produced `screenings:relayshield-fresh-test...` (the webhook
was registered and the Worker screened it; verdict `unknown`, 15/100). Under managed installation `/auth` is never called, so
before the deploy a fresh install would have stored nothing; that was the reviewer-path risk and it is closed.

**Not proven: the tag and timeline-note write with an exchanged token.** `verdictActions('unknown')` returns no tags and no note,
so an `unknown` order never writes anything. The built-in fixture (`fixture-high-...@relayshield.net`) only fires on
`relayshield-test.myshopify.com`. The screening service graded `@testsafebrowsing.appspot.com`, `@mailinator.com` and
`@relayshield.net` all `unknown`, since the Worker sends only the buyer email and the shop URL. A reviewer's test orders will be
`unknown` too, so they cannot reach that path either. The write failing would be logged and swallowed, not break the app. To prove
it: allow the fresh store in the fixture, deploy, place a `fixture-high-` order, check the tag. **Do not deploy during review.**
The scopes were granted on the install screen ("View and edit store data: Orders").

### THE "DEPRECATED OFFLINE TOKEN" BANNER

Dev Dashboard Overview shows a red banner, "Deprecated offline token · Fix overdue · Last detected October 3, 2026". After the
fresh install it was unchanged and Installs read 2, so the new install is not being flagged. It is probably the old
`relayshield-test` token, installed under the legacy flow. The deployed code sends `expiring: "1"` and refreshes the token.
If a reviewer raises it, uninstall and reinstall the app on `relayshield-test`. Reinstalling may wipe that store's screenings
record, which holds the listing screenshots' data, so look first.

### WHERE THE SHOPIFY UI ACTUALLY IS. THIS COST THREE ROUNDS BECAUSE I GUESSED.

* Creating a dev store: Partner dashboard (`partners.shopify.com`), not the store Admin. Name, plan **Basic**, tick
  "Generate test data", leave "Test a feature preview" off.
* Installing an unpublished app: **Dev Dashboard** (`dev.shopify.com/dashboard`), the app's Overview, **Install app** top right.
  The store Admin's "Add apps" lists only published App Store apps. Seeing "Create app" means the wrong organisation or login,
  and creating one would mint a different Client ID. Never create a second app.
* I cannot reach any shopify.com page from the container, so I gave menu paths from memory twice and both were wrong. When a
  vendor UI is unreachable, ask for a screenshot of where he is before naming a button.

### THE SHOPIFY AI TOOLKIT HAS NO APP STORE REVIEW COMMAND IN THE VERSION INSTALLED

`claude plugin install shopify-ai-toolkit@claude-plugins-official` installed 2.1.2 (the plugin's manifest on GitHub says 2.2.0).
`/shopify-app-store-review` is unknown; the plugin shows 2 skills (the general `shopify-plugin:shopify` and a UCP shopping
skill), and those run shell commands. Its manifest says scripts send usage telemetry to shopify.dev unless
`OPT_OUT_INSTRUMENTATION=true`. The self-review was skipped; the submission page calls it optional and its row was already ticked.
Plugin skills are namespaced `plugin:skill`, not bare. A local Claude Code session started with **auto mode on** and offered to scan
shell history; both were declined.

### TWO THINGS TO FIX ABOUT OUR OWN SETUP

* **`/Users/andrewgibbs/dev/relayshield/CLAUDE.md` is over Claude Code's 150k-char limit (793k chars)**, so a local session on his
  Mac probably reads only a fraction of this file, including the rules written for him. This file needs splitting or trimming.
* `claude-plugins-official` is the same directory FD-12 (our own plugin) is waiting on; Shopify's toolkit is listed there.

### TODOS FOR THE NEXT SESSION, IN ORDER

1. **Read any Shopify review email, word for word, and answer fast.** No deploys to the Worker until a decision. Leave both dev
   stores and the app installed.
2. After the decision: prove the tag and note write (fixture for the fresh store), and decide the banner (reinstall the old store).
3. Fix `tools/recover_live_worker.sh` to ignore keep-names strings and the two helper identifiers, with a test.
4. Split or trim `CLAUDE.md`.
5. Push `main` and merge this branch (CLAUDE.md conflicts keep both sides). Unmerged: the x401 pack and grant tool, the Shopify
   Worker change is already deployed.
6. Carried from the 10-17 first session, unchanged: x401 `VERIFIER_NONCE_TABLE`, the Proof form and Muse summary, the whole
   2026-10-12 WAFR/FTR list, root key deletion (due from 2026-10-16), the first real MCP candidate `--approve`, CS Mobile v1.7.0
   behind a missing JDK, `tools/backfill_first_seen.py --apply`.

## WHERE 2026-10-18 LEFT THINGS. THE DRIFT CHECK NO LONGER CRIES WOLF, AND CLAUDE.md IS SPLIT SO IT CAN BE READ.

**Both cleanups owed from 2026-10-17 are done. Branch `claude/bold-goldberg-9m0c9b`, pushed, NOT merged.**

### `tools/recover_live_worker.sh` (commit `2cb3138`)

* **The 10-17 note blamed esbuild's `--keep-names` helper alone. That was half the cause.** Reproduced with
  esbuild 0.25.0 on `shopify/worker.js`: 2 identifiers and 50 strings (the 10-17 paste said 47; the gap is
  unexplained and is probably the esbuild version wrangler bundles with). After stripping `__name(...)` only,
  7 strings were still reported, and bundling EVERY Worker in the repo showed why: the string extractor was
  a regex with the 4-character minimum inside the pattern, so one short string such as `"raw"` put every later
  quote on the line out of step, differently in the two files. It also read apostrophes in comments and
  regex literals as strings, compared strings as written instead of as values (esbuild re-quotes and writes
  non-ASCII as `\uXXXX`), and did not know esbuild folds `"a " + "b"` into one literal.
* **Fix:** a balanced-paren scan cuts only the trailing name string of each `__name(...)` call; a small lexer
  replaces the regex; JS escapes are decoded on both sides; only strings joined by `+` are folded. 18 tests
  in `test_recover_live_worker.py`, each guard proven by reintroducing its defect (three survivors were found
  and tightened: comment-skipping, division-versus-regex and unicode-in-identifiers).
* **Measured:** 18 of 19 Workers now compare clean against their own esbuild bundle, and a planted
  exfiltration function in a real Worker is still reported (5 identifiers, 2 strings).
  `cloudflare_worker_blog.js` is the exception and it is not drift: the bundle inlines `blog_posts.js` and two
  image modules, and the script compares one file. Documented in the script header. `cloudflare_worker_checkemail.js`
  only bundles with `--external:cloudflare:email`.
* **UNVERIFIED, and the cheapest next check:** this was proven against esbuild 0.25.0 output, not against
  what the Workers API actually returns for a Worker wrangler deployed. When Andrew next runs
  `sh tools/recover_live_worker.sh relayshield-order-screening shopify/worker.js` the expected last line is
  `NOTHING IS DEPLOYED THAT THE REPO DOES NOT HAVE`. Anything else, send the list.

### CLAUDE.md split (this commit)

* 802,620 characters in 212 sections became: `CLAUDE.md` 87,349 (27 standing-rule sections moved verbatim, plus
  the new organising section), `docs/claude_memory/LOG_CURRENT.md` (recent records, 10 sections), nine
  `archive_NN.md` volumes, and a generated `INDEX.md`. **The split is lossless**: all 212 section bodies
  reassemble byte-identically to the old file (checked, not assumed).
* `tools/claude_memory.py --check | --index | --rotate` and `test_claude_md_size.py` (19 tests, 8 guards proven
  by mutation) hold the caps: CLAUDE.md 120,000, LOG_CURRENT.md 90,000. A session that appends its record to
  CLAUDE.md instead of the log now fails the test.
* **150,000 is Andrew's figure and is not verified against Claude Code's documentation.** If his client still
  warns about the size of CLAUDE.md, the next step is replacing the longest standing-rule sections
  (`COMMANDS HANDED TO ANDREW` 17.8k, `THREE INSTRUCTIONS` 9.7k) with digests. Deliberately NOT done now: it
  rewrites rules rather than moving them.
* **The old record says "this file" in many places** (WHERE THE CURRENT WORK LIST LIVES, the merge-block rule A).
  The organising section says to read it as `LOG_CURRENT.md`. `grep` the INDEX for any section a code comment
  names; most of the lessons now live in the archive.
* Stale `.pyc` lied again during the mutation proofs (a same-size edit restored within a second). The trap is
  already recorded on 2026-10-06. `rm -rf __pycache__ tools/__pycache__` between proof steps.

### Facts checked against `origin/main` this session (7795b96)

The x401 announcement pack, `tools/grant_verifier_table_access.py` and the Shopify Worker change ARE on
`origin/main`. The 10-17 item "merge and push the branch's unmerged pieces" is closed. Still open from 10-17,
unchanged: the Shopify review email, the tag-and-note write proof, the "deprecated offline token" banner,
x401 `VERIFIER_NONCE_TABLE`, the Proof form and the Muse summary.

## WHERE 2026-10-18 (SECOND SESSION) LEFT THINGS. THE FTR IS READY FOR ANDREW'S CONSOLE STEPS; THREE CORRECTIONS FROM HIM.

**Andrew merged the split cleanly (fast-forward, `OK` on the size check, 18 tests).** Branch
`claude/bold-goldberg-9m0c9b`, new commits unmerged.

### Corrections from Andrew, recorded as he gave them (not independently verified)

* **TWILIO IS SETTLED. The "1,407 calls in an hour" thread above is closed, and the 10-12 advice to rotate the auth token
  is withdrawn.** He says a recent session traced the spend to the SIM swap check frequency, and the cadence went from
  hourly to once every 12 hours (the schedule rule reads `rate(12 hours)`, confirmed in the 10-12 record). My 10-18
  summary listed Twilio as open because I read the stale 10-12 text, which is the "a doc recording an open item is a
  lead, not a fact" rule in the direction it is least expected.
* **Shopify: nothing to do.** The app is submitted and waiting on the App Store. The tag-and-note proof and the banner
  both depend on the response, so they stay parked.
* **AWS FTR: "finish now".**

### What was built for the FTR (commit follows this entry)

* `assets/marketplace/consumption_security_architecture.{html,png}`: the architecture diagram for
  `prod-kkvurtspreofy`, named by its listing name so no internal bundle name appears in an upload. Every box is read
  from code (`relayshield_bundle_fulfillment.py`, the metering calls in `relayshield_api.py` and
  `relayshield_agentic_api.py`, `hf-space-mcp-server/app.py`). It shows the Hugging Face MCP endpoint, Cloudflare and the
  data providers as OUTSIDE AWS. **Omitted deliberately: SNS** (the fulfillment module says events do not arrive until
  the subscription exists with this product's real topic ARN, and nothing records that), per-function IAM roles, key
  types, log redaction, vendor names, account number, counts.
* **A real defect found and fixed on the way:** the Bundle B architecture description and diagram footer claimed
  "every Lambda runs under its own least-privilege IAM role", "AWS-managed keys" and "identifiers hashed before they are
  written". All three are untrue (dozens of Lambdas share one role, two customer-managed KMS keys exist, some handlers log
  values readably). Nothing had been submitted with them, because the Bundle B form was one radio button. Corrected in
  `bundle_b_architecture_details_2026-09-20.md` and the Bundle B diagram was re-rendered. No other customer-facing
  surface carries the claim (grepped).
* `ftr_finish_2026-10-18.md`: the ordered finish list, the nine Notes that went stale (concurrency 10 to 1,000, the
  October init outages, the twelve-hour cadence), a Dave Shapiro email draft, and what Andrew sends back.

### Needed from Andrew, in this order

1. The four read-only AWS outputs (account concurrency, budget limit, SIM swap schedule, SNS subscriptions on
   `bundle-fulfillment`). Every Note that cites a number waits on them.
2. The pillar and number of the one unanswered WAFR question. All 57 have drafted answers, so which one is open cannot be
   told from the repository. The OPS and SEC answers were given in chat and not saved.
3. What THIS product's Architecture details tab in the Marketplace Management Portal currently says. For Bundle B the
   honest answer was "None of the above" (not considered deployed on AWS) because endpoints depend on third-party data
   providers. If the FTR needs an AWS-hosted product, that is the one thing that could stop validation. Read it, do not
   change it in the same sitting.
4. Any FTR checklist item he cannot answer. The FTR Guide is egress-blocked from the container and has never been read.

**Unchanged and still open:** the root access key (ends `N2XZ`) deletion, due on or after 2026-10-16; API alarm; badge
table; x401 `VERIFIER_NONCE_TABLE`, Proof form and Muse summary; CS Mobile v1.7.0 behind a missing JDK.

## 2026-10-19: THE WEEKLY REPORT'S "ALL-TIME" INDICATOR COUNT WAS A MONITOR-ONLY LOG. IT NOW MEASURES THE CORPUS. AZURE: LET IT EXPIRE, WITH CHECKS.

**Weekly metrics. Read from Andrew's own inbox (Gmail connector), not recalled.** The 2026-10-19 email
printed `Unique indicators (all-time, distinct) | 256,779`, and the 2026-10-12 email `255,580`. Two facts
follow from that and neither was in the repo:

* **The live Lambda is still the 2026-09-28 build.** Its label is `all-time, distinct`; the repo's label has
  said `cumulative, all-time` since 2026-10-11 and has carried the new-this-week, backfilled and red
  `NOT ALL-TIME` rows since 2026-10-12. None of those rows is in the live email. So none of the
  2026-10-06 / 08 / 11 / 12 changes to `relayshield_weekly_metrics.py` has reached AWS (it is in neither
  `deploy_lambdas.yml` nor `lambda_drift_check.yml`; a hand `update-function-code` is the only route).
* **The figure was never going to be cumulative, even after `backfill_first_seen.py --apply`.** Only
  `relayshield_intel_monitor._record_first_seen` writes `relayshield_intel_first_seen`.
  `relayshield_intel_feed._write_ioc`, which writes the public-feed sightings that are most new indicators,
  never does. Evidence: +1,199 in a week against a corpus that grows by tens of thousands a week
  (687,011 distinct on 2026-10-08, 661,609 on 09-30). A backfill fixes the past and nothing after it.
  This corrects the 2026-10-08 entry's "a small figure means the table was under-seeded": true, and
  incomplete, because the table is structurally monitor-only.

**Built (`relayshield_weekly_metrics.py`, 67 tests pass, `test_weekly_metrics.py`):**
`_measure_corpus` scans `relayshield_intel_iocs` in 8 parallel segments and collapses to distinct
indicators, same definition as `tools/ti_demo_metrics.py --distinct` (email, phone, `_control` excluded). The
email now leads with `Distinct indicators in corpus (cumulative)`, one week ago, net change, and the split
between RelayShield-channel collection and public feeds (MEASUREMENT DOCTRINE: the split is what is
defensible). The old row is relabelled `Telegram-monitor first-seen log (cumulative since 2026-08-27, never
expires)` and keeps its own red warning. **It runs LAST in the metrics dict and inside the Lambda's remaining
time. If it cannot finish it prints `NOT MEASURED` with the reason and the manual command; it never prints a
partial count and never falls back to the first-seen figure.** Each of three reintroduced defects (no dedup,
failed segment ignored, a segment skipped) was caught by tests.

**Retention caveat, printed in the email itself:** sightings expire (feeds 365 days, Telegram 90), so this
counts indicators still inside retention and can fall. It is the same population `--distinct` measures. A true
forever-count needs the feed writers to record first-seen too: PutItem on `relayshield_intel_first_seen` for
the feed Lambda's role (an IAM change on a full shared role, so a customer-managed policy) plus a conditional
write per new indicator. NOT built, because it touches ingestion; it is the correct long-term fix.

**NOT DEPLOYED, and UNVERIFIED whether the Lambda can afford it.** The scan loop is ~4.8 us/row in a sandbox
benchmark (~45s of compute for 9.5M rows at full CPU). Not measurable from here: botocore's response parsing,
and the Lambda's memory and timeout, which decide how much CPU it gets. The function's configuration has to be
READ first. If it cannot finish, the first email says `NOT MEASURED: time budget exhausted` and nothing breaks.

**Azure.** Andrew's portal screenshot: signed in as the work account `andrew@relayshieldad...` in
DEFAULT DIRECTORY, showing "Don't have a subscription?". That reproduces the archive_01 note (no subscription
visible to this identity) and does not contradict the expiry notice: "Azure subscription 1" belongs to the
`relayshieldadmin@gmail.com` login. Nothing in production depends on Azure (no workflow, Lambda or deploy path
calls it); the only Azure resource was the throwaway Sentinel QA workspace, whose teardown MS-1b already
called for. Recommendation given: let it expire. Open checks handed to Andrew: which resource groups exist,
Entra app registrations and the Tenant ID (the tenant, the Power Platform connector and the Partner Center
account sit outside the subscription), and the `sentinel_qa` API key still to revoke. **Not yet confirmed
by anyone: that the tenant survives the subscription's deletion.**

**2026-10-19, same day, two corrections against my own work.**
* **`ti_demo_metrics.py --distinct` was the wrong command to hand over.** It holds every sighting row in one
  list (`_scan_live`), so a ~9.5M-row table needs several GB. On Andrew's Mac it printed its "FULL SCAN"
  warning and returned to the prompt with no result. I recommended it without reading its memory profile.
  Replaced by `tools/corpus_distinct.py`: one 8-byte hash per indicator (~60 MB), a heartbeat every 10 seconds,
  an account guard, and it runs the SAME `_measure_corpus` the Lambda runs, so its timing is the evidence for
  whether the Lambda can do this. (The backfill's dry run, `backfill_first_seen.py` without `--apply`, is the
  other tool that produced 687,011 on 2026-10-08, but it is the same file that writes with `--apply`.)
* **The live `relayshield-weekly-metrics` is Timeout 120 s, Memory 256 MB** (read by Andrew, last modified
  2026-09-28). At that size the in-Lambda scan cannot run: the guard needs 45 s plus a 60 s reserve and the
  report's existing scans already use most of 120 s, so the email would print `NOT MEASURED`. 256 MB is also
  ~0.14 vCPU, and the scan is CPU-bound on response parsing. Do not deploy it onto that config and expect a
  number. Drift read the same day: live is byte-identical to commit `a56ee4ad` (stale, nothing to recover).
* **THIRD CORRECTION, SAME DAY: `tools/corpus_distinct.py` failed on its first real run** with
  `'str' object has no attribute 'get'` on all 8 segments, after 1.7 s. Cause: `_measure_corpus` parses
  low-level `{"S": "..."}` items, but both the tool and the Lambda path passed `dynamodb.meta.client`, the
  RESOURCE's client, which has the type conversion wired in and returns plain Python values. Proven with real
  boto3 1.43 and `botocore.stub.Stubber` (`resource.meta.client` -> `{'ioc_value': 'a.example'}`;
  `boto3.client('dynamodb')` -> `{'ioc_value': {'S': 'a.example'}}`). **Why 67 green tests did not catch it:
  the fake client returned the shape my code wanted, so it tested my assumption against itself.** Fixed:
  `_lowlevel_client()` returns a plain `boto3.client("dynamodb")`, the tool builds its own, and a client that
  returns deserialised items now fails with "pass boto3.client('dynamodb'), not resource.meta.client".
  Verified this time by running the REAL module against real boto3 with Stubber's response validation (a
  throwaway venv in the scratchpad, not part of the repo suite: the repo's tests stub boto3 out). **Lesson:
  when code parses another library's wire format, the test needs that library's real output, not a hand-built
  stand-in.** It was still not run against real DynamoDB; the next run on Andrew's Mac is that test.

**MEASURED 2026-10-19/20 on Andrew's Mac, `tools/corpus_distinct.py` (real DynamoDB, first working run):**
**723,810 distinct indicators** (697,502 a week earlier, **+26,308**), of which **15,765 collected by RelayShield
channels** and 708,045 ingested from public feeds. 9,538,567 sightings scanned in **284.2 s** (~33.6K rows/s,
CPU-bound on response parsing). It reconciles with the 2026-10-08 measurement (687,011) at ~+26K/week. Andrew's
reaction, verbatim in substance: this is the row he wants in the weekly report. That figure is the evidence for
the Lambda sizing: a Mac core did it in under five minutes, so `relayshield-weekly-metrics` (Timeout 120 s,
Memory 256 MB, last modified 2026-09-28) needs Timeout 900 s and Memory 1769 MB (one full vCPU) before the
in-Lambda scan can finish. Rollback is those two values back to 120/256 and the 2026-09-28 file (`a56ee4ad`).

## 2026-10-20: THE FEED NOW NOTES FIRST-SEEN (OFF BY DEFAULT); THE BACKFILL WAS A TWO-HOUR SILENCE; AZURE IS EMPTY.

**Deployed by Andrew's own paste (read, not assumed):** `relayshield-weekly-metrics` is now **Timeout 900 s,
Memory 1769 MB**, code modified 2026-10-20T00:24:53Z, 24,481 bytes. The corpus row has NOT yet been seen in an
email: Andrew still has to invoke it, and the first email's `Measured from N sightings in Ns` line is the
real in-Lambda timing.

**Azure, settled by Andrew's screenshots 2026-10-20.** Subscription `c2a7909e-923e-4282-b883-90886c36a6f7`
("Azure subscription 1"): Status **Disabled**, "Your free credit has expired", current cost 0.00, Owner is the
`relayshieldadmin@gmail.com` login, **no resource groups, no resources**. Entra tenant `Default Directory`,
**Tenant ID `4abf9bc4-9257-4c71-8b6b-a8afc934b4a5`**, primary domain `relayshieldadmingmail.onmicrosoft.com`,
Entra ID Free, **2 users, 0 groups, 0 applications, 0 devices**. So nothing was lost to the subscription
expiring, and there is no Entra application registration for MS-3 to depend on (it must be created fresh if
Security Store is ever pursued). Not confirmed by anyone: that the tenant survives the subscription's deletion
(it has users and no subscription dependency, so it should). Still open: revoke the `sentinel_qa` API key.

**Feed first-seen (Andrew approved: "I'm ok to make the Lambda record first-seen too").**
`relayshield_intel_feed.py` now NOTES each ingested indicator in memory (`_write_ioc`, `_batch_write_iocs`,
after a clean flush only) and runs ONE parallel conditional-put flush (`_flush_first_seen`, 16 workers) just
before the Telegram summary, inside the Lambda's remaining time minus 90 s. Fail-open; an AccessDenied stops the
flush after one warning and names the grant. **OFF BY DEFAULT: it only records when `FIRST_SEEN_FEED_ENABLED=1`.**
Reason, and it is the whole point of the flag: the writes are conditional and first writer wins, so a feed
that records an old indicator BEFORE `tools/backfill_first_seen.py --apply` has run stamps it with today's date
permanently and the backfill can never correct it. Turn it on only after the backfill finished. Verified against
real boto3 with Stubber (the resource client takes plain Python values; a real conditional failure counts as
known; a real AccessDeniedException is recognised). 18 tests in `test_intel_feed_first_seen.py`, each of three
reintroduced defects caught.
* **Why a flush and not a write per indicator:** several sources already call `_write_ioc` once per row inside a
  900 s budget (see the AbuseIPDB comment), so a second round trip per call would have doubled their cost.
* **Which role the feed runs under is NOT established.** `relayshield-intel-feed` is absent from the shared
  role's `functions_using_this_role`, so it probably has its own role and needs `dynamodb:PutItem` on
  `relayshield_intel_first_seen`. Read it with `iam simulate-principal-policy` before enabling.
* **Not covered:** `relayshield_intel_kev.py` and `relayshield_intel_substack.py` also write sightings and do not
  record first-seen. Both are low volume and run on the shared role, which already has PutItem on the table.

**`tools/backfill_first_seen.py` fixed.** Its `--apply` wrote ~470,000 rows ONE AT A TIME with no output, about two
hours of silence from a laptop, and was apparently never run to completion (the live table held ~257K rows against
~724K distinct). Now 32 parallel conditional writers with a heartbeat, and it refuses to run against account
`620534471984` (it had no account guard and it WRITES). 7 tests in `test_backfill_first_seen.py`. The scan phase
is unchanged (sequential, resource layer, several minutes).

**Sequence, enforced where it can be:** (1) invoke the weekly report and read the email, (2) run the backfill with
`--apply`, (3) read the feed role's PutItem decision and grant if denied, (4) push `main` (CI deploys the feed
with the flag off, so the deploy is inert), (5) set `FIRST_SEEN_FEED_ENABLED=1` through `lambda_env_set.yml`,
(6) then relabel the weekly report's first-seen row, which stops being "Telegram-monitor" only at that point.

**2026-10-20 (later): FIRST REAL WEEKLY EMAIL WITH THE CORPUS ROW, AND WHAT IT SHOWED.** Andrew's screenshot of the
9:01 PM report: `Distinct indicators in corpus (cumulative) 723,787`, one week ago 697,479, **net +26,308**,
15,742 collected by RelayShield channels, 708,045 from public feeds, **measured from 9,538,540 sightings in
494.1 s inside the Lambda** (Timeout 900, Memory 1769). The corpus row works.
* **He still said "the unique indicators is still incremental".** The row he was reading was almost certainly the
  first-seen log beneath it (257,696, +1,399 this week, 194,987 seeded), which was labelled "(cumulative since
  2026-08-27, never expires)" and so looked like a competing total. It is 36% of the corpus. **Demoted:** it is now
  a muted diagnostic, "First-seen log (diagnostic, not the total above)", showing its size as a percentage of the
  measured corpus, and its note says it is still being seeded. A test makes exactly ONE row in the section call itself
  cumulative, proven by relabelling the log row. Needs a hand redeploy of the weekly Lambda (same zip block).
* **194,987 pre-2026-08-27 rows already existed in the first-seen table**, i.e. an earlier `backfill_first_seen.py
  --apply` had been started and stopped partway (consistent with it being a two-hour serial silence). The new
  backfill skips those and writes the rest.
* **GROWTH WARNING, so it is not rediscovered as a failure.** The sightings table grows ~430K rows a week (9,108,658
  to 9,537,878 between 10-12 and 10-19) and will keep growing until retention (feeds 365 days) starts expiring
  rows, around June 2027. The in-Lambda scan time scales with rows: 494 s now, and the guard's budget is roughly
  Timeout minus the other metrics minus 60 s reserve, so it will hit `NOT MEASURED: time budget exhausted` in
  roughly 10 to 12 weeks (around the new year). That degrades gracefully, it does not break the email. **The
  durable fix is the first-seen log itself:** once the backfill has completed and the feed recorder is on, its
  row COUNT is a cheap, never-expiring, forever-cumulative figure, and the headline should switch to it.
* **The feed's role cannot write the table yet.** `relayshield-intel-feed` runs under
  `arn:aws:iam::239677749008:role/relayshield-intel-feed-role` and `simulate-principal-policy` returned
  `implicitDeny` for PutItem on `relayshield_intel_first_seen`. `tools/grant_feed_first_seen_write.py` reads the
  decision and, with `--apply`, adds ONE new inline policy `relayshield-first-seen-put` (PutItem on that table only),
  refusing if a policy of that name exists, if the role is the full shared role, or if the account is wrong.
  8 tests, and the real tool was run against real botocore clients under Stubber to validate every request.

## WHERE 2026-10-20 LEFT THINGS. THE INDICATOR REPORT IS DONE; THE FIRST-SEEN SEQUENCE IS HALF RUN; THE WAFR IS THE NEXT BIG THREAD. READ THIS FIRST.

**This section supersedes the earlier "WHERE ... LEFT THINGS" lists. Where a line carries an earlier item, it says so.**

### Where each thread stands, from Andrew's own pastes (read, not assumed)

* **Weekly metrics: DONE and deployed.** `relayshield-weekly-metrics` is Timeout 900 s, Memory 1769 MB. The 9:01 PM email on
  2026-10-19 showed `Distinct indicators in corpus (cumulative) 723,787`, one week ago 697,479, **+26,308**, in 494 s inside
  the Lambda. **Andrew: "The updated Weekly metrics report is exactly what I want to see updated every week."** Still to
  deploy: the 587ebf5 change that demotes the first-seen row to a muted diagnostic (he read it as the cumulative total).
* **First-seen backfill: RUN, NOT CONFIRMED COMPLETE.** `tools/backfill_first_seen.py --apply` scanned 9,538,515 sightings,
  **726,875 distinct**, first-seen range 2026-06-21 to 2026-10-19, then wrote at ~360 rows/s with 0 failures. The paste ended at
  466 s with 167,246 of 726,875 done (wrote 14,955, already present 152,291). **The early "already present" rate is explained,
  not a fault:** an earlier serial `--apply` had written the first ~195K rows in the same deterministic scan order. No final
  `wrote N, skipped M ... failure(s)` line was pasted. Re-running is safe (conditional writes), about 35 minutes.
* **Feed first-seen: BUILT, NOT DEPLOYED, FLAG OFF.** `relayshield_intel_feed.py` notes indicators in memory and flushes once,
  gated by `FIRST_SEEN_FEED_ENABLED=1`. **The feed role cannot write the table yet:** `tools/grant_feed_first_seen_write.py`
  printed `implicitDeny` for `relayshield-intel-feed-role` and the policy it would add; Andrew has NOT yet run it with `--apply`.
* **Azure: nothing to do.** Subscription Disabled, no resources, Entra tenant `4abf9bc4-9257-4c71-8b6b-a8afc934b4a5` with 0
  applications. Only the `sentinel_qa` API key revocation remains.
* **Branch state:** work is on `claude/tender-wozniak-b3zdhc` (pushed, 587ebf5 plus this entry). **Andrew's local `main` is ahead
  of `origin/main`; nothing is on `origin/main`, so no CI deploy has fired.** Pushing `main` deploys `relayshield-intel-feed`
  (flag off, so inert) and everything else on the branch that has a CI path.

### The WAFR, as Andrew gave it on 2026-10-20 (NOT independently verified, and the findings themselves are NOT in this repo)

**"The WAFR results were disappointing from Amazon, but it is probably worthwhile to stay the course and fix the issues
preventing our Agentic Attack Surface bundle from passing their audit as being market ready, despite already being a released
product."** DECISION: stay the course. I have not seen Amazon's response: there is no AWS result email in the connected
Gmail, and nothing in the repo records it. **So everything under WAFR below is provisional until Andrew pastes the actual
findings.** The product is `prod-kkvurtspreofy`, listed by Amazon as "RelayShield - Consumption Security API Bundles" (the old
Bundle D); the FTR solution is `soln-aicwx4eiyofnm`. Nothing a buyer or AWS reviewer reads says "Bundle D".

### TODOS FOR THE NEXT SESSION, IN ORDER

**A. Finish the first-seen sequence (each step needs the one before it; the order is what protects the data).**
1. **Paste the backfill's final line**, or re-run it: `AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/backfill_first_seen.py --apply`
   after the merge block. Done means `wrote N, skipped M already present, 0 failure(s)`. Then the weekly report's
   `First-seen log` row should read roughly 100% of the corpus.
2. **Grant the feed role**: `tools/grant_feed_first_seen_write.py --apply`. Proof is `allowed` on the re-simulation.
3. **Redeploy the weekly Lambda** (zip, `update-function-code`; config already 900 s / 1769 MB) so the demoted first-seen row ships.
4. **Push `main`**; CI deploys the feed with the flag off. Then set `FIRST_SEEN_FEED_ENABLED=1` through the Actions workflow
   "Set one Lambda env var" (function `relayshield-intel-feed`, key `FIRST_SEEN_FEED_ENABLED`, value `1`). **Never before 1 and
   2**: recording before the backfill stamps today's date on old indicators permanently.
5. **Read the feed's first Telegram summary** for the `First-seen: N new indicators, M already known` line.
6. **Once coverage is ~100%, switch the report headline to the first-seen row count** (cheap, never expires), and keep the
   corpus scan as a cross-check. **The scan has about 10 to 12 weeks of headroom** (494 s of a ~740 s budget, table growing
   ~430K rows a week), so do this before about the new year or the row starts printing `NOT MEASURED`.
7. **Put `relayshield_weekly_metrics.py` on a CI deploy path and in `lambda_drift_check.yml`.** It was stale in AWS for three weeks
   and nothing said so. This is also a WAFR OPS finding with evidence. The map entry must ship in a push that touches the `.py`.
8. **Fix `relayshield-signup-api` in the deploy-invoke policy**: `python3 tools/check_deploy_invoke_policy.py --write`, then
   `sh tools/apply_deploy_invoke_policy.sh`. `test_workflows_parse.py` fails on it today (pre-existing).
9. **Revoke the `sentinel_qa` API key.**

**B. WAFR / FTR: stay the course (the main thread).**
1. **Andrew pastes Amazon's response**: which items failed, whether highs block approval, what "market ready" means in their words,
   and any reviewer comments. Until then, do not re-answer anything.
2. **Work the known cause list from 2026-10-12, cheapest first** (the list above in "TODOS FOR THE NEXT SESSION" of that entry still
   stands; whether Amazon cited each is unknown): the API alarm and a guard so a hand-deploy cannot replace a package the import
   probe has not seen; the gas-monitor KMS grant (`tools/grant_gas_monitor_kms.sh`); the cost budget (`tools/create_cost_budget.sh`);
   the badge route's missing table; **reserved concurrency (the 1,000 quota was APPROVED 2026-10-12)**; **one IAM role per Lambda
   (`iam_role_split.md`; 41 functions share one role with 26 inline policies, the largest SEC finding)**; log retention on the 8
   groups with none; tag standardisation; Lambda versions and aliases for rollback; tests in CI; a load test and tracing; arm64.
3. **Check this product's Architecture details tab** in the Marketplace Management Portal. For Bundle B the honest answer was "None
   of the above" because endpoints depend on third-party providers; **if the FTR needs an AWS-hosted product that is the one
   thing that could stop validation.** Read it, do not change it in the same sitting.
4. **Re-verify every claim in the WAFR Notes and the listing against code.** On 2026-10-18 the Bundle B description claimed
   per-Lambda least-privilege roles, AWS-managed keys and hashed identifiers, all untrue; this repo has the habit of writing
   the aspiration. Nine Notes also went stale (concurrency, October outages, twelve-hour SIM cadence): `ftr_finish_2026-10-18.md`.
5. **Then**: re-tick and re-word the WAFR, Save milestone, PDF under 3 MB, request FTR validation again, email Dave Shapiro.
6. **Read the FTR Guide in Partner Central**: it has never been read (docs.aws.amazon.com is egress-blocked from the container).

**C. Carried, unchanged.** Root access key (ends `N2XZ`) deletion was due on or after 2026-10-16 and is now overdue if nothing broke;
x401 `VERIFIER_NONCE_TABLE`, Proof form and Muse summary; CS Mobile v1.7.0 build behind a missing JDK; read the Hudson Rock terms
before promoting the free check; first real MCP candidate `--approve`; Shopify is parked on the App Store response.

### Lessons from this session (the standing one is in CLAUDE.md)
* **Before committing, run `git branch --show-current`.** I committed the feed change while sitting on local `main` (left there
  after merging the branch in to read files), then pushed the stale feature branch and told Andrew it was pushed. The stop hook
  caught it. After a read-only merge into `main`, `git checkout` back before any commit.
* **Standing rule added to `CLAUDE.md`:** a test that builds the input it expects proves nothing; check parsing code against the
  library's real output (botocore `Stubber`). Three of today's defects were found that way and none by the fakes.

## 2026-10-20 (later): FIRST-SEEN STEPS A1 TO A3 DONE; THE FLAG IS STILL OFF. main ALREADY CARRIED THE CODE UNDER REBASED HASHES.

From Andrew's own pastes (read, not assumed):

* **A1 DONE.** `backfill_first_seen.py --apply` finished: `wrote 471322, skipped 255553 already present, 0 failure(s)`. Total 726,875 rows, scan range to 2026-10-19 21:50 UTC.
* **A2 DONE.** `grant_feed_first_seen_write.py --apply` added `relayshield-first-seen-put` to `relayshield-intel-feed-role`; re-simulation: `allowed`.
* **A3 DONE.** `relayshield-weekly-metrics` redeployed by zip from the working tree: LastModified 2026-10-20T23:26:31Z, 24,985 bytes, handler `relayshield_weekly_metrics.lambda_handler`, 900 s, 1769 MB. The file is byte-identical (blob 33d3b84) on `origin/main` and on `claude/tender-wozniak-b3zdhc`, so it carries the demoted first-seen row.
* **A4 HALF DONE.** `origin/main` already held the feed, weekly-metrics, backfill and grant-tool changes as commits 984d1c9 / 84061e2 (same content as 452437e / 587ebf5, different hashes, so a rebase-style landing). Andrew's push said `Everything up-to-date` and Deploy Lambdas was green. **`FIRST_SEEN_FEED_ENABLED` is NOT yet set.** That is the last step and nothing records first-seen from the feed until it is.
* **The merge that conflicted was not a real conflict.** Merging `claude/tender-wozniak-b3zdhc` into a `main` that already had the same changes under other hashes conflicted in `INDEX.md` and `LOG_CURRENT.md` only. Code files were identical. The branch's three doc files (CLAUDE.md, INDEX.md, LOG_CURRENT.md) were a strict superset of main's (no deletions), so they were applied onto main on `claude/exciting-bell-t98uu8` instead of resolving by hand.
* **Lesson.** Before handing a merge block, compare `git --no-pager diff --stat origin/main origin/<branch>` first. When main has already absorbed a branch under new hashes, the merge block is wrong and the move is to take the branch's doc files onto main.
* **Gap, small:** the backfill scan stopped at 2026-10-19 21:50 UTC. An indicator first seen after that and before the flag goes on will carry the date the feed first records it. At most a day or two off.

## 2026-10-20 (night): THE intel-monitor ALARM. THE CI IMPORT PROBE RAN A FULL TELEGRAM POLL. CAUSE OF THE ERRORS DATAPOINT NOT YET ESTABLISHED.

* **Alarm:** `relayshield-intel-monitor-errors`, OK to ALARM at 2026-10-20 23:41:56 UTC, datapoint 23:31.
* **What was found (Actions run 209 job log, and Andrew's CloudWatch read):** Andrew dispatched Deploy Changed Lambdas by hand at 23:27:57 (a dispatch deploys ALL 27 mapped functions). `relayshield-intel-monitor` was redeployed at 23:30:07. The import probe invoked it at 23:33:01 and it took until 23:35:04 (123 s; every other function ~2 s) because `relayshield_intel_monitor.lambda_handler` did not recognise `ci.import-probe`, unlike intel_feed and intel_kev, so it ran a full channel poll on the live Telethon session, holding the single-flight lock. The only ERROR line in 3 h was `@cti_vn` private/banned, caught per channel, which does not raise and does not count as a Lambda Errors datapoint.
* **Fixed:** the probe guard is now the first thing in `lambda_handler`, before the lock. `test_relayshield_intel_monitor_contract.py::ImportProbeGuard` checks it precedes `_acquire_lock()` and does no work; proven by changing the string and watching it fail. Deploys with the next push to main that touches the file.
* **NOT established:** which invocation produced the Errors datapoint at 23:31. The first read filtered on `ERROR/Traceback/Runtime/Task timed out` and showed no failing invocation. Next read: the `REPORT RequestId` lines (Status, Duration, Max Memory) for 23:25 to 23:45.
* **Side finding:** `@cti_vn` is private or the account is banned from it. It will log an ERROR every run until removed from `relayshield_intel_channels`.

## 2026-10-25: "DEPLOYED ON AWS: NO" ON `prod-szi2wdww3obry` IS THE 2026-09-20 CHOICE, NOT A WAFR SIDE EFFECT. READ FROM THE PORTAL, NOT RECALLED.

Andrew reported the listing "was deployed on AWS and something in our WAFR submission changed the status". **Not supported by any record.**
Read from his screenshots of the Management Portal (SaaS products, then the Public row):

* The product's **Architecture details** tab reads `AWS hosting pattern of your application: None of the above.` and the
  Assessment reads `Deployed on AWS: No, this product is not fully deployed on AWS. Contact us for details.` That is the answer
  chosen 2026-09-20 (`bundle_b_architecture_details_2026-09-20.md`), because the supply-chain endpoint depends on a paid third-party
  API and secret-scan on six public registries.
* **Portal SaaS products list:** three rows titled "Attack Surface & Supply Chain API". The **Public** one (last modified Sep 22) is the
  real listing `prod-szi2wdww3obry`. The two **Restricted** ones (Sep 23) are the withdrawn duplicates `prod-v5nr5gjtdnofi` and
  `prod-p3ei5nmgufnnq`. Never open or edit those two; the ids differ only by a random suffix.
* **Gmail (own inbox) has no AWS message** about a status change, the WAFR result or architecture details. The only recent AWS mail
  on this listing is the 2026-10-23 "AI Insights" notice.
* **Not established:** whether the field was ever Yes, and what a WAFR/FTR does to it. The buyer-side "Manage subscriptions" page
  is NOT where listings live; sellers use the Management Portal, SaaS products tab (the Server products tab is empty).
* **Do not select "The product runs entirely on AWS"** until AWS says outbound calls to public APIs are not "3rd party dependencies".
  Today it would be a public claim a reviewer can check, and it would be false.

**Next:** Andrew sends the Requests log tab (shows any change request against this product), and opens a Contact us case asking whether
the field was ever Yes and what restores it. Nothing is changed on the tab in the same sitting.

## 2026-10-25 (later): THE FTR IS BLOCKED BY TWO PREREQUISITES, NOT BY THE WAFR. READ FROM PARTNER CENTRAL SCREENSHOTS.

Partner Central, solution `soln-aicwx4eiyofnm`, Validation details: **FTR status Blocked; "Request validation" is greyed out.**
Prerequisites, in AWS's sequence: linked to exactly one Marketplace product **Complete**; no non-Marketplace products **Complete**;
software product **Complete**; **"AWS Marketplace product is deployed on AWS" INCOMPLETE** (banner: "FTR validation requires your product
to be hosted on AWS"); **"Partner Revenue Measurement (PRM) enabled" INCOMPLETE** (needs one of Resource Tagging, User Agent String or
Marketplace Metering; the dashboard takes up to 7 days to reflect it, so it is the long pole).

* **CORRECTION OF MY OWN EARLIER STATEMENT:** I told Andrew the console did not tie the FTR to "Deployed on AWS". It does. The repo had flagged
  this on 2026-10-18 (`ftr_finish_2026-10-18.md` section 6) and I under-weighted it.
* The linked product is `prod-kkvurtspreofy`; its Architecture details tab also reads "Deployed on AWS: No" (product last modified Aug 5).
  `prod-szi2wdww3obry` is NOT what the FTR judges. Neither product was changed by the WAFR.
* Well-Architected Tool workload "RelayShield API": 57/57 answered, **37 High, 15 Medium** (last updated 2026-10-18). That is the
  "disappointing" result. It is not what blocks the request; the two prerequisites do.
* **AWS rule, SECONDARY (search summary of the SaaS guidelines; docs.aws.amazon.com is unreachable from the container, WebFetch too):**
  "deployed on AWS" needs the application AND control planes entirely on AWS; third-party services that transmit, store or process
  application data must also run on AWS (CDN, DNS and corporate IdP exempt); agents/gateways may sit outside if they send data only to AWS.
* **Likely causes in `prod-kkvurtspreofy`, from code:** the declared MCP endpoint is the Hugging Face Space (`hf-space-mcp-server/app.py`,
  outside AWS, receives callers' keys and queried domains); `relayshield_agentic_api.py` calls `rdap.org`. NOT checked: the other Bundle D
  endpoints' outbound calls. The authoritative answer is the "Contact us for details" case on the tab's Assessment panel.
* **PRM:** metering already exists (`BatchMeterUsage`) but secondary sources say PRM metering covers AMI/ML, so Resource Tagging
  (`aws-apn-id`) is the safer route for SaaS. Needs the exact tag value from Partner Central; do not guess it.

## 2026-10-25 (build): AWS-HOSTED MCP ENDPOINT WRITTEN AND TESTED; NOT DEPLOYED, LISTING NOT CHANGED.

Why: the FTR prerequisite "product is deployed on AWS" fails for `prod-kkvurtspreofy` (AWS's own assistant read its hosting architecture as
Control Plane and Application Plane both `UNSPECIFIED`, i.e. the "None of the above" answer), and the listing's registered MCP endpoint is the
`-aws` Hugging Face Space. Repo evidence that only Bundle D registers that Space: Bundle A and B entity JSON are plain `SaaSUrlDeliveryOptionDetails`;
`hf-space-mcp-server/app.py` says the `-aws` Space is "registered as Bundle D's MCP endpoint". The TI product (`prod-kb3ftelx44wlk`) is not in the repo,
so it is unconfirmed. The Spaces are NOT retired.

* `relayshield_mcp_http.py`: the same 13 tools, MCP Streamable HTTP (POST JSON-RPC), stdlib only, Lambda handler. Same result shapes, AWS-mode scrub always on.
* `test_relayshield_mcp_http.py` (28 tests): runs every tool through BOTH `app.py` (gradio and requests stubbed, `AWS_MARKETPLACE_MODE=true`) and the
  new module against identical fake upstream answers, plus the JSON-RPC transport, plus the real `_http_request` against a real local HTTP server
  (200, 401, 500, timeout, refused). Proven by mutation: changed scope text, swapped severity order, a third-party import, a non-RelayShield host and a leaked
  signup link each fail it.
* `tools/create_mcp_http_lambda.sh`: dedicated logs-only role, function, `/mcp` on API `atq6wtkp6k` (ANY of POST/GET/OPTIONS), stage redeploy, proof over the
  execute-api host AND `https://api.relayshield.net/mcp`. UNVERIFIED against AWS (no credentials here); `sh -n` clean and the demo-key extraction checked.
* **Not done, in order:** (1) run the script; (2) map in `deploy_lambdas.yml`, `lambda_drift_check.yml`, `iam_github_deploy_invoke.json`; (3) a guarded
  listing change set moving the registered MCP endpoint (a change set REPLACES what it is given; the 2026-07-27 rate-card rollback is the precedent);
  (4) only then resubmit Architecture details as "runs entirely on AWS". Submitting it earlier would be a false public claim.
* **Known limits:** API Gateway REST cuts a response at 29 s while `check_agent_risk_summary` can chain three 15 s calls; `X-RS-Source` stays
  `hf-mcp-space` so usage still lands in the weekly report (both dispatchers match that exact string); `rdap.org` is still called by the backend and AWS may
  count it as a third-party dependency. NOT checked: the other Bundle D endpoints' outbound calls.
* **PRM:** AWS's assistant says User Agent String `APN_1.1/pc_46y72j0d99w7lyqkiqrakpc5k$`, management-plane calls only, one per resource per month. That
  guidance is written for products that call into customer accounts; ours does not. Ask what the prerequisite actually detects before adding it anywhere.

## 2026-10-25 (later): THE LIVE ENTITY READ; MOVING THE MCP ENDPOINT ALONE DOES NOT MAKE `prod-kkvurtspreofy` "ENTIRELY ON AWS".

Read from Actions run 40201513798 (`marketplace_read_product.yml`, entity `prod-kkvurtspreofy`, full), not recalled:
* Delivery option `do-f5mvr663dvomi` (version `version-baq5najnqgsam`): `Type: ApiRegistration`, `ApiType: MCP_SERVER`, ONE endpoint,
  `EndpointUrl` = the `-aws` Hugging Face Space, `AuthorizationTypes: [API_KEY]`. `HostingArchitecture.Platforms` = CONTROL_PLANE and
  APPLICATION_PLANE, both `Provider: UNSPECIFIED`, `EnvironmentOwner: UNSPECIFIED`; **`ArchitectureDiagramUrl: ""`** (no diagram on the listing).
  So the endpoint AND the architecture declaration are fields on the same delivery option.
* **The public LongDescription and Highlights still quote "5.0M+ IOCs, 3,750+ malware families, 85+ Telegram marketplaces"**, which MEASUREMENT
  DOCTRINE forbids. `tools/marketplace_add_dimension.py --with-copy` is the route; it is one change set per product at a time, so batch it.
* **Third-party calls reachable from the five endpoints on this product (traced by AST, not grepped):** `prompt-injection-breach` and
  `llm-credential-exposure` call nothing outside AWS. `mcp-registry-risk` calls RDAP (optional enrichment, best-effort). `tech-stack-cve` calls GitHub for a
  public-PoC signal (optional, returns None on failure). **`bulk-identity-risk` calls TWO live third-party APIs in `_domain_risk_fast` (a paid breach
  API for D1 and an infostealer API for D2) plus the breach API again in `_agent_risk`.** Both are the endpoint's data, and customer domains and emails go to them.
  The form's own text for "runs entirely on AWS" requires any 3rd party dependencies to run on AWS, so declaring it today would be a false public claim.
* The AWS-hosted MCP server exposes all 13 tools (parity with the Space), so it also fronts the HIBP/GitHub-backed tools of other bundles. The listing
  advertises only 5. Restricting the AWS listing's toolset to those 5 is a small follow-up.
* `assets/marketplace/consumption_security_architecture.{html,png}` now shows the MCP endpoint as API Gateway `/mcp` to Lambda, and no Hugging Face box.
  It still lists "third-party data providers" outside AWS, which is TRUE today. It must be re-rendered if the dependencies are removed.
* **Do not shut down the `-aws` Space:** existing subscribers' MCP clients are configured with its URL.

## 2026-10-25 (decision + build): ANDREW CHOSE TO DILUTE BUNDLE D ON THE AWS PATH ONLY. BUILT, TESTED, NOT DEPLOYED.

**Decision, in his words:** discovery is the bind ("buyers are not finding my licenses"), the FTR is "another potential discovery surface and a reason to message
Dave Shapiro" (it does NOT guarantee a sales resource), and Bundle D stays the FTR product because it is the most timely for AWS enterprise buyers. He accepted
that this makes the bundle sold through AWS differ from the one sold on the developers site and Stripe. I had recommended parking the FTR, then recommended tracing
the TI listing instead; both were overruled. Evidence from the 2026-10-20 weekly report, for the record: AWS Marketplace 0 active subscribers, $0 YTD; Bundle D
endpoints 0 Stripe-metered calls last week; x402 `bulk-identity-risk` 1 call ever. The TI listing's feed handlers (TAXII, MISP, actor, cve, trending) make NO outbound
calls (AST trace); only `/v1/intel/telegram` enriches via an IP-geolocation and a registration-age lookup. That route stays available if Bundle D proves too costly.

**What changed (AWS-licensed keys only, marker = `key_record["aws_customer_id"]`, set in BOTH dispatchers and never read from the request):**
* `bulk-identity-risk`: the domain score skips the external breach-history and external infostealer lookups, the agent score skips both again; what remains
  (IOC corpus, ransomware victims, stolen sessions, CVEs) is RESCALED to 0-100 (`_FIRST_PARTY_DOMAIN_MAX = 75`, `_FIRST_PARTY_AGENT_MAX = 40`). Without the rescale an
  agent could never exceed 40 and the "a CRITICAL agent elevates the org" rule could never fire. The response carries `data_path: first_party`, `signals_not_run`, and a note.
* `tech-stack-cve`: no public-exploit lookup; `poc_available` is ABSENT (not False). `mcp-registry-risk`: no registration-age lookup; `signals_not_run` names it.
* Stripe-direct, x402 and free-tier callers keep every lookup and the exact old response shape (asserted).
* The AWS-hosted MCP server is narrowed by `RS_MCP_TOOLS` to the five tools the listing sells plus status (six). `tools/create_mcp_http_lambda.sh` sets it
  and, on re-run, re-sends BOTH env vars (update-function-configuration replaces the block).
* `test_aws_first_party_path.py` (21 tests): no outbound call is made on the AWS path (urlopen replaced by a function that fails the test), rescaling, marker
  cannot be forged or suppressed, both real dispatchers executed. `test_relayshield_mcp_http.py` 35 tests. Both proven by mutation (six defects reintroduced each).
* The architecture diagram now says "Public data sources: read by the scheduled collectors; no customer query data is sent to them".

**Known limits, stated so nobody rediscovers them:** an AWS-licensed key that also has a Stripe customer can still call other metered endpoints (supply-chain, secret-scan)
and those still call third parties; they are not part of the listed product. 14 other test files fail in this container and fail identically on the commit before this
work (x402 manifest count 36 != 38, bundle_b_gating, day3, weekly_metrics and others); none were touched. Listing copy still quotes the retired corpus counts.

**NEXT, in order:** merge this branch; CI deploys `relayshield-api` and `relayshield-agentic-api` (check the run is green AND the import probe passes); re-run
`tools/create_mcp_http_lambda.sh` (it now sets the toolset); prove an AWS-licensed key's bulk-identity-risk response says `first_party`; THEN the listing change set (endpoint +
copy) and the Architecture details resubmission with the new diagram. The PRM prerequisite is still open: ask what Partner Central detects before adding a User Agent string anywhere.

## 2026-10-25 (pricing + copy): THE AWS EDITION OF BUNDLE D IS PRICED 5-10% BELOW STRIPE-DIRECT. TOOLS BUILT, NOTHING SUBMITTED.

**Decided by Andrew, in his words:** *"if we ever [have AWS subscribers], it should be at a 5-10% discount off the Stripe price which includes more. I'm ok to state the scores come
from RS own corpus."* He also removed agent-bait: *"a capability of the RS mcp proxy fw which is a different product."* There are no AWS subscribers, so no price moved.

* **Live offer read (Actions run 40237468649, `offer-3d5w6tbuis4wu`, State Released):** `UsageBasedPricingTerm` bulk_identity_risk 2.000, tech_stack_cve 0.200, mcp_registry_risk 0.350,
  prompt_injection_breach 0.350, llm_credential_exposure 0.400; `ConfigurableUpfrontPricingTerm` P1M agentic_bundle_access 299; plus Legal, Support, Renewal terms and a country
  TargetingRule. Identical to `aws_marketplace/offer_baseline_2026-07-31.json`. Stripe-direct per-call prices are `METERED_CREDIT_COSTS` in `relayshield_api.py`.
* **New AWS prices:** $270 monthly (9.7% off; $269 would be 10.03%, outside the band), bulk 1.800, tech-stack 0.180, mcp-registry 0.320, prompt-injection 0.320, llm-credential 0.360.
  Spec: `aws_marketplace/bundle_d_aws_prices.json`. Tool: `tools/marketplace_update_offer_prices.py` (dry run reads the live offer; copies the two pricing terms verbatim; ONE
  `UpdatePricingTerms` change; refuses a missing/extra dimension, a live price that has moved, a price outside the band, the wrong offer/state, apply without confirmation, wrong
  account). Workflow `.github/workflows/marketplace_offer_prices.yml` (dropdown confirm). `test_bundle_d_aws_prices.py`, 22 tests, proven by mutation; the request was also validated
  against botocore's real marketplace-catalog model in a throwaway venv. **NOT proven:** that AWS accepts `UpdatePricingTerms` on a Released public offer. Only AWS can say.
* **Listing copy** (`aws_marketplace/bundle_d_listing_copy.json`, paste file `bundle_d_listing_copy_aws_edition.md`, `test_bundle_d_listing_copy.py`, 13 tests): agent-bait out, no tool count,
  no "newly-registered" claim (the registration-age lookup does not run for AWS keys), no corpus counts, no vendor names, and the new promise "queries are not forwarded to outside data
  providers". **The old draft ShortDescription was 631 characters in a 500-character field and would have been refused;** the live accepted one is 475, this is 469.
* **Product edits go through the Management Portal, not a hand-built change set,** because the live delivery option is `Type: ApiRegistration` (`ApiType: MCP_SERVER`) and the repo holds no accepted
  change-set example for it. Inventing the shape would be the seven-rejections mistake again. The portal composes it, as it did for "Update architecture details" on 2026-09-22.
* **Stale wording left in place on purpose:** comments in `relayshield_developer_signup.py` (Bundle D "same product, same price, two doors") and `relayshield_api.py` ("the two doors cannot drift")
  predate this decision. Editing them would redeploy two live Lambdas for comments. The customer-visible "same rates as the AWS Marketplace listing" line is in the Bundle A email, not Bundle D.
* **ORDER, and why:** (1) merge, re-run `tools/create_mcp_http_lambda.sh` so the endpoint serves only the listed tools; (2) prices dry run, then apply; (3) portal: Fulfillment options, MCP endpoint
  to `https://api.relayshield.net/mcp`; (4) portal: Product information copy; (5) ONLY AFTER the endpoint change completes, portal: Architecture details plus the diagram. Declaring "entirely on
  AWS" before the endpoint moves would be a false public claim.

## 2026-10-26: THE MCP SETUP SCRIPT FAILED ON ITS FIRST RE-RUN. SHORTHAND `--environment` BREAKS ON COMMAS. FIXED AND PROVEN WITH THE REAL aws CLI.

Andrew's run of `tools/create_mcp_http_lambda.sh` died at step 5 with `Error parsing parameter '--environment': Expected: '=', received: ','`. **Mine, and knowable:** I wrote
`Variables={RS_DEMO_API_KEY=...,RS_MCP_TOOLS=a,b,c}`, and the CLI's shorthand reads every comma as a separator, while `RS_MCP_TOOLS` is a comma-separated list. The script header
did say "UNVERIFIED" about its AWS half, but that label is for what could differ in his state, not for a defect one `pip install awscli` reproduces in 30 seconds.

* **State left behind:** `update-function-code` had succeeded (the new module with `RS_MCP_TOOLS` support is on the function) and `update-function-configuration` had not, so the endpoint
  still serves all 13 tools until the script is re-run. Nothing is broken; the listing still points at the Space.
* **Fix:** the environment is built once as JSON by python3 (`ENV_JSON`) and passed to BOTH `create-function` and `update-function-configuration`. Reproduced the old error and verified the
  new form with `awscli` in a throwaway venv pointed at a dead endpoint, so it fails after argument parsing: the shorthand gives the caret under the comma, the JSON gives "Could not connect".
  The venv awscli is v1; his is v2, whose JSON-argument parsing is the same.
* **Test that would have caught it:** `SetupScriptEnvironment` in `test_relayshield_mcp_http.py` runs the script's OWN `ENV_JSON` line with the script's real tool list and parses the result,
  and refuses `Variables={` in any non-comment line. Proven by putting the shorthand back.
* **Also read this turn:** the "Marketplace Bundle D AWS prices" run (Actions 40248369052) was a DRY RUN against the live offer; the table matched the spec exactly; nothing was sent.
* **Lesson for the next script that passes a list to the aws CLI:** put it in JSON, and run the argument through the real CLI before handing it over. `pip install awscli` in the scratchpad venv works.

## 2026-10-26 (portal): THE AWS MCP ENDPOINT IS LIVE WITH 6 TOOLS; THE FULFILLMENT FORM'S USAGE TEXT STILL POINTED AT THE HUGGING FACE SPACE.

* `tools/create_mcp_http_lambda.sh` re-run succeeded after the JSON fix: `https://api.relayshield.net/mcp` and the execute-api host both return `tools/list -> 6 tools`; stage `co89ol` deployed.
* Andrew's Fulfillment options form (product `prod-kkvurtspreofy`, Management Portal) showed: Fulfillment method "Redirect to your website" (cannot be changed in the form; support request only),
  Fulfillment URL `https://api.relayshield.net/marketplace/bundle-fulfillment`, AI agent or tool details Type "MCP server", **MCP endpoint URL typed by Andrew into the form (from my instruction) as `https://api.relayshield.net/mcp`, NOT yet submitted, so the live listing still points at the Space**,
  MCP usage instructions (max 4,000 chars) and optional API usage instructions (max 4,000) still carrying the OLD text, Authorization method "API key", and
  **"Amazon Bedrock AgentCore Gateway integration": "Enable tool for AgentCore Gateway integration - Recommended" vs "Do not enable" (currently NOT enabled).**
* **Submitting only the URL would have left the listing contradicting itself:** the old MCP instructions say "Point your MCP client at: ...hf.space/gradio_api/mcp/sse" and describe
  "domain-registration age"; the old API instructions say mcp-registry-risk scores "registration-age red flags". Both are false on the AWS path. Replacement:
  `aws_marketplace/bundle_d_mcp_usage_instructions.md` (2,049 chars, guarded by `McpUsageInstructions` in `test_bundle_d_listing_copy.py`, proven by five mutations). For the API instructions the
  single phrase "registration-age red flags" becomes "known-malicious domains".
* **TRADE-OFF TO KNOW:** the Space spoke the legacy SSE transport; the AWS endpoint speaks Streamable HTTP (the current MCP transport). An MCP client that supports only SSE cannot use the new URL.
  The Space stays up for existing configurations, and the new text names the transport so nobody is surprised.
* **AgentCore Gateway integration is a discovery lever worth a look, NOT done:** AWS marks it "Recommended" and it is aimed at exactly the "buyers are not finding my licenses" problem. It needs an
  OpenAPI 3.x file (`relayshield_openapi_spec.py` exists) and has requirements the repo has not read. Do not tick it in the same submission as the endpoint change.

## 2026-10-26 (portal, second attempt): THE FORM REJECTED A TRAILING NEWLINE, AND THE WRONG FILE WAS PASTED.

Andrew's screenshot: the MCP usage instructions field held the LONG DESCRIPTION text, with the error **"Values can not start or end with whitespace characters (space, tab, newline)."**
* **Two faults, both mine:** (1) I had sent two paste files in one session (the Product information copy and the MCP usage text) and the wrong one ended up in the field; (2) my usage-instruction
  files ended with a newline, so even the RIGHT file would have been refused. Whole-field paste files now carry NO trailing newline and each starts with its own heading ("Connecting",
  "Overview"), so a wrong paste is obvious on sight.
* **`aws_marketplace/bundle_d_api_usage_instructions.md` (3,710 chars of 4,000):** the LIVE REST usage text, rebuilt from the Actions log of run 40201513798, with exactly one sentence changed:
  "registration-age red flags" became "known-malicious domains". Andrew could not find that phrase in a small textarea, so he gets the whole field. After the form is submitted, READ THE LIVE ENTITY
  AGAIN and compare it to this file byte for byte: that is the check that the rebuilt text matches what was live.
* **Guards** (`PasteableWithoutWhitespaceErrors`, `ApiUsageInstructions` in `test_bundle_d_listing_copy.py`, proven by five mutations): no leading or trailing whitespace on any pasted field, no CR,
  the two usage files start with their own headings and are not the long description, the API text fits 4,000, the false claim is gone, the five endpoints and the curl continuations survive.
* **Lesson:** a value pasted into a portal field is validated by that portal, and the validation rules are knowable only from the form. When the first field is rejected, check every other pasted file
  for the same defect before sending the next one.

## 2026-10-26 (submitted): FULFILLMENT OPTIONS REQUEST IS UNDER REVIEW; A READ-ONLY LISTING VERIFIER NOW EXISTS.

* **Request `8k3v6j9uihtt9hh4vnp7lwbwzi`, "Update fulfillment options" (change: Update delivery options), entity `RelayShield - Consumption Security API Bundles`, status Under review**, submitted
  2026-10-25 8:40 PM EDT, revision `prod-kkvurtspreofy@30`. What Andrew actually pasted into the usage fields is NOT known to this session; the verifier is how it gets established.
  **One open change per product at a time (AWS seller-ops, 2026-07-17): do not submit the Product information copy until this request completes.**
* **`tools/verify_bundle_d_listing.py`** + workflow **"Marketplace Bundle D listing check (read only)"** (`marketplace_verify_listing.yml`; stage dropdown endpoint | copy | architecture | prices | all): reads the live product and
  the offer, compares byte for byte with `bundle_d_mcp_usage_instructions.md`, `bundle_d_api_usage_instructions.md`, `bundle_d_listing_copy.json` and `bundle_d_aws_prices.json`, prints PASS or DIFFERS per field,
  and says WHERE the first difference is and whether it is only whitespace. A named stage judges the exit code; all four stages are always printed. `test_verify_bundle_d_listing.py` (24 tests), proven by nine
  mutations, one of which SURVIVED the first version (highlights not compared) and now has tests. Run over a botocore-Stubber-validated `describe_entity` client in a throwaway venv.
  Fixture `aws_marketplace/fixtures/prod_kkvurtspreofy_before_2026-10-25.json` is the real entity structure before any change; free-text fields nobody reads are shortened.
* **My new workflow's first draft did not parse** (a plain YAML value containing ": "), which `test_workflows_parse.py` caught before it was pushed. That is the rule working; run it after every workflow edit.
* **NEXT:** when the request completes, run the verifier with stage `endpoint`; only if it PASSES, submit the Product information copy; verify stage `copy`; then Architecture details plus the diagram; verify
  stage `architecture`; then the prices dry run, apply, verify stage `prices`.

## 2026-10-26 (verified): ENDPOINT AND MCP TEXT ARE LIVE AND EXACT. THE API USAGE TEXT WENT LIVE CORRUPTED, BECAUSE IT WAS COPIED FROM A RENDERED MARKDOWN PREVIEW.

Request `8k3v6j9uihtt9hh4vnp7lwbwzi` Succeeded. Verifier run (Actions 40253202290, stage endpoint), read from the log:
* **PASS:** ApiType MCP_SERVER, exactly one endpoint, **endpoint URL `https://api.relayshield.net/mcp`**, authorization API_KEY only, **MCP usage instructions identical to `bundle_d_mcp_usage_instructions.md`**,
  fulfillment URL unchanged, product Public. The listing now points buyers at the AWS endpoint.
* **DIFFERS:** API usage instructions: live 3,675 characters against 3,710, first difference at character 214, `1. Subscribe` live as `1 Subscribe`.
  **Cause, reproduced to the character:** copying from a rendered Markdown view consumes the trailing backslash on every curl continuation line (13 lines, 2 characters each, the space before it trimmed too)
  and draws each `N. ` list marker as `N ` (9 markers, 1 character each). 26 + 9 = 35. A simulation of exactly that transform gives length 3,675 and first difference 214. The MCP file has neither
  construct, which is why it passed. **The live API text therefore LOST the backslashes in its curl examples, which breaks them if copied.** (The previous live text had them: the baseline read shows `\` line endings.)
* **MY FAULT:** I sent the paste files as `.md`. A `.md` opens in a previewer. For text that is pasted into a form, the exact bytes must reach the clipboard: `pbcopy < file` does that with no rendering in between.
  **Standing rule for any paste-into-a-form text: give a `pbcopy < ~/dev/relayshield/<path>` line, and say what the field must look like before submitting** (here: `1. Subscribe` keeps its period, curl lines end in a backslash).
* **Verifier improved** (`tools/verify_bundle_d_listing.py`): on a mismatch it now lists EVERY differing region and recognises the rendered-Markdown signature by name (`as_rendered_markdown`), with
  tests using the real numbers (`TheRenderedMarkdownSignature`, proven by mutation). The next stage is to resubmit the API text via pbcopy and re-run the endpoint check.
* **STILL TRUE, do not forget:** copy, architecture and prices stages all read DIFFERS, as expected; none has been submitted. One open change per product: the endpoint request is complete, so the copy may go
  next, but ONLY after the API text is fixed, because a Fulfillment-options resubmission is a change on the same product.

## WHERE 2026-10-26 LEFT THINGS. BUNDLE D "DEPLOYED ON AWS" WORK: ENDPOINT LIVE, API USAGE TEXT AWAITING RESUBMISSION. READ THIS FIRST.

**This section supersedes the earlier "WHERE ... LEFT THINGS" lists for the AWS Bundle D / FTR thread only.** The 2026-10-20 list still holds for everything else (first-seen sequence, WAFR, indicator report).

### WHY ANY OF THIS EXISTS
Andrew's goal is DISCOVERY on AWS Marketplace: buyers do not find his listings, so he wants the Foundational Technical Review (FTR) to qualify Bundle D for co-sell, Partner Solution Finder and an assigned AWS
sales contact (he intends to ask Dave Shapiro at AWS for a partner sales contact once qualified). The FTR on solution `soln-aicwx4eiyofnm` (linked to `prod-kkvurtspreofy`, "Consumption Security API Bundles")
is BLOCKED by two Partner Central prerequisites: **"AWS Marketplace product is deployed on AWS"** and **"Partner Revenue Measurement (PRM) enabled"**. The first was UNSPECIFIED because the listing's
Architecture details were declared "None of the above" on 2026-09-20 (not changed by the WAFR; the Requests log showed only our own edits). He chose, over my objection, to DILUTE the AWS edition of Bundle D
(AWS path makes no third-party calls, agent-bait removed, ~5-10% cheaper than Stripe-direct, Stripe-direct bundle unchanged). The two editions now diverge on purpose.

### STATE AT END OF SESSION (verified unless marked)
* **Code, all merged to Andrew's `main`, tests green for the new work:** first-party data path (`relayshield_api.py`, `relayshield_agentic_api.py`, CLAUDE.md rule); AWS-hosted MCP server `relayshield_mcp_http.py`
  (Lambda `relayshield-mcp-http`, `RS_MCP_TOOLS` = 6 tools); `tools/marketplace_update_offer_prices.py` + workflow; `tools/verify_bundle_d_listing.py` + workflow; listing copy and usage-text files under `aws_marketplace/`.
* **LIVE and verified (Actions run 40253202290, stage endpoint):** MCP endpoint `https://api.relayshield.net/mcp` (6 tools, both hosts proven), MCP usage instructions exact, ApiType MCP_SERVER, API_KEY auth only,
  fulfillment URL unchanged, product Public. Public is NOT news: it has been Public since Aug 5, and says nothing about FTR status.
* **LIVE but WRONG:** the **API usage instructions** field holds a 3,675-char corrupted text (curl backslashes and list-marker periods lost to a rendered-Markdown copy). Correct text is
  `aws_marketplace/bundle_d_api_usage_instructions.md` (3,710 bytes, starts `Overview`, no trailing newline). **Resubmission was IN PROGRESS when Andrew stopped: a Fulfillment options "update request" is open/in
  progress. Do not assume it completed.**
* **NOT SUBMITTED, all four read DIFFERS as expected:** Product information copy, Architecture details + diagram, prices (dry run matched; apply never run).
* **PRM prerequisite: unresolved.** No decision made on how it is detected.

### THE PASTE FAILURE, SO THE NEXT SESSION DOES NOT REPEAT IT
Twice Cmd+V in the portal pasted the TERMINAL TRANSCRIPT instead of the file (the clipboard was overwritten after `pbcopy`, most likely by copying terminal output to send to me; the portal then refused it for exceeding 4,000
characters, which is harmless). **Do not hand a `pbcopy` route again for this text.** The route that avoids the terminal altogether, verified byte-identical (3,710 bytes, `text/plain`, `cmp` IDENTICAL):
open `https://raw.githubusercontent.com/nzdsf2-gif/relayshield/main/aws_marketplace/bundle_d_api_usage_instructions.md`, Cmd+A, Cmd+C, then in the portal field Cmd+A, Delete, Cmd+V. Raw text view is not rendered, so no Markdown
corruption. Pre-submit check: first line `Overview`, `1. Subscribe` keeps its period, curl lines end in `\`. The same raw-URL route works for every other paste file. **Only possible while the file is on `main`.**

### TODO FOR NEXT SESSION, IN ORDER (one open change per product at a time)
1. **Ask Andrew whether the Fulfillment options request completed and what the API usage field held when submitted.** Then dispatch "Marketplace Bundle D listing check (read only)" with stage `endpoint` and read the
   log with the GitHub MCP tools. Pass condition: every endpoint line PASS, including API usage instructions. If it DIFFERS, the verifier names the first differing character and the cause.
2. **Product information copy** (only after step 1 passes): short description (469 chars), long description, 3 highlights, 13 keywords from `aws_marketplace/bundle_d_listing_copy.json` / `bundle_d_listing_copy_aws_edition.md`.
   Because that is many fields, give Andrew a raw-URL (or per-field `.txt`) for each, one field at a time, and say what each field must look like. Then verify stage `copy`.
3. **Architecture details + diagram** (only after endpoint is verified live): declare control and application planes on AWS, upload `assets/marketplace/consumption_security_architecture.png`. AWS feedback on this is fast
   (about an hour), so expect a possible rejection naming a dependency. Verify stage `architecture`.
4. **Prices:** workflow "Marketplace Bundle D AWS prices", mode `apply`, confirm `UPDATE-LIVE-PRICES`, ONLY on Andrew's explicit go. Dry run already matched the live card. UNVERIFIED: whether AWS accepts
   `UpdatePricingTerms` on a Released public offer; if refused, the error names why and the fallback is the portal's pricing edit. Verify stage `prices`.
5. **PRM:** before building anything, Andrew should ask AWS's PRM assistant WHAT the prerequisite detects (resource tags vs User Agent String `APN_1.1/pc_<productcode>$` in CloudTrail vs Marketplace Metering) and on
   WHICH resources. Product code is `46y72j0d99w7lyqkiqrakpc5k`. If it needs a User Agent string, the `relayshield-mcp-http` Lambda is the natural carrier; a separate heartbeat Lambda is the fallback.
6. **After 1 to 5 pass:** re-check Partner Central: does the FTR still show "Blocked", and on what? Only then is it worth Andrew emailing Dave Shapiro.

### OPTIONAL / LOWER PRIORITY
* AgentCore Gateway integration option was shown as "Recommended" in the portal (needs an OpenAPI file). Unexplored.
* Live proof of the first-party path with a real AWS-licensed key has not been done (the tests prove it; production has not been exercised).
* Stale `lambda-drift` issues (#53, #20, #19, #16, #13) are probably closable; check before closing.
* Code comments saying Bundle D is "same product, same price, two doors" are wrong since 2026-10-25; fix when those Lambdas are next deployed.
* Hudson Rock free-API terms still unread (attribution may collide with the no-vendor-names rule).
* 14 test files fail identically at baseline (x402 manifest count 36 vs 38, bundle_b_gating, day3, weekly_metrics and others). Pre-existing, not from this work.

### STANDING LESSONS FROM THIS SESSION (rules, not history)
* Paste-into-a-form text: raw bytes only, no trailing newline, and say what the field must look like before submit. Never send a `.md` to be opened in a previewer and copied.
* "Public" on a catalogue row means listed, not released-after-a-change and not validated.
* A claim about what is live is checked with the read-only verifier, not inferred from a form saying Succeeded.

### UPDATE, same night, 2026-10-26: ANDREW REPORTS THE API USAGE INSTRUCTIONS UPDATE SUCCEEDED IN AWS MARKETPLACE
His words: "It was successfully updated in AWS marketplace just now." **That is his report of the portal request, NOT a verifier result.** Todo 1 above shrinks to: dispatch "Marketplace Bundle D listing check
(read only)" with stage `endpoint` and confirm the API usage line PASSES (live text must be 3,710 characters, identical to `aws_marketplace/bundle_d_api_usage_instructions.md`). Workflow dispatch is a click for
Andrew (403 for Claude). If it passes, go straight to todo 2 (Product information copy). Nothing else changed tonight.

## 2026-10-26 (next session, step 2 prepared): PER-FIELD PASTE FILES FOR THE PRODUCT INFORMATION COPY. STEP 1 (ENDPOINT VERIFY) STILL NEEDS ANDREW'S CLICK.

* Read the Actions list: the only "Marketplace Bundle D listing check" run is 40253202290 (pre-fix, failed). Andrew's "update succeeded" is therefore still unverified; dispatch is a click for him.
* `aws_marketplace/portal_fields/` holds the six Product information fields, one file each, generated from `bundle_d_listing_copy.json`, no trailing whitespace, no CR. A test
  (`test_per_field_portal_files_are_exactly_the_json_fields`) fails if any file drifts from the JSON; proven by appending a character. Route: raw URL, Cmd+A, Cmd+C, per the 2026-10-26 lesson (no pbcopy).
* The portal's keyword control is unseen by this session; the keyword file is one per line and may need adapting to the form.

## 2026-10-26 (step 1 DONE): ENDPOINT STAGE ALL PASS, INCLUDING API USAGE INSTRUCTIONS.

Verifier run 40406106919 (stage endpoint, head a68264e), read from the job log: all 8 endpoint lines PASS (MCP_SERVER, one endpoint, `https://api.relayshield.net/mcp`, API_KEY only, MCP usage text exact,
**API usage text exact**, fulfillment URL unchanged, Public). The corrupted API text is fixed. Other stages read DIFFERS as expected. Live copy still has the old 475-char short description, the
5.0M/3,750/85 corpus-count highlight, and keywords 'consumption pricing' + 'agent framework security'. NEXT: Product information copy (step 2) from `aws_marketplace/portal_fields/`.

## 2026-10-26 (keywords): THE PORTAL'S KEYWORDS FIELD WANTS ONE COMMA-SEPARATED LINE, NOT ONE PER LINE.

Andrew's screenshot: "Provide a comma-separated list of keywords", up to 15 keywords, each under 50 characters. My per-line file was a guess about a control this session had not seen, and I had flagged it as unseen. File is now
`aws_marketplace/portal_fields/6_search_keywords_comma_separated.txt` (13 keywords joined by a bare comma, no space after it, so no keyword can start with whitespace); the drift test was updated and passes.

## 2026-10-26 (step 2 SUBMITTED): "UPDATE PRODUCT INFORMATION" REQUEST `6e7hu041897ertq2ajm01r59y` IS UNDER REVIEW.

Submitted by Andrew 2026-10-26 6:06 PM EDT, change type "Update information", entity `RelayShield - Consumption Security API Bundles`, from the six files in `aws_marketplace/portal_fields/`
(keywords as one comma-separated line). **What he actually pasted into each field is NOT known until the verifier reads it.** One open change per product: NOTHING else may be submitted until this shows Succeeded.
NEXT: when it Succeeds, Andrew dispatches "Marketplace Bundle D listing check (read only)" with stage `copy`; I read the log. Only if copy PASSES: Architecture details + diagram
(`assets/marketplace/consumption_security_architecture.png`), then verify stage `architecture`, then prices (explicit go only), then PRM, then the Partner Central re-check.

## 2026-10-26 (step 2 DONE, step 3 READY): PRODUCT INFORMATION REQUEST SUCCEEDED AND THE COPY STAGE PASSES; THE FIRST-PARTY CODE IS CONFIRMED DEPLOYED.

* Request `6e7hu041897ertq2ajm01r59y` Succeeded. Verifier (run 40406106919, attempt 2, a "Re-run all jobs" that ran 23:06 UTC after the Succeeded; it prints all four stages from live data): **copy stage PASS on all four
  fields** (ShortDescription, LongDescription, Highlights, SearchKeywords); endpoint stage still all PASS. Architecture and prices still DIFFERS, as expected.
* Before declaring "runs entirely on AWS": deploy run 40235523349 (head c61fdd9, which contains cfa8bd9, the first-party path) succeeded and the import probe passed for `relayshield-agentic-api`, `relayshield-api` and
  `relayshield-mcp-http`. **Still NOT proven live:** an AWS-licensed key's response saying `data_path: first_party` (tests prove it with the real dispatchers; no production call has been made). Recommend doing it after submitting.
* NEXT: Architecture details + `assets/marketplace/consumption_security_architecture.png` (1600x900, already on main), then verify stage `architecture`; then prices on his explicit go; then PRM; then Partner Central re-check.

## 2026-10-26 (step 3 SUBMITTED): "UPDATE HOSTING ARCHITECTURE" REQUEST `7c016057sqdn42spdi30yevay` IS UNDER REVIEW (`prod-kkvurtspreofy@34`).

Submitted by Andrew 2026-10-26 7:14 PM EDT. The form had a single "Application plane" section ("Entirely or mostly in your seller AWS account", whose own text says both application and control plane run in the seller's
account) and NO separate control plane section, so only that was answered. **Not yet known:** whether the diagram upload was attached (Andrew did not say), and whether the entity will read CONTROL_PLANE as declared; the
verifier's `architecture` stage answers both. One open change per product: nothing else may be submitted until it shows Succeeded. If AWS rejects, the likely named cause is a third-party dependency; do NOT edit the diagram to hide the Cloudflare box.
NEXT: Succeeded -> verifier stage `architecture` (Andrew dispatches or re-runs; I read the job log) -> prices only on his explicit go -> PRM question -> Partner Central re-check.

## 2026-10-26 (step 3 DONE; PRM TOOL BUILT, NOT RUN): ARCHITECTURE STAGE ALL PASS; PRM = RESOURCE TAGGING `aws-apn-id = pc:46y72j0d99w7lyqkiqrakpc5k`.

* Request `7c016057sqdn42spdi30yevay` Succeeded (7:15 PM EDT). Verifier run 40406106919 attempt 3 (23:17 UTC): endpoint 8/8, copy 4/4, **architecture 3/3 PASS** (CONTROL_PLANE and APPLICATION_PLANE declared, diagram URL set). Only prices DIFFERS.
  The single "Application plane" answer ("seller AWS account") covered the control plane too; the form had no separate section.
* **Andrew's correction, recorded:** the trigger for contacting Dave Shapiro was the WAFR/FTR effort, not this listing work. He also expects more cleanup of "gaps"; the WAFR is 37 High / 15 Medium (2026-10-18).
* **PRM, researched by search only** (docs.aws.amazon.com and help.clazar.io are unreachable from the container, so everything below is SECONDARY): AWS offers three methods (Marketplace Metering, automatic for AMI/ML; Resource Tagging, suits SaaS;
  User Agent String, `APN_1.1/pc_<code>$`, management-plane SDK calls). Tag: key `aws-apn-id`, value `pc:<product code>` (AWS Jan 2026 launch announcement as quoted); newer account-suffixed key `aws-apn-id-<partner account id>` allows up to
  10 partners per resource. Only resources that INCUR CHARGES are attributed; IAM etc. give nothing; dashboard lags up to 7 days. The product code `46y72j0d99w7lyqkiqrakpc5k` is the real entity's `Description.ProductCode`.
  The earlier AWS-assistant advice (User Agent String) is for products that call INTO customer accounts; ours does not, so tagging is the route.
* **Built:** `aws_marketplace/prm_tag_spec.json` (4 Lambdas, REST API `atq6wtkp6k`, 6 DynamoDB tables) and `tools/prm_tag_resources.py` (dry run default; adds ONE tag; refuses to overwrite a different `aws-apn-id`; refuses wrong account;
  reports missing resources). `test_prm_tag_resources.py` 8 tests, 4 of 5 mutations caught by it; the 5th (wrong parameter name to the Lambda call) can only be caught against the real library, and WAS: botocore Stubber over the real lambda,
  apigateway and dynamodb service models passes for the real tool and rejects the mutant (check script was in the scratchpad, not committed). NOT proven: that AWS accepts the REST API ARN form for tagging, and that the FTR prerequisite turns
  Complete on this small a spend. Tagging relayshield-api attributes ALL of that shared function's spend to Bundle D's code; acceptable for the prerequisite.
* NEXT: Andrew runs the tool on the Mac (dry run, then `--apply`); wait up to 7 days for the dashboard; prices apply on his go; re-check Partner Central.

## 2026-10-26 (prices SUBMITTED): CHANGE SET `5bf8i6hbov1600xq5q10bs0m2` SENT; AWS REVIEWS ASYNCHRONOUSLY. GREEN MEANS SUBMITTED, NOT LIVE.

Actions run 40419471680 (apply, head a68264e, 23:24 UTC): the log's final lines are `SUBMITTED. ChangeSetId 5bf8i6hbov1600xq5q10bs0m2` and the document sent carries bulk 1.800, tech_stack 0.180, mcp_registry 0.320,
prompt_injection 0.320, llm_credential 0.360 and monthly agentic_bundle_access 270. **Not yet verified live:** the verifier's `prices` stage is the check; do not call prices done until it reads PASS. One open change on the
product until the change set finishes. PRM tagging is an AWS-account action, not a Marketplace change, so it does not collide.

## 2026-10-26 (prices, re-run refused): THE SECOND APPLY WAS REFUSED BECAUSE THE FIRST HAD ALREADY TAKEN EFFECT. THE GUARD WORKED.

Run 40419471680 attempt 2 (23:27 UTC, a re-run three minutes after the first apply) exited 2 with `REFUSED: the live prices are not the prices the spec was written against`, listing live agentic_bundle_access 270, bulk 1.800, llm_credential 0.360,
mcp_registry 0.320, prompt_injection 0.320, tech_stack 0.180. Those ARE the new AWS-edition prices, so change set `5bf8i6hbov1600xq5q10bs0m2` completed within about three minutes and the tool refused to apply the same change twice.
This is read from Andrew's screenshot of the refusal, NOT yet from the verifier: next, verifier stage `prices` must read PASS before prices are called done. Do not re-run apply.

## 2026-10-26 (ALL FOUR VERIFIER STAGES PASS): THE LISTING SIDE OF THE BUNDLE D "DEPLOYED ON AWS" WORK IS COMPLETE AND READ BACK FROM AWS.

Verifier run 40420394927 (stage all, 23:32 UTC, head a68264e), read from the job log: **endpoint 8/8, copy 4/4, architecture 3/3, prices PASS ("offer rate card is AFTER, the AWS-edition prices are live"), "ALL JUDGED CHECKS PASS".**
Requests: fulfillment `8k3v6j9uihtt9hh4vnp7lwbwzi`, product info `6e7hu041897ertq2ajm01r59y`, architecture `7c016057sqdn42spdi30yevay`, prices change set `5bf8i6hbov1600xq5q10bs0m2`, API usage text fixed.
**REMAINING, nothing else on the listing:** (1) PRM tagging on Andrew's Mac (`tools/prm_tag_resources.py`, dry run then `--apply`; NOT yet run as far as this session knows); (2) wait up to 7 days for the PRM dashboard; (3) re-check Partner Central: does the
FTR still show Blocked, and on what; (4) live proof of the first-party path with a real AWS-licensed key (still unproven in production); (5) then Dave Shapiro. Lower priority: AgentCore Gateway option, stale lambda-drift issues, stale "two doors" code comments.

## 2026-10-26 (two corrections from Andrew, both recorded): THE FTR NEEDS THE END-TO-END SUBSCRIPTION TEST; DAVE SHAPIRO IS CONTACTED ONLY AFTER THE WAFR GAPS ARE FIXED, RESUBMITTED, AND THE FTR PASSES.

* **E2E test, his words:** the FTR will not show a released product until the end-to-end test is run; it was done for earlier licenses. **I had the record and did not volunteer it** (`bundle_b_launch_runbook.md` steps 7 and 8, and 8c).
  The Bundle B precedent: a PRIVATE TEST OFFER targeted at buyer account `442429445748` ("TestUser"), granting the Entitled dimension once and pricing every metered dimension at `0.00000001` (non-zero on purpose so
  `BatchMeterUsage` really runs); accept it in the buyer's browser -> agreement; the FULFILLMENT REDIRECT posts a registration token -> `ResolveCustomer` -> `GetEntitlements` -> pending row -> SNS subscribe-success provisions the API key -> one metered call
  -> `BatchMeterUsage` with the LicenseArn. Those are exactly what AWS audits ("successful calls to the Entitlements Service", "successful metering records"). Bundle D has only `bundle_a_*` and `bundle_b_*` test-offer files in `aws_marketplace/`; **there is no `bundle_d_test_offer.json`**.
  **THE SAME TEST IS THE MISSING LIVE PROOF of the first-party path:** the key it provisions carries `aws_customer_id`, so one call to `bulk-identity-risk` must answer `data_path: first_party`.
  Not yet done: read how Bundle D's earlier test was run (it has 0 subscribers, so it may have used another route), then derive and dry-run a Bundle D test offer. One open change per product, so it waits for any in-flight request.
* **Dave Shapiro, his words:** NOT when this license is unblocked. The earlier plan is: address some of the WAFR gap items and resubmit; **when that AND the FTR pass, contact him.** The WAFR is 37 High / 15 Medium (2026-10-18). The only written starting points found are `ftr_finish_2026-10-18.md` section 4
  (the remaining High risks, each to carry a concrete plan in its Notes) and the sequence at LOG line 448 (re-tick and re-word the WAFR, save milestone, PDF under 3 MB, request FTR validation again, then email Dave). No dated remediation plan was found. Earlier lines in this log that make the Bundle D licence the trigger for contacting him are superseded.

## 2026-10-26 (PRM TAGS APPLIED): `aws-apn-id = pc:46y72j0d99w7lyqkiqrakpc5k` ON 11 RESOURCES, READ FROM ANDREW'S TERMINAL.

Dry run showed 11 TODO, 0 conflicts, 0 missing. `--apply` printed TAGGED for the 4 Lambdas (`relayshield-api`, `-agentic-api`, `-mcp-http`, `-bundle-fulfillment`), REST API `atq6wtkp6k` and 6 tables (`relayshield_api_keys`, `_intel_iocs`, `_stolen_sessions`,
`_ransomware_victims`, `_intel_cve`, `_identity_graph`) with no error. The "11 to tag" count is taken before tagging, so it was expected on the apply run. **A second dry run (expect 11 OK) has not been read yet.** The PRM dashboard may take up to 7 days.
Andrew has NOT seen Amazon's WAFR response (nobody has; it is not in Gmail or the repo). His question: can he resubmit for FTR approval after PRM + the E2E test offer, before the WAFR list? Not answered by any source in the repo (`ftr_finish_2026-10-18.md` s.4: "UNVERIFIED whether unresolved High risks block approval"; the FTR Guide has never been read). The "Request validation" button is greyed until Partner Central's prerequisites are Complete, so the PRM wait (up to 7 days) sets the earliest date either way.

**Confirmed later the same night:** a second dry run read `OK  already tagged` on all 11 resources, `0 to tag, 11 already done, 0 need attention`. PRM dashboard lag (up to 7 days) now runs from 2026-10-26.
NEXT: Andrew to screenshot Partner Central, solution `soln-aicwx4eiyofnm`, **Validation** tab (and Change history if no WAFR response is there): FTR status, prerequisites, any WAFR result, any FTR Guide text on High risks. Then Bundle D E2E test offer (the change-set tool's live-listing refusal must be read first), then the WAFR list.

## 2026-10-26 (E2E): BUNDLE D TEST OFFER BUILT AND DRY-RUN CLEAN; THE LIVE-LISTING GUARD DOES NOT REFUSE IT. NOT SENT.

* `aws_marketplace/bundle_d_test_offer.json` = Bundle B's accepted test offer with ONLY the product id (literal `prod-kkvurtspreofy`, so there is no typed placeholder), the six live dimension keys (grant `agentic_bundle_access`, five metered at `0.00000001`) and the wording changed.
  Private offer to buyer account `442429445748`, one month, charge 0.01 USD, same nine changes ending in `ReleaseOffer`. `python3 tools/marketplace_submit_changeset.py aws_marketplace/bundle_d_test_offer.json` (dry run, no AWS needed) validates 9 changes, both dates ok.
* **The tool's LIVE_ENTITIES guard checks only `Entity.Identifier`; a `CreateOffer` carries its product in `DetailsDocument.ProductId`, so it passes, correctly (a new private offer replaces no rate card).** No tool change. The guard still refuses any change whose Entity.Identifier is the live id (tested).
  The runbook's claim that a typed Bundle A/D id is refused at test-offer time is NOT what the code does; I could not find that check.
* The only dry-run warning left is the DimensionKey `llm_credential_exposure` (23 chars vs 21 proven): unavoidable, it is the real live dimension and is already accepted inside the live offer. My first description was 135 chars vs 129 accepted; shortened to 111.
* `test_bundle_d_test_offer.py` (8 tests, 5 mutations caught: wrong product, wrong buyer, zero price, truncated key, last change swapped).
* **Dispatch needs the file on `main`** (the OIDC trust is tight, so a run from a branch is unlikely to assume the role; UNVERIFIED). Andrew's local `main` was 5 commits ahead of `origin/main` with no Lambda `.py` among them, so pushing it deploys nothing.
* NEXT: merge to main + `git push origin main`; Actions "Marketplace Change Set" with changeset `aws_marketplace/bundle_d_test_offer.json`, dry-run then apply (confirm `CREATE-NEW-PRODUCT`, `product_id` EMPTY); accept the private offer from the TestUser buyer account; follow the fulfillment redirect;
  read the key; ONE call to `bulk-identity-risk` must say `data_path: first_party`; verify `BatchMeterUsage` succeeded. Still pending from Andrew: the Validation-tab screenshot.

## 2026-10-26 (Partner Central, read from screenshots): THE SOLUTION IS LIMITED AND THAT IS REQUIRED FOR THE FTR; "UPDATE VISIBILITY" IS NOT AN AUDIT TRIGGER FOR THIS WORK AND SHOULD NOT BE CLICKED.

Solution `soln-aicwx4eiyofnm` "RelayShield Agentic Attack Surface API", type Software, **Status Limited**, last modified Oct 8. The Validation tab says verbatim: "To check the FTR status of your solution or request an FTR, choose Request validation. You're redirected to Partner Central, where you can
access the validation page... your solution must have an approved FTR [to co-sell, get APN benefits or appear in Partner Solution Finder]. **Your solution must be in Limited status before you can request an FTR. An FTR is not required to list your solution publicly in the AWS Marketplace catalog.**"
Overview text: multi-product solutions with more than two public products can be publicly listed; ours is single-product (validated via FTR instead). So: the solution-level "Update visibility" button is NOT the product-level UpdateVisibility that audited Bundle B, and moving a Limited solution to Public would leave the state the FTR requires.
"Request validation" on this tab only redirects to the Partner Central validation page (the prerequisites list read on 2026-10-25); it is safe to click to READ; no FTR is requested until a submit control on that page, which was greyed out while prerequisites were incomplete. Not yet seen again after the architecture, price and PRM work.
