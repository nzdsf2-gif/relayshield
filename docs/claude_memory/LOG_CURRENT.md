# LOG_CURRENT: recent session records

<!-- NEW SESSION RECORDS ARE APPENDED HERE, NEVER TO CLAUDE.md. Newest last. The last
     'WHERE ... LEFT THINGS' section supersedes the ones above it. When this passes
     90,000 characters run: python3 tools/claude_memory.py --rotate --write -->

## WHERE 2026-10-12 LEFT THINGS. THE WAFR IS ANSWERED AND SAVED, NOT SUBMITTED. READ THIS FIRST.

**State, from Andrew's console, 2026-10-12 end of session.** All 57 Well-Architected questions were worked
(OPS, SEC, REL, PERF, COST, SUS) and he used **Save and exit** with the overview reading **36 High Risks,
15 Medium Risks and ONE question unanswered**. Which question is unanswered is NOT known: find it from each
pillar's question list before anything else. Save and exit locks nothing (UNVERIFIED, from knowledge of the
tool, docs are egress-blocked): the workload stays editable, ticking a practice removes its risk, and a
milestone is only a snapshot. **The order is: fix, then re-tick and re-word Notes, then Save milestone, then
generate the PDF (under 3 MB), then request FTR validation.** A report generated before the fixes carries the
old risks. 36 High is the self-assessment working as designed (every unticked practice is a flagged risk); the
FTR checklist itself is UNREAD, and whether unresolved highs block approval is UNVERIFIED. Read that section
of the FTR Guide in Partner Central before requesting validation.

The answers are in `wafr_answers_reliability_2026-10-11.md` and `wafr_answers_perf_cost_sus_2026-10-12.md`.
The second has a CONDITIONAL table: the budget sentence, the "moved to four-hourly" sentences and the SUS 3
tick are only true after the budget script and the schedule script have been run. Until then they must come
out of the Notes. The Lambda concurrency increase to 1,000 is **PENDING** (AWS case 1791763915000769, an
automated acknowledgement only, "under review"); nothing that depends on it gets ticked until it is approved.

### THE FOUR FINDINGS FROM THE ERROR READS (also in the section above, restated so they are not lost)

1. **The API had a second outage on 10-11 and nothing alarmed.** `relayshield-api`'s 9,171 errors are
   init failures (5,956 `Runtime.UserCodeSyntaxError`, 3,667 `Runtime.ImportModuleError`), spiking on 10-05
   (17,607 error lines, the scamkit slip) and **10-11 (10,777)**, against about 285 a day otherwise. The 10-11
   cause is read as the 01:12 UTC hand-deploy replacing a good package; **which module was missing is still
   unread** (`tools/diagnose_lambda_errors.sh relayshield-api` now prints it, with first and last time and
   failures per hour). The five existing alarms cover other functions; none covers the API.
2. **The gas monitor has failed every run since at least 10-05 on a missing KMS grant, not a code bug.**
   `relayshield-gas-monitor-role` was never allowed to use the customer-managed key on `relayshield_users`.
   `tools/grant_gas_monitor_kms.sh` (dry run by default) fixes it; its proof is the next 15-minute run, not the
   simulation, because the grant is conditioned on `kms:ViaService`. Not yet run.
3. **The ~285 a day error baseline is the badge route** logging `ResourceNotFoundException` every five minutes
   because it reads a DynamoDB table that does not exist. Handled, so not a Lambda error, but it pollutes every
   error count and should be fixed by creating the table or removing the read.
4. **The Twilio credentials are unproven safe.** If Twilio really showed one user with 1,407 calls in an hour,
   our code cannot have made them (Telegram webhook 19 invocations, WhatsApp 22, API Twilio paths zero in the
   week). The check is Twilio Console, Monitor, Usage and the request logs for the source; if not ours, rotate
   the auth token in Twilio and in the secret `relayshield/twilio_auth_token`.

### TWILIO TOP-UP, ASKED 2026-10-12 WITH THE BALANCE UNDER $5

Recommendation given (Andrew decides, it is his money): **top up the $20 minimum, because exposure is bounded
by the balance, and a zero balance silently stops SIM swap and WhatsApp alerts to real customers.** Two
conditions on it: auto-recharge OFF, and check Twilio's usage page for the last 24 hours by source before
leaving it, since a thief spends whatever is in the account. Run the schedule script (4 hours) the same day.

