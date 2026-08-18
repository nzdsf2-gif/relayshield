# Handover, written end of 2026-08-10

Read `project_session_snapshot_2026-08-10` in memory first. The task list (#1 to #17) carries the
detail; this is the ordering.

## Bundle A went PUBLIC today

`prod-f5qkfsxlxs4qg`, Visibility `Public`, ProductState `Active`, change set
`6y08jdyygcrrwngfthquwysyl` SUCCEEDED at 19:11:59Z. The $0.01 test is what unblocked it: the 08-07
attempt had failed an AUDIT_ERROR naming two requirements, and CloudTrail now confirms both.

**It was not searchable on the storefront the same evening.** Indexing lags 24 to 48 hours. Check
before treating it as a problem.

## Start here tomorrow

**1. Verify Bundle A is indexed, then do the listing-URL pass in one go.** Search the storefront for
"RelayShield". Grab the real public listing URL from the seller portal: the `prodview` id **cannot**
be derived from the `prod-` id, and a guessed URL serves AWS's "Page not found" page with a **200
status**, which is exactly how it fooled me. Then update `/developers`, the blog, the API reference,
the MSP brief and the XSOAR demo notes **together**, not piecemeal.

**The marketing line worth leading with is procurement, not the badge:** buying through Marketplace
draws down against existing AWS committed spend, which turns a new-vendor purchase into a line item
on a bill they have already committed to. That belongs in the MSP brief and every partner
conversation.

**2. Architecture details (#11), now unblocked.** Answers already decided: hosting pattern "The
product runs entirely on AWS", application plane "Entirely or mostly in your seller AWS account",
control plane the same. Upload `relayshield_bundle_a_architecture.png` from the repo root. Not a
gate for public visibility, only the "Deployed on AWS" search designation.

**3. XSOAR demo (#8).** Promised by Friday 21 August. **Check the blocking unknown first**: whether
the free Community Edition tier still allows installing a custom pack from a contribution branch. If
it does not, the approach needs rethinking and there is still time.

**4. Blog (#13).** `blog-bluenoroff-telegram-clickfix.md`. The six `?source=` keys are already
registered and verified rendering live, with a bogus-key control confirming they mean something.
**Reread the coverage-claim section** before posting: it changed today from "we carry zero APT38
indicators" to "we ingested JUMPSEC's 83", and that is the part most likely to be quoted back. Add
the Telegram bot CTA to the Telegram version, since the bot now screens links inline and in DM.

**5. Angle 2 (#17), the on-deck build.** Spec in `angle2_maintainer_watch_scope.md`.

## Waiting on other people

- **BotsArchive** wants EUR 10 for the channel post. **Declined.** No action.
- **tgdr.io** submitted and acknowledged, awaiting review.
- **Botostore** submitted, silent, and a search shows "No results". Not confirmed.
- **Twilio #28883049** still open, so `/v1/metered/sim-swap` still 503s on a live public bundle.
- **MetaMask Snaps Directory**, submitted 2026-08-09.

## Open, not started

- **#16 Stripe Door 2 for Bundle A**, gated on AWS indexing. Mirror what was done for Bundle D.
- **#10** rsscan agent instruction file scanning (Angle 1).
- **#14** Hackernoon and other canonical-accepting syndication.
- **#15** the one-time demo video set. Inline mode in a group chat is the single best subject.
- **Discord**, researched not started. `discord_landscape_research.md`. Slash-command only, and
  deliberately do **not** request Message Content Intent.
- **The Stripe Product and Price for Bundle D do not exist yet.** Code is deployed and dormant.
  Create the product at $299/mo, send me the `price_...` id, and I will set the env var. Description
  copy is ready.

## Things that are still broken

- **`sites.google.com` and `raw.githubusercontent.com` are tagged as ClickFix domain IOCs.** Hosting
  platforms, not threats. A customer sweep matching them is a false positive with real cost.
- **`relayshield_agentic_api.py:260`** still has the `or not BUNDLE_D_PRODUCT_CODE` guard that the
  main API deliberately removed. Latent, not live, since that Lambda serves no Bundle A paths.
- **New-user acquisition attribution has a gap.** `?start=src_x` logs the arrival, but a brand-new
  user has no record at `/start` time, so only the log line captures them. Click attribution works;
  signup attribution for new users would need the source threading through `create_telegram_user`.

## Traps that cost time today

- **A 200 status code is not success.** AWS "Page not found" returns 200. So did storebot.me before
  it started 403ing, and botostore's silent form.
- **DynamoDB `Limit` with a `FilterExpression` on a scan** applies the limit to items *examined*,
  before filtering. It made `actor-lookup` blind to 83% of the MITRE table.
- **Telegram bot directories have largely decayed.** Four tried: one paid, one dead, one silent, one
  worked. Do not plan a channel around them.
- **`~/anaconda3/bin/python3`** is the only interpreter here with boto3.
