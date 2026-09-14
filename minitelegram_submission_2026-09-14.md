# miniTelegram submission: the key is live, here is the form

**2026-09-14.** Second web front door, after FindMini went in earlier today.

---

## YES, START THE FORM. THE KEY IS REGISTERED AND THE DEPLOY IS GREEN.

`tg-miniapp-minitelegram` is registered in all three lists that must agree, the same check that
stops FD-8 happening again:

* `miniapp_routes.json`, new rank 6
* `ALLOWED_SOURCES` in `cloudflare_worker_miniapp.js`, the Worker's edge gate
* `_SOURCE_ALIASES` in `relayshield_developer_signup.py`, the landing page

**One thing has to happen before an arrival through this listing is attributed**, and it is the same
step as yesterday: merge and push so the Worker and the landing page redeploy. Until then an arrival
carrying this key is silently downgraded to the generic `tg-miniapp` at the edge.

**You can fill the form before that lands.** Their team reviews before publication, so nobody
arrives through the listing on the day you submit it. The block at the end of this file does the
push.

---

## THE FORM, FIELD BY FIELD

Their flow, as described: sign in with Telegram, then submit an app card. **UNVERIFIED from the
container** -- minitelegram.com is egress-blocked here, so the field list below is what their FAQ
describes and the labels may differ. Everything in it is reused from the FindMini submission, which
is the point: one product, one description, across every catalogue.

### Official link

    https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-minitelegram

**Note the key differs from the FindMini link by one word.** That is deliberate and it is the whole
reason this is worth doing properly: two standing listings that cannot be told apart in the logs are
one listing as far as any decision is concerned.

### App name

    RelayShield IDCheck

Same as everywhere. Not "RelayShield", which belongs to the TI monitoring product on the same bot,
and not "IDCheck", which drops the only word that makes us findable by name.

### Short description

    Check a link, a TON address or a Telegram handle before you trust it. No signup, no wallet connect.

19 words. Written against the page the Worker actually serves, so it names all three inputs the
paste box accepts rather than two of them.

### Full description

Unchanged from the FindMini submission -- see `findmini_submission_2026-09-14.md`, which was sent
with the previous reply and is committed. It names SOURCES and CAPABILITIES and quotes no corpus
counts, because a catalogue entry is a standing page we cannot cheaply edit.

The three refusals stay in, and they are the part that distinguishes us from every other entry in a
Telegram app directory: it never says something is safe, it never touches the wallet, and it checks
TON and only TON.

### Categories

**CORRECTED. My first answer named four categories that do not exist on the form.** I recommended
Security, Utilities, Tools or TON without having seen the list, which is the same defect as writing
a BotFather step for a bot whose apps I had never listed: a well-formed instruction written against
an unexamined state. The options are wallets, trading and analytics, tasks and productivity, and
loaders.

**Pick "tasks and productivity", and it is the only one of the four that is not a false claim.**

The argument is not preference, it is that three of them contradict the submission's own copy:

* **Wallets** is the trap, because it looks closest and it is the worst. The full description a
  moderator reads two fields later says outright *"It does not connect to your wallet, ask for a
  seed phrase, or ask you to sign anything."* Filing a non-wallet app under Wallets is a
  self-contradiction inside one submission, and it puts us in the shelf a cautious user is browsing
  precisely because they are trying to check something.
* **Trading and analytics** would claim trading signals or portfolio analytics. We do neither.
* **Loaders** is clicker and tap-to-earn infrastructure. Wrong audience and a bad neighbourhood for
  a security product, which is the `@telegtapps` argument again.

**Tasks and productivity is a genuine fit rather than a least-bad fallback.** IDCheck is a utility
you open to get one thing done and then close. It is not a place you keep money and not a game.

**Two things worth doing while you are there.** If the form allows multi-select, pick that one
ALONE rather than adding Wallets for reach. And if there is a free-text or "other" field, say
"security" in it: a catalogue with no security category and a growing number of checker apps is one
that may add one, and being the app that asked is cheap.

### Screenshots

The same five frames as FindMini, taken on one phone in one sitting. If you already took them for
that submission, reuse the identical files -- there is no reason for two catalogues to show
different screenshots of the same app, and re-shooting risks a mismatched set.

### Language

**EN only.** Matches the interface.

### Profile picture

`assets/miniapp/idcheck_icon_512.png`, the 512x512 generated from the brand design. Already sent,
and in the repo after the merge below.

---

## AFTER YOU SUBMIT

**ANDREW RUNS THIS**, once the merge below has landed and the two deploy workflows are green:

Open `https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-minitelegram` on your phone and press
**Check it** on anything. Opening the link logs nothing on its own; pressing Check it is what writes
the `source=` line the counter reads.

Then take the baseline, before the listing publishes:

    AWS_PROFILE=relayshield ~/.rsvenv/bin/python tools/miniapp_funnel.py --days 30 --snapshot before-minitelegram

It refuses to overwrite an existing baseline, which is the most important line in that tool:
overwriting after the listing is live turns the before-and-after into a comparison of a number with
itself, and that reads as "the channel did nothing".

---

## WHAT IS LEFT AFTER THIS

**tApps Center is the third and it is still unresolved**, waiting on one observation only you can
make: when you opened `t.me/app_moderation_bot`, did Telegram show a START button and a bot
description, or nothing at all? That single answer separates "the bot is live and wants a deep-link
payload" from "the username is wrong or abandoned", and they have completely different next steps.

Do not spend another round on tApps before that is answered. Two of the three web front doors will
be submitted by the end of today, which was the whole of Top 15 item 1.
