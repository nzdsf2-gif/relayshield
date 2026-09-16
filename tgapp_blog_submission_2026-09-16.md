# tg.app submission: the RelayShield Blog channel (2026-09-16)

Paste-ready answers for the fields left blank on the **Add Channel or Group** form.
This is the **second** RelayShield listing on tg.app. The first is the Mini App
(*Scam Checker | RelayShield IDCheck*), approved 2026-09-15. This one is the
CHANNEL, `t.me/RelayShield`, which is a different destination.

**Two fields were settled by checking rather than guessing. One is yours to read,
because tg.app is egress-blocked from the container and I cannot see their list.**

---

## 1. Name

Currently `RelayShield Blog`. **Change it to:**

```
RelayShield Blog | Crypto Scam Alerts
```

**Why, and the trade-off is real.** tg.app's own guidance on the Mini App listing was
*"Telegram search favors titles that match what users type, not brand names alone."*
Nobody types "RelayShield". But this form also warns **"Listings may be rejected if the
profile does not match"**, and the Telegram channel's actual title is `RelayShield Blog`.

**I would take the form above**: it contains the exact Telegram title, so a moderator
comparing the listing against the profile sees a match, and it carries the words people
search. The alternative is leaving it as `RelayShield Blog` and letting the tags carry
the search terms, which is safer against rejection and worse in search.

**UNVERIFIED:** I have not read tg.app's moderation rules. If the listing comes back
rejected on a name mismatch, revert to the bare `RelayShield Blog` and re-submit.

Note the separator is a pipe, not an em-dash. House style forbids em-dashes in published
copy, and the Mini App listing already uses a pipe.

## 2. Category *

**This one is yours and I am not guessing at it.** tg.app is egress-blocked here, so I
cannot enumerate the dropdown, and choosing a name for a list I cannot see is the exact
mistake this repo has paid for before.

**Pick the first of these that appears in the menu:**

1. **Security** — most accurate
2. **Crypto** — accurate, broader audience
3. **News** — accurate for a blog channel
4. **Tools** — what the Mini App listing was given, so it is known to exist

## 3. Short Description * (120/150)

```
Real-time crypto scam alerts: SIM swap, wallet drains, address poisoning and fake-token checks. Free checks in Telegram.
```

## 4. Full Description * (821/5000)

**Delete the auto-pulled line `4 members on Telegram.`** It was filled in by
"Load from Telegram" and it is the single worst sentence that could appear on a public
listing: a member count is stale the moment it is written, and four is a number that
argues against us to every reader. The repo's own rule is that a public listing carries
only claims that stay true without maintenance.

```
Real-time crypto scam alerts from RelayShield.

What gets posted here:
- SIM swap and port-out fraud, and how to lock a carrier account before it happens
- Wallet drains, address poisoning and approval exploits, with the on-chain detail
- Leaked credentials and infostealer activity seen in criminal Telegram markets
- Fake tokens and typosquatted domains aimed at wallet users

Check anything yourself, free and with no signup:
https://t.me/relayshield_bot?start=SRC_tgappblog

Paste a link, a TON address or a bot handle and get a verdict back in seconds. The same checks run inside our Mini App, RelayShield IDCheck.

Written by the team that runs the RelayShield threat intelligence pipeline. Indicators are collected continuously from monitored criminal Telegram marketplaces, infostealer log dumps and public feeds.
```

**Three deliberate choices in that copy:**

- **`?start=SRC_tgappblog` is attribution, and it needs NO code change.** Verified by
  reading `relayshield_telegram_webhook.py:1709`: the handler takes any payload beginning
  `SRC_`, lower-cases the rest, logs `acquisition source=tgappblog` and writes
  `acquisition_source` onto the user record **on first touch only**. There is no allowlist
  to register against, unlike the `_SOURCE_BANNERS` table, which governs the developers
  landing page and is a different surface entirely. `tools/miniapp_funnel.py` counts these
  lines at its BOT stage, so this listing is measurable from day one.
- **The handle is lower-case `relayshield_bot`.** Telegram resolves usernames
  case-insensitively so `@RelayShield_bot` works, but one spelling everywhere is the rule
  that exists because `checkemail@` shipped as `emailcheck@` twice in one message.
- **No corpus count anywhere.** MEASUREMENT DOCTRINE, on a page a competitor can read.
  Sources and capabilities, never figures.

## 5. Telegram Link or Username *

`https://t.me/RelayShield` — already correct, leave it.

## 6. I administer this channel or group *

**Tick it.** You do administer it. The listing cannot be submitted otherwise.

## 7. Icon URL

```
https://raw.githubusercontent.com/nzdsf2-gif/relayshield/main/assets/miniapp/relayshield_icon_512.png
```

**Verified live, not assumed:** `HTTP 200`, `content-type: image/png`, 69,915 bytes,
512x512. The file is tracked on `origin/main` under the `.gitignore` exception added on
2026-09-14 for exactly this reason.

**This field takes a URL, not an upload, so the `.webp` problem does not apply.** That
defect cost three rounds on miniTelegram because the chat layer re-encodes images in
transit. A URL is fetched by tg.app's own server from GitHub, and nothing in the path
re-encodes anything.

**Use `relayshield_icon_512.png`, the RelayShield brand mark, NOT `idcheck_icon_512.png`.**
The IDCheck icon belongs to the Mini App and is already on that listing. This listing is
the company's channel.

## 8. Screenshots

**Leave empty. The field is not marked required.**

The only screenshots we have are `assets/miniapp/store_1080x1920/`, and they are of the
Mini App. Putting them on a CHANNEL listing shows a reader a product that is not what they
are subscribing to. One honest icon beats four images of a different thing, and a
screenshot of a channel is just a screenshot of text posts.

## 9. Tags (2 to 5)

tg.app says tags are how it categorises the listing and suggests title keywords, and asks
for terms matching how people search inside Telegram. **Add these five:**

```
crypto security
scam alerts
wallet security
sim swap
threat intelligence
```

---

## After it is approved

1. **Take the funnel baseline BEFORE any traffic arrives**, and mind the ordering that is
   easy to get backwards. Opening the deep link yourself logs the arrival, so a self-test
   inside the baseline is harmless and the same visit after it becomes part of the delta.

       AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --snapshot before-tgappblog

   The tool **refuses to overwrite a baseline**, which is the most important line in it.

2. **Record the result in the catalogue table in CLAUDE.md**, next to the five Mini App
   destinations. This is a sixth listing and a different destination from
   `tg-miniapp-tgapp`, which is the Mini App on the same site.
