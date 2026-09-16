---
title: "A file read is a credential theft. CVE-2026-85706 and what is actually in those files."
slug: a-file-read-bug-is-a-credential-theft-bug
date: 2026-09-16
---

# A file read is a credential theft. CVE-2026-85706 and what is actually in those files.

GitLab patched a critical path traversal in its repository commits API last Thursday, and
attackers were already using it. The reporting is Mathew J. Schwartz at BankInfoSecurity
([piece here](https://www.bankinfosecurity.com/in-the-wild-attacks-hit-popular-devsecops-platform-gitlab-a-40012)),
built on a [watchTowr advisory](https://www.linkedin.com/posts/watchtowr_watchtowr-intel-is-already-observing-in-the-wild-activity-7504127032608415744-8JqE),
a [Rapid7 alert](https://www.rapid7.com/blog/post/etr-cve-2026-85706-critical-gitlab-path-traversal-exploited-in-the-wild/),
and [GitLab's own patch release](https://docs.gitlab.com/releases/patches/patch-release-gitlab-19-3-2-released/).
CISA added it to the Known Exploited Vulnerabilities catalogue on Friday. Everything below rests on
their work, and if you self-host GitLab the patch matters more than the rest of this post.

The short version: an unauthenticated attacker can read arbitrary files off a self-hosted GitLab
server. CVSS 10.0. Patched in 19.3.2, 19.2.6 and 19.1.8. GitLab.com is already patched and
Dedicated customers need do nothing.

## The score is about the read. The damage is about what it reads.

A 10.0 describes the mechanism: no authentication, remote, full read. It does not describe the
outcome, and the outcome is the part worth planning around. watchTowr put it precisely: the
vulnerability lets an attacker "read local files and configs to obtain credentials, secrets and
sensitive information."

That is the whole game. Nobody exfiltrates a GitLab server because they want your Ruby source.
They want the things that let them come back later without a CVE. A file read is a credential
theft with an extra step, and the extra step is the one that expires when you patch. The
credentials do not expire when you patch.

So the question that decides how bad last week was for you is not "was I vulnerable". It is
**what was readable**.

## What is readable on a GitLab box

Two categories, and they fail differently.

**The server's own configuration.** The database password, the secret key base, the SMTP
credentials, the object storage keys, CI/CD variables. This is the application's own state. It is
not in your repositories and no pre-commit hook has ever touched it. If you were exposed, treat
all of it as public and rotate it, in the order below.

**Whatever your developers committed.** This is the other half and it is the half you control
before the next bug rather than after it. Every credential that was ever committed to a repository
on that server was readable by the same request. Not just the ones in HEAD: a commits API is, by
construction, a way to read history, and a secret deleted in a later commit is still sitting in an
earlier one.

The second category is where the blast radius gets strange. A GitLab token in a repository is not
one credential. A runner token executes CI. A deploy token writes to packages and containers. A
Kubernetes agent token reaches the cluster. An OAuth application secret impersonates your login
provider to every app that trusts it. One readable file can be lateral movement into three systems
that have nothing to do with GitLab.

## The honest scope of a pre-commit hook

We make a pre-commit secret scanner called rsscan, and this is exactly the kind of moment where a
vendor tells you their tool would have saved you. It would not have, and the distinction is worth
being precise about because it decides what you should actually do on Monday.

**rsscan cannot help with the first category at all.** It reads `git diff --cached`, your own staged
change, on your own machine, before the commit exists. It has no view of `gitlab.rb`, no view of
`secrets.yml`, no view of the CI variables in the database. A tool that runs on a laptop cannot
defend a server's config, and anyone telling you otherwise is selling you something.

**What it does is make the second category smaller.** A credential that never reaches a commit is
not in the history that the next file-read bug walks. That is not glamorous and it is not a
mitigation for CVE-2026-85706, which is already out. It is the thing that determines how much the
next one costs you, and there is always a next one: this same release carried seventeen other
fixes, including an insecure deserialization flaw at 9.9 that GitLab says could expose Advanced
Search configuration and credentials to an authenticated Duo Chat user.

Stating that plainly is the point. A control that reduces future blast radius is worth having.
It is not an incident response plan.

## The question to put to your own secret scanner

A detector reports what it has a pattern for, and "clean" and "we have never looked for this" are
the same output on the screen. So the question worth putting to whatever scanner you run, this
week specifically, is not how many patterns it carries. It is whether it carries the ones for the
platform you have just had to patch. That takes ten minutes to settle: generate a dummy token of
each shape, run them through, and see which ones come back named.

RelayShield covers eight GitLab credential formats, in all three of the places they have to agree,
with the token classes taken from gitleaks' own rule source rather than from a documentation page:
personal access tokens in both the classic and the newer routable format, deploy, runner, OAuth
application, Kubernetes agent, pipeline trigger and CI job tokens. The routable format has to be
tested first, because the classic pattern matches the first twenty characters of a routable token
and would otherwise report the wrong type with the wrong remediation.

## The other half: it has already left

Patching closes the door. It does not tell you whether anything walked out first, and that is a
different question with a different answer.

Credentials stolen from an exploited server do not sit still. They get tested, traded and posted,
and the places they get posted are observable. We collect indicators continuously from monitored
criminal Telegram marketplaces, infostealer log dumps and public indicator feeds, which is how you
answer "has this specific thing surfaced" rather than "was I theoretically exposed". For a
credential you know was readable, that is a more useful question than any scan of your own estate.

## What to do, in this order

The order matters more than the list, and getting it backwards is a real and common mistake.

**1. Patch or remove public access.** 19.3.2, 19.2.6 or 19.1.8. GitLab warns the updates include
database migrations, so single-node installations will have downtime and multi-node deployments
should use the zero-downtime procedure. If you cannot patch in the next few hours, take the
instance off the public internet instead. Rapid7 recommends treating this as an emergency change
outside normal patch cycles, and CISA set a federal deadline of Monday.

**2. Hunt before you assume you were fine.** Rapid7 is explicit that you should look for signs of
compromise even after updating. watchTowr named the specific thing to grep for: HTTP POST requests
to `/api/v4/projects/{id}/repository/commits/` URIs containing `file.path` parameters. Do that
before you conclude anything, because the alternative is concluding it from the absence of
evidence you never went looking for.

**3. Rotate, and only now.** This is the step people get out of order. Rotating credentials on a
server that is still readable hands the attacker the new ones and costs you the rotation. Patch,
then hunt, then rotate, starting with anything that grants access somewhere else: runner tokens,
deploy tokens, agent tokens, OAuth application secrets, then the server's own database and object
storage credentials.

**4. Then make the next one smaller.** Get secret scanning in front of the commit rather than after
it, and check that it covers the platforms you actually run. That is the only step on this list
that is about the next bug rather than this one, which is why it is last and why it is the one
that will still be paying off in a year.

---

The pre-commit hook is `pip install rsscan`, it runs offline on your staged diff, and it is free.
The corpus lookup for "has this already surfaced" is
`POST /v1/breach-check` at
[api.relayshield.net/developers](https://api.relayshield.net/developers?source=gitlab-cve-blog).
Neither will ever tell you something is safe. The ceiling is "nothing known against it", and the
response says so itself, because on the day a file-read bug is being exploited in the wild an
absence of evidence is the one thing nobody should be selling as reassurance.
