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

**This applies only when you link `/developers` directly.** When you link the blog post, use the
bare canonical URL: the blog ignores `?src=`, and the post's own CTA carries it onward.

| Context | Link to use |
|---|---|
| From the launch post, anywhere | `...developers?src=llmjacking` (already in the post) |
| Any AWS context | `...developers?src=aws` |
| Hacker News / Reddit | `...developers?src=hn` |
| n8n community | `...developers?src=n8n` |
| Hugging Face | `...developers?src=huggingface` |

Aliases resolve, so `blog`, `medium`, `linkedin`, `telegram` and `post` all land on the LLMjacking
variant, and `hn`/`reddit` land on the GitHub one. An unknown value falls back to the plain page
rather than erroring.

**2. Lead with LLMjacking, never with the listing.** "We launched an AWS Marketplace bundle" is a
press release nobody asked for. "A $30 stolen key against a $46,000 a day burn rate, and your SIEM
sees nothing" is a story. The bundle is the last line, not the first.

---

## Sequence

### Now: owned channels

The copy is reproduced below so you can read it in one place. **Do not copy it out of this file.**
Markdown mangles a paste. Use the matching plain-ASCII file in `bundle_d_launch_posts/`, loaded
straight onto the clipboard:

```bash
LC_CTYPE=UTF-8 pbcopy < bundle_d_launch_posts/linkedin.txt
```

The `LC_CTYPE=UTF-8` matters: this shell has no locale set and a bare `pbcopy` corrupts non-ASCII.

---

### LinkedIn: TWO separate pastes

LinkedIn suppresses reach on posts carrying an outbound link in the body, so the links go in the
first comment. That means two actions, in this order:

**Paste 1 of 2 — the post body** (`linkedin.txt`). Note it references the AWS bundle in text but
carries no URL, which is the point.

```
Your EDR would see nothing. Your SIEM would see nothing. Your cloud posture tool would see nothing.

If one of your AI agents leaked its Anthropic or OpenAI key tomorrow, the first signal you would get is the bill.

Sysdig measured $46,000 a day from compromised Bedrock credentials. A single leaked Gemini key ran $82,000 in 48 hours. Stolen LLM keys sell for about $30.

That gap is not a tooling failure. Every one of those controls is working correctly. They are watching for data leaving the building, and nothing is leaving the building. The stolen thing is compute, and it is being spent on someone else's behalf.

We now match 19 LLM credential formats across 14 providers against 4.6M indicators from 83 criminal Telegram channels:

OpenAI (all three key formats), Anthropic, Google Gemini, Amazon Bedrock (long and short lived), xAI Grok, Groq, NVIDIA NIM, Replicate, Hugging Face, LangSmith.

And the ones most tooling misses entirely: DeepSeek, Moonshot Kimi, Qwen via Alibaba DashScope, and Alibaba Cloud Model Studio.

That last group matters more than its size suggests. Teams adopt DeepSeek and Qwen because inference is cheap, so those keys land in prototypes and side projects that never got the review a production OpenAI key would get. A scanner built only for US provider formats does not fail loudly on a leaked DeepSeek key. It returns clean, because it was never looking for that shape of string. A confident all clear is worse than a missed alert.

This shipped today as Agentic Attack Surface, our new bundle on AWS Marketplace: LLM credential exposure, MCP registry risk, prompt injection breach detection, agent framework CVE monitoring and per-agent identity risk scoring. $299/mo, billed through your existing AWS account, no separate payment method.

There is also a free check that needs no API key at all. Both links in the comments.

#LLMjacking #AIsecurity #ThreatIntelligence
```

**Paste 2 of 2 — post this as the FIRST COMMENT immediately after publishing** (`linkedin-comment.txt`):

```
Full write-up, including the free no-key check:
https://blog.relayshield.net/your-ai-agents-have-credentials-someone-is-already-looking-for-them

Agentic Attack Surface on AWS Marketplace:
https://aws.amazon.com/marketplace/pp/prodview-6p6csngrcg3zq
```

### X / Mastodon / Farcaster: five parts

Split on the `[n/6]` markers. **Do not paste the markers themselves.** All six verified under 280
characters using X's 23-character URL allowance, longest is 249.

