---
title: "The EDR was dead before the theft started"
slug: the-edr-was-dead-before-the-theft-started
date: 2026-09-21
---

# The EDR was dead before the theft started

On 17 September 2026, LastPass's Threat Intelligence, Mitigation and Escalation team
published joint research with Delphos Labs on an infostealer they track as **Rapuncel**.
Everything factual below comes from
[their report](https://blog.lastpass.com/posts/lastpass-delphos-report-rapuncel-infostealer)
and from [BleepingComputer's write-up of it](https://www.bleepingcomputer.com/news/security/fake-lastpass-authenticator-github-repos-push-new-rapuncel-infostealer/).
We did not find this campaign and we are not claiming to have.

One detail in it is worth more attention than it is getting.

Before Rapuncel steals anything, it loads a kernel driver that carries a hardcoded list of
**145 antivirus and EDR products**, and terminates them. The driver is signed through
Microsoft's Windows Hardware Compatibility Publisher chain. It ships as `nvfsflt64.sys`,
presenting itself as an NVIDIA file system filter; researchers identified it as a renamed
`CcProtect.sys` from a commercial encryption product.

So the order of operations is: disable the detection layer, then steal.

## What that order means

Almost every control most organisations own is a detection control. It observes, it
correlates, it alerts. All of them share one unexamined assumption: **that they are
running when the thing they detect happens.**

A kill list of 145 products is that assumption being attacked directly and at scale. It is
not evasion in the usual sense, where malware tries to look boring enough to slip past. It
is the security stack being switched off first, with a signature Windows trusts.

And once it is off, the question "did we detect it?" has a fixed answer, and the answer is
no. Not because the product was bad. Because it was not running.

What is left is the only signal that survives the endpoint: **the stolen material turning
up somewhere else.**

## What Rapuncel takes, and why the list matters

Per the same research, once the protections are down the stealer collects credentials from
**more than 25 browsers**, data from **around 30 cryptocurrency wallets**, session
credentials for Discord, Steam and Telegram, the contents of Windows Credential Manager,
and screenshots.

Read that list again for what it is not. It is not mostly passwords.

- **Session credentials** for three messaging and gaming platforms.
- **Browser data**, which in practice means cookies as much as saved logins.
- **Wallet data**, which is not a credential you rotate at all.

This is the distinction we keep coming back to, because it decides whether a response
works. **A password reset invalidates a password. It does not invalidate a session.** An
attacker holding a live session cookie does not need to log in, so there is nothing for a
new password to stop, and no MFA prompt to satisfy either, because the session already
satisfied it.

The same is true one step further out. Rotating a key does not revoke a token. Changing a
seed phrase is not a thing you can do.

## How it arrives, which is the ordinary part

Victims search for software, follow a result to a GitHub repository impersonating the real
project, and download from it. The campaign impersonated **at least 40 brands**, including
LastPass Authenticator itself, and the researchers date it to at least 13 August 2026. The
downloads are ZIP archives inflated to as much as **148 MB**, which is large enough to fall
outside some scanning limits.

The installer is a renamed copy of `vsdbg.exe`, Microsoft's Visual Studio debugger, with a
malicious `vsdbg.dll` dropped beside it, so the attacker's code executes inside a signed
Microsoft process.

There is no exploit in that chain. A person searched, trusted a repository that looked
right, and ran it.

## What we do about it, and what we do not

**We are not an EDR and we would not have stopped this.** A signed kernel driver
terminating 145 security products is not something an API answers. Any vendor telling you
otherwise this week is selling you something.

What we work on is the half that is still observable after the endpoint stops reporting:
whether the material that left is now in circulation.

- `POST /v1/metered/infostealer` answers whether an email address appears in infostealer
  log dumps. Not whether it was in a breach years ago, which is a different and much older
  question, but whether a machine belonging to that person was logging keystrokes and
  hoovering browser stores.
- `POST /v1/metered/session-risk` answers the question a password reset does not: whether a
  live session was taken.
- `POST /v1/wallet-risk` and `POST /v1/link-check` are open, with no key, no card and no
  signup, capped per source IP rather than billed. The link check is the one that would
  have been useful in front of the download.

And in the consumer product, the response for this specific shape is `/sweep`: close the
forwarding rules, revoke the sessions, remove the rogue recovery options, **and only then**
reset the password. Doing it in the other order leaves an attacker inside an account whose
password has just been helpfully changed for them.

## The uncomfortable part

We collect from criminal marketplaces and infostealer log dumps, which means what we see is
the output of campaigns like this one after they have already worked. We are not early to
the infection. We are early to the consequence, which is a smaller claim and a true one.

We do not quote a corpus headline, here or anywhere. Most of any vendor's total is ingested
public feeds you already have, and the number that matters is what is in it that you could
not find elsewhere. Ask us that instead.

## If you want the short version

The detection layer was off before the theft began, by design, with a Microsoft signature.
Plan for the case where your detection did not fire, because that case is now a product
feature of the malware. The plan is: know what left, revoke sessions before rotating
passwords, and treat a wallet as unrecoverable rather than rotatable.

Free checks, no account: forward a suspicious email to
[checkemail@relayshield.net](mailto:checkemail@relayshield.net), or paste a link or a wallet
address into [the checker in Telegram](https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-blog).

The API is at
[api.relayshield.net/developers](https://api.relayshield.net/developers?source=rapuncel-blog).
