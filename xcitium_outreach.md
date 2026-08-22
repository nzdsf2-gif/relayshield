# Endpoint-security partner outreach — Xcitium and the wider list

*Decision and drafts, 2026-08-21. Nothing here has been sent.*

Part 1 is Xcitium specifically. **Part 2 is a reusable template** for ThreatLocker, Huntress,
Blackpoint Cyber, WatchGuard and LimaCharlie, with the per-company hook each one needs.

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


---
---

# Part 2 — General partner outreach template

For **ThreatLocker, Huntress, Blackpoint Cyber, WatchGuard and LimaCharlie**. Same motion as
Xcitium: a technology-alliance conversation, not a services pitch, routed to alliances or product
rather than a sales inbox.

## The one argument that works on all of them

Every company on this list instruments **something the customer owns** — an endpoint, a tenant, a
network, a log stream. The attacks RelayShield covers happen **where the customer owns nothing**:

* a **SIM swap** completes inside the mobile carrier's provisioning system;
* a **session cookie** from a stealer log resumes a session that is already authenticated, so no
  login event ever looks anomalous;
* a **credential from someone else's breach** logs in cleanly on the first attempt;
* an **OAuth grant** issued months ago keeps working after the password is rotated.

None of those produce a process to watch, a binary to block, or a failed login to alert on. They are
not a gap in anyone's product — they are outside the boundary every one of these products draws.

**That framing is the whole pitch, and getting it wrong kills the send.** Do not tell an endpoint
vendor their endpoint tool has a blind spot. Tell them the two things cover disjoint ground.

## The template

Replace `<HOOK>` with the company's line from the table below. Everything else stays.

> **Subject: Signal from outside the perimeter — possible fit with <COMPANY>'s partner stack**
>
> Hi <name>,
>
> <HOOK>
>
> I work on the attacks where the customer's own telemetry never fires. A SIM swap completes inside
> the carrier. A session cookie from a stealer log resumes a session that is already authenticated,
> so the login looks perfectly normal. A credential from a third-party breach works on the first
> try. There is no process to inspect, nothing to block, and no failed login to alert on — the
> evidence sits outside the boundary any endpoint or tenant tool can draw.
>
> RelayShield monitors that outside: live carrier queries for SIM/eSIM swap and port-out, breach and
> stealer-log exposure for a customer's people, lookalike domain registration, and OAuth grant
> abuse. It is not EDR, XDR or MDR and is not trying to be — it is an input, delivered as an alert
> or over an API.
>
> The reason I am writing to <COMPANY> rather than to an MSP directly: your partners already have a
> detection answer and a response answer, so this lands as a missing input rather than a competing
> console. Connectors already exist for Sentinel, XSOAR, Elastic and ConnectWise, so it can arrive
> inside a partner's current workflow instead of adding another pane of glass.
>
> Worth 20 minutes with whoever owns technology alliances? Happy to send the technical write-up
> first if that is the faster read.
>
> <signature>

## Per-company hook, and what to watch for

| Company | `<HOOK>` line | The thing that will decide it |
|---|---|---|
| **ThreatLocker** | "Allowlisting answers the hardest version of the endpoint problem: if it is not approved, it does not run. I am writing about the attacks where nothing needs to run." | Cleanest fit on the list. Default-deny is a strong, specific claim and the disjointness argument is exact — a stolen session needs no executable. Lead with ringfencing as the thing that *works*, then the class it cannot reach |
| **Huntress** | "Huntress ITDR already watches the Microsoft 365 tenant closely — unauthorised access, rogue rules, session abuse inside the tenant. I am writing about the part of that chain that happens before the tenant sees anything." | ⚠️ **The only real overlap on this list. Name it in the first line or the message fails.** Their ITDR covers identity *inside* M365. RelayShield covers the carrier and the criminal market — the credential's life before it reaches a login. Complementary, but only if you say so first; if you don't, they will, and less charitably |
| **Blackpoint Cyber** | "Your SOC's argument is time to response — analysts on it in minutes, not hours. I am writing about the signals that arrive before there is anything to respond to." | Sell **earlier warning**, not more coverage. An MDR's economics are analyst hours, so a signal that shortens triage or pre-empts an incident is a margin argument. Do not pitch it as more alerts — that is a cost to them |
| **WatchGuard** | "AuthPoint puts MFA in front of your partners' customers. A SIM swap is the attack that walks straight through the SMS half of that, and it happens at the carrier where no product can see it." | The sharpest single-sentence hook available, because it names a concrete failure of a product they sell. Keep it factual and unsmug — the point is that carrier-side monitoring makes their MFA *hold*, not that their MFA is weak |
| **LimaCharlie** | "You have built the opposite of a closed platform: telemetry, detections and third-party capability that customers compose themselves. I am writing because our data wants to be an input in exactly that shape." | ⚠️ **Different ask, not a different hook — change the last paragraph.** They are infrastructure, usage-billed, with an add-on marketplace. Propose being **an add-on / feed**, not a partnership. Lead with the API, STIX/TAXII and MISP surfaces and per-call pricing. Do not send them the alert-delivery story |

## Rules for the whole batch

* **No corpus-size headline.** If a number is needed: *500K+ distinct indicators, 5.8M+ citations*,
  and be ready to explain the difference — see the MSP brief. A single inflated figure is the exact
  mistake that nearly went out to the blockchain-analytics segment.
* **Never claim a joint customer, an existing partnership, or overlap you cannot name.** The XSOAR
  Tech Alliance thread is already gated on two named joint customers; do not invent them here.
