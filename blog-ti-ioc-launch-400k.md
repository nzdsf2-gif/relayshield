# 400,000 Indicators of Compromise. One API Call.

*Why real-time threat intelligence shouldn't cost $25,000 a year*

*Published: [DATE] | Cross-posted: LinkedIn · n8n Community · X · Farcaster*

---

Most security teams know their organization has been breached before they get the alert.

The attacker moved laterally for 48 hours. The credential was for sale on a criminal forum for two weeks. The domain lookalike was registered three days before the phishing campaign launched.

The intelligence existed. It just wasn't in the right hands at the right time.

That's the problem RelayShield was built to solve.

---

## What We Launched

This week we crossed 400,000 indicators of compromise in our corpus — active threat data spanning credential exposure, infostealer malware, ransomware victims, network-layer threats, and live dark web intelligence.

All of it is queryable through a single API. Pay per call. No $25,000/year contract required.

Here's what that looks like in practice.

---

## What You Can Detect

**Credential exposure**
Know within hours — not weeks — when an email address appears in a breach or criminal channel dump. We track 400K+ exposed records with breach date, affected data classes, and severity scoring.

**Infostealer malware hits**
450+ malware families tracked. When we flag an infostealer hit, we tell you *which* malware stole the credential and *what else* was in the same log — because a password reset doesn't fix a stolen session cookie.

**Active session hijack risk**
The attack vector behind 90%+ of MFA bypasses isn't a stolen password. It's a stolen session token. Our session risk endpoint detects active OAuth and session cookie exposure before attackers use it.

**Ransomware victim intelligence**
Know if a vendor, customer, or target organization has appeared on a ransomware gang's victim list — before they announce it publicly. Average lead time: 24–72 hours ahead of public disclosure.

**Supply chain risk**
One API call. Up to 10 vendor domains. Returns a composite risk score combining breach history, infostealer exposure, and dark web signals — so your MSP or security team can run weekly vendor sweeps automatically.

**IOC lookup**
400K+ indicators spanning malicious IPs, domains, URLs, file hashes, and wallet addresses. Enriched with threat actor attribution, confidence scoring, and ATT&CK technique mapping.

**Identity correlation**
An email doesn't exist in isolation. Our identity graph links exposed emails to associated phone numbers, domains, and usernames seen alongside them in criminal channel dumps — turning one compromised identifier into a full exposure picture.

---

## How It's Different

Most threat intelligence products are built for analysts who live in dashboards. RelayShield is built for workflows.

Every capability above is available as an API endpoint — designed to be called from n8n, Zapier, Tines, your SIEM, your onboarding flow, or any custom integration. If you can make an HTTP request, you can use it.

This week we launched as a verified node on **n8n Cloud** — available directly from the canvas, no manual install. We also submitted to the **Zapier App Directory** with 12 actions and a real-time breach alert trigger.

A workflow that would have required a SOC analyst and an enterprise TI subscription now runs automatically:

→ New employee onboarded → breach + infostealer check on their email → if stealer hit found, check for active session exposure → if risk detected, flag for IT review and enforce MFA

→ Weekly vendor sweep → supply chain risk check across your top 10 vendors → if any show breach + stealer overlap → auto-create ticket and Slack alert

→ Real-time alert → IOC lookup on suspicious IP from SIEM → if matched, auto-block and log with threat actor context

---

## Who It's For

**MSPs** running security services for SMB clients who can't afford enterprise TI pricing.

**Developers** building security-aware products — onboarding flows, fraud detection, account protection.

**Security analysts** who want API access to TI data without a six-figure contract.

**Automation builders** using n8n, Zapier, or Tines who want real security intelligence in their workflows.

---

## Pricing

Metered, pay-per-call. No subscription required to start.

| Capability | Cost |
|---|---|
| Breach check | $0.10 |
| Infostealer exposure | $0.50 |
| SIM swap detection | $0.25 |
| Supply chain risk | $0.10/vendor |
| Session risk | $0.30 |
| IOC lookup | $0.05 |
| Identity graph | $0.35 |
| Ransomware risk | $0.40 |
| Domain lookalike | $0.30 |

API keys at [relayshield.net/developers](https://api.relayshield.net/developers).

For teams needing predictable monthly costs:

**TI Starter — $499/mo**
For MSPs and enterprises building internal SOC platforms. 10,000 TI API calls/month, full IOC lookup, CVE intelligence, and STIX/TAXII feed access. Ideal for teams running automated enrichment pipelines across a fixed client base.

**TI Unlimited — $999/mo**
For MSPs managing multiple SMB clients who need unlimited API calls without tracking per-call costs. Run daily breach sweeps, weekly vendor risk reports, and real-time IOC enrichment across your entire book of business — no metering, no surprises.

Both plans coming soon to AWS Marketplace.

---

*RelayShield — security intelligence for teams that can't afford to wait for enterprise pricing.*

*[Get your API key →](https://api.relayshield.net/developers)*
