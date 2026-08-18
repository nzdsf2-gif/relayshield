# Mid-size Discord pipeline, built and verified 2026-08-13

*Supersedes the empty "Tier 2" section in `discord_server_targets.md`. Every member count below was
resolved live today against Discord's unauthenticated invite-preview endpoint, the same one
`_queue_discovered_discord_invites()` uses.*

---

## First, the correction that matters

`discord_server_targets.md` says to check `relayshield_intel_discord_channels` before doing any
manual searching, and calls the member counts in it "a ready-made shortlist."

**That table holds exactly one row.**

| guild | members | found via | first seen |
|---|---|---|---|
| `rugpullbot.com - SOL & BSC` | 2,332 | Telegram channel `letmerug` | 2026-08-01 |

One lead in two weeks. And the reason is not a bug in the harvester, which I read and which works
correctly. **It is the wrong corpus, by construction.**

That pipeline scans the message text of the criminal Telegram channels we monitor for threat
intelligence. So the only Discord servers it can ever surface are servers advertised *inside
criminal Telegram channels*. The one lead it produced is a rug-pull-detection bot shop, which is
what that population looks like. Those are not communities that would install a protective bot.
They are either competitors or the thing we protect people from.

**Repurposing that table as a sales lead list is a category error.** It was built to find criminal
infrastructure to monitor, and it is good at that. Stop treating it as the Tier 2 source. Do not
spend another hour waiting for it to fill up.

---

## CORRECTION, later on 2026-08-13: the founder is in none of these

Reading the founder's actual Discord membership (69 servers) showed that **not one of the 14
verified candidates below is a server he is already in.** Every one of them would be a cold start:
join, build standing, then ask. That is the expensive path.

**Servers he is ALREADY in, that fit better precisely because standing already exists:**

| Server | Fit |
|---|---|
| **LEAP WALLET** | A wallet community. Members hold addresses and paste links daily, which is exactly what `/scan` serves. Best product fit available. |
| **Suiet** | Sui wallet. Same shape. |
| **Ctrl** | Wallet, formerly XDEFI. Same shape. |
| **Blue Team Village** | Security practitioners. Wrong audience for the bot, right audience for rsscan and the API. |
| **MSPGeek** | Budget-holding audience, but for Bundle A rather than the bot. Self-promo policy still unknown; ask a mod first. |

Also present and relevant to other workstreams: Coinbase Developer Platform (held for the x402
post), n8n, MCP Contributors, PayAI Network (recorded as not a channel), Wormhole, Sui, Sei,
Injective, Osmosis, Astroport, Kujira, Dymension, Eclipse, Solayer, LayerZero, ZKsync, CoinGecko,
Coin Bureau, The Defiant.

**Use the list below only after the already-joined servers are exhausted.** Member counts in it
remain accurate and the resolver method is still the right one for any new candidate.

## THE FOUR TARGETS, decided 2026-08-13

Chain support decides the shortlist before anything else. `/scan` handles **EVM, Solana and Bitcoin
only** (`_looks_like_address` is `_EVM_RE | _SOL_RE | _BTC_RE`). That rules out every Sui, Cosmos,
Aptos and NEAR community, including Suiet, which was briefly recommended here on "wallet community"
pattern-matching without checking chain support. It was wrong.

Solana gaming, NFT and collectible communities are the right hunting ground: wallet-dense audiences
whose entire activity is connecting wallets and clicking links, and a permanent scam problem.

| Rank | Server | Members | Online | Online % | Why |
|---|---|---|---|---|---|
| 1 | **Famous Fox Federation** | 15,279 | 1,365 | **8.9%** | Active Solana NFT utility community. Best engagement-to-size ratio in the set |
| 2 | **DRiP** | 6,615 | 895 | **13.5%** | Highest engagement of all. Solana collectibles, wallet-native, small enough that one person decides |
| 3 | **Claynosaurz** | 31,241 | 1,729 | 5.5% | Large Solana NFT and gaming community |
| 4 | **Parcl** | 49,594 | 1,462 | **2.9%** | Founder's pick. Biggest roster in band, but the quietest room here. High ceiling, low certainty |

