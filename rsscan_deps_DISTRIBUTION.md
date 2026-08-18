# `rsscan --deps` release: distribution

*Written 2026-08-13. Channels decided by the founder today: Hugging Face, Medium, LinkedIn,
Telegram, plus our own Discord `#announcements`. Hacker News and Reddit deliberately not selected.*

**House rule: no em-dashes, en-dashes or ` -- ` in any copy below.** Hyphens inside technical terms
stay (`package-lock.json`, `pre-commit`, `--deps`). Re-check if you edit a block.

---

## Publish order, and the two hard preconditions

Nothing goes out until both of these are true.

1. **rsscan 0.2.0 is on PyPI. STILL FALSE as of 2026-08-13 12:50 UTC.** Every piece of copy below
   says `pip install rsscan` and then `rsscan --deps`. If 0.2.0 is not published, the first thing
   every reader does is get `unrecognized arguments: --deps`, and there is no recovering that first
   impression.

   Built and validated, not uploaded. `dist/rsscan-0.2.0-py3-none-any.whl` and
   `dist/rsscan-0.2.0.tar.gz` both pass `twine check`, and the wheel was installed into a clean venv
   where `rsscan --version` reports `0.2.0` and `rsscan --deps` reproduced the express numbers
   exactly (65 / 85 / 46 / 11). **The upload needs the founder's PyPI token and has to be run by the
   founder.** See the command block below.

2. ~~**`relayshield_developer_signup.py` is deployed.**~~ **DONE 2026-08-13.** Deployed twice
   (12:40 and 12:45 UTC) and verified against the live endpoint, not just the deploy result. All
   seven CTA keys render, plus the two added later for dev.to and Mastodon, and the two pre-existing
   keys (`rsscan`, `npm-worm-hf`) did not regress.

### The PyPI upload, for the founder to run

There is no `~/.pypirc` and no `TWINE_*` in the environment, so twine will prompt. **Let it prompt.**
Do not put the token on the command line or in an environment variable in a shell that keeps
history: a static PyPI token is precisely the credential class rsscan itself detects.

```bash
cd "/Users/andrewgibbs/Side SaaS Hustle/rsscan" && ~/anaconda3/bin/python -m twine upload dist/rsscan-0.2.0*
```

Username is `__token__`, password is the `pypi-...` token. A **project-scoped** token is fine here:
the account-scoped requirement only applies to a package's very first publish, and `rsscan` has
existed since 0.1.0.

Verify after upload, in a fresh venv rather than the build one:

```bash
python3 -m venv /tmp/rsv && /tmp/rsv/bin/pip install -q rsscan==0.2.0 && /tmp/rsv/bin/rsscan --version
```

Then, in order:

1. Canonical post on `blog.relayshield.net`
2. Hugging Face article (full paste, the only channel that gets the model-token section)
3. Medium (**import, do not paste**)
4. LinkedIn (reframed, not the same post)
5. dev.to (paste with `canonical_url`, model-token section dropped)
6. Mastodon
7. Telegram
8. Our Discord `#announcements`

---

## Also update these version references before release

`README.md` still pins the old version in four install snippets, and a reader copying them gets
0.1.3, which has no `--deps`:

- pre-commit `rev: v0.1.3` becomes `v0.2.0`
- GitHub Action `RelayShield/rsscan@v0.1.3` becomes `@v0.2.0`
- GitLab `image: relayshield/rsscan:0.1.3` and the two Docker examples become `0.2.0`
- the webhook payload example showing `"version": "0.1.3"`

The CircleCI orb is at its own version (`@0.1.0`) and is a separate publish. Leave it unless the orb
is republished.

Also needed: a git tag `v0.2.0` (the pre-commit `rev:` and the Action both resolve against tags), a
Docker Hub push, and the public repo re-export, since `rsscan/` is tracked in the parent repo and the
public repo is built from a clean export rather than being the same tree.

---

## Canonical

**Source:** `blog_source/rsscan-deps-who-can-publish-into-your-dependencies.md`
**Slug:** `rsscan-deps-who-can-publish-into-your-dependencies`
**CTA in the post:** `?source=rsscan-deps`

### Metadata

