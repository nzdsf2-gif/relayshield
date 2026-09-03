# RelayShield widget for Telegram bots

Screen a link or a wallet address that a user pasted, and get back a verdict and
a ready-to-send reply. One function. No dependencies. No signup for the first
call.

```
User:  hey check this https://claim-airdrop.example/connect
Bot:   ⚠️ High risk. Do not proceed.
       `https://claim-airdrop.example/connect`
       • this domain appears in RelayShield's criminal IOC corpus
       • the domain was registered only 3 days ago
```

## Install

There is no package to install. Copy one file into your bot.

**Python** (aiogram, python-telegram-bot, pyTelegramBotAPI, raw webhook):

```
curl -O https://raw.githubusercontent.com/nzdsf2-gif/relayshield/main/widget/relayshield_widget.py
```

**JavaScript** (grammY, Telegraf, node-telegram-bot-api, raw webhook), Node 18+:

```
curl -O https://raw.githubusercontent.com/nzdsf2-gif/relayshield/main/widget/relayshield-widget.js
```

## Use

aiogram:

```python
from relayshield_widget import check

@dp.message()
async def on_message(message):
    v = check(message.text)
    if v.blocked:
        await message.reply(v.text, parse_mode="Markdown", disable_web_page_preview=True)
```

grammY:

```js
import { check } from "./relayshield-widget.js";

bot.on("message:text", async (ctx) => {
  const v = await check(ctx.message.text);
  if (v.blocked) await ctx.reply(v.text, { parse_mode: "Markdown" });
});
```

`check()` is synchronous in Python and returns a promise in JavaScript. It takes
whatever the user typed and works out for itself whether that is a URL, a bare
domain, or an EVM, Solana, TON, Bitcoin or Ronin address. Anything else returns
an unsupported verdict and makes no network call.

## The verdict

| Field | Meaning |
|---|---|
| `blocked` | `true` only for `high` and `critical`. This is the one to branch on. |
| `level` | `critical`, `high`, `medium`, `low`, `unknown`. |
| `ok` | `false` when the check did not complete. `level` is then `unknown`. |
| `reasons` | Plain-language findings, safe to show a user. |
| `text` | Ready to send with `parse_mode="Markdown"`. |
| `html` | The same, for `parse_mode="HTML"`. |
| `raw` | The API response, if you want to render it yourself. |

## Two things it will never do

**It never throws.** A timeout, a DNS failure, a rate limit, a change on our
side: every one of them returns a verdict with `ok=false` and `level="unknown"`.
Your handler cannot crash because our API had a bad minute.

**It never says "safe".** A clean link check is an absence of evidence across
three sources, not proof of safety, so the best a clean URL gets is "nothing
known against it" plus that caveat. Nothing in this file will tell your users a
link is safe on our behalf.

## Telegram Markdown, which is a trap

Telegram's legacy `Markdown` parse mode has no escape syntax. A backslash before
an underscore is a backslash, not an escape, and an unclosed entity makes
Telegram reject the whole message with a 400 — so a URL containing an underscore
can silently drop your reply, verdict and all. We shipped that bug once and
spent a session finding it.

`.text` puts every attacker-controlled value inside a code span, which legacy
Markdown treats as literal, and strips the one character that could close it. If
you would rather use HTML, `.html` is the same message with proper escaping.

## Cost and limits

| | |
|---|---|
| Link check | `POST /v1/link-check` — keyless, capped per source IP per day |
| Address check | `POST /v1/wallet-risk` — keyless, same cap, EVM / Solana / TON / Bitcoin |
| A key | Raises the cap. 100 free calls, no card: https://api.relayshield.net/developers?source=tg-widget |

```python
v = check(text, api_key="rs_live_…")
```

```js
const v = await check(text, { apiKey: "rs_live_…" });
```

A key also unlocks `POST /v1/scan-url`, which adds a multi-engine VirusTotal
analysis on top of the immediate signals. The widget does not call it, because
that endpoint submits and then needs polling, and a Telegram handler has to
answer now.

## What it sends us

The URL or address being checked, and `source: "tg-widget"` so we can tell how
many installs are real. No user id, no chat id, no message text beyond the thing
being screened, and no key unless you pass one. URLs are hashed before they
reach our logs.

## Running the tests

```
python3 test_relayshield_widget.py
node --test widget/relayshield-widget.test.mjs
```

Both suites run offline against a stub transport. They mirror each other case
for case, because the failure that matters is the two clients quietly diverging
and returning different verdicts for the same input.
