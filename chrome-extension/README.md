# RelayShield — Link & Wallet Check (Chrome extension)

FD-6. Right-click a link, or paste a link or a wallet address into the popup, and get a
verdict from the same free/keyless product this repo already ships everywhere else:
`/v1/link-check` (RelayShield's IOC corpus, Google Safe Browsing, RDAP domain age) and
`/v1/wallet-risk` (EVM, Solana, TON, Bitcoin). No signup, no key, same as the Mini App and
the free MCP server.

## What's here

    manifest.json    MV3 manifest
    api.js           shared request/detection logic (background.js and popup.html both load it)
    background.js    context menu ("Check this link/wallet with RelayShield") + notifications
    popup.html/.js   paste box, click Check, get a verdict
    icons/           16/32/48/128, generated from assets/miniapp/relayshield_icon_512.png

## Verified, not just parsed

`node --check` passed on all three JS files, which only proves they parse. The manifest was
also loaded into the actual pre-installed Chromium via Playwright (`--load-extension`): the
service worker registered with no throw, the popup rendered its expected elements with zero
console errors, and the ported chain-detection regexes were exercised in-browser against real
EVM/URL/garbage inputs. That is the level this repo's own CLAUDE.md insists on for anything
that ships as an artifact rather than a library — `node --check` answers "does it parse",
never "does it run."

**Not yet tested**: an actual context-menu click end-to-end against the live API (background.js's
`runCheck` → `rsCheckAny` → `fetch`), since that needs a real network call this container can't
make to `api.relayshield.net`. The request/response shapes were read directly from
`relayshield_api.py`'s `handle_link_check` and `handle_wallet_risk` (field names verified, not
guessed), but load it unpacked and try it against a live link before submitting.

## Attribution

Every call carries `source: "chrome-extension"`, and that key is already registered in
`_SOURCE_BANNERS` (`relayshield_developer_signup.py`) — done before this shipped, per the
front-door rule. The popup's "get an API key" link points at
`api.relayshield.net/developers?source=chrome-extension`.

## ANDREW RUNS THIS — load it locally to try it

```zsh
open -a "Google Chrome" chrome://extensions
```
EXPECT: the Extensions page opens.

Then: toggle **Developer mode** (top right) → **Load unpacked** → select
`~/dev/relayshield/chrome-extension`. Right-click any link on any page and look for "Check
this link with RelayShield" in the context menu.

## Store listing copy

**Title** (manifest `name`, 44/75 chars): `RelayShield: Link, Wallet & Email Scam Check`

**Summary** (manifest `description`, becomes the store card's short description, 116/132 chars):
`Right-click a link, paste a wallet address, or check a suspicious email. Free scam screening,
no signup, no account.`

**Detailed description** (the listing page, under the screenshots):

> Right-click any link on any page — or open the popup — to check it before you trust it.
> RelayShield screens against a criminal threat corpus built from monitored underground
> channels, Google Safe Browsing's live blocklist, and how recently the domain was
> registered.
>
> Paste a wallet address (EVM, Solana, TON, or Bitcoin) for a risk screen against known
> scam, drainer, and sanctions activity — before you send anything to it.
>
> Paste a suspicious email's sender, subject, and body to check it for phishing signals:
> brand impersonation, urgency language, mismatched sending domains, and any links inside
> it — checked the same way as the link tab.
>
> **No signup. No account. No card.** Every check here is free, with nothing to configure
> first.
>
> **We never tell you something is "safe."** Absence of a flag means nothing is known
> against it right now — not that it's clean forever. A phishing site registered five
> minutes ago is in no database yet, and we say so rather than pretending otherwise.
>
> Want ongoing monitoring instead of one-off checks — breach alerts, SIM-swap protection,
> infostealer exposure? RelayShield's Telegram and WhatsApp bots do that continuously; this
> extension is the free, no-signup front door to the same underlying checks.

## Before submitting to the Chrome Web Store

1. **$5 one-time developer registration fee**, paid once, covers every extension you ever
   publish under that account. Confirmed current as of this session — not the stale $25 figure
   from an unrelated store.
2. **Privacy practices disclosure is mandatory**, not optional paperwork: the Developer
   Dashboard's Privacy tab requires stating that the extension transmits user-provided text
   (pasted links/addresses/email content) to a remote server, and a privacy policy URL —
   `relayshield.net/privacy` already exists and covers this.
3. **Screenshots for the store listing, at 1280×800 or 640×400.** Two working previews are
   attached to this session's reply for visual reference — built from mocked results (this
   container can't reach the live API), and at the popup's natural 372×520 size, not the store's
   required dimensions. Take the final ones yourself, against a real result, at the correct size.
4. **Icon**: reused from the existing brand asset (`relayshield_icon_512.png`), not
   IDCheck-specific — this is the general RelayShield mark, matching the same reasoning
   `relayshield_icon_512.html`'s own comment gives for the Telegram bot's icon: same shield,
   different surface, each labelled as itself.

## v0.2.0: email check added

`/v1/email-check` is now a second tab in the popup (Sender / Subject / Body fields, since it
scores a parsed message rather than a single pasted string). Links inside the pasted body are
extracted client-side and sent alongside the text, matching what the endpoint expects from "a
caller that has already parsed the message" — the extension IS that caller here.

**Deliberately not built**: automatically reading the currently-open email in Gmail/Outlook via
a content script. That needs per-provider DOM scraping, which breaks silently whenever those
sites change their markup — a real, ongoing maintenance cost. Worth it only if the manual
paste-in tab proves people actually use email checking from here; build the cheap version first,
measure, then decide.