### TODOS FOR THE NEXT SESSION, IN ORDER

1. **Find and answer the one unanswered WAFR question**, then work the 36 High risks cheapest first.
2. **Run, in this order, each dry run read before `--apply`, and record the date of each here:**
   `tools/set_sim_swap_monitor_schedule.sh` (back to `rate(4 hours)`), `tools/grant_gas_monitor_kms.sh`,
   `tools/create_cost_budget.sh`, `tools/diagnose_lambda_errors.sh relayshield-api`. Every command carries
   `AWS_PROFILE=relayshield` and the merge block first. None of these tools has run against real AWS.
3. **Settle the Twilio question**: usage by product and source for 10-03 to 10-10, and the origin of "1,407 in
   an hour". Rotate the token if the source is not ours. Confirm auto-recharge is off.
4. **Alarm the API**: a CloudWatch alarm on `relayshield-api` errors, and a guard so a hand-deploy cannot replace
   a package the import probe has not seen. Read the 10-11 missing module first.
5. **Create or remove the badge route's missing table** so the 285 a day stops.
6. **Confirm the concurrency quota approval** (PENDING at 1,000), then set reserved concurrency and update REL.
7. **Click Actions, Deploy Privacy Policy Worker, Run workflow on main** (live was diffed and is safe).
8. **After the fixes: re-tick and re-word the WAFR, Save milestone, generate the PDF, request FTR validation on
   solution `soln-aicwx4eiyofnm`, then email Dave Shapiro** (ask who owns co-sell for early-stage ISVs).
9. **Delete the deactivated root access key (ends N2XZ) on or after 2026-10-16** if nothing has broken.
10. **Carried, not re-verified:** tag standardisation; retention on the 8 log groups with none; arm64 and
    right-sizing trial; a load test and tracing; running the test suite in CI; Lambda versions and aliases for
    rollback; `relayshield-signup-api` missing from the invoke policy; the badge route table; read the Hudson
    Rock terms; CS Mobile v1.7.0 build blocked on a JDK; `tools/backfill_first_seen.py --apply` unconfirmed.

## WHERE 2026-10-15 LEFT THINGS. TOMORROW STARTS WITH THE PRIVACY POLICY, THEN THE LOCAL E2E TEST.

**State, from Andrew's own output, not recalled.** `origin/main` is at `026fb5ca`, pushed 2026-10-15, and
carries both 2026-10-15 CLAUDE.md sections above (the Muse UI record and the telemetry scope decisions).
**Nothing in this session changed code.** The promotion tool (`tools/promote_mcp_candidates.py`) is on main,
list mode is proven against real AWS, and both writes simulate `allowed`. The first real `--approve` has not
happened and there is no real candidate to approve.

### ORDER OF WORK (Andrew's, and it is load-bearing: the policy is the authority, everything else follows it)

