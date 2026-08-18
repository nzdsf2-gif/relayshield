# Cyber Insurance Outreach — Talking Points & At-Bay Message

Status: talking points reusable across carriers/MGAs; At-Bay message ready to send tomorrow (2026-07-22).

## Core positioning (use for every carrier)

**The pitch is a B2B underwriting/risk-signal data source, not a consumer benefit.**
This distinction matters — it's what separates RelayShield's angle from a company like
Enfortra (white-label dark-web/credit monitoring sold *through* an insurer *to* their
policyholders as a perk). RelayShield is the opposite direction: feeding a real-time
identity-compromise signal *into the insurer's own* underwriting and risk-monitoring —
the same role Coalition Control or At-Bay's own security monitoring already plays for
device/network-surface signals. Never let this get filed next to a policyholder-benefit
pitch; say "underwriting signal" explicitly, not "monitoring benefit."

**What RelayShield sees that existing carrier telemetry doesn't:**
- Breach exposure (email/credential appears in a known breach)
- Infostealer/stealer-log detection — 24-72 hours ahead of public breach databases
- Active stolen session material (cookies/tokens circulating in criminal archives) —
  bypasses password resets and 2FA entirely, a signal device/network monitoring can't see
- SIM swap / carrier port detection in real time
- Domain lookalike / phishing infrastructure targeting a specific insured
- Ransomware group victim/leak-site presence, often with pre-ransomware credential
  harvesting detected beforehand

The common thread: this is **identity-layer compromise**, not transaction-shape or
device/network anomalies. Carriers doing continuous security-signal underwriting
(Coalition Control, At-Bay Security) already have the device/network side covered —
identity-layer is the gap.

**Why this matters to the carrier specifically, not just "more data":**
- Underwriting precision — a policyholder with active infostealer exposure or breached
  credentials is a materially different risk than a clean one, today, not at renewal
- Retention — flagging emerging exposure to a policyholder before it becomes a claim is
  a genuine value-add the carrier can point to
- Competitive differentiation — few carriers have identity-layer signal in their
  underwriting stack yet; this is a "we see something others don't" story

