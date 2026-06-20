# FiberSmith / Arjen — RelayShield Integration Strategy

*Created June 2026. Arjen is a RelayShield Crypto Shield subscriber and independent consultant to FiberSmith, an OSS (Operations Support System) supplier to the fixed broadband market.*

---

## Background

**FiberSmith** builds OSS platforms for fixed broadband ISPs. OSS systems manage:
- Network provisioning and activation
- Fault/alarm management (NOC)
- Customer management (CPE, subscriber records)
- Performance monitoring

**Arjen** is our connection — already a paying RS user (Crypto Shield), understands the product, and has internal credibility at FiberSmith. He is the ideal internal champion for a pilot.

Andrew's 25-year telecom background gives significant credibility in this conversation that most security vendors can't match.

---

## Where RelayShield Fits in Broadband OSS

### Integration Point 1 — IOC Feed into DNS/Network-Layer Blocking (Strongest Fit)

RelayShield's IOC database (200K+ malicious IPs, domains, URLs from 8 criminal Telegram channels + 11 authoritative feeds) can feed directly into:
- **DNS RPZ (Response Policy Zones)** — ISP's recursive DNS resolver blocks known-malicious domains for all customers automatically
- **Edge firewall / access control** — block outbound connections to known C2 IPs (Emotet, QakBot, TrickBot, etc. from Feodo Tracker)

FiberSmith's ISP clients already have DNS resolvers and edge infrastructure. RS becomes the threat intelligence layer powering their existing blocking capability.

**Technical integration:** STIX/TAXII 2.1 feed (built June 2026) or direct API. ISP SIEM/firewall pulls new IOCs on a configurable schedule.

**Commercial model:** IOC feed license — flat-rate MSSP-tier subscription, white-labeled if preferred.

---

### Integration Point 2 — Infected CPE Detection

When a residential or business customer's device (CPE) makes outbound calls to known botnet C2 IPs in our Feodo Tracker data:
- FiberSmith's OSS detects the C2 callout in traffic logs
- Cross-references against RS IOC API to confirm malicious destination
- Auto-creates a support ticket in the OSS alarm management system
- Optionally quarantines the customer segment or triggers remediation workflow

This is a **managed security service upsell** for FiberSmith's ISP clients — "we proactively detect and remediate infected devices on your network."

---

### Integration Point 3 — Customer Identity Protection as White-Label Product

ISPs bundle security services for their subscriber base (Comcast has Norton 360, etc.). FiberSmith's ISP clients have large SMB and residential subscriber bases.

RelayShield can be their **"Fiber Shield"** — customer-facing identity protection powered by RS, delivered via WhatsApp/Telegram:
- Breach monitoring
- SIM swap detection
- Infostealer alerts
- Domain typosquat monitoring

ISP provides distribution, RS provides the product. Revenue model: per-subscriber monthly fee, MSP-style margin structure.

---

### Integration Point 4 — SOC/NOC Enrichment on Network Events

When a NOC alarm fires (unusual traffic, customer complaint, port scan detected), the SOC analyst can enrich with RS data:
- Is this source IP flagged as malicious?
- Is this customer's domain on a ransomware victim list? (INTEL-4)
- Has this customer's email appeared in recent breach data?

One API call per alarm enriches the SOC ticket with identity and threat context. Integrates into existing ticketing/SOAR workflows via REST API or STIX/TAXII.

---

## Technical Integration — STIX/TAXII

RS now has a STIX/TAXII 2.1 compliant feed endpoint:
- `GET /v1/intel/taxii/` — discovery
- `GET /v1/intel/taxii/collections/iocs/objects/` — paginated STIX indicators

SIEMs and security tools that already speak TAXII (Splunk, Sentinel, Elastic, QRadar, OpenCTI) can ingest RS IOCs with zero custom integration work. FiberSmith's OSS or their clients' SIEM can point a TAXII client at the RS endpoint.

---

## Commercial Model Options

| Model | Description | Best For |
|---|---|---|
| **IOC Feed License** | Flat-rate MSSP subscription ($499–$999/mo) — STIX/TAXII or bulk API | FiberSmith internal + resale to ISP clients |
| **White-label identity protection** | RS powers "Fiber Shield" — per-subscriber fee split | ISP customer-facing product |
| **OEM/API integration** | RS API embedded in FiberSmith OSS platform — per-call or subscription | Direct platform integration |
| **Co-sell / referral** | Arjen refers ISP clients directly, RS pays referral margin | Low-friction start |

---

## Pilot Proposal for Arjen

**Phase 1 (immediate):** Arjen provides RS TAXII endpoint to one FiberSmith ISP client's security team for evaluation. Zero cost, zero commitment. Evaluate IOC coverage for their network threats.

**Phase 2 (30 days):** If Phase 1 shows value, formalize as a TI license ($499/mo). Arjen earns referral/consulting fee.

**Phase 3 (90 days):** If ISP wants to bundle identity protection for their subscribers, structure a white-label agreement.

---

## AWS ISV Accelerate Connection

FiberSmith + any ISP reference customer strengthens the case for AWS ISV Accelerate (co-sell program). The telco/ISP vertical is exactly what Andrew's AWS contact can open doors in. A named ISP reference customer makes the ISV Accelerate conversation much stronger.

---

## Questions to Ask Arjen

1. Does FiberSmith's OSS have a SOC/NOC function that currently consumes threat intel feeds? If so, what format (STIX/TAXII, Syslog, CSV)?
2. Do FiberSmith's ISP clients have DNS RPZ capability in their resolvers?
3. Is there an existing security product bundling arrangement with the ISPs, or is this whitespace?
4. What is the typical size of FiberSmith's ISP clients (subscriber count, IT/security team size)?
5. Would Arjen be willing to make an introduction to FiberSmith's product/partnerships team?

---

## Priority

**Medium-high.** Not an immediate revenue path but a potentially significant channel:
- Andrew has the telecom credibility to be taken seriously
- Arjen is a warm connection with internal credibility
- STIX/TAXII endpoint (built June 2026) removes the integration friction
- One ISP reference customer changes the AWS ISV Accelerate conversation

Start with a conversation with Arjen — no pitch, just exploring whether FiberSmith's clients have the SOC/threat intel consumption pattern that makes this a fit.
