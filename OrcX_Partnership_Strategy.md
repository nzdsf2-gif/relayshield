# OrchestrateX (OrcX.ai) — Partnership Strategy

**Contact:** Former partner/colleague (friendly relationship)
**Next call scheduled:** Thursday 2026-07-16 — Gary + his CTO partner joining this time
**Their site:** orcx.ai
**Product:** "Quantum" — Enterprise AI Control Plane

---

## What OrcX Does

OrchestrateX governs enterprise AI deployments at runtime. Their platform monitors and controls live AI systems across:
- Voice AI
- Agent Copilots
- Workforce Systems / Contact Centers
- CRM and AI Assistants
- Session Intelligence

**Core capabilities:**
- **Runtime Governance** — continuous oversight of AI interactions in live environments
- **AI Interaction Traceability** — 100% visibility into AI session flows and decision chains
- **Operational AI Supervision** — detect inefficiencies, monitor AI behavior in production
- **Unified Control Plane** — centralize governance across fragmented AI systems

**The problem they solve:** "The control gap in enterprise AI — the growing distance between how fast AI acts and how fast humans can respond."

**Target customer:** Enterprises running production AI agents at scale (contact centers, CRM, copilots). Likely mid-market to enterprise, not SMB.

---

## Why the Partnership Fit Is Strong

OrcX governs *what AI agents do* at runtime. They have no signal on *whether the identities and credentials those agents act on behalf of are compromised.*

A stolen session cookie, exposed API key, or breached user credential feeding into an AI agent workflow is invisible to a runtime governance layer — and potentially catastrophic (an AI agent with a hijacked session has full account access with no 2FA prompt).

**RelayShield is the identity and credential security layer underneath the AI governance layer.**

---

## Specific Integration Points

### 1. NHI Exposure — AI agents use API keys
`POST /v1/metered/nhi-exposure` detects API keys and tokens exposed in criminal stealer logs.

Enterprise AI agents call dozens of third-party APIs (CRM, data warehouse, identity providers). If any of those API keys appear in stealer logs, the AI agent is operating on compromised credentials. OrcX's runtime governance layer has no way to know this — RelayShield does.

**Integration:** OrcX calls `/v1/metered/nhi-exposure` on onboarding to audit the API keys their customers' AI agents use, and periodically to detect new exposures.

### 2. Session Risk — stolen sessions in AI workflows
`POST /v1/metered/session-risk` detects stolen session cookies in criminal archive dumps.

OrcX has a "Session Intelligence" module. RelayShield's session hijack detection (INTEL-5) extracts stolen session cookies from Telegram stealer archives. These two capabilities are **complementary** — OrcX traces AI sessions forward (what happened), RelayShield detects stolen credentials that could compromise those sessions upstream.

**Integration:** When OrcX detects an anomalous AI session, they can call `/v1/metered/session-risk` against the user's email to check whether active stolen sessions exist in the criminal corpus.

### 3. Identity Risk Score — score the humans AI acts on behalf of
`GET /v1/metered/identity-risk-score` returns a 0–100 domain security credit score across 6 dimensions: breach exposure, infostealer density, IOC presence, ransomware victim, active session exposure, CVE exposure.

**Integration:** OrcX scores the identity risk of users being served by enterprise AI — a user with a score of 20/F should trigger elevated AI session scrutiny or MFA re-challenge.

### 4. Supply Chain Risk — vendor APIs called by AI agents
`POST /v1/metered/supply-chain` returns composite breach + stealer + dark web risk scores for vendor domains.

Enterprise AI agents call third-party vendor APIs constantly. If a vendor is breached, the AI agent's calls to that vendor could be compromised. OrcX can run periodic supply chain sweeps against their customers' integrated vendor lists.

**Integration:** OrcX calls `/v1/metered/supply-chain` against the third-party API domains their customers' AI agents call, surfacing vendor risk before it propagates into AI-driven workflows.

### 5. IOC Pivot + Bulk Lookup — AI security enrichment pipelines
`POST /v1/metered/bulk-ioc` and `POST /v1/metered/ioc-pivot` for log enrichment.

OrcX logs 100% of AI interactions. Those logs contain IPs, domains, and URLs. Enriching those logs with IOC status (is this domain malware C2?) is a natural fit.

**Integration:** OrcX enriches AI session logs with RelayShield IOC data via bulk lookup — flagging sessions that interact with known-malicious infrastructure.

