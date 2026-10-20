# Proof x401 Verifier Enrollment Request (DRAFT)

To: Proof x401 team (via dev.proof.com contact)
From: Andrew Gibbs, RelayShield
Subject: x401 Verifier Enrollment - RelayShield (Sandbox)

Hello,

We're implementing an independent x401 verifier for RelayShield's agent verification API and would like to enroll in your sandbox environment.

**About us:**
- Company: RelayShield (threat intelligence for AI agents)
- Domain: relayshield.net
- Use case: Merchant-side verification of agent credentials via x401

**What we're building:**
An x401 relying party (draft 0.2.0) that verifies Proof-issued human identity credentials as part of our TAP/PAP agent verification flow. Our verifier is already implemented; we need to complete trust configuration and end-to-end testing.

We saw today's Money20/20 announcement of the Proof + Circle demo (x401 identity + x402 USDC payments from a Circle Agent Wallet). We're building the verifier side of that same flow, which is why we're reaching out now.

**What we need:**
1. Sandbox verifier enrollment (via the registration path at proof.com/x401)
2. Proof's authoritative Root CA certificate (for X.509 chain validation)
3. The issuer identifier for human identity credentials from Proof's Cloud Wallet
4. Confirmation on whether you publish a JWKS endpoint, use x5c, or another mechanism per artifact
5. Any issuer metadata or certificate discovery endpoints

**Our verifier info:**
- Client ID Metadata Document will be hosted at: https://relayshield.net/.well-known/x401/cimd.json
- Contact email: [Andrew to fill]

I have a verified Proof digital ID (IAL2, holder since Oct 18) that I can use for end-to-end testing.

We're ready to generate our P-256 verifier key pair and complete the enrollment steps. I also noticed you're running x401 developer sessions at Money20/20 (Booth #5069) through Oct 21 - happy to connect there if that's easier.

Thanks,
Andrew Gibbs
RelayShield

---

# RelayShield x401 Implementation Plan

## Current State
- ✅ x401 relying party implemented (draft 0.2.0, OpenID4VP 1.0)
- ✅ TAP verifier integration working (PROOF-RESPONSE triggers x401 path)
- ✅ Authorizer fixed and deployed
- ✅ Andrew's Proof digital ID verified (IAL2)
- ❌ Issuer registry empty (needs Proof's trust material)
- ❌ No x401 policy configured
- ❌ Not enrolled as Proof verifier

## Phase 1: Trust Configuration
1. Obtain Proof's Root CA certificate from dev.proof.com
2. Update `x401_issuers.json` schema to support X.509 trust anchors:
   ```json
   {
     "issuers": {
       "proof": {
         "issuer_id": "https://proof.com/issuers/human-id",
         "trust_anchor": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
         "type": "x509"
       }
     }
   }
   ```
3. Update verifier to validate X.509 chains against the trust anchor

## Phase 2: Verifier Enrollment
1. Generate P-256 key pair for RelayShield verifier
2. Host CIMD at https://relayshield.net/.well-known/x401/cimd.json
3. Submit enrollment request to Proof (draft above)
4. Complete sandbox enrollment

## Phase 3: E2E Testing (Sandbox)
1. Configure x401 policy for TAP verifier
2. Initiate challenge from RelayShield API
3. Present credential from Proof Cloud Wallet
4. Verify signature chain and claims
5. Confirm accept/reject logic

## Phase 4: Production
1. Complete production enrollment
2. Switch to production trust anchors
3. Deploy updated verifier
4. Announce x401 capability

## Blockers
- Proof's Root CA certificate (need from docs or enrollment)
- Enrollment approval timeline (unknown)
- Issuer identifier confirmation