1. **Privacy policy section 12 in `cloudflare_worker_privacy.js`, with `test_mcp_proxy_privacy.py`.** Change the
   policy and the test together, then deploy by manual dispatch (`deploy_privacy.yml`). What the new text must say:
   * Sent, for PUBLIC upstream hosts only: the **tool name** on an indicator that already passed `public_host()`.
     Tool ARGUMENTS stay out entirely.
   * **SSRF categories become reportable.** A tool name may attach only where the SERVER'S OWN BEHAVIOUR is the
     evidence. An argument-level `ssrf_internal_url` block stays a count with no tool name and no destination, and
     an internal destination is never sent in any form.
   * Also sent: **kit ids**, **neighbor reputation deltas** (public host only), and **hashes of URLs and wallet
     addresses** found in a flagged response.
   * **Not sent: region.** Timestamps are captured server side (rows are keyed by one), the client sends none.
   * **Hash wording must differ.** A response hash cannot be reversed. A URL or wallet hash CAN be confirmed by
     anyone who guesses the candidate, so the policy must NOT extend "cannot be reversed" to those two.
   * Keep the retention figures pinned to the ingest TTLs (the existing test does this) and keep the sentence that a
     reported hostname is not added to the corpus unless independently confirmed (the promotion tool's `--evidence`
     rule depends on it).
   * Also fix the prose that says tool names are never sent: `mcp_proxy/README.md` "Opt-in telemetry" (around lines
     305-325) and the header docstring of `mcp_proxy/telemetry.py` ("WHAT IS NEVER SENT: tool arguments, tool names,
     ..."). Three places state it and the privacy test pins them.
2. **The local E2E test, against the REAL proxy, not the demo.** The demo does not report telemetry (Andrew). It runs
   on his Mac against the live API. **Counts tier only**: the indicators tier needs a public test upstream, so it waits.
   Read the proxy's actual start path first (`mcp_proxy/proxy.py`, `__main__` or the CLI entry) before writing the
   tool, and print the body of what the API returns, not a summary. No EC2 hosted proxy until there are customers.
3. Then, in this order: `_mcpt_validate` and the telemetry table writes (new fields OPTIONAL so old proxies keep
   working), `mcp_proxy/telemetry.py`, the production UI copy, and a read-only super-user view of the review queue.

### WHAT IS STILL UNVERIFIED, SO IT IS NOT TREATED AS FACT

* **How `kit_ids` are derived in `proxy.py`.** They are computed locally and not sent today; read the derivation
  before describing what a kit id discloses, because the policy sentence depends on it.
* **Whether the live screener emits `ssrf_redirect_chain` and `embedded_url_ssrf`.** `ssrf_internal_url` is confirmed
  in `screener.py` (`POISON_SSRF`); the other two were seen only in demo scenario dicts. Do not add a category the live
  code never produces.
* **What backs the Muse toggle.** `Plan FW Cloud` and `Account preview` look like a mock. For a proxy people run
  themselves the setting is the environment variable `MCP_PROXY_TELEMETRY`.
* **The review queue endpoint does not exist.** A Cloudflare Worker cannot read DynamoDB, so the super-user view needs
  an admin-authenticated API route. Read-only first; approval stays in the CLI.
* **Muse's page source is not in this repo.** Everything about it is read from screenshots.

### THE PROMPT FOR MUSE (agreed in conversation 2026-10-15, recorded here because the chat is not a record)

Copy changes only, no layout change. (1) Drive the sharing lists from two arrays, `SHARED_TODAY` and
`SHARED_PENDING`, and render only `SHARED_TODAY`. Today that is: an anonymous random install ID; counts of flagged or
blocked calls by threat category; and at the indicators level (needs an API key) the public hostname of an MCP server
that returned a flagged response plus a one-way hash of that response. `SHARED_PENDING`, hidden until each item ships:
tool names on public servers, scam-kit fingerprint IDs, URL and wallet hashes, neighbor reputation changes, SSRF
findings. (2) "Never shared" reads exactly: tool arguments and prompts; response or instruction text; private,
internal or local hostnames and addresses; API keys or account details; anything from calls that were allowed; your
own policy decisions. (3) Remove "Raw URLs", "region" and "coarse timestamps" from every list, and make no claim that a
hash "cannot be reversed" except for the response hash. (4) Remove the Corpus review queue from the customer tab
entirely; it becomes a separate read-only admin view later. (5) Keep the OFF/ON toggle, default OFF, label it
"Preview" until a backend setting exists, with one line under it: "Telemetry is optional and off by default.
Self-hosted proxies use the MCP_PROXY_TELEMETRY setting." (6) Never mention corpus review or human approval in
customer copy. **Move items from pending to today only after the policy, endpoint and reporter have shipped.**

### CARRIED, NOT RE-VERIFIED THIS SESSION
The first real `--approve`; reader-side wording for promoted rows (`_assess_domain` ignores `source`); an explicit
`kind` field on indicators; proxy adoption; a startup log line stating the telemetry state; `Deploy Privacy Policy
Worker` dispatch; and the whole 2026-10-12 WAFR/FTR list above, which this session did not touch.

## 2026-10-15 (third session): OPT-IN TELEMETRY FOR THE HOSTED VERIFIERS IS BUILT. NOTHING IS RUN OR DEPLOYED.

Asked for from `tap_x401_solution_design` sections 2.3, 2.4 and 4 (phases 2 and 3), extended to TAP
and PAP. Phase 1, the x401 verifier, is Muse's and not in this repo. Full detail, the run order and
the Muse prompt are in `verifier_telemetry_handoff_2026-10-15.md`; this is the record.

**Built, 52 + 16 tests, each guard proven by reintroducing its defect:**
`relayshield_verifier_telemetry.py` (one core for TAP, PAP and x401), the TAP wiring, `GET` and `POST
/v1/verifiers/config`, `tools/setup_verifier_telemetry_table.sh`, a PutItem-only grant (the grant tool
gained `--function`), privacy policy section 13 (Contact is now 14), `test_verifier_telemetry_privacy.py`
which reads policy and code together, and `tools/delete_verifier_reports.py`.

**Where it differs from the design doc, and why it matters:** a `reporter_hash` was added, so the doc's
"historical data is not deleted" is false and the policy promises deletion instead; nothing is called
"anonymized"; `ip_prefix` is the AGENT's address and only if the merchant passes `agent_ip`, never the
API caller's; the enum is nine values because that is what TAP really emits; `attack_pattern` records
what was screened, not what matched; opt-in is per API KEY, not per account.

**The one that changes the pricing story: the committed TAP `lambda_handler` passes no `ti_screen` and
no `nonce_store`.** On main it does no threat-intel screening and has no replay protection across
invocations, while the pricing card promises TI screening and "signed verification receipts" (that word
is not in the file). Either live differs from main or the claims outrun the code. Read
`sh tools/handler_drift.sh relayshield_tap_verifier.py` before anything else touches that Lambda. It is
also in the deploy `paths:` trigger and NOT in `LAMBDA_MAP`, so a push deploys nothing.

**There is no PAP verifier in this repo.** Only `check_poppy_json` inside the MCP proxy, already covered
by section 12. And `/v1/tap/verify` is not routed in `relayshield_api.py`, so the Lambda's real name is
unrecorded: the grant takes `--function`.

**Order matters and is in the handoff:** merge and push (API route live, opting in stores a flag only),
deploy the privacy Worker, create the table and grant, THEN hand-deploy the TAP Lambda with BOTH files
in the zip. Collection starts at the last step, after the policy is live. A zip missing the telemetry
module still verifies and silently reports nothing.

**Not touched, and flagged:** section 3.3 pricing copy ("700K+ indicators" is a count that goes stale;
"x401 mandate verification" must not appear before that verifier ships; the live card says 1,000 a month,
the doc says 100 free) and the blog angles ("FinCEN recognition", "launched today" are unverified).
The privacy section 12 amendments from the earlier 2026-10-15 session are STILL pending.

**Tests that fail on clean `origin/main`, confirmed by stashing my changes, so not from this work:**
`test_bundle_b_gating`, `test_corpus_provenance`, `test_url_malware_attribution`,
`test_x402_manifest_completeness`, and `test_workflows_parse` (relayshield-signup-api missing from the
invoke policy).

## 2026-10-16: x401 IS RECONCILED WITH THE TELEMETRY HOOK, AND THE PS256 VERIFIER NEVER WORKED

Detail and the open list are in `verifier_telemetry_handoff_2026-10-15.md` section 7. The record:

* **Muse's x401 work was recovered from a stash.** The standard merge block's stash line swept
  Andrew's uncommitted edit to `relayshield_tap_verifier.py` and a new untracked `x401_verifier.py`
  into `stash@{0}`, so a session asked to "check again" could not see it. It is on branch
  `x401-wip` (`10c29815`). **The stash line swallows tracked edits as well as untracked files**,
  which this file said once and a block was handed over anyway. Anything uncommitted must be
  committed or told apart before the merge block runs. `git stash branch` is the recovery, and it
  drops the stash on success (the content is then on the branch).
* **The branch had never been run.** Running it found five bugs in the handler (see the handoff),
  most seriously that every mandate check was skipped when the transaction value was empty.
  **A constraint that cannot be checked is a failure, not a pass.** That is the rule, and
  `validate_mandate_scope` now follows it, including `nan` amounts and unreadable dates.
* **`_pss_verify` rejected every valid RSA-PSS signature**, so no PS256 TAP request could ever have
  been accepted. Its leading-bit check shifted the wrong way and it never cleared the top bits of
  the data block. `test_accept_ps256` allowed `accept` OR `reject`, with the comment "environment-
  specific RSA issue", and another test ended `or True  # placeholder`. **A test that accepts both
  outcomes is not a test**, and a comment blaming the environment is a lead to run down, not a
  reason to stop. 40 of 40 valid signatures now verify; `test_pss_verify.py` covers four modulus sizes.
* **The token must not choose the scheme for a key.** `_x401_verify_sig` decides from the registry
  key's type, so an Ed25519 key only ever verifies EdDSA and an RSA key only PS256. RS256 (PKCS#1
  v1.5) is unsupported and fails rather than being checked with the wrong scheme.
