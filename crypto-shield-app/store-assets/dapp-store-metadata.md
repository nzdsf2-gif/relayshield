# Solana dApp Store — App Metadata Draft

## App Name
Crypto Shield

## Publisher
RelayShield LLC

## Short Description / Tagline (~80 char limit — check portal's exact limit)
The only wallet security app that watches your credentials, not just your chain.

**DECISION OPEN, added 2026-08-10.** The Full Description below was rewritten on 2026-08-09 to
answer the doxxing concern head on. **The short description and the subtitle were not.** Both still
carry only the differentiator. Whether they should carry the privacy answer instead is a real
trade-off, not an oversight to fix blindly: the tagline is the only place the competitive
differentiator appears above the fold, and there is no room for both.

Note the current tagline is **exactly 80 characters**, so it has zero headroom if the portal's real
limit turns out to be lower.

Measured options, all under 80:

| # | Chars | Text |
|---|---|---|
| current | 80 | The only wallet security app that watches your credentials, not just your chain. |
| A | 72 | Wallet security that never links your email, phone and wallets together. |
| B | 74 | Read-only wallet security. Nothing about you is stored or linked together. |
| C | 71 | Watches your credentials and your chain. Never builds a profile of you. |
| D | 67 | Credential and chain security. Your details are never linked, ever. |

**Recommendation: keep the current tagline.** The privacy answer needs about three sentences to be
convincing, and 80 characters compresses it into a claim that reads like every other app's privacy
boilerplate. It is already carried properly in three places that a hesitant user actually reaches:
the Full Description, the onboarding screen at the exact point of collection, and the privacy
policy. Option C is the one to use if the founder wants it in the tagline anyway, since it is the
only one that keeps both halves.

## Category
Utilities / Security (pick whichever the portal's category list calls closest to this — not Finance/DeFi, since this app doesn't move funds)

## Store Description (SINGLE FIELD, revised 2026-08-10) — USE THIS ONE

**The Solana dApp Store portal has one description field, not a short plus a long.** This is the
copy to paste. The older "Full Description" further down is kept for reference only and **must not
be used**: it contains a claim that is false (see the correction note under it).

**Links verified live 2026-08-10** by HTTP status, not by memory:

| URL | Status |
|---|---|
| `https://privacy.relayshield.net` | **200**, renders "Privacy Policy \| RelayShield" |
| `https://terms.relayshield.net` | **200**, renders "Terms of Service \| RelayShield" |
| `https://relayshield.net/privacy` | **404** Carrd catch-all |
| `https://relayshield.net/terms` | **404** Carrd catch-all |
| `https://cryptoshield.relayshield.net` | **does not resolve** |

Both working URLs are already served by the existing Cloudflare workers
(`cloudflare_worker_privacy.js`, `cloudflare_worker_terms.js`). **No new worker or doc page is
needed.** Use the subdomains and never the apex paths.

```
Read-only wallet security for Solana, EVM, TON, Bitcoin and XRP. Starts with a 7 day free trial.

Crypto Shield watches your wallets by public address, and watches the credentials behind them. EVM coverage includes Base.

Continuous monitoring (subscription):
- Breach exposure for your linked email, checked against known breach corpora
- Infostealer log monitoring, which detects stolen session cookies and saved passwords traded on criminal marketplaces
- SIM-swap detection on your linked phone number, the common route around SMS 2FA
- OAuth backdoor and stale app-authorization checks
- Wallet activity monitoring with real-time push alerts

On-demand scans:
- Token and contract risk: honeypots, rug pulls, fake tokens, hidden transfer restrictions
- Airdrop scam detection
- NFT contract security and floor price tracking
- dApp and domain reputation
- Address poisoning detection, which identifies look-alike addresses planted in your transaction history
- Token approval review and transaction simulation before signing

Your credentials, handled:
- Email, phone and wallet addresses are stored encrypted on your device
- Each check goes to one provider, which sees one detail and nothing else
- Your identifiers are never linked together on our servers
- Remove a credential and it is deleted, along with its history
- Logs are kept 90 days and never record an identifier in readable form

Crypto Shield never requests your seed phrase or private keys and cannot move funds.

Credential and identity monitoring runs on RelayShield's threat intelligence infrastructure and requires an active subscription. Cancel any time from within the app.

Terms: https://terms.relayshield.net

Built by RelayShield, a threat intelligence company protecting businesses and consumers against breaches, SIM-swap fraud and infostealer malware.
```

