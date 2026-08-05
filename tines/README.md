# RelayShield — Employee Credential Early Warning

**Detect credential exposure in criminal Telegram channels 24–72 hours before HIBP picks it up. Stop the attack while it's forming — not after it executes.**

---

## What this story does

Most breach detection workflows fire after the credential is already in a public database. By then, the attacker has had days to act.

This story queries two intelligence surfaces in sequence:

**Surface 1 — Criminal Telegram channel intelligence (RelayShield INTEL)**
RelayShield monitors criminal Telegram channels in real time: infostealer log markets, credential dump announcements, and Web3 threat feeds. When an employee email appears in these channels, it means attackers have the credential *right now* — and it hasn't surfaced publicly yet.

→ **CRITICAL alert fires.** Your SOC has a 24–72 hour window to force a reset, revoke sessions, and harden the account before the attacker uses it.

**Surface 2 — Breach database check (HIBP via RelayShield)**
Cross-reference against known public breach databases. If the credential is already public but not yet in Telegram channels, a HIGH alert fires for standard remediation.

---

## Alert severity logic

| Condition | Severity | What it means |
|---|---|---|
| Telegram hit (with or without breach) | 🚨 CRITICAL | Attack forming now — act within hours |
| Breach only (no Telegram hit) | ⚠️ HIGH | Credential public — standard remediation |
| Neither | ✅ CLEAN | No action required |

---

## Why CRITICAL is different

A breach alert tells you something already happened.

A **Telegram intelligence hit tells you something is about to happen.**

Criminal Telegram channels are where infostealer logs are sold, credential dumps are posted, and SIM swap operators advertise. When an employee's email appears there, it means:

- An infostealer may have run on their device
- Their credentials are being actively sold or traded
- A SIM swap targeting their phone number may be in planning

The 24–72 hour lead time is the window between "attackers have the credential" and "HIBP indexes the breach." This story is built to act in that window.

---

## Setup

### Prerequisites
- A RelayShield API key — get one at [api.relayshield.net](https://api.relayshield.net/developers)
- A Slack webhook URL for your SOC channel (or swap for PagerDuty, ServiceNow, Jira)
- Tines account (free community tier works)

### Credentials to configure in Tines

| Credential name | Where to get it |
|---|---|
| `RelayShield_API_Key` | api.relayshield.net → sign up → API key emailed instantly |
| `Slack_Webhook_URL` | Slack → Apps → Incoming Webhooks |
| `RelayShield_Webhook_Secret` | Choose any string — used to secure the trigger endpoint |

### How to trigger
Send a POST to the story's webhook URL:
```bash
curl -X POST https://your-tines-tenant.tines.com/webhook/relayshield/... \
  -H "Content-Type: application/json" \
  -d '{"email": "employee@yourcompany.com"}'
```

Wire this to:
- **HR system** — trigger on new hire or offboarding
- **Identity provider** — trigger on login anomaly
- **Scheduled job** — daily sweep of full employee roster
- **Manual** — run on-demand during incident response

---

## Customising the story

The story is built to drop into your existing SOC workflow. Common modifications:

**Replace Slack with PagerDuty**
Swap the Slack HTTP agents for a PagerDuty Events API call. Use `severity: critical` for Telegram hits, `severity: warning` for breach-only.

**Add a ServiceNow ticket**
After the Slack alert, add an HTTP agent posting to your ServiceNow instance to auto-create an incident with the RelayShield data pre-populated.

**Batch-check a roster**
Wrap the webhook trigger in a CSV import agent to check every employee email in sequence. RelayShield's metered billing means you only pay for calls that return results you act on.

**Upgrade to TI API subscription**
The Telegram intelligence step uses RelayShield's `POST /v1/intel/telegram` endpoint, included in the **Threat Intelligence API** subscription ($499/mo MSP, $999/mo MSSP unlimited). For high-volume continuous monitoring across multiple client environments, the subscription tier removes per-call billing entirely.

---

## API endpoints used

| Endpoint | Purpose | Pricing |
|---|---|---|
| `POST /v1/metered/breach` | HIBP breach check | $0.10/call |
| `POST /v1/intel/telegram` | Telegram criminal channel IOC lookup | Included in TI API subscription ($499/mo) |

Full API reference: [api.relayshield.net/developers](https://api.relayshield.net/developers)

---

## Intelligence coverage

RelayShield's INTEL-2 pipeline continuously monitors verified criminal and security research Telegram channels across multiple categories:

- **Credential dumps** — Exposed.vc and live criminal dump channels
- **Crypto drainers** — CryptoScamDB wallet blacklists, Web3 security feeds
- **General threat intel** — vx-underground, Recorded Future, and others

IOCs extracted: email addresses, phone numbers, wallet addresses, domains.

Updated continuously. Lambda processes new channel messages within 6 hours of posting. Channel list is actively expanded — see the monthly GitHub Actions review workflow.

---

## About RelayShield

RelayShield is a threat intelligence API built by a 25-year telecom security professional. It monitors the full identity attack chain — breach exposure, SIM swap, session hijack, infostealer malware, OAuth supply chain risk, and wallet counterparty fraud — across both consumer and enterprise surfaces.

**Pricing:** Pay-as-you-go from $0.10/call. No annual contract. No procurement cycle. First call in under 60 seconds.

**Threat Intelligence API:** $499/mo MSP (10k calls) · $999/mo MSSP (unlimited) · 24–72hr lead time over HIBP

[api.relayshield.net/developers](https://api.relayshield.net/developers) · support@relayshield.net