* **The trusted-issuer registry is empty and is Andrew's call.** Empty means every presentation is a
  `review`; nothing is accepted. Nothing in this repo should invent which issuers to trust.
* **Guards proven by reintroduction (8):** tx-value skip, nan, the old PSS shift, token-chosen alg,
  unguarded import, empty-registry-as-accept, issuer not passed to telemetry, review overriding
  reject. `test_x401_integration.py` (40), `test_pss_verify.py` (4); the TAP, telemetry and privacy
  suites still pass. `test_workflows_parse` still fails on `relayshield-signup-api` missing from the
  invoke policy, as it does on clean main.
* **Not deployed, and the zip needs four files** (see the handoff). Nothing here has run against AWS.

## 2026-10-16 (later): I RECOMMENDED "PROOF'S PUBLISHED KEY" WITHOUT CHECKING. THERE IS NONE, AND x401 TARGETS THE OLD DRAFT.

Asked to add Proof's key to the issuer registry "as you suggest". The recommendation was mine and
unverified. Reading the spec from `raw.githubusercontent.com/proof/x401/main/spec.md` (reachable;
`x401.proof.com` is not) showed:

* **Proof is not an issuer.** Issuer trust is the verifier's own policy via DCQL
  `trusted_authorities`. There is no single key. **No key was added**; `x401_issuers.json` is empty.
