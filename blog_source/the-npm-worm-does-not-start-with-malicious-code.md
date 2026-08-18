---
title: "The npm Worm Does Not Start With Malicious Code"
slug: the-npm-worm-does-not-start-with-malicious-code
date: 2026-08-12
---

# The npm Worm Does Not Start With Malicious Code

Every package security tool on the market reads the artifact. Socket, Snyk, Aikido, Endor: they
fetch the tarball, look at what the code does, and tell you whether it is dangerous. They are good
at it, and if you are not running one you should be.

They all share a blind spot, and it is not a bug in any of them. It is structural.

**A self-replicating npm worm does not begin with malicious code. It begins with a maintainer
account.**

## The actual chain

Reconstruct one of these from the end and the sequence is always roughly this:

1. A maintainer's laptop gets infostealer malware on it. Not a targeted attack. The usual route:
   a cracked tool, a fake browser update, a malicious ad.
2. The stealer takes everything the browser and the filesystem will give it. Saved passwords,
   session cookies, and, on a developer machine, the contents of `.npmrc`. That file holds a
   long-lived npm publish token.
3. The token is sold in a log, usually within days.
4. The buyer publishes a new patch version of a package that maintainer owns. The code is not
   subtle. It does not need to be, because nobody is reading a patch bump.
5. That version runs on install, in CI, on machines belonging to everyone who depends on it. It
   harvests **their** npm tokens.
6. It publishes itself into their packages. Now it is a worm.

Look at where the detectable code appears in that list. **Step four.** By the time there is a
malicious artifact for a scanner to analyse, the compromise is four steps old and the propagation
is one step away.

Everything before step four is an identity problem. None of it is visible in a tarball, because
none of it has happened in a tarball yet.

Shai-Hulud, in September 2025, is the version of this most people have now heard of. It is worth
being precise about why it spread: not because the payload was clever, but because the credential
that lets you publish to npm is a bearer token that usually lives in a plaintext file on a laptop,
and laptops get infostealers.

## The question nobody can answer

Here is the question a security lead actually wants answered before a release:

> Of the 412 packages we install, is any of them currently maintained by an account that has been
> compromised?

Ask your SCA tool. It cannot answer, and not because it is bad. It analyses code, and this is not a
question about code. It is a question about people, and specifically about whether a particular
human's machine is currently owned.

We can answer it, because that is what we already do. Screening an identity against infostealer
corpora, breach data and session records is the thing RelayShield was built to do. This is that
same engine pointed at a different input: instead of your employees, the maintainers of your
dependencies.

## What we shipped

`POST /v1/metered/dependency-risk`. Send a list of package names, or a `package.json` or
`package-lock.json`.

```bash
curl -X POST https://api.relayshield.net/v1/metered/dependency-risk \
  -H "X-RS-API-KEY: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"packages": ["left-pad", "chalk", "@types/node"]}'
```

Each package is resolved to the accounts that can publish it, including the account that actually
published the version you are installing. Those accounts are screened against our infostealer
corpus. You get back findings at the dependency level:

```json
{
  "packages_checked": 412,
  "maintainer_accounts_screened": 148,
  "role_accounts_excluded": 13,
  "dependencies_at_risk": 3,
  "high_severity": 3,
  "findings": [{
    "package": "left-pad",
    "severity": "HIGH",
    "signal": "maintainer_in_recent_stealer_log",
    "most_recent": "2026-07-28T04:12:00.000Z",
    "detail": "An account able to publish this package appears in an infostealer log dated within the last 90 days."
  }],
  "recommended_action": "Pin the flagged versions, require review on their updates, and do not auto-merge their releases until the exposure ages out."
}
```

That is the whole product. Three of your dependencies are maintained by an account in a recent
stealer log. Pin them, review their updates, do not auto-merge.

## Four decisions worth explaining

**We never tell you who the maintainer is.** Not in the response, not in a log, not in a debug
field. You do not need someone's identity in order to pin a version and require review, and naming
an uninvolved third party as compromised carries real legal exposure for zero product benefit. We
did not build a version that names people even internally, because internal fields have a way of
ending up in support conversations.

**Recency is the signal. Breaches are not.** A maintainer's address turning up in a 2013 breach
tells you nothing about whether their laptop is owned today, and alerting on it would bury the real
finding under a decade of noise. A stealer log within 90 days is HIGH. Older is MEDIUM, and we call
it context rather than an incident.

**Role addresses are excluded from alerting, not just from display.** Around 9% of npm maintainer
emails are shared inboxes: `security@`, `dev@`, `oss-bot@`. A hit on a mailing list tells you
nothing about whether one person's machine is compromised, and a false positive on a product whose
entire pitch is the opposite of false positives is worse than no product.

**npm first, PyPI later.** We measured both. About 91% of npm maintainer emails are individual
humans; on PyPI it is closer to 69%, because PyPI returns a lot of `contact@` and mailing list
addresses. npm is both the better join and where the self-replicating worms actually are.

## The part that matters more than the scan

A one-time dependency scan is close to decorative. Your tree is clean today and a maintainer gets
phished in March. **The compromise happens at a random future moment, which means this is a
continuous product or it is a decoration.**

So `dependency` is now a subject type in Verdict Watch, alongside addresses, emails, domains and
phone numbers. Register a package, and you are notified when the answer **changes**, not on a
schedule and not when the same known exposure gets a new log entry. Flat rate, because the marginal
cost of re-screening 400 maintainers is approximately the same as re-screening four.

## One honest caveat

A clean result means nothing was found **in the sources we queried**. It is not proof that your
dependencies are safe.

The specific gap worth knowing about: registry metadata is not always current. If a maintainer
changed their email and the registry still lists the old one, we screen an address that is not
theirs any more, and it comes back clean. That is a false clean, and we would rather you hear it
from us than discover it.

When an upstream source is unavailable, we say so explicitly and the response tells you the run was
incomplete rather than printing a reassuring sentence underneath a degraded flag. Nobody's threat
feed proves absence. Anyone selling you that is selling certainty that does not exist.

## Getting it

`dependency-risk` is **included at no per-call charge** in the **Agentic Attack Surface** bundle at
$299/mo, alongside LLM credential exposure, MCP registry risk, prompt injection breach exposure,
tech stack CVE and bulk identity risk. Scan a 400-package manifest as often as you like; it costs
the same as scanning four, because that is roughly what it costs us. Buy it on
[AWS Marketplace](https://aws.amazon.com/marketplace/pp/prodview-6p6csngrcg3zq), which draws down
your existing AWS committed spend, or directly by card at
[api.relayshield.net/developers](https://api.relayshield.net/developers?source=blog-npm-worm).

Outside the bundle it is pay-as-you-go at $0.50 a call, priced against what it costs to serve: one
call fans out to as many as 100 registry lookups and 150 identity screens.

Point it at your own `package-lock.json`. If it comes back clean, you have lost a minute. If it
does not, you have found the thing four steps before the scanner would.
