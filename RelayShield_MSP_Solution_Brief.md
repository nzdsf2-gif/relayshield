# RelayShield: MSP Partner Brief

**The proactive identity protection layer your SMB clients can't get anywhere else**

---

## The Gap in Every MSP Stack

Your clients are protected against malware, ransomware, and network intrusion. What their stack almost certainly does not cover is **identity**: the attack surface that precedes every one of those threats.

Identity-based attacks don't announce themselves. They begin weeks before damage occurs: a credential appearing in a breach database, a SIM swap quietly redirecting a phone number, an infostealer log listing an employee's saved passwords on a criminal marketplace. By the time your endpoint or SIEM fires an alert, the attacker has already been inside, authenticated, legitimate, and invisible.

**Identity protection has become a client checkbook requirement.** Cyber insurance carriers now ask about breach monitoring at renewal. State data protection regulations increasingly require documented credential monitoring programs. Clients who have experienced an incident, or know someone who has, are actively asking their MSP what identity monitoring they provide. Most MSP stacks have no answer.

RelayShield is that answer.

---

## What Makes RelayShield Different: We Work While the Attack Is Forming

Every other identity protection service on the market operates on the same model: detect that an account has already been taken over, then notify the victim. **RelayShield's architecture is fundamentally different.** We analyze attack signals while attacks are still forming, and intervene before financial loss occurs.

### The Proactive Response Layer

RelayShield monitors the full attack surface simultaneously and correlates signals across vectors in real time. When signals align, a credential breach followed by an infostealer log appearance followed by a SIM swap attempt, our predictive engine recognizes the attack chain and fires a warning before the attacker completes it.

This is not detection. This is prevention.

**What competitors do:**
> *"Your account has been taken over. Here's what happened."*

**What RelayShield does:**
> *"An attack is forming against your account. Here's what to do right now to stop it."*

### Multi-Vector Signal Correlation

RelayShield monitors five attack surfaces simultaneously and correlates events across all of them:

| Signal | What We Detect | When We Fire |
|---|---|---|
| **Credential breach** | Employee email in a breach database | Within hours of indexing, before attackers begin credential stuffing |
| **Infostealer log exposure** | Device credentials in criminal Telegram markets | 24 to 72 hours ahead of public breach databases, before attackers replay stolen sessions |
| **SIM swap** | Phone number being hijacked at carrier level | Real-time carrier query, before 2FA bypass completes |
| **Domain lookalike** | Typosquat domains registered to impersonate your client | Within hours of registration, before phishing campaigns launch |
| **OAuth supply chain** | Rogue app granted persistent access to Microsoft 365 or Google Workspace | On detection, with one-tap revocation instructions |

When two or more signals fire within a correlation window, RelayShield escalates to a **Coordinated Attack Warning**: the only commercial product at this price point that does this.

### Predictive Attack Chain Alerts

RelayShield's engine recognizes eleven documented attack chains and fires pre-chain warnings when the first signal is detected:

**Identity surface chains:**
- Breach + SIM swap → predicted account takeover
- Infostealer + VPN credential exposure → predicted ransomware precursor
- Smishing + SIM swap → predicted financial account drain
- Domain lookalike + breach → predicted spear phishing campaign
- OAuth app breach + SIM swap → all downstream connected services at risk
- OAuth app breach + credential harvesting → active OAuth token exploitation

**Cross-surface chains (identity × crypto asset):**
- SIM swap + flagged wallet counterparty → CRITICAL crypto exchange drain in progress
- Credential breach + flagged wallet counterparty → coordinated identity and asset attack
- Port-out fraud + flagged wallet counterparty → CRITICAL dual-vector crypto theft chain

Your client gets a warning about what is likely to happen next, with specific steps to break the chain, before the attacker completes it.

---

## The Attack Surface We Cover

### Infostealer Malware: The Fastest-Growing Enterprise Threat

