# RelayShield — MSP Partner Brief

**The proactive identity protection layer your SMB clients can't get anywhere else**

---

## The Gap in Every MSP Stack

Your clients are protected against malware, ransomware, and network intrusion. What their stack almost certainly does not cover is **identity** — the attack surface that precedes every one of those threats.

Identity-based attacks don't announce themselves. They begin weeks before damage occurs: a credential appearing in a breach database, a SIM swap quietly redirecting a phone number, an infostealer log listing an employee's saved passwords on a criminal marketplace. By the time your endpoint or SIEM fires an alert, the attacker has already been inside — authenticated, legitimate, and invisible.

**Identity protection has become a client checkbook requirement.** Cyber insurance carriers now ask about breach monitoring at renewal. State data protection regulations increasingly require documented credential monitoring programs. Clients who have experienced an incident — or know someone who has — are actively asking their MSP what identity monitoring they provide. Most MSP stacks have no answer.

RelayShield is that answer.

---

## What Makes RelayShield Different: We Work While the Attack Is Forming

Every other identity protection service on the market operates on the same model: detect that an account has already been taken over, then notify the victim. **RelayShield's architecture is fundamentally different.** We analyze attack signals while attacks are still forming — and intervene before financial loss occurs.

### The Proactive Response Layer

RelayShield monitors the full attack surface simultaneously and correlates signals across vectors in real time. When signals align — a credential breach followed by an infostealer log appearance followed by a SIM swap attempt — our predictive engine recognizes the attack chain and fires a warning before the attacker completes it.

This is not detection. This is prevention.

**What competitors do:**
> *"Your account has been taken over. Here's what happened."*

**What RelayShield does:**
> *"An attack is forming against your account. Here's what to do right now to stop it."*

### Multi-Vector Signal Correlation

RelayShield monitors five attack surfaces simultaneously and correlates events across all of them:

| Signal | What We Detect | When We Fire |
|---|---|---|
| **Credential breach** | Employee email in a breach database | Within hours of indexing — before attackers begin credential stuffing |
| **Infostealer log exposure** | Device credentials in criminal Telegram markets | 24–72 hours ahead of HIBP — before attackers replay stolen sessions |
| **SIM swap** | Phone number being hijacked at carrier level | Real-time carrier query — before 2FA bypass completes |
| **Domain lookalike** | Typosquat domains registered to impersonate your client | Within hours of registration — before phishing campaigns launch |
| **OAuth supply chain** | Rogue app granted persistent access to Microsoft 365 or Google Workspace | On detection — with one-tap revocation instructions |

When two or more signals fire within a correlation window, RelayShield escalates to a **Coordinated Attack Warning** — the only commercial product at this price point that does this.

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

Your client gets a warning about what is likely to happen next — with specific steps to break the chain — before the attacker completes it.

---

## The Attack Surface We Cover

### Infostealer Malware — The Fastest-Growing Enterprise Threat

Infostealer malware infected **11.1 million devices in 2025**, putting 3.3 billion credentials into criminal markets. Entry-level infostealer toolkits are available via Malware-as-a-Service for $60/month. In a single pass, they harvest every saved browser password, active session cookie, VPN credential, and cloud platform login from an infected device — packaged and sold in criminal Telegram channels within 24–72 hours.

Stolen VPN and remote access credentials are the primary entry point for ransomware deployment. The infostealer is the reconnaissance. The ransomware is the conclusion.

RelayShield monitors criminal Telegram channels and infostealer log markets in near real-time. When an employee's credentials appear in a log, the alert fires within hours — with a four-step device remediation protocol — before session replay, password resets on financial accounts, or ransomware deployment begins.

**No other MSP-accessible product monitors the Telegram channels where these logs are sold.**

### SIM Swap — The Only Cost-Effective Carrier Surface Monitor

SIM swap fraud is the attack that bypasses 2FA entirely. An attacker who controls a phone number receives every verification code, banking alert, and account recovery text sent to that number. Once complete, they own every account secured with that phone number.

RelayShield is the **only cost-effective solution that monitors the carrier surface for SIM swap activity** at SMB-accessible pricing. We query the carrier in real time via Twilio Lookup v2 — detecting active port or SIM swap events and alerting the user immediately, before the attacker completes account access.

Enterprise SIM swap monitoring solutions start at $10K+/year. RelayShield delivers equivalent carrier-level detection at a fraction of the cost.

### Credential Breach & Dark Web Monitoring

Employee credentials monitored against all known breach databases including dark web sources. When an email appears in a breach, the alert fires with severity scoring, affected data classes, and a prioritized remediation sequence — not just a notification that something happened.

### Domain Lookalike & Typosquat Detection

Business domains scanned against 500M+ registered domains for lookalike registrations. Alerts fire within hours of a new typosquat domain appearing — before attackers launch the phishing campaign that uses it.

### OAuth Supply Chain Monitoring

Rogue OAuth applications with persistent access to Microsoft 365 and Google Workspace detected and flagged monthly. Session token exposure in criminal channels monitored and alerted before attackers use stolen cookies to bypass authentication.

