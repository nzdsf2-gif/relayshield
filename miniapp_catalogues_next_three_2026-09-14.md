# Three more catalogues, keys registered, ranked by what is actually verified

**2026-09-14.** After miniTelegram's form crashed on four separate icon files and discarded the
filled form each time. FindMini is submitted and publishing. These are the next three.

**All three keys are registered in the three lists that must agree, before any submission.** An
unregistered key is silently downgraded to the generic `tg-miniapp` at the Worker's edge and logs
`unmatched:` on the landing page, which is attribution that looks like it worked.

| Rank | Catalogue | Key | Route verified? | Needs an image? |
|---|---|---|---|---|
| 1 | **awesome-telegram-mini-apps** | `tg-miniapp-awesome` | **YES, from its own CONTRIBUTING.md** | **NO** |
| 2 | **ton.app** | `tg-miniapp-tonapp` | YES, from its own Terms of Service | probably |
| 3 | **tg.app** | `tg-miniapp-tgapp` | no, search summary only | unknown |

---

## 1. awesome-telegram-mini-apps — DO THIS ONE FIRST

**It is the only route here with no file picker anywhere in it.** One line of Markdown in a pull
request, submitted from a browser. Given that the last two rounds were lost to an upload dialog
crashing, that property matters more than the audience size.

**The route was READ, not inferred.** `CONTRIBUTING.md` in the repo says, verbatim: one pull request
per suggestion, additions go to the bottom of the relevant category, and the format is
`- [Resource](link) - Description.` The `## Products` section is where we belong, and its most
recent entry already uses the `t.me/<bot>/<app>` Mini App form, so our link fits the house style
rather than asking for an exception.

**The line to add, at the BOTTOM of `## Products`:**

    - [RelayShield IDCheck](https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-awesome) - Check a link, a TON address or a Telegram handle before you trust it. No signup and no wallet connect.

**How to submit it without cloning anything.** Open the README on GitHub, press the pencil icon to
edit, and GitHub forks the repo and opens a pull request for you. Title it
`Add RelayShield IDCheck to Products`. In the body, say what it does in one sentence and that it is
free and needs no wallet connection, because their guideline asks for the link and why it should be
included.

**The `?startapp=` parameter is deliberate and I would keep it.** It is Telegram's own documented
Mini App deep-link parameter rather than a marketing tracker, and it is the only thing that will
tell us whether a developer-audience list sends anybody. Small risk a maintainer strips it; the
listing still succeeds if they do.

**Be honest about what this route is worth.** It is a developer list, not a consumer catalogue, so
an arrival is more likely to be a bot developer than somebody checking an address before they send
money. That is a poor VOLUME bet and a good FIT bet, and it happens to be the exact audience the
`tg-miniapp-bottoken` route already exists for.

---

## 2. ton.app — the best category fit we will get anywhere

**Their own Terms of Service is the source**, which is the standard this programme should have been
holding all along: *"Dapp developers have the right to submit an application to TON App for listing
their dApp on the website. If TON App determines the dApp is appropriate, it will be listed and made
public."* Acceptance and ranking are at their discretion.

**This is the one destination where TON-only is the HEADLINE rather than a limitation.** Everywhere
else we have to explain why the Check tab refuses Ethereum and Solana. On a TON catalogue that
refusal is the product being exactly what the audience wants, and the watchlist monitor watching TON
and only TON stops being a caveat.

**ANDREW CLICKS THIS:** open `ton.app` and look at the header and footer for "Submit", "Add your
dApp", "List your app" or "For developers". **UNVERIFIED from the container** -- ton.app is
egress-blocked here, so I have their ToS via search and not their navigation. The web-front-door
finding says the submission route will be visible in one look.

Deep link when you get there:

    https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-tonapp

---

## 3. tg.app — cheapest to check, weakest evidence

Described as letting you list a mini-app, bot, channel or group from one catalogue, **free, with a
quick review**. That is a search summary and nothing more: **tg.app is egress-blocked here, so I
have not read their own page and this is explicitly the weaker of the three.**

Check it the same way, and apply the type check before submitting anything: **a curated catalogue
with a submission route, or a broker selling promoted posts?** If every listing looks like an
advertisement and the only way in is paying for a post, it is the second kind and we do not submit.
That check is what `@telegtapps` failed.

    https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-tgapp

---

## ONE I CHECKED AND AM REJECTING, SO NOBODY SPENDS A ROUND ON IT

**`telesearch/Telegram-Mini-Apps-List` on GitHub.** It looks like a fourth candidate and it is not.
Read from the repo itself rather than from the search result that surfaced it:

* **Last updated December 2024**, stated in the README's own header.
* **No `CONTRIBUTING.md`** -- a 404. There is no submission route; the owner maintains the list.
* It is ranked purely by monthly users, and the top thirty are PAWS, Blum, Hamster Kombat, Not
  Pixel, Tomarket. **A clicker leaderboard**, which is the `@telegtapps` audience problem again.

Three reasons, any one of which is enough. Recorded here because the cheapest thing I can do is stop
the next session rediscovering it.

---

## WHAT I GOT WRONG ON THE ICON, RECORDED PLAINLY

I decided the chat delivery was re-encoding images to `.webp`, and that was true, but **I never
confirmed which files your four attempts actually used.** Then I sent you back a file you had
already tried and told you it was different. It was the same bytes. The theory was built on an
assumption, and the fix I shipped on top of it was worthless.

**The right move after the first failure was one question about what you were holding, not four
generated variants.** This repo already records that when the same instruction fails three times the
instruction is the loop, and I ran it to four.

**miniTelegram is parked, not abandoned.** A form that crashes and discards a filled submission is
their defect and no image fixes it. If you want it later, their FAQ page will carry a contact and
the report costs one email. It is behind all three above.