Infostealer malware infected **11.1 million devices in 2025**, putting 3.3 billion credentials into criminal markets. Entry-level infostealer toolkits are available via Malware-as-a-Service for $60/month. In a single pass, they harvest every saved browser password, active session cookie, VPN credential, and cloud platform login from an infected device, packaged and sold in criminal Telegram channels within 24 to 72 hours.

Stolen VPN and remote access credentials are the primary entry point for ransomware deployment. The infostealer is the reconnaissance. The ransomware is the conclusion.

RelayShield monitors criminal Telegram channels and infostealer log markets in near real-time. When an employee's credentials appear in a log, the alert fires within hours, with a four-step device remediation protocol, before session replay, password resets on financial accounts, or ransomware deployment begins.

**No other MSP-accessible product monitors the Telegram channels where these logs are sold.**

### LLMjacking & Shadow AI: The Credential Class Your Stack Cannot See

The same infostealer that harvests browser passwords also harvests AI provider API keys. That changes the economics of a single leaked credential.

A stolen password gives an attacker access. A stolen LLM API key gives them **your client's credit card with no spending limit**. Published incidents range from tens of thousands of dollars per day to a **$500K single-month bill** from one unthrottled key. The underground price for a stolen LLM key is roughly **$30**. That asymmetry, $30 to buy, six figures to absorb, is why this is the fastest-moving credential category in criminal markets.

The exposure is larger than most MSPs realise, because it is not confined to the AI tools a client has approved:

- **Shadow AI.** Developers sign up for DeepSeek, Moonshot Kimi and Alibaba Qwen directly, on personal accounts, without going through procurement. None of it appears in an MSP's SaaS inventory.
- **One key, many models.** A single leaked Hugging Face token bills against DeepSeek, Qwen, Kimi and NVIDIA models through Inference Providers, the attacker never needs a vendor key at all.
- **Cloud keys are now AI keys.** Amazon Bedrock issues dedicated long-lived API keys used as bearer tokens. They are not IAM credentials, and tooling built to spot `AKIA` keys does not see them.

**RelayShield detects exposed API keys across 14 LLM and AI providers** in criminal stealer log archives, OpenAI, Anthropic Claude, Google Gemini, xAI Grok, Amazon Bedrock, Groq, Replicate, LangSmith, Hugging Face, NVIDIA NIM, DeepSeek, Moonshot Kimi, Alibaba Qwen, and Alibaba Cloud.

**Coverage no other tooling provides.** Gitleaks, the most widely deployed open-source secret scanner, ships **zero** detection rules for DeepSeek, Moonshot, Qwen or NVIDIA. An MSP relying on standard secret scanning is blind to every one of them. RelayShield is not scanning your client's repositories for keys they might leak; it is scanning the criminal channels where keys **already leaked** are being sold.

**The MSP conversation this opens:** *"Do you know which AI services your developers are using, and whether any of those keys are already for sale?"* Most clients cannot answer either half. It is a fast, concrete way into an AI-governance discussion that does not require the client to have an AI strategy first.

### SIM Swap: The Only Cost-Effective Carrier Surface Monitor

SIM swap fraud is the attack that bypasses 2FA entirely. An attacker who controls a phone number receives every verification code, banking alert, and account recovery text sent to that number. Once complete, they own every account secured with that phone number.

RelayShield is the **only cost-effective solution that monitors the carrier surface for SIM swap activity** at SMB-accessible pricing. We query the carrier in real time via Twilio Lookup v2, detecting active port or SIM swap events and alerting the user immediately, before the attacker completes account access.

Enterprise SIM swap monitoring solutions start at $10K+/year. RelayShield delivers equivalent carrier-level detection at a fraction of the cost.

### Credential Breach & Dark Web Monitoring

Employee credentials monitored against all known breach databases including dark web sources. When an email appears in a breach, the alert fires with severity scoring, affected data classes, and a prioritized remediation sequence, not just a notification that something happened.

### Domain Lookalike & Typosquat Detection

