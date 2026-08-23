# We said the numbers would drift. Three weeks later we re-ran them.

*Every number below was measured against the live APIs. The dates are stated because they matter.*

<!-- INTERNAL: publish everything from the rule below down to the NOT FOR PUBLICATION line.
     The italic line above is publishable; this comment and the plan at the bottom are not. -->

---

In August we published [a post about searching public GitHub for leaked AWS
keys](https://blog.relayshield.net/we-searched-github-for-leaked-aws-keys-five-of-five-were-false-positives).
The finding was that `"openai.com" AKIA` returned **4,240 hits**, and the top five results contained
**zero credentials**. One of them was a secret-scanning tool's own documentation.

We also said, in the post, that search result counts drift and that anyone quoting them should
re-run before trusting the number.

That is an easy thing to write and an annoying thing to honour. So here is the re-run.

## The same five queries, three weeks later

| Query | 2026-08-03 | `MEASURE` | Change |
|---|---:|---:|---:|
| `"openai.com" AKIA` | 4,240 | `MEASURE` | `MEASURE` |
| `"openai.com" AKIA[A-Z0-9]{16}` | `MEASURE` | `MEASURE` | `MEASURE` |
| Literal `AKIA` | `MEASURE` | `MEASURE` | `MEASURE` |
| Top-5 false-positive rate | 5 of 5 | `MEASURE` of 5 | `MEASURE` |

`MEASURE — write the finding here once the queries are re-run. Both outcomes are publishable: if
the counts moved substantially, that IS the drift thesis confirmed and the post writes itself. If
they held steady, the finding is that the ratio is stable and the false-positive problem is
structural rather than a bad week. Do not decide which story you want before measuring.`

The one number we can state without re-running is the one that has not changed: the reason those
hits are not credentials. A search engine matched a string. It has no opinion about whether the
string was a secret. That does not drift.

## The sixth source

When the first post went out, the hosted scan covered five surfaces: GitHub, npm, PyPI, Docker Hub
and Hugging Face. It now covers six. **Postman public workspaces and collections** joined the set.

Postman is a genuinely different shape of exposure and it is worth explaining why we bothered.

A leaked key in a repository is usually an accident of history — someone committed it, someone else
did not notice. A leaked key in a **public Postman collection is an accident of intent**. Somebody
built a working request, filled in a real token to test it, and published the collection so a
colleague could use it. The credential is not a stray artefact in the collection. It is the part
that made the collection work.

Repo scanning cannot see any of it. Neither can your pre-commit hook, because nothing was ever
committed.

| Surface | What a repo scanner misses there |
|---|---|
| npm | The `.env` published inside the tarball, not the repo |
| PyPI | Same, and it has no search API — org attribution has to be reconstructed |
| Docker Hub | Build args baked into an image layer |
| Hugging Face | Tokens in a model repo a data scientist pushed |
| **Postman** | **A live credential in a saved request, published on purpose** |

## Per-source false-positive rates

The first post measured false positives on one surface. The obvious question is whether the other
five behave the same way, and the answer matters: if false-positive rates are wildly different per
surface, a scanner that applies one verification standard across all six is wrong five times out of
six.

| Surface | Raw hits | Verified credentials | False-positive rate |
|---|---:|---:|---:|
| GitHub | `MEASURE` | `MEASURE` | `MEASURE` |
| npm | `MEASURE` | `MEASURE` | `MEASURE` |
| PyPI | `MEASURE` | `MEASURE` | `MEASURE` |
| Docker Hub | `MEASURE` | `MEASURE` | `MEASURE` |
| Hugging Face | `MEASURE` | `MEASURE` | `MEASURE` |
| Postman | `MEASURE` | `MEASURE` | `MEASURE` |

`MEASURE — run one scan per surface against a domain we control, with a sample large enough to be
worth quoting. State the sample size in the table. A false-positive rate over 20 hits is not a
rate, it is an anecdote, and this post's entire credibility is that we know the difference.`

`If the sample is too thin for some surfaces, publish the ones that are solid and say plainly which
were too thin. A four-row table with stated denominators beats a six-row table with two invented
rows, and the audience for this post is exactly the audience that will check.`

## What this means if you are buying a scanner

Three questions worth asking any vendor, including us:

1. **What is your false-positive rate, per surface, with the denominator?** A single blended number
   across six very different surfaces is a number designed not to be checked.
2. **Do you verify, or do you report search hits?** These are different products at the same price.
3. **Where do you look that a repo scanner does not?** If the answer is only "GitHub, but better",
   your pre-commit hook already covers most of the value.

The hosted scan runs across all six surfaces for a domain you own, with the verification pass, at
**$0.35 a call**. No subscription. If you want to check the claim before paying for it, that is
rather the point of pricing it per call.

---

## NOT FOR PUBLICATION — plan, checks and open items

### This post does not ship until the MEASURE blocks are filled

There are two of them and they are the entire post. A follow-up to a measurement post that contains
no new measurements is worse than not publishing: it retroactively weakens the first post, which is
currently our most linked piece.

- [ ] **Re-run the GitHub queries.** Record date, exact query strings and counts. Both outcomes are
      publishable — decide the framing after, not before.
- [ ] **Re-check the top five results** for `"openai.com" AKIA`. Record repo paths for audit,
      **do not publish them** — same rule as the first post. It is about scanning being hard, not
      about those projects being bad.
- [ ] **Measure per-surface false-positive rates** with real denominators. Drop any surface whose
      sample is too thin and say so in the post.
- [ ] **Confirm the six-source claim on the live developers page.** The API prices
      `/v1/payg/secret-scan` and `/v1/metered/secret-scan` at $0.35 described as six-source
      (GitHub, npm, PyPI, Docker Hub, HF, Postman). The developers page said **five**-source when
      verified on 2026-08-03. If the page still says five, fix the page before publishing a post
      that says six.
- [ ] **Confirm the canonical URL of part one** before linking it. The slug in `blog_posts.js` is
      `we-searched-github-for-leaked-aws-keys-five-of-five-were-false-positives` (published
      2026-08-03).
- [ ] Re-confirm `$0.35` is still the live price.

### Note on the GitLab angle

**Do not reintroduce it.** The GitLab admission and the regex-defect section were both cut from the
published version of part one, so a follow-up that references "the GitLab thread from last time"
points at something readers never saw. If we want to publish the GitLab material — that code search
is Premium-gated at both instance and project level, that we had advertised and billed for it, and
that we cut the feature rather than quietly fixing it — it is **its own post**, written from
scratch, not a callback.

That post is worth writing. Owning a billing mistake in public is rare enough to get linked on its
own merits. But it is a third post, not a section of this one.

### Ordering: this goes SECOND

Publish the **Agent Tesla emoji post first**, then this one, roughly a week apart.

The reasoning is about shelf life, not quality:

- The Agent Tesla post is a **news reaction**. Its value halves every few days and every vendor is
  covering the emoji trick this week. Published late, it is the fifteenth take.
- This post is **evergreen**. The drift re-run and the per-surface rates are just as good in three
  weeks as today, and it needs measurement work that has not been done yet.

Publishing this one first would mean rushing the measurements to beat a deadline that does not
exist, while letting the perishable post rot. Ship the perishable thing while it is fresh; give the
durable thing the time it needs to be right.

Both posts also share a spine, which is worth being deliberate about across the pair: **a matcher
that returns a confident number without checking its assumptions.** Agent Tesla defeats string
matching with emoji; case-sensitive label filters defeat themselves; search-hit scanners report
matches as findings. Same failure, three costumes. If the pair lands well, that is the series.

### Channels

Canonical `blog.relayshield.net` (via `hashnode_export/` + `build_blog.py`) → Medium (**import
with the canonical URL, do not paste**) → LinkedIn → Telegram → Farcaster → Mastodon.
**Not X** (suspended). **Not Hashnode** (abandoned 2026-07-29).

**LinkedIn is the highest-value channel for this one**, same as part one — lead with the buyer's
three questions, not the drift table. That audience is deciding whether to renew a scanner.

**Length limits:** Mastodon 500 · Farcaster ~1024 bytes · LinkedIn 3000 · Telegram 4096. Write each
short version to its own limit. Apply the no-dash rule to every short version.

**LinkedIn hashtags** (3–5): `#DevSecOps #SecretsManagement #ApplicationSecurity #SupplyChainSecurity #CISO`
**Mastodon** (3–4): `#infosec #devsecops #appsec #opensource`
**Farcaster:** post to `/security` and `/dev`; hashtags are not a thing there.
