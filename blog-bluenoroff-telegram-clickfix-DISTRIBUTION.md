# Distribution: "Sender Recognition Is Not Authentication"

**Post file:** `blog-bluenoroff-telegram-clickfix.md`
**Status:** **PUBLISHED 2026-08-11.** Canonical is the self-hosted blog.
**Slug:** `sender-recognition-is-not-authentication`
**Live URL:** https://blog.relayshield.net/sender-recognition-is-not-authentication

Verified live after deploy, by content and not by status code: the page renders the full body,
`rel="canonical"` points at the clean URL so the `?source=` variants will not split it, the post is
item 1 in `rss.xml`, the card is on the index, it is in `sitemap.xml`, and both cut passages are
absent from the served HTML. A `?source=` URL 404'd once in the first seconds after deploy and has
served 200 with identical bytes on every check since; treat a single post-deploy 404 as propagation,
but recheck rather than assume.

**Note for the social copy below:** the post no longer contains the explicit "we did not detect this
campaign, JUMPSEC did" sentence, cut at the founder's direction. That line is still in the LinkedIn,
Telegram and Reddit blocks, and it should stay there, because the post can no longer carry the
disclaimer on its own.

Every block below is ready to paste. Character counts are **measured**, not estimated, and each is
checked against that platform's real limit.

---

## Gates to clear before publishing

**1. The coverage claim CHANGED on 2026-08-10 and the copy below reflects the new position.**
The corpus originally had zero APT38 attribution. It now carries JUMPSEC's published campaign
infrastructure, ingested by `tools/ingest_apt38_jumpsec.py` and verified live:

| Tag | Before | After |
|---|---|---|
| `apt38` (60 domains, 10 IPs, 13 sha256) | 0 | **83** |
| `ClickFix` | 271 rows, 13 unique domains | 273 rows, still 13 unique |

Re-verified live on 2026-08-11 against the `malware-index` GSI, immediately before publication:
`malware=apt38` returns **83** rows, split 60 domain / 10 ip / 13 sha256, 83 distinct `ioc_value`s,
confidence split 44 high / 39 medium, and **every row carries a `reference`**. `threat_actor` is
`APT38` on all 83. `lazarus`, `nukesped`, `bluenoroff` and `unc1069` all still return 0, so the
post's "we ingested a researcher's attribution, we did not have our own" framing holds exactly.

Verified end to end, not just written: `/v1/metered/asset-intel` returns a populated match with the
JUMPSEC citation for `callsdk.online` and `144.172.110.53`, a control asset comes back clean, and
`/v1/metered/threat-actor` actor-lookup resolves APT38, BlueNoroff, Bluenoroff, Sapphire Sleet and
BeagleBoyz to 26 IOCs while a nonsense actor name returns `found: false`.

**The line that must not be crossed:** we ingested a researcher's published attribution, we did not
discover this campaign. The post says so in those words. Do not let any social copy drift into
"RelayShield detects BlueNoroff." This audience checks, and the honest version is the one that gets
linked.

**2. Say "a small set", not a number, for the ClickFix domains.** The GSI now returns **273** rows
but still only **13 distinct `ioc_value`s**. The table is keyed `(ioc_value, seen_ts)`, so repeat
observations create repeat rows, and two more landed overnight. "273 ClickFix indicators" would be a
real overstatement. Most recent observation is `2026-08-11T06:00:36Z`, this morning, so
"observations landing on the day this was written" is accurate as written.

**3. Do not publish the ClickFix domain list.** **Three** of the 13 are hosting platforms rather
than threats: `sites.google.com`, `raw.githubusercontent.com` and `buyaneli876-oss.github.io`.
Publishing that list would be a self-inflicted false-positive story on a blog whose credibility
rests on the opposite. See the separate open item about those rows.

**4. No em-dashes, no en-dashes, no ` -- ` substitute** anywhere, including social copy. Audited
clean in the post and in every block below.

---

## Positioning

**Lead with "sender recognition is not authentication."** That is the durable, teachable line. It
survives this campaign, applies to the next one, and is the sentence a reader can repeat to their
own team on Monday.