Business domains scanned against 500M+ registered domains for lookalike registrations. Alerts fire within hours of a new typosquat domain appearing, before attackers launch the phishing campaign that uses it.

### OAuth Supply Chain Monitoring

Rogue OAuth applications with persistent access to Microsoft 365 and Google Workspace detected and flagged monthly. Session token exposure in criminal channels monitored and alerted before attackers use stolen cookies to bypass authentication.

### Crypto Asset Intelligence: Cross-Surface Attack Detection

For clients with digital asset exposure, crypto-native businesses, DeFi operators, Web3 agencies, or high-net-worth individuals, RelayShield extends monitoring to the wallet attack surface via a composite GoPlus Security intelligence call.

**`POST /v1/crypto-intel`**: $0.30/call, takes a wallet address and optional token contract, returns:
- **Address risk flags:** phishing association, blacklist, honeypot-related activity, cybercrime, money laundering, OFAC sanctions
- **Token risk flags:** honeypot detection, buy/sell tax anomalies, mint authority risk, ownership concentration
- **Composite risk score:** CRITICAL / HIGH / MEDIUM / LOW with correlation advisories

**What makes this unique, cross-surface chain detection:** The crypto-intel endpoint doesn't operate in isolation. When GoPlus flags a wallet counterparty as CRITICAL risk, RelayShield records a `wallet_risk_flag` signal in the same 72-hour correlation window as identity signals. If a SIM swap, credential breach, or port-out fraud event has also fired for the same user within that window, RelayShield escalates to a composite CRITICAL alert describing the active coordinated attack chain.

A SIM swap alert and a flagged wallet counterparty arriving within 72 hours is not a coincidence. It is the most common crypto exchange drain pattern. RelayShield is the only product with both signal streams and the correlation layer to connect them.

**MSP use case:** Embed `/v1/crypto-intel` into client onboarding workflows, transaction review processes, or incident response playbooks. The endpoint is callable via REST API, MCP tool (`check_crypto_intel`), or through the consumer-facing Telegram and WhatsApp bots for Crypto Shield subscribers.

---

## Alert Delivery: Where Your Clients Already Are

RelayShield delivers every alert via **WhatsApp and Telegram**: no app to install, no dashboard to check, no training required. The alert arrives as a plain-English message with specific steps, directly on the device your client already uses.

For MSP-managed business accounts, alerts go simultaneously to the affected employee and the admin, your point of contact sees every incident the moment it fires.

---

## Partner Tiers

| Plan | Best For | Monthly Price | MSP Margin |
|---|---|---|---|
| **Business Starter** | Mobile-first sole proprietors, single-owner businesses, freelancers | $19.99/account | 20% |
| **Business Starter + Domain** | Sole proprietors with a business website, adds typosquat domain monitoring | $24.99/account | 20% |
| **Business Basic** | Small teams up to 5 seats, per-member SIM swap, breach, infostealer + admin dashboard | $89.99/account | 25% |
| **Business Shield** | Growing SMBs up to 10 seats, all Basic features + per-seat SIM monitoring + priority alerts | $139.99/account | 25% |
| **Business Shield Pro** | Established SMBs up to 25 seats, full stack + SIM lock onboarding + compliance reporting | $299.99/account | 25% |
| **Crypto Shield** | Crypto-native businesses, DeFi operators, Web3 companies | $19.99/seat | 20% |
| **Multi-Site Shield** | Multi-location businesses, franchises, retail chains, distributed teams with shared/service account exposure | From $45/location | Reseller pricing available |

**On Crypto Shield for MSPs:** If your client base includes crypto-native businesses, exchanges, DeFi operators, Web3 agencies, or high-net-worth individuals with significant digital asset holdings, Crypto Shield adds wallet monitoring, counterparty risk screening, and address poisoning detection alongside the full identity stack. Relevant for MSPs serving financial services or technology verticals.

*White-label arrangement available for partners with 10+ seats under management. Volume pricing available for 50+ seats.*

