# FindMini.app submission: every field, filled

**2026-09-14.** Paste-ready. Everything below is written to survive a moderator clicking it.

---

## THE ADS CHECKBOX: NO. LEAVE IT UNTICKED.

**"Contact me about running ads in my app 💰" -- do not tick it.** This is the clearest call on the
page and it is not close.

**1. The ad inventory in this ecosystem is the exact category we exist to warn people about.**
Telegram Mini App ad networks serve clickers, tap-to-earn games and high-risk dapps. We already
refused to submit to `@telegtapps` for precisely this reason, in writing: *"a security product listed
in a channel advertising high-risk dapps is a bad first impression rather than a cheap one."*
Ticking this box invites that same inventory INSIDE our own app, permanently, on the one surface we
fully control. It is the same defect we already rejected, one layer worse, because there it was
somebody else's channel and here it would be our product.

**2. It inverts the product's only claim.** A user pastes an address into a tool that says "we check
whether things are trustworthy". Rendering a paid ad for an unvetted dapp next to that verdict is us
placing a bet we have not checked, inside the UI whose whole job is checking. If someone follows one
and gets drained, we did not merely fail to warn them, we introduced them.

**3. The money is not real at our scale.** We have three live payment rails and Stars. Mini App ad
CPMs against a few hundred users are pennies. We would be trading the only asset a security brand has
for an amount that does not show up in a monthly total.

**It is only a "contact me" checkbox, not a commitment** -- so the cost of ticking it is a sales
conversation we decline, not a contract. Untick it anyway. There is no version of this we want, and
an unanswered sales thread is its own small tax.

---

## THE FORM, FIELD BY FIELD

### Bot/App Start link  *(required)*

    https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-findminiweb

**The `?startapp=` payload is the entire reason this submission is measurable.** The field's own hint
says it may carry a start command, so this is the intended use rather than a trick.

`tg-miniapp-findminiweb` is a NEW key registered this session in all three lists that must agree.
See "What I changed" below -- it needs a merge and a push before it resolves.

### App Name  *(required)*

    RelayShield IDCheck

Matches the BotFather registration exactly. Do not shorten it to "RelayShield": the bot's TI
monitoring product already owns that name and the two should stay separable.

### Profile picture  *(required, square, min 256x256, under 1MB)*

    assets/miniapp/idcheck_icon_512.png

512x512, 186 KB, square. Generated this session and sent alongside this file, so you can upload it
without going near the repo.

### App short description in English, maximum 20 words  *(required)*

    Check a TON address or link before you send. Free, instant, no wallet connection and no signup.

17 words. Leads with the action, and the three "no"s are the objections a stranger actually has.

### App short description in Russian  *(optional)*

**Leave it empty.** We have no Russian copy and machine-translating a security warning is how a
nuance inverts. A wrong hedge in a safety claim is worse than an absent translation, and the
interface is English-only anyway, so a Russian card would promise an experience we do not deliver.

### App full description in English  *(required)*

    RelayShield IDCheck answers one question: is this worth trusting with your money?

    Paste a link and it checks the domain against Google Safe Browsing, how long the
    domain has existed, and RelayShield's indicator corpus, collected continuously from
    monitored criminal Telegram marketplaces, infostealer log dumps and public
    indicator feeds.

    Paste a TON address and it runs the same checks, then shows what it can see about
    the address itself.

    Watching something you care about? Add it to your watchlist and the bot messages
    you when what it sees changes. Three watch slots are free, and free alerts arrive
    immediately and in full, with nothing held back. 50 Stars raises the limit to 25
    slots for 90 days, which covers what a larger watchlist costs us to keep checking.

    Three things it deliberately does not do.

    It never tells you something is safe. The strongest answer it gives is that nothing
    is known against it, which is not the same thing. Saying otherwise is the most
    dangerous thing a tool like this could do.

    It does not connect to your wallet, ask for a seed phrase, or ask you to sign
    anything. There is nothing to approve.

    It checks TON, and only TON. Paste an Ethereum, Solana or Bitcoin address and it
    says plainly that it is not checking that, rather than guessing.

    No account, no card, no signup.

**Why no numbers in it.** MEASUREMENT DOCTRINE: on a page we cannot cheaply edit, name the SOURCES
and the CAPABILITIES, never the counts. A corpus headline would be wrong within a month and this
listing is a standing page a competitor can read.

**The one count that IS in there is the price**, which the doctrine permits because it only moves by
a deliberate act with a commit behind it. 50 Stars / 25 slots / 90 days are pinned against
`SLOTS_PRICE_STARS`, `PAID_WATCH_SLOTS` and `SLOTS_DURATION_DAYS`. **If pricing ever changes, email
`support@findmini.app`** -- copy shown to a buyer that disagrees with what the server grants is a
price we do not honour.