* **The code implements x401 0.1.0** (`PROOF-PRESENTATION`, a bare W3C VP of JWT credentials) while
  its docstring says "0.2.0". The current draft uses `PROOF-REQUEST` / `PROOF-RESPONSE` /
  `PROOF-RESULT` and an OpenID4VP/DCQL flow in which the VERIFIER composes and signs the request and
  validates the result against it. That is a different product, not a rename.
* **x401 stays off.** An empty registry means every presentation is a `review`. Do not put x401 on
  the pricing card. The choice (a bespoke 0.1.0-style mode for a named customer, or the real
  relying-party build) is in the handoff, section 8.

**The rule, again: a recommendation that names a specific external artefact ("their published key",
"their endpoint", "their header") is a claim about that artefact and needs the artefact read first.**
This is the `_APIFY_BANNER` and MetaMask-Snap mistake with a recommendation on the end of it.

The three open items from the reconcile are fixed (handoff section 8): replay protection (two bugs:
a fresh store per call, and nothing shared across containers; now a DynamoDB conditional put behind
`VERIFIER_NONCE_TABLE`), required `exp`, and TI screening (`relayshield_tap_ti.py`, behind
`VERIFIER_TI_SCREEN=1`). **The new environment variables are off by default so that the table, the
grant and the variable can be put in place in that order; setting the variable first makes every
request answer `nonce_store_error`.**

**A test that reuses a nonce was passing only because replay protection did nothing.** Seventeen
existing TAP tests failed the moment the store persisted, because they all use nonce `n1`. They now
get a fresh store each; that failure was the fix working.

## 2026-10-16: THE x401 RELYING PARTY IS BUILT (NOT DEPLOYED). SEE `x401_relying_party.md`.

Andrew was announcing a full-stack x401+TAP verifier and rejected my "leave x401 off" recommendation as
lazy; he was right that the recommendation answered "is Muse's code safe" and not "can we ship the stack".
Built from the x401 0.2.0 spec and OpenID4VP 1.0 (pulled from the vendor repos, not recalled): `x401_jose.py`,
`x401_rp.py`, `x401_net.py`, wired into `relayshield_tap_verifier.py` (TAP first, then the credential).
`x401_testkit.py` (issuer, wallet, agent) is test-only and NOT packaged. Muse's `x401_verifier.py` targets the
old 0.1.0 draft and is no longer the path.

Proof: 97 + 23 + 42 + 40 + 9 + 4 tests, `tools/x401_demo.py` runs the flow with six attacks, and each guard was
mutation-proven. Two mutants are equivalent and documented, not hidden.

