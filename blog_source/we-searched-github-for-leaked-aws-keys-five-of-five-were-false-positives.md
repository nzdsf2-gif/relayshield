---
title: "We searched public GitHub for leaked AWS keys. All five top results were false positives."
slug: we-searched-github-for-leaked-aws-keys-five-of-five-were-false-positives
date: 2026-08-03
---

# We searched public GitHub for leaked AWS keys. All five top results were false positives.

*Every number below was measured against the live APIs.*

---

Search public GitHub for `"yourcompany.com" AKIA` and you will get thousands of results. Almost
none of them are credentials.

We know, because we built the scanner that had to tell the difference. The gap between "this search
returned a hit" and "you have a leaked key" turned out to be the entire product.

## Five out of five

Here are the top five results for `"openai.com" AKIA`, a query that returns **4,240 hits**:

1. A documentation table listing environment variable names, including `OPENAI_API_KEY`
2. A config example containing the literal string `aws_access_key_id=AKIA....` with dots, not a key
3. A README for a redaction tool, describing which credential formats it detects
4. A curated link list that happened to contain both strings
5. A policy file with a domain allowlist including `"*.openai.com"`

Five out of five. Not one contained a credential. One of them was a secret-scanning tool's own
documentation.

Any scanner that treats a search hit as a finding reports all five as a **CRITICAL AWS key
exposure**. That is not a hypothetical failure mode. It is the default one, because the search
engine is doing exactly what it was asked to do. It matched a string. It has no opinion about
whether that string was a secret.

## Why this should matter to you

If you run a pre-commit hook, you are covered against one thing: a key you are about to commit,
from a machine that has the hook installed. That is worth having. It is also a narrow window.

It cannot see a key committed fourteen months ago by someone who has since left. It cannot see the
`.env` that got published inside your npm package. It cannot see the build arg baked into a
public Docker image layer, or the token sitting in a Hugging Face model repo a data scientist
pushed from a laptop that never had your hooks installed.

Those keys are already public. They are not going to be caught going out. They are out.

The obvious move is to go looking for them, and that is where most teams stop, because the first
honest attempt produces the list above: thousands of hits, five out of five of them garbage. Run
that at your org and you generate a rotation backlog nobody works through. Alert fatigue on a
security signal isn't a nuisance. It is how the real finding gets closed as noise.

**For engineering managers, the cost is specific and measurable.** Every false CRITICAL is a
credential rotation that gets scheduled, assigned, investigated and cancelled. It burns a senior
engineer's afternoon and it teaches the team that the scanner cries wolf. The second lesson is more
expensive than the first afternoon.

## What we built differently

**Findings, not search hits.** Every candidate we surface gets the actual compiled credential
patterns re-run against the matched code fragment, and survives only if a real credential *shape*
is present. GitHub will return that fragment if you ask for it correctly, and most integrations
never do. This is the step that turns 4,240 candidates into a list you can act on, and it is the
difference between a tool that finds things and a tool that generates work.

Running **all 31 patterns** over each fragment costs no extra API calls, so it does something else
for free. A result surfaced by searching for an AWS prefix that actually contains a GitHub token
gets reported as a GitHub token, correctly labelled, instead of being filed under the wrong vendor.

**We look where secrets actually ship, not just where code lives.** Repo scanning is the wrong
shape of the problem, because secrets leak inside *released artifacts* constantly. Our scan covers
GitHub repositories, **npm and PyPI packages, Docker Hub images, and Hugging Face models and
Spaces**.

PyPI took real work. It has no search API any more, so "which packages belong to this org" has no
endpoint at all. The simple index does answer it, but it is 863,068 package names and roughly 45 MB,
which you cannot load into a 256 MB Lambda. Streaming it with a chunked regex works: 5.6 seconds,
28 MB peak resident memory.

**And the layer that has nothing to do with secrets.** A leaked API key is one shape of credential
exposure. Here is another: three of your engineers' passwords are sitting in an infostealer log
right now, harvested off a personal machine, complete with live session cookies that skip your MFA
entirely. No secret scanner will ever show you that, because it isn't in your code. We check
workforce identities against infostealer corpora, breach data, SIM-swap signals and stolen session
records, the same identities your CI/CD, cloud consoles and registries authenticate.

That combination is the thing we have not seen anywhere else: what leaked *from* your code, and
what leaked *about* the people who write it.

## Start free, and escalate when you find something

**If you write code: take the free tool.** `rsscan` runs all 31 patterns entirely on your machine.
No API key, no account, no network call, no size cap, MIT licensed. A pre-commit secret scanner
that uploads your diff to a vendor is a bad trade, so ours doesn't.

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/RelayShield/rsscan
    rev: v0.1.2
    hooks:
      - id: rsscan
```

It is on PyPI, GitHub, Docker Hub, the GitHub Marketplace and the CircleCI orb registry. It will
never cost you anything, and it does not phone home.

**If you own the risk: the local hook is the half you can see.** `rsscan --report exposure.md`
writes a shareable exposure summary containing fingerprints and no secret values, safe to paste
into a ticket or forward to whoever owns credential rotation.

Then find out what is already public. The hosted scan runs across GitHub, npm, PyPI, Docker Hub and
Hugging Face for a domain you own, with the verification pass above, at **$0.35 a call**,
pay-as-you-go, no seat licences, no annual contract. It sits alongside the identity checks in the
same API: breach exposure, infostealer logs, SIM-swap and session risk on your workforce.

**→ Get an API key and run your first scan: [api.relayshield.net/developers](https://api.relayshield.net/developers?source=secret-scan)**

Scan your own domain first. If it comes back clean, you have lost four minutes and thirty-five
cents. If it doesn't, you found it before someone else did.
