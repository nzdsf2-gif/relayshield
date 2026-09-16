# tg.app, listing 2 of 3: the BOT

The Mini App listing is **Approved and live**. This is the second of the three
tg.app allows, and it is a different product on the same brand: the bot does
monitoring, the Mini App does one-off checks.

Every field below is ready to paste. Two of them are wrong on your screen right
now and are called out.

---

## 1. FIRST, THE ICON URL ON YOUR SCREEN IS A PLACEHOLDER

The Icon field currently holds
`https://ui-avatars.com/api/?name=RelayShield&background=4F46E5&color=fff&size=...`,
which renders the purple **RE** square in the preview beside it. That is not our
brand mark and it is not a file we control.

**Use this instead:**

```
https://raw.githubusercontent.com/nzdsf2-gif/relayshield/main/assets/miniapp/relayshield_icon_512.png
```

**It 404s until you merge and push `main`.** A `raw.githubusercontent.com/.../main/...`
URL reads GitHub's default branch, and that file is on the branch right now. Merge
first, load the URL in a browser to confirm it shows the shield, then paste it.

**It is NOT `idcheck_icon_512.png`.** That tile reads "IDCheck", which is the Mini
App. An icon naming a different product on a card for this one is the kind of
thing a moderator notices and a user does not, and the user is the one who ends up
confused. Same shield, same two Telegram theme colours, correct wordmark.

---

## 2. THE FIELDS

| Field | Value |
|---|---|
| **App Name** | `Breach Monitor | RelayShield` |
| **Type** | Bot |
| **Category** | Tools |
| **Telegram Link** | `https://t.me/relayshield_bot?start=SRC_tg-miniapp-tgapp` |
| **Website** | `https://api.relayshield.net/developers?source=tg-miniapp-tgapp` |
| **GitHub** | `https://github.com/nzdsf2-gif/relayshield` |
| **Icon** | the raw URL in section 1 |
| **X / Instagram / YouTube** | leave empty |

**Short Description** (136 of 150):

```
Breach monitoring inside Telegram. Check whether your email, phone or wallet has turned up in a leak, and get told when a new one lands.
```

**Full Description** (734 of 5000):

```
For anyone whose email, phone or crypto wallet is worth stealing. RelayShield checks them against criminal Telegram marketplaces, infostealer log dumps and public breach data, then keeps watching and messages you when something new surfaces.

Send an email address, a phone number or a wallet address and you get a verdict back in the chat. No signup, no wallet connect, nothing to install.

It also covers SIM swap monitoring, leaked API and LLM provider keys, and link checking for suspicious URLs. The companion Mini App, RelayShield IDCheck, checks a link or a TON address on its own.

RelayShield never says "safe". An absence of evidence is reported as an absence of evidence, which is the only honest answer a checker can give.
```

**Tags** (their readiness panel wants 2 to 5):

```
breach check
data leak
scam checker
crypto security
phishing
```

---

## 3. WHY THE NAME IS "BREACH MONITOR" AND NOT "SCAM CHECKER"

Their panel is right that a title should match what people type, and the Mini App
listing already took `Scam Checker | RelayShield IDCheck`. **Two listings competing
for the same phrase is one listing's worth of reach split in half**, and it tells a
browsing user nothing about which to open.

So the bot takes the term for the thing it actually does that the Mini App does not:
it *keeps* watching and messages you. "Breach monitor" is a real search term, it is
true of this product, and it separates the two cards.

**Their literal example, `"tools | RelayShield"`, is not the one to copy.** "Tools"
is the category field, which is already set; nobody searches it.

---

## 4. SCREENSHOTS: LEAVE THEM EMPTY

The field is optional and the four images we have are of the **Mini App**, not the
bot. Putting Mini App screens on a bot card shows a product the card does not open.

**My recommendation: submit without them.** A listing with no screenshots is worse
than one with good ones and better than one with misleading ones, and the Mini App
card already carries them.

**If you want them, the honest version is two phone screenshots of the bot chat** --
a `/start` and one real check -- taken on your phone and committed to the repo, not
sent through chat, because the chat layer re-encodes images to `.webp` and an upload
dialog will not let you select one. Two minutes, and it is a better card. Your call
whether tonight is the night.

---

## 5. THE THIRD LISTING, WHEN YOU WANT IT

`https://t.me/RelayShield` as **Add Channel**. No attribution to carry, no copy to
write beyond a sentence. It costs a minute and it is the least valuable of the
three, so it is not worth staying up for.
