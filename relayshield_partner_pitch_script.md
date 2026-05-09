# RelayShield Partner Pitch Script
### Tradeshow Edition — May 2026

---

## Core 30-Second Opener (all audiences — lead with this)

> "Every important account your customers own — their email, their bank, their point of sale system, their WhatsApp, their Telegram — is protected by a phone number. When that number is compromised, everything falls. RelayShield is the monitoring layer that sits between the carrier and those accounts. We detect the attack the moment it starts — SIM swap, credential breach, phishing domain, stolen OAuth token — and we deliver real-time, plain-English guidance directly to WhatsApp or Telegram. We have a live bot running on Telegram today. No app to download. No dashboard to log into. The alert finds them."

*Pause. Let them respond. Then branch by audience.*

---

## Audience 1 — Telcos Selling B2B/B2C Services

**Hook:**
> "Your customers call you after their number gets hijacked. By then the damage is done. RelayShield is the service you offer before that call ever happens."

**Speaking Points:**

- We monitor at the identity layer — breach exposure, SIM swap events, port-out fraud, phishing infrastructure — and we alert on the carrier's behalf before the account takeover completes
- When a SIM swap fires, we tell the customer: lock your SIM PIN, call your carrier's fraud line, and here's the number. We drive that call *to you* — which is a customer retention event, not a complaint call
- Carrier-specific guidance already built in: AT&T, T-Mobile, Verizon hardening steps delivered per subscriber automatically
- Alerts delivered to WhatsApp or Telegram — whichever channel the subscriber already uses. Our Telegram bot (@RelayShield_bot) is live today
- White-label and co-brand paths available — your brand, your customer relationship, our detection engine
- Revenue share model structured for wholesale distribution

**Close:**
> "You already own the carrier relationship. We give you the security intelligence layer that makes it defensible. That's a new revenue line and a churn reduction tool in one."

---

## Audience 2 — Enterprise SMB IT Teams

**Hook:**
> "You're protecting the network perimeter. But every employee's phone number is an attack surface you don't control — and one SIM swap away from a full credential bypass."

**Speaking Points:**

- RelayShield monitors every employee account: breach exposure, SIM swap, phishing domains spoofing your brand, OAuth tokens stolen from breached SaaS tools your team uses
- The moment an employee is hit, you get a co-notification — breach name, severity, affected account — before they even know
- We detect attack chains, not just individual events. If an employee's credentials appear in a breach and then someone attempts a SIM swap 48 hours later, we flag the coordinated attack before it completes
- Employees can receive alerts on WhatsApp or Telegram — including via our live @RelayShield_bot. No app to install, no portal to provision
- Employee offboarding: send REMOVE via WhatsApp or Telegram — we deactivate monitoring and auto-send a 6-step security checklist (revoke OAuth, rotate shared credentials, audit SaaS admin rights, recover devices)
- Seat-based business tiers. Admin dashboard via WhatsApp or Telegram — no new tool to learn

**Close:**
> "You can't put a firewall on an employee's SIM card. We can. It's $9 per seat per month at Business Basic. You're probably spending more than that on the coffee in the break room."

---

## Audience 3 — SMB Business Owners (No IT Staff)

**Hook:**
> "You don't need to understand cybersecurity. You need to know the moment someone is trying to steal from you — and exactly what to do about it."

**Speaking Points:**

- Everything your business runs on is behind a phone number: your bank account, your email, your point of sale system, your WhatsApp. One SIM swap and an attacker owns all of it before you open for business
- When something goes wrong, RelayShield sends you a WhatsApp or Telegram message. Not a 40-page report — a message. In plain English. "Your email appeared in a data breach. Here's what was exposed. Here's what to do in the next 10 minutes."
- Our Telegram bot is live right now at @RelayShield_bot — if you use Telegram, you can start there without ever touching WhatsApp
- We cover your employees too. If someone on your team gets targeted — or you need to offboard someone in a hurry — you handle it from the same WhatsApp or Telegram conversation. No IT department required
- We watch for fake versions of your business domain. If someone registers a lookalike of your website to scam your customers, you hear about it that day
- Business Starter is $24.99 a month — less than one fraudulent transaction

**Close:**
> "Your insurance company isn't going to cover you if you didn't have monitoring in place. We are the monitoring. And we live in your phone."

---

## Audience 4 — MSPs and MSSPs

**Hook:**
> "Identity monitoring is the gap in every stack you're managing. Your clients ask you about it. You're probably improvising the answer right now."

**Speaking Points:**

- RelayShield fills the identity layer without you building it: breach monitoring, SIM swap detection, domain lookalike scanning, OAuth supply chain watchlist, multi-vector attack correlation — all live today on AWS, API-first
- Alerts delivered to WhatsApp and Telegram simultaneously for Business Basic+ — dual-channel redundancy against account takeover. @RelayShield_bot is operational today
- Multi-tenant architecture with UUID-based client isolation. Each enterprise org is isolated by `org_id` — you can never accidentally cross client data. MSP admin sees seat counts and org status, never client security data
- When any managed employee is hit, the alert goes to the employee, to their company admin, and — at Business Shield Pro — to you. Three-layer notification chain
- REST API for RMM/PSA/SIEM integration. Five endpoints live today on AWS API Gateway. RapidAPI listing for self-serve onboarding; enterprise key management available on request
- MCP server available on PyPI — AI-native teams can integrate via Claude, Cursor, or any MCP-compatible agent today
- Pricing scales at MSP margins. We're structured for resale

**Speaking Points for technical MSSPs:**
- Six active attack chains modeled: smishing → SIM swap, breach + SIM swap, breach + OTP interception, domain phishing → breach, OAuth supply chain, coordinated multi-vector. Predictive warnings fire on the *first* signal before the chain completes
- API async pattern for file and URL scanning — submit/poll, stays within API Gateway's 29s limit
- All PII field-encrypted at rest with AWS KMS CMKs. CloudTrail, Config, PITR enabled. OIDC-based CI/CD. SOC posture documented

**Close:**
> "You can resell this tomorrow. We handle the detection, the alerting, the remediation guidance, and the infrastructure. You handle the client relationship. That's the split."

---

## Universal Objection Handlers

| Objection | Response |
|---|---|
| "We already have a breach monitoring tool" | "Does it correlate a breach with a SIM swap 48 hours later and warn the user before the second attack? We do. That's the gap." |
| "Our customers don't use WhatsApp" | "Telegram works too — our bot is live at @RelayShield_bot today. And they're already on one of them. No app install, no portal login — that's the adoption advantage." |
| "What about enterprise compliance?" | "KMS field encryption, CloudTrail audit trail, DynamoDB PITR, OIDC CI/CD. E&O + Cyber + AI insurance in place. Security posture doc available." |
| "How do you handle employee privacy?" | "Employees receive alerts about their own accounts only. Admin co-notification covers breach name and severity — no personal message content is shared upward." |
| "What's the competitive moat?" | "25 years of carrier-layer expertise. We model attack chains that start at the telco before they reach the account. Nobody else is looking at that seam." |

---

## Leave-Behind One-Liner (badge, card, booth sign)

> **RelayShield** — *The monitoring layer between your carrier and everything that matters.*
> Real-time breach, SIM swap, phishing, and OAuth attack detection → WhatsApp or Telegram.
> `relayshield.net` · Telegram: @RelayShield_bot · REST API: RapidAPI · MCP server: PyPI