**Framing by buyer type (learned from Vouch/Coalition outreach):**
- Technical/advisor contacts (like Vouch's Joyce Calixto) → lead with *what the signal
  is* and how it's distinct from what they already monitor
- Business/revenue contacts (like Coalition's CRO) → lead with the *underwriting
  precision / retention / differentiation* framing first, technical detail second
- A contact who owns both the security *product line* and business development (see
  At-Bay below) → closer to the business framing, but can reference the product
  integration angle more directly since they'd own that decision too

## At-Bay — recommended contact

At-Bay has three plausible contacts; recommending **Thom Dekens, Chief Business Officer
& General Manager of At-Bay Security** as the primary target — he owns both the BD
relationship and the specific product line (At-Bay Security, their continuous-monitoring
offering) this pitch would plug into, a closer match than a pure CRO ask. Alternates:
**Roman Itskovich** (Co-Founder & CRO — mirrors the exact role used successfully for the
Coalition outreach) as the fallback if Dekens isn't reachable or routes elsewhere, and
**Kristie Felton** (Head of Insurance, oversees partnerships) as a third option if this
reads better as an insurance-operations relationship than a security-product one.

## Message to send — At-Bay (Thom Dekens)

> Subject: Identity-layer signal for At-Bay Security's underwriting stack
>
> Hi Thom,
>
> I run RelayShield — real-time identity-compromise threat intelligence (breach,
> infostealer, active stolen-session, SIM-swap, and domain-impersonation detection),
> currently live via API and already integrated into our own cyber/E&O coverage
> underwriting process as a policyholder.
>
> At-Bay Security already does continuous security-signal-driven monitoring on the
> device/network side. What we see is the identity layer specifically — credential and
> session compromise that shows up 24-72 hours ahead of public breach databases, and
> account-takeover signals (like active stolen session cookies) that bypass password
> resets and 2FA entirely. That's a different signal type than device/network anomalies,
> not a competing one.
>
> Would it be useful to explore feeding this into At-Bay's own underwriting/monitoring
> stack as a complementary data source — sharper risk assessment on active policies, and
> earlier warning on emerging exposure before it becomes a claim? Happy to walk through
> exactly what the signal looks like and how it'd integrate.
>
> Andrew
> RelayShield

## Cowbell — recommended contact, researched 2026-08-14

**Cowbell is the best-fit carrier left on the list.** Their whole model is continuous external risk
assessment (Cowbell Factors), so nobody there needs the concept of an outside signal explained. The
question is only who decides.

**Primary: Rajeev Gupta, Co-Founder & Chief Product Officer.**
Cowbell Factors is a **product**, so adding a signal to it is a product decision, not an underwriting
one. He is also a co-founder, which means he can decide without a committee. That is the same "one
person decides" logic used to rank the Discord targets, and it is the single biggest predictor of
whether a small vendor gets a real answer. Founder to founder is also a genuine advantage here.

**Alternate: Kara Owens, Chief Insurance Officer.** Her remit covers risk and portfolio management
plus new product development and innovation, so she is the insurance-side owner of exactly this. Use
her if Gupta routes it or does not reply.

**Others on the leadership team**, for context rather than as targets: Jack Kudale (Founder & CEO),
Trent Cooksley (Co-Founder & COO), Simon Hughes (Chief Commercial Officer), Joshua Chan (CTO), Emma
Werth (VP, Underwriting & Reinsurance).

> **DO NOT contact Caroline Thompson.** She was Chief Underwriting Officer and would have been the
> obvious pick. She left Cowbell for a new cyber MGA called Elixir. She is still returned by search
> as though she holds the role.

### The staleness pattern is now three for three, so treat verification as mandatory

Every insurance contact researched through search aggregators in this project has had at least one
departed name attached:

| Company | Name returned | Reality |
|---|---|---|
| Vouch | Amy Becht, Head of Partnerships | Left around March 2024 |
| Vouch | Sebastian Chen Schmidt, Embedded Partnerships Lead | Left last year, caught on LinkedIn before sending |
| Cowbell | Caroline Thompson, Chief Underwriting Officer | Left for Elixir |

**Check LinkedIn before sending. Every time.** This is no longer a precaution, it is a step.

### Do NOT reuse the Vouch message. Two reasons, both fatal.

Founder asked 2026-08-14 whether the Clark Kays message works here. It does not.

1. **Wrong ask.** The Vouch message requests a slot in a *technology partner program*, because Vouch
   sold its underwriting arm and has nothing to feed. Cowbell is a real MGA that underwrites its own
   book. The correct pitch here is the underwriting-signal one.
2. **The opener does not exist.** The Vouch message's whole power was "I'm a Vouch policyholder",
   the one line a cold vendor cannot write. **You are not a Cowbell customer.** Remove that sentence
   and what remains is a cold email making an ask that does not apply to them.

### The Cowbell message

The cold-open substitute for policyholder standing is **demonstrating you know their product and can
name the specific gap in it**. Cowbell Factors is the hook.

```text
Subject: The signal Cowbell Factors can't see

Hi Rajeev,

Cowbell Factors already scores continuous outside-in risk, which is more than most carriers have. I want to describe one dimension it structurally can't reach, because I think it's complementary rather than competing.

RelayShield is identity-layer threat intelligence. We detect when a company's credentials, active session cookies and OAuth tokens are circulating in infostealer logs and criminal marketplaces, usually ahead of the public breach databases.

Outside-in scoring sees a company's attack surface: exposed services, misconfigurations, patch posture. It cannot see whether the people inside it already have working credentials or live session material in criminal hands. Stolen session cookies matter most here, because they survive a password reset and bypass MFA, so they never appear in any control an insured can attest to on an application.

It also moves on a different clock. Attack surface changes slowly. Identity exposure changes the day a stealer log drops, which makes it a portfolio monitoring signal on active policies as much as an underwriting one.

Would a short conversation be worth it? Happy to run it live against any domain you want to pick.

Andrew Gibbs
RelayShield
```

**Why it is built this way**

**The subject line is the pitch.** It names their product and asserts a gap, which is the only thing
that earns a click from a co-founder with a full inbox.

**"More than most carriers have" is genuine credit, not flattery.** Cowbell built that capability and
he co-founded the company. Opening by conceding their strength makes the gap claim credible instead
of adversarial.

**"Complementary rather than competing" appears in the first paragraph** because a CPO's first
instinct on hearing about an external risk signal is "we already do that". Answer it before he thinks
it.

**The portfolio-monitoring paragraph is the easier sale.** It requires no change to the underwriting
workflow, only a feed. Same reasoning as the Corix message to Lori Bailey.

**Same live-demo offer as Corix**, which is now safe to make: the em-dash defect in the
`identity-risk-score` summary was fixed and deployed 2026-08-14.

## Reusable next-carrier checklist

1. Identify the contact who owns either BD/partnerships or the security-product line
   specifically (not general sales, not a pure technical/engineering contact)
2. Lead with underwriting precision/retention if business-framed contact, or the
   signal-distinctness technical framing if advisor/technical contact
3. Always name the specific signals (breach/infostealer/session/SIM-swap/domain/
   ransomware), never a vague "monitoring" claim
4. Explicitly frame as underwriting-signal, never policyholder-benefit, to avoid
   collision with white-label identity-protection vendors already selling into the
   same buyer
