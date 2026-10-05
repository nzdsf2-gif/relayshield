# Solana dApp Store — App Metadata Draft

## App Name
Crypto Shield

## Publisher
RelayShield LLC

## Short Description / Tagline (~80 char limit — check portal's exact limit)
Is your crypto email already in a leak? Check it free, then watch your wallets and your logins.

## Category
Utilities / Security (pick whichever the portal's category list calls closest to this — not Finance/DeFi, since this app doesn't move funds)

## Full Description

Most wallets are not drained by a clever contract. They are drained because the email
behind them was already in a leak, a session was stolen by infostealer malware, or a SIM was
swapped. Crypto Shield checks that off-chain layer as well as the chain.

**Try it before you decide anything.** Connect Phantom or Solflare (read-only, we only see
your public address) and your wallet is scanned straight away. Type in your email and get one
free check against breach records and infostealer logs. No account, no card, no key. The
result says what was found, or that nothing is known, which is not a promise nothing exists.

Crypto Shield is read-only security monitoring for Solana, EVM (including Base), TON,
Bitcoin, and XRP, built by RelayShield, a threat intelligence company that also protects
businesses and consumers against breaches, SIM-swap fraud, and infostealer malware.

<!-- SIM swap monitoring is listed below as of v1.6.0 (2026-10-03): Settings now
     posts /v1/sim-swap/enroll and the monitor delivers by push. The free email
     check and the connect-and-scan first run exist only as of v1.7.0 (2026-10-05).
     Paste this listing into the portal at the same time as the v1.7.0 build, never before:
     a listing that promises it while the live build cannot do it is the
     CSM-SIMSWAP-1 defect again, and the portal copy is not versioned. -->

We never ask for your seed phrase or private keys. Crypto Shield can't move your funds —
it watches your wallets and alerts you the moment something looks wrong.

**What it does:**
- Real-time wallet risk scanning across Solana, EVM (including Base), TON, Bitcoin, and XRP
- Address poisoning detection — catches look-alike addresses attackers use to trick you
  into copying the wrong address from your transaction history
- NFT security scanning — flags malicious/fake NFT contracts, not just floor prices
- NFT floor price tracking and alerts
- Criminal marketplace intelligence, collected continuously from monitored underground
  channels, infostealer log dumps and public indicator feeds, so you're flagged before you
  know you're a target
- One free email exposure check, and ongoing breach and infostealer alerts for your linked
  email with the 7-day free trial
- SIM swap monitoring — turn it on for your own number and get a push notification if your
  carrier reports a SIM change or a port-out (US carriers)
- Attack chain sequencing — see whether a breach, a SIM swap and a lookalike domain line up
  against you as one attack, instead of three unrelated alerts
- Signature Guard — token/NFT approval monitoring, transaction simulation before you sign,
  and session hijack detection
- Security Sweep — one-tap check across breach exposure, infostealer logs, and OAuth
  backdoors
- Real-time push notifications the moment a threat is detected

**Why it's different:** most wallet-security tools watch on-chain activity. Many real
attacks start off-chain: a leaked password, a stolen session, a SIM swap, long before a
malicious transaction is signed. Crypto Shield treats the credential layer and the chain layer
as one attack surface.

Every alert is cryptographically verified before it reaches your phone. RelayShield
carries active Tech E&O and Cyber Insurance coverage.

## Keywords (if the portal has a keywords/tags field)
wallet security, crypto security, address poisoning, NFT security, phishing protection,
breach monitoring, Solana wallet, transaction simulation, signature guard,
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
- **Subtitle** (50 char max): `Is your crypto email already in a leak?` (39 chars)
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
