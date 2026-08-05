# Badge Endpoint Launch — Social Posts
**Audience:** DeFi protocols, prediction markets, crypto security community
**Timing:** Publish after the Polymarket blog drops — ride the inbound attention

---

## X / Twitter — Thread (5 tweets)

**Tweet 1 (hook):**
The Polymarket attack wasn't a smart contract exploit.

It was a vendor credential compromise that any team could detect in advance — if they were watching the right signals.

We built a free public badge endpoint for DeFi protocols to show their users they're watching. 🧵

---

**Tweet 2 (what it is):**
`GET https://api.relayshield.net/v1/badge?domain=yourprotocol.xyz`

Returns a live SVG badge with your protocol's security risk level — color-coded, updated every hour, embeddable with one `<script>` tag.

GREEN: monitored, no active threats
RED: active signals detected

---

**Tweet 3 (what it monitors):**
Behind the badge:

→ Employee credentials in stealer log archives
→ Service account API keys / oracle signing tokens in criminal markets
→ Vendor / oracle provider risk (Chainlink, Pyth, UMA, Alchemy)
→ Threat actor IOC attribution
→ Real-time peg + RWA health

The layer auditors don't look at.

---

**Tweet 4 (call to action):**
One line to embed:

```html
<script src="https://api.relayshield.net/badge.js
  ?domain=yourprotocol.xyz"></script>
```

Badge is free. Full monitoring + webhooks at api.relayshield.net/developers

Full write-up on the Polymarket attack chain + 5 RS detection signals: [blog link]

---

**Tweet 5 (close):**
If you run a prediction market, oracle-dependent protocol, or DeFi treasury:

The signal that preceded Polymarket was sitting in public threat intel databases for days before the attack.

You don't need a SOC. You need 30 minutes of setup and a webhook.

relayshield.net/badge

---

## Farcaster (320 char max — one cast)

We launched a free public security badge for DeFi protocols.

One line of code → live risk score on your site, updated hourly. Monitors stealer logs, vendor credentials, oracle provider risk, threat actor IOCs.

The layer the Polymarket attacker exploited. The layer auditors don't cover.

relayshield.net/badge

---

## Mastodon — infosec.exchange (500 char)

New: free public security badge endpoint for DeFi protocols and prediction markets.

`GET https://api.relayshield.net/v1/badge?domain=yourprotocol.xyz`

Returns a live SVG — green/yellow/orange/red based on:
→ Employee credentials in stealer log corpus
→ Service account / oracle key exposure
→ Vendor supply chain risk
→ Threat actor IOC attribution

The Polymarket attack was detectable days in advance from exactly these signals.

Badge is free. relayshield.net/badge

t.me/RelayShield for updates.

---

## infosec.exchange — Mastodon security community variant (500 char)

For the DeFi/prediction markets folks here:

We ingested the full UNC4221/UAC-0185 IOC set (June 2026 bulletin — 32 indicators, CERT-UA#12414) and launched a free public badge endpoint that DeFi protocols can embed to show live credential-layer risk status.

`https://api.relayshield.net/v1/badge?domain=example.com`

The credential/supply chain attack vector is real, it's active, and it's unmonitored by most DeFi security tooling.

relayshield.net/badge | t.me/RelayShield

---

## Notes on sequencing

1. **Publish Polymarket blog first** (Hashnode) — the posts above reference it
2. **X thread** — drop same day as blog, link the post in tweet 4
3. **Farcaster + Mastodon** — same day, 30 min apart
4. **infosec.exchange** — target the security researcher audience, not just DeFi
5. **DM to warm contacts** — nephew's connection, any Solana DeFi team you have a thread with
6. **Do NOT blast the badge** before you have at least one protocol willing to install it — social proof matters for the second wave of installs
