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

## Before submitting to the Chrome Web Store

1. **$5 one-time developer registration fee**, paid once, covers every extension you ever
   publish under that account. Confirmed current as of this session — not the stale $25 figure
   from an unrelated store.
2. **Privacy practices disclosure is mandatory**, not optional paperwork: the Developer
   Dashboard's Privacy tab requires stating that the extension transmits user-provided text
   (pasted links/addresses) to a remote server, and a privacy policy URL —
   `relayshield.net/privacy` already exists and covers this.
3. **Screenshots and a short description** for the store listing — none exist yet. 1280×800 or
   640×400, at least one showing the popup with a real verdict.
4. **Icon**: reused from the existing brand asset (`relayshield_icon_512.png`), not
   IDCheck-specific — this is the general RelayShield mark, matching the same reasoning
   `relayshield_icon_512.html`'s own comment gives for the Telegram bot's icon: same shield,
   different surface, each labelled as itself.

## What's deliberately NOT in v1

`/v1/email-check` isn't wired in — it scores a full message (from/subject/body/links), not a
bare pasted string, so it doesn't fit a single paste box the way link and wallet checks do.
Worth a fast-follow with its own UI (a small form, not a text area) rather than forcing it into
this one.