**Do not lead with "North Korea."** It is the highest-volume framing and therefore the lowest
differentiation. Every outlet already ran that headline on 7 August. The loop, the pre-malware
browser fingerprinting, and the correction are what nobody else is leading with.

**Do not lead with the actor names.** BlueNoroff, UNC1069 and APT38 are three labels with different
evidentiary weight. Using them as a headline invites the exact detection question we answer "no" to.

**The correction is the trust play.** Saying publicly that opening the link does not drain your
wallet, against our own commercial interest, is the most linkable thing in the post.

**Secondary hook for the crypto-native channels:** the wallet fingerprinting happens in the browser,
before any malware, using ordinary web APIs. Being selected happens before being attacked.

---

## Channel status, checked before writing this

| Channel | Status | Limit | Link goes |
|---|---|---|---|
| LinkedIn | active, best historical performer | 3,000 chars | **first comment**, never the body |
| Telegram | active | 4,096 chars | inline |
| Mastodon | active | **500 chars**, URLs count as 23 | inline |
| Farcaster | active | **~1,024 bytes**, byte-counted | inline |
| Medium | active | none | canonical set **by hand** |
| Reddit r/netsec, r/cybersecurity | no account history | none | inline, but see warning |
| **X / Twitter** | **SUSPENDED since 2026-07-02**, appeal denied | n/a | **do not plan around it** |
| **Hashnode** | abandoned, AutoMod archived a post 3 times, appeal unresolved | n/a | **do not use** |

---

## 1. LinkedIn: post first, it is the strongest channel

Link in the **first comment**. A link in the body suppresses reach.

**Body, measured 2,729 / 3,000 characters:**

```
Most social engineering has a tell. A domain one character off. A sender you have never heard from. A tone that does not match the person it claims to be.

The DPRK linked campaign JUMPSEC pulled apart in July has none of those. The message really does come from someone you know, from their real account, referencing a relationship that really exists.

Read the chain in the order it runs and a loop appears.

1. A compromised Telegram account belonging to a real industry contact sends a meeting invitation.
2. The target joins a fake Zoom or Teams call. An operator appears on video with no audio.
3. A staged audio fault leads to a fake SDK update prompt with troubleshooting text to copy.
4. Copying that text does not copy that text. The clipboard is replaced with an attacker command.
5. Running the command installs an implant.
6. The implant checks for Telegram Web or Telegram Desktop, and steals that session.
7. That stolen session sends the next round of invitations.

Step 7 feeds step 1.

Every compromise does not just produce a victim. It produces delivery infrastructure, and that infrastructure is a real person's trusted identity inside a community where everyone already talks to everyone.

There is no exploit anywhere in that list. No zero day. The only technically interesting component is a clipboard swap, which has been a solved trick for twenty years.

Two things I think are underrated here.

First, the reconnaissance happens before any malware, in the browser. The fake meeting page fingerprints wallet extensions using EIP-6963 discovery and legacy probes, across roughly ten browser variants, then operators decide whether you are worth a payload. Being interesting is a state you enter before you are attacked.

Second, the defensive habit most people have built is "read before you run." Reading is exactly what fails here. What you read and what lands in your clipboard are different strings.

One correction, against our own commercial interest. The version circulating says opening the link drains your wallet. In the documented chains it does not. Compromise needs a second act: running the pasted command. That distinction matters, because "do not click anything" is advice nobody can follow, while "never paste a command you did not compose" is a rule a person can actually hold, and it breaks the entire chain.

The control that works is not spotting a fake sender. There is no fake sender. It is verifying the meeting out of band, on a channel the attacker does not already own.

Write-up in the comments.

If your team got a meeting invite from a known contact today, what in your process would have caught this?

#CyberSecurity #ThreatIntel #SocialEngineering #InfoSec #CryptoSecurity
```

**First comment:**

```
Full write-up, including what actually helps at each stage: https://blog.relayshield.net/sender-recognition-is-not-authentication?source=bluenoroff-linkedin
```

**Hashtags** (LinkedIn rewards 3 to 5, not 30; they are already at the end of the body above):

```
#CyberSecurity #ThreatIntel #SocialEngineering #InfoSec #CryptoSecurity
```

