# Get the CryptoShield Badge
### Show your users your protocol is security-monitored | relayshield.net/badge

---

## What is the CryptoShield Badge?

The CryptoShield badge is a real-time security signal you embed on your protocol's site or app. It shows your users — and your team — that your domain, vendor stack, and infrastructure are actively monitored for credential exposure, supply chain compromise, and threat actor targeting.

It updates automatically. When your risk level changes, the badge changes.

---

## What the badge checks

| Signal | What it monitors |
|---|---|
| **Infostealer density** | Employee and developer credentials appearing in criminal stealer log archives |
| **Breach exposure** | Your domain in known breach databases — scored by recency and severity |
| **NHI exposure** | API keys, service tokens, and CI/CD secrets appearing in stealer archives |
| **Supply chain risk** | Oracle providers and vendor domains your protocol depends on |
| **Session exposure** | Active stolen session cookies in criminal corpus |
| **Threat actor targeting** | IOC attribution linking known actors to your infrastructure |

---

## Badge styles

**Flat (default)**
```html
<script src="https://api.relayshield.net/badge.js?domain=yourprotocol.xyz"></script>
```
![CryptoShield | LOW RISK 8/100](#)

**Compact (small footprint)**
```html
<script src="https://api.relayshield.net/badge.js?domain=yourprotocol.xyz&style=compact"></script>
```

**Fixed position (bottom-right corner)**
```html
<script src="https://api.relayshield.net/badge.js?domain=yourprotocol.xyz&position=fixed-bottom-right"></script>
```

---

## Risk levels

| Badge color | Level | What it means |
|---|---|---|
| 🟢 Green | LOW (0–21) | No active threat signals |
| 🟡 Yellow | MEDIUM (22–44) | Early warning signals detected |
| 🟠 Orange | HIGH (45–69) | Active credential or supply chain exposure |
| 🔴 Red | CRITICAL (70–100) | Immediate response required |

The badge score updates every hour. If your score crosses into HIGH or CRITICAL, your team receives an immediate alert via the RelayShield API webhook.

---

## Who is using CryptoShield monitoring?

Any protocol embedding the badge has enrolled their domain in continuous monitoring across RelayShield's threat intelligence corpus — 1M+ IOCs from 30+ feeds, live infostealer log intelligence, and supply chain risk scoring updated daily.

---

## Get started in 60 seconds

**Step 1** — Register at api.relayshield.net/developers (free trial available)

**Step 2** — Add your domain to your account

**Step 3** — Paste one script tag:
```html
<script src="https://api.relayshield.net/badge.js?domain=yourprotocol.xyz"></script>
```

**Step 4** — Configure your webhook to receive alerts when risk level changes:
```bash
curl -X POST https://api.relayshield.net/v1/metered/webhook-config \
  -H "X-RS-API-KEY: your_key" \
  -d '{"url": "https://yourprotocol.xyz/security-webhook", "events": ["risk_level_change"]}'
```

That's it. The badge goes live. Monitoring starts immediately.

---

## For DeFi protocols and prediction markets

The Polymarket incident of June 2026 confirmed what security researchers have warned for years: the attack surface in DeFi is not the smart contracts — it's the credential layer. Oracle signing keys, developer credentials, vendor service tokens. These don't appear in audit reports. They appear in criminal stealer log archives.

CryptoShield monitors the signals that auditors don't look at. The badge tells your users and counterparties that someone is watching the layer that matters.

---

## Pricing

| Plan | Coverage | Price |
|---|---|---|
| **Badge Free** | Domain risk score + badge only | Free |
| **TI Starter** | Full 6-dimension monitoring + alerts + webhook | $499/month |
| **TI Pro** | Everything + supply chain vendor sweep + NHI | $999/month |

The badge itself is always free. Monitoring and alerts require a TI plan.

---

## Questions?

**relayshield.net** | relayshieldadmin@gmail.com | t.me/RelayShield

*© 2026 RelayShield LLC*
