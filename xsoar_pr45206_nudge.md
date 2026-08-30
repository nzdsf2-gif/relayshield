# XSOAR PR #45206 — status and the nudge

Verified 2026-08-30 from the container. Re-run `sh tools/check_xsoar_pack.sh`
before any of this goes into a deck, an email or a landing page.

## What is verified

| Question | Answer | How |
|---|---|---|
| Is PR #45206 open? | **Yes** | `refs/pull/45206/merge` present; GitHub deletes it on merge or close |
| Is the pack on master? | **No** | `pack_metadata.json` 404 on master, control pack 200, same file 200 at the PR head |
| Is the pack complete? | **Yes, 13 files** | `git ls-tree` at PR head `6288055` |
| Who last touched it? | **A Palo Alto maintainer** | head commit is Moshe Eichler, 2026-08-09, merging `contrib/nzdsf2-gif_add-relayshield-pack` into `add-relayshield-pack` |
| How current is it? | **~24 days stale** | its base is master as of 2026-08-06 |

The pack is structurally complete: `pack_metadata.json`, `README.md`,
`ReleaseNotes/1_0_0.md`, `CONTRIBUTORS.json`, `Author_image.png`, both ignore
files, and the integration with its `.py`, `.yml`, `_description.md`, `_image.png`
and `_test.py`. Nothing obvious is missing.

`"support": "community"` in the metadata. That is the correct setting for a
contribution made outside a partnership, and it is what makes the Alliance
genuinely unnecessary here. It also bounds the claim: a community pack ships in
the marketplace, it is not Palo Alto supported, so "available for Cortex XSOAR"
is fair and "supported by Palo Alto" is not.

## The finding that changes the nudge

**The branches behind the PR have been dismantled, while the PR stayed open.**

- `add-relayshield-pack`, the maintainer branch the PR head sits on, **no longer
  exists** in `demisto/content`.
- `contrib/nzdsf2-gif_add-relayshield-pack` is still there, but its head is
  `2c87a93` and **zero files under `Packs/RelayShield` exist at that commit**. It
  has been overwritten with ordinary master content.

The pack survives only because GitHub keeps `refs/pull/45206/head` immutable.

This corrects the reading in CLAUDE.md. That note said the contrib branch being
live and its "Auto Merge Docker Update" workflow still firing on 2026-08-29 meant
the PR was active. The branch is live, but it no longer contains the pack, so
that automation is master-sync noise and is not evidence of work on this
contribution.

Most likely explanation: the pack was lost in branch housekeeping and the PR was
never closed. That is a good thing to be nudging about, because it is specific,
checkable in a minute by whoever reads it, and it gives them an easy action.

## What could not be checked

**CI check status and review threads.** `api.github.com/repos/demisto/content/*`
returns 403 from this container: the agent proxy scopes API access to the
session's allowed repositories. It is not a rate limit, `/rate_limit` answers 200
with 14,997 requests remaining. `raw.githubusercontent.com` and the git protocol
both work, which is how everything above was verified.

So if a reviewer has requested changes, or a required check is red, that is not
reflected here. Read the PR page before sending, and adjust the second paragraph
if there is an open review comment to answer.

## The nudge, to post as a comment on PR #45206

> Hi, checking in on this one and flagging something that looks like it may have
> gone wrong on our side of the fence rather than yours.
>
> This PR is still open, and its head commit (6288055, 9 August) carries the
> complete pack: metadata, README, release notes, contributors, and the
> integration with its test file. But the branch that commit sits on,
> `add-relayshield-pack`, no longer exists in the repo, and
> `contrib/nzdsf2-gif_add-relayshield-pack` now points at a commit with no
> `Packs/RelayShield` files in it at all. The pack content only survives on the
> pull request's own head ref.
>
> That looks like branch cleanup rather than a decision about the contribution,
> so I wanted to raise it rather than let it sit.
>
> Happy to do whichever is easiest for you: rebase onto current master and push
> again here, or open a fresh PR from a clean branch if this one is beyond
> recovering. The pack is community support, one integration, no dependencies, so
> re-submitting is cheap if that is simpler.
>
> Anything you need from me on the content itself, I will turn it around quickly.

## Where this does not go

Not to `apa@rain.xyz`, not to the Tech Alliance contacts, not into
`xsoar_email_to_panw_techpartners.md`. The pack is a public contribution and
needs no partnership. The Alliance is a separate commercial track gated on three
named joint customers, and mixing them invites the answer "let us talk about the
Alliance first", which is the one outcome that would slow the merge down.
