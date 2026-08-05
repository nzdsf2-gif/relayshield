# Distribution: "The Malware Stopped Stealing Passwords. It Started Stealing You."

**Post is LIVE:** https://blog.relayshield.net/the-malware-stopped-stealing-passwords-it-started-stealing-you
**Published:** 2026-08-04. Canonical is the self-hosted blog, not Hashnode.

Every block below is ready to paste. Character counts are measured, not estimated, and each is
checked against that platform's real limit.

---

## The rule that governs all of this copy

**Do not claim RelayShield detects MedusaHVNC or Dolphin X.** Re-verified live 2026-08-04 against
the `malware-index` GSI, all four name variants: **0 IOCs each**. The names are in the detection
table, so a future mention gets tagged, but nothing has been tagged yet. "We have a regex for it"
is not detection, and this audience will check.

What the copy claims instead is the layer underneath, which is real: stolen **session cookies** and
**machine credentials** surfacing in criminal archives. That is what `session-risk` and
`nhi-exposure` actually return.

Second rule: **no em-dashes, no en-dashes, and no ` -- ` double-hyphen substitute** anywhere,
including in social copy. Only hyphens inside compound technical terms stay.

---

## Positioning

Lead with **"MFA worked, so attackers stopped attacking it."** That is the durable hook.

Do **not** lead with the malware names. "MedusaHVNC" and "Dolphin X" are unknown brands to almost
everyone and will not carry a click on their own. They are the evidence, not the headline.

Secondary hook, for the developer and AI audience: **cloud tokens now include LLM keys**, which
ties straight back to the LLMjacking post already published.

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
| Hashnode | abandoned, silently unpublished a post twice | n/a | **do not use** |

---

## 1. LinkedIn: post first, it is the strongest channel

Link in the **first comment**. A link in the body suppresses reach.

**Body, 1,847 / 3,000 characters:**

```
The industry spent a decade telling everyone to turn on MFA. It worked.

That is exactly why attackers stopped attacking it.

A stolen password on its own is now a low-value commodity. So the economics moved to the thing that sits after the login: the session cookie. A cookie issued after a successful MFA challenge is, to the application, proof that the challenge already happened. Steal it, and there is nothing left to challenge.

Two malware families surfacing in criminal channels show the same shift from opposite directions.

The first runs a real browser on an invisible desktop on the victim's own machine. Not a spoofed window. Not a screenshot replay. A genuine session, on the real device.

Think about which controls that defeats:

- Impossible-travel detection: the session comes from the victim's real IP, in their real city.
- Device fingerprinting: it is the real device, real browser build, real fonts.
- Behavioural risk scoring: it is a genuine continuation of a legitimate login.
- Cookie-theft detection: the cookie never leaves the machine, so nothing is in transit to catch.

Most fraud controls are tests of where a session came from. This answers every one of them honestly.

The second inverts the usual stealer logic. Instead of grabbing everything and selling it by the gigabyte, it profiles the victim first, then decides what to take. A developer workstation becomes an SSH key and cloud token target. A finance workstation becomes a session cookie target.

Breadth without triage produces noise. Breadth with triage produces a target list.

Here is the part I think defenders underestimate most.

When a stealer takes a cloud token or an SSH key, the damage does not stop at one user's account. Those credentials are long-lived, broadly scoped, not covered by MFA because there is no human to challenge, and not tied to any employee lifecycle. Offboarding a person does not revoke the key they created.

A stolen password is a door. A stolen cloud token is often the building.

And "cloud tokens" now routinely includes LLM provider API keys, which are a live uncapped billing liability from the moment they leak.

If your credential exposure programme covers only human accounts and only passwords, it is scoped to the previous generation of this threat.

Full write-up in the comments.

What is your organisation's actual rotation interval on machine credentials? Not the policy. The real one.
```

**First comment:**

```
Full analysis, including what actually helps at each stage: https://blog.relayshield.net/the-malware-stopped-stealing-passwords-it-started-stealing-you?source=session-hijack-linkedin
```

**Hashtags** (LinkedIn rewards 3 to 5, not 30; put them at the end of the body):

```
#CyberSecurity #IdentitySecurity #MFA #InfoSec #CISO
```

**Why the closing question:** prior LinkedIn engagement on this account came from comments, not
from the post body. Machine-credential rotation interval is a question practitioners have an
uncomfortable answer to, which is what makes people reply.

---

## 2. Telegram: intel note, not marketing

**1,193 / 4,096 characters.** Telegram has no rich-text paste, so use
`LC_CTYPE=UTF-8 pbcopy < file` and verify with `pbpaste | diff`.

```
Session hijacking has quietly become the main event.

Two families in criminal channels this month, same underlying shift:

One runs a legitimate browser on an invisible desktop on the victim's own machine. Real device, real IP, real browser fingerprint. Impossible-travel detection, device fingerprinting and behavioural scoring all pass, because every one of them is a test of where the session came from, and the honest answer is "the victim's laptop."

The other profiles the victim with AI before deciding what to steal, then targets browser passwords, crypto wallets, SSH keys and cloud tokens across 300+ applications. Selection logic on top of breadth turns a dump into a target list.

The common thread: the password is the delivery mechanism. The session cookie and the machine credential are the payload.

Machine credentials are the underrated half. Long-lived, broadly scoped, no MFA because there is no human to challenge, and not revoked when the person who made them leaves.

We are not claiming detection of either family. What we do monitor is the output: stolen session cookies and machine credentials appearing in criminal archives.

Full write-up:
https://blog.relayshield.net/the-malware-stopped-stealing-passwords-it-started-stealing-you?source=session-hijack-telegram
```

