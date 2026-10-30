# LOG_CURRENT: recent session records

<!-- NEW SESSION RECORDS ARE APPENDED HERE, NEVER TO CLAUDE.md. Newest last. The last
     'WHERE ... LEFT THINGS' section supersedes the ones above it. When this passes
     90,000 characters run: python3 tools/claude_memory.py --rotate --write -->

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

## 2026-10-27: WAFR/FTR GAP WORK STARTED. THE FTR GATE IS ZERO HIGH RISKS IN SEC, OPS AND REL ONLY (SECONDARY SOURCE). TESTS NOW RUN IN CI.

* **Required to clear all 37 High? Probably not.** Search summaries of AWS's Partner Central "Request FTR" page: WAFR report under a year old, zero HRIs in Security, Operational Excellence and Reliability, solution named
  in the workload, reviewer named, PDF under 3 MB; resubmittable. Perf/Cost/Sustainability do not gate. **UNVERIFIED against the guide itself (docs.aws.amazon.com is egress-blocked, WebFetch ENOTFOUND).** Andrew should confirm in Partner Central.
* **Not known:** the per-pillar split of the 37 High / 15 Medium. Andrew reads OPS/SEC/REL High counts from the WAT Overview.
* **Built:** `.github/workflows/tests.yml` + `tools/run_test_suite.py` + `tests_known_failing.txt` (13 files, may only shrink) + `tests_requirements.txt`. 104 files: 91 pass, 13 known-failing, measured with pytest, boto3, pyyaml, requests,
  cryptography on Python 3.13. Different dependency sets give different baselines (boto3 absent turns 3 more red; cryptography absent turns 6 more red). Mutation-tested locally; **never run on GitHub yet**.
* Plan and gap table: `wafr_ftr_gap_plan_2026-10-27.md`. NEXT: reserved concurrency, API alarm, log-retention tools (dry-run default, Stubber-checked); then IAM role split in stages.

## 2026-10-28: PER-PILLAR WAFR COUNTS READ FROM ANDREW'S CHART. IF THE THREE-PILLAR RULE HOLDS, THE TARGET IS 24 HIGH RISKS, NOT 37.
OPS 5H/5M, SEC 9H/1M, REL 10H/2M, PERF 4H/1M, COST 9H/0M, SUS 0H/6M (37 H / 15 M). Gate pillars (OPS+SEC+REL) = 24 High. The rule itself is still unconfirmed against AWS's page. Recorded in `wafr_ftr_gap_plan_2026-10-27.md` section 2.

## 2026-10-28 (rule CONFIRMED): THE FTR WAFR GATE IS ZERO HRIs IN SEC, OPS, REL. READ FROM AWS'S PAGE BY ANDREW.
Five requirements: report under 1 year old; zero HRIs in Security, Operational Excellence, Reliability; solution named in workload name or description; reviewer's full name and email in the reviewer owner field; done in the Well-Architected Tool.
Target is 24 High (5 OPS, 9 SEC, 10 REL). The earlier "UNVERIFIED" on the pillar rule is closed. Still unchecked: workload name/description names the solution; reviewer owner field is filled.

## 2026-10-28 (build): `tools/wafr_hardening.py` WRITTEN AND TESTED, NOT RUN AGAINST AWS. REL 1/6/7/10.
Steps `concurrency`, `alarm`, `retention`; dry run default; spec `tools/wafr_hardening_spec.json` (api 100, bundle-fulfillment 10, stripe-webhook 10 reserved; those numbers are MY PROPOSAL, not measured). `test_wafr_hardening.py` 13 tests: fakes for decisions,
botocore Stubber over the real service models for request/response shapes, six planted bugs all caught. Retention DELETES events older than 90 days on groups that had none; the dry run lists size and age first. The alarm step copies the AlarmActions
of the existing Lambda Errors alarms (found by reading them) and blocks if there are none. NEXT: Andrew runs the dry run, reads it, then `--apply` per step. After apply, REL 1/7/10 Notes and ticks can change (reserved concurrency exists; alarm exists), with evidence = the tool's output.

## 2026-10-29: CORRECTION. THE WAFR SECURITY HIGH-RISK LIST WAS SAVED (ON AN UNMERGED BRANCH). I WRONGLY REPEATED "NEVER SAVED". THE OPS HIGH-RISK LIST WAS NEVER READ.

The gap plan (section 5) and the 2026-10-28 handoff said the OPS and SEC answers "were given in chat and never saved". That was inherited and unchecked. Found by `git fetch --all --prune` then `git log --all -S` with no pathspec:
* **SEC high-risk list: SAVED** in commit `77ec256` on `origin/claude/kind-fermi-2y6dhb` (never merged to main), section "2026-10-27 (WAFR SECURITY HIGH-RISK LIST ...)". Copied below verbatim.
* **OPS high-risk list: NEVER READ.** That same commit says "Operational Excellence and Reliability high-risk lists NOT yet read". Only the COUNT (5 High) was ever recorded. Andrew has not been asked for it in a way that reached a saved record; it needs the console filter Operational Excellence + High risk.
* **The 2026-10-10 per-question OPS 1-11 / SEC 1-11 ANSWER TEXTS** (archive_08.md ~L520) really were chat-only. That is a different thing from the HRI lists.
* The dashboard unit is a best practice not met (36 rows in SEC); the FTR gate counts HIGH-RISK QUESTIONS (9 SEC). A question stops being High when enough of its practices are genuinely met, not when one is.

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

## WHERE 2026-10-29 LEFT THINGS. WAFR/FTR THREAD: 24 HIGH RISKS TO CLEAR. DECISION: NO GUARDDUTY, WAF DEFERRED. READ THIS FIRST FOR THE WAFR THREAD.