---

## Does Identity Risk Scoring Require Code Changes?

**No.** Our existing endpoints work as-is for OrcX's use cases:

- `/v1/metered/identity-risk-score` takes `domain` — works for any enterprise domain
- `/v1/metered/nhi-exposure` takes `domain` and `emails` — works for AI agent key scanning
- `/v1/metered/session-risk` takes `email` — works for per-user session checks
- `/v1/metered/supply-chain` takes `vendor_domains[]` — works for API vendor scanning

The only enhancement worth considering: a **batch identity risk score** endpoint (`POST /v1/metered/bulk-identity-risk`) that accepts up to 20 domains and returns scores for all — useful for OrcX scoring all users in an enterprise AI deployment in one call rather than N sequential calls. This would be a minor addition to `relayshield_api.py`, ~30 lines.

---

## Partnership Structure to Propose

**Option A — Referral/RevShare (easiest to close)**
OrcX refers customers who need identity/credential security. RelayShield pays 20% of Year 1 subscription revenue. No engineering required on OrcX's side.

**Option B — Embedded Integration (stronger)**
OrcX embeds RelayShield API calls into their platform's onboarding audit and ongoing monitoring. RelayShield provides wholesale API rate (e.g., 40% discount off retail). OrcX marks up as part of their "AI Security Posture" offering. Co-marketing: "Powered by RelayShield Identity Intelligence."

**Option C — Joint GTM**
Joint case study: "How OrcX + RelayShield close the AI governance gap." Target shared accounts — enterprises evaluating AI governance who also need identity security. Mutual warm intros.

---

## Buy vs. Build — For the CTO

Added 2026-07-11 ahead of the call with Gary + his CTO partner (Thursday 2026-07-16). The founder knows this CTO from before and flagged him as the type who needs convincing on *why RelayShield vs. build it in-house* — a technical person will see through generic "we're specialized" claims, so these are the specific, defensible reasons, not marketing language.

**1. The hard part isn't the API, it's the ongoing data operation.**
Anyone can write a scraper. What's actually hard is *sustained* collection: RelayShield monitors 37+ criminal Telegram channels for stolen session cookies and infostealer log dumps, maintains a 2.28M+ item IOC corpus, ingests MITRE ATT&CK (groups, techniques, and software/malware — 800+ entries), a 4,500+ family malware taxonomy (Malpedia), CISA KEV/EPSS scoring, and ransomware leak-site tracking — all correlated and updated daily. This isn't a weekend build. It's the accumulated output of an ongoing operation, and every piece of it breaks and needs re-fixing on its own schedule — we hit three silent upstream schema changes in the last month alone (GoPlus's NFT security API, MITRE's STIX format, a Payment Link config gap) that required real debugging, not just noticing a cron job failed.

**2. Access isn't code.** Monitoring criminal Telegram marketplaces for stolen-session and stealer-log data requires actual OSINT tradecraft — knowing which channels matter, avoiding getting banned or fed disinformation, and doing it without tipping off the operators. That's a standing capability, not a library you `pip install`.

**3. The IP that matters is the correlation.** A single IOC feed is a commodity — dozens of vendors sell one. RelayShield's differentiator is the coordinated-attack-detection correlation engine that fuses breach exposure, infostealer activity, session hijack signals, IOC presence, ransomware history, and CVE/KEV exposure into one risk signal — recognizing when independent-looking signals are actually the same campaign, across 11 documented attack chains. A provisional patent application covering this correlation engine has been drafted and is prepared for attorney filing — **do not say "patent-pending" or "patent-filed" on the call; nothing has been filed with the USPTO yet.** If asked directly, the honest answer is "we've drafted the filing and are moving toward submission" — not a claim of issued or pending protection. Building a comparable feed is possible; building the correlation layer on top of it, well enough to be worth patenting, is the actual hard problem.

