# SentinelOne partner submission — RelayShield business description

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
