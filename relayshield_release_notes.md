# RelayShield — Release Notes

*Customer-facing. Plain language. No internal pricing detail, architecture, or competitive positioning.*

---

## June 2026 — Major Release

### Threat Intelligence Corpus — 1,000,000+ Indicators

Our threat intelligence database now exceeds **1,000,000+ indicators** — IP addresses, domains, URLs, and file hashes — drawn from 20 authoritative feeds updated daily. We track **1,000+ malware families** including LummaC2, RedLine, Vidar, Emotet, QakBot, and 990+ others.

Every indicator is enriched with:
- Threat actor attribution (189 MITRE ATT&CK groups)
- Confidence scoring
- MITRE ATT&CK technique mapping
- 365-day retention

---

### New: Bulk IOC Enrichment

**`POST /v1/metered/bulk-ioc`** — Submit up to 100 IP addresses, domains, URLs, or file hashes in a single call. Ideal for SIEM log enrichment pipelines where checking each indicator individually would be impractical.

Returns matched/unmatched status, malware family, threat actor, confidence score, and first/last seen timestamps for each.

**Price:** $0.50 per batch (up to 100 IOCs)

---

### New: IOC Pivot — Lateral Infrastructure Discovery

**`POST /v1/metered/ioc-pivot`** — Given one known-malicious indicator, discover related infrastructure sharing the same malware family. If you find one LummaC2 C2 IP, pivot to uncover the rest of the campaign's infrastructure before it's widely blocked.

**Price:** $0.20 per call

---

### New: Brand Protection Monitoring

**`POST /v1/metered/brand-monitor`** — Scan our full IOC corpus for your organisation's brand name patterns. Returns phishing domains impersonating your brand, malware C2 infrastructure using your name, and dark web mentions. Helps you detect brand abuse before your customers encounter it.

**Price:** $0.25 per call

---

### New: Threat Actor Profiles

**`GET /v1/intel/actor`** — Full MITRE ATT&CK profile for any named threat actor: tactics, techniques, target sectors, origin, and associated indicators from our live corpus. Available to TI subscribers.

---

### New: Trending Threats

**`GET /v1/intel/trending`** — The top indicators seen across all feeds in the last 24 or 48 hours. See what's actively spreading right now, grouped by indicator type. Available to TI subscribers.

---

### New: Agentic AI Identity Risk

**`POST /v1/metered/bulk-identity-risk`** — Score the identity risk of up to 10 organisational domains and up to 5 individual identities (service accounts, agent emails) per domain in a single call.

Designed for teams running AI copilots, agent workflows, or automated systems that need to know whether the identities their systems act on behalf of are currently exposed in breach databases, infostealer logs, or active session theft records.

Each domain returns a risk score (0–100, grade A–F) across six dimensions. Each individual identity returns signals from breach history, infostealer detection, and stolen session records. If any agent identity is critically exposed, the domain risk is automatically elevated.

**Price:** $2.00 per call

---

### Early Warning Intelligence

**`POST /v1/metered/threat-actor`** now surfaces CVE proof-of-concept discussion in criminal channels **before** NVD publication — typically 24–72 hours ahead of public disclosure. Combined with our daily CISA KEV ingestion (1,600+ actively-exploited CVEs), this gives you a window to act before patches are available.

---

### Third-Party Risk Score

**`POST /v1/metered/supply-chain`** returns a composite risk score for up to 10 vendor domains per call — combining breach exposure, infostealer hits, and dark web signals. Use it in vendor onboarding workflows or weekly sweeps of your supply chain.

---

### WhatsApp Alerts — Window Reliability

We've resolved an issue where WhatsApp's 24-hour messaging window could silently close between alert events, causing some notifications to fail without error. All subscribers now receive a weekly status check-in — tapping the confirmation button keeps your alert channel active. If you haven't received a check-in message, please message the bot to re-open the channel.

---

### n8n Integration — Version 0.1.14

The RelayShield n8n community node has been updated. New operations available in this version:
- Identity Graph correlation
- Ransomware Risk assessment
- Session Risk / AiTM detection
- Supply Chain risk scoring
- OAuth Watchlist (upgraded with live stealer log corpus)

Search **"RelayShield"** in the n8n community nodes library to install or update.

---

## July 2026 — SIEM Integration & Crypto Shield Mobile Update

### New: STIX/TAXII 2.1 and MISP Feed Export

Two new ways to pull the full IOC corpus directly into your existing security tooling — no custom integration work required.

**`GET /v1/intel/taxii/*`** — A standards-compliant TAXII 2.1 server. Point Splunk, Sentinel, Elastic, or QRadar's built-in TAXII client at this endpoint and IOCs arrive as STIX 2.1 Indicator objects on your existing schedule.

**`GET /v1/intel/misp/event`** — The same IOC corpus as a native MISP Event, for teams running MISP rather than a TAXII-based pipeline. Both formats support incremental pulls (`added_after` + pagination) so you only ingest what's new. Available to TI subscribers.

---

### New: Shareable Risk Report Links

**`POST /v1/report/share`** — Turn any wallet scan, domain check, or vendor sweep result into a persistent URL. Generating a link requires a subscription; viewing a shared link is public, no login required — paste it into a client ticket, an incident report, or a security write-up the same way you'd link to a VirusTotal or Shodan result page.

---

### Crypto Shield Mobile — NFT Security & XRP Support

Crypto Shield, our consumer wallet security app for Solana, EVM, TON, and Bitcoin, adds two new scan types this release:

- **NFT Security** — flags malicious or fake NFT contracts (the category of scam where a drainer contract is disguised as an airdropped "reward" NFT), separate from the existing NFT floor-price tracking.
- **XRP Address** — balance and fraud-advisory lookups for native XRP Ledger accounts.

Crypto Shield is read-only — it never asks for your seed phrase or private keys, and every alert is cryptographically verified before it reaches your phone.

---

## How to Access New Endpoints

All endpoints above are available immediately to existing subscribers. Log in to **api.relayshield.net/developers** to view your API key and the full endpoint reference.

TI subscription endpoints (`/v1/intel/actor`, `/v1/intel/trending`) require an active TI Starter or TI Unlimited plan.

Questions? Reply to this message or contact support@relayshield.net

---

*RelayShield — Identity protection built for what comes after the breach.*
