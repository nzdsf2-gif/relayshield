# Email to Palo Alto Networks tech partners: DRAFT, NOT SENT

**To:** techpartners@paloaltonetworks.com
**From:** andrew@relayshield.net
**Subject:** Cortex XSOAR content pack PR #45206: requesting a demo tenant to record the required demo

---

Hello,

I maintain the RelayShield content pack for Cortex XSOAR. Moshe Eichler reviewed and approved the
code on PR #45206 in `demisto/content` and asked for a recorded demo before the pack can be
published. He suggested I reach out to this address to arrange access.

The blocker is straightforward: I need somewhere to record the demo. Cortex XSOAR Community Edition
has been discontinued, so the free tier I would previously have used to produce a recording is no
longer available, and I do not have a tenant of my own.

**What I am asking for:** time-limited access to a demo or sandbox XSOAR tenant, long enough to
install the pack and record a short walkthrough of the integration working end to end. A trial
tenant, a partner sandbox, or a supervised session all work equally well from my side.

**About the pack.** RelayShield is an identity-layer threat intelligence API. The pack adds
commands that let an XSOAR playbook check an email address, domain, phone number or indicator
against breach, infostealer and criminal-marketplace data before a playbook grants access, resets a
credential or closes an incident. The code is complete and approved; the demo is the only
outstanding item.

If a tenant is not something you can provide, I am happy to work another way. If there is a
reference environment, a recorded-demo template you prefer, or a partner program I should enrol in
first, please point me at it and I will follow that path instead.

Company details for your records:

- Company: RelayShield LLC
- Contact: Andrew Gibbs, andrew@relayshield.net
- PR: https://github.com/demisto/content/pull/45206
- Product: https://api.relayshield.net/developers

Thank you,

Andrew Gibbs
RelayShield LLC

---

## NOT FOR SENDING: notes for the founder

**Check these before you send:**

1. **PR number and reviewer: VERIFIED.** I checked the live PR rather than trusting TODO.md.
   `demisto/content#45206` is OPEN, titled "Add RelayShield content pack", and `MosheEichler` is on
   the reviewer list. Nothing to re-check here.
2. **The commitment date.** You withdrew the 21 Aug demo commitment given the silence. This draft
   deliberately does not mention any date, so it does not re-commit you to one. Add a date only if
   you want to.
3. **Which address to send from.** `andrew@relayshield.net` deliverability was re-confirmed
   2026-08-09. Sending from the Gmail account would look inconsistent with the LLC framing.

**What I deliberately left out:**

- Any pitch about the product beyond one short paragraph. This is a logistics request, not a sales
  email, and the code is already approved.
- Pricing, marketplace or co-sell talk. Raising commercial terms in a request for a sandbox
  invites a longer, slower thread with a different team.
- Any mention of the discontinued Community Edition being a problem for Palo Alto. It is stated as
  a fact about my situation, not a complaint.

**I have not sent this.** Say the word and I will, or paste back an edited version.