**Not verified: any real wallet, any real issuer, wallet acceptance of the did:web client_id.** mso_mdoc,
ldp_vc, response encryption and token exchange are refused by design. There is no "Proof published key"; the
earlier claim was retracted in a previous section and the registry ships empty on purpose.

**Deploy order and traps** (the function is NOT in `LAMBDA_MAP`; the zip must contain every module;
`VERIFIER_NONCE_TABLE` is set LAST and merged, never replaced): see `x401_relying_party.md`. Privacy policy
section 14 describes the processing; Contact moved to 15 and `test_verifier_telemetry_privacy.py` pins that.
`test_x401_privacy.py` executes real credentials with a distinctive claim value and fails if it reaches a log
or the nonce store, which holds only a SHA-256 key and an expiry of at most an hour.

## 2026-10-16 (later): x401 DEPLOY STEPS 1-4 RAN. THE VERIFIER HAS ITS OWN ROLE, SO THE SHARED-POLICY GRANT TOOL DOES NOT APPLY.

Measured from Andrew's output, not recalled:
* **The signing key exists.** Secret `relayshield/x401_verifier_key` is created; the public half is in
  `relayshield_x401_pubkey.py` (commit `7b452be1`, pushed to main) and `https://api.relayshield.net/.well-known/did.json`
  answers 200 with the same `x`/`y`. The privacy Worker (section 14) deployed green.
* **The verifier Lambda is `relayshield-tap-verifier`, role `relayshield-tap-verifier-role`** (python3.12, handler
  `relayshield_tap_verifier.lambda_handler`). `relayshield-pap-verifier` is a separate function that x401 does not touch.
  The role carries only `AWSLambdaBasicExecutionRole` and `relayshield-x401-secret-read` (created and attached today;
  the simulator says `allowed` for the signing secret).
* **Drift read: live is byte-identical to `10c29815`** (Muse's WIP, recovered from the stash), last modified
  2026-10-16T00:45Z, and its package holds no other `relayshield_*.py`. Nothing live-only, so a deploy of the new
  package loses nothing. Live still has the old behaviour (empty issuer registry, PS256 verifier that rejects every valid
  signature, per-call nonce store).
* **`tools/grant_breach_cache_access.py` STOPPED, as predicted:** `relayshield-first-seen-write` is not attached to the
  verifier's role. The dedicated `tools/grant_verifier_table_access.py` (PutItem only, on exactly the nonce and telemetry
  tables, refuses a missing table or the wrong account, 8 tests, six guards mutation-proven) replaces it for this role.
* **UNCONFIRMED: the table setup scripts' completion.** Andrew's paste showed the nonce script print `created` output up
  to the table name and then nothing, and no telemetry-script output at all. A `set -e` abort at `wait table-exists` and
  a truncated paste look identical. The scripts are idempotent; the next step re-runs them and reads each table.

## 2026-10-16 (later still): THE GRANT TOOL REPORTED A GRANTED POLICY AS A FAILURE. MY STAND-IN AWS HAD THE WRONG SHAPE.

`tools/grant_verifier_table_access.py` created and attached `relayshield-verifier-tables-write` and then printed
`IAM simulator: ... -> ['allowed']` followed by `STOP: the role still cannot write both tables.` The policy was fine. The
tool asked the simulator about BOTH table ARNs in one call and compared the number of result rows to the number of tables,
but `simulate-principal-policy` returns ONE row per ACTION however many resources were asked about, so one action always
looked like a failure. **The tests passed because the stand-in `aws` returned one row per ARN, which the real API does not.**
A fake that answers the way the author expects is a second implementation that agrees with the first.

Fixed: one simulator call per table, each answer required to be `allowed`, and the fake now returns the real shape (one
row per action) and records how it was asked. Run against the OLD code the new tests fail, and two further breakages are
caught. `grant_x401_secret_access.py` has one resource and one action, so it was never affected.

Also measured the same evening: the telemetry table's TTL is ENABLED (the script's `None` line is just the
`update-time-to-live` response having no status field), the nonce table's TTL is ENABLED, and **`relayshield-tap-verifier` has
NO environment variables at all** (`keys(Environment.Variables)` failed on null). So `VERIFIER_NONCE_TABLE` has nothing to
be merged into and the merge tool's "preserved: (none)" is correct, not a warning.

