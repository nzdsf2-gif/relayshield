# x401 + TAP announcement pack, 2026-10-16

Three things in this file: where to contact Proof and what to say, the summary for Muse, and the
list of claims the announcement can and cannot make today.

## 1. Proof: where and what

**Where.** The x401 page links a "NOW LIVE" contact form at <https://www.proof.com/contact-x401>.
UNVERIFIED: this container cannot open proof.com, so the form's fields and its confirmation step are
not known. The contributor list is said to be at <https://x401.id> (also unread). If the form has a
free-text box, paste the short version below. If it has only fixed fields, use the short version in
the message field and send the questions to the address the confirmation page names.

**Short version (fits a message box):**

> Subject: x401 relying party built, asking for issuer details to test against
>
> We are RelayShield (api.relayshield.net). We built an x401 0.2.0 / OpenID4VP 1.0 relying party and
> run it next to our TAP agent verifier. It composes a signed request (client_id
> decentralized_identifier:did:web:api.relayshield.net), validates dc+sd-jwt and jwt_vc_json
> presentations, enforces DCQL claim values itself, checks status-list revocation and binds the
> credential to the TAP-authenticated agent. We have tested it against our own simulated issuer and
> wallet only. We would like to test against Proof's credentials and would be grateful for: (1) the
> issuer identifier and a JWKS or key we can trust for the Proof person credential and for the
> Business Certificate; (2) the credential type or vct and claim names, including the assurance level
> claim; (3) whether signatures are plain JWS (ES256, EdDSA, PS256) or an x5c chain; (4) a sandbox
> issuer or test credentials; (5) any conformance tests or a reference wallet. We will not list any
> issuer as trusted until you give us its keys. Andrew Gibbs, andrew@relayshield.net

**For a follow-up:** add that the code is not open source today, that it refuses mso_mdoc, ldp_vc,
encrypted responses and token exchange with a named error, and that wallet acceptance of a did:web
client_id is the thing we most want to test.

**What it must NOT say:** that we are conformant, certified, or listed by Proof; that Proof's key is
trusted; any customer or volume figure.

## 2. Summary for Muse

> **What was built.** The x401 verifier on branch x401-wip targeted the old 0.1.0 draft
> (PROOF-PRESENTATION). It has been replaced by an x401 0.2.0 relying party built on OpenID4VP 1.0:
> the verifier composes a signed request (JAR, typ oauth-authz-req+jwt, ES256, did:web client_id),
> the agent hands it to the wallet unchanged, and the wallet's response comes back in PROOF-RESPONSE.
> Modules: x401_jose.py (JWS, ES256 / Ed25519 / PS256 in pure Python), x401_rp.py (request
> composition and credential validation), x401_net.py (SSRF-guarded fetch for status lists and
> result URIs), wired into relayshield_tap_verifier.py so TAP authenticates the agent first and the
> credential is checked second; both must accept.
>
> **Validated:** nonce HMAC, expiry, route and method binding, single use (DynamoDB conditional put);
> audience; credential signature against a registry key; issuer allowlist; vct; exp required;
> selective-disclosure digests; key-binding JWT (nonce, aud, sd_hash); holder consistency; DCQL
> claim paths and values enforced by us; claim_sets; credential_sets; Token Status List revocation
> (fails closed); agent binding to the TAP key id. Over-shared claims are never returned.
>
> **Refused with a named error:** mso_mdoc, ldp_vc, encrypted responses, OAuth token exchange,
> federation / ETSI TL trust resolution, JWS JSON serialisation.
>
> **State.** Hand-deployed to relayshield-tap-verifier on 2026-10-16. The signing key is in Secrets
> Manager (relayshield/x401_verifier_key) and the public half is served at
> https://api.relayshield.net/.well-known/did.json. The issuer registry and policy list are empty by
> design, so today every presentation is refused or sent to review; nothing is accepted until a
> trusted issuer is added. Not tested with a real wallet or issuer. VERIFIER_NONCE_TABLE is not yet
> set, so replay protection is per container until it is.
>
> **For the Verifiers tab:** the x401 flow is driven by the merchant's request fields plus
> x401_policy; `{"action": "x401_challenge", "x401_policy": "...", "path": "...", "method": "..."}`
> returns only the challenge. Do not describe the product as accepting credentials from any named
> issuer, and do not list "x401 mandate verification" or any issuer name until it is true.
> Tests: test_x401_jose, test_x401_rp, test_x401_lambda, test_x401_integration, test_x401_ops_tools,
> test_x401_privacy, test_package_verifier. Demo: python3 tools/x401_demo.py.

## 3. Announcement claims

**Can say, because it ran today:**
- RelayShield runs an x401 0.2.0 / OpenID4VP relying party alongside its TAP agent verifier.
- Verified end to end with a simulated issuer, wallet and agent, including six attack cases (replay,
  a minor's credential, a proof harvested for a phishing origin, a forged issuer, a different agent
  presenting someone else's proof, and the same proof used on another route).
- Requests are signed and discoverable at a did:web identity.

**Cannot say yet:**
- That any real issuer, including Proof, is supported or trusted. The registry is empty.
- That any real wallet works with it. Wallet acceptance of a did:web client_id is untested.
- "Conformant", "certified" or "listed".
- That the testkit issuer proves anyone's identity. It proves the mechanics only, and the demo
  must be labelled as using a simulated issuer.

**The testkit issuer.** Use `python3 tools/x401_demo.py` for the demo. It generates a fresh key
every run and registers nothing live. Do not put a testkit key in the live issuer registry: its
private half would be in a public repository, so anyone could mint a credential the live verifier
would accept. If a live demo route is wanted, it needs its own policy that guards nothing real, and
that is a separate decision.
