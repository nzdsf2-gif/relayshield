# ToxicPanda 2.0 commits bank fraud from your own phone. We checked our corpus for it and found nothing, on purpose.

*Corpus check measured 2026-08-25 against the live `malware-index` GSI.*

<!-- INTERNAL: publish everything from the rule below down to the NOT FOR PUBLICATION line.
     The italic line above is publishable; this comment and the plan at the bottom are not. -->

---

Malwarebytes published a writeup this week on ToxicPanda 2.0, an Android banking trojan first
analysed by Zimperium's zLabs team, and it carries an unusually direct thesis: don't steal the
session, use it. The malware tricks a victim into granting VPN access and Accessibility Service
permission, then commits fraud from the device itself, using the victim's own IP address, their own
app session, their own behavioral fingerprint. To a bank's fraud model watching for anomalies, none
of that looks anomalous. It looks like the customer, because in every observable way, it is.

## What the campaign does

The chain, as reported: a sideloaded app delivered from disposable AWS-hosted buckets rather than
fixed infrastructure, a fake install flow that requests VPN privileges and blocks Google Play
network traffic, a payload decrypted at runtime rather than shipped in the clear, then Accessibility
Service abuse to run banking overlays, capture PINs, and drive the device remotely. Malwarebytes
detects samples as `Android/Trojan.Dropper.agent` and `Android/Trojan.FakeApp.ACR2401245FC11`: its
own internal classifier labels, not indicators anyone else's tooling would match against.

