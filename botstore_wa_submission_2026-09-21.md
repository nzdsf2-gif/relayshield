# botstore.info: DEAD END. DO NOT CONTACT THEM. Closed 2026-09-21.

**VERDICT: no. Dotgo is a WhatsApp Business Solution Provider selling the messaging service
we already buy from Twilio, and the Bot Store listing is a benefit of being their customer
rather than an open directory.**

`botstore.info/Whatsapp` is a sales page, not a submission route. Read off the founder's own
screenshots:

| What they charge | |
|---|---|
| Onboarding | $0 |
| Dotgo platform fee | "capped at $1,000/month" under a **promotion dated 2021**, so the current rate is unstated |
| Traffic | WhatsApp's own fee **plus** $0.001 per message to Dotgo |
| Bot with live agent software | $200/month, or $1,800/year |
| Each additional agent | $30/month |
| **Commitment period** | **1 year, on both the monthly and the annual plan** |

**Three reasons this is not close, in order of how much they matter:**

1. **It would mean moving our WhatsApp number to a different BSP.** Every WhatsApp path we
   have runs on Twilio: `get_twilio_credentials`, `send_whatsapp`, the signature
   verification, the templates. Migrating the number to Dotgo to obtain a catalogue row is
   a platform migration paying for a listing.
2. **A minimum of $2,400 a year on a one-year commitment**, before the platform fee whose
   real number is not published, to get a free directory listing. The entire point of the
   catalogue programme is that a listing is a standing shelf that costs nothing.
3. **A 2021 promotion still on the page in 2026** is not a live price. Asking would cost a
   round and the answer cannot change points 1 and 2.

**This is `@telegtapps` in a new costume, and it is a THIRD type this programme had not
named.** That one was a broker selling posts where no free route existed. This is a
directory that IS genuinely open for RCS bots, which we do not have, and gated behind a paid
platform relationship for WhatsApp, which we do. **"Open directory" was true, for a product
line that is not ours.**

**THE TYPE-CHECK QUESTION IS NOW THREE-WAY, not two.** Before submitting anywhere, ask which
of these it is:

    curated catalogue      a free submission route, reviewed, listed
    broker                 sells posts; the "listing" is an advertisement
    platform benefit       free ONLY to customers of the paid product beside it

The third is the hardest to see from outside, because its marketing is identical to the
first. **The tell is a Pricing page anywhere on the domain.** A real catalogue has no
pricing for the thing being listed.

**What was NOT wasted:** the WhatsApp bot now runs a keyless check for a stranger instead of
bouncing them, and `WA_NUMBER` is filled so every front-door link we own renders. Both were
prerequisites for any WhatsApp discovery surface, and both stand whatever happens to this
directory. **The listing copy below is kept for the next WhatsApp directory that has a free
route.**

---

## THE LISTING COPY, KEPT FOR A FUTURE DIRECTORY


**Link to give them**

```text
https://wa.me/<the number from step 1, digits only>?text=SRC_wa-botstore
```

Replace `<...>` with the digits. **That is a placeholder in a document, never in a command**
-- which is why step 1 prints it rather than this file carrying it.

**The `?text=SRC_wa-botstore` suffix is not optional.** WhatsApp has no deep-link payload,
so the token rides in the prefilled message body, and `parse_wa_source` reads it BEFORE the
user lookup and strips it from the message. There is **no allowlist** on that side, so the
key needs no registration anywhere -- but a listing pointing at a bare `wa.me/<number>` logs
nothing, leaves no `unmatched:` row to find later, and is indistinguishable from organic
traffic forever. **Omission is the unrecoverable mistake here.**

**Name**

```text
RelayShield | Scam & Breach Checker
```

**Category:** Security, or Utilities. Not Finance.

**Short description**

```text
Send a link or a wallet address and get a risk verdict back. Free, no account.
```

**Full description**

```text
RelayShield checks the things people are about to trust, and monitors the things an attacker needs to take over an account.

Send it a link or a cryptocurrency wallet address and it answers in seconds, free and with no account: the link is checked against Google Safe Browsing, a criminal indicator corpus and domain age, and the address is checked for drainer and scam-token signals across EVM, Solana, TON, Bitcoin and XRP.

It will never tell you something is safe. The most it says is that nothing is known against it, because an absence of evidence is not proof, and a checker that says "safe" is training you to trust the one it misses.

For people who want ongoing cover, it also monitors your email, phone number and wallets for data breaches, infostealer malware logs and SIM-swap attempts, and messages you here the moment something surfaces. It then walks you through the fix step by step: close the email backdoors, revoke the stolen sessions, and only then reset the password, which is the order that actually works.

Built by a telecom security professional with 25 years on the carrier side.
```

**Tags:** `security`, `scam-detection`, `anti-phishing`, `cryptocurrency`, `data-breach`,
`identity-protection`

---

## WHAT CHANGED SO THIS LISTING IS WORTH HAVING

**Until today the bot answered a stranger with "your account isn't set up yet, visit
relayshield.net".** Listing a bot that bounces everyone who arrives is worse than not being
listed: a directory row is a standing shelf, and the first impression is the only one.

**It now runs the check.** `keyless_check()` in `relayshield_whatsapp_webhook.py` sends a
link to `/v1/link-check` and an address to `/v1/wallet-risk`, both of which are keyless by
design -- no signup, no card, capped per source IP rather than billed -- so there was never
a commercial reason to refuse. It simply was not wired.

Two rules are inherited from `widget/relayshield_widget.py` and neither is negotiable:

- **It never raises.** Every failure path returns a string. A stranger's first message must
  not produce a stack trace and silence.
- **It never says "safe".** The ceiling on a clean answer is "nothing known against it".

And when there is nothing checkable in the message, the greeting **leads with the
capability and puts the signup last**. A test asserts that ordering, because leading with a
wall is what this branch used to do.

**KNOWN LIMIT, recorded rather than discovered later:** the keyless cap is per source IP and
every call leaves through the Lambda's egress address, so heavy use could throttle the whole
WhatsApp front door against itself. That is the same NAT problem that decided
`relayshield_watchlist_monitor.py` imports its handler instead of calling the public
endpoint. The 429 is handled explicitly and says "busy, treat it as unchecked" rather than
folding into a generic failure, so the log distinguishes the cap from an outage. **The fix,
if it ever fires, is an internal API key from Secrets Manager, not a retry.**

**AND A MEASUREMENT GAP, stated so it is not read as a zero later:** the API-side
`source=wa-frontdoor` on those calls lands in `/aws/lambda/relayshield-api` and is counted
by **neither** `tools/miniapp_funnel.py`'s CHECKED stage (it filters `tg-miniapp*`) nor
`tools/source_arrivals.py`'s two surfaces. The arrival-side `SRC_wa-botstore` IS counted, by
the funnel's WHATSAPP stage. So the number of people who arrive is measurable today and the
number of checks they run is not.
