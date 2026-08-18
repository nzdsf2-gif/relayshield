# RelayShield vs. Flashpoint, Recorded Future, Intel 471, SOCRadar, Cyble, Searchlight Cyber

*Competitive benchmark — 2026-07-24*

## The core finding

Unlike the prior benchmark (GitGuardian/GreyNoise/Team Cymru/CyberArk — adjacent categories, not real competitors), these six sit in the *exact same category* as RelayShield: criminal-forum/marketplace/dark-web OSINT correlated to a specific org or person. This is the real competitive set. The honest read: every one of them operates a materially deeper collection pipeline than RelayShield does today — vetted human access to closed forums, hundreds of billions of records, dedicated Tor infrastructure — while RelayShield's current OSINT corpus is ~52 curated/keyword-verified public Telegram channels plus a handful of free clearnet feeds (abuse.ch, a ransomwatch GitHub mirror, CISA KEV). That gap is real and is exactly what prompted this benchmark.

| | Collection depth | Distinguishing mechanism | Price band |
|---|---|---|---|
| **RelayShield** | Public Telegram channels + free clearnet feeds | Agent-native (MCP/x402), self-serve PAYG, cheapest by an order of magnitude | $0.10–$2/call, $499–$999/mo TI |
| Flashpoint | Vetted human analysts inside closed forums/marketplaces | "Primary Source Collection" — human-operated access, not scraping | Enterprise, quote-only |
| Recorded Future | Hundreds of Tor sites, IRC, forums, paste sites, Telegram | AI-linked chatter → CVE/actor/IOC correlation | $3K–$25K+/mo, up to $250K/yr |
| Intel 471 | Closed forums, IM groups, data-leak blogs, marketplaces | Verity471 unified CTI + exposure + threat-hunting platform | Enterprise, quote-only |
| SOCRadar | Open/deep/dark web + social | AI copilot for investigation workflows, SIEM/SOAR native | Mid-market, faster/cheaper than the above |
| Cyble | Dark/deep/surface web, AI-native enrichment | Broadest scope (physical threats, deepfakes, DFIR bundled in) | Enterprise, quote-only |
| Searchlight Cyber | 475B+ records; forums, marketplaces, onion sites, chat | **Tor network traffic monitoring** — detects an org's own infra talking to Tor, not just content scraping | Enterprise, quote-only |

---

## Flashpoint

Human-operated **Primary Source Collection** inside closed forums/marketplaces/encrypted channels — not automated scraping, actual vetted analyst access. Payment-fraud tracking (compromised cards, BINs, money-mule setups) across illicit card shops. CVE Dashboard ranks CVEs by *actor discussion volume* over the last 30 days, not just severity.

**Gap for RelayShield**: no BIN/stolen-card monitoring endpoint at all today. No "actor discussion volume" signal on CVEs — `tech-stack-cve` and `threat-actor` cover exploit chatter and KEV/EPSS, but not a ranked "how hot is this CVE in criminal conversation right now" score.

[Sources: flashpoint.io/why-flashpoint/dark-web-threat-intelligence-platforms, flashpoint.io/blog/understanding-illicit-ecosystems-dark-web-forums-cybercrime]

## Recorded Future

The scale leader — hundreds of Tor sites, IRC channels, forums, paste sites, plus Telegram, tracked as criminal infrastructure rotates IPs/domains. AI automates linking dark-web chatter to specific CVEs, actors, and IOCs. Priced for enterprises with dedicated CTI analysts ($3K–$25K+/mo, up to $250K/yr) — explicitly "overkill if you only need credential monitoring."

**Gap for RelayShield**: real collection depth. **Not a gap**: RelayShield's whole pricing thesis (self-serve PAYG, $0.10–$2/call, no CTI-analyst headcount required) is a direct structural answer to Recorded Future's own stated weakness — it validates the underdog positioning rather than exposing a hole.

[Sources: recordedfuture.com/blog/dark-web-monitoring, decryptiondigest.com/blog/dark-web-monitoring-free-vs-paid-comparison]

## Intel 471

Verity471 (launched 2025) unifies CTI + exposure monitoring + threat hunting. Real-time **keyword and forum watchers** across text, **images, and logos** — visual brand-impersonation detection, not just text matching. Monitors closed forums/IM groups/data-leak blogs/marketplaces for goods (data, cards) being sold.

**Gap for RelayShield**: `brand-monitor` is text-only (plain-string domain match against message text) — no image/logo recognition at all. This is a real, concrete, buildable gap (OCR + logo-hash matching against known brand assets is a well-understood pattern, not exotic).

