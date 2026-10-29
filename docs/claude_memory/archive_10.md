<!-- Verbatim sections moved out of CLAUDE.md on 2026-10-18, original order. Not auto-loaded.
     Find one with: grep -n 'WORDS' docs/claude_memory/INDEX.md -->

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