---

## For Security-Forward MSP Partners: API Access

RelayShield exposes its full monitoring capability via REST API, enabling MSPs and MSSPs to embed RelayShield intelligence directly into their own tooling, SIEM integrations, and SOAR playbooks.

**Transactional API endpoints (PAYG and subscription), 29 endpoints live:**
- `POST /v1/metered/breach`: credential breach lookup ($0.10)
- `POST /v1/metered/sim-swap`: real-time carrier SIM swap check ($0.25)
- `POST /v1/metered/domain`: domain lookalike scan ($0.30)
- `POST /v1/metered/infostealer`: infostealer log exposure check ($0.50)
- `POST /v1/metered/oauth-watchlist`: OAuth supply chain exposure check ($0.30)
- `POST /v1/metered/supply-chain`: vendor breach + stealer composite risk score, up to 10 domains ($0.10)
- `POST /v1/metered/session-risk`: active session hijack / AiTM detection ($0.30)
- `POST /v1/metered/identity-graph`: email → phone/domain correlation from criminal dumps ($0.35)
- `POST /v1/metered/ransomware-risk`: ransomware victim list check + pre-ransomware credentials ($0.40)
- `POST /v1/metered/nhi-exposure`: API key/token/machine credential exposure in stealer logs ($0.40)
- `POST /v1/metered/secret-scan`: secret detection across GitHub, npm, PyPI, Docker Hub and Hugging Face ($0.35)
- `POST /v1/metered/target-risk`: 6-signal correlation risk score ($0.50)
- `POST /v1/metered/crypto-intel`: wallet address risk, token honeypot/tax flags ($0.30)
- `POST /v1/metered/asset-intel`: **NEW** asset watchlist + continuous IOC monitoring, push alerts on match ($0.15)
- `POST /v1/metered/threat-actor`: **Early Warning Intelligence**: surfaces CVE PoC discussion in criminal channels **before NVD publication** (24 to 72 hour warning window) + full MITRE ATT&CK threat actor/campaign lookup ($0.30)
- `POST /v1/metered/tech-stack-cve`: **Agent Framework Exploit Monitoring**: cross-references a client's declared tech stack against CISA KEV + high-EPSS CVEs ($0.20)
- `POST /v1/metered/cve-identity-risk`: CVE × identity signal composite risk: EPSS + KEV + infostealer corpus + ransomware victim + exploit chatter, the only API closing the loop from vulnerability to live organizational identity exposure ($0.40)
- `POST /v1/metered/identity-risk-score`: domain security credit score (0 to 100, grade A to F) across 6 dimensions: breach, infostealer density, IOC presence, ransomware victim, active session exposure, CVE exposure. Embeds directly in client QBRs and cyber insurance renewals ($0.35)
- `POST /v1/metered/bulk-identity-risk`: **NEW** hierarchical org + agent-level risk scoring: up to 10 client domains + up to 5 individual agent identities (emails) per domain in a single call. Returns domain risk score (6 dimensions) plus per-agent breach, infostealer, and active session signals. Purpose-built for AI governance workflows and MSP weekly client sweeps. No competitor offers per-agent identity risk within an organizational hierarchy ($2.00/call)
- `POST /v1/metered/bulk-ioc`: **NEW** bulk IOC enrichment: submit up to 100 IPs, domains, or hashes in a single call, built for SIEM log enrichment pipelines ($0.50/batch)
- `POST /v1/metered/ioc-pivot`: **NEW** lateral infrastructure discovery: given one IOC, return all related IOCs sharing the same malware family, surfaces full C2 networks from a single indicator ($0.20)
- `POST /v1/metered/brand-monitor`: **NEW** brand protection: scan 5.0M+ IOC corpus for brand name patterns, phishing domains, malware C2 infrastructure, and dark web mentions ($0.35)
- `POST /v1/metered/mcp-registry-risk`: **NEW** MCP server / agent-tool registry reputation check: typosquat detection, registration-age scoring against RelayShield's IOC corpus ($0.35)
- `POST /v1/metered/prompt-injection-breach`: **NEW** detects breach exposure sourced from prompt-injection attacks against AI agents, not traditional phishing/malware ($0.35)
- `GET /v1/intel/telegram`: IOC lookup against live threat intelligence database (5.0M+ indicators; domains, IPs, URLs, hashes)
- `GET /v1/intel/cve`: CISA KEV lookup by CVE ID or keyword, ransomware-campaign flag included
- `GET /v1/intel/actor`: full MITRE ATT&CK threat actor profile: TTPs, target sectors, associated IOCs from corpus (TI subscription)
- `GET /v1/intel/trending`: top IOCs seen across all feeds in the last 24/48 hours, what's actively spreading now (TI subscription)

