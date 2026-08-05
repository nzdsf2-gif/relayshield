# The Malware Stopped Stealing Passwords. It Started Stealing You.

**PUBLISHED 2026-08-04.**
**Live:** https://blog.relayshield.net/the-malware-stopped-stealing-passwords-it-started-stealing-you
**Rendered copy:** `hashnode_export/the-malware-stopped-stealing-passwords-it-started-stealing-you.md`
(that file is what `build_blog.py` reads; this file is the working draft plus the channel plan).

**Figures verified live 2026-08-04 before publishing:** IOC corpus **4,965,358** (copy: `4.9M+`,
was 4,530,716 on 07-28) and **85 active** Telegram channels (copy: `85+`; the raw table holds 313
rows, which is the wrong denominator). The malware-family count was **dropped, not quoted** -
Malpedia was unreachable and an unverifiable figure does not go in a measurement post.

**Also applied at publish:** 21 em-dashes removed to house style, individually rather than by
find-replace, so the prose still scans.

---

Two families surfacing in criminal channels this month tell the same story from different angles:
credential theft has stopped being the goal. It has become the setup.

**MedusaHVNC** runs a legitimate browser on an invisible Windows desktop. Not a spoofed window,
not a screenshot-and-replay — a real browser session, on the victim's real machine, inside a
hidden desktop the user never sees.

**Dolphin X** profiles its victims using AI, then targets browser passwords, cryptocurrency
wallets, SSH keys, and cloud tokens across more than 300 applications.

Neither is interesting because it steals passwords. Both are interesting because of what they do
with what surrounds a password.

## Why "just steal the password" stopped working

The industry spent a decade telling people to turn on MFA, and it worked. A stolen password on
its own is now a low-value commodity. So the economics moved.

What defeats MFA is not a better password guess. It is **already being inside the authenticated
session**. A session cookie issued *after* a successful MFA challenge is, to the application, proof
that the challenge already happened. Steal that, and there is nothing left to challenge.

This is the shift both families represent, from opposite directions.

### MedusaHVNC: don't steal the session, occupy it

HVNC — Hidden Virtual Network Computing — is not new as a technique, but its use here is
instructive. Rather than exfiltrating a cookie and replaying it from attacker infrastructure, the
operator drives a browser **on the victim's own machine**, in a desktop the victim cannot see.

Consider what that defeats:

- **Impossible-travel detection** — the session originates from the victim's real IP, in their
  real city.
- **Device fingerprinting** — it is the real device, real browser build, real fonts, real canvas
  hash.
- **Behavioural risk scoring** — the session is a genuine continuation of a legitimate login.
- **Cookie-theft detection** — the cookie never leaves the machine, so there is nothing in transit
  to catch.

The fraud controls most organisations rely on are largely tests of *where a session came from*.
HVNC answers every one of those tests honestly.

### Dolphin X: profile first, harvest second

Dolphin X inverts the usual stealer logic. Traditional infostealers are indiscriminate: grab
everything, dump it to a channel, let a buyer sort through it later. That is why stealer logs are
sold by the gigabyte.

Reported AI-driven victim profiling changes the unit economics. If the malware can work out
*whose* machine it is on before deciding what to take, then:

- A developer workstation becomes an **SSH key and cloud token** target.
- A finance workstation becomes a **session cookie and banking portal** target.
- A crypto holder becomes a **wallet and seed phrase** target.

The 300+ application coverage matters less than the selection logic sitting on top of it. Breadth
without triage produces noise. Breadth *with* triage produces a target list.

And the categories named — browser passwords, crypto wallets, SSH keys, cloud tokens — are not a
random spread. They are the four things that most reliably convert into either money or deeper
access.

## The part defenders keep underestimating: non-human credentials

Both families converge on something worth stating plainly.

When a stealer takes an SSH key or a cloud token, the damage does not stop at one user's account.
Those credentials are frequently:

- **long-lived** — rotated on a schedule measured in months, if at all
- **broadly scoped** — provisioned once, for convenience, with far more access than the task needed
- **not covered by MFA** — a machine credential has no human to challenge
- **not tied to an employee lifecycle** — offboarding a person does not revoke the key they created

