# Indie Hackers: rsscan launch post

**Status:** DRAFT, pending founder review.
**Decision applied:** free tool only. **Bundle A is deliberately not mentioned.** It is a $150/mo
security-lead purchase and IH is developers without a security budget. Pitching it here is
off-strategy (funnel decision 6: do not spend the pitch on the developer) and turns a clean free-tool
post into a sales post, which that audience punishes.

---

## Where this goes, and in what order

IH has two surfaces and they are not interchangeable:

1. **A product page**: `indiehackers.com/products`, then **Add your product**. This is the directory
   listing. It is a profile, not a post: name, tagline, URL, description, revenue (you can leave
   this blank or set $0), and your founder profile as the maker. It gets you indexed; it does not
   get you readers on its own.
2. **A post**: the story below. This is what actually gets read. Post it from your profile and it
   surfaces in the feed and in the newsletter you already subscribe to.

**Do the participation first.** The consistent advice, and the thing that separates a post that
lands from one that gets ignored: a link drop from an account with no history is spotted
immediately. Spend a few days commenting genuinely on other people's posts *before* posting this.
One week of real participation changes how the launch is received.

**Sequencing for this specific post:** do not post until **rsscan 0.1.3 is live on PyPI and the
`v0.1.3` GitHub tag exists.** The post's whole credibility is that the install line works when
someone pastes it. This is the "announced before it existed" trap and it has bitten this project
before.

**Tagline for the product page:**
> A pre-commit hook that blocks secrets before they enter git history. Free, local, no account.

---

## The post

**Title:** We searched public GitHub for leaked AWS keys. All five top results were false positives.

I build a security API, and last month I wanted to know how bad the leaked-credential problem
actually is on public GitHub. So I searched for AWS access keys the way a scanner would.

The literal string `AKIA` returned 4,240 results. Adding a pattern that requires the key's actual
shape returned 119. A 36x difference, and the narrower one is the honest number.

Then I read the top five results by hand. All five were false positives:

- a docs table listing credential formats
- the literal placeholder `aws_access_key_id=AKIA....`
- a README describing which formats the tool redacts
- a link list
- a domain allowlist

Not one was a live credential. That surprised me enough to change what I was building.

**Why it matters more than it sounds.** A false CRITICAL is not free. It is a rotation that gets
scheduled, assigned, investigated, and cancelled. Do that a few times and the team stops believing
the scanner, which is the actual failure mode, because that is when the real one gets ignored.

So I made verification part of the tool rather than a nice-to-have: a hit only becomes a finding if
the matched value passes the credential's own format check. A docs example does not get reported at
you as a critical incident.

**The other decision, which I went back and forth on.** The obvious build is to POST the diff to an
API and scan server-side. Easier to update, gives you usage analytics, natural upsell.

I could not get past the objection I would have had myself: *why is my pre-commit hook uploading my
source code to a third party?* So the scanner runs entirely on the developer's machine. All 31
patterns ship inside the package. No account, no API key, no network call, no size cap.

That cost me the analytics and made the free tier genuinely free to run. My cost per scan is zero
because there is no scan endpoint. Adoption is worth more to me right now than telemetry.

**One design detail I got wrong first.** Failure behaviour should not be the same in both places.
A pre-commit hook that wedges every commit when something goes wrong gets uninstalled, and then it
catches nothing at all, so it fails *open*. A CI gate that reports success when it could not
actually run is worse than no gate, because it manufactures false assurance, so it fails *closed*.
I shipped both as the same thing initially and it was wrong in one of the two.

It is free and MIT-licensed:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/RelayShield/rsscan
    rev: v0.1.3
    hooks:
      - id: rsscan
```

Findings never include the secret value. You get a file, a line, and a non-reversible fingerprint, so it
is safe to run in CI without leaking the thing you are scanning for into the build log.

Happy to answer anything about the pattern set or the verification step. If you run it and get a
false positive I would genuinely like to see it. That is the number I care about.

---

## Notes for the founder

- **Every number is already verified**: 4,240 and 119 were re-measured live on 2026-08-03, and the
  five categories are the real ones. Do not re-quote 4,272, which was the older measurement.
- **Re-check the two figures the morning you post.** GitHub result counts drift, and the post's
  whole credibility is measurement.
- **No em-dashes or en-dashes** in the body, per house style. Hyphens in technical terms stay.
- This overlaps the published blog post. That is fine: IH readers are not the blog's readers, and
  the framing here is the build decisions rather than the research. Do **not** cross-post the blog
  text verbatim.
- Expect "how is this different from gitleaks/trufflehog?" in the comments. The honest answer for
  this audience is: for a pre-commit hook, not much, and it is free either way. The difference is
  the verification step and the five published-artifact sources beyond repos. Do not reach for the
  identity/Bundle A pitch in a comment reply; it reads as bait-and-switch on IH.
