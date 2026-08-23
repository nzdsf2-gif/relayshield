# Competitive benchmark: RelayShield vs SOCRadar

*Written 2026-08-23. Top-10 item 5.*

## The rule this document is built on

**Every claim about our corpus is `measured_exclusive_share` per category. The 511K headline appears
nowhere.**

This is not style. The Segment 1 outreach nearly went out resting on 511K, and the finding that
killed it was that the majority of those indicators are ingested third-party feeds — abuse.ch
(URLhaus, ThreatFox, Feodo) and CISA KEV — which the buyer already has. A benchmark that repeats
that mistake fails the same way, except it fails **in front of a competitor's customer**, who has
the other side of the comparison open in the next tab and every reason to check.

SOCRadar's own marketing leans on breadth. We cannot win a breadth argument and must not start one.

### Producing the numbers

Numbers below marked `MEASURE` are placeholders. They are filled by:

```
cd "$HOME/Side SaaS Hustle"
AWS_PROFILE=relayshield python3 tools/exclusive_share_by_category.py --markdown
```

That tool reuses `tools/export_intel_sample.py`'s own feed classification, so its per-category
figures reconcile exactly with the corpus-wide `measured_exclusive_share` already quoted in the
sample manifest, rather than being a second measurement that disagrees by a percent.

Any category it flags `⚠️` (fewer than 100 collected indicators) **does not go in this document at
all.** A 100% exclusive share over 12 wallets is not a claim, and putting it next to a vendor with a
dedicated research team invites exactly the audit we would lose.

---

## What SOCRadar actually is

An Extended Threat Intelligence (XTI) platform, sold to security teams, combining three product
areas: External Attack Surface Management, Cyber Threat Intelligence, and Digital Risk Protection.
Sold as six tiers — XTI Essential, Essential / Business / Ultimate-Flex Dark Web Monitoring,
Ultimate Brand Protection, and a Freemium tier.

**Publicly quoted pricing** (third-party aggregators, not SOCRadar's own page — treat as indicative,
confirm before using in a deal):

| Tier | Listed |
|---|---|
| Essential Dark Web Monitoring | ~$3,950/yr |
| Business Dark Web Monitoring | ~$6,950/yr |
| XTI Essential, Ultimate-Flex, Ultimate Brand Protection | custom quote |
| Freemium | free — one-year access to CTI tools; one-week Business trial |

They are an enterprise platform sale with a free on-ramp. That shape matters more than the exact
figure, and it is the thing to design against.

---

## Dimension 1 — Coverage

| | SOCRadar | RelayShield |
|---|---|---|
| Positioning | Breadth: forums, marketplaces, leak sites, paste sites, Telegram, botnet activity | Depth in a narrow lane |
| Corpus claim | Not published as a single number | We do not publish one either — per-category exclusive share only |
| Exclusive share, `tg_handle` | n/a — not a category they surface | `MEASURE` |
| Exclusive share, `domain` | Overlaps our feed sources heavily | `MEASURE` — expect low; abuse.ch is common ground |
| Exclusive share, wallets | Not a focus | `MEASURE` |
| Historical depth | Years | Months. **This is a real loss, state it** |

**Honest reading:** on coverage we lose on breadth and on history, and both are structural. The
categories where we can win are the ones public feeds do not publish — `tg_handle` above all, since
feeds publish infrastructure, not people. That is the whole argument, and it lives or dies on the
measured number.

⚠️ `tg_handle` is a **lead list, not a verdict** — `_RE_TG_CHANNEL` matches any `@mention`. It must
never be described as "known scam operators" in this document or anywhere else without filtering.

---

## Dimension 2 — Collection surface

| | SOCRadar | RelayShield |
|---|---|---|
| Telegram | Yes — channels and private groups | Yes — 122 channels, 95 reachable |
| Dark web forums / marketplaces | Yes, at scale | No |
| Ransomware leak sites | Yes | Yes (`relayshield_intel_ransomware`) |
| Stealer logs | Yes | Yes (INTEL-5) |
| Automated crawlers + AI analytics | Yes | Partial |
| **Victim-submitted live attacks** | **No** | **Yes — Telegram, WhatsApp, Discord `/scan`** |

**The one asymmetry worth pressing.** Their collection is crawling; ours includes real victims
pasting real attacks in real time, typically before the domain reaches any feed. That surface is
structurally unavailable to a platform with no consumer footprint.

It is also now measurable rather than assertable: `relayshield_intel_pivot.py` logs every `/scan`
submission and re-checks the `unknown` ones at 24h / 72h / 7d, so a link clean on Monday and flagged
everywhere by Friday produces a timestamped lead time. `lead_time_summary()` reports the median
**with its sample size**.

**Do not use this section until that ledger has data.** "We see things first" with no measurement
behind it is exactly the 511K failure wearing a different hat. Once it has data it is the single
strongest claim in this document, because it is falsifiable and they cannot reproduce it.

