# LOG_CURRENT: recent session records

<!-- NEW SESSION RECORDS ARE APPENDED HERE, NEVER TO CLAUDE.md. Newest last. The last
     'WHERE ... LEFT THINGS' section supersedes the ones above it. When this passes
     90,000 characters run: python3 tools/claude_memory.py --rotate --write -->

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

## 2026-10-27 (Partner Central Validation details, read from screenshots): FOUR OF FIVE PREREQUISITES COMPLETE; ONLY PRM IS INCOMPLETE. THERE IS NO E2E PREREQUISITE ON THIS LIST.

Solution `soln-aicwx4eiyofnm`, Validation details page: **FTR status Blocked; "Request validation" greyed.** Prerequisites (run in sequence): linked to exactly one Marketplace product **Complete**; no non-Marketplace products **Complete**; linked to a software product **Complete**;
**"AWS Marketplace product is deployed on AWS" Complete (it was Incomplete on 2026-10-25: the architecture request took effect)**; **"AWS Marketplace product is Partner Revenue Measurement (PRM) enabled" Incomplete.** Banner, verbatim in substance: PRM is now part of the FTR; integrate at least one of Resource Tagging, User Agent String
or AWS Marketplace Metering; track status in the onboarding table of the **Attributed Revenue dashboard** on Partner Central; **the dashboard refreshes DAILY and compliance can take up to 7 days to surface after integration**; if nothing after 7 days, use the PRM onboarding troubleshooting guide or APN Support.
The tags went on 2026-10-26 evening, so the window runs to about 2026-11-02. A "Software FTR guide" link and a Refresh button are on the page. **Not on the list: an end-to-end subscription test, or a WAFR line.** Andrew's reading: E2E was required to go Limited to Public, and may not be needed for the FTR. That is consistent with the page but NOT proven: the FTR itself may check things the prerequisites list does not (the Software FTR guide is unread).

## 2026-10-27 (THE SOFTWARE FTR GUIDE, last updated 2026-10-26, read from Andrew's screenshots): THE FTR IS AN AUTOMATED WAFR CHECK. ZERO HIGH-RISK ISSUES (HRIs) ARE REQUIRED IN SECURITY, OPERATIONAL EXCELLENCE AND RELIABILITY ONLY. NO E2E TEST. PRM HAS AN OPT-IN STEP WE HAVE NOT DONE.

* **How it works:** submit a SOC 2 Type II report OR a WAFR report through the Validation tab; "receive automated results in minutes", "no manual review queue", AI-generated feedback on failed controls. FTR valid two years. **This supersedes my earlier warning that a rejected FTR "costs a full review cycle"; the guide says otherwise. NOT seen: the "If validation fails" and FAQs sections (whether a failure has any cooldown or limit).**
* **WAFR validation checks (verbatim in substance):** report completed within the last 12 months; **zero active HRIs in the Security pillar; zero in Operational Excellence; zero in Reliability** (the guide says medium-risk items do not affect those controls; Performance, Cost and Sustainability are NOT in the check list);
  the workload NAME or DESCRIPTION must explicitly match or closely align with the SOLUTION name (ours: "RelayShield Agentic Attack Surface API"; the workload is "RelayShield API", so add the solution name); the WAFR **reviewer owner must be "First Last - email"**.
  So the 37 High / 15 Medium (2026-10-18) matters only for the SEC, OPS and REL High items. The per-pillar HRI counts have NOT been read; they are in the WAFR Tool's Overview.
* **Prerequisites (five):** one Marketplace product; no non-Marketplace products; software type; Deployed on AWS badge; **PRM enabled: "To enable: go to your product in the AWS Marketplace Management Portal > Attributed Revenue tab > opt in to Partner Revenue Measurement. PRM uses resource tagging and Marketplace Metering ... can take up to 7 days after enablement."**
  **THE OPT-IN IS NOT DONE AND MY EARLIER PRM PLAN (TAGGING ONLY) OMITTED IT.** My web search could not confirm an opt-in step; AWS's own guide says it exists, so the guide wins. The Attributed Revenue DASHBOARD is under Partner Analytics in Partner Central; the opt-in is on the product's tab in the Management Portal.