**Why the privacy paragraph is worded the way it is, and what changed.** The earlier draft claimed
*"We do not store your email address or your phone number after a check returns."* **That is not
true and it must not ship.** `handle_watch_add` in `relayshield_api.py` writes `subject_value` in
plaintext to the verdict-watches table, and it has to: continuous monitoring cannot re-screen an
identifier it deleted. The privacy policy already gets this right ("an enrolled mobile number and
its carrier history are retained only while the number stays enrolled, and are deleted when you
remove it"), so the old store copy contradicted our own published policy. The replacement claims
only what is true and verifiable: encrypted on-device storage, one detail per provider, no linkage,
deletion on removal, 90 day logs with hashed identifiers. Every one of those is backed by the live
policy text.

## Full Description (SUPERSEDED 2026-08-10, DO NOT USE)

**Contains the false retention claim described above.** Kept only so the change is auditable.

Crypto Shield is read-only wallet security monitoring for Solana, EVM (including Base),
TON, Bitcoin, and XRP, built by RelayShield, a threat intelligence company that also
protects businesses and consumers against breaches, SIM-swap fraud, and infostealer malware.

We never ask for your seed phrase or private keys. Crypto Shield can't move your funds. It
watches your wallets and alerts you the moment something looks wrong.

**What it does:**
- Real-time wallet risk scanning across Solana, EVM (including Base), TON, Bitcoin, and XRP
- Address poisoning detection: catches look-alike addresses attackers use to trick you
  into copying the wrong address from your transaction history
- NFT security scanning: flags malicious/fake NFT contracts, not just floor prices
- NFT floor price tracking and alerts
- Criminal marketplace intelligence: 95 monitored underground channels where stolen data
  and drainer kits are traded, so you're flagged before you know you're a target
- SIM-swap and breach exposure alerts for your linked email/phone
- Signature Guard: token/NFT approval monitoring, transaction simulation before you sign,
  and session hijack detection
- Security Sweep: one-tap check across breach exposure, infostealer logs, and OAuth
  backdoors
- Real-time push notifications the moment a threat is detected

**Why it's different:** every competing wallet-security product watches on-chain activity
only. Most real attacks start off-chain, with a leaked password, a phished session or a
SIM swap, long before a malicious transaction ever gets signed. Crypto Shield is the only
consumer product that treats the credential layer and the chain layer as one attack surface.

**About the email and phone number we ask for.** Monitoring your credentials means we have
to ask for the credentials being monitored, and that deserves a straight answer rather than
a privacy policy link.

They are stored encrypted on your own device. They are the questions we ask on your behalf,
not a profile we keep. We do not store your email address or your phone number after a check
returns. We keep wallet addresses only because alerting you to activity on them requires
knowing what to watch, and a wallet address is already public on the chain.

Each check goes to the single provider that can answer it, and each one sees a single detail
and nothing else. The provider that checks your phone number never learns your email. The one
that checks your email never learns your number. Neither ever learns your wallets. Your
identifiers are never linked together anywhere except on your own device, which means there
is no profile of you for us to lose, leak, or be compelled to hand over.

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
- **Subtitle** (50 char max): `Watches your credentials, not just chain` (40 chars)
  - Same open decision as the tagline above. Measured alternatives if the privacy answer is wanted
    here: `Credentials + chain. Never linked together.` (43),
    `Credentials and chain. We keep no profile.` (42),
    `Watches credentials, keeps no profile` (37).
    Same recommendation: keep the current one.
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
