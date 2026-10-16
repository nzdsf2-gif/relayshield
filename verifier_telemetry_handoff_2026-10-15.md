# Verifier opt-in telemetry: what was built, what changed from the design doc, what to run

2026-10-15. Covers design doc sections 2.3 (DynamoDB schema), 2.4 (privacy policy), 4 phases 2
and 3, and the extension to the TAP and PAP verifiers. Phase 1 (the x401 verifier) is Muse's.

## 1. What is built (all on branch `claude/ecstatic-davinci-wh8xxr`)

| Piece | File | State |
|---|---|---|
| Telemetry core, shared by TAP, PAP, x401 | `relayshield_verifier_telemetry.py` | built, 52 tests |
| TAP verifier wired to it | `relayshield_tap_verifier.py` (`_report_rejection`) | built, verdict cannot change |
| Opt-in API | `POST` / `GET /v1/verifiers/config` in `relayshield_api.py` | built, tested through the dispatcher |
| Table + TTL + AgentHashIndex | `tools/setup_verifier_telemetry_table.sh` | written, NOT run, UNVERIFIED against real AWS |
| IAM grant (PutItem only) | `tools/grant_breach_cache_access.py --table relayshield_verifier_telemetry --function <name>` | built, 23 tests |
| Privacy policy section 13 | `cloudflare_worker_privacy.js` (Contact is now 14) | written, NOT deployed |
| Policy-to-code pin | `test_verifier_telemetry_privacy.py` | 16 tests |
| Deletion on request | `tools/delete_verifier_reports.py` | built, dry run by default |

Defaults and guarantees, each pinned by a test that was proven by reintroducing the defect:
off by default; only a JSON boolean `true` turns it on (the string "true", 1, a missing field
all mean off); only REJECTED verifications are recorded; an accept or review costs no DynamoDB
read; telemetry cannot change a verdict or break a response; the customer's key is read from
the call to us, never from the agent's headers; the agent's address is only what the merchant
passes as `agent_ip`, never the address of the account calling us.

## 2. Where this deliberately differs from the design doc

1. **Added `reporter_hash`** (first 16 hex of SHA-256 of the API key). Without it there is no
   way to honour a deletion request and no way to count distinct accounts before anything is
   treated as corroborated. Consequence: the doc's 2.4 item 7, "historical anonymized data is
   not deleted", is not true of this design, so the policy says the opposite and
   `tools/delete_verifier_reports.py` exists to keep that promise.