- **Display title**: rsscan --deps: Nearly Half of Your Dependencies' Publishers Are on Personal Gmail
- **SEO title** (~60 chars): Who Can Publish Into Your npm Dependencies?
- **Meta description** (150 limit): A typical app installs 433 packages. 275 accounts can publish into them and 126 are on personal Gmail. We released a free tool that counts yours.
- **Cover image**: none. A bar showing 275 accounts split into 126 personal / 121 org / 28 role would
  carry the argument. Do not block publishing on it.

### The numbers, and where they came from

Reproducible by anyone. `npm install --package-lock-only --ignore-scripts` to generate each lockfile,
then `rsscan --deps`. Measured 2026-08-13.

| Install | Packages | Publisher accounts | Consumer webmail | Role/automation | Unresolved |
|---|---|---|---|---|---|
| `npm i express` | 65 | 85 | 46 (54%) | 11 | 0 |
| `npm i webpack` | 67 | 95 | 40 (42%) | 12 | 0 |
| `npm i eslint` | 68 | 101 | 51 (50%) | 14 | 0 |
| `npm i jest` | 289 | 208 | 96 (46%) | 19 | 0 |
| `npm i next` | 54 | 29 | 10 (34%) | 4 | 0 |
| all nine together | **433** | **275** | **126 (46%)** | 28 | 0 |

118 of the 126 are literally `gmail.com`. Zero GitHub `noreply` addresses landed in that count,
which I checked specifically before publishing, because a webmail figure inflated by privacy-masked
addresses is the first thing a hostile reader would find.

**Do not round 46% to "about half" in a headline.** It is 45.8%, and the precision is the credibility.

---

## 1. Hugging Face

**This is the channel the article was shaped for**, because HF only accepts two kinds of post: an AI
science or engineering piece, or **the release of an open source artifact**. `rsscan` is MIT
licensed and a new capability in it qualifies under the second. The npm worm post does not qualify
at all, since it announces a paid closed API, and posting it here would have been rejected or
ignored.

We have HF PRO, so there is no paywall. **We also have 0 followers, so this has no organic feed
reach.** Its value is that it is durable and indexed. Do the article; skip the HF Post.

**Full paste, not an import.** The model-token section below exists nowhere else and a canonical
import would not carry it.

### Front matter

```yaml
---
title: "Who Can Publish Into Your Dependencies?"
thumbnail: /blog/assets/rsscan-deps/thumbnail.png
authors:
- user: relayshieldadmin
---
```

### Edit 1: canonical line, immediately under the title

```text
*Originally published at [blog.relayshield.net](https://blog.relayshield.net/rsscan-deps-who-can-publish-into-your-dependencies).*
```

### Edit 2: the CTA link

Change the `/developers` link in the closing section to `?source=rsscan-deps-hf`.

### Edit 3: keep the model-token section

The section titled **"If you ship models, this is the same problem wearing different clothes"** is
already in the canonical source file. On HF it is the reason to be there at all. Do not trim it for
length.

### Also do this

Cross-link the Space, because a working thing beats a description:

```text
The related identity check runs free on our Space, no API key:
https://huggingface.co/spaces/relayshieldadmin/relayshield-agentic-attack-surface
```

---

## 2. Medium

**Import, do not paste.** Use Medium's import tool against the canonical URL, which sets the
canonical tag automatically and avoids the duplicate-content problem. Pasting has bitten us before.

After import, change the one CTA link to `?source=rsscan-deps-medium`.

The model-token section can stay or go on Medium; it does no harm and the audience is mixed.

---

## 3. LinkedIn: a different post, not this one

**The article opens with `pip install`, which is the wrong lead here.** LinkedIn is where the
security lead sits, and per the founder-approved funnel that is the layer with budget. The developer
already gets the tool for free; this audience is being sold the question, not the CLI.

**LinkedIn suppresses posts carrying an external link, so the number carries the post and the link
goes in the first comment.**

```text
A question worth asking your team this week: how many people can publish code into your production build?

Not how many dependencies you have. How many human beings hold credentials that let them push a new version into your tree.

We measured a completely ordinary install. Next.js, React, TypeScript, ESLint, Jest, axios, Tailwind, Prettier, dotenv. Nothing exotic.

433 packages.
275 distinct accounts that can publish into them.
126 of those accounts are on consumer webmail. 118 are Gmail.

Nobody in that sentence is doing anything wrong. That is what makes it a supply chain problem rather than a negligence problem. Open source gets published by people on their own machines, with their own accounts, largely for free, and then the rest of us put it in production.

Why the 126 is the number I would take to a risk committee: a publish credential on a company domain sits behind SSO, and when that person is compromised there is an IT function that can revoke it centrally. A publish credential on a personal Gmail has no offboarding, no central revocation, no device management and no security team.

And this is the part your SCA tool structurally cannot answer. It reads the artifact. It is very good at that. But a self-replicating npm worm does not start with malicious code, it starts with a maintainer account and an infostealer, four steps before there is anything for a scanner to find.

We released the counting tool free and open source this week, so you can run it against your own lockfile in about a minute. Link in the comments.

#supplychainsecurity #devsecops #cybersecurity
```

