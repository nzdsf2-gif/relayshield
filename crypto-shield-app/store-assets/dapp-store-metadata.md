# Solana dApp Store — App Metadata Draft

## App Name
Crypto Shield

## Publisher
RelayShield LLC

## Short Description / Tagline (~80 char limit — check portal's exact limit)
The only wallet security app that watches your credentials, not just your chain.

## Category
Utilities / Security (pick whichever the portal's category list calls closest to this — not Finance/DeFi, since this app doesn't move funds)

## Full Description

Crypto Shield is read-only wallet security monitoring for Solana, EVM (including Base),
TON, Bitcoin, and XRP — built by RelayShield, a threat intelligence company that also
protects businesses and consumers against breaches, SIM-swap fraud, and infostealer malware.

We never ask for your seed phrase or private keys. Crypto Shield can't move your funds —
it watches your wallets and alerts you the moment something looks wrong.

**What it does:**
- Real-time wallet risk scanning across Solana, EVM (including Base), TON, Bitcoin, and XRP
- Address poisoning detection — catches look-alike addresses attackers use to trick you
  into copying the wrong address from your transaction history
- NFT security scanning — flags malicious/fake NFT contracts, not just floor prices
- NFT floor price tracking and alerts
- Criminal marketplace intelligence — 80+ monitored underground channels where stolen data
  and drainer kits are traded, so you're flagged before you know you're a target
- SIM-swap and breach exposure alerts for your linked email/phone
- Signature Guard — token/NFT approval monitoring, transaction simulation before you sign,
  and session hijack detection
- Security Sweep — one-tap check across breach exposure, infostealer logs, and OAuth
  backdoors
- Real-time push notifications the moment a threat is detected

**Why it's different:** every competing wallet-security product watches on-chain activity
only. Most real attacks start off-chain — a leaked password, a phished session, a SIM-swap
— long before a malicious transaction ever gets signed. Crypto Shield is the only consumer
product that treats the credential layer and the chain layer as one attack surface.

Every alert is cryptographically verified before it reaches your phone. RelayShield
carries active Tech E&O and Cyber Insurance coverage.

## Keywords (if the portal has a keywords/tags field)
wallet security, crypto security, address poisoning, NFT security, phishing protection,
SIM swap, breach monitoring, Solana wallet, transaction simulation, signature guard,
XRP wallet, Base chain, lookalike token detection

## Portal form field values (publish.solanamobile.com — confirmed 2026-07-04, revised 2026-08-01)
- **dApp Name** (25 char max): `Crypto Shield`
  - **DO NOT CHANGE THIS NAME.** Release NFTs are minted as `<dApp Name> vX.Y.Z`, and the
    in-app update check (`/v1/app/cs-mobile-latest-version`) finds releases by matching the
    `Crypto Shield` prefix against everything the publisher has minted. Rename the app and the
    update nudge silently stops firing — the exact failure v1.5.0 exists to fix.
- **Package Name**: `net.relayshield.cryptoshieldmobile`
  - Changed 2026-08-01. The old `net.relayshield.cryptoshield` record cannot be reused for
    v1.5.0 — its signing certificate is unrecoverable and rotation is unsupported, so this
    ships as a NEW dApp record. Leave the old record live until this one is approved.
- **Publisher wallet**: `E64PiTT7U8ZUWFKdkrBFw1YzdD2bU1gKcuGnBRVqp7M6` (`E64P...p7M6`) —
    must be the same publisher, both to keep the publisher account and because the update
    check looks up releases by this authority.
- **Subtitle** (50 char max): `Watches your credentials, not just chain`
- **dApp Icon (512x512)**: `dapp-store/icon-512.png`
- **Banner (1200x600)**: `dapp-store/banner-1200x600.png`
- **dApp Preview (min 4)**: all 5 files in `screenshots/` (1080x2400, matching)

## Support / Contact
relayshieldadmin@gmail.com

## Privacy Policy URL
https://privacy.relayshield.net

**Corrected 2026-08-01.** The previously listed `https://relayshield.net/privacy` returns a
**404** (Carrd catch-all "Page not found") — verified live. Same class of mistake as the
developer-URL rule: the apex domain is a Carrd site and does not serve these paths; the
content lives on a subdomain. `https://privacy.relayshield.net` returns 200 with the real
policy. A dead privacy URL is a standard review rejection, so do not submit the old one.
