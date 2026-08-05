# 341 Lookalikes, 1 Alarm: The Case for Ongoing Domain Hygiene

*RelayShield Threat Intelligence*

---

Attackers don't need to breach you. They just need to register something that looks like you.

A typosquat domain (a character swapped, a hyphen inserted, a `.io` instead of a `.com`) costs less than a coffee and takes thirty seconds to register. It doesn't need a vulnerability. It doesn't need a leaked credential. It just needs to sit there, resolving, waiting for a phishing kit, a fake login page, or a "support" email that looks close enough to fool someone in a hurry.

Most companies don't know how much of this surface already exists against their own name. So we checked.

---

## What we did

We ran RelayShield's own domain-lookalike detection against 24 well-known companies across three categories: DeFi protocols, prediction markets, and fintech/payments platforms. For each brand, the tool generates typosquat-shaped permutations (character swaps, TLD variants, phishing-style prefixes and suffixes like `login-` or `-support`) and checks which ones are actually registered and resolving right now.

Confirming a domain is registered is table stakes. Most typosquat-detection tools stop there. What matters more is what we do next: for every confirmed lookalike, we pull its registration age and cross-check Certificate Transparency logs for TLS certificate issuance, including how recently a cert was issued. A domain registered five years ago with no certificate history is almost certainly dormant or a defensive registration. A domain registered eleven days ago that just picked up its first TLS certificate is a site being stood up right now. Registration age and certificate timing, read together, separate "this typosquat exists" from "this typosquat is becoming infrastructure," and it's the closest thing to a leading indicator available before a domain ever shows up on a blocklist.

x402 USDC micropayments financed each domain search.

What follows is aggregated by category, with sample sizes large enough (8 brands per category) to infer meaningful insights.

---

## What we found

**341 registered, resolving lookalike domains across 24 brands.** Median of 13.5 per brand, ranging from 7 to 25.

| Category | Brands checked | Total lookalikes found | Avg per brand |
|---|---|---|---|
| DeFi | 8 | 96 | 12.0 |
| Prediction Markets | 8 | 95 | 11.9 |
| Fintech / Payments | 8 | 150 | 18.8 |

Fintech carries meaningfully more registered lookalike surface than the other two categories (roughly 50% more per brand than DeFi or prediction markets). That tracks: fintech brands are higher-value phishing targets, and the domains we found back that up. A large share of the fintech lookalikes follow recognizable credential-phishing naming conventions: `login-`, `-verify`, `-support`, and `my-` prefixes and suffixes stacked onto the real brand name. That's not a random typo distribution. That's the shape of domains registered with intent.

**Only 1 of the 341 is currently flagged as active phishing or malware by public blocklists.** Read that as a floor, not a ceiling: blocklists catch a domain once it's already serving malicious content, not before. The other 340 sit unclassified, some almost certainly defensive registrations by the brands themselves, others dormant infrastructure waiting to be activated. A domain doesn't need to fail a safety check to be dangerous. It just needs to exist when someone decides to use it.

**5 domains were registered within the last 90 days.** That's the bucket worth watching. Recent registration plus a typosquat-shaped name is the strongest signal available before a domain shows up on anyone's blocklist, because blocklists are reactive by design and this is the one signal that isn't.

---

## Why the gap matters

Standard security tooling reacts once a domain is actively serving malicious content, which means the detection window opens after the infrastructure is already live. Nobody is watching the layer before that (registration, resolution, certificate issuance), not because the data isn't available, but because checking it continuously isn't anyone's job until something's already gone wrong.

---

## Check your own exposure, free

Run the same check against your own domain. No cost, no signup required.

- **DeFi & prediction markets:** badge.relayshield.net/defi
- **Fintech & payments:** badge.relayshield.net/fintech
- **SaaS & dev tools:** badge.relayshield.net/saas
- **AI-agent-native companies:** badge.relayshield.net/ai-agents

If you like what you see, embedding RelayShield's badge is a separate step worth taking: it turns a one-time check into a standing signal. It updates hourly, and it's visible to your own visitors and customers, not just your internal team. Anyone who lands on your site sees, continuously, that someone is watching the domain-lookalike layer around your brand, not just being told you take it seriously.

For programmatic access, bulk checks, webhook alerts on new registrations, or integration into your own security tooling, the same check is available via API. Documentation at api.relayshield.net/developers.

---

*RelayShield monitors the credential and domain layer continuously, not just after something's already gone wrong.*

*© 2026 RelayShield LLC · relayshieldadmin@gmail.com*