### Screenshots  *(required, up to 10, EQUAL SIZE, under 1MB each)*

Four is plenty and equal size is a hard requirement, so take them all on one device in one sitting.
In this order, because the first is the thumbnail:

1. **Check tab after pressing "Try a link that gets flagged."** The strongest single frame we have:
   a real red verdict, earned live. The example URL is Google's own Safe Browsing test host, so the
   flag is genuine and it is not a real criminal domain.
2. **A TON address verdict**, showing the address panel.
3. **The Watching tab**, showing the slot meter and the tier line.
4. **Spot the fake**, the quiz.

**Do not screenshot a clean "nothing known" result as frame 1.** It is the honest common case and it
is the worst possible thumbnail: it looks like an empty app.

### TON blockchain  *(you have ticked it)*

**Keep it ticked, and it is honest.** The app reads TON chain data on every address check and the
watchlist monitor re-checks TON and only TON. That is using the TON blockchain.

**The trap to avoid is in the copy, not the checkbox.** We do NOT use TON Connect, hold no contract
and take no TON payments. A moderator who ticks through expecting a dapp and finds no wallet
connection has been misled. The description above heads that off by saying outright there is no
wallet connection and nothing to sign, so the checkbox and the copy agree.

### Select interface languages  *(required)*

**EN only.** Matches reality.

### Additional links  *(optional -- and this is the founder's second goal, so use it)*

    https://api.relayshield.net/developers?source=tg-miniapp-findminiweb

The stated reason the Mini App exists is to expand the discovery surface for the bot **and the API
landing site**. This field is the only place in the submission that reaches the second one, and it
costs nothing.

**Same key on purpose.** Both links come from one destination, the FindMini listing. They land in
different log groups -- `relayshield-api` for a Check press, `relayshield-developer-signup` for the
landing page -- so they stay separable without burning a second key on one listing.

### Developer's Telegram contact  *(required, not published)*

`@Cryptonomicon1`, as you have it. Not published, so nothing to weigh.

---

## WHAT I CHANGED, AND THE ONE THING YOU MUST DO BEFORE THIS RESOLVES

**`tg-miniapp-findminiweb` is registered in all three lists that must agree**, which is the check
that stops FD-8 happening again -- an unregistered key is silently downgraded to the generic
`tg-miniapp` at the Worker's edge and logs `unmatched:` on the landing page, which is attribution
that looks like it worked:

* `miniapp_routes.json`, new rank 5, ranks below it shifted to stay contiguous
* `ALLOWED_SOURCES` in `cloudflare_worker_miniapp.js`
* `_SOURCE_ALIASES` in `relayshield_developer_signup.py`

**Why a separate key from `tg-miniapp-findminiapp`.** That one is the Telegram CHANNEL,
56,380 subscribers. This is the web directory. Same operation very probably, and still two
destinations: a channel post is ONE impression lasting a day, a directory listing is a STANDING
shelf that keeps returning arrivals. One key across both merges a broadcast with a permanent
surface and makes the delta uninterpretable, which is the `tg-miniapp-channel` defect this table was
rebuilt to remove.

Tests: `test_miniapp_routes.py` 77, `test_miniapp.py` 66, `test_developer_signup_banners.py` 7,
`node --check`, and `tools/miniapp_smoke.mjs` reporting every control responding. All green.

**You can submit the form NOW and merge in parallel.** FindMini's stated turnaround is under 24
hours, the deploy takes minutes, and a moderator clicking the link before the key is live still gets
a perfectly working app -- the key just downgrades to the generic one for that click. Nothing breaks,
and nobody arrives through the listing until it is published.

---

## ONE THING THAT IS NOT URGENT BUT SHOULD NOT BE LOST

**`relayshield_favicon.png` is 24576 x 24576 pixels and 87 MB.** That is not a favicon; it is a
generated asset nobody measured, committed at full size. Nothing in the repo references it, checked
by grep, so it is not slowing down a live page.

**It is slowing down every clone and every CI checkout, forever, and the figure is worse than it
sounds.** `git count-objects -vH` reports the whole repository packs to **88.15 MiB**. That one file
is 87 MB of it. Measured, not estimated: RelayShield's entire source history is about a megabyte and
the rest is an oversized icon.

Note it survives a blanket `*.png` rule in `.gitignore` because somebody force-added it.

The 512x512 icon above was produced from it, so it is not useless, just wrongly sized. Worth
replacing with a sane one and dropping the original in a later session. Not today, and not before
the submission.