* **Send one at a time, in the order in the table.** ThreatLocker first — it has the cleanest
  argument, and the first reply teaches you which objection is the real one before you spend the
  other four.
* **Do not send the EDR/MDR blog to any of them.** `relayshield_edr_mdr_complement_blog.md` is
  written for end customers, and its frame is "your EDR cannot see this". To a vendor that reads as
  an attack on their product. Send `RelayShield_MSP_Solution_Brief.md` instead — it is written for
  the channel and it is the document that actually matches this pitch.


---
---

# Part 3 — Wider target list, after the ThreatLocker send

*Added 2026-08-22. ThreatLocker sent; SentinelOne rejected and removed.*

## What the ThreatLocker send tells us about who to target

ThreatLocker was the cleanest fit on Part 2's list for one structural reason worth naming, because
it generalises: **its product makes a strong, specific, falsifiable claim** — if it is not approved,
it does not run. A specific claim gives the disjointness argument something to attach to. Vendors
whose marketing is a broad "complete protection" have no edge to work against, and the message
collapses into a generic pitch.

**So the filter is not "sells security to MSPs". It is:**

1. **A specific, nameable control** — allowlisting, containment, MFA, network segmentation, backup.
   The sharper the claim, the sharper the gap next to it.
2. **The control operates on something the customer owns** — a device, a tenant, a network, a
   session. That is what makes "outside the perimeter" a real boundary rather than a slogan.
3. **They sell through a channel**, so they are structurally interested in things their partners can
   resell or bundle.
4. **They are not already selling identity threat intelligence**, or if they are, we can name the
   overlap in the first line.

**And a negative filter, learned today: skip anyone whose partner programme has a hard commercial
gate.** SentinelOne's PartnerOne rejected in under five minutes — an automated screen on company
size or revenue, not a judgement on fit. Prefer vendors with an **open contribution route** (a
plugin repo, a marketplace with public submission, a documented integration path) over a partner
portal with a form. Rapid7 InsightConnect PR #4024 is the proof: an open-contribution repo took the
work with no gate at all.

## Ranked targets

Tier 1 first. Send one at a time — the first reply teaches you which objection is real before you
spend the rest.

### Tier 1 — specific control, channel-led, no obvious identity overlap

| Company | Their specific control | The disjointness line | Route |
|---|---|---|---|
| **ThreatLocker** | Application allowlisting and ringfencing | ✅ **SENT 2026-08-22** | — |
| **Huntress** | Managed EDR + ITDR for SMB via MSPs | ⚠️ Real overlap — ITDR covers M365 identity. Name it in line one: theirs is inside the tenant, ours is the carrier and the criminal market before any login | Partner/alliances |
| **Blackpoint Cyber** | 24/7 MDR with fast containment | Sell earlier warning, not more coverage. An MDR is billed in analyst hours, so extra alert volume is a cost — a signal that pre-empts an incident is a margin argument | Technology alliances |
| **WatchGuard** | AuthPoint MFA + firewall + endpoint | Sharpest single line available: a SIM swap walks straight through the SMS half of AuthPoint, at the carrier, where no product can see it. Keep it factual — the point is that carrier monitoring makes their MFA hold | Technology partner |
| **Todyl** | Single-agent consolidated SASE + SIEM + EDR for MSPs | Their pitch is "one agent, fewer tools", so an extra console is the objection. Lead with the API and the feed, not the alert product | Partner team |

### Tier 2 — platform and infrastructure plays, different ask

These want **data or a marketplace listing**, not a partnership. Do not send them the alert-delivery
story.

| Company | Why | The ask |
|---|---|---|
| **LimaCharlie** | SecOps Cloud Platform, usage-billed, add-on marketplace, telemetry-native | Be an add-on / feed. Lead with the API, STIX/TAXII, MISP and per-call pricing |
| **Tines** | SOAR, and we already ship a story there (`tines/`) | Extend the existing integration rather than opening a new relationship |
| **Rapid7 InsightConnect** | ✅ Already done — PR #4024, open contribution, no gate | Follow up on the PR; add actions once it lands |
| **Microsoft Sentinel** | Open contribution model, and PR #14924 is already in flight | Land #14924, then propose the second data-connector PR |

### Tier 3 — backup and recovery, an angle nobody is working

Worth naming because the argument is unusually clean and these vendors are deeply channel-led.

| Company | The line |
|---|---|
| **Datto / Kaseya**, **Acronis**, **Veeam** | Backup answers "we can restore after ransomware". It does not answer how the attacker got valid credentials — which, for the intrusions that matter, is a stolen session, a breached credential, or a swapped SIM. Restoring into an environment whose credentials are still exposed re-runs the incident. That is a genuinely different sale from every EDR conversation on this page |

### Explicitly not on this list

* **SentinelOne** — rejected 2026-08-21 by automated screen. Removed. Re-entry is a joint customer
  pulling for it, which is a sales outcome, not a submission to redo.
* **CrowdStrike** — no open build path found (2026-07-26 research); partnerships read as formal
  enterprise alliances. Deprioritised unless a specific deal pulls for it.
* **Xcitium** — Part 1 above, still unsent.

## Reuse note

The 50/100/250-word descriptions, form fields, technical spec and data-handling section in
`sentinelone_partner_submission.md` are vendor-neutral. Swap the product names in the "why this
integration" block and they work for every company above — that submission is not wasted work.
