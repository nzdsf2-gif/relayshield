# Draft reply to MosheEichler on demisto/content#45206

Status checked live 2026-08-09: PR open, mergeable, `docs-approved` applied,
labels `pending-demo` + `pending-contributor`. Moshe pinged 2026-08-09 04:25.

NOT FOR PUBLICATION below the line at the bottom.

---

Hi @MosheEichler, thanks for the nudge, and apologies for the quiet stretch.

No help needed on the code. The pack is where we want it and I see `docs-approved`
went on, so thank you for that.

The one thing outstanding on our side is the demo. We do not run a Cortex XSOAR
tenant of our own, which is why this went through GitHub rather than the
Marketplace UI in the first place, so I signed up for Community Edition to have
somewhere to run it. I am recording rather than booking a live session, since
your demo-prep page allows it and it saves coordinating across timezones after
I have already kept you waiting.

Planning to cover, straight off demo-prep:

- product overview and the use cases the pack serves
- the commands implemented, and a run of each against a live instance
- instance configuration, including where the API key comes from
- error handling on invalid credentials
- command verification against the standards: arguments, outputs, descriptions

One thing worth stating up front so it does not look like an omission: this pack
is reputation commands only. There is no fetch-incidents, no playbooks and no
layouts, so those sections of demo-prep do not apply.

I will have the recording to you by Friday 21 August. If you would rather have
it as a live session over the DFIR Slack after all, say the word and I will
book one.

Thanks again for the patience on this one.

---
NOT FOR PUBLICATION

- Fill in `<DATE>` before posting. Do not post an open-ended timeline; that is
  what produced the six-day gap Moshe is chasing.
- No em-dashes, en-dashes or double hyphens anywhere above. Checked.
- Do NOT narrate unraised defects to him. Reviewer-reply scope rule.
- Community Edition signup is done per founder. The remaining unknown is whether
  the free tier (post 30-day trial) still allows installing a custom pack from a
  contribution branch. Verify that BEFORE promising a date.
