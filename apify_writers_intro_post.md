# Pre-call intro for `#apify-writers`

**Status: ready to post. This is NOT a submission** and it does not spend anything.
The July Typeform is closed and the next call opens in November; posting an
introduction while a call is closed is normal in that channel, and a developer
did exactly this on 2026-09-04 without being told off.

**What it is for:** getting the dev.to publishing question answered, and being a
name the reviewers have already seen when the November call opens. It also asks
the one thing we cannot find out ourselves, which is how the dev.to access works.

**Two decisions inside it, both deliberate:**

1. **It does not link a draft.** The other poster linked a public Google Doc. Ours
   asserts three facts from the Apify console that no session has verified
   (the runs figure, the Standby configuration, the dependency pins as they stand
   today), and linking a draft that gets one of them wrong is a worse first
   impression than linking nothing. Offer the draft, send it once it is checked.
2. **It does not quote the run count.** 154 is small enough that a reviewer may
   read it as a toy, and "in production since August" says the part that matters
   without inviting the comparison.

---

## POST THIS (copy from here down)

Hi! I'm the developer behind the `relayshield-security-tools` Actor. It runs
breach, infostealer and SIM-swap checks as an MCP server over Streamable HTTP, in
Standby mode, and it has been in production since August.

I have a finished draft for the "your Actor as a tool for AI agents" theme. It is
about two decisions that were not obvious to me when I built it:

- **Why Standby rather than run-per-request.** An agent calling a tool expects a
  response in the time it takes to answer a question, not the time it takes to
  boot a container, and that difference changes what the Actor is usable for.
- **A dependency conflict that crash-looped every real run**, which took a while
  to see because it only appeared under load. `apify>=2,<3` pulls a Crawlee whose
  `HttpHeaders` model dies against the Pydantic that FastMCP needs, failing at
  import with "cannot specify both default and default_factory". The fix was to
  go forward to `apify>=4,<5`, not back, and that is the part I would have wanted
  to read before spending the day on it.

It is around 1,300 words with the wire-level detail included rather than
paraphrased.

I can see the July Typeform is closed and that the next call opens in November,
so I am not submitting yet. Two questions in the meantime:

1. The pinned message mentions $100 in Apify credits for articles published on
   dev.to under the Apify organisation. How does that access work, and is it
   something to sort out before or after the article is accepted?
2. Happy to send the draft for early review if that is useful ahead of the call.
   If you would rather see it through the Typeform in November, that is no
   problem and I will wait.

Thanks!

## END OF POST

---

## NOT FOR PUBLICATION

**Before the November Typeform, confirm these three with the console open.** The
article asserts them and no session has verified them directly:

1. **The runs figure**, and whether to quote it at all. Currently left out of both
   this post and the draft, deliberately.
2. **The Standby configuration** (memory, timeout), if we want to quote it. The
   draft currently does not.
3. **The dependency versions as they stand today.** The `apify>=2,<3` to
   `apify>=4,<5` story comes from a Dockerfile comment dated 2026-08-25. If the
   pin has moved, both this post and the article move with it. **This post states
   the pins as fact, so it is the first thing to re-read before posting.**

**The disqualifier, unchanged:** the article must not appear on
`blog.relayshield.net`, Medium or dev.to before Apify publishes it. Originality is
a programme rule and it is about prior publication. Submitting is not publishing;
posting this introduction is not publishing either.

**After they publish**, the $100 dev.to version under their organisation is a
post-publication republish, so the usual canonical-first channel order resumes
then, not before.