---

## 3. Mastodon: 500 char limit, URLs count as 23

**Measured 476 / 500** with the URL counted as 23. Do not add to this without re-counting.

```
MFA worked, so attackers stopped attacking it.

Two stealer families this month, same shift: don't beat the login, occupy the session after it.

One drives a real browser on an invisible desktop on the victim's own machine. Impossible-travel, device fingerprinting, behavioural scoring all pass honestly.

Password = delivery mechanism. Session cookie and cloud token = payload.

https://blog.relayshield.net/the-malware-stopped-stealing-passwords-it-started-stealing-you?source=session-hijack-mastodon

#infosec #threatintel
```

**Hashtags:** Mastodon relies on hashtags for discovery far more than the other networks, but two
strong ones beat six weak ones. `#infosec` and `#threatintel` are the active ones in this
community. Consider `#cybersecurity` as a third if you want reach over precision.

---

## 4. Farcaster: ~1,024 BYTES, not characters

**Measured 892 bytes.** Byte-counted, so any non-ASCII costs more than one. This copy is
deliberately all-ASCII.

Lead with the wallet and seed-phrase angle. This is a crypto-native audience and the enterprise
framing lands flat there.

```
One of these stealer families profiles the victim with AI before deciding what to take.

Land on a crypto holder's machine and it goes for wallets and seed phrases. Land on a developer's and it goes for SSH keys and cloud tokens.

The other one is worse in a quieter way: it drives a real browser on an invisible desktop on your actual machine. Real device, real IP, real fingerprint. Every "is this session suspicious" check passes, because every one of them is a test of where the session came from.

Your seed phrase was never the only thing worth taking. The authenticated session was.

https://blog.relayshield.net/the-malware-stopped-stealing-passwords-it-started-stealing-you?source=session-hijack-farcaster
```

**Channels to cast into:** `/security`, `/dev`. No hashtags, Farcaster does not use them the way
Mastodon does.

---

## 5. Medium: paste, do not import

**Cover image:** `relayshield_session_hijack_cover.png` (1600x840, house palette, matches the
secret-scanning post's cover). Medium crops the feature image to roughly 2:1, so the headline and
the stat row both survive. Set it as the story's feature image, and Medium will also use it as the
social preview card.

Three import attempts were mangled previously, so the working method is a rich-HTML clipboard
paste:

```bash
osascript -e "set the clipboard to «data HTML$(hexdump -ve '1/1 "%.2x"' post.html)»"
```

Then **Cmd+V** in the Medium editor (not Cmd+Shift+V, that is Hashnode's requirement).

**Then set the canonical link by hand.** Medium will not do it for a pasted story:
Story settings → Advanced settings → Canonical link →
`https://blog.relayshield.net/the-malware-stopped-stealing-passwords-it-started-stealing-you`

Without it, the Medium copy competes with your own blog in search results.

**Medium tags** (5 max, and Medium's tags are topic-matched, not hashtags):

```
Cybersecurity, Infosec, Security, Identity, Malware
```

**Subtitle:**

```
MFA worked. So attackers stopped attacking it.
```

---

## 6. Reddit: highest risk, highest ceiling

r/netsec and r/cybersecurity both reach exactly this audience, and both will remove a first post
from an account with no comment history. **Do not post cold.** If you want this channel, spend a
week commenting on other threads first.

If you do post, r/netsec wants the technical framing with no product mention at all:

**Title:**

```
Two stealer families showing the same shift: from stealing credentials to occupying authenticated sessions
```

Link straight to the post with `?source=session-hijack-reddit`. Do not add commentary that reads
as marketing. Answer questions in the comments technically or not at all.

---

## Attribution

All seven `?source=` keys are **registered and verified rendering live** as of 2026-08-04:
`session-hijack`, and `-linkedin`, `-telegram`, `-mastodon`, `-farcaster`, `-medium`, `-reddit`.
A bogus key was confirmed to render no banner, so the check is real.

This matters because an unregistered key logs as `unmatched:` and renders nothing. The CloudWatch
source report currently shows live `unmatched:circleci`, `unmatched:rsscan`, `unmatched:docker` and
`unmatched:dockerhub` entries, which is what that failure looks like in the wild.

Arrivals by channel:

```
fields @timestamp | filter @message like /developer-signup request/
| parse @message "source=*" as src | filter src like /session-hijack/
| stats count() by src | sort by count() desc
```

---

## Sequencing

1. **LinkedIn first.** Strongest channel, and its comment thread benefits from a head start.
2. **Telegram and Mastodon** same day, any order.
3. **Farcaster** same day.
4. **Medium** next day, so the canonical has time to be indexed first.
5. **Reddit** only if you are willing to build comment history first.

**Do not post all of these within an hour of each other.** The last post went out 2026-08-03 and
this one on 2026-08-04, which is already tight for the same audience. Spacing the syndication over
two days softens that.

## Keywords worth carrying into any copy you write yourself

Primary: session hijacking, session cookie theft, MFA bypass, stolen session, infostealer.
Secondary: HVNC, non-human identity, machine credentials, cloud token, credential exposure,
stealer logs, AiTM.
Tie-in: LLMjacking, LLM API key exposure.
