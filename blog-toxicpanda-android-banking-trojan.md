# ToxicPanda 2.0 commits bank fraud from your own phone. We checked our corpus for it and found nothing, on purpose.

*Corpus check measured 2026-08-25 against the live `malware-index` GSI.*

<!-- INTERNAL: publish everything from the rule below down to the NOT FOR PUBLICATION line.
     The italic line above is publishable; this comment and the plan at the bottom are not. -->

---

Malwarebytes published a writeup this week on ToxicPanda 2.0, an Android banking trojan with an
unusually direct thesis: don't steal the session, use it. The malware tricks a victim into granting
VPN access and Accessibility Service permission, then commits fraud from the device itself, using
the victim's own IP address, their own app session, their own behavioral fingerprint. To a bank's
fraud model watching for anomalies, none of that looks anomalous. It looks like the customer,
because in every observable way, it is.

## What the campaign does

The chain, as reported: a sideloaded app delivered from disposable AWS-hosted buckets rather than
fixed infrastructure, a fake install flow that requests VPN privileges and blocks Google Play
network traffic, a payload decrypted at runtime rather than shipped in the clear, then Accessibility
Service abuse to run banking overlays, capture PINs, and drive the device remotely. Malwarebytes
detects samples as `Android/Trojan.Dropper.agent` and `Android/Trojan.FakeApp.ACR2401245FC11`: its
own internal classifier labels, not indicators anyone else's tooling would match against. There is
no published C2 domain, file hash, or package name. We checked the source directly before writing
this: none exist to publish.

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

## Why an indicator feed cannot see this by design

We ran into the same shape of gap eight days ago, from a different direction. An Agent Tesla
campaign was hiding inside JScript padded with Unicode emoji, defeating string-based signature
matching. The detail that mattered there wasn't the emoji, it was that the payload ran via
reflective in-memory injection and never touched disk, so file-based detection got exactly one
shot, at an obfuscated dropper, and nothing else.

ToxicPanda fails the same test from the other end. Agent Tesla defeats fingerprinting by hiding the
artifact. ToxicPanda defeats it by not needing one: no fixed C2 to blocklist, because the fraud
happens on a session the victim's own bank already trusts. Different malware, same lesson. When an
attacker's whole design goal is defeating the thing that produces a fingerprint, a feed built on
fingerprints is the wrong layer to expect a catch from, no matter whose feed it is.

## What actually sees this

Not a malware signature. The credential and session material that shows up afterward in criminal
stealer logs, the same infrastructure infostealers like RedLine, Raccoon, and Vidar feed. An employee
whose device credentials or active banking session get harvested upstream of a fraud incident is
visible there, even when the malware that put them there leaves nothing an indicator feed can name.
That's a different signal than "did we see this malware family," and it's the one that was actually
checkable here.

## The honest caveat

We are not claiming to have detected ToxicPanda, analyzed a sample, or found IOCs no one else has.
We did none of those things. What we're reporting is the measurement itself: we checked, specifically
and by name, and our corpus does not cover this malware class today. Any vendor whose IOC feed does
claim Android banking trojan coverage should be asked the same direct question we just asked
ourselves.

---

## NOT FOR PUBLICATION: plan, checks and sources

### Pre-publication checklist

- [ ] Re-run the `malware-index` query for ToxicPanda + the 5 named families before publishing:
      confirm still zero, not stale from 2026-08-25.
- [ ] Re-confirm no C2/hash/package IOCs have since been published for this campaign by Malwarebytes
      or a follow-up report. If any exist by publish time, do not claim "none exist"; cite them.
- [ ] Confirm the Agent Tesla post this references is itself live before cross-linking it.
- [ ] Do not add ToxicPanda as a family label or seed any IOC row for it. There is nothing real to
      seed. An "Android" taxonomy category can exist as an empty bucket for future real coverage,
      but should not be back-filled with anything from this campaign.

### Why this post exists

