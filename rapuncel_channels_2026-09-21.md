# Rapuncel post: every channel, with hashtags and tags

**Canonical:** `blog_markdown/the-edr-was-dead-before-the-theft-started.md`, built into
`blog_posts.js`. **dev.to file:** `the-edr-was-dead-before-the-theft-started-devto.md`,
generated from the canonical body rather than written by hand.

**Canonical URL** (it must be LIVE before any syndication):

```text
https://blog.relayshield.net/the-edr-was-dead-before-the-theft-started
```

**House order, and it is not negotiable:** blog.relayshield.net canonical, then Medium,
then dev.to, then LinkedIn, then Telegram, then Farcaster, then Mastodon. **Not X**
(`@RelayShieldHQ` is suspended) and **not Hashnode** (abandoned 2026-07-29).

**Every `?source=` key below is registered in this commit**, before anything ships. One key
per CHANNEL, all rendering the same banner: the raw parameter is what gets logged, so the
destinations stay separable in CloudWatch while the landing is identical.

---

## NOT FOR PUBLICATION -- read before sending

**EVERY FACT IN THIS POST IS SECONDARY EVIDENCE AND THE POST SAYS SO.**
`blog.lastpass.com`, `techtimes.com`, `gbhackers.com`, `cybersecuritynews.com` and
`bleepingcomputer.com` are **all egress-blocked from the container**, so the figures came
from search summaries of those pages rather than from the pages themselves. The post
attributes every number in prose to LastPass and Delphos Labs and links both in the first
paragraph, which is the house rule for a piece built on somebody else's reporting and is
also what makes an unverified figure safe to print.

**Confirm these five in a browser before publishing.** They are consistent across several
independent summaries, which is not the same as having read the report:

1. **145** AV/EDR products on the kill list
2. **25+** browsers, **~30** wallets, plus Discord, Steam and Telegram session credentials,
   Windows Credential Manager and screenshots
3. **40** impersonated brands, campaign active since at least **13 August 2026**
4. `nvfsflt64.sys`, a renamed `CcProtect.sys`, signed via Windows Hardware Compatibility
   Publisher
5. Installer is a renamed `vsdbg.exe` with a sideloaded malicious `vsdbg.dll`; ZIPs inflated
   to **148 MB**

If any figure moved, edit the canonical FIRST and re-run `python3 build_blog.py`. A Medium
import is a snapshot and does not follow a later correction.

**THE CLAIM THIS POST DELIBERATELY DOES NOT MAKE:** that RelayShield would have stopped
this. It says the opposite, in its own voice, twice. We are not an EDR, and a post implying
we would have caught a signed kernel driver is one a reader disproves in a paragraph. Saying
the limit out loud is what makes the rest of it credible, exactly as the GitLab post did.

**No corpus figures anywhere**, per MEASUREMENT DOCTRINE, and the post says outright that we
do not quote one and why. That is a differentiator rather than an omission.

---

## 1. blog.relayshield.net -- CANONICAL