**x401 package deployed 2026-10-16 02:21 UTC**: `relayshield-tap-verifier`, sha256 `5ad58e35...`, 47,439 bytes. A challenge
request for a policy that does not exist answers `404 unknown_policy`, which proves the new code loaded AND the signing key
was read from Secrets Manager (a signer failure answers 503 before the policy lookup). **Not yet done:** the grant tool
re-run, `VERIFIER_NONCE_TABLE`, a policy, a trusted issuer.

## WHERE 2026-10-17 LEFT THINGS. TWO THREADS: x401 IS DEPLOYED BUT TRUSTS NOBODY, AND THE SHOPIFY CHECK IS STILL PENDING.

**Branch `claude/ecstatic-davinci-wh8xxr`, last commit `ecde0bf`, pushed and NOT on `origin/main`.** Commits not on
main: the verifier-table grant tool and its fix, the x401 announcement pack, and the Shopify Worker change with its
tests. `origin/main` already carries the x401 relying party itself (`5d03e88`) and the published public key
(`7b452be`). Andrew's local `main` has merged `f7119a7`; whether he pushed it is unknown, so check
`git --no-pager log --oneline origin/main..main` before assuming.

### x401 + TAP: DEPLOYED, REFUSES EVERYTHING, BY DESIGN

* Deployed to `relayshield-tap-verifier` on 2026-10-16 (hand deploy, the function is not in `LAMBDA_MAP`). A challenge for an
  unknown policy answers `404 unknown_policy`, which proves the new code loaded and the signing key was read.
* **`VERIFIER_NONCE_TABLE` is still a PLAN, not applied.** His plan output was `before {}`, `after {"VERIFIER_NONCE_TABLE":
  "<redacted>"}`, `preserved: (none)`. Until it is applied, replay protection is per container. `x401_issuers.json` is
  `{"issuers": {}}` and `x401_policies.json` holds no policy, so nothing can be accepted.
* **The issuer question, researched 2026-10-16 from secondary sources** (proof.com, x401.id and shopify-style vendor sites are all
  egress-blocked): Proof is an issuer, not a trust anchor, so there is no key to add. It issues an IAL2 person credential
  (`jwt_vc_json`, assurance levels VC-AL2 and VC-AL3, backed by an X.509 certificate from its own CA) and, with Enigma, Business
  Certificates for verified businesses. No sandbox, issuer DID, JWKS or `vct` was found, and nothing names a category claim.
  GLEIF vLEI is ACDC/KERI and EU PID is mostly mdoc, so neither fits our formats. **Unverified and decisive: whether Proof's
  credentials are signed with a JWKS key or an `x5c` chain.** We verify against registry JWKS only (ES256, Ed25519, PS256).
* **Decision (Andrew, 2026-10-17): use the x401 testkit issuer for the announcement.** That means `python3 tools/x401_demo.py`,
  labelled as a simulated issuer. **Do not register a testkit key in the live registry**: its private half would be in a public
  repo, so anyone could mint a credential the live verifier accepts. A live demo route needs its own policy guarding nothing real,
  and that is a separate decision he has not made.
* `x401_announcement_pack_2026-10-16.md` holds the Proof contact text (form at `https://www.proof.com/contact-x401`, fields
  unread), the summary for Muse, and the list of claims the announcement can and cannot make. **Whether the Proof form was
  submitted and the Muse summary sent is not recorded.**

### SHOPIFY ORDER SCREENING: THE EMBEDDED APP CHECKS ARE STUCK AT "PENDING", AND NOBODY HAS ANSWERED

App "RelayShield Order Screening", version `relayshield-order-screening-4` (released 2026-10-10), dev store
`relayshield-test.myshopify.com`, Worker `relayshield-order-screening` on `relayshieldadmin.workers.dev`, code in `shopify/`.

**What is established.**
* Both embedded checks ("latest App Bridge from Shopify's CDN", "session tokens") show an EMPTY circle, not red: Shopify has
  received no data, which is different from failing. Everything else on the submission list is green.
* The app loads in the Admin iframe and shows the shop name, and that is only rendered when the Worker has verified a session
  token, so tokens arrive and verify. That does NOT prove App Bridge initialised: the server reads the `id_token` URL parameter,
  which needs no App Bridge. A wrong or empty `shopify-api-key` meta value fails silently and looks exactly like this.
