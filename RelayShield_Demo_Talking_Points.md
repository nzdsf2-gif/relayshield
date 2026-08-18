# RelayShield TI Demo — Talking Points
*For: MSP prospects, security-aware developers, enterprise buyer conversations*
*Demo URL: https://relayshield-ti-demo.relayshieldadmin.workers.dev?token=rs-demo-2026*

---

## Opening Frame (30 seconds)

> "Most threat intelligence platforms cost $30,000–$150,000 a year and require a trained analyst to interpret. What I'm going to show you is the same class of signal — MITRE ATT&CK actor profiles, live IOC corpus, stolen credential detection, CVE exposure scoring — accessible via a REST call, starting at $499 a month. Let me walk you through what that looks like in practice."

---

## Tab 1 — Identity Risk Score

**What to say:**
- "Type in any domain. You're running a 6-dimension identity risk assessment in real time against our live corpus."
- "Each dimension maps to a real attack vector — breach exposure tells you what's already in criminal hands; infostealer density tells you how actively that domain is targeted by credential-harvesting malware right now."
- "The CVE Exposure dimension is the one no competitor closes — we cross-reference your domain's vendor stack against CISA KEV, pull EPSS exploit probability, and score it as part of identity risk. Not a separate product."
- "Adobe.com scores CRITICAL 75/100 across 4 dimensions. That's not synthetic — that's live data from HIBP, Hudson Rock, AlienVault OTX, and our own corpus."

**Key proof point:**
Session Exposure score of 10/10 for adobe.com = active stolen session records in our corpus right now. That's SpyCloud's core product. We're delivering it at developer-accessible pricing.

**Objection handle — "We already get breach data from HIBP":**
> "HIBP tells you a breach happened, historically. Our infostealer density dimension tells you credentials are being actively harvested from that domain *today* — that's a Hudson Rock signal, not HIBP. And the CVE dimension adds a layer HIBP has no visibility into. These are three completely different data sources converging into one score."

---

## Tab 2 — Threat Actor Intelligence

**What to say:**
- "Search 'Lazarus Group' — this pulls a full MITRE ATT&CK profile, known TTPs, targeted sectors, and — critically — IOCs from our corpus that are attributed to that actor."
- "For an MSP, this answers the question their clients can't: 'Is the group that just hit Colonial Pipeline targeting anyone in our vertical?'"
- "The actor timeline shows when they were most active. The technique list maps to specific controls — you can walk a client through which of their gaps this actor exploits."

**Key proof point:**
Lazarus Group is the primary DeFi and crypto threat actor — $3B+ stolen. Any crypto-adjacent client should see this query run against their own domain's IOC overlap.

---

## Tab 3 — Trending Threats (IOC Feed)

**What to say:**
- "This is our live IOC corpus — 800K+ indicators ingested from 20+ feeds: CISA KEV, Abuse.ch, AlienVault OTX subscribed pulses, Emerging Threats, and 15 others."
- "The trending view shows what's spiking in the last 24/48 hours. For an MSP running weekly client sweeps, this is your 'what's on fire right now' briefing."
- "The color coding maps directly to threat type — C2 infrastructure, phishing domains, malware hashes, ransomware callbacks. Every IOC is enriched with source attribution."

**Key proof point:**
IOC bulk check endpoint (`/v1/metered/bulk-ioc`) lets an MSP submit 100 IOCs from their SIEM in one call at $0.50 — closing the log enrichment gap that ThreatConnect charges per-seat subscription pricing for.

---

## Tab 4 — Agentic Identity Risk

**What to say:**
- "This is the capability that didn't exist 18 months ago — scoring not just human identities but AI agent and service account identities. The attack surface has changed. You now have AI agents running with API keys, OAuth tokens, and cloud credentials. If those credentials hit criminal stealer logs, your agent is compromised before you know it."
- "Enter your org domain and list your service accounts. We score the domain, then check each identity against breach, infostealer, and our stolen credentials corpus separately."
- "Look at admin@adobe.com — CRITICAL 95/100 with a SERVICE_ACCOUNT finding. That's an Adobe service token appearing in our stealer archive. The domain baseline was 75, but the agent credential exposure elevates overall risk to 95."
- "This is the supply chain risk report your CISO is asking for. One API call."