Already built. Merge and push; `deploy_blog.yml` fires on any change under `blog_markdown/**`.
Key: **`rapuncel-blog`** (in the post's own closing link).

**Verify the canonical is live before step 2.** Medium and dev.to both carry a canonical
pointing here, and a canonical that 404s hands the canonical position to the syndicated copy.

## 2. Medium

**Import with the canonical URL. Never paste** -- Medium has no Markdown paste, and an
import is a snapshot, so get the canonical right first.

Change the one API link to `?source=rapuncel-medium`.

**Tags (Medium allows 5):** `Cybersecurity`, `Infosec`, `Malware`, `Infostealer`,
`Cryptocurrency`

## 3. dev.to

```zsh
cd ~/dev/relayshield
python3 tools/publish_devto.py the-edr-was-dead-before-the-theft-started-devto.md --dry-run
```

then, with the key in the environment:

```zsh
cd ~/dev/relayshield
read -rs "DEVTO_API_KEY?Paste your dev.to API key, then press Enter: "
export DEVTO_API_KEY
python3 tools/publish_devto.py the-edr-was-dead-before-the-theft-started-devto.md --publish
```

Key at <https://dev.to/settings/extensions>, under "DEV Community API Keys".
EXPECT: a published URL.
STOP IF: `422` naming a tag -- that tag does not exist on DEV. Drop it and re-run.
STOP IF: `403` -- Cloudflare rejecting the client, not the key. A bad key gives `401`.

**Tags, four maximum and they must already exist:** `security`, `devops`, `opensource`.
Three rather than four on purpose: `malware` is not a confirmed DEV tag and a 422 costs a
round.

## 4. LinkedIn -- 3000 character limit

```text
Rapuncel does something worth more attention than it is getting.

Before it steals anything, it loads a kernel driver carrying a hardcoded list of 145 antivirus and EDR products, and kills them. The driver is signed through Microsoft's Windows Hardware Compatibility Publisher chain. It presents itself as an NVIDIA filter driver and is a renamed component of a commercial encryption product.

So the order is: disable the detection layer, then steal.

Almost every control most organisations own is a detection control, and all of them share one unexamined assumption: that they are running when the thing they detect happens. A kill list of 145 products is that assumption being attacked directly, with a signature Windows trusts. Once it fires, "did we detect it?" has a fixed answer, and it is no. Not because the product was bad. Because it was not running.

What Rapuncel then takes is the part that decides whether your response works. Per LastPass and Delphos Labs: credentials from more than 25 browsers, data from around 30 cryptocurrency wallets, session credentials for Discord, Steam and Telegram, Windows Credential Manager, and screenshots.

Read that list for what it is not. It is not mostly passwords.

A password reset invalidates a password. It does not invalidate a session. An attacker holding a live session cookie never logs in, so there is nothing for a new password to stop and no MFA prompt to satisfy, because the session already satisfied it. Rotating a key does not revoke a token. And a seed phrase is not something you rotate at all.

The delivery was ordinary: a search, a GitHub repository impersonating a real project, a download. At least 40 brands impersonated, since mid-August.

We are not an EDR and we would not have stopped this. Anyone telling you otherwise this week is selling you something. What we work on is the half that survives the endpoint going quiet: whether the material that left is now in circulation, and whether a live session was taken rather than a password.

If you take one thing from it: plan for the case where your detection did not fire, because that case is now a product feature of the malware. Revoke sessions before you rotate passwords. Treat a wallet as unrecoverable rather than rotatable.

Research by the LastPass TIME team and Delphos Labs, published 17 September. Full write-up and the two endpoints that answer the "what left" question:

https://blog.relayshield.net/the-edr-was-dead-before-the-theft-started

#CyberSecurity #InfoSec #ThreatIntelligence #Infostealer #EDR #IncidentResponse
```

Link: put `?source=rapuncel-linkedin` on the API link if you add one in a comment. **LinkedIn
demotes posts with outbound links in the body**, so the canonical link at the end is the only
one, and anything else goes in the first comment.

## 5. Telegram -- 4096 character limit, `t.me/RelayShield`

```text
⚠️ The EDR was dead before the theft started.

LastPass and Delphos Labs published research on an infostealer they call Rapuncel. One detail deserves more attention than it is getting.

Before it steals anything, it loads a kernel driver with a hardcoded list of 145 antivirus and EDR products, and kills them. The driver is signed through Microsoft's own hardware compatibility chain and poses as an NVIDIA filter driver.

Disable the detection layer, then steal.

Then it takes credentials from 25+ browsers, data from around 30 crypto wallets, session credentials for Discord, Steam and Telegram, Windows Credential Manager, and screenshots.

That list is mostly not passwords, and that is what decides your response:

• A password reset invalidates a password. It does not invalidate a session.
• An attacker with a live session cookie never logs in, so there is no MFA prompt to satisfy. The session already satisfied it.
• A seed phrase is not something you rotate.

It arrived the ordinary way: a search, a GitHub page impersonating a real project, a download. At least 40 brands impersonated since mid-August.

We are not an EDR and we would not have stopped this. What we do is the part that survives the endpoint going quiet: telling you what left, and whether a session was taken rather than a password.

Revoke sessions BEFORE you rotate passwords. In the bot that is /sweep.

Free, no account: paste a link or a wallet address into the checker, or forward a suspicious email to checkemail@relayshield.net

Full write-up:
https://blog.relayshield.net/the-edr-was-dead-before-the-theft-started?source=rapuncel-telegram
```

**Parse mode: HTML or plain.** Legacy Markdown has **no escape syntax**, so any value with an
underscore breaks it, and `/sweep` plus the URL are exactly that shape. Plain text is safest
here and loses nothing.

## 6. Farcaster -- roughly 1024 bytes

```text
Rapuncel loads a Microsoft-signed kernel driver that kills 145 AV and EDR products BEFORE it steals anything.

Then: 25+ browsers, ~30 crypto wallets, Discord/Steam/Telegram session credentials, Windows Credential Manager.

Mostly not passwords. Which matters, because a password reset invalidates a password and does NOT invalidate a session. A live cookie never logs in, so there is no MFA prompt to satisfy.

Every detection control assumes it is running when the thing happens. A 145-product kill list attacks that assumption directly.

We are not an EDR and would not have stopped this. We work on what survives the endpoint going quiet: what left, and whether a session was taken.

Revoke sessions before rotating passwords.

https://blog.relayshield.net/the-edr-was-dead-before-the-theft-started?source=rapuncel-farcaster
```

**Channels:** `/security`, `/crypto`. No hashtags; Farcaster uses channels instead and
hashtags read as noise there.

## 7. Mastodon -- 500 character limit

```text
Rapuncel kills 145 AV/EDR products with a Microsoft-signed kernel driver BEFORE stealing anything.

Then: 25+ browsers, ~30 wallets, Discord/Steam/Telegram sessions, Credential Manager.

Mostly not passwords. A reset invalidates a password, not a session.

Revoke sessions first, then rotate.

https://blog.relayshield.net/the-edr-was-dead-before-the-theft-started?source=rapuncel-mastodon

#infosec #malware
```

**Two hashtags, deliberately.** Mastodon's 500 characters include the URL, and its culture
treats hashtag stuffing as spam. `#infosec` and `#malware` are the two that actually carry
discovery there.

---

## Hashtags and tags, collected

| Channel | Tags / hashtags | Limit |
|---|---|---|
| Medium | `Cybersecurity` `Infosec` `Malware` `Infostealer` `Cryptocurrency` | 5 |
| dev.to | `security` `devops` `opensource` | 4, must already exist |
| LinkedIn | `#CyberSecurity` `#InfoSec` `#ThreatIntelligence` `#Infostealer` `#EDR` `#IncidentResponse` | no hard cap, 6 is the practical ceiling |
| Telegram | none | a channel post does not need them |
| Farcaster | channels `/security` `/crypto`, no hashtags | ~1024 bytes |
| Mastodon | `#infosec` `#malware` | 500 chars including the URL |

---

## The attribution keys, all registered before this ships

    rapuncel            the banner all seven render
    rapuncel-blog       canonical
    rapuncel-medium     Medium
    rapuncel-devto      dev.to
    rapuncel-linkedin   LinkedIn
    rapuncel-telegram   Telegram channel
    rapuncel-farcaster  Farcaster
    rapuncel-mastodon   Mastodon

Count arrivals per channel with:

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/source_arrivals.py --days 30 --key rapuncel-linkedin

**The `?source=` goes on `/developers`, never on the bare host.** `?source=` on the root is
read by nothing, which is FD-8's exact shape. The post's own closing link already has it
right.
