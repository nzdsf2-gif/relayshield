# We turned a security API into an Apify Actor that AI agents can call, and the hard part was a dependency

Most Actors are built to fetch something. Ours is built to answer a question, and the caller is not
a person. `relayshield-security-tools` runs on Apify as an MCP server over Streamable HTTP, so an AI
agent can ask it whether an email address shows up in breach data, whether an MCP server it is about
to connect to is a typosquat, or whether a set of credentials is already circulating in criminal
infostealer logs. It has answered 154 runs so far.

This is a write-up of what that took: why an Actor was the right host for it, why Standby mode is
the only mode that makes sense when the caller is an agent, and the dependency conflict that
crash-looped every real run until we pinned our way out of it. That last one cost the most time and
is the most transferable, so it gets the most space.

## Why put an MCP server on Apify at all

We already run the underlying API on AWS Lambda behind API Gateway. So the obvious question, and
the one an Apify reviewer should ask, is why an Actor exists at all.

Three reasons, in ascending order of how much they mattered.

**Distribution.** Apify Store is a place where people go looking for tools, and increasingly for
tools an agent can call. Our API is discoverable if you already know to look for a security API.
The Actor is discoverable if you are browsing for something that plugs into what you already run.

**The pricing model fits per-call security checks exactly.** Pay per usage is how our API is priced
anyway: a breach check is a fixed unit of work, and an agent calling it a hundred times costs a
hundred times as much. There is no seat, no minimum and no subscription to reconcile. Aligning the
Actor's pricing with the underlying product meant no second billing model to explain.

**MCP is the interface agents already speak.** Exposing the same checks as MCP tools means an agent
does not integrate with us. It discovers a tool, reads the schema, and calls it. That is a much
lower bar than "read our REST docs and write a client", and it is the reason to build an Actor
whose output is an answer rather than a dataset.

## Standby, not run-per-request, and the reason is latency

Apify's default model is a run: something starts, does work, produces a dataset, and finishes. That
is right for scraping and wrong for a tool an agent calls mid-reasoning.

An agent asking "is this MCP server a typosquat" is inside a chain of thought with a user waiting at
the end of it. A cold start plus a container boot plus the check is not an answer, it is a timeout.
The whole value of the check is that it lands before the agent acts on the thing it just checked.

Standby mode fixes the shape: the Actor is already up, holding an HTTP server, and a request hits an
endpoint rather than starting a run. Our Dockerfile wraps a stdio MCP server so it is served over
Streamable HTTP, which is the transport an MCP client can hold open.

The design consequence worth stating plainly: **if you are building an Actor as a tool for agents,
decide the transport before anything else.** Everything downstream, including the dependency problem
below, follows from serving HTTP rather than producing a dataset.

## The dependency conflict that crash-looped every real run

Here is the part that took the longest and the part I would want to read.

The Actor packages our Python MCP server, which is built on FastMCP. FastMCP needs a current
Pydantic. The Apify Python SDK, at the major version we started on, pulls in Crawlee, and the
Crawlee version it pulls has an `HttpHeaders` model that is not compatible with that Pydantic.

The failure looks like this, at import time:

```text
cannot specify both default and default_factory
```

Pydantic raises it while building Crawlee's `HttpHeaders` model. Nothing in that sentence mentions
Apify, FastMCP, or anything you wrote. It is a model definition in a library you did not choose,
pulled by a library you did choose, failing against a version of a validation library that a third
library required.

Two things made it expensive:

**It is an import-time failure, so it kills the process before your code runs.** In Standby mode
that means the container comes up, fails to import, and restarts. Then does it again. A build that
succeeds and a container that crash-loops look very different in the Apify UI, and the build being
green sends you looking in the wrong place first.

**It did not reproduce in a trivial test.** A quick local import of the SDK on its own is fine. The
conflict only appears with the full dependency set resolved together, which is to say in the built
image, which is to say after a build. Our verification note from the day we settled it reads:
`apify>=2,<3` crash-loops 100 percent of real Standby runs.

**The fix was a major version forward, not a pin backward.** `apify>=4,<5` pulls `crawlee>=1.x`,
which is built against current Pydantic and imports cleanly. That is counterintuitive if your
instinct with dependency conflicts is to pin older and narrower. Here the older pin was the problem
and the newer major version was the resolution.

The lesson generalises past Apify: **when a transitive dependency fails at import, check whether the
library you are pinning is holding back a dependency that has already fixed the incompatibility
upstream.** Pinning narrow is a reflex, and it is sometimes exactly backwards.