### Ruled out, and the reason matters more than the names

**The question is not size, it is who decides.** A company-run server with staff moderators does not
add an outside bot. A project community where one identifiable person decides will consider it.

| | Why not |
|---|---|
| **Backpack** and **Mad Lads** | **The same organisation.** And Backpack is a wallet: asking a wallet company to install third-party wallet security implies their own wallet does not protect users. Structurally unacceptable to them |
| **Jupiter** | Company-run with staff mods. Less conflicted than Backpack, but its 5,041-member server is tiny next to the protocol, so the real community is elsewhere |
| Star Atlas 162k, STEPN 201k, MixMob 50k | Over the band. Reach only, never an install ask |
| Genopets, Honeyland, DeFi Land | ~1.0 to 1.2k. At the floor; an install is worth little |

### Three vanity codes resolved to the WRONG server

Guessed codes mis-resolved at a 20% rate on 2026-08-13, which is the whole argument for the
official-site rule:

| Guessed | Actually resolved to |
|---|---|
| `sharky` | "Bubcus", 14 members |
| `hxro` | "@херо inctv", Cyrillic, 1,125 members |
| `smb` | **"SMB Panel, Social Media Botting"**, 6,719 members, a spam service |

Pitching any of those would have been actively embarrassing. **Confirm every invite from the
project's own website before contacting anyone.**

## The verified list

Resolved live 2026-08-13. `online %` is `approximate_presence_count / approximate_member_count`,
which the four criteria in the targets doc did not include and which turns out to be the most
useful single discriminator: it separates a community that is alive from a member count that
accumulated during a mint three years ago.

### In the 1,000 to 50,000 band, ranked for conversion

| Server | Members | Online | Online % | Why it qualifies |
|---|---|---|---|---|
| **Raydium Protocol** | 44,285 | 2,497 | 5.6% | Largest in-band Solana DEX community. Members trade unknown tokens, so "is this contract real" is a live daily question. |
| **Kamino** | 30,565 | 2,394 | 7.8% | Lending, high engagement for its size, address-heavy conversation. |
| **Tensor** | 26,827 | 2,045 | 7.6% | NFT marketplace. NFT communities are the canonical scam-link environment. |
| **Metaplex** | 22,200 | 1,277 | 5.8% | NFT standard. Half community, half developer, so it serves both plays. |
| **Jito Developers** | 21,646 | 2,448 | **11.3%** | Highest engagement in the set. Developer-weighted, so strong for the admin-reach play. |
| **Solflare** | 21,450 | 830 | 3.9% | **A wallet.** Best product fit in the whole list: every member holds addresses and pastes links. |
| **Orca** | 20,930 | 332 | 1.6% | In band, but the low online share suggests a quiet server. |
| **Helius** | 19,959 | 254 | **1.3%** | RPC provider, developer audience, but the lowest engagement here. Ticket-driven, not conversational. |
| **Save (formerly Solend)** | 17,587 | 728 | 4.1% | Rebranded, so the community has been through a name change, which usually means active moderation. |
| **Step** | 11,126 | 502 | 4.5% | Portfolio tracker. Address-centric audience. |
| **Jupiter Exchange** | 5,041 | 179 | 3.6% | Small server for a very large protocol, so one person almost certainly decides. |
| **Drift** | 4,681 | 197 | 4.2% | Perps community. Same shape as Kamino at a size where the ask is easier. |
| **Anchor** | 1,294 | 218 | **16.8%** | Tiny and extremely engaged. Pure developer. Reach play, not a `/scan` play. |
| **Sanctum** | 1,263 | 140 | 11.1% | Small, engaged, liquid-staking. Easiest yes on the list. |

### Over 50,000: reach only, do not ask for an install

| Server | Members | Online |
|---|---|---|
| Magic Eden | 179,463 | 5,598 |
| Solana Tech | 148,878 | 6,062 |
| Meteora | 69,307 | 5,035 |
| **Solana Mobile Community** | **68,882** | **6,168** |
| Backpack | 61,605 | 4,421 |

Solana Mobile is in this band, which confirms the sequencing already decided: it is a reach post
aimed at admins in the audience, never an install ask. See `discord_solana_mobile_post.md`.

