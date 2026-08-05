# RelayShield — Multi-Site Shield
### Unified Identity Security for Multi-Location Businesses | relayshield.net

---

## One breach at one location can take down the whole business

You have 12 locations, 47 employees, and one IT person — or no IT person. Your POS system, business email, and bank accounts share the same phone number your manager uses every day. A SIM swap at your smallest location compromises the same credentials that protect your main accounts.

Traditional security tools weren't designed for this. You can't deploy enterprise software to a franchise manager in a break room. You can't pay per-seat pricing across 47 employees at 12 locations. And you can't afford to find out about a breach at 2 AM when you're staring at a locked account and a zero balance.

**Multi-Site Shield was built for exactly this.**

---

## The attack chain your multi-location business isn't watching

```
Location 3 — shift manager's phone number is SIM-swapped.
She doesn't notice for 4 hours. Her phone has no signal.

The attacker uses her number to bypass 2FA on your
shared Square account. Processes $8,400 in refunds.

Meanwhile, her saved browser credentials from an
infostealer infection 3 weeks ago are used to access
your payroll portal. 22 employee records exported.

Your IT contact is at Location 7.
You find out when your bookkeeper calls on Monday.
```

> **Multi-location businesses are disproportionately targeted because they have more credential surfaces, more employees with privileged access, and less central IT oversight than a comparably-sized single-site operation.**

---

## What Multi-Site Shield monitors — at every location, simultaneously

| Signal | What it protects |
|---|---|
| **SIM swap monitoring** | Per-employee phone numbers across all locations — carrier-layer detection, not just alerts after the fact |
| **Infostealer detection** | Employee email credentials in criminal stealer log markets — alerts within hours of publication, before attackers act |
| **Breach monitoring** | All monitored email addresses across your entire org, scored by severity |
| **Session exposure** | Active stolen session cookies in criminal archives — catches attackers who bypass 2FA entirely |
| **Domain lookalike monitoring** | Flags attackers registering yourfranchise-billing.com before they impersonate you to vendors or customers |
| **NHI / service account monitoring** | API keys, POS integration tokens, and service credentials appearing in stealer archives |
| **Supply chain risk** | Vendors you trust — POS providers, payroll platforms, cloud tools — scored for credential exposure |

---

## The dashboard your IT person (or you) actually needs

Multi-Site Shield includes a unified management dashboard showing your entire operation in a single view.

---

### Dashboard Mockup

