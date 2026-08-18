# The npm Worm: Distribution Package

*All channels. Ready to post. Canonical is live. Cross-post: Hugging Face, LinkedIn, Medium,
dev.to, Telegram, Mastodon, Farcaster. Show HN draft included.*

**House rule for this post: no em-dashes or en-dashes in any copy below.** Hyphens inside technical
terms stay (`dependency-risk`, `pre-commit`, `package-lock.json`). If you edit any block, re-check
it.

---

## Canonical (LIVE, published 2026-08-12)

**URL:** https://blog.relayshield.net/the-npm-worm-does-not-start-with-malicious-code

Worker version `9bd89bf4`. Verified rendering in a real browser, not just a 200. Everything below
links to this. **Do not re-host the full body anywhere except Hugging Face, Medium and dev.to**, and
on all three only with the canonical set.

**Post body source:** `blog_source/the-npm-worm-does-not-start-with-malicious-code.md` in the repo.
That file is the paste source for any channel that needs the whole thing.

### Metadata

- **Display title**: The npm Worm Does Not Start With Malicious Code
- **SEO title** (~60 char budget): npm Worms Start With a Maintainer, Not With Code
- **Meta description** (150 limit): A self-replicating npm worm begins with a compromised maintainer account, four steps before there is any malicious code for a scanner to find.
- **Slug**: `the-npm-worm-does-not-start-with-malicious-code`
- **Cover image**: none generated. A six-step chain graphic with step 4 circled ("this is where
  scanners start looking") would carry the whole argument. **Do not block publishing on it.**

### Attribution keys (REGISTERED AND DEPLOYED 2026-08-12, verified live)

Each renders the npm banner on `/developers`; an unregistered key renders nothing and logs
`unmatched:`. Verified today, key by key.

> **These are CTA links that go inside a post. None of them is ever the URL you import, paste into
> a share box, or hand to a syndication tool.** They all point at the developer signup page. The
> only URL that represents the article is the canonical above.

| Channel | Link to use |
|---|---|
| Blog CTA (already in the post) | `https://api.relayshield.net/developers?source=blog-npm-worm` |
| Hugging Face | `https://api.relayshield.net/developers?source=npm-worm-hf` |
| LinkedIn | `https://api.relayshield.net/developers?source=npm-worm-linkedin` |
| Medium | `https://api.relayshield.net/developers?source=npm-worm-medium` |
| dev.to | `https://api.relayshield.net/developers?source=npm-worm-devto` |
| Telegram | `https://api.relayshield.net/developers?source=npm-worm-telegram` |
| Mastodon | `https://api.relayshield.net/developers?source=npm-worm-mastodon` |
| Farcaster | `https://api.relayshield.net/developers?source=npm-worm-farcaster` |
| Show HN | `https://api.relayshield.net/developers?source=npm-worm-hn` |

**Do not invent a new one** without adding it to `_SOURCE_ALIASES` in
`relayshield_developer_signup.py` and redeploying.

---

## 1. Hugging Face blog

**Best fit we have had for HF, and it goes second after the canonical.** Developers who install
packages are exactly this audience, we already have a presence there rather than a cold start, and
there is a bridge nobody else can write.

**This one is a full paste, NOT an import.** The whole reason to post here is the HF-specific
section below, and no canonical import will carry it. Paste the body from
`blog_source/the-npm-worm-does-not-start-with-malicious-code.md`, then make the three edits listed
under it.

### Front matter

```yaml
---
title: "The npm Worm Does Not Start With Malicious Code"
thumbnail: /blog/assets/npm-worm/thumbnail.png
authors:
- user: relayshieldadmin
---
```

### Edit 1: canonical line, immediately under the title

```text
*Originally published at [blog.relayshield.net](https://blog.relayshield.net/the-npm-worm-does-not-start-with-malicious-code).*
```

### Edit 2: insert this ENTIRE section between "What we shipped" and "Four decisions worth explaining"

This is the part that does not exist anywhere else, and it is why we are posting here at all.

```text
## If you ship models, this is the same problem wearing different clothes

Everything above is about npm because that is where the self-replicating worms are. The mechanism
is not about npm.

The stealer log that carries a maintainer's npm publish token carries their Hugging Face token in
the same dump, from the same laptop, in the same afternoon. Both are bearer credentials. Both sit
in a plaintext file in the home directory. Neither is protected by the MFA on the account that
owns it, because a token is not a login.

`hf_` user access tokens and organization tokens are two of the 19 AI and LLM credential formats we
match, and they are in the corpus for the same reason npm tokens are: somebody's machine got owned
and the stealer took the whole directory.

Think about what a write-scoped HF token actually permits. Pushing a new revision to a model repo.
Updating the weights that something downstream loads with `from_pretrained` and does not diff,
because nobody diffs weights. A model repo has the same shape of trust as a package registry, with
one difference that makes it worse: a malicious npm patch bump is at least readable if someone
bothers. A poisoned checkpoint is a binary blob, and there is no equivalent of reading the diff.

The defence is the same on both sides, and it is not clever:

- Tokens are credentials, so they expire. A publish token that has been valid since 2023 is not a
  token, it is a permanent key someone left in a drawer.
- Scope them to what actually needs pushing. A CI job that reads does not need a write token.
- Assume the laptop is the weak point, because it is. Every chain in this post runs through a
  developer machine, not through a registry.

And the question worth asking about your own dependencies is the same in both ecosystems: not "is
this artifact malicious", which is what every scanner already answers, but "is the account that can
replace this artifact currently compromised".
```

### Edit 3: swap the CTA link

The post's "Getting it" section ends with a `/developers` link. Change its query to
`?source=npm-worm-hf`.

### Also do this

Cross-link the Space. HF readers can try the free-tier `llm-credential-exposure` check with no API
key, and a working thing beats a description:

```text
The related check runs free on our Space with no API key:
https://huggingface.co/spaces/relayshieldadmin/relayshield-agentic-attack-surface
```

---

## 2. LinkedIn

Highest-value channel for revenue even though the subject is developer-facing. **Native post, not a
link post.** LinkedIn suppresses off-platform links, so the argument goes in the body and the URL
goes in the first comment.

**Plain text. LinkedIn renders no markdown, so there is no bold or italic below by design.**

```text
Every package security tool reads the artifact. Socket, Snyk, Aikido, Endor: they fetch the tarball, look at what the code does, and tell you whether it is dangerous. They are good at it, and if you are not running one you should be.

They share one blind spot, and it is not a bug in any of them. It is structural.

A self-replicating npm worm does not begin with malicious code. It begins with a maintainer account.

Reconstruct one from the end and the sequence is always roughly this:

1. A maintainer's laptop picks up infostealer malware. Not a targeted attack. A cracked tool, a fake browser update, a malicious ad.
2. The stealer takes everything the filesystem will give it, including .npmrc, which holds a long-lived publish token.
3. The token sells in a log, usually within days.
4. The buyer publishes a new patch version. The code is not subtle. It does not need to be, because nobody reads a patch bump.
5. That version runs on install, in CI, on machines belonging to everyone downstream. It harvests their npm tokens.
6. It publishes itself into their packages. Now it is a worm.

Look at where the detectable code appears in that list. Step four.

By the time there is a malicious artifact for a scanner to analyse, the compromise is four steps old and the propagation is one step away. Everything before step four is an identity problem, and none of it is visible in a tarball, because none of it has happened in a tarball yet.

So we built the check for the other four steps. Send a package-lock.json, get back which of your dependencies are maintained by an account sitting in a recent infostealer log. Pin those, require review on their updates, do not auto-merge them.

One design decision worth stating plainly, because it was the hardest part.

We never tell you who the maintainer is. Not in the response, not in a log, not in a debug field. You do not need somebody's identity in order to pin a version and require review, and publishing "this named person is compromised" about someone who never opted in is not a thing we are willing to do. We did not build a version that names people even internally, because internal fields have a way of ending up in support conversations.

And the honest caveat, which I would rather you hear from us: registry metadata is not always current. If a maintainer changed their email and the registry still lists the old one, we screen an address that is not theirs any more and it comes back clean. That is a false clean. Nobody's threat feed proves absence.

Full write-up in the comments.

#SupplyChainSecurity #DevSecOps #npm #AppSec #ThreatIntelligence
```

### First comment (post immediately after)

```text
Full post: https://blog.relayshield.net/the-npm-worm-does-not-start-with-malicious-code

Run it against your own manifest: https://api.relayshield.net/developers?source=npm-worm-linkedin
```

### Hashtag notes

Five, at the end of the body, never in the comment. LinkedIn's own guidance is three to five; more
reads as spam and does not increase reach.

- **Use:** `#SupplyChainSecurity` `#DevSecOps` `#npm` `#AppSec` `#ThreatIntelligence`
- **Reserves if you swap one:** `#OpenSource`, `#SoftwareSupplyChain`, `#CyberSecurity`, `#InfoSec`
- **Avoid:** `#security` alone, far too broad to do anything

**Tagging:** naming Socket, Snyk, Aikido and Endor respectfully in the body is fine. Tagging them
into the post is a different act and invites a fight we do not want. Tag at most two accounts, and
only where there is a live conversation already.

---

## 3. Medium

**Use "Import a story". Do not paste.** Medium has no Markdown paste support, and Import sets the
canonical to blog.relayshield.net in one step, which is the whole point.

> ### THE IMPORT URL IS THIS ONE, AND ONLY THIS ONE
>
> ```text
> https://blog.relayshield.net/the-npm-worm-does-not-start-with-malicious-code
> ```
>
> **Do NOT paste the `?source=npm-worm-medium` link into the importer.** That link is the
> attribution CTA that goes *inside* the finished story. It points at the developer signup page, so
> importing it produces a Medium story that is a copy of our pricing page. This happened on
> 2026-08-12 because the attribution table sits directly above this section and the two links look
> interchangeable. They are not: **you import the canonical, you link the attribution.**

1. Medium → avatar → **Stories** → **Import a story**
2. Paste the **canonical URL in the box above**, click Import
3. **Repair the two code blocks by hand. This is not optional and it is not our bug.** See
   "Fixing the code blocks" below. Confirmed on 2026-08-12: our page serves both blocks as proper
   `<pre><code>` with real newlines (3 and 14 respectively, checked in the served HTML). Medium's
   importer collapses them to a single line anyway, and emits a **stray empty code block** after
   each one.
4. Find the CTA link at the bottom of the story. It will have imported as
   `?source=blog-npm-worm`. **Change it to `?source=npm-worm-medium`** so Medium traffic is
   attributable separately from blog traffic.
5. **Confirm the canonical points at blog.relayshield.net in a browser** before calling it done.
   This is the step that has been skipped before.

### If you already imported the wrong URL

Medium will have created a story containing our developer signup page. **Delete it rather than
editing it**, then import again from the canonical:

1. Medium → avatar → **Stories** → **Drafts**
2. Find the bad import. It will be titled something like "RelayShield API: Security Intelligence for
   Developers & Agents" rather than the post title.
3. The **...** menu on the story → **Delete story**
4. Re-import from the canonical URL above

Delete rather than edit because a Medium import sets the canonical link from the URL it was given.
A story imported from `/developers` carries a canonical pointing at `/developers`, and editing the
visible body does not change it. That would tell Google our pricing page and the article are the
same document.

### Fixing the code blocks

Medium's importer flattens `<pre>` content to one line and leaves an empty code block behind it.
Verified 2026-08-12 that the fault is Medium's, not ours: the served HTML has two `<pre><code>`
blocks containing real newlines. Nothing to fix on our side, so do not go looking.

**Two repairs, two deletions.**

1. Select the flattened curl block and replace it with this, newlines intact:

```text
curl -X POST https://api.relayshield.net/v1/metered/dependency-risk \
  -H "X-RS-API-KEY: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"packages": ["left-pad", "chalk", "@types/node"]}'
```

2. Delete the **empty code block** immediately below it. Click into it and backspace until the grey
   block disappears.

3. Select the flattened JSON block and replace it with this:

```text
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

4. Delete the second **empty code block** below it.

**Paste into Medium's code block, not as plain text.** Put the cursor in the existing grey block
before pasting, or Medium will render it as body prose. If it loses the block, type three
backticks on a new line to create a fresh one, then paste inside it.

### The vertical line is correct, leave it alone

The bar to the left of *"Of the 412 packages we install, is any of them currently maintained by an
account that has been compromised?"* is **Medium's blockquote styling, and it is intentional.**

That line is a `>` blockquote in the source (line 50 of
`blog_source/the-npm-worm-does-not-start-with-malicious-code.md`). It is the security lead's
question pulled out of the body so it reads as the thing the whole post is answering. It renders
with a left rule on our blog too, just a subtler one. **Do not convert it back to a paragraph**, it
loses the emphasis that makes the section work.

### What a correct import looks like

Verified against the live page on 2026-08-12, so you know what to expect:

- Title: **The npm Worm Does Not Start With Malicious Code**
- Exactly **two** links in the body: the AWS Marketplace listing, and the `/developers` CTA
- No stray "← All posts" navigation link at the top. That was a real bug on an earlier post and it
  is fixed; if you see one, tell me rather than deleting it by hand.

### Medium tags (maximum 5, and Medium ranks on them)

```text
Cybersecurity
Supply Chain Security
Npm
Devsecops
Open Source
```

Medium matches these as topics rather than hashtags, so use the title-case topic names exactly as
above rather than lowercase hashtags. `Cybersecurity` is the high-traffic one and should be first.

### Medium subtitle

```text
A worm starts four steps before there is any code for a scanner to find.
```

---

## 4. dev.to

Paste the markdown body from `blog_source/the-npm-worm-does-not-start-with-malicious-code.md` under
this front matter. dev.to renders our markdown as-is, so nothing needs repairing.

```yaml
---
title: The npm Worm Does Not Start With Malicious Code
published: true
canonical_url: https://blog.relayshield.net/the-npm-worm-does-not-start-with-malicious-code
tags: security, npm, opensource, devops
---
```

dev.to allows **four** tags, lowercase, no spaces. `supplychain` is not an established tag there, so
`security` plus `npm` does the work. Swap the CTA link to `?source=npm-worm-devto`.

---

## 5. Telegram

Post through our own channel. This audience installs things, so the endpoint goes near the top.

```text
New writeup: the npm worm does not start with malicious code.

It starts with a maintainer's laptop picking up infostealer malware, which takes .npmrc, which holds a long-lived publish token. The token sells in a log. The buyer publishes a patch version. That version harvests everyone else's npm tokens in CI and republishes itself.

There is nothing for a package scanner to look at until step four of six. By then the compromise is four steps old and propagation is one step away.

So we shipped the check for the first four steps:

POST /v1/metered/dependency-risk

Send a list of package names, or your package.json or package-lock.json. You get back which dependencies are maintained by an account that appears in a recent infostealer log, with the severity split on recency: a stealer log inside 90 days is HIGH, older is context rather than an incident.

It never tells you who the maintainer is. Not in the response, not in a log, not in a debug field. Dependency level only. You do not need someone's identity to pin a version and require review.

Register a package as a dependency watch and you are told when the answer changes, rather than on a schedule.

Included at no per-call charge in the Agentic Attack Surface bundle, 299 USD a month. 0.50 USD a call outside it.

Full post:
https://blog.relayshield.net/the-npm-worm-does-not-start-with-malicious-code

Get a key:
https://api.relayshield.net/developers?source=npm-worm-telegram
```

**Copy with the locale forced**, or the arrows and any bold will mangle:

```bash
LC_CTYPE=UTF-8 pbcopy < telegram_npm_worm.txt
```

---

## 6. Mastodon

Small but genuinely technical, and this crowd responds to the privacy decision far more than to the
product. Lead with what we refused to build.

```text
Built a thing that answers "is any of my dependencies maintained by an account that is currently compromised", and the hardest part was deciding what NOT to return.

Findings come back at the dependency level. We never return, log or store the maintainer's identity. Not even in an internal field, because internal fields end up in support conversations. You do not need to know who someone is in order to pin a version and require review, and publishing "this named person is compromised" about somebody who never opted in is not a thing we are willing to do.

The mechanism it is aimed at: a self-replicating npm worm starts with a maintainer's laptop getting an infostealer, four steps before there is any malicious code for a scanner to find. Everything before step four is an identity problem and no tarball analysis can see it.

Honest caveat, since this crowd will ask: registry metadata is not always current. Maintainer changes their email, registry still lists the old one, we screen an address that is not theirs any more and it comes back clean. That is a false clean and we would rather say it out loud.

Write-up: https://blog.relayshield.net/the-npm-worm-does-not-start-with-malicious-code

#infosec #npm #supplychain #opensource #appsec
```

Same `LC_CTYPE=UTF-8 pbcopy` rule.

---

## 7. Farcaster

Weakest fit on the list. Crypto-native audience, and this post is not crypto. Post it, keep it
short, do not invest in it.

**Farcaster counts BYTES, not characters.** Check before posting:

```bash
python3 -c "print(len(open('farcaster_npm_worm.txt','rb').read()), 'bytes')"
```

```text
npm worms don't start with malicious code. They start with a maintainer's laptop getting an infostealer, 4 steps before a scanner has anything to look at.

We check those 4 steps now: send a package-lock.json, get back which deps are maintained by an account in a recent stealer log.

Dependency level only. Never names the human.

blog.relayshield.net/the-npm-worm-does-not-start-with-malicious-code
```

---

## 8. Show HN, optional and high variance

Only worth it if you lead with the limitation. HN punishes a pitch and rewards a stated failure
mode.

**Title:**

```text
Show HN: Check whether your npm dependencies' maintainers are in a stealer log
```

**First comment, post immediately:**

```text
Author here. The thing that made this worth building is that every package scanner reads the artifact, and a self-replicating worm starts four steps before there is an artifact to read: maintainer's laptop gets an infostealer, .npmrc publish token goes into a log, token sells, attacker publishes a patch version, that version harvests tokens in everyone's CI, it republishes itself.

So this screens the publisher accounts rather than the code.

The limitations, up front, because they are the interesting part:

Registry metadata is not always current. If a maintainer changed their email and the registry still lists the old one, we screen an address that is not theirs any more and it comes back clean. That is a false clean and I do not have a good fix for it.

Around 9% of npm maintainer emails are role addresses (security@, dev@, oss-bot@). We exclude those from alerting entirely rather than just from display, because a hit on a shared inbox says nothing about whether one person's machine is owned. That means we also miss a real compromise behind a role address.

Recency is the whole signal. A maintainer's address in a 2013 breach tells you nothing about today, so breach hits are context and only a stealer log inside 90 days is HIGH.

npm only for now. We measured PyPI at about 69% individual-human emails against npm's 91%, because PyPI returns a lot of mailing lists, and screening a mailing list is meaningless.

We never return the maintainer's identity, in the response or in logs. Happy to argue about that one; I think naming an uninvolved third party as compromised is not ours to do.

https://api.relayshield.net/developers?source=npm-worm-hn
```

---

## Sequencing

| When | Channel |
|---|---|
| Day 0 (done) | Canonical live |
| Day 0 | Telegram and Discord. Ours, zero cost. |
| Day 1 | **Hugging Face**, with the full paste and the extra section |
| Day 1 | LinkedIn, morning US Eastern |
| Day 2 | Medium import, verify canonical in a browser |
| Day 2 | dev.to |
| Day 3 | Mastodon |
| Day 4 | Farcaster |
| Optional | Show HN, weekday morning, never alongside the LinkedIn push |

## Do not post

- **X / @RelayShieldHQ is suspended.** Not a channel.
- **Hashnode is retired permanently.** Never again.
- **HackerNoon is paywalled** for company-owned domains, and the review step itself sits behind the
  paywall, so there is no free path at all.

## After posting

One query answers whether any of it worked. Run it a week out:

```
fields @timestamp, @message
| filter @message like /developer-signup request/ and @message like /npm-worm/
| parse @message "source=*" as src
| stats count() by src
| sort by count() desc
```

A channel showing zero after a week is data about the channel, not a reason to post there again
harder. Four of five Telegram bot directories turned out dead or paid; the same discipline applies.
