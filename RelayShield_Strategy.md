# RelayShield — Strategic Business Document
*Generated: March 2026 | Last Updated: March 2026*

---

## 1. Product Overview

**RelayShield** is an AI-native identity protection platform built on a telecom security foundation. It monitors credentials, email domains, phone numbers, and business secrets across breach databases, dark web feeds, carrier-layer signals, and public code repositories — delivering real-time alerts and conversational remediation via WhatsApp and Telegram.

### Core Positioning Statement
> *"Actionable Security, Delivered to Your WhatsApp."*
> *Your credentials are probably already on the dark web. RelayShield finds them first — then walks you through exactly what to do next, right in your WhatsApp.*

### Supporting Taglines
> *"Already using a data removal service? Smart start. Now add the protection layer it can't provide."*

> *"RelayShield doesn't just tell you that your credentials were breached. It monitors for signs that your data is actively being stolen — exposed secrets in public code repositories, domain impersonators targeting your business, and your company data appearing in dark web marketplaces. Built by a 25-year telecom security professional, priced for businesses that can't afford enterprise tools."*

---

## 2. Founder Profile

- 25 years telecommunications industry experience
- Product Management and Business Development background
- Identity Management and Zero-Trust expertise
- Cryptography and encryption knowledge
- Vibe-coding capability: AWS Lambda, DynamoDB, Twilio/WhatsApp, Python, webhooks
- Completed SmartAsst project (Task Manager/Scheduler with WhatsApp front-end)

---

## 3. Target Market

### Primary Segments
- **SMBs** (Small/Medium Businesses) — recurring B2B contracts, self-serve onboarding
- **Privacy-conscious consumers** — volume play, $12/month

### Pricing Strategy — Standard vs Founding Member

**Standard Pricing (Permanent — All New Customers After Founding Period):**

| Tier | Target | Price | What They Get |
|---|---|---|---|
| **Personal Shield** | Consumers | $15/month | Email + phone breach monitoring, WhatsApp alerts, AI remediation |
| **Business Shield** | SMBs | $99/month | Up to 10 employee emails, domain monitoring, team dashboard, WhatsApp alerts |
| **Business Shield Pro** | Growing SMBs | $179/month | Up to 25 seats, SIM swap monitoring, priority support |

**Founding Member Pricing (First 50 SMB Customers — Locked Forever):**

| Tier | Standard Price | Founding Rate | Saving |
|---|---|---|---|
| **Personal Shield** | $15/month | $12/month | $3/month |
| **Business Shield** | $99/month | $79/month | $20/month |
| **Business Shield Pro** | $179/month | $149/month | $30/month |

### Why This Approach Is Strategically Superior

No customer ever experiences a price increase. The frame is inverted entirely:

```
OLD APPROACH:   Launch at $79 → raise to $99 at Phase 2
Customer hears: "You're charging me more"
Result:         Churn risk, complaints, negative reviews

NEW APPROACH:   $99 standard price, $79 founding discount
Customer hears: "I locked in a great rate early"
Result:         Loyalty, word of mouth, zero resentment
```

### Founding Member Acquisition Strategy

Use the expiring discount — not a price increase — as the urgency driver:

> *"🔒 Founding Member Offer — First 50 businesses only. Lock in Business Shield at $79/month forever. Standard price is $99/month. Sign up today and your rate never changes, no matter what features we add."*

When founding spots fill, simply close the offer. New customers pay $99. Existing customers keep $79 for life. No price increase conversation. Ever.

### Standalone Value Comparison (Phase 2 Justification)

| Capability | Standalone Tool | Standalone Cost |
|---|---|---|
| Email breach monitoring | HIBP direct | ~$30/month |
| Dark web data sale monitoring | Flare SMB | $50-100/month |
| Secret/API key scanning | GitGuardian | $29/month |
| Domain spoofing detection | BrandShield | $10-30/month |
| WhatsApp conversational AI | Nothing comparable | — |
| Telecom layer / SIM swap | Nothing comparable | — |
| **Total standalone** | **4 separate tools** | **$120-190/month** |

