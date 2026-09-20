# tgboard.com: three listings, one key, never submitted before

**Checked 2026-09-20: `tgboard` appears NOWHERE in this repository** -- not in any `.json`,
`.md`, `.py` or `.js`, not in `miniapp_routes.json`, not in `bot_directories.json`, not in
any of the ten submission records. **This is a new destination.**

That is a claim about the repo, which is the only thing I can check. It is not a claim about
tgboard's database: they may already carry a RelayShield entry they built themselves, which
is what section 1 exists for.

Catalogue #6. Its form is the **tg.app shape** -- separate Type tabs for Channels, Bots,
Mini-apps, Groups and Stickers -- and tg.app is the one catalogue that has actually gone live
for us, twice. So the tg.app playbook applies unchanged.

**The key `tg-miniapp-tgboard` is registered in all three lists as of this commit**, before
anything is submitted: `miniapp_routes.json` rank 18, `ALLOWED_SOURCES` in
`cloudflare_worker_miniapp.js`, `_SOURCE_ALIASES` in `relayshield_developer_signup.py`. An
unregistered Mini App key is silently downgraded to the generic `tg-miniapp` at the Worker's
edge and logs `unmatched:` on the landing page, which is attribution that looks like it
worked. **It must be MERGED AND DEPLOYED before you submit** -- see section 6.

---

## 1. FIRST, SEARCH THEIR CATALOGUE. Ten seconds, and it has been skipped five times.

**ANDREW CLICKS THIS, before opening the Add form:** tgboard's own search box, for
`relayshield` and for `RelayShield IDCheck`.

tg.app taught this the expensive way: it keys **one listing per bot username**, so the Mini
App and the bot were the same slot to it, and a second submission is a collision rather than
an addition. If tgboard already carries an entry, adding a second makes a duplicate we then
have to get removed.

**If the search returns nothing, proceed. If it returns something, send me what it shows**
and we claim or correct rather than create.

---

## 2. The Mini App

Type tab: **Mini-apps**

**t.me link**

```text
https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-tgboard
```

### THE LINK FIELD REFUSED THIS. MEASURED 2026-09-20.

    Invalid or private t.me link

**Their validator rejects it before any fetch happens.** The hazard predicted above turned
out to be worse than a silent strip: it is a hard refusal, which is the better failure of the
two because it cannot be mistaken for success.

**Two candidate causes and they need different fixes.** Test them in the field itself, cheapest
first, pressing Fetch after each:

| # | Paste this | If it is ACCEPTED, the cause was |
|---|---|---|
| 1 | `https://t.me/relayshield_bot/idcheck` | the `?startapp=` query string |
| 2 | `https://t.me/relayshield_bot` | the two-segment Mini App path |

**If test 1 passes**, their regex simply does not allow a query string. Submit the bare link
and recover the attribution through the other two fields, below.

**If only test 2 passes**, the Mini-apps tab keys on the BOT USERNAME and cannot address a
Mini App directly. That is tg.app's one-listing-per-bot finding repeating, and it means the
Mini App listing and the bot listing are the same slot. **Spend it on the Mini App**: it is the
thing a catalogue visitor can open, and three catalogues already carry
`t.me/relayshield_bot/idcheck` directly. Use the Mini App name, tagline and description on that
single listing and skip section 3.

**If BOTH are refused**, the account or the bot is being read as private, and that is a
question for them rather than a thing to keep retrying. Send me what it says.

### RECOVERING THE ATTRIBUTION WHEN THE LINK FIELD WILL NOT CARRY IT

A bare Mini App link is NOT zero, and knowing that stops it being over-corrected: `sourceFor()`
falls back to the generic `tg-miniapp`, so those arrivals land in the generic bucket,
indistinguishable from any other unattributed open. The tgboard delta is what is lost, not the
traffic.

Two fields can carry the key instead, in this order:

1. **Any Website or URL field on the listing.** Use
   `https://api.relayshield.net/developers?source=tg-miniapp-tgboard`. This is the RELIABLE
   one: the key is registered in `_SOURCE_BANNERS`/`_SOURCE_ALIASES`, the landing page reads
   `?source=` there, and it is counted by `tools/source_arrivals.py`. Note the path is
   `/developers`, not the bare host: `?source=` on the root is read by nothing and is FD-8's
   exact shape.
2. **The attributed `t.me` link as plain text in the Description.** A reader who taps it
   carries `?startapp=tg-miniapp-tgboard` and lands attributed. Worth including whatever
   happens with field 1, and it costs one line.

**THE SAME VALIDATOR WILL PROBABLY REFUSE THE BOT LINK IN SECTION 3**
(`?start=SRC_tg-miniapp-tgboard`). **That one matters more**, because a bot arrival with no
payload logs nothing at all and leaves no `unmatched:` row to find later. If the field refuses
it, put the `?start=SRC_tg-miniapp-tgboard` form in the Description as plain text so at least
the readers who tap through are counted.

