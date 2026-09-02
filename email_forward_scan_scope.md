# Forward-an-email scan address — scope

*Written 2026-09-02. FD-8 candidate. Nothing built yet.*

---

## The problem it solves

The bots can only see what a user can get into a chat window. That is fine for an SMS (copy, paste)
and fine for a Telegram message (forward). It is worst exactly where phishing actually lands:
**email**.

To check a suspicious email today, a user must open it, select the body, copy it, switch app, and
paste. Every one of those steps loses people, and the copy loses the part that matters most —
**the real sender address and the headers**. A pasted email body is the weakest possible input:
display names survive, `Return-Path`, `Received:` and SPF/DKIM/DMARC results do not.

Forwarding an email is a **one-tap gesture every email user already knows**, on every client, with
no new app and no account. It is the single highest-leverage input channel we do not have.

## Why it is cheap here specifically

Cloudflare Email Routing is already live and proven on `relayshield.net`. TODO.md item 23 records a
full audit: rule Active, destination Verified, MX/SPF/DMARC correct, **45 of 45 delivered** over 30
days. The infrastructure question is already answered; this is a routing rule and a Worker, not a
mail stack.

## Shape

    user forwards suspicious email
        -> scan@relayshield.net
        -> Cloudflare Email Routing rule
        -> Email Worker (message.raw)
        -> parse: headers, body text, links, attachments-by-name
        -> the SAME analyser the bots use
        -> reply by email to the sender's address

**The analyser is not rewritten.** `_build_msgscan_response()` already produces the verdict, and
`relayshield_forward_analysis` already produces the provenance block. This adds an input adapter
and an output adapter, nothing else. That is the same "one core, thin adapters" shape as the
Telegram and WhatsApp forward handlers, and for the same reason: a second copy of the fraud logic
is a second thing to keep correct.

## What email gives us that the bots cannot

This is the part that makes it more than a convenience:

| Signal | Telegram | WhatsApp | Email |
|---|---|---|---|
| Original sender identity | id + username | **none, ever** | **full envelope + From** |
| Authentication result | n/a | n/a | **SPF / DKIM / DMARC** |
| Routing path | no | no | **`Received:` chain** |
| Reply-to mismatch | no | no | **yes** |

A forwarded email carries `Authentication-Results` from the user's own provider. That is a
verdict computed by Google or Microsoft, and a DMARC `fail` on a message claiming to be from a bank
is about as strong a signal as this product can get anywhere. It is strictly better provenance than
Telegram's, and Telegram's is the best the bots have.

## Decisions to make before building

1. **Address.** `scan@relayshield.net` reads as an instruction. `check@` is the alternative. Pick
   one and never change it — it will end up in printed material.
2. **Who may use it.** Open to anyone is a free abuse surface and a free acquisition channel at the
   same time. Recommend: **open, rate-limited per sender, no account required**, matching the free
   tier's existing posture. An unknown sender gets the verdict plus one line about the bot.
3. **Attachments.** Scan by name and type only in v1. Detonating attachments is a different product
   with a different risk profile; VirusTotal file submission already exists behind `ATTACH` and can
   be wired later.
4. **Reply format.** Plain text, not HTML. It renders everywhere, cannot carry a tracking pixel, and
   cannot itself look like phishing.
5. **Retention.** A forwarded email is somebody's mail. Store the verdict and the extracted IOCs;
   **do not store the body.** This is the one decision that is hard to reverse.

## Risks, named

- **We become a spam destination.** Any published address does. Cloudflare Email Routing drops most
  of it, and per-sender rate limiting handles the rest. Budget for it rather than being surprised.
- **The reply could be forged in our name.** The reply is what a user trusts, so
  `scan@relayshield.net` needs its own SPF/DKIM/DMARC alignment before the address is published
  anywhere, not after.
- **Loop risk.** A reply to an auto-forwarder can ping-pong. Drop anything with our own address in
  the `Received:` chain, and never reply to a `no-reply@` or a message carrying
  `Auto-Submitted: auto-*`.
- **PII.** Forwarded mail will contain personal data nobody consented to us holding. Decision 5 is
  the control, and it has to be built in from the first commit, not added later.

## Effort

| Piece | Estimate |
|---|---|
| Email Worker skeleton, routing rule, DNS | 0.5 day |
| Header/body/link parsing, DMARC extraction | 1 day |
| Wire to the existing analyser and provenance renderer | 0.5 day |
| Reply composition, loop and auto-reply guards | 0.5 day |
| Rate limiting, abuse handling, retention policy in code | 1 day |
| **Total** | **3.5 days** |

## Why it belongs on the front-door list

It is the only entry point that needs **no app, no install, no account and no new gesture** — a
user forwards an email, which they already do many times a week. For an audience like Bob Kramich
that is a materially lower bar than any bot command, and unlike the Chrome extension (FD-6) there
is nothing to install.

Sequence it after FD-1 to FD-3, which are publish steps against code that already exists. This is a
build.

**Attribution:** register `source=email-scan` in `_SOURCE_BANNERS` in
`relayshield_developer_signup.py` before the address appears anywhere.