**Why the closing question:** prior engagement on this account came from comments, not from the
body. "What in your process would have caught this" is uncomfortable to answer honestly, which is
what makes people reply. It also surfaces prospects: anyone who answers "nothing" has just
self-qualified.

---

## 2. Telegram: intel note, not marketing

**Measured 1,694 / 4,096 characters.** Telegram has no rich-text paste, so use
`LC_CTYPE=UTF-8 pbcopy < file` and verify with `pbpaste | diff`.

There is an obvious irony in publishing a Telegram-account-compromise advisory to a Telegram
channel. Lean into it rather than around it: this is the audience with the exposure.

```
Sender recognition is not authentication.

The DPRK linked campaign JUMPSEC documented in July runs a loop rather than a funnel:

A compromised Telegram account belonging to a real industry contact sends a meeting invite. The target joins a fake Zoom or Teams call. A staged audio fault produces a fake SDK update prompt with troubleshooting text to copy. Copying it does not copy it, the clipboard is swapped for an attacker command. Running it installs an implant. The implant checks for Telegram Web or Telegram Desktop and steals that session. That session sends the next round of invites.

The last step feeds the first. Each compromise produces delivery infrastructure, not just a victim.

Two underrated details:

The fingerprinting happens before any malware, in the browser. The meeting page enumerates wallet extensions via EIP-6963 discovery and legacy probes across about ten browser variants, and operators triage on the result. You are selected before anything runs.

The clipboard swap defeats "read before you run." What is on screen and what is in your buffer are different strings.

Correction worth making: opening the link does not drain a wallet. The documented chains need a second act by the victim. That matters, because it turns the advice from "do not click anything" into "never paste a command you did not compose."

We did not detect this campaign, JUMPSEC did. What we have done is ingest the infrastructure they published, 60 domains and 10 IPs, with their confidence split and the citation kept on every record. If any of it turns up in your DNS logs, you get a hit and a source you can go and read.

One practical thing, since this is the audience with the exposure. @relayshield_bot now checks a link or a wallet address inline, in whatever chat the message landed in. Type @relayshield_bot followed by the link and the result posts where everyone reading the thread can see it, with no install by that group. For a suspicious email or text, DM the bot and use /scan.

It will not tell you something is safe. A brand new phishing domain is in no database yet, and the result says so.

Full write-up:
https://blog.relayshield.net/sender-recognition-is-not-authentication?source=bluenoroff-telegram
```

---

## 3. Mastodon: 500 char limit, URLs count as 23

**Measured 375 / 500** with the URL counted as 23. Do not add to this without re-counting.

```
Sender recognition is not authentication.

A DPRK linked campaign hijacks real Telegram accounts, lures contacts to fake Zoom calls, and swaps the clipboard so "copy this fix" pastes an attacker command.

The implant then steals the victim's Telegram session and sends the next round of invites.

The last step feeds the first.

https://blog.relayshield.net/sender-recognition-is-not-authentication?source=bluenoroff-mastodon

#infosec #threatintel
```

**Hashtags:** Mastodon leans on hashtags for discovery far more than the other networks, but two
strong ones beat six weak ones. `#infosec` and `#threatintel` are the active tags in this community.
There is headroom for a third at 375 characters; `#dprk` is the most on-topic option, and
`#opsec` reaches a slightly different room.

---

## 4. Farcaster: ~1,024 BYTES, not characters

**Measured 766 bytes.** Byte-counted, so any non-ASCII costs more than one character. This copy is
deliberately all-ASCII.

Lead with the wallet fingerprinting. This is a crypto-native audience and the enterprise framing
lands flat there.

```
The fake meeting page fingerprints your wallets before any malware exists.

EIP-6963 discovery, legacy window.ethereum probing, non EVM globals, plus extension IDs across about ten browser variants. Ordinary web APIs, on a page you opened yourself. Operators read the result and decide whether you are worth a payload.

Then the clipboard trick: the troubleshooting text on screen is not the text that lands in your buffer.

Then the implant looks for Telegram Web or Telegram Desktop and takes that session, which sends the next round of invites to your contacts.

Opening the link does not drain you. Pasting the command does. That distinction is the whole defense.

https://blog.relayshield.net/sender-recognition-is-not-authentication?source=bluenoroff-farcaster
```

