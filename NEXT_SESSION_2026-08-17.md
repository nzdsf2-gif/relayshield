# Next session: 2026-08-17

**Read `memory/project_session_snapshot_2026-08-16.md` first.** Then
`project_corpus_composition_and_provenance.md` before writing any copy about scale, sourcing or speed.

**Verify before trusting anything below.** This file is history the moment it is written.

---

## Top 15

### The two that are live and wrong

**1. Strip the 24-72h lead-time claim.** *"Telegram-sourced indicators typically surface 24 to 72
hours ahead of public feeds"* is served right now at `api.relayshield.net/guides/elastic-security` and
sits in ~30 files. Founder approved removal. **A technical buyer can disprove it with one query.**

**Trap:** several hits are a different, valid claim about attacker behaviour and must not be swept up:
`relayshield_domain_monitor.py:427`, and the Telegram and WhatsApp webhooks, all say *"from this
domain within the next 24-72 hours"*. Replace individually.

Live code first: `relayshield_api.py` (guide HTML and endpoint descriptions),
`relayshield_developer_signup.py:2239`, `relayshield_openapi_spec.py:2559`,
`elastic_security_integration_guide.md`, `blog_source/elastic-security-*.md`. Then
`python3 build_guides.py` and redeploy the three-file package. Drafts, published posts, solution
briefs and `generate_pdfs.py` are positioning and a separate founder decision.

**2. METRICS-2: the published IOC count is sightings, not indicators.** We publish "5.6M+ indicators"
on 11 surfaces. Measured exhaustively: **489,974 distinct**, 11.7 sightings each. Correct it together
with #1 and the provenance wording, in one pass, not three.

### Verify what was deployed but never confirmed

**3. Did the intel monitor extraction fixes work?** Deployed 2026-08-16 23:17 UTC, **unverified**.
Check the next Telegram digest for the new **Media seen** block. If it shows photos and documents
arriving while `Images OCR'd` and `ZIP/RAR archives parsed` stay 0, extraction is still broken. If it
says "No attachments seen this run", the channels genuinely do not post them. **Until now every 0 was
ambiguous between those two**, which is how three dead paths went unnoticed for months. Also check
`relayshield_marketplace_listings` for rows.

**4. Re-verify the TAXII feed still terminates.** The fix was confirmed once. Confirm `more=False` is
still reached and `path=feed` still serves with no fallback, now that the QA workspace is gone and
Elastic or others are the only consumers.

### MS-3, closest to shipping

**5. Register an Entra Application ID.** We do not have one. Security Store's technical configuration
needs it alongside Tenant ID `4abf9bc4-9257-4c71-8b6b-a8afc934b4a5`. **Founder action.**

**6. Create the SaaS offer** in Partner Center using the Commercial Marketplace enrolment already
held. Package is built and zipped at `relayshield_agent_package.zip`. Full walkthrough in
`security_store_agent/README.md`. **Founder action.**

**7. RISK: does Security Copilot accept OpenAPI 3.1?** Unresolved and it could block the import. Ours
is 3.1; Power Platform rejects anything above 2.0. If it fails,
`tools/build_powerplatform_connector.py` already converts and can be repointed at the five agent
operations, but the result needs hosting at a public URL.

### Corpus, the strategic thread

**8. Fix the polling cadence.** `rate(6 hours)` with a 6h10m lookback. A product positioned on speed
cannot poll its differentiated source four times a day. Tier it: 15 minutes for genuine marketplace
channels, 6 hours for the CTI aggregators, to limit flood-wait exposure.

**9. Cull channels on measured yield.** 73 of 90 produce zero IOCs. Per-channel instrumentation went
live 2026-08-16, so after about a week this becomes data instead of guesswork. Replace from the
verified Tier 2 list.

**10. Test whether "exclusive" means exclusive.** 99.4% of channel content appears in no feed **we
ingest**. Whether it exists on OTX or VirusTotal is **untested**. Sample 100 and check **before**
building a pitch on exclusivity.

**11. Decide the corpus growth strategy.** Adding commodity feeds adds volume and zero
differentiation. The 1.67% is the only part that matters commercially.

### Microsoft, follow-on

**12. MS-4 certification.** Deferred deliberately. Four prerequisites in
`powerplatform_connector/CERTIFICATION_PREP.md`: enrol in **Microsoft 365 and Copilot** (separate from
Commercial Marketplace), 120 successful test calls needing a metered key, rebuild the connector inside
a solution, and an Azure blob SAS URI. Icon is **done** and passes all 11 rules.

**13. Chase `Azure/Azure-Sentinel#14924`.** One-line fix to a Microsoft rule that matches nothing.
Landing it before our own `Solutions/RelayShield` PR is the point.

### Everything else

**14. The Kraken/Privy blog post is ready to publish.** `blog_source/your-wallet-provider-had-a-vendor-and-that-vendor-had-a-dashboard.md`,
dated 2026-08-17, with its own checklist and distribution plan. **Checklist item 3 verified**:
`@virtuals-protocol/acp-cli` still lists `@privy-io/node`. Items 1 and 2 are the founder's: re-read
the Kraken notice against the post, and check whether Privy published its own statement.

**15. Ansible Galaxy namespace.** Still does not exist. The two emails were moderation events, not
namespace creation. Everything else is done and the tarball is staged at
`publish_ready/relayshield-security-0.1.0.tar.gz`.

---

## Blocked on others

XSOAR (email sent to `techpartners@paloaltonetworks.com`), Ansible Galaxy namespace (staff),
Partner Center company verification, `Azure/Azure-Sentinel#14924` review.

## Environment

- **`az` CLI is NOT installed.** Every Azure action needs the founder in the portal.
- **`python3.11`** is the only interpreter with boto3; **`/usr/bin/python3`** the only one with PyYAML.
- `relayshield-api` is a **three-file deploy**.
- `relayshield-breach-check-role-1sapnwdl` has hit the **10,240-byte inline policy limit**; new grants
  must be managed policies.