```
┌─────────────────────────────────────────────────────────────────────────┐
│  RELAYSHIELD — MULTI-SITE SHIELD                    🔴 2 CRITICAL OPEN  │
│  Tex-Mex Group   •   12 Locations   •   Last scan: 4 min ago            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  PORTFOLIO OVERVIEW                                                     │
│  ┌──────────┬────────────┬──────────┬──────────┬──────────────────┐    │
│  │ Location  │ Risk Score │ Status   │ Alerts   │ Last Incident    │    │
│  ├──────────┼────────────┼──────────┼──────────┼──────────────────┤    │
│  │ Austin TX │ 🔴 78/100  │ CRITICAL │ 2 open   │ Infostealer hit  │    │
│  │ Dallas TX │ 🟡 42/100  │ HIGH     │ 1 open   │ Breach exposure  │    │
│  │ Houston   │ 🟢 12/100  │ CLEAR    │ —        │ 18 days ago      │    │
│  │ San Antonio│ 🟢 8/100  │ CLEAR    │ —        │ 31 days ago      │    │
│  │ Austin 2  │ 🔴 71/100  │ CRITICAL │ 1 open   │ SIM swap attempt │    │
│  │ Plano TX  │ 🟡 38/100  │ HIGH     │ 1 open   │ Domain lookalike │    │
│  │ ...       │ ...        │ ...      │ ...      │ ...              │    │
│  └──────────┴────────────┴──────────┴──────────┴──────────────────┘    │
│                                                                         │
│  ACTIVE ALERTS                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 🔴 CRITICAL  Austin TX   Infostealer — manager@austintx.com      │   │
│  │              RedLine log published 6h ago. Session cookies       │   │
│  │              exposed for Square POS + Gmail. ACK to remediate →  │   │
│  │                                                                   │   │
│  │ 🔴 CRITICAL  Austin 2    SIM Swap attempt — +1-512-555-0147      │   │
│  │              Carrier-layer port request detected 22 min ago.     │   │
│  │              Alert sent to manager. Carrier block recommended →  │   │
│  │                                                                   │   │
│  │ 🟡 HIGH      Dallas TX   Breach — ops@dallas.texmexgroup.com     │   │
│  │              Appeared in LinkedIn 2024 breach. Password reuse    │   │
│  │              risk: Square, Gusto payroll. Rotate recommended →   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  RISK TREND (30 DAYS)          LOCATION KPIs                           │
│  ████▄▄▄▄████▄██▄▄▄            Monitored employees:      47            │
│  70 ──────────────── 30        Infostealer hits (30d):    3            │
│                                Breach alerts (30d):       8            │
│  PORTFOLIO RISK: HIGH 44/100   SIM swap attempts (30d):   1            │
│                                Domains monitored:         4            │
│                                Open critical alerts:      2            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### Location Drill-Down View

Click any location to see the site-specific risk profile:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Austin TX — Identity Risk Detail                    CRITICAL  78/100   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  SIGNAL DIMENSIONS                                  SCORE               │
│  Breach Exposure        ████████████████████████    25 / 25             │
│  Infostealer Density    ████████████████████████    25 / 25             │
│  Session Exposure       ████████████████████        10 / 10             │
│  CVE Exposure           ████████████                8 / 25              │
│  IOC Presence           ███████                     5 / 15              │
│  Ransomware Victim      ────────────────────────    0 / 20              │
│                                                                         │
│  MONITORED IDENTITIES (Austin TX)                                       │
│  manager@austintx.texmexgroup.com  🔴 CRITICAL — Infostealer hit        │
│  owner@austintx.texmexgroup.com    🟡 HIGH — Breach exposure            │
│  pos-service@texmexgroup.com       🟡 HIGH — API key in stealer log     │
│                                                                         │
│  RECENT ALERTS                                                          │
│  Jun 26 09:14  Infostealer — RedLine log, 3 credentials extracted      │
│  Jun 24 17:22  Breach — LinkedIn 2024, ops@austin email affected        │
│  Jun 18 11:05  Domain lookalike — texmex-group-secure.com registered   │
│                                                                         │
│  [Remediate via WhatsApp]  [Download Report]  [Open ConnectWise Ticket] │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Site-Specific KPIs at a Glance

Each location displays a consistent set of operational security metrics:

| KPI | What It Measures |
|---|---|
| **Risk Score (0–100)** | Composite identity risk across 6 signal dimensions |
| **Risk Grade (A–F)** | Simple letter grade for quick triage at a glance |
| **Open Alerts** | Count of unacknowledged CRITICAL/HIGH alerts for that site |
| **Infostealer Hits (30d)** | Times a monitored employee credential appeared in criminal stealer logs |
| **Breach Exposures** | Number of monitored identities with confirmed breach records |
| **SIM Swap Attempts** | Carrier-layer port/swap events detected for monitored phone numbers |
| **Days Since Last Incident** | Time since last confirmed CRITICAL or HIGH event |
| **Domain Lookalikes Active** | Typosquat/impersonation domains currently registered and live |

---

## What makes Multi-Site Shield different

| | **Traditional security tools** | **Multi-Site Shield** |
|---|---|---|
| View | One dashboard per site | Unified portfolio view across all locations |
| Alert routing | Alert goes to whoever owns that account | Centralized triage + per-location routing |
| Breach correlation | Siloed — breach at Location 3 has no context | Cross-location: same credential reused at Location 7? Flagged. |
| Infostealer | Typically not included | Included at every tier |
| SIM swap | Consumer-grade, if at all | Carrier-layer monitoring |
| PSA integration | None | ConnectWise / Autotask ticket creation on every CRITICAL alert |
| Pricing | Per-seat × locations × tools | Flat per-location — predictable |

---

## The two capabilities that set RelayShield apart

### 1. Proactive Response — we stop attacks before the damage is done

Most security tools are reactive by design. They detect a confirmed breach and send an alert. By then, the attacker has already taken over the account, transferred funds, or exfiltrated data. Your team is cleaning up damage, not preventing it.

RelayShield monitors threat signals in real time **as attacks are forming**. The moment we detect early-chain indicators — credentials appearing in a stealer log, a SIM swap request at the carrier, a lookalike domain registered near your brand — we alert and guide your response. The attack is stopped at the signal stage, before financial damage or reputational harm occurs.

> **Other solutions tell you what happened. RelayShield tells you what's about to happen — and what to do about it right now.**

---

### 2. Multi-Vector Attack Correlation — coordinated attacks trigger coordinated warnings

Sophisticated attacks don't fire a single signal. They combine multiple vectors in sequence. RelayShield's correlation engine monitors for two or more signals firing within the same time window and escalates to a **Coordinated Attack Warning** — a higher-severity alert that names the attack chain and the likely next step.

**Examples of coordinated attack patterns we detect:**

| Signals detected | Attack chain identified | What happens next |
|---|---|---|
| Infostealer log hit + VPN credentials exposed | **Imminent ransomware** | Attacker establishes foothold before deploying payload |
| Smishing campaign + SIM swap attempt | **Imminent financial drain** | Phone number theft to bypass 2FA on banking accounts |
| Data breach exposure + lookalike domain registered | **Imminent spear phishing** | Personalised attack using your own breach data against you |

**Why it matters:** Most security platforms generate alert volume. RelayShield generates **actionable intelligence** — prioritised, escalated, and delivered with specific remediation steps so your team knows exactly what to do and in what order. No alert fatigue. No noise. No missed signals buried in a dashboard nobody checks.

---

## ConnectWise / Autotask PSA Integration

For MSPs managing multi-location clients in ConnectWise or Autotask, Multi-Site Shield creates service tickets automatically when a CRITICAL or HIGH alert fires — no manual triage required.

**Every ticket includes:**
- Alert type and severity
- Affected identity (email, phone number, or service account)
- Signal source (breach name, stealer log family, carrier event)
- Recommended remediation steps (pre-written, actionable)
- Link to full RelayShield location drill-down

**Integration setup:** 15 minutes. Paste your ConnectWise API key into the Multi-Site Shield portal. Done.

---

## Plans & Pricing

**Pricing is per-location + per-employee.** Each location includes 3 base employees (monitored users). Additional employees are $6/employee/month.

| | **Multi-Site Starter** | **Multi-Site Pro** | **Enterprise (MSP)** |
|---|---|---|---|
| **Best for** | 2–5 locations, owner-operated | 6–20 locations, light IT | MSP-managed, any size |
| **Locations** | Up to 5 | Up to 20 | Unlimited |
| **Base employees/location** | 3 included | 3 included | Custom |
| **Additional employees** | $6/employee/mo | $6/employee/mo | Volume rate |
| **Breach monitoring** | ✅ | ✅ | ✅ |
| **Infostealer detection** | ✅ | ✅ | ✅ |
| **SIM swap monitoring** | ✅ | ✅ | ✅ |
| **Session exposure** | ✅ | ✅ | ✅ |
| **Domain lookalike** | 1 domain | Per location | Per location |
| **NHI / service account** | — | ✅ | ✅ |
| **Supply chain risk** | — | ✅ | ✅ |
| **Portfolio dashboard** | ✅ | ✅ | ✅ White-label |
| **ConnectWise / Autotask** | — | ✅ | ✅ |
| **WA / Telegram manager alerts** | ✅ | ✅ | ✅ |
| **Alert routing** | Email/WA/TG | Email/WA/TG + Slack | Full webhook config |
| **Per-location/month** | **$45/location** | **$39/location** | Custom |

**Example — 5 locations, 5 users each:**
$45 × 5 locations = $225 + (10 additional employees × $6) = **$285/month**

**Example — 12 locations, 4 employees avg:**
$39 × 12 locations = $468 + (12 additional employees × $6) = **$540/month**

*Minimum 2 locations. Month-to-month. MSP reseller pricing available.*

---

## Why RelayShield

→ **Built by a 25-year telecom security professional**

→ **Carrier-layer SIM swap monitoring** — not just alerts after the port. Active detection at the carrier event level. No competitor offers this at SMB pricing.

→ **Every alert is actionable** — the moment a threat is detected, plain-English remediation guidance is delivered directly to the location manager's WhatsApp or Telegram. They respond on their phone immediately, in the app they already use. No dashboard login. No IT degree required. Meanwhile the IT manager or business owner monitors the full portfolio from the central dashboard and receives a ConnectWise ticket for every CRITICAL alert — so nothing falls through the cracks at either level.

→ **PSA-native for MSPs** — ConnectWise and Autotask integration means Multi-Site Shield alerts become service tickets in your existing workflow with zero new tools.

→ **Transparent per-location, per-identity pricing** — pay for the locations and identities you actually monitor. No per-seat surprises as your team grows.

---

## Get started

Your dashboard is waiting. Here's what we found across a typical 12-location portfolio in the first scan: **2 CRITICAL alerts** open, **3 infostealer hits** in 30 days, **1 SIM swap attempt** detected, **47 identities** monitored — portfolio risk score **HIGH 44/100**.

Schedule a 20-minute assessment and we'll run the same scan across your locations — live, on the call — and show you exactly where the gaps are before your next incident.

**relayshield.net** | relayshieldadmin@gmail.com | +1 (339) 203-9730

*© 2026 RelayShield. All rights reserved.*