RelayShield Phase 2 delivers all of this in one product, one WhatsApp conversation, one dashboard, one invoice — at $99/month.

### Revenue Path to $2,500/Month

**During founding period (mix of $79 and $99 SMB):**
- Pure SMB founding: 32 clients × $79 = $2,528
- Mixed founding: 15 SMB ($1,185) + 110 consumers ($1,320) = $2,505

**After founding period closes (standard pricing):**
- Pure SMB standard: 26 clients × $99 = $2,574
- Mixed standard: 12 SMB ($1,188) + 110 consumers ($1,320) = $2,508
- Consumer at $15: 167 consumers × $15 = $2,505

**Break even:** 2 consumer subscribers at $15 covers all Phase 1 running costs (~$35/month)

---

## 4. Core Differentiators

### 1. Telecom Layer (Primary Moat)
- SIM swap detection and alerts
- Phone number dark web exposure monitoring
- Carrier account change notifications
- SS7 vulnerability awareness and remediation
- Carrier change monitoring via Twilio Lookup API (~$0.01/lookup)
- No competitor addresses telecom-layer identity threats at consumer/SMB level

### 2. WhatsApp-Native Alerts
- Two-way conversational delivery (not one-way push)
- 90%+ open rates vs email
- Already built in existing tech stack
- Competitors send one-directional alerts only

### 3. Conversational AI Remediation
- Step-by-step guidance via WhatsApp conversation
- Available 24/7 including 3am on Sunday
- Powered by Claude API
- Competitors stop at the alert — RelayShield walks users through recovery

### 4. SMB Team Dashboard
- Monitor all employee emails from one account
- Team-level risk scoring
- Admin visibility across workforce
- Justifies recurring monthly subscription
- No competitor serves this segment with a purpose-built product

### 5. Published Accuracy Benchmarks
- Explicit commitment to transparency
- No competitor publishes precision/recall metrics
- Builds trust with enterprise buyers
- Directly attacks Aura and Incogni credibility gap

### 6. AI-Native Architecture
- AI is the engine, not a feature bolt-on
- Every interaction trains proprietary dataset
- Enables predictive analytics in Phase 2-3
- Dataset becomes separately monetizable asset

### 7. Exfiltration Detection (Phase 2 Moat)
- Secret and API key exposure monitoring via GitGuardian
- Dark web data sale monitoring via Flare API
- Domain spoofing and typosquatting detection via dnstwist
- Cloud account anomaly detection (Phase 3)
- No SMB-priced competitor combines all four capabilities
- Detects active data theft — not just historical breaches

---

## 5. Breach Intelligence Engine

### Core HIBP API Capabilities

**Email Breach Monitoring** — $4.50/month (Pwned 1, 10 RPM)
- Daily scheduled check per monitored email
- New breach → WhatsApp alert + Claude remediation
- DataClasses field reveals phone number exposure
- Upgrade trigger: Pwned 2 ($22/month, 50 RPM) at 50+ paying customers

**Password Breach Checking** — FREE (Pwned Passwords API)
- K-anonymity model — password never transmitted
- Send first 5 chars of SHA-1 hash only
- Returns count of times password seen in breaches
- Consumer onboarding + post-breach conversation trigger

**Domain Scanner** — Included in Pwned 1
- SMB onboarding → instant domain-wide exposure report
- Returns all breached employee emails for a domain
- 25 breached emails per domain (Pwned 1 limit)
- Weekly re-scan for new employee breaches

### SMS Protection Layer
- Phone number exposure detection (HIBP DataClasses)
- SS7 vulnerability advisory via Claude remediation
- Smishing awareness guidance post-breach
- Carrier change monitoring via Twilio Lookup API (~$0.01/lookup)

---

## 6. Exfiltration Detection Engine (Phase 2)

### The Key Distinction
```
DATA EXFILTRATION PREVENTION    Stops data leaving a system in real time
                                 Requires: network agents, endpoint software
                                 → Enterprise DLP territory — NOT RelayShield's lane

DATA EXFILTRATION DETECTION     Identifies that data HAS been stolen
                                 Requires: dark web monitoring, secret scanning,
                                 domain monitoring
                                 → EXACTLY RelayShield's lane
```