2. **No "anonymized" anywhere.** A hash of a public key id can be confirmed by anyone holding
   the id, and a /24 prefix plus a timestamp is not anonymous. The policy says "one-way hash"
   and states the limit plainly (this repo's hash-wording rule).
3. **`ip_prefix`**: IPv4 /24 and IPv6 /48, global addresses only, and only if the merchant
   sends `agent_ip` in the request. The doc did not say whose address. Using the API caller's
   would have collected the customer's network instead of the attacker's.
4. **`rejection_reason` enum widened** from five values to nine (adds `unknown_key`,
   `intent_mismatch`, `malformed`, `other`) because those are what the TAP verifier really
   emits. The raw reason string is never stored.
5. **`attack_pattern` records what was SCREENED**, not what matched (`wallet`, `domain`,
   `wallet+domain`). The verifier cannot tell which indicator matched.
6. **Infrastructure failures are not reported** (`nonce_store_error`, `ti_unavailable`,
   `jwks_unavailable`). Recording our outage as an attack would poison the data.
7. **Endpoint is `/v1/verifiers/config`**, not `/api/verifiers/config`, to match every other
   route. The flag lives on the API key record, so **opt-in is per key, not per account**:
   an account with three keys opts in three times.
8. **`agent_id_hash` is omitted when empty.** It is the GSI key and DynamoDB refuses an empty
   string there; omitting keeps the index sparse.
9. **A `ti_match` row is our own corpus's verdict coming back at us.** Counting it is fine.
   Nothing reads this table into the IOC corpus, and nothing should without a reviewed step
   that refuses echoes (as `tools/promote_mcp_candidates.py` does).

## 3. Things found while reading the code (not fixed, each with a recommendation)

- **The committed TAP `lambda_handler` passes no `ti_screen` and no `nonce_store`.** In the code
  on main it performs no threat-intel screening and has no replay protection across
  invocations, yet the pricing card promises TI screening and "signed verification receipts"
  (the word "receipt" does not appear in the file). Either the live Lambda differs from main
  or the claims outrun the code. **Recommendation: run the drift read first, then I wire the
  screen and a DynamoDB nonce store (about half a day).** Until then no `ti_match` row can be
  produced by the committed handler.
- **`relayshield_tap_verifier.py` is in the deploy `paths:` trigger but not in `LAMBDA_MAP`,**
  so a push deploys nothing and the file looks wired. Hand deploy, or map it (the mapping
  commit must touch the `.py`).
- **No `/v1/tap/verify` route exists in `relayshield_api.py`** and the Lambda's real name is not
  recorded anywhere. The grant script takes `--function` for this reason.
- **There is no PAP verifier in this repo.** The only PAP code is `check_poppy_json` inside the
  MCP proxy, which section 12 already covers. `maybe_report("pap", ...)` is ready the moment a
  PAP verifier exists to call it. The $49 PAP and $80 bundle in the doc have no code behind
  them here.
- **Section 3.3 pricing copy, not touched.** "700K+ live threat indicators" is a count that
  goes stale (687K measured 2026-10-08, growing about 25K a week); name sources instead.
  "x401 mandate verification" must not go on a pricing card before the x401 verifier ships.
  The live card says fair use 1,000 verifications a month, the doc says 100 free.
- **Blog angles: "FinCEN recognition" and "launched today" are unverified claims.** Do not
  publish them without a source.
- **The config route has no CORS, on purpose.** A browser console holding the customer's key
  would be dead (curl cannot show this). The console's backend must call it server side.

## 4. Order to run it (each step is Andrew's; nothing below has been run)

Collection only starts at step 6, and the policy is live before then.

1. **ANDREW RUNS THIS**: merge the branch (the standard block, no `git add -A`).
2. Run the new tests, then push `main`. The push deploys `relayshield-api`, which carries the
   `/v1/verifiers/config` route. At this point opting in only stores a flag.
3. **ANDREW CLICKS THIS**: Actions, "Deploy Privacy Policy Worker", Run workflow on main.
   Optionally run `sh tools/recover_live_worker.sh relayshield-privacy cloudflare_worker_privacy.js`
   first and proceed only on `IDENTICAL`.
4. **ANDREW RUNS THIS**: `AWS_PROFILE=relayshield sh tools/setup_verifier_telemetry_table.sh`.
5. Find the TAP Lambda's real name (read only), then the grant dry run, then `--apply`.
6. Read the drift (`sh tools/handler_drift.sh relayshield_tap_verifier.py`), then hand-deploy the
   TAP Lambda **with both files in the zip** (`relayshield_tap_verifier.py` and
   `relayshield_verifier_telemetry.py`). If the second is missing the verifier still works and
   silently reports nothing.
7. End-to-end: opt in with your own key, send one bad request with `agent_ip`, query today's
   `TELEMETRY#<date>` partition, then delete the test row with the deletion tool.

## 5. For Muse: the console toggle (paste as is)

> Add a **Verifier telemetry** setting to the verifiers settings area (TAP, PAP, x401). Keep it
> separate from the MCP firewall telemetry tab. Copy changes and one control only, no layout
> change elsewhere.
>
> **Control.** One OFF/ON toggle, default OFF, never pre-ticked. Under it show "Last changed"
> with the time returned by the API (blank until first changed).
>
> **Backend.** Call `GET` and `POST https://api.relayshield.net/v1/verifiers/config` from your
> SERVER with the customer's key in `X-RS-API-KEY`. POST body: `{"telemetry_opt_in": true}` or
> `false` (a JSON boolean, nothing else is accepted). GET returns
> `{"ok": true, "data": {"telemetry_opt_in": bool, "changed_at": "..."}}`. The endpoint has no
> CORS, so do not call it from the browser.
>
> **Heading:** "Share threat signals from blocked attacks (optional)"
>
> **Body:** "Off by default. When on, each time one of your verifiers rejects a request we record
> the reason, a one-way hash of the agent's identifier, and the network prefix of the agent's
> address if you pass it to us. This helps us spot attacks that hit more than one customer and
> improve detection for everyone. Nothing is recorded for accepted requests. Turn it off any
> time. Entries are deleted after 90 days."
>
> **"Recorded when on" list (exactly these):** reason for the rejection; one-way hash of the
> agent's identifier; network prefix of the agent's address, only if you send it; which verifier
> rejected it and when; for x401, a one-way hash of the credential issuer; a short one-way hash
> of your API key so entries can be deleted on request.
>
> **"Never recorded" list (exactly these):** transaction amounts; merchants; customer or
> cardholder data; anything about the person in an x401 credential; the full agent identifier;
> full IP addresses; the contents of the request; your API key.
>
> **Do not** write "anonymous" or "anonymized", do not say a hash "cannot be reversed", and do
> not mention corpus review, human approval, or other customers seeing your data. Link
> "Privacy policy" to https://privacy.relayshield.net (section 13).

## 6. For Muse: what the x401 verifier must do to plug in

Call this after the final verdict, and never let it affect the verdict:

```python
import relayshield_verifier_telemetry as vt
vt.maybe_report("tap+x401", verdict, api_event, request, issuer=issuer_did)
```

`verdict` needs `.decision` and `.reasons` (or a dict with those keys). Use the reason
`mandate_scope_exceeded` for a scope failure so it is recorded as `mandate_exceeded`.
`api_event` is the Lambda event of the call to us (it carries the customer's key), `request` is
the agent's request. Do not pass the agent's headers as `api_event`. Put the `import` inside a
guarded helper, as `_report_rejection` does in the TAP verifier, so a package missing the file
cannot break verification. Use the verifier type `x401` for x401-only and `tap+x401` for both.

## 7. UPDATE 2026-10-16: x401 RECONCILED WITH THE TELEMETRY HOOK

Muse's x401 work (recovered from a stash onto branch `x401-wip`, commit `10c29815`) is merged into
`claude/ecstatic-davinci-wh8xxr` and fixed. Its unrelated landing-page and MCP-proxy edits stayed on
`x401-wip` and are NOT on this branch.

**What was wrong with it as committed, all found by running it:**
1. A rejected x401 request returned a `Verdict` object, not an HTTP response (a 502 in production).
2. The transaction was read from fields a proxied event does not have, and every mandate check was
   skipped when its transaction value was empty, so a mandate was verified against nothing.
3. A `null` `headers` crashed the handler.
4. The issuer registry was `{}` with a TODO, so every presentation failed as "unknown issuer".
5. A missing `x401_verifier.py` in the zip took down TAP verification as well.
6. `nan` passed an amount ceiling, and an unreadable `validUntil` meant the mandate never expired.
7. The token's own `alg` header chose the scheme for an issuer's key.
8. **Pre-existing, not Muse's: `_pss_verify` rejected EVERY valid RSA-PSS (PS256) signature**
   (the leading-bit check shifted the wrong way). TAP requests signed with PS256 could never have
   been accepted. The TAP test for it allowed either outcome. Fixed and tested on four modulus sizes.

**How a request is read now.** The agent's `PROOF-PRESENTATION` header comes from
`request["headers"]`, exactly where the TAP signature headers are. The transaction being authorised
is `request["transaction"]` = `{amount, currency, merchant, action_category, agent_id}`, with
`agent_id`, `merchant_domain` and `authority` on the request used when it omits them. A constraint
the mandate sets that the transaction does not supply FAILS. **Merchants must therefore send a
`transaction` object**, and the API docs for the verifier need to say so.

**Verdicts.** TAP only: unchanged. Presentation only: x401 decides. Both: both must accept; any
reject wins, then any review. An empty registry or a missing module is a `review`, never an accept
and never reported as an attack.

**ANDREW DECIDES: the trusted-issuer registry.** It is `x401_issuers.json` beside the module (ships
`{"issuers": {}}`), or the `X401_TRUSTED_ISSUERS` environment variable holding the same JSON. Each
entry is issuer id -> a public JWK (Ed25519 `OKP` or `RSA`; RSA keys verify PS256 only). Until it has
entries every presentation is a `review`. Which issuers to trust is a business decision; Proof's
published key is the obvious first entry, and it should be read from Proof, not from this repo.
**The zip must contain `relayshield_tap_verifier.py`, `x401_verifier.py`, `x401_issuers.json` and
`relayshield_verifier_telemetry.py`.**

**Still open, not fixed:**
- Replay protection is an in-memory dict per Lambda container. It does not stop a replay that lands
  on another container. It needs a DynamoDB nonce store, for TAP and x401 alike.
- A credential with no `exp` is accepted forever. Recommend requiring `exp`.
- `committed lambda_handler passes no ti_screen`: TAP does no threat-intel screening on main.
- The mandate's `agent` is compared with a merchant-supplied `agent_id`, not cross-bound to the TAP
  signing key. Binding them needs a defined mapping from the Visa key id to the mandate's agent.
- Landing-page edits on `x401-wip` say "700K+ threat indicators" and sell a PAP verifier; neither
  has code behind it in this repo.
