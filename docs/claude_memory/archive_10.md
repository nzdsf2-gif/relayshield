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

