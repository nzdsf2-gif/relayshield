# XSOAR PR #45206 — status and the nudge

Verified 2026-08-30. Supersedes the first draft of this file, which was wrong on
the central point. Re-run `sh tools/check_xsoar_pack.sh` before any claim about
the pack goes into a deck, an email or a landing page.

## The blocker, stated correctly

**The demo is a merge requirement, not a partnership requirement.**

`.github/project_conf/contributions.ini` on master defines the contribution
pipeline's own columns:

    column_names = Waiting for review,Reviewed and waiting For Changes,
                   Pending Demo,Post Demo Changes,Merged,Closed (not merged),Hackathon

    [Pending Demo]
    pull_request.labels = pending-demo

    [Post Demo Changes]
    pull_request.labels = post-demo

**Pending Demo** and **Post Demo Changes** are stages every contribution passes
through on the way to Merged. The demo is not something Moshe added because of a
partnership conversation and it is not droppable. A pack does not reach Merged
without passing through it.

So the plan needs splitting in two, because only one half survives:

- **Drop the Alliance as the commercial track.** Still right. The pack is
  `"support": "community"` and needs no partnership to ship.
- **Drop the demo.** Not available. It gates this merge directly.

What is actually wrong is not the demo, it is that the only route to a demo
environment we have been offered runs through the Alliance team.

## What the PR page shows

| | |
|---|---|
| Checks | **All passed.** 16 successful, 4 skipped |
| Branch | **Out of date, but "changes can be cleanly merged"** |
| Review | **1 change requested by a reviewer with write access** |
| Merge | **Blocked**, solely by that review |

Nothing is failing. The pack is complete at the PR head: 13 files, metadata,
README, release notes, contributors, and the integration with its own
`_test.py`. This is not a quality problem and there is no code to fix.

## The deadlock, and the way out

From Moshe's own comments: he needed somewhere to install the pack in order to
record the demo, signed up for Community Edition to do it, and then found
Community Edition was discontinued in August 2024 because it was built on XSOAR 6
and never carried to 8. He then pointed at the Alliance team for tenant access.

Read that again, because it is the useful part: **the reviewer was trying to host
the demo environment himself and could not.** The tenant gap is his as much as
ours. That makes it a shared logistics problem to solve together, not a favour to
ask for, and it is why the nudge below asks a process question rather than
requesting access.

Two openings, both of which avoid the Alliance entirely:

1. **A live screenshare instead of a recording.** If Moshe drives, or if we drive
   against an environment he can reach, no tenant is needed on our side at all.
   Reviewers routinely accept a live walkthrough. This is the cheapest unlock and
   it is the one to lead with.
2. **Ask what other community contributors do.** Packs from community
   contributors merge in this repo constantly, Brandefense landed on 2026-08-06.
   Those contributors demoed somehow, without an Alliance. Asking how they did it
   is specific, answerable in one line, and stays firmly on the community track.

## What could not be checked, and what to confirm

`api.github.com/repos/demisto/content/*` is 403 from the container, because the
agent proxy scopes API access to the session's allowed repositories. Not a rate
limit: `/rate_limit` answers 200 with 14,997 remaining. `raw.githubusercontent.com`
and the git protocol both work, which is how the rest of this was verified.

So the **exact wording of the requested change** has not been read, only its
existence. Before posting, expand "1 requested change" on the PR and check the
labels. If `pending-demo` is on it, the pipeline column confirms the demo is the
only outstanding item. If the requested change is something else as well, answer
that too.

## The nudge, to post as a comment on PR #45206

> Hi Moshe, following up on the demo, and proposing a way around the tenant
> problem rather than asking you to solve it again.
>
> Where things stand: checks are green, the branch is out of date but reports as
> cleanly mergeable, and the only thing blocking is the requested change. Happy
> to update the branch whenever it is useful.
>
> On the demo environment. You mentioned Community Edition was discontinued in
> August 2024 and was not carried over to 8, which leaves external contributors
> without an obvious way to install a pack in order to record one. Two options
> that would not need a tenant on our side:
>
> 1. A live screenshare, at whatever time suits you. We walk through the
> integration end to end against our production API, you see every command and
> its raw output, and you can ask for anything you want exercised on the spot. If
> a recording is needed for the record afterwards, we can capture that session.
>
> 2. If a self-recorded video is required, could you point me at what other
> community contributors are doing? Packs are merging from community
> contributors regularly, so there must be a standard route, and I would rather
> follow it than invent one.
>
> To be clear about scope: we are pursuing this as a community pack contribution
> only, not as part of a partnership track, so I want to keep it to whatever the
> normal community path is.
>
> The integration is one API with no dependencies, so the demo itself should be
> short. Whichever route is easiest for you, I can be ready this week.

## Why the earlier draft was withdrawn

It led on a claim that branch cleanup had lost the pack, inferred from
`add-relayshield-pack` being absent from `demisto/content` and the contrib branch
`contrib/nzdsf2-gif_add-relayshield-pack` pointing at `2c87a93`, a plain master
commit with zero `Packs/RelayShield` files.

The observations are real but the inference was not. The PR page reports the
branch as out of date and cleanly mergeable, so the head is alive, most likely in
a fork rather than in `demisto/content` itself. Posting that draft would have
told a maintainer his repository was broken while ignoring the review that is
actually blocking the merge.

The contrib branch pointing at a bare master commit is still odd and is noted
here for the record, but it is not blocking anything and does not belong in a
comment.

## Where this does not go

Not to `apa@rain.xyz`, not to the Tech Alliance contacts, not into
`xsoar_email_to_panw_techpartners.md`. Raising both together invites "let us talk
about the Alliance first", which is the one reply that slows the merge down. The
nudge above says explicitly that this is a community contribution, to close that
door before it opens.
