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

**Paste-ready copy lives in `bundle_d_launch_posts/` as plain `.txt` files.**

Do not copy the text out of this document. Everything below is a description of what to post; the
actual copy is in those files, as plain ASCII with no Markdown, no `>` quote markers and no smart
punctuation, so a straight paste gives you exactly what should appear in the box.

Safest way to load one, which also avoids the shell mangling UTF-8:

```bash
LC_CTYPE=UTF-8 pbcopy < bundle_d_launch_posts/linkedin.txt
```

| File | Channel | Notes |
|---|---|---|
| `linkedin.txt` | LinkedIn | Body only. Hashtags included at the end. |
| `linkedin-comment.txt` | LinkedIn | The canonical URL, posted as the **first comment**. LinkedIn suppresses reach on posts with an outbound link in the body. |
| `x-thread.txt` | X / Mastodon / Farcaster | Four parts, split on the `[n/4]` markers. Do not paste the markers. All four verified under 280 characters with X's 23-character URL allowance. |
| `telegram.txt` | Telegram | Link inline, no separate comment needed. |

**The link to use everywhere is the bare canonical post URL:**

```
https://blog.relayshield.net/your-ai-agents-have-credentials-someone-is-already-looking-for-them
```

No `?src=` on it. The blog ignores that parameter entirely (verified), and the post's own call to
action already carries `?src=llmjacking` through to the developers page. `?src=` belongs only on
links that point directly at `/developers`, which is mainly the practitioner-community case.

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