### Capability 1 — Secret and API Key Exposure Monitoring
**Tool:** GitGuardian API | **Cost:** Free tier → $29/month

- Monitors GitHub, GitLab, Bitbucket public repositories and Pastebin
- Detects exposed API keys, database credentials, AWS keys, Twilio tokens
- Scans for secrets tied to user's monitored domain
- Returns: exact file, line number, secret type exposed
- Lambda checks GitGuardian API daily
- WhatsApp alert on detection:
  > *"⚠️ An API key linked to yourdomain.com was found in a public GitHub repository. Reply DETAILS for location and immediate revocation steps."*

### Capability 2 — Dark Web Data Sale Monitoring
**Tool:** Flare API | **Cost:** ~$50-100/month SMB tier

- Monitors dark web forums and illicit marketplaces
- Detects data sale listings mentioning user's domain
- Identifies bulk credential dumps containing domain emails
- Flags threat actor posts mentioning company names
- Domain-level scan added to existing HIBP domain check workflow
- WhatsApp alert on detection:
  > *"🔴 Data matching yourdomain.com was detected in a dark web marketplace listing. Reply URGENT for immediate response steps."*

### Capability 3 — Domain Spoofing and Typosquatting Detection
**Tool:** dnstwist (open source Python) | **Cost:** FREE

- Generates 100+ lookalike variations of monitored domain
- Checks which variations are newly registered and active
- Returns: registered lookalikes, IP addresses, mail server configs
- Weekly Lambda function runs dnstwist on each monitored SMB domain
- WhatsApp alert on detection:
  > *"⚠️ A domain impersonating yourdomain.com was registered 3 days ago: y0urdomain.com. This is a common data theft precursor. Reply STEPS for immediate action."*

### Capability 4 — Cloud Account Anomaly Detection
**Tool:** Google Workspace Admin SDK + Microsoft Graph API | **Phase 3**

- Monitors Google Drive and Microsoft 365 audit logs
- Detects unusual bulk downloads, new external sharing, login anomalies
- Flags new country logins and unrecognised device access
- Requires OAuth permissions from SMB admin
- Strong retention driver once implemented

### Phase 2 Additional Monthly Costs

| Capability | Tool | Cost |
|---|---|---|
| Secret/API key scanning | GitGuardian | ~$29/month |
| Dark web data monitoring | Flare API | ~$75/month |
| Domain spoofing detection | dnstwist | FREE |
| **Phase 2 addition** | | **~$104/month** |
| **Phase 2 total running costs** | | **~$139/month** |

Break even at Phase 2: 2 SMB clients at $99 = $198 — covers all costs with margin.

---

## 7. Competitive Analysis

### Competitor Map

| Competitor | Threat Level | Category |
|---|---|---|
| **Aura** | 🔴 High | Identity protection suite |
| **LifeLock/Norton** | 🟡 Medium | Consumer brand |
| **HaveIBeenPwned** | 🟡 Medium | Free breach lookup |
| **Flare/SpyCloud** | 🟢 Low | Enterprise only ($500+/month) |
| **Incogni** | 🟢 Low | Adjacent category (data broker removal) |
| **IsItDangerous** | 🟢 Low | Different problem, weakening position |

---

### Aura — Primary Competitor

**What they do:** AI-powered all-in-one digital safety platform. Credit monitoring, dark web scanning, antivirus, VPN, password manager, fraud insurance.

**Key facts:**
- $1.6B valuation, $672M funding, $300M+ ARR
- 1.1M+ subscribers, 1,700+ employer partners
- March 2026: 900,000-record data breach (active trust crisis)

**Confirmed gaps RelayShield exploits:**

