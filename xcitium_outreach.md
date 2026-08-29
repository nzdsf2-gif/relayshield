# EDR/XDR partner outreach — Xcitium and the wider target set

*Decision and drafts, 2026-08-21. Target set and customisation added 2026-08-27.*

**Sent so far:** ThreatLocker, Huntress, Blackpoint Cyber. Xcitium not yet sent.

---

## Recommendation: yes, send — but not as a services pitch

Sending is worth it. This is one of the few outreach motions currently **ungated** — Segment 1
(blockchain analytics) is tabled on exclusive-indicator volume, Segment 2 is gated on the MetaMask
Snap approval, and Zapier is frozen until 1 September. This segment needs none of those.

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
- **Do not name a channel count.** The figure differs across four of our own surfaces
  (95 / 87 / 122 / 37+). Until that is reconciled and re-measured, say "criminal Telegram channels"
  without a number rather than pick one and be wrong in front of a vendor who may check.

### Routing

Technology alliances / partner team first — the same motion as the XSOAR Tech Alliance application.
Secondary: Product or Channel leadership on LinkedIn. Do **not** route to a sales inbox; this is not
a purchase conversation in either direction.

---

# The target set

Ordered by fit, not by size. Fit here means three things at once: **(a)** their product stops
something that executes, so our disjoint-attack-class argument lands as complement rather than
competition; **(b)** they sell through MSPs/MSSPs, where our existing collateral and connectors
already fit; **(c)** there is a technology-alliance or integrations door that is not a sales inbox.

| # | Company | Why they fit | Door | Status |
|---|---|---|---|---|
| 1 | **Huntress** | Managed EDR + ITDR for SMB via MSPs; identity is already their expansion story | Integrations / partnerships | **SENT** |
| 2 | **ThreatLocker** | Allowlisting and ringfencing: the purest "nothing unapproved executes" thesis | Technology alliances | **SENT** |
| 3 | **Blackpoint Cyber** | MDR built for MSPs; 24/7 SOC that would consume our signal as an input | Partner / integrations | **SENT** |
| 4 | **Xcitium** | ZeroDwell auto-containment, MSP-heavy channel | Technology alliances | Drafted below, not sent |
| 5 | **Todyl** | Single-agent SASE + EDR + MDR for MSPs; module-shaped platform, we are a natural module | Partnerships | Not started |
| 6 | **Coro** | SMB-focused consolidated platform sold heavily through MSPs; explicitly buys breadth | Alliances | Not started |
| 7 | **Guardz** | MSP-native, identity and email risk already central to their pitch | Partnerships | Not started |
| 8 | **Cynet** | All-in-one for lean teams and MSSPs; "one platform" story wants inputs it does not own | Alliances | Not started |
| 9 | **Adlumin** | MDR/SOC platform, MSP and mid-market; SIEM-shaped, so our connectors matter | Integrations | Not started |
| 10 | **Field Effect** | Canadian MDR sold through partners; small enough that a small vendor gets read | Partnerships | Not started |
| 11 | **Acronis** | MSP platform with security bolted onto backup; hungry for security differentiation | Technology alliances | Not started |
| 12 | **Sophos** | MSP channel at scale, Managed Risk product line is adjacent to our signal | Technology alliance programme | Lower priority: big-vendor process |

## Deliberately not on this list

- **CrowdStrike, SentinelOne, Palo Alto, Microsoft.** Their alliance programmes have a
  minimum-viable-partner bar we do not clear today (named joint customers, revenue commitments,
  marketplace certification). Approaching them now spends the first-impression card at the exact
  moment we cannot answer "who else uses this". Revisit when there are two named joint customers.
  Note SentinelOne registration is already an open carried-forward item — that is a separate motion.
- **Pure identity vendors** (Okta, JumpCloud, Push Security). The overlap is genuine rather than
  disjoint, so the complement argument weakens and it turns into a competitive conversation.
- **Pure TI vendors** (Recorded Future, Intel 471, Flashpoint). They sell what looks superficially
  like what we sell, they have more of it, and the "we have telecom signal you do not" argument is
  better made to someone who does not benchmark feeds for a living.

---

# Customisation for the top candidates

The Message 1 / Message 2 drafts below are the base. Do not send them unmodified. For each target,
**replace the containment sentence in paragraph 1** with that company's own thesis in their language,
and **replace the "reason I am writing to X specifically" paragraph**. Everything else can stand.

Two rules that apply to every one of them:

- **Mirror their vocabulary, not ours.** ThreatLocker says "allowlisting" and "ringfencing";
  Huntress says "tradecraft" and "the SOC"; Blackpoint says "MDR" and "response"; Xcitium says
  "ZeroDwell" and "auto-containment". Using their word in the first sentence is what signals you
  actually looked at the product.
- **One sentence of specificity beats a paragraph of positioning.** Name the endpoint, the connector,
  or the exact alert. Vague capability claims from an unknown vendor read as noise.

### 1. Huntress — SENT

**Their thesis:** managed EDR plus ITDR, human SOC, sold to and through MSPs serving SMB.

**Hook if you follow up:** they already sell identity threat detection, so the disjoint-class
argument is narrower here and must be precise. Their ITDR watches the identity *after* it is in
Microsoft 365 — sign-ins, inbox rules, session anomalies. Ours watches the same identity *before*
that: the carrier-level SIM swap that intercepts the OTP, and the stealer-log exposure that hands
over a valid session in the first place. Say "upstream of your ITDR", not "your ITDR misses this".

**Follow-up angle:** their SOC analysts are the buyer of a feed like this, not the product team. Ask
whether the SOC would find pre-incident carrier and stealer-log signal actionable, and offer a
read-only API key for one analyst to try against their own tenant list.

### 2. ThreatLocker — SENT