**Key proof point:**
The elevated score banner — "Domain baseline 75/100 → Elevated 95/100 due to agent credential exposure" — is exactly the kind of finding that triggers an incident response. You can automate this with n8n or Zapier and have it fire a ConnectWise ticket the moment an agent identity hits our corpus.

---

## Tab 5 — NHI Exposure (Non-Human Identity)

**What to say:**
- "NHI stands for non-human identity — API keys, service tokens, OAuth credentials, CI/CD secrets. These don't have 2FA. They don't expire unless you rotate them. And they're the most common vector in supply chain attacks."
- "Enter a domain. We query our stolen session corpus for service account credentials found in infostealer archives attributed to that domain."
- "Adobe.com returns two CRITICAL findings — an AWS_SECRET_ACCESS_KEY and an ADOBE_SERVICE_TOKEN. Both appear in our archive with a confidence rating and source attribution."
- "The Polymarket attack in 2026 was an NHI failure — an oracle API key or signing credential was compromised. This endpoint would have flagged the precursor in the stealer logs before the attacker used it."

**Key proof point:**
Enterprise NHI monitoring (GitGuardian, SpyCloud NHI, Cyberark) starts at $50K/year. Our NHI endpoint is included in the TI Starter plan at $499/month. For MSPs, that's a $49K/year conversation on one capability alone.

---

## Closing Frame

> "Everything you just saw is available via REST API today. No SOC required. No 6-month onboarding. The TI Starter plan gives you 10,000 calls a month, full IOC corpus access, and all five capabilities — for $499/month. For MSPs, we have a reseller model that lets you embed this into your stack and margin it however you want."

---

## Competitive Benchmarks to Drop

| Capability | RelayShield | Competitor | Their Price |
|---|---|---|---|
| Infostealer / NHI detection | ✅ $499/mo | SpyCloud | ~$30K+/yr |
| IOC corpus + actor profiles | ✅ included | Recorded Future | $50K+/yr |
| Bulk IOC enrichment | ✅ $0.50/100 IOCs | ThreatConnect | per-seat subscription |
| Identity risk scoring | ✅ $0.35/call | No direct equivalent | N/A |
| Agentic / NHI scoring | ✅ included | Cyberark, GitGuardian | $50K+/yr |

---

## Demo Assessment & Recommendations

### Current Strength: 8/10

The demo is genuinely compelling. It shows live data, real-time scoring, and a capability stack that maps directly to what enterprise buyers pay $30K–$150K/year for. The agentic tab is the differentiator — nobody in this price bracket is doing it.

### What Would Push It to 10/10

**1. A "before/after" attack timeline visual**
Show a horizontal timeline on the Identity Risk tab: Breach detected → Infostealer hit → Session stolen → Account takeover. Mark where on that chain your domain currently sits. Makes the risk visceral, not abstract.

**2. Downloadable PDF risk report**
After running any domain, offer a "Download Report" button that generates a 2-page PDF with the score breakdown, risk factors, and recommended remediations. This is what a prospect forwards to their CISO.

**3. Live webhook demo**
Show a Slack/Teams notification firing when a domain crosses CRITICAL threshold. Prospect sees the alert they'd actually get in their workflow — not just a demo portal result. One-minute integration proof.

**4. MSP multi-tenant view stub**
Even a static "Your Client Portfolio" table showing 5 fictional domains with risk levels and last-scan dates would let an MSP immediately visualize their use case. Tex-Mex Group is the first real-world version of this.

**5. Comparison callout on each tab**
A subtle "vs SpyCloud: $30K+/yr" or "vs Recorded Future: $50K+/yr" badge on each capability. Puts the price framing in the prospect's head without you having to say it.