**Name**

```text
Scam Checker | RelayShield IDCheck
```

Not the brand alone. tg.app's own guidance was that Telegram search favours titles matching
what users type, and nobody types "RelayShield". The pipe is deliberate: house style forbids
em-dashes in published copy, and both live tg.app listings already use a pipe. **This changes
nothing in BotFather** -- the app title stays `RelayShield IDCheck` and the short name stays
`idcheck`. A catalogue title and a Mini App title are different fields on different systems.

**Category:** pick the first of **Tools**, **Utilities**, **Security** that their dropdown
offers. `Tools` is what the live tg.app listing was given, so it is known to exist somewhere.
**I am not guessing past that** -- tgboard is egress-blocked from this container and choosing
from a list I cannot see is the mistake this repo has paid for.

**Tagline** (one line for the card view)

```text
Check a link, a TON address or a Telegram handle before you trust it.
```

**Description**

```text
Paste anything suspicious and get an answer in seconds. No signup, no wallet connect, nothing to install.

It takes three kinds of input:
- A link, checked against Google Safe Browsing, a criminal indicator corpus and domain age
- A TON address (EQ... / UQ... / 0:...), checked for drainer and scam-token signals
- A @handle, checked before you trust a bot or an account that messaged you

Watch up to 3 addresses free and get a Telegram message if something changes. 50 Stars raises it to 25 addresses for 90 days.

It will never tell you something is safe. The most it says is that nothing is known against it, because an absence of evidence is not proof, and a checker that says "safe" is training you to trust the one it misses.
```

**Tags:** `scam-checker`, `security`, `anti-scam`, `phishing`, `ton`, `wallet`, `crypto`,
`tools`. Keep whichever their field accepts, in that order: the first three are what a worried
person types, the rest are category fit.

**Icon, if it asks:** `assets/miniapp/idcheck_icon_512.png` (512x512 square).
**Screenshots, if it asks:** `assets/miniapp/store/01..04` (900x1600 each).
Both arrive through the merge in section 6. **Do not use an image sent in chat** -- it arrives
re-encoded as `.webp` and an upload dialog greys it out of the file picker.

---

## 3. The bot

Type tab: **Bots**

**t.me link**

```text
https://t.me/relayshield_bot?start=SRC_tg-miniapp-tgboard
```

`SRC_` is the prefix `handle_start` actually parses, read out of the handler rather than
assumed. **There is no allowlist on this side** -- any key is accepted and logged verbatim --
so the only way to get this wrong is to submit a bare `t.me/relayshield_bot`, which logs
nothing, leaves no `unmatched:` row to find later, and is indistinguishable from organic
`/start` traffic forever.

**Name**

```text
RelayShield | Breach & SIM Swap Alerts
```

**Category:** Security, or Tools.

**Tagline**

```text
Find out if your email, phone or wallet is already exposed, and get told when that changes.
```

**Description**

```text
RelayShield monitors the things an attacker needs to take over your accounts, and messages you in Telegram when something moves.

What it does:
- Breach and infostealer exposure for your email, including malware that stole a live session rather than a password
- SIM swap and carrier port-out monitoring, so a number transfer reaches you before the account takeover does
- Wallet and link checks on demand, free and with no account
- Browser extension audits, password reuse checks and OTP guidance

Commands: /quickstart to start, /scan to check a link or screenshot, /app for the checker, /breach, /sim, /sweep, /extensions, /help for the full menu.

It is honest about what it does not know. A clean result says nothing is known against the target, never that the target is safe.
```

**That command list was extracted from `_BOT_COMMANDS_BASE` with `ast`, not typed from
memory.** That table is what `setMyCommands` registers, so a command not in it is one a
reader's Telegram menu does not offer. An earlier draft of the StoreBot listing advertised
`/watch`, which does not exist.

**Tags:** `security`, `privacy`, `monitoring`, `data-breach`, `sim-swap`, `crypto`,
`anti-scam`, `alerts`.

---

## 4. The channel

Type tab: **Channels**

**t.me link**

```text
https://t.me/RelayShield
```

No attribution to carry and none needed: a channel link has no payload mechanism, and this is
a different username from `t.me/relayshield_bot`, so it cannot collide with the bot listing.

**Name**

```text
RelayShield Blog | Crypto Scam Alerts
```

The same form tg.app approved on 2026-09-16. It contains the exact Telegram title
(`RelayShield Blog`), so a moderator comparing the listing against the profile sees a match,
and it carries the words people search.

**Category:** Security, Crypto or News, first that appears.

**Tagline**

```text
Real-time crypto scam alerts: SIM swap, wallet drains, address poisoning and fake tokens.
```