| Aura Gap | RelayShield Advantage |
|---|---|
| Zero SIM swap / telecom detection | Core Phase 2 capability |
| One-way WhatsApp alerts only | Two-way conversational AI |
| No Telegram | Phase 2 roadmap |
| No SMB team dashboard | Core SMB product |
| No published accuracy benchmarks | Explicit commitment |
| No predictive analytics | Phase 2-3 roadmap |
| No exfiltration detection | Phase 2 differentiator |
| Billing complaints (BBB 1.06/5) | Transparent self-serve pricing |
| March 2026 data breach | Active trust crisis — acquisition opportunity |

**Positioning against Aura:**
> *"Aura protects your credit. RelayShield protects the threats Aura can't see — your phone network, your team's credentials, your business secrets in public code repositories, and your next steps at 3am."*

---

### Incogni (by Surfshark) — Adjacent Competitor

**What they do:** Automated data broker removal service. Sends legally-binding opt-out requests to 420+ data brokers under GDPR/CCPA. Repeats every 60-90 days.

**Key facts:**
- $7.99/month annual, 245M+ removals
- Deloitte-verified (August 2025)
- No dark web monitoring by design

**Critical vulnerability:**
> Incogni's own Help Center states: *"Once your data is on the dark web, it's too late."*
> RelayShield operates precisely in the space Incogni publicly surrenders.

**Positioning against Incogni:**
> *"Already using a data removal service? Smart start. Now add the protection layer it can't provide."*

**Strategic play:** Target Incogni's 2M+ users as a warm audience — they are already privacy-conscious and paying for security tools.

---

### IsItDangerous — Not a Real Competitor

**What they do:** WhatsApp-based message and URL verification. Forward a suspicious link, receive Safe/Caution/Dangerous verdict. Built on Payemoji platform.

**Why they are not a threat:**
- Reactive (check after receiving a threat) vs RelayShield proactive
- No dark web monitoring, no breach detection, no telecom layer
- Meta launched native WhatsApp anti-scam tools March 2026 — existential threat to IsItDangerous
- No SMB product, no conversational remediation

---

## 8. Product Roadmap

### Phase 1 — Validate (Months 1-3)
- ✅ Core breach + dark web monitoring (HIBP API)
- ✅ WhatsApp alerts via existing Twilio stack
- ✅ AI conversational remediation (Claude API)
- ✅ Password breach checking (Pwned Passwords — free)
- ✅ Domain scanner for SMB onboarding
- ✅ SMS/phone number exposure detection
- ✅ Carrier change monitoring (Twilio Lookup)
- ✅ Consumer tier ($12/month founding / $15 standard) + SMB tier ($79/month founding / $99 standard)
- ✅ Self-serve landing page with founding member pricing offer (first 50 SMBs)
- ✅ Stripe subscription billing
- ✅ Instrument everything for dataset building

### Phase 2 — Differentiate (Months 4-8)
- Telecom layer: SIM swap detection, carrier signals, port-out alerts
- Telegram Bot integration + agentic workflows
- Secret/API key exposure monitoring (GitGuardian API)
- Dark web data sale monitoring (Flare API)
- Domain spoofing/typosquatting detection (dnstwist — free)
- Proprietary heuristics engine
- SMB team dashboard + risk scoring
- Published accuracy benchmarks
- Industry breach reports (first B2B data product)
- SS7 advanced monitoring
- **Close founding member offer — new customers pay standard pricing ($99/$179)**

### Phase 3 — Monetize the Moat (Months 9-18)
- Cloud account anomaly detection (Google Workspace + Microsoft 365)
- Predictive analytics engine
- Threat intelligence API (separate revenue stream)
- Agentic Telegram workflows
- White-label licensing (carriers, insurers, SMB platforms)
- Dataset licensing to research partners
- Anonymized risk benchmarks for research partnerships

---

## 9. Telegram Agentic Workflows (Phase 2 Roadmap)

- **Autonomous Breach Patrol Bot** — proactively messages users when new breach data detected
- **Scheduled Risk Briefings** — weekly identity risk score summary
- **Interactive Remediation Flows** — rich inline buttons for step-by-step recovery
- **Team Alert Routing** — SMB admins get Telegram notifications, employees get WhatsApp
- **Agentic Identity Audit** — user triggers full scan via Telegram command
- **Threat Intelligence Briefings** — daily/weekly digest of emerging breach campaigns
- **Exfiltration Alert Routing** — secret exposure and dark web sale alerts via Telegram for SMB admins

