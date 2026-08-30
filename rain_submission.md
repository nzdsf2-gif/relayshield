# Rain: Agentic Startup Program application and the apa@rain.xyz email

Drafted 2026-08-30, from the analysis in `socradar_gap_closure_roadmap.md` (2026-08-27).

## Sequencing, which is not arbitrary

The roadmap's next-actions list ends: "**Then** apply to the Agentic Startup Program, and mail
apa@rain.xyz referencing it." Keep that order. The Alliance address is a coalition contact and an
unsolicited mail to it reads as "add us to a list", which is the one framing the roadmap says to
avoid. The same mail sent after an application, referencing it, reads as follow-through.

So: form first, email second, and the email names the application.

## Measurement rule, applying here with force

No corpus total. No endpoint count as a coverage claim. Nothing from
`exclusive_share_by_category.py` unless that category has cleared 100 collected indicators. Every
member of this Alliance can check a number, and several of them do this for a living.

Everything quantitative below is a thing that happened on-chain and can be verified by a stranger:
two payments of $0.35 in USDC on Base, and their transaction hashes.

---

## Part 1: Agentic Startup Program

Field names are a best guess at the form's shape. Match the answer to the question actually asked
rather than pasting a section into the wrong box.

**Company.** RelayShield

**What you build, in one line.**
Counterparty risk checks that an AI agent can call and pay for itself, before it connects to a tool
or pays an API.

**The problem.**
Agent payment infrastructure answers whether an agent is allowed to spend. It does not answer
whether the thing being paid is legitimate. An agent holding a valid single-use card, inside its
limits, against a verified account, paying a typosquatted API is a fully authorised transaction.
Every control in that path passes it, because every control is about the spender.

**What we do about it.**
We score the counterparty rather than the spender. Is this MCP server a near-miss of a real one. Was
the domain registered last week. Does it appear in a criminal indicator corpus. The checks are
priced per call and payable over x402 in USDC on Base, with no account and no API key, which means
an agent can use them autonomously at the moment of intent.

**Demo.**
Two minutes, unattended, no human in the loop and no account anywhere. An agent discovers two MCP
servers. It pays $0.35 over x402 to check each one before connecting. It refuses the typosquat and
proceeds with the legitimate one. The 402 challenge, the rail it selects, and the settled Base
transaction are all on screen, so the payments can be verified independently after the video ends.

**Why Rain specifically.**
The Agent Control Layer issues a single-use virtual card at the moment of intent. That moment is the
natural place for a counterparty check, because it is the last point at which refusing is free.
Checking before the card exists is strictly better than disputing after the charge.

**Traction, stated honestly.**
Endpoints are live and payable over x402 today, listed in the CDP Bazaar, and reachable from agent
frameworks through a published MCP server. The demo above is a real transaction, not a mock.

---

## Part 2: the email to apa@rain.xyz

Send after the application. Attach the recording, or link it if the file is too large for the
recipient's gateway.

**Subject:** Counterparty checks an agent can pay for, before the card is issued

> Hello,
>
> I run RelayShield. We build counterparty risk checks that an AI agent can call and pay for by
> itself, over x402 in USDC on Base, with no account.
>
> I have applied to the Agentic Startup Program, and I am writing here because the gap we work on
> sits squarely in the Alliance's stated scope.
>
> Agent payment controls answer whether an agent is allowed to spend. They do not answer whether the
> counterparty is legitimate. An agent with a valid single-use card, inside its limits, on a verified
> account, paying a typosquatted API is a fully authorised transaction. Nothing in the authorisation
> path is wrong. The money still goes to the wrong party.
>
> That is a different question from the ones already well covered here. Fraud and AML scoring, and
> blockchain analytics, assess the user and the funds. We assess the counterparty and the tool.
> Analytics will tell an agent that a wallet is sanctioned. It will not tell the agent that the MCP
> server it is about to grant tool-calling access to was registered three days ago and is one
> character away from the real one.
>
> Rather than describe it, here is a two minute recording of an agent doing it. It discovers two MCP
> servers, pays $0.35 over x402 to check each one before connecting, refuses the typosquat, and
> proceeds with the legitimate one. No human approves anything and no account is created. The 402
> challenge, the selected rail and the settled Base transactions are all visible, so the payments can
> be verified on-chain independently of the video.
>
> The reason I am writing to Rain and not more generally: the Agent Control Layer issues a single-use
> card at the moment of intent, and that moment is the natural hook for a counterparty check. It is
> the last point where declining costs nothing. If there is a pre-issuance hook in the API, that is
> the whole integration.
>
> Happy to walk through it live, or to answer in writing if that is easier.
>
> Andrew Gibbs
> RelayShield

---

## Before this goes out

- **Confirm the recording is legible end to end**, particularly the 402 lines and the settled
  transaction hashes. They are the only claims in the email a reader can check, so they are the ones
  that must be readable.
- **Decide the sending address.** The Gmail account is a personal one. `support@relayshield.net`
  exists and reads better to a payments company, but only if it is a mailbox that will see a reply.
- **Test the Sardine and Chainalysis paragraph on someone outside the project**, per the roadmap's
  next-actions item 3. It is the paragraph most likely to decide whether this reads as a peer or as
  a worse version of a member. If it does not survive a first read, it will not survive theirs.
- **Roadmap item 1 is still open**: read the Agent Control Layer API docs and find whether a
  pre-issuance hook exists. The email asks the question rather than assuming the answer, which is
  survivable, but knowing beforehand would be better.
