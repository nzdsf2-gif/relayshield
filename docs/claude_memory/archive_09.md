<!-- Verbatim sections moved out of CLAUDE.md on 2026-10-18, original order. Not auto-loaded.
     Find one with: grep -n 'WORDS' docs/claude_memory/INDEX.md -->

## 2026-10-14: THE PROMOTION STEP IS BUILT. IT IS THE ONLY WAY A PROXY REPORT REACHES THE CORPUS.

`tools/promote_mcp_candidates.py` (+ `test_promote_mcp_candidates.py`, 30 tests, 7 defects
reintroduced and each fired its own guard). Review-and-approve, one candidate at a time:

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/promote_mcp_candidates.py          # list
    ... --all                                                                             # + why each is blocked
    ... --approve ID8+ --reviewer NAME --evidence "what you checked" --confirm-host HOST  # dry run
    ... same line plus --apply                                                            # writes
    ... --reject ID8+ --reviewer NAME --reason "why"

**A PROMOTED HOST FLAGS IMMEDIATELY, FOR EVERYONE.** `_assess_domain` treats ANY domain/url row in
`relayshield_intel_iocs` as "appears in RelayShield's criminal IOC corpus" and reads no confidence or
source field. The row is labelled `confidence: unverified, source: mcp_proxy_telemetry`, but that is a
label, not a gate. A test fails if `_assess_domain` ever starts honouring either field, because the
tool's warning would then be out of date. So a wrong promotion is a false positive served to every
user, which is why a human approves each one and every blocker is re-checked at approval time.

**TWO DESIGN FINDINGS, BOTH FROM READING HOW THE PROXY PRODUCES THE DATA, NOT FROM THE SCHEMA:**

1. **THE REPORTED HOST IS THE UPSTREAM MCP SERVER, NOT A HOST IN THE CONTENT.** A tool RESULT can
   relay third-party content (a repository, a document, an email) that carries an injection, so the
   server is not the actor and promoting it would flag a legitimate server. Only DISCOVERY-time
   findings (tools/list, prompts/list: metadata the server authors itself) are attributable.
   The proxy records an approved-taxonomy id only for discovery and passes `[]` for results, so
   **"no taxonomy id" is treated as "a tool result, not promotable"**. That coupling is implicit, so
   `test_promote_mcp_candidates` reads `proxy.py` with `ast` and fails if it breaks. Proven by
   passing ids on the result call.
2. **`malicious_url` AND `kit_match` ARE ECHOES OF OUR OWN CORPUS.** The proxy decides them by calling
   `/v1/composite-check` and `/v1/payg/scamkit-match`. Promoting them would feed our verdict back in as
   independent evidence, so a false positive would look corroborated by the very installs it fooled.
   **That is the loop hazard in "a perpetual fence", and it is closed by never promoting those two.**
   Promotable: `prompt_injection`, `credential_exfiltration`, `oauth_tampering` only. Counts for the
   rest are still collected and useful as trend data.

**OTHER RULES:** distinct reporting ACCOUNTS (default 2, `anon` never counts) because a free key is minted
from an email alone, so this is a threshold and not proof; reserved documentation names, brand official
domains and shared-hosting platforms THEMSELVES are blocked (a tenant of one is allowed with a note); a
host already in the corpus is blocked; all-zero hash is blocked, which is why the 2026-10-14 test
candidate can never be promoted. The denylists are PARSED out of `relayshield_api.py` with `ast`, not
retyped, with a floor so an empty parse refuses rather than passing everything.

**`--evidence` IS REQUIRED (20+ characters) AND STORED ON THE ROW**, because privacy policy section 12
promises a reported hostname "is not added to our threat intelligence corpus ... unless we have
independently confirmed it". Two reporting accounts are corroboration; someone fetching the server's
`tools/list` and reading it is confirmation. A test pins the policy sentence beside the requirement.

**WRITE SAFETY:** claim (`unreviewed` -> `promoting`, conditional) -> one `put_item` -> `promoted`. A failed
corpus write releases the claim; a failed release says so loudly. Two approvers cannot both win. It
writes ONLY `relayshield_intel_iocs`, never `relayshield_intel_first_seen`: promoted rows must not enter
the lead-time measurement (SPEED-1), and a test asserts the one `put_item` and no first-seen reference.

**UNVERIFIED, and the first run settles it:** whether `relayshield-deployer` can `Scan` the telemetry table
(the report tool already assumes so), `UpdateItem` it, and `PutItem` `relayshield_intel_iocs`. An
AccessDenied is printed as itself. The tool was exercised end to end only against a stubbed boto3.

**NOT BUILT, in order of value:**
* **Reader-side wording.** A promoted row should say "reported by monitored MCP proxies", not "criminal
  IOC corpus". Today it cannot, because `_assess_domain` ignores `source`.
* **A `kind` field on indicators**, so discovery vs result is explicit instead of inferred from the
  taxonomy id. Needs a proxy release and an endpoint change.
