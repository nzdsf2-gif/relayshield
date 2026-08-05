# Five Out of Five: Distribution Package

*All channels. Ready to post. Canonical is live. Cross-post: Medium, LinkedIn, Telegram, Farcaster,
Mastodon. Show HN and TLDR Security drafts included.*

**House rule for this post: no em-dashes or en-dashes in any copy below.** Hyphens inside technical
terms stay (`pre-commit`, `secret-scan`, `SIM-swap`). If you edit any block, re-check it.

---

## Canonical (LIVE, published 2026-08-03)

**URL:** https://blog.relayshield.net/we-searched-github-for-leaked-aws-keys-five-of-five-were-false-positives

Worker version `f7f2926f`. Everything below links to this. Do not re-host the body anywhere except
Medium, and there only via Import so the canonical tag is set.

### Metadata (for Medium and any future syndication)

- **Display title**: We searched public GitHub for leaked AWS keys. All five top results were false positives.
- **SEO title** (~60 char budget): Secret Scanning False Positives: 5 of 5 Top GitHub Hits
- **Meta description** (150 limit): We searched public GitHub for AWS keys leaked against a domain. 4,240 hits. The top five contained no credentials at all. Here is what that costs you.
- **Slug**: `we-searched-github-for-leaked-aws-keys-five-of-five-were-false-positives`
- **Tags**: `cybersecurity`, `devsecops`, `appsec`, `secrets-management`, `supply-chain-security`
- **Cover image**: none generated. A plain "5 / 5" or "4,240 → 0" stat graphic would work. Do not
  block publishing on it.

### Attribution keys (registered and deployed 2026-08-03, verified live)

Each channel gets its own key so CloudWatch can separate them. All render the same landing banner.

| Channel | Link to use |
|---|---|
| Blog CTA (already in the post) | `https://api.relayshield.net/developers?source=secret-scan` |
| Medium | `https://api.relayshield.net/developers?source=secret-scan-medium` |
| LinkedIn | `https://api.relayshield.net/developers?source=secret-scan-linkedin` |
| Telegram | `https://api.relayshield.net/developers?source=secret-scan-telegram` |
| Farcaster | `https://api.relayshield.net/developers?source=secret-scan-farcaster` |
| Mastodon | `https://api.relayshield.net/developers?source=secret-scan-mastodon` |
| Show HN | `https://api.relayshield.net/developers?source=secret-scan-hn` |

An unregistered key logs `unmatched:` and renders no banner. Do not invent new ones without adding
them to `_SOURCE_BANNERS` in `relayshield_developer_signup.py` and redeploying.

---

## 1. Medium

**Use "Import a story". Do not paste.** Medium has no Markdown paste support, and Import sets the
canonical link to blog.relayshield.net in one step, which is the whole point.

**Delete any earlier draft and re-import.** The first import on 2026-08-03 pulled the site's
"← All posts" navigation link into the top of the story. That was our bug: the link sat inside the
page's article element, which is exactly what an importer treats as the post body. Fixed and
deployed (worker `9c6be2d4`), verified live: the article element now contains one link, the CTA.
A fresh import comes in clean.

1. Medium → your avatar → **Stories** → **Import a story**
2. Paste the canonical URL above, click Import
3. **Fix the code block by hand. This one is Medium's importer, not our HTML.** Our page serves a
   proper 6-line `<pre><code>` block (verified), but the importer flattens the newlines into a
   single line and leaves two empty code blocks after it. Delete all three, insert one fresh Medium
   code block (type three backticks then Enter), and paste exactly:
   ```
   # .pre-commit-config.yaml
   repos:
     - repo: https://github.com/RelayShield/rsscan
       rev: v0.1.2
       hooks:
         - id: rsscan
   ```
   Indentation is load-bearing YAML. If it flattens, the config a reader copies will not work.
4. Check the numbered list survived. It is a real `<ol>` on our side, so it should come through.
5. Set tags: `Cybersecurity`, `DevSecOps`, `Programming`, `Security`, `Software Development`
6. Before publishing, swap the CTA link in the body to the `secret-scan-medium` key above.
7. Confirm the footer reads "Originally published at https://blog.relayshield.net". That line is
   Medium's own confirmation that the canonical tag was picked up. If it is missing, stop and
   re-import rather than publishing a duplicate that competes with the canonical in search.

**Expected and fine, do not try to fix:** Medium converts straight quotes and apostrophes to curly
ones. That is its typography, it applies to every imported story, and it does not affect the
canonical post.

---

## 2. LinkedIn

Highest-value channel for this post. Security leads and engineering managers live there. Leads with
the cost argument, not the finding.

**Plain text. LinkedIn renders no markdown, so there is no bold or italic below by design.**