```
[1/6]
A stolen LLM API key is not a door into your systems. It IS the thing being stolen. It converts directly into compute that you pay for and someone else uses.

[2/6]
Sysdig: $46,000/day from compromised Bedrock creds. One leaked Gemini key: $82,000 in 48 hours. Operation Bizarre Bazaar: 35,000+ sessions in 40 days, $100K+/day. Stolen keys sell for ~$30.

[3/6]
Here is what makes it nasty. No endpoint compromised, so EDR sees nothing. No anomalous login, so the SIEM sees nothing. No data exfiltrated, so DLP sees nothing. Your first signal is the invoice.

[4/6]
We match 19 key formats across 14 providers: OpenAI (3 formats), Anthropic, Gemini, Bedrock, xAI Grok, Groq, NVIDIA NIM, Replicate, Hugging Face, LangSmith. Plus DeepSeek, Moonshot Kimi, Qwen and Alibaba Cloud.

[5/6]
Most tooling misses that last group. DeepSeek and Qwen keys land in cheap prototypes nobody reviewed. A US-formats-only scanner returns clean on a leaked DeepSeek key: it never looked for that string shape. A confident all clear is the worst result.

[6/6]
Shipped today as Agentic Attack Surface on AWS Marketplace. $299/mo via your AWS account. Free check, no key required:

https://blog.relayshield.net/your-ai-agents-have-credentials-someone-is-already-looking-for-them

https://aws.amazon.com/marketplace/pp/prodview-6p6csngrcg3zq

#LLMjacking #infosec #AIsecurity
```

### Telegram: one paste

Existing subscribers are already warm, so both links go inline and there is no comment step.

```
Your EDR would see nothing. Your SIEM would see nothing. Your cloud posture tool would see nothing.

If one of your AI agents leaked its Anthropic or OpenAI key tomorrow, the first signal you would get is the bill.

Sysdig measured $46,000 a day from compromised Bedrock credentials. A single leaked Gemini key ran $82,000 in 48 hours. Stolen LLM keys sell for about $30.

We now match 19 LLM credential formats across 14 providers against 4.6M indicators from 83 criminal Telegram channels:

OpenAI (all three formats), Anthropic, Google Gemini, Amazon Bedrock, xAI Grok, Groq, NVIDIA NIM, Replicate, Hugging Face, LangSmith.

Plus the ones most tooling misses: DeepSeek, Moonshot Kimi, Qwen via Alibaba DashScope, Alibaba Cloud Model Studio.

Teams adopt DeepSeek and Qwen because inference is cheap, so those keys end up in prototypes that never got reviewed. A scanner built only for US formats does not fail loudly on a leaked DeepSeek key. It returns clean, because it was never looking for that shape of string.

This shipped today as Agentic Attack Surface, our new bundle on AWS Marketplace. $299/mo, billed through your existing AWS account. There is also a free check that needs no API key.

Full write-up:
https://blog.relayshield.net/your-ai-agents-have-credentials-someone-is-already-looking-for-them

On AWS Marketplace:
https://aws.amazon.com/marketplace/pp/prodview-6p6csngrcg3zq
```

### The two links

Every post carries one or both of these. Never a search link, never with `?src=` on the blog URL.

```
Blog post (canonical):
https://blog.relayshield.net/your-ai-agents-have-credentials-someone-is-already-looking-for-them

AWS Marketplace (Bundle D product page):
https://aws.amazon.com/marketplace/pp/prodview-6p6csngrcg3zq
```

The blog ignores `?src=` entirely (verified), and the post's own call to action already carries
`?src=llmjacking` through to the developers page. `?src=` belongs only on links pointing directly at
`/developers`.

### +1 day: Medium

**Import a story**, do not paste. Paste has zero Markdown support and mangles the formatting; import
sets the canonical link back to the blog in the same step. Source URL is the canonical above.

### +2 days: Hacker News

Submit as **Show HN only if the free tool is the subject**, otherwise a plain link post titled around
the threat, not the product:

```
LLMjacking: the credential theft your SIEM structurally cannot see
```

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
- ~~AWS Marketplace search index had not picked up Bundle D.~~ **Resolved 2026-07-30**, it now
  appears in search. The AWS-specific angle is safe to push.
- ~~Swap the search placeholder for the direct product page URL.~~ **Done 2026-07-30.** The listing
  indexed and the direct page is live:
  https://aws.amazon.com/marketplace/pp/prodview-6p6csngrcg3zq
  Verified it resolves to Bundle D with all six prices correct. Updated in the blog post and on all
  four badge pages. **Use this URL, not a search link, in every social post.** Strip the tracking
  params (`?sr=`, `?ref_=`, `applicationId=`) that the console appends.