[Sources: intel471.com/use-cases/dark-web-monitoring-and-investigations, intel471.com/platform/cyber-threat-intelligence]

## SOCRadar

Positioned as the strongest mid-market pick — faster/cheaper than the big four above. Fraud protection covers stolen credit cards, financial credentials, banking scams. **SOCRadar Copilot** — an AI assistant that accelerates analyst investigation workflows inside the platform.

**Gap for RelayShield**: same card/fraud gap as Flashpoint. On the Copilot idea specifically — **not really a gap**, arguably RelayShield's MCP/agent-native tools (an agent calling RelayShield's endpoints directly, not a human clicking through a dashboard copilot) is a more advanced version of the same "AI-assisted investigation" idea, just built the other direction (agent-as-caller vs. agent-as-assistant-to-a-human-caller). Worth stating this explicitly in positioning rather than treating it as a weakness.

[Sources: gartner.com/reviews/product/socradar-extended-threat-intelligence-platform, socradar.io/blog/top-10-dark-web-monitoring-tools]

## Cyble

Broadest scope of the six: dark/deep/surface web plus **deepfake detection and takedown**, physical threat monitoring, third-party risk management, DFIR — all bundled under one AI-native platform.

**Gap for RelayShield**: deepfake detection is a real, growing 2026 threat category (executive impersonation via AI-generated video/audio for fraud/social engineering) with zero RelayShield equivalent. Physical-threats monitoring is out of scope/not a fit for RelayShield's identity-exposure thesis — correctly excluded, not a gap worth chasing.

[Sources: cyble.com/products/cyble-vision, cyble.com/blog/dark-web-intelligence-monitoring-guide]

## Searchlight Cyber (DarkIQ)

475B+ records across forums, marketplaces, onion sites, chat platforms — real collection scale. All alerts MITRE ATT&CK-mapped. The genuinely distinctive feature: **Tor traffic monitoring** — detects when an organization's *own network* is talking to the Tor network (inbound/outbound connections to any IP/CIDR/domain on the customer's infra), a network-telemetry signal, not a content-scraping one.

**Gap for RelayShield**: this is a structurally different product (needs visibility into a customer's own netflow/DNS, not just OSINT scraping) — a bigger lift than any other item here, closer to a GreyNoise-style capability than a RelayShield-style one. Worth flagging as a "maybe, later, different engineering shape" rather than a near-term roadmap item.

[Sources: slcyber.io/products/darkiq, businesswire.com/news/home/20231205374872/en]

---

## Roadmap additions worth scoping (ranked by buildability, not just impact)

1. **BIN/stolen-card monitoring** (Flashpoint + SOCRadar both flag this) — a new `/v1/metered/card-exposure` endpoint checking submitted BINs/card fragments against the existing stealer-log/credential-dump corpus already being ingested. Near-zero new collection infra — the data's likely already flowing through `relayshield_intel_monitor.py`'s stealer-archive parsing, just never extracted/indexed as card data specifically.
2. **Image/logo brand monitoring** (Intel 471) — extends the existing text-based `brand-monitor` with OCR + perceptual-hash logo matching against a customer's uploaded brand assets. Moderate lift, well-understood pattern (`relayshield_infostealer_monitor.py` already has an OCR path for screenshot-based MSGSCAN, real reusable groundwork).
3. **CVE "actor discussion heat" score** (Flashpoint) — a ranking signal layered onto existing `tech-stack-cve`/`threat-actor` data (how often a CVE appears in monitored channel chatter over a rolling window), not a new data source, just a new derived metric from data already being collected.
4. **Deepfake detection/takedown** (Cyble) — genuinely new capability, would need either a third-party deepfake-detection API partnership or meaningful new ML work. Real 2026 relevance, but the most expensive item on this list — scope as a "watch and revisit" item, not a near-term build.
5. **Tor network traffic monitoring** (Searchlight) — different product shape entirely (customer-network telemetry, not OSINT). Interesting but a genuinely separate engineering track — don't conflate with the OSINT-depth conversation below.

## The structural gap this benchmark actually surfaces

None of items 1–5 close the real gap: **collection depth**. Every one of these six vendors has either vetted human access to closed criminal forums/marketplaces or a Tor collection pipeline processing hundreds of billions of records; RelayShield has neither. That's the direct context for the "add bots to monitor Dread/XSS/Exploit" question this benchmark was requested alongside — see the separate discussion on that in-chat rather than here, since it's a build/legal-risk decision, not a benchmark finding.