### Crypto Asset Intelligence — Cross-Surface Attack Detection

For clients with digital asset exposure — crypto-native businesses, DeFi operators, Web3 agencies, or high-net-worth individuals — RelayShield extends monitoring to the wallet attack surface via a composite GoPlus Security intelligence call.

**`POST /v1/crypto-intel`** — $0.30/call — takes a wallet address and optional token contract, returns:
- **Address risk flags:** phishing association, blacklist, honeypot-related activity, cybercrime, money laundering, OFAC sanctions
- **Token risk flags:** honeypot detection, buy/sell tax anomalies, mint authority risk, ownership concentration
- **Composite risk score:** CRITICAL / HIGH / MEDIUM / LOW with correlation advisories

**What makes this unique — cross-surface chain detection:** The crypto-intel endpoint doesn't operate in isolation. When GoPlus flags a wallet counterparty as CRITICAL risk, RelayShield records a `wallet_risk_flag` signal in the same 72-hour correlation window as identity signals. If a SIM swap, credential breach, or port-out fraud event has also fired for the same user within that window, RelayShield escalates to a composite CRITICAL alert describing the active coordinated attack chain.

A SIM swap alert and a flagged wallet counterparty arriving within 72 hours is not a coincidence — it is the most common crypto exchange drain pattern. RelayShield is the only product with both signal streams and the correlation layer to connect them.

**MSP use case:** Embed `/v1/crypto-intel` into client onboarding workflows, transaction review processes, or incident response playbooks. The endpoint is callable via REST API, MCP tool (`check_crypto_intel`), or through the consumer-facing Telegram and WhatsApp bots for Crypto Shield subscribers.

---

## Alert Delivery: Where Your Clients Already Are

RelayShield delivers every alert via **WhatsApp and Telegram** — no app to install, no dashboard to check, no training required. The alert arrives as a plain-English message with specific steps, directly on the device your client already uses.

For MSP-managed business accounts, alerts go simultaneously to the affected employee and the admin — your point of contact sees every incident the moment it fires.

---

## Partner Tiers

| Plan | Best For | Monthly Price | MSP Margin |
|---|---|---|---|
| **Business Starter** | Mobile-first sole proprietors — single-owner businesses, freelancers | $19.99/account | 20% |
| **Business Starter + Domain** | Sole proprietors with a business website — adds typosquat domain monitoring | $24.99/account | 20% |
| **Business Basic** | Small teams up to 5 seats — per-member SIM swap, breach, infostealer + admin dashboard | $89.99/account | 25% |
| **Business Shield** | Growing SMBs up to 10 seats — all Basic features + per-seat SIM monitoring + priority alerts | $139.99/account | 25% |
| **Business Shield Pro** | Established SMBs up to 25 seats — full stack + SIM lock onboarding + compliance reporting | $299.99/account | 25% |
| **Crypto Shield** | Crypto-native businesses, DeFi operators, Web3 companies | $19.99/seat | 20% |

**On Crypto Shield for MSPs:** If your client base includes crypto-native businesses — exchanges, DeFi operators, Web3 agencies, or high-net-worth individuals with significant digital asset holdings — Crypto Shield adds wallet monitoring, counterparty risk screening, and address poisoning detection alongside the full identity stack. Relevant for MSPs serving financial services or technology verticals.

*White-label arrangement available for partners with 10+ seats under management. Volume pricing available for 50+ seats.*

---

## For Security-Forward MSP Partners: API Access

RelayShield exposes its full monitoring capability via REST API — enabling MSPs and MSSPs to embed RelayShield intelligence directly into their own tooling, SIEM integrations, and SOAR playbooks.

**Transactional API endpoints (PAYG and subscription):**
- `POST /v1/breach` — credential breach lookup
- `POST /v1/sim-swap` — real-time carrier SIM swap check
- `POST /v1/domain` — domain lookalike scan
- `POST /v1/infostealer` — infostealer log exposure check
- `POST /v1/oauth-watchlist` — OAuth supply chain exposure check (31 watched apps)
- `POST /v1/crypto-intel` — wallet address risk, token honeypot/tax flags, counterparty screening (GoPlus composite)
- `GET /v1/intel/telegram` — IOC lookup against live threat intelligence database (200,000+ indicators across 9 sources; domains, IPs, URLs, hashes)
- `GET /v1/intel/cve` — CISA KEV lookup by CVE ID or keyword, ransomware-campaign flag included

**Threat Intelligence API — live:**
MSSPs operating at scale can query RelayShield's live IOC database directly via `GET /v1/intel/telegram`. The feed aggregates **200,000+ indicators** from two source categories — **8 verified criminal Telegram channels** and **11 authoritative threat intelligence feeds** — updated continuously:

- **Criminal Telegram channels (8 verified)** — infostealer log markets, credential dump channels, and SIM swap service listings. The underground sources that surface threats 24–72 hours before public breach databases. Active session cookies, raw credential files, and breach announcements appear here first. RelayShield tracks **450+ malware families and variants** across all sources — including QakBot, LummaC2, Emotet, TrickBot, Dridex, RedLine, Vidar, Raccoon, BumbleBee, PikaBot, BazarLoader, ClearFake, and 440+ others.
- **ThreatFox (abuse.ch)** — malware IOCs tagged by family: LummaC2, RedLine, Vidar, Stealc, Raccoon, and 14 other credential-theft families
- **URLhaus (abuse.ch)** — malicious URLs used for active malware distribution, updated daily
- **Feodo Tracker aggressive (abuse.ch)** — ~8,000 active botnet C2 IPs (Emotet, QakBot, Dridex, IcedID, TrickBot)
- **MalwareBazaar (abuse.ch)** — malware sample SHA256 hashes, tagged by malware family
- **Spamhaus DROP/EDROP** — IP CIDR ranges operated by professional spam and cybercrime networks
- **AbuseIPDB** — crowdsourced IP abuse reports, confidence-filtered (≥90%)
- **Emerging Threats** — compromised IP blocklist updated daily
- **AlienVault OTX** — community threat pulses covering domains, IPs, and file hashes

Pass any domain, IP, URL, or SHA256 hash to check for known malware infrastructure association — ahead of reputation services that lag by days or weeks.

**Global ransomware CVE intelligence:** RelayShield ingests the full CISA Known Exploited Vulnerabilities (KEV) catalog daily — 1,600+ actively-exploited CVEs tracked, with vulnerabilities tied to known ransomware campaigns flagged separately. Use this as a concrete upsell signal: when a vendor/product your clients run appears with an actively-exploited, ransomware-linked CVE, you have a dated, documented reason to open a remediation conversation — not a generic "patch your systems" reminder.

**Price-to-performance:** Enterprise threat intelligence platforms start at $30K–$300K/year for equivalent IOC coverage. RelayShield delivers 200,000+ queryable indicators at **$499/month** — the same enrichment data your clients' enterprise competitors pay $5K+/month to access.

IOC data is retained for 90 days.

**Developer subscription — live today:** $499/mo for 10,000 API calls, $999/mo unlimited. Self-serve signup at relayshield.net/developers — covers all metered endpoints above plus the threat intelligence feed. Built for security engineers at small-to-mid-size companies building internal SIEM/SOAR tooling, and security SaaS vendors embedding breach and infostealer data into their own product. No commitment, cancel anytime.

**Mid-market MSSP feed (coming):** A bulk export tier ($1,500–$3,000/mo) for MSSPs running this data through their own SIEM/SOAR pipeline at scale across many client tenants, delivered as a continuous feed rather than per-query lookups. Contact us to join early access.

---

## Why This Is Easy to Sell

| Factor | Detail |
|---|---|
| **Fills a genuine gap** | Identity monitoring is a client ask MSPs currently can't answer |
| **Compliance driver** | Cyber insurance carriers and state regulations increasingly require documented credential monitoring |
| **Zero friction** | WhatsApp/Telegram delivery — clients onboard in under 5 minutes, no MSP involvement after referral |
| **Instant credibility** | First alert proves value immediately — clients see a real breach or risk on day one |
| **Recurring MRR** | Monthly per-account subscription — predictable, stackable revenue |
| **Natural upsell** | Pairs with any existing endpoint, backup, or antivirus contract — not a replacement |
| **Carrier-level differentiation** | SIM swap monitoring at carrier depth — no competitor offers this at SMB pricing |

---

## The MSP Pitch

> *"Your clients' identity stack has a blind spot: the carrier surface, the criminal Telegram channels, and the attack signals that fire weeks before a breach becomes visible. RelayShield closes that gap — monitoring every credential, phone number, domain, and infostealer log in real time, correlating signals across the full attack surface, and alerting your clients while the attack is still forming. Not after the damage is done."*

---

## What Your Clients Get on Day One

1. Immediate breach check on all monitored email addresses
2. Infostealer log scan — credentials checked against criminal market exposure
3. SIM swap monitoring activated on all registered phone numbers
4. Domain lookalike scan across 500M+ registered domains
5. OAuth supply chain audit — 31 watched apps checked for breach exposure; rogue app detection active
6. Predictive attack chain engine active — correlation monitoring begins immediately across 11 chains
7. Cross-surface correlation live — identity signals (SIM swap, breach, port-out) correlated against crypto wallet risk signals for clients with digital asset exposure
8. Step-by-step remediation guidance built into every alert

---

## Getting Started

**Pilot program:** Free 30-day Business Starter + Domain account for the MSP principal — full feature access for a single seat. No team seats, no commitment required. First alert proves the value proposition before your first client conversation.

**Onboarding:** Clients self-onboard via a 2-minute WhatsApp or Telegram flow. No MSP involvement required after the initial referral.

**Support:** Direct line to RelayShield founder for all partner questions.

---

## Contact

**Andrew Gibbs** — Founder, RelayShield
relayshieldadmin@gmail.com
relayshield.net
Andover, MA — RelayShield LLC (Est. April 2026)

*25 years in telecommunications security. Built on a carrier-layer detection foundation no competitor has replicated.*

---

*RelayShield is a registered business in the Commonwealth of Massachusetts (ID: 001963633).*