**Threat Intelligence API, live:**
MSSPs operating at scale can query RelayShield's live IOC database directly via `GET /v1/intel/telegram`. The feed aggregates **5.0M+ indicators** from **20+ authoritative threat intelligence feeds** and **85+ criminal Telegram channels**: updated continuously. RelayShield tracks **3,750+ malware families** including QakBot, LummaC2, Emotet, TrickBot, RedLine, Vidar, Raccoon, and 3,743+ others. IOCs are enriched with threat actor attribution, confidence scoring, and MITRE ATT&CK technique mapping.

Pass any domain, IP, URL, or SHA256 hash to check for known malware infrastructure, ahead of reputation services that lag by days or weeks. New: submit batches of up to 100 IOCs via `/v1/metered/bulk-ioc` for log enrichment pipelines.

**Early Warning Intelligence:** RelayShield surfaces CVE PoC discussion in criminal Telegram channels **before NVD publication**: giving MSPs a 24 to 72 hour warning window before vendors issue patches. RelayShield ingests the full CISA KEV catalog daily, 1,600+ actively-exploited CVEs tracked, with ransomware-campaign-linked vulnerabilities flagged separately.

**Automated feed formats, STIX/TAXII 2.1 and MISP:** Point your SIEM's built-in TAXII client at `GET /v1/intel/taxii/*` for a standards-compliant feed of STIX 2.1 Indicator objects, no custom integration work required for Splunk, Sentinel, Elastic, or QRadar. For MISP-based environments (the default/co-primary format across government, CERT/ISAC, and mid-market SOC tooling that STIX-only integration doesn't reach), `GET /v1/intel/misp/event` exports the same IOC corpus as native MISP Event JSON with tagged attributes. Both require a TI subscription and support incremental pulls (`added_after` + pagination) so your SIEM only ingests what's new.

**Shareable risk report links:** Any wallet scan, domain check, or vendor sweep result can be turned into a persistent, shareable URL (`POST /v1/report/share`), generation requires a subscription, but viewing the resulting link is public with no login required. Paste it into a client ticket, a security write-up, or an incident report the same way you'd link to a VirusTotal or Shodan result page. Doubles as a light audit trail for client-facing deliverables.

**Third-Party Risk Score:** `POST /v1/metered/supply-chain` delivers a composite vendor risk score across breach exposure, infostealer density, and dark web presence for up to 10 vendor domains per call ($0.10). Equivalent to Recorded Future's vendor risk module at developer-accessible pricing.

**Price-to-performance:** Enterprise threat intelligence platforms (Recorded Future, ThreatConnect) start at $30K to $300K/year. RelayShield delivers 5.0M+ queryable indicators at **$499/month**: the same enrichment data your clients' enterprise competitors pay $5K+/month to access.

IOC data is retained for 365 days.

**Developer subscription, live today:** $499/mo for 10,000 API calls, $999/mo unlimited. Self-serve signup at api.relayshield.net/developers, covers all metered endpoints above plus the threat intelligence feed. Built for security engineers at small-to-mid-size companies building internal SIEM/SOAR tooling, and security SaaS vendors embedding breach and infostealer data into their own product. No commitment, cancel anytime. Also available on **AWS Marketplace** for teams that prefer to procure and bill through an existing AWS account.

