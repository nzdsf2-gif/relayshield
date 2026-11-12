# The right address led to the wrong site: the Name.com DNS hijack

November 10, 2026

Late on Friday, October 30, the usual safety advice stopped working. Visitors typed the correct address of a DeFi site they trusted and landed on a copy built to drain their wallets. The address bar was right. The site was not.

The common thread was the domain registrar. Security firm Blockaid flagged token launch site Flap and staking app Kintsu, then listed ten more sites it said were serving the Step Drainer kit, a ready-made tool that tricks visitors into signing away their funds. The list included Pickle Finance, Origami Finance, Echelon, FluxBeam and StonkFun. The Block found in public registry records that all twelve were registered through Name.com. Name.com confirmed on X on October 31 that some customer domains "were improperly redirected late Friday as part of a plan to access visitors' crypto wallets," and said they had been restored. In a statement to The Block, Name.com put the number of affected customer domains at fifteen. Website host Vercel said it knew of nine impacted domains tied to its platform. Name.com's November 3 incident report says the changes came from a support account, made through ordinary management tools between 00:35 and 01:18 UTC on October 31. Its investigation found no exploit of Name.com's infrastructure, and it had not determined whether the support account was deliberately misused or its credentials were compromised.

The two tallies measure different things. The Block traced about $138,000 to three attacker wallets on Ethereum-style networks. Bitquery, which counted what each victim lost rather than what the attackers held, put the figure at about $202,000 taken from 32 wallets, most of it from a single Kintsu user on Monad. Neither tally includes Solana or Aptos, where some of the sites also run.

The projects that have spoken say the attack was limited to their websites; their smart contracts were not touched. Kintsu said its smart contracts were not compromised, and Origami Finance said none of its users' funds were. Origami reopened its vaults on November 1. Kintsu paused deposits and withdrawals of its sMON token on October 31 and said recovering stolen funds "is not yet guaranteed."

## Why this one is different

Most wallet-drainer scams need you to make a mistake: click a fake link, mistype an address, trust a sponsored search result. Here, the address was right. DNS is the internet's address book, and the attackers changed the entry, so the correct name led to the attacker's server. The page looked normal. The main warning sign was what the wallet asked you to approve.

Kintsu added a detail worth knowing: the attack used a wallet "delegation" signature, the kind that lets another contract act on behalf of your account. Cancelling token approvals afterward does not undo that, so Kintsu told affected users to move their funds to a new wallet with a new recovery phrase.

## What RelayShield monitoring is built to catch

To be clear: this post is based on public reporting from The Block, Bitquery, Blockaid, Name.com and the affected projects, not on a RelayShield catch, and it does not claim these specific domains are in the RelayShield corpus.

What RelayShield monitoring is built to surface is the ecosystem around an attack like this. Drainer kits, hijacked domains and the stolen funds they produce circulate through the Telegram marketplaces RelayShield watches: 139 marketplaces, 800K+ indicators, 10.9M citations. The Telegram and WhatsApp bots and the free checks let you screen a suspicious link before you connect a wallet, and rescan lets you check a URL again as its infrastructure changes. That matters here: a site that was clean yesterday can be hijacked today.

## The one rule

Read the wallet prompt before you sign it. A swap or a deposit should never ask for permission over all your tokens, or to hand control of your account to another contract. If the request is broader than what you are doing, reject it, and keep the money you cannot afford to lose in a wallet that never connects to websites.

If you visited one of these sites between the evening of October 30 and the morning of October 31, Eastern time, follow that project's instructions. If you signed anything, move what is left to a new wallet, and do not trust anyone who messages you offering to "recover" funds. No one legitimate needs your recovery phrase.

---
Sources: The Crypto Guide, "Name.com DNS Hijack Hit DeFi Sites: What Users Should Do" (Nov 1, 2026), reporting on The Block (Oct 31, 2026), Bitquery (Oct 31, 2026), Blockaid community alerts (Oct 31, 2026), Name.com statement on X (Oct 31, 2026), Vercel security notice, Kintsu incident update (Oct 31, 2026), Origami Finance update (Nov 1, 2026).
