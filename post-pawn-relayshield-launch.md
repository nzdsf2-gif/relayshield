> **STATUS: DRAFT — Ready to publish**
> **Target: PAWN Security Practitioner Community (Substack)**

# I Spent 25 Years in Telecom Security. Here's What I Built With That Knowledge — And Why Automation Teams Need It Now.

Most threat intelligence platforms are built by people who've never touched a carrier network. I spent 25 years inside one. What I saw from that vantage point — and what most of the security industry is still missing — is why I built RelayShield.

---

## The Gap Nobody Talks About

Your SOC has EDR. It has email security. It has a SIEM ingesting logs from everything on the network.

What it doesn't have is visibility into the layer where your users' identities actually live: the phone number.

I watched SIM swap fraud evolve from an occasional carrier headache into a precision attack vector that threat actors now deploy against high-value individuals and corporate accounts as a matter of routine. The mechanics are well understood inside telecom. Outside of it, most security teams are still treating it as an edge case.

It isn't. And the infrastructure that enables it — the criminal Telegram channels where SIM swap services are advertised, the infostealer log markets where fresh credentials with phone numbers are sold hours after infection, the lookalike domains registered the same day a phishing kit goes live — all of that intelligence is there to be collected. It just hasn't been wired into the tools security teams already use.

That's what RelayShield does.

---

## What We Built

RelayShield is a threat intelligence and identity monitoring API with six core capabilities:

**Breach exposure** — real-time check against known breach databases for a given email address. Not a static list. Live.

**Infostealer log exposure** — checks if credentials have appeared in criminal infostealer log markets (RedLine, Vidar, Raccoon derivatives and their successors). This is the pre-breach signal most teams don't have visibility into. By the time a credential shows up in HaveIBeenPwned, it's been for sale for weeks.

**SIM swap detection** — carrier-level query that detects an active SIM swap or port-out in progress. The only way to know before the account takeover happens, not after.

**Domain lookalike scanning** — typosquat and homoglyph detection for a given domain. Catches the infrastructure stage of a phishing campaign before the emails go out.

**OAuth supply chain watchlist** — checks if breached credentials are associated with OAuth app authorizations that could allow persistent access even after a password reset.

**Threat intelligence IOC lookup** — 1.4M+ indicators from live criminal Telegram channels, ThreatFox, URLhaus, and CISA's Known Exploited Vulnerabilities catalog. Cross-referenced for ransomware activity. Updated continuously.

---

## Why Automation Teams Specifically

Security practitioners in operations roles don't need another dashboard to check. They need enrichment data that flows into the tools they're already running — their SOAR playbooks, their ticketing system, their alerting pipeline.

That's how RelayShield is designed to be used. Every capability is a REST endpoint that returns structured JSON. There's no portal to log into, no proprietary query language, no professional services engagement. You call it, you get data, you act on it.

The economics work differently too. Most enterprise TI platforms are priced for SOC teams at large organisations — annual contracts, minimum seat counts, lengthy procurement cycles. RelayShield is metered. You pay for what you call. For security practitioners inside lean teams — or consultants running detection workflows across multiple clients — that matters.

We just went live as a **verified node in n8n** — which means if your team is already running n8n for SOAR-adjacent work, you can drop RelayShield into an existing workflow in minutes with no custom code.

The use cases write themselves:

- New employee onboarding → breach check on corporate email before provisioning access
- Daily scheduled run → infostealer exposure check across your monitored email list, Slack alert if anything surfaces
- Phishing report intake → domain lookalike scan on reported sender domain, auto-enrich the ticket
- VIP protection workflow → SIM swap check on executive phone numbers on a schedule
- Threat intel enrichment → IOC lookup on any indicator that comes through your pipeline

For Tines users, the REST API works the same way — we're building the native Tines action next.

---

## The Intelligence Stack

The TI feed is worth a separate conversation. Here's what's feeding it:

- **20+ criminal Telegram channels** monitored continuously — infostealer logs, credential dumps, SIM swap service listings, crypto drainer infrastructure
- **ThreatFox** — abuse.ch's malware IOC feed, tagged by malware family
- **URLhaus** — malicious URL and domain feed, updated in near real-time
- **CISA KEV** — the Known Exploited Vulnerabilities catalog, cross-referenced against ransomware campaign data
- **Feodo Tracker** — abuse.ch's botnet C2 IP blocklist covering Emotet, QakBot, Dridex, IcedID, and TrickBot infrastructure
- **AbuseIPDB** — crowdsourced IP abuse reports, confidence-filtered
- **MalwareBazaar** — abuse.ch's malware sample hash database, updated daily

The combined result is **1.4M+ indicators** across domains, IPs, URLs, and malware hashes — and it runs **24–72 hours ahead** of most public breach databases for the threat types it covers. When a fresh infostealer log drops in a criminal channel, it's in our database before it propagates to the aggregators.

For the CISA KEV integration specifically: you can query by CVE ID or by keyword (vendor, product). If you're a defender trying to figure out if "apache" or "citrix" or "exchange" have active KEV entries right now, one API call returns the current picture cross-referenced against ransomware activity flags.

---

## Pricing

**B2B WhatsApp / Telegram monitoring (SMB):**
- **Business Starter — $19.99/month** — sole proprietors and small business owners. Breach exposure, infostealer monitoring, SIM swap detection, OAuth watchlist, AI-guided remediation via WhatsApp or Telegram. 3 monitored email addresses.
- **Business Starter + Domain — $24.99/month** — everything in Starter plus typosquat and lookalike domain monitoring for 1 business domain. For owner-operators whose website is an active attack surface.
- **Business Basic — $89.99/month** — up to 5 seats. Team-level identity protection with dual WhatsApp + Telegram delivery, 2 monitored emails per seat, and the full detection stack per employee.

**B2A API:**
- Metered access: breach, SIM swap, infostealer, domain, OAuth watchlist — pay per call, no commitment
- **$499/month** — 10,000 TI API calls/month, full IOC database access, CVE lookup. For in-house security teams and lean SOC environments running enrichment workflows against a fixed asset inventory.
- **$999/month** — unlimited TI API calls. For MSSPs, MDRs, and security consultants running high-volume enrichment pipelines across multiple clients.

---

## A Note on Who Built This

Solo founder. 25 years in telecom security. This isn't a VC-funded team with a go-to-market playbook — it's a practitioner who got tired of watching the same attacks succeed because the telemetry that could stop them wasn't accessible outside of carrier walls.

If you're in security operations, threat intelligence, or running SOAR workflows and want early access or want to talk about what we're building next, I'm reachable directly.

**API docs and signup:** [api.relayshield.net/developers](https://api.relayshield.net/developers)
**n8n node:** search `n8n-nodes-relayshield` in the n8n node library

---

*RelayShield monitors breach exposure, SIM swap fraud, infostealer logs, domain lookalikes, OAuth supply chain risk, and threat intelligence IOCs via REST API and workflow automation integrations.*