* **Proxy adoption.** Telemetry is opt-in and off by default, so the loop is closed in code and empty in
  fact until installs report. Until then the candidate list will read zero, which is the normal state.

## 2026-10-14: THE PROMOTION TOOL RAN AGAINST REAL AWS. LIST MODE IS PROVEN; THE TWO WRITES ARE NOT.

Andrew merged `claude/awesome-cannon-mer1x5` into his LOCAL main (not pushed) and ran
`tools/promote_mcp_candidates.py --all` as `relayshield-deployer`. Output, not recalled:
`1 candidate(s) ...: 0 eligible for review, 1 not`, the one being the `probe-test.example.com` test
candidate, blocked on all five grounds (echo category, no taxonomy id, 1 reporter, all-zero hash, reserved
documentation name). So the safety property holds on live data: the test row can never be promoted.

**PROVEN by that run:** the deployer can `Scan` `relayshield_mcp_proxy_telemetry` and `Query`
`relayshield_intel_iocs` (the corpus lookup runs for every candidate before evaluation, and an AccessDenied
would have printed a traceback). **STILL UNPROVEN:** `UpdateItem` on the telemetry table (needed by approve
and reject) and `PutItem` on `relayshield_intel_iocs` (needed by approve). Both are exercised only by a
write, so the first real approval is also the first test of the deployer's write access to the corpus.
Read it with `iam simulate-principal-policy` against the deployer user BEFORE the first approval, so a
denied write is found by a read and not by a half-finished claim.

**2026-10-14 (later): BOTH WRITES SIMULATE AS `allowed`.** `iam simulate-principal-policy` on
`arn:aws:iam::239677749008:user/relayshield-deployer` returned `dynamodb:PutItem allowed` on
`relayshield_intel_iocs` and `dynamodb:UpdateItem allowed` on `relayshield_mcp_proxy_telemetry`. A
simulation is not the write, so the first real approval remains the final proof, but a missing grant is
no longer the expected failure.

## 2026-10-15: MUSE BUILT A PRODUCTION MCP FIREWALL UI WITH A TELEMETRY OPT-IN. ITS DISCLOSURE DOES NOT MATCH WHAT THE PROXY SENDS.

Andrew showed three screenshots of a production UI generated by Muse for `mcpfw.relayshield.net`
(header: Region us-east-1, Plan FW Cloud, Account preview). It sits beside the demo UI
(`mcp_proxy/dashboard.html`) and **its source is NOT in this repo** (a grep for its strings finds nothing),
so everything below is read from screenshots. Andrew's decision: **only the opt-in telemetry is needed in the
production UI**, and this session was told not to build any of it, only to record it.