## Build from source, not from the published release

One more thing that reads as a detail and is not.

The Actor's Dockerfile builds our MCP server from the repository's own source, not from the version
published to PyPI. The published package is pinned to an older release aimed at a different use
case: a plain stdio container that a desktop client launches. The Actor needs whatever is on the
branch, wrapped for HTTP.

If we had built from the published release, the Actor would have silently shipped an older tool
surface than our own API supports, and the mismatch would have surfaced as an agent calling a tool
that our docs describe and the Actor does not have. That is a bad failure: it looks like the agent
is wrong.

**Decide deliberately whether your Actor tracks your published package or your repository**, and
write the reason in the Dockerfile where the next person will find it. Ours is three lines of
comment above the `COPY`, and it has already saved one wrong assumption.

## What we would tell someone else building an Actor as an agent tool

1. **Pick Standby if a human is waiting at the end of the call.** A run is the right primitive for
   producing data and the wrong one for answering a question.
2. **Resolve your dependencies in the image, early, before you write features.** The conflict above
   would have cost an hour on day one and cost considerably more on day four.
3. **Make the tool schema the product.** An agent reads names and descriptions and decides from
   them. A tool called `check` with a vague description will not be called; one that says exactly
   what it answers will be.
4. **Never let the tool throw at the caller.** An agent that gets an exception has no recovery path
   and will usually drop the tool entirely. Ours returns a structured "unknown" verdict on every
   failure path, including timeouts and rate limits, so a bad minute on our side degrades the
   answer instead of breaking the agent.
5. **Never let the tool overclaim.** Ours will say "nothing known against this" and will not say
   "safe". An absence of evidence is not proof, and an agent will repeat whatever word you give it
   to a user who cannot check.
6. **Align the Actor's pricing with the underlying product.** Pay per usage matched what we already
   charge per call. If they had disagreed we would have had two stories to explain, and the second
   one always gets explained badly.

## The honest limits

The Actor is a wrapper around a hosted API, so it is only as available as that API. If our Lambda is
down, the Actor returns unknown verdicts, which is the correct behaviour and still not an answer.

The checks are point-in-time. A clean result means nothing was found in the sources we queried at
that moment, and a corpus is not the world.

And Standby costs money to sit up. That is fine when call volume is steady and worth watching when
it is not: an Actor that answers three questions a day is cheaper as a run than as a resident
server.

---

*RelayShield's Actor is `relayshieldadmin/relayshield-security-tools` on Apify Store. It exposes
breach, SIM swap, infostealer, MCP registry risk, prompt injection breach, LLMjacking and secret
scanning checks as MCP tools over Streamable HTTP.*

---

NOT FOR PUBLICATION

## Internal plan and checklist

**Programme rules, confirmed 2026-09-03 from Apify's own page:**

- $500 per published article, on the Apify or Crawlee blog.
- 1,000 to 5,000 words. This draft is around 1,300, so it clears the floor with room to grow if a
  reviewer wants more depth on the MCP tool schema.
- Original, not published anywhere else first. **So this does NOT go on blog.relayshield.net until
  Apify has published or declined.** That inverts our usual canonical-first channel order and it is
  the single easiest way to disqualify the submission.
- Submitted through their Discord.
- Written by developers who actually built the thing. We did.
- Separately: $100 in Apify credits per article published on dev.to under their organisation.

**Before submitting, three facts need checking by someone with the console open**, because this
draft asserts them and I have not verified them directly:

1. **The 154 runs figure** and whether it is worth quoting at all. It is small enough that a
   reviewer might read it as a toy. Consider dropping the number and keeping "in production since
   August".
2. **The exact Standby configuration** (memory, timeout) if we want to quote it. The draft
   deliberately does not.
3. **The dependency versions as they stand today.** The draft says `apify>=2,<3` crash-looped and
   `apify>=4,<5` fixed it, taken from the Dockerfile comment dated 2026-08-25. If the pin has moved
   since, the article must move with it.

**Timing.** The July call closed 2026-08-16 and the programme is quarterly, so the next call is the
target rather than an immediate submission. Use the wait to get the three facts above nailed down,
and to decide the dev.to version.

**What this article is really for.** The $500 is not the point. The point is that it is a technical
article on a platform developers read, about a category we sell into, written from work we actually
did. The Actor gets a link, the API gets a link, and both carry `?source=apify` which is already a
registered key.