### One resolved result that proves why the invite rule exists

The vanity code `phantom` resolves to a server named `/phantom` with **77 members**. Phantom is one
of the largest wallets on Solana. That is not their community.

A plausible-looking vanity code resolved to something that is almost certainly squatted or
unrelated. This is exactly the failure the hard rule in `discord_server_targets.md` prevents:
**get the invite from the project's own official website, never from a directory and never by
guessing a vanity code.** Every code above was guessed for measurement purposes and must be
re-confirmed from the official site before it is used for anything.

Codes that returned 404 and tell us nothing either way: `marginfi`, `zeta`, `mangomarkets`,
`squads`, `dialect`, `tiplink`, `wormhole`, `pyth`, `switchboard`, `lifinity`. Those projects
mostly do have Discords; their invites are just not on a guessable vanity.

---

## What I could verify and what I could not

Being explicit, because two of the four qualification criteria cannot be checked from outside.

| Criterion | Status |
|---|---|
| 2. Between 1,000 and 50,000 members | **Verified live** for all 14 above |
| 1. Scam links are a visible, unsolved problem | **Not verified.** Requires reading two weeks of their general and support channels, which requires joining |
| 3. An identifiable, reachable admin | **Not verified.** Requires being in the server to see the mod list |
| 4. They already run third-party bots | **Not verified**, and see the competitive finding below |

So this is a verified *shortlist*, not a qualified list. The next step per server is roughly ten
minutes: join, read the general channel, look at the member list for existing bots, identify who
moderates.

**Suggested first five**, weighting product fit and ease of getting a decision over raw size:
Solflare, Sanctum, Drift, Jupiter Exchange, Tensor.

---

## Competitive finding that changes the pitch

**[SecurityBot](https://securitybot.info/) already exists and does approximately this.** Web3 scam
prevention on Discord: phishing-link detection, scam wallet address blocking, staff impersonation
prevention, and a **scammer database shared network-wide across every server it protects**.

Two consequences, and both should be absorbed before any admin conversation:

1. **Criterion 4 cuts both ways.** "They already run third-party bots" was on the list because it
   means the trust objection is already answered. But in a crypto server the bot they already run
   may well be this one, and then the slot is occupied and we are the second scam bot in the room.
   **Check the member list for SecurityBot specifically before pitching.**
2. **The network-effect claim is theirs, not ours.** A shared cross-server scammer database is a
   better story than anything we can currently tell about breadth on Discord, and we should not
   walk into a conversation claiming novelty we do not have.

Where we are genuinely different, and it is worth being narrow and accurate about it: they are a
moderation bot that reads and blocks. We are a query tool that **deliberately does not request the
Message Content Intent**, which means we are structurally unable to read a server's messages. That
is a weaker product in a moderation frame and a stronger one in a privacy frame, and privacy is the
frame a paranoid crypto admin is actually in. It is also the sentence that has been carrying the
whole pitch already.

Our second real difference is the intelligence behind `/scan`: criminal IOC feeds and stealer-log
derived data rather than a community-reported scam list.

---

## The pipeline, as a repeatable thing rather than this one list

The method that produced the table above, so it does not have to be reinvented:

1. Collect candidate invite codes **from official project websites**.
2. Resolve each with the unauthenticated preview endpoint. No bot token, no auth:
   `GET https://discord.com/api/v10/invites/<code>?with_counts=true`
   Returns `guild.name`, `guild.id`, `channel.name`, `approximate_member_count`,
   `approximate_presence_count`.
3. Filter to 1,000 to 50,000 members.
4. Rank by online percentage, not by member count.
5. Then do the ten minutes of manual qualification per server that no endpoint can do for you.

A working script is at `scripts/resolve_discord_invites.py` (added today). It takes codes on the
command line or from a file and prints the ranked table.

**Honest limit, unchanged and worth not forgetting:** consumer crypto Discord users have no budget.
This channel will not produce direct revenue. Its value is the 75-server threshold that unlocks the
Discord App Directory, and reaching admins who happen also to be security practitioners with a work
budget.