**Three hashtags, at the end, and no more.** LinkedIn deprioritised hashtags when it removed hashtag following, so they do far less for reach here than on Mastodon, and a stack of them reads as spam to the senior audience this post is aimed at. Two or three are free and still help categorisation: one specific to the content, one practice area, one broad.

**None in the first comment.** That comment exists to carry the link, and hashtags there just dilute it.

**First comment:**

```text
Free, MIT, runs locally and sends us nothing:

pip install rsscan && rsscan --deps

Full write-up with the methodology and all six measurements: https://blog.relayshield.net/rsscan-deps-who-can-publish-into-your-dependencies

And if the follow-on question is "are any of those accounts actually compromised right now", that is the paid part: https://api.relayshield.net/developers?source=rsscan-deps-linkedin
```

---

## 4. Telegram

Short, one link, no thread.

```text
How many people can publish code into your production build?

We measured an ordinary install: Next.js, React, TypeScript, ESLint, Jest, axios, Tailwind, Prettier, dotenv.

433 packages. 275 accounts that can publish into them. 126 of those on consumer webmail, 118 of them Gmail.

Nobody is doing anything wrong there. It is just how open source gets published, and it is invisible to every tool that reads the artifact instead of asking who can replace it.

The counting tool is free, MIT, and runs entirely on your machine:

pip install rsscan && rsscan --deps

Write-up, with the method so you can reproduce every number:
https://blog.relayshield.net/rsscan-deps-who-can-publish-into-your-dependencies
```

Use `?source=rsscan-deps-telegram` on any `/developers` link if you add one.

**Reminder from prior sessions:** force `LC_CTYPE` when using `pbcopy` for Telegram, or the UTF-8
gets mangled on paste.

---

## 5. dev.to

**Good fit, and the cheapest one on this list.** Developer audience, tool releases are native
content there rather than tolerated self-promo, and it supports `canonical_url` in front matter so
there is no duplicate-content cost.

**Paste the body**, with this front matter. The canonical tag is what makes pasting safe here.

```yaml
---
title: "Who can publish into your dependencies?"
published: true
canonical_url: https://blog.relayshield.net/rsscan-deps-who-can-publish-into-your-dependencies
tags: security, npm, opensource, devops
---
```

Change the CTA link to `?source=rsscan-deps-devto`.

**Drop the model-token section on dev.to.** It is the reason to post on Hugging Face and it is dead
weight for an audience that mostly does not ship models. Everything else stays.

dev.to's four-tag limit is real, and `security` plus `npm` are the two that actually route it.

---

## 6. Mastodon

**Decent fit, specifically for the infosec instances.** Practitioner audience, no algorithmic
suppression of links the way LinkedIn has, and a reproducible number is the kind of thing that gets
boosted there. Low effort, small but real reach.

Post from the account on whichever instance we hold. This is a link post; the number does the work.

```text
A completely ordinary npm install: Next.js, React, TypeScript, ESLint, Jest, axios, Tailwind, Prettier, dotenv.

433 packages.
275 distinct accounts that can publish into them.
126 of those on consumer webmail. 118 are Gmail.

Nobody in that sentence is doing anything wrong. It is just how open source gets published, and it is invisible to every tool that reads the artifact instead of asking who can replace it.

We released the counting tool free and MIT. Runs locally, sends nothing:

pip install rsscan && rsscan --deps

Method and all six measurements:
https://blog.relayshield.net/rsscan-deps-who-can-publish-into-your-dependencies

#infosec #npm #supplychain #opensource
```

Use `?source=rsscan-deps-mastodon` on any `/developers` link.

**Two mechanical reminders from prior sessions.** Force `LC_CTYPE` when using `pbcopy` or the UTF-8
gets mangled on paste. And check the character limit on the specific instance before posting: 500 is
the default but infosec.exchange and several others run higher, and the block above is over 500.

---