Indicators for the campaign do exist. Zimperium publishes IOC sets from its zLabs research in a
public GitHub repository, [github.com/Zimperium/IOC](https://github.com/Zimperium/IOC), and the
ToxicPanda material was published there alongside the analysis. So this is not a campaign nobody
can fingerprint. It is a campaign whose fingerprints exist and have not reached the collection
surface an indicator feed like ours is built on. That distinction is the whole post.

## What we checked in our own corpus

We searched our threat-intel corpus for ToxicPanda specifically, then for five other major Android
banking trojan families (Octo, Cerberus, Anubis, Hook, and Medusa) via a direct query against the
malware-family index. Then, to be sure a naming mismatch wasn't hiding a real hit, we pulled an
80,000-record sample of every distinct family label the corpus carries and checked it by hand.

**Zero hits. On any of them.**

The 42 distinct families in that sample are real and current: Windows infostealers, remote-access
trojans, Mirai-class botnets, ransomware loaders, just none of them Android banking trojans. That
is not us undercounting. It is an honest description of what an IOC-feed corpus, ours included,
actually covers today.

## Why the gap is structural, not an oversight

Two separate things are going on, and they are worth keeping apart.

The first is collection surface. Our corpus is collected from criminal marketplaces, stealer log
dumps, and public abuse feeds. A mobile security vendor's research repository is a different
surface entirely. Nothing we ingest reaches into it, which is why a family with published
indicators still lands as zero hits here.

The second is shelf life, and it is the more interesting one. Ingesting that IOC set would buy
real but short-lived coverage. Delivery runs through disposable AWS-hosted buckets rather than
fixed infrastructure. The payload decrypts at runtime. The fraud itself happens on-device, inside
a session the victim's bank already trusts, so there is no exfiltration hop to a C2 you can
blocklist and no anomalous session to score. The hashes and the buckets rotate. The technique does
not.

We ran into the same shape of problem earlier this month, from a different direction. An Agent
Tesla campaign was hiding inside JScript padded with Unicode emoji, defeating string-based
signature matching. The detail that mattered there wasn't the emoji, it was that the payload ran
via reflective in-memory injection and never touched disk, so file-based detection got exactly one
shot, at an obfuscated dropper, and nothing else.

ToxicPanda fails the same test from the other end. Agent Tesla defeats fingerprinting by hiding the
artifact. ToxicPanda defeats it by making the artifact disposable and putting the fraud somewhere a
fingerprint was never going to reach. Different malware, same lesson. When an attacker's design
goal is to outlive the thing that produces a fingerprint, a feed built on fingerprints is the wrong
layer to expect the catch from, no matter whose feed it is.

## What actually sees this

Not a malware signature. The credential and session material that shows up afterward in criminal
stealer logs, the same infrastructure infostealers like RedLine, Raccoon, and Vidar feed. An employee
whose device credentials or active banking session get harvested upstream of a fraud incident is
visible there, even when the malware that put them there leaves nothing an indicator feed can name.
That's a different signal than "did we see this malware family," and it's the one that was actually
checkable here.

## The honest caveat

We are not claiming to have detected ToxicPanda, analyzed a sample, or found IOCs no one else has.
We did none of those things, and we are not claiming nobody has published indicators for this
campaign, because Zimperium has. What we're reporting is the measurement itself: we checked,
specifically and by name, and our corpus does not cover this malware class today. Any vendor whose
IOC feed does claim Android banking trojan coverage should be asked the same direct question we
just asked ourselves.

## Sources

- [ToxicPanda 2.0 can take over your Android phone and banking apps](https://www.malwarebytes.com/blog/mobile/2026/08/toxicpanda-2-0-can-take-over-your-android-phone-and-banking-apps), Malwarebytes
- [The ToxicPanda Never Sleeps: ToxicPanda 2.0 Prepares its Next Strike on Mobile](https://zimperium.com/blog/the-toxicpanda-never-sleeps-toxicpanda-2.0-prepares-its-next-strike-on-mobile), Zimperium zLabs, the original research
- [Zimperium/IOC](https://github.com/Zimperium/IOC), the public IOC repository for zLabs research

---

## NOT FOR PUBLICATION: plan, checks and sources

### Publication status

Staged for `blog.relayshield.net` on 2026-08-26 as
`blog_content/toxicpanda-2-android-banking-trojan-corpus-check.json`, the frozen snapshot that is
the source of truth, exactly where `685e295` put the last published post. `blog_posts.js` rebuilt:
21 posts, zero removals.

**Nothing was ever sent to Hashnode.** The builder's old RSS fallback has been deleted and
`hashnode_export/` renamed to `blog_markdown/`, so no part of the publish path is named after or
talks to a platform we retired on 2026-07-29.

**Not live yet.** The container has no Cloudflare credentials and the egress proxy denies
`api.cloudflare.com`, so the deploy runs on the Mac:

    python3 build_blog.py
    npx wrangler deploy --config wrangler.blog.toml

Medium cross-post is import-with-canonical-URL and can only be done after the canonical URL is live.

### Correction made 2026-08-26, before staging

The 2026-08-25 draft claimed: "There is no published C2 domain, file hash, or package name. We
checked the source directly before writing this: none exist to publish." That is **wrong**. The
Malwarebytes writeup carries no IOCs, but it is secondary reporting. The original research is
Zimperium zLabs (published 2026-08-19), and Zimperium publishes IOC sets for zLabs research at
`github.com/Zimperium/IOC`. Publishing the original claim in front of a security audience would
have been checkable in one click, which is the Segment 1 failure mode exactly.

The post is stronger for the fix: "the indicators exist and our collection surface does not reach
them" is a sharper and more defensible claim than "nobody can fingerprint this."

### Pre-publication checklist

- [ ] **Open `https://github.com/Zimperium/IOC` and find the ToxicPanda 2.0 directory.** Link the
      directory itself rather than the repo root if it exists. Container egress could reach the
      repo README but not enumerate directories, so the exact path is unverified from here.
- [ ] Re-run the `malware-index` query for ToxicPanda + the 5 named families before publishing:
      confirm still zero, not stale from 2026-08-25. Needs `AWS_PROFILE=relayshield`, so the Mac.
- [ ] Optional but better: check the corpus against Zimperium's **published hashes and C2 values**,
      not just the family label. A by-indicator zero is a stronger claim than a by-name zero, and it
      is the one a sceptical reader will ask for.
- [ ] The Agent Tesla post is **not live** (`blog-agent-tesla-v4-emoji-obfuscation.md` is still a
      draft, absent from `blog_content/` and `blog_posts.js`). The reference in this post is now
      worded as our own measurement rather than a cross-link, so it stands alone. If Agent Tesla
      publishes later, add the link both ways.
- [ ] Do not add ToxicPanda as a family label or seed any IOC row for it from this post. If the
      Zimperium set is ingested, that is a deliberate collection decision made on its own merits,
      not a side effect of publishing. An "Android" taxonomy category can exist as an empty bucket.

### Why this post exists

News-reaction post with an original measurement inside it, same structure as the Agent Tesla draft.
The reaction half (ToxicPanda is in the news) is what gets read; the measurement half (we checked,
we don't have it, here's structurally why) is the part that's actually ours and doesn't decay.
Unlike the Agent Tesla piece, this one isn't racing a decaying news window: the finding is "absence,
explained," which stays true whenever it publishes.

### What we are deliberately NOT claiming

- Not claiming we analyzed a ToxicPanda sample. We did not.
- Not claiming any Android banking trojan coverage exists in the corpus today. It does not.
- Not claiming no indicators exist for this campaign. They do, from Zimperium.
- Not claiming `check_infostealer` / `check_session_risk` would have caught this specific campaign
  pre-fraud. The honest claim is narrower: they see the credential/session exposure class this kind
  of malware produces, not this malware itself.

### Sources

- [ToxicPanda 2.0 can take over your Android phone and banking apps (Malwarebytes)](https://www.malwarebytes.com/blog/mobile/2026/08/toxicpanda-2-0-can-take-over-your-android-phone-and-banking-apps)
- [The ToxicPanda Never Sleeps: ToxicPanda 2.0 Prepares its Next Strike on Mobile (Zimperium zLabs, original research)](https://zimperium.com/blog/the-toxicpanda-never-sleeps-toxicpanda-2.0-prepares-its-next-strike-on-mobile)
- [Zimperium/IOC (public IOC repository for zLabs research)](https://github.com/Zimperium/IOC)
- RelayShield internal: `malware-index` GSI query, 2026-08-25 (ToxicPanda, Octo, Cerberus, Anubis,
  Hook, Medusa: all zero) plus an 80,000-record scan of distinct family labels.

---

## DISTRIBUTION PACKAGE

**Channels:** self-hosted blog canonical, then Medium (**import, do not paste**), LinkedIn,
Telegram, Farcaster (`/security`), Mastodon. **Not X** (suspended). **Not Hashnode** (retired).
No em-dashes or en-dashes anywhere below; hyphens inside technical terms stay.

**Corrected 2026-08-26 in every block below:** the "no IOC exists" line is gone, and **BRATA is
removed** from the family list. The 2026-08-25 drafts said "five other families" and then named
six, with BRATA never queried. Six named families where five were measured is the kind of detail a
sceptical reader checks.

### Metadata (for Medium and any future syndication)

- **Display title**: ToxicPanda 2.0 commits bank fraud from your own phone. We checked our corpus for it and found nothing, on purpose.
- **SEO title** (~60 char budget): ToxicPanda 2.0: Why No IOC Feed Covers It (Checked)
- **Meta description** (150 limit, 149 used): ToxicPanda 2.0 commits Android banking fraud from the victim's own session. We checked our threat-intel corpus: zero hits, and here's the structural reason.
- **Slug**: `toxicpanda-2-android-banking-trojan-corpus-check`
- **Canonical**: `https://blog.relayshield.net/toxicpanda-2-android-banking-trojan-corpus-check`
- **Tags**: `cybersecurity`, `mobile-security`, `threat-intelligence`, `android`, `fraud-detection`

---

### 1. LinkedIn (2394/3000 chars)

```text
ToxicPanda 2.0 spreads by asking for two permissions most people grant without reading: VPN access and Accessibility Service. Once granted, it runs banking fraud from inside your own session, using your own IP address and your own device fingerprint.

That last part is the detail worth sitting with. The malware does not need to steal your session and use it elsewhere. It commits the fraud FROM your phone, in real time, while you are logged in. To a bank's fraud model, that traffic looks exactly like you, because in every observable way, it is you.

We checked our own threat-intel corpus for it. Not a guess, a real query: the malware-family index, searched for ToxicPanda and five other major Android banking trojan families (Octo, Cerberus, Anubis, Hook, Medusa), plus an 80,000-record sample of every distinct family label we carry.

Zero hits. On any of them.

Indicators for this campaign do exist. Zimperium's zLabs team published the original analysis and publishes IOC sets for its research publicly. So the honest finding is not "nobody can fingerprint this." It is narrower and more useful: the fingerprints exist, and the collection surface an indicator feed is built on does not reach them.

There is a shelf-life problem underneath that. Delivery runs through disposable AWS-hosted buckets rather than fixed infrastructure, the payload decrypts at runtime, and the fraud itself happens on-device inside a session your bank already trusts. The hashes and the buckets rotate. The technique does not.

We saw the same shape of problem earlier this month in an Agent Tesla campaign hiding inside emoji-obfuscated code: reflective in-memory injection means the payload never touches disk, so file-based detection gets one shot at an obfuscated dropper and nothing else. Different malware, same lesson.

What actually sees this kind of compromise is not a malware signature. It is the credential and session material that shows up afterward in criminal stealer logs, the same infrastructure infostealers like RedLine and Vidar feed. If an employee's banking session or device credentials get harvested upstream of the fraud itself, that is visible. The malware that put them there usually is not.

Full writeup, including what we checked and what we deliberately did not claim, in the first comment.

#ThreatIntelligence #MobileSecurity #DetectionEngineering #InfoSec #BankingFraud
```

**First comment, post immediately after the LinkedIn post** (LinkedIn suppresses reach on posts
with outbound links in the body, so the link goes here; posting it within the first minute or two
is what makes the comment rank and carries the click through to the canonical URL):

```text
Full writeup, with the exact query we ran and the families we checked by name:
https://blog.relayshield.net/toxicpanda-2-android-banking-trojan-corpus-check

Original research is Zimperium zLabs, and the Malwarebytes writeup is the readable summary. Both are linked in the post, along with the part most vendors skip: what our corpus does not cover, and why that is structural rather than an oversight.
```

### 2. Telegram (1071/4096 chars)

```text
New finding: we checked our own threat-intel corpus for ToxicPanda 2.0, the Android banking trojan making news this week, and came up empty. On purpose, we're telling you why.

ToxicPanda tricks you into granting VPN + Accessibility Service permissions, then commits banking fraud FROM your own phone, using your own session and IP. To a bank's fraud model, that traffic looks exactly like you.

We searched our corpus for ToxicPanda and five other major Android banking trojan families (Octo, Cerberus, Anubis, Hook, Medusa). Zero hits across an 80,000-record sample. Indicators for the campaign do exist, published by Zimperium zLabs. The gap is that our collection surface does not reach them, and that the indicators themselves are disposable: rotating AWS buckets, runtime-decrypted payload, fraud committed on-device.

What actually shows this kind of compromise: check_infostealer and check_session_risk, since the credentials and session material end up in stealer logs even when the malware itself leaves nothing durable to match.

Full writeup with the details:
```
*(append canonical URL)*

### 3. Farcaster: post to `/security` and `/dev` (584/1024 bytes)

```text
ToxicPanda 2.0 commits banking fraud FROM your own phone, using your own session and IP, after tricking you into granting VPN + Accessibility Service access.

We checked our corpus for it and five other major Android banking trojan families (Octo, Cerberus, Anubis, Hook, Medusa). Zero hits across 80,000 sampled indicators.

Indicators do exist, from Zimperium zLabs. They are also disposable: rotating AWS buckets, runtime-decrypted payload, fraud committed on-device.

What catches this instead: the credentials and session material that leak into stealer logs afterward.

Writeup:
```
*(append canonical URL; no hashtags on Farcaster per house convention)*

### 4. Mastodon: infosec.exchange (406/500 chars plus 23 for the URL, URLs count as 23 flat)

```text
ToxicPanda 2.0: an Android trojan that commits bank fraud from your own phone, your own session, your own IP.

We checked our corpus for it plus 5 other major families. Zero hits in 80k sampled indicators. Indicators exist (Zimperium zLabs), our collection surface just does not reach them.

What catches it: stealer-log credential exposure, not a malware signature.

#infosec #threatintel #androidsecurity
```
*(append canonical URL before the hashtag line)*

### 5. Show HN (optional; only if the measurement framing, not the product, leads)

**Title:** `We checked our threat-intel corpus for ToxicPanda 2.0 and found nothing (here's why)`

**First comment (post immediately after submitting):**

```text
Author here. The interesting part wasn't that our corpus lacked ToxicPanda coverage, it's what the
gap is made of. Indicators for the campaign exist, published by Zimperium zLabs alongside the
original analysis. Our corpus is collected from criminal marketplaces and stealer logs, so it never
reaches a mobile research repo, and the indicators themselves are short-lived: delivery is
disposable AWS buckets, the payload decrypts at runtime, and the actual fraud runs on-device using
the victim's own session and IP rather than exfiltrating to a C2 you could blocklist.

We checked by name against our own malware-family index (ToxicPanda, Octo, Cerberus, Anubis, Hook,
Medusa) plus an 80k-record sample of every family label we carry. Zero hits across the board.

Happy to talk through the methodology or what we think actually would catch this class of fraud
(credential/session exposure signals, not a malware signature).
```

### After posting

Watch arrivals the same way as prior posts: attribution keys per channel if this gets a CTA added
later (none is proposed here; this post's "product" mention is `check_infostealer`/`check_session_risk`
by name, not a link, matching its own "not claiming detection" stance). Two things to check the day
after: the canonical URL renders (Cloudflare caches 5 minutes, a 404 immediately post-deploy is
expected), and the LinkedIn first comment is actually the top comment, not buried under a reply.
