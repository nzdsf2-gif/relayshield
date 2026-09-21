# botstore.info: submit the WhatsApp bot. Not the Telegram one.

**botstore.info is Dotgo's Bot Store: "World's First and Only Open and Global Directory of
RCS and WhatsApp Bots."** Read off its own homepage rather than inferred.

**THE TELEGRAM BOT DOES NOT GO HERE.** A Telegram bot is neither an RCS bot nor a WhatsApp
Business bot, and submitting it is the type-check failing in the same way `@telegtapps`
did. `@relayshield_bot` belongs on tg.app, tgboard and StoreBot, where it already is or is
queued.

**AND THE FORM IN YOUR SCREENSHOT IS THE WRONG ONE.** "Create an account. It's free." with
a mobile number as the user id, a carrier and RCS notification preferences is the CONSUMER
signup: it lets you browse and rate bots. Finishing it would not have let you list
anything. The listing route is in the dark nav bar: **"Do You Develop Bots?"** and
**"Become an RBM Partner"**.

---

## STEP 1 -- ANDREW RUNS THIS. Get the number, and fill it everywhere.

The listing needs the WhatsApp number, and `WA_NUMBER` is still the empty string in both
Workers, so every front-door link we own currently renders as nothing.

    cd ~/dev/relayshield
    AWS_PROFILE=relayshield python3 tools/wa_front_door_link.py --write

EXPECT: the number printed in E.164, and `cloudflare_worker_blog.js`,
`cloudflare_worker_miniapp.js` and the developers page reported as updated.
STOP IF: `ExpiredToken` or `AccessDenied` -- a fact about the AWS session, not about the
secret. Re-auth and re-run.
STOP IF: it refuses to print a link. It refuses anything that is not E.164 rather than
emitting one that would pass a probe and reach nobody: **`wa.me` answers a malformed number
with HTTP 200 and an "invalid" page**, so a broken front door looks live to every check we
own.

**It never prints the raw SecretString**, only the number, so this is safe to run with the
terminal visible.

Then commit and push so the links deploy:

    cd ~/dev/relayshield
    git add cloudflare_worker_blog.js cloudflare_worker_miniapp.js relayshield_developer_signup.py
    git commit --no-edit -m "Fill WA_NUMBER so the front-door links render"
    git push -u origin main

## STEP 2 -- ANDREW CLICKS THIS. The developer route, not the consumer one.

`botstore.info` -> **"Do You Develop Bots?"** in the dark nav bar.

**Search their catalogue for `relayshield` first.** tg.app keys one listing per bot and a
second submission collides rather than adds; nobody has established whether this one does,
and the check costs ten seconds.

**If the only route offered is "Become an RBM Partner", stop and tell me.** RBM is Google's
RCS Business Messaging, which is a carrier-side programme with an onboarding process, not a
directory form. That is a different and much larger commitment than a listing, and it is
not worth making to get a row in a catalogue.

## STEP 3 -- the listing copy

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