**Their thesis:** default-deny allowlisting and ringfencing. Nothing runs unless approved.

**Hook if you follow up:** they have the strongest version of the "nothing executes" story in the
market, which makes our argument cleanest against them. A SIM swap and a stolen session are not
things a policy can deny, because no process starts. Frame it as: your policy engine ends the
question of what runs; this covers what happens where nothing runs at all.

**Follow-up angle:** ThreatLocker's community and their conference are unusually open to small
vendors. If the email goes cold, the technology-alliance form plus a presence at their event is a
better second attempt than another email.

### 3. Blackpoint Cyber — SENT

**Their thesis:** MDR with a 24/7 SOC, built specifically for MSP delivery, response-first.

**Hook if you follow up:** they are a consumer of signal, not a builder of it, which is the easiest
possible fit. The pitch is an input to their SOC queue, not a product. Lead with the SIEM/SOAR
connectors and the ConnectWise path, because the question they care about is whether it lands in
existing workflow.

**Follow-up angle:** ask what their SOC would want to see on a SIM-swap alert to make it actionable
at 3am. That is a real question, the answer is useful to us regardless, and it converts a pitch into
a design conversation.

### 4. Xcitium — drafted, not sent

**Their thesis:** ZeroDwell auto-containment. Unknown executables run in a virtual container so an
unknown binary cannot do harm while it is unknown.

**Customisation already applied** in the drafts below: paragraph 1 leads with containment in their
words, and the "why Xcitium specifically" paragraph names their MSP channel plus the existing
connectors.

**Extra angle worth adding for them specifically:** their differentiator is the *unknown* file. Our
strongest single line for that audience is that credential and session attacks have no unknown to
contain, because the artefact is a valid credential and the process is the real browser. That is a
sentence they will not have heard from a TI vendor.

### 5. Todyl — highest-value of the unsent

**Their thesis:** one agent, several modules (SASE, EDR, MDR, SIEM) sold to MSPs.

**Why they may be the best fit on this list:** their architecture is explicitly modular and their
sales motion is "add another module to the same agent". We are shaped like a module they do not have
and would not build, since carrier relationships and stealer-log collection are nothing like their
core engineering. Their SIEM module also means our connector work is directly relevant.

**Customisation:** replace the containment sentence with their consolidation thesis — "you have
consolidated the endpoint, network and detection stack behind one agent" — then make the point that
the carrier and the criminal marketplace are the two surfaces no agent can reach, because neither is
on the customer's network.

### 6. Coro

**Their thesis:** consolidated SMB security, modular, heavily MSP-sold, deliberately buys breadth.

**Customisation:** Coro's public positioning is about removing the need for many point tools. Do not
fight that. Frame as a module inside their consolidation story rather than another console, and lead
with the API rather than the alerting, since they will want to own the UI.

### 7. Guardz

**Their thesis:** MSP-native, unified detection with strong email and identity focus.

**Customisation:** the closest to overlap on this list, so be careful. Their identity risk is
tenant-side; ours is carrier-side and marketplace-side. If that distinction is not made in the first
three sentences, this one reads as a competitor and gets ignored.

---

## Message 1 — primary, short cold open (LinkedIn or email)

> **Subject: The attacks that never touch the endpoint, and a possible fit with Xcitium's MSP stack**
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
> there is nothing to contain, because nothing executed.
>
> RelayShield monitors that layer: live carrier queries for SIM/eSIM swap and port-out, breach and
> stealer-log exposure for a customer's people, lookalike domain registration, and OAuth grant
> abuse. It is not EDR and does not want to be. It is signal from outside the perimeter, delivered
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

> Hi <name>. Xcitium's containment story answers the "unknown binary on a box you own" problem
> better than most. I work on the attacks that never put a binary anywhere: SIM swap inside the
> carrier, stolen session cookies resuming an authenticated session, breached credentials that log
> in cleanly the first time. Endpoint stays healthy, nothing to contain.
>
> RelayShield monitors that layer: carrier-level SIM/port-out checks, breach and stealer-log
> exposure, lookalike domains, OAuth abuse, with connectors into Sentinel, XSOAR, Elastic and
> ConnectWise so it lands in a partner's existing workflow rather than a new console.
>
> Not an EDR, not pitching one. Is technology alliances the right door, or should I be talking to
> someone on channel?

## Message 3 — the follow-up, for a send that went quiet

Use once, after about ten working days. Do not re-pitch; add one fact and make the ask smaller.

> Hi <name>, following up once on the note below, then I will leave it.
>
> One thing I should have led with: the integration already exists on our side. A partner can pull
> this over an API or receive it in Sentinel, XSOAR, Elastic or ConnectWise today, so evaluating it
> costs an API key rather than a project.
>
> If technology alliances is not the right door, pointing me at the right one is a completely
> acceptable answer.

---

## If they reply

Send `relayshield_edr_mdr_complement_blog.md` and `RelayShield_MSP_Solution_Brief.md`, in that
order. The blog carries the argument; the brief carries the packaging.

**Before quoting any figure on a call, re-measure it.** The last measured set is in
`victim_side_outreach_messages.md` and was taken 2026-08-17 — treat anything older than about a week
as stale, and quote per-category exclusive numbers rather than a total.

## Tracking

Record for each send: date, company, person, door used (alliances / channel / product), and reply or
silence. Four sends with no structure is anecdote; twelve with structure tells you whether the
disjoint-attack-class argument works on this audience at all, which is the thing actually being
tested here.

Two signals worth watching specifically:

- **Which door replies.** If alliances is silent and channel answers, the motion is a channel motion
  and the messaging should change accordingly.
- **Which objection recurs.** If "we already have threat intelligence" comes back three times, the
  first paragraph is not doing its job and the carrier-signal distinction needs to move earlier.
