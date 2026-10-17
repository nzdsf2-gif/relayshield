# RelayShield x401 relying party

Status 2026-10-16: **built, tested and hand-deployed to `relayshield-tap-verifier` (steps 1-6 below ran). `VERIFIER_NONCE_TABLE` is not yet set, no policy or trusted issuer exists, and nothing has been tested against a real wallet or a real issuer.**
Every signature in the tests is real (ES256, Ed25519, PS256); the only things stubbed are the clock and the network fetch.

## What it is

Together with the existing TAP verifier this is a full stack for agent commerce:

| Layer | Question answered | Mechanism |
|---|---|---|
| TAP | Which AI agent is calling, and is the request really from it? | RFC 9421 HTTP message signature, Ed25519 / PS256 |
| x401 | Which human stands behind it, and do they hold the credential this route requires? | x401 0.2.0 + OpenID4VP 1.0 over the DC API |
| Binding | Is the credential being used by the agent that was authorised to carry it? | Agent id (TAP key id) carried into the x401 result check |

RelayShield is the **relying party**: it composes the signed OpenID4VP request, receives the wallet's response through the agent, and validates it. It never sees a wallet and never holds the person's key.

## Flow

1. The agent calls the merchant's route. The merchant sends the request to the verifier Lambda.
2. TAP authenticates the agent. No proof yet, so the verdict is `proof_required` and the Lambda answers **401** with a `PROOF-REQUEST` header (a signed OpenID4VP request, `client_id` = `decentralized_identifier:did:web:api.relayshield.net`, `expected_origins` from the policy).
3. The agent passes the request to the person's wallet unchanged. The wallet checks our signature against `/.well-known/did.json`, asks the person, and discloses only what the DCQL query asked for.
4. The agent retries with `PROOF-RESPONSE`. The Lambda re-verifies TAP, then validates the credential and returns the combined verdict. On accept, `claims` holds exactly what the policy requested.

Merchant request to the Lambda (JSON, as for TAP): the signed request fields (`authority`, `path`, `method`, `headers`) plus `x401_policy`. To only obtain a challenge: `{"action": "x401_challenge", "x401_policy": "...", "path": "...", "method": "..."}`. `x401_route` / `x401_method` override the bound route.

## What is validated

Nonce HMAC and expiry, route and method binding, single use; audience (`origin:<origin>`, or `client_id` for relayed delivery); credential signature against a **trusted issuer key from the registry**; issuer on the policy's allowlist; `vct`; `exp` required, `nbf`/`iat`; selective-disclosure digests with no unmatched disclosures; key binding JWT signature, `nonce`, `aud`, `sd_hash`, `iat`; holder consistency across credentials; DCQL claim paths and **values enforced by us** (wallets only treat values as best effort), `claim_sets`, `credential_sets`; Token Status List revocation (fails closed, URI must match an allowed prefix); result-URI results (prefix allowlist, SSRF-guarded fetch); agent binding. Over-shared claims are never returned.

## Not supported (refused with a specific error, never silently accepted)

`mso_mdoc` (mobile driving licences), `ldp_vc`, encrypted responses (`dc_api.jwt`), OAuth token exchange / Verification Tokens, `openid_federation` / ETSI TL / `aki` trust resolution (trust is the policy allowlist plus registry keys), JWS JSON serialisation. We do not issue a result-drop endpoint, though a result URI supplied by a wallet is dereferenced under the allowlist.

## Configuration (environment variables)

| Variable | Purpose |
|---|---|
| `X401_SIGNING_JWK` | Private ES256 JWK that signs requests. Secret. Public half is published in `relayshield_x401_pubkey.py` |
| `X401_KID`, `X401_CLIENT_ID` | Key id and `client_id` (defaults to the did:web above) |
| `X401_NONCE_SECRET` | HMAC key for stateless nonces (falls back to the signing key) |
| `X401_POLICIES` | Policies JSON (overrides `x401_policies.json`) |
| `X401_TRUSTED_ISSUERS` | Issuer registry JSON (overrides `x401_issuers.json`) |
| `VERIFIER_NONCE_TABLE` | DynamoDB table for single-use enforcement across containers. **Set last.** |
| `VERIFIER_TI_SCREEN` | Enables threat-intel screening of the request |

An invalid policy is dropped, never loosened. A key containing a private member in the issuer registry is refused.

## Deployment order (nothing below has been run)

1. Merge and push. Deploy the privacy Worker (section 14 describes this processing).
2. `AWS_PROFILE=relayshield python3 tools/generate_x401_verifier_key.py` (dry run, then `--apply`).
3. Commit the printed public JWK into `relayshield_x401_pubkey.py`; push (deploys `relayshield-api`, which serves `/.well-known/did.json`). Verify with `curl https://api.relayshield.net/.well-known/did.json`.
4. `AWS_PROFILE=relayshield python3 tools/grant_x401_secret_access.py --function <name>`.
5. Create the nonce and telemetry tables (`tools/setup_verifier_nonces_table.sh`, `tools/setup_verifier_telemetry_table.sh`), then grant the verifier role PutItem on both with `AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/grant_verifier_table_access.py --function relayshield-tap-verifier` (dry run, then `--apply`). Not `grant_breach_cache_access.py`: that edits a shared policy the verifier's own role does not carry.
6. Read drift first: `sh tools/handler_drift.sh relayshield_tap_verifier.py`. Then `python3 tools/package_verifier.py` and hand-deploy `dist/verifier.zip` (handler `relayshield_tap_verifier.lambda_handler`). The function is not in `LAMBDA_MAP`, so a push alone deploys nothing.
7. Set `VERIFIER_NONCE_TABLE` last, merging into the existing environment (a bare `--environment` replaces it).
8. Populate `x401_policies.json` and `x401_issuers.json`. **These are business decisions: which credentials, which issuers are trusted. No issuer key may be invented.**

## Honest limits

- Not tested with a real wallet or issuer; wallet acceptance of a `did:web` `client_id` is unverified.
- Across Lambda containers replay protection needs `VERIFIER_NONCE_TABLE`; without it the store is per-container.
- Ed25519 verification is pure Python and slow (hundreds of ms).
- `safe_fetch` resolves then connects, so a DNS-rebinding race remains theoretically possible.
- The TI screen needs `relayshield_api` in the package and IAM for its lookups.

## Try it

`python3 tools/x401_demo.py` runs the whole flow, with a simulated issuer, wallet and agent, and six attacks (replay, minor, phishing origin, forged issuer, wrong agent, wrong route).
Tests: `test_x401_jose`, `test_x401_rp`, `test_x401_lambda`, `test_x401_integration`, `test_x401_ops_tools`, `test_x401_privacy`, `test_package_verifier`.
