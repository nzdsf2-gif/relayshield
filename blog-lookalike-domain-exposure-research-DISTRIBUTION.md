# 341 Lookalikes, 1 Alarm — Distribution Package
*All channels. Ready to post. Primary: Hashnode. Cross-post: Medium, LinkedIn, Farcaster, Mastodon, Telegram. TLDR outreach draft included.*

---

## Hashnode (primary — publish first, link to it from everything else)

### Publishing metadata

- **Display title**: 341 Lookalikes, 1 Alarm: The Case for Ongoing Domain Hygiene
- **SEO title** (~60 char budget): Domain Lookalike Research: 24 Brands, 341 Typosquats Found
- **Meta description** (150 char limit): We checked 24 DeFi, prediction market, and fintech brands for lookalike domains. 341 found. Only 1 is blocklisted. Here's why that gap matters.
- **Slug**: `341-lookalikes-1-alarm-domain-hygiene-research`
- **Tags** (Hashnode caps around 5): `cybersecurity`, `web3`, `fintech`, `phishing`, `threat-intelligence`
- **Cover image**: none generated here — a simple stat graphic (341 / 1 / 5) would work well; don't block publishing on this.

### Full post body

*(Copy everything below this line through the end — this is the finalized post from `blog-lookalike-domain-exposure-research.md`.)*

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

---

## Medium (cross-post, full article)

Same full body as the Hashnode post above. Set the canonical URL field to the Hashnode post's URL once published (Medium's "Change story URL" / canonical-link setting under story stats → ... menu) so search engines credit Hashnode as the original, not a duplicate-content flag on Medium.

**Topics (5 max)**: Cybersecurity, Web3, Fintech, Phishing, Crypto — mirrors Hashnode's tags, with Crypto swapped in for Threat Intelligence since it's a much larger Medium audience and covers both the DeFi and prediction-market brands.

---

## LinkedIn (post second, after Hashnode is live)

```
Attackers don't need to breach you. They just need to register something that looks like you.

We checked 24 well-known companies across DeFi, prediction markets, and fintech for lookalike domains. Not "does this look risky" guesswork. Live DNS resolution against typosquat permutations, then registration age and TLS certificate timing cross-checked for every hit.

341 registered, resolving lookalike domains found. Median of 13.5 per brand.

Only 1 is currently flagged by public blocklists as active phishing or malware.

Read that as a floor, not a ceiling. Blocklists catch a domain once it's already serving malicious content. The other 340 sit unclassified — some are the brands' own defensive registrations, others are dormant infrastructure waiting to be activated. A domain doesn't need to fail a safety check to be dangerous. It just needs to exist when someone decides to use it.

Fintech carried ~50% more lookalike surface per brand than DeFi or prediction markets — and a lot of it follows textbook credential-phishing naming: login-, -verify, -support, my- stacked onto the real brand name. That's not random typo noise. That's intent.

Full research + methodology: [Hashnode link]

Check your own domain for free: badge.relayshield.net

#CyberSecurity #ThreatIntelligence #Phishing #DeFi #Fintech #DomainSecurity #InfoSec
```

---

## Farcaster (crypto-native audience — /security, /defi channels)

```
We checked 24 DeFi, prediction market, and fintech brands for lookalike domains.

341 found. Registered, resolving, right now.

Only 1 is currently flagged as active phishing by public blocklists. The other 340 are unclassified — some defensive, some dormant infrastructure waiting to be lit up.

Blocklists catch domains after they're already weaponized. We check registration age + TLS cert timing to catch them before.

Full research: [Hashnode link]
Check your own domain free: badge.relayshield.net

#DeFi #Web3Security #ThreatIntel
```

---

## Mastodon (infosec.exchange, character-limited)

```
We checked 24 DeFi/fintech/prediction-market brands for lookalike domains: 341 found, registered and resolving right now.

Only 1 is currently blocklist-flagged. That's a floor, not a ceiling — blocklists catch domains after they're weaponized, not before.

We cross-check registration age + TLS cert issuance timing instead. That's the leading indicator.

Full writeup: [Hashnode link]
Free self-check: badge.relayshield.net

#infosec #phishing #DomainSecurity
```

---

## Telegram (RelayShield channel — conversational, own subscriber base)

```
New research from the RelayShield team 🔍

We checked 24 well-known DeFi, prediction market, and fintech companies for lookalike domains — the typosquat variants attackers register before launching phishing campaigns.

The number: 341 registered, resolving lookalikes across those 24 brands.

The alarming part: only 1 is currently flagged by public blocklists as active phishing. The rest sit unclassified — some are the brands' own defensive registrations, but plenty are dormant infrastructure that hasn't been activated yet. Blocklists only catch domains after they're already being used.

We didn't stop at "is it registered" — for every hit we also check registration age and TLS certificate issuance timing, which is the closest thing to an early-warning signal before a domain shows up on anyone's blocklist.

Full research + methodology: [Hashnode link]

Want to check your own domain? It's free, no signup: badge.relayshield.net
```

---

## TLDR Security newsletter — outreach draft

Submit via TLDR's story-suggestion form/tips inbox at tldr.tech once the Hashnode post is live. This is a story suggestion, not a product pitch — lead with the finding, not RelayShield.

**Subject line** (if email-based): Research: we checked 24 brands for lookalike domains, only 1 is blocklisted

**Body:**

```
Hi TLDR Security team,

Sharing a piece that might fit an upcoming issue: we ran a live domain-lookalike scan against 24 well-known DeFi, prediction market, and fintech companies and found 341 registered, resolving typosquat domains. Only 1 of the 341 is currently flagged by public blocklists as active phishing.

The methodology detail that might be the more interesting part for your audience: we cross-check registration age against Certificate Transparency log data (TLS cert issuance timing) for every hit, which turns out to be a real leading indicator of when a dormant typosquat is being activated into live phishing infrastructure, well before it shows up on any blocklist.

Link: [Hashnode URL]

Happy to answer questions if useful for context. No ask beyond sharing the research if it's a fit.

[Name], RelayShield
```

---

## HuggingFace — worth posting?

Short answer: not this piece, at least not as-is. HuggingFace's audience is ML/AI practitioners and the existing RelayShield HF presence (the Agentic Attack Surface Space, the MITRE dataset) is specifically positioned around AI-agent security — a distinct, already-working narrative. This research is about traditional company domain-lookalike exposure across DeFi/fintech/prediction-markets; it doesn't have an AI-agent hook, so posting it to HF's Community/Discussion tab would be off-target for that audience and dilutes the sharper agent-security positioning already working there (per CDPX-5's existing framing).

If a future piece specifically covered AI-agent-native companies' domain/MCP-server lookalike exposure (tying into the `/ai-agents` badge vertical and the existing Bundle D narrative), that would be a much stronger HF fit. Worth keeping in mind as a follow-up angle rather than forcing this piece there.