* Secondary evidence (forum snippets, Shopify pages unreachable): the checks are telemetry from App Bridge initialising in a real
  Admin session on a dev store, every 2 hours, with up to 2 days of lag, and staff advise a browser with no extensions. Several
  developers report the same stuck state with correct setups, and some were unblocked by staff after verification.
* **A code comment in `shopify/worker.js` said the checks "load the App URL directly (no session token)". That was wrong** (the
  checks are not a crawler) and is corrected.
* **A real defect, not proven to be the cause:** managed installation (`use_legacy_install_flow = false`) never calls `/auth`, which
  was the only place the Worker got a token or registered `orders/create`. The existing dev store works because it was installed under
  the old flow (orders #1004 to #1010, Oct 4 to 10, mostly synthetic fixtures). A fresh install, which is what a reviewer does,
  would be empty. The Worker now exchanges the session token on first authenticated load. **Written and tested against stubs
  only, NOT deployed, and the token-exchange parameter names are from memory.**

**Where it stands.** Andrew posted to the Shopify community and got no answer. His support ticket has been with an AI support
agent for 10 days without reaching a person. He will retry from a browser with no extensions.

### TODOS FOR THE NEXT SESSION, IN ORDER

1. **Shopify console check, his result decides everything.** In a clean browser profile, open the app in Admin, Inspect, Console,
   filter `RelayShield`. `session token acquired` then `session auth check: 200` means the code is fine and this is Shopify's side.
   `session token unavailable` or `App Bridge not ready` means compare the `shopify-api-key` meta value with the Client ID in the
   Dev Dashboard. No `[RelayShield]` lines means the live Worker is not the repo code. `401` means a wrong `SHOPIFY_API_SECRET`.
   Ask for the exact lines, not a summary. Full table and the support text are in `shopify_embedded_check_2026-10-17.md`.
2. **Shopify drift read BEFORE any deploy:** `sh tools/recover_live_worker.sh relayshield-order-screening shopify/worker.js`. Only
   `IDENTICAL` makes a deploy safe. `shopify/wrangler.toml` holds a placeholder KV id, so a deploy needs the real id from
   `npx wrangler kv namespace list` in the LOCAL copy only, then `git checkout shopify/wrangler.toml`. Then deploy and prove token
   exchange on a SECOND, freshly installed dev store, because the existing one is left alone by design and proves nothing about it.
3. **Get a human at Shopify.** The AI agent loop is the blocker, not the code. Options, each UNVERIFIED because shopify.com is
   unreachable from here: reply on the ticket asking in plain words for a human agent and quoting the App ID and the ten-day age;
   reply on the specific community thread for "embedded app checks stuck" with the paragraph from the analysis file; use any
   Partner Support chat or phone route the Partner dashboard shows. Record which one worked here.
4. **Run `/shopify-app-store-review`** from the Shopify AI Toolkit, which the last row of the submission page offers.
5. **Merge and push** the branch's three unmerged pieces to `main` (standard merge block, CLAUDE.md conflicts keep both sides).
6. **x401:** apply `VERIFIER_NONCE_TABLE` (read the plan, then `--apply`), re-run `grant_verifier_table_access.py` once more and
   record its output, send the Proof form, send Muse the summary, and decide whether a live demo policy is wanted.
7. **Carried, not re-verified this session:** the whole 2026-10-12 WAFR/FTR list (the unanswered question, 36 High risks, the API
   alarm, the badge table, `tools/diagnose_lambda_errors.sh` and the budget at USD 10), the root key deletion on or after
   2026-10-16, the first real `--approve` of an MCP candidate, the 2026-10-15 telemetry policy amendments, CS Mobile v1.7.0 behind a
   missing JDK, and `tools/backfill_first_seen.py --apply`.

### THREE THINGS FROM THIS SESSION WORTH NOT REPEATING

* **A guess about a vendor's checker, written into a code comment, steered the build for ten days.** The "checks load the App URL"
  comment justified serving the dashboard without a token. Read how a checker gets its data before building to pass it.
* **A recommendation that named a specific vendor artefact ("Proof's published key") was wrong** and was retracted. It nearly went
  into a registry that decides who is trusted.
* **A stand-in `aws` that answers the way its author expects is a second implementation that agrees with the first.** The grant tool
  reported a granted policy as a failure because the fake returned one row per ARN and the real API returns one per action.
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
