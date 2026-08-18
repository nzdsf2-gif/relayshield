# Discord: landscape research

**Written 2026-08-11.** Commissioned after the Telegram directory route turned out to be largely
decayed or paywalled. Research only, nothing built.

**Headline: the barrier is far lower than expected, and materially lower than Telegram's.**

---

## The three facts that decide the shape of the build

**1. Verification is only required at 75+ servers.** Below that, a bot needs no review, no
verification, no approval. We can ship, list and grow to 74 servers with zero gatekeeping. That is
the opposite of the Telegram directory experience today.

**2. Slash commands require no privileged intents.** A `/scan` command works out of the box.

**3. Message Content Intent will be refused if slash commands can do the job.** Discord's own policy
is explicit: *"If your bot's functionality can be achieved via Slash Commands or Buttons, your
application for this privileged intent will be rejected."* Generic justifications are rejected.

**The product consequence, and it is a real constraint, not a detail:** we must build
slash-command-only. That means the bot **cannot** silently watch a channel and auto-flag a scam
link someone posts. A user has to invoke `/scan`. That is less magical than the Telegram inline
experience, where the result posts into the conversation, and the plan should not pretend otherwise.

It is also the right call regardless. Asking to read every message in a server, as a security
vendor, is exactly the permission a cautious admin refuses, and refusing it ourselves is a
credibility asset we can say out loud.

---

## What a RelayShield Discord bot would actually be

Same engine as the Telegram bot, different front end. No new backend capability.

- `/scan <link or address>` , the merged dispatcher we already built: URL to the VirusTotal path,
  address to GoPlus and Chainabuse.
- `/scam` , guidance when someone thinks they are being had.
- Ephemeral replies by default (visible only to the invoker), with a "post to channel" button. That
  matters: a scam check is often embarrassing, and forcing it public suppresses use.

**The credential-layer upsell works better here than on Telegram**, because ephemeral replies are
native. The public answer stays about the address; the private one can mention exposure and point
at a DM.

---

## Listing surfaces

| Surface | Notes |
|---|---|
| **top.gg** | The large third-party directory. Requirements are ordinary: bot online during review, public, invitable, main commands working, no spam or NSFW content in the description. No fee found in the published guidelines. |
| **Discord App Directory** | Discord's own, official, and separate from top.gg. Worth listing in both. |

Compared with Telegram, where StoreBot now 403s, BotsArchive wants EUR 10 for the channel post and
Botostore silently swallowed a submission, these are functioning, documented, first-party-adjacent
channels.

---

## Why the audience is worth it

Crypto communities live on Discord at least as much as Telegram, and NFT and DeFi projects are
overwhelmingly Discord-first. Scam links in project servers are a permanent, unsolved moderation
problem, which is the same wedge as the Telegram group play but into a larger room.

---

## Honest caveats

- **Slash commands are less viral than Telegram inline.** Telegram inline stamps every posted result
  "via @relayshield_bot" to the whole chat. A Discord ephemeral reply is seen by one person. The
  compounding loop is weaker unless the user chooses to post it, so the "post to channel" button is
  not a nicety, it is the growth mechanic.
- **75 servers is a real threshold**, and hitting it triggers a verification review. Plan for it
  rather than being surprised.
- **Server admins are gatekeepers.** A bot spreads by admins adding it, and crypto server admins are
  justifiably paranoid. Not asking for Message Content Intent is the single strongest thing we can
  put in front of them.
- **This is a third channel while two are unfinished.** Telegram inline shipped today and has no
  users yet. The founder-stated preference is high-potential channels one at a time. Discord is
  worth doing; it is not obviously worth doing before Telegram has been given a fair run.

---

## Recommended sequence, if it goes ahead

1. Slash-command bot with `/scan` and `/scam`, ephemeral by default, no privileged intents.
2. List on the Discord App Directory and top.gg.
3. Approach a small number of crypto server admins, leading with "we deliberately cannot read your
   messages."
4. Only then think about the 75-server verification threshold.

## Sources

- [Discord Bot Guidelines, Top.gg](https://support.top.gg/hc/en-us/articles/23146912808988-Discord-Bot-Guidelines)
- [Message Content Intent Review Policy, Discord](https://support-dev.discord.com/hc/en-us/articles/5324827539479-Message-Content-Intent-Review-Policy)
- [About privileged intents and public bots](https://docs.discord.red/en/latest/intents.html)
- [Discord privileged gateway intents and MESSAGE_CONTENT in 2026](https://space-node.net/blog/discord-gateway-intents-message-content-2026)