* **Tabs:** Overview, Servers, Policies, Quarantine, Audit Trail, **Telemetry**, API Keys, Verifiers, Billing.
* **Telemetry tab:** a "Sharing state" card with an OFF/ON toggle ("Equivalent to leaving
  MCP_PROXY_TELEMETRY unset"), a "Shared when on (indicators level)" list, a "Never shared" list, a note that
  the indicators level needs an API key, and a "Corpus review queue" table (candidate, type, source server,
  evidence, first seen, status "Pending review").
* **Andrew had Muse remove the sentence "Candidates land in the review queue below and are only written to the
  TI corpus after a human approves them".** True, but internal, so not customer copy. The screenshot he sent
  still shows it, so it may predate that edit.

### THREE THINGS THE UI SAYS THAT THE CODE AND THE PRIVACY POLICY CONTRADICT

Read from `mcp_proxy/telemetry.py` (`snapshot_and_reset`), `relayshield_api.py` (`_mcpt_validate`) and
`cloudflare_worker_privacy.js` section 12, which `test_mcp_proxy_privacy.py` pins:

1. **"Shared when on" lists "Tool names and verdicts".** The policy says tool names are NEVER sent, the README
   says the same, and `record()` never receives one. The report carries only: install id, mode, taxonomy
   version, counts by (category, taxonomy id, kind), and at the indicators level the PUBLIC HOSTNAME of the
   flagged server plus a SHA-256 of the response.
2. **It lists "kit_<sha256> fingerprints, URL and wallet hashes, neighbor reputation deltas, coarse timestamps
   and region".** None of those fields exists in the payload, and `_mcpt_validate` would reject a field it does
   not know. A disclosure that promises MORE sharing than happens is a consent problem too: a customer may
   decline something we never collect.
3. **"Never shared" says "Raw URLs".** The indicators level sends a raw hostname (not a URL, and not hashed).
   The policy states that plainly; the UI should say "the public hostname of a flagged server".

**The policy is the authority and the UI must be corrected to it, not the other way round.** Changing what is
collected means changing section 12 and its test first.

### THE REVIEW QUEUE'S EXAMPLE TYPES CANNOT EXIST IN THIS BACKEND

The mock rows are a "Phishing-kit fingerprint" (`kit_...`) and a "Lookalike domain indicator" (`url_h: ...`).
Candidates here are keyed on a host hash with a category from `prompt_injection`, `credential_exfiltration`,
`oauth_tampering`, `malicious_url` and `kit_match`. The last two are echoes of our own corpus and
`tools/promote_mcp_candidates.py` refuses to promote them (`ECHO_CATEGORIES`). **A queue that shows kit and URL
rows would be showing items the promotion step blocks by design.**

### OPEN, UNANSWERED

* **Is the queue customer-facing?** If it is, it is a customer's view of their own reported items and the
  header ("awaiting human review before any TI corpus update") restates the sentence Andrew removed. If it is
  our internal view, it does not belong in a customer UI. Andrew's stated scope ("only the opt-in telemetry")
  suggests it should not be there.
* **Does anything back the toggle?** `Plan FW Cloud` and `Account preview` look like a mock. For the proxy
  people run themselves, the setting is the environment variable `MCP_PROXY_TELEMETRY`; a hosted multi-tenant
  proxy is a different consent model, because RelayShield would itself be the processor of the traffic, and
  UNVERIFIED whether such a service exists.
* **Still no end-to-end test with a real running proxy**, and no real candidate, so the first
  `--approve` is still the first real write to `relayshield_intel_iocs`.

## 2026-10-15 (later): TELEMETRY SCOPE DECIDED WITH ANDREW. SSRF IS NOT REPORTED AT ALL TODAY, WHICH IS BIGGER THAN THE TOOL-NAME QUESTION.

**Found while checking Andrew's contention that tool names add value for SSRF detection.** The live screener
(`mcp_proxy/screener.py`, `POISON_SSRF = "ssrf_internal_url"`) emits SSRF verdicts, and `proxy.py` passes the
verdict category to `telemetry.record()`. **`ssrf_internal_url`, `ssrf_redirect_chain` and `embedded_url_ssrf`
are in NEITHER `REPORTABLE_CATEGORIES` (`mcp_proxy/telemetry.py`) NOR `_MCPT_CATEGORIES` (`relayshield_api.py`),**
so `record()` returns early and the endpoint would refuse them. The proxy's SSRF hardening, which exists because
of the zotero-mcp SSRF, therefore contributes nothing to the corpus. UNVERIFIED: that the redirect-chain and
embedded-URL strings are emitted by the live screener (they were seen in demo scenario dicts in `proxy.py`);
`ssrf_internal_url` is confirmed in `screener.py`.

### DECISIONS (Andrew, 2026-10-15). THE POLICY IS CHANGED FIRST, THEN THE ENDPOINT, THEN THE REPORTER, THEN THE UI.

1. **Tool names are sent, for PUBLIC upstream hosts only**, attached to an indicator that already passed
   `public_host()`. Length and character set validated on the endpoint. Tool ARGUMENTS stay out entirely.
2. **SSRF categories become reportable.** Rule for what may carry a tool name: **only findings where the SERVER'S
   OWN BEHAVIOUR is the evidence** (a redirect chain served by a public host that lands on internal
   infrastructure, a discovery-time finding, a flagged result). **An argument-level `ssrf_internal_url` block stays
   a COUNT with no tool name and no destination**: the agent chose that URL, our proxy refused it before the tool
   ran, so naming the tool would accuse it of something it did not do. An internal destination is customer
   topology and is never sent in any form.
3. **Also sent:** kit ids already computed in `proxy.py` as `kit_ids` (host-to-kit association, UNVERIFIED how they
   are derived), neighbor reputation deltas (public host only), and hashes of URLs and wallet addresses found in a
   flagged response.
4. **Not sent: region** (we log no IPs, so it would be self-reported, low value, one more disclosure). **Timestamps
   are already captured server-side** (report rows are keyed by one), so the client sends none.
5. **The hash wording must differ.** A response hash cannot be reversed. A URL or wallet hash CAN be confirmed by
   anyone who guesses the candidate, because wallet addresses are public and URLs are guessable. Policy section 12
   must not extend "cannot be reversed" to them.
6. **Review queue: super-user only (Andrew), not shown to customers.** Read-only view first; approval stays in
   `tools/promote_mcp_candidates.py`. The Worker cannot read DynamoDB, so it needs an admin-authenticated endpoint.
7. **No EC2 hosted proxy until there are customers (Andrew).** The proxy is customer-run, so the E2E test runs
   locally against the live API. **The demo does not report telemetry (Andrew), so the test must use the real
   proxy.** Counts tier is testable locally; the indicators tier needs a public test upstream, so it is deferred.

### WHAT HAS TO AGREE BEFORE ANY OF IT SHIPS

`cloudflare_worker_privacy.js` section 12 and `test_mcp_proxy_privacy.py` first (deploy is a manual dispatch),
then `_mcpt_validate` and the telemetry table writes (new fields optional, so old proxies keep working), then
`telemetry.py`, then the production UI copy. **The UI must list only what has shipped**, because the earlier
mismatch was a list promising fields that did not exist. Muse should hold the new items behind a flag.