## 7. Our own Discord `#announcements`

**This is not distribution.** The server has two members and is two days old, so there is nobody to
reach. It is the maintenance signal that the top.gg listing depends on: an admin who clicks
"Support Server" on a public listing and finds an empty server has been answered on whether this is
maintained, in the wrong direction.

**The deadline is the listing going live, not today.** Get these two posts in before top.gg
approves and that invite is on a public page.

### This part is manual, and has to be

**The bot holds zero permissions in that server, deliberately**, which is why it cannot create the
channel or post for you. That is the same reason it could not rename the server. Keep it that way:
"this bot requests no permissions" is one of the strongest lines in the listing copy and it stops
being true the moment we grant it something for convenience.

### Creating the channel, click by click

1. Open the **RelayShield** server in the Discord app.
2. Hover the channel-list header and click the **+** icon, or right-click empty space in the channel
   list and choose **Create Channel**.
3. **Text Channel**, name it `announcements`, lowercase, no `#` (Discord adds that itself).
4. Do **not** tick "Private Channel". It should be publicly readable; the restriction we want is on
   *posting*, not on reading, and that is the next step.
5. Click **Create Channel**.

### Making it read-only, which is the step that matters

Without this, anyone who joins can post in it, and an announcements channel a stranger can post a
scam link into is worse than no announcements channel. For a security vendor it is the worst
possible screenshot.

1. Hover `#announcements`, click the **gear** icon (Edit Channel).
2. **Permissions** in the left sidebar.
3. Under **Roles/Members**, select **@everyone**.
4. Set **Send Messages** to the red **✗**.
5. Leave **View Channel** and **Read Message History** as the green **✓**.
6. **Save Changes**.

You keep posting rights through your own admin role, which sits above @everyone.

### Posting the two stories

Post them as **two separate messages**, npm worm first since it is the older story. Two dated
entries read as a channel where things get posted; one reads as a channel someone set up.

Discord's message box sends on Enter, so use **Shift+Enter** for the line breaks inside each post,
or paste the whole block at once.

The `**bold**` markers in the copy below are Discord markdown and will render as bold. Leave them in.

**Do not write "today" or "just published" on the npm worm post.** It went up 2026-08-12. A late
cross-post is completely normal; implying it is fresh when it is not is the one thing that would
actually cost credibility in a channel whose entire job is looking honest.

After posting, **right-click each message and Pin** it. A two-message channel does not need pins for
navigation, but pinned messages survive being scrolled past and it costs nothing.

**Post 1, npm worm (published 2026-08-12):**

```text
**Why we built the dependency checks: the npm worm does not start with malicious code**

A self-replicating npm worm starts with a maintainer account, not with a malicious release. An infostealer takes the publish token out of somebody's .npmrc, and a patch version nobody reads ships four steps before there is any artifact for a scanner to analyse.

https://blog.relayshield.net/the-npm-worm-does-not-start-with-malicious-code
```

**Post 2, the release:**

```text
**Released: `rsscan --deps`, free and MIT licensed**

It counts the accounts that can publish into your npm dependencies. We ran it on an ordinary install of Next.js, React, TypeScript, ESLint, Jest, axios, Tailwind, Prettier and dotenv: 433 packages, 275 accounts that can publish into them, and 126 of those on consumer webmail.

Runs locally, no account, no API key, and it sends us nothing.

pip install rsscan && rsscan --deps

https://blog.relayshield.net/rsscan-deps-who-can-publish-into-your-dependencies
```

Then do the lockdown pass that `discord_support_server_setup.md` does not cover, before the invite is
public anywhere: `#announcements` read-only, posting restricted in `#start-here`, `@everyone`
mention permission off for non-admins, slowmode on the open channels. A scam link sitting
unmoderated in the scam-prevention company's own server is the worst screenshot we could hand
anyone.

---

## What is deliberately NOT in this plan

- **Hacker News and Reddit**, not selected by the founder today. Worth noting for later that an
  MIT-licensed CLI with a reproducible surprising number is close to ideal Show HN material, and
  that the decision to keep the org signal opt-in removes the single most likely reason an HN thread
  would have turned hostile.
- **dev.to, Mastodon, Farcaster.** Available, not chosen.
- **@RelayShieldHQ on X.** Suspended.
- **Solana Mobile Discord.** Wrong audience for this artifact, and it has its own separate post for
  the bot this week. Two asks into one server gets both ignored.