**Supersedes the WAFR parts of every earlier "WHERE ... LEFT THINGS" list, including the 2026-10-28 one (commit `755dc6f` on `origin/claude/laughing-meitner-m54bli`, not on this branch).** Branches holding WAFR facts that are NOT merged together: `claude/kind-fermi-2y6dhb` (SEC list), `claude/laughing-meitner-m54bli` (2026-10-28 handoff, hardening tool notes). Before claiming any WAFR fact is missing: `git fetch --all --prune && git log --all --oneline -S "<string>"`, no pathspec. Merge with `tools/resolve_md_conflict.py docs/claude_memory/LOG_CURRENT.md --write`.

### The gate, CONFIRMED from AWS's page (Andrew, 2026-10-28)
Zero High-risk issues in Security, Operational Excellence and Reliability; report under 1 year old; workload name/description names the solution (saved); reviewer owner field "Andrew Gibbs - andrew@relayshield.net" (saved). Perf, Cost, Sustainability do not gate.

### Counts, from Andrew's dashboard screenshot 2026-10-29 (the chart, unchanged since 10-28)
| Pillar | High | Medium | Gates |
|---|---|---|---|
| Operational Excellence | 5 | 5 | yes |
| Security | 9 | 1 | yes |
| Reliability | 10 | 2 | yes |
| Performance Efficiency | 4 | 1 | no |
| Cost Optimization | 9 | 0 | no |
| Sustainability | 0 | 6 | no |
The chart counts HIGH-RISK QUESTIONS. The Security "issues by improvement plan item" table counts unmet PRACTICES (36 in Security). A question leaves High only when enough of its practices are genuinely met.

### Which High items are KNOWN and which are NOT
* **SEC (9 questions, 36 practices): KNOWN**, recorded verbatim in the section "2026-10-29: CORRECTION" above. High questions are SEC1, 2, 3, 5, 6, 7, 8, 10, 11. SEC4 and SEC9 are not High.
* **OPS (5 High): the questions are NOT KNOWN.** Never read. Andrew filters the dashboard "issues by improvement plan item" table to Operational Excellence + High risk and pastes the rows. **Save them here the moment they arrive.**
* **REL (10 High of 13 questions): WHICH 10 is NOT KNOWN.** The answers are in `wafr_answers_reliability_2026-10-11.md` but the Tool's High/Medium result per question was never recorded. Same filter, Reliability + High risk.
* The 2026-10-10 answer TEXTS for OPS 1-11 and SEC 1-11 were chat-only and are lost; they are not needed, the High lists are.

### DECISIONS, 2026-10-29, Andrew's, do not re-open without new evidence
* **NO GuardDuty now or near-term.** It closes no High question on its own: detection is SEC4, which is not High. Its only links are SEC1 "evaluate new security services" and weakly SEC6 "automate compute protection".
* **WAF is DEFERRED, not rejected.** It could move SEC5 (network protection) from High to Medium at best, and only if "Create network layers" can honestly be ticked as not applicable (no VPC). Weak justification for about $10-12 per month plus $0.60 per million requests (UNVERIFIED: aws.amazon.com is egress-blocked, prices came from search summaries). Reopen only if SEC5 is the last High left, or after the FTR.
* The Security count is driven by WRITTEN PLANS (SEC10 incident response, SEC11 application security, SEC7 data classification, SEC1 threat model and root user) and the one-role-per-Lambda IAM split (SEC3), not by paid services.

### Built, not yet applied to AWS
* `tools/wafr_hardening.py` (REL 1/6/7/10): dry run on Andrew's Mac was clean 2026-10-28; nothing applied. Reserved concurrency values (api 100, fulfillment 10, stripe 10) are my proposal, unmeasured. Apply order: `--step concurrency`, then `--step alarm` (READ the `notifies:` line first), then `--step retention`, each with `AWS_PROFILE=relayshield` and `--apply`.
* `.github/workflows/tests.yml`: has never run on GitHub (main not pushed).

### TODO, IN ORDER
1. Andrew pastes the OPS High rows and the REL High rows. Claude saves them in this file the same turn.
2. Claude builds, dry-run-default, with botocore Stubber checks: Lambda versions plus alias deploy change, AWS Backup plan, DLQs, tracing, API Gateway throttling and access logging, tag script, weekly-metrics CI deploy path (needs an IAM grant first). Claude drafts the written plans (incident response, forensics, playbooks, data classification, threat model, secure-development, DR and test plans) from the repo, marked draft until Andrew adopts them.
3. Andrew runs, in stages: the REL hardening tool; `tools/protect_dynamodb_tables.sh` (PITR, run status unknown); IAM snapshot then `iam_split_roles.py` per function.
4. Re-tick in the WA Tool WITH EVIDENCE only; save a milestone; PDF under 3 MB; request validation.
5. Dave Shapiro is contacted only after the FTR passes.

## 2026-10-29: OPS AND REL HIGH-RISK LISTS, READ FROM ANDREW'S SCREENSHOTS OF THE DASHBOARD TABLE "issues by improvement plan item" (filter pillar + High risk). VERBATIM. ALL THREE LISTS NOW COMPLETE (SEC 36, OPS 11, REL 37 practices).

**These are unmet PRACTICES, not questions.** OPS: 5 High questions, 11 practices (2 pages, complete). REL: 10 High questions, 37 practices over 4 pages, ALL CAPTURED. SEC list is in the section "2026-10-29: CORRECTION" above (36 practices, complete).

