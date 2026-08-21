# Xcitium — EDR/XDR partner outreach

*Decision and drafts, 2026-08-21. Not yet sent.*

## Recommendation: yes, send — but not as a services pitch

Sending is worth it. This is one of the few outreach motions currently **ungated** — Segment 1
(blockchain analytics) is tabled on exclusive-indicator volume, Segment 2 is gated on the MetaMask
Snap approval, and Zapier is frozen until 1 September. Xcitium needs none of those.

Three reasons it fits better than a generic vendor cold email:

1. **Their product thesis names the gap for us.** Xcitium's differentiator is auto-containment /
   ZeroDwell — unknown executables run in a virtual container so an unknown binary cannot do harm.
   That is a strong answer to *code you didn't expect running on a box you own*. The attacks
   RelayShield covers **run no code on the endpoint at all**: a SIM swap happens inside the carrier,
   a stolen session cookie resumes an already-authenticated session, a credential from a third-party
   breach logs in successfully the first time. There is nothing to contain because nothing executes.
   That is a clean, factual complement, not a criticism of their engine.
2. **Their channel is MSP/MSSP-heavy**, which is the segment we already have collateral for —
   `RelayShield_MSP_Solution_Brief.md`, `relayshield_msp_digest.py`, the ConnectWise webhook, and
   SIEM/SOAR connectors for Sentinel, XSOAR and Elastic. We are not asking them to imagine an
   integration path.
3. **The published asset already exists.** `relayshield_edr_mdr_complement_blog.md` is the argument
   in long form and can be linked rather than pasted.

### The one thing that must not be got wrong

**Do not send the blog's framing to an EDR vendor.** That post is written for end customers and its
frame is "your EDR cannot see this" — which, addressed to the company that sells the EDR, reads as an
attack on their product and gets deleted. Invert it: their containment story is the *reason* the fit
is clean, because the two cover disjoint attack classes. The drafts below do that deliberately.

### Two objections to pre-empt

- *"We already have threat intelligence."* They do. The pitch is not a feed — it is telecom/carrier
  and identity signal (SIM swap, port-out, session exposure) that a TI feed does not carry.
- *"Who are you?"* Small vendor, and pretending otherwise fails on the first search. Lead with what
  is live and specific, not with scale.

### Honesty rules for this send

- **No corpus-size headline.** Not 511K, not 5.4M. That number nearly went out to blockchain
  analytics buyers who ingest most of it already, and it would fail the same way here.
- Do not describe RelayShield as EDR, XDR, or a replacement for either.
- Do not claim an existing partnership, customer overlap, or joint customers we cannot name.

### Routing

Technology alliances / partner team first — the same motion as the XSOAR Tech Alliance application.
Secondary: Product or Channel leadership on LinkedIn. Do **not** route to a sales inbox; this is not
a purchase conversation in either direction.

---

## Message 1 — primary, short cold open (LinkedIn or email)

> **Subject: The attacks that never touch the endpoint — possible fit with Xcitium's MSP stack**
>
> Hi <name>,
>
> Containment answers the hard version of the endpoint problem: an unknown binary lands, and it
> cannot do damage while it is unknown. I am writing about the class of attack where nothing lands
> at all.
>
> A SIM swap happens inside the mobile carrier. A session cookie lifted from a stealer log resumes
> a session that is already authenticated. A credential from someone else's breach logs in cleanly
> on the first attempt. In all three the endpoint is healthy, the process tree is ordinary, and
> there is nothing to contain — because nothing executed.
>
> RelayShield monitors that layer: live carrier queries for SIM/eSIM swap and port-out, breach and
> stealer-log exposure for a customer's people, lookalike domain registration, and OAuth grant
> abuse. It is not EDR and does not want to be — it is signal from outside the perimeter, delivered
> as an alert or over an API.
>
> The reason I am writing to Xcitium specifically rather than to an MSP: your partners already have
> a containment answer and a managed answer, so this arrives as a missing input rather than a
> competing console. There are SIEM/SOAR connectors already built (Sentinel, XSOAR, Elastic) and a
> ConnectWise path, so it can land in a partner's existing workflow instead of adding a tenth pane
> of glass.
>
> Worth 20 minutes with whoever owns technology alliances? Happy to send the technical write-up
> first if that is the faster read.
>
> <signature>

## Message 2 — LinkedIn DM variant (under the character limit, no subject line)

> Hi <name> — Xcitium's containment story answers the "unknown binary on a box you own" problem
> better than most. I work on the attacks that never put a binary anywhere: SIM swap inside the
> carrier, stolen session cookies resuming an authenticated session, breached credentials that log
> in cleanly the first time. Endpoint stays healthy, nothing to contain.
>
> RelayShield monitors that layer — carrier-level SIM/port-out checks, breach and stealer-log
> exposure, lookalike domains, OAuth abuse — with connectors into Sentinel, XSOAR, Elastic and
> ConnectWise so it lands in a partner's existing workflow rather than a new console.
>
> Not an EDR, not pitching one. Is technology alliances the right door, or should I be talking to
> someone on channel?

---

## If they reply

Send `relayshield_edr_mdr_complement_blog.md` and `RelayShield_MSP_Solution_Brief.md`, in that
order. The blog carries the argument; the brief carries the packaging.

**Before quoting any figure on a call, re-measure it.** The last measured set is in
`victim_side_outreach_messages.md` and was taken 2026-08-17 — treat anything older than about a week
as stale, and quote per-category exclusive numbers rather than a total.
