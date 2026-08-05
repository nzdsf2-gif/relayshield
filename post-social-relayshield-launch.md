> **STATUS: DRAFT — Post same day as HN/PAWN**
> **Post order: HN first (morning) → PAWN → social (afternoon)**

---

## X / TWITTER (280 chars)

RelayShield: breach check, SIM swap detection, infostealer exposure, domain lookalikes + 1.4M+ IOC lookup — REST API for SOC teams and security automation engineers. Now a verified n8n node.

🔗 api.relayshield.net/developers

---

## X — THREAD (for more reach, post as replies to the above)

**2/** The attack chain that keeps succeeding:
→ credential leaked in infostealer log
→ carrier SIM swap executed
→ account taken over
→ funds gone

Every piece of telemetry to detect it earlier exists. It just wasn't wired into a callable API. Until now.

**3/** Six endpoints:
- Breach exposure
- Infostealer log market check (24-72h ahead of HIBP)
- Carrier SIM swap detection
- Domain lookalike scan
- OAuth supply chain watchlist
- IOC lookup (1.4M+ indicators: Telegram, ThreatFox, URLhaus, CISA KEV, Feodo, MalwareBazaar)

**4/** Just went live as a verified n8n node. Drop it into your existing automation workflow in minutes.

Also works with Tines, Make, or anything that POSTs JSON.

$499/mo — 10K TI API calls, in-house SOC teams
$999/mo — unlimited, MSSPs + multi-client pipelines

api.relayshield.net/developers

---

## FARCASTER (longer form, FC audience tolerates more depth)

Most SOC teams are flying blind on the identity layer.

They have EDR, email security, a SIEM. What they don't have is visibility into SIM swap activity at the carrier level, credential exposure in infostealer log markets before it hits public aggregators, or a live IOC feed sourced directly from criminal Telegram channels.

RelayShield is a REST API (and now a verified n8n node) built to close that gap:

— Breach exposure
— Infostealer log market checks (source channels, not downstream aggregators — 24-72h earlier signal)
— Carrier-level SIM swap detection
— Domain lookalike scanning
— OAuth supply chain exposure
— IOC lookup across 1.4M+ indicators from criminal Telegram channels, ThreatFox, URLhaus, CISA KEV, Feodo Tracker, and MalwareBazaar

For in-house security teams, lean SOC environments, MSSPs, and anyone running SOAR workflows who needs enrichment data that actually moves.

api.relayshield.net/developers

---

## MASTODON (infosec.exchange — tag appropriately)

RelayShield: breach, SIM swap, infostealer, domain lookalike, OAuth supply chain, and live IOC lookup — REST API + verified n8n node.

1.4M+ IOCs from criminal Telegram channels, ThreatFox, URLhaus, CISA KEV, Feodo Tracker, and MalwareBazaar. Infostealer signal runs 24-72h ahead of public aggregators.

$499/mo — in-house SOC teams and lean security environments
$999/mo — MSSPs and multi-client enrichment pipelines

api.relayshield.net/developers

#infosec #threatintelligence #cybersecurity #n8n #SOAR #SIMswap

---

## REDDIT — r/n8n

**Title:** RelayShield is now a verified n8n node — breach checks, SIM swap detection, infostealer exposure, and 1.4M+ IOC lookup in your workflows

**Body:**
Hey r/n8n — just got notification that n8n-nodes-relayshield has been approved and is scheduled for inclusion in the next release batch (within 14 days).

**What it adds to your workflows:**
- Breach exposure check (email)
- Infostealer log market check (are credentials actively being sold right now?)
- Carrier SIM swap detection
- Domain lookalike scan
- OAuth supply chain watchlist
- IOC lookup — 1.4M+ indicators from criminal Telegram channels, ThreatFox, URLhaus, CISA KEV, Feodo Tracker, and MalwareBazaar

**Example workflow:**
Schedule → breach check on employee email list → IF exposed → Slack alert + infostealer check → IF in log markets → escalate to ticket

**Who it's for:** in-house security teams, MSSPs, and anyone building detection or enrichment workflows. Pay-per-call for detection endpoints, $499/mo for TI access.

**Install:** search `n8n-nodes-relayshield` in community nodes, or npm install it directly.

Happy to answer questions about the node or the API.

Docs: api.relayshield.net/developers

---

## REDDIT — r/netsec / r/cybersecurity

**Title:** I built a threat intelligence API to close the gap between carrier-level identity attacks and the tools security teams actually use — Show HN style writeup inside

**Body:**
Most security teams have solid coverage on endpoint and email. What they don't have is visibility into the identity layer where SIM swap fraud, infostealer log markets, and carrier-level attacks operate.

RelayShield is a REST API built to change that.

**Capabilities:**
- Infostealer log market exposure (monitoring source channels, not downstream aggregators — 24-72h earlier signal)
- Carrier-level SIM swap / port-out detection
- Domain lookalike scanning
- OAuth supply chain exposure check
- Live IOC lookup: 1.4M+ indicators from criminal Telegram channels, ThreatFox, URLhaus, CISA KEV, Feodo Tracker, and MalwareBazaar — cross-referenced for ransomware activity

**Stack:** AWS Lambda, DynamoDB, continuous Telegram ingestion pipeline.

Just went live as a verified n8n node for SOAR/automation integration. REST API works with anything that POSTs JSON.

For in-house SOC teams: $499/mo for 10K TI API calls. For MSSPs running multi-client pipelines: $999/mo unlimited. Pay-per-call for detection endpoints.

I'm genuinely interested in what data points practitioners would want in the IOC response payload — happy to discuss the threat intel side in detail.

Docs and free tier: api.relayshield.net/developers

---

## SLACK — Tines Community (#integrations or #tools)

**RelayShield REST API — breach check, SIM swap detection, infostealer exposure, and 1.4M+ IOC lookup for your Tines stories**

If you're building detection or enrichment stories in Tines, RelayShield adds six threat intelligence capabilities via HTTP Request action today — no custom integration required.

**What's available:**
• `/v1/metered/breach` — email breach exposure, live
• `/v1/metered/infostealer` — credential exposure in criminal log markets, 24-72h ahead of public aggregators
• `/v1/metered/sim-swap` — carrier-level SIM swap / port-out detection
• `/v1/metered/domain` — typosquat and lookalike domain scan
• `/v1/metered/oauth-watchlist` — OAuth supply chain exposure for breached credentials
• `/v1/intel/telegram` — IOC lookup across 1.4M+ indicators (criminal Telegram channels, ThreatFox, URLhaus, CISA KEV, Feodo Tracker, MalwareBazaar)
• `/v1/intel/cve` — CISA KEV lookup by CVE ID or keyword, ransomware-flagged

All endpoints return structured JSON. Authentication is a single API key header (`X-RS-API-KEY`).

**Example story:** Phishing report intake → domain lookalike scan on reported sender domain → IF match found → auto-enrich ticket + escalate

Built for security automation teams, MSSPs running multi-client detection workflows, and lean SOC environments that need enrichment data without annual contracts.

$499/mo — 10K TI API calls (in-house SOC)
$999/mo — unlimited (MSSPs / multi-client)
Pay-per-call for detection endpoints

Docs and free tier: api.relayshield.net/developers — happy to help anyone wire it into an existing story.

---

## SLACK — MISP Community (#tools or #integration)

**RelayShield — 1.4M+ IOC REST API covering domains, IPs, URLs, and malware hashes. Queryable in real time.**

For teams using MISP for threat intel correlation, RelayShield adds a live IOC enrichment layer via REST API — useful for enriching incoming events or cross-referencing indicators before they're ingested.

**Feed sources (updated daily):**
• 20+ criminal Telegram channels — infostealer logs, credential dumps, SIM swap infrastructure
• ThreatFox (abuse.ch) — malware IOCs tagged by family
• URLhaus (abuse.ch) — malicious URLs and domains
• CISA KEV — exploited vulnerabilities, cross-referenced for ransomware activity
• Feodo Tracker aggressive — ~8K botnet C2 IPs (Emotet, QakBot, Dridex, IcedID, TrickBot)
• AbuseIPDB — confidence-filtered IP abuse reports
• MalwareBazaar (abuse.ch) — malware sample SHA256 hashes

**Query endpoint:** `POST /v1/intel/telegram` — accepts domain, IP, email, phone, or wallet address, returns source, category, and malware family where available.

1.4M+ indicators. Runs 24-72h ahead of public aggregators for the threat types it covers.

$499/mo for 10K API calls / $999/mo unlimited. Pay-per-call also available.

Docs: api.relayshield.net/developers

---

## SLACK — OpenCTI Community (#integrations or #general)

**RelayShield — real-time threat intelligence API for enriching OpenCTI observables**

If you're using OpenCTI for intel management, RelayShield can enrich observables via REST API — domains, IPs, URLs, email addresses, malware hashes, and wallet addresses against a continuously updated IOC database.

**1.4M+ indicators sourced from:**
• Criminal Telegram channels (infostealer, credential dump, SIM swap infrastructure)
• ThreatFox, URLhaus, MalwareBazaar (abuse.ch feeds)
• CISA Known Exploited Vulnerabilities — with ransomware activity flags
• Feodo Tracker — botnet C2 IPs
• AbuseIPDB — crowdsourced IP reputation

**Also available:**
• Carrier-level SIM swap / port-out detection
• Infostealer log market exposure — 24-72h ahead of public breach databases
• Domain lookalike and typosquat scanning
• OAuth supply chain watchlist

All via REST, structured JSON responses, single API key. No SDK required — works with any HTTP connector.

For security teams building enrichment pipelines, MSSPs correlating intel across client environments, and SOC analysts who need faster signal on the identity-layer threat types that SIEM data doesn't cover.

Docs and free tier: api.relayshield.net/developers

---

## n8n COMMUNITY FORUM

**Title:** RelayShield node just approved — breach monitoring, SIM swap detection, and threat intel in your n8n workflows

**Body:**
Excited to share that n8n-nodes-relayshield has been approved as a verified node and is scheduled to appear in the next n8n release (within 14 days).

**What it adds to your n8n toolkit:**

7 operations in one node:
1. Breach Check — email breach exposure
2. Infostealer Check — credential exposure in criminal log markets
3. SIM Swap Detection — carrier-level port-out detection
4. Domain Lookalike Scan — typosquat and homoglyph detection
5. OAuth Watchlist Check — supply chain exposure via OAuth authorizations
6. Threat Intelligence — IOC Lookup (domain, IP, email, phone, wallet) — 1.4M+ indicators
7. Threat Intelligence — CVE Lookup (CISA KEV by CVE ID or keyword)

**Built for:** security automation engineers, SOC teams running n8n for enrichment workflows, and MSSPs who need scalable TI access across client environments.

**Example workflow:**
Schedule node → RelayShield Breach Check (employee email) → IF breach_count > 0 → RelayShield Infostealer Check → IF exposed → Gmail/Slack alert

**Credentials:** Just your RelayShield API key in the credential. Test connection is built in.

You can already install it via community nodes (search `n8n-nodes-relayshield`) or npm. Will appear in the native node library within 14 days.

API docs + key: api.relayshield.net/developers

Happy to help anyone build workflows around it.