**OPS, 11 High practices (complete):** Evaluate internal customer needs; Mechanisms exist to manage responsibilities and ownership; Mechanisms exist to request additions, changes, and exceptions; Responsibilities between teams are predefined or negotiated; Escalation is encouraged; Communications are timely, clear, and actionable; Team members are encouraged to maintain and grow their skill sets; Resource teams appropriately; Implement distributed tracing; Ensure personnel capability; Create support plans for production workloads.

**REL, page 1:** Manage service quotas across accounts and Regions; Accommodate fixed service quotas and constraints through architecture; Monitor and manage quotas; Automate quota management; Ensure that a sufficient gap exists between the current quotas and the maximum usage to accommodate failover; Provision redundant connectivity between private networks in the cloud and on-premises environments; Ensure IP subnet allocation accounts for expansion and availability; Prefer hub-and-spoke topologies over many-to-many mesh; Enforce non-overlapping private IP address ranges in all private address spaces where they are connected; Implement loosely coupled dependencies.
**REL, page 2:** Do constant work; Control and limit retry calls; Fail fast and limit queues; Define and calculate metrics (Aggregation); Send notifications (Real-time processing and alarming); Automate responses (Real-time processing and alarming); Analyze logs; Monitor end-to-end tracing of requests through your system; Integrate functional testing as part of your deployment; Integrate resiliency testing as part of your deployment.
**REL, page 3:** Deploy using immutable infrastructure; Use bulkhead architectures to limit scope of impact; Automate recovery for components constrained to a single location; Monitor all components of the workload to detect failures; Fail over to healthy resources; Rely on the data plane and not the control plane during recovery; Use static stability to prevent bimodal behavior; Send notifications when events impact availability; Architect your product to meet availability targets and uptime service level agreements (SLAs); Test scalability and performance requirements.
**REL, page 4 (received 2026-10-29, the last page; REL total is 37 practices):** Test resiliency using chaos engineering; Conduct game days regularly; Define recovery objectives for downtime and data loss; Use defined recovery strategies to meet the recovery objectives; Test disaster recovery implementation to validate the implementation; Manage configuration drift at the DR site or Region; Automate recovery.

**Observations, mine, not yet acted on:** (1) REL network practices (private connectivity, subnets, hub-and-spoke, non-overlapping ranges) assume a VPC; this workload has none, so the WA Tool's "question does not apply to this workload" with a Note may be the honest answer, Andrew's call. (2) "Implement distributed tracing" (OPS) and "Monitor end-to-end tracing" (REL) are ONE control: X-Ray active tracing on Lambda and API Gateway. (3) "Create support plans for production workloads" is a paid AWS Support plan, a spend decision for Andrew; price UNVERIFIED. (4) Several OPS practices are team-and-people practices on a one-person company; tick only what is true, otherwise write the gap or document the single-owner model.

## WHERE 2026-10-29 (BUILD SESSION) LEFT THINGS. WAFR/FTR: CONTROLS BUILT, TESTED AND PUSHED TO `claude/sharp-bohr-72o23p`. NOT MERGED. NOTHING APPLIED TO AWS. READ THIS FIRST.

**Supersedes the "WHERE 2026-10-29 LEFT THINGS" section above for the TODO order** (that one is the pre-build state; its decisions still stand). The branch is pushed; "deployed" would be false: Claude has no AWS credentials, and workflow dispatch is 403 for Claude. Every AWS-touching tool below was checked against the REAL boto3 service models with botocore Stubber and by planting bugs; none has run against AWS.

