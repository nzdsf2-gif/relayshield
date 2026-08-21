# Gaming and prediction markets: outreach focus list

*Built 2026-08-14. Supersedes the betting/perps sweep in `NEXT_SESSION_2026-08-14.md` section 2.*

## The correction that starts this

Yesterday's sweep offered `dydx` (23,928), `gmx` (6,314) and `azuro` (18,891) as prediction-market
candidates. **Founder rejected all three on 2026-08-14 and was right.** dYdX and GMX are perpetuals
exchanges, and Azuro is a betting *protocol* rather than a community. None of them is a gaming or
prediction-market audience. That sweep is discarded rather than reranked.

Also carried forward: **Polymarket (107,897) and Kalshi are ruled out.** Too big, and Kalshi is not
crypto.

## Chain support gate, checked first this time

`relayshield_discord_bot.py:112` is `^0x[a-fA-F0-9]{40}$`, exactly 40 hex characters, plus base58
Solana and Bitcoin. Verified today by reading the regex, not from memory.

**This rules out Starknet outright.** Starknet addresses are `0x` followed by up to 64 hex, so they
fail the EVM pattern. **Loot Survivor is therefore out** despite resolving at 1,015 members and a
strong 16.0% online. It would have been the second-best gaming number in the set.

BNB Chain, Arbitrum, Base, Ronin and Immutable zkEVM all use 40-hex `0x` addresses and pass.

### Avalanche C-Chain qualifies, and this was tested rather than assumed

