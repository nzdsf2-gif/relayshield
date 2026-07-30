# Bundle D launch: channel distribution plan

**Canonical post:** https://blog.relayshield.net/your-ai-agents-have-credentials-someone-is-already-looking-for-them
**Published:** 2026-07-30. Verified live: post page, index, RSS (17 items), sitemap.

Everything below points back to the canonical URL. Nothing gets a full re-post except Medium, which
imports with a canonical link.

---

## The two rules

**1. Always append `?src=` to the link.** The developers page now serves per-source variants, but
only if the link carries the parameter. Most Slack, Discord and native app clicks strip the referrer,
so without `?src=` the reader lands on the generic page and has to hunt for the thing that brought
them. Costs nothing, and it is the difference between a targeted landing and a bounce.

| Channel | Link to use |
|---|---|
| LinkedIn / X / Mastodon | `...developers?src=aws` |
| Hacker News / Reddit | `...developers?src=github` |
| n8n community | `...developers?src=n8n` |
| Any AWS context | `...developers?src=aws` |
| Hugging Face | `...developers?src=huggingface` |

**2. Lead with LLMjacking, never with the listing.** "We launched an AWS Marketplace bundle" is a
press release nobody asked for. "A $30 stolen key against a $46,000 a day burn rate, and your SIEM
sees nothing" is a story. The bundle is the last line, not the first.

---

## Sequence

### Now: owned channels

**LinkedIn** (primary, the buyer is here)

> Your EDR would see nothing. Your SIEM would see nothing. Your cloud posture tool would see nothing.
>
> If one of your AI agents leaked its Anthropic or OpenAI key tomorrow, the first signal you would get
> is the bill.
>
> Sysdig measured $46,000 a day from compromised Bedrock credentials. A single leaked Gemini key ran
> $82,000 in 48 hours. Stolen LLM keys sell for about $30.
>
> That gap is not a tooling failure. Every one of those controls is working correctly. They are
> watching for data leaving the building, and nothing is leaving the building. The stolen thing is
> compute, and it is being spent on someone else's behalf.
>
> We now match 19 LLM credential formats across 14 providers against 4.6M indicators from 83 criminal
> Telegram channels. Free check, no API key, link in comments.
>
> [canonical URL]

Put the link in the first comment, not the post body, if you want LinkedIn reach.

**X / Mastodon / Farcaster** (thread, 4 posts)

1. A stolen LLM API key is not a door into your systems. It IS the thing being stolen. It converts
   directly into compute that you pay for and someone else uses.
2. Sysdig: $46,000/day from compromised Bedrock creds. One leaked Gemini key: $82,000 in 48 hours.
   Operation Bizarre Bazaar: 35,000+ sessions in 40 days, $100K+/day. Stolen keys sell for ~$30.
3. Here is what makes it nasty. No endpoint compromised, so EDR sees nothing. No anomalous login, so
   the SIEM sees nothing. No data exfiltrated, so DLP sees nothing. Your first signal is the invoice.
4. We match 19 LLM key formats across 14 providers. Free check, no key required: [canonical URL]

**Telegram channel** — post the LinkedIn body verbatim with the link inline. Existing subscribers are
already warm; no reframing needed.

### +1 day: Medium

**Import a story**, do not paste. Paste has zero Markdown support and mangles the formatting; import
sets the canonical link back to the blog in the same step. Source URL is the canonical above.

### +2 days: Hacker News

Submit as **Show HN only if the free tool is the subject**, otherwise a plain link post titled around
the threat, not the product:

> LLMjacking: the credential theft your SIEM structurally cannot see

Do not submit the bundle. Do not mention AWS Marketplace in the title. If it gets traction, answer
questions in comments and let the product be discovered.

### +3 days: Reddit

- **r/netsec** — link post, threat framing. This subreddit removes anything that smells like vendor
  marketing, so the title must be about the technique.
- **r/msp** — different angle: "what happens when a client's AI agent leaks its API key and who eats
  the bill". MSP-relevant, and the MSP is the one who gets the call.

### Ongoing: practitioner communities (NOT broadcast)

These are relationship channels. A launch post gets ignored at best and removed at worst. What earns
standing is offering the free zero-key check when somebody asks about leaked keys.

| Community | Platform | Notes |
|---|---|---|
| Blue Team Village | **Discord**, 8,300+ | Defenders, DFIR, CTI. Better path: their **CFP**. "LLMjacking: the credential theft your SIEM structurally cannot see" is a real talk we have the data for. |
| r/msp Discord | Discord | The MSP buyer. Same rule: be useful first. |
| MSPGeek | Discord | As above. |
| Filigran / OpenCTI | **Slack**, ~6,500 | **DO NOT post Bundle D here.** Gated on OPENCTI-1 shipping, then post the integration guide. See DISTRIB-FILIGRAN-1 in TODO.md. |

---

## Hashtags

Keep them few. Three or four beats ten on every platform that still counts them, and LinkedIn
actively suppresses hashtag-stuffed posts.

**LinkedIn (3):** `#LLMjacking` `#AIsecurity` `#ThreatIntelligence`

**X / Mastodon (3):** `#LLMjacking` `#infosec` `#AIsecurity`

**Secondary pool**, swap in when the angle shifts:
`#CyberSecurity` `#MSP` `#MSSP` `#SecOps` `#AIagents` `#MCP` `#CloudSecurity` `#DevSecOps` `#AWSMarketplace`

`#LLMjacking` is the important one. It is the term the research community settled on, it is still low
volume, and being consistently present on it is worth more than reach on `#CyberSecurity`.

---

## The verified numbers

Live-checked 2026-07-30. Do not round up beyond these, and re-check before reusing in a later post:
growth makes them stale fast.

| Figure | Value | Safe to say |
|---|---|---|
| IOC corpus | 4,656,328 | "4.6M+" |
| Criminal Telegram channels | 83 active | "83+" |
| Threat feeds | 20 | "20+" |
| LLM credential formats matched | 19 | "19" |
| Named LLM providers | 14 | "14" |
| Metered API endpoints | 26 | "26" |

External figures, all attributable: $46,000/day (Sysdig, AWS Bedrock research); $82,000 in 48 hours
(leaked Google Gemini key, March 2026); 35,000+ sessions in 40 days and $100,000+/day (Operation
Bizarre Bazaar); 376% rise in AI-service credential theft Q4 2025 to Q1 2026 (Sysdig); ~$30 street
price for a stolen LLM credential.

**Attribute Sysdig by name every time.** The credibility of the whole post rests on these being
somebody else's measurements, not our marketing.

---

## What NOT to say

- **Never claim a clean result means safe.** The post is explicit that a clean check means nothing was
  found in the sources we queried. Do not let a social post overclaim what the post itself carefully
  qualifies.
- **Do not name customers**, including AWS Marketplace buyers.
- **Do not imply we detected any specific named incident.** We did not detect Bizarre Bazaar; we cite
  published research on it.
- **No em dashes.** House style as of this launch.

---

## Follow-ups

- Add `?src=` to the links in existing blog posts and integration listings. The variants shipped
  2026-07-30 and are doing nothing on old links.
- The AWS Marketplace search index had not picked up Bundle D at publish time (visibility flipped
  ~2h earlier). If a post drives someone to search and they find nothing, that is a bad first
  impression. Re-check before pushing the AWS-specific angle hard.
- Once the direct product page URL is available from the Management Portal, swap it into the badge
  pages (MKTPL-BADGE-1) and into any social post still pointing at a search link.