### Built this session (all on `claude/sharp-bohr-72o23p`)
| What | Files | Evidence it works, and what is NOT proven |
|---|---|---|
| **Observability tool**: X-Ray tracing on 4 Lambdas and the API stage, stage default throttle, CloudWatch dashboard plus 5 saved Logs Insights queries, account-concurrency quota alarm | `tools/wafr_observability.py`, `tools/wafr_observability_spec.json`, `test_wafr_observability.py` (31 tests) | Stubber over lambda, iam, apigateway, cloudwatch, logs, service-quotas models; 11 planted bugs all caught. **NOT proven:** that AWS accepts the dashboard body (the tool prints AWS's validation messages and exits 1 if any), that `update_stage` `replace` creates a missing throttle setting, that the profile may call `iam:SimulatePrincipalPolicy`. Throttle 100 rps / burst 200 is MY PROPOSAL |
| **Deploy test gate**: `deploy_lambdas.yml` now `needs: tests` (calls `tests.yml`); a manual run bypasses it and prints a notice | `.github/workflows/deploy_lambdas.yml`, `.github/workflows/tests.yml` (`workflow_call`) | `test_deploy_versions.py` parses it and 8 planted bugs are caught. **NOT proven:** `tests.yml` has NEVER run on GitHub. If it is red for an environment reason, every push deploy is blocked until fixed (use manual dispatch meanwhile) |
| **Version + alias publishing** after the import probe, never fails the deploy, warns loudly | same workflow; `iam_github_deploy_versions.json`; `tools/apply_deploy_versions_policy.sh` | The step's script was run against a stubbed `aws` in all three modes (ok, no alias yet, denied). **The deploy role does NOT yet have the permissions**; until the policy script runs, deploys succeed and print a "Versioning incomplete" warning. **The `live` alias is NOT what serves traffic**: API Gateway still invokes the unqualified function |
| **Rollback workflow** (restores a version's CODE, probes, moves the alias) | `.github/workflows/rollback_lambda.yml` | Target-selection script run against a stub for previous / number / unpublished / garbage / injection input. Never run on GitHub; needs at least 2 published versions |
| **Four DRAFT documents**, none adopted | `docs/reliability/recovery_objectives_and_dr_plan.md`, `game_day_plan.md`, `availability_target_and_load_test_plan.md`, `docs/ops/operating_model.md` | Written from repo facts. RTO/RPO, 99.5% target, and the load-test profile are PROPOSALS. Each has CONFIRM items only Andrew can answer. Nothing is a test result |
| **Practice-to-evidence map** | `wafr_practice_map_2026-10-29.md` | Every OPS (11) and REL (37) High practice with its backing and status. The re-tick checklist |

### Verified merge procedure (run in a clean copy, 2026-10-29)
origin/main is BEHIND Andrew's local main (his holds `755dc6f`, the 10-28 handoff, unpushed). Merging this branch conflicts ONLY in `docs/claude_memory/LOG_CURRENT.md` (an append conflict); `tools/resolve_md_conflict.py` keeps both sides; the index regenerates; `--rotate --write` then brings the log from 113,656 to 59,031 characters. **Do NOT merge `claude/kind-fermi-2y6dhb`**: its useful content (the SEC list) is already copied into this log, and its log rotation conflicts. Its unique commits are otherwise Bundle D / handoff records already represented here.

### TODO, IN ORDER
1. **ANDREW: merge this branch** (block below), run `python3 test_workflows_parse.py`, push `main`. First push to main is the first real run of `tests.yml` and the deploy gate. Expect green with 13 known failures; if red for an environment reason, fix that before anything else.
2. **ANDREW: dry runs, read them, then apply one step at a time.** `tools/wafr_hardening.py` (concurrency, alarm: READ the `notifies:` line, retention) then `tools/wafr_observability.py` (tracing, throttle, dashboard, quota). Python is `~/.rsvenv/bin/python` (needs boto3). Tracing may print BLOCKED if the shared role already has 10 managed policies: then the IAM role split (`iam_role_split.md`) is the prerequisite, not a failure of the tool.
3. **ANDREW: `sh tools/apply_deploy_versions_policy.sh`**, then trigger one deploy and check the "Publish a version" step reads ✅ and not a warning. Then `AWS_PROFILE=relayshield sh tools/protect_dynamodb_tables.sh` (dry run first; its run status is unknown).
4. **ANDREW decides:** buy an AWS Support plan (search summary: Business Support+ from $29/month; UNVERIFIED; older plans end 2027-01-01); throttle 100/200; reserved concurrency 100/10/10; whether the WA Tool's REL 2 was answered "none of these" instead of "question does not apply" (no VPC), which alone could take 4 practices off the list.
5. **ANDREW: read the four DRAFT documents, answer the CONFIRM items, replace each STATUS line with "ADOPTED <date>" or edit.** A document that is not adopted is not evidence.
6. **CLAUDE, next build:** async retry limits and DLQs (`MaximumRetryAttempts`, `MaximumEventAge`, needs an SQS grant: the shared role's inline budget is full, so a customer-managed policy or the role split), AWS Backup plan (needs a service role), DynamoDB and EventBridge alarms, API integration through the `live` alias (needs `lambda:InvokeFunction` permission on the alias for API Gateway), Service Quotas automatic management (not investigated).
7. **SECURITY (9 High questions, 36 practices) is untouched this session.** Check whether `relayshield_incident_response_plan.md` (v1.0, May 2026, owner Andrew) already supports SEC10 before drafting a new one; it may need a forensics section and a test record rather than a rewrite. Then written plans (threat model, data classification, secure-development, emergency access), the IAM split (SEC3), root user MFA and key check (SEC1).
8. **Hold game day 1** (PITR restore and bulkhead test) once steps 2 and 3 are done. It converts four DRAFT rows into evidence.
9. **Only then re-tick in the WA Tool, with evidence cited in each Note**, save a milestone, PDF under 3 MB, request validation. Dave Shapiro only after the FTR passes.

### ANDREW RUNS THIS: the merge (every line verified in a clean copy; the push is not)
```zsh
cd ~/dev/relayshield
git checkout main
git --no-pager fetch origin claude/sharp-bohr-72o23p
git stash push --include-untracked -m "pre-merge untracked"
git -c pull.rebase=false merge --no-edit FETCH_HEAD
```
EXPECT: "CONFLICT (content): Merge conflict in docs/claude_memory/LOG_CURRENT.md" and no other conflict. (If it merges cleanly, skip the next block.)
STOP IF: a conflict in any `.py`, `.yml` or `.json`: another session edited the same code; send the `git status` output.

Only if it conflicted, then:
```zsh
cd ~/dev/relayshield
python3 tools/resolve_md_conflict.py docs/claude_memory/LOG_CURRENT.md --write
python3 tools/claude_memory.py --index --write
git add docs/claude_memory
git commit --no-edit
python3 tools/claude_memory.py --rotate --write
python3 tools/claude_memory.py --index --write
git add docs/claude_memory
git commit -m "Rotate LOG_CURRENT after merge"
python3 test_workflows_parse.py
```
EXPECT: "All 26 workflows parse and define jobs." (verified on this branch 2026-10-29) and `claude_memory.py --check` reporting both files under their caps.
STOP IF: "unresolved" markers remain (`grep -c '^<<<<<<<' docs/claude_memory/LOG_CURRENT.md` must print 0).

### Standing lessons from this session
* **A record on an unmerged branch is invisible to the next session.** The SEC list sat on `kind-fermi` for two days and a session reported it "never saved". Fix at the source: a session that writes a record must say which branch holds it, and the handoff must name unmerged branches (this one does, above).
* **Ask for the console list in the first reply, not the third.** The OPS and REL High lists were never read until Andrew was asked a pointed question. The ask costs him ten minutes and unblocks all the mapping.
* **A paid control that closes zero High questions is not a control worth buying.** GuardDuty was ruled out on that basis (decision above); apply the same test to every purchase this thread proposes, the support plan included.
* **Building the control is not closing the finding.** 48 practices are mapped; none is ticked; most are UNRUN or DRAFT. The `wafr_practice_map_2026-10-29.md` statuses are the honest count.

## 2026-10-29 (merge + rotate session): `claude/sharp-bohr-72o23p` MERGED INTO `claude/happy-ptolemy-ygtv0n`, LOG ROTATED. NOT ON `main`. NOTHING APPLIED TO AWS.

The WAFR/FTR build branch merged with NO conflict (main had already absorbed the 10-28 handoff). `--rotate --write` took LOG_CURRENT from 118,349 to about 60,000 characters (new `archive_10.md`); `--check`, `test_claude_md_size.py` and `test_workflows_parse.py` pass. The TODO order in "WHERE 2026-10-29 (BUILD SESSION) LEFT THINGS" stands unchanged. The count: the FTR gate is 24 High-risk QUESTIONS (OPS 5, SEC 9, REL 10); the practice lists behind them are OPS 11, SEC 36, REL 37 = 84 unmet practices. The branch addresses OPS and REL only (SEC untouched), and every control is UNRUN against AWS.

## 2026-10-29 (WA Tool, Andrew's console): REL 2 MARKED "QUESTION DOES NOT APPLY". RELIABILITY HIGH 10 -> 9. GATE TOTAL NOW 23 (OPS 5, SEC 9, REL 9).

Done by Andrew in the console, reason "Out of scope" with the no-VPC Notes (no Lambda is VPC-attached, evidence script 2026-10-11; only network surface is the API Gateway regional endpoint). Reliability pillar overview after saving, from his screenshot: 13/13 answered, High 9, Medium 2, No improvements identified 1, Not Applicable 1, Unanswered 0. **This proves the Tool recalculates the pillar count on save, and that a "does not apply" answer removes the question from the High count.** It was legitimate only because REL 2's four unmet practices all assume a VPC and there is none; it is not a route for any question whose practices apply (SEC5 was considered on 2026-10-29 and the decision to defer stands, because the public API Gateway endpoint is a network surface). REL 2 is no longer on the re-tick list. The per-question table of what to tick and after which step was given in chat this session and matches `wafr_practice_map_2026-10-29.md`; REL 4 and REL 5 have no controls built yet and cannot clear.

## 2026-10-29 (build, REL 5): `tools/wafr_async_failures.py` WRITTEN AND TESTED. NOT RUN AGAINST AWS. REL 4 STILL HAS NOTHING BUILT.

Backs REL 5 "Control and limit retry calls" and "Fail fast and limit queues". Four steps, dry run by default, spec `tools/wafr_async_spec.json`: **queue** (one SQS standard queue `relayshield-async-failures`, SSE-SQS, 14 days), **access** (each execution role must be allowed `sqs:SendMessage` on that one queue, checked with the IAM simulator; if not, ONE customer-managed policy `relayshield-async-failures-send` is created and attached, only where the role has room under the 10-managed-policy limit, else BLOCKED), **retry** (Lambda async invoke config: retries 1, max event age 3600 s, queue as on-failure destination, on every function that is the Lambda target of an ENABLED EventBridge rule, discovered from AWS), **alarm** (queue not empty, notifies the same targets the existing Lambda error alarms use). Retries 1 and age 3600 are MY PROPOSAL, unmeasured; Lambda's own limits are 0 to 2 and 60 to 21600 and the tool refuses anything outside them.

**Safety decisions, each with a test that fails if reversed:** `put_function_event_invoke_config` REPLACES a whole config (including an OnSuccess destination), so it is called only where none exists and a different existing config is reported as CONFLICT and kept. A destination is never set for a role that cannot write to it (a silent drop is worse than no destination). Access is granted BEFORE the destination is set, and a permission-shaped refusal from Lambda is retried for about a minute for IAM propagation. A function called by something other than EventBridge (S3, SNS) is not discovered; list it under `async.extra_functions`. The public API is invoked synchronously and has no async config.

**Evidence, and its limits.** 39 tests: fakes for the decisions plus botocore Stubber over the REAL lambda, iam, sqs, events and cloudwatch models (boto3 1.43.121). 12 planted bugs (disabled rules included, put over an existing config, destination set for a role that cannot send, attach before create, unencrypted queue, over-broad action, no-room check removed, alias dropped, alarm with nobody to tell, wrong account, propagation retry removed, conflict overwritten) each turned the suite red; one real bug was found by the tests first (sorting a function seen with and without an alias). **NOT proven:** that Lambda accepts the destination the instant the policy is attached (hence the retry), that the simulator answers for the shared role, and the real SQS error code for a missing queue (older botocore says `AWS.SimpleQueueService.NonExistentQueue`, 1.43 says `QueueDoesNotExist`; both are handled and both are tested). Full suite with the CI dependency set: no new failures; `test_claude_md_size.py` now passes (the rotation fixed it) so its line was removed from `tests_known_failing.txt`, which is the ratchet working.

**Needs a managed-policy slot on the shared role, like the X-Ray policy in `wafr_observability.py --step tracing`.** If the shared role already has 10, BOTH are blocked and the IAM role split (`iam_role_split.md`) is the prerequisite for REL 5 and for tracing. The dry run says which.

**Next, in order.** (1) Andrew merges PR 54, then runs the dry run of this tool and reads it. (2) Apply `--step queue`, then `--step access` (read the policy line), then `--step retry`, then `--step alarm`. (3) After apply, REL 5 "Control and limit retry calls" may be ticked citing the tool output; "Fail fast and limit queues" is PARTIAL (client timeouts not assessed), so tick it only if the Note says what is and is not covered. (4) REL 4 (loosely coupled dependencies, constant work) still has NOTHING built; "Do constant work" may honestly be a review-and-Note item for scheduled polling, "Implement loosely coupled dependencies" needs a real change (e.g. the Stripe webhook or fulfillment path via a queue) and is a design decision for Andrew. The practice map is updated for REL 2 (N/A in the Tool), REL 5 and the REL 6 notifications row.

## 2026-10-29 (build, REL 4): STRIPE WEBHOOK QUEUE MODE + `tools/wafr_stripe_queue.py`. CODE WRITTEN AND TESTED, FLAG OFF, NOTHING APPLIED TO AWS. ANDREW APPROVED THE DESIGN IN CHAT.

Andrew said: "Rel4: Im ok to put Stripe webhook behind a queue." Design, chosen to keep the payment path safe: **the same function does both jobs.** `relayshield_stripe_webhook.py` gained a queue mode that is OFF unless the Lambda env var `STRIPE_EVENT_QUEUE_URL` is set. On HTTP it still verifies the Stripe signature (the 5-minute tolerance only makes sense at the door), and for a `checkout.session.completed` it puts the event on the queue and returns 200; other event types are acknowledged without queueing; an enqueue failure returns **500 so Stripe retries for up to three days and nothing is processed inline** (an inline second attempt could onboard the customer twice). Invoked by SQS (`event["Records"]`, which API Gateway cannot produce because it fixes the top-level keys), it processes the event through `process_checkout_event`, the old handler body MOVED, not rewritten. The consumer accepts only `aws:sqs` records whose ARN ends `:relayshield-stripe-events`, does not re-check the signature age, and RAISES on any failure so SQS retries and then redrives to the DLQ (returning normally deletes the message). Deploying this code changes nothing by itself: flag off is the old behaviour.

**The webhook had NO tests before this.** `test_stripe_webhook_queue_mode.py` first pinned today's behaviour (15 tests, run against the UNCHANGED handler and passing), then added queue mode (16 tests that failed before the change, pass after). `test_day3.py` still passes with a region set on both the original and the new handler.

**Infra tool `tools/wafr_stripe_queue.py`** (spec `tools/wafr_stripe_queue_spec.json`), dry run by default. Default run = `queues` (DLQ first, then the main queue, SSE-SQS, 14 days, redrive after 5 receives, visibility timeout = 6 x the function's own timeout read from the function), `access` (one customer-managed policy, four sqs actions on the one queue, attached only if the role has room), `consumer` (SQS event source mapping, batch size 1, max concurrency 2). **`enable` and `disable` are separate steps, never in the default run.** `enable` MERGES the flag into the existing Lambda environment (`update_function_configuration` replaces the whole Environment, which would delete `DAY3_LAMBDA_ARN` and `DAY3_SCHEDULER_ROLE_ARN`) and refuses unless the consumer mapping is enabled, the role can use the queue, and the DEPLOYED code (downloaded from Lambda, not read from git) contains queue mode. `disable` removes only its own variable and the consumer keeps draining.

**Evidence and limits.** 48 tests for the tool (fakes for decisions, Stubber over the real lambda, iam and sqs models; the real model rejected a made-up UUID in my own test data, which is the kind of thing it is there for) plus 31 for the handler. 22 planted bugs (14 in the tool, 8 in the handler: wrong create order, environment replaced, code check skipped, consumer check skipped, disable removes everything, default run includes enable, one allowed action enough, conflict overwritten, mapping for a role that cannot use the queue, visibility ignores the multiplier, unreadable environment overwritten, wrong account, no-room check removed, marker in a non-py file; consumer swallows a 500, any queue accepted, enqueue failure answers 200, flag ignored, queues AND processes inline, any event source accepted, signature check removed, non-checkout events queued) each turned its suite red. Full suite with the CI dependency set: no new failures. **NOT proven:** that SQS delivers the documented record shape to this function (fields used: eventSource, eventSourceARN, body), that Lambda accepts the mapping the instant the policy is attached (the tool retries a permission-shaped refusal for about a minute), that the simulator answers for this role, and that the presigned code URL downloads.

**ORDER MATTERS, and the enable step enforces it:** (1) merge, let `deploy_lambdas.yml` deploy the new handler (flag off, behaviour unchanged); (2) dry run then `--apply` of the default steps; (3) only then `--step enable --apply`; (4) watch one real checkout go through; (5) to go back, `--step disable --apply`. Needs ANOTHER managed-policy slot on the shared role if the stripe-webhook role is the shared one (X-Ray, the async-failures policy and this one are three): if the role is full, the IAM role split is the prerequisite for all of them.

**FOUND, NOT FIXED (separate task queued): `relayshield_stripe_webhook.py` Telegram flow uses `subscription_tier` before it is defined** (`resolved_tier = pre_payment.get("subscription_tier") or subscription_tier`; pyflakes reports it, and it is identical on the original). A Telegram checkout whose pre-payment record has no tier raises NameError and Stripe retries forever. **ALSO PRE-EXISTING, same family:** processing is not atomic (user record created, then a 500 on Twilio credentials; the retry finds the user and skips, so the welcome message is never sent). A queue with redrive does not make that worse and does not fix it.

**REL 4 status:** "Implement loosely coupled dependencies" can be ticked only after `--step enable` has run and a checkout has been seen going through, and the Note must say only the Stripe webhook is decoupled. "Do constant work" is a review-and-Note item (scheduled polling is constant by design). The Tool decides whether the question leaves High.

## WHERE 2026-10-29/30 (WAFR BUILD SESSION 2) LEFT THINGS. PR 54 OPEN, CI GREEN, NOT MERGED. NOTHING APPLIED TO AWS. READ THIS FIRST FOR THE WAFR THREAD.

**Supersedes the TODO order in "WHERE 2026-10-29 (BUILD SESSION) LEFT THINGS" and the 2026-10-29 count.** Written at Andrew's request before he rebooted his Mac. Everything below is pushed; nothing lives only on his machine or in the container.

### State
* **[PR 54](https://github.com/nzdsf2-gif/relayshield/pull/54)** `claude/happy-ptolemy-ygtv0n` into `main`, head `67f2301` plus the commit carrying this section. CI was green at `67f2301` (Run test suite, Run Security Checks, GitGuardian), mergeable clean, no reviews. **Andrew merges it on 2026-10-30.** It carries: the whole `claude/sharp-bohr-72o23p` WAFR build branch (merged with no conflict), the log rotation (`archive_10.md`), `tools/wafr_async_failures.py` (REL 5), the Stripe webhook queue mode and `tools/wafr_stripe_queue.py` (REL 4), the updated practice map, and one line removed from `tests_known_failing.txt` (`test_claude_md_size.py` passes now).
* **Merging PR 54 DEPLOYS `relayshield_stripe_webhook.py` to production** (the flag `STRIPE_EVENT_QUEUE_URL` is unset, so behaviour is identical; 15 pinned tests back that) and is the **first real run of the deploy test gate** (`deploy_lambdas.yml` needs `tests.yml`). `tests.yml` itself already ran green on the PR. If the first push deploy is red for an environment reason, use a manual dispatch meanwhile and fix that before anything else.
* **Gate count: 23 High questions (OPS 5, SEC 9, REL 9).** Andrew marked REL 2 "Question does not apply" in the Tool (reason Out of scope, no-VPC Notes), screenshot: Reliability High 9, Medium 2, No improvements identified 1, Not Applicable 1, Unanswered 0, 13/13 answered. **That proved the Tool recalculates on save.**
* **On Andrew's Mac:** he ran the merge block BEFORE PR 54 was merged, so `main` had nothing new and `tools/wafr_async_failures.py` was "No such file". His `git stash push --include-untracked` DID save something as "pre-merge untracked" (the output also said "Ignoring path developers-agent-toolkit/" and "gemini-relayshield-scam-checker/", which are nested repos git cannot stash). `git stash list` shows it; `git stash pop` restores it if it was his own work. Unknown content.
* **Queued, not started:** a suggested task card "Fix undefined subscription_tier in Stripe Telegram flow" (a latent NameError in `relayshield_stripe_webhook.py`, present on the original; Andrew has not started it).

### ANDREW RUNS THIS after merging PR 54 (dry run only, writes nothing; UNVERIFIED against AWS)
```zsh
cd ~/dev/relayshield
git checkout main
git stash push --include-untracked -m "pre-merge untracked"
git -c pull.rebase=false pull --no-edit origin main
AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/wafr_async_failures.py
```
EXPECT: `N asynchronously invoked function(s) found from ENABLED EventBridge rules`, sections `== queue`, `== access`, `== retry`, `== alarm`, ending `Dry run only.` STOP IF: file missing (PR not merged); a `BLOCKED` line saying "role split" (the shared role has 10 managed policies: X-Ray, the async-failures policy and the Stripe queue policy all need a slot, so `iam_role_split.md` is the prerequisite); a conflict in `LOG_CURRENT.md` (`python3 tools/resolve_md_conflict.py docs/claude_memory/LOG_CURRENT.md --write`).

### TODO, IN ORDER
1. **ANDREW:** merge PR 54; watch the first `deploy_lambdas.yml` run on `main`; run the block above and send the output.
2. **ANDREW, each as a dry run first, read it, then one `--apply` at a time (all `AWS_PROFILE=relayshield ~/.rsvenv/bin/python`):** `tools/wafr_hardening.py` (`--step concurrency`, then `--step alarm`, READ the `notifies:` line, then `--step retention`), `tools/wafr_observability.py` (tracing, throttle, dashboard, quota; tracing may print BLOCKED if the role has 10 managed policies), `sh tools/apply_deploy_versions_policy.sh` then one deploy and check "Publish a version" reads ✅, `AWS_PROFILE=relayshield sh tools/protect_dynamodb_tables.sh` (run status unknown), then `tools/wafr_async_failures.py` (`--step queue`, `access`, `retry`, `alarm`).
3. **ANDREW, Stripe queue (REL 4), strictly in this order:** (a) the deploy of PR 54 has run; (b) `tools/wafr_stripe_queue.py` dry run, then `--apply` (queues, access, consumer; the flag stays OFF); (c) ONLY THEN `--step enable --apply`, which refuses unless the consumer works and the DEPLOYED code contains queue mode; (d) watch one real checkout go through; (e) rollback is `--step disable --apply`. Do not enable before (a) and (b).
4. **ANDREW decides:** AWS Support plan (search summary: Business Support+ from $29 per month, UNVERIFIED; older plans end 2027-01-01); throttle 100/200; reserved concurrency 100/10/10; async retries 1 and max event age 3600 s (mine, unmeasured); read the four DRAFT documents under `docs/` and mark each ADOPTED or edit it.
5. **CLAUDE, next build:** the 9 SECURITY questions are UNTOUCHED (check whether `relayshield_incident_response_plan.md` v1.0 already supports SEC10 before drafting; then threat model, data classification, secure-development, emergency access, the IAM split for SEC3, root user MFA and key check for SEC1); AWS Backup plan, DynamoDB and EventBridge alarms, API through the `live` alias, Service Quotas automatic management; the REL 4 "Do constant work" Note.
6. **ANDREW re-ticks in the Tool, with evidence cited in each Note, one question at a time (table below), saves a milestone, PDF under 3 MB (unverified), requests validation.** Dave Shapiro only after the FTR passes.

### HOW TO RE-TICK: the exact console path, and the per-question table (this was chat-only until now)
**Path:** `https://console.aws.amazon.com/wellarchitected/` (region where the workload was created; the REL answers file says us-east-1, UNVERIFIED) > Workloads > RelayShield API > Lenses: AWS Well-Architected Framework > Continue reviewing > pillar > question title > Edit > tick only what is TRUE > Notes (evidence) > Save and exit > read the risk badge. If a question is hard to find, the dashboard table "issues by improvement plan item" names the question for each practice. Notes never change the score. Do NOT tick the "do not tick yet" list.

REL question numbers are VERIFIED against `wafr_answers_reliability_2026-10-11.md` and reproduce the counts (REL 1, 2, 4, 5, 6, 8, 10, 11, 12, 13 are the 10 High questions; REL 3, 7, 9 are not). **OPS question numbers are from MEMORY of the lens** (the OPS answers were never saved): match by the practice name shown inside each question.

| Question | Practices to tick (names as in the Tool) | Only after | Cite |
|---|---|---|---|
| OPS 1 | Evaluate internal customer needs | `docs/ops/operating_model.md` section 6 adopted | the adopted doc |
| OPS 2 | Mechanisms exist to manage responsibilities and ownership; Mechanisms exist to request additions, changes, and exceptions; Responsibilities between teams are predefined or negotiated | operating model sections 1 and 2 adopted | the adopted doc |
| OPS 3 | Escalation is encouraged; Communications are timely, clear, and actionable; Team members are encouraged to maintain and grow their skill sets; Resource teams appropriately | operating model sections 3 to 5 adopted; tick only what is true | doc, alarm names |
| OPS 4 | Implement distributed tracing | `wafr_observability.py --step tracing --apply` | tool output |
| OPS 7 | Ensure personnel capability; Create support plans for production workloads | section 5 adopted; a paid Support plan bought | doc; Support plan page |
| REL 1 | Monitor and manage quotas; Accommodate fixed service quotas and constraints through architecture | `wafr_observability.py --step quota --apply` | alarm name |
| REL 2 | DONE 2026-10-29 (does not apply) | | |
| REL 4 | Implement loosely coupled dependencies (Note: ONLY the Stripe webhook is decoupled); Do constant work (a review Note) | Stripe `--step enable` run and one checkout seen through the queue | tool output |
| REL 5 | Control and limit retry calls; Fail fast and limit queues (PARTIAL: client timeouts not assessed, say so) | `wafr_async_failures.py` all four steps applied | tool output |
| REL 6 | Define and calculate metrics; Send notifications; Analyze logs; Monitor end-to-end tracing of requests | `wafr_hardening.py --step alarm` and `wafr_observability.py` (dashboard, tracing) applied | tool output |
| REL 8 | Integrate functional testing as part of your deployment; Deploy using immutable infrastructure | PR 54 merged and deploy green; `apply_deploy_versions_policy.sh` run; one deploy shows "Publish a version" ✅ | run URL |
| REL 10 | Use bulkhead architectures to limit scope of impact | `wafr_hardening.py --step concurrency --apply` | tool output |
| REL 11 | Send notifications when events impact availability; Architect your product to meet availability targets and SLAs | alarms applied; `docs/reliability/availability_target_and_load_test_plan.md` adopted | alarm name, doc |
| REL 12 | Test scalability and performance requirements; Test resiliency using chaos engineering; Conduct game days regularly | load test run and game day 1 held | game day record |
| REL 13 | Define recovery objectives; Use defined recovery strategies; Test disaster recovery implementation; Manage configuration drift at the DR site or Region | DR plan adopted; PITR applied; one restore done | restore record |

**DO NOT TICK YET (nothing built):** REL 1 Automate quota management; REL 6 Automate responses; REL 10 Automate recovery for components constrained to a single location; REL 11 Rely on the data plane and not the control plane during recovery, Use static stability to prevent bimodal behavior; REL 13 Automate recovery. **Realistic outcome, MINE and unverifiable because the Tool's per-question thresholds are not visible:** after everything above is applied, roughly 4 to 8 of the 23 could clear; Security (9) needs its own session.

### STANDING LESSONS FROM THIS SESSION (the first two are now rules in CLAUDE.md, WAFR section, rules 6 and 7)
* "Does not apply" is a real lever but only where every unmet practice assumes something the workload lacks.
* A payment path with no tests gets pinned first and new behaviour ships dark behind a flag, with the switch as its own step.
* **I handed Andrew a block that depended on an unmerged PR and he ran it before merging.** I did say to merge first, but the block itself did not stop him. A block that needs a merge must fail loudly on its own: when the next block depends on a PR, say "STOP: run this only after the PR shows Merged" as its first line, and include `git --no-pager log --oneline -1 -- <file>` so the missing file is self-explaining.
* botocore Stubber rejected my own made-up test data (a 3-character UUID) and a wrong call order; both were test mistakes that the real model caught, which is what it is for. The tool's broad `except Exception` on reads turns a stub mismatch into "blocked", so a Stubber test that fails with "responses remaining" usually means the call order differs from what the tool does (it plans every queue first, then creates).
* Only a CI event whose `head_sha` equals the PR head means the latest commit is green: an event for an older commit arrived while the newer run was still in progress, and checking the check runs directly caught it.
