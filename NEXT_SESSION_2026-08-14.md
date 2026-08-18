# Next session, after the 2026-08-13 reboot

## 1. OrcX trial success criteria slide. IN PROGRESS, nothing written yet.

**Meeting is next week.** The deck is `orcx_relayshield_demo_proposal.pptx`, 7 slides, 13.33 x 7.5.

**Analysis already done, so start from here:**

- The new slide goes **between slide 6 (Proposed demo terms) and slide 7 (Let's make it real)**.
- **Duplicate slide 6 and replace its text.** It is already the right shape: a title, a subtitle,
  and four white rounded cards, each with a coral icon circle, a bold header and a description line.
- Slide 6 geometry, measured: cards at L=0.70 W=11.90 H=0.94, tops at 2.05 / 3.17 / 4.29 / 5.41.
  Icon circle L=1.00 W=0.64. Icon PICTURE L=1.15 W=0.35. Header text L=1.90 W=10.40 H=0.36.
  Description L=1.90 W=10.40 H=0.45.
- Design language: lavender background, white cards, coral circles, navy serif title, sans body.
- `python-pptx` is **not** installed in system python. It IS now installed in
  `~/anaconda3/bin/python` (1.0.2). Use that interpreter.
- Icons are PICTURE parts. Duplicating the slide carries them over. They are generic enough
  (key, clock, lock, trend arrow) to reuse without looking wrong.

**The four criteria drafted, and the reasoning matters:**

1. **All three calls run inside Quantum's own flow**, not a RelayShield demo script. Proven in the
   live working session with Gary.
2. **At least one upstream finding with no corresponding in-session behaviour.** This is the entire
   thesis of the deck. **This criterion can genuinely fail**, and it should stay written that way:
   if it never happens in 90 days, the integration has not proven its premise and both sides should
   know. A success-criteria slide where nothing can fail is a sales slide.
3. **A score change produces a different policy outcome.** The 58 to 84 escalation must move Quantum
   from elevate to terminate, or the score is decoration.
4. **Degraded is never reported as clean.** Every unavailable source surfaces as degraded. This is
   the one failure mode that would make the feed untrustworthy in production, and it is a genuine
   RelayShield differentiator.

Do NOT add a fifth card about the commercial trigger. Slide 6 already covers it ("Two paths at the
trigger, never automatic") and repeating it weakens both.

## 2. Prediction markets: SMALLER projects only.

**Founder decision 2026-08-13: Polymarket and Kalshi are the WRONG target.** Too big, and Kalshi is
not crypto. Resolved counts confirm Polymarket at 107,897 members, well outside the 1k to 50k band.

**Find smaller prediction-market projects.** Plenty exist. Resolve them with
`python3 scripts/resolve_discord_invites.py <codes>` and rank by online percentage, not member count.

Already resolved and in band from the betting/perps sweep: `azuro` 18,891 (1.8% online, quiet),
`dydx` 23,928 (6.0%), `gmx` 6,314 (3.8%).

**Unresolved, worth retrying from official sites:** `thales`, `rollbit`, `stake`, `bcgame` all 404 on
guessed vanity codes.

**Open question the founder has not decided:** gambling communities (Gamdom 10,586 at 16.5% online,
Duelbits 18,044, Shuffle) fit the product but sit awkwardly beside MSP and enterprise sales through
AWS Marketplace. Prediction markets carry less of that baggage than casinos. Decide deliberately.

## 3. Discord bot outreach, ready to send.

**Famous Fox Federation is the top target and the route is decided:** post in their
**`#collab-inquiry`** channel, which is a sanctioned intake route and beats a DM outright. Invite
verified: `discord.gg/famousfoxes` resolves to Famous Fox Federation, 15,279 members, 8.9% online.
Their rule 2 is permissive: "We love sharing relevant links... once is enough."

**Send from the Cryptonomicon account, not RelayShieldAdmin.** Founder agreed. RelayShieldAdmin is
days old, and a new account DMing about a bot is both the worst credibility pattern and a real risk
of Discord flagging the account that owns the bot. Name RelayShieldAdmin in the message as the dev
account so the admin can verify.

**The draft needs one edit before sending:** it opens "I run a small security project", which assumed
one account. Add the dev-account line so the handle mismatch is explained up front.

Message and per-server checklist: `discord_admin_approach_message.md`.
Targets and ranking: `discord_midsize_pipeline_2026-08-13.md`.

Then: **DRiP** (6,615, 13.5% online, highest engagement), **Claynosaurz** (31,241, 5.5%),
**Parcl** (49,594, 2.9%, founder's pick, biggest roster but quietest room).

## 4. Blue Team Village rsscan post. Drafted, not sent.

`btv_rsscan_post.md`. Channel is **`#tools`**.

Their posting guidelines permit "news and information about Blue Team tools and research" and
explicitly forbid "posts that advertise or sell commercial products or services". **rsscan is
postable, the API is not.** The moment pricing or Bundle A appears it is a forbidden commercial post.
That line is not worth testing.

**The CFP idea is dead for this year, verified:** DEF CON 2026 ran 7 to 9 August and is over; Blue
Team Con's CFP closed 20 April 2026. Next windows are roughly March to April 2027 (Blue Team Con) and
up to mid-May 2027 (BTV). Calendar it; do not spend an evening on an abstract now.

## 5. Small open defect

**An em-dash in user-facing product text.** `/v1/metered/identity-risk-score` returns a `summary`
reading "Domain adobe.com scores 75/100 (F — CRITICAL)". It renders in the TI demo shown to
prospects, and breaks the no-dashes house rule. Fix in `relayshield_api.py`.

## 6. Not done, deliberately

- **Solana Mobile bot post: abandoned.** Their rule 5 prohibits advertising and the carve-out covers
  only events and dApp Store apps. A bot invite is neither. See `discord_server_targets.md`.
- **TON communities: not a Discord target.** The Discord bot matches EVM, Solana and Bitcoin only.
  The **Telegram** bot does support TON via TONAPI. TON's community is Telegram-native anyway, so
  TON outreach belongs to the Telegram bot, not this one.
- **Suiet and all Cosmos/Aptos servers: ruled out on chain support**, not on fit.