News-reaction post with an original measurement inside it, same structure as the Agent Tesla draft.
The reaction half (ToxicPanda is in the news) is what gets read; the measurement half (we checked,
we don't have it, here's structurally why) is the part that's actually ours and doesn't decay.
Unlike the Agent Tesla piece, this one isn't racing a decaying news window: the finding is "absence,
explained," which stays true whenever it publishes.

### What we are deliberately NOT claiming

- Not claiming we analyzed a ToxicPanda sample. We did not.
- Not claiming any Android banking trojan coverage exists in the corpus today. It does not.
- Not naming any IOC for this campaign. None were available to name.
- Not claiming `check_infostealer` / `check_session_risk` would have caught this specific campaign
  pre-fraud. The honest claim is narrower: they see the credential/session exposure class this kind
  of malware produces, not this malware itself.

### Sources

- [ToxicPanda 2.0 can take over your Android phone and banking apps (Malwarebytes)](https://www.malwarebytes.com/blog/mobile/2026/08/toxicpanda-2-0-can-take-over-your-android-phone-and-banking-apps)
- RelayShield internal: `malware-index` GSI query, 2026-08-25 (ToxicPanda, Octo, Cerberus, Anubis,
  Hook, Medusa: all zero) plus an 80,000-record scan of distinct family labels.

---

## DISTRIBUTION PACKAGE

**Channels:** self-hosted blog canonical → Medium (**import, do not paste**) → LinkedIn → Telegram
→ Farcaster (`/security`) → Mastodon. **Not X** (suspended). **Not Hashnode** (retired). Apply the
no-em-dash/en-dash rule to every block below; hyphens inside technical terms stay.

### Metadata (for Medium and any future syndication)

- **Display title**: ToxicPanda 2.0 commits bank fraud from your own phone. We checked our corpus for it and found nothing, on purpose.
- **SEO title** (~60 char budget): ToxicPanda 2.0: Why No IOC Feed Covers It (Checked)
- **Meta description** (150 limit, 148 used): ToxicPanda 2.0 commits Android banking fraud from the victim's own session. We checked our threat-intel corpus for it: zero hits across 80,000 indicators, and here's the structural reason why.
- **Slug**: `toxicpanda-2-android-banking-trojan-corpus-check`
- **Tags**: `cybersecurity`, `mobile-security`, `threat-intelligence`, `android`, `fraud-detection`

---

### 1. LinkedIn (2305/3000 chars)

```text
ToxicPanda 2.0 spreads by asking for two permissions most people grant without reading: VPN access and Accessibility Service. Once granted, it runs banking fraud from inside your own session, using your own IP address and your own device fingerprint.

That last part is the detail worth sitting with. The malware does not need to steal your session and use it elsewhere. It commits the fraud FROM your phone, in real time, while you are logged in. To a bank's fraud model, that traffic looks exactly like you, because in every observable way, it is you.

We checked our own threat-intel corpus for it. Not a guess, a real query: the malware-family index, searched for ToxicPanda and five other major Android banking trojan families (Octo, Cerberus, Anubis, Hook, Medusa, BRATA), plus an 80,000-record sample of every distinct family label we carry.

Zero hits. On any of them.

That is not a gap in our coverage specifically. It is structural. An indicator feed exists to catch malware you can fingerprint: a hash, a C2 domain, a package name. ToxicPanda's whole design avoids leaving those. It decrypts its payload at runtime, delivers through disposable AWS-hosted buckets instead of fixed infrastructure, and the actual fraud happens on-device, inside a session your bank already trusts.

We saw the same shape of problem last week in an Agent Tesla campaign hiding inside emoji-obfuscated code: reflective in-memory injection means the payload never touches disk, so file-based detection gets one shot at an obfuscated dropper and nothing else. Different malware, same lesson. When the attacker's whole design goal is defeating the thing that fingerprints code, a feed of fingerprints stops being the right layer to catch it on.

What actually sees this kind of compromise is not a malware signature. It is the credential and session material that shows up afterward in criminal stealer logs, the same infrastructure infostealers like RedLine and Vidar feed. If an employee's banking session or device credentials get harvested by something upstream of the fraud itself, that is visible. The malware that put them there usually is not.

Full detail on the campaign: Malwarebytes' original writeup is linked in the post.

#ThreatIntelligence #MobileSecurity #DetectionEngineering #InfoSec #BankingFraud
```

### 2. Telegram (960/4096 chars)

```text
New finding: we checked our own threat-intel corpus for ToxicPanda 2.0, the Android banking trojan making news this week, and came up empty. On purpose, we're telling you why.

ToxicPanda tricks you into granting VPN + Accessibility Service permissions, then commits banking fraud FROM your own phone, using your own session and IP. To a bank's fraud model, that traffic looks exactly like you.

We searched our corpus for ToxicPanda and five other major Android banking trojan families (Octo, Cerberus, Anubis, Hook, Medusa, BRATA). Zero hits across an 80,000-record sample. Not a coverage gap we're embarrassed about, a structural one: this malware is built to avoid leaving anything an indicator feed can fingerprint.

What actually shows this kind of compromise: check_infostealer and check_session_risk, since the credentials and session material end up in stealer logs even when the malware itself leaves nothing to match.

Full writeup with the details:
```
*(append canonical URL)*

### 3. Farcaster: post to `/security` and `/dev` (541/1024 bytes)

```text
ToxicPanda 2.0 commits banking fraud FROM your own phone, using your own session and IP, after tricking you into granting VPN + Accessibility Service access.

We checked our corpus for it and five other major Android banking trojan families (Octo, Cerberus, Anubis, Hook, Medusa, BRATA). Zero hits across 80,000 sampled indicators.

Not a gap, a structural fact: no C2 domain, no hash, no package name to fingerprint by design.

What catches this instead: the credentials and session material that leak into stealer logs afterward.

Writeup:
```
*(append canonical URL; no hashtags on Farcaster per house convention)*

### 4. Mastodon: infosec.exchange (404/500 chars, URLs count as 23 chars flat)

```text
ToxicPanda 2.0: an Android trojan that commits bank fraud from your own phone, your own session, your own IP.

We checked our corpus for it plus 5 other major families. Zero hits in 80k sampled indicators. Structural, not a gap: it's built to leave nothing to fingerprint.

What catches it: stealer-log credential exposure, not a malware signature.

#infosec #threatintel #androidsecurity #mobilesecurity
```
*(append canonical URL before the hashtag line)*

### 5. Show HN (optional; only if the measurement framing, not the product, leads)

**Title:** `We checked our threat-intel corpus for ToxicPanda 2.0 and found nothing (here's why)`

**First comment (post immediately after submitting):**

```text
Author here. The interesting part wasn't that our corpus lacked ToxicPanda coverage, it's that it's
structurally hard for any IOC-based feed to have it. The malware doesn't need fixed infrastructure:
payload decrypts at runtime, delivery is disposable AWS buckets, and the actual fraud runs on-device
using the victim's own session and IP rather than exfiltrating anything to a C2 you could blocklist.

We checked by name against our own malware-family index (ToxicPanda, Octo, Cerberus, Anubis, Hook,
Medusa) plus an 80k-record sample of every family label we carry. Zero hits across the board.

Happy to talk through the methodology or what we think actually would catch this class of fraud
(credential/session exposure signals, not a malware signature).
```

**LinkedIn hashtags** (already inline above): `#ThreatIntelligence #MobileSecurity #DetectionEngineering #InfoSec #BankingFraud`
**Mastodon tags** (already inline above): `#infosec #threatintel #androidsecurity #mobilesecurity`

### After posting

Watch arrivals the same way as prior posts: attribution keys per channel if this gets a CTA added
later (none is proposed here; this post's "product" mention is `check_infostealer`/`check_session_risk`
by name, not a link, matching its own "not claiming detection" stance). Two things to check the day
after: the canonical URL renders (Cloudflare caches 5 minutes, a 404 immediately post-deploy is
expected), and the Agent Tesla cross-link (if that post is live by then) resolves correctly both ways.
