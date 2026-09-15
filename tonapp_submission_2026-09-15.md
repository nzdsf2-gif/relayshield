# ton.app submission — RelayShield IDCheck

Catalogue #3. `findmini.app` is submitted and awaiting review, the
`awesome-telegram-mini-apps` pull request (#77) is open, `minitelegram.com` is
parked on their own icon-upload crash.

Attribution key for this destination: **`tg-miniapp-tonapp`**, rank 7 in
`miniapp_routes.json`, registered in all three lists that must agree.

---

## 1. Why the screenshots were rejected, and it is not the drag-and-drop

The form states, in its own words:

> Required resolution: 900x1600px. Max. size: 10MB.

**Required, not maximum.** An iPhone screenshot is 1179x2556, which is not only
the wrong size but the wrong *shape* — 9:19.5 against ton.app's 9:16. So there
was never a version of your phone screenshots that would have been accepted, and
nothing about email, Desktop or dragging was involved. Resizing them would
distort the app, and a centre crop would eat the header.

**They are generated at the exact size instead**, by
`assets/miniapp/build_store_screenshots.sh`, the same way
`build_botfather_image.sh` already handles BotFather's mandatory 640x360. Four
files, each exactly 900x1600:

| File | Screen |
|---|---|
| `assets/miniapp/store/01_check.png` | The Check tab as it opens |
| `assets/miniapp/store/02_refusal.png` | An EVM address refused: "Not checked here" |
| `assets/miniapp/store/03_watch.png` | The Watching tab, tier copy and the Stars button |
| `assets/miniapp/store/04_learn.png` | Spot the fake |

**Upload them in that order.** The first is the one a catalogue shows largest.

**Nothing in them is a mock-up and nothing is a canned verdict.** All four
states are produced by the app's own client-side code with no network call at
all, so none of them can go stale or claim something the product does not do.
That is deliberate: a fabricated "flagged" card in a store listing is a claim
about our own product that nobody can check.

### Two things worth knowing about how they were made

**The rig caught itself first.** The page module begins
`import { check } from "/relayshield-widget.js"` — an absolute path, which from
a local file resolves to the filesystem root and 404s. A module whose import
fails runs nothing while the static HTML renders perfectly, so the first run
produced four screenshots of the boot watchdog's own error banner: *"This app's
code did not start."* The watchdog worked exactly as designed, on a screenshot
rig rather than a deploy. The script serves over HTTP now, and it fails hard if
the four outputs come back byte-identical.

**Headless Chromium enforces a minimum window width of 500 CSS pixels.**
Measured, not read: asking for 390, 450 or 500 all report `clientWidth === 500`,
while the screenshot is still taken at the size requested — so a phone-width
request lays the page out at 500 and then crops the difference off the right
edge. The first run silently cut the third tab and half the "Check it" button.

### The one line in 03_watch.png you may want to look at

At the bottom: *"Open this from Telegram to keep a watchlist — a watch is tied
to your Telegram account, so we cannot load one here."* That is the honest
browser fallback, and it appears because the screenshot rig has no Telegram SDK.
**My recommendation is to leave it.** It is true, it explains why the list is
empty rather than implying the user has no watches, and doctoring it out is the
wrong instinct for a security product's store page. If you would rather it were
not there, say so and I will stage that screen differently.

---

## 2. The three Telegram links

Paste these into the three `t.me/...` slots, in this order:

```
https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-tonapp
https://t.me/relayshield_bot?start=SRC_tg-miniapp-tonapp
https://t.me/RelayShield
```

1. **The Mini App itself**, carrying this catalogue's own attribution key. This
   is the link that has to be right: an unregistered key is silently downgraded
   to the generic `tg-miniapp` at the Worker's edge, which is attribution that
   looks like it worked.
2. **The bot.** `SRC_` is the prefix `handle_start` actually parses
   (`payload.upper().startswith("SRC_")`, then lower-cased), and Telegram allows
   `A-Za-z0-9_-` in a deep-link payload, so the hyphens are fine. Read out of
   the handler, not assumed.
3. **The announcements channel.**

## 3. Yes, include the bot link. It is the stronger half of the funnel.

Three reasons, and the third is the one that decides it:

- **The bot is the alert channel.** Watching a TON address is only worth
  anything because the bot messages you when the answer changes. A catalogue
  entry that lists the Mini App and not the bot lists half the product.
- **A Mini App opened from a direct link creates no chat**, so a new user has
  nothing to pin, mute or archive. The bot link is the only route that gives
  them one.
- **It is the entire stated reason this Mini App exists** — expanding the
  discovery surface for the Telegram bot and the API landing site. Leaving the
  bot out of a catalogue listing would be spending the listing on the surface we
  built to *feed* the other two.

## 4. The remaining fields

| Field | Value |
|---|---|
| App Name | `RelayShield IDCheck` |
| Category | **Utilities** — as you have it |
| Languages | English |
| Caption | *Check a link, a TON address or a Telegram handle before you trust it. No signup, no wallet connect.* |
| Website | `https://api.relayshield.net/developers?source=tg-miniapp-tonapp` |
| Github | Leave it as the profile URL you entered |

**On the Github field**, my recommendation is the profile rather than the
monorepo. A consumer catalogue visitor gets nothing from a repository full of
Lambda handlers and deploy workflows, and the profile is the stable link.

**Full description** — same copy as FindMini, which is deliberate: it names
sources and capabilities and quotes no counts, so it needs no maintenance on a
page we cannot cheaply edit.

> RelayShield IDCheck screens three things before you act on them: a link, a TON
> address, and a Telegram bot handle.
>
> A link is checked against indicators collected from criminal Telegram
> channels, Google Safe Browsing, and how old the domain is. A TON address is
> checked against TON's own account data, DEX liquidity, and the same indicator
> corpus. You can watch up to three TON addresses free, and the bot messages you
> the moment one of them changes — liquidity pulled, a balance emptied, code
> appearing on an address that had none.
>
> Three things it will not do, and each is on purpose. It never says "safe" — an
> absence of evidence is not proof, and the best answer it will give you is "no
> match in any source we check". It never touches your wallet: there is no
> connect step, because reading an address does not require permission to spend
> from one. And it checks TON only, because this is a Telegram app and TON is
> the chain Telegram ships.
>
> Three addresses free, alerted immediately and in full. 50 Stars raises it to
> 25 addresses for 90 days. Stars buy more slots and nothing else — the free
> alerts are identical.

---

## 5. The ordering, and it is easy to get backwards

`tg-miniapp-tonapp` is registered on the branch and **is not deployed yet**.
Only `tg-miniapp-findminiweb` is live.

1. **Merge and push** (the block in the reply). This deploys the key AND the
   verdict-card fix below, and it puts the four screenshots on your Mac
   byte-identical — images travel in the repo, never through the chat.
2. **Open the deep link and press "Check it" once.** Opening the app logs
   nothing; pressing Check it is what writes the `source=` line the funnel
   counts.
3. **Take the baseline**, `--snapshot before-tonapp`. The tool refuses to
   overwrite one, which is the most important line in it.
4. **Then submit.** A self-visit inside the baseline is harmless; the same visit
   after it becomes part of the delta.

---

## 6. A defect your own phone screenshot caught, now fixed

In the screenshot you sent, the Check tab's card read **"Could not complete the
check"** as its heading, directly above body copy saying *"Checked against our
criminal-channel indicator corpus, Google Safe Browsing and domain age. None of
them knows this one."* Those two sentences contradict each other.

**It was not a one-off and it was not the network.** `check()` returns level
`unknown` for two opposite things: a target that *was* screened against all
three sources and matched none of them — which is every ordinary URL, the most
common outcome the app has — and a call that never came back. `Verdict.ok` is
the discriminator, and the widget has always used it. The page read only
`.level`, so **every clean result rendered the failure heading.** The share
image carried the same heading, so a picture of a clean result left the app
saying the check had failed.

Fixed: `unknown` now heads "No match in any source we check", the failure
wording is only reachable from an actual failure, and the caveat and call to
action split the same way — a target that was not checked must not be told "not
in any source we check". Two guards, one of which executes the function out of
the served page, both proven by putting the defect back.

**UNVERIFIED from this container:** whether the flagged example
(`testsafebrowsing.appspot.com/s/malware.html`, Google's own Safe Browsing test
host) is currently returning a real flag. `api.relayshield.net` is egress-blocked
here, so I cannot tell whether your card said `unknown` because the call failed
or because Safe Browsing did not flag it. **After the merge deploys, press "Try a
link that gets flagged" once and tell me the heading.** "Do not proceed" means
everything works. "No match in any source we check" means the example is no
longer flagged by construction and needs replacing — which would be a real
finding and a separate fix.