```text
Every false CRITICAL from a secret scanner is a credential rotation that gets scheduled, assigned, investigated, and then cancelled.

It burns a senior engineer's afternoon. Worse, it teaches the team that the scanner cries wolf. That second lesson costs far more than the afternoon did.

Here is how easily it happens.

We searched public GitHub for AWS keys leaked against a domain. The query returns 4,240 hits. We read the top five:

1. A documentation table listing environment variable names
2. A config example containing the literal string aws_access_key_id=AKIA.... (dots, not a key)
3. A README for a redaction tool, describing which formats it detects
4. A curated link list that happened to contain both strings
5. A policy file with a domain allowlist

Five out of five. Not one contained a credential. One of them was a secret-scanning tool's own documentation.

Any scanner that treats a search hit as a finding reports all five as a CRITICAL AWS key exposure. That is not an edge case. It is the default, because the search engine did exactly what it was asked to do. It matched a string. It has no opinion about whether that string was a secret.

The fix is not clever. It is just work: re-run the actual credential patterns against the matched code fragment, and keep only what has a real credential shape.

Two things worth saying to anyone who owns this risk.

First, a pre-commit hook covers exactly one thing: a key you are about to commit, from a machine that has the hook installed. It cannot see a key committed fourteen months ago by someone who has since left. It cannot see the .env published inside your npm package, or the build arg baked into a public Docker image layer. Those keys are already out.

Second, and this is the part secret scanning never touches: your engineers' own credentials. Passwords sitting in infostealer logs right now, harvested off personal machines, with live session cookies that skip your MFA entirely. None of that is in your code, so no secret scanner will ever show it to you. They are the same identities your CI/CD, cloud consoles and registries authenticate.

Full writeup with the measurement:
https://blog.relayshield.net/we-searched-github-for-leaked-aws-keys-five-of-five-were-false-positives

The local scanner is free and MIT licensed. It runs entirely on your machine. No API key, no account, no network call:
https://api.relayshield.net/developers?source=secret-scan-linkedin

#DevSecOps #SecretsManagement #ApplicationSecurity #SupplyChainSecurity #CISO
```

---

## 3. Telegram

Existing channel. This audience installs things, so lead with the free tool and keep the finding as
supporting evidence.

```text
New writeup: we searched public GitHub for AWS keys leaked against a domain.

4,240 hits. We read the top five. None of them contained a credential.

One was a documentation table. One was the literal placeholder aws_access_key_id=AKIA.... with dots instead of a key. One was a redaction tool's own README listing the formats it detects. A scanner that treats a search hit as a finding reports all five as a CRITICAL AWS key exposure.

So we built the boring half: every candidate gets the real credential patterns re-run against the matched code fragment, and only a genuine credential shape survives.

The free part, if you want it:

rsscan runs all 31 credential patterns entirely on your own machine. No API key, no account, no network call, no size cap, MIT licensed. A pre-commit secret scanner that uploads your diff to a vendor is a bad trade, so ours does not.

pip install rsscan && rsscan .

Also on GitHub, Docker Hub, the GitHub Marketplace and the CircleCI orb registry.

The hosted scan is the half the local hook cannot do. It looks for what is already public, across GitHub, npm, PyPI, Docker Hub and Hugging Face, for a domain you own. 0.35 USD a call, pay as you go.

Full post:
https://blog.relayshield.net/we-searched-github-for-leaked-aws-keys-five-of-five-were-false-positives

Get a key:
https://api.relayshield.net/developers?source=secret-scan-telegram
```

---

## 4. Farcaster

Dev-heavy audience. Lead with the finding. Post to **/security** and **/dev**. Hashtags are not
really a thing here, so there are none.

```text
We searched public GitHub for AWS keys leaked against a domain. 4,240 hits.

We read the top five:

1. a docs table of env var names
2. the literal placeholder aws_access_key_id=AKIA.... (dots, not a key)
3. a redaction tool's README listing formats it detects
4. a link list containing both strings
5. a policy file with a domain allowlist

Five out of five. Zero credentials.

Any scanner that treats a search hit as a finding calls all five a CRITICAL AWS key exposure. The search engine did what it was asked. It matched a string.

Writeup:
https://blog.relayshield.net/we-searched-github-for-leaked-aws-keys-five-of-five-were-false-positives

Free local scanner, MIT, runs fully offline:
https://api.relayshield.net/developers?source=secret-scan-farcaster
```

---

## 5. Mastodon

infosec.exchange conventions. Tags are the discovery mechanism, so 3 or 4 of them.

**Mastodon counts every URL as 23 characters regardless of its real length,** so the long canonical
URL is cheap here. The count below reflects that.