**Channels to cast into:** `/security`, `/crypto`, `/dev`. No hashtags; Farcaster does not use them
the way Mastodon does.

---

## 5. Medium: paste, do not import

Three import attempts have been mangled previously, so the working method is a rich-HTML clipboard
paste:

```bash
osascript -e "set the clipboard to «data HTML$(hexdump -ve '1/1 "%.2x"' post.html)»"
```

Then **Cmd+V** in the Medium editor (Cmd+Shift+V is Hashnode's requirement, not Medium's).

**Then set the canonical link by hand.** Medium will not do it for a pasted story:
Story settings, then Advanced settings, then Canonical link, set to
`https://blog.relayshield.net/sender-recognition-is-not-authentication`

Without it the Medium copy competes with your own blog in search.

**Medium tags** (5 max; Medium tags are topic-matched, not hashtags):

```
Cybersecurity, Threat Intelligence, Social Engineering, Cryptocurrency, Infosec
```

**Subtitle:**

```
The contact list is not the target. It is the supply chain.
```

---

## 6. Reddit: highest risk, highest ceiling

r/netsec and r/cybersecurity both reach exactly this audience, and both will remove a first post
from an account with no comment history. **Do not post cold.** If you want this channel, spend a
week commenting on other threads first. This has been true in every distribution plan so far and has
not been actioned; either invest the week or stop listing it.

r/netsec wants the technical framing with no product mention at all.

**Title:**

```
The DPRK ClickFix campaign is a loop, not a funnel: stolen Telegram sessions are the delivery channel for the next round
```

Link straight to the post with `?source=bluenoroff-reddit`. Answer questions technically or not at
all.

Also viable and lower risk: **r/CryptoCurrency** and **r/ethdev** for the wallet-fingerprinting
angle, where the pre-malware EIP-6963 sweep is genuinely news to most readers.

---

## 7. Tags and keywords worth carrying into any copy written by hand

**Primary:** ClickFix, BlueNoroff, UNC1069, Telegram account takeover, fake Zoom meeting, clipboard
hijacking, social engineering, DPRK, crypto security.

**Secondary:** session hijacking, EIP-6963, wallet fingerprinting, NukeSped, APT38, infostealer,
Telegram session theft, out-of-band verification, deepfake meeting.

**Tie-in to already-published work:** session hijacking and machine credentials (the session-hijack
post), macOS ClickFix infostealer (`blog-macos-clickfix-infostealer.md`, which is the direct
predecessor and should be linked from this one), and Lazarus/Polymarket
(`blog-polymarket-lazarus-relayshield.md`) for the DPRK thread.

**Internal linking is worth more than any of the tags above.** Three existing posts cover adjacent
ground and none of them link to each other. This post is the natural hub.

---

## Attribution

Six `?source=` keys need **registering before publication**, or they log as `unmatched:` and render
no banner:

```
bluenoroff-telegram, bluenoroff-linkedin, bluenoroff-mastodon,
bluenoroff-farcaster, bluenoroff-medium, bluenoroff-reddit
```

Verify by loading one live URL and confirming the banner renders, then load a deliberately bogus key
and confirm it renders nothing. That second check is what makes the first one meaningful.

Arrivals by channel:

```
fields @timestamp | filter @message like /developer-signup request/
| parse @message "source=*" as src | filter src like /bluenoroff/
| stats count() by src | sort by count() desc
```

---

## Sequencing

1. **LinkedIn first.** Strongest channel, and the comment thread benefits from a head start.
2. **Telegram and Mastodon** same day, either order.
3. **Farcaster** same day.
4. **Medium** next day, so the canonical has time to be indexed first.
5. **Reddit** only if the comment history gets built first.

**Timeliness note:** the source reporting is dated 7 August and the JUMPSEC research is from July.
This is already a week behind the news cycle, which is fine for the angle chosen, since the post
competes on analysis rather than on being first. Do not stretch it another week.
