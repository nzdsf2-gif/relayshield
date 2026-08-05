# We searched public GitHub for leaked AWS keys. All five top results were false positives.

*Every number below was measured against the live APIs.*

<!-- INTERNAL: publish everything from the rule below down to the NOT FOR PUBLICATION line.
     The italic line above is publishable; this comment and the plan at the bottom are not. -->

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

---

## NOT FOR PUBLICATION — distribution plan

*(House style for this post: no em-dashes or en-dashes anywhere in the publishable body. Hyphens
inside technical terms are untouched and must stay: `pre-commit`, `secret-scan`, `SIM-swap`,
`pay-as-you-go`, `.pre-commit-config.yaml`. This internal section still uses em-dashes because it is
never published. Re-check the body if it is edited again.)*

### Pre-flight checks (do these first)

- [x] ~~**CTA banner.**~~ Done 2026-08-03. A dedicated `secret-scan` variant is registered and
      deployed, reachable only by explicit `?source=` (no host claims, so it can't collide with the
      LLMjacking variant that owns `blog.relayshield.net`). `blog`/`medium`/`linkedin`/`telegram`/
      `post` were deliberately **left** on llmjacking — the published LLMjacking post links with
      `?src=blog`, and repointing those would have misdirected its existing readers.
      **Use the per-channel keys when syndicating** so CloudWatch can tell the channels apart; all
      render the same banner:
      `secret-scan` (blog canonical) · `secret-scan-medium` · `secret-scan-linkedin` ·
      `secret-scan-telegram` · `secret-scan-farcaster` · `secret-scan-mastodon` · `secret-scan-hn`
- [x] ~~**Re-verify the 4,272 figure and the top-five results.**~~ **Re-measured live 2026-08-03
      against `api.github.com/search/code`, authenticated, `text-match+json`.**
      `"openai.com" AKIA` now returns **4,240** (down 32, 0.75% drift) — post updated in both places.
      **All five top results are still false positives, and each still matches its stated category:**
      1. docs table of env var names (`langwatch/better-agents/docs/USAGE.md`)
      2. literal `aws_access_key_id=AKIA....` placeholder (`mongodb/kingfisher/docs/ACCESS_MAP.md`)
      3. redaction tool's README listing formats it detects (`silentchainai/SILENTCHAIN/README.md`)
      4. curated link list (`BAILOOL/DoYouEvenLearn/README.md`)
      5. policy allowlist containing `"*.openai.com"` (`luckyPipewrench/pipelock/docs/policy-spec-v0.1.md`)
      Not one contains a credential. #3 is a secret-redaction tool's own docs, so the irony line
      still holds. Repo names recorded here for audit only — **do not publish them**, per the item
      below. If this is republished later, re-run before trusting the number again.
- [x] ~~**Confirm `rev: v0.1.2` is still current.**~~ Verified 2026-08-03: PyPI serves `0.1.2` and
      the latest GitHub release is `v0.1.2`. The pin in the post is correct.
- [x] ~~**Confirm the `$0.35` secret-scan price.**~~ Verified 2026-08-03 on the live developers
      page: `/v1/metered/secret-scan — $0.35 / call`, described as five-source coverage. Matches.
- [ ] Confirm the rsscan GitHub URL renders and the pre-commit block installs in a scratch repo.
- [ ] Don't name the five false-positive repos. The post is about scanning being hard, not those
      projects being bad, and naming them invites a pile-on they didn't earn.

### Canonical + syndication order

1. **`blog.relayshield.net`** — canonical. Publish here first via `hashnode_export/` + `build_blog.py`.
2. **Medium** — **use "Import a story" with the canonical URL. Do not paste.** Medium has no
   Markdown paste support and import sets the canonical link automatically in one step.
3. **LinkedIn** — the highest-value channel for this post. Security leads live there.
4. **Telegram** — existing channel, short version.
5. **Farcaster** — dev-heavy audience.
6. **Mastodon** — infosec community is genuinely active there.

**Do NOT post to X** — the `@RelayShieldHQ` account is suspended.
**Do NOT post to Hashnode** — abandoned 2026-07-29 after repeated silent AutoMod removals.

### Length limits (verified)

| Channel | Limit |
|---|---|
| Mastodon | 500 chars |
| Farcaster | ~1024 bytes |
| LinkedIn | 3000 chars |
| Telegram | 4096 chars |

Write each short version to its own limit. Do not force one 280-char draft onto all of them.
**Apply the no-dash rule to every short version too**, or the syndicated copies reintroduce what
was just stripped from the canonical post.

### Hashtags

**LinkedIn** (3 to 5 max; more reads as spam):
`#DevSecOps #SecretsManagement #ApplicationSecurity #SupplyChainSecurity #CISO`

**Mastodon** (infosec.exchange conventions — tags are the discovery mechanism, use 3 or 4):
`#infosec #devsecops #appsec #opensource`

**Farcaster** — hashtags are not really a thing; post to the **/security** and **/dev** channels
instead.

**Telegram / blog** — no hashtags.

### Angle per channel

*(Updated — the regex-defect section and the GitLab admission were both cut, so any older guidance
pointing at "part one" or the GitLab angle no longer maps to anything in the post.)*

- **LinkedIn:** lead with the **manager cost** — "every false CRITICAL is a rotation that gets
  scheduled, assigned, investigated and cancelled." Then the five-of-five proof. That audience buys
  on wasted-cycle arguments, and it lands on the identity differentiator.
- **Farcaster / Mastodon:** lead with **five out of five**. It is immediately legible to engineers
  and it is a claim they can go reproduce in thirty seconds, which is why it travels.
- **Telegram:** lead with the **free local tool** — that audience installs things. No account, no
  network call, MIT.
- **Blog:** full post, in order.

### Follow-on, after the post is live

- **TLDR InfoSec** (`tldr.tech/infosec`, NOT `/security`, which 404s) — pitch editorial. A genuinely free MIT tool plus a real
  measured finding is a strong fit, and much stronger with a live install link and a published URL
  to reference. Scoped as BA-4 in TODO.
- **Show HN** — five-out-of-five is the HN-shaped part. Title it as the finding, never as the
  product.
- Watch arrivals in CloudWatch to see whether the post converts:
  ```
  fields @timestamp | filter @message like /developer-signup request/
  | parse @message "source=*" as src | stats count() by src | sort by count() desc
  ```