A stolen password is a door. A stolen cloud token is often the building.

This is also where the LLMjacking overlap sits. "Cloud tokens" now routinely includes LLM provider
API keys, and those carry an unusual property: they are a live, uncapped billing liability from the
moment they leak. Published incidents range from tens of thousands of dollars per day up to a
$500K single-month bill from one unthrottled key. An attacker profiling a developer machine for
cloud credentials is, incidentally, profiling it for LLM keys.

## What actually helps

Being honest about which controls address which problem:

**Against session hijacking specifically**
- **Phishing-resistant MFA (FIDO2/passkeys)** — the strongest single control, because the
  credential is bound to the origin and cannot be replayed.
- **Short session lifetimes and token binding** — reduces the window a stolen cookie is worth
  anything.
- **Re-authentication on sensitive actions** — a hijacked session should not be able to change
  payment details or add an OAuth grant unchallenged.

**Against the profiling/harvest stage**
- **Short-lived, narrowly-scoped machine credentials** — this is the single highest-leverage change
  for the SSH-key and cloud-token category, and the one most often deferred.
- **Credential inventory that includes non-human identities** — you cannot rotate what you do not
  know exists.
- **Egress monitoring on developer workstations** — where the highest-value credentials live.

**What monitoring adds**
None of the above tells you whether it has *already happened*. That is the gap exposure monitoring
fills: watching criminal channels and stealer-log archives for your organisation's credentials,
session cookies, and machine tokens appearing for sale — so rotation is triggered by evidence
rather than by schedule.

To be clear about the boundary: monitoring is a detection control, not a preventive one. It does
not stop MedusaHVNC running on a laptop. It shortens the interval between compromise and response,
which for a long-lived cloud token is often the difference that matters.

## What to take from this

The useful signal in these two families is not their specific implementations, which will be
obsolete within a year. It is the direction:

1. **Attackers are optimising for legitimacy, not stealth.** MedusaHVNC does not evade device
   trust — it inherits it.
2. **Attackers are optimising for relevance, not volume.** Dolphin X's profiling is an efficiency
   play, and efficiency plays are the ones that get copied.
3. **Machine credentials are the payload.** Passwords are the delivery mechanism.

If your credential-exposure programme covers only human accounts and only passwords, it is scoped
to the previous generation of this threat.

---

*RelayShield monitors 85+ criminal Telegram marketplaces and stealer-log archives for exposed
credentials, session cookies, and non-human identity secrets including cloud and LLM provider API
keys. 4.9M+ indicators, collected continuously.*

---
---

# Channel distribution strategy

**Moved.** Ready-to-paste copy for every channel, each measured against that platform's real
limit, lives in **`blog-session-hijack-DISTRIBUTION.md`**.

The plan that used to sit here was written on 2026-07-28 and had gone stale in three ways:

1. It named **Hashnode as canonical**. The blog is self-hosted now; Hashnode is abandoned and has
   twice silently unpublished a post. Canonical is `blog.relayshield.net`.
2. It told you to publish to Medium via **"Import a story"**. After three mangled imports the
   founder abandoned import entirely - the working method is a rich-HTML clipboard paste, and the
   canonical link must then be set by hand under Advanced settings.
3. It gated publishing on **"the AWS Bundle D visibility decision"**, which resolved on 2026-07-30
   (Bundle D is public and approved).

**The one thing from it that still stands, and matters most:**

> **Do not claim RelayShield detects MedusaHVNC or Dolphin X.**

Re-verified live 2026-08-04 against the `malware-index` GSI, all four name variants
(`dolphinx`, `medusahvnc`, `dolphin x`, `medusa hvnc`): **0 IOCs each**. Both names are in the
detection table in `relayshield_intel_monitor.py`, so a future mention would be tagged - but
nothing has been tagged yet, and "we have a regex for it" is not detection. Claiming coverage we
do not have is the fastest way to lose exactly this audience.

What we *can* claim, and what the copy leads with, is the layer underneath: stolen session cookies
and machine credentials appearing in criminal archives, which `session-risk` and `nhi-exposure`
genuinely do return.
