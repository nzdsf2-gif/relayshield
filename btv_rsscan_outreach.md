# Blue Team Village: rsscan outreach

**Status:** DRAFT, pending founder review. Nothing has been sent.
**Decision applied:** free tool only. **Bundle A, the metered API and the intel corpus are
deliberately not mentioned.** BTV punishes vendor pitching harder than Indie Hackers does, and the
same logic as funnel decision 6 applies: do not spend the pitch on an audience with no budget
authority for a $150/mo security-lead purchase. One free tool, one link, no upsell.

---

## Channel: Discord, not the CFC

**DEF CON 34 ran 6 to 9 August 2026.** It finished nine days ago, so the Call for Content for DC34
is closed and a talk pitch has nowhere to land right now. Two live options:

1. **The Discord community** (`discord.gg/blueteamvillage`). This is the recommended route and the
   message below is written for it. Post-con is good timing rather than bad: people are back at
   their desks, the server is active, and there is no competing conference noise.
2. **`cfc@blueteamvillage.org`** for the DC35 Call for Content. **Verify whether it has opened
   before sending anything.** It was not open as of this writing. A tool demo or workshop is a
   plausible DC35 submission, but that is a decision for next spring, not this session.

**Participate before you link.** Same rule that governs the Indie Hackers post and for the same
reason: a link drop from an account with no history is spotted instantly, and in a defensive
security community it reads as marketing. Spend real time in the server first.

---

## Claim discipline: one thing to get right

The README's headline promise is "no account, no API key, no network call." That is true of the
secret scanner. **It is not true of `--deps`, which queries `registry.npmjs.org`.**

The live README already scopes this correctly ("no network call to RelayShield, and no telemetry").
The message below keeps that precision. **Do not let it get flattened into a blanket "no network
call" claim.** This audience reads tool claims adversarially, will run it and watch the traffic, and
one disprovable sentence costs more credibility than the post can earn. This is the same failure
mode as the 24-72h lead-time claim and the 5.6M indicator number.

Second gate: **the install line must work when someone pastes it.** rsscan is at **0.2.0** on PyPI
as of 13 August 2026 and the pin is `rev: v0.2.0`. Confirm that is still current before posting.

---

## The message (Discord)

> Hi all. I build a small free tool called rsscan and I think it fits what this server does, so I
> wanted to put it in front of people who will tell me if it is wrong.
>
> It is a pre-commit hook that blocks API keys and tokens before they enter git history. 31
> credential patterns: AWS IAM, GitHub PATs, Stripe, Slack, private keys, and the LLM provider keys
> that have started showing up in commits. It runs on your machine, matching locally against
> patterns shipped inside the package. No account, no API key, no telemetry, and your source never
> leaves the host.
>
> The reason it is a pre-commit hook and not a CI check: CI only sees the secret after the push, and
> at that point it is in history and has to be rotated even if you delete the commit. The CI
> integrations exist as a backstop, not a substitute.
>
> Newer bit that may be more interesting here. `rsscan --deps` reads your package-lock.json and
> counts how many distinct npm accounts can publish into your dependency tree, flagging the ones on
> personal webmail with no SSO or central revocation behind them. On one of my own projects that was
> 433 dependencies and 275 distinct publisher accounts. That is the blast radius number I had never
> actually seen written down anywhere. This one does hit the network, but only registry.npmjs.org.
> Nothing goes to me.
>
> Free, no signup, MIT. https://github.com/RelayShield/rsscan
>
> What I would genuinely like: tell me what it misses. The false-positive rate on secret scanners is
> the thing that gets them uninstalled, so if it fires on something dumb I want the fingerprint.

**Length check:** fits Discord's 2000-character limit with room to spare.

---

## What to expect, and how to answer it

- **"Why not gitleaks or trufflehog?"** Honest answer: those are more mature and broader. rsscan's
  narrower bet is the pre-commit position plus a low false-positive rate on machine credentials. Do
  not claim superiority, and do not dodge the question. Naming them first is more credible than
  waiting to be asked.
- **"Is this a funnel for a paid product?"** Yes, eventually, and say so plainly if asked. The tool
  is free, MIT and standalone, and there is no upsell inside it. Denying the commercial connection
  is the only answer that actually damages you here.
- **"What is the false positive rate?"** The measured GitHub search work is the strongest material
  available and it is defensible: literal `AKIA` returned 4,272 results against 119 for the
  scoped pattern, and the top five were all placeholders, docs and allowlists. Re-verify those
  counts before quoting them, they drift.

---

## Not doing, and why

- No mention of relayshield.net commercial pages, the metered endpoints, or the intel corpus.
- No DM campaign to BTV organisers. One public post in the right channel, then answer replies.
- No cross-post to other DEF CON village servers on the same day.
