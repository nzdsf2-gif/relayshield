---
title: "rsscan --deps: Nearly Half of Your Dependencies' Publishers Are on Personal Gmail"
slug: rsscan-deps-who-can-publish-into-your-dependencies
date: 2026-08-13
---

# rsscan --deps: Nearly Half of Your Dependencies' Publishers Are on Personal Gmail

Install Next.js, React, TypeScript, ESLint, Jest, axios, Tailwind, Prettier and dotenv into an empty
directory. That is not an unusual project. That is Tuesday.

You get 433 packages. Behind those 433 packages are **275 distinct accounts that can publish code
into them**, and **126 of those accounts are on consumer webmail**. 118 of the 126 are `gmail.com`.

Nobody is doing anything wrong in that sentence. That is the part worth sitting with.

We built the thing that counts it, we are releasing it under MIT today, and you can reproduce every
number in this post in about a minute.

```bash
pip install rsscan
rsscan --deps
```

It reads `package-lock.json` or `package.json` from the current directory, resolves each package to
the accounts that can publish it, and prints counts. It runs locally. There is no account, no API
key, and no network call to us: the only host it contacts is `registry.npmjs.org`.

## What we measured

Six manifests, generated with `npm install --package-lock-only --ignore-scripts`, which resolves the
full transitive tree from registry metadata without downloading a tarball or running an install
script. Then `rsscan --deps` over each.

| Install | Packages | Publisher accounts | On consumer webmail | Role or automation | Unresolved |
|---|---|---|---|---|---|
| `npm i express` | 65 | 85 | 46 (54%) | 11 | 0 |
| `npm i webpack` | 67 | 95 | 40 (42%) | 12 | 0 |
| `npm i eslint` | 68 | 101 | 51 (50%) | 14 | 0 |
| `npm i jest` | 289 | 208 | 96 (46%) | 19 | 0 |
| `npm i next` | 54 | 29 | 10 (34%) | 4 | 0 |
| the nine packages above, together | 433 | 275 | 126 (46%) | 28 | 0 |

Measured 13 August 2026. These numbers will drift as maintainer lists change, which is rather the
point.

Three things about the method, because a number nobody can check is not a finding.

**"Publisher account" means a distinct email in the registry's `maintainers` array, plus `_npmUser`
on the version you would actually install.** That second field matters: `maintainers` lists everyone
who *could* have published, while `_npmUser` is whoever *did* push the bytes sitting in your
`node_modules`.

**Email is a proxy for account, and it is imperfect in both directions.** One human with two
addresses counts twice. Two humans sharing an address count once. We report distinct addresses and
call them accounts because that is what the registry exposes, and pretending otherwise would be
worse than the caveat.

**"Consumer webmail" is a fixed domain list**, and we checked it was not inflated before publishing
this. No GitHub `noreply` addresses landed in the count. Role and automation addresses like
`security@` or `oss-bot@` are counted in their own column and excluded from the webmail figure, so
nothing is double counted.

The **Unresolved** column is zero across all six, and it exists because it is the column that keeps
the rest honest. A package whose publishers we could not look up is not a package with no
publishers. If a run cannot reach the registry, `--deps` prints that count in red rather than
quietly folding it into a reassuring total.

## Why this number is the one that matters

Every package security tool on the market reads the artifact. Socket, Snyk, Aikido, Endor: they
fetch the tarball, look at what the code does, and tell you whether it is dangerous. They are good
at it, and if you are not running one you should be.

They share a blind spot, and it is not a bug in any of them. It is structural.

**A self-replicating npm worm does not begin with malicious code. It begins with a maintainer
account.**

Reconstruct one from the end and the sequence is always roughly this:

1. A maintainer's laptop gets infostealer malware on it. Not a targeted attack. The usual route: a
   cracked tool, a fake browser update, a malicious ad.
2. The stealer takes everything the browser and the filesystem will give it. Saved passwords,
   session cookies, and, on a developer machine, the contents of `.npmrc`. That file holds a
   long-lived npm publish token.
3. The token is sold in a log, usually within days.
4. The buyer publishes a new patch version of a package that maintainer owns. The code is not
   subtle. It does not need to be, because nobody is reading a patch bump.
5. That version runs on install, in CI, on machines belonging to everyone who depends on it. It
   harvests *their* npm tokens.
6. It publishes itself into their packages. Now it is a worm.