**Yes, and Avalanche subnets too** (Beam, DFK Chain, MapleStory's chain). All use standard 40-hex
`0x` addresses.

A pedantic but load-bearing correction: **C-Chain is an L1, not an L2.** It is one of Avalanche's
three native chains and settles on its own consensus, not to Ethereum. It does not change the answer
here, but it matters if the distinction ever ends up in outreach copy.

**The part that needed checking.** `relayshield_api.py:3183` is
`_GOPLUS_CHAIN_IDS = {"evm": 1, "solana": 101}`, so **every** `0x` address is queried against GoPlus
on **Ethereum mainnet**, whatever chain it is really from. That is the exact shape of the false-clean
defect this codebase has fixed repeatedly, so it was worth testing rather than reasoning about.

**Tested 2026-08-14** against the documented Ronin bridge exploiter address
(`0x098B716B8Aaf21512996dC57EB0615e2383E2f96`) across `chain_id` 1, 56, 43114 and 42161:

| chain_id | Chain | Flags returned |
|---|---|---|
| 1 | Ethereum | `blacklist_doubt`, `sanctioned`, `stealing_attack` |
| 56 | BNB | identical |
| 43114 | Avalanche C-Chain | identical |
| 42161 | Arbitrum | identical |

**GoPlus's malicious-address labels are cross-chain**, so the hardcoded `chain_id=1` does not produce
false cleans for the flags the verdict is built from. The per-chain fields that *do* vary
(`contract_address`) are not read by the risk logic at `relayshield_api.py:3454`.

**This also clears the Thetan/BNB caveat below.** It was flagged as "confirm GoPlus BSC coverage
before pitching", and that check now passes.

> Honest limit on the test: it exercised `blacklist_doubt` and `stealing_attack` on one address.
> `phishing_activities`, `darkweb_transactions` and `cybercrime` were not exercised and are assumed
> to behave the same way. The evidence is strong, not exhaustive.

### AVAX gaming: qualifies technically, thin in practice

Resolved 2026-08-14. The chain is fine; the communities are the problem.

| Server | Members | Online % | Verdict |
|---|---|---|---|
| Arena | 15,384 | 4.2% | In band, but this is the AVAX social app, not a game. Verify before using |
| Beam.gg | 3,801 | 2.2% | In band, quiet |
| Castle Crush | 19,853 | 1.0% | 191 online. Effectively dead |
| MapleStory Universe | 222,588 | 4.3% | Far over band, company-run |
| Avalanche | 50,002 | 5.5% | Two members over the ceiling, and it is the L1's own staff-moderated server |

**Did not resolve:** Crabada, Ascenders, Heroes of NFT, Imperium Empires, Colony, Kingdom Karnage,
DFK Chain, Shatterline, and `playbeam`. Nine 404s means this picture is incomplete rather than
settled, so if AVAX is worth pursuing the next step is pulling those invites from official sites.

**As it stands, nothing in the AVAX set beats the top five below.** Shrapnel, the best-known AVAX
game, resolved at 63,924 and is over the ceiling.

## Read this before pitching anyone below

**Every invite code in this document was guessed, not taken from an official site.** The resolver's
own docstring warns that this is how you end up measuring a squatted server, and this run proved it
six times over:

| Guessed code | What it actually resolved to |
|---|---|
| `limitless` | "Limitless Rust", 111,201 members. A Rust game server, not Limitless Exchange |
| `nyan` | A 139,490-member social and giveaways server, not Nyan Heroes |
| `unicorns` | "/unicorns #vc :3", 363 members |
| `dfk` | "dfk Party Royale", 1,418 members. Not DeFi Kingdoms' main server |
| `faraway` | "Faraway Placeholder", 591 members |
| `sipher` | "\>.\<", 2,530 members at 0.8% online |

Roughly one guessed code in six landed on the wrong server. **Confirm every invite from the
project's own website before sending anything.**

---

## Prediction markets: the honest finding

**The crypto prediction-market category is too small to build a pipeline from.** This is the result,
not a failure to search hard enough. Twenty-two candidate codes across two passes produced exactly
one live, in-band community.

| Project | Members | Online % | Verdict |
|---|---|---|---|
| **Overtime** | 4,163 | **16.5%** | **The only real target.** In band, genuinely active |
| Myriad | 50,605 | 3.2% | 605 over the band ceiling and quiet. Marginal |
| Opinion Labs | 71,905 | 1.8% | Too big, and very quiet for its size |
| Divvy.Bet | 1,307 | 0.5% | In band on paper. **6 people online. Dead** |
| Truemarkets | 172 | 88.4% | Too small to matter |

**Did not resolve at all**, on any code tried: Hedgehog Markets, Aver, Monaco Protocol, SX Bet,
Thales, Limitless Exchange, BetOnSol, Futuur, Prediqt, Augur, BetSwirl. A 404 is not proof a project
has no Discord, but eleven consecutive ones says the category's communities are either gone,
private, or never existed at scale.

**Recommendation: treat Overtime as a one-off, not a category.** Overtime runs on Optimism, Arbitrum
and Base, so addresses pass the EVM gate. Do not spend more time trying to manufacture a
prediction-market list out of what is left.

### CORRECTION TO THE CORRECTION, later on 2026-08-14: the category is one, and it is Limitless

**I said the category was zero. That was wrong, and the reason I got it wrong matters.**

`limitless` resolved to a Rust game server and `limitlessexchange` returned 404, and I let two failed
lookups stand in for evidence of absence. **This document's own rule says a 404 tells you nothing
either way**, and I broke it in the paragraph immediately below.

**Limitless is real, live, and the best prediction-market target available.** Their X handle is
`@trylimitless`, and `discord.gg/trylimitless` resolves to **Limitless, 12,249 members, 935 online,
7.6%**. In band.

It is not a marginal project. Limitless launched in 2025 on Base, is backed by **Coinbase Ventures**,
and crossed **$1B in notional monthly volume** for the first time this year, up from roughly $360M.
Markets span crypto prices, stocks, politics and events, so unlike Overtime it is a genuine
prediction market rather than a sportsbook.

**Verify the invite from `limitless.exchange` before sending.** The code above was inferred from their
X handle, which is exactly the guessing this document warns against.

**Truemarkets** is also on Base but its Discord resolved at 172 members. Too small.

### Overtime is sports betting, not a prediction market. And it is now a NO.

**Founder correction, and it was right.**

**Founder correction, and it is right.** Overtime is a sports betting protocol, not a prediction
market. Its own channel list settles it: `#casino`, `#speed-markets`, and a `#report-scammers`
channel full of betting-tout scams.

**So the honest count for crypto prediction markets in band is zero, not one.** The single "real
target" in the table above was misfiled. Nothing else in that table survives either: Myriad is over
the ceiling, Opinion Labs is too big and quiet, Divvy.Bet has six people online, Truemarkets is 172.
**Stop treating prediction markets as a channel.** It is not one.

**Overtime moves into the gambling bucket**, which is the decision the founder left open on
2026-08-13 and which is now being made in practice rather than in principle. Worth naming: the
practical exposure is low, since installing a free bot is not a marketing partnership and does not
appear in AWS Marketplace materials. But it is the gambling question being answered, not sidestepped.

**Member count discrepancy, unresolved.** The invite preview returned **4,163 members**. The server's
own stats channel, read from inside by the founder, says **10,975**. The in-server figure is the one
to trust; invite previews and stats bots count differently, and a stats bot may include all-time
joins or bots. **It changes nothing actionable**: both numbers sit inside the 1,000 to 50,000 band.
Recorded because the same gap appeared on LAMINA1 and will appear again.

**Chain note:** Overtime is EVM (Optimism, Arbitrum, Base), not Solana. The bot covers both, so
nothing is blocked, but the pitch should not describe it as a Solana community.

**OUTCOME: declined 2026-08-14. "Not looking rn."** Ticket opened, message sent, answer back within
the hour. **Close the thread and do not follow up.**

**This is the ask-permission approach working, not failing.** A clean no in under an hour, with no
rule breached and no server burned, is the outcome that method is designed to produce. Compare the
alternative: post first, get removed, and lose the room permanently. The cost of finding out was
roughly ten minutes.

## Predi by Virtuals: not a Discord target. See the x402 section instead.

Checked 2026-08-14. **`predictbase`, `predibot` and `predi` all 404.** That is consistent with how the
product actually works: **PrediBot is X-native**, users create and place onchain predictions by
tagging `@predibot_` in a tweet. There is no community room to pitch a Discord bot into.

PREDI is on Base, contract `0xaeA742f80922f7C94B8FD91686c9dFbDFE90d9E6`.

**Virtuals Protocol itself has two servers resolving under the same name**, which is a live instance
of the trap at the top of this document:

| Code | Guild | Members | Online % |
|---|---|---|---|
| `virtualsio` | Virtuals Protocol | 12,661 | 9.2% |
| `virtuals` | Virtuals Protocol | 5,677 | 4.5% |

**One of these is not theirs.** Do not touch either until the invite is confirmed from `virtuals.io`.

**But the Discord bot is the wrong product for this audience anyway.** See below.

---

## Gaming: this is where the audience actually is

Ranked by online percentage, which is the presence proxy, not by member count.

| Rank | Server | Members | Online % | Chain | Note |
|---|---|---|---|---|---|
| 1 | **Wildcard** | 1,085 | **14.7%** | EVM | Small, engaged, one person decides |
| 2 | **Honeyland** | 1,051 | **13.8%** | Solana | Best Solana engagement in the set |
| 3 | **Pirate Nation** | 1,075 | **13.5%** | Arbitrum | Resolved as "Pirate Nation Foundation", verify this is the player community and not a governance server |
| 4 | **Gods Unchained** | 24,937 | **11.8%** | Immutable zkEVM | Best size-to-engagement trade here. Biggest prize on the list |
| 5 | **Genopets** | 1,190 | **11.6%** | Solana | Move-to-earn, wallet-native |
| 6 | Amiko Arena | 31,193 | 6.6% | Solana | Resolved from the `aurory` code under a different name. **Verify the rebrand before trusting this row** |
| 7 | Treasure | 39,502 | 5.5% | Arbitrum | Large, quieter. An ecosystem hub rather than one game |
| 8 | Thetan World | 1,936 | 5.1% | BNB Chain | Chain support verified 2026-08-14, see the Avalanche section |

### VERIFIED INVITE CODES, resolved 2026-08-17

**The original list ranked servers but recorded invite codes for only three of them**, which is why
the Wildcard row was unusable. Every code below was resolved live against Discord's public
unauthenticated invite endpoint on 2026-08-17. All show `expires: never`.

| Server | Invite | Members | Online % | Status |
|---|---|---|---|---|
| **Splinterlands** | `discord.gg/splinterlands` | 16,271 | **19.1%** | **NEW, best engagement on the whole list** |
| Gods Unchained | `discord.gg/godsunchained` | 24,909 | 14.6% | verified |
| Honeyland | `discord.gg/honeyland` | 1,052 | 13.6% | verified |
| Pirate Nation | `discord.gg/piratenation` | 1,077 | 13.3% | verified |
| ~~Wildcard~~ | `discord.gg/wildcard` | 1,086 | 12.2% | **WRONG AUDIENCE, see below** |
| The Sandbox | `discord.gg/thesandbox` | 5,348 | 11.4% | **NEW, in band** |
| Genopets | `discord.gg/genopets` | 1,194 | 11.3% | verified |

**Wildcard: the invite on their own website is EXPIRED.** `discord.com/invite/QZRgv9M2UZ` returns
`{"message": "Invite is expired.", "code": 50270}` from Discord's API, so it is not a permission
problem and retrying will not help. **`discord.gg/wildcard` is live and permanent.** Game Discords
rotate invites after raids and often forget to update the website link, so resolve a code before
trusting any published invite.

### WILDCARD IS NOT A WEB3 GAME. Corrected 2026-08-17.

**The original row labelled Wildcard "EVM". That was wrong.** `discord.gg/wildcard` resolves to
**Wildcard Gaming, an esports organisation**. Its own welcome message reads "Wildcard Gaming's
discord server ... prospective esport legends", and the channels are `#esport-discussion`,
`Watch Party` and `Gaming`. There is no wallet-holding audience here, so a counterparty-screening
bot has nothing to attach to.

Member count matches the original measurement almost exactly (1,085 vs 1,087), so this is the same
server that was ranked #1, mis-categorised at the time. **The confusion is a real one**: there is a
separate web3 game also called Wildcard (Wildcard Alliance), and neither `playwildcard` nor
`wildcardalliance` resolves to anything.

Discord's own API also reports the guild as `VERIFIED` with `AUTO_MODERATION` enabled. A verified
brand server with automated moderation is the opposite of the "small community without mods who ban
harmless requests" profile this pipeline is built for.

**Do not pitch here.** Redirect that effort to Splinterlands, Honeyland, Pirate Nation and Genopets,
which are actual web3 games with wallet-native audiences.

**Lesson for the rest of the list: resolving an invite proves a server EXISTS, not that it is the
right server.** Member count and online percentage say nothing about whether the audience holds
wallets. Read the welcome or rules channel before writing a chain label into this table. The
"Pirate Nation Foundation" and "Amiko Arena" rows carry the same unverified risk and are flagged
accordingly.

### Checked and rejected 2026-08-17, with the reason

| Server | Invite | Members | Online % | Why not |
|---|---|---|---|---|
| Illuvium | `discord.gg/illuvium` | 138,709 | 8.0% | Far over the size ceiling |
| Shrapnel | `discord.gg/shrapnel` | 63,883 | 6.7% | Over ceiling, engagement below band |
| Open Loot (OLD) | `discord.gg/bigtime` | 25,465 | 6.8% | Resolves to a server named "(OLD)". **Legacy, find the current one before using** |
| Aavegotchi | `discord.gg/aavegotchi` | 25,238 | 5.3% | Engagement below band |

`axieinfinity`, `ember`, `darkbright`, `playwildcard`, `wildcardalliance`, `nyanheroes`, `parallel`,
`guildofguardians`, `galagames`, `cryptounicorns` all return **Unknown Invite**. Guessing vanity
codes works maybe half the time; do not put a guessed code in a doc without resolving it first.

### Revised order, 2026-08-17

1. **Splinterlands.** 19.1% online at 16,271 members is the best size-to-engagement trade found so
   far, better than Gods Unchained. A trading-card game with an active market means constant address
   and link traffic, which is exactly the surface the bot serves.
2. **Honeyland**, **Pirate Nation**, **Genopets.** All ~1,100 at 11-14%, the "one person decides"
   profile. Founder decision 2026-08-17: **these smaller communities are the target precisely
   because they lack mods who ban harmless requests.** Wildcard is removed from this tier; it is an
   esports org, see above. **Verify Pirate Nation is the player community and not the governance
   server before pitching.**
3. **Gods Unchained**, then **The Sandbox**.

### Founder additions 2026-08-14, both verified against official invites

**DeFi Kingdoms. Add it, and override the band.**

My guessed `dfk` code resolved to "dfk Party Royale", 1,418 members, which I flagged as probably not
the main server. It was not. The official invite from `defikingdoms.com/social.html` is
`discord.com/invite/kARBQuMAhS`, and it resolves to **DeFi Kingdoms, 55,661 members, 5.4% online**.

That is 5,661 over the band ceiling, and it should still go on the list. **The band is a proxy, not a
rule.** It exists to approximate "small enough that one person decides and standing is achievable".
The founder is a former player who knows the community is still active and knows it has a healthy
partner channel. That is actual standing plus a named intake route, which is the thing the band was
only ever estimating. When you have the real signal, stop using the proxy.

Also resolved: **DeFi Kingdoms JP [OFFICIAL]**, 3,263 members, 3.3% online, a separate official
Japanese server. In band, and a plausible second shot if the main one stalls.

DFK runs on DFK Chain, an Avalanche subnet, so addresses are 40-hex `0x` and pass the gate.

**LAMINA1. Add it, but the member count is not what we thought.**

`discord.gg/lamina1` is confirmed official and resolves to **LAMINA1, 1,924 members, 98 online,
5.1%**. Comfortably in band.

**It is not 49K.** LAMINA1's own communications describe "over 50k engaged" in its Betanet, which is
a total community-engagement figure across all channels, not Discord membership. Worth knowing before
pitching, so the ask is not built on reach that is not in the room.

The upside of the correction is real: at 1,924 it is far more likely one identifiable person decides
than it would be at 49,000.

LAMINA1 is a Layer 1 built on Avalanche, so `0x` addresses, and chain support is confirmed by the
GoPlus test above.

**One thing to check first, per the playbook.** It is a metaverse and creator-economy project rather
than a trading community, and 98 people online is quiet. Read the general channel for actual
wallet-scam traffic before pitching. If nobody is asking "is this link real", the product does not
solve a problem they feel, whatever the chain support says.

### Ruled out, with the reason

- **Loot Survivor** (1,015, 16.0%): Starknet. Fails the address regex. The single most painful cut.
- **Open Loot** (`bigtime` code): resolved to "Open Loot (OLD)", a server the project itself has
  marked stale. The current one is 295,342 members, far over band.
- **Star Atlas** 162,212, **Axie** 641,599, **Pixels** 214,197, **STEPN** 201,008, **Illuvium**
  138,714, **Off The Grid** 138,541, **Sunflower Land** 114,239, **Ember Sword** 57,557,
  **Shrapnel** 63,924, **MixMob** 50,180: all over the 50,000 ceiling. Company-run servers with
  staff moderators, which per `discord_midsize_pipeline_2026-08-13.md` is the profile that does not
  add an outside bot.
- **Photo Finish** (168), **Influence** (79), **SX Network** (36): too small, and the low counts
  suggest the guessed code found a side server rather than the main one.

---

## Suggested order

1. **Gods Unchained**, rank 4. Largest audience that is still in band, 11.8% online is genuinely
   active for 24,937 members, and a trading-card game means constant link and address traffic.
2. **Wildcard**, **Honeyland**, **Genopets**, **Pirate Nation**. All four are ~1,100 members at
   13-15% online, which is the "one person decides" profile that the Famous Fox approach is built
   for. Cheap to try, and four attempts at this size cost less than one at Gods Unchained's.
3. **Overtime**, as the only prediction-market entry.

Use the message and the per-server checklist in `discord_admin_approach_message.md`. The rules-first
step is not optional: it is what stopped the Solana Mobile post on 2026-08-13.

## Still open, founder decision from yesterday

Gambling communities (Gamdom 10,586 at 16.5%, Duelbits 18,044, Shuffle) remain undecided. Nothing on
this list depends on that call. Prediction markets carry less of the baggage, but the category turned
out to be one server deep, so if the gambling question is answered "no", the practical effect is that
this becomes a gaming-only pipeline.

---

# Session 2026-08-20

## First: this file was laptop-only until today

It was recovered by upload, not from git. **`relayshield_discord_bot.py` is still missing**, and so
are `discord_admin_approach_message.md`, `discord_midsize_pipeline_2026-08-13.md` and
`NEXT_SESSION_2026-08-14.md` — every one of them is cited above as load-bearing, and none is in the
repo. The address regex at `relayshield_discord_bot.py:112` that gates this entire list cannot be
re-read by anyone but the founder.

That is the **third** time single-laptop-only state has caused a wrong answer in this project
(rsscan 0.2.x is the standing example). **Push the Discord bot workstream.** Until then every claim
in this document that rests on reading the bot's source is unverifiable by anyone else.

## Constraint on this session's additions: invites could not be resolved

`discord.com` is **egress-blocked** in this sandbox — `CONNECT tunnel failed, response 403`. The
public invite endpoint this document relies on is unreachable from here.

So, obeying this document's own cardinal rule: **not one invite code, member count or online
percentage below is claimed as verified.** Candidates are named with the reason they belong, and the
resolution step is left explicit. Do not pitch anyone from this section until the invite is resolved
from the project's own site.

Resolve on the founder's Mac:

    curl -s "https://discord.com/api/v10/invites/CODE?with_counts=true" | python3 -m json.tool

Read `guild.name`, `approximate_member_count`, `approximate_presence_count`. Online % is
presence ÷ member.

---

## DeFi Kingdoms: rsscan or the bot?

**Pitch the bot. Mention rsscan in one line. Use the BizDev form.**

DFK is already on this list as a founder addition, with the band deliberately overridden and the
official invite verified (`discord.com/invite/kARBQuMAhS`, 55,661 members, 5.4% online). Everything
that made it a target still holds: DFK Chain is an Avalanche subnet, so addresses are 40-hex `0x`
and pass the gate; the founder is a former player; there is a partner channel.

Why the bot leads and not rsscan:

1. **The bot serves their players; rsscan serves their engineers.** The BizDev form is gatekeeping
   partnerships, and a community-safety feature for 55,661 players is something a BizDev team can
   approve, announce and take credit for. A secret-scanning pre-commit hook is not — it is a link
   you send an engineer, and it never needed a form.
2. **rsscan has no partnership shape.** It is free, MIT, runs locally, needs no account and no
   integration. There is nothing to negotiate, which is a virtue everywhere except on a
   collaboration form, where it reads as a non-ask.
3. **DFK likely already has secret scanning.** GitHub's is on by default for public repos. rsscan's
   real edge is the *pre-commit* hook catching the key before it enters history — a genuine
   argument, but a second-conversation one, not an opener.

So: lead with the bot, then one line — "separately, and free: our engineers may want rsscan, MIT,
runs locally, catches API keys pre-commit" — with the repo link. Zero cost to include, and it shows
the company is more than a single bot.

### Route: use the BizDev form, not the general contact form

From the contact page, three routes exist and only one is right:

| Route | Use for | Verdict |
|---|---|---|
| General contact form | General question / Suggestion / Publication / Other. Explicitly **not** user support | Wrong. A bot install is not a suggestion |
| **BizDev form** — `https://forms.gle/fv4y1G3ppNgJDpEDA` | "partnership or collaboration" | **This one** |
| `defikingdoms.com/bugreport.html` | vulnerabilities | Wrong, and misusing it would burn credibility |

**But check the partner channel first.** The band was overridden for DFK specifically because the
founder has standing and DFK has "a healthy partner channel." A warm route through that channel
beats a cold Google Form every time. The BizDev form is the fallback if the partner channel is
stale or the founder's standing has decayed — it is not the first choice just because it is the
route that happens to be documented.

### Headwind to know before sending: DeFi is leaving Discord in 2026

This is new since the list was built and it cuts against every Discord-bot pitch:

* **Morpho** switched its public Discord to read-only from **Feb 1, 2026**, moving to ticketed support.
* **DefiLlama** and others moved to live chat and email tickets, arguing Discord makes it
  "impossible" to fully block DM scams even with verification and stricter moderation.
* **Marc Zeller** (Aavechan Initiative) called Discord "full of scammers" and said Morpho's move
  should prompt other protocols to reconsider.
* Underneath it: Discord's **October Zendesk breach**, with researchers claiming 2M+ passport and
  driver's-licence images exfiltrated.

**Why this does not kill the DFK pitch.** The exodus is DeFi *protocol support desks* — rooms whose
only job is answering "my transaction failed." A game's Discord is the social layer and largely is
the product; DFK cannot leave it the way Morpho could. Games are structurally stickier here.

**Why it still changes the pitch.** The prevailing view among sophisticated teams in 2026 is that
Discord is a liability. Walking in with "add our bot to your Discord" without acknowledging that
reads as unaware. **Name it and turn it:** the reason protocols are fleeing is that they have no way
to screen what gets posted and DM'd — which is the thing the bot does. That reframes the bot as the
alternative to abandoning the room, not as one more integration.

**Check before sending:** scan DFK's recent announcements for any sign they are themselves reducing
Discord. If they are, the pitch changes shape entirely.

---

## New candidates, all UNRESOLVED

Ranked by fit, not size — none of these has been measured. Nothing here is a claim about member
count, and the invite must come from the project's own site.

### Gaming

| Candidate | Chain | Gate | Why it belongs | Next step |
|---|---|---|---|---|
| **Lumiterra** | Ronin | ✅ 40-hex `0x` | The strongest new name. Posted **+9,451% active wallets in Q3 2025**, one of the fastest-growing web3 MMORPGs. Open-world survival + farming + guild play means constant item trading, which is exactly the address-and-link traffic the bot attaches to | Invite from official site |
| **The Machines Arena** | Ronin | ✅ | 4v4 hero shooter on Ronin, named alongside Lumiterra and Pixels as the titles driving Ronin's daily active wallets to 419K in Q3 (+55%). Shooters skew younger and more drainer-exposed | Invite from official site |
| **Guild of Guardians** | Immutable zkEVM | ✅ | Already tried above and returned Unknown Invite on a *guessed* code — which this document says proves nothing. Immutable stablemate of Gods Unchained, the current #4 on the list | Pull the real invite from `guildofguardians.com` before writing it off |
| **DeFi Kingdoms JP** | DFK Chain | ✅ | Already resolved above: 3,263 members, 3.3% online, separate official Japanese server, in band. **Do not pitch in parallel with the main server** — one company, and two simultaneous approaches looks careless | Hold as the second shot |

**Ruled out on the gate, same basis as Starknet:**

* **Alien Worlds (WAX)** — WAX uses EOS-style 12-character account names, not `0x` hex or base58.
  **Fails the regex at `relayshield_discord_bot.py:112`.** Worth recording because WAX's raw activity
  (687M gaming transactions) makes it look attractive until you check the address format. Gate first,
  as this document already learned once.

**Ruled out on size** (over the 50,000 ceiling, consistent with the existing table): Pixels
(~214K), Big Time / Open Loot current server (~295K), Axie Infinity.

### Gaming guilds — a new axis worth one test

Guilds are not games, and that is the point. A guild's members are cross-game, wallet-native by
definition, and are precisely the cohort that gets drained. A guild admin is also far more likely to
be the "one person decides" profile than a company-run game server with staff moderators.

| Candidate | Note | Next step |
|---|---|---|
| **Yield Guild Games (YGG)** | 40+ game partnerships. Probably over the ceiling — measure before assuming | Resolve |
| **GuildFi** | Named alongside YGG and Merit Circle as having built large loyal token-voting communities | Resolve |
| **Merit Circle / Beam** | **Beam.gg already measured: 3,801 members, 2.2% online — in band but quiet.** Merit Circle's own server is a separate room and was never measured | Resolve Merit Circle proper |

**Test exactly one guild before treating this as a category.** That is the lesson prediction markets
taught at a cost of twenty-two lookups: do not build a list for a category that has not yet produced
a single live, in-band, correctly-categorised room.

### DeFi projects: recommend NOT opening this as a category

The user asked to explore DeFi candidates. The honest answer is that the evidence argues against it,
and for the same structural reason prediction markets came out at zero.

DeFi protocol Discords in 2026 are **actively contracting** — read-only, ticketed support, or gone
(Morpho, DefiLlama, and the Zeller quote above). The ones that remain split into two useless halves:
the large protocol servers are staff-moderated and over the ceiling, and the small ones are quiet
enough that nobody is asking "is this link real" — the exact disqualifier already applied to
LAMINA1.

**The exception is the shape DFK already is: gaming-adjacent DeFi.** A game with real DeFi mechanics
has a community that both holds wallets *and* has a social reason to stay in Discord. That is the
overlap worth mining, and DFK is its archetype rather than an outlier.

**Recommendation: do not build a DeFi protocol list.** Spend the same effort resolving the four
gaming names above, where the audience is not leaving the platform.

---

## Suggested order after this session

1. **Push `relayshield_discord_bot.py` and the three missing docs.** Everything else here is
   unverifiable until that lands, and this is the third repeat of the same failure.
2. **DeFi Kingdoms** — partner channel first, BizDev form as fallback. Bot leads, rsscan as a
   one-liner.
3. **Resolve the four gaming invites** (Lumiterra, The Machines Arena, Guild of Guardians, and
   re-check Splinterlands' 19.1% still holds) from official sites.
4. **One guild test** before deciding whether guilds are a category.
5. Existing order stands for the already-verified names: Splinterlands, then Honeyland / Pirate
   Nation / Genopets, then Gods Unchained and The Sandbox.

---

# Session 2026-08-20, part 2

## `relayshield_discord_bot.py` is now in the repo

Recovered by upload and committed. rsscan reports **0 findings** on it (dogfooded before the commit),
and the two hardcoded values are non-secret by design: `APPLICATION_ID` is public, and `PUBLIC_KEY`
is Discord's *verification* key — it only verifies inbound signatures and signs nothing. Every real
credential comes from Secrets Manager at runtime.

**The regex this whole document's chain gate rests on is now readable by anyone:**

    _EVM_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")     # line 112
    _SOL_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
    _BTC_RE = re.compile(r"^(bc1[a-z0-9]{25,62}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})$")

Everything the document claimed about the gate checks out.

## Ronin: EVM, supported — with one gap worth fixing before pitching a Ronin game

**Yes, Ronin is EVM and it passes.** Ronin addresses are ordinary 20-byte EVM addresses, so they
match `_EVM_RE`, they resolve to `chain="evm"` in `_detect_chain_api()`
(`relayshield_api.py:2827`), and Crypto Shield Mobile's wallet type is
`"solana" | "evm" | "bitcoin" | "ton"` (`crypto-shield-app/src/hooks/useWallet.ts:8`) — generic EVM,
not a per-chain allowlist. **Nothing about Ronin needs adding for CS Mobile to accept the address.**

Screening goes to GoPlus with `chain_id=1` for every EVM address
(`_GOPLUS_CHAIN_IDS = {"evm": 1, "solana": 101}`, `relayshield_api.py:2825`). The 2026-08-14 test in
this document established that GoPlus's malicious-address labels are cross-chain, so a Ronin drainer
that GoPlus knows about does come back flagged. That still rests on one address and three of the six
flag types, so it is strong evidence rather than proof.

**The gap: the `ronin:` prefix.** Ronin historically displayed addresses as `ronin:abc…` rather than
`0xabc…`. It is the *same* 20-byte address — purely cosmetic, no cryptographic difference — and
Ronin Wallet has since moved to showing `0x`. But legacy `ronin:` strings still circulate, dApps
still accept them, and **`_EVM_RE` anchors on `^0x`, so a pasted `ronin:` address is rejected** —
the bot answers "that did not look like a link or a wallet address."

There is **no Ronin handling anywhere in the codebase** (grepped `relayshield_api.py` and
`relayshield_telegram_webhook.py`: zero hits).

**Fix before pitching Lumiterra or The Machines Arena** — a one-line normalise in
`_looks_like_address`/`_normalize_url`, rewriting a leading `ronin:` to `0x`. Cheap, and the failure
mode without it is the worst kind: the bot looks broken to exactly the audience being courted, on
their own chain, in their own address format. Same class of check as the WAX gate, caught in time.

**DFK itself is unaffected** — DFK Chain is an Avalanche subnet and uses plain `0x`.

### ✅ FIXED 2026-08-21 — the Ronin gate is closed

`_RONIN_RE` and `_normalize_address()` in `relayshield_discord_bot.py` rewrite `ronin:<40 hex>` to
`0x<40 hex>` before the address shape test, so a pasted legacy address now gets a real verdict.
Normalising there rather than inside `check_wallet()` means the "Warn the channel" button carries
the normalised form too, so the re-check on click hits the same API path the first check did.
Mixed case and surrounding whitespace are handled; a malformed `ronin:` string is still rejected;
`ronin.example.com` still routes to the URL checker.

`relayshield_discord_bot.py` was also added to `deploy_lambdas.yml`'s `LAMBDA_MAP` as
`rs-discord-bot` the same day — before that it had **no CI deploy path at all**, so a repo-side fix
would never have reached the live bot.

**Ronin-game outreach is unblocked.** The recommendations below assume it.

## Recommended Ronin targets, in send order

Ronin is the single best chain on this list for the bot: one publisher (Sky Mavis) curates the
ecosystem, the games are Discord-native, and Q3 daily active wallets of 419K (+55%) say the players
are actually there. **Ordered by fit, and the order matters** — the first two are the pitch, the rest
are what you send only if those stall.

| # | Target | Band | Why this one, in this position |
|---|---|---|---|
| 1 | **Lumiterra** | In band | **Send first.** +9,451% active wallets in Q3 2025 means a server that is still growing into its moderation, which is exactly when an automated screening bot is welcome rather than redundant. Open-world survival with constant item trading is the highest address-and-link traffic on the chain. Smaller and hungrier than Pixels, so a partnership is a decision one person can make |
| 2 | **The Machines Arena** | In band | **Send second, and only after Lumiterra replies or goes quiet for a week.** A 4v4 hero shooter skews younger and more drainer-exposed, which is the strongest *safety* argument available — but it is also a harder audience to claim credit with. Do not run both in parallel: they are ecosystem neighbours and word travels |
| 3 | **Ronin ecosystem / Sky Mavis developer channels** | Publisher | The leverage play, not the volume play. One integration blessed by the publisher reaches every title at once. Slower, and it needs at least one live game reference first — which is precisely why it sits below Lumiterra rather than above it |
| 4 | **Pixels** | ~214K, **over the ceiling** | Ruled out on size by this document's own 50,000 rule, and that rule stands. Listed here only so it is not re-proposed: a server that size has staff moderators and an existing tooling stack, so the bot is a procurement conversation, not a favour |
| 5 | **Axie Infinity** | Far over | Same reason as Pixels, more so. Do not open |

**Pitch the bot, not rsscan** — the same reasoning that settled DFK applies unchanged. rsscan is
free and MIT-licensed, so there is nothing to negotiate; the bot serves players and has a
partnership shape.

**Lead with the `ronin:` fix, not with the corpus.** "We handle your chain's legacy address format
correctly" is a concrete, checkable claim these teams can verify in ten seconds, and it lands far
better than any indicator count. It also quietly says we did the work before turning up.

**Do not quote total corpus size.** Same rule as every other outreach in this repo, for the same
reason.

**The headwind still applies.** DeFi protocols are leaving Discord in 2026 (Morpho read-only from
1 Feb, DefiLlama moved to ticketed support). Games are stickier, but name it and turn it: teams
leave because they cannot screen what gets posted, and screening what gets posted is the product.

## DFK: no channels visible until you pass `#✅verify`

Confirmed from the server view — DFK runs a verification gate, with `#✅verify` under **Launchpad**
and everything else hidden until it is cleared. That is why the channel list looked empty; it is not
a permissions bug and not a sign of a dead server.

Live server stats read from inside: **55.6K total, 2.58K online (4.6%)**. That matches the
2026-08-14 invite-preview figures (55,661 / 5.4%) closely enough to treat both as sound — and it is
the *opposite* of the LAMINA1 and Overtime discrepancies, where the two sources disagreed sharply.

**Clear `#✅verify` first.** The partner channel cannot be found, let alone used, from outside the
gate, and the partner channel is the preferred route.

## Draft: DFK BizDev form submission

Route: `https://forms.gle/fv4y1G3ppNgJDpEDA`. **Use only if the partner channel is unavailable after
verifying.**

> **Nature:** Partnership / collaboration
> **Company:** RelayShield LLC
>
> I played DFK, and I now run RelayShield, a security company. I'd like to offer the DFK server a
> free Discord bot that screens links and wallet addresses against criminal threat-intel feeds.
>
> How it works: a player runs `/scan` on a suspicious link or address and gets a private answer,
> checked against our own criminal IOC corpus and external reputation sources. If it comes back
> flagged, they can push the warning to the channel with one click. There is also `/scam`, a short
> "am I being scammed" checklist.
>
> Two things that matter for a server of 55K:
>
> • **It cannot read your channels.** Slash commands only — no Message Content Intent, no gateway
> connection. It is structurally unable to see anything it wasn't explicitly invoked on, and I'd
> rather you verify that than take my word for it.
>
> • **It never says "safe."** A drainer domain registered an hour ago is in no database anywhere, so
> a clean result says exactly that and nothing stronger. Overclaiming here is how a security bot
> gets someone drained.
>
> Free, no data sharing, no contract, and happy to run it in a staging server first or walk the mod
> team through it before it touches the main server.
>
> Separately, and needing nothing from you: if your engineers want it, rsscan is our free MIT
> secret-scanner that blocks API keys and deployer keys at commit time rather than after a push —
> github.com/RelayShield/rsscan. No signup, runs locally.

**Why this shape.** It leads with the players, not the company. The "cannot read your channels"
paragraph is the strongest thing available given the 2026 climate of protocols abandoning Discord
over exactly that exposure, and the bot's own docstring says the refusal was designed as the pitch.
rsscan is one paragraph at the end, aimed at a different reader, and explicitly costs them nothing
to ignore.

## Guilds: yes, examples were added

Answering the question directly — the guild axis was added in part 1 of this session with three
named examples: **Yield Guild Games**, **GuildFi**, and **Merit Circle / Beam** (Beam.gg is the only
one with a measurement: 3,801 members, 2.2% online, in band but quiet). All three are **UNRESOLVED**
— no invite code, no verified count — because `discord.com` is egress-blocked here.

The standing recommendation is unchanged: **resolve and test exactly one guild** before treating
guilds as a category, on the lesson prediction markets taught at a cost of twenty-two lookups.