* **No end-to-end test requirement appears anywhere in the guide.** It stays useful only as the live proof of the first-party data path.
* **Automating the PRM check:** searched; found NO API for the Partner Central FTR prerequisite status or the Attributed Revenue dashboard (AWS docs unreachable from the container, so not conclusive). Gmail has shown no AWS status emails. So a daily poll is not possible; the honest substitute is a reminder.

## 2026-10-27 (screenshots): NO "ATTRIBUTED REVENUE" TAB ON THE PRODUCT; THE FTR HAS NO RESUBMISSION LIMIT; TWO PRM REMINDERS SCHEDULED.

* **The Management Portal product page for `prod-kkvurtspreofy` (Public, product code `46y72j0d99w7lyqkiqrakpc5k`) has tabs: Requests log, Product information, Pricing configuration, Fulfillment options, Architecture details, Tags, Vendor Insights. There is NO Attributed Revenue tab.**
  So the guide's "opt in on the Attributed Revenue tab" does not match what Andrew's portal shows; do not invent an opt-in. The FAQ says PRM is "enabled via Resource Tagging, User Agent string, or Marketplace Metering" and that a still-Incomplete check needs "7 days after enablement, then Refresh". The tags (2026-10-26) are the enablement. The Attributed Revenue DASHBOARD lives under Partner Analytics in Partner Central; its onboarding table is the place to see the product's PRM status (not yet looked at).
  Request `bundle_d_aws_edition_prices` shows Succeeded, 2026-10-26 7:24 to 7:25 PM EDT (the prices change set). Requests log has 20 entries.
* **FTR failure mode, from the guide:** "Validation document did not pass review", a Validation Feedback section lists each failing control with remediation, the button becomes **Resubmit, and there is NO LIMIT on resubmissions.** Sample failures: report not within 12 months; HRIs in Security / Operational Excellence / Reliability; workload not referencing the solution name. So a first submission costs nothing but a PDF (under 3 MB) and is itself the cheapest way to see the exact failing controls. FAQ: disagree with a result -> contact AWS Partner Support (they can get a PSA to review).
* **WAFR Tool** workload "RelayShield API", AWS Well-Architected Framework lens, 57/57 answered, **37 high, 15 medium**, last updated 2026-10-18 8:35 PM; no profile attached; pillar priority order OPS, SEC, REL, PERF, COST, SUS. **Per-pillar HRI counts still NOT read** (open the lens page, not the workload summary).
* **Scheduled (Andrew said "ok on plain reminder"):** `trig_01KS2P51C5Q6XKpdiJeKPfE1` fires 2026-10-29 14:00 UTC (day 3 check); `trig_01WefXijabC2ZxJC8XaUzu69` fires 2026-11-02 14:00 UTC (day 7 check and escalation to PRM troubleshooting guide / APN Support, with a drafted message). Both are send_later into this session; cancel with delete_trigger.

## 2026-10-27 (Attributed Revenue dashboard, WAFR workload edit): DASHBOARD EMPTY, AND ITS OWN NOTE SAYS "UP TO 7 BUSINESS DAYS"; THE DESCRIPTION WAS PUT IN THE NOTES FIELD, NOT THE DESCRIPTION.

* **Attributed Revenue dashboard (Partner Central > Partner Analytics): "No data to display".** Its note, verbatim in substance: once the organization has at least one product listed in the "Products and AWS services enabled for PRM" table (**which may take up to 7 BUSINESS days after PRM implementation**), the organization is PRM compliant; if a product is not visible after implementing, contact the Partner Management team or APN support.
  So the real test is the PRODUCT APPEARING in that table. 7 business days from Monday 2026-10-26 evening is Wednesday 2026-11-04. **The day-7 reminder `trig_01WefXijabC2ZxJC8XaUzu69` was moved from 2026-11-02 to 2026-11-05 14:00 UTC for this reason.** The day-3 reminder (2026-10-29) is unchanged.
