# SentinelOne partner submission — RelayShield business description

> ## 🔴 REJECTED 2026-08-21 — do not resubmit as-is
>
> The PartnerOne application was declined **in under five minutes**: "does not currently align with
> our program requirements and focus areas." A five-minute turnaround on a submission of this length
> is an automated screen, not a review. Nothing in the copy below was read.
>
> **What that means practically.** The rejection carries no signal about the positioning, the use
> cases, or the technical fit — it is almost certainly a filter on company size, revenue, existing
> customer count, or an unmet program prerequisite. Rewriting the copy would be solving a problem
> that has not been shown to exist.
>
> **Do not appeal on content.** `partnerops@sentinelone.com` is offered for "if you believe we may
> have missed key information about your business", but a one-paragraph reply to an automated
> screen is unlikely to reopen it, and it costs the option of applying again later from a stronger
> position. The realistic re-entry route is **a joint customer pulling for the integration** — the
> same gate the XSOAR Tech Alliance thread sits behind. That is a sales outcome, not a submission
> problem.
>
> **This file is not wasted.** The 50/100/250-word descriptions, the form fields, the four use
> cases, the technical spec and the data-handling section are vendor-neutral. Reuse them for
> ThreatLocker, Huntress, Blackpoint Cyber, WatchGuard and LimaCharlie (see
> `xcitium_outreach.md` Part 2) by swapping the product names in the "why this integration" block.
> Rapid7 InsightConnect (PR #4024) remains the live proof that the open-contribution route works
> where a partner-program gate does not.


*Drafted 2026-08-21. Copy blocks are ready to paste; read the guardrails first.*

Partner and marketplace forms ask the same question at three different lengths and then ask for
categories. All four are below. **Use them verbatim** — every claim has been checked against what is
actually live, and the numbers follow the corpus rule (distinct indicators and citations are
different things, and both are stated).

---

## 50-word version — "describe your company"

> RelayShield is an identity threat intelligence platform that monitors the layer outside the
> endpoint: mobile carrier activity, criminal marketplaces, and third-party breach data. It detects
> SIM swap, stolen session cookies, exposed credentials and OAuth abuse before an attacker
> authenticates, and delivers findings by API, SIEM feed or direct alert.

## 100-word version — "product overview"

> RelayShield is an identity threat intelligence platform covering the attack surface endpoint and
> network tooling cannot instrument: the mobile carrier, criminal marketplaces, and third-party
> breaches.
>
> It performs live carrier queries for SIM and eSIM swap and port-out fraud, checks identities
> against breach corpora and infostealer logs, detects lookalike domain registration, monitors OAuth
> grant exposure, and screens non-human identities — API keys, service tokens and LLM provider keys
> — appearing in criminal archives.
>
> Findings are delivered over a REST API, as a STIX/TAXII 2.1 or MISP feed, or as direct alerts.
> RelayShield sells directly, through AWS Marketplace, and through MSP partners.

## 250-word version — "detailed description"

> RelayShield is an identity threat intelligence platform. It monitors the part of an attack that
> happens before an attacker touches anything the customer owns.
>
> Endpoint and network security instrument assets under the customer's control. A large class of
> identity attacks never appears there. A SIM swap completes inside the mobile carrier's
> provisioning system. A session cookie harvested by infostealer malware resumes a session that is
> already authenticated, so no login looks anomalous. A credential from a third-party breach
> succeeds on the first attempt. An OAuth grant issued months earlier survives a password rotation.
> None of these generate a suspicious process, a blocked binary, or a failed authentication.
>
> RelayShield collects that signal directly. Live carrier network queries detect SIM and eSIM swaps
> and port-out fraud within minutes. Continuous monitoring checks identities against breach corpora
> and infostealer log archives. Domain monitoring detects typosquat and homoglyph registration
> against a customer's brand through DNS and Certificate Transparency. An OAuth watchlist tracks
> high-risk SaaS applications for compromise. Dedicated endpoints screen non-human identities —
> API keys, service tokens and LLM provider credentials — surfacing in criminal archives.
>
> The intelligence corpus holds 500,000+ distinct indicators of compromise drawn from 5.8M+
> citations, collected from monitored criminal Telegram channels alongside authoritative public
> feeds, with threat actor attribution, confidence scoring and MITRE ATT&CK mapping.
>
> Delivery is by REST API, STIX/TAXII 2.1, MISP, SIEM and SOAR connectors, or direct alerting.
> RelayShield is an AWS Marketplace seller and sells through MSP and MSSP partners.

---

## Form fields — categories, integrations, technical

| Field | Answer |
|---|---|
| **Category** | Threat Intelligence — with Identity Security / ITDR as secondary if the form allows two |
| **Integration type** | Data enrichment and threat intelligence feed |
| **Integration surfaces** | REST API (`api.relayshield.net`); STIX/TAXII 2.1 (`/v1/intel/taxii/`, collection `iocs`); MISP-compatible REST; webhook alert delivery |
| **Authentication** | API key, sent as `X-RS-API-KEY` or `Authorization: Bearer`. TAXII accepts the key in Basic auth |
| **Deployment** | SaaS, multi-tenant, AWS us-east-1 |
| **Existing SIEM/SOAR integrations** | Microsoft Sentinel (first-party TAXII connector), Elastic Security (Custom Threat Intelligence and MISP integrations), Splunk HEC, CEF/QRadar, Cortex XSOAR, ConnectWise, n8n, Zapier, Ansible Galaxy (`relayshield.security`) |
| **Commercial model** | Subscription ($499/mo 10K calls, $999/mo unlimited), per-call metered, x402 USDC micropayments, and AWS Marketplace (three listings: Threat Intelligence Starter/Unlimited, Core Identity Exposure, Agentic Attack Surface) |
| **Marketplace presence** | AWS Marketplace seller, AWS account 239677749008 |

---

## The Singularity Marketplace angle, if the form asks "why this integration"

> SentinelOne's platform resolves what happened on an asset. RelayShield supplies what happened
> before it — the carrier event, the credential's appearance in a criminal market, the stolen
> session — as enrichment inside the same investigation rather than a separate console.
>
> The concrete case: an analyst reviewing a suspicious authentication can see, in the same view,
> whether that identity's phone number was swapped in the last 48 hours, whether its credentials
> appear in a recent stealer log, and whether an active session cookie for it is circulating. Those
> three facts turn an ambiguous alert into a decision, and none of them originate on an endpoint.
>
> Delivery is through interfaces SentinelOne already consumes — STIX/TAXII 2.1 and a REST API — so
> this is a configuration exercise rather than a development one.

---

# Proposed use case integration — detailed description

*This is the section a technical alliance reviewer reads. It is written to be pasted into a
free-text "describe your proposed integration" field, or attached as-is.*

## Summary in one paragraph

> RelayShield proposes a **bi-directional threat intelligence and identity-enrichment integration**
> with the SentinelOne Singularity Platform. Inbound, RelayShield supplies indicators and identity
> exposure signals collected outside the customer's perimeter — mobile carrier events, criminal
> marketplace activity, infostealer log archives and third-party breach data — as enrichment on
> SentinelOne alerts and as a STIX/TAXII 2.1 threat intelligence feed. Outbound, RelayShield
> consumes identity context from Singularity to scope which identities it monitors. The integration
> adds an evidence source that no endpoint agent can produce, inside the console the analyst is
> already working in.

## The problem it solves, stated precisely

A SentinelOne analyst investigating a suspicious authentication or an anomalous process on an
endpoint can establish what happened **on that asset**. What the platform cannot establish, because
the evidence does not exist on any asset the customer owns, is how the attacker arrived with valid
credentials:

* Was this identity's phone number **SIM-swapped or ported** in the last 48 hours? That event
  happened inside a mobile carrier's provisioning system.
* Are this identity's credentials in a **recent infostealer log**? That log is being sold in a
  criminal marketplace.
* Is a **live session cookie** for this identity circulating? If so, the attacker never
  authenticated at all — they resumed a session that was already valid, which is why nothing in the
  authentication telemetry looks wrong.
* Did this identity's credentials appear in a **third-party breach** that the customer was never
  notified about?

Each of those turns an ambiguous alert into a decision. None of them can be derived from endpoint
telemetry, at any level of instrumentation. That is the gap this integration fills — not more
detection, a different *evidence class*.

## Three integration surfaces

| # | Surface | What it does | Build state |
|---|---|---|---|
| 1 | **Singularity Marketplace app** (Nexus FaaS) | Analyst-invoked and automation-invoked enrichment actions against a SentinelOne alert or identity | **Gated** — needs Partner Portal approval for sandbox/API access before anything can be built |
| 2 | **STIX/TAXII 2.1 threat intelligence feed** | Continuous IOC ingest into Singularity Data Lake for correlation against existing telemetry | **Live today** — no development required on either side |
| 3 | **Outbound alert push** | RelayShield-detected identity events (SIM swap, new breach hit, session exposure) pushed into SentinelOne as events/alerts | **Partially built** — `relayshield_siem_connector.py` already emits Splunk HEC, CEF and XSOAR-webhook shapes; a SentinelOne target is a new formatter, not new architecture |

Surface 2 is deliverable immediately and is the sensible first milestone. Surfaces 1 and 3 follow
once API access exists.

---

## Use case 1 — Alert triage enrichment (primary)

**Actor:** SOC analyst, or an automated workflow, working a SentinelOne alert.

**Flow:**

1. SentinelOne raises an alert involving a user identity — suspicious authentication, credential
   access behaviour, an anomalous process running under a user context.
2. The analyst invokes **Enrich Identity** from the Marketplace app, or a workflow invokes it
   automatically on alert creation.
3. The app calls RelayShield with the identity's email address and, where the customer has supplied
   it, phone number:
   * `POST /v1/metered/sim-swap` — live carrier network query for SIM/eSIM swap and port-out
   * `POST /v1/metered/infostealer` — presence in infostealer log archives
   * `POST /v1/metered/breach` — third-party breach exposure
   * `POST /v1/metered/session-risk` — active session cookie / AiTM exposure
4. Results return as structured JSON and are written back as alert enrichment: a composite identity
   risk verdict, per-signal detail, and first-seen dates.

**What the analyst sees that they did not have before:** "This user's number was ported 31 hours
ago, and their credentials appear in a stealer log first seen 6 days ago." That reframes an
ambiguous authentication alert as an in-progress account takeover, and it changes the response from
*monitor* to *revoke sessions and re-enrol MFA now*.

**Why it belongs in the console rather than a separate tool:** the value is entirely in the
adjacency. An analyst who has to leave the investigation to check a second product does not check.

## Use case 2 — Pre-incident early warning

**Actor:** the platform, unattended.

RelayShield continuously monitors a scoped set of workforce identities — typically executives,
finance, IT administrators and anyone with privileged access. When a monitored identity is hit,
RelayShield pushes an event into SentinelOne through surface 3:

| Trigger | Severity | Why it matters before any endpoint event |
|---|---|---|
| SIM swap or port-out detected | CRITICAL | Every SMS second factor for that identity now goes to the attacker. Minutes matter |
| Credentials in a new infostealer log | HIGH | The device is or was infected and the credentials are already for sale |
| Active session cookie exposure | HIGH | MFA is irrelevant — the session is already authenticated |
| New third-party breach hit | MEDIUM | Credential-stuffing window opens now, often 90+ days before the attack |

**The point of this use case:** it produces a SentinelOne alert **when there is nothing on the
endpoint to detect**. The endpoint is clean, the process tree is ordinary, and the compromise is
already underway somewhere the agent cannot see. For an MDR practice this is the difference between
responding to an incident and preventing one.

**Deliberate design constraint:** volume is scoped, not fleet-wide. A managed detection provider is
billed in analyst hours, so an integration that raises alert volume is a cost. These fire on
monitored identities only, and each carries a specific recommended action rather than a bare
finding.

## Use case 3 — Threat intelligence correlation in Singularity Data Lake

**Actor:** the platform, unattended.

RelayShield's IOC corpus — **500K+ distinct indicators drawn from 5.8M+ citations** — ingests over
STIX/TAXII 2.1 and correlates against existing telemetry: DNS lookups, network connections, file
hashes.

* API root: `https://api.relayshield.net/v1/intel/taxii/`, collection id `iocs`
* Incremental pulls via `added_after` plus pagination, so only new indicators transfer
* Every indicator carries `valid_until`, threat actor attribution, confidence scoring and MITRE
  ATT&CK mapping

**The differentiating property is timing, not volume.** These indicators are collected from the
criminal Telegram channels where credentials and infrastructure are *sold*, rather than from
downstream aggregation, so they typically surface **24 to 72 hours ahead of public feeds**. That
window is the period in which a stolen credential is still worth rotating.

**Stated honestly, because a threat intelligence team will check:** a portion of the corpus is
ingested from authoritative public feeds (abuse.ch, CISA KEV) that most buyers already hold. The
exclusive slice is the channel-collected material. We report both, and we would rather be asked
this question than have it discovered.

## Use case 4 — Agentic and non-human identity exposure

The differentiator that is hardest to source elsewhere, and increasingly the one that opens the
conversation.

* `POST /v1/metered/nhi-exposure` — API keys and service tokens in criminal archives
* `POST /v1/metered/llm-credential-exposure` — exposed LLM/AI provider keys across 14 providers
* `POST /v1/metered/secret-scan` — public artifact secret detection across GitHub, npm, PyPI,
  Docker Hub, Hugging Face and Postman
* `POST /v1/metered/supply-chain` — vendor breach and infostealer exposure, up to 10 domains

A leaked LLM provider key is an uncapped live billing liability — published incidents run from tens
of thousands of dollars per day to a $500K single-month bill from one unthrottled key, against an
underground price of roughly $30 to buy one. No endpoint agent sees the key leave, because it
usually leaves through a repository, a container image or a package, not a process.

---

## Proposed actions exposed by the Marketplace app

Scoped deliberately to a first release rather than the full 28-endpoint surface — the same
incremental approach used for the Rapid7 InsightConnect plugin, which is already built, validated
and submitted (`rapid7/insightconnect-plugins` PR #4024).

| Action | Endpoint | Input | Returns |
|---|---|---|---|
| `enrich_identity` | composite | email, optional phone | Composite risk verdict across all four identity signals |
| `check_sim_swap` | `/v1/metered/sim-swap` | phone number | Swap/port-out status, carrier, event recency |
| `check_breach` | `/v1/metered/breach` | email | Breach list, data classes exposed, severity |
| `check_infostealer` | `/v1/metered/infostealer` | email | Stealer log presence, malware family, first seen |
| `check_session_risk` | `/v1/metered/session-risk` | email or domain | Active session cookie exposure, AiTM indicators |
| `check_domain` | `/v1/metered/domain` | domain | Typosquat and lookalike registrations |
| `check_supply_chain` | `/v1/metered/supply-chain` | up to 10 vendor domains | Composite vendor risk |

## Technical specification

| Item | Detail |
|---|---|
| **Transport** | HTTPS REST, JSON request and response |
| **Auth** | API key as `X-RS-API-KEY` or `Authorization: Bearer`. TAXII additionally accepts the key in Basic auth (put it in **both** username and password fields — a blank password causes conformant TAXII clients to skip auth entirely) |
| **Response envelope** | `{"ok": true, "data": {...}}` on success; `{"ok": false, "error": "..."}` with a non-2xx status on failure. **Note the `data` wrapper** — two n8n templates shipped referencing fields one level too shallow, so it is called out explicitly here |
| **Latency** | Sub-second for corpus lookups; SIM swap depends on a live carrier query, typically 1–3 seconds |
| **Rate limits** | Per-key, tier-dependent; enterprise limits negotiable |
| **Hosting** | AWS us-east-1, multi-tenant SaaS |
| **Data residency** | US. EU residency is not currently offered — relevant if a joint prospect is EU-regulated |

## Data handling

Deliberately included, because this is where an alliance review usually stops.

* RelayShield receives **only the identifier being checked** — an email address, phone number or
  domain. No endpoint telemetry, no file contents, no process data.
* Queried identifiers are **not retained as customer data** or added to any monitoring list unless
  the customer explicitly enrols them.
* **Credentials and session tokens are never returned in plaintext.** Findings describe exposure —
  which breach, which data classes, when first seen — never the secret itself.
* The IOC corpus contains attacker infrastructure. **Victim organisation names are stored in a
  separate table and are never served as indicators of compromise**, so a breached company's own
  domain can never be returned to a customer as "dangerous".

## Proposed phasing

| Phase | Deliverable | Depends on |
|---|---|---|
| **1** | STIX/TAXII feed documented and validated against Singularity Data Lake; joint integration guide | Nothing. Live today |
| **2** | Outbound identity alerts into SentinelOne via a new formatter in `relayshield_siem_connector.py` | Confirmation of the preferred ingest endpoint and event schema |
| **3** | Singularity Marketplace app with the seven actions above | **Partner Portal approval → Nexus FaaS sandbox and API access** |
| **4** | Bi-directional: consume identity context from Singularity to scope monitoring automatically | Phase 3 in production |

**Phase 3 is the one we cannot start.** Marketplace apps run on SentinelOne's hosted Nexus FaaS
platform and sandbox access is gated behind partner approval, so there is nothing to build until
that is granted. Phases 1 and 2 are not gated and can proceed in parallel with the application.

## What we are asking for

1. Technology Partner approval and **Nexus FaaS sandbox access** — the single blocker on phase 3.
2. Confirmation of the preferred **inbound event ingest** path and schema for phase 2.
3. A technical contact for a **joint validation** of the TAXII feed against Singularity Data Lake.
4. Listing guidance for Singularity Marketplace once phase 3 is built.

---

## Guardrails

**Do not claim a joint customer.** The XSOAR Tech Alliance application is already gated on naming
two, and none exist to name. If this form asks for references, say so and offer a technical
walkthrough instead — a fabricated reference is unrecoverable when it is checked.

**Do not quote a single large indicator number.** 500K+ distinct indicators and 5.8M+ citations are
different measurements and both belong in any sentence that uses either. A vendor of this size will
ask which one you mean, and having the answer ready is worth more than the bigger number.

**Do not position RelayShield as EDR, XDR or a SentinelOne alternative.** Every version above is
written as an input to their platform. That is the only framing that survives their product team.

**Re-measure before submitting** if this sits for more than a week: `tools/export_intel_sample.py`
for the corpus figures, and re-check the AWS Marketplace listing states.

**Check SentinelOne's current product names against their own docs before pasting.** The use case
section references Singularity Marketplace, Singularity Data Lake and Nexus FaaS. Those are correct
as of the 2026-07-26 research recorded in `TODO.md` item 71, but vendor product naming moves and a
stale name in the first paragraph reads as someone who has not looked recently.

**Expect the identity overlap question.** SentinelOne sells identity security of its own. The
answer, which is true: theirs operates inside the directory and the session; RelayShield operates
outside both — the carrier, the criminal market, and the credential's life before it ever reaches an
authentication attempt. **Raise it before they do.**

**Do not soften the phase 3 blocker.** Saying plainly that the Marketplace app cannot be built until
sandbox access is granted is what makes the rest of the timeline credible, and it puts the one thing
we actually need from them in front of the reviewer.