**Mid-market MSSP feed (coming):** A bulk export tier ($1,500 to $3,000/mo) for MSSPs running this data through their own SIEM/SOAR pipeline at scale across many client tenants, delivered as a continuous feed rather than per-query lookups. Contact us to join early access.

**Drops into the SIEM your clients already run:** RelayShield's IOC corpus is served over STIX/TAXII 2.1 and MISP, so it ingests through **Elastic Security's built-in Threat Intel integrations** with configuration alone, no connector to build and no professional-services engagement. Splunk HEC, CEF/QRadar and Cortex XSOAR are supported as push destinations. For an MSSP running a shared SIEM across client tenants, this removes the integration objection entirely.

**Live automation, not just an API:** RelayShield's employee-offboarding credential check is a published, officially-approved template in n8n's workflow library ([n8n.io/workflows/16694](https://n8n.io/workflows/16694)), an HR webhook triggers three parallel identity-risk checks (breach, infostealer, OAuth token exposure) the moment someone's offboarded, routing findings to Slack, a manager email summary, and a Notion audit log automatically. This isn't a hypothetical integration path. It's live, installable today, built on the same API MSPs get direct access to above.

---

## Why This Is Easy to Sell

| Factor | Detail |
|---|---|
| **Fills a genuine gap** | Identity monitoring is a client ask MSPs currently can't answer |
| **Compliance driver** | Cyber insurance carriers and state regulations increasingly require documented credential monitoring |
| **Zero friction** | WhatsApp/Telegram delivery. Clients onboard in under 5 minutes, no MSP involvement after referral |
| **Instant credibility** | First alert proves value immediately. Clients see a real breach or risk on day one |
| **Recurring MRR** | Monthly per-account subscription. Predictable, stackable revenue |
| **Natural upsell** | Pairs with any existing endpoint, backup, or antivirus contract, not a replacement |
| **Carrier-level differentiation** | SIM swap monitoring at carrier depth. No competitor offers this at SMB pricing |

---

## The MSP Pitch

> *"Your clients' identity stack has a blind spot: the carrier surface, the criminal Telegram channels, and the attack signals that fire weeks before a breach becomes visible. RelayShield closes that gap, monitoring every credential, phone number, domain, and infostealer log in real time, correlating signals across the full attack surface, and alerting your clients while the attack is still forming. Not after the damage is done."*

---

## What Your Clients Get on Day One

1. Immediate breach check on all monitored email addresses
2. Infostealer log scan, credentials checked against criminal market exposure
3. SIM swap monitoring activated on all registered phone numbers
4. Domain lookalike scan across 500M+ registered domains
5. OAuth supply chain audit, 31 watched apps checked for breach exposure; rogue app detection active
6. Predictive attack chain engine active, correlation monitoring begins immediately across 11 chains
7. Cross-surface correlation live, identity signals (SIM swap, breach, port-out) correlated against crypto wallet risk signals for clients with digital asset exposure
8. Step-by-step remediation guidance built into every alert

---

## Getting Started

**Pilot program:** Free 30-day Business Starter + Domain account for the MSP principal. Full feature access for a single seat. No team seats, no commitment required. First alert proves the value proposition before your first client conversation.

**Onboarding:** Clients self-onboard via a 2-minute WhatsApp or Telegram flow. No MSP involvement required after the initial referral.

**Support:** Direct line to RelayShield founder for all partner questions.

---

## Contact

**Andrew Gibbs**: Founder, RelayShield
relayshieldadmin@gmail.com
relayshield.net
Andover, MA, RelayShield LLC (Est. April 2026)

*25 years in telecommunications security. Built on a carrier-layer detection foundation no competitor has replicated.*

---

*RelayShield is a registered business in the Commonwealth of Massachusetts (ID: 001963633).*
