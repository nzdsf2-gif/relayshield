# StoreBot.me submission — RelayShield Telegram bot

**Destination:** `storebot.me/add-bot/`
**Decision: submit the BOT, not the Mini App.** Reasoning at the bottom.
**Attribution key: `storebot`**, registered in `_SOURCE_BANNERS` and in the funnel
before this file existed.

---

## Paste these into the form, field by field

**First Name**

    Andrew

**Last Name**

    Gibbs

**Your Email**

    andrew@relayshield.net

**Bot Title**

    Scam Checker | RelayShield

**Upload Bot Image** — accepted: jpg, png, gif. Use the file already in the repo:

    assets/miniapp/idcheck_icon_512.png

512x512, RGB, no alpha, 65 KB against their 256 MB cap. **Select it from the
Finder window the merge opens; do not use a copy downloaded from a chat, which
arrives re-encoded as `.webp` and cannot even be selected in a jpg/png picker.**

**Bot Direct Link**

    https://t.me/relayshield_bot?start=SRC_storebot

**Telegram URL**

    https://t.me/relayshield_bot

**Website URL**

    https://api.relayshield.net/developers?source=storebot

**Twitter URL** — leave EMPTY. `@RelayShieldHQ` is suspended and linking a dead
account from a public listing is worse than linking nothing.

**Facebook URL / Vkontakte URL** — leave empty.

**Blog URL**

    https://blog.relayshield.net

**Bot Status**

    Online

**Bot Description**

    Check a link, a wallet address or a suspicious message before you act on
    it. Free, no signup, and it never claims something is safe.

**Bot Info**

    RelayShield tells you whether something you were sent is known to be
    dangerous, and monitors your identity for the things you cannot see.

    Check anything, free and without an account:
    - Paste a link and get it screened against a criminal indicator corpus
      collected from Telegram marketplaces, Google Safe Browsing, and domain
      registration age. A domain registered eleven days ago is worth knowing
      about.
    - Paste a wallet address (EVM, Solana, TON or Bitcoin) and get it screened
      against the same corpus.
    - Forward a suspicious message straight to the bot. No command needed.
    - Send a screenshot of a text message and it will read it.

    Monitoring, if you want it:
    - Breach and infostealer alerts for your email addresses.
    - SIM swap and port-out detection for your phone number.
    - Lookalike domain scanning for a company domain.

    The Mini App adds a TON watchlist: three addresses free, re-checked every
    few hours, with an alert the moment liquidity, balance or contract code
    changes. Open it with /app, or at t.me/relayshield_bot/idcheck

    One thing we will not do: tell you something is safe. A check that finds
    nothing means nothing is known against it, which is not the same thing,
    and the bot says so in those words every time.

**Bot Commands** — taken verbatim from `_BOT_COMMANDS_BASE`, which is the
table `setMyCommands` actually registers, not from memory:

    /start - Set up monitoring, or start checking straight away
    /quickstart - Three things you can do right now
    /app - Open RelayShield IDCheck - scan a link or wallet address
    /scan - Check a link, message or screenshot
    /scam - Suspicious message, bot, or call? Get guidance
    /infostealer - Check if an email was stolen by malware
    /breach - Breach monitoring status
    /sweep - Close email backdoors and sign out hijacked sessions
    /extensions - Audit browser extensions for infostealer malware
    /reuse - Cross-account password reuse check
    /otp - Unexpected OTP guidance
    /sim - SIM swap monitoring status
    /phone - Carrier hardening against SIM swap and smishing
    /tgsecurity - Telegram security: harden, linked devices, check a bot
    /verify - Callback rule, OTP rule, safe word, wire transfer protocol
    /plan - Your license type and upgrade options
    /help - This menu

---

## NOT FOR PUBLICATION — why the bot and not the Mini App

**StoreBot is a BOT directory.** The form's required fields are Bot Direct
Link, Bot Status, Bot Commands. A Mini App has no commands and no online/offline
state, so three of its fields would be empty or invented.

**And the bot's cold start is a good first impression, which was checked rather
than assumed.** `msg_welcome()` in `relayshield_telegram_webhook.py` greets a
new chat with what the product does and an intent keyboard, and asks "Who are
you protecting?" It does not demand a phone number, a payment or an email before
it says anything useful. A directory visitor lands somewhere sensible.

**The Mini App is named inside Bot Info and reachable from the bot**, so the
listing does not cost us that surface. Three catalogues already carry
`t.me/relayshield_bot/idcheck` directly.

**THE ONE THING THAT COULD GO WRONG, from the tg.app lesson:** a catalogue may
key a listing on the BOT USERNAME and allow only one per bot. If StoreBot
already holds a RelayShield card, or refuses this one as a duplicate, that is
the same constraint and not a new problem. Search `storebot.me` for RelayShield
before filling the form; if a card already exists, the action is a correction
request to their contact form, not a second submission.

**THE `?start=SRC_storebot` PAYLOAD IS THE HALF THAT IS INVISIBLE WHEN IT IS
WRONG.** The bare `t.me/relayshield_bot` in the Telegram URL field is correct
and deliberate -- that field is an identity, not a tracked link. The Bot Direct
Link is the one a visitor taps, and it is the only thing that writes
`acquisition source=storebot` into the webhook log. If it is submitted without
the payload, every arrival it produces is real and uncountable, which reads in
the funnel exactly like a listing nobody clicked.

**Take the baseline BEFORE the listing goes live:**

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --snapshot before-storebot

It refuses to overwrite, so a late one cannot quietly become a comparison of a
number with itself.

**I INVENTED A COMMAND IN THE FIRST DRAFT OF THIS FILE, ONE TURN AFTER WRITING
THE RULE ABOUT IT.** The list said `/watch`, `/wascam` and `/simswap`. The real
Mini App command is `/app`; `/wascam` and `/simswap` are handler aliases that
`setMyCommands` never registers, so a user reading them in a public listing
would type a command their own Telegram menu does not offer. The list above is
now generated from `_BOT_COMMANDS_BASE` by `ast`, which is the table the bot
actually registers. **A command list is a published artefact: read it out of
the code, never out of memory.**

**UNVERIFIED from the container:** `storebot.me` is egress-blocked here, so the
form fields above are read from the founder's screenshots and the character
limits on Bot Description and Bot Info are unknown. If either is truncated on
submission, cut from the bottom -- both are written so the first two lines carry
the whole claim.
