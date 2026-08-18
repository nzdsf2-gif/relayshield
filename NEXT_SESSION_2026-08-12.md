# Handover, written end of 2026-08-11

Ordering lives in `PRIORITY_QUEUE_2026-08-11.md`. This is what happened and what it changed.

## Start here tomorrow

1. **The four Bundle A doc updates** (blog, API reference, MSP brief, XSOAR demo notes). The
   listing URL is in hand and verified. SIM swap **stays in the copy**, founder's decision.
2. **XSOAR demo (#8).** Promised **21 August**, ten days out, not started. **Check the blocking
   unknown first**: whether free Community Edition still installs a custom pack from a contribution
   branch. If it does not, the approach needs rethinking and there is still time.
3. **Bundle D Stripe Door 2 — MINE, not the founder's.** I mislabelled it twice.

## The through-line today

**Four separate defects were the same shape: work that was reported as done but was not reaching
production.** The `/scan` and `/msgscan` merge that landed in the handler but not in `/help` or the
command list. The IOC-before-VirusTotal ordering that had inverted in production. The Bundle A
"Listing in review" placeholder still on the live `/developers` page. The MetaMask Snap reported as
submitted with nothing to show for it.

**The lesson, and it cost real time twice: check the live artifact, not the file.** Every fix today
was verified by downloading the deployed Lambda zip and diffing it, or by fetching the rendered page
and grepping content rather than reading a status code.

## Shipped and verified live

**Blog** — "Sender Recognition Is Not Authentication" published at
`blog.relayshield.net/sender-recognition-is-not-authentication`. Distributed to LinkedIn, Telegram,
Mastodon, Farcaster and Medium. **Medium canonical verified in a browser** and points home.

**Telegram bot, seven changes**, all deployed and verified against the live artifact:
- `/scan` and `/msgscan` merged everywhere a user looks. The 08-10 merge had only reached the
  handler; `/help` and `_BOT_COMMANDS_BASE` still advertised both, so Arjen's original complaint
  was still live.
- **Restored the optimised scan ordering.** Production was calling VirusTotal first and
  unconditionally. Now: IOC corpus, then Safe Browsing, then domain age, returning as soon as a
  blocklist-grade signal fires. A known-bad domain now costs **one local DynamoDB read and no
  external calls at all**.
- Fixed `Limit=5` + `FilterExpression` on the IOC query, the same shape that made `actor-lookup`
  blind to 83% of its table. Measured first: it was latent, not live.
- Three consolidations on one test, *would a real user fail to tell these apart*: `/sessions` into
  `/sweep`, `/vishing` into `/scam`, `/linkeddevices` + `/botcheck` + `/verifybot` into
  `/tgsecurity`. Base tier 21 commands to 15. **Every merged command still works as a hidden alias.**
- **A screenshot with no caption now goes straight to OCR.** Previously it needed a caption, so a
  user who screenshotted a scam SMS got silence.
- Category shortcut buttons on Quick Start, gated by plan, **additive** to "See all commands".

**Discord bot, built from nothing and live.** Endpoint
`https://zquf6rgaeg.execute-api.us-east-1.amazonaws.com/prod/discord/interactions`, Ed25519
verified, `/scan` and `/scam` registered. **Discord validated the endpoint itself**, which is real
proof rather than a claim: it sends a signed PING and refuses the URL unless it gets a correct PONG.
First real `/scan` in a test server returned a flagged verdict naming our corpus, ephemeral, with
the share button. Plan in `discord_flywheel_and_conversion_plan.md`.

**Bundle A is public and now visible.** `https://aws.amazon.com/marketplace/pp/prodview-zgdxyqfd63hog`,
verified by content. Added to the `/developers` page and all four badge pages. Public offer is
**$150/mo** commitment plus $0.10 to $0.50 per call across six endpoints.

**v1.4.0 unpublished** from the Solana dApp Store by Solana support.

## Corrections I had to make today

1. **"You posted this blog to HashNode."** I had not, but I wrote a success report containing the
   path `hashnode_export/...`, which read exactly like that. **Hashnode is retired permanently.**
   The directory is now `blog_source/` and `build_blog.py` no longer fetches Hashnode's RSS.
2. **HackerNoon has no importer.** It does. It also has a paywall for company-owned domains, which
   killed the channel after a full submission was prepared. **Check the money question before
   building the submission.**
3. **The MetaMask Snap is "not submitted".** It is under review, up to 30 days, to roughly
   8 September. A directory that 404s during review looks identical to one that never received the
   submission. Status comes from the reply, not the URL.
4. **Bundle D Stripe is a founder action.** It is mine. Said twice.
5. **n8n has two templates.** Three. `17255` was missing from my notes.
6. **I nearly cut the Telegram menu from 29 commands to 7.** The founder stopped me. The ask was
   targeted consolidation where users confuse two commands, not a cull.
7. **I put an OAuth URL in a bash code block**, so zsh tried to execute it. It is a browser link.

## Traps worth keeping

- **A 200 is not success, and a 404 is not failure.** AWS serves "Page not found" with a 200. The
  MetaMask directory serves 404 for anything under review.
- **Discord's API returns 403 to the default Python user agent.** Send a real `User-Agent`.
- **Lambda Function URLs with `AuthType: NONE` return 403 in this account** despite a correct
  resource policy. Almost certainly an org guardrail. Use the existing API Gateway
  (`zquf6rgaeg`) instead, and remember the stage name is in the path: `/prod/...`.
- **`cryptography` is already available** on python3.14 via the `relayshield-cdp-auth` layer. No new
  layer needed for Ed25519.
- **Two sessions deploying one Lambda is last-writer-wins.** A background task and I both edited the
  Telegram webhook today. It happened to be clean; verify rather than assume.

## Open, and needing a founder decision

- **`/exposure` metering.** Free and unmetered, a capped dedicated key, or a per-user allowance.
  Spec and recommendation in `discord_flywheel_and_conversion_plan.md`. Option 1 repeats the open
  CS Mobile unmetered-in-prod problem.
- **Zapier**, 38 tasks held on the free plan. Not paying, so the work is cutting consumption.
- **G2, Capterra, TrustRadius, Gartner Peer Insights.** No profiles exist. Arjen is the first
  review ask.

## Waiting on other people, no action

- **Twilio #28883049.** `/v1/metered/sim-swap` continues to 503 on a live public paid bundle.
- **MetaMask Snaps Directory**, in review to ~8 September. Ours to do: test `onTransaction` on
  **Sepolia**.
- **AWS ISV Accelerate**, raised with an AWS Partnership Sales contact today.
- **tgdr.io**, submitted and acknowledged.

## Deliberately deferred

- **`assetlinks.json` legacy statement.** v1.4.0 is unpublished but installs persist, and deleting
  the statement breaks Connect Wallet for those users. Both statements stay. Revisit in weeks.