**4. Opportunity cost, not just dollar cost.** The real buy-vs-build comparison isn't "our wholesale rate vs. free" — it's wholesale rate vs. permanent headcount (someone has to own this pipeline forever, since threat intel decays fast if it isn't fresh) that OrcX would otherwise spend advancing Quantum's actual moat: runtime governance and AI interaction traceability. Every engineering hour spent maintaining a Telegram stealer-log scraper is an hour not spent on the product OrcX is actually trying to win with.

**5. The honest reframe if he pushes back:** ask him directly — *"Is verifying whether a session cookie showed up in a criminal stealer dump part of your competitive moat as a governance platform, or is your moat the runtime traceability and control-plane logic itself?"* If it's the latter (it almost certainly is), then this is infrastructure to buy, not a capability to build — same logic as not rolling your own TLS stack.

---

## Hard Data Points for the Call

Concrete, verifiable numbers — not marketing rounding — for when the CTO wants specifics, not narrative.

**Scale (as of 2026-07-11):**
- 2.28M+ IOC indicators (domains, IPs, URLs, hashes), 20+ authoritative threat intel feeds
- 37+ monitored criminal Telegram channels for stolen-session and infostealer-log data specifically
- 4,500+ tracked malware families (MITRE ATT&CK software/malware objects + Malpedia taxonomy)
- 189 MITRE ATT&CK groups, 824 ATT&CK software/malware entries ingested
- 11 documented cross-signal attack chains in the correlation engine (identity-surface and identity×crypto-asset)

**Speed (the actual differentiator vs. detection-only competitors):**
- Infostealer log exposure detected 24–72 hours ahead of public breach databases — before session replay or credential stuffing begins
- Credential breach alerts fire within hours of indexing, not days
- Domain lookalike/typosquat alerts within hours of registration — before the phishing campaign using it launches
- SIM swap detected via real-time carrier query (Twilio Lookup v2), not batch/delayed polling

**Cost comparison (the buy-vs-build number to actually use):**
- Enterprise-grade SIM swap monitoring alone starts at $10K+/year from dedicated vendors — included at RelayShield's SMB-accessible pricing
- Session-hijack/AiTM detection (RelayShield's INTEL-5 capability) is comparable to SpyCloud's flagship offering at roughly 1/100th the price
- Wholesale API rate for OrcX: ~40% off retail (matches existing Option B terms) — vs. the realistic 6–12+ month, 1–2 dedicated engineer/analyst cost of reaching feature parity in-house, *plus* permanent ongoing headcount to keep it maintained (see Buy vs. Build point 1 — three separate upstream schema breaks required real debugging in the last month alone, not just noticing a cron job failed)

## What OrcX Gets by White-Labeling (Option B specifics)

- **Full wholesale API access** at ~40% off retail — same 24 endpoints covering breach, infostealer, SIM swap, session hijack, domain lookalike, OAuth exposure, and identity-risk scoring
- **True white-label available**: RelayShield branding suppressed entirely from API responses (error messages, field names) — OrcX's customers never see "RelayShield," only "Quantum" — or co-marketed as "Powered by RelayShield Identity Intelligence" if OrcX prefers the credibility signal instead
- **Fast to live**: no new infrastructure on OrcX's side — a flat monthly invoice (metering bypassed via a license flag, ~1 hour of RelayShield-side work) and a 2–3 page API license agreement, not a full enterprise MSA
- **Zero ongoing maintenance burden** shifts to RelayShield — OrcX consumes a stable API, never touches the Telegram-monitoring pipeline, the correlation engine, or the schema-drift firefighting that comes with owning threat intel collection
- **Differentiation for OrcX's own pitch**: "AI governance + identity/credential integrity" is a stronger, more complete story against other AI governance platforms than runtime traceability alone — this is a capability OrcX can point to in their own sales conversations without having built it

---

## Pitch for Thursday

> "You govern what the AI does. We secure the identities it acts on behalf of. No enterprise AI governance story is complete without credential and session integrity — and that's the exact gap we close. An AI agent operating on a stolen session cookie or compromised API key is invisible to your runtime governance layer until it's too late. We detect that upstream."

---

## On Friendly SMB Intros

Ask directly: *"Do you have 2-3 SMB contacts who'd be open to a quick 15-minute call on identity breach protection? Not a hard sell — just friendly ears."*

Frame it as a favour request, not a sales ask. His credibility as the referrer is worth more than any cold outreach.

---

## Build Requirements for Enterprise Licensing

If Gary moves forward, here's what needs to be built or agreed before go-live:

**1. Wholesale API Key — ~1 hour (low effort)**
Add a `platform_license: true` flag to the API key record in DynamoDB. `relayshield_api.py` checks this flag and bypasses Stripe metering entirely — usage is not reported to Stripe meter events. Monthly flat invoice sent manually instead. Rate limits elevated to match agreed call volume (e.g., 50K calls/month ceiling).

**2. SLA / Uptime Commitment — no build, just a document**
No formal SLA currently exists. For a $1,500+/month enterprise contract, OrcX will expect at minimum: 99.5% uptime commitment, response time SLA for P1 incidents (e.g., < 4 hours), and a status page. AWS API Gateway + Lambda gives ~99.95% uptime natively — formalising this is a document exercise, not an infrastructure change.

**3. White-Label Option — ~1 day (medium effort)**
Suppress "RelayShield" branding in all API responses (error messages, field names like `relayshield_*`, summary strings). Replace with OrcX branding or neutral language. Controlled by the `platform_license` key flag. Keeps RelayShield invisible to OrcX's end customers if they prefer. Optional — charge extra for this ($200-300/mo premium).

**4. Legal: API License Agreement — ~1-2 days (external)**
Simple 2-3 page document covering: permitted use, data handling, rate limits, SLA, IP ownership, termination. Not a full enterprise MSA. Can use a standard API license template as base. Should be reviewed by a lawyer before signing anything above $5K/year in contract value.

---

## Airgapped / Public Sector Deployment Model (IRS, SSA)

Gary's lead customers (IRS, Social Security Administration) run Sapient workforce management inside **airgapped environments — no direct internet API calls permitted.** Every integration point above (`/v1/metered/*`, live TAXII polling) assumes a real-time internet round trip. That assumption breaks here, so the delivery model has to change, not just the pricing.

### Why live API calls don't work
Federal airgapped enclaves (IRS/SSA-class) have no route to a public internet endpoint like `api.relayshield.net`. Any data entering the enclave has to cross a **cross-domain solution (CDS)** or a one-way data diode — hardware/software chokepoints (Owl Cyber Defense, Forcepoint, Fortress-class guards are common in federal environments) that inspect, sanitize, and one-way-transfer files on a schedule. Per-call metered API access is architecturally incompatible with this — there's no live call to make.

### Proposed model: scheduled batch export, not live polling
RelayShield already has the right shape of product for this — the STIX/TAXII 2.1 feed (`GET /v1/intel/taxii/*`, live) is a producer/consumer format built for federated distribution, not just live queries:

1. **Outside-the-gate collector** — OrcX (or their integrator) runs a lightweight process *outside* the airgap that pulls RelayShield's TAXII feed (or a purpose-built export) on a schedule — e.g. daily — pulling new IOCs, CVE/KEV updates, ransomware victim data, and ATT&CK mappings since the last pull.
2. **Package + sign** — Bundle the delta as a signed STIX 2.1 bundle (or flat JSON/CSV if the customer's CDS prefers simpler formats). Signing lets the CDS/guard verify integrity without needing to parse semantics.
3. **One-way transfer across the CDS** — The signed bundle crosses into the enclave through the customer's existing guard infrastructure — RelayShield never touches the classified/airgapped side directly, and never needs to. OrcX's in-enclave Sapient/governance dashboard ingests the bundle locally (flat file import, not API call).
4. **Local matching inside the enclave** — Once inside, OrcX's platform does IOC/CVE matching against their own logs entirely offline, using the imported corpus. No outbound call needed at query time.

This is the same pattern RelayShield already has on the roadmap as "Bulk S3/Kinesis MSSP feed" for MSSP continuous-enrichment customers — the airgapped case is a more constrained variant of the same delivery shape, not a new product.

### Commercial implication
This is **not a per-call metered relationship** — there's nothing to meter once the data is inside the enclave. It has to be a **flat bulk subscription** (matches the existing TI Starter $499/mo or TI Unlimited $999/mo structure, or a custom enterprise data-feed tier priced on corpus size/update frequency rather than call volume). Worth pricing this as its own SKU — e.g. "Federal/Airgapped Feed" — since the delivery engineering (export job, signing, format negotiation) is a one-time build, not incremental per-customer cost.

### Compliance reality check — say this on the call, don't let it surprise later
Actual production sale *to* IRS/SSA (as opposed to selling *through* OrcX, who already holds whatever authority-to-operate they have) almost certainly requires **FedRAMP** (or at minimum a FedRAMP-equivalent security assessment) for any component touching federal data, even indirectly via a data feed. RelayShield, as a small Lambda-based SaaS, is not FedRAMP-authorized and pursuing that authorization is a multi-month, non-trivial-cost effort — not something to commit to on this call. The realistic path: **RelayShield sits behind OrcX's existing authorization boundary** — RelayShield's feed is treated as a third-party data source that OrcX's already-authorized platform ingests and re-exports, the same way OrcX would treat any other threat intel vendor feed. Confirm this is how Gary is already thinking about it — if OrcX expects RelayShield to hold its own ATO, that's a different (much longer, much costlier) conversation.

### Questions to ask Gary on the call
- What format does their existing CDS/guard already accept for threat intel today (STIX/TAXII, flat CSV, something else)? Match that instead of inventing a new format.
- Does OrcX's platform sit fully inside the enclave, or do they have an unclassified staging tier we'd actually integrate with?
- Update cadence they need — daily, weekly? (Drives the export job design.)
- Do they need bidirectional (matches/alerts flowing back out), or is this one-way ingestion only? (One-way is far simpler and likely the realistic ask given the airgap.)
- Whose authorization boundary does the RelayShield feed sit under — confirm the FedRAMP point above explicitly rather than assuming.

---

## Call Notes — Jun 25 2026

- Gary agreed to schedule follow-up in a few weeks to pitch collaboration to his CEO
- Lead customers: **government/public sector** — Social Security Administration, IRS
- Use case: AI governance layer for **Sapient workforce management tool**
- OrcX has built a governance dashboard for AI runtime oversight
- **Key constraint: airgapped environments** — no direct internet API calls
- Private sector pipeline: **Citibank** (in discussions) — our solution plays naturally here
- Gary liked the concept of **partner guardrails** — verifying third-party tool identity security
- Next step: prepare CEO pitch deck + live demo of threat intelligence

## Action Items Post-Call

- [ ] Confirm OrcX target customer profile (enterprise only, or mid-market SMB too?)
- [ ] Ask if they have a developer API / integration layer we can target
- [ ] Explore Option B if he's interested in technical integration
- [ ] Get 2-3 SMB intro names if he's willing
- [ ] Follow up with MSP brief PDF + developer docs link
- [ ] If interest confirmed: scope platform_license flag build (~1 hr) and draft API license agreement

---

## Call Notes — Jul 16 2026 (Gary + CTO + CEO)

**Outcome: passed the first hurdle.** Call went well; the airgapped/CDS-collector pitch (lightweight collector outside the enclave, per the "Airgapped / Public Sector Deployment Model" section above) landed as intended — CEO engaged directly on FedRAMP/FIPS certification requirements, confirming the compliance framing above matches how they're actually thinking about it.

- **They likely don't have a collector built yet** — impression from the call is OrcX is working with an **SI (systems integrator) partner** who might already have this capability. Worth asking directly who that SI is and whether RelayShield should be looped in with them instead of/alongside OrcX building it themselves.
- **Target verticals expanding beyond government**: following the public-sector foothold, OrcX wants to move into other heavily regulated industries — **finance, banks, utilities.** This generalizes the Citibank pipeline noted 2026-06-25 from "one private-sector lead" to "a deliberate vertical strategy" — regulated-industry positioning (not just federal/airgapped) should now be a standing part of the pitch, not a one-off.
- **CEO described OrcX's internal object model**: UUIDs, context IDs, session IDs, Agent ID, login session, and employee IDs — this is their session/identity data architecture for Quantum's runtime governance layer.
- **New integration angle, raised by the CEO himself (not something we pitched)**: use RelayShield's **OAuth watchlist** as enrichment to their **policy engine at the session level**. This wasn't in the "Specific Integration Points" list above (which covered NHI exposure, session-risk, identity-risk-score, supply-chain, IOC-pivot/bulk-lookup) — add OAuth watchlist as integration point #6: OrcX's policy engine could call `/v1/metered/oauth-watchlist` to flag sessions tied to risky/over-privileged OAuth grants before applying session-level policy decisions.
- **Momentum context**: they are currently preoccupied with their lead customer (the IRS/SSA-class airgapped deployment) — not actively blocked, but not their top-of-mind priority right now either. The opportunity is to keep building on this call's momentum rather than waiting for them to circle back unprompted.

### Updated action items
- [ ] Ask Gary directly who the SI partner is and whether they already have (or are building) an outside-the-enclave collector
- [ ] Draft the OAuth-watchlist-as-session-policy-enrichment integration point as a concrete one-pager or API snippet, since the CEO raised it unprompted — strike while it's fresh
- [ ] Update the pitch deck/one-pager to explicitly include finance/banks/utilities as target verticals, not just government
- [ ] Propose a concrete next touchpoint (don't let momentum stall while they're focused on their lead customer) — e.g. a short follow-up doc or demo tailored to the OAuth-watchlist/policy-engine integration specifically

---

## Gary's Follow-Up (2026-07-23) — Embedding Security Into Quantum's Demo

Gary's actual ask, paraphrased from his email: OrcX hasn't fielded any security questions yet in AI governance conversations, but they know it's coming and want to "have something to show around security during demos." Explicitly **not** a production integration ask right now — he's clear that OrcX is heads-down on closing their first paying contract to avoid raising capital/diluting equity, and everything else (including this) is secondary to that until it lands. He wants to align on technical + commercial shape in the next 1-2 weeks.

**Read this correctly: he's asking for a demo asset, not a production contract.** Applying the existing Option B wholesale terms here would be a mismatch — see the commercial note below.

### Recommended demo narrative

Lean on the integration point the CEO raised unprompted on the Jul 16 call (OAuth watchlist → policy engine enrichment) — it's the freshest idea, already bought-into, and doesn't require inventing a new pitch. **Extended 2026-07-25 with a third signal, `session-risk`, for a genuine escalation arc instead of one static finding:**

> Quantum is watching a live AI agent session. The session is tied to an OAuth-connected app / employee identity. RelayShield's OAuth watchlist flags that identity as carrying a stolen credential or over-privileged token currently circulating in a criminal stealer-log dump — something Quantum's runtime traceability has no way to see on its own, because it's an *upstream identity compromise*, not an *in-session behavioral anomaly*. RelayShield's identity-risk-score gives that finding a graded trust score. Then the strongest beat: `session-risk` finds that *this exact session's cookie* is already sitting in the same criminal stealer-log dump — meaning a forced re-auth wouldn't actually fix anything, since the session itself, not just the password, is compromised. Identity-risk-score is called again and the score visibly escalates. Quantum's policy engine reacts: elevated scrutiny → forced re-auth → the session-cookie finding overrides that and forces outright termination — closing the loop between "is this AI session behaving normally" (OrcX's strength) and "is the identity behind this session actually trustworthy" (RelayShield's strength).

This is the same pitch-line already drafted for Thursday ("You govern what the AI does. We secure the identities it acts on behalf of.") — the demo just makes it visible and interactive instead of a slide.

### What to actually build for the demo

Small and fast, matching the "design partner" framing below, not a production build:

1. `POST /v1/metered/oauth-watchlist` called against a handful of **pre-seeded demo identities** (not live customer data) — a few genuinely flagged accounts to guarantee a compelling live result, not a real-time query against an unpredictable corpus.
2. Response styled to render natively inside Quantum's own dashboard UI (their object model — UUIDs, context IDs, session IDs, Agent ID — already has a slot for exactly this kind of risk flag) rather than looking like a bolted-on third-party widget.
3. `POST /v1/metered/identity-risk-score` for a "trust score" visual — called **twice** in sequence (once after the OAuth alert, again after the session-cookie alert below) so the score visibly escalates in real time on the same identity/domain, rather than a single static number.
4. **Added 2026-07-25**: `POST /v1/metered/session-risk` — checks the same seeded identity against RelayShield's stolen-session-cookie corpus (INTEL-5, sourced from criminal infostealer log dumps). This is the strongest beat of the three: it demonstrates that even a forced re-auth doesn't remediate a stolen *session*, only a stolen password — a materially more urgent finding than a flagged OAuth token alone. Technical note: `oauth-watchlist`'s existing INTEL-5 signal and `session-risk` both read the same underlying table (`relayshield_stolen_sessions`, keyed by SHA-256 of email), so one seeded record pair drives both endpoints — no dependency on live HaveIBeenPwned data for a fabricated demo email.

### Commercial note — this is the one thing I'd tighten

The existing Option A/B/C structure and the "Build Requirements for Enterprise Licensing" section (platform_license flag, wholesale rate, SLA, 2-3 page API license agreement) are all scoped for a **paid, production** relationship. Gary just told us OrcX isn't taking on cost or commitment before their first contract closes — proposing wholesale terms right now would ask him to negotiate a contract he explicitly said he's not ready for, and risks stalling the actual momentum he wants to keep.

**Propose a fourth, lighter tier instead — a Demo/Design Partner arrangement:**
- A capped, no-cost developer API key (or a short free trial window) scoped only to the endpoints the demo needs (`oauth-watchlist`, `identity-risk-score`, `session-risk`) — not full API access.
- No SLA, no license agreement, no wholesale rate negotiation — this is a demo asset, not a production dependency, so none of that machinery is needed yet.
- Time-boxed (90 days, or when their first contract closes, whichever comes first) so it doesn't quietly become an indefinite free tier.

**Corrected 2026-07-25 — real flaw found in the original framing, not just a wording issue.** The original version of this section said the free demo arrangement "converts into Option B... once OrcX signs their first paying customer." That's not something either side can actually agree to right now: Option B's wholesale rate, SLA, and 2-3 page license agreement don't exist yet in a form Gary has seen or consented to — there's no mechanism by which signing an unrelated customer contract of *theirs* could bind OrcX to commercial terms of *ours* they've never been shown. Proposing an "automatic conversion" would have either been unenforceable or, worse, looked like a bait-and-switch once Gary actually saw what Option B costs.

**What's actually reasonable instead — two separate, both-optional paths, presented at the point their first PO closes:**

1. **Buy the demo system as-is** — a priced, flat-rate subscription covering exactly the three endpoints proven out in the demo (`oauth-watchlist`, `identity-risk-score`, `session-risk`), nothing more. **Proposed price: $99/mo**, reasoning below. This is the low-friction option — no new negotiation, just "the thing that worked in the demo, now paid."
2. **Negotiate full Option B** (wholesale/white-label, broader endpoint access, embedded-in-Quantum resale terms) — the existing structure already scoped elsewhere in this doc, offered as a real alternative for if/when OrcX wants to embed RelayShield more deeply into Quantum itself, not just the three demo endpoints.

Neither path is automatic. Both require OrcX to actually choose and agree — the free window simply ends at the 90-day/first-PO trigger, at which point these two options are what's on the table, not a default outcome.

**Pricing reasoning for the $99/mo 3-endpoint tier**: each of these three endpoints already lives inside a different existing bundle (`oauth-watchlist` in Bundle A, `session-risk` in Bundle B, `identity-risk-score` in Bundle C) — OrcX doesn't want the other ~15 endpoints those bundles include, just these three. Pricing it as a fraction of each source bundle's per-endpoint value (roughly $25 + $20 + $33 ≈ $78/mo baseline) plus a modest premium for flat-rate predictability rounds to a clean $99/mo — real money, but low enough not to be a blocker for a company Gary's already told us is cost-conscious pre-revenue, and clearly cheaper than buying into three full bundles ($450/mo combined) to get the same three endpoints. **Founder should confirm or adjust this number before it's quoted to Gary** — this is a genuinely new pricing decision, not a value pulled from existing published rates.

### Questions to bring to the call
- Confirm the demo is standalone/seeded data, not a live pull against real customer sessions — avoids any data-handling conversation neither side needs yet.
- Confirm oauth-watchlist + identity-risk-score + session-risk are the three he wants shown, or if he has a different specific moment in mind for "something to show on security."
- Raise the Demo/Design Partner framing directly — check he agrees a free, scoped, time-boxed arrangement is the right shape before they've closed their first deal, rather than assuming.
- Present the two-path commercial structure (buy the 3-API system at $99/mo, or negotiate full Option B) as the real options at the 90-day/first-PO trigger — not something either side is bound to yet.

### Updated action items
- [ ] Scope the three demo-seeded endpoint calls (oauth-watchlist, identity-risk-score ×2, session-risk) against fabricated demo identities — no real customer data
- [ ] Issue a capped, no-cost developer API key scoped to just those three endpoints
- [ ] Propose the Demo/Design Partner framing explicitly on the call — don't let it default into Option B terms by omission
- [ ] Get founder sign-off on the $99/mo 3-endpoint price before it's ever quoted to Gary
- [ ] Set a revisit trigger (90 days, or their first signed PO) so the free tier has a natural endpoint, and present both paths (buy the 3-API system, or negotiate Option B) at that trigger — not as an automatic default
