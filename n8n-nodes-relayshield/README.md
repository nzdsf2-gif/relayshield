# n8n-nodes-relayshield

An [n8n](https://n8n.io) community node for [RelayShield](https://relayshield.net) — security intelligence for automation workflows.

## Operations

| Operation | Endpoint | Cost |
|---|---|---|
| **Breach Check** | `POST /v1/metered/breach` | $0.10/call |
| **SIM Swap Detection** | `POST /v1/metered/sim-swap` | $0.25/call |
| **Infostealer Check** | `POST /v1/metered/infostealer` | $0.50/call |
| **Domain Lookalike Scan** | `POST /v1/metered/domain` | $0.30/call |
| **OAuth Watchlist Check** | `POST /v1/metered/oauth-watchlist` | $0.20/call |
| **Threat Intelligence — IOC Lookup** | `GET /v1/intel/telegram` | Subscription |
| **Threat Intelligence — CVE Lookup** | `GET /v1/intel/cve` | Free |

## Installation

In your n8n instance, go to **Settings → Community Nodes → Install** and enter:

```
n8n-nodes-relayshield
```

## Credentials

You need a RelayShield API key. Get one at [api.relayshield.net/developers](https://api.relayshield.net/developers).

Add it in n8n: **Credentials → New → RelayShield API**.

## Pricing

- **PAYG metered billing** — pay only for calls made, billed monthly via Stripe
- **Credit packs** — $25 / $50 / $100 one-time, credits never expire
- **Developer subscription** — $499/mo (10,000 TI calls) · $999/mo (unlimited TI calls)

## Example workflows

### Employee breach monitoring
```
Schedule Trigger → RelayShield (Breach Check) → IF breach_count > 0 → Slack alert
```

### Infostealer detection in incident response
```
Webhook → RelayShield (Infostealer Check) → IF exposed → PagerDuty alert + Jira ticket
```

### IOC enrichment in SOAR playbook
```
Webhook (alert) → RelayShield (IOC Lookup) → IF matched → escalate + block IP in firewall
```

### CVE triage for ransomware-linked vulnerabilities
```
Schedule Trigger → RelayShield (CVE Lookup, keyword=your-vendor) → filter ransomware_flagged=true → Jira ticket
```

## Support

- Docs: [relayshield.net/developers](https://api.relayshield.net/developers)
- Email: [support@relayshield.net](mailto:support@relayshield.net)
