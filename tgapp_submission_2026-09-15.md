# tg.app — three listings, not one

Catalogue #4. Its Creator Studio has **separate routes for apps, bots, channels and
groups**, which no catalogue we have submitted to so far did. That changes the answer
to your question: yes, the bot goes here too, and so does the channel.

---

## 1. READ BEFORE YOU WRITE. The sidebar has a "Claim Listing" item.

**ANDREW CLICKS THIS, and it is the first step:** in Creator Studio, use the catalogue's
own search for `relayshield` and `RelayShield IDCheck`, and open **Claim Listing**.

A catalogue with a Claim flow is a catalogue that lists apps their owners did not submit.
If `@relayshield_bot` is already in there, **claiming it is a different action from
creating it**, and creating a second entry makes a duplicate we then have to get removed.
This costs ten seconds and it is the step that has been skipped four times this programme.

**If the search returns nothing, proceed to section 2.**

---

## 2. The three listings, in this order

### (a) The Mini App — "List existing app or bot"

```
https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-tgapp
```

The card says *"Paste the Telegram link and we'll pull the details."* Fields it will
probably ask for, with the copy already written:

| Field | Value |
|---|---|
| Name | `RelayShield IDCheck` |
| Short description | *Check a link, a TON address or a Telegram handle before you trust it. No signup, no wallet connect.* |
| Category | Utilities, or the nearest equivalent their list offers |
| Icon | `assets/miniapp/idcheck_icon_512.png` — 512x512, square |
| Screenshots | `assets/miniapp/store/01..04` — 900x1600 each |
| Website | `https://api.relayshield.net/developers?source=tg-miniapp-tgapp` |

**CHECK THE SAVED LINK AFTER IT PULLS THE DETAILS.** A form that fetches a `t.me` URL to
read its metadata may normalise the URL and drop the `?startapp=` query on the way. If the
listing shows a bare `t.me/relayshield_bot/idcheck`, the attribution is gone and the
listing is worth measurably less. Edit it back if the field is editable; if it is not,
tell me and we use the Website field as the attributed link instead.

### (b) The bot — "List existing app or bot", second time

```
https://t.me/relayshield_bot?start=SRC_tg-miniapp-tgapp
```

`SRC_` is the prefix `handle_start` actually parses, read out of the handler rather than
assumed. Describe it as the monitoring bot, not as the Mini App: *breach, SIM swap and
infostealer monitoring for your email, phone and wallets, with alerts in Telegram.*

### (c) The channel — "Add Channel"

```
https://t.me/RelayShield
```

Announcements. No attribution to carry and none needed.

---

## 3. All three share ONE key, and that is correct

`tg-miniapp-tgapp`, on every one of them.

The rule is one key per **destination**, and tg.app is one destination. The funnel already
separates what happens after the click: a bot arrival lands in the **BOT** stage via the
`SRC_` payload, a Mini App check lands in the check stage via `?startapp=`. Splitting the
key would not tell us anything the stages do not already tell us, and it would make the
tg.app delta two numbers that have to be added back together.

---

## 4. The widget cannot be listed here, and that is not a gap

`widget/relayshield-widget.js` is **a file other developers copy into their own bot**. It
has no `t.me` link, no chat, and no Telegram presence of its own — there is nothing for
"paste the Telegram link and we'll pull the details" to pull.

**Its two real homes already exist**: the developer page at
`api.relayshield.net/developers`, and the awesome-telegram-mini-apps pull request (#77),
which is a developer list rather than a consumer catalogue and is exactly the right
audience for a copy-in file. **My recommendation is to leave it there and not to invent a
Telegram surface for it** just to have something to list — a bot that exists only to be
catalogued is a control that does nothing, which is a defect this repo has paid for twice.

---

## 5. Ordering, unchanged from ton.app

`tg-miniapp-tgapp` is registered in all three lists and ships on your next merge. So:

1. Merge and push.
2. `sh tools/verify_miniapp_source_key.sh tg-miniapp-tgapp` — must print **LIVE**.
3. Open the deep link and press **Check it** once. Opening logs nothing; pressing Check it
   writes the `source=` line.
4. `AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30 --snapshot before-tgapp`
5. Submit all three listings.

**UNVERIFIED from the container:** tg.app is egress-blocked here, so every field name above
is read off your own screenshots and the rest is the copy we already use. If a field asks
for something not on this list, send me the label.