Look at where the detectable code appears in that list. **Step four.** By the time there is a
malicious artifact for a scanner to analyse, the compromise is four steps old and propagation is one
step away. Everything before step four is an identity problem, and none of it is visible in a
tarball, because none of it has happened in a tarball yet.

Shai-Hulud, in September 2025, is the version of this most people have now heard of. It is worth
being precise about why it spread: not because the payload was clever, but because the credential
that lets you publish to npm is a bearer token that usually lives in a plaintext file on a laptop,
and laptops get infostealers.

Which is why 126 is a more interesting number than 433. A publish credential on a company domain
sits behind SSO, and when that person leaves or gets compromised there is an IT function that can
revoke it centrally. A publish credential on a personal Gmail has none of that. There is no
offboarding, no central revocation, no device management, and no security team. **That is not a
criticism of the maintainers. It is a description of how open source actually gets published**, by
people doing it on their own machines, on their own time, with their own accounts, largely for free,
in code that the rest of us then put in production.

## If you ship models, this is the same problem wearing different clothes

Everything above is about npm because that is where the self-replicating worms are. The mechanism is
not about npm.

The stealer log that carries a maintainer's npm publish token carries their Hugging Face token in
the same dump, from the same laptop, in the same afternoon. Both are bearer credentials. Both sit in
a plaintext file in the home directory. Neither is protected by the MFA on the account that owns it,
because a token is not a login.

Think about what a write-scoped HF token actually permits. Pushing a new revision to a model repo.
Updating the weights that something downstream loads with `from_pretrained` and does not diff,
because nobody diffs weights. A model repo has the same shape of trust as a package registry, with
one difference that makes it worse: a malicious npm patch bump is at least readable if someone
bothers. A poisoned checkpoint is a binary blob, and there is no equivalent of reading the diff.

The defence is the same on both sides, and it is not clever:

- Tokens are credentials, so they should expire. A publish token that has been valid since 2023 is
  not a token, it is a permanent key someone left in a drawer.
- Scope them to what actually needs pushing. A CI job that reads does not need a write token.
- Assume the laptop is the weak point, because it is. Every chain in this post runs through a
  developer machine, not through a registry.

And the question worth asking about your own dependencies is the same in both ecosystems: not "is
this artifact malicious", which is what every scanner already answers, but "is the account that can
replace this artifact currently compromised".

## What `--deps` deliberately does not do

It does not screen anybody. It counts.

That is a design decision and not a roadmap gap, so it is worth being direct about where the line
is. `rsscan --deps` tells you the size and shape of your publisher surface. It cannot tell you
whether any of those 275 accounts is compromised right now, because answering that means checking
identities against infostealer corpora and breach data, and that is a different job with real costs
attached. We sell that part. This part is free, and it is free in the way that matters: no account,
no key, no rate limit, and no telemetry.

It also **names nobody**. Not in the output, not in a log, not in a debug field. You do not need any
individual's identity in order to pin a version and require review on its updates, and naming an
uninvolved third party as a risk carries real legal exposure for zero benefit. The tool prints
integers.

On telemetry specifically, since this is a security tool asking to be run on your machine:
`rsscan --deps` sends nothing anywhere. The wider `rsscan` secret scanner has an `--org` flag that
reports a domain and severity counts so we can see adoption at a company, and it is **opt-in, off by
default**. We wrote a version that inferred it from your git commit email and turned it on by
default. We held that version back and shipped this one instead.

## The honest limit

A count is not a verdict, and registry metadata is not always current. If a maintainer changed their
email and the registry still lists the old one, `--deps` counts an address that is not theirs any
more. That inflates the count in one direction and hides a real account in the other. We would
rather you hear that from us than find it yourself.

`rsscan` is MIT licensed, on [PyPI](https://pypi.org/project/rsscan/) and
[GitHub](https://github.com/RelayShield/rsscan), and also ships as a pre-commit hook, a GitHub
Action, a GitLab CI component, a CircleCI orb and a Docker image. The dependency counting is new in
this release. The secret scanning has been there since the start, matches 31 credential patterns
entirely on your machine, and never transmits your code or a matched value.

If you want the part that answers "and is any of them compromised", that is
[our dependency-risk API](https://api.relayshield.net/developers?source=rsscan-deps), included flat
in a bundle rather than metered per manifest, because re-screening 400 maintainers costs us about
what re-screening four does.

But run the free one first. Point it at your own lockfile and see how many people can publish into
your production build. Most teams have never counted.

```bash
pip install rsscan && rsscan --deps
```
