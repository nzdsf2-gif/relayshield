# Blue Team Village: the rsscan post

*Written 2026-08-13, after reading their `#posting-guidelines` in full.*

---

## The rule that decides everything here

BTV's posting guidelines name what belongs and what gets you warned.

**Explicitly welcome:**

> news and information about **Blue Team tools and research**

**Explicitly forbidden:**

> Posts that **advertise or sell commercial products or services, including training**

**So rsscan is postable and the API is not.** rsscan is free, MIT licensed, open source, runs
entirely locally and sends nothing anywhere. That is squarely "blue team tools and research."

**The moment the post mentions dependency-risk pricing, Bundle A, or anything with a number and a
dollar sign, it becomes a commercial post and it is against the rules.** That line is not a
judgement call and it is not worth testing. Improper posts are removed and the poster is warned.

There is no clever way around this, and trying would be worse than not posting: this is a
practitioner community where the founder wants standing for years, not a click today.

## Channel

**`#tools`.** It exists and it is exactly what it is for.

`#vulnerability-mgmt` and `#sec-eng` are reasonable alternatives if the framing leans toward the
research finding rather than the release. **Do not cross-post to all three.**

`#ai` is a genuine fit for the model-token half of the argument, but save it. One post, one channel.

## Also worth knowing

Their guidelines open with: *"We recommend that all new members hang out for a bit before posting."*
The founder has been a member for a while but has not posted. Reading `#tools` for a few days first
costs nothing and is the difference between arriving and showing up.

---

## The draft

**Lead with the finding, not the tool.** Defenders respond to a number with a method attached.
Everything here is reproducible by the reader in about a minute, which is the whole reason it earns
its place in a practitioner channel.

```text
Released a small thing this week that came out of looking at npm worm mechanics, and the number surprised me enough to share it.

Install Next.js, React, TypeScript, ESLint, Jest, axios, Tailwind, Prettier and dotenv into an empty directory. 433 packages. Behind those 433 packages are 275 distinct accounts that can publish into them, and 126 of those are on consumer webmail. 118 of the 126 are gmail.com.

Nobody in that sentence is doing anything wrong. It is just how open source gets published. But it means a publish credential for a chunk of your tree sits on a personal account with no SSO, no central revocation and no device management, which is exactly the account an infostealer monetises.

The tool that counts it is free and MIT:

pip install rsscan && rsscan --deps

It reads package-lock.json locally, resolves each package to its maintainers plus the _npmUser who actually published the version you have, and prints counts. No account, no API key, no telemetry, and the only host it contacts is registry.npmjs.org.

Two things it deliberately does not do: it does not screen anyone, and it names nobody. It prints integers. Packages it could not resolve are counted separately rather than folded into the totals, because a package whose publishers you could not look up is not a package with no publishers.

Method if you want to reproduce the numbers: npm install --package-lock-only --ignore-scripts to generate the lockfile, then rsscan --deps over it.

https://github.com/RelayShield/rsscan
```

## What was deliberately left out, and why

- **No pricing, no API, no bundle, no "we also sell".** Forbidden by their guidelines, and naming it
  would undo the reason the post is welcome.
- **No link to the blog post.** The GitHub repo is the artefact a defender wants. A marketing domain
  in a practitioner channel reads as the thing the guidelines prohibit even when the content is fine.
- **No claim rsscan detects worms.** It counts publisher accounts. Overclaiming to this audience is
  the fastest way to lose them.
- **No mention of the Discord bot.** Wrong audience, and a second ask halves the first.

## If someone asks "can you tell me if any of those accounts are compromised?"

That question is the entire funnel and **it has to come from them.** When it does, answer it plainly
and once: yes, that is a paid thing we do, here is what it checks, and here is the honest limit.
Answering a direct question is not advertising. Volunteering it first is.

## Related

- `discord_server_targets.md` for why practitioner communities are contribute-first.
- The CFP is closed: DEF CON 2026 ran 7 to 9 August and Blue Team Con's CFP closed 20 April.
  Next windows are roughly March to April 2027 (Blue Team Con) and up to mid-May 2027 (BTV).