---

## 10. Dataset Monetization Roadmap

| Path | Timeline | Model |
|---|---|---|
| Threat intelligence API | Phase 3 | Per-call or subscription |
| Industry breach reports | Phase 2 | B2B report licensing |
| Anonymized risk benchmarks | Phase 2 | Research partnerships |
| White-label data feeds | Phase 3 | Enterprise licensing |
| Exfiltration pattern dataset | Phase 3 | Enterprise licensing |

**Key principle from Day 1:** Instrument everything. Log signals, outcomes, and remediation responses in structured formats. Every interaction builds the proprietary dataset.

---

## 11. Technical Architecture

### Tech Stack
| Component | Tool |
|---|---|
| Breach monitoring | HaveIBeenPwned API ($4.50/month) |
| Secret scanning | GitGuardian API (Phase 2) |
| Dark web monitoring | Flare API (Phase 2) |
| Domain spoofing | dnstwist open source (Phase 2) |
| Alert delivery | Twilio WhatsApp (existing stack) |
| AI remediation | Claude API (Anthropic) |
| Database | AWS DynamoDB |
| Compute | AWS Lambda |
| Scheduler | AWS EventBridge |
| Payments | Stripe |
| Secrets | AWS Secrets Manager |
| Landing page | Carrd.co ($19/year) |

### DynamoDB Tables
- `relayshield_users`
- `relayshield_monitored_emails`
- `relayshield_breach_alerts`

### Monthly Running Costs

**Phase 1:**
| Service | Cost |
|---|---|
| HIBP API | $4.50 |
| Twilio WhatsApp | ~$10 |
| Claude API | ~$15 |
| AWS (Lambda + DynamoDB) | ~$2 |
| Secrets Manager | ~$2 |
| Carrd | $1.58 |
| **Total** | **~$35/month** |

**Phase 2 (additional):**
| Service | Cost |
|---|---|
| GitGuardian API | ~$29 |
| Flare API | ~$75 |
| dnstwist | $0 |
| **Phase 2 addition** | **~$104/month** |
| **Phase 2 total** | **~$139/month** |

---

## 12. Backend Security Architecture