```text
We searched public GitHub for AWS keys leaked against a domain. 4,240 hits.

The top five results: a docs table, a literal AKIA.... placeholder, a redaction tool's own README, a link list, and a domain allowlist.

Five out of five. Not one contained a credential.

Any scanner that treats a search hit as a finding calls all five a CRITICAL exposure.

https://blog.relayshield.net/we-searched-github-for-leaked-aws-keys-five-of-five-were-false-positives

Free local scanner, MIT: https://api.relayshield.net/developers?source=secret-scan-mastodon

#infosec #devsecops #appsec #opensource
```

---

## 6. Show HN

**Title it as the finding, never as the product.** The measurement is the HN-shaped part; a launch
announcement gets flagged.

**Title options, best first:**

1. `We searched public GitHub for leaked AWS keys, 5 of 5 top results were false positives`
2. `Show HN: rsscan, a pre-commit secret scanner that never uploads your code`
3. `GitHub code search has no regex, and most secret scanners send it regex anyway`

Option 1 is a link post to the blog. Option 2 is a Show HN to the GitHub repo and is the honest
framing only if you are actually submitting the tool, not the post. Do not run both in the same week.

**First comment (post it yourself, immediately after submitting):**

```text
Author here. The number that surprised me was not the false positive rate, it was how ordinary the false positives are. Four of the five are documentation. One is a secret-scanning tool's own README listing the formats it detects.

The verification step is unglamorous: request the matched fragment from the search API, then re-run the real credential patterns against it and keep only what has a genuine credential shape. It costs no extra API calls, and it is the entire difference between a list of hits and a list of findings.

The local scanner is MIT and runs fully offline: https://github.com/RelayShield/rsscan

Happy to answer questions about the pattern set or the rate-limit handling.
```

---

## 7. TLDR Security outreach

Scoped as BA-4 in TODO. Pitch after the post has been live a day or two, so the link has some
history.

**Corrected 2026-08-03: the newsletter is at `tldr.tech/infosec`, NOT `tldr.tech/security`.**
That path 404s and was wrong in this doc and in TODO. Verified live: `/infosec` returns 200, the
network's newsletter index lists `/ai /crypto /data /design /dev /devops /fintech /founders
/hardware /infosec /it /marketing /privacy /product /tech`, and there is no `/security`.

**What TLDR InfoSec actually is** (from its own page): a free daily newsletter covering security
news, vulnerabilities and tools in a 5-minute read, **410,000 subscribers**, aimed at practitioners
through to CISOs, each issue linking out to the original reporting. The 1.6M figure on tldr.tech is
the whole TLDR network across all editions, not this one.

**There is no published editorial or submission address.** The only contact route linked from the
page is `advertise.tldr.tech`, which is paid sponsorship, not editorial. So the pitch below has no
verified destination yet. Find a real editorial contact before sending, and do not pay for
placement on the strength of this item.

**Second target worth checking: `tl;dr sec` (tldrsec.com) by Clint Gibler.** TLDR InfoSec's own FAQ
calls it out as a separate, independent newsletter. It covers security tooling and research, which
is a closer fit for a free MIT tool plus a measured finding. **Unverified:** tldrsec.com returned
403 behind Cloudflare bot protection, so its submission route could not be checked from here.

**Subject:** `Measured finding: 5 of 5 top GitHub secret-scan hits were false positives`

```text
Hi,

Short pitch for TLDR Security.

We searched public GitHub for AWS keys leaked against a domain. The query returns 4,240 hits. The top five results contained no credentials at all: a documentation table, a literal aws_access_key_id=AKIA.... placeholder, a redaction tool's own README, a link list, and a domain allowlist. One of the false positives was a secret-scanning tool documenting the formats it detects.

The writeup covers why this is the default behaviour rather than an edge case, and what verification actually costs to implement.

There is also a free MIT tool in it, rsscan, a pre-commit secret scanner that runs all 31 patterns locally with no API key, no account and no network call. Not a trial, not a freemium gate.

Post: https://blog.relayshield.net/we-searched-github-for-leaked-aws-keys-five-of-five-were-false-positives
Tool: https://github.com/RelayShield/rsscan

Happy to supply the raw query results if useful.

Thanks,
Andrew
RelayShield
```

---

## Do not post

- **X**: the `@RelayShieldHQ` account is suspended.
- **Hashnode**: abandoned 2026-07-29 after repeated silent AutoMod removals.

---

## After posting

Watch arrivals by channel. Each key above appears as its own row:

```
fields @timestamp | filter @message like /developer-signup request/
| parse @message "source=*" as src | stats count() by src | sort by count() desc
```

A row reading `unmatched:<something>` means a live link is pointing at a key that does not exist.
Fix the link or register the key.

Two things to check the day after:

- The Medium import kept the numbered list and the canonical tag points at blog.relayshield.net.
- The blog post still renders. Cloudflare caches for 5 minutes (`max-age=300`), so a 404 immediately
  after any redeploy is expected and not a failure.
