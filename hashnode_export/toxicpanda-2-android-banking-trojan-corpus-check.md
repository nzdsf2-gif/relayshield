---
title: "ToxicPanda 2.0 commits bank fraud from your own phone. We checked our corpus for it and found nothing, on purpose."
slug: toxicpanda-2-android-banking-trojan-corpus-check
date: 2026-08-26
---

# ToxicPanda 2.0 commits bank fraud from your own phone. We checked our corpus for it and found nothing, on purpose.

*Corpus check measured 2026-08-25 against the live `malware-index` GSI.*

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