### Data Minimisation Principles
- Never store actual passwords
- Stripe handles all payment data (store Stripe customer ID only)
- Use anonymised UUIDs in third-party tools
- No CRM or Salesforce with PII access (Aura's breach vector)
- Encrypt sensitive fields at field level using AWS KMS

### AWS Security Controls
- DynamoDB: AWS KMS Customer Managed Keys
- IAM: Least privilege per Lambda function
- Lambda: Runs inside VPC, private subnet
- API Gateway: AWS WAF enabled
- CloudTrail: All API calls logged
- GuardDuty: Threat detection enabled
- Deletion Protection: ON for all DynamoDB tables
- Point-in-Time Recovery: ON for all DynamoDB tables
- $1 billing alert on all AWS accounts

### Third-Party Vendor Policy
| Vendor | Access Level |
|---|---|
| Stripe | Payment processing only |
| Twilio | Phone numbers, delivery metadata |
| Anthropic | Breach type/category (no user PII) |
| HIBP | Email addresses for breach lookup |
| GitGuardian | Domain/repo names only (Phase 2) |
| Flare | Domain names for monitoring (Phase 2) |

---

## 13. Landing Page Structure

**Headline:**
> *"Actionable Security, Delivered to Your WhatsApp."*

**Sub-headline:**
> *Your credentials are probably already on the dark web. RelayShield finds them first — then walks you through exactly what to do next, right in your WhatsApp. Real-time breach monitoring with telecom-layer detection. Step-by-step remediation delivered to the device you already use.*

**Feature bullets:**
- 🔍 Real-time breach & dark web monitoring
- 📱 Instant WhatsApp alerts with AI remediation
- 🔐 Secret & API key exposure detection (Phase 2)
- 🕵️ Domain impersonation monitoring (Phase 2)
- 📡 Telecom-layer SIM swap protection (Phase 2)

**Trust signal:**
> *"Built by a 25-year telecom security professional. Already using Incogni or Aura? Now add the protection layer they can't provide."*

**Founding member urgency block:**
> *"🔒 Founding Member Pricing — First 50 businesses only. Lock in Business Shield at $79/month forever. Standard price is $99/month. Spots remaining: [X]"*

**Dual CTA:**
- "Protect My Business →"
- "Join Early Access →"

---

## 14. Validation Strategy

### Community Targets
| Community | Message Angle |
|---|---|
| r/privacy | Telecom-layer threats + WhatsApp remediation |
| r/personalfinance | Cost of identity theft vs $12/month founding rate |
| r/cybersecurity | Architecture credibility + exfiltration detection |
| r/smallbusiness | Business credential + secret exposure awareness |
| r/scams | Value-first: what to do if breached |
| r/devops | API key and secret exposure monitoring angle |
| LinkedIn | 25-year telecom expertise content |

### Aura Breach Timing Play (Active Now — March 2026)
Post on r/personalfinance and r/privacy:
> *"Aura just had a 900,000-record breach. If you're reconsidering your identity protection, here's what RelayShield does differently — including the telecom threats and exfiltration signals Aura still can't detect."*

**Window:** Approximately 60-90 days from March 2026.

### Validation Metrics
| Signal | Meaning |
|---|---|
| 50+ email signups | Strong interest — proceed to MVP |
| 5+ pre-orders | Real validation — build immediately |
| High click, low signup | Messaging problem — tweak headline |
| DMs asking questions | These are your first customers |

---

## 15. 6-Week MVP Build Plan

| Week | Milestone | Hours |
|---|---|---|
| 1 | Breach detection engine (HIBP + Lambda + DynamoDB) | 5 |
| 2 | WhatsApp alert delivery (Twilio integration) | 5 |
| 3 | Claude AI conversational remediation | 5 |
| 4 | Stripe payments + Carrd landing page | 5 |
| 5 | SMB tier + end-to-end testing | 5 |
| 6 | First paying customer acquisition | 5 |

**Total: 30 hours across 6 weeks to first revenue**

---

## 16. Account and Infrastructure Setup

### Accounts Created
- ✅ relayshieldadmin@gmail.com — secured with MFA + authenticator
- ✅ HIBP API key — purchased ($4.50/month, Pwned 1)
- ✅ HIBP API key stored in AWS Secrets Manager (relayshield/hibp_api_key)
- ⬜ relayshield.ai — register on Namecheap
- ⬜ relayshield.net — register on Namecheap
- ⬜ Anthropic account (Week 3)
- ⬜ Stripe account (Week 4)
- ⬜ Carrd account (Week 4)
- ⬜ GitGuardian account (Phase 2)
- ⬜ Flare account (Phase 2)

### AWS Resources (SmartAsst account, tagged Project: RelayShield)
- ✅ relayshield_users (DynamoDB)
- ✅ relayshield_monitored_emails (DynamoDB)
- ✅ relayshield_breach_alerts (DynamoDB)
- ✅ relayshield-breach-check (Lambda, Python 3.14)
- ✅ relayshield/hibp_api_key (Secrets Manager)
- ⬜ IAM policy: relayshield-breach-check-policy
- ⬜ Lambda timeout: 3 minutes
- ⬜ EventBridge scheduler (Week 1 completion)
- ⬜ Test record in relayshield_monitored_emails

---

## 17. Secrets Manager Keys

| Secret Name | Status |
|---|---|
| relayshield/hibp_api_key | ✅ Created |
| relayshield/twilio_account_sid | ⬜ Week 2 |
| relayshield/twilio_auth_token | ⬜ Week 2 |
| relayshield/anthropic_api_key | ⬜ Week 3 |
| relayshield/stripe_secret_key | ⬜ Week 4 |
| relayshield/gitguardian_api_key | ⬜ Phase 2 |
| relayshield/flare_api_key | ⬜ Phase 2 |
