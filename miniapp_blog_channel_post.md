# The RelayShield blog channel post, and how to pin it

Written 2026-09-12, asked as: *"Am i just inserting the link as part of that blog's broadcast and is
there a way to pin the link with some marketing plug?"*

**Short answers: it is its own post, not a line inside another one. Yes, you can pin it, and a
pinned post is the only thing on a Telegram channel that keeps working after the broadcast has
scrolled away.**

---

## 1. Post it as its own message

A link buried inside a broadcast about something else gets read as a footnote. The Mini App is the
subject of this post or it is not in it.

**Copy below, ready to paste. Nothing in it is a claim we cannot support.**

---

Paste starts here:

RelayShield IDCheck is live inside Telegram.

Paste a link or a TON address. You get back what is actually known about it: our indicator corpus
collected from criminal Telegram channels, Google Safe Browsing, and how old the domain is. No
signup, no key, no card.

It never tells you something is safe. The best answer it gives is "nothing known against it",
because an absence of evidence is not proof, and a security tool that says "safe" is lying to you
the one time it matters.

Three things it does that a link checker does not:

Watch an address. Tap "Tell me if this changes" and we re-check it every few hours and message you
here the moment it does. Liquidity pulled, balance drained, a contract deployed at an address that
had none, or newly flagged as a scam. Three addresses free, alerted immediately and in full.

Work inside any chat. Type @relayshield_bot followed by a link in any conversation and the verdict
posts into that conversation. You do not have to leave the chat where the scam was posted.

Spot the fake. A quick drill on lookalike domains, which is how most of this actually reaches
people.

Open it: https://t.me/relayshield_bot/idcheck?startapp=tg-miniapp-blog

Paste ends here.

---

**Three notes on the copy.**

- **"Three addresses free, alerted immediately and in full" is the one line that is not negotiable.**
  Stars buy more watch slots and nothing else. Any hint that paid alerts are faster or more complete
  would be taxing the free tier while claiming not to, and a test in this repo forbids those words in
  the app itself.
- **It does not mention Stars at all.** A first post that opens with a price sells before anybody has
  felt the value. The tier is on screen inside the Watching tab the moment they open it, which is the
  right place for it.
- **Do not let the composer turn it into Markdown.** `@relayshield_bot` carries an underscore, and
  Telegram's legacy Markdown has no escape syntax. Typed as plain text in the channel composer this
  is fine. If you want emphasis, select the words and use the app's own Bold, never asterisks.

---

## 2. Pin it

**UNVERIFIED from the container** -- core.telegram.org is egress blocked here, so this is written
from how Telegram channels have worked rather than from the current documentation. It is a two-second
check on your own channel either way.

- **Phone:** long-press the posted message, tap **Pin**. It asks whether to notify subscribers.
- **Desktop:** right-click the message, **Pin**.

A pinned message sits in a bar at the top of the channel for every subscriber, so it keeps working
after the post has scrolled away. That is the whole reason to pin rather than just post.

**This is also the closest thing that exists to "pinning the Mini App".** Telegram has no primitive
for pinning a Mini App: what a user pins is a chat. A pinned channel post carrying the link is the
nearest equivalent that we control, and it does not touch `@relayshield_bot`'s menu button, which
belongs to the TI monitoring product and stays there.

---

## 3. What this post is FOR, at four subscribers

Measured 2026-09-12: the channel has **4 subscribers**. That closes the UNMEASURED line in
`miniapp_discovery_funnel.md` and it changes nothing about the running order, for one reason.

**The blog channel was never ranked first for reach.** It ranks first because it is the cheapest
possible place to discover that something is wrong, and at four subscribers that is more true rather
than less. What it is rehearsing:

1. **Does the link render and open?** A `t.me/<bot>/<app>` link posted in a channel is the exact
   artefact every other channel will carry. If it renders badly, or opens to something broken on a
   phone that is not yours, four people see it instead of 3.9 million.
2. **Does `tg-miniapp-blog` reach the logs?** That is the whole attribution chain end to end: the
   `?startapp=` value, the Worker's `ALLOWED_SOURCES` gate, the `source=` on the API call, the
   CloudWatch line, and `tools/miniapp_funnel.py`'s filter. A key that is sent, accepted and never
   logged is a false absence, and it has happened twice in this repo already.
3. **Does the before-and-after mechanism work at all?** `--snapshot before-blog` then
   `--compare before-blog` on a channel where you can predict the answer is the only cheap place to
   find out that the comparison prints something useless.

**A delta of one arrival from this post is a success.** It proves the chain. A delta of zero from a
channel with four subscribers proves nothing about the app and quite a lot about the measurement, so
read it as a broken pipe rather than a verdict.