Their published limitation — private channels, closed forums and bespoke marketplaces are hard to
monitor, and several forums from their own Top-10 research are outside their scope — is a fair thing
to note, but it cuts at us too. We have less access, not more.

---

## Dimension 3 — Pricing and packaging

| | SOCRadar | RelayShield |
|---|---|---|
| Model | Annual subscription, tiered by assets and scope | Subscription + x402 pay-as-you-go |
| Entry | ~$3,950/yr (indicative) | $0.05–$2.00 per call, no commitment |
| Free tier | Freemium, one year of CTI tools | Free tier on several endpoints |
| Procurement | Enterprise cycle, quote for most tiers | Self-serve; card or USDC |
| Marketplaces | — | AWS Marketplace, RapidAPI, n8n, Zapier, MCP |

**Where we genuinely win.** Not on price-per-unit — on **commitment**. A team that wants to check
400 domains once cannot do that with SOCRadar at any tier; they buy a year or they do not buy. That
is a different purchase, not a cheaper one, and it should be pitched as such.

Attacking them on headline price is a trap: they will discount, and we will have anchored the
conversation on a number where an enterprise buyer's instinct is that cheap means thin.

---

## Dimension 4 — Integrations

| Integration | SOCRadar | RelayShield |
|---|---|---|
| Microsoft Sentinel | Yes | PR #14924 open |
| Cortex XSOAR | Yes — content pack in the Marketplace | PR #45206 open |
| MISP | Yes — MISP server | Partial |
| STIX / TAXII | Yes — TAXII 2.1, STIX 2.1; Elastic ships an integration for it | TAXII endpoint exists |
| Splunk / QRadar | Yes | No |
| **MCP / agent-native** | Not documented | **Yes — PyPI, plus ElizaOS, n8n, Zapier** |
| Consumer channels | No | Telegram, WhatsApp, Discord |

**This is the weakest column for us and the document should say so.** They are ahead on every
classical SOC integration, and their TAXII server being shipped as a first-class Elastic integration
is a real distribution advantage we have no equivalent to. Both of our SIEM/SOAR integrations are
*open PRs*, not shipped — and until they merge, this row reads as intent.

The one column we lead is agent-native distribution, where nothing in their public material
suggests an MCP surface. That is a genuine lead, but it is a lead in a market that is still small,
and it should be presented as positioning rather than as a reason to switch.

---

## What we can defend, and what we cannot

**Defensible, once measured:**
1. Per-category exclusive share in categories public feeds do not carry — `tg_handle` first.
2. Measured lead time on victim-submitted indicators, quoted with its sample size.
3. No-commitment access to a corpus at all — a different purchase, not a cheaper one.
4. Consumer delivery channels they do not have.

**Not defensible, do not attempt:**
1. Corpus size. We lose, and 511K invites the audit that kills the rest.
2. Historical depth. Months against years.
3. Breadth of collection. They crawl surfaces we have no access to.
4. Classical SIEM/SOAR integration maturity — pending on both open PRs.
5. Anything about private-channel access. Their stated limitation is ours too, more so.

---

## Open questions before this goes anywhere

1. **Run the measurement.** Every `MEASURE` above. Nothing ships until then.
2. **Confirm SOCRadar pricing** against their own page — the figures here are third-party.
3. **Does their Freemium tier cover Telegram monitoring?** If yes, our free tier is not a
   differentiator and this document overstates the packaging argument.
4. **Wait for the `/scan` ledger.** Dimension 2's strongest claim is unmeasured today.
5. **Decide the audience.** A benchmark aimed at their customers must survive their rebuttal; one
   aimed at our own positioning can be franker about where we lose. This draft is written for the
   second and would need hardening for the first.

---

## Sources

- [SOCRadar plans and pricing](https://socradar.io/plans-and-pricing/)
- [SOCRadar Platform Pricing 2026 — ethicalhacking.ai](https://ethicalhacking.ai/pricing/socradar-platform-pricing)
- [SOCRadar pricing breakdown — costbench.com](https://costbench.com/software/threat-intelligence/socradar/)
- [Gartner Peer Insights — SOCRadar XTI](https://www.gartner.com/reviews/market/security-threat-intelligence-products-and-services/vendor/socradar/product/socradar-extended-threat-intelligence-platform)
- [How to use SOCRadar integrations](https://socradar.io/blog/how-to-use-socradar-integrations/)
- [SOCRadar Threat Intelligence (TAXII) — Elastic](https://www.elastic.co/docs/reference/integrations/ti_socradar_taxii)
- [Cortex XSOAR and SOCRadar XTI — Palo Alto Networks](https://www.paloaltonetworks.com/blog/security-operations/extend-threat-intelligence-with-information-processing-from-cortex-xsoar-and-socradar-xti/)
- [SOCRadar dark web monitoring tools](https://socradar.io/blog/top-10-dark-web-monitoring-tools/)
