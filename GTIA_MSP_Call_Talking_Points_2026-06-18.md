# GTIA MSP Partnership Call — Talking Points
**Date:** June 18, 2026

---

## Opening (30 seconds)

RelayShield is a proactive identity protection API purpose-built for MSPs. Unlike HIBP-style breach lookup services that tell you what already happened, RelayShield detects attacks while they're still forming — before financial loss. We monitor five attack surfaces simultaneously, correlate signals across them, and fire pre-chain warnings so MSPs can intervene in time.

---

## The Gap in Every MSP Stack

Every MSP stack today has endpoint, network, and SIEM covered. What almost none of them have is **identity** — the attack surface that precedes every other threat.

- Credential breaches, infostealer logs, and SIM swaps occur **weeks before** MFA bypass and account takeover
- Cyber insurance carriers now ask about breach monitoring at renewal
- Clients are starting to ask: "What do you cover for identity?"
- Most MSP stacks have no answer

---

## What RelayShield Monitors (6-Feed TI Stack)

| Signal | Source | Lead Time |
|---|---|---|
| **Credential breach** | Criminal breach databases | Hours before credential stuffing begins |
| **Infostealer log exposure** | Criminal Telegram marketplaces | 24–72 hrs ahead of HIBP |
| **SIM swap / port-out fraud** | Carrier-level real-time query | Before 2FA bypass completes |
| **Domain lookalike** | Newly registered typosquat domains | Hours after registration |
| **OAuth supply chain** | Rogue app access to M365 / Google Workspace | On detection |
| **Threat intelligence IOC** | ThreatFox, URLhaus, CISA KEV, Spamhaus DROP/EDROP, AbuseIPDB, criminal Telegram channels | Continuous ingestion |

The last feed is what differentiates us for MSPs serving security-conscious clients — a live IOC database with 6 sources, including CISA Known Exploited Vulnerabilities cross-referenced with ransomware activity.

---

## The Coordinated Attack Warning (Competitive Differentiator)

When two or more signals align within a correlation window, RelayShield fires a **Coordinated Attack Warning**. This is the only commercial product at this price point doing multi-vector correlation.

Example chain: *Breach + SIM swap detected → predicted account takeover in progress*

MSPs get actionable, prioritized escalations — not raw alert noise.

---

## Integration Story

Three ways MSPs can deploy:

1. **REST API** — drop into any SOAR, ticketing system, or homegrown MSP portal. Full documentation at `api.relayshield.net/developers`. Metered, PAYG per call.
2. **n8n community node** — `n8n-nodes-relayshield` published to npm (v0.1.4, just cleared Creator Portal). Drag-and-drop all six operations into n8n workflows. Ready today.
3. **Tines** — submitted to their partner library, pending verification.

For MSPs already running n8n or Tines automation stacks, RelayShield is a native integration — no custom code, no webhook wrangling.

---

## Pricing

| Plan | Price | Best For |
|---|---|---|
| **PAYG** | Per-call metered | Low-volume testing, ad-hoc checks |
| **TI Starter** | $499/mo | MSPs adding TI feed access for a security team |
| **TI Professional** | $999/mo | MSPs reselling to multiple clients or needing higher call volume |

MSP reseller / white-label pricing available — structure TBD based on GTIA member profile.

---

## Questions to Ask GTIA

1. What does the average GTIA member MSP's current identity monitoring stack look like? (HIBP? Nothing?)
2. Are members billing identity monitoring as a standalone line item, or bundling it into an MDR/managed security tier?
3. What's the preferred integration path — REST API, n8n, Tines, or something else?
4. Is there appetite for a white-label or co-branded offering for member resale?
5. What would a GTIA member proof-of-concept engagement look like — a pilot with 2–3 members?

---

## Proof Points to Mention

- **6 active threat intel feeds** ingesting continuously (Telegram, ThreatFox, URLhaus, CISA KEV, Spamhaus DROP/EDROP, AbuseIPDB)
- **Published n8n community node** — first identity security node in their marketplace
- **AWS-hosted**, production API, paying customers today
- **25 years telecom security background** — built by a practitioner who has worked SIM swap fraud firsthand at the carrier level

---

## Possible Ask

Pilot program: 3–5 GTIA member MSPs, 90 days, cost-free or discounted. In exchange: documented case studies and a GTIA member webinar at the end of the pilot.

---

## One-Line Close

> "Every MSP in the room can name the last client who got breached. RelayShield is how you tell the next client you saw it coming."