* **WAFR workload edit:** Andrew typed "RelayShield Agentic Attack Surface API" into **"Edit workload notes"** (an optional free-text field). The FTR check reads the workload NAME or DESCRIPTION, and the REVIEW OWNER, which are workload PROPERTIES, a different edit page. Notes were left as they are (harmless). UNVERIFIED against his console layout: properties are edited from the workload page's properties section.
* Per-pillar HRI counts still NOT read (he opened the workload page, not the lens page). Generate the PDF only AFTER the properties and the HRI fixes are saved.

## 2026-10-27 (WAFR workload properties SAVED; per-pillar HRIs still unread).

Properties tab now reads: Name "RelayShield API"; **Description "RelayShield Agentic Attack Surface API: identity exposure, credential and agent-tooling risk checks over HTTPS. API Gateway, Lambda and DynamoDB in one AWS account, plus scheduled collectors that feed the data it serves."** (names the solution, as the FTR check needs);
Review owner **"Andrew Gibbs, andrew@relayshield.net"** (comma, but the FTR guide's example is "First Last - email" with a DASH; the automated parser may require it, so change it to "Andrew Gibbs - andrew@relayshield.net"); Environment Production; Region us-east-1; Account 239677749008.
Andrew's last screenshot was the Dashboard's "Well-Architected Framework issues by improvement plan item (163)" with filters All pillars / High risk issues (first rows are Cost Optimization). It has a pillar dropdown; the three pillar counts that matter (Security, Operational Excellence, Reliability) have NOT been read.
Rule for the fixes: ticking a best practice in the Tool is an attestation. Fix the infrastructure first, tick only what is true (the 2026-10-18 lesson: this repo writes the aspiration).

## 2026-10-27 (WAFR SECURITY HIGH-RISK LIST, read from three screenshots): 36 UNMET HIGH-RISK BEST PRACTICES ACROSS 9 OF THE 11 SECURITY QUESTIONS. THIS IS A PROGRAM, NOT A WEEK'S TIDY-UP.

Review owner now reads "Andrew Gibbs - andrew@relayshield.net" (dash, as the FTR guide's example). Description names the solution (saved).
Dashboard list "issues by improvement plan item", filter Security + High risk, 36 rows (the dashboard's unit is a best practice not met, NOT a question; the lens counted 37 high-risk QUESTIONS in total across all six pillars; how many of those are Security was not shown).
**SEC1 operate:** Separate workloads using accounts; Secure account root user and properties; Identify and prioritize risks using a threat model; Evaluate and implement new security services and features regularly.
**SEC2 identities:** Use temporary credentials; Rely on a centralized identity provider; Employ user groups and attributes.
**SEC3 permissions:** Grant least privilege access; Define permission guardrails for your organization; Manage access based on lifecycle; Establish emergency access process; Reduce permissions continuously; Analyze public and cross account access.
**SEC5 network:** Create network layers; Implement inspection-based protection; Automate network protection.
**SEC6 compute:** Provision compute from hardened images; Reduce manual management and interactive access; Automate compute protection.
**SEC7 data classification:** Understand your data classification scheme; Automate identification and classification.
**SEC8 data at rest:** Automate data at rest protection; Enforce access control.
**SEC10 incident response:** Identify key personnel and external resources; Develop incident management plans; Prepare forensic capabilities; Develop and test security incident response playbooks; Pre-provision access; Run simulations.
**SEC11 application security:** Perform regular penetration testing; Regularly assess security properties of the pipelines; Train for application security; Automate testing throughout the development and release lifecycle; Conduct code reviews; Centralize services for packages and dependencies; Build a program that embeds security ownership in workload teams.
**Not in the list (so not HRI): SEC4 detect and investigate (logging, central analysis, response automation) and SEC9 data in transit.**
Triage proposed to Andrew: (A) written plans and processes (threat model, incident plan, playbooks, forensic plan, key personnel, emergency access, data classification, security review cadence, training, ownership): drafted by Claude from the repo, true only once adopted; (B) cheap AWS configuration (root user MFA and key deletion, IAM Access Analyzer, GuardDuty/Security Hub/Inspector, Identity Center, WAF on the API, KMS/encryption defaults); (C) structural (separate accounts and SCP guardrails via AWS Organizations; one IAM role per Lambda per `iam_role_split.md`).
Operational Excellence and Reliability high-risk lists NOT yet read; still needed to size the whole job.

## WHERE 2026-10-27 LEFT THINGS. BUNDLE D LISTING SIDE IS DONE AND VERIFIED; PRM TAGS ARE ON; THE FTR NOW TURNS ON PRM (WAIT) AND ON ZERO HIGH-RISK WAFR ISSUES IN SECURITY, OPERATIONS AND RELIABILITY. READ THIS FIRST.

**This supersedes the 2026-10-20 "WHERE ... LEFT THINGS" list (now in `archive_10.md`, find it with `grep -n "WHERE 2026-10-20" docs/claude_memory/INDEX.md`) for the AWS Bundle D / FTR / WAFR thread. The first-seen and housekeeping items from that list are carried below, unchanged.**

### WHAT IS DONE AND PROVEN (read back from AWS or from Andrew's own screenshots, not assumed)
* **Bundle D listing, `prod-kkvurtspreofy`:** verifier run 40420394927 (stage all) read **endpoint 8/8, copy 4/4, architecture 3/3, prices PASS.** Requests: fulfillment `8k3v6j9uihtt9hh4vnp7lwbwzi`; product information `6e7hu041897ertq2ajm01r59y`; architecture
  `7c016057sqdn42spdi30yevay` (Application plane "seller AWS account"; the form had no separate control-plane section); prices change set `5bf8i6hbov1600xq5q10bs0m2` (live within about 3 minutes; the second apply was correctly refused). API usage text fixed (it had lost its curl backslashes to a rendered-Markdown copy).
  Re-run the check any time: Actions, "Marketplace Bundle D listing check (read only)", stage `all`. A green tick alone is not proof: read the job log (`mcp__github__get_job_logs`).
* **Partner Central, solution `soln-aicwx4eiyofnm` (Limited, which the FTR requires): four of five prerequisites Complete, including "deployed on AWS". Only "PRM enabled" is Incomplete; FTR Blocked.**
* **PRM tags applied 2026-10-26 evening, `aws-apn-id = pc:46y72j0d99w7lyqkiqrakpc5k`, on 11 resources** (4 Lambdas, REST API `atq6wtkp6k`, 6 tables); a second read showed all 11 OK. Tool `tools/prm_tag_resources.py`, spec `aws_marketplace/prm_tag_spec.json`, `test_prm_tag_resources.py`.
  Run on the Mac: `AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/prm_tag_resources.py` (add `--apply` to write).
* **WAFR workload properties saved:** description names "RelayShield Agentic Attack Surface API"; review owner "Andrew Gibbs - andrew@relayshield.net" (dash format, as the FTR guide requires).
* **First-party data path is deployed** (deploy run 40235523349, import probe passed for api, agentic-api, mcp-http). **NOT proven live:** an AWS-licensed key's call returning `data_path: first_party`.
* **Bundle D test offer is BUILT and dry-run clean, NOT SENT, and no longer on the critical path:** `aws_marketplace/bundle_d_test_offer.json` + `test_bundle_d_test_offer.py` (8 tests, 5 mutations caught). The change-set tool's live-listing guard does not refuse it (a `CreateOffer` carries its product in `DetailsDocument.ProductId`). It needs the file on `origin/main` to dispatch (OIDC trust is likely main-only; UNVERIFIED).
  Its remaining value: the live proof of the first-party path. Dry-run: `python3 tools/marketplace_submit_changeset.py aws_marketplace/bundle_d_test_offer.json`.

### THE FACTS THAT CHANGED THE PLAN (all from the Software FTR guide and Partner Central, read from Andrew's screenshots 2026-10-27)
* **The FTR is an AUTOMATED check of a WAFR report (or SOC 2 Type II)**, results in minutes, **NO LIMIT ON RESUBMISSIONS**, valid two years. WAFR controls: report within 12 months; **zero active High-Risk Issues in SECURITY, OPERATIONAL EXCELLENCE and RELIABILITY only** (Performance, Cost, Sustainability are not checked; medium risks do not matter);
  workload name or description references the solution name; reviewer owner "First Last - email". Failure shows per-control AI feedback and the button becomes Resubmit. Upload is a PDF under 3 MB. **Generate the PDF only after the HRI fixes and properties are saved.**
* **No end-to-end subscription test is on the FTR prerequisites or in the guide.** (Andrew's earlier statement that it was needed applied to Limited to Public.)
* **PRM:** no "Attributed Revenue" tab exists on the Management Portal product; the guide's opt-in step does not match his portal, so none was invented. The dashboard is under Partner Analytics in Partner Central and is currently "No data to display"; its note says a product can take **up to 7 BUSINESS days** to appear, and once one is listed the organization is PRM compliant. 7 business days from Mon 2026-10-26 is **Wed 2026-11-04**.
* **I could not automate a daily PRM check:** no API found for the Partner Central prerequisite status or the dashboard (AWS docs are unreachable from the container, so not conclusive); AWS sends no status emails. Substitute: two reminders into this session, `trig_01KS2P51C5Q6XKpdiJeKPfE1` (**2026-10-29 14:00 UTC**, day-3 Refresh check) and `trig_01WefXijabC2ZxJC8XaUzu69` (**2026-11-05 14:00 UTC**, escalate to the PRM troubleshooting guide / APN Support with a drafted message). Cancel with `delete_trigger`.
* **Andrew's corrections, standing:** (1) **Dave Shapiro is contacted ONLY after the WAFR gaps are fixed, the WAFR resubmitted, AND the FTR passes**, not when the license unblocks. (2) The E2E test requirement was for visibility, not the FTR. (3) He keeps his own list: "address some of the open WAFR gaps and resubmit".

### THE WAFR WORK, WHICH IS NOW THE LONG POLE (a program of weeks, not days)
* The Tool: workload "RelayShield API", AWS Well-Architected Framework lens, 57/57 answered, **37 high-risk QUESTIONS, 15 medium** (2026-10-18). The dashboard's "improvement plan item" list counts unmet best practices: **Security has 36 across 9 of 11 questions** (list in the 2026-10-27 entry "WAFR SECURITY HIGH-RISK LIST"). SEC4 (detect and investigate) and SEC9 (in transit) are NOT high risk.
* **OPERATIONAL EXCELLENCE AND RELIABILITY LISTS ARE NOT YET READ.** First step next session: Andrew filters the same dashboard list (gear icon, page size 50; pillar dropdown; "High risk issues") for Operational Excellence and then Reliability and screenshots them, so the whole job can be sized.
* **Recommendation (mine, Andrew has not yet answered it):** tick NOTHING until true (the 2026-10-18 lesson: this repo writes the aspiration). Order: **B** cheap AWS settings first (root user MFA and DELETE the old access key ending `N2XZ`, overdue since 2026-10-16; IAM Access Analyzer; GuardDuty / Security Hub / Inspector; Identity Center for his own login; a WAF in front of the API), then **A** written plans and processes that I draft from the repo and he adopts (threat model, incident management plan, playbooks, forensic plan, key personnel, emergency access, data classification, security review cadence, training, security-ownership program, pen-test plan), and **C** structural only after sizing: separate accounts and permission guardrails via AWS Organizations (there are already two other accounts, `620534471984` pre-audit and `442429445748` test buyer), and one IAM role per Lambda (`iam_role_split.md`, multi-day).
  A question moves from High to Medium by satisfying enough best practices, not all. The per-question rules are visible only in the Tool. A Well-Architected partner is the paid alternative; not recommended yet. Starting offer to Andrew: a READ-ONLY script that reports root user status and Access Analyzer, before anything changes.
* The older cheapest-first list (API alarm and deploy guard, gas-monitor KMS grant, cost budget, reserved concurrency (quota 1,000 approved 2026-10-12), log retention on 8 groups, tags, Lambda versions and aliases, tests in CI, load test) is in `archive_10.md` under "WHERE 2026-10-20", part B item 2. **Cost, performance and sustainability items no longer matter for the FTR**; alarms, rollback (versions and aliases), concurrency and tests map to Operational Excellence and Reliability.

### ORDER FOR THE NEXT SESSION
1. `git fetch --all --prune`, then `git branch --show-current` (must be `claude/kind-fermi-2y6dhb`, or a fresh branch if that one is merged); read this section; ask Andrew for the PRM dashboard and Validation status.
2. Get the Operational Excellence and Reliability HRI screenshots; produce one ranked, cheapest-first table of all three pillars with the build / document / decide label on each.
3. Start group B with a read-only check script; Andrew runs it; then the changes, one at a time, each verified before any box is ticked.
4. When PRM reads Complete: generate the WAFR PDF (after fixes), request validation, read the feedback, resubmit. Only then, Dave Shapiro.
5. Optional: the Bundle D test offer and the live first-party proof; AgentCore Gateway option.

### CARRIED FROM THE 2026-10-20 LIST, UNCHANGED (see `archive_10.md`)
* First-seen sequence: backfill final line not pasted (re-run is safe, `tools/backfill_first_seen.py --apply`), feed-role grant (`tools/grant_feed_first_seen_write.py --apply`), weekly Lambda redeploy, feed flag only after both; put `relayshield_weekly_metrics.py` on a CI deploy path and in `lambda_drift_check.yml`;
  fix `relayshield-signup-api` in the deploy-invoke policy (`test_workflows_parse.py` fails on it); revoke the `sentinel_qa` API key; root access key deletion; x401 items; CS Mobile v1.7.0; Hudson Rock terms unread; Shopify parked.
* 14 test files fail identically at baseline (x402 manifest count, bundle_b_gating, day3, weekly_metrics, others); stale `lambda-drift` issues (#53, #20, #19, #16, #13) probably closable; "same price, two doors" code comments are stale.

### BRANCH STATE
Work is on `claude/kind-fermi-2y6dhb`, pushed. Andrew's local `main` was fast-forwarded to `7f569c3b` (includes the PRM tool, portal fields and tests) but has NOT been pushed to `origin/main`; the pending merge block for the Bundle D test offer file was never run. None of the unpushed changes touch a Lambda `.py`, so pushing `main` deploys nothing.
I cannot push `main`. Every merge block starts with the standard five lines in CLAUDE.md.

### STANDING LESSONS FROM THIS SESSION (rules, not history)
* **Read the job log, not the tick.** "Green" meant "submitted" for the prices run and "all stages printed" for the verifier; the log lines are the proof.
* **A portal form's control is unseen until a screenshot shows it.** My per-line keywords file was refused ("provide a comma-separated list"); I had flagged it as unseen and still shipped it. Say what is unseen AND make the file adaptable.
* **A guide beats my search and my memory, and a portal screenshot beats the guide.** I invented neither the Attributed Revenue opt-in nor an API; I named the mismatch instead.
* **Ask where a claimed requirement is written before building to it.** I accepted "the FTR needs the E2E test" and built a test offer; the prerequisites page and guide do not say so. Cheap here, but it was effort spent on an unverified premise.
* **For paste-into-form text: raw GitHub URL, or a text editor (TextEdit via Finder), never a Markdown previewer.** Per-field `.txt` files in `aws_marketplace/portal_fields/` are the pattern.