**Description**

```text
Real-time crypto scam alerts from RelayShield.

What gets posted here:
- SIM swap and port-out fraud, and how to lock a carrier account before it happens
- Wallet drains, address poisoning and approval exploits, with the on-chain detail
- Leaked credentials and infostealer activity seen in criminal Telegram markets
- Plain explanations of how each one works, so the next variant is recognisable

Free checks with no account: open @relayshield_bot, or paste a link, a TON address or a handle into the RelayShield IDCheck mini app.
```

**IF ANY FIELD AUTO-FILLS A MEMBER COUNT, DELETE IT.** tg.app's "Load from Telegram" put
`4 members on Telegram.` into the description, and that is the single worst sentence that can
appear on a public listing: it is stale the moment it is written and the number argues against
us to every reader. A public listing carries only claims that stay true without maintenance.

**Tags:** `crypto`, `security`, `scam-alerts`, `news`, `phishing`, `wallet`, `sim-swap`.

---

## 5. One key for all three, and that is correct

`tg-miniapp-tgboard`, on the Mini App link and the bot link alike.

The rule is one key per **destination**, and tgboard is one destination. The funnel already
separates what happens after the click: a `?startapp=` check lands in the CHECK stage, a
`?start=SRC_` arrival lands in the BOT stage. Splitting the key would tell us nothing the
stages do not, and would make the tgboard delta two numbers that have to be added back
together -- the `tg-miniapp-channel` defect the route table was rebuilt to remove.

**Groups and Stickers are not ours.** We have three surfaces and there are five tabs;
submitting to the other two would be inventing a surface.

**On the "Promotion" nav item:** tgboard sells placement as well as listing for free. That
does **not** make it a broker -- `@telegtapps` was a broker because the free route did not
exist and every post was an advertisement, and here the free form is on the same page. But it
is the shape to watch. **Do not buy a promoted post.** Let the free listing run, count the
arrivals, and decide with a number rather than a hunch.

---

## 6. The order, and it is easy to get backwards

**The key must be DEPLOYED before you submit, and the baseline taken before arrivals start.**

    ANDREW RUNS THIS:
    cd ~/dev/relayshield
    git checkout main
    git --no-pager fetch origin claude/tender-planck-cb2qrx
    git rm -rf --cached -q --ignore-unmatch ansible-relayshield relayshield-snap
    git stash push --include-untracked -m "pre-merge untracked"
    git -c pull.rebase=false merge --no-edit FETCH_HEAD
    git push -u origin main

EXPECT: the push succeeds. That fires `deploy_miniapp` and `deploy_lambdas`; both must go
green before the key resolves at the edge.
STOP IF: conflict markers. In CLAUDE.md alone this is expected and the resolution is KEEP BOTH
SIDES: `git checkout --merge CLAUDE.md`, then delete the three marker lines by hand. A conflict
in a `.py`, a `.json` or a workflow is two sessions on the same code; send it.

Then, once both workflows are green:

    ANDREW RUNS THIS:
    cd ~/dev/relayshield
    sh tools/verify_miniapp_source_key.sh tg-miniapp-tgboard

EXPECT: `LIVE`, with the `const SOURCE = "tg-miniapp-tgboard"` line printed.
STOP IF: `DOWNGRADED` -- the edge answered with the GENERIC key, so the deploy did not run or
did not carry this commit. **This is the state that looks like working attribution and is
not.** Do not submit until it reads LIVE.
STOP IF: `UNREACHABLE` -- nothing answered, which says nothing about the key either way.

Then the baseline, **before** the listings go live:

    ANDREW RUNS THIS:
    cd ~/dev/relayshield
    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --snapshot before-tgboard

EXPECT: a written JSON baseline under `miniapp_funnel_snapshots/`.
STOP IF: it refuses to overwrite. That refusal is the most important line in the tool -- a
baseline taken after the submission is a comparison of a number with itself, which reads as
"the channel did nothing".

**Opening the deep link yourself logs NOTHING. Pressing "Check it" DOES.** So a self-test
before the baseline is harmless; the same tap after it becomes part of the delta.

---

## 7. What is UNVERIFIED here, so nothing is over-claimed

- **The Category dropdown and the Tags field.** tgboard.com is egress-blocked from this
  container, so I have not seen either list. Everything above the fold comes from your own
  screenshot, which is a primary source and better evidence than any search summary; the
  Description field and anything below it I am inferring from the form's shape.
- **Whether tgboard already lists us.** Section 1 is the read.
- **Whether it keys one listing per bot username**, as tg.app does. If the bot submission is
  refused because the Mini App already holds the slot, that is the tg.app finding repeating and
  it costs nothing: the Mini App is the better surface to spend a single slot on, because it is
  the thing a catalogue visitor can open.
